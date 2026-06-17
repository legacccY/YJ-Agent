"""
stratify_eval.py — PC-A 分层评估器 (BraTS test, CPU 可跑)
服务: MedAD-FailMap Phase 0, PC-A (A1-strat-size / A2-strat-contrast / A3-interact-2D)

输入:
  - anomaly_scores_brats_<model>.csv  (train_recon_ae.py 产出)
  - BraTS test/annotation/ 像素 mask (png, pixel>0=肿瘤)

产出:
  - stratify_size_<model>.csv          -- 按 size 分桶检出率
  - stratify_contrast_<model>.csv      -- 按 contrast 分桶检出率
  - stratify_interact_<model>.csv      -- size x contrast 3x3 网格检出率 (A3)

协变量口径 (03_phase0_plan.md):
  - size    = 最大连通域面积 (像素数, 官方 mask pixel>0)
  - contrast = 病灶均值 - 3px 膨胀环带均值 (绝对值)

多重比较: 无 (分层描述性统计，显著性检验在 incremental_stats.py 含 Holm/FDR)

分桶: >=3 桶 (size: 三等分 33/67 percentile; contrast: 同)
      A3: size x contrast 各 3 档 -> 3x3 = 9 格

检出率定义: 阈值 = 测试集 anomaly_score 前 10% (top-10% 判正异常)
  🔴 TODO: 阈值选法官方未明确指定 per-pillar 检出率口径,
            此处用 top-10% 作为雏形，需 researcher/主线确认。

依赖: numpy, scikit-image (label, binary_dilation), Pillow
"""

import argparse
import csv
import os
from pathlib import Path

import numpy as np
from PIL import Image


# ============================================================
# 协变量计算
# ============================================================
def compute_mask_covariate(mask_arr):
    """
    从二值 mask (H,W) 计算 size + contrast_proxy。
    contrast_proxy 需要原图灰度值，此处返回 size 和 mask 自身。
    连通域用 skimage.measure.label (4-连通)。
    返回最大连通域面积 (像素数)，若 mask 全零返回 0。
    """
    from skimage.measure import label as sk_label
    mask_bin = (mask_arr > 0).astype(np.uint8)
    if mask_bin.sum() == 0:
        return 0
    labeled = sk_label(mask_bin, connectivity=1)
    regions = np.bincount(labeled.ravel())
    regions[0] = 0          # 背景置 0
    return int(regions.max())


def compute_contrast(img_arr, mask_arr, dilation_px=3):
    """
    contrast = |mean(img[mask]) - mean(img[ring])|
    ring = binary_dilation(mask, px) XOR mask
    img_arr: (H,W) float, mask_arr: (H,W) uint8

    🔴 TODO: dilation_px=3 是 03_phase0_plan.md 指定值，
             但原图坐标系 (64x64 resized) 下 3px 环宽合理性需主线/researcher 确认。
    """
    from skimage.morphology import dilation, disk
    mask_bin = (mask_arr > 0)
    if mask_bin.sum() == 0:
        return 0.0
    dilated = dilation(mask_bin.astype(np.uint8), footprint=disk(dilation_px)).astype(bool)
    ring    = dilated & (~mask_bin)
    if ring.sum() == 0:
        return 0.0
    lesion_mean = float(img_arr[mask_bin].mean())
    ring_mean   = float(img_arr[ring].mean())
    return abs(lesion_mean - ring_mean)


# ============================================================
# 读 mask 目录
# ============================================================
def load_mask(mask_dir, filename):
    """尝试 filename 及不带/带 suffix 变体，返回 (H,W) uint8 array 或 None

    BraTS2021 官方命名：测试原图 `BraTS2021_XXXXX_flair_YY.png`，
    对应 mask 在 annotation/ 下叫 `BraTS2021_XXXXX_seg_YY.png`（_flair_→_seg_）。
    anomaly_scores csv 记的是原图名，故 mask 查找需做 _flair_→_seg_ 映射。
    """
    mask_dir = Path(mask_dir)
    stem = Path(filename).stem
    # 候选 stem：原名 + BraTS _flair_→_seg_ 映射
    cand_stems = [stem]
    if "_flair_" in stem:
        cand_stems.append(stem.replace("_flair_", "_seg_"))
    for s in cand_stems:
        for ext in (".png", ".PNG", ".jpg", ".JPG"):
            p = mask_dir / (s + ext)
            if p.exists():
                return np.array(Image.open(p).convert("L"))
    return None


def load_img_gray(img_dir, filename, size=64):
    """读测试原图 (resize 到 64x64)，返回 float [0,1]"""
    img_dir = Path(img_dir)
    stem = Path(filename).stem
    for ext in (".png", ".PNG", ".jpg", ".JPG", ".jpeg"):
        p = img_dir / (stem + ext)
        if not p.exists():
            p = img_dir / filename
        if p.exists():
            arr = np.array(Image.open(p).convert("L").resize((size, size),
                                                              Image.BILINEAR),
                           dtype=np.float32) / 255.0
            return arr
    return None


# ============================================================
# 分桶工具
# ============================================================
def percentile_bin(values, n_bins=3):
    """按 n_bins 等分 percentile 分桶，返回 bin index array (0-based)"""
    arr = np.array(values, dtype=np.float64)
    edges = np.percentile(arr[arr > 0] if (arr > 0).any() else arr,
                          np.linspace(0, 100, n_bins + 1))
    edges = np.unique(edges)
    bins  = np.digitize(arr, edges[1:-1])   # 0 ~ n_bins-1
    return bins


# ============================================================
# 主逻辑
# ============================================================
def run_stratify(args):
    score_csv  = Path(args.score_csv)
    mask_dir   = Path(args.mask_dir)        # brats/test/annotation/
    tumor_dir  = Path(args.tumor_img_dir)   # brats/test/tumor/  (原图，算 contrast 用)
    out_dir    = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    model_tag = args.model_tag   # ae / vae

    # 读 anomaly scores (只取 tumor 行)
    rows = []
    with open(score_csv, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["split"] == "tumor":
                rows.append(row)
    print(f"[stratify] tumor rows: {len(rows)}")

    # 计算每张 tumor 图的 size, contrast
    sizes     = []
    contrasts = []
    scores    = []
    valid_rows = []

    for row in rows:
        fname = row["filename"]
        mask_arr = load_mask(mask_dir, fname)
        if mask_arr is None:
            continue  # mask 缺失跳过
        img_arr = load_img_gray(tumor_dir, fname, size=64)
        # resize mask to 64x64
        mask_resized = np.array(
            Image.fromarray(mask_arr).resize((64, 64), Image.NEAREST)
        )
        size_val     = compute_mask_covariate(mask_resized)
        if img_arr is not None:
            contrast_val = compute_contrast(img_arr, mask_resized, dilation_px=3)
        else:
            contrast_val = 0.0  # img 找不到时退化
        sizes.append(size_val)
        contrasts.append(contrast_val)
        scores.append(float(row["anomaly_score"]))
        valid_rows.append(row)

    print(f"[stratify] valid (mask found): {len(valid_rows)}")
    sizes     = np.array(sizes,     dtype=np.float64)
    contrasts = np.array(contrasts, dtype=np.float64)
    scores    = np.array(scores,    dtype=np.float64)

    # 检出率阈值: top-10% 全 test 集 anomaly score
    # 🔴 TODO: 阈值口径需主线/researcher 确认
    threshold = np.percentile(scores, 90)
    detected  = (scores >= threshold).astype(int)

    # ---- A1: size 分桶 ----
    n_bins = 3
    size_bins = percentile_bin(sizes, n_bins)
    _write_strat_csv(out_dir / f"stratify_size_{model_tag}.csv",
                     sizes, size_bins, detected, scores,
                     bin_name="size_bin", value_name="size_px")

    # ---- A2: contrast 分桶 ----
    contrast_bins = percentile_bin(contrasts, n_bins)
    _write_strat_csv(out_dir / f"stratify_contrast_{model_tag}.csv",
                     contrasts, contrast_bins, detected, scores,
                     bin_name="contrast_bin", value_name="contrast")

    # ---- A3: size x contrast 3x3 grid ----
    _write_interact_csv(out_dir / f"stratify_interact_{model_tag}.csv",
                        sizes, size_bins, contrasts, contrast_bins,
                        detected, scores)

    # ---- per-image 明细 csv (供 stratify_significance.py T1/T2/T3 使用) ----
    # 列: filename / size_px / contrast / anomaly_score / detected
    # detected 口径与上方一致: tumor-only P90 阈值
    per_image_path = out_dir / f"stratify_per_image_{model_tag}.csv"
    with open(per_image_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["filename", "size_px", "contrast",
                                               "anomaly_score", "detected"])
        writer.writeheader()
        for idx, row in enumerate(valid_rows):
            writer.writerow({
                "filename":     row["filename"],
                "size_px":      round(float(sizes[idx]), 4),
                "contrast":     round(float(contrasts[idx]), 6),
                "anomaly_score": round(float(scores[idx]), 6),
                "detected":     int(detected[idx]),
            })
    print(f"  -> {per_image_path.name}: {len(valid_rows)} rows (per-image detail)")

    print(f"[stratify] done. outputs in {out_dir}")


def _write_strat_csv(out_path, values, bins, detected, scores, bin_name, value_name):
    """输出分桶检出率 csv"""
    unique_bins = sorted(set(bins))
    rows_out = []
    for b in unique_bins:
        mask = bins == b
        n        = int(mask.sum())
        n_det    = int(detected[mask].sum())
        det_rate = n_det / n if n > 0 else float("nan")
        val_mean = float(values[mask].mean()) if n > 0 else float("nan")
        val_min  = float(values[mask].min())  if n > 0 else float("nan")
        val_max  = float(values[mask].max())  if n > 0 else float("nan")
        score_mean = float(scores[mask].mean()) if n > 0 else float("nan")
        rows_out.append({
            bin_name:     b,
            value_name + "_mean": round(val_mean, 4),
            value_name + "_min":  round(val_min, 4),
            value_name + "_max":  round(val_max, 4),
            "n":           n,
            "n_detected":  n_det,
            "detection_rate": round(det_rate, 4),
            "anomaly_score_mean": round(score_mean, 6),
        })
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows_out[0].keys()))
        writer.writeheader()
        writer.writerows(rows_out)
    print(f"  -> {out_path.name}: {len(rows_out)} bins")


def _write_interact_csv(out_path, sizes, size_bins, contrasts, contrast_bins,
                         detected, scores):
    """A3: 3x3 size x contrast 交互网格"""
    rows_out = []
    for sb in sorted(set(size_bins)):
        for cb in sorted(set(contrast_bins)):
            mask = (size_bins == sb) & (contrast_bins == cb)
            n    = int(mask.sum())
            if n == 0:
                rows_out.append({
                    "size_bin": sb, "contrast_bin": cb,
                    "n": 0, "n_detected": 0, "detection_rate": float("nan"),
                    "size_mean": float("nan"), "contrast_mean": float("nan"),
                    "anomaly_score_mean": float("nan"),
                })
                continue
            n_det    = int(detected[mask].sum())
            det_rate = n_det / n
            rows_out.append({
                "size_bin":     sb,
                "contrast_bin": cb,
                "n":            n,
                "n_detected":   n_det,
                "detection_rate": round(det_rate, 4),
                "size_mean":    round(float(sizes[mask].mean()), 2),
                "contrast_mean": round(float(contrasts[mask].mean()), 4),
                "anomaly_score_mean": round(float(scores[mask].mean()), 6),
            })
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows_out[0].keys()))
        writer.writeheader()
        writer.writerows(rows_out)
    print(f"  -> {out_path.name}: {len(rows_out)} cells (3x3 grid)")


# ============================================================
# Entry point
# ============================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PC-A 分层评估: size/contrast 分桶 + 3x3 交互")
    _root = Path(__file__).resolve().parent.parent
    _data = _root / "data" / "BraTS2021"  # 真实数据目录名
    _res  = _root / "results"

    parser.add_argument("--score-csv",    default=str(_res / "anomaly_scores_brats_ae.csv"),
                        help="train_recon_ae.py 产出的 anomaly score csv")
    parser.add_argument("--mask-dir",     default=str(_data / "test" / "annotation"),
                        help="BraTS test/annotation/ 目录 (像素 mask)")
    parser.add_argument("--tumor-img-dir",default=str(_data / "test" / "tumor"),
                        help="BraTS test/tumor/ 目录 (原图，算 contrast)")
    parser.add_argument("--out-dir",      default=str(_res),
                        help="输出 csv 目录")
    parser.add_argument("--model-tag",    default="ae",
                        help="模型标签，用于输出文件名 (ae/vae)")
    args = parser.parse_args()
    run_stratify(args)
