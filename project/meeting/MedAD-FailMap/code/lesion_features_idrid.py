"""
lesion_features_idrid.py — IDRiD 眼底 DR 适配器（Phase 1 G1-a 负臂 n=3）
服务: MedAD-FailMap Phase 1, PC-B Gate1 G1-a 几何同构验证
lever: A' 病灶几何双峰 + 稀释 regime 窄 niche，负臂 n=2→n=3 实证

核心机制：
  眼底图含大片黑角（retina 圆形亮区 + 四角纯黑）。
  FOV（Field of View）= retina 圆形区域，与 CBIS 乳腺区 / BraTS 脑组织平行。
  机制公平面积比：area_ratio_fov = lesion_px / fov_px
  敏感性对照：area_ratio_full = lesion_px / (H*W)（含黑角偏差）

FOV 分割：
  眼底图灰度 Otsu，取最大连通域 = retina 圆形 FOV。
  黑角灰度接近 0，retina 明显更亮。
  不用 scipy（OMP#15），不用 torch，用 skimage.filters/measure。

异常病灶 union（DR 病理）：
  MA (Microaneurysms) + HE (Haemorrhages) + EX (Hard Exudates) + SE (Soft Exudates，若存在)
  union = 各 type mask 的逐像素 OR。
  排除 OD (Optic Disc)：正常解剖结构，recon-AD 训正常眼底不会标 OD 为异常。
  n_components = union mask 的连通域数（多灶性是 A' 双峰论点证据）。
  各 type 分项 px 单独记录（ma_px / he_px / ex_px / se_px）。

IDRiD Segmentation A 数据集：
  图：D:/YJ-Agent/data/external/idrid/A. Segmentation/1. Original Images/a. Training Set/IDRiD_NN.jpg
  mask：.../2. All Segmentation Groundtruths/a. Training Set/<type>/IDRiD_NN_XX.tif
  type 目录及后缀：
    1. Microaneurysms     → _MA.tif
    2. Haemorrhages       → _HE.tif
    3. Hard Exudates      → _EX.tif
    4. Soft Exudates      → _SE.tif  (只 26/54 有)
    5. Optic Disc         → _OD.tif  (排除，正常解剖)
  总训练图 54 张（IDRiD_01 ~ IDRiD_54，跳号可能存在，以文件存在为准）。
  不是每张都有全 4 类病理 mask（缺失 = 对应 lesion_px=0，不 crash）。

输出 csv schema:
  image_id, fov_px, lesion_px, area_ratio_fov, area_ratio_full,
  n_components, ma_px, he_px, ex_px, se_px

与 BraTS/CBIS 对齐说明：
  - BraTS:  area_ratio = tumor_px / brain_px（机制公平，见 brats_brain_px.py）
  - CBIS:   area_ratio = mass_px  / breast_px（机制公平，lesion_features_cbis.py）
  - IDRiD:  area_ratio = lesion_px / fov_px（本模块，机制公平）
  三端分母均为「组织有效区」，排黑边/黑角，机制可比。

依赖: numpy, scikit-image (Otsu + 连通域), Pillow
不用 scipy（OMP#15），Windows 路径用 pathlib.Path，无 torch
"""

import argparse
import csv
from pathlib import Path

import numpy as np
from PIL import Image


# ============================================================
# FOV 分割（Otsu + 最大连通域）
# ============================================================

def segment_fov(img_arr_gray):
    """
    对眼底图灰度图做 Otsu 阈值，取最大连通域 = retina FOV mask。

    眼底图黑角灰度接近 0，retina 圆形区域明显更亮。
    Otsu 分界把黑角（背景）和 retina（前景）分开；
    最大连通域 = retina 圆形 FOV。

    img_arr_gray: (H,W) uint8

    返回:
      fov_mask : (H,W) bool，True = retina FOV 区域
      otsu_thr : float（归一化 [0,1]，供调试）
      fov_px   : int，FOV 像素数
    """
    from skimage.filters import threshold_otsu
    from skimage.measure import label as sk_label

    arr_f = img_arr_gray.astype(np.float32) / 255.0
    otsu_thr = float(threshold_otsu(arr_f))

    # 大于 Otsu → retina 前景
    binary = (arr_f > otsu_thr).astype(np.uint8)

    if binary.sum() == 0:
        return np.zeros(img_arr_gray.shape, dtype=bool), otsu_thr, 0

    # 取最大连通域（4-连通），排散点黑角噪声
    labeled = sk_label(binary, connectivity=1)
    region_sizes = np.bincount(labeled.ravel())
    region_sizes[0] = 0  # 排背景 label 0
    largest_label = int(region_sizes.argmax())

    fov_mask = (labeled == largest_label)
    fov_px = int(fov_mask.sum())

    return fov_mask, otsu_thr, fov_px


# ============================================================
# 单 type mask 读取（.tif，二值）
# ============================================================

def _load_tif_mask(tif_path, target_size=None):
    """
    读 IDRiD .tif mask，>0 为前景，返回 (H,W) uint8。
    IDRiD 官方 mask 前景像素值为 76（非 255），故阈值用 >0。
    target_size: (W, H) tuple（PIL.resize 格式），若非 None 则 NEAREST resize。
    """
    img = Image.open(tif_path).convert("L")
    if target_size is not None:
        img = img.resize(target_size, Image.NEAREST)
    arr = np.array(img, dtype=np.uint8)
    return (arr > 0).astype(np.uint8)


# ============================================================
# 单图特征提取
# ============================================================

_LESION_TYPES = {
    "MA": ("1. Microaneurysms", "_MA"),
    "HE": ("2. Haemorrhages",  "_HE"),
    "EX": ("3. Hard Exudates", "_EX"),
    "SE": ("4. Soft Exudates", "_SE"),
    # OD 排除（正常解剖）
}


def extract_idrid_features(img_path, mask_root, image_id, img_size=None):
    """
    给定一张眼底图 + mask 根目录 + image_id，提取 IDRiD DR 病灶特征。

    img_path   : 眼底彩照（.jpg），RGB
    mask_root  : groundtruth 根目录，下含各 type 子目录
    image_id   : 如 "IDRiD_01"
    img_size   : 若非 None，FOV/mask 在 img_size×img_size 坐标算；
                 None（推荐）= 原始分辨率（4288×2848），保留 MA 等微灶精度。
                 IDRiD MA 病灶极小（<50px），resize 64 会导致微灶全部消失，
                 因此默认在原始分辨率计算面积比（比值与坐标系无关）。

    返回 dict:
      {
        "fov_px":          int,   # FOV（retina 圆形区）像素数
        "lesion_px":       int,   # DR 病理 union 像素数（MA+HE+EX+SE）
        "area_ratio_fov":  float, # lesion_px / fov_px（主，机制公平）
        "area_ratio_full": float, # lesion_px / (H*W)（敏感性对照）
        "n_components":    int,   # union mask 连通域数（多灶性）
        "ma_px":           int,
        "he_px":           int,
        "ex_px":           int,
        "se_px":           int,
        "otsu_thr":        float, # FOV Otsu 阈值（供调试）
      }

    断言: area_ratio_fov ∈ [0, 1]，area_ratio_full ∈ [0, 1]。
    缺失 type mask → 该 type_px = 0（不 crash）。
    """
    from skimage.measure import label as sk_label

    # 读眼底图（RGB → 灰度，用于 FOV 分割）
    pil_img = Image.open(img_path).convert("RGB")
    pil_gray = pil_img.convert("L")
    orig_w, orig_h = pil_gray.size  # PIL: (W, H)

    # 是否 resize（仅当 img_size 明确指定时）
    if img_size is not None:
        target_wh = (img_size, img_size)
        pil_gray_r = pil_gray.resize(target_wh, Image.BILINEAR)
        img_arr = np.array(pil_gray_r, dtype=np.uint8)
        effective_h, effective_w = img_size, img_size
    else:
        img_arr = np.array(pil_gray, dtype=np.uint8)
        effective_h, effective_w = orig_h, orig_w
        target_wh = None

    full_frame_px = effective_h * effective_w

    # FOV 分割（Otsu，最大连通域）
    fov_mask, otsu_thr, fov_px = segment_fov(img_arr)

    # 各 type mask 加载 + union（与图同坐标系）
    union_mask = np.zeros((effective_h, effective_w), dtype=np.uint8)
    type_px = {}

    mask_root = Path(mask_root)
    for key, (subdir, suffix) in _LESION_TYPES.items():
        tif_path = mask_root / subdir / f"{image_id}{suffix}.tif"
        if tif_path.exists():
            m = _load_tif_mask(tif_path, target_size=target_wh)
            type_px[key] = int(m.sum())
            union_mask = np.maximum(union_mask, m)  # OR
        else:
            type_px[key] = 0

    lesion_px = int(union_mask.sum())

    # n_components（union mask 连通域数，多灶性，A' 双峰论据）
    if lesion_px > 0:
        labeled = sk_label(union_mask, connectivity=1)
        comp_sizes = np.bincount(labeled.ravel())
        comp_sizes[0] = 0
        n_components = int((comp_sizes > 0).sum())
    else:
        n_components = 0

    # area_ratio 计算
    if fov_px > 0:
        area_ratio_fov = lesion_px / fov_px
    else:
        area_ratio_fov = float("nan")

    area_ratio_full = lesion_px / full_frame_px if full_frame_px > 0 else float("nan")

    # 断言 ∈ [0, 1]（nan 跳过）
    if area_ratio_fov == area_ratio_fov:  # not nan
        assert 0.0 <= area_ratio_fov <= 1.0, (
            f"{image_id}: area_ratio_fov={area_ratio_fov:.4f} 超出 [0,1]"
        )
    assert 0.0 <= area_ratio_full <= 1.0, (
        f"{image_id}: area_ratio_full={area_ratio_full:.4f} 超出 [0,1]"
    )

    return {
        "fov_px":          fov_px,
        "lesion_px":       lesion_px,
        "area_ratio_fov":  float(area_ratio_fov),
        "area_ratio_full": float(area_ratio_full),
        "n_components":    n_components,
        "ma_px":           type_px["MA"],
        "he_px":           type_px["HE"],
        "ex_px":           type_px["EX"],
        "se_px":           type_px["SE"],
        "otsu_thr":        otsu_thr,
    }


# ============================================================
# 批量提取
# ============================================================

def batch_extract_idrid(img_dir, mask_root, out_csv, img_size=None):
    """
    批量提取 IDRiD 训练集 54 张眼底图的特征，输出 per-image csv。

    img_dir   : 眼底彩照目录（IDRiD_NN.jpg）
    mask_root : groundtruth 根目录（含 1. Microaneurysms/ 等子目录）
    out_csv   : 输出 csv 路径
    img_size  : resize 尺寸（与 BraTS/CBIS 64px 坐标系一致，默认 64）

    输出 csv 列:
      image_id, fov_px, lesion_px, area_ratio_fov, area_ratio_full,
      n_components, ma_px, he_px, ex_px, se_px

    统计打印:
      area_ratio_fov: p25/med/p75 + n_components 中位
    """
    img_dir   = Path(img_dir)
    mask_root = Path(mask_root)
    out_csv   = Path(out_csv)

    # 收集图文件（IDRiD_NN.jpg，以实际存在文件为准）
    img_files = sorted(img_dir.glob("IDRiD_*.jpg"))
    if not img_files:
        img_files = sorted(img_dir.glob("IDRiD_*.JPG"))
    if not img_files:
        print(f"[lesion_features_idrid] 未找到图文件：{img_dir}")
        return []

    _sz_str = str(img_size) if img_size is not None else "原始分辨率"
    print(f"[lesion_features_idrid] 共 {len(img_files)} 张眼底图，img_size={_sz_str}")

    rows_out = []
    n_skip   = 0
    n_nomask = 0  # 完全无任何病理 mask 的图（lesion_px=0）

    for img_path in img_files:
        image_id = img_path.stem  # e.g. "IDRiD_01"
        try:
            feats = extract_idrid_features(
                img_path, mask_root, image_id, img_size=img_size
            )
        except Exception as e:
            print(f"  [warn] {image_id}: {e}")
            n_skip += 1
            continue

        arf = feats["area_ratio_fov"]
        arf_str = f"{arf:.6f}" if arf == arf else "nan"  # nan check

        if feats["lesion_px"] == 0:
            n_nomask += 1

        rows_out.append({
            "image_id":        image_id,
            "fov_px":          feats["fov_px"],
            "lesion_px":       feats["lesion_px"],
            "area_ratio_fov":  arf_str,
            "area_ratio_full": f"{feats['area_ratio_full']:.6f}",
            "n_components":    feats["n_components"],
            "ma_px":           feats["ma_px"],
            "he_px":           feats["he_px"],
            "ex_px":           feats["ex_px"],
            "se_px":           feats["se_px"],
        })

    print(
        f"  处理: {len(rows_out)} 成功 / {n_skip} 跳过错误"
        f" / {n_nomask} 无病理 mask (lesion_px=0)"
    )

    if not rows_out:
        print("[lesion_features_idrid] 无输出行，检查路径")
        return rows_out

    # 写 csv
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "image_id", "fov_px", "lesion_px",
        "area_ratio_fov", "area_ratio_full",
        "n_components", "ma_px", "he_px", "ex_px", "se_px",
    ]
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows_out)
    print(f"  -> {out_csv}")

    # 分位数统计
    _print_stats(rows_out)

    return rows_out


def _print_stats(rows):
    """打印 area_ratio_fov 分位数 + n_components 中位数。"""
    arf_vals = []
    nc_vals  = []
    for r in rows:
        arf = r["area_ratio_fov"]
        if isinstance(arf, str):
            try:
                arf = float(arf)
            except ValueError:
                arf = float("nan")
        if arf == arf:  # not nan
            arf_vals.append(arf)
        nc_vals.append(int(r["n_components"]))

    if arf_vals:
        arr = np.array(arf_vals)
        p25 = float(np.percentile(arr, 25))
        med = float(np.percentile(arr, 50))
        p75 = float(np.percentile(arr, 75))
        print(
            f"\n[IDRiD lesion stats] n={len(arf_vals)} 有效图"
            f"\n  area_ratio_fov: p25={p25:.4f}  med={med:.4f}  p75={p75:.4f}"
        )
    else:
        print("[IDRiD lesion stats] 无有效 area_ratio_fov")

    if nc_vals:
        nc_arr = np.array(nc_vals)
        nc_med = float(np.median(nc_arr))
        nc_p75 = float(np.percentile(nc_arr, 75))
        print(f"  n_components:   med={nc_med:.1f}  p75={nc_p75:.1f}")


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "IDRiD DR 眼底特征提取 — Phase 1 G1-a 负臂 n=3\n"
            "area_ratio_fov  = lesion_px / fov_px（主，机制公平）\n"
            "area_ratio_full = lesion_px / full_frame_px（敏感性对照）\n"
            "异常病灶 = MA+HE+EX+SE union，排 OD（正常解剖）"
        )
    )

    _ROOT  = Path(__file__).resolve().parent.parent
    _DATA  = Path("D:/YJ-Agent/data/external/idrid/A. Segmentation")
    _IMG   = _DATA / "1. Original Images/a. Training Set"
    _MASK  = _DATA / "2. All Segmentation Groundtruths/a. Training Set"
    _RES   = _ROOT / "results"

    parser.add_argument(
        "--img-dir",
        default=str(_IMG),
        help="眼底彩照目录（IDRiD_NN.jpg，默认 IDRiD A Segmentation training）",
    )
    parser.add_argument(
        "--mask-root",
        default=str(_MASK),
        help="Groundtruth 根目录（含 1. Microaneurysms/ 等子目录）",
    )
    parser.add_argument(
        "--out-csv",
        default=str(_RES / "lesion_features_idrid.csv"),
        help="输出 per-image csv 路径",
    )
    parser.add_argument(
        "--img-size",
        type=int,
        default=None,
        help=(
            "resize 到 N×N 再算（None=原始分辨率，推荐）。"
            "IDRiD MA 病灶极小（<50px），resize 64 会导致微灶全部消失，"
            "故默认 None（原图 4288x2848 精度）。"
            "面积比是比值，与坐标系无关，原图分辨率最准。"
        ),
    )

    args = parser.parse_args()

    batch_extract_idrid(
        img_dir=args.img_dir,
        mask_root=args.mask_root,
        out_csv=args.out_csv,
        img_size=args.img_size,
    )

