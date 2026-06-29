#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parse_netmhcpan_el.py
Service: quantimmu-bench §tools_present  lever=NetMHCpan 4.1 -EL presentation 列

EL 版孪生脚本（克隆 parse_netmhcpan_ba.py，只换抽取列 BA→EL）。
NetMHCpan-4.1 的 -xls 输出**同一张表同时含 EL 列与 BA 列**，故无须 HPC 重跑：
直接复用 run_w2 已落地的本地 65 个 <allele_safe>_out.xls
（默认 inputs-dir 仍指向同一个 netmhcpan_ba_inputs/，别新建目录）。

实测 netMHCpan-4.1 -xls 真实表头（tab 分隔，2026-06-26 HPC 核验）：
  Pos  Peptide  ID  core  icore  EL-score  EL_Rank  BA-score  BA_Rank  Ave  NB
  → EL-score / EL_Rank = presentation（呈递）信号，本脚本抽的就是这两列。

Score direction (IMPORTANT):
  EL-score ∈ [0,1]，**越高 = 越可能被呈递**（presentation），本就与本 benchmark
  「越高越强」约定一致 → netmhcpan_el_score = EL-score（不翻向）。
  EL_Rank 是 %rank，越低越强；仅在 EL-score 缺失时回退用 -EL_Rank。

Output schema (scripts/out/newtools/netmhcpan_el_DS1DS2_scores.csv):
  bb_idx                 : int(as str), join key back to master_backbone.csv
  netmhcpan_el_ELscore   : float, EL-score 0-1（越高越可能呈递）
  netmhcpan_el_Rnk_EL    : float, EL_Rank %rank（越低越强）
  netmhcpan_el_score     : float, = EL-score（higher = stronger，统一方向）
  is_MT                  : 'True' if row derives from MT_Subpeptide,
                           'False' if from WT_Subpeptide
  pending_DTU_consent    : 'True' for ALL rows — DTU 许可红线：
                           NetMHCpan 属 DTU 工具，未拿到书面同意前不得发表
                           本工具的 benchmark 数字（同 -BA 版）。

One bb_idx may appear TWICE (once is_MT=True, once is_MT=False) because
master_backbone stores both MT and WT subpeptides per row.

Windows note: pathlib + utf-8 throughout.
"""

import argparse
import csv
import math
import re
from pathlib import Path
from collections import defaultdict


# ---------------------------------------------------------------------------
# XLS parsing helpers
# ---------------------------------------------------------------------------

def _find_col(header_row: list, patterns: list) -> int:
    """
    Find column index by trying each regex pattern in order.
    Returns index of first match, or -1 if none found.
    """
    for pat in patterns:
        rx = re.compile(pat, re.IGNORECASE)
        for i, col in enumerate(header_row):
            if rx.search(col):
                return i
    return -1


def parse_xls_file(xls_path: Path, allele_safe: str) -> dict:
    """
    Parse a netMHCpan-4.1 -xls output file, extracting EL-score / EL_Rank.

    Returns dict: {peptide_seq: {'EL_score': float, 'Rnk_EL': float}}

    The -xls output is a TSV with optional '#' comment lines, then a header
    line containing 'Peptide', then data lines. We fuzzy-match column names.
    """
    results = {}

    with open(xls_path, encoding='utf-8', errors='replace') as fh:
        lines = fh.readlines()

    # Find header line: first non-comment line that contains "Peptide"
    header_idx = -1
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('#') or stripped == '':
            continue
        if re.search(r'\bPeptide\b', stripped, re.IGNORECASE):
            header_idx = i
            break

    if header_idx == -1:
        print(f'  WARN: could not find header line in {xls_path.name}, skipping.')
        return results

    header_cols = lines[header_idx].rstrip('\n').split('\t')

    # Fuzzy column matching for EL columns.
    # 实测表头: ... EL-score  EL_Rank  BA-score  BA_Rank ...
    pep_col     = _find_col(header_cols, [r'^Peptide$'])
    elscore_col = _find_col(header_cols, [r'^EL-score$', r'^EL_score$', r'^ELscore$'])
    rank_col    = _find_col(header_cols, [r'^EL_Rank$', r'^EL-Rank$', r'^ELRank$', r'%Rank_EL', r'Rnk_EL'])

    if pep_col == -1:
        print(f'  WARN: Peptide column not found in {xls_path.name}. Cols: {header_cols[:6]}')
        return results
    if elscore_col == -1:
        print(f'  WARN: EL-score column not found in {xls_path.name}. Cols: {header_cols}')
    if rank_col == -1:
        print(f'  WARN: EL_Rank column not found in {xls_path.name}. Cols: {header_cols}')

    # Parse data rows
    for line in lines[header_idx + 1:]:
        stripped = line.strip()
        if stripped == '' or stripped.startswith('#'):
            continue
        cols = stripped.split('\t')
        if len(cols) <= pep_col:
            continue

        peptide = cols[pep_col].strip()
        if not peptide:
            continue

        el_score = float('nan')
        rnk_el   = float('nan')

        try:
            if elscore_col != -1 and elscore_col < len(cols):
                el_score = float(cols[elscore_col])
        except ValueError:
            pass

        try:
            if rank_col != -1 and rank_col < len(cols):
                rnk_el = float(cols[rank_col])
        except ValueError:
            pass

        results[peptide] = {'EL_score': el_score, 'Rnk_EL': rnk_el}

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    script_dir = Path(__file__).resolve().parent
    # 复用 -BA 版同一个 inputs 目录（同一批 *_out.xls 同时含 EL 与 BA 列）
    default_inputs = (
        script_dir.parent.parent.parent
        / 'scripts' / 'out' / 'newtools' / 'netmhcpan_ba_inputs'
    )
    default_out = (
        script_dir.parent.parent.parent
        / 'scripts' / 'out' / 'newtools'
        / 'netmhcpan_el_DS1DS2_scores.csv'
    )

    parser = argparse.ArgumentParser(
        description='Parse NetMHCpan-4.1 -xls outputs for EL (presentation) and join to bb_idx'
    )
    parser.add_argument(
        '--inputs-dir',
        default=str(default_inputs),
        help='Directory with <allele>_out.xls and pep_index.csv (default: %(default)s)',
    )
    parser.add_argument(
        '--out-csv',
        default=str(default_out),
        help='Output CSV path (default: %(default)s)',
    )
    args = parser.parse_args()

    inputs_dir = Path(args.inputs_dir)
    out_csv    = Path(args.out_csv)

    if not inputs_dir.exists():
        raise FileNotFoundError(f'inputs_dir not found: {inputs_dir}')

    out_csv.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Load pep_index.csv → lookup: (allele_safe, subpeptide, is_MT) → [bb_idx, ...]
    # ------------------------------------------------------------------
    index_path = inputs_dir / 'pep_index.csv'
    if not index_path.exists():
        raise FileNotFoundError(
            f'pep_index.csv not found at {index_path}. '
            f'Run prep_netmhcpan_ba.py first.'
        )

    pep_index = defaultdict(list)
    with open(index_path, encoding='utf-8', newline='') as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            key = (row['allele_safe'], row['subpeptide'], row['is_MT'])
            pep_index[key].append(row['bb_idx'])

    print(f'[parse] pep_index loaded: {len(pep_index)} unique (allele, pep, is_MT) keys')

    # ------------------------------------------------------------------
    # Find all *_out.xls files
    # ------------------------------------------------------------------
    xls_files = sorted(inputs_dir.glob('*_out.xls'))
    if not xls_files:
        print(f'[parse] WARNING: no *_out.xls files found in {inputs_dir}')
        print('[parse] Have you run run_netmhcpan_ba.sh / staged the xls files yet?')
        return

    print(f'[parse] Found {len(xls_files)} XLS files to parse.')

    # ------------------------------------------------------------------
    # Parse each XLS once, cache, join to pep_index, emit output rows
    # ------------------------------------------------------------------
    output_rows = []
    total_matched = 0
    total_missing = 0
    parsed_keys = set()   # (allele_safe, peptide) seen in any xls

    for xls_path in xls_files:
        name = xls_path.stem                       # e.g. HLA-A02-01_out
        allele_safe = name[:-4] if name.endswith('_out') else name

        print(f'[parse] {xls_path.name}  allele_safe={allele_safe}')
        scores = parse_xls_file(xls_path, allele_safe)
        print(f'        {len(scores)} peptide scores parsed')

        for peptide_seq, sc in scores.items():
            parsed_keys.add((allele_safe, peptide_seq))
            el_score = sc['EL_score']   # 0-1, 越高越可能呈递
            rnk_el   = sc['Rnk_EL']     # %rank, 越低越强
            # Unified direction: higher = stronger presentation = more likely immunogenic.
            # EL-score 已是 0-1 越高越强 → 直接用；缺失回退 -EL_Rank。
            if not math.isnan(el_score):
                uni_score = el_score
            elif not math.isnan(rnk_el):
                uni_score = -rnk_el
            else:
                uni_score = float('nan')

            # Join to pep_index for both is_MT=True and is_MT=False
            for is_mt_str in ('True', 'False'):
                key = (allele_safe, peptide_seq, is_mt_str)
                bb_idx_list = pep_index.get(key, [])
                if not bb_idx_list:
                    continue
                for bb_idx in bb_idx_list:
                    total_matched += 1
                    output_rows.append({
                        'bb_idx':                 bb_idx,
                        'netmhcpan_el_ELscore':   '' if math.isnan(el_score) else el_score,
                        'netmhcpan_el_Rnk_EL':    '' if math.isnan(rnk_el) else rnk_el,
                        'netmhcpan_el_score':     '' if math.isnan(uni_score) else uni_score,
                        'is_MT':                  is_mt_str,
                        'pending_DTU_consent':    'True',
                    })

    # Check for unmatched pep_index keys (entries with no XLS score)
    for (allele_safe, pep, is_mt), bb_list in pep_index.items():
        if (allele_safe, pep) not in parsed_keys:
            total_missing += len(bb_list)

    # ------------------------------------------------------------------
    # Write output CSV
    # ------------------------------------------------------------------
    fieldnames = [
        'bb_idx',
        'netmhcpan_el_ELscore',
        'netmhcpan_el_Rnk_EL',
        'netmhcpan_el_score',
        'is_MT',
        'pending_DTU_consent',
    ]
    with open(out_csv, 'w', encoding='utf-8', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)

    print(f'\n[parse] Output: {len(output_rows)} rows → {out_csv}')
    print(f'[parse] matched={total_matched}  unmatched_index_entries={total_missing}')
    if total_missing > 0:
        print(f'[parse] WARNING: {total_missing} pep_index entries had no XLS score.')
        print('        Check whether all alleles have a corresponding *_out.xls.')
    print('[parse] pending_DTU_consent=True on all rows. Do NOT publish until DTU consent received.')
    print('[parse] Score direction: netmhcpan_el_score = EL-score (0-1, higher = more likely presented)')


if __name__ == '__main__':
    main()
