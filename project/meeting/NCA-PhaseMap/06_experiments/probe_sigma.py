"""probe_sigma.py — σ（branching ratio）探针 — NCA-PhaseMap 补2 §1
服务项目：NCA-PhaseMap / K-new-3 机制段（解耦路A）

方法：
    受控随机初始化 BackboneNCA（fc0.w~N(0,0.01), fc0.b=0,
    fc1.w~N(0,0.01) 非零 [关键：旧M1 fc1=0→dx≡0→全nan bug]，fc1.b=0），
    不训练、不读训练 csv（破循环论证）。
    喂真实 patch（Hippo/BraTS），跑 N≥200 步 NCA forward（fire_rate=1-ur），
    每步记活跃 cell 计数 A(t) = (|state[...,alive_ch]| > eps_active).sum()。
    eps_active 用 step1 全场 |state| P90 标定（跑前冻结）。
    用 mrestimator 估 branching ratio σ + CI。
    σ=1 → 临界吸收态（相变判据）。

预装：pip install mrestimator

【入口】
    python probe_sigma.py [--dataset hippo|brats] [--n_steps 200]
                          [--smoke 1] [--out_suffix _test]

【输出】
    results/probe_sigma.csv
    列: ur, fire_rate, dataset, init_seed, sigma, sigma_ci_low,
        sigma_ci_high, eps_active, n_steps, mre_ok
    results/probe_sigma_state.json  心跳

【环境变量（HPC）】
    MEDNCA_ROOT    Med-NCA 根目录
    BRATS_ROOT     BraTS test/ 目录
    PHASEMAP_OUT   输出根目录
"""

import os
import sys
import csv
import json
import math
import time
import argparse
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

# ─── mrestimator import（容错：失败给清晰报错） ──────────────────────
# 安装：pip install mrestimator
try:
    import mrestimator as mre
    _MRE_AVAILABLE = True
except ImportError as _mre_err:
    _MRE_AVAILABLE = False
    _MRE_ERR_MSG = str(_mre_err)

# ─── 路径常量（复用 B1_B2_B3_sweep.py 口径） ────────────────────────
MEDNCA_ROOT = os.environ.get(
    'MEDNCA_ROOT',
    os.path.join("D:", os.sep, "YJ-Agent", "project", "meeting", "Med-NCA")
)
OFFICIAL_ROOT = os.path.join(MEDNCA_ROOT, "M3D-NCA-official")
DATA_HIP      = os.path.join(MEDNCA_ROOT, "data", "Task04_Hippocampus")

_BRATS_ROOT_DEFAULT = os.environ.get(
    'BRATS_ROOT',
    os.path.join("D:", os.sep, "YJ-Agent", "project", "meeting",
                 "MedAD-FailMap", "data", "BraTS2021", "test")
)

THIS_DIR    = os.environ.get('PHASEMAP_OUT',
                             os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(THIS_DIR, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

# ─── NCA 超参（零偏离官方，复用 sweep 口径） ─────────────────────────
CHANNEL_N   = 16
HIDDEN_SIZE = 128
DEVICE      = "cuda:0" if torch.cuda.is_available() else "cpu"
IMG_SIZE    = (64, 64)
LR          = 16e-4
BETAS       = (0.5, 0.5)
INFERENCE_STEPS_EVAL = 16

FIXED_INIT_VAR = 0.01  # N(0, 0.01) 对齐 sweep

# alive channel（同 sweep pred=x[...,1:2] 口径，channel index 1）
ALIVE_CH = 1

# ur 网格（对齐补1/补3）
UR_GRID = [0.25, 0.30, 0.35, 0.40, 0.45, 0.50,
           0.55, 0.60, 0.65, 0.70, 0.75, 0.80]

INIT_SEEDS = [42, 43, 44, 45, 46]

# 标定 eps_active 用的分位数
EPS_ACTIVE_QUANTILE = 0.90  # P90 of |state| at step1

NCA_CONFIG_BASE = {
    'img_path':        os.path.join(DATA_HIP, "imagesTr"),
    'label_path':      os.path.join(DATA_HIP, "labelsTr"),
    'device':          DEVICE,
    'channel_n':       CHANNEL_N,
    'inference_steps': INFERENCE_STEPS_EVAL,
    'cell_fire_rate':  0.5,
    'input_channels':  1,
    'output_channels': 1,
    'hidden_size':     HIDDEN_SIZE,
    'input_size':      [[16, 16], [64, 64]],
    'data_split':      [0.7, 0.0, 0.3],
    'rescale':         True,
}


# ─── 工具函数 ─────────────────────────────────────────────────────────

def set_seed(s):
    np.random.seed(s)
    torch.manual_seed(s)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(s)


def write_state(path, phase, extra=None):
    state = {"phase": phase, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")}
    if extra:
        state.update(extra)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def write_csv(rows, path, cols):
    with open(path, 'w', newline='', encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)


def _fmt(v):
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return 'nan'
    if isinstance(v, float):
        return round(v, 8)
    return v


# ─── 路径 patch（Hippo 数据集构造用，复用 sweep 口径） ───────────────

def _patch_path(v):
    if not isinstance(v, str):
        return v
    v_posix = v.replace('\\', '/')
    marker = 'Med-NCA/'
    idx = v_posix.find(marker)
    if idx == -1:
        return v
    rel = v_posix[idx + len(marker):]
    return MEDNCA_ROOT.replace('\\', '/') + '/' + rel


def patch_experiment_paths(exp):
    for stage in exp.projectConfig:
        for k, v in stage.items():
            patched = _patch_path(v)
            if patched != v:
                stage[k] = patched
    exp.set_current_config()


# ─── 受控初始化 NCA ───────────────────────────────────────────────────

def build_controlled_nca(device, init_seed):
    """
    受控随机初始化 BackboneNCA（破循环论证，不读训练权重）。

    关键区别 vs 旧 M1：
      fc1.w ~ N(0, 0.01)  ← 非零！旧 M1 fc1=0 → dx≡0 → 全 nan
      这是测量协议（非训练私改），论文 §Method 须写明
      「在受控随机权重下测架构传播特性」。
    """
    set_seed(init_seed)
    sys.path.insert(0, OFFICIAL_ROOT)
    os.chdir(OFFICIAL_ROOT)
    from src.models.Model_BackboneNCA import BackboneNCA

    ca = BackboneNCA(
        channel_n=CHANNEL_N,
        fire_rate=0.5,
        device=device,
        hidden_size=HIDDEN_SIZE,
        input_channels=1,
    ).to(device)

    with torch.no_grad():
        nn.init.normal_(ca.fc0.weight, mean=0.0, std=FIXED_INIT_VAR)
        if ca.fc0.bias is not None:
            nn.init.zeros_(ca.fc0.bias)
        # fc1 非零（修旧 M1 bug）——测量协议，不训练
        nn.init.normal_(ca.fc1.weight, mean=0.0, std=FIXED_INIT_VAR)
        if ca.fc1.bias is not None:
            nn.init.zeros_(ca.fc1.bias)

    return ca


# ─── make_seed（复用 sweep 口径） ────────────────────────────────────

def make_seed(img, channel_n, device):
    """img: [B, C, H, W] → seed: [B, H, W, channel_n]"""
    B, C, H, W = img.shape
    seed = torch.zeros(B, H, W, channel_n, device=device)
    seed[..., :C] = img.permute(0, 2, 3, 1)
    return seed


# ─── eps_active 标定 ─────────────────────────────────────────────────

def calibrate_eps_active(ca, patch_batch, fire_rate, device, quantile=EPS_ACTIVE_QUANTILE):
    """
    用受控 init 网络 step1 全场 |state| 的 P90 标定 eps_active。
    跑前一次标定、冻结，不事后调。
    patch_batch: [B, C, H, W] 真实 patch（取 batch 首个足矣）
    """
    img_b = patch_batch[:4].to(device)  # 最多取 4 张
    seed  = make_seed(img_b, CHANNEL_N, device)

    with torch.no_grad():
        x1 = ca(seed, steps=1, fire_rate=fire_rate)  # [B, H, W, ch]

    abs_state = x1.abs().cpu().numpy()  # [B, H, W, ch]
    eps = float(np.quantile(abs_state.flatten(), quantile))

    # 防 eps 退化为 0（全场静止）
    if eps < 1e-10:
        eps = 1e-10
        print(f"[probe_sigma] WARNING: eps_active 标定退化→{eps:.2e}，全场可能无响应", flush=True)

    print(f"[probe_sigma] eps_active 标定(P{quantile*100:.0f})={eps:.6e}  "
          f"(fire_rate={fire_rate:.4f})", flush=True)
    return eps


# ─── 数据集加载 ───────────────────────────────────────────────────────

def load_dataset(dataset_name, brats_root, smoke):
    """返回 (train_ds, label_str)"""
    if smoke:
        class MockDS(torch.utils.data.Dataset):
            def __init__(self, n=8):
                H, W = IMG_SIZE
                self.s = [
                    (torch.rand(1, H, W), (torch.rand(1, H, W) > 0.7).float())
                    for _ in range(n)
                ]
            def __len__(self): return len(self.s)
            def __getitem__(self, i): return self.s[i]
        return MockDS(), "mock"

    if dataset_name == 'hippo':
        sys.path.insert(0, OFFICIAL_ROOT)
        os.chdir(OFFICIAL_ROOT)
        from src.datasets.Nii_Gz_Dataset_3D import Dataset_NiiGz_3D
        from src.utils.Experiment import Experiment
        from src.agents.Agent_Med_NCA import Agent_Med_NCA
        from src.models.Model_BackboneNCA import BackboneNCA

        device = torch.device(DEVICE)
        config = [{
            **NCA_CONFIG_BASE,
            'model_path': os.path.join(MEDNCA_ROOT, "checkpoints", "r1_hippocampus"),
            'lr': LR, 'lr_gamma': 0.9999, 'betas': list(BETAS),
            'save_interval': 9999, 'evaluate_interval': 9999,
            'n_epoch': 1000, 'batch_size': 48, 'train_model': 1,
            'unlock_CPU': True, 'Persistence': False,
            'batch_duplication': 1, 'keep_original_scale': False,
        }]
        dataset_nii = Dataset_NiiGz_3D(slice=2)
        ca1_tmp = BackboneNCA(CHANNEL_N, 0.5, device, hidden_size=HIDDEN_SIZE, input_channels=1).to(device)
        ca2_tmp = BackboneNCA(CHANNEL_N, 0.5, device, hidden_size=HIDDEN_SIZE, input_channels=1).to(device)
        agent_tmp = Agent_Med_NCA([ca1_tmp, ca2_tmp])
        exp_tmp   = Experiment(config, dataset_nii, [ca1_tmp, ca2_tmp], agent_tmp)
        patch_experiment_paths(exp_tmp)
        dataset_nii.set_experiment(exp_tmp)
        exp_tmp.set_model_state('train')
        dataset_nii.set_size(IMG_SIZE)

        samples = []
        for idx in range(len(dataset_nii)):
            _, img_np, lbl_np = dataset_nii[idx]
            img = torch.from_numpy(img_np).permute(2, 0, 1).float()
            lbl = torch.from_numpy(lbl_np).permute(2, 0, 1).float()
            samples.append((img, lbl))

        class ListDS(torch.utils.data.Dataset):
            def __init__(self, s): self.s = s
            def __len__(self): return len(self.s)
            def __getitem__(self, i): return self.s[i]

        return ListDS(samples), "hippo"

    else:  # brats
        exp_dir = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, exp_dir)
        from data_brats import BraTSSliceDataset
        ds = BraTSSliceDataset(data_root=brats_root, fg_thresh=0.02)
        return ds, "brats"


# ─── σ 估计（mrestimator 调用） ──────────────────────────────────────

def estimate_sigma_mre(activity_series):
    """
    用 mrestimator 估 branching ratio σ + CI（Bug 2 修复版）。
    activity_series: list/ndarray of floats, len ≥ 20

    返回 (sigma, ci_low, ci_high, ok_flag)
    ok_flag=False 时代表 mrestimator 失败，σ=nan。

    full_analysis 正确签名（v0.1.6+）：
      mre.full_analysis(data, dt, method, kmax/steps/tmax 其一, showoverview=False)
    返回 OutputHandler：
      res.fits[0].mre        = branching ratio σ
      res.fits[0].mrestderr  = σ 标准误（用于 CI）

    method 说明：
      'stationarymean'（sm）= 单 trial / 1D array 用这个
      'trialseparated'（ts） = 多 trial（2D array，每行一个 trial）用这个
    本函数输入为 1D array，故用 'stationarymean'。
    """
    if not _MRE_AVAILABLE:
        raise ImportError(
            f"mrestimator 未安装，请先运行：pip install mrestimator\n"
            f"原始错误：{_MRE_ERR_MSG}"
        )

    arr = np.array(activity_series, dtype=np.float64)
    if len(arr) < 20:
        return float('nan'), float('nan'), float('nan'), False

    # kmax 取序列长度一半以内，避免 "steps greater than half" 警告
    kmax = max(10, len(arr) // 2 - 1)

    # ── 方法一：full_analysis（Bug 2 修复：补全 method + kmax + showoverview=False）
    try:
        res = mre.full_analysis(
            data=arr,
            dt=1,
            dtunit='step',
            method='stationarymean',   # 单 trial（1D array）
            kmax=kmax,
            showoverview=False,        # loop 调用防内存泄漏
        )
        # OutputHandler.fits[0] → FitResult
        # FitResult 字段：.mre（branching ratio）、.mrestderr（标准误）
        if not res.fits:
            raise ValueError("full_analysis 返回 fits 为空（可能拟合失败）")
        fit0    = res.fits[0]
        sigma   = float(fit0.mre)
        m_err   = float(fit0.mrestderr) if fit0.mrestderr is not None else float('nan')
        ci_low  = sigma - m_err if not math.isnan(m_err) else float('nan')
        ci_high = sigma + m_err if not math.isnan(m_err) else float('nan')
        return sigma, ci_low, ci_high, True

    except Exception as e1:
        # ── 方法二：coefficients + fit 分步回退
        try:
            kmax_fb = max(10, len(arr) // 2 - 1)
            coeffs  = mre.coefficients(arr, steps=(1, kmax_fb), method='stationarymean')
            fit     = mre.fit(coeffs)
            # FitResult 字段：.mre（branching ratio）、.mrestderr（标准误）
            sigma   = float(fit.mre)
            m_err   = float(fit.mrestderr) if fit.mrestderr is not None else float('nan')
            ci_low  = sigma - m_err if not math.isnan(m_err) else float('nan')
            ci_high = sigma + m_err if not math.isnan(m_err) else float('nan')
            return sigma, ci_low, ci_high, True

        except Exception as e2:
            print(
                f"[probe_sigma] WARNING: mrestimator 两种调用均失败。\n"
                f"  full_analysis: {e1}\n"
                f"  coefficients+fit: {e2}\n"
                f"  → sigma=nan，mre_ok=0。",
                flush=True
            )
            return float('nan'), float('nan'), float('nan'), False


# ─── 单次 (ur, init_seed, dataset) 探针 ─────────────────────────────

def run_probe_sigma(ca, ds, ur, n_steps, device, init_seed, dataset_label,
                    smoke=False):
    """
    跑 n_steps 步 NCA forward，每步记 A(t)，
    返回 dict: sigma, sigma_ci_low, sigma_ci_high, eps_active, n_steps, mre_ok
    """
    fire_rate = round(1.0 - ur, 6)

    loader = DataLoader(
        ds,
        batch_size=4,
        shuffle=True,
        num_workers=0,   # Windows spawn 规范
        pin_memory=False,
    )

    # ── 取一个 batch 标定 eps_active（跑前冻结）
    first_batch = None
    for img_b, lbl_b in loader:
        first_batch = img_b
        break

    if first_batch is None:
        raise RuntimeError("数据集为空，无法标定 eps_active")

    eps_active = calibrate_eps_active(ca, first_batch, fire_rate, device)

    # ── 主循环：收集 A(t) ────────────────────────────────────────────
    set_seed(init_seed)
    activity_series = []

    # 初始化 state（取第一个 batch 作为背景 patch）
    img_b = first_batch[:1].to(device)   # 取 1 张
    x = make_seed(img_b, CHANNEL_N, device)  # [1, H, W, ch]

    with torch.no_grad():
        for t in range(n_steps):
            x = ca(x, steps=1, fire_rate=fire_rate)
            # A(t)：活跃 cell 计数，alive_ch=1
            alive_count = int((x[..., ALIVE_CH].abs() > eps_active).sum().item())
            activity_series.append(float(alive_count))

            if len(activity_series) % 50 == 0:
                print(f"    [σ] ur={ur:.2f} seed={init_seed} "
                      f"t={t+1}/{n_steps} A(t)={alive_count}", flush=True)

    if smoke:
        # smoke 模式：打印 series 概况
        arr = np.array(activity_series)
        print(f"    [SMOKE] activity series: mean={arr.mean():.1f} "
              f"std={arr.std():.1f} min={arr.min():.1f} max={arr.max():.1f}", flush=True)

    # ── mrestimator 估 σ ─────────────────────────────────────────────
    sigma, ci_low, ci_high, mre_ok = estimate_sigma_mre(activity_series)

    # BUG FIX: f-string 格式符位不允许条件表达式，先算字符串再插值
    sigma_str  = f"{sigma:.4f}"   if not math.isnan(sigma)  else "nan"
    ci_low_str = f"{ci_low:.4f}"  if not math.isnan(ci_low) else "nan"
    ci_hi_str  = f"{ci_high:.4f}" if not math.isnan(ci_high) else "nan"
    print(
        f"    [σ] ur={ur:.2f} seed={init_seed} ds={dataset_label} "
        f"sigma={sigma_str} "
        f"ci=[{ci_low_str},{ci_hi_str}] "
        f"eps={eps_active:.2e} mre_ok={int(mre_ok)}",
        flush=True
    )

    return {
        'sigma':         sigma,
        'sigma_ci_low':  ci_low,
        'sigma_ci_high': ci_high,
        'eps_active':    eps_active,
        'n_steps':       len(activity_series),
        'mre_ok':        int(mre_ok),
    }


# ─── 主流程 ──────────────────────────────────────────────────────────

def main():
    # 前置：mrestimator 可用性检查
    if not _MRE_AVAILABLE:
        print(
            f"[probe_sigma] FATAL: mrestimator 未安装。\n"
            f"  请先运行：pip install mrestimator\n"
            f"  原始错误：{_MRE_ERR_MSG}",
            flush=True
        )
        sys.exit(1)

    parser = argparse.ArgumentParser(description="σ（branching ratio）探针 — NCA-PhaseMap §1")
    parser.add_argument('--dataset',    choices=['hippo', 'brats', 'both'],
                        default='both', help='数据集：hippo|brats|both（默认 both）')
    parser.add_argument('--n_steps',    type=int, default=200,
                        help='每次 forward 步数（≥200，σ 需足够长序列）')
    parser.add_argument('--ur_list',    type=str, default=None,
                        help='覆盖默认 ur 网格（逗号分隔，如 0.25,0.30,...）')
    parser.add_argument('--seeds',      type=str, default='42,43,44,45,46',
                        help='init_seed 列表（逗号分隔）')
    parser.add_argument('--brats_root', default=_BRATS_ROOT_DEFAULT)
    parser.add_argument('--smoke',      type=int, default=0,
                        help='smoke 模式：1=MockDS + 仅 20 步 + 仅前 2 run')
    parser.add_argument('--out_suffix', type=str, default='',
                        help='输出文件后缀，防覆盖既有结果')
    args = parser.parse_args()

    smoke    = args.smoke > 0
    n_steps  = 20 if smoke else max(args.n_steps, 200)  # 强制 ≥200
    init_seeds = [int(s) for s in args.seeds.split(',')]
    ur_grid  = ([float(u) for u in args.ur_list.split(',')]
                if args.ur_list else UR_GRID)

    datasets = (['hippo', 'brats'] if args.dataset == 'both'
                else [args.dataset])

    out_csv   = os.path.join(RESULTS_DIR, f"probe_sigma{args.out_suffix}.csv")
    out_state = os.path.join(RESULTS_DIR, f"probe_sigma{args.out_suffix}_state.json")

    cols = ['ur', 'fire_rate', 'dataset', 'init_seed',
            'sigma', 'sigma_ci_low', 'sigma_ci_high',
            'eps_active', 'n_steps', 'mre_ok']

    all_rows = []
    device   = torch.device(DEVICE)

    print(f"[probe_sigma] 开始 σ 探针", flush=True)
    print(f"  ur_grid={ur_grid}", flush=True)
    print(f"  init_seeds={init_seeds}", flush=True)
    print(f"  n_steps={n_steps}  smoke={smoke}", flush=True)
    print(f"  datasets={datasets}", flush=True)
    write_state(out_state, "init", {
        "ur_grid": ur_grid, "init_seeds": init_seeds,
        "n_steps": n_steps, "datasets": datasets
    })

    for ds_name in datasets:
        print(f"\n[probe_sigma] 加载数据集 {ds_name}...", flush=True)
        ds, ds_label = load_dataset(ds_name, args.brats_root, smoke)
        print(f"[probe_sigma] {ds_label} n={len(ds)}", flush=True)

        grid = [(ur, seed) for ur in ur_grid for seed in init_seeds]
        if smoke:
            grid = grid[:2]

        for run_idx, (ur, init_seed) in enumerate(grid):
            fire_rate = round(1.0 - ur, 6)
            print(
                f"\n[probe_sigma] [{ds_label}] [{run_idx+1}/{len(grid)}]  "
                f"ur={ur}  fire_rate={fire_rate}  init_seed={init_seed}",
                flush=True
            )
            write_state(out_state, "running", {
                "dataset": ds_label, "ur": ur,
                "init_seed": init_seed,
                "run": run_idx + 1, "total": len(grid)
            })

            # 受控初始化（每次重新 init，init_seed 唯一确定权重）
            ca = build_controlled_nca(device, init_seed)

            try:
                res = run_probe_sigma(
                    ca=ca,
                    ds=ds,
                    ur=ur,
                    n_steps=n_steps,
                    device=device,
                    init_seed=init_seed,
                    dataset_label=ds_label,
                    smoke=smoke,
                )
            except Exception as ex:
                print(f"  [probe_sigma] 报错: {ex}", flush=True)
                res = {
                    'sigma': float('nan'), 'sigma_ci_low': float('nan'),
                    'sigma_ci_high': float('nan'), 'eps_active': float('nan'),
                    'n_steps': 0, 'mre_ok': 0,
                }

            row = {
                'ur':            round(ur, 4),
                'fire_rate':     round(fire_rate, 4),
                'dataset':       ds_label,
                'init_seed':     init_seed,
                'sigma':         _fmt(res['sigma']),
                'sigma_ci_low':  _fmt(res['sigma_ci_low']),
                'sigma_ci_high': _fmt(res['sigma_ci_high']),
                'eps_active':    _fmt(res['eps_active']),
                'n_steps':       res['n_steps'],
                'mre_ok':        res['mre_ok'],
            }
            all_rows.append(row)
            write_csv(all_rows, out_csv, cols)

    write_state(out_state, "done", {
        "total_runs": len(all_rows),
        "mre_ok_count": sum(r['mre_ok'] for r in all_rows),
        "csv": out_csv,
    })
    print(f"\n[probe_sigma] 完成。CSV: {out_csv}", flush=True)
    mre_ok_n = sum(r['mre_ok'] for r in all_rows)
    print(f"  mre_ok: {mre_ok_n}/{len(all_rows)} runs", flush=True)
    if mre_ok_n == 0:
        print(
            "  [WARNING] 全量 mre_ok=0，请主线核 mrestimator 版本：\n"
            "    import mrestimator; print(mrestimator.__version__)\n"
            "  再按 estimate_sigma_mre() 注释里的 TODO 调通 API。",
            flush=True
        )


if __name__ == '__main__':
    main()
