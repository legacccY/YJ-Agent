#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parse_trap_official.py
===============================================================================
服务：quantimmu-bench / 工具补跑舰队 / lever=工具补跑（TRAP 替代失效的 T-SCAPE）。

作用：读 run_trap_official.py 产的 trap_output.csv（列 Peptide, nlog2Rank, TRAP, ...）
      + prep_trap_official.py 产的 trap_input_map.csv（(Peptide,nlog2Rank)→bb_idx_list）
      → 按 (peptide, nlog2Rank) 精确 join 回贴 bb_idx → 产
      scripts/out_official/TRAP_official.csv（列 bb_idx, MT_TRAP）。1761 行对齐 backbone。

★ join 键 = (Peptide, round(nlog2Rank, 6)) ★
      TRAP value 是 (Peptide, nlog2Rank) 的确定性函数（嵌入只依赖肽序、hydrophobicity 由肽序算、
      MLP 第二维=nlog2Rank），故按此键 join 数学上精确，无歧义；同键多 bb_idx → 全赋同值（正确，
      非兜底造数）。prep 与本脚本均 round 到 6 位小数，run 脚本透传 nlog2Rank 不改精度。

★ 方向 ★ MT_TRAP = TRAP value ∈[0,1]，越高越免疫原（>0.5 阳性），**不翻向**。

T-SCAPE 是 MT-only（只肽+HLA）；TRAP 同为 MT-only（肽+rank）→ 只产 MT_TRAP 列（无 WT）。
被过滤的（非 9-10mer / rank 缺 / 等位未跑）→ 对应 bb_idx 诚实 NaN，**绝不肽级兜底造数**。

输入：--trap-out trap_output.csv、--map trap_input_map.csv、--backbone master_backbone_official.csv
输出：scripts/out_official/TRAP_official.csv
跑法：python scripts/hpc_official/parse_trap_official.py（主线本地跑，我不跑）
依赖：标准库 + official_io.py。Windows：pathlib + utf-8。

命名通知 W0：输出 TRAP_official.csv / 列 MT_TRAP；merge 别名 trap → TRAP。
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from official_io import load_backbone_bb_order, write_official_mt_only  # noqa: E402

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

TOOL = 'TRAP'
ROUND_NDIGITS = 6   # 与 prep_trap_official.py 一致


def _nlog_key(v) -> str:
    """nlog2Rank → 统一字符串键（round 到 6 位）。"""
    try:
        return f'{round(float(v), ROUND_NDIGITS):.6f}'
    except (TypeError, ValueError):
        return ''


def read_trap_output(output_path: Path) -> dict:
    """读 TRAP 输出 → {(peptide, nlog_key): TRAP_value(float)}。"""
    pair_to_score = {}
    with open(output_path, newline='', encoding='utf-8') as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames or []
        required = {'Peptide', 'nlog2Rank', 'TRAP'}
        missing = required - set(fieldnames)
        if missing:
            raise ValueError(
                f'TRAP 输出缺列: {missing}。实际列: {fieldnames}\n'
                '预期列: Peptide, nlog2Rank, TRAP（run_trap_official.py 产生）')
        for row in reader:
            peptide = str(row['Peptide']).strip()
            nlog_k = _nlog_key(row['nlog2Rank'])
            val = str(row['TRAP']).strip()
            if val.lower() in ('', 'nan', 'none', '<na>'):
                continue
            try:
                score = float(val)
            except ValueError as e:
                print(f'[parse_trap] WARN: TRAP 无法转 float: {val!r} '
                      f'(pep={peptide}, nlog2Rank={nlog_k})，跳过: {e}', file=sys.stderr)
                continue
            pair_to_score[(peptide, nlog_k)] = score
    return pair_to_score


def read_map(map_path: Path) -> list:
    rows = []
    with open(map_path, newline='', encoding='utf-8') as fh:
        for row in csv.DictReader(fh):
            rows.append(row)
    return rows


def main():
    script_dir = Path(__file__).resolve().parent
    tr_dir = script_dir.parent / 'out_official' / 'trap_inputs'
    default_out = tr_dir / 'trap_output.csv'
    default_map = tr_dir / 'trap_input_map.csv'
    default_backbone = script_dir.parent / 'out_official' / 'master_backbone_official.csv'
    default_out_csv = script_dir.parent / 'out_official' / 'TRAP_official.csv'

    ap = argparse.ArgumentParser(description='Parse TRAP → TRAP_official.csv')
    ap.add_argument('--trap-out', default=str(default_out),
                    help='TRAP 输出 CSV（Peptide,nlog2Rank,TRAP）（default: %(default)s）')
    ap.add_argument('--map', default=str(default_map),
                    help='prep_trap_official.py 产的 trap_input_map.csv')
    ap.add_argument('--backbone', default=str(default_backbone))
    ap.add_argument('--out-csv', default=str(default_out_csv))
    args = ap.parse_args()

    bb_order = load_backbone_bb_order(Path(args.backbone))

    map_path = Path(args.map)
    if not map_path.exists():
        raise FileNotFoundError(f'trap_input_map.csv 不存在: {map_path}（先跑 prep_trap_official.py）')
    map_rows = read_map(map_path)

    out_path = Path(args.trap_out)
    if not out_path.exists():
        print(f'[parse_trap] WARNING: TRAP 输出不存在: {out_path}（推理跑完？）。'
              f'MT_TRAP 全 NaN。', file=sys.stderr)
        pair_to_score = {}
    else:
        pair_to_score = read_trap_output(out_path)
        print(f'[parse_trap] TRAP 输出: {len(pair_to_score)} 个 (pep, nlog2Rank) 对', file=sys.stderr)

    mt_map = {}
    n_matched = 0
    n_nan = 0
    matched_peptides = set()
    for row in map_rows:
        peptide = str(row['Peptide']).strip()
        nlog_k = _nlog_key(row['nlog2Rank'])
        bb_list = [x.strip() for x in str(row['bb_idx_list']).split(',') if x.strip()]
        score = pair_to_score.get((peptide, nlog_k))
        if score is None:
            n_nan += len(bb_list)
            continue
        matched_peptides.add((peptide, nlog_k))
        for bb_idx in bb_list:
            mt_map[bb_idx] = round(score, 6)
            n_matched += 1

    print(f'[parse_trap] 有 TRAP 的 bb_idx={n_matched}  NaN（未匹配/被过滤）={n_nan}', file=sys.stderr)
    write_official_mt_only(Path(args.out_csv), TOOL, bb_order, mt_map,
                           n_distinct_alleles_mt=len(matched_peptides))
    print('[parse_trap] 方向：MT_TRAP = TRAP value（0-1，越高越免疫原，>0.5 阳性，不翻向）。',
          file=sys.stderr)
    print('[parse_trap] 注：n_distinct 这里报的是 distinct (peptide,nlog2Rank) 对数，非等位数。',
          file=sys.stderr)


if __name__ == '__main__':
    main()
