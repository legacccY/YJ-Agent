"""分析跨数据集 zero-shot 结果，生成论文图表。

输入：
  results/external_ham10000_predictions.csv
  results/external_pad_ufes_predictions.csv

输出：
  results/external_ablation.csv         — 全量指标表
  results/figures/fig9_cross_dataset.png — 4-panel 论文图

Proposition 2 验证：F 的 entropy 应随 q_bar 单调递减（Spearman ρ < -0.1, p<0.05）

Usage:
  cd D:/YJ-Agent/project
  python analyze_external.py
"""

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.metrics import roc_auc_score

sys.path.insert(0, str(Path(__file__).parent))
from benchmark.metrics import compute_binary_ece, compute_qbar_ece

PROJECT_DIR = Path(__file__).parent
RESULTS_DIR = PROJECT_DIR / "results"
FIG_DIR     = RESULTS_DIR / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

PRED_FILES = {
    "HAM10000":  RESULTS_DIR / "external_ham10000_predictions.csv",
    "PAD-UFES":  RESULTS_DIR / "external_pad_ufes_predictions.csv",
}

BASELINE_DISPLAY = {
    "A":  "B3 Direct",
    "D":  "Std VIB",
    "E":  "Adap. Prior",
    "F":  "Q-VIB Full\n(Ours)",
    "G":  "Q-VIB+TokFT",
    "TS": "VIB+TS",
    "H":  "Focal+LS",
}

BASELINE_COLOR = {
    "A":  "#1f77b4",
    "D":  "#ff7f0e",
    "E":  "#2ca02c",
    "F":  "#d62728",
    "G":  "#9467bd",
    "TS": "#8c564b",
    "H":  "#e377c2",
}

N_BOOTSTRAP = 5000


# ── Helpers ────────────────────────────────────────────────────────────────────

def bootstrap_auc_ci(probs, targets, n=5000, seed=42):
    rng = np.random.default_rng(seed)
    aucs = []
    for _ in range(n):
        idx = rng.integers(0, len(targets), size=len(targets))
        t = targets[idx]; p = probs[idx]
        if t.sum() == 0 or t.sum() == len(t):
            continue
        aucs.append(roc_auc_score(t, p))
    aucs = np.array(aucs)
    return float(aucs.mean()), float(np.percentile(aucs, 2.5)), float(np.percentile(aucs, 97.5))


def bootstrap_auc_pval(probs_f, probs_d, targets, n=5000, seed=42):
    """Bootstrap two-sided p-value for AUC(F) > AUC(D)."""
    rng = np.random.default_rng(seed)
    delta_obs = roc_auc_score(targets, probs_f) - roc_auc_score(targets, probs_d)
    deltas = []
    for _ in range(n):
        idx = rng.integers(0, len(targets), size=len(targets))
        t = targets[idx]; pf = probs_f[idx]; pd_ = probs_d[idx]
        if t.sum() == 0 or t.sum() == len(t):
            continue
        deltas.append(roc_auc_score(t, pf) - roc_auc_score(t, pd_))
    deltas = np.array(deltas)
    p = float(np.mean(deltas <= 0))  # one-sided: P(delta <= 0 | H1: F > D)
    return delta_obs, p


def entropy_from_probs(prob_pos: np.ndarray) -> np.ndarray:
    p = np.stack([1 - prob_pos, prob_pos], axis=1).clip(1e-9)
    return -(p * np.log(p)).sum(axis=1)


def compute_metrics(sub: pd.DataFrame) -> dict:
    probs   = sub["prob_pos"].values
    targets = sub["target"].values
    q_bar   = sub["q_bar"].values
    ent     = entropy_from_probs(probs)

    auc = (float(roc_auc_score(targets, probs))
           if targets.sum() > 0 and targets.sum() < len(targets) else float("nan"))
    ece = compute_binary_ece(probs, targets)
    auc_mean, auc_lo, auc_hi = bootstrap_auc_ci(probs, targets)

    # q_bar bins (5 bins) — entropy vs q_bar
    segments = compute_qbar_ece(probs, targets, q_bar, n_bins=5)
    ent_qbar = [(s["q_mean"], s["entropy_mean"]) for s in segments]

    # Spearman ρ: entropy ~ q_bar
    rho, p_rho = stats.spearmanr(q_bar, ent)

    return {
        "auc": auc, "auc_lo": auc_lo, "auc_hi": auc_hi,
        "ece": ece, "mean_entropy": float(ent.mean()),
        "n": len(targets), "n_pos": int(targets.sum()),
        "spearman_rho": float(rho), "spearman_p": float(p_rho),
        "ent_qbar": ent_qbar,
        "segments": segments,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    all_ablation_rows = []
    dataset_results = {}

    for dname, pred_path in PRED_FILES.items():
        if not pred_path.exists():
            print(f"[SKIP] {pred_path} not found")
            continue

        df = pd.read_csv(pred_path)
        print(f"\n=== {dname}: {len(df)} predictions, {df['baseline'].nunique()} baselines ===")

        dataset_results[dname] = {}
        baselines = sorted(df["baseline"].unique())

        for bl in baselines:
            sub = df[df["baseline"] == bl].reset_index(drop=True)
            m = compute_metrics(sub)
            dataset_results[dname][bl] = m
            all_ablation_rows.append({
                "dataset":     dname,
                "baseline":    bl,
                "baseline_name": BASELINE_DISPLAY.get(bl, bl),
                "n":           m["n"],
                "n_pos":       m["n_pos"],
                "auc":         round(m["auc"], 4),
                "auc_lo":      round(m["auc_lo"], 4),
                "auc_hi":      round(m["auc_hi"], 4),
                "ece":         round(m["ece"], 4),
                "mean_entropy": round(m["mean_entropy"], 4),
                "spearman_rho": round(m["spearman_rho"], 4),
                "spearman_p":   m["spearman_p"],
            })
            auc_str = f"{m['auc']:.3f} [{m['auc_lo']:.3f}-{m['auc_hi']:.3f}]"
            print(f"  [{bl}] {BASELINE_DISPLAY.get(bl,''):20s}  "
                  f"AUC={auc_str}  ECE={m['ece']:.3f}  "
                  f"H={m['mean_entropy']:.3f}  ρ={m['spearman_rho']:+.3f}(p={m['spearman_p']:.3f})")

        # F vs D bootstrap
        if "F" in dataset_results[dname] and "D" in dataset_results[dname]:
            sub_f = df[df["baseline"] == "F"].reset_index(drop=True)
            sub_d = df[df["baseline"] == "D"].reset_index(drop=True)
            # Align by image_id
            merged = sub_f.merge(sub_d, on="image_id", suffixes=("_F", "_D"))
            if len(merged) > 10:
                delta, p = bootstrap_auc_pval(
                    merged["prob_pos_F"].values,
                    merged["prob_pos_D"].values,
                    merged["target_F"].values,
                )
                print(f"\n  F vs D bootstrap ({dname}): ΔAUC={delta:+.4f}  p={p:.4f}")

    # Save ablation table
    abl_df = pd.DataFrame(all_ablation_rows)
    out_csv = RESULTS_DIR / "external_ablation.csv"
    abl_df.to_csv(out_csv, index=False)
    print(f"\nAblation -> {out_csv}")

    # ── Figure 9: 4-panel cross-dataset ────────────────────────────────────────
    datasets_ordered = [d for d in ["HAM10000", "PAD-UFES"] if d in dataset_results]
    if len(datasets_ordered) == 0:
        print("No data to plot."); return

    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    fig.suptitle("Cross-Dataset Zero-Shot Validation", fontsize=14, fontweight="bold", y=0.98)

    for col_idx, dname in enumerate(datasets_ordered):
        res = dataset_results[dname]
        bl_keys = [k for k in ["A", "D", "E", "F", "G", "TS", "H"] if k in res]

        # ── Panel (row=0): AUC bar chart ────────────────────────────────────
        ax_auc = axes[0, col_idx]
        aucs    = [res[k]["auc"]    for k in bl_keys]
        auc_lo  = [res[k]["auc_lo"] for k in bl_keys]
        auc_hi  = [res[k]["auc_hi"] for k in bl_keys]
        yerr_lo = [a - lo for a, lo in zip(aucs, auc_lo)]
        yerr_hi = [hi - a for a, hi in zip(aucs, auc_hi)]
        colors  = [BASELINE_COLOR.get(k, "#888888") for k in bl_keys]
        labels  = [BASELINE_DISPLAY.get(k, k) for k in bl_keys]
        x = np.arange(len(bl_keys))

        bars = ax_auc.bar(x, aucs, color=colors, alpha=0.85, edgecolor="black", linewidth=0.5)
        ax_auc.errorbar(x, aucs, yerr=[yerr_lo, yerr_hi], fmt="none",
                        color="black", capsize=4, linewidth=1.2)

        # Highlight F
        f_idx = bl_keys.index("F") if "F" in bl_keys else None
        if f_idx is not None:
            bars[f_idx].set_edgecolor("#8B0000")
            bars[f_idx].set_linewidth(2.0)

        ax_auc.set_xticks(x)
        ax_auc.set_xticklabels(labels, rotation=30, ha="right", fontsize=8)
        ax_auc.set_ylabel("AUC-ROC" if col_idx == 0 else "")
        ax_auc.set_title(f"(a) {dname}: AUC" if col_idx == 0 else f"(c) {dname}: AUC", fontweight="bold")
        ax_auc.set_ylim(0.4, 1.0)
        ax_auc.axhline(0.5, color="gray", linestyle="--", linewidth=0.8)
        ax_auc.grid(axis="y", alpha=0.3)
        ax_auc.spines[["top", "right"]].set_visible(False)

        # ── Panel (row=1): Entropy vs q_bar (Proposition 2) ─────────────────
        ax_ent = axes[1, col_idx]

        for k in ["D", "F"]:
            if k not in res:
                continue
            ent_qbar = res[k]["ent_qbar"]
            if len(ent_qbar) == 0:
                continue
            qs = [x[0] for x in ent_qbar]
            es = [x[1] for x in ent_qbar]
            color = BASELINE_COLOR.get(k, "#888")
            label = BASELINE_DISPLAY.get(k, k).replace("\n", " ")
            rho   = res[k]["spearman_rho"]
            p_rho = res[k]["spearman_p"]
            ax_ent.plot(qs, es, "o-", color=color, linewidth=2, markersize=6,
                        label=f"{label} (ρ={rho:+.2f}, p={p_rho:.3f})")

        ax_ent.set_xlabel("Quality Score q̄")
        ax_ent.set_ylabel("Mean Predictive Entropy" if col_idx == 0 else "")
        panel_label = "b" if col_idx == 0 else "d"
        ax_ent.set_title(f"({panel_label}) {dname}: Entropy vs q̄ [Prop.2]", fontweight="bold")
        ax_ent.legend(fontsize=8)
        ax_ent.grid(alpha=0.3)
        ax_ent.spines[["top", "right"]].set_visible(False)

    plt.tight_layout(rect=[0, 0, 1, 0.97])
    out_fig = FIG_DIR / "fig9_cross_dataset.png"
    plt.savefig(out_fig, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Figure -> {out_fig}")

    # ── Proposition 2 pass/fail report ────────────────────────────────────────
    print("\n=== Proposition 2 Verification ===")
    for dname in datasets_ordered:
        if "F" not in dataset_results[dname]:
            continue
        m_f = dataset_results[dname]["F"]
        rho = m_f["spearman_rho"]
        p   = m_f["spearman_p"]
        ok  = rho < -0.1 and p < 0.05
        print(f"  {dname}: F entropy~q_bar  rho={rho:+.4f}  p={p:.4f}  {'PASS' if ok else 'FAIL'}")

    # ── F vs D AUC significance ────────────────────────────────────────────────
    print("\n=== F vs D AUC Bootstrap ===")
    for dname, pred_path in PRED_FILES.items():
        if not pred_path.exists():
            continue
        df = pd.read_csv(pred_path)
        if "F" not in df["baseline"].unique() or "D" not in df["baseline"].unique():
            continue
        sub_f = df[df["baseline"] == "F"].reset_index(drop=True)
        sub_d = df[df["baseline"] == "D"].reset_index(drop=True)
        merged = sub_f.merge(sub_d, on="image_id", suffixes=("_F", "_D"))
        if len(merged) < 10:
            print(f"  {dname}: not enough paired samples")
            continue
        delta, p = bootstrap_auc_pval(
            merged["prob_pos_F"].values,
            merged["prob_pos_D"].values,
            merged["target_F"].values,
        )
        sig = "PASS p<0.05" if p < 0.05 else ("MARGINAL p<0.10" if p < 0.10 else "FAIL n.s.")
        print(f"  {dname}: ΔAUC(F-D)={delta:+.4f}  p={p:.4f}  {sig}")

    # ── Acceptance criteria ────────────────────────────────────────────────────
    print("\n=== Sprint 2.1 Acceptance Criteria ===")
    criteria_pass = 0

    # 1. HAM10000 F vs D AUC p<0.05
    if "HAM10000" in PRED_FILES and PRED_FILES["HAM10000"].exists():
        df = pd.read_csv(PRED_FILES["HAM10000"])
        if "F" in df["baseline"].unique() and "D" in df["baseline"].unique():
            sf = df[df["baseline"]=="F"]; sd = df[df["baseline"]=="D"]
            m = sf.merge(sd, on="image_id", suffixes=("_F","_D"))
            if len(m) > 10:
                delta, p = bootstrap_auc_pval(m["prob_pos_F"].values, m["prob_pos_D"].values, m["target_F"].values)
                ok = p < 0.05
                print(f"  [1] HAM10000 F vs D AUC p<0.05: {'PASS' if ok else 'FAIL'} (p={p:.4f})")
                criteria_pass += int(ok)

    # 2. PAD-UFES Proposition 2 (Spearman ρ<-0.1, p<0.05)
    if "PAD-UFES" in dataset_results and "F" in dataset_results["PAD-UFES"]:
        m_f = dataset_results["PAD-UFES"]["F"]
        ok = m_f["spearman_rho"] < -0.1 and m_f["spearman_p"] < 0.05
        print(f"  [2] PAD-UFES Prop.2 (ρ<-0.1, p<0.05): {'PASS' if ok else 'FAIL'} "
              f"(ρ={m_f['spearman_rho']:+.4f}, p={m_f['spearman_p']:.4f})")
        criteria_pass += int(ok)

    # 3. F ECE in LQ bin (q_bar<0.45) < TS ECE
    for dname in datasets_ordered:
        if "F" not in dataset_results[dname] or "TS" not in dataset_results[dname]:
            continue
        segs_f  = dataset_results[dname]["F"]["segments"]
        segs_ts = dataset_results[dname]["TS"]["segments"]
        lq_f  = [s["ece"] for s in segs_f  if s["q_hi"] <= 0.45]
        lq_ts = [s["ece"] for s in segs_ts if s["q_hi"] <= 0.45]
        if lq_f and lq_ts:
            ok = np.mean(lq_f) < np.mean(lq_ts)
            print(f"  [3] {dname} LQ ECE F({np.mean(lq_f):.3f}) < TS({np.mean(lq_ts):.3f}): {'PASS' if ok else 'FAIL'}")
            criteria_pass += int(ok)

    print(f"\n  Total criteria passed: {criteria_pass}/3+ {'Sprint 2.1 PASS' if criteria_pass >= 1 else 'Sprint 2.1 FAIL - Report numbers as-is'}")


if __name__ == "__main__":
    main()
