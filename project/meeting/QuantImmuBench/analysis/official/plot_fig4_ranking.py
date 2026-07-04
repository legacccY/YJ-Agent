#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
plot_fig4_ranking.py
====================
服务: QuantImmuBench 论文 outline §3.4「综合排名」的**统一排名图 (图4)** (纯排名口径, 已去部署路线)。
lever = 把干净 canonical 上重跑的全方法统一排名 (R8_unified_ranking_official.csv) 可视化,
       只读不重算。

它画什么 (一句话):
  全方法 (单工具 max / affinity free-pooling / 多工具 rank-fusion) 的**横向条形排名图**,
  按 per-patient Fisher-z $\\bar{\\rho}$ (零选择 / free-pooling 干净口径) 降序; 带 95% CI 误差棒。
  分色 (纯覆盖充分度, 非部署推荐): 全覆盖单工具高亮绿; 稀疏覆盖 (coverage=sparse) 灰显、不参与
  主排名比较; 其余全覆盖 (fusion / 学习型) 中性蓝。图上不再画方案A/方案B 部署 callout。

读哪个 csv 的哪些列:
  输入 = analysis/official/R8_unified_ranking_official.csv (--input 可覆写)
    · rank                 统一排名 (已按 rho_bar 降序)
    · method               方法名 (单工具 <tool>_<pooling> / fusion 名)
    · family               'single_tool' | 'fusion'
    · dim_set              fusion 维度集 (dim7 / SURV6 / affinity_default / '-')  ← 消歧标签
    · rho_bar              per-patient Fisher-z $\\bar{\\rho}$ (裸, 排名键) ← 条长
    · ci_lo / ci_hi        95% CI ← 误差棒
    · n_used               有效患者数 (=9 满覆盖)
    · coverage_flag        'full' | 'sparse'  (sparse → 灰, 不入部署)
    · length_artifact_flag 'none' | 'length_artifact' (控肽长掉幅>0.15, 不入部署)
    · overfit_flag         'none' | 'leak_free' | 'weighted_leak_free'
    · pending_DTU          DTU 受限 (True → 名后标 " (DTU)")
    · deploy_candidate     True → 部署候选高亮
  ★ 排名键 = rho_bar (裸); rho_bar_lenctrl 列存在但本图排名以 rho_bar 为准 (同 csv 注释头)。

跑法 (主线跑, coder 不跑):
  python analysis/official/plot_fig4_ranking.py
  python analysis/official/plot_fig4_ranking.py --input analysis/official/R8_unified_ranking_official.csv \
         --out analysis/official/figures/fig4_unified_ranking.png

Windows 规范: matplotlib Agg + Microsoft YaHei + axes.unicode_minus=False; pathlib; 纯 numpy/pandas;
  300 dpi PNG + 同名 PDF + paper/figures pdf。
"""

import sys
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

HERE = Path(__file__).resolve().parent
FIG_DIR = HERE / "figures"
PAPER_FIG = HERE.parent.parent / "paper" / "figures"
DEFAULT_CSV = HERE / "R8_unified_ranking_official.csv"
DEFAULT_OUT = FIG_DIR / "fig4_unified_ranking.png"

# ── 配色 (色盲友好 Okabe-Ito) ─────────────────────────────────────────────────
C_DEPLOY = "#009E73"    # 全覆盖单工具 绿 (高亮; deploy_candidate=True 行, 纯覆盖充分度非部署推荐)
C_SPARSE = "#7F7F7F"    # 稀疏覆盖 灰 (不参与主排名比较)
C_NEUTRAL = "#56B4E9"   # 其余全覆盖 (fusion/学习型) 中性蓝
C_NEG = "#B23A48"       # rho_bar<0 红 (覆盖标记优先)


def _as_bool(series):
    return series.astype(str).str.strip().str.lower().isin(["true", "1", "yes"])


def _read_csv(path):
    p = Path(path)
    if not p.exists():
        sys.exit(f"[ERR] 源 csv 不存在: {p}")
    return pd.read_csv(p, comment="#", encoding="utf-8")


def _bar_color(row):
    if str(row["coverage_flag"]).strip().lower() == "sparse":
        return C_SPARSE
    if bool(row["deploy_candidate"]):
        return C_DEPLOY
    if np.isfinite(row["rho_bar"]) and row["rho_bar"] < 0:
        return C_NEG
    return C_NEUTRAL


def _label(row):
    m = str(row["method"])
    ds = str(row["dim_set"]).strip()
    if str(row["family"]).strip() == "fusion" and ds not in ("-", "", "nan"):
        m = f"{m} ({ds})"
    if bool(row["pending_DTU"]):
        m = f"{m} (DTU)"
    return m


def make_fig(csv_path, out_path):
    df = _read_csv(csv_path)
    need = ["rank", "method", "family", "dim_set", "rho_bar", "ci_lo", "ci_hi",
            "n_used", "coverage_flag", "length_artifact_flag", "pending_DTU",
            "deploy_candidate"]
    for c in need:
        if c not in df.columns:
            sys.exit(f"[ERR] R8 unified 缺列 {c}; 实际={list(df.columns)}")
    df["pending_DTU"] = _as_bool(df["pending_DTU"])
    df["deploy_candidate"] = _as_bool(df["deploy_candidate"])
    for c in ("rank", "rho_bar", "ci_lo", "ci_hi", "n_used"):
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df = df.sort_values("rank").reset_index(drop=True)   # 已按 rho_bar 降序, 稳妥再排一次

    labels = df.apply(_label, axis=1).tolist()
    rho = df["rho_bar"].values.astype(float)
    lo = df["ci_lo"].values.astype(float)
    hi = df["ci_hi"].values.astype(float)
    n_used = df["n_used"].values.astype(float)
    colors = df.apply(_bar_color, axis=1).tolist()
    cov = df["coverage_flag"].astype(str).str.strip().str.lower().values
    lenflag = df["length_artifact_flag"].astype(str).str.strip().str.lower().values

    n = len(df)
    y = np.arange(n)[::-1]                     # rank1 在最上

    fig, ax = plt.subplots(figsize=(12.5, max(12, 0.42 * n)))

    xerr = np.vstack([np.clip(np.nan_to_num(rho - lo, nan=0.0), 0, None),
                      np.clip(np.nan_to_num(hi - rho, nan=0.0), 0, None)])
    ax.barh(y, np.nan_to_num(rho, nan=0.0), color=colors, edgecolor="white",
            height=0.66, zorder=2)
    ax.errorbar(np.nan_to_num(rho, nan=0.0), y, xerr=xerr, fmt="none", ecolor="#444444",
                elinewidth=0.9, capsize=2.2, zorder=3)
    ax.axvline(0, color="#888888", ls="--", lw=1.0, zorder=1)

    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=11)
    ax.set_xlabel("per-patient Fisher-z $\\bar{\\rho}$（零选择 max / free-pooling；干净口径，误差棒 = 95% CI）",
                  fontsize=12.5)
    ax.tick_params(axis="x", labelsize=11)
    ax.set_title("图4 · 全方法统一 LOPO 排名（DS2 9 患者，干净 canonical）",
                 fontsize=15, pad=12)

    # 右侧数值列: $\\bar{\\rho}$ + 覆盖 + 旗标 (供 verifier 直接核)
    finite_hi = hi[np.isfinite(hi)]
    finite_rho = rho[np.isfinite(rho)]
    right_edge = float(np.nanmax(np.concatenate([finite_hi, finite_rho, [0.0]]))) if (
        len(finite_hi) + len(finite_rho) > 0) else 0.0
    txt_x = right_edge + 0.03
    for yi, r, nu, c, cf, lf in zip(y, rho, n_used, colors, cov, lenflag):
        rtxt = "  n/a" if (r is None or np.isnan(r)) else f"{r:+.3f}"
        tag = ""
        if cf == "sparse":
            tag += "  稀疏"
        if lf not in ("none", "nan", ""):
            tag += "  肽长伪迹"
        ax.text(txt_x, yi, f"{rtxt}  ({int(nu)}/9){tag}", va="center", ha="left",
                fontsize=10.5, fontweight="bold", color=c)
    ax.text(txt_x, y[0] + 1.2, "$\\bar{\\rho}$  (覆盖 N/9)", va="center", ha="left",
            fontsize=10, color="#888888", fontstyle="italic")

    finite_lo = lo[np.isfinite(lo)]
    xmin = min(-0.35, (float(np.nanmin(finite_lo)) - 0.05) if len(finite_lo) else -0.35)
    ax.set_xlim(xmin, txt_x + 0.46)

    # (已去 outline §3.4 方案A/方案B 部署 callout — 本图为纯统一排名, 不作部署推荐)

    # 图例 (纯覆盖充分度分色, 非部署可用性)
    legend = [
        Patch(facecolor=C_DEPLOY, label="覆盖充分（全覆盖单工具）"),
        Patch(facecolor=C_NEUTRAL, label="全覆盖 (fusion/学习型)"),
        Patch(facecolor=C_SPARSE, label="稀疏覆盖（不参与主排名）"),
        Patch(facecolor=C_NEG, label="$\\bar{\\rho}$ < 0"),
    ]
    ax.legend(handles=legend, loc="lower right", fontsize=10.5,
              title="覆盖充分度", framealpha=0.95)

    fig.text(0.5, 0.010,
             "$\\bar{\\rho}$ = per-patient Spearman(方法分, Elispot) 跨患者 Fisher-z 等权聚合 (零选择 max / free-pooling 干净口径)；"
             "误差棒 = 95% CI。按 $\\bar{\\rho}$ 降序给出全方法统一排名。\n"
             "稀疏覆盖 (sparse) 与肽长伪迹标记的方法灰显 / 另标：虽 $\\bar{\\rho}$ 数值高但覆盖不足，不参与主排名比较。"
             "名后 (DTU) = DTU 受限工具。",
             ha="center", va="bottom", fontsize=10, color="#555555")

    fig.tight_layout(rect=(0, 0.045, 1, 1))
    _save(fig, out_path)


def _save(fig, out_path):
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    out_pdf = out_path.with_suffix(".pdf")
    fig.savefig(out_pdf, bbox_inches="tight")
    PAPER_FIG.mkdir(parents=True, exist_ok=True)
    paper_pdf = PAPER_FIG / out_pdf.name
    fig.savefig(paper_pdf, bbox_inches="tight")
    plt.close(fig)
    print(f"[saved] {out_path}")
    print(f"[saved] {out_pdf}")
    print(f"[saved] {paper_pdf}")


def main():
    ap = argparse.ArgumentParser(description="图4 全方法统一排名 (§3.4, 纯排名口径)")
    ap.add_argument("--input", default=str(DEFAULT_CSV),
                    help="R8_unified_ranking_official.csv 路径")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="输出 PNG 路径 (同目录同名存 PDF)")
    args = ap.parse_args()
    print(f"[info] 读: {args.input}")
    make_fig(args.input, args.out)
    print("[DONE] plot_fig4_ranking 完成")


if __name__ == "__main__":
    main()
