"""
prep_neoapred_input.py — NeoaPred 输入预处理脚本
=================================================
读 master_backbone.csv → 过滤严格 9mer(MT+WT 均为 9mer) → 去重 unique
(MT_Subpeptide, WT_Subpeptide, HLA_Allele) → 写 NeoaPred 输入 CSV + map 文件。

输入:
  scripts/out/master_backbone.csv

产出(均在 --out-dir，默认 scripts/out/newtools/):
  neoapred_input.csv      — NeoaPred 入口 CSV
        列: ID, Allele, WT, Mut
        Allele 格式: 缩写型(如 A2402)，去 HLA- 去* 去:
        Mut = MT_Subpeptide, WT = WT_Subpeptide
        ID 自增: ID_0, ID_1, ...
  neoapred_input_map.csv  — ID → bb_idx 列表映射
        列: ID, bb_idxs
        同一 unique (MT, WT, HLA) 可对应多个 backbone 行

范围: 严格 9mer，仅 len(MT_Subpeptide)==9 且 len(WT_Subpeptide)==9 的行。
      其余长度最终 merge 时填 NaN，不强喂 NeoaPred。

运行示例:
    python HPC/deploy/neoapred/prep_neoapred_input.py
    python HPC/deploy/neoapred/prep_neoapred_input.py --smoke 5
    python HPC/deploy/neoapred/prep_neoapred_input.py \\
        --backbone scripts/out/master_backbone.csv \\
        --out-dir  scripts/out/newtools

烟测 (--smoke N):
    只取 unique 9mer 前 N 条，用于快速验格式，不跑全量。
    python HPC/deploy/neoapred/prep_neoapred_input.py --smoke 5
"""

import argparse
import os
import re
import sys
from pathlib import Path

import pandas as pd


# ---------------------------------------------------------------------------
# HLA 格式转换：标准 HLA-A*24:02 → NeoaPred 缩写型 A2402
# ---------------------------------------------------------------------------

_RE_STANDARD = re.compile(r'^HLA-([A-C])\*(\d{2}):(\d{2})$', re.IGNORECASE)


def hla_to_neoapred(hla_std: str) -> str | None:
    """
    HLA-A*24:02 → A2402  (locus 字母 + 4 位数字)
    HLA-B*57:01 → B5701
    HLA-C*07:02 → C0702

    仅支持标准三场格式 HLA-X*DD:DD；其他格式返回 None（调用方跳过该行）。
    """
    if not hla_std or not isinstance(hla_std, str):
        return None
    m = _RE_STANDARD.match(hla_std.strip())
    if not m:
        # 容错：尝试去前缀后匹配（不含 HLA- 的情况）
        candidate = hla_std.strip()
        for prefix in ('HLA-', 'hla-'):
            if candidate.startswith(prefix):
                candidate = candidate[len(prefix):]
                break
        # 尝试 X*DD:DD
        m2 = re.match(r'^([A-C])\*(\d{2}):(\d{2})$', candidate, re.IGNORECASE)
        if m2:
            return m2.group(1).upper() + m2.group(2) + m2.group(3)
        return None
    return m.group(1).upper() + m.group(2) + m.group(3)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description='NeoaPred 输入预处理：过滤 9mer + 去重 + HLA 缩写转换'
    )
    parser.add_argument(
        '--backbone',
        default=None,
        help='master_backbone.csv 路径（默认自动定位 scripts/out/master_backbone.csv）'
    )
    parser.add_argument(
        '--out-dir',
        default=None,
        help='输出目录（默认 scripts/out/newtools/）'
    )
    parser.add_argument(
        '--smoke',
        type=int,
        default=0,
        metavar='N',
        help='烟测模式：只取 unique 9mer 前 N 条（0=全量，默认 0）'
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # ------------------------------------------------------------------
    # 路径解析（相对本脚本向上找项目根）
    # ------------------------------------------------------------------
    script_dir = Path(__file__).resolve().parent            # HPC/deploy/neoapred/
    project_root = script_dir.parent.parent.parent          # QuantImmuBench/

    if args.backbone:
        backbone_path = Path(args.backbone).resolve()
    else:
        backbone_path = project_root / 'scripts' / 'out' / 'master_backbone.csv'

    if args.out_dir:
        out_dir = Path(args.out_dir).resolve()
    else:
        out_dir = project_root / 'scripts' / 'out' / 'newtools'

    out_dir.mkdir(parents=True, exist_ok=True)

    print(f'[INFO] backbone  = {backbone_path}', file=sys.stderr)
    print(f'[INFO] out_dir   = {out_dir}',        file=sys.stderr)
    if args.smoke:
        print(f'[INFO] smoke     = {args.smoke} (只取前 {args.smoke} unique 9mer)',
              file=sys.stderr)

    # ------------------------------------------------------------------
    # 读 master_backbone
    # ------------------------------------------------------------------
    if not backbone_path.exists():
        print(f'[ERROR] backbone 文件不存在: {backbone_path}', file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(backbone_path, index_col='bb_idx', low_memory=False)
    print(f'[backbone] 读入 {len(df)} 行', file=sys.stderr)

    # ------------------------------------------------------------------
    # 过滤严格 9mer（MT + WT 均为 9mer）
    # ------------------------------------------------------------------
    df['_mt_len'] = df['MT_Subpeptide'].astype(str).str.len()
    df['_wt_len'] = df['WT_Subpeptide'].astype(str).str.len()

    mask_9mer = (df['_mt_len'] == 9) & (df['_wt_len'] == 9)
    sub9 = df[mask_9mer].copy()
    print(f'[filter] 9mer (MT+WT 均 9mer) = {len(sub9)} 行', file=sys.stderr)

    # ------------------------------------------------------------------
    # 过滤 HLA 非空
    # ------------------------------------------------------------------
    sub9 = sub9[sub9['HLA_Allele'].notna()].copy()
    sub9 = sub9[sub9['HLA_Allele'].astype(str).str.strip() != '']

    # 转 NeoaPred 缩写型 HLA
    sub9['_hla_neoa'] = sub9['HLA_Allele'].apply(
        lambda h: hla_to_neoapred(str(h))
    )
    # 记录转换失败数
    failed = sub9['_hla_neoa'].isna().sum()
    if failed:
        print(f'[WARN] {failed} 行 HLA 无法转换为缩写型，将跳过', file=sys.stderr)
        bad_hlas = sub9.loc[sub9['_hla_neoa'].isna(), 'HLA_Allele'].value_counts()
        for h, cnt in bad_hlas.items():
            print(f'  {repr(h)}: {cnt} 行', file=sys.stderr)

    sub9 = sub9[sub9['_hla_neoa'].notna()].copy()
    print(f'[filter] HLA 转换成功后 = {len(sub9)} 行', file=sys.stderr)

    # ------------------------------------------------------------------
    # 去重 unique (MT_Subpeptide, WT_Subpeptide, HLA_Allele)
    # 并建 ID → bb_idx 列表映射
    # ------------------------------------------------------------------
    # 三元组 key 列
    sub9['_trio_key'] = (
        sub9['MT_Subpeptide'].astype(str) + '|' +
        sub9['WT_Subpeptide'].astype(str) + '|' +
        sub9['HLA_Allele'].astype(str)
    )

    # groupby 收集 bb_idx（index）
    key_to_bbidxs = {}
    key_to_row = {}   # key → first row (MT_sub, WT_sub, hla_neoa)
    for bb_idx, row in sub9.iterrows():
        key = row['_trio_key']
        key_to_bbidxs.setdefault(key, []).append(bb_idx)
        if key not in key_to_row:
            key_to_row[key] = {
                'MT_sub':   str(row['MT_Subpeptide']),
                'WT_sub':   str(row['WT_Subpeptide']),
                'hla_neoa': str(row['_hla_neoa']),
            }

    unique_keys = list(key_to_bbidxs.keys())
    print(f'[unique] unique (MT, WT, HLA) = {len(unique_keys)} 条', file=sys.stderr)

    # 烟测：截断
    if args.smoke and args.smoke > 0:
        unique_keys = unique_keys[:args.smoke]
        print(f'[smoke] 截断至 {len(unique_keys)} 条', file=sys.stderr)

    # ------------------------------------------------------------------
    # 构建 NeoaPred 输入 CSV：ID, Allele, WT, Mut
    # ------------------------------------------------------------------
    input_records = []
    map_records   = []

    for i, key in enumerate(unique_keys):
        row_info = key_to_row[key]
        id_str   = f'ID_{i}'
        input_records.append({
            'ID':     id_str,
            'Allele': row_info['hla_neoa'],
            'WT':     row_info['WT_sub'],
            'Mut':    row_info['MT_sub'],
        })
        map_records.append({
            'ID':      id_str,
            'bb_idxs': str(key_to_bbidxs[key]),   # Python list repr，merge 时 ast.literal_eval
        })

    input_df = pd.DataFrame(input_records, columns=['ID', 'Allele', 'WT', 'Mut'])
    map_df   = pd.DataFrame(map_records,   columns=['ID', 'bb_idxs'])

    # ------------------------------------------------------------------
    # 写出
    # ------------------------------------------------------------------
    input_path = out_dir / 'neoapred_input.csv'
    map_path   = out_dir / 'neoapred_input_map.csv'

    input_df.to_csv(input_path, index=False, encoding='utf-8')
    map_df.to_csv(map_path,     index=False, encoding='utf-8')

    print(f'[output] neoapred_input.csv     → {input_path} ({len(input_df)} 行)', file=sys.stderr)
    print(f'[output] neoapred_input_map.csv → {map_path}',                         file=sys.stderr)
    print('[DONE] prep_neoapred_input.py 完成', file=sys.stderr)


if __name__ == '__main__':
    main()
