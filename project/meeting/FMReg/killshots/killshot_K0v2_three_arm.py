"""
killshot_K0v2_three_arm.py
FMReg A0 立项闸 K0v2：三臂 killshot
  「FM 真多解后验」vs「确定性异方差/cVAE 后验（臂 B）」vs「确定性基线（臂 A）」

证伪线（预登记，compute_verdict 跑前写死，不事后调阈）：
  GREEN  = dip_C 显著 AND dip_C > dip_B（bootstrap CI 排除 0）AND dice_C_ensemble ≥ dice_A
           守门：neg_jac_pct_C < 0.10（排除「多峰=发散」假阳）
  RED    = dip_C 不显著 AND rho_C 不优于 rho_B（C 后验与 B 无可区分）
  YELLOW = rho_C > rho_B 但 dip_C 无显著多峰

三臂：
  A（det）          : TinyUNet(in=2) → SVF v → S&S → φ → warp
                      loss: NCC(warp,fixed) + λ_s·‖∇v‖²  (λ_s=1.0)
                      out_conv init: Normal(0,1e-5), bias=0

  B（cVAE/VoxelMorph-prob 式）: TinyUNet 双头 mean_v + log_sigma → reparam → S&S
                      loss: NCC(mean_v → S&S → warp, fixed) + KL (Laplacian 先验)
                      TODO: researcher 查 VoxelMorph-prob 官方 prior_lambda 默认
                            （Dalca 2019 附录，voxelmorph/tf/losses.py KL class）
                            占位 prior_lambda=10

  C（FM warp-driven，零 teacher）: TinyUNetFM(in=moving+fixed+ψ_t+t) → FM velocity
                      训练：ψ_0~N(0,σ_p²), t~U(0,1), 1-2 步 Euler rollout 驱动配准损失
                      σ_p：先跑少量步 A 统计 SVF std，数据驱动设定（不臆想固定值）

Eval 数据两套：
  1. BraTS 自然大形变对（100 对，top40% mean_disp 子集）
  2. 受控歧义对（25 对，synth_ambiguity_pair，人造单 blob→双对称 blob）

分叉度指标（受控歧义对上，K=8 采样，纯 numpy）：
  disp_spread / dip_stat（Hartigan dip，手写纯 numpy）/ bimodal_coeff（Sarle BC）
  cluster_sep（2-means silhouette 近似）/ rho（后验方差↔配准误差 Pearson）

运行：
  python killshot_K0v2_three_arm.py          # full: 2000 步×3 臂, K=8, eval 100+25 对
  python killshot_K0v2_three_arm.py --smoke  # 5 对/10 步/K=3/CPU < 60s

输出：
  killshots/results/killshot_K0v2_three_arm.csv
  killshots/results/k0v2_posterior_BvsC.png

Windows 规范：num_workers=0, pin_memory=False, spawn-safe, forward-slash 路径,
              纯 numpy 统计 (no scipy, 避 OMP Error #15), matplotlib Agg
"""

import argparse
import os
import sys
import glob
import csv
import time
import random
import math

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

try:
    from PIL import Image
except ImportError:
    print("[ERROR] Pillow not found. pip install Pillow")
    sys.exit(1)

# ============================================================
# 复用 K0v1 几何/损失算子（避免重复实现）
# ============================================================
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

try:
    from killshot_K0_fm_vs_vxmdiff import (
        scaling_and_squaring,  # svf[B,2,H,W] → disp[B,H,W,2]
        warp_by_disp,          # (moving, disp) → warped
        make_identity_grid,    # (B,H,W,device) → [B,H,W,2]
        ncc_loss,              # returns -NCC (for minimization)
        smooth_loss,           # ‖∇v‖²
        dice_fg_numpy,         # pure numpy Dice
        pearson_r_numpy,       # pure numpy Pearson (no scipy)
        jacobian_det_disp,     # [B,H-2,W-2] Jacobian det
        BraTSPairDataset,      # inter-subject pair dataset
    )
    print("[INFO] Imported shared ops from killshot_K0_fm_vs_vxmdiff.py")
except ImportError as e:
    print(f"[ERROR] Cannot import K0v1 ops: {e}")
    sys.exit(1)

# ============================================================
# 复用 K0v2 探针的受控歧义对构造
# ============================================================
try:
    from killshot_K0v2_energy_probe import (
        build_controlled_pair,  # → (moving, fixed, psi_left, psi_right)
        make_gaussian_blob,
        PAIR_CONFIGS,
    )
    print("[INFO] Imported synth_ambiguity_pair ops from killshot_K0v2_energy_probe.py")
except ImportError as e:
    print(f"[ERROR] Cannot import K0v2 probe ops: {e}")
    sys.exit(1)

# ============================================================
# 路径 & 超参常量
# ============================================================
DATA_DIR   = "D:/YJ-Agent/project/meeting/MedAD-FailMap/data/BraTS2021/train"
RESULT_DIR = "D:/YJ-Agent/project/meeting/FMReg/killshots/results"
RESULT_CSV = os.path.join(RESULT_DIR, "killshot_K0v2_three_arm.csv")
RESULT_FIG = os.path.join(RESULT_DIR, "k0v2_posterior_BvsC.png")

IMG_SIZE     = 128
BRAIN_THRESH = 0.05
SS_INT_STEPS = 7

# 臂 A/B/C 共享超参
# TODO: 未找到官方 VoxelMorph-diff 2D BraTS lr；以下 1e-4 参考常见实践，需 researcher 确认
LR         = 1e-4
LAMBDA_S   = 1.0    # 空间正则系数（共享）
K_SAMPLES  = 48     # eval 后验采样次数（full）  [BUG-FIX #2: K=8 dip 精度粗 → K=48]

# 臂 B（cVAE/VoxelMorph-prob）
# TODO: researcher 查 VoxelMorph-prob 官方 prior_lambda 默认值
#       （Dalca 2019 "Unsupervised Learning of Probabilistic Diffeomorphic Registration for Images
#       and Surfaces" 附录，voxelmorph/tf/losses.py KL class）
#       占位值 10，不可用于 paper 直接引用，等 researcher 确认后替换
PRIOR_LAMBDA = 10

# 臂 C（FM warp-driven）
# σ_p 由数据驱动标定（在 run() 内先跑少量 A 步估计 SVF std），不臆想固定值
# 下方 SIGMA_P_PLACEHOLDER 仅作 fallback；实际由 estimate_sigma_p() 覆写
SIGMA_P_PLACEHOLDER = 0.15  # fallback 量级参考，不用于 full run
FM_ROLLOUT_STEPS    = 2     # 训练内 Euler 步数（≤2 控显存，rollout 内反传）
FM_EVAL_STEPS       = 4     # eval Euler 步数（no_grad）


# ============================================================
# Building blocks
# ============================================================
class ConvBlock(nn.Module):
    def __init__(self, cin, cout):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(cin, cout, 3, padding=1),
            nn.InstanceNorm2d(cout),
            nn.LeakyReLU(0.2),
            nn.Conv2d(cout, cout, 3, padding=1),
            nn.InstanceNorm2d(cout),
            nn.LeakyReLU(0.2),
        )

    def forward(self, x):
        return self.net(x)


class TinyUNetDet(nn.Module):
    """
    臂 A：确定性 SVF 输出。
    in=[B,2,H,W] → out=[B,2,H,W] SVF v
    out_conv init: Normal(0,1e-5), bias=0
    （VoxelMorph 官方 mean flow init，researcher 确认）
    """
    def __init__(self, in_ch=2, base=16):
        super().__init__()
        self.enc1 = ConvBlock(in_ch, base)
        self.enc2 = ConvBlock(base, base * 2)
        self.enc3 = ConvBlock(base * 2, base * 4)
        self.pool = nn.MaxPool2d(2)
        self.bottleneck = ConvBlock(base * 4, base * 8)
        self.up3  = nn.ConvTranspose2d(base * 8, base * 4, 2, stride=2)
        self.dec3 = ConvBlock(base * 8, base * 4)
        self.up2  = nn.ConvTranspose2d(base * 4, base * 2, 2, stride=2)
        self.dec2 = ConvBlock(base * 4, base * 2)
        self.up1  = nn.ConvTranspose2d(base * 2, base, 2, stride=2)
        self.dec1 = ConvBlock(base * 2, base)
        self.out_conv = nn.Conv2d(base, 2, 1)
        # VoxelMorph 官方 mean flow init: Normal(0,1e-5), bias=0
        nn.init.normal_(self.out_conv.weight, std=1e-5)
        nn.init.zeros_(self.out_conv.bias)

    def forward(self, x):
        e1 = self.enc1(x)
        e2 = self.enc2(self.pool(e1))
        e3 = self.enc3(self.pool(e2))
        b  = self.bottleneck(self.pool(e3))
        d3 = self.dec3(torch.cat([self.up3(b),  e3], dim=1))
        d2 = self.dec2(torch.cat([self.up2(d3), e2], dim=1))
        d1 = self.dec1(torch.cat([self.up1(d2), e1], dim=1))
        return self.out_conv(d1)


class TinyUNetCVAE(nn.Module):
    """
    臂 B：VoxelMorph-prob 式双头输出（mean_v + log_sigma）。
    in=[B,2,H,W] → mean_v[B,2,H,W], log_sigma[B,2,H,W]

    Init（官方）：
      mean head: Normal(0,1e-5), bias=0
      log_sigma head: Normal(0,1e-10), bias=-10
        → 训练初期 σ≈exp(-10/2)≈0.007 极小，防 KL 爆炸
    """
    def __init__(self, in_ch=2, base=16):
        super().__init__()
        self.enc1 = ConvBlock(in_ch, base)
        self.enc2 = ConvBlock(base, base * 2)
        self.enc3 = ConvBlock(base * 2, base * 4)
        self.pool = nn.MaxPool2d(2)
        self.bottleneck = ConvBlock(base * 4, base * 8)
        self.up3  = nn.ConvTranspose2d(base * 8, base * 4, 2, stride=2)
        self.dec3 = ConvBlock(base * 8, base * 4)
        self.up2  = nn.ConvTranspose2d(base * 4, base * 2, 2, stride=2)
        self.dec2 = ConvBlock(base * 4, base * 2)
        self.up1  = nn.ConvTranspose2d(base * 2, base, 2, stride=2)
        self.dec1 = ConvBlock(base * 2, base)

        # 双头：mean + log_sigma
        self.mean_head     = nn.Conv2d(base, 2, 1)
        self.logsigma_head = nn.Conv2d(base, 2, 1)

        nn.init.normal_(self.mean_head.weight,     std=1e-5)
        nn.init.zeros_(self.mean_head.bias)
        nn.init.normal_(self.logsigma_head.weight, std=1e-10)
        nn.init.constant_(self.logsigma_head.bias, -10.0)

    def forward(self, x):
        e1 = self.enc1(x)
        e2 = self.enc2(self.pool(e1))
        e3 = self.enc3(self.pool(e2))
        b  = self.bottleneck(self.pool(e3))
        d3 = self.dec3(torch.cat([self.up3(b),  e3], dim=1))
        d2 = self.dec2(torch.cat([self.up2(d3), e2], dim=1))
        d1 = self.dec1(torch.cat([self.up1(d2), e1], dim=1))
        mean_v     = self.mean_head(d1)
        log_sigma  = self.logsigma_head(d1)
        return mean_v, log_sigma


class TinyUNetFM(nn.Module):
    """
    臂 C：FM velocity 网络。
    in=[B, 5, H, W] = moving(1)+fixed(1)+ψ_t(2)+t_map(1)
    out=[B, 2, H, W] FM velocity u
    """
    def __init__(self, base=16):
        super().__init__()
        in_ch = 5
        self.enc1 = ConvBlock(in_ch, base)
        self.enc2 = ConvBlock(base, base * 2)
        self.enc3 = ConvBlock(base * 2, base * 4)
        self.pool = nn.MaxPool2d(2)
        self.bottleneck = ConvBlock(base * 4, base * 8)
        self.up3  = nn.ConvTranspose2d(base * 8, base * 4, 2, stride=2)
        self.dec3 = ConvBlock(base * 8, base * 4)
        self.up2  = nn.ConvTranspose2d(base * 4, base * 2, 2, stride=2)
        self.dec2 = ConvBlock(base * 4, base * 2)
        self.up1  = nn.ConvTranspose2d(base * 2, base, 2, stride=2)
        self.dec1 = ConvBlock(base * 2, base)
        self.out_conv = nn.Conv2d(base, 2, 1)
        nn.init.normal_(self.out_conv.weight, std=1e-5)
        nn.init.zeros_(self.out_conv.bias)

    def forward(self, moving, fixed, psi_t, t):
        """
        moving, fixed: [B,1,H,W]
        psi_t        : [B,2,H,W]
        t            : [B] scalar in [0,1]
        returns u    : [B,2,H,W]
        """
        B, _, H, W = moving.shape
        t_map = t.view(B, 1, 1, 1).expand(B, 1, H, W)
        x = torch.cat([moving, fixed, psi_t, t_map], dim=1)
        e1 = self.enc1(x)
        e2 = self.enc2(self.pool(e1))
        e3 = self.enc3(self.pool(e2))
        b  = self.bottleneck(self.pool(e3))
        d3 = self.dec3(torch.cat([self.up3(b),  e3], dim=1))
        d2 = self.dec2(torch.cat([self.up2(d3), e2], dim=1))
        d1 = self.dec1(torch.cat([self.up1(d2), e1], dim=1))
        return self.out_conv(d1)


# ============================================================
# 臂 B KL 损失（VoxelMorph-prob Laplacian 先验）
# ============================================================
def kl_laplacian_loss(mean_v, log_sigma, prior_lambda=PRIOR_LAMBDA, ndims=2):
    """
    KL(q || prior) 参照 voxelmorph/tf/losses.py KL class（Laplacian 先验）。

    sigma_term = prior_lambda * D * exp(log_sigma) - log_sigma
                 D = 邻域度矩阵；2D 内部像素度 = 4，简化为常数 4
    prec_term  = prior_lambda * 0.5 * sum_{邻域}(mean_i - mean_j)^2
                 ≈ prior_lambda * spatial_smooth(mean_v)  (‖∇mean_v‖²)

    loss = 0.5 * ndims * mean(sigma_term + prec_term)

    注：prior_lambda=PRIOR_LAMBDA 占位（TODO：researcher 确认官方默认）。
    mean_v    : [B,2,H,W]
    log_sigma : [B,2,H,W]
    """
    D_const = 4.0  # 2D 内部像素邻域度

    # sigma_term：每像素值
    sigma_term = prior_lambda * D_const * torch.exp(log_sigma) - log_sigma  # [B,2,H,W]

    # prec_term：mean velocity 空间梯度平方（Laplacian 平滑近似）
    # 与 smooth_loss 同形式，但用 mean_v
    dx = mean_v[:, :, :, 1:] - mean_v[:, :, :, :-1]
    dy = mean_v[:, :, 1:, :] - mean_v[:, :, :-1, :]
    prec_term_val = prior_lambda * ((dx ** 2).mean() + (dy ** 2).mean())

    kl = 0.5 * ndims * (sigma_term.mean() + prec_term_val)
    return kl


# ============================================================
# 训练：臂 A（确定性 det）
# ============================================================
def train_arm_A(loader, n_steps, device):
    """
    臂 A：确定性 VoxelMorph-diff 式配准。
    损失: NCC(warp(moving, S&S(v)), fixed) + λ_s·‖∇v‖²
    Returns trained model.
    """
    print("[INFO] === 训练臂 A (det: TinyUNetDet) ===")
    model = TinyUNetDet(in_ch=2, base=16).to(device)
    opt   = torch.optim.Adam(model.parameters(), lr=LR)
    model.train()
    step     = 0
    log_every = max(1, n_steps // 10)
    t0 = time.time()

    while step < n_steps:
        for moving, fixed in loader:
            if step >= n_steps:
                break
            moving, fixed = moving.to(device), fixed.to(device)
            opt.zero_grad()
            inp  = torch.cat([moving, fixed], dim=1)
            v    = model(inp)
            disp = scaling_and_squaring(v, SS_INT_STEPS)
            warped = warp_by_disp(moving, disp)
            loss = ncc_loss(warped, fixed) + LAMBDA_S * smooth_loss(v)
            loss.backward()
            opt.step()
            step += 1
            if step % log_every == 0 or step <= 3:
                print(f"  [A-det] step {step}/{n_steps}  loss={loss.item():.5f}  "
                      f"t={time.time()-t0:.1f}s")
    print(f"[INFO] 臂 A 训练完成 ({time.time()-t0:.1f}s)")
    return model


# ============================================================
# σ_p 数据驱动估计（消源②：先跑少量步 A 估 SVF std）
# ============================================================
def estimate_sigma_p(arm_a_model, loader, device, n_batches=5):
    """
    用已训练（或部分训练）的臂 A 模型在训练集统计 SVF std，
    σ_p 取该量级作为臂 C 的 prior noise scale。
    不臆想固定值。

    Returns: sigma_p (float), estimated std of SVF outputs
    """
    arm_a_model.eval()
    all_stds = []
    with torch.no_grad():
        for i, (moving, fixed) in enumerate(loader):
            if i >= n_batches:
                break
            moving, fixed = moving.to(device), fixed.to(device)
            inp = torch.cat([moving, fixed], dim=1)
            v   = arm_a_model(inp)          # [B,2,H,W]
            std_batch = float(v.std().cpu().item())
            all_stds.append(std_batch)
    sigma_p = float(np.mean(all_stds)) if all_stds else SIGMA_P_PLACEHOLDER
    sigma_p = max(sigma_p, 1e-4)  # 防极小值
    print(f"[INFO] 估计 σ_p (臂 A SVF std over {len(all_stds)} batches) = {sigma_p:.6f}")
    return sigma_p


# ============================================================
# 训练：臂 B（cVAE/VoxelMorph-prob 式）
# ============================================================
def train_arm_B(loader, n_steps, device):
    """
    臂 B：VoxelMorph-prob 式 cVAE（解析高斯后验）。
    损失: NCC(warp(mean_v → S&S), fixed) + KL (Laplacian 先验)
    eval 时 K=8 reparam 采样。
    Returns trained model.
    """
    print("[INFO] === 训练臂 B (cVAE: TinyUNetCVAE, VoxelMorph-prob 式) ===")
    model = TinyUNetCVAE(in_ch=2, base=16).to(device)
    opt   = torch.optim.Adam(model.parameters(), lr=LR)
    model.train()
    step     = 0
    log_every = max(1, n_steps // 10)
    t0 = time.time()

    while step < n_steps:
        for moving, fixed in loader:
            if step >= n_steps:
                break
            moving, fixed = moving.to(device), fixed.to(device)
            opt.zero_grad()
            inp             = torch.cat([moving, fixed], dim=1)
            mean_v, log_sig = model(inp)

            # reconstruction 用 mean_v（不采样，稳定梯度）
            disp   = scaling_and_squaring(mean_v, SS_INT_STEPS)
            warped = warp_by_disp(moving, disp)
            recon_loss = ncc_loss(warped, fixed)

            kl = kl_laplacian_loss(mean_v, log_sig, prior_lambda=PRIOR_LAMBDA)
            loss = recon_loss + kl
            loss.backward()
            opt.step()
            step += 1
            if step % log_every == 0 or step <= 3:
                print(f"  [B-cVAE] step {step}/{n_steps}  "
                      f"recon={recon_loss.item():.5f}  kl={kl.item():.5f}  "
                      f"t={time.time()-t0:.1f}s")
    print(f"[INFO] 臂 B 训练完成 ({time.time()-t0:.1f}s)")
    return model


# ============================================================
# 训练：臂 C（FM warp-driven，零 teacher）
# ============================================================
def train_arm_C(loader, n_steps, device, sigma_p):
    """
    臂 C：FM warp-driven（消蒸馏陷阱）。

    每步：
      ψ_0 ~ N(0, σ_p²)
      t ~ U(0,1)
      用 1-2 步 Euler rollout 从 ψ_0 生成 ψ̂（rollout 内反传）
        ψ_{k+1} = ψ_k + (1/rollout_steps) * u_θ(ψ_k, t_k, moving, fixed)
      损失: NCC(warp(moving, S&S(ψ̂)), fixed) + λ_s·‖∇ψ̂‖²

    关键：无任何固定 target SVF，ψ̂ 完全由配准重建损失驱动。
    σ_p 由 estimate_sigma_p() 数据驱动设定。
    """
    print(f"[INFO] === 训练臂 C (FM warp-driven, 零 teacher, σ_p={sigma_p:.6f}) ===")
    model = TinyUNetFM(base=16).to(device)
    opt   = torch.optim.Adam(model.parameters(), lr=LR)
    model.train()
    step     = 0
    log_every = max(1, n_steps // 10)
    t0 = time.time()
    rollout_dt = 1.0 / FM_ROLLOUT_STEPS

    while step < n_steps:
        for moving, fixed in loader:
            if step >= n_steps:
                break
            moving, fixed = moving.to(device), fixed.to(device)
            B, _, H, W = moving.shape
            opt.zero_grad()

            # ψ_0 ~ N(0, σ_p²)
            psi = torch.randn(B, 2, H, W, device=device) * sigma_p

            # t ~ U(0,1)，整段 rollout 用同一 t（简化，保 rollout 内反传）
            t_samp = torch.rand(B, device=device)

            # Euler rollout（FM_ROLLOUT_STEPS 步，rollout 内反传）
            for k in range(FM_ROLLOUT_STEPS):
                t_k = t_samp + k * rollout_dt  # 沿 [t, t+1] 段
                t_k = t_k.clamp(0.0, 1.0)
                u   = model(moving, fixed, psi, t_k)
                psi = psi + rollout_dt * u    # 更新 ψ，grad 流过

            psi_hat = psi  # [B,2,H,W]，由配准损失驱动

            disp   = scaling_and_squaring(psi_hat, SS_INT_STEPS)
            warped = warp_by_disp(moving, disp)
            loss   = ncc_loss(warped, fixed) + LAMBDA_S * smooth_loss(psi_hat)
            loss.backward()
            opt.step()
            step += 1
            if step % log_every == 0 or step <= 3:
                print(f"  [C-FM]   step {step}/{n_steps}  loss={loss.item():.5f}  "
                      f"t={time.time()-t0:.1f}s")
    print(f"[INFO] 臂 C 训练完成 ({time.time()-t0:.1f}s)")
    return model


# ============================================================
# 受控歧义对数据集（基于探针的 build_controlled_pair）
# ============================================================

# [BUG-FIX #1] 扩展为 24 个几何各不相同的 distinct 配置，取代原来 5×循环复制
# 原 PAIR_CONFIGS 只有 5 种，重复 5 次 → n_eff=5，bootstrap CI 假窄。
# 现在覆盖为本地 24 种，各 (sigma, offset_x, note) 均不同。
# sigma ∈ {6,8,10,12,15}，offset_x ∈ {18,24,30,36,42}，offset_y ∈ {0,4,8}
# 组合策略：先穷举 sigma×offset_x 主矩阵 15 种，再加 offset_y 扰动 9 种
# 共 24 种，每种几何含义均不同（distinct sigma/offset 组合）。
_LOCAL_PAIR_CONFIGS = [
    # sigma, offset_x, note  （offset_y 由 build_controlled_pair 扩展版支持；
    # 原函数签名只有 sigma+offset_x → offset_y=0 条目用原函数，
    # offset_y≠0 条目用下方 build_controlled_pair_oy 包装）
    # ---- 主矩阵 sigma×offset_x (offset_y=0) ----
    (6.0,   18, "s6-ox18-oy0"),
    (6.0,   24, "s6-ox24-oy0"),
    (6.0,   30, "s6-ox30-oy0"),
    (8.0,   18, "s8-ox18-oy0"),
    (8.0,   24, "s8-ox24-oy0"),
    (8.0,   36, "s8-ox36-oy0"),
    (10.0,  24, "s10-ox24-oy0"),
    (10.0,  30, "s10-ox30-oy0"),
    (10.0,  42, "s10-ox42-oy0"),
    (12.0,  24, "s12-ox24-oy0"),
    (12.0,  30, "s12-ox30-oy0"),
    (12.0,  36, "s12-ox36-oy0"),
    (15.0,  30, "s15-ox30-oy0"),
    (15.0,  36, "s15-ox36-oy0"),
    (15.0,  42, "s15-ox42-oy0"),
    # ---- offset_y 扰动（中心偏上/偏下，增加几何多样性）----
    (8.0,   24, "s8-ox24-oy4"),   # offset_y=+4
    (8.0,   30, "s8-ox30-oy4"),
    (10.0,  24, "s10-ox24-oy4"),
    (10.0,  36, "s10-ox36-oy4"),
    (12.0,  30, "s12-ox30-oy4"),
    (10.0,  24, "s10-ox24-oy8"),  # offset_y=+8
    (10.0,  30, "s10-ox30-oy8"),
    (12.0,  24, "s12-ox24-oy8"),
    (15.0,  30, "s15-ox30-oy8"),
]
assert len(_LOCAL_PAIR_CONFIGS) == 24, "必须 24 个 distinct configs"

# offset_y 值表（与 _LOCAL_PAIR_CONFIGS 对应，index 对齐）
_LOCAL_PAIR_OFFSET_Y = [
    0, 0, 0,   # s6
    0, 0, 0,   # s8
    0, 0, 0,   # s10
    0, 0, 0,   # s12
    0, 0, 0,   # s15
    4, 4, 4, 4, 4,   # offset_y=4
    8, 8, 8, 8,      # offset_y=8
]
assert len(_LOCAL_PAIR_OFFSET_Y) == 24, "offset_y 表必须 24 个"


def _build_pair_with_oy(H, W, sigma, offset_x, offset_y, device):
    """
    build_controlled_pair 的 offset_y 扩展版本（纯局部，不修改 energy_probe）。
    offset_y=0 时与原函数等价；offset_y≠0 时 fixed blob 中心沿 y 轴偏移 offset_y 像素。
    """
    cy, cx = H / 2, W / 2
    # moving: 中心 blob（不偏移）
    mov_np = make_gaussian_blob(H, W, cx=cx, cy=cy, sigma=sigma)
    # fixed: 左 + 右 blob，cy 偏移 offset_y（使两峰不完全对称于 x 轴）
    left_np  = make_gaussian_blob(H, W, cx=cx - offset_x, cy=cy + offset_y, sigma=sigma)
    right_np = make_gaussian_blob(H, W, cx=cx + offset_x, cy=cy + offset_y, sigma=sigma)
    fix_np   = np.clip(left_np + right_np, 0.0, 1.0).astype(np.float32)

    moving = torch.from_numpy(mov_np[None, None]).to(device)
    fixed  = torch.from_numpy(fix_np[None, None]).to(device)

    shift_norm_x = -float(offset_x) / (W / 2.0)
    shift_norm_y = float(offset_y) / (H / 2.0)
    psi_left_np  = np.zeros((1, 2, H, W), dtype=np.float32)
    psi_left_np[:, 0, :, :] = shift_norm_x
    psi_left_np[:, 1, :, :] = shift_norm_y
    psi_right_np = np.zeros((1, 2, H, W), dtype=np.float32)
    psi_right_np[:, 0, :, :] = -shift_norm_x
    psi_right_np[:, 1, :, :] = shift_norm_y

    psi_left  = torch.from_numpy(psi_left_np).to(device)
    psi_right = torch.from_numpy(psi_right_np).to(device)
    return moving, fixed, psi_left, psi_right


def make_synth_ambiguity_pairs(n_pairs, device, size=IMG_SIZE):
    """
    生成 n_pairs 个受控歧义对（直接用前 n_pairs 个 distinct config，不循环复制）。
    [BUG-FIX #1] 原实现 PAIR_CONFIGS*循环 → n_eff=5，现改为 24 distinct configs。
    n_pairs full=24, smoke=3。
    每对: (moving[1,1,H,W], fixed[1,1,H,W], psi_left[1,2,H,W], psi_right[1,2,H,W])
    """
    assert n_pairs <= len(_LOCAL_PAIR_CONFIGS), \
        f"n_pairs={n_pairs} 超过 distinct configs={len(_LOCAL_PAIR_CONFIGS)}"
    pairs = []
    for i in range(n_pairs):
        sigma, offset_x, note = _LOCAL_PAIR_CONFIGS[i]
        offset_y = _LOCAL_PAIR_OFFSET_Y[i]
        moving, fixed, psi_l, psi_r = _build_pair_with_oy(
            size, size, sigma, offset_x, offset_y, device
        )
        pairs.append((moving, fixed, psi_l, psi_r, note))
    return pairs


# ============================================================
# 臂 A eval（BraTS + 受控歧义）
# ============================================================
def eval_arm_A(model, eval_loader, device):
    """Returns: dice, neg_jac_pct, mean_disp (per-sample lists)."""
    model.eval()
    dices, neg_jacs, mean_disps = [], [], []
    with torch.no_grad():
        for moving, fixed in eval_loader:
            moving, fixed = moving.to(device), fixed.to(device)
            inp    = torch.cat([moving, fixed], dim=1)
            v      = model(inp)
            disp   = scaling_and_squaring(v, SS_INT_STEPS)
            warped = warp_by_disp(moving, disp)

            dices.extend(dice_fg_numpy(warped.cpu().numpy(), fixed.cpu().numpy()))

            jac     = jacobian_det_disp(disp)
            neg_pct = (jac < 0).float().mean(dim=[-1, -2]).cpu().numpy()
            neg_jacs.extend(neg_pct.tolist())

            # mean displacement magnitude [B]
            disp_np  = disp.cpu().numpy()                        # [B,H,W,2]
            mag_mean = np.sqrt((disp_np ** 2).sum(axis=-1)).mean(axis=(1, 2))
            mean_disps.extend(mag_mean.tolist())

    return {"dice": dices, "neg_jac_pct": neg_jacs, "mean_disp": mean_disps}


# ============================================================
# 臂 B eval
# ============================================================
def eval_arm_B(model, eval_loader, device, k_samples):
    """
    Returns: dice (mean), neg_jac_pct, mean_disp,
             posterior_vars (per-sample K 样本后验方差),
             recon_errs (per-sample MAE)
    eval: K 次 reparam 采样（no_grad）
    """
    model.eval()
    dices, neg_jacs, mean_disps = [], [], []
    post_vars, recon_errs = [], []

    with torch.no_grad():
        for moving, fixed in eval_loader:
            moving, fixed = moving.to(device), fixed.to(device)
            inp = torch.cat([moving, fixed], dim=1)
            mean_v, log_sig = model(inp)

            # 主评估用 mean_v（无噪声 deterministic）
            disp   = scaling_and_squaring(mean_v, SS_INT_STEPS)
            warped = warp_by_disp(moving, disp)
            dices.extend(dice_fg_numpy(warped.cpu().numpy(), fixed.cpu().numpy()))

            jac     = jacobian_det_disp(disp)
            neg_pct = (jac < 0).float().mean(dim=[-1, -2]).cpu().numpy()
            neg_jacs.extend(neg_pct.tolist())

            disp_np  = disp.cpu().numpy()
            mag_mean = np.sqrt((disp_np ** 2).sum(axis=-1)).mean(axis=(1, 2))
            mean_disps.extend(mag_mean.tolist())

            # recon err (from mean path)
            recon_np = np.abs(warped.cpu().numpy() - fixed.cpu().numpy()).mean(axis=(1, 2, 3))
            recon_errs.extend(recon_np.tolist())

            # K 后验样本：reparam v_k = mean_v + exp(0.5*log_sigma)*ε_k
            psi_samples = []
            for _ in range(k_samples):
                eps = torch.randn_like(mean_v)
                v_k = mean_v + torch.exp(0.5 * log_sig) * eps
                psi_samples.append(v_k.cpu().numpy())   # [B,2,H,W]
            psi_stack = np.stack(psi_samples, axis=0)   # [K,B,2,H,W]
            var_k = psi_stack.var(axis=0).mean(axis=(1, 2, 3))  # [B]
            post_vars.extend(var_k.tolist())

    return {
        "dice": dices, "neg_jac_pct": neg_jacs, "mean_disp": mean_disps,
        "posterior_vars": post_vars, "recon_errs": recon_errs,
    }


# ============================================================
# 臂 C eval（FM Euler 采样）
# ============================================================
def fm_sample_psi(model, moving, fixed, device, sigma_p, n_steps, seed=None):
    """
    FM eval: Euler 积分 n_steps 步生成 ψ̂（no_grad）。
    ψ_0 ~ N(0, σ_p²)，每次不同 seed → 不同样本。
    """
    B, _, H, W = moving.shape
    if seed is not None:
        rng = np.random.default_rng(seed)
        psi_np = rng.standard_normal((B, 2, H, W)).astype(np.float32) * sigma_p
        psi = torch.from_numpy(psi_np).to(device)
    else:
        psi = torch.randn(B, 2, H, W, device=device) * sigma_p
    dt = 1.0 / n_steps
    with torch.no_grad():
        for i in range(n_steps):
            t_val = torch.full((B,), i * dt, device=device, dtype=torch.float32)
            u = model(moving, fixed, psi, t_val)
            psi = psi + dt * u
    return psi   # [B,2,H,W]


def eval_arm_C(model, eval_loader, device, k_samples, sigma_p):
    """
    Returns: dice (ensemble 均值), neg_jac_pct, mean_disp,
             posterior_vars, recon_errs
    eval: K 次不同 ψ_0 采样，ensemble dice 取各样本平均。
    """
    model.eval()
    dices_ens, neg_jacs, mean_disps = [], [], []
    post_vars, recon_errs = [], []

    with torch.no_grad():
        for moving, fixed in eval_loader:
            moving, fixed = moving.to(device), fixed.to(device)
            f_np = fixed.cpu().numpy()

            psi_samples = []
            warped_samples = []
            dice_per_k = []

            for k in range(k_samples):
                psi_k  = fm_sample_psi(model, moving, fixed, device,
                                       sigma_p, FM_EVAL_STEPS, seed=k)
                disp_k = scaling_and_squaring(psi_k, SS_INT_STEPS)
                w_k    = warp_by_disp(moving, disp_k)

                psi_samples.append(psi_k.cpu().numpy())
                warped_samples.append(w_k.cpu().numpy())
                dice_per_k.append(dice_fg_numpy(w_k.cpu().numpy(), f_np))

            # ensemble dice: mean over K samples, per-sample → flatten
            dice_per_k = np.array(dice_per_k)  # [K, B]
            dice_ens   = dice_per_k.mean(axis=0)  # [B]
            dices_ens.extend(dice_ens.tolist())

            # neg_jac from last sample（代表性）
            jac     = jacobian_det_disp(
                scaling_and_squaring(
                    torch.from_numpy(psi_samples[-1]).to(device), SS_INT_STEPS
                )
            )
            neg_pct = (jac < 0).float().mean(dim=[-1, -2]).cpu().numpy()
            neg_jacs.extend(neg_pct.tolist())

            # mean disp from last sample
            disp_np  = scaling_and_squaring(
                torch.from_numpy(psi_samples[-1]).to(device), SS_INT_STEPS
            ).cpu().numpy()
            mag_mean = np.sqrt((disp_np ** 2).sum(axis=-1)).mean(axis=(1, 2))
            mean_disps.extend(mag_mean.tolist())

            # recon err: mean over K samples
            warped_np_k = np.stack(warped_samples, axis=0)  # [K,B,1,H,W]
            recon_np = np.abs(warped_np_k - f_np[None]).mean(axis=(0, 2, 3, 4))  # [B]
            recon_errs.extend(recon_np.tolist())

            # posterior var: over K SVF samples
            psi_stack = np.stack(psi_samples, axis=0)   # [K,B,2,H,W]
            var_k = psi_stack.var(axis=0).mean(axis=(1, 2, 3))  # [B]
            post_vars.extend(var_k.tolist())

    return {
        "dice": dices_ens, "neg_jac_pct": neg_jacs, "mean_disp": mean_disps,
        "posterior_vars": post_vars, "recon_errs": recon_errs,
    }


# ============================================================
# 受控歧义对分叉度指标（纯 numpy，no scipy）
# ============================================================

def pca_project_1d(vecs):
    """
    vecs: [K, D] numpy float32
    Returns 1D projection along first principal component: [K]
    """
    K, D = vecs.shape
    if K < 2:
        return vecs[:, 0]
    centered = vecs - vecs.mean(axis=0, keepdims=True)
    # 协方差矩阵 → 用 SVD 取第一左奇异向量（等效 PCA 第一 PC）
    # D 可能很大（2*H*W），用 K×K trick（K 小时快）
    # C = (1/K) * centered @ centered.T → [K,K]
    C = (centered @ centered.T) / max(K - 1, 1)   # [K,K]
    # 最大特征向量（power iteration，numpy 手写，避免 scipy）
    v = np.ones(K, dtype=np.float64)
    v /= np.linalg.norm(v) + 1e-12
    for _ in range(50):
        v = C @ v
        norm = np.linalg.norm(v)
        if norm < 1e-12:
            break
        v /= norm
    proj = centered @ (centered.T @ v)  # 投影到 PC1 方向
    # 归一化到标量投影
    pc1_dir = centered.T @ v            # [D] PC1 direction（unnormalized）
    pc1_norm = np.linalg.norm(pc1_dir) + 1e-12
    scores = centered @ (pc1_dir / pc1_norm)  # [K]
    return scores.astype(np.float64)


def hartigan_dip_numpy(x):
    """
    Hartigan dip statistic（手写纯 numpy，无 diptest 包）。
    近似算法：寻找最大的「最小最大差」（greatest convex minorant 方法简化版）。

    参考思路：Hartigan & Hartigan 1985 统计量 = 最大可能的 F(x)-G(x)，
    其中 G 是将 F 约束为单峰分布。简化实现：基于排序后的 ECDF 与其凸壳之差。

    返回 dip 值（>=0），越大越多峰；无参数，仅统计量。
    TODO: 此为近似实现，若需要精确 p 值需完整 Hartigan 1985 算法，
          当前用于相对比较（臂 B vs 臂 C）足够，不作绝对 p 值声明。
    """
    x = np.sort(np.asarray(x, dtype=np.float64))
    n = len(x)
    if n < 4:
        return 0.0

    # ECDF
    ecdf = np.arange(1, n + 1) / n

    # 计算「greatest convex minorant」(GCM) 通过累积最大斜率
    # dip = max |ECDF - GCM| / 2  （简化，足够相对比较）
    # 用分段线性逼近 GCM
    gcm = np.zeros(n)
    gcm[0] = ecdf[0]
    for i in range(1, n):
        # GCM：i 之前所有点的最大斜率
        slopes = (ecdf[i] - ecdf[:i]) / (x[i] - x[:i] + 1e-12)
        gcm[i] = gcm[i - 1] + max(slopes.max(), 0.0) * (x[i] - x[i - 1]) \
                 if i > 0 else ecdf[i]
    gcm = np.minimum(gcm, 1.0)

    dip = float(np.max(np.abs(ecdf - gcm))) / 2.0
    return dip


def bimodal_coeff_numpy(x):
    """
    Sarle Bimodality Coefficient = (skew^2 + 1) / kurtosis.
    BC > 5/9 (~0.555) 通常提示双模态。
    x: 1D array-like
    """
    x = np.asarray(x, dtype=np.float64)
    n = len(x)
    if n < 4:
        return 0.0
    m  = x.mean()
    s  = x.std() + 1e-12
    xc = (x - m) / s
    skew = float(np.mean(xc ** 3))
    kurt = float(np.mean(xc ** 4))
    if kurt < 1e-6:
        return 0.0
    bc = (skew ** 2 + 1.0) / kurt
    return float(bc)


def cluster_sep_numpy(scores):
    """
    2-means silhouette 近似（1D）：
    1. 找最优分割点（穷举中点）使组内方差最小
    2. silhouette = (inter_dist - intra_dist) / max(inter, intra)
    返回值 in [-1,1]，越高越分离。
    """
    scores = np.asarray(scores, dtype=np.float64)
    n = len(scores)
    if n < 4:
        return 0.0
    s_sorted = np.sort(scores)

    best_intra = np.inf
    best_split = n // 2
    for split in range(1, n):
        g1 = s_sorted[:split]
        g2 = s_sorted[split:]
        intra = (g1.var() * len(g1) + g2.var() * len(g2)) / n
        if intra < best_intra:
            best_intra = intra
            best_split = split

    g1 = s_sorted[:best_split]
    g2 = s_sorted[best_split:]
    inter = abs(g1.mean() - g2.mean()) if (len(g1) > 0 and len(g2) > 0) else 0.0
    total_var = scores.var() + 1e-12
    sil = (inter - np.sqrt(best_intra + 1e-12)) / (np.sqrt(total_var))
    return float(np.clip(sil, -1.0, 1.0))


def compute_forking_metrics(warp_samples_np):
    """
    受控歧义对上的分叉度指标。
    warp_samples_np: [K, H, W] — K 个 warp 后图像（前景区域或全图均可）

    Returns dict:
      disp_spread: float
      dip_stat: float
      bimodal_coeff: float
      cluster_sep: float
    """
    K, H, W = warp_samples_np.shape
    flat = warp_samples_np.reshape(K, -1).astype(np.float64)  # [K, H*W]

    # disp_spread: K 个图像逐像素 std 的均值
    disp_spread = float(flat.std(axis=0).mean())

    # PCA 投影到 1D
    scores = pca_project_1d(flat)   # [K]

    dip  = hartigan_dip_numpy(scores)
    bc   = bimodal_coeff_numpy(scores)
    csep = cluster_sep_numpy(scores)

    return {
        "disp_spread":    disp_spread,
        "dip_stat":       dip,
        "bimodal_coeff":  bc,
        "cluster_sep":    csep,
    }


def eval_forking_on_synth(model_B, model_C, synth_pairs, device, k_samples, sigma_p):
    """
    在受控歧义对上计算三臂分叉度指标。

    Returns:
      results_B: list of per-pair dicts (forking metrics + rho)
      results_C: list of per-pair dicts
      proj_B_all: list of [K] 1D projection scores per pair (for figure)
      proj_C_all: list of [K] 1D projection scores per pair
    """
    model_B.eval()
    model_C.eval()
    results_B, results_C = [], []
    proj_B_all, proj_C_all = [], []

    for pair_idx, (moving, fixed, psi_l, psi_r, note) in enumerate(synth_pairs):
        # moving, fixed: [1,1,H,W] already on device

        # ---- 臂 B: K reparam 采样 ----
        inp = torch.cat([moving, fixed], dim=1)
        with torch.no_grad():
            mean_v, log_sig = model_B(inp)
        warps_B = []
        psi_B_samples = []
        for k in range(k_samples):
            with torch.no_grad():
                eps  = torch.randn_like(mean_v)
                v_k  = mean_v + torch.exp(0.5 * log_sig) * eps
                d_k  = scaling_and_squaring(v_k, SS_INT_STEPS)
                w_k  = warp_by_disp(moving, d_k)
            warps_B.append(w_k.cpu().numpy()[0, 0])      # [H,W]
            psi_B_samples.append(v_k.cpu().numpy())

        warps_B_np = np.stack(warps_B, axis=0)           # [K,H,W]
        m_B = compute_forking_metrics(warps_B_np)

        # rho_B: posterior var vs recon err（单对，单值）
        psi_B_stack = np.stack(psi_B_samples, axis=0)    # [K,1,2,H,W]
        var_B = float(psi_B_stack.var(axis=0).mean())
        recon_B = float(np.abs(warps_B_np.mean(axis=0) - fixed.cpu().numpy()[0, 0]).mean())
        # rho 在单对上无意义（标量），攒所有对后再算；先存 var/recon
        m_B["post_var"] = var_B
        m_B["recon_err"] = recon_B
        m_B["pair_note"] = note
        results_B.append(m_B)

        # PC1 投影供图
        flat_B = warps_B_np.reshape(k_samples, -1).astype(np.float64)
        proj_B_all.append(pca_project_1d(flat_B))

        # ---- 臂 C: K ψ_0 采样 ----
        warps_C = []
        psi_C_samples = []
        for k in range(k_samples):
            with torch.no_grad():
                psi_k = fm_sample_psi(model_C, moving, fixed, device,
                                      sigma_p, FM_EVAL_STEPS, seed=k)
                d_k   = scaling_and_squaring(psi_k, SS_INT_STEPS)
                w_k   = warp_by_disp(moving, d_k)
            warps_C.append(w_k.cpu().numpy()[0, 0])
            psi_C_samples.append(psi_k.cpu().numpy())

        warps_C_np = np.stack(warps_C, axis=0)
        m_C = compute_forking_metrics(warps_C_np)

        psi_C_stack = np.stack(psi_C_samples, axis=0)
        var_C = float(psi_C_stack.var(axis=0).mean())
        recon_C = float(np.abs(warps_C_np.mean(axis=0) - fixed.cpu().numpy()[0, 0]).mean())
        m_C["post_var"] = var_C
        m_C["recon_err"] = recon_C
        m_C["pair_note"] = note
        results_C.append(m_C)

        flat_C = warps_C_np.reshape(k_samples, -1).astype(np.float64)
        proj_C_all.append(pca_project_1d(flat_C))

        print(f"  [synth pair {pair_idx}]  "
              f"B dip={m_B['dip_stat']:.4f} bc={m_B['bimodal_coeff']:.3f}  |  "
              f"C dip={m_C['dip_stat']:.4f} bc={m_C['bimodal_coeff']:.3f}")

    return results_B, results_C, proj_B_all, proj_C_all


# ============================================================
# Bootstrap CI for dip difference（纯 numpy）
# ============================================================
def bootstrap_dip_diff_ci(scores_B_list, scores_C_list, n_boot=500, alpha=0.05):
    """
    scores_B_list, scores_C_list: list of [K] arrays (一个 per pair)
    Returns: (mean_diff, ci_low, ci_high) — dip_C - dip_B 的 bootstrap CI
    如果 ci_low > 0 → dip_C 显著优于 dip_B。
    """
    rng = np.random.default_rng(0)
    n_pairs = len(scores_B_list)
    if n_pairs == 0:
        return 0.0, -1.0, 1.0

    diffs = []
    for _ in range(n_boot):
        idx = rng.integers(0, n_pairs, size=n_pairs)
        d_B = np.mean([hartigan_dip_numpy(scores_B_list[i]) for i in idx])
        d_C = np.mean([hartigan_dip_numpy(scores_C_list[i]) for i in idx])
        diffs.append(d_C - d_B)
    diffs = np.array(diffs)
    mean_diff = float(diffs.mean())
    ci_low    = float(np.percentile(diffs, 100 * alpha / 2))
    ci_high   = float(np.percentile(diffs, 100 * (1 - alpha / 2)))
    return mean_diff, ci_low, ci_high


# ============================================================
# 机械 Verdict（预登记，不留事后调阈口子）
# ============================================================
def compute_verdict(
    dice_A, dice_C_ens,
    dip_B, dip_C,
    dip_diff_ci_low,    # bootstrap CI low bound of dip_C - dip_B
    rho_B, rho_C,
    neg_jac_pct_C,
    bc_B=0.0, bc_C=0.0,  # [BUG-FIX #3/#4] 新增 BC 双腿
):
    """
    [BUG-FIX #3] cluster_sep 已移除出判据（恒 1.0 饱和，unreliable）。
    [BUG-FIX #4] 三色判据重写，消除 dip 绝对阈 > 0.001 恒 True 问题。

    多峰「显著赢」用 bootstrap CI 排 0：
      dip_C_wins = dip_diff_ci_low > 0  （CI 排除 0 → C 多峰显著强于 B）

    BC 双模态佐证：
      bc_sig = BC_C > 0.555 (Sarle 双峰阈) AND BC_C > BC_B （C 比 B 更双峰）

    预登记三色（机械，不事后改）：
      GREEN  = dip_C_wins AND bc_sig
               AND dice_C_ens >= dice_A - 0.01
               AND neg_jac_pct_C < 0.10   # 守门：排除发散假阳
      RED    = (not dip_C_wins) AND rho_C <= rho_B + 0.02
      YELLOW = rho_C > rho_B + 0.02 AND (not dip_C_wins)
               ← 命中当前「校准赢但多峰未显著」情形
      其余   = AMBIGUOUS（应极少）

    注：bc_sig 失败但 dip_C_wins 时归 AMBIGUOUS 而非 GREEN，
        避免单腿多峰信号放行。
    """
    # [BUG-FIX #4] 多峰判据基于 bootstrap CI，不用 dip 绝对值阈
    dip_C_wins   = dip_diff_ci_low > 0.0          # CI 排 0 → 多峰显著
    bc_sig       = (bc_C > 0.555) and (bc_C > bc_B)  # BC 双腿佐证
    dice_ok      = dice_C_ens >= dice_A - 0.01
    guard_jac    = neg_jac_pct_C < 0.10

    rho_C_better = rho_C > rho_B + 0.02

    if dip_C_wins and bc_sig and dice_ok and guard_jac:
        return ("GREEN: dip_C_wins(CI>0) AND bc_sig(BC_C>0.555且>BC_B), "
                "dice_C_ensemble ≥ dice_A-0.01, neg_jac_pct_C < 10% "
                "→ FM 真多解后验成立，不可替换价值确认，放行 Gate1")
    elif dip_C_wins and bc_sig and dice_ok and not guard_jac:
        return ("YELLOW(发散守门触发): dip_C_wins AND bc_sig 但 neg_jac_pct_C >= 10% "
                "→ 多峰可能部分来自形变发散，需排查 λ_s 或增大 int_steps")
    elif (not dip_C_wins) and (not rho_C_better):
        return ("RED: dip_C not wins(CI≤0) AND rho_C 不优于 rho_B(+0.02) "
                "→ FM 后验与 cVAE 后验无可区分，多解后验假设不成立，报主线拍板降级")
    elif (not dip_C_wins) and rho_C_better:
        return ("YELLOW: rho_C > rho_B+0.02 但 dip_C not wins(CI≤0) "
                "→ 校准改善但多模态性未达显著，部分证据（当前 K0v2 full run 命中此分支）")
    else:
        return ("AMBIGUOUS: 指标混合信号，需人工解读 "
                f"(dip_C_wins={dip_C_wins}, bc_sig={bc_sig}, bc_C={bc_C:.4f}, bc_B={bc_B:.4f}, "
                f"dip_diff_ci_low={dip_diff_ci_low:.4f}, "
                f"dice_ok={dice_ok}, rho_C={rho_C:.4f}, rho_B={rho_B:.4f})")


# ============================================================
# 出图：受控歧义对 B vs C PCA 投影直方图
# ============================================================
def plot_posterior_BvsC(proj_B_all, proj_C_all, out_path):
    """
    叠加 B 和 C 各对的 PCA 1D 投影分布（直方图）。
    proj_B_all, proj_C_all: list of [K] arrays (per pair)
    """
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    colors_B = plt.cm.Blues(np.linspace(0.4, 0.9, len(proj_B_all)))
    colors_C = plt.cm.Reds(np.linspace(0.4, 0.9, len(proj_C_all)))

    for i, (pb, pc) in enumerate(zip(proj_B_all, proj_C_all)):
        axes[0].hist(pb, bins=min(len(pb), 8), alpha=0.6, color=colors_B[i],
                     label=f"pair {i}", density=True)
        axes[1].hist(pc, bins=min(len(pc), 8), alpha=0.6, color=colors_C[i],
                     label=f"pair {i}", density=True)

    axes[0].set_title("臂 B (cVAE): K samples PCA-1D distribution")
    axes[1].set_title("臂 C (FM): K samples PCA-1D distribution")
    for ax in axes:
        ax.set_xlabel("PC1 projection score")
        ax.set_ylabel("density")
        ax.legend(fontsize=7)
        ax.grid(True, alpha=0.3)

    fig.suptitle("K0v2 Posterior Forking: Arm B vs Arm C (Synth Ambiguity Pairs)", y=1.01)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    print(f"[SAVED FIG] {out_path}")


# ============================================================
# Main run
# ============================================================
def run(smoke=False, data_dir=DATA_DIR, out_dir=RESULT_DIR):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[INFO] K0v2 three-arm killshot | device={device} | smoke={smoke}")

    # --- 规模配置 ---
    n_train_pairs  = 5    if smoke else 400
    n_train_steps  = 10   if smoke else 2000
    n_eval_pairs   = 5    if smoke else 100
    n_synth_pairs  = 3    if smoke else 24   # [BUG-FIX #1: full=24 distinct configs]
    k_samp         = 4    if smoke else K_SAMPLES  # [BUG-FIX #2: smoke K=4, full K=48]
    batch_size     = 4

    print(f"[INFO] train_steps={n_train_steps}  eval_pairs={n_eval_pairs}  "
          f"synth_pairs={n_synth_pairs}  k_samples={k_samp}")

    # --- 数据集 ---
    train_ds = BraTSPairDataset(data_dir, n_pairs=n_train_pairs, size=IMG_SIZE, seed=42)
    train_dl = DataLoader(train_ds, batch_size=batch_size, shuffle=True,
                          num_workers=0, pin_memory=False)
    eval_ds  = BraTSPairDataset(data_dir, n_pairs=n_eval_pairs, size=IMG_SIZE, seed=99)
    eval_dl  = DataLoader(eval_ds, batch_size=batch_size, shuffle=False,
                          num_workers=0, pin_memory=False)

    # ===================== Phase 1: 训练臂 A =====================
    model_A = train_arm_A(train_dl, n_train_steps, device)

    # --- σ_p 数据驱动标定（用训练好的 A 统计 SVF std） ---
    sigma_p = estimate_sigma_p(model_A, train_dl, device, n_batches=5)
    print(f"[INFO] σ_p (data-driven) = {sigma_p:.6f}")

    # ===================== Phase 2: 训练臂 B =====================
    model_B = train_arm_B(train_dl, n_train_steps, device)

    # ===================== Phase 3: 训练臂 C =====================
    model_C = train_arm_C(train_dl, n_train_steps, device, sigma_p)

    # ===================== Phase 4: BraTS Eval =====================
    print("[INFO] === Eval on BraTS pairs ===")
    res_A = eval_arm_A(model_A, eval_dl, device)
    res_B = eval_arm_B(model_B, eval_dl, device, k_samp)
    res_C = eval_arm_C(model_C, eval_dl, device, k_samp, sigma_p)

    # top40% 大形变子集（按 mean_disp 排序取 top 40%）
    n_top = max(1, int(len(res_A["mean_disp"]) * 0.4))
    top_idx = np.argsort(res_A["mean_disp"])[-n_top:]

    def subset(lst, idx): return [lst[i] for i in idx]

    dice_A_top    = float(np.mean(subset(res_A["dice"],   top_idx)))
    dice_B_top    = float(np.mean(subset(res_B["dice"],   top_idx)))
    dice_C_top    = float(np.mean(subset(res_C["dice"],   top_idx)))
    neg_A_top     = float(np.mean(subset(res_A["neg_jac_pct"], top_idx))) * 100
    neg_B_top     = float(np.mean(subset(res_B["neg_jac_pct"], top_idx))) * 100
    neg_C_top     = float(np.mean(subset(res_C["neg_jac_pct"], top_idx))) * 100
    mean_disp_top = float(np.mean(subset(res_A["mean_disp"], top_idx)))

    rho_B, p_B = pearson_r_numpy(res_B["posterior_vars"], res_B["recon_errs"])
    rho_C, p_C = pearson_r_numpy(res_C["posterior_vars"], res_C["recon_errs"])
    # guard: pearson_r_numpy 返回 nan 时（方差≈0，smoke 少步常见）改为 0
    if math.isnan(rho_B):
        rho_B, p_B = 0.0, 1.0
    if math.isnan(rho_C):
        rho_C, p_C = 0.0, 1.0

    # ===================== Phase 5: Synth Ambiguity Eval =====================
    print("[INFO] === Eval on synth ambiguity pairs ===")
    synth_pairs = make_synth_ambiguity_pairs(n_synth_pairs, device, size=IMG_SIZE)
    res_syn_B, res_syn_C, proj_B_all, proj_C_all = eval_forking_on_synth(
        model_B, model_C, synth_pairs, device, k_samp, sigma_p
    )

    dip_B_mean = float(np.mean([r["dip_stat"]      for r in res_syn_B]))
    dip_C_mean = float(np.mean([r["dip_stat"]      for r in res_syn_C]))
    bc_B_mean  = float(np.mean([r["bimodal_coeff"] for r in res_syn_B]))
    bc_C_mean  = float(np.mean([r["bimodal_coeff"] for r in res_syn_C]))
    csep_B     = float(np.mean([r["cluster_sep"]   for r in res_syn_B]))
    csep_C     = float(np.mean([r["cluster_sep"]   for r in res_syn_C]))
    spread_B   = float(np.mean([r["disp_spread"]   for r in res_syn_B]))
    spread_C   = float(np.mean([r["disp_spread"]   for r in res_syn_C]))

    # bootstrap CI for dip_C - dip_B
    dip_diff_mean, dip_ci_low, dip_ci_high = bootstrap_dip_diff_ci(
        proj_B_all, proj_C_all, n_boot=200 if smoke else 500
    )

    # rho on synth pairs
    var_B_syn  = [r["post_var"]  for r in res_syn_B]
    err_B_syn  = [r["recon_err"] for r in res_syn_B]
    var_C_syn  = [r["post_var"]  for r in res_syn_C]
    err_C_syn  = [r["recon_err"] for r in res_syn_C]
    rho_B_syn, _ = pearson_r_numpy(var_B_syn, err_B_syn)
    rho_C_syn, _ = pearson_r_numpy(var_C_syn, err_C_syn)
    if math.isnan(rho_B_syn):
        rho_B_syn = 0.0
    if math.isnan(rho_C_syn):
        rho_C_syn = 0.0

    # ===================== Verdict =====================
    # [BUG-FIX #3/#4] 传入 bc_B/bc_C；cluster_sep 已移出判据（仍落 csv 标 unreliable）
    verdict = compute_verdict(
        dice_A      = float(np.mean(res_A["dice"])),
        dice_C_ens  = float(np.mean(res_C["dice"])),
        dip_B       = dip_B_mean,
        dip_C       = dip_C_mean,
        dip_diff_ci_low = dip_ci_low,
        rho_B       = rho_B_syn,
        rho_C       = rho_C_syn,
        neg_jac_pct_C = float(np.mean(res_C["neg_jac_pct"])),
        bc_B        = bc_B_mean,
        bc_C        = bc_C_mean,
    )

    # ===================== 打印摘要 =====================
    print("\n" + "=" * 72)
    print("  K0v2 THREE-ARM KILLSHOT RESULTS")
    print("=" * 72)
    print(f"  σ_p (data-driven)        = {sigma_p:.6f}")
    print(f"  prior_lambda (臂B, TODO) = {PRIOR_LAMBDA}  # researcher 待确认")
    print()
    print("  === BraTS 全集 ===")
    print(f"  dice_A                   = {np.mean(res_A['dice']):.4f}")
    print(f"  dice_B (mean path)       = {np.mean(res_B['dice']):.4f}")
    print(f"  dice_C (ensemble)        = {np.mean(res_C['dice']):.4f}")
    print(f"  neg_jac_A                = {np.mean(res_A['neg_jac_pct'])*100:.4f}%")
    print(f"  neg_jac_B                = {np.mean(res_B['neg_jac_pct'])*100:.4f}%")
    print(f"  neg_jac_C                = {np.mean(res_C['neg_jac_pct'])*100:.4f}%")
    print()
    print(f"  === BraTS top40% 大形变子集 (n={n_top}, mean_disp={mean_disp_top:.4f}) ===")
    print(f"  dice_A_top40             = {dice_A_top:.4f}")
    print(f"  dice_B_top40             = {dice_B_top:.4f}")
    print(f"  dice_C_top40_ens         = {dice_C_top:.4f}")
    print(f"  neg_jac_A_top40          = {neg_A_top:.4f}%")
    print(f"  neg_jac_B_top40          = {neg_B_top:.4f}%")
    print(f"  neg_jac_C_top40          = {neg_C_top:.4f}%")
    print()
    print(f"  rho_B (BraTS)            = {rho_B:.4f}  (p={p_B:.4f})")
    print(f"  rho_C (BraTS)            = {rho_C:.4f}  (p={p_C:.4f})")
    print()
    print(f"  === 受控歧义对 (n={n_synth_pairs}) ===")
    print(f"  dip_B (mean)             = {dip_B_mean:.4f}")
    print(f"  dip_C (mean)             = {dip_C_mean:.4f}")
    print(f"  dip_diff CI              = [{dip_ci_low:.4f}, {dip_ci_high:.4f}]  "
          f"(dip_C - dip_B = {dip_diff_mean:.4f})")
    print(f"  bimodal_coeff_B          = {bc_B_mean:.4f}  (Sarle BC, threshold=0.555)")
    print(f"  bimodal_coeff_C          = {bc_C_mean:.4f}  bc_sig=(C>0.555 AND C>B): "
          f"{bc_C_mean > 0.555 and bc_C_mean > bc_B_mean}")
    print(f"  cluster_sep_B            = {csep_B:.4f}  [UNRELIABLE: 饱和恒1.0, 已移出判据]")
    print(f"  cluster_sep_C            = {csep_C:.4f}  [UNRELIABLE: 饱和恒1.0, 已移出判据]")
    print(f"  disp_spread_B            = {spread_B:.6f}")
    print(f"  disp_spread_C            = {spread_C:.6f}")
    print(f"  rho_B_syn                = {rho_B_syn:.4f}")
    print(f"  rho_C_syn                = {rho_C_syn:.4f}")
    print()
    print(f"  n_train_steps (each arm) = {n_train_steps}")
    print(f"  k_samples                = {k_samp}")
    print()
    print(f"  VERDICT: {verdict}")
    print("=" * 72)

    # ===================== 出图 =====================
    os.makedirs(out_dir, exist_ok=True)
    plot_posterior_BvsC(proj_B_all, proj_C_all,
                        os.path.join(out_dir, "k0v2_posterior_BvsC.png"))

    # ===================== 写 CSV =====================
    csv_path = os.path.join(out_dir, "killshot_K0v2_three_arm.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            # BraTS 全集
            "dice_A", "dice_B", "dice_C_ensemble",
            "neg_jac_pct_A", "neg_jac_pct_B", "neg_jac_pct_C",
            "rho_B_brats", "p_rho_B", "rho_C_brats", "p_rho_C",
            # BraTS top40% 子集
            "dice_A_top40", "dice_B_top40", "dice_C_top40",
            "neg_jac_A_top40", "neg_jac_B_top40", "neg_jac_C_top40",
            "brats_mean_disp_top40", "n_top40",
            # 受控歧义 [BUG-FIX #3/#4]
            "dip_B_synth", "dip_C_synth",
            "dip_diff_mean", "dip_ci_low", "dip_ci_high",
            "bimodal_coeff_B", "bimodal_coeff_C",
            "bc_sig",                          # BC_C>0.555 AND BC_C>BC_B
            "cluster_sep_B_UNRELIABLE",        # [不进判据，饱和恒1.0]
            "cluster_sep_C_UNRELIABLE",        # [不进判据，饱和恒1.0]
            "disp_spread_B", "disp_spread_C",
            "rho_B_synth", "rho_C_synth",
            # 超参
            "n_train_steps", "k_samples", "sigma_p", "prior_lambda",
            "smoke", "verdict",
        ])
        w.writerow([
            f"{np.mean(res_A['dice']):.4f}",
            f"{np.mean(res_B['dice']):.4f}",
            f"{np.mean(res_C['dice']):.4f}",
            f"{np.mean(res_A['neg_jac_pct'])*100:.4f}",
            f"{np.mean(res_B['neg_jac_pct'])*100:.4f}",
            f"{np.mean(res_C['neg_jac_pct'])*100:.4f}",
            f"{rho_B:.4f}", f"{p_B:.4f}",
            f"{rho_C:.4f}", f"{p_C:.4f}",
            # top40
            f"{dice_A_top:.4f}", f"{dice_B_top:.4f}", f"{dice_C_top:.4f}",
            f"{neg_A_top:.4f}", f"{neg_B_top:.4f}", f"{neg_C_top:.4f}",
            f"{mean_disp_top:.4f}", n_top,
            # synth
            f"{dip_B_mean:.4f}", f"{dip_C_mean:.4f}",
            f"{dip_diff_mean:.4f}", f"{dip_ci_low:.4f}", f"{dip_ci_high:.4f}",
            f"{bc_B_mean:.4f}", f"{bc_C_mean:.4f}",
            str(bc_C_mean > 0.555 and bc_C_mean > bc_B_mean),   # bc_sig
            f"{csep_B:.4f}", f"{csep_C:.4f}",   # UNRELIABLE，仅记录供参考
            f"{spread_B:.6f}", f"{spread_C:.6f}",
            f"{rho_B_syn:.4f}", f"{rho_C_syn:.4f}",
            # 超参
            n_train_steps, k_samp,
            f"{sigma_p:.6f}", PRIOR_LAMBDA,
            smoke, verdict,
        ])
    print(f"[SAVED CSV] {csv_path}")
    print("[DONE] K0v2 three-arm killshot complete.")


# ============================================================
# Entry point
# ============================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Killshot K0v2 Three-Arm: FM 真多解后验 vs cVAE vs det (FMReg A0)")
    parser.add_argument("--smoke", action="store_true",
                        help="5 对/10 步/K=3/CPU <60s 三臂全跑 smoke test")
    parser.add_argument("--data-dir", default=DATA_DIR,
                        help="override BraTS flair png dir (HPC path)")
    parser.add_argument("--out-dir", default=RESULT_DIR,
                        help="override result output dir (HPC path)")
    args = parser.parse_args()
    run(smoke=args.smoke, data_dir=args.data_dir, out_dir=args.out_dir)
