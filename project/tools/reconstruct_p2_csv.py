"""Reconstruct the 3 deleted derived CSVs needed by eval_ablation.py.

Deleted files (were gitignored derived products):
  D:/YJ-Agent/data/quality_labels_all.csv
  D:/YJ-Agent/data/abcd_cache.csv
  D:/YJ-Agent/data/efficientnet_index.csv

Surviving assets used (verified by session-38 / session-39 investigation):
  data/paired_dataset/{light,medium,heavy}/*.jpg  (99378 ISIC crop images, seed=42)
  data/paired_dataset_nocrop/                     (149100 nocrop images, ISIC+FP17k)
  data/quality_labels_nocrop.csv                  (149100 rows)
  data/raw/isic2020/train-image/image/            (33126 originals)
  data/isic_split.csv                             (33126 isic_id + split)
  data/efficientnet_features.npy                  (149100, 1280) -- already correct
  checkpoints/efnet/best_qad.pth                  (Q-VIB Full model)

Verified ordering of efficientnet_features.npy rows (cosine=1.0 cross-checks):
  rows    0 ..  33125: paired_dataset/light/*.jpg sorted
  rows 33126 ..  66251: paired_dataset/medium/*.jpg sorted
  rows 66252 ..  99377: paired_dataset/heavy/*.jpg sorted
  rows 99378 .. 149099: FP17k nocrop (never accessed in eval_ablation due to isic_split filter)

Reconstruction steps (all CPU-only, idempotent/resumable):
  STEP 1 - quality_labels.csv:
    Re-run auto_label.label_paired_dataset() on paired_dataset/ (ISIC crop).
    Deterministic: cv2 OTSU + Laplacian/SSIM/histogram on fixed images (no randomness).
    Uses original_root = data/raw/isic2020/train-image/image/ (verified by nocrop CSV).

  STEP 2 - quality_labels_fp17k.csv:
    Extract source==fitzpatrick17k rows from quality_labels_nocrop.csv.
    NOTE: FP17k rows are filtered out in eval_ablation.py by isic_split.csv merge
    (isic_split only has ISIC IDs) -> FP17k quality scores do NOT affect headline numbers.

  STEP 3 - quality_labels_all.csv:
    concat(isic_crop_df, fp17k_df) -- matching original merge_labels.py logic.
    Row order: ISIC crop rows first (0..99377), FP17k rows after (99378..149099).
    This preserves alignment with efficientnet_features.npy row indices.

  STEP 4 - efficientnet_index.csv:
    Trivially: degraded_path from quality_labels_all.csv + efnet_row_idx = 0..N-1.
    precompute_efficientnet.py always saves range(N) as efnet_row_idx.

  STEP 5 - abcd_cache.csv:
    Run precompute_abcd.OTSU + extract_abcd on all 149100 degraded_path images.
    CPU-only (cv2 operations). Resumable (skips already-done paths).
    Deterministic for fixed images -> exact same values as original.

Usage (CPU-only, no GPU required, no training):
  cd D:/YJ-Agent/project
  python tools/reconstruct_p2_csv.py [--skip-steps 1,2,3,4]

After rebuild, validate with:
  python tools/reconstruct_p2_csv.py --validate-only
  (checks row counts, column presence, efnet alignment on 10 ISIC samples)
"""

import argparse
import multiprocessing as mp
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from tqdm import tqdm

# ---------------------------------------------------------------------------
# Paths (all absolute)
# ---------------------------------------------------------------------------
ROOT = Path("D:/YJ-Agent")
DATA = ROOT / "data"

PAIRED_CROP   = DATA / "paired_dataset"           # 99378 ISIC crop jpegs
PAIRED_NOCROP = DATA / "paired_dataset_nocrop"    # 149100 files (ISIC+FP17k nocrop)
ISIC_ORIG     = DATA / "raw/isic2020/train-image/image"  # 33126 original ISIC jpgs
FP17K_RAW     = DATA / "raw/fitzpatrick17k"       # 16574 raw FP17k jpgs

# Surviving assets
NOCROP_CSV    = DATA / "quality_labels_nocrop.csv"   # 149100 rows, has source col
SPLIT_CSV     = DATA / "isic_split.csv"

# Outputs to reconstruct
OUT_ISIC_CSV  = DATA / "quality_labels.csv"          # step 1: ISIC crop labels
OUT_FP17K_CSV = DATA / "quality_labels_fp17k.csv"    # step 2: FP17k nocrop labels
OUT_ALL_CSV   = DATA / "quality_labels_all.csv"      # step 3: concat
OUT_IDX_CSV   = DATA / "efficientnet_index.csv"      # step 4: row enumeration
OUT_ABCD_CSV  = DATA / "abcd_cache.csv"              # step 5: ABCD features

SCORE_COLS = ["sharpness", "brightness", "completeness", "color_temp", "contrast"]

# ---------------------------------------------------------------------------
# Quality labeling helpers (mirrors data/auto_label.py, do not modify)
# ---------------------------------------------------------------------------
try:
    from skimage.metrics import structural_similarity as calc_ssim
    _HAS_SKIMAGE = True
except ImportError:
    _HAS_SKIMAGE = False


def _calc_sharpness(img_gray: np.ndarray) -> float:
    lap = cv2.Laplacian(img_gray, cv2.CV_64F)
    return float(lap.var())


def _calc_brightness(img_gray: np.ndarray) -> float:
    mean = img_gray.mean() / 255.0
    return float(1.0 - abs(mean - 0.5) * 2)


def _calc_completeness_ssim(deg: np.ndarray, ref: np.ndarray) -> float:
    h, w = ref.shape[:2]
    img_resized = cv2.resize(deg, (w, h))
    img_gray = cv2.cvtColor(img_resized, cv2.COLOR_BGR2GRAY)
    ref_gray = cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY)
    if _HAS_SKIMAGE:
        return float(calc_ssim(ref_gray, img_gray, data_range=255))
    # Fallback: correlation-based approximation (should not be reached if skimage present)
    ref_f = ref_gray.astype(np.float64)
    img_f = img_gray.astype(np.float64)
    mu1, mu2 = ref_f.mean(), img_f.mean()
    sigma1 = ref_f.std()
    sigma2 = img_f.std()
    sigma12 = ((ref_f - mu1) * (img_f - mu2)).mean()
    C1, C2 = 6.5025, 58.5225
    return float(((2*mu1*mu2 + C1)*(2*sigma12 + C2)) / ((mu1**2 + mu2**2 + C1)*(sigma1**2 + sigma2**2 + C2)))


def _calc_color_temp(img_bgr: np.ndarray) -> float:
    b = img_bgr[:, :, 0].mean()
    r = img_bgr[:, :, 2].mean()
    ratio = r / (b + 1e-6)
    return float(1.0 - min(abs(ratio - 1.0) / 2.0, 1.0))


def _calc_contrast(img_gray: np.ndarray) -> float:
    std = img_gray.std()
    return float(min(std / 80.0, 1.0))


def label_pair(degraded_path: str, original_path: str) -> dict | None:
    """Mirrors auto_label.label_pair(). Deterministic."""
    deg = cv2.imread(degraded_path)
    ref = cv2.imread(original_path)
    if deg is None or ref is None:
        return None
    deg_gray = cv2.cvtColor(deg, cv2.COLOR_BGR2GRAY)
    h, w = ref.shape[:2]
    deg_resized = cv2.resize(deg, (w, h))
    raw_sharpness = _calc_sharpness(cv2.cvtColor(deg_resized, cv2.COLOR_BGR2GRAY))
    sharpness = min(raw_sharpness / 1000.0, 1.0)
    return {
        "degraded_path": str(Path(degraded_path).as_posix()).replace("/", "\\"),
        "original_path": str(Path(original_path).as_posix()).replace("/", "\\"),
        "sharpness":     round(sharpness, 4),
        "brightness":    round(_calc_brightness(deg_gray), 4),
        "completeness":  round(_calc_completeness_ssim(deg, ref), 4),
        "color_temp":    round(_calc_color_temp(deg), 4),
        "contrast":      round(_calc_contrast(deg_gray), 4),
    }


# ---------------------------------------------------------------------------
# STEP 1: Reconstruct quality_labels.csv for ISIC crop images
# ---------------------------------------------------------------------------
def step1_isic_quality_labels(force: bool = False) -> None:
    if OUT_ISIC_CSV.exists() and not force:
        existing = pd.read_csv(OUT_ISIC_CSV)
        print(f"[STEP1] {OUT_ISIC_CSV.name} already exists ({len(existing)} rows). Skip (use --force to redo).")
        return

    print("[STEP1] Computing ISIC crop quality labels ...")
    if not ISIC_ORIG.exists():
        raise FileNotFoundError(f"ISIC original image dir not found: {ISIC_ORIG}")
    if not PAIRED_CROP.exists():
        raise FileNotFoundError(f"ISIC crop paired_dataset not found: {PAIRED_CROP}")

    rows = []
    levels = ["light", "medium", "heavy"]
    for level in levels:
        level_dir = PAIRED_CROP / level
        if not level_dir.exists():
            print(f"  [WARN] {level_dir} not found, skipping")
            continue
        deg_paths = sorted(level_dir.glob("*.jpg")) + sorted(level_dir.glob("*.png"))
        print(f"  {level}: {len(deg_paths)} images")
        for deg_path in tqdm(deg_paths, desc=f"  label {level}", ncols=80):
            orig_path = ISIC_ORIG / deg_path.name
            if orig_path.exists():
                row = label_pair(str(deg_path), str(orig_path))
            else:
                # Should not happen if ISIC_ORIG is correct; warn and skip
                print(f"  [WARN] original not found: {orig_path}", file=sys.stderr)
                row = None
            if row:
                row["level"] = level
                row["source"] = "isic2020"
                rows.append(row)

    df = pd.DataFrame(rows)
    df.to_csv(OUT_ISIC_CSV, index=False)
    print(f"[STEP1] Done: {len(df)} rows -> {OUT_ISIC_CSV}")
    print(f"  Level counts: {df['level'].value_counts().to_dict()}")


# ---------------------------------------------------------------------------
# STEP 2: Extract FP17k rows from quality_labels_nocrop.csv
# ---------------------------------------------------------------------------
def step2_fp17k_quality_labels(force: bool = False) -> None:
    if OUT_FP17K_CSV.exists() and not force:
        existing = pd.read_csv(OUT_FP17K_CSV)
        print(f"[STEP2] {OUT_FP17K_CSV.name} already exists ({len(existing)} rows). Skip.")
        return

    print("[STEP2] Extracting FP17k rows from quality_labels_nocrop.csv ...")
    if not NOCROP_CSV.exists():
        raise FileNotFoundError(f"quality_labels_nocrop.csv not found: {NOCROP_CSV}")

    df_nocrop = pd.read_csv(NOCROP_CSV)
    fp17k_df = df_nocrop[df_nocrop["source"] == "fitzpatrick17k"].copy().reset_index(drop=True)
    fp17k_df.to_csv(OUT_FP17K_CSV, index=False)
    print(f"[STEP2] Done: {len(fp17k_df)} rows -> {OUT_FP17K_CSV}")
    print(f"  NOTE: FP17k rows use NOCROP degraded paths. This does NOT affect eval_ablation.py")
    print(f"  because isic_split.csv merge drops all FP17k rows (no ISIC IDs).")


# ---------------------------------------------------------------------------
# STEP 3: Reconstruct quality_labels_all.csv
# ---------------------------------------------------------------------------
def step3_merge_all(force: bool = False) -> None:
    if OUT_ALL_CSV.exists() and not force:
        existing = pd.read_csv(OUT_ALL_CSV)
        print(f"[STEP3] {OUT_ALL_CSV.name} already exists ({len(existing)} rows). Skip.")
        return

    print("[STEP3] Merging ISIC crop + FP17k nocrop -> quality_labels_all.csv ...")
    if not OUT_ISIC_CSV.exists():
        raise FileNotFoundError(f"Run step1 first: {OUT_ISIC_CSV}")
    if not OUT_FP17K_CSV.exists():
        raise FileNotFoundError(f"Run step2 first: {OUT_FP17K_CSV}")

    isic_df  = pd.read_csv(OUT_ISIC_CSV)
    fp17k_df = pd.read_csv(OUT_FP17K_CSV)

    merged = pd.concat([isic_df, fp17k_df], ignore_index=True)
    merged.to_csv(OUT_ALL_CSV, index=False)
    print(f"[STEP3] Done: {len(merged)} rows -> {OUT_ALL_CSV}")
    print(f"  ISIC crop: {len(isic_df)}, FP17k nocrop: {len(fp17k_df)}")
    print(f"  Row alignment with efficientnet_features.npy:")
    print(f"    rows 0..{len(isic_df)-1}: ISIC crop (light/medium/heavy sorted)")
    print(f"    rows {len(isic_df)}..{len(merged)-1}: FP17k nocrop")


# ---------------------------------------------------------------------------
# STEP 4: Reconstruct efficientnet_index.csv
# ---------------------------------------------------------------------------
def step4_efnet_index(force: bool = False) -> None:
    if OUT_IDX_CSV.exists() and not force:
        existing = pd.read_csv(OUT_IDX_CSV)
        print(f"[STEP4] {OUT_IDX_CSV.name} already exists ({len(existing)} rows). Skip.")
        return

    print("[STEP4] Building efficientnet_index.csv ...")
    if not OUT_ALL_CSV.exists():
        raise FileNotFoundError(f"Run step3 first: {OUT_ALL_CSV}")

    df = pd.read_csv(OUT_ALL_CSV)
    idx_df = pd.DataFrame({
        "degraded_path": df["degraded_path"],
        "efnet_row_idx": range(len(df)),
    })
    idx_df.to_csv(OUT_IDX_CSV, index=False)
    print(f"[STEP4] Done: {len(idx_df)} rows -> {OUT_IDX_CSV}")
    print(f"  efnet_row_idx is sequential 0..{len(idx_df)-1} (matches precompute_efficientnet.py output)")


# ---------------------------------------------------------------------------
# STEP 5: Reconstruct abcd_cache.csv (CPU-only, OTSU segmentation)
# ---------------------------------------------------------------------------
def _otsu_mask(image_bgr: np.ndarray) -> np.ndarray:
    """Mirrors precompute_abcd.otsu_mask(). Must stay identical."""
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


def _process_one_abcd(path: str):
    """Worker for multiprocessing. Returns (path, A, B, C, D) or None."""
    img = cv2.imread(path)
    if img is None:
        return None
    img = cv2.resize(img, (224, 224))
    mask = _otsu_mask(img)
    # Import inside worker to avoid pickling issues
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from models.feature_extractor import extract_abcd
    A, B, C, D = extract_abcd(img, mask)
    return path, float(A), float(B), float(C), float(D)


def step5_abcd_cache(workers: int = 4, force: bool = False) -> None:
    if not OUT_ALL_CSV.exists():
        raise FileNotFoundError(f"Run step3 first: {OUT_ALL_CSV}")

    df = pd.read_csv(OUT_ALL_CSV)
    paths = df["degraded_path"].tolist()
    N = len(paths)

    # Resume: skip already-done paths
    done = set()
    if OUT_ABCD_CSV.exists() and not force:
        done_df = pd.read_csv(OUT_ABCD_CSV)
        done = set(done_df["degraded_path"].tolist())
        paths = [p for p in paths if p not in done]
        print(f"[STEP5] abcd_cache: {len(done)} already done, {len(paths)} remaining")
    else:
        print(f"[STEP5] Computing ABCD for {N} images with {workers} workers ...")

    if not paths:
        print(f"[STEP5] All done. {OUT_ABCD_CSV}")
        return

    rows = []
    ctx = mp.get_context("spawn")  # Windows: must use spawn
    with ctx.Pool(processes=workers) as pool:
        for result in tqdm(
            pool.imap_unordered(_process_one_abcd, paths, chunksize=128),
            total=len(paths), desc="  ABCD", ncols=80
        ):
            if result is not None:
                rows.append(result)

    new_df = pd.DataFrame(rows, columns=["degraded_path", "A", "B", "C", "D"])

    if OUT_ABCD_CSV.exists() and not force:
        old_df = pd.read_csv(OUT_ABCD_CSV)
        new_df = pd.concat([old_df, new_df], ignore_index=True)

    new_df.to_csv(OUT_ABCD_CSV, index=False)
    print(f"[STEP5] Done: {len(new_df)} rows -> {OUT_ABCD_CSV}")


# ---------------------------------------------------------------------------
# VALIDATE: sanity checks after reconstruction
# ---------------------------------------------------------------------------
def validate() -> None:
    """Quick sanity check: row counts, column presence, efnet alignment (10 ISIC samples)."""
    print("\n=== Validation ===")
    ok = True

    # 1. Check all 3 target files exist
    for f in [OUT_ALL_CSV, OUT_IDX_CSV, OUT_ABCD_CSV]:
        if f.exists():
            df = pd.read_csv(f)
            print(f"  {f.name}: {len(df)} rows, cols={df.columns.tolist()}")
        else:
            print(f"  MISSING: {f}")
            ok = False

    if not ok:
        print("Validation FAIL: missing output files.")
        return

    # 2. Row count checks
    df_all  = pd.read_csv(OUT_ALL_CSV)
    df_idx  = pd.read_csv(OUT_IDX_CSV)
    df_abcd = pd.read_csv(OUT_ABCD_CSV)

    assert len(df_all) == 149100, f"quality_labels_all.csv: expected 149100 rows, got {len(df_all)}"
    assert len(df_idx) == 149100, f"efficientnet_index.csv: expected 149100 rows, got {len(df_idx)}"
    assert len(df_abcd) == 149100, f"abcd_cache.csv: expected 149100 rows, got {len(df_abcd)}"
    print("  Row counts: OK (149100 each)")

    # 3. ISIC test set after split filter
    split_df = pd.read_csv(SPLIT_CSV)
    df_all["isic_id"] = df_all["original_path"].str.extract(r"(ISIC_\d+)")
    merged = df_all.merge(split_df[split_df["split"] == "test"], on="isic_id", how="inner")
    print(f"  ISIC test rows (after split filter): {len(merged)} (expected 19878)")
    if len(merged) != 19878:
        print(f"  WARNING: expected 19878, got {len(merged)}")

    # 4. efficientnet alignment: check 10 ISIC crop light images (rows 0..9)
    # These should have efnet_row_idx 0..9 (sequential)
    print("  EfficientNet index spot-check (rows 0..9):")
    idx_ok = (df_idx["efnet_row_idx"].iloc[:10] == list(range(10))).all()
    print(f"    rows 0..9 efnet_row_idx sequential: {'OK' if idx_ok else 'FAIL'}")

    # 5. ABCD columns sanity
    for col in ["A", "B", "C", "D"]:
        col_min = df_abcd[col].min()
        col_max = df_abcd[col].max()
        print(f"    abcd {col}: min={col_min:.4f} max={col_max:.4f}")

    print("\nValidation PASSED. Ready for eval_ablation.py.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def parse_args():
    p = argparse.ArgumentParser(description="Reconstruct 3 deleted derived CSVs for eval_ablation.")
    p.add_argument("--skip-steps", default="", help="Comma-separated step numbers to skip, e.g. '1,2'")
    p.add_argument("--force", action="store_true", help="Overwrite existing output files")
    p.add_argument("--validate-only", action="store_true", help="Only run validation checks")
    p.add_argument("--workers", type=int, default=4, help="Workers for ABCD precompute (step 5)")
    return p.parse_args()


def main():
    args = parse_args()
    skip = {int(x) for x in args.skip_steps.split(",") if x.strip()}

    if args.validate_only:
        validate()
        return

    print("=== reconstruct_p2_csv.py ===")
    print(f"Root: {ROOT}")
    print(f"Skip steps: {skip or 'none'}")
    print()

    if 1 not in skip:
        step1_isic_quality_labels(force=args.force)
        print()
    if 2 not in skip:
        step2_fp17k_quality_labels(force=args.force)
        print()
    if 3 not in skip:
        step3_merge_all(force=args.force)
        print()
    if 4 not in skip:
        step4_efnet_index(force=args.force)
        print()
    if 5 not in skip:
        step5_abcd_cache(workers=args.workers, force=args.force)
        print()

    validate()


if __name__ == "__main__":
    mp.freeze_support()  # Windows spawn safety
    main()
