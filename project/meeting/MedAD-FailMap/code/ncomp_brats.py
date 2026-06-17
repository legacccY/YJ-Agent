"""
ncomp_brats.py — BraTS per-slice 连通域数补充列（n_components）
服务: MedAD-FailMap PR-7c iso 第二维（多灶性）+ A' 可复现性缺口修复

现状: stratify_per_image_ae.csv 与 brats_brain_px.csv 均无 n_components 列。
      LOG 声称 BraTS 肿瘤 n_components 中位 1-3（P25=1, P75=3），但无 csv 源。
      本脚本读 data/BraTS2021/test/annotation/ 的 binary seg mask，
      计算每个 slice 的连通域数，输出补充 csv（不改动既有 csv）。

口径（与 CBIS/IDRiD 完全一致）:
  skimage.measure.label(bin_mask, connectivity=1)  # 4-连通
  n_components = 前景连通域总数（bin_mask.sum()==0 时 n_components=0）
  mask 前景: pixel > 0（annotation PNG 前景值为 255，阈值 >0 兜底）

  BraTS annotation mask 命名规则：
    flair: BraTS2021_<ID>_flair_<slice>.png  (来自 stratify_per_image_ae.csv)
    seg:   BraTS2021_<ID>_seg_<slice>.png    (annotation/ 下)
    映射: flair filename.replace('_flair_', '_seg_')

输出 csv: results/ncomp_brats.csv
  列: filename(flair 名), seg_filename, n_components
  filename 与 stratify_per_image_ae.csv / brats_brain_px.csv 的 filename 列对齐，
  可直接 join。

依赖: numpy, scikit-image, Pillow
不用 scipy（OMP#15），无 torch
"""

import argparse
import csv
from pathlib import Path

import numpy as np
from PIL import Image


def count_components_from_seg(seg_path):
    """
    读 BraTS binary seg mask，返回 4-连通域数（与 CBIS/IDRiD 口径一致）。

    seg_path: Path to annotation PNG（前景 =255，背景=0）
    返回 int（0 = 空 mask）
    """
    from skimage.measure import label as sk_label

    arr = np.array(Image.open(seg_path).convert("L"), dtype=np.uint8)
    bin_mask = (arr > 0).astype(np.uint8)

    if bin_mask.sum() == 0:
        return 0

    labeled = sk_label(bin_mask, connectivity=1)  # 4-连通（connectivity=1）
    region_sizes = np.bincount(labeled.ravel())
    region_sizes[0] = 0  # 排背景 label 0
    return int((region_sizes > 0).sum())


def run(
    strat_csv,
    ann_dir,
    out_csv,
):
    """
    主入口：读 stratify_per_image_ae.csv 的 filename 列（flair 命名），
    映射到 annotation/ 下的 seg mask，计算 n_components。

    Args:
        strat_csv : str/Path  BraTS per-image csv（含 filename 列，flair 命名）
        ann_dir   : str/Path  annotation 目录（含 *_seg_*.png）
        out_csv   : str/Path  输出 csv 路径

    输出列: filename, seg_filename, n_components
    """
    strat_csv = Path(strat_csv)
    ann_dir   = Path(ann_dir)
    out_csv   = Path(out_csv)

    if not strat_csv.exists():
        raise FileNotFoundError(f"strat_csv 不存在: {strat_csv}")
    if not ann_dir.exists():
        raise FileNotFoundError(f"ann_dir 不存在: {ann_dir}")

    with open(strat_csv, newline="") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        raise ValueError(f"strat_csv 无有效行: {strat_csv}")

    if "filename" not in rows[0]:
        raise ValueError(f"strat_csv 缺 filename 列，实际列: {list(rows[0].keys())}")

    out_rows = []
    n_missing = 0

    for r in rows:
        flair_fn  = r["filename"]                             # e.g. BraTS2021_01467_flair_13.png
        seg_fn    = flair_fn.replace("_flair_", "_seg_")     # -> BraTS2021_01467_seg_13.png
        seg_path  = ann_dir / seg_fn

        if not seg_path.exists():
            n_missing += 1
            out_rows.append({
                "filename":     flair_fn,
                "seg_filename": seg_fn,
                "n_components": "nan",  # 缺失 seg mask
            })
            continue

        n_comp = count_components_from_seg(seg_path)
        out_rows.append({
            "filename":     flair_fn,
            "seg_filename": seg_fn,
            "n_components": n_comp,
        })

    if n_missing > 0:
        print(f"[ncomp_brats] WARNING: {n_missing}/{len(rows)} 缺少 seg mask，n_components=nan")

    # 写 csv
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["filename", "seg_filename", "n_components"]
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
            f"[ncomp_brats] n={len(arr)} slices  "
            f"p25={np.percentile(arr, 25):.0f}  "
            f"median={np.median(arr):.0f}  "
            f"p75={np.percentile(arr, 75):.0f}  "
            f"max={arr.max()}"
        )
        print(f"  n_components==0: {(arr==0).sum()}")
        print(f"  n_components in [1,3]: {((arr>=1)&(arr<=3)).sum()} "
              f"({100*((arr>=1)&(arr<=3)).sum()/len(arr):.1f}%)")

    print(f"  -> {out_csv}  ({len(out_rows)} rows)")
    return out_rows


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "BraTS per-slice n_components 补充列\n"
            "口径: skimage.measure.label(bin_mask, connectivity=1) 4-连通\n"
            "与 CBIS/IDRiD lesion_features 完全一致\n"
            "输出 csv: results/ncomp_brats.csv  (filename + seg_filename + n_components)\n"
            "filename 与 stratify_per_image_ae.csv / brats_brain_px.csv join 键一致"
        )
    )
    _root = Path(__file__).resolve().parent.parent

    parser.add_argument(
        "--strat-csv",
        default=str(_root / "results" / "stratify_per_image_ae.csv"),
        help="BraTS per-image csv（含 filename 列，flair 命名），默认 results/stratify_per_image_ae.csv",
    )
    parser.add_argument(
        "--ann-dir",
        default=str(_root / "data" / "BraTS2021" / "test" / "annotation"),
        help="BraTS annotation 目录（含 *_seg_*.png），默认 data/BraTS2021/test/annotation/",
    )
    parser.add_argument(
        "--out-csv",
        default=str(_root / "results" / "ncomp_brats.csv"),
        help="输出 csv 路径，默认 results/ncomp_brats.csv",
    )

    args = parser.parse_args()
    run(
        strat_csv=args.strat_csv,
        ann_dir=args.ann_dir,
        out_csv=args.out_csv,
    )
