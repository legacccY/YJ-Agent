#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_add_neoag.py — QuantImmuBench G1 工具补齐 24→25/30（第 30 工具 = neoag，免疫原槽收尾）
==================================================================
服务: quantimmu-bench §工具部署 / lever=补满 30 工具最后 1 个免疫原槽（替搁置 NeoaPred）

⚠️ 跑法纪律：**本脚本由 merge DAG 节点 / 主线串行统一跑，本窗口只产出不执行 merge**
   （避免多窗并发写共享 xlsx 崩进程）。

设计（仿 scripts/patch_add_transhla.py，但 neoag = (MT,WT) **肽-对**级，不吃 HLA）:
  - base = scripts/out/merged_all_tools_24tools.xlsx 活真源（34247 行，当前最高 NN，含 ImmugenX）。
    本脚本只贴 neoag 两列（MT_Neoag 承分 / WT_Neoag 结构 NaN）。
    # TODO（主线核）：若 24tools.xlsx 已被更高 NN 取代，把 BASE 指到实际最高 NN tools xlsx。
  - score 源 = HPC/deploy/neoag/neoag_raw.csv（列 mt_peptide, wt_peptide, score；
    R/caret GBM 跑出，CPU 秒~分钟级）。
  - **(MT,WT) 对级 + HLA-agnostic**：neoag 模型吃 (mut, wt, 位号) 出一个 neoantigen 免疫原分，
    不吃 HLA → score_map 键 = (MT, WT) 肽-对（非含 HLA）；同对各 HLA_Allele 行广播同值（同 Repitope/TransHLA）。
    → 按 base 的 (MT_Subpeptide, WT_Subpeptide) **对级**查表。

================== 方向（⚠️TODO 官方未核，重要）==================
  neoag GBM immunogenicity 分一般「越高越免疫原」→ 默认 **不翻转**直接用 MT_Neoag。
  ⚠️ 本机无外网未核官方 README 方向；主窗 clone github.com/vincentlaboratories/neoag 后核：
     越低越免疫原 → 把 raw 的 score 取负（在 parse_output.py 用 --flip，或此处 FLIP=True）。
  MT_Neoag = (MT,WT) 对的 neoag 分（benchmark 主用列）。
  WT_Neoag = **结构性 NaN**（neoag 不对 WT 单独打 neoantigen 分；仅为 MT_/WT_ 双列 schema 对齐保留，
             主线可按需丢弃）。

================== HLA-FIX ==================
  (MT,WT) 对级查表与 HLA 无关 → P101/P102 HLA 订正不影响 neoag 列，天然安全（同 TransHLA）。

================== 许可 ==================
  neoag = **non-commercial research license**（数字可发表，学术非商用）。非 DTU pending → 不写 sidecar。
  （唯一红线：别把 neoag repo 代码/Final_gbm_model.rds 进公开 repo；与本合表无关。）

================== 输出 ==================
  scripts/out/merged_all_tools_25tools.xlsx（期望 34247 行）
    新增列: MT_Neoag, WT_Neoag(全 NaN)

================== 跑法（主线串行，本窗不跑）==================
  1) python scripts/patch_add_neoag.py  → merged_all_tools_25tools.xlsx
  2) python analysis/merge_metrics_NNtools.py → metrics_ds2_25tools.csv + per_patient_*（自动扫最高 NN）

依赖: pandas, openpyxl
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent          # scripts/
ROOT = HERE.parent                               # QuantImmuBench/

EXPECTED_ROWS = 34247

BASE = ROOT / 'scripts' / 'out' / 'merged_all_tools_24tools.xlsx'
RAW = ROOT / 'HPC' / 'deploy' / 'neoag' / 'neoag_raw.csv'
OUT = ROOT / 'scripts' / 'out' / 'merged_all_tools_25tools.xlsx'

SCORE_COL = 'score'   # raw 主分数列名（run_neoag.R 输出固定 mt_peptide,wt_peptide,score）

# ⚠️TODO 官方未核：分方向。False=越高越免疫原直接用；True=取负翻转。
FLIP = False


def load_pair_score_map(raw_path: Path) -> dict:
    """读 neoag_raw.csv，建 {(MT,WT): score}（(肽,肽) 对级，HLA-agnostic）。"""
    df = pd.read_csv(raw_path, encoding='utf-8')
    df.columns = [c.strip() for c in df.columns]
    for c in ('mt_peptide', 'wt_peptide', SCORE_COL):
        if c not in df.columns:
            print(f'[ERR] {raw_path.name} 缺列 {c}（实有: {list(df.columns)}）', file=sys.stderr)
            sys.exit(1)
    df['mt_peptide'] = df['mt_peptide'].astype(str).str.strip().str.upper()
    df['wt_peptide'] = df['wt_peptide'].astype(str).str.strip().str.upper()
    df[SCORE_COL] = pd.to_numeric(df[SCORE_COL], errors='coerce')
    df = df[(df['mt_peptide'] != '') & (df['wt_peptide'] != '') & df[SCORE_COL].notna()]
    vals = (-df[SCORE_COL].astype(float)) if FLIP else df[SCORE_COL].astype(float)
    score_map = dict(zip(zip(df['mt_peptide'], df['wt_peptide']), vals))
    print(f'[INFO] score_map 读入: {len(score_map)} 条唯一 (MT,WT) 对'
          f'（raw 行 {len(df)}，FLIP={FLIP}）', file=sys.stderr)
    return score_map


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    if not BASE.exists():
        print(f'[ERR] base 不存在: {BASE}', file=sys.stderr); sys.exit(1)
    if not RAW.exists():
        print(f'[ERR] raw 不存在: {RAW}（先跑 neoag 四件套 prep→run→产 raw）', file=sys.stderr); sys.exit(1)

    m = pd.read_excel(BASE)
    print(f'[INFO] base 读入: {len(m)} 行 × {len(m.columns)} 列  ({BASE.name})', file=sys.stderr)
    if len(m) != EXPECTED_ROWS:
        print(f'[ERR] base 行数 {len(m)} ≠ 预期 {EXPECTED_ROWS}', file=sys.stderr); sys.exit(1)
    for req in ('MT_Subpeptide', 'WT_Subpeptide'):
        if req not in m.columns:
            print(f'[ERR] base 缺必要列 {req}（neoag 需 (MT,WT) 对级查表）', file=sys.stderr); sys.exit(1)
    for col in ('MT_Neoag', 'WT_Neoag'):
        if col in m.columns:
            print(f'[ERR] base 已含 {col}，疑重复 patch，中止', file=sys.stderr); sys.exit(1)

    score_map = load_pair_score_map(RAW)

    mt = m['MT_Subpeptide'].astype('string').fillna('').str.strip().str.upper()
    wt = m['WT_Subpeptide'].astype('string').fillna('').str.strip().str.upper()
    keys = list(zip(mt.tolist(), wt.tolist()))
    vals = [score_map.get(k, np.nan) if (k[0] and k[1]) else np.nan for k in keys]
    m['MT_Neoag'] = pd.to_numeric(pd.Series(vals, index=m.index), errors='coerce')
    # WT_Neoag 结构性 NaN（neoag 无独立 WT neoantigen 分；schema 对齐保留）
    m['WT_Neoag'] = np.nan

    fill = int(m['MT_Neoag'].notna().sum())
    pct = fill / len(m) * 100 if len(m) else 0.0
    flag = '  [WARN<50%]' if pct < 50 else ''
    print(f'[MT_Neoag] 填充率={fill}/{len(m)} ({pct:.1f}%){flag}', file=sys.stderr)
    print('[WT_Neoag] 结构性全 NaN（neoag 不打独立 WT 分）', file=sys.stderr)

    if len(m) != EXPECTED_ROWS:
        print(f'[ERR] 合并后行数 {len(m)} ≠ {EXPECTED_ROWS}！中止', file=sys.stderr); sys.exit(1)

    if 'Patient_ID' in m.columns:
        pid = m['Patient_ID'].astype(str)
        pp = pid.str.contains('101') | pid.str.contains('102')
        print(f'[HLA-FIX] P101/P102 行={int(pp.sum())}；MT_Neoag 非空={int(m.loc[pp, "MT_Neoag"].notna().sum())}'
              '（对级查表，HLA 订正不影响，天然安全）', file=sys.stderr)

    print('[LICENSE] neoag = non-commercial research license，数字可发表（学术非商用）；'
          '非 DTU pending → 不写 sidecar。⚠️ HLA-agnostic caveat（同对各 allele 同值）。', file=sys.stderr)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    m.to_excel(OUT, index=False, engine='openpyxl')
    print(f'\n[DONE] 输出: {OUT}\n[DONE] {len(m)} 行 × {len(m.columns)} 列（新增 [MT_Neoag, WT_Neoag]）',
          file=sys.stderr)


if __name__ == '__main__':
    main()
