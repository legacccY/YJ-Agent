"""Generate fig7: QCTS quality-awareness on ImageNet-C corruptions.

Two-panel scatter: raw_rho vs qcts_rho per corruption (averaged over severities),
for ResNet-50 and ViT-Tiny. Points below y=x show QCTS improvement.

Output: figures/fig7_imagenetc_qcts.{pdf,svg,png}
"""
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from pathlib import Path

ROOT = Path("D:/YJ-Agent/project")
OUT = ROOT / "meeting/BMVC/figures"
OUT.mkdir(exist_ok=True)

CORRUPTION_LABELS = {
    "gaussian_noise": "Gauss. noise",
    "shot_noise": "Shot noise",
    "impulse_noise": "Impulse noise",
    "defocus_blur": "Defocus blur",
    "glass_blur": "Glass blur",
    "motion_blur": "Motion blur",
    "zoom_blur": "Zoom blur",
    "snow": "Snow",
    "frost": "Frost",
    "fog": "Fog",
    "brightness": "Brightness",
    "contrast": "Contrast",
    "elastic_transform": "Elastic",
    "pixelate": "Pixelate",
    "jpeg_compression": "JPEG",
    "gaussian_blur": "Gauss. blur",
    "spatter": "Spatter",
    "saturate": "Saturate",
}

BACKBONES = {
    "resnet50": "ResNet-50",
    "vit_tiny": "ViT-Tiny",
}

fig, axes = plt.subplots(1, 2, figsize=(8, 3.8))

for ax, (bb_key, bb_label) in zip(axes, BACKBONES.items()):
    df = pd.read_csv(ROOT / f"results/backbones/{bb_key}/corruption_robustness_itb-lq.csv")
    df = df[df["corruption"] != "clean"]

    # Average over severities
    agg = df.groupby("corruption")[["raw_rho", "ts_rho", "qcts_rho"]].mean().reset_index()

    x = agg["raw_rho"].values
    y = agg["qcts_rho"].values
    labels = [CORRUPTION_LABELS.get(c, c) for c in agg["corruption"].values]

    # Color by improvement
    improved = y < x
    ax.scatter(x[improved], y[improved], c="#2196F3", s=55, zorder=3,
               label=f"QCTS↑ ({improved.sum()}/{len(x)})")
    ax.scatter(x[~improved], y[~improved], c="#FF7043", s=55, marker="^", zorder=3,
               label=f"QCTS↓ ({(~improved).sum()}/{len(x)})")

    # Diagonal reference (y=x)
    lims = [min(x.min(), y.min()) - 0.02, max(x.max(), y.max()) + 0.02]
    ax.plot(lims, lims, "k--", lw=0.9, alpha=0.5, zorder=1)
    ax.fill_between(lims, lims[0], lims, color="#2196F3", alpha=0.05)

    # Annotate notable points
    for xi, yi, lab in zip(x, y, labels):
        delta = yi - xi
        if abs(delta) > 0.04:  # only label big improvements or regressions
            ax.annotate(lab, (xi, yi), fontsize=5.5, ha="center", va="bottom",
                        xytext=(0, 3), textcoords="offset points",
                        color="#2196F3" if yi < xi else "#FF7043")

    ax.set_xlabel(r"$\rho(H,\bar q)$ — raw", fontsize=9)
    ax.set_ylabel(r"$\rho(H,\bar q)$ — QCTS", fontsize=9)
    ax.set_title(bb_label, fontsize=10, fontweight="bold")
    ax.set_xlim(lims); ax.set_ylim(lims)
    ax.legend(fontsize=7.5, loc="upper left", framealpha=0.85)
    ax.axhline(0, color="gray", lw=0.5, alpha=0.4)
    ax.axvline(0, color="gray", lw=0.5, alpha=0.4)
    ax.tick_params(labelsize=8)

    # Text annotation: QCTS improvement
    n_better = improved.sum()
    ax.text(0.97, 0.04,
            f"QCTS improves\n{n_better}/{len(x)} corruptions",
            transform=ax.transAxes, ha="right", va="bottom",
            fontsize=7.5, color="#1565C0",
            bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="#2196F3", lw=0.7))

axes[0].set_title("(a) ResNet-50", fontsize=10, fontweight="bold")
axes[1].set_title("(b) ViT-Tiny", fontsize=10, fontweight="bold")

fig.suptitle(
    r"QCTS improves $\rho(H,\bar q)$ on ImageNet-C corruptions"
    "\n(points below diagonal = more quality-aware after QCTS)",
    fontsize=9, y=1.02
)

plt.tight_layout()
for fmt in ["pdf", "svg", "png"]:
    out_path = OUT / f"fig7_imagenetc_qcts.{fmt}"
    fig.savefig(out_path, dpi=200 if fmt == "png" else None,
                bbox_inches="tight", format=fmt)
    print(f"[saved] {out_path}")

plt.close()
print("\nDone.")
