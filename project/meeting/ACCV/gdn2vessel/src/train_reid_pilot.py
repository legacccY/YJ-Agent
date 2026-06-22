"""
train_reid_pilot.py — End-to-end re-ID command pilot harness for gdn2vessel Claim 2.

Validates "spatial re-ID is attributable to memory" (致命-2 判据, ACCEPTANCE P4).

Two core ablation arms (driven by --reid_feat_source):
  A2  (memory) -- headline: re-ID comes from GDN-2 associative memory features.
  A0' (cnn)    -- zero-hypothesis: re-ID using plain CNN bottleneck features
                  (same head, no memory).  Tests that re-ID ≠ ordinary features.

Additional ablation flags:
  --no_detach_memory      → A3 arm: gradient flows back into memory (ablation-only).
  --reid_breakpoint_source {pred_skeleton,gt_skeleton} → A4 arm.

Evaluation (held-out benchmark NPZ batch, frozen seed=42):
  • re-ID rate   = correct same-root / N_gaps
  • ε_β0         = |β0_pred − β0_gt| / β0_gt
  • SR           = gaps closed / N_gaps
  • partial_corr(memory_on, reid_rate | ε_β0) — pure numpy, no scipy.stats
    (禁 scipy.stats — OMP Error #15 on Windows+PyTorch)

  Benchmark loading — two modes (both produce same per-image CSV):
    --benchmark_npz <file>       : single-file backward-compatible mode (smoke/debug)
    --benchmark_dir <cache_dir> --dataset <ds> --severity <sev>
                                 : multi-image mode via manifest.json (production).
                                   Filters manifest by dataset+severity, loads all
                                   matching NPZs → per-image rows in reid_results.csv.

Results written to state.json (real-time) and reid_results.csv.
  reid_results.csv columns:
    epoch, image_id, severity, dataset, reid_rate, reid_rate_head, reid_idf1,
    epsilon_beta0, success_rate, n_gaps,
    reid_rate_head_high, reid_rate_head_low,  (A-v2 crowding cols)
    seed, cldice, betti_err_total,            (gate-B topology cols)
    arm
  reid_rate_head / reid_idf1: re-ID head logit-driven metrics (NaN if head not active
    or no gaps with same-root partner visible in eval tile).
  seed: training seed (args.seed); required by gate_frangi_verdict.py for
    (image_id, seed) pairing between gate-on and gate-off arms.
  cldice: binary-mask clDice (arXiv 2003.07311, eval version via skimage.skeletonize).
  betti_err_total: |β0_err| + |β1_err| topology error (cross-validation indicator).

Partial-correlation tool (standalone callable):
  python src/train_reid_pilot.py --partial_corr_only \\
      --state_a outputs/reid_a2/state.json \\
      --state_b outputs/reid_a0/state.json

Red-line guard (greppable assertions):
  • R5: no GT topology in memory / Frangi — enforced by UNetGDN2 signature (no gt param).
  • R5: detach isolation enforced by reid_detach_memory_train=True (default).
  • Red-line 1: benchmark test set NEVER merged with training samples.
    (benchmark NPZs are pre-frozen from precompute_benchmark.py, test-only.)

Windows compatibility:
  • multiprocessing_context='spawn' for DataLoader (if num_workers > 0)
  • pin_memory=False
  • if __name__ == '__main__' guard at bottom (mandatory)
  • No scipy.stats import (OMP Error #15)
  • Partial-correlation computed as hand-written residual Pearson (pure numpy)

CLI usage:
  # A2 (memory arm, headline) — multi-image benchmark dir:
  python src/train_reid_pilot.py \\
      --reid_feat_source memory \\
      --data_root /data/DRIVE \\
      --benchmark_dir /data/benchmark_cache \\
      --dataset drive --severity Medium \\
      --output_dir outputs/reid_a2

  # A0' (CNN zero-hypothesis) — multi-image benchmark dir:
  python src/train_reid_pilot.py \\
      --reid_feat_source cnn \\
      --data_root /data/DRIVE \\
      --benchmark_dir /data/benchmark_cache \\
      --dataset drive --severity Medium \\
      --output_dir outputs/reid_a0

  # Backward-compatible single-file smoke mode:
  python src/train_reid_pilot.py \\
      --reid_feat_source memory \\
      --data_root /data/DRIVE \\
      --benchmark_npz /data/benchmark_cache/drive_Medium_id01_seed42.npz \\
      --output_dir outputs/reid_a2

  # Compute partial-corr after both arms done:
  python src/train_reid_pilot.py --partial_corr_only \\
      --state_a outputs/reid_a2/state.json \\
      --state_b outputs/reid_a0/state.json \\
      --csv_a outputs/reid_a2/reid_results.csv \\
      --csv_b outputs/reid_a0/reid_results.csv

  # CI smoke (2 steps, CPU, no data needed):
  python src/train_reid_pilot.py --smoke --data_root /data/DRIVE
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader

# --------------------------------------------------------------------------- #
#  sys.path: src/ must be importable
# --------------------------------------------------------------------------- #
_src_dir = Path(__file__).parent
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))


# --------------------------------------------------------------------------- #
#  Seg-loss helpers (identical to train_pilot.py, no drift)
# --------------------------------------------------------------------------- #

def _dice_loss(pred_prob: torch.Tensor, target: torch.Tensor,
               mask: torch.Tensor, eps: float = 1e-6) -> torch.Tensor:
    """Soft Dice loss computed only inside FOV mask."""
    pred_flat = (pred_prob * mask).reshape(pred_prob.shape[0], -1)
    tgt_flat  = (target * mask).reshape(target.shape[0], -1)
    intersection = (pred_flat * tgt_flat).sum(1)
    denom = pred_flat.sum(1) + tgt_flat.sum(1)
    dice = (2 * intersection + eps) / (denom + eps)
    return 1.0 - dice.mean()


def _bce_loss(logits: torch.Tensor, target: torch.Tensor,
              mask: torch.Tensor) -> torch.Tensor:
    """BCE computed only inside FOV mask."""
    bce = F.binary_cross_entropy_with_logits(logits, target, reduction='none')
    n_valid = mask.sum().clamp(min=1)
    return (bce * mask).sum() / n_valid


def seg_loss(logits: torch.Tensor, target: torch.Tensor,
             mask: torch.Tensor) -> torch.Tensor:
    """0.5 * BCE + 0.5 * Dice (same as train_pilot.py)."""
    prob = torch.sigmoid(logits)
    return 0.5 * _bce_loss(logits, target, mask) + 0.5 * _dice_loss(prob, target, mask)


# --------------------------------------------------------------------------- #
#  Dice metric (pure numpy, no scipy — OMP-safe)
# --------------------------------------------------------------------------- #

def dice_np(pred_bin: np.ndarray, target: np.ndarray,
            mask: np.ndarray, eps: float = 1e-6) -> float:
    p = pred_bin[mask > 0]
    t = target[mask > 0]
    intersection = (p * t).sum()
    denom = p.sum() + t.sum()
    return float((2 * intersection + eps) / (denom + eps))


# --------------------------------------------------------------------------- #
#  Partial correlation (pure numpy — FORBIDDEN to use scipy.stats, OMP red-line)
#
#  partial_corr(X, Y | Z):
#    Regress out Z from both X and Y via OLS, then Pearson on residuals.
#    Returns (r, bootstrap_ci_lower, bootstrap_ci_upper).
#    bootstrap: n_resample samples of size len(X).
# --------------------------------------------------------------------------- #

def _pearson_r(a: np.ndarray, b: np.ndarray) -> float:
    """Pearson r, pure numpy."""
    a = a - a.mean()
    b = b - b.mean()
    denom = (np.sqrt((a ** 2).sum()) * np.sqrt((b ** 2).sum()))
    if denom < 1e-12:
        return 0.0
    return float((a * b).sum() / denom)


def _residuals_after_ols(X: np.ndarray, Z: np.ndarray) -> np.ndarray:
    """
    Regress Z out of X using OLS (X = a + b*Z + residual).
    Returns residuals.  Pure numpy, no scipy.
    """
    Z_centered = Z - Z.mean()
    b_denom = (Z_centered ** 2).sum()
    if b_denom < 1e-12:
        return X - X.mean()
    b = (Z_centered * (X - X.mean())).sum() / b_denom
    a = X.mean() - b * Z.mean()
    return X - (a + b * Z)


def partial_corr_numpy(
    X: np.ndarray,
    Y: np.ndarray,
    Z: np.ndarray,
    n_resample: int = 1000,
    rng_seed: int = 42,
) -> Dict[str, float]:
    """
    partial_corr(X, Y | Z) — Pearson on OLS residuals after regressing out Z.

    Used for ACCEPTANCE P4 判据 2:
      X = memory_on indicator (1 for A2, 0 for A0')
      Y = reid_rate
      Z = epsilon_beta0

    Returns dict: {r, ci_lower, ci_upper, n}

    NOTE: scipy.stats is FORBIDDEN (OMP Error #15 on Windows+PyTorch).
    This implementation is pure numpy with bootstrap CI.

    Threshold (ACCEPTANCE P4, pre-registered 2026-06-20):
      PASS if r > 0.2 AND ci_lower > 0
      FAIL if r ≤ 0.2 OR ci_lower ≤ 0 → re-ID is only an ε_β0 side-effect
    """
    X = np.asarray(X, dtype=np.float64)
    Y = np.asarray(Y, dtype=np.float64)
    Z = np.asarray(Z, dtype=np.float64)
    assert len(X) == len(Y) == len(Z), "Arrays must have the same length"

    resid_X = _residuals_after_ols(X, Z)
    resid_Y = _residuals_after_ols(Y, Z)
    r = _pearson_r(resid_X, resid_Y)

    # Bootstrap CI (percentile)
    rng = np.random.RandomState(rng_seed)
    boot_rs = []
    n = len(X)
    for _ in range(n_resample):
        idx = rng.randint(0, n, size=n)
        rx = _residuals_after_ols(X[idx], Z[idx])
        ry = _residuals_after_ols(Y[idx], Z[idx])
        boot_rs.append(_pearson_r(rx, ry))
    boot_rs = np.array(boot_rs)
    ci_lo = float(np.percentile(boot_rs, 2.5))
    ci_hi = float(np.percentile(boot_rs, 97.5))

    return {
        'r': r,
        'ci_lower': ci_lo,
        'ci_upper': ci_hi,
        'n': n,
        # Pre-registered pass/fail (ACCEPTANCE P4)
        'PASS': (r > 0.2) and (ci_lo > 0),
    }


# --------------------------------------------------------------------------- #
#  Benchmark NPZ list resolver (multi-image production path)
# --------------------------------------------------------------------------- #

def load_benchmark_npz_list(
    benchmark_npz: Optional[str],
    benchmark_dir: Optional[str],
    dataset: Optional[str],
    severity: Optional[str],
) -> List[str]:
    """
    Resolve the list of benchmark NPZ paths to evaluate.

    Two modes:
      Single-file (backward-compat / smoke):
        benchmark_npz != None  → return [benchmark_npz]

      Multi-file (production — needs n≥20 images for meaningful partial-corr):
        benchmark_dir + dataset + severity → read manifest.json, filter entries,
        return all matching npz paths.

    Returns list of absolute path strings.  Never returns an empty list without
    printing a warning.
    """
    if benchmark_npz is not None:
        # Single-file mode: wrap in list for uniform downstream handling
        return [benchmark_npz]

    if benchmark_dir is None:
        return []

    manifest_path = Path(benchmark_dir) / 'manifest.json'
    if not manifest_path.exists():
        print(f'[benchmark] WARNING: manifest.json not found in {benchmark_dir}. '
              f'Run precompute_benchmark.py first.')
        return []

    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)

    # Filter by dataset and/or severity
    selected = []
    for entry in manifest:
        if dataset is not None and entry.get('dataset') != dataset:
            continue
        if severity is not None and entry.get('severity') != severity:
            continue
        npz = entry.get('npz', '')
        if npz and Path(npz).exists():
            selected.append(npz)
        else:
            print(f'[benchmark] WARNING: NPZ missing on disk: {npz}')

    if not selected:
        print(f'[benchmark] WARNING: No NPZ found for dataset={dataset} severity={severity} '
              f'in {manifest_path}. Check precompute_benchmark.py output.')

    return selected


# --------------------------------------------------------------------------- #
#  Benchmark-based re-ID evaluation (held-out NPZ batch, never training data)
# --------------------------------------------------------------------------- #

def _reid_head_forward_on_tile(
    model: nn.Module,
    device: torch.device,
    image: np.ndarray,
    gaps: list,
    tile_size: int = 512,
    gap_k: Optional[np.ndarray] = None,
    k_thresh: Optional[float] = None,
) -> Dict[str, float]:
    """
    Run re-ID head on a single 512×512 crop centred on the gaps' centroid.

    Design (mirrors evaluate.py:_compute_reid_head_metrics, adapted for tiled eval):
      - Full-res images (e.g. CHASE 960×999) cannot go through the model whole:
        bottleneck H/16 × W/16 would exceed max_seq_len=1024.
      - Solution: extract one 512×512 tile centred on the centroid of all gaps
        (clamped to image bounds). 512 → 32×32 = 1024 tokens (exactly at limit).
      - Only gaps whose centre falls inside the tile are evaluated; others are
        out-of-view for this tile and are excluded (their logits would be noise).
      - Breakpoint positions are expressed in dec_feat (H/4 = 128×128) coordinates
        relative to the tile.

    A-v2 M-B B-3: if gap_k and k_thresh are provided, also computes
    reid_rate_head_high / reid_rate_head_low (crowding-stratified subsets).
    gap_k must correspond to the *full* gap list (same index as `gaps`); the
    function handles subsetting to gaps_in_tile internally.

    Args:
        model:     UNetGDN2 (checked by caller for use_reid_head / reid_head).
        device:    torch.device
        image:     (H, W) float32 preprocessed image.
        gaps:      list of GapRecord (full-image coordinates).
        tile_size: side length of crop (default 512 to respect max_seq_len=1024).
        gap_k:     optional (len(gaps),) array of per-gap k values (crowding;
                   from benchmark.crowding.compute_k_per_gap). Aligned with `gaps`.
        k_thresh:  float — preregistered k_thresh from crowding manifest (median).

    Returns:
        dict with keys: reid_rate_head, reid_idf1
        (plus reid_rate_head_high, reid_rate_head_low, n_high, n_low, r_chance_high
         when gap_k and k_thresh are provided and not nan).

    Nan values returned when:
      - No gaps provided.
      - No gaps fall inside the selected tile.
      - model.reid_head is None / use_reid_head is False.
      - reid_ctx missing o_seq / dec_feat (A0' cnn arm with no attention).
    """
    from benchmark.metrics import reid_rate_head as _rrh

    _nan_dict: Dict[str, float] = {'reid_rate_head': float('nan'),
                                    'reid_idf1': float('nan')}

    if not gaps:
        return _nan_dict
    if not (hasattr(model, 'use_reid_head') and model.use_reid_head
            and hasattr(model, 'reid_head') and model.reid_head is not None):
        return _nan_dict

    H_img, W_img = image.shape

    # --- Compute tile bounds centred on gaps centroid ---
    cy_all = [g.center_yx[0] for g in gaps]
    cx_all = [g.center_yx[1] for g in gaps]
    cy_c = int(np.mean(cy_all))
    cx_c = int(np.mean(cx_all))

    half = tile_size // 2
    y0 = max(0, min(cy_c - half, H_img - tile_size))
    x0 = max(0, min(cx_c - half, W_img - tile_size))
    # If image is smaller than tile_size, use the whole image (pad below)
    y0 = max(0, y0)
    x0 = max(0, x0)
    y1 = min(H_img, y0 + tile_size)
    x1 = min(W_img, x0 + tile_size)

    # Crop + pad to exactly (tile_size, tile_size) if image is smaller
    crop = image[y0:y1, x0:x1]
    ch, cw = crop.shape
    if ch < tile_size or cw < tile_size:
        pad_img = np.zeros((tile_size, tile_size), dtype=np.float32)
        pad_img[:ch, :cw] = crop
        crop = pad_img

    # --- Filter gaps to those whose centre falls inside the tile ---
    # Also track original indices so gap_k can be subsetted accordingly.
    gaps_in_tile = []
    gap_orig_indices = []   # indices into the original `gaps` list
    local_cy = []
    local_cx = []
    for orig_idx, g in enumerate(gaps):
        gy, gx = g.center_yx
        if y0 <= gy < y1 and x0 <= gx < x1:
            gaps_in_tile.append(g)
            gap_orig_indices.append(orig_idx)
            local_cy.append(gy - y0)
            local_cx.append(gx - x0)

    if not gaps_in_tile:
        return _nan_dict

    K = len(gaps_in_tile)

    # --- Subset gap_k to tile gaps ---
    gap_k_tile: Optional[np.ndarray] = None
    if gap_k is not None and k_thresh is not None:
        gap_k_arr = np.asarray(gap_k, dtype=np.float64)
        if gap_k_arr.shape[0] == len(gaps):
            gap_k_tile = gap_k_arr[gap_orig_indices]  # (K,) subset

    # --- Forward with reid_ctx ---
    inp = torch.tensor(crop, dtype=torch.float32
                       ).unsqueeze(0).unsqueeze(0).to(device)   # (1,1,tile,tile)
    model.eval()
    with torch.no_grad():
        out = model(inp, return_reid_ctx=True)

    # model may return (logits, reid_ctx) or just logits
    if isinstance(out, tuple) and len(out) == 2:
        _, reid_ctx = out
    else:
        return _nan_dict

    o_seq = reid_ctx.get('o_seq')
    dec_feat = reid_ctx.get('dec_feat')
    memory_state = reid_ctx.get('memory_state')

    if o_seq is None or dec_feat is None:
        # A0' cnn arm: o_seq may be None (no memory). reid_rate_head = NaN.
        return _nan_dict

    H_dec = dec_feat.shape[-2]   # tile_size / 4 = 128 for 512-tile
    W_dec = dec_feat.shape[-1]

    # Build breakpoint_positions in dec_feat coordinate space
    # tile coords → dec_feat coords (proportional)
    positions = torch.zeros(1, K, 2, dtype=torch.float32, device=device)
    for idx in range(K):
        cy_dec = local_cy[idx] * H_dec / tile_size
        cx_dec = local_cx[idx] * W_dec / tile_size
        positions[0, idx, 0] = float(cy_dec)
        positions[0, idx, 1] = float(cx_dec)

    positions[..., 0].clamp_(0, H_dec - 1)
    positions[..., 1].clamp_(0, W_dec - 1)

    with torch.no_grad():
        reid_logits = model.reid_head(
            o_seq=o_seq,
            dec_feat=dec_feat,
            breakpoint_positions=positions,
            memory_state=memory_state,
        )   # (1, K, K)

    logits_np = reid_logits[0].detach().cpu().numpy().astype(np.float32)  # (K, K)

    # Pass gap_k_tile and k_thresh for crowding stratification (M-B B-3).
    result = _rrh(logits_np, gaps_in_tile,
                  gap_k=gap_k_tile,
                  k_thresh=k_thresh)
    return result


def _tiled_inference(
    model: nn.Module,
    device: torch.device,
    image: np.ndarray,
    tile_size: int = 512,
    overlap: int = 64,
) -> np.ndarray:
    """
    Sliding-window tiled inference to handle full-resolution images whose
    bottleneck sequence length exceeds GDN-2's max_seq_len=1024.

    A 512×512 tile → bottleneck 32×32 = 1024 tokens (exactly at limit).

    Args:
        image:      (H, W) float32 preprocessed image (green+CLAHE+norm).
        tile_size:  side length of each tile (default 512 to keep tokens≤1024).
        overlap:    overlap between adjacent tiles (pixels); overlap region is
                    averaged across contributing tiles.

    Returns:
        logit_map:  (H, W) float32 — averaged raw logits in original image space.

    Implementation:
        - Pad image to be divisible by stride = tile_size - overlap.
        - For each tile: model forward → logit tile.
        - Accumulate logits in sum_map; count in count_map; average at end.
        - Crop back to original (H, W).
    """
    H_orig, W_orig = image.shape
    stride = tile_size - overlap

    # Pad so we always have full tiles covering every pixel
    pad_h = (stride - (H_orig - overlap) % stride) % stride
    pad_w = (stride - (W_orig - overlap) % stride) % stride
    img_pad = np.pad(image, ((0, pad_h), (0, pad_w)), mode='reflect')
    H_pad, W_pad = img_pad.shape

    sum_map   = np.zeros((H_pad, W_pad), dtype=np.float64)
    count_map = np.zeros((H_pad, W_pad), dtype=np.float64)

    model.eval()
    with torch.no_grad():
        y0 = 0
        while y0 + tile_size <= H_pad:
            x0 = 0
            while x0 + tile_size <= W_pad:
                y1 = y0 + tile_size
                x1 = x0 + tile_size
                tile_np = img_pad[y0:y1, x0:x1]  # (tile_size, tile_size)
                inp = torch.tensor(tile_np, dtype=torch.float32
                                   ).unsqueeze(0).unsqueeze(0).to(device)
                logits_t = model(inp)              # (1, 1, tile_size, tile_size)
                logits_np = logits_t.squeeze(0).squeeze(0).cpu().numpy()
                sum_map[y0:y1, x0:x1]   += logits_np
                count_map[y0:y1, x0:x1] += 1.0
                x0 += stride
            y0 += stride

    # Average and crop to original size
    # count_map is guaranteed ≥1 everywhere we covered
    logit_map = (sum_map / np.maximum(count_map, 1.0)).astype(np.float32)
    return logit_map[:H_orig, :W_orig]


def _eval_single_npz(
    model: nn.Module,
    device: torch.device,
    npz_path: str,
    reid_feat_source: str,
    tile_size: int = 512,
    overlap: int = 64,
    gap_k: Optional[np.ndarray] = None,
    k_thresh: Optional[float] = None,
    seed: int = 42,
) -> Dict:
    """
    Run model on one benchmark NPZ.  Returns per-image metric dict.

    Bug-fix v2 (2026-06-20):
      BUG1 fixed: model input is now the preprocessed source image (field 'image'
           from NPZ, green+CLAHE+norm), matching training distribution.
           Previous code incorrectly fed mask_broken (binary disconnection mask),
           which is completely OOD input — making eval metrics invalid.
      BUG2 fixed: full-resolution images (e.g. CHASE 960×999) produce bottleneck
           sequences of 60×62=3720 >> max_seq_len=1024, causing AssertionError.
           Now uses 512×512 sliding-window tiled inference (_tiled_inference) with
           overlap averaging stitch.  512×512 → 32×32 = 1024 tokens (at limit).

    R5 guard: image is model input (input-derived).  break_result/gap_positions
    from NPZ are used only as the judge (to compute reid_rate/ε_β0/SR) — they
    never enter the model.

    RED LINE: npz_path must come from precompute_benchmark.py test-only split.
    """
    from benchmark.metrics import (
        epsilon_beta0,
        success_rate,
        reid_rate as compute_reid_rate,
        cldice_metric,
        betti_error,
    )
    from benchmark.synth_breaks import BreakResult, GapRecord
    from datasets.precompute_benchmark import load_benchmark_sample

    sample = load_benchmark_sample(npz_path)
    vessel_segment_map = sample['vessel_segment_map']               # (H, W) int32
    gaps_raw           = sample['gaps']                             # List[dict]
    image_id           = sample['image_id']
    ds_name            = sample['dataset']
    sev                = sample['severity']

    # BUG1 FIX: use preprocessed source image, not mask_broken
    image_f = sample.get('image') if sample.get('image') is not None else None
    if image_f is None:
        raise ValueError(
            f'NPZ {Path(npz_path).name} missing "image" field. '
            f'Re-run precompute_benchmark.py --force to regenerate with new schema.'
        )
    image_f = image_f.astype(np.float32)   # (H, W)

    gaps = [GapRecord(**{
        'gap_id':           g['gap_id'],
        'center_yx':        tuple(g['center_yx']),
        'radius':           g['radius'],
        'gap_size':         g['gap_size'],
        'sigma':            g['sigma'],
        'segment_id_left':  g['segment_id_left'],
        'segment_id_right': g['segment_id_right'],
    }) for g in gaps_raw]

    break_result = BreakResult(
        mask_broken=sample['mask_broken'],
        gaps=gaps,
        vessel_segment_map=vessel_segment_map,
    )

    # GT mask: vessel_segment_map > 0 ≡ original GT foreground
    gt_mask = (vessel_segment_map > 0).astype(np.uint8)

    # BUG2 FIX: tiled inference to avoid bottleneck sequence > max_seq_len=1024
    # 512×512 tile → 32×32 bottleneck = 1024 tokens (exactly at limit)
    logit_map = _tiled_inference(
        model, device, image_f,
        tile_size=tile_size,
        overlap=overlap,
    )
    pred_prob = 1.0 / (1.0 + np.exp(-logit_map))   # sigmoid, no torch needed
    pred_bin  = (pred_prob > 0.5).astype(np.uint8)

    rr  = compute_reid_rate(pred_bin, break_result)
    eps = epsilon_beta0(pred_bin, gt_mask)
    sr  = success_rate(pred_bin, break_result)

    # --- gate-B topology metrics: clDice + Betti (arXiv 2003.07311) ---
    # clDice: harmonic mean of topology precision & sensitivity via skeletonize.
    # betti_error: |β0_err| + |β1_err| (component + loop count errors).
    # Both use binary masks (eval version, not soft-skeleton training loss).
    cldice_val    = cldice_metric(pred_bin, gt_mask)
    betti_dict    = betti_error(pred_bin, gt_mask)
    betti_err_tot = betti_dict['betti_err_total']

    # --- M-B B-3: per-image gap_k computation (crowding, A-v2) ---
    # Compute k per gap from vessel_segment_map (for evaluation stratification only;
    # never flows into model forward or training).
    # If k_thresh is None/nan, reid_rate_head_high/low will not be computed.
    per_gap_k: Optional[np.ndarray] = None
    if k_thresh is not None and not (isinstance(k_thresh, float) and np.isnan(k_thresh)):
        try:
            from benchmark.crowding import compute_k_per_gap, R_WIN
            k_dict = compute_k_per_gap(gaps, R_win=R_WIN)
            per_gap_k = np.array([k_dict.get(i, 0) for i in range(len(gaps))],
                                  dtype=np.float64)
        except Exception as _ke:
            print(f'  [crowding] WARNING: k computation failed: {_ke}')
            per_gap_k = None

    # Re-ID head eval: run reid_head on a 512×512 crop centred on gaps centroid.
    # Returns dict with reid_rate_head, reid_idf1, and (when gap_k provided)
    # reid_rate_head_high, reid_rate_head_low, n_high, n_low, r_chance_high.
    # Returns NaN when: no gaps, model has no reid_head, or o_seq is None (A0' cnn).
    head_result = _reid_head_forward_on_tile(
        model, device, image_f, gaps,
        gap_k=per_gap_k if per_gap_k is not None else gap_k,
        k_thresh=k_thresh,
    )

    row: Dict = {
        'image_id':       image_id,
        'dataset':        ds_name,
        'severity':       sev,
        'reid_rate':      rr,
        'reid_rate_head': head_result.get('reid_rate_head', float('nan')),
        'reid_idf1':      head_result.get('reid_idf1',      float('nan')),
        'epsilon_beta0':  eps,
        'success_rate':   sr,
        'n_gaps':         len(gaps),
        # crowding-stratified (nan when gap_k/k_thresh not provided or A0' headless)
        'reid_rate_head_high': head_result.get('reid_rate_head_high', float('nan')),
        'reid_rate_head_low':  head_result.get('reid_rate_head_low',  float('nan')),
        # gate-B topology cols (clDice gate主判据 + Betti 交叉印证)
        'cldice':           cldice_val,
        'betti_err_total':  betti_err_tot,
        # seed: required by gate_frangi_verdict.py for (image_id, seed) pairing
        'seed':             seed,
    }
    return row


def evaluate_on_benchmark(
    model: nn.Module,
    device: torch.device,
    npz_paths: List[str],
    reid_feat_source: str,
    csv_path: Optional[Path] = None,
    epoch: int = 0,
    arm: str = 'memory',
    k_thresh: Optional[float] = None,
    seed: int = 42,
) -> Dict[str, float]:
    """
    Run model on a list of benchmark NPZ files, accumulate per-image metrics,
    optionally append to reid_results.csv, and return aggregate averages.

    Arguments:
      npz_paths      — list of NPZ paths (from load_benchmark_npz_list).
                       Single-element list = backward-compat single-file mode.
      k_thresh       — A-v2 M-B: preregistered crowding threshold (median from
                       crowding_manifest.json). When provided, also computes
                       reid_rate_head_high / reid_rate_head_low per image.
      csv_path       — if not None, append per-image rows to this CSV.
      epoch          — current training epoch (written to CSV).
      arm            — reid_feat_source string for CSV 'arm' column.
      seed           — training seed, written to CSV 'seed' column for gate pairing.

    Returns dict of aggregated means:
      reid_rate, epsilon_beta0, success_rate, cldice_mean, betti_err_total_mean,
      n_gaps (total), n_images.

    Statistical power note:
      Partial-corr across two arms requires n≥10 per arm (20 total) for
      meaningful CI.  With n<10 a WARNING is printed.

    RED LINE: npz_paths must originate from precompute_benchmark.py test-only split.
    """
    if not npz_paths:
        return {
            'reid_rate': 0.0, 'epsilon_beta0': 0.0, 'success_rate': 0.0,
            'cldice_mean': 0.0, 'betti_err_total_mean': 0.0,
            'n_gaps': 0, 'n_images': 0,
        }

    per_image_rows: List[Dict] = []
    errors = 0

    for npz_path in npz_paths:
        try:
            row = _eval_single_npz(model, device, npz_path, reid_feat_source,
                                   k_thresh=k_thresh, seed=seed)
            per_image_rows.append(row)
        except Exception as exc:
            print(f'  [benchmark] SKIP {Path(npz_path).name}: {exc}')
            errors += 1

    if not per_image_rows:
        print(f'  [benchmark] WARNING: all {len(npz_paths)} NPZ(s) failed to evaluate.')
        return {
            'reid_rate': 0.0, 'epsilon_beta0': 0.0, 'success_rate': 0.0,
            'n_gaps': 0, 'n_images': 0,
        }

    n_images = len(per_image_rows)
    if n_images < 10:
        print(f'  [benchmark] WARNING: only {n_images} images evaluated. '
              f'Statistical power for partial-corr is LOW (need n≥10 per arm). '
              f'Run precompute_benchmark.py for more test images.')

    # Aggregate means
    rr_mean  = float(np.mean([r['reid_rate']     for r in per_image_rows]))
    eps_mean = float(np.mean([r['epsilon_beta0'] for r in per_image_rows]))
    sr_mean  = float(np.mean([r['success_rate']  for r in per_image_rows]))
    n_gaps   = int(sum(r['n_gaps']               for r in per_image_rows))

    def _nanmean_list(key: str) -> float:
        """nanmean over a named column; nan if all nan."""
        vals = [r.get(key, float('nan')) for r in per_image_rows]
        arr  = np.array(vals, dtype=np.float64)
        return float(np.nanmean(arr)) if not np.all(np.isnan(arr)) else float('nan')

    # Aggregate reid_rate_head / reid_idf1 (ignore NaN rows — nanmean)
    rrh_mean        = _nanmean_list('reid_rate_head')
    ridf1_mean      = _nanmean_list('reid_idf1')
    # A-v2 M-B: crowding-stratified aggregates
    rrh_high_mean   = _nanmean_list('reid_rate_head_high')
    rrh_low_mean    = _nanmean_list('reid_rate_head_low')
    # gate-B topology aggregates
    cldice_mean     = _nanmean_list('cldice')
    betti_err_mean  = _nanmean_list('betti_err_total')

    def _safe_round(v: float, ndigits: int = 6) -> object:
        """Round finite float; return 'nan' string for NaN (csv-safe)."""
        import math
        return round(v, ndigits) if math.isfinite(v) else float('nan')

    # Append per-image rows to CSV (production mode)
    # Columns: epoch, image_id, severity, dataset,
    #          reid_rate, reid_rate_head, reid_idf1,
    #          epsilon_beta0, success_rate, n_gaps,
    #          reid_rate_head_high, reid_rate_head_low,  ← A-v2 M-B new columns
    #          seed, cldice, betti_err_total,            ← gate-B topology cols
    #          arm
    # CRITICAL: header (written in main()) must match this column order exactly.
    if csv_path is not None:
        with open(csv_path, 'a', newline='', encoding='utf-8') as cf:
            writer = csv.writer(cf)
            for row in per_image_rows:
                writer.writerow([
                    epoch,
                    row['image_id'],
                    row['severity'],
                    row['dataset'],
                    _safe_round(row['reid_rate'],                           6),
                    _safe_round(row.get('reid_rate_head',       float('nan')), 6),
                    _safe_round(row.get('reid_idf1',            float('nan')), 6),
                    _safe_round(row['epsilon_beta0'],                       6),
                    _safe_round(row['success_rate'],                        6),
                    row['n_gaps'],
                    _safe_round(row.get('reid_rate_head_high',  float('nan')), 6),
                    _safe_round(row.get('reid_rate_head_low',   float('nan')), 6),
                    row.get('seed', seed),                                  # gate pairing key
                    _safe_round(row.get('cldice',          float('nan')), 6),
                    _safe_round(row.get('betti_err_total', float('nan')), 6),
                    arm,
                ])

    if errors:
        print(f'  [benchmark] {errors} NPZ(s) skipped due to errors (of {len(npz_paths)} total).')

    return {
        'reid_rate':              rr_mean,
        'reid_rate_head':         rrh_mean,
        'reid_idf1':              ridf1_mean,
        'reid_rate_head_high':    rrh_high_mean,
        'reid_rate_head_low':     rrh_low_mean,
        'epsilon_beta0':          eps_mean,
        'success_rate':           sr_mean,
        'cldice_mean':            cldice_mean,       # gate-B primary metric
        'betti_err_total_mean':   betti_err_mean,    # gate-B cross-validation
        'n_gaps':                 n_gaps,
        'n_images':               n_images,
    }


# --------------------------------------------------------------------------- #
#  Build breakpoint positions for training-time re-ID supervision
# --------------------------------------------------------------------------- #

def _sample_breakpoint_positions(
    gt_batch: torch.Tensor,
    n_bps: int,
    device: torch.device,
) -> Tuple[torch.Tensor, torch.Tensor]:
    """
    Sample n_bps breakpoint positions from GT vessel foreground pixels.

    For training: we use apply_breaks on each GT mask (in CPU numpy), then pick
    gap centres as breakpoint positions for the re-ID head.  Same-root labels
    are derived from the GapRecord segment IDs (two endpoints of same gap = positive).

    Returns:
        positions:       (B, n_bps, 2)  float — (h, w) pixel coords
        same_root_labels:(B, n_bps, n_bps) float {0,1}

    R5 guard: GT mask is used only to derive synthetic breakpoint positions
    (we apply_breaks ourselves — we know which pixels we cut).
    The positions themselves do NOT encode GT topology — they are gap centres
    in the broken mask.  This is the "apply_breaks weak supervision" creatis
    paradigm (Claim 2, STORY R5).
    """
    from benchmark.synth_breaks import apply_breaks

    B, C, H, W = gt_batch.shape
    all_positions = torch.zeros(B, n_bps, 2, device=device)
    all_labels    = torch.zeros(B, n_bps, n_bps, device=device)

    for b in range(B):
        gt_np = gt_batch[b, 0].cpu().numpy().astype(np.uint8)  # (H, W)

        # Synthesise breaks with a random seed per sample (non-frozen, training-time)
        seed = int(torch.randint(0, 100000, (1,)).item())
        try:
            br = apply_breaks(gt_np, gap_size=8, nb_deco=50, seed=seed)
        except Exception:
            # Degenerate mask (all-black) — return zero positions / zero labels
            continue

        gaps = br.gaps
        if len(gaps) == 0:
            continue

        # Build gap-centre position list, capped to n_bps
        centres = [g.center_yx for g in gaps[:n_bps]]
        seg_left  = [g.segment_id_left  for g in gaps[:n_bps]]
        seg_right = [g.segment_id_right for g in gaps[:n_bps]]
        k = len(centres)

        pos_tensor = torch.zeros(n_bps, 2)
        for i, (cy, cx) in enumerate(centres):
            pos_tensor[i, 0] = float(cy)
            pos_tensor[i, 1] = float(cx)
        all_positions[b, :k] = pos_tensor[:k].to(device)

        # Same-root label matrix: label[i,j]=1 if i and j share a vessel segment
        # Two gap endpoints are "same root" if they share seg_left or seg_right.
        labels_b = torch.zeros(n_bps, n_bps)
        for i in range(k):
            for j in range(k):
                if i == j:
                    continue
                segs_i = {seg_left[i], seg_right[i]} - {-1}
                segs_j = {seg_left[j], seg_right[j]} - {-1}
                if segs_i & segs_j:   # non-empty intersection = shared vessel root
                    labels_b[i, j] = 1.0
        all_labels[b] = labels_b.to(device)

    return all_positions, all_labels


# --------------------------------------------------------------------------- #
#  Training epoch (re-ID pilot)
# --------------------------------------------------------------------------- #

def train_epoch_reid(
    model: nn.Module,
    loader: DataLoader,
    optimizer: torch.optim.Optimizer,
    device: torch.device,
    lambda_reid: float,
    lambda_c: float,
    n_bps: int,
) -> float:
    """
    One training epoch: seg_loss + reid_loss (L_match + L_contrastive).
    re-ID head receives breakpoint positions derived from apply_breaks on
    the same GT batch (synthetic-break weak supervision, detach-isolated).
    """
    from models.reid_loss import compute_reid_combined_loss

    model.train()
    total_loss = 0.0

    for batch in loader:
        img = batch['image'].to(device)    # (B, 1, H, W)
        gt  = batch['gt'].to(device)       # (B, 1, H, W) float {0,1}
        fov = batch['fov'].to(device)      # (B, 1, H, W) float {0,1}

        optimizer.zero_grad()

        # Forward: request reid_ctx
        logits, reid_ctx = model(img, return_reid_ctx=True)  # logits (B,1,H,W)

        # Segmentation loss
        l_seg = seg_loss(logits, gt, fov)

        # Re-ID loss (synthetic-break weak supervision, detach-isolated)
        reid_logits_val = None
        same_root_labels_val = None

        if model.use_reid_head and reid_ctx.get('o_seq') is not None:
            # Sample breakpoint positions from GT (we cut them ourselves)
            positions, same_root_labels = _sample_breakpoint_positions(
                gt, n_bps=n_bps, device=device
            )
            # Clamp positions to dec_feat resolution
            dec_feat = reid_ctx['dec_feat']  # (B, dec_ch, H_dec, W_dec)
            H_dec = dec_feat.shape[-2]
            W_dec = dec_feat.shape[-1]
            positions[..., 0].clamp_(0, H_dec - 1)
            positions[..., 1].clamp_(0, W_dec - 1)

            # reid_head expects positions in dec_feat coordinate space
            reid_logits_val = model.reid_head(
                o_seq=reid_ctx['o_seq'],
                dec_feat=reid_ctx['dec_feat'],
                breakpoint_positions=positions,
                memory_state=reid_ctx.get('memory_state'),
            )
            same_root_labels_val = same_root_labels

        loss = compute_reid_combined_loss(
            l_seg, reid_logits_val, same_root_labels_val,
            lambda_reid=lambda_reid, lambda_c=lambda_c,
        )
        loss.backward()
        optimizer.step()
        total_loss += loss.item()

    return total_loss / max(len(loader), 1)


# --------------------------------------------------------------------------- #
#  Validation epoch (seg Dice only — re-ID eval done on benchmark separately)
# --------------------------------------------------------------------------- #

@torch.no_grad()
def val_epoch(
    model: nn.Module,
    loader: DataLoader,
    device: torch.device,
) -> float:
    model.eval()
    dice_scores = []
    for batch in loader:
        img = batch['image'].to(device)
        gt  = batch['gt'].to(device)
        fov = batch['fov'].to(device)

        logits = model(img)   # (B, 1, H, W) — no reid_ctx needed for val Dice
        prob = torch.sigmoid(logits)
        pred_bin = (prob > 0.5).float()

        for b in range(img.shape[0]):
            d = dice_np(
                pred_bin[b, 0].cpu().numpy(),
                gt[b, 0].cpu().numpy(),
                fov[b, 0].cpu().numpy(),
            )
            dice_scores.append(d)

    return float(np.mean(dice_scores)) if dice_scores else 0.0


# --------------------------------------------------------------------------- #
#  state.json helpers
# --------------------------------------------------------------------------- #

def write_state(path: Path, epoch: int, train_loss: float, val_dice: float,
                best_dice: float, status: str,
                benchmark_metrics: Optional[Dict] = None,
                partial_corr_result: Optional[Dict] = None,
                reid_feat_source: str = 'memory'):
    """
    Write live training state to state.json (atomic rename).

    Schema adds re-ID fields on top of train_pilot.py base schema:
      reid_rate, epsilon_beta0, success_rate — from held-out benchmark eval.
      partial_corr — partial correlation result dict (after both arms available).
      reid_feat_source — which ablation arm is running.
    """
    state: Dict = {
        'epoch':          epoch,
        'train_loss':     round(float(train_loss), 6),
        'val_dice':       round(float(val_dice), 6),
        'best_dice':      round(float(best_dice), 6),
        'status':         status,
        'reid_feat_source': reid_feat_source,
    }
    if benchmark_metrics is not None:
        import math as _math
        def _rnd(v, nd=6):
            """Round finite float; pass through NaN as-is (json will write null)."""
            try:
                f = float(v)
                return round(f, nd) if _math.isfinite(f) else None
            except (TypeError, ValueError):
                return None
        state['reid_rate']            = _rnd(benchmark_metrics.get('reid_rate', 0.0))
        state['reid_rate_head']       = _rnd(benchmark_metrics.get('reid_rate_head',      float('nan')))
        state['reid_idf1']            = _rnd(benchmark_metrics.get('reid_idf1',           float('nan')))
        state['reid_rate_head_high']  = _rnd(benchmark_metrics.get('reid_rate_head_high', float('nan')))
        state['reid_rate_head_low']   = _rnd(benchmark_metrics.get('reid_rate_head_low',  float('nan')))
        state['epsilon_beta0']        = _rnd(benchmark_metrics.get('epsilon_beta0', 0.0))
        state['success_rate']         = _rnd(benchmark_metrics.get('success_rate', 0.0))
        state['n_gaps']               = int(benchmark_metrics.get('n_gaps', 0))
        state['n_images']             = int(benchmark_metrics.get('n_images', 0))
    if partial_corr_result is not None:
        state['partial_corr'] = {k: round(float(v), 6) if isinstance(v, float) else v
                                  for k, v in partial_corr_result.items()}

    tmp = path.with_suffix('.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2)
    tmp.replace(path)


def save_ckpt(model: nn.Module, path: Path):
    torch.save(model.state_dict(), path)


# --------------------------------------------------------------------------- #
#  Partial-corr standalone mode (reads two state.json files, outputs verdict)
# --------------------------------------------------------------------------- #

def run_partial_corr_only(args) -> None:
    """
    Read two arm state.json files, compute partial_corr(memory_on, reid_rate | ε_β0).

    Interpretation:
      X = memory indicator: 1.0 for A2 (memory arm), 0.0 for A0' (CNN arm).
      Y = reid_rate   (from state.json['reid_rate'])
      Z = ε_β0        (from state.json['epsilon_beta0'])

    Requires at least one epoch of evaluation data in each state file
    (uses final best value, or last-written value).

    Prints verdict to stdout + writes to partial_corr_verdict.json.

    NOTE: This mode is designed to combine per-image evaluation results from
    a CSV log (--csv_a / --csv_b) if available, otherwise falls back to scalar
    values from state.json (less statistical power — fewer data points).
    """
    def _load_state(p: str) -> Dict:
        with open(p, 'r', encoding='utf-8') as f:
            return json.load(f)

    state_a = _load_state(args.state_a)
    state_b = _load_state(args.state_b)

    print(f"[partial_corr] state_a: {args.state_a}")
    print(f"  reid_feat_source={state_a.get('reid_feat_source','?')}, "
          f"reid_rate={state_a.get('reid_rate','?')}, "
          f"epsilon_beta0={state_a.get('epsilon_beta0','?')}")
    print(f"[partial_corr] state_b: {args.state_b}")
    print(f"  reid_feat_source={state_b.get('reid_feat_source','?')}, "
          f"reid_rate={state_b.get('reid_rate','?')}, "
          f"epsilon_beta0={state_b.get('epsilon_beta0','?')}")

    # Try to load per-image CSV logs for more statistical power
    csv_a_path = args.csv_a or str(Path(args.state_a).parent / 'reid_results.csv')
    csv_b_path = args.csv_b or str(Path(args.state_b).parent / 'reid_results.csv')

    rows_a, rows_b = [], []
    for csv_path, rows in [(csv_a_path, rows_a), (csv_b_path, rows_b)]:
        if Path(csv_path).exists():
            with open(csv_path, 'r', newline='', encoding='utf-8') as cf:
                reader = csv.DictReader(cf)
                for row in reader:
                    try:
                        # Accept both old (epoch,train_loss,...) and new per-image columns.
                        # New CSV has: epoch,image_id,severity,dataset,reid_rate,epsilon_beta0,...
                        # Old CSV had: epoch,train_loss,val_dice,reid_rate,epsilon_beta0,...
                        # Both have 'reid_rate' and 'epsilon_beta0' — safe to read by name.
                        rr  = row.get('reid_rate', '')
                        eps = row.get('epsilon_beta0', '')
                        if rr == '' or eps == '':
                            continue
                        rows.append({
                            'reid_rate':     float(rr),
                            'epsilon_beta0': float(eps),
                        })
                    except (KeyError, ValueError):
                        pass

    if rows_a and rows_b:
        # Per-image mode: concat both arms with memory indicator
        rr_vals  = [r['reid_rate']     for r in rows_a] + [r['reid_rate']     for r in rows_b]
        eps_vals = [r['epsilon_beta0'] for r in rows_a] + [r['epsilon_beta0'] for r in rows_b]
        mem_vals = ([1.0] * len(rows_a)) + ([0.0] * len(rows_b))
        data_source = 'per-image CSV'
        n_total = len(rows_a) + len(rows_b)
        if n_total < 20:
            print(f"[partial_corr] WARNING: only {n_total} data points total "
                  f"(a={len(rows_a)}, b={len(rows_b)}). "
                  f"Need ≥20 for reliable CI (partial-corr power LOW). "
                  f"Use --benchmark_dir with more images.")
        elif min(len(rows_a), len(rows_b)) < 10:
            print(f"[partial_corr] WARNING: imbalanced arms "
                  f"(a={len(rows_a)}, b={len(rows_b)}). "
                  f"Each arm should have ≥10 rows for reliable CI.")
    else:
        # Scalar fallback: two data points only — very low power, warn
        print("[partial_corr] WARNING: CSV logs not found; using 2-point scalar fallback."
              " Statistical power is very low. Run with more images for reliable CI.")
        rr_vals  = [state_a.get('reid_rate',  0.0), state_b.get('reid_rate',  0.0)]
        eps_vals = [state_a.get('epsilon_beta0', 0.0), state_b.get('epsilon_beta0', 0.0)]
        # A2=memory=1, A0'=CNN=0
        src_a = state_a.get('reid_feat_source', 'memory')
        src_b = state_b.get('reid_feat_source', 'cnn')
        mem_vals = [1.0 if src_a == 'memory' else 0.0,
                    1.0 if src_b == 'memory' else 0.0]
        data_source = 'scalar state.json (2 points)'

    X = np.array(mem_vals, dtype=np.float64)
    Y = np.array(rr_vals,  dtype=np.float64)
    Z = np.array(eps_vals, dtype=np.float64)

    result = partial_corr_numpy(X, Y, Z, n_resample=1000, rng_seed=42)
    result['data_source'] = data_source

    verdict = 'PASS' if result['PASS'] else 'FAIL'
    print(f"\n[partial_corr] partial_corr(memory_on, reid_rate | ε_β0):")
    print(f"  r={result['r']:.4f}  95%CI=[{result['ci_lower']:.4f}, {result['ci_upper']:.4f}]")
    print(f"  n={result['n']}  data_source={data_source}")
    print(f"  Pre-registered threshold: r>0.2 AND CI_lower>0")
    print(f"  VERDICT: {verdict}")
    if not result['PASS']:
        print("  ⚠ FAIL → Claim 2 degraded: re-ID is ε_β0 side-effect, not independent.")
        print("    STOP: report to user (拍板点 — ACCEPTANCE P4 致命-2 FAIL)")

    # Write verdict file
    verdict_path = Path(args.state_a).parent / 'partial_corr_verdict.json'
    with open(verdict_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2)
    print(f"[partial_corr] verdict written → {verdict_path}")


# --------------------------------------------------------------------------- #
#  Model builder
# --------------------------------------------------------------------------- #

def build_model(args) -> nn.Module:
    """
    Build UNetGDN2 with re-ID head wired for the specified ablation arm.

    A2  (memory):       memory_mode='delta_rule',  reid_feat_source='memory', detach=True
    A1' (linear_attn):  memory_mode='linear_attn', reid_feat_source='linear_attn', detach=True
    A0' (cnn):          memory_mode='cnn',          reid_feat_source='cnn',    detach=True
    A3  ablation: detach_memory_train=False (args.no_detach_memory)
    A4  ablation: reid_breakpoint_source='pred_skeleton'
    """
    from models.unet_gdn2 import UNetGDN2

    reid_feat_source = args.reid_feat_source

    # Map reid_feat_source → memory_mode (arm selector for UNetGDN2)
    _source_to_mode = {
        'memory':       'delta_rule',   # A2: stateful GDN-2 associative memory
        'linear_attn':  'linear_attn',  # A1': iso-param stateless linear attention
        'cnn':          'cnn',          # A0': pure CNN, no attention module
    }
    memory_mode = _source_to_mode[reid_feat_source]

    # A3: detach control
    detach_mem = not args.no_detach_memory
    # A4: breakpoint source
    bp_source = args.reid_breakpoint_source
    # A-v2 M-A: memory-only head (use_loc_feat=False) or fuse head (use_loc_feat=True)
    use_loc_feat = getattr(args, 'use_loc_feat', True)

    # --use_frangi CLI flag (路B gate-on/off 对照实验入口).
    # Default behaviour preserved: on for delta_rule/linear_attn, off for cnn.
    # Explicit --use_frangi {0,1} overrides the default for ALL memory_modes,
    # allowing gate-on vs gate-off under the SAME memory_mode (delta_rule).
    _frangi_cli = getattr(args, 'use_frangi', None)   # None = auto (not passed on CLI)
    if _frangi_cli is not None:
        use_frangi = bool(int(_frangi_cli))            # explicit: 1→True, 0→False
    else:
        use_frangi = memory_mode in ('delta_rule', 'linear_attn')  # legacy auto

    model = UNetGDN2(
        in_ch=1,
        out_ch=1,
        base_ch=args.base_ch,
        d_head=args.d_head,
        n_heads=args.n_heads,
        memory_mode=memory_mode,
        backend=args.backend,
        directions=1,
        use_frangi=use_frangi,
        use_reid_head=True,
        dec_feat_layer='dec3',
        reid_d_id=args.reid_d_id,
        reid_feat_source=reid_feat_source,
        reid_detach_memory_train=detach_mem,
        reid_breakpoint_source=bp_source,
        reid_use_loc_feat=use_loc_feat,   # A-v2 M-A
    )

    # Assertions to guard red-lines (R5, detach)
    assert model.use_reid_head, "re-ID head must be attached"
    assert model.reid_head.detach_memory_train == detach_mem
    assert model.reid_head.feat_source == reid_feat_source
    # R5: memory/Frangi has no 'gt' param — checked structurally
    import inspect
    if model.memory is not None:
        sig = inspect.signature(model.memory.forward)
        assert 'gt' not in sig.parameters, "GDN2MemoryModule.forward must not accept 'gt'"
    if model.linear_attn is not None:
        sig = inspect.signature(model.linear_attn.forward)
        assert 'gt' not in sig.parameters, "LinearAttnModule.forward must not accept 'gt'"

    return model


# --------------------------------------------------------------------------- #
#  Argument parser
# --------------------------------------------------------------------------- #

def parse_args():
    p = argparse.ArgumentParser(
        description='gdn2vessel re-ID pilot harness (Claim 2 / 致命-2 判据)')

    # ---- Partial-corr standalone mode ----
    p.add_argument('--partial_corr_only', action='store_true',
                   help='Only compute partial correlation from two existing state files')
    p.add_argument('--state_a', type=str, default=None,
                   help='Path to state.json of arm A (e.g. A2 memory arm)')
    p.add_argument('--state_b', type=str, default=None,
                   help='Path to state.json of arm B (e.g. A0 CNN arm)')
    p.add_argument('--csv_a', type=str, default=None,
                   help='Path to reid_results.csv of arm A (optional, higher power)')
    p.add_argument('--csv_b', type=str, default=None,
                   help='Path to reid_results.csv of arm B (optional, higher power)')

    # ---- Training mode ----
    p.add_argument('--reid_feat_source', default='memory',
                   choices=['memory', 'linear_attn', 'cnn'],
                   help="A2=memory (headline), A1'=linear_attn (iso-param ablation), "
                        "A0'=cnn (zero-hypothesis)")
    p.add_argument('--reid_breakpoint_source', default='gt_skeleton',
                   choices=['pred_skeleton', 'gt_skeleton'],
                   help='A4=pred_skeleton (封泄漏); default=gt_skeleton (A2)')
    p.add_argument('--no_detach_memory', action='store_true',
                   help='A3 ablation: disable detach (default: detach=True, MUST be '
                        'True in non-ablation runs)')
    p.add_argument('--use_loc_feat', action='store_true', default=True,
                   help='A-v2 M-A: include dec_feat in re-ID head (default True). '
                        'Pass --no_use_loc_feat for memory-only head (命门 A-v2 三臂).')
    p.add_argument('--no_use_loc_feat', dest='use_loc_feat', action='store_false',
                   help='A-v2 M-A: memory-only head (砍 dec_feat 近路).')
    # 路B Frangi门 on/off 独立开关（gate-on vs gate-off 2臂对照实验）
    # Default behaviour (None): 跟随 memory_mode 自动选（delta_rule/linear_attn→on, cnn→off）
    # Explicit 1: gate-on 无论 memory_mode; Explicit 0: gate-off 无论 memory_mode。
    p.add_argument('--use_frangi', type=int, default=None,
                   choices=[0, 1],
                   help='路B Frangi门开关：1=gate-on, 0=gate-off. '
                        'Default None = auto (delta_rule/linear_attn→1, cnn→0).')
    p.add_argument('--k_thresh', type=float, default=None,
                   help='A-v2 M-B: preregistered crowding threshold k_thresh '
                        '(median, from crowding_manifest.json). When provided, '
                        'also outputs reid_rate_head_high / reid_rate_head_low. '
                        'If omitted, loads from crowding_manifest.json in '
                        '--benchmark_dir (if exists); otherwise crowding cols = NaN.')
    p.add_argument('--crowding_manifest', type=str, default=None,
                   help='Path to crowding_manifest.json (default: '
                        '<benchmark_dir>/crowding_manifest.json).')

    p.add_argument('--data_root', type=str, required=False,
                   help='Path to dataset root directory (e.g. .../CHASE for --dataset chase, '
                        '.../DRIVE for --dataset drive). Subdir structure per each dataset class.')

    # ---- Benchmark source (two modes, mutually exclusive but both optional) ----
    p.add_argument('--benchmark_npz', type=str, default=None,
                   help='Single-file backward-compat mode: path to one pre-frozen NPZ '
                        '(from precompute_benchmark.py). For smoke/debug only — '
                        'use --benchmark_dir for production (n≥20 images).')
    p.add_argument('--benchmark_dir', type=str, default=None,
                   help='Multi-image mode: directory containing precomputed NPZs + '
                        'manifest.json (output of precompute_benchmark.py). '
                        'Use with --dataset and --severity to filter entries.')
    p.add_argument('--dataset', type=str, default=None,
                   choices=['drive', 'chase', 'stare', 'hrf', 'fives'],
                   help='Dataset filter for --benchmark_dir mode '
                        '(e.g. drive). If omitted, all datasets are used.')
    p.add_argument('--severity', type=str, default=None,
                   choices=['Easy', 'Medium', 'Hard', 'Extreme'],
                   help='Severity filter for --benchmark_dir mode '
                        '(e.g. Medium). If omitted, all severities are used.')
    p.add_argument('--output_dir', type=str, default='outputs/reid_pilot')
    p.add_argument('--epochs', type=int, default=100)
    p.add_argument('--lr', type=float, default=1e-3)
    p.add_argument('--batch_size', type=int, default=2)
    p.add_argument('--patch_size', type=int, default=512)
    p.add_argument('--num_workers', type=int, default=0,
                   help='DataLoader workers. 0=safe on Windows. 2-4 on HPC Linux.')
    p.add_argument('--backend', default='naive', choices=['naive', 'chunk'])
    p.add_argument('--patience', type=int, default=20)
    p.add_argument('--base_ch', type=int, default=32)
    p.add_argument('--d_head', type=int, default=64)
    p.add_argument('--n_heads', type=int, default=1)
    p.add_argument('--reid_d_id', type=int, default=64)
    p.add_argument('--n_bps', type=int, default=8,
                   help='Number of breakpoint positions per image for re-ID head training')
    p.add_argument('--lambda_reid', type=float, default=0.1,
                   help='Weight for L_match. NOTE: self-designed; grid {0.05,0.1,0.3}')
    p.add_argument('--lambda_c', type=float, default=0.05,
                   help='Weight for L_contrastive. NOTE: self-designed; grid {0.0,0.05,0.1}')
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--eval_benchmark_every', type=int, default=10,
                   help='Evaluate benchmark re-ID metrics every N epochs')
    p.add_argument('--smoke', action='store_true',
                   help='Run 2 mini-steps and exit (CI smoke test, no data needed '
                        'when --benchmark_npz is omitted in smoke mode)')

    return p.parse_args()


# --------------------------------------------------------------------------- #
#  Main
# --------------------------------------------------------------------------- #

def main():
    args = parse_args()

    # ---- Partial-corr standalone mode ----
    if args.partial_corr_only:
        if args.state_a is None or args.state_b is None:
            print('[partial_corr_only] ERROR: --state_a and --state_b required')
            sys.exit(1)
        run_partial_corr_only(args)
        return

    # ---- Training mode ----
    if args.data_root is None:
        print('[train_reid_pilot] ERROR: --data_root required for training mode')
        sys.exit(1)

    # Reproducibility
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    state_path  = output_dir / 'state.json'
    ckpt_path   = output_dir / 'best.pth'
    csv_path    = output_dir / 'reid_results.csv'

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    _arm_labels = {
        'memory':       'A2(memory)',
        'linear_attn':  "A1'(linear_attn)",
        'cnn':          "A0'(cnn)",
    }
    arm_label = _arm_labels.get(args.reid_feat_source, args.reid_feat_source)
    _frangi_cli_val = getattr(args, 'use_frangi', None)
    _frangi_str = ('auto' if _frangi_cli_val is None
                   else ('gate-on(1)' if int(_frangi_cli_val) == 1 else 'gate-off(0)'))
    print(f'[train_reid_pilot] device={device}  arm={arm_label}  '
          f'detach_memory={not args.no_detach_memory}  '
          f'bp_source={args.reid_breakpoint_source}  seed={args.seed}  '
          f'use_frangi={_frangi_str}')

    # Warn if A3 ablation active (safety reminder)
    if args.no_detach_memory:
        print('[train_reid_pilot] ⚠ A3 ablation: detach_memory_train=False — '
              'gradients will flow into memory.  Use ONLY for ablation comparison.')

    # Dataset — registry-driven by --dataset (mirrors precompute_benchmark._build_registry)
    # DRIVE uses standalone DRIVEDataset; CHASE/STARE/HRF/FIVES inherit BaseVesselDataset.
    # Both share the same constructor signature: (data_root, split, patch_size, augment).
    # Red-line 1: TEST_IDS in each class are disjoint from TRAIN_IDS/VAL_IDS (asserted at
    # __init__ time by BaseVesselDataset._check_split_disjoint); benchmark NPZs are
    # pre-frozen from the test split only → no leakage possible here (train uses 'train').
    _dataset_key = (args.dataset or 'drive').lower()
    if _dataset_key == 'drive':
        from datasets.drive import DRIVEDataset as _DatasetCls
    elif _dataset_key == 'chase':
        from datasets.chase import CHASEDataset as _DatasetCls
    elif _dataset_key == 'stare':
        from datasets.stare import STAREDataset as _DatasetCls
    elif _dataset_key == 'hrf':
        from datasets.hrf import HRFDataset as _DatasetCls
    elif _dataset_key == 'fives':
        from datasets.fives import FIVESDataset as _DatasetCls
    else:
        raise ValueError(f'[train_reid_pilot] Unknown --dataset {_dataset_key!r}. '
                         f'Choices: drive | chase | stare | hrf | fives')

    print(f'[train_reid_pilot] dataset={_dataset_key}  data_root={args.data_root}')
    train_ds = _DatasetCls(
        data_root=args.data_root,
        split='train',
        patch_size=args.patch_size,
        augment=True,
    )
    val_ds = _DatasetCls(
        data_root=args.data_root,
        split='val',
        patch_size=args.patch_size,
        augment=False,
    )

    # DataLoader — spawn + pin_memory=False for Windows compatibility
    loader_kwargs: Dict = dict(
        batch_size=args.batch_size,
        num_workers=args.num_workers,
        pin_memory=False,          # pin_memory=False mandatory on Windows spawn
    )
    if args.num_workers > 0:
        loader_kwargs['multiprocessing_context'] = 'spawn'

    train_loader = DataLoader(train_ds, shuffle=True,  **loader_kwargs)
    val_loader   = DataLoader(val_ds,   shuffle=False, **loader_kwargs)

    # Model
    model = build_model(args).to(device)
    n_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f'[train_reid_pilot] model params = {n_params:,}')
    print(f'[train_reid_pilot] use_memory={model.memory is not None}  '
          f'reid_head.feat_source={model.reid_head.feat_source}  '
          f'reid_head.detach_memory_train={model.reid_head.detach_memory_train}')

    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode='max', factor=0.5, patience=10, min_lr=1e-6)

    best_dice = 0.0
    no_improve = 0

    # Resolve benchmark NPZ list once (multi-image production or single-file smoke)
    benchmark_npz_list = load_benchmark_npz_list(
        benchmark_npz=args.benchmark_npz,
        benchmark_dir=getattr(args, 'benchmark_dir', None),
        dataset=getattr(args, 'dataset', None),
        severity=getattr(args, 'severity', None),
    )
    if benchmark_npz_list:
        n_bench = len(benchmark_npz_list)
        print(f'[train_reid_pilot] benchmark: {n_bench} NPZ(s) '
              f'({"multi-image" if n_bench > 1 else "single-file"} mode)')
        if n_bench < 10:
            print(f'  WARNING: {n_bench} < 10 benchmark images. '
                  f'Use --benchmark_dir for production partial-corr (need n≥10 per arm).')
    else:
        print('[train_reid_pilot] No benchmark NPZ specified; skipping held-out eval.')

    # --- A-v2 M-B: resolve k_thresh from manifest or CLI arg ---
    # k_thresh is preregistered before training (not derived from results).
    # Priority: --k_thresh CLI > crowding_manifest.json in benchmark_dir.
    _k_thresh: Optional[float] = getattr(args, 'k_thresh', None)
    if _k_thresh is None:
        # Try to load from crowding_manifest.json
        _bench_dir = getattr(args, 'benchmark_dir', None)
        _manifest_path_arg = getattr(args, 'crowding_manifest', None)
        _manifest_src = _manifest_path_arg or (
            str(Path(_bench_dir) / 'crowding_manifest.json') if _bench_dir else None
        )
        if _manifest_src and Path(_manifest_src).exists():
            try:
                from benchmark.crowding import load_k_manifest, get_k_thresh_for_dataset
                _cmanifest = load_k_manifest(str(Path(_manifest_src).parent))
                _ds_for_k = getattr(args, 'dataset', None) or 'chase'
                _k_thresh = get_k_thresh_for_dataset(_cmanifest, _ds_for_k)
                if not (isinstance(_k_thresh, float) and _k_thresh == _k_thresh):
                    _k_thresh = None
                else:
                    print(f'[train_reid_pilot] k_thresh loaded from manifest: '
                          f'{_k_thresh:.1f} (dataset={_ds_for_k})')
            except Exception as _ke:
                print(f'[train_reid_pilot] WARNING: could not load k_thresh from manifest: {_ke}')
                _k_thresh = None
        else:
            print('[train_reid_pilot] No crowding_manifest.json found; '
                  'reid_rate_head_high/low will be NaN (run crowding.py first).')
    else:
        print(f'[train_reid_pilot] k_thresh from --k_thresh arg: {_k_thresh:.1f}')

    # CSV header — per-image schema.
    # A-v2 M-B: added reid_rate_head_high, reid_rate_head_low (crowding-stratified).
    # CRITICAL: column order here MUST match the writerow() call in
    #           evaluate_on_benchmark() — any divergence causes header/data mismatch
    #           (blood-lesson from A-I integration, 2026-06-20).
    with open(csv_path, 'w', newline='', encoding='utf-8') as cf:
        writer = csv.writer(cf)
        writer.writerow([
            'epoch', 'image_id', 'severity', 'dataset',
            'reid_rate', 'reid_rate_head', 'reid_idf1',
            'epsilon_beta0', 'success_rate', 'n_gaps',
            'reid_rate_head_high', 'reid_rate_head_low',   # A-v2 M-B crowding cols
            'seed', 'cldice', 'betti_err_total',           # gate-B topology cols
            'arm',
        ])

    write_state(state_path, 0, 0.0, 0.0, 0.0, 'running',
                reid_feat_source=args.reid_feat_source)

    for epoch in range(1, args.epochs + 1):
        t0 = time.time()

        train_loss = train_epoch_reid(
            model, train_loader, optimizer, device,
            lambda_reid=args.lambda_reid,
            lambda_c=args.lambda_c,
            n_bps=args.n_bps,
        )
        val_dice = val_epoch(model, val_loader, device)
        elapsed = time.time() - t0

        scheduler.step(val_dice)

        improved = val_dice > best_dice
        if improved:
            best_dice = val_dice
            save_ckpt(model, ckpt_path)
            no_improve = 0
        else:
            no_improve += 1

        # Benchmark re-ID evaluation (held-out multi-image, every N epochs)
        bench_metrics = None
        if benchmark_npz_list and epoch % args.eval_benchmark_every == 0:
            try:
                # evaluate_on_benchmark appends per-image rows to csv_path directly
                bench_metrics = evaluate_on_benchmark(
                    model=model,
                    device=device,
                    npz_paths=benchmark_npz_list,
                    reid_feat_source=args.reid_feat_source,
                    csv_path=csv_path,
                    epoch=epoch,
                    arm=args.reid_feat_source,
                    k_thresh=_k_thresh,   # A-v2 M-B crowding stratification
                    seed=args.seed,       # gate-B: written to CSV seed col for pairing
                )
                print(f'  [benchmark] n_images={bench_metrics["n_images"]}  '
                      f'reid_rate={bench_metrics["reid_rate"]:.4f}  '
                      f'ε_β0={bench_metrics["epsilon_beta0"]:.4f}  '
                      f'SR={bench_metrics["success_rate"]:.4f}  '
                      f'clDice={bench_metrics.get("cldice_mean", float("nan")):.4f}')
            except Exception as exc:
                print(f'  [benchmark] eval failed: {exc}')

        write_state(state_path, epoch, train_loss, val_dice, best_dice, 'running',
                    benchmark_metrics=bench_metrics,
                    reid_feat_source=args.reid_feat_source)

        print(f'[epoch {epoch:03d}/{args.epochs}] '
              f'loss={train_loss:.4f}  val_dice={val_dice:.4f}  '
              f'best={best_dice:.4f}  {"*" if improved else ""}  '
              f'arm={arm_label}  ({elapsed:.1f}s)')

        # Smoke test: exit after 2 epochs
        if args.smoke and epoch >= 2:
            print('[smoke] 2-step smoke done — exiting.')
            write_state(state_path, epoch, train_loss, val_dice, best_dice, 'done',
                        reid_feat_source=args.reid_feat_source)
            return

        # Early stopping
        if no_improve >= args.patience:
            print(f'[train_reid_pilot] early stop at epoch {epoch} '
                  f'(no improvement for {args.patience} epochs)')
            break

    write_state(state_path, epoch, train_loss, val_dice, best_dice, 'done',
                reid_feat_source=args.reid_feat_source)
    print(f'[train_reid_pilot] done. arm={arm_label}  best_dice={best_dice:.4f}')
    print(f'[train_reid_pilot] To compute partial-corr verdict after both arms, run:')
    print(f'  python src/train_reid_pilot.py --partial_corr_only \\')
    print(f'      --state_a <A2_dir>/state.json --state_b <A0_dir>/state.json \\')
    print(f'      --csv_a <A2_dir>/reid_results.csv --csv_b <A0_dir>/reid_results.csv')


# --------------------------------------------------------------------------- #
#  Windows mandatory guard
# --------------------------------------------------------------------------- #

if __name__ == '__main__':
    main()
