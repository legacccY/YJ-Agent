"""
prep_input.py  (Python 3, host-side)
服务项目: quantimmu-bench  lever: pTuneos Pre&RecNeo benchmark

从 merged_all_tools_4tools.xlsx 抽出 pTuneos 所需列，生成：
  ptuneos_input_all.tsv      — 全量（含重复）
  ptuneos_input_unique.tsv   — 按 (MT_pep, WT_pep, HLA_type) 去重
  ptuneos_input_unique_map.csv  — unique → all 的 idx 映射
  ptuneos_verify_input.tsv   — 从官方 example TSV 抽 40 行做对账验证集

用法:
  python prep_input.py [--xlsx PATH] [--example_tsv PATH] [--outdir PATH]
"""

import argparse
import os
import pandas as pd

REQUIRED_COLS = [
    'Dataset', 'Patient_ID', 'Peptide_ID', 'Position',
    'HLA_Allele', 'MT_Subpeptide', 'WT_Subpeptide'
]

DEFAULT_XLSX = os.path.join(
    os.path.dirname(__file__), '..', 'out', 'merged_all_tools_4tools.xlsx'
)
DEFAULT_EXAMPLE = os.path.join(
    os.path.dirname(__file__), '..', 'out', 'ptuneos_example', 'test_final_neo_model.tsv'
)
DEFAULT_OUTDIR = os.path.dirname(__file__)


def load_xlsx(path):
    print("[prep_input] Reading: {}".format(path))
    df = pd.read_excel(path, engine='openpyxl')
    print("[prep_input] Loaded {} rows x {} cols".format(df.shape[0], df.shape[1]))
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError("Missing columns in xlsx: {}".format(missing))
    return df


def build_all_tsv(df):
    """
    抽必要列，去掉 MT_Subpeptide 为空的行，
    输出列: Dataset / Patient_ID / Peptide_ID / Position / HLA_Allele
            MT_pep / WT_pep / HLA_type
    MT_pep = MT_Subpeptide, WT_pep = WT_Subpeptide, HLA_type = HLA_Allele 原值
    """
    out = df[REQUIRED_COLS].copy()
    before = len(out)
    out = out.dropna(subset=['MT_Subpeptide'])
    out = out[out['MT_Subpeptide'].astype(str).str.strip() != '']
    after = len(out)
    print("[prep_input] Dropped {} rows with empty MT_Subpeptide ({} remain)".format(
        before - after, after))

    out = out.rename(columns={
        'MT_Subpeptide': 'MT_pep',
        'WT_Subpeptide': 'WT_pep',
        'HLA_Allele':    'HLA_type',
    })
    out = out.reset_index(drop=True)
    out.index.name = 'all_idx'
    return out


def print_stats(df):
    print("\n[prep_input] --- Dataset row counts ---")
    for ds, cnt in df.groupby('Dataset').size().items():
        print("  {}: {}".format(ds, cnt))

    print("\n[prep_input] --- MT_pep length distribution ---")
    lens = df['MT_pep'].astype(str).str.len()
    for l, cnt in sorted(lens.value_counts().items()):
        marker = " **(hydro_defaulted)**" if l not in (9, 10, 11) else ""
        print("  len={}: {}{}".format(l, cnt, marker))
    print()


def build_unique(df_all):
    """
    按 (MT_pep, WT_pep, HLA_type) 去重。
    返回 df_unique（带 unique_idx），df_map（all_idx -> unique_idx）。
    """
    key_cols = ['MT_pep', 'WT_pep', 'HLA_type']
    df_all_reset = df_all.reset_index()  # all_idx becomes column
    df_all_reset['_key'] = (
        df_all_reset['MT_pep'].astype(str) + '||' +
        df_all_reset['WT_pep'].astype(str) + '||' +
        df_all_reset['HLA_type'].astype(str)
    )
    # 建 key -> unique_idx 映射
    unique_keys = df_all_reset['_key'].unique()
    key_to_uid = {k: i for i, k in enumerate(unique_keys)}
    df_all_reset['unique_idx'] = df_all_reset['_key'].map(key_to_uid)

    # unique TSV: 保留第一次出现的行
    first_occ = df_all_reset.drop_duplicates(subset=['_key'], keep='first')
    df_unique = first_occ[key_cols + ['unique_idx']].copy()
    df_unique = df_unique.set_index('unique_idx').sort_index()

    # map TSV
    df_map = df_all_reset[['all_idx', 'unique_idx',
                            'Dataset', 'Patient_ID', 'Peptide_ID', 'Position',
                            'MT_pep', 'WT_pep', 'HLA_type']].copy()

    n_unique = len(df_unique)
    n_all = len(df_all_reset)
    print("[prep_input] Unique (MT_pep, WT_pep, HLA_type) pairs: {} / {} total".format(
        n_unique, n_all))
    return df_unique, df_map


def build_verify_tsv(example_tsv_path):
    """
    从官方 example test_final_neo_model.tsv 抽 MT_pep/WT_pep/HLA_type
    + 原 model_pro 作 ref_model_pro，取前 40 行。
    example TSV 列序: col2=HLA_type(idx1), col6=MT_pep(idx5), col7=WT_pep(idx6),
                      col27=model_pro(idx26)
    用列名直接选（更健壮）: #Position=idx0, HLA_type=idx1, MT_pep=idx5, WT_pep=idx6, model_pro=idx26
    """
    print("[prep_input] Reading example TSV: {}".format(example_tsv_path))
    df = pd.read_csv(example_tsv_path, sep='\t')
    print("[prep_input] Example TSV shape: {}".format(df.shape))
    need = ['HLA_type', 'MT_pep', 'WT_pep', 'model_pro']
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise ValueError("Example TSV missing columns: {}".format(missing))
    df_v = df[need].head(40).copy()
    df_v = df_v.rename(columns={'model_pro': 'ref_model_pro'})
    df_v = df_v.reset_index(drop=True)
    print("[prep_input] Verify set: {} rows".format(len(df_v)))
    return df_v


def main():
    parser = argparse.ArgumentParser(description='Prep pTuneos ELISpot input TSVs')
    parser.add_argument('--xlsx', default=DEFAULT_XLSX,
                        help='Path to merged_all_tools_4tools.xlsx')
    parser.add_argument('--example_tsv', default=DEFAULT_EXAMPLE,
                        help='Path to ptuneos example test_final_neo_model.tsv')
    parser.add_argument('--outdir', default=DEFAULT_OUTDIR,
                        help='Output directory (default: same as script)')
    args = parser.parse_args()

    outdir = os.path.abspath(args.outdir)
    os.makedirs(outdir, exist_ok=True)

    # --- All TSV ---
    df_raw = load_xlsx(args.xlsx)
    df_all = build_all_tsv(df_raw)
    print_stats(df_all)

    path_all = os.path.join(outdir, 'ptuneos_input_all.tsv')
    # 输出列顺序: MT_pep / WT_pep / HLA_type 在最前（模型吃前三列），其余保留做合并 key
    out_cols = ['MT_pep', 'WT_pep', 'HLA_type',
                'Dataset', 'Patient_ID', 'Peptide_ID', 'Position']
    df_all[out_cols].to_csv(path_all, sep='\t', index=True, index_label='all_idx',
                             lineterminator='\n')
    print("[prep_input] Wrote: {}".format(path_all))

    # --- Unique TSV + map ---
    df_unique, df_map = build_unique(df_all)

    path_unique = os.path.join(outdir, 'ptuneos_input_unique.tsv')
    df_unique[['MT_pep', 'WT_pep', 'HLA_type']].to_csv(
        path_unique, sep='\t', index=True, index_label='unique_idx',
        lineterminator='\n')
    print("[prep_input] Wrote: {}".format(path_unique))

    path_map = os.path.join(outdir, 'ptuneos_input_unique_map.csv')
    df_map.to_csv(path_map, index=False, lineterminator='\n')
    print("[prep_input] Wrote: {}".format(path_map))

    # --- Verify TSV ---
    example_tsv = os.path.abspath(args.example_tsv)
    if os.path.exists(example_tsv):
        df_v = build_verify_tsv(example_tsv)
        path_verify = os.path.join(outdir, 'ptuneos_verify_input.tsv')
        df_v.to_csv(path_verify, sep='\t', index=True, index_label='verify_idx',
                    lineterminator='\n')
        print("[prep_input] Wrote: {}".format(path_verify))
    else:
        print("[prep_input] WARNING: example_tsv not found at {}, skipping verify set".format(
            example_tsv))

    print("\n[prep_input] Done.")


if __name__ == '__main__':
    main()
