#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
prep_dtu_netmhcpan_official.py
===============================================================================
服务：quantimmu-bench / Conductor 节点 tools_dtu (W1窗) / lever=6 DTU 工具在新官方
      RCC 数据上补跑 → out_official csv。

作用：读 master_backbone_official.csv → 按 HLA 等位分组 → 写 netMHCpan **家族共用**
      （-BA / -EL / netMHCstabpan / NetTepi 同一批 per-allele .pep 输入）的：
        <allele_safe>.pep   每行一条 unique 子肽（MT + WT 子肽去重）
        pep_index.csv       列：allele_safe, allele_netmhcpan, subpeptide, is_MT, bb_idx
                            —— 逐 bb_idx 一行（不去重），供 parse 精确回贴；
                            一个 (allele, subpep) 可对应多个 bb_idx（不同肽同子肽），
                            这里逐 bb_idx 记录以便 parse 回贴全部。
        allele_map.tsv      两列 TSV（allele_safe<TAB>allele_netmhcpan），供 run 脚本 while read。

HLA 格式：
      backbone  HLA-A*02:01
      CLI       HLA-A02:01   （去 *，留 :）
      文件名安全 HLA-A02-01   （去 *，: → -）

方向：本脚本只产输入，不涉及打分方向（方向在各 parse 脚本里统一为「越大越免疫原」）。

输入：scripts/out_official/master_backbone_official.csv（只读）
输出：scripts/out_official/dtu_netmhcpan_inputs/{<allele_safe>.pep, pep_index.csv, allele_map.tsv}

跑法（主线本地跑，我不跑）：
      python scripts/hpc_official/prep_dtu_netmhcpan_official.py
      # 产出后上传 inputs 目录到 HPC，由 run_netmhcpan_*.sh / run_netmhcstabpan.sh /
      # run_nettepi.sh 各自跑（NetTepi 只跑其支持的 13 等位，其余等位无输出 → parse 填 NaN）。

依赖：标准库（csv, pathlib, collections）。无第三方。
Windows：pathlib + utf-8 explicit + sys.stdout.reconfigure。
"""

import argparse
import csv
import sys
from pathlib import Path
from collections import defaultdict

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass


# ---------------------------------------------------------------------------
# HLA 格式 helpers
# ---------------------------------------------------------------------------

def hla_to_netmhcpan(h: str) -> str:
    """HLA-A*02:01 → HLA-A02:01（去 *，留 :）。"""
    return h.replace('*', '')


def hla_to_safe(h: str) -> str:
    """HLA-A*02:01 → HLA-A02-01（去 *，: → -；安全文件名）。"""
    return h.replace('*', '').replace(':', '-')


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    script_dir = Path(__file__).resolve().parent              # scripts/hpc_official
    default_backbone = script_dir.parent / 'out_official' / 'master_backbone_official.csv'
    default_out = script_dir.parent / 'out_official' / 'dtu_netmhcpan_inputs'

    parser = argparse.ArgumentParser(
        description='Prepare netMHCpan-family (BA/EL/stabpan/NetTepi) input .pep '
                    'from master_backbone_official.csv'
    )
    parser.add_argument('--backbone', default=str(default_backbone),
                        help='master_backbone_official.csv 路径（default: %(default)s）')
    parser.add_argument('--out-dir', default=str(default_out),
                        help='输出目录（default: %(default)s）')
    args = parser.parse_args()

    backbone_path = Path(args.backbone)
    out_dir = Path(args.out_dir)

    if not backbone_path.exists():
        raise FileNotFoundError(f'master_backbone_official.csv 不存在: {backbone_path}')

    out_dir.mkdir(parents=True, exist_ok=True)
    print(f'[prep] backbone  : {backbone_path}')
    print(f'[prep] output dir: {out_dir}')

    # allele_info[safe] = {'netmhcpan': str, 'peptides': set, 'index': [(subpep, is_MT_str, bb_idx)]}
    allele_info = defaultdict(lambda: {'netmhcpan': '', 'peptides': set(), 'index': []})

    n_rows = 0
    with open(backbone_path, encoding='utf-8', newline='') as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            n_rows += 1
            bb_idx  = row['bb_idx'].strip()
            hla_raw = row['HLA_Allele'].strip()
            mt_pep  = row['MT_Subpeptide'].strip()
            wt_pep  = row['WT_Subpeptide'].strip()

            safe = hla_to_safe(hla_raw)
            nmhc = hla_to_netmhcpan(hla_raw)
            allele_info[safe]['netmhcpan'] = nmhc

            if mt_pep:
                allele_info[safe]['peptides'].add(mt_pep)
                allele_info[safe]['index'].append((mt_pep, 'True', bb_idx))
            if wt_pep:
                allele_info[safe]['peptides'].add(wt_pep)
                allele_info[safe]['index'].append((wt_pep, 'False', bb_idx))

    n_alleles = len(allele_info)
    n_index = sum(len(d['index']) for d in allele_info.values())
    print(f'[prep] backbone 数据行: {n_rows}')
    print(f'[prep] {n_alleles} 个 unique HLA 等位，{n_index} 条 (allele, pep, is_MT, bb_idx) index 行')

    # 写 .pep
    for safe, data in sorted(allele_info.items()):
        pep_path = out_dir / f'{safe}.pep'
        sorted_peps = sorted(data['peptides'])
        with open(pep_path, 'w', encoding='utf-8') as fh:
            for pep in sorted_peps:
                fh.write(pep + '\n')
        print(f'[prep]   {safe}.pep  →  {len(sorted_peps)} unique peptides')

    # 写 pep_index.csv（逐 bb_idx 一行）
    index_path = out_dir / 'pep_index.csv'
    with open(index_path, 'w', encoding='utf-8', newline='') as fh:
        writer = csv.writer(fh)
        writer.writerow(['allele_safe', 'allele_netmhcpan', 'subpeptide', 'is_MT', 'bb_idx'])
        for safe, data in sorted(allele_info.items()):
            nmhc = data['netmhcpan']
            for (subpep, is_mt, bb_idx) in data['index']:
                writer.writerow([safe, nmhc, subpep, is_mt, bb_idx])
    print(f'[prep] pep_index.csv 写出 {n_index} 行 → {index_path}')

    # 写 allele_map.tsv
    allele_map_path = out_dir / 'allele_map.tsv'
    with open(allele_map_path, 'w', encoding='utf-8') as fh:
        for safe in sorted(allele_info.keys()):
            nmhc = allele_info[safe]['netmhcpan']
            fh.write(f'{safe}\t{nmhc}\n')
    print(f'[prep] allele_map.tsv 写出 {n_alleles} 等位 → {allele_map_path}')
    print('[prep] 完成。下一步：上传 inputs/ 到 HPC，跑 run_netmhcpan_*.sh / '
          'run_netmhcstabpan.sh / run_nettepi.sh（主线串行）。')


if __name__ == '__main__':
    main()
