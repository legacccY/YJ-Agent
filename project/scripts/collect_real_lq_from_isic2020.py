"""L4 (fast): Collect real low-quality dermoscopy from existing ISIC 2020 originals.

No download needed — uses original_path from quality_labels_all.csv.
Filters by natural image quality: Laplacian variance, brightness, and saturation.
Targets 200 images across 4 quality categories.

Output:
    data/real_lq_dermoscopy_isic/metadata.json
    data/real_lq_dermoscopy_isic/{blur,dark,reflection,other}/*.jpg  (symlinks or copies)
"""
import json
import shutil
import cv2
import numpy as np
import pandas as pd
from pathlib import Path
from tqdm import tqdm

ROOT = Path("D:/YJ-Agent")
OUT_DIR = ROOT / "data/real_lq_dermoscopy_isic"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Quality thresholds for natural LQ images
LAP_THRESH = 80      # Laplacian variance < 80 = naturally blurry
BRIGHT_THRESH = 60   # Mean brightness < 60 = dark image
SAT_THRESH = 0.03    # Specular reflection (% bright pixels > 240)

N_TARGET = 200
N_PER_CAT = N_TARGET // 4


def compute_quality(img_bgr):
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    lap = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness = float(gray.mean())
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    specular_pct = float((hsv[:, :, 2] > 240).mean())
    dark_pct = float((gray < 20).mean())
    is_blur = lap < LAP_THRESH
    is_dark = brightness < BRIGHT_THRESH
    is_reflection = specular_pct > SAT_THRESH
    is_artifact = dark_pct > 0.10
    return {
        "lap_var": round(lap, 2),
        "brightness": round(brightness, 2),
        "specular_pct": round(specular_pct, 4),
        "dark_pct": round(dark_pct, 4),
        "is_blur": is_blur,
        "is_dark": is_dark,
        "is_reflection": is_reflection,
        "is_artifact": is_artifact,
        "is_lq": is_blur or is_dark or is_reflection or is_artifact,
    }


def classify_category(q):
    if q["is_blur"] and (q["is_dark"] or q["is_reflection"]):
        return "combined"
    if q["is_blur"]:
        return "blur"
    if q["is_dark"] or q["is_artifact"]:
        return "dark"
    if q["is_reflection"]:
        return "reflection"
    return "other"


def main():
    df = pd.read_csv(ROOT / "data/quality_labels_all.csv")

    # Get unique original paths
    originals = df["original_path"].drop_duplicates().tolist()
    print(f"[data] {len(originals)} unique original ISIC images")

    # Shuffle for random sampling
    rng = np.random.default_rng(42)
    rng.shuffle(originals)

    collected = []
    counts = {"blur": 0, "dark": 0, "reflection": 0, "combined": 0, "other": 0}

    pbar = tqdm(total=N_TARGET, desc="Scanning for LQ images")
    processed = 0

    for orig_path_str in originals:
        if sum(counts.values()) >= N_TARGET:
            break

        orig_path = Path(orig_path_str)
        if not orig_path.exists():
            continue

        img = cv2.imread(str(orig_path))
        if img is None:
            continue
        processed += 1

        qc = compute_quality(img)
        if not qc["is_lq"]:
            continue

        cat = classify_category(qc)
        if counts.get(cat, 0) >= N_PER_CAT and cat not in ("other",):
            # Overflow to 'other' or skip
            if cat != "other" and counts.get("other", 0) < N_PER_CAT:
                cat = "other"
            else:
                continue

        # Copy to output directory
        cat_dir = OUT_DIR / cat
        cat_dir.mkdir(exist_ok=True)
        out_file = cat_dir / orig_path.name
        if not out_file.exists():
            shutil.copy2(orig_path, out_file)

        counts[cat] = counts.get(cat, 0) + 1
        collected.append({
            "original_path": str(orig_path),
            "out_path": str(out_file),
            "category": cat,
            **qc,
        })
        pbar.update(1)

    pbar.close()

    print(f"\n[done] Collected {len(collected)} / {processed} scanned")
    print(f"  Category breakdown: {counts}")

    # Compute summary stats
    laps = [r["lap_var"] for r in collected]
    brights = [r["brightness"] for r in collected]
    print(f"  Mean Lap.var = {np.mean(laps):.1f}, Mean brightness = {np.mean(brights):.1f}")

    meta = {
        "source": "ISIC 2020 originals (quality_labels_all.csv)",
        "n_collected": len(collected),
        "n_scanned": processed,
        "counts": counts,
        "mean_lap_var": round(float(np.mean(laps)), 2),
        "mean_brightness": round(float(np.mean(brights)), 2),
        "thresholds": {
            "lap_thresh": LAP_THRESH,
            "bright_thresh": BRIGHT_THRESH,
            "sat_thresh": SAT_THRESH,
        },
        "images": collected,
    }
    with open(OUT_DIR / "metadata.json", "w") as f:
        json.dump(meta, f, indent=2)
    print(f"  Metadata: {OUT_DIR}/metadata.json")


if __name__ == "__main__":
    main()
