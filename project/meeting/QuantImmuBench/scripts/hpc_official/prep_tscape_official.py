#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
prep_tscape_official.py
===============================================================================
服务：quantimmu-bench / Conductor 节点 tools_dtu (W1窗) / lever=6 DTU 工具补跑 out_official。
（注：T-SCAPE 并非 DTU 工具，但同属本节点 lever=6 的 6 工具补跑批次。）

作用：读 master_backbone_official.csv → 取 unique (MT_Subpeptide, HLA_Allele) 对
      （≤20mer，超长跳过计数）→ 产 T-SCAPE 输入 + 回贴 map。

T-SCAPE 范围（MT-only）：只喂 MT 子肽 + HLA，不需 WT。HLA 保持标准格式
      HLA-A*02:01（T-SCAPE 原生接受 WHO 格式，无需转换）。

方向：score 0-1 越高越强（>0.5=免疫原），parse 不翻向。

输入：scripts/out_official/master_backbone_official.csv（只读）
输出：scripts/out_official/tscape_inputs/{tscape_input.csv (列 Allele,peptide),
      tscape_input_map.csv (列 Peptide,Allele,bb_idx_list)}

跑法（主线本地跑，我不跑）：
      python scripts/hpc_official/prep_tscape_official.py
      # 上传 tscape_input.csv 到 HPC 跑 submit_tscape.sbatch → 拉回 tscape_output.csv

依赖：标准库（csv, pathlib, collections）。Windows：pathlib + utf-8 + sys.stdout.reconfigure。
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

MAX_PEPTIDE_LEN = 20   # T-SCAPE 支持 ≤20mer（超长跳过）


def prep(backbone_path: Path, out_dir: Path, side: str = 'MT') -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    pep_col = 'MT_Subpeptide' if side == 'MT' else 'WT_Subpeptide'
    suffix = '' if side == 'MT' else '_WT'   # WT 侧另存，避免覆盖 MT 输入（向后兼容）
    tscape_input_path = out_dir / f'tscape_input{suffix}.csv'
    tscape_map_path = out_dir / f'tscape_input_map{suffix}.csv'

    pair_to_bbidx: dict = defaultdict(list)   # (Peptide, Allele) → [bb_idx, ...]
    skipped_long = 0
    skipped_empty = 0
    total_rows = 0

    with open(backbone_path, newline='', encoding='utf-8') as f_in:
        reader = csv.DictReader(f_in)
        for row in reader:
            total_rows += 1
            mt_pep  = row[pep_col].strip()
            hla_raw = row['HLA_Allele'].strip()
            bb_idx  = row['bb_idx'].strip()

            if not mt_pep:
                skipped_empty += 1
                continue
            if len(mt_pep) > MAX_PEPTIDE_LEN:
                skipped_long += 1
                print(f'[prep_tscape] SKIP bb_idx={bb_idx}: {mt_pep!r} 长度={len(mt_pep)} > {MAX_PEPTIDE_LEN}',
                      file=sys.stderr)
                continue

            pair_to_bbidx[(mt_pep, hla_raw)].append(bb_idx)

    unique_pairs = list(pair_to_bbidx.keys())

    # 写 T-SCAPE 输入（列 Allele,peptide —— 官方 pmhc_im 输入列名，peptide 小写）
    with open(tscape_input_path, 'w', newline='', encoding='utf-8') as f_out:
        writer = csv.writer(f_out)
        writer.writerow(['Allele', 'peptide'])
        for (pep, allele) in unique_pairs:
            writer.writerow([allele, pep])

    # 写 map（(Peptide,Allele) → bb_idx 列表，逗号分隔）
    with open(tscape_map_path, 'w', newline='', encoding='utf-8') as f_map:
        writer_map = csv.writer(f_map)
        writer_map.writerow(['Peptide', 'Allele', 'bb_idx_list'])
        for (pep, allele) in unique_pairs:
            writer_map.writerow([pep, allele, ','.join(pair_to_bbidx[(pep, allele)])])

    n_unique = len(unique_pairs)
    n_total_bb = sum(len(v) for v in pair_to_bbidx.values())
    print(f'[prep_tscape] side={side}（肽源列={pep_col}）')
    print(f'[prep_tscape] backbone 总行数        : {total_rows}')
    print(f'[prep_tscape] 跳过（肽空）          : {skipped_empty}')
    print(f'[prep_tscape] 跳过（>{MAX_PEPTIDE_LEN}mer）        : {skipped_long}')
    print(f'[prep_tscape] unique (MT, HLA) 对     : {n_unique}')
    print(f'[prep_tscape] 覆盖 bb_idx 数           : {n_total_bb}')
    print(f'[prep_tscape] 输出 tscape_input.csv   : {tscape_input_path}')
    print(f'[prep_tscape] 输出 tscape_input_map   : {tscape_map_path}')


def main():
    script_dir = Path(__file__).resolve().parent              # scripts/hpc_official
    default_backbone = script_dir.parent / 'out_official' / 'master_backbone_official.csv'
    default_out = script_dir.parent / 'out_official' / 'tscape_inputs'

    parser = argparse.ArgumentParser(
        description='Prepare T-SCAPE input from master_backbone_official.csv (MT-only, ≤20mer)'
    )
    parser.add_argument('--backbone', default=str(default_backbone),
                        help='master_backbone_official.csv 路径')
    parser.add_argument('--out-dir', default=str(default_out),
                        help='输出目录（default: %(default)s）')
    parser.add_argument('--side', choices=['MT', 'WT'], default='MT',
                        help='打分侧：MT 读 MT_Subpeptide（默认，写 tscape_input.csv）；'
                             'WT 读 WT_Subpeptide（写 tscape_input_WT.csv，8-11 DAI 补跑）。')
    args = parser.parse_args()

    backbone_path = Path(args.backbone)
    if not backbone_path.exists():
        print(f'[prep_tscape] ERROR: backbone 不存在: {backbone_path}', file=sys.stderr)
        sys.exit(1)

    prep(backbone_path, Path(args.out_dir), side=args.side)


if __name__ == '__main__':
    main()
