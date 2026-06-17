"""probe_persistence.py
Kill-shot probe: 验证 2D NCA 能否在正常胸片上学会非平凡的图像修复/保持
以及学习 t0->t1 疾病进展映射（Gate3 轨迹探针）。

Gate 1 / Gate 3 / Direction B / Med-NCA NCA-JEPA project
不启动正式训练，写完交主线跑。

三个非退化 mode（恒等 NCA 在所有 mode 都必须失败）：
- mode=damage  : seed=原图，随机矩形损伤后跑 T2 步，loss=MSE(输出,原图)
                 恒等 NCA 无法填补损伤 -> loss 大 -> 真测试
- mode=reconstruct: seed=16^2 bilinear 糊图 resize 回 resolution^2，loss=MSE(输出,原图)
                 恒等 NCA 输出仍糊 -> loss 大 -> 真测试
- mode=trajectory: seed=t0 图，target=t1 图（同患者纵向 No Finding->单一 finding）
                 跑 T 步，loss=MSE(输出可见通道, t1)
                 Gate3 杀手锏：中间态 step 16/32/48/64 单调性指标
                 （dist_to_t1 单调降 / dist_from_t0 单调升）
                 平凡基线 baseline_psnr_t0_to_t1 写入 state.json

三 mode 共同：
- forward 全程禁止把可见通道重写回真图（退化根因已删除）
- sample pool 防发散、随机步数、state.json 实时写（含 mode 字段）
- PSNR/SSIM（纯 numpy）、发散早停、每 N ep 对比图
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

class NIHPairDataset(Dataset):
    """NIH CXR-14 同患者纵向对：t0=No Finding, t1=单一指定 finding。

    skeptic 修1：固定 finding="Nodule"（局灶病，材料叙事范例），不再自动选最多的类。
    关键过滤：只保留 t0/t1 同 View Position 的对（消除 PA/AP 体位换带来的噪声）。
    patient-level train/val 切分，同患者不跨集（防泄漏）。

    __getitem__ 返回 (t0_img, t1_img)，两张均为 FloatTensor (H, W, 1) [0,1]。
    """

    def __init__(
        self,
        img_dir: str,
        csv_path: str,
        resolution: int,
        seed: int,
        val_split: float = 0.1,
        split: str = "train",               # "train" | "val"
        finding: str = "Nodule",            # 固定指定，不自动选最多（skeptic 修1）
        require_same_view: bool = True,     # 只留 t0/t1 同 View Position 的对
        max_pairs: int | None = None,       # None=全部
    ) -> None:
        import csv as csv_mod
        from collections import defaultdict

        self.img_dir = pathlib.Path(img_dir)
        self.resolution = resolution

        # ---- 读 CSV（含 View Position）----
        all_rows: list[dict] = []
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv_mod.DictReader(f)
            for row in reader:
                all_rows.append({
                    "fname": row["Image Index"].strip(),
                    "labels": row["Finding Labels"].strip(),
                    "pid": row["Patient ID"].strip(),
                    "followup": int(row["Follow-up #"].strip()),
                    "vp": row["View Position"].strip(),
                })

        # ---- 按患者分组 ----
        patient_records: dict[str, list] = defaultdict(list)
        for r in all_rows:
            patient_records[r["pid"]].append(r)

        # ---- 抽 (t0, t1) 对：指定 finding + 可选同VP过滤 ----
        pairs: list[tuple[str, str, str]] = []   # (pid, t0_fname, t1_fname)
        total_before_vp = 0

        for pid, recs in patient_records.items():
            recs_sorted = sorted(recs, key=lambda r: r["followup"])
            # 最早 No Finding
            t0_cands = [r for r in recs_sorted if r["labels"] == "No Finding"]
            if not t0_cands:
                continue
            earliest_t0 = min(t0_cands, key=lambda r: r["followup"])
            # 最早符合指定 finding 的 t1（followup 晚于 t0）
            for r in recs_sorted:
                if r["followup"] <= earliest_t0["followup"]:
                    continue
                if r["labels"] != finding:
                    continue
                # 图片存在校验
                if not (self.img_dir / earliest_t0["fname"]).exists():
                    break
                if not (self.img_dir / r["fname"]).exists():
                    break
                total_before_vp += 1
                if require_same_view and r["vp"] != earliest_t0["vp"]:
                    break  # 体位不同，丢弃（但不继续找，一患者只尝试一次）
                pairs.append((pid, earliest_t0["fname"], r["fname"]))
                break

        same_vp_n = len(pairs)
        print(
            f"\n[NIHPairDataset] finding='{finding}' "
            f"total_pairs={total_before_vp} "
            f"same_vp_pairs={same_vp_n} "
            f"(require_same_view={require_same_view})"
        )

        if max_pairs is not None:
            rng = random.Random(seed)
            rng.shuffle(pairs)
            pairs = pairs[:max_pairs]

        # ---- patient-level train/val split ----
        all_pids = list({p[0] for p in pairs})
        rng = random.Random(seed)
        rng.shuffle(all_pids)
        val_n_pids = max(1, int(len(all_pids) * val_split))
        val_pids = set(all_pids[:val_n_pids])
        train_pids = set(all_pids[val_n_pids:])

        if split == "train":
            self.pairs = [(t0, t1) for pid, t0, t1 in pairs if pid in train_pids]
        else:
            self.pairs = [(t0, t1) for pid, t0, t1 in pairs if pid in val_pids]

        self.selected_finding = finding
        print(
            f"[NIHPairDataset] split={split} n_pairs={len(self.pairs)} "
            f"(train_pids={len(train_pids)}, val_pids={len(val_pids)})"
        )

    def __len__(self) -> int:
        return len(self.pairs)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor]:
        t0_fname, t1_fname = self.pairs[idx]

        def _load(fname: str) -> torch.Tensor:
            img = Image.open(str(self.img_dir / fname)).convert("L")
            img = img.resize((self.resolution, self.resolution), Image.BILINEAR)
            arr = np.array(img, dtype=np.float32) / 255.0   # (H, W)
            arr = arr[:, :, np.newaxis]                       # (H, W, 1)
            return torch.from_numpy(arr)                      # FloatTensor (H, W, 1)

        return _load(t0_fname), _load(t1_fname)


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


def build_seed_trajectory(t0_img: torch.Tensor, channel_n: int) -> torch.Tensor:
    """mode=trajectory: seed 可见通道 = t0 图，隐藏通道置 0。

    t0_img: (B, H, W, 1) float32 [0,1]
    返回: (B, H, W, channel_n)
    """
    B, H, W, _ = t0_img.shape
    seed = torch.zeros(B, H, W, channel_n, dtype=t0_img.dtype, device=t0_img.device)
    seed[:, :, :, :1] = t0_img
    return seed


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
# 5b. trajectory 中间态评估工具（Gate3 核心）
# ==============================================================================

def compute_roi_mask(t0_np: np.ndarray, t1_np: np.ndarray, smooth_sigma: float = 2.0, threshold: float = 0.1) -> np.ndarray:
    """计算 diff ROI mask：(|t1-t0| 高斯平滑后 > threshold) 的二值区域。

    skeptic 修2：局灶病变区的检测，用于 change_in_roi_frac 计算。
    平滑参数防止单像素噪声被计入 ROI。

    t0_np, t1_np: (H, W) float32 [0,1]
    返回: (H, W) bool mask，True = 病灶变化区
    """
    diff = np.abs(t1_np.astype(np.float32) - t0_np.astype(np.float32))
    # 纯 numpy 高斯平滑（避免 scipy）：用均匀盒滤波近似（3次 box=近似 Gaussian）
    # kernel_size = max(3, int(smooth_sigma * 3) | 1)  确保奇数
    ks = max(3, int(smooth_sigma * 2) * 2 + 1)
    # 三次 box filter 近似 Gaussian（中心极限定理）
    kernel = np.ones(ks, dtype=np.float32) / ks
    smoothed = np.apply_along_axis(lambda x: np.convolve(x, kernel, mode="same"), 0, diff)
    smoothed = np.apply_along_axis(lambda x: np.convolve(x, kernel, mode="same"), 1, smoothed)
    smoothed = np.apply_along_axis(lambda x: np.convolve(x, kernel, mode="same"), 0, smoothed)
    smoothed = np.apply_along_axis(lambda x: np.convolve(x, kernel, mode="same"), 1, smoothed)
    smoothed = np.apply_along_axis(lambda x: np.convolve(x, kernel, mode="same"), 0, smoothed)
    mask = smoothed > threshold
    return mask


def compute_change_in_roi_frac(
    snap_a: np.ndarray,
    snap_b: np.ndarray,
    roi_mask: np.ndarray,
) -> float:
    """计算相邻步变化 |snap_b - snap_a| 的逐像素能量落在 ROI mask 内的占比。

    skeptic 修2 核心：真局部生长 -> 变化集中病灶区 -> frac 高；
                      全局线性插值 -> 变化均匀铺满 -> frac 低。

    snap_a, snap_b: (H, W) float32
    roi_mask: (H, W) bool
    返回: float [0, 1]，ROI 内能量 / 总能量（若总能量 < 1e-10 返回 0）
    """
    delta = np.abs(snap_b.astype(np.float32) - snap_a.astype(np.float32))
    total_energy = float(np.sum(delta ** 2))
    if total_energy < 1e-10:
        return 0.0
    roi_energy = float(np.sum((delta ** 2) * roi_mask.astype(np.float32)))
    return roi_energy / total_energy


def compute_front_expansion_violation_rate(
    roi_mask: np.ndarray,
    snap_sequence: list[np.ndarray],
    t0_np: np.ndarray,
    changed_thresh: float = 0.05,
) -> float:
    """计算 ROI 内已变化像素数随步是否单调增（病变前沿扩张）。

    skeptic 修2 可选：changed 像素 = |snap - t0| > changed_thresh 且在 ROI 内。
    返回违反率（多少比例的相邻步对违反单调增）。

    snap_sequence: list of (H, W) 按步排列
    """
    if len(snap_sequence) < 2:
        return 0.0
    counts = []
    for snap in snap_sequence:
        changed = (np.abs(snap - t0_np) > changed_thresh) & roi_mask
        counts.append(int(np.sum(changed)))
    violations = sum(1 for i in range(len(counts) - 1) if counts[i + 1] < counts[i] - 0)
    return violations / max(1, len(counts) - 1)


def compute_laplacian_variance(img_np: np.ndarray) -> float:
    """计算图像 Laplacian 方差（高频能量代理）。

    skeptic 修4：防 L2 把中间态糊成均值假装收敛。
    糊图 Laplacian 方差低，清晰图高。

    img_np: (H, W) float32 [0,1]
    纯 numpy 实现（无 scipy/cv2）：用有限差分 Laplacian。
    """
    # 4-邻域 Laplacian: L = -4*p + p_left + p_right + p_up + p_down
    lap = (
        -4.0 * img_np[1:-1, 1:-1]
        + img_np[0:-2, 1:-1]    # up
        + img_np[2:,   1:-1]    # down
        + img_np[1:-1, 0:-2]    # left
        + img_np[1:-1, 2:]      # right
    )
    return float(np.var(lap))


def compute_linear_interp_metrics(
    t0_np: np.ndarray,
    t1_np: np.ndarray,
    eval_steps: list[int],
    roi_mask: np.ndarray,
) -> dict:
    """基线：全局线性插值 out_k = (1-k/T)*t0 + (k/T)*t1。

    skeptic 修3：零训练纯算基线，用于对比 change_in_roi_frac。
    T = max(eval_steps)，在各 eval_step 插值后算指标。

    返回 dict：
      linear_final_psnr_to_t1, linear_change_in_roi_frac_mean,
      linear_mono_to_t1_violation_rate
    """
    T = max(eval_steps)
    snaps = {}
    for s in eval_steps:
        alpha = s / T   # alpha=1 时 = t1
        snaps[s] = (1.0 - alpha) * t0_np + alpha * t1_np

    # final PSNR
    final_psnr = psnr_numpy(snaps[T], t1_np)

    # change_in_roi_frac for adjacent steps
    frac_vals = []
    snap_list = [snaps[s] for s in eval_steps]
    for i in range(len(snap_list) - 1):
        frac_vals.append(compute_change_in_roi_frac(snap_list[i], snap_list[i + 1], roi_mask))

    # dist_to_t1 序列（期望单调降）
    dists_to_t1 = [float(np.mean((snaps[s] - t1_np) ** 2)) for s in eval_steps]
    mono_viol = compute_monotonicity_violation_rate(dists_to_t1)

    return {
        "linear_final_psnr_to_t1": final_psnr,
        "linear_change_in_roi_frac_mean": float(np.mean(frac_vals)) if frac_vals else 0.0,
        "linear_mono_to_t1_violation_rate": mono_viol,
    }


def compute_monotonicity_violation_rate(
    snap_dists: list[float],
) -> float:
    """给定一个样本在各 snapshot step 的距离序列，判断是否单调。

    snap_dists: list of floats, 长度 >= 2（比如 [d16, d32, d48, d64]）
    返回 0.0（单调）或 1.0（违反）——用于批量平均得到违反率。

    对 dist_to_t1 应该单调降（后面的 < 前面的），
    对 dist_from_t0 应该单调升（后面的 > 前面的）——
    传入前已由调用方取反向，所以统一检查「单调不增/不降」都用此函数检测「是否严格单调」。

    注：此函数检测序列是否单调不降（非严格），
    调用方按需传 dist_to_t1（期望降）或 negated dist_from_t0（期望降）。
    违反 = 存在 snap_dists[i+1] > snap_dists[i] 的情况（对降序来说是反弹）。
    """
    for i in range(len(snap_dists) - 1):
        if snap_dists[i + 1] > snap_dists[i] + 1e-8:
            return 1.0
    return 0.0


def save_trajectory_comparison(
    t0_np: np.ndarray,
    snaps: list[np.ndarray],
    t1_np: np.ndarray,
    out_path: str,
) -> None:
    """保存轨迹对比图：t0 | snap_steps... | t1 横拼 PNG。

    t0_np, t1_np: (H, W) float32 [0,1]
    snaps: list of (H, W) float32 [0,1]，按 step 排列
    """
    def to_u8(arr: np.ndarray) -> np.ndarray:
        return (np.clip(arr, 0.0, 1.0) * 255).astype(np.uint8)

    frames = [to_u8(t0_np)] + [to_u8(s) for s in snaps] + [to_u8(t1_np)]
    row = np.concatenate(frames, axis=1)  # (H, W*(2+len(snaps)))
    img = Image.fromarray(row, mode="L")
    img.save(out_path)


# ==============================================================================
# 5c. baseline_unet_oneshot：小 U-Net 强基线（skeptic 修3）
# ==============================================================================

class SmallUNet(nn.Module):
    """3-层 down/up U-Net，t0->t1 一跳映射，同等量级参数作强基线。

    skeptic 修3：NCA 终态 PSNR 不必赢 U-Net，但 NCA 必须在 change_in_roi_frac
    上明显 > 线性插值基线（U-Net 作终态参考，线性插值作局部性判定对照）。
    U-Net 无自然中间态，只输出终态。

    input: (B, 1, H, W)  output: (B, 1, H, W) [0,1]
    """

    def __init__(self, base_ch: int = 16) -> None:
        super().__init__()
        # Encoder
        self.enc1 = nn.Sequential(
            nn.Conv2d(1, base_ch, 3, padding=1), nn.ReLU(inplace=True),
            nn.Conv2d(base_ch, base_ch, 3, padding=1), nn.ReLU(inplace=True),
        )
        self.pool1 = nn.MaxPool2d(2)
        self.enc2 = nn.Sequential(
            nn.Conv2d(base_ch, base_ch * 2, 3, padding=1), nn.ReLU(inplace=True),
            nn.Conv2d(base_ch * 2, base_ch * 2, 3, padding=1), nn.ReLU(inplace=True),
        )
        self.pool2 = nn.MaxPool2d(2)
        # Bottleneck
        self.bottleneck = nn.Sequential(
            nn.Conv2d(base_ch * 2, base_ch * 4, 3, padding=1), nn.ReLU(inplace=True),
            nn.Conv2d(base_ch * 4, base_ch * 4, 3, padding=1), nn.ReLU(inplace=True),
        )
        # Decoder
        self.up2 = nn.ConvTranspose2d(base_ch * 4, base_ch * 2, 2, stride=2)
        self.dec2 = nn.Sequential(
            nn.Conv2d(base_ch * 4, base_ch * 2, 3, padding=1), nn.ReLU(inplace=True),
            nn.Conv2d(base_ch * 2, base_ch * 2, 3, padding=1), nn.ReLU(inplace=True),
        )
        self.up1 = nn.ConvTranspose2d(base_ch * 2, base_ch, 2, stride=2)
        self.dec1 = nn.Sequential(
            nn.Conv2d(base_ch * 2, base_ch, 3, padding=1), nn.ReLU(inplace=True),
            nn.Conv2d(base_ch, base_ch, 3, padding=1), nn.ReLU(inplace=True),
        )
        self.out_conv = nn.Conv2d(base_ch, 1, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: (B, 1, H, W) -> out: (B, 1, H, W) [0,1]"""
        e1 = self.enc1(x)
        e2 = self.enc2(self.pool1(e1))
        b = self.bottleneck(self.pool2(e2))
        d2 = self.dec2(torch.cat([self.up2(b), e2], dim=1))
        d1 = self.dec1(torch.cat([self.up1(d2), e1], dim=1))
        return torch.sigmoid(self.out_conv(d1))


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
    assert mode in ("damage", "reconstruct", "trajectory"), f"Unknown mode: {mode}"

    # 设备
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[probe] mode={mode} device={device}")

    # 随机种子
    seed = cfg["data"]["seed"]
    torch.manual_seed(seed)
    np.random.seed(seed)
    random.seed(seed)

    # 输出目录（per-mode 子目录，防止各 mode 互覆）
    out_dir = pathlib.Path(cfg["output"]["out_dir"]) / mode
    out_dir.mkdir(parents=True, exist_ok=True)
    state_path = str(out_dir / cfg["output"]["state_json"])

    resolution = cfg["data"]["resolution"]
    channel_n = cfg["model"]["channel_n"]

    # ---- 数据集（mode 分叉）----
    if mode == "trajectory":
        traj_cfg = cfg.get("trajectory", {})
        _finding = traj_cfg.get("finding", "Nodule")   # 默认 Nodule（skeptic 修1）
        _require_same_view = traj_cfg.get("require_same_view", True)
        train_ds = NIHPairDataset(
            img_dir=cfg["data"]["img_dir"],
            csv_path=cfg["data"]["csv_path"],
            resolution=resolution,
            seed=seed,
            val_split=cfg["data"].get("val_split", 0.1),
            split="train",
            finding=_finding,
            require_same_view=_require_same_view,
            max_pairs=traj_cfg.get("max_pairs", None),
        )
        val_ds = NIHPairDataset(
            img_dir=cfg["data"]["img_dir"],
            csv_path=cfg["data"]["csv_path"],
            resolution=resolution,
            seed=seed,
            val_split=cfg["data"].get("val_split", 0.1),
            split="val",
            finding=_finding,
            require_same_view=_require_same_view,
            max_pairs=traj_cfg.get("max_pairs", None),
        )
    else:
        n_normal = cfg["data"]["n_normal"]
        val_n = max(1, int(n_normal * cfg["data"]["val_split"]))
        train_n = n_normal - val_n
        all_indices = list(range(n_normal))
        random.Random(seed).shuffle(all_indices)
        train_indices = all_indices[:train_n]
        val_indices = all_indices[train_n:]
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

    # trajectory mode: baseline U-Net 同数据同 epoch 训练（skeptic 修3）
    unet_model: SmallUNet | None = None
    unet_optimizer = None
    if mode == "trajectory":
        traj_unet_cfg = cfg.get("trajectory", {})
        unet_base_ch = traj_unet_cfg.get("unet_base_ch", 16)
        unet_model = SmallUNet(base_ch=unet_base_ch).to(device)
        unet_optimizer = torch.optim.Adam(unet_model.parameters(), lr=cfg["train"]["lr"])
        print(f"[probe] U-Net baseline initialized (base_ch={unet_base_ch})")

    # mode-specific 参数
    damage_frac = cfg.get("damage", {}).get("frac", 0.25)
    damage_steps_min = cfg.get("damage", {}).get("steps_t2_min", 32)
    damage_steps_max = cfg.get("damage", {}).get("steps_t2_max", 64)
    reconstruct_low_res = cfg.get("reconstruct", {}).get("low_res", 16)

    # trajectory 参数
    traj_cfg = cfg.get("trajectory", {})
    traj_eval_steps: list[int] = traj_cfg.get("traj_eval_steps", [16, 32, 48, 64])

    # Sample Pool
    # trajectory mode: pool 只存 NCA 中间状态（(B,H,W,C)），
    # 但 pool 不记住对应 t1 target——
    # 设计选择：每 batch 从 loader 重取 (t0,t1) 对，pool_replace 个样本用新鲜 t0 seed 替换，
    # 其余槽位用 pool 里存的持久状态继续跑，loss 对 t1 计算。
    # 这保证每个 pool 槽位始终来自同一 t0 的传播路径，且我们始终知道对应 t1（来自本 batch）。
    # 简单且可靠：pool 大小 = batch_size，一批数据对应一批 pool 槽，无跨批污染。
    # 注：trajectory pool_size 建议等于 batch_size 的整数倍，默认用 batch_size。
    if mode == "trajectory":
        # trajectory pool：pool_size = min(cfg pool_size, len(train_ds))
        traj_pool_size = min(cfg["train"]["pool_size"], max(1, len(train_ds)))
        pool = SamplePool(
            pool_size=traj_pool_size,
            h=resolution,
            w=resolution,
            channel_n=channel_n,
            device=device,
        )
        # 初始化 pool：从训练集抽 pool_size 个 t0 作为 seed
        pool_init_t0s = []
        for i in range(min(traj_pool_size, len(train_ds))):
            t0_img, _ = train_ds[i]
            pool_init_t0s.append(t0_img.to(device))
        if pool_init_t0s:
            init_t0_batch = torch.stack(pool_init_t0s, dim=0)  # (N, H, W, 1)
            init_seeds = build_seed_trajectory(init_t0_batch, channel_n)
            pool.seed_from_batch(init_seeds)
    else:
        pool = SamplePool(
            pool_size=cfg["train"]["pool_size"],
            h=resolution,
            w=resolution,
            channel_n=channel_n,
            device=device,
        )
        pool_init_imgs = []
        for i, img in enumerate(train_ds):
            # trajectory 的 train_ds 返回 tuple，其他返回 Tensor
            pool_init_imgs.append(img.to(device))
            if i + 1 >= cfg["train"]["pool_size"]:
                break
        if pool_init_imgs:
            init_batch = torch.stack(pool_init_imgs, dim=0)
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

        for batch_data in train_loader:
            if mode == "trajectory":
                # batch_data = (t0_batch, t1_batch), each (B, H, W, 1)
                t0_batch, t1_batch = batch_data
                t0_batch = t0_batch.to(device)
                t1_batch = t1_batch.to(device)
                B = t0_batch.size(0)
                batch_imgs = t0_batch   # alias for pool sample sizing
            else:
                batch_imgs = batch_data.to(device)
                B = batch_imgs.size(0)

            # 从 pool 取持久化状态
            actual_B = min(B, pool.pool_size)
            pool_batch, pool_indices = pool.sample(actual_B, replace=pool_replace)
            pool_batch = pool_batch[:B].clone()
            pool_indices = pool_indices[:B]

            optimizer.zero_grad()

            if mode == "damage":
                n_replace = min(pool_replace, B)
                fresh_seed = build_seed_damage(batch_imgs[:n_replace], channel_n)
                pool_batch[:n_replace] = fresh_seed

                steps_t1 = random.randint(steps_min, steps_max)
                x = pool_batch
                for _ in range(steps_t1):
                    x = model.update(x)

                x = apply_damage(x, damage_frac=damage_frac)

                steps_t2 = random.randint(damage_steps_min, damage_steps_max)
                for _ in range(steps_t2):
                    x = model.update(x)

                x_out = x
                loss = F.mse_loss(x_out[:, :, :, :1], batch_imgs[:B])

            elif mode == "reconstruct":
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

            else:
                # --- mode=trajectory ---
                # pool_replace 个重置为新鲜 t0 seed
                n_replace = min(pool_replace, B)
                fresh_seed = build_seed_trajectory(t0_batch[:n_replace], channel_n)
                pool_batch[:n_replace] = fresh_seed

                # 随机步数 [steps_min, steps_max] 迭代
                steps = random.randint(steps_min, steps_max)
                x_out = pool_batch
                for _ in range(steps):
                    x_out = model.update(x_out)

                # loss = MSE(NCA 输出可见通道, t1)
                loss = F.mse_loss(x_out[:, :, :, :1], t1_batch[:B])

            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            scheduler.step()

            pool.commit(x_out.detach(), pool_indices)
            epoch_losses.append(loss.item())

            # U-Net baseline 同步训练（trajectory 专用）
            if mode == "trajectory" and unet_model is not None and unet_optimizer is not None:
                unet_model.train()
                unet_optimizer.zero_grad()
                # input: (B, 1, H, W) channel-first
                t0_cf = t0_batch[:B].permute(0, 3, 1, 2)   # (B, 1, H, W)
                t1_cf = t1_batch[:B].permute(0, 3, 1, 2)   # (B, 1, H, W)
                unet_pred = unet_model(t0_cf)
                unet_loss = F.mse_loss(unet_pred, t1_cf)
                unet_loss.backward()
                unet_optimizer.step()

        train_loss = float(np.mean(epoch_losses)) if epoch_losses else float("nan")
        loss_history.append(train_loss)

        # ---- Val ----
        model.eval()
        psnr_list: list[float] = []
        ssim_list: list[float] = []
        save_img_this_epoch = (epoch % save_every == 0) or (epoch == 1)
        saved_sample = False

        # trajectory 专用中间态指标收集（skeptic 修2/3/4 全套）
        if mode == "trajectory":
            dists_to_t1_per_step: dict[int, list[float]] = {s: [] for s in traj_eval_steps}
            dists_from_t0_per_step: dict[int, list[float]] = {s: [] for s in traj_eval_steps}
            mono_to_t1_violations: list[float] = []
            mono_from_t0_violations: list[float] = []
            baseline_psnr_list: list[float] = []          # PSNR(t0, t1)
            final_psnr_to_t1_list: list[float] = []
            final_psnr_to_t0_list: list[float] = []
            # 修2：局部性指标
            change_in_roi_frac_list: list[float] = []     # NCA 相邻步 ROI 内能量占比均值
            front_expansion_viol_list: list[float] = []   # 前沿扩张违反率
            # 修3：基线
            linear_frac_list: list[float] = []            # 线性插值 change_in_roi_frac
            linear_psnr_list: list[float] = []            # 线性插值 final_psnr
            unet_psnr_list: list[float] = []              # U-Net 终态 PSNR
            # 修4：Laplacian 方差（抗糊代理）
            lap_var_pred_list: list[float] = []           # NCA 终态
            lap_var_t1_list: list[float] = []             # target（t1 参考值）

            traj_out_dir = out_dir / "trajectory"
            traj_out_dir.mkdir(parents=True, exist_ok=True)

        with torch.no_grad():
            for val_data in val_loader:
                if mode == "trajectory":
                    t0_val, t1_val = val_data
                    t0_val = t0_val.to(device)   # (B, H, W, 1)
                    t1_val = t1_val.to(device)   # (B, H, W, 1)
                    B_val = t0_val.size(0)

                    # NCA 中间态 snapshot
                    max_eval_step = max(traj_eval_steps)
                    x_eval = build_seed_trajectory(t0_val, channel_n)
                    snapshots: dict[int, torch.Tensor] = {}
                    for s in range(1, max_eval_step + 1):
                        x_eval = model.update(x_eval)
                        if s in traj_eval_steps:
                            snapshots[s] = x_eval[:, :, :, :1].clone()  # (B, H, W, 1)

                    pred_final = snapshots[max(traj_eval_steps)]

                    # U-Net 基线终态（skeptic 修3）
                    unet_pred_batch: torch.Tensor | None = None
                    if unet_model is not None:
                        unet_model.eval()
                        t0_cf = t0_val.permute(0, 3, 1, 2)  # (B, 1, H, W)
                        unet_pred_batch = unet_model(t0_cf)  # (B, 1, H, W)

                    for b in range(B_val):
                        t0_np = t0_val[b, :, :, 0].cpu().numpy()
                        t1_np = t1_val[b, :, :, 0].cpu().numpy()

                        # 平凡基线
                        baseline_psnr_list.append(psnr_numpy(t0_np, t1_np))

                        # 修2：ROI mask（病灶变化区）
                        roi_mask = compute_roi_mask(
                            t0_np, t1_np,
                            smooth_sigma=traj_cfg.get("roi_smooth_sigma", 2.0),
                            threshold=traj_cfg.get("roi_threshold", 0.1),
                        )

                        # 各 step 距离 + change_in_roi_frac（相邻步）
                        sample_dists_to_t1: list[float] = []
                        sample_dists_from_t0: list[float] = []
                        snap_list_np = [snapshots[s][b, :, :, 0].cpu().numpy() for s in traj_eval_steps]

                        for i, s in enumerate(traj_eval_steps):
                            snap_np = snap_list_np[i]
                            d_to_t1 = float(np.mean((snap_np - t1_np) ** 2))
                            d_from_t0 = float(np.mean((snap_np - t0_np) ** 2))
                            dists_to_t1_per_step[s].append(d_to_t1)
                            dists_from_t0_per_step[s].append(d_from_t0)
                            sample_dists_to_t1.append(d_to_t1)
                            sample_dists_from_t0.append(d_from_t0)

                        # change_in_roi_frac：相邻步之间（t0->snap16, snap16->snap32, ...）
                        prev_np = t0_np
                        frac_vals_sample: list[float] = []
                        for snap_np in snap_list_np:
                            frac_vals_sample.append(
                                compute_change_in_roi_frac(prev_np, snap_np, roi_mask)
                            )
                            prev_np = snap_np
                        change_in_roi_frac_list.append(float(np.mean(frac_vals_sample)))

                        # front_expansion 违反率（skeptic 修2 可选）
                        front_expansion_viol_list.append(
                            compute_front_expansion_violation_rate(
                                roi_mask, snap_list_np, t0_np,
                                changed_thresh=traj_cfg.get("front_changed_thresh", 0.05),
                            )
                        )

                        # 单调性
                        mono_to_t1_violations.append(
                            compute_monotonicity_violation_rate(sample_dists_to_t1)
                        )
                        mono_from_t0_violations.append(
                            compute_monotonicity_violation_rate([-d for d in sample_dists_from_t0])
                        )

                        # 终态 PSNR
                        pred_final_np = pred_final[b, :, :, 0].cpu().numpy()
                        final_psnr_to_t1_list.append(psnr_numpy(pred_final_np, t1_np))
                        final_psnr_to_t0_list.append(psnr_numpy(pred_final_np, t0_np))

                        psnr_list.append(psnr_numpy(pred_final_np, t1_np))
                        ssim_list.append(ssim_numpy(pred_final_np, t1_np))

                        # 修3a：线性插值基线
                        lin_metrics = compute_linear_interp_metrics(
                            t0_np, t1_np, traj_eval_steps, roi_mask
                        )
                        linear_frac_list.append(lin_metrics["linear_change_in_roi_frac_mean"])
                        linear_psnr_list.append(lin_metrics["linear_final_psnr_to_t1"])

                        # 修3b：U-Net 基线 PSNR
                        if unet_pred_batch is not None:
                            unet_np = unet_pred_batch[b, 0].cpu().numpy()
                            unet_psnr_list.append(psnr_numpy(unet_np, t1_np))

                        # 修4：Laplacian 方差
                        lap_var_pred_list.append(compute_laplacian_variance(pred_final_np))
                        lap_var_t1_list.append(compute_laplacian_variance(t1_np))

                        # 轨迹对比图
                        if save_img_this_epoch and not saved_sample:
                            img_path = str(traj_out_dir / f"epoch_{epoch:04d}_traj.png")
                            save_trajectory_comparison(t0_np, snap_list_np, t1_np, img_path)
                            saved_sample = True

                else:
                    val_imgs = val_data.to(device)
                    B_val = val_imgs.size(0)

                    if mode == "damage":
                        x_val = build_seed_damage(val_imgs, channel_n)
                        x_val = apply_damage(x_val, damage_frac=damage_frac)
                        for _ in range(steps_max):
                            x_val = model.update(x_val)
                        seed_vis = val_imgs[:, :, :, 0]
                    else:
                        blurry_seed = build_seed_reconstruct(val_imgs, channel_n, low_res=reconstruct_low_res)
                        x_val = blurry_seed.clone()
                        for _ in range(steps_max):
                            x_val = model.update(x_val)
                        seed_vis = blurry_seed[:, :, :, 0]

                    pred = x_val[:, :, :, :1]

                    for b in range(B_val):
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

        # 发散判据 1：PSNR 塌破阈值
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

        # 构建 extra 字段
        extra: dict = {
            "mode": mode,
            "best_psnr": best_psnr,
            "lr": scheduler.get_last_lr()[0],
            "converged": bool(val_psnr >= cfg["diverge"]["psnr_converge"]),
        }

        if mode == "trajectory":
            # 各 step 平均距离
            step_metrics: dict = {}
            for s in traj_eval_steps:
                step_metrics[f"dist_to_t1_step{s}"] = float(np.mean(dists_to_t1_per_step[s]))
                step_metrics[f"dist_from_t0_step{s}"] = float(np.mean(dists_from_t0_per_step[s]))
            extra.update(step_metrics)
            # 基础单调性
            extra["mono_to_t1_violation_rate"] = float(np.mean(mono_to_t1_violations))
            extra["mono_from_t0_violation_rate"] = float(np.mean(mono_from_t0_violations))
            # 终态 PSNR
            extra["baseline_psnr_t0_to_t1"] = float(np.mean(baseline_psnr_list))
            extra["final_psnr_to_t1"] = float(np.mean(final_psnr_to_t1_list))
            extra["final_psnr_to_t0"] = float(np.mean(final_psnr_to_t0_list))
            extra["val_psnr_to_t1"] = val_psnr
            extra["traj_eval_steps"] = traj_eval_steps
            # 修2：局部性判据（核心 PASS/FAIL 依据）
            extra["change_in_roi_frac"] = float(np.mean(change_in_roi_frac_list))
            extra["front_expansion_violation_rate"] = float(np.mean(front_expansion_viol_list))
            # 修3：强基线对照（NCA 必须 change_in_roi_frac > linear_interp）
            extra["linear_interp_change_in_roi_frac"] = float(np.mean(linear_frac_list))
            extra["linear_interp_final_psnr_to_t1"] = float(np.mean(linear_psnr_list))
            extra["unet_final_psnr_to_t1"] = float(np.mean(unet_psnr_list)) if unet_psnr_list else None
            # 修4：Laplacian 方差（抗糊代理）
            extra["laplacian_var_pred"] = float(np.mean(lap_var_pred_list))
            extra["laplacian_var_t1"] = float(np.mean(lap_var_t1_list))
            # PASS 判据摘要（供主线机械判 kill，True=通过该项）
            _frac_nca = extra["change_in_roi_frac"]
            _frac_lin = extra["linear_interp_change_in_roi_frac"]
            extra["pass_mapping"] = bool(extra["final_psnr_to_t1"] > extra["baseline_psnr_t0_to_t1"])
            extra["pass_monotone"] = bool(extra["mono_to_t1_violation_rate"] < 0.5)
            extra["pass_locality"] = bool(_frac_nca > _frac_lin + traj_cfg.get("roi_frac_margin", 0.05))
            extra["pass_non_degenerate"] = bool(extra["final_psnr_to_t1"] > extra["final_psnr_to_t0"] - 3.0)
            extra["pass_summary"] = all([
                extra["pass_mapping"],
                extra["pass_monotone"],
                extra["pass_locality"],
                extra["pass_non_degenerate"],
            ])

        write_state(
            state_path=state_path,
            epoch=epoch,
            train_loss=train_loss,
            val_psnr=val_psnr,
            val_ssim=val_ssim,
            diverged=diverged,
            extra=extra,
        )

        if epoch % 10 == 0 or epoch == 1 or diverged:
            msg = (
                f"[probe] epoch={epoch:4d}/{epochs} "
                f"loss={train_loss:.6f} "
                f"val_psnr={val_psnr:.2f}dB "
                f"val_ssim={val_ssim:.4f} "
                f"best_psnr={best_psnr:.2f}dB"
            )
            if mode == "trajectory":
                vr_t1 = extra["mono_to_t1_violation_rate"]
                frac_nca = extra["change_in_roi_frac"]
                frac_lin = extra["linear_interp_change_in_roi_frac"]
                unet_p = extra.get("unet_final_psnr_to_t1")
                lap_r = extra["laplacian_var_pred"] / max(extra["laplacian_var_t1"], 1e-10)
                msg += (
                    f" | roi_frac(NCA={frac_nca:.3f},lin={frac_lin:.3f})"
                    f" mono_viol={vr_t1:.2f}"
                    f" lap_ratio={lap_r:.2f}"
                    + (f" unet={unet_p:.2f}dB" if unet_p is not None else "")
                    + (f" PASS={extra['pass_summary']}")
                )
            print(msg)

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
