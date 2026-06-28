# -*- coding: utf-8 -*-
"""
patch_merge_fixed.py — QuantImmuBench HLA bug 修复合表（patch 法，Entry HLA-AUDIT）

不重新 join（避开 context-dependent 工具如 PredIG/NOAH/NetCleave 的 (subpep,HLA) 键
折叠 bug，以及 HLA-agnostic 工具的键漏配 bug）。改为：旧 merged_16tools 行序与修正
backbone 完全 1:1 对齐（只 HLA_Allele 标签在 P101/P102 变），直接 patch：
  - 非 P101/P102 行：保留旧表精心做好的 join 分数（这些行未变）。
  - P101/P102 行：HLA-dependent 工具置 NaN（待 Phase B 重推理正确等位）；
                  HLA-agnostic 工具（NeoTImmuML/Repitope，分数仅依赖肽序列，
                  P101/P102 肽序列未变）保留旧分 = 仍有效。
  - 额外修 deepHLApan merge 传播 bug：旧 merge 对同 (subpep,HLA) 多 bb_idx 只填第一个
    → 用同组非空值回填 NaN（deepHLApan 非 context-dependent，同 (subpep,HLA) 同分）。

输出 scripts/out_fixed/merged_all_tools_fixed.xlsx（覆盖自然键版）。
"""
import os
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OLD_MERGE = os.path.join(ROOT, 'scripts', 'out', 'merged_all_tools_16tools.xlsx')
FIXED_BB  = os.path.join(ROOT, 'scripts', 'out_fixed', 'master_backbone.csv')
OUT       = os.path.join(ROOT, 'scripts', 'out_fixed', 'merged_all_tools_fixed.xlsx')

# HLA-agnostic 工具：分数仅依赖肽序列，P101/P102 肽未变 → 保留旧分
HLA_AGNOSTIC = {'MT_NeoTImmuML', 'WT_NeoTImmuML', 'MT_Repitope', 'WT_Repitope'}


def main():
    m = pd.read_excel(OLD_MERGE)
    bb = pd.read_csv(FIXED_BB)
    assert len(m) == len(bb), f'行数不一致 {len(m)} vs {len(bb)}'

    # 1. 行序对齐校验：bb_idx + MT_Subpeptide 必须逐行一致（只 HLA 应变）
    if 'bb_idx' in m.columns and 'bb_idx' in bb.columns:
        assert (m['bb_idx'].values == bb['bb_idx'].values).all(), 'bb_idx 行序不一致'
    assert (m['MT_Subpeptide'].astype(str).values ==
            bb['MT_Subpeptide'].astype(str).values).all(), 'MT_Subpeptide 行序不一致'

    # 2. 用修正 backbone 的 HLA_Allele 覆盖（修正 P101/P102 标签）
    m['HLA_Allele'] = bb['HLA_Allele'].values

    # 3. 工具列清单
    tool_cols = [c for c in m.columns
                 if c.startswith(('MT_', 'WT_'))
                 and 'Subpep' not in c and 'Full' not in c]
    extra_cols = [c for c in m.columns if c == 'pTuneos_hydro_defaulted']
    hla_dep_cols = [c for c in (tool_cols + extra_cols) if c not in HLA_AGNOSTIC]

    p101102 = m['Patient_ID'].astype(str).str.extract(r'(10[12])')[0].notna()
    n_pp = int(p101102.sum())

    # 4. deepHLApan 传播 bug 修复（在 nulling 之前，对全表非 context 工具回填）
    #    同 (subpep, HLA) 同分；用组内非空值回填 NaN。
    for sub_col, score_col in [('MT_Subpeptide', 'MT_deepHLApan'),
                               ('WT_Subpeptide', 'WT_deepHLApan')]:
        before = int(m[score_col].isna().sum())
        grp = m.groupby([sub_col, 'HLA_Allele'])[score_col]
        m[score_col] = grp.transform(lambda s: s.ffill().bfill())
        after = int(m[score_col].isna().sum())
        print(f'[deepHLApan] {score_col} NaN {before} -> {after} (回填 {before - after})')

    # 5. P101/P102：HLA-dependent 工具置 NaN（待重推理），HLA-agnostic 保留
    for c in hla_dep_cols:
        m.loc[p101102, c] = np.nan

    # 6. 报告
    print(f'\n[patch] P101/P102 行={n_pp}; HLA-dep 列 {len(hla_dep_cols)} 已置 NaN；'
          f'HLA-agnostic 保留: {sorted(HLA_AGNOSTIC)}')
    for c in sorted(HLA_AGNOSTIC):
        kept = int(m.loc[p101102, c].notna().sum())
        print(f'  [keep] {c} P101/P102 非空={kept}/{n_pp}')

    m.to_excel(OUT, index=False)
    print(f'\n[DONE] 写 {OUT}  shape={m.shape}')


if __name__ == '__main__':
    main()
