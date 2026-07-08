#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
plot_rerun_9mer.py

服务：QuantImmuBench §3.1 单工具 max-pooling 零选择基线 —— 用昨天改动②③（原始蛋白
      定点切含突变窗）重跑的 9mer 数，复刻上一版对比 PPT 的两张图。

lever：§3.1 单工具 max ρ̄（per-patient Spearman → effN>=8 门槛 → Fisher-Z 病人等权 → tanh）。

数据源（只读，列名已核实，两表 comment="#" 头）：
  - 新切 9mer（改动②③，主角）:
        analysis/official/recompute_effN/R1_recomputed_rerun_9mer_effN8.csv
        (102 SNV 肽 · 9 患者 · 原始蛋白定点切含突变窗 · 2026-07-08 重跑)
  - 旧 SLP 9mer（改动②前，对照）:
        analysis/official/recompute_effN/R1_recomputed_effN8.csv
        (130 SLP 疫苗肽切)
  两表列: Tool、fisherz_rho_effN、ci_lo、ci_hi、coverage_fail（bool）等。
  有效工具 = fisherz_rho_effN 非 NaN 且 coverage_fail=False。
  新切表 DeepNetBim(max 饱和退化, coverage_fail=True) / NeoaPred(已剔, 无列/NaN) 不入排序。

产物（PNG dpi>=200 + PDF，各写两处目录 figures/ 与 paper/figures/）：
  主图: fig_rerun_9mer_maxpool_ranking          —— 28 有效工具横向 ρ̄ 排序条形（+95%CI 误差棒）
  次图: fig_rerun_9mer_newcut_vs_oldSLP_dumbbell —— 新切 vs 旧 SLP 逐工具哑铃对比

红线：本脚本【只写不跑】。所有数值（均值、计数、升降判定）一律从 csv 现算，零硬编码。
      禁 scipy（画图纯 numpy/pandas）。
主线跑：  python analysis/official/recompute_effN/plot_rerun_9mer.py [--dpi 300]
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

CSV_NEW = SCRIPT_DIR / "R1_recomputed_rerun_9mer_effN8.csv"   # 新切 9mer（主角）
CSV_OLD = SCRIPT_DIR / "R1_recomputed_effN8.csv"              # 旧 SLP 9mer（对照）
OUT_DIRS = [SCRIPT_DIR / "figures", ROOT / "paper" / "figures"]

# ---- 学术配色（Okabe-Ito 色盲友好，沿用姊妹脚本习惯）----
COLOR_POS = "#0072B2"    # 深蓝：ρ̄ > 0
COLOR_NEG = "#E69F00"    # 橙：ρ̄ < 0
COLOR_NA = "#BBBBBB"     # 灰：N/A（DeepNetBim / NeoaPred，不入排序）
COLOR_MEAN = "#D55E00"   # vermillion：均值线
# 哑铃
COLOR_NEW = "#0072B2"    # 深蓝实心：新切 9mer
COLOR_OLD = "#E69F00"    # 橙空心：旧 SLP 9mer
COLOR_UP = "#009E73"     # 绿连线：新切 > 旧（排序能力升）
COLOR_DOWN = "#D55E00"   # vermillion 连线：新切 < 旧（降）


def _covfail_mask(series):
    """稳健解析 coverage_fail 为 bool（pandas 可能推成 bool 或 object/str）。"""
    import pandas as pd
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


# ============================ 主图：排序条形 ============================
def make_ranking(dpi):
    """28 有效工具 9mer 新切 ρ̄ 横向条形排序 + 95%CI；DeepNetBim/NeoaPred 标 N/A 置底。"""
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    import numpy as np

    df, valid = load_table(CSV_NEW)
    valid = valid.sort_values("fisherz_rho_effN", ascending=False).reset_index(drop=True)

    # N/A 工具（coverage_fail=True 或 rho=NaN）——DeepNetBim / NeoaPred
    na = df[df["fisherz_rho_effN"].isna() | df["_covfail"]].copy()

    tools = valid["Tool"].tolist()
    vals = valid["fisherz_rho_effN"].to_numpy()
    lo = valid["ci_lo"].to_numpy()
    hi = valid["ci_hi"].to_numpy()
    n_valid = len(tools)
    mean_val = float(vals.mean())  # 28 有效工具均值（现算，零硬编码）

    na_tools = na["Tool"].tolist()
    n_na = len(na_tools)
    n_rows = n_valid + n_na

    # y 位置：降序 => 顶部最高；有效在上，N/A 置底
    y_valid = np.arange(n_rows - 1, n_na - 1, -1)  # 顶部起
    y_na = np.arange(n_na - 1, -1, -1)             # 底部区

    colors = [COLOR_POS if v >= 0 else COLOR_NEG for v in vals]
    # 误差棒相对长度（防负）
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
    # N/A 标签置灰
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
        "（9mer 新切肽口径 · effN$\\geq$8 · 病人等权 Fisher-Z）",
        fontsize=12.5, pad=10,
    )
    ax.grid(axis="x", linestyle=":", color="0.82", linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)

    # 图例
    handles = [
        Patch(facecolor=COLOR_POS, label="$\\bar{\\rho}$ > 0"),
        Patch(facecolor=COLOR_NEG, label="$\\bar{\\rho}$ < 0"),
        Patch(facecolor=COLOR_NA, label="N/A（DeepNetBim max 饱和 / NeoaPred 已剔）"),
    ]
    ax.legend(handles=handles, loc="lower right", fontsize=8.5, frameon=True, framealpha=0.92)

    # 副标/脚注
    fig.text(
        0.01, 0.005,
        "改动②③新切肽口径 · 102 SNV 肽 · 9 患者 · 数据 2026-07-08 重跑；"
        "误差棒=cluster-bootstrap 95%CI；DeepNetBim(max 饱和)/NeoaPred(已剔) 不入排序。"
        f" 有效工具 n={n_valid}，均值 ρ̄={mean_val:.3f}。"
        " 数据源：R1_recomputed_rerun_9mer_effN8.csv。",
        fontsize=6.6, color="0.4",
    )
    fig.subplots_adjust(left=0.16, right=0.965, top=0.93, bottom=0.09)

    outs = _save(fig, "fig_rerun_9mer_maxpool_ranking", dpi)

    # ---- print 关键值供主线核 ----
    print(f"[ranking] valid tools = {n_valid}, N/A = {n_na}: {na_tools}")
    print(f"[ranking] mean rho (valid) = {mean_val:.4f}")
    print("[ranking] top3:")
    for i in range(min(3, n_valid)):
        print(f"    {tools[i]:<16s} rho={vals[i]:.4f}  CI[{lo[i]:.3f},{hi[i]:.3f}]")
    print(f"[ranking] saved -> {'; '.join(str(p) for p in outs)}")
    return mean_val, n_valid


# ============================ 次图：哑铃对比 ============================
def _draw_dumbbell(ax, sub, xlim):
    """哑铃行：左点=旧 SLP（v_old），右点=新切（v_new），连线按升降异色。sub 已按新切降序。"""
    import numpy as np
    tools = sub["Tool"].tolist()
    vnew = sub["v_new"].to_numpy()
    vold = sub["v_old"].to_numpy()
    n = len(tools)
    y = np.arange(n)[::-1]  # 降序 => 最高置顶
    off = 0.006

    for i in range(n):
        yy = y[i]
        xn, xo = float(vnew[i]), float(vold[i])
        is_up = xn > xo  # 新切 > 旧 SLP（排序能力升）
        lc = COLOR_UP if is_up else COLOR_DOWN
        lw = 2.2 if is_up else 2.2
        ax.plot([xo, xn], [yy, yy], color=lc, lw=lw, solid_capstyle="round", zorder=1)
        # 旧 SLP：橙空心
        ax.scatter([xo], [yy], s=46, facecolor="white", edgecolor=COLOR_OLD,
                   linewidth=1.6, zorder=3)
        # 新切：蓝实心
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
    """新切 9mer vs 旧 SLP 9mer 逐工具哑铃：只画两侧都有效的工具，按新切降序。"""
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    import numpy as np

    _, vnew = load_table(CSV_NEW)
    _, vold = load_table(CSV_OLD)
    a = vnew[["Tool", "fisherz_rho_effN"]].rename(columns={"fisherz_rho_effN": "v_new"})
    b = vold[["Tool", "fisherz_rho_effN"]].rename(columns={"fisherz_rho_effN": "v_old"})
    merged = a.merge(b, on="Tool", how="inner").dropna(subset=["v_new", "v_old"])
    merged = merged.sort_values("v_new", ascending=False).reset_index(drop=True)

    n = len(merged)
    vn = merged["v_new"].to_numpy()
    vo = merged["v_old"].to_numpy()
    mean_new = float(vn.mean())
    mean_old = float(vo.mean())
    n_up = int((vn > vo).sum())
    n_down = int((vn < vo).sum())

    v_all = np.concatenate([vn, vo])
    pad = 0.09
    xlim = (float(v_all.min()) - pad, float(v_all.max()) + pad)

    fig, ax = plt.subplots(figsize=(11.0, max(7.5, 0.36 * n + 2.0)))
    fig.subplots_adjust(left=0.185, right=0.965, top=0.905, bottom=0.135)
    _draw_dumbbell(ax, merged, xlim)

    ax.set_xlabel("Per-patient Spearman $\\bar{\\rho}$"
                  "（Fisher-z 病人等权，患者内 effN$\\geq$8）", fontsize=11)
    ax.set_title(
        "9mer 新切肽 vs 旧 SLP 切肽：改动②去肽长混杂后单工具排序能力变化",
        fontsize=12.5, pad=8,
    )

    # 图例（左上，空区不压点）
    handles = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor=COLOR_NEW,
               markeredgecolor="white", markersize=9, label="新切 9mer（实心蓝）"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="white",
               markeredgecolor=COLOR_OLD, markeredgewidth=1.6, markersize=9,
               label="旧 SLP 9mer（空心橙）"),
        Line2D([0], [0], color=COLOR_UP, lw=2.6, label=f"新切 > 旧（升，{n_up}）"),
        Line2D([0], [0], color=COLOR_DOWN, lw=2.6, label=f"新切 < 旧（降，{n_down}）"),
    ]
    ax.legend(handles=handles, loc="upper left", fontsize=8.5, frameon=True,
              framealpha=0.92, borderpad=0.6, handlelength=1.6)

    # 均值统计框（右下）
    stats_txt = (
        f"旧 SLP 均值 $\\bar{{\\rho}}$ = {mean_old:.3f}    |    "
        f"新切 均值 $\\bar{{\\rho}}$ = {mean_new:.3f}\n"
        f"逐工具对比 n = {n}（两侧均有效）"
    )
    ax.text(0.985, 0.02, stats_txt, transform=ax.transAxes,
            ha="right", va="bottom", fontsize=8.5, color="0.15",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="white",
                      edgecolor="0.7", alpha=0.92))

    # caveat 文字框（显著，顶部居中偏右）
    caveat = ("⚠️ 新切=102 SNV 肽（原始蛋白定点切） · 旧 SLP=130 肽（疫苗肽切） · "
              "肽集不同，仅作趋势示意非严格同集对照")
    fig.text(0.5, 0.055, caveat, ha="center", va="center", fontsize=8.2,
             color="#8A3B00", fontweight="bold",
             bbox=dict(boxstyle="round,pad=0.5", facecolor="#FFF3E0",
                       edgecolor="#E69F00", linewidth=1.2, alpha=0.96))

    fig.text(
        0.5, 0.012,
        "数据源：R1_recomputed_rerun_9mer_effN8.csv（新切）+ R1_recomputed_effN8.csv（旧 SLP）；"
        "per-patient Spearman ρ̄，患者内 effN≥8 的 Fisher-z 病人等权均值。",
        ha="center", fontsize=6.6, color="0.4",
    )

    outs = _save(fig, "fig_rerun_9mer_newcut_vs_oldSLP_dumbbell", dpi)

    # ---- print 关键值供主线核 ----
    print(f"[dumbbell] tools (both valid) = {n}  mean_new={mean_new:.4f} mean_old={mean_old:.4f}")
    print(f"[dumbbell] 新切>旧: {n_up}  新切<旧: {n_down}")
    print("[dumbbell] top3 by new:")
    for i in range(min(3, n)):
        print(f"    {merged['Tool'].iloc[i]:<16s} new={vn[i]:.4f} old={vo[i]:.4f}")
    print(f"[dumbbell] saved -> {'; '.join(str(p) for p in outs)}")
    return mean_new, mean_old, n


def main():
    ap = argparse.ArgumentParser(
        description="QuantImmuBench §3.1 新切 9mer max-pool 排序 + 新旧哑铃对比图")
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
    print("[done] both figures written (script did NOT execute training/model code).")


if __name__ == "__main__":
    main()
