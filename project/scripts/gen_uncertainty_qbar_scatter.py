"""W3: MC Dropout + Deep Ensemble uncertainty vs q̄ scatter + bootstrap Spearman ρ.

Uses existing itb_predictions.csv (no re-inference needed).
Uncertainty proxy = binary entropy H(p) of mean prediction.

Output:
    results/uncertainty_rho_bootstrap.csv
    figures/fig_uncertainty_qbar.{pdf,svg,png}

Usage:
    python project/scripts/gen_uncertainty_qbar_scatter.py
"""
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path
from scipy.stats import spearmanr

ROOT = Path("D:/YJ-Agent/project")
OUT = ROOT / "meeting/BMVC/figures"
OUT.mkdir(exist_ok=True)

METHODS = {
    "I":     ("MC Dropout",     "#e377c2"),
    "J":     ("Deep Ensemble",  "#bcbd22"),
    "D":     ("Std VIB",        "#1f77b4"),
    "D+QCTS": ("Std VIB + QCTS", "#2ca02c"),
}


def binary_entropy(p):
    p = np.clip(p, 1e-7, 1 - 1e-7)
    return -(p * np.log(p) + (1 - p) * np.log(1 - p))


def bootstrap_rho(h, q, n_boots=2000, seed=42):
    rng = np.random.default_rng(seed)
    rhos = []
    for _ in range(n_boots):
        idx = rng.integers(0, len(h), len(h))
        r, _ = spearmanr(h[idx], q[idx])
        rhos.append(r)
    return np.array(rhos)


def main():
    df = pd.read_csv(ROOT / "results/itb_predictions.csv")
    qcts_path = ROOT / "results/qcts_itb_predictions.csv"
    if qcts_path.exists():
        qcts_df = pd.read_csv(qcts_path)
        qcts_df["baseline"] = "D+QCTS"
        df = pd.concat([df, qcts_df], ignore_index=True)

    df["entropy"] = binary_entropy(df["prob_pos"].values)

    # ITB-LQ only (quality-aware calibration analysis)
    lq = df[df["subset"] == "ITB-LQ"].copy()

    fig, axes = plt.subplots(1, 2, figsize=(9, 3.8))

    results = []
    for (bl, (name, color)), ax in zip(METHODS.items(), [axes[0], axes[0], axes[1], axes[1]]):
        sub = lq[lq["baseline"] == bl]
        if len(sub) < 10:
            continue
        h = sub["entropy"].values
        q = sub["qbar"].values

        rho_obs, p_obs = spearmanr(h, q)
        boots = bootstrap_rho(h, q)
        ci_lo, ci_hi = np.percentile(boots, [2.5, 97.5])

        results.append({
            "method": name, "baseline": bl,
            "rho": round(float(rho_obs), 4),
            "rho_ci_lo": round(float(ci_lo), 4),
            "rho_ci_hi": round(float(ci_hi), 4),
            "p_obs": float(p_obs),
            "n": len(sub),
        })
        print(f"  {name}: rho={rho_obs:.3f} [{ci_lo:.3f},{ci_hi:.3f}] p={p_obs:.4e} n={len(sub)}")

    # Plot panel 1: MC Dropout + Deep Ensemble scatter
    ax = axes[0]
    for bl, (name, color) in [("I", METHODS["I"]), ("J", METHODS["J"])]:
        sub = lq[lq["baseline"] == bl]
        if len(sub) < 10:
            continue
        h = sub["entropy"].values
        q = sub["qbar"].values
        rho_obs, _ = spearmanr(h, q)
        boots = bootstrap_rho(h, q)
        ci_lo, ci_hi = np.percentile(boots, [2.5, 97.5])

        # Hexbin scatter
        hb = ax.hexbin(q, h, gridsize=20, cmap="Blues" if bl == "I" else "YlOrRd",
                       alpha=0.6, mincnt=1, linewidths=0.2)
        # ρ annotation
        ax.text(0.05 if bl == "I" else 0.55, 0.92 if bl == "I" else 0.80,
                f"{name}\n$\\rho={rho_obs:.3f}$ [{ci_lo:.3f},{ci_hi:.3f}]",
                transform=ax.transAxes, fontsize=7.5,
                color=color, bbox=dict(fc="white", ec=color, lw=0.8, alpha=0.9))

    ax.set_xlabel(r"Image quality $\bar q$", fontsize=9)
    ax.set_ylabel(r"Entropy $H(p)$", fontsize=9)
    ax.set_title("(a) MC Dropout & Deep Ensemble\nentropy vs quality (ITB-LQ)", fontsize=8.5, fontweight="bold")
    ax.tick_params(labelsize=8)

    # Plot panel 2: ρ comparison bar chart with CI
    ax = axes[1]
    names = [r["method"] for r in results]
    rhos = [r["rho"] for r in results]
    ci_los = [r["rho_ci_lo"] for r in results]
    ci_his = [r["rho_ci_hi"] for r in results]
    colors = [METHODS[r["baseline"]][1] for r in results]

    x = np.arange(len(names))
    bars = ax.bar(x, rhos, color=colors, width=0.6, zorder=3, alpha=0.85)
    for i, (lo, hi, rho_v) in enumerate(zip(ci_los, ci_his, rhos)):
        ax.plot([x[i], x[i]], [lo, hi], "k-", lw=2, zorder=4)
        ax.plot([x[i]-0.1, x[i]+0.1], [lo, lo], "k-", lw=1.5, zorder=4)
        ax.plot([x[i]-0.1, x[i]+0.1], [hi, hi], "k-", lw=1.5, zorder=4)
        ax.text(x[i], rho_v - 0.01 if rho_v < 0 else rho_v + 0.01,
                f"{rho_v:.3f}", ha="center", va="top" if rho_v < 0 else "bottom",
                fontsize=7, fontweight="bold", color="white" if abs(rho_v) > 0.05 else "black")

    ax.axhline(0, color="k", lw=0.8, alpha=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels(names, fontsize=8, rotation=15, ha="right")
    ax.set_ylabel(r"Spearman $\rho(H, \bar q)$ on ITB-LQ", fontsize=9)
    ax.set_title("(b) Quality-awareness comparison\n(bootstrap 95% CI, n=300)", fontsize=8.5, fontweight="bold")
    ax.set_ylim(min(rhos + ci_los) - 0.05, max(rhos + ci_his) + 0.08)
    ax.tick_params(labelsize=8)

    # Annotation: "more quality-aware = more negative ρ"
    ax.text(0.98, 0.95, "more quality-aware →\n(more negative ρ)",
            transform=ax.transAxes, ha="right", va="top", fontsize=7.5,
            color="gray", style="italic")

    plt.tight_layout()
    for fmt in ["pdf", "svg", "png"]:
        fig.savefig(OUT / f"fig_uncertainty_qbar.{fmt}",
                    dpi=200 if fmt == "png" else None, bbox_inches="tight", format=fmt)
    plt.close()
    print(f"Figures: {OUT}/fig_uncertainty_qbar.*")

    # Save results CSV
    df_res = pd.DataFrame(results)
    df_res.to_csv(ROOT / "results/uncertainty_rho_bootstrap.csv", index=False)
    print(f"CSV: {ROOT}/results/uncertainty_rho_bootstrap.csv")


if __name__ == "__main__":
    main()
