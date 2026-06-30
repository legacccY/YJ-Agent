#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parse_netmhcpan_el_official.py
===============================================================================
服务：quantimmu-bench / Conductor 节点 tools_dtu (W1窗) / lever=6 DTU 工具补跑 out_official。

作用：读 netMHCpan-4.1 `-xls` 输出 <allele_safe>_out.xls（与 -BA 版**同一批文件**，-xls
      一张表同时含 EL 与 BA 列，无须 HPC 重跑）+ pep_index.csv → 严格 (allele_safe, 子肽)
      匹配回贴 → 产 scripts/out_official/netMHCpan_EL_official.csv
      （列 bb_idx, MT_netMHCpan_EL, WT_netMHCpan_EL）。1761 行对齐 backbone，缺即 NaN。

★ 方向 ★ -xls 真实表头（2026-06-26 HPC 核验）：
      Pos Peptide ID core icore EL-score EL_Rank BA-score BA_Rank Ave NB
      本脚本取 **EL-score**（∈[0,1] 呈递概率，越高=越可能被呈递=越免疫原），方向已一致，
      **不翻向**。缺 EL-score 回退 -EL_Rank（EL_Rank 越低越强 → 取负）。

严格匹配铁律同 BA 版：缺即 NaN，绝不肽级兜底回填别等位。

输入：--inputs-dir（含 pep_index.csv + <allele_safe>_out.xls，与 -BA 共用同一目录）
      --backbone master_backbone_official.csv
输出：scripts/out_official/netMHCpan_EL_official.csv
跑法：python scripts/hpc_official/parse_netmhcpan_el_official.py（主线本地跑，我不跑）
依赖：标准库 + official_io.py。Windows：pathlib + utf-8。
DTU 许可红线：未获书面同意前勿对外发表本工具数字。
"""

import argparse
import csv
import math
import re
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent))
from official_io import load_backbone_bb_order, write_official_mt_wt  # noqa: E402

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

TOOL = 'netMHCpan_EL'


def _find_col(header_row: list, patterns: list) -> int:
    for pat in patterns:
        rx = re.compile(pat, re.IGNORECASE)
        for i, col in enumerate(header_row):
            if rx.search(col):
                return i
    return -1


def parse_xls_file(xls_path: Path) -> dict:
    """返回 {peptide: {'EL_score': float, 'EL_Rank': float}}。"""
    results = {}
    with open(xls_path, encoding='utf-8', errors='replace') as fh:
        lines = fh.readlines()

    header_idx = -1
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith('#') or s == '':
            continue
        if re.search(r'\bPeptide\b', s, re.IGNORECASE):
            header_idx = i
            break
    if header_idx == -1:
        print(f'  WARN: {xls_path.name} 找不到表头行，跳过。', file=sys.stderr)
        return results

    header_cols = lines[header_idx].rstrip('\n').split('\t')
    pep_col     = _find_col(header_cols, [r'^Peptide$'])
    elscore_col = _find_col(header_cols, [r'^EL-score$', r'^EL_score$', r'^ELscore$'])
    rank_col    = _find_col(header_cols, [r'^EL_Rank$', r'^EL-Rank$', r'^ELRank$', r'%Rank_EL', r'Rnk_EL'])

    if pep_col == -1:
        print(f'  WARN: {xls_path.name} 无 Peptide 列。Cols={header_cols[:6]}', file=sys.stderr)
        return results
    if elscore_col == -1:
        print(f'  WARN: {xls_path.name} 无 EL-score 列。Cols={header_cols}', file=sys.stderr)
    if rank_col == -1:
        print(f'  WARN: {xls_path.name} 无 EL_Rank 列。Cols={header_cols}', file=sys.stderr)

    for line in lines[header_idx + 1:]:
        s = line.strip()
        if s == '' or s.startswith('#'):
            continue
        cols = s.split('\t')
        if len(cols) <= pep_col:
            continue
        peptide = cols[pep_col].strip()
        if not peptide:
            continue
        el_score = float('nan')
        el_rank = float('nan')
        try:
            if elscore_col != -1 and elscore_col < len(cols):
                el_score = float(cols[elscore_col])
        except ValueError:
            pass
        try:
            if rank_col != -1 and rank_col < len(cols):
                el_rank = float(cols[rank_col])
        except ValueError:
            pass
        results[peptide] = {'EL_score': el_score, 'EL_Rank': el_rank}
    return results


def load_pep_index(index_path: Path) -> dict:
    group = defaultdict(list)
    with open(index_path, encoding='utf-8', newline='') as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            group[(row['allele_safe'], row['subpeptide'])].append((row['is_MT'], row['bb_idx']))
    return group


def uni_score(el_score: float, el_rank: float) -> float:
    if not math.isnan(el_score):
        return el_score
    if not math.isnan(el_rank):
        return -el_rank
    return float('nan')


def main():
    script_dir = Path(__file__).resolve().parent
    default_inputs = script_dir.parent / 'out_official' / 'dtu_netmhcpan_inputs'
    default_backbone = script_dir.parent / 'out_official' / 'master_backbone_official.csv'
    default_out = script_dir.parent / 'out_official' / 'netMHCpan_EL_official.csv'

    ap = argparse.ArgumentParser(description='Parse netMHCpan-4.1 -xls EL → netMHCpan_EL_official.csv')
    ap.add_argument('--inputs-dir', default=str(default_inputs))
    ap.add_argument('--backbone', default=str(default_backbone))
    ap.add_argument('--out-csv', default=str(default_out))
    args = ap.parse_args()

    inputs_dir = Path(args.inputs_dir)
    index_path = inputs_dir / 'pep_index.csv'
    if not index_path.exists():
        raise FileNotFoundError(f'pep_index.csv 不存在: {index_path}（先跑 prep_dtu_netmhcpan_official.py）')

    bb_order = load_backbone_bb_order(Path(args.backbone))
    group = load_pep_index(index_path)
    print(f'[parse] pep_index: {len(group)} 个 (allele_safe, subpep) 键', file=sys.stderr)

    xls_files = sorted(inputs_dir.glob('*_out.xls'))
    if not xls_files:
        print(f'[parse] WARNING: {inputs_dir} 下无 *_out.xls。全列 NaN。', file=sys.stderr)

    mt_map, wt_map = {}, {}
    mt_alleles = set()
    for xls_path in xls_files:
        name = xls_path.stem
        allele_safe = name[:-4] if name.endswith('_out') else name
        scores = parse_xls_file(xls_path)
        print(f'[parse] {xls_path.name} allele_safe={allele_safe}  {len(scores)} 肽', file=sys.stderr)
        for peptide, sc in scores.items():
            us = uni_score(sc['EL_score'], sc['EL_Rank'])
            if math.isnan(us):
                continue
            for (is_mt, bb_idx) in group.get((allele_safe, peptide), []):
                if is_mt == 'True':
                    mt_map[bb_idx] = us
                    mt_alleles.add(allele_safe)
                else:
                    wt_map[bb_idx] = us

    write_official_mt_wt(Path(args.out_csv), TOOL, bb_order, mt_map, wt_map,
                         n_distinct_alleles_mt=len(mt_alleles))
    print('[parse] 方向：MT/WT_netMHCpan_EL = EL-score（0-1，越高越可能呈递）。'
          'DTU 许可红线：未获书面同意前勿对外发表。', file=sys.stderr)


if __name__ == '__main__':
    main()
