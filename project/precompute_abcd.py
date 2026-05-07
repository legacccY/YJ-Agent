"""预计算 ABCD 特征并缓存到 CSV。

使用 OTSU 阈值分割（<1ms/张），替代训练时实时跑 MobileSAM。
MobileSAM 只保留在 eval_qad.py 里用于最终评测。

输出：D:/YJ-Agent/data/abcd_cache.csv
  columns: degraded_path, A, B, C, D

Usage:
    python precompute_abcd.py --labels D:/YJ-Agent/data/quality_labels_all.csv
"""

import argparse
import multiprocessing as mp
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from tqdm import tqdm

from models.feature_extractor import extract_abcd


def otsu_mask(image_bgr: np.ndarray) -> np.ndarray:
    """Fast OTSU-based lesion mask. <1ms per image."""
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    # OTSU on inverted gray (lesions typically darker than background)
    _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    # Morphological cleanup
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    # Fallback: if mask is too small (<2% area), use center ellipse
    if mask.sum() < 0.02 * mask.size:
        H, W = mask.shape
        mask = np.zeros((H, W), dtype=np.uint8)
        cv2.ellipse(mask, (W // 2, H // 2), (W // 3, H // 3), 0, 0, 360, 255, -1)
    return mask.astype(bool)


def process_one(path: str) -> tuple[str, float, float, float, float] | None:
    img = cv2.imread(path)
    if img is None:
        return None
    img = cv2.resize(img, (224, 224))
    mask = otsu_mask(img)
    A, B, C, D = extract_abcd(img, mask)
    return path, float(A), float(B), float(C), float(D)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", default="D:/YJ-Agent/data/quality_labels_all.csv")
    parser.add_argument("--out", default="D:/YJ-Agent/data/abcd_cache.csv")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    df = pd.read_csv(args.labels)
    paths = df["degraded_path"].tolist()

    # Skip already-computed paths if cache exists
    out_path = Path(args.out)
    done = set()
    if out_path.exists():
        done = set(pd.read_csv(out_path)["degraded_path"].tolist())
        paths = [p for p in paths if p not in done]
        print(f"Resuming: {len(done)} already done, {len(paths)} remaining")
    else:
        print(f"Computing ABCD for {len(paths)} images with {args.workers} workers")

    if not paths:
        print("All done.")
        return

    rows = []
    with mp.Pool(processes=args.workers) as pool:
        for result in tqdm(pool.imap_unordered(process_one, paths, chunksize=64),
                           total=len(paths), desc="ABCD precompute"):
            if result is not None:
                rows.append(result)

    new_df = pd.DataFrame(rows, columns=["degraded_path", "A", "B", "C", "D"])

    if out_path.exists():
        old_df = pd.read_csv(out_path)
        new_df = pd.concat([old_df, new_df], ignore_index=True)

    new_df.to_csv(out_path, index=False)
    print(f"Saved {len(new_df)} rows to {out_path}")


if __name__ == "__main__":
    mp.freeze_support()
    main()
