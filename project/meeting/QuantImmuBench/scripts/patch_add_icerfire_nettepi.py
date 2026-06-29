#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_add_icerfire_nettepi.py — QuantImmuBench G1 工具补齐 17→18/30
==================================================================
服务: quantimmu-bench / lever=G1 工具补齐（合 ICERFIRE + NetTepi 两列进大表）

设计哲学（仿 scripts/patch_merge_fixed.py + scripts/merge_newtools.py）:
  - **不重 join、不重建**：base = scripts/out/merged_all_tools_16tools.xlsx 是
    活真源（34247 行，已 HLA-FIX，P101/P102 用订正 HLA 填好）。本脚本只在它
    身上按 bb_idx left-join 贴两列新工具分数，绝不从头重 join（会丢 HLA-FIX）。
  - bb_idx left-join 机制照 merge_newtools.merge_one_tool 的「长 schema」分支：
    bb_idx 主键 + <tool>_score → MT_<tool>（这两 CSV 全行即 MT 侧，无 is_MT）。

================== 输入 ==================
  base:  scripts/out/merged_all_tools_16tools.xlsx   (34247 行 × 57 列, bb_idx 0-34246)

  ICERFIRE: scripts/out/newtools/icerfire_DS1DS2_scores.csv
    前 5 行为 # 注释（read_csv comment='#' 跳过），真实 header:
      bb_idx, icerfire_rank, icerfire_score, pending_DTU_consent
    bb_idx 唯一(29666 行, 无 NaN)；icerfire_score = 100 - icerfire_rank
    → **越高越强免疫原**（CSV 注释已声明方向已翻转统一），符合 MT_<tool> 约定。
    覆盖 29666/34247 ≈ 86.6%（icerfire 用 content join，部分 bb_idx 无匹配）。

  NetTepi: scripts/out/newtools/nettepi_DS1DS2_scores.csv
    header: bb_idx, nettepi_Comb, nettepi_Rank, nettepi_score, pending_DTU_consent
    bb_idx 唯一(34247 行, 但 26804 行分数为 NaN)；nettepi_score = nettepi_Comb。
    方向核实(本脚本 Bash 已核): bb_idx=1 Comb=0.515 / Rank=0.4(强)，
    bb_idx=0 Comb=0.048 / Rank=50.0(弱) → Comb 越高 ↔ Rank 越低 ↔ 越强免疫原。
    → nettepi_score 越高越强，符合 MT_<tool> 约定。范围 -0.049~0.79（Comb 可为负）。
    ⚠️ 有效填充仅 7443/34247 ≈ 21.7%（<50%，会打 WARN，主线知悉即可，非 bug）。

  两工具方向均「越大越免疫原」，与现有 MT_* 约定一致 → **本脚本不翻向**。

================== HLA-FIX 核查 ==================
  两 CSV 均**只有 bb_idx、无 HLA 列**。按任务约定：bb_idx 已是 HLA-FIX backbone
  的主键，直接 bb_idx 对齐即可，无 HLA 标签可比对、无需置 NaN。
  base 表 P101/P102 行的 HLA 已是订正真值
    （P101={A*66:01,B*40:01,B*57:01,C*06:02} / P102={A*02:01,B*35:03,B*38:01}，
     本脚本上游 Bash 已核 base 表这两患者 HLA 唯一值集 == 订正真值）。
  两 CSV 文件时间戳 2026-06-27，晚于 HLA-FIX 产出 16tools.xlsx 的时点，
  即两工具是在「订正 backbone」上重新算的 → P101/P102 对应 bb_idx 行分数应为
  正确等位下的结果，**不同于** patch_merge_fixed 对旧表 P101/P102 置 NaN 的处理，
  这里**不置 NaN**（旧表置 NaN 是因旧 join 用了错 HLA；本批新工具是订正后产物）。
  ⚠️ 留主线决策点（见文末「主线需决策」）: ICERFIRE 输出 CSV 的 join_strategy
     注释提到 content join on (MT_Subpeptide, WT_Subpeptide, HLA_icerfire)，
     输出已无 HLA 列，无法在本脚本里复核其 P101/P102 用的是否订正 HLA。

================== 输出 ==================
  scripts/out/merged_all_tools_18tools.xlsx   (期望 34247 行 × 59 列)
  scripts/out/newtools/PENDING_DTU_tools.txt  追加 ICERFIRE / NetTepi（去重）

================== 校验 ==================
  - 合并后行数必须 == 34247，否则 sys.exit(1)
  - 打印 MT_ICERFIRE / MT_NetTepi 填充率 (notna / 34247)

================== 跑法（主线串行，本脚本只写不跑）==================
  1) python scripts/patch_add_icerfire_nettepi.py
       预期产出: scripts/out/merged_all_tools_18tools.xlsx (34247×59)
                 + PENDING_DTU_tools.txt 追加两工具
  2) python analysis/pooling_sweep_17tools.py --input scripts/out/merged_all_tools_18tools.xlsx
       该脚本自动发现 MT_* 工具列（含新增两列），按 bb_idx 已在表内。
       预期产出: analysis/pooling_global_spearman_17tools.csv 等（含 ICERFIRE/NetTepi 行）
       ⚠️ 该脚本 NEW_TOOLS/OLD_TOOLS/pending 集合（line 80-85）未含 ICERFIRE/NetTepi，
          两工具会被当工具跑出 rho，但着色/DTU-pending 注释会缺；输出文件名仍 _17tools。
          若要正确分色+标 DTU pending，需主线另改该脚本（不在本任务范围）。
  3) python analysis/merge_metrics_NNtools.py
       自动寻 scripts/out/ 下最高 NN 的 merged_all_tools_<NN>tools.xlsx → 选 18tools。
       预期产出: analysis/metrics_ds2_18tools.csv + analysis/per_patient_spearman_18tools.csv

依赖: pandas, openpyxl
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

EXPECTED_ROWS = 34247

BASE = ROOT / 'scripts' / 'out' / 'merged_all_tools_16tools.xlsx'
ICERFIRE_CSV = ROOT / 'scripts' / 'out' / 'newtools' / 'icerfire_DS1DS2_scores.csv'
NETTEPI_CSV = ROOT / 'scripts' / 'out' / 'newtools' / 'nettepi_DS1DS2_scores.csv'
OUT = ROOT / 'scripts' / 'out' / 'merged_all_tools_18tools.xlsx'
PENDING_TXT = ROOT / 'scripts' / 'out' / 'newtools' / 'PENDING_DTU_tools.txt'


def left_join_score(result: pd.DataFrame, csv_path: Path, score_col: str,
                    mt_col: str, read_kwargs: dict) -> pd.DataFrame:
    """
    照 merge_newtools.merge_one_tool 长 schema 分支：
    读 CSV → bb_idx 主键 → 取 score_col → 强制数值 → drop_duplicates(bb_idx) 防外扩
    → left-join 到 result 命名 mt_col。两 CSV 全行即 MT 侧（无 is_MT）。
    """
    sdf = pd.read_csv(csv_path, **read_kwargs)
    sdf.columns = [c.strip() for c in sdf.columns]

    if 'bb_idx' not in sdf.columns:
        print(f'[ERR] {csv_path.name} 缺 bb_idx 列', file=sys.stderr)
        sys.exit(1)
    if score_col not in sdf.columns:
        print(f'[ERR] {csv_path.name} 缺分数列 {score_col}（实有列: {list(sdf.columns)}）',
              file=sys.stderr)
        sys.exit(1)

    sdf[score_col] = pd.to_numeric(sdf[score_col], errors='coerce')

    join_df = (sdf[['bb_idx', score_col]]
               .drop_duplicates('bb_idx')
               .rename(columns={score_col: mt_col}))

    before = len(result)
    result = result.merge(join_df, on='bb_idx', how='left')
    if len(result) != before:
        print(f'[ERR] {mt_col}: bb_idx merge 改变行数 {before}->{len(result)}，中止',
              file=sys.stderr)
        sys.exit(1)

    fill = int(result[mt_col].notna().sum())
    pct = fill / before * 100 if before else 0.0
    flag = '  [WARN<50%]' if pct < 50 else ''
    print(f'[{mt_col}] 填充率={fill}/{before} ({pct:.1f}%){flag}', file=sys.stderr)
    return result


def append_pending(tools):
    """追加 DTU pending 工具名到 sidecar，去重保留原有顺序。"""
    existing = []
    if PENDING_TXT.exists():
        existing = [ln.strip() for ln in
                    PENDING_TXT.read_text(encoding='utf-8').splitlines() if ln.strip()]
    merged = list(existing)
    for t in tools:
        if t not in merged:
            merged.append(t)
    PENDING_TXT.write_text('\n'.join(merged) + '\n', encoding='utf-8')
    print(f'[INFO] DTU pending sidecar -> {PENDING_TXT}', file=sys.stderr)
    print(f'       工具列表: {merged}', file=sys.stderr)


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    if not BASE.exists():
        print(f'[ERR] base 大表不存在: {BASE}', file=sys.stderr)
        sys.exit(1)

    m = pd.read_excel(BASE)
    print(f'[INFO] base 读入: {len(m)} 行 × {len(m.columns)} 列  ({BASE.name})',
          file=sys.stderr)

    if 'bb_idx' not in m.columns:
        print('[ERR] base 缺 bb_idx 列，无法主键 join', file=sys.stderr)
        sys.exit(1)
    if len(m) != EXPECTED_ROWS:
        print(f'[ERR] base 行数 {len(m)} ≠ 预期 {EXPECTED_ROWS}', file=sys.stderr)
        sys.exit(1)

    for col in ('MT_ICERFIRE', 'MT_NetTepi'):
        if col in m.columns:
            print(f'[ERR] base 已含 {col} 列，疑重复 patch，中止', file=sys.stderr)
            sys.exit(1)

    # ── ICERFIRE：跳过 # 注释行，icerfire_score（=100-rank，越高越强）→ MT_ICERFIRE ──
    m = left_join_score(m, ICERFIRE_CSV, 'icerfire_score', 'MT_ICERFIRE',
                        read_kwargs=dict(comment='#', encoding='utf-8'))

    # ── NetTepi：nettepi_score（=Comb，越高越强）→ MT_NetTepi ──────────────────────
    m = left_join_score(m, NETTEPI_CSV, 'nettepi_score', 'MT_NetTepi',
                        read_kwargs=dict(encoding='utf-8'))

    # ── 行数硬校验 ──────────────────────────────────────────────────────────────
    if len(m) != EXPECTED_ROWS:
        print(f'[ERR] 合并后行数 {len(m)} ≠ 预期 {EXPECTED_ROWS}！中止写出', file=sys.stderr)
        sys.exit(1)

    # ── HLA-FIX 说明（两 CSV 无 HLA 列 → bb_idx 对齐，不置 NaN，见文件头注）──────────
    pid = m['Patient_ID'].astype(str)
    pp = pid.str.contains('101') | pid.str.contains('102')
    n_pp = int(pp.sum())
    ic_pp = int(m.loc[pp, 'MT_ICERFIRE'].notna().sum())
    nt_pp = int(m.loc[pp, 'MT_NetTepi'].notna().sum())
    print(f'[HLA-FIX] P101/P102 行={n_pp}（按 bb_idx 对齐，CSV 无 HLA 列故不置 NaN）；'
          f'其中 MT_ICERFIRE 非空={ic_pp}，MT_NetTepi 非空={nt_pp}', file=sys.stderr)

    # ── DTU sidecar（两工具均 DTU 系，pending_DTU_consent=True）────────────────────
    append_pending(['ICERFIRE', 'NetTepi'])

    # ── 输出 ────────────────────────────────────────────────────────────────────
    OUT.parent.mkdir(parents=True, exist_ok=True)
    m.to_excel(OUT, index=False, engine='openpyxl')
    print(f'\n[DONE] 输出: {OUT}', file=sys.stderr)
    print(f'[DONE] 最终表: {len(m)} 行 × {len(m.columns)} 列（新增 MT_ICERFIRE, MT_NetTepi）',
          file=sys.stderr)


if __name__ == '__main__':
    main()
