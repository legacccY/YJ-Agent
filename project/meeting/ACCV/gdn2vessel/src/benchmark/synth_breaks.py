"""
synth_breaks.py — Synthetic vessel disconnection protocol for gdn2vessel benchmark.

Core algorithm aligned EXACTLY with creatis plug-and-play-reco-regularization:
  arXiv 2404.10506, github.com/creatis-myriad/plug-and-play-reco-regularization
  Function: create_disconnections() in data_utils (researcher-verified source).

Official parameters (from example.py):
  nb_deco=100, size_deco_max=8, noise_level=200

Severity grid (this paper):
  Easy   : size_max=6,  nb_deco=100   — paper extension
  Medium : size_max=8,  nb_deco=100   — ALIGNED with creatis (size_deco_max=8)
  Hard   : size_max=10, nb_deco=100   — paper extension
  Extreme: size_max=12, nb_deco=100   — paper extension

NOTE: Medium is the only severity anchored to creatis official params.
Easy/Hard/Extreme are this paper's extensions. Marked in code comments.

Re-ID label infrastructure (GapRecord / seg_left / seg_right) is this paper's
addition on top of the creatis protocol.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy.ndimage import distance_transform_bf, label as ndlabel
from skimage.filters import gaussian
from skimage.morphology import skeletonize

# --------------------------------------------------------------------------- #
#  Severity grid
# --------------------------------------------------------------------------- #
# NOTE: size_max=8 / nb_deco=100 == creatis official (size_deco_max=8, nb_deco=100)
# Easy / Hard / Extreme are *this paper's extensions*; not from creatis.
SEVERITY_GRID = {
    'Easy':    dict(size_max=6,  nb_deco=100),   # paper extension
    'Medium':  dict(size_max=8,  nb_deco=100),   # aligned with creatis official
    'Hard':    dict(size_max=10, nb_deco=100),   # paper extension
    'Extreme': dict(size_max=12, nb_deco=100),   # paper extension
}

# Official sigma for gaussian smoothing (create_artefact std_gauss arg passed
# from create_disconnections is 0.8, not the default 0.7 in the signature).
_SIGMA_GAUSS = 0.8   # official: create_disconnections passes 0.8 to create_artefact

# --------------------------------------------------------------------------- #
#  Data classes (public API — do NOT change field names; re-ID code depends on them)
# --------------------------------------------------------------------------- #

@dataclass
class GapRecord:
    """Metadata for a single synthesised gap."""
    gap_id: int                          # sequential index within this image
    center_yx: Tuple[int, int]           # (row, col) of gap centre on skeleton
    radius: int                          # taille_disk used (disk radius, pixels)
    gap_size: int                        # size_max parameter used
    sigma: float                         # gaussian sigma used (always 0.8 per creatis)
    segment_id_left: int                 # GT vessel segment id left of gap
    segment_id_right: int                # GT vessel segment id right of gap
    # segment IDs: labels from scipy.ndimage.label on original GT mask.
    # Two dominant GT-segment neighbours of the erased zone stored here.


@dataclass
class BreakResult:
    """Output of apply_breaks for a single mask."""
    mask_broken: np.ndarray              # (H, W) uint8 {0,1} — mask with gaps
    gaps: List[GapRecord] = field(default_factory=list)
    vessel_segment_map: np.ndarray = field(
        default_factory=lambda: np.zeros((1, 1), dtype=np.int32)
    )
    # vessel_segment_map: (H, W) int32 — per-pixel original vessel segment label.
    # Used by re-ID evaluation to check whether reconnection matched correct vessel.


# --------------------------------------------------------------------------- #
#  creatis internal helpers — aligned line-by-line to official repo
# --------------------------------------------------------------------------- #

def _disc(img: np.ndarray, x: int, y: int, pixel_radius: int) -> np.ndarray:
    """
    Hand-written solid disk (circle fill).
    Exact copy of creatis `disc()` function:
      for i in range(x-r, x+r+1):
          r = sqrt(R^2 - (i-x)^2)
          for j in range(y-r, y+r+1): img[i,j]=1
    Boundary-safe version.
    """
    h, w = img.shape
    for i in range(x - pixel_radius, x + pixel_radius + 1):
        if i < 0 or i >= h:
            continue
        r_row = int(np.sqrt(max(0, pixel_radius ** 2 - (i - x) ** 2)))
        for j in range(y - r_row, y + r_row + 1):
            if 0 <= j < w:
                img[i, j] = 1
    return img


def _create_artefact(
    disconnect: np.ndarray,
    pos_x: int,
    pos_y: int,
    size_disk: int,
    mean_pix: int,
    std_pix: float,
    std_gauss: float = 0.7,
) -> np.ndarray:
    """
    Create erasure artefact at position (pos_x, pos_y).
    Exact translation of creatis `create_artefact()`:
      1. Draw solid disk of radius size_disk.
      2. Randomly sample mean_pix pixels inside disk (sparse mask).
      3. Gaussian-smooth the sparse mask (sigma=std_gauss).
      4. Threshold at >0.4 to get final binary artefact.

    NOTE: official create_disconnections calls this with std_gauss=0.8 (not
    the default 0.7 in the signature). Callers must pass 0.8 explicitly.
    """
    image = np.zeros(disconnect.shape, dtype=np.float64)
    image = _disc(image, pos_x, pos_y, size_disk)

    coords = np.nonzero(image == 1)
    number_pixels = int(np.random.normal(mean_pix, scale=std_pix))
    if number_pixels <= 0:
        number_pixels = 1

    if number_pixels < len(coords[0]):
        random_position = np.random.randint(len(coords[0]), size=number_pixels)
        artefact = np.zeros(image.shape)
        artefact[coords[0][random_position], coords[1][random_position]] = 1
    else:
        artefact = np.zeros(image.shape)
        artefact[coords[0], coords[1]] = 1

    # gaussian from skimage.filters; std_gauss=0.8 passed by create_disconnections
    artefact = (gaussian(artefact, sigma=std_gauss) > 0.4) * 1.0
    return artefact


def _create_disconnections(
    ground_truth: np.ndarray,
    nb_disconnection: int,
    size_max: int,
    rng_seed: Optional[int] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Core disconnection algorithm — exact translation of creatis
    `create_disconnections(groundTruth, nb_disconnection, size_max)`.

    Steps (line-by-line from official repo):
      1. distance_transform_bf (chessboard) on GT.
      2. Skeletonise GT; mask distance map to skeleton only.
      3. Collect unique distance values (vessel thickness tiers).
      4. Build urns (lists of pixel coords) per tier; keep only 3 finest tiers.
      5. Exponential probability distribution over urns (thinner = higher prob).
      6. For each of nb_disconnection draws:
           - Pick urn by probability; sample random point (with replacement).
           - taille_disk = Normal(size_max // vessel_size, scale=4), clipped ≥0.
           - nb_pix_max = sum of pixels in disk(taille_disk).
           - dense ∈ {0,1} uniform; sparse or dense pixel count.
           - call create_artefact with std_gauss=0.8.
           - accumulate: image -= artifact, disconnections += artifact.
      7. Binarise at ≥0.1.

    Args:
        ground_truth:     (H, W) binary mask {0,1}.
        nb_disconnection: number of erasure samples (official default=100).
        size_max:         maximum gap size parameter (official default=8).
        rng_seed:         optional seed for numpy.random (for reproducibility).

    Returns:
        (image, disconnections):
          image         — (H, W) float64, binarised at ≥0.1 (GT minus erasures).
          disconnections — (H, W) float64, binarised at ≥0.1 (sum of all artefacts).
    """
    if rng_seed is not None:
        np.random.seed(rng_seed)

    ground_truth = ground_truth.astype(np.float64)

    # --- Step 1-2: distance map on skeleton only ---
    distance_map = distance_transform_bf(ground_truth, 'chessboard')
    skelet = skeletonize(ground_truth.astype(bool)).astype(np.float64)
    distance_map = skelet * distance_map  # mask to skeleton pixels only

    # --- Step 3-4: collect urns (coord lists per thickness tier) ---
    max_vessel_size = np.unique(distance_map)
    # max_vessel_size[0] == 0.0 (background); skip it
    urns = []
    for i in max_vessel_size[1:]:
        coords_i = np.nonzero(distance_map == i)
        if len(coords_i[0]) != 0:
            urns.append(np.stack(coords_i, axis=-1))   # shape (N, 2)
    urns = urns[:3]  # keep only 3 finest vessel tiers (thinnest = most breakable)
    nb_urns = len(urns)

    if nb_urns == 0:
        # Degenerate: no skeletal pixels found (e.g. all-black mask)
        image = (ground_truth >= 0.1) * 1.0
        disconnections = np.zeros(ground_truth.shape)
        return image, disconnections

    # --- Step 5: exponential cumulative probabilities ---
    # P(urn i) = 2^(nb_urns - (i+1)) / (2^nb_urns - 1)
    proba_urns = [0.0]
    for i in range(nb_urns):
        last = proba_urns[-1]
        prob_cum = last + (2 ** (nb_urns - (i + 1))) / ((2 ** nb_urns) - 1)
        proba_urns.append(prob_cum)

    # --- Step 6: draw nb_disconnection samples ---
    drawn_urns = np.random.rand(nb_disconnection)
    image = ground_truth.copy()
    disconnections = np.zeros(image.shape)

    for i in range(len(proba_urns) - 1):
        # Samples that fall into urn i's probability bin
        category = (
            (drawn_urns > proba_urns[i]) & (drawn_urns <= proba_urns[i + 1])
        ).astype(int)
        number_drawn_urn = int(np.sum(category))
        if number_drawn_urn == 0:
            continue

        vessel_size = max_vessel_size[i + 1]  # thickness tier value
        mean_deco_size = size_max // int(vessel_size)
        # taille_disk: expected disk radius; Normal(mean, scale=4), clipped ≥0
        taille_disk_samples = np.random.normal(mean_deco_size, scale=4,
                                               size=number_drawn_urn)

        # Pick random points from this urn (with replacement, per official code)
        point_disconnect = np.random.randint(len(urns[i]), size=number_drawn_urn)

        disconnect = np.zeros(image.shape)
        for k_idx, j in enumerate(point_disconnect):
            taille_disk = abs(int(taille_disk_samples[k_idx]))
            if taille_disk == 0:
                continue  # zero-radius disk: nothing to erase

            from skimage.morphology import disk as skimage_disk
            nb_pix_max = int(np.sum(skimage_disk(taille_disk)))

            # dense=1: denser artefact; dense=0: sparser
            dense = np.random.randint(0, 2)
            if dense == 1:
                nb_pix = abs(int(np.random.normal(nb_pix_max // 2,
                                                   scale=nb_pix_max // 4 or 1)))
            else:
                nb_pix = abs(int(np.random.normal(nb_pix_max // 4,
                                                   scale=nb_pix_max // 8 or 1)))

            # pos_x, pos_y: row, col of chosen skeletal point
            pos_x = int(urns[i][j][0])
            pos_y = int(urns[i][j][1])

            artifact = _create_artefact(
                disconnect, pos_x, pos_y, taille_disk, nb_pix,
                std_pix=1.0,       # official passes 1 (mean_pix arg used as mean_pix)
                std_gauss=_SIGMA_GAUSS,   # 0.8 per official create_disconnections call
            )
            disconnect = disconnect + artifact

        image = image - disconnect
        disconnections = disconnections + disconnect

    # --- Step 7: binarise ---
    image = (image >= 0.1) * 1.0
    disconnections = (disconnections >= 0.1) * 1.0
    return image, disconnections


# --------------------------------------------------------------------------- #
#  re-ID label helpers (this paper's addition on top of creatis protocol)
# --------------------------------------------------------------------------- #

def _find_segment_neighbours(
    vessel_segment_map: np.ndarray,
    cy: int,
    cx: int,
    search_radius: int = 12,
) -> Tuple[int, int]:
    """
    Find the two dominant GT vessel segment IDs that border a gap centre (cy, cx).
    Search in a ring of pixels within search_radius of the gap centre.

    Uses vessel_segment_map (ndlabel on original GT) so IDs are consistent
    with BreakResult.vessel_segment_map used by the re-ID evaluator.

    Returns (seg_left, seg_right); seg_right=-1 if only one segment found.
    """
    h, w = vessel_segment_map.shape
    r = search_radius
    y0, y1 = max(0, cy - r), min(h, cy + r + 1)
    x0, x1 = max(0, cx - r), min(w, cx + r + 1)

    region = vessel_segment_map[y0:y1, x0:x1]
    cy_loc = cy - y0
    cx_loc = cx - x0
    ry, rx = np.mgrid[0:y1 - y0, 0:x1 - x0]
    dist2 = (ry - cy_loc) ** 2 + (rx - cx_loc) ** 2
    ring_mask = dist2 <= r ** 2

    seg_ids = region[ring_mask]
    seg_ids = seg_ids[seg_ids > 0]
    if len(seg_ids) == 0:
        return -1, -1

    unique, counts = np.unique(seg_ids, return_counts=True)
    order = np.argsort(-counts)
    seg_left = int(unique[order[0]])
    seg_right = int(unique[order[1]]) if len(unique) > 1 else -1
    return seg_left, seg_right


def _extract_gap_records(
    ground_truth: np.ndarray,
    disconnections: np.ndarray,
    vessel_segment_map: np.ndarray,
    size_max: int,
) -> List[GapRecord]:
    """
    Post-process the disconnections mask to extract per-gap GapRecord metadata.

    Strategy: label connected components of the disconnections mask. Each
    component is one gap region. Record centre, approximate radius (from
    bounding box), and neighbouring GT segment IDs.

    This is a this-paper addition — creatis does not produce per-gap records.
    """
    struct8 = np.ones((3, 3), dtype=np.int32)
    labeled, n_gaps = ndlabel((disconnections > 0).astype(np.int32),
                               structure=struct8)
    records: List[GapRecord] = []
    for gap_id in range(1, n_gaps + 1):
        coords = np.argwhere(labeled == gap_id)
        if len(coords) == 0:
            continue
        cy = int(np.mean(coords[:, 0]))
        cx = int(np.mean(coords[:, 1]))
        # Approximate radius from half-diagonal of bounding box
        rr = max(1, int(np.max(np.max(coords, axis=0) - np.min(coords, axis=0)) // 2))
        seg_l, seg_r = _find_segment_neighbours(vessel_segment_map, cy, cx, rr + 8)
        records.append(GapRecord(
            gap_id=gap_id - 1,
            center_yx=(cy, cx),
            radius=rr,
            gap_size=size_max,
            sigma=_SIGMA_GAUSS,
            segment_id_left=seg_l,
            segment_id_right=seg_r,
        ))
    return records


# --------------------------------------------------------------------------- #
#  Public API
# --------------------------------------------------------------------------- #

def apply_breaks(
    gt_mask: np.ndarray,
    gap_size: int = 8,
    nb_deco: int = 100,
    seed: Optional[int] = None,
) -> BreakResult:
    """
    Synthesise artificial vessel disconnections in a binary GT mask.

    Core algorithm is an exact translation of creatis create_disconnections().
    See module docstring for parameter-level alignment notes.

    Severity anchoring (this paper):
      gap_size=8, nb_deco=100  →  Medium  (aligned with creatis official)
      Other gap_size values are this paper's extensions.

    Args:
        gt_mask:  (H, W) binary array {0,1} or bool — original GT mask.
        gap_size: size_max parameter (controls expected disk radius). Default=8.
        nb_deco:  nb_disconnection — number of erasure draws. Default=100.
        seed:     Random seed for reproducibility (same seed → same gaps).

    Returns:
        BreakResult:
          mask_broken:       (H, W) uint8 {0,1} — GT mask with gaps removed.
          gaps:              List[GapRecord] — per-gap metadata for re-ID eval.
          vessel_segment_map: (H, W) int32 — original GT segment labels.

    Zero-leakage assertion: mask_broken pixels that were 0 in gt_mask are
    still 0 (no hallucinated vessels). Enforced after binarisation.
    """
    gt = (gt_mask > 0).astype(np.float64)

    # --- Label original connected vessel segments (before any break) ---
    struct8 = np.ones((3, 3), dtype=np.int32)
    vessel_segment_map, _ = ndlabel(gt.astype(np.int32), structure=struct8)
    vessel_segment_map = vessel_segment_map.astype(np.int32)

    # --- Run creatis algorithm ---
    mask_float, disconnections = _create_disconnections(
        gt, nb_disconnection=nb_deco, size_max=gap_size, rng_seed=seed
    )

    mask_broken = mask_float.astype(np.uint8)

    # Zero-leakage assertion: mask_broken must be subset of original GT
    assert np.all(mask_broken[gt == 0] == 0), (
        "Zero-leakage violated: mask_broken has foreground pixels absent in GT"
    )

    # --- Extract per-gap metadata for re-ID evaluation ---
    gaps = _extract_gap_records(gt, disconnections, vessel_segment_map, gap_size)

    return BreakResult(
        mask_broken=mask_broken,
        gaps=gaps,
        vessel_segment_map=vessel_segment_map,
    )


def apply_breaks_all_severities(
    gt_mask: np.ndarray,
    base_seed: int = 42,
) -> Dict[str, BreakResult]:
    """
    Apply breaks for all severity levels (Easy/Medium/Hard/Extreme).
    Each severity gets a reproducible seed derived from base_seed.

    Medium is aligned with creatis official (size_max=8, nb_deco=100).
    Easy/Hard/Extreme are this paper's extensions.

    Returns dict mapping severity_name → BreakResult.
    """
    results: Dict[str, BreakResult] = {}
    for i, (severity, params) in enumerate(SEVERITY_GRID.items()):
        results[severity] = apply_breaks(
            gt_mask,
            gap_size=params['size_max'],
            nb_deco=params['nb_deco'],
            seed=base_seed + i * 1000,
        )
    return results
