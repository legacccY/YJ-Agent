"""
parse_lidc.py — DisagreePred KILL-1 方案甲：pylidc 解析 LIDC-IDRI，构建分歧标签 + patch

服务项目：DisagreePred，lever = KILL-1 gating（方案甲）
禁止：不生成 k=0 负样本；禁垂直翻转；禁私改分歧定义

方案甲设计红线（2026-06-18 skeptic 红队定）：
  - 只保留 k≥1（至少 1 名医师标注）的 nodule cluster
  - 二元标签：disagree_binary = 1 if k∈{1,2,3} else 0（k=4 全一致=0）
  - 禁掺 k=0 负样本（避结节检测 leakage，参见 01_STORY.md KILL-1 设计红线）
  - k=2（2v2）最大分歧，k=1/3 轻微，k=4 全一致；binary disagree="非全体一致"

pylidc 配置说明：
  需在 ~/.pylidcrc 指定 DICOM 目录：
    [dicom]
    path = <LIDC DICOM 根目录>     # 例：D:/data/LIDC-IDRI
  安装：pip install pylidc
  参考：https://pylidc.github.io/

cluster_annotations() tol 说明（researcher 核源 2026-06-18）：
  - 文档写 tol 默认=pixel_spacing，但这是 bug（Scan.py L419 源码为准）
  - 实际默认 tol=slice_thickness；传 tol=None 用默认即可
  - 显式传 tol=None，注释标明，勿传 pixel_spacing

标签来源：Armato et al. Medical Physics 2011 (PMC3041807)
  存在性分歧 65.2% = 2669 被标结节中仅 928 获 4/4 一致

HU 归一化口径：LUNA16（clip[-1000, 400]，归一化 (x+1000)/1400）
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
from pathlib import Path

import numpy as np

# ─── monkey-patch numpy 弃用别名（pylidc 0.2.3 用 np.int/float/bool/object）──
# numpy >= 1.24 移除这些别名，必须在 import pylidc 前打补丁（parse_lidc 在函数
# 内部 import pylidc，但补丁需在模块顶层执行以确保生效）
np.int = int
np.float = float
np.bool = bool
np.object = object
# ─────────────────────────────────────────────────────────────────────────────

# ─── compat: pylidc 用 configparser.SafeConfigParser（Py3.12 已移除）─────────
# 不补丁 → 读不到 ~/.pylidcrc → to_volume 全失败 → 0 cluster
import configparser as _cp
if not hasattr(_cp, "SafeConfigParser"):
    _cp.SafeConfigParser = _cp.ConfigParser
# ─────────────────────────────────────────────────────────────────────────────

# ─── 数据配置（真源：.portfolio/datasets.json lidc_idri.local）────────────
# 数据就位后修改 DATA_ROOT，或通过 --data_root 传入
DATA_ROOT = Path("TODO_LIDC_LOCAL_PATH")   # 待下载 LIDC DICOM 根目录
# 输出目录
OUT_DIR = Path(__file__).resolve().parent.parent / "results"
PATCH_DIR = OUT_DIR / "patches"            # npy patch 存放目录
LABEL_CSV = OUT_DIR / "lidc_disagree_labels.csv"

# patch 参数
PATCH_SIZE = 96        # 96×96 轴向切片（可改 64）
HU_MIN = -1000.0       # LUNA16 肺窗 clip 下界
HU_MAX = 400.0         # LUNA16 肺窗 clip 上界

# 数据集划分（patient-level，防泄漏）
SPLIT_RATIOS = (0.70, 0.15, 0.15)   # train/val/test
RANDOM_SEED = 42


def assert_data_ready(data_root: Path) -> None:
    """数据就位检查——缺失时提前报错，提示下载指引。"""
    assert data_root.exists() and data_root != Path("TODO_LIDC_LOCAL_PATH"), (
        f"[DATA] LIDC 未就位：DATA_ROOT={data_root}\n"
        "请先下载 LIDC-IDRI (~124 GB) 至本地，见 .portfolio/datasets.json lidc_idri 条目。\n"
        "下载源：https://www.cancerimagingarchive.net/collection/lidc-idri/\n"
        "下载完成后：\n"
        "  1. 修改 parse_lidc.py 顶部 DATA_ROOT 指向 DICOM 根目录\n"
        "  2. 配置 ~/.pylidcrc：\n"
        "       [dicom]\n"
        "       path = <LIDC DICOM 根目录>\n"
    )


def hu_normalize(arr: np.ndarray) -> np.ndarray:
    """LUNA16 口径肺窗归一化：clip[-1000, 400] → (x+1000)/1400 → [0,1]。"""
    arr = np.clip(arr.astype(np.float32), HU_MIN, HU_MAX)
    return (arr - HU_MIN) / (HU_MAX - HU_MIN)


def extract_patch_2d(vol: np.ndarray, cz: int, cy: int, cx: int,
                     patch_size: int = PATCH_SIZE) -> np.ndarray | None:
    """
    从 3D volume（z,y,x）提取以 (cz,cy,cx) 为中心的轴向 2D patch。
    HU 已归一化的 float32 volume，返回 (patch_size, patch_size) float32。
    若质心出界则返回 None。
    """
    half = patch_size // 2
    z, h, w = vol.shape
    if cz < 0 or cz >= z:
        return None
    y0, y1 = cy - half, cy + half
    x0, x1 = cx - half, cx + half
    # pad 边界处理
    slice2d = vol[cz]          # (H, W)
    patch = np.zeros((patch_size, patch_size), dtype=np.float32)
    # 源坐标（clamp 到 volume 范围）
    sy0, sy1 = max(y0, 0), min(y1, h)
    sx0, sx1 = max(x0, 0), min(x1, w)
    # 目标坐标（patch 内对应位置）
    dy0, dy1 = sy0 - y0, sy1 - y0
    dx0, dx1 = sx0 - x0, sx1 - x0
    if sy0 >= sy1 or sx0 >= sx1:
        return None
    patch[dy0:dy1, dx0:dx1] = slice2d[sy0:sy1, sx0:sx1]
    return patch


def compute_entropy(k: int, total: int = 4) -> float:
    """
    计算投票熵作为连续分歧度。
    k = 标注该结节的医师数（投票"有结节"的人数，共 total=4）。
    p = k/total（有结节概率），熵 = -p*log2(p) - (1-p)*log2(1-p)（二项）。
    k=0 或 k=4 熵=0（全一致）；k=2 熵=1（最大分歧）。
    """
    if k <= 0 or k >= total:   # k>=total（含 k>4 的 pylidc 合并边缘）熵=0
        return 0.0
    p = k / total
    return float(-p * math.log2(p) - (1 - p) * math.log2(1 - p))


def patient_level_split(patient_ids: list[str],
                        ratios: tuple[float, float, float] = SPLIT_RATIOS,
                        seed: int = RANDOM_SEED
                        ) -> dict[str, str]:
    """
    Patient-level split：同一患者所有 nodule 必须在同一 split（防泄漏）。
    返回 {patient_id: 'train'/'val'/'test'}。
    """
    ids = sorted(set(patient_ids))
    rng = random.Random(seed)
    rng.shuffle(ids)
    n = len(ids)
    n_train = int(n * ratios[0])
    n_val = int(n * ratios[1])
    split_map: dict[str, str] = {}
    for i, pid in enumerate(ids):
        if i < n_train:
            split_map[pid] = "train"
        elif i < n_train + n_val:
            split_map[pid] = "val"
        else:
            split_map[pid] = "test"
    return split_map


def parse_lidc(data_root: Path, out_dir: Path = OUT_DIR,
               patch_dir: Path = PATCH_DIR,
               patch_size: int = PATCH_SIZE) -> None:
    """
    主解析流程：
      1. 遍历所有 Scan，对每个 scan 调用 cluster_annotations(tol=None)
      2. 只保留 k≥1 的 cluster（方案甲：禁 k=0 负样本）
      3. 提取 nodule-centered 2D 轴向 patch（质心 z 层，96×96）
      4. 计算标签 + patient-level split
      5. 输出 lidc_disagree_labels.csv + patch npy 文件
    """
    import pylidc as pl  # 放函数内，顶层 import 报错时可早期提示

    out_dir.mkdir(parents=True, exist_ok=True)
    patch_dir.mkdir(parents=True, exist_ok=True)

    print(f"[parse_lidc] 开始扫描 LIDC-IDRI，DATA_ROOT={data_root}")

    rows: list[dict] = []
    skipped_k0 = 0        # k=0 被跳过数（方案甲禁用，仅计数做统计）
    skipped_vol = 0       # volume 加载失败数
    skipped_patch = 0     # patch 出界数

    # 只处理 data_root 下已下载的 patient（子集 smoke，避免迭代全 1018 scan）
    downloaded = {p.name for p in Path(data_root).iterdir() if p.is_dir()}
    all_scans = pl.query(pl.Scan).all()
    scans = [s for s in all_scans if s.patient_id in downloaded]
    print(f"[parse_lidc] DB 共 {len(all_scans)} scan，data_root 已下载 {len(downloaded)} patient → 处理 {len(scans)} scan")

    for scan in scans:
        patient_id = scan.patient_id  # 例：LIDC-IDRI-0001
        try:
            vol = scan.to_volume()    # ndarray (z, h, w)，单位 HU
        except Exception as e:
            print(f"  [WARN] {patient_id} to_volume 失败: {e}")
            skipped_vol += 1
            continue

        vol_norm = hu_normalize(vol)  # LUNA16 归一化

        # cluster_annotations(tol=None)：用默认 tol=slice_thickness
        # ⚠️ 文档写 pixel_spacing 是 bug，源码 Scan.py L419 为准（researcher 核源 2026-06-18）
        clusters = scan.cluster_annotations(tol=None)

        for cluster_idx, cluster in enumerate(clusters):
            k = len(cluster)  # 标注该 cluster 的医师数

            # ─── 方案甲：禁掺 k=0 负样本（设计红线）──────────────────────
            # k=0 = 无任何医师标注该区域；掺入会让「分歧 vs 不分歧」退化成
            # 「有结节 vs 无结节」（检测 leakage），KILL-1 假 PASS
            if k == 0:
                skipped_k0 += 1
                continue
            # ────────────────────────────────────────────────────────────

            # 二元标签：k=4 全体一致=0；k∈{1,2,3} 非全一致=1
            disagree_binary = 0 if k == 4 else 1

            # 连续分歧度：投票熵（k=2 最大分歧=1.0，k=4/k=0 全一致=0.0）
            disagree_entropy = compute_entropy(k, total=4)

            # 计算 cluster 质心（体素坐标，z=轴向切片索引）
            # 取所有标注的 centroid 均值（各标注者 bbox 质心）
            centroids = []
            for ann in cluster:
                # ann.centroid 返回 (x_mm, y_mm, z_mm) 或直接 bbox；
                # 用 ann.bbox() 取 voxel index range
                # 更可靠：用 ann.boolean_mask() 中心，但 costly
                # pylidc Annotation.centroid 直接返回 (row, col, slice) pixel 坐标
                try:
                    cy_ann, cx_ann, cz_ann = ann.centroid  # (row, col, slice)
                    centroids.append((int(round(cz_ann)),
                                      int(round(cy_ann)),
                                      int(round(cx_ann))))
                except Exception:
                    pass

            if not centroids:
                skipped_patch += 1
                continue

            # 取均值质心
            cz = int(round(np.mean([c[0] for c in centroids])))
            cy = int(round(np.mean([c[1] for c in centroids])))
            cx = int(round(np.mean([c[2] for c in centroids])))

            patch = extract_patch_2d(vol_norm, cz, cy, cx, patch_size)
            if patch is None:
                skipped_patch += 1
                continue

            # 保存 patch npy
            patch_fname = f"{patient_id}_c{cluster_idx:03d}.npy"
            patch_path = patch_dir / patch_fname
            np.save(str(patch_path), patch)

            rows.append({
                "patient_id": patient_id,
                "nodule_cluster_id": f"{patient_id}_c{cluster_idx:03d}",
                "k_annotators": k,
                "disagree_binary": disagree_binary,
                "disagree_entropy": round(disagree_entropy, 6),
                "patch_path": str(patch_path).replace("\\", "/"),
                "split": "__PENDING__",   # patient-level split 在下方统一赋
            })

    if not rows:
        raise RuntimeError("[parse_lidc] 无有效 cluster 提取，请检查 LIDC 数据和 pylidcrc 配置")

    # ─── Patient-level split（防泄漏：同病人不跨 split）──────────────────
    patient_ids = [r["patient_id"] for r in rows]
    split_map = patient_level_split(patient_ids, SPLIT_RATIOS, RANDOM_SEED)
    for r in rows:
        r["split"] = split_map[r["patient_id"]]

    # ─── 写 CSV ──────────────────────────────────────────────────────────
    import csv
    fieldnames = [
        "patient_id", "nodule_cluster_id", "k_annotators",
        "disagree_binary", "disagree_entropy", "patch_path", "split",
    ]
    with open(str(LABEL_CSV), "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # ─── 统计摘要 ─────────────────────────────────────────────────────────
    total = len(rows)
    n_disagree = sum(r["disagree_binary"] for r in rows)
    n_agree = total - n_disagree
    split_counts = {s: sum(1 for r in rows if r["split"] == s)
                    for s in ["train", "val", "test"]}
    k_dist = {}
    for r in rows:
        k_dist[r["k_annotators"]] = k_dist.get(r["k_annotators"], 0) + 1

    summary = {
        "total_clusters": total,
        "disagree_binary_1": n_disagree,
        "disagree_binary_0": n_agree,
        "disagree_rate": round(n_disagree / total, 4) if total else 0,
        "k_distribution": k_dist,
        "split_counts": split_counts,
        "skipped_k0": skipped_k0,
        "skipped_vol_load_fail": skipped_vol,
        "skipped_patch_oob": skipped_patch,
        "patch_size": patch_size,
        "hu_clip": [HU_MIN, HU_MAX],
        "label_source": "Armato et al. Medical Physics 2011 (PMC3041807): 存在性分歧 65.2%",
        "design_note": "方案甲：只保留 k>=1 cluster，禁 k=0 负样本（避检测 leakage）",
    }

    summary_path = OUT_DIR / "parse_lidc_summary.json"
    with open(str(summary_path), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"[parse_lidc] 完成")
    print(f"  总 cluster（k>=1）: {total}")
    print(f"  disagree=1（k∈{{1,2,3}}）: {n_disagree}  ({100*n_disagree/total:.1f}%)")
    print(f"  disagree=0（k=4 全一致）: {n_agree}  ({100*n_agree/total:.1f}%)")
    print(f"  k 分布: {k_dist}")
    print(f"  split: {split_counts}")
    print(f"  跳过 k=0（方案甲禁用）: {skipped_k0}")
    print(f"  CSV → {LABEL_CSV}")
    print(f"  摘要 → {summary_path}")


def main() -> None:
    import multiprocessing
    multiprocessing.freeze_support()   # Windows spawn 必须

    parser = argparse.ArgumentParser(
        description="DisagreePred KILL-1 方案甲：解析 LIDC-IDRI，构建分歧标签 + patch")
    parser.add_argument(
        "--data_root", type=str, default=str(DATA_ROOT),
        help="LIDC DICOM 根目录（需配合 ~/.pylidcrc）")
    parser.add_argument(
        "--out_dir", type=str, default=str(OUT_DIR),
        help="输出目录（默认 results/）")
    parser.add_argument(
        "--patch_size", type=int, default=PATCH_SIZE,
        help="2D patch 边长（96 或 64，默认 96）")
    parser.add_argument(
        "--smoke", type=int, default=0,
        help="smoke 测试模式：处理前 N 个 Scan，0=全量")
    args = parser.parse_args()

    data_root = Path(args.data_root)
    out_dir = Path(args.out_dir)
    patch_dir = out_dir / "patches"

    assert_data_ready(data_root)
    parse_lidc(data_root, out_dir, patch_dir, args.patch_size)


if __name__ == "__main__":
    main()
