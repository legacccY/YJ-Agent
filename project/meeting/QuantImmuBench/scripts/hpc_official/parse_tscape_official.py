#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parse_tscape_official.py
===============================================================================
服务：quantimmu-bench / Conductor 节点 tools_dtu (W1窗) / lever=6 工具补跑 out_official。
（T-SCAPE 非 DTU 工具，但同属本节点 6 工具补跑批次。）

作用：读 HPC 拉回的 T-SCAPE 输出 tscape_output.csv（列 Allele, peptide, score）+
      tscape_input_map.csv（prep_tscape_official.py 产，(Peptide,Allele)→bb_idx_list）
      → 按 (peptide, allele) 精确 join 回贴 → 产
      scripts/out_official/TSCAPE_official.csv（列 bb_idx, MT_TSCAPE）。
      1761 行对齐 backbone。

T-SCAPE 是 MT-only 工具（只需肽+HLA）→ 只产 MT_TSCAPE 列（无 WT）。

★ 方向 ★ score ∈[0,1]，越高越强（>0.5=免疫原），**不翻向** → MT_TSCAPE = score。

join 铁律：按 (peptide, 归一 allele) 精确匹配；allele 两边都归一到缩写型（去 HLA-、*、:）。
      一个 (pep, allele) 对多 bb_idx → 全赋同值。被 mhc_pseudo_matching 过滤掉的 allele
      不出现在输出 → 对应 bb_idx 诚实 NaN，绝不兜底。

输入：--tscape-out tscape_output.csv、--map tscape_input_map.csv、--backbone master_backbone_official.csv
输出：scripts/out_official/TSCAPE_official.csv
跑法：python scripts/hpc_official/parse_tscape_official.py（主线本地跑，我不跑）
依赖：标准库 + official_io.py。Windows：pathlib + utf-8。
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from official_io import (  # noqa: E402
    load_backbone_bb_order,
    write_official_mt_only,
    write_official_mt_wt,
)

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

TOOL = 'TSCAPE'


def _norm_allele(a: str) -> str:
    """HLA-A*24:02 / A2402 → A2402（去 HLA-、*、:）。"""
    a = str(a).strip()
    if a.upper().startswith('HLA-'):
        a = a[4:]
    elif a.upper().startswith('HLA'):
        a = a[3:]
    return a.replace('*', '').replace(':', '')


def read_tscape_output(output_path: Path) -> dict:
    """读 T-SCAPE 输出 → {(peptide, norm_allele): score}。"""
    pair_to_score = {}
    with open(output_path, newline='', encoding='utf-8') as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames or []
        required = {'Allele', 'peptide', 'score'}
        missing = required - set(fieldnames)
        if missing:
            raise ValueError(
                f'T-SCAPE 输出缺列: {missing}。实际列: {fieldnames}\n'
                '预期列: Allele, peptide(小写), score（T-SCAPE inference_csv.py 产生）')
        for row in reader:
            peptide = row['peptide'].strip()
            allele = _norm_allele(row['Allele'])
            try:
                score = float(row['score'])
            except ValueError as e:
                print(f'[parse_tscape] WARN: score 无法转 float: {row["score"]!r} '
                      f'(pep={peptide}, allele={allele})，跳过: {e}', file=sys.stderr)
                continue
            pair_to_score[(peptide, allele)] = score
    return pair_to_score


def read_map(map_path: Path) -> list:
    rows = []
    with open(map_path, newline='', encoding='utf-8') as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append(row)
    return rows


def build_side_map(map_path: Path, out_path: Path, tag: str) -> tuple:
    """一侧（MT 或 WT）：读 map + T-SCAPE 输出 → {bb_idx: score}。
    返回 (bb→分, 命中 bb 数, NaN bb 数, 命中等位集)。缺输出 → 空 map（全 NaN）。"""
    if not map_path.exists():
        raise FileNotFoundError(f'[{tag}] tscape_input_map 不存在: {map_path}（先跑 prep_tscape_official.py）')
    map_rows = read_map(map_path)

    if not out_path.exists():
        print(f'[parse_tscape][{tag}] WARNING: T-SCAPE 输出不存在: {out_path}（HPC 跑完拉回？）。全 NaN。',
              file=sys.stderr)
        pair_to_score = {}
    else:
        pair_to_score = read_tscape_output(out_path)
        print(f'[parse_tscape][{tag}] T-SCAPE 输出: {len(pair_to_score)} 个 (pep, allele) 对', file=sys.stderr)

    side_map = {}
    n_matched = n_nan = 0
    matched_alleles = set()
    for row in map_rows:
        peptide = row['Peptide'].strip()
        allele = _norm_allele(row['Allele'])
        bb_list = [x.strip() for x in row['bb_idx_list'].split(',') if x.strip()]
        score = pair_to_score.get((peptide, allele))
        if score is None:
            n_nan += len(bb_list)
            continue
        matched_alleles.add(allele)
        for bb_idx in bb_list:
            side_map[bb_idx] = round(score, 6)
            n_matched += 1
    print(f'[parse_tscape][{tag}] 有 score 的 bb_idx={n_matched}  NaN（allele 被过滤）={n_nan}', file=sys.stderr)
    return side_map, n_matched, n_nan, matched_alleles


def main():
    script_dir = Path(__file__).resolve().parent
    ts_dir = script_dir.parent / 'out_official' / 'tscape_inputs'
    default_out = ts_dir / 'tscape_output.csv'
    default_map = ts_dir / 'tscape_input_map.csv'
    default_backbone = script_dir.parent / 'out_official' / 'master_backbone_official.csv'
    default_out_csv = script_dir.parent / 'out_official' / 'TSCAPE_official.csv'

    ap = argparse.ArgumentParser(description='Parse T-SCAPE → TSCAPE_official.csv')
    ap.add_argument('--tscape-out', default=str(default_out),
                    help='MT 侧 T-SCAPE 输出 CSV（Allele,peptide,score）（default: %(default)s）')
    ap.add_argument('--map', default=str(default_map),
                    help='MT 侧 tscape_input_map.csv（prep_tscape_official.py --side MT 产）')
    ap.add_argument('--wt-tscape-out', default='',
                    help='WT 侧 T-SCAPE 输出 CSV。给了则输出 3 列 bb_idx,MT_TSCAPE,WT_TSCAPE；'
                         '不给则维持 2 列 MT-only（向后兼容 9mer）。')
    ap.add_argument('--wt-map', default='',
                    help='WT 侧 tscape_input_map_WT.csv（prep_tscape_official.py --side WT 产）。'
                         '与 --wt-tscape-out 成对给。')
    ap.add_argument('--backbone', default=str(default_backbone))
    ap.add_argument('--out-csv', default=str(default_out_csv))
    args = ap.parse_args()

    bb_order = load_backbone_bb_order(Path(args.backbone))

    mt_map, _, _, matched_alleles = build_side_map(Path(args.map), Path(args.tscape_out), 'MT')

    if args.wt_tscape_out:
        if not args.wt_map:
            raise SystemExit('[parse_tscape] --wt-tscape-out 需同时给 --wt-map（WT 侧 map 文件）。')
        wt_map, _, _, _ = build_side_map(Path(args.wt_map), Path(args.wt_tscape_out), 'WT')
        write_official_mt_wt(Path(args.out_csv), TOOL, bb_order, mt_map, wt_map,
                             n_distinct_alleles_mt=len(matched_alleles))
        print('[parse_tscape] 方向：MT_TSCAPE/WT_TSCAPE = score（0-1，越高越强，不翻向）。', file=sys.stderr)
    else:
        write_official_mt_only(Path(args.out_csv), TOOL, bb_order, mt_map,
                               n_distinct_alleles_mt=len(matched_alleles))
        print('[parse_tscape] 方向：MT_TSCAPE = score（0-1，越高越强，不翻向）。', file=sys.stderr)


if __name__ == '__main__':
    main()
