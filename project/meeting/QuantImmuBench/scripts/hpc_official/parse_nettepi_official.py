#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parse_nettepi_official.py
===============================================================================
服务：quantimmu-bench / Conductor 节点 tools_dtu (W1窗) / lever=6 DTU 工具补跑 out_official。

作用：读 HPC 拉回的 NetTepi-1.0 输出 + pep_index.csv（与 netMHCpan 家族共用，
      prep_dtu_netmhcpan_official.py 产）→ 严格 (allele_safe, 子肽) 匹配回贴 → 产
      scripts/out_official/NetTepi_official.csv（列 bb_idx, MT_NetTepi, WT_NetTepi）。
      1761 行对齐 backbone，缺即 NaN。

NetTepi 只支持 13 个 HLA 等位（DTU 官方），其余等位无输出 → 对应 bb_idx 诚实 NaN
      （部分覆盖，不兜底）。

★ 方向 ★ NetTepi 输出 **Comb**（综合 T 细胞表位分，越高=越强免疫原），方向已一致，
      **不翻向** → MT/WT_NetTepi = Comb。

⚠️ 文件名/列名 TODO：
      - 本脚本假设 NetTepi 每等位一个原始输出文件 `<allele_safe>_nettepi.txt`
        （allele_safe 同 pep_index，如 HLA-A02-01）。# TODO 主线：run_nettepi.sh 须按此命名，
        或用 --raw-dir + --suffix 指定实际后缀。
      - NetTepi 输出列名（Peptide / Comb / %Rank）按旧 parse_nettepi.py 的模糊匹配；
        # TODO researcher：HPC 首次跑后核实实际表头（含空格/大小写/分隔符）。

严格匹配铁律同 BA 版：缺即 NaN，绝不肽级兜底回填别等位。

输入：--raw-dir（含 <allele_safe>_nettepi.txt）、--index-csv（pep_index.csv 复用 netmhcpan 家族）、
      --backbone master_backbone_official.csv
输出：scripts/out_official/NetTepi_official.csv
跑法：python scripts/hpc_official/parse_nettepi_official.py（主线本地跑，我不跑）
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

TOOL = 'NetTepi'

# TODO researcher：跑通后核实 NetTepi 实际输出列头
COL_PEPTIDE = 'Peptide'
COL_COMB = 'Comb'
COL_RANK = '%Rank'

RAW_SUFFIX = '_nettepi.txt'   # <allele_safe>_nettepi.txt；# TODO 主线 run 脚本对齐此命名


def parse_raw_file(filepath: Path) -> dict:
    """解析单个 NetTepi 原始输出 → {peptide: {'Comb': float, 'Rank': float}}。"""
    results = {}
    with open(filepath, encoding='utf-8', errors='replace') as fh:
        lines = [l.rstrip('\n') for l in fh.readlines()]

    # 找数据表头：同时含 peptide 与 comb（避开 "# Input is in PEPTIDE format" 注释）
    header_idx = None
    for i, line in enumerate(lines):
        if line.lstrip().startswith('#'):
            continue
        if re.search(r'\bpeptide\b', line, re.IGNORECASE) and \
           re.search(r'\bcomb\b', line, re.IGNORECASE):
            header_idx = i
            break
    if header_idx is None:
        print(f'  WARN: {filepath.name} 找不到含 Peptide+Comb 的表头行。'
              f'# TODO 核实 NetTepi 输出格式。', file=sys.stderr)
        return results

    header_line = lines[header_idx]
    sep = '\t' if '\t' in header_line else None

    def split_line(line: str) -> list:
        return line.split(sep) if sep else re.split(r'\s+', line.strip())

    headers = [h.strip() for h in split_line(header_line)]

    def find_col(name: str) -> int | None:
        try:
            return headers.index(name)
        except ValueError:
            lower = [h.lower() for h in headers]
            try:
                return lower.index(name.lower())
            except ValueError:
                return None

    idx_pep = find_col(COL_PEPTIDE)
    if idx_pep is None:
        print(f'  WARN: {filepath.name} 无 Peptide 列。header={headers}', file=sys.stderr)
        return results
    idx_comb = find_col(COL_COMB)
    idx_rank = find_col(COL_RANK)
    if idx_comb is None:
        print(f'  WARN: {filepath.name} 无 Comb 列。header={headers}', file=sys.stderr)

    for line in lines[header_idx + 1:]:
        s = line.strip()
        if not s or s.startswith('#'):
            continue
        parts = split_line(line)
        if len(parts) <= idx_pep:
            continue
        pep = parts[idx_pep].strip()
        if not pep:
            continue
        comb_val = float('nan')
        rank_val = float('nan')
        if idx_comb is not None and idx_comb < len(parts):
            try:
                comb_val = float(parts[idx_comb])
            except ValueError:
                pass
        if idx_rank is not None and idx_rank < len(parts):
            try:
                rank_val = float(parts[idx_rank])
            except ValueError:
                pass
        results[pep] = {'Comb': comb_val, 'Rank': rank_val}
    return results


def load_pep_index(index_path: Path) -> dict:
    group = defaultdict(list)
    with open(index_path, encoding='utf-8', newline='') as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            group[(row['allele_safe'], row['subpeptide'])].append((row['is_MT'], row['bb_idx']))
    return group


def main():
    script_dir = Path(__file__).resolve().parent
    default_raw = script_dir.parent / 'out_official' / 'nettepi_out'
    default_index = script_dir.parent / 'out_official' / 'dtu_netmhcpan_inputs' / 'pep_index.csv'
    default_backbone = script_dir.parent / 'out_official' / 'master_backbone_official.csv'
    default_out = script_dir.parent / 'out_official' / 'NetTepi_official.csv'

    ap = argparse.ArgumentParser(description='Parse NetTepi-1.0 → NetTepi_official.csv')
    ap.add_argument('--raw-dir', default=str(default_raw),
                    help=f'含 <allele_safe>{RAW_SUFFIX} 的目录（default: %(default)s）')
    ap.add_argument('--suffix', default=RAW_SUFFIX,
                    help=f'NetTepi 原始输出文件后缀（default: {RAW_SUFFIX}）')
    ap.add_argument('--index-csv', default=str(default_index),
                    help='pep_index.csv（复用 netmhcpan 家族）')
    ap.add_argument('--backbone', default=str(default_backbone))
    ap.add_argument('--out-csv', default=str(default_out))
    args = ap.parse_args()

    index_path = Path(args.index_csv)
    if not index_path.exists():
        raise FileNotFoundError(f'pep_index.csv 不存在: {index_path}（先跑 prep_dtu_netmhcpan_official.py）')

    bb_order = load_backbone_bb_order(Path(args.backbone))
    group = load_pep_index(index_path)
    print(f'[parse] pep_index: {len(group)} 个 (allele_safe, subpep) 键', file=sys.stderr)

    raw_dir = Path(args.raw_dir)
    raw_files = sorted(raw_dir.glob(f'*{args.suffix}')) if raw_dir.exists() else []
    if not raw_files:
        print(f'[parse] WARNING: {raw_dir} 下无 *{args.suffix}（HPC 跑完拉回？）。全列 NaN。', file=sys.stderr)

    mt_map, wt_map = {}, {}
    mt_alleles = set()
    suf = args.suffix
    for raw_path in raw_files:
        name = raw_path.name
        allele_safe = name[:-len(suf)] if name.endswith(suf) else raw_path.stem
        scores = parse_raw_file(raw_path)
        print(f'[parse] {raw_path.name} allele_safe={allele_safe}  {len(scores)} 肽', file=sys.stderr)
        for peptide, sc in scores.items():
            comb = sc['Comb']
            if math.isnan(comb):
                continue
            for (is_mt, bb_idx) in group.get((allele_safe, peptide), []):
                if is_mt == 'True':
                    mt_map[bb_idx] = comb
                    mt_alleles.add(allele_safe)
                else:
                    wt_map[bb_idx] = comb

    write_official_mt_wt(Path(args.out_csv), TOOL, bb_order, mt_map, wt_map,
                         n_distinct_alleles_mt=len(mt_alleles))
    print('[parse] 方向：MT/WT_NetTepi = Comb（综合分越高越强）。'
          'NetTepi 仅支持 13 等位，其余 NaN。DTU 许可红线：未获书面同意前勿对外发表。', file=sys.stderr)


if __name__ == '__main__':
    main()
