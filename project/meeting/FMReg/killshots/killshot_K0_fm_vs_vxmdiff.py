"""
killshot_K0_fm_vs_vxmdiff.py
FMReg A0 立项闸 killshot: VoxelMorph-diff (SVF+S&S) vs FM-in-SVF 增益对照

证伪线:
  GREEN = FM 在 Dice 不输 VoxelMorph-diff + 后验不确定性 ρ 显著>0 → FM 有不可替换增益 → headline 候选①
  RED   = FM 对 VoxelMorph-diff 无可测增益 (ρ 不显著 & Dice 不优) → 退化坐实 → 报拍板降级
  YELLOW= 中间态

模型 A = VoxelMorph-diff: TinyUNet → SVF v → S&S 积分 (int_steps=7) → φ → warp
模型 B = FM-in-SVF: TinyUNetFM(moving+fixed+psi_t+t) → FM velocity u → Euler 积分生成 SVF ψ̂ → 同一 S&S → φ → warp
         FM 训练: t~U(0,1), ψ_t=(1-t)·ψ_0+t·ψ_1, 预测 u=(ψ_1-ψ_0); ψ_1 用 VoxelMorph-diff teacher SVF

指标:
  dice_vxmdiff, dice_fm
  neg_jac_pct_vxmdiff, neg_jac_pct_fm
  fm_uncertainty_corr  (K 次采样形变方差 与 配准误差的 Pearson ρ, 纯 numpy 实现)
  fm_steps_N1/N2/N4/N8 (少步扫描 Dice)
  verdict

数据: D:/YJ-Agent/project/meeting/MedAD-FailMap/data/BraTS2021/train/*_flair_*.png
输出: D:/YJ-Agent/project/meeting/FMReg/killshots/results/killshot_K0_fm_vs_vxmdiff.csv

运行:
  python killshot_K0_fm_vs_vxmdiff.py            # full run (~2000 steps per model)
  python killshot_K0_fm_vs_vxmdiff.py --smoke    # 5 pairs, 10 steps 冒烟 (cpu ok)

Windows 规范: num_workers=0, pin_memory=False, spawn-safe, 路径 forward slash
              PLCC/SRCC 纯 numpy (no scipy, 避免 OMP Error #15)
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

# ---------- dependency check ----------
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

# ---------- paths ----------
DATA_DIR   = "D:/YJ-Agent/project/meeting/MedAD-FailMap/data/BraTS2021/train"
RESULT_DIR = "D:/YJ-Agent/project/meeting/FMReg/killshots/results"
RESULT_CSV = os.path.join(RESULT_DIR, "killshot_K0_fm_vs_vxmdiff.csv")

IMG_SIZE    = 128
BRAIN_THRESH = 0.05   # foreground threshold for Dice

# VoxelMorph-diff hyperparams
# S&S int_steps=7: from voxelmorph/py/utils.py default int_steps=7 (Arsigny 2006 DARTEL standard)
SS_INT_STEPS = 7
# λ_smooth=0.01 for MSE; NCC used here with λ=1.0 (VoxelMorph official: ncc λ=1.0)
# TODO: 未找到官方 VoxelMorph-diff 2D BraTS 脑配准明确 λ 值；以下参考 voxelmorph paper Table 1 ncc λ=1.0
LAMBDA_SMOOTH = 1.0
# TODO: 未找到官方 VoxelMorph-diff 2D 脑配准 lr；以下用常见实践 1e-4，需 researcher 确认
LR_VXM = 1e-4
LR_FM  = 1e-4   # 与 VoxelMorph-diff 同 lr 保证公平对照

K_SAMPLES            = 8    # FM 后验采样次数
FM_EULER_STEPS_LIST  = [1, 2, 4, 8]  # 少步扫描


# ============================================================
# Dataset
# ============================================================
class BraTSPairDataset(Dataset):
    """
    随机取两个不同 subject 的 flair 切片作 (moving, fixed) inter-subject 对。
    与 killshot_s2_03_jacobian.py 同风格。
    """
    def __init__(self, data_dir, n_pairs=200, size=128, seed=42):
        random.seed(seed)
        all_files = sorted(glob.glob(os.path.join(data_dir, "*_flair_*.png")))
        if len(all_files) == 0:
            raise FileNotFoundError(f"[ERROR] No flair PNGs found in {data_dir}")
        subjects = {}
        for f in all_files:
            subj = os.path.basename(f).split("_flair_")[0]
            subjects.setdefault(subj, []).append(f)
        subj_ids = list(subjects.keys())
        if len(subj_ids) < 2:
            raise ValueError("[ERROR] Need >=2 subjects for inter-subject pairs")
        self.pairs = []
        for _ in range(n_pairs):
            s_mov, s_fix = random.sample(subj_ids, 2)
            mov = random.choice(subjects[s_mov])
            fix = random.choice(subjects[s_fix])
            self.pairs.append((mov, fix))
        self.size = size

    def _load(self, path):
        img = Image.open(path).convert("L")
        img = img.resize((self.size, self.size), Image.BILINEAR)
        arr = np.array(img, dtype=np.float32) / 255.0
        return torch.from_numpy(arr).unsqueeze(0)   # [1, H, W]

    def __len__(self):
        return len(self.pairs)

    def __getitem__(self, idx):
        mov_path, fix_path = self.pairs[idx]
        return self._load(mov_path), self._load(fix_path)


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


class TinyUNet(nn.Module):
    """
    Model A (VoxelMorph-diff backbone):
    in=[B, 2, H, W] (moving+fixed) → out=[B, 2, H, W] stationary velocity field (SVF).
    base=16 channels.
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
        nn.init.normal_(self.out_conv.weight, std=1e-4)
        nn.init.zeros_(self.out_conv.bias)

    def forward(self, x):
        e1 = self.enc1(x)
        e2 = self.enc2(self.pool(e1))
        e3 = self.enc3(self.pool(e2))
        b  = self.bottleneck(self.pool(e3))
        d3 = self.dec3(torch.cat([self.up3(b), e3], dim=1))
        d2 = self.dec2(torch.cat([self.up2(d3), e2], dim=1))
        d1 = self.dec1(torch.cat([self.up1(d2), e1], dim=1))
        return self.out_conv(d1)


class TinyUNetFM(nn.Module):
    """
    Model B (FM-in-SVF backbone):
    in=[B, 5, H, W] = moving(1)+fixed(1)+psi_t(2)+time_map(1)
    out=[B, 2, H, W] FM velocity u(psi_t, t).
    Same architecture as TinyUNet, in_ch=5.
    """
    def __init__(self, base=16):
        super().__init__()
        in_ch = 5  # moving(1) + fixed(1) + svf_t(2) + time_broadcast(1)
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
        nn.init.normal_(self.out_conv.weight, std=1e-4)
        nn.init.zeros_(self.out_conv.bias)

    def forward(self, moving, fixed, psi_t, t):
        """
        moving, fixed : [B, 1, H, W]
        psi_t         : [B, 2, H, W]  interpolant SVF at time t
        t             : [B] scalar time in [0, 1]
        returns u     : [B, 2, H, W]  FM velocity
        """
        B, _, H, W = moving.shape
        t_map = t.view(B, 1, 1, 1).expand(B, 1, H, W)
        x = torch.cat([moving, fixed, psi_t, t_map], dim=1)  # [B, 5, H, W]
        e1 = self.enc1(x)
        e2 = self.enc2(self.pool(e1))
        e3 = self.enc3(self.pool(e2))
        b  = self.bottleneck(self.pool(e3))
        d3 = self.dec3(torch.cat([self.up3(b), e3], dim=1))
        d2 = self.dec2(torch.cat([self.up2(d3), e2], dim=1))
        d1 = self.dec1(torch.cat([self.up1(d2), e1], dim=1))
        return self.out_conv(d1)


# ============================================================
# Spatial transforms
# ============================================================
def make_identity_grid(B, H, W, device):
    """Returns [B, H, W, 2] identity sampling grid in [-1, 1]."""
    gy, gx = torch.meshgrid(
        torch.linspace(-1, 1, H, device=device),
        torch.linspace(-1, 1, W, device=device),
        indexing="ij",
    )
    grid = torch.stack([gx, gy], dim=-1)   # [H, W, 2]
    return grid.unsqueeze(0).expand(B, -1, -1, -1)


def compose_displacement(phi, delta):
    """
    Composition: phi_new(x) = phi(x + delta(x)).
    Both phi, delta: [B, H, W, 2] displacement in [-1, 1] normalized coords.
    Used in scaling-and-squaring squaring step.
    """
    B, H, W, _ = phi.shape
    identity = make_identity_grid(B, H, W, phi.device)
    coords = (identity + delta).clamp(-1, 1)   # [B, H, W, 2]
    phi_img = phi.permute(0, 3, 1, 2)           # [B, 2, H, W]
    sampled = F.grid_sample(phi_img, coords, mode="bilinear",
                             padding_mode="border", align_corners=True)
    return sampled.permute(0, 2, 3, 1)          # [B, H, W, 2]


def scaling_and_squaring(svf, int_steps=SS_INT_STEPS):
    """
    Scaling-and-squaring integration: φ = exp(v).
    Algorithm: v_0 = v / 2^T; φ ← φ∘φ  for T iterations.
    Reference: Arsigny et al. 2006 (DARTEL); VoxelMorph vecint default int_steps=7.
    svf: [B, 2, H, W] stationary velocity field, values in normalized [-1,1] coords.
    Returns φ: [B, H, W, 2] displacement field.
    """
    B, _, H, W = svf.shape
    phi = svf / (2.0 ** int_steps)         # scale: v_0
    phi = phi.permute(0, 2, 3, 1)          # [B, H, W, 2]
    for _ in range(int_steps):
        phi = phi + compose_displacement(phi, phi)   # squaring: φ ← φ∘φ
    return phi   # [B, H, W, 2]


def warp_by_disp(moving, disp):
    """
    Warp image by displacement field.
    moving : [B, 1, H, W]
    disp   : [B, H, W, 2] displacement in [-1, 1]
    Returns warped [B, 1, H, W].
    """
    B, _, H, W = moving.shape
    identity = make_identity_grid(B, H, W, moving.device)
    grid = (identity + disp).clamp(-1, 1)
    return F.grid_sample(moving, grid, mode="bilinear",
                         padding_mode="border", align_corners=True)


def jacobian_det_disp(disp):
    """
    Jacobian determinant of φ = identity + disp.
    disp: [B, H, W, 2].
    Returns [B, H-2, W-2] (valid interior region after finite diff).
    """
    dx = disp[:, :, :, 0]   # [B, H, W]
    dy = disp[:, :, :, 1]

    # central finite difference
    ddx_dx = (dx[:, :, 2:] - dx[:, :, :-2]) / 2.0   # [B, H, W-2]
    ddx_dy = (dx[:, 2:, :] - dx[:, :-2, :]) / 2.0   # [B, H-2, W]
    ddy_dx = (dy[:, :, 2:] - dy[:, :, :-2]) / 2.0
    ddy_dy = (dy[:, 2:, :] - dy[:, :-2, :]) / 2.0

    # crop to valid interior [H-2, W-2]
    ddx_dx = ddx_dx[:, 1:-1, :]   # [B, H-2, W-2]
    ddx_dy = ddx_dy[:, :, 1:-1]
    ddy_dx = ddy_dx[:, 1:-1, :]
    ddy_dy = ddy_dy[:, :, 1:-1]

    # det(J(φ)) = (1+ddx/dx)*(1+ddy/dy) - ddx/dy*ddy/dx
    jac = (1 + ddx_dx) * (1 + ddy_dy) - ddx_dy * ddy_dx
    return jac   # [B, H-2, W-2]


# ============================================================
# Losses
# ============================================================
def ncc_loss(pred, target, win=9):
    """
    Local NCC loss (returns negative NCC for minimization).
    pred, target: [B, 1, H, W].
    TODO: 未找到官方 VoxelMorph-diff 2D 脑配准 NCC window size;
          以下 win=9 参考 voxelmorph/py/losses.py NCC class default win=[9,9]
    """
    B, C, H, W = pred.shape
    pad = win // 2
    p = F.unfold(pred,   kernel_size=win, padding=pad)  # [B, C*win^2, L]
    t = F.unfold(target, kernel_size=win, padding=pad)
    p_mean = p.mean(dim=1, keepdim=True)
    t_mean = t.mean(dim=1, keepdim=True)
    p_c = p - p_mean
    t_c = t - t_mean
    num   = (p_c * t_c).sum(dim=1)
    denom = torch.sqrt((p_c ** 2).sum(dim=1) * (t_c ** 2).sum(dim=1) + 1e-8)
    ncc   = (num / denom).mean()
    return -ncc   # negative for minimization


def smooth_loss(svf):
    """Spatial smoothness regularization ||∇v||^2. svf: [B, 2, H, W]."""
    dx = svf[:, :, :, 1:] - svf[:, :, :, :-1]
    dy = svf[:, :, 1:, :] - svf[:, :, :-1, :]
    return (dx ** 2).mean() + (dy ** 2).mean()


def vxmdiff_loss(warped, fixed, svf, lam=LAMBDA_SMOOTH):
    """VoxelMorph-diff loss: NCC(warped, fixed) + λ·||∇v||^2."""
    return ncc_loss(warped, fixed) + lam * smooth_loss(svf)


def fm_loss_svf(u_pred, u_target, warped, fixed):
    """
    FM-in-SVF training loss:
      MSE(u_pred, u_target)  -- conditional flow matching objective
    + NCC(warped, fixed)     -- reconstruction consistency (optional but helps)
    Note: smoothness reg on u not standard in FM (omitted per FM theory).
    """
    fm_mse = F.mse_loss(u_pred, u_target)
    recon  = ncc_loss(warped, fixed)
    return fm_mse + recon


# ============================================================
# Metrics — pure numpy (no scipy, avoid OMP Error #15 on Windows)
# ============================================================
def pearson_r_numpy(x, y):
    """
    Pearson ρ + two-sided p-value approximation via normal approx.
    Pure numpy/math, no scipy.
    x, y: 1D array-like.
    Returns (r, p_approx).
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    n = len(x)
    if n < 3:
        return 0.0, 1.0
    xm = x - x.mean()
    ym = y - y.mean()
    num   = (xm * ym).sum()
    denom = math.sqrt((xm ** 2).sum() * (ym ** 2).sum() + 1e-12)
    r = float(np.clip(num / denom, -1.0, 1.0))
    # t-statistic
    t_stat = r * math.sqrt(n - 2) / (math.sqrt(max(1 - r ** 2, 1e-12)))
    # two-sided p via complementary error function (normal approx, conservative)
    z = abs(t_stat) / math.sqrt(2.0)
    p_approx = math.erfc(z)
    return r, float(p_approx)


def dice_fg_numpy(warped_np, fixed_np, thresh=BRAIN_THRESH):
    """
    Per-sample binary Dice for foreground.
    warped_np, fixed_np: [B, 1, H, W] or [B, H, W] numpy arrays.
    Returns list of per-sample Dice values.
    """
    if warped_np.ndim == 4:
        warped_np = warped_np[:, 0]
        fixed_np  = fixed_np[:, 0]
    dices = []
    for w, f in zip(warped_np, fixed_np):
        p = (w > thresh).astype(np.float32)
        t = (f > thresh).astype(np.float32)
        inter = (p * t).sum()
        union = p.sum() + t.sum()
        dices.append(float((2 * inter + 1e-6) / (union + 1e-6)))
    return dices


# ============================================================
# FM inference: Euler integration in SVF space
# ============================================================
def fm_infer_svf(fm_model, moving, fixed, n_steps, device, noise_seed=None):
    """
    Euler integration of FM model to generate SVF ψ̂.
    ψ_0 ~ N(0, 0.01) (small noise prior, plausible zero-displacement prior)
    ψ_{t+dt} = ψ_t + dt * u_theta(ψ_t, t, moving, fixed)
    Returns ψ_1 = generated SVF [B, 2, H, W].
    """
    B, _, H, W = moving.shape
    if noise_seed is not None:
        gen = torch.Generator(device=device)
        gen.manual_seed(noise_seed)
        psi = torch.randn(B, 2, H, W, device=device, generator=gen) * 0.01
    else:
        psi = torch.randn(B, 2, H, W, device=device) * 0.01
    dt = 1.0 / n_steps
    fm_model.eval()
    with torch.no_grad():
        for i in range(n_steps):
            t_val = i * dt
            t_tensor = torch.full((B,), t_val, device=device, dtype=torch.float32)
            u = fm_model(moving, fixed, psi, t_tensor)
            psi = psi + dt * u
    return psi   # [B, 2, H, W]


# ============================================================
# Training: VoxelMorph-diff (Model A)
# ============================================================
def train_vxmdiff(loader, n_steps, device):
    print("[INFO] === Training Model A: VoxelMorph-diff (SVF + S&S, int_steps=7) ===")
    model = TinyUNet(in_ch=2, base=16).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=LR_VXM)
    model.train()
    t0 = time.time()
    step = 0
    log_every = max(1, n_steps // 10)
    while step < n_steps:
        for moving, fixed in loader:
            if step >= n_steps:
                break
            moving, fixed = moving.to(device), fixed.to(device)
            optimizer.zero_grad()
            inp = torch.cat([moving, fixed], dim=1)      # [B, 2, H, W]
            svf = model(inp)                              # [B, 2, H, W]
            disp = scaling_and_squaring(svf, SS_INT_STEPS)  # [B, H, W, 2]
            warped = warp_by_disp(moving, disp)           # [B, 1, H, W]
            loss = vxmdiff_loss(warped, fixed, svf)
            loss.backward()
            optimizer.step()
            step += 1
            if step % log_every == 0 or step <= 3:
                print(f"  [VXM-diff] step {step}/{n_steps}  loss={loss.item():.5f}  "
                      f"t={time.time()-t0:.1f}s")
    print(f"[INFO] VoxelMorph-diff training done ({time.time()-t0:.1f}s)")
    return model


# ============================================================
# Training: FM-in-SVF (Model B)
# Teacher SVF from frozen VoxelMorph-diff = ψ_1 target
# ============================================================
def train_fm_svf(loader, vxm_model, n_steps, device):
    """
    Conditional FM training:
      ψ_1 = teacher SVF from frozen VoxelMorph-diff
      ψ_0 = N(0, 0.01^2) noise
      t ~ U(0,1)
      ψ_t = (1-t)*ψ_0 + t*ψ_1  (linear interpolant = straight ODE path)
      u_target = ψ_1 - ψ_0       (constant-speed FM velocity)
      loss = MSE(u_pred, u_target) + NCC(warp(moving, S&S(ψ_t)), fixed)
    Reference: Lipman et al. 2022 "Flow Matching for Generative Modeling"
    """
    print("[INFO] === Training Model B: FM-in-SVF (teacher=VoxelMorph-diff) ===")
    fm_model = TinyUNetFM(base=16).to(device)
    optimizer = torch.optim.Adam(fm_model.parameters(), lr=LR_FM)
    vxm_model.eval()   # teacher frozen
    fm_model.train()
    t0 = time.time()
    step = 0
    log_every = max(1, n_steps // 10)
    while step < n_steps:
        for moving, fixed in loader:
            if step >= n_steps:
                break
            moving, fixed = moving.to(device), fixed.to(device)
            B = moving.shape[0]

            # teacher SVF ψ_1 (no grad)
            with torch.no_grad():
                inp = torch.cat([moving, fixed], dim=1)
                psi_1 = vxm_model(inp).detach()   # [B, 2, H, W]

            # ψ_0 ~ N(0, 0.01)
            psi_0 = torch.randn_like(psi_1) * 0.01

            # t ~ U(0,1) per sample
            t_samp = torch.rand(B, device=device)      # [B]
            t_view = t_samp.view(B, 1, 1, 1)

            # interpolant ψ_t = (1-t)*ψ_0 + t*ψ_1
            psi_t = (1 - t_view) * psi_0 + t_view * psi_1

            # target FM velocity (straight-line ODE)
            u_target = psi_1 - psi_0   # [B, 2, H, W]

            optimizer.zero_grad()
            u_pred = fm_model(moving, fixed, psi_t, t_samp)   # [B, 2, H, W]

            # reconstruction term: warp moving by S&S(psi_t)
            with torch.no_grad():
                disp_t = scaling_and_squaring(psi_t, SS_INT_STEPS)
            warped_t = warp_by_disp(moving, disp_t)

            loss = fm_loss_svf(u_pred, u_target, warped_t, fixed)
            loss.backward()
            optimizer.step()
            step += 1
            if step % log_every == 0 or step <= 3:
                print(f"  [FM-SVF]   step {step}/{n_steps}  loss={loss.item():.5f}  "
                      f"t={time.time()-t0:.1f}s")
    print(f"[INFO] FM-in-SVF training done ({time.time()-t0:.1f}s)")
    return fm_model


# ============================================================
# Evaluation: VoxelMorph-diff
# ============================================================
def eval_vxmdiff(vxm_model, eval_loader, device):
    """
    Returns dict:
      dice: list[float] per sample
      neg_jac_pct: list[float] per sample (fraction of neg Jacobian pixels)
    """
    vxm_model.eval()
    dices, neg_jacs = [], []
    with torch.no_grad():
        for moving, fixed in eval_loader:
            moving, fixed = moving.to(device), fixed.to(device)
            inp   = torch.cat([moving, fixed], dim=1)
            svf   = vxm_model(inp)
            disp  = scaling_and_squaring(svf, SS_INT_STEPS)
            warped = warp_by_disp(moving, disp)

            dices.extend(dice_fg_numpy(warped.cpu().numpy(), fixed.cpu().numpy()))

            jac = jacobian_det_disp(disp)                  # [B, H-2, W-2]
            neg_pct = (jac < 0).float().mean(dim=[-1, -2]).cpu().numpy()  # [B]
            neg_jacs.extend(neg_pct.tolist())

    return {"dice": dices, "neg_jac_pct": neg_jacs}


# ============================================================
# Evaluation: FM-in-SVF
# ============================================================
def eval_fm(fm_model, eval_loader, device, n_euler_steps=4, k_samples=K_SAMPLES):
    """
    FM-in-SVF eval.
    Returns dict:
      dice: list[float] per sample (main eval, n_euler_steps)
      neg_jac_pct: list[float] per sample
      uncertainty_vars: list[float] per sample — mean pixel-wise SVF variance across K samples
      recon_errs: list[float] per sample — mean |warped - fixed|
      step_dices: dict {n_steps: mean_dice}  (steps sweep)
    """
    fm_model.eval()
    dices_main, neg_jacs_main = [], []
    uncertainty_vars = []
    recon_errs = []
    step_dices = {s: [] for s in FM_EULER_STEPS_LIST}

    with torch.no_grad():
        for moving, fixed in eval_loader:
            moving, fixed = moving.to(device), fixed.to(device)
            f_np = fixed.cpu().numpy()

            # --- main prediction (n_euler_steps) ---
            psi_main = fm_infer_svf(fm_model, moving, fixed,
                                    n_euler_steps, device, noise_seed=0)
            disp_main = scaling_and_squaring(psi_main, SS_INT_STEPS)
            warped_main = warp_by_disp(moving, disp_main)
            w_np = warped_main.cpu().numpy()

            dices_main.extend(dice_fg_numpy(w_np, f_np))

            jac = jacobian_det_disp(disp_main)
            neg_pct = (jac < 0).float().mean(dim=[-1, -2]).cpu().numpy()
            neg_jacs_main.extend(neg_pct.tolist())

            recon_err_batch = np.abs(w_np - f_np).mean(axis=(1, 2, 3))  # [B]
            recon_errs.extend(recon_err_batch.tolist())

            # --- K posterior samples → uncertainty ---
            psi_samples = []
            for k in range(k_samples):
                psi_k = fm_infer_svf(fm_model, moving, fixed,
                                     n_euler_steps, device, noise_seed=k)
                psi_samples.append(psi_k.cpu().numpy())   # [B, 2, H, W]
            psi_stack = np.stack(psi_samples, axis=0)     # [K, B, 2, H, W]
            var_per_sample = psi_stack.var(axis=0).mean(axis=(1, 2, 3))  # [B]
            uncertainty_vars.extend(var_per_sample.tolist())

            # --- steps sweep ---
            for s in FM_EULER_STEPS_LIST:
                psi_s = fm_infer_svf(fm_model, moving, fixed, s, device, noise_seed=0)
                disp_s = scaling_and_squaring(psi_s, SS_INT_STEPS)
                warped_s = warp_by_disp(moving, disp_s)
                step_dices[s].extend(dice_fg_numpy(warped_s.cpu().numpy(), f_np))

    return {
        "dice": dices_main,
        "neg_jac_pct": neg_jacs_main,
        "uncertainty_vars": uncertainty_vars,
        "recon_errs": recon_errs,
        "step_dices": {s: float(np.mean(v)) for s, v in step_dices.items()},
    }


# ============================================================
# Verdict
# ============================================================
def compute_verdict(dice_vxm, dice_fm, neg_vxm, neg_fm, rho, p_rho):
    """
    GREEN  = FM Dice not worse (within 1%) AND ρ>0 AND p<0.05
    RED    = FM Dice worse by >1% AND (ρ<=0 OR p>=0.05)
    YELLOW = mixed
    """
    dice_ok  = dice_fm >= dice_vxm - 0.01
    post_sig = (rho > 0.0 and p_rho < 0.05)

    if dice_ok and post_sig:
        return ("GREEN: FM Dice not worse than VoxelMorph-diff + posterior uncertainty "
                "calibrated (rho>0, p<0.05) → FM has irreplaceable generative benefit "
                "→ headline candidate① proceed to Gate1")
    elif (not dice_ok) and (not post_sig):
        return ("RED: FM Dice worse than VoxelMorph-diff AND posterior rho not significant "
                "(rho<=0 or p>=0.05) → FM-in-SVF degrades to 'VoxelMorph-diff with "
                "different sampler' → headline NOT established, report for downgrade/redirect")
    elif dice_ok and (not post_sig):
        return ("YELLOW: FM Dice ok but posterior uncertainty not significant (p>=0.05) "
                "→ partial evidence; posterior may need more training steps or larger eval")
    else:
        return ("YELLOW: FM Dice slightly worse but posterior rho significant "
                "→ uncertainty calibration present but accuracy gap needs investigation")


# ============================================================
# Main
# ============================================================
def run(smoke=False):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[INFO] device={device}  smoke={smoke}")

    n_train_pairs  = 5   if smoke else 400
    n_train_steps  = 10  if smoke else 2000
    n_eval_pairs   = 5   if smoke else 100
    batch_size     = 4
    k_samp         = 3   if smoke else K_SAMPLES
    euler_eval     = 4

    print(f"[INFO] train_steps={n_train_steps}  eval_pairs={n_eval_pairs}  "
          f"k_samples={k_samp}  euler_eval={euler_eval}")

    # datasets
    train_ds = BraTSPairDataset(DATA_DIR, n_pairs=n_train_pairs, size=IMG_SIZE, seed=42)
    train_dl = DataLoader(train_ds, batch_size=batch_size, shuffle=True,
                          num_workers=0, pin_memory=False)

    eval_ds  = BraTSPairDataset(DATA_DIR, n_pairs=n_eval_pairs, size=IMG_SIZE, seed=99)
    eval_dl  = DataLoader(eval_ds, batch_size=batch_size, shuffle=False,
                          num_workers=0, pin_memory=False)

    # Phase 1: train VoxelMorph-diff
    vxm_model = train_vxmdiff(train_dl, n_train_steps, device)

    # Phase 2: train FM-in-SVF (teacher=vxm_model)
    fm_model = train_fm_svf(train_dl, vxm_model, n_train_steps, device)

    # Phase 3: eval
    print("[INFO] === Evaluating VoxelMorph-diff ===")
    vxm_res = eval_vxmdiff(vxm_model, eval_dl, device)

    print("[INFO] === Evaluating FM-in-SVF ===")
    fm_res  = eval_fm(fm_model, eval_dl, device,
                      n_euler_steps=euler_eval, k_samples=k_samp)

    # aggregate metrics
    dice_vxm = float(np.mean(vxm_res["dice"]))
    dice_fm  = float(np.mean(fm_res["dice"]))
    neg_vxm  = float(np.mean(vxm_res["neg_jac_pct"])) * 100.0
    neg_fm   = float(np.mean(fm_res["neg_jac_pct"]))  * 100.0

    # Pearson ρ: FM uncertainty_var vs recon_err — FM main evidence
    rho, p_rho = pearson_r_numpy(fm_res["uncertainty_vars"], fm_res["recon_errs"])

    step_dices = fm_res["step_dices"]
    verdict    = compute_verdict(dice_vxm, dice_fm, neg_vxm, neg_fm, rho, p_rho)

    # print summary
    print("\n" + "=" * 70)
    print("  KILLSHOT K0 RESULTS: VoxelMorph-diff vs FM-in-SVF")
    print("=" * 70)
    print(f"  dice_vxmdiff          = {dice_vxm:.4f}")
    print(f"  dice_fm (N={euler_eval})       = {dice_fm:.4f}")
    print(f"  neg_jac_pct_vxmdiff   = {neg_vxm:.4f}%")
    print(f"  neg_jac_pct_fm        = {neg_fm:.4f}%")
    print(f"  fm_uncertainty_corr ρ = {rho:.4f}  (p_approx={p_rho:.4f})")
    print(f"  fm_steps_dice N=1     = {step_dices.get(1, 'NA')}")
    print(f"  fm_steps_dice N=2     = {step_dices.get(2, 'NA')}")
    print(f"  fm_steps_dice N=4     = {step_dices.get(4, 'NA')}")
    print(f"  fm_steps_dice N=8     = {step_dices.get(8, 'NA')}")
    print(f"  n_train_steps (each)  = {n_train_steps}")
    print(f"  n_eval_pairs          = {n_eval_pairs}")
    print(f"  k_samples             = {k_samp}")
    print(f"  VERDICT: {verdict}")
    print("=" * 70)

    # write CSV
    os.makedirs(RESULT_DIR, exist_ok=True)
    with open(RESULT_CSV, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "dice_vxmdiff", "dice_fm",
            "neg_jac_pct_vxmdiff", "neg_jac_pct_fm",
            "fm_uncertainty_corr", "fm_uncert_p",
            "fm_steps_N1", "fm_steps_N2", "fm_steps_N4", "fm_steps_N8",
            "n_train_steps", "n_eval_pairs", "k_samples",
            "ss_int_steps", "euler_steps_eval",
            "smoke", "verdict",
        ])
        w.writerow([
            f"{dice_vxm:.4f}", f"{dice_fm:.4f}",
            f"{neg_vxm:.4f}", f"{neg_fm:.4f}",
            f"{rho:.4f}", f"{p_rho:.4f}",
            f"{step_dices.get(1, 'NA'):.4f}" if isinstance(step_dices.get(1), float) else "NA",
            f"{step_dices.get(2, 'NA'):.4f}" if isinstance(step_dices.get(2), float) else "NA",
            f"{step_dices.get(4, 'NA'):.4f}" if isinstance(step_dices.get(4), float) else "NA",
            f"{step_dices.get(8, 'NA'):.4f}" if isinstance(step_dices.get(8), float) else "NA",
            n_train_steps, n_eval_pairs, k_samp,
            SS_INT_STEPS, euler_eval,
            smoke, verdict,
        ])
    print(f"\n[SAVED] {RESULT_CSV}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Killshot K0: VoxelMorph-diff vs FM-in-SVF 增益对照 (FMReg A0)")
    parser.add_argument("--smoke", action="store_true",
                        help="5 pairs, 10 steps smoke test (cpu ok, ~30s)")
    parser.add_argument("--data-dir", default=DATA_DIR,
                        help="override BraTS flair png dir (HPC path)")
    parser.add_argument("--out-dir", default=RESULT_DIR,
                        help="override result csv output dir (HPC path)")
    args = parser.parse_args()
    # allow HPC paths to override Windows defaults
    DATA_DIR   = args.data_dir
    RESULT_DIR = args.out_dir
    RESULT_CSV = os.path.join(RESULT_DIR, "killshot_K0_fm_vs_vxmdiff.csv")
    run(smoke=args.smoke)
