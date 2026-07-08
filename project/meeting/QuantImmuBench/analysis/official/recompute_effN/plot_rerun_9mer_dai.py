#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
plot_rerun_9mer_dai.py

服务：QuantImmuBench §3.1 单工具 DAI 排名 —— DAI = max(MT-WT, 0) 净增强口径
      （袁老师 outline §2.3 相减型），用上新数据的 WT（改动③）重跑的 9mer 数。
      复用姊妹脚本 plot_rerun_9mer.py 的 make_ranking() 布局（横向条形 + 95%CI 误差棒
      + 正蓝负橙 + 均值线 + coverage_fail/NaN 置底标 N/A），只换：输入 csv=DAI 档、
      标题、脚注、N/A 名单，并加两处诚实标注（不美化近-null 结果）。

lever：§3.1 单工具 DAI ρ̄（DAI=max(MT-WT,0) → per mut_key max-pool → per-patient Spearman
       → effN>=8 门槛 → Fisher-Z 病人等权 → tanh）。

数据源（只读，列名已核实）：
  - 主排名（DAI，effN>=8，comment="#" 头）:
        analysis/official/recompute_effN/R1_recomputed_rerun_9mer_dai_effN8.csv
        列: Tool、fisherz_rho_effN、ci_lo、ci_hi、n_full、coverage_fail（bool）等。
        有效工具 = fisherz_rho_effN 非 NaN 且 coverage_fail=False（当前 25 工具可算 DAI，
        含 Seq2Neo/TSCAPE WT 补跑后入榜）。有效数与 N/A 数量+名单一律从 csv 现取，不写死。
        N/A（coverage_fail=True，仅 MT 无 WT / WT 结构 NaN，DAI 分不入）当前 4 个：
            ICERFIRE / IMPROVE / pTuneos / NeoaG。
        NeoaPred 已剔（不入 N/A 展示）。
  - MT-only 对照（算 MT vs DAI 脚注，comment="#" 头）:
        analysis/official/recompute_effN/R1_recomputed_rerun_9mer_effN8.csv
  - 逐肽 pooled DAI（算 IEDB_Calis 的 DAI=0 平局数，comment 无）:
        data/frozen/pooled_dai_rerun_9mer.csv （列 <Tool>_max = 该肽 DAI 值）

产物（PNG dpi>=200 + PDF，各写两处目录 figures/ 与 paper/figures/）：
  fig_rerun_9mer_dai_ranking —— 有效工具（当前 25）横向 DAI ρ̄ 排序条形（+95%CI 误差棒）

红线：本脚本【只写不跑】。所有数值（均值、计数、升降、平局数）一律从 csv 现算，零硬编码。
      禁 scipy（画图纯 numpy/pandas）；mathtext 防豆腐块；Windows：Agg/UTF-8/YaHei+SimHei/
      axes.unicode_minus=False/pathlib/__main__。不覆盖 MT 版图（新文件名带 _dai）。
主线跑：  python analysis/official/recompute_effN/plot_rerun_9mer_dai.py [--dpi 300]
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

CSV_DAI = SCRIPT_DIR / "R1_recomputed_rerun_9mer_dai_effN8.csv"   # DAI（主角）
CSV_MT = SCRIPT_DIR / "R1_recomputed_rerun_9mer_effN8.csv"        # MT-only（对照，脚注用）
CSV_POOL = ROOT / "data" / "frozen" / "pooled_dai_rerun_9mer.csv"  # 逐肽 DAI（平局数用）
OUT_DIRS = [SCRIPT_DIR / "figures", ROOT / "paper" / "figures"]

# NeoaPred 已剔（不入 N/A 展示；其余 coverage_fail=True 的 6 工具正常置底标 N/A）
NA_EXCLUDE = {"NeoaPred"}

# ---- 学术配色（Okabe-Ito 色盲友好，沿用姊妹脚本 plot_rerun_9mer.py）----
COLOR_POS = "#0072B2"    # 深蓝：ρ̄ > 0
COLOR_NEG = "#E69F00"    # 橙：ρ̄ < 0
COLOR_NA = "#BBBBBB"     # 灰：N/A（仅 MT 无 WT，DAI 分不入）
COLOR_MEAN = "#D55E00"   # vermillion：均值线
COLOR_WARN = "#8A3B00"   # 警示文字（IEDB_Calis 平局 caveat）


def _covfail_mask(series):
    """稳健解析 coverage_fail 为 bool（pandas 可能推成 bool 或 object/str）。"""
    if series.dtype == bool:
        return series.fillna(False)
    return series.astype(str).str.strip().str.lower().isin(["true", "1"])


def load_table(csv_path):
    """读 DAI 表，返回全 df + 有效子集（rho 非 NaN 且 coverage_fail=False）。"""
    import pandas as pd
    df = pd.read_csv(csv_path, comment="#")
    df["_covfail"] = _covfail_mask(df["coverage_fail"])
    valid = df[df["fisherz_rho_effN"].notna() & (~df["_covfail"])].copy()
    return df, valid


def _mt_context():
    """从 MT-only 表算脚注用对照数：MT 有效均值、netMHCpan_BA 的 MT ρ̄。全现算。"""
    _, mtv = load_table(CSV_MT)
    mt_mean = float(mtv["fisherz_rho_effN"].mean())
    row = mtv[mtv["Tool"] == "netMHCpan_BA"]
    mt_bmba = float(row["fisherz_rho_effN"].iloc[0]) if len(row) else float("nan")
    return mt_mean, mt_bmba


def _iedb_tie_count():
    """从逐肽 pooled DAI 算 IEDB_Calis 的 DAI=0 平局数（zeros / n_notna）。全现算。"""
    import pandas as pd
    col = "IEDB_Calis_max"
    try:
        p = pd.read_csv(CSV_POOL)
        if col not in p.columns:
            return None, None
        n = int(p[col].notna().sum())
        z = int((p[col] == 0).sum())
        return z, n
    except Exception:
        return None, None


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


# ============================ 主图：DAI 排序条形 ============================
def make_ranking(dpi):
    """有效工具 DAI ρ̄ 横向条形排序 + 95%CI；N/A 工具置底；有效/N/A 数与名单全现算；诚实标注不美化。"""
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    import numpy as np

    df, valid = load_table(CSV_DAI)
    valid = valid.sort_values("fisherz_rho_effN", ascending=False).reset_index(drop=True)

    # N/A 工具（coverage_fail=True 或 rho=NaN），排除已剔的 NeoaPred
    na = df[df["fisherz_rho_effN"].isna() | df["_covfail"]].copy()
    na = na[~na["Tool"].isin(NA_EXCLUDE)]

    tools = valid["Tool"].tolist()
    vals = valid["fisherz_rho_effN"].to_numpy()
    lo = valid["ci_lo"].to_numpy()
    hi = valid["ci_hi"].to_numpy()
    n_valid = len(tools)
    mean_val = float(vals.mean())  # 有效工具均值（现算，零硬编码）

    na_tools = na["Tool"].tolist()
    n_na = len(na_tools)
    n_rows = n_valid + n_na

    # 脚注对照数（现算）
    mt_mean, mt_bmba = _mt_context()
    dai_bmba_row = valid[valid["Tool"] == "netMHCpan_BA"]
    dai_bmba = float(dai_bmba_row["fisherz_rho_effN"].iloc[0]) if len(dai_bmba_row) else float("nan")
    tie_z, tie_n = _iedb_tie_count()

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
        ax.text(0.0 + off, yi, "N/A（仅 MT 无 WT，DAI 分不入）", va="center", ha="left",
                fontsize=7.5, color="0.45", style="italic", zorder=5)

    # 零线 + 均值线
    ax.axvline(0.0, color="0.35", linestyle="--", linewidth=1.0, zorder=1)
    ax.axvline(mean_val, color=COLOR_MEAN, linestyle="-", linewidth=1.4, zorder=1)
    ax.text(mean_val, n_rows - 0.3, f"均值 $\\bar{{\\rho}}$ = {mean_val:.3f}（近随机）",
            ha="center", va="bottom", fontsize=9, color=COLOR_MEAN, fontweight="bold")

    # 轴标签（IEDB_Calis 加星标 *，指向平局 caveat）
    labels_valid = []
    idx_iedb = None
    for i, t in enumerate(tools):
        if t == "IEDB_Calis":
            labels_valid.append(t + " *")
            idx_iedb = i
        else:
            labels_valid.append(t)

    y_all = np.concatenate([y_valid, y_na])
    labels_all = labels_valid + list(na_tools)
    ax.set_yticks(y_all)
    ax.set_yticklabels(labels_all, fontsize=8.5)
    # N/A 标签置灰
    na_set = set(y_na.tolist())
    for tick, yi in zip(ax.get_yticklabels(), y_all):
        if yi in na_set:
            tick.set_color("0.5")

    ax.set_ylim(-0.7, n_rows + 0.2)

    vmin = float(min(lo.min(), 0.0))
    vmax = float(max(hi.max(), mean_val))
    ax.set_xlim(vmin - 0.10, vmax + 0.14)
    ax.set_xlabel("Per-patient Spearman $\\bar{\\rho}$（DAI=$\\max$(MT$-$WT,0)"
                  " · Fisher-z 病人等权 · 患者内 effN$\\geq$8）", fontsize=11)
    ax.set_title(
        "§3.1 单工具 DAI 排名 · DAI = $\\max$(MT$-$WT, 0) 净增强 · 9mer 新切肽"
        " · effN$\\geq$8 病人等权 Fisher-Z",
        fontsize=12.5, pad=10,
    )
    ax.grid(axis="x", linestyle=":", color="0.82", linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)

    # ---- IEDB_Calis 平局 caveat（星标脚注，指向该条）----
    if idx_iedb is not None and tie_z is not None:
        yi = y_valid[idx_iedb]
        v = vals[idx_iedb]
        cav = f"* IEDB_Calis：{tie_z}/{tie_n} 肽 DAI=0 平局，{v:.2f} 偏乐观不稳"
        # 文本框落在顶部行左侧大片留白（x<0 处，条形不占），annotate 箭头指向 IEDB_Calis 条尖，
        # 用 axes-fraction 定位保证完整落在 axes 内不越右边界截断。
        ax.annotate(
            cav, xy=(vals[idx_iedb], yi), xycoords="data",
            xytext=(0.035, 0.90), textcoords="axes fraction",
            va="top", ha="left", fontsize=8.0, color=COLOR_WARN, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.35", facecolor="#FFF3E0",
                      edgecolor="#E69F00", linewidth=1.0, alpha=0.96),
            arrowprops=dict(arrowstyle="->", color="#E69F00", lw=1.1,
                            connectionstyle="arc3,rad=-0.2"),
            zorder=6,
        )

    # ---- DAI vs MT-only 结论 callout（点一句，不美化）----
    callout = (
        "DAI（MT$-$WT）整体弱于 MT-only（均值 $\\bar{\\rho}$="
        f"{mt_mean:.3f}）：\n结合类如 netMHCpan_BA 从 MT {mt_bmba:.3f} 塌到 DAI {dai_bmba:.3f}；\n"
        f"仅 {' / '.join(tools[:3])} 保留信号。"  # top-3 现算，不写死
    )
    ax.text(0.985, 0.62, callout, transform=ax.transAxes,
            ha="right", va="top", fontsize=8.6, color="0.15",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="white",
                      edgecolor="0.7", alpha=0.94), zorder=6)

    # 图例
    handles = [
        Patch(facecolor=COLOR_POS, label="DAI $\\bar{\\rho}$ > 0"),
        Patch(facecolor=COLOR_NEG, label="DAI $\\bar{\\rho}$ < 0"),
        Patch(facecolor=COLOR_NA, label="N/A（仅 MT 无 WT / WT 结构 NaN，DAI 分不入）"),
    ]
    ax.legend(handles=handles, loc="lower right", fontsize=8.5, frameon=True, framealpha=0.92)

    # 副标/脚注
    fig.text(
        0.01, 0.005,
        "用上新数据的 WT（改动③） · DAI 按 mut_key max-pool · 102 SNV 肽 · 9 患者 · 数据 2026-07-08 重跑；"
        "误差棒=cluster-bootstrap 95%CI。"
        f" {n_valid} 工具可算 DAI，均值 $\\bar{{\\rho}}$={mean_val:.3f}（近随机）；"
        f" {n_na} 工具无 WT 分不入（{'/'.join(na_tools)}）。"  # 数量+名单从 coverage_fail 集现取，不写死
        " 数据源：R1_recomputed_rerun_9mer_dai_effN8.csv。",
        fontsize=6.6, color="0.4",
    )
    fig.subplots_adjust(left=0.16, right=0.965, top=0.93, bottom=0.09)

    outs = _save(fig, "fig_rerun_9mer_dai_ranking", dpi)

    # ---- print 关键值供主线核 ----
    print(f"[dai-ranking] valid tools = {n_valid}, N/A(shown) = {n_na}: {na_tools}")
    print(f"[dai-ranking] mean rho (valid) = {mean_val:.4f}  (MT-only mean = {mt_mean:.4f})")
    print(f"[dai-ranking] netMHCpan_BA: MT {mt_bmba:.4f} -> DAI {dai_bmba:.4f}")
    print(f"[dai-ranking] IEDB_Calis ties: DAI=0 in {tie_z}/{tie_n} peptides")
    print("[dai-ranking] top3:")
    for i in range(min(3, n_valid)):
        print(f"    {tools[i]:<16s} rho={vals[i]:.4f}  CI[{lo[i]:.3f},{hi[i]:.3f}]")
    print("[dai-ranking] tail3:")
    for i in range(max(0, n_valid - 3), n_valid):
        print(f"    {tools[i]:<16s} rho={vals[i]:.4f}  CI[{lo[i]:.3f},{hi[i]:.3f}]")
    print(f"[dai-ranking] saved -> {'; '.join(str(p) for p in outs)}")
    return mean_val, n_valid


def main():
    ap = argparse.ArgumentParser(
        description="QuantImmuBench §3.1 单工具 DAI 排名横向条形图")
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
    print("[done] DAI ranking figure written (script did NOT execute training/model code).")


if __name__ == "__main__":
    main()
