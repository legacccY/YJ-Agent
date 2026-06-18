"""
plot_iclr_crossdomain.py
-------------------------
ICLR 2027 VisiSkin-Agent  跨域泛化柱状图（4 皮肤域, per-baseline）

CSV 来源 (ICLR Jun14-15 重跑, R10 干净):
  results/external_fitz17k_predictions.csv
  results/external_ham10000_predictions.csv
  results/external_pad_ufes_predictions.csv
  results/external_dermnet_predictions.csv
读取列: baseline, baseline_name, prob_pos, target
  → 逐 baseline 纯 numpy trapz 计算 AUC (不用 scipy)

注意: cross_dataset_qcdi.csv 不使用（Jun5 BMVC 嫌疑，R10 隔离）
      CheXray/Fundus crossdomain 不使用（用户拍板只 4 皮肤域）

关键值 (脚本重算):
  ITB (Fitz17k):  A=0.6085, F=0.5991, H=0.6105, G=0.6188
  HAM10000:       A=0.8048, F=0.6212, H=0.7561, G=0.7060
  PAD-UFES:       A=0.6726, F=0.4889, H=0.5630, G=0.5431
  DermNet:        A=0.5030, F=0.5373, H=0.6038, G=0.5394

画了什么:
  4 域 × 4 baseline 分组柱状 AUC
  baselines: A(Direct), F(Q-VIB Full), H(Focal+LS), G(Q-VIB+TokFT)

Usage:
    python plot_iclr_crossdomain.py [--out DIR]
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

RESULTS_DIR = "D:/YJ-Agent/project/results"

# ---------- AUC 计算 (纯 numpy, 不用 scipy) ----------
def compute_auc(y_true, y_score):
    y_true = np.array(y_true, dtype=float)
    y_score = np.array(y_score, dtype=float)
    desc = np.argsort(-y_score)
    y_true_sorted = y_true[desc]
    npos = y_true.sum()
    nneg = len(y_true) - npos
    if npos == 0 or nneg == 0:
        return float("nan")
    tp = np.cumsum(y_true_sorted)
    fp = np.arange(1, len(y_true) + 1) - tp
    tpr = tp / npos
    fpr = fp / nneg
    return float(np.trapz(tpr, fpr))

# ---------- 4 皮肤域 (只用 external_*_predictions.csv, 不碰 qcdi/crossdomain) ----------
SKIN_DATASETS = {
    "ITB\n(Fitz17k)": "external_fitz17k_predictions.csv",
    "HAM10000":       "external_ham10000_predictions.csv",
    "PAD-UFES":       "external_pad_ufes_predictions.csv",
    "DermNet":        "external_dermnet_predictions.csv",
}
SHOW_BL = ["A", "F", "H", "G"]
BL_NAMES = {
    "A": "Direct (EfB3)",
    "F": "Q-VIB Full",
    "H": "Focal+LS",
    "G": "Q-VIB+TokFT",
}

skin_aucs = {}  # domain → {bl: auc}
for dname, fname in SKIN_DATASETS.items():
    path = os.path.join(RESULTS_DIR, fname)
    df = pd.read_csv(path)
    # confirm columns
    assert "baseline" in df.columns and "prob_pos" in df.columns and "target" in df.columns, \
        f"Missing expected columns in {fname}: {df.columns.tolist()}"
    skin_aucs[dname] = {}
    for bl in SHOW_BL:
        sub = df[df["baseline"] == bl]
        auc = compute_auc(sub["target"], sub["prob_pos"])
        skin_aucs[dname][bl] = auc
        print(f"[CHECK] {dname.split(chr(10))[0]} {bl}: AUC={auc:.4f}  n={len(sub)}")

# ---------- 绘图 ----------
all_domains = list(skin_aucs.keys())
n_domains = len(all_domains)
n_bl = len(SHOW_BL)
x = np.arange(n_domains)
width = 0.19
COLORS = ["#1f77b4", "#d62728", "#ff7f0e", "#2ca02c"]

fig, ax = plt.subplots(figsize=(8.5, 4.6))

for i, bl in enumerate(SHOW_BL):
    aucs = [skin_aucs[d][bl] for d in all_domains]
    offset = (i - (n_bl - 1) / 2) * width
    bars = ax.bar(x + offset, aucs, width, color=COLORS[i],
                  label=BL_NAMES[bl], alpha=0.85)
    # value labels
    for bar, val in zip(bars, aucs):
        if not np.isnan(val):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.005,
                    f"{val:.3f}", ha="center", va="bottom", fontsize=6.5, rotation=90)

ax.set_xticks(x)
ax.set_xticklabels(all_domains, fontsize=9)
ax.set_ylabel("AUC", fontsize=10)
ax.set_ylim(0.35, 0.90)
ax.axhline(0.5, color="gray", linestyle="--", linewidth=0.8, alpha=0.5)
ax.legend(fontsize=9, loc="upper right", framealpha=0.9)
ax.tick_params(labelsize=9)

# 注释: HAM10000 上 Direct 大幅领先 (quality-oblivious 训练域内)
a_ham = skin_aucs["HAM10000"]["A"]
ax.annotate(
    f"Direct AUC={a_ham:.3f}\n(in-distribution advantage)",
    xy=(1 + (SHOW_BL.index("A") - (n_bl - 1) / 2) * width, a_ham),
    xytext=(1.5, 0.845),
    fontsize=7.5, color=COLORS[SHOW_BL.index("A")],
    arrowprops=dict(arrowstyle="->", color=COLORS[SHOW_BL.index("A")], lw=0.9),
    bbox=dict(boxstyle="round,pad=0.25", fc="white",
              ec=COLORS[SHOW_BL.index("A")], alpha=0.85),
)

plt.tight_layout()

for ext in ("pdf", "png"):
    out_path = os.path.join(args.out, f"fig_crossdomain.{ext}")
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    print(f"[SAVED] {out_path}")

plt.close()
print("[DONE] fig_crossdomain (4 skin domains, no CheXray, no qcdi)")
