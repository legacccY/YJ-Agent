"""ITB 结果分析 + 论文图表生成（v3：顶会标准）。

Usage:
  cd D:/YJ-Agent/project
  python analyze_results.py

Outputs (results/figures/):
  fig1_comparison_bars.png   — AUC / Binary ECE / MeanEntropy 对比（A/D/E/F × 4 子集）
  fig2_calibration.png       — Isotonic 校准曲线（LQ vs HQ）
  fig3_entropy_qbar.png      — Entropy vs q̄ ±SEM（Proposition 2 核心图）
  fig4_entropy_kde.png       — LQ vs HQ 熵分布 KDE
  fig5_kl_sigma.png          — σ²(q̄) 理论曲线 + 实证 KL 项双轴图（Lemma 1）
  fig6_agent_turns.png       — Agent 交互轮次小提琴图
  itb_ablation.csv           — 消融实验汇总表（含 Brier Score）
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from scipy.stats import gaussian_kde
from sklearn.isotonic import IsotonicRegression

from benchmark.metrics import compute_binary_ece, compute_qbar_ece, sensitivity_at_specificity

PRED_CSV       = "results/itb_predictions.csv"
AGENT_CSV      = "results/itb_agent_eval.csv"
FIG_DIR        = Path("results/figures")
ABLATION_CSV   = "results/itb_ablation.csv"

BASELINE_ORDER  = ["A", "D", "E", "F", "G"]
BASELINE_LABELS = {
    "A": "EfficientNet-B3\n(Direct)",
    "D": "Std VIB",
    "E": "Adaptive Prior",
    "F": "Q-VIB Full",
    "G": "Q-VIB+TokFT (Ours)",
}
BASELINE_COLORS = {"A": "#888888", "D": "#4878CF", "E": "#6ACC65", "F": "#E8A838", "G": "#D65F5F"}
SUBSET_ORDER   = ["ITB-HQ", "ITB-Edge", "ITB-LQ", "ITB-Diverse"]
SUBSET_SHORT   = {"ITB-HQ": "HQ", "ITB-Edge": "Edge", "ITB-LQ": "LQ", "ITB-Diverse": "Diverse"}

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


# ── Data loaders ─────────────────────────────────────────────────────────────

def load_predictions():
    return pd.read_csv(PRED_CSV)


def brier_score(prob_pos: np.ndarray, targets: np.ndarray) -> float:
    return float(np.mean((prob_pos - targets) ** 2))


def delong_auc_ci(prob_pos, targets, n_boot=2000, rng=None):
    """Bootstrap AUC with 95% CI (DeLong's method approximated by bootstrap)."""
    from sklearn.metrics import roc_auc_score
    if targets.sum() == 0 or targets.sum() == len(targets):
        return float("nan"), float("nan"), float("nan")
    rng = rng or np.random.default_rng(42)
    base_auc = float(roc_auc_score(targets, prob_pos))
    boot_aucs = []
    for _ in range(n_boot):
        idx = rng.integers(0, len(targets), size=len(targets))
        t, p = targets[idx], prob_pos[idx]
        if t.sum() == 0 or t.sum() == len(t):
            continue
        boot_aucs.append(float(roc_auc_score(t, p)))
    if not boot_aucs:
        return base_auc, float("nan"), float("nan")
    ci = np.percentile(boot_aucs, [2.5, 97.5])
    return base_auc, float(ci[0]), float(ci[1])


def recompute_summary(preds: pd.DataFrame) -> pd.DataFrame:
    from sklearn.metrics import roc_auc_score, f1_score, accuracy_score
    rows = []
    rng = np.random.default_rng(42)
    for bk in BASELINE_ORDER:
        for subset in SUBSET_ORDER:
            sub = preds[(preds["baseline"] == bk) & (preds["subset"] == subset)]
            if len(sub) == 0:
                continue
            pp = sub["prob_pos"].values
            tg = sub["target"].values
            qb = sub["qbar"].values
            p2 = np.stack([1 - pp, pp], axis=1).clip(1e-9)
            preds_cls = p2.argmax(-1)
            auc, auc_lo, auc_hi = delong_auc_ci(pp, tg, rng=rng)
            ece = compute_binary_ece(pp, tg) if subset != "ITB-Diverse" else float("nan")
            bs  = brier_score(pp, tg)
            entropy = float(-(p2 * np.log(p2)).sum(-1).mean())
            sens95 = sensitivity_at_specificity(pp, tg, target_spec=0.95)
            rows.append({
                "baseline": bk, "baseline_name": BASELINE_LABELS[bk].replace("\n", " "),
                "subset": subset, "n": len(tg),
                "auc": auc, "auc_lo": auc_lo, "auc_hi": auc_hi,
                "ece": ece, "brier": bs,
                "f1": float(f1_score(tg, preds_cls, zero_division=0)),
                "acc": float(accuracy_score(tg, preds_cls)),
                "mean_entropy": entropy,
                "sensitivity_at_95spec": sens95,
            })
    return pd.DataFrame(rows)


# ── Figure 1: Comparison bars (A / D / E / F) ────────────────────────────────

def fig_comparison_bars(df: pd.DataFrame):
    metrics = [
        ("auc",          "AUC-ROC ↑",      (0.4, 1.0)),
        ("ece",          "Binary ECE ↓",   (0.0, 0.15)),
        ("mean_entropy", "Mean Entropy",    None),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(6.8, 2.5))
    x = np.arange(len(SUBSET_ORDER))
    n_b = len(BASELINE_ORDER)
    width = 0.18

    for ax, (col, title, ylim) in zip(axes, metrics):
        for i, bk in enumerate(BASELINE_ORDER):
            sub = df[df["baseline"] == bk].set_index("subset")
            vals, yerr_lo, yerr_hi = [], [], []
            for s in SUBSET_ORDER:
                v = sub.loc[s, col] if s in sub.index and not np.isnan(sub.loc[s, col]) else float("nan")
                vals.append(v)
                if col == "auc" and s in sub.index:
                    lo = sub.loc[s, "auc_lo"] if not np.isnan(sub.loc[s, "auc_lo"]) else v
                    hi = sub.loc[s, "auc_hi"] if not np.isnan(sub.loc[s, "auc_hi"]) else v
                    yerr_lo.append(v - lo); yerr_hi.append(hi - v)
                else:
                    yerr_lo.append(0); yerr_hi.append(0)

            offset = (i - (n_b - 1) / 2) * width
            for j, (v, elo, ehi) in enumerate(zip(vals, yerr_lo, yerr_hi)):
                if np.isnan(v):
                    ax.bar(x[j] + offset, 0, width, color=BASELINE_COLORS[bk],
                           alpha=0.2, edgecolor="grey", linewidth=0.5, hatch="////")
                else:
                    bar = ax.bar(x[j] + offset, v, width,
                                 label=BASELINE_LABELS[bk].replace("\n", " ") if j == 0 else "",
                                 color=BASELINE_COLORS[bk], alpha=0.85, edgecolor="white", linewidth=0.4)
                    if col == "auc" and (elo + ehi) > 0:
                        ax.errorbar(x[j] + offset, v, yerr=[[elo], [ehi]],
                                    fmt="none", color="black", capsize=2, linewidth=0.7)

        ax.set_title(title)
        ax.set_xticks(x)
        ax.set_xticklabels([SUBSET_SHORT[s] for s in SUBSET_ORDER], rotation=15)
        if ylim:
            ax.set_ylim(*ylim)

    axes[1].text(0.98, 0.97, "Diverse: N/A\n(class imbalance)",
                 transform=axes[1].transAxes, ha="right", va="top",
                 fontsize=6, color="grey", style="italic")
    axes[0].legend(loc="lower right", framealpha=0.75, ncol=1, fontsize=6)
    fig.tight_layout(pad=0.5)
    out = FIG_DIR / "fig1_comparison_bars.png"
    fig.savefig(out, dpi=PLT_DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  {out}")


# ── Figure 2: Calibration curves ─────────────────────────────────────────────

def fig_calibration(preds: pd.DataFrame):
    fig, axes = plt.subplots(1, 2, figsize=(5.2, 2.5))
    for ax, subset in zip(axes, ["ITB-LQ", "ITB-HQ"]):
        sub = preds[preds["subset"] == subset]
        ax.plot([0, 1], [0, 1], "k--", lw=0.8, label="Perfect", alpha=0.55)
        for bk in BASELINE_ORDER:
            b = sub[sub["baseline"] == bk].sort_values("prob_pos")
            if len(b) == 0:
                continue
            ir = IsotonicRegression(out_of_bounds="clip")
            ir.fit(b["prob_pos"].values, b["target"].values)
            grid = np.linspace(b["prob_pos"].min(), b["prob_pos"].max(), 300)
            ax.plot(grid, ir.predict(grid), lw=1.4, color=BASELINE_COLORS[bk],
                    label=BASELINE_LABELS[bk].replace("\n", " "))
        ax.set(title=subset, xlabel="Predicted P(malignant)",
               ylabel="Observed fraction positive", xlim=(0, 1), ylim=(0, 1))
    axes[0].legend(loc="upper left", framealpha=0.8, fontsize=6)
    fig.tight_layout(pad=0.5)
    out = FIG_DIR / "fig2_calibration.png"
    fig.savefig(out, dpi=PLT_DPI, bbox_inches="tight")
    plt.close(fig); print(f"  {out}")


# ── Figure 3: Entropy vs q̄ ±SEM ─────────────────────────────────────────────

def fig_entropy_qbar(preds: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(4.5, 2.8))
    n_bins = 6
    for bk in BASELINE_ORDER:
        b = preds[preds["baseline"] == bk]
        segs = compute_qbar_ece(b["prob_pos"].values, b["target"].values,
                                b["qbar"].values, n_bins=n_bins)
        if not segs:
            continue
        qmid = np.array([s["q_mean"] for s in segs])
        ent  = np.array([s["entropy_mean"] for s in segs])
        sem  = np.array([s["entropy_sem"] for s in segs])
        ax.plot(qmid, ent, "o-", ms=4.5, color=BASELINE_COLORS[bk],
                label=BASELINE_LABELS[bk].replace("\n", " "), zorder=3)
        ax.fill_between(qmid, ent - sem, ent + sem, color=BASELINE_COLORS[bk], alpha=0.13, zorder=2)

    ax.set(xlabel="Mean quality score $\\bar{q}$",
           ylabel="Predictive entropy $H$",
           title="Entropy decreases with image quality (Proposition 2)")
    ax.legend(loc="upper right", framealpha=0.8, fontsize=6.5)

    # Annotate Std VIB as flat
    ax.annotate("Std VIB: quality-agnostic",
                xy=(0.50, 0.204), xytext=(0.35, 0.215),
                fontsize=6, color=BASELINE_COLORS["D"],
                arrowprops=dict(arrowstyle="->", color=BASELINE_COLORS["D"], lw=0.8))
    ax.annotate("Q-VIB: quality-aware ↓",
                xy=(0.65, 0.153), xytext=(0.50, 0.165),
                fontsize=6, color=BASELINE_COLORS["F"],
                arrowprops=dict(arrowstyle="->", color=BASELINE_COLORS["F"], lw=0.8))

    fig.tight_layout(pad=0.5)
    out = FIG_DIR / "fig3_entropy_qbar.png"
    fig.savefig(out, dpi=PLT_DPI, bbox_inches="tight")
    plt.close(fig); print(f"  {out}")


# ── Figure 4: Entropy KDE ─────────────────────────────────────────────────────

def fig_entropy_kde(preds: pd.DataFrame):
    fig, axes = plt.subplots(1, 2, figsize=(5.5, 2.4))
    xg = np.linspace(0, 0.8, 300)
    for ax, subset in zip(axes, ["ITB-LQ", "ITB-HQ"]):
        sub = preds[preds["subset"] == subset]
        for bk in BASELINE_ORDER:
            b = sub[sub["baseline"] == bk]
            if len(b) == 0:
                continue
            p2 = np.stack([1 - b["prob_pos"].values, b["prob_pos"].values], axis=1).clip(1e-9)
            ent = -(p2 * np.log(p2)).sum(-1)
            kde = gaussian_kde(ent, bw_method=0.25)
            ax.plot(xg, kde(xg), lw=1.4, color=BASELINE_COLORS[bk],
                    label=BASELINE_LABELS[bk].replace("\n", " "))
            ax.fill_between(xg, kde(xg), alpha=0.10, color=BASELINE_COLORS[bk])
        ax.set(title=f"Entropy ({subset})", xlabel="Prediction entropy $H$",
               ylabel="Density", xlim=(0, 0.75)); ax.set_ylim(bottom=0)
    axes[0].legend(framealpha=0.8, fontsize=6)
    fig.tight_layout(pad=0.5)
    out = FIG_DIR / "fig4_entropy_kde.png"
    fig.savefig(out, dpi=PLT_DPI, bbox_inches="tight")
    plt.close(fig); print(f"  {out}")


# ── Figure 5: σ²(q̄) + empirical KL term (Lemma 1) ──────────────────────────

def fig_kl_sigma(preds: pd.DataFrame):
    """Dual-axis: left = theoretical σ²(q̄), right = empirical mean KL per q̄ bin."""
    # Theoretical σ²(q̄): sigma0_sq=0.1, tau=0.5, alpha=5.0
    q_grid = np.linspace(0.05, 0.85, 200)
    sigma0_sq, tau, alpha = 0.1, 0.5, 5.0
    sigma_sq_theory = sigma0_sq + (1 - sigma0_sq) / (1 + np.exp(-alpha * (-(q_grid - tau))))

    fig, ax1 = plt.subplots(figsize=(4.5, 2.8))
    ax2 = ax1.twinx()

    # Left: σ²(q̄) theoretical (one curve, label in left axis)
    ax1.plot(q_grid, sigma_sq_theory, "k-", lw=2.0, label=r"$\sigma^2(\bar{q})$ (theory)", zorder=5)
    ax1.fill_between(q_grid, sigma_sq_theory, sigma0_sq, alpha=0.08, color="black")
    ax1.set_xlabel("Mean quality score $\\bar{q}$")
    ax1.set_ylabel(r"Prior variance $\sigma^2(\bar{q})$", color="black")
    ax1.tick_params(axis="y", labelcolor="black")
    ax1.set_ylim(0, 1.05)

    # Right: empirical KL per q̄ bin for D/E/F (not A)
    n_bins = 6
    kl_baselines = ["D", "E", "F"]
    for bk in kl_baselines:
        b = preds[preds["baseline"] == bk]
        if "kl_term" not in b.columns or b["kl_term"].isna().all():
            continue
        b = b.dropna(subset=["kl_term"])
        # Bin by qbar
        b = b.copy(); b["qbin"] = pd.qcut(b["qbar"], n_bins, labels=False, duplicates="drop")
        kl_means, q_mids = [], []
        for bi in sorted(b["qbin"].dropna().unique()):
            seg = b[b["qbin"] == bi]
            kl_means.append(seg["kl_term"].mean())
            q_mids.append(seg["qbar"].mean())
        ax2.plot(q_mids, kl_means, "o--", ms=4, color=BASELINE_COLORS[bk],
                 label=f"KL ({BASELINE_LABELS[bk].replace(chr(10), ' ')})", lw=1.1, alpha=0.85)

    ax2.set_ylabel("Empirical KL divergence", color="#555")
    ax2.tick_params(axis="y", labelcolor="#555")
    ax2.spines["right"].set_visible(True)

    # Combined legend
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="center right",
               framealpha=0.8, fontsize=6)

    # CORRECTED NARRATIVE:
    # KL INCREASES with q̄ — this is expected behaviour, not an anomaly.
    # When quality is high, σ²(q̄) is small (tight prior), forcing the encoder
    # to compress more information into z → larger KL divergence.
    # This tighter compression leads to more discriminative latent codes
    # and lower prediction entropy (Proposition 2).
    ax1.annotate(
        "High quality → tighter prior\n($\\sigma^2\\downarrow$) → more compression (KL$\\uparrow$)",
        xy=(0.72, sigma0_sq + (1 - sigma0_sq) / (1 + np.exp(-5.0 * (-(0.72 - 0.5))))),
        xytext=(0.35, 0.65),
        fontsize=6, color="black",
        arrowprops=dict(arrowstyle="->", color="black", lw=0.8),
        bbox=dict(boxstyle="round,pad=0.2", fc="white", alpha=0.8, ec="grey", lw=0.5),
    )
    ax2.annotate(
        "KL↑ → lower entropy\n(Proposition 2)",
        xy=(0.70, 0),  # position adjusted at runtime; annotation anchored to ax2
        xytext=(0.20, ax2.get_ylim()[1] * 0.85 if ax2.get_ylim()[1] > 0 else 0.5),
        fontsize=6, color="#555",
        arrowprops=dict(arrowstyle="->", color="#555", lw=0.7),
    )

    ax1.set_title("Lemma 1: Tighter prior at high quality → stronger compression")
    fig.tight_layout(pad=0.5)
    out = FIG_DIR / "fig5_kl_sigma.png"
    fig.savefig(out, dpi=PLT_DPI, bbox_inches="tight")
    plt.close(fig); print(f"  {out}")


# ── Figure 6: Agent interaction turns violin ──────────────────────────────────

def fig_agent_turns(agent_df: pd.DataFrame):
    subsets = ["ITB-HQ", "ITB-Edge", "ITB-LQ"]
    palette = {"ITB-HQ": "#4878CF", "ITB-Edge": "#E8B84B", "ITB-LQ": "#D65F5F"}

    fig, axes = plt.subplots(1, 2, figsize=(5.5, 2.6))

    # Panel A: Turns violin
    ax = axes[0]
    data_by_subset = [agent_df[agent_df["subset"] == s]["turns"].values for s in subsets]
    parts = ax.violinplot(data_by_subset, positions=range(len(subsets)),
                          showmedians=True, showextrema=False)
    for i, (body, s) in enumerate(zip(parts["bodies"], subsets)):
        body.set_facecolor(palette[s]); body.set_alpha(0.7)
    parts["cmedians"].set_color("black"); parts["cmedians"].set_linewidth(1.5)
    ax.set_xticks(range(len(subsets)))
    ax.set_xticklabels([s.replace("ITB-", "") for s in subsets])
    ax.set_ylabel("Interaction turns"); ax.set_title("Agent Interaction Turns")
    ax.set_ylim(0.5, max(3.5, agent_df["turns"].max() + 0.5))

    # Panel B: Retake rate bar
    ax2 = axes[1]
    retake_rates = [agent_df[agent_df["subset"] == s]["retake_triggered"].mean() for s in subsets]
    bars = ax2.bar(range(len(subsets)), retake_rates,
                   color=[palette[s] for s in subsets], alpha=0.8, edgecolor="white")
    for bar, rate in zip(bars, retake_rates):
        ax2.text(bar.get_x() + bar.get_width() / 2, rate + 0.01, f"{rate:.0%}",
                 ha="center", va="bottom", fontsize=7)
    ax2.set_xticks(range(len(subsets)))
    ax2.set_xticklabels([s.replace("ITB-", "") for s in subsets])
    ax2.set_ylabel("Retake request rate"); ax2.set_title("Agent Retake Rate by Subset")
    ax2.set_ylim(0, 1.15)

    fig.tight_layout(pad=0.5)
    out = FIG_DIR / "fig6_agent_turns.png"
    fig.savefig(out, dpi=PLT_DPI, bbox_inches="tight")
    plt.close(fig); print(f"  {out}")


# ── Ablation CSV + significance tests ─────────────────────────────────────────

def save_ablation_and_stats(df: pd.DataFrame, preds: pd.DataFrame):
    rows = []
    for bk in BASELINE_ORDER:
        for subset in SUBSET_ORDER:
            sub = df[(df["baseline"] == bk) & (df["subset"] == subset)]
            if len(sub) == 0:
                continue
            r = sub.iloc[0]
            sens95 = r.get("sensitivity_at_95spec", float("nan"))
            rows.append({
                "Baseline": BASELINE_LABELS[bk].replace("\n", " "),
                "Subset": subset,
                "AUC": f"{r['auc']:.3f} [{r['auc_lo']:.3f}, {r['auc_hi']:.3f}]",
                "Sens@95Spec": f"{sens95:.3f}" if not np.isnan(sens95) else "N/A",
                "ECE": f"{r['ece']:.3f}" if not np.isnan(r["ece"]) else "N/A",
                "Brier": f"{r['brier']:.4f}",
                "Entropy": f"{r['mean_entropy']:.3f}",
                "F1": f"{r['f1']:.3f}",
            })
    abl = pd.DataFrame(rows)
    abl.to_csv(ABLATION_CSV, index=False)
    print(f"  {ABLATION_CSV}")
    print()
    print(abl.to_string(index=False))

    # Significance: bootstrap entropy on ITB-LQ (Q-VIB vs Std VIB, one-sided: H_F > H_D)
    print("\n── Bootstrap significance (Mean Entropy, ITB-LQ) ──")
    lq = preds[preds["subset"] == "ITB-LQ"]
    rng = np.random.default_rng(42)
    for bk_a, bk_b, direction in [("F", "D", "F>D"), ("F", "E", "F>E")]:
        a = lq[lq["baseline"] == bk_a]["prob_pos"].values
        b = lq[lq["baseline"] == bk_b]["prob_pos"].values
        diffs = []
        for _ in range(5000):
            s = rng.integers(0, len(a), size=len(a))
            def ent(pp):
                p2 = np.stack([1-pp, pp], axis=1).clip(1e-9)
                return float(-(p2 * np.log(p2)).sum(-1).mean())
            diffs.append(ent(a[s]) - ent(b[s]))
        diffs = np.array(diffs)
        p_one = float((diffs <= 0).mean())  # one-sided: P(H_F <= H_D)
        ci = np.percentile(diffs, [2.5, 97.5])
        sig = "p<0.05 [sig]" if p_one < 0.05 else f"p={p_one:.3f} [n.s.]"
        print(f"  H({BASELINE_LABELS[bk_a].replace(chr(10),' ')}) - H({BASELINE_LABELS[bk_b].replace(chr(10),' ')}) "
              f"on ITB-LQ: Delta={diffs.mean():+.4f}  95%CI [{ci[0]:.4f}, {ci[1]:.4f}]  {sig}")

    # Significance: AUC on ITB-LQ (Q-VIB > Std VIB)
    print("\n── Bootstrap significance (AUC, ITB-LQ) ──")
    from sklearn.metrics import roc_auc_score
    for bk_a, bk_b in [("F", "D"), ("F", "A")]:
        a = lq[lq["baseline"] == bk_a]
        b = lq[lq["baseline"] == bk_b]
        if len(b) == 0:
            continue
        diffs = []
        for _ in range(5000):
            s = rng.integers(0, len(a), size=len(a))
            ta, pa = a["target"].values[s], a["prob_pos"].values[s]
            tb, pb = b["target"].values[s], b["prob_pos"].values[s]
            try:
                diffs.append(roc_auc_score(ta, pa) - roc_auc_score(tb, pb))
            except Exception:
                pass
        diffs = np.array(diffs)
        p_one = float((diffs <= 0).mean())
        ci = np.percentile(diffs, [2.5, 97.5])
        sig = "p<0.05 [sig]" if p_one < 0.05 else f"p={p_one:.3f} [n.s.]"
        print(f"  AUC({BASELINE_LABELS[bk_a].replace(chr(10),' ')}) - AUC({BASELINE_LABELS[bk_b].replace(chr(10),' ')}) "
              f"on ITB-LQ: Delta={diffs.mean():+.4f}  95%CI [{ci[0]:.4f}, {ci[1]:.4f}]  {sig}")

    # Significance: Entropy on ITB-HQ (Q-VIB < Std VIB, one-sided: H_F < H_D)
    print("\n── Bootstrap significance (Mean Entropy, ITB-HQ, Q-VIB should be LOWER) ──")
    hq = preds[preds["subset"] == "ITB-HQ"]
    for bk_a, bk_b in [("D", "F"), ("D", "E")]:
        a = hq[hq["baseline"] == bk_a]["prob_pos"].values
        b = hq[hq["baseline"] == bk_b]["prob_pos"].values
        diffs = []
        for _ in range(5000):
            s = rng.integers(0, len(a), size=len(a))
            def ent2(pp):
                p2 = np.stack([1-pp, pp], axis=1).clip(1e-9)
                return float(-(p2 * np.log(p2)).sum(-1).mean())
            diffs.append(ent2(a[s]) - ent2(b[s]))
        diffs = np.array(diffs)
        p_one = float((diffs <= 0).mean())
        ci = np.percentile(diffs, [2.5, 97.5])
        sig = "p<0.05 [sig]" if p_one < 0.05 else f"p={p_one:.3f} [n.s.]"
        lname_a = BASELINE_LABELS[bk_a].replace(chr(10),' ')
        lname_b = BASELINE_LABELS[bk_b].replace(chr(10),' ')
        print(f"  H({lname_a}) - H({lname_b}) on ITB-HQ: Delta={diffs.mean():+.4f}  95%CI [{ci[0]:.4f}, {ci[1]:.4f}]  {sig}")


def main():
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading predictions...")
    preds = load_predictions()
    df    = recompute_summary(preds)
    print(f"  {len(preds)} per-sample rows | baselines: {preds['baseline'].unique().tolist()}")
    print()
    print(df[["baseline_name","subset","auc","ece","brier","mean_entropy"]].to_string(index=False))

    print("\nGenerating figures...")
    fig_comparison_bars(df)
    fig_calibration(preds)
    fig_entropy_qbar(preds)
    fig_entropy_kde(preds)
    fig_kl_sigma(preds)

    # Agent turns (optional — only if CSV exists)
    agent_csv = Path(AGENT_CSV)
    if agent_csv.exists():
        agent_df = pd.read_csv(agent_csv)
        fig_agent_turns(agent_df)
    else:
        print(f"  [skip] {AGENT_CSV} not found — run run_agent_itb.py first")

    save_ablation_and_stats(df, preds)
    print("\nDone. All figures in results/figures/")


if __name__ == "__main__":
    main()
