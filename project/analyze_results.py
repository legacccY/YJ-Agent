"""ITB 结果分析 + 论文图表生成（v2：classwise ECE + smooth calibration + wide entropy panel）。

Usage:
  cd D:/YJ-Agent/project
  python analyze_results.py

Outputs (results/figures/):
  fig1_comparison_bars.png  — AUC / ECE / MeanEntropy 对比柱状图
  fig2_calibration.png      — isotonic-smoothed 校准曲线（LQ vs HQ）
  fig3_entropy_qbar.png     — Entropy vs q̄（单宽幅，±1 SEM，Proposition 2 核心图）
  fig4_entropy_kde.png      — LQ vs HQ 预测熵 KDE 分布
  itb_ablation.csv          — 消融实验汇总表
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.stats import gaussian_kde
from sklearn.isotonic import IsotonicRegression

from benchmark.metrics import compute_binary_ece, compute_qbar_ece, summary_metrics

PRED_CSV     = "results/itb_predictions.csv"
FIG_DIR      = Path("results/figures")
ABLATION_CSV = "results/itb_ablation.csv"

BASELINE_ORDER  = ["D", "E", "F"]
BASELINE_LABELS = {"D": "Std VIB", "E": "Adaptive Prior", "F": "Q-VIB Full (Ours)"}
BASELINE_COLORS = {"D": "#4878CF", "E": "#6ACC65", "F": "#D65F5F"}
SUBSET_ORDER    = ["ITB-HQ", "ITB-Edge", "ITB-LQ", "ITB-Diverse"]
SUBSET_SHORT    = {"ITB-HQ": "HQ", "ITB-Edge": "Edge", "ITB-LQ": "LQ", "ITB-Diverse": "Diverse"}

PLT_DPI = 300
plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 8,
    "axes.titlesize": 9,
    "axes.labelsize": 8,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "legend.fontsize": 7,
    "lines.linewidth": 1.3,
    "axes.spines.top": False,
    "axes.spines.right": False,
})


def load_predictions():
    return pd.read_csv(PRED_CSV)


def recompute_summary(preds: pd.DataFrame) -> pd.DataFrame:
    """Recompute summary metrics from per-sample predictions using classwise ECE."""
    rows = []
    for bk in BASELINE_ORDER:
        for subset in SUBSET_ORDER:
            sub = preds[(preds["baseline"] == bk) & (preds["subset"] == subset)]
            if len(sub) == 0:
                continue
            pp = sub["prob_pos"].values
            tg = sub["target"].values
            qb = sub["qbar"].values
            probs2 = np.stack([1 - pp, pp], axis=1)
            preds_cls = probs2.argmax(-1)
            from sklearn.metrics import roc_auc_score, f1_score, accuracy_score
            auc = (float(roc_auc_score(tg, pp))
                   if tg.sum() > 0 and tg.sum() < len(tg) else float("nan"))
            ece = compute_binary_ece(pp, tg) if subset != "ITB-Diverse" else float("nan")
            entropy = float(-(probs2.clip(1e-9) * np.log(probs2.clip(1e-9))).sum(-1).mean())
            rows.append({
                "baseline": bk, "baseline_name": BASELINE_LABELS[bk], "subset": subset,
                "n": len(tg), "auc": auc, "ece": ece,
                "f1": float(f1_score(tg, preds_cls, zero_division=0)),
                "acc": float(accuracy_score(tg, preds_cls)),
                "mean_entropy": entropy,
            })
    return pd.DataFrame(rows)


# ── Figure 1: AUC / ECE / MeanEntropy bars ────────────────────────────────────

def fig_comparison_bars(df: pd.DataFrame):
    metrics = [
        ("auc",          "AUC-ROC ↑",        (0.4, 1.0)),
        ("ece",          "Binary ECE ↓",      (0.0, 0.20)),
        ("mean_entropy", "Mean Entropy",       None),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(6.8, 2.3))
    x = np.arange(len(SUBSET_ORDER))
    width = 0.22

    for ax, (col, title, ylim) in zip(axes, metrics):
        for i, bk in enumerate(BASELINE_ORDER):
            sub = df[df["baseline"] == bk].set_index("subset")
            vals = []
            hatches = []
            for s in SUBSET_ORDER:
                v = sub.loc[s, col] if s in sub.index else float("nan")
                vals.append(v)
                # ECE for Diverse is nan → hatch to signal excluded
                hatches.append("////" if (col == "ece" and s == "ITB-Diverse") else "")
            offset = (i - 1) * width
            for j, (v, h) in enumerate(zip(vals, hatches)):
                if np.isnan(v):
                    ax.bar(x[j] + offset, 0, width, color=BASELINE_COLORS[bk],
                           alpha=0.25, edgecolor="grey", linewidth=0.5, hatch="////")
                else:
                    ax.bar(x[j] + offset, v, width,
                           label=BASELINE_LABELS[bk] if j == 0 else "",
                           color=BASELINE_COLORS[bk], alpha=0.85,
                           edgecolor="white", linewidth=0.5)

        ax.set_title(title)
        ax.set_xticks(x)
        ax.set_xticklabels([SUBSET_SHORT[s] for s in SUBSET_ORDER], rotation=15)
        if ylim:
            ax.set_ylim(*ylim)

    # ECE: add note about Diverse exclusion
    axes[1].text(0.98, 0.97, "Diverse: N/A\n(4% pos. rate)",
                 transform=axes[1].transAxes, ha="right", va="top",
                 fontsize=6, color="grey", style="italic")

    axes[0].legend(loc="lower right", framealpha=0.7)
    fig.tight_layout(pad=0.5)
    out = FIG_DIR / "fig1_comparison_bars.png"
    fig.savefig(out, dpi=PLT_DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved {out}")


# ── Figure 2: Isotonic-smoothed calibration curves ───────────────────────────

def fig_calibration(preds: pd.DataFrame):
    subsets_to_plot = ["ITB-LQ", "ITB-HQ"]
    fig, axes = plt.subplots(1, 2, figsize=(5.0, 2.5))

    for ax, subset in zip(axes, subsets_to_plot):
        sub = preds[preds["subset"] == subset]
        ax.plot([0, 1], [0, 1], "k--", linewidth=0.8, label="Perfect", alpha=0.6)

        for bk in BASELINE_ORDER:
            b = sub[sub["baseline"] == bk].sort_values("prob_pos")
            if len(b) == 0:
                continue
            pp = b["prob_pos"].values
            tg = b["target"].values

            # Isotonic regression: smooth calibration without hard bins
            ir = IsotonicRegression(out_of_bounds="clip")
            ir.fit(pp, tg)
            pp_grid = np.linspace(pp.min(), pp.max(), 200)
            frac_smooth = ir.predict(pp_grid)

            ax.plot(pp_grid, frac_smooth, "-", linewidth=1.4,
                    color=BASELINE_COLORS[bk], label=BASELINE_LABELS[bk])

        ax.set_title(subset)
        ax.set_xlabel("Predicted P(malignant)")
        ax.set_ylabel("Observed fraction positive")
        ax.set_xlim(0, 1); ax.set_ylim(0, 1)

    axes[0].legend(loc="upper left", framealpha=0.8)
    fig.tight_layout(pad=0.5)
    out = FIG_DIR / "fig2_calibration.png"
    fig.savefig(out, dpi=PLT_DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved {out}")


# ── Figure 3: Entropy vs q̄ (single wide panel, ±1 SEM) ──────────────────────

def fig_entropy_qbar(preds: pd.DataFrame):
    """Key Proposition 2 figure: entropy decreases with quality for Q-VIB but not Std VIB."""
    n_bins = 6
    fig, ax = plt.subplots(figsize=(4.5, 2.6))

    for bk in BASELINE_ORDER:
        b = preds[preds["baseline"] == bk].copy()
        segs = compute_qbar_ece(b["prob_pos"].values, b["target"].values,
                                b["qbar"].values, n_bins=n_bins)
        if not segs:
            continue
        qmid = np.array([s["q_mean"] for s in segs])
        ent  = np.array([s["entropy_mean"] for s in segs])
        sem  = np.array([s["entropy_sem"] for s in segs])

        ax.plot(qmid, ent, "o-", markersize=4.5,
                color=BASELINE_COLORS[bk], label=BASELINE_LABELS[bk], zorder=3)
        ax.fill_between(qmid, ent - sem, ent + sem,
                        color=BASELINE_COLORS[bk], alpha=0.15, zorder=2)

    ax.set_xlabel("Mean quality score $\\bar{q}$")
    ax.set_ylabel("Predictive entropy $H$")
    ax.set_title("Entropy decreases with quality (Proposition 2)")
    ax.legend(loc="upper right", framealpha=0.8)

    # Annotate direction
    ax.annotate("Q-VIB sensitive\nto quality ↓",
                xy=(0.65, 0.153), xytext=(0.55, 0.165),
                fontsize=6, color=BASELINE_COLORS["F"],
                arrowprops=dict(arrowstyle="->", color=BASELINE_COLORS["F"], lw=0.8))

    fig.tight_layout(pad=0.5)
    out = FIG_DIR / "fig3_entropy_qbar.png"
    fig.savefig(out, dpi=PLT_DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved {out}")


# ── Figure 4: Entropy KDE — LQ vs HQ ─────────────────────────────────────────

def fig_entropy_kde(preds: pd.DataFrame):
    fig, axes = plt.subplots(1, 2, figsize=(5.5, 2.4))
    x_grid = np.linspace(0, 0.8, 300)

    for ax, subset in zip(axes, ["ITB-LQ", "ITB-HQ"]):
        sub = preds[preds["subset"] == subset]
        for bk in BASELINE_ORDER:
            b = sub[sub["baseline"] == bk]
            if len(b) == 0:
                continue
            probs2 = np.stack([1 - b["prob_pos"].values, b["prob_pos"].values], axis=1).clip(1e-9)
            entropy = -(probs2 * np.log(probs2)).sum(-1)
            kde = gaussian_kde(entropy, bw_method=0.25)
            ax.plot(x_grid, kde(x_grid), linewidth=1.4,
                    color=BASELINE_COLORS[bk], label=BASELINE_LABELS[bk])
            ax.fill_between(x_grid, kde(x_grid), alpha=0.12, color=BASELINE_COLORS[bk])

        ax.set_title(f"Entropy ({subset})")
        ax.set_xlabel("Prediction entropy $H$")
        ax.set_ylabel("Density")
        ax.set_xlim(0, 0.75)
        ax.set_ylim(bottom=0)

    axes[0].legend(framealpha=0.8)
    fig.tight_layout(pad=0.5)
    out = FIG_DIR / "fig4_entropy_kde.png"
    fig.savefig(out, dpi=PLT_DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved {out}")


# ── Ablation CSV + bootstrap significance ────────────────────────────────────

def save_ablation_and_stats(df: pd.DataFrame, preds: pd.DataFrame):
    abl_rows = []
    for bk in BASELINE_ORDER:
        for subset in SUBSET_ORDER:
            sub = df[(df["baseline"] == bk) & (df["subset"] == subset)]
            if len(sub) == 0:
                continue
            r = sub.iloc[0]
            abl_rows.append({
                "baseline": bk, "name": BASELINE_LABELS[bk], "subset": subset,
                "AUC": round(r["auc"], 3),
                "ECE": round(r["ece"], 3) if not np.isnan(r["ece"]) else "N/A",
                "F1": round(r["f1"], 3),
                "MeanEntropy": round(r["mean_entropy"], 3),
            })
    abl = pd.DataFrame(abl_rows)
    abl.to_csv(ABLATION_CSV, index=False)
    print(f"  Saved {ABLATION_CSV}")
    print()
    print(abl.to_string(index=False))

    # Bootstrap significance: Entropy on ITB-LQ (Q-VIB vs Std VIB)
    print("\n── Bootstrap significance (Mean Entropy, ITB-LQ) ──")
    lq = preds[preds["subset"] == "ITB-LQ"]
    rng = np.random.default_rng(42)
    for bk_a, bk_b in [("F", "D"), ("F", "E")]:
        a = lq[lq["baseline"] == bk_a]["prob_pos"].values
        b = lq[lq["baseline"] == bk_b]["prob_pos"].values
        diffs = []
        for _ in range(2000):
            s = rng.integers(0, len(a), size=len(a))
            def ent(pp):
                p2 = np.stack([1-pp, pp], axis=1).clip(1e-9)
                return float(-(p2*np.log(p2)).sum(-1).mean())
            diffs.append(ent(a[s]) - ent(b[s]))
        diffs = np.array(diffs)
        ci_lo, ci_hi = np.percentile(diffs, [2.5, 97.5])
        sig = "p<0.05" if ci_lo > 0 else "n.s."
        print(f"  H({BASELINE_LABELS[bk_a]}) - H({BASELINE_LABELS[bk_b]}): "
              f"Delta={diffs.mean():+.4f}  95% CI [{ci_lo:.4f}, {ci_hi:.4f}]  {sig}")


def main():
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading predictions and recomputing metrics (classwise binary ECE)...")
    preds = load_predictions()
    df = recompute_summary(preds)
    print(f"  {len(preds)} per-sample rows | {df['baseline'].nunique()} baselines | "
          f"{df['subset'].nunique()} subsets")
    print()
    print(df[["baseline_name","subset","auc","ece","mean_entropy"]].to_string(index=False))

    print("\nGenerating figures...")
    fig_comparison_bars(df)
    fig_calibration(preds)
    fig_entropy_qbar(preds)
    fig_entropy_kde(preds)
    save_ablation_and_stats(df, preds)

    print("\nDone.")


if __name__ == "__main__":
    main()
