#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
plot_subset_extra_v3.py
服务: quantimmu-bench — 把被误删的「其他种类的图」按 v3 标准重画回来。

产出 (analysis/figures/*_v3.{png,pdf})，每个子集:
  fig_roc_<label>_v3        ROC 曲线（max 聚合, Elispot>0），v3 样式
  fig_consistency_<label>_v3 工具间一致性热图（肽级分数两两 Spearman），v3 样式
  fig_lenstrat_<label>_v3   按肽长分层的 AUC（仅 5tools/10tools）

数据源:
  scripts/out/merged_all_tools_16tools.xlsx  ← HLA 修正后逐肽分数矩阵（与 v3 同源）

口径: 每条肽对每个工具取「子肽×HLA 最大分」聚合到肽级；标签 = Elispot>0。
纯 numpy 算 rank/Spearman/ROC（避 scipy.stats × torch OMP 冲突）。
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

HERE   = Path(__file__).resolve().parent
ROOT   = HERE.parent
FIGDIR = HERE / "figures"
FIGDIR.mkdir(exist_ok=True)
MERGED = ROOT / "scripts" / "out" / "merged_all_tools_16tools.xlsx"

# 工具显示名 → merged xlsx 的 MT_ 列名
COL = {
    "DeepImmuno": "MT_DeepImmuno", "PredIG": "MT_PredIG", "pTuneos": "MT_pTuneos",
    "IMPROVE": "MT_IMPROVE_mean_prediction_rf", "NeoTImmuML": "MT_NeoTImmuML",
    "PRIME": "MT_PRIME", "ImmuneApp": "MT_ImmuneApp", "deepHLApan": "MT_deepHLApan",
    "HLAthena": "MT_HLAthena",
    "BigMHC": "MT_BigMHC", "CNNeo": "MT_CNNeo", "IEDB_Calis": "MT_IEDB_Calis",
    "MHCflurry": "MT_MHCflurry_presentation", "Repitope": "MT_Repitope",
    "netMHCpan-BA": "MT_netmhcpan_ba", "TSCAPE": "MT_TSCAPE",
}

SUBSETS = {
    "5tools":  ["DeepImmuno", "PredIG", "pTuneos", "IMPROVE", "NeoTImmuML"],
    "10tools": ["DeepImmuno", "PredIG", "pTuneos", "IMPROVE", "NeoTImmuML",
                "PRIME", "ImmuneApp", "deepHLApan", "HLAthena"],
    "newtools": ["IEDB_Calis", "Repitope", "netMHCpan-BA", "MHCflurry",
                 "CNNeo", "BigMHC", "TSCAPE"],
}
NLABEL = {"5tools": "第一批 5 工具", "10tools": "10 工具", "newtools": "新增 7 工具"}
DOLEN  = {"5tools", "10tools"}   # 长度分层只对前两批（新工具肽长口径不同）

LINE_COLORS = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#D55E00",
               "#56B4E9", "#F0E442", "#999999", "#882255", "#117733"]


_MERGED_DS2 = None
def load_ds2():
    """读 merged xlsx 一次，过滤 DS2，缓存复用（避免每工具重读 10MB）。"""
    global _MERGED_DS2
    if _MERGED_DS2 is None:
        df = pd.read_excel(MERGED)
        if "Dataset" in df.columns:
            df = df[df["Dataset"] == "DS2"].copy()
        _MERGED_DS2 = df
    return _MERGED_DS2


def save_fig(fig, name):
    fig.savefig(FIGDIR / f"{name}.png", dpi=150, bbox_inches="tight")
    fig.savefig(FIGDIR / f"{name}.pdf", bbox_inches="tight")
    try:
        from PIL import Image
        im = Image.open(FIGDIR / f"{name}.png"); w, h = im.size; im.close()
    except Exception:
        w, h = round(fig.get_figwidth() * 150), round(fig.get_figheight() * 150)
    plt.close(fig)
    print(f"  [saved] {name}  {w}x{h}px  ratio={w/h:.2f}")


def rankdata_avg(x):
    """平均秩（处理并列），纯 numpy。"""
    x = np.asarray(x, float)
    order = np.argsort(x, kind="mergesort")
    ranks = np.empty(len(x), float)
    sx = x[order]
    i = 0
    while i < len(x):
        j = i
        while j + 1 < len(x) and sx[j + 1] == sx[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return ranks


def spearman(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    m = ~(np.isnan(a) | np.isnan(b))
    if m.sum() < 3:
        return np.nan
    ra, rb = rankdata_avg(a[m]), rankdata_avg(b[m])
    if ra.std() == 0 or rb.std() == 0:
        return np.nan
    return float(np.corrcoef(ra, rb)[0, 1])


def auc_mw(y, s):
    """Mann-Whitney AUC（含并列平均秩），纯 numpy。"""
    y, s = np.asarray(y, int), np.asarray(s, float)
    m = ~np.isnan(s)
    y, s = y[m], s[m]
    npos, nneg = int((y == 1).sum()), int((y == 0).sum())
    if npos == 0 or nneg == 0:
        return np.nan
    r = rankdata_avg(s)
    return (r[y == 1].sum() - npos * (npos + 1) / 2.0) / (npos * nneg)


def roc_xy(y, s):
    y, s = np.asarray(y, int), np.asarray(s, float)
    m = ~np.isnan(s)
    y, s = y[m], s[m]
    order = np.argsort(-s, kind="mergesort")
    y = y[order]
    P, N = max((y == 1).sum(), 1), max((y == 0).sum(), 1)
    tpr = np.concatenate([[0], np.cumsum(y) / P])
    fpr = np.concatenate([[0], np.cumsum(1 - y) / N])
    return fpr, tpr


def peptide_level(tools):
    """读 corrected merged，过滤 DS2，按 Peptide_ID 取每工具子肽×HLA 最大分 → 肽级矩阵 + 标签。
    口径与官方 metrics_ds2_*.csv 一致（sub_agg=max，HLA-dep 工具 P101/P102 为 NaN 自动 dropna）。"""
    df = load_ds2()
    cols = [COL[t] for t in tools]
    keep = ["Peptide_ID", "Elispot", "Peptide_Length"] + cols
    df = df[keep].copy()
    for c in cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    agg = {c: "max" for c in cols}
    agg["Elispot"] = "first"
    agg["Peptide_Length"] = "first"
    pep = df.groupby("Peptide_ID", as_index=False).agg(agg)
    pep["label"] = (pep["Elispot"] > 0).astype(int)
    return pep, cols


# ── ROC ───────────────────────────────────────────────────────────────────────
def plot_roc(tools, label):
    pep, cols = peptide_level(tools)
    aucs = {t: auc_mw(pep["label"].values, pep[COL[t]].values) for t in tools}
    order = sorted(tools, key=lambda t: (-aucs[t] if not np.isnan(aucs[t]) else 1))

    fig, ax = plt.subplots(figsize=(7.6, 6.4))
    ax.plot([0, 1], [0, 1], ls="--", color="#999", lw=1.2, label="随机 (AUC 0.50)")
    for i, t in enumerate(order):
        fpr, tpr = roc_xy(pep["label"].values, pep[COL[t]].values)
        ax.plot(fpr, tpr, lw=2.0, color=LINE_COLORS[i % len(LINE_COLORS)],
                label=f"{t}  (AUC {aucs[t]:.3f})")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1.02)
    ax.set_xlabel("假阳性率 (1 − 特异度)", fontsize=10.5)
    ax.set_ylabel("真阳性率 (敏感度)", fontsize=10.5)
    ax.set_title(f"{NLABEL[label]} ROC 曲线 — DS2 HLA 修正后\n"
                 "肽级最大分聚合，Elispot>0 为阳性；曲线越凸向左上判别力越强",
                 fontsize=10.5, pad=8)
    ax.legend(loc="lower right", fontsize=8.5, framealpha=0.92)
    ax.grid(color="#eee", lw=0.5)
    ax.set_axisbelow(True)
    plt.tight_layout()
    save_fig(fig, f"fig_roc_{label}_v3")


# ── 工具间一致性热图 ───────────────────────────────────────────────────────────
def plot_consistency(tools, label):
    pep, cols = peptide_level(tools)
    n = len(tools)
    M = np.full((n, n), np.nan)
    for i, ti in enumerate(tools):
        for j, tj in enumerate(tools):
            M[i, j] = 1.0 if i == j else spearman(pep[COL[ti]].values, pep[COL[tj]].values)

    fig, ax = plt.subplots(figsize=(max(6.5, 0.62 * n + 2.4), max(5.6, 0.62 * n + 1.8)))
    im = ax.imshow(M, cmap="RdYlGn", vmin=-0.5, vmax=1.0, interpolation="nearest")
    for i in range(n):
        for j in range(n):
            v = M[i, j]
            if np.isnan(v):
                continue
            tc = "white" if (v > 0.6 or v < -0.2) else "black"
            ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=8, color=tc)
    ax.set_xticks(range(n)); ax.set_xticklabels(tools, fontsize=8.5, rotation=35, ha="right")
    ax.set_yticks(range(n)); ax.set_yticklabels(tools, fontsize=8.5)
    cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.03)
    cb.set_label("肽级分数两两 Spearman 相关", fontsize=9)
    ax.set_title(f"{NLABEL[label]} 工具间一致性热图 — DS2 HLA 修正后\n"
                 "对角线恒为 1；非对角越接近 0 说明不同工具排序越各说各话",
                 fontsize=10.5, pad=8)
    plt.tight_layout()
    save_fig(fig, f"fig_consistency_{label}_v3")


# ── 长度分层 AUC（按每工具最强结合子肽的 k-mer 长度分层）────────────────────────
def best_binder_len_table(tool):
    """每工具：每条肽取最强结合子肽，记其 Window_Size(k-mer 长度) + 标签。"""
    df = load_ds2()
    col = COL[tool]
    sub = df[["Peptide_ID", "Elispot", "Window_Size", col]].copy()
    sub[col] = pd.to_numeric(sub[col], errors="coerce")
    sub = sub.dropna(subset=[col])
    if len(sub) == 0:
        return None
    idx = sub.groupby("Peptide_ID")[col].idxmax()
    bb = sub.loc[idx].copy()
    bb["label"] = (bb["Elispot"] > 0).astype(int)
    bb = bb.rename(columns={col: "score", "Window_Size": "blen"})
    return bb[["Peptide_ID", "label", "blen", "score"]]


def plot_lenstrat(tools, label):
    bbt = {t: best_binder_len_table(t) for t in tools}
    bins = [(8, 9, "8–9 mer"), (10, 11, "10–11 mer"), (12, 14, "12–14 mer")]
    # 各区间样本量按第一个工具估（各工具最强子肽长度略有差异，取并集判定有效）
    keep_bins = []
    for lo, hi, nm in bins:
        ok = False
        for t in tools:
            b = bbt[t]
            if b is None:
                continue
            seg = b[(b["blen"] >= lo) & (b["blen"] <= hi)]
            if len(seg) >= 8 and seg["label"].nunique() == 2:
                ok = True
        if ok:
            keep_bins.append((lo, hi, nm))
    if not keep_bins:
        print(f"  [skip] lenstrat_{label}: 分层后样本不足")
        return

    n_t, n_g = len(tools), len(keep_bins)
    fig, ax = plt.subplots(figsize=(max(8.5, 1.05 * n_t + 2.5), 5.6))
    x = np.arange(n_g); bw = 0.84 / n_t
    for i, t in enumerate(tools):
        b = bbt[t]
        vals = []
        for lo, hi, nm in keep_bins:
            if b is None:
                vals.append(np.nan); continue
            seg = b[(b["blen"] >= lo) & (b["blen"] <= hi)]
            vals.append(auc_mw(seg["label"].values, seg["score"].values)
                        if (len(seg) >= 8 and seg["label"].nunique() == 2) else np.nan)
        ax.bar(x + (i - n_t / 2 + 0.5) * bw, np.nan_to_num(vals, nan=0.0), width=bw,
               color=LINE_COLORS[i % len(LINE_COLORS)], label=t, edgecolor="#fff", linewidth=0.4)
    ax.axhline(0.5, ls="--", color="#888", lw=1.2)
    ax.text(n_g - 0.5, 0.505, "随机 0.5", fontsize=8, color="#888", va="bottom", ha="right")
    ax.set_xticks(x)
    ax.set_xticklabels([nm for _, _, nm in keep_bins], fontsize=9.5)
    ax.set_ylim(0, 1.0)
    ax.set_ylabel("AUC-ROC", fontsize=10.5)
    ax.set_title(f"{NLABEL[label]} 按结合子肽长度分层的判别力 AUC — DS2 HLA 修正后\n"
                 "横轴为每工具最强结合子肽的 k-mer 长度；看判别力是否跨肽长稳健（仅作参考）",
                 fontsize=10.5, pad=8)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12),
              ncol=min(n_t, 5), fontsize=8.5, frameon=False)
    ax.grid(axis="y", color="#eee", lw=0.5)
    ax.set_axisbelow(True)
    plt.tight_layout()
    save_fig(fig, f"fig_lenstrat_{label}_v3")


def main():
    print("=== plot_subset_extra_v3.py — ROC + 一致性热图 + 长度分层 ===")
    for label, tools in SUBSETS.items():
        print(f"\n##### {label}: {tools}")
        plot_roc(tools, label)
        plot_consistency(tools, label)
        if label in DOLEN:
            plot_lenstrat(tools, label)
    print("\n[DONE]", FIGDIR)


if __name__ == "__main__":
    main()
