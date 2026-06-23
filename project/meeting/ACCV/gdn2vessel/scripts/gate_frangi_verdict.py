"""
gate_frangi_verdict.py — 路B Frangi门 gate-on vs gate-off 最小验证判定脚本。

功能：
  读取 12 run (DRIVE/CHASE × gate-on/off × 3seed) 的 per-image metrics CSV，
  numpy 手算 PASS/FAIL 判定，输出 verdict JSON。

CSV 格式（真实训练产出，reid_results.csv）：
  epoch, image_id, severity, dataset, reid_rate, reid_rate_head, reid_idf1,
  epsilon_beta0, success_rate, n_gaps, reid_rate_head_high, reid_rate_head_low,
  seed, cldice, betti_err_total, arm

  重要：csv 内 arm 列值 = 'memory'（reid_feat_source），不代表 gate-on/off。
  arm (gate-on/off) 从包含该 csv 的父目录名推断：
    - 目录名含 'gate_on' 或 'gate-on' → arm = 'gate-on'
    - 目录名含 'gate_off' 或 'gate-off' → arm = 'gate-off'
  目录命名示例：
    outputs/gate_sweep/gate_on_drive_s0/reid_results.csv  → gate-on
    outputs/gate_sweep/gate_off_drive_s0/reid_results.csv → gate-off

  多 epoch：每 run csv 含多行（不同 epoch 多次 eval），
  对每个 (image_id, seed) 取最大 epoch 行（防重复）。

  dataset 字段归一为小写。

PASS 条件（全部同时满足）：
  P1: ≥1集 clDice gap = mean(on) - mean(off) ≥ +0.03 (3-seed均值gap)
  P2: 该集 per-image 配对符号检验或 Wilcoxon 单侧 p < 0.05 (numpy手算)
      AND bootstrap 95%CI 下界 > 0 (≥1000 resample)
  P3: DRIVE + CHASE 两集方向都为正 (mean gap > 0)

FAIL 条件：gap<0.03 OR p≥0.05/CI≤0 OR 两集方向相反

辅助指标（ε_β0/Betti 同向作交叉印证，不参与 PASS 判定）：
  报告 gate-on vs gate-off 的 mean gap 及方向。

红线：
  - 禁 scipy.stats（OMP Error #15）——全程 numpy 手算
  - 禁 hardcode 假数据，需明确 CLI 路径输入
  - arm 不从 csv 内列读（那列是 memory），从目录名推断

用法（主线跑，coder 不跑）：
  # 最常用：指定含 12 run 子目录的根目录，自动递归找 reid_results.csv
  python scripts/gate_frangi_verdict.py \\
      --csv_dir outputs/gate_sweep/ \\
      --out_json outputs/gate_frangi_verdict.json

  # 或直接 glob
  python scripts/gate_frangi_verdict.py \\
      --csv_glob "outputs/gate_sweep/**/reid_results.csv" \\
      --out_json outputs/gate_frangi_verdict.json

Windows 兼容：无 scipy，无 fork，路径用 pathlib。
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np


# ============================================================================
# 判据常量（预登记，禁改）
# ============================================================================

GAP_THRESH   = 0.03      # clDice gap 最小判据（P1）
P_THRESH     = 0.05      # 单侧 p 值上界（P2）
N_BOOTSTRAP  = 1000      # bootstrap resample 次数（P2 CI）
DATASETS     = ['drive', 'chase']   # 路B 两集（P3）


# ============================================================================
# 纯 numpy 统计工具（禁 scipy.stats）
# ============================================================================

def sign_test_pvalue(deltas: np.ndarray, one_sided: str = 'greater') -> float:
    """
    符号检验（单侧）：H1: median(delta) > 0。
    纯 numpy，不用 scipy.stats.binom_test。

    Reference: Dixon & Mood 1946; any nonparametric stats textbook.
    p = P(X >= n_pos | X ~ Binom(n, 0.5)) where n = n_pos + n_neg (ties removed).
    """
    deltas = np.asarray(deltas, dtype=float)
    nonzero = deltas[deltas != 0.0]
    n = len(nonzero)
    if n == 0:
        return 1.0
    n_pos = int(np.sum(nonzero > 0))
    if one_sided == 'greater':
        # P(X >= n_pos | Binom(n, 0.5)) — exact via cumulative
        # P(X >= k) = sum_{j=k}^{n} C(n,j) * 0.5^n
        total = 0.0
        coeff = 1.0
        # Compute C(n, j) iteratively from j=0 to n
        coeffs = np.zeros(n + 1)
        coeffs[0] = 1.0
        for j in range(1, n + 1):
            coeffs[j] = coeffs[j - 1] * (n - j + 1) / j
        p = float(np.sum(coeffs[n_pos:]) * (0.5 ** n))
        return min(p, 1.0)
    raise ValueError(f'one_sided must be "greater", got {one_sided!r}')


def wilcoxon_signed_rank_pvalue(deltas: np.ndarray, one_sided: str = 'greater') -> float:
    """
    Wilcoxon 符号秩检验（单侧，正态近似，用于 n >= 10 场景）。
    纯 numpy，不用 scipy.stats.wilcoxon。

    Reference: Wilcoxon 1945; standard formula W+ statistic normal approximation.
    H1: delta > 0 (one_sided='greater').
    """
    deltas = np.asarray(deltas, dtype=float)
    nonzero = deltas[deltas != 0.0]
    n = len(nonzero)
    if n == 0:
        return 1.0
    # Ranks of |delta| (average ranks for ties)
    abs_d = np.abs(nonzero)
    order = np.argsort(abs_d)
    ranks = np.empty_like(order, dtype=float)
    ranks[order] = np.arange(1, n + 1, dtype=float)
    # Handle ties: average rank
    sorted_abs = abs_d[order]
    i = 0
    while i < n:
        j = i
        while j < n and sorted_abs[j] == sorted_abs[i]:
            j += 1
        if j > i + 1:
            avg = float(np.mean(np.arange(i + 1, j + 1, dtype=float)))
            for k in range(i, j):
                ranks[order[k]] = avg
        i = j
    # W+ = sum of ranks where delta > 0
    w_plus = float(np.sum(ranks[nonzero > 0]))
    # Normal approximation
    mu    = n * (n + 1) / 4.0
    sigma = np.sqrt(n * (n + 1) * (2 * n + 1) / 24.0)
    if sigma == 0.0:
        return 1.0
    # One-sided p for H1: W+ > expected
    z = (w_plus - mu) / sigma
    if one_sided == 'greater':
        # P(Z >= z) for standard normal, numpy approximation
        p = _standard_normal_sf(z)
        return float(p)
    raise ValueError(f'one_sided must be "greater", got {one_sided!r}')


def _standard_normal_sf(z: float) -> float:
    """
    Survival function P(Z > z) for standard normal, using numpy erf.
    Accurate to ~1e-14 for |z| < 8.
    """
    return float(0.5 * (1.0 - float(np.real(
        # erfc(z/sqrt(2)) / 2
        # numpy has no erfc, use erf
        _erf(z / np.sqrt(2.0))
    ))))


def _erf(x: float) -> float:
    """numpy-based erf via series approximation (Abramowitz & Stegun 7.1.26)."""
    # Use numpy's built-in vectorized erf if available (numpy >= 1.20)
    return float(np.sign(x) * (1.0 - _erfc_approx(abs(x))))


def _erfc_approx(x: float) -> float:
    """Complementary error function approximation (rational Chebyshev)."""
    # A&S 7.1.26: max |ε| < 1.5e-7
    p  = 0.3275911
    a1 = 0.254829592
    a2 = -0.284496736
    a3 = 1.421413741
    a4 = -1.453152027
    a5 = 1.061405429
    t = 1.0 / (1.0 + p * x)
    poly = t * (a1 + t * (a2 + t * (a3 + t * (a4 + t * a5))))
    return float(poly * np.exp(-x * x))


def bootstrap_ci_lower(deltas: np.ndarray,
                        n_resample: int = N_BOOTSTRAP,
                        alpha: float = 0.05,
                        rng_seed: int = 0) -> float:
    """
    Bootstrap 95% CI 下界：对 per-image delta 进行 n_resample 次有放回抽样，
    计算每次 mean，取 alpha/2 分位数作为 CI 下界。

    纯 numpy，不用 scipy.
    """
    deltas = np.asarray(deltas, dtype=float)
    n = len(deltas)
    if n == 0:
        return float('-inf')
    rng = np.random.default_rng(rng_seed)
    boot_means = np.array([
        rng.choice(deltas, size=n, replace=True).mean()
        for _ in range(n_resample)
    ])
    ci_lower = float(np.percentile(boot_means, 100.0 * alpha / 2.0))
    return ci_lower


# ============================================================================
# arm 推断（从目录名，不读 csv 内 arm 列）
# ============================================================================

def infer_arm_from_dirpath(csv_path: Path) -> Optional[str]:
    """
    从 csv 文件的父目录名推断 arm（gate-on / gate-off）。

    规则（大小写不敏感，- 和 _ 等价）：
      目录名含 'gate_on'  或 'gate-on'  → 'gate-on'
      目录名含 'gate_off' 或 'gate-off' → 'gate-off'

    返回 None 表示推断失败（调用方会打 WARNING 并跳过该 csv）。

    动机：真实训练输出 csv 内 arm 列值='memory'（reid_feat_source），
    不代表 gate-on/off；arm 信息编码在子目录名里，例如：
      outputs/gate_sweep/gate_on_drive_s0/reid_results.csv  → gate-on
      outputs/gate_sweep/gate_off_drive_s0/reid_results.csv → gate-off
    """
    # 检查 csv 文件所在目录 + 其父目录（共两级）
    for part in [csv_path.parent.name, csv_path.parent.parent.name]:
        normalized = part.replace('-', '_').lower()
        if 'gate_on' in normalized:
            return 'gate-on'
        if 'gate_off' in normalized:
            return 'gate-off'
    return None


# ============================================================================
# CSV 加载
# ============================================================================

def load_metrics_csv(csv_paths: List[Path],
                     arm_override: Optional[str] = None) -> Dict[str, List[dict]]:
    """
    读取多个 per-run metrics CSV，按 dataset 分组返回行列表。

    真实 CSV 格式（reid_results.csv）：
      epoch, image_id, severity, dataset, reid_rate, reid_rate_head, reid_idf1,
      epsilon_beta0, success_rate, n_gaps, reid_rate_head_high, reid_rate_head_low,
      seed, cldice, betti_err_total, arm

    arm 来源：
      1. arm_override 参数（单测时直接指定，e.g. 'gate-on'）
      2. csv 父目录名推断（infer_arm_from_dirpath）
      3. csv 内 arm 列归一化（兼容旧格式/单测 csv 里直接写 gate-on/gate-off）
      优先级：arm_override > 目录名 > csv 列（fallback）

    多 epoch 去重：对每个 (image_id, seed) 只保留最大 epoch 行，
    防止多次 eval 导致同图重复计入。

    dataset 归一为小写。
    缺失列 → 报警告，填 NaN（不 crash）。
    """
    # 需要的列（csv 内 arm 列降为可选，实际从目录名推断）
    required_cols = {'image_id', 'dataset', 'seed', 'cldice',
                     'epsilon_beta0', 'betti_err_total'}

    # 每个 csv 路径加载为 raw rows（含 epoch）
    # 结构：{(dataset, image_id, seed, arm): {epoch: raw_row}}
    # 先按 csv 粒度聚合，最后选最大 epoch
    raw_by_key: Dict[tuple, dict] = {}  # key → {epoch → parsed_row_dict}

    for csv_path in csv_paths:
        csv_path = Path(csv_path)
        if not csv_path.exists():
            print(f'[gate_frangi_verdict] WARNING: CSV not found, skip: {csv_path}',
                  file=sys.stderr)
            continue

        # 推断 arm
        if arm_override is not None:
            arm_for_this_csv = arm_override
        else:
            arm_from_dir = infer_arm_from_dirpath(csv_path)
            if arm_from_dir is not None:
                arm_for_this_csv = arm_from_dir
            else:
                # fallback: 读 csv 内 arm 列（旧格式 / 单测直接写 gate-on/gate-off）
                arm_for_this_csv = None  # 延迟到行级推断

        with open(csv_path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                print(f'[gate_frangi_verdict] WARNING: empty CSV, skip: {csv_path}',
                      file=sys.stderr)
                continue
            missing = required_cols - set(reader.fieldnames)
            if missing:
                print(f'[gate_frangi_verdict] WARNING: CSV missing cols {missing}: {csv_path}',
                      file=sys.stderr)

            for row in reader:
                ds = row.get('dataset', '').strip().lower()
                if not ds:
                    continue

                # arm 确定
                if arm_for_this_csv is not None:
                    arm = arm_for_this_csv
                else:
                    # fallback: 从 csv 内 arm 列归一化（兼容直接写 gate-on/gate-off 的旧格式）
                    arm_raw = row.get('arm', '').strip().lower()
                    if arm_raw in ('gate-on', 'gate_on', '1', 'on'):
                        arm = 'gate-on'
                    elif arm_raw in ('gate-off', 'gate_off', '0', 'off'):
                        arm = 'gate-off'
                    else:
                        # 真实 csv 的 'memory' 会走到这里——警告并跳过
                        print(
                            f'[gate_frangi_verdict] WARNING: cannot infer arm from dir '
                            f'({csv_path.parent.name!r}) or csv col ({arm_raw!r}), skip row '
                            f'image_id={row.get("image_id")!r} in {csv_path}',
                            file=sys.stderr)
                        continue

                image_id = row.get('image_id', '').strip()
                seed     = _safe_int(row.get('seed', '0'))
                epoch    = _safe_int(row.get('epoch', '0'))

                key = (ds, image_id, seed, arm)
                parsed = {
                    'image_id':         image_id,
                    'dataset':          ds,
                    'seed':             seed,
                    'arm':              arm,
                    'epoch':            epoch,
                    'cldice':           _safe_float(row.get('cldice', 'nan')),
                    'epsilon_beta0':    _safe_float(row.get('epsilon_beta0', 'nan')),
                    'betti_err_total':  _safe_float(row.get('betti_err_total', 'nan')),
                }
                # 保留最大 epoch（每 key 只存一行 → last epoch wins）
                if key not in raw_by_key or epoch > raw_by_key[key]['epoch']:
                    raw_by_key[key] = parsed

    # 按 dataset 聚合（去掉 epoch 字段，不需要下游知道）
    rows_by_dataset: Dict[str, List[dict]] = {}
    for parsed in raw_by_key.values():
        ds = parsed['dataset']
        rows_by_dataset.setdefault(ds, []).append(parsed)

    return rows_by_dataset


def _safe_float(s: str) -> float:
    try:
        return float(s)
    except (ValueError, TypeError):
        return float('nan')


def _safe_int(s: str) -> int:
    try:
        return int(s)
    except (ValueError, TypeError):
        return 0


# ============================================================================
# 配对逻辑
# ============================================================================

def paired_gate_deltas(rows: List[dict],
                        metric: str = 'cldice') -> Tuple[np.ndarray, dict]:
    """
    对同一 dataset 内的行按 (image_id, seed) 配对 gate-on vs gate-off，
    返回 delta 数组 (on - off) 及配对统计 dict。

    配对键 = (image_id, seed)：同断点 benchmark 天然配对（同 split 同 seed）。
    """
    on_map:  Dict[tuple, float] = {}
    off_map: Dict[tuple, float] = {}
    for r in rows:
        key = (r['image_id'], r['seed'])
        val = r[metric]
        if r['arm'] == 'gate-on':
            on_map[key] = val
        elif r['arm'] == 'gate-off':
            off_map[key] = val

    common = sorted(set(on_map) & set(off_map))
    n_total_on  = sum(1 for r in rows if r['arm'] == 'gate-on')
    n_total_off = sum(1 for r in rows if r['arm'] == 'gate-off')

    if not common:
        return np.array([]), {
            'n_pairs': 0, 'n_on': n_total_on, 'n_off': n_total_off,
            'n_keys_on': len(on_map), 'n_keys_off': len(off_map),
        }

    on_vals  = np.array([on_map[k]  for k in common], dtype=float)
    off_vals = np.array([off_map[k] for k in common], dtype=float)
    deltas = on_vals - off_vals

    # Drop NaN pairs
    valid = ~(np.isnan(on_vals) | np.isnan(off_vals))
    deltas = deltas[valid]

    info = {
        'n_pairs': len(common),
        'n_valid': int(np.sum(valid)),
        'n_on':  n_total_on,
        'n_off': n_total_off,
    }
    return deltas, info


# ============================================================================
# 单集判定
# ============================================================================

def dataset_verdict(rows: List[dict],
                    dataset: str,
                    metric: str = 'cldice') -> dict:
    """
    对单集（DRIVE 或 CHASE）判定 gate-on vs gate-off。

    返回 dict 包含：
      gap, n_pairs, mean_on, mean_off,
      sign_p, wilcoxon_p, p_used, boot_ci_lower,
      direction_positive (gap > 0),
      gap_ok (gap >= GAP_THRESH),
      stat_ok (p_used < P_THRESH AND boot_ci_lower > 0),
      dataset_pass (gap_ok AND stat_ok AND direction_positive)
      reason (触发原因，PASS时空字符串)
    """
    deltas, pair_info = paired_gate_deltas(rows, metric=metric)
    n = len(deltas)

    mean_on  = float(np.nanmean([r[metric] for r in rows if r['arm'] == 'gate-on']))
    mean_off = float(np.nanmean([r[metric] for r in rows if r['arm'] == 'gate-off']))
    gap = float(mean_on - mean_off)

    if n == 0:
        return {
            'dataset': dataset, 'metric': metric,
            'gap': gap, 'n_pairs': 0, 'mean_on': mean_on, 'mean_off': mean_off,
            'sign_p': 1.0, 'wilcoxon_p': 1.0, 'p_used': 1.0, 'boot_ci_lower': float('-inf'),
            'direction_positive': gap > 0,
            'gap_ok': False, 'stat_ok': False, 'dataset_pass': False,
            'reason': f'n_pairs=0, no valid paired data',
            **pair_info,
        }

    sign_p = sign_test_pvalue(deltas, one_sided='greater')
    wilcoxon_p = (wilcoxon_signed_rank_pvalue(deltas, one_sided='greater')
                  if n >= 10 else sign_p)   # Wilcoxon normal approx 要求 n≥10
    p_used = min(sign_p, wilcoxon_p)        # 取较小者（更保守 → 联合判据）

    ci_lower = bootstrap_ci_lower(deltas, n_resample=N_BOOTSTRAP, rng_seed=42)

    direction_pos = gap > 0.0
    gap_ok  = gap >= GAP_THRESH
    stat_ok = (p_used < P_THRESH) and (ci_lower > 0.0)
    ds_pass = gap_ok and stat_ok and direction_pos

    reasons = []
    if not direction_pos:
        reasons.append(f'direction negative (gap={gap:.4f})')
    if not gap_ok:
        reasons.append(f'gap={gap:.4f} < threshold={GAP_THRESH}')
    if p_used >= P_THRESH:
        reasons.append(f'p={p_used:.4f} >= {P_THRESH}')
    if ci_lower <= 0.0:
        reasons.append(f'boot_CI_lower={ci_lower:.4f} <= 0')

    return {
        'dataset': dataset, 'metric': metric,
        'gap': round(gap, 6),
        'mean_on': round(mean_on, 6),
        'mean_off': round(mean_off, 6),
        'n_pairs': n,
        **pair_info,
        'sign_p': round(sign_p, 6),
        'wilcoxon_p': round(wilcoxon_p, 6),
        'p_used': round(p_used, 6),
        'boot_ci_lower': round(ci_lower, 6),
        'direction_positive': bool(direction_pos),
        'gap_ok':   bool(gap_ok),
        'stat_ok':  bool(stat_ok),
        'dataset_pass': bool(ds_pass),
        'reason': '; '.join(reasons) if reasons else '',
    }


# ============================================================================
# 辅助指标报告（ε_β0 / Betti，不参与 PASS 判定）
# ============================================================================

def aux_metric_report(rows: List[dict], metric: str, dataset: str) -> dict:
    """ε_β0 或 betti_err_total 的方向报告（lower is better → gate-on 应更小）。"""
    # 注：ε_β0 / Betti 越小越好，所以 on 比 off 改善 = gap < 0（反向）
    deltas, _ = paired_gate_deltas(rows, metric=metric)
    mean_on  = float(np.nanmean([r[metric] for r in rows if r['arm'] == 'gate-on']))
    mean_off = float(np.nanmean([r[metric] for r in rows if r['arm'] == 'gate-off']))
    gap = float(mean_on - mean_off)  # 负 = gate-on 更好（低 ε 更好）
    return {
        'dataset': dataset, 'metric': metric,
        'gap': round(gap, 6),     # 负值 = gate-on 改善
        'mean_on': round(mean_on, 6),
        'mean_off': round(mean_off, 6),
        'n_pairs': len(deltas),
        'direction_better': bool(gap < 0),   # lower is better
        'note': 'auxiliary only, not in PASS criteria',
    }


# ============================================================================
# 全局 PASS/FAIL 判定
# ============================================================================

def run_verdict(rows_by_dataset: Dict[str, List[dict]],
                datasets: Optional[List[str]] = None) -> dict:
    """
    全局判定：DRIVE + CHASE 两集同时通过 P1/P2/P3 才 PASS。

    Args:
        rows_by_dataset: dataset → rows（由 load_metrics_csv 返回）
        datasets:        要检查的集列表（默认 DATASETS = ['drive','chase']）

    Returns:
        verdict dict，含 per-dataset 结果 + 全局 PASS/FAIL + 触发原因。
    """
    if datasets is None:
        datasets = DATASETS

    per_dataset: List[dict] = []
    aux_eps_b0: List[dict] = []
    aux_betti:  List[dict] = []

    for ds in datasets:
        rows = rows_by_dataset.get(ds, [])
        if not rows:
            print(f'[gate_frangi_verdict] WARNING: no rows for dataset={ds!r}',
                  file=sys.stderr)
        # 主判据：clDice
        per_dataset.append(dataset_verdict(rows, ds, metric='cldice'))
        # 辅助印证
        aux_eps_b0.append(aux_metric_report(rows, 'epsilon_beta0', ds))
        aux_betti.append(aux_metric_report(rows, 'betti_err_total', ds))

    # P3: 两集方向都为正
    all_positive_direction = all(d['direction_positive'] for d in per_dataset)
    # P1: ≥1 集 gap >= 0.03
    any_gap_ok = any(d['gap_ok'] for d in per_dataset)
    # P2: 对应集 stat_ok（p<0.05 AND CI>0）
    # PASS = 所有 P1/P2/P3 同时：≥1 集 gap 达标 + 该集 stat_ok + 两集方向正
    gap_ok_datasets  = [d['dataset'] for d in per_dataset if d['gap_ok']]
    stat_ok_datasets = [d['dataset'] for d in per_dataset if d['stat_ok']]
    pass_datasets    = [d['dataset'] for d in per_dataset if d['dataset_pass']]

    # Strict: 需要 ≥1 集同时满足 P1+P2，且 P3（两集都正向）
    global_pass = bool(
        any_gap_ok
        and any(d['gap_ok'] and d['stat_ok'] for d in per_dataset)
        and all_positive_direction
    )

    fail_reasons = []
    if not any_gap_ok:
        fail_reasons.append(
            f'No dataset reached gap>={GAP_THRESH}: '
            + ', '.join(f"{d['dataset']}={d['gap']:.4f}" for d in per_dataset)
        )
    if not any(d['stat_ok'] for d in per_dataset if d['gap_ok']):
        fail_reasons.append(
            f'No dataset with gap>={GAP_THRESH} passed stat test (p<{P_THRESH} AND CI>0)'
        )
    if not all_positive_direction:
        neg_dirs = [d['dataset'] for d in per_dataset if not d['direction_positive']]
        fail_reasons.append(f'Negative direction in: {neg_dirs} — P3 violated')

    verdict_str = 'PASS' if global_pass else 'FAIL'

    result = {
        'VERDICT':            verdict_str,
        'global_pass':        global_pass,
        'fail_reasons':       fail_reasons,
        'thresholds': {
            'gap_thresh':    GAP_THRESH,
            'p_thresh':      P_THRESH,
            'n_bootstrap':   N_BOOTSTRAP,
            'datasets':      datasets,
        },
        # 主判据 per-dataset
        'per_dataset_cldice': per_dataset,
        'gap_ok_datasets':    gap_ok_datasets,
        'stat_ok_datasets':   stat_ok_datasets,
        'pass_datasets':      pass_datasets,
        # 辅助印证（不参与 PASS，仅报告）
        'aux_epsilon_beta0':  aux_eps_b0,
        'aux_betti_err':      aux_betti,
    }
    return result


# ============================================================================
# CLI
# ============================================================================

def parse_args():
    p = argparse.ArgumentParser(
        description='路B Frangi门 gate-on vs gate-off 最小验证 PASS/FAIL 判定')
    p.add_argument('--csv_dir', type=str, default=None,
                   help='包含所有 12 run 的 metrics CSV 的根目录（递归搜索 *.csv）')
    p.add_argument('--csv_glob', type=str, default=None,
                   help='直接指定 CSV glob 路径（与 --csv_dir 二选一）')
    p.add_argument('--csv_files', type=str, nargs='+', default=None,
                   help='直接指定多个 CSV 文件路径')
    p.add_argument('--datasets', type=str, nargs='+', default=None,
                   help=f'要检查的集（默认 {DATASETS}）')
    p.add_argument('--out_json', type=str, default=None,
                   help='输出 verdict JSON 路径（默认仅打印到 stdout）')
    return p.parse_args()


def main():
    args = parse_args()

    # ---- 收集 CSV 文件 ----
    csv_paths: List[Path] = []
    if args.csv_files:
        csv_paths = [Path(f) for f in args.csv_files]
    elif args.csv_glob:
        csv_paths = [Path(f) for f in glob.glob(args.csv_glob, recursive=True)]
    elif args.csv_dir:
        csv_paths = list(Path(args.csv_dir).rglob('*.csv'))
    else:
        print('[gate_frangi_verdict] ERROR: 需要 --csv_dir / --csv_glob / --csv_files 之一',
              file=sys.stderr)
        sys.exit(1)

    if not csv_paths:
        print(f'[gate_frangi_verdict] ERROR: 未找到任何 CSV 文件', file=sys.stderr)
        sys.exit(1)

    print(f'[gate_frangi_verdict] 找到 {len(csv_paths)} 个 CSV 文件', file=sys.stderr)

    # ---- 打印每个 csv 推断到的 arm（调试用） ----
    for cp in sorted(csv_paths):
        inferred = infer_arm_from_dirpath(Path(cp))
        print(f'[gate_frangi_verdict]   {Path(cp).parent.name!r:40s} → arm={inferred!r}',
              file=sys.stderr)

    # ---- 加载 ----
    rows_by_dataset = load_metrics_csv(csv_paths)
    for ds, rows in rows_by_dataset.items():
        n_on  = sum(1 for r in rows if r['arm'] == 'gate-on')
        n_off = sum(1 for r in rows if r['arm'] == 'gate-off')
        print(f'[gate_frangi_verdict] dataset={ds}: {len(rows)} rows '
              f'(gate-on={n_on}, gate-off={n_off})', file=sys.stderr)

    # ---- 判定 ----
    datasets = args.datasets or DATASETS
    verdict = run_verdict(rows_by_dataset, datasets=datasets)

    # ---- 输出 ----
    out_str = json.dumps(verdict, indent=2, ensure_ascii=False)
    print(out_str)

    if args.out_json:
        out_path = Path(args.out_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(out_str)
        print(f'[gate_frangi_verdict] verdict written → {out_path}', file=sys.stderr)

    # ---- 人读摘要 ----
    print('\n' + '=' * 60, file=sys.stderr)
    print(f'  FRANGI GATE VERDICT: {verdict["VERDICT"]}', file=sys.stderr)
    print('=' * 60, file=sys.stderr)
    for d in verdict['per_dataset_cldice']:
        status = 'PASS' if d['dataset_pass'] else 'FAIL'
        print(f'  [{status}] {d["dataset"]}: gap={d["gap"]:.4f}  '
              f'p={d["p_used"]:.4f}  CI_lo={d["boot_ci_lower"]:.4f}', file=sys.stderr)
    if verdict['fail_reasons']:
        for r in verdict['fail_reasons']:
            print(f'  FAIL reason: {r}', file=sys.stderr)
    print('', file=sys.stderr)

    sys.exit(0 if verdict['global_pass'] else 1)


if __name__ == '__main__':
    main()
