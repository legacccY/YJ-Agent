#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_model_matrix_v2.py
========================
服务: quantimmu-bench / lever=G2 (无泄漏 + 多维 fusion 物理前提)

目的
----
现有 quantimmune/model_matrix.csv 只含 9 免疫原性工具 max-agg 维 + seq_* 维,
**不含 pooled 亲和力维**。但论文 headline 的 geomean rank-fusion (3/4/6/7 维)
混用「亲和力-pooled 维」(如 netAffneg topk k=20,α=0) + 「免疫原性-max 维」。
不把 pooled 亲和力维桥接进 model_matrix, geomean 主角维度根本不在矩阵里,
下游 analysis/fusion_study.py / quantimmune/lopo_eval.py 无法跑多维 fusion。

本脚本 = 在不破坏现有 model_matrix.csv 的前提下, 产出扩展矩阵 model_matrix_v2.csv:
  = 原 model_matrix 全部列 (9 免疫原维 MT_* + seq_* 维 + Patient_ID/Peptide_ID/Elispot)
  + 新增 pooled 亲和力维列 (从合表子肽层 pool 到突变层, 逐病人 label-blind 归一化)

数据流 (含无泄漏论证, 详见每步注释)
-----------------------------------
  1. 读基矩阵: quantimmune/model_matrix.csv  (183 行, Peptide_ID 为键, 含 Patient_ID/Elispot)
  2. 读合表:   scripts/out/merged_all_tools_18tools.xlsx (优先) → 16tools.xlsx (回退)
               子肽×HLA 级别, 含亲和力工具 MT_ 列
  3. Step-定向: 亲和力取「越高越强结合」方向。
               ★ 注意: 合表里的亲和力列在 parse 阶段已完成定向:
                 - MT_netmhcpan_ba          = netMHCpan BA-score (0-1, 越高越强结合)
                 - MT_MHCflurry_affinity_neg = -affinity(nM)      (原越低越强, 取负后越高越强)
               故此处 DIRECTION=+1 (源已是 -Aff 等价方向)。
               ★ 此步只用工具分数列本身, 不碰任何标签。
  4. Step-pool: 对每个亲和力工具列, 按 Peptide_ID groupby, 用 topk_w(k=20, α=0)
               = 前 20 条等权平均 pool 到突变(肽)层 (大纲 §3.4 务实默认)。
               ★ 复用 analysis/pooling_sweep_17tools.py 的 pool_topk_w 算子 (不另造)。
               ★ 此步只用工具分数列 + Peptide_ID 分组键, 不碰任何标签。
  5. Step-逐病人归一化: 对每个 Patient_ID 组的 pooled 值做 min 平移 + RMS 标准化。
               ★ 只用该病人自身的 pooled 亲和力值 + Patient_ID 分组键。
               ★ 绝不碰 Elispot/SFC/免疫原性 label, 也不跨病人借统计 → 无泄漏。
  6. 合并: 把 pooled 亲和力维 (按 Peptide_ID) 左连到基矩阵, 行数与基矩阵一致。
  7. 输出: quantimmune/model_matrix_v2.csv

无泄漏总结 (G2 卖点)
--------------------
  pool 与归一化全程 label-blind:
    - 定向 (step3): 只用工具分数方向, 无标签。
    - pool   (step4): 只用工具分数 + Peptide_ID 分组, 无标签。
    - 归一化 (step5): 只用病人自身 pooled 值 + Patient_ID 分组, 无标签, 不跨病人。
  Elispot 列原样从基矩阵带过来, 全程未参与任何 pooled 维的构造。

新增列命名
----------
  pool_<short>_top20_raw : 原始 pooled 亲和力 (定向后, pool 完, 未逐病人归一化)
  pool_<short>_top20     : 逐病人 (min 平移 + RMS) 归一化后的 pooled 亲和力维
                           = 供下游 fusion/robustness/ablation 用的 fusion 维
  short 映射: netmhcpan_ba → netAffneg ; MHCflurry_affinity_neg → mhcfluAffneg

跑法 (主线跑, 本脚本不自跑)
---------------------------
  python quantimmune/build_model_matrix_v2.py
  python quantimmune/build_model_matrix_v2.py --input scripts/out/merged_all_tools_16tools.xlsx
  python quantimmune/build_model_matrix_v2.py --base-matrix quantimmune/model_matrix.csv

来源引用
--------
  pooling 算子 topk_w: analysis/pooling_sweep_17tools.py (k=20, α=0 ⇔ weight_scheme='equal')
  亲和力定向:          HPC/deploy/.../parse_*.py (netMHCpan BA-score / MHCflurry -affinity(nM))
  k=20, α=0 默认:       QuanImmu-Paper-Outline.md §3.4
"""

import sys
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

# UTF-8 stdout (Windows 必要)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent          # quantimmune/
ROOT = HERE.parent                               # QuantImmuBench/
ANALYSIS_DIR = ROOT / "analysis"

DEFAULT_BASE_MATRIX = HERE / "model_matrix.csv"
# 输入合表优先级: 18tools (A1 产物, 可能未生成) → 16tools (现存活真源)
INPUT_PRIORITY = [
    ROOT / "scripts" / "out" / "merged_all_tools_18tools.xlsx",
    ROOT / "scripts" / "out" / "merged_all_tools_16tools.xlsx",
]
OUT_MATRIX = HERE / "model_matrix_v2.csv"

# ── 亲和力工具列 → 短名映射 ───────────────────────────────────────────────────
# key = 合表中的 MT_ 列名; value = (short_name, direction)
# direction=+1 表示该列已是「越高越强结合」(源 parse 阶段已定向, 见模块 docstring)。
# ★ 若将来接入原始 nM 列 (越低越强), 需把对应 direction 设为 -1 (= 取 -Aff)。
AFFINITY_TOOLS = {
    "MT_netmhcpan_ba":          ("netAffneg",    +1),  # netMHCpan BA-score (0-1, 越高越强)
    "MT_MHCflurry_affinity_neg": ("mhcfluAffneg", +1),  # -affinity(nM) (越高越强)
    # TODO: 若 18tools 合表新增其它亲和力工具列 (如 MT_MHCflurry_affinity 原始 nM),
    #       需主线核实际列名 + 方向后补进此 dict。
}

TOPK_K = 20          # 大纲 §3.4: top-k k=20
TOPK_ALPHA = 0       # α=0 ⇔ 前 20 条等权平均 ⇔ pool_topk_w(weight_scheme='equal')
EPS = 1e-12


# ── 复用 pooling_sweep_17tools.py 的 pooling 算子 (单一真源, 不另造) ───────────
# 优先 import; import 失败 (如 matplotlib 缺) 则回退到逐字搬运的同款实现,
# 保证 pool 数学定义与 pooling_sweep_17tools.py 完全一致。
try:
    if str(ANALYSIS_DIR) not in sys.path:
        sys.path.insert(0, str(ANALYSIS_DIR))
    from pooling_sweep_17tools import pool_topk_w, _sort_desc  # noqa: F401
    _POOL_SOURCE = "import:pooling_sweep_17tools"
except Exception as _e:  # pragma: no cover - 仅当 import 失败时走回退
    print(f"[warn] import pooling_sweep_17tools 失败 ({_e}); 回退到逐字搬运同款实现")

    def _sort_desc(arr):
        # 逐字搬运 pooling_sweep_17tools.py:_sort_desc
        arr = np.asarray(arr, float)
        arr = arr[~np.isnan(arr)]
        if len(arr) == 0:
            return arr
        return np.sort(arr)[::-1].copy()

    def pool_topk_w(arr, k=5, weight_scheme="inv_rank"):
        # 逐字搬运 pooling_sweep_17tools.py:pool_topk_w
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

    _POOL_SOURCE = "verbatim_copy:pooling_sweep_17tools"


def pool_top20_equal(arr):
    """topk_w k=20, α=0 (= 前 20 条等权平均, weight_scheme='equal')。
    α=0 ⇔ rank^0=1 ⇔ 全等权, 与 pooling_sweep_17tools.pool_topk_w 同款。
    """
    return pool_topk_w(arr, k=TOPK_K, weight_scheme="equal")


# ── 逐病人 label-blind 归一化: min 平移 + RMS 标准化 ─────────────────────────
def per_patient_norm(values: np.ndarray) -> np.ndarray:
    """对单个病人组的 pooled 亲和力值做 min 平移 + RMS 标准化。
    无泄漏: 只用该病人自身的 pooled 值, 不碰标签, 不跨病人借统计。

    步骤:
      shifted = v - nanmin(v)            (min 平移, 把最小值挪到 0)
      rms     = sqrt(nanmean(shifted^2)) (RMS 尺度)
      normed  = shifted / rms            (rms<eps 时不除, 退化为全 0)
    全 NaN / 单点 / 常数列 → 安全退化。
    """
    v = np.asarray(values, dtype=float)
    if np.all(np.isnan(v)):
        return v
    vmin = np.nanmin(v)
    shifted = v - vmin
    ss = shifted[~np.isnan(shifted)]
    rms = float(np.sqrt(np.mean(ss ** 2))) if ss.size else 0.0
    if rms < EPS:
        # 常数列 (含单点): 平移后全 0, 保持 0 (NaN 仍 NaN)
        return shifted
    return shifted / rms


def find_input(cli_input: str | None) -> Path:
    """按优先级自动找合表; --input 显式给定则优先用。"""
    if cli_input is not None:
        p = Path(cli_input)
        if not p.is_absolute():
            p = ROOT / p
        return p
    for cand in INPUT_PRIORITY:
        if cand.exists():
            return cand
    # 都不存在则返回最高优先级 (让 main 报错给出清晰路径)
    return INPUT_PRIORITY[0]


def main():
    ap = argparse.ArgumentParser(
        description="build_model_matrix_v2: 桥接 pooled 亲和力维进 model_matrix")
    ap.add_argument("--input", default=None,
                    help="合表 xlsx 路径 (默认自动找 18tools→16tools)")
    ap.add_argument("--base-matrix", default=str(DEFAULT_BASE_MATRIX),
                    help="基矩阵 model_matrix.csv 路径")
    ap.add_argument("--out", default=str(OUT_MATRIX),
                    help="输出 CSV 路径 (默认 quantimmune/model_matrix_v2.csv)")
    args = ap.parse_args()

    base_path = Path(args.base_matrix)
    merged_path = find_input(args.input)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[info] pooling 算子来源: {_POOL_SOURCE}")
    print(f"[info] pool 配置: topk_w k={TOPK_K}, α={TOPK_ALPHA} (=前{TOPK_K}条等权平均)")

    # ── Step 1: 读基矩阵 ──────────────────────────────────────────────────────
    if not base_path.exists():
        sys.exit(f"[ERR] 基矩阵不存在: {base_path}\n"
                 f"      先跑: python quantimmune/build_model_matrix.py")
    base = pd.read_csv(base_path, encoding="utf-8")
    print(f"\n[step1] 基矩阵 {base_path}  shape={base.shape}")
    for req in ("Peptide_ID", "Patient_ID", "Elispot"):
        if req not in base.columns:
            sys.exit(f"[ERR] 基矩阵缺必要列: {req}")
    print(f"  患者数: {base['Patient_ID'].nunique()}  肽数: {base['Peptide_ID'].nunique()}")

    # ── Step 2: 读合表 ────────────────────────────────────────────────────────
    if not merged_path.exists():
        sys.exit(f"[ERR] 合表不存在: {merged_path}")
    print(f"\n[step2] 合表 {merged_path}")
    mdf = pd.read_excel(merged_path)
    print(f"  原始 (子肽层): {mdf.shape}")
    if "Peptide_ID" not in mdf.columns:
        sys.exit("[ERR] 合表缺 Peptide_ID 列, 无法 pool 到突变层")

    # 检测合表里实际存在的亲和力工具列
    present_aff = {c: AFFINITY_TOOLS[c] for c in AFFINITY_TOOLS if c in mdf.columns}
    missing_aff = [c for c in AFFINITY_TOOLS if c not in mdf.columns]
    if missing_aff:
        print(f"  [warn] 合表缺以下预期亲和力列 (跳过): {missing_aff}")
    if not present_aff:
        sys.exit("[ERR] 合表中无任一已知亲和力工具列, 无 pooled 亲和力维可桥接。\n"
                 "      预期至少 MT_netmhcpan_ba; 请主线核实际列名。")
    print(f"  检测到亲和力工具列: {list(present_aff.keys())}")

    # ── Step 3+4: 定向 + pool 到突变层 (per Peptide_ID) ───────────────────────
    # ★ label-blind: 只用工具分数列 + Peptide_ID 分组, 全程不碰标签。
    print(f"\n[step3+4] 定向 (DIRECTION) + topk_w(k={TOPK_K},α={TOPK_ALPHA}) pool 到突变层 ...")
    pooled = pd.DataFrame({"Peptide_ID": mdf["Peptide_ID"].drop_duplicates().values})
    raw_cols = []
    for col, (short, direction) in present_aff.items():
        s = pd.to_numeric(mdf[col], errors="coerce") * direction  # step3 定向
        tmp = pd.DataFrame({"Peptide_ID": mdf["Peptide_ID"], "_v": s})
        # step4 pool: per Peptide_ID 取所有子肽×HLA 行, topk_w(k=20, equal)
        agg = (tmp.dropna(subset=["_v"])
                  .groupby("Peptide_ID")["_v"]
                  .agg(lambda g: pool_top20_equal(g.values))
                  .rename(f"pool_{short}_top20_raw")
                  .reset_index())
        pooled = pooled.merge(agg, on="Peptide_ID", how="left")
        raw_cols.append(f"pool_{short}_top20_raw")
        n_valid = pooled[f"pool_{short}_top20_raw"].notna().sum()
        print(f"  {col:<28s} → pool_{short}_top20_raw  (dir={direction:+d}, "
              f"{n_valid}/{len(pooled)} 肽有值)")

    # ── 合并 pooled 维到基矩阵 (按 Peptide_ID), 行数与基矩阵一致 ──────────────
    merged = base.merge(pooled, on="Peptide_ID", how="left")
    assert len(merged) == len(base), \
        f"行数变化 {len(base)}→{len(merged)} (Peptide_ID 非唯一?), 终止防错"

    # ── Step 5: 逐病人 (min 平移 + RMS) 归一化 ───────────────────────────────
    # ★ label-blind: 只用病人自身的 pooled 值 + Patient_ID 分组, 不碰标签, 不跨病人。
    print("\n[step5] 逐病人 min 平移 + RMS 标准化 (label-blind, 不跨病人) ...")
    norm_cols = []
    for raw_col in raw_cols:
        norm_col = raw_col.replace("_raw", "")   # pool_<short>_top20 (fusion 维)
        merged[norm_col] = (
            merged.groupby("Patient_ID")[raw_col]
                  .transform(lambda v: per_patient_norm(v.values))
        )
        norm_cols.append(norm_col)
        n_valid = merged[norm_col].notna().sum()
        print(f"  {raw_col:<32s} → {norm_col}  ({n_valid}/{len(merged)} 非 NaN)")

    # ── Step 6: 列顺序 = 原矩阵全列 + 新增 raw + 新增 norm ────────────────────
    new_cols = raw_cols + norm_cols
    final_cols = list(base.columns) + [c for c in new_cols if c not in base.columns]
    merged = merged[final_cols]

    # ── Step 7: 写出 ──────────────────────────────────────────────────────────
    merged.to_csv(out_path, index=False, encoding="utf-8")
    print(f"\n[saved] {out_path}  shape={merged.shape}")
    print(f"  原矩阵列数: {len(base.columns)}  新增 pooled 亲和力维: {len(new_cols)}")
    print(f"  新增列: {new_cols}")
    print(f"  fusion 维 (逐病人归一化): {norm_cols}")
    print("\n[无泄漏论证] pool(step4)+定向(step3)+归一化(step5) 全程 label-blind;")
    print("             Elispot 原样从基矩阵带过, 未参与任一 pooled 维构造。")
    print("[DONE] model_matrix_v2.csv 就绪, 下游 fusion_study.py/lopo_eval.py 可用 --matrix 指向它。")


if __name__ == "__main__":
    main()
