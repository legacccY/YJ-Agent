#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parse_netmhcpan_ba_official.py
===============================================================================
服务：quantimmu-bench / Conductor 节点 tools_dtu (W1窗) / lever=6 DTU 工具补跑 out_official。

作用：读 HPC 拉回的 netMHCpan-4.1 `-BA -xls` 输出 <allele_safe>_out.xls + pep_index.csv
      → 严格 (allele_safe, 子肽) 匹配回贴 bb_idx → 产
      scripts/out_official/netMHCpan_BA_official.csv（列 bb_idx, MT_netMHCpan_BA, WT_netMHCpan_BA）。
      1761 行对齐 backbone，缺分留空（NaN）。

★ 方向（重要，已查旧 parse_netmhcpan_ba.py 实际用列）★
      netMHCpan-4.1 的 `-xls` 文件**没有 Aff(nM) 列**（nM 仅出现在 stdout 文本表格，
      不在 -xls）。-xls 真实表头（2026-06-26 HPC 核验）：
        Pos Peptide ID core icore EL-score EL_Rank BA-score BA_Rank Ave NB
      → 本脚本取 **BA-score**（∈[0,1]，越高=越强结合=越免疫原），方向已与本 benchmark
        「越大越免疫原」一致，**不翻向**，直接作为 MT/WT_netMHCpan_BA。
      → 缺 BA-score 时回退 -BA_Rank（BA_Rank 越低越强，取负使越大越强）。
      ⚠️ 故任务描述里的「1-log50000(aff)」变换在此**不适用**（-xls 无 nM 列）；沿用旧脚本
        既定做法用 BA-score。# TODO researcher 确认：是否需改用 stdout 的 Aff(nM) 做 1-log50k
        （需 HPC 重定向 stdout，当前 -xls 管线不产 nM）。

严格匹配铁律：score 只在 (该等位文件实际跑出的子肽) 命中时赋值，缺即 NaN，
      **绝不肽级兜底回填别等位的分**。一个 (allele,subpep) 可对多 bb_idx（pep_index 逐 bb_idx 记），
      全部赋同值。is_MT=True→MT 列；is_MT=False→WT 列。

输入：
      --inputs-dir  含 pep_index.csv（prep_dtu_netmhcpan_official.py 产）+ <allele_safe>_out.xls
                    （HPC 跑完拉回），默认 scripts/out_official/dtu_netmhcpan_inputs/
      --backbone    master_backbone_official.csv（决定 1761 行顺序）
输出：scripts/out_official/netMHCpan_BA_official.csv

跑法（主线本地跑，我不跑）：
      python scripts/hpc_official/parse_netmhcpan_ba_official.py
依赖：标准库 + 同目录 official_io.py。Windows：pathlib + utf-8 + sys.stdout.reconfigure。

DTU 许可红线：netMHCpan 属 DTU 工具，未拿到书面同意前不得对外发表本工具 benchmark 数字。
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

TOOL = 'netMHCpan_BA'


def _find_col(header_row: list, patterns: list) -> int:
    for pat in patterns:
        rx = re.compile(pat, re.IGNORECASE)
        for i, col in enumerate(header_row):
            if rx.search(col):
                return i
    return -1


def parse_xls_file(xls_path: Path) -> dict:
    """解析 netMHCpan-4.1 -xls，返回 {peptide: {'BA_score': float, 'BA_Rank': float}}。"""
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
    bascore_col = _find_col(header_cols, [r'^BA-score$', r'^BA_score$', r'^BAscore$'])
    rank_col    = _find_col(header_cols, [r'^BA_Rank$', r'^BA-Rank$', r'^BARank$', r'%Rank_BA', r'Rnk_BA'])

    if pep_col == -1:
        print(f'  WARN: {xls_path.name} 无 Peptide 列。Cols={header_cols[:6]}', file=sys.stderr)
        return results
    if bascore_col == -1:
        print(f'  WARN: {xls_path.name} 无 BA-score 列。Cols={header_cols}', file=sys.stderr)
    if rank_col == -1:
        print(f'  WARN: {xls_path.name} 无 BA_Rank 列。Cols={header_cols}', file=sys.stderr)

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
        ba_score = float('nan')
        ba_rank = float('nan')
        try:
            if bascore_col != -1 and bascore_col < len(cols):
                ba_score = float(cols[bascore_col])
        except ValueError:
            pass
        try:
            if rank_col != -1 and rank_col < len(cols):
                ba_rank = float(cols[rank_col])
        except ValueError:
            pass
        results[peptide] = {'BA_score': ba_score, 'BA_Rank': ba_rank}
    return results


def load_pep_index(index_path: Path) -> dict:
    """返回 group: (allele_safe, subpeptide) → [(is_MT_str, bb_idx), ...]。"""
    group = defaultdict(list)
    with open(index_path, encoding='utf-8', newline='') as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            key = (row['allele_safe'], row['subpeptide'])
            group[key].append((row['is_MT'], row['bb_idx']))
    return group


def uni_score(ba_score: float, ba_rank: float) -> float:
    """统一方向：越大越免疫原。BA-score 已 0-1 越高越强 → 直接用；缺则回退 -BA_Rank。"""
    if not math.isnan(ba_score):
        return ba_score
    if not math.isnan(ba_rank):
        return -ba_rank
    return float('nan')


def main():
    script_dir = Path(__file__).resolve().parent
    default_inputs = script_dir.parent / 'out_official' / 'dtu_netmhcpan_inputs'
    default_backbone = script_dir.parent / 'out_official' / 'master_backbone_official.csv'
    default_out = script_dir.parent / 'out_official' / 'netMHCpan_BA_official.csv'

    ap = argparse.ArgumentParser(description='Parse netMHCpan-4.1 -BA -xls → netMHCpan_BA_official.csv')
    ap.add_argument('--inputs-dir', default=str(default_inputs),
                    help='含 pep_index.csv + <allele_safe>_out.xls（default: %(default)s）')
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
        print(f'[parse] WARNING: {inputs_dir} 下无 *_out.xls（HPC 跑完拉回？）。全列 NaN。', file=sys.stderr)

    mt_map, wt_map = {}, {}
    mt_alleles = set()
    for xls_path in xls_files:
        name = xls_path.stem
        allele_safe = name[:-4] if name.endswith('_out') else name
        scores = parse_xls_file(xls_path)
        print(f'[parse] {xls_path.name} allele_safe={allele_safe}  {len(scores)} 肽', file=sys.stderr)
        for peptide, sc in scores.items():
            us = uni_score(sc['BA_score'], sc['BA_Rank'])
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
    print('[parse] 方向：MT/WT_netMHCpan_BA = BA-score（0-1，越高越强结合）。'
          'DTU 许可红线：未获书面同意前勿对外发表。', file=sys.stderr)


if __name__ == '__main__':
    main()
