"""
ncomp_ham.py — HAM10000 per-image 连通域数补充列（n_components）
服务: MedAD-FailMap PR-7c iso 第二维（多灶性）+ A' 可复现性缺口修复

现状: lesion_features_ham.csv 无 n_components 列。
      LOG 声称 HAM n_components 中位 1（>98% 样本单一皮损），但无 csv 源。
      本脚本读 HAM10000_segmentations_lesion_tschandl/ 的 binary seg mask，
      计算每张图的连通域数，输出补充 csv（不改动 lesion_features_ham.csv）。

口径（与 CBIS/IDRiD/ncomp_brats 完全一致）:
  skimage.measure.label(bin_mask, connectivity=1)  # 4-连通
  n_components = 前景连通域总数（bin_mask.sum()==0 时 n_components=0）
  mask 前景: pixel > 127（HAM segmentation 掩膜标准二值，兼容 0/255 格式）

  HAM mask 命名规则：
    ISIC_<id>_segmentation.png  (与 lesion_features_ham.csv filename 对齐)
    filename 列中图像为 ISIC_<id>.jpg，stem = ISIC_<id>

输出 csv: results/ncomp_ham.csv
  列: filename(ISIC_<id>.jpg), n_components
  filename 与 lesion_features_ham.csv 的 filename 列对齐，可直接 join。

依赖: numpy, scikit-image, Pillow
不用 scipy（OMP#15），无 torch
"""

import argparse
import csv
from pathlib import Path

import numpy as np
from PIL import Image


def count_components_from_mask(mask_path):
    """
    读 HAM binary lesion mask，返回 4-连通域数（与 CBIS/IDRiD 口径一致）。

    mask_path: Path to ISIC_<id>_segmentation.png（前景 >127）
    返回 int（0 = 空 mask）
    """
    from skimage.measure import label as sk_label

    arr = np.array(Image.open(mask_path).convert("L"), dtype=np.uint8)
    bin_mask = (arr > 127).astype(np.uint8)

    if bin_mask.sum() == 0:
        return 0

    labeled = sk_label(bin_mask, connectivity=1)  # 4-连通（connectivity=1）
    region_sizes = np.bincount(labeled.ravel())
    region_sizes[0] = 0  # 排背景 label 0
    return int((region_sizes > 0).sum())


def run(
    ham_csv,
    mask_dir,
    out_csv,
):
    """
    主入口：读 lesion_features_ham.csv 的 filename 列（ISIC_<id>.jpg），
    在 mask_dir 中找对应 mask（ISIC_<id>_segmentation.png），
    计算 n_components，输出补充 csv。

    Args:
        ham_csv  : str/Path  lesion_features_ham.csv（含 filename 列）
        mask_dir : str/Path  HAM segmentation mask 目录
        out_csv  : str/Path  输出 csv 路径

    输出列: filename, n_components
    """
    ham_csv  = Path(ham_csv)
    mask_dir = Path(mask_dir)
    out_csv  = Path(out_csv)

    if not ham_csv.exists():
        raise FileNotFoundError(f"ham_csv 不存在: {ham_csv}")
    if not mask_dir.exists():
        raise FileNotFoundError(f"mask_dir 不存在: {mask_dir}")

    with open(ham_csv, newline="") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        raise ValueError(f"ham_csv 无有效行: {ham_csv}")

    if "filename" not in rows[0]:
        raise ValueError(f"ham_csv 缺 filename 列，实际列: {list(rows[0].keys())}")

    out_rows = []
    n_missing = 0

    for r in rows:
        fn       = r["filename"]                          # e.g. ISIC_0024310.jpg
        img_id   = Path(fn).stem                          # ISIC_0024310
        mask_fn  = img_id + "_segmentation.png"
        mask_path = mask_dir / mask_fn

        if not mask_path.exists():
            n_missing += 1
            out_rows.append({
                "filename":     fn,
                "n_components": "nan",
            })
            continue

        n_comp = count_components_from_mask(mask_path)
        out_rows.append({
            "filename":     fn,
            "n_components": n_comp,
        })

    if n_missing > 0:
        print(f"[ncomp_ham] WARNING: {n_missing}/{len(rows)} 缺少 seg mask，n_components=nan")

    # 写 csv
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["filename", "n_components"]
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(out_rows)

    # 统计打印
    valid_nc = [
        int(r["n_components"])
        for r in out_rows
        if r["n_components"] not in ("nan", "", None)
    ]
    if valid_nc:
        arr = np.array(valid_nc)
        print(
            f"[ncomp_ham] n={len(arr)} images  "
            f"p25={np.percentile(arr, 25):.0f}  "
            f"median={np.median(arr):.0f}  "
            f"p75={np.percentile(arr, 75):.0f}  "
            f"max={arr.max()}"
        )
        print(f"  n_components==1: {(arr==1).sum()} "
              f"({100*(arr==1).sum()/len(arr):.1f}%)")

    print(f"  -> {out_csv}  ({len(out_rows)} rows)")
    return out_rows


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "HAM10000 per-image n_components 补充列\n"
            "口径: skimage.measure.label(bin_mask, connectivity=1) 4-连通\n"
            "与 CBIS/IDRiD/BraTS ncomp_brats 完全一致\n"
            "输出 csv: results/ncomp_ham.csv  (filename + n_components)\n"
            "filename 与 lesion_features_ham.csv join 键一致"
        )
    )
    _root = Path(__file__).resolve().parent.parent

    parser.add_argument(
        "--ham-csv",
        default=str(_root / "results" / "lesion_features_ham.csv"),
        help="lesion_features_ham.csv（含 filename 列），默认 results/lesion_features_ham.csv",
    )
    parser.add_argument(
        "--mask-dir",
        default="D:/YJ-Agent/data/external/ham10000/HAM10000_segmentations_lesion_tschandl",
        help="HAM segmentation mask 目录（ISIC_<id>_segmentation.png）",
    )
    parser.add_argument(
        "--out-csv",
        default=str(_root / "results" / "ncomp_ham.csv"),
        help="输出 csv 路径，默认 results/ncomp_ham.csv",
    )

    args = parser.parse_args()
    run(
        ham_csv=args.ham_csv,
        mask_dir=args.mask_dir,
        out_csv=args.out_csv,
    )
