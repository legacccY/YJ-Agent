#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parse_netmhcpan_ba.py
Service: quantimmu-bench §Tier-2  lever=NetMHCpan 4.1 -BA proxy baseline

Reads all <allele_safe>_out.xls files produced by run_netmhcpan_ba.sh
plus pep_index.csv produced by prep_netmhcpan_ba.py,
and joins them to produce a per-bb_idx score table.

Score direction (IMPORTANT):
  netMHCpan reports %Rank_BA where LOWER rank = stronger binding.
  We define netmhcpan_ba_score = -Rnk_BA  so that HIGHER score = stronger
  binding / more likely immunogenic (consistent with other tools in this
  benchmark where higher score = stronger signal).

Output schema (scripts/out/newtools/netmhcpan_ba_DS1DS2_scores.csv):
  bb_idx                 : int, join key back to master_backbone.csv
  netmhcpan_ba_Aff_nM   : float, binding affinity in nM  (lower = stronger)
  netmhcpan_ba_Rnk_BA   : float, %Rank_BA from netMHCpan  (lower = stronger)
  netmhcpan_ba_score     : float, = -Rnk_BA  (higher = stronger, unified direction)
  is_MT                  : bool str, 'True' if row derives from MT_Subpeptide,
                           'False' if from WT_Subpeptide
  pending_DTU_consent    : 'True' for ALL rows — DTU licensing red line:
                           do NOT publish benchmark numbers until DTU provides
                           written consent for use of netMHCpan in this context.

One bb_idx may appear TWICE (once is_MT=True, once is_MT=False) because
master_backbone stores both MT and WT subpeptides per row.

Windows note: pathlib + utf-8 throughout.
"""

import argparse
import csv
import os
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
    Parse a netMHCpan-4.1 -xls output file.

    Returns dict: {peptide_seq: {'Aff_nM': float, 'Rnk_BA': float}}

    The -xls output is a TSV. netMHCpan 4.1 output has comment lines
    starting with '#', then a header line, then data lines.

    Column names (typical, may vary slightly by version — we fuzzy-match):
      Peptide   : the peptide sequence
      Aff(nM)   : binding affinity in nM
      %Rank_BA  : BA rank percentage

    TODO: verify actual column names after first real run on HPC.
          If %Rank_BA is labelled differently (e.g. 'Rnk_BA', 'Rank_BA'),
          the patterns below cover the common variants.
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

    # Fuzzy column matching.
    # 实测 netMHCpan-4.1 -xls 真实表头（2026-06-26 HPC 核验）：
    #   Pos  Peptide  ID  core  icore  EL-score  EL_Rank  BA-score  BA_Rank  Ave  NB
    # 注意：-xls 文件里 **没有 Aff(nM) 列**（nM 仅出现在 stdout 表格），
    #       BA 信息 = `BA-score`(0-1,越高越强结合) + `BA_Rank`(%rank,越低越强)。
    pep_col     = _find_col(header_cols, [r'^Peptide$'])
    bascore_col = _find_col(header_cols, [r'^BA-score$', r'^BA_score$', r'^BAscore$'])
    rank_col    = _find_col(header_cols, [r'^BA_Rank$', r'^BA-Rank$', r'^BARank$', r'%Rank_BA', r'Rnk_BA'])

    if pep_col == -1:
        print(f'  WARN: Peptide column not found in {xls_path.name}. Cols: {header_cols[:6]}')
        return results
    if bascore_col == -1:
        print(f'  WARN: BA-score column not found in {xls_path.name}. Cols: {header_cols}')
    if rank_col == -1:
        print(f'  WARN: BA_Rank column not found in {xls_path.name}. Cols: {header_cols}')

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

        ba_score = float('nan')
        rnk_ba   = float('nan')

        try:
            if bascore_col != -1 and bascore_col < len(cols):
                ba_score = float(cols[bascore_col])
        except ValueError:
            pass

        try:
            if rank_col != -1 and rank_col < len(cols):
                rnk_ba = float(cols[rank_col])
        except ValueError:
            pass

        results[peptide] = {'BA_score': ba_score, 'Rnk_BA': rnk_ba}

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    script_dir = Path(__file__).resolve().parent
    default_inputs = (
        script_dir.parent.parent.parent
        / 'scripts' / 'out' / 'newtools' / 'netmhcpan_ba_inputs'
    )
    default_out = (
        script_dir.parent.parent.parent
        / 'scripts' / 'out' / 'newtools'
        / 'netmhcpan_ba_DS1DS2_scores.csv'
    )

    parser = argparse.ArgumentParser(
        description='Parse NetMHCpan-4.1 -BA XLS outputs and join to bb_idx'
    )
    parser.add_argument(
        '--inputs-dir',
        default=str(default_inputs),
        help='Directory containing <allele>_out.xls and pep_index.csv (default: %(default)s)',
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

    # key = (allele_safe, subpeptide, is_MT_str)  value = [bb_idx, ...]
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
        print('[parse] Have you run run_netmhcpan_ba.sh on HPC yet?')
        return

    print(f'[parse] Found {len(xls_files)} XLS files to parse.')

    # ------------------------------------------------------------------
    # Parse each XLS, join to pep_index, emit output rows
    # ------------------------------------------------------------------
    output_rows = []
    total_matched = 0
    total_missing = 0

    for xls_path in xls_files:
        # Derive allele_safe from filename: <allele_safe>_out.xls
        name = xls_path.stem          # e.g. HLA-A02-01_out
        if name.endswith('_out'):
            allele_safe = name[:-4]   # remove '_out'
        else:
            allele_safe = name

        print(f'[parse] {xls_path.name}  allele_safe={allele_safe}')
        scores = parse_xls_file(xls_path, allele_safe)
        print(f'        {len(scores)} peptide scores parsed')

        for peptide_seq, sc in scores.items():
            ba_pred = sc['BA_score']   # netMHCpan BA-score, 0-1, 越高越强结合
            rnk_ba  = sc['Rnk_BA']     # BA_Rank, %rank, 越低越强
            # Unified direction: higher = stronger binding = more immunogenic.
            # 直接用 BA-score（已是 0-1 越高越强），缺失时回退 -BA_Rank。
            import math
            if not math.isnan(ba_pred):
                uni_score = ba_pred
            elif not math.isnan(rnk_ba):
                uni_score = -rnk_ba
            else:
                uni_score = float('nan')

            # Join to pep_index for both is_MT=True and is_MT=False
            for is_mt_str in ('True', 'False'):
                key = (allele_safe, peptide_seq, is_mt_str)
                bb_idx_list = pep_index.get(key, [])
                if not bb_idx_list:
                    continue  # peptide not in index for this allele/role
                for bb_idx in bb_idx_list:
                    total_matched += 1
                    output_rows.append({
                        'bb_idx':                bb_idx,
                        'netmhcpan_ba_BAscore':  '' if math.isnan(ba_pred) else ba_pred,
                        'netmhcpan_ba_Rnk_BA':   '' if math.isnan(rnk_ba) else rnk_ba,
                        'netmhcpan_ba_score':     '' if math.isnan(uni_score) else uni_score,
                        'is_MT':                 is_mt_str,
                        'pending_DTU_consent':   'True',
                    })

    # Check for unmatched pep_index keys
    parsed_keys = set()
    for xls_path in xls_files:
        name = xls_path.stem
        allele_safe = name[:-4] if name.endswith('_out') else name
        scores = parse_xls_file(xls_path, allele_safe)
        for pep in scores:
            parsed_keys.add((allele_safe, pep))

    for (allele_safe, pep, is_mt), bb_list in pep_index.items():
        if (allele_safe, pep) not in parsed_keys:
            total_missing += len(bb_list)

    # ------------------------------------------------------------------
    # Write output CSV
    # ------------------------------------------------------------------
    fieldnames = [
        'bb_idx',
        'netmhcpan_ba_BAscore',
        'netmhcpan_ba_Rnk_BA',
        'netmhcpan_ba_score',
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
        print('        Check whether all alleles ran successfully in run_netmhcpan_ba.sh.')
    print('[parse] pending_DTU_consent=True on all rows. Do NOT publish until DTU consent received.')
    print('[parse] Score direction: netmhcpan_ba_score = BA-score (0-1, higher = stronger binding)')


if __name__ == '__main__':
    main()
