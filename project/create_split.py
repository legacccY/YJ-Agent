"""Create stratified 70/10/20 train/val/test split by ISIC ID.

Split is by *original image ID*, so all degradation levels of the same image
stay in the same partition (no data leakage across train/val/test).

Output: D:/YJ-Agent/data/isic_split.csv  (isic_id, split)

Usage:
    python create_split.py
"""

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

META_CSV  = "D:/YJ-Agent/data/raw/isic2020/train-metadata.csv"
OUT_CSV   = "D:/YJ-Agent/data/isic_split.csv"
SEED      = 42

TRAIN_FRAC = 0.70
VAL_FRAC   = 0.10
# TEST_FRAC = 0.20 (remainder)


def main():
    if Path(OUT_CSV).exists():
        print(f"Split file already exists: {OUT_CSV}")
        return

    meta = pd.read_csv(META_CSV)[["isic_id", "target"]]
    meta = meta.drop_duplicates("isic_id")
    print(f"Total unique ISIC IDs: {len(meta)}")
    print(f"  Positive (melanoma): {meta['target'].sum()} ({meta['target'].mean()*100:.1f}%)")

    # Stratified split: keep class ratio in every partition
    ids = meta["isic_id"].values
    targets = meta["target"].values

    train_ids, rest_ids, _, rest_targets = train_test_split(
        ids, targets, test_size=(1 - TRAIN_FRAC), random_state=SEED, stratify=targets
    )
    val_fraction_of_rest = VAL_FRAC / (1 - TRAIN_FRAC)
    val_ids, test_ids = train_test_split(
        rest_ids, test_size=(1 - val_fraction_of_rest), random_state=SEED, stratify=rest_targets
    )

    split_df = pd.concat([
        pd.DataFrame({"isic_id": train_ids, "split": "train"}),
        pd.DataFrame({"isic_id": val_ids,   "split": "val"}),
        pd.DataFrame({"isic_id": test_ids,  "split": "test"}),
    ]).reset_index(drop=True)

    split_df.to_csv(OUT_CSV, index=False)

    for s in ["train", "val", "test"]:
        mask = split_df["split"] == s
        count = mask.sum()
        print(f"  {s}: {count} IDs")

    print(f"\nSaved: {OUT_CSV}")
    print("To use: QADDataset(..., split_csv=OUT_CSV, split='train')")


if __name__ == "__main__":
    main()
