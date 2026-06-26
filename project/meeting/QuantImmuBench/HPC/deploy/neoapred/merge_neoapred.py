"""
merge_neoapred.py — NeoaPred 结果回贴脚本
==========================================
读 NeoaPred 输出 MhcPep_foreignness.csv + 映射表 neoapred_input_map.csv，
按 ID 映射回 bb_idx，在 master_backbone 中追加列 MT_NeoaPred。

输入:
  --foreignness-csv : NeoaPred 产出的 Foreignness/MhcPep_foreignness.csv
  --map-csv         : prep_neoapred_input.py 产出的 neoapred_input_map.csv
  --backbone        : master_backbone.csv（可选，用于拼完整输出；默认只输出分数列）

产出:
  scripts/out/newtools/neoapred_scores.csv
        列: bb_idx, MT_NeoaPred[, WT_NeoaPred]
        非 9mer 行（不在 map 中）= NaN

列说明:
  MT_NeoaPred : NeoaPred Foreignness_Score（MT 侧）
                越高越强免疫原，阈值参考 >0.5（见 README）
  WT_NeoaPred : 若 NeoaPred 输出含 WT 侧分数列，则产出；否则只有 MT_NeoaPred
                NeoaPred PepFore 模式计算 MT 相对 WT 的 foreignness，
                主输出为 MT 侧 Foreignness_Score；
                TODO: 确认 MhcPep_foreignness.csv 实际列结构（实跑后核实）

运行示例:
    python HPC/deploy/neoapred/merge_neoapred.py \\
        --foreignness-csv neoapred_out/test_out/Foreignness/MhcPep_foreignness.csv \\
        --map-csv         scripts/out/newtools/neoapred_input_map.csv \\
        --out-dir         scripts/out/newtools

    # 同时输出含全 backbone 列的 xlsx（可选）:
    python HPC/deploy/neoapred/merge_neoapred.py \\
        --foreignness-csv neoapred_out/test_out/Foreignness/MhcPep_foreignness.csv \\
        --map-csv         scripts/out/newtools/neoapred_input_map.csv \\
        --backbone        scripts/out/master_backbone.csv \\
        --out-dir         scripts/out/newtools
"""

import argparse
import ast
import os
import sys
from pathlib import Path

import pandas as pd


# ---------------------------------------------------------------------------
# 已知/预期的 Foreignness_Score 列名（NeoaPred 官方输出）
# 若实际列名不同，脚本会自动 fallback 并打印警告
# ---------------------------------------------------------------------------
_SCORE_COL_CANDIDATES = [
    'Foreignness_Score',    # 官方文档/paper 中引用的列名
    'foreignness_score',
    'Foreignness',
    'foreignness',
    'Score',
]

# WT 侧分数列（如果存在）
# TODO: 实跑后确认 MhcPep_foreignness.csv 是否含 WT 侧列
_WT_SCORE_COL_CANDIDATES = [
    'WT_Foreignness_Score',
    'wt_foreignness_score',
    'WT_Score',
    'WT_Foreignness',
]


def find_column(df: pd.DataFrame, candidates: list, label: str) -> str | None:
    """在 df 中找第一个匹配 candidates 的列名；找不到返回 None 并打印告警。"""
    for c in candidates:
        if c in df.columns:
            return c
    print(
        f'[WARN] 找不到 {label} 列（候选: {candidates}）。'
        f'实际列名: {list(df.columns)[:10]}',
        file=sys.stderr
    )
    return None


def parse_args():
    parser = argparse.ArgumentParser(
        description='NeoaPred Foreignness Score 回贴到 master_backbone'
    )
    parser.add_argument(
        '--foreignness-csv',
        required=True,
        help='NeoaPred 输出文件路径（Foreignness/MhcPep_foreignness.csv）'
    )
    parser.add_argument(
        '--map-csv',
        default=None,
        help='neoapred_input_map.csv 路径（默认自动定位 scripts/out/newtools/neoapred_input_map.csv）'
    )
    parser.add_argument(
        '--backbone',
        default=None,
        help='（可选）master_backbone.csv；提供后同时输出含全 backbone 列的 CSV'
    )
    parser.add_argument(
        '--out-dir',
        default=None,
        help='输出目录（默认 scripts/out/newtools/）'
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # ------------------------------------------------------------------
    # 路径解析
    # ------------------------------------------------------------------
    script_dir   = Path(__file__).resolve().parent       # HPC/deploy/neoapred/
    project_root = script_dir.parent.parent.parent       # QuantImmuBench/

    foreignness_path = Path(args.foreignness_csv).resolve()

    if args.map_csv:
        map_path = Path(args.map_csv).resolve()
    else:
        map_path = project_root / 'scripts' / 'out' / 'newtools' / 'neoapred_input_map.csv'

    if args.out_dir:
        out_dir = Path(args.out_dir).resolve()
    else:
        out_dir = project_root / 'scripts' / 'out' / 'newtools'

    out_dir.mkdir(parents=True, exist_ok=True)

    print(f'[INFO] foreignness_csv = {foreignness_path}', file=sys.stderr)
    print(f'[INFO] map_csv         = {map_path}',         file=sys.stderr)
    print(f'[INFO] out_dir         = {out_dir}',          file=sys.stderr)

    # ------------------------------------------------------------------
    # 验证输入文件
    # ------------------------------------------------------------------
    for p, label in [(foreignness_path, 'foreignness_csv'), (map_path, 'map_csv')]:
        if not p.exists():
            print(f'[ERROR] 文件不存在: {p} ({label})', file=sys.stderr)
            sys.exit(1)

    # ------------------------------------------------------------------
    # 读 NeoaPred 输出
    # ------------------------------------------------------------------
    forn_df = pd.read_csv(foreignness_path, low_memory=False)
    print(f'[foreignness] 读入 {len(forn_df)} 行，列：{list(forn_df.columns)}', file=sys.stderr)

    # 找 ID 列（应为 'ID'）
    if 'ID' not in forn_df.columns:
        # 尝试首列作为 ID
        print('[WARN] 未找到 ID 列，使用第一列作为 ID', file=sys.stderr)
        forn_df = forn_df.rename(columns={forn_df.columns[0]: 'ID'})

    # 找 MT Foreignness_Score 列
    mt_col = find_column(forn_df, _SCORE_COL_CANDIDATES, 'Foreignness_Score(MT)')
    if mt_col is None:
        print('[ERROR] 无法定位 Foreignness_Score 列，退出', file=sys.stderr)
        sys.exit(1)

    # 找 WT 侧分数列（可选，找不到不报错）
    wt_col = find_column(forn_df, _WT_SCORE_COL_CANDIDATES, 'WT_Foreignness_Score')
    if wt_col is None:
        print('[INFO] 未检测到 WT 侧分数列，只输出 MT_NeoaPred', file=sys.stderr)

    # 构建 ID → score 映射
    # TODO: 确认 NeoaPred 输出是否有重复 ID（PepFore 一般不重复，但多模型子模式可能有）
    id_to_mt  = dict(zip(forn_df['ID'].astype(str), forn_df[mt_col]))
    id_to_wt  = (
        dict(zip(forn_df['ID'].astype(str), forn_df[wt_col]))
        if wt_col else {}
    )

    # ------------------------------------------------------------------
    # 读映射表 neoapred_input_map.csv
    # ------------------------------------------------------------------
    map_df = pd.read_csv(map_path, low_memory=False)
    print(f'[map] 读入 {len(map_df)} 行（unique 9mer 条数）', file=sys.stderr)

    # map_df 列: ID, bb_idxs（bb_idxs 是 Python list repr "[0, 1, ...]"）

    # ------------------------------------------------------------------
    # 展开 ID → bb_idx，构建 bb_idx → MT_NeoaPred
    # ------------------------------------------------------------------
    bb_mt_records = {}   # bb_idx → MT_NeoaPred
    bb_wt_records = {}   # bb_idx → WT_NeoaPred（若有）

    missing_ids   = 0
    matched_ids   = 0

    for _, row in map_df.iterrows():
        id_str  = str(row['ID'])
        bbidxs_raw = str(row['bb_idxs'])

        # 解析 bb_idxs（Python list repr）
        try:
            bbidxs = ast.literal_eval(bbidxs_raw)
            if not isinstance(bbidxs, list):
                bbidxs = [bbidxs]
        except (ValueError, SyntaxError) as e:
            print(f'[WARN] 无法解析 bb_idxs "{bbidxs_raw}" for ID={id_str}: {e}',
                  file=sys.stderr)
            continue

        # 查分数
        if id_str in id_to_mt:
            matched_ids += 1
            mt_score = id_to_mt[id_str]
            wt_score = id_to_wt.get(id_str)
            for bb_idx in bbidxs:
                bb_mt_records[bb_idx] = mt_score
                if wt_score is not None:
                    bb_wt_records[bb_idx] = wt_score
        else:
            missing_ids += 1
            # 可能是烟测跑了部分 ID，此时正常；全量跑时 missing 应为 0
            if missing_ids <= 10:   # 只打前 10 个告警
                print(f'[WARN] ID {id_str} 在 NeoaPred 输出中未找到', file=sys.stderr)

    if missing_ids > 10:
        print(f'[WARN] ...（共 {missing_ids} 个 ID 未找到分数，仅显示前 10）', file=sys.stderr)

    print(f'[merge] 匹配 ID = {matched_ids}/{len(map_df)}，回贴 bb_idx 数 = {len(bb_mt_records)}',
          file=sys.stderr)

    # ------------------------------------------------------------------
    # 构建输出 DataFrame（包含全部 bb_idx 范围，非 9mer 行 NaN）
    # ------------------------------------------------------------------
    # 若提供 backbone，用其 bb_idx 范围保证完整性；否则只输出有分数的 bb_idx
    if args.backbone:
        backbone_path = Path(args.backbone).resolve()
        if not backbone_path.exists():
            print(f'[ERROR] backbone 文件不存在: {backbone_path}', file=sys.stderr)
            sys.exit(1)
        backbone = pd.read_csv(backbone_path, index_col='bb_idx', low_memory=False)
        all_bb_idxs = backbone.index.tolist()
        print(f'[backbone] 读入 {len(backbone)} 行', file=sys.stderr)
    else:
        # 只输出 9mer 有分数的行（非完整表，merge 时 outer join 补 NaN）
        all_bb_idxs = sorted(bb_mt_records.keys())
        print('[INFO] 未提供 backbone，只输出有分数的 bb_idx', file=sys.stderr)

    # 构建分数列
    scores_mt = [bb_mt_records.get(idx) for idx in all_bb_idxs]   # None = NaN

    out_data = {'bb_idx': all_bb_idxs, 'MT_NeoaPred': scores_mt}
    if wt_col:
        scores_wt = [bb_wt_records.get(idx) for idx in all_bb_idxs]
        out_data['WT_NeoaPred'] = scores_wt

    out_df = pd.DataFrame(out_data)

    non_nan = out_df['MT_NeoaPred'].notna().sum()
    print(f'[output] 总行 = {len(out_df)}，MT_NeoaPred 有值行 = {non_nan}', file=sys.stderr)

    # ------------------------------------------------------------------
    # 写出
    # ------------------------------------------------------------------
    out_path = out_dir / 'neoapred_scores.csv'
    out_df.to_csv(out_path, index=False, encoding='utf-8')
    print(f'[output] neoapred_scores.csv → {out_path}', file=sys.stderr)

    # 简单统计：分数分布
    if non_nan > 0:
        scores_valid = out_df['MT_NeoaPred'].dropna()
        print(
            f'[stats] MT_NeoaPred: min={scores_valid.min():.4f}, '
            f'max={scores_valid.max():.4f}, '
            f'mean={scores_valid.mean():.4f}, '
            f'>0.5 候选={( scores_valid > 0.5).sum()} 行',
            file=sys.stderr
        )

    print('[DONE] merge_neoapred.py 完成', file=sys.stderr)


if __name__ == '__main__':
    main()
