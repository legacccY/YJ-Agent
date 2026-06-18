"""
gate1_g2a_fourarm.py
FMReg Gate1 阶段1 G2-A gating — 四臂 3D 真中训

服务项目: FMReg / lever: L0 校准后验 / 命门: A0 rho_C 显著大于 rho_DE
真源: project/meeting/FMReg/05_Gate1_matrix.md §2 + §3 + §6

四臂:
  A  (det)      VoxelMorph-diff  3D UNet + SVF + S&S + warp
  B  (cVAE)     prob-VoxelMorph  双头 mean/log_sigma, KL Laplacian 先验
  C  (FM)       FM warp-driven 零 teacher, 3D TinyUNetFM, 多采样后验
  DE (ensemble) N=5 臂A 不同 seed 预测方差当后验

阶段2注意: 机制组 2x2 因子设计中「采样」因子 ELBO 侧的 reparam 后验结构
          与本脚本 FM 多采样结构需统一定义，coder 届时回报。

数据: IXI 3D .pkl (160×192×224, atlas-to-patient)
      atlas.pkl = fixed, subject_{i}.pkl = moving
      Train=403/Val=58/Test=115
      label=FreeSurfer subcortical seg (int16/float32, 38 non-zero structures)

Gating verdict (§6 预登记, 跑前写死不事后调阈):
  PASS = rho_C 显著 > rho_DE (配对 bootstrap p<0.05 或 CI 不重叠)
         AND rho_C > rho_B
         AND AUSE_C < AUSE_DE (方向一致)
         AND ECE_C < ECE_DE (方向一致)
         AND dice_C >= dice_A - 0.02 (不退精度守门)
  FAIL = rho_C 不显著优于 rho_DE → 停报, 降 TMLR 不洗
  AMBIGUOUS = rho_C>rho_DE 但 CI 重叠, 人工审

输出:
  gate1/results/gate1_g2a_fourarm.csv      (四臂全指标)
  gate1/results/gate1_g2a_sparsification.png
  gate1/results/gate1_g2a_verdict.txt

Windows 规范:
  num_workers=0, pin_memory=False, spawn-safe
  纯 numpy 统计 (no scipy, 避 OMP Error #15)
  matplotlib Agg, forward-slash 路径

运行:
  python gate1/gate1_g2a_fourarm.py --smoke          # CPU < 3min, 4 subject/10步/K=3/DE N=2
  python gate1/gate1_g2a_fourarm.py                  # 真中训, 需 GPU
  python gate1/gate1_g2a_fourarm.py --data-dir D:/xxx/IXI_data --out-dir D:/xxx/results
  python gate1/gate1_g2a_fourarm.py --phase eval     # 只跑 eval (需已有 ckpt)
  python gate1/gate1_g2a_fourarm.py --arm A          # 只跑单臂 (train+eval)
"""

import argparse
import csv
import glob
import math
import os
import pickle
import random
import sys
import time

import numpy as np

# ---------- matplotlib (Agg before any display import) ----------
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ---------- torch ----------
try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from torch.utils.data import Dataset, DataLoader
except ImportError:
    print("[ERROR] torch not found. pip install torch torchvision")
    sys.exit(1)

# ============================================================
# 路径 & 超参常量
# ============================================================
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))

DATA_DIR_DEFAULT   = os.path.join(_ROOT, "data", "IXI", "IXI_data")
RESULT_DIR_DEFAULT = os.path.join(_HERE, "results")
CKPT_DIR_DEFAULT   = os.path.join(_HERE, "ckpts")

# IXI 3D 体积 (160, 192, 224)
IMG_SHAPE = (160, 192, 224)

# FreeSurfer subcortical labels (atlas-subject intersection, 38 non-zero)
# 全部 atlas 中存在的非零 label, 对应 label_info.txt
LABEL_IDS = [
    2, 3, 4, 5, 7, 8, 10, 11, 12, 13, 14, 15, 16, 17, 18,
    24, 26, 28, 30, 31, 41, 42, 43, 44, 46, 47, 49, 50, 51, 52,
    53, 54, 58, 60, 62, 63, 77, 85,
]  # 38 structures

# === 臂 A/B backbone: VoxelMorph 3D UNet ===
# 官方超参 (voxelmorph/networks.py VxmDense, IXI config)
# researcher 核定: enc[16,32,32,32]/dec[32,32,32,32,32,16,16]
ENC_NF = [16, 32, 32, 32]
DEC_NF = [32, 32, 32, 32, 32, 16, 16]

# S&S 积分步数
SS_INT_STEPS = 7

# 训练超参 (researcher 核定)
LR_DEFAULT   = 1e-4           # 臂 A/B/C 共享 lr, researcher 核定
LAMBDA_S     = 0.01           # 正则系数 λ_smooth (05_Gate1_matrix §5)
N_EPOCHS_DEFAULT = 500        # TODO: 未找到 TransMorph IXI 官方 epoch 数, researcher 核定后替换
                              # VoxelMorph IXI 常用 ~500 ep, 以此占位
BATCH_SIZE   = 1              # 3D 全分辨率显存约束, batch=1

# === 臂 B (cVAE/prob-VoxelMorph) ===
# researcher 核定: prior_lambda=10, image_sigma=0.02
PRIOR_LAMBDA  = 10            # 官方 voxelmorph/tf/losses.py KL class
IMAGE_SIGMA   = 0.02          # researcher 核定 (05 Gate1 matrix §5 §7 修订)
# init: mean head Normal(0,1e-5)/bias=0, log_sigma head Normal(0,1e-10)/bias=-10

# === 臂 C (FM warp-driven) ===
FM_ROLLOUT_STEPS_TRAIN = 2    # 训练内 Euler 步 (≤2 控显存)
FM_EVAL_STEPS          = 4    # eval Euler 步 (no_grad)
# sigma_p: 数据驱动 (先训臂A估SVF std), 不臆想固定值

# === DE (deep ensemble) ===
DE_N_FULL  = 5                # full run DE seed 数 (>=5 §2.2)
DE_SEEDS   = [0, 1, 2, 3, 4] # 5 seeds

# K 采样 (eval 后验)
K_SAMPLES_FULL  = 10          # full run posterior sample count
# TODO: 未找到 PULPo 官方 K 设置 (per-sample eval K), researcher 核定
#       VoxelMorph-prob eval 常用 K=10-20; 占位 K=10

# ECE bins
ECE_N_BINS = 10               # TODO: ECE bin 口径 WACV2022/PULPo exact impl 未确认,
                              # 标准 calibration ECE 用 10 bins 占位, researcher 确认

# ============================================================
# 工具函数
# ============================================================

def set_seed(seed: int):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def pkload(fname: str):
    """加载 IXI .pkl → (image np.float32, label np.int32)"""
    with open(fname, "rb") as f:
        img, lbl = pickle.load(f)
    img = img.astype(np.float32)
    lbl = lbl.astype(np.int32)
    return img, lbl


# ============================================================
# IXI 3D Dataset (atlas-to-patient)
# ============================================================
class IXIDataset3D(Dataset):
    """
    atlas (fixed) → subject (moving), atlas-to-patient 配准
    返回: moving [1,D,H,W], fixed [1,D,H,W], moving_lbl [1,D,H,W], fixed_lbl [1,D,H,W]
    """
    def __init__(self, data_dir: str, split: str = "Train",
                 n_subjects: int = None, seed: int = 42,
                 crop_size: int = None):
        """
        crop_size: if set, center-crop all volumes to crop_size³ (for smoke test).
                   Full-resolution (160,192,224) for real training.
        """
        self.data_dir  = data_dir
        self.split     = split
        self.crop_size = crop_size

        # 加载 atlas
        atlas_path = os.path.join(data_dir, "atlas.pkl")
        self.atlas_img, self.atlas_lbl = pkload(atlas_path)

        # 找 subject pkl
        split_dir = os.path.join(data_dir, split)
        paths = sorted(glob.glob(os.path.join(split_dir, "*.pkl")))
        if n_subjects is not None:
            rng = np.random.default_rng(seed)
            idx = rng.choice(len(paths), min(n_subjects, len(paths)), replace=False)
            paths = [paths[i] for i in sorted(idx)]
        self.paths = paths
        print(f"[IXI] split={split}  n_subjects={len(paths)}  "
              f"crop={'full' if crop_size is None else crop_size}")

    @staticmethod
    def _center_crop(vol, size):
        """Center crop [D,H,W] numpy array to [size, size, size]"""
        d, h, w = vol.shape
        d0 = max((d - size) // 2, 0)
        h0 = max((h - size) // 2, 0)
        w0 = max((w - size) // 2, 0)
        return vol[d0:d0+size, h0:h0+size, w0:w0+size]

    def __len__(self):
        return len(self.paths)

    def __getitem__(self, idx):
        img, lbl = pkload(self.paths[idx])
        atl_img  = self.atlas_img.copy()
        atl_lbl  = self.atlas_lbl.copy()

        if self.crop_size is not None:
            img     = self._center_crop(img,     self.crop_size)
            lbl     = self._center_crop(lbl,     self.crop_size)
            atl_img = self._center_crop(atl_img, self.crop_size)
            atl_lbl = self._center_crop(atl_lbl, self.crop_size)

        # moving = subject, fixed = atlas
        moving_img = torch.from_numpy(img[None])
        fixed_img  = torch.from_numpy(atl_img[None])
        moving_lbl = torch.from_numpy(lbl[None].astype(np.int32))
        fixed_lbl  = torch.from_numpy(atl_lbl[None].astype(np.int32))
        return moving_img, fixed_img, moving_lbl, fixed_lbl


# ============================================================
# 3D 空间算子
# ============================================================

def make_identity_grid_3d(shape, device):
    """
    返回 3D identity grid [1, D, H, W, 3] (float32, [-1,1] 归一化坐标)
    shape = (D, H, W)
    """
    D, H, W = shape
    vectors = [
        torch.linspace(-1, 1, D, device=device),
        torch.linspace(-1, 1, H, device=device),
        torch.linspace(-1, 1, W, device=device),
    ]
    grids = torch.meshgrid(*vectors, indexing="ij")
    grid  = torch.stack(grids, dim=-1).unsqueeze(0).float()  # [1,D,H,W,3]
    return grid


def scaling_and_squaring_3d(svf, int_steps=7):
    """
    3D Scaling and Squaring: SVF [B,3,D,H,W] → disp [B,D,H,W,3]
    先缩放 1/2^int_steps, 再平方 int_steps 次
    """
    B, _, D, H, W = svf.shape
    device  = svf.device
    id_grid = make_identity_grid_3d((D, H, W), device)  # [1,D,H,W,3]
    id_grid = id_grid.expand(B, -1, -1, -1, -1)          # [B,D,H,W,3]

    flow = svf / (2 ** int_steps)   # [B,3,D,H,W]

    def flow2disp(f):
        """[B,3,D,H,W] → [B,D,H,W,3]"""
        return f.permute(0, 2, 3, 4, 1)

    def compose(disp):
        """
        disp: [B,D,H,W,3] relative displacement in DHW coords
        composed = disp(id + disp) + disp  (squaring step)
        """
        # convert DHW offset → WH D sampling coords for grid_sample
        new_locs = id_grid + disp                    # [B,D,H,W,3] in DHW
        new_locs_xyz = new_locs[..., [2, 1, 0]]     # → WH D for grid_sample
        # sample disp at new_locs
        warped_disp = F.grid_sample(
            disp.permute(0, 4, 1, 2, 3),            # [B,3,D,H,W]
            new_locs_xyz,
            mode="bilinear", padding_mode="border", align_corners=True
        )                                             # [B,3,D,H,W]
        return disp + warped_disp.permute(0, 2, 3, 4, 1)  # [B,D,H,W,3]

    disp = flow2disp(flow)
    for _ in range(int_steps):
        disp = compose(disp)
    return disp   # [B,D,H,W,3]


def warp_by_disp_3d(moving, disp):
    """
    3D warp: moving [B,C,D,H,W], disp [B,D,H,W,3] → warped [B,C,D,H,W]
    disp is in DHW coordinate offset space ([-1,1] normalized)
    """
    B, _, D, H, W = moving.shape
    id_grid = make_identity_grid_3d((D, H, W), moving.device).expand(B, -1, -1, -1, -1)
    new_locs     = id_grid + disp                    # [B,D,H,W,3] DHW
    new_locs_xyz = new_locs[..., [2, 1, 0]]         # WH D for grid_sample
    warped = F.grid_sample(
        moving, new_locs_xyz,
        mode="bilinear", padding_mode="border", align_corners=True
    )
    return warped


def warp_label_3d(lbl_float, disp):
    """
    Warp label (nearest neighbor): lbl_float [B,1,D,H,W] float32 → [B,1,D,H,W]
    """
    B, _, D, H, W = lbl_float.shape
    id_grid = make_identity_grid_3d((D, H, W), lbl_float.device).expand(B, -1, -1, -1, -1)
    new_locs     = id_grid + disp
    new_locs_xyz = new_locs[..., [2, 1, 0]]
    warped = F.grid_sample(
        lbl_float, new_locs_xyz,
        mode="nearest", padding_mode="border", align_corners=True
    )
    return warped


def ncc_loss_3d(pred, target, win=9):
    """
    3D Local NCC loss (returns -NCC for minimization)
    pred, target: [B,1,D,H,W]
    win: local window size
    """
    ndims    = 3
    win_size = win ** ndims
    sum_filt = torch.ones([1, 1, win, win, win], dtype=pred.dtype, device=pred.device)
    pad_no   = win // 2
    padding  = (pad_no, pad_no, pad_no)

    I2  = pred * pred
    J2  = target * target
    IJ  = pred * target

    I_sum  = F.conv3d(pred,   sum_filt, stride=1, padding=padding)
    J_sum  = F.conv3d(target, sum_filt, stride=1, padding=padding)
    I2_sum = F.conv3d(I2,     sum_filt, stride=1, padding=padding)
    J2_sum = F.conv3d(J2,     sum_filt, stride=1, padding=padding)
    IJ_sum = F.conv3d(IJ,     sum_filt, stride=1, padding=padding)

    u_I = I_sum / win_size
    u_J = J_sum / win_size

    cross  = IJ_sum - u_J * I_sum - u_I * J_sum + u_I * u_J * win_size
    I_var  = I2_sum - 2 * u_I * I_sum + u_I * u_I * win_size
    J_var  = J2_sum - 2 * u_J * J_sum + u_J * u_J * win_size

    cc = cross * cross / (I_var * J_var + 1e-5)
    return -cc.mean()


def smooth_loss_3d(flow):
    """
    3D spatial gradient regularization ‖∇v‖²
    flow: [B,3,D,H,W]
    """
    dx = flow[:, :, 1:, :, :]  - flow[:, :, :-1, :, :]
    dy = flow[:, :, :, 1:, :]  - flow[:, :, :, :-1, :]
    dz = flow[:, :, :, :, 1:]  - flow[:, :, :, :, :-1]
    return (dx**2).mean() + (dy**2).mean() + (dz**2).mean()


def jacobian_det_3d(disp):
    """
    3D Jacobian determinant of displacement field
    disp: [B,D,H,W,3] (relative offset, not absolute coords)
    returns: [B, D-1, H-1, W-1] det values
    Uses forward finite difference approximation
    """
    d  = disp.permute(0, 4, 1, 2, 3)  # [B,3,D,H,W]

    # Jacobian columns (forward difference, output [B, D-1, H-1, W-1])
    J00 = 1.0 + d[:, 0, 1:,  :-1, :-1] - d[:, 0, :-1, :-1, :-1]
    J01 =       d[:, 0, :-1, 1:,  :-1] - d[:, 0, :-1, :-1, :-1]
    J02 =       d[:, 0, :-1, :-1, 1:]  - d[:, 0, :-1, :-1, :-1]
    J10 =       d[:, 1, 1:,  :-1, :-1] - d[:, 1, :-1, :-1, :-1]
    J11 = 1.0 + d[:, 1, :-1, 1:,  :-1] - d[:, 1, :-1, :-1, :-1]
    J12 =       d[:, 1, :-1, :-1, 1:]  - d[:, 1, :-1, :-1, :-1]
    J20 =       d[:, 2, 1:,  :-1, :-1] - d[:, 2, :-1, :-1, :-1]
    J21 =       d[:, 2, :-1, 1:,  :-1] - d[:, 2, :-1, :-1, :-1]
    J22 = 1.0 + d[:, 2, :-1, :-1, 1:]  - d[:, 2, :-1, :-1, :-1]

    det = (J00 * (J11 * J22 - J12 * J21)
         - J01 * (J10 * J22 - J12 * J20)
         + J02 * (J10 * J21 - J11 * J20))
    return det  # [B, D-1, H-1, W-1]


# ============================================================
# Dice (38 structures, pure numpy)
# ============================================================

def dice_labels_numpy(warped_lbl_np, fixed_lbl_np, label_ids=LABEL_IDS):
    """
    warped_lbl_np: [B,1,D,H,W] int32 numpy
    fixed_lbl_np:  [B,1,D,H,W] int32 numpy
    returns: per-batch mean Dice list [float] × B
    """
    B = warped_lbl_np.shape[0]
    batch_dice = []
    for b in range(B):
        w = warped_lbl_np[b, 0]
        f = fixed_lbl_np[b, 0]
        dices = []
        for lbl in label_ids:
            w_bin = (w == lbl)
            f_bin = (f == lbl)
            inter = float((w_bin & f_bin).sum())
            union = float(w_bin.sum() + f_bin.sum())
            if union > 0:
                dices.append(2.0 * inter / union)
        batch_dice.append(float(np.mean(dices)) if dices else 0.0)
    return batch_dice


# ============================================================
# Pure numpy stats (no scipy, avoid OMP Error #15)
# ============================================================

def pearson_r_numpy(x, y):
    """Pearson r + approximate p-value (two-tailed), pure numpy"""
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    n = len(x)
    if n < 3:
        return 0.0, 1.0
    mx, my = x.mean(), y.mean()
    xc, yc = x - mx, y - my
    num    = float((xc * yc).sum())
    denom  = float(np.sqrt((xc**2).sum() * (yc**2).sum())) + 1e-15
    r      = float(np.clip(num / denom, -1.0, 1.0))
    if abs(r) >= 1.0 - 1e-9:
        p = 0.0
    else:
        t = r * math.sqrt(n - 2) / (math.sqrt(1 - r**2) + 1e-15)
        # TODO: 精确 t-分布 p 值需 incomplete beta; 此处用标准正态近似
        p = float(2.0 * _norm_cdf_approx(-abs(t)))
    return r, p


def _norm_cdf_approx(x):
    """Standard normal CDF approximation (Abramowitz & Stegun 26.2.17)"""
    sign = 1.0 if x >= 0 else -1.0
    xa = abs(x)
    t  = 1.0 / (1.0 + 0.2316419 * xa)
    poly = (((1.330274429 * t - 1.821255978) * t + 1.781477937) * t
            - 0.356563782) * t + 0.319381530
    approx = 1.0 - (1.0 / math.sqrt(2 * math.pi)) * math.exp(-0.5 * xa**2) * poly * t
    return approx if sign > 0 else 1.0 - approx


def bootstrap_pearson_paired_ci(unc_C, err_C, unc_DE, err_DE,
                                 n_boot=500, alpha=0.05, seed=0):
    """
    配对 bootstrap: rho_C - rho_DE 的 CI
    returns (mean_diff, ci_low, ci_high, p_approx)
    p_approx = fraction of bootstrap samples where diff <= 0
    """
    rng    = np.random.default_rng(seed)
    unc_C  = np.asarray(unc_C,  dtype=np.float64)
    err_C  = np.asarray(err_C,  dtype=np.float64)
    unc_DE = np.asarray(unc_DE, dtype=np.float64)
    err_DE = np.asarray(err_DE, dtype=np.float64)
    N = len(unc_C)
    assert len(unc_DE) == N, "C and DE must have same N subjects"
    diffs = []
    for _ in range(n_boot):
        idx  = rng.integers(0, N, size=N)
        r_C,  _ = pearson_r_numpy(unc_C[idx],  err_C[idx])
        r_DE, _ = pearson_r_numpy(unc_DE[idx], err_DE[idx])
        diffs.append(r_C - r_DE)
    diffs     = np.array(diffs)
    mean_diff = float(diffs.mean())
    ci_low    = float(np.percentile(diffs, 100 * alpha / 2))
    ci_high   = float(np.percentile(diffs, 100 * (1 - alpha / 2)))
    p_approx  = float((diffs <= 0).mean())
    return mean_diff, ci_low, ci_high, p_approx


# ============================================================
# Calibration metrics (§3, pure numpy)
# ============================================================

def compute_ause(unc_arr, err_arr, n_thresholds=100):
    """
    AUSE (Area Under Sparsification Error curve)
    unc_arr: [N] per-sample uncertainty proxy (posterior variance)
    err_arr: [N] per-sample reconstruction error
    Returns: AUSE (float, lower is better)
    """
    unc = np.asarray(unc_arr, dtype=np.float64)
    err = np.asarray(err_arr, dtype=np.float64)
    N   = len(unc)
    if N < 10:
        return float("nan")
    thresholds   = np.linspace(0, 1, n_thresholds)
    sort_unc     = np.argsort(-unc)    # unc descending
    sort_oracle  = np.argsort(-err)    # oracle: err descending
    curve_model  = []
    curve_oracle = []
    for frac in thresholds:
        n_keep = max(1, int(N * (1 - frac)))
        curve_model.append(err[sort_unc[:n_keep]].mean())
        curve_oracle.append(err[sort_oracle[:n_keep]].mean())
    curve_model  = np.array(curve_model)
    curve_oracle = np.array(curve_oracle)
    ause = float(np.trapz(curve_model - curve_oracle, thresholds))
    return max(ause, 0.0)


def compute_ece(unc_std_arr, err_arr, n_bins=ECE_N_BINS):
    """
    ECE (Expected Calibration Error)
    unc_std_arr: per-sample posterior std (sqrt of variance)
    err_arr:     per-sample reconstruction error
    TODO: WACV2022 PULPo 精确口径 (label boundary 3-voxel dilated region ECE)
          当前为 global per-sample ECE, researcher 确认口径后替换
    Returns: ECE (float, lower is better)
    """
    unc = np.asarray(unc_std_arr, dtype=np.float64)
    err = np.asarray(err_arr,     dtype=np.float64)
    N   = len(unc)
    if N < n_bins * 2:
        return float("nan")
    bin_edges     = np.percentile(unc, np.linspace(0, 100, n_bins + 1))
    bin_edges[0]  -= 1e-9
    bin_edges[-1] += 1e-9
    ece = 0.0
    for i in range(n_bins):
        mask = (unc > bin_edges[i]) & (unc <= bin_edges[i + 1])
        if mask.sum() < 2:
            continue
        sigma_i          = unc[mask].mean() + 1e-9
        coverage_nominal = 0.6827   # 1-sigma Gaussian coverage
        coverage_actual  = float((np.abs(err[mask]) <= sigma_i).mean())
        bin_weight       = mask.sum() / N
        ece += bin_weight * abs(coverage_nominal - coverage_actual)
    return ece


def compute_ncc_vx(unc_arr, err_arr):
    """
    NCC_VX (PULPo proxy): Pearson rho(unc, err) at per-sample level
    Positive = uncertainty correlates with error = calibrated
    TODO: PULPo exact NCC_VX definition (voxel-level cross-correlation map)
          needs per-voxel arrays; current impl uses per-sample proxy
    """
    r, _ = pearson_r_numpy(unc_arr, err_arr)
    return float(r)


def compute_sdlogj(disp_np):
    """
    SDlogJ: std of log|det J| at non-folding voxels
    disp_np: [D,H,W,3] numpy float32
    """
    d  = disp_np
    J00 = 1.0 + d[1:, :-1, :-1, 0] - d[:-1, :-1, :-1, 0]
    J01 =       d[:-1, 1:, :-1, 0]  - d[:-1, :-1, :-1, 0]
    J02 =       d[:-1, :-1, 1:, 0]  - d[:-1, :-1, :-1, 0]
    J10 =       d[1:, :-1, :-1, 1]  - d[:-1, :-1, :-1, 1]
    J11 = 1.0 + d[:-1, 1:, :-1, 1]  - d[:-1, :-1, :-1, 1]
    J12 =       d[:-1, :-1, 1:, 1]  - d[:-1, :-1, :-1, 1]
    J20 =       d[1:, :-1, :-1, 2]  - d[:-1, :-1, :-1, 2]
    J21 =       d[:-1, 1:, :-1, 2]  - d[:-1, :-1, :-1, 2]
    J22 = 1.0 + d[:-1, :-1, 1:, 2]  - d[:-1, :-1, :-1, 2]
    det = (J00 * (J11*J22 - J12*J21)
         - J01 * (J10*J22 - J12*J20)
         + J02 * (J10*J21 - J11*J20))
    pos_mask = det > 0
    if pos_mask.sum() < 10:
        return float("nan")
    return float(np.std(np.log(det[pos_mask])))


# ============================================================
# 3D UNet (VoxelMorph official enc/dec channels)
# ============================================================

class ConvBlock3D(nn.Module):
    """3D conv + InstanceNorm3D + LeakyReLU"""
    def __init__(self, cin, cout, stride=1):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv3d(cin, cout, 3, stride=stride, padding=1),
            nn.InstanceNorm3d(cout),
            nn.LeakyReLU(0.2, inplace=True),
        )
    def forward(self, x):
        return self.net(x)


class UNet3D(nn.Module):
    """
    3D UNet backbone (VoxelMorph-diff official architecture)
    enc_nf=[16,32,32,32], dec_nf=[32,32,32,32,32,16,16]
    in_ch=2 (moving+fixed concatenated)
    """
    def __init__(self, in_ch=2, enc_nf=None, dec_nf=None):
        super().__init__()
        enc_nf = enc_nf or ENC_NF
        dec_nf = dec_nf or DEC_NF

        # Encoder: stride-2 downsampling (4 levels)
        self.enc = nn.ModuleList()
        prev = in_ch
        for nf in enc_nf:
            self.enc.append(ConvBlock3D(prev, nf, stride=2))
            prev = nf

        # Decoder: upsample + skip concatenation
        # enc=[16,32,32,32] → enc_feats = [e0(16@D/2), e1(32@D/4), e2(32@D/8), e3(32@D/16)]
        # decoder h starts at e3 (D/16); need 4 upsamples to get back to D
        # skip connections: up0→cat e2, up1→cat e1, up2→cat e0
        #                   up3→no cat (4th upsample restores full resolution)
        # n_up=4 (must match enc levels), n_skip=3 (enc_feats[:-1] reversed)
        # skip_ch = reversed(enc_nf[:-1]) = [32(e2), 32(e1), 16(e0)]
        self.up        = nn.ModuleList()
        self.dec_convs = nn.ModuleList()
        n_up    = len(enc_nf)               # 4 upsample ops
        n_skip  = len(enc_nf) - 1          # 3 with skip
        skip_ch = list(reversed(enc_nf[:-1]))  # [32, 32, 16]
        in_dec  = enc_nf[-1]               # 32 (from deepest encoder)

        # Build n_up upsample modules
        for _ in range(n_up):
            self.up.append(nn.Upsample(scale_factor=2, mode="trilinear",
                                       align_corners=False))

        # Build dec_convs matching dec_nf (len=7)
        # first n_skip levels: upsample+skip; next 1 level: upsample no-skip;
        # remaining: no upsample no-skip
        _in = in_dec
        for i, nf in enumerate(dec_nf):
            if i < n_skip:
                self.dec_convs.append(ConvBlock3D(_in + skip_ch[i], nf))
            else:
                self.dec_convs.append(ConvBlock3D(_in, nf))
            _in = nf
        in_dec = _in

        self.out_ch = in_dec  # = dec_nf[-1] = 16

    def forward(self, x):
        enc_feats = []
        h = x
        for conv in self.enc:
            h = conv(h)
            enc_feats.append(h)

        h          = enc_feats[-1]
        # skip_feats: enc_feats[-2], enc_feats[-3], enc_feats[-4]  (n_skip=3)
        skip_feats = list(reversed(enc_feats[:-1]))  # len=3: [e2, e1, e0]
        n_up       = len(self.up)   # 4
        n_skip     = len(skip_feats)  # 3

        for i, dec_conv in enumerate(self.dec_convs):
            if i < n_up:
                h = self.up[i](h)
            if i < n_skip:
                h = torch.cat([h, skip_feats[i]], dim=1)
            h = dec_conv(h)
        return h  # [B, 16, D, H, W] (full resolution)


# ============================================================
# Arm A: Deterministic VoxelMorph-diff (3D)
# ============================================================

class ArmA_Det(nn.Module):
    """
    Arm A: deterministic SVF output
    in=[B,2,D,H,W] → SVF [B,3,D,H,W] → S&S → disp [B,D,H,W,3] → warp
    out_conv init: Normal(0,1e-5), bias=0  (VoxelMorph official mean flow init)
    """
    def __init__(self):
        super().__init__()
        self.unet     = UNet3D(in_ch=2)
        self.out_conv = nn.Conv3d(self.unet.out_ch, 3, kernel_size=3, padding=1)
        nn.init.normal_(self.out_conv.weight, std=1e-5)
        nn.init.zeros_(self.out_conv.bias)

    def forward(self, moving, fixed):
        """Returns: svf [B,3,D,H,W], disp [B,D,H,W,3], warped [B,1,D,H,W]"""
        x      = torch.cat([moving, fixed], dim=1)
        fea    = self.unet(x)
        svf    = self.out_conv(fea)
        disp   = scaling_and_squaring_3d(svf, SS_INT_STEPS)
        warped = warp_by_disp_3d(moving, disp)
        return svf, disp, warped


# ============================================================
# Arm B: cVAE / prob-VoxelMorph (3D)
# ============================================================

class ArmB_CVAE(nn.Module):
    """
    Arm B: prob-VoxelMorph double-head (mean_svf + log_sigma)
    KL Laplacian prior (prior_lambda=10, researcher verified)
    mean head  init: Normal(0,1e-5),  bias=0
    log_sigma  init: Normal(0,1e-10), bias=-10
    """
    def __init__(self):
        super().__init__()
        self.unet          = UNet3D(in_ch=2)
        self.mean_head     = nn.Conv3d(self.unet.out_ch, 3, kernel_size=3, padding=1)
        self.logsigma_head = nn.Conv3d(self.unet.out_ch, 3, kernel_size=3, padding=1)
        nn.init.normal_(self.mean_head.weight,     std=1e-5)
        nn.init.zeros_(self.mean_head.bias)
        nn.init.normal_(self.logsigma_head.weight, std=1e-10)
        nn.init.constant_(self.logsigma_head.bias, -10.0)

    def forward(self, moving, fixed):
        """Returns: mean_svf [B,3,D,H,W], log_sigma [B,3,D,H,W]"""
        x         = torch.cat([moving, fixed], dim=1)
        fea       = self.unet(x)
        mean_svf  = self.mean_head(fea)
        log_sigma = self.logsigma_head(fea)
        return mean_svf, log_sigma


def kl_laplacian_loss_3d(mean_svf, log_sigma,
                          prior_lambda=PRIOR_LAMBDA, ndims=3):
    """
    3D KL(q || Laplacian prior)
    Reference: voxelmorph/tf/losses.py KL class (Dalca 2019)

    sigma_term = prior_lambda * D_const * exp(log_sigma) - log_sigma
                 D_const = 6  (3D 6-neighborhood degree)
    prec_term  = prior_lambda * ‖∇mean_svf‖²  (spatial gradient)

    Total: 0.5 * ndims * mean(sigma_term + prec_term)

    image_sigma (=0.02) is applied by caller in training loss weighting
    """
    D_const    = 6.0
    sigma_term = prior_lambda * D_const * torch.exp(log_sigma) - log_sigma

    dx = mean_svf[:, :, 1:, :, :]  - mean_svf[:, :, :-1, :, :]
    dy = mean_svf[:, :, :, 1:, :]  - mean_svf[:, :, :, :-1, :]
    dz = mean_svf[:, :, :, :, 1:]  - mean_svf[:, :, :, :, :-1]
    prec_val = prior_lambda * ((dx**2).mean() + (dy**2).mean() + (dz**2).mean())

    return 0.5 * ndims * (sigma_term.mean() + prec_val)


# ============================================================
# Arm C: FM warp-driven zero teacher (3D)
# ============================================================

class ArmC_FM(nn.Module):
    """
    Arm C: FM velocity network
    in=[B, 6, D, H, W] = moving(1)+fixed(1)+psi_t(3)+t_map(1)
    out=[B, 3, D, H, W] FM velocity u
    """
    def __init__(self):
        super().__init__()
        self.unet     = UNet3D(in_ch=6)
        self.out_conv = nn.Conv3d(self.unet.out_ch, 3, kernel_size=3, padding=1)
        nn.init.normal_(self.out_conv.weight, std=1e-5)
        nn.init.zeros_(self.out_conv.bias)

    def forward(self, moving, fixed, psi_t, t):
        """
        moving, fixed: [B,1,D,H,W]
        psi_t        : [B,3,D,H,W]
        t            : [B] in [0,1]
        returns u    : [B,3,D,H,W]
        """
        B, _, D, H, W = moving.shape
        t_map = t.view(B, 1, 1, 1, 1).expand(B, 1, D, H, W)
        x     = torch.cat([moving, fixed, psi_t, t_map], dim=1)
        fea   = self.unet(x)
        return self.out_conv(fea)


def estimate_sigma_p_3d(arm_a_model, loader, device, n_batches=3):
    """Data-driven sigma_p: std of arm A SVF outputs"""
    arm_a_model.eval()
    stds = []
    with torch.no_grad():
        for i, batch in enumerate(loader):
            if i >= n_batches:
                break
            moving, fixed, _, _ = batch
            svf, _, _ = arm_a_model(moving.to(device), fixed.to(device))
            stds.append(float(svf.std().cpu().item()))
    sigma_p = float(np.mean(stds)) if stds else 0.15
    sigma_p = max(sigma_p, 1e-4)
    print(f"[INFO] σ_p data-driven (arm A SVF std, {len(stds)} batches) = {sigma_p:.6f}")
    return sigma_p


# ============================================================
# Training functions
# ============================================================

def train_arm_A(model, loader, n_epochs, device, ckpt_path=None, seed=0):
    """
    Arm A training
    Loss: NCC(warp(moving, S&S(svf)), fixed) + λ_s·‖∇svf‖²
    """
    set_seed(seed)
    opt = torch.optim.Adam(model.parameters(), lr=LR_DEFAULT)
    model.train()
    t0        = time.time()
    log_every = max(1, n_epochs // 10)
    for ep in range(n_epochs):
        for batch in loader:
            moving, fixed, _, _ = batch
            moving = moving.to(device)
            fixed  = fixed.to(device)
            opt.zero_grad()
            svf, disp, warped = model(moving, fixed)
            loss = ncc_loss_3d(warped, fixed) + LAMBDA_S * smooth_loss_3d(svf)
            loss.backward()
            opt.step()
        if (ep + 1) % log_every == 0 or ep == 0:
            print(f"  [A s={seed}] ep {ep+1}/{n_epochs}  loss={loss.item():.5f}  "
                  f"t={time.time()-t0:.1f}s")
    if ckpt_path:
        os.makedirs(os.path.dirname(ckpt_path), exist_ok=True)
        torch.save(model.state_dict(), ckpt_path)
        print(f"  [A] ckpt → {ckpt_path}")
    return model


def train_arm_B(model, loader, n_epochs, device, ckpt_path=None, seed=0):
    """
    Arm B training (prob-VoxelMorph)
    Loss: recon_NCC / image_sigma² + KL_Laplacian
    image_sigma = 0.02 (researcher verified)
    """
    set_seed(seed)
    opt           = torch.optim.Adam(model.parameters(), lr=LR_DEFAULT)
    model.train()
    t0            = time.time()
    log_every     = max(1, n_epochs // 10)
    img_sigma_sq  = IMAGE_SIGMA ** 2
    for ep in range(n_epochs):
        for batch in loader:
            moving, fixed, _, _ = batch
            moving = moving.to(device)
            fixed  = fixed.to(device)
            opt.zero_grad()
            mean_svf, log_sigma = model(moving, fixed)
            disp   = scaling_and_squaring_3d(mean_svf, SS_INT_STEPS)
            warped = warp_by_disp_3d(moving, disp)
            recon  = ncc_loss_3d(warped, fixed) / img_sigma_sq
            kl     = kl_laplacian_loss_3d(mean_svf, log_sigma)
            loss   = recon + kl
            loss.backward()
            opt.step()
        if (ep + 1) % log_every == 0 or ep == 0:
            print(f"  [B] ep {ep+1}/{n_epochs}  recon={recon.item():.5f}  "
                  f"kl={kl.item():.5f}  t={time.time()-t0:.1f}s")
    if ckpt_path:
        os.makedirs(os.path.dirname(ckpt_path), exist_ok=True)
        torch.save(model.state_dict(), ckpt_path)
        print(f"  [B] ckpt → {ckpt_path}")
    return model


def train_arm_C(model, loader, n_epochs, device, sigma_p, ckpt_path=None, seed=0):
    """
    Arm C training (FM warp-driven zero teacher)
    Each step:
      psi_0 ~ N(0, sigma_p²)
      t ~ U(0,1)
      rollout FM_ROLLOUT_STEPS_TRAIN Euler steps (grad flows through)
      Loss: NCC(warp(moving, S&S(psi_hat)), fixed) + λ_s·‖∇psi_hat‖²
    """
    set_seed(seed)
    opt = torch.optim.Adam(model.parameters(), lr=LR_DEFAULT)
    model.train()
    t0        = time.time()
    log_every = max(1, n_epochs // 10)
    dt        = 1.0 / FM_ROLLOUT_STEPS_TRAIN
    for ep in range(n_epochs):
        for batch in loader:
            moving, fixed, _, _ = batch
            moving = moving.to(device)
            fixed  = fixed.to(device)
            B, _, D, H, W = moving.shape
            opt.zero_grad()
            psi    = torch.randn(B, 3, D, H, W, device=device) * sigma_p
            t_samp = torch.rand(B, device=device)
            for k in range(FM_ROLLOUT_STEPS_TRAIN):
                t_k  = (t_samp + k * dt).clamp(0.0, 1.0)
                u    = model(moving, fixed, psi, t_k)
                psi  = psi + dt * u
            psi_hat = psi
            disp    = scaling_and_squaring_3d(psi_hat, SS_INT_STEPS)
            warped  = warp_by_disp_3d(moving, disp)
            loss    = ncc_loss_3d(warped, fixed) + LAMBDA_S * smooth_loss_3d(psi_hat)
            loss.backward()
            opt.step()
        if (ep + 1) % log_every == 0 or ep == 0:
            print(f"  [C] ep {ep+1}/{n_epochs}  loss={loss.item():.5f}  "
                  f"t={time.time()-t0:.1f}s")
    if ckpt_path:
        os.makedirs(os.path.dirname(ckpt_path), exist_ok=True)
        torch.save(model.state_dict(), ckpt_path)
        print(f"  [C] ckpt → {ckpt_path}")
    return model


# ============================================================
# FM eval sampling
# ============================================================

def fm_sample_3d(model, moving, fixed, device, sigma_p,
                 n_steps=FM_EVAL_STEPS, seed=None):
    """
    FM eval: Euler integrate n_steps → psi_hat [B,3,D,H,W] (no_grad)
    Different seeds → different posterior samples
    """
    B, _, D, H, W = moving.shape
    if seed is not None:
        rng    = np.random.default_rng(seed)
        psi_np = rng.standard_normal((B, 3, D, H, W)).astype(np.float32) * sigma_p
        psi    = torch.from_numpy(psi_np).to(device)
    else:
        psi = torch.randn(B, 3, D, H, W, device=device) * sigma_p
    dt = 1.0 / n_steps
    with torch.no_grad():
        for i in range(n_steps):
            t_val = torch.full((B,), i * dt, device=device, dtype=torch.float32)
            u   = model(moving, fixed, psi, t_val)
            psi = psi + dt * u
    return psi


# ============================================================
# Eval functions (return per-sample metrics)
# ============================================================

def eval_arm_A_full(model, loader, device):
    """Returns per-sample: dice, neg_jac_pct, sdlogj, post_var (=0 det), recon_err"""
    model.eval()
    dice_l, neg_jac_l, sdlogj_l, post_var_l, recon_err_l = [], [], [], [], []
    with torch.no_grad():
        for batch in loader:
            moving, fixed, mov_lbl, fix_lbl = batch
            moving = moving.to(device)
            fixed  = fixed.to(device)
            _, disp, warped = model(moving, fixed)

            wlbl = warp_label_3d(mov_lbl.float().to(device), disp)
            dice_l.extend(dice_labels_numpy(wlbl.cpu().numpy().astype(np.int32),
                                            fix_lbl.numpy().astype(np.int32)))

            jac     = jacobian_det_3d(disp)
            neg_pct = (jac < 0).float().mean(dim=[-1,-2,-3]).cpu().numpy()
            neg_jac_l.extend(neg_pct.tolist())

            disp_np = disp.cpu().numpy()
            for b in range(disp_np.shape[0]):
                sdlogj_l.append(compute_sdlogj(disp_np[b]))

            recon = np.abs(warped.cpu().numpy() - fixed.cpu().numpy()).mean(axis=(1,2,3,4))
            recon_err_l.extend(recon.tolist())
            post_var_l.extend([0.0] * moving.shape[0])

    return {"dice": dice_l, "neg_jac_pct": neg_jac_l, "sdlogj": sdlogj_l,
            "post_var": post_var_l, "recon_err": recon_err_l}


def eval_arm_B_full(model, loader, device, k_samples):
    """Arm B eval: K reparam samples → posterior var"""
    model.eval()
    dice_l, neg_jac_l, sdlogj_l, post_var_l, recon_err_l = [], [], [], [], []
    with torch.no_grad():
        for batch in loader:
            moving, fixed, mov_lbl, fix_lbl = batch
            moving = moving.to(device)
            fixed  = fixed.to(device)
            mean_svf, log_sigma = model(moving, fixed)

            disp   = scaling_and_squaring_3d(mean_svf, SS_INT_STEPS)
            warped = warp_by_disp_3d(moving, disp)
            wlbl   = warp_label_3d(mov_lbl.float().to(device), disp)
            dice_l.extend(dice_labels_numpy(wlbl.cpu().numpy().astype(np.int32),
                                            fix_lbl.numpy().astype(np.int32)))

            jac = jacobian_det_3d(disp)
            neg_jac_l.extend(
                (jac < 0).float().mean(dim=[-1,-2,-3]).cpu().numpy().tolist())

            disp_np = disp.cpu().numpy()
            for b in range(disp_np.shape[0]):
                sdlogj_l.append(compute_sdlogj(disp_np[b]))

            recon = np.abs(warped.cpu().numpy() - fixed.cpu().numpy()).mean(axis=(1,2,3,4))
            recon_err_l.extend(recon.tolist())

            psi_list = []
            for _ in range(k_samples):
                eps = torch.randn_like(mean_svf)
                v_k = mean_svf + torch.exp(0.5 * log_sigma) * eps
                psi_list.append(v_k.cpu().numpy())
            psi_stack = np.stack(psi_list, axis=0)   # [K,B,3,D,H,W]
            var_k = psi_stack.var(axis=0).mean(axis=(1,2,3,4))
            post_var_l.extend(var_k.tolist())

    return {"dice": dice_l, "neg_jac_pct": neg_jac_l, "sdlogj": sdlogj_l,
            "post_var": post_var_l, "recon_err": recon_err_l}


def eval_arm_C_full(model, loader, device, k_samples, sigma_p):
    """Arm C eval: K different psi_0 samples → ensemble dice, posterior var"""
    model.eval()
    dice_l, neg_jac_l, sdlogj_l, post_var_l, recon_err_l = [], [], [], [], []
    with torch.no_grad():
        for batch in loader:
            moving, fixed, mov_lbl, fix_lbl = batch
            moving = moving.to(device)
            fixed  = fixed.to(device)
            f_np   = fixed.cpu().numpy()
            fix_lbl_np = fix_lbl.numpy().astype(np.int32)

            psi_list  = []
            warp_list = []
            dice_k    = []
            for k in range(k_samples):
                psi_k  = fm_sample_3d(model, moving, fixed, device, sigma_p,
                                      FM_EVAL_STEPS, seed=k)
                disp_k = scaling_and_squaring_3d(psi_k, SS_INT_STEPS)
                w_k    = warp_by_disp_3d(moving, disp_k)
                wlbl_k = warp_label_3d(mov_lbl.float().to(device), disp_k)
                psi_list.append(psi_k.cpu().numpy())
                warp_list.append(w_k.cpu().numpy())
                dice_k.append(dice_labels_numpy(wlbl_k.cpu().numpy().astype(np.int32),
                                                fix_lbl_np))

            dice_arr = np.array(dice_k)   # [K, B]
            dice_l.extend(dice_arr.mean(axis=0).tolist())

            # neg_jac from last sample
            last_disp_t = scaling_and_squaring_3d(
                torch.from_numpy(psi_list[-1]).to(device), SS_INT_STEPS)
            jac = jacobian_det_3d(last_disp_t)
            neg_jac_l.extend(
                (jac < 0).float().mean(dim=[-1,-2,-3]).cpu().numpy().tolist())

            last_disp_np = last_disp_t.cpu().numpy()
            for b in range(last_disp_np.shape[0]):
                sdlogj_l.append(compute_sdlogj(last_disp_np[b]))

            # recon err: mean over K
            w_stack = np.stack(warp_list, axis=0)  # [K,B,1,D,H,W]
            recon   = np.abs(w_stack - f_np[None]).mean(axis=(0,2,3,4,5))
            recon_err_l.extend(recon.tolist())

            # posterior var over K SVF samples
            psi_stack = np.stack(psi_list, axis=0)  # [K,B,3,D,H,W]
            var_k = psi_stack.var(axis=0).mean(axis=(1,2,3,4))
            post_var_l.extend(var_k.tolist())

    return {"dice": dice_l, "neg_jac_pct": neg_jac_l, "sdlogj": sdlogj_l,
            "post_var": post_var_l, "recon_err": recon_err_l}


def eval_arm_DE_full(de_models, loader, device):
    """
    DE eval: N arm-A models, per-voxel displacement variance as posterior uncertainty
    de_models: list of trained ArmA_Det
    """
    for m in de_models:
        m.eval()
    dice_l, neg_jac_l, sdlogj_l, post_var_l, recon_err_l = [], [], [], [], []
    with torch.no_grad():
        for batch in loader:
            moving, fixed, mov_lbl, fix_lbl = batch
            moving = moving.to(device)
            fixed  = fixed.to(device)
            fix_lbl_np = fix_lbl.numpy().astype(np.int32)

            disp_list  = []
            warp_list  = []
            dice_n     = []
            for m in de_models:
                _, disp_m, w_m = m(moving, fixed)
                wlbl_m = warp_label_3d(mov_lbl.float().to(device), disp_m)
                disp_list.append(disp_m.cpu().numpy())  # [B,D,H,W,3]
                warp_list.append(w_m.cpu().numpy())
                dice_n.append(dice_labels_numpy(wlbl_m.cpu().numpy().astype(np.int32),
                                                fix_lbl_np))

            dice_arr = np.array(dice_n)  # [N, B]
            dice_l.extend(dice_arr.mean(axis=0).tolist())

            # neg_jac from last model's disp
            last_disp_torch = torch.from_numpy(disp_list[-1]).to(device)
            jac = jacobian_det_3d(last_disp_torch)
            neg_jac_l.extend(
                (jac < 0).float().mean(dim=[-1,-2,-3]).cpu().numpy().tolist())

            last_disp_np = disp_list[-1]
            for b in range(last_disp_np.shape[0]):
                sdlogj_l.append(compute_sdlogj(last_disp_np[b]))

            # recon err: mean warped
            w_stack = np.stack(warp_list, axis=0)  # [N,B,1,D,H,W]
            f_np    = fixed.cpu().numpy()
            recon   = np.abs(w_stack.mean(axis=0) - f_np).mean(axis=(1,2,3,4))
            recon_err_l.extend(recon.tolist())

            # posterior var: inter-model disp variance
            disp_stack = np.stack(disp_list, axis=0)   # [N,B,D,H,W,3]
            var_n = disp_stack.var(axis=0).mean(axis=(1,2,3,4))  # [B]
            post_var_l.extend(var_n.tolist())

    return {"dice": dice_l, "neg_jac_pct": neg_jac_l, "sdlogj": sdlogj_l,
            "post_var": post_var_l, "recon_err": recon_err_l}


# ============================================================
# Gating Verdict (§6 preregistered, frozen before run)
# ============================================================

def compute_g2a_verdict(
    rho_C, rho_B, rho_DE,
    rho_diff_ci_low,
    rho_diff_p,
    ause_C, ause_DE,
    ece_C, ece_DE,
    dice_C, dice_A,
):
    """
    G2-A Gating Verdict (§6 of 05_Gate1_matrix.md — preregistered, do not modify thresholds)

    PASS = rho_C significantly > rho_DE (CI_low > 0 OR p < 0.05)
           AND rho_C > rho_B
           AND AUSE_C < AUSE_DE
           AND ECE_C < ECE_DE
           AND dice_C >= dice_A - 0.02

    FAIL = rho_C not significantly > rho_DE (CI_low <= 0 AND p >= 0.05)
           → halt, downgrade to TMLR, no p-hacking

    AMBIGUOUS = mixed signals, manual review required
    """
    sig_vs_DE = (rho_diff_ci_low > 0.0) or (rho_diff_p < 0.05)
    better_vs_B = rho_C > rho_B
    ause_ok  = (ause_C < ause_DE) if (not math.isnan(ause_C or 0)
                                       and not math.isnan(ause_DE or 0)) else None
    ece_ok   = (ece_C < ece_DE)   if (not math.isnan(ece_C or 0)
                                       and not math.isnan(ece_DE or 0)) else None
    # handle NaN
    if ause_C != ause_C or ause_DE != ause_DE:
        ause_ok = None
    else:
        ause_ok = ause_C < ause_DE
    if ece_C != ece_C or ece_DE != ece_DE:
        ece_ok = None
    else:
        ece_ok = ece_C < ece_DE

    dice_ok = dice_C >= dice_A - 0.02

    all_consistent = sig_vs_DE and better_vs_B and dice_ok and (ause_ok is not False) and (ece_ok is not False)

    if all_consistent and sig_vs_DE:
        verdict = "PASS"
        detail  = (f"rho_C({rho_C:.4f}) 显著>rho_DE({rho_DE:.4f}) (CI_low={rho_diff_ci_low:.4f}>0 or p={rho_diff_p:.4f}<0.05) "
                   f"AND rho_C>rho_B({rho_B:.4f}) "
                   f"AND AUSE_C({ause_C:.4f})<AUSE_DE({ause_DE:.4f}) "
                   f"AND ECE_C({ece_C:.4f})<ECE_DE({ece_DE:.4f}) "
                   f"AND dice_C({dice_C:.4f})>=dice_A({dice_A:.4f})-0.02 "
                   "→ 继续阶段2")
    elif not sig_vs_DE and rho_C <= rho_DE:
        verdict = "FAIL"
        detail  = (f"rho_C({rho_C:.4f}) 不显著优于 rho_DE({rho_DE:.4f}) "
                   f"(CI_low={rho_diff_ci_low:.4f}<=0 AND p={rho_diff_p:.4f}>=0.05) "
                   "→ 强 baseline 不输, A0 机制证不出, 停报, 降 TMLR 不洗")
    elif rho_C > rho_DE and not sig_vs_DE:
        verdict = "AMBIGUOUS"
        detail  = (f"rho_C({rho_C:.4f})>rho_DE({rho_DE:.4f}) 但 CI 重叠 (p={rho_diff_p:.4f}), "
                   "建议增大 n_subjects 或 n_boot, 人工审")
    elif sig_vs_DE and not dice_ok:
        verdict = "AMBIGUOUS"
        detail  = (f"rho_C 显著>rho_DE 但 dice_C({dice_C:.4f})<dice_A({dice_A:.4f})-0.02 "
                   "→ 精度守门触发, 检查 arm C 配准质量")
    elif sig_vs_DE and not better_vs_B:
        verdict = "AMBIGUOUS"
        detail  = (f"rho_C 显著>rho_DE 但 rho_C({rho_C:.4f})<=rho_B({rho_B:.4f}) "
                   "→ 校准优于强 baseline 但弱于(塌缩)cVAE, 检查实现")
    elif sig_vs_DE and (ause_ok is False or ece_ok is False):
        verdict = "AMBIGUOUS"
        detail  = (f"rho_C 显著>rho_DE 但 AUSE/ECE 方向不一致 "
                   f"(AUSE_ok={ause_ok}, ECE_ok={ece_ok}), 人工审")
    else:
        verdict = "AMBIGUOUS"
        detail  = (f"混合信号 (sig_vs_DE={sig_vs_DE}, better_vs_B={better_vs_B}, "
                   f"ause_ok={ause_ok}, ece_ok={ece_ok}, dice_ok={dice_ok}), 人工审")

    return verdict, detail


# ============================================================
# Plotting: sparsification curves
# ============================================================

def plot_sparsification(results_dict, out_path, n_thresholds=50):
    """Draw sparsification curves for all arms"""
    n_arms = len(results_dict)
    fig, axes = plt.subplots(1, n_arms, figsize=(5 * n_arms, 4))
    if n_arms == 1:
        axes = [axes]
    colors = {"A": "gray", "B": "blue", "C": "red", "DE": "green"}
    thresholds = np.linspace(0, 0.9, n_thresholds)

    for ax, (arm_name, res) in zip(axes, results_dict.items()):
        unc = np.asarray(res["post_var"],  dtype=np.float64)
        err = np.asarray(res["recon_err"], dtype=np.float64)
        N   = len(unc)
        if N < 5:
            ax.set_title(f"Arm {arm_name} (N too small)")
            continue
        sort_unc    = np.argsort(-unc)
        sort_oracle = np.argsort(-err)
        curve_model  = []
        curve_oracle = []
        for frac in thresholds:
            n_keep = max(1, int(N * (1 - frac)))
            curve_model.append(err[sort_unc[:n_keep]].mean())
            curve_oracle.append(err[sort_oracle[:n_keep]].mean())
        c = colors.get(arm_name, "black")
        ax.plot(thresholds, curve_model,  color=c, linewidth=2, label=f"Arm {arm_name}")
        ax.plot(thresholds, curve_oracle, color="black", linestyle="--",
                linewidth=1.5, label="Oracle")
        ax.fill_between(thresholds,
                        np.array(curve_oracle), np.array(curve_model),
                        alpha=0.15, color=c, label="AUSE area")
        ax.set_xlabel("Fraction removed")
        ax.set_ylabel("Mean recon error (remaining)")
        ax.set_title(f"Arm {arm_name}")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

    fig.suptitle("G2-A Gate1 Sparsification Curves — IXI 3D atlas-to-patient")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    print(f"[SAVED FIG] {out_path}")


# ============================================================
# Main run
# ============================================================

def run(args):
    smoke    = args.smoke
    data_dir = args.data_dir
    out_dir  = args.out_dir
    ckpt_dir = args.ckpt_dir
    phase    = args.phase
    arm_only = args.arm

    os.makedirs(out_dir,  exist_ok=True)
    os.makedirs(ckpt_dir, exist_ok=True)

    if args.cpu or smoke:
        device = torch.device("cpu")
    else:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[INFO] G2-A Gate1 fourarm 3D | device={device} | smoke={smoke} | phase={phase}")

    # --- Scale config ---
    # smoke: 2 subjects, 3 steps, K=2, DE N=2, crop to 64³ for CPU <3min
    n_train   = 2    if smoke else None    # None = all 403
    n_test    = 2    if smoke else None    # None = all 115
    n_epochs  = 3    if smoke else (args.epochs if getattr(args, "epochs", None) else N_EPOCHS_DEFAULT)
    k_samp    = 2    if smoke else K_SAMPLES_FULL
    de_n      = 2    if smoke else DE_N_FULL
    de_seeds  = DE_SEEDS[:de_n]
    crop_size = 64   if smoke else None    # center-crop 64³ for fast smoke

    print(f"[INFO] n_epochs={n_epochs}  k_samples={k_samp}  de_n={de_n}  "
          f"n_train={n_train}  n_test={n_test}  crop={crop_size}")

    # --- Datasets ---
    train_ds = IXIDataset3D(data_dir, split="Train", n_subjects=n_train,
                            seed=42, crop_size=crop_size)
    test_ds  = IXIDataset3D(data_dir, split="Test",  n_subjects=n_test,
                            seed=99, crop_size=crop_size)
    train_dl = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True,
                          num_workers=0, pin_memory=False)
    test_dl  = DataLoader(test_ds,  batch_size=BATCH_SIZE, shuffle=False,
                          num_workers=0, pin_memory=False)

    results  = {}
    sigma_p  = 0.15   # will be overwritten by data-driven estimate

    # =================== Arm A ===================
    if arm_only in (None, "A", "DE"):
        print("\n[INFO] ===== Arm A (det VoxelMorph-diff 3D) =====")
        ckpt_A = os.path.join(ckpt_dir, "arm_A_seed0.pt")
        model_A = ArmA_Det().to(device)
        if phase != "eval":
            model_A = train_arm_A(model_A, train_dl, n_epochs, device, ckpt_A, seed=0)
        elif os.path.exists(ckpt_A):
            model_A.load_state_dict(torch.load(ckpt_A, map_location=device))
            print(f"  [A] loaded {ckpt_A}")
        sigma_p = estimate_sigma_p_3d(model_A, train_dl, device, n_batches=3)

        if arm_only != "DE":
            print("  [A] evaluating ...")
            res_A = eval_arm_A_full(model_A, test_dl, device)
            results["A"] = res_A
            rho_A, p_A = pearson_r_numpy(res_A["post_var"], res_A["recon_err"])
            print(f"  [A] dice={np.mean(res_A['dice']):.4f}  "
                  f"neg_jac={np.mean(res_A['neg_jac_pct'])*100:.3f}%  "
                  f"rho={rho_A:.4f}(p={p_A:.4f})")

    # =================== Arm DE ===================
    if arm_only in (None, "DE"):
        print(f"\n[INFO] ===== Arm DE (deep ensemble N={de_n}) =====")
        de_models = []
        for si in de_seeds:
            ckpt_i = os.path.join(ckpt_dir, f"arm_A_seed{si}.pt")
            m_i    = ArmA_Det().to(device)
            if phase != "eval":
                m_i = train_arm_A(m_i, train_dl, n_epochs, device, ckpt_i, seed=si)
            elif os.path.exists(ckpt_i):
                m_i.load_state_dict(torch.load(ckpt_i, map_location=device))
                print(f"  [DE] loaded {ckpt_i}")
            de_models.append(m_i)

        print("  [DE] evaluating ...")
        res_DE = eval_arm_DE_full(de_models, test_dl, device)
        results["DE"] = res_DE
        rho_DE, p_DE = pearson_r_numpy(res_DE["post_var"], res_DE["recon_err"])
        print(f"  [DE] dice={np.mean(res_DE['dice']):.4f}  "
              f"neg_jac={np.mean(res_DE['neg_jac_pct'])*100:.3f}%  "
              f"rho={rho_DE:.4f}(p={p_DE:.4f})")

    # =================== Arm B ===================
    if arm_only in (None, "B"):
        print("\n[INFO] ===== Arm B (cVAE prob-VoxelMorph 3D) =====")
        ckpt_B = os.path.join(ckpt_dir, "arm_B.pt")
        model_B = ArmB_CVAE().to(device)
        if phase != "eval":
            model_B = train_arm_B(model_B, train_dl, n_epochs, device, ckpt_B, seed=0)
        elif os.path.exists(ckpt_B):
            model_B.load_state_dict(torch.load(ckpt_B, map_location=device))
            print(f"  [B] loaded {ckpt_B}")

        print("  [B] evaluating ...")
        res_B = eval_arm_B_full(model_B, test_dl, device, k_samp)
        results["B"] = res_B
        rho_B, p_B = pearson_r_numpy(res_B["post_var"], res_B["recon_err"])
        print(f"  [B] dice={np.mean(res_B['dice']):.4f}  "
              f"neg_jac={np.mean(res_B['neg_jac_pct'])*100:.3f}%  "
              f"rho={rho_B:.4f}(p={p_B:.4f})")

    # =================== Arm C ===================
    if arm_only in (None, "C"):
        if "model_A" not in dir() or model_A is None:
            print("[WARN] sigma_p not calibrated (arm A not trained), using placeholder 0.15")
        print("\n[INFO] ===== Arm C (FM warp-driven zero teacher 3D) =====")
        ckpt_C = os.path.join(ckpt_dir, "arm_C.pt")
        model_C = ArmC_FM().to(device)
        if phase != "eval":
            model_C = train_arm_C(model_C, train_dl, n_epochs, device,
                                  sigma_p, ckpt_C, seed=0)
        elif os.path.exists(ckpt_C):
            model_C.load_state_dict(torch.load(ckpt_C, map_location=device))
            print(f"  [C] loaded {ckpt_C}")

        print("  [C] evaluating ...")
        res_C = eval_arm_C_full(model_C, test_dl, device, k_samp, sigma_p)
        results["C"] = res_C
        rho_C, p_C = pearson_r_numpy(res_C["post_var"], res_C["recon_err"])
        print(f"  [C] dice={np.mean(res_C['dice']):.4f}  "
              f"neg_jac={np.mean(res_C['neg_jac_pct'])*100:.3f}%  "
              f"rho={rho_C:.4f}(p={p_C:.4f})")

    # =================== Metrics + Verdict ===================
    if all(k in results for k in ("A", "B", "C", "DE")):
        print("\n[INFO] ===== Computing calibration metrics + G2-A Verdict =====")

        def safe_rho(pv, re):
            r, p = pearson_r_numpy(pv, re)
            if math.isnan(r):
                print(f"  [WARN] rho is NaN (likely too few samples), setting to 0")
                return 0.0, 1.0
            return r, p

        rho_A_v,  p_A_v  = safe_rho(results["A"]["post_var"],  results["A"]["recon_err"])
        rho_B_v,  p_B_v  = safe_rho(results["B"]["post_var"],  results["B"]["recon_err"])
        rho_C_v,  p_C_v  = safe_rho(results["C"]["post_var"],  results["C"]["recon_err"])
        rho_DE_v, p_DE_v = safe_rho(results["DE"]["post_var"], results["DE"]["recon_err"])

        rho_diff_mean, rho_ci_low, rho_ci_high, rho_p_approx = bootstrap_pearson_paired_ci(
            results["C"]["post_var"],  results["C"]["recon_err"],
            results["DE"]["post_var"], results["DE"]["recon_err"],
            n_boot=200 if smoke else 1000, seed=42,
        )

        ause_A  = compute_ause(results["A"]["post_var"],  results["A"]["recon_err"])
        ause_B  = compute_ause(results["B"]["post_var"],  results["B"]["recon_err"])
        ause_C  = compute_ause(results["C"]["post_var"],  results["C"]["recon_err"])
        ause_DE = compute_ause(results["DE"]["post_var"], results["DE"]["recon_err"])

        def safe_sqrt_unc(pv):
            return np.sqrt(np.clip(np.asarray(pv, dtype=np.float64), 0, None))

        ece_A  = compute_ece(safe_sqrt_unc(results["A"]["post_var"]),  results["A"]["recon_err"])
        ece_B  = compute_ece(safe_sqrt_unc(results["B"]["post_var"]),  results["B"]["recon_err"])
        ece_C  = compute_ece(safe_sqrt_unc(results["C"]["post_var"]),  results["C"]["recon_err"])
        ece_DE = compute_ece(safe_sqrt_unc(results["DE"]["post_var"]), results["DE"]["recon_err"])

        ncc_vx_A  = compute_ncc_vx(results["A"]["post_var"],  results["A"]["recon_err"])
        ncc_vx_B  = compute_ncc_vx(results["B"]["post_var"],  results["B"]["recon_err"])
        ncc_vx_C  = compute_ncc_vx(results["C"]["post_var"],  results["C"]["recon_err"])
        ncc_vx_DE = compute_ncc_vx(results["DE"]["post_var"], results["DE"]["recon_err"])
        # NCC_LM: TODO per-label centroid region sampling (same as NCC_VX for now)
        ncc_lm_C  = ncc_vx_C   # TODO: PULPo landmark-level NCC_LM exact impl
        ncc_lm_DE = ncc_vx_DE  # TODO: same

        def nm(lst):
            v = [x for x in lst if not (x != x)]  # remove nan
            return float(np.nanmean(v)) if v else float("nan")

        dice_A_v  = nm(results["A"]["dice"])
        dice_B_v  = nm(results["B"]["dice"])
        dice_C_v  = nm(results["C"]["dice"])
        dice_DE_v = nm(results["DE"]["dice"])
        neg_A_v   = nm(results["A"]["neg_jac_pct"]) * 100
        neg_B_v   = nm(results["B"]["neg_jac_pct"]) * 100
        neg_C_v   = nm(results["C"]["neg_jac_pct"]) * 100
        neg_DE_v  = nm(results["DE"]["neg_jac_pct"]) * 100
        sdlj_A    = nm([x for x in results["A"]["sdlogj"]  if not math.isnan(x)])
        sdlj_B    = nm([x for x in results["B"]["sdlogj"]  if not math.isnan(x)])
        sdlj_C    = nm([x for x in results["C"]["sdlogj"]  if not math.isnan(x)])
        sdlj_DE   = nm([x for x in results["DE"]["sdlogj"] if not math.isnan(x)])

        verdict, detail = compute_g2a_verdict(
            rho_C=rho_C_v,  rho_B=rho_B_v,   rho_DE=rho_DE_v,
            rho_diff_ci_low=rho_ci_low,        rho_diff_p=rho_p_approx,
            ause_C=ause_C,   ause_DE=ause_DE,
            ece_C=ece_C,     ece_DE=ece_DE,
            dice_C=dice_C_v, dice_A=dice_A_v,
        )

        # --- Print summary ---
        print("\n" + "=" * 88)
        print("  G2-A Gate1 Four-Arm 3D Results  (IXI, atlas-to-patient)")
        print("=" * 88)
        print(f"  n_test={len(results['A']['dice'])}  k={k_samp}  de_n={de_n}  "
              f"epochs={n_epochs}  prior_lambda={PRIOR_LAMBDA}  image_sigma={IMAGE_SIGMA}")
        print()
        hdr = f"  {'arm':6s}  {'dice':>7s}  {'neg_jac%':>9s}  {'SDlogJ':>7s}  {'rho':>7s}  {'p':>7s}  {'AUSE':>7s}  {'ECE':>7s}  {'NCC_VX':>8s}"
        print(hdr)
        print("  " + "-"*(len(hdr)-2))
        for an, dv, nv, sv, rv, pv, av, ev, nv2 in [
            ("A",  dice_A_v,  neg_A_v,  sdlj_A,  rho_A_v,  p_A_v,  ause_A,  ece_A,  ncc_vx_A),
            ("B",  dice_B_v,  neg_B_v,  sdlj_B,  rho_B_v,  p_B_v,  ause_B,  ece_B,  ncc_vx_B),
            ("C",  dice_C_v,  neg_C_v,  sdlj_C,  rho_C_v,  p_C_v,  ause_C,  ece_C,  ncc_vx_C),
            ("DE", dice_DE_v, neg_DE_v, sdlj_DE, rho_DE_v, p_DE_v, ause_DE, ece_DE, ncc_vx_DE),
        ]:
            def fmt(x): return f"{x:.4f}" if not math.isnan(x) else " nan"
            print(f"  {an:6s}  {fmt(dv):>7s}  {fmt(nv):>9s}  {fmt(sv):>7s}  "
                  f"{fmt(rv):>7s}  {fmt(pv):>7s}  {fmt(av):>7s}  {fmt(ev):>7s}  {fmt(nv2):>8s}")

        print()
        print(f"  rho_C - rho_DE = {rho_diff_mean:.4f}  "
              f"CI=[{rho_ci_low:.4f}, {rho_ci_high:.4f}]  "
              f"p_approx={rho_p_approx:.4f}")
        print(f"  NCC_LM_C={ncc_lm_C:.4f}  NCC_LM_DE={ncc_lm_DE:.4f}  "
              "(TODO: exact landmark centroid impl)")
        print()
        print(f"  G2-A VERDICT: {verdict}")
        print(f"  DETAIL: {detail}")
        print("=" * 88)

        # --- Sparsification plot ---
        plot_sparsification(results, os.path.join(out_dir, "gate1_g2a_sparsification.png"))

        # --- Write CSV ---
        csv_path = os.path.join(out_dir, "gate1_g2a_fourarm.csv")
        rows = [
            ("A",  dice_A_v,  neg_A_v,  sdlj_A,  rho_A_v,  p_A_v,  ause_A,  ece_A,  ncc_vx_A),
            ("B",  dice_B_v,  neg_B_v,  sdlj_B,  rho_B_v,  p_B_v,  ause_B,  ece_B,  ncc_vx_B),
            ("C",  dice_C_v,  neg_C_v,  sdlj_C,  rho_C_v,  p_C_v,  ause_C,  ece_C,  ncc_vx_C),
            ("DE", dice_DE_v, neg_DE_v, sdlj_DE, rho_DE_v, p_DE_v, ause_DE, ece_DE, ncc_vx_DE),
        ]
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([
                "arm", "dice", "neg_jac_pct", "sdlogj",
                "rho", "p_rho", "ause", "ece", "ncc_vx",
                "rho_diff_C_DE", "rho_ci_low", "rho_ci_high", "rho_p_approx",
                "ncc_lm",
                "n_test", "n_epochs", "k_samples", "de_n",
                "prior_lambda", "image_sigma", "lambda_s",
                "ss_int_steps", "fm_rollout_train", "fm_eval_steps",
                "smoke", "verdict", "verdict_detail",
            ])
            for (an, dv, nv, sv, rv, pv, av, ev, nv2) in rows:
                def fmt(x): return f"{x:.4f}" if not math.isnan(x) else "nan"
                is_C  = (an == "C")
                is_DE = (an == "DE")
                w.writerow([
                    an,
                    fmt(dv), fmt(nv), fmt(sv),
                    fmt(rv), fmt(pv), fmt(av), fmt(ev), fmt(nv2),
                    fmt(rho_diff_mean)  if is_C  else "",
                    fmt(rho_ci_low)     if is_C  else "",
                    fmt(rho_ci_high)    if is_C  else "",
                    fmt(rho_p_approx)   if is_C  else "",
                    fmt(ncc_lm_C)       if is_C  else (fmt(ncc_lm_DE) if is_DE else ""),
                    len(results["A"]["dice"]), n_epochs, k_samp, de_n,
                    PRIOR_LAMBDA, IMAGE_SIGMA, LAMBDA_S,
                    SS_INT_STEPS, FM_ROLLOUT_STEPS_TRAIN, FM_EVAL_STEPS,
                    smoke,
                    verdict if is_C else "",
                    detail  if is_C else "",
                ])
        print(f"[SAVED CSV] {csv_path}")

        # --- Write verdict txt ---
        vpath = os.path.join(out_dir, "gate1_g2a_verdict.txt")
        with open(vpath, "w", encoding="utf-8") as f:
            f.write(f"G2-A Gate1 Verdict\n{'='*64}\n")
            f.write(f"VERDICT: {verdict}\n")
            f.write(f"DETAIL:  {detail}\n\n")
            f.write(f"rho_C={rho_C_v:.4f}  rho_B={rho_B_v:.4f}  rho_DE={rho_DE_v:.4f}\n")
            f.write(f"rho_C - rho_DE: mean={rho_diff_mean:.4f}  "
                    f"CI=[{rho_ci_low:.4f}, {rho_ci_high:.4f}]  p={rho_p_approx:.4f}\n")
            f.write(f"AUSE_C={ause_C:.4f}  AUSE_DE={ause_DE:.4f}\n")
            f.write(f"ECE_C={ece_C:.4f}    ECE_DE={ece_DE:.4f}\n")
            f.write(f"dice_A={dice_A_v:.4f}  dice_C={dice_C_v:.4f}\n\n")
            f.write("Preregistered thresholds (§6 05_Gate1_matrix.md):\n"
                    "  PASS = rho_C sig>rho_DE (CI_low>0 or p<0.05) AND rho_C>rho_B\n"
                    "         AND AUSE_C<AUSE_DE AND ECE_C<ECE_DE\n"
                    "         AND dice_C>=dice_A-0.02\n"
                    "  FAIL = rho_C not sig > rho_DE → downgrade to TMLR, no p-hacking\n")
        print(f"[SAVED VERDICT] {vpath}")
        print("[DONE] G2-A Gate1 fourarm 3D complete.")

    else:
        print(f"[INFO] single-arm mode (arm={arm_only}), verdict skipped.")
        print("[DONE]")


# ============================================================
# Entry point
# ============================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="G2-A Gate1 四臂 3D (FMReg L0 校准后验 gating)")
    parser.add_argument("--smoke", action="store_true",
                        help="smoke test: 2 subjects/3 steps/K=2/DE N=2/crop64/CPU <3min")
    parser.add_argument("--cpu", action="store_true",
                        help="force CPU (smoke also forces CPU automatically)")
    parser.add_argument("--data-dir",  default=DATA_DIR_DEFAULT,
                        help="IXI_data directory (override for HPC)")
    parser.add_argument("--out-dir",   default=RESULT_DIR_DEFAULT,
                        help="output directory for CSV/figures/verdict")
    parser.add_argument("--ckpt-dir",  default=CKPT_DIR_DEFAULT,
                        help="checkpoint storage directory")
    parser.add_argument("--phase", choices=["train", "eval", "all"], default="all",
                        help="all=train+eval | eval=eval only (needs ckpts) | train=train only")
    parser.add_argument("--arm", choices=["A", "B", "C", "DE"], default=None,
                        help="run single arm only (default: all arms)")
    parser.add_argument("--epochs", type=int, default=None,
                        help="override N_EPOCHS (reduced-epoch gating probe; default官方 500)")
    args = parser.parse_args()
    run(args)
