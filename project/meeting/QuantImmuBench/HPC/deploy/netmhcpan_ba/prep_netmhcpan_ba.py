#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
prep_netmhcpan_ba.py
Service: quantimmu-bench §Tier-2  lever=NetMHCpan 4.1 -BA proxy baseline

Reads master_backbone.csv → groups by HLA allele → writes per-allele .pep files
and a pep_index.csv that maps (allele, subpeptide, is_MT) → bb_idx for score
back-annotation in parse_netmhcpan_ba.py.

HLA format note:
  master_backbone:  HLA-A*02:01
  netMHCpan CLI:    HLA-A02:01  (remove '*', keep ':')
  safe filename:    HLA-A02-01  (remove '*', replace ':' with '-')

Output files (in --out-dir):
  <allele_safe>.pep       one unique subpeptide per line (MT + WT, deduplicated)
  pep_index.csv           columns: allele_safe, allele_netmhcpan, subpeptide, is_MT, bb_idx
  allele_map.tsv          two-column TSV (allele_safe<TAB>allele_netmhcpan), used by run script

Windows note: pathlib used throughout; utf-8 encoding explicit.
"""

import argparse
import csv
import os
from pathlib import Path
from collections import defaultdict


# ---------------------------------------------------------------------------
# HLA format helpers
# ---------------------------------------------------------------------------

def hla_to_netmhcpan(h: str) -> str:
    """HLA-A*02:01 → HLA-A02:01  (remove '*', keep ':')"""
    return h.replace('*', '')


def hla_to_safe(h: str) -> str:
    """HLA-A*02:01 → HLA-A02-01  (remove '*', replace ':' → '-'; safe for filenames)"""
    return h.replace('*', '').replace(':', '-')


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    script_dir = Path(__file__).resolve().parent
    # Default paths relative to the deploy script location
    default_backbone = script_dir.parent.parent.parent / 'scripts' / 'out' / 'master_backbone.csv'
    default_out = script_dir.parent.parent.parent / 'scripts' / 'out' / 'newtools' / 'netmhcpan_ba_inputs'

    parser = argparse.ArgumentParser(
        description='Prepare NetMHCpan-4.1 -BA input .pep files from master_backbone.csv'
    )
    parser.add_argument(
        '--backbone',
        default=str(default_backbone),
        help='Path to master_backbone.csv (default: %(default)s)',
    )
    parser.add_argument(
        '--out-dir',
        default=str(default_out),
        help='Output directory for .pep files, pep_index.csv, allele_map.tsv (default: %(default)s)',
    )
    args = parser.parse_args()

    backbone_path = Path(args.backbone)
    out_dir = Path(args.out_dir)

    if not backbone_path.exists():
        raise FileNotFoundError(f'master_backbone.csv not found: {backbone_path}')

    out_dir.mkdir(parents=True, exist_ok=True)
    print(f'[prep] backbone  : {backbone_path}')
    print(f'[prep] output dir: {out_dir}')

    # ------------------------------------------------------------------
    # Pass 1: collect per-allele peptide sets and index rows
    # allele_info[safe] = {
    #   'netmhcpan': str,
    #   'peptides':  set of unique subpeptides,
    #   'index':     list of (subpeptide, is_MT_str, bb_idx)
    # }
    # ------------------------------------------------------------------
    allele_info = defaultdict(lambda: {'netmhcpan': '', 'peptides': set(), 'index': []})

    with open(backbone_path, encoding='utf-8', newline='') as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            bb_idx   = row['bb_idx'].strip()
            hla_raw  = row['HLA_Allele'].strip()
            mt_pep   = row['MT_Subpeptide'].strip()
            wt_pep   = row['WT_Subpeptide'].strip()

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
    n_index   = sum(len(d['index']) for d in allele_info.values())
    print(f'[prep] {n_alleles} unique HLA alleles, {n_index} total (allele, pep, bb_idx) index rows')

    # ------------------------------------------------------------------
    # Write .pep files
    # ------------------------------------------------------------------
    for safe, data in sorted(allele_info.items()):
        pep_path = out_dir / f'{safe}.pep'
        sorted_peps = sorted(data['peptides'])
        with open(pep_path, 'w', encoding='utf-8') as fh:
            for pep in sorted_peps:
                fh.write(pep + '\n')
        print(f'[prep]   {safe}.pep  →  {len(sorted_peps)} unique peptides')

    # ------------------------------------------------------------------
    # Write pep_index.csv
    # columns: allele_safe, allele_netmhcpan, subpeptide, is_MT, bb_idx
    # One row per (bb_idx × is_MT) entry; downstream parse explodes by this.
    # ------------------------------------------------------------------
    index_path = out_dir / 'pep_index.csv'
    with open(index_path, 'w', encoding='utf-8', newline='') as fh:
        writer = csv.writer(fh)
        writer.writerow(['allele_safe', 'allele_netmhcpan', 'subpeptide', 'is_MT', 'bb_idx'])
        for safe, data in sorted(allele_info.items()):
            nmhc = data['netmhcpan']
            for (subpep, is_mt, bb_idx) in data['index']:
                writer.writerow([safe, nmhc, subpep, is_mt, bb_idx])
    print(f'[prep] pep_index.csv written: {n_index} rows → {index_path}')

    # ------------------------------------------------------------------
    # Write allele_map.tsv  (used by run_netmhcpan_ba.sh)
    # Two-column TSV, no header, for easy `while read` in bash
    # ------------------------------------------------------------------
    allele_map_path = out_dir / 'allele_map.tsv'
    with open(allele_map_path, 'w', encoding='utf-8') as fh:
        for safe in sorted(allele_info.keys()):
            nmhc = allele_info[safe]['netmhcpan']
            fh.write(f'{safe}\t{nmhc}\n')
    print(f'[prep] allele_map.tsv written: {n_alleles} alleles → {allele_map_path}')

    print('[prep] Done. Next step: upload inputs/ to HPC and sbatch run_netmhcpan_ba.sh')


if __name__ == '__main__':
    main()
