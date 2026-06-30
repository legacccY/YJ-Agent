"""
prep_presml_official.py — 4 个 ML 呈递工具官方数据输入生成
=============================================================
QuantImmuBench Phase0 W2-presml slice。读 uniq_pep_hla.csv（+ backbone，仅
TransHLA 用），为 4 个 ML 呈递工具各产输入文件到 scripts/out_official/：

  MHCflurry  : mhcflurry_input_official.csv   列 peptide,HLA_Allele（带星原样）
  MHCnuggets : mhcnuggets_input_official.csv  列 peptide,HLA_Allele,mhcnuggets_allele（去星）
  MHCseqNet  : mhcseqnet_input_official.csv   列 peptide,HLA_Allele（带星，pan-allele）
  TransHLA   : transhla_input_official.csv    列 peptide（HLA-agnostic，仅唯一肽）

长度过滤：
  - MHCflurry / MHCnuggets / MHCseqNet : 8-15mer（支持范围外剔除，MHCflurry 另写
    mhcflurry_unsupported_official.csv 记录剔除肽）
  - TransHLA（TransHLA_I）              : 8-14mer（超范围剔除写 transhla_skipped_official.csv）

★ strict 纪律说明 ★
TransHLA 是 HLA-agnostic，最终要回贴 backbone 两侧（MT_Subpeptide / WT_Subpeptide），
故其唯一肽集 = backbone MT_Subpeptide ∪ WT_Subpeptide 去重去空再 8-14mer 过滤，
**不是** uniq_pep_hla.csv 的 peptide 列（那只含 uniq 对里的肽，可能漏 backbone 子肽）。
其余 3 个 HLA-aware 工具的肽-等位对来自 uniq_pep_hla.csv（1596 对去重）。

Windows 规范：纯 pandas/pathlib，UTF-8，无 GPU。
运行示例：
    python scripts/hpc_official/prep_presml_official.py
    python scripts/hpc_official/prep_presml_official.py \
        --uniq     scripts/out_official/newtools/uniq_pep_hla.csv \
        --backbone scripts/out_official/master_backbone_official.csv \
        --out-dir  scripts/out_official
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

# 长度范围（闭区间）
MIN_LEN_AWARE, MAX_LEN_AWARE = 8, 15       # MHCflurry / MHCnuggets / MHCseqNet
MIN_LEN_TRANSHLA, MAX_LEN_TRANSHLA = 8, 14  # TransHLA_I


def _len_ok(pep: str, lo: int, hi: int) -> bool:
    return isinstance(pep, str) and lo <= len(pep.strip()) <= hi


def destar(allele: str) -> str:
    """HLA-A*02:01 → HLA-A02:01（仅去星，冒号保留）。MHCnuggets 等位格式。"""
    return str(allele).strip().replace('*', '')


# ---------------------------------------------------------------------------
# HLA-aware 三工具：肽-等位对来自 uniq_pep_hla.csv
# ---------------------------------------------------------------------------

def build_aware_inputs(uniq: pd.DataFrame, out_dir: Path):
    """对 MHCflurry / MHCnuggets / MHCseqNet 生成输入；8-15mer 过滤。"""
    df = uniq[['peptide', 'HLA_Allele']].copy()
    df['peptide'] = df['peptide'].astype(str).str.strip()
    df['HLA_Allele'] = df['HLA_Allele'].astype(str).str.strip()
    df = df.drop_duplicates(subset=['peptide', 'HLA_Allele']).reset_index(drop=True)
    n_total = len(df)

    keep = df['peptide'].map(lambda p: _len_ok(p, MIN_LEN_AWARE, MAX_LEN_AWARE))
    df_ok = df[keep].reset_index(drop=True)
    df_bad = df[~keep].reset_index(drop=True)
    n_drop = len(df_bad)

    # MHCflurry：peptide,HLA_Allele（带星原样）
    flurry = df_ok[['peptide', 'HLA_Allele']].copy()
    flurry_path = out_dir / 'mhcflurry_input_official.csv'
    flurry.to_csv(flurry_path, index=False, encoding='utf-8')
    print(f'[MHCflurry]  {flurry_path}  {len(flurry)} 行（剔除 {n_drop} 超 8-15mer / 共 {n_total}）')

    # MHCflurry 不支持肽记录（同 8-15 过滤；MHCflurry 自身仅 8-15mer）
    unsup_path = out_dir / 'mhcflurry_unsupported_official.csv'
    df_bad[['peptide', 'HLA_Allele']].to_csv(unsup_path, index=False, encoding='utf-8')
    print(f'[MHCflurry]  {unsup_path}  {n_drop} 行（剔除的超范围肽-等位对）')

    # MHCnuggets：peptide,HLA_Allele,mhcnuggets_allele（去星）
    nuggets = df_ok[['peptide', 'HLA_Allele']].copy()
    nuggets['mhcnuggets_allele'] = nuggets['HLA_Allele'].map(destar)
    nuggets_path = out_dir / 'mhcnuggets_input_official.csv'
    nuggets.to_csv(nuggets_path, index=False, encoding='utf-8')
    print(f'[MHCnuggets] {nuggets_path}  {len(nuggets)} 行（剔除 {n_drop} 超 8-15mer / 共 {n_total}）')

    # MHCseqNet：peptide,HLA_Allele（带星，pan-allele）
    seqnet = df_ok[['peptide', 'HLA_Allele']].copy()
    seqnet_path = out_dir / 'mhcseqnet_input_official.csv'
    seqnet.to_csv(seqnet_path, index=False, encoding='utf-8')
    print(f'[MHCseqNet]  {seqnet_path}  {len(seqnet)} 行（剔除 {n_drop} 超 8-15mer / 共 {n_total}）')


# ---------------------------------------------------------------------------
# TransHLA：HLA-agnostic，唯一肽 = backbone MT_Subpeptide ∪ WT_Subpeptide
# ---------------------------------------------------------------------------

def build_transhla_input(backbone: pd.DataFrame, out_dir: Path):
    """TransHLA 唯一肽集；8-14mer 过滤，超范围写 skipped。"""
    peps = set()
    for col in ('MT_Subpeptide', 'WT_Subpeptide'):
        if col not in backbone.columns:
            print(f'[WARN] backbone 缺列 {col}，跳过', file=sys.stderr)
            continue
        for v in backbone[col].dropna():
            s = str(v).strip()
            if s and s.lower() != 'nan':
                peps.add(s)
    peps = sorted(peps)
    n_total = len(peps)

    ok = [p for p in peps if _len_ok(p, MIN_LEN_TRANSHLA, MAX_LEN_TRANSHLA)]
    bad = [p for p in peps if not _len_ok(p, MIN_LEN_TRANSHLA, MAX_LEN_TRANSHLA)]

    in_path = out_dir / 'transhla_input_official.csv'
    pd.DataFrame({'peptide': ok}).to_csv(in_path, index=False, encoding='utf-8')
    print(f'[TransHLA]   {in_path}  {len(ok)} 行唯一肽（剔除 {len(bad)} 超 8-14mer / 共 {n_total}）')

    skip_path = out_dir / 'transhla_skipped_official.csv'
    pd.DataFrame({'peptide': bad}).to_csv(skip_path, index=False, encoding='utf-8')
    print(f'[TransHLA]   {skip_path}  {len(bad)} 行（剔除的超范围肽）')


def parse_args():
    here = Path(__file__).resolve().parent
    default_official = here.parent / 'out_official'
    p = argparse.ArgumentParser(
        description='生成 4 个 ML 呈递工具（MHCflurry/MHCnuggets/MHCseqNet/TransHLA）官方输入')
    p.add_argument('--uniq', default=str(default_official / 'newtools' / 'uniq_pep_hla.csv'),
                   help='uniq_pep_hla.csv（列 peptide,HLA_Allele,source）')
    p.add_argument('--backbone', default=str(default_official / 'master_backbone_official.csv'),
                   help='master_backbone_official.csv（TransHLA 取 MT/WT_Subpeptide）')
    p.add_argument('--out-dir', default=str(default_official),
                   help='输出目录')
    return p.parse_args()


def main():
    args = parse_args()
    uniq_path = Path(args.uniq).resolve()
    bb_path = Path(args.backbone).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if not uniq_path.exists():
        sys.exit(f'[FATAL] uniq 文件不存在：{uniq_path}')
    if not bb_path.exists():
        sys.exit(f'[FATAL] backbone 文件不存在：{bb_path}')

    uniq = pd.read_csv(uniq_path, encoding='utf-8')
    print(f'[uniq] 读入 {len(uniq)} 行 ← {uniq_path}，列 {list(uniq.columns)}')
    backbone = pd.read_csv(bb_path, encoding='utf-8')
    print(f'[backbone] 读入 {len(backbone)} 行 ← {bb_path}')

    build_aware_inputs(uniq, out_dir)
    build_transhla_input(backbone, out_dir)
    print('[DONE] prep_presml_official.py 完成')


if __name__ == '__main__':
    main()
