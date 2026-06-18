"""
prep_lgg_heldout.py — LGG held-out 切片预处理（纯 CPU）
服务: MedAD-FailMap § M-3 (LGG held-out C4 复现)
lever: 从 LGG kaggle_3m 数据里切出 15 独立 held-out 患者切片，
       按 mask 空/非空分 normal/tumor，存成 score_external.py 能吃的结构

输入:
    data/external/lgg-mri-segmentation.zip（或已解压的 kaggle_3m/ 目录）
    results/phase1/lgg_dedup.csv（overlaps_brats2021==False 的 15 患者）

输出:
    data/lgg_heldout/
        tumor/   <slice>.png   (mask 非空切片，label=1)
        normal/  <slice>.png   (mask 全零切片，label=0)
    results/phase1/lgg_heldout_manifest.csv  (filename, patient_dir, split, label, mask_px)

约定:
  - 图像源: LGG <patient_dir>/<id>_<n>.tif, 取 FLAIR 通道 (ch1, 与 BraTS 一致)
  - mask:   <patient_dir>/<id>_<n>_mask.tif, 二值 (>0 = 前景)
  - resize: 64x64 (Pillow BILINEAR)，灰度，存 PNG
  - 切片文件名: <patient_dir>__<orig_stem>.png (双下划线避免歧义)
  - 不改预处理/不改尺寸/不对齐 BraTS 归一化（归一化交 score_external.py 的 transform）

LGG kaggle_3m 解压结构（Kaggle 下载 mateuszbuda/lgg-mri-segmentation）:
    lgg-mri-segmentation/
        kaggle_3m/
            TCGA_CS_4941_19960909/
                TCGA_CS_4941_19960909_1.tif
                TCGA_CS_4941_19960909_1_mask.tif
                ...

zip 解压路径优先级:
    1. data/external/kaggle_3m/         (已解压后用)
    2. data/external/lgg-mri-segmentation/kaggle_3m/
    3. 自动尝试解压 data/external/lgg-mri-segmentation.zip -> data/external/

依赖: numpy, Pillow, zipfile（标准库）
"""

import argparse
import csv
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image


# ============================================================
# 工具函数
# ============================================================

def find_kaggle3m_root(external_dir: Path):
    """
    定位 kaggle_3m/ 根目录（含 TCGA_ 子文件夹）。
    按优先级探查，返回 Path 或 None（未找到）。
    """
    candidates = [
        external_dir / "kaggle_3m",
        external_dir / "lgg-mri-segmentation" / "kaggle_3m",
    ]
    for c in candidates:
        if c.exists() and any(c.iterdir()):
            return c
    return None


def try_unzip(zip_path: Path, extract_to: Path):
    """
    尝试用 zipfile 解压（仅适用于标准 zip）。
    若解压成功返回 True，否则 False（提示用户手动解压）。
    """
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            members = zf.namelist()
            print(f"[prep_lgg] unzipping {zip_path} ({len(members)} entries) -> {extract_to}")
            zf.extractall(extract_to)
        return True
    except zipfile.BadZipFile as e:
        print(f"[prep_lgg] warn: zipfile failed ({e}).")
        print(f"  -> Please manually extract {zip_path} to {extract_to}")
        print(f"     e.g.: 7z x \"{zip_path}\" -o\"{extract_to}\"")
        return False


def get_flair_channel(tif_path: Path):
    """
    读 LGG .tif 文件，取 FLAIR 通道 (ch1, 1-indexed)。
    kaggle_3m: ch0=pre-contrast, ch1=FLAIR, ch2=post-contrast（RGB）。
    灰度图直接用。
    返回 PIL Image (L mode)。
    """
    img = Image.open(tif_path)
    arr = np.array(img)
    if arr.ndim == 2:
        # 已是灰度（部分切片可能只存单通道）
        return Image.fromarray(arr.astype(np.uint8), mode="L")
    if arr.ndim == 3:
        # RGB 或 RGBA: 取 ch1 (FLAIR)
        ch = arr[:, :, 1].astype(np.uint8)
        return Image.fromarray(ch, mode="L")
    raise ValueError(f"Unexpected tif shape: {arr.shape} in {tif_path}")


def read_mask(mask_path: Path):
    """读 mask tif，返回 np.ndarray bool (H, W)"""
    mask = Image.open(mask_path)
    arr = np.array(mask)
    if arr.ndim == 3:
        arr = arr[:, :, 0]  # 取第一通道
    return arr > 0


# ============================================================
# 主逻辑
# ============================================================

def prep_lgg_heldout(args):
    external_dir  = Path(args.external_dir)
    dedup_csv     = Path(args.dedup_csv)
    out_dir       = Path(args.out_dir)
    manifest_csv  = Path(args.manifest_csv)
    target_size   = (64, 64)

    # ---- 找 kaggle_3m 根 ----
    kaggle3m = find_kaggle3m_root(external_dir)
    if kaggle3m is None:
        zip_path = external_dir / "lgg-mri-segmentation.zip"
        if zip_path.exists():
            print(f"[prep_lgg] kaggle_3m not found, trying to unzip {zip_path} ...")
            ok = try_unzip(zip_path, external_dir)
            if ok:
                kaggle3m = find_kaggle3m_root(external_dir)
        if kaggle3m is None:
            raise FileNotFoundError(
                f"kaggle_3m not found under {external_dir}.\n"
                f"Please extract lgg-mri-segmentation.zip first:\n"
                f"  7z x \"{external_dir / 'lgg-mri-segmentation.zip'}\" -o\"{external_dir}\""
            )

    print(f"[prep_lgg] kaggle_3m root: {kaggle3m}")

    # ---- 读 dedup csv，取 overlaps_brats2021==False 的 15 例 ----
    if not dedup_csv.exists():
        raise FileNotFoundError(f"lgg_dedup.csv not found: {dedup_csv}")

    held_patients = []
    with open(dedup_csv, newline="") as f:
        for row in csv.DictReader(f):
            val = row["overlaps_brats2021"].strip().lower()
            if val in ("false", "0", "no"):
                held_patients.append(row["patient_dir"])

    if not held_patients:
        raise RuntimeError("No overlaps_brats2021==False patients found in lgg_dedup.csv")
    print(f"[prep_lgg] held-out patients: {len(held_patients)}")
    for p in held_patients:
        print(f"  {p}")

    # ---- 输出目录 ----
    tumor_dir  = out_dir / "tumor"
    normal_dir = out_dir / "normal"
    tumor_dir.mkdir(parents=True, exist_ok=True)
    normal_dir.mkdir(parents=True, exist_ok=True)

    # ---- 枚举切片并按 mask 分类 ----
    manifest_rows = []
    n_tumor  = 0
    n_normal = 0
    n_skip   = 0

    for patient_dir in held_patients:
        pdir = kaggle3m / patient_dir
        if not pdir.exists():
            print(f"  [warn] patient dir not found: {pdir}, skip")
            n_skip += 1
            continue

        # 收集所有 *_mask.tif（排除 mask 本身找到 pair）
        mask_files = sorted(pdir.glob("*_mask.tif"))
        if not mask_files:
            print(f"  [warn] no mask files in {pdir}, skip")
            n_skip += 1
            continue

        for mask_path in mask_files:
            # 对应图像: stem 去掉 "_mask"
            img_stem = mask_path.stem.replace("_mask", "")
            # 尝试 .tif 和其他后缀
            img_path = None
            for ext in (".tif", ".tiff", ".png", ".jpg"):
                candidate = pdir / (img_stem + ext)
                if candidate.exists():
                    img_path = candidate
                    break

            if img_path is None:
                print(f"  [warn] no image for mask {mask_path.name}, skip")
                continue

            # 读 mask
            try:
                mask_arr = read_mask(mask_path)
            except Exception as e:
                print(f"  [warn] mask read error {mask_path.name}: {e}, skip")
                continue

            mask_px = int(mask_arr.sum())
            is_tumor = mask_px > 0
            split = "tumor" if is_tumor else "normal"
            label = 1 if is_tumor else 0

            # 读图像（FLAIR ch1）
            try:
                flair_img = get_flair_channel(img_path)
            except Exception as e:
                print(f"  [warn] image read error {img_path.name}: {e}, skip")
                continue

            # resize 64x64（与 BraTS 同 input_size，归一化交 score_external）
            flair_resized = flair_img.resize(target_size, Image.BILINEAR)

            # 存 png，文件名: <patient_dir>__<orig_stem>.png
            out_fname = f"{patient_dir}__{img_stem}.png"
            dst_dir   = tumor_dir if is_tumor else normal_dir
            dst_path  = dst_dir / out_fname
            flair_resized.save(dst_path)

            manifest_rows.append({
                "filename":    out_fname,
                "patient_dir": patient_dir,
                "split":       split,
                "label":       label,
                "mask_px":     mask_px,
                "orig_stem":   img_stem,
            })

            if is_tumor:
                n_tumor += 1
            else:
                n_normal += 1

        print(f"  {patient_dir}: done (tumor so far={n_tumor}, normal={n_normal})")

    # ---- 写 manifest ----
    manifest_csv.parent.mkdir(parents=True, exist_ok=True)
    if manifest_rows:
        fieldnames = list(manifest_rows[0].keys())
        with open(manifest_csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(manifest_rows)

    print(f"\n[prep_lgg] SUMMARY")
    print(f"  held-out patients processed: {len(held_patients) - n_skip} / {len(held_patients)}")
    print(f"  tumor slices  (label=1): {n_tumor}")
    print(f"  normal slices (label=0): {n_normal}")
    print(f"  total slices: {n_tumor + n_normal}")
    print(f"  manifest -> {manifest_csv}")
    print(f"  output dirs:")
    print(f"    tumor/  -> {tumor_dir}")
    print(f"    normal/ -> {normal_dir}")

    if n_skip:
        print(f"  [warn] {n_skip} patient dirs skipped (not found or no mask files)")

    return n_tumor, n_normal


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":
    _repo_root = Path(__file__).resolve().parent.parent
    _res  = _repo_root / "results"
    _data = _repo_root / "data"
    _ext  = _data / "external"

    parser = argparse.ArgumentParser(
        description="prep_lgg_heldout.py — LGG 15 独立例切片预处理 (CPU, M-3 held-out)"
    )
    parser.add_argument("--external-dir",
                        default=str(_ext),
                        help="data/external/ 目录（含 lgg-mri-segmentation.zip 或已解压的 kaggle_3m/）")
    parser.add_argument("--dedup-csv",
                        default=str(_res / "phase1" / "lgg_dedup.csv"),
                        help="results/phase1/lgg_dedup.csv（含 overlaps_brats2021 列）")
    parser.add_argument("--out-dir",
                        default=str(_data / "lgg_heldout"),
                        help="输出目录（含 tumor/ normal/ 子目录）")
    parser.add_argument("--manifest-csv",
                        default=str(_res / "phase1" / "lgg_heldout_manifest.csv"),
                        help="输出 manifest csv 路径")
    args = parser.parse_args()
    prep_lgg_heldout(args)
