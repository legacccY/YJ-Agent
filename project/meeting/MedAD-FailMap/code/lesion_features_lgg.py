"""
lesion_features_lgg.py — LGG-MRI (Buda kaggle_3m) per-slice 几何特征提取
服务: MedAD-FailMap Phase 1 G1-a 同构判定，§STORY② iso=True 正臂锚候选
lever: LGG-MRI vs BraTS2021 几何同构验证

数据约定（Buda et al. 2019 TCGA kaggle_3m）：
  <patient_dir>/<id>_<n>.tif   — RGB 3 通道: ch0=pre-contrast, ch1=FLAIR, ch2=post-contrast
  <patient_dir>/<id>_<n>_mask.tif — 二值肿瘤 mask（前景=255，背景=0）
  110 患者，非空 mask 切片约 1373 张

口径（与 BraTS 严格一致）：
  size_px  = 肿瘤 mask 连通域总面积（resize 后 64² 坐标系），mask > 0
  n_components = skimage.measure.label(bin_mask, connectivity=1) 4-连通
               与 ncomp_brats.py 逐字同口径（包含所有前景连通域，非最大）
  area_ratio_full = size_px / (64*64)
               与 brats_brain_px.csv 的 area_ratio_full 列同口径（PR-7b G1-a 主判分母）
               分母 = 64² 全帧，两端均无须 skull-strip，可直接比较。

  ⚠️ skull-strip 口径说明（TODO）：
    BraTS 已做 skull-stripping（非脑区=0），brats_brain_px.csv area_ratio_brain = size_px / brain_px
    LGG (Buda kaggle_3m) 未做 skull-stripping，FLAIR 通道几乎全非零（~99.8% 非零像素）。
    若对 LGG 用 FLAIR nonzero 算 brain_px，则 brain_px ≈ 全帧（~4090/4096），
    area_ratio = tumor/4090 ≈ tumor/64²，与 area_ratio_full 几乎等同，
    但与 BraTS area_ratio_brain（tumor/skull-strip 脑区，median brain_px≈1619/4096）**不可比**。
    # TODO: 若需和 BraTS area_ratio_brain 口径比较，须对 LGG 执行脑区分割（如 HD-BET/FSL BET）。
    # 当前 G1-a 判定使用 area_ratio_full 两端等价口径，不触发此 TODO。

  额外输出 area_ratio_brain_note 列标注 skull-strip 不可比情况供审查。

输出 csv: results/phase1/lesion_features_lgg.csv
  列: filename / patient_id / size_px / n_components / area_ratio_full / overlaps_brats2021
  + brain_px_note (str): "N/A_lgg_no_skull_strip"（提醒 area_ratio_brain 不可比）

overlaps_brats2021 列：
  LGG 约 65/110 患者属 BraTS-TCGA-LGG 子集（与 BraTS2021 重叠）。
  # TODO: BraTS-TCGA-LGG 患者 ID 列表未从 TCIA 核实，overlaps_brats2021=unknown。
  # 建议访问 https://cancerimagingarchive.net/analysis-result/brats-tcga-lgg/ 核对。
  # 去重后独立例数 = overlaps_brats2021=False 的患者，用于外推读数（不含泄漏样本）。

G1-a iso 判定（PR-7b + PR-7c 双维门，冻结常数）：
  PR-7b: area_ratio_full 占比门
    brats_p25_full = 0.0198（brats_brain_px.csv area_ratio_full P25，见 results/brats_brain_px.csv）
    冻结 brats_low_ratio_pct=25（→ P25），min_overlap_frac=5%（1/20）
    iso_area = (lgg 落 ≤P25 的比例 >= 5%)
  PR-7c: n_components 占比门
    brats_p75_ncomp = 3（ncomp_brats.csv n_components P75，冻结）
    min_ncomp_overlap_frac=5%（1/20）
    iso_ncomp = (lgg n_components ≤ 3 的比例 >= 5%)
  iso = iso_area AND iso_ncomp

依赖: numpy, scikit-image, Pillow
不用 scipy（OMP#15），无 torch，纯 CPU
Windows 路径用 pathlib.Path
DataLoader 不在此模块
"""

import argparse
import csv
import sys
from pathlib import Path

import numpy as np
from PIL import Image


# ============================================================
# 常量（冻结，来自 PR-7b / PR-7c）
# ============================================================

# PR-7b area_ratio_full P25（来自 brats_brain_px.csv area_ratio_full，n=1948）
# brats_brain_px.csv area_ratio_full P25=0.0198（Bash 核实）
BRATS_P25_AREA_RATIO_FULL = 0.0198   # 冻结，PR-7b 稀释 regime 边界
MIN_OVERLAP_FRAC_AREA     = 0.05     # PR-7b: 目标集 >=5% 落稀释 regime -> iso_area=True

# PR-7c n_components P75（来自 ncomp_brats.csv，n=1948；BraTS p75=3 在 planner 已核）
BRATS_P75_NCOMP           = 3        # 冻结，PR-7c 低焦 regime 边界
MIN_OVERLAP_FRAC_NCOMP    = 0.05     # PR-7c: 目标集 >=5% 落 ≤3 -> iso_ncomp=True

# LGG 图像通道（Buda 约定）
_FLAIR_CH = 1   # RGB ch1 = FLAIR

# resize 目标（与 BraTS 64×64 口径一致）
_IMG_SIZE = 64


# ============================================================
# 核心：单切片特征
# ============================================================

def extract_slice_features(img_path, mask_path, img_size=_IMG_SIZE):
    """
    提取单个 LGG 切片的几何特征。

    Args:
        img_path  : Path/str  RGB tif（ch0=pre, ch1=FLAIR, ch2=post）
        mask_path : Path/str  binary mask tif（前景=255，背景=0）
        img_size  : int       resize 目标尺寸（默认 64，与 BraTS 口径一致）

    Returns:
        dict:
          size_px          : int   tumor 连通域总面积（resize 后 img_size² 坐标系）
          n_components     : int   4-连通连通域数（skimage label connectivity=1）
                                   0 = 空 mask（不含肿瘤切片，调用方已过滤非空）
          area_ratio_full  : float size_px / (img_size * img_size)
          brain_px_note    : str   "N/A_lgg_no_skull_strip"（skull-strip 口径说明）
    """
    from skimage.measure import label as sk_label
    from skimage.transform import resize as sk_resize

    # --- 读取 mask ---
    mask_arr = np.array(Image.open(mask_path).convert("L"), dtype=np.uint8)
    # resize mask（nearest 插值保二值性）
    if mask_arr.shape != (img_size, img_size):
        mask_small = sk_resize(
            mask_arr.astype(np.float32),
            (img_size, img_size),
            order=0,                   # nearest，保二值
            anti_aliasing=False,
            preserve_range=True,
        ).astype(np.uint8)
    else:
        mask_small = mask_arr

    bin_mask = (mask_small > 0).astype(np.uint8)

    # --- n_components & size_px（与 ncomp_brats.py 逐字同口径）---
    if bin_mask.sum() == 0:
        n_comp  = 0
        size_px = 0
    else:
        labeled     = sk_label(bin_mask, connectivity=1)  # 4-连通
        region_sizes = np.bincount(labeled.ravel())
        region_sizes[0] = 0  # 排背景 label 0
        n_comp  = int((region_sizes > 0).sum())          # 连通域总数（非最大）
        size_px = int(region_sizes.sum())                 # 全部前景像素

    # --- area_ratio_full（两端均用 img_size² 分母，可与 BraTS 直接比）---
    total_px = float(img_size * img_size)
    area_ratio_full = float(size_px) / total_px

    # 断言值域 [0, 1]
    if area_ratio_full < 0 or area_ratio_full > 1.0 + 1e-9:
        raise ValueError(
            f"area_ratio_full={area_ratio_full:.6f} 超出 [0,1]，"
            f"size_px={size_px}，img_size={img_size}。"
            f"请检查 mask 格式。"
        )

    return {
        "size_px":         size_px,
        "n_components":    n_comp,
        "area_ratio_full": round(area_ratio_full, 6),
        "brain_px_note":   "N/A_lgg_no_skull_strip",
        # TODO: skull-strip brain_px 不可比，area_ratio_brain 暂不输出。
        # 若需与 BraTS area_ratio_brain 对应，须对 LGG 执行 BET/HD-BET 脑区分割。
    }


# ============================================================
# 批量遍历：全部含肿瘤切片
# ============================================================

def batch_extract_lgg(
    lgg_root,
    out_csv,
    img_size=_IMG_SIZE,
    overlaps_brats_ids=None,
    smoke=False,
):
    """
    遍历 lgg_root/TCGA_*/ 下所有 *_mask.tif，
    只处理 mask 非空（肿瘤）切片，提取特征并写 csv。

    Args:
        lgg_root         : str/Path  kaggle_3m 根目录
        out_csv          : str/Path  输出 csv 路径
        img_size         : int       resize 尺寸（默认 64）
        overlaps_brats_ids: set/None TCGA patient IDs 属于 BraTS-TCGA-LGG 子集
                           （如 {"TCGA_CS_4941_19960909", ...}）；
                           None = 全部标 "unknown"
                           # TODO: 从 TCIA 核实真实列表
        smoke            : bool      True = 只处理前 5 张非空切片（冒烟测试）

    输出 csv 列:
        filename / patient_id / size_px / n_components / area_ratio_full
        / brain_px_note / overlaps_brats2021
    """
    lgg_root = Path(lgg_root)
    out_csv  = Path(out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    # 收集所有 patient 目录（TCGA_*）
    patient_dirs = sorted([
        d for d in lgg_root.iterdir()
        if d.is_dir() and d.name.startswith("TCGA_")
    ])
    if not patient_dirs:
        raise FileNotFoundError(f"lgg_root 下无 TCGA_* 患者目录: {lgg_root}")

    # 所有 mask 文件（不递归 patient_dir 层，与数据结构一致）
    all_mask_paths = []
    for pd in patient_dirs:
        all_mask_paths.extend(sorted(pd.glob("*_mask.tif")))

    if not all_mask_paths:
        raise FileNotFoundError(
            f"lgg_root 下无 *_mask.tif 文件（检查路径 {lgg_root}）"
        )

    fieldnames = [
        "filename", "patient_id",
        "size_px", "n_components", "area_ratio_full",
        "brain_px_note", "overlaps_brats2021",
    ]

    rows = []
    n_processed = 0
    n_skipped   = 0   # 空 mask（无肿瘤）跳过数

    with open(out_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for mask_path in all_mask_paths:
            # 对应图像路径（去掉 _mask 后缀）
            fname_stem = mask_path.name.replace("_mask.tif", "")
            img_path   = mask_path.parent / (fname_stem + ".tif")

            if not img_path.exists():
                print(f"[lesion_features_lgg] WARNING: 图像不存在，跳过: {img_path}")
                n_skipped += 1
                continue

            # 快速判断 mask 非空（避免全量读取）
            mask_quick = np.array(Image.open(mask_path).convert("L"), dtype=np.uint8)
            if mask_quick.sum() == 0:
                # 空 mask = 非肿瘤切片，跳过（G1-a 只看肿瘤切片）
                n_skipped += 1
                continue

            # patient_id = 父目录名
            patient_id = mask_path.parent.name

            # overlaps_brats2021 标记
            if overlaps_brats_ids is None:
                overlaps = "unknown"
                # TODO: TCIA BraTS-TCGA-LGG 患者 ID 列表未从官方核实
                # 访问 https://cancerimagingarchive.net/analysis-result/brats-tcga-lgg/ 获取
            else:
                overlaps = str(patient_id in overlaps_brats_ids)

            try:
                feats = extract_slice_features(img_path, mask_path, img_size=img_size)
            except Exception as e:
                print(f"[lesion_features_lgg] ERROR on {img_path.name}: {e}")
                n_skipped += 1
                continue

            row = {
                "filename":          mask_path.name.replace("_mask.tif", ".tif"),
                "patient_id":        patient_id,
                "size_px":           feats["size_px"],
                "n_components":      feats["n_components"],
                "area_ratio_full":   feats["area_ratio_full"],
                "brain_px_note":     feats["brain_px_note"],
                "overlaps_brats2021": overlaps,
            }
            writer.writerow(row)
            rows.append(row)
            n_processed += 1

            if smoke and n_processed >= 5:
                print(f"[lesion_features_lgg] smoke=True，处理 {n_processed} 张后停止")
                break

    # --- 统计打印 ---
    if rows:
        size_arr   = np.array([r["size_px"]        for r in rows], dtype=float)
        ncomp_arr  = np.array([r["n_components"]   for r in rows], dtype=float)
        ratio_arr  = np.array([r["area_ratio_full"] for r in rows], dtype=float)

        print(
            f"\n[lesion_features_lgg] 处理完成: "
            f"n={n_processed} 含肿瘤切片，跳过 {n_skipped} 张（空 mask/缺图）"
        )
        print(
            f"  size_px:         "
            f"p25={np.percentile(size_arr,25):.0f}  "
            f"med={np.median(size_arr):.0f}  "
            f"p75={np.percentile(size_arr,75):.0f}"
        )
        print(
            f"  n_components:    "
            f"med={np.median(ncomp_arr):.0f}  "
            f"p75={np.percentile(ncomp_arr,75):.0f}  "
            f"max={ncomp_arr.max():.0f}"
        )
        print(
            f"  area_ratio_full: "
            f"p25={np.percentile(ratio_arr,25):.4f}  "
            f"med={np.median(ratio_arr):.4f}  "
            f"p75={np.percentile(ratio_arr,75):.4f}"
        )
        print(f"  -> {out_csv}  ({n_processed} rows)")
    else:
        print(f"[lesion_features_lgg] WARNING: 无有效行输出（所有 mask 均为空）")

    return rows


# ============================================================
# G1-a iso 判定（PR-7b + PR-7c 双维门）
# ============================================================

def compute_g1a_iso(
    rows,
    brats_ncomp_csv,
    brats_area_full_csv,
    out_dir,
):
    """
    PR-7b + PR-7c 双维 iso 判定。

    Args:
        rows           : batch_extract_lgg 返回的 list of dict
        brats_ncomp_csv: results/ncomp_brats.csv（含 n_components 列）
        brats_area_full_csv: results/brats_brain_px.csv（含 area_ratio_full 列）
        out_dir        : 输出目录（results/phase1/）

    输出:
        distribution_overlap_brats_lgg_area_ratio.csv
        distribution_overlap_brats_lgg_n_components.csv
        g1a_iso_lgg.csv（单行：双维结果 + iso 最终判定）
    """
    # 动态 import（与既有代码保持一致）
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from distribution_overlap import compute_ovl_bc, _get_bins, _load_col

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not rows:
        raise ValueError("[compute_g1a_iso] rows 为空，无法判定")

    # LGG 向量
    lgg_ratio = np.array([float(r["area_ratio_full"]) for r in rows], dtype=float)
    lgg_ncomp = np.array([float(r["n_components"])    for r in rows], dtype=float)
    # 只取 n_components > 0（与 distribution_overlap.py 一致：0=空 mask 不参与分布比较）
    lgg_ncomp_pos = lgg_ncomp[lgg_ncomp > 0]

    # BraTS 向量
    brats_ratio = _load_col(brats_area_full_csv, "area_ratio_full")
    brats_ncomp = _load_col(brats_ncomp_csv, "n_components")
    brats_ncomp_pos = brats_ncomp[brats_ncomp > 0]

    if len(brats_ratio) == 0:
        raise ValueError(
            f"brats_brain_px.csv 无有效 area_ratio_full 列: {brats_area_full_csv}"
        )
    if len(brats_ncomp_pos) == 0:
        raise ValueError(
            f"ncomp_brats.csv 无有效 n_components > 0: {brats_ncomp_csv}"
        )

    # --- OVL / BC（固化 bin，与既有 distribution_overlap.py 同口径）---
    bins_ar, scheme_ar, nbins_ar = _get_bins("area_ratio")
    bins_nc, scheme_nc, nbins_nc = _get_bins("n_components")

    ovl_ar, bc_ar = compute_ovl_bc(brats_ratio, lgg_ratio, bins_ar)
    ovl_nc, bc_nc = compute_ovl_bc(brats_ncomp_pos, lgg_ncomp_pos, bins_nc)

    # 写 OVL/BC csv
    def _write_overlap_csv(path, pair, feature, nbins, scheme, ovl, bc, n_src, n_tgt):
        import csv as _csv
        with open(path, "w", newline="") as f:
            w = _csv.DictWriter(f, fieldnames=[
                "pair","feature","n_bins","bin_scheme","OVL","BC","n_source","n_target"
            ])
            w.writeheader()
            w.writerow({
                "pair": pair, "feature": feature,
                "n_bins": nbins, "bin_scheme": scheme,
                "OVL": round(ovl, 6), "BC": round(bc, 6),
                "n_source": n_src, "n_target": n_tgt,
            })
        print(f"  -> {path}")

    _write_overlap_csv(
        out_dir / "distribution_overlap_brats_lgg_area_ratio.csv",
        "brats_lgg", "area_ratio", nbins_ar, scheme_ar,
        ovl_ar, bc_ar, len(brats_ratio), len(lgg_ratio),
    )
    _write_overlap_csv(
        out_dir / "distribution_overlap_brats_lgg_n_components.csv",
        "brats_lgg", "n_components", nbins_nc, scheme_nc,
        ovl_nc, bc_nc, len(brats_ncomp_pos), len(lgg_ncomp_pos),
    )

    # --- PR-7b area 占比门 ---
    n_lgg_total = len(lgg_ratio)
    n_lgg_area_low = int((lgg_ratio <= BRATS_P25_AREA_RATIO_FULL).sum())
    frac_area = n_lgg_area_low / n_lgg_total if n_lgg_total > 0 else 0.0
    iso_area = frac_area >= MIN_OVERLAP_FRAC_AREA

    # --- PR-7c n_components 占比门 ---
    # 分母用全部切片（含 n_comp=0 的空 mask 切片已在 batch_extract 过滤，
    # 这里 rows 均为非空 mask，n_comp >= 1）
    n_lgg_ncomp = len(lgg_ncomp)
    n_lgg_ncomp_low = int((lgg_ncomp <= BRATS_P75_NCOMP).sum())
    frac_ncomp = n_lgg_ncomp_low / n_lgg_ncomp if n_lgg_ncomp > 0 else 0.0
    iso_ncomp = frac_ncomp >= MIN_OVERLAP_FRAC_NCOMP

    # --- 最终 iso 判定 ---
    iso = iso_area and iso_ncomp

    # --- 写 g1a_iso_lgg.csv ---
    result = {
        # PR-7b area
        "brats_p25_area_ratio_full":       BRATS_P25_AREA_RATIO_FULL,
        "min_overlap_frac_area":           MIN_OVERLAP_FRAC_AREA,
        "lgg_n_total":                     n_lgg_total,
        "lgg_n_in_area_low_zone":          n_lgg_area_low,
        "lgg_frac_in_area_low_zone":       round(frac_area, 6),
        "iso_area":                        iso_area,
        # PR-7c n_comp
        "brats_p75_ncomp":                 BRATS_P75_NCOMP,
        "min_overlap_frac_ncomp":          MIN_OVERLAP_FRAC_NCOMP,
        "lgg_n_ncomp_slices":              n_lgg_ncomp,
        "lgg_n_ncomp_le_brats_p75":        n_lgg_ncomp_low,
        "lgg_frac_ncomp_le_brats_p75":     round(frac_ncomp, 6),
        "iso_ncomp":                       iso_ncomp,
        # OVL/BC（描述性，PR-7b③ 连续趋势支撑）
        "OVL_area_ratio":                  round(ovl_ar, 6),
        "BC_area_ratio":                   round(bc_ar, 6),
        "OVL_n_components":                round(ovl_nc, 6),
        "BC_n_components":                 round(bc_nc, 6),
        # 最终判定
        "iso":                             iso,
        "note": (
            f"PR-7b: LGG {n_lgg_area_low}/{n_lgg_total}="
            f"{frac_area*100:.1f}% <=brats_p25_area={BRATS_P25_AREA_RATIO_FULL} "
            f"(need>={MIN_OVERLAP_FRAC_AREA*100:.0f}%) -> iso_area={iso_area}; "
            f"PR-7c: {n_lgg_ncomp_low}/{n_lgg_ncomp}="
            f"{frac_ncomp*100:.1f}% n_comp<={BRATS_P75_NCOMP} "
            f"(need>={MIN_OVERLAP_FRAC_NCOMP*100:.0f}%) -> iso_ncomp={iso_ncomp}; "
            f"iso={iso}"
        ),
    }

    iso_csv = out_dir / "g1a_iso_lgg.csv"
    with open(iso_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(result.keys()))
        w.writeheader()
        w.writerow(result)

    print(f"\n[G1-a iso 判定]")
    print(f"  PR-7b area:   {n_lgg_area_low}/{n_lgg_total} = {frac_area*100:.1f}%  "
          f"(brats_p25={BRATS_P25_AREA_RATIO_FULL}, need>={MIN_OVERLAP_FRAC_AREA*100:.0f}%)  "
          f"iso_area={iso_area}")
    print(f"  PR-7c ncomp:  {n_lgg_ncomp_low}/{n_lgg_ncomp} = {frac_ncomp*100:.1f}%  "
          f"(brats_p75_ncomp<={BRATS_P75_NCOMP}, need>={MIN_OVERLAP_FRAC_NCOMP*100:.0f}%)  "
          f"iso_ncomp={iso_ncomp}")
    print(f"  OVL_area={ovl_ar:.4f}  BC_area={bc_ar:.4f}  "
          f"OVL_ncomp={ovl_nc:.4f}  BC_ncomp={bc_nc:.4f}")
    print(f"  *** iso = {iso} ***")
    print(f"  -> {iso_csv}")

    return result


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "LGG-MRI (Buda kaggle_3m) 几何特征提取 + G1-a iso 判定\n"
            "口径: skimage.measure.label connectivity=1（同 ncomp_brats.py）\n"
            "      area_ratio_full = size_px / 64²（同 brats_brain_px.csv area_ratio_full）\n"
            "输出: results/phase1/lesion_features_lgg.csv\n"
            "      results/phase1/g1a_iso_lgg.csv\n"
            "      results/phase1/distribution_overlap_brats_lgg_*.csv"
        )
    )
    _root = Path(__file__).resolve().parent.parent
    _res  = _root / "results"
    _data = Path("D:/YJ-Agent/data/external/lgg_mri_seg/kaggle_3m")

    parser.add_argument(
        "--lgg-root",
        default=str(_data),
        help="kaggle_3m 根目录（含 TCGA_* 患者子目录）",
    )
    parser.add_argument(
        "--out-csv",
        default=str(_res / "phase1" / "lesion_features_lgg.csv"),
        help="输出特征 csv",
    )
    parser.add_argument(
        "--brats-ncomp-csv",
        default=str(_res / "ncomp_brats.csv"),
        help="BraTS n_components csv（results/ncomp_brats.csv）",
    )
    parser.add_argument(
        "--brats-area-full-csv",
        default=str(_res / "brats_brain_px.csv"),
        help="BraTS area_ratio_full csv（results/brats_brain_px.csv，含 area_ratio_full 列）",
    )
    parser.add_argument(
        "--out-dir",
        default=str(_res / "phase1"),
        help="G1-a 输出目录（g1a_iso_lgg.csv / distribution_overlap_*.csv）",
    )
    parser.add_argument(
        "--img-size",
        type=int,
        default=64,
        help="resize 尺寸（默认 64，与 BraTS 口径一致；勿改）",
    )
    parser.add_argument(
        "--smoke",
        type=int,
        default=0,
        help="冒烟模式：只处理前 N 张（0=全量）",
    )

    args = parser.parse_args()

    # Step 1: 提取特征
    rows = batch_extract_lgg(
        lgg_root=args.lgg_root,
        out_csv=args.out_csv,
        img_size=args.img_size,
        overlaps_brats_ids=None,  # TODO: 从 TCIA 核实后传入真实列表
        smoke=(args.smoke > 0),
    )

    if not rows:
        print("[lesion_features_lgg] 无有效行，退出")
        sys.exit(1)

    # Step 2: G1-a iso 判定
    compute_g1a_iso(
        rows=rows,
        brats_ncomp_csv=args.brats_ncomp_csv,
        brats_area_full_csv=args.brats_area_full_csv,
        out_dir=args.out_dir,
    )
