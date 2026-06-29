#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_add_transhla.py — QuantImmuBench G1 工具补齐 20→21/30
==================================================================
服务: quantimmu-bench / lever=G1 工具补齐（合 TransHLA 一列进大表）

设计（仿 patch_add_mhcnuggets.py，但 TransHLA = HLA-agnostic 肽-only）:
  - base = scripts/out/merged_all_tools_20tools.xlsx 活真源（34247 行，已含
    MHCnuggets/ICERFIRE/NetTepi/BigMHC_EL，已 HLA-FIX）。只贴 TransHLA 列。
  - score 源 = HPC/deploy/transhla/transhla_raw.csv（列 peptide,prob,label；
    11903 unique 肽，本地 WSL2 RTX4070 GPU + ESM2-650M 跑出）。
  - **HLA-agnostic**：TransHLA 只依赖肽序列、不吃 HLA → score_map 键 = 肽（非
    (肽,HLA)）；同肽对所有 HLA_Allele 行广播同值（同 Repitope）。
    → 按 base 的 MT_Subpeptide / WT_Subpeptide **肽-only** 查表（不带 HLA）。

================== 方向（重要）==================
  TransHLA prob = 「是表位」概率 [0-1]，越高越免疫原 → **不翻转**，直接用。

================== HLA-FIX ==================
  肽-only 查表与 HLA 无关 → P101/P102 HLA 订正不影响 TransHLA 列，天然安全。

================== 许可 ==================
  TransHLA = MIT，可发表，非 DTU pending → 不写 sidecar。
  ⚠️ benchmark 报告须标 HLA-agnostic caveat（同肽各 allele 同值，同 Repitope）。

================== 输出 ==================
  scripts/out/merged_all_tools_21tools.xlsx（期望 34247 × 65）
    新增列: MT_TransHLA, WT_TransHLA

================== 跑法 ==================
  1) python scripts/patch_add_transhla.py
  2) python analysis/merge_metrics_NNtools.py  → *_21tools.csv

依赖: pandas, openpyxl
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
EXPECTED_ROWS = 34247

BASE = ROOT / 'scripts' / 'out' / 'merged_all_tools_20tools.xlsx'
RAW = ROOT / 'HPC' / 'deploy' / 'transhla' / 'transhla_raw.csv'
OUT = ROOT / 'scripts' / 'out' / 'merged_all_tools_21tools.xlsx'

PROB_COL = 'prob'


def load_score_map(raw_path: Path) -> dict:
    """读 transhla_raw.csv，建 score_map {peptide: prob}（肽-only，不翻向）。"""
    df = pd.read_csv(raw_path, encoding='utf-8')
    df.columns = [c.strip() for c in df.columns]
    for c in ('peptide', PROB_COL):
        if c not in df.columns:
            print(f'[ERR] {raw_path.name} 缺列 {c}（实有: {list(df.columns)}）',
                  file=sys.stderr)
            sys.exit(1)
    df['peptide'] = df['peptide'].astype(str).str.strip()
    df[PROB_COL] = pd.to_numeric(df[PROB_COL], errors='coerce')
    df = df[(df['peptide'] != '') & df[PROB_COL].notna()]
    score_map = dict(zip(df['peptide'], df[PROB_COL].astype(float)))
    print(f'[INFO] score_map 读入: {len(score_map)} 条唯一肽键（肽-only，HLA-agnostic）',
          file=sys.stderr)
    return score_map


def lookup_col(m: pd.DataFrame, pep_col: str, score_map: dict,
               new_col: str) -> pd.DataFrame:
    """按 m[pep_col] 肽-only 查 score_map → 写 new_col（广播到各 allele 行）。"""
    if pep_col not in m.columns:
        print(f'[ERR] base 缺 {pep_col} 列', file=sys.stderr)
        sys.exit(1)
    peps = m[pep_col].astype('string').fillna('').str.strip()
    vals = [score_map.get(p, np.nan) if p else np.nan for p in peps.tolist()]
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
        print(f'[ERR] base 不存在: {BASE}', file=sys.stderr); sys.exit(1)
    if not RAW.exists():
        print(f'[ERR] raw 不存在: {RAW}', file=sys.stderr); sys.exit(1)

    m = pd.read_excel(BASE)
    print(f'[INFO] base 读入: {len(m)} 行 × {len(m.columns)} 列  ({BASE.name})',
          file=sys.stderr)
    if len(m) != EXPECTED_ROWS:
        print(f'[ERR] base 行数 {len(m)} ≠ {EXPECTED_ROWS}', file=sys.stderr); sys.exit(1)
    if 'MT_Subpeptide' not in m.columns:
        print('[ERR] base 缺 MT_Subpeptide', file=sys.stderr); sys.exit(1)
    for col in ('MT_TransHLA', 'WT_TransHLA'):
        if col in m.columns:
            print(f'[ERR] base 已含 {col}，疑重复 patch，中止', file=sys.stderr); sys.exit(1)

    score_map = load_score_map(RAW)
    m = lookup_col(m, 'MT_Subpeptide', score_map, 'MT_TransHLA')
    if 'WT_Subpeptide' in m.columns:
        m = lookup_col(m, 'WT_Subpeptide', score_map, 'WT_TransHLA')

    if len(m) != EXPECTED_ROWS:
        print(f'[ERR] 合并后行数 {len(m)} ≠ {EXPECTED_ROWS}！中止', file=sys.stderr); sys.exit(1)

    print('[LICENSE] TransHLA = MIT，可发表；非 DTU。'
          '⚠️ HLA-agnostic（同肽各 allele 同值，报告须标 caveat，同 Repitope）。',
          file=sys.stderr)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    m.to_excel(OUT, index=False, engine='openpyxl')
    new_cols = [c for c in ('MT_TransHLA', 'WT_TransHLA') if c in m.columns]
    print(f'\n[DONE] 输出: {OUT}\n[DONE] {len(m)} 行 × {len(m.columns)} 列（新增 {new_cols}）',
          file=sys.stderr)


if __name__ == '__main__':
    main()
