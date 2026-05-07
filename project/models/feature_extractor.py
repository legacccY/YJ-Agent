"""ABCD Feature Extractor for skin lesion images.

Computes 4 interpretable features from a segmentation mask + image:
  A - Asymmetry:    1 - symmetry_score (higher = more asymmetric)
  B - Border:       edge irregularity index (higher = more irregular border)
  C - Color:        color diversity score (higher = more color variation)
  D - Diameter:     relative lesion size (area fraction of image)

All features are normalized to [0, 1].

Reference: Abbasi et al. (2004), dermoscopy ABCD rule.
"""

import cv2
import numpy as np
import torch


def _symmetry_score(mask: np.ndarray) -> float:
    """Vertical + horizontal symmetry of the lesion shape."""
    if mask.sum() == 0:
        return 0.0
    mask_u8 = mask.astype(np.uint8)
    flip_v = np.flipud(mask_u8)
    flip_h = np.fliplr(mask_u8)
    sym_v = np.logical_and(mask_u8, flip_v).sum() / (mask_u8.sum() + 1e-8)
    sym_h = np.logical_and(mask_u8, flip_h).sum() / (mask_u8.sum() + 1e-8)
    return float((sym_v + sym_h) / 2.0)


def _border_irregularity(mask: np.ndarray) -> float:
    """Compactness-based border irregularity: higher = more irregular."""
    contours, _ = cv2.findContours(
        mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    if not contours:
        return 0.0
    contour = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(contour)
    perimeter = cv2.arcLength(contour, closed=True)
    if area < 1 or perimeter < 1:
        return 0.0
    # Polsby–Popper compactness: circle = 1, irregular = <1
    compactness = 4 * np.pi * area / (perimeter ** 2)
    irregularity = 1.0 - float(np.clip(compactness, 0.0, 1.0))
    return irregularity


def _color_diversity(image_bgr: np.ndarray, mask: np.ndarray) -> float:
    """Std of hue values inside lesion, normalized to [0, 1]."""
    if mask.sum() == 0:
        return 0.0
    hsv = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2HSV)
    hue = hsv[:, :, 0][mask].astype(float)  # [0, 180]
    std = float(hue.std())
    return float(np.clip(std / 90.0, 0.0, 1.0))  # normalize by half-range


def _relative_diameter(mask: np.ndarray) -> float:
    """Lesion area as a fraction of total image area."""
    total = mask.size
    if total == 0:
        return 0.0
    return float(np.clip(mask.sum() / total, 0.0, 1.0))


def extract_abcd(image_bgr: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Compute ABCD feature vector from image and mask.

    Args:
        image_bgr: BGR image, shape (H, W, 3), dtype uint8.
        mask: Binary lesion mask, shape (H, W), dtype bool.
    Returns:
        features: np.ndarray of shape (4,), values in [0, 1].
                  [asymmetry, border_irregularity, color_diversity, diameter]
    """
    A = 1.0 - _symmetry_score(mask)     # asymmetry
    B = _border_irregularity(mask)       # border irregularity
    C = _color_diversity(image_bgr, mask)
    D = _relative_diameter(mask)

    return np.array([A, B, C, D], dtype=np.float32)


def extract_abcd_tensor(
    image_bgr: np.ndarray,
    mask: np.ndarray,
    device: torch.device | None = None,
) -> torch.Tensor:
    """Return ABCD features as a torch.Tensor of shape (4,)."""
    feats = extract_abcd(image_bgr, mask)
    t = torch.from_numpy(feats)
    if device is not None:
        t = t.to(device)
    return t
