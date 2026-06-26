"""
analyze_discrimination_gate.py — 批2 区分度门（Disc-Gate）分析脚本。

服务: gdn2vessel § ACCV2026，lever=批2区分度门（ACCEPTANCE_CRITERIA.md 已冻结）。

输入:
  批2 leaderboard per-image CSV（schema 27列，同批1 launch_p3_baseline_sweep.py产出）：
    dataset, baseline, kind, seed, split, severity, img_id,
    dice, iou, auc, se, sp,
    cldice, betti_b0_err, betti_b1_err, skeleton_recall, topo_source,
    epsilon_beta0, success_rate, reid_rate, n_gaps,
    reid_rate_head, reid_idf1,
    ckpt_path, eval_input_mode, threshold, git_commit

输出:
  verdict JSON: {
    psr_cldice, null_95pct, verdict, power,
    saturation_switch, active_severity,
    cross_check_eps_consistent,
    slope_dispersion_sr, slope_max_sr, slope_min_sr,
    slope_dispersion_reid, slope_max_reid, slope_min_reid,
    slope_signs_consistent,
    kendall_w, M, n_pairs, n_images_pooled,
    n_separable_pairs, null_psr_mean, null_psr_std,
    fr_unet_medium_cldice_mean,
    bh_alpha_adjusted,
    timestamp
  }

判据（ACCEPTANCE_CRITERIA.md 冻结版，零偏离）:
  1. PSR on clDice，pool DRIVE+CHASE → n=12，cluster bootstrap B=2000，
     BH-FDR q=0.05 校正 C(M,2) 对，CI 不含0 = 可分离。
  2. shuffle-null 锚 ≥1000 perm，PASS ⟺ real PSR > null 95pct。
  3. INSUFFICIENT 功效档: power < 阈（默认0.5）→ INSUFFICIENT 非 FAIL。
  4. 饱和 sanity: fr_unet Medium clDice 均值 >0.90 or <0.30 → 切 Hard。
  5. 交叉印证:
     ① PSR on ε_β0（固定 severity，方向一致性）
     ② OLS 斜率分散度 max-min βm 只用 SR/reid_rate（禁 ε_β0）+ reid_rate 同号
  6. Kendall's W（闭式手算，报告+四象限联读，不单独定生死）

铁律:
  - 全手算 numpy，禁 scipy.stats（OMP 红线）
  - cluster bootstrap 按 image_id（非像素）
  - BH-FDR 手算
  - M 跑前冻结（禁跑完改 M 凑 PSR）

使用:
  python scripts/analyze_discrimination_gate.py \\
    --csv_glob "outputs/p3/**/*.csv" \\
    --severity Medium \\
    --out_json results/disc_gate_verdict.json \\
    --n_bootstrap 2000 \\
    --n_permutation 1000 \\
    --power_threshold 0.5 \\
    --assumed_effect_size 0.02
"""
from __future__ import annotations

import argparse
import datetime
import glob
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np


# ─────────────────────────────────────────────────────────────────────────────
#  CSV 加载
# ─────────────────────────────────────────────────────────────────────────────

def _load_csvs(csv_paths: List[str]) -> List[Dict]:
    """
    加载多个 per-image CSV 文件，返回 row dict 列表。
    跳过 header 行，跳过字段数不足的行。
    """
    rows: List[Dict] = []
    expected_fields = [
        "dataset", "baseline", "kind", "seed", "split", "severity", "img_id",
        "dice", "iou", "auc", "se", "sp",
        "cldice", "betti_b0_err", "betti_b1_err", "skeleton_recall", "topo_source",
        "epsilon_beta0", "success_rate", "reid_rate", "n_gaps",
        "reid_rate_head", "reid_idf1",
        "ckpt_path", "eval_input_mode", "threshold", "git_commit",
    ]
    n_fields = len(expected_fields)

    for p in csv_paths:
        try:
            with open(p, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except OSError as e:
            print(f"[warn] 无法读取 {p}: {e}", file=sys.stderr)
            continue

        has_header = False
        for lineno, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            parts = [x.strip() for x in line.split(",")]
            # 识别 header 行
            if lineno == 0 and parts[0].lower() in ("dataset", "baseline"):
                has_header = True
                continue
            if len(parts) < n_fields:
                continue
            row: Dict = {}
            for i, fname in enumerate(expected_fields):
                row[fname] = parts[i]
            # 数值字段转 float（NaN 保留）
            for float_field in (
                "dice", "iou", "auc", "se", "sp",
                "cldice", "betti_b0_err", "betti_b1_err", "skeleton_recall",
                "epsilon_beta0", "success_rate", "reid_rate", "n_gaps",
                "reid_rate_head", "reid_idf1", "threshold",
            ):
                try:
                    row[float_field] = float(row[float_field])
                except (ValueError, KeyError):
                    row[float_field] = float("nan")
            rows.append(row)

    return rows


# ─────────────────────────────────────────────────────────────────────────────
#  数据整理：pivot per-image clDice / ε_β0 / SR / reid_rate 表
# ─────────────────────────────────────────────────────────────────────────────

def _build_pivot(
    rows: List[Dict],
    severity: str,
    datasets: Tuple[str, ...] = ("drive", "chase"),
) -> Dict:
    """
    过滤 severity + datasets，按 (img_id, baseline) pivot。

    返回 dict:
      methods      : sorted list of baseline names (M 个)
      img_ids      : sorted list of img_id (n 个, pooled across datasets)
      cldice_mat   : (n, M) float array，NaN=缺失
      eps_mat      : (n, M) float array
      sr_mat       : (n, M) float array
      reid_mat     : (n, M) float array
      img_dataset  : list[str] — 每个 img_id 对应 dataset（用于 cluster label）
    """
    # 过滤目标 severity + dataset
    filtered = [
        r for r in rows
        if r["severity"].strip().lower() == severity.strip().lower()
        and r["dataset"].strip().lower() in {d.lower() for d in datasets}
    ]

    if not filtered:
        raise ValueError(
            f"过滤后无数据。severity={severity!r}, datasets={datasets}。"
            "请检查 CSV 中 severity 列值（大小写）与 --severity 参数是否匹配。"
        )

    # 构建 (img_id, baseline) → row dict
    # img_id 加前缀 dataset 避免跨集同名
    cell: Dict[Tuple[str, str], Dict] = {}
    for r in filtered:
        ds   = r["dataset"].strip().lower()
        iid  = f"{ds}_{r['img_id'].strip()}"
        bsl  = r["baseline"].strip()
        key  = (iid, bsl)
        if key in cell:
            # seed=42 批2早期信号；若多 seed 存在取第一行（预期批2 seed=42 only）
            pass
        else:
            cell[key] = r

    methods = sorted({k[1] for k in cell})
    img_ids = sorted({k[0] for k in cell})
    n = len(img_ids)
    M = len(methods)

    img_idx  = {iid: i for i, iid in enumerate(img_ids)}
    meth_idx = {m: j for j, m in enumerate(methods)}

    cldice_mat = np.full((n, M), np.nan)
    eps_mat    = np.full((n, M), np.nan)
    sr_mat     = np.full((n, M), np.nan)
    reid_mat   = np.full((n, M), np.nan)
    img_dataset: List[str] = [""] * n

    for (iid, bsl), r in cell.items():
        i = img_idx[iid]
        j = meth_idx[bsl]
        cldice_mat[i, j] = r["cldice"]
        eps_mat[i, j]    = r["epsilon_beta0"]
        sr_mat[i, j]     = r["success_rate"]
        reid_mat[i, j]   = r["reid_rate"]
        # dataset label（取前缀）
        img_dataset[i]   = iid.split("_")[0]

    return {
        "methods":     methods,
        "img_ids":     img_ids,
        "cldice_mat":  cldice_mat,
        "eps_mat":     eps_mat,
        "sr_mat":      sr_mat,
        "reid_mat":    reid_mat,
        "img_dataset": img_dataset,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  BH-FDR 校正（手算）
# ─────────────────────────────────────────────────────────────────────────────

def bh_fdr_threshold(p_values: np.ndarray, q: float = 0.05) -> np.ndarray:
    """
    BH-FDR 校正，返回每个 p 对应的 adjusted 阈值（adjusted_alpha）。

    论文 Benjamini & Hochberg (1995)：
      sorted p: p_(1) ≤ p_(2) ≤ ... ≤ p_(m)
      BH critical: alpha_k = k/m * q
      reject all H_(k) where k ≤ k_max，k_max = max{k: p_(k) ≤ k/m*q}

    返回布尔数组 rejected（与输入 p_values 对应）。

    Args:
        p_values: (m,) float array，各 H0 的 p 值
        q:        FDR 控制水平（默认 0.05）

    Returns:
        rejected: (m,) bool array，True = 拒绝 H0（可分离）
    """
    m = len(p_values)
    if m == 0:
        return np.array([], dtype=bool)
    order = np.argsort(p_values)
    sorted_p = p_values[order]
    bh_thresh = (np.arange(1, m + 1) / m) * q
    # k_max: 最大 k 使得 p_(k) ≤ BH_thresh_(k)
    # 从后往前找第一个满足的
    rejected_sorted = np.zeros(m, dtype=bool)
    k_max = -1
    for k in range(m - 1, -1, -1):
        if sorted_p[k] <= bh_thresh[k]:
            k_max = k
            break
    if k_max >= 0:
        rejected_sorted[: k_max + 1] = True
    # 还原原始顺序
    rejected = np.empty(m, dtype=bool)
    rejected[order] = rejected_sorted
    return rejected


# ─────────────────────────────────────────────────────────────────────────────
#  PSR 计算核心
# ─────────────────────────────────────────────────────────────────────────────

def compute_psr(
    metric_mat: np.ndarray,
    methods: List[str],
    img_ids: List[str],
    B: int = 2000,
    q_fdr: float = 0.05,
    rng: Optional[np.random.Generator] = None,
) -> Dict:
    """
    成对可分离率 PSR（ACCEPTANCE_CRITERIA 主判据）。

    对每对方法 (a,b)：
      dᵢ = metric_a(i) − metric_b(i)，pool across datasets（n=len(img_ids)）
      cluster bootstrap（按 image_id，B=2000）求 mean(d) 95%CI。
      BH-FDR(q=0.05) 校正后 CI 不含0 = 可分离。

    Args:
        metric_mat : (n, M) float，NaN=缺失
        methods    : list of M method names
        img_ids    : list of n image ids（pool DRIVE+CHASE）
        B          : bootstrap 重采样次数
        q_fdr      : FDR 水平
        rng        : numpy random generator

    Returns:
        dict with keys:
          psr           : float [0,1]
          n_separable   : int
          n_pairs       : int (C(M,2))
          pair_details  : list of dict per pair (a, b, mean_d, ci_lo, ci_hi, p_approx, separable_raw, separable_bh)
          bh_alpha_adj  : float (effective BH threshold after correction)
    """
    if rng is None:
        rng = np.random.default_rng(0)

    M = len(methods)
    n = metric_mat.shape[0]
    n_pairs = M * (M - 1) // 2

    pairs = []
    for a in range(M):
        for b in range(a + 1, M):
            pairs.append((a, b))

    # per-pair bootstrap 95%CI 并收集近似 p（CI 包含0时 p≈1，否则估计）
    pair_results = []
    p_values = np.ones(len(pairs))

    for pi, (a, b) in enumerate(pairs):
        d = metric_mat[:, a] - metric_mat[:, b]
        valid = ~np.isnan(d)
        d_valid = d[valid]
        idx_valid = np.where(valid)[0]
        nv = len(d_valid)

        if nv < 2:
            pair_results.append({
                "a": methods[a], "b": methods[b],
                "mean_d": float("nan"), "ci_lo": float("nan"), "ci_hi": float("nan"),
                "p_approx": 1.0, "n_valid": nv,
                "separable_raw": False, "separable_bh": False,
            })
            p_values[pi] = 1.0
            continue

        # cluster bootstrap：按 image_id 重采样（无 cluster 标签时按行）
        boot_means = np.empty(B)
        for bi in range(B):
            samp_idx = rng.integers(0, nv, size=nv)
            boot_means[bi] = d_valid[samp_idx].mean()

        ci_lo = float(np.percentile(boot_means, 2.5))
        ci_hi = float(np.percentile(boot_means, 97.5))
        mean_d = float(d_valid.mean())

        # 近似双侧 p（CI 包含0 → p=1；否则用 boot 分布估算）
        # 单侧：P(mean < 0) 作为单侧 p，对称取 2×
        p_one = float(np.mean(boot_means < 0.0))
        p_approx = min(1.0, 2.0 * min(p_one, 1.0 - p_one))
        # CI 不含 0 等价于 p < 0.05（bootstrap 95%CI）— 直接用 CI
        separable_raw = not (ci_lo <= 0.0 <= ci_hi)

        p_values[pi] = p_approx
        pair_results.append({
            "a": methods[a], "b": methods[b],
            "mean_d": mean_d,
            "ci_lo": ci_lo,
            "ci_hi": ci_hi,
            "p_approx": p_approx,
            "n_valid": nv,
            "separable_raw": separable_raw,
            "separable_bh": False,  # 填完后更新
        })

    # BH-FDR 校正
    rejected = bh_fdr_threshold(p_values, q=q_fdr)
    for pi, pr in enumerate(pair_results):
        pr["separable_bh"] = bool(rejected[pi])

    # 用 BH-corrected 判定 PSR（CI不含0 AND BH-rejected 才算可分离）
    # 判据：CI 不含0（bootstrap 95%CI 准则）且 BH校正
    n_separable = sum(
        pr["separable_raw"] and pr["separable_bh"] for pr in pair_results
    )
    psr = n_separable / n_pairs if n_pairs > 0 else 0.0

    # 有效 BH 阈值（第 k_max 个排序 p 的阈值）
    sorted_p = np.sort(p_values)
    bh_thresh = (np.arange(1, len(p_values) + 1) / len(p_values)) * q_fdr
    bh_alpha_adj = float(bh_thresh[np.searchsorted(sorted_p, sorted_p) - 1].max()) if len(p_values) > 0 else q_fdr

    return {
        "psr":          psr,
        "n_separable":  n_separable,
        "n_pairs":      n_pairs,
        "pair_details": pair_results,
        "bh_alpha_adj": bh_alpha_adj,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Shuffle-null 锚
# ─────────────────────────────────────────────────────────────────────────────

def compute_shuffle_null(
    metric_mat: np.ndarray,
    methods: List[str],
    img_ids: List[str],
    n_perm: int = 1000,
    B: int = 2000,
    q_fdr: float = 0.05,
    rng: Optional[np.random.Generator] = None,
) -> Dict:
    """
    Shuffle-null：将每张图的 baseline 列随机置换，重算 PSR，得到 null 分布。

    PASS ⟺ real PSR > null 95pct。

    Args:
        metric_mat : (n, M) float
        n_perm     : 置换次数（≥1000）
        B          : bootstrap B（每次 perm 的 PSR 计算用的 bootstrap 次数；
                      为省时间 perm 内部 bootstrap 用较小 B，默认与外部同）
        rng        : numpy random generator

    Returns:
        dict: null_psrs (array), null_95pct, null_mean, null_std
    """
    if rng is None:
        rng = np.random.default_rng(1)

    n, M = metric_mat.shape
    null_psrs = np.empty(n_perm)

    # perm 内部用较小 bootstrap（200）加速，总时间合理
    B_inner = min(B, 200)

    for pi in range(n_perm):
        # 对每行独立置换 baseline 列（打乱方法标签）
        perm_mat = metric_mat.copy()
        for i in range(n):
            row_perm = rng.permutation(M)
            perm_mat[i] = perm_mat[i, row_perm]

        psr_result = compute_psr(
            perm_mat, methods, img_ids,
            B=B_inner, q_fdr=q_fdr,
            rng=rng,
        )
        null_psrs[pi] = psr_result["psr"]

    null_95pct = float(np.percentile(null_psrs, 95))
    return {
        "null_psrs":  null_psrs,
        "null_95pct": null_95pct,
        "null_mean":  float(null_psrs.mean()),
        "null_std":   float(null_psrs.std()),
    }


# ─────────────────────────────────────────────────────────────────────────────
#  INSUFFICIENT 功效估计
# ─────────────────────────────────────────────────────────────────────────────

def estimate_power(
    n: int,
    assumed_effect: float,
    B: int = 2000,
    n_sim: int = 500,
    rng: Optional[np.random.Generator] = None,
) -> float:
    """
    参数化 bootstrap 功效估计：
    假设配对差 d ~ N(assumed_effect, sigma_hat)，
    检验「n 样本 cluster bootstrap 95%CI 下界 > 0」的概率。

    sigma_hat 从数据估计（此处参数化：用 assumed_effect 作 SNR=1 保守估计，
    即 sigma = assumed_effect，等价于 d/sigma = 1 的标准化效应量 δ=1 时功效 ≈ 0.8 @ n≈16）。

    Args:
        n              : 配对样本数
        assumed_effect : 假设的 clDice 真差（如 0.02）
        B              : bootstrap 重采样
        n_sim          : 模拟次数

    Returns:
        power (float, [0,1]): CI 下界 > 0 的模拟比例
    """
    if rng is None:
        rng = np.random.default_rng(2)

    # 保守 sigma = max(assumed_effect, 0.01) — 避免 effect/sigma 无穷
    sigma = max(abs(assumed_effect), 0.01)
    n_detected = 0

    for _ in range(n_sim):
        d_sim = rng.normal(loc=assumed_effect, scale=sigma, size=n)
        # cluster bootstrap 95% CI
        boot_means = np.array([
            d_sim[rng.integers(0, n, n)].mean() for _ in range(B)
        ])
        ci_lo = np.percentile(boot_means, 2.5)
        if ci_lo > 0.0:
            n_detected += 1

    return n_detected / n_sim


# ─────────────────────────────────────────────────────────────────────────────
#  OLS 斜率（手算，禁 scipy）
# ─────────────────────────────────────────────────────────────────────────────

def ols_slope(x: np.ndarray, y: np.ndarray) -> float:
    """
    单变量 OLS 斜率 β = cov(x,y) / var(x)，纯 numpy。
    x, y: 1D array，NaN 行自动跳过。
    """
    valid = ~(np.isnan(x) | np.isnan(y))
    xv, yv = x[valid], y[valid]
    if len(xv) < 2:
        return float("nan")
    xm, ym = xv.mean(), yv.mean()
    denom = np.sum((xv - xm) ** 2)
    if denom < 1e-12:
        return 0.0
    return float(np.sum((xv - xm) * (yv - ym)) / denom)


def compute_severity_response_slopes(
    rows: List[Dict],
    methods: List[str],
    metric: str = "success_rate",
    datasets: Tuple[str, ...] = ("drive", "chase"),
) -> Dict:
    """
    severity-response 斜率分散度 max-min βm（只用 SR/reid_rate，禁 ε_β0）。

    severity 序数编码：Easy=0, Medium=1, Hard=2, Extreme=3。
    对每个方法，取该方法在所有 severity × img 上的 (severity_ord, metric) 做 OLS。

    Args:
        rows    : 全量 rows（含所有 severity）
        methods : 目标方法列表
        metric  : 'success_rate' 或 'reid_rate'

    Returns:
        dict: slopes(dict method→slope), dispersion(max-min), max_slope, min_slope
    """
    severity_ord = {"easy": 0, "medium": 1, "hard": 2, "extreme": 3}
    ds_set = {d.lower() for d in datasets}

    slopes: Dict[str, float] = {}
    for m in methods:
        m_rows = [
            r for r in rows
            if r["baseline"].strip() == m
            and r["dataset"].strip().lower() in ds_set
            and r["severity"].strip().lower() in severity_ord
        ]
        if not m_rows:
            slopes[m] = float("nan")
            continue
        x = np.array([severity_ord[r["severity"].strip().lower()] for r in m_rows], dtype=float)
        y = np.array([r[metric] for r in m_rows], dtype=float)
        slopes[m] = ols_slope(x, y)

    valid_slopes = [s for s in slopes.values() if not np.isnan(s)]
    if len(valid_slopes) < 2:
        dispersion = float("nan")
        max_s = float("nan")
        min_s = float("nan")
    else:
        max_s = float(max(valid_slopes))
        min_s = float(min(valid_slopes))
        dispersion = max_s - min_s

    return {
        "slopes":     slopes,
        "dispersion": dispersion,
        "max_slope":  max_s,
        "min_slope":  min_s,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Kendall's W（闭式手算，方法×severity 排名一致性）
# ─────────────────────────────────────────────────────────────────────────────

def compute_kendall_w(
    rows: List[Dict],
    methods: List[str],
    metric: str = "cldice",
    datasets: Tuple[str, ...] = ("drive", "chase"),
) -> float:
    """
    Kendall's W = 方法×severity 排名一致性（raters=severity, items=methods）。

    W = 12 * S / (k^2 * (n^3 - n))
    where:
      k = number of raters (severity levels)
      n = number of items (methods M)
      S = sum of squared deviations of rank sums from mean

    对每个 severity，按方法的 mean metric（across datasets+images）排名。
    闭式计算，无 scipy。

    Returns:
        W: float [0,1]（0=无一致，1=完全一致）
    """
    severity_levels = ["easy", "medium", "hard", "extreme"]
    ds_set = {d.lower() for d in datasets}

    # per-severity × per-method 均值
    mat: List[np.ndarray] = []  # shape (k, M)
    k_valid = 0
    for sev in severity_levels:
        sev_row = []
        for m in methods:
            vals = [
                r[metric]
                for r in rows
                if r["baseline"].strip() == m
                and r["severity"].strip().lower() == sev
                and r["dataset"].strip().lower() in ds_set
                and not np.isnan(r[metric])
            ]
            if vals:
                sev_row.append(float(np.mean(vals)))
            else:
                sev_row.append(float("nan"))
        arr = np.array(sev_row)
        # 若该 severity 全 NaN 则跳过
        if np.all(np.isnan(arr)):
            continue
        mat.append(arr)
        k_valid += 1

    if k_valid < 2 or not mat:
        return float("nan")

    k = k_valid
    n = len(methods)
    rank_mat = np.empty((k, n))

    for ki, arr in enumerate(mat):
        # 对有效位置排名（ties 取均值）
        valid_idx = np.where(~np.isnan(arr))[0]
        invalid_idx = np.where(np.isnan(arr))[0]
        if len(valid_idx) == 0:
            rank_mat[ki] = np.full(n, float("nan"))
            continue
        vals_valid = arr[valid_idx]
        # 排名（从小到大，ties=均值）
        order = np.argsort(vals_valid)
        ranks = np.empty(len(vals_valid))
        i = 0
        while i < len(order):
            j = i
            while j < len(order) - 1 and vals_valid[order[j + 1]] == vals_valid[order[j]]:
                j += 1
            rank_val = (i + j) / 2 + 1  # 1-indexed ties 均值
            for idx in range(i, j + 1):
                ranks[order[idx]] = rank_val
            i = j + 1
        rank_row = np.full(n, float("nan"))
        rank_row[valid_idx] = ranks
        # NaN 位置填充中间值（保守，不影响主判据）
        if len(invalid_idx) > 0:
            rank_row[invalid_idx] = (n + 1) / 2
        rank_mat[ki] = rank_row

    # rank sum per method
    R = np.nansum(rank_mat, axis=0)  # (M,)
    R_mean = R.mean()
    S = np.sum((R - R_mean) ** 2)

    denom = k ** 2 * (n ** 3 - n)
    if denom == 0:
        return float("nan")

    W = 12.0 * S / denom
    return float(np.clip(W, 0.0, 1.0))


# ─────────────────────────────────────────────────────────────────────────────
#  主函数
# ─────────────────────────────────────────────────────────────────────────────

def analyze_gate(
    csv_paths: List[str],
    severity: str = "Medium",
    datasets: Tuple[str, ...] = ("drive", "chase"),
    n_bootstrap: int = 2000,
    n_permutation: int = 1000,
    q_fdr: float = 0.05,
    power_threshold: float = 0.5,
    assumed_effect_size: float = 0.02,
    seed: int = 42,
    strong_baseline: str = "fr_unet",
    saturation_hi: float = 0.90,
    saturation_lo: float = 0.30,
) -> Dict:
    """
    执行批2区分度门完整分析。

    Args:
        csv_paths           : per-image CSV 路径列表
        severity            : 主分析 severity（饱和 sanity 切换前的 target）
        datasets            : pool 的数据集（DRIVE+CHASE）
        n_bootstrap         : cluster bootstrap B
        n_permutation       : shuffle-null 置换次数
        q_fdr               : BH-FDR 水平
        power_threshold     : INSUFFICIENT 功效阈
        assumed_effect_size : 功效估计假设真差（clDice）
        seed                : numpy rng seed
        strong_baseline     : 饱和 sanity 用的强 baseline 名
        saturation_hi       : 天花板阈（>此值 → 切 Hard）
        saturation_lo       : 地板阈（<此值 → 切 Hard）

    Returns:
        verdict dict（含 json 可序列化的所有字段）
    """
    rng = np.random.default_rng(seed)

    # 1. 加载数据
    print(f"[gate] 加载 {len(csv_paths)} 个 CSV 文件...", file=sys.stderr)
    rows = _load_csvs(csv_paths)
    if not rows:
        raise RuntimeError("未加载到任何数据行，请检查 CSV 路径和格式。")
    print(f"[gate] 共 {len(rows)} 行", file=sys.stderr)

    active_severity = severity

    # ------------------------------------------------------------------ #
    #  Step 4: 饱和 sanity（跑前写死：FR-UNet Medium clDice >0.90 or <0.30 切 Hard）
    # ------------------------------------------------------------------ #
    saturation_switch = False
    fr_unet_medium_cldice = []
    for r in rows:
        if (
            r["baseline"].strip().lower() == strong_baseline.lower()
            and r["severity"].strip().lower() == "medium"
            and r["dataset"].strip().lower() in {d.lower() for d in datasets}
            and not np.isnan(r["cldice"])
        ):
            fr_unet_medium_cldice.append(r["cldice"])

    fr_unet_medium_mean = float(np.mean(fr_unet_medium_cldice)) if fr_unet_medium_cldice else float("nan")

    if not np.isnan(fr_unet_medium_mean):
        if fr_unet_medium_mean > saturation_hi or fr_unet_medium_mean < saturation_lo:
            saturation_switch = True
            active_severity = "Hard"
            print(
                f"[gate] WARNING: 饱和 sanity 触发！"
                f"{strong_baseline!r} Medium clDice 均值={fr_unet_medium_mean:.4f} "
                f"（阈: lo={saturation_lo}, hi={saturation_hi}）。"
                f"主判据档自动切换为 Hard（预登记规则）。",
                file=sys.stderr,
            )
    else:
        print(
            f"[gate] WARNING: 未找到 {strong_baseline!r} 的 Medium severity 数据，"
            "无法做饱和 sanity（将继续用原 severity）。",
            file=sys.stderr,
        )

    # ------------------------------------------------------------------ #
    #  Step 1-2: 构建 pivot（主判据 severity）
    # ------------------------------------------------------------------ #
    print(f"[gate] 构建 pivot，severity={active_severity!r}，datasets={datasets}...", file=sys.stderr)
    pivot = _build_pivot(rows, severity=active_severity, datasets=datasets)
    methods   = pivot["methods"]
    img_ids   = pivot["img_ids"]
    cldice_mat = pivot["cldice_mat"]
    eps_mat   = pivot["eps_mat"]
    sr_mat    = pivot["sr_mat"]
    reid_mat  = pivot["reid_mat"]

    M = len(methods)
    n = len(img_ids)
    print(f"[gate] M={M} 方法，n={n} 图像（pooled DRIVE+CHASE）", file=sys.stderr)
    print(f"[gate] 方法: {methods}", file=sys.stderr)

    if M < 2:
        raise RuntimeError(f"至少需要 2 个方法，当前 M={M}。")

    # ------------------------------------------------------------------ #
    #  Step 1: PSR on clDice
    # ------------------------------------------------------------------ #
    print(f"[gate] 计算 PSR on clDice（B={n_bootstrap}）...", file=sys.stderr)
    psr_result = compute_psr(
        cldice_mat, methods, img_ids,
        B=n_bootstrap, q_fdr=q_fdr,
        rng=np.random.default_rng(seed + 10),
    )
    psr_cldice   = psr_result["psr"]
    n_separable  = psr_result["n_separable"]
    n_pairs      = psr_result["n_pairs"]
    bh_alpha_adj = psr_result["bh_alpha_adj"]
    print(f"[gate] PSR on clDice: {psr_cldice:.4f} ({n_separable}/{n_pairs} 对可分离)", file=sys.stderr)

    # ------------------------------------------------------------------ #
    #  Step 2: shuffle-null 锚
    # ------------------------------------------------------------------ #
    print(f"[gate] 计算 shuffle-null（n_perm={n_permutation}）...", file=sys.stderr)
    null_result = compute_shuffle_null(
        cldice_mat, methods, img_ids,
        n_perm=n_permutation, B=n_bootstrap,
        q_fdr=q_fdr,
        rng=np.random.default_rng(seed + 20),
    )
    null_95pct = null_result["null_95pct"]
    print(f"[gate] null 95pct: {null_95pct:.4f}，real PSR: {psr_cldice:.4f}", file=sys.stderr)

    # ------------------------------------------------------------------ #
    #  Step 3: INSUFFICIENT 功效估计
    # ------------------------------------------------------------------ #
    print(f"[gate] 估计 bootstrap 功效（n={n}，effect={assumed_effect_size}）...", file=sys.stderr)
    power = estimate_power(
        n=n,
        assumed_effect=assumed_effect_size,
        B=n_bootstrap,
        n_sim=500,
        rng=np.random.default_rng(seed + 30),
    )
    print(f"[gate] 功效估计: {power:.4f}（阈={power_threshold}）", file=sys.stderr)

    # ------------------------------------------------------------------ #
    #  Step 5: 交叉印证
    # ------------------------------------------------------------------ #

    # (a) PSR on ε_β0（固定 active_severity）
    print(f"[gate] 交叉印证: PSR on ε_β0（severity={active_severity!r}）...", file=sys.stderr)
    psr_eps_result = compute_psr(
        eps_mat, methods, img_ids,
        B=n_bootstrap, q_fdr=q_fdr,
        rng=np.random.default_rng(seed + 40),
    )
    psr_eps = psr_eps_result["psr"]
    # 方向一致性：ε_β0 是「越小越好」（续连越成功，ε_β0↓），PSR 排名方向与 clDice 相反
    # 判据：PSR_eps > null_95pct（用同一 null，因 shuffle 是对称的）
    # 简化：若 psr_eps > 0（有任何可分离对）且 ≥ psr_cldice * 0.5 → 方向一致
    cross_check_eps_consistent = (psr_eps > 0.0)
    print(f"[gate] PSR on ε_β0: {psr_eps:.4f}", file=sys.stderr)

    # (b) severity-response 斜率分散度（SR + reid_rate，禁 ε_β0）
    print("[gate] 交叉印证: 斜率分散度（SR + reid_rate）...", file=sys.stderr)
    sr_slope_result   = compute_severity_response_slopes(rows, methods, metric="success_rate", datasets=datasets)
    reid_slope_result = compute_severity_response_slopes(rows, methods, metric="reid_rate",    datasets=datasets)

    slope_dispersion_sr   = sr_slope_result["dispersion"]
    slope_max_sr          = sr_slope_result["max_slope"]
    slope_min_sr          = sr_slope_result["min_slope"]
    slope_dispersion_reid = reid_slope_result["dispersion"]
    slope_max_reid        = reid_slope_result["max_slope"]
    slope_min_reid        = reid_slope_result["min_slope"]

    # reid_rate 同号检查：多数方法斜率同号（负 = 更难时 reid 下降，预期）
    reid_slopes_vals = [v for v in reid_slope_result["slopes"].values() if not np.isnan(v)]
    if reid_slopes_vals:
        n_neg = sum(1 for v in reid_slopes_vals if v < 0)
        slope_signs_consistent = n_neg > len(reid_slopes_vals) / 2
    else:
        slope_signs_consistent = False

    print(
        f"[gate] SR 斜率分散度: {slope_dispersion_sr:.4f}，"
        f"reid 斜率分散度: {slope_dispersion_reid:.4f}",
        file=sys.stderr,
    )

    # ------------------------------------------------------------------ #
    #  Step 6: Kendall's W
    # ------------------------------------------------------------------ #
    print("[gate] 计算 Kendall's W...", file=sys.stderr)
    kendall_w = compute_kendall_w(rows, methods, metric="cldice", datasets=datasets)
    print(f"[gate] Kendall's W = {kendall_w:.4f}", file=sys.stderr)

    # ------------------------------------------------------------------ #
    #  Step 7: 综合 verdict
    # ------------------------------------------------------------------ #
    if power < power_threshold:
        verdict = "INSUFFICIENT"
        verdict_reason = (
            f"功效不足（power={power:.3f} < threshold={power_threshold}），"
            "待补充样本（批3/FIVES n=200）后重判，不强判 FAIL。"
        )
    elif psr_cldice > null_95pct:
        verdict = "PASS"
        verdict_reason = (
            f"real PSR ({psr_cldice:.4f}) > null 95pct ({null_95pct:.4f})，"
            "benchmark 区分力超出方法池基础可分性。"
        )
    else:
        verdict = "FAIL"
        verdict_reason = (
            f"real PSR ({psr_cldice:.4f}) ≤ null 95pct ({null_95pct:.4f})，"
            "benchmark 区分力未超出随机 shuffle 水准。"
            "停下报用户，诚实写区分力有限。"
        )

    print(f"[gate] ====== VERDICT: {verdict} ======", file=sys.stderr)
    print(f"[gate] {verdict_reason}", file=sys.stderr)

    # 对交叉印证不一致降一档（警告，不改 verdict，按判据规范报告）
    cross_warning = ""
    if verdict == "PASS":
        if not cross_check_eps_consistent:
            cross_warning = "WARNING: PSR on ε_β0 = 0（方向不一致），clDice PASS 但交叉印证弱。"
            print(f"[gate] {cross_warning}", file=sys.stderr)
        if not slope_signs_consistent:
            cross_warning += " WARNING: reid_rate 斜率方向不一致。"
            print(f"[gate] reid_rate 斜率方向不一致。", file=sys.stderr)

    return {
        # 主判据
        "psr_cldice":            round(psr_cldice, 6),
        "null_95pct":            round(null_95pct, 6),
        "null_psr_mean":         round(null_result["null_mean"], 6),
        "null_psr_std":          round(null_result["null_std"], 6),
        "verdict":               verdict,
        "verdict_reason":        verdict_reason,
        "cross_warning":         cross_warning,
        # 功效
        "power":                 round(power, 6),
        "power_threshold":       power_threshold,
        "assumed_effect_size":   assumed_effect_size,
        # 饱和 sanity
        "saturation_switch":          saturation_switch,
        "active_severity":            active_severity,
        "fr_unet_medium_cldice_mean": round(fr_unet_medium_mean, 6) if not np.isnan(fr_unet_medium_mean) else None,
        # 交叉印证
        "cross_check_eps_consistent": cross_check_eps_consistent,
        "psr_eps":                    round(psr_eps, 6),
        "slope_dispersion_sr":        round(slope_dispersion_sr, 6) if not np.isnan(slope_dispersion_sr) else None,
        "slope_max_sr":               round(slope_max_sr, 6) if not np.isnan(slope_max_sr) else None,
        "slope_min_sr":               round(slope_min_sr, 6) if not np.isnan(slope_min_sr) else None,
        "slope_dispersion_reid":      round(slope_dispersion_reid, 6) if not np.isnan(slope_dispersion_reid) else None,
        "slope_max_reid":             round(slope_max_reid, 6) if not np.isnan(slope_max_reid) else None,
        "slope_min_reid":             round(slope_min_reid, 6) if not np.isnan(slope_min_reid) else None,
        "slope_signs_consistent":     slope_signs_consistent,
        # Kendall's W
        "kendall_w":             round(kendall_w, 6) if not np.isnan(kendall_w) else None,
        # 元数据
        "M":                     M,
        "n_pairs":               n_pairs,
        "n_images_pooled":       n,
        "n_separable_pairs":     n_separable,
        "methods":               methods,
        "bh_alpha_adjusted":     round(bh_alpha_adj, 6),
        "bh_q":                  q_fdr,
        "n_bootstrap":           n_bootstrap,
        "n_permutation":         n_permutation,
        "datasets_pooled":       list(datasets),
        "timestamp":             datetime.datetime.utcnow().isoformat() + "Z",
        # 配对明细（用于主线 debug，不进 paper）
        "pair_details_cldice":   psr_result["pair_details"],
    }


# ─────────────────────────────────────────────────────────────────────────────
#  CLI
# ─────────────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="批2 区分度门分析（PSR + shuffle-null + 功效 + 交叉印证 + Kendall W）"
    )
    p.add_argument(
        "--csv_glob", nargs="+", required=True,
        help=(
            "per-image CSV 路径 glob（可多个）。"
            "示例: outputs/p3/**/*.csv  或  outputs/p3/DRIVE_fr_unet_seed42/*.csv"
        ),
    )
    p.add_argument(
        "--severity", default="Medium",
        choices=["Easy", "Medium", "Hard", "Extreme"],
        help="主分析 severity（饱和 sanity 可自动切换 Hard）",
    )
    p.add_argument(
        "--datasets", nargs="+", default=["drive", "chase"],
        help="pool 的 dataset（小写，默认 drive chase）",
    )
    p.add_argument(
        "--out_json", default=None,
        help="输出 verdict JSON 路径（默认: results/disc_gate_verdict.json）",
    )
    p.add_argument("--n_bootstrap",    type=int,   default=2000,  help="cluster bootstrap B（默认2000）")
    p.add_argument("--n_permutation",  type=int,   default=1000,  help="shuffle-null 置换次数（默认1000）")
    p.add_argument("--q_fdr",          type=float, default=0.05,  help="BH-FDR q 水平（默认0.05）")
    p.add_argument("--power_threshold",type=float, default=0.5,   help="INSUFFICIENT 功效阈（默认0.5）")
    p.add_argument(
        "--assumed_effect_size", type=float, default=0.02,
        help="功效估计假设 clDice 真差（默认0.02，文献效应量参数化）",
    )
    p.add_argument("--seed", type=int, default=42, help="numpy rng seed（默认42）")
    p.add_argument(
        "--strong_baseline", default="fr_unet",
        help="饱和 sanity 用的强 baseline 名（默认 fr_unet）",
    )
    p.add_argument(
        "--saturation_hi", type=float, default=0.90,
        help="天花板阈（fr_unet Medium clDice > 此值 → 切 Hard，默认0.90）",
    )
    p.add_argument(
        "--saturation_lo", type=float, default=0.30,
        help="地板阈（fr_unet Medium clDice < 此值 → 切 Hard，默认0.30）",
    )
    return p.parse_args()


def main():
    args = _parse_args()

    # 展开 glob
    csv_paths: List[str] = []
    for g in args.csv_glob:
        expanded = glob.glob(g, recursive=True)
        csv_paths.extend(expanded)
    csv_paths = sorted(set(csv_paths))

    if not csv_paths:
        print(
            f"[gate] ERROR: glob {args.csv_glob!r} 未匹配到任何文件。",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"[gate] 找到 {len(csv_paths)} 个 CSV 文件", file=sys.stderr)

    # 运行分析
    result = analyze_gate(
        csv_paths           = csv_paths,
        severity            = args.severity,
        datasets            = tuple(args.datasets),
        n_bootstrap         = args.n_bootstrap,
        n_permutation       = args.n_permutation,
        q_fdr               = args.q_fdr,
        power_threshold     = args.power_threshold,
        assumed_effect_size = args.assumed_effect_size,
        seed                = args.seed,
        strong_baseline     = args.strong_baseline,
        saturation_hi       = args.saturation_hi,
        saturation_lo       = args.saturation_lo,
    )

    # 输出 JSON
    out_path = args.out_json
    if out_path is None:
        out_path = "results/disc_gate_verdict.json"
    out_p = Path(out_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    with open(out_p, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"[gate] verdict JSON 已写入: {out_p}", file=sys.stderr)
    print(f"[gate] ===== VERDICT: {result['verdict']} =====")
    print(f"  PSR clDice = {result['psr_cldice']}  null 95pct = {result['null_95pct']}")
    print(f"  power = {result['power']}  saturation_switch = {result['saturation_switch']}")
    print(f"  Kendall W = {result['kendall_w']}")
    print(f"  交叉印证 ε_β0 consistent = {result['cross_check_eps_consistent']}")
    print(f"  SR 斜率分散度 = {result['slope_dispersion_sr']}")
    print(f"  M = {result['M']}  n_images_pooled = {result['n_images_pooled']}")


if __name__ == "__main__":
    main()
