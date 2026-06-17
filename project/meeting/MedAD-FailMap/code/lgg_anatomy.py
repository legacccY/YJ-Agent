"""
lgg_anatomy.py — LGG 含瘤切片脑区近似 + area_ratio_brain_approx 提取
服务: MedAD-FailMap Phase 1 § STORY② 正臂锚事实核实
lever: LGG area_ratio_brain_approx vs BraTS area_ratio_brain 分布对比

背景（口径说明）：
  BraTS 已 skull-strip：非脑区=0，brain_px = nonzero + 最大连通域（brats_brain_px.py 口径）。
  LGG (Buda kaggle_3m) 未 skull-strip：直接 Otsu + 最大连通域 + 填洞近似脑区（非精确）。
  两者差异：
    BraTS : 精确 skull-strip，brain_px median ≈ 1619/4096（约 40% 全帧）
    LGG   : 近似脑区（Otsu 阈值 + 最大连通域 + 二值填洞），可能含颅骨灰质边缘
  ⚠️ 不可直接等同，仅作分布形状参考。

通道约定（README + 数据验证）：
  Buda .tif 3 通道顺序：ch0=pre-contrast, ch1=FLAIR, ch2=post-contrast
  （101/110 例成立；9 例缺 post→ch2=FLAIR 填充，6 例缺 pre→ch0=FLAIR 填充，ch1 始终=FLAIR）
  本脚本取 FLAIR=ch1。

resize 坐标系：
  与 brats_brain_px.csv 同口径：resize 到 64×64，size_px / brain_px 均在 64² 坐标系内。

输出:
  results/phase1/lesion_features_lgg_anatomy.csv
  列: filename / patient_id / size_px / n_components / area_ratio_full
      / brain_px_approx / area_ratio_brain_approx / approx_method

依赖: numpy, scikit-image, Pillow
不用 scipy（OMP#15），纯 CPU，Windows pathlib.Path
"""

import argparse
import csv
import sys
from pathlib import Path

import numpy as np
from PIL import Image


# ============================================================
# 常量
# ============================================================

_FLAIR_CH  = 1     # RGB ch1 = FLAIR（Buda et al. README 确认，ch0=pre, ch1=FLAIR, ch2=post）
_IMG_SIZE  = 64    # resize 目标，与 brats_brain_px.csv 同坐标系


# ============================================================
# 脑区近似（Otsu + 最大连通域 + 填洞）
# ============================================================

def _otsu_threshold_numpy(arr_float):
    """
    纯 numpy Otsu 阈值（0~1 归一化输入），不用 scipy。
    与 conspicuity_proxy.py _otsu_threshold_numpy 同实现逻辑。
    """
    n_bins = 256
    hist, bin_edges = np.histogram(arr_float, bins=n_bins, range=(0.0, 1.0))
    bin_centers = 0.5 * (bin_edges[:-1] + bin_edges[1:])
    hist = hist.astype(np.float64)
    total = hist.sum()
    if total == 0:
        return 0.5

    w0 = np.cumsum(hist) / total
    w1 = 1.0 - w0
    mu0_num = np.cumsum(hist * bin_centers)
    mu0 = np.where(w0 > 0, mu0_num / (w0 * total + 1e-12), 0.0)
    mu1_num = (hist * bin_centers).sum() - mu0_num
    mu1 = np.where(w1 > 0, mu1_num / (w1 * total + 1e-12), 0.0)

    between_var = w0 * w1 * (mu0 - mu1) ** 2
    best_idx = int(np.argmax(between_var))
    return float(bin_centers[best_idx])


def _approx_brain_mask(flair_small):
    """
    对 64×64 FLAIR 通道近似脑区 mask：
      1. 归一化到 [0,1]
      2. Otsu 阈值（numpy 实现）
      3. 取最大连通域（skimage label connectivity=1）
      4. 填洞（binary_fill_holes 等价：skimage morphology.remove_small_holes，
         或直接用 scipy.ndimage.binary_fill_holes —— 此处用 skimage flood_fill 替代
         以避免 scipy OMP 冲突；实际用 np.logical_not + flood_fill 近似填洞）

    Returns:
        brain_mask: bool array (64, 64)  True=近似脑区
        brain_px  : int  近似脑区像素数（64² 坐标系）
        method    : str  "otsu_maxconn_floodfill"
    """
    from skimage.measure import label as sk_label
    from skimage.morphology import remove_small_holes

    arr = flair_small.astype(np.float32)
    mx = arr.max()
    if mx > 0:
        arr_norm = arr / mx
    else:
        # 全黑切片（极少见），返回全零脑区
        return np.zeros(flair_small.shape, dtype=bool), 0, "otsu_maxconn_floodfill"

    # Otsu
    thresh = _otsu_threshold_numpy(arr_norm)
    binary = (arr_norm > thresh)

    # 最大连通域（4-连通）
    labeled = sk_label(binary, connectivity=1)
    if labeled.max() == 0:
        return np.zeros(flair_small.shape, dtype=bool), 0, "otsu_maxconn_floodfill"

    counts = np.bincount(labeled.ravel())
    counts[0] = 0  # 排背景
    max_label = int(np.argmax(counts))
    brain_mask = (labeled == max_label)

    # 填洞：remove_small_holes 将封闭在前景内的小孔填满（area_threshold 设全图大小确保全填）
    # skimage.morphology.remove_small_holes 用 area_threshold 控制最大洞大小
    area_thr = int(_IMG_SIZE * _IMG_SIZE)  # 允许填任意大小的洞
    try:
        # max_size 替代已废弃的 area_threshold（skimage >= 0.26）
        brain_mask = remove_small_holes(brain_mask, max_size=area_thr)
    except TypeError:
        # 旧版 skimage 用 area_threshold 参数名
        try:
            brain_mask = remove_small_holes(brain_mask, area_threshold=area_thr)
        except Exception:
            pass
    except Exception:
        pass  # 极端情况跳过填洞

    brain_px = int(brain_mask.sum())
    return brain_mask, brain_px, "otsu_maxconn_floodfill"


# ============================================================
# 单切片特征提取（含近似脑区）
# ============================================================

def extract_slice_features_anatomy(img_path, mask_path, img_size=_IMG_SIZE):
    """
    提取单切片几何特征（与 lesion_features_lgg.py 口径 + 近似脑区）。

    Args:
        img_path  : Path/str  RGB .tif（ch0=pre, ch1=FLAIR, ch2=post）
        mask_path : Path/str  binary mask .tif（前景=255）
        img_size  : int       resize 尺寸（默认 64）

    Returns dict:
        size_px              : int
        n_components         : int   4-连通
        area_ratio_full      : float  size_px / img_size²
        brain_px_approx      : int    近似脑区像素数（Otsu+最大连通域+填洞）
        area_ratio_brain_approx : float  size_px / brain_px_approx（若 brain_px=0 则 nan）
        approx_method        : str    "otsu_maxconn_floodfill"
    """
    from skimage.measure import label as sk_label
    from skimage.transform import resize as sk_resize

    # --- 读 mask ---
    mask_arr = np.array(Image.open(mask_path).convert("L"), dtype=np.uint8)
    if mask_arr.shape != (img_size, img_size):
        mask_small = sk_resize(
            mask_arr.astype(np.float32),
            (img_size, img_size),
            order=0,
            anti_aliasing=False,
            preserve_range=True,
        ).astype(np.uint8)
    else:
        mask_small = mask_arr
    bin_mask = (mask_small > 0).astype(np.uint8)

    # --- n_components & size_px（4-连通，与 ncomp_brats.py 逐字同口径）---
    if bin_mask.sum() == 0:
        n_comp  = 0
        size_px = 0
    else:
        labeled      = sk_label(bin_mask, connectivity=1)
        region_sizes = np.bincount(labeled.ravel())
        region_sizes[0] = 0
        n_comp  = int((region_sizes > 0).sum())
        size_px = int(region_sizes.sum())

    total_px        = float(img_size * img_size)
    area_ratio_full = float(size_px) / total_px

    # --- 读 FLAIR（ch1）用于近似脑区 ---
    img_rgb = np.array(Image.open(img_path).convert("RGB"), dtype=np.uint8)
    flair   = img_rgb[:, :, _FLAIR_CH]  # ch1 = FLAIR
    if flair.shape != (img_size, img_size):
        flair_small = sk_resize(
            flair.astype(np.float32),
            (img_size, img_size),
            order=1,         # bilinear
            anti_aliasing=True,
            preserve_range=True,
        ).astype(np.float32)
    else:
        flair_small = flair.astype(np.float32)

    brain_mask, brain_px, method = _approx_brain_mask(flair_small)

    # area_ratio_brain_approx = size_px / brain_px
    # 口径说明：BraTS brain_px 用 nonzero+最大连通域（精确 skull-strip），
    #           LGG 用 Otsu+最大连通域+填洞（近似，可能偏大或偏小）。
    # 若 brain_px == 0（全黑切片）则设为 nan；若 size_px > brain_px（近似误差）则 clip 到 1.0。
    if brain_px == 0:
        area_ratio_brain_approx = float("nan")
    else:
        ratio = float(size_px) / float(brain_px)
        area_ratio_brain_approx = min(ratio, 1.0)  # clip：近似误差可能使 tumor > brain_approx

    return {
        "size_px":                  size_px,
        "n_components":             n_comp,
        "area_ratio_full":          round(area_ratio_full, 6),
        "brain_px_approx":          brain_px,
        "area_ratio_brain_approx":  round(area_ratio_brain_approx, 6)
                                    if not np.isnan(area_ratio_brain_approx)
                                    else float("nan"),
        "approx_method":            method,
    }


# ============================================================
# 批量提取
# ============================================================

def batch_extract_lgg_anatomy(
    lgg_root,
    out_csv,
    img_size=_IMG_SIZE,
    smoke=False,
):
    """
    遍历 lgg_root/TCGA_*/ 下所有非空 mask 切片，提取近似脑区 area_ratio。

    输出 csv 列:
        filename / patient_id / size_px / n_components / area_ratio_full
        / brain_px_approx / area_ratio_brain_approx / approx_method
    """
    lgg_root = Path(lgg_root)
    out_csv  = Path(out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    patient_dirs = sorted([
        d for d in lgg_root.iterdir()
        if d.is_dir() and d.name.startswith("TCGA_")
    ])
    if not patient_dirs:
        raise FileNotFoundError(f"lgg_root 下无 TCGA_* 患者目录: {lgg_root}")

    all_mask_paths = []
    for pd in patient_dirs:
        all_mask_paths.extend(sorted(pd.glob("*_mask.tif")))

    if not all_mask_paths:
        raise FileNotFoundError(f"lgg_root 下无 *_mask.tif: {lgg_root}")

    fieldnames = [
        "filename", "patient_id",
        "size_px", "n_components", "area_ratio_full",
        "brain_px_approx", "area_ratio_brain_approx", "approx_method",
    ]

    rows       = []
    n_processed = 0
    n_skipped   = 0

    with open(out_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for mask_path in all_mask_paths:
            fname_stem = mask_path.name.replace("_mask.tif", "")
            img_path   = mask_path.parent / (fname_stem + ".tif")

            if not img_path.exists():
                print(f"[lgg_anatomy] WARNING: 图不存在跳过: {img_path}")
                n_skipped += 1
                continue

            # 快速判断 mask 非空
            mask_quick = np.array(Image.open(mask_path).convert("L"), dtype=np.uint8)
            if mask_quick.sum() == 0:
                n_skipped += 1
                continue

            patient_id = mask_path.parent.name

            try:
                feats = extract_slice_features_anatomy(img_path, mask_path, img_size=img_size)
            except Exception as e:
                print(f"[lgg_anatomy] ERROR on {img_path.name}: {e}")
                n_skipped += 1
                continue

            row = {
                "filename":                 mask_path.name.replace("_mask.tif", ".tif"),
                "patient_id":               patient_id,
                "size_px":                  feats["size_px"],
                "n_components":             feats["n_components"],
                "area_ratio_full":          feats["area_ratio_full"],
                "brain_px_approx":          feats["brain_px_approx"],
                "area_ratio_brain_approx":  feats["area_ratio_brain_approx"],
                "approx_method":            feats["approx_method"],
            }
            writer.writerow(row)
            rows.append(row)
            n_processed += 1

            if smoke and n_processed >= 5:
                print(f"[lgg_anatomy] smoke=True，处理 {n_processed} 张后停止")
                break

    # --- 统计 ---
    if rows:
        ratio_arr = np.array([
            float(r["area_ratio_brain_approx"])
            for r in rows
            if str(r["area_ratio_brain_approx"]) not in ("nan", "")
        ], dtype=float)

        if len(ratio_arr) > 0:
            print(
                f"\n[lgg_anatomy] 完成: n={n_processed} 含肿瘤切片, 跳过 {n_skipped}"
            )
            print(
                f"  area_ratio_brain_approx: "
                f"P25={np.percentile(ratio_arr, 25):.4f}  "
                f"med={np.percentile(ratio_arr, 50):.4f}  "
                f"P75={np.percentile(ratio_arr, 75):.4f}"
            )
            print(f"  -> {out_csv} ({n_processed} rows)")
    else:
        print("[lgg_anatomy] WARNING: 无有效行输出")

    return rows


# ============================================================
# 分位对比报告（LGG approx vs BraTS exact）
# ============================================================

def report_quantile_comparison(lgg_rows, brats_brain_px_csv):
    """
    打印 LGG area_ratio_brain_approx 与 BraTS area_ratio_brain 的分位对比。
    ⚠️ 仅报事实分布，不做 iso 判定。

    Args:
        lgg_rows           : batch_extract_lgg_anatomy 返回的 list of dict
        brats_brain_px_csv : results/brats_brain_px.csv（含 area_ratio_brain 列）
    """
    # LGG approx
    lgg_arr = np.array([
        float(r["area_ratio_brain_approx"])
        for r in lgg_rows
        if str(r["area_ratio_brain_approx"]) not in ("nan", "")
    ], dtype=float)

    # BraTS exact
    brats_arr = []
    with open(brats_brain_px_csv, newline="") as f:
        for row in csv.DictReader(f):
            v = row.get("area_ratio_brain", "")
            if v not in ("", "nan"):
                brats_arr.append(float(v))
    brats_arr = np.array(brats_arr, dtype=float)

    print("\n" + "=" * 60)
    print("[分位对比] LGG area_ratio_brain_approx vs BraTS area_ratio_brain")
    print("  [!] 口径差异：LGG=Otsu近似脑区（未精确skull-strip）；"
          "BraTS=精确skull-strip（nonzero+最大连通域）")
    print(f"  LGG  n={len(lgg_arr)}")
    if len(lgg_arr) > 0:
        print(
            f"  LGG  P25={np.percentile(lgg_arr,25):.4f}  "
            f"med={np.percentile(lgg_arr,50):.4f}  "
            f"P75={np.percentile(lgg_arr,75):.4f}"
        )
    print(f"  BraTS n={len(brats_arr)}")
    if len(brats_arr) > 0:
        print(
            f"  BraTS P25={np.percentile(brats_arr,25):.4f}  "
            f"med={np.percentile(brats_arr,50):.4f}  "
            f"P75={np.percentile(brats_arr,75):.4f}"
        )
    print("=" * 60)


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "LGG 含瘤切片近似脑区面积比提取\n"
            "输出: results/phase1/lesion_features_lgg_anatomy.csv\n"
            "仅报分布事实，不做 iso 判定（判据由 planner 设计）"
        )
    )
    _root = Path(__file__).resolve().parent.parent
    _res  = _root / "results"
    _data = Path("D:/YJ-Agent/data/external/lgg_mri_seg/kaggle_3m")

    parser.add_argument(
        "--lgg-root",
        default=str(_data),
    )
    parser.add_argument(
        "--out-csv",
        default=str(_res / "phase1" / "lesion_features_lgg_anatomy.csv"),
    )
    parser.add_argument(
        "--brats-brain-px-csv",
        default=str(_res / "brats_brain_px.csv"),
        help="BraTS brain_px csv（含 area_ratio_brain 列，用于分位对比）",
    )
    parser.add_argument(
        "--img-size",
        type=int,
        default=64,
    )
    parser.add_argument(
        "--smoke",
        type=int,
        default=0,
        help="冒烟：只处理前 N 张非空切片（0=全量）",
    )

    args = parser.parse_args()

    rows = batch_extract_lgg_anatomy(
        lgg_root=args.lgg_root,
        out_csv=args.out_csv,
        img_size=args.img_size,
        smoke=(args.smoke > 0),
    )

    if rows and Path(args.brats_brain_px_csv).exists():
        report_quantile_comparison(rows, args.brats_brain_px_csv)
