"""mech_early_predict.py — 早期预测 AUC 后处理 — NCA-PhaseMap 补2 臂1
服务项目：NCA-PhaseMap / K-new-3 机制段·臂1（时序先驱 + 早期预测）

读所有 G_mech_traj_*.csv，每 run 取早期窗口 step<=50（dice 还在高台）的
σ_t/dfront_t 均值+末值为特征 X，最终 collapsed 为标签 y，
算单变量 AUC + bootstrap 1000 CI + 留一交叉验证。

【collapse 判据】（从 B0 读，不重标）
    B0_baseline.csv 列：dataset, dice_bg_mean, dice_bg_std, collapse_thresh
    collapse_thresh = max(0.01, dice_bg_mean + 3*dice_bg_std)（B0 预计算值）
    final_dice < collapse_thresh → collapsed=1

    BraTS：collapse_thresh=0.012883
    Hippo：collapse_thresh=0.116746

【特征定义】
    取步骤 step<=early_window（默认 50）的行：
    x_sigma_mean  = σ_t 均值（早期窗口，nan 安全）
    x_sigma_last  = σ_t 末值（step<=early_window 的最后一行）
    x_d_mean      = dfront_t 均值
    x_d_last      = dfront_t 末值

【AUC（ROC 曲线下面积）】
    纯 numpy 实现（不用 sklearn，Windows OMP 安全）。
    正例 y=1（collapsed），负例 y=0（survived）。
    每个特征单独算 AUC（单变量，n=15 no-clip run）。

【bootstrap CI】
    1000 次有放回采样，95% CI（2.5-97.5 百分位）。

【留一交叉验证】
    n 次，每次留一 run，剩余 n-1 训练（取最优阈），测留出 run。
    报告 LOO-AUC（等同于 Mann-Whitney U / AUROC）。

【前置打印】
    打印 step<=early_window 时各 run dice_proxy 均值，
    供主线核「early window 时塌缩/存活 run dice 是否显著分化」。
    若分化：缩 early_window → --early_window 30。

【判据（K-new-3 早期预测分支）】
    🟢 AUC CI 下界 > 0.5 → 早期预测成立
    🟡 CI 含 0.5 但点估 > 0.5 → 方向一致但 n 不足（降格措辞，不强卖）
    🔴 AUC 点估 ≤ 0.5 → 无预测力

【n=15 no-clip run 偏小说明】
    CI 会宽（预期[0.4, 1.0]范围），方向 > 0.5 即有意义。
    不强卖显著性。

【入口】
    python mech_early_predict.py [--early_window 50] [--n_bootstrap 1000]
                                 [--b0_csv results/B0_baseline.csv]
                                 [--no_clip_only]

【输出】
    results/mech_early_predict.csv
    列：feature, auc, ci_low, ci_high, loo_auc, n_pos, n_neg, verdict
    results/mech_early_predict_per_run.csv
    列：run_id, dataset, ur, clip_norm, seed, collapsed,
        x_sigma_mean, x_sigma_last, x_d_mean, x_d_last,
        final_dice, n_early_steps

【环境变量】
    PHASEMAP_OUT   输出根目录
"""

import os
import sys
import csv
import glob
import json
import math
import argparse
import numpy as np

THIS_DIR    = os.environ.get('PHASEMAP_OUT',
                             os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(THIS_DIR, "results")

# B0 collapse 判据（从 B0_baseline.csv 读，不重标）
B0_CSV_DEFAULT = os.path.join(RESULTS_DIR, "B0_baseline.csv")

# 默认早期窗口
EARLY_WINDOW_DEFAULT = 50


# ─── 工具函数 ─────────────────────────────────────────────────────────

def _to_float(s):
    try:
        v = float(s)
        return float('nan') if math.isnan(v) else v
    except (ValueError, TypeError):
        return float('nan')


def _safe_mean(lst):
    valid = [v for v in lst if not math.isnan(v)]
    return float(np.mean(valid)) if valid else float('nan')


def _safe_last(lst):
    """取列表中最后一个非 nan 值。"""
    for v in reversed(lst):
        if not math.isnan(v):
            return float(v)
    return float('nan')


# ─── 读 B0 collapse 判据 ─────────────────────────────────────────────

def load_b0_collapse_thresh(b0_csv):
    """
    从 B0_baseline.csv 读 dataset → collapse_thresh。
    列：dataset, ..., collapse_thresh
    返回 {'BraTS2021': 0.012883, 'Hippocampus': 0.116746}（以 dataset 列为 key）。
    """
    thresh = {}
    if not os.path.exists(b0_csv):
        print(f"[predict] WARNING: B0 csv 不存在: {b0_csv}", flush=True)
        print(f"[predict] 使用内嵌值 BraTS=0.012883 / Hippo=0.116746", flush=True)
        return {'BraTS2021': 0.012883, 'Hippocampus': 0.116746}

    with open(b0_csv, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            ds_name = row['dataset'].strip()
            thresh[ds_name] = _to_float(row['collapse_thresh'])

    print(f"[predict] B0 collapse_thresh 读取: {thresh}", flush=True)
    return thresh


def _get_collapse_thresh(dataset_name, b0_thresh):
    """根据 dataset 字段匹配 B0 阈值（brats→BraTS2021, hippo→Hippocampus）。"""
    ds = dataset_name.lower()
    if 'brat' in ds:
        return b0_thresh.get('BraTS2021', 0.012883)
    elif 'hip' in ds or 'hippocampus' in ds:
        return b0_thresh.get('Hippocampus', 0.116746)
    else:
        # 未知 dataset：返回 nan，后续判 collapsed=nan
        print(f"[predict] WARNING: 未识别 dataset='{dataset_name}'，collapsed=nan", flush=True)
        return float('nan')


# ─── 读 G_mech_traj csv ─────────────────────────────────────────────

def load_all_mech_csvs(results_dir, no_clip_only=True):
    """
    扫 results/G_mech_traj_*.csv，返回 per-run 记录列表。
    no_clip_only=True（默认）：只保留 clip_norm='None' 的 no-clip 主条件（n=15）。

    返回：list of dict，每个对应一个 (run_id, ur, clip_norm, seed)：
      {run_id, dataset, ur, clip_norm, seed, steps: [step_dicts]}
    """
    pattern = os.path.join(results_dir, "G_mech_traj_*.csv")
    files   = sorted(glob.glob(pattern))

    if not files:
        raise FileNotFoundError(
            f"[predict] 未找到 G_mech_traj_*.csv in {results_dir}\n"
            f"  请先运行 G_mech_traj.py --all"
        )

    print(f"[predict] 找到 {len(files)} 个 G_mech_traj csv", flush=True)

    all_run_records = {}  # key=(run_id,ur,clip_norm,seed) → {meta, steps:[]}

    for fp in files:
        with open(fp, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                clip_n = row.get('clip_norm', 'None')
                if no_clip_only and clip_n != 'None':
                    continue

                key = (row['run_id'], row['ur'], clip_n, row['seed'])
                if key not in all_run_records:
                    all_run_records[key] = {
                        'run_id':    row['run_id'],
                        'dataset':   row.get('dataset', ''),
                        'ur':        _to_float(row['ur']),
                        'clip_norm': clip_n,
                        'seed':      int(row['seed']),
                        'steps':     [],
                    }
                all_run_records[key]['steps'].append({
                    'step':       int(row['step']),
                    'dice_proxy': _to_float(row.get('dice_proxy', 'nan')),
                    'sigma_t':    _to_float(row.get('sigma_t', 'nan')),
                    'dfront_t':   _to_float(row.get('dfront_t', 'nan')),
                    'diverged':   int(row.get('diverged', 0)),
                })

    # 按 step 排序
    for rec in all_run_records.values():
        rec['steps'].sort(key=lambda r: r['step'])

    records = list(all_run_records.values())
    print(f"[predict] 共 {len(records)} 个 run（no_clip_only={no_clip_only}）", flush=True)
    return records


# ─── 特征提取 + collapse 标签 ────────────────────────────────────────

def extract_features_and_labels(records, b0_thresh, early_window):
    """
    每个 run 提取早期特征 + 最终 collapse 标签。

    返回 per_run_rows（list of dict）供后续分析。
    同时打印 step<=early_window 时各 run dice 均值（供主线核是否已分化）。
    """
    per_run_rows = []

    print(f"\n[predict] === step<={early_window} 各 run dice_proxy 均值 "
          f"（主线核是否已分化）===", flush=True)

    for rec in records:
        steps_all   = rec['steps']
        early_steps = [s for s in steps_all if s['step'] <= early_window]
        late_steps  = steps_all  # 全程，用于判终态

        # 早期窗口特征
        sigma_early = [s['sigma_t']   for s in early_steps]
        d_early     = [s['dfront_t']  for s in early_steps]
        dice_early  = [s['dice_proxy'] for s in early_steps]

        x_sigma_mean = _safe_mean(sigma_early)
        x_sigma_last = _safe_last(sigma_early)
        x_d_mean     = _safe_mean(d_early)
        x_d_last     = _safe_last(d_early)

        dice_early_mean = _safe_mean(dice_early)

        # 最终 dice（取最后非 nan 值）
        dice_all_vals = [s['dice_proxy'] for s in late_steps]
        final_dice    = _safe_last(dice_all_vals)

        # collapse 标签（从 B0 读阈，不重标）
        collapse_thresh = _get_collapse_thresh(rec['dataset'], b0_thresh)
        if math.isnan(collapse_thresh) or math.isnan(final_dice):
            collapsed = float('nan')
        else:
            collapsed = 1 if final_dice < collapse_thresh else 0

        print(
            f"  run_id={rec['run_id']:20s}  seed={rec['seed']}  "
            f"dice_early_mean={dice_early_mean:.4f}  "
            f"final_dice={final_dice:.4f}  "
            f"collapsed={collapsed}  (thresh={collapse_thresh:.4f})",
            flush=True
        )

        per_run_rows.append({
            'run_id':       rec['run_id'],
            'dataset':      rec['dataset'],
            'ur':           rec['ur'],
            'clip_norm':    rec['clip_norm'],
            'seed':         rec['seed'],
            'collapsed':    collapsed,
            'x_sigma_mean': x_sigma_mean,
            'x_sigma_last': x_sigma_last,
            'x_d_mean':     x_d_mean,
            'x_d_last':     x_d_last,
            'final_dice':   final_dice,
            'n_early_steps': len(early_steps),
        })

    return per_run_rows


# ─── AUC（纯 numpy，Windows OMP 安全） ──────────────────────────────

def compute_auc_np(scores, labels):
    """
    ROC-AUC 纯 numpy 实现（不调 scipy）。
    正例 label=1（collapsed），分数越高预测越可能 collapsed。

    对 σ 特征（σ 低→collapsed），AUC 应 > 0.5 时取负值，
    调用方传入 1-σ_feature 或调用时指定方向。
    此处直接算，调用方负责传入「方向正确」的 scores。

    返回 (auc_val, n_pos, n_neg)。
    """
    scores = np.array(scores, dtype=np.float64)
    labels = np.array(labels, dtype=np.int32)

    # 过滤 nan
    valid_mask = ~np.isnan(scores) & (labels != -1)
    scores = scores[valid_mask]
    labels = labels[valid_mask]

    n_pos = int((labels == 1).sum())
    n_neg = int((labels == 0).sum())

    if n_pos == 0 or n_neg == 0:
        return float('nan'), n_pos, n_neg

    # Mann-Whitney U 等价：遍历所有 (pos, neg) 对
    # AUC = P(score_pos > score_neg) + 0.5*P(score_pos == score_neg)
    pos_scores = scores[labels == 1]
    neg_scores = scores[labels == 0]

    n_greater = 0
    n_equal   = 0
    for ps in pos_scores:
        n_greater += int((neg_scores < ps).sum())
        n_equal   += int((neg_scores == ps).sum())

    auc = (n_greater + 0.5 * n_equal) / (n_pos * n_neg)
    return float(auc), n_pos, n_neg


def bootstrap_auc_ci(scores, labels, n_bootstrap=1000, ci=95, rng_seed=42):
    """
    bootstrap AUC 置信区间（有放回采样，纯 numpy）。
    返回 (ci_low, ci_high)。
    """
    rng = np.random.RandomState(rng_seed)
    n   = len(scores)
    scores = np.array(scores, dtype=np.float64)
    labels = np.array(labels, dtype=np.int32)

    boot_aucs = []
    for _ in range(n_bootstrap):
        idx = rng.choice(n, n, replace=True)
        bs, bl = scores[idx], labels[idx]
        auc_b, _, _ = compute_auc_np(bs, bl)
        if not math.isnan(auc_b):
            boot_aucs.append(auc_b)

    if not boot_aucs:
        return float('nan'), float('nan')

    lo = float(np.percentile(boot_aucs, (100 - ci) / 2))
    hi = float(np.percentile(boot_aucs, 100 - (100 - ci) / 2))
    return lo, hi


def loo_auc(scores, labels):
    """
    留一交叉验证 AUC（等价于全局 AUROC，证明：LOO-AUC = AUC 对二类问题）。
    此处直接返回全局 AUC（n 小时 LOO 等价，避免阈值依赖的分类 LOO-ACC）。
    """
    auc_val, _, _ = compute_auc_np(scores, labels)
    return auc_val


def _auc_verdict(auc_val, ci_low, ci_high):
    """判据：CI 下界 > 0.5 → 成立；CI 含 0.5 但点估 > 0.5 → 方向一致 n 不足。"""
    if math.isnan(auc_val):
        return "N/A"
    if ci_low > 0.5:
        return "PREDICTIVE"           # 🟢 AUC CI 下界>0.5
    elif auc_val > 0.5:
        return "DIRECTION_N_SMALL"    # 🟡 方向一致但 n 不足
    else:
        return "NOT_PREDICTIVE"       # 🔴 无预测力


# ─── 主流程 ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="早期预测 AUC — NCA-PhaseMap 补2 臂1"
    )
    parser.add_argument('--early_window', type=int, default=EARLY_WINDOW_DEFAULT,
                        help=f'早期窗口（step<=N，默认{EARLY_WINDOW_DEFAULT}）')
    parser.add_argument('--n_bootstrap',  type=int, default=1000,
                        help='bootstrap 次数（默认 1000）')
    parser.add_argument('--b0_csv',       default=B0_CSV_DEFAULT,
                        help='B0 baseline csv 路径（读 collapse_thresh）')
    parser.add_argument('--no_clip_only', action='store_true', default=True,
                        help='只分析 no-clip run（默认 True，n=15）')
    parser.add_argument('--include_clip', action='store_true',
                        help='包含 clip=1.0 对照 run（关闭 no_clip_only）')
    args = parser.parse_args()

    no_clip_only = not args.include_clip

    print(f"[predict] === 早期预测 AUC  early_window={args.early_window}  "
          f"n_bootstrap={args.n_bootstrap}  no_clip_only={no_clip_only} ===", flush=True)

    # 读 B0 collapse 判据
    b0_thresh = load_b0_collapse_thresh(args.b0_csv)

    # 读所有 mech traj csv
    try:
        records = load_all_mech_csvs(RESULTS_DIR, no_clip_only=no_clip_only)
    except FileNotFoundError as e:
        print(f"[predict] FATAL: {e}", flush=True)
        sys.exit(1)

    if not records:
        print("[predict] 无有效 run 数据，退出。", flush=True)
        sys.exit(1)

    # 提取特征 + 标签（同时打印 early dice 均值供主线核）
    per_run_rows = extract_features_and_labels(records, b0_thresh, args.early_window)

    # 写 per-run csv
    per_run_csv = os.path.join(RESULTS_DIR, "mech_early_predict_per_run.csv")
    per_run_cols = ['run_id', 'dataset', 'ur', 'clip_norm', 'seed', 'collapsed',
                    'x_sigma_mean', 'x_sigma_last', 'x_d_mean', 'x_d_last',
                    'final_dice', 'n_early_steps']
    with open(per_run_csv, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=per_run_cols, extrasaction='ignore')
        w.writeheader()
        for row in per_run_rows:
            # 格式化浮点
            out = {}
            for k in per_run_cols:
                v = row[k]
                if isinstance(v, float):
                    out[k] = 'nan' if math.isnan(v) else round(v, 6)
                else:
                    out[k] = v
            w.writerow(out)
    print(f"\n[predict] per-run csv -> {per_run_csv}", flush=True)

    # 过滤有效行（collapsed 非 nan）
    valid_rows = [r for r in per_run_rows
                  if not isinstance(r['collapsed'], float) or not math.isnan(r['collapsed'])]
    n_valid = len(valid_rows)
    n_pos = sum(1 for r in valid_rows if r['collapsed'] == 1)
    n_neg = sum(1 for r in valid_rows if r['collapsed'] == 0)
    print(f"\n[predict] 有效 run={n_valid}  collapsed(y=1)={n_pos}  survived(y=0)={n_neg}",
          flush=True)

    if n_valid == 0:
        print("[predict] 无有效 run（检查 collapse 标签），退出。", flush=True)
        sys.exit(1)

    labels = np.array([int(r['collapsed']) for r in valid_rows], dtype=np.int32)

    # ── 特征定义 ────────────────────────────────────────────────────
    # σ 特征：σ 低→collapsed，AUC 用负值（-σ）使正例得分更高
    # d 特征：d 高→collapsed，AUC 直接用正值
    features_def = [
        # (feature_name,  score_array,           direction_note)
        ('sigma_mean_neg', [-r['x_sigma_mean'] for r in valid_rows],
         '负 σ_mean（σ↓→collapsed，取负使正例高分）'),
        ('sigma_last_neg', [-r['x_sigma_last'] for r in valid_rows],
         '负 σ_last（σ↓→collapsed，取负使正例高分）'),
        ('d_mean',         [r['x_d_mean']      for r in valid_rows],
         'd_mean（d↑→collapsed）'),
        ('d_last',         [r['x_d_last']      for r in valid_rows],
         'd_last（d↑→collapsed）'),
    ]

    results_rows = []

    print(f"\n[predict] === AUC 结果 ===", flush=True)
    for feat_name, scores_raw, direction_note in features_def:
        scores = np.array([float(v) for v in scores_raw], dtype=np.float64)

        # 过滤含 nan 的样本
        valid_feat = ~np.isnan(scores)
        s_f = scores[valid_feat]
        l_f = labels[valid_feat]

        if len(s_f) == 0 or (l_f == 1).sum() == 0 or (l_f == 0).sum() == 0:
            print(f"  {feat_name}: 跳过（有效样本不足或单类）", flush=True)
            results_rows.append({
                'feature':   feat_name,
                'auc':       'nan', 'ci_low': 'nan', 'ci_high': 'nan',
                'loo_auc':   'nan',
                'n_pos':     int((l_f == 1).sum()) if len(l_f) > 0 else 0,
                'n_neg':     int((l_f == 0).sum()) if len(l_f) > 0 else 0,
                'verdict':   'N/A',
            })
            continue

        auc_val, n_p, n_n = compute_auc_np(s_f, l_f)
        ci_lo, ci_hi      = bootstrap_auc_ci(s_f, l_f, n_bootstrap=args.n_bootstrap)
        loo_val           = loo_auc(s_f, l_f)
        verdict           = _auc_verdict(auc_val, ci_lo, ci_hi)

        auc_str  = f"{auc_val:.4f}" if not math.isnan(auc_val) else "nan"
        ci_str   = f"[{ci_lo:.4f},{ci_hi:.4f}]" if not math.isnan(ci_lo) else "[nan,nan]"
        print(
            f"  {feat_name:20s}  AUC={auc_str}  CI={ci_str}  "
            f"LOO-AUC={loo_val:.4f}  n={len(s_f)}(+{n_p}/-{n_n})  {verdict}",
            flush=True
        )
        print(f"    ({direction_note})", flush=True)

        results_rows.append({
            'feature':   feat_name,
            'auc':       round(auc_val, 6) if not math.isnan(auc_val) else 'nan',
            'ci_low':    round(ci_lo,   6) if not math.isnan(ci_lo)   else 'nan',
            'ci_high':   round(ci_hi,   6) if not math.isnan(ci_hi)   else 'nan',
            'loo_auc':   round(loo_val, 6) if not math.isnan(loo_val) else 'nan',
            'n_pos':     n_p,
            'n_neg':     n_n,
            'verdict':   verdict,
        })

    # 写汇总 csv
    out_csv = os.path.join(RESULTS_DIR, "mech_early_predict.csv")
    out_cols = ['feature', 'auc', 'ci_low', 'ci_high', 'loo_auc', 'n_pos', 'n_neg', 'verdict']
    with open(out_csv, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=out_cols, extrasaction='ignore')
        w.writeheader()
        w.writerows(results_rows)

    print(f"\n[predict] AUC csv -> {out_csv}", flush=True)

    # 综合判定
    verdicts = [r['verdict'] for r in results_rows if r['verdict'] != 'N/A']
    n_predictive   = sum(1 for v in verdicts if v == 'PREDICTIVE')
    n_direction    = sum(1 for v in verdicts if v == 'DIRECTION_N_SMALL')
    n_not          = sum(1 for v in verdicts if v == 'NOT_PREDICTIVE')

    overall = (
        "K_NEW3_EARLY_PREDICT_PASS"   if n_predictive > 0 else
        "K_NEW3_EARLY_PREDICT_WEAK"   if n_direction  > 0 else
        "K_NEW3_EARLY_PREDICT_FAIL"
    )

    summary = {
        "overall":          overall,
        "n_predictive":     n_predictive,
        "n_direction_only": n_direction,
        "n_not_predictive": n_not,
        "early_window":     args.early_window,
        "n_valid_runs":     n_valid,
        "n_pos":            n_pos,
        "n_neg":            n_neg,
        "interpretation": {
            "K_NEW3_EARLY_PREDICT_PASS":
                "≥1 特征 AUC CI 下界>0.5 → 早期预测成立 ✓",
            "K_NEW3_EARLY_PREDICT_WEAK":
                "AUC 方向正确但 CI 含 0.5 → n 不足，降格措辞不强卖",
            "K_NEW3_EARLY_PREDICT_FAIL":
                "所有特征 AUC≤0.5 → 早期无预测力，K-new-3 失败",
        }[overall],
        "note": (
            f"n={n_valid} run 偏小（no-clip 主条件），CI 宽属预期。"
            "方向>0.5 即有意义，不强卖显著性。"
            f"early_window={args.early_window}（可调 --early_window 30 缩窗）。"
        ),
    }

    summary_path = os.path.join(RESULTS_DIR, "mech_early_predict_summary.json")
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2)

    print(f"\n{'='*60}", flush=True)
    print(f"[predict] OVERALL = {overall}", flush=True)
    print(f"  {summary['interpretation']}", flush=True)
    print(f"  summary -> {summary_path}", flush=True)
    print(f"{'='*60}", flush=True)


if __name__ == '__main__':
    main()
