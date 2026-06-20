"""
metrics.py — Vessel reconnection evaluation metrics for gdn2vessel benchmark.

Three metrics as defined in STORY_FRAMEWORK.md + PHASE_1_data_benchmark.md:

  1. ε_β0  (epsilon_beta0) — Connected-component error ratio
           ε_β0 = |β0_pred − β0_gt| / β0_gt
     where β0 counts connected components (0th Betti number).
     Measures topological fidelity: lower is better, 0 = perfect.
     Source: standard topological metric; plug-and-play arXiv 2404.10506 uses it.

  2. SR    (Success Rate / gap closure rate)
           SR = (N_gaps_before − N_gaps_remaining) / N_gaps_before
         = fraction of injected gaps that were successfully reconnected.
     "Gap remaining" detection: after prediction, dilate each gap centre disk
     and check if the predicted mask is still disconnected at that location.

  3. re-ID rate — Same-vessel reconnection accuracy (novel, Claim 2)
           re-ID = correct_same_root / N_gaps
     "Correct" = the reconnection at gap g bridges segment IDs seg_left and
     seg_right from GapRecord (i.e., the predicted mask re-connects the exact
     two vessel segments that were disconnected, not arbitrary other vessels).
     Logic borrowed from MOT IDF1: we match predicted connectivity to GT identity.

     Algorithm:
       For each gap g with (seg_left, seg_right):
         1. Dilate the gap centre region in the predicted mask.
         2. Check which vessel_segment_map labels are present in that region
            of the ORIGINAL GT mask (the "ground-truth identities").
         3. If both seg_left and seg_right appear (gap reconnected correctly)
            AND the predicted mask is connected at that location → correct.
       re-ID rate = correct / len(gaps)

NOTE on OMP / scipy import safety:
  β0 connectivity uses scipy.ndimage.label (pure C, no OpenMP conflict).
  We avoid scipy.stats everywhere (OMP Error #15 on Windows+PyTorch).

HPC pip requirements:
  numpy>=1.21
  scipy>=1.7     (scipy.ndimage.label only; NOT scipy.stats)
"""

from __future__ import annotations

from typing import List, Tuple

import numpy as np
from scipy.ndimage import label as ndlabel

from .synth_breaks import BreakResult, GapRecord


# --------------------------------------------------------------------------- #
#  1. ε_β0  — Connected-component error ratio
# --------------------------------------------------------------------------- #

def count_components(binary_mask: np.ndarray) -> int:
    """
    Count connected components (β0) in a binary mask.
    Uses 8-connectivity (diagonal links) for vessel masks.

    Args:
        binary_mask: (H, W) array with nonzero = foreground

    Returns:
        Integer count of connected components.
    """
    struct = np.ones((3, 3), dtype=np.int32)  # 8-connectivity
    _, n = ndlabel((binary_mask > 0).astype(np.int32), structure=struct)
    return int(n)


def epsilon_beta0(
    pred_mask: np.ndarray,
    gt_mask: np.ndarray,
) -> float:
    """
    ε_β0 = |β0_pred − β0_gt| / max(β0_gt, 1)

    Args:
        pred_mask: (H, W) predicted binary mask {0,1} or bool
        gt_mask:   (H, W) ground-truth binary mask {0,1} or bool

    Returns:
        ε_β0 (float, ≥ 0). Lower is better. 0 = perfect component count match.
    """
    b0_pred = count_components(pred_mask)
    b0_gt = count_components(gt_mask)
    return abs(b0_pred - b0_gt) / max(b0_gt, 1)


# --------------------------------------------------------------------------- #
#  2. SR — Gap closure / success rate
# --------------------------------------------------------------------------- #

def _is_gap_closed(
    pred_mask: np.ndarray,
    cy: int,
    cx: int,
    radius: int,
    check_radius_extra: int = 3,
) -> bool:
    """
    Determine whether a synthesised gap at (cy, cx) has been closed in pred_mask.

    Strategy: check if the predicted mask covers the centre of the erased zone.
    A gap is "closed" if the predicted mask has at least one foreground pixel
    within a disk of radius (radius + check_radius_extra) around the gap centre.

    Args:
        pred_mask:          (H, W) predicted binary mask
        cy, cx:             gap centre pixel
        radius:             the radius used when erasing the gap
        check_radius_extra: additional radius for leniency (accounts for slight
                            spatial offset in reconnection)

    Returns:
        True if gap is considered reconnected/closed.
    """
    h, w = pred_mask.shape
    r = radius + check_radius_extra
    y0, y1 = max(0, cy - r), min(h, cy + r + 1)
    x0, x1 = max(0, cx - r), min(w, cx + r + 1)
    patch = pred_mask[y0:y1, x0:x1]

    if patch.size == 0:
        return False

    # Build disk mask within patch
    ry, rx = np.ogrid[y0 - cy:y1 - cy, x0 - cx:x1 - cx]
    disk = (ry * ry + rx * rx) <= r * r
    return bool(np.any(patch[disk] > 0))


def success_rate(
    pred_mask: np.ndarray,
    break_result: BreakResult,
) -> float:
    """
    SR = (N_before − N_remaining) / N_before

    where N_before = len(break_result.gaps) = number of injected gaps,
    and N_remaining = number of gaps still open in pred_mask.

    Args:
        pred_mask:    (H, W) predicted binary mask after model reconnection
        break_result: BreakResult from apply_breaks (contains gap metadata)

    Returns:
        SR ∈ [0, 1]. 1.0 = all gaps closed.
    """
    gaps = break_result.gaps
    if len(gaps) == 0:
        return 1.0  # no gaps → trivially all closed

    n_closed = sum(
        1 for g in gaps
        if _is_gap_closed(pred_mask, g.center_yx[0], g.center_yx[1], g.radius)
    )
    return n_closed / len(gaps)


# --------------------------------------------------------------------------- #
#  3. re-ID rate — Same-vessel identity matching (Claim 2)
# --------------------------------------------------------------------------- #

def _check_reid_at_gap(
    pred_mask: np.ndarray,
    gt_vessel_segment_map: np.ndarray,
    gap: GapRecord,
    search_radius_extra: int = 4,
) -> bool:
    """
    Check if the prediction correctly re-identifies the same-root vessel at gap g.

    Algorithm (MOT IDF1-inspired):
      1. Look in the predicted mask around the gap centre (radius + extra).
      2. Find which GT vessel segment IDs (from vessel_segment_map) are present
         in that region AND have predicted foreground pixels → these are the
         "claimed" re-connections.
      3. Correct if both seg_left AND seg_right from GapRecord appear in the
         claimed set (meaning the prediction bridged the exact same two segments).

    Args:
        pred_mask:               (H, W) predicted binary mask
        gt_vessel_segment_map:   (H, W) int32 label map of original GT segments
        gap:                     GapRecord with seg_left, seg_right
        search_radius_extra:     extra search radius beyond gap radius

    Returns:
        True if the gap is correctly re-identified (same-root reconnection).
    """
    if gap.segment_id_left < 0:
        # Could not determine even one neighbouring segment → unknown (False)
        return False
    # Note: gap.segment_id_right == -1 is valid (single-segment internal gap);
    # handled below after computing claimed_segs.

    cy, cx = gap.center_yx
    r = gap.radius + search_radius_extra
    h, w = pred_mask.shape
    y0, y1 = max(0, cy - r), min(h, cy + r + 1)
    x0, x1 = max(0, cx - r), min(w, cx + r + 1)

    pred_patch = (pred_mask[y0:y1, x0:x1] > 0)
    seg_patch = gt_vessel_segment_map[y0:y1, x0:x1]

    if not np.any(pred_patch):
        return False  # prediction is empty at this gap → not reconnected

    # Build disk mask
    ry, rx = np.ogrid[y0 - cy:y1 - cy, x0 - cx:x1 - cx]
    disk = (ry * ry + rx * rx) <= r * r

    # GT segment IDs present under predicted foreground pixels within disk
    claimed_segs = set(seg_patch[pred_patch & disk].tolist())
    claimed_segs.discard(0)  # background

    if gap.segment_id_right < 0:
        # Single-segment gap: both sides belong to the same vessel root.
        # Correct if we see the one known segment ID in the prediction.
        correct = gap.segment_id_left in claimed_segs
    else:
        # Two-segment gap: must bridge both specific segments (MOT IDF1 strict).
        correct = (gap.segment_id_left in claimed_segs) and (gap.segment_id_right in claimed_segs)
    return correct


def reid_rate(
    pred_mask: np.ndarray,
    break_result: BreakResult,
) -> float:
    """
    re-ID rate = correct_same_root / N_gaps

    "Correct" means the model reconnected the exact pair of vessel segments that
    were disconnected (segment_id_left, segment_id_right in GapRecord).
    Borrowing MOT IDF1 logic: wrong reconnection (bridging a different vessel)
    is counted as 0, not as 0.5.

    Args:
        pred_mask:    (H, W) predicted binary mask
        break_result: BreakResult from apply_breaks

    Returns:
        re-ID rate ∈ [0, 1]. 1.0 = all gaps correctly re-identified to same root.
    """
    gaps = break_result.gaps
    if len(gaps) == 0:
        return 1.0

    n_correct = sum(
        1 for g in gaps
        if _check_reid_at_gap(pred_mask, break_result.vessel_segment_map, g)
    )
    return n_correct / len(gaps)


# --------------------------------------------------------------------------- #
#  Convenience: compute all three metrics at once
# --------------------------------------------------------------------------- #

def compute_all_metrics(
    pred_mask: np.ndarray,
    gt_mask: np.ndarray,
    break_result: BreakResult,
) -> dict:
    """
    Compute ε_β0, SR, and re-ID rate for a single prediction.

    Args:
        pred_mask:    (H, W) predicted binary mask after reconnection
        gt_mask:      (H, W) original GT mask (no breaks; used for β0 reference)
        break_result: BreakResult containing gap metadata + vessel_segment_map

    Returns:
        dict with keys: 'epsilon_beta0', 'success_rate', 'reid_rate',
                        'beta0_pred', 'beta0_gt', 'n_gaps',
                        'n_gaps_closed', 'n_gaps_reidentified'
    """
    b0_pred = count_components(pred_mask)
    b0_gt = count_components(gt_mask)
    eps_b0 = abs(b0_pred - b0_gt) / max(b0_gt, 1)

    gaps = break_result.gaps
    n_gaps = len(gaps)

    n_closed = sum(
        1 for g in gaps
        if _is_gap_closed(pred_mask, g.center_yx[0], g.center_yx[1], g.radius)
    )
    n_reidentified = sum(
        1 for g in gaps
        if _check_reid_at_gap(pred_mask, break_result.vessel_segment_map, g)
    )

    sr = n_closed / n_gaps if n_gaps > 0 else 1.0
    rr = n_reidentified / n_gaps if n_gaps > 0 else 1.0

    return {
        'epsilon_beta0': eps_b0,
        'beta0_pred': b0_pred,
        'beta0_gt': b0_gt,
        'success_rate': sr,
        'reid_rate': rr,
        'n_gaps': n_gaps,
        'n_gaps_closed': n_closed,
        'n_gaps_reidentified': n_reidentified,
    }
