"""
plot_iclr_e2_perdim.py
-----------------------
ICLR 2027 VisiSkin-Agent  E2 各退化维度 × 严重度指标曲线

CSV 来源: results/e2_perdim.csv
读取列: axis, psnr_deg, psnr_enh, ssim_enh, n

e2_perdim 结构: 4 个 axis (brightness/color_shift/contrast/blur) × 1行
(每个 axis 一行, 代表单退化维度的聚合结果)

关键值:
  brightness:   psnr_deg=13.70 → psnr_enh=37.68, ssim_enh=0.9871
  color_shift:  psnr_deg=25.83 → psnr_enh=33.77, ssim_enh=0.9886
  contrast:     psnr_deg=32.29 → psnr_enh=29.11, ssim_enh=0.9703
  blur:         psnr_deg=36.67 → psnr_enh=35.82, ssim_enh=0.9216

画了什么:
  双子图:
    (a) PSNR改善 (psnr_enh - psnr_deg) 按退化维度柱状
    (b) 增强后 SSIM 按维度柱状
  颜色区分维度; 虚线显示 psnr_deg 原始值 (第二 y 轴参考)

Usage:
    python plot_iclr_e2_perdim.py [--out DIR]
"""

import argparse
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# ---------- CLI ----------
parser = argparse.ArgumentParser()
parser.add_argument("--out", default="D:/YJ-Agent/project/report/figures")
args = parser.parse_args()
os.makedirs(args.out, exist_ok=True)

CSV_PATH = "D:/YJ-Agent/project/results/e2_perdim.csv"
df = pd.read_csv(CSV_PATH)
print(f"[READ] {CSV_PATH}: {df.shape}, axes={df['axis'].tolist()}")

for _, row in df.iterrows():
    delta = row["psnr_enh"] - row["psnr_deg"]
    print(f"[CHECK] axis={row['axis']}: psnr_deg={row['psnr_deg']:.3f}, "
          f"psnr_enh={row['psnr_enh']:.3f}, delta={delta:.3f}, ssim_enh={row['ssim_enh']:.4f}")

AXIS_LABELS = {
    "brightness": "Brightness",
    "color_shift": "Color Shift",
    "contrast": "Contrast",
    "blur": "Blur",
}

axes_list = df["axis"].tolist()
labels = [AXIS_LABELS.get(a, a) for a in axes_list]
psnr_deg = df["psnr_deg"].values
psnr_enh = df["psnr_enh"].values
ssim_enh = df["ssim_enh"].values
delta_psnr = psnr_enh - psnr_deg

x = np.arange(len(axes_list))
# colorblind-safe
COLORS = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.5, 4.5))

# (a) PSNR improvement — one label per bar, sign from csv delta directly
bars = ax1.bar(x, delta_psnr, color=COLORS, alpha=0.85, width=0.55)
for bar, val in zip(bars, delta_psnr):
    # signed label: positive above bar, negative below bar
    if val >= 0:
        label_y = bar.get_height() + 0.2
        va = "bottom"
    else:
        label_y = val - 0.5
        va = "top"
    signed = f"+{val:.1f}" if val >= 0 else f"{val:.1f}"
    col = "#d62728" if val < 0 else "black"
    ax1.text(bar.get_x() + bar.get_width() / 2, label_y,
             signed, ha="center", va=va, fontsize=9, fontweight="bold", color=col)

ax1.axhline(0, color="gray", linewidth=0.8)
ax1.set_xticks(x)
ax1.set_xticklabels(labels, fontsize=9.5)
ax1.set_ylabel("PSNR Improvement (dB)\npsnr_enh − psnr_deg", fontsize=9)
ax1.tick_params(labelsize=9)
ax1.set_title("(a) Enhancement PSNR Gain by Degradation Axis", fontsize=9, pad=4)

# add degraded PSNR reference (secondary axis)
ax1b = ax1.twinx()
ax1b.plot(x, psnr_deg, "o--", color="dimgray", markersize=6, linewidth=1.2,
          label="PSNRₐ (degraded)", alpha=0.6)
ax1b.set_ylabel("PSNR (degraded input, dB)", fontsize=8, color="dimgray")
ax1b.tick_params(labelsize=8, colors="dimgray")
ax1b.legend(fontsize=8, loc="upper right")

# (b) SSIM enhanced
bars2 = ax2.bar(x, ssim_enh, color=COLORS, alpha=0.85, width=0.55)
for bar, val in zip(bars2, ssim_enh):
    ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.002,
             f"{val:.4f}", ha="center", va="bottom", fontsize=8.5)

ax2.set_xticks(x)
ax2.set_xticklabels(labels, fontsize=9.5)
ax2.set_ylabel("SSIM (enhanced)", fontsize=10)
ax2.set_ylim(0.88, 1.00)
ax2.tick_params(labelsize=9)
ax2.set_title("(b) Enhanced SSIM by Degradation Axis", fontsize=9, pad=4)

plt.tight_layout()

for ext in ("pdf", "png"):
    out_path = os.path.join(args.out, f"fig_e2_perdim.{ext}")
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    print(f"[SAVED] {out_path}")

plt.close()
print("[DONE] fig_e2_perdim")
