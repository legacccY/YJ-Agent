"""G_mech_traj.py — 臂1 主：真训练 run 逐 step 机制量时序
服务项目：NCA-PhaseMap / 补2 机制段·臂1（时序先驱 + 早期预测）

Fork G_gradient_traj.py run_traj（Adam/pool/no-clip 主条件/dice_proxy 零偏离）。
每 k step（默认 k=5，--mech_interval）在当前权重快照上测 σ(t)/d(t)/ρ(t)：
  - 快照语义：torch.no_grad() + 临时 deepcopy 当前 ca_list，测量前向不污染训练图。
    注：逐 step 当前权重快照测，非终态。
  - σ(t)：复用 probe_sigma estimate_sigma_mre——快照网上额外空跑 N_roll 步
    （默认 200，--sigma_rollout），收活跃 cell 序列→estimate_sigma_mre。
    固定用该 run 第一个 batch patch（跑前冻结，跨 step 同 patch，
    保证 σ 变化只来自权重变化）。
  - d(t)：复用 probe_dn 双副本算子，N=16，同 mask A/B，θ=peak/e。
  - ρ(t)：廉价对照，power iteration foreground x0，留列不主押（臂2已验 flat）。

被试矩阵（真训练 run）：
  BraTS ur∈{0.50,0.65,0.80}（data_brats.BraTSSliceDataset）
  Hippo ur∈{0.30,0.45}（HipSliceDataset）
  各 seed{42,43,44}；clip=None 主 + clip=1.0 对照
  clip=1.0 对照仅加在：BraTS ur=0.80 + Hippo ur=0.45 两档
  共 15 no-clip run + 4 clip=1.0 对照 run = 19 run

300 step。

输出：
  results/G_mech_traj_<tag>.csv
  列：run_id, dataset, ur, clip_norm, seed, step,
      dice_proxy, fg_ratio, diverged,
      sigma_t, dfront_t, rho_t
  results/G_mech_state.json  心跳（逐 run 更新）

入口：
  python G_mech_traj.py --run_id brats_050   （单档）
  python G_mech_traj.py --all                （全被试矩阵）
  python G_mech_traj.py --run_id brats_050 --smoke 1

算力提示：σ 每 k=5 step 跑 N_roll=200 步快照，60 快照/run × N_roll=200 → 大头。
  主线可降本：--mech_interval 10 --sigma_rollout 150

环境变量：
  MEDNCA_ROOT    Med-NCA 根目录
  BRATS_ROOT     BraTS test/ 目录
  PHASEMAP_OUT   输出根目录
"""

import os
import sys
import csv
import copy
import json
import math
import time
import argparse
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.utils.data import DataLoader

# ─── mrestimator import（容错，同 probe_sigma） ────────────────────────
try:
    import mrestimator as mre
    _MRE_AVAILABLE = True
except ImportError as _mre_err:
    _MRE_AVAILABLE = False
    _MRE_ERR_MSG = str(_mre_err)

# ─── 路径常量 ─────────────────────────────────────────────────────────
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

# ─── 超参（零偏离官方，复用 G_gradient_traj 口径） ──────────────────────
DEVICE         = "cuda:0" if torch.cuda.is_available() else "cpu"
IMG_SIZE       = (64, 64)
ABLATION_STEPS = 300
LR             = 16e-4
BETAS          = (0.5, 0.5)
CHANNEL_N      = 16
HIDDEN_SIZE    = 128
INFERENCE_STEPS_EVAL = 16
FIXED_INIT_VAR = 0.01

INPUT_CHANNELS = 1
ALIVE_CH       = 1          # alive channel（同 sweep pred=x[...,1:2]）
THETA_INV_E    = math.e     # θ = peak(Δ) / e（d(N) 标准，probe_dn 口径）
EPS_ACTIVE_QUANTILE = 0.90  # eps_active 标定分位（同 probe_sigma）

# power iteration 超参（ρ 廉价对照）
N_ITER_RHO = 50     # 训练内快照用，不需 100 iter（廉价优先）
TOL_RHO    = 1e-5

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

# ─── 被试矩阵（臂1，19 run） ─────────────────────────────────────────
# run_id 格式：{dataset}_{ur×100:03d}
# no-clip 主条件：15 run；clip=1.0 对照：4 run（ur 最高档 BraTS0.80+Hippo0.45）
_ALL_RUNS = [
    # BraTS no-clip
    {'run_id': 'brats_050', 'dataset': 'brats', 'ur': 0.50, 'clip': None},
    {'run_id': 'brats_065', 'dataset': 'brats', 'ur': 0.65, 'clip': None},
    {'run_id': 'brats_080', 'dataset': 'brats', 'ur': 0.80, 'clip': None},
    # Hippo no-clip
    {'run_id': 'hippo_030', 'dataset': 'hippo', 'ur': 0.30, 'clip': None},
    {'run_id': 'hippo_045', 'dataset': 'hippo', 'ur': 0.45, 'clip': None},
    # clip=1.0 对照（高 ur 两档）
    {'run_id': 'brats_080_clip1', 'dataset': 'brats', 'ur': 0.80, 'clip': 1.0},
    {'run_id': 'hippo_045_clip1', 'dataset': 'hippo', 'ur': 0.45, 'clip': 1.0},
]
SEEDS = [42, 43, 44]


# ─── 工具函数 ─────────────────────────────────────────────────────────

def set_seed(s):
    np.random.seed(s)
    torch.manual_seed(s)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(s)


def dice_loss_fn(logit, target, smooth=1.0):
    pred  = torch.sigmoid(logit).flatten()
    tgt   = target.flatten()
    inter = (pred * tgt).sum()
    return 1.0 - (2.0 * inter + smooth) / (pred.sum() + tgt.sum() + smooth)


def write_state(path, phase, extra=None):
    state = {"phase": phase, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")}
    if extra:
        state.update(extra)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def _fmt(v):
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return 'nan'
    if isinstance(v, float):
        return round(v, 8)
    return v


# ─── 路径 patch（Hippo 构造用） ──────────────────────────────────────

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


# ─── 数据集构造 ──────────────────────────────────────────────────────

class HipSliceDataset(torch.utils.data.Dataset):
    """Hippocampus 切片数据集，复用 G_gradient_traj 口径。"""
    def __init__(self):
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
        ca1 = BackboneNCA(CHANNEL_N, 0.5, device, hidden_size=HIDDEN_SIZE,
                          input_channels=INPUT_CHANNELS).to(device)
        ca2 = BackboneNCA(CHANNEL_N, 0.5, device, hidden_size=HIDDEN_SIZE,
                          input_channels=INPUT_CHANNELS).to(device)
        agent_tmp = Agent_Med_NCA([ca1, ca2])
        exp_tmp   = Experiment(config, dataset_nii, [ca1, ca2], agent_tmp)
        patch_experiment_paths(exp_tmp)
        dataset_nii.set_experiment(exp_tmp)
        exp_tmp.set_model_state('train')
        dataset_nii.set_size(IMG_SIZE)
        self.samples = []
        for idx in range(len(dataset_nii)):
            _, img_np, lbl_np = dataset_nii[idx]
            img = torch.from_numpy(img_np).permute(2, 0, 1).float()
            lbl = torch.from_numpy(lbl_np).permute(2, 0, 1).float()
            self.samples.append((img, lbl))

    def __len__(self): return len(self.samples)
    def __getitem__(self, idx): return self.samples[idx]


def load_dataset(dataset_name, brats_root, smoke):
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
        return MockDS()

    if dataset_name == 'hippo':
        return HipSliceDataset()
    else:  # brats
        exp_dir = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, exp_dir)
        from data_brats import BraTSSliceDataset
        return BraTSSliceDataset(data_root=brats_root, fg_thresh=0.02)


# ─── Pool（同 G_gradient_traj） ──────────────────────────────────────

class SimplePool:
    def __init__(self, maxsize=40):
        self.pool = {}
        self.maxsize = maxsize

    def __len__(self): return len(self.pool)

    def get(self, idx, seed_tensor, device):
        if idx in self.pool:
            return self.pool[idx].to(device)
        return seed_tensor

    def put(self, idx, state_tensor):
        if len(self.pool) >= self.maxsize:
            k = next(iter(self.pool))
            del self.pool[k]
        self.pool[idx] = state_tensor.detach().cpu()


def make_seed(img, channel_n, device):
    B, C, H, W = img.shape
    seed = torch.zeros(B, H, W, channel_n, device=device)
    seed[..., :C] = img.permute(0, 2, 3, 1)
    return seed


def build_nca(device):
    sys.path.insert(0, OFFICIAL_ROOT)
    os.chdir(OFFICIAL_ROOT)
    from src.models.Model_BackboneNCA import BackboneNCA
    ca = BackboneNCA(CHANNEL_N, 0.5, device, hidden_size=HIDDEN_SIZE,
                     input_channels=INPUT_CHANNELS).to(device)
    with torch.no_grad():
        nn.init.normal_(ca.fc0.weight, mean=0.0, std=FIXED_INIT_VAR)
        if ca.fc0.bias is not None:
            nn.init.zeros_(ca.fc0.bias)
    return ca


# ─── 机制量快照测量器 ─────────────────────────────────────────────────

def _mre_estimate(arr):
    """
    mrestimator 调用（同 probe_sigma/probe_ckpt_inference 口径）。
    返回 (sigma, ci_low, ci_high, ok_flag)。
    """
    if not _MRE_AVAILABLE:
        return float('nan'), float('nan'), float('nan'), False
    if len(arr) < 20:
        return float('nan'), float('nan'), float('nan'), False

    kmax = max(10, len(arr) // 2 - 1)
    try:
        res = mre.full_analysis(
            data=arr,
            dt=1,
            dtunit='step',
            method='stationarymean',
            kmax=kmax,
            showoverview=False,
        )
        if not res.fits:
            raise ValueError("fits 为空")
        fit0  = res.fits[0]
        sigma = float(fit0.mre)
        m_err = float(fit0.mrestderr) if fit0.mrestderr is not None else float('nan')
        ci_lo = sigma - m_err if not math.isnan(m_err) else float('nan')
        ci_hi = sigma + m_err if not math.isnan(m_err) else float('nan')
        return sigma, ci_lo, ci_hi, True
    except Exception as e1:
        try:
            kmax_fb = max(10, len(arr) // 2 - 1)
            coeffs  = mre.coefficients(arr, steps=(1, kmax_fb), method='stationarymean')
            fit     = mre.fit(coeffs)
            sigma   = float(fit.mre)
            m_err   = float(fit.mrestderr) if fit.mrestderr is not None else float('nan')
            ci_lo   = sigma - m_err if not math.isnan(m_err) else float('nan')
            ci_hi   = sigma + m_err if not math.isnan(m_err) else float('nan')
            return sigma, ci_lo, ci_hi, True
        except Exception:
            return float('nan'), float('nan'), float('nan'), False


def measure_sigma_snapshot(ca_snap, fixed_patch, fire_rate, n_roll, device, snap_seed):
    """
    σ(t) 快照测量：在 deepcopy 快照权重上额外空跑 n_roll 步，
    收活跃 cell 序列 → estimate_sigma_mre。

    ca_snap:      deepcopy 的训练 ca_list（列表，取最后一个 ca 测，对齐补1 ca2）
    fixed_patch:  该 run 冻结的 batch patch [B, C, H, W]（跨 step 同一 patch）
    fire_rate:    1 - ur
    n_roll:       rollout 步数（默认 200）
    snap_seed:    随机种子（与训练 seed 隔离）

    注：逐 step 当前权重快照测，非终态。快照不污染训练图。
    """
    # 用最后一个 ca（对齐 G_traj 的 ca2 语义）
    ca = ca_snap[-1]
    ca.eval()

    img = fixed_patch[:1].to(device)      # 取 1 张，固定跨 step
    seed_x = make_seed(img, CHANNEL_N, device)  # [1, H, W, ch]

    # eps_active 标定（P90 step1 全场 |state|）
    torch.manual_seed(snap_seed)
    with torch.no_grad():
        x1 = ca(seed_x.clone(), steps=1, fire_rate=fire_rate)
    eps_active = float(np.quantile(x1.abs().cpu().numpy().flatten(), EPS_ACTIVE_QUANTILE))
    if eps_active < 1e-10:
        eps_active = 1e-10

    # 空跑 n_roll 步收 A(t)
    activity_series = []
    x_run = seed_x.clone()
    torch.manual_seed(snap_seed + 1)
    with torch.no_grad():
        for t in range(n_roll):
            x_run = ca(x_run, steps=1, fire_rate=fire_rate)
            alive_count = int((x_run[..., ALIVE_CH].abs() > eps_active).sum().item())
            activity_series.append(float(alive_count))

    arr = np.array(activity_series, dtype=np.float64)
    sigma, ci_lo, ci_hi, mre_ok = _mre_estimate(arr)
    return float(sigma)   # 只返回点估，CI 不写入逐 step csv（轻量）


def measure_d_snapshot(ca_snap, fixed_patch, fire_rate, device, snap_seed,
                        N_steps=16, delta=0.1):
    """
    d(t) 快照测量：双副本算子，N=16，θ=peak/e。
    同 probe_dn 协议，A/B 共享 mask 序列。

    ca_snap:      deepcopy 的训练 ca_list（取最后一个 ca）
    fixed_patch:  该 run 冻结的 batch patch [B, C, H, W]
    """
    ca = ca_snap[-1]
    ca.eval()

    img  = fixed_patch[:1].to(device)    # [1, 1, H, W]
    H, W = IMG_SIZE

    state_A = make_seed(img, CHANNEL_N, device)  # [1, H, W, ch]
    state_B = state_A.clone()
    cy, cx  = H // 2, W // 2
    state_B[0, cy, cx, ALIVE_CH] = state_B[0, cy, cx, ALIVE_CH] + delta

    # 预生成 N 步共享 mask（A/B 完全一致，同 probe_dn 协议）
    masks = []
    mask_seed_base = snap_seed * 10000
    for step in range(N_steps):
        torch.manual_seed(mask_seed_base + step)
        m = (torch.rand(1, H, W, 1, device=device) > fire_rate).float()
        masks.append(m)

    with torch.no_grad():
        for step in range(N_steps):
            m = masks[step]
            state_A = _manual_update(ca, state_A, m)
            state_B = _manual_update(ca, state_B, m)

    # d_front 计算（CPU）
    diff      = (state_B - state_A).squeeze(0).cpu()   # [H, W, ch]
    delta_map = diff.norm(dim=-1)                       # [H, W]
    peak      = float(delta_map.max().item())

    if peak < 1e-30:
        return 0.0

    theta    = peak / THETA_INV_E
    above    = (delta_map > theta)
    n_active = int(above.sum().item())
    if n_active == 0:
        return 0.0

    ys, xs  = above.nonzero(as_tuple=True)
    dists   = ((ys.float() - cy) ** 2 + (xs.float() - cx) ** 2).sqrt()
    d_front = float(dists.max().item())
    return d_front


def _manual_update(ca, x_in, shared_mask):
    """
    手动单步 NCA update（绕开官方 mask，给双副本共享 mask）。
    逻辑同 probe_dn.manual_update_with_mask，对照 BasicNCA.update。
    TODO [MASK-1] 主线运行前对照 Model_BasicNCA.py 55-80 确认零偏离。
    """
    x   = x_in.transpose(1, 3)           # [B, ch, H, W]
    dx  = ca.perceive(x)                 # [B, 3*ch, H, W]
    dx  = dx.transpose(1, 3)            # [B, H, W, 3*ch]
    dx  = F.relu(ca.fc0(dx))            # [B, H, W, hidden]
    dx  = ca.fc1(dx)                    # [B, H, W, ch]
    dx  = dx * shared_mask              # broadcast [B, H, W, 1]
    x2  = (x_in + dx).clone()
    x_out = torch.cat(
        (x_in[..., :INPUT_CHANNELS], x2[..., INPUT_CHANNELS:]),
        dim=-1
    )
    return x_out


def measure_rho_snapshot(ca_snap, fixed_patch, fire_rate, device, snap_seed,
                          n_iter=N_ITER_RHO, tol=TOL_RHO):
    """
    ρ(t) 廉价对照：power iteration foreground x0，ca 最后一个。
    用 n_iter=50，容忍未收敛（廉价对照，不主押）。
    """
    ca = ca_snap[-1]
    img  = fixed_patch[:1].to(device)
    seed = make_seed(img, CHANNEL_N, device)

    # foreground x0：warmup 4 步（快照内省算力）
    torch.manual_seed(snap_seed + 90000)
    with torch.no_grad():
        x0_val = ca(seed.clone(), steps=4, fire_rate=fire_rate)
    x0 = x0_val.detach().clone()

    # power iteration（autograd vjp）
    # 临时开 ca grad
    for p in ca.parameters():
        p.requires_grad_(True)
    x0.requires_grad_(True)
    torch.manual_seed(snap_seed)
    try:
        y = ca(x0, steps=1, fire_rate=fire_rate)
    except Exception:
        for p in ca.parameters():
            p.requires_grad_(False)
        return float('nan')

    set_seed(snap_seed + 10000)
    v = torch.randn_like(y)
    v = v / (v.norm() + 1e-12)

    lambda_prev = float('nan')
    lambda_max  = float('nan')

    for it in range(n_iter):
        try:
            Jt_v = torch.autograd.grad(
                outputs=y,
                inputs=x0,
                grad_outputs=v,
                retain_graph=True,
                create_graph=False,
            )[0]
        except RuntimeError:
            break

        norm_Jtv = Jt_v.norm().item()
        if norm_Jtv < 1e-20:
            lambda_max = 0.0
            break

        lambda_k   = float((v * Jt_v).sum().item()) / (float((v * v).sum().item()) + 1e-20)
        lambda_max = abs(lambda_k)

        if not math.isnan(lambda_prev):
            rel_diff = abs(lambda_max - abs(lambda_prev)) / max(abs(lambda_max), 1e-8)
            if rel_diff < tol:
                break

        lambda_prev = lambda_k
        v = Jt_v / (norm_Jtv + 1e-12)

    # 清理计算图（防显存泄漏）
    del y, x0

    for p in ca.parameters():
        p.requires_grad_(False)

    return float(lambda_max)


# ─── 逐 step 训练 + 机制量快照（臂1 核心） ──────────────────────────

def run_mech_traj(ca_list, train_ds, update_rate, n_steps, device, seed_val,
                  clip_norm, run_id, dataset_name, csv_path,
                  mech_interval, sigma_rollout, snap_seed_base):
    """
    逐 step 训练（Adam/pool/no-clip 主条件，零偏离 G_gradient_traj run_traj），
    每 mech_interval step 在当前权重快照上测 σ(t)/d(t)/ρ(t)。

    快照语义：torch.no_grad() + 临时 deepcopy，测量不污染训练图。
    固定 patch：该 run 第一个 batch patch（跑前冻结），保证 σ 变化只来自权重。

    mech_interval:  测量间隔（默认 5）
    sigma_rollout:  σ 快照 forward 步数（默认 200，算力大头）
    snap_seed_base: 测量用种子基（与训练 seed 隔离，默认 9999 + run_idx）

    clip_norm=None → no-clip（主条件）
    clip_norm=1.0  → 对照
    """
    fire_rate  = 1.0 - update_rate
    clip_label = str(clip_norm) if clip_norm is not None else 'None'

    set_seed(seed_val)
    optimizer = [optim.Adam(ca.parameters(), lr=LR, betas=BETAS) for ca in ca_list]
    loader    = DataLoader(train_ds, batch_size=4, shuffle=True,
                           num_workers=0, pin_memory=False)
    pool      = SimplePool(maxsize=40)

    diverged = False

    # CSV 列名（机制量列加在 dice_proxy/fg_ratio/diverged 后）
    cols = ['run_id', 'dataset', 'ur', 'fire_rate', 'clip_norm', 'seed', 'step',
            'dice_proxy', 'fg_ratio', 'diverged',
            'sigma_t', 'dfront_t', 'rho_t']

    file_exists = os.path.exists(csv_path)
    f_csv = open(csv_path, 'a', newline='', encoding='utf-8')
    writer = csv.DictWriter(f_csv, fieldnames=cols, extrasaction='ignore')
    if not file_exists:
        writer.writeheader()

    # 固定 patch：取第一个 batch（跑前冻结，跨 step 同 patch）
    fixed_patch = None
    for img_b, lbl_b in loader:
        fixed_patch = img_b.detach().clone()  # [B, C, H, W]，CPU
        break
    if fixed_patch is None:
        raise RuntimeError(f"[mech_traj] 数据集为空: run_id={run_id} seed={seed_val}")

    step = 0
    try:
        while step < n_steps:
            for img, lbl in loader:
                if step >= n_steps:
                    break

                img, lbl = img.to(device), lbl.to(device)
                seed = make_seed(img, CHANNEL_N, device)

                if len(pool) > 0:
                    for bi in range(seed.shape[0]):
                        seed[bi] = pool.get(step * 1000 + bi, seed[bi], device)

                for opt in optimizer:
                    opt.zero_grad()

                x = seed
                for ca in ca_list:
                    x = ca(x, steps=INFERENCE_STEPS_EVAL, fire_rate=fire_rate)

                pred         = x[..., 1:2]
                lbl_permuted = lbl.permute(0, 2, 3, 1)

                if lbl_permuted.sum() == 0:
                    step += 1
                    continue

                loss     = dice_loss_fn(pred, lbl_permuted)
                loss_val = loss.item()

                is_div = math.isnan(loss_val) or math.isinf(loss_val)
                if is_div:
                    diverged = True

                if not is_div:
                    loss.backward()

                    # clip（None=no-clip 主条件）
                    if clip_norm is not None:
                        for ca in ca_list:
                            torch.nn.utils.clip_grad_norm_(ca.parameters(), clip_norm)

                    for opt in optimizer:
                        opt.step()

                    dice_proxy = float(1.0 - loss_val)

                    with torch.no_grad():
                        fg_ratio = float((torch.sigmoid(pred) > 0.5).float().mean().item())

                    for bi in range(x.shape[0]):
                        pool.put(step * 1000 + bi, x[bi])

                else:
                    dice_proxy = float('nan')
                    fg_ratio   = float('nan')

                # ── 每 mech_interval step 测机制量快照 ──────────────
                sigma_t  = float('nan')
                dfront_t = float('nan')
                rho_t    = float('nan')

                if step % mech_interval == 0:
                    snap_seed = snap_seed_base + step  # 每 step 独立种子

                    # deepcopy 快照（不污染训练图）
                    with torch.no_grad():
                        ca_snap = [copy.deepcopy(ca).to(device) for ca in ca_list]
                        for ca_s in ca_snap:
                            ca_s.eval()

                    fp_device = fixed_patch.to(device) if fixed_patch is not None else None

                    # σ(t)
                    if fp_device is not None and not is_div:
                        try:
                            sigma_t = measure_sigma_snapshot(
                                ca_snap, fp_device, fire_rate,
                                sigma_rollout, device, snap_seed
                            )
                        except Exception as ex:
                            print(f"  [σ] step={step} 报错: {ex}", flush=True)
                            sigma_t = float('nan')

                    # d(t)，N=16
                    if fp_device is not None and not is_div:
                        try:
                            dfront_t = measure_d_snapshot(
                                ca_snap, fp_device, fire_rate, device, snap_seed,
                                N_steps=16, delta=0.1
                            )
                        except Exception as ex:
                            print(f"  [d] step={step} 报错: {ex}", flush=True)
                            dfront_t = float('nan')

                    # ρ(t)（廉价对照，可选）
                    if fp_device is not None and not is_div:
                        try:
                            rho_t = measure_rho_snapshot(
                                ca_snap, fp_device, fire_rate, device, snap_seed
                            )
                        except Exception as ex:
                            print(f"  [ρ] step={step} 报错: {ex}", flush=True)
                            rho_t = float('nan')

                    # 显式释放快照（省显存）
                    del ca_snap
                    torch.cuda.empty_cache() if torch.cuda.is_available() else None

                # ── 写 csv ──────────────────────────────────────────
                row = {
                    'run_id':    run_id,
                    'dataset':   dataset_name,
                    'ur':        round(update_rate, 4),
                    'fire_rate': round(fire_rate, 4),
                    'clip_norm': clip_label,
                    'seed':      seed_val,
                    'step':      step,
                    'dice_proxy': _fmt(dice_proxy),
                    'fg_ratio':   _fmt(fg_ratio),
                    'diverged':   int(diverged),
                    'sigma_t':    _fmt(sigma_t),
                    'dfront_t':   _fmt(dfront_t),
                    'rho_t':      _fmt(rho_t),
                }
                writer.writerow(row)
                f_csv.flush()

                if step % 50 == 0:
                    sigma_str = f"{sigma_t:.4f}" if not math.isnan(sigma_t) else "nan"
                    d_str     = f"{dfront_t:.4f}" if not math.isnan(dfront_t) else "nan"
                    print(
                        f"  step={step:4d}  dice={dice_proxy:.4f}  "
                        f"σ={sigma_str}  d={d_str}  div={int(diverged)}",
                        flush=True
                    )

                step += 1

    finally:
        f_csv.close()

    return diverged


# ─── 主流程 ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="G_mech_traj：臂1 真训练逐 step 机制量时序"
    )
    parser.add_argument('--run_id',
                        choices=[r['run_id'] for r in _ALL_RUNS],
                        default=None,
                        help='单个 run_id（与 --all 二选一）')
    parser.add_argument('--all', action='store_true',
                        help='跑全被试矩阵（所有 run_id × seed）')
    parser.add_argument('--smoke',    type=int, default=0,
                        help='smoke: 1=MockDS + 20 step + 1 seed + 快速 rollout')
    parser.add_argument('--mech_interval', type=int, default=5,
                        help='机制量测量间隔（step 数，默认 5）')
    parser.add_argument('--sigma_rollout', type=int, default=200,
                        help='σ 快照 forward 步数（默认 200，降本可用 150）')
    parser.add_argument('--brats_root', default=_BRATS_ROOT_DEFAULT,
                        help='BraTS test/ 目录')
    parser.add_argument('--seeds',   type=str, default=None,
                        help='覆盖 seed 列表（逗号分隔，默认 42,43,44）')
    parser.add_argument('--no_rho',  action='store_true',
                        help='跳过 ρ(t) 计算（省算力，对照不主押时可用）')
    args = parser.parse_args()

    smoke   = args.smoke > 0
    n_steps = 20 if smoke else ABLATION_STEPS
    mech_interval  = args.mech_interval
    sigma_rollout  = 20 if smoke else args.sigma_rollout
    seeds          = [int(s) for s in args.seeds.split(',')] if args.seeds else SEEDS
    if smoke:
        seeds = seeds[:1]

    # 确定要跑的 run 配置列表
    if args.all:
        runs_to_do = _ALL_RUNS
    elif args.run_id:
        runs_to_do = [r for r in _ALL_RUNS if r['run_id'] == args.run_id]
    else:
        parser.error("需要 --run_id 或 --all")

    out_state = os.path.join(RESULTS_DIR, "G_mech_state.json")

    if not _MRE_AVAILABLE:
        print(
            f"[G_mech] WARNING: mrestimator 未安装，σ 全量 nan。\n"
            f"  请先：pip install mrestimator\n"
            f"  原始错误：{_MRE_ERR_MSG}",
            flush=True
        )

    print(f"[G_mech] mech_interval={mech_interval}  sigma_rollout={sigma_rollout}",
          flush=True)
    print(f"[G_mech] run 配置数={len(runs_to_do)}  seeds={seeds}  n_steps={n_steps}",
          flush=True)

    write_state(out_state, "init", {
        "runs": [r['run_id'] for r in runs_to_do],
        "seeds": seeds, "n_steps": n_steps,
        "mech_interval": mech_interval, "sigma_rollout": sigma_rollout,
    })

    sys.path.insert(0, OFFICIAL_ROOT)
    os.chdir(OFFICIAL_ROOT)
    device = torch.device(DEVICE)

    total_runs = len(runs_to_do) * len(seeds)
    run_counter = 0

    for run_cfg in runs_to_do:
        run_id      = run_cfg['run_id']
        dataset_name = run_cfg['dataset']
        ur          = run_cfg['ur']
        clip_norm   = run_cfg['clip']
        clip_label  = str(clip_norm) if clip_norm is not None else 'None'

        out_csv = os.path.join(RESULTS_DIR, f"G_mech_traj_{run_id}.csv")

        # 清理旧 csv（本次重头跑）
        if os.path.exists(out_csv):
            os.remove(out_csv)

        print(f"\n[G_mech] === run_id={run_id}  dataset={dataset_name}  "
              f"ur={ur}  clip={clip_label}  n_seeds={len(seeds)} ===", flush=True)

        # 加载数据集（每个 run_id 共享同一数据集实例）
        print(f"[G_mech] 加载数据集 {dataset_name}...", flush=True)
        if smoke:
            train_ds = load_dataset('mock', args.brats_root, smoke=True)
        else:
            train_ds = load_dataset(dataset_name, args.brats_root, smoke=False)
        print(f"[G_mech] 数据集加载完，n={len(train_ds)}", flush=True)

        for seed_val in seeds:
            run_counter += 1
            print(
                f"\n[G_mech] [{run_counter}/{total_runs}]  "
                f"run_id={run_id}  seed={seed_val}",
                flush=True
            )
            write_state(out_state, "running", {
                "run_id": run_id, "seed": seed_val,
                "run_counter": run_counter, "total_runs": total_runs,
            })

            set_seed(seed_val)
            ca1 = build_nca(device)
            ca2 = build_nca(device)

            # snap_seed_base：与训练 seed 隔离（99999 + run_counter * 1000）
            snap_seed_base = 99999 + run_counter * 1000

            diverged = run_mech_traj(
                ca_list=[ca1, ca2],
                train_ds=train_ds,
                update_rate=ur,
                n_steps=n_steps,
                device=device,
                seed_val=seed_val,
                clip_norm=clip_norm,
                run_id=run_id,
                dataset_name=dataset_name,
                csv_path=out_csv,
                mech_interval=mech_interval,
                sigma_rollout=sigma_rollout,
                snap_seed_base=snap_seed_base,
            )

            print(f"  [G_mech] run_id={run_id} seed={seed_val}  "
                  f"diverged={diverged}", flush=True)

        print(f"\n[G_mech] run_id={run_id} 完成。CSV: {out_csv}", flush=True)

    write_state(out_state, "done", {
        "total_runs": total_runs,
        "run_ids": [r['run_id'] for r in runs_to_do],
    })
    print(f"\n[G_mech] 全部完成。state: {out_state}", flush=True)


if __name__ == '__main__':
    main()
