"""
lesion_features_cbis.py — CBIS-DDSM 乳腺 X 线 mass 适配器（Phase 1 G1-a 正臂）
服务: MedAD-FailMap Phase 1, PC-B Gate1 G1-a 几何同构验证
lever: 机制公平面积比（mass/breast 对应 BraTS tumor/brain）

核心机制说明：
  mammogram 全图含大片黑边（乳腺只占画面 40-60%）。
  若 area_ratio 分母用全图 64²，mass 比例被黑边假性压小，
  与 BraTS（脑组织几乎占满切片）机制不可比。
  机制公平面积比：area_ratio_breast = mass_px / breast_px（乳腺组织区域像素）
  对照敏感性：area_ratio_full  = mass_px / full_frame_px（全图，暴露黑边偏差）

乳腺区域分割：
  Otsu 阈值（skimage.filters.threshold_otsu）取最大连通域 = 乳腺组织 mask。
  不用 scipy（OMP#15），不用 torch。

CBIS-DDSM 数据集（awsaf49 版）：
  TODO: 待数据到位后确认真实目录结构。
  当前假设：
    --img-dir   : 全乳 mammogram PNG 目录（每张 = 一个 case 的全乳图）
    --mask-dir  : ROI mask PNG 目录（二值 mask，同名或通过 meta csv 关联）
    --meta-csv  : CBIS metadata csv，含 abnormality_type 列（mass/calcification）
  只处理 mass 子集，排 calcification（calcification 多斑点散簇，几何不齐 BraTS 单瘤）。

输出 per-image csv schema：
  image_id, mass_px, breast_px, full_frame_px,
  area_ratio_breast (= mass_px / breast_px, 主，机制公平),
  area_ratio_full   (= mass_px / full_frame_px, 敏感性对照),
  n_components      (mass ROI 连通域数，供审查；多 ROI 取最大),
  contrast          (相对环宽，复用 lesion_features 几何函数),
  dilation_px, ring_width_frac,
  breast_otsu_threshold (乳腺 Otsu 阈值，供调试)

与 BraTS 机制对齐说明：
  BraTS 现有 area_ratio = size_px / (64*64) = tumor/全图（Phase 0 定义）。
  公平对比需 BraTS 侧也用 tumor/脑组织。
  本模块不动 Phase 0 BraTS csv；BraTS 脑组织 Otsu 由 area_ratio_check.py
  扩展参数 --brats-brain-mask-dir 处理（新增列，不改旧 csv）。
  # TODO: BraTS 脑组织 Otsu 分母待主线拍板后启动，确保两端机制完全对称。

依赖: numpy, scikit-image (Otsu + 连通域), Pillow
不用 scipy（OMP#15），Windows 路径用 pathlib.Path
"""

import argparse
import csv
from pathlib import Path

import numpy as np
from PIL import Image


# ============================================================
# 乳腺组织分割 (Otsu + 最大连通域)
# ============================================================

def segment_breast(img_arr_gray):
    """
    对全乳灰度图做 Otsu 阈值，取最大连通域作为乳腺组织 mask。
    去黑边逻辑：黑边灰度接近 0，乳腺组织灰度高于背景。

    img_arr_gray: (H,W) uint8 或 float32 [0,1] 均可（内部统一转 float32 [0,1]）。

    返回:
      breast_mask : (H,W) bool，True = 乳腺组织
      otsu_thr    : float，Otsu 阈值（float [0,1] 归一化）
      breast_px   : int，乳腺组织像素数
    """
    from skimage.filters import threshold_otsu
    from skimage.measure import label as sk_label

    # 统一归一化到 [0,1]
    if img_arr_gray.dtype == np.uint8:
        arr_f = img_arr_gray.astype(np.float32) / 255.0
    else:
        arr_f = img_arr_gray.astype(np.float32)

    # Otsu 阈值（skimage 实现，无 scipy）
    otsu_thr = float(threshold_otsu(arr_f))

    # 二值化：大于 Otsu → 前景（乳腺组织）
    binary = (arr_f > otsu_thr).astype(np.uint8)

    if binary.sum() == 0:
        # 极端情况：全黑图，乳腺 mask 为空
        return np.zeros_like(binary, dtype=bool), otsu_thr, 0

    # 取最大连通域（4-连通），排除散点噪声
    labeled = sk_label(binary, connectivity=1)
    region_sizes = np.bincount(labeled.ravel())
    region_sizes[0] = 0  # 排除背景 label 0
    largest_label = int(region_sizes.argmax())

    breast_mask = (labeled == largest_label)
    breast_px = int(breast_mask.sum())

    return breast_mask, otsu_thr, breast_px


# ============================================================
# Mass ROI 提取（最大连通域 + n_components 记录）
# ============================================================

def extract_mass_roi(roi_mask_arr):
    """
    从二值 ROI mask 取 mass 连通域。
    mass 子集（单瘤）理论上应只有 1 个连通域；
    若有多个（分裂 mask），取最大连通域，记录 n_components 供审查。

    roi_mask_arr: (H,W) uint8，>127 为前景。

    返回:
      mass_mask   : (H,W) bool，最大连通域
      mass_px     : int，mass 像素数
      n_components: int，连通域总数（>1 说明 mask 有分裂，需人工审查）
    """
    from skimage.measure import label as sk_label

    bin_mask = (roi_mask_arr > 127).astype(np.uint8)
    if bin_mask.sum() == 0:
        return np.zeros_like(bin_mask, dtype=bool), 0, 0

    labeled = sk_label(bin_mask, connectivity=1)
    region_sizes = np.bincount(labeled.ravel())
    region_sizes[0] = 0

    n_components = int((region_sizes > 0).sum())
    largest_label = int(region_sizes.argmax())

    mass_mask = (labeled == largest_label)
    mass_px = int(mass_mask.sum())

    return mass_mask, mass_px, n_components


# ============================================================
# 对比度（相对环宽，复用 lesion_features 几何结构）
# ============================================================

def compute_contrast_relative_cbis(img_arr_float, mass_mask, ring_width_frac=0.075):
    """
    contrast = |mean(img[mass]) - mean(img[ring])|
    ring = dilation(mass_mask, dilation_px) XOR mass_mask
    dilation_px = max(1, round(equiv_diameter * ring_width_frac))
      equiv_diameter = sqrt(4 * mass_px / pi)

    与 lesion_features.compute_contrast_relative 结构一致，接受已提取的 mass_mask。
    ring_width_frac 三档 {0.05, 0.075, 0.10}（Phase 1 敏感性扫描）。

    返回 (contrast: float, dilation_px: int)
    """
    from skimage.morphology import dilation, disk

    if mass_mask.sum() == 0:
        return 0.0, 0

    mass_px = int(mass_mask.sum())
    equiv_diam = float(np.sqrt(4.0 * mass_px / np.pi))
    dilation_px = max(1, round(equiv_diam * ring_width_frac))

    dilated = dilation(mass_mask.astype(np.uint8), footprint=disk(dilation_px)).astype(bool)
    ring = dilated & (~mass_mask)

    if ring.sum() == 0:
        return 0.0, dilation_px

    lesion_mean = float(img_arr_float[mass_mask].mean())
    ring_mean = float(img_arr_float[ring].mean())
    return abs(lesion_mean - ring_mean), dilation_px


# ============================================================
# 单图特征提取
# ============================================================

def extract_cbis_features(img_path, mask_path, ring_width_frac=0.075, img_size=None):
    """
    给定全乳 mammogram + ROI mask，返回 CBIS mass 特征 dict。

    img_path:  全乳 mammogram（PNG/JPG），灰度或 RGB（内部转灰度）
    mask_path: ROI mask（PNG），二值（>127 = mass 区域）
    ring_width_frac: 相对环宽（等效直径百分比），Phase 1 三档 {0.05, 0.075, 0.10}
    img_size: 若非 None，两者均 resize 到 img_size × img_size 再算特征
              Phase 1 须传 64（与 BraTS 64px 坐标系一致）
              # TODO: Phase 1 运行时传 --img-size 64，待主线确认

    返回 dict:
      {
        "mass_px":               int,   # mass ROI 像素数（最大连通域）
        "breast_px":             int,   # 乳腺组织像素数（Otsu 分割）
        "full_frame_px":         int,   # 全图像素数（H×W）
        "area_ratio_breast":     float, # mass_px / breast_px（主，机制公平）
        "area_ratio_full":       float, # mass_px / full_frame_px（敏感性对照）
        "n_components":          int,   # mass ROI 连通域数（>1 需人工审查）
        "contrast":              float, # 相对环宽对比度
        "dilation_px":           int,   # 实际使用的环宽 px
        "ring_width_frac":       float,
        "breast_otsu_threshold": float, # Otsu 阈值（供调试）
        "orig_h":                int,   # 原始图高度（resize 前）
        "orig_w":                int,   # 原始图宽度（resize 前）
      }
    """
    # 读全乳图（灰度）
    pil_img = Image.open(img_path).convert("L")
    orig_h, orig_w = pil_img.size[1], pil_img.size[0]

    # 读 ROI mask
    pil_mask = Image.open(mask_path).convert("L")

    # resize（若指定 img_size）
    if img_size is not None:
        pil_img  = pil_img.resize((img_size, img_size), Image.BILINEAR)
        pil_mask = pil_mask.resize((img_size, img_size), Image.NEAREST)

    img_arr  = np.array(pil_img, dtype=np.uint8)
    mask_arr = np.array(pil_mask, dtype=np.uint8)

    # 乳腺组织分割（Otsu）
    breast_mask, otsu_thr, breast_px = segment_breast(img_arr)

    # Mass ROI 提取
    mass_mask, mass_px, n_components = extract_mass_roi(mask_arr)

    # 全图像素
    full_h, full_w = img_arr.shape[:2]
    full_frame_px = full_h * full_w

    # area_ratio 计算
    # area_ratio_breast: 主要指标，机制公平（mass 相对于乳腺组织）
    if breast_px > 0:
        area_ratio_breast = mass_px / breast_px
    else:
        area_ratio_breast = float("nan")  # 乳腺分割失败（极端黑图）

    # area_ratio_full: 敏感性对照（含黑边偏差，暴露与 BraTS 全图分母的差异）
    area_ratio_full = mass_px / full_frame_px if full_frame_px > 0 else float("nan")

    # 对比度（相对环宽）
    img_float = img_arr.astype(np.float32) / 255.0
    contrast, dilation_px = compute_contrast_relative_cbis(
        img_float, mass_mask, ring_width_frac=ring_width_frac
    )

    return {
        "mass_px":               mass_px,
        "breast_px":             breast_px,
        "full_frame_px":         full_frame_px,
        "area_ratio_breast":     float(area_ratio_breast),
        "area_ratio_full":       float(area_ratio_full),
        "n_components":          n_components,
        "contrast":              float(contrast),
        "dilation_px":           dilation_px,
        "ring_width_frac":       ring_width_frac,
        "breast_otsu_threshold": otsu_thr,
        "orig_h":                orig_h,
        "orig_w":                orig_w,
    }


# ============================================================
# Meta CSV 解析 — mass 过滤
# ============================================================

def load_mass_image_ids(meta_csv_path):
    """
    从 CBIS metadata csv 读 mass 子集的 image_id 集合，排 calcification。

    CBIS-DDSM awsaf49 版 metadata csv 期望含以下列（大小写不敏感）：
      - image_id（或 image id / filename）
      - abnormality_type（或 abnormality type / type）

    过滤条件：abnormality_type.strip().lower() == "mass"

    TODO: CBIS-DDSM awsaf49 版实际列名待数据到位后确认。
          如列名不同，调整下方 _try_col 列表即可，逻辑不变。

    返回 set(image_id)，若 meta_csv_path 为 None 则返回 None（不过滤）。
    """
    if meta_csv_path is None:
        return None  # 不过滤，全部处理

    meta_path = Path(meta_csv_path)
    if not meta_path.exists():
        print(f"[lesion_features_cbis] WARNING: meta-csv 不存在: {meta_path}，不做 mass 过滤")
        return None

    # 尝试多种列名变体（CBIS-DDSM 不同版本有空格/下划线差异）
    id_col_candidates   = ["image_id", "image id", "filename", "image_file_path", "file_name"]
    type_col_candidates = ["abnormality_type", "abnormality type", "type", "pathology"]

    mass_ids = set()
    with open(meta_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            print("[lesion_features_cbis] WARNING: meta-csv 无字段名，不做 mass 过滤")
            return None

        # 找实际列名
        lower_fields = {fn.strip().lower(): fn for fn in reader.fieldnames}
        id_col   = next((lower_fields[c] for c in id_col_candidates if c in lower_fields), None)
        type_col = next((lower_fields[c] for c in type_col_candidates if c in lower_fields), None)

        if id_col is None or type_col is None:
            print(
                f"[lesion_features_cbis] WARNING: meta-csv 找不到 image_id 或 abnormality_type 列。"
                f"实际列: {reader.fieldnames}。不做 mass 过滤。"
                f"# TODO: CBIS 真实列名待数据到位后确认。"
            )
            return None

        for row in reader:
            atype = row.get(type_col, "").strip().lower()
            iid   = row.get(id_col, "").strip()
            if atype == "mass" and iid:
                # 去扩展名，只保留 stem 部分（与文件查找一致）
                mass_ids.add(Path(iid).stem)

    print(f"[lesion_features_cbis] meta-csv mass 子集: {len(mass_ids)} 个 image_id")
    return mass_ids


# ============================================================
# 图/mask 对查找
# ============================================================

def _find_img_mask_pairs(img_dir, mask_dir, meta_csv_path=None):
    """
    在 img_dir 和 mask_dir 中找配对的 (img_path, mask_path, image_id)。

    CBIS-DDSM awsaf49 版文件命名假设（待数据到位确认）：
      全乳图：  <image_id>.png 或 .jpg
      ROI mask：<image_id>_mask.png 或 <image_id>.png（同名目录或带 _mask 后缀）
      若两者同名（image_id.png 在不同目录），则 mask_dir 存 ROI mask。

    TODO: CBIS 真实文件命名规律待 data/external/cbis_ddsm/ 下载完毕后确认。
          以下实现支持以下三种命名变体：
            1. mask_dir/<image_id>_mask.png
            2. mask_dir/<image_id>.png（与图同名，不同目录）
            3. mask_dir/<image_id>_roi_mask.png

    mass_ids: 若非 None，只处理在集合中的 image_id。
    """
    mass_ids = load_mass_image_ids(meta_csv_path)

    img_dir  = Path(img_dir)
    mask_dir = Path(mask_dir)

    # 收集 img 文件（按 stem 建索引）
    img_map = {}
    for ext in (".png", ".jpg", ".jpeg", ".PNG", ".JPG", ".JPEG"):
        for p in img_dir.glob(f"*{ext}"):
            img_map[p.stem] = p

    # 收集 mask 文件（多种命名变体）
    mask_map = {}
    for ext in (".png", ".PNG"):
        for p in mask_dir.glob(f"*{ext}"):
            stem = p.stem
            # 规范化：去掉 _mask / _roi_mask 后缀，得到 image_id
            for suffix in ("_mask", "_roi_mask", "_ROI_mask"):
                if stem.endswith(suffix):
                    stem = stem[: -len(suffix)]
                    break
            mask_map[stem] = p

    pairs = []
    skipped_no_img   = 0
    skipped_non_mass = 0

    # 以 mask 为主迭代（mask 决定有哪些 ROI）
    for image_id, mask_path in sorted(mask_map.items()):
        # mass 过滤（若提供 meta csv）
        if mass_ids is not None and image_id not in mass_ids:
            skipped_non_mass += 1
            continue

        img_path = img_map.get(image_id)
        if img_path is None:
            skipped_no_img += 1
            continue

        pairs.append((img_path, mask_path, image_id))

    if skipped_non_mass > 0:
        print(f"[lesion_features_cbis] 跳过 {skipped_non_mass} 非 mass（calcification 等）")
    if skipped_no_img > 0:
        print(f"[lesion_features_cbis] 跳过 {skipped_no_img} 无对应全乳图的 mask")

    return pairs


# ============================================================
# 批量提取
# ============================================================

def batch_extract_cbis(
    img_dir,
    mask_dir,
    out_csv,
    meta_csv=None,
    ring_width_frac=0.075,
    ring_frac_list=None,
    img_size=None,
):
    """
    批量提取 CBIS-DDSM mass 特征，输出 per-image csv。

    Args:
        img_dir:        全乳 mammogram 目录
        mask_dir:       ROI mask 目录
        out_csv:        输出 csv 路径（多档时追加 _rf* 后缀）
        meta_csv:       CBIS metadata csv（含 abnormality_type 列），用于 mass 过滤
                        None = 不过滤（全部处理）
                        # TODO: CBIS awsaf49 版实际 meta csv 路径待数据到位确认
        ring_width_frac: 单档环宽（默认 0.075=7.5%）
        ring_frac_list:  三档敏感性扫描（如 [0.05, 0.075, 0.10]），传入时循环
        img_size:       resize 尺寸（Phase 1 须传 64 保证与 BraTS 64px 一致）
                        None = 不 resize（使用原始分辨率，area_ratio_breast 仍有效，
                        但 area_ratio_full 分母随图变化，跨图不可直接比较）
                        # TODO: Phase 1 运行须传 img_size=64 或 --img-size 64

    输出 csv 列:
      image_id, mass_px, breast_px, full_frame_px,
      area_ratio_breast, area_ratio_full,
      n_components, contrast, dilation_px, ring_width_frac,
      breast_otsu_threshold, orig_h, orig_w
    """
    fracs = ring_frac_list if ring_frac_list else [ring_width_frac]

    pairs = _find_img_mask_pairs(img_dir, mask_dir, meta_csv_path=meta_csv)
    if not pairs:
        print("[lesion_features_cbis] 无可处理的 (img, mask) 对，请检查目录与 meta-csv。")
        return {}

    print(f"[lesion_features_cbis] 处理 {len(pairs)} 个 mass 样本，ring_fracs={fracs}")

    all_results = {}
    for frac in fracs:
        rows_out = []
        for img_path, mask_path, image_id in pairs:
            try:
                feats = extract_cbis_features(
                    img_path, mask_path,
                    ring_width_frac=frac,
                    img_size=img_size,
                )
            except Exception as e:
                print(f"  [warn] {image_id}: {e}")
                continue

            # 处理 nan（乳腺分割失败）
            arb = feats["area_ratio_breast"]
            rows_out.append({
                "image_id":               image_id,
                "mass_px":                feats["mass_px"],
                "breast_px":              feats["breast_px"],
                "full_frame_px":          feats["full_frame_px"],
                "area_ratio_breast":      round(arb, 6) if not np.isnan(arb) else "nan",
                "area_ratio_full":        round(feats["area_ratio_full"], 6),
                "n_components":           feats["n_components"],
                "contrast":               round(feats["contrast"], 6),
                "dilation_px":            feats["dilation_px"],
                "ring_width_frac":        feats["ring_width_frac"],
                "breast_otsu_threshold":  round(feats["breast_otsu_threshold"], 6),
                "orig_h":                 feats["orig_h"],
                "orig_w":                 feats["orig_w"],
            })

        all_results[frac] = rows_out

        if out_csv and rows_out:
            # 多档时追加 _rf* 后缀（与 lesion_features.py 命名一致）
            if len(fracs) > 1:
                p = Path(out_csv)
                frac_str = str(frac).replace(".", "p")
                out_path = p.parent / (p.stem + f"_rf{frac_str}" + p.suffix)
            else:
                out_path = Path(out_csv)

            out_path.parent.mkdir(parents=True, exist_ok=True)
            fieldnames = [
                "image_id", "mass_px", "breast_px", "full_frame_px",
                "area_ratio_breast", "area_ratio_full",
                "n_components", "contrast", "dilation_px", "ring_width_frac",
                "breast_otsu_threshold", "orig_h", "orig_w",
            ]
            with open(out_path, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=fieldnames)
                w.writeheader()
                w.writerows(rows_out)
            print(f"  -> {out_path.name}: {len(rows_out)} mass samples (ring_frac={frac})")

    return all_results if len(fracs) > 1 else all_results.get(fracs[0], [])


# ============================================================
# 从 pairs csv 批量提取（awsaf49 真实数据接口）
# ============================================================

def batch_extract_from_pairs(
    pairs_csv: str,
    out_csv: str,
    ring_width_frac: float = 0.075,
    ring_frac_list=None,
    img_size: int = None,
):
    """
    从 cbis_build_pairs.py 产出的配对清单 csv 批量提取 mass 特征。

    pairs_csv 列（必须含）:
      abnorm_uid, full_img_jpeg_path, roi_mask_jpeg_path,
      abnormality_type, pathology, patient_id, side, view, abnormality_id

    产出 per-abnormality 特征 csv，列与 batch_extract_cbis 一致，
    额外追加 abnorm_uid / patient_id / side / view / abnormality_id /
    pathology / mass_shape / mass_margins（来自 pairs_csv）。

    只处理 abnormality_type == 'mass' 的行（过滤 calcification）。
    """
    fracs = ring_frac_list if ring_frac_list else [ring_width_frac]
    pairs_path = Path(pairs_csv)
    if not pairs_path.exists():
        raise FileNotFoundError(f"pairs csv 不存在: {pairs_path}")

    # 读配对清单
    with open(pairs_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        all_pairs = list(reader)

    # 只取 mass（通常 pairs csv 里已是纯 mass，但双重保险）
    mass_pairs = [
        r for r in all_pairs
        if r.get("abnormality_type", "mass").strip().lower() == "mass"
    ]
    skipped_non_mass = len(all_pairs) - len(mass_pairs)
    if skipped_non_mass > 0:
        print(f"[lesion_features_cbis] 跳过 {skipped_non_mass} 非 mass（pairs csv 过滤）")

    if not mass_pairs:
        print("[lesion_features_cbis] pairs csv 中无 mass 行，退出")
        return {}

    print(f"[lesion_features_cbis] pairs csv mass 行: {len(mass_pairs)}，ring_fracs={fracs}")

    # 追加字段名（来自 pairs csv）
    pair_extra_cols = [
        "abnorm_uid", "patient_id", "side", "view", "abnormality_id",
        "pathology", "mass_shape", "mass_margins", "split",
    ]
    base_feat_cols = [
        "mass_px", "breast_px", "full_frame_px",
        "area_ratio_breast", "area_ratio_full",
        "n_components", "contrast", "dilation_px", "ring_width_frac",
        "breast_otsu_threshold", "orig_h", "orig_w",
    ]
    fieldnames = pair_extra_cols + base_feat_cols

    all_results = {}
    for frac in fracs:
        rows_out = []
        n_err = 0
        for pair in mass_pairs:
            uid       = pair.get("abnorm_uid", "")
            img_path  = pair["full_img_jpeg_path"]
            mask_path = pair["roi_mask_jpeg_path"]

            try:
                feats = extract_cbis_features(
                    img_path, mask_path,
                    ring_width_frac=frac,
                    img_size=img_size,
                )
            except Exception as e:
                print(f"  [warn] {uid}: {e}")
                n_err += 1
                continue

            arb = feats["area_ratio_breast"]
            out_row = {
                "abnorm_uid":      uid,
                "patient_id":      pair.get("patient_id", ""),
                "side":            pair.get("side", ""),
                "view":            pair.get("view", ""),
                "abnormality_id":  pair.get("abnormality_id", ""),
                "pathology":       pair.get("pathology", ""),
                "mass_shape":      pair.get("mass_shape", ""),
                "mass_margins":    pair.get("mass_margins", ""),
                "split":           pair.get("split", ""),
                "mass_px":                feats["mass_px"],
                "breast_px":              feats["breast_px"],
                "full_frame_px":          feats["full_frame_px"],
                "area_ratio_breast":      round(arb, 6) if arb == arb else "nan",  # nan check
                "area_ratio_full":        round(feats["area_ratio_full"], 6),
                "n_components":           feats["n_components"],
                "contrast":               round(feats["contrast"], 6),
                "dilation_px":            feats["dilation_px"],
                "ring_width_frac":        feats["ring_width_frac"],
                "breast_otsu_threshold":  round(feats["breast_otsu_threshold"], 6),
                "orig_h":                 feats["orig_h"],
                "orig_w":                 feats["orig_w"],
            }
            rows_out.append(out_row)

        all_results[frac] = rows_out

        if out_csv and rows_out:
            if len(fracs) > 1:
                p = Path(out_csv)
                frac_str = str(frac).replace(".", "p")
                out_path = p.parent / (p.stem + f"_rf{frac_str}" + p.suffix)
            else:
                out_path = Path(out_csv)

            out_path.parent.mkdir(parents=True, exist_ok=True)
            with open(out_path, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=fieldnames)
                w.writeheader()
                w.writerows(rows_out)
            print(f"  -> {out_path.name}: {len(rows_out)} mass samples"
                  f" (ring_frac={frac}, errors={n_err})")

    return all_results if len(fracs) > 1 else all_results.get(fracs[0], [])


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "CBIS-DDSM mass 特征提取 — Phase 1 G1-a 机制公平面积比\n"
            "area_ratio_breast = mass_px / breast_px（主），\n"
            "area_ratio_full   = mass_px / full_frame_px（敏感性对照）\n"
            "\n"
            "两种模式：\n"
            "  (A) --pairs-csv 模式（推荐，awsaf49 真实数据）：\n"
            "      先跑 cbis_build_pairs.py 产出配对清单，再传 --pairs-csv <path>。\n"
            "  (B) --img-dir / --mask-dir 模式（合成测试 / 旧接口兼容）：\n"
            "      全乳图和 ROI mask 在各自目录中同名或 *_mask 命名。"
        )
    )
    _root = Path(__file__).resolve().parent.parent
    _data = Path("D:/YJ-Agent/data/external/cbis_ddsm")
    _res  = _root / "results"

    # 模式 A：pairs csv（推荐，awsaf49 真实路径）
    parser.add_argument(
        "--pairs-csv",
        default=None,
        help=(
            "cbis_build_pairs.py 产出的配对清单 csv。\n"
            "传入后使用模式 A（忽略 --img-dir / --mask-dir / --meta-csv）。\n"
            "默认路径: results/cbis_mass_pairs.csv"
        ),
    )

    # 模式 B：旧接口（img-dir / mask-dir）
    parser.add_argument(
        "--img-dir",
        default=str(_data / "images"),
        help="[模式B] 全乳 mammogram PNG 目录",
    )
    parser.add_argument(
        "--mask-dir",
        default=str(_data / "masks"),
        help="[模式B] ROI mask PNG 目录",
    )
    parser.add_argument(
        "--meta-csv",
        default=None,
        help="[模式B] CBIS metadata csv（含 image_id + abnormality_type 列）",
    )

    # 共同参数
    parser.add_argument(
        "--out-csv",
        default=str(_res / "lesion_features_cbis_mass.csv"),
        help="输出 per-image csv 路径",
    )
    parser.add_argument(
        "--ring-width-frac",
        type=float,
        default=0.075,
        help="相对环宽（等效直径百分比，默认 0.075=7.5%%）",
    )
    parser.add_argument(
        "--ring-frac-list",
        type=float,
        nargs="+",
        default=None,
        help="三档敏感性扫描：如 0.05 0.075 0.10（输出三个 csv）",
    )
    parser.add_argument(
        "--img-size",
        type=int,
        default=64,
        help="resize 到 N×N（Phase 1 传 64，与 BraTS 64px 坐标系一致；默认 64）",
    )
    args = parser.parse_args()

    if args.pairs_csv:
        # 模式 A：awsaf49 真实数据，经 cbis_build_pairs 配对后跑
        batch_extract_from_pairs(
            pairs_csv=args.pairs_csv,
            out_csv=args.out_csv,
            ring_width_frac=args.ring_width_frac,
            ring_frac_list=args.ring_frac_list,
            img_size=args.img_size,
        )
    else:
        # 模式 B：旧接口（img-dir / mask-dir），用于合成测试
        batch_extract_cbis(
            img_dir=args.img_dir,
            mask_dir=args.mask_dir,
            out_csv=args.out_csv,
            meta_csv=args.meta_csv,
            ring_width_frac=args.ring_width_frac,
            ring_frac_list=args.ring_frac_list,
            img_size=args.img_size,
        )
