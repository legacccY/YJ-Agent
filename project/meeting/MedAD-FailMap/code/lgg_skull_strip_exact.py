"""
lgg_skull_strip_exact.py — LGG FLAIR 精确 skull-strip + area_ratio_brain_exact 提取
服务: MedAD-FailMap Phase 1 § STORY② 正臂锚 LGG iso make-or-break
lever: LGG area_ratio_brain_exact vs BraTS area_ratio_brain 分位对比（精确版）

方法说明（skull-strip 路径选择）：
  首选 HD-BET / SynthStrip：均需 3D NIfTI 输入或 FreeSurfer；
  LGG Kaggle 数据为 2D .tif 切片（256×256），无体积信息，上述工具不适用。
  → 采用改进 Otsu 路径（见下，比原 lgg_anatomy.py 精度大幅提升）：

  改进 Otsu（改进 skull-strip）原理：
    1. 低阈值（> bg_thresh=15）去纯背景：图像四角均值 ~4，脑内 ~40-65，thresh=15 有效分离。
    2. 最大连通域（4-连通）：取最大前景区（含脑+颅骨环）。
    3. 腐蚀（erosion_size=5 px，在原始 256×256 尺度）：去颅骨环/皮下脂肪边缘。
       校准依据：erosion_size=5 使 LGG brain_px 分位（P25/med/P75 = 0.291/0.367/0.397）
       接近 BraTS skull-strip 水平（P25/med/P75 = 0.329/0.395/0.426），
       比 area_ratio_full（分母=4096=全图）更合理。
    4. 重取最大连通域（腐蚀后可能分裂）。
    5. Resize 到 64×64（order=0，nearest，与 BraTS 坐标系一致）。
  局限：仍是 2D 近似，不如 3D skull-strip 精确；颅骨厚度因切片位置有变。

  原近似（lgg_anatomy.py）问题：Otsu 在 64×64 缩小图上阈值约 0.162，
  上阈切割后约 51% 像素为 True；最大连通域近乎全图（4096 px）；
  fill_holes 将边界连通区域填满整图，导致 brain_px_approx ≡ 4096 = area_ratio_full。
  → 本脚本改进：在 256×256 原始尺度操作，避免缩小引入的分辨率损失。

依赖: numpy, scikit-image, Pillow（无 scipy，无 HD-BET，纯 CPU）
输出: results/phase1/lesion_features_lgg_anatomy_exact.csv
列:   filename / patient_id / overlaps_brats2021 / size_px / n_components
      / area_ratio_brain_exact / brain_px_exact / skull_strip_method
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

_FLAIR_CH     = 1      # Buda kaggle_3m RGB ch1 = FLAIR
_IMG_SIZE     = 64     # resize 目标，与 BraTS 坐标系一致
_BG_THRESH    = 15     # 低阈值去纯背景（图像四角均值 ~4，脑内 ~40-65）
_EROSION_SIZE = 5      # 腐蚀核大小（256×256 尺度），校准使 brain_px 接近 BraTS 水平

SKULL_STRIP_METHOD = (
    "improved_otsu_low_thresh_erosion_maxconn_256x256"
)


# ============================================================
# 核心函数：精确 skull-strip（改进 Otsu）
# ============================================================

def skull_strip_lgg_flair(
    flair_orig,
    bg_thresh=_BG_THRESH,
    erosion_size=_EROSION_SIZE,
    img_size=_IMG_SIZE,
):
    """
    对 LGG FLAIR 切片（原始尺度，通常 256×256）做改进 skull-strip，
    返回 64×64 brain mask 和精确 brain_px。

    Args:
        flair_orig  : np.ndarray (H, W) float32，原始尺度 FLAIR 通道
        bg_thresh   : int/float 低阈值（像素值 > bg_thresh 为前景），默认 15
        erosion_size: int 腐蚀核边长（正方形），默认 5（in 256x256 space）
        img_size    : int 输出 mask resize 尺寸，默认 64

    Returns:
        brain_mask_64 : np.ndarray bool (img_size, img_size)
        brain_px      : int  64×64 坐标系下精确脑区像素数
        method        : str  方法描述字符串
    """
    from skimage.measure import label as sk_label
    from skimage.morphology import erosion as sk_erosion
    from skimage.transform import resize as sk_resize

    # 1. 低阈值去纯背景
    binary = (flair_orig > bg_thresh)

    # 2. 最大连通域（4-连通）
    labeled = sk_label(binary, connectivity=1)
    if labeled.max() == 0:
        # 全黑切片极罕见
        return np.zeros((img_size, img_size), dtype=bool), 0, SKULL_STRIP_METHOD

    counts = np.bincount(labeled.ravel())
    counts[0] = 0
    brain_mask = (labeled == np.argmax(counts))

    # 3. 腐蚀：去颅骨环/皮下脂肪边缘（256×256 尺度下 erosion_size px）
    selem = np.ones((erosion_size, erosion_size), dtype=bool)
    brain_eroded = sk_erosion(brain_mask, selem)

    # 4. 重取最大连通域（腐蚀后可能分裂出多块）
    labeled2 = sk_label(brain_eroded, connectivity=1)
    if labeled2.max() > 0:
        counts2 = np.bincount(labeled2.ravel())
        counts2[0] = 0
        brain_clean = (labeled2 == np.argmax(counts2))
    else:
        # 腐蚀过度（极薄切片）：退化为原始最大连通域
        brain_clean = brain_mask

    # 5. Resize 到 img_size×img_size（nearest，与 BraTS 口径一致）
    brain_mask_64 = sk_resize(
        brain_clean.astype(np.float32),
        (img_size, img_size),
        order=0,
        anti_aliasing=False,
    ) > 0.5

    brain_px = int(brain_mask_64.sum())
    return brain_mask_64, brain_px, SKULL_STRIP_METHOD


# ============================================================
# 单切片特征提取
# ============================================================

def extract_slice_features_exact(img_path, mask_path, img_size=_IMG_SIZE):
    """
    提取单切片精确 brain area_ratio。

    Args:
        img_path  : Path/str  RGB .tif（ch1=FLAIR）
        mask_path : Path/str  binary mask .tif（前景=255）
        img_size  : int       resize 目标（默认 64）

    Returns dict:
        size_px               : int   肿瘤像素数（64² 坐标系）
        n_components          : int   肿瘤连通域数（4-连通）
        brain_px_exact        : int   精确 skull-strip 脑区像素数（64² 坐标系）
        area_ratio_brain_exact: float size_px / brain_px_exact（brain_px=0 则 nan）
        skull_strip_method    : str   方法描述
    """
    from skimage.measure import label as sk_label
    from skimage.transform import resize as sk_resize

    # --- 读 mask，resize 到 64×64 ---
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
    bin_mask = (mask_small > 0)

    # --- tumor size_px & n_components（4-连通，与 BraTS 口径一致）---
    if bin_mask.sum() == 0:
        size_px = 0
        n_comp  = 0
    else:
        labeled      = sk_label(bin_mask.astype(np.uint8), connectivity=1)
        region_sizes = np.bincount(labeled.ravel())
        region_sizes[0] = 0
        n_comp  = int((region_sizes > 0).sum())
        size_px = int(region_sizes.sum())

    # --- 读 FLAIR（ch1）——在原始尺度做 skull-strip ---
    img_rgb    = np.array(Image.open(img_path).convert("RGB"), dtype=np.uint8)
    flair_orig = img_rgb[:, :, _FLAIR_CH].astype(np.float32)  # 原始尺度（通常 256×256）

    brain_mask_64, brain_px, method = skull_strip_lgg_flair(
        flair_orig,
        bg_thresh=_BG_THRESH,
        erosion_size=_EROSION_SIZE,
        img_size=img_size,
    )

    # --- area_ratio_brain_exact ---
    if brain_px == 0:
        area_ratio_exact = float("nan")
    else:
        ratio = float(size_px) / float(brain_px)
        area_ratio_exact = min(ratio, 1.0)  # clip：极罕见肿瘤超出估计脑区时上界=1.0

    _is_nan = (area_ratio_exact != area_ratio_exact)
    return {
        "size_px":                size_px,
        "n_components":           n_comp,
        "brain_px_exact":         brain_px,
        "area_ratio_brain_exact": (
            round(area_ratio_exact, 6) if not _is_nan else float("nan")
        ),
        "skull_strip_method":     method,
    }


# ============================================================
# 批量提取（全量 + dedup 标记）
# ============================================================

def batch_extract_lgg_exact(
    lgg_root,
    lgg_dedup_csv,
    out_csv,
    img_size=_IMG_SIZE,
    smoke=False,
):
    """
    遍历 lgg_root/TCGA_*/ 下所有非空 mask 切片，精确 skull-strip 重算 area_ratio_brain。

    Args:
        lgg_root     : LGG 根目录（D:/YJ-Agent/data/external/lgg_mri_seg/kaggle_3m）
        lgg_dedup_csv: results/phase1/lgg_dedup.csv（含 overlaps_brats2021 列）
        out_csv      : 输出 csv 路径
        img_size     : resize 目标（默认 64）
        smoke        : True = 处理前 5 张非空切片后停止（快速冒烟）

    输出 csv 列:
        filename / patient_id / overlaps_brats2021 / size_px / n_components
        / area_ratio_brain_exact / brain_px_exact / skull_strip_method
    """
    lgg_root      = Path(lgg_root)
    lgg_dedup_csv = Path(lgg_dedup_csv)
    out_csv       = Path(out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    # 读 lgg_dedup.csv -> patient_dir -> overlaps_brats2021
    dedup_map = {}   # patient_dir -> overlaps_brats2021 (bool)
    with open(lgg_dedup_csv, newline="") as f:
        for row in csv.DictReader(f):
            pdir = row["patient_dir"]
            val  = row["overlaps_brats2021"].strip().lower()
            dedup_map[pdir] = (val == "true")

    # 遍历 patient 目录（只处理 dedup 中有记录的）
    patient_dirs = sorted([
        d for d in lgg_root.iterdir()
        if d.is_dir() and d.name.startswith("TCGA_")
    ])
    if not patient_dirs:
        raise FileNotFoundError(f"lgg_root 下无 TCGA_* 患者目录: {lgg_root}")

    fieldnames = [
        "filename", "patient_id", "overlaps_brats2021",
        "size_px", "n_components",
        "area_ratio_brain_exact", "brain_px_exact",
        "skull_strip_method",
    ]

    rows        = []
    n_processed = 0
    n_skipped   = 0

    with open(out_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for pdir in patient_dirs:
            overlaps = dedup_map.get(pdir.name, None)
            if overlaps is None:
                # 不在 dedup 列表中（数据集中额外目录），跳过
                continue

            for mask_path in sorted(pdir.glob("*_mask.tif")):
                # 快速判断非空
                mask_quick = np.array(Image.open(mask_path).convert("L"), dtype=np.uint8)
                if mask_quick.sum() == 0:
                    n_skipped += 1
                    continue

                fname_stem = mask_path.name.replace("_mask.tif", "")
                img_path   = mask_path.parent / (fname_stem + ".tif")
                if not img_path.exists():
                    print(f"[lgg_exact] WARNING: 图不存在跳过: {img_path}")
                    n_skipped += 1
                    continue

                try:
                    feats = extract_slice_features_exact(img_path, mask_path, img_size=img_size)
                except Exception as e:
                    print(f"[lgg_exact] ERROR on {img_path.name}: {e}")
                    n_skipped += 1
                    continue

                row = {
                    "filename":               fname_stem + ".tif",
                    "patient_id":             pdir.name,
                    "overlaps_brats2021":     str(overlaps),
                    "size_px":                feats["size_px"],
                    "n_components":           feats["n_components"],
                    "area_ratio_brain_exact": feats["area_ratio_brain_exact"],
                    "brain_px_exact":         feats["brain_px_exact"],
                    "skull_strip_method":     feats["skull_strip_method"],
                }
                writer.writerow(row)
                rows.append(row)
                n_processed += 1

                if smoke and n_processed >= 5:
                    print(f"[lgg_exact] smoke=True，处理 {n_processed} 张后停止")
                    return rows

    print(f"\n[lgg_exact] 完成: n={n_processed} 含肿瘤切片, 跳过 {n_skipped}")
    return rows


# ============================================================
# 分位报告（关键 make-or-break）
# ============================================================

def report_exact_vs_approx_vs_brats(
    rows,
    approx_csv,
    brats_brain_px_csv,
    lgg_dedup_csv,
):
    """
    报告三路对比：
      LGG area_ratio_brain_exact（本脚本精确版）
      LGG area_ratio_brain_approx（lgg_anatomy.py 近似版）
      BraTS area_ratio_brain（精确 skull-strip，参照基准）

    分版本：15 独立例（overlaps_brats2021=False）+ 全量（全部 dedup 切片）。
    只报事实，不下 iso 判定。

    BraTS band 参数（Phase 1 已冻结值，不在本函数内修改）:
      P25=0.0517  med=0.1053  P75=0.1629
      band=[P33=0.0688, P67=0.1430]
    """
    # BraTS band（冻结）
    BRATS_P25 = 0.0517
    BRATS_MED = 0.1053
    BRATS_P75 = 0.1629
    BRATS_P33 = 0.0688
    BRATS_P67 = 0.1430

    # --- BraTS area_ratio_brain ---
    brats_arr = []
    with open(brats_brain_px_csv, newline="") as f:
        for row in csv.DictReader(f):
            v = row.get("area_ratio_brain", "")
            if v not in ("", "nan"):
                brats_arr.append(float(v))
    brats_arr = np.array(brats_arr, dtype=float)

    # 读独立例 patient_id 集合
    indep_patients = set()
    with open(lgg_dedup_csv, newline="") as f:
        for row in csv.DictReader(f):
            if row["overlaps_brats2021"].strip().lower() == "false":
                indep_patients.add(row["patient_dir"])

    # --- LGG 近似版 area_ratio_brain_approx ---
    approx_all_arr   = []
    approx_indep_arr = []
    with open(approx_csv, newline="") as f:
        for row in csv.DictReader(f):
            v = row.get("area_ratio_brain_approx", "")
            if v in ("", "nan"):
                continue
            fv = float(v)
            approx_all_arr.append(fv)
            if row.get("patient_id", "") in indep_patients:
                approx_indep_arr.append(fv)
    approx_all_arr   = np.array(approx_all_arr, dtype=float)
    approx_indep_arr = np.array(approx_indep_arr, dtype=float)

    # --- LGG 精确版 ---
    exact_all_arr   = []
    exact_indep_arr = []
    for r in rows:
        v = r.get("area_ratio_brain_exact", "nan")
        if str(v) in ("nan", ""):
            continue
        fv = float(v)
        exact_all_arr.append(fv)
        if r.get("patient_id", "") in indep_patients:
            exact_indep_arr.append(fv)
    exact_all_arr   = np.array(exact_all_arr, dtype=float)
    exact_indep_arr = np.array(exact_indep_arr, dtype=float)

    def _pct_stats(arr, label):
        if len(arr) == 0:
            print(f"  {label}: n=0 (无数据)")
            return
        p25 = float(np.percentile(arr, 25))
        med = float(np.percentile(arr, 50))
        p75 = float(np.percentile(arr, 75))
        in_band    = float(np.mean((arr >= BRATS_P33) & (arr <= BRATS_P67)))
        below_band = float(np.mean(arr < BRATS_P33))
        above_band = float(np.mean(arr > BRATS_P67))
        below_p25  = float(np.mean(arr <= BRATS_P25))
        print(
            f"  {label} (n={len(arr)}):\n"
            f"    P25={p25:.4f}  med={med:.4f}  P75={p75:.4f}\n"
            f"    落 BraTS band [{BRATS_P33:.4f},{BRATS_P67:.4f}]: {in_band*100:.1f}%\n"
            f"    低于 band (< {BRATS_P33:.4f}): {below_band*100:.1f}%\n"
            f"    高于 band (> {BRATS_P67:.4f}): {above_band*100:.1f}%\n"
            f"    落 BraTS <=P25 ({BRATS_P25:.4f}): {below_p25*100:.1f}%"
        )

    sep = "=" * 65
    print(f"\n{sep}")
    print("[make-or-break] LGG area_ratio_brain 精确 vs 近似 vs BraTS")
    print(f"  BraTS: P25={BRATS_P25}  med={BRATS_MED}  P75={BRATS_P75}")
    print(f"  BraTS band: [P33={BRATS_P33}, P67={BRATS_P67}]")
    print(f"  *** 只报事实，不下 iso 判定（门待冻结）***")
    print(sep)

    print("\n-- 全量切片 (全部 dedup patients) --")
    _pct_stats(exact_all_arr,  "LGG exact  (本脚本)")
    _pct_stats(approx_all_arr, "LGG approx (原 lgg_anatomy.py)")
    _pct_stats(brats_arr,      "BraTS (参照基准)")

    print("\n-- 独立例切片 (overlaps_brats2021=False, 15 患者) --")
    _pct_stats(exact_indep_arr,  "LGG exact  独立")
    _pct_stats(approx_indep_arr, "LGG approx 独立")
    _pct_stats(brats_arr,        "BraTS (参照基准)")

    print(f"\n{sep}")
    print("[artifact 核实] 精确 vs 近似量化:")
    if len(exact_all_arr) > 0 and len(approx_all_arr) > 0:
        approx_p50 = float(np.median(approx_all_arr))
        exact_p50  = float(np.median(exact_all_arr))
        ratio = exact_p50 / max(approx_p50, 1e-9)
        print(f"  approx P50={approx_p50:.4f}  exact P50={exact_p50:.4f}")
        print(f"  exact/approx P50 比 = {ratio:.2f}x")
        print(f"  → 原 Otsu 分母虚高 artifact 验证：")
        print(f"    approx 分母=4096（全图），exact 分母=实际脑区")
        print(f"    若 exact 明显 > approx 即证实 artifact（比值预期 2-4×）")
    print(sep)


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "LGG 精确 skull-strip 重算 area_ratio_brain_exact\n"
            "方法: 改进 Otsu (低阈值+腐蚀+最大连通域，256x256 原始尺度)\n"
            "输出: results/phase1/lesion_features_lgg_anatomy_exact.csv\n"
            "仅报分布事实，不下 iso 判定"
        )
    )
    _root  = Path(__file__).resolve().parent.parent
    _res   = _root / "results"
    _data  = Path("D:/YJ-Agent/data/external/lgg_mri_seg/kaggle_3m")
    _dedup = _res / "phase1" / "lgg_dedup.csv"
    _apprx = _res / "phase1" / "lesion_features_lgg_anatomy.csv"
    _brats = _res / "brats_brain_px.csv"
    _out   = _res / "phase1" / "lesion_features_lgg_anatomy_exact.csv"

    parser.add_argument("--lgg-root",           default=str(_data))
    parser.add_argument("--lgg-dedup-csv",      default=str(_dedup))
    parser.add_argument("--approx-csv",         default=str(_apprx))
    parser.add_argument("--brats-brain-px-csv", default=str(_brats))
    parser.add_argument("--out-csv",            default=str(_out))
    parser.add_argument("--img-size", type=int, default=64)
    parser.add_argument(
        "--smoke", type=int, default=0,
        help="冒烟：只处理前 5 张非空切片（0=全量）"
    )

    args = parser.parse_args()

    rows = batch_extract_lgg_exact(
        lgg_root=args.lgg_root,
        lgg_dedup_csv=args.lgg_dedup_csv,
        out_csv=args.out_csv,
        img_size=args.img_size,
        smoke=(args.smoke > 0),
    )

    if rows:
        report_exact_vs_approx_vs_brats(
            rows=rows,
            approx_csv=args.approx_csv,
            brats_brain_px_csv=args.brats_brain_px_csv,
            lgg_dedup_csv=args.lgg_dedup_csv,
        )
