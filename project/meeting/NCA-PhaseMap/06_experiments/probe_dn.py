"""probe_dn.py — d(N) 脉冲传播半径探针 — NCA-PhaseMap 补2 §1
服务项目：NCA-PhaseMap / K-new-3 机制段（解耦路A）

方法（damage spreading，inspired by [cond-mat/9811159]）：
    受控随机初始化 BackboneNCA（fc0.w~N(0,0.01), fc0.b=0,
    fc1.w~N(0,0.01) 非零 [关键：旧M1 fc1=0→dx≡0→全nan bug]，fc1.b=0），
    不训练、不读训练 csv（破循环论证，测量协议）。

    双副本法：
      副本 A = 原始 seed 态（真实 patch 或合成背景图）。
      副本 B = A + 中心 cell 单通道扰动 δ=0.1（alive_ch=1）。
      A/B 用同一 fire_rate mask 序列跑 N 步 NCA forward——
        ⚠️  官方 BasicNCA.update 内部用 torch.rand 生成 mask（无外部传入接口）。
        本实现绕开 forward/update，在 probe 侧预生成 mask 张量序列，
        调用 perceive+fc0+fc1 后手动乘 mask，保证 A/B 完全一致。

    d(N) 前沿半径：
      每步差 Δ = |state_B − state_A|（全 channel L2）
      θ = max(Δ) × (1/e)           ← researcher 定：峰值的 1/e≈0.368
      d_front = max euclid dist to center over cells where Δ > θ
      n_active = # cells where Δ > θ
      d_equiv  = sqrt(n_active / π)  辅助

    扫描 N∈{4,8,16,32}，主报 N=16（对齐官方 inference_steps）。

【入口】
    python probe_dn.py [--dataset hippo|brats|synthetic|all]
                       [--n_list 4,8,16,32]
                       [--delta 0.1]
                       [--smoke 1]
                       [--out_suffix _test]

【输出】
    results/probe_dn.csv
    列: ur, fire_rate, dataset, init_seed, N,
        d_front, n_active, d_equiv, theta_used
    results/probe_dn_state.json  心跳

【环境变量（HPC）】
    MEDNCA_ROOT    Med-NCA 根目录
    BRATS_ROOT     BraTS test/ 目录
    PHASEMAP_OUT   输出根目录

TODO（主线跑前须确认）：
  [MASK-1] 本实现绕开官方 update，在 probe 侧手动生成 mask。
           手动 update 逻辑从 BasicNCA.update 逐行复制，须在 snapshot 时
           对照 D:\\YJ-Agent\\project\\meeting\\Med-NCA\\M3D-NCA-official\\
           src\\models\\Model_BasicNCA.py 行 55-80 确认零偏离。
  [MASK-2] BasicNCA.update 用 np.random（perceive 里的 sobel 是 np.outer，
           非 np.random；perceive BackboneNCA 版用 torch.conv2d，无 np.random）。
           确认：BackboneNCA.update 唯一随机源 = torch.rand（行 72）。
           本实现在每步 forward 前 torch.manual_seed(mask_seed_base+step)
           生成同一 mask 给 A/B，物理正确。np.random 无另外随机源（已核）。
  [MASK-3] x = x + dx * stochastic 是原地加后 clone（forward 里 .clone()），
           无 in-place 风险——但本实现手动复制 update，需确认 clone() 时机。
  [EPS-1]  eps_active 不在 d(N) 中直接使用（d(N) 用 θ=max(Δ)/e），
           但 SyntheticDS 背景图用 zero_tensor，需确认是否
           引入数值下溢（fire_rate 高时全场 Δ≈0 → θ≈0 → 无超阈 cell）。
  [THETA]  θ=峰值/e 是 researcher 定标准，本实现 1/e 用 Python math.e，
           确认与实验设计稿一致。
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

# ─── 路径常量（复用 probe_sigma / B1_B2_B3_sweep 口径） ─────────────
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

FIXED_INIT_VAR = 0.01   # N(0, 0.01) 对齐 sweep
ALIVE_CH       = 1      # alive channel index（同 sweep pred=x[...,1:2]）
INPUT_CHANNELS = 1      # 与 BackboneNCA input_channels 参数对齐

# ur 网格（对齐补1/补3）
UR_GRID = [0.25, 0.30, 0.35, 0.40, 0.45, 0.50,
           0.55, 0.60, 0.65, 0.70, 0.75, 0.80]

INIT_SEEDS = [42, 43, 44, 45, 46]

# N 步集合（看前沿增长斜率）
DEFAULT_N_LIST = [4, 8, 16, 32]

# 扰动幅度
DEFAULT_DELTA = 0.1

# θ 分母 = e（researcher 定标准：峰值的 1/e）
THETA_INV_E = math.e  # θ = max(Δ) / e

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


# ─── 受控初始化 NCA（复用 probe_sigma 骨架，零改协议） ───────────────

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
        fire_rate=0.5,         # 构造参数；实际 fire_rate 在 probe 侧手动传
        device=device,
        hidden_size=HIDDEN_SIZE,
        input_channels=INPUT_CHANNELS,
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


# ─── 手动单步 NCA update（绕开官方 update 随机，给双副本共享 mask）──
#
# TODO [MASK-1] 此函数逐行对照 BasicNCA.update（Model_BasicNCA.py 55-80）
#               + BackboneNCA.perceive（Model_BackboneNCA.py 21-29），
#               主线运行前须人工确认无偏离。
#
# 官方 update 流程（BasicNCA.update）：
#   x = x_in.transpose(1,3)          # [B, H, W, ch] → [B, ch, H, W]
#   dx = self.perceive(x)             # [B, 3*ch, H, W]
#   dx = dx.transpose(1,3)           # → [B, H, W, 3*ch]
#   dx = F.relu(self.fc0(dx))         # [B, H, W, hidden]
#   dx = self.fc1(dx)                 # [B, H, W, ch]
#   dx = dx * stochastic              # mask: [B, H, W, 1]  (broadcast)
#   x  = x + dx.transpose(1,3)       # [B, ch, H, W]
#   x  = x.transpose(1,3)            # [B, H, W, ch]
#
# 官方 forward（BasicNCA.forward）最后 clone 保留 input_channels 不变：
#   x2 = self.update(x, fire_rate).clone()
#   x  = torch.concat((x[...,:input_channels], x2[...,input_channels:]), 3)

def manual_update_with_mask(ca, x_in, shared_mask):
    """
    用预生成 shared_mask 跑单步 NCA update，绕开内部 torch.rand。

    Args:
        ca:           BackboneNCA 实例（eval，无 grad）
        x_in:         [B, H, W, ch]（in）
        shared_mask:  [B, H, W, 1] float tensor（0/1），A/B 共享同一对象

    Returns:
        x_out:        [B, H, W, ch]（out）

    TODO [MASK-3] 官方 forward 对 update 输出 .clone()，此处手动实现已包含
                  独立 tensor 返回，无 in-place 风险——但主线确认时对照行号。
    """
    x = x_in.transpose(1, 3)           # [B, ch, H, W]

    # perceive（BackboneNCA 版：两个 Conv2d）
    # TODO [MASK-1] 确认 perceive 是 BackboneNCA 而非 BasicNCA Sobel 版
    dx = ca.perceive(x)                 # [B, 3*ch, H, W]
    dx = dx.transpose(1, 3)            # [B, H, W, 3*ch]
    dx = F.relu(ca.fc0(dx))            # [B, H, W, hidden]
    dx = ca.fc1(dx)                    # [B, H, W, ch]
    dx = dx * shared_mask              # broadcast mask [B, H, W, 1] → [B, H, W, ch]

    x2 = (x_in + dx).clone()           # [B, H, W, ch]  clone 对齐官方 forward

    # 保留 input_channels 不变（对齐官方 forward 最后 concat）
    x_out = torch.cat(
        (x_in[..., :INPUT_CHANNELS], x2[..., INPUT_CHANNELS:]),
        dim=-1
    )
    return x_out


def precompute_masks(N, shape_BHW1, fire_rate, device, mask_seed_base):
    """
    预生成 N 步共享 mask 列表（A/B 双副本用同一序列）。

    每步 mask 用独立 seed = mask_seed_base + step，
    保证实验可复现且 A/B 完全一致（物理正确关键）。

    mask 值：1 = cell 激活（update 被采纳），对应官方：
        stochastic = (torch.rand(...) > fire_rate).float()
        即 fire_rate 越高 → 1 的比例越低（更稀疏）

    Args:
        N:              步数
        shape_BHW1:     (B, H, W, 1) tuple
        fire_rate:      1 - ur
        device:
        mask_seed_base: 基准 seed（建议 = 1000 * step_run_idx）

    Returns:
        List[Tensor]，len=N，每个 [B, H, W, 1] float
    """
    masks = []
    B, H, W, _ = shape_BHW1
    for step in range(N):
        torch.manual_seed(mask_seed_base + step)
        m = (torch.rand(B, H, W, 1, device=device) > fire_rate).float()
        masks.append(m)
    return masks


# ─── d(N) 单次前沿计算 ──────────────────────────────────────────────

def compute_d_front(state_A, state_B, H, W):
    """
    给定两副本某步末态，算 d_front / n_active / d_equiv / theta_used。

    Args:
        state_A:  [1, H, W, ch] tensor（CPU float）
        state_B:  [1, H, W, ch] tensor（CPU float）
        H, W:     空间尺寸

    Returns:
        dict: d_front, n_active, d_equiv, theta_used
              若无超阈 cell → d_front=0, n_active=0, d_equiv=0

    注：中心 = (H//2, W//2)（注入点）。
    """
    # 逐 cell L2（全 channel）
    diff = (state_B - state_A).squeeze(0)     # [H, W, ch]
    delta_map = diff.norm(dim=-1)             # [H, W]  L2 across channels

    peak = float(delta_map.max().item())
    if peak < 1e-30:
        # 全场无响应（fire_rate 极高或扰动被 mask 全挡）
        return {
            'd_front': 0.0,
            'n_active': 0,
            'd_equiv': 0.0,
            'theta_used': 0.0,
        }

    theta = peak / THETA_INV_E              # θ = peak / e

    above_mask = (delta_map > theta)        # [H, W] bool
    n_active = int(above_mask.sum().item())

    if n_active == 0:
        return {
            'd_front': 0.0,
            'n_active': 0,
            'd_equiv': 0.0,
            'theta_used': float(theta),
        }

    # 超阈 cell 坐标 → 到中心的最大欧氏距离
    cy, cx = H // 2, W // 2
    ys, xs = above_mask.nonzero(as_tuple=True)   # [n_active]
    ys = ys.float()
    xs = xs.float()
    dists = ((ys - cy) ** 2 + (xs - cx) ** 2).sqrt()
    d_front = float(dists.max().item())
    d_equiv  = math.sqrt(n_active / math.pi)

    return {
        'd_front':   d_front,
        'n_active':  n_active,
        'd_equiv':   d_equiv,
        'theta_used': float(theta),
    }


# ─── 单次 (ur, init_seed, N, dataset) 探针 ──────────────────────────

def run_probe_dn(ca, patch, ur, N_steps, device, init_seed, delta,
                 smoke=False):
    """
    双副本跑 N_steps 步，返回 N_steps 末步的 d(N) 指标。

    Args:
        ca:         BackboneNCA（受控 init，eval，no_grad）
        patch:      [1, C, H, W] float tensor（单张图，已在 CPU）
        ur:         update ratio（0~1）
        N_steps:    forward 步数
        device:
        init_seed:  用于 mask seed base（非权重 init，权重已由 build_controlled_nca 锁定）
        delta:      中心 cell 扰动幅度

    Returns:
        dict: d_front, n_active, d_equiv, theta_used
    """
    fire_rate = 1.0 - ur
    H, W      = patch.shape[2], patch.shape[3]

    # ── 副本 A（原始 seed 态）
    state_A = make_seed(patch.to(device), CHANNEL_N, device)  # [1, H, W, ch]

    # ── 副本 B = A + 中心单 cell ALIVE_CH 通道扰动
    state_B = state_A.clone()
    cy, cx  = H // 2, W // 2
    state_B[0, cy, cx, ALIVE_CH] = state_B[0, cy, cx, ALIVE_CH] + delta

    # ── 预生成共享 mask 序列（物理正确关键：A/B 同 mask）
    # mask_seed_base 用 init_seed * 10000 保证与权重 seed 不重叠
    mask_seed_base = init_seed * 10000
    masks = precompute_masks(
        N=N_steps,
        shape_BHW1=(1, H, W, 1),
        fire_rate=fire_rate,
        device=device,
        mask_seed_base=mask_seed_base,
    )

    # ── 逐步 forward（手动 update，A/B 同 mask）
    with torch.no_grad():
        for step in range(N_steps):
            m = masks[step]
            state_A = manual_update_with_mask(ca, state_A, m)
            state_B = manual_update_with_mask(ca, state_B, m)

    # ── d(N) 计算（在 CPU 上，省显存）
    result = compute_d_front(
        state_A.cpu(),
        state_B.cpu(),
        H, W
    )

    if smoke:
        print(
            f"    [SMOKE d(N)] ur={ur:.2f} N={N_steps} seed={init_seed} "
            f"d_front={result['d_front']:.3f} n_active={result['n_active']} "
            f"theta={result['theta_used']:.4e}",
            flush=True
        )

    return result


# ─── 合成中心脉冲背景图（纯架构传播，与前景占比解耦） ────────────────

class SyntheticDS(torch.utils.data.Dataset):
    """
    合成数据集：纯零背景图（[1, H, W]）。
    测「纯架构传播」与真实前景占比解耦。

    TODO [EPS-1] 纯零背景 → step1 全场 |state| ≈ 0（fire_rate 高时尤甚），
                 若 eps_active 用于其他量须确认不退化。
                 probe_dn 中 θ=peak/e，不依赖 eps_active，此处无依赖问题。
    """
    def __init__(self, n=16):
        H, W = IMG_SIZE
        self.imgs = [torch.zeros(1, H, W) for _ in range(n)]

    def __len__(self): return len(self.imgs)
    def __getitem__(self, i): return self.imgs[i], torch.zeros(1, *IMG_SIZE)


# ─── 数据集加载 ───────────────────────────────────────────────────────

def load_dataset(dataset_name, brats_root, smoke):
    """
    返回 (dataset, label_str)。
    取一张代表性 patch 用于双副本实验。
    """
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

    if dataset_name == 'synthetic':
        return SyntheticDS(n=16), "synthetic"

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
        ca1_tmp = BackboneNCA(CHANNEL_N, 0.5, device, hidden_size=HIDDEN_SIZE,
                              input_channels=INPUT_CHANNELS).to(device)
        ca2_tmp = BackboneNCA(CHANNEL_N, 0.5, device, hidden_size=HIDDEN_SIZE,
                              input_channels=INPUT_CHANNELS).to(device)
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


# ─── 主流程 ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="d(N) 脉冲传播半径探针 — NCA-PhaseMap §1"
    )
    parser.add_argument('--dataset',
                        choices=['hippo', 'brats', 'synthetic', 'all'],
                        default='all',
                        help='数据集：hippo|brats|synthetic|all（默认 all）')
    parser.add_argument('--n_list',    type=str, default='4,8,16,32',
                        help='N 步集合（逗号分隔，默认 4,8,16,32）')
    parser.add_argument('--delta',     type=float, default=DEFAULT_DELTA,
                        help='中心 cell 扰动幅度（默认 0.1）')
    parser.add_argument('--ur_list',   type=str, default=None,
                        help='覆盖默认 ur 网格（逗号分隔）')
    parser.add_argument('--seeds',     type=str, default='42,43,44,45,46',
                        help='init_seed 列表（逗号分隔）')
    parser.add_argument('--brats_root', default=_BRATS_ROOT_DEFAULT)
    parser.add_argument('--smoke',     type=int, default=0,
                        help='smoke 模式：1=MockDS + 仅前 2 run + N=[4,8]')
    parser.add_argument('--out_suffix', type=str, default='',
                        help='输出文件后缀，防覆盖既有结果')
    args = parser.parse_args()

    smoke     = args.smoke > 0
    n_list    = [int(x) for x in args.n_list.split(',')]
    if smoke:
        n_list = [n for n in n_list if n <= 8]
        if not n_list:
            n_list = [4, 8]
    init_seeds = [int(s) for s in args.seeds.split(',')]
    ur_grid    = ([float(u) for u in args.ur_list.split(',')]
                  if args.ur_list else UR_GRID)
    delta      = args.delta

    if args.dataset == 'all':
        datasets_to_run = ['hippo', 'brats', 'synthetic']
    else:
        datasets_to_run = [args.dataset]

    out_csv   = os.path.join(RESULTS_DIR, f"probe_dn{args.out_suffix}.csv")
    out_state = os.path.join(RESULTS_DIR, f"probe_dn{args.out_suffix}_state.json")

    cols = ['ur', 'fire_rate', 'dataset', 'init_seed', 'N',
            'd_front', 'n_active', 'd_equiv', 'theta_used']

    all_rows = []
    device   = torch.device(DEVICE)

    print(f"[probe_dn] 开始 d(N) 探针", flush=True)
    print(f"  ur_grid={ur_grid}", flush=True)
    print(f"  init_seeds={init_seeds}", flush=True)
    print(f"  n_list={n_list}  delta={delta}  smoke={smoke}", flush=True)
    print(f"  datasets={datasets_to_run}", flush=True)
    write_state(out_state, "init", {
        "ur_grid":     ur_grid,
        "init_seeds":  init_seeds,
        "n_list":      n_list,
        "delta":       delta,
        "datasets":    datasets_to_run,
    })

    for ds_name in datasets_to_run:
        print(f"\n[probe_dn] 加载数据集 {ds_name}...", flush=True)
        ds, ds_label = load_dataset(ds_name, args.brats_root, smoke)
        print(f"[probe_dn] {ds_label} n={len(ds)}", flush=True)

        # 取固定 patch 集（多 patch 均值更稳健）
        # 每次取前 min(8, len(ds)) 张，减少采样噪声
        n_patches = 2 if smoke else min(8, len(ds))
        patches = []
        for i in range(n_patches):
            img, _ = ds[i]
            # img 可能是 [C, H, W] 或 [H, W, C]，统一处理
            if img.dim() == 2:
                img = img.unsqueeze(0)  # [1, H, W]
            if img.shape[0] > img.shape[-1]:
                # 可能是 [H, W, C] 形式，转换
                img = img.permute(2, 0, 1)
            img = img[:INPUT_CHANNELS]  # 只取第一通道
            patches.append(img.unsqueeze(0).float())  # [1, 1, H, W]

        # 构建扫描网格 (ur, seed)
        grid = [(ur, seed) for ur in ur_grid for seed in init_seeds]
        if smoke:
            grid = grid[:2]

        for run_idx, (ur, init_seed) in enumerate(grid):
            fire_rate = round(1.0 - ur, 6)
            print(
                f"\n[probe_dn] [{ds_label}] [{run_idx+1}/{len(grid)}]  "
                f"ur={ur}  fire_rate={fire_rate}  init_seed={init_seed}",
                flush=True
            )
            write_state(out_state, "running", {
                "dataset": ds_label, "ur": ur,
                "init_seed": init_seed,
                "run": run_idx + 1, "total": len(grid),
            })

            # 受控初始化（每次重新 init，init_seed 唯一确定权重）
            ca = build_controlled_nca(device, init_seed)
            ca.eval()

            for N_steps in n_list:
                # 多 patch 均值
                d_fronts   = []
                n_actives  = []
                d_equivs   = []
                theta_useds = []

                for patch in patches:
                    try:
                        res = run_probe_dn(
                            ca=ca,
                            patch=patch,
                            ur=ur,
                            N_steps=N_steps,
                            device=device,
                            init_seed=init_seed,
                            delta=delta,
                            smoke=smoke,
                        )
                        d_fronts.append(res['d_front'])
                        n_actives.append(res['n_active'])
                        d_equivs.append(res['d_equiv'])
                        theta_useds.append(res['theta_used'])
                    except Exception as ex:
                        print(f"  [probe_dn] patch 报错: {ex}", flush=True)
                        d_fronts.append(float('nan'))
                        n_actives.append(0)
                        d_equivs.append(float('nan'))
                        theta_useds.append(float('nan'))

                # 多 patch 均值（nan 安全）
                def _safe_mean(lst):
                    valid = [v for v in lst if not (isinstance(v, float) and math.isnan(v))]
                    return float(np.mean(valid)) if valid else float('nan')

                def _safe_mean_int(lst):
                    valid = [v for v in lst if v > 0]
                    return float(np.mean(valid)) if valid else 0.0

                d_front_mean  = _safe_mean(d_fronts)
                n_active_mean = _safe_mean_int(n_actives)
                d_equiv_mean  = _safe_mean(d_equivs)
                theta_mean    = _safe_mean(theta_useds)

                print(
                    f"    [d(N)] ur={ur:.2f} seed={init_seed} ds={ds_label} "
                    f"N={N_steps} "
                    f"d_front={d_front_mean:.3f} "
                    f"n_active={n_active_mean:.1f} "
                    f"theta={theta_mean:.4e}",
                    flush=True
                )

                row = {
                    'ur':         round(ur, 4),
                    'fire_rate':  round(fire_rate, 4),
                    'dataset':    ds_label,
                    'init_seed':  init_seed,
                    'N':          N_steps,
                    'd_front':    _fmt(d_front_mean),
                    'n_active':   round(n_active_mean, 2),
                    'd_equiv':    _fmt(d_equiv_mean),
                    'theta_used': _fmt(theta_mean),
                }
                all_rows.append(row)

            # 每完成一个 (ur, seed) 就写 csv（防中断丢失）
            write_csv(all_rows, out_csv, cols)

    write_state(out_state, "done", {
        "total_rows": len(all_rows),
        "csv":        out_csv,
    })
    print(f"\n[probe_dn] 完成。CSV: {out_csv}", flush=True)
    print(f"  total rows: {len(all_rows)}", flush=True)


if __name__ == '__main__':
    main()
