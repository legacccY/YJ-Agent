"""L4: Download real low-quality dermoscopy images from ISIC Archive (public API).

Strategy:
- ISIC 2020 images with low BRISQUE score (blurry/artifacts) from public metadata
- Target: 200 images across 4 quality categories:
    blur (out-of-focus), artifact (hair/frame), reflection (specular), combined

No login required: ISIC Archive API is publicly accessible.

Usage:
    python project/scripts/download_real_lq_dermoscopy.py
    python project/scripts/download_real_lq_dermoscopy.py --n 200 --out data/real_lq_dermoscopy
"""
import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np
import requests
from tqdm import tqdm

ISIC_API = "https://api.isic-archive.com/api/v2"
OUT_DEFAULT = Path("D:/YJ-Agent/data/real_lq_dermoscopy")

# Quality categories to sample from
QUALITY_CATEGORIES = {
    "blur":       {"min_blur": 0, "max_blur": 40,  "n": 60},   # Laplacian variance < 40 = blurry
    "artifact":   {"min_blur": 0, "max_blur": 100, "n": 60},   # hair / frame artifacts
    "reflection": {"min_blur": 0, "max_blur": 100, "n": 50},
    "combined":   {"min_blur": 0, "max_blur": 50,  "n": 30},
}


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=200, help="Total images to download")
    p.add_argument("--out", type=str, default=str(OUT_DEFAULT))
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args()


def laplacian_var(img_gray: np.ndarray) -> float:
    return float(cv2.Laplacian(img_gray, cv2.CV_64F).var())


def is_low_quality(img_bgr: np.ndarray, lap_thresh: float = 80) -> dict:
    """Classify image quality issues."""
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    lap = laplacian_var(gray)

    # Blur: low Laplacian variance
    is_blur = lap < lap_thresh

    # Specular reflection: bright saturated pixels
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    bright_pct = float((hsv[:, :, 2] > 240).mean())
    is_reflection = bright_pct > 0.03

    # Dark artifact: large dark regions
    dark_pct = float((gray < 30).mean())
    is_artifact = dark_pct > 0.05

    return {
        "lap_var": round(lap, 2),
        "is_blur": is_blur,
        "is_reflection": is_reflection,
        "is_artifact": is_artifact,
        "is_lq": is_blur or is_reflection or is_artifact,
    }


def fetch_isic_batch(offset: int = 0, limit: int = 100) -> list:
    """Fetch image metadata from ISIC API."""
    url = f"{ISIC_API}/images/"
    params = {
        "limit": limit,
        "offset": offset,
        "sort": "random",
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        return data.get("results", [])
    except Exception as e:
        print(f"  [warn] API error at offset={offset}: {e}")
        return []


def get_image_url(image_id: str) -> str | None:
    """Get full-resolution image URL from ISIC API."""
    try:
        r = requests.get(f"{ISIC_API}/images/{image_id}", timeout=10)
        if r.status_code == 200:
            files = r.json().get("files", {})
            # Prefer full, fallback to thumbnail_256
            return (files.get("full") or files.get("thumbnail_256") or {}).get("url")
    except Exception:
        pass
    return None


def download_image(image_id: str, out_path: Path) -> bool:
    """Download ISIC image via S3 URL."""
    url = get_image_url(image_id)
    if not url:
        return False
    try:
        r = requests.get(url, timeout=30)
        if r.status_code == 200:
            with open(out_path, "wb") as f:
                f.write(r.content)
            return True
    except Exception:
        pass
    return False


def main():
    args = parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    meta_path = out_dir / "metadata.json"

    print(f"[target] {args.n} real low-quality dermoscopy images -> {out_dir}")
    print(f"[source] ISIC Archive public API: {ISIC_API}")

    collected = []
    counts = {"blur": 0, "reflection": 0, "artifact": 0, "combined": 0, "other_lq": 0}
    target_per_cat = args.n // 4
    total_target = args.n

    offset = 0
    batch_size = 50
    max_batches = 200  # safety limit

    pbar = tqdm(total=total_target, desc="Downloading LQ images")

    while len(collected) < total_target and offset < batch_size * max_batches:
        batch = fetch_isic_batch(offset=offset, limit=batch_size)
        if not batch:
            break

        for item in batch:
            if len(collected) >= total_target:
                break
            image_id = item.get("isic_id") or item.get("id") or item.get("name")
            if not image_id:
                continue

            # Temp download to check quality
            tmp_path = out_dir / f"_tmp_{image_id}.jpg"
            if not download_image(image_id, tmp_path):
                continue

            img = cv2.imread(str(tmp_path))
            if img is None:
                tmp_path.unlink(missing_ok=True)
                continue

            qc = is_low_quality(img)
            if not qc["is_lq"]:
                tmp_path.unlink(missing_ok=True)
                continue

            # Classify category
            if qc["is_blur"] and qc["is_reflection"]:
                cat = "combined"
            elif qc["is_blur"]:
                cat = "blur"
            elif qc["is_reflection"]:
                cat = "reflection"
            elif qc["is_artifact"]:
                cat = "artifact"
            else:
                cat = "other_lq"

            # Cap per category
            if counts.get(cat, 0) >= target_per_cat and cat != "other_lq":
                tmp_path.unlink(missing_ok=True)
                continue

            # Save to category subdirectory
            cat_dir = out_dir / cat
            cat_dir.mkdir(exist_ok=True)
            final_path = cat_dir / f"{image_id}.jpg"
            tmp_path.replace(final_path)  # replace() works even if dest exists (Windows safe)
            counts[cat] = counts.get(cat, 0) + 1

            collected.append({
                "image_id": image_id,
                "path": str(final_path),
                "category": cat,
                **qc,
            })
            pbar.update(1)
            time.sleep(0.1)  # rate limit

        offset += batch_size
        time.sleep(0.5)

    pbar.close()

    with open(meta_path, "w") as f:
        json.dump({"n_collected": len(collected), "counts": counts, "images": collected}, f, indent=2)

    print(f"\n[done] Collected {len(collected)} images")
    print(f"  Category breakdown: {counts}")
    print(f"  Metadata saved: {meta_path}")

    # Compute summary quality stats for paper
    if collected:
        laps = [r["lap_var"] for r in collected]
        print(f"  Mean Laplacian variance: {np.mean(laps):.1f} (vs clean ~200+)")


if __name__ == "__main__":
    main()
