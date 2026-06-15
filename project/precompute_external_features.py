"""预计算外部数据集特征（HAM10000 / PAD-UFES）。

对每张图提取：
  - abcd (4D)         via extract_abcd + OTSU mask
  - q_vector (5D)     via VisiScore-Net
  - efnet_feat (1280D) via EfficientNet-B0

输出（每个数据集）：
  data/external/<dataset>/abcd.npy
  data/external/<dataset>/q.npy
  data/external/<dataset>/efnet.npy
  data/external/<dataset>/index.csv   (image_id, image_path, target, q_bar, target_malignant)

支持 resume：如果 npy 行数与 index.csv 一致则跳过已完成的部分。

Usage:
  cd D:/YJ-Agent/project
  python precompute_external_features.py --dataset ham10000
  python precompute_external_features.py --dataset pad_ufes
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import torch
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent))

from agent.tools import extract_features, ModelRegistry

PROJECT_DIR = Path(__file__).parent
DATA_DIR    = PROJECT_DIR.parent / "data" / "external"
LOG_PATH    = PROJECT_DIR.parent / "log" / "sprint2_state.json"

# ── Dataset configs ────────────────────────────────────────────────────────────

DATASET_CFG = {
    "ham10000": {
        "root":       DATA_DIR / "ham10000",
        "meta_csv":   DATA_DIR / "ham10000" / "HAM10000_metadata.csv",
        "img_col":    "image_id",
        "label_col":  "dx",
        "positive":   "mel",
        "malignant":  {"mel", "bcc", "akiec"},
        # images might be in sub-directories
        "img_dirs":   [
            DATA_DIR / "ham10000" / "ham10000_images_part_1",
            DATA_DIR / "ham10000" / "ham10000_images_part_2",
            DATA_DIR / "ham10000",  # fallback: flat layout
        ],
        "img_ext":    ".jpg",
    },
    "pad_ufes": {
        "root":       DATA_DIR / "pad_ufes",
        "meta_csv":   DATA_DIR / "pad_ufes" / "metadata.csv",
        "img_col":    "img_id",
        "label_col":  "diagnostic",
        "positive":   "MEL",
        "malignant":  {"MEL", "BCC", "SCC"},
        "img_dirs":   [
            DATA_DIR / "pad_ufes" / "PAD-UFES-20" / "Dataset",  # kaggle maxjen/pad-ufes-20 layout
            DATA_DIR / "pad_ufes" / "images",
            DATA_DIR / "pad_ufes",  # fallback
        ],
        "img_ext":    ".png",
    },
    # Fitzpatrick17k: clinical (non-dermoscopy) photos, lives in data/raw not data/external.
    # Cross-domain L7: melanoma = positive (3 label variants), images named <md5hash>.jpg.
    "fitz17k": {
        "root":       Path("D:/YJ-Agent/data/raw/fitzpatrick17k"),
        "meta_csv":   Path("D:/YJ-Agent/data/raw/fitzpatrick17k/fitzpatrick17k.csv"),
        "img_col":    "md5hash",
        "label_col":  "label",
        "positive":   {"melanoma", "malignant melanoma", "superficial spreading melanoma ssm"},
        "malignant":  {"melanoma", "malignant melanoma", "superficial spreading melanoma ssm",
                       "basal cell carcinoma", "squamous cell carcinoma"},
        "img_dirs":   [Path("D:/YJ-Agent/data/raw/fitzpatrick17k/images")],
        "img_ext":    ".jpg",
    },
    # DermNet: clinical (non-dermoscopy) atlas. Malignant-vs-benign neoplasm proxy:
    # AK/BCC class = positive(1), Seborrheic-Keratoses class = benign(0). Melanoma/nevi
    # mixed folder + 20 inflammatory classes excluded (see build_dermnet_metadata.py).
    # image_id = path relative to dermnet root (includes .jpg) -> img_ext "" so find_image
    # resolves root/<image_id> directly.
    "dermnet": {
        "root":       DATA_DIR / "dermnet",
        "meta_csv":   DATA_DIR / "dermnet" / "dermnet_metadata.csv",
        "img_col":    "image_id",
        "label_col":  "label",
        "positive":   {"Actinic Keratosis Basal Cell Carcinoma and other Malignant Lesions"},
        "malignant":  {"Actinic Keratosis Basal Cell Carcinoma and other Malignant Lesions"},
        "img_dirs":   [DATA_DIR / "dermnet"],
        "img_ext":    "",
    },
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def update_state(key: str, value):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    state = {}
    if LOG_PATH.exists():
        with open(LOG_PATH) as f:
            state = json.load(f)
    state[key] = value
    state["last_update"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_PATH, "w") as f:
        json.dump(state, f, indent=2)


def find_image(image_id: str, cfg: dict) -> Path | None:
    """Search all img_dirs for this image_id (with correct extension)."""
    ext = cfg["img_ext"]
    name = image_id if image_id.endswith(ext) else image_id + ext
    for d in cfg["img_dirs"]:
        p = Path(d) / name
        if p.exists():
            return p
    return None


def build_index(cfg: dict) -> pd.DataFrame:
    """Load metadata and build (image_id, image_path, target, target_malignant) dataframe."""
    meta = pd.read_csv(cfg["meta_csv"])
    img_col   = cfg["img_col"]
    label_col = cfg["label_col"]

    # For HAM10000 the image_id column does not include extension
    rows = []
    missing = 0
    for _, row in meta.iterrows():
        iid = str(row[img_col])
        dx  = str(row[label_col]).strip()
        img_path = find_image(iid, cfg)
        if img_path is None:
            missing += 1
            continue
        pos = cfg["positive"]
        target = int(dx in pos) if isinstance(pos, (set, list, tuple)) else int(dx == pos)
        target_mal = int(dx in cfg["malignant"])
        rows.append({
            "image_id":       iid,
            "image_path":     str(img_path),
            "target":         target,
            "target_malignant": target_mal,
            "dx":             dx,
        })

    df = pd.DataFrame(rows)
    if missing > 0:
        print(f"  [WARN] {missing} images not found on disk")
    print(f"  Index built: {len(df)} samples, {df['target'].sum()} MEL positives")
    return df


# ── Main extraction ────────────────────────────────────────────────────────────

def run(dataset: str):
    cfg  = DATASET_CFG[dataset]
    root = Path(cfg["root"])
    root.mkdir(parents=True, exist_ok=True)

    abcd_path  = root / "abcd.npy"
    q_path     = root / "q.npy"
    efnet_path = root / "efnet.npy"
    idx_path   = root / "index.csv"

    # ── Build or load index ────────────────────────────────────────────────────
    print(f"\n=== Precomputing features for: {dataset} ===")
    index = build_index(cfg)
    if len(index) == 0:
        print("ERROR: No images found. Check that images are extracted to the right directory.")
        return

    # ── Resume logic ──────────────────────────────────────────────────────────
    done_ids: set[str] = set()
    abcd_rows, q_rows, efnet_rows = [], [], []
    done_index_rows = []

    if idx_path.exists():
        existing_idx = pd.read_csv(idx_path)
        done_ids = set(existing_idx["image_id"].tolist())
        n_done = len(done_ids)
        if n_done > 0:
            print(f"  Resume: {n_done} already done, loading cached arrays...")
            if abcd_path.exists():
                abcd_rows  = list(np.load(abcd_path))
            if q_path.exists():
                q_rows     = list(np.load(q_path))
            if efnet_path.exists():
                efnet_rows = list(np.load(efnet_path))
            done_index_rows = existing_idx.to_dict("records")

    todo = index[~index["image_id"].isin(done_ids)]
    print(f"  To process: {len(todo)} images")

    if len(todo) == 0:
        print("  All done! Nothing to recompute.")
        return

    # ── Warm up model registry ─────────────────────────────────────────────────
    print("  Loading models (first call may take ~30s)...")
    _ = ModelRegistry.get().visiscore
    _ = ModelRegistry.get().efnet
    print(f"  Device: {ModelRegistry.get().device}")

    # ── Process ───────────────────────────────────────────────────────────────
    errors = 0
    t0 = time.time()
    update_state(f"{dataset}_status", "processing")

    for idx_row, row in tqdm(todo.iterrows(), total=len(todo), desc=dataset):
        img_bgr = cv2.imread(str(row["image_path"]))
        if img_bgr is None:
            errors += 1
            continue
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

        try:
            feats = extract_features(img_rgb)
        except Exception as e:
            print(f"\n  [ERR] {row['image_id']}: {e}")
            errors += 1
            continue

        q_bar = float(feats.q_vector.mean())
        abcd_rows.append(feats.abcd.astype(np.float32))
        q_rows.append(feats.q_vector.astype(np.float32))
        efnet_rows.append(feats.efnet_feat.astype(np.float32))
        done_index_rows.append({
            "image_id":         row["image_id"],
            "image_path":       row["image_path"],
            "target":           row["target"],
            "target_malignant": row["target_malignant"],
            "q_bar":            q_bar,
        })

        # Checkpoint every 500 images
        if len(done_index_rows) % 500 == 0:
            np.save(abcd_path,  np.array(abcd_rows,  dtype=np.float32))
            np.save(q_path,     np.array(q_rows,     dtype=np.float32))
            np.save(efnet_path, np.array(efnet_rows, dtype=np.float32))
            pd.DataFrame(done_index_rows).to_csv(idx_path, index=False)
            elapsed = time.time() - t0
            update_state(f"{dataset}_progress", {
                "done": len(done_index_rows),
                "total": len(index),
                "errors": errors,
                "elapsed_s": round(elapsed, 1),
            })

    # Final save
    np.save(abcd_path,  np.array(abcd_rows,  dtype=np.float32))
    np.save(q_path,     np.array(q_rows,     dtype=np.float32))
    np.save(efnet_path, np.array(efnet_rows, dtype=np.float32))
    pd.DataFrame(done_index_rows).to_csv(idx_path, index=False)

    elapsed = time.time() - t0
    print(f"\n  Done in {elapsed/60:.1f} min | {len(done_index_rows)} samples | {errors} errors")
    print(f"  abcd  : {abcd_path}  shape={np.array(abcd_rows).shape}")
    print(f"  q     : {q_path}     shape={np.array(q_rows).shape}")
    print(f"  efnet : {efnet_path} shape={np.array(efnet_rows).shape}")
    print(f"  index : {idx_path}")

    # Sanity check
    idx_df = pd.DataFrame(done_index_rows)
    q_arr  = np.array(q_rows, dtype=np.float32)
    nan_count = int(np.isnan(q_arr).sum())
    zero_rows = int((np.abs(q_arr).sum(axis=1) == 0).sum())
    print(f"\n  Sanity: NaN={nan_count}  all-zero rows={zero_rows}")
    print(f"  q_bar stats: mean={idx_df['q_bar'].mean():.3f}  std={idx_df['q_bar'].std():.3f}  "
          f"min={idx_df['q_bar'].min():.3f}  max={idx_df['q_bar'].max():.3f}")
    print(f"  Class balance: {int(idx_df['target'].sum())} positives / {len(idx_df)} total "
          f"({100*idx_df['target'].mean():.1f}%)")

    update_state(f"{dataset}_status", "done")
    update_state(f"{dataset}_n", len(done_index_rows))
    update_state(f"{dataset}_mel_pos", int(idx_df["target"].sum()))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True,
                        choices=["ham10000", "pad_ufes", "fitz17k", "dermnet"])
    args = parser.parse_args()
    run(args.dataset)


if __name__ == "__main__":
    main()
