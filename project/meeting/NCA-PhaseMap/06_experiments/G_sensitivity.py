"""G 阈值敏感性后处理 — NCA-PhaseMap Gate1 腿② 🟡-4

读 G_gradient_traj.py 产出的 traj csv，对 27 组 P_g × P_f × N 参数组合，
计算 sign(t_grad_die - t_func_die) 是否 27/27 同号，判断是否升级 A3 因果。

【定义】
    t_grad_die(run, P_g)  = 第一个 step s.t. 接下来 N 步的 grad_norm_mean 均 < P_g 百分位阈
    t_func_die(run, P_f)  = 第一个 step s.t. 接下来 N 步的 dice_proxy 均 < P_f 百分位阈
    sign_delta = sign(t_grad_die - t_func_die)
      >0 → 梯度先降（功能先崩，梯度随后），A3 支柱2「塌缩非梯度驱动」可能成立
      <0 → 梯度先死（梯度先于功能崩），K4 翻转 A3，改写 claim
      =0 → 同时，不可分辨

【27 组参数】
    P_g ∈ {10%, 20%, 30%}    （grad_norm 下降阈百分位）
    P_f ∈ {1%, 2%, 5%}       （dice_proxy 下降阈百分位）
    N   ∈ {3, 5, 10}         （连续 N 步确认稳定性）

【结论规则（🟡-4 冻结）】
    - 所有 run × 所有组合 27/27 同号 → 升级 A3 因果
    - 任一翻号                      → 「时序不可分辨，维持相关性，不升级因果」
    - t_grad >  t_func（27/27）     → 功能先崩，梯度未先死  → A3 表述成立
    - t_grad <  t_func（27/27）     → K4 翻转              → 改写 A3

【入口（不训练，纯读 csv）】
    python G_sensitivity.py --run_id G1   # 分析 G1（全塌档）
    python G_sensitivity.py --run_id G3   # 分析 G3（临界档，最干净）
    python G_sensitivity.py --all         # 读 G1/G2/G3 全部

【输出】
    results/G_sensitivity_<run_id>.csv：P_g, P_f, N, run_id, ur, clip, seed,
                                        t_grad_die, t_func_die, sign_delta
    results/G_sensitivity_summary.json：27×run 矩阵 + 全稳判定
"""

import os
import sys
import csv
import json
import math
import argparse
import itertools
import numpy as np

THIS_DIR    = os.environ.get('PHASEMAP_OUT',
                             os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(THIS_DIR, "results")

# 27 组参数网格（冻结，🟡-4）
P_G_GRID = [10, 20, 30]       # grad_norm 百分位阈
P_F_GRID = [1,  2,  5]        # dice_proxy 百分位阈（功能崩）
N_GRID   = [3,  5,  10]       # 连续步数确认


# ─── 读 traj csv ────────────────────────────────────────────────────
def load_traj_csv(path: str) -> dict:
    """
    读 G_traj_*.csv，返回 {(run_id,ur,clip,seed): list_of_step_dicts}。
    每行已有 run_id/ur/clip_norm/seed/step/grad_norm_mean/dice_proxy/diverged。
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"traj csv 不存在: {path}")

    runs = {}
    with open(path, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (row['run_id'], row['ur'], row['clip_norm'], row['seed'])
            if key not in runs:
                runs[key] = []
            runs[key].append({
                'step':           int(row['step']),
                'grad_norm_mean': _to_float(row.get('grad_norm_mean', 'nan')),
                'dice_proxy':     _to_float(row.get('dice_proxy', 'nan')),
                'diverged':       int(row.get('diverged', 0)),
            })

    # 按 step 排序
    for key in runs:
        runs[key].sort(key=lambda r: r['step'])

    return runs


def _to_float(s):
    try:
        v = float(s)
        return float('nan') if math.isnan(v) else v
    except (ValueError, TypeError):
        return float('nan')


# ─── 计算 t_grad_die / t_func_die ───────────────────────────────────
def compute_death_times(steps: list, p_g: int, p_f: int, N: int):
    """
    steps: 排序后的 step 行列表（含 grad_norm_mean / dice_proxy）
    返回 (t_grad_die, t_func_die)，int 或 inf。
    """
    grad_vals = [r['grad_norm_mean'] for r in steps]
    dice_vals = [r['dice_proxy']     for r in steps]

    # 去 NaN
    gv_valid = [v for v in grad_vals if not math.isnan(v)]
    dv_valid = [v for v in dice_vals if not math.isnan(v)]

    if len(gv_valid) == 0 or len(dv_valid) == 0:
        return float('inf'), float('inf')

    g_thresh = float(np.percentile(gv_valid, p_g))   # 低百分位 = 梯度"死"阈
    f_thresh = float(np.percentile(dv_valid, p_f))   # 低百分位 = 功能"死"阈

    def _first_sustain(series, threshold, N_confirm, below=True):
        """找第一个连续 N 步 series <= threshold（below=True）的起始 step。
        使用 <= 而非 <，因为 percentile 阈恰好等于序列值时应计入死亡。
        """
        n = len(series)
        for i in range(n - N_confirm + 1):
            window = series[i:i + N_confirm]
            if below:
                if all((not math.isnan(v)) and v <= threshold for v in window):
                    return i
            else:
                if all((not math.isnan(v)) and v >= threshold for v in window):
                    return i
        return float('inf')

    t_grad = _first_sustain(grad_vals, g_thresh, N, below=True)
    t_func = _first_sustain(dice_vals, f_thresh, N, below=True)

    return t_grad, t_func


# ─── 分析单个 run（一组参数）────────────────────────────────────────
def analyze_run(key_str, steps, p_g, p_f, N):
    run_id, ur, clip, seed = key_str

    # 跳过全存活（dice 始终高）run——没有"功能死"事件，t_func=inf，sign 无意义
    dice_vals = [r['dice_proxy'] for r in steps if not math.isnan(r['dice_proxy'])]
    if not dice_vals:
        return None

    t_grad, t_func = compute_death_times(steps, p_g, p_f, N)

    if math.isinf(t_grad) and math.isinf(t_func):
        sign_delta = 0  # 两者都不死，不可分辨
    elif math.isinf(t_func):
        sign_delta = 0  # 功能不死，skip
    elif math.isinf(t_grad):
        sign_delta = 1  # 梯度不死但功能死 → t_grad > t_func（梯度未先死）
    else:
        diff = t_grad - t_func
        sign_delta = int(np.sign(diff))

    return {
        'P_g':         p_g,
        'P_f':         p_f,
        'N':           N,
        'run_id':      run_id,
        'ur':          ur,
        'clip_norm':   clip,
        'seed':        seed,
        't_grad_die':  t_grad  if not math.isinf(t_grad)  else 'inf',
        't_func_die':  t_func  if not math.isinf(t_func)  else 'inf',
        'sign_delta':  sign_delta,   # >0 功能先崩（A3支柱2方向），<0 梯度先死（K4方向）
    }


# ─── 主分析 ─────────────────────────────────────────────────────────
def run_sensitivity(run_ids: list):
    """对所有指定 run_id 的 traj csv 跑 27 组敏感性分析。"""
    all_rows  = []
    col_order = ['P_g', 'P_f', 'N', 'run_id', 'ur', 'clip_norm', 'seed',
                 't_grad_die', 't_func_die', 'sign_delta']

    for rid in run_ids:
        traj_path = os.path.join(RESULTS_DIR, f"G_traj_{rid.lower()}.csv")
        try:
            run_data = load_traj_csv(traj_path)
        except FileNotFoundError as e:
            print(f"[G_sens] 跳过 {rid}：{e}", flush=True)
            continue

        print(f"[G_sens] {rid}  run数={len(run_data)}", flush=True)

        for (p_g, p_f, N) in itertools.product(P_G_GRID, P_F_GRID, N_GRID):
            for key, steps in run_data.items():
                res = analyze_run(key, steps, p_g, p_f, N)
                if res is not None:
                    all_rows.append(res)

        # 写单 run 敏感性 csv
        out_csv = os.path.join(RESULTS_DIR, f"G_sensitivity_{rid}.csv")
        rows_rid = [r for r in all_rows if r['run_id'] == rid]
        with open(out_csv, 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=col_order, extrasaction='ignore')
            w.writeheader()
            w.writerows(rows_rid)
        print(f"[G_sens] {rid} -> {out_csv}  ({len(rows_rid)} 行)", flush=True)

    # ── 全稳判定 ───────────────────────────────────────────────────
    signs = [r['sign_delta'] for r in all_rows]
    n_pos  = sum(1 for s in signs if s > 0)
    n_neg  = sum(1 for s in signs if s < 0)
    n_zero = sum(1 for s in signs if s == 0)
    total  = len(signs)

    all_same_sign = (n_neg == 0 and n_zero == 0) or (n_pos == 0 and n_zero == 0)
    a3_upgrade    = all_same_sign and n_pos > 0   # 全 >0 → 功能先崩 → A3 方向稳

    verdict = "STABLE_A3" if (all_same_sign and n_pos > 0) \
         else "STABLE_K4" if (all_same_sign and n_neg > 0) \
         else "UNSTABLE"

    summary = {
        "verdict":       verdict,
        "a3_upgrade":    a3_upgrade,
        "total_checks":  total,
        "n_pos":         n_pos,
        "n_neg":         n_neg,
        "n_zero":        n_zero,
        "interpretation": (
            "全>0: 功能先崩/梯度未先死 → 升级 A3 因果 (支柱2 成立)" if verdict == "STABLE_A3"
            else "全<0: 梯度先死 → K4 翻转 A3，改写 claim" if verdict == "STABLE_K4"
            else "有翻号: 时序不可分辨，维持相关性，不升级因果"
        ),
        "note": (
            "P_g×P_f×N 27组 × run数 = 全稳才升级。"
            "sign=0 = 两者同时或某事件未发生，按保守计入 UNSTABLE 区分。"
        ),
    }

    summary_path = os.path.join(RESULTS_DIR, "G_sensitivity_summary.json")
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2)

    print(f"\n{'='*60}", flush=True)
    print(f"[G_sens] VERDICT = {verdict}", flush=True)
    print(f"  n_pos={n_pos}  n_neg={n_neg}  n_zero={n_zero}  total={total}", flush=True)
    print(f"  {summary['interpretation']}", flush=True)
    print(f"  summary -> {summary_path}", flush=True)
    print(f"{'='*60}", flush=True)

    return summary


# ─── CLI ─────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="G 阈值敏感性后处理（27 组 P_g×P_f×N）")
    parser.add_argument('--run_id', choices=['G1', 'G2', 'G3'],
                        help='处理单个 run_id；与 --all 二选一')
    parser.add_argument('--all', action='store_true',
                        help='处理 G1+G2+G3 全部')
    args = parser.parse_args()

    if args.all:
        run_ids = ['G1', 'G2', 'G3']
    elif args.run_id:
        run_ids = [args.run_id]
    else:
        parser.error("需要 --run_id 或 --all")

    run_sensitivity(run_ids)


if __name__ == '__main__':
    main()
