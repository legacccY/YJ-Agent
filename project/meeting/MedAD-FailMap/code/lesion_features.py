"""
lesion_features.py — HAM/METS 同口径特征提取（Phase 1 PC-B 跨集外推）
服务: MedAD-FailMap Phase 1, PC-B T6/B2 (G1-a 同构性)

给定图像 + 对应 binary lesion mask（ISIC_<id>_segmentation.png），
计算与 BraTS 同口径:
  size_px  = 最大连通域面积（像素，skimage.measure.label 4-连通）
             — 直接复用 stratify_eval.compute_mask_covariate 口径
  contrast = |mean(灰度,病灶内) − mean(灰度,环带)|
             ring = mask 边界向外 dilation，
             宽度 = mask 等效直径 × ring_width_frac
             — 复用 stratify_eval.compute_contrast 结构，宽度参数化

PR-2 口径统一（Phase 1 专用，不动 Phase 0）:
  Phase 1 跨集 contrast 两端均用**相对环宽**（equiv_diam × ring_frac），
  在 64×64 resize 坐标系上算（与 BraTS 64px 口径一致）。
  BraTS Phase 0 的 3px 绝对环宽口径（stratify_eval.compute_contrast(dilation_px=3)）
  保持不动——只有 Phase 0 的 PC-A csv 用它，Phase 1 特征单独存、不覆盖。
  三档敏感性：ring_frac in {0.05, 0.075, 0.10}，CLI 支持传单值或三档扫描。
  # TODO: PR-2 ring_frac=0.075 为 06_phase1_plan 建议值，待 reviewer 复裁 + 主线拍板冻结。

PR-1 口径（Phase 1）:
  detected 阈值在**病灶子集（dx!=nv 异常皮损）**内算 P{detected_pct}（CLI --lesion-dx-filter）。
  # TODO: PR-1 detected_pct=90 / 病灶子集定义 待 reviewer 复裁 + 主线拍板冻结。

输出 csv schema 与 BraTS per-image 对齐（同 stratify_eval 产出的 stratify_per_image_ae.csv）：
  filename / size_px / contrast / anomaly_score / detected / seed / ring_frac

依赖: numpy, scikit-image, Pillow
不用 scipy（OMP#15）
Windows 路径用 pathlib.Path，DataLoader 不在此模块（无 torch）
"""

import argparse
import csv
from pathlib import Path

import numpy as np
from PIL import Image


# ============================================================
# 复用 BraTS 口径（对齐 stratify_eval.py 函数，不另立）
# ============================================================

def compute_size_px(mask_arr):
    """
    最大连通域面积（像素数），4-连通，与 stratify_eval.compute_mask_covariate 同口径。
    mask_arr: (H,W) uint8，>0 为病灶
    返回 int
    """
    from skimage.measure import label as sk_label
    mask_bin = (mask_arr > 0).astype(np.uint8)
    if mask_bin.sum() == 0:
        return 0
    labeled = sk_label(mask_bin, connectivity=1)
    regions = np.bincount(labeled.ravel())
    regions[0] = 0
    return int(regions.max())


def compute_contrast_relative(img_arr, mask_arr, ring_width_frac=0.075):
    """
    contrast = |mean(img[lesion]) - mean(img[ring])|
    ring = dilation(mask, dilation_px) XOR mask
    dilation_px = max(1, round(equiv_diameter * ring_width_frac))
      equiv_diameter = sqrt(4 * size_px / pi)  （mask 等效直径，圆等面积）

    对 BraTS（dilation_px=3 固定）调用时：
      ring_width_frac 参数不适用，用 stratify_eval.compute_contrast(dilation_px=3) 更原子。
      本函数仅供 HAM/METS（需相对环宽）。

    PR-2: ring_width_frac 默认 0.075，跑前冻结进 05_preregistration。
    # TODO: PR-2 ring_width_frac=0.075 为 06_phase1_plan 建议值，待 reviewer 复裁 + 主线拍板冻结。
    """
    from skimage.morphology import dilation, disk
    mask_bin = (mask_arr > 0)
    if mask_bin.sum() == 0:
        return 0.0, 0
    size_px = int(mask_bin.sum())
    equiv_diam = float(np.sqrt(4.0 * size_px / np.pi))
    dilation_px = max(1, round(equiv_diam * ring_width_frac))

    dilated = dilation(mask_bin.astype(np.uint8), footprint=disk(dilation_px)).astype(bool)
    ring = dilated & (~mask_bin)
    if ring.sum() == 0:
        return 0.0, dilation_px
    lesion_mean = float(img_arr[mask_bin].mean())
    ring_mean = float(img_arr[ring].mean())
    return abs(lesion_mean - ring_mean), dilation_px


def load_img_gray(img_path, size=None):
    """
    读图为灰度 float [0,1]。
    size: int -> resize 到 (size, size)（与 BraTS 64px 口径对齐）；None 不 resize。
    """
    p = Path(img_path)
    img = Image.open(p).convert("L")
    if size is not None:
        img = img.resize((size, size), Image.BILINEAR)
    return np.array(img, dtype=np.float32) / 255.0


def load_mask_bin(mask_path, size=None):
    """
    读 binary lesion mask，>127 为前景。
    size: int -> resize 到 (size, size) (NEAREST)。
    """
    p = Path(mask_path)
    mask = Image.open(p).convert("L")
    if size is not None:
        mask = mask.resize((size, size), Image.NEAREST)
    arr = np.array(mask, dtype=np.uint8)
    arr = (arr > 127).astype(np.uint8) * 255
    return arr


# ============================================================
# 单图特征提取
# ============================================================

def extract_lesion_features(img_path, mask_path, ring_width_frac=0.075, img_size=None):
    """
    给定一张图及对应 binary mask，返回同口径特征 dict。
    img_size: 若非 None，resize 到 img_size x img_size（BraTS 口径=64）。

    返回:
      {
        "size_px":      int,
        "contrast":     float,
        "dilation_px":  int,     # 实际使用的环宽 px（供调试）
        "ring_width_frac": float,
        "img_h":        int,     # 原始图 H
        "img_w":        int,     # 原始图 W
      }
    """
    img_arr = load_img_gray(img_path, size=img_size)
    mask_arr = load_mask_bin(mask_path, size=img_size)

    size_px = compute_size_px(mask_arr)
    contrast, dilation_px = compute_contrast_relative(img_arr, mask_arr,
                                                       ring_width_frac=ring_width_frac)

    # 原始图尺寸（不 resize 时）
    raw = np.array(Image.open(img_path))
    img_h, img_w = raw.shape[:2]

    return {
        "size_px":         size_px,
        "contrast":        float(contrast),
        "dilation_px":     dilation_px,
        "ring_width_frac": ring_width_frac,
        "img_h":           img_h,
        "img_w":           img_w,
    }


def extract_lesion_features_phase1(img_path, mask_path, ring_width_frac=0.075,
                                   phase1_img_size=64):
    """
    PR-2 Phase 1 专用：强制在 64×64 坐标系上算特征，与 BraTS 64px 口径一致。
    不动 Phase 0 的 extract_lesion_features（保留 img_size=None 默认）。

    phase1_img_size: Phase 1 固定 64（不允许 None，确保坐标系统一）。
    ring_width_frac: 相对环宽（等效直径百分比），Phase 1 两端统一使用。
      三档敏感性：{0.05, 0.075, 0.10}，由调用方循环传入。
      # TODO: PR-2 三档冻结单值 待 reviewer 复裁 + 主线拍板冻结。
    """
    assert phase1_img_size is not None and phase1_img_size > 0, (
        "Phase 1 要求强制 resize，phase1_img_size 不得为 None"
    )
    return extract_lesion_features(
        img_path, mask_path,
        ring_width_frac=ring_width_frac,
        img_size=phase1_img_size,
    )


# ============================================================
# 批量提取 + 与 anomaly score csv join
# ============================================================

def _load_dx_filter_set(lesion_dx_filter):
    """
    PR-1: 从 dx_filter 参数加载允许通过的 img_id 集合。
    lesion_dx_filter:
      - None / "all"  → 不过滤（返回 None）
      - "exclude_nv"  → 从 score_csv 中排除 dx==nv 的图（默认 Phase 1 语义）
      - str（csv 路径）→ 读 csv，保留 dx 列 != "nv" 的 img_id 集合
      - list/set       → 直接作为允许 img_id 集合

    注意：调用方需将 img_id 与此集合比对，不在集合内的跳过。
    返回 set(img_id) 或 None（不过滤）。
    # TODO: PR-1 病灶子集定义 待 reviewer 复裁 + 主线拍板冻结。
    """
    if lesion_dx_filter is None or lesion_dx_filter == "all":
        return None
    if isinstance(lesion_dx_filter, (list, set)):
        return set(lesion_dx_filter)
    if isinstance(lesion_dx_filter, str) and lesion_dx_filter == "exclude_nv":
        # 占位：调用方需传 metadata csv 路径，此处返回特殊哨兵
        return "EXCLUDE_NV"
    if isinstance(lesion_dx_filter, str) and Path(lesion_dx_filter).exists():
        allowed = set()
        with open(lesion_dx_filter, newline="") as f:
            for row in csv.DictReader(f):
                dx = row.get("dx", row.get("label", "")).strip().lower()
                img_id = row.get("image_id", row.get("filename", "")).strip()
                img_id = Path(img_id).stem.replace("_segmentation", "")
                if dx != "nv" and img_id:
                    allowed.add(img_id)
        return allowed
    return None


def batch_extract(
    img_dir=None,
    mask_dir=None,
    score_csv=None,
    out_csv=None,
    ring_width_frac=0.075,
    img_size=None,
    seed=42,
    detected_pct=90.0,
    lesion_only_dx=None,
    lesion_dx_filter=None,
    metadata_csv=None,
    ring_frac_list=None,
    phase1_mode=False,
    img_dirs=None,
):
    """
    批量提取 img_dir（或多个 img_dirs）中所有图的 lesion features，join anomaly score csv。

    Args:
        img_dir:          图像目录（ISIC_<id>.jpg 等）；与 img_dirs 二选一，传了 img_dirs 则此参数被忽略
        img_dirs:         多图像目录（list of str/Path），用于 HAM10000 part_1+part_2 等多目录场景；
                          传了此参数则 img_dir 被忽略。
        mask_dir:         mask 目录（ISIC_<id>_segmentation.png，HAM10000 官方命名）
        score_csv:        (可选) anomaly score csv，join 用 filename 列
        out_csv:          输出 csv 路径（单档 ring_frac 时用；三档时自动追加 _rfrac{v} 后缀）
        ring_width_frac:  PR-2 环宽，默认 0.075（单档模式）
        img_size:         resize 尺寸，None 不 resize
        seed:             PR-5 seed（写入输出 csv，多 seed 聚合用）
        detected_pct:     PR-1 detected 阈值百分位（在病灶子集内算 P90），默认 90
        lesion_only_dx:   (废弃，兼容旧调用) 同 lesion_dx_filter
        lesion_dx_filter: PR-1 dx 过滤：None="all"/不过滤；"exclude_nv"=排除 nv（需 metadata_csv）；
                          str=metadata csv 路径（dx!=nv 行）；list/set=允许 img_id 集合
                          默认 None（不过滤），Phase 1 CLI 默认 "exclude_nv"。
                          # TODO: PR-1 待冻结。
        metadata_csv:     HAM metadata csv 路径（dx 列过滤用，当 lesion_dx_filter="exclude_nv" 时必传）
        ring_frac_list:   PR-2 三档敏感性扫描，list of float，如 [0.05, 0.075, 0.10]。
                          传入时循环跑三档并各输出一个 csv（out_csv 追加 _rf{v} 后缀）。
                          不传时仅跑 ring_width_frac 单档。
                          # TODO: PR-2 三档冻结单值 待 reviewer 复裁 + 主线拍板冻结。
        phase1_mode:      True = PR-2 强制 img_size=64（两端坐标系统一），忽略 img_size 参数。

    PR-1: detected 在病灶子集（dx!=nv 异常皮损）内算 P90（跨集同构语义）
    PR-2: ring_frac 三档扫描，外推结论须三档方向一致才算确证。
    """
    # PR-2 phase1_mode 强制 resize=64
    if phase1_mode:
        img_size = 64

    # PR-1 dx 过滤集合（兼容旧参数 lesion_only_dx）
    _dx_filter_param = lesion_dx_filter if lesion_dx_filter is not None else lesion_only_dx
    dx_allowed = None
    if _dx_filter_param is not None:
        if _dx_filter_param == "exclude_nv":
            # 需要 metadata_csv 解析 dx!=nv
            if metadata_csv and Path(metadata_csv).exists():
                _dx_filter_param = metadata_csv
                dx_allowed = _load_dx_filter_set(_dx_filter_param)
            else:
                print("[lesion_features] PR-1: lesion_dx_filter='exclude_nv' 需传 --metadata-csv，"
                      "当前 metadata_csv 未提供，跳过 dx 过滤")
        else:
            dx_allowed = _load_dx_filter_set(_dx_filter_param)

    # 三档 ring_frac 扫描 vs 单档
    fracs_to_run = ring_frac_list if ring_frac_list else [ring_width_frac]

    all_results = {}  # frac -> rows_out
    for frac in fracs_to_run:
        rows_out = _batch_extract_single_frac(
            img_dir=img_dir,
            img_dirs=img_dirs,
            mask_dir=mask_dir,
            score_csv=score_csv,
            ring_width_frac=frac,
            img_size=img_size,
            seed=seed,
            detected_pct=detected_pct,
            dx_allowed=dx_allowed,
        )
        all_results[frac] = rows_out

        if out_csv:
            # 多档时加后缀区分，单档保持原文件名
            if len(fracs_to_run) > 1:
                p = Path(out_csv)
                frac_str = str(frac).replace(".", "p")
                out_path = p.parent / (p.stem + f"_rf{frac_str}" + p.suffix)
            else:
                out_path = Path(out_csv)
            if rows_out:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                fieldnames = ["filename", "size_px", "contrast", "dilation_px",
                              "ring_frac", "anomaly_score", "label", "detected", "seed"]
                with open(out_path, "w", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=fieldnames)
                    w.writeheader()
                    w.writerows(rows_out)
                print(f"  -> {out_path.name}: {len(rows_out)} rows (ring_frac={frac})")

    # 返回：单档返回 list，多档返回 dict
    if len(fracs_to_run) == 1:
        return all_results[fracs_to_run[0]]
    return all_results


def _batch_extract_single_frac(
    img_dir,
    mask_dir,
    score_csv,
    ring_width_frac,
    img_size,
    seed,
    detected_pct,
    dx_allowed,
    img_dirs=None,
):
    """
    内部函数：单档 ring_frac 的批量提取逻辑（batch_extract 循环调用）。
    dx_allowed: set(img_id) 或 None（不过滤）。
    img_dirs: 多目录（list of str/Path），优先于 img_dir；传了则 img_dir 被忽略。
    """
    # 解析图像目录列表：img_dirs 优先，否则退回 img_dir
    if img_dirs:
        _img_dirs = [Path(d) for d in img_dirs]
    else:
        _img_dirs = [Path(img_dir)]
    mask_dir = Path(mask_dir)

    # 收集 mask 文件（HAM10000 官方命名 ISIC_<id>_segmentation.png）
    mask_files = sorted(mask_dir.glob("*_segmentation.png"))
    if not mask_files:
        mask_files = sorted(mask_dir.glob("*.png"))  # fallback

    # 构建 img_id -> mask_path 映射
    mask_map = {}
    for mf in mask_files:
        stem = mf.stem  # e.g. ISIC_0024306_segmentation
        img_id = stem.replace("_segmentation", "")  # -> ISIC_0024306
        mask_map[img_id] = mf

    # 读 anomaly score csv（若提供），建 filename -> row dict
    score_map = {}
    if score_csv and Path(score_csv).exists():
        with open(score_csv, newline="") as f:
            for row in csv.DictReader(f):
                fn = row.get("filename", "")
                key = Path(fn).stem  # strip extension
                score_map[key] = row

    rows_out = []
    for img_id, mask_path in mask_map.items():
        # PR-1: dx 过滤（仅保留 dx!=nv 的病灶子集）
        if dx_allowed is not None and dx_allowed != "EXCLUDE_NV":
            if img_id not in dx_allowed:
                continue  # 不在允许集合，跳过

        # 查找对应图：在所有图目录里搜（多目录支持 HAM part_1/part_2）
        img_path = None
        for _d in _img_dirs:
            for ext in (".jpg", ".jpeg", ".png", ".JPG", ".JPEG", ".PNG"):
                candidate = _d / (img_id + ext)
                if candidate.exists():
                    img_path = candidate
                    break
            if img_path is not None:
                break
        if img_path is None:
            continue  # 找不到图跳过（skip，不 crash）

        try:
            feats = extract_lesion_features(
                img_path, mask_path,
                ring_width_frac=ring_width_frac,
                img_size=img_size,
            )
        except Exception as e:
            print(f"  [warn] {img_id}: {e}")
            continue

        # join score csv
        score_row = score_map.get(img_id, {})
        anomaly_score_str = score_row.get("anomaly_score", "nan")
        label_str = score_row.get("label", "nan")

        rows_out.append({
            "filename":    img_id + (img_path.suffix if img_path else ""),
            "size_px":     feats["size_px"],
            "contrast":    round(feats["contrast"], 6),
            "dilation_px": feats["dilation_px"],
            "ring_frac":   feats["ring_width_frac"],   # PR-2: 旧列名 ring_width_frac -> ring_frac
            "anomaly_score": anomaly_score_str,
            "label":       label_str,
            "seed":        seed,
        })

    if not rows_out:
        print(f"[lesion_features] no rows extracted (ring_frac={ring_width_frac}), "
              f"check img_dir/mask_dir or dx_filter")
        return rows_out

    # PR-1: detected 在病灶子集内算 P{detected_pct}
    scores_arr = np.array([
        float(r["anomaly_score"]) if r["anomaly_score"] not in ("nan", "", None)
        else float("nan")
        for r in rows_out
    ])
    valid_scores = scores_arr[~np.isnan(scores_arr)]
    if len(valid_scores) >= 10:
        threshold = float(np.percentile(valid_scores, detected_pct))
        for i, r in enumerate(rows_out):
            s = scores_arr[i]
            r["detected"] = int(s >= threshold) if not np.isnan(s) else "nan"
        print(f"[lesion_features] PR-1 detected threshold (P{detected_pct:.0f} lesion-only, "
              f"ring_frac={ring_width_frac}): {threshold:.6f}")
    else:
        for r in rows_out:
            r["detected"] = "nan"
        print(f"[lesion_features] insufficient scores for P{detected_pct:.0f} threshold "
              f"(ring_frac={ring_width_frac}), detected=nan")

    return rows_out


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Phase 1 HAM/METS 同口径 lesion 特征提取（G1-a 同构性）"
    )
    _root = Path(__file__).resolve().parent.parent
    _res = _root / "results"

    parser.add_argument("--img-dir", default=None,
                        help="图像目录（单目录）；与 --img-dirs 二选一，传了 --img-dirs 则此参数被忽略")
    parser.add_argument("--img-dirs", nargs="+", default=None,
                        help="多图像目录（空格分隔），用于 HAM10000 part_1+part_2 等多目录场景；"
                             "传了此参数则 --img-dir 被忽略。"
                             "示例: --img-dirs path/part_1 path/part_2")
    parser.add_argument("--mask-dir", required=True,
                        help="mask 目录（HAM: HAM10000_segmentations_lesion_tschandl/）")
    parser.add_argument("--score-csv", default=None,
                        help="(可选) anomaly score csv，join filename 列")
    parser.add_argument("--out-csv",
                        default=str(_res / "lesion_features_ham.csv"))
    parser.add_argument("--ring-width-frac", type=float, default=0.075,
                        help="PR-2: mask 等效直径的百分比作环宽（默认 0.075=7.5%%）"
                             " # TODO: PR-2 待冻结单值")
    parser.add_argument("--ring-frac-list", type=float, nargs="+", default=None,
                        help="PR-2 三档敏感性扫描：传 3 个值如 0.05 0.075 0.10；"
                             "传入时循环出三个 csv（out_csv 追加 _rf* 后缀）。"
                             "不传则只跑 --ring-width-frac 单档。"
                             " # TODO: PR-2 三档冻结单值 待 reviewer 复裁 + 主线拍板冻结。")
    parser.add_argument("--img-size", type=int, default=None,
                        help="resize 到 N×N（BraTS 口径=64）；None=不 resize")
    parser.add_argument("--phase1-mode", action="store_true",
                        help="PR-2 Phase 1 模式：强制 img_size=64（两端坐标系统一）")
    parser.add_argument("--seed", type=int, default=42,
                        help="seed 标记（写入 csv，多 seed 聚合用，PR-5）")
    parser.add_argument("--detected-pct", type=float, default=90.0,
                        help="PR-1: detected 阈值百分位，在病灶子集内算（默认 90）"
                             " # TODO: PR-1 待冻结")
    parser.add_argument("--lesion-dx-filter", default=None,
                        help="PR-1 dx 过滤：None=不过滤；exclude_nv=排除 nv（需 --metadata-csv）；"
                             "str=metadata csv 路径（dx!=nv 行）。"
                             "默认 None，Phase 1 建议传 exclude_nv。"
                             " # TODO: PR-1 待冻结")
    parser.add_argument("--metadata-csv", default=None,
                        help="HAM metadata csv 路径（dx 列过滤用，--lesion-dx-filter=exclude_nv 时必传）")
    args = parser.parse_args()

    # --img-dirs 优先；两个都没传则报错
    _img_dirs_arg = args.img_dirs if args.img_dirs else None
    if _img_dirs_arg is None and args.img_dir is None:
        parser.error("需传 --img-dir（单目录）或 --img-dirs（多目录，可多个）之一")

    batch_extract(
        img_dir=args.img_dir,
        img_dirs=_img_dirs_arg,
        mask_dir=args.mask_dir,
        score_csv=args.score_csv,
        out_csv=args.out_csv,
        ring_width_frac=args.ring_width_frac,
        img_size=args.img_size,
        seed=args.seed,
        detected_pct=args.detected_pct,
        lesion_dx_filter=args.lesion_dx_filter,
        metadata_csv=args.metadata_csv,
        ring_frac_list=args.ring_frac_list,
        phase1_mode=args.phase1_mode,
    )
