"""
lidc_disagreement_stats.py — DisagreePred：XML-only 分歧信号分布统计

服务项目：DisagreePred，lever = KILL-1 gating（分歧信号先验核实）
禁止：零 CT 下载（纯 DB/XML 统计）；不改 parse_lidc.py 业务逻辑；不碰别项目

目标：
  - 遍历全 1018 scan，cluster_annotations() 不加载 DICOM volume
  - 统计 k=1/2/3/4 各多少 cluster
  - 计算 k<4（存在分歧）vs k=4（全一致）比例
  - 对照 Armato2011 口径：存在性分歧 ~65.2%（2669 被标结节中 928=34.8% 获 4/4 一致）
    注：cluster 阈值 tol 不同会导致 cluster 数略有差异，数量级一致即满足
  - 输出逐 cluster CSV + print summary

输出：project/meeting/DisagreePred/results/lidc_disagreement_dist.csv
列：scan_pid, cluster_idx, k_annotators, disagree_binary, disagree_strength

disagree_strength 定义：min(k, 4-k) / 2
  k=0: 0.0（无标注，不应出现，设防）
  k=1: 0.5 (min(1,3)/2)
  k=2: 1.0 (min(2,2)/2) ← 最大分歧
  k=3: 0.5 (min(3,1)/2)
  k=4: 0.0 (min(4,0)/2) ← 全一致

cluster_annotations() 说明（researcher 核源 2026-06-18）：
  tol=None → 用默认 tol=slice_thickness（源码 Scan.py L419）
  cluster_annotations() 不需要 DICOM volume，纯 XML/DB 运算，zero-download
"""

from __future__ import annotations

# ─── monkey-patch numpy 弃用别名（pylidc 0.2.3 用 np.int/float/bool/object）──
# numpy >= 1.24 移除这些别名，必须在 import pylidc 前打补丁
import numpy as np
np.int = int
np.float = float
np.bool = bool
np.object = object
# ─────────────────────────────────────────────────────────────────────────────

import csv
import math
import sys
from pathlib import Path

import pylidc as pl  # noqa: E402（monkey-patch 必须在前）

# ─── 输出路径 ─────────────────────────────────────────────────────────────────
OUT_DIR = Path(__file__).resolve().parent.parent / "results"
OUT_CSV = OUT_DIR / "lidc_disagreement_dist.csv"

# ─── Armato2011 参照数字（Armato et al. Medical Physics 2011, PMC3041807）────
# 2669 被标结节中 928 获 4/4 全一致 = 34.8%，即存在性分歧 = 65.2%
# 注：我们的 cluster 数可能因 tol 设置略有不同，数量级一致即满足
ARMATO_AGREE_FRAC = 0.348   # 34.8% k=4
ARMATO_DISAGREE_FRAC = 0.652  # 65.2% k<4


def disagree_strength(k: int, total: int = 4) -> float:
    """
    连续分歧度：min(k, total-k) / (total/2)
    k=2 最大=1.0；k=4 或 k=0 全一致=0.0；k=1/3 轻微=0.5
    """
    if k <= 0 or k >= total:
        return 0.0
    return min(k, total - k) / (total / 2)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    scans = pl.query(pl.Scan).all()
    total_scans = len(scans)
    print(f"[lidc_disagreement_stats] 总 Scan 数: {total_scans}")

    rows: list[dict] = []
    skipped_scans: int = 0   # cluster_annotations 抛异常的 scan 数

    for scan_idx, scan in enumerate(scans):
        pid = scan.patient_id
        try:
            # tol=None 用默认 slice_thickness，不需 DICOM volume（pure XML/DB）
            clusters = scan.cluster_annotations(tol=None)
        except Exception as exc:
            print(f"  [WARN] scan {pid} cluster_annotations 失败: {exc}", file=sys.stderr)
            skipped_scans += 1
            continue

        for cidx, cluster in enumerate(clusters):
            k = len(cluster)
            disagree_bin = 0 if k == 4 else 1
            strength = disagree_strength(k, total=4)
            rows.append({
                "scan_pid": pid,
                "cluster_idx": cidx,
                "k_annotators": k,
                "disagree_binary": disagree_bin,
                "disagree_strength": round(strength, 4),
            })

        # 进度每 100 scan 打一次
        if (scan_idx + 1) % 100 == 0:
            print(f"  processed {scan_idx + 1}/{total_scans} scans, clusters so far: {len(rows)}")

    # ─── 写 CSV ───────────────────────────────────────────────────────────────
    fieldnames = ["scan_pid", "cluster_idx", "k_annotators", "disagree_binary", "disagree_strength"]
    with open(str(OUT_CSV), "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # ─── 统计摘要 ──────────────────────────────────────────────────────────────
    total_clusters = len(rows)
    if total_clusters == 0:
        print("[ERROR] 无任何 cluster，检查 pylidc 配置。", file=sys.stderr)
        sys.exit(1)

    k_counts: dict[int, int] = {}
    for r in rows:
        k = r["k_annotators"]
        k_counts[k] = k_counts.get(k, 0) + 1

    n_agree = k_counts.get(4, 0)       # k=4 全一致
    n_disagree = total_clusters - n_agree  # k<4 存在分歧

    agree_frac = n_agree / total_clusters
    disagree_frac = n_disagree / total_clusters

    # 对照偏差
    diff_vs_armato = abs(disagree_frac - ARMATO_DISAGREE_FRAC)
    match_flag = "对上 (数量级一致)" if diff_vs_armato < 0.10 else "偏差 >10%，注意核查"

    print()
    print("=" * 55)
    print("  lidc_disagreement_stats — SUMMARY")
    print("=" * 55)
    print(f"  总 cluster 数          : {total_clusters}")
    print(f"  跳过 scan (异常)       : {skipped_scans}")
    print()
    print("  k 分布（k = 标注该 cluster 的医师数）:")
    for k_val in sorted(k_counts.keys()):
        cnt = k_counts[k_val]
        pct = 100.0 * cnt / total_clusters
        print(f"    k={k_val}: {cnt:5d}  ({pct:.1f}%)")
    print()
    print(f"  k=4 全一致             : {n_agree:5d}  ({100*agree_frac:.1f}%)")
    print(f"  k<4 存在分歧           : {n_disagree:5d}  ({100*disagree_frac:.1f}%)")
    print()
    print(f"  Armato2011 参照        : k<4 ~65.2% (tol 不同 cluster 数有出入)")
    print(f"  我们算出 k<4 比例      : {100*disagree_frac:.1f}%")
    print(f"  偏差                   : {100*diff_vs_armato:.1f}pp  → {match_flag}")
    print()
    print(f"  CSV → {OUT_CSV}")
    print("=" * 55)


if __name__ == "__main__":
    main()
