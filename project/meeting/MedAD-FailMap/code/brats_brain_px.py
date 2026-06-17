"""
brats_brain_px.py — BraTS 脑组织像素数补充列（Phase 1 G1-a 机制对称）
服务: MedAD-FailMap Phase 1, PC-B Gate1 G1-a 几何同构验证
lever: BraTS tumor/brain 对称分母（对应 CBIS mass/breast）

背景：
  BraTS Phase 0 per-image csv（stratify_per_image_ae.csv）的 area_ratio
  分母用全图 64²，含空气/颅骨背景。
  CBIS 正臂用 mass/乳腺组织（area_ratio_breast），两端分母不等价。
  本脚本在 64×64 坐标系内对每张 BraTS tumor 图算 brain_px，
  输出补充 csv（不动 Phase 0 既有 csv）。

BraTS skull-strip 特性 + 正确分割方法：
  BraTS 官方测试图已做 skull-stripping（非脑区=0），脑区灰度>0。

  ⚠️ Bug 修复（v2）：
    旧实现用 Otsu 阈值 → 阈值落在脑内部（FLAIR 亮 tumor/白质分布），
    把亮 tumor 区当「非脑」割掉 → brain_px 偏小 → area_ratio_brain 虚高（最大值 1.885）。

  正确做法（--brain-method nonzero，默认）：
    brain_mask = img > eps（即非零像素区）+ 取最大连通域去孤立噪点。
    skull-strip 后非脑=0，非零=脑组织（含 tumor），brain_px 必然 >= tumor_px。
    tumor ⊂ brain → area_ratio_brain = size_px / brain_px ∈ [0,1] 成立。

  Otsu（--brain-method otsu）：
    保留作 mammogram / 非 skull-strip 场景的 fallback。
    不适用于 skull-strip 数据（已移出默认路径）。

与 CBIS 对称：
  CBIS: area_ratio_breast = mass_px / breast_px（Otsu 最大连通域 = 乳腺区）
        mammogram 有真实黑边（无内容区=0），Otsu 正确区分乳腺 vs 背景。
  BraTS: area_ratio_brain = size_px / brain_px（nonzero 最大连通域 = 脑区）
        skull-strip 后非脑=0，nonzero 直接取脑区，无需 Otsu。

不动 Phase 0：
  不修改 stratify_eval.py 或 stratify_per_image_ae.csv。
  输出独立 csv（results/brats_brain_px.csv），
  area_ratio_check.py 通过 --brats-brain-px-col 参数 join 读取。

断言：
  area_ratio_brain ∈ [0, 1]（tumor ⊂ brain）。
  若 > 1 则 ValueError 暴露（而非静默写入错误数值）。

输出 csv schema：
  filename, brain_px, brain_threshold, full_frame_px, brain_method
  追加（若传 --brats-strat-csv）: size_px, area_ratio_brain, area_ratio_full

依赖: numpy, scikit-image, Pillow
不用 scipy（OMP#15），Windows 路径用 pathlib.Path

CLI 用法（Phase 1 G1-a 对称版）：
  # Step 1: 算 BraTS brain_px（默认 nonzero 方法）
  python code/brats_brain_px.py \\
    --tumor-img-dir data/BraTS2021/test/tumor/ \\
    --out-csv results/brats_brain_px.csv \\
    --img-size 64 \\
    --brats-strat-csv results/stratify_per_image_ae.csv

  # Step 2: G1-a 对称判定
  python code/area_ratio_check.py \\
    --brats-features-csv results/brats_brain_px.csv \\
    --target-features-csv results/lesion_features_cbis_mass.csv \\
    --target-ratio-col area_ratio_breast \\
    --brats-brain-px-col brain_px \\
    --target-name cbis_mass \\
    --out-dir results/
"""

import argparse
import csv
from pathlib import Path

import numpy as np
from PIL import Image


# ============================================================
# 脑组织分割（nonzero 默认 / otsu fallback）
# ============================================================

_BRAIN_METHODS = ("nonzero", "otsu")


def segment_brain(img_arr_gray, brain_method="nonzero", nonzero_eps=1e-6):
    """
    从 skull-stripped BraTS 切片分割脑组织 mask。

    brain_method: str
      "nonzero"（默认）：brain_mask = (img > nonzero_eps)，取最大连通域去孤立噪点。
        适用于 skull-strip 图（非脑区=0，脑区>0）。
        tumor ⊂ 脑组织，故 brain_px >= tumor_px → area_ratio_brain ∈ [0,1] 严格保证。
        ⚠️ v1 用 Otsu → 阈值落脑内部（亮 FLAIR/tumor），brain_px 虚小，ratio >1（max 1.885）。
           已修为默认 nonzero。

      "otsu"（fallback）：img > threshold_otsu(img)，取最大连通域。
        适用于 mammogram 等有真实内容/背景对比的图（CBIS breast segment 用此法）。
        不适用于 skull-strip BraTS（脑内灰度分布 Otsu 会欠割）。

    img_arr_gray: (H,W) uint8 或 float32（内部统一转 float32 [0,1]）。
    nonzero_eps:  nonzero 模式的非零阈值（默认 1e-6，uint8 归一化后 1/255≈0.004 也可）。

    返回:
      brain_mask  : (H,W) bool，True = 脑组织
      threshold   : float，实际使用的阈值（nonzero=eps, otsu=Otsu 阈值）
      brain_px    : int，脑组织像素数
    """
    if brain_method not in _BRAIN_METHODS:
        raise ValueError(f"brain_method 须为 {_BRAIN_METHODS}，得 {brain_method!r}")

    from skimage.measure import label as sk_label

    # 统一归一化到 [0,1]
    if img_arr_gray.dtype == np.uint8:
        arr_f = img_arr_gray.astype(np.float32) / 255.0
    else:
        arr_f = img_arr_gray.astype(np.float32)

    # 极端情况：全零（全黑）切片
    if arr_f.max() == 0.0:
        return np.zeros(arr_f.shape, dtype=bool), 0.0, 0

    if brain_method == "nonzero":
        # skull-strip 核心路径：非零像素=脑组织
        threshold = float(nonzero_eps)
        binary = (arr_f > nonzero_eps).astype(np.uint8)

    else:  # "otsu"
        from skimage.filters import threshold_otsu
        threshold = float(threshold_otsu(arr_f))
        binary = (arr_f > threshold).astype(np.uint8)

    if binary.sum() == 0:
        return np.zeros(binary.shape, dtype=bool), threshold, 0

    # 取最大连通域（4-连通），去孤立噪点
    labeled = sk_label(binary, connectivity=1)
    region_sizes = np.bincount(labeled.ravel())
    region_sizes[0] = 0  # 排除背景 label 0
    largest_label = int(region_sizes.argmax())

    brain_mask = (labeled == largest_label)
    brain_px   = int(brain_mask.sum())

    return brain_mask, threshold, brain_px


# ============================================================
# 单图 brain_px 提取
# ============================================================

def extract_brain_px(img_path, img_size=64, brain_method="nonzero"):
    """
    读 BraTS tumor 切片（skull-stripped），在 img_size×img_size 坐标系内算 brain_px。

    img_size:     须与 stratify_eval.py 的 resize 口径一致（默认 64）。
    brain_method: "nonzero"（默认，skull-strip 正确做法）或 "otsu"（fallback）。
                  详见 segment_brain 文档。

    返回 dict:
      {
        "brain_px":       int,   # 脑组织像素数（最大连通域）
        "brain_threshold": float, # 实际阈值（nonzero=eps, otsu=Otsu 值）
        "full_frame_px":  int,   # resize 后全图像素数（img_size²）
        "brain_method":   str,   # 使用的方法
      }
    """
    pil_img = Image.open(img_path).convert("L")
    if img_size is not None:
        pil_img = pil_img.resize((img_size, img_size), Image.BILINEAR)

    img_arr = np.array(pil_img, dtype=np.uint8)
    brain_mask, threshold, brain_px = segment_brain(img_arr, brain_method=brain_method)

    full_h, full_w = img_arr.shape[:2]
    full_frame_px  = full_h * full_w

    return {
        "brain_px":        brain_px,
        "brain_threshold": threshold,
        "full_frame_px":   full_frame_px,
        "brain_method":    brain_method,
    }


# ============================================================
# 批量提取 + （可选）join stratify_per_image csv
# ============================================================

def batch_extract_brain_px(
    tumor_img_dir,
    out_csv,
    img_size=64,
    brain_method="nonzero",
    brats_strat_csv=None,
    filename_col="filename",
    size_px_col="size_px",
):
    """
    批量提取 BraTS tumor 切片的 brain_px，输出补充 csv。

    Args:
        tumor_img_dir:  BraTS tumor 图像目录（skull-stripped PNG/JPG）
                        命名与 stratify_per_image_ae.csv 的 filename 列一致。
                        # TODO: 确认本地 BraTS tumor 图目录路径（与 stratify_eval 一致）
        out_csv:        输出 csv 路径（results/brats_brain_px.csv）
        img_size:       resize 尺寸，须与 stratify_eval 口径一致（默认 64）
        brain_method:   "nonzero"（默认，skull-strip 正确）或 "otsu"（fallback）
        brats_strat_csv: 若传入，join stratify_per_image_ae.csv（含 filename + size_px），
                         输出列追加 size_px + area_ratio_brain（= size_px / brain_px）。
                         None = 只输出 filename/brain_px/brain_threshold/full_frame_px/brain_method。
        filename_col:   strat csv 中 filename 列名（默认 "filename"）
        size_px_col:    strat csv 中 size_px 列名（默认 "size_px"）

    断言（join 模式）：
        area_ratio_brain = size_px / brain_px 必须 ∈ [0, 1]。
        tumor ⊂ brain，故 size_px <= brain_px。若 > 1 则抛 ValueError（暴露欠割 bug）。

    输出 csv 列（始终含）：
      filename, brain_px, brain_threshold, full_frame_px, brain_method
    追加列（若传 brats_strat_csv）：
      size_px, area_ratio_brain, area_ratio_full
      (area_ratio_brain = size_px/brain_px，area_ratio_full = size_px/full_frame_px)
    """
    if brain_method not in _BRAIN_METHODS:
        raise ValueError(f"brain_method 须为 {_BRAIN_METHODS}，得 {brain_method!r}")

    tumor_dir = Path(tumor_img_dir)

    # 收集图像文件（按 stem 建索引）
    img_map = {}
    for ext in (".png", ".jpg", ".jpeg", ".PNG", ".JPG", ".JPEG"):
        for p in tumor_dir.glob(f"*{ext}"):
            img_map[p.stem] = p

    if not img_map:
        print(f"[brats_brain_px] WARNING: tumor_img_dir 无图像文件: {tumor_dir}")
        print(f"  # TODO: 请传入 BraTS skull-stripped tumor 图像目录")
        return []

    # 若提供 strat csv，建 stem -> size_px 映射
    strat_size_map = {}
    if brats_strat_csv is not None and Path(brats_strat_csv).exists():
        with open(brats_strat_csv, newline="") as f:
            for row in csv.DictReader(f):
                fn  = row.get(filename_col, "")
                spx = row.get(size_px_col, "")
                key = Path(fn).stem
                try:
                    strat_size_map[key] = float(spx)
                except (ValueError, TypeError):
                    pass
        print(f"[brats_brain_px] join strat csv: {len(strat_size_map)} rows from {brats_strat_csv}")
    elif brats_strat_csv is not None:
        print(f"[brats_brain_px] WARNING: brats_strat_csv 不存在: {brats_strat_csv}")

    rows_out = []
    skipped  = 0
    ratio_violations = []  # 收集 > 1 的违反项，批量报告

    for stem, img_path in sorted(img_map.items()):
        try:
            feats = extract_brain_px(img_path, img_size=img_size, brain_method=brain_method)
        except Exception as e:
            print(f"  [warn] {stem}: {e}")
            skipped += 1
            continue

        row = {
            "filename":        img_path.name,
            "brain_px":        feats["brain_px"],
            "brain_threshold": round(feats["brain_threshold"], 6),
            "full_frame_px":   feats["full_frame_px"],
            "brain_method":    feats["brain_method"],
        }

        # 若有 strat csv join，追加 size_px + area_ratio_brain
        if strat_size_map:
            size_px = strat_size_map.get(stem, float("nan"))
            row["size_px"] = size_px if not np.isnan(size_px) else "nan"

            if feats["brain_px"] > 0 and not np.isnan(size_px):
                arb = size_px / feats["brain_px"]
                # 断言 tumor ⊂ brain（area_ratio_brain ∈ [0,1]）
                if arb > 1.0 + 1e-9:
                    ratio_violations.append(
                        f"{img_path.name}: area_ratio_brain={arb:.4f} > 1 "
                        f"(size_px={size_px}, brain_px={feats['brain_px']}, "
                        f"method={brain_method})"
                    )
                row["area_ratio_brain"] = round(arb, 6)
            else:
                row["area_ratio_brain"] = "nan"

            if feats["full_frame_px"] > 0 and not np.isnan(size_px):
                arf = round(size_px / feats["full_frame_px"], 6)
                row["area_ratio_full"] = arf
            else:
                row["area_ratio_full"] = "nan"

        rows_out.append(row)

    # 批量断言：有违反则 ValueError（暴露欠割，不静默写入）
    if ratio_violations:
        raise ValueError(
            f"[brats_brain_px] area_ratio_brain > 1 违反 tumor⊂brain 断言（{len(ratio_violations)} 张）。\n"
            f"根因：brain_method='{brain_method}' 欠割脑区（brain_px < tumor_px）。\n"
            f"解决：BraTS skull-strip 数据请用 --brain-method nonzero（默认）。\n"
            f"前 5 违反：\n  " + "\n  ".join(ratio_violations[:5])
        )

    if skipped > 0:
        print(f"[brats_brain_px] 跳过 {skipped} 张图（处理异常）")

    if not rows_out:
        print("[brats_brain_px] 无输出行，请检查 tumor_img_dir")
        return rows_out

    # 写输出 csv
    if out_csv is not None:
        out_path = Path(out_csv)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # 字段名（有 join 则多几列）
        base_fields = ["filename", "brain_px", "brain_threshold", "full_frame_px", "brain_method"]
        if strat_size_map:
            fieldnames = base_fields + ["size_px", "area_ratio_brain", "area_ratio_full"]
        else:
            fieldnames = base_fields

        with open(out_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows_out)

        print(f"  -> {out_path.name}: {len(rows_out)} rows "
              f"(img_size={img_size}, brain_method={brain_method})")

    return rows_out


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "BraTS 脑组织像素数补充列 — Phase 1 G1-a 机制对称\n"
            "输出 brats_brain_px.csv，供 area_ratio_check.py --brats-brain-px-col 读取。\n"
            "不动 Phase 0 既有 csv 和 stratify_eval.py。\n"
            "# TODO: BraTS tumor 图目录路径待主线确认（与 stratify_eval 一致）"
        )
    )
    _root = Path(__file__).resolve().parent.parent
    _data = _root / "data" / "brats"
    _res  = _root / "results"

    parser.add_argument(
        "--tumor-img-dir",
        default=str(_data / "test" / "tumor"),  # TODO: 待确认真实路径
        help="BraTS skull-stripped tumor 图像目录（PNG/JPG）。# TODO: 待主线确认路径",
    )
    parser.add_argument(
        "--out-csv",
        default=str(_res / "brats_brain_px.csv"),
        help="输出 brain_px 补充 csv 路径",
    )
    parser.add_argument(
        "--img-size",
        type=int,
        default=64,
        help="resize 尺寸（须与 stratify_eval 口径一致，默认 64）",
    )
    parser.add_argument(
        "--brats-strat-csv",
        default=None,
        help=(
            "（可选）stratify_per_image_ae.csv 路径；"
            "传入时 join size_px，输出追加 area_ratio_brain = size_px/brain_px。"
            "推荐传入，方便直接用于 area_ratio_check.py 对称版对比。"
        ),
    )
    parser.add_argument(
        "--brain-method",
        default="nonzero",
        choices=list(_BRAIN_METHODS),
        help=(
            "脑区分割方法（默认 nonzero，skull-strip 数据正确做法）。\n"
            "  nonzero: img > eps 取非零像素 + 最大连通域（skull-strip 后脑区非零）。\n"
            "  otsu:    Otsu 阈值 + 最大连通域（mammogram 等场景的 fallback，"
            "不适用于 BraTS skull-strip）。"
        ),
    )
    parser.add_argument(
        "--filename-col",
        default="filename",
        help="strat csv 中 filename 列名（默认 filename）",
    )
    parser.add_argument(
        "--size-px-col",
        default="size_px",
        help="strat csv 中 size_px 列名（默认 size_px）",
    )
    args = parser.parse_args()

    batch_extract_brain_px(
        tumor_img_dir=args.tumor_img_dir,
        out_csv=args.out_csv,
        img_size=args.img_size,
        brain_method=args.brain_method,
        brats_strat_csv=args.brats_strat_csv,
        filename_col=args.filename_col,
        size_px_col=args.size_px_col,
    )
