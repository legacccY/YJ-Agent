"""
tools_topology.py — Wrappers for external topology evaluation libraries.

Wraps three open-source topology tools as callable functions:

  1. clDice (Centerline Dice)
     Source: github.com/jocpae/clDice
     Paper:  arXiv 1811.01885 (Shit et al., MICCAI 2021)
     Measures overlap of centerlines; standard vessel connectivity metric.

  2. Skeleton Recall
     Source: github.com/MIC-DKFZ/Skeleton-Recall
     Paper:  arXiv 2404.09729 (Kirchhoff et al., ECCV 2024)
     Recall on the GT skeleton; penalises missed thin vessel branches.

  3. Betti-Matching-3D
     Source: github.com/nstucki/Betti-Matching-3D
     Paper:  arXiv 2211.15914 (Stucki et al., ICLR 2023)
     Note:   Primarily designed for 3D; 2D usage requires shape (1, H, W) input.
             Computes Betti number matching loss — β0 + β1 topology errors.

# ============================================================================ #
# HPC pip install checklist (must be installed before using these wrappers):   #
# ============================================================================ #
#
#   # 1. clDice — pure Python, no C extension
#   pip install git+https://github.com/jocpae/clDice.git
#   # OR copy clDice/clDice/cldice.py and import directly (no package setup needed)
#
#   # 2. Skeleton Recall
#   pip install git+https://github.com/MIC-DKFZ/Skeleton-Recall.git
#   # Requires: scikit-image, numpy, torch (for loss variant)
#
#   # 3. Betti-Matching-3D
#   pip install git+https://github.com/nstucki/Betti-Matching-3D.git
#   # Requires: numpy, gudhi (persistent homology C++ backend)
#   # gudhi install: conda install -c conda-forge gudhi   OR   pip install gudhi
#   # NOTE: gudhi compilation may take ~5 min on HPC; pre-built conda pkg is faster.
#
#   # Supporting packages
#   pip install scikit-image numpy scipy
#
# ============================================================================ #

Each wrapper:
  - Accepts numpy (H, W) binary arrays (float or uint8 {0,1}).
  - Catches ImportError and raises RuntimeError with install instructions.
  - Has a standalone fallback for ε_β0 / skeleton recall that works without
    the external library for smoke-testing (marked with _fallback suffix).

"""

from __future__ import annotations

from typing import Optional, Tuple, Union

import numpy as np


# --------------------------------------------------------------------------- #
#  Type alias
# --------------------------------------------------------------------------- #
BinaryMask = np.ndarray  # (H, W) binary array, nonzero = foreground


# --------------------------------------------------------------------------- #
#  1. clDice
# --------------------------------------------------------------------------- #

def compute_cldice(
    pred: BinaryMask,
    gt: BinaryMask,
    iterations: int = 15,
) -> float:
    """
    Centerline Dice (clDice) between prediction and GT vessel mask.

    Requires: pip install git+https://github.com/jocpae/clDice.git

    Args:
        pred:       (H, W) predicted binary mask
        gt:         (H, W) GT binary mask
        iterations: morphological thinning iterations (default 15, per original)

    Returns:
        clDice score ∈ [0, 1]; higher is better.
    """
    try:
        # clDice repo exposes soft_skeletonize + soft_cldice or direct clDice
        # Try the most common import paths from the repo
        try:
            from clDice.cldice import clDice as _cldice_fn
        except ImportError:
            from cldice import clDice as _cldice_fn  # type: ignore

        pred_f = (pred > 0).astype(np.float32)
        gt_f = (gt > 0).astype(np.float32)
        score = _cldice_fn(pred_f, gt_f)
        return float(score)

    except ImportError as e:
        raise RuntimeError(
            "clDice not installed. Run:\n"
            "  pip install git+https://github.com/jocpae/clDice.git\n"
            f"Original error: {e}"
        ) from e


def compute_cldice_fallback(
    pred: BinaryMask,
    gt: BinaryMask,
) -> float:
    """
    Fallback clDice using skimage skeletonize (no external dep).
    Less accurate than the official thinning implementation but usable for
    smoke-testing without the clDice package.

    Returns clDice ∈ [0, 1].
    """
    from skimage.morphology import skeletonize

    pred_b = (pred > 0)
    gt_b = (gt > 0)

    skel_pred = skeletonize(pred_b)
    skel_gt = skeletonize(gt_b)

    # Sensitivity of pred skeleton on GT, precision of GT skeleton on pred
    # clDice = 2 * (Tprec * Tsens) / (Tprec + Tsens)
    tprec_num = np.sum(skel_pred & gt_b)
    tprec_den = np.sum(skel_pred)
    tsens_num = np.sum(skel_gt & pred_b)
    tsens_den = np.sum(skel_gt)

    tprec = tprec_num / max(tprec_den, 1)
    tsens = tsens_num / max(tsens_den, 1)

    if tprec + tsens == 0:
        return 0.0
    return float(2.0 * tprec * tsens / (tprec + tsens))


# --------------------------------------------------------------------------- #
#  2. Skeleton Recall
# --------------------------------------------------------------------------- #

def compute_skeleton_recall(
    pred: BinaryMask,
    gt: BinaryMask,
) -> float:
    """
    Skeleton Recall: fraction of GT skeleton pixels covered by the prediction.

    Requires: pip install git+https://github.com/MIC-DKFZ/Skeleton-Recall.git
    (or equivalently: the SkeletonRecall class from that repo)

    Args:
        pred: (H, W) predicted binary mask
        gt:   (H, W) GT binary mask

    Returns:
        Skeleton Recall ∈ [0, 1]; higher is better.
    """
    try:
        try:
            from skeleton_recall import SkeletonRecall  # primary import
        except ImportError:
            from Skeleton_Recall.skeleton_recall import SkeletonRecall  # type: ignore

        # SkeletonRecall expects torch tensors (B, C, H, W) or numpy (H, W)
        # Check the API; most versions accept numpy directly
        import torch
        pred_t = torch.from_numpy((pred > 0).astype(np.float32)).unsqueeze(0).unsqueeze(0)
        gt_t = torch.from_numpy((gt > 0).astype(np.float32)).unsqueeze(0).unsqueeze(0)

        metric = SkeletonRecall()
        score = metric(pred_t, gt_t)
        return float(score)

    except ImportError as e:
        raise RuntimeError(
            "Skeleton-Recall not installed. Run:\n"
            "  pip install git+https://github.com/MIC-DKFZ/Skeleton-Recall.git\n"
            f"Original error: {e}"
        ) from e


def compute_skeleton_recall_fallback(
    pred: BinaryMask,
    gt: BinaryMask,
) -> float:
    """
    Fallback Skeleton Recall using skimage skeletonize (no external dep).
    Recall = (GT_skeleton ∩ pred_foreground) / GT_skeleton_total

    Returns Skeleton Recall ∈ [0, 1].
    """
    from skimage.morphology import skeletonize

    gt_b = (gt > 0)
    pred_b = (pred > 0)
    skel_gt = skeletonize(gt_b)

    n_skel = int(np.sum(skel_gt))
    if n_skel == 0:
        return 1.0  # empty skeleton → trivially recalled
    n_covered = int(np.sum(skel_gt & pred_b))
    return n_covered / n_skel


# --------------------------------------------------------------------------- #
#  3. Betti-Matching-3D
# --------------------------------------------------------------------------- #

def compute_betti_matching(
    pred: BinaryMask,
    gt: BinaryMask,
    dim: int = 0,
) -> float:
    """
    Betti-Matching topology score (lower is better, 0 = perfect).

    Computes Betti number matching error for dimension `dim` (0=components, 1=loops).
    For 2D vessel masks, dim=0 (connected components) is most relevant.

    Requires:
      pip install git+https://github.com/nstucki/Betti-Matching-3D.git
      conda install -c conda-forge gudhi   # (or pip install gudhi)

    The Betti-Matching-3D library expects 3D inputs; 2D masks are treated as
    single-slice 3D volumes (shape (1, H, W)).

    Args:
        pred: (H, W) predicted binary mask
        gt:   (H, W) GT binary mask
        dim:  Betti dimension to evaluate (0 or 1)

    Returns:
        Betti matching error (float ≥ 0). Lower is better.
    """
    try:
        try:
            from betti_matching import BettiMatching  # primary module name
        except ImportError:
            import betti_matching_3d as BettiMatchingMod  # type: ignore
            BettiMatching = BettiMatchingMod.BettiMatching

        pred_3d = (pred > 0).astype(np.float32)[np.newaxis, :, :]  # (1, H, W)
        gt_3d = (gt > 0).astype(np.float32)[np.newaxis, :, :]

        bm = BettiMatching(pred_3d, gt_3d)
        error = bm.error(dim=dim)
        return float(error)

    except ImportError as e:
        raise RuntimeError(
            "Betti-Matching-3D not installed. Run:\n"
            "  pip install git+https://github.com/nstucki/Betti-Matching-3D.git\n"
            "  conda install -c conda-forge gudhi\n"
            f"Original error: {e}"
        ) from e


def compute_betti_matching_fallback(
    pred: BinaryMask,
    gt: BinaryMask,
) -> Tuple[int, int]:
    """
    Fallback Betti number difference (β0, β1) using scipy.ndimage and skimage.
    Does NOT do persistent-homology matching; just compares raw Betti numbers.
    Sufficient for smoke testing and preliminary results.

    Returns:
        (beta0_error, beta1_error) — absolute differences in β0, β1.
    """
    from scipy.ndimage import label as ndlabel
    from skimage.measure import euler_number

    def _b0(mask: np.ndarray) -> int:
        struct = np.ones((3, 3), dtype=np.int32)
        _, n = ndlabel((mask > 0).astype(np.int32), structure=struct)
        return int(n)

    def _b1(mask: np.ndarray) -> int:
        # β1 = loops; approximated via Euler characteristic for 2D binary image
        # χ = β0 - β1  (for binary 2D, ignoring higher dims)
        # skimage euler_number uses 8-connectivity by default
        chi = int(euler_number((mask > 0), connectivity=2))
        b0 = _b0(mask)
        return max(0, b0 - chi)  # β1 = β0 - χ

    b0_pred, b0_gt = _b0(pred), _b0(gt)
    b1_pred, b1_gt = _b1(pred), _b1(gt)
    return abs(b0_pred - b0_gt), abs(b1_pred - b1_gt)


# --------------------------------------------------------------------------- #
#  Convenience: topology suite (with graceful fallback)
# --------------------------------------------------------------------------- #

def compute_topology_suite(
    pred: BinaryMask,
    gt: BinaryMask,
    use_external: bool = True,
) -> dict:
    """
    Compute the full topology evaluation suite for one image pair.

    Tries external libraries first; falls back to pure-numpy/skimage
    implementations if libraries are not installed.

    Args:
        pred:         (H, W) predicted binary mask
        gt:           (H, W) GT binary mask
        use_external: If False, always use fallback (for testing without HPC libs)

    Returns:
        dict with keys: 'cldice', 'skeleton_recall', 'betti_b0_err', 'betti_b1_err',
                        'cldice_source', 'skeleton_recall_source', 'betti_source'
    """
    results: dict = {}

    # --- clDice ---
    if use_external:
        try:
            results['cldice'] = compute_cldice(pred, gt)
            results['cldice_source'] = 'official'
        except RuntimeError:
            results['cldice'] = compute_cldice_fallback(pred, gt)
            results['cldice_source'] = 'fallback_skimage'
    else:
        results['cldice'] = compute_cldice_fallback(pred, gt)
        results['cldice_source'] = 'fallback_skimage'

    # --- Skeleton Recall ---
    if use_external:
        try:
            results['skeleton_recall'] = compute_skeleton_recall(pred, gt)
            results['skeleton_recall_source'] = 'official'
        except RuntimeError:
            results['skeleton_recall'] = compute_skeleton_recall_fallback(pred, gt)
            results['skeleton_recall_source'] = 'fallback_skimage'
    else:
        results['skeleton_recall'] = compute_skeleton_recall_fallback(pred, gt)
        results['skeleton_recall_source'] = 'fallback_skimage'

    # --- Betti Matching ---
    if use_external:
        try:
            b0_err = compute_betti_matching(pred, gt, dim=0)
            b1_err = compute_betti_matching(pred, gt, dim=1)
            results['betti_b0_err'] = b0_err
            results['betti_b1_err'] = b1_err
            results['betti_source'] = 'official'
        except RuntimeError:
            b0_err, b1_err = compute_betti_matching_fallback(pred, gt)
            results['betti_b0_err'] = float(b0_err)
            results['betti_b1_err'] = float(b1_err)
            results['betti_source'] = 'fallback_scipy'
    else:
        b0_err, b1_err = compute_betti_matching_fallback(pred, gt)
        results['betti_b0_err'] = float(b0_err)
        results['betti_b1_err'] = float(b1_err)
        results['betti_source'] = 'fallback_scipy'

    return results
