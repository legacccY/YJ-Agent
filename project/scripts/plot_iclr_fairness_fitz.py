"""
plot_iclr_fairness_fitz.py
---------------------------
ICLR 2027 VisiSkin-Agent  Fitzpatrick I–VI 肤型公平性 AUC 柱状图（单子图）
ECE 子图已删除（ECE 列有未决张力，ICLR 本轮不展示）。

CSV 来源: results/fairness_fitzpatrick_iclr_full.csv  (ICLR 专属，不含 BMVC 产物)
读取列: baseline, baseline_name, skin_group, n, auc
  — 只取 skin_group ∈ {I-II, III-IV, V-VI} 聚合行
  — csv 无 AUC CI 列，只画柱（无误差棒）

关键值 (直接来自 csv):
  A Direct  I-II=0.6223  III-IV=0.6003  V-VI=0.5726
  F Q-VIB   I-II=0.5854  III-IV=0.6109  V-VI=0.5781
  H Focal   I-II=0.6424  III-IV=0.5788  V-VI=0.4785
  G TokFT   I-II=0.6067  III-IV=0.6247  V-VI=0.5831

画了什么:
  单子图: 3 肤型组 × 4 baseline 分组柱状 (AUC only)
  公平性发现: 深肤色 V-VI 段 AUC 比 I-II 系统性偏低

Usage:
    python plot_iclr_fairness_fitz.py [--out DIR]
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

CSV_PATH = "D:/YJ-Agent/project/results/fairness_fitzpatrick_iclr_full.csv"
df = pd.read_csv(CSV_PATH)
print(f"[READ] {CSV_PATH}: {df.shape}, groups={df['skin_group'].unique()}")

# 只要聚合组 I-II / III-IV / V-VI
df_grp = df[df["skin_group"].isin(["I-II", "III-IV", "V-VI"])].copy()

# 选显示的 baselines（AUC 公平性对比最清晰的 4 个）
SHOW_BL = ["A", "F", "H", "G"]
BL_NAMES = {
    "A": "Direct (EfB3)",
    "F": "Q-VIB Full",
    "H": "Focal+LS",
    "G": "Q-VIB+TokFT",
}
df_grp = df_grp[df_grp["baseline"].isin(SHOW_BL)].copy()

# 打印关键值核查 (AUC only)
for bl in SHOW_BL:
    for sg in ["I-II", "III-IV", "V-VI"]:
        row = df_grp[(df_grp["baseline"] == bl) & (df_grp["skin_group"] == sg)]
        if len(row) > 0:
            print(f"[CHECK] {bl} {sg}: AUC={row['auc'].values[0]:.4f}")

skin_groups = ["I-II", "III-IV", "V-VI"]
n_bl = len(SHOW_BL)
x = np.arange(len(skin_groups))
width = 0.19

# colorblind-safe
COLORS = ["#1f77b4", "#d62728", "#ff7f0e", "#2ca02c"]

fig, ax = plt.subplots(figsize=(7.0, 4.4))

for i, bl in enumerate(SHOW_BL):
    sub = df_grp[df_grp["baseline"] == bl].set_index("skin_group")
    aucs = [sub.loc[sg, "auc"] for sg in skin_groups]
    offset = (i - (n_bl - 1) / 2) * width
    bars = ax.bar(x + offset, aucs, width, color=COLORS[i],
                  label=BL_NAMES[bl], alpha=0.85)
    # value labels
    for bar, val in zip(bars, aucs):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.002,
                f"{val:.3f}", ha="center", va="bottom", fontsize=6.5, rotation=90)

ax.set_xticks(x)
ax.set_xticklabels(["I–II\n(light)", "III–IV\n(medium)", "V–VI\n(dark)"], fontsize=10)
ax.set_ylabel("AUC", fontsize=10)
ax.set_ylim(0.40, 0.72)
ax.axhline(0.5, color="gray", linestyle="--", linewidth=0.8, alpha=0.6)
ax.legend(fontsize=9, loc="upper right", framealpha=0.9)
ax.tick_params(labelsize=9)

# 公平性注释: Focal+LS I-II → V-VI 最大 drop
h_iii = df_grp[(df_grp["baseline"] == "H") & (df_grp["skin_group"] == "I-II")]["auc"].values[0]
h_vvi = df_grp[(df_grp["baseline"] == "H") & (df_grp["skin_group"] == "V-VI")]["auc"].values[0]
h_col = COLORS[SHOW_BL.index("H")]
ax.annotate(
    f"Focal+LS: {h_iii:.3f}→{h_vvi:.3f}\n(−{h_iii - h_vvi:.3f} across tone)",
    xy=(2 + (SHOW_BL.index("H") - (n_bl - 1) / 2) * width, h_vvi),
    xytext=(1.20, 0.435),
    fontsize=7.5, color=h_col,
    arrowprops=dict(arrowstyle="->", color=h_col, lw=0.9),
    bbox=dict(boxstyle="round,pad=0.25", fc="white", ec=h_col, alpha=0.85),
)

plt.tight_layout()

for ext in ("pdf", "png"):
    out_path = os.path.join(args.out, f"fig_fairness_fitz.{ext}")
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    print(f"[SAVED] {out_path}")

plt.close()
print("[DONE] fig_fairness_fitz (single AUC panel, ECE removed)")
