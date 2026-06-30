#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_add_andy90.py — QuantImmuBench §工具部署（合 andy90 immunogenicity_predictor 一列进大表）
==================================================================
服务: quantimmu-bench / lever=补免疫原性组第 19 槽（andy90 amplitude），合 andy90 列进大表

设计（仿 scripts/patch_add_mhcseqnet.py，但 score 源已是 parse 后的 4-key 对齐 scores csv）:
  - base = scripts/out/merged_all_tools_<NN>tools.xlsx 活真源（34247 行，已 HLA-FIX）。
  - score 源 = scripts/out/newtools/Andy90ImmPred_DS1DS2_scores.csv
    （HPC/deploy/andy90_immpred/parse_output.py 产，已对齐 universe 4-key，含 MT_Andy90/WT_Andy90）。
  - 按 (Dataset, Peptide_ID, HLA_Allele, MT_Subpeptide) 四键 left-merge 贴 MT/WT_Andy90 两列。

⚠️ BASE_NN：跑前先 `ls scripts/out/merged_all_tools_*tools.xlsx` 核实际最高 NN，改 BASE_NN。

方向：amplitude = self*foreign/binding，**越高越免疫原，不翻转**（与 benchmark 其他 MT_* 一致）。
覆盖：andy90 仅 26/65 allele × 8-11mer → ~30% 覆盖（低覆盖，同 NetTepi，caveat 须标）。
许可：andy90 = github.com/andy90/immunogenicity_predictor，**MIT**，可发表，非 DTU pending。
HLA-FIX：scores 由 parse 在订正后 universe 上对齐 → P101/P102 天然安全。

输出: scripts/out/merged_all_tools_<NN+1>tools.xlsx，新增列 MT_Andy90, WT_Andy90
依赖: pandas, openpyxl
"""

import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent          # scripts/
ROOT = HERE.parent                               # QuantImmuBench/

EXPECTED_ROWS = 34247

# ⚠️ TODO(主线核实际最高 NN)：MHCSeqNet 后为 27 → 出 28。改这一个常量。
BASE_NN = 27

BASE = ROOT / 'scripts' / 'out' / f'merged_all_tools_{BASE_NN}tools.xlsx'
SCORES = ROOT / 'scripts' / 'out' / 'newtools' / 'Andy90ImmPred_DS1DS2_scores.csv'
OUT = ROOT / 'scripts' / 'out' / f'merged_all_tools_{BASE_NN + 1}tools.xlsx'

KEY = ['Dataset', 'Peptide_ID', 'HLA_Allele', 'MT_Subpeptide']
NEW_COLS = ['MT_Andy90', 'WT_Andy90']


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    if not BASE.exists():
        print(f'[ERR] base 不存在: {BASE}（核最高 NN 改 BASE_NN={BASE_NN}）', file=sys.stderr)
        sys.exit(1)
    if not SCORES.exists():
        print(f'[ERR] scores 不存在: {SCORES}', file=sys.stderr)
        sys.exit(1)

    m = pd.read_excel(BASE)
    print(f'[INFO] base: {len(m)} 行 × {len(m.columns)} 列 ({BASE.name})', file=sys.stderr)
    if len(m) != EXPECTED_ROWS:
        print(f'[ERR] base 行数 {len(m)} ≠ {EXPECTED_ROWS}', file=sys.stderr)
        sys.exit(1)
    for req in KEY:
        if req not in m.columns:
            print(f'[ERR] base 缺键列 {req}', file=sys.stderr)
            sys.exit(1)
    for col in NEW_COLS:
        if col in m.columns:
            print(f'[ERR] base 已含 {col}，疑重复 patch，中止', file=sys.stderr)
            sys.exit(1)

    s = pd.read_csv(SCORES, encoding='utf-8')
    for c in KEY + NEW_COLS:
        if c not in s.columns:
            print(f'[ERR] scores 缺列 {c}（实有 {list(s.columns)}）', file=sys.stderr)
            sys.exit(1)
    s = s[KEY + NEW_COLS].copy()
    # 四键统一为 str 防 dtype 不一致 join 漏
    for c in KEY:
        m[c] = m[c].astype(str).str.strip()
        s[c] = s[c].astype(str).str.strip()
    s = s.drop_duplicates(subset=KEY)

    before = len(m)
    m = m.merge(s, on=KEY, how='left')
    if len(m) != before:
        print(f'[ERR] merge 后行数 {len(m)} ≠ {before}（键不唯一？）', file=sys.stderr)
        sys.exit(1)

    for col in NEW_COLS:
        fill = int(m[col].notna().sum())
        print(f'[{col}] 填充率={fill}/{len(m)} ({100*fill/len(m):.1f}%)'
              + ('  [低覆盖 andy90 26/65 allele 预期]' if fill/len(m) < 0.5 else ''),
              file=sys.stderr)

    print('[LICENSE] andy90 = MIT，可发表；非 DTU pending → 不写 sidecar。', file=sys.stderr)
    print('[CAVEAT] andy90 低覆盖 ~30%（26/65 allele × 8-11mer），amplitude 越高越免疫原不翻转。',
          file=sys.stderr)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    m.to_excel(OUT, index=False, engine='openpyxl')
    print(f'\n[DONE] 输出: {OUT}\n[DONE] {len(m)} 行 × {len(m.columns)} 列（新增 {NEW_COLS}）',
          file=sys.stderr)


if __name__ == '__main__':
    main()
