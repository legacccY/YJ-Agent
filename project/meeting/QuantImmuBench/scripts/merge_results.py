"""
merge_results.py — QuantImmuBench 结果合并脚本
================================================
把三工具（DeepImmuno / PredIG / IMPROVE）的原始输出回贴到主干表，
产出：
  ① 每工具一个 merged xlsx（主干列 + 工具 MT/WT 分数列）
  ② 合成大表 merged_all_tools.xlsx（主干 + 三工具分数全并）

输出文件（均在 --out-dir，默认 ./out/）：
    out/merged_deepimmuno.xlsx
    out/merged_predig.xlsx
    out/merged_improve.xlsx
    out/merged_all_tools.xlsx

运行示例（smoke 验证）：
    python scripts/merge_results.py \\
        --backbone             scripts/out/master_backbone.csv \\
        --deepimmuno-result    scripts/out/smoke/deepimmuno_smoke_result.txt \\
        --predig-result        scripts/out/smoke/predig_smoke_result.csv \\
        --predig-input         scripts/out/predig_input.csv \\
        --out-dir              scripts/out/smoke_merged

全量（跑完三工具后）：
    python scripts/merge_results.py \\
        --backbone             scripts/out/master_backbone.csv \\
        --deepimmuno-result    <deepimmuno-cnn-result.txt 路径> \\
        --predig-result        <predig_out.csv 路径> \\
        --predig-input         scripts/out/predig_input.csv \\
        --improve-result       <improve_out_simple.tsv 路径> \\
        --map-dir              scripts/out \\
        --out-dir              scripts/out

各工具输出格式（实测 2026-06-23 smoke 确认）：
  DeepImmuno:
    tab 分隔，有表头 peptide/HLA/immunogenicity；
    HLA 列无冒号（如 HLA-A*2402）；分数 0-1 连续。
    回贴 key = (peptide, HLA_di)，MT+WT 子肽各查一次。

  PredIG:
    CSV，列 ID/epitope/HLA_allele/PredIG/NOAH/NetCleave/...
    ID = <HLA_allele>_<epitope>（如 HLA-A*24:02_RLETIRNPK），无 protein_name。
    HLA_allele 输出为标准带冒号格式（HLA-A*24:02），与 predig_input.csv 一致。
    【严格保输入行序】→ 位置 join：output 第 i 行 ↔ predig_input.csv 第 i 行。
    predig_input.csv protein_name 列含 |MT|/|WT| 标记，据此区分 MT/WT 侧。
    join 前执行行级断言：epitope + HLA_allele 必须完全匹配，任一不符即报错终止。
    回贴列：MT_PredIG / WT_PredIG + MT_NOAH / MT_NetCleave /
            MT_Stab_peptide / MT_TCR_contact（WT 侧只贴 WT_PredIG）。

  IMPROVE:
    TSV，列含 Mut_peptide/HLA_allele/mean_prediction_rf（步骤2 Predict 输出）。
    回贴 key = (Mut_peptide, WT_peptide, HLA_allele_去星)，via improve_input_map.csv。
    --improve-result 缺省时跳过，不报错。
"""

import argparse
import ast
import os
import sys
from pathlib import Path

import pandas as pd


# ---------------------------------------------------------------------------
# HLA 格式转换（与 prepare_inputs 保持一致，此处独立实现）
# ---------------------------------------------------------------------------

def hla_to_deepimmuno(hla_std: str) -> str:
    """HLA-A*24:02 → HLA-A*2402（去冒号，保留星号）"""
    return str(hla_std).replace(':', '')


def hla_to_improve(hla_std: str) -> str:
    """HLA-A*02:01 → HLA-A02:01（去星号，保留冒号）"""
    return str(hla_std).replace('*', '')


# ---------------------------------------------------------------------------
# 解析器：各工具原始输出 → DataFrame
# ---------------------------------------------------------------------------

def parse_deepimmuno(result_path: Path) -> pd.DataFrame:
    """
    解析 DeepImmuno 批量输出（deepimmuno-cnn-result.txt）。
    格式：tab 分隔，有表头，列 peptide / HLA / immunogenicity。
    HLA 列已是无冒号格式（HLA-A*2402）。
    返回 DataFrame 列：peptide, HLA_di, immunogenicity。
    """
    df = pd.read_csv(result_path, sep='\t', encoding='utf-8')
    df.columns = [c.strip() for c in df.columns]

    required = {'peptide', 'HLA', 'immunogenicity'}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f'DeepImmuno 输出缺列 {missing}，实际列：{list(df.columns)}。\n'
            f'请核对 {result_path} 并调整 parse_deepimmuno。'
        )

    df = df.rename(columns={'HLA': 'HLA_di'})
    # 统一去冒号（防御：若某版本输出带冒号）
    df['HLA_di'] = df['HLA_di'].astype(str).str.replace(':', '', regex=False)
    df['peptide'] = df['peptide'].astype(str).str.strip()
    return df[['peptide', 'HLA_di', 'immunogenicity']]


def parse_predig_with_position_join(
    result_path: Path,
    input_path: Path,
) -> pd.DataFrame:
    """
    解析 PredIG 输出，并通过位置 join 恢复 protein_name（含 |MT|/|WT| 标记）。

    PredIG 输出 ID = <HLA_allele>_<epitope>，无 protein_name。
    但 PredIG 严格保输入行序：output[i] 对应 input[i]（0-indexed，去表头后）。
    predig_input.csv 第 i 行（去表头后）的 protein_name 即对应 output[i]。

    断言保护（任一行不符即 raise）：
      output[i].epitope       == input[i].epitope
      output[i].HLA_allele    == input[i].HLA_allele  （均为标准 HLA-A*24:02 格式）

    返回 DataFrame：在 PredIG 输出列基础上追加列 protein_name（来自 input）。
    所有特征列保留（PredIG / NOAH / NetCleave / Stab_peptide / TCR_contact 等）。
    """
    out_df = pd.read_csv(result_path, encoding='utf-8')
    out_df.columns = [c.strip() for c in out_df.columns]

    inp_df = pd.read_csv(input_path, encoding='utf-8')
    inp_df.columns = [c.strip() for c in inp_df.columns]

    # 检查必需列
    for col in ('epitope', 'HLA_allele'):
        if col not in out_df.columns:
            raise ValueError(
                f'PredIG 输出缺列 {col!r}，实际列：{list(out_df.columns)}'
            )
    if 'protein_name' not in inp_df.columns:
        raise ValueError(
            f'predig_input.csv 缺列 protein_name，实际列：{list(inp_df.columns)}'
        )

    n_out = len(out_df)
    n_inp = len(inp_df)
    if n_out != n_inp:
        raise ValueError(
            f'PredIG 行数不符：output={n_out} 行，input={n_inp} 行（去表头后）。'
            f'\n位置 join 要求严格等行数，请检查是否全量输出。'
        )

    # 行级断言
    mismatches = []
    for i in range(n_out):
        out_ep  = str(out_df.iloc[i]['epitope']).strip()
        inp_ep  = str(inp_df.iloc[i]['epitope']).strip()
        out_hla = str(out_df.iloc[i]['HLA_allele']).strip()
        inp_hla = str(inp_df.iloc[i]['HLA_allele']).strip()
        if out_ep != inp_ep or out_hla != inp_hla:
            mismatches.append(
                f'  行 {i}: output=({out_ep!r},{out_hla!r}) vs input=({inp_ep!r},{inp_hla!r})'
            )
        if len(mismatches) >= 5:   # 最多打印 5 个不匹配，快速报错
            break

    if mismatches:
        raise AssertionError(
            'PredIG 位置 join 断言失败！epitope/HLA 不匹配，\n'
            '输出行序已被 PredIG 打乱，不能直接位置 join。\n'
            '首批不匹配：\n' + '\n'.join(mismatches)
        )

    # 位置 join：贴上 protein_name
    out_df = out_df.copy()
    out_df['protein_name'] = inp_df['protein_name'].values

    print(
        f'[PredIG] 位置 join 断言通过（{n_out} 行全部 epitope+HLA 匹配）',
        file=sys.stderr
    )
    return out_df


def parse_improve(result_path: Path) -> pd.DataFrame:
    """
    解析 IMPROVE Predict_immunogenicity 输出 TSV。
    格式：输入列全保留 + 追加 mean_prediction_rf。
    关键列：Mut_peptide, WT_peptide（或 Norm_peptide）, HLA_allele, mean_prediction_rf。
    HLA_allele 是 IMPROVE 格式（无星，如 HLA-A02:01）。
    """
    df = pd.read_csv(result_path, sep='\t', encoding='utf-8')
    df.columns = [c.strip() for c in df.columns]

    # 兼容 WT_peptide / Norm_peptide 列名
    if 'WT_peptide' not in df.columns and 'Norm_peptide' in df.columns:
        df = df.rename(columns={'Norm_peptide': 'WT_peptide'})

    required = {'Mut_peptide', 'HLA_allele', 'mean_prediction_rf'}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f'IMPROVE 输出缺列 {missing}，实际列：{list(df.columns)}。\n'
            f'请核对 {result_path} 并调整 parse_improve。'
        )

    # 统一去星号（对齐 map key）
    df['HLA_allele_imp'] = df['HLA_allele'].astype(str).str.replace('*', '', regex=False)
    return df


# ---------------------------------------------------------------------------
# 回贴函数
# ---------------------------------------------------------------------------

def merge_deepimmuno(
    backbone: pd.DataFrame,
    di_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    DeepImmuno 回贴。
    key = (peptide_无冒号, HLA_无冒号) → immunogenicity。
    MT 子肽匹配 → MT_DeepImmuno；WT 子肽匹配 → WT_DeepImmuno。
    缺失（长度不在 9/10-mer 或未送工具）填 NaN。
    """
    # 建 score 查找字典 key=(peptide, HLA_di) → score
    score_map: dict = {}
    for _, row in di_df.iterrows():
        k = (str(row['peptide']).strip(), str(row['HLA_di']).strip())
        score_map[k] = row['immunogenicity']

    mt_scores = []
    wt_scores = []
    for _, row in backbone.iterrows():
        hla_raw = str(row['HLA_Allele']) if pd.notna(row['HLA_Allele']) else ''
        hla_di  = hla_to_deepimmuno(hla_raw) if hla_raw else ''

        mt_sub = str(row['MT_Subpeptide']).strip()
        wt_sub = str(row['WT_Subpeptide']).strip()

        mt_scores.append(score_map.get((mt_sub, hla_di), float('nan')))
        wt_scores.append(score_map.get((wt_sub, hla_di), float('nan')))

    result = backbone.copy()
    result['MT_DeepImmuno'] = mt_scores
    result['WT_DeepImmuno'] = wt_scores
    return result


# PredIG 特征列：位置 join 后保留在输出的额外列（除 ID/epitope/HLA_allele/PredIG）
_PREDIG_EXTRA_COLS = [
    'NOAH', 'NetCleave', 'Stab_peptide', 'TCR_contact',
    'Hydrophobicity_peptide', 'MW_peptide', 'Charge_peptide',
    'Hydrophobicity_tcr_contact', 'MW_tcr_contact', 'Charge_tcr_contact',
]


def merge_predig(
    backbone: pd.DataFrame,
    pg_df: pd.DataFrame,
    map_path: Path,
) -> pd.DataFrame:
    """
    PredIG 回贴（位置 join 版）。
    pg_df 已含 protein_name 列（由 parse_predig_with_position_join 贴入）。
    protein_name 格式 = Peptide_ID|MT|win{w}|pos{p}|HLA 或 |WT|...

    回贴路径：
      protein_name → predig_input_map.csv（key 含 protein_name 后缀）→ backbone bb_idx。
      map key 格式：epitope|HLA_allele|protein_seq|protein_name。
      用 rsplit('|', 1) 取最后段作 protein_name 匹配。

    贴回列：
      MT 侧：MT_PredIG + MT_NOAH / MT_NetCleave / MT_Stab_peptide /
             MT_TCR_contact（有则贴，无则 NaN）
      WT 侧：WT_PredIG（仅主分数）
    """
    map_df = pd.read_csv(map_path, encoding='utf-8')

    # 建 protein_name → 该行 scores 的字典
    pg_lookup: dict = {}
    for _, row in pg_df.iterrows():
        pname = str(row['protein_name'])
        if pname not in pg_lookup:
            pg_lookup[pname] = row

    # 初始化 backbone 新增列
    result = backbone.copy()
    result['MT_PredIG'] = float('nan')
    result['WT_PredIG'] = float('nan')

    # 确定实际存在哪些额外列
    actual_extra = [c for c in _PREDIG_EXTRA_COLS if c in pg_df.columns]
    for col in actual_extra:
        result[f'MT_{col}'] = float('nan')
        result[f'WT_{col}'] = float('nan')

    # 遍历 map，回贴分数
    for _, map_row in map_df.iterrows():
        raw_key = str(map_row['key'])
        # key 格式：epitope|HLA_allele|protein_seq|protein_name
        # protein_name 本身含 | 分隔符（Peptide_ID|MT|win|pos|HLA），
        # 但 protein_name 始终在最后 5 个 | 分隔段，rsplit 不可靠。
        # 改用 predig_input_map.csv 的 key 直接与 protein_name 对齐：
        # key = f'{mt_sub}|{hla}|{mt_full}|{pname}'（见 prepare_inputs.py）
        # 最后一个 | 后即为 protein_name（protein_name 不含 | 以外的特殊字符外的 | ）
        # protein_name = Peptide_ID|MT|win{w}|pos{p}|HLA → 含 4 个 |
        # key 共 3 个字段 + 1 pname = epitope|HLA|protein_seq + '|' + pname
        # 所以 pname = key 从第 4 个 | 开始的部分（倒数不定）
        # 最简单：map_df 里已存了 key，protein_name 就是 prepare_inputs.py
        # export_predig 里写入的 pname_mt/pname_wt，即：
        # f'{pid}|MT|win{win}|pos{pos}|{hla}'（或 WT）
        # key = f'{mt_sub}|{hla}|{mt_full}|{pname}'
        # 所以从 key 里拆出 pname：key 前三段是 epitope|HLA_allele|protein_seq，
        # 后面整体是 pname（pname 本身含 | 所以 split 只做 3 次）
        parts = raw_key.split('|', 3)
        if len(parts) < 4:
            print(f'[WARN] map key 格式异常，跳过：{raw_key[:80]}', file=sys.stderr)
            continue
        protein_name = parts[3]   # Peptide_ID|MT|win|pos|HLA（含内部 |）

        try:
            bb_indices = ast.literal_eval(str(map_row['backbone_indices']))
        except Exception as e:
            print(f'[WARN] backbone_indices 解析失败：{e}', file=sys.stderr)
            continue

        if protein_name not in pg_lookup:
            # 该 protein_name 在 PredIG 输出中缺失（可能长度被过滤等）
            continue

        row_scores = pg_lookup[protein_name]
        score_val  = row_scores.get('PredIG', float('nan'))
        is_mt = '|MT|' in protein_name

        for idx in bb_indices:
            if idx not in result.index:
                continue
            if is_mt:
                result.at[idx, 'MT_PredIG'] = score_val
                for col in actual_extra:
                    result.at[idx, f'MT_{col}'] = row_scores.get(col, float('nan'))
            else:
                result.at[idx, 'WT_PredIG'] = score_val
                for col in actual_extra:
                    result.at[idx, f'WT_{col}'] = row_scores.get(col, float('nan'))

    n_mt_filled = result['MT_PredIG'].notna().sum()
    n_wt_filled = result['WT_PredIG'].notna().sum()
    print(
        f'[PredIG] 回贴完成：MT_PredIG={n_mt_filled} 行非空，'
        f'WT_PredIG={n_wt_filled} 行非空',
        file=sys.stderr
    )
    return result


def merge_improve(
    backbone: pd.DataFrame,
    im_df: pd.DataFrame,
    map_path: Path,
) -> pd.DataFrame:
    """
    IMPROVE 回贴。
    key = (Mut_peptide, WT_peptide, HLA_allele_imp)（无星格式）
    通过 improve_input_map.csv → backbone bb_idx 贴 mean_prediction_rf。
    列命名：MT_IMPROVE_mean_prediction_rf。
    IMPROVE 分数是 MT/WT 对的评分，统一贴 MT 侧；WT 侧留 NaN。
    """
    map_df = pd.read_csv(map_path, encoding='utf-8')

    # 建 key → score 字典
    score_map: dict = {}
    for _, row in im_df.iterrows():
        mt  = str(row['Mut_peptide']).strip()
        wt  = str(row.get('WT_peptide', '')).strip()
        hla = str(row['HLA_allele_imp']).strip()
        k   = f'{mt}|{wt}|{hla}'
        score_map[k] = row['mean_prediction_rf']

    result = backbone.copy()
    result['MT_IMPROVE_mean_prediction_rf'] = float('nan')

    for _, map_row in map_df.iterrows():
        key = str(map_row['key'])
        try:
            bb_indices = ast.literal_eval(str(map_row['backbone_indices']))
        except Exception:
            continue
        score_val = score_map.get(key, float('nan'))
        for idx in bb_indices:
            if idx in result.index:
                result.at[idx, 'MT_IMPROVE_mean_prediction_rf'] = score_val

    n_filled = result['MT_IMPROVE_mean_prediction_rf'].notna().sum()
    print(f'[IMPROVE] 回贴完成：MT_IMPROVE_mean_prediction_rf={n_filled} 行非空', file=sys.stderr)
    return result


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description='QuantImmuBench 结果合并：三工具输出回贴主干表'
    )
    _default_out = os.path.join(os.path.dirname(__file__), 'out')

    parser.add_argument(
        '--backbone',
        default=os.path.join(_default_out, 'master_backbone.csv'),
        help='master_backbone.csv 路径（prepare_inputs.py 输出）'
    )
    parser.add_argument(
        '--deepimmuno-result',
        default=None,
        help='DeepImmuno 批量输出文件路径（deepimmuno-cnn-result.txt，可选）'
    )
    parser.add_argument(
        '--predig-result',
        default=None,
        help='PredIG 输出 CSV 路径（可选）'
    )
    parser.add_argument(
        '--predig-input',
        default=os.path.join(_default_out, 'predig_input.csv'),
        help='prepare_inputs.py 生成的 predig_input.csv（位置 join 用，含 protein_name）'
    )
    parser.add_argument(
        '--improve-result',
        default=None,
        help='IMPROVE Predict_immunogenicity 输出 TSV 路径（可选，缺省跳过）'
    )
    parser.add_argument(
        '--map-dir',
        default=_default_out,
        help='存放 *_input_map.csv 的目录（默认同 --out-dir）'
    )
    parser.add_argument(
        '--out-dir',
        default=_default_out,
        help='输出目录（默认 ./out 相对脚本位置）'
    )
    return parser.parse_args()


def main():
    args = parse_args()
    backbone_path  = Path(args.backbone).resolve()
    map_dir        = Path(args.map_dir).resolve()
    out_dir        = Path(args.out_dir).resolve()
    predig_inp_path = Path(args.predig_input).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f'[INFO] backbone     = {backbone_path}',   file=sys.stderr)
    print(f'[INFO] map_dir      = {map_dir}',          file=sys.stderr)
    print(f'[INFO] predig_input = {predig_inp_path}',  file=sys.stderr)
    print(f'[INFO] out_dir      = {out_dir}',           file=sys.stderr)

    # 读主干表
    backbone = pd.read_csv(backbone_path, index_col='bb_idx', encoding='utf-8')
    print(f'[backbone] 读入 {len(backbone)} 行', file=sys.stderr)

    merged_di = None
    merged_pg = None
    merged_im = None

    # ----------------------------------------------------------------
    # DeepImmuno
    # ----------------------------------------------------------------
    if args.deepimmuno_result:
        di_path = Path(args.deepimmuno_result).resolve()
        print(f'[DeepImmuno] 解析 {di_path}', file=sys.stderr)
        di_df = parse_deepimmuno(di_path)
        merged_di = merge_deepimmuno(backbone, di_df)
        out_path = out_dir / 'merged_deepimmuno.xlsx'
        merged_di.to_excel(out_path, index=True, engine='openpyxl')
        n_mt = merged_di['MT_DeepImmuno'].notna().sum()
        n_wt = merged_di['WT_DeepImmuno'].notna().sum()
        print(
            f'[DeepImmuno] 已写 {out_path}（MT_DeepImmuno={n_mt} 行非空，'
            f'WT_DeepImmuno={n_wt} 行非空）',
            file=sys.stderr
        )
    else:
        print('[DeepImmuno] --deepimmuno-result 未提供，跳过', file=sys.stderr)

    # ----------------------------------------------------------------
    # PredIG（位置 join + 断言）
    # ----------------------------------------------------------------
    if args.predig_result:
        pg_path  = Path(args.predig_result).resolve()
        map_path = map_dir / 'predig_input_map.csv'
        print(f'[PredIG] 解析（位置 join）{pg_path}', file=sys.stderr)
        if not predig_inp_path.exists():
            raise FileNotFoundError(
                f'--predig-input 路径不存在：{predig_inp_path}\n'
                f'请先运行 prepare_inputs.py 生成 predig_input.csv。'
            )
        pg_df = parse_predig_with_position_join(pg_path, predig_inp_path)
        merged_pg = merge_predig(backbone, pg_df, map_path)
        out_path = out_dir / 'merged_predig.xlsx'
        merged_pg.to_excel(out_path, index=True, engine='openpyxl')
        print(f'[PredIG] 已写 {out_path}', file=sys.stderr)
    else:
        print('[PredIG] --predig-result 未提供，跳过', file=sys.stderr)

    # ----------------------------------------------------------------
    # IMPROVE（可选）
    # ----------------------------------------------------------------
    if args.improve_result:
        im_path  = Path(args.improve_result).resolve()
        map_path = map_dir / 'improve_input_map.csv'
        print(f'[IMPROVE] 解析 {im_path}', file=sys.stderr)
        im_df = parse_improve(im_path)
        merged_im = merge_improve(backbone, im_df, map_path)
        out_path = out_dir / 'merged_improve.xlsx'
        merged_im.to_excel(out_path, index=True, engine='openpyxl')
        print(f'[IMPROVE] 已写 {out_path}', file=sys.stderr)
    else:
        print('[IMPROVE] --improve-result 未提供，跳过', file=sys.stderr)

    # ----------------------------------------------------------------
    # 合成大表（backbone 为底，逐工具左 join 分数列）
    # ----------------------------------------------------------------
    all_table = backbone.copy()

    if merged_di is not None:
        for col in ['MT_DeepImmuno', 'WT_DeepImmuno']:
            if col in merged_di.columns:
                all_table[col] = merged_di[col]

    if merged_pg is not None:
        pg_new_cols = [c for c in merged_pg.columns if c not in backbone.columns]
        for col in pg_new_cols:
            all_table[col] = merged_pg[col]

    if merged_im is not None:
        im_new_cols = [c for c in merged_im.columns if c not in backbone.columns]
        for col in im_new_cols:
            all_table[col] = merged_im[col]

    all_path = out_dir / 'merged_all_tools.xlsx'
    all_table.to_excel(all_path, index=True, engine='openpyxl')
    print(
        f'[ALL] 合成大表已写 {all_path}'
        f'（{len(all_table)} 行，{len(all_table.columns)} 列）',
        file=sys.stderr
    )

    print('[DONE] merge_results.py 完成', file=sys.stderr)


if __name__ == '__main__':
    main()
