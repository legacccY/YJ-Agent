"""probe_corr.py — corr(σ, ρ) 后处理 — NCA-PhaseMap 补2 §3
服务项目：NCA-PhaseMap / K-new-3 机制段（corr 检查）

方法：
    读 probe_sigma.csv + probe_rho.csv，
    配对 (ur, init_seed, dataset)，
    计算 Pearson r + Spearman ρ_s（纯 numpy，无 scipy）。
    |r| ≥ 0.9 → 打印「σ≈ρ 同源 → 双独立腿措辞」提示。
    纯后处理，无 GPU。

配对规则：
    以 probe_sigma.csv 的 (ur, init_seed, dataset) 为主键，
    左连接 probe_rho.csv，mre_ok=1 且 converged=1 的行才纳入分析。

【入口】
    python probe_corr.py [--sigma_csv results/probe_sigma.csv]
                         [--rho_csv results/probe_rho.csv]
                         [--out_csv results/probe_corr.csv]
                         [--r_thresh 0.9]

【输出】
    results/probe_corr.csv
    列: dataset, n_pairs, pearson_r, pearson_p, spearman_r, spearman_p,
        abs_r_max, verdict
    打印逐对数值 + 全局 verdict

【无 scipy 实现说明】
    Pearson r：numpy 标准公式
    Spearman ρ_s：对 σ 和 ρ 分别 argsort 求秩，再算 Pearson r of ranks
    p 值：t 统计量 t = r * sqrt(n-2) / sqrt(1-r²)，
          两尾 p ≈ 2*(1-Φ(|t|)) 用 numpy 数值积分近似（无 scipy.stats）
    这是与 sweep 保持一致的「纯 numpy 实现」规范。
"""

import os
import sys
import csv
import json
import math
import time
import argparse
import numpy as np

# ─── 路径常量 ─────────────────────────────────────────────────────────
THIS_DIR    = os.environ.get('PHASEMAP_OUT',
                             os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(THIS_DIR, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

_DEFAULT_SIGMA_CSV = os.path.join(RESULTS_DIR, "probe_sigma.csv")
_DEFAULT_RHO_CSV   = os.path.join(RESULTS_DIR, "probe_rho.csv")
_DEFAULT_OUT_CSV   = os.path.join(RESULTS_DIR, "probe_corr.csv")


# ─── 纯 numpy 统计工具（无 scipy） ───────────────────────────────────

def _pearson_r(x, y):
    """Pearson r（numpy 标准实现）。返回 (r, p_value)。"""
    n = len(x)
    if n < 3:
        return float('nan'), float('nan')
    xm = x - x.mean()
    ym = y - y.mean()
    denom = math.sqrt((xm**2).sum() * (ym**2).sum())
    if denom < 1e-20:
        return float('nan'), float('nan')
    r = float((xm * ym).sum() / denom)
    r = max(-1.0, min(1.0, r))  # 夹 [-1,1] 防浮点溢出

    # p 值：t 统计量 → 近似两尾 p（正态近似，适合 n≥10）
    if abs(r) >= 1.0 - 1e-10:
        p = 0.0
    else:
        t_stat = r * math.sqrt(n - 2) / math.sqrt(1.0 - r**2 + 1e-20)
        # 两尾 p ≈ 2*(1-Φ(|t|))，Φ 用 erf 近似
        p = 2.0 * (1.0 - _norm_cdf(abs(t_stat)))
    return r, p


def _norm_cdf(z):
    """标准正态 CDF Φ(z)，用 math.erf 实现，无 scipy。"""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _rankdata(arr):
    """对 arr 赋秩次（平均秩处理并列，numpy 纯实现）。"""
    n = len(arr)
    order = np.argsort(arr, kind='stable')
    ranks = np.empty(n, dtype=float)
    i = 0
    while i < n:
        j = i + 1
        while j < n and arr[order[j]] == arr[order[i]]:
            j += 1
        # [i, j) 并列，平均秩
        avg_rank = (i + j - 1) / 2.0 + 1.0
        ranks[order[i:j]] = avg_rank
        i = j
    return ranks


def _spearman_r(x, y):
    """Spearman ρ_s（via Pearson of ranks）。返回 (rho, p_value)。"""
    rx = _rankdata(x)
    ry = _rankdata(y)
    return _pearson_r(rx, ry)


# ─── CSV 读取 ─────────────────────────────────────────────────────────

def read_csv_as_dicts(path):
    """读 csv，返回 list of dict（值仍为 str）。"""
    if not os.path.exists(path):
        raise FileNotFoundError(f"CSV 不存在: {path}")
    with open(path, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        return list(reader)


def _safe_float(s):
    """安全转 float，nan 字符串 → float('nan')。"""
    try:
        v = float(s)
        return v
    except (ValueError, TypeError):
        return float('nan')


def _safe_int(s, default=0):
    try:
        return int(s)
    except (ValueError, TypeError):
        return default


# ─── 主逻辑 ──────────────────────────────────────────────────────────

def run_corr(sigma_csv, rho_csv, out_csv, r_thresh=0.9):
    """
    配对 probe_sigma.csv + probe_rho.csv，计算 corr(σ, ρ)。
    返回 list of result dicts（每个 dataset 一行）。
    """
    print(f"[probe_corr] 读 sigma_csv: {sigma_csv}", flush=True)
    sigma_rows = read_csv_as_dicts(sigma_csv)
    print(f"[probe_corr] 读 rho_csv:   {rho_csv}", flush=True)
    rho_rows   = read_csv_as_dicts(rho_csv)

    # 构建 rho 索引：(ur_str, init_seed_str, dataset_str) → row
    rho_index = {}
    for r in rho_rows:
        key = (r['ur'], r['init_seed'], r['dataset'])
        rho_index[key] = r

    # 按 dataset 分组
    datasets_seen = sorted(set(r['dataset'] for r in sigma_rows))
    print(f"[probe_corr] datasets: {datasets_seen}", flush=True)

    all_result_rows = []
    all_sigmas = []
    all_rhos   = []

    for ds in datasets_seen:
        sigmas = []
        rhos   = []
        skipped_no_rho  = 0
        skipped_mre     = 0
        skipped_conv    = 0
        skipped_nan     = 0

        for sr in sigma_rows:
            if sr['dataset'] != ds:
                continue

            mre_ok = _safe_int(sr.get('mre_ok', '1'), default=1)
            if mre_ok == 0:
                skipped_mre += 1
                continue

            key = (sr['ur'], sr['init_seed'], sr['dataset'])
            rr  = rho_index.get(key)
            if rr is None:
                skipped_no_rho += 1
                continue

            converged = _safe_int(rr.get('converged', '1'), default=1)
            if converged == 0:
                skipped_conv += 1
                continue

            sv = _safe_float(sr['sigma'])
            rv = _safe_float(rr['rho'])

            if math.isnan(sv) or math.isnan(rv):
                skipped_nan += 1
                continue

            sigmas.append(sv)
            rhos.append(rv)

        n_pairs = len(sigmas)
        print(
            f"\n[probe_corr] dataset={ds}  n_pairs={n_pairs}  "
            f"skipped: no_rho={skipped_no_rho} mre_fail={skipped_mre} "
            f"not_conv={skipped_conv} nan={skipped_nan}",
            flush=True
        )

        if n_pairs < 3:
            print(f"  [WARN] 有效配对 {n_pairs}<3，跳过相关计算", flush=True)
            res = {
                'dataset': ds, 'n_pairs': n_pairs,
                'pearson_r': 'nan', 'pearson_p': 'nan',
                'spearman_r': 'nan', 'spearman_p': 'nan',
                'abs_r_max': 'nan', 'verdict': 'insufficient_data',
            }
            all_result_rows.append(res)
            continue

        sig_arr = np.array(sigmas, dtype=float)
        rho_arr = np.array(rhos,   dtype=float)

        pr, pp     = _pearson_r(sig_arr, rho_arr)
        sr2, sp    = _spearman_r(sig_arr, rho_arr)
        abs_r_max  = max(abs(pr), abs(sr2))

        if abs_r_max >= r_thresh:
            verdict = f"sigma_approx_rho_DUAL_LEG (|r|={abs_r_max:.3f}>={r_thresh})"
            print(
                f"  Pearson r={pr:.4f}(p={pp:.4f})  "
                f"Spearman rho={sr2:.4f}(p={sp:.4f})",
                flush=True
            )
            print(
                f"\n  *** |r|={abs_r_max:.3f} >= {r_thresh} ***\n"
                f"  → σ≈ρ 数学同源（谱临界量同源）\n"
                f"  → 措辞降「一个谱临界量(σ≈ρ) + 一个空间传播量 d(N)」双独立腿\n"
                f"  → 不得卖「三个独立机制量」",
                flush=True
            )
        else:
            verdict = f"sigma_rho_independent (|r|={abs_r_max:.3f}<{r_thresh})"
            print(
                f"  Pearson r={pr:.4f}(p={pp:.4f})  "
                f"Spearman rho={sr2:.4f}(p={sp:.4f})",
                flush=True
            )
            print(
                f"  |r|={abs_r_max:.3f} < {r_thresh}  "
                f"→ σ 与 ρ 测量不同维度，可保留三独立腿（bonus）",
                flush=True
            )

        res = {
            'dataset':   ds,
            'n_pairs':   n_pairs,
            'pearson_r': round(pr,  6) if not math.isnan(pr)  else 'nan',
            'pearson_p': round(pp,  6) if not math.isnan(pp)  else 'nan',
            'spearman_r': round(sr2, 6) if not math.isnan(sr2) else 'nan',
            'spearman_p': round(sp,  6) if not math.isnan(sp)  else 'nan',
            'abs_r_max': round(abs_r_max, 6) if not math.isnan(abs_r_max) else 'nan',
            'verdict':   verdict,
        }
        all_result_rows.append(res)
        all_sigmas.extend(sigmas)
        all_rhos.extend(rhos)

    # ── 全局（跨 dataset）相关 ──────────────────────────────────────
    if len(all_sigmas) >= 3:
        sig_all = np.array(all_sigmas, dtype=float)
        rho_all = np.array(all_rhos,   dtype=float)
        pr_all, pp_all   = _pearson_r(sig_all, rho_all)
        sr_all, sp_all   = _spearman_r(sig_all, rho_all)
        abs_max_all      = max(abs(pr_all), abs(sr_all))
        verdict_all      = (f"ALL_sigma_approx_rho_DUAL_LEG (|r|={abs_max_all:.3f}>={r_thresh})"
                            if abs_max_all >= r_thresh
                            else f"ALL_independent (|r|={abs_max_all:.3f}<{r_thresh})")
        print(
            f"\n[probe_corr] 全局（all datasets）  n={len(all_sigmas)}\n"
            f"  Pearson r={pr_all:.4f}(p={pp_all:.4f})  "
            f"Spearman rho={sr_all:.4f}(p={sp_all:.4f})\n"
            f"  verdict: {verdict_all}",
            flush=True
        )
        all_result_rows.append({
            'dataset':   'ALL',
            'n_pairs':   len(all_sigmas),
            'pearson_r': round(pr_all,  6) if not math.isnan(pr_all)  else 'nan',
            'pearson_p': round(pp_all,  6) if not math.isnan(pp_all)  else 'nan',
            'spearman_r': round(sr_all, 6) if not math.isnan(sr_all)  else 'nan',
            'spearman_p': round(sp_all, 6) if not math.isnan(sp_all)  else 'nan',
            'abs_r_max': round(abs_max_all, 6) if not math.isnan(abs_max_all) else 'nan',
            'verdict':   verdict_all,
        })

    # ── 写 CSV ───────────────────────────────────────────────────────
    cols = ['dataset', 'n_pairs', 'pearson_r', 'pearson_p',
            'spearman_r', 'spearman_p', 'abs_r_max', 'verdict']
    with open(out_csv, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore')
        w.writeheader()
        w.writerows(all_result_rows)
    print(f"\n[probe_corr] 完成。CSV: {out_csv}", flush=True)

    return all_result_rows


# ─── 主流程 ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="corr(σ,ρ) 后处理 — NCA-PhaseMap §3（纯 numpy，无 scipy/GPU）"
    )
    parser.add_argument('--sigma_csv', default=_DEFAULT_SIGMA_CSV,
                        help=f'probe_sigma.csv 路径（默认 {_DEFAULT_SIGMA_CSV}）')
    parser.add_argument('--rho_csv',   default=_DEFAULT_RHO_CSV,
                        help=f'probe_rho.csv 路径（默认 {_DEFAULT_RHO_CSV}）')
    parser.add_argument('--out_csv',   default=_DEFAULT_OUT_CSV,
                        help=f'输出 CSV 路径（默认 {_DEFAULT_OUT_CSV}）')
    parser.add_argument('--r_thresh',  type=float, default=0.9,
                        help='同源判定阈（默认 |r|≥0.9）')
    args = parser.parse_args()

    print(f"[probe_corr] r_thresh={args.r_thresh}", flush=True)
    run_corr(
        sigma_csv=args.sigma_csv,
        rho_csv=args.rho_csv,
        out_csv=args.out_csv,
        r_thresh=args.r_thresh,
    )


if __name__ == '__main__':
    main()
