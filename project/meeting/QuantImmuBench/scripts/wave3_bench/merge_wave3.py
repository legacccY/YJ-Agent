"""
merge_wave3.py — QuantImmuBench Wave-3 结果合并
================================================
把 3 工具（PRIME / ImmuneApp / deepHLApan）的原始输出回贴到主干表，
追加 6 列：
    MT_PRIME / WT_PRIME
    MT_ImmuneApp / WT_ImmuneApp
    MT_deepHLApan / WT_deepHLApan

以 merged_all_tools_5tools.xlsx 为底（已含第一批 5 工具分数），
新加 6 列后产出 merged_all_tools_8tools.xlsx。
若 --base 未提供则以 master_backbone.csv 为底（只含主干列）。

各工具输出格式（实测/文档确认）：
  PRIME:
    TSV，17 列，表头含 Peptide/BestAllele/Score_bestAllele/Score_<allele>...
    用 --prime-result-MT / --prime-result-WT 分别传 MT 侧和 WT 侧跑出结果目录。
    支持两种调用方式：
      (a) 整合目录：--prime-result-MT <dir>  → 扫目录下所有 *.txt/*.tsv PRIME 输出并拼接
      (b) 单文件：  --prime-result-MT <file> → 直接解析单个 PRIME 输出文件
    回贴 key = (peptide, allele_prime)，通过 prime_input_map_MT/WT.csv 映射 bb_idx。
    score 列：优先取 Score_bestAllele，若缺则取列名含目标 allele 的 Score_xxx 列。

  ImmuneApp:
    TSV，列 Allele/Peptide/Sample/Immunogenicity_score（文件名 ImmuneApp_Immunogenicity_predictions.tsv）。
    --immuneapp-result-MT / --immuneapp-result-WT 支持目录（扫所有 .tsv）或单文件。
    回贴 key = (Peptide, Allele)，Allele 为标准格式（HLA-A*24:02）。
    通过 immuneapp_input_map_MT/WT.csv → bb_idx。

  deepHLApan:
    CSV，列 Annotation,HLA,Peptide,binding score,immunogenic score（或含变体列名）。
    --deephlapan-result-MT / --deephlapan-result-WT 为单文件路径。
    Annotation = bb_idx（由 prep_inputs_wave3.py 写入）→ 直接按 Annotation 回贴，无需 map。
    score 列：取 immunogenic score。

运行示例（全量）：
    python scripts/wave3_bench/merge_wave3.py \\
        --base             scripts/out/merged_all_tools_5tools.xlsx \\
        --backbone         scripts/out/master_backbone.csv \\
        --map-dir          scripts/out \\
        --prime-result-MT  <prime_out_MT_dir_or_file> \\
        --prime-result-WT  <prime_out_WT_dir_or_file> \\
        --immuneapp-result-MT <immuneapp_out_MT_dir_or_file> \\
        --immuneapp-result-WT <immuneapp_out_WT_dir_or_file> \\
        --deephlapan-result-MT <MT_predicted_result.csv> \\
        --deephlapan-result-WT <WT_predicted_result.csv> \\
        --out-dir          scripts/out
"""

import argparse
import ast
import os
import sys
from pathlib import Path

import pandas as pd


# ---------------------------------------------------------------------------
# HLA 格式转换（与 prep_inputs_wave3.py 保持一致，独立实现）
# ---------------------------------------------------------------------------

def hla_to_prime(hla_std: str) -> str:
    """HLA-A*24:02 → A2402（去 HLA- + 去星 + 去冒号）"""
    s = str(hla_std).strip()
    if s.upper().startswith('HLA-'):
        s = s[4:]
    return s.replace('*', '').replace(':', '')


# ---------------------------------------------------------------------------
# 解析器：各工具原始输出 → DataFrame
# ---------------------------------------------------------------------------

def _collect_files(path_str: str, exts: tuple = ('.txt', '.tsv', '.csv')) -> list[Path]:
    """
    path_str 可为目录或文件。
    - 目录：扫 exts 后缀文件（非递归）。
    - 文件：直接返回 [path]。
    """
    p = Path(path_str).resolve()
    if p.is_dir():
        files = []
        for ext in exts:
            files.extend(sorted(p.glob(f'*{ext}')))
        return files
    elif p.is_file():
        return [p]
    else:
        raise FileNotFoundError(f'路径不存在：{p}')


def parse_prime(path_str: str, side: str = 'MT') -> pd.DataFrame:
    """
    解析 PRIME 输出（TSV）。
    path_str：目录（扫所有 .txt/.tsv）或单文件。
    返回 DataFrame，列：Peptide, BestAllele, Score_bestAllele（+ 原始其他列）。
    跨文件拼接，重置索引。

    PRIME 输出表头示例（17 列）：
        Peptide  BestAllele  %Rank_bestAllele  Score_bestAllele  Score_A2402  ...
    """
    files = _collect_files(path_str, exts=('.txt', '.tsv'))
    if not files:
        raise FileNotFoundError(f'PRIME-{side} 路径下无 .txt/.tsv 文件：{path_str}')

    dfs = []
    for f in files:
        try:
            df = pd.read_csv(f, sep='\t', encoding='utf-8', comment='#')
            df.columns = [c.strip() for c in df.columns]
            dfs.append(df)
            print(f'[PRIME-{side}] 读入 {len(df)} 行 ← {f.name}', file=sys.stderr)
        except Exception as e:
            print(f'[WARN] PRIME-{side} 跳过文件 {f.name}：{e}', file=sys.stderr)

    if not dfs:
        raise ValueError(f'PRIME-{side}：所有文件解析失败，请检查格式')

    merged = pd.concat(dfs, ignore_index=True)

    # 必需列检查
    if 'Peptide' not in merged.columns:
        raise ValueError(
            f'PRIME-{side} 输出缺列 Peptide，实际列：{list(merged.columns)}\n'
            '请检查 PRIME 输出格式（--score/-mix 参数是否正确）'
        )
    if 'Score_bestAllele' not in merged.columns:
        # 尝试找 Score_xxx 列
        score_cols = [c for c in merged.columns if c.startswith('Score_')]
        if not score_cols:
            raise ValueError(
                f'PRIME-{side} 输出无 Score_bestAllele 也无 Score_xxx 列，'
                f'实际列：{list(merged.columns)}'
            )
        # 取第一个 Score_xxx 作为回退
        merged['Score_bestAllele'] = merged[score_cols[0]]
        print(
            f'[WARN] PRIME-{side}：未找到 Score_bestAllele，'
            f'使用 {score_cols[0]} 代替',
            file=sys.stderr
        )

    # 保留 BestAllele（可选，用于 debug）
    if 'BestAllele' not in merged.columns:
        merged['BestAllele'] = None

    merged['Peptide'] = merged['Peptide'].astype(str).str.strip()
    print(f'[PRIME-{side}] 共 {len(merged)} 行（来自 {len(files)} 个文件）', file=sys.stderr)
    return merged


def parse_immuneapp(path_str: str, side: str = 'MT') -> pd.DataFrame:
    """
    解析 ImmuneApp 输出（TSV，列 Allele/Peptide/Sample/Immunogenicity_score）。
    path_str：目录（扫所有 .tsv）或单文件。
    跨文件拼接。
    """
    files = _collect_files(path_str, exts=('.tsv',))
    if not files:
        # 也尝试 .txt
        files = _collect_files(path_str, exts=('.txt', '.tsv'))
    if not files:
        raise FileNotFoundError(f'ImmuneApp-{side} 路径下无 .tsv 文件：{path_str}')

    dfs = []
    for f in files:
        try:
            df = pd.read_csv(f, sep='\t', encoding='utf-8')
            df.columns = [c.strip() for c in df.columns]
            dfs.append(df)
            print(f'[ImmuneApp-{side}] 读入 {len(df)} 行 ← {f.name}', file=sys.stderr)
        except Exception as e:
            print(f'[WARN] ImmuneApp-{side} 跳过文件 {f.name}：{e}', file=sys.stderr)

    if not dfs:
        raise ValueError(f'ImmuneApp-{side}：所有文件解析失败')

    merged = pd.concat(dfs, ignore_index=True)

    required = {'Peptide', 'Immunogenicity_score'}
    # 兼容列名大小写
    col_map = {c.lower(): c for c in merged.columns}
    for req in list(required):
        if req not in merged.columns and req.lower() in col_map:
            merged = merged.rename(columns={col_map[req.lower()]: req})

    missing = required - set(merged.columns)
    if missing:
        raise ValueError(
            f'ImmuneApp-{side} 输出缺列 {missing}，实际列：{list(merged.columns)}\n'
            '请检查输出文件名是否为 ImmuneApp_Immunogenicity_predictions.tsv'
        )

    # Allele 列（可选，用于 key 匹配；有些版本列名不同）
    if 'Allele' not in merged.columns:
        # 尝试寻找含 allele 的列
        allele_cols = [c for c in merged.columns if 'allele' in c.lower() or 'hla' in c.lower()]
        if allele_cols:
            merged = merged.rename(columns={allele_cols[0]: 'Allele'})
            print(f'[WARN] ImmuneApp-{side}：Allele 列用 {allele_cols[0]} 代替', file=sys.stderr)
        else:
            merged['Allele'] = None
            print(
                f'[WARN] ImmuneApp-{side}：未找到 Allele 列，'
                '将仅按肽段匹配（可能歧义）',
                file=sys.stderr
            )

    merged['Peptide'] = merged['Peptide'].astype(str).str.strip()
    if merged['Allele'].notna().any():
        merged['Allele'] = merged['Allele'].astype(str).str.strip()

    print(f'[ImmuneApp-{side}] 共 {len(merged)} 行（来自 {len(files)} 个文件）', file=sys.stderr)
    return merged


def parse_deephlapan(result_path: str, side: str = 'MT') -> pd.DataFrame:
    """
    解析 deepHLApan 输出（CSV）。
    列：Annotation, HLA, Peptide, binding score, immunogenic score
    Annotation = bb_idx（由 prep_inputs_wave3.py 写入，直接用于回贴）。
    """
    p = Path(result_path).resolve()
    if not p.exists():
        raise FileNotFoundError(f'deepHLApan-{side} 结果文件不存在：{p}')

    df = pd.read_csv(p, encoding='utf-8')
    df.columns = [c.strip() for c in df.columns]

    # 兼容列名变体
    col_lower = {c.lower(): c for c in df.columns}

    # immunogenic score
    imm_col = None
    for candidate in ('immunogenic score', 'immunogenic_score', 'immunogenicity'):
        if candidate in col_lower:
            imm_col = col_lower[candidate]
            break
    if imm_col is None:
        raise ValueError(
            f'deepHLApan-{side} 输出缺 immunogenic score 列，'
            f'实际列：{list(df.columns)}'
        )
    if imm_col != 'immunogenic score':
        df = df.rename(columns={imm_col: 'immunogenic score'})

    # Annotation 列
    if 'Annotation' not in df.columns:
        ann_candidates = [c for c in df.columns if 'annot' in c.lower() or 'id' in c.lower()]
        if ann_candidates:
            df = df.rename(columns={ann_candidates[0]: 'Annotation'})
        else:
            raise ValueError(
                f'deepHLApan-{side} 缺 Annotation 列，实际列：{list(df.columns)}'
            )

    df['Annotation'] = df['Annotation'].astype(str).str.strip()
    print(f'[deepHLApan-{side}] 读入 {len(df)} 行 ← {p.name}', file=sys.stderr)
    return df[['Annotation', 'immunogenic score']]


# ---------------------------------------------------------------------------
# 回贴函数
# ---------------------------------------------------------------------------

def merge_prime(
    backbone: pd.DataFrame,
    prime_mt_df: pd.DataFrame | None,
    prime_wt_df: pd.DataFrame | None,
    map_dir: Path,
) -> pd.DataFrame:
    """
    PRIME 回贴。
    key = (Peptide, allele_prime)，通过 prime_input_map_MT/WT.csv → bb_idx。
    贴回列：MT_PRIME（来自 MT 侧），WT_PRIME（来自 WT 侧）。
    """
    result = backbone.copy()
    result['MT_PRIME'] = float('nan')
    result['WT_PRIME'] = float('nan')

    def _do_merge(side_df: pd.DataFrame, map_path: Path, col_name: str):
        if side_df is None:
            return
        if not map_path.exists():
            print(f'[WARN] PRIME map 不存在：{map_path}', file=sys.stderr)
            return

        map_df = pd.read_csv(map_path, encoding='utf-8')

        # 建 (peptide, allele_prime) → score 字典
        score_map: dict = {}
        for _, row in side_df.iterrows():
            pep = str(row['Peptide']).strip()
            # BestAllele 可能是 PRIME 格式（A2402），也可能是其他
            best_allele = str(row.get('BestAllele', '')).strip()
            score = row['Score_bestAllele']
            # key 用肽段（PRIME 按 allele 分目录跑，每文件肽唯一对应一个 allele）
            # 为保险，也按 (pep, best_allele) 存；回贴时用 map key 的 allele 来查
            score_map[pep] = score                         # 肽段唯一（按 allele 分跑）
            if best_allele:
                score_map[(pep, best_allele)] = score      # (pep, allele) 复合 key 备用

        # 遍历 map，回贴
        for _, map_row in map_df.iterrows():
            raw_key = str(map_row['key'])
            if raw_key.startswith('SKIPPED_LEN:'):
                continue

            # map key 格式：peptide|allele_prime
            parts = raw_key.split('|', 1)
            if len(parts) < 2:
                continue
            pep, allele_pr = parts[0], parts[1]

            # 查分数：优先 (pep, allele) 复合，降级用肽段
            score_val = score_map.get((pep, allele_pr), score_map.get(pep, float('nan')))

            try:
                bb_indices = ast.literal_eval(str(map_row['backbone_indices']))
            except Exception:
                continue

            for idx in bb_indices:
                if idx in result.index:
                    result.at[idx, col_name] = score_val

    _do_merge(prime_mt_df, map_dir / 'prime_input_map_MT.csv', 'MT_PRIME')
    _do_merge(prime_wt_df, map_dir / 'prime_input_map_WT.csv', 'WT_PRIME')

    n_mt = result['MT_PRIME'].notna().sum()
    n_wt = result['WT_PRIME'].notna().sum()
    print(f'[PRIME] 回贴完成：MT_PRIME={n_mt} 行非空，WT_PRIME={n_wt} 行非空', file=sys.stderr)
    return result


def merge_immuneapp(
    backbone: pd.DataFrame,
    ia_mt_df: pd.DataFrame | None,
    ia_wt_df: pd.DataFrame | None,
    map_dir: Path,
) -> pd.DataFrame:
    """
    ImmuneApp 回贴。
    key = (Peptide, Allele)，通过 immuneapp_input_map_MT/WT.csv → bb_idx。
    若 Allele 列为 None（输出缺失），降级按肽段匹配（可能多 allele 歧义，打 WARN）。
    贴回列：MT_ImmuneApp，WT_ImmuneApp。
    """
    result = backbone.copy()
    result['MT_ImmuneApp'] = float('nan')
    result['WT_ImmuneApp'] = float('nan')

    def _do_merge(side_df: pd.DataFrame, map_path: Path, col_name: str, side: str):
        if side_df is None:
            return
        if not map_path.exists():
            print(f'[WARN] ImmuneApp map 不存在：{map_path}', file=sys.stderr)
            return

        map_df = pd.read_csv(map_path, encoding='utf-8')

        # 建 key → score
        score_map: dict = {}
        has_allele = side_df['Allele'].notna().any()
        for _, row in side_df.iterrows():
            pep   = str(row['Peptide']).strip()
            score = row['Immunogenicity_score']
            if has_allele and pd.notna(row['Allele']):
                allele = str(row['Allele']).strip()
                score_map[(pep, allele)] = score
            score_map[pep] = score   # 肽段单 key 备用

        for _, map_row in map_df.iterrows():
            raw_key = str(map_row['key'])
            if raw_key.startswith('SKIPPED_LEN:'):
                continue

            parts = raw_key.split('|', 1)
            if len(parts) < 2:
                continue
            pep, hla_std = parts[0], parts[1]

            score_val = score_map.get((pep, hla_std), score_map.get(pep, float('nan')))

            try:
                bb_indices = ast.literal_eval(str(map_row['backbone_indices']))
            except Exception:
                continue

            for idx in bb_indices:
                if idx in result.index:
                    result.at[idx, col_name] = score_val

    _do_merge(ia_mt_df, map_dir / 'immuneapp_input_map_MT.csv', 'MT_ImmuneApp', 'MT')
    _do_merge(ia_wt_df, map_dir / 'immuneapp_input_map_WT.csv', 'WT_ImmuneApp', 'WT')

    n_mt = result['MT_ImmuneApp'].notna().sum()
    n_wt = result['WT_ImmuneApp'].notna().sum()
    print(
        f'[ImmuneApp] 回贴完成：MT_ImmuneApp={n_mt} 行非空，'
        f'WT_ImmuneApp={n_wt} 行非空',
        file=sys.stderr
    )
    return result


def merge_deephlapan(
    backbone: pd.DataFrame,
    dp_mt_df: pd.DataFrame | None,
    dp_wt_df: pd.DataFrame | None,
) -> pd.DataFrame:
    """
    deepHLApan 回贴。
    Annotation = bb_idx（整数字符串），直接 at[idx, col] 填值，无需 map。
    贴回列：MT_deepHLApan，WT_deepHLApan。
    """
    result = backbone.copy()
    result['MT_deepHLApan'] = float('nan')
    result['WT_deepHLApan'] = float('nan')

    def _do_merge(side_df: pd.DataFrame, col_name: str, side: str):
        if side_df is None:
            return
        n_filled = 0
        for _, row in side_df.iterrows():
            ann = str(row['Annotation']).strip()
            if ann.startswith('SKIPPED_LEN'):
                continue
            try:
                bb_idx = int(ann)
            except ValueError:
                print(f'[WARN] deepHLApan-{side}：Annotation 非整数 bb_idx：{ann!r}', file=sys.stderr)
                continue
            if bb_idx in result.index:
                result.at[bb_idx, col_name] = row['immunogenic score']
                n_filled += 1
        print(f'[deepHLApan-{side}] 回贴 {n_filled} 行 → {col_name}', file=sys.stderr)

    _do_merge(dp_mt_df, 'MT_deepHLApan', 'MT')
    _do_merge(dp_wt_df, 'WT_deepHLApan', 'WT')

    n_mt = result['MT_deepHLApan'].notna().sum()
    n_wt = result['WT_deepHLApan'].notna().sum()
    print(
        f'[deepHLApan] 回贴完成：MT_deepHLApan={n_mt} 行非空，'
        f'WT_deepHLApan={n_wt} 行非空',
        file=sys.stderr
    )
    return result


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description='QuantImmuBench Wave-3 结果合并：PRIME/ImmuneApp/deepHLApan 回贴主干表'
    )
    _default_out = str(Path(__file__).resolve().parent.parent / 'out')

    parser.add_argument('--base',
        default=str(Path(_default_out) / 'merged_all_tools_5tools.xlsx'),
        help='底表路径（默认 merged_all_tools_5tools.xlsx；若不存在则用 master_backbone.csv）')
    parser.add_argument('--backbone',
        default=str(Path(_default_out) / 'master_backbone.csv'),
        help='master_backbone.csv 路径（--base 缺失时用）')
    parser.add_argument('--map-dir',
        default=_default_out,
        help='存放 *_input_map_MT/WT.csv 的目录（默认同 --out-dir）')
    parser.add_argument('--out-dir',
        default=_default_out,
        help='输出目录（默认 scripts/out/）')

    # PRIME
    parser.add_argument('--prime-result-MT', default=None,
        help='PRIME MT 侧输出（目录或单文件）')
    parser.add_argument('--prime-result-WT', default=None,
        help='PRIME WT 侧输出（目录或单文件）')

    # ImmuneApp
    parser.add_argument('--immuneapp-result-MT', default=None,
        help='ImmuneApp MT 侧输出（目录或单文件）')
    parser.add_argument('--immuneapp-result-WT', default=None,
        help='ImmuneApp WT 侧输出（目录或单文件）')

    # deepHLApan
    parser.add_argument('--deephlapan-result-MT', default=None,
        help='deepHLApan MT 侧输出 CSV 路径（*_predicted_result.csv）')
    parser.add_argument('--deephlapan-result-WT', default=None,
        help='deepHLApan WT 侧输出 CSV 路径')

    return parser.parse_args()


def main():
    args    = parse_args()
    map_dir = Path(args.map_dir).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f'[INFO] map_dir  = {map_dir}', file=sys.stderr)
    print(f'[INFO] out_dir  = {out_dir}', file=sys.stderr)

    # --- 读底表 ---
    base_path = Path(args.base).resolve()
    if base_path.exists():
        print(f'[INFO] 底表 = {base_path}（5tools xlsx）', file=sys.stderr)
        backbone = pd.read_excel(base_path, index_col='bb_idx', engine='openpyxl')
    else:
        bb_path = Path(args.backbone).resolve()
        print(
            f'[WARN] 底表 {base_path.name} 不存在，改用 backbone {bb_path}',
            file=sys.stderr
        )
        backbone = pd.read_csv(bb_path, index_col='bb_idx', encoding='utf-8')
    print(f'[backbone] 读入 {len(backbone)} 行，{len(backbone.columns)} 列', file=sys.stderr)

    current = backbone.copy()

    # ----------------------------------------------------------------
    # PRIME
    # ----------------------------------------------------------------
    prime_mt_df = None
    prime_wt_df = None
    if args.prime_result_MT:
        print(f'[PRIME-MT] 解析 {args.prime_result_MT}', file=sys.stderr)
        prime_mt_df = parse_prime(args.prime_result_MT, side='MT')
    else:
        print('[PRIME] --prime-result-MT 未提供，跳过 MT_PRIME', file=sys.stderr)

    if args.prime_result_WT:
        print(f'[PRIME-WT] 解析 {args.prime_result_WT}', file=sys.stderr)
        prime_wt_df = parse_prime(args.prime_result_WT, side='WT')
    else:
        print('[PRIME] --prime-result-WT 未提供，跳过 WT_PRIME', file=sys.stderr)

    if prime_mt_df is not None or prime_wt_df is not None:
        current = merge_prime(current, prime_mt_df, prime_wt_df, map_dir)
    else:
        current['MT_PRIME'] = float('nan')
        current['WT_PRIME'] = float('nan')

    # ----------------------------------------------------------------
    # ImmuneApp
    # ----------------------------------------------------------------
    ia_mt_df = None
    ia_wt_df = None
    if args.immuneapp_result_MT:
        print(f'[ImmuneApp-MT] 解析 {args.immuneapp_result_MT}', file=sys.stderr)
        ia_mt_df = parse_immuneapp(args.immuneapp_result_MT, side='MT')
    else:
        print('[ImmuneApp] --immuneapp-result-MT 未提供，跳过 MT_ImmuneApp', file=sys.stderr)

    if args.immuneapp_result_WT:
        print(f'[ImmuneApp-WT] 解析 {args.immuneapp_result_WT}', file=sys.stderr)
        ia_wt_df = parse_immuneapp(args.immuneapp_result_WT, side='WT')
    else:
        print('[ImmuneApp] --immuneapp-result-WT 未提供，跳过 WT_ImmuneApp', file=sys.stderr)

    if ia_mt_df is not None or ia_wt_df is not None:
        current = merge_immuneapp(current, ia_mt_df, ia_wt_df, map_dir)
    else:
        current['MT_ImmuneApp'] = float('nan')
        current['WT_ImmuneApp'] = float('nan')

    # ----------------------------------------------------------------
    # deepHLApan
    # ----------------------------------------------------------------
    dp_mt_df = None
    dp_wt_df = None
    if args.deephlapan_result_MT:
        print(f'[deepHLApan-MT] 解析 {args.deephlapan_result_MT}', file=sys.stderr)
        dp_mt_df = parse_deephlapan(args.deephlapan_result_MT, side='MT')
    else:
        print('[deepHLApan] --deephlapan-result-MT 未提供，跳过 MT_deepHLApan', file=sys.stderr)

    if args.deephlapan_result_WT:
        print(f'[deepHLApan-WT] 解析 {args.deephlapan_result_WT}', file=sys.stderr)
        dp_wt_df = parse_deephlapan(args.deephlapan_result_WT, side='WT')
    else:
        print('[deepHLApan] --deephlapan-result-WT 未提供，跳过 WT_deepHLApan', file=sys.stderr)

    if dp_mt_df is not None or dp_wt_df is not None:
        current = merge_deephlapan(current, dp_mt_df, dp_wt_df)
    else:
        current['MT_deepHLApan'] = float('nan')
        current['WT_deepHLApan'] = float('nan')

    # ----------------------------------------------------------------
    # 输出 merged_all_tools_8tools.xlsx
    # ----------------------------------------------------------------
    out_path = out_dir / 'merged_all_tools_8tools.xlsx'
    current.to_excel(out_path, index=True, engine='openpyxl')
    print(
        f'[ALL] 8tools 大表已写 {out_path}'
        f'（{len(current)} 行，{len(current.columns)} 列）',
        file=sys.stderr
    )

    # 列摘要
    wave3_cols = ['MT_PRIME', 'WT_PRIME', 'MT_ImmuneApp', 'WT_ImmuneApp',
                  'MT_deepHLApan', 'WT_deepHLApan']
    for col in wave3_cols:
        n = current[col].notna().sum() if col in current.columns else 0
        print(f'  {col}: {n} 行非空', file=sys.stderr)

    print('[DONE] merge_wave3.py 完成', file=sys.stderr)


if __name__ == '__main__':
    main()
