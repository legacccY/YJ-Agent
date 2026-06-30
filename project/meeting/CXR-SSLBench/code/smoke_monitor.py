# -*- coding: utf-8 -*-
"""
Collapse / loss-sanity 烟测监控 —— 矩阵 §2 健康判据 gate（投全预算前强制）。

职责（INTERFACE §4 + 矩阵 §2）：
  1. 纯 numpy 监控量（**禁 scipy**，OMP #15 红线）：DINO teacher 熵/KL-to-uniform/特征 std；
     MoCo 对比 loss vs ln(batch)/特征 std/梯度范数/dip；MAE+CheX loss-sanity（平台/无发散）。
  2. MonitorWriter：每 50-100 步 append `results/smoke_<method>.csv` + 写 `results/state_<run>.json` 心跳。
  3. evaluate_gate：按预登记判据判 PASS/FAIL/INCOMPLETE（缺 collapse-critical 量时**不给假 PASS**）。
  4. `--tail` 模式：解析官方训练 stdout 日志抽 loss/grad_norm（官方不 emit 熵/std → 标 missing，gate 报 INCOMPLETE）。

⚠️ DINO 熵 / 特征 std 需训练内部 teacher softmax / 特征 → 官方 main_dino 不 emit。
   compute_dino_metrics 已就绪；wiring（在官方 loop 调 monitor.log_step 灌入）是集成点，主线烟测时挂 hook。
   若 CSV 缺这些列，gate 对 DINO 返回 INCOMPLETE（强制主线补 hook，不放行假 PASS）。
"""
import argparse
import csv
import math
import os
import re
import sys
import time

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, 'pretrain'))
from common import write_state  # noqa: E402  (复用 pretrain/common 的原子 state.json 写)

LN = math.log

# ---- 预登记健康判据常量（矩阵 §2，冻结于此）----
DINO_OUT_DIM = 65536
DINO_ENT_LO_FRAC, DINO_ENT_HI_FRAC = 0.3, 0.95   # 熵 ∈ (0.3,0.95)×ln(out_dim)
FEAT_STD_MIN = 0.01                               # 特征 std 下限（DINO/MoCo 共用）
LOSS_DIVERGE_TOL = 0.10                           # loss 末窗均值 > 首窗均值×(1+tol) 判发散


# ===========================================================================
# 纯 numpy 监控量
# ===========================================================================
def teacher_entropy(probs):
    """probs:[N,D] teacher softmax 输出 -> 平均熵（nats）。collapse-to-uniform→ln(D)，collapse-to-onehot→0。"""
    p = np.asarray(probs, dtype=np.float64)
    p = np.clip(p, 1e-12, 1.0)
    ent = -(p * np.log(p)).sum(axis=-1)           # 每样本熵
    return float(ent.mean())


def kl_to_uniform(probs, out_dim=None):
    """KL(p || uniform) = ln(D) - entropy。→0 = 塌成均匀；→ln(D) = 塌成 one-hot。"""
    p = np.asarray(probs, dtype=np.float64)
    D = out_dim or p.shape[-1]
    return float(LN(D) - teacher_entropy(p))


def feature_std(feats):
    """feats:[N,Dim] -> 跨样本 std 的均值（每维 std 再平均）。塌缩 → →0。"""
    f = np.asarray(feats, dtype=np.float64)
    return float(f.std(axis=0).mean())


def contrastive_baseline(batch):
    """InfoNCE 随机基线 = ln(batch)。MoCo 健康 = loss 应 < ln(batch)（不卡此平台）。"""
    return float(LN(batch))


def grad_norm_ok(g):
    return bool(np.isfinite(g)) and g >= 0.0


def loss_diverged(losses, tol=LOSS_DIVERGE_TOL):
    """NaN/inf 或 末窗均值显著高于首窗均值 → 发散。losses=按步 list。"""
    a = np.asarray([x for x in losses if x is not None], dtype=np.float64)
    if a.size == 0:
        return True, 'no-loss'
    if not np.isfinite(a).all():
        return True, 'NaN/inf'
    if a.size >= 4:
        k = max(1, a.size // 4)
        first, last = a[:k].mean(), a[-k:].mean()
        if last > first * (1 + tol):
            return True, f'rise {first:.4f}->{last:.4f}'
    return False, 'ok'


def loss_decreasing(losses):
    """末四分位均值 < 首四分位均值 → 在降（DINO/通用单调降判据）。"""
    a = np.asarray([x for x in losses if x is not None], dtype=np.float64)
    if a.size < 4 or not np.isfinite(a).all():
        return False
    k = max(1, a.size // 4)
    return bool(a[-k:].mean() < a[:k].mean())


# ===========================================================================
# 整段监控量计算（hook 在官方 loop 调；feats/probs 来自训练内部）
# ===========================================================================
def compute_dino_metrics(teacher_probs=None, feats=None, out_dim=DINO_OUT_DIM):
    m = {}
    if teacher_probs is not None:
        m['teacher_entropy'] = teacher_entropy(teacher_probs)
        m['kl_uniform'] = kl_to_uniform(teacher_probs, out_dim=out_dim)
    if feats is not None:
        m['feat_std'] = feature_std(feats)
    return m


def compute_moco_metrics(feats=None, grad_norm=None, batch=None):
    m = {}
    if feats is not None:
        m['feat_std'] = feature_std(feats)
    if grad_norm is not None:
        m['grad_norm'] = float(grad_norm)
    if batch is not None:
        m['contrastive_baseline'] = contrastive_baseline(batch)
    return m


# ===========================================================================
# MonitorWriter：smoke_<method>.csv + state.json 心跳
# ===========================================================================
_CSV_FIELDS = ['run', 'method', 'seed', 'step', 'epoch', 'loss',
               'teacher_entropy', 'kl_uniform', 'feat_std', 'grad_norm',
               'contrastive_baseline', 'timestamp']


class MonitorWriter:
    def __init__(self, results_dir, run, method, seed):
        self.results_dir = results_dir
        self.run, self.method, self.seed = run, method, seed
        os.makedirs(results_dir, exist_ok=True)
        self.csv_path = os.path.join(results_dir, f'smoke_{method}.csv')
        self._losses = []
        if not os.path.exists(self.csv_path):
            with open(self.csv_path, 'w', newline='') as f:
                csv.DictWriter(f, fieldnames=_CSV_FIELDS).writeheader()

    def log_step(self, step, *, epoch=None, loss=None, total_steps=None, **metrics):
        """每 50-100 步调用。metrics 含 teacher_entropy/kl_uniform/feat_std/grad_norm/contrastive_baseline。"""
        if loss is not None:
            self._losses.append(loss)
        row = {k: '' for k in _CSV_FIELDS}
        row.update(run=self.run, method=self.method, seed=self.seed, step=step,
                   epoch=epoch if epoch is not None else '',
                   loss=loss if loss is not None else '',
                   timestamp=time.strftime('%Y-%m-%dT%H:%M:%S'))
        for k, v in metrics.items():
            if k in row:
                row[k] = v
        with open(self.csv_path, 'a', newline='') as f:
            csv.DictWriter(f, fieldnames=_CSV_FIELDS).writerow(row)
        write_state(self.results_dir, self.run, step=step, total_steps=total_steps,
                    epoch=epoch, loss=loss, metrics={k: metrics[k] for k in metrics},
                    status='running', method=self.method, seed=self.seed)
        return row

    def finalize(self, verdict, reasons):
        write_state(self.results_dir, self.run, status=f'smoke_{verdict.lower()}',
                    method=self.method, seed=self.seed,
                    metrics={'verdict': verdict, 'reasons': reasons})


# ===========================================================================
# Gate：读 smoke_<method>.csv 累积量 -> PASS/FAIL/INCOMPLETE（矩阵 §2 预登记判据）
# ===========================================================================
def _col(rows, key):
    out = []
    for r in rows:
        v = r.get(key, '')
        if v == '' or v is None:
            continue
        try:
            out.append(float(v))
        except (TypeError, ValueError):
            pass
    return out


def evaluate_gate(method, rows, *, batch=None, stop_grad_conv1=None):
    """返回 dict(verdict, reasons, checks)。
    verdict: PASS / FAIL / INCOMPLETE（缺 collapse-critical 量 → INCOMPLETE，绝不假 PASS）。"""
    method = method.lower()
    losses = _col(rows, 'loss')
    checks, reasons, missing = {}, [], []

    # 通用：无发散 / NaN
    div, why = loss_diverged(losses)
    checks['no_divergence'] = (not div, why)
    if div:
        reasons.append(f'loss 发散/NaN: {why}')

    if method == 'dino':
        ents = _col(rows, 'teacher_entropy')
        stds = _col(rows, 'feat_std')
        lo, hi = DINO_ENT_LO_FRAC * LN(DINO_OUT_DIM), DINO_ENT_HI_FRAC * LN(DINO_OUT_DIM)
        if ents:
            last = ents[-1]
            ok = lo < last < hi
            checks['entropy_band'] = (ok, f'{last:.3f} ∈ ({lo:.3f},{hi:.3f})?')
            if not ok:
                reasons.append(f'teacher 熵 {last:.3f} 出界 ({lo:.3f},{hi:.3f})（collapse 信号）')
        else:
            missing.append('teacher_entropy')
        if stds:
            ok = stds[-1] > FEAT_STD_MIN
            checks['feat_std'] = (ok, f'{stds[-1]:.4f}>{FEAT_STD_MIN}?')
            if not ok:
                reasons.append(f'特征 std {stds[-1]:.4f} ≤ {FEAT_STD_MIN}（塌缩）')
        else:
            missing.append('feat_std')
        dec = loss_decreasing(losses)
        checks['loss_decreasing'] = (dec, 'last-q < first-q?')
        if not dec:
            reasons.append('loss 未单调降')

    elif method == 'moco':
        stds = _col(rows, 'feat_std')
        baselines = _col(rows, 'contrastive_baseline')
        b = baselines[-1] if baselines else (contrastive_baseline(batch) if batch else None)
        if b is not None and losses:
            ok = losses[-1] < b
            checks['loss_below_ln_batch'] = (ok, f'{losses[-1]:.4f}<ln(batch)={b:.4f}?')
            if not ok:
                reasons.append(f'对比 loss {losses[-1]:.4f} 卡在 ln(batch)={b:.4f} 平台（未学到）')
        else:
            missing.append('contrastive_baseline/batch')
        if stds:
            ok = stds[-1] > FEAT_STD_MIN
            checks['feat_std'] = (ok, f'{stds[-1]:.4f}>{FEAT_STD_MIN}?')
            if not ok:
                reasons.append(f'特征 std {stds[-1]:.4f} ≤ {FEAT_STD_MIN}')
        else:
            missing.append('feat_std')
        if stop_grad_conv1 is False:
            reasons.append('stop_grad_conv1 未开（矩阵 §2 必开项）')
            checks['stop_grad_conv1'] = (False, 'must be on')
        elif stop_grad_conv1 is True:
            checks['stop_grad_conv1'] = (True, 'on')

    elif method in ('mae', 'chexworld'):
        # 廉价 loss-sanity：平台 or 降、无发散即可（少 collapse 监控）
        checks['loss_sanity'] = (not div, why)
        # 平台/降：末窗不高于首窗即算健康（loss_diverged 已覆盖 rise）
    else:
        return dict(verdict='INCOMPLETE', reasons=[f'未知 method {method}'], checks={})

    if missing:
        return dict(verdict='INCOMPLETE',
                    reasons=[f'缺 collapse-critical 监控量 {missing}（需主线挂 hook，不放行假 PASS）'] + reasons,
                    checks=checks, missing=missing)
    verdict = 'PASS' if not reasons else 'FAIL'
    return dict(verdict=verdict, reasons=reasons, checks=checks, missing=[])


# ===========================================================================
# --tail：解析官方训练 stdout 日志抽 loss / grad_norm（官方不 emit 熵/std）
# ===========================================================================
_LOSS_RE = re.compile(r'(?:^|\s)[Ll]oss[:=]?\s*([0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?)')
_GN_RE = re.compile(r'(?:grad[_ ]?norm|Grad_Norm)[:=]?\s*([0-9]*\.?[0-9]+)')


def parse_log_line(line):
    """从一行官方日志抽 (loss, grad_norm)；抽不到返回 (None, None)。"""
    lm = _LOSS_RE.search(line)
    gm = _GN_RE.search(line)
    loss = float(lm.group(1)) if lm else None
    gn = float(gm.group(1)) if gm else None
    return loss, gn


def tail_log_to_rows(log_path, method, seed='', run=''):
    """读官方日志整文件，抽每行 loss/grad_norm 成 rows（供 evaluate_gate）。"""
    rows = []
    with open(log_path, 'r', errors='ignore') as f:
        for i, ln in enumerate(f):
            loss, gn = parse_log_line(ln)
            if loss is None and gn is None:
                continue
            rows.append(dict(run=run, method=method, seed=seed, step=i,
                             loss='' if loss is None else loss,
                             grad_norm='' if gn is None else gn))
    return rows


def _read_csv(path):
    with open(path, newline='') as f:
        return list(csv.DictReader(f))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description='烟测监控 / gate（不跑训练，只读 csv/日志判健康）')
    p.add_argument('--mode', choices=['verdict', 'tail-verdict', 'selftest'], default='verdict')
    p.add_argument('--method', required=False)
    p.add_argument('--csv', help='verdict 模式：smoke_<method>.csv 路径')
    p.add_argument('--log', help='tail-verdict 模式：官方训练 stdout 日志路径')
    p.add_argument('--results_dir', default=None, help='写 state_<run>.json 处')
    p.add_argument('--run', default='smk')
    p.add_argument('--seed', default='0')
    p.add_argument('--batch', type=int, default=None, help='MoCo ln(batch) 基线用')
    p.add_argument('--stop_grad_conv1', choices=['true', 'false'], default=None)
    a = p.parse_args()

    if a.mode == 'selftest':
        # 纯函数自检（不读盘、不跑训练）
        u = np.full((8, 16), 1 / 16.0)
        print('entropy(uniform 16) =', teacher_entropy(u), 'ln16=', LN(16))
        print('kl_uniform(uniform) =', kl_to_uniform(u))
        print('feat_std(randn) =', feature_std(np.random.randn(100, 32)))
        sys.exit(0)

    sgc = {'true': True, 'false': False}.get(a.stop_grad_conv1, None)
    if a.mode == 'verdict':
        rows = _read_csv(a.csv)
    else:  # tail-verdict
        rows = tail_log_to_rows(a.log, a.method, seed=a.seed, run=a.run)
    res = evaluate_gate(a.method, rows, batch=a.batch, stop_grad_conv1=sgc)
    print(f'[GATE] method={a.method} verdict={res["verdict"]}')
    for k, v in res.get('checks', {}).items():
        print(f'   {k}: {v}')
    for r in res.get('reasons', []):
        print(f'   ⚠️ {r}')
    if a.results_dir:
        write_state(a.results_dir, a.run, status=f'smoke_{res["verdict"].lower()}',
                    method=a.method, seed=a.seed,
                    metrics={'verdict': res['verdict'], 'reasons': res['reasons']})
    sys.exit(0 if res['verdict'] == 'PASS' else 1)
