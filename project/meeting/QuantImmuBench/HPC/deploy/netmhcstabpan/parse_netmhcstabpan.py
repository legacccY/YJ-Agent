#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parse_netmhcstabpan.py
Service: quantimmu-bench §tools_present  lever=netMHCstabpan-1.0 (DTU stability)

Reads all <allele_safe>_stab.xls files produced by run_netmhcstabpan.sh
plus pep_index.csv (REUSED from the netMHCpan-4.1 -BA inputs — same peptides ×
alleles), and joins them to a per-bb_idx score table.

netMHCstabpan output columns (DTU official, stdout layout):
    pos  HLA  peptide  Identity  Pred  Thalf(h)  %Rank_Stab  BindLevel
Direction:
    Pred         higher = MORE stable  (predicted stability score, ~0-1)
    Thalf(h)     higher = MORE stable  (predicted half-life in hours)
    %Rank_Stab   LOWER  = MORE stable  (rank vs reference peptides)
    BindLevel    SB / WB / (blank)

Score direction (unified across this benchmark = HIGHER = stronger signal):
    netmhcstabpan_score = Pred                 (already higher = more stable)
    fallback if Pred missing: -%Rank_Stab      (negated so higher = more stable)

Output schema (scripts/out/newtools/netmhcstabpan_DS1DS2_scores.csv):
    bb_idx                 : int, join key back to master_backbone.csv
    netmhcstabpan_Pred     : float, stability prediction (higher = more stable)
    netmhcstabpan_Thalf    : float, half-life hours       (higher = more stable)
    netmhcstabpan_RnkStab  : float, %Rank_Stab            (lower  = more stable)
    netmhcstabpan_score    : float, = Pred (fallback -RnkStab); higher = stronger
    is_MT                  : bool str, 'True' if from MT_Subpeptide else 'False'
    pending_DTU_consent    : 'True' for ALL rows — DTU licensing red line.

One bb_idx may appear TWICE (is_MT=True and is_MT=False).

⚠️ FLAG/FORMAT TODO: the netMHCstabpan-1.0 -xls layout is NOT verified for this
   exact (old, netMHCpan-2.8-era) build. Column headers are fuzzy-matched below;
   if -xls is unavailable and run_netmhcstabpan.sh redirected stdout instead,
   the stdout table is whitespace-aligned (not strictly tab-separated) — see
   the `_split_row` note and adjust the splitter if needed after the first run.

Windows note: pathlib + utf-8 throughout.
"""

import argparse
import csv
import math
import re
from pathlib import Path
from collections import defaultdict


# ---------------------------------------------------------------------------
# Column / row parsing helpers
# ---------------------------------------------------------------------------

def _find_col(header_row: list, patterns: list) -> int:
    """Find column index by trying each regex pattern in order. -1 if none."""
    for pat in patterns:
        rx = re.compile(pat, re.IGNORECASE)
        for i, col in enumerate(header_row):
            if rx.search(col):
                return i
    return -1


def _split_row(line: str) -> list:
    """
    Split a data/header row into columns.

    netMHCstabpan -xls output is TAB-separated. BUT if this old build lacks
    -xls and run_netmhcstabpan.sh redirected stdout, the table is
    whitespace-aligned. We try tab first; if that yields a single column,
    fall back to runs-of-whitespace.

    TODO: confirm which path applies after the first real run; if stdout was
          captured, the header line may also carry leading '#' or be preceded
          by a dashed separator line (handled by the header search in
          parse_xls_file).
    """
    if '\t' in line:
        return line.rstrip('\n').split('\t')
    return line.split()


def parse_xls_file(xls_path: Path) -> dict:
    """
    Parse one netMHCstabpan <allele>_stab.xls file.

    Returns dict: {peptide_seq: {'Pred': float, 'Thalf': float, 'RnkStab': float}}
    """
    results = {}

    with open(xls_path, encoding='utf-8', errors='replace') as fh:
        lines = fh.readlines()

    # Find header line: first non-comment line containing 'peptide'.
    header_idx = -1
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == '' or stripped.startswith('#'):
            continue
        # skip dashed separator lines (------) seen in net* stdout tables
        if set(stripped) <= set('-'):
            continue
        if re.search(r'\bpeptide\b', stripped, re.IGNORECASE):
            header_idx = i
            break

    if header_idx == -1:
        print(f'  WARN: no header line found in {xls_path.name}, skipping.')
        return results

    header_cols = _split_row(lines[header_idx])

    pep_col   = _find_col(header_cols, [r'^peptide$', r'\bpeptide\b'])
    # Pred = stability prediction; older builds may label it 'Pred' or 'Score'.
    pred_col  = _find_col(header_cols, [r'^Pred$', r'^Prediction$', r'^Score$'])
    thalf_col = _find_col(header_cols, [r'Thalf', r'half'])
    rnk_col   = _find_col(header_cols, [r'%?Rank_?Stab', r'%?Rank'])

    if pep_col == -1:
        print(f'  WARN: Peptide column not found in {xls_path.name}. Cols: {header_cols[:8]}')
        return results
    if pred_col == -1:
        print(f'  WARN: Pred column not found in {xls_path.name}. Cols: {header_cols}')
    if thalf_col == -1:
        print(f'  WARN: Thalf column not found in {xls_path.name}. Cols: {header_cols}')
    if rnk_col == -1:
        print(f'  WARN: %Rank_Stab column not found in {xls_path.name}. Cols: {header_cols}')

    for line in lines[header_idx + 1:]:
        stripped = line.strip()
        if stripped == '' or stripped.startswith('#'):
            continue
        if set(stripped) <= set('-'):
            continue
        cols = _split_row(line)
        if len(cols) <= pep_col:
            continue

        peptide = cols[pep_col].strip()
        if not peptide or not peptide.isalpha():
            # skip footer/summary lines that are not real peptide rows
            continue

        def _get(idx):
            if idx == -1 or idx >= len(cols):
                return float('nan')
            try:
                return float(cols[idx])
            except ValueError:
                return float('nan')

        results[peptide] = {
            'Pred':    _get(pred_col),
            'Thalf':   _get(thalf_col),
            'RnkStab': _get(rnk_col),
        }

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    script_dir = Path(__file__).resolve().parent
    newtools_dir = script_dir.parent.parent.parent / 'scripts' / 'out' / 'newtools'

    # pep_index.csv is REUSED from the -BA inputs (same peptides × alleles).
    default_index = newtools_dir / 'netmhcpan_ba_inputs' / 'pep_index.csv'
    # *_stab.xls outputs live in their own dir (see run_netmhcstabpan.sh).
    default_xls_dir = newtools_dir / 'netmhcstabpan_inputs'
    default_out = newtools_dir / 'netmhcstabpan_DS1DS2_scores.csv'

    parser = argparse.ArgumentParser(
        description='Parse netMHCstabpan-1.0 XLS outputs and join to bb_idx'
    )
    parser.add_argument('--index-csv', default=str(default_index),
                        help='pep_index.csv (reused from -BA) (default: %(default)s)')
    parser.add_argument('--xls-dir', default=str(default_xls_dir),
                        help='Directory of <allele>_stab.xls (default: %(default)s)')
    parser.add_argument('--out-csv', default=str(default_out),
                        help='Output CSV path (default: %(default)s)')
    args = parser.parse_args()

    index_path = Path(args.index_csv)
    xls_dir = Path(args.xls_dir)
    out_csv = Path(args.out_csv)

    if not index_path.exists():
        raise FileNotFoundError(
            f'pep_index.csv not found at {index_path}. '
            f'It is reused from the netMHCpan -BA inputs — make sure those exist.'
        )

    out_csv.parent.mkdir(parents=True, exist_ok=True)

    # Load pep_index → (allele_safe, subpeptide, is_MT) → [bb_idx, ...]
    pep_index = defaultdict(list)
    with open(index_path, encoding='utf-8', newline='') as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            key = (row['allele_safe'], row['subpeptide'], row['is_MT'])
            pep_index[key].append(row['bb_idx'])
    print(f'[parse] pep_index loaded: {len(pep_index)} unique (allele, pep, is_MT) keys')

    if not xls_dir.exists():
        print(f'[parse] WARNING: xls dir not found: {xls_dir}')
        print('[parse] Have you run run_netmhcstabpan.sh on HPC yet?')
        return

    xls_files = sorted(xls_dir.glob('*_stab.xls'))
    if not xls_files:
        print(f'[parse] WARNING: no *_stab.xls files found in {xls_dir}')
        print('[parse] Have you run run_netmhcstabpan.sh on HPC yet?')
        return
    print(f'[parse] Found {len(xls_files)} XLS files to parse.')

    output_rows = []
    total_matched = 0
    parsed_keys = set()

    for xls_path in xls_files:
        name = xls_path.stem               # e.g. HLA-A02-01_stab
        allele_safe = name[:-5] if name.endswith('_stab') else name

        print(f'[parse] {xls_path.name}  allele_safe={allele_safe}')
        scores = parse_xls_file(xls_path)
        print(f'        {len(scores)} peptide scores parsed')

        for peptide_seq, sc in scores.items():
            parsed_keys.add((allele_safe, peptide_seq))
            pred    = sc['Pred']
            thalf   = sc['Thalf']
            rnkstab = sc['RnkStab']

            # Unified direction: higher = more stable = stronger signal.
            if not math.isnan(pred):
                uni_score = pred
            elif not math.isnan(rnkstab):
                uni_score = -rnkstab
            else:
                uni_score = float('nan')

            for is_mt_str in ('True', 'False'):
                bb_idx_list = pep_index.get((allele_safe, peptide_seq, is_mt_str), [])
                for bb_idx in bb_idx_list:
                    total_matched += 1
                    output_rows.append({
                        'bb_idx':                bb_idx,
                        'netmhcstabpan_Pred':    '' if math.isnan(pred) else pred,
                        'netmhcstabpan_Thalf':   '' if math.isnan(thalf) else thalf,
                        'netmhcstabpan_RnkStab': '' if math.isnan(rnkstab) else rnkstab,
                        'netmhcstabpan_score':   '' if math.isnan(uni_score) else uni_score,
                        'is_MT':                 is_mt_str,
                        'pending_DTU_consent':   'True',
                    })

    # Count pep_index entries that got no score.
    total_missing = 0
    for (allele_safe, pep, _is_mt), bb_list in pep_index.items():
        if (allele_safe, pep) not in parsed_keys:
            total_missing += len(bb_list)

    fieldnames = [
        'bb_idx',
        'netmhcstabpan_Pred',
        'netmhcstabpan_Thalf',
        'netmhcstabpan_RnkStab',
        'netmhcstabpan_score',
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
        print('        Check whether all alleles ran in run_netmhcstabpan.sh.')
    print('[parse] pending_DTU_consent=True on all rows. Do NOT publish until DTU consent received.')
    print('[parse] Score direction: netmhcstabpan_score = Pred (higher = more stable).')


if __name__ == '__main__':
    main()
