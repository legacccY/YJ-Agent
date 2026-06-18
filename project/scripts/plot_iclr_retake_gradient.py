"""
plot_iclr_retake_gradient.py
-----------------------------
ICLR 2027 VisiSkin-Agent  Retake 触发率随退化档梯度柱状图 + CI

CSV 来源: results/agent_vs_direct_risk.csv
读取列 (channel=retake):
  channel, band, retake_rate, retake_rate_ci_lo, retake_rate_ci_hi

关键值 (直接来自 csv, channel=retake):
  severe:   retake_rate=0.8889, CI=[0.8000, 0.9778]
  moderate: retake_rate=0.6508, CI=[0.6000, 0.7051]
  high:     retake_rate=0.0552, CI=[0.0310, 0.0828]

(band 名称: high = 图像质量已高不需 retake → 低触发; severe/moderate = 质量差 → 高触发)

画了什么:
  3 档 (severe degraded / moderate degraded / high quality) 柱状 + 误差棒
  颜色 = RdBu 色谱 (red=低质高触发, blue=高质低触发)

Usage:
    python plot_iclr_retake_gradient.py [--out DIR]
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

CSV_PATH = "D:/YJ-Agent/project/results/agent_vs_direct_risk.csv"
df = pd.read_csv(CSV_PATH)
retake = df[(df["channel"] == "retake") & (df["band"].isin(["severe", "moderate", "high"]))].copy()
print(f"[READ] {CSV_PATH}: retake rows={len(retake)}")

# 核关键值
for _, row in retake.iterrows():
    print(f"[CHECK] band={row['band']}: retake_rate={row['retake_rate']:.4f}, "
          f"CI=[{row['retake_rate_ci_lo']:.4f}, {row['retake_rate_ci_hi']:.4f}]")

# 排序: severe / moderate / high
ORDER = ["severe", "moderate", "high"]
ORDER_LABELS = ["Severely\nDegraded", "Moderately\nDegraded", "High\nQuality"]
retake = retake.set_index("band").loc[ORDER].reset_index()

rates = retake["retake_rate"].values
ci_lo = retake["retake_rate_ci_lo"].values
ci_hi = retake["retake_rate_ci_hi"].values
yerr_lo = rates - ci_lo
yerr_hi = ci_hi - rates

# RdBu: severe=red, moderate=mid, high=blue
COLORS = ["#d62728", "#ff7f0e", "#1f77b4"]

fig, ax = plt.subplots(figsize=(5.5, 4.2))

x = np.arange(3)
bars = ax.bar(x, rates, color=COLORS, alpha=0.85, width=0.52,
              yerr=[yerr_lo, yerr_hi], capsize=5,
              error_kw={"elinewidth": 1.5, "ecolor": "dimgray"})

# value labels
for bar, val, lo, hi in zip(bars, rates, ci_lo, ci_hi):
    ax.text(bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.02,
            f"{val:.0%}", ha="center", va="bottom", fontsize=10, fontweight="bold")

ax.set_xticks(x)
ax.set_xticklabels(ORDER_LABELS, fontsize=9.5)
ax.set_ylabel("Retake Trigger Rate", fontsize=10)
ax.set_ylim(0, 1.08)
ax.axhline(0.5, color="gray", linestyle="--", linewidth=0.8, alpha=0.5)
ax.tick_params(labelsize=9)

# 注释: expected direction
ax.annotate("retake when\nneeded", xy=(0, 0.89), xytext=(0.45, 0.97),
            fontsize=8, color="#d62728", ha="center",
            arrowprops=dict(arrowstyle="->", color="#d62728", lw=0.8))
ax.annotate("skip when\nalready clean", xy=(2, 0.055), xytext=(1.6, 0.22),
            fontsize=8, color="#1f77b4", ha="center",
            arrowprops=dict(arrowstyle="->", color="#1f77b4", lw=0.8))

plt.tight_layout()

for ext in ("pdf", "png"):
    out_path = os.path.join(args.out, f"fig_retake_gradient.{ext}")
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    print(f"[SAVED] {out_path}")

plt.close()
print("[DONE] fig_retake_gradient")
