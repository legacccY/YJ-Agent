"""
synth_breaks.py — Synthetic vessel disconnection protocol for gdn2vessel benchmark.

Protocol aligned with creatis plug-and-play-reco-regularization (arXiv 2404.10506,
github.com/creatis-myriad/plug-and-play-reco-regularization).

Key algorithm (from paper §3 + repo data_utils):
  1. Skeletonise the GT binary vessel mask to get 1-pixel-wide centreline.
  2. Sample a *target radius* i from the geometric distribution
         P(i) = 2^(p-i) / (2^p - 1),   i = 1 … p
     where p is the maximum radius parameter (we use p=4 per DRIVE/STARE σ=4).
  3. For each candidate break:
       a. Pick a random skeletal point that belongs to a sufficiently long segment
          (length > 2*s, where s is the gap size parameter).
       b. Erode a circular region of radius i around that skeletal point on the GT
          mask, producing a gap of diameter ≈ 2i pixels.
       c. Additionally dilate a Gaussian blur of width σ around the centre of
          the removed disk to model blurry low-contrast transitions (σ=4 for
          DRIVE/STARE as per paper).
  4. Record the gap metadata (centre, radius, gap_size s, two endpoint segment IDs).

Gaps per image:
  - DRIVE/STARE: 5 gaps per image (following creatis default; adjust n_breaks).
  - All four s values {6, 8, 10, 12} generate separate benchmark variants.

NOTE: We implement the radius-distribution sampling and disk erosion faithfully.
The exact σ-blur step (Gaussian smooth on boundary) is included as described.
The creatis repo does not publish a public __init__ package; this implementation
follows the paper description. If discrepancies are found with a future public
release, update accordingly and mark TODO below.

# TODO: Verify exact number of breaks per image (n_breaks) against official
#       creatis codebase if/when they publish a self-contained script. Paper
#       text leaves this as a hyperparameter; we default to 5.

HPC pip requirements (add to requirements.txt or install before running):
  scikit-image>=0.19.0   (skeletonize via skimage.morphology)
  opencv-python>=4.5.0   (connected components, disk erosion via cv2)
  numpy>=1.21
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from skimage.morphology import skeletonize

# --------------------------------------------------------------------------- #
#  Protocol constants (DRIVE / STARE default per arXiv 2404.10506)
# --------------------------------------------------------------------------- #

# Gap size options (s): diameter of erased segment in pixels
GAP_SIZES = (6, 8, 10, 12)          # s ∈ {6, 8, 10, 12}

# Max radius parameter p (σ=4 ≈ p=4 for DRIVE/STARE).
# P(i) = 2^(p-i)/(2^p-1) → radius distribution biased toward thin vessels.
MAX_RADIUS_P = 4

# Gaussian sigma for boundary blurring (models low-contrast transitions)
SIGMA_BOUNDARY = 4.0                 # σ=4 for DRIVE/STARE

# Default number of breaks injected per image
DEFAULT_N_BREAKS = 5


# --------------------------------------------------------------------------- #
#  Data classes
# --------------------------------------------------------------------------- #

@dataclass
class GapRecord:
    """Metadata for a single synthesised gap."""
    gap_id: int           # sequential index within this image
    center_yx: Tuple[int, int]       # (row, col) of gap centre on skeleton
    radius: int           # sampled radius i from P(i)
    gap_size: int         # s value used
    sigma: float          # Gaussian sigma used for boundary blur
    segment_id_left: int  # vessel segment id on left/top side of gap
    segment_id_right: int # vessel segment id on right/bottom side of gap
    # segment IDs are labels from scipy.ndimage.label on the broken skeleton;
    # the two dominant neighbours of the erased zone are stored.


@dataclass
class BreakResult:
    """Output of apply_breaks for a single mask."""
    mask_broken: np.ndarray            # (H, W) uint8 {0,1} vessel mask with gaps
    gaps: List[GapRecord] = field(default_factory=list)
    vessel_segment_map: np.ndarray = field(default_factory=lambda: np.zeros((1,1), dtype=np.int32))
    # vessel_segment_map: (H, W) int32 — each connected vessel segment on the
    # original (unbroken) mask has a unique positive integer label. Used by
    # re-ID evaluation to determine if a reconnection matched the correct vessel.


# --------------------------------------------------------------------------- #
#  Internal helpers
# --------------------------------------------------------------------------- #

def _sample_radius(p: int, rng: np.random.Generator) -> int:
    """Sample radius i ∈ {1, …, p} from P(i) = 2^(p-i) / (2^p - 1)."""
    denom = 2**p - 1
    probs = np.array([2**(p - i) / denom for i in range(1, p + 1)], dtype=np.float64)
    # Normalise (should already sum to 1, but guard floating-point drift)
    probs /= probs.sum()
    return int(rng.choice(np.arange(1, p + 1), p=probs))


def _disk_mask(radius: int) -> np.ndarray:
    """Return a bool (2r+1, 2r+1) filled disk structuring element."""
    d = 2 * radius + 1
    y, x = np.ogrid[-radius:radius + 1, -radius:radius + 1]
    return (x * x + y * y) <= radius * radius


def _erase_disk(mask: np.ndarray, cy: int, cx: int, radius: int) -> np.ndarray:
    """
    Zero-out a disk of given radius centred at (cy, cx) in binary mask.
    Returns modified copy (does NOT modify in-place).
    """
    out = mask.copy()
    h, w = out.shape
    disk = _disk_mask(radius)
    r = radius
    # Clamp to image boundary
    y0, y1 = max(0, cy - r), min(h, cy + r + 1)
    x0, x1 = max(0, cx - r), min(w, cx + r + 1)
    dy0, dy1 = y0 - (cy - r), y1 - (cy - r)
    dx0, dx1 = x0 - (cx - r), x1 - (cx - r)
    out[y0:y1, x0:x1][disk[dy0:dy1, dx0:dx1]] = 0
    return out


def _apply_boundary_blur(mask: np.ndarray, cy: int, cx: int,
                         radius: int, sigma: float) -> np.ndarray:
    """
    Erase a disk of pixels and smooth the boundary to simulate low-contrast
    vessel transitions (described in arXiv 2404.10506 §3).

    Protocol:
      1. Hard-erase the central disk (radius r) — guarantees gap pixels removed.
      2. Apply Gaussian blur only to the transition ring just outside the disk
         (radius r+1 … r + ring_width), attenuating the boundary smoothly.

    Returns float32 array; caller binarises at threshold 0.5.
    The hard erase in step 1 is lossless (values set to 0), so pixels inside
    the disk will always be 0 in the output regardless of sigma.
    """
    mask_f = mask.astype(np.float32)

    # Step 1: hard erase — set disk interior to 0
    hard_erased = _erase_disk(mask_f.astype(np.uint8), cy, cx, radius).astype(np.float32)

    # Step 2: Gaussian blur on the hard-erased mask to soften the boundary ring.
    # Use a sigma-proportional kernel, but capped so it doesn't fill the erased zone.
    # We use a smaller effective sigma for the blend (sigma/2) to keep the
    # boundary smear local and avoid restoring the centre.
    blur_sigma = max(0.5, sigma / 2.0)
    ksize = int(4 * blur_sigma) | 1   # ~2-sigma-wide kernel, always odd
    ksize = max(ksize, 3)
    blurred = cv2.GaussianBlur(hard_erased, (ksize, ksize), blur_sigma)

    # Build a "keep hard erase" mask: inside disk → keep 0 (hard erase wins),
    # outside disk → use blurred value (smooth boundary).
    h, w = mask_f.shape
    r = radius
    y0, y1 = max(0, cy - r), min(h, cy + r + 1)
    x0, x1 = max(0, cx - r), min(w, cx + r + 1)
    disk = _disk_mask(r)
    dy0, dy1 = y0 - (cy - r), y1 - (cy - r)
    dx0, dx1 = x0 - (cx - r), x1 - (cx - r)

    result = blurred.copy()
    # Force erased disk to stay 0 regardless of blur diffusion
    result[y0:y1, x0:x1][disk[dy0:dy1, dx0:dx1]] = 0.0

    return result


def _find_segment_neighbours(
    vessel_segment_map: np.ndarray,
    cy: int, cx: int,
    radius: int,
) -> Tuple[int, int]:
    """
    Find the two dominant GT vessel segment IDs that border the gap centre.

    Uses the vessel_segment_map (ndlabel on the full GT binary mask) rather
    than skeleton labels, so the IDs are in the same label space as those
    stored in BreakResult.vessel_segment_map and used by _check_reid_at_gap.

    Search strategy: look in a ring of width +3 pixels outside the erased disk;
    collect all GT segment IDs in that ring that are foreground in the map.

    Returns (seg_left, seg_right) where seg_right = -1 if only one segment
    is found (single-branch internal gap — both sides are the same vessel root).
    """
    h, w = vessel_segment_map.shape
    r_search = radius + 5   # search ring slightly outside erased zone
    y0, y1 = max(0, cy - r_search), min(h, cy + r_search + 1)
    x0, x1 = max(0, cx - r_search), min(w, cx + r_search + 1)

    region_labels = vessel_segment_map[y0:y1, x0:x1]

    # Build ring mask: annulus between radius and r_search
    cy_local = cy - y0
    cx_local = cx - x0
    ry, rx = np.mgrid[0:y1 - y0, 0:x1 - x0]
    dist2 = (ry - cy_local) ** 2 + (rx - cx_local) ** 2
    # Ring: outside erased disk (dist > radius) but within search zone
    ring_mask = (dist2 > radius ** 2) & (dist2 <= r_search ** 2)

    seg_ids = region_labels[ring_mask]
    seg_ids = seg_ids[seg_ids > 0]

    if len(seg_ids) == 0:
        return -1, -1

    unique, counts = np.unique(seg_ids, return_counts=True)
    sorted_idx = np.argsort(-counts)
    seg_left = int(unique[sorted_idx[0]])
    seg_right = int(unique[sorted_idx[1]]) if len(unique) > 1 else -1
    return seg_left, seg_right


# --------------------------------------------------------------------------- #
#  Public API
# --------------------------------------------------------------------------- #

def apply_breaks(
    gt_mask: np.ndarray,
    gap_size: int = 8,
    n_breaks: int = DEFAULT_N_BREAKS,
    p: int = MAX_RADIUS_P,
    sigma: float = SIGMA_BOUNDARY,
    seed: Optional[int] = None,
    min_segment_len: int = 20,
) -> BreakResult:
    """
    Synthesise artificial vessel disconnections in a binary GT mask.

    Protocol aligned with arXiv 2404.10506 (creatis plug-and-play):
      - Radius sampled from P(i) = 2^(p-i)/(2^p-1)
      - Disk erasure at skeletal point with gap_size ≥ 2*radius constraint
      - Gaussian boundary blur (sigma) to model low-contrast transitions
      - Records per-gap vessel segment IDs for re-ID evaluation

    Args:
        gt_mask:          (H, W) binary array {0, 1} or bool — original GT mask.
        gap_size:         s ∈ {6, 8, 10, 12}; approximate gap diameter.
        n_breaks:         Number of gaps to inject per image.
        p:                Max radius parameter; radius drawn from {1,…,p}.
        sigma:            Gaussian boundary blur sigma (pixels).
        seed:             Random seed for reproducibility (fixed seed → same gaps).
        min_segment_len:  Minimum skeleton branch length to be eligible for a gap.

    Returns:
        BreakResult with:
          - mask_broken:        (H, W) uint8 {0,1} — mask with gaps applied
          - gaps:               list of GapRecord (one per successfully placed gap)
          - vessel_segment_map: (H, W) int32 — per-pixel original vessel segment id
    """
    if seed is not None:
        rng = np.random.default_rng(seed)
    else:
        rng = np.random.default_rng()

    gt = (gt_mask > 0).astype(np.uint8)

    # --- Step 1: label original connected vessel segments (before any break) ---
    from scipy.ndimage import label as ndlabel
    vessel_segment_map, _ = ndlabel(gt)
    vessel_segment_map = vessel_segment_map.astype(np.int32)

    # --- Step 2: skeletonise ---
    skeleton = skeletonize(gt.astype(bool)).astype(bool)

    # --- Step 3: label skeleton segments for neighbour lookup ---
    skel_labels, _ = ndlabel(skeleton)
    skel_labels = skel_labels.astype(np.int32)

    # Collect eligible skeletal pixels (long enough segment, away from boundary)
    skel_yx = np.argwhere(skeleton)   # (N, 2)
    h, w = gt.shape
    margin = gap_size + p + int(3 * sigma) + 2
    eligible_mask = (
        (skel_yx[:, 0] >= margin) & (skel_yx[:, 0] < h - margin) &
        (skel_yx[:, 1] >= margin) & (skel_yx[:, 1] < w - margin)
    )
    eligible_yx = skel_yx[eligible_mask]

    if len(eligible_yx) == 0:
        # No eligible pixels → return unchanged mask
        return BreakResult(
            mask_broken=gt.copy(),
            gaps=[],
            vessel_segment_map=vessel_segment_map,
        )

    # --- Step 4: iteratively place breaks ---
    current_mask = gt.copy()
    current_skeleton = skeleton.copy()
    gaps: List[GapRecord] = []
    used_centres: List[Tuple[int, int]] = []

    # Shuffle eligible pool
    idx_order = rng.permutation(len(eligible_yx))
    ptr = 0
    gap_id = 0

    while gap_id < n_breaks and ptr < len(eligible_yx):
        cy, cx = int(eligible_yx[idx_order[ptr], 0]), int(eligible_yx[idx_order[ptr], 1])
        ptr += 1

        # Skip if not on current (living) skeleton (previous gaps may have removed it)
        if not current_skeleton[cy, cx]:
            continue

        # Skip if too close to a previous break centre
        too_close = any(
            abs(cy - prev_y) < gap_size + 2 * p and abs(cx - prev_x) < gap_size + 2 * p
            for prev_y, prev_x in used_centres
        )
        if too_close:
            continue

        # Sample radius
        r = _sample_radius(p, rng)
        # Ensure gap_size is consistent: r <= gap_size // 2 (otherwise gap is tiny)
        r = min(r, max(1, gap_size // 2))

        # Find neighbouring segment IDs before erasing.
        # Use vessel_segment_map (GT mask label space) so seg IDs match those
        # stored in BreakResult and queried in _check_reid_at_gap.
        seg_left, seg_right = _find_segment_neighbours(
            vessel_segment_map,
            cy, cx, r,
        )

        # Apply soft Gaussian-blurred erosion → binarise at 0.5
        mask_soft = _apply_boundary_blur(current_mask, cy, cx, r, sigma)
        current_mask = (mask_soft >= 0.5).astype(np.uint8)

        # Update skeleton: erase the same region on skeleton
        current_skeleton = _erase_disk(current_skeleton.astype(np.uint8), cy, cx, r).astype(bool)

        used_centres.append((cy, cx))
        gaps.append(GapRecord(
            gap_id=gap_id,
            center_yx=(cy, cx),
            radius=r,
            gap_size=gap_size,
            sigma=sigma,
            segment_id_left=seg_left,
            segment_id_right=seg_right,
        ))
        gap_id += 1

    return BreakResult(
        mask_broken=current_mask,
        gaps=gaps,
        vessel_segment_map=vessel_segment_map,
    )


def apply_breaks_all_severities(
    gt_mask: np.ndarray,
    gap_sizes: Tuple[int, ...] = GAP_SIZES,
    n_breaks: int = DEFAULT_N_BREAKS,
    p: int = MAX_RADIUS_P,
    sigma: float = SIGMA_BOUNDARY,
    base_seed: int = 42,
) -> Dict[int, BreakResult]:
    """
    Apply breaks for all gap_size values in gap_sizes, each with its own
    reproducible seed derived from base_seed.

    Returns dict mapping gap_size → BreakResult.
    """
    results: Dict[int, BreakResult] = {}
    for i, s in enumerate(gap_sizes):
        results[s] = apply_breaks(
            gt_mask,
            gap_size=s,
            n_breaks=n_breaks,
            p=p,
            sigma=sigma,
            seed=base_seed + i * 1000,
        )
    return results
