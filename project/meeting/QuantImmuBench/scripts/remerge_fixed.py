#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
remerge_fixed.py — QuantImmuBench HLA-AUDIT 修复：重建全工具合表
=================================================================
服务: quantimmu-bench / lever=HLA-AUDIT backbone 修复 + deepHLApan merge bug 修复

基于修正 backbone (out_fixed/master_backbone.csv) 重建全工具合表，
全部使用自然键 join（根治 deepHLApan NaN 传播 bug）：
  - 自然键 (MT_Subpeptide, HLA_Allele) → 同一 (subpep,HLA) 的所有 bb_idx 全填（BUG 修复）
  - P101/P102 行因正确等位不在原始 CSV → 预期大量 NaN（待 Phase B 重推理，正常）
  - 列结构与 merged_all_tools_16tools.xlsx 完全一致

输出: scripts/out_fixed/merged_all_tools_fixed.xlsx

NaN 报告（每工具）:
  (a) 总 NaN 行数
  (b) P101/P102 NaN（Patient_ID in {101,102}）= 待重推理计数
  (c) 非 P101/P102 NaN（应≈旧表水平，若暴增则 join 写错）

末尾断言：非 P101/P102 行与旧表 merged_all_tools_16tools.xlsx 分数几乎全等。

跑法:
  python scripts/remerge_fixed.py

依赖: pandas, openpyxl
Windows 规范: 纯 pandas 操作，无多进程
"""

import os
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# UTF-8 stdout（Windows 必要）
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

HERE = Path(__file__).resolve().parent          # scripts/
ROOT = HERE.parent                               # project/meeting/QuantImmuBench/

# ── 路径常量 ─────────────────────────────────────────────────────────────────
FIXED_BB     = HERE / 'out_fixed' / 'master_backbone.csv'
OLD_MERGED   = HERE / 'out' / 'merged_all_tools_16tools.xlsx'
OUT_XLSX     = HERE / 'out_fixed' / 'merged_all_tools_fixed.xlsx'
OUT_DIR      = HERE / 'out'
NEWTOOLS_DIR = OUT_DIR / 'newtools'
HPC_DIR      = ROOT / 'HPC'
PTUNEOS_DIR  = HERE / 'ptuneos'

# P101/P102 = Patient_ID 101, 102（backbone 数值型）
P101P102_IDS = {101, 102}
EXPECTED_ROWS = 34247


# ── HLA 格式转换 ──────────────────────────────────────────────────────────────

def hla_no_colon(hla_std: str) -> str:
    """HLA-A*24:02 → HLA-A*2402（去冒号，保留星号；DeepImmuno 格式）"""
    return str(hla_std).replace(':', '')


def hla_to_improve(hla_std: str) -> str:
    """HLA-A*02:01 → HLA-A02:01（去星号，保留冒号；IMPROVE map 格式）"""
    return str(hla_std).replace('*', '')


def hla_to_prime(hla_std: str) -> str:
    """HLA-A*24:02 → A2402（去 HLA- + 去星 + 去冒号；PRIME 文件名格式）"""
    s = str(hla_std).strip()
    if s.upper().startswith('HLA-'):
        s = s[4:]
    return s.replace('*', '').replace(':', '')


def hla_norm_allele(hla_std: str) -> str:
    """HLA-A*24:02 → A2402（HLAthena 文件名格式，与 hla_to_prime 等价）"""
    return str(hla_std).replace('HLA-', '').replace('*', '').replace(':', '').strip()


def hla_no_star(hla_std: str) -> str:
    """HLA-A*24:02 → HLA-A24:02（去星号，保留 HLA- 前缀；deepHLApan 输出格式）"""
    return str(hla_std).replace('*', '')


# ── NaN 报告 ─────────────────────────────────────────────────────────────────

def report_nan(label: str, series: pd.Series, mask_pp: pd.Series) -> None:
    """打印三联 NaN 统计：总 / P101P102 / 非P101P102。"""
    total_nan = int(series.isna().sum())
    pp_nan    = int(series[mask_pp].isna().sum())
    npp_nan   = int(series[~mask_pp].isna().sum())
    total     = len(series)
    pp_tot    = int(mask_pp.sum())
    npp_tot   = total - pp_tot
    print(
        f'  [{label}]'
        f'  总NaN={total_nan}/{total}'
        f'  P101/P102 NaN={pp_nan}/{pp_tot}(待重推理)'
        f'  非P101/P102 NaN={npp_nan}/{npp_tot}'
    )


# ============================================================
# 工具 1: DeepImmuno
# ============================================================

def merge_deepimmuno(result: pd.DataFrame) -> pd.DataFrame:
    """
    DeepImmuno 回贴（自然键）。
    key = (peptide, HLA_no_colon)，HLA 格式 HLA-A*2402（有星无冒号）。
    """
    p = OUT_DIR / 'deepimmuno_full_result.txt'
    if not p.exists():
        print(f'[DeepImmuno] 跳过：文件不存在 {p}', file=sys.stderr)
        result['MT_DeepImmuno'] = np.nan
        result['WT_DeepImmuno'] = np.nan
        return result

    di = pd.read_csv(p, sep='\t', encoding='utf-8')
    di.columns = [c.strip() for c in di.columns]
    # 标准化 HLA：去冒号（deepimmuno 输出已是无冒号格式，防御性再做一次）
    di['_hla_di'] = di['HLA'].astype(str).str.replace(':', '', regex=False)
    di['peptide'] = di['peptide'].astype(str).str.strip()
    di_dedup = di[['peptide', '_hla_di', 'immunogenicity']].drop_duplicates(
        subset=['peptide', '_hla_di']
    )

    # backbone 侧也去冒号
    result['_hla_di'] = result['HLA_Allele'].astype(str).str.replace(':', '', regex=False)

    # MT join
    mt_join = di_dedup.rename(columns={
        'peptide': 'MT_Subpeptide',
        'immunogenicity': 'MT_DeepImmuno',
    })
    result = result.merge(mt_join, on=['MT_Subpeptide', '_hla_di'], how='left')

    # WT join（重用 _hla_di）
    wt_join = di_dedup.rename(columns={
        'peptide': 'WT_Subpeptide',
        'immunogenicity': 'WT_DeepImmuno',
    })
    result = result.merge(wt_join, on=['WT_Subpeptide', '_hla_di'], how='left')

    result.drop(columns=['_hla_di'], inplace=True, errors='ignore')
    print(
        f'[DeepImmuno] MT_DeepImmuno 非空={result["MT_DeepImmuno"].notna().sum()}'
        f'  WT_DeepImmuno 非空={result["WT_DeepImmuno"].notna().sum()}',
        file=sys.stderr,
    )
    return result


# ============================================================
# 工具 2: PredIG（位置 join 获取 MT/WT 标记 → 自然键）
# ============================================================

_PREDIG_EXTRA = ['NOAH', 'NetCleave', 'Stab_peptide', 'TCR_contact']


def merge_predig(result: pd.DataFrame) -> pd.DataFrame:
    """
    PredIG 回贴（位置 join 后转自然键）。
    步骤：
      1. 位置 join predig_full_out.csv × out/predig_input.csv → 获取 protein_name（含 |MT|/|WT|）
      2. 按 (epitope, HLA_allele, is_MT) 建查找表
      3. 自然键 (MT_Subpeptide, HLA_Allele) → MT_PredIG 等；同 (subpep,HLA) 的所有 bb_idx 全填。
    注意：使用 out/predig_input.csv（工具实际跑的输入），不是 out_fixed/
    """
    out_path = OUT_DIR / 'predig_full_out.csv'
    inp_path = OUT_DIR / 'predig_input.csv'
    null_cols = ['MT_PredIG', 'WT_PredIG'] \
                + [f'MT_{c}' for c in _PREDIG_EXTRA] \
                + [f'WT_{c}' for c in _PREDIG_EXTRA]
    if not out_path.exists() or not inp_path.exists():
        print(f'[PredIG] 跳过：文件缺失 ({out_path.name} / {inp_path.name})', file=sys.stderr)
        for col in null_cols:
            result[col] = np.nan
        return result

    out_df = pd.read_csv(out_path, encoding='utf-8')
    inp_df = pd.read_csv(inp_path, encoding='utf-8')
    out_df.columns = [c.strip() for c in out_df.columns]
    inp_df.columns = [c.strip() for c in inp_df.columns]

    if len(out_df) != len(inp_df):
        print(
            f'[PredIG][WARN] 行数不符 out={len(out_df)} inp={len(inp_df)}，'
            '跳过（位置 join 要求等行数）',
            file=sys.stderr,
        )
        for col in null_cols:
            result[col] = np.nan
        return result

    # 位置 join：贴入 protein_name，确定 MT/WT
    out_df = out_df.copy()
    out_df['protein_name'] = inp_df['protein_name'].values
    out_df['_is_MT'] = out_df['protein_name'].str.contains('|MT|', regex=False)

    actual_extra = [c for c in _PREDIG_EXTRA if c in out_df.columns]

    def _predig_side(is_mt_flag: bool, subpep_col: str, predig_col: str) -> pd.DataFrame:
        rows = out_df[out_df['_is_MT'] == is_mt_flag].copy()
        keep = ['epitope', 'HLA_allele', 'PredIG'] + actual_extra
        avail = [c for c in keep if c in rows.columns]
        side_df = rows[avail].drop_duplicates(subset=['epitope', 'HLA_allele'])
        side_label = 'MT' if is_mt_flag else 'WT'
        rename = {
            'epitope': subpep_col,
            'HLA_allele': 'HLA_Allele',
            'PredIG': predig_col,
        }
        for c in actual_extra:
            rename[c] = f'{side_label}_{c}'
        return side_df.rename(columns=rename)

    mt_join = _predig_side(True, 'MT_Subpeptide', 'MT_PredIG')
    wt_join = _predig_side(False, 'WT_Subpeptide', 'WT_PredIG')

    result = result.merge(mt_join, on=['MT_Subpeptide', 'HLA_Allele'], how='left')
    result = result.merge(wt_join, on=['WT_Subpeptide', 'HLA_Allele'], how='left')

    print(
        f'[PredIG] MT_PredIG 非空={result["MT_PredIG"].notna().sum()}'
        f'  WT_PredIG 非空={result["WT_PredIG"].notna().sum()}',
        file=sys.stderr,
    )
    return result


# ============================================================
# 工具 3: IMPROVE
# ============================================================

def merge_improve(result: pd.DataFrame) -> pd.DataFrame:
    """
    IMPROVE 回贴（自然键）。
    key = (Mut_peptide, WT_peptide, HLA_allele_no_star)；
    同 3-key 多行取均值（per-patient 重复）。
    """
    p = OUT_DIR / 'improve_full_result.tsv'
    if not p.exists():
        print(f'[IMPROVE] 跳过：{p}', file=sys.stderr)
        result['MT_IMPROVE_mean_prediction_rf'] = np.nan
        return result

    im = pd.read_csv(p, sep='\t', encoding='utf-8')
    im.columns = [c.strip() for c in im.columns]
    if 'WT_peptide' not in im.columns and 'Norm_peptide' in im.columns:
        im = im.rename(columns={'Norm_peptide': 'WT_peptide'})

    # HLA: 去星号（IMPROVE 格式 HLA-A02:01，无星）
    im['_hla_imp'] = im['HLA_allele'].astype(str).str.replace('*', '', regex=False)

    # 同 3-key 多行（不同 patient 特征）→ 取均值
    im_grp = (
        im.groupby(['Mut_peptide', 'WT_peptide', '_hla_imp'])['mean_prediction_rf']
        .mean()
        .reset_index()
        .rename(columns={
            'Mut_peptide':         'MT_Subpeptide',
            'WT_peptide':          'WT_Subpeptide',
            '_hla_imp':            '_hla_imp_k',
            'mean_prediction_rf':  'MT_IMPROVE_mean_prediction_rf',
        })
    )

    result['_hla_imp_k'] = result['HLA_Allele'].astype(str).str.replace('*', '', regex=False)
    result = result.merge(
        im_grp, on=['MT_Subpeptide', 'WT_Subpeptide', '_hla_imp_k'], how='left'
    )
    result.drop(columns=['_hla_imp_k'], inplace=True, errors='ignore')
    print(
        f'[IMPROVE] MT_IMPROVE_mean_prediction_rf 非空='
        f'{result["MT_IMPROVE_mean_prediction_rf"].notna().sum()}',
        file=sys.stderr,
    )
    return result


# ============================================================
# 工具 4: NeoTImmuML（HLA-agnostic，peptide → score）
# ============================================================

def merge_neotimmuml(result: pd.DataFrame) -> pd.DataFrame:
    """NeoTImmuML（HLA-agnostic）：MT_Subpeptide / WT_Subpeptide → neotimmuml_score。"""
    p = OUT_DIR / 'neotimmuml_scores.csv'
    if not p.exists():
        print(f'[NeoTImmuML] 跳过：{p}', file=sys.stderr)
        result['MT_NeoTImmuML'] = np.nan
        result['WT_NeoTImmuML'] = np.nan
        return result

    neo = pd.read_csv(p, encoding='utf-8')
    neo.columns = [c.strip() for c in neo.columns]
    neo['Peptide'] = neo['Peptide'].astype(str).str.strip()
    neo_dedup = neo[['Peptide', 'neotimmuml_score']].drop_duplicates('Peptide')

    mt_join = neo_dedup.rename(columns={'Peptide': 'MT_Subpeptide', 'neotimmuml_score': 'MT_NeoTImmuML'})
    result = result.merge(mt_join, on='MT_Subpeptide', how='left')

    wt_join = neo_dedup.rename(columns={'Peptide': 'WT_Subpeptide', 'neotimmuml_score': 'WT_NeoTImmuML'})
    result = result.merge(wt_join, on='WT_Subpeptide', how='left')

    print(
        f'[NeoTImmuML] MT 非空={result["MT_NeoTImmuML"].notna().sum()}'
        f'  WT 非空={result["WT_NeoTImmuML"].notna().sum()}',
        file=sys.stderr,
    )
    return result


# ============================================================
# 工具 5: pTuneos（自然键 (MT_pep, WT_pep, HLA_type)）
# ============================================================

def merge_ptuneos(result: pd.DataFrame) -> pd.DataFrame:
    """pTuneos 回贴（自然键）。join 键 = (MT_Subpeptide, WT_Subpeptide, HLA_Allele)。"""
    p = PTUNEOS_DIR / 'ptuneos_unique_output.tsv'
    if not p.exists():
        print(f'[pTuneos] 跳过：{p}', file=sys.stderr)
        result['MT_pTuneos'] = np.nan
        result['pTuneos_hydro_defaulted'] = np.nan
        return result

    pto = pd.read_csv(p, sep='\t', encoding='utf-8')
    pto.columns = [c.strip() for c in pto.columns]
    slim = (
        pto[['MT_pep', 'WT_pep', 'HLA_type', 'model_pro', 'hydro_defaulted']]
        .copy()
        .rename(columns={
            'MT_pep':        'MT_Subpeptide',
            'WT_pep':        'WT_Subpeptide',
            'HLA_type':      'HLA_Allele',
            'model_pro':     'MT_pTuneos',
            'hydro_defaulted': 'pTuneos_hydro_defaulted',
        })
        .drop_duplicates(subset=['MT_Subpeptide', 'WT_Subpeptide', 'HLA_Allele'])
    )
    result = result.merge(slim, on=['MT_Subpeptide', 'WT_Subpeptide', 'HLA_Allele'], how='left')
    print(f'[pTuneos] MT_pTuneos 非空={result["MT_pTuneos"].notna().sum()}', file=sys.stderr)
    return result


# ============================================================
# 工具 6: PRIME（per-allele txt 目录，自然键）
# ============================================================

def _load_prime_dir(dir_path: Path, side: str) -> pd.DataFrame:
    """
    读取 PRIME per-allele 输出目录（*.txt），
    返回 DataFrame: [Peptide, _allele_prime, Score_bestAllele]。
    allele_prime = 文件名去扩展名（如 A0101）。
    """
    files = sorted(list(dir_path.glob('*.txt')) + list(dir_path.glob('*.tsv')))
    if not files:
        return pd.DataFrame(columns=['Peptide', '_allele_prime', 'Score_bestAllele'])

    dfs = []
    for f in files:
        allele_prime = re.sub(r'\.(txt|tsv)$', '', f.name, flags=re.IGNORECASE)
        try:
            df = pd.read_csv(f, sep='\t', comment='#', encoding='utf-8')
            df.columns = [c.strip() for c in df.columns]
            if 'Peptide' not in df.columns:
                continue
            if 'Score_bestAllele' not in df.columns:
                sc = [c for c in df.columns if c.startswith('Score_')]
                if not sc:
                    continue
                df['Score_bestAllele'] = df[sc[0]]
            df['_allele_prime'] = allele_prime
            df['Peptide'] = df['Peptide'].astype(str).str.strip()
            dfs.append(df[['Peptide', '_allele_prime', 'Score_bestAllele']])
        except Exception as e:
            print(f'[PRIME-{side}][WARN] 跳过 {f.name}: {e}', file=sys.stderr)

    if not dfs:
        return pd.DataFrame(columns=['Peptide', '_allele_prime', 'Score_bestAllele'])
    combined = pd.concat(dfs, ignore_index=True)
    return combined.drop_duplicates(subset=['Peptide', '_allele_prime'])


def merge_prime(result: pd.DataFrame) -> pd.DataFrame:
    """PRIME 回贴（自然键）。key = (Subpeptide, allele_prime 格式)。"""
    mt_dir = OUT_DIR / 'prime_MT'
    wt_dir = OUT_DIR / 'prime_WT'
    result['_allele_prime'] = result['HLA_Allele'].apply(hla_to_prime)

    for side, subpep_col, col_name, dir_path in [
        ('MT', 'MT_Subpeptide', 'MT_PRIME', mt_dir),
        ('WT', 'WT_Subpeptide', 'WT_PRIME', wt_dir),
    ]:
        if not dir_path.exists():
            print(f'[PRIME-{side}] 跳过：目录不存在 {dir_path}', file=sys.stderr)
            result[col_name] = np.nan
            continue
        prime_df = _load_prime_dir(dir_path, side)
        if prime_df.empty:
            print(f'[PRIME-{side}] 目录无有效文件，跳过', file=sys.stderr)
            result[col_name] = np.nan
            continue
        join_df = prime_df.rename(columns={
            'Peptide': subpep_col,
            'Score_bestAllele': col_name,
        })
        result = result.merge(join_df, on=[subpep_col, '_allele_prime'], how='left')
        print(f'[PRIME-{side}] {col_name} 非空={result[col_name].notna().sum()}', file=sys.stderr)

    result.drop(columns=['_allele_prime'], inplace=True, errors='ignore')
    return result


# ============================================================
# 工具 7: ImmuneApp（per-HLA tsv 目录，自然键）
# ============================================================

def _load_immuneapp_dir(dir_path: Path, side: str) -> pd.DataFrame:
    """读取 ImmuneApp per-HLA .tsv 目录，合并返回 [Peptide, Allele, Immunogenicity_score]。"""
    files = sorted(dir_path.glob('*.tsv'))
    if not files:
        return pd.DataFrame(columns=['Peptide', 'Allele', 'Immunogenicity_score'])

    dfs = []
    for f in files:
        try:
            df = pd.read_csv(f, sep='\t', encoding='utf-8')
            df.columns = [c.strip() for c in df.columns]
            if 'Peptide' not in df.columns or 'Immunogenicity_score' not in df.columns:
                continue
            if 'Allele' not in df.columns:
                continue
            df['Peptide'] = df['Peptide'].astype(str).str.strip()
            df['Allele']  = df['Allele'].astype(str).str.strip()
            dfs.append(df[['Peptide', 'Allele', 'Immunogenicity_score']])
        except Exception as e:
            print(f'[ImmuneApp-{side}][WARN] 跳过 {f.name}: {e}', file=sys.stderr)

    if not dfs:
        return pd.DataFrame(columns=['Peptide', 'Allele', 'Immunogenicity_score'])
    combined = pd.concat(dfs, ignore_index=True)
    return combined.drop_duplicates(subset=['Peptide', 'Allele'])


def merge_immuneapp(result: pd.DataFrame) -> pd.DataFrame:
    """ImmuneApp 回贴（自然键）。key = (Subpeptide, Allele_std HLA-A*24:02 格式)。"""
    mt_dir = OUT_DIR / 'immuneapp_MT'
    wt_dir = OUT_DIR / 'immuneapp_WT'

    for side, subpep_col, col_name, dir_path in [
        ('MT', 'MT_Subpeptide', 'MT_ImmuneApp', mt_dir),
        ('WT', 'WT_Subpeptide', 'WT_ImmuneApp', wt_dir),
    ]:
        if not dir_path.exists():
            print(f'[ImmuneApp-{side}] 跳过：{dir_path}', file=sys.stderr)
            result[col_name] = np.nan
            continue
        ia_df = _load_immuneapp_dir(dir_path, side)
        if ia_df.empty:
            result[col_name] = np.nan
            continue
        join_df = ia_df.rename(columns={
            'Peptide': subpep_col,
            'Allele': 'HLA_Allele',
            'Immunogenicity_score': col_name,
        })
        result = result.merge(join_df, on=[subpep_col, 'HLA_Allele'], how='left')
        print(f'[ImmuneApp-{side}] {col_name} 非空={result[col_name].notna().sum()}', file=sys.stderr)

    return result


# ============================================================
# 工具 8: deepHLApan（自然键修复 NaN bug）
# ============================================================

def _load_deephlapan_dir(dir_path: Path, side: str) -> pd.DataFrame:
    """
    解析 deepHLApan 输出目录（*_predicted_result.csv）。
    返回 [Peptide, _hla_ns, immunogenic_score]，
    _hla_ns = HLA_no_star 格式（HLA-A24:02）。
    """
    csv_files = sorted(dir_path.glob('*_predicted_result.csv'))
    if not csv_files:
        csv_files = sorted(dir_path.glob('*.csv'))
    if not csv_files:
        return pd.DataFrame(columns=['Peptide', '_hla_ns', 'immunogenic score'])

    dfs = []
    for f in csv_files:
        try:
            df = pd.read_csv(f, encoding='utf-8')
            df.columns = [c.strip() for c in df.columns]
            # 兼容列名变体
            col_lower = {c.lower(): c for c in df.columns}
            for cand in ('immunogenic score', 'immunogenic_score', 'immunogenicity'):
                if cand in col_lower:
                    df = df.rename(columns={col_lower[cand]: 'immunogenic score'})
                    break
            missing = {'Peptide', 'HLA', 'immunogenic score'} - set(df.columns)
            if missing:
                print(f'[deepHLApan-{side}][WARN] 缺列 {missing}，跳过 {f.name}', file=sys.stderr)
                continue
            df['Peptide'] = df['Peptide'].astype(str).str.strip()
            # HLA in output: HLA-A24:02（已无星），normalize 确保一致
            df['_hla_ns'] = df['HLA'].astype(str).str.replace('*', '', regex=False).str.strip()
            dfs.append(df[['Peptide', '_hla_ns', 'immunogenic score']])
        except Exception as e:
            print(f'[deepHLApan-{side}][WARN] {f.name}: {e}', file=sys.stderr)

    if not dfs:
        return pd.DataFrame(columns=['Peptide', '_hla_ns', 'immunogenic score'])
    combined = pd.concat(dfs, ignore_index=True)
    return combined.drop_duplicates(subset=['Peptide', '_hla_ns'])


def merge_deephlapan(result: pd.DataFrame) -> pd.DataFrame:
    """
    deepHLApan 回贴（自然键 — BUG 修复）。
    旧代码：Annotation→bb_idx（只填 1 个，同 (pep,HLA) 多 bb_idx 的其余留 NaN）。
    新代码：(MT_Subpeptide, HLA_no_star) join，所有匹配 bb_idx 全填 → BUG 根治。
    key_backbone: HLA_Allele.replace('*','') = HLA-A24:02
    key_output  : HLA col 已是 HLA-A24:02（无星）
    """
    mt_dir = OUT_DIR / 'deephlapan_out_MT'
    wt_dir = OUT_DIR / 'deephlapan_out_WT'

    # 在 result 上添加 _hla_ns（backbone 侧去星）
    result['_hla_ns'] = result['HLA_Allele'].astype(str).str.replace('*', '', regex=False)

    for side, subpep_col, col_name, dir_path in [
        ('MT', 'MT_Subpeptide', 'MT_deepHLApan', mt_dir),
        ('WT', 'WT_Subpeptide', 'WT_deepHLApan', wt_dir),
    ]:
        if not dir_path.exists():
            print(f'[deepHLApan-{side}] 跳过：{dir_path}', file=sys.stderr)
            result[col_name] = np.nan
            continue
        dp_df = _load_deephlapan_dir(dir_path, side)
        if dp_df.empty:
            result[col_name] = np.nan
            continue
        join_df = dp_df.rename(columns={
            'Peptide': subpep_col,
            'immunogenic score': col_name,
        })[[subpep_col, '_hla_ns', col_name]]
        result = result.merge(join_df, on=[subpep_col, '_hla_ns'], how='left')
        print(f'[deepHLApan-{side}] {col_name} 非空={result[col_name].notna().sum()}', file=sys.stderr)

    result.drop(columns=['_hla_ns'], inplace=True, errors='ignore')
    return result


# ============================================================
# 工具 9: HLAthena（per-allele txt，自然键）
# ============================================================

def merge_hlathena(result: pd.DataFrame) -> pd.DataFrame:
    """
    HLAthena 回贴（自然键）。
    文件: HPC/hlathena_run/hla_bench3/<allele>_{MT,WT}.txt
    key = (norm_allele, peptide) → MSi（presentation score）。
    """
    hla_dir = HPC_DIR / 'hlathena_run' / 'hla_bench3'
    if not hla_dir.exists():
        print(f'[HLAthena] 跳过：目录不存在 {hla_dir}', file=sys.stderr)
        result['MT_HLAthena'] = np.nan
        result['WT_HLAthena'] = np.nan
        return result

    # 加载所有 per-allele 文件
    mt_parts, wt_parts = [], []
    for f in sorted(hla_dir.glob('*_MT.txt')):
        m = re.match(r'^(.+)_MT\.txt$', f.name)
        if not m:
            continue
        allele_norm = hla_norm_allele(m.group(1))
        try:
            df = pd.read_csv(f, sep='\t', encoding='utf-8')
            df.columns = [c.strip() for c in df.columns]
            pcol = 'pep' if 'pep' in df.columns else df.columns[0]
            scol = 'MSi' if 'MSi' in df.columns else df.columns[1]
            df = df.rename(columns={pcol: 'Peptide', scol: 'MSi'})
            df['_allele_norm'] = allele_norm
            df['Peptide'] = df['Peptide'].astype(str).str.strip()
            mt_parts.append(df[['Peptide', '_allele_norm', 'MSi']])
        except Exception as e:
            print(f'[HLAthena-MT][WARN] {f.name}: {e}', file=sys.stderr)

    for f in sorted(hla_dir.glob('*_WT.txt')):
        m = re.match(r'^(.+)_WT\.txt$', f.name)
        if not m:
            continue
        allele_norm = hla_norm_allele(m.group(1))
        try:
            df = pd.read_csv(f, sep='\t', encoding='utf-8')
            df.columns = [c.strip() for c in df.columns]
            pcol = 'pep' if 'pep' in df.columns else df.columns[0]
            scol = 'MSi' if 'MSi' in df.columns else df.columns[1]
            df = df.rename(columns={pcol: 'Peptide', scol: 'MSi'})
            df['_allele_norm'] = allele_norm
            df['Peptide'] = df['Peptide'].astype(str).str.strip()
            wt_parts.append(df[['Peptide', '_allele_norm', 'MSi']])
        except Exception as e:
            print(f'[HLAthena-WT][WARN] {f.name}: {e}', file=sys.stderr)

    result['_allele_norm'] = result['HLA_Allele'].apply(hla_norm_allele)

    for side, subpep_col, col_name, parts in [
        ('MT', 'MT_Subpeptide', 'MT_HLAthena', mt_parts),
        ('WT', 'WT_Subpeptide', 'WT_HLAthena', wt_parts),
    ]:
        if not parts:
            print(f'[HLAthena-{side}] 无文件，跳过', file=sys.stderr)
            result[col_name] = np.nan
            continue
        side_df = (
            pd.concat(parts, ignore_index=True)
            .drop_duplicates(subset=['Peptide', '_allele_norm'])
            .rename(columns={'Peptide': subpep_col, 'MSi': col_name})
        )
        result = result.merge(side_df, on=[subpep_col, '_allele_norm'], how='left')
        print(f'[HLAthena-{side}] {col_name} 非空={result[col_name].notna().sum()}', file=sys.stderr)

    result.drop(columns=['_allele_norm'], inplace=True, errors='ignore')
    return result


# ============================================================
# 工具 10: newtools（4-key 自然键: BigMHC/CNNeo/IEDB_Calis/MHCflurry/Repitope）
# ============================================================

_NAT_KEY  = ['Dataset', 'Peptide_ID', 'HLA_Allele', 'MT_Subpeptide']
_SEQ_COLS = {'MT_Subpeptide', 'WT_Subpeptide', 'MT_FullPeptide', 'WT_FullPeptide'}


def merge_newtools(result: pd.DataFrame) -> pd.DataFrame:
    """
    合并 newtools/ 目录下 *_DS1DS2_scores.csv（BigMHC/CNNeo/IEDB_Calis/MHCflurry/Repitope）。
    使用 4-key 自然键 (Dataset,Peptide_ID,HLA_Allele,MT_Subpeptide) 做 left merge。
    P101/P102 修正后的 (Peptide_ID, corrected_HLA) 不在原始 CSV → 自然 NaN。
    """
    csvs = sorted(NEWTOOLS_DIR.glob('*_DS1DS2_scores.csv'))
    if not csvs:
        print('[newtools] 无 *_DS1DS2_scores.csv，跳过', file=sys.stderr)
        return result

    for csv_path in csvs:
        try:
            sdf = pd.read_csv(csv_path, encoding='utf-8')
        except Exception as e:
            print(f'[newtools][WARN] {csv_path.name}: {e}', file=sys.stderr)
            continue
        sdf.columns = [c.strip() for c in sdf.columns]
        direct_cols = [c for c in sdf.columns
                       if (c.startswith('MT_') or c.startswith('WT_')) and c not in _SEQ_COLS]
        has_nat = (all(k in sdf.columns for k in _NAT_KEY) and
                   all(k in result.columns for k in _NAT_KEY))
        if not direct_cols or not has_nat:
            print(f'[newtools][WARN] {csv_path.name} 无直接 schema 或缺 4-key，跳过', file=sys.stderr)
            continue
        for c in direct_cols:
            sdf[c] = pd.to_numeric(sdf[c], errors='coerce')
        join_df = sdf[_NAT_KEY + direct_cols].drop_duplicates(_NAT_KEY)
        before = len(result)
        result = result.merge(join_df, on=_NAT_KEY, how='left')
        if len(result) != before:
            print(f'[newtools][ERR] {csv_path.name}: merge 后行数变化 {before}→{len(result)}，中止', file=sys.stderr)
            sys.exit(1)
        for c in direct_cols:
            fill = result[c].notna().sum()
            pct = fill / before * 100 if before else 0.0
            print(f'  [{csv_path.stem}] {c} 填充={fill}/{before}({pct:.1f}%)', file=sys.stderr)

    return result


# ============================================================
# 工具 11: netmhcpan_ba（bb_idx join + is_MT flag）
# ============================================================

def merge_netmhcpan_ba(result: pd.DataFrame) -> pd.DataFrame:
    """netmhcpan_ba bb_idx join，is_MT 区分 MT/WT。注意：P101/P102 保留旧 HLA 下的分数（bb_idx 不变）。"""
    p = NEWTOOLS_DIR / 'netmhcpan_ba_DS1DS2_scores.csv'
    if not p.exists():
        print(f'[netmhcpan_ba] 跳过：{p}', file=sys.stderr)
        result['MT_netmhcpan_ba'] = np.nan
        result['WT_netmhcpan_ba'] = np.nan
        return result

    sdf = pd.read_csv(p, encoding='utf-8')
    sdf.columns = [c.strip() for c in sdf.columns]
    sdf['netmhcpan_ba_score'] = pd.to_numeric(sdf['netmhcpan_ba_score'], errors='coerce')

    def _is_true(v): return str(v).strip().lower() in ('true', '1', 'yes')
    is_mt = sdf['is_MT'].apply(_is_true)

    mt_df = (
        sdf[is_mt][['bb_idx', 'netmhcpan_ba_score']]
        .groupby('bb_idx')['netmhcpan_ba_score'].mean().reset_index()
        .rename(columns={'netmhcpan_ba_score': 'MT_netmhcpan_ba'})
    )
    wt_df = (
        sdf[~is_mt][['bb_idx', 'netmhcpan_ba_score']]
        .groupby('bb_idx')['netmhcpan_ba_score'].mean().reset_index()
        .rename(columns={'netmhcpan_ba_score': 'WT_netmhcpan_ba'})
    )
    result = result.merge(mt_df, on='bb_idx', how='left')
    result = result.merge(wt_df, on='bb_idx', how='left')
    print(
        f'[netmhcpan_ba] MT 非空={result["MT_netmhcpan_ba"].notna().sum()}'
        f'  WT 非空={result["WT_netmhcpan_ba"].notna().sum()}',
        file=sys.stderr,
    )
    return result


# ============================================================
# 工具 12: T-SCAPE（bb_idx join）
# ============================================================

def merge_tscape(result: pd.DataFrame) -> pd.DataFrame:
    """T-SCAPE bb_idx join，MT only。"""
    p = NEWTOOLS_DIR / 'tscape_scores.csv'
    if not p.exists():
        print(f'[TSCAPE] 跳过：{p}', file=sys.stderr)
        result['MT_TSCAPE'] = np.nan
        return result

    sdf = pd.read_csv(p, encoding='utf-8')
    sdf.columns = [c.strip() for c in sdf.columns]
    sdf['MT_TSCAPE'] = pd.to_numeric(sdf['MT_TSCAPE'], errors='coerce')
    sdf_dedup = sdf[['bb_idx', 'MT_TSCAPE']].drop_duplicates('bb_idx')
    result = result.merge(sdf_dedup, on='bb_idx', how='left')
    print(f'[TSCAPE] MT_TSCAPE 非空={result["MT_TSCAPE"].notna().sum()}', file=sys.stderr)
    return result


# ============================================================
# 列顺序（与旧表 merged_all_tools_16tools.xlsx 一致）
# ============================================================

BACKBONE_COLS = [
    'bb_idx', 'Dataset', 'Patient_ID', 'Peptide_ID', 'Gene_Name', 'Mutation',
    'MT_FullPeptide', 'WT_FullPeptide', 'Peptide_Length', 'Elispot',
    'Window_Size', 'Position', 'MT_Subpeptide', 'WT_Subpeptide', 'HLA_Allele',
    'Ref_UniProt_ID', 'Peptide_Position',
]
TOOL_COLS = [
    'MT_DeepImmuno', 'WT_DeepImmuno',
    'MT_PredIG', 'WT_PredIG',
    'MT_NOAH', 'WT_NOAH', 'MT_NetCleave', 'WT_NetCleave',
    'MT_Stab_peptide', 'WT_Stab_peptide', 'MT_TCR_contact', 'WT_TCR_contact',
    'MT_IMPROVE_mean_prediction_rf',
    'MT_NeoTImmuML', 'WT_NeoTImmuML',
    'MT_pTuneos', 'pTuneos_hydro_defaulted',
    'MT_PRIME', 'WT_PRIME',
    'MT_ImmuneApp', 'WT_ImmuneApp',
    'MT_deepHLApan', 'WT_deepHLApan',
    'MT_HLAthena', 'WT_HLAthena',
    'MT_BigMHC', 'WT_BigMHC',
    'MT_CNNeo', 'WT_CNNeo',
    'MT_IEDB_Calis', 'WT_IEDB_Calis',
    'MT_MHCflurry_presentation', 'WT_MHCflurry_presentation',
    'MT_MHCflurry_affinity_neg', 'WT_MHCflurry_affinity_neg',
    'MT_Repitope', 'WT_Repitope',
    'MT_netmhcpan_ba', 'WT_netmhcpan_ba',
    'MT_TSCAPE',
]
ALL_COLS = BACKBONE_COLS + TOOL_COLS


# ============================================================
# main
# ============================================================

def main():
    print(f'[INFO] 修正 backbone : {FIXED_BB}', file=sys.stderr)
    print(f'[INFO] 旧合表        : {OLD_MERGED}', file=sys.stderr)
    print(f'[INFO] 输出          : {OUT_XLSX}', file=sys.stderr)

    if not FIXED_BB.exists():
        print(f'[ERR] 修正 backbone 不存在: {FIXED_BB}', file=sys.stderr)
        sys.exit(1)

    # ── 读修正 backbone ────────────────────────────────────────────────────────
    backbone = pd.read_csv(FIXED_BB, encoding='utf-8')
    backbone.columns = [c.strip() for c in backbone.columns]
    if len(backbone) != EXPECTED_ROWS:
        print(f'[WARN] backbone 行数 {len(backbone)} ≠ 预期 {EXPECTED_ROWS}', file=sys.stderr)
    print(f'[backbone] 读入 {len(backbone)} 行 × {len(backbone.columns)} 列', file=sys.stderr)

    pp_mask = backbone['Patient_ID'].isin(P101P102_IDS)
    print(
        f'[backbone] P101/P102 行={pp_mask.sum()}  其余={len(backbone)-pp_mask.sum()}',
        file=sys.stderr,
    )

    result = backbone.copy()

    # ── 逐工具合并 ────────────────────────────────────────────────────────────
    print('\n=== 逐工具合并（自然键） ===', file=sys.stderr)

    result = merge_deepimmuno(result)
    _check_rows(result, 'after DeepImmuno')

    result = merge_predig(result)
    _check_rows(result, 'after PredIG')

    result = merge_improve(result)
    _check_rows(result, 'after IMPROVE')

    result = merge_neotimmuml(result)
    _check_rows(result, 'after NeoTImmuML')

    result = merge_ptuneos(result)
    _check_rows(result, 'after pTuneos')

    result = merge_prime(result)
    _check_rows(result, 'after PRIME')

    result = merge_immuneapp(result)
    _check_rows(result, 'after ImmuneApp')

    result = merge_deephlapan(result)
    _check_rows(result, 'after deepHLApan')

    result = merge_hlathena(result)
    _check_rows(result, 'after HLAthena')

    result = merge_newtools(result)
    _check_rows(result, 'after newtools')

    result = merge_netmhcpan_ba(result)
    _check_rows(result, 'after netmhcpan_ba')

    result = merge_tscape(result)
    _check_rows(result, 'after TSCAPE')

    # ── NaN 报告（三联）─────────────────────────────────────────────────────
    print('\n=== NaN 统计报告 ===')
    pp_mask_r = result['Patient_ID'].isin(P101P102_IDS)
    for col in TOOL_COLS:
        if col in result.columns:
            report_nan(col, result[col], pp_mask_r)

    # ── 整理列顺序 ────────────────────────────────────────────────────────────
    final_cols = [c for c in ALL_COLS if c in result.columns]
    extra = [c for c in result.columns if c not in final_cols]
    if extra:
        print(f'[INFO] 额外列（附末尾）: {extra}', file=sys.stderr)
    result = result[final_cols + extra]

    # ── round(8) 防浮点不稳（参考 per_patient POOLING_STUDY §4）─────────────
    for col in TOOL_COLS:
        if col in result.columns:
            result[col] = pd.to_numeric(result[col], errors='coerce').round(8)

    # ── 写出 ──────────────────────────────────────────────────────────────────
    OUT_XLSX.parent.mkdir(parents=True, exist_ok=True)
    result.to_excel(OUT_XLSX, index=False, engine='openpyxl')
    print(f'\n[DONE] 写出 {OUT_XLSX}  shape={result.shape}', file=sys.stderr)

    # ── 对比断言（非 P101/P102 行与旧表应几乎全等）────────────────────────────
    _compare_with_old(result)

    print('\n[DONE] remerge_fixed.py 完成', file=sys.stderr)


def _check_rows(df: pd.DataFrame, label: str) -> None:
    """合并后行数守卫，暴增则立即中止。"""
    if len(df) != EXPECTED_ROWS:
        print(
            f'[ERR] {label}: 行数 {len(df)} ≠ {EXPECTED_ROWS}，'
            '可能 join 键非唯一导致行扩张，中止',
            file=sys.stderr,
        )
        sys.exit(1)


def _compare_with_old(result: pd.DataFrame) -> None:
    """对比非 P101/P102 行与旧表，断言分数几乎全等。"""
    if not OLD_MERGED.exists():
        print(f'\n[对比] 旧合表不存在，跳过对比', file=sys.stderr)
        return

    print('\n=== 对比断言（非 P101/P102 行 vs 旧表） ===', file=sys.stderr)
    try:
        old_df = pd.read_excel(OLD_MERGED)
    except Exception as e:
        print(f'[对比][WARN] 读旧表失败: {e}', file=sys.stderr)
        return
    old_df.columns = [c.strip() for c in old_df.columns]

    npp_new = result[~result['Patient_ID'].isin(P101P102_IDS)].set_index('bb_idx').sort_index()
    npp_old = old_df[~old_df['Patient_ID'].isin(P101P102_IDS)].set_index('bb_idx').sort_index()

    compare_cols = [c for c in TOOL_COLS if c in npp_new.columns and c in npp_old.columns]
    n_ok, n_warn = 0, 0
    for col in compare_cols:
        rn = pd.to_numeric(npp_new[col], errors='coerce')
        ro = pd.to_numeric(npp_old[col], errors='coerce')
        both = rn.notna() & ro.notna()
        if both.sum() == 0:
            print(f'  {col}: 无共同非空行可比较', file=sys.stderr)
            continue
        diffs = (rn[both] - ro[both]).abs()
        n_mismatch = int((diffs > 1e-5).sum())
        max_diff = float(diffs.max())
        if n_mismatch == 0:
            n_ok += 1
            print(f'  {col}: OK  共同非空={both.sum()}', file=sys.stderr)
        else:
            n_warn += 1
            print(
                f'  {col}: WARN {n_mismatch} 行差异 max={max_diff:.3e}  共同非空={both.sum()}',
                file=sys.stderr,
            )

    print(
        f'\n[对比] 共 {len(compare_cols)} 列: {n_ok} OK  {n_warn} WARN',
        file=sys.stderr,
    )
    if n_warn > 0:
        print(
            '  [!] deepHLApan 预期 WARN（NaN bug 修复后多填行，分数值同但旧表部分行为 NaN）',
            file=sys.stderr,
        )


if __name__ == '__main__':
    main()
