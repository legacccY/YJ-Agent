"""Regenerate abcd_cache.csv from cache_deg.npy (exact pixels the model saw).

Why: the original abcd_cache was computed from cache_deg.npy (RGB array, 224x224),
NOT from the on-disk paired_dataset/*.jpg. Rebuilding from disk jpgs (reconstruct_p2_csv.py
STEP5) drifts for some images (jpeg recompression / resize interpolation), which moved
the eval AUC off the frozen 0.707. Verified: row50000 abcd_cache == extract_abcd(cache_deg[50000]
with BGR flip) to 4 decimals. cache_deg is stored RGB -> flip to BGR for cv2 ops.

Row alignment (verified): cache_deg row i == cache_meta row i == quality_labels_all row i
(q corr=1.0, mean abs diff=0 across all 149100 rows).

Output: data/abcd_cache.csv with degraded_path from quality_labels_all + A,B,C,D from cache_deg.
CPU-only, idempotent.
"""
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from tqdm import tqdm

ROOT = Path("D:/YJ-Agent")
DATA = ROOT / "data"
sys.path.insert(0, str(ROOT / "project"))
from models.feature_extractor import extract_abcd  # noqa: E402

CACHE_DEG = DATA / "cache_deg.npy"
QUAL_ALL = DATA / "quality_labels_all.csv"
OUT_ABCD = DATA / "abcd_cache.csv"


def otsu_mask(image_bgr: np.ndarray) -> np.ndarray:
    """Mirrors precompute_abcd.otsu_mask / reconstruct_p2_csv._otsu_mask."""
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    if mask.sum() < 0.02 * mask.size:
        H, W = mask.shape
        mask = np.zeros((H, W), dtype=np.uint8)
        cv2.ellipse(mask, (W // 2, H // 2), (W // 3, H // 3), 0, 0, 360, 255, -1)
    return mask.astype(bool)


def main():
    deg = np.load(CACHE_DEG, mmap_mode="r")  # (149100, 224, 224, 3) uint8 RGB
    qdf = pd.read_csv(QUAL_ALL)
    N = len(qdf)
    assert deg.shape[0] == N, f"row mismatch: cache_deg {deg.shape[0]} vs quality_labels_all {N}"

    paths = qdf["degraded_path"].tolist()
    rows = []
    for i in tqdm(range(N), desc="abcd from cache_deg", ncols=80):
        img_rgb = np.array(deg[i])           # RGB
        img_bgr = img_rgb[:, :, ::-1].copy()  # -> BGR (cv2 convention, matches original)
        mask = otsu_mask(img_bgr)
        A, B, C, D = extract_abcd(img_bgr, mask)
        rows.append((paths[i], float(A), float(B), float(C), float(D)))

    out = pd.DataFrame(rows, columns=["degraded_path", "A", "B", "C", "D"])
    out.to_csv(OUT_ABCD, index=False)
    print(f"Done: {len(out)} rows -> {OUT_ABCD}")


if __name__ == "__main__":
    main()
