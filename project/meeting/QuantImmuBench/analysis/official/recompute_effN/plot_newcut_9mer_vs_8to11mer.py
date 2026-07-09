#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
plot_newcut_9mer_vs_8to11mer.py

服务：QuantImmuBench §2.2 可变窗补充口径出图 —— 【新切重跑 (rerun)】版。
      对比 "新切 9mer" vs "新切 8-11mer 全量" 的单工具 per-patient Spearman 排名。
      区别于旧 covfix 版 (plot_9mer_vs_8to11mer.py, 读 R1_recomputed_effN8.csv, 分母 130)。

数据源 (只读, 列名已核实):
  - 9mer   (新切) : analysis/official/recompute_effN/R1_recomputed_rerun_9mer_effN8.csv     (已存在, Jul 8)
  - 8-11mer(新切) : analysis/official/recompute_effN/R1_recomputed_rerun_8to11mer_effN8.csv (主线稍后 recompute 产)
      两表 schema 同 (同一 recompute 脚本 --tag 不同产)。用到列:
        Tool、fisherz_rho_effN (per-patient Spearman, Fisher-z 均值, effN>=8 门槛)、coverage_fail (bool)。
      pandas 读需 comment="#" (文件头 3 行 # 注释)。
  - 覆盖 (子肽层真源): data/frozen/coverage_matrix.NEW.csv
      长表 (列: mut_key, subpep_seq, hla_allele_std, side, tool, status; status∈{scored,missing}; side∈{MT,WT})。
      每工具覆盖率 = MT 侧 status=='scored' 占比, 分母 = MT 子肽×HLA 位点数 (满覆盖 = 17088)。
      修正 recheck-fix: 旧版读 pooled_clean_rerun_8to11mer.csv <Tool>_max 非空计数 (mut_key 层 max-pool),
      任一窗有分即非空 → 29 工具全画 102/102, 抹平子肽层真实覆盖差异 (误导)。

产物 (300dpi png + pdf, 各写 figures/ 与 paper/figures/ 两处):
  A: fig_newcut_9mer_vs_8to11mer_spearman —— 每工具 新切9mer vs 新切8-11mer 双色横向分组条形, 按 8-11mer rho 降序
  B: fig_newcut_8to11mer_coverage         —— 各工具子肽层 MT 侧真实覆盖率条形 (分母 17088 子肽×HLA 位点)

红线：本脚本【只写不跑】。数字全从 csv 现算, 不硬编任何 rho / 覆盖值。
主线跑：
      python analysis/official/recompute_effN/plot_newcut_9mer_vs_8to11mer.py [--dpi 300]
"""
import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # Windows 无 GUI 后端
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Windows 控制台 UTF-8 stdout (防中文/箭头乱码)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ---- 路径 (相对脚本解析: 脚本在 analysis/official/recompute_effN/, 项目根=parents[2]) ----
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]  # recompute_effN -> official -> analysis -> <ROOT>
assert SCRIPT_DIR == ROOT / "analysis" / "official" / "recompute_effN", \
    f"路径解析异常: SCRIPT_DIR={SCRIPT_DIR} ROOT={ROOT}"

CSV_9MER = SCRIPT_DIR / "R1_recomputed_rerun_9mer_effN8.csv"
CSV_811 = SCRIPT_DIR / "R1_recomputed_rerun_8to11mer_effN8.csv"
CSV_POOLED_811 = ROOT / "data" / "frozen" / "pooled_clean_rerun_8to11mer.csv"
OUT_DIRS = [ROOT / "figures", ROOT / "paper" / "figures"]

N_PEPTIDES = 102  # 8-11mer 新切池满分 (新切纯 SNV; 核: pooled_clean_rerun_9mer.csv = 102 行数据)

# ---- 学术配色 (蓝/灰双色, 色盲友好; 与旧 covfix 版一致便于横比) ----
COLOR_9MER = "#2166AC"   # 深蓝 (9mer main)
COLOR_811 = "#92C5DE"    # 浅蓝灰 (8-11mer aperture)
COLOR_PASS = "#4DAF4A"   # 绿 (覆盖满 102 达标)
COLOR_FAIL = "#FF7F00"   # 橙 (覆盖<102)
COLOR_DEGEN = "#999999"  # 灰 (非空满 102 但退化常数列, 秩相关 n/a)


def _save(fig, stem, dpi):
    """写 png+pdf 到 OUT_DIRS 全部目录。"""
    outs = []
    for d in OUT_DIRS:
        d.mkdir(parents=True, exist_ok=True)
        png = d / f"{stem}.png"
        pdf = d / f"{stem}.pdf"
        fig.savefig(png, dpi=dpi, bbox_inches="tight")
        fig.savefig(pdf, bbox_inches="tight")
        outs.append(png)
        outs.append(pdf)
    plt.close(fig)
    return outs


def make_fig_a(dpi):
    """图A: 新切9mer vs 新切8-11mer per-patient Spearman 双色横向分组条形图。按 8-11mer 降序。"""
    df9 = pd.read_csv(CSV_9MER, comment="#")[["Tool", "fisherz_rho_effN"]]
    df8 = pd.read_csv(CSV_811, comment="#")[["Tool", "fisherz_rho_effN"]]
    merged = df9.merge(df8, on="Tool", how="inner", suffixes=("_9mer", "_811")).dropna(
        subset=["fisherz_rho_effN_9mer", "fisherz_rho_effN_811"]
    )
    # 剔 9mer-only 硬限长工具 —— 其 8-11max ≡ 9mer max, 放进对比图=两条等长的假对比。
    #   (数据核: NeoaPred 结构 9mer, DeepNetBim 硬 9mer, 见 04_LOG; 与旧 covfix 版同一处理)
    EXCLUDE_9MER_ONLY = {"NeoaPred", "DeepNetBim"}
    n_before = len(merged)
    merged = merged[~merged["Tool"].isin(EXCLUDE_9MER_ONLY)].copy()
    dropped = n_before - len(merged)
    # 按 8-11mer 值降序 (本任务口径: 以可变窗为主排序)
    merged = merged.sort_values("fisherz_rho_effN_811", ascending=False).reset_index(drop=True)

    tools = merged["Tool"].tolist()
    v9 = merged["fisherz_rho_effN_9mer"].to_numpy()
    v8 = merged["fisherz_rho_effN_811"].to_numpy()
    n = len(tools)

    # y 轴: 降序 => 顶部为最高值, 故 y 位置反转
    y = np.arange(n)[::-1]
    h = 0.38

    fig, ax = plt.subplots(figsize=(13.0, max(6.5, 0.46 * n + 1.6)))
    ax.barh(y + h / 2, v9, height=h, color=COLOR_9MER, label="new-cut 9mer",
            edgecolor="white", linewidth=0.3)
    ax.barh(y - h / 2, v8, height=h, color=COLOR_811, label="new-cut 8-11mer (full)",
            edgecolor="white", linewidth=0.3)

    # 每条标数值 (符号感知: 正条标右, 负条标左, 不遮条)
    off = 0.006
    for yi, val in zip(y + h / 2, v9):
        ax.text(val + (off if val >= 0 else -off), yi, f"{val:.3f}",
                va="center", ha=("left" if val >= 0 else "right"),
                fontsize=6.5, color=COLOR_9MER, fontweight="bold")
    for yi, val in zip(y - h / 2, v8):
        ax.text(val + (off if val >= 0 else -off), yi, f"{val:.3f}",
                va="center", ha=("left" if val >= 0 else "right"),
                fontsize=6.5, color="#3B7CB0")

    ax.axvline(0.0, color="0.35", linestyle="--", linewidth=1.0, zorder=0)
    ax.set_yticks(y)
    ax.set_yticklabels(tools, fontsize=9)
    vmin = float(min(v8.min(), v9.min()))
    vmax = float(max(v8.max(), v9.max()))
    ax.set_xlim(min(vmin - 0.09, -0.02), vmax + 0.09)
    ax.set_xlabel("Per-patient Spearman (Fisher-z mean, effN>=8)", fontsize=10)
    ax.set_title(
        "Per-patient Spearman: new-cut 9mer vs new-cut 8-11mer variable window (rerun, effN>=8)",
        fontsize=11.5,
    )
    ax.legend(loc="upper left", bbox_to_anchor=(1.005, 1.0), fontsize=9, frameon=True)
    ax.grid(axis="x", linestyle=":", color="0.8", linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)
    fig.text(
        0.01, 0.005,
        "Source (new-cut rerun): R1_recomputed_rerun_9mer_effN8.csv + R1_recomputed_rerun_8to11mer_effN8.csv. "
        "Per-patient Spearman rho, Fisher-z averaged over patients with effN>=8; sorted by 8-11mer rho. "
        "Only tools applicable to both apertures shown; DeepNetBim / NeoaPred excluded (9mer-only: 8-11 max identical to 9mer max).",
        fontsize=6.5, color="0.4",
    )

    outs = _save(fig, "fig_newcut_9mer_vs_8to11mer_spearman", dpi)

    # ---- print 关键值供主线/verifier 核 ----
    print(f"[Fig A] joined tools (dropna) = {n} (excluded {dropped} 9mer-only: {sorted(EXCLUDE_9MER_ONLY)})")
    print("[Fig A] top3 by 8-11mer:")
    for i in range(min(3, n)):
        print(f"    {tools[i]:<16s} 9mer={v9[i]:.4f}  8-11mer={v8[i]:.4f}")
    print(f"[Fig A] saved: {[p.name for p in outs]}")
    return n


def make_fig_b(dpi):
    """图B: 子肽层 MT 侧真实覆盖 —— 每工具 = MT 侧 status=='scored' 占比。

    修正 (recheck-fix): 旧版用 pooled_clean_rerun_8to11mer.csv 的 <Tool>_max 非空计数当覆盖,
    因 pooled 是 mut_key 层 max-pool —— 任一窗有分该肽即非空, 29 工具全画成 102/102, 把子肽层
    真实覆盖差异抹平 (连只跑 9mer 的 DeepNetBim 也显 102), 误导读者以为覆盖齐平。

    真源改用子肽层长表 data/frozen/coverage_matrix.NEW.csv
      (列: mut_key, subpep_seq, hla_allele_std, side, tool, status; status∈{scored,missing}; side∈{MT,WT})。
      每工具覆盖率 = MT 侧 scored 行数 / MT 侧总行数 (满覆盖工具分母 = 17088 子肽×HLA 位点)。
    工具集取自 coverage_matrix 出现的全部工具 (29; NeoaPred 不在 roster 自然不画)。
    数字全从 csv 现算, 不硬编。
    """
    cov_csv = ROOT / "data" / "frozen" / "coverage_matrix.NEW.csv"
    cm = pd.read_csv(cov_csv, comment="#")
    mt = cm[cm["side"] == "MT"]

    # 每工具: scored / total (MT 侧), 分母即该工具 MT 侧子肽×HLA 位点数 (满覆盖=17088)
    grp = mt.groupby("tool")["status"]
    total_s = grp.size()
    scored_s = grp.apply(lambda s: int((s == "scored").sum()))
    cov_df = pd.DataFrame({"total": total_s, "scored": scored_s}).reset_index()
    cov_df.rename(columns={"tool": "Tool"}, inplace=True)
    cov_df["frac"] = cov_df["scored"] / cov_df["total"]
    cov_df["pct"] = 100.0 * cov_df["frac"]
    cov_df = cov_df.sort_values("frac", ascending=False).reset_index(drop=True)

    # 分母一致性核查 (spec: 满覆盖工具 total=17088); 不一致则告警不阻断
    DENOM = 17088
    off_denom = cov_df[cov_df["total"] != DENOM]
    if not off_denom.empty:
        print(f"[Fig B] WARNING: {len(off_denom)} tool(s) with MT total != {DENOM}: "
              f"{dict(zip(off_denom['Tool'], off_denom['total']))}")

    tlist = cov_df["Tool"].tolist()
    pvals = cov_df["pct"].to_numpy()
    svals = cov_df["scored"].to_numpy()
    tvals = cov_df["total"].to_numpy()
    n = len(tlist)

    # 满覆盖 (100%) 绿, 覆盖不齐 (<100%) 橙 —— 让「子肽层覆盖不齐」一眼可见
    FULL_EPS = 1e-9
    is_full = [p >= 100.0 - FULL_EPS for p in pvals]
    colors = [COLOR_PASS if f else COLOR_FAIL for f in is_full]
    n_full = sum(is_full)
    n_partial = n - n_full

    y = np.arange(n)[::-1]
    fig, ax = plt.subplots(figsize=(8.6, max(6.0, 0.38 * n + 1.5)))
    ax.barh(y, pvals, color=colors, edgecolor="white", linewidth=0.3)
    ax.axvline(100.0, color="0.3", linestyle="--", linewidth=1.0, zorder=0)

    for yi, p, sc, tt in zip(y, pvals, svals, tvals):
        ax.text(min(p + 1.2, 101.5), yi, f"{p:.1f}% ({int(sc)}/{int(tt)})",
                va="center", ha="left", fontsize=6.8, color="0.25")

    ax.set_yticks(y)
    ax.set_yticklabels(tlist, fontsize=8)
    ax.set_xlim(0, 118)
    ax.set_xticks([0, 20, 40, 60, 80, 100])
    ax.set_xlabel("Sub-peptide-level MT coverage (%)  [denom = 17088 sub-peptide x HLA slots]", fontsize=9.5)
    ax.set_title(
        "Tool coverage at sub-peptide level (new-cut 8-11mer, MT side; % of scored slots)",
        fontsize=10.5,
    )
    ax.grid(axis="x", linestyle=":", color="0.8", linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)

    from matplotlib.patches import Patch
    handles = [
        Patch(facecolor=COLOR_PASS, label=f"full coverage (100%, n={n_full})"),
        Patch(facecolor=COLOR_FAIL, label=f"partial (<100%, n={n_partial})"),
    ]
    ax.legend(handles=handles, loc="lower right", fontsize=9, frameon=True)
    fig.text(
        0.01, 0.005,
        "Source (sub-peptide level): data/frozen/coverage_matrix.NEW.csv. "
        "Coverage = MT-side status=='scored' fraction per tool over MT sub-peptide x HLA slots "
        "(full = 17088). Unlike mut_key-level max-pool (which shows every tool at 102/102), this "
        "reveals true per-slot coverage gaps for 9mer-only / length-restricted tools.",
        fontsize=6.3, color="0.4",
    )

    outs = _save(fig, "fig_newcut_8to11mer_coverage", dpi)

    # ---- print 每工具 coverage% 供主线/verifier 核 ----
    print(f"[Fig B] tools plotted = {n}; full-coverage(100%) = {n_full}, partial(<100%) = {n_partial}")
    print("[Fig B] per-tool MT coverage (descending):")
    for t, p, sc, tt in zip(tlist, pvals, svals, tvals):
        print(f"    {t:<16s} {p:6.1f}%  ({int(sc)}/{int(tt)})")
    print(f"[Fig B] saved: {[p.name for p in outs]}")
    return n_full


def main():
    ap = argparse.ArgumentParser(description="QuantImmuBench §2.2 new-cut 8-11mer aperture figures (rerun)")
    ap.add_argument("--dpi", type=int, default=300, help="raster dpi for png (default 300)")
    args = ap.parse_args()

    print(f"[out] figures -> {[str(d) for d in OUT_DIRS]}")
    make_fig_a(args.dpi)
    make_fig_b(args.dpi)
    print("[done] both figures written.")


if __name__ == "__main__":
    main()
