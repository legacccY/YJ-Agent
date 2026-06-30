#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
prep_trap_official.py
===============================================================================
服务：quantimmu-bench / 工具补跑舰队 / lever=工具补跑（TRAP 替代失效的 T-SCAPE）。

TRAP = T-cell Recognition potential of HLA-I presented peptides
       (Lee et al., Genome Medicine 2023, 15(1):70, DOI 10.1186/s13073-023-01225-z)
       repo https://github.com/ChloeHJ/TRAP  (license CC-BY-NC-SA 4.0)

作用：读 master_backbone（经 pep_index）+ netMHCpan-4.1 原始 -xls 输出 →
      为每个 MT 子肽（9-10mer）取 NetMHCpan %Rank（EL_Rank）→ 算 nlog2Rank →
      产 TRAP 官方推理输入 trap_input.csv + 回贴 map trap_input_map.csv。

★ TRAP 官方输入格式（已核 repo gbm_example_test_data.csv，2026-06-30 curl 实拉）★
      列 = Peptide,nlog2Rank
        - Peptide   : 9-10mer 肽序（TRAP 仅接受 9-10mer，超此长度不在范围 → 跳过）
        - nlog2Rank : = -log2(NetMHCpan %Rank)。%Rank 用 netMHCpan 打印的原始百分值
                       （如 0.33 / 11.0988），**不除以 100**。
                       验证：repo 例 FLEEIILKSL nlog2Rank=1.6095 → rank=2^-1.6095≈0.33%
                       （强结合），与 -xls 里 EL_Rank 量纲一致。
      hydrophobicity 由 TRAP 推理端从肽序内部算（dash_app.preprocess_test_peptides），
      **无需我们提供**，故输入只两列。

★ rank 取哪列（关键决策，见 TODO-RANK）★
      TRAP 论文说 "NetMHCpan rank"。NetMHCpan-4.1 默认 %Rank = EL_Rank（eluted ligand），
      呈递相关，与 "MHC-I presented peptides" 语义一致 → 本脚本取 **EL_Rank**。
      ⚠️ TODO-RANK：未在 TRAP 论文 Methods 找到 EL vs BA 的明确字样，需 researcher 复核
         原文。若论文实为 BA_Rank，把 RANK_COL 改 'BA_Rank' 重跑即可（同一批 -xls 已含）。
      注：我们已存的 netMHCpan_EL_official.csv 列 MT_netMHCpan_EL 是 **EL-score**（∈[0,1]），
         **不是 rank**，故不能复用该 CSV；rank 直接从原始 -xls 的 EL_Rank 列取（同一批官方
         输出，零额外 HPC 重跑）。

方向：TRAP value 越高越免疫原（>0.5=阳性），parse 端不翻向。MT-only（无 WT）。

输入（只读）：
      --pep-index   scripts/out_official/dtu_netmhcpan_inputs/pep_index.csv
                    （列 allele_safe, allele_netmhcpan, subpeptide, is_MT, bb_idx）
      --xls-dir     scripts/out_official/dtu_netmhcpan_inputs/  （含 <allele_safe>_out.xls）
输出：
      scripts/out_official/trap_inputs/trap_input.csv      （列 Peptide,nlog2Rank）
      scripts/out_official/trap_inputs/trap_input_map.csv  （列 Peptide,nlog2Rank,bb_idx_list）

跑法（主线本地跑，我不跑）：
      python scripts/hpc_official/prep_trap_official.py

依赖：标准库（csv, math, re, pathlib, collections）。Windows：pathlib + utf-8。
"""

import argparse
import csv
import math
import re
import sys
from pathlib import Path
from collections import defaultdict

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

# TRAP 仅接受 9-10mer
MIN_LEN, MAX_LEN = 9, 10
# 取 NetMHCpan %Rank 的列名（见 TODO-RANK）。EL_Rank=默认呈递 rank。
RANK_COL = 'EL_Rank'
# nlog2Rank join 精度（prep / parse 两端一致）
ROUND_NDIGITS = 6


def _find_col(header_cols: list, patterns: list) -> int:
    for pat in patterns:
        rx = re.compile(pat, re.IGNORECASE)
        for i, col in enumerate(header_cols):
            if rx.search(col):
                return i
    return -1


def parse_xls_rank(xls_path: Path, rank_col_name: str) -> dict:
    """读 netMHCpan-4.1 -xls → {peptide: rank(float)}（取 rank_col_name 列）。

    -xls 表头（2026-06-26 HPC 核）：
      Pos  Peptide  ID  core  icore  EL-score  EL_Rank  BA-score  BA_Rank  Ave  NB
    """
    out = {}
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
        return out

    header_cols = lines[header_idx].rstrip('\n').split('\t')
    pep_col = _find_col(header_cols, [r'^Peptide$'])
    # EL_Rank / EL-Rank / %Rank_EL ；BA_Rank / BA-Rank
    if rank_col_name == 'EL_Rank':
        rank_pats = [r'^EL_Rank$', r'^EL-Rank$', r'^ELRank$', r'%Rank_EL', r'Rnk_EL']
    elif rank_col_name == 'BA_Rank':
        rank_pats = [r'^BA_Rank$', r'^BA-Rank$', r'^BARank$', r'%Rank_BA', r'Rnk_BA']
    else:
        rank_pats = [rf'^{re.escape(rank_col_name)}$']
    rank_col = _find_col(header_cols, rank_pats)

    if pep_col == -1:
        print(f'  WARN: {xls_path.name} 无 Peptide 列。Cols={header_cols[:6]}', file=sys.stderr)
        return out
    if rank_col == -1:
        print(f'  WARN: {xls_path.name} 无 {rank_col_name} 列。Cols={header_cols}', file=sys.stderr)
        return out

    for line in lines[header_idx + 1:]:
        s = line.strip()
        if s == '' or s.startswith('#'):
            continue
        cols = s.split('\t')
        if len(cols) <= max(pep_col, rank_col):
            continue
        peptide = cols[pep_col].strip()
        if not peptide:
            continue
        try:
            rank = float(cols[rank_col])
        except ValueError:
            continue
        out[peptide] = rank
    return out


def prep(pep_index_path: Path, xls_dir: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    input_path = out_dir / 'trap_input.csv'
    map_path = out_dir / 'trap_input_map.csv'

    # 1. 解析全部 -xls → {(allele_safe, peptide): rank}
    xls_files = sorted(xls_dir.glob('*_out.xls'))
    if not xls_files:
        print(f'[prep_trap] ERROR: {xls_dir} 下无 *_out.xls', file=sys.stderr)
        sys.exit(1)
    allele_pep_rank = {}
    for xls_path in xls_files:
        name = xls_path.stem
        allele_safe = name[:-4] if name.endswith('_out') else name
        ranks = parse_xls_rank(xls_path, RANK_COL)
        for pep, rank in ranks.items():
            allele_pep_rank[(allele_safe, pep)] = rank
        print(f'[prep_trap] {xls_path.name} allele_safe={allele_safe}  {len(ranks)} 肽 {RANK_COL}',
              file=sys.stderr)

    # 2. 读 pep_index，取 is_MT==True 行 → (Peptide, nlog2Rank) → bb_idx
    pair_to_bb = defaultdict(list)   # (Peptide, nlog2Rank_rounded) → [bb_idx]
    pep_nlog = {}                    # (Peptide, nlog2Rank_rounded) → nlog2Rank(float, 已 round)
    total_mt = 0
    skip_len = 0
    skip_norank = 0
    skip_badrank = 0
    with open(pep_index_path, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            if str(row.get('is_MT', '')).strip() != 'True':
                continue
            total_mt += 1
            allele_safe = row['allele_safe'].strip()
            peptide = row['subpeptide'].strip()
            bb_idx = row['bb_idx'].strip()

            if not (MIN_LEN <= len(peptide) <= MAX_LEN):
                skip_len += 1
                continue
            rank = allele_pep_rank.get((allele_safe, peptide))
            if rank is None:
                skip_norank += 1
                continue
            if rank <= 0:          # log 无定义
                skip_badrank += 1
                print(f'[prep_trap] WARN bb_idx={bb_idx}: {RANK_COL}={rank} <=0，跳过',
                      file=sys.stderr)
                continue
            nlog2 = round(-math.log2(rank), ROUND_NDIGITS)
            key = (peptide, nlog2)
            pair_to_bb[key].append(bb_idx)
            pep_nlog[key] = nlog2

    unique_pairs = list(pair_to_bb.keys())

    # 3. 写 TRAP 输入（Peptide,nlog2Rank）
    with open(input_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['Peptide', 'nlog2Rank'])
        for (pep, nlog2) in unique_pairs:
            w.writerow([pep, nlog2])

    # 4. 写 map（(Peptide,nlog2Rank) → bb_idx 列表，逗号分隔）
    with open(map_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['Peptide', 'nlog2Rank', 'bb_idx_list'])
        for (pep, nlog2) in unique_pairs:
            w.writerow([pep, nlog2, ','.join(pair_to_bb[(pep, nlog2)])])

    n_cov_bb = sum(len(v) for v in pair_to_bb.values())
    print(f'[prep_trap] pep_index is_MT=True 行     : {total_mt}')
    print(f'[prep_trap] 跳过（非 {MIN_LEN}-{MAX_LEN}mer）      : {skip_len}')
    print(f'[prep_trap] 跳过（{RANK_COL} 缺）          : {skip_norank}')
    print(f'[prep_trap] 跳过（rank<=0）            : {skip_badrank}')
    print(f'[prep_trap] unique (Peptide,nlog2Rank) : {len(unique_pairs)}')
    print(f'[prep_trap] 覆盖 bb_idx 数              : {n_cov_bb}')
    print(f'[prep_trap] 输出 trap_input.csv        : {input_path}')
    print(f'[prep_trap] 输出 trap_input_map.csv    : {map_path}')
    print(f'[prep_trap] rank 列 = {RANK_COL}（见 TODO-RANK：EL vs BA 待 researcher 复核论文）')


def main():
    script_dir = Path(__file__).resolve().parent              # scripts/hpc_official
    out_official = script_dir.parent / 'out_official'
    default_pep_index = out_official / 'dtu_netmhcpan_inputs' / 'pep_index.csv'
    default_xls_dir = out_official / 'dtu_netmhcpan_inputs'
    default_out = out_official / 'trap_inputs'

    ap = argparse.ArgumentParser(
        description='Prepare TRAP input (Peptide,nlog2Rank) from netMHCpan -xls (MT-only, 9-10mer)')
    ap.add_argument('--pep-index', default=str(default_pep_index))
    ap.add_argument('--xls-dir', default=str(default_xls_dir))
    ap.add_argument('--out-dir', default=str(default_out))
    args = ap.parse_args()

    pep_index_path = Path(args.pep_index)
    if not pep_index_path.exists():
        print(f'[prep_trap] ERROR: pep_index 不存在: {pep_index_path}', file=sys.stderr)
        sys.exit(1)

    prep(pep_index_path, Path(args.xls_dir), Path(args.out_dir))


if __name__ == '__main__':
    main()
