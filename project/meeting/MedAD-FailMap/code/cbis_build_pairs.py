"""
cbis_build_pairs.py — awsaf49 CBIS-DDSM mass join
服务: MedAD-FailMap Phase 1, PC-B Gate1 G1-a 几何同构验证
lever: 机制公平面积比（mass/breast 对应 BraTS tumor/brain）

已知坑（awsaf49 版）：
  1. mass csv 的 'cropped image file path' / 'ROI mask file path' 标签有时互换。
     策略：绕过 path 列的标签，改用 dicom_info.SeriesDescription 当真值分类
     每条 dicom 行为 full/ROI mask/cropped。
  2. mass csv 的 path 第一段（如 'Mass-Training_P_00001_LEFT_CC'）
     与 dicom_info.PatientID 直接对应，可用于 join，无须解析 SeriesInstanceUID。

join 逻辑：
  对每条 mass 异常行：
    - full_pid = 'image file path' 第一段 → 查 dicom_info：
        PatientID==full_pid AND SeriesDescription=='full mammogram images'
    - mask_pid = 'ROI mask file path' 第一段 → 查 dicom_info：
        PatientID==mask_pid AND SeriesDescription=='ROI mask images'
      若查到空（可能 csv 标签互换），再查 SeriesDescription=='cropped images'
      并记 swap_flag=True（供调试）。
  配对成功 → 记 abnorm_uid / jpeg 实际路径；失败 → skip + 原因。

输出 csv（per-abnormality）:
  abnorm_uid, split(train/test), patient_id, side, view, abnormality_id,
  abnormality_type, pathology, mass_shape, mass_margins,
  full_img_jpeg_path, roi_mask_jpeg_path,
  swap_flag (0=正常, 1=ROI-mask路径实际是 cropped，已纠正)

依赖: numpy（仅用于计数），pathlib，csv。不用 pandas/scipy/torch。
Windows 路径：统一用 pathlib.Path，输出路径分隔符用 /。
"""

import argparse
import csv
from pathlib import Path


# ============================================================
# 核心 join 函数
# ============================================================

def build_mass_pairs(
    cbis_root: str,
    out_csv: str = None,
    include_test: bool = True,
    verbose: bool = True,
):
    """
    读取 CBIS-DDSM awsaf49 版 csv，产出 mass 配对清单。

    Args:
        cbis_root:    CBIS-DDSM 数据根目录（含 csv/ 和 jpeg/）
        out_csv:      输出 csv 路径。None = 不写文件（只返回 list）
        include_test: True = train + test；False = 只 train
        verbose:      打印进度

    Returns:
        pairs     : list of dict（配对成功的行）
        skip_log  : list of dict（跳过记录，含 skip_reason）
    """
    cbis_root = Path(cbis_root)
    csv_dir   = cbis_root / "csv"
    jpeg_base = cbis_root  # jpeg 路径在 dicom_info 中是 'CBIS-DDSM/jpeg/...'

    # --- 1. 读 dicom_info ---
    dicom_csv = csv_dir / "dicom_info.csv"
    if not dicom_csv.exists():
        raise FileNotFoundError(f"dicom_info.csv 不存在: {dicom_csv}")

    # 按 (PatientID, SeriesDescription) 建索引
    dicom_by_pid_desc: dict[tuple, list[dict]] = {}
    with open(dicom_csv, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            key = (row["PatientID"], row["SeriesDescription"])
            if key not in dicom_by_pid_desc:
                dicom_by_pid_desc[key] = []
            dicom_by_pid_desc[key].append(row)

    # --- 2. 读 mass csv（train + 可选 test）---
    mass_csvs = [csv_dir / "mass_case_description_train_set.csv"]
    if include_test:
        mass_csvs.append(csv_dir / "mass_case_description_test_set.csv")

    all_mass_rows = []
    for p in mass_csvs:
        split_name = "train" if "train" in p.name else "test"
        if not p.exists():
            raise FileNotFoundError(f"mass csv 不存在: {p}")
        with open(p, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                row["_split"] = split_name
                all_mass_rows.append(row)

    if verbose:
        print(f"[cbis_build_pairs] mass rows: {len(all_mass_rows)}")

    # --- 3. join ---
    pairs    = []
    skip_log = []
    n_swap   = 0

    for row in all_mass_rows:
        pid        = row["patient_id"].strip()
        side       = row["left or right breast"].strip()
        view       = row["image view"].strip()
        abnorm_id  = row["abnormality id"].strip()
        atype      = row["abnormality type"].strip()
        pathology  = row["pathology"].strip()
        shape      = row.get("mass shape", "").strip()
        margins    = row.get("mass margins", "").strip()
        split      = row["_split"]

        # 唯一 key：用于输出
        abnorm_uid = f"Mass-{split.capitalize()}_{pid}_{side}_{view}_{abnorm_id}"

        # full mammogram: 'image file path' 第一段
        full_path_str = row.get("image file path", "").strip()
        if not full_path_str:
            skip_log.append({
                "abnorm_uid":  abnorm_uid,
                "skip_reason": "image file path 为空",
            })
            continue
        full_pid = full_path_str.split("/")[0]

        # ROI mask：先按 'ROI mask file path'，可能互换
        mask_path_str = row.get("ROI mask file path", "").strip()
        swap_flag     = 0
        mask_pid      = None

        if mask_path_str:
            mask_pid_raw = mask_path_str.split("/")[0]
            # 优先查 ROI mask images
            if dicom_by_pid_desc.get((mask_pid_raw, "ROI mask images")):
                mask_pid  = mask_pid_raw
                swap_flag = 0
            elif dicom_by_pid_desc.get((mask_pid_raw, "cropped images")):
                # path 列标签互换：实际文件是 cropped images 目录
                # 但 SeriesDescription 里 ROI mask 应在 'cropped image file path' 列
                crop_path_str = row.get("cropped image file path", "").strip()
                if crop_path_str:
                    crop_pid_raw = crop_path_str.split("/")[0]
                    if dicom_by_pid_desc.get((crop_pid_raw, "ROI mask images")):
                        mask_pid  = crop_pid_raw
                        swap_flag = 1
                        n_swap   += 1
                if mask_pid is None:
                    skip_log.append({
                        "abnorm_uid":  abnorm_uid,
                        "skip_reason": f"ROI mask 路径 {mask_pid_raw} SeriesDesc=cropped，cropped path 也找不到 ROI mask",
                    })
                    continue
            else:
                # 完全找不到
                skip_log.append({
                    "abnorm_uid":  abnorm_uid,
                    "skip_reason": f"ROI mask PatientID={mask_pid_raw} 在 dicom_info 中找不到任何匹配",
                })
                continue
        else:
            skip_log.append({
                "abnorm_uid":  abnorm_uid,
                "skip_reason": "ROI mask file path 为空",
            })
            continue

        # 查 full mammogram jpeg
        full_dicom_rows = dicom_by_pid_desc.get((full_pid, "full mammogram images"), [])
        if not full_dicom_rows:
            skip_log.append({
                "abnorm_uid":  abnorm_uid,
                "skip_reason": f"full mammogram PatientID={full_pid} 在 dicom_info 中找不到",
            })
            continue

        # 查 ROI mask jpeg
        mask_dicom_rows = dicom_by_pid_desc.get((mask_pid, "ROI mask images"), [])
        if not mask_dicom_rows:
            skip_log.append({
                "abnorm_uid":  abnorm_uid,
                "skip_reason": f"ROI mask PatientID={mask_pid} 在 dicom_info 中找不到",
            })
            continue

        # 取第一个（每 PatientID + SeriesDescription 组合通常只有 1 行）
        full_rel  = full_dicom_rows[0]["image_path"]   # 'CBIS-DDSM/jpeg/...'
        mask_rel  = mask_dicom_rows[0]["image_path"]

        # 转成实际绝对路径
        # dicom_info.image_path 前缀 'CBIS-DDSM/' 对应 cbis_root
        full_jpeg_path = (jpeg_base / full_rel.replace("CBIS-DDSM/", "")).as_posix()
        mask_jpeg_path = (jpeg_base / mask_rel.replace("CBIS-DDSM/", "")).as_posix()

        # 文件存在性校验
        if not Path(full_jpeg_path).exists():
            skip_log.append({
                "abnorm_uid":  abnorm_uid,
                "skip_reason": f"full jpeg 文件不存在: {full_jpeg_path}",
            })
            continue
        if not Path(mask_jpeg_path).exists():
            skip_log.append({
                "abnorm_uid":  abnorm_uid,
                "skip_reason": f"ROI mask jpeg 文件不存在: {mask_jpeg_path}",
            })
            continue

        pairs.append({
            "abnorm_uid":        abnorm_uid,
            "split":             split,
            "patient_id":        pid,
            "side":              side,
            "view":              view,
            "abnormality_id":    abnorm_id,
            "abnormality_type":  atype,
            "pathology":         pathology,
            "mass_shape":        shape,
            "mass_margins":      margins,
            "full_img_jpeg_path":  full_jpeg_path,
            "roi_mask_jpeg_path":  mask_jpeg_path,
            "swap_flag":         swap_flag,
        })

    # --- 4. 报告 ---
    if verbose:
        print(f"[cbis_build_pairs] 配对成功: {len(pairs)}")
        print(f"[cbis_build_pairs] 跳过: {len(skip_log)}")
        if n_swap > 0:
            print(f"[cbis_build_pairs] swap_flag=1（ROI/crop 路径互换已纠正）: {n_swap}")
        if skip_log:
            # 按原因汇总
            from collections import Counter
            reason_counts = Counter(r["skip_reason"].split(":")[0] for r in skip_log)
            for reason, cnt in reason_counts.most_common():
                print(f"  skip [{cnt}]: {reason}")

    # --- 5. 写输出 csv ---
    if out_csv and pairs:
        out_path = Path(out_csv)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = [
            "abnorm_uid", "split", "patient_id", "side", "view", "abnormality_id",
            "abnormality_type", "pathology", "mass_shape", "mass_margins",
            "full_img_jpeg_path", "roi_mask_jpeg_path", "swap_flag",
        ]
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(pairs)
        if verbose:
            print(f"[cbis_build_pairs] -> {out_path}")

    return pairs, skip_log


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "CBIS-DDSM awsaf49 版 mass 配对 join\n"
            "产出 per-abnormality 配对清单 csv（含 full jpeg + ROI mask jpeg 绝对路径）\n"
            "服务: MedAD-FailMap Phase 1 G1-a 几何同构验证"
        )
    )
    _default_root = Path("D:/YJ-Agent/data/external/cbis_ddsm")
    _default_out  = Path(__file__).resolve().parent.parent / "results" / "cbis_mass_pairs.csv"

    parser.add_argument(
        "--cbis-root",
        default=str(_default_root),
        help="CBIS-DDSM 数据根目录（含 csv/ + jpeg/）",
    )
    parser.add_argument(
        "--out-csv",
        default=str(_default_out),
        help="输出配对清单 csv",
    )
    parser.add_argument(
        "--no-test",
        action="store_true",
        help="只用 train set（默认 train+test）",
    )
    args = parser.parse_args()

    pairs, skip_log = build_mass_pairs(
        cbis_root=args.cbis_root,
        out_csv=args.out_csv,
        include_test=not args.no_test,
        verbose=True,
    )
    print(f"\n配对成功: {len(pairs)}，跳过: {len(skip_log)}")
