#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
plot_R1_effN.py
===============
服务: QuantImmuBench §3.1 图1 (30 工具 max-pool per-patient Spearman) 的 **修正版画图**。
读 recompute_R1_effN.py 产的 R1_recomputed_effN8.csv, 画修正版横条图 (PNG + paper/figures pdf)。
lever = 单工具 <tool>_max per-patient Spearman (零选择 headline)。

骨架复用 analysis/plot_ppt_v4_results.py 的 fig1_spearman (类别配色 + Windows YaHei + 纯
matplotlib Agg)。★ 未 import 原脚本 —— 原脚本 import 时会连带 `from S1_peptide_level_auprc
import load_binary_labels` 触发副作用/依赖, 故把所需常量+helper 就地复制 (自包含, 只从
_official_common import 纯常量 DTU_TOOLS)。配色/PRESENTATION_TOOLS 与原脚本逐字一致。

覆盖失败处理 (task 二选一, 本脚本选 A): coverage_fail=True 的工具 **保留在图内但归到最下方
单独区**, 灰 (C_GREY) + 名后标 "(coverage insuf.)"。选 A 而非「整体排除只脚注」的理由: 更
透明 —— 读者能直接看到它们存在且其 rho 不可信 (从 <3 患者撑起), 而非藏进脚注。

Windows 规范: Microsoft YaHei + axes.unicode_minus=False (防豆腐块); 纯 matplotlib Agg;
  pathlib; 独立 figure + plt.close()。★ 本脚本不自跑, 主线跑 (见文件尾)。
"""

import sys
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")                       # 无 GUI 后端 (只出文件)
import matplotlib.pyplot as plt

# Windows 必要: UTF-8 stdout
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ── 中文字体 (铁律: 防缺字豆腐块) ─────────────────────────────────────────────
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

HERE = Path(__file__).resolve().parent                  # analysis/official/recompute_effN/
OFFICIAL = HERE.parent                                  # analysis/official/
sys.path.insert(0, str(OFFICIAL))
from _official_common import DTU_TOOLS                   # noqa: E402  (纯常量, 无副作用)

R1_EFFN_CSV = HERE / "R1_recomputed_effN8.csv"          # main 里按 --input/--tag 覆写
OUT_PNG = HERE / "fig1_spearman_30tools_9mer_effN8.png"  # main 里按 --tag 覆写
LENLABEL = "9mer"                                       # 口径字样 (标题/xlabel/脚注), --lenlabel 覆写
# paper/figures 目录 (相对项目根): OFFICIAL.parent=analysis/, .parent.parent=QuantImmuBench/(根)
PAPER_FIG = OFFICIAL.parent.parent / "paper" / "figures"

# ── 配色 (逐字复用原 plot_ppt_v4_results.py) ──────────────────────────────────
C_PRESENT = "#0072B2"   # 呈递/结合类 蓝
C_IMMUNO = "#E69F00"    # 免疫原类 橙
C_NEG = "#B23A48"       # rho<0 红
C_GREY = "#7F7F7F"      # 覆盖失败 灰

# 呈递/结合类名单 (硬编码自 DEPLOY_TRACKER 表 A; 其余 TOOLS_30 归免疫原, 与原脚本一致)
PRESENTATION_TOOLS = {
    "HLAthena", "MHCflurry", "MHCnuggets", "MHCseqNet", "TransHLA",
    "netMHCpan_BA", "netMHCpan_EL", "netMHCstabpan",
}


def cat_color(tool, rho=None, coverage_fail=False):
    """条色: 覆盖失败 → 灰 (最优先); rho<0 → 红; 否则按类别蓝/橙。"""
    if coverage_fail:
        return C_GREY
    if rho is not None and not np.isnan(rho) and rho < 0:
        return C_NEG
    return C_PRESENT if tool in PRESENTATION_TOOLS else C_IMMUNO


def dtu_label(tool):
    """DTU 受限工具名后加 ' (DTU)'。"""
    return f"{tool} (DTU)" if tool in DTU_TOOLS else tool


def _read_csv(path):
    p = Path(path)
    if not p.exists():
        sys.exit(f"[ERR] 源 csv 不存在 (先跑 recompute_R1_effN.py): {p}")
    return pd.read_csv(p, comment="#", encoding="utf-8")


def _legend(ax, entries, **kw):
    from matplotlib.patches import Patch
    handles = [Patch(facecolor=c, edgecolor="none", label=l) for l, c in entries]
    ax.legend(handles=handles, **kw)


def fig1_effN():
    df = _read_csv(R1_EFFN_CSV)
    need = ["Tool", "fisherz_rho_effN", "ci_lo", "ci_hi", "n_full", "coverage_fail"]
    for c in need:
        if c not in df.columns:
            sys.exit(f"[ERR] fig1_effN: R1_recomputed_effN8 缺列 {c}; 实际={list(df.columns)}")

    df["coverage_fail"] = df["coverage_fail"].astype(str).str.strip().str.lower().isin(
        ["true", "1", "yes"])
    for c in ("fisherz_rho_effN", "ci_lo", "ci_hi"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["n_full"] = pd.to_numeric(df["n_full"], errors="coerce").fillna(0).astype(int)

    # ★ 主榜/参考区切分 = 覆盖是否满 9/9 (用户 2026-07-03 定): 只有 9/9 全覆盖工具进主榜排名;
    #   <9/9 (缺任一患者, 多因 P102 仅 8 肽稀疏) 归「参考区」灰显不参与主排序 —— 防覆盖子集不同致
    #   不可比 (如 MHCnuggets 0.46 靠缺最难 P102 的 8 患易子集虚高, 同患集下 netMHCpan_BA 反超)。
    def _rho_key(v):
        return -np.inf if (v is None or np.isnan(v)) else v
    is_ref = df["n_full"] < 9                            # 部分覆盖 → 参考区
    ok = df[~is_ref].copy()                              # 9/9 全覆盖 → 主榜
    ref = df[is_ref].copy()
    ok = ok.sort_values("fisherz_rho_effN", ascending=False,
                        key=lambda s: s.map(_rho_key)).reset_index(drop=True)
    # 参考区: 先按覆盖数降序 (8/9 在 1/9 前), 同覆盖再按 rho 降序
    ref = ref.sort_values(["n_full", "fisherz_rho_effN"], ascending=[False, False],
                          key=lambda s: s.map(_rho_key) if s.name == "fisherz_rho_effN" else s
                          ).reset_index(drop=True)
    plot_df = pd.concat([ok, ref], ignore_index=True)   # 主榜在上; 参考区在下
    n_ok = len(ok)

    tools = plot_df["Tool"].tolist()
    rho = plot_df["fisherz_rho_effN"].values.astype(float)
    lo = plot_df["ci_lo"].values.astype(float)
    hi = plot_df["ci_hi"].values.astype(float)
    n_full = plot_df["n_full"].values.astype(int)
    cfail = plot_df["coverage_fail"].values.astype(bool)
    refflag = (n_full < 9)                              # 参考区标记 (逐行)

    n = len(tools)
    y = np.arange(n)[::-1]                               # 第 0 行画在最上
    # 配色: 主榜 (9/9) 用类别色; 参考区 (<9/9) 一律灰 —— 视觉上不与主榜同台比。
    colors = [C_GREY if rf else cat_color(t, r, False)
              for t, r, rf in zip(tools, rho, refflag)]

    # max-pool 退化工具: 覆盖满 130/130 但 max-pool 饱和成常数列 → per-patient rho=nan,
    #   非真「覆盖失败」(易与覆盖矩阵 100% 打架致误读)。证据: pooled_clean_9mer 里
    #   DeepNetBim_max nunique==1 全=1.0 且 0 NaN; topk(k>=2)/softmax/rankdecay 方差恢复 (见 §3.2)。
    DEGENERATE_MAXPOOL = {"DeepNetBim"}

    # y 轴标签: DTU 后缀 + 参考区标覆盖不全 (8/9 标"部分覆盖"; 真缺肽<3 患者标"覆盖失败";
    #   满覆盖但 max-pool 退化的另标"max-pool 退化", 与真覆盖失败区分)
    ylabels = []
    for t, nf, cf in zip(tools, n_full, cfail):
        lab = dtu_label(t)
        if t in DEGENERATE_MAXPOOL:
            lab = f"{lab} (max-pool 退化)"
        elif cf:
            lab = f"{lab} (覆盖失败)"
        elif nf < 9:
            lab = f"{lab} (部分覆盖)"
        ylabels.append(lab)

    fig, ax = plt.subplots(figsize=(11.5, 15))
    # 误差棒: 相对条端的非对称长度 (rho/lo/hi 皆 NaN 时 nan_to_num 成 0, 不画错棒)
    xerr = np.vstack([np.clip(np.nan_to_num(rho - lo, nan=0.0), 0, None),
                      np.clip(np.nan_to_num(hi - rho, nan=0.0), 0, None)])
    ax.barh(y, np.nan_to_num(rho, nan=0.0), color=colors, edgecolor="white",
            height=0.62, zorder=2)
    ax.errorbar(np.nan_to_num(rho, nan=0.0), y, xerr=xerr, fmt="none", ecolor="#444444",
                elinewidth=1.0, capsize=2.5, zorder=3)
    ax.axvline(0, color="#888888", ls="--", lw=1.0, zorder=1)

    # 主榜 (9/9) / 参考区 (<9/9): 参考区加浅灰底纹 + 分隔线 (不再用会压条/压数字的内联文字,
    #   参考区身份改由底纹 + ylabel "(部分覆盖)"/"(覆盖失败)" + 图例 + 脚注共同标识, 零重叠)
    if n_ok > 0 and n_ok < n:
        sep_y = y[n_ok] + 0.5
        ax.axhspan(y[-1] - 0.5, sep_y, color="#F2F2F2", zorder=0)   # 参考区浅底纹 (最底层)
        ax.axhline(sep_y, color="#BBBBBB", ls=":", lw=1.2, zorder=1)

    ax.set_yticks(y)
    ax.set_yticklabels(ylabels, fontsize=15)
    ax.set_xlabel("per-patient Spearman rho (跨患者 Fisher-z 等权聚合, effN>=8 门槛)", fontsize=13)
    ax.tick_params(axis="x", labelsize=12)
    ax.set_title(f"30 工具 per-patient Spearman（{LENLABEL} 口径；主榜=9/9 全覆盖工具，effN>=8 门槛）",
                 fontsize=16, pad=12)

    # 标签列: (a) rho 数值紧跟 CI 右端, (b) n_full 再右一列
    finite_hi = hi[np.isfinite(hi)]
    finite_rho = rho[np.isfinite(rho)]
    right_edge = np.nanmax(np.concatenate([finite_hi, finite_rho, [0.0]])) if (
        len(finite_hi) + len(finite_rho) > 0) else 0.0
    rho_x = right_edge + 0.05           # 数值标签列起点 (合并 rho + 覆盖, 单 text 零重叠)
    for yi, r, nf, c, cf in zip(y, rho, n_full, colors, cfail):
        rtxt = "  n/a" if (r is None or np.isnan(r)) else f"{r:+.3f}"
        ax.text(rho_x, yi, f"{rtxt}   ({nf}/9)", va="center", ha="left",
                fontsize=13, fontweight="bold", color=c)
    # 列表头
    ax.text(rho_x, y[0] + 1.15, "rho  (覆盖 N/9)", va="center", ha="left",
            fontsize=11, color="#888888", fontstyle="italic")

    finite_lo = lo[np.isfinite(lo)]
    xmin = min(-0.25, (np.nanmin(finite_lo) - 0.05) if len(finite_lo) else -0.25)
    ax.set_xlim(xmin, rho_x + 0.42)     # 右侧留够放 "+0.460   (8/9)"

    # 图例放坐标区外右上 (bbox_to_anchor>1 = 轴外), 绝不压任何工具条/数值 (旧 upper-left 图例框宽
    #   过负值带右缘溢过 x=0 压住顶部长条根部, 故外移)
    _legend(ax, [("呈递/结合类 (主榜)", C_PRESENT), ("免疫原类 (主榜)", C_IMMUNO),
                 ("部分覆盖 <9/9 (参考区)", C_GREY)],
            loc="upper left", bbox_to_anchor=(1.005, 1.0),
            fontsize=11, title="工具类别", framealpha=0.95)
    # 脚注移到坐标区外底部 (fig.text, 不与图例/数值重叠)
    fig.text(0.5, 0.012,
             "rho = per-patient Spearman(工具打分, Elispot), 跨患者 Fisher-z 等权聚合, 门槛 effN>=8;  "
             "覆盖 N/9 = 通过门槛的患者数;  误差棒 = cluster-bootstrap 95%CI\n"
             "主榜 = 9/9 全覆盖工具 (公平同患者集可比); 灰条 = 部分覆盖(<9/9, 多缺最难 P102)仅供参考不参与主排序 "
             "—— 防覆盖子集不同致虚高(如 MHCnuggets 0.46 缺 P102, 同患集下 netMHCpan_BA 反超)。名后(DTU)=受限工具",
             ha="center", va="bottom", fontsize=10.5, color="#555555")

    fig.tight_layout(rect=(0, 0.045, 1, 1))    # 底部留白给脚注
    fig.savefig(OUT_PNG, dpi=200, bbox_inches="tight")
    # 再存一份 pdf 进 paper/figures/ (供论文 \includegraphics; 同一 fig 存两次, close 前)
    PAPER_FIG.mkdir(parents=True, exist_ok=True)
    out_pdf = PAPER_FIG / (OUT_PNG.stem + ".pdf")       # 跟随 OUT_PNG 命名 (tag 空=原 9mer pdf 名不变)
    fig.savefig(out_pdf, bbox_inches="tight")
    plt.close(fig)
    print(f"[saved] {OUT_PNG}")
    print(f"[saved] {out_pdf}")


def main():
    global R1_EFFN_CSV, OUT_PNG, LENLABEL
    ap = argparse.ArgumentParser(
        description="§3.1 图1 修正版横条图 (支持多长度口径 --input/--tag/--lenlabel)")
    ap.add_argument("--input", default=None,
                    help="源 csv (默认 None=R1_recomputed_effN8.csv 9mer 主口径); "
                         "8-11mer 口径传 recompute 产的 R1_recomputed_8to11mer_effN8.csv")
    ap.add_argument("--tag", default="",
                    help="非空则加进输出图名 (如 8to11mer -> fig1_spearman_30tools_8to11mer_effN8.png/pdf); "
                         "空=维持现有 9mer 无前缀命名不变")
    ap.add_argument("--lenlabel", default="9mer",
                    help="标题/脚注里的口径字样 (默认 9mer; 8-11mer 口径传 8-11mer)")
    args = ap.parse_args()
    tag = args.tag.strip()
    LENLABEL = args.lenlabel

    if args.input:
        in_path = Path(args.input)
        if not in_path.is_absolute():
            in_path = HERE / in_path                     # 相对路径按脚本目录解析 (产物同目录)
        R1_EFFN_CSV = in_path
    # else: 保持默认 R1_recomputed_effN8.csv (9mer)

    if tag:
        OUT_PNG = HERE / f"fig1_spearman_30tools_{tag}_effN8.png"
    # else: 保持默认 fig1_spearman_30tools_9mer_effN8.png (不变)

    print(f"[info] 读: {R1_EFFN_CSV}  (tag='{tag}', lenlabel='{LENLABEL}')")
    fig1_effN()
    print("[DONE] plot_R1_effN 完成")


if __name__ == "__main__":
    main()
