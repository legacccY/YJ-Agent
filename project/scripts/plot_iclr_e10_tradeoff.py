"""
plot_iclr_e10_tradeoff.py
--------------------------
ICLR 2027 VisiSkin-Agent  E10 fidelity-vs-diagnosis tradeoff scatter

CSV 来源 (results/e10_<model>.csv), 读取列:
  model, psnr_perimg, dAUC, dAUC_ci_lo, dAUC_ci_hi

关键值 (row 1 = VisiEnhance):
  VisiEnhance: psnr=32.79, dAUC=-0.0172
  MIRNet-v2:   psnr=13.48, dAUC=-0.0872
  NAFNet:      psnr=22.04, dAUC=-0.1148
  Real-ESRGAN: psnr=21.61, dAUC=-0.0832
  Restormer:   psnr=22.30, dAUC=-0.0964
  SwinIR:      psnr=21.69, dAUC=-0.1335
  Uformer-B:   psnr=22.28, dAUC=-0.0939

画了什么: x=PSNR, y=ΔAUC, 散点+误差棒 + 象限注释
          VisiEnhance 标星 + 标注框; 其余 baselines 用 colorblind-safe 配色

Usage:
    python plot_iclr_e10_tradeoff.py [--out DIR]
"""

import argparse
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd

# ---------- CLI ----------
parser = argparse.ArgumentParser()
parser.add_argument("--out", default="D:/YJ-Agent/project/report/figures")
args = parser.parse_args()
os.makedirs(args.out, exist_ok=True)

RESULTS_DIR = "D:/YJ-Agent/project/results"

# ---------- 读取数据 ----------
CSV_MAP = {
    "MIRNet-v2":   "e10_mirnetv2.csv",
    "NAFNet":      "e10_nafnet.csv",
    "Real-ESRGAN": "e10_realesrgan.csv",
    "Restormer":   "e10_restormer.csv",
    "SwinIR":      "e10_swinir.csv",
    "Uformer-B":   "e10_uformer.csv",
}

records = []
for label, fname in CSV_MAP.items():
    path = os.path.join(RESULTS_DIR, fname)
    df = pd.read_csv(path)
    # 第2行 (idx 1) = baseline model
    row = df.iloc[1]
    rec = {
        "model": label,
        "psnr": float(row["psnr_perimg"]),
        "dAUC": float(row["dAUC"]),
        "ci_lo": float(row["dAUC_ci_lo"]) if str(row["dAUC_ci_lo"]) not in ("", "nan") else np.nan,
        "ci_hi": float(row["dAUC_ci_hi"]) if str(row["dAUC_ci_hi"]) not in ("", "nan") else np.nan,
    }
    records.append(rec)
    print(f"[READ] {label}: psnr={rec['psnr']}, dAUC={rec['dAUC']}")

# VisiEnhance from first row of any e10 csv (same across all)
df0 = pd.read_csv(os.path.join(RESULTS_DIR, "e10_mirnetv2.csv"))
ve_row = df0.iloc[0]
ve = {
    "model": "VisiEnhance",
    "psnr": float(ve_row["psnr_perimg"]),
    "dAUC": float(ve_row["dAUC"]),
    "ci_lo": float(ve_row["dAUC_ci_lo"]) if str(ve_row["dAUC_ci_lo"]) not in ("", "nan") else np.nan,
    "ci_hi": float(ve_row["dAUC_ci_hi"]) if str(ve_row["dAUC_ci_hi"]) not in ("", "nan") else np.nan,
}
print(f"[READ] VisiEnhance: psnr={ve['psnr']}, dAUC={ve['dAUC']}")

# ---------- 颜色 (colorblind-safe tab10) ----------
COLORS = [
    "#1f77b4", "#ff7f0e", "#2ca02c",
    "#d62728", "#9467bd", "#8c564b",
]

# ---------- 绘图 ----------
fig, ax = plt.subplots(figsize=(6.5, 4.8))

# 象限背景阴影
# 高保真伤诊断: x>28, y<0 → 右下
ax.axhspan(ymin=-0.22, ymax=0, xmin=0, xmax=1, alpha=0.04, color="red")
ax.axhspan(ymin=0, ymax=0.02, xmin=0, xmax=1, alpha=0.04, color="green")
ax.axhline(0, color="gray", linewidth=0.8, linestyle="--", alpha=0.6)

# baselines
for i, rec in enumerate(records):
    yerr_lo = abs(rec["dAUC"] - rec["ci_lo"]) if not np.isnan(rec["ci_lo"]) else 0
    yerr_hi = abs(rec["ci_hi"] - rec["dAUC"]) if not np.isnan(rec["ci_hi"]) else 0
    ax.errorbar(
        rec["psnr"], rec["dAUC"],
        yerr=[[yerr_lo], [yerr_hi]] if (yerr_lo > 0 or yerr_hi > 0) else None,
        fmt="o", color=COLORS[i], markersize=7, capsize=3,
        linewidth=1.2, label=rec["model"],
    )
    # label offset
    ax.annotate(
        rec["model"],
        xy=(rec["psnr"], rec["dAUC"]),
        xytext=(3, 4), textcoords="offset points",
        fontsize=7.5, color=COLORS[i],
    )

# VisiEnhance 星形
ax.plot(ve["psnr"], ve["dAUC"], marker="*", color="#e6194b",
        markersize=14, zorder=5, linestyle="None", label="VisiEnhance")
ax.annotate(
    "VisiEnhance\n(PSNR 32.79, ΔAUC −0.017)",
    xy=(ve["psnr"], ve["dAUC"]),
    xytext=(-90, -22), textcoords="offset points",
    fontsize=8, color="#e6194b",
    arrowprops=dict(arrowstyle="->", color="#e6194b", lw=0.8),
    bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="#e6194b", alpha=0.85),
)

# 象限标注
ax.text(14.0, 0.010, "diagnosis-safe\nzone", fontsize=7.5, color="#2ca02c",
        fontstyle="italic", va="center")
ax.text(14.0, -0.195, "high-fidelity but\ndiagnosis-harmful", fontsize=7.5,
        color="#d62728", fontstyle="italic", va="center")

ax.set_xlabel("Per-image PSNR (dB)", fontsize=10)
ax.set_ylabel("Paired ΔAUC (enhancement − reference)", fontsize=10)
ax.tick_params(labelsize=9)
ax.set_xlim(11, 36)
ax.set_ylim(-0.22, 0.02)
ax.legend(loc="lower right", fontsize=8, framealpha=0.9)
ax.set_title("")  # no title for paper

plt.tight_layout()

for ext in ("pdf", "png"):
    out_path = os.path.join(args.out, f"fig_e10_tradeoff.{ext}")
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    print(f"[SAVED] {out_path}")

plt.close()
print("[DONE] fig_e10_tradeoff")
