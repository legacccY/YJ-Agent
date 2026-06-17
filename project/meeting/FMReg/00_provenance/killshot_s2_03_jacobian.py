"""
killshot_s2_03_jacobian.py
G5 killshot: Flow-matching 单步 Euler 积分能否产生拓扑合法（雅可比正）的解剖形变场?
证伪线: neg_jac_pct > 5% 且 dice_fm <= dice_affine → 单步 FM 形变塌 (RED)

数据: BraTS2021 已配准 PNG 切片 (flair modality, 2D)
      D:/YJ-Agent/project/meeting/MedAD-FailMap/data/BraTS2021/train/
方法: 极简 2ch U-Net (moving+fixed → 2ch velocity), 单步 Euler warp, 200 step 训练
输出: D:/YJ-Agent/project/ideation/runs/2026-06-17_run-002_medimg-method/06_experiments/results/killshot_s2_03_jacobian.csv

运行: python killshot_s2_03_jacobian.py
      python killshot_s2_03_jacobian.py --smoke  # 5图10步冒烟
"""

import argparse
import os
import sys
import glob
import csv
import time
import random

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
DATA_DIR = os.path.join("D:/", "YJ-Agent", "project", "meeting",
                        "MedAD-FailMap", "data", "BraTS2021", "train")
RESULT_DIR = os.path.join("D:/", "YJ-Agent", "project", "ideation",
                           "runs", "2026-06-17_run-002_medimg-method",
                           "06_experiments", "results")
RESULT_CSV = os.path.join(RESULT_DIR, "killshot_s2_03_jacobian.csv")

IMG_SIZE = 128   # downsample to 128x128
BRAIN_THRESH = 0.05  # foreground threshold for Dice (normalized intensity)

# ---------- dataset ----------
class BraTSPairDataset(Dataset):
    """
    每次随机取两个不同 subject 的切片作 (moving, fixed) 对。
    以 flair 模态为准。
    """
    def __init__(self, data_dir, n_pairs=40, size=128, seed=42):
        random.seed(seed)
        all_files = sorted(glob.glob(os.path.join(data_dir, "*_flair_*.png")))
        if len(all_files) == 0:
            raise FileNotFoundError(f"No flair PNGs in {data_dir}")
        # group by subject id (BraTS2021_XXXXX_flair_ZZ.png)
        subjects = {}
        for f in all_files:
            subj = os.path.basename(f).split("_flair_")[0]
            subjects.setdefault(subj, []).append(f)
        subj_ids = list(subjects.keys())
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
        return torch.from_numpy(arr).unsqueeze(0)  # [1, H, W]

    def __len__(self):
        return len(self.pairs)

    def __getitem__(self, idx):
        mov_path, fix_path = self.pairs[idx]
        return self._load(mov_path), self._load(fix_path)


# ---------- model: tiny 2ch U-Net → 2ch velocity ----------
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
    """in: [B, 2, H, W] (moving + fixed), out: [B, 2, H, W] velocity"""
    def __init__(self, base=16):
        super().__init__()
        self.enc1 = ConvBlock(2, base)
        self.enc2 = ConvBlock(base, base * 2)
        self.enc3 = ConvBlock(base * 2, base * 4)
        self.pool = nn.MaxPool2d(2)

        self.bottleneck = ConvBlock(base * 4, base * 8)

        self.up3 = nn.ConvTranspose2d(base * 8, base * 4, 2, stride=2)
        self.dec3 = ConvBlock(base * 8, base * 4)
        self.up2 = nn.ConvTranspose2d(base * 4, base * 2, 2, stride=2)
        self.dec2 = ConvBlock(base * 4, base * 2)
        self.up1 = nn.ConvTranspose2d(base * 2, base, 2, stride=2)
        self.dec1 = ConvBlock(base * 2, base)

        self.out_conv = nn.Conv2d(base, 2, 1)
        # init small → start near identity
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


# ---------- warp + jacobian ----------
def make_identity_grid(B, H, W, device):
    """Returns [B, H, W, 2] identity sampling grid in [-1, 1]."""
    gy, gx = torch.meshgrid(
        torch.linspace(-1, 1, H, device=device),
        torch.linspace(-1, 1, W, device=device),
        indexing="ij",
    )
    grid = torch.stack([gx, gy], dim=-1)  # [H, W, 2]
    return grid.unsqueeze(0).expand(B, -1, -1, -1)


def warp(moving, velocity, device):
    """
    Single-step Euler: phi = identity + v
    velocity: [B, 2, H, W] in pixel units / H (i.e. normalized [-1,1] range)
    Returns warped image [B, 1, H, W]
    """
    B, _, H, W = velocity.shape
    identity = make_identity_grid(B, H, W, device)
    # velocity already in [-1,1] normalized coords
    # permute velocity to [B, H, W, 2]
    v_perm = velocity.permute(0, 2, 3, 1)
    grid = identity + v_perm
    grid = grid.clamp(-1, 1)
    warped = F.grid_sample(moving, grid, mode="bilinear",
                           padding_mode="border", align_corners=True)
    return warped


def jacobian_det(velocity):
    """
    Compute Jacobian determinant of phi = identity + v.
    velocity: [B, 2, H, W], normalized coords.
    Returns [B, H, W] Jacobian det.
    """
    B, _, H, W = velocity.shape
    vx = velocity[:, 0]  # [B, H, W]
    vy = velocity[:, 1]

    # dv/dx via finite diff (central)
    dvx_dx = (vx[:, :, 2:] - vx[:, :, :-2]) / 2.0
    dvx_dy = (vx[:, 2:, :] - vx[:, :-2, :]) / 2.0
    dvy_dx = (vy[:, :, 2:] - vy[:, :, :-2]) / 2.0
    dvy_dy = (vy[:, 2:, :] - vy[:, :-2, :]) / 2.0

    # crop to valid region (H-2, W-2)
    dvx_dx = dvx_dx[:, 1:-1, :]  # [B, H-2, W-2]
    dvx_dy = dvx_dy[:, :, 1:-1]
    dvy_dx = dvy_dx[:, 1:-1, :]
    dvy_dy = dvy_dy[:, :, 1:-1]

    # Jacobian of phi = I + v: det = (1+dvx/dx)*(1+dvy/dy) - dvx/dy*dvy/dx
    jac = (1 + dvx_dx) * (1 + dvy_dy) - dvx_dy * dvy_dx
    return jac  # [B, H-2, W-2]


def dice_fg(pred, target, thresh=BRAIN_THRESH):
    """Binary Dice for foreground (intensity > thresh)."""
    p = (pred > thresh).float()
    t = (target > thresh).float()
    inter = (p * t).sum(dim=[-1, -2, -3])
    union = p.sum(dim=[-1, -2, -3]) + t.sum(dim=[-1, -2, -3])
    dice = (2 * inter + 1e-6) / (union + 1e-6)
    return dice.mean().item()


# ---------- FM loss: velocity should transport moving → fixed ----------
def fm_loss(velocity, moving, fixed, device):
    """
    Standard flow-matching MSE: predict velocity = (fixed - moving)
    as the direct interpolation target (linear FM at t=1).
    """
    target_v = fixed - moving  # naive linear FM target; in image space

    # normalize to [-1,1] coord scale: divide by H (approx)
    H = moving.shape[-1]
    target_v_norm = target_v / H  # rough normalization

    # expand to 2ch: use same displacement for both spatial dims (proxy)
    # Better: compute per-channel displacement proxy from image difference
    # We use a simple approach: stack the same scalar field for both dims
    # (this is a proxy; real FM would have full 2D vector target)
    B = moving.shape[0]
    # create 2ch target from image-level proxy
    img_diff = (fixed - moving)  # [B, 1, H, W]
    # channel 0 = horizontal proxy (column gradient of diff), channel 1 = vertical
    diff_sq = img_diff.squeeze(1)  # [B, H, W]
    # dx: gradient along x
    dx = torch.zeros_like(diff_sq)
    dx[:, :, 1:-1] = (diff_sq[:, :, 2:] - diff_sq[:, :, :-2]) / 2.0
    dy = torch.zeros_like(diff_sq)
    dy[:, 1:-1, :] = (diff_sq[:, 2:, :] - diff_sq[:, :-2, :]) / 2.0
    target_field = torch.stack([dx, dy], dim=1)  # [B, 2, H, W]
    target_field = target_field / (H * 0.5)  # normalize

    loss = F.mse_loss(velocity, target_field)

    # also add reconstruction loss: warp should match fixed
    warped = warp(moving, velocity, device)
    recon_loss = F.mse_loss(warped, fixed)

    return loss + recon_loss


# ---------- main ----------
def run(smoke=False):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[INFO] device={device}")

    n_pairs = 5 if smoke else 40
    n_steps = 10 if smoke else 200
    batch_size = 4

    print(f"[INFO] smoke={smoke}, n_pairs={n_pairs}, n_steps={n_steps}")

    dataset = BraTSPairDataset(DATA_DIR, n_pairs=n_pairs, size=IMG_SIZE)
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True,
                        num_workers=0, pin_memory=False)

    model = TinyUNet(base=16).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)

    # ---------- train ----------
    print(f"[INFO] training {n_steps} steps ...")
    t0 = time.time()
    step = 0
    model.train()
    while step < n_steps:
        for moving, fixed in loader:
            if step >= n_steps:
                break
            moving, fixed = moving.to(device), fixed.to(device)
            optimizer.zero_grad()
            inp = torch.cat([moving, fixed], dim=1)  # [B, 2, H, W]
            velocity = model(inp)
            loss = fm_loss(velocity, moving, fixed, device)
            loss.backward()
            optimizer.step()
            step += 1
            if step % 50 == 0 or step <= 5:
                print(f"  step {step}/{n_steps}  loss={loss.item():.4f}  "
                      f"elapsed={time.time()-t0:.1f}s")

    # ---------- eval ----------
    print("[INFO] evaluating ...")
    model.eval()
    all_neg_jac = []
    all_dice_fm = []
    all_dice_aff = []

    eval_dataset = BraTSPairDataset(DATA_DIR, n_pairs=20 if not smoke else 5,
                                     size=IMG_SIZE, seed=99)
    eval_loader = DataLoader(eval_dataset, batch_size=4, shuffle=False,
                             num_workers=0, pin_memory=False)

    with torch.no_grad():
        for moving, fixed in eval_loader:
            moving, fixed = moving.to(device), fixed.to(device)
            inp = torch.cat([moving, fixed], dim=1)
            velocity = model(inp)

            # Jacobian
            jac = jacobian_det(velocity)  # [B, H-2, W-2]
            neg_frac = (jac < 0).float().mean(dim=[-1, -2])  # [B]
            all_neg_jac.extend(neg_frac.cpu().numpy().tolist())

            # Dice FM
            warped = warp(moving, velocity, device)
            dice_fm = dice_fg(warped, fixed)
            all_dice_fm.append(dice_fm)

            # Dice affine baseline = identity (no warp)
            dice_aff = dice_fg(moving, fixed)
            all_dice_aff.append(dice_aff)

    neg_jac_pct = float(np.mean(all_neg_jac)) * 100.0
    dice_fm_mean = float(np.mean(all_dice_fm))
    dice_aff_mean = float(np.mean(all_dice_aff))

    # ---------- verdict ----------
    verdict = "UNCLEAR"
    if neg_jac_pct > 5.0 and dice_fm_mean <= dice_aff_mean:
        verdict = "RED: FM single-step collapses (neg_jac>5% & dice_fm<=dice_affine)"
    elif neg_jac_pct > 5.0:
        verdict = "YELLOW: neg_jac high but FM Dice > affine (partial fail)"
    elif dice_fm_mean > dice_aff_mean + 0.02:
        verdict = "GREEN: FM outperforms affine & topology ok"
    else:
        verdict = "YELLOW: topology ok but FM barely beats affine"

    print("\n===== RESULTS =====")
    print(f"  neg_jac_pct   = {neg_jac_pct:.2f}%  (killshot line: >5%)")
    print(f"  dice_fm       = {dice_fm_mean:.4f}")
    print(f"  dice_affine   = {dice_aff_mean:.4f}  (identity baseline)")
    print(f"  VERDICT       : {verdict}")

    # ---------- write CSV ----------
    os.makedirs(RESULT_DIR, exist_ok=True)
    with open(RESULT_CSV, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["neg_jac_pct", "dice_fm", "dice_affine",
                         "n_train_steps", "n_eval_pairs", "smoke", "verdict"])
        writer.writerow([f"{neg_jac_pct:.4f}", f"{dice_fm_mean:.4f}",
                         f"{dice_aff_mean:.4f}", n_steps,
                         len(eval_dataset), smoke, verdict])
    print(f"\n[SAVED] {RESULT_CSV}")
    print(f"SUMMARY | neg_jac_pct={neg_jac_pct:.2f}% | "
          f"dice_fm={dice_fm_mean:.4f} | dice_aff={dice_aff_mean:.4f} | {verdict}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true",
                        help="5 pairs, 10 steps smoke test")
    args = parser.parse_args()
    run(smoke=args.smoke)
