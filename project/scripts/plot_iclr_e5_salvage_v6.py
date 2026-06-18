"""
plot_iclr_e5_salvage_v6.py
---------------------------
ICLR 2027 VisiSkin-Agent  E5 Melanoma Salvage — v6 NULL 结果可视化

CSV 来源:
  results/e5_salvage_v6.csv         (stratum-level 汇总)
  results/e5_salvage_v6_persample.csv (per-sample, 用于 overall stats)

读取列 (v6.csv): stratum, n, qbar_route_mean, salvageable, salvaged,
                  SalvageRate, DamageRate, n_pos
读取列 (persample): sev, target, qbar_route, correct_deg, correct_enh, qband

关键值 (来自 per-sample melanoma target==1):
  Melanoma n=351, salvageable=77 (wrong on deg)
  salvaged=4  (5.2%),  damaged=83  (23.7%),  net=-79
  → 诚实 null: enhancement 对 melanoma 净负效应

画了什么:
  瀑布图: salvageable(77) → salvaged(+4) → damaged(−83) → net change(−79)
  + 右侧 bar 图: per-severity (mild/moderate/severe) salvaged vs damaged

取代 report/figures/fig_e5_salvage.{pdf,png} (v5 过时正向故事版)

Usage:
    python plot_iclr_e5_salvage_v6.py [--out DIR]
"""

import argparse
import os

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

CSV_SUMM = "D:/YJ-Agent/project/results/e5_salvage_v6.csv"
CSV_PERS = "D:/YJ-Agent/project/results/e5_salvage_v6_persample.csv"

df_summ = pd.read_csv(CSV_SUMM)
df_per = pd.read_csv(CSV_PERS)

print(f"[READ] {CSV_SUMM}: {df_summ.shape}")
print(f"[READ] {CSV_PERS}: {df_per.shape}")

# ---------- 计算 melanoma stats ----------
pos = df_per[df_per["target"] == 1].copy()
n_mel = len(pos)
salvageable = int((pos["correct_deg"] == 0).sum())
salvaged = int(((pos["correct_deg"] == 0) & (pos["correct_enh"] == 1)).sum())
damaged = int(((pos["correct_deg"] == 1) & (pos["correct_enh"] == 0)).sum())
net = salvaged - damaged

n_correct = n_mel - salvageable  # originally correct on deg = 274
print(f"[CHECK] Melanoma n={n_mel}, salvageable={salvageable}, n_correct={n_correct}")
print(f"  salvaged={salvaged} ({salvaged/salvageable:.1%} of {salvageable} misclassified), "
      f"damaged={damaged} ({damaged/n_correct:.1%} of {n_correct} correct), net={net}")

# per-severity
sev_stats = {}
for sev in ["mild", "moderate", "severe"]:
    sub = pos[pos["sev"] == sev]
    s = int(((sub["correct_deg"] == 0) & (sub["correct_enh"] == 1)).sum())
    d = int(((sub["correct_deg"] == 1) & (sub["correct_enh"] == 0)).sum())
    sev_stats[sev] = {"salvaged": s, "damaged": d, "net": s - d}
    print(f"[CHECK] {sev}: salvaged={s}, damaged={d}, net={s-d}")

# ---------- 布局: 左=瀑布, 右=per-sev ----------
fig, (ax_wf, ax_sv) = plt.subplots(1, 2, figsize=(10.0, 4.8),
                                    gridspec_kw={"width_ratios": [1.4, 1]})

# ---- 瀑布图 ----
# Steps: salvageable base | +salvaged | -damaged | =net effect
categories = ["Salvageable\n(wrong on\ndeg., n=77)",
               "Salvaged\n(+4)",
               "Damaged\n(−83)",
               "Net Change\n(−79)"]
values = [salvageable, salvaged, -damaged, net]
colors = ["#9467bd", "#2ca02c", "#d62728", "#d62728" if net < 0 else "#2ca02c"]

# 瀑布的起始 y 值
running = [0, salvageable, salvageable + salvaged, 0]
bar_heights = [salvageable, salvaged, damaged, abs(net)]

for i, (cat, val, run, h, col) in enumerate(
        zip(categories, values, running, bar_heights, colors)):
    if i == 0:
        bottom = 0
        ax_wf.bar(i, h, bottom=bottom, color=col, alpha=0.75, width=0.55)
    elif i == 1:  # salvaged (on top of salvageable)
        ax_wf.bar(i, h, bottom=0, color=col, alpha=0.75, width=0.55)
    elif i == 2:  # damaged (descending from n_mel=351)
        # show as negative bar from 0
        ax_wf.bar(i, -h, bottom=0, color=col, alpha=0.75, width=0.55)
    else:  # net: show absolute
        ax_wf.bar(i, -h, bottom=0, color=col, alpha=0.85, width=0.55,
                  hatch="//", edgecolor="white")

    # label
    label_y = (h + 2) if val >= 0 else (-h - 5)
    txt = f"+{h}" if val > 0 else f"−{h}" if val < 0 else f"{h}"
    ax_wf.text(i, label_y if i != 2 else -(h + 5),
               txt, ha="center", va="bottom" if val >= 0 else "top",
               fontsize=10, fontweight="bold",
               color="#2ca02c" if val > 0 else "#d62728")

ax_wf.axhline(0, color="gray", linewidth=0.8)
ax_wf.set_xticks(range(4))
ax_wf.set_xticklabels(categories, fontsize=8.5)
ax_wf.set_ylabel("Number of Melanoma Cases", fontsize=10)
ax_wf.set_ylim(-100, 100)
ax_wf.set_title("(a) Enhancement Effect on Melanoma\n(v6 honest null result)", fontsize=9, pad=4)
ax_wf.tick_params(labelsize=9)

# add annotation box — damage rate denom = n_correct (274 originally-correct mel cases)
ax_wf.text(2.5, 70,
           f"n_mel = {n_mel}\n"
           f"SalvageRate = {salvaged/salvageable:.1%} ({salvaged}/{salvageable} misclassified)\n"
           f"DamageRate = {damaged/n_correct:.1%} ({damaged}/{n_correct} correct)\n"
           f"Net = {net}",
           fontsize=7.5, va="top", ha="center",
           bbox=dict(boxstyle="round,pad=0.4", fc="lightyellow", ec="gray", alpha=0.9))

# ---- per-severity ----
sev_order = ["mild", "moderate", "severe"]
sev_labels = ["Mild", "Moderate", "Severe"]
salv_vals = [sev_stats[s]["salvaged"] for s in sev_order]
dam_vals  = [sev_stats[s]["damaged"]  for s in sev_order]

x = np.arange(3)
w = 0.32
ax_sv.bar(x - w/2, salv_vals, w, color="#2ca02c", alpha=0.8, label="Salvaged")
ax_sv.bar(x + w/2, dam_vals,  w, color="#d62728", alpha=0.8, label="Damaged")

for i, (s, d) in enumerate(zip(salv_vals, dam_vals)):
    ax_sv.text(i - w/2, s + 0.3, str(s), ha="center", fontsize=9, color="#2ca02c", fontweight="bold")
    ax_sv.text(i + w/2, d + 0.3, str(d), ha="center", fontsize=9, color="#d62728", fontweight="bold")

ax_sv.set_xticks(x)
ax_sv.set_xticklabels(sev_labels, fontsize=9.5)
ax_sv.set_ylabel("Melanoma Cases", fontsize=10)
ax_sv.set_title("(b) Per-Severity: Salvaged vs. Damaged\n(melanoma positive only)", fontsize=9, pad=4)
ax_sv.legend(fontsize=9, loc="upper left", framealpha=0.9)
ax_sv.tick_params(labelsize=9)
ax_sv.set_ylim(0, max(dam_vals) + 8)

plt.tight_layout()

for ext in ("pdf", "png"):
    out_path = os.path.join(args.out, f"fig_e5_salvage_v6.{ext}")
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    print(f"[SAVED] {out_path}")

plt.close()
print("[DONE] fig_e5_salvage_v6 (honest null, replaces v5)")
