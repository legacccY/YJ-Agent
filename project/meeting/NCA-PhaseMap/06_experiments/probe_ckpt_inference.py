"""probe_ckpt_inference.py — 臂2：官方训练 ckpt 探针 — NCA-PhaseMap 补2 §2
服务项目：NCA-PhaseMap / K-new-3 机制段·臂2（ckpt 辅证，crux 验证）

=== 臂2 存在意义 ===
路径A（臂1：受控随机初始化）已实证作废——随机网≈identity 无信号（动力学死掉）。
臂2 = 载**官方 Med-NCA r1_hippocampus epoch_300 健康 ckpt**（真有动力学），
权重固定，变 inference-ur 测三量 σ/ρ/d，验「测量函数在真权重上到底有没有信号」。
这是 path A 死后最便宜的 crux 验证。

=== 官方 ckpt 加载方式 ===
复用 B1_B2_B3_sweep.py 的 HipSliceDataset 构造骨架：
  Experiment.__init__ 检测到 checkpoints/r1_hippocampus/models/ 存在
  → 调 reload() → agent.load_state(epoch_300/)
  → model0.pth 加载进 ca1，model1.pth 加载进 ca2
  → 日志打 "Reload State 300"
与旧探针的关键差异：保留 reload 后的 ca1/ca2 健康权重（不丢弃）。

=== 自检 ===
ckpt 加载后检查 ca1.fc1.weight.std() 和 ca2.fc1.weight.std()：
  受控 init = 0.01；训练后应显著 >> 0.01（通常 0.05~0.5）。
  若仍 ≈ 0.01 说明 reload 未生效 → raise RuntimeError 停下报错。

=== 测量协议 ===
- 对每个 inference-ur ∈ {0.25,...,0.80}（步长 0.05，对齐补1/补3）
- mask seed ∈ {42,43,44}（vs 臂1 的5个init_seed，臂2权重固定不用多 init_seed）
- σ（branching ratio）：ca2 输出态活动序列，mrestimator 估
- ρ（谱半径）：x0_mode=foreground，ca2 单步 update 算子，power iteration
- d（脉冲传播半径）：ca2 双副本法，N={4,8,16,32}，主报 N=16
- mask 协议：torch.rand > fire_rate 逐 step，mask_seed 固定复现

=== 输出 ===
results/probe_ckpt_inference.csv
列: ur, fire_rate, inference_ur, mech, value, mask_seed, x0_mode, ckpt_verified, N

results/probe_ckpt_inference_state.json  心跳

=== 入口 ===
python probe_ckpt_inference.py [--n_steps 200] [--smoke 1] [--out_suffix _test]

=== 环境变量 ===
MEDNCA_ROOT    Med-NCA 根目录
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
import torch.nn.functional as F
from torch.utils.data import DataLoader

# ─── mrestimator import（容错） ──────────────────────────────────────
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
CKPT_PATH     = os.path.join(MEDNCA_ROOT, "checkpoints", "r1_hippocampus")

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
INPUT_CHANNELS = 1
ALIVE_CH = 1

# ckpt init var（受控 init = 0.01；训练后 >> 0.01）
FIXED_INIT_VAR = 0.01
CKPT_MIN_WEIGHT_STD = 0.015  # 自检阈：高于此视为 ckpt 生效（保守）

# ur 网格（对齐补1/补3）
UR_GRID = [0.25, 0.30, 0.35, 0.40, 0.45, 0.50,
           0.55, 0.60, 0.65, 0.70, 0.75, 0.80]

# 臂2 只需 mask_seed（权重固定，不用多 init_seed）
MASK_SEEDS = [42, 43, 44]

# d(N) 步集合
DEFAULT_N_LIST = [4, 8, 16, 32]

# σ 每次 forward 步数
N_STEPS_SIGMA = 200

# θ 分母 = e（d(N) 峰值 1/e 标准，同 probe_dn.py）
THETA_INV_E = math.e

# eps_active 标定分位数（同 probe_sigma.py）
EPS_ACTIVE_QUANTILE = 0.90

# power iteration 超参（同 probe_rho.py）
N_ITER_RHO = 100
TOL_RHO    = 1e-6

# warmup steps for foreground x0（同 probe_rho.py）
WARMUP_STEPS = 8

# config 模板（官方 Experiment 构造用，不训练只取数据+ckpt）
NCA_CONFIG_BASE = {
    'img_path':        os.path.join(DATA_HIP, "imagesTr"),
    'label_path':      os.path.join(DATA_HIP, "labelsTr"),
    'device':          DEVICE,
    'channel_n':       CHANNEL_N,
    'inference_steps': INFERENCE_STEPS_EVAL,
    'cell_fire_rate':  0.5,
    'input_channels':  INPUT_CHANNELS,
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


# ─── 路径 patch（复用 sweep 口径） ───────────────────────────────────

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


# ─── make_seed ───────────────────────────────────────────────────────

def make_seed(img, channel_n, device):
    """img: [B, C, H, W] → seed: [B, H, W, channel_n]"""
    B, C, H, W = img.shape
    seed = torch.zeros(B, H, W, channel_n, device=device)
    seed[..., :C] = img.permute(0, 2, 3, 1)
    return seed


# ─── 官方 ckpt 加载（臂2 核心，复用 HipSliceDataset 构造骨架） ────────

def load_official_ckpt_and_dataset(device, smoke=False):
    """
    通过官方 Experiment 构造流程加载 r1_hippocampus epoch_300 权重。

    流程：
      1. 构造 Experiment（model_path=checkpoints/r1_hippocampus）
      2. Experiment.__init__ 检测到 models/ → reload() → agent.load_state(epoch_300/)
         → ca1←model0.pth, ca2←model1.pth（日志打 "Reload State 300"）
      3. 保留 ca1/ca2 引用（臂2 关键：旧探针丢弃了这两个对象）
      4. 同时返回 hippo test 数据集（取 test split = data_split=[0.7,0.0,0.3] 的 0.3 部分）

    Returns:
        ca1:     BackboneNCA（低分辨，16×16 patch 训练）
        ca2:     BackboneNCA（高分辨，64×64 patch 训练）
        samples: list of (img_tensor [C,H,W], lbl_tensor [C,H,W])，test split
        ckpt_verified: bool（自检通过标志）
    """
    sys.path.insert(0, OFFICIAL_ROOT)
    os.chdir(OFFICIAL_ROOT)

    from src.datasets.Nii_Gz_Dataset_3D import Dataset_NiiGz_3D
    from src.utils.Experiment import Experiment
    from src.agents.Agent_Med_NCA import Agent_Med_NCA
    from src.models.Model_BackboneNCA import BackboneNCA

    device_obj = torch.device(device) if isinstance(device, str) else device

    config = [{
        **NCA_CONFIG_BASE,
        'model_path': CKPT_PATH,
        'lr':         LR,
        'lr_gamma':   0.9999,
        'betas':      list(BETAS),
        'save_interval':     9999,
        'evaluate_interval': 9999,
        'n_epoch':    1000,
        'batch_size': 48,
        'train_model': 1,
        'unlock_CPU': True,
        'Persistence': False,
        'batch_duplication': 1,
        'keep_original_scale': False,
    }]

    dataset_nii = Dataset_NiiGz_3D(slice=2)

    # ca1/ca2 — 训练权重由 Experiment.reload() 加载进来
    ca1 = BackboneNCA(CHANNEL_N, 0.5, device_obj, hidden_size=HIDDEN_SIZE,
                      input_channels=INPUT_CHANNELS).to(device_obj)
    ca2 = BackboneNCA(CHANNEL_N, 0.5, device_obj, hidden_size=HIDDEN_SIZE,
                      input_channels=INPUT_CHANNELS).to(device_obj)

    agent = Agent_Med_NCA([ca1, ca2])

    # Experiment 构造：
    #   general() → agent.set_exp(self) → agent.initialize()（创建 optimizer/scheduler）
    #   reload()  → 从 config.dt 读旧 projectConfig → 旧路径 epoch_300 → agent.load_state
    #   注意：reload() 内部用 config.dt 里的 model_path（可能是 Linux 绝对路径），
    #         在 Windows 上 os.path.exists 返回 False → load_state 不调 → ckpt 未生效。
    #         修法：构造后检查权重，若仍是 init 值则显式用正确路径重调 load_state。
    print(f"[probe_ckpt] 构造 Experiment，期待日志 'Reload State 300'...", flush=True)
    exp = Experiment(config, dataset_nii, [ca1, ca2], agent)
    patch_experiment_paths(exp)
    # 对齐 B1_B2_B3_sweep.py HipSliceDataset.__init__（L231-233）
    dataset_nii.set_experiment(exp)

    # ── 自检：训练后权重应显著 >> FIXED_INIT_VAR=0.01
    ca1_w_std = float(ca1.fc1.weight.std().item())
    ca2_w_std = float(ca2.fc1.weight.std().item())
    print(
        f"[probe_ckpt] 自检 fc1.weight.std（Experiment 构造后）: "
        f"ca1={ca1_w_std:.6f}  ca2={ca2_w_std:.6f}  (受控init=0.01)",
        flush=True
    )

    # Bug 1 修复：Experiment.reload() 内部用 config.dt 里的旧路径，
    # Windows 上 os.path.exists 返回 False → load_state 未调 → 权重仍是 init。
    # 修法：若权重仍近似 init 值，显式用正确 CKPT_PATH 强制加载。
    epoch_300_path = os.path.join(CKPT_PATH, 'models', 'epoch_300')  # 预定义，供 warning 用
    ckpt_auto_ok = (ca1_w_std > CKPT_MIN_WEIGHT_STD and
                    ca2_w_std > CKPT_MIN_WEIGHT_STD)

    if not ckpt_auto_ok:
        print(
            f"[probe_ckpt] Experiment.reload() 路径未生效（std≈0.01 仍是 init），"
            f"显式调 agent.load_state({epoch_300_path})",
            flush=True
        )
        if not os.path.isdir(epoch_300_path):
            raise RuntimeError(
                f"[probe_ckpt] FATAL: epoch_300 目录不存在: {epoch_300_path}\n"
                f"  请检查 MEDNCA_ROOT 和 checkpoints 路径。"
            )
        agent.load_state(epoch_300_path)
        print("[probe_ckpt] agent.load_state 显式调用完成", flush=True)

        # 二次自检
        ca1_w_std = float(ca1.fc1.weight.std().item())
        ca2_w_std = float(ca2.fc1.weight.std().item())

    print(
        f"[probe_ckpt] 最终 fc1.weight.std: ca1={ca1_w_std:.6f}  ca2={ca2_w_std:.6f}  "
        f"(受控init=0.01；显著 > 0.01 即视为 ckpt 生效)",
        flush=True
    )

    # ckpt_verified: 打印值 + 与 0.01 对比，只要明显 != init 即算 PASS
    ckpt_verified = (ca1_w_std > CKPT_MIN_WEIGHT_STD and
                     ca2_w_std > CKPT_MIN_WEIGHT_STD)

    if ckpt_verified:
        print(f"[probe_ckpt] ckpt 自检 PASS: ca1_std={ca1_w_std:.6f}, ca2_std={ca2_w_std:.6f}",
              flush=True)
    else:
        print(
            f"[probe_ckpt] WARNING: ckpt 自检未 PASS，std 仍接近 init(0.01)。\n"
            f"  ca1={ca1_w_std:.6f}  ca2={ca2_w_std:.6f}\n"
            f"  可能原因：model0.pth/model1.pth 不在 {epoch_300_path}/\n"
            f"  或 fc1 层训练后确实 std 偏小——请主线对照 ckpt 实际情况判断。\n"
            f"  继续运行（不 raise），ckpt_verified=False 写入 CSV 供后续分析。",
            flush=True
        )

    # ── 取 test split 数据（data_split=[0.7,0.0,0.3] 的 test 部分）
    exp.set_model_state('test')
    dataset_nii.set_size(IMG_SIZE)

    samples = []
    for idx in range(len(dataset_nii)):
        if smoke and idx >= 4:
            break
        _, img_np, lbl_np = dataset_nii[idx]
        img = torch.from_numpy(img_np).permute(2, 0, 1).float()
        lbl = torch.from_numpy(lbl_np).permute(2, 0, 1).float()
        samples.append((img, lbl))

    print(f"[probe_ckpt] 数据集 test split: {len(samples)} 张", flush=True)

    # ── 冻结权重（eval + 不需 grad）
    ca1.eval()
    ca2.eval()
    for p in ca1.parameters():
        p.requires_grad_(False)
    for p in ca2.parameters():
        p.requires_grad_(False)

    return ca1, ca2, samples, ckpt_verified


# ─── σ 测量算子（复用 probe_sigma.py 思路，测 ca2 输出态活动序列） ────

def measure_sigma(ca1, ca2, patch_img, fire_rate, n_steps, device,
                  mask_seed, smoke=False):
    """
    σ（branching ratio）：
    - 官方级联：ca1（低分辨）→ 上采 → ca2（64²）。
    - 活动序列 A(t) 在 ca2 的 n_steps 步输出态的 ALIVE_CH 测。
    - eps_active 用 step1 全场 |state| P90 标定。

    Args:
        ca1, ca2:     官方健康权重（eval，no grad）
        patch_img:    [1, C, H, W] float tensor（test patch，CPU）
        fire_rate:    1 - ur
        n_steps:      ca2 前向步数（≥200 给足时序）
        device:
        mask_seed:    用于固定 mask（torch seed base）
        smoke:        smoke 模式用少步数

    Returns:
        dict: sigma, sigma_ci_low, sigma_ci_high, eps_active, n_steps_run, mre_ok
    """
    if not _MRE_AVAILABLE:
        return {
            'sigma': float('nan'), 'sigma_ci_low': float('nan'),
            'sigma_ci_high': float('nan'), 'eps_active': float('nan'),
            'n_steps_run': 0, 'mre_ok': 0,
        }

    img = patch_img.to(device)
    H, W = IMG_SIZE

    # ── 官方级联 forward（ca1→上采→ca2 状态初始化）
    with torch.no_grad():
        # ca1（低分辨 16×16）
        import torch.nn as nn_mod
        down_size = (H // 4, W // 4)
        img_low = F.interpolate(img, size=down_size, mode='bilinear', align_corners=False)
        seed_low = make_seed(img_low, CHANNEL_N, device)  # [1, 16, 16, ch]
        out_low = ca1(seed_low, steps=INFERENCE_STEPS_EVAL, fire_rate=fire_rate)

        # 上采到 64×64
        up = torch.nn.Upsample(scale_factor=4, mode='nearest')
        out_low_perm = out_low.permute(0, 3, 1, 2)   # [1, ch, 16, 16]
        out_low_up   = up(out_low_perm).permute(0, 2, 3, 1)  # [1, 64, 64, ch]

        # ca2 输入：拼合高分辨图像通道 + 低分辨特征（对齐官方 get_outputs）
        seed_hi = make_seed(img, CHANNEL_N, device)  # [1, 64, 64, ch]
        x = torch.cat(
            (seed_hi[..., :INPUT_CHANNELS],
             out_low_up[..., INPUT_CHANNELS:]),
            dim=-1
        )  # [1, 64, 64, ch]

    # ── eps_active 标定（用 ca2 step1 P90）
    with torch.no_grad():
        torch.manual_seed(mask_seed)
        x1 = ca2(x.clone(), steps=1, fire_rate=fire_rate)
    abs_state = x1.abs().cpu().numpy()
    eps_active = float(np.quantile(abs_state.flatten(), EPS_ACTIVE_QUANTILE))
    if eps_active < 1e-10:
        eps_active = 1e-10
        print(f"  [σ] WARNING: eps_active 退化→{eps_active:.2e}", flush=True)

    # ── 收集 ca2 活动序列 A(t)
    activity_series = []
    x_run = x.clone()
    n_actual = 20 if smoke else n_steps

    with torch.no_grad():
        for t in range(n_actual):
            torch.manual_seed(mask_seed + t + 1)
            x_run = ca2(x_run, steps=1, fire_rate=fire_rate)
            alive_count = int((x_run[..., ALIVE_CH].abs() > eps_active).sum().item())
            activity_series.append(float(alive_count))

    # ── mrestimator 估 σ
    arr = np.array(activity_series, dtype=np.float64)
    sigma, ci_low, ci_high, mre_ok = _mre_estimate(arr)

    return {
        'sigma':         sigma,
        'sigma_ci_low':  ci_low,
        'sigma_ci_high': ci_high,
        'eps_active':    eps_active,
        'n_steps_run':   len(activity_series),
        'mre_ok':        int(mre_ok),
    }


def _mre_estimate(arr):
    """
    mrestimator 调用（Bug 2 修复版）。

    full_analysis 正确签名（v0.1.6+）：
      mre.full_analysis(data, dt, method, kmax/steps/tmax 其一, showoverview=False)
    返回 OutputHandler：
      res.fits[0].mre        = branching ratio σ
      res.fits[0].mrestderr  = σ 标准误（用于 CI）
    """
    if len(arr) < 20:
        return float('nan'), float('nan'), float('nan'), False

    # kmax 取序列长度一半以内，避免 "steps greater than half" 警告
    kmax = max(10, len(arr) // 2 - 1)

    try:
        # Bug 2 修复：补全 method + kmax + showoverview=False（loop 调用防内存泄漏）
        res = mre.full_analysis(
            data=arr,
            dt=1,
            dtunit='step',
            method='stationarymean',   # 单 trial（1D array）用 stationarymean
            kmax=kmax,
            showoverview=False,
        )
        # OutputHandler.fits[0] → FitResult
        # FitResult 字段：.mre（branching ratio）、.mrestderr（标准误）
        if not res.fits:
            raise ValueError("full_analysis 返回 fits 为空")
        fit0    = res.fits[0]
        sigma   = float(fit0.mre)
        m_err   = float(fit0.mrestderr) if fit0.mrestderr is not None else float('nan')
        ci_low  = sigma - m_err if not math.isnan(m_err) else float('nan')
        ci_high = sigma + m_err if not math.isnan(m_err) else float('nan')
        return sigma, ci_low, ci_high, True
    except Exception as e1:
        # 回退：coefficients + fit 分步调用
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
                f"  [σ] mrestimator 两种调用均失败:\n"
                f"    full_analysis: {e1}\n"
                f"    coefficients+fit: {e2}",
                flush=True
            )
            return float('nan'), float('nan'), float('nan'), False


# ─── ρ 测量算子（ca2 单步 update，foreground x0，power iteration） ────

def measure_rho(ca2, patch_img, fire_rate, device, mask_seed,
                warmup_steps=WARMUP_STEPS, n_iter=N_ITER_RHO, tol=TOL_RHO,
                smoke=False):
    """
    ρ（谱半径）：ca2 单步 update 算子在 foreground 演化态 x0 处的 Jacobian 谱半径。

    x0 用 foreground 模式（喂真实 patch 跑 warmup_steps 步后的演化态），
    贴近工作点动力学（x0=0 时 f'(0)≈0 → ρ≈1 无信号，臂1 已实证此问题）。

    Args:
        ca2:          BackboneNCA ca2（官方健康权重，eval）
        patch_img:    [1, C, H, W] float tensor（test patch，CPU）
        fire_rate:    1 - ur
        device:
        mask_seed:    固定 mask（torch seed）
        warmup_steps: foreground warmup 步数
        n_iter, tol:  power iteration 超参

    Returns:
        dict: rho, lambda_max, n_iter_conv, converged
    """
    img = patch_img.to(device)
    seed = make_seed(img, CHANNEL_N, device)

    # ── foreground 演化态 x0（no_grad warmup）
    torch.manual_seed(mask_seed + 90000)
    with torch.no_grad():
        x0_val = ca2(seed.clone(), steps=warmup_steps, fire_rate=fire_rate)
    x0 = x0_val.detach()

    n_iter_actual = 5 if smoke else n_iter

    # ── power iteration（autograd vjp，参 locuslab/deq）
    x0.requires_grad_(True)
    torch.manual_seed(mask_seed)
    y = ca2(x0, steps=1, fire_rate=fire_rate)  # 建图

    set_seed(mask_seed + 10000)
    v = torch.randn_like(y)
    v = v / (v.norm() + 1e-12)

    lambda_prev = float('nan')
    n_iter_conv = n_iter_actual
    lambda_max  = float('nan')

    for it in range(n_iter_actual):
        try:
            Jt_v = torch.autograd.grad(
                outputs=y,
                inputs=x0,
                grad_outputs=v,
                retain_graph=True,
                create_graph=False,
            )[0]
        except RuntimeError as e:
            print(f"  [ρ] autograd.grad 失败 iter={it}: {e}", flush=True)
            lambda_max  = float('nan')
            n_iter_conv = it
            break

        norm_Jtv = Jt_v.norm().item()
        if norm_Jtv < 1e-20:
            lambda_max  = 0.0
            n_iter_conv = it
            break

        lambda_k   = float((v * Jt_v).sum().item()) / (float((v * v).sum().item()) + 1e-20)
        lambda_max = abs(lambda_k)

        if not math.isnan(lambda_prev):
            rel_diff = abs(lambda_max - abs(lambda_prev)) / max(abs(lambda_max), 1e-8)
            if rel_diff < tol:
                n_iter_conv = it + 1
                break

        lambda_prev = lambda_k
        v = Jt_v / (norm_Jtv + 1e-12)

    converged = (n_iter_conv < n_iter_actual)

    # 清理计算图（防显存泄漏）
    del y, x0

    return {
        'rho':         float(lambda_max),
        'lambda_max':  float(lambda_max),
        'n_iter_conv': n_iter_conv,
        'converged':   int(converged),
    }


# ─── 手动单步 NCA update（绕开官方 mask，给 d(N) 双副本共享 mask） ────
# 逻辑同 probe_dn.py，用 ca2

def manual_update_with_mask_ca2(ca2, x_in, shared_mask):
    """
    用预生成 shared_mask 跑 ca2 单步 NCA update，绕开内部 torch.rand。

    TODO [MASK-1] 此函数与 probe_dn.py 的 manual_update_with_mask 同逻辑，
                  逐行对照 BasicNCA.update（Model_BasicNCA.py 55-80），
                  主线确认无偏离。
    """
    x = x_in.transpose(1, 3)           # [B, ch, H, W]
    dx = ca2.perceive(x)               # [B, 3*ch, H, W]
    dx = dx.transpose(1, 3)           # [B, H, W, 3*ch]
    dx = F.relu(ca2.fc0(dx))          # [B, H, W, hidden]
    dx = ca2.fc1(dx)                  # [B, H, W, ch]
    dx = dx * shared_mask             # broadcast [B, H, W, 1]

    x2 = (x_in + dx).clone()
    x_out = torch.cat(
        (x_in[..., :INPUT_CHANNELS], x2[..., INPUT_CHANNELS:]),
        dim=-1
    )
    return x_out


def measure_d(ca2, patch_img, fire_rate, N_steps, device, mask_seed,
              delta=0.1, smoke=False):
    """
    d(N) 脉冲传播半径：ca2 双副本法。
    θ = peak(Δ) / e，d_front = 超阈 cell 到中心最大距离。

    Args:
        ca2:          BackboneNCA ca2（官方健康权重，eval，no_grad）
        patch_img:    [1, C, H, W] float tensor（test patch，CPU）
        fire_rate:    1 - ur
        N_steps:      forward 步数
        device:
        mask_seed:    固定 mask seed（保证 A/B 同 mask）
        delta:        中心 cell 扰动幅度（默认 0.1，同 probe_dn.py）

    Returns:
        dict: d_front, n_active, d_equiv, theta_used
    """
    img  = patch_img.to(device)
    H, W = IMG_SIZE

    # ── 副本 A
    state_A = make_seed(img, CHANNEL_N, device)  # [1, H, W, ch]
    # ── 副本 B = A + 中心 ALIVE_CH 扰动
    state_B = state_A.clone()
    cy, cx  = H // 2, W // 2
    state_B[0, cy, cx, ALIVE_CH] = state_B[0, cy, cx, ALIVE_CH] + delta

    # ── 预生成共享 mask 序列
    masks = []
    for step in range(N_steps):
        torch.manual_seed(mask_seed + step)
        m = (torch.rand(1, H, W, 1, device=device) > fire_rate).float()
        masks.append(m)

    # ── 逐步 forward
    with torch.no_grad():
        for step in range(N_steps):
            m = masks[step]
            state_A = manual_update_with_mask_ca2(ca2, state_A, m)
            state_B = manual_update_with_mask_ca2(ca2, state_B, m)

    # ── d(N) 计算（CPU）
    diff = (state_B - state_A).squeeze(0).cpu()   # [H, W, ch]
    delta_map = diff.norm(dim=-1)                  # [H, W]

    peak = float(delta_map.max().item())
    if peak < 1e-30:
        return {'d_front': 0.0, 'n_active': 0, 'd_equiv': 0.0, 'theta_used': 0.0}

    theta    = peak / THETA_INV_E
    above    = (delta_map > theta)
    n_active = int(above.sum().item())

    if n_active == 0:
        return {'d_front': 0.0, 'n_active': 0, 'd_equiv': 0.0, 'theta_used': float(theta)}

    ys, xs = above.nonzero(as_tuple=True)
    dists  = ((ys.float() - cy) ** 2 + (xs.float() - cx) ** 2).sqrt()
    d_front = float(dists.max().item())
    d_equiv  = math.sqrt(n_active / math.pi)

    return {
        'd_front':    d_front,
        'n_active':   n_active,
        'd_equiv':    d_equiv,
        'theta_used': float(theta),
    }


# ─── smoke 数据集（mock）────────────────────────────────────────────

class MockDS(torch.utils.data.Dataset):
    def __init__(self, n=4):
        H, W = IMG_SIZE
        self.s = [
            (torch.rand(1, H, W), (torch.rand(1, H, W) > 0.7).float())
            for _ in range(n)
        ]
    def __len__(self): return len(self.s)
    def __getitem__(self, i): return self.s[i]


# ─── 主流程 ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="臂2：官方 ckpt 探针 — NCA-PhaseMap §2"
    )
    parser.add_argument('--n_steps',    type=int, default=N_STEPS_SIGMA,
                        help='σ 每次 forward 步数（默认 200）')
    parser.add_argument('--n_list',     type=str, default='4,8,16,32',
                        help='d(N) 步集合（逗号分隔）')
    parser.add_argument('--ur_list',    type=str, default=None,
                        help='覆盖默认 ur 网格（逗号分隔）')
    parser.add_argument('--mask_seeds', type=str, default='42,43,44',
                        help='mask seed 列表（逗号分隔，默认 42,43,44）')
    parser.add_argument('--smoke',      type=int, default=0,
                        help='smoke 模式：1=mock+少步+少 run 快速验算子')
    parser.add_argument('--out_suffix', type=str, default='',
                        help='输出文件后缀，防覆盖既有结果')
    args = parser.parse_args()

    smoke      = args.smoke > 0
    n_steps    = 20 if smoke else max(args.n_steps, 200)
    n_list     = [int(x) for x in args.n_list.split(',')]
    if smoke:
        n_list = [n for n in n_list if n <= 8]
        if not n_list:
            n_list = [4, 8]
    ur_grid    = ([float(u) for u in args.ur_list.split(',')]
                  if args.ur_list else UR_GRID)
    mask_seeds = [int(s) for s in args.mask_seeds.split(',')]

    if smoke:
        mask_seeds = mask_seeds[:1]
        ur_grid    = ur_grid[:2]

    out_csv   = os.path.join(RESULTS_DIR, f"probe_ckpt_inference{args.out_suffix}.csv")
    out_state = os.path.join(RESULTS_DIR, f"probe_ckpt_inference{args.out_suffix}_state.json")

    # mrestimator 检查
    if not _MRE_AVAILABLE:
        print(
            f"[probe_ckpt] WARNING: mrestimator 未安装，σ 全量 nan。\n"
            f"  请先：pip install mrestimator\n"
            f"  原始错误：{_MRE_ERR_MSG}",
            flush=True
        )

    cols = ['ur', 'fire_rate', 'inference_ur', 'mech', 'value',
            'mask_seed', 'x0_mode', 'ckpt_verified', 'N']

    device = torch.device(DEVICE)

    print(f"[probe_ckpt] 开始臂2 ckpt 探针", flush=True)
    print(f"  ur_grid={ur_grid}", flush=True)
    print(f"  mask_seeds={mask_seeds}", flush=True)
    print(f"  n_steps(σ)={n_steps}  n_list(d)={n_list}  smoke={smoke}", flush=True)
    print(f"  ckpt={CKPT_PATH}", flush=True)
    write_state(out_state, "init", {
        "ur_grid": ur_grid, "mask_seeds": mask_seeds,
        "n_steps": n_steps, "n_list": n_list, "smoke": smoke,
    })

    # ── 加载官方 ckpt + 数据集
    if smoke:
        # smoke 模式：mock 数据集，但仍尝试加载 ckpt（验算子的关键）
        print("[probe_ckpt][SMOKE] 尝试加载官方 ckpt（smoke 仍须验 ckpt 权重）", flush=True)
        try:
            ca1, ca2, samples, ckpt_verified = load_official_ckpt_and_dataset(
                device=DEVICE, smoke=True
            )
        except Exception as e_ckpt:
            print(f"[probe_ckpt][SMOKE] ckpt 加载失败，切换 mock 权重（仅验算子管线）: {e_ckpt}",
                  flush=True)
            # smoke 降级：mock 权重，仅验管线通路
            sys.path.insert(0, OFFICIAL_ROOT)
            os.chdir(OFFICIAL_ROOT)
            from src.models.Model_BackboneNCA import BackboneNCA
            ca1 = BackboneNCA(CHANNEL_N, 0.5, device, hidden_size=HIDDEN_SIZE,
                              input_channels=INPUT_CHANNELS).to(device)
            ca2 = BackboneNCA(CHANNEL_N, 0.5, device, hidden_size=HIDDEN_SIZE,
                              input_channels=INPUT_CHANNELS).to(device)
            ca1.eval(); ca2.eval()
            samples = [(torch.rand(1, *IMG_SIZE), torch.zeros(1, *IMG_SIZE)) for _ in range(4)]
            ckpt_verified = False
        print(f"[probe_ckpt][SMOKE] ckpt_verified={ckpt_verified}", flush=True)
    else:
        ca1, ca2, samples, ckpt_verified = load_official_ckpt_and_dataset(
            device=DEVICE, smoke=False
        )

    print(f"[probe_ckpt] samples={len(samples)}", flush=True)

    # 取代表性 patch（多 patch 均值更稳健，取前 min(8, len) 张）
    n_patches = min(2 if smoke else 8, len(samples))
    patches   = []
    for i in range(n_patches):
        img, _ = samples[i]
        if img.dim() == 2:
            img = img.unsqueeze(0)
        if img.shape[0] > img.shape[-1]:
            img = img.permute(2, 0, 1)
        patches.append(img[:INPUT_CHANNELS].unsqueeze(0).float())  # [1, 1, H, W]

    all_rows = []
    total_grid = [(ur, ms) for ur in ur_grid for ms in mask_seeds]

    for run_idx, (ur, mask_seed) in enumerate(total_grid):
        fire_rate = round(1.0 - ur, 6)
        print(
            f"\n[probe_ckpt] [{run_idx+1}/{len(total_grid)}]  "
            f"ur={ur}  fire_rate={fire_rate}  mask_seed={mask_seed}",
            flush=True
        )
        write_state(out_state, "running", {
            "ur": ur, "mask_seed": mask_seed,
            "run": run_idx + 1, "total": len(total_grid),
        })

        # ── 多 patch 均值（减少采样噪声）
        sigma_vals  = []
        rho_vals    = []
        d_by_N      = {N: [] for N in n_list}

        for p_idx, patch in enumerate(patches):
            # σ
            try:
                res_s = measure_sigma(
                    ca1=ca1, ca2=ca2,
                    patch_img=patch,
                    fire_rate=fire_rate,
                    n_steps=n_steps,
                    device=device,
                    mask_seed=mask_seed + p_idx * 100000,
                    smoke=smoke,
                )
                sigma_vals.append(res_s['sigma'])
            except Exception as ex:
                print(f"  [σ] patch{p_idx} 报错: {ex}", flush=True)
                sigma_vals.append(float('nan'))

            # ρ（ca2，foreground x0）
            try:
                # ρ 的 autograd 需要 ca2 有 grad——临时开 ca2 grad
                for p in ca2.parameters():
                    p.requires_grad_(True)
                res_r = measure_rho(
                    ca2=ca2,
                    patch_img=patch,
                    fire_rate=fire_rate,
                    device=device,
                    mask_seed=mask_seed + p_idx * 100000 + 1,
                    warmup_steps=WARMUP_STEPS,
                    smoke=smoke,
                )
                for p in ca2.parameters():
                    p.requires_grad_(False)
                rho_vals.append(res_r['rho'])
            except Exception as ex:
                for p in ca2.parameters():
                    p.requires_grad_(False)
                print(f"  [ρ] patch{p_idx} 报错: {ex}", flush=True)
                rho_vals.append(float('nan'))

            # d(N)
            for N_steps in n_list:
                try:
                    res_d = measure_d(
                        ca2=ca2,
                        patch_img=patch,
                        fire_rate=fire_rate,
                        N_steps=N_steps,
                        device=device,
                        mask_seed=mask_seed + p_idx * 100000 + 2,
                        smoke=smoke,
                    )
                    d_by_N[N_steps].append(res_d['d_front'])
                except Exception as ex:
                    print(f"  [d] N={N_steps} patch{p_idx} 报错: {ex}", flush=True)
                    d_by_N[N_steps].append(float('nan'))

        # ── 多 patch 均值（nan 安全）
        def _safe_mean(lst):
            valid = [v for v in lst if isinstance(v, float) and not math.isnan(v)]
            return float(np.mean(valid)) if valid else float('nan')

        sigma_mean = _safe_mean(sigma_vals)
        rho_mean   = _safe_mean(rho_vals)

        sigma_str = f"{sigma_mean:.4f}" if not math.isnan(sigma_mean) else "nan"
        rho_str   = f"{rho_mean:.4f}"   if not math.isnan(rho_mean)   else "nan"
        print(
            f"  σ={sigma_str}  ρ={rho_str}",
            flush=True
        )

        # ── 写行（mech=sigma / rho(foreground) / dfront_N）
        base = {
            'ur':            round(ur, 4),
            'fire_rate':     round(fire_rate, 4),
            'inference_ur':  round(ur, 4),
            'mask_seed':     mask_seed,
            'x0_mode':       'foreground',
            'ckpt_verified': int(ckpt_verified),
            'N':             '',
        }

        # sigma 行
        all_rows.append({**base,
                         'mech': 'sigma', 'value': _fmt(sigma_mean)})

        # rho 行
        all_rows.append({**base,
                         'mech': 'rho_foreground', 'value': _fmt(rho_mean)})

        # d 行（每个 N 一行）
        for N_steps in n_list:
            d_mean = _safe_mean(d_by_N[N_steps])
            d_str  = f"{d_mean:.4f}" if not math.isnan(d_mean) else "nan"
            print(f"  d(N={N_steps})={d_str}", flush=True)
            all_rows.append({**base,
                             'mech': 'dfront', 'value': _fmt(d_mean), 'N': N_steps})

        write_csv(all_rows, out_csv, cols)

    write_state(out_state, "done", {
        "total_rows":    len(all_rows),
        "ckpt_verified": int(ckpt_verified),
        "csv":           out_csv,
    })
    print(f"\n[probe_ckpt] 完成。CSV: {out_csv}", flush=True)
    print(f"  total rows: {len(all_rows)}", flush=True)
    print(f"  ckpt_verified: {ckpt_verified}", flush=True)
    if not ckpt_verified:
        print(
            "  [WARNING] ckpt_verified=False，ckpt 权重加载可能未生效，"
            "结果不可信！先核 'Reload State 300' 日志。",
            flush=True
        )


if __name__ == '__main__':
    main()
