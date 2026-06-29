#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_add_bigmhc_el.py — QuantImmuBench G1 工具补齐 18→19/30
==================================================================
服务: quantimmu-bench / lever=G1 工具补齐（合 BigMHC_EL 一列进大表）

设计哲学（仿 scripts/patch_add_icerfire_nettepi.py + HPC/.../parse_output.py）:
  - **不重 join、不重建**：base = scripts/out/merged_all_tools_18tools.xlsx 是活
    真源（34247 行 × 59 列，A1 产出，已 HLA-FIX，已含 MT_ICERFIRE/MT_NetTepi）。
    本脚本只在它身上贴 BigMHC_EL 分数列，绝不从头重 join（会丢 HLA-FIX）。
  - join 机制照 parse_output.py 的「(peptide, mhc_str) 自然键」分支：BigMHC 输出
    .prd 的 mhc 列保留原始 HLA 字符串（HLA-A*01:01 等），与 base 表的 HLA_Allele
    列同款格式（本脚本上游 Bash 已核：universe/uniq_pep_hla/EL .prd 三方 HLA 列
    均为 'HLA-X*NN:NN'，与 base 表 HLA_Allele 一致）。
    → 直接 (MT_Subpeptide, HLA_Allele) / (WT_Subpeptide, HLA_Allele) 字符串查表。
    base 表自带 bb_idx，但本批走自然键 join（与 A1 icerfire 走 bb_idx 不同），
    因为 .prd 输出无 bb_idx 列、只有 (mhc, pep)，自然键是天然主键。

================== 输入 ==================
  base:  scripts/out/merged_all_tools_18tools.xlsx   (34247 行 × 59 列)
         含列 bb_idx / Patient_ID / Peptide_ID / Elispot /
              MT_Subpeptide / WT_Subpeptide / HLA_Allele / MT_BigMHC(=IM) / ...

  EL .prd: HPC/deploy/bigmhc_im/bigmhc_inputs/bigmhc_el_output.prd
           53583 行含表头（53582 数据行）。列: mhc, pep, tgt, len, BigMHC_EL
           BigMHC_EL ∈ [0,1]，eluted ligand 呈递概率（sigmoid 后）。
           上游 Bash 已核：.prd 数据行数 53582 == uniq_pep_hla.csv 53582
           → BigMHC EL 对所有输入 (pep,hla) 均出分、无跳过，命中率应近 100%。

================== 方向说明（重要，勿删）==================
  BigMHC_EL 高值 = 越可能被呈递 = 越可能是真免疫原表位，与 benchmark 其他
  MT_* 工具「越大越免疫原」约定一致 → **本脚本不翻向**，直接使用。
  （与同源 MT_BigMHC=BigMHC_IM 方向一致；IM=免疫原性概率，EL=呈递概率，
    两列各自独立保留，故 EL 命名 MT_BigMHC_EL 以区分既有 MT_BigMHC。）

================== HLA-FIX 核查（上游 Bash 已核，勿删）==================
  本脚本按 base 表**自身的** (MT_Subpeptide, HLA_Allele) 查 EL score_map，
  故 join 天然对齐 base 表已订正的 HLA（HLA-FIX backbone），**无须手动置 NaN**：
    - base 表 P101/P102 行的 HLA 已是订正真值
      (P101={A*66:01,B*40:01,B*57:01,C*06:02} / P102={A*02:01,B*35:03,B*38:01})。
    - 上游 Bash 已核：这些订正 HLA 在 uniq_pep_hla.csv 与 EL .prd 中均存在
      (HLA-A*66:01=161 行 / HLA-B*57:01=940 行 / HLA-B*35:03=112 行 等全有)
      → EL 是在「订正 backbone」上重新算的，score_map 含订正 (pep,hla) 键。
    - 因此 base 表 P101/P102 行按其订正 HLA 字符串查表即天然命中正确分数，
      与 A1 icerfire/nettepi 「bb_idx 对齐、不置 NaN」处理等价（手段不同、结果同）。

================== 许可（重要，与 A1 不同）==================
  BigMHC = JHU Karchin Lab 学术许可（academic / non-commercial），
  非商用可发表 —— **不是 DTU pending consent**（区别于 ICERFIRE/NetTepi）。
  → 本脚本**不写** PENDING_DTU sidecar、不追加任何 pending 列表。

================== 输出 ==================
  scripts/out/merged_all_tools_19tools.xlsx   (期望 34247 行 × 61 列)
    新增列: MT_BigMHC_EL, WT_BigMHC_EL

================== 校验 ==================
  - 读入/合并后行数必须 == 34247，否则 sys.exit(1)
  - base 已含 MT_BigMHC_EL → 疑重复 patch，中止
  - 打印 MT_BigMHC_EL / WT_BigMHC_EL 填充率 + P101/P102 行非空数

================== 跑法（主线串行，本脚本只写不跑）==================
  1) python scripts/patch_add_bigmhc_el.py
       预期产出: scripts/out/merged_all_tools_19tools.xlsx (34247×61)
  2) python analysis/merge_metrics_NNtools.py
       自动扫 scripts/out/ 下最高 NN → 选 19tools；MT_BigMHC_EL 不在其 EXCLUDE
       集合，会被自动当独立工具评估（MT_BigMHC=IM 同样保留为独立工具）。
       预期产出: analysis/metrics_ds2_19tools.csv + per_patient_spearman_19tools.csv

依赖: pandas, openpyxl
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent          # scripts/
ROOT = HERE.parent                               # QuantImmuBench/

EXPECTED_ROWS = 34247

BASE = ROOT / 'scripts' / 'out' / 'merged_all_tools_18tools.xlsx'
EL_PRD = (ROOT / 'HPC' / 'deploy' / 'bigmhc_im' / 'bigmhc_inputs'
          / 'bigmhc_el_output.prd')
OUT = ROOT / 'scripts' / 'out' / 'merged_all_tools_19tools.xlsx'

EL_COL = 'BigMHC_EL'        # .prd 中的分数列名（上游已核实）


def load_el_score_map(prd_path: Path) -> dict:
    """
    读 BigMHC EL 输出 .prd（标准 CSV），建 score_map {(pep, mhc): float}。
    照 parse_output.load_bigmhc_prd 的自然键逻辑，只换列名 BigMHC_IM→BigMHC_EL。
    mhc 列存原始 HLA 字符串（HLA-A*02:01），pep 为肽序列，直接用于 join。
    """
    df = pd.read_csv(prd_path, encoding='utf-8')
    df.columns = [c.strip() for c in df.columns]

    if EL_COL not in df.columns:
        print(f'[ERR] {prd_path.name} 缺分数列 {EL_COL}（实有列: {list(df.columns)}）\n'
              '      TODO: 核实 BigMHC -m=el 输出列名是否为 BigMHC_EL。',
              file=sys.stderr)
        sys.exit(1)
    for c in ('pep', 'mhc'):
        if c not in df.columns:
            print(f'[ERR] {prd_path.name} 缺 {c} 列（实有列: {list(df.columns)}）',
                  file=sys.stderr)
            sys.exit(1)

    df['pep'] = df['pep'].astype(str).str.strip()
    df['mhc'] = df['mhc'].astype(str).str.strip()
    df[EL_COL] = pd.to_numeric(df[EL_COL], errors='coerce')

    # 丢空键/NaN 分数，最后一条同键覆盖（去重防多映射）
    df = df[(df['pep'] != '') & (df['mhc'] != '') & df[EL_COL].notna()]
    score_map = dict(zip(zip(df['pep'], df['mhc']), df[EL_COL].astype(float)))

    print(f'[INFO] EL score_map 读入: {len(score_map)} 条唯一 (pep,mhc) 键'
          f'（.prd 数据行 {len(df)}）', file=sys.stderr)
    return score_map


def lookup_col(m: pd.DataFrame, pep_col: str, score_map: dict,
               new_col: str) -> pd.DataFrame:
    """
    按 (m[pep_col], m['HLA_Allele']) 自然键查 score_map → 写新列 new_col。
    空肽/空 HLA → NaN。纯 pandas/numpy（zip + map），不改行数。
    """
    if pep_col not in m.columns:
        print(f'[ERR] base 缺 {pep_col} 列，无法自然键 join', file=sys.stderr)
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
        print(f'[ERR] base 大表不存在: {BASE}', file=sys.stderr)
        sys.exit(1)
    if not EL_PRD.exists():
        print(f'[ERR] EL .prd 不存在: {EL_PRD}', file=sys.stderr)
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
    for col in ('MT_BigMHC_EL', 'WT_BigMHC_EL'):
        if col in m.columns:
            print(f'[ERR] base 已含 {col} 列，疑重复 patch，中止', file=sys.stderr)
            sys.exit(1)

    score_map = load_el_score_map(EL_PRD)

    # ── MT 侧（主输出）──────────────────────────────────────────────────────────
    m = lookup_col(m, 'MT_Subpeptide', score_map, 'MT_BigMHC_EL')

    # ── WT 侧（对照；base 有 WT_Subpeptide 列才加，与 parse_output 一致）──────────
    if 'WT_Subpeptide' in m.columns:
        m = lookup_col(m, 'WT_Subpeptide', score_map, 'WT_BigMHC_EL')
    else:
        print('[INFO] base 无 WT_Subpeptide 列 → 跳过 WT_BigMHC_EL', file=sys.stderr)

    # ── 行数硬校验 ──────────────────────────────────────────────────────────────
    if len(m) != EXPECTED_ROWS:
        print(f'[ERR] 合并后行数 {len(m)} ≠ 预期 {EXPECTED_ROWS}！中止写出',
              file=sys.stderr)
        sys.exit(1)

    # ── HLA-FIX P101/P102 报告（自然键查表天然对齐订正 HLA，不置 NaN，见头注）────
    if 'Patient_ID' in m.columns:
        pid = m['Patient_ID'].astype(str)
        pp = pid.str.contains('101') | pid.str.contains('102')
        n_pp = int(pp.sum())
        mt_pp = int(m.loc[pp, 'MT_BigMHC_EL'].notna().sum())
        wt_pp = (int(m.loc[pp, 'WT_BigMHC_EL'].notna().sum())
                 if 'WT_BigMHC_EL' in m.columns else 0)
        print(f'[HLA-FIX] P101/P102 行={n_pp}（按订正 HLA 自然键查表，天然对齐不置 NaN）；'
              f'其中 MT_BigMHC_EL 非空={mt_pp}，WT_BigMHC_EL 非空={wt_pp}',
              file=sys.stderr)

    # ── 许可说明：BigMHC = JHU 学术许可，非 DTU pending，不写 sidecar ──────────────
    print('[LICENSE] BigMHC = JHU Karchin Lab 学术/非商用许可，可发表；'
          '非 DTU pending → 不写 PENDING_DTU sidecar。', file=sys.stderr)

    # ── 输出 ────────────────────────────────────────────────────────────────────
    OUT.parent.mkdir(parents=True, exist_ok=True)
    m.to_excel(OUT, index=False, engine='openpyxl')
    print(f'\n[DONE] 输出: {OUT}', file=sys.stderr)
    new_cols = [c for c in ('MT_BigMHC_EL', 'WT_BigMHC_EL') if c in m.columns]
    print(f'[DONE] 最终表: {len(m)} 行 × {len(m.columns)} 列（新增 {new_cols}）',
          file=sys.stderr)


if __name__ == '__main__':
    main()
