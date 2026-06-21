"""
identity_budget.py — Layer 1 数据集身份预算工具 (gdn2vessel Route 2 lever L4)

**三粒度定义**（全图级，区别于 crowding.py 的局部 R_win 视野 k）：
  1. 连通分量 (cc)：`scipy.ndimage.label(mask)` 的前景连通分量数（背景 label=0 排除）。
     锚点：CHASE_DB1 须落 n ∈ {1, 4}（Stage-1 坐实），偏离即算法 bug。
  2. 分支段 (branch)：`skimage.morphology.skeletonize` → 对每个骨架像素计算 8-邻居
     骨架像素数 → junction = 邻居数 ≥ 3 → 删除 junction 像素 → 剩余骨架
     `scipy.ndimage.label` → 分量数 = 分支段数。纯 scipy+numpy，不用 sknw/skan。
  3. 分叉点 (bifur)：邻居数 ≥ 3 的骨架像素的连通分量数（相邻 junction 像素合为
     一个分叉点再 label 计数）。

预登记判据（写定于 ROUTE2_BUDGET_PREREG.md，禁跑完后调）：
  PASS ⟺  median n ∈ [32, 96]  AND  ≥30% 图 n ≥ 48

统计用 numpy.percentile；禁 scipy.stats（Windows OMP Error #15）。
零 GPU，纯 CPU。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy.ndimage import label as ndlabel
from skimage.morphology import skeletonize

# ─────────────────────────────────────────────────────────────────────────────
#  判据常量（与 PREREG 文件对齐，禁修改）
# ─────────────────────────────────────────────────────────────────────────────
PREREG_MEDIAN_LO: int = 32
PREREG_MEDIAN_HI: int = 96
PREREG_FRAC_GE48: float = 0.30
PREREG_THRESHOLD_48: int = 48
D_HEAD: int = 64  # GDN-2 per-head 状态维（Schlag 2021 正交界）

# ─────────────────────────────────────────────────────────────────────────────
#  数据集路径映射（从 datasets.json 解析 + 本地已确认目录；读不到的集 SKIP）
# ─────────────────────────────────────────────────────────────────────────────
# 各条目 = List[mask_dir_or_glob_pattern]，脚本对每条目聚合所有 .tif/.png/.gif 文件
# 来源注释 → datasets.json vessel_collection_kaggle / vessel_pending
DATASET_MASK_DIRS: Dict[str, List[str]] = {
    # ── 视网膜（vessel_collection_kaggle）──────────────────────────────── #
    "chase": [
        "D:/YJ-Agent/data/vessel/CHASE/masks",         # manual1 only (28 图)
    ],
    "drive": [
        "D:/YJ-Agent/data/vessel/DRIVE/training/1st_manual",  # 20 training GT
        # test GT 缺失（grand-challenge 官方包不含 test GT），仅用 training 20 图
    ],
    "fives": [
        "D:/YJ-Agent/data/vessel/FIVES/masks",         # 800 图
    ],
    "hrf": [
        "D:/YJ-Agent/data/vessel/HRF/masks",           # 45 GT tif（不含 roi_masks）
    ],
    "stare": [
        "D:/YJ-Agent/data/vessel/STARE/masks",         # 20 .ppm.png
    ],
    # ── OCTA（vessel_pending）────────────────────────────────────────── #
    "rose1_svc": [
        "D:/YJ-Agent/data/vessel_octa/ROSE_kaggle/ROSE/ROSE-1/SVC/train/gt",   # 30
        "D:/YJ-Agent/data/vessel_octa/ROSE_kaggle/ROSE/ROSE-1/SVC/test/gt",    # 9
    ],
    "rose1_dvc": [
        "D:/YJ-Agent/data/vessel_octa/ROSE_kaggle/ROSE/ROSE-1/DVC/train/gt",   # 30
        "D:/YJ-Agent/data/vessel_octa/ROSE_kaggle/ROSE/ROSE-1/DVC/test/gt",    # 9
    ],
    "rose2": [
        "D:/YJ-Agent/data/vessel_octa/ROSE_kaggle/ROSE/ROSE-2/train/gt",       # 90
        "D:/YJ-Agent/data/vessel_octa/ROSE_kaggle/ROSE/ROSE-2/test/gt",        # 22
    ],
    # OCTA-500：本地只有 octa500.zip（未解压），运行时 SKIP
    "octa500_3m": [],   # placeholder — zip 未解压，自动 SKIP
    # ── 冠脉（vessel_pending）────────────────────────────────────────── #
    "chuac": [
        "D:/YJ-Agent/data/vessel_coronary/CHUAC/Hemotool",   # 30 PNG GT
    ],
    # DCA1 / XCAD：本地只有 zip，运行时 SKIP
    "dca1": [],     # placeholder — zip 未解压，自动 SKIP
    "xcad": [],     # placeholder — zip 未解压，自动 SKIP
}

# 支持的 mask 文件扩展名（无大小写区分）
_MASK_EXTS: Tuple[str, ...] = (".tif", ".tiff", ".png", ".gif", ".ppm", ".pgm", ".bmp")


# ─────────────────────────────────────────────────────────────────────────────
#  图像加载（二值化）
# ─────────────────────────────────────────────────────────────────────────────

def _load_mask(path: Path) -> Optional[np.ndarray]:
    """
    加载二值血管 mask → bool (H, W)。
    支持 8-bit（像素值 0/255 或 0/1）。
    失败返回 None。
    """
    try:
        from PIL import Image
        img = Image.open(str(path)).convert("L")
        arr = np.array(img, dtype=np.uint8)
        return arr > 0
    except Exception as e:
        print(f"  [WARN] 无法加载 {path}: {e}", file=sys.stderr)
        return None


# ─────────────────────────────────────────────────────────────────────────────
#  核心计数函数（可被 pytest 直接调）
# ─────────────────────────────────────────────────────────────────────────────

def _neighbor_count_kernel(skel: np.ndarray) -> np.ndarray:
    """
    对骨架二值图（bool H×W），返回每个前景像素的 8-邻居中骨架像素数 (int H×W)。
    用 scipy.ndimage.generic_filter（8-邻居求和）实现，避免 import sknw/skan。
    """
    from scipy.ndimage import generic_filter

    skel_int = skel.astype(np.float64)

    def _sum8(values: np.ndarray) -> float:
        # footprint 3×3 共 9 个值，中心自身在 index 4
        return float(values.sum() - values[4])  # 排除中心自身

    neighbor_img = generic_filter(skel_int, _sum8, size=3, mode="constant", cval=0.0)
    # 非骨架像素置 0
    result = np.round(neighbor_img).astype(np.int32)
    result[~skel] = 0
    return result


def count_identities(mask: np.ndarray, granularity: str) -> int:
    """
    对单张二值 mask 计算指定粒度的 distinct 身份数。

    Parameters
    ----------
    mask        : (H, W) bool 或 0/1 ndarray，前景 = 血管
    granularity : "cc" | "branch" | "bifur"

    Returns
    -------
    int ≥ 0
        "cc"     → scipy.ndimage.label 连通分量数（8-连通）
        "branch" → skeletonize → 删 junction（8-邻居≥3）→ 剩余连通分量数
        "bifur"  → junction 像素的连通分量数（相邻 junction 合为一个分叉点）

    Notes
    -----
    - 8-连通结构：np.ones((3,3)) 传入 ndlabel。
    - 空 mask（无前景）→ 返回 0。
    - 单像素骨架无邻居 → 算作 1 分支段（端点孤立像素也保留）。
    """
    mask_b = np.asarray(mask, dtype=bool)
    struct8 = np.ones((3, 3), dtype=np.int32)  # 8-连通

    if not mask_b.any():
        return 0

    if granularity == "cc":
        _, n = ndlabel(mask_b.astype(np.int32), structure=struct8)
        return int(n)

    # 公共步骤：skeletonize
    skel = skeletonize(mask_b)  # bool (H, W)

    if not skel.any():
        return 0

    if granularity == "bifur":
        # junction = 骨架像素 且 8-邻居骨架数 ≥ 3
        nbr = _neighbor_count_kernel(skel)
        junction = skel & (nbr >= 3)
        if not junction.any():
            return 0
        _, n_bifur = ndlabel(junction.astype(np.int32), structure=struct8)
        return int(n_bifur)

    if granularity == "branch":
        # 1. 找 junction pixels（8-邻居骨架数 ≥ 3）
        nbr = _neighbor_count_kernel(skel)
        junction = skel & (nbr >= 3)
        # 2. 删除 junction 像素，保留端点 + 普通链像素
        skel_pruned = skel & ~junction
        if not skel_pruned.any():
            # 极端情况：整个骨架全是 junction（如小正方形），仍算 1 段
            return 1
        _, n_branch = ndlabel(skel_pruned.astype(np.int32), structure=struct8)
        return int(n_branch)

    raise ValueError(f"granularity 须为 'cc'/'branch'/'bifur'，得到: {granularity!r}")


# ─────────────────────────────────────────────────────────────────────────────
#  数据集聚合
# ─────────────────────────────────────────────────────────────────────────────

def _collect_mask_files(dirs: List[str]) -> List[Path]:
    """收集目录列表中的所有 mask 文件（过滤扩展名）。"""
    files: List[Path] = []
    for d in dirs:
        p = Path(d)
        if not p.exists():
            continue
        for f in sorted(p.iterdir()):
            if f.suffix.lower() in _MASK_EXTS:
                files.append(f)
    return files


def _compute_dataset_stats(
    name: str,
    dirs: List[str],
    granularities: List[str],
    n_sample: int,
    rng: np.random.RandomState,
) -> Optional[Dict]:
    """
    计算单个数据集的统计结果。
    返回 None 表示 SKIP（文件不足 / 目录不存在）。
    """
    all_files = _collect_mask_files(dirs)
    if len(all_files) == 0:
        print(f"  [SKIP] {name}: 未找到 mask 文件（目录不存在或 zip 未解压）")
        return None

    if len(all_files) <= n_sample:
        sampled = all_files
    else:
        idx = rng.choice(len(all_files), size=n_sample, replace=False)
        idx.sort()
        sampled = [all_files[i] for i in idx]

    print(f"  [{name}] 共 {len(all_files)} 图，采样 {len(sampled)} 图 ...", flush=True)

    result: Dict = {
        "dataset": name,
        "n_total": len(all_files),
        "n_sampled": len(sampled),
        "granularities": {},
    }

    for gran in granularities:
        counts: List[int] = []
        for fp in sampled:
            mask = _load_mask(fp)
            if mask is None:
                continue
            try:
                c = count_identities(mask, gran)
            except Exception as e:
                print(f"    [ERR] {fp.name} gran={gran}: {e}", file=sys.stderr)
                continue
            counts.append(c)

        if not counts:
            result["granularities"][gran] = {"error": "no valid masks loaded"}
            continue

        arr = np.array(counts, dtype=np.float64)
        median_val = float(np.median(arr))
        mean_val = float(np.mean(arr))
        q25 = float(np.percentile(arr, 25))
        q75 = float(np.percentile(arr, 75))
        min_val = int(np.min(arr))
        max_val = int(np.max(arr))

        # 直方图 bins（0 到 max+1，间距 8）
        bin_max = max(max_val + 1, 128)
        bin_edges = list(range(0, bin_max + 9, 8))
        hist_counts, _ = np.histogram(arr, bins=bin_edges)

        # 判据
        in_target_band = (PREREG_MEDIAN_LO <= median_val <= PREREG_MEDIAN_HI)
        frac_ge48 = float(np.mean(arr >= PREREG_THRESHOLD_48))
        pass_prereg = in_target_band and (frac_ge48 >= PREREG_FRAC_GE48)

        result["granularities"][gran] = {
            "n_valid": len(counts),
            "median": round(median_val, 2),
            "mean": round(mean_val, 2),
            "q25": round(q25, 2),
            "q75": round(q75, 2),
            "min": min_val,
            "max": max_val,
            "histogram": {
                "bin_edges": bin_edges,
                "counts": hist_counts.tolist(),
            },
            "prereg": {
                "median_in_target_band": bool(in_target_band),
                "frac_ge48": round(frac_ge48, 4),
                "pass": bool(pass_prereg),
                "target_band": f"[{PREREG_MEDIAN_LO}, {PREREG_MEDIAN_HI}]",
                "d_head": D_HEAD,
            },
        }

        icon = "PASS" if pass_prereg else "FAIL"
        print(
            f"    {gran:8s}  median={median_val:6.1f}  q25/q75={q25:.1f}/{q75:.1f}"
            f"  n≥48={frac_ge48*100:.1f}%  [{icon}]"
        )

    return result


# ─────────────────────────────────────────────────────────────────────────────
#  Markdown 打印
# ─────────────────────────────────────────────────────────────────────────────

def _print_markdown(results: List[Dict], granularities: List[str]) -> None:
    """打印人读 Markdown 表到 stdout。"""
    print("\n" + "=" * 80)
    print("## Layer 1 身份预算报告（预登记判据：median∈[32,96] AND ≥30%图 n≥48）")
    print(f"## d_head={D_HEAD}（GDN-2 per-head 容量锚点）")
    print("=" * 80)

    gran_headers = "  ".join(f"{g:>8}" for g in granularities)
    sub_headers = "  ".join(f"{'med/q25/q75':>8}" for _ in granularities)  # noqa – decorative
    print(f"\n{'dataset':<16} {'n_total':>8}  " + gran_headers)
    print("-" * 80)

    for r in results:
        ds = r["dataset"]
        nt = r.get("n_total", "?")
        parts = [f"{ds:<16} {str(nt):>8}"]
        for gran in granularities:
            gd = r["granularities"].get(gran, {})
            if "error" in gd:
                parts.append(f"{'ERR':>26}")
            else:
                med = gd.get("median", "?")
                q25 = gd.get("q25", "?")
                q75 = gd.get("q75", "?")
                flag = "[PASS]" if gd.get("prereg", {}).get("pass") else "[FAIL]"
                parts.append(f"  med={med:.1f} q=[{q25:.0f},{q75:.0f}] {flag}")
        print("  ".join(parts))

    print("\n详见 outputs/route2_budget/identity_budget.json")


# ─────────────────────────────────────────────────────────────────────────────
#  CLI 入口
# ─────────────────────────────────────────────────────────────────────────────

def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="Layer 1 数据集身份预算工具 — 每图 distinct 身份数分布 vs d=64"
    )
    parser.add_argument(
        "--datasets",
        nargs="+",
        default=None,
        help="要处理的数据集名列表（默认跑全部能找到的）。"
             f"可选: {sorted(DATASET_MASK_DIRS.keys())}",
    )
    parser.add_argument(
        "--granularities",
        nargs="+",
        default=["cc", "branch", "bifur"],
        choices=["cc", "branch", "bifur"],
        help="要计算的粒度（默认三种都跑）",
    )
    parser.add_argument(
        "--n_sample",
        type=int,
        default=10,
        help="每集最多采样图数（默认 10；有则随机 RandomState(42) 采样）",
    )
    parser.add_argument(
        "--out",
        default="outputs/route2_budget/identity_budget.json",
        help="输出 JSON 路径（默认 outputs/route2_budget/identity_budget.json）",
    )
    args = parser.parse_args(argv)

    # 确定要跑的数据集
    if args.datasets is None:
        target_datasets = sorted(DATASET_MASK_DIRS.keys())
    else:
        unknown = set(args.datasets) - set(DATASET_MASK_DIRS.keys())
        if unknown:
            print(f"[WARN] 未知数据集名: {unknown}，已忽略", file=sys.stderr)
        target_datasets = [d for d in args.datasets if d in DATASET_MASK_DIRS]

    rng = np.random.RandomState(42)

    all_results: List[Dict] = []
    print(f"\n[identity_budget] 开始计算 {len(target_datasets)} 个数据集，"
          f"粒度={args.granularities}，n_sample={args.n_sample}\n")

    for ds_name in target_datasets:
        dirs = DATASET_MASK_DIRS[ds_name]
        if not dirs:
            print(f"  [SKIP] {ds_name}: 无路径配置（zip 未解压或 placeholder）")
            continue
        print(f"[{ds_name}]")
        r = _compute_dataset_stats(
            ds_name,
            dirs,
            args.granularities,
            args.n_sample,
            rng,
        )
        if r is not None:
            all_results.append(r)
        print()

    # 保存 JSON
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "identity_budget_v1",
        "prereg_ref": "reference/ROUTE2_BUDGET_PREREG.md",
        "d_head": D_HEAD,
        "n_sample": args.n_sample,
        "granularities": args.granularities,
        "results": all_results,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"[identity_budget] JSON 保存 → {out_path}")

    # Markdown 表
    if all_results:
        _print_markdown(all_results, args.granularities)


if __name__ == "__main__":
    main()
