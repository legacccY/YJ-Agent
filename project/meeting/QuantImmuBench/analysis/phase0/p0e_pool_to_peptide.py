#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
p0e_pool_to_peptide.py
服务: quantimmu-bench / Phase 0 数据地基重建 (03_EXPERIMENT_PLAN.md §3)

把 (重对齐后的) 子肽×HLA×工具分数长表 pool 到肽级 (每肽一行)。

================== 输入 (依赖外部补跑) ==================
  scripts/out/merged_all_tools_30_official.csv  (子肽×HLA 长表)
    >>> 本脚本假设它已存在 <<< (主线: 补跑 29 缺失肽 + P104 新等位 -> 合并产)
    若不存在则清晰报错给出依赖说明, 不 silent。
    工具分数列约定: MT_<tool> 前缀 (沿用 merged_all_tools_*.xlsx 惯例)。
  data/frozen/ds2_official_groundtruth.csv      (p0a 产, 锚定 130 肽 + Elispot)

================== 8 pooling 算子 ==================
  max / mean / geomean / sum / softmax / top3mean / topk_w / rankdecay
  (定义复用 analysis/pooling_sweep_17tools.py; 分数 round(8) 防浮点 tie)

================== 输出 ==================
  data/frozen/pooled_peptide_level_30tools.csv  (130 行, 每肽一行)
    列: mut_key, Patient_ID, Peptide_ID, Elispot, n_subpep,
        <tool>_<op>            (每 tool×op 一列 pooled 分数, round8)
        count_conf_<tool>_<op> (bool: |spearman(pooled, n_subpep_tool)|>0.5)
  注: count_conf 是逐 tool×op 跨 130 肽算的单一 bool, 广播到每行。
      n_subpep 列 = 该肽长表总子肽行数; 混杂 corr 用逐工具有效计数 (内部)。

================== 校验门 ==================
  [P0-e1] 行数 == 130 (每肽一行)
  [P0-e2] 打印每工具缺失(pending)状态 (整列 NaN = 该工具尚未补跑)
  [P0-e3] fail-loud: 任一肽全工具皆空 -> 报错停
          (工具列暂缺标 pending 不报错; 整肽行不能空)

================== 跑法 ==================
  python analysis/phase0/p0e_pool_to_peptide.py
  python analysis/phase0/p0e_pool_to_peptide.py --input <长表路径>
"""

import sys
import argparse
from pathlib import Path
from functools import partial

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[2]

FROZEN_DIR = ROOT / "data" / "frozen"
GT_CSV = FROZEN_DIR / "ds2_official_groundtruth.csv"
DEFAULT_INPUT = ROOT / "scripts" / "out" / "merged_all_tools_30_official.csv"
OUT_CSV = FROZEN_DIR / "pooled_peptide_level_30tools.csv"

COUNT_CONFOUND_THRESH = 0.5

# 非工具 MT_* 列 (沿用 pooling_sweep_17tools.py)
EXCLUDE = {"MT_FullPeptide", "MT_Subpeptide", "MT_NOAH", "MT_NetCleave",
           "MT_Stab_peptide", "MT_TCR_contact"}


# ── 纯 numpy Spearman (禁 scipy 防 OMP#15; 复用 pooling_sweep) ──────────────
def spearman_np(x, y):
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    m = ~(np.isnan(x) | np.isnan(y))
    x, y = x[m], y[m]
    n = len(x)
    if n < 3 or len(np.unique(x)) < 2 or len(np.unique(y)) < 2:
        return np.nan
    rx = pd.Series(x).rank().values
    ry = pd.Series(y).rank().values
    rx -= rx.mean()
    ry -= ry.mean()
    denom = np.sqrt((rx ** 2).sum() * (ry ** 2).sum())
    if denom == 0:
        return np.nan
    return float((rx * ry).sum() / denom)


# ── 8 种 Pooling 算子 (复用 pooling_sweep_17tools.py 定义) ───────────────────
def _sort_desc(arr):
    arr = np.asarray(arr, float)
    arr = arr[~np.isnan(arr)]
    if len(arr) == 0:
        return arr
    return np.sort(arr)[::-1].copy()


def pool_max(arr):
    s = _sort_desc(arr)
    return float(s[0]) if len(s) else np.nan


def pool_mean(arr):
    s = _sort_desc(arr)
    return float(s.mean()) if len(s) else np.nan


def pool_top3mean(arr, k=3):
    s = _sort_desc(arr)
    return float(s[:min(k, len(s))].mean()) if len(s) else np.nan


def pool_sum(arr):
    """⚠ count 混杂: sum≈n_subpep。"""
    s = _sort_desc(arr)
    return float(s.sum()) if len(s) else np.nan


def pool_geomean(arr, eps=1e-9):
    s = _sort_desc(arr)
    if len(s) == 0:
        return np.nan
    if s[-1] <= 0:
        s = s - s[-1] + eps
    return float(np.exp(np.mean(np.log(np.maximum(s, eps)))))


def pool_softmax(arr, T=1.0):
    s = _sort_desc(arr)
    if len(s) == 0:
        return np.nan
    logits = s / T
    logits -= logits.max()
    w = np.exp(logits)
    w /= w.sum()
    return float((w * s).sum())


def pool_topk_w(arr, k=5, weight_scheme="inv_rank"):
    s = _sort_desc(arr)
    if len(s) == 0:
        return np.nan
    top = s[:min(k, len(s))]
    m = len(top)
    ranks = np.arange(1, m + 1, dtype=float)
    if weight_scheme == "inv_rank":
        w = 1.0 / ranks
    elif weight_scheme == "linear":
        w = (m + 1.0 - ranks)
    elif weight_scheme == "equal":
        w = np.ones(m, dtype=float)
    else:
        raise ValueError(f"未知 weight_scheme: {weight_scheme!r}")
    w_sum = w.sum()
    return float((w * top).sum() / w_sum) if w_sum else np.nan


def pool_rankdecay(arr, d=0.5):
    s = _sort_desc(arr)
    if len(s) == 0:
        return np.nan
    n = len(s)
    exps = np.arange(n, dtype=float)
    w = d ** exps
    w_sum = w.sum()
    return float((w * s).sum() / w_sum) if w_sum else np.nan


POOLINGS = {
    "max":       pool_max,
    "mean":      pool_mean,
    "geomean":   pool_geomean,
    "sum":       pool_sum,
    "softmax":   partial(pool_softmax,   T=1.0),
    "top3mean":  pool_top3mean,
    "topk_w":    partial(pool_topk_w,    k=5, weight_scheme="inv_rank"),
    "rankdecay": partial(pool_rankdecay, d=0.5),
}


def col_to_toolname(col):
    """MT_列名 -> 工具短名; IMPROVE 特例。"""
    name = col[3:]
    if name.startswith("IMPROVE"):
        return "IMPROVE"
    return name


def main():
    ap = argparse.ArgumentParser(description="子肽×HLA×工具 -> 肽级 8 pooling")
    ap.add_argument("--input", default=None,
                    help="子肽×HLA 长表 (默认 scripts/out/merged_all_tools_30_official.csv)")
    args = ap.parse_args()

    in_path = Path(args.input) if args.input else DEFAULT_INPUT
    if not in_path.is_absolute():
        in_path = ROOT / in_path

    if not in_path.exists():
        raise SystemExit(
            f"[ERR] 重对齐长表不存在: {in_path}\n"
            f"[ERR] 依赖说明: 此表由主线产 ==\n"
            f"        1) 按 data/frozen/RERUN_PEPTIDE_LIST.csv 补跑 29 缺失肽(全工具)\n"
            f"           + P104 新等位 A3001 (子肽展开见 subpep_hla_expansion.csv)\n"
            f"        2) 把补跑结果与旧 merged_all_tools_29tools.xlsx 可复用部分合并\n"
            f"        3) 导出为该 CSV (子肽×HLA 长表, MT_<tool> 分数列)\n"
            f"[ERR] 产出后再跑本脚本。")

    if not GT_CSV.exists():
        raise SystemExit(f"[ERR] 依赖缺失: {GT_CSV}  (先跑 p0a_build_groundtruth.py)")

    gt = pd.read_csv(GT_CSV)
    gt["Patient_ID"] = gt["Patient_ID"].astype(int)
    gt["Peptide_ID"] = gt["Peptide_ID"].astype(str)
    gt_keys = gt["mut_key"].tolist()
    assert len(gt_keys) == 130, f"[ERR] GT 锚定肽数={len(gt_keys)} != 130"

    print(f"[info] 读长表: {in_path}")
    df = pd.read_csv(in_path)
    print(f"[info] 长表 shape={df.shape}")

    # mut_key 构建 (若长表无该列, 用 Patient_ID|Peptide_ID)
    if "mut_key" not in df.columns:
        for req in ("Patient_ID", "Peptide_ID"):
            if req not in df.columns:
                raise SystemExit(f"[ERR] 长表缺 '{req}' 且无 mut_key, 无法构键")
        df["mut_key"] = (df["Patient_ID"].astype(int).astype(str)
                         + "|" + df["Peptide_ID"].astype(str))

    # ── 工具列检测 ──────────────────────────────────────────────────────
    tool_cols = []
    for c in df.columns:
        if not c.startswith("MT_") or c in EXCLUDE:
            continue
        df[c] = pd.to_numeric(df[c], errors="coerce")
        tool_cols.append(c)
    if not tool_cols:
        raise SystemExit("[ERR] 未找到 MT_* 工具分数列")
    tools = {col_to_toolname(c): c for c in tool_cols}
    print(f"[info] 检测到 {len(tools)} 个工具: {sorted(tools.keys())}")

    # ── 锚定 130 肽 (按 GT 顺序) ────────────────────────────────────────
    idx = pd.Index(gt_keys, name="mut_key")
    out = gt.set_index("mut_key")[["Patient_ID", "Peptide_ID", "Elispot"]].reindex(idx).copy()

    # 通用 n_subpep = 该肽长表总子肽行数
    n_subpep_all = df.groupby("mut_key").size().reindex(idx).fillna(0).astype(int)
    out["n_subpep"] = n_subpep_all.values

    # ── 逐工具 × 8 pooling ──────────────────────────────────────────────
    pooled_cols = []
    pending_tools = []
    confound_specs = []   # (pooled_col, conf_col, nsub_tool_series)

    for tool, col in sorted(tools.items()):
        valid = df[df[col].notna()]
        if valid.empty:
            pending_tools.append(tool)
            # 整列 pending: 写满 NaN 的 8 列 + count_conf False
            for op in POOLINGS:
                pcol = f"{tool}_{op}"
                out[pcol] = np.nan
                out[f"count_conf_{tool}_{op}"] = False
                pooled_cols.append(pcol)
            continue

        g = valid.groupby("mut_key")[col]
        nsub_tool = g.size().reindex(idx)   # 逐工具有效子肽计数 (用于混杂 corr)

        for op, fn in POOLINGS.items():
            pcol = f"{tool}_{op}"
            pooled = g.agg(lambda a: fn(a.values)).reindex(idx).round(8)
            out[pcol] = pooled.values
            pooled_cols.append(pcol)
            confound_specs.append((pcol, f"count_conf_{tool}_{op}", nsub_tool))

    # ── count 混杂诊断 (逐 tool×op 跨肽 corr, 广播 bool) ────────────────
    for pcol, ccol, nsub_tool in confound_specs:
        rho = spearman_np(out[pcol].values, nsub_tool.values)
        is_conf = (abs(rho) > COUNT_CONFOUND_THRESH) if not np.isnan(rho) else False
        out[ccol] = bool(is_conf)

    out = out.reset_index()

    # ── 校验门 ──────────────────────────────────────────────────────────
    assert len(out) == 130, f"[P0-e1] FAIL: 行数={len(out)} != 130"
    print(f"[P0-e1] PASS: 行数 == 130")

    # [P0-e2] 工具 pending 状态
    print(f"[P0-e2] 工具补跑状态:")
    n_pending = 0
    for tool in sorted(tools):
        cols_t = [f"{tool}_{op}" for op in POOLINGS]
        filled = int(out[cols_t].notna().any(axis=1).sum())
        if filled == 0:
            n_pending += 1
            print(f"         {tool}: PENDING (整列空, 待补跑)")
        else:
            print(f"         {tool}: {filled}/130 肽有值")
    print(f"[P0-e2] pending 工具数: {n_pending}/{len(tools)}")

    # [P0-e3] fail-loud: 任一肽全工具皆空
    pooled_mat = out[pooled_cols]
    all_empty = ~pooled_mat.notna().any(axis=1)
    n_all_empty = int(all_empty.sum())
    if n_all_empty > 0:
        bad = out.loc[all_empty, "mut_key"].tolist()
        raise SystemExit(
            f"[P0-e3] FAIL: {n_all_empty} 肽全工具皆空 (整肽行无任何分数): {bad}\n"
            f"        -- 长表未覆盖这些肽, 需补跑后重产长表 (不 silent)")
    print(f"[P0-e3] PASS: 无全工具皆空的肽 (每肽行至少 1 工具有值)")

    # ── 写出 ─────────────────────────────────────────────────────────────
    FROZEN_DIR.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_CSV, index=False, encoding="utf-8")
    print(f"\n[saved] {OUT_CSV}  shape={out.shape}")
    print(f"[info] {len(tools)} 工具 × {len(POOLINGS)} pooling = {len(pooled_cols)} pooled 列")
    print("[DONE] p0e_pool_to_peptide 完成")


if __name__ == "__main__":
    main()
