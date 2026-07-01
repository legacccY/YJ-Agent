# -*- coding: utf-8 -*-
"""
plot_ppt_v4_eval.py — QuantImmuBench 进度评价版 PPT 图 (Part 2)
服务: Q2 融合近亲 / 问题一(肽长混杂)现象 lever。
产 6 张 PNG 到 analysis/figures_ppt_v4/。
配色沿用项目 v3。中文字体 Microsoft YaHei。
本脚本只画图不下结论(图E中性措辞)。主线运行, coder 不跑。

数据来源 (全部 pandas 读, comment='#' 跳注释行):
  图A q2_rank_corr_heatmap.png     <- analysis/official/Q2_rank_corr_matrix.csv  (8x8 index_col=0)
  图B q2_taylor_scatter.png        <- analysis/theory/Q2_taylor_verification.csv (corr_theory,corr_actual,s2_i,residual)
  图C q2_pointest_cluster.png      <- analysis/official/Q2_fusion_kinship_paired.csv (rho_bar_a,rho_bar_b,p_raw)
  图D q2_auprc_kinship.png         <- analysis/official/Q2_peptide_auprc_kinship.csv (role=primary: delta,ci_lo,ci_hi,p_cross0)
  图E len_confound_bare_vs_ctrl.png<- analysis/official/R1_single_maxpool_official.csv (Tool,fisherz_rho_raw,fisherz_rho_lenctrl)
  图F progress_overview.png        <- 硬编码进度数字
"""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

# ---- 中文字体 (Windows 铁律) ----
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

# ---- 项目 v3 配色 ----
C_BLUE = "#0072B2"   # 主
C_ORANGE = "#E69F00" # 强调
C_GRAY = "#7F7F7F"   # 灰
C_RED = "#B23A48"    # 红警
C_GREEN = "#00A896"  # 绿

# ---- 路径 (基于脚本所在 analysis/ 目录) ----
HERE = os.path.dirname(os.path.abspath(__file__))
OFF = os.path.join(HERE, "official")
THEORY = os.path.join(HERE, "theory")
OUT = os.path.join(HERE, "figures_ppt_v4")
os.makedirs(OUT, exist_ok=True)

DPI = 200


def save(fig, name):
    path = os.path.join(OUT, name)
    fig.savefig(path, dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"[saved] {path}")


# ============================================================
# 图A: 8x8 融合法两两秩相关热图
#   源 Q2_rank_corr_matrix.csv, index_col=0, 对角线为空(NaN)
# ============================================================
def fig_A():
    df = pd.read_csv(os.path.join(OFF, "Q2_rank_corr_matrix.csv"),
                     comment="#", index_col=0)
    labels = list(df.columns)
    M = df.values.astype(float)  # 对角 NaN

    fig, ax = plt.subplots(figsize=(8.2, 7.0))
    im = ax.imshow(M, cmap="YlGnBu", vmin=0.7, vmax=1.0, aspect="equal")

    n = len(labels)
    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_xticklabels(labels, rotation=40, ha="right", fontsize=9)
    ax.set_yticklabels(labels, fontsize=9)

    # 格子标数值 (跳 NaN 对角)
    for i in range(n):
        for j in range(n):
            v = M[i, j]
            if np.isnan(v):
                ax.text(j, i, "—", ha="center", va="center",
                        color=C_GRAY, fontsize=9)
                continue
            # 深底用白字
            txt_color = "white" if v >= 0.90 else "black"
            ax.text(j, i, f"{v:.2f}", ha="center", va="center",
                    color=txt_color, fontsize=8)

    # 高亮 geomean-mean_rank ≈0.95 近亲格 (双向两格)
    try:
        gi = labels.index("geomean")
        mi = labels.index("mean_rank")
        for (r, c) in [(gi, mi), (mi, gi)]:
            ax.add_patch(Rectangle((c - 0.5, r - 0.5), 1, 1, fill=False,
                                   edgecolor=C_ORANGE, lw=2.5))
    except ValueError:
        pass  # TODO: 若列名变更主线核

    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("病人内均值 Spearman 秩相关", fontsize=10)

    ax.set_title("融合方法两两排序相关（病人内均值）", fontsize=15, pad=12)
    fig.text(0.5, 0.015,
             "橙框标注 geomean 与 mean_rank：平均 ρ≈0.95，属数学近亲",
             ha="center", fontsize=10, color=C_ORANGE)
    fig.subplots_adjust(bottom=0.18)
    save(fig, "q2_rank_corr_heatmap.png")


# ============================================================
# 图B: 泰勒二阶验证散点
#   x=corr_theory (s²/2A), y=corr_actual (A-G), 颜色 s2_i, y=x 对角
# ============================================================
def fig_B():
    df = pd.read_csv(os.path.join(THEORY, "Q2_taylor_verification.csv"),
                     comment="#")
    x = df["corr_theory"].values
    y = df["corr_actual"].values
    s2 = df["s2_i"].values

    fig, ax = plt.subplots(figsize=(7.6, 6.6))
    sc = ax.scatter(x, y, c=s2, cmap="viridis", s=34, alpha=0.8,
                    edgecolor="white", linewidth=0.4)

    # y=x 对角线 (基于数据范围)
    lo = float(np.nanmin([x.min(), y.min()]))
    hi = float(np.nanmax([x.max(), y.max()]))
    pad = (hi - lo) * 0.05
    ax.plot([lo - pad, hi + pad], [lo - pad, hi + pad],
            "--", color=C_RED, lw=1.6, label="y = x（理论=实际）")

    ax.set_xlim(lo - pad, hi + pad)
    ax.set_ylim(lo - pad, hi + pad)
    ax.set_xlabel("理论修正  s²/(2A)", fontsize=12)
    ax.set_ylabel("实际修正  A − G", fontsize=12)
    ax.set_title("几何均值 ≈ 算术均值 − 分歧度修正（泰勒二阶验证）",
                 fontsize=14, pad=10)
    # 副标注: 残差中位≈0.041 / 相对误差中位≈12.5% (来自 csv 注释)
    ax.text(0.03, 0.95,
            "残差中位 ≈ 0.041   |相对误差| 中位 ≈ 12.5%  (n=130)",
            transform=ax.transAxes, fontsize=10, color=C_GRAY,
            va="top")
    ax.legend(loc="lower right", fontsize=10, frameon=False)

    cbar = fig.colorbar(sc, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("肽内 rank 方差  s²", fontsize=10)
    save(fig, "q2_taylor_scatter.png")


# ============================================================
# 图C: 三融合法 per-patient 平均ρ 点估紧簇
#   源 Q2_fusion_kinship_paired.csv: rho_bar_a/rho_bar_b, p_raw
#   geomean 0.362 / mean_rank 0.352 / median 0.268
#   p(geomean vs mean_rank)=0.79
# ============================================================
def fig_C():
    df = pd.read_csv(os.path.join(OFF, "Q2_fusion_kinship_paired.csv"),
                     comment="#")

    # 从配对行提取三法 平均ρ (每法在 rho_bar_a 或 rho_bar_b 出现)
    rho = {}
    for _, r in df.iterrows():
        rho[r["method_a"]] = r["rho_bar_a"]
        rho[r["method_b"]] = r["rho_bar_b"]
    order = ["geomean", "mean_rank", "median"]
    vals = [rho[m] for m in order]

    # p 值: geomean vs mean_rank 用 p_raw
    p_gm = df[(df["method_a"] == "geomean") &
              (df["method_b"] == "mean_rank")]["p_raw"].values
    p_gm = float(p_gm[0]) if len(p_gm) else np.nan

    # TODO(主线核): 本 csv 仅含配对 Δz均值 的 95%CI (ci_lo_raw/ci_hi_raw),
    # 无 per-method 独立 CI。此处不画 per-method 误差棒, 改标 p 值示统计打平。
    # 如需 per-method CI 需 researcher/analyst 补 per-patient bootstrap。

    fig, ax = plt.subplots(figsize=(7.0, 6.0))
    colors = [C_BLUE, C_ORANGE, C_GRAY]
    xpos = np.arange(len(order))
    bars = ax.bar(xpos, vals, width=0.55, color=colors,
                  edgecolor="black", linewidth=0.6)

    for xb, v in zip(xpos, vals):
        ax.text(xb, v + 0.008, f"{v:.3f}", ha="center", va="bottom",
                fontsize=11, fontweight="bold")

    ax.set_xticks(xpos)
    ax.set_xticklabels(["geomean", "mean_rank", "median"], fontsize=11)
    ax.set_ylabel("per-patient Spearman 平均ρ  (Fisher-z 均值)", fontsize=11)
    ax.set_ylim(0, max(vals) * 1.28)
    ax.set_title("三融合法点估紧簇，统计打平", fontsize=15, pad=10)

    # 标 geomean vs mean_rank p 值 (近亲桥)
    y_br = max(vals[0], vals[1]) * 1.10
    ax.plot([0, 0, 1, 1], [y_br, y_br + 0.006, y_br + 0.006, y_br],
            color="black", lw=1.0)
    ax.text(0.5, y_br + 0.010,
            f"geomean vs mean_rank  p = {p_gm:.2f}（近亲）",
            ha="center", va="bottom", fontsize=10, color=C_ORANGE)

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    save(fig, "q2_pointest_cluster.png")


# ============================================================
# 图D: 肽级 AUPRC 三对 ΔAUPRC (primary 口径 pval<0.05)
#   源 Q2_peptide_auprc_kinship.csv role 含 primary
#   delta + [ci_lo,ci_hi] 误差棒 + p_cross0 标注
# ============================================================
def fig_D():
    df = pd.read_csv(os.path.join(OFF, "Q2_peptide_auprc_kinship.csv"),
                     comment="#")
    prim = df[df["role"].str.contains("primary")].copy()

    def short(s):
        return s.replace("fusion_", "")
    pair_lbl = [f"{short(a)}\n− {short(b)}"
                for a, b in zip(prim["method_a"], prim["method_b"])]
    delta = prim["delta"].values
    lo = prim["ci_lo"].values
    hi = prim["ci_hi"].values
    p = prim["p_cross0"].values

    # 误差棒长度 (非对称)
    err_lo = delta - lo
    err_hi = hi - delta

    fig, ax = plt.subplots(figsize=(7.6, 6.0))
    xpos = np.arange(len(prim))
    bars = ax.bar(xpos, delta, width=0.55, color=C_BLUE,
                  edgecolor="black", linewidth=0.6)
    ax.errorbar(xpos, delta, yerr=[err_lo, err_hi], fmt="none",
                ecolor=C_RED, elinewidth=1.6, capsize=6)

    ax.axhline(0, color=C_GRAY, lw=1.0, ls="--")

    for xb, v, pv, h in zip(xpos, delta, p, hi):
        ax.text(xb, h + 0.004, f"Δ={v:.3f}\np={pv:.2f}",
                ha="center", va="bottom", fontsize=10)

    ax.set_xticks(xpos)
    ax.set_xticklabels(pair_lbl, fontsize=10)
    ax.set_ylabel("ΔAUPRC（bootstrap 1000×，95%CI）", fontsize=11)
    ax.set_ylim(min(0, lo.min()) - 0.02, hi.max() + 0.03)
    ax.set_title("肽级 AUPRC（130 肽功效）：三法差异均不显著",
                 fontsize=14, pad=10)
    ax.text(0.02, 0.96, "primary 口径 pval<0.05；全部 p_cross0 > 0.05",
            transform=ax.transAxes, fontsize=10, color=C_GRAY, va="top")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    save(fig, "q2_auprc_kinship.png")


# ============================================================
# 图E: 单工具相关 裸 vs 控肽长 对照 (问题一现象, 只画不下结论)
#   源 R1_single_maxpool_official.csv: fisherz_rho_raw / fisherz_rho_lenctrl
#   代表工具 6 个
# ============================================================
def fig_E():
    df = pd.read_csv(os.path.join(OFF, "R1_single_maxpool_official.csv"),
                     comment="#")
    reps = ["HLAthena", "andy90", "netMHCpan_BA", "MHCflurry", "PRIME", "IMPROVE"]
    sub = df[df["Tool"].isin(reps)].copy()
    # 保持指定顺序
    sub["__ord"] = sub["Tool"].apply(lambda t: reps.index(t))
    sub = sub.sort_values("__ord")

    tools = sub["Tool"].tolist()
    raw = sub["fisherz_rho_raw"].values
    ctrl = sub["fisherz_rho_lenctrl"].values

    x = np.arange(len(tools))
    w = 0.38
    fig, ax = plt.subplots(figsize=(9.2, 6.0))
    b1 = ax.bar(x - w / 2, raw, w, label="裸（等权）", color=C_BLUE,
                edgecolor="black", linewidth=0.5)
    b2 = ax.bar(x + w / 2, ctrl, w, label="控肽长（偏相关 ctrl=peplen）",
                color=C_ORANGE, edgecolor="black", linewidth=0.5)

    for bars in (b1, b2):
        for bb in bars:
            h = bb.get_height()
            ax.text(bb.get_x() + bb.get_width() / 2, h + 0.008,
                    f"{h:.2f}", ha="center", va="bottom", fontsize=9)

    ax.axhline(0, color=C_GRAY, lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(tools, rotation=18, ha="right", fontsize=10)
    ax.set_ylabel("per-patient Spearman 平均ρ（Fisher-z）", fontsize=11)
    ax.set_ylim(0, max(raw.max(), ctrl.max()) * 1.25)
    ax.set_title("单工具相关：控肽长前后对照", fontsize=15, pad=10)
    # 中性副注 — 不写结论性措辞
    ax.text(0.02, 0.96,
            "HLAthena 0.63→0.25，netMHCpan_BA 0.39→0.43"
            "（肽长是否作混杂待讨论）",
            transform=ax.transAxes, fontsize=10, color=C_GRAY, va="top")
    ax.legend(loc="upper right", fontsize=10, frameon=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    save(fig, "len_confound_bare_vs_ctrl.png")


# ============================================================
# 图F: 进度总览 (硬编码, 甜甜圈 + 进度条)
# ============================================================
def fig_F():
    # 硬编码进度 (完成/总)
    items = [
        ("工具接入", 30, 30, C_GREEN),
        ("人数据集", 2, 2, C_GREEN),      # ds1 + ds2 官方 130 肽
        ("鼠数据集", 0, 2, C_RED),        # 缺
        ("融合方法", 12, 12, C_GREEN),    # 12 法
        ("三层结果 R1-R6", 6, 6, C_GREEN),
        ("三重检验四件套", 4, 4, C_GREEN),  # 泰勒/配对置换/bootstrap/秩相关矩阵
    ]

    fig = plt.figure(figsize=(11.0, 5.4))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.0, 1.35], wspace=0.28)

    # --- 左: 甜甜圈 = 数据集完成度 (人2 + 鼠0 / 共4) ---
    ax0 = fig.add_subplot(gs[0, 0])
    done_ds = 2
    total_ds = 4
    sizes = [done_ds, total_ds - done_ds]
    ax0.pie(sizes, colors=[C_BLUE, "#E0E0E0"], startangle=90,
            counterclock=False,
            wedgeprops=dict(width=0.38, edgecolor="white"))
    ax0.text(0, 0, f"{done_ds}/{total_ds}", ha="center", va="center",
             fontsize=26, fontweight="bold", color=C_BLUE)
    ax0.text(0, -1.35, "数据集就绪（人 2 已就绪 / 鼠 2 缺失）",
             ha="center", fontsize=11, color=C_GRAY)
    ax0.set_title("数据覆盖", fontsize=13)

    # --- 右: 水平进度条 ---
    ax1 = fig.add_subplot(gs[0, 1])
    ypos = np.arange(len(items))[::-1]
    for y, (name, done, total, col) in zip(ypos, items):
        frac = done / total if total else 0
        ax1.barh(y, 1.0, height=0.55, color="#ECECEC")
        ax1.barh(y, frac, height=0.55, color=col)
        ax1.text(1.02, y, f"{done}/{total}", va="center", ha="left",
                 fontsize=11, fontweight="bold")
        ax1.text(-0.02, y, name, va="center", ha="right", fontsize=11)
    ax1.set_xlim(0, 1.18)
    ax1.set_ylim(-0.6, len(items) - 0.4)
    ax1.axis("off")
    ax1.set_title("QuantImmuBench 进度总览", fontsize=15, pad=10)

    save(fig, "progress_overview.png")


if __name__ == "__main__":
    fig_A()
    fig_B()
    fig_C()
    fig_D()
    fig_E()
    fig_F()
    print("[done] 6 figs ->", OUT)
