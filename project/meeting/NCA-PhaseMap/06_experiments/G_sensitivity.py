"""G 阈值敏感性后处理 — NCA-PhaseMap Gate1 腿② 🟡-4
兼容：补2 机制段·臂1 σ/d 各 27 组先驱符号检验

=== 旧功能（grad 先驱，保持兼容）===
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

【输出（grad 旧功能）】
    results/G_sensitivity_<run_id>.csv：P_g, P_f, N, run_id, ur, clip, seed,
                                        t_grad_die, t_func_die, sign_delta
    results/G_sensitivity_summary.json：27×run 矩阵 + 全稳判定

=== 新功能（机制量先驱符号检验，--mech 模式）===
读 G_mech_traj_*.csv（臂1 产出），对 σ_t 和 dfront_t 各跑 27 组符号检验。

【符号方向（物理正确，各量独立定）】
    σ(t) 趋塌缩 = 降（↓），t_sigma_drop = 首次连续 N 步跌破低百分位阈（与 grad 同向）
    d(t) 趋塌缩 = 升（↑），t_d_rise    = 首次连续 N 步超过高百分位阈（反向！）

    sign_delta_sigma = sign(t_sigma_drop − t_func_die)
        >0 → σ 在 dice 崩之后才跌（dice 先崩）→ σ 非先驱（同步或果）
        <0 → σ 先跌（σ 先于 dice 崩）        → σ 是先驱 ✓

    sign_delta_d     = sign(t_d_rise − t_func_die)
        <0 → d 在 dice 崩之前就升（d 先驱）  → d 是先驱 ✓
        >0 → d 在 dice 崩之后才升（非先驱）

    🟢 先驱判据：
       σ 先驱：全部 run × 27 组 sign_delta_sigma < 0（σ 比 dice 先跌）
       d 先驱：全部 run × 27 组 sign_delta_d     < 0（d 比 dice 先升）

【27 组参数（复用旧网格，物理含义扩展）】
    P_X ∈ {10%, 20%, 30%}   （σ_t 低百分位阈 / d_t 高百分位阈）
    P_f ∈ {1%, 2%, 5%}      （dice_proxy 低百分位阈，同旧）
    N   ∈ {3, 5, 10}        （连续 N 步确认，同旧）

【入口】
    # 机制量（σ+d 先驱，臂1）
    python G_sensitivity.py --mech --mech_run_id brats_080   （单 run_id）
    python G_sensitivity.py --mech --mech_all                （全 run_id，扫 results/G_mech_traj_*.csv）

【输出（mech 模式）】
    results/G_mech_sensitivity_sigma.csv：P_X, P_f, N, run_id, ur, clip_norm, seed,
                                          t_sigma_drop, t_func_die, sign_delta
    results/G_mech_sensitivity_d.csv：    P_X, P_f, N, run_id, ur, clip_norm, seed,
                                          t_d_rise, t_func_die, sign_delta
    results/G_mech_sensitivity_summary.json：σ/d 各自判定 + 综合 K-new-3 先驱判断
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


# ─── 机制量（σ/d）先驱符号检验（补2 臂1 扩展） ──────────────────────

# 27 组参数复用旧网格（符号方向各量独立定，见模块注释）
P_X_GRID = P_G_GRID   # [10, 20, 30]   百分位
P_F_GRID_MECH = P_F_GRID  # [1, 2, 5]  dice_proxy 低百分位阈（同旧）
N_GRID_MECH   = N_GRID    # [3, 5, 10]  连续步数


def load_mech_traj_csv(path: str) -> dict:
    """
    读 G_mech_traj_*.csv，返回 {(run_id,ur,clip_norm,seed): list_of_step_dicts}。
    列：run_id, dataset, ur, clip_norm, seed, step, dice_proxy, diverged, sigma_t, dfront_t, rho_t
    nan 字符串自动转 float('nan')。
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"mech traj csv 不存在: {path}")

    runs = {}
    with open(path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (row['run_id'], row['ur'], row['clip_norm'], row['seed'])
            if key not in runs:
                runs[key] = []
            runs[key].append({
                'step':       int(row['step']),
                'dice_proxy': _to_float(row.get('dice_proxy', 'nan')),
                'sigma_t':    _to_float(row.get('sigma_t', 'nan')),
                'dfront_t':   _to_float(row.get('dfront_t', 'nan')),
                'diverged':   int(row.get('diverged', 0)),
            })

    for key in runs:
        runs[key].sort(key=lambda r: r['step'])

    return runs


def _first_sustain_below(series, threshold, N_confirm):
    """首次连续 N 步 series <= threshold 的起始 index（σ 趋塌缩=降）。"""
    n = len(series)
    for i in range(n - N_confirm + 1):
        window = series[i:i + N_confirm]
        if all((not math.isnan(v)) and v <= threshold for v in window):
            return i
    return float('inf')


def _first_sustain_above(series, threshold, N_confirm):
    """首次连续 N 步 series >= threshold 的起始 index（d 趋塌缩=升）。"""
    n = len(series)
    for i in range(n - N_confirm + 1):
        window = series[i:i + N_confirm]
        if all((not math.isnan(v)) and v >= threshold for v in window):
            return i
    return float('inf')


def compute_mech_death_times(steps, p_x, p_f, N, mech_col, mech_is_rise):
    """
    计算 t_mech 和 t_func_die。

    mech_col:    步行列名，'sigma_t' 或 'dfront_t'
    mech_is_rise: True → d（趋塌缩=升，检测超高百分位）
                  False → σ（趋塌缩=降，检测跌低百分位）

    返回 (t_mech, t_func_die)。
    """
    mech_vals = [r[mech_col]    for r in steps]
    dice_vals = [r['dice_proxy'] for r in steps]

    mv_valid = [v for v in mech_vals if not math.isnan(v)]
    dv_valid = [v for v in dice_vals if not math.isnan(v)]

    if len(mv_valid) == 0 or len(dv_valid) == 0:
        return float('inf'), float('inf')

    if mech_is_rise:
        # d 趋塌缩=升：检测超过高百分位（p_x = 高端百分位，如 70/80/90）
        # 这里 P_X 复用 [10,20,30] 语义倒置为高端：实际用 100-p_x = [90,80,70]
        m_thresh = float(np.percentile(mv_valid, 100 - p_x))   # 高百分位阈
        t_mech = _first_sustain_above(mech_vals, m_thresh, N)
    else:
        # σ 趋塌缩=降：检测跌破低百分位（同 grad 方向）
        m_thresh = float(np.percentile(mv_valid, p_x))          # 低百分位阈
        t_mech = _first_sustain_below(mech_vals, m_thresh, N)

    f_thresh = float(np.percentile(dv_valid, p_f))
    t_func   = _first_sustain_below(dice_vals, f_thresh, N)

    return t_mech, t_func


def analyze_mech_run(key_str, steps, p_x, p_f, N, mech_col, mech_is_rise):
    """
    分析单个 run 的机制量先驱符号。

    sign_delta = sign(t_mech − t_func_die)

    σ 先驱判断（mech_is_rise=False）：
        sign < 0 → σ 先跌（σ 先于 dice 崩） ✓先驱
        sign > 0 → σ 后跌（非先驱）

    d 先驱判断（mech_is_rise=True）：
        sign < 0 → d 先升（d 先于 dice 崩）  ✓先驱
        sign > 0 → d 后升（非先驱）
    """
    run_id, ur, clip, seed = key_str

    dice_vals = [r['dice_proxy'] for r in steps if not math.isnan(r['dice_proxy'])]
    if not dice_vals:
        return None

    t_mech, t_func = compute_mech_death_times(
        steps, p_x, p_f, N, mech_col, mech_is_rise
    )

    if math.isinf(t_mech) and math.isinf(t_func):
        sign_delta = 0
    elif math.isinf(t_func):
        sign_delta = 0  # dice 不死，无参照
    elif math.isinf(t_mech):
        # 机制量无事件：σ 不跌/d 不升，而 dice 崩了
        # → 机制量事件晚于 dice（量 = inf > t_func），sign > 0 = 非先驱
        sign_delta = 1
    else:
        diff = t_mech - t_func
        sign_delta = int(np.sign(diff))

    return {
        'P_X':          p_x,
        'P_f':          p_f,
        'N':            N,
        'run_id':       run_id,
        'ur':           ur,
        'clip_norm':    clip,
        'seed':         seed,
        't_mech':       t_mech  if not math.isinf(t_mech)  else 'inf',
        't_func_die':   t_func  if not math.isinf(t_func)  else 'inf',
        'sign_delta':   sign_delta,
        # sign_delta < 0 → 机制量先驱（σ 先跌 / d 先升）
    }


def run_mech_sensitivity(mech_run_ids):
    """
    对 G_mech_traj_<run_id>.csv 跑 σ 和 d 各 27 组符号检验。

    mech_run_ids: list of run_id 字符串（如 ['brats_050','brats_065',...]）
    """
    # σ 分析（趋塌缩=降，sign<0 为先驱）
    sigma_rows = []
    # d 分析（趋塌缩=升，sign<0 为先驱）
    d_rows     = []

    sigma_col_order = ['P_X', 'P_f', 'N', 'run_id', 'ur', 'clip_norm', 'seed',
                       't_mech', 't_func_die', 'sign_delta']
    d_col_order     = sigma_col_order  # 同结构

    for rid in mech_run_ids:
        traj_path = os.path.join(RESULTS_DIR, f"G_mech_traj_{rid}.csv")
        try:
            run_data = load_mech_traj_csv(traj_path)
        except FileNotFoundError as e:
            print(f"[G_mech_sens] 跳过 {rid}：{e}", flush=True)
            continue

        print(f"[G_mech_sens] {rid}  run 数={len(run_data)}", flush=True)

        for (p_x, p_f, N) in itertools.product(P_X_GRID, P_F_GRID_MECH, N_GRID_MECH):
            for key, steps in run_data.items():
                # σ（降方向）
                res_s = analyze_mech_run(
                    key, steps, p_x, p_f, N,
                    mech_col='sigma_t', mech_is_rise=False
                )
                if res_s is not None:
                    sigma_rows.append(res_s)

                # d（升方向）
                res_d = analyze_mech_run(
                    key, steps, p_x, p_f, N,
                    mech_col='dfront_t', mech_is_rise=True
                )
                if res_d is not None:
                    d_rows.append(res_d)

    # 写 σ csv
    sigma_csv = os.path.join(RESULTS_DIR, "G_mech_sensitivity_sigma.csv")
    with open(sigma_csv, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=sigma_col_order, extrasaction='ignore')
        w.writeheader()
        w.writerows(sigma_rows)
    print(f"[G_mech_sens] σ csv -> {sigma_csv}  ({len(sigma_rows)} 行)", flush=True)

    # 写 d csv
    d_csv = os.path.join(RESULTS_DIR, "G_mech_sensitivity_d.csv")
    with open(d_csv, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=d_col_order, extrasaction='ignore')
        w.writeheader()
        w.writerows(d_rows)
    print(f"[G_mech_sens] d csv -> {d_csv}  ({len(d_rows)} 行)", flush=True)

    # ── 判定（σ 先驱：全部 sign < 0；d 先驱：全部 sign < 0）────────────
    def _verdict_mech(rows, label):
        """
        先驱判据：全部 sign < 0。
        注：sign < 0 表示机制量事件（σ 跌/d 升）早于 dice 崩。
        """
        signs = [r['sign_delta'] for r in rows]
        n_neg  = sum(1 for s in signs if s < 0)
        n_pos  = sum(1 for s in signs if s > 0)
        n_zero = sum(1 for s in signs if s == 0)
        total  = len(signs)

        all_neg  = (n_pos == 0 and n_zero == 0)
        precedes = all_neg and n_neg > 0

        verdict = "PRECEDES" if precedes \
             else "FOLLOWS"  if (n_neg == 0 and n_zero == 0) \
             else "MIXED"

        interp = {
            "PRECEDES": f"全部 sign<0：{label} 先于 dice 崩 → 先驱成立 ✓",
            "FOLLOWS":  f"全部 sign>0：{label} 晚于 dice 崩 → 非先驱（结果不是原因）",
            "MIXED":    f"有翻号：{label} 时序不可分辨 → 降级为「相关性」",
        }[verdict]

        return {
            "verdict":     verdict,
            "precedes":    precedes,
            "total":       total,
            "n_neg":       n_neg,
            "n_pos":       n_pos,
            "n_zero":      n_zero,
            "interpretation": interp,
        }

    sigma_verdict = _verdict_mech(sigma_rows, "σ")
    d_verdict     = _verdict_mech(d_rows,     "d_front")

    # 综合 K-new-3 先驱判断
    both_precede = sigma_verdict["precedes"] and d_verdict["precedes"]
    either_precede = sigma_verdict["precedes"] or d_verdict["precedes"]
    knew3_verdict = (
        "STRONG_PRECURSOR"   if both_precede   else
        "PARTIAL_PRECURSOR"  if either_precede else
        "NOT_PRECURSOR"
    )

    summary = {
        "sigma": sigma_verdict,
        "d_front": d_verdict,
        "K_new_3_precursor": knew3_verdict,
        "interpretation": {
            "STRONG_PRECURSOR":  "σ+d 均先驱 → K-new-3 机制段强先驱 ✓",
            "PARTIAL_PRECURSOR": "σ 或 d 之一先驱 → 部分先驱，措辞降级",
            "NOT_PRECURSOR":     "σ/d 均非先驱 → K-new-3 降 TMLR",
        }[knew3_verdict],
        "note": (
            "P_X×P_f×N 27 组 × run 数，全稳才判先驱。"
            "σ 方向：降=趋塌缩，sign<0=先驱。"
            "d 方向：升=趋塌缩，sign<0=先驱（P_X 倒置为高百分位）。"
        ),
    }

    summary_path = os.path.join(RESULTS_DIR, "G_mech_sensitivity_summary.json")
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2)

    print(f"\n{'='*60}", flush=True)
    print(f"[G_mech_sens] σ VERDICT = {sigma_verdict['verdict']}", flush=True)
    print(f"  n_neg={sigma_verdict['n_neg']}  n_pos={sigma_verdict['n_pos']}  "
          f"n_zero={sigma_verdict['n_zero']}  total={sigma_verdict['total']}", flush=True)
    print(f"  {sigma_verdict['interpretation']}", flush=True)
    print(f"[G_mech_sens] d VERDICT = {d_verdict['verdict']}", flush=True)
    print(f"  n_neg={d_verdict['n_neg']}  n_pos={d_verdict['n_pos']}  "
          f"n_zero={d_verdict['n_zero']}  total={d_verdict['total']}", flush=True)
    print(f"  {d_verdict['interpretation']}", flush=True)
    print(f"[G_mech_sens] K-new-3 = {knew3_verdict}: {summary['interpretation']}", flush=True)
    print(f"  summary -> {summary_path}", flush=True)
    print(f"{'='*60}", flush=True)

    return summary


# ─── CLI ─────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="G 阈值敏感性后处理（27 组 P_g×P_f×N）+ 机制量先驱检验（--mech）"
    )
    # 旧 grad 参数
    parser.add_argument('--run_id', choices=['G1', 'G2', 'G3'],
                        help='[grad模式] 处理单个 run_id；与 --all 二选一')
    parser.add_argument('--all', action='store_true',
                        help='[grad模式] 处理 G1+G2+G3 全部')

    # 新 mech 参数
    parser.add_argument('--mech', action='store_true',
                        help='[mech模式] 读 G_mech_traj_*.csv，做 σ/d 各 27 组先驱符号检验')
    parser.add_argument('--mech_run_id', type=str, default=None,
                        help='[mech模式] 单个 run_id（如 brats_080）；与 --mech_all 二选一')
    parser.add_argument('--mech_all', action='store_true',
                        help='[mech模式] 扫 results/ 下所有 G_mech_traj_*.csv')

    args = parser.parse_args()

    if args.mech:
        # ── mech 模式：σ/d 先驱符号检验 ───────────────────────────
        if args.mech_all:
            import glob as _glob
            pattern = os.path.join(RESULTS_DIR, "G_mech_traj_*.csv")
            files   = _glob.glob(pattern)
            if not files:
                print(f"[G_mech_sens] 未找到 G_mech_traj_*.csv in {RESULTS_DIR}", flush=True)
                return
            # 从文件名提取 run_id
            mech_run_ids = []
            for fp in files:
                basename = os.path.basename(fp)
                # G_mech_traj_<run_id>.csv
                rid = basename.replace('G_mech_traj_', '').replace('.csv', '')
                mech_run_ids.append(rid)
            mech_run_ids = sorted(set(mech_run_ids))
        elif args.mech_run_id:
            mech_run_ids = [args.mech_run_id]
        else:
            parser.error("[mech模式] 需要 --mech_run_id 或 --mech_all")

        run_mech_sensitivity(mech_run_ids)

    else:
        # ── 旧 grad 模式（保持兼容）────────────────────────────────
        if args.all:
            run_ids = ['G1', 'G2', 'G3']
        elif args.run_id:
            run_ids = [args.run_id]
        else:
            parser.error("[grad模式] 需要 --run_id 或 --all；机制量先驱检验用 --mech")

        run_sensitivity(run_ids)


if __name__ == '__main__':
    main()
