#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
plot_8to11_rerun_figs.py

服务：QuantImmuBench §2.2 / §3.1 —— 8-11mer 可变窗口径补充口径出图（重做，专业级）。
      现有 8-11mer 对比图太长、配色乱，本脚本严格复用姊妹脚本 plot_rerun_9mer.py 的
      Okabe-Ito 配色 + 绘图手法重画 3 张图。

lever：§3.1 单工具 max ρ̄（per-patient Spearman → effN>=8 门槛 → Fisher-Z 病人等权 → tanh），
       口径 = 改动②③ 8-11mer 可变窗（原始蛋白定点切含突变窗，8/9/10/11mer 全长）。

数据源（只读，列名已核实）：
  - 8-11mer 新切（主角，comment="#" 头）:
        analysis/official/recompute_effN/R1_recomputed_rerun_8to11mer_effN8.csv
  - 9mer 新切（对照，comment="#" 头）:
        analysis/official/recompute_effN/R1_recomputed_rerun_9mer_effN8.csv
    两表列: Tool、fisherz_rho_effN、ci_lo、ci_hi、n_full、coverage_fail(bool) 等（30 工具）。
    有效工具 = fisherz_rho_effN 非 NaN 且 coverage_fail=False。
  - 子肽层覆盖（长表）:
        data/frozen/coverage_matrix.NEW.csv
        列: mut_key,subpep_seq,hla_allele_std,side,tool,status
        覆盖率 = MT 侧 status=='scored' 占比（分母=该工具 MT 行数，满覆盖 17088）。

产物（PNG dpi>=200 + PDF，各写两处目录 figures/ 与 paper/figures/）：
  图1: fig_8to11_ranking             —— 8-11mer 单工具 ρ̄ 横向排序条形（+95%CI 误差棒）
  图2: fig_8to11_vs_9mer_dumbbell    —— 9mer vs 8-11mer 逐工具哑铃，1×2 上/下半分栏（治太长）
  图3: fig_8to11_coverage            —— 子肽层 MT 侧覆盖横向条形（满覆盖绿 / 上限橙）

红线：本脚本【只写不跑】。所有数值（均值、计数、升降判定、覆盖率）一律从 csv 现算，零硬编码。
      禁 scipy（画图纯 numpy/pandas）。
主线跑：  python analysis/official/recompute_effN/plot_8to11_rerun_figs.py [--dpi 300]
"""
import argparse
import sys
from pathlib import Path


# ---- Windows UTF-8 stdout（防中文 print 乱码；放 __main__ 前的顶层安全） ----
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


# ---- 路径（脚本在 analysis/official/recompute_effN/，项目根=parents[2]）----
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]  # recompute_effN -> official -> analysis -> <ROOT>

CSV_811 = SCRIPT_DIR / "R1_recomputed_rerun_8to11mer_effN8.csv"  # 8-11mer 新切（主角）
CSV_9MER = SCRIPT_DIR / "R1_recomputed_rerun_9mer_effN8.csv"     # 9mer 新切（对照）
CSV_COV = ROOT / "data" / "frozen" / "coverage_matrix.NEW.csv"   # 子肽层覆盖长表
FULL_COV = 17088  # 满覆盖 MT 行数（子肽×HLA 位点层，脚注说明）
OUT_DIRS = [SCRIPT_DIR / "figures", ROOT / "paper" / "figures"]

# ---- 学术配色（Okabe-Ito 色盲友好，严格沿用 plot_rerun_9mer.py）----
COLOR_POS = "#0072B2"    # 深蓝：ρ̄ > 0
COLOR_NEG = "#E69F00"    # 橙：ρ̄ < 0
COLOR_NA = "#BBBBBB"     # 灰：N/A（不入排序）
COLOR_MEAN = "#D55E00"   # vermillion：均值线
# 哑铃
COLOR_NEW = "#0072B2"    # 深蓝实心：8-11mer 新切
COLOR_OLD = "#E69F00"    # 橙空心：9mer 新切
COLOR_UP = "#009E73"     # 绿连线：8-11 > 9mer（排序能力升）
COLOR_DOWN = "#D55E00"   # vermillion 连线：8-11 < 9mer（降）


def _covfail_mask(series):
    """稳健解析 coverage_fail 为 bool（pandas 可能推成 bool 或 object/str）。"""
    import pandas as pd  # noqa: F401
    if series.dtype == bool:
        return series.fillna(False)
    return series.astype(str).str.strip().str.lower().isin(["true", "1"])


def load_table(csv_path):
    """读单表，返回全 df + 有效子集（rho 非 NaN 且 coverage_fail=False）。"""
    import pandas as pd
    df = pd.read_csv(csv_path, comment="#")
    df["_covfail"] = _covfail_mask(df["coverage_fail"])
    valid = df[df["fisherz_rho_effN"].notna() & (~df["_covfail"])].copy()
    return df, valid


def _save(fig, stem, dpi):
    """写两处目录（PNG + PDF），不用 bbox_inches='tight' 保精确纵横比。"""
    import matplotlib.pyplot as plt
    outs = []
    for d in OUT_DIRS:
        d.mkdir(parents=True, exist_ok=True)
        png = d / f"{stem}.png"
        pdf = d / f"{stem}.pdf"
        fig.savefig(png, dpi=dpi)
        fig.savefig(pdf)
        outs.append(png)
    plt.close(fig)
    return outs


# ============================ 图1：8-11mer 排序条形 ============================
def make_ranking(dpi):
    """8-11mer 有效工具 ρ̄ 横向条形排序 + 95%CI；coverage_fail / NaN 工具标 N/A 置底。"""
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    import numpy as np

    df, valid = load_table(CSV_811)
    valid = valid.sort_values("fisherz_rho_effN", ascending=False).reset_index(drop=True)

    # N/A 工具（coverage_fail=True 或 rho=NaN）
    na = df[df["fisherz_rho_effN"].isna() | df["_covfail"]].copy()

    tools = valid["Tool"].tolist()
    vals = valid["fisherz_rho_effN"].to_numpy()
    lo = valid["ci_lo"].to_numpy()
    hi = valid["ci_hi"].to_numpy()
    n_valid = len(tools)
    mean_val = float(vals.mean())  # 有效工具均值（现算，零硬编码）

    na_tools = na["Tool"].tolist()
    n_na = len(na_tools)
    n_rows = n_valid + n_na

    # y 位置：降序 => 顶部最高；有效在上，N/A 置底
    y_valid = np.arange(n_rows - 1, n_na - 1, -1)  # 顶部起
    y_na = np.arange(n_na - 1, -1, -1)             # 底部区

    colors = [COLOR_POS if v >= 0 else COLOR_NEG for v in vals]
    xerr = np.vstack([np.clip(vals - lo, 0, None), np.clip(hi - vals, 0, None)])

    fig, ax = plt.subplots(figsize=(12.0, max(7.0, 0.40 * n_rows + 1.8)))
    ax.barh(y_valid, vals, height=0.66, color=colors, edgecolor="white", linewidth=0.3, zorder=2)
    ax.errorbar(vals, y_valid, xerr=xerr, fmt="none", ecolor="0.35",
                elinewidth=1.0, capsize=2.6, zorder=3)

    # 数值标签：正条标 ci_hi 右侧、负条标 ci_lo 左侧，避开误差棒
    off = 0.010
    for yi, v, l, h in zip(y_valid, vals, lo, hi):
        if v >= 0:
            ax.text(h + off, yi, f"{v:.3f}", va="center", ha="left",
                    fontsize=7, color=COLOR_POS, fontweight="bold", zorder=5)
        else:
            ax.text(l - off, yi, f"{v:.3f}", va="center", ha="right",
                    fontsize=7, color=COLOR_NEG, fontweight="bold", zorder=5)

    # N/A 行：零长条 + 文字
    for yi, t in zip(y_na, na_tools):
        ax.text(0.0 + off, yi, "N/A（不入排序）", va="center", ha="left",
                fontsize=7.5, color="0.45", style="italic", zorder=5)

    # 零线 + 均值线
    ax.axvline(0.0, color="0.35", linestyle="--", linewidth=1.0, zorder=1)
    ax.axvline(mean_val, color=COLOR_MEAN, linestyle="-", linewidth=1.4, zorder=1)
    ax.text(mean_val, n_rows - 0.3, f"均值 $\\bar{{\\rho}}$ = {mean_val:.3f}",
            ha="center", va="bottom", fontsize=9, color=COLOR_MEAN, fontweight="bold")

    # 轴
    y_all = np.concatenate([y_valid, y_na])
    labels_all = tools + [f"{t}" for t in na_tools]
    ax.set_yticks(y_all)
    ax.set_yticklabels(labels_all, fontsize=8.5)
    for tick, yi in zip(ax.get_yticklabels(), y_all):
        if yi in set(y_na.tolist()):
            tick.set_color("0.5")
    ax.set_ylim(-0.7, n_rows + 0.2)

    vmin = float(min(lo.min(), 0.0))
    vmax = float(max(hi.max(), mean_val))
    ax.set_xlim(vmin - 0.10, vmax + 0.10)
    ax.set_xlabel("Per-patient Spearman $\\bar{\\rho}$"
                  "（Fisher-z 病人等权，患者内 effN$\\geq$8）", fontsize=11)
    ax.set_title(
        "§3.1 单工具 max-pooling per-patient Spearman $\\bar{\\rho}$"
        "（8–11mer 可变窗口径 · effN$\\geq$8 · 病人等权 Fisher-Z）",
        fontsize=12.5, pad=10,
    )
    ax.grid(axis="x", linestyle=":", color="0.82", linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)

    # 图例
    handles = [
        Patch(facecolor=COLOR_POS, label="$\\bar{\\rho}$ > 0"),
        Patch(facecolor=COLOR_NEG, label="$\\bar{\\rho}$ < 0"),
        Patch(facecolor=COLOR_NA, label="N/A（coverage_fail / 长度受限 NaN，不入排序）"),
    ]
    ax.legend(handles=handles, loc="lower right", fontsize=8.5, frameon=True, framealpha=0.92)

    # 副标/脚注
    fig.text(
        0.01, 0.005,
        "改动②③ 8–11mer 可变窗口径（原始蛋白定点切含突变窗，8/9/10/11mer 全长）· "
        "误差棒=cluster-bootstrap 95%CI；coverage_fail / 长度受限 NaN 工具不入排序。"
        f" 有效工具 n={n_valid}，均值 ρ̄={mean_val:.3f}。"
        " 数据源：R1_recomputed_rerun_8to11mer_effN8.csv。",
        fontsize=6.6, color="0.4",
    )
    fig.subplots_adjust(left=0.16, right=0.965, top=0.93, bottom=0.09)

    outs = _save(fig, "fig_8to11_ranking", dpi)

    # ---- print 关键值供主线核 ----
    print(f"[ranking] valid tools = {n_valid}, N/A = {n_na}: {na_tools}")
    print(f"[ranking] mean rho (valid) = {mean_val:.4f}")
    print("[ranking] top3:")
    for i in range(min(3, n_valid)):
        print(f"    {tools[i]:<16s} rho={vals[i]:.4f}  CI[{lo[i]:.3f},{hi[i]:.3f}]")
    print(f"[ranking] figsize = (12.0, {max(7.0, 0.40 * n_rows + 1.8):.2f})")
    print(f"[ranking] saved -> {'; '.join(str(p) for p in outs)}")
    return mean_val, n_valid


# ============================ 图2：哑铃对比（1×2 分栏） ============================
def _draw_dumbbell(ax, sub, xlim):
    """哑铃行：左点=9mer(v_old 空心橙)，右点=8-11(v_new 实心蓝)，连线按升降异色。
    sub 已按 9mer(v_old) 降序。升=8-11>9mer(绿) / 降=8-11<9mer(橙红)。"""
    import numpy as np
    tools = sub["Tool"].tolist()
    vnew = sub["v_new"].to_numpy()   # 8-11mer
    vold = sub["v_old"].to_numpy()   # 9mer
    n = len(tools)
    y = np.arange(n)[::-1]  # 降序 => 最高置顶
    off = 0.006

    for i in range(n):
        yy = y[i]
        xn, xo = float(vnew[i]), float(vold[i])
        is_up = xn > xo  # 8-11 > 9mer（排序能力升）
        lc = COLOR_UP if is_up else COLOR_DOWN
        ax.plot([xo, xn], [yy, yy], color=lc, lw=2.2, solid_capstyle="round", zorder=1)
        # 9mer：橙空心
        ax.scatter([xo], [yy], s=46, facecolor="white", edgecolor=COLOR_OLD,
                   linewidth=1.6, zorder=3)
        # 8-11mer：蓝实心
        ax.scatter([xn], [yy], s=46, color=COLOR_NEW, edgecolor="white",
                   linewidth=0.5, zorder=4)
        # 数值标注：右点朝右、左点朝左
        if xn >= xo:
            ax.text(xn + off, yy, f"{xn:.3f}", ha="left", va="center",
                    fontsize=6.8, color=COLOR_NEW, fontweight="bold", zorder=5)
            ax.text(xo - off, yy, f"{xo:.3f}", ha="right", va="center",
                    fontsize=6.8, color=COLOR_OLD, zorder=5)
        else:
            ax.text(xo + off, yy, f"{xo:.3f}", ha="left", va="center",
                    fontsize=6.8, color=COLOR_OLD, fontweight="bold", zorder=5)
            ax.text(xn - off, yy, f"{xn:.3f}", ha="right", va="center",
                    fontsize=6.8, color=COLOR_NEW, zorder=5)

    ax.axvline(0.0, color="0.45", linestyle="--", linewidth=0.9, zorder=0)
    ax.set_yticks(y)
    ax.set_yticklabels(tools, fontsize=9)
    ax.set_ylim(-0.6, n - 0.4)
    ax.set_xlim(*xlim)
    ax.grid(axis="x", linestyle=":", color="0.82", linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)


def make_dumbbell(dpi):
    """9mer vs 8-11mer 逐工具哑铃：只画两侧都有效的工具，按 9mer 降序，上/下半分两栏。"""
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    import numpy as np

    _, v811 = load_table(CSV_811)
    _, v9 = load_table(CSV_9MER)
    a = v811[["Tool", "fisherz_rho_effN"]].rename(columns={"fisherz_rho_effN": "v_new"})  # 8-11
    b = v9[["Tool", "fisherz_rho_effN"]].rename(columns={"fisherz_rho_effN": "v_old"})    # 9mer
    merged = a.merge(b, on="Tool", how="inner").dropna(subset=["v_new", "v_old"])
    # 按 9mer(v_old) 降序 —— 分栏与排序基准均以 9mer 为准
    merged = merged.sort_values("v_old", ascending=False).reset_index(drop=True)

    n = len(merged)
    vn = merged["v_new"].to_numpy()  # 8-11
    vo = merged["v_old"].to_numpy()  # 9mer
    mean_811 = float(vn.mean())
    mean_9 = float(vo.mean())
    n_9_gt = int((vo > vn).sum())    # 9mer > 8-11
    n_up = int((vn > vo).sum())      # 8-11 > 9mer（升）
    n_down = int((vn < vo).sum())    # 8-11 < 9mer（降）

    # 分栏：前一半 / 后一半（按 9mer 降序）
    half = (n + 1) // 2
    left = merged.iloc[:half].reset_index(drop=True)   # 上半
    right = merged.iloc[half:].reset_index(drop=True)  # 下半

    # 两子图共享 x 轴范围（便于比较）
    v_all = np.concatenate([vn, vo])
    pad = 0.09
    xlim = (float(v_all.min()) - pad, float(v_all.max()) + pad)

    rows_per_col = max(len(left), len(right))
    fig, axes = plt.subplots(1, 2, figsize=(15.5, max(7.5, 0.42 * rows_per_col + 2.4)))
    fig.subplots_adjust(left=0.095, right=0.975, top=0.885, bottom=0.135, wspace=0.34)

    _draw_dumbbell(axes[0], left, xlim)
    _draw_dumbbell(axes[1], right, xlim)
    axes[0].set_title(f"上半（按 9mer 降序 · 第 1–{len(left)} 名）", fontsize=10.5, pad=6)
    axes[1].set_title(f"下半（第 {len(left) + 1}–{n} 名）", fontsize=10.5, pad=6)
    for ax in axes:
        ax.set_xlabel("Per-patient Spearman $\\bar{\\rho}$"
                      "（Fisher-z 病人等权，effN$\\geq$8）", fontsize=10)

    fig.suptitle(
        "9mer 新切 vs 8–11mer 可变窗：逐工具排序能力变化（按 9mer 降序，上半 / 下半分栏）",
        fontsize=13.5, y=0.965,
    )

    # 图例（整图一处，放左子图空区，不每栏重复）
    handles = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor=COLOR_NEW,
               markeredgecolor="white", markersize=9, label="8–11mer 可变窗（实心蓝）"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="white",
               markeredgecolor=COLOR_OLD, markeredgewidth=1.6, markersize=9,
               label="9mer 新切（空心橙）"),
        Line2D([0], [0], color=COLOR_UP, lw=2.6, label=f"8–11 > 9mer（升，{n_up}）"),
        Line2D([0], [0], color=COLOR_DOWN, lw=2.6, label=f"8–11 < 9mer（降，{n_down}）"),
    ]
    axes[0].legend(handles=handles, loc="lower left", fontsize=8.2, frameon=True,
                   framealpha=0.92, borderpad=0.6, handlelength=1.6)

    # 均值统计框（右子图右下）
    stats_txt = (
        f"9mer 均值 $\\bar{{\\rho}}$ = {mean_9:.3f}    |    "
        f"8–11mer 均值 $\\bar{{\\rho}}$ = {mean_811:.3f}\n"
        f"9mer > 8–11mer：{n_9_gt}/{n}（逐工具，两侧均有效）"
    )
    axes[1].text(0.985, 0.02, stats_txt, transform=axes[1].transAxes,
                 ha="right", va="bottom", fontsize=8.5, color="0.15",
                 bbox=dict(boxstyle="round,pad=0.5", facecolor="white",
                           edgecolor="0.7", alpha=0.92))

    # caption box（底部居中）
    caption = ("MHCnuggets 是唯一 8–11 略升的工具；MHCseqNet / ImmuGenX 翻负 = "
               "非 9mer 窗抢走 max-pool 的真实信号")
    fig.text(0.5, 0.052, caption, ha="center", va="center", fontsize=8.4,
             color="#8A3B00", fontweight="bold",
             bbox=dict(boxstyle="round,pad=0.5", facecolor="#FFF3E0",
                       edgecolor="#E69F00", linewidth=1.2, alpha=0.96))

    fig.text(
        0.5, 0.012,
        "数据源：R1_recomputed_rerun_8to11mer_effN8.csv（8–11mer）+ "
        "R1_recomputed_rerun_9mer_effN8.csv（9mer）；"
        "per-patient Spearman ρ̄，患者内 effN≥8 的 Fisher-z 病人等权均值。",
        ha="center", fontsize=6.6, color="0.4",
    )

    outs = _save(fig, "fig_8to11_vs_9mer_dumbbell", dpi)

    # ---- print 关键值供主线核 ----
    print(f"[dumbbell] tools (both valid) = {n}  mean_9mer={mean_9:.4f} mean_8to11={mean_811:.4f}")
    print(f"[dumbbell] 9mer>8-11: {n_9_gt}/{n}  (8-11升 {n_up}, 8-11降 {n_down})")
    print(f"[dumbbell] split: 上半 {len(left)} / 下半 {len(right)}")
    print("[dumbbell] top3 by 9mer:")
    for i in range(min(3, n)):
        print(f"    {merged['Tool'].iloc[i]:<16s} 9mer={vo[i]:.4f} 8-11={vn[i]:.4f}")
    print(f"[dumbbell] figsize = (15.5, {max(7.5, 0.42 * rows_per_col + 2.4):.2f})")
    print(f"[dumbbell] saved -> {'; '.join(str(p) for p in outs)}")
    return mean_9, mean_811, n, n_9_gt


# ============================ 图3：子肽层覆盖 ============================
def make_coverage(dpi):
    """每工具 MT 侧 status=='scored' 占比横向条形；满覆盖绿 / 上限橙，降序。"""
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    import pandas as pd
    import numpy as np

    cov = pd.read_csv(CSV_COV, usecols=["side", "tool", "status"])
    mt = cov[cov["side"] == "MT"]
    grp = mt.groupby("tool")["status"]
    tot = grp.size()
    scored = grp.apply(lambda s: (s == "scored").sum())
    frac = (scored / tot).sort_values(ascending=False)

    tools = frac.index.tolist()
    fr = frac.to_numpy()
    sc = scored.reindex(tools).to_numpy()
    tt = tot.reindex(tools).to_numpy()
    n_tools = len(tools)
    n_full = int((fr >= 0.999999).sum())  # 满覆盖工具数（浮点稳健）

    y = np.arange(n_tools - 1, -1, -1)  # 降序 => 顶部最高
    colors = [COLOR_UP if f >= 0.999999 else COLOR_NEG for f in fr]

    fig, ax = plt.subplots(figsize=(11.0, max(7.0, 0.40 * n_tools + 1.6)))
    ax.barh(y, fr * 100.0, height=0.66, color=colors, edgecolor="white",
            linewidth=0.3, zorder=2)

    # 数值标签：满覆盖简写，不满标 76.8% (13119/17088)
    for yi, f, s, t in zip(y, fr, sc, tt):
        if f >= 0.999999:
            txt = f"100% ({int(s)}/{int(t)})"
            col = COLOR_UP
        else:
            txt = f"{f * 100:.1f}% ({int(s)}/{int(t)})"
            col = "#8A3B00"
        ax.text(f * 100.0 + 0.8, yi, txt, va="center", ha="left",
                fontsize=7, color=col, fontweight="bold", zorder=5)

    ax.axvline(100.0, color="0.35", linestyle="--", linewidth=1.0, zorder=1)
    ax.set_yticks(y)
    ax.set_yticklabels(tools, fontsize=8.5)
    ax.set_ylim(-0.7, n_tools + 0.2)
    ax.set_xlim(0, 118)
    ax.set_xlabel("MT 侧子肽×HLA 位点覆盖率（status=='scored' 占比，%）", fontsize=11)
    ax.set_title(
        f"8–11mer 子肽层 MT 侧覆盖：{n_full}/{n_tools} 工具满覆盖，"
        f"{n_tools - n_full} 个诚实上限",
        fontsize=12.5, pad=10,
    )
    ax.grid(axis="x", linestyle=":", color="0.82", linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)

    handles = [
        Patch(facecolor=COLOR_UP, label=f"满覆盖 100%（{n_full} 工具）"),
        Patch(facecolor=COLOR_NEG, label=f"<100%（诚实上限，{n_tools - n_full} 工具）"),
    ]
    ax.legend(handles=handles, loc="lower right", fontsize=8.5, frameon=True, framealpha=0.92)

    fig.text(
        0.01, 0.005,
        "覆盖率 = MT 侧 status=='scored' 行数 / 该工具 MT 总行数（满覆盖=17088）。"
        " 统计层 = 子肽×HLA 位点层，非 mut_key 层 max-pool"
        "（后者会误显全 102 满覆盖，掩盖工具真实适用面）。"
        " 数据源：data/frozen/coverage_matrix.NEW.csv。",
        fontsize=6.6, color="0.4",
    )
    fig.subplots_adjust(left=0.16, right=0.965, top=0.93, bottom=0.09)

    outs = _save(fig, "fig_8to11_coverage", dpi)

    # ---- print 关键值供主线核 ----
    print(f"[coverage] tools = {n_tools}, 满覆盖 = {n_full}, 上限 = {n_tools - n_full}")
    check = ["HLAthena", "NetTepi", "DeepImmuno", "DeepNetBim", "ICERFIRE"]
    for t in check:
        if t in frac.index:
            f = float(frac.loc[t])
            s = int(scored.loc[t])
            n_ = int(tot.loc[t])
            print(f"    {t:<12s} {f * 100:5.1f}% ({s}/{n_})")
    print(f"[coverage] figsize = (11.0, {max(7.0, 0.40 * n_tools + 1.6):.2f})")
    print(f"[coverage] saved -> {'; '.join(str(p) for p in outs)}")
    return n_tools, n_full


def main():
    ap = argparse.ArgumentParser(
        description="QuantImmuBench 8-11mer 可变窗：排序 + 9mer 哑铃对比 + 子肽层覆盖 3 图")
    ap.add_argument("--dpi", type=int, default=300, help="raster dpi for png (default 300, >=200)")
    args = ap.parse_args()

    import matplotlib
    matplotlib.use("Agg")  # Windows 无 GUI 后端
    import matplotlib.pyplot as plt
    # 中文字体 + 负号防豆腐（rcParams 需在 pyplot 导入后设）
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    for d in OUT_DIRS:
        print(f"[out] -> {d}")
    make_ranking(args.dpi)
    make_dumbbell(args.dpi)
    make_coverage(args.dpi)
    print("[done] 3 figures written (script did NOT execute training/model code).")


if __name__ == "__main__":
    main()
