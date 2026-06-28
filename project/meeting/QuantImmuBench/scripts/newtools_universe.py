"""
newtools_universe.py — 第二批工具(扩张 v2 第一波 5 工具)统一输入宇宙
================================================================
从 merged_all_tools_9tools.xlsx 抽出 benchmark 的 backbone 4-key 全集 +
工具要喂的唯一 (peptide, HLA) 对清单(MT / WT 分开)。

所有第一波工具(MHCflurry/IEDB-Calis/CNNeo/BigMHC-im/Repitope)的 input prep
都从本脚本产出的两个文件读，保证 key 一致、可回贴。

产出(scripts/out/newtools/):
  universe.csv          — backbone 4-key 全集(34247 行)
        列: Dataset, Peptide_ID, HLA_Allele, MT_Subpeptide, WT_Subpeptide,
            Window_Size, Position, Elispot
  uniq_pep_hla.csv      — 唯一 (peptide, HLA) 对(MT+WT 合并去重)
        列: peptide, HLA_Allele, source(MT|WT|BOTH)
  uniq_pep.csv          — 唯一肽(HLA-agnostic 工具如 Repitope 用)
        列: peptide, source

回贴规则(各工具 parse 用):
  MT_<Tool> = 工具对 (MT_Subpeptide, HLA_Allele) 的分数
  WT_<Tool> = 工具对 (WT_Subpeptide, HLA_Allele) 的分数
  方向统一: 越高越免疫原(nM 类取负/percentile,见各 kit)

运行:
  python scripts/newtools_universe.py
"""
import os
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
MERGED = HERE / 'out' / 'merged_all_tools_9tools.xlsx'
OUT = HERE / 'out' / 'newtools'
OUT.mkdir(parents=True, exist_ok=True)

KEY = ['Dataset', 'Peptide_ID', 'HLA_Allele', 'MT_Subpeptide']


def main():
    df = pd.read_excel(MERGED, engine='openpyxl')
    cols = KEY + ['WT_Subpeptide', 'Window_Size', 'Position', 'Elispot']
    uni = df[cols].copy()
    assert uni.duplicated(subset=KEY).sum() == 0, '4-key 非唯一!'
    uni_path = OUT / 'universe.csv'
    uni.to_csv(uni_path, index=False, encoding='utf-8')
    print(f'[universe] {len(uni)} 行 → {uni_path}')

    # 唯一 (peptide, HLA) 对: MT + WT
    mt = df[['MT_Subpeptide', 'HLA_Allele']].rename(columns={'MT_Subpeptide': 'peptide'})
    mt['source'] = 'MT'
    wt = df[['WT_Subpeptide', 'HLA_Allele']].rename(columns={'WT_Subpeptide': 'peptide'})
    wt['source'] = 'WT'
    both = pd.concat([mt, wt], ignore_index=True)
    both = both.dropna(subset=['peptide', 'HLA_Allele'])
    both = both[both['peptide'].astype(str).str.len() > 0]
    # 合并 source 标记
    grp = both.groupby(['peptide', 'HLA_Allele'])['source'].apply(
        lambda s: 'BOTH' if set(s) >= {'MT', 'WT'} else list(s)[0]
    ).reset_index()
    ph_path = OUT / 'uniq_pep_hla.csv'
    grp.to_csv(ph_path, index=False, encoding='utf-8')
    print(f'[uniq_pep_hla] {len(grp)} 对 → {ph_path}')

    # 唯一肽(HLA-agnostic)
    pep = pd.concat([
        df[['MT_Subpeptide']].rename(columns={'MT_Subpeptide': 'peptide'}).assign(source='MT'),
        df[['WT_Subpeptide']].rename(columns={'WT_Subpeptide': 'peptide'}).assign(source='WT'),
    ], ignore_index=True).dropna()
    pep = pep[pep['peptide'].astype(str).str.len() > 0]
    pg = pep.groupby('peptide')['source'].apply(
        lambda s: 'BOTH' if set(s) >= {'MT', 'WT'} else list(s)[0]
    ).reset_index()
    pep_path = OUT / 'uniq_pep.csv'
    pg.to_csv(pep_path, index=False, encoding='utf-8')
    print(f'[uniq_pep] {len(pg)} 肽 → {pep_path}')


if __name__ == '__main__':
    main()
