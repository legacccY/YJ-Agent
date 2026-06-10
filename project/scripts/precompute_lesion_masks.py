#!/usr/bin/env python
"""Precompute lesion-region masks for mask-weighted L1 (v6 mask-L1).

WHY classical segmentation, not classifier Grad-CAM:
  Smoke (2026-06-10) falsified ResNet-50 Grad-CAM: on dermoscopy it fires on corner
  vignette / peripheral skin texture (classic ISIC shortcut), NOT the lesion. A mask that
  misses the lesion would make mask-L1 protect the wrong pixels -> wasted multi-day run.
  Dermoscopy lesions are a central, darker blob -> classical segmentation localises them
  far more reliably, with zero model dependency and no circularity with the B3 eval probe.

Three-tier pipeline (validated failure-to-safe-fallback ~1% on 300-image sample):
  1. Otsu on LAB-L (inverted) + central-largest connected component   (~87% handled)
  2. GrabCut with central-box init (OpenCV, no download)               (recovers ~12%)
  3. Central Gaussian prior (safe: lesions are central)                (~1% residual)
  A mask of 0 degenerates mask-L1 to plain L1 (no harm), so even tier-3 cannot hurt.

Alignment: mask saved at out-size (== training img_size, default 256), pixel-aligned with
  x_ref (original plain-resized to 256). No center crop anywhere.

Output: one uint8 PNG per unique isic_id in OUT_DIR (0-255 = lesion weight).
  Train-time: L1_w = L1 * (1 + lambda_mask * (mask/255)).

Usage (smoke): python project/scripts/precompute_lesion_masks.py \
  --labels-csv data/quality_labels_nocrop.csv --out-dir data/lesion_masks --limit 20 --debug-overlay
Usage (full):  same without --limit (runs on CPU, ~mins for 49700).
"""
import argparse
from pathlib import Path

import cv2
import numpy as np

OUT = 256


def _ok(m: np.ndarray) -> bool:
    """Accept mask if coverage in [2%,60%] and centroid within 0.55 of center radius."""
    cov = m.mean()
    if not (0.02 <= cov <= 0.60):
        return False
    h, w = m.shape
    ys, xs = np.mgrid[0:h, 0:w]
    tot = m.sum() + 1e-6
    d = (((m * ys).sum() / tot - h / 2) ** 2 + ((m * xs).sum() / tot - w / 2) ** 2) ** 0.5 / (h / 2)
    return d <= 0.55


def _otsu(bgr: np.ndarray) -> np.ndarray:
    L = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)[:, :, 0]
    Lb = cv2.GaussianBlur(L, (0, 0), 3)
    _, th = cv2.threshold(Lb, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    th = cv2.morphologyEx(th, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
    n, lbl, stats, cent = cv2.connectedComponentsWithStats(th)
    best, bs = 0, -1.0
    h, w = bgr.shape[:2]
    for i in range(1, n):
        a = stats[i, cv2.CC_STAT_AREA]
        if a < 256:
            continue
        cy, cx = cent[i]
        d = ((cy - h / 2) ** 2 + (cx - w / 2) ** 2) ** 0.5
        s = a / (1 + d)               # large + central preferred
        if s > bs:
            bs, best = s, i
    return (lbl == best).astype(np.float32) if best > 0 else np.zeros((h, w), np.float32)


def _grabcut(bgr: np.ndarray) -> np.ndarray:
    h, w = bgr.shape[:2]
    mask = np.zeros((h, w), np.uint8)
    bgd = np.zeros((1, 65), np.float64)
    fgd = np.zeros((1, 65), np.float64)
    rect = (int(0.15 * w), int(0.15 * h), int(0.70 * w), int(0.70 * h))
    try:
        cv2.grabCut(bgr, mask, rect, bgd, fgd, 5, cv2.GC_INIT_WITH_RECT)
    except Exception:
        return np.zeros((h, w), np.float32)
    m = np.where((mask == 1) | (mask == 3), 1.0, 0.0).astype(np.float32)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    return m


def _central_gaussian(h: int, w: int, sigma_frac: float = 0.28) -> np.ndarray:
    ys, xs = np.mgrid[0:h, 0:w]
    s = sigma_frac * h
    g = np.exp(-(((ys - h / 2) ** 2 + (xs - w / 2) ** 2) / (2 * s * s)))
    return g.astype(np.float32)        # soft [0,1], peak 1 at center


def lesion_mask(bgr: np.ndarray) -> tuple[np.ndarray, str]:
    """Return (mask[0,1], tier) for a 256x256 BGR image."""
    m = _otsu(bgr)
    if _ok(m):
        # soft-dilate the hard mask so the L1 weight has a gradient at the boundary
        m = cv2.GaussianBlur(m, (0, 0), 5)
        return m / (m.max() + 1e-6), "otsu"
    m = _grabcut(bgr)
    if _ok(m):
        m = cv2.GaussianBlur(m, (0, 0), 5)
        return m / (m.max() + 1e-6), "grabcut"
    return _central_gaussian(*bgr.shape[:2]), "gaussian"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels-csv", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--out-size", type=int, default=OUT)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--debug-overlay", action="store_true")
    ap.add_argument("--shard", type=int, default=0, help="this shard index [0,nshards)")
    ap.add_argument("--nshards", type=int, default=1, help="run N parallel procs, each a disjoint shard")
    ap.add_argument("--skip-existing", action="store_true", help="skip ids whose mask png already exists")
    args = ap.parse_args()

    import pandas as pd
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.labels_csv)
    df["isic_id"] = df["original_path"].apply(lambda p: Path(p).stem)
    uniq = df.drop_duplicates("isic_id")[["isic_id", "original_path"]].reset_index(drop=True)
    if args.limit > 0:
        uniq = uniq.iloc[: args.limit]
    if args.nshards > 1:
        uniq = uniq.iloc[args.shard :: args.nshards].reset_index(drop=True)
    print(f"[data] shard {args.shard}/{args.nshards}: {len(uniq)} ids -> {out_dir}")

    tiers = {"otsu": 0, "grabcut": 0, "gaussian": 0}
    done = skipped = 0
    for _, row in uniq.iterrows():
        if args.skip_existing and (out_dir / f"{row['isic_id']}.png").exists():
            continue
        bgr = cv2.imread(str(row["original_path"]))
        if bgr is None:
            skipped += 1
            continue
        if bgr.shape[:2] != (args.out_size, args.out_size):
            bgr = cv2.resize(bgr, (args.out_size, args.out_size), interpolation=cv2.INTER_AREA)
        m, tier = lesion_mask(bgr)
        tiers[tier] += 1
        cv2.imwrite(str(out_dir / f"{row['isic_id']}.png"), (m * 255).astype(np.uint8))
        if args.debug_overlay:
            heat = cv2.applyColorMap((m * 255).astype(np.uint8), cv2.COLORMAP_JET)
            cv2.imwrite(str(out_dir / f"_ov_{tier}_{row['isic_id']}.png"),
                        cv2.addWeighted(bgr, 0.6, heat, 0.4, 0))
        done += 1
        if done % 5000 == 0:
            print(f"  {done}/{len(uniq)}  tiers={tiers}")
    print(f"[done] wrote {done}, skipped {skipped}.  tiers={tiers} "
          f"({100*tiers['gaussian']/max(done,1):.1f}% fell to central-gaussian)")


if __name__ == "__main__":
    main()
