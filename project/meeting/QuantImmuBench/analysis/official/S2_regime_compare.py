#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
S2_regime_compare.py
====================
服务: QuantImmuBench Part D Phase 5 —— 「每个数据处理修正对关键结论的影响」量化对照表。
对应大纲: paper/QuanImmu-Paper-Outline.md §2.6 (评判标准重建) + Part C 数据清洗决策。
产物给 writer/reviewer: 一张表说清「legacy 脏口径 → 干净口径」每一步修正各自的净效应,
证明 Part B/C 的口径切换不是随手改, 而是每步都有可量化的方向与幅度。

━━━ 对照阶梯 (5 rung, 相邻差 = 1 个具名修正的净效应) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  每 rung 各算 5 个 method (netMHCpan_BA/PRIME/PredIG/HLAthena 单工具 + geomean-fusion)
  的 per-patient Fisher-z 聚合 ρ̄ (min_pep=3)。相邻两 rung 之差 = 一步修正的净贡献:

    rung0  legacy_bestpool_invvar   : legacy 脏表, 逐工具 best-of-8 pooling (含 sum), 逆方差权
    rung1  legacy_max_invvar        : legacy 脏表, 零选择 max 维,               逆方差权
       └─ Δ(弃sum选择) = rung1 - rung0   (弃「best pooling 挑到 sum≈数子肽数」的 count 混杂)
    rung2  clean_max_invvar         : 干净表 (突变过滤/弃WT/弃全窗), max 维,      逆方差权
       └─ Δ(突变过滤+换干净表) = rung2 - rung1
    rung3  clean_max_equal          : 干净表, max 维,                           等权 ← 【干净表裸】
       └─ Δ(跨病人等权 invvar→equal) = rung3 - rung2
    rung4  clean_max_equal_ctrl     : 干净表, max 维, 等权, per-patient 偏相关 ctrl=peplen
       └─ Δ(控肽长混杂) = rung4 - rung3   ← 【干净表控肽长】

  ★ 命名对齐 task 三口径: rung0=「legacy 脏表(逆方差)」, rung3=「干净表裸(等权)」,
    rung4=「干净表控肽长」。rung1/rung2 为分离「弃sum」与「突变过滤」的中间诊断 rung
    (否则 legacy→clean 一步跳把两效应搅在一起, 无法分账)。

━━━ 关键结论读法 (每 method 一行, 值随口径怎么变) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  例 HLAthena: rung0 (best-of-8+sum+invvar) 虚高 → rung3 (裸 max 等权) → rung4 (控肽长) 落地,
    量化「best-pooling 选择偏 + 逆方差 + 肽长混杂」各贡献多少虚高。

━━━ 输入 (只读) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  · 干净表  = data/frozen/pooled_clean_9mer.csv          (含 peplen, 51 变体 pooling)
  · legacy = data/frozen/pooled_peptide_level_30tools_9mer.csv (8 pooling 含 sum, 无 peplen; 若缺则 skip rung0/1)

━━━ 方法 (纯 numpy/pandas; 禁 scipy.stats 防 OMP #15) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  · per_patient_spearman / per_patient_partial_spearman / apply_fusion —— 全复用 _official_common,
    与 R1-R9 口径逐位一致。weight='invvar' | 'equal' 由 rung 决定。
  · geomean-fusion = apply_fusion(4 工具对应 pooling 列, method='geomean') 病人内 rank 融合 (leak-free)。

━━━ 输出 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  · S2_regime_compare.csv —— 宽表: index=method, 列=5 rung 的 ρ̄ + 4 个具名 Δ (弃sum/突变过滤/等权/控肽长)。
  · stdout 打印宽表 + 「每修正净效应」摘要 (各修正跨 method 的平均 Δ 与方向)。

━━━ 跑法 (主线跑, 本脚本不自跑) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  python analysis/official/S2_regime_compare.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from _official_common import (
    FROZEN_POOLED, FROZEN_POOLED_LEGACY, apply_fusion, ensure_out_dir,
    load_frozen, per_patient_partial_spearman, per_patient_spearman, r6,
)

# Windows 必要: UTF-8 stdout
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

TOOLS = ["netMHCpan_BA", "PRIME", "PredIG", "HLAthena"]   # 单工具 method
FUSION_NAME = "geomean_fusion"
# legacy 8 pooling (含 sum = count 混杂); best-of-8 在此集内选。
LEGACY_POOLINGS = ["max", "mean", "geomean", "sum", "softmax", "top3mean", "topk_w", "rankdecay"]

# rung 定义: (rung_id, 展示名, table, pooling_mode, weight, ctrl)
#   pooling_mode: 'best8'=legacy best-of-8 选择 | 'max'=零选择 max 维
RUNGS = [
    ("rung0", "legacy_bestpool_invvar", "legacy", "best8", "invvar", None),
    ("rung1", "legacy_max_invvar",      "legacy", "max",   "invvar", None),
    ("rung2", "clean_max_invvar",       "clean",  "max",   "invvar", None),
    ("rung3", "clean_max_equal",        "clean",  "max",   "equal",  None),
    ("rung4", "clean_max_equal_ctrl",   "clean",  "max",   "equal",  "peplen"),
]

# 相邻 rung 之差 = 具名修正: (Δ列名, rung_hi, rung_lo)
DELTAS = [
    ("d_dropsum",     "rung1", "rung0"),   # 弃 best-pooling 选到 sum 的 count 混杂
    ("d_mutfilter",   "rung2", "rung1"),   # 突变过滤 + 换干净表 (弃 WT/全窗)
    ("d_equalweight", "rung3", "rung2"),   # 跨病人 invvar -> equal
    ("d_ctrlpeplen",  "rung4", "rung3"),   # per-patient 偏相关控肽长
]

DTU_NOTE = "netMHCpan_BA 属 DTU 受限工具 (pending_DTU_consent), 结果照常算仅内部用。"


# ═══════════════════════════════════════════════════════════════════════════════
# pooling 列名 (legacy best-of-8 / 零选择 max)
# ═══════════════════════════════════════════════════════════════════════════════

def _legacy_best_pooling_col(df, tool, weight):
    """legacy 表内该工具 best-of-8 pooling (含 sum) 列名, 按 weight 选 per-patient ρ̄ 最高。
    返回 (col, pooling_name, rho); 无有效列 -> (None, None, nan)。
    ★ 这就是 legacy「脏」的来源: 允许挑到 sum (∝ n_subpep, count 作弊) 抬高 ρ̄。
    """
    best_col, best_pl, best_rho = None, None, -np.inf
    for pl in LEGACY_POOLINGS:
        col = f"{tool}_{pl}"
        if col not in df.columns or df[col].notna().sum() == 0:
            continue
        rho = per_patient_spearman(df, col, weight=weight)[0]
        if rho is not None and not np.isnan(rho) and rho > best_rho:
            best_col, best_pl, best_rho = col, pl, rho
    if best_col is None:
        return None, None, np.nan
    return best_col, best_pl, best_rho


def _tool_col_for_rung(df, tool, pooling_mode, weight):
    """返回该 rung 下工具的分数列名 + pooling 标签。"""
    if pooling_mode == "max":
        col = f"{tool}_max"
        return (col if col in df.columns else None), "max"
    if pooling_mode == "best8":
        col, pl, _ = _legacy_best_pooling_col(df, tool, weight)
        return col, (pl if pl else "NA")
    sys.exit(f"[ERR] 未知 pooling_mode: {pooling_mode}")


# ═══════════════════════════════════════════════════════════════════════════════
# 单 rung: 5 method 的 ρ̄
# ═══════════════════════════════════════════════════════════════════════════════

def eval_rung(clean_df, legacy_df, rung):
    """算某 rung 下 5 method (4 工具 + geomean-fusion) 的 per-patient ρ̄。
    返回 {method: (rho, note)}。表缺失 (legacy 不存在) -> 全 NaN + note。
    """
    _, name, table, pooling_mode, weight, ctrl = rung
    df = legacy_df if table == "legacy" else clean_df
    out = {}
    if df is None:
        for m in TOOLS + [FUSION_NAME]:
            out[m] = (np.nan, f"{table}表缺失,skip")
        return out

    # 单工具
    fusion_cols = []
    fusion_labels = []
    for tool in TOOLS:
        col, pl = _tool_col_for_rung(df, tool, pooling_mode, weight)
        if col is None:
            out[tool] = (np.nan, "列缺")
            continue
        if ctrl is not None:
            rho = per_patient_partial_spearman(df, col, ctrl=ctrl, weight=weight)[0]
        else:
            rho = per_patient_spearman(df, col, weight=weight)[0]
        out[tool] = (rho, f"pool={pl}")
        fusion_cols.append(col)
        fusion_labels.append(pl)

    # geomean-fusion over 4 工具的该 rung pooling 列
    if len(fusion_cols) >= 2:
        fused = apply_fusion(df, fusion_cols, "geomean")
        if ctrl is not None:
            frho = per_patient_partial_spearman(df, fused.values, ctrl=ctrl, weight=weight)[0]
        else:
            frho = per_patient_spearman(df, fused.values, weight=weight)[0]
        out[FUSION_NAME] = (frho, f"fuse[{','.join(fusion_labels)}]")
    else:
        out[FUSION_NAME] = (np.nan, "融合维不足")
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    out_dir = ensure_out_dir()
    print(f"[info] 读干净表 (只读): {FROZEN_POOLED}")
    clean_df = load_frozen(FROZEN_POOLED)
    print(f"[info] clean shape={clean_df.shape}")
    if "peplen" not in clean_df.columns:
        sys.exit("[ERR] 干净表缺 peplen 列 (rung4 控肽长依赖)")

    if FROZEN_POOLED_LEGACY.exists():
        print(f"[info] 读 legacy 脏表 (只读): {FROZEN_POOLED_LEGACY}")
        legacy_df = load_frozen(FROZEN_POOLED_LEGACY)
        print(f"[info] legacy shape={legacy_df.shape}")
    else:
        legacy_df = None
        print(f"[warn] legacy 表不存在 ({FROZEN_POOLED_LEGACY}); rung0/rung1 记 NaN。")
    print(f"[note] {DTU_NOTE}")

    methods = TOOLS + [FUSION_NAME]

    # rung × method -> rho / note
    rho_by_rung = {}   # rung_id -> {method: rho}
    note_by_rung = {}  # rung_id -> {method: note}
    for rung in RUNGS:
        rid = rung[0]
        res = eval_rung(clean_df, legacy_df, rung)
        rho_by_rung[rid] = {m: res[m][0] for m in methods}
        note_by_rung[rid] = {m: res[m][1] for m in methods}
        print(f"[rung] {rid} {rung[1]}: "
              + ", ".join(f"{m}={r6(res[m][0],3)}" for m in methods))

    # ── 宽表: index=method, 列=5 rung ρ̄ + 4 Δ ────────────────────────────────
    rung_ids = [r[0] for r in RUNGS]
    rung_names = {r[0]: r[1] for r in RUNGS}
    data = {}
    for rid in rung_ids:
        data[rung_names[rid]] = [r6(rho_by_rung[rid][m], 4) for m in methods]
    wide = pd.DataFrame(data, index=methods)
    # Δ 列
    for dname, hi, lo in DELTAS:
        col = []
        for m in methods:
            vh, vl = rho_by_rung[hi][m], rho_by_rung[lo][m]
            col.append(r6(vh - vl, 4) if not (np.isnan(vh) or np.isnan(vl)) else np.nan)
        wide[dname] = col

    out_csv = out_dir / "S2_regime_compare.csv"
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        f.write("# S2_regime_compare.csv — 每个数据处理修正对关键结论(per-patient ρ̄)的净效应\n")
        f.write("# 5 rung 阶梯 (相邻差=1 具名修正); 列=各 rung ρ̄ + 4 Δ。\n")
        f.write("#   d_dropsum=弃best-pooling选sum(count混杂) | d_mutfilter=突变过滤+换干净表\n")
        f.write("#   d_equalweight=跨病人invvar->equal | d_ctrlpeplen=偏相关控肽长\n")
        f.write("# 口径逐位复用 _official_common (同 R1-R9); 纯 numpy Spearman, 禁 scipy。\n")
        f.write("# label=method(行), 各 rung/Δ 值=per-patient Fisher-z 聚合 ρ̄。\n")
        wide.reset_index().rename(columns={"index": "method"}).to_csv(f, index=False)
    print(f"\n[saved] {out_csv}")

    # ── 打印宽表 ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 90)
    print("口径对照宽表 (per-patient ρ̄; 行=method, 列=rung + 具名 Δ)")
    print("=" * 90)
    with pd.option_context("display.width", 200, "display.max_columns", 30):
        print(wide.to_string())

    # ── 「每修正净效应」摘要 ──────────────────────────────────────────────────
    print("\n" + "-" * 90)
    print("每修正净效应摘要 (跨 method 平均 Δ; 负=该修正拉低虚高 ρ̄, 正=抬高)")
    print("-" * 90)
    label_map = {
        "d_dropsum": "弃 sum 选择 (count 混杂)",
        "d_mutfilter": "突变过滤 + 换干净表",
        "d_equalweight": "跨病人等权 (invvar->equal)",
        "d_ctrlpeplen": "偏相关控肽长",
    }
    for dname, _, _ in DELTAS:
        vals = wide[dname].dropna().values.astype(float)
        if len(vals) == 0:
            print(f"  {label_map[dname]:<28}: 无有效 Δ (依赖表缺失)")
            continue
        mean_d = float(np.mean(vals))
        arrow = "↓拉低" if mean_d < 0 else ("↑抬高" if mean_d > 0 else "≈无变")
        detail = ", ".join(f"{m}={r6(v,3)}" for m, v in zip(methods, wide[dname].values))
        print(f"  {label_map[dname]:<28}: 平均Δ={r6(mean_d,4)} {arrow}  ({detail})")

    print("\n[DONE] S2_regime_compare 完成")


if __name__ == "__main__":
    main()
