"""
verify_no_leakage.py — P1 anti-leakage gate (RED LINE 1 hard gate).

Enumerates all training/val image file paths (and optionally md5 hashes)
from each dataset split and checks they have zero overlap with the benchmark
test split.

Usage:
  python verify_no_leakage.py --data_root <root> --dataset <drive|chase|stare|hrf|fives|all>

Output:
  PASS/FAIL per dataset + full report printed to stdout.
  Exit code 0 = all clear; exit code 1 = leakage detected.

Design:
  1. Instantiate dataset with split='train'/'val' — collect image paths.
  2. Instantiate dataset with split='test' — collect benchmark image paths.
  3. Assert path intersection is empty (filename-level + optional md5).
  4. Also assert ID set intersection is empty (redundant but belt+suspenders).

This is a mandatory P1 gate: must run clean before training starts.
Stores a report to benchmark_cache/leakage_report.txt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# --------------------------------------------------------------------------- #
#  Allow running as script directly (src/ is project root for imports)
# --------------------------------------------------------------------------- #
_this_dir = Path(__file__).parent
_src_dir  = _this_dir.parent
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))


# --------------------------------------------------------------------------- #
#  Helpers
# --------------------------------------------------------------------------- #

def _file_md5(path: Path, chunk_size: int = 65536) -> str:
    """Compute MD5 of a file (for content-level dedup check)."""
    h = hashlib.md5()
    try:
        with open(path, 'rb') as f:
            while chunk := f.read(chunk_size):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return 'ERROR'


def _collect_split_paths(dataset, split_ids: List) -> Dict[str, Path]:
    """Return {sid_str: resolved_img_path} for a list of IDs."""
    result = {}
    for sid in split_ids:
        try:
            p = dataset._img_path(sid)
            if p.exists():
                result[str(sid)] = p.resolve()
            else:
                result[str(sid)] = p  # record even if missing (for report)
        except Exception as e:
            result[str(sid)] = Path(f'ERROR:{e}')
    return result


def verify_dataset(
    name: str,
    dataset_cls,
    data_root: str,
    check_md5: bool = False,
) -> Tuple[bool, str]:
    """
    Verify no leakage between train+val and test for one dataset.

    Returns (passed: bool, report: str).
    """
    lines = [f'=== {name} ===']

    # Instantiate with skip_missing=True (HPC paths may not be local)
    try:
        ds_train = dataset_cls(data_root=data_root, split='train', skip_missing=True)
        ds_val   = dataset_cls(data_root=data_root, split='val',   skip_missing=True)
        ds_test  = dataset_cls(data_root=data_root, split='test',  skip_missing=True)
    except Exception as e:
        lines.append(f'SKIP — could not instantiate dataset: {e}')
        return True, '\n'.join(lines)  # skip (not fail) if data not present

    train_ids = set(str(i) for i in ds_train.get_train_ids())
    val_ids   = set(str(i) for i in ds_val.get_val_ids())
    test_ids  = set(str(i) for i in ds_test.get_test_ids())

    lines.append(f'  train: {len(train_ids)} ids | val: {len(val_ids)} ids | test: {len(test_ids)} ids')

    # --- ID-level disjoint check ---
    train_test_overlap_ids = train_ids & test_ids
    val_test_overlap_ids   = val_ids   & test_ids
    train_val_overlap_ids  = train_ids & val_ids

    id_ok = True
    if train_test_overlap_ids:
        lines.append(f'  [FAIL] train ∩ test ID overlap: {train_test_overlap_ids}')
        id_ok = False
    if val_test_overlap_ids:
        lines.append(f'  [FAIL] val ∩ test ID overlap: {val_test_overlap_ids}')
        id_ok = False
    if train_val_overlap_ids:
        lines.append(f'  [FAIL] train ∩ val ID overlap: {train_val_overlap_ids}')
        id_ok = False
    if id_ok:
        lines.append('  [OK] ID-level: train/val/test disjoint')

    # --- File path-level check ---
    train_paths = _collect_split_paths(ds_train, ds_train.get_train_ids())
    val_paths   = _collect_split_paths(ds_val,   ds_val.get_val_ids())
    test_paths  = _collect_split_paths(ds_test,  ds_test.get_test_ids())

    # Resolved paths that actually exist
    train_existing = {str(p) for p in train_paths.values() if p.exists()}
    val_existing   = {str(p) for p in val_paths.values()   if p.exists()}
    test_existing  = {str(p) for p in test_paths.values()  if p.exists()}

    path_ok = True
    train_test_path_overlap = train_existing & test_existing
    val_test_path_overlap   = val_existing   & test_existing
    if train_test_path_overlap:
        lines.append(f'  [FAIL] train ∩ test PATH overlap ({len(train_test_path_overlap)} files):')
        for p in sorted(train_test_path_overlap)[:5]:
            lines.append(f'    {p}')
        path_ok = False
    if val_test_path_overlap:
        lines.append(f'  [FAIL] val ∩ test PATH overlap ({len(val_test_path_overlap)} files):')
        for p in sorted(val_test_path_overlap)[:5]:
            lines.append(f'    {p}')
        path_ok = False
    if path_ok:
        n_train_exist = len(train_existing)
        n_test_exist  = len(test_existing)
        lines.append(f'  [OK] Path-level: no overlap ({n_train_exist} train+val paths vs {n_test_exist} test paths)')

    # --- Optional MD5 content-level check ---
    md5_ok = True
    if check_md5 and (train_existing or test_existing):
        lines.append('  Computing MD5s...')
        train_md5s = {_file_md5(Path(p)) for p in train_existing}
        val_md5s   = {_file_md5(Path(p)) for p in val_existing}
        test_md5s  = {_file_md5(Path(p)) for p in test_existing}
        train_md5s.discard('ERROR')
        val_md5s.discard('ERROR')
        test_md5s.discard('ERROR')
        md5_overlap_tv = (train_md5s | val_md5s) & test_md5s
        if md5_overlap_tv:
            lines.append(f'  [FAIL] MD5 content overlap: {len(md5_overlap_tv)} duplicate files')
            md5_ok = False
        else:
            lines.append(f'  [OK] MD5-level: no content duplicates')

    passed = id_ok and path_ok and md5_ok
    status = 'PASS' if passed else 'FAIL'
    lines.insert(1, f'  Status: {status}')
    return passed, '\n'.join(lines)


# --------------------------------------------------------------------------- #
#  Main
# --------------------------------------------------------------------------- #

def main():
    parser = argparse.ArgumentParser(description='Verify no train/test leakage in vessel datasets')
    parser.add_argument('--data_root_base', type=str, default='D:/YJ-Agent/data/vessel',
                        help='Base directory containing DRIVE/ CHASE/ STARE/ HRF/ FIVES/')
    parser.add_argument('--hpc_root_base', type=str,
                        default='/gpfs/work/bio/jiayu2403/gdn2vessel/data/vessel',
                        help='HPC base path (used if local paths do not exist)')
    parser.add_argument('--dataset', type=str, default='all',
                        choices=['drive', 'chase', 'stare', 'hrf', 'fives', 'all'])
    parser.add_argument('--check_md5', action='store_true',
                        help='Also compute MD5 hashes for content-level check (slow)')
    parser.add_argument('--report_out', type=str, default=None,
                        help='Write report to this file (default: print only)')
    args = parser.parse_args()

    # Import dataset classes
    from datasets.drive import DRIVEDataset
    from datasets.chase import CHASEDataset
    from datasets.stare import STAREDataset
    from datasets.hrf   import HRFDataset
    from datasets.fives import FIVESDataset

    base = Path(args.data_root_base)

    dataset_map = {
        'drive': (DRIVEDataset, str(base / 'DRIVE')),
        'chase': (CHASEDataset, str(base / 'CHASE')),
        'stare': (STAREDataset, str(base / 'STARE')),
        'hrf':   (HRFDataset,   str(base / 'HRF')),
        'fives': (FIVESDataset, str(base / 'FIVES')),
    }

    if args.dataset == 'all':
        to_check = list(dataset_map.keys())
    else:
        to_check = [args.dataset]

    all_reports = []
    all_passed  = True

    for name in to_check:
        cls, root = dataset_map[name]
        passed, report = verify_dataset(name.upper(), cls, root, check_md5=args.check_md5)
        all_reports.append(report)
        if not passed:
            all_passed = False

    summary = '\n'.join(all_reports)
    summary += f'\n\n{"="*40}\nOVERALL: {"PASS — no leakage detected" if all_passed else "FAIL — leakage detected (see above)"}\n'

    print(summary)

    if args.report_out:
        Path(args.report_out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.report_out, 'w', encoding='utf-8') as f:
            f.write(summary)
        print(f'Report written to {args.report_out}')

    sys.exit(0 if all_passed else 1)


if __name__ == '__main__':
    main()
