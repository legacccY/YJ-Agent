"""预处理所有图片到 memmap 缓存，只需跑一次。

生成：
  data/cache_deg.npy    - 退化图，shape (N, H, W, 3) uint8
  data/cache_clean.npy  - 原图（去重后），shape (M, H, W, 3) uint8
  data/cache_meta.npy   - 每行的 (clean_idx, labels[5])，shape (N, 6)

用法：
  cd D:/YJ-Agent/project
  python data/build_cache.py
"""
import sys
import numpy as np
import pandas as pd
import cv2
from pathlib import Path
from tqdm import tqdm

IMG_SIZE = 224
CSV_PATH  = Path("D:/YJ-Agent/data/quality_labels_all.csv")
CACHE_DIR = Path("D:/YJ-Agent/data")

SCORE_COLS = ["sharpness", "brightness", "completeness", "color_temp", "contrast"]


def load_img(path: str) -> np.ndarray:
    img = cv2.imread(path)
    if img is None:
        img = np.zeros((IMG_SIZE, IMG_SIZE, 3), dtype=np.uint8)
    img = cv2.resize(img, (IMG_SIZE, IMG_SIZE), interpolation=cv2.INTER_LINEAR)
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


def main():
    df = pd.read_csv(CSV_PATH)
    N = len(df)
    print(f"Total rows: {N}")

    # ── 建原图索引（去重）──────────────────────────────
    unique_originals = df["original_path"].unique()
    orig2idx = {p: i for i, p in enumerate(unique_originals)}
    M = len(unique_originals)
    print(f"Unique originals: {M}")

    # ── 估算磁盘占用 ───────────────────────────────────
    deg_gb   = N * IMG_SIZE * IMG_SIZE * 3 / 1e9
    clean_gb = M * IMG_SIZE * IMG_SIZE * 3 / 1e9
    print(f"Cache size: deg={deg_gb:.1f} GB, clean={clean_gb:.1f} GB, total={deg_gb+clean_gb:.1f} GB")

    # ── 创建 memmap 文件 ───────────────────────────────
    deg_cache   = np.lib.format.open_memmap(CACHE_DIR / "cache_deg.npy",   mode="w+", dtype=np.uint8,   shape=(N, IMG_SIZE, IMG_SIZE, 3))
    clean_cache = np.lib.format.open_memmap(CACHE_DIR / "cache_clean.npy", mode="w+", dtype=np.uint8,   shape=(M, IMG_SIZE, IMG_SIZE, 3))
    meta        = np.lib.format.open_memmap(CACHE_DIR / "cache_meta.npy",  mode="w+", dtype=np.float32, shape=(N, 6))

    # ── 写退化图 ───────────────────────────────────────
    print("\n[1/2] Writing degraded images...")
    for i, row in tqdm(df.iterrows(), total=N, ncols=80):
        deg_cache[i] = load_img(row["degraded_path"])
        clean_idx = orig2idx[row["original_path"]]
        labels = row[SCORE_COLS].values.astype(np.float32)
        meta[i, 0] = clean_idx
        meta[i, 1:] = labels

    # ── 写原图（去重）─────────────────────────────────
    print("\n[2/2] Writing clean images...")
    for i, path in enumerate(tqdm(unique_originals, ncols=80)):
        clean_cache[i] = load_img(path)

    del deg_cache, clean_cache, meta
    print("\nDone! Cache files written to D:/YJ-Agent/data/")


if __name__ == "__main__":
    main()
