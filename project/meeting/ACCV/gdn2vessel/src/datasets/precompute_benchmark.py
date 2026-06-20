"""
precompute_benchmark.py — Offline freeze of synthetic vessel disconnection benchmark.

P1 gate hard product: all baselines evaluate on the SAME frozen break masks,
so results are fully comparable. Same (dataset, severity, seed) → same gaps.

Protocol:
  For each (dataset, test split, severity in SEVERITY_GRID):
    - Load original GT mask (test split only — RED LINE 1)
    - Run apply_breaks(seed=base_seed + severity_offset) via synth_breaks.py
    - Save to benchmark_cache/<dataset>_<severity>_seed42.npz
      containing: mask_broken, vessel_segment_map, gap_records_json
    - On subsequent runs: load from cache, skip recompute (idempotent)

Usage:
  python precompute_benchmark.py \
      --data_root_base /gpfs/work/bio/jiayu2403/gdn2vessel/data/vessel \
      --cache_dir      /gpfs/work/bio/jiayu2403/gdn2vessel/data/benchmark_cache \
      --dataset all

Output:
  benchmark_cache/
    drive_Easy_seed42.npz
    drive_Medium_seed42.npz
    drive_Hard_seed42.npz
    drive_Extreme_seed42.npz
    chase_Easy_seed42.npz
    ...
    manifest.json   (maps dataset+severity → npz path + n_gaps + timestamp)

NPZ schema (per file):
  mask_broken:        (H, W) uint8 {0,1}
  vessel_segment_map: (H, W) int32
  gap_records_json:   bytes (JSON-encoded List[GapRecord as dict])
  image_id:           str (sample ID)
  dataset:            str
  severity:           str
  seed_used:          int
  original_shape:     (H, W) as int array

Windows note: no multiprocessing used here (spawn overhead not worth it for
one-time precompute). Single-process serial is fine.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

# --------------------------------------------------------------------------- #
#  Path setup
# --------------------------------------------------------------------------- #
_this_dir = Path(__file__).parent
_src_dir  = _this_dir.parent
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from benchmark.synth_breaks import apply_breaks, SEVERITY_GRID


# --------------------------------------------------------------------------- #
#  Constants
# --------------------------------------------------------------------------- #
BASE_SEED = 42  # reproducible benchmark seed


def severity_seed(base: int, severity_name: str) -> int:
    """Derive per-severity seed from base seed. Matches apply_breaks_all_severities."""
    sev_list = list(SEVERITY_GRID.keys())  # ['Easy', 'Medium', 'Hard', 'Extreme']
    idx = sev_list.index(severity_name)
    return base + idx * 1000


# --------------------------------------------------------------------------- #
#  Dataset registry (maps name → (cls, subdir))
# --------------------------------------------------------------------------- #

def _build_registry(base_root: Path):
    from datasets.drive import DRIVEDataset
    from datasets.chase import CHASEDataset
    from datasets.stare import STAREDataset
    from datasets.hrf   import HRFDataset
    from datasets.fives import FIVESDataset

    return {
        'drive': (DRIVEDataset, str(base_root / 'DRIVE')),
        'chase': (CHASEDataset, str(base_root / 'CHASE')),
        'stare': (STAREDataset, str(base_root / 'STARE')),
        'hrf':   (HRFDataset,   str(base_root / 'HRF')),
        'fives': (FIVESDataset, str(base_root / 'FIVES')),
    }


# --------------------------------------------------------------------------- #
#  Core precompute for one (dataset, severity)
# --------------------------------------------------------------------------- #

def precompute_one(
    dataset_name: str,
    dataset_cls,
    data_root: str,
    severity: str,
    cache_dir: Path,
    base_seed: int = BASE_SEED,
    force_recompute: bool = False,
) -> List[Dict]:
    """
    Precompute break masks for all test-split images of one dataset at one severity.

    Returns list of manifest entries (one per test image).
    """
    params = SEVERITY_GRID[severity]
    seed = severity_seed(base_seed, severity)

    # Load test split (RED LINE 1: only test images)
    try:
        ds = dataset_cls(data_root=data_root, split='test', patch_size=None,
                         augment=False, skip_missing=True)
    except Exception as e:
        print(f'  SKIP {dataset_name}/{severity}: cannot load dataset: {e}')
        return []

    test_ids = ds.get_test_ids()
    if not test_ids:
        print(f'  SKIP {dataset_name}/{severity}: no test IDs (data not present)')
        return []

    manifest_entries = []

    for sid in test_ids:
        npz_name = f'{dataset_name}_{severity}_id{sid}_seed{base_seed}.npz'
        npz_path = cache_dir / npz_name

        if npz_path.exists() and not force_recompute:
            print(f'  CACHE HIT: {npz_name}')
            manifest_entries.append({
                'dataset': dataset_name,
                'severity': severity,
                'image_id': str(sid),
                'seed': seed,
                'npz': str(npz_path),
                'status': 'cached',
            })
            continue

        # Load GT (test split only — never train/val)
        try:
            gt = ds._load_gt(sid)  # (H, W) uint8 {0,1}
        except Exception as e:
            print(f'  SKIP {dataset_name}/{severity}/{sid}: cannot load GT: {e}')
            continue

        H, W = gt.shape

        # Run apply_breaks with frozen seed
        t0 = time.time()
        result = apply_breaks(
            gt_mask=gt,
            gap_size=params['size_max'],
            nb_deco=params['nb_deco'],
            seed=seed,
        )
        elapsed = time.time() - t0

        # Serialise GapRecord list to JSON
        gap_records_json = json.dumps([asdict(g) for g in result.gaps]).encode('utf-8')

        # Save NPZ
        np.savez_compressed(
            str(npz_path),
            mask_broken        = result.mask_broken,
            vessel_segment_map = result.vessel_segment_map,
            gap_records_json   = np.frombuffer(gap_records_json, dtype=np.uint8),
            image_id           = np.array([str(sid)]),
            dataset            = np.array([dataset_name]),
            severity           = np.array([severity]),
            seed_used          = np.array([seed]),
            original_shape     = np.array([H, W]),
        )

        n_gaps = len(result.gaps)
        print(f'  DONE {npz_name}: {n_gaps} gaps, {elapsed:.1f}s')

        manifest_entries.append({
            'dataset':  dataset_name,
            'severity': severity,
            'image_id': str(sid),
            'seed':     seed,
            'npz':      str(npz_path),
            'n_gaps':   n_gaps,
            'shape':    [H, W],
            'status':   'computed',
        })

    return manifest_entries


# --------------------------------------------------------------------------- #
#  Load helper (used by evaluators)
# --------------------------------------------------------------------------- #

def load_benchmark_sample(npz_path: str):
    """
    Load a precomputed benchmark sample from NPZ.

    Returns dict with:
      mask_broken        — (H,W) uint8
      vessel_segment_map — (H,W) int32
      gaps               — List[dict] (GapRecord as dict)
      image_id           — str
      dataset            — str
      severity           — str
      seed_used          — int
      original_shape     — (H, W) tuple
    """
    data = np.load(npz_path, allow_pickle=False)
    gap_bytes = data['gap_records_json'].tobytes()
    gaps = json.loads(gap_bytes.decode('utf-8'))
    return {
        'mask_broken':        data['mask_broken'],
        'vessel_segment_map': data['vessel_segment_map'],
        'gaps':               gaps,
        'image_id':           str(data['image_id'][0]),
        'dataset':            str(data['dataset'][0]),
        'severity':           str(data['severity'][0]),
        'seed_used':          int(data['seed_used'][0]),
        'original_shape':     tuple(data['original_shape'].tolist()),
    }


# --------------------------------------------------------------------------- #
#  Main
# --------------------------------------------------------------------------- #

def main():
    parser = argparse.ArgumentParser(description='Precompute frozen benchmark break masks')
    parser.add_argument('--data_root_base', type=str,
                        default='D:/YJ-Agent/data/vessel',
                        help='Base dir containing DRIVE/ CHASE/ STARE/ HRF/ FIVES/')
    parser.add_argument('--cache_dir', type=str,
                        default='D:/YJ-Agent/data/benchmark_cache',
                        help='Output directory for .npz files')
    parser.add_argument('--dataset', type=str, default='all',
                        choices=['drive', 'chase', 'stare', 'hrf', 'fives', 'all'])
    parser.add_argument('--severity', type=str, default='all',
                        choices=list(SEVERITY_GRID.keys()) + ['all'])
    parser.add_argument('--base_seed', type=int, default=BASE_SEED)
    parser.add_argument('--force', action='store_true',
                        help='Recompute even if NPZ cache already exists')
    args = parser.parse_args()

    base_root  = Path(args.data_root_base)
    cache_dir  = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    registry = _build_registry(base_root)

    datasets_to_run = list(registry.keys()) if args.dataset == 'all' else [args.dataset]
    severities_to_run = list(SEVERITY_GRID.keys()) if args.severity == 'all' else [args.severity]

    all_manifest = []

    for ds_name in datasets_to_run:
        cls, root = registry[ds_name]
        for severity in severities_to_run:
            print(f'\n[{ds_name.upper()} / {severity}]')
            entries = precompute_one(
                dataset_name   = ds_name,
                dataset_cls    = cls,
                data_root      = root,
                severity       = severity,
                cache_dir      = cache_dir,
                base_seed      = args.base_seed,
                force_recompute= args.force,
            )
            all_manifest.extend(entries)

    # Write manifest
    manifest_path = cache_dir / 'manifest.json'
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(all_manifest, f, indent=2)

    n_computed = sum(1 for e in all_manifest if e.get('status') == 'computed')
    n_cached   = sum(1 for e in all_manifest if e.get('status') == 'cached')
    print(f'\nDone. {n_computed} computed, {n_cached} cache hits. Manifest: {manifest_path}')


if __name__ == '__main__':
    main()
