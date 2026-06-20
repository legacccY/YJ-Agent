"""
metrics.py — Vessel reconnection evaluation metrics for gdn2vessel benchmark.

Metric suite overview:

 ── creatis protocol (arXiv 2404.10506) ──────────────────────────────────────
  DSC   Dice Similarity Coefficient: 2|A∩B| / (|A|+|B|)
  ASSD  Average Symmetric Surface Distance: (mean_d(pred→gt) + mean_d(gt→pred))/2
  ε_β0  Component-count error ratio: |β0_pred − β0_gt| / max(β0_gt, 1)

 ── standard cross-validation metrics (Entry 9, L2/L6) ──────────────────────
  Betti-err  Topological error: β0_err + β1_err
               β0_err = |β0_pred − β0_gt|   (component count)
               β1_err = |β1_pred − β1_gt|   (loop count; β1 = β0 − χ, χ = euler_number)
             Source: standard algebraic topology / Betti numbers.
             Purpose: cross-validate SR against a label-free topology metric.

  APLS  Average Path Length Similarity (SpaceNet metric).
        Formula from CosmiQ/apls (github.com/CosmiQ/apls, SpaceNet-3 challenge):
          single_path_metric(len_gt, len_prop) = min(1, |len_gt − len_prop| / len_gt)
            (missing path → 1; zero-length gt → 0)
          APLS = 1 − mean_{(s,t) in GT control pairs, len_gt≥min_len}(
                       mean( sim_gt→prop, sim_prop→gt ) )
        Implementation: skeleton→networkx graph (8-connected, Euclidean edge weights)
        → all_pairs_dijkstra → GT control nodes sampled at stride → nearest-node
        mapping into opposing graph for symmetric evaluation.
        Dependency: networkx (stdlib-compatible; already installed on HPC).

 ── this paper's custom gap-level metrics ────────────────────────────────────
  SR      gap-closure rate (NOT a creatis metric)
  re-ID   same-vessel reconnection rate (NOT a creatis metric)

NOTE on OMP / scipy import safety:
  All scipy usage here is scipy.ndimage (pure C, no OpenMP conflict).
  scipy.stats is NEVER imported (OMP Error #15 on Windows+PyTorch).

HPC pip requirements:
  numpy>=1.21
  scipy>=1.7        (scipy.ndimage only; NOT scipy.stats)
  scikit-image>=0.19 (skeletonize, euler_number)
  networkx>=2.6     (APLS skeleton graph)
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy.ndimage import label as ndlabel, distance_transform_edt

from .synth_breaks import BreakResult, GapRecord


# --------------------------------------------------------------------------- #
#  0. DSC — Dice Similarity Coefficient (creatis metric #1)
# --------------------------------------------------------------------------- #

def dice_coefficient(
    pred_mask: np.ndarray,
    gt_mask: np.ndarray,
) -> float:
    """
    DSC = 2 * |pred ∩ gt| / (|pred| + |gt|)

    Standard binary segmentation overlap metric.
    Returns 1.0 if both masks are empty (no vessel pixels).

    Args:
        pred_mask: (H, W) predicted binary mask {0,1} or bool
        gt_mask:   (H, W) ground-truth binary mask {0,1} or bool

    Returns:
        DSC ∈ [0, 1]. Higher is better. 1.0 = perfect overlap.
    """
    pred = (pred_mask > 0)
    gt = (gt_mask > 0)
    intersection = np.logical_and(pred, gt).sum()
    denom = pred.sum() + gt.sum()
    if denom == 0:
        return 1.0  # both empty → trivially perfect
    return float(2 * intersection / denom)


# --------------------------------------------------------------------------- #
#  0b. ASSD — Average Symmetric Surface Distance (creatis metric #2)
# --------------------------------------------------------------------------- #

def _surface_pixels(binary_mask: np.ndarray) -> np.ndarray:
    """
    Extract foreground surface (boundary) pixels of a binary mask.
    A foreground pixel is a surface pixel if it has at least one background
    neighbour (4-connectivity).

    Returns boolean mask of same shape, True = surface pixel.
    """
    from scipy.ndimage import binary_erosion
    struct4 = np.array([[0, 1, 0],
                        [1, 1, 1],
                        [0, 1, 0]], dtype=bool)
    eroded = binary_erosion(binary_mask > 0, structure=struct4, border_value=0)
    return (binary_mask > 0) & ~eroded


def assd(
    pred_mask: np.ndarray,
    gt_mask: np.ndarray,
) -> float:
    """
    ASSD = (mean_d(pred_surface → gt) + mean_d(gt_surface → pred)) / 2

    Computes average symmetric surface distance using scipy.ndimage
    distance_transform_edt (Euclidean distance transform).
    No scipy.stats import — safe on Windows+PyTorch (no OMP Error #15).

    Returns 0.0 if both masks are empty.
    Returns inf if one mask is empty and the other is not
    (undefined surface, degenerate case).

    Args:
        pred_mask: (H, W) predicted binary mask {0,1} or bool
        gt_mask:   (H, W) ground-truth binary mask {0,1} or bool

    Returns:
        ASSD in pixels (float). Lower is better. 0.0 = perfect surface match.
    """
    pred = (pred_mask > 0).astype(np.uint8)
    gt = (gt_mask > 0).astype(np.uint8)

    # Degenerate cases
    if pred.sum() == 0 and gt.sum() == 0:
        return 0.0
    if pred.sum() == 0 or gt.sum() == 0:
        return float('inf')

    # Surface pixels of each mask
    pred_surf = _surface_pixels(pred)
    gt_surf = _surface_pixels(gt)

    # Distance transform: for each pixel, distance to nearest foreground pixel
    # distance_transform_edt on the *complement* gives distance to nearest fg
    dist_pred_to_gt = distance_transform_edt(~(gt > 0))    # dist from every pixel to nearest gt fg
    dist_gt_to_pred = distance_transform_edt(~(pred > 0))  # dist from every pixel to nearest pred fg

    # Mean surface distance in each direction
    d_pred_surf_to_gt = dist_pred_to_gt[pred_surf].mean() if pred_surf.sum() > 0 else 0.0
    d_gt_surf_to_pred = dist_gt_to_pred[gt_surf].mean() if gt_surf.sum() > 0 else 0.0

    return float((d_pred_surf_to_gt + d_gt_surf_to_pred) / 2.0)


# --------------------------------------------------------------------------- #
#  1. ε_β0  — Connected-component error ratio (creatis metric #3)
# --------------------------------------------------------------------------- #
# NOTE: count_components (β0) is also used by betti_error below.
#       Defined here first so both functions can share it.

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
#  1b. Betti-err — Topological error (standard cross-validation, Entry 9 L2/L6)
# --------------------------------------------------------------------------- #
#
#  Betti numbers (2D binary mask):
#    β0 = number of connected components       (count_components above)
#    β1 = number of loops (independent cycles)
#
#  2D Euler-Poincaré characteristic:  χ = β0 − β1
#  => β1 = β0 − χ
#
#  skimage.measure.euler_number(mask, connectivity=1) returns χ using
#  4-connectivity Euler formula (standard for 2D binary images).
#  connectivity=1 ↔ 4-connected foreground (consistent with β0 via 8-connected
#  background complement is 4-connected — Jordan curve theorem analogue).
#
#  Reference: Euler characteristic / Betti numbers — standard algebraic topology.
#  skimage source: https://github.com/scikit-image/scikit-image


def count_loops(binary_mask: np.ndarray) -> int:
    """
    Count β1 (number of topological loops / independent cycles) in a 2D binary mask.

    Formula: β1 = β0 − χ
    where β0 = connected components (count_components, 8-connectivity)
    and   χ  = euler_number(mask, connectivity=1) from skimage.measure.

    Args:
        binary_mask: (H, W) array with nonzero = foreground

    Returns:
        β1 as non-negative integer (loops count). Clamped ≥ 0 (β1 ≥ 0 always).
    """
    from skimage.measure import euler_number as skimage_euler
    mask_bin = (binary_mask > 0).astype(np.int32)
    b0 = count_components(mask_bin)
    chi = int(skimage_euler(mask_bin, connectivity=1))
    # β1 = β0 - χ; must be non-negative by definition
    return max(0, b0 - chi)


def betti_error(
    pred_mask: np.ndarray,
    gt_mask: np.ndarray,
) -> dict:
    """
    Betti-number topological error between pred and GT masks.

    Returns absolute differences in β0 (components) and β1 (loops), plus total.

    Formula:
        β0_err = |β0_pred − β0_gt|
        β1_err = |β1_pred − β1_gt|
        betti_err_total = β0_err + β1_err

    Used as a standard label-free topology metric to cross-validate the paper's
    SR metric and prevent reviewer criticism of "self-validating custom metric".
    Source: standard algebraic topology (Betti numbers), no proprietary formula.

    Args:
        pred_mask: (H, W) predicted binary mask {0,1} or bool
        gt_mask:   (H, W) ground-truth binary mask {0,1} or bool

    Returns:
        dict with keys:
          'beta0_pred', 'beta0_gt', 'beta0_err'
          'beta1_pred', 'beta1_gt', 'beta1_err'
          'betti_err_total'
    """
    b0_pred = count_components(pred_mask)
    b0_gt   = count_components(gt_mask)
    b1_pred = count_loops(pred_mask)
    b1_gt   = count_loops(gt_mask)

    b0_err = abs(b0_pred - b0_gt)
    b1_err = abs(b1_pred - b1_gt)

    return {
        'beta0_pred': b0_pred,
        'beta0_gt':   b0_gt,
        'beta0_err':  b0_err,
        'beta1_pred': b1_pred,
        'beta1_gt':   b1_gt,
        'beta1_err':  b1_err,
        'betti_err_total': b0_err + b1_err,
    }


# --------------------------------------------------------------------------- #
#  1c. APLS — Average Path Length Similarity (standard cross-validation)
# --------------------------------------------------------------------------- #
#
#  Official formula from CosmiQ/apls (github.com/CosmiQ/apls):
#    single_path_metric(len_gt, len_prop):
#      if len_gt <= 0: return 0
#      if len_prop < 0: return diff_max (= 1.0)    # missing path
#      return min(diff_max, |len_gt - len_prop| / len_gt)
#
#    APLS = 1 - mean(single_path_metric over all GT control-node pairs
#                    where len_gt >= min_path_length)
#    Symmetric version: average of GT→Prop and Prop→GT directions.
#
#  Binary-image adaptation (vs GeoJSON in original SpaceNet):
#    1. Skeletonize both masks → pixel-level skeleton.
#    2. Build networkx graph: skeleton pixel = node; 8-connected edges with
#       Euclidean weight (1.0 for axis, √2 for diagonal).
#    3. Compute all_pairs_dijkstra_path_length on GT graph.
#    4. Map GT control nodes to nearest node in Prop skeleton (KD-tree).
#    5. Compute Prop all_pairs_dijkstra and evaluate symmetric APLS.
#
#  This adaptation follows the standard approach for binary vessel/road images
#  (used in clDice, DRIVE topology evaluations). The core formula is identical
#  to the official SpaceNet APLS.
#
#  Dependency: networkx (must be installed; `pip install networkx`)


def _skeleton_to_graph(skel: np.ndarray):
    """
    Convert a binary skeleton image to a networkx Graph.

    Nodes: each foreground pixel, identified by (row, col) tuple.
    Edges: 8-connected neighbours with Euclidean weights (1.0 or √2).

    Args:
        skel: (H, W) boolean skeleton image.

    Returns:
        (G, node_list) where G is nx.Graph and node_list is list of (y, x) tuples.
    """
    try:
        import networkx as nx
    except ImportError:
        raise ImportError(
            "networkx is required for APLS. Install with: pip install networkx"
        )

    yx_list = [tuple(p) for p in np.argwhere(skel)]
    if len(yx_list) == 0:
        return nx.Graph(), []

    node_idx: Dict[tuple, int] = {yx: i for i, yx in enumerate(yx_list)}
    G = nx.Graph()
    G.add_nodes_from(range(len(yx_list)))

    for (y, x), nid in node_idx.items():
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                nb = (y + dy, x + dx)
                if nb in node_idx:
                    w = 1.0 if (dy == 0 or dx == 0) else float(np.sqrt(2))
                    nid_nb = node_idx[nb]
                    if not G.has_edge(nid, nid_nb):
                        G.add_edge(nid, nid_nb, weight=w)

    return G, yx_list


def _map_nodes_to_graph(
    source_yx: List[tuple],
    target_yx: List[tuple],
) -> Dict[int, int]:
    """
    For each node index in source_yx, find the nearest node in target_yx.
    Returns dict: source_node_idx → target_node_idx.
    Uses pure numpy (no scipy.spatial.KDTree — avoids scipy.stats proximity).
    """
    if len(source_yx) == 0 or len(target_yx) == 0:
        return {}
    src = np.array(source_yx, dtype=np.float32)   # (Ns, 2)
    tgt = np.array(target_yx, dtype=np.float32)   # (Nt, 2)
    # Batch nearest-neighbour via broadcast; O(Ns*Nt) — fine for skeleton sizes
    mapping: Dict[int, int] = {}
    for i, s in enumerate(src):
        dists = np.sum((tgt - s) ** 2, axis=1)
        mapping[i] = int(np.argmin(dists))
    return mapping


def _single_path_metric(len_gt: float, len_prop: float, diff_max: float = 1.0) -> float:
    """
    Official CosmiQ single_path_metric formula:
      if len_gt <= 0: return 0
      if len_prop < 0: return diff_max   (missing path)
      return min(diff_max, |len_gt - len_prop| / len_gt)

    Source: github.com/CosmiQ/apls, apls.py line 1886-1915.
    """
    if len_gt <= 0:
        return 0.0
    if len_prop < 0:
        return diff_max
    return float(min(diff_max, abs(len_gt - len_prop) / len_gt))


def _apls_one_direction(
    all_pairs_gt: Dict[int, Dict[int, float]],
    all_pairs_prop: Dict[int, Dict[int, float]],
    gt_to_prop_map: Dict[int, int],
    min_path_length: float,
    diff_max: float = 1.0,
) -> float:
    """
    Compute APLS score for one direction (GT→Prop).

    For each (start, end) pair in GT with len_gt >= min_path_length:
      - Map start→start_prop, end→end_prop via gt_to_prop_map.
      - Look up len_prop = all_pairs_prop[start_prop][end_prop] (−1 if missing).
      - Accumulate single_path_metric.

    Returns 1 - mean(diffs), or 0.0 if no valid pairs.
    """
    diffs = []
    for start_gt, paths in all_pairs_gt.items():
        start_prop = gt_to_prop_map.get(start_gt)
        if start_prop is None:
            # GT start node has no mapping → all its paths score diff_max
            for end_gt, len_gt in paths.items():
                if end_gt == start_gt:
                    continue
                if len_gt < min_path_length:
                    continue
                diffs.append(diff_max)
            continue

        prop_paths = all_pairs_prop.get(start_prop, {})
        for end_gt, len_gt in paths.items():
            if end_gt == start_gt:
                continue
            if len_gt < min_path_length:
                continue
            end_prop = gt_to_prop_map.get(end_gt)
            if end_prop is None:
                len_prop = -1.0  # missing
            else:
                len_prop = prop_paths.get(end_prop, -1.0)
            diffs.append(_single_path_metric(len_gt, len_prop, diff_max))

    if len(diffs) == 0:
        return 0.0
    return float(1.0 - np.mean(diffs))


def apls(
    pred_mask: np.ndarray,
    gt_mask: np.ndarray,
    min_path_length: float = 10.0,
    control_node_stride: int = 5,
) -> float:
    """
    APLS — Average Path Length Similarity.

    Computes the symmetric APLS score between pred and GT binary vessel masks.
    Formula: official SpaceNet APLS (CosmiQ/apls, SpaceNet-3 challenge).

    Algorithm:
      1. Skeletonize both masks.
      2. Build networkx skeleton graphs with Euclidean edge weights.
      3. Sample control nodes from GT skeleton at stride (reduces O(n^2) cost).
      4. Compute all_pairs_dijkstra for GT and Prop graphs.
      5. Map GT↔Prop nodes by nearest pixel; evaluate symmetric APLS.
      6. APLS = (APLS_gt_onto_prop + APLS_prop_onto_gt) / 2

    Args:
        pred_mask:            (H, W) predicted binary mask {0,1} or bool
        gt_mask:              (H, W) GT binary mask {0,1} or bool
        min_path_length:      Minimum GT path length to consider (pixels).
                              Default=10.0 (per CosmiQ apls.py default).
        control_node_stride:  Sample every Nth GT skeleton node as control node.
                              Reduces computation on large skeletons. Default=5.

    Returns:
        APLS ∈ [0, 1]. Higher is better. 1.0 = perfect path-length match.
        Returns 0.0 if GT skeleton is empty.
        Returns nan if networkx is not installed.

    Reference:
        github.com/CosmiQ/apls — functions single_path_metric, path_sim_metric,
        compute_apls_metric (lines 1886–2085).
        Blog: https://medium.com/the-downlinq/spacenet-road-detection-and-routing-challenge-part-ii-apls-implementation-92acd86f4094
    """
    try:
        import networkx as nx
    except ImportError:
        # TODO: install networkx on HPC before evaluating APLS
        return float('nan')

    from skimage.morphology import skeletonize as _skel

    gt_bin  = (gt_mask > 0).astype(bool)
    pred_bin = (pred_mask > 0).astype(bool)

    gt_skel   = _skel(gt_bin)
    pred_skel = _skel(pred_bin)

    G_gt,   yx_gt   = _skeleton_to_graph(gt_skel)
    G_prop, yx_prop = _skeleton_to_graph(pred_skel)

    if len(yx_gt) == 0:
        return 0.0   # no GT skeleton → undefined (return 0 per CosmiQ convention)
    if len(yx_prop) == 0:
        return 0.0   # no Prop skeleton → all paths missing → APLS = 1 - 1 = 0

    # Sample control nodes from GT at stride to reduce O(n^2) computation
    control_gt = list(range(0, len(yx_gt), control_node_stride))
    if len(control_gt) == 0:
        control_gt = [0]

    # All-pairs shortest path (weighted Euclidean)
    all_pairs_gt   = dict(nx.all_pairs_dijkstra_path_length(G_gt,   weight='weight'))
    all_pairs_prop = dict(nx.all_pairs_dijkstra_path_length(G_prop, weight='weight'))

    # Node mapping: GT pixel coords → nearest Prop pixel, and vice versa
    gt_to_prop = _map_nodes_to_graph(yx_gt, yx_prop)
    prop_to_gt = _map_nodes_to_graph(yx_prop, yx_gt)

    # Restrict GT all_pairs to control nodes only (direction: GT→Prop)
    all_pairs_gt_ctrl: Dict[int, Dict[int, float]] = {
        s: {e: d for e, d in paths.items() if e in control_gt}
        for s, paths in all_pairs_gt.items()
        if s in control_gt
    }

    # Symmetric: GT→Prop and Prop→GT
    # For Prop→GT direction, use prop nodes mapped back to GT coords
    apls_gt_onto_prop = _apls_one_direction(
        all_pairs_gt_ctrl, all_pairs_prop, gt_to_prop, min_path_length
    )

    # Build Prop control nodes as the mapped-from-GT set
    prop_ctrl = list(set(gt_to_prop[n] for n in control_gt if n in gt_to_prop))
    all_pairs_prop_ctrl: Dict[int, Dict[int, float]] = {
        s: {e: d for e, d in paths.items() if e in prop_ctrl}
        for s, paths in all_pairs_prop.items()
        if s in prop_ctrl
    }

    apls_prop_onto_gt = _apls_one_direction(
        all_pairs_prop_ctrl, all_pairs_gt, prop_to_gt, min_path_length
    )

    return float((apls_gt_onto_prop + apls_prop_onto_gt) / 2.0)


# --------------------------------------------------------------------------- #
#  2. SR — Gap closure / success rate  [THIS PAPER'S CUSTOM METRIC]
#  NOTE: SR is NOT a creatis metric. creatis uses DSC/ASSD/ε_β0 only.
#        SR is a novel gap-level metric contributed by this paper, using
#        per-gap GapRecord metadata from synth_breaks.apply_breaks().
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
#  Convenience: compute full metric suite at once
# --------------------------------------------------------------------------- #

def compute_all_metrics(
    pred_mask: np.ndarray,
    gt_mask: np.ndarray,
    break_result: BreakResult,
    compute_assd: bool = True,
    compute_apls: bool = False,
    apls_min_path_length: float = 10.0,
    apls_control_stride: int = 5,
) -> dict:
    """
    Compute the full metric suite for a single prediction.

    Metric groups:
      creatis protocol  — DSC / ASSD / ε_β0  (arXiv 2404.10506)
      standard cross-   — Betti-err (β0_err + β1_err) / APLS  (Entry 9, L2/L6)
      this paper custom — SR (gap-closure rate) / re-ID rate

    Args:
        pred_mask:           (H, W) predicted binary mask after reconnection
        gt_mask:             (H, W) original GT mask (no breaks; used as reference)
        break_result:        BreakResult containing gap metadata + vessel_segment_map
        compute_assd:        if False, skip ASSD (slow on large images). Default True.
        compute_apls:        if False, skip APLS (skeleton graph, slow). Default False.
                             Enable for final benchmark evaluation; disable for training.
        apls_min_path_length: min GT path length for APLS evaluation (default 10.0 px).
        apls_control_stride: stride for GT control node sampling in APLS (default 5).

    Returns:
        dict with keys:
          creatis           — 'dsc', 'assd', 'epsilon_beta0'
          standard cross    — 'betti_err_total', 'beta0_err', 'beta1_err',
                               'beta1_pred', 'beta1_gt', 'apls'
          this paper custom — 'success_rate', 'reid_rate'
          auxiliary         — 'beta0_pred', 'beta0_gt', 'n_gaps',
                               'n_gaps_closed', 'n_gaps_reidentified'

    NOTE: SR and re-ID rate are this paper's custom metrics, not from creatis or SpaceNet.
    """
    # --- DSC (creatis metric #1) ---
    dsc = dice_coefficient(pred_mask, gt_mask)

    # --- ASSD (creatis metric #2) ---
    assd_val = assd(pred_mask, gt_mask) if compute_assd else float('nan')

    # --- ε_β0 (creatis metric #3) ---
    b0_pred = count_components(pred_mask)
    b0_gt   = count_components(gt_mask)
    eps_b0  = abs(b0_pred - b0_gt) / max(b0_gt, 1)

    # --- Betti-err (standard cross-validation, Entry 9) ---
    be = betti_error(pred_mask, gt_mask)
    # be already contains beta0_pred, beta0_gt (redundant but consistent with be dict)

    # --- APLS (standard cross-validation, Entry 9) ---
    apls_val = (
        apls(pred_mask, gt_mask,
             min_path_length=apls_min_path_length,
             control_node_stride=apls_control_stride)
        if compute_apls else float('nan')
    )

    # --- SR and re-ID (this paper's custom gap-level metrics) ---
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
        # creatis three-metric protocol (arXiv 2404.10506)
        'dsc':            dsc,
        'assd':           assd_val,
        'epsilon_beta0':  eps_b0,
        # standard cross-validation metrics (Entry 9, L2/L6)
        'betti_err_total': be['betti_err_total'],
        'beta0_err':       be['beta0_err'],
        'beta1_err':       be['beta1_err'],
        'beta1_pred':      be['beta1_pred'],
        'beta1_gt':        be['beta1_gt'],
        'apls':            apls_val,
        # this paper's custom gap-level metrics (NOT creatis / NOT SpaceNet)
        'success_rate':   sr,    # gap-closure rate
        'reid_rate':      rr,    # same-vessel reconnection
        # auxiliary
        'beta0_pred':     b0_pred,
        'beta0_gt':       b0_gt,
        'n_gaps':         n_gaps,
        'n_gaps_closed':  n_closed,
        'n_gaps_reidentified': n_reidentified,
    }
