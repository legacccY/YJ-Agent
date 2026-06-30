#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
prepare_inputs_official.py — QuantImmuBench Phase 0 P0-d：新官方数据 43 肽补跑工具输入生成
============================================================================================
服务: quantimmu-bench / 03_EXPERIMENT_PLAN.md §3 P0-d（lever=新官方数据补跑缺失 43 肽）

背景
----
旧管道 scripts/prepare_inputs.py 读旧 Elispot_Dataset2.xlsx 生成各工具输入。现切到
**新官方数据**（已冻结在 data/frozen/），需对旧预测缺失的 **43 肽** 补跑。本脚本
**只读 frozen 4 件套、绝不碰旧 xlsx**，把 43 肽的子肽×HLA 展开表转成各工具的标准
输入文件 + map，沿用既有格式契约（DeepImmuno/PredIG/IMPROVE/PRIME/ImmuneApp/
deepHLApan/newtools 宇宙/ptuneos），使现有 runner / 各 patch_add_*.py 合并脚本能直接吃。

设计哲学（复用不重写）
----------------------
  - 不另起一套格式：把 frozen subpep_hla_expansion.csv 转成 prepare_inputs.py / wave3
    所用的 canonical master_backbone schema（MT_Subpeptide/HLA_Allele/Window_Size/...），
    然后 **import 既有 export 函数** 生成输入，保证字节级格式一致：
      · DeepImmuno / PredIG / IMPROVE  ← prepare_inputs.export_*
      · PRIME / ImmuneApp / deepHLApan ← wave3_bench.prep_inputs_wave3.export_*
  - newtools 宇宙（MHCflurry/IEDB_Calis/CNNeo/BigMHC/Repitope/MHCnuggets/MHCseqNet/
    TransHLA/MuNIS/ImmuGenX/NeoaG/NetMHCpan_EL/DeepNetBim/andy90/NeoaPred + DTU 5 工具）
    一律从 newtools_universe 风格的 uniq_pep_hla.csv 读，各自 deploy 脚本再按工具重格式化
    HLA → 本脚本复制 newtools_universe.py 逻辑产 universe/uniq_pep_hla/uniq_pep。
  - ptuneos 自带 (MT_pep, WT_pep, HLA_type) tsv 格式 → 复制 ptuneos/prep_input.py 的 build。

✅ WT 侧已接入（2026-06-30，WT 地基就绪后补）
--------------------------------------------
  WT 子肽来自 data/frozen/subpep_hla_expansion_WT.csv（244 行：14 待补跑肽的 WT 子肽×HLA，
  列含 WT_FullPeptide + subpep_seq[=WT 子肽] + side='WT'）。本脚本按
  (mut_key, subpep_pos, HLA) **逐格配对** MT vs WT，把 WT_Subpeptide / WT_FullPeptide
  填进 canonical backbone → 既有 export 函数（已具 MT/WT 双侧能力）自动产 WT 侧输入：
    · PredIG          WT 行（protein_name 含 |WT|）
    · IMPROVE         WT_peptide 列填入
    · PRIME-WT        prime_input_<allele>/peps_WT.txt + prime_input_map_WT.csv
    · ImmuneApp-WT    immuneapp_input_<allele>/peps_WT.txt + _map_WT.csv
    · deepHLApan-WT   deephlapan_input_WT.csv + _map_WT.csv
    · pTuneos         WT_pep 列填入（→ DAI 差异打分可重生成）
    · newtools 宇宙   uniq_pep_hla.csv / uniq_pep.csv 含 WT 子肽（source=WT/BOTH）
  ⚠️ 仅 14 肽/244 子肽×HLA 有 WT（SNV，等长逐格可配对）；其余 29 肽（indel/无 WT）
     WT 侧仍留空——这是正确的，DAI 对 indel 不适用。MT 侧输出行数与改前完全一致。

frozen 数据源（只读，data/frozen/）
-----------------------------------
  subpep_hla_expansion.csv  1761 行（43 肽子肽×HLA 展开，全 9mer）
        列: mut_key, Patient_ID, Peptide_ID, Vaccine_Peptide, subpep_seq,
            subpep_pos, window_size, hla_allele_std
  patient_hla.csv           39 行（患者级 HLA 分型，含 HLA-FIX 后 P104 新等位）
  ds2_official_groundtruth.csv  130 行（含 Elispot 标签等）
  RERUN_PEPTIDE_LIST.csv    43 行（待补跑肽，29 full + 14 partial）

列名映射 frozen → canonical backbone
------------------------------------
  subpep_seq       → MT_Subpeptide
  Vaccine_Peptide  → MT_FullPeptide
  hla_allele_std   → HLA_Allele       （frozen 已 HLA-FIX，**不得再从旧数据取 HLA**）
  window_size      → Window_Size       （全 =9）
  subpep_pos       → Position          （1-based）
  Peptide_ID       → Peptide_ID
  Patient_ID       → Patient_ID
  (无)             → WT_Subpeptide / WT_FullPeptide = ''（空，见上限制）
  Elispot          ← ds2_official_groundtruth 按 mut_key 左连接

产出（均在 --out-dir，默认 scripts/out_official/，不覆盖旧 scripts/out/）
------------------------------------------------------------------------
  master_backbone_official.csv         canonical backbone（index=bb_idx）
  deepimmuno_input.csv / _map.csv      DeepImmuno（无表头 peptide,HLA[去冒号]，9/10mer）
  predig_input.csv / _map.csv          PredIG recombinant（epitope,HLA_allele,protein_seq,protein_name）
  improve_input.tsv / _map.csv         IMPROVE（TSV，Mut/WT_peptide,HLA[去星]）WT_peptide 已填
  prime_input_<allele>/peps_MT.txt     PRIME 按 allele 分目录 + prime_input_map_MT.csv
  prime_input_<allele>/peps_WT.txt     PRIME WT 侧 + prime_input_map_WT.csv
  immuneapp_input_<allele>/peps_MT.txt ImmuneApp 按 allele 分目录 + immuneapp_input_map_MT.csv
  immuneapp_input_<allele>/peps_WT.txt ImmuneApp WT 侧 + immuneapp_input_map_WT.csv
  deephlapan_input_MT.csv / _map_MT.csv deepHLApan MT（Annotation,HLA[去星],peptide）
  deephlapan_input_WT.csv / _map_WT.csv deepHLApan WT 侧
  newtools/universe.csv                backbone 8 列全集（回贴用，含 WT 子肽列）
  newtools/uniq_pep_hla.csv            唯一 (peptide,HLA_Allele,source[MT/WT/BOTH]) — 全 HPC binding 工具通用喂料，含 WT
  newtools/uniq_pep.csv                唯一肽（HLA-agnostic 工具如 Repitope，含 WT）
  ptuneos/ptuneos_input_all.tsv        pTuneos（MT_pep,WT_pep,HLA_type）WT_pep 已填 + _unique.tsv + _unique_map.csv

跑法（主线串行，本脚本只写不跑）
--------------------------------
  python scripts/prepare_inputs_official.py
  → 产出 scripts/out_official/ 下全部输入文件；再由各 runner / 合并脚本吃。

依赖: pandas, openpyxl（仅 import 复用，本脚本不读 xlsx）
"""

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# 路径锚定（脚本在 scripts/，ROOT = QuantImmuBench/）
# ---------------------------------------------------------------------------
HERE = Path(__file__).resolve().parent          # .../scripts/
ROOT = HERE.parent                               # .../QuantImmuBench/
FROZEN = ROOT / 'data' / 'frozen'

# 复用既有 HLA 工具函数 + export 函数（保证格式契约一致，不重写）
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
_WAVE3_DIR = HERE / 'wave3_bench'
if str(_WAVE3_DIR) not in sys.path:
    sys.path.insert(0, str(_WAVE3_DIR))

from prepare_inputs import (                      # noqa: E402
    normalize_hla,
    report_hla_warnings,
    export_deepimmuno,
    export_predig,
    export_improve,
)
import prep_inputs_wave3 as wave3                  # noqa: E402  (export_prime/immuneapp/deephlapan)


# ---------------------------------------------------------------------------
# canonical backbone schema（与 prepare_inputs.expand_ds2 输出列对齐）
# ---------------------------------------------------------------------------
BACKBONE_COLS = [
    'Dataset', 'Patient_ID', 'Peptide_ID', 'Gene_Name', 'Mutation',
    'MT_FullPeptide', 'WT_FullPeptide', 'Peptide_Length', 'Elispot',
    'Window_Size', 'Position', 'MT_Subpeptide', 'WT_Subpeptide',
    'HLA_Allele', 'Ref_UniProt_ID', 'Peptide_Position',
    # 官方补跑额外保留（便于回贴 / 追溯，不影响既有 export 函数）
    'mut_key',
]


def _build_wt_lookup() -> dict:
    """
    读 data/frozen/subpep_hla_expansion_WT.csv，构建 WT 子肽查表，供 MT backbone 逐格配对。
      key  = (mut_key, subpep_pos:int, hla_std)   ← 与 MT 行同键（mut_key+位置+HLA）
      val  = (WT_Subpeptide, WT_FullPeptide)
    WT 文件列: mut_key, Patient_ID, Peptide_ID, Vaccine_Peptide(=MT 全长), WT_FullPeptide,
              subpep_seq(=WT 子肽), subpep_pos, window_size, hla_allele_std, side(='WT')
    仅 14 肽/244 子肽×HLA 有 WT（SNV，等长可逐格配对）；indel/无 WT 肽不在此表 → WT 侧留空。
    HLA 用 normalize_hla 归一，与 MT 侧同口径，保证键可对上。
    """
    wt_path = FROZEN / 'subpep_hla_expansion_WT.csv'
    if not wt_path.exists():
        print(f'[WARN] WT 文件缺失，WT 侧将全空: {wt_path}', file=sys.stderr)
        return {}
    wt = pd.read_csv(wt_path, encoding='utf-8')
    lut: dict = {}
    n_dup = 0
    for _, r in wt.iterrows():
        hla_std = normalize_hla(r['hla_allele_std'])
        if hla_std is None:
            continue
        key = (str(r['mut_key']), int(r['subpep_pos']), hla_std)
        val = (str(r['subpep_seq']).strip(), str(r['WT_FullPeptide']).strip())
        if key in lut:
            n_dup += 1
        lut[key] = val
    print(f'[frozen] subpep_hla_expansion_WT: {len(wt)} 行，{wt["Peptide_ID"].nunique()} 肽 '
          f'→ WT 查表 {len(lut)} 键（重复 {n_dup}）', file=sys.stderr)
    return lut


def build_backbone(out_dir: Path) -> pd.DataFrame:
    """
    从 frozen subpep_hla_expansion.csv 构建 canonical master_backbone。
    - HLA 一律用 frozen hla_allele_std（已 HLA-FIX），仅过 normalize_hla 做格式校验，
      **不从旧数据取 HLA**。
    - Elispot 按 mut_key 左连接 ds2_official_groundtruth。
    - WT_*：从 subpep_hla_expansion_WT.csv 按 (mut_key, subpep_pos, HLA) 逐格配对填入；
      indel/无 WT 肽（29 肽）WT 侧留空（正确，DAI 不适用）。
    """
    sub_path = FROZEN / 'subpep_hla_expansion.csv'
    gt_path = FROZEN / 'ds2_official_groundtruth.csv'
    for p in (sub_path, gt_path):
        if not p.exists():
            print(f'[ERR] frozen 文件缺失: {p}', file=sys.stderr)
            sys.exit(1)

    sub = pd.read_csv(sub_path, encoding='utf-8')
    gt = pd.read_csv(gt_path, encoding='utf-8')
    wt_lut = _build_wt_lookup()                  # WT 子肽逐格查表
    print(f'[frozen] subpep_hla_expansion: {len(sub)} 行，{sub["Peptide_ID"].nunique()} 肽',
          file=sys.stderr)
    print(f'[frozen] ds2_official_groundtruth: {len(gt)} 行', file=sys.stderr)

    # Elispot / Gene 信息 by mut_key（mut_key 在 GT 唯一）
    gt_cols = {}
    if 'Elispot' in gt.columns:
        gt_cols['Elispot'] = gt.set_index('mut_key')['Elispot'].to_dict()
    gene_col = 'Gene_and_Protein_Change' if 'Gene_and_Protein_Change' in gt.columns else None
    mut_type_col = 'Mutation_type' if 'Mutation_type' in gt.columns else None
    gene_map = gt.set_index('mut_key')[gene_col].to_dict() if gene_col else {}
    mut_map = gt.set_index('mut_key')[mut_type_col].to_dict() if mut_type_col else {}
    elispot_map = gt_cols.get('Elispot', {})

    records = []
    n_hla_ok = 0
    n_wt_filled = 0
    for _, r in sub.iterrows():
        mut_key = str(r['mut_key'])
        hla_raw = r['hla_allele_std']
        hla_std = normalize_hla(hla_raw)         # frozen 已标准，仅校验/统一大写
        if hla_std is not None:
            n_hla_ok += 1
        mt_sub = str(r['subpep_seq']).strip()
        mt_full = str(r['Vaccine_Peptide']).strip()
        pos = int(r['subpep_pos'])
        # WT 侧逐格配对（mut_key + 位置 + HLA）；无 WT（indel/29 肽）则留空
        wt_sub, wt_full = wt_lut.get((mut_key, pos, hla_std), ('', ''))
        if wt_sub:
            n_wt_filled += 1
        records.append({
            'Dataset':          'DS2',
            'Patient_ID':       str(r['Patient_ID']),
            'Peptide_ID':       str(r['Peptide_ID']),
            'Gene_Name':        gene_map.get(mut_key, ''),
            'Mutation':         mut_map.get(mut_key, ''),
            'MT_FullPeptide':   mt_full,
            'WT_FullPeptide':   wt_full,                  # WT 已接入（见 _build_wt_lookup）
            'Peptide_Length':   len(mt_full),
            'Elispot':          elispot_map.get(mut_key, None),
            'Window_Size':      int(r['window_size']),
            'Position':         pos,
            'MT_Subpeptide':    mt_sub,
            'WT_Subpeptide':    wt_sub,                   # WT 已接入
            'HLA_Allele':       hla_std,
            'Ref_UniProt_ID':   None,
            'Peptide_Position': None,
            'mut_key':          mut_key,
        })

    bb = pd.DataFrame(records, columns=BACKBONE_COLS)
    bb = bb.reset_index(drop=True)               # 整数 index = bb_idx，供 export 函数用
    n_wt_peps = bb.loc[bb['WT_Subpeptide'].astype(str).str.len() > 0, 'Peptide_ID'].nunique()
    print(f'[backbone] 构建 {len(bb)} 行 × {len(bb.columns)} 列；HLA 归一化通过 {n_hla_ok}/{len(bb)}；'
          f'WT 侧填入 {n_wt_filled} 行（{n_wt_peps} 肽，预期 244 行/14 肽）', file=sys.stderr)

    # 写 canonical backbone（index_label=bb_idx，与 prepare_inputs.main 一致）
    bb_path = out_dir / 'master_backbone_official.csv'
    bb.to_csv(bb_path, index=True, index_label='bb_idx', encoding='utf-8')
    print(f'[GEN] backbone: {len(bb)} 行 -> {bb_path}', file=sys.stderr)
    return bb


# ---------------------------------------------------------------------------
# newtools 宇宙（复制 newtools_universe.py 逻辑，源换成本脚本 backbone）
# ---------------------------------------------------------------------------
def export_newtools_universe(backbone: pd.DataFrame, out_dir: Path):
    """
    产 universe.csv / uniq_pep_hla.csv / uniq_pep.csv —— 全 HPC binding 工具的通用喂料。
    与 newtools_universe.py 同列契约。WT 列全空 → source 全 'MT'。
    """
    nt_dir = out_dir / 'newtools'
    nt_dir.mkdir(parents=True, exist_ok=True)

    cols = ['Dataset', 'Peptide_ID', 'HLA_Allele', 'MT_Subpeptide',
            'WT_Subpeptide', 'Window_Size', 'Position', 'Elispot']
    uni = backbone[cols].copy()
    uni_path = nt_dir / 'universe.csv'
    uni.to_csv(uni_path, index=False, encoding='utf-8')
    print(f'[GEN] newtools/universe: {len(uni)} 行 -> {uni_path}', file=sys.stderr)

    # 唯一 (peptide, HLA) 对：MT + WT（WT 空 → 只剩 MT）
    mt = backbone[['MT_Subpeptide', 'HLA_Allele']].rename(
        columns={'MT_Subpeptide': 'peptide'})
    mt['source'] = 'MT'
    wt = backbone[['WT_Subpeptide', 'HLA_Allele']].rename(
        columns={'WT_Subpeptide': 'peptide'})
    wt['source'] = 'WT'
    both = pd.concat([mt, wt], ignore_index=True)
    both = both.dropna(subset=['peptide', 'HLA_Allele'])
    both = both[both['peptide'].astype(str).str.len() > 0]
    grp = both.groupby(['peptide', 'HLA_Allele'])['source'].apply(
        lambda s: 'BOTH' if set(s) >= {'MT', 'WT'} else list(s)[0]
    ).reset_index()
    ph_path = nt_dir / 'uniq_pep_hla.csv'
    grp.to_csv(ph_path, index=False, encoding='utf-8')
    print(f'[GEN] newtools/uniq_pep_hla: {len(grp)} 对 -> {ph_path}', file=sys.stderr)

    # 唯一肽（HLA-agnostic，如 Repitope）
    pep = pd.concat([
        backbone[['MT_Subpeptide']].rename(
            columns={'MT_Subpeptide': 'peptide'}).assign(source='MT'),
        backbone[['WT_Subpeptide']].rename(
            columns={'WT_Subpeptide': 'peptide'}).assign(source='WT'),
    ], ignore_index=True).dropna()
    pep = pep[pep['peptide'].astype(str).str.len() > 0]
    pg = pep.groupby('peptide')['source'].apply(
        lambda s: 'BOTH' if set(s) >= {'MT', 'WT'} else list(s)[0]
    ).reset_index()
    pep_path = nt_dir / 'uniq_pep.csv'
    pg.to_csv(pep_path, index=False, encoding='utf-8')
    print(f'[GEN] newtools/uniq_pep: {len(pg)} 肽 -> {pep_path}', file=sys.stderr)


# ---------------------------------------------------------------------------
# pTuneos 输入（复制 ptuneos/prep_input.py 的 build 逻辑，源换成本脚本 backbone）
# ---------------------------------------------------------------------------
def export_ptuneos(backbone: pd.DataFrame, out_dir: Path):
    """
    产 ptuneos_input_all.tsv / _unique.tsv / _unique_map.csv，
    列契约与 ptuneos/prep_input.py 一致：MT_pep, WT_pep, HLA_type（+ 追溯列）。
    ⚠️ WT_pep 全空（frozen 无 WT）→ pTuneos 差异打分（MT vs WT）不可重生成，
       仅产 MT 侧输入供 HPC 跑，见 MISSING_TOOLS。
    """
    pt_dir = out_dir / 'ptuneos'
    pt_dir.mkdir(parents=True, exist_ok=True)

    out = backbone[['Dataset', 'Patient_ID', 'Peptide_ID', 'Position',
                    'HLA_Allele', 'MT_Subpeptide', 'WT_Subpeptide']].copy()
    out = out.dropna(subset=['MT_Subpeptide'])
    out = out[out['MT_Subpeptide'].astype(str).str.strip() != '']
    out = out.rename(columns={
        'MT_Subpeptide': 'MT_pep',
        'WT_Subpeptide': 'WT_pep',
        'HLA_Allele':    'HLA_type',
    }).reset_index(drop=True)
    out.index.name = 'all_idx'

    all_cols = ['MT_pep', 'WT_pep', 'HLA_type',
                'Dataset', 'Patient_ID', 'Peptide_ID', 'Position']
    path_all = pt_dir / 'ptuneos_input_all.tsv'
    out[all_cols].to_csv(path_all, sep='\t', index=True, index_label='all_idx',
                         lineterminator='\n')
    print(f'[GEN] ptuneos/all: {len(out)} 行 -> {path_all}', file=sys.stderr)

    # unique by (MT_pep, WT_pep, HLA_type)
    df = out.reset_index()
    df['_key'] = (df['MT_pep'].astype(str) + '||' +
                  df['WT_pep'].astype(str) + '||' +
                  df['HLA_type'].astype(str))
    uniq_keys = df['_key'].unique()
    k2u = {k: i for i, k in enumerate(uniq_keys)}
    df['unique_idx'] = df['_key'].map(k2u)
    first = df.drop_duplicates(subset=['_key'], keep='first')
    df_u = first[['MT_pep', 'WT_pep', 'HLA_type', 'unique_idx']].set_index(
        'unique_idx').sort_index()
    path_u = pt_dir / 'ptuneos_input_unique.tsv'
    df_u[['MT_pep', 'WT_pep', 'HLA_type']].to_csv(
        path_u, sep='\t', index=True, index_label='unique_idx', lineterminator='\n')
    print(f'[GEN] ptuneos/unique: {len(df_u)} 行 -> {path_u}', file=sys.stderr)

    df_map = df[['all_idx', 'unique_idx', 'Dataset', 'Patient_ID', 'Peptide_ID',
                 'Position', 'MT_pep', 'WT_pep', 'HLA_type']].copy()
    path_map = pt_dir / 'ptuneos_input_unique_map.csv'
    df_map.to_csv(path_map, index=False, lineterminator='\n')
    print(f'[GEN] ptuneos/unique_map: {len(df_map)} 行 -> {path_map}', file=sys.stderr)


# ---------------------------------------------------------------------------
# 覆盖校验：43 肽全覆盖
# ---------------------------------------------------------------------------
def assert_coverage(backbone: pd.DataFrame, expected_peptides: int = 43):
    """断言 backbone 覆盖全 43 肽，且每肽 ≥1 行进 9mer-able（全 9mer）工具。"""
    n_pep = backbone['Peptide_ID'].nunique()
    if n_pep != expected_peptides:
        print(f'[ERR][COVERAGE] backbone 肽数 {n_pep} ≠ 预期 {expected_peptides}',
              file=sys.stderr)
        sys.exit(1)

    # 每肽至少一行 MT 子肽长度 ∈ {9,10}（DeepImmuno-able）
    mt_len = backbone['MT_Subpeptide'].astype(str).str.len()
    di_able = backbone[mt_len.isin({9, 10})]
    peps_di = set(di_able['Peptide_ID'].unique())
    peps_all = set(backbone['Peptide_ID'].unique())
    missing = peps_all - peps_di
    if missing:
        print(f'[ERR][COVERAGE] {len(missing)} 肽无 9/10mer 行进 DeepImmuno: '
              f'{sorted(missing)[:5]}...', file=sys.stderr)
        sys.exit(1)

    # 每肽至少一行有有效 HLA
    has_hla = backbone[backbone['HLA_Allele'].notna()]
    peps_hla = set(has_hla['Peptide_ID'].unique())
    no_hla = peps_all - peps_hla
    if no_hla:
        print(f'[WARN][COVERAGE] {len(no_hla)} 肽全行 HLA 为空: {sorted(no_hla)[:5]}',
              file=sys.stderr)

    print(f'[COVERAGE] PASS：{n_pep} 肽全覆盖，每肽 ≥1 行进 9/10mer 工具 + 有效 HLA',
          file=sys.stderr)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def parse_args():
    p = argparse.ArgumentParser(
        description='QuantImmuBench P0-d：新官方数据 43 肽补跑各工具输入生成（只写不跑）')
    p.add_argument('--out-dir', default=str(HERE / 'out_official'),
                   help='输出目录（默认 scripts/out_official/，不覆盖旧 out/）')
    p.add_argument('--window', type=int, default=9,
                   help='子肽窗口大小（frozen 全 9mer；仅作记录/校验，默认 9）')
    return p.parse_args()


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    args = parse_args()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f'[INFO] FROZEN  = {FROZEN}', file=sys.stderr)
    print(f'[INFO] out_dir = {out_dir}', file=sys.stderr)
    print(f'[INFO] window  = {args.window}（frozen 全 9mer）', file=sys.stderr)

    # 1. 构建 canonical backbone（含写 master_backbone_official.csv）
    backbone = build_backbone(out_dir)

    # 2. 覆盖校验
    assert_coverage(backbone, expected_peptides=43)

    # 3. 既有 export 函数复用（格式契约 100% 沿用）
    #    —— DeepImmuno / PredIG / IMPROVE（prepare_inputs.py）
    print('[INFO] === DeepImmuno / PredIG / IMPROVE（复用 prepare_inputs.export_*）===',
          file=sys.stderr)
    export_deepimmuno(backbone, out_dir)
    export_predig(backbone, out_dir)
    export_improve(backbone, out_dir)            # ⚠️ WT_peptide 列空，见 MISSING_TOOLS

    #    —— PRIME / ImmuneApp / deepHLApan（wave3_bench.prep_inputs_wave3.export_*）
    print('[INFO] === PRIME / ImmuneApp / deepHLApan（复用 wave3.export_*）===',
          file=sys.stderr)
    wave3.export_prime(backbone, out_dir)
    wave3.export_immuneapp(backbone, out_dir)
    wave3.export_deephlapan(backbone, out_dir)   # WT 侧因无 WT 子肽自动跳过

    # 4. newtools 宇宙（全 HPC binding 工具通用喂料）
    print('[INFO] === newtools 宇宙（universe / uniq_pep_hla / uniq_pep）===',
          file=sys.stderr)
    export_newtools_universe(backbone, out_dir)

    # 5. pTuneos 输入
    print('[INFO] === pTuneos 输入 ===', file=sys.stderr)
    export_ptuneos(backbone, out_dir)

    # 6. HLA 告警汇总
    report_hla_warnings()

    # ------------------------------------------------------------------
    # 汇总表
    # ------------------------------------------------------------------
    # WT 侧覆盖快照（直接从 backbone 数，免跑回读）
    wt_mask = backbone['WT_Subpeptide'].astype(str).str.len() > 0
    n_wt_rows = int(wt_mask.sum())
    n_wt_peps = int(backbone.loc[wt_mask, 'Peptide_ID'].nunique())
    print('\n[SUMMARY] ====== 工具输入覆盖汇总（43 肽，全 9mer，MT 侧）======',
          file=sys.stderr)
    print(f'  WT 侧已接入：backbone {n_wt_rows} 行 / {n_wt_peps} 肽有 WT 子肽（预期 244/14），'
          f'各 WT 侧文件行数见上 [PRIME-WT]/[deepHLApan-WT]/[ImmuneApp-WT] 打印', file=sys.stderr)
    print('  本地直读（既有 export 函数产标准输入）:', file=sys.stderr)
    print('    DeepImmuno   out_official/deepimmuno_input.csv', file=sys.stderr)
    print('    PredIG       out_official/predig_input.csv（含 |WT| 行）', file=sys.stderr)
    print('    IMPROVE      out_official/improve_input.tsv      WT_peptide 已填', file=sys.stderr)
    print('    PRIME        out_official/prime_input_<allele>/peps_{MT,WT}.txt', file=sys.stderr)
    print('    ImmuneApp    out_official/immuneapp_input_<allele>/peps_{MT,WT}.txt', file=sys.stderr)
    print('    deepHLApan   out_official/deephlapan_input_{MT,WT}.csv', file=sys.stderr)
    print('    pTuneos      out_official/ptuneos/ptuneos_input_unique.tsv（WT_pep 已填）', file=sys.stderr)
    print('  通用宇宙喂料（各 HPC binding 工具 deploy 脚本读它再重格式化 HLA）:', file=sys.stderr)
    print('    out_official/newtools/uniq_pep_hla.csv  →', file=sys.stderr)
    print('      MHCflurry/IEDB_Calis/CNNeo/BigMHC/Repitope/MHCnuggets/MHCseqNet/', file=sys.stderr)
    print('      TransHLA/MuNIS/ImmuGenX/NeoaG/NetMHCpan_EL/DeepNetBim/andy90/NeoaPred', file=sys.stderr)
    print('      + DTU 5 工具（netMHCpan_BA/netMHCstabpan/ICERFIRE/NetTepi/TSCAPE）', file=sys.stderr)

    # ------------------------------------------------------------------
    # MISSING_TOOLS / TODO（信息不足，不臆造格式）
    # ------------------------------------------------------------------
    # MISSING_TOOLS = [
    #   'WT-side': ✅ 已接入（2026-06-30）。WT 子肽来自 frozen subpep_hla_expansion_WT.csv
    #       （14 肽/244 子肽×HLA，SNV 等长逐格配对）→ IMPROVE WT_peptide / pTuneos WT_pep /
    #       PRIME-WT / deepHLApan-WT / PredIG |WT| 行 / newtools WT 子肽全部填入。
    #       其余 29 肽（indel/无 WT）WT 侧留空 = 正确，DAI 对 indel 不适用。
    #   'NeoTImmuML': 需先经 scripts/neotimmuml/calc_78_features.R 算 78 维特征（R + iFeature
    #       依赖，HPC 跑），其输入 = 肽序列清单。本脚本产的 newtools/uniq_pep.csv 可作肽源，
    #       但 78 特征计算链由其自有 R 管道完成 → 标 HPC，不在此重写其特征格式。
    #   'hlathena / mhlapre': runner 为 .sif 容器（HPC），输入约定见各自 NOTES.md；
    #       通用喂料 = uniq_pep_hla.csv，工具自身 deploy 脚本重格式化 → 标 HPC。
    # ]

    print('\n[DONE] prepare_inputs_official.py 完成（只写未跑；WT 侧已接入 14 肽/244 子肽×HLA）',
          file=sys.stderr)


if __name__ == '__main__':
    main()
