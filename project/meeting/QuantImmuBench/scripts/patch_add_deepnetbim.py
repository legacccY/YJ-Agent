#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_add_deepnetbim.py — QuantImmuBench §工具部署（合 DeepNetBim 一列进大表）
==================================================================
服务: quantimmu-bench / lever=补免疫原性组第 20 槽（DeepNetBim），合列进大表

设计哲学（仿 scripts/patch_add_mhcnuggets.py / patch_add_mhcseqnet.py，HLA-aware
单列自然键 join，不重建不丢 HLA-FIX）:
  - base = scripts/out/merged_all_tools_<NN>tools.xlsx 活真源（34247 行，已 HLA-FIX）。
    本脚本只贴 DeepNetBim 两列。
  - score 源 = scripts/out/newtools/DeepNetBim_DS1DS2_scores.csv（parse_output.py 产，
    含 MT_DeepNetBim / WT_DeepNetBim，已按 (subpeptide, 带星HLA) 对级回贴）。
    ⚠️ 注意：本 patch 直接读 parse 产出的 *_scores.csv（已是 universe 行序 + 带星 HLA），
       按 (MT_Subpeptide, HLA_Allele) / (WT_Subpeptide, HLA_Allele) 自然键查表贴回 base。
    （区别 mhcnuggets/mhcseqnet patch 读 raw.csv 自建 score_map —— DeepNetBim 因 raw 的
     mhc 是去星格式，重建带星已在 parse_output.py 做完，故 patch 直接复用 *_scores.csv。）

================== ⚠️ TODO（主线跑前必核 BASE 的 NN）==================
  当前最高 NN 随其它窗口推进会变动（MHCSeqNet / andy90 / 其它新工具串行 merge 时 NN 递增）。
  跑前先 `ls scripts/out/merged_all_tools_*tools.xlsx` 核**实际最高 NN**，
  把 BASE_NN 改成该 NN，OUT 自动出 NN+1。本脚本默认假设最高=27 → 出 28tools，
  ❗若实际不是 27 必须改下面 BASE_NN 常量。
=======================================================================

================== 方向说明（重要，勿删）==================
  DeepNetBim immuno_probability ∈[0,1]，**越高越免疫原**（用 immuno 模型，非 binding）。
  本脚本**不翻转**，直接用 → 越高越免疫原，与 benchmark 其他 MT_* 工具
  「越大越免疫原」约定一致。（对照 MHCnuggets 是 IC50 越低越强需取负，本工具不取负。）

================== HLA-FIX（同 mhcnuggets：自然键查 base 自身订正 HLA，不置 NaN）==================
  base 表 P101/P102 行 HLA 已订正；DeepNetBim_DS1DS2_scores.csv 在同一 universe 行序上回贴，
  HLA_Allele 带星与 base 同款 → 按 base 订正 HLA 自然键查表天然命中，无须手动置 NaN。

================== 许可（重要 caveat）==================
  DeepNetBim = github.com/Li-Lab-SJTU/DeepNetBim，**license=null（无 LICENSE 文件）**。
  用户已拍板可用，但 **发表前须邮件 Li-Lab-SJTU 索明确授权；只发聚合指标不二次分发权重**。
  → 非标准 OSI 许可，不写 PENDING_DTU sidecar，但 NOTES/PROVENANCE 标 license caveat。

================== 输出 ==================
  scripts/out/merged_all_tools_<NN+1>tools.xlsx （期望 34247 行）
    新增列: MT_DeepNetBim, WT_DeepNetBim

================== 跑法（主线串行）==================
  1) 先核最高 NN，改 BASE_NN 常量
  2) python scripts/patch_add_deepnetbim.py  → merged_all_tools_<NN+1>tools.xlsx
  3) python analysis/merge_metrics_NNtools.py → metrics_ds2_<NN+1>tools.csv 等（自动扫最高 NN）

依赖: pandas, openpyxl
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent          # scripts/
ROOT = HERE.parent                               # QuantImmuBench/

EXPECTED_ROWS = 34247

# MHCSeqNet(27)+andy90(28) 已 patch -> 当前最高=28 -> 出 29tools
BASE_NN = 28

BASE = ROOT / 'scripts' / 'out' / f'merged_all_tools_{BASE_NN}tools.xlsx'
SCORES = ROOT / 'scripts' / 'out' / 'newtools' / 'DeepNetBim_DS1DS2_scores.csv'
OUT = ROOT / 'scripts' / 'out' / f'merged_all_tools_{BASE_NN + 1}tools.xlsx'


def load_score_map(scores_path: Path) -> tuple:
    """
    读 DeepNetBim_DS1DS2_scores.csv，建两张查找表：
      mt_map {(MT_Subpeptide, HLA_Allele): MT_DeepNetBim}
      wt_map {(MT_Subpeptide, HLA_Allele): WT_DeepNetBim}  —— 注意 *_scores.csv 的
        WT_DeepNetBim 是该行 WT 子肽的分；但 scores.csv 仅保留 MT_Subpeptide 列
        （未带 WT_Subpeptide），故 WT 列仍以 (MT_Subpeptide, HLA) 行序键索引回 base。
    实际上 *_scores.csv 已是 universe 行序，本 patch 用 (MT_Subpeptide, HLA_Allele)
    自然键对齐 base 的同名键（base 也含 MT_Subpeptide/HLA_Allele），方向不翻转。
    """
    df = pd.read_csv(scores_path, encoding='utf-8')
    df.columns = [c.strip() for c in df.columns]

    for c in ('HLA_Allele', 'MT_Subpeptide', 'MT_DeepNetBim', 'WT_DeepNetBim'):
        if c not in df.columns:
            print(f'[ERR] {scores_path.name} 缺列 {c}（实有: {list(df.columns)}）',
                  file=sys.stderr)
            sys.exit(1)

    df['MT_Subpeptide'] = df['MT_Subpeptide'].astype(str).str.strip()
    df['HLA_Allele'] = df['HLA_Allele'].astype(str).str.strip()
    df['MT_DeepNetBim'] = pd.to_numeric(df['MT_DeepNetBim'], errors='coerce')
    df['WT_DeepNetBim'] = pd.to_numeric(df['WT_DeepNetBim'], errors='coerce')

    keys = list(zip(df['MT_Subpeptide'], df['HLA_Allele']))
    mt_map = {k: v for k, v in zip(keys, df['MT_DeepNetBim'].astype(float))}
    wt_map = {k: v for k, v in zip(keys, df['WT_DeepNetBim'].astype(float))}
    n_mt = int(df['MT_DeepNetBim'].notna().sum())
    print(f'[INFO] scores 读入: {len(df)} 行，MT 非空={n_mt}'
          f'（DeepNetBim 仅 9mer，预期低覆盖；方向不翻转）', file=sys.stderr)
    return mt_map, wt_map


def lookup_col(m: pd.DataFrame, score_map: dict, new_col: str) -> pd.DataFrame:
    """按 (m['MT_Subpeptide'], m['HLA_Allele']) 自然键查 score_map → 写 new_col。"""
    peps = m['MT_Subpeptide'].astype('string').fillna('').str.strip()
    hlas = m['HLA_Allele'].astype('string').fillna('').str.strip()
    keys = list(zip(peps.tolist(), hlas.tolist()))
    vals = [score_map.get(k, np.nan) if (k[0] and k[1]) else np.nan for k in keys]
    m[new_col] = pd.to_numeric(pd.Series(vals, index=m.index), errors='coerce')
    fill = int(m[new_col].notna().sum())
    pct = fill / len(m) * 100 if len(m) else 0.0
    # DeepNetBim 仅 9mer，低覆盖 ~17% 属预期，不报 WARN<50%
    print(f'[{new_col}] 填充率={fill}/{len(m)} ({pct:.1f}%)  [仅9mer，低覆盖属预期]',
          file=sys.stderr)
    return m


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    if not BASE.exists():
        print(f'[ERR] base 不存在: {BASE}\n'
              f'  ⚠️ 核实际最高 NN 并改脚本 BASE_NN 常量（当前={BASE_NN}）', file=sys.stderr)
        sys.exit(1)
    if not SCORES.exists():
        print(f'[ERR] scores 不存在: {SCORES}\n'
              f'  请先跑 HPC/deploy/deepnetbim/parse_output.py', file=sys.stderr)
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
    for col in ('MT_DeepNetBim', 'WT_DeepNetBim'):
        if col in m.columns:
            print(f'[ERR] base 已含 {col}，疑重复 patch，中止', file=sys.stderr)
            sys.exit(1)

    mt_map, wt_map = load_score_map(SCORES)

    m = lookup_col(m, mt_map, 'MT_DeepNetBim')
    m = lookup_col(m, wt_map, 'WT_DeepNetBim')

    if len(m) != EXPECTED_ROWS:
        print(f'[ERR] 合并后行数 {len(m)} ≠ {EXPECTED_ROWS}！中止', file=sys.stderr)
        sys.exit(1)

    if 'Patient_ID' in m.columns:
        pid = m['Patient_ID'].astype(str)
        pp = pid.str.contains('101') | pid.str.contains('102')
        n_pp = int(pp.sum())
        mt_pp = int(m.loc[pp, 'MT_DeepNetBim'].notna().sum())
        wt_pp = int(m.loc[pp, 'WT_DeepNetBim'].notna().sum())
        print(f'[HLA-FIX] P101/P102 行={n_pp}；MT 非空={mt_pp}，WT 非空={wt_pp}'
              f'（仅 9mer 命中）', file=sys.stderr)

    print('[LICENSE] DeepNetBim = Li-Lab-SJTU，**license=null（无 LICENSE）**；'
          '发表前须邮件索授权，只发聚合指标不二次分发权重 → 见 NOTES caveat。',
          file=sys.stderr)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    m.to_excel(OUT, index=False, engine='openpyxl')
    new_cols = [c for c in ('MT_DeepNetBim', 'WT_DeepNetBim') if c in m.columns]
    print(f'\n[DONE] 输出: {OUT}\n[DONE] {len(m)} 行 × {len(m.columns)} 列（新增 {new_cols}）',
          file=sys.stderr)


if __name__ == '__main__':
    main()
