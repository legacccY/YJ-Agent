"""
frozen_breaks.py — Held-out breakpoint freezing for fair three-arm comparison (M2b).

Problem: if each evaluation call re-samples random breaks with a new seed, then
A0'/A1'/A2 across different training seeds see different per-image break patterns,
making paired statistical tests (Wilcoxon sign-rank on per-image deltas) invalid.

Solution: for each (img_id, dataset) pair, pre-generate ONE canonical break_result
using a deterministic seed = hash(20260621 + img_id), store as .npz/.pkl, then
return the SAME break_result to ALL arms and ALL training seeds at eval time.

This guarantees:
  - Per-image pairing is valid (same gaps seen by all arms).
  - Held-out: the frozen breaks are NOT generated from the training distribution
    (seed depends only on img_id, not on any model or training seed).
  - Reproducible: same img_id always gives same break_result on any machine.
  - Canonical storage: .npz format (same as precompute_benchmark.py).

Usage::

    from benchmark.frozen_breaks import get_frozen_breaks, precompute_frozen_breaks

    # Pre-generate (run once, store to disk):
    precompute_frozen_breaks(dataset_items, cache_dir='outputs/frozen_breaks/')

    # Load at eval time:
    br = get_frozen_breaks(cache_dir='outputs/frozen_breaks/', img_id='01')

API:
    get_frozen_breaks(cache_dir, img_id, dataset='', gap_size=8, nb_deco=50) -> BreakResult
    precompute_frozen_breaks(items, cache_dir, ...) -> None

Deterministic seed formula:
    seed = (20260621 + abs(hash(str(img_id)))) % (2**31 - 1)

This is collision-resistant for normal image-ID ranges (int or str up to ~1M images).
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import numpy as np

from .synth_breaks import BreakResult, GapRecord, apply_breaks


# ---------------------------------------------------------------------------
#  Deterministic seed formula (stable across Python versions via hashlib)
# ---------------------------------------------------------------------------

_SEED_BASE = 20260621


def _img_id_to_seed(img_id: Union[str, int]) -> int:
    """
    Convert img_id to a deterministic seed in [0, 2^31-1).

    Uses MD5 hex digest for cross-Python-version stability
    (Python's built-in hash() is salted per-process since Python 3.3).

    Seed = (20260621 + int(md5(str(img_id))[:8], 16)) % (2^31 - 1)
    """
    h = hashlib.md5(str(img_id).encode('utf-8')).hexdigest()
    offset = int(h[:8], 16)   # 32-bit integer from first 8 hex chars
    return (_SEED_BASE + offset) % (2**31 - 1)


# ---------------------------------------------------------------------------
#  Canonical NPZ path for a given img_id
# ---------------------------------------------------------------------------

def _npz_path(cache_dir: Path, img_id: Union[str, int], dataset: str = '') -> Path:
    """
    Canonical filename: frozen_<dataset>_<img_id>.npz
    Sanitise img_id (strip slashes / spaces for filesystem safety).
    """
    safe_id = str(img_id).replace('/', '_').replace('\\', '_').replace(' ', '_')
    prefix = f"{dataset}_" if dataset else ''
    return cache_dir / f"frozen_{prefix}{safe_id}.npz"


# ---------------------------------------------------------------------------
#  Serialise / deserialise BreakResult to/from NPZ
# ---------------------------------------------------------------------------

def _save_break_result(path: Path, br: BreakResult) -> None:
    """Save a BreakResult to a .npz file (deterministic storage)."""
    gap_records_json = json.dumps([asdict(g) for g in br.gaps]).encode('utf-8')
    np.savez_compressed(
        str(path),
        mask_broken        = br.mask_broken,
        vessel_segment_map = br.vessel_segment_map,
        gap_records_json   = np.frombuffer(gap_records_json, dtype=np.uint8),
    )


def _load_break_result(path: Path) -> BreakResult:
    """Load a BreakResult from a .npz file saved by _save_break_result."""
    data = np.load(str(path), allow_pickle=False)
    mask_broken        = data['mask_broken']
    vessel_segment_map = data['vessel_segment_map']
    gap_records_bytes  = data['gap_records_json'].tobytes()
    gap_records_list   = json.loads(gap_records_bytes.decode('utf-8'))
    # JSON deserialises tuples as lists; restore Tuple[int,int] for center_yx.
    gaps = []
    for d in gap_records_list:
        if isinstance(d.get('center_yx'), list):
            d['center_yx'] = tuple(d['center_yx'])
        gaps.append(GapRecord(**d))
    return BreakResult(
        mask_broken        = mask_broken,
        gaps               = gaps,
        vessel_segment_map = vessel_segment_map,
    )


# ---------------------------------------------------------------------------
#  Public API: get_frozen_breaks
# ---------------------------------------------------------------------------

def get_frozen_breaks(
    cache_dir: Union[str, Path],
    img_id: Union[str, int],
    gt_mask: Optional[np.ndarray] = None,
    dataset: str = '',
    gap_size: int = 8,
    nb_deco: int = 50,
    regenerate: bool = False,
) -> Optional[BreakResult]:
    """
    Return the canonical held-out BreakResult for (img_id, dataset).

    Behaviour:
      1. Compute deterministic seed from img_id.
      2. If cached NPZ exists and regenerate=False → load and return.
      3. If not cached and gt_mask is provided → generate, save, return.
      4. If not cached and gt_mask is None → return None (caller must handle).

    Args:
        cache_dir:   Directory for cached .npz files.
        img_id:      Image identifier (str or int; used for seed + filename).
        gt_mask:     (H, W) uint8 GT vessel mask.  Required if NPZ not cached.
        dataset:     Dataset name (used in filename to avoid collisions across datasets).
        gap_size:    size_max for apply_breaks (default 8, aligned with creatis).
        nb_deco:     nb_deco for apply_breaks (default 50).
        regenerate:  Force re-generation even if cached file exists.

    Returns:
        BreakResult or None (if cache miss and gt_mask not provided).
    """
    cache_dir = Path(cache_dir)
    npz = _npz_path(cache_dir, img_id, dataset)

    if npz.exists() and not regenerate:
        return _load_break_result(npz)

    if gt_mask is None:
        return None

    # Generate with deterministic seed
    seed = _img_id_to_seed(img_id)
    try:
        br = apply_breaks(gt_mask, gap_size=gap_size, nb_deco=nb_deco, seed=seed)
    except Exception:
        # Degenerate mask (all-zero, no vessel pixels) — return empty BreakResult
        empty = BreakResult(
            mask_broken        = gt_mask.copy(),
            gaps               = [],
            vessel_segment_map = np.zeros_like(gt_mask, dtype=np.int32),
        )
        return empty

    # Cache to disk
    cache_dir.mkdir(parents=True, exist_ok=True)
    _save_break_result(npz, br)
    return br


# ---------------------------------------------------------------------------
#  Convenience: precompute frozen breaks for a dataset split
# ---------------------------------------------------------------------------

def precompute_frozen_breaks(
    items: List[Dict[str, Any]],
    cache_dir: Union[str, Path],
    dataset: str = '',
    gap_size: int = 8,
    nb_deco: int = 50,
    overwrite: bool = False,
) -> Dict[Union[str, int], bool]:
    """
    Pre-generate and cache frozen break_results for a list of dataset items.

    Items schema (same as _load_fullimg_dispatch output):
      {'img_id': str|int, 'gt': (H,W) np.uint8, ...}

    Args:
        items:      list of sample dicts (must contain 'img_id' and 'gt').
        cache_dir:  directory to store .npz files.
        dataset:    dataset name prefix.
        gap_size:   size_max for apply_breaks.
        nb_deco:    nb_deco for apply_breaks.
        overwrite:  if True, regenerate even if NPZ exists.

    Returns:
        dict: img_id → True (success) or False (error/degenerate)
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    results: Dict[Union[str, int], bool] = {}

    for sample in items:
        img_id = sample['img_id']
        gt     = sample['gt']
        br = get_frozen_breaks(
            cache_dir   = cache_dir,
            img_id      = img_id,
            gt_mask     = gt,
            dataset     = dataset,
            gap_size    = gap_size,
            nb_deco     = nb_deco,
            regenerate  = overwrite,
        )
        results[img_id] = (br is not None and len(br.gaps) > 0)

    n_ok = sum(1 for v in results.values() if v)
    print(f"[frozen_breaks] precomputed {n_ok}/{len(items)} valid break_results → {cache_dir}")
    return results
