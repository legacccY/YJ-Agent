#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parse_netmhcstabpan_official.py
===============================================================================
服务：quantimmu-bench / Conductor 节点 tools_dtu (W1窗) / lever=6 DTU 工具补跑 out_official。

作用：读 HPC 拉回的 netMHCstabpan-1.0 输出 <allele_safe>_stab.xls + pep_index.csv（与
      netMHCpan 家族共用，prep_dtu_netmhcpan_official.py 产）→ 严格 (allele_safe, 子肽)
      匹配回贴 → 产 scripts/out_official/netMHCstabpan_official.csv
      （列 bb_idx, MT_netMHCstabpan, WT_netMHCstabpan）。1761 行对齐 backbone，缺即 NaN。

netMHCstabpan 输出列（DTU 官方）：pos HLA peptide Identity Pred Thalf(h) %Rank_Stab BindLevel
★ 方向 ★
      Pred        越高 = 越稳定（稳定性预测分 ~0-1）→ 越免疫原，**不翻向**。
      Thalf(h)    越高 = 越稳定（半衰期小时）。
      %Rank_Stab  越低 = 越稳定。
      统一取 **Pred**（越大越强）作为 MT/WT_netMHCstabpan；缺 Pred 回退 -%Rank_Stab。

⚠️ 格式 TODO：旧 netMHCstabpan-1.0（netMHCpan-2.8 时代 build）的 -xls 列布局未在新数据上
      重新核验；下方列名为模糊匹配，且 stdout 表格可能是空白对齐而非严格 tab。
      若 run_netmhcstabpan.sh 重定向 stdout 而非产 -xls，_split_row 会回退按空白切分。
      # TODO researcher/主线：HPC 首次跑后核实 <allele_safe>_stab.xls 实际表头与分隔符。

严格匹配铁律同 BA 版：缺即 NaN，绝不肽级兜底回填别等位。

输入：--xls-dir（含 <allele_safe>_stab.xls）、--index-csv（pep_index.csv，复用 netmhcpan 家族）、
      --backbone master_backbone_official.csv
输出：scripts/out_official/netMHCstabpan_official.csv
跑法：python scripts/hpc_official/parse_netmhcstabpan_official.py（主线本地跑，我不跑）
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

TOOL = 'netMHCstabpan'


def _find_col(header_row: list, patterns: list) -> int:
    for pat in patterns:
        rx = re.compile(pat, re.IGNORECASE)
        for i, col in enumerate(header_row):
            if rx.search(col):
                return i
    return -1


def _split_row(line: str) -> list:
    """tab 优先；无 tab 回退空白切分（兼容 stdout 对齐表）。"""
    if '\t' in line:
        return line.rstrip('\n').split('\t')
    return line.split()


def parse_xls_file(xls_path: Path) -> dict:
    """返回 {peptide: {'Pred': float, 'Thalf': float, 'RnkStab': float}}。"""
    results = {}
    with open(xls_path, encoding='utf-8', errors='replace') as fh:
        lines = fh.readlines()

    header_idx = -1
    for i, line in enumerate(lines):
        s = line.strip()
        if s == '' or s.startswith('#'):
            continue
        if set(s) <= set('-'):   # 跳过 ----- 分隔线
            continue
        if re.search(r'\bpeptide\b', s, re.IGNORECASE):
            header_idx = i
            break
    if header_idx == -1:
        print(f'  WARN: {xls_path.name} 找不到表头行，跳过。', file=sys.stderr)
        return results

    header_cols = _split_row(lines[header_idx])
    pep_col   = _find_col(header_cols, [r'^peptide$', r'\bpeptide\b'])
    pred_col  = _find_col(header_cols, [r'^Pred$', r'^Prediction$', r'^Score$'])
    thalf_col = _find_col(header_cols, [r'Thalf', r'half'])
    rnk_col   = _find_col(header_cols, [r'%?Rank_?Stab', r'%?Rank'])

    if pep_col == -1:
        print(f'  WARN: {xls_path.name} 无 Peptide 列。Cols={header_cols[:8]}', file=sys.stderr)
        return results
    if pred_col == -1:
        print(f'  WARN: {xls_path.name} 无 Pred 列。Cols={header_cols}', file=sys.stderr)
    if rnk_col == -1:
        print(f'  WARN: {xls_path.name} 无 %Rank_Stab 列。Cols={header_cols}', file=sys.stderr)

    for line in lines[header_idx + 1:]:
        s = line.strip()
        if s == '' or s.startswith('#') or set(s) <= set('-'):
            continue
        cols = _split_row(line)
        if len(cols) <= pep_col:
            continue
        peptide = cols[pep_col].strip()
        if not peptide or not peptide.isalpha():
            continue

        def _get(idx):
            if idx == -1 or idx >= len(cols):
                return float('nan')
            try:
                return float(cols[idx])
            except ValueError:
                return float('nan')

        results[peptide] = {'Pred': _get(pred_col), 'Thalf': _get(thalf_col), 'RnkStab': _get(rnk_col)}
    return results


def load_pep_index(index_path: Path) -> dict:
    group = defaultdict(list)
    with open(index_path, encoding='utf-8', newline='') as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            group[(row['allele_safe'], row['subpeptide'])].append((row['is_MT'], row['bb_idx']))
    return group


def uni_score(pred: float, rnkstab: float) -> float:
    if not math.isnan(pred):
        return pred
    if not math.isnan(rnkstab):
        return -rnkstab
    return float('nan')


def main():
    script_dir = Path(__file__).resolve().parent
    default_xls = script_dir.parent / 'out_official' / 'netmhcstabpan_inputs'
    default_index = script_dir.parent / 'out_official' / 'dtu_netmhcpan_inputs' / 'pep_index.csv'
    default_backbone = script_dir.parent / 'out_official' / 'master_backbone_official.csv'
    default_out = script_dir.parent / 'out_official' / 'netMHCstabpan_official.csv'

    ap = argparse.ArgumentParser(description='Parse netMHCstabpan-1.0 -xls → netMHCstabpan_official.csv')
    ap.add_argument('--xls-dir', default=str(default_xls),
                    help='含 <allele_safe>_stab.xls 的目录（default: %(default)s）')
    ap.add_argument('--index-csv', default=str(default_index),
                    help='pep_index.csv（复用 netmhcpan 家族）（default: %(default)s）')
    ap.add_argument('--backbone', default=str(default_backbone))
    ap.add_argument('--out-csv', default=str(default_out))
    args = ap.parse_args()

    index_path = Path(args.index_csv)
    if not index_path.exists():
        raise FileNotFoundError(f'pep_index.csv 不存在: {index_path}（先跑 prep_dtu_netmhcpan_official.py）')

    bb_order = load_backbone_bb_order(Path(args.backbone))
    group = load_pep_index(index_path)
    print(f'[parse] pep_index: {len(group)} 个 (allele_safe, subpep) 键', file=sys.stderr)

    xls_dir = Path(args.xls_dir)
    xls_files = sorted(xls_dir.glob('*_stab.xls')) if xls_dir.exists() else []
    if not xls_files:
        print(f'[parse] WARNING: {xls_dir} 下无 *_stab.xls（HPC 跑完拉回？）。全列 NaN。', file=sys.stderr)

    mt_map, wt_map = {}, {}
    mt_alleles = set()
    for xls_path in xls_files:
        name = xls_path.stem
        allele_safe = name[:-5] if name.endswith('_stab') else name
        scores = parse_xls_file(xls_path)
        print(f'[parse] {xls_path.name} allele_safe={allele_safe}  {len(scores)} 肽', file=sys.stderr)
        for peptide, sc in scores.items():
            us = uni_score(sc['Pred'], sc['RnkStab'])
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
    print('[parse] 方向：MT/WT_netMHCstabpan = Pred（越高越稳定→越强）。'
          'DTU 许可红线：未获书面同意前勿对外发表。', file=sys.stderr)


if __name__ == '__main__':
    main()
