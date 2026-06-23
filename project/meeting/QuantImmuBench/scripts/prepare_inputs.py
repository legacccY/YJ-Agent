"""
prepare_inputs.py — QuantImmuBench 预处理脚本
================================================
读 Elispot_Dataset1.xlsx + Elispot_Dataset2.xlsx，构建 master_backbone.csv，
并导出三工具（DeepImmuno / PredIG / IMPROVE）输入文件及对应映射表。

产出文件（均在 --out-dir，默认 ./out/）：
    out/master_backbone.csv          主干炸开表（子肽×HLA 每行一条）
    out/deepimmuno_input.csv         DeepImmuno 输入（无表头，peptide,HLA，仅 9/10-mer）
    out/deepimmuno_input_map.csv     unique (peptide,HLA) → backbone 行索引列表
    out/predig_input.csv             PredIG recombinant 模式输入
    out/predig_input_map.csv
    out/improve_input.tsv            IMPROVE 输入（TSV，8-12mer）
    out/improve_input_map.csv

运行示例：
    python scripts/prepare_inputs.py
    python scripts/prepare_inputs.py --data-dir ../data --out-dir ./out
"""

import argparse
import os
import sys
import re
import ast
from pathlib import Path

import pandas as pd
import openpyxl  # noqa: F401  — 确保 engine='openpyxl' 可用


# ---------------------------------------------------------------------------
# HLA 归一化
# ---------------------------------------------------------------------------

# 标准格式正则：HLA-X*DD:DD（或更多位）
_RE_STANDARD = re.compile(
    r'^HLA-[A-Z]\*\d{2}:\d{2}', re.IGNORECASE
)
# 紧凑 5 字符：字母 + 4 位数字，如 B5701 / A0201
_RE_COMPACT5 = re.compile(
    r'^([A-Ca-c])(\d{2})(\d{2})$'
)

_hla_warn_counts: dict = {}


def normalize_hla(raw) -> str | None:
    """
    归一化 HLA 等位基因字符串到 HLA-X*DD:DD 格式。
    返回 None 表示无法识别（调用方跳过该 HLA）。

    规则：
      - 已标准（含 * 和 :，如 HLA-A*24:02）→ 原样返回
      - 紧凑 5 字符 B5701 → HLA-B*57:01
      - 其他 / 空 → None，stderr 计数告警
    """
    if raw is None:
        return None
    val = str(raw).strip()
    if not val or val.lower() in ('none', 'nan', ''):
        return None

    # 已标准
    if _RE_STANDARD.match(val):
        # 确保大写
        return val.upper()

    # 紧凑 5 字符（可能已有 HLA- 前缀被剥掉，也可能没有）
    # 先尝试去掉可能的 HLA- 前缀再 match
    candidate = val
    for prefix in ('HLA-', 'hla-'):
        if candidate.startswith(prefix):
            candidate = candidate[len(prefix):]
            break

    m = _RE_COMPACT5.match(candidate)
    if m:
        locus, g1, g2 = m.group(1).upper(), m.group(2), m.group(3)
        return f'HLA-{locus}*{g1}:{g2}'

    # 未知格式
    key = val
    _hla_warn_counts[key] = _hla_warn_counts.get(key, 0) + 1
    return None


def report_hla_warnings():
    if _hla_warn_counts:
        total = sum(_hla_warn_counts.values())
        print(
            f"[WARN] 共跳过 {total} 个无法归一化的 HLA 值：",
            file=sys.stderr
        )
        for k, v in sorted(_hla_warn_counts.items(), key=lambda x: -x[1]):
            print(f"  {repr(k)}: {v} 次", file=sys.stderr)


# ---------------------------------------------------------------------------
# HLA 格式转换（工具专用）
# ---------------------------------------------------------------------------

def hla_to_deepimmuno(hla_std: str) -> str:
    """HLA-A*24:02 → HLA-A*2402（去冒号）"""
    return hla_std.replace(':', '')


def hla_to_improve(hla_std: str) -> str:
    """HLA-A*02:01 → HLA-A02:01（去星号）"""
    return hla_std.replace('*', '')


# ---------------------------------------------------------------------------
# 读取 Dataset1（DS1）
# ---------------------------------------------------------------------------

def load_ds1(data_dir: Path) -> pd.DataFrame:
    """
    读 Elispot_Dataset1.xlsx sheet='All_Peptides'（83 行，9-mer）。
    列（0-indexed）：
      0  Patient ID
      1  Gene Name
      2  Mutation
      3  MT Epitope Seq     (MT 9mer)
      4  WT Peptide Seq     (WT 9mer)
      5  Peptide Length
      6-11  HLA Allele-1..HLA Allele-6
      12 ELISpot
      13 Ref UniProt ID
      14 Peptide Position
    返回原始 DataFrame（列名原样），不炸开。
    """
    path = data_dir / 'Elispot_Dataset1.xlsx'
    df = pd.read_excel(path, sheet_name='All_Peptides', engine='openpyxl')
    print(f'[DS1] 读入 {len(df)} 行，列：{list(df.columns)}', file=sys.stderr)
    return df


# ---------------------------------------------------------------------------
# 读取 Dataset2（DS2）
# ---------------------------------------------------------------------------

def load_ds2(data_dir: Path) -> pd.DataFrame:
    """
    读 Elispot_Dataset2.xlsx sheet='All_Peptides'（101 行，变长肽 15-29mer）。
    关键列：
      0  Patient_ID
      1  Peptide_ID
      3  Vaccine_Peptide   (MT 全长)
      4  WT Peptide Seq    (WT 全长，列名结尾有空格)
      5  Gene_and_Protein_Change
      8  Elispot
      9-14 HLA-1..HLA-6   (紧凑格式 B5701)
      16 Hugo_Symbol
      43 Parsed_Gene
      44 Parsed_Mutation
      45 Ref UniProt ID
      46 Peptide Position
    返回原始 DataFrame。
    """
    path = data_dir / 'Elispot_Dataset2.xlsx'
    df = pd.read_excel(path, sheet_name='All_Peptides', engine='openpyxl')
    print(f'[DS2] 读入 {len(df)} 行，列：{list(df.columns)}', file=sys.stderr)
    return df


# ---------------------------------------------------------------------------
# 炸开函数
# ---------------------------------------------------------------------------

_DS2_WINDOW_SIZES = list(range(8, 15))   # 8,9,10,11,12,13,14


def expand_ds1(df: pd.DataFrame) -> pd.DataFrame:
    """
    DS1：不滑窗，每行 × 每个非空 HLA → 一行。
    Window_Size=9, Position=1, MT/WT Subpeptide = 9mer 本身。
    """
    hla_cols = [
        'HLA Allele-1', 'HLA Allele-2', 'HLA Allele-3',
        'HLA Allele-4', 'HLA Allele-5', 'HLA Allele-6',
    ]
    # 用位置索引取，以防列名有细微差异
    actual_cols = list(df.columns)

    records = []
    for row_idx, row in df.iterrows():
        # 取关键字段
        mt_full = str(row.iloc[3]).strip() if pd.notna(row.iloc[3]) else ''
        wt_full = str(row.iloc[4]).strip() if pd.notna(row.iloc[4]) else ''
        if not mt_full:
            continue

        # Gene_Name + Mutation 拼 Peptide_ID
        gene = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ''
        mut  = str(row.iloc[2]).strip() if pd.notna(row.iloc[2]) else ''
        pid  = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ''
        peptide_id = f'{pid}_{row_idx}' if pid else f'DS1_{row_idx}'

        elispot = row.iloc[12] if pd.notna(row.iloc[12]) else None
        uniprot = row.iloc[13] if pd.notna(row.iloc[13]) else None
        pep_pos = row.iloc[14] if pd.notna(row.iloc[14]) else None

        # HLA 列（6-11）
        hla_values = [row.iloc[i] for i in range(6, 12)]
        hla_norm_list = []
        for hv in hla_values:
            n = normalize_hla(hv)
            if n and n not in hla_norm_list:
                hla_norm_list.append(n)

        if not hla_norm_list:
            # 无有效 HLA，仍保留行但 HLA_Allele=NaN
            hla_norm_list = [None]

        for hla in hla_norm_list:
            records.append({
                'Dataset':       'DS1',
                'Patient_ID':    pid,
                'Peptide_ID':    peptide_id,
                'Gene_Name':     gene,
                'Mutation':      mut,
                'MT_FullPeptide': mt_full,
                'WT_FullPeptide': wt_full,
                'Peptide_Length': len(mt_full),
                'Elispot':       elispot,
                'Window_Size':   9,
                'Position':      1,
                'MT_Subpeptide': mt_full,
                'WT_Subpeptide': wt_full,
                'HLA_Allele':    hla,
                'Ref_UniProt_ID': uniprot,
                'Peptide_Position': pep_pos,
            })

    out = pd.DataFrame(records)
    print(f'[DS1] 炸开后 {len(out)} 行', file=sys.stderr)
    return out


def expand_ds2(df: pd.DataFrame) -> pd.DataFrame:
    """
    DS2：滑窗，每行 × Window_Size(8-14) × Position × 非空 HLA → 一行。
    MT_Subpeptide = MT_FullPeptide[pos-1 : pos-1+win]（1-based Position）。
    WT_Subpeptide = WT_FullPeptide[pos-1 : pos-1+win]（等长对齐，SNV 保证）。
    """
    records = []
    for row_idx, row in df.iterrows():
        # 取列（按位置索引）
        # 0 Patient_ID, 1 Peptide_ID, 3 Vaccine_Peptide(MT), 4 WT Peptide Seq(trailing space)
        patient_id  = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ''
        peptide_id  = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else f'DS2_{row_idx}'
        mt_full     = str(row.iloc[3]).strip() if pd.notna(row.iloc[3]) else ''
        wt_full     = str(row.iloc[4]).strip() if pd.notna(row.iloc[4]) else ''

        if not mt_full:
            continue

        full_len = len(mt_full)

        # 5 Gene_and_Protein_Change
        gene_prot = str(row.iloc[5]).strip() if pd.notna(row.iloc[5]) else ''
        # 43 Parsed_Gene, 44 Parsed_Mutation
        gene_name = str(row.iloc[43]).strip() if pd.notna(row.iloc[43]) else gene_prot
        mutation  = str(row.iloc[44]).strip() if pd.notna(row.iloc[44]) else ''

        elispot   = row.iloc[8]  if pd.notna(row.iloc[8])  else None
        uniprot   = row.iloc[45] if pd.notna(row.iloc[45]) else None
        pep_pos   = row.iloc[46] if pd.notna(row.iloc[46]) else None

        # HLA 列（9-14）：紧凑格式
        hla_values = [row.iloc[i] for i in range(9, 15)]
        hla_norm_list = []
        for hv in hla_values:
            n = normalize_hla(hv)
            if n and n not in hla_norm_list:
                hla_norm_list.append(n)

        if not hla_norm_list:
            hla_norm_list = [None]

        # 滑窗
        for win in _DS2_WINDOW_SIZES:
            if win > full_len:
                continue
            for pos0 in range(0, full_len - win + 1):   # 0-based 起点
                pos1 = pos0 + 1                          # 1-based Position
                mt_sub = mt_full[pos0: pos0 + win]
                # WT 同步切（等长）
                wt_sub = wt_full[pos0: pos0 + win] if len(wt_full) >= pos0 + win else ''

                for hla in hla_norm_list:
                    records.append({
                        'Dataset':       'DS2',
                        'Patient_ID':    patient_id,
                        'Peptide_ID':    peptide_id,
                        'Gene_Name':     gene_name,
                        'Mutation':      mutation,
                        'MT_FullPeptide': mt_full,
                        'WT_FullPeptide': wt_full,
                        'Peptide_Length': full_len,
                        'Elispot':       elispot,
                        'Window_Size':   win,
                        'Position':      pos1,
                        'MT_Subpeptide': mt_sub,
                        'WT_Subpeptide': wt_sub,
                        'HLA_Allele':    hla,
                        'Ref_UniProt_ID': uniprot,
                        'Peptide_Position': pep_pos,
                    })

    out = pd.DataFrame(records)
    print(f'[DS2] 炸开后 {len(out)} 行', file=sys.stderr)
    return out


# ---------------------------------------------------------------------------
# 工具输入文件导出
# ---------------------------------------------------------------------------

def export_deepimmuno(backbone: pd.DataFrame, out_dir: Path):
    """
    DeepImmuno 输入：无表头两列 peptide,HLA（无冒号格式）。
    仅 length∈{9,10} 子肽。MT + WT 都写入，合并后 unique (peptide,HLA)。
    同时写 deepimmuno_input_map.csv：unique_key → backbone 行 index 列表。

    DeepImmuno HLA 格式：HLA-A*0201（去掉冒号，保留星号）。
    """
    valid_len = {9, 10}

    # 过滤有效行（子肽长度 + HLA 非空）
    mask = (
        backbone['MT_Subpeptide'].apply(lambda x: len(str(x)) in valid_len)
        & backbone['HLA_Allele'].notna()
    )
    sub = backbone[mask].copy()

    # 展开 MT + WT
    mt_rows = sub[['MT_Subpeptide', 'HLA_Allele']].copy()
    mt_rows.columns = ['peptide', 'HLA_std']
    mt_rows['_bb_idx'] = sub.index

    # WT 子肽可能为空（DS1 等长必有；DS2 极端情况 WT 短于 MT）
    wt_mask = sub['WT_Subpeptide'].apply(lambda x: len(str(x)) in valid_len)
    wt_rows = sub.loc[wt_mask, ['WT_Subpeptide', 'HLA_Allele']].copy()
    wt_rows.columns = ['peptide', 'HLA_std']
    wt_rows['_bb_idx'] = sub.loc[wt_mask].index

    all_rows = pd.concat([mt_rows, wt_rows], ignore_index=True)

    # 转 DeepImmuno HLA 格式
    all_rows['HLA_di'] = all_rows['HLA_std'].apply(
        lambda h: hla_to_deepimmuno(str(h)) if pd.notna(h) else None
    )
    all_rows = all_rows[all_rows['HLA_di'].notna()].copy()

    # 构建 unique key → backbone idx map
    all_rows['_key'] = all_rows['peptide'] + '|' + all_rows['HLA_di']
    map_df = (
        all_rows.groupby('_key')['_bb_idx']
        .apply(list)
        .reset_index()
    )
    map_df.columns = ['key', 'backbone_indices']

    # unique 输入（去重）
    unique_input = all_rows[['peptide', 'HLA_di']].drop_duplicates()

    # 写 csv（无表头）
    inp_path = out_dir / 'deepimmuno_input.csv'
    unique_input.to_csv(inp_path, index=False, header=False, encoding='utf-8')

    # 写 map
    map_path = out_dir / 'deepimmuno_input_map.csv'
    map_df.to_csv(map_path, index=False, encoding='utf-8')

    print(
        f'[DeepImmuno] 输入 {len(unique_input)} unique (peptide,HLA) → {inp_path}',
        file=sys.stderr
    )


def export_predig(backbone: pd.DataFrame, out_dir: Path):
    """
    PredIG recombinant 模式输入：epitope,HLA_allele,protein_seq,protein_name
    - length 8-14 全要
    - HLA 标准格式（HLA-A*02:01 带星带冒号）
    - protein_seq = 全长肽（MT 子肽用 MT_FullPeptide，WT 子肽用 WT_FullPeptide）
    - protein_name = Peptide_ID|MT|win{win}|pos{pos} 形式唯一标识
    MT + WT 各出行（protein_name 区分 MT/WT）。
    """
    valid_len = range(8, 15)   # 8..14

    mask = (
        backbone['MT_Subpeptide'].apply(lambda x: len(str(x)) in valid_len)
        & backbone['HLA_Allele'].notna()
    )
    sub = backbone[mask].copy()

    records = []
    idx_map: dict = {}   # key → list of backbone idx

    for bb_idx, row in sub.iterrows():
        win  = int(row['Window_Size'])
        pos  = int(row['Position'])
        pid  = str(row['Peptide_ID'])
        hla  = str(row['HLA_Allele'])
        mt_sub = str(row['MT_Subpeptide'])
        wt_sub = str(row['WT_Subpeptide'])
        mt_full = str(row['MT_FullPeptide'])
        wt_full = str(row['WT_FullPeptide'])

        # MT 行
        pname_mt = f'{pid}|MT|win{win}|pos{pos}|{hla}'
        key_mt   = f'{mt_sub}|{hla}|{mt_full}|{pname_mt}'
        records.append({
            'epitope':      mt_sub,
            'HLA_allele':   hla,
            'protein_seq':  mt_full,
            'protein_name': pname_mt,
        })
        idx_map.setdefault(key_mt, []).append(bb_idx)

        # WT 行（仅当 WT 子肽有效）
        if wt_sub and len(wt_sub) in valid_len:
            pname_wt = f'{pid}|WT|win{win}|pos{pos}|{hla}'
            key_wt   = f'{wt_sub}|{hla}|{wt_full}|{pname_wt}'
            records.append({
                'epitope':      wt_sub,
                'HLA_allele':   hla,
                'protein_seq':  wt_full,
                'protein_name': pname_wt,
            })
            idx_map.setdefault(key_wt, []).append(bb_idx)

    out_df = pd.DataFrame(records, columns=['epitope', 'HLA_allele', 'protein_seq', 'protein_name'])
    inp_path = out_dir / 'predig_input.csv'
    out_df.to_csv(inp_path, index=False, encoding='utf-8')

    map_df = pd.DataFrame([
        {'key': k, 'backbone_indices': str(v)}
        for k, v in idx_map.items()
    ])
    map_path = out_dir / 'predig_input_map.csv'
    map_df.to_csv(map_path, index=False, encoding='utf-8')

    print(
        f'[PredIG] 输入 {len(out_df)} 行（含 MT+WT）→ {inp_path}',
        file=sys.stderr
    )


def export_improve(backbone: pd.DataFrame, out_dir: Path):
    """
    IMPROVE 输入：TSV，表头含 Mut_peptide, WT_peptide, HLA_allele（无星号格式）。
    仅 length 8-12（IMPROVE 支持范围）。每个 MT/WT 子肽对 × HLA 一行。

    IMPROVE HLA 格式：HLA-A02:01（去星号，保留冒号），参考实测 HLA-B40:02。
    """
    valid_len = range(8, 13)   # 8..12

    mask = (
        backbone['MT_Subpeptide'].apply(lambda x: len(str(x)) in valid_len)
        & backbone['HLA_Allele'].notna()
    )
    sub = backbone[mask].copy()

    records = []
    idx_map: dict = {}

    for bb_idx, row in sub.iterrows():
        mt_sub = str(row['MT_Subpeptide'])
        wt_sub = str(row['WT_Subpeptide'])
        hla_std = str(row['HLA_Allele'])
        hla_imp = hla_to_improve(hla_std)

        key = f'{mt_sub}|{wt_sub}|{hla_imp}'
        records.append({
            'Mut_peptide': mt_sub,
            'WT_peptide':  wt_sub,
            'HLA_allele':  hla_imp,
        })
        idx_map.setdefault(key, []).append(bb_idx)

    out_df = pd.DataFrame(records, columns=['Mut_peptide', 'WT_peptide', 'HLA_allele'])
    inp_path = out_dir / 'improve_input.tsv'
    out_df.to_csv(inp_path, index=False, sep='\t', encoding='utf-8')

    map_df = pd.DataFrame([
        {'key': k, 'backbone_indices': str(v)}
        for k, v in idx_map.items()
    ])
    map_path = out_dir / 'improve_input_map.csv'
    map_df.to_csv(map_path, index=False, encoding='utf-8')

    print(
        f'[IMPROVE] 输入 {len(out_df)} 行 → {inp_path}',
        file=sys.stderr
    )


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description='QuantImmuBench 预处理：炸开主干表 + 导出三工具输入文件'
    )
    parser.add_argument(
        '--data-dir',
        default=os.path.join(os.path.dirname(__file__), '..', 'data'),
        help='含两个 xlsx 的数据目录（默认 ../data 相对脚本位置）'
    )
    parser.add_argument(
        '--out-dir',
        default=os.path.join(os.path.dirname(__file__), 'out'),
        help='输出目录（默认 ./out 相对脚本位置）'
    )
    return parser.parse_args()


def main():
    args = parse_args()
    data_dir = Path(args.data_dir).resolve()
    out_dir  = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f'[INFO] data_dir  = {data_dir}', file=sys.stderr)
    print(f'[INFO] out_dir   = {out_dir}',  file=sys.stderr)

    # 1. 读原始数据
    df1 = load_ds1(data_dir)
    df2 = load_ds2(data_dir)

    # 2. 炸开
    bb1 = expand_ds1(df1)
    bb2 = expand_ds2(df2)

    # 3. 合并主干表
    backbone = pd.concat([bb1, bb2], ignore_index=True)
    print(f'[backbone] 合并后共 {len(backbone)} 行', file=sys.stderr)

    # 4. 导出主干表
    bb_path = out_dir / 'master_backbone.csv'
    backbone.to_csv(bb_path, index=True, index_label='bb_idx', encoding='utf-8')
    print(f'[backbone] 已写 {bb_path}', file=sys.stderr)

    # 5. 导出三工具输入
    export_deepimmuno(backbone, out_dir)
    export_predig(backbone, out_dir)
    export_improve(backbone, out_dir)

    # 6. HLA 告警汇总
    report_hla_warnings()

    print('[DONE] prepare_inputs.py 完成', file=sys.stderr)


if __name__ == '__main__':
    main()
