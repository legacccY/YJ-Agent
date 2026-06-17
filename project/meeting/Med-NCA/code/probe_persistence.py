"""probe_persistence.py
Kill-shot probe: 验证 2D NCA 能否在正常胸片上学会非平凡的图像修复/保持。

Gate 1 / Direction B / Med-NCA NCA-JEPA project
不启动正式训练，写完交主线跑。

两个非退化 mode（恒等 NCA 在两个 mode 都必须失败）：
- mode=damage  : seed=原图，随机矩形损伤后跑 T2 步，loss=MSE(输出,原图)
                 恒等 NCA 无法填补损伤 -> loss 大 -> 真测试
- mode=reconstruct: seed=16^2 bilinear 糊图 resize 回 resolution^2，loss=MSE(输出,原图)
                 恒等 NCA 输出仍糊 -> loss 大 -> 真测试

两 mode 共同：
- forward 全程禁止把可见通道重写回真图（这是退化根因，已删除）
- sample pool 防发散、随机步数、state.json 实时写（含 mode 字段）
- PSNR/SSIM（纯 numpy）、发散早停、每 25ep 对比图 [seed|输出|原图]
- converged 判据 val_psnr >= psnr_converge（默认 25 dB）

Windows 规范：num_workers=0, pin_memory=False, OMP=1, 绝对路径, 纯 numpy 指标
"""

from __future__ import annotations

import json
import os
import pathlib
import random
import time

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import yaml

# Windows OMP 设置（必须在 torch 导入后立即设）
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

from PIL import Image
from torch.utils.data import DataLoader, Dataset


# ==============================================================================
# 1. Dataset
# ==============================================================================

class NIHNormalDataset(Dataset):
    """NIH CXR-14 No-Finding 子集，返回 float32 [0,1] 灰度图 (H, W, 1)。

    channel-last 以配合 NCA (B, H, W, C) 约定。
    """

    def __init__(
        self,
        img_dir: str,
        csv_path: str,
        resolution: int,
        n_normal: int,
        seed: int,
        indices: list | None = None,
    ) -> None:
        import csv as csv_mod

        self.img_dir = pathlib.Path(img_dir)
        self.resolution = resolution

        # 读 CSV，筛 No Finding
        all_normal: list[str] = []
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv_mod.DictReader(f)
            for row in reader:
                if row["Finding Labels"].strip() == "No Finding":
                    img_path = self.img_dir / row["Image Index"].strip()
                    if img_path.exists():
                        all_normal.append(row["Image Index"].strip())

        # 随机取 n_normal 张
        rng = random.Random(seed)
        rng.shuffle(all_normal)
        selected = all_normal[:n_normal]

        if indices is not None:
            self.files = [selected[i] for i in indices]
        else:
            self.files = selected

    def __len__(self) -> int:
        return len(self.files)

    def __getitem__(self, idx: int) -> torch.Tensor:
        img_path = self.img_dir / self.files[idx]
        img = Image.open(str(img_path)).convert("L")
        img = img.resize((self.resolution, self.resolution), Image.BILINEAR)
        arr = np.array(img, dtype=np.float32) / 255.0  # (H, W)
        arr = arr[:, :, np.newaxis]                      # (H, W, 1)
        return torch.from_numpy(arr)                      # FloatTensor (H, W, 1)


# ==============================================================================
# 2. NCA Model
# ==============================================================================

class PersistenceNCA(nn.Module):
    """2D NCA：Sobel 感知 + 1x1 conv MLP + stochastic mask。

    照抄官方 BasicNCA 逻辑（M3D-NCA-official/src/models/Model_BasicNCA.py）。
    优化：Sobel kernel 在 __init__ 里预建为 register_buffer，
    消除每步 numpy 重建 + .to(device) 传输（数学完全等价）。

    layout: (B, H, W, C)  channel-last（与官方一致）
    """

    def __init__(
        self,
        channel_n: int,
        fire_rate: float,
        device: torch.device,
        hidden_size: int = 128,
        input_channels: int = 1,
    ) -> None:
        super().__init__()
        self.channel_n = channel_n
        self.input_channels = input_channels
        self.fire_rate = fire_rate
        self.device = device

        # 官方 MLP：channel_n*3 -> hidden -> channel_n
        self.fc0 = nn.Linear(channel_n * 3, hidden_size)
        self.fc1 = nn.Linear(hidden_size, channel_n, bias=False)
        with torch.no_grad():
            self.fc1.weight.zero_()  # 官方：zero init fc1 使初始 delta=0

        # 预建 Sobel kernel，register_buffer 让它随 model.to(device) 一起走，
        # 消除每步 np.outer + from_numpy + .to(device) + repeat 的 host-device 同步。
        # 数学完全等价：系数 / repeat / groups 与官方原文相同。
        _dx = np.outer([1, 2, 1], [-1, 0, 1]) / 8.0        # (3,3) Sobel x
        _dy = _dx.T                                          # (3,3) Sobel y
        sobel_x = torch.from_numpy(_dx.astype(np.float32)).view(1, 1, 3, 3).repeat(channel_n, 1, 1, 1)
        sobel_y = torch.from_numpy(_dy.astype(np.float32)).view(1, 1, 3, 3).repeat(channel_n, 1, 1, 1)
        self.register_buffer("sobel_x", sobel_x)  # (channel_n, 1, 3, 3)
        self.register_buffer("sobel_y", sobel_y)  # (channel_n, 1, 3, 3)

        self.to(device)

    def perceive(self, x: torch.Tensor) -> torch.Tensor:
        """Sobel x + Sobel y + identity，input (B, C, H, W)，output (B, 3C, H, W)。

        用预建的 register_buffer sobel_x/sobel_y，消除每步 numpy 重建 + .to(device) 传输。
        """
        y1 = F.conv2d(x, self.sobel_x, padding=1, groups=self.channel_n)
        y2 = F.conv2d(x, self.sobel_y, padding=1, groups=self.channel_n)
        return torch.cat((x, y1, y2), dim=1)  # (B, 3C, H, W)

    def update(self, x_in: torch.Tensor, fire_rate: float | None = None) -> torch.Tensor:
        """单步 update，layout (B, H, W, C)。"""
        if fire_rate is None:
            fire_rate = self.fire_rate

        x = x_in.transpose(1, 3)           # (B, H, W, C) -> (B, C, H, W)
        dx = self.perceive(x)               # (B, 3C, H, W)
        dx = dx.transpose(1, 3)             # (B, W, H, 3C) -- 官方顺序
        dx = self.fc0(dx)
        dx = F.relu(dx)
        dx = self.fc1(dx)                   # (B, W, H, C)

        # stochastic mask（device 上生成，避免 CPU->GPU 同步）
        stochastic = (
            torch.rand(dx.size(0), dx.size(1), dx.size(2), 1, device=self.device)
            > fire_rate
        ).float()
        dx = dx * stochastic

        # 还原：官方 x = x + dx.transpose(1,3)，x 是 (B,C,H,W)
        dx_t = dx.transpose(1, 3)           # (B, W, H, C) -> (B, C, H, W)
        x_new = x + dx_t                    # (B, C, H, W)
        x_new = x_new.transpose(1, 3)       # (B, H, W, C)
        return x_new

    def forward(
        self, x: torch.Tensor, steps: int = 64, fire_rate: float | None = None
    ) -> torch.Tensor:
        """T 步迭代，返回 (B, H, W, C)。不冻结可见通道。"""
        for _ in range(steps):
            x = self.update(x, fire_rate)
        return x


# ==============================================================================
# 3. Mode-specific seed builders & damage
# ==============================================================================

def build_seed_damage(img: torch.Tensor, channel_n: int) -> torch.Tensor:
    """mode=damage: seed = 原图（可见通道=img，隐藏=0）。

    img: (B, H, W, 1) float32 [0,1]
    返回: (B, H, W, channel_n)
    """
    B, H, W, _ = img.shape
    seed = torch.zeros(B, H, W, channel_n, dtype=img.dtype, device=img.device)
    seed[:, :, :, :1] = img
    return seed


def apply_damage(x: torch.Tensor, damage_frac: float = 0.25) -> torch.Tensor:
    """对 (B, H, W, C) NCA 状态随机抹一个矩形区域（全通道置 0）。

    damage_frac: 损伤区边长 / 总边长（默认 1/4）。
    每个样本独立随机位置，batch 内各不同。
    """
    B, H, W, C = x.shape
    x = x.clone()
    side_h = max(1, int(H * damage_frac))
    side_w = max(1, int(W * damage_frac))
    for b in range(B):
        r0 = random.randint(0, H - side_h)
        c0 = random.randint(0, W - side_w)
        x[b, r0:r0 + side_h, c0:c0 + side_w, :] = 0.0
    return x


def build_seed_reconstruct(img: torch.Tensor, channel_n: int, low_res: int = 16) -> torch.Tensor:
    """mode=reconstruct: seed 可见通道 = img 降采样到 low_res 再上采样回 H（糊图）。

    img: (B, H, W, 1) float32 [0,1]
    返回: (B, H, W, channel_n)，可见通道 = 糊图，隐藏 = 0
    """
    B, H, W, _ = img.shape
    # img (B, H, W, 1) -> (B, 1, H, W) for F.interpolate
    img_chf = img.permute(0, 3, 1, 2)  # (B, 1, H, W)
    blurry = F.interpolate(img_chf, size=(low_res, low_res), mode="bilinear", align_corners=False)
    blurry = F.interpolate(blurry, size=(H, W), mode="bilinear", align_corners=False)
    blurry = blurry.permute(0, 2, 3, 1)  # (B, H, W, 1)

    seed = torch.zeros(B, H, W, channel_n, dtype=img.dtype, device=img.device)
    seed[:, :, :, :1] = blurry
    return seed


# ==============================================================================
# 4. Sample Pool（防发散核心）
# ==============================================================================

class SamplePool:
    """持久化 NCA 状态池，防止 NCA 发散。

    做法（官方 texture/growing NCA）：
      - pool 储存 NCA 迭代中间状态
      - 每 batch 从 pool 随机取，跑 T 步，loss 后把新状态放回 pool
      - 偶尔注入新鲜 seed（replace 个），强制 NCA 保持「从头恢复」能力
    """

    def __init__(self, pool_size: int, h: int, w: int, channel_n: int, device: torch.device) -> None:
        self.pool_size = pool_size
        self.device = device
        self._pool = torch.zeros(pool_size, h, w, channel_n, device=device)

    def seed_from_batch(self, seeds: torch.Tensor) -> None:
        """用已构建好的 seed 初始化 pool 前 N 个槽。

        seeds: (N, H, W, channel_n)
        """
        n = min(seeds.size(0), self.pool_size)
        self._pool[:n] = seeds[:n].detach()

    def sample(self, batch_size: int, replace: int = 1) -> tuple:
        """随机取 batch_size 个样本，返回 (batch_tensor, indices)。

        replace: 把其中 replace 个替换为全零（模拟从新鲜 seed 开始）。
        """
        indices = random.sample(range(self.pool_size), min(batch_size, self.pool_size))
        batch = self._pool[indices].clone()
        for i in range(min(replace, len(indices))):
            batch[i] = torch.zeros_like(batch[i])
        return batch, indices

    def commit(self, batch: torch.Tensor, indices: list) -> None:
        """把跑完 T 步的 NCA 状态写回 pool。

        用 CPU LongTensor 做 fancy index 写入，避免 CUDA illegal memory access。
        """
        idx_tensor = torch.LongTensor(indices)
        data = batch.detach().clone().to(self._pool.device)
        self._pool[idx_tensor] = data


# ==============================================================================
# 5. 纯 numpy 指标（避免 scipy OMP 冲突）
# ==============================================================================

def psnr_numpy(pred: np.ndarray, target: np.ndarray, max_val: float = 1.0) -> float:
    """PSNR，输入 [0,1] float。"""
    mse = np.mean((pred - target) ** 2)
    if mse < 1e-10:
        return 100.0
    return float(10.0 * np.log10(max_val ** 2 / mse))


def ssim_numpy(pred: np.ndarray, target: np.ndarray) -> float:
    """简化 SSIM（全局统计，val 监控用），纯 numpy 实现。"""
    C1 = (0.01) ** 2
    C2 = (0.03) ** 2
    mu1 = float(np.mean(pred))
    mu2 = float(np.mean(target))
    sigma1_sq = float(np.var(pred))
    sigma2_sq = float(np.var(target))
    sigma12 = float(np.mean((pred - mu1) * (target - mu2)))
    numerator = (2 * mu1 * mu2 + C1) * (2 * sigma12 + C2)
    denominator = (mu1 ** 2 + mu2 ** 2 + C1) * (sigma1_sq + sigma2_sq + C2)
    if abs(denominator) < 1e-10:
        return 0.0
    return float(numerator / denominator)


# ==============================================================================
# 6. 保存对比图 [seed | 输出 | 原图]
# ==============================================================================

def save_comparison(
    seed_vis: np.ndarray,
    predicted: np.ndarray,
    original: np.ndarray,
    out_path: str,
) -> None:
    """存 [seed 可见通道 | NCA 输出 | 原图] 横拼 PNG。

    所有输入: (H, W) float32 [0,1]
    """
    def to_u8(arr: np.ndarray) -> np.ndarray:
        return (np.clip(arr, 0.0, 1.0) * 255).astype(np.uint8)

    row = np.concatenate([to_u8(seed_vis), to_u8(predicted), to_u8(original)], axis=1)
    img = Image.fromarray(row, mode="L")
    img.save(out_path)


# ==============================================================================
# 7. State JSON（训练中实时写）
# ==============================================================================

def write_state(
    state_path: str,
    epoch: int,
    train_loss: float,
    val_psnr: float,
    val_ssim: float,
    diverged: bool,
    extra: dict | None = None,
) -> None:
    payload: dict = {
        "epoch": epoch,
        "train_loss": train_loss,
        "val_psnr": val_psnr,
        "val_ssim": val_ssim,
        "diverged": diverged,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    if extra:
        payload.update(extra)
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


# ==============================================================================
# 8. 主训练流程
# ==============================================================================

def train(cfg: dict) -> None:
    mode = cfg.get("mode", "damage")
    assert mode in ("damage", "reconstruct"), f"Unknown mode: {mode}"

    # 设备
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[probe] mode={mode} device={device}")

    # 随机种子
    seed = cfg["data"]["seed"]
    torch.manual_seed(seed)
    np.random.seed(seed)
    random.seed(seed)

    # 输出目录（per-mode 子目录，防止两 mode 互覆）
    out_dir = pathlib.Path(cfg["output"]["out_dir"]) / mode
    out_dir.mkdir(parents=True, exist_ok=True)
    state_path = str(out_dir / cfg["output"]["state_json"])

    # 数据集划分
    n_normal = cfg["data"]["n_normal"]
    val_n = max(1, int(n_normal * cfg["data"]["val_split"]))
    train_n = n_normal - val_n
    all_indices = list(range(n_normal))
    random.Random(seed).shuffle(all_indices)
    train_indices = all_indices[:train_n]
    val_indices = all_indices[train_n:]

    resolution = cfg["data"]["resolution"]

    train_ds = NIHNormalDataset(
        img_dir=cfg["data"]["img_dir"],
        csv_path=cfg["data"]["csv_path"],
        resolution=resolution,
        n_normal=n_normal,
        seed=seed,
        indices=train_indices,
    )
    val_ds = NIHNormalDataset(
        img_dir=cfg["data"]["img_dir"],
        csv_path=cfg["data"]["csv_path"],
        resolution=resolution,
        n_normal=n_normal,
        seed=seed,
        indices=val_indices,
    )

    train_loader = DataLoader(
        train_ds,
        batch_size=cfg["train"]["batch"],
        shuffle=True,
        num_workers=0,
        pin_memory=False,
    )
    val_loader = DataLoader(
        val_ds,
        batch_size=cfg["train"]["batch"],
        shuffle=False,
        num_workers=0,
        pin_memory=False,
    )

    print(f"[probe] train={len(train_ds)}, val={len(val_ds)}, resolution={resolution}")

    # 模型
    channel_n = cfg["model"]["channel_n"]
    model = PersistenceNCA(
        channel_n=channel_n,
        fire_rate=cfg["model"]["fire_rate"],
        device=device,
        hidden_size=cfg["model"]["hidden_size"],
        input_channels=cfg["model"]["input_channels"],
    )

    optimizer = torch.optim.Adam(model.parameters(), lr=cfg["train"]["lr"])
    scheduler = torch.optim.lr_scheduler.ExponentialLR(
        optimizer, gamma=cfg["train"]["lr_gamma"]
    )

    # mode-specific 参数
    damage_frac = cfg.get("damage", {}).get("frac", 0.25)
    damage_steps_min = cfg.get("damage", {}).get("steps_t2_min", 32)
    damage_steps_max = cfg.get("damage", {}).get("steps_t2_max", 64)
    reconstruct_low_res = cfg.get("reconstruct", {}).get("low_res", 16)

    # Sample Pool
    pool = SamplePool(
        pool_size=cfg["train"]["pool_size"],
        h=resolution,
        w=resolution,
        channel_n=channel_n,
        device=device,
    )

    # 用训练集前 pool_size 张构建初始 seed 填 pool
    pool_init_imgs = []
    for i, img in enumerate(train_ds):
        pool_init_imgs.append(img.to(device))
        if i + 1 >= cfg["train"]["pool_size"]:
            break
    if pool_init_imgs:
        init_batch = torch.stack(pool_init_imgs, dim=0)  # (N, H, W, 1)
        if mode == "damage":
            init_seeds = build_seed_damage(init_batch, channel_n)
        else:
            init_seeds = build_seed_reconstruct(init_batch, channel_n, low_res=reconstruct_low_res)
        pool.seed_from_batch(init_seeds)

    # 发散监控
    loss_history: list[float] = []
    flat_steps = cfg["diverge"]["loss_flat_steps"]
    flat_tol = cfg["diverge"]["loss_flat_tol"]
    psnr_min = cfg["diverge"]["psnr_min"]
    diverged = False

    steps_min = cfg["train"]["steps_min"]
    steps_max = cfg["train"]["steps_max"]
    pool_replace = cfg["train"]["pool_replace"]
    epochs = cfg["train"]["epochs"]
    save_every = cfg["output"]["save_img_every"]

    best_psnr = -float("inf")

    print("[probe] Training start...")

    for epoch in range(1, epochs + 1):
        model.train()
        epoch_losses: list[float] = []

        for batch_imgs in train_loader:
            batch_imgs = batch_imgs.to(device)  # (B, H, W, 1)
            B = batch_imgs.size(0)

            # 从 pool 取持久化状态
            actual_B = min(B, cfg["train"]["pool_size"])
            pool_batch, pool_indices = pool.sample(actual_B, replace=pool_replace)
            pool_batch = pool_batch[:B].clone()
            pool_indices = pool_indices[:B]

            optimizer.zero_grad()

            if mode == "damage":
                # --- mode=damage ---
                # pool_replace 个重置的样本：重建干净 seed（可见=原图，隐藏=0）
                n_replace = min(pool_replace, B)
                fresh_seed = build_seed_damage(batch_imgs[:n_replace], channel_n)
                pool_batch[:n_replace] = fresh_seed

                # T1 步正常传播
                steps_t1 = random.randint(steps_min, steps_max)
                x = pool_batch
                for _ in range(steps_t1):
                    x = model.update(x)

                # 随机损伤（可见+隐藏全部置 0）
                x = apply_damage(x, damage_frac=damage_frac)

                # T2 步修复
                steps_t2 = random.randint(damage_steps_min, damage_steps_max)
                for _ in range(steps_t2):
                    x = model.update(x)

                x_out = x
                # loss 全图 MSE（不只是损伤区，鼓励 NCA 整图保持一致）
                loss = F.mse_loss(x_out[:, :, :, :1], batch_imgs[:B])

            else:
                # --- mode=reconstruct ---
                # pool_replace 个重置的样本：重建糊图 seed
                n_replace = min(pool_replace, B)
                fresh_seed = build_seed_reconstruct(
                    batch_imgs[:n_replace], channel_n, low_res=reconstruct_low_res
                )
                pool_batch[:n_replace] = fresh_seed

                steps = random.randint(steps_min, steps_max)
                x_out = pool_batch
                for _ in range(steps):
                    x_out = model.update(x_out)

                loss = F.mse_loss(x_out[:, :, :, :1], batch_imgs[:B])

            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            scheduler.step()

            # 写回 pool（detach 切断计算图，LongTensor index 避免 CUDA 非法访问）
            pool.commit(x_out.detach(), pool_indices)

            epoch_losses.append(loss.item())

        train_loss = float(np.mean(epoch_losses)) if epoch_losses else float("nan")
        loss_history.append(train_loss)

        # Val（从干净 seed 开始，不用 pool）
        model.eval()
        psnr_list: list[float] = []
        ssim_list: list[float] = []
        save_img_this_epoch = (epoch % save_every == 0) or (epoch == 1)
        saved_sample = False

        with torch.no_grad():
            for val_imgs in val_loader:
                val_imgs = val_imgs.to(device)  # (B, H, W, 1)
                B = val_imgs.size(0)

                if mode == "damage":
                    x_val = build_seed_damage(val_imgs, channel_n)
                    x_val = apply_damage(x_val, damage_frac=damage_frac)
                    for _ in range(steps_max):
                        x_val = model.update(x_val)
                    seed_vis = val_imgs[:, :, :, 0]  # 原图当 seed 显示列
                else:
                    blurry_seed = build_seed_reconstruct(val_imgs, channel_n, low_res=reconstruct_low_res)
                    x_val = blurry_seed.clone()
                    for _ in range(steps_max):
                        x_val = model.update(x_val)
                    seed_vis = blurry_seed[:, :, :, 0]  # 糊图当 seed 显示列

                pred = x_val[:, :, :, :1]  # (B, H, W, 1)

                for b in range(B):
                    pred_np = pred[b, :, :, 0].cpu().numpy()
                    gt_np = val_imgs[b, :, :, 0].cpu().numpy()
                    psnr_list.append(psnr_numpy(pred_np, gt_np))
                    ssim_list.append(ssim_numpy(pred_np, gt_np))

                    if save_img_this_epoch and not saved_sample:
                        img_path = str(out_dir / f"epoch_{epoch:04d}_compare.png")
                        save_comparison(
                            seed_vis[b].cpu().numpy(),
                            np.clip(pred_np, 0.0, 1.0),
                            gt_np,
                            img_path,
                        )
                        saved_sample = True

        val_psnr = float(np.mean(psnr_list)) if psnr_list else 0.0
        val_ssim = float(np.mean(ssim_list)) if ssim_list else 0.0

        if val_psnr > best_psnr:
            best_psnr = val_psnr
            torch.save(model.state_dict(), str(out_dir / "best_model.pth"))

        # 发散判据 1：PSNR 塌破阈值（epoch>10 才判，给 NCA 热身）
        if epoch > 10 and val_psnr < psnr_min:
            print(f"[probe] DIVERGED: val_psnr={val_psnr:.2f} < {psnr_min} @ epoch {epoch}")
            diverged = True

        # 发散判据 2：loss 死平
        if len(loss_history) >= flat_steps:
            recent = loss_history[-flat_steps:]
            if (max(recent) - min(recent)) < flat_tol:
                print(f"[probe] DIVERGED: loss flat for {flat_steps} epochs @ epoch {epoch}")
                diverged = True

        # 发散判据 3：NaN/inf
        if not np.isfinite(train_loss):
            print(f"[probe] DIVERGED: train_loss={train_loss} @ epoch {epoch}")
            diverged = True

        # 写 state.json（含 mode 字段）
        write_state(
            state_path=state_path,
            epoch=epoch,
            train_loss=train_loss,
            val_psnr=val_psnr,
            val_ssim=val_ssim,
            diverged=diverged,
            extra={
                "mode": mode,
                "best_psnr": best_psnr,
                "lr": scheduler.get_last_lr()[0],
                "converged": bool(val_psnr >= cfg["diverge"]["psnr_converge"]),
            },
        )

        if epoch % 10 == 0 or epoch == 1 or diverged:
            print(
                f"[probe] epoch={epoch:4d}/{epochs} "
                f"loss={train_loss:.6f} "
                f"val_psnr={val_psnr:.2f}dB "
                f"val_ssim={val_ssim:.4f} "
                f"best_psnr={best_psnr:.2f}dB"
            )

        if diverged:
            print("[probe] Early stop due to divergence.")
            break

    status = "DIVERGED" if diverged else ("CONVERGED" if best_psnr >= cfg["diverge"]["psnr_converge"] else "PARTIAL")
    print(f"\n[probe] Done. mode={mode} Status={status}, best_val_psnr={best_psnr:.2f}dB")
    print(f"[probe] Results in: {out_dir}")
    print(f"[probe] state.json: {state_path}")


# ==============================================================================
# 9. Entry point（Windows spawn guard）
# ==============================================================================

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="NCA Persistence Probe")
    parser.add_argument(
        "--config",
        type=str,
        default=str(pathlib.Path(__file__).parent / "probe_persistence.yaml"),
        help="Path to YAML config",
    )
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    train(cfg)


if __name__ == "__main__":
    main()
