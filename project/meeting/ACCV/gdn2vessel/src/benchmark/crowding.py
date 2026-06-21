"""
crowding.py — State-crowding subgroup budget for gdn2vessel Claim2 A-v2 (M-B).

Purpose:
  Compute per-gap state-crowding k(i) and dataset k_thresh values BEFORE any
  training run.  k is derived exclusively from input-derived quantities:
  the benchmark NPZ's vessel_segment_map (used only for evaluation difficulty
  stratification, never fed to the model or back into training).

  Preregistered design (ACCEPTANCE_CRITERIA.md 命门方向 A-v2):
    k(i)     = number of DISTINCT vessel segment IDs (left+right) among all
               gaps whose centre falls within radius R_win of gap i's centre.
    R_win    = bottleneck receptive field radius, derived from architecture
               constants only (input-derived, no GT result used).
    k_thresh = median of {k(i)} across all gaps in a dataset split.
               Mean and 60th-percentile also reported for robustness.

R_win derivation (architecture constants, patch_size=512):
  UNetGDN2 encoder: 4 × (DoubleConv + MaxPool2d(2,2))
  → bottleneck spatial: 512 / 16 = 32 pixels per bottleneck token.
  One bottleneck token covers 16×16 input pixels (one-to-one stride).
  GDN-2 / LinearAttn processes the full bottleneck sequence as 1D tokens
  (raster order); the state S_t is of dimension d_head × d_head shared across
  ALL tokens in one pass.  Key collision arises when many distinct vessel
  identities are presented to the same state within one local neighbourhood.
  We define the "local neighbourhood" as the spatial region corresponding to
  the bottleneck resolution (32×32 for a 512 crop), so:
    R_win  = bottleneck_stride × ceil(bottleneck_H / 2)
           = 16 × ceil(32 / 2)
           = 16 × 16
           = 256 px   (in input image pixel coordinates)
  This is deliberately generous — it captures the full half-diameter of the
  bottleneck field, ensuring high-crowding regions are those where many segment
  identities compete within one "memory slot" sweep.
  Formula (parametric for flexibility):
    bottleneck_stride = patch_size // bottleneck_H  (= 512 // 32 = 16)
    R_win = bottleneck_stride * (bottleneck_H // 2)  (= 16 * 16 = 256 px)

  Architecture constants (do NOT change without re-running this script):
    PATCH_SIZE      = 512
    BOTTLENECK_H    = 32    (= PATCH_SIZE / 16, four 2× downsamples)
    BOTTLENECK_STRIDE = 16  (= PATCH_SIZE / BOTTLENECK_H)
    R_WIN           = 256   (= BOTTLENECK_STRIDE × (BOTTLENECK_H // 2))

k辖域声明 (ACCEPTANCE R5 / A-v2 skeptic 🟠-1):
  k uses GT vessel_segment_map for difficulty stratification ONLY.
  Three-arm shared partition: same k_thresh applied to A2, A1', A0' equally.
  k never flows into any arm's training or forward pass.
  Robustness option: Frangi-peak density / skeleton-branching density as
  input-derived proxy — see compute_k_per_gap docstring.

Red lines:
  - No scipy.stats (OMP #15 on Windows+PyTorch)
  - k must be computed from benchmark NPZ BEFORE seeing any reid results
  - k_thresh from manifest, not inlined/hardcoded per run
  - R_win is architecture-constant, not tuned to maximise A2>A1'

CLI:
  python src/benchmark/crowding.py --benchmark_dir <dir> [--dataset chase]
  Writes k_thresh manifest: <dir>/crowding_manifest.json

  Or import and call:
    from benchmark.crowding import compute_k_thresh_for_dataset, load_k_manifest
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

# ─────────────────────────────────────────────────────────────────────────────
# Architecture constants (input-derived, not GT-derived)
# Do NOT change without re-running precomputed manifests.
# ─────────────────────────────────────────────────────────────────────────────
PATCH_SIZE       = 512   # training / eval tile size
BOTTLENECK_H     = 32    # = PATCH_SIZE / 16 (four 2× downsamples in UNetGDN2)
BOTTLENECK_STRIDE = PATCH_SIZE // BOTTLENECK_H   # = 16 px per bottleneck token
R_WIN            = BOTTLENECK_STRIDE * (BOTTLENECK_H // 2)   # = 256 px
# R_WIN formula: bottleneck_stride × half_bottleneck_H
# = 16 × 16 = 256 input pixels.
# Rationale: one GDN-2 state sweep covers the full bottleneck extent;
#   crowding risk is highest when k distinct segment IDs appear within
#   this radius.  Using half-bottleneck as radius is a conservative estimate
#   (full-bottleneck diameter would double R_WIN).


# ─────────────────────────────────────────────────────────────────────────────
# Core computation: k(i) per gap
# ─────────────────────────────────────────────────────────────────────────────

def compute_k_per_gap(
    gaps: List[dict],
    R_win: float = R_WIN,
) -> Dict[int, int]:
    """
    For each gap i, compute k(i) = number of DISTINCT vessel segment IDs
    (union of segment_id_left and segment_id_right) among ALL gaps j whose
    centre (center_yx) falls within Euclidean distance R_win of gap i's centre.

    This includes gap i itself in its own window (so k(i) ≥ 1 if the gap
    has a valid segment ID, k(i) = 0 only if all segment IDs are -1/invalid).

    Args:
        gaps:   list of gap dicts (or GapRecord-like objects) with attributes:
                  center_yx       — (y, x) tuple/list in image pixel coords
                  segment_id_left — int (vessel segment ID at left endpoint)
                  segment_id_right— int (vessel segment ID at right endpoint)
                  Gaps with segment_id_left == segment_id_right == -1 are
                  considered "invalid" and contribute 0 distinct IDs.
        R_win:  neighbourhood radius in input image pixels.
                Default = architecture-constant R_WIN = 256 px.

    Returns:
        Dict mapping gap index (0-based, matching position in `gaps`) → k value.

    Notes:
        - Purely numpy, no scipy.  OMP-safe.
        - For robustness audit: an input-derived proxy (Frangi peak count within
          R_win) can replace this — the correlation between GT-k and Frangi-k
          should be high in dense vessel regions (planned robustness check).
    """
    n = len(gaps)
    if n == 0:
        return {}

    # Extract centre coordinates
    def _cy(g):
        cy = g['center_yx'] if isinstance(g, dict) else g.center_yx
        return float(cy[0])

    def _cx(g):
        cx = g['center_yx'] if isinstance(g, dict) else g.center_yx
        return float(cx[1])

    def _sid_left(g):
        return int(g['segment_id_left'] if isinstance(g, dict) else g.segment_id_left)

    def _sid_right(g):
        return int(g['segment_id_right'] if isinstance(g, dict) else g.segment_id_right)

    centres_y = np.array([_cy(g) for g in gaps], dtype=np.float64)
    centres_x = np.array([_cx(g) for g in gaps], dtype=np.float64)
    sids_left  = np.array([_sid_left(g)  for g in gaps], dtype=np.int64)
    sids_right = np.array([_sid_right(g) for g in gaps], dtype=np.int64)

    R2 = R_win ** 2
    k_dict: Dict[int, int] = {}

    for i in range(n):
        dy = centres_y - centres_y[i]
        dx = centres_x - centres_x[i]
        dist2 = dy * dy + dx * dx
        in_window = dist2 <= R2   # includes gap i itself

        # Collect all distinct valid segment IDs within window
        seg_ids: set = set()
        for j in np.where(in_window)[0]:
            sl = int(sids_left[j])
            sr = int(sids_right[j])
            if sl != -1:
                seg_ids.add(sl)
            if sr != -1:
                seg_ids.add(sr)

        k_dict[i] = len(seg_ids)

    return k_dict


def compute_k_thresh(all_k_values: List[int]) -> Dict[str, float]:
    """
    Compute k_thresh statistics from a list of k values (one per gap).

    Returns dict with:
      'median' — median k (primary k_thresh per ACCEPTANCE preregistration)
      'mean'   — mean k
      'p60'    — 60th percentile k (robustness check; direction must agree with median)

    All three must be reported; Claim2 承重门 uses 'median'.
    No scipy.  Hand-computed with numpy.
    """
    if not all_k_values:
        return {'median': float('nan'), 'mean': float('nan'), 'p60': float('nan'), 'n': 0}
    arr = np.array(all_k_values, dtype=np.float64)
    return {
        'median': float(np.median(arr)),
        'mean':   float(np.mean(arr)),
        'p60':    float(np.percentile(arr, 60)),
        'n':      len(all_k_values),
    }


# ─────────────────────────────────────────────────────────────────────────────
# High-level: compute k_thresh for one dataset from benchmark NPZs
# ─────────────────────────────────────────────────────────────────────────────

def compute_k_thresh_for_dataset(
    npz_paths: List[str],
    R_win: float = R_WIN,
) -> Dict[str, object]:
    """
    Load a list of benchmark NPZ files (all for one dataset), aggregate all
    gap k values across images, and compute k_thresh statistics.

    Returns dict:
      'k_thresh':     {'median', 'mean', 'p60', 'n'}
      'n_images':     number of NPZ files processed
      'n_gaps_total': total gap count across all images
      'R_win':        R_win value used
      'n_high':       gaps with k >= k_thresh['median']  (for ≥4 check)
      'n_low':        gaps with k <  k_thresh['median']
      'k_per_image':  list of per-image mean k (for debugging)
    """
    from datasets.precompute_benchmark import load_benchmark_sample
    from benchmark.synth_breaks import GapRecord

    all_k: List[int] = []
    k_per_image: List[float] = []
    n_images = 0
    errors = 0

    for npz_path in npz_paths:
        try:
            sample = load_benchmark_sample(npz_path)
            gaps_raw = sample['gaps']
            gaps = [GapRecord(**{
                'gap_id':           g['gap_id'],
                'center_yx':        tuple(g['center_yx']),
                'radius':           g['radius'],
                'gap_size':         g['gap_size'],
                'sigma':            g['sigma'],
                'segment_id_left':  g['segment_id_left'],
                'segment_id_right': g['segment_id_right'],
            }) for g in gaps_raw]

            k_dict = compute_k_per_gap(gaps, R_win=R_win)
            vals   = list(k_dict.values())
            all_k.extend(vals)
            k_per_image.append(float(np.mean(vals)) if vals else float('nan'))
            n_images += 1
        except Exception as exc:
            print(f'[crowding] SKIP {Path(npz_path).name}: {exc}')
            errors += 1

    thresh = compute_k_thresh(all_k)
    k_med  = thresh['median']

    n_high = int(sum(1 for k in all_k if k >= k_med)) if not np.isnan(k_med) else 0
    n_low  = int(sum(1 for k in all_k if k <  k_med)) if not np.isnan(k_med) else 0

    if errors:
        print(f'[crowding] {errors} NPZ(s) skipped.')

    return {
        'k_thresh':     thresh,
        'n_images':     n_images,
        'n_gaps_total': len(all_k),
        'R_win':        R_win,
        'n_high':       n_high,
        'n_low':        n_low,
        'k_per_image':  k_per_image,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Manifest: write / load k_thresh per dataset
# ─────────────────────────────────────────────────────────────────────────────

MANIFEST_FILENAME = 'crowding_manifest.json'


def write_k_manifest(
    benchmark_dir: str,
    datasets: Optional[List[str]] = None,
    severity: Optional[str] = None,
    R_win: float = R_WIN,
) -> Dict:
    """
    Load benchmark NPZs for each dataset (optionally filtered by severity),
    compute k_thresh per dataset, write manifest JSON to benchmark_dir.

    Manifest schema:
      {
        "R_win": 256,
        "datasets": {
          "chase": { "k_thresh": {...}, "n_images": 8, ... },
          ...
        }
      }
    """
    import os

    bench_dir = Path(benchmark_dir)
    manifest_path = bench_dir / 'manifest.json'

    if not manifest_path.exists():
        raise FileNotFoundError(
            f'benchmark manifest.json not found at {manifest_path}. '
            f'Run precompute_benchmark.py first.'
        )

    with open(manifest_path, encoding='utf-8') as f:
        entries = json.load(f)   # list of dicts with 'path', 'dataset', 'severity', ...

    # Filter entries
    if datasets is None:
        datasets = sorted(set(e.get('dataset', '') for e in entries))
    if severity is not None:
        entries = [e for e in entries if e.get('severity') == severity]

    result: Dict = {'R_win': R_win, 'datasets': {}}

    for ds in datasets:
        ds_entries = [e for e in entries if e.get('dataset', '').lower() == ds.lower()]
        npz_paths  = [str(bench_dir / e['path']) for e in ds_entries
                      if (bench_dir / e['path']).exists()]
        if not npz_paths:
            print(f'[crowding] WARNING: no NPZs found for dataset={ds}')
            result['datasets'][ds] = {
                'k_thresh': {'median': float('nan'), 'mean': float('nan'),
                             'p60': float('nan'), 'n': 0},
                'n_images': 0,
                'n_gaps_total': 0,
                'R_win': R_win,
                'n_high': 0,
                'n_low': 0,
            }
            continue

        print(f'[crowding] computing k for dataset={ds}  n_npz={len(npz_paths)}...')
        ds_result = compute_k_thresh_for_dataset(npz_paths, R_win=R_win)
        result['datasets'][ds] = {k: v for k, v in ds_result.items()
                                   if k != 'k_per_image'}   # don't bloat manifest
        thresh = ds_result['k_thresh']
        print(f'  k_thresh: median={thresh["median"]:.1f}  '
              f'mean={thresh["mean"]:.1f}  p60={thresh["p60"]:.1f}  '
              f'n_gaps={thresh["n"]}  n_high={ds_result["n_high"]}  '
              f'n_low={ds_result["n_low"]}')

    out_path = bench_dir / MANIFEST_FILENAME
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'[crowding] manifest written → {out_path}')
    return result


def load_k_manifest(benchmark_dir: str) -> Dict:
    """
    Load crowding_manifest.json from benchmark_dir.
    Returns the manifest dict (keyed by 'R_win' and 'datasets').
    Raises FileNotFoundError if manifest does not exist.
    """
    path = Path(benchmark_dir) / MANIFEST_FILENAME
    if not path.exists():
        raise FileNotFoundError(
            f'crowding_manifest.json not found at {path}. '
            f'Run: python src/benchmark/crowding.py --benchmark_dir {benchmark_dir}'
        )
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def get_k_thresh_for_dataset(manifest: Dict, dataset: str) -> float:
    """
    Extract the preregistered k_thresh (median) for a dataset from a loaded manifest.
    Returns float('nan') if dataset not found or k_thresh is nan.
    """
    ds_info = manifest.get('datasets', {}).get(dataset)
    if ds_info is None:
        ds_lower = dataset.lower()
        for k, v in manifest.get('datasets', {}).items():
            if k.lower() == ds_lower:
                ds_info = v
                break
    if ds_info is None:
        return float('nan')
    return float(ds_info.get('k_thresh', {}).get('median', float('nan')))


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _cli():
    import argparse
    parser = argparse.ArgumentParser(
        description=(
            'gdn2vessel A-v2 M-B state-crowding budget tool.\n'
            'Computes per-gap k values and k_thresh (median/mean/p60) for each\n'
            'dataset from benchmark NPZs, writes crowding_manifest.json.\n'
            'Run BEFORE training — k is model-independent, one-off computation.\n'
            f'R_win architecture constant = {R_WIN} px (see module docstring).'
        )
    )
    parser.add_argument('--benchmark_dir', required=True,
                        help='Directory containing benchmark NPZs + manifest.json '
                             '(output of precompute_benchmark.py).')
    parser.add_argument('--datasets', nargs='+', default=None,
                        help='Dataset name(s) to process (default: all in manifest).')
    parser.add_argument('--severity', default=None,
                        help='Filter NPZs by severity (e.g. Medium; default: all).')
    parser.add_argument('--R_win', type=float, default=float(R_WIN),
                        help=f'Neighbourhood radius in px (default={R_WIN}, architecture constant).')
    args = parser.parse_args()

    result = write_k_manifest(
        benchmark_dir=args.benchmark_dir,
        datasets=args.datasets,
        severity=args.severity,
        R_win=args.R_win,
    )
    print('[crowding] Done.')
    for ds, info in result['datasets'].items():
        thresh = info['k_thresh']
        print(f'  {ds}: median={thresh["median"]:.1f}  mean={thresh["mean"]:.1f}  '
              f'p60={thresh["p60"]:.1f}  n_gaps={thresh["n"]}  '
              f'n_high={info["n_high"]}  n_low={info["n_low"]}')


if __name__ == '__main__':
    import sys
    _src_dir = str(Path(__file__).parent.parent)
    if _src_dir not in sys.path:
        sys.path.insert(0, _src_dir)
    _cli()
