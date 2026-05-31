"""Regenerate paired degraded images WITHOUT random crop (pixel-aligned).

Reads quality_labels_all.csv rows for the given level(s), re-degrades each
original with crop_prob=0, writes to data/paired_dataset_nocrop/<level>/,
and emits quality_labels_nocrop.csv with rewritten degraded_path.

Original paired_dataset is left untouched (reversible).
"""
import argparse
import os
import random
import sys
from pathlib import Path

import cv2
import pandas as pd
from tqdm import tqdm

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data.degrade import degrade_image

LABELS = "D:/YJ-Agent/data/quality_labels_all.csv"
OUT_ROOT = Path("D:/YJ-Agent/data/paired_dataset_nocrop")
OUT_CSV = "D:/YJ-Agent/data/quality_labels_nocrop.csv"
SIZE = 256
SEED = 42


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--levels", nargs="+", default=["medium"])
    args = ap.parse_args()

    df = pd.read_csv(LABELS)
    random.seed(SEED)

    # Load existing nocrop CSV (merge, not overwrite — preserve already-done levels)
    existing = pd.read_csv(OUT_CSV) if Path(OUT_CSV).exists() else pd.DataFrame()
    if not existing.empty:
        keep = existing[~existing["level"].isin(args.levels)]
    else:
        keep = pd.DataFrame()

    new_rows = []
    for level in args.levels:
        sub = df[df["level"] == level].copy()
        out_dir = OUT_ROOT / level
        out_dir.mkdir(parents=True, exist_ok=True)
        done = skipped = 0
        for _, row in tqdm(sub.iterrows(), total=len(sub), desc=f"{level} no-crop"):
            src = row["original_path"]
            if not os.path.exists(src):
                skipped += 1
                continue
            img = cv2.imread(src)
            if img is None:
                skipped += 1
                continue
            deg = degrade_image(img, level, target_size=SIZE, crop_prob=0.0)
            name = Path(src).stem + ".jpg"
            dst = out_dir / name
            cv2.imwrite(str(dst), deg)
            r = row.copy()
            r["degraded_path"] = str(dst).replace("/", "\\")
            new_rows.append(r)
            done += 1
        print(f"[{level}] written={done} skipped={skipped}")

    out = pd.concat([keep, pd.DataFrame(new_rows)], ignore_index=True)
    out.to_csv(OUT_CSV, index=False)
    print(f"[DONE] {len(out)} rows total -> {OUT_CSV}")


if __name__ == "__main__":
    main()
