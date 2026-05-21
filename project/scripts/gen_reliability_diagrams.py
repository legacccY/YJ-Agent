"""C4: Per-stratum reliability diagrams for main paper / supp.

4 methods: Std VIB (D) / Std VIB+TS / Std VIB+QCTS / MC Dropout (I)
2 strata:  ITB-LQ, ITB-HQ
Output:    figures/fig_reliability.{pdf,svg,png}
"""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path("D:/YJ-Agent/project")
OUT_FIG = ROOT / "meeting/BMVC/figures"

N_BINS = 10


def bin_reliability(probs, targets, n_bins=N_BINS):
    bins = np.linspace(0, 1, n_bins + 1)
    accs, confs, counts = [], [], []
    for lo, hi in zip(bins[:-1], bins[1:]):
        m = (probs >= lo) & (probs < hi)
        if m.sum() < 1:
            accs.append(np.nan); confs.append((lo + hi) / 2); counts.append(0)
            continue
        accs.append(float(targets[m].mean()))
        confs.append(float(probs[m].mean()))
        counts.append(int(m.sum()))
    return np.array(confs), np.array(accs), np.array(counts)


def main():
    preds = pd.read_csv(ROOT / "results/itb_predictions.csv")
    qcts = pd.read_csv(ROOT / "results/qcts_itb_predictions.csv")
    qcts["baseline"] = "D+QCTS"
    all_preds = pd.concat([preds, qcts], ignore_index=True)

    methods = [
        ("D",      "Std VIB",      "#1f77b4"),
        ("TS",     "Std VIB + TS", "#ff7f0e"),
        ("D+QCTS", "Std VIB + QCTS", "#2ca02c"),
        ("I",      "MC Dropout",   "#d62728"),
    ]
    subsets = [("ITB-LQ", "LQ"), ("ITB-HQ", "HQ")]

    fig, axes = plt.subplots(1, 2, figsize=(7.6, 3.4), sharey=True)

    for ax, (subset, label) in zip(axes, subsets):
        ax.plot([0, 1], [0, 1], "k--", lw=1, alpha=0.5, label="Perfectly calibrated")
        for bl, name, color in methods:
            sub = all_preds[(all_preds.baseline == bl) & (all_preds.subset == subset)]
            if len(sub) < 10:
                continue
            confs, accs, counts = bin_reliability(sub["prob_pos"].values,
                                                  sub["target"].values.astype(float))
            valid = ~np.isnan(accs) & (counts >= 3)
            sizes = 8 + (counts[valid] / counts[valid].max()) * 60 if valid.sum() else 8
            ax.plot(confs[valid], accs[valid], "-", color=color, lw=1.4, alpha=0.85, label=name)
            ax.scatter(confs[valid], accs[valid], s=sizes, color=color, alpha=0.85,
                       edgecolor="white", linewidth=0.5, zorder=3)

        ax.set_xlim(0, 1); ax.set_ylim(0, 1)
        ax.set_xlabel("Confidence (predicted prob.)", fontsize=8)
        ax.set_title(f"ITB-{label} ($n{{=}}{len(sub) if len(sub) else '?'}$)", fontsize=9)
        ax.tick_params(labelsize=7)
        ax.grid(True, alpha=0.3, lw=0.4)

    axes[0].set_ylabel("Accuracy (empirical)", fontsize=8)
    axes[1].legend(fontsize=6.5, loc="upper left", framealpha=0.9)

    plt.tight_layout()
    for fmt in ["pdf", "svg", "png"]:
        fig.savefig(OUT_FIG / f"fig_reliability.{fmt}",
                    dpi=200 if fmt == "png" else None,
                    bbox_inches="tight", format=fmt)
    print(f"Saved → {OUT_FIG}/fig_reliability.{{pdf,svg,png}}")


if __name__ == "__main__":
    main()
