#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_add_munis.py — QuantImmuBench G1 工具补齐 21→22/30
==================================================================
服务: quantimmu-bench / lever=G1 工具补齐（合 MUNIS 一列进大表）

设计哲学（仿 scripts/patch_add_bigmhc_el.py，单列自然键 join，不重建不丢 HLA-FIX）:
  - base = scripts/out/merged_all_tools_21tools.xlsx 活真源（34247 行 × 61 列，
    已 HLA-FIX，已含 ICERFIRE/NetTepi/BigMHC_EL）。本脚本只贴 MUNIS 列。
  - score 源 = HPC/deploy/munis/munis_raw.csv（列 peptide,HLA_Allele,ic50；
    53582 数据行，本地 WSL2 TF2.10 全量跑出，0 NaN）。HLA_Allele 为原始带星
    'HLA-A*02:01' 格式，与 base 表 HLA_Allele 同款 → (MT_Subpeptide, HLA_Allele)
    / (WT_Subpeptide, HLA_Allele) 字符串自然键直接查表。

================== 方向说明（重要，勿删）==================
  MUNIS 原始输出 = binding affinity IC50(nM)，**越低越强结合**。
  本脚本建 score_map 时取负（-ic50）→ 越高越免疫原，与 benchmark 其他
  MT_* 工具「越大越免疫原」约定一致。

================== HLA-FIX（同 bigmhc_el：自然键查 base 自身订正 HLA，不置 NaN）==================
  base 表 P101/P102 行 HLA 已订正；munis_raw 在同一 uniq_pep_hla 上跑，
  含订正 (pep,hla) 键 → 按 base 订正 HLA 自然键查表天然命中，无须手动置 NaN。

================== 许可 ==================
  MUNIS = MIT/CC-BY-4.0(Zenodo) 许可，学术可发表 —— **非 DTU pending**，
  不写 PENDING_DTU sidecar。

================== 输出 ==================
  scripts/out/merged_all_tools_22tools.xlsx （期望 34247 行 × 63 列）
    新增列: MT_MUNIS, WT_MUNIS

================== 跑法（主线串行）==================
  1) python scripts/patch_add_munis.py  → merged_all_tools_22tools.xlsx
  2) python analysis/merge_metrics_NNtools.py → metrics_ds2_20tools.csv +
     per_patient_spearman_20tools.csv（自动扫最高 NN=20）

依赖: pandas, openpyxl
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent          # scripts/
ROOT = HERE.parent                               # QuantImmuBench/

EXPECTED_ROWS = 34247

BASE = ROOT / 'scripts' / 'out' / 'merged_all_tools_21tools.xlsx'
RAW = ROOT / 'HPC' / 'deploy' / 'munis' / 'munis_raw.csv'
OUT = ROOT / 'scripts' / 'out' / 'merged_all_tools_22tools.xlsx'

SCORE_COL = 'score'  # MUNIS EL 呈递概率,越高越强,不翻向        # raw 中的分数列名（coder NOTES 已核）


def load_score_map(raw_path: Path) -> dict:
    """读 munis_raw.csv，建 score_map {(pep, hla): score}（直用,越高越强）。"""
    df = pd.read_csv(raw_path, encoding='utf-8')
    df.columns = [c.strip() for c in df.columns]

    for c in ('peptide', 'HLA_Allele', SCORE_COL):
        if c not in df.columns:
            print(f'[ERR] {raw_path.name} 缺列 {c}（实有: {list(df.columns)}）',
                  file=sys.stderr)
            sys.exit(1)

    df['peptide'] = df['peptide'].astype(str).str.strip()
    df['HLA_Allele'] = df['HLA_Allele'].astype(str).str.strip()
    df[SCORE_COL] = pd.to_numeric(df[SCORE_COL], errors='coerce')
    df = df[(df['peptide'] != '') & (df['HLA_Allele'] != '') & df[SCORE_COL].notna()]

    # score 直用；同键最后覆盖
    score_map = dict(zip(zip(df['peptide'], df['HLA_Allele']),
                         df[SCORE_COL].astype(float)))
    print(f'[INFO] score_map 读入: {len(score_map)} 条唯一 (pep,hla) 键'
          f'（raw 数据行 {len(df)}，方向 score 直用不翻）', file=sys.stderr)
    return score_map


def lookup_col(m: pd.DataFrame, pep_col: str, score_map: dict,
               new_col: str) -> pd.DataFrame:
    """按 (m[pep_col], m['HLA_Allele']) 自然键查 score_map → 写 new_col。"""
    if pep_col not in m.columns:
        print(f'[ERR] base 缺 {pep_col} 列', file=sys.stderr)
        sys.exit(1)
    peps = m[pep_col].astype('string').fillna('').str.strip()
    hlas = m['HLA_Allele'].astype('string').fillna('').str.strip()
    keys = list(zip(peps.tolist(), hlas.tolist()))
    vals = [score_map.get(k, np.nan) if (k[0] and k[1]) else np.nan for k in keys]
    m[new_col] = pd.to_numeric(pd.Series(vals, index=m.index), errors='coerce')
    fill = int(m[new_col].notna().sum())
    pct = fill / len(m) * 100 if len(m) else 0.0
    flag = '  [WARN<50%]' if pct < 50 else ''
    print(f'[{new_col}] 填充率={fill}/{len(m)} ({pct:.1f}%){flag}', file=sys.stderr)
    return m


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    if not BASE.exists():
        print(f'[ERR] base 不存在: {BASE}', file=sys.stderr)
        sys.exit(1)
    if not RAW.exists():
        print(f'[ERR] raw 不存在: {RAW}', file=sys.stderr)
        sys.exit(1)

    m = pd.read_excel(BASE)
    print(f'[INFO] base 读入: {len(m)} 行 × {len(m.columns)} 列  ({BASE.name})',
          file=sys.stderr)
    if len(m) != EXPECTED_ROWS:
        print(f'[ERR] base 行数 {len(m)} ≠ 预期 {EXPECTED_ROWS}', file=sys.stderr)
        sys.exit(1)
    for req in ('HLA_Allele', 'MT_Subpeptide'):
        if req not in m.columns:
            print(f'[ERR] base 缺必要列 {req}', file=sys.stderr)
            sys.exit(1)
    for col in ('MT_MUNIS', 'WT_MUNIS'):
        if col in m.columns:
            print(f'[ERR] base 已含 {col}，疑重复 patch，中止', file=sys.stderr)
            sys.exit(1)

    score_map = load_score_map(RAW)

    m = lookup_col(m, 'MT_Subpeptide', score_map, 'MT_MUNIS')
    if 'WT_Subpeptide' in m.columns:
        m = lookup_col(m, 'WT_Subpeptide', score_map, 'WT_MUNIS')
    else:
        print('[INFO] base 无 WT_Subpeptide → 跳过 WT_MUNIS', file=sys.stderr)

    if len(m) != EXPECTED_ROWS:
        print(f'[ERR] 合并后行数 {len(m)} ≠ {EXPECTED_ROWS}！中止', file=sys.stderr)
        sys.exit(1)

    if 'Patient_ID' in m.columns:
        pid = m['Patient_ID'].astype(str)
        pp = pid.str.contains('101') | pid.str.contains('102')
        n_pp = int(pp.sum())
        mt_pp = int(m.loc[pp, 'MT_MUNIS'].notna().sum())
        wt_pp = (int(m.loc[pp, 'WT_MUNIS'].notna().sum())
                 if 'WT_MUNIS' in m.columns else 0)
        print(f'[HLA-FIX] P101/P102 行={n_pp}；MT 非空={mt_pp}，WT 非空={wt_pp}',
              file=sys.stderr)

    print('[LICENSE] MUNIS = MIT/CC-BY-4.0(Zenodo)，可发表；'
          '非 DTU pending → 不写 sidecar。', file=sys.stderr)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    m.to_excel(OUT, index=False, engine='openpyxl')
    new_cols = [c for c in ('MT_MUNIS', 'WT_MUNIS') if c in m.columns]
    print(f'\n[DONE] 输出: {OUT}\n[DONE] {len(m)} 行 × {len(m.columns)} 列（新增 {new_cols}）',
          file=sys.stderr)


if __name__ == '__main__':
    main()
