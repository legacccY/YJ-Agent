"""test_probe_persistence.py
Smoke test for probe_persistence.py
- 1 张图，2 epoch，跑通不报错
- state.json 生成且包含必要字段
- tensor shape 对

Med-NCA Gate 1 / Direction B
不跑实际 NIH 数据（smoke 模式用合成数据，速度快，不依赖数据集路径存在）
"""

from __future__ import annotations

import json
import pathlib
import random
import sys
import tempfile

import numpy as np
import pytest
import torch

# 把 code 目录加入 path
CODE_DIR = pathlib.Path(__file__).parent
sys.path.insert(0, str(CODE_DIR))

from probe_persistence import (
    NIHNormalDataset,
    PersistenceNCA,
    SamplePool,
    psnr_numpy,
    ssim_numpy,
    save_comparison,
    write_state,
)


# ==============================================================================
# 辅助：合成 Dataset（不依赖真实数据路径）
# ==============================================================================

class SyntheticDataset(torch.utils.data.Dataset):
    """合成灰度图 Dataset，返回 (H, W, 1) float32 [0,1]。"""

    def __init__(self, n: int = 4, resolution: int = 16) -> None:
        self.n = n
        self.resolution = resolution
        rng = np.random.RandomState(42)
        self._data = [
            torch.from_numpy(rng.rand(resolution, resolution, 1).astype(np.float32))
            for _ in range(n)
        ]

    def __len__(self) -> int:
        return self.n

    def __getitem__(self, idx: int) -> torch.Tensor:
        return self._data[idx]


# ==============================================================================
# Tests
# ==============================================================================

def test_persistence_nca_forward_shape():
    """NCA forward 输出 shape 正确，layout (B, H, W, C)。"""
    device = torch.device("cpu")
    H, W, channel_n = 16, 16, 8
    model = PersistenceNCA(channel_n=channel_n, fire_rate=0.5, device=device, hidden_size=32)
    x = torch.zeros(2, H, W, channel_n)
    out = model.forward(x, steps=4)
    assert out.shape == (2, H, W, channel_n), f"Expected (2,{H},{W},{channel_n}), got {out.shape}"


def test_persistence_nca_update_shape():
    """NCA update 单步 shape 不变。"""
    device = torch.device("cpu")
    H, W, channel_n = 8, 8, 4
    model = PersistenceNCA(channel_n=channel_n, fire_rate=0.5, device=device, hidden_size=16)
    x = torch.randn(1, H, W, channel_n)
    out = model.update(x)
    assert out.shape == x.shape, f"Shape mismatch: {out.shape} vs {x.shape}"


def test_sample_pool_sample_commit():
    """SamplePool sample/commit 不报错，形状一致。"""
    device = torch.device("cpu")
    H, W, C = 8, 8, 4
    pool = SamplePool(pool_size=16, h=H, w=W, channel_n=C, device=device)
    batch, indices = pool.sample(batch_size=4, replace=1)
    assert batch.shape == (4, H, W, C)
    assert len(indices) == 4
    # 写回
    pool.commit(batch, indices)


def test_psnr_ssim_identical():
    """相同图像 PSNR 应极高，SSIM 应约为 1.0。"""
    img = np.random.rand(64, 64).astype(np.float32)
    p = psnr_numpy(img, img)
    s = ssim_numpy(img, img)
    assert p > 90.0, f"PSNR of identical images should be >90, got {p}"
    assert abs(s - 1.0) < 0.01, f"SSIM of identical images should be ~1.0, got {s}"


def test_psnr_ssim_noise():
    """完全噪声 vs 原图 PSNR 应低。"""
    rng = np.random.RandomState(0)
    img = rng.rand(64, 64).astype(np.float32)
    noise = rng.rand(64, 64).astype(np.float32)
    p = psnr_numpy(img, noise)
    assert p < 30.0, f"PSNR of random noise should be <30, got {p}"


def test_write_state(tmp_path):
    """write_state 生成 state.json 并包含必要字段。"""
    state_path = str(tmp_path / "state.json")
    write_state(
        state_path=state_path,
        epoch=5,
        train_loss=0.01,
        val_psnr=22.0,
        val_ssim=0.8,
        diverged=False,
        extra={"best_psnr": 22.0, "converged": False},
    )
    assert pathlib.Path(state_path).exists(), "state.json not created"
    with open(state_path, "r") as f:
        d = json.load(f)
    for key in ("epoch", "train_loss", "val_psnr", "val_ssim", "diverged", "timestamp"):
        assert key in d, f"Missing key in state.json: {key}"
    assert d["epoch"] == 5
    assert d["diverged"] is False


def test_save_comparison(tmp_path):
    """save_comparison 生成 PNG 文件不报错。"""
    H = 32
    orig = np.random.rand(H, H).astype(np.float32)
    pred = np.random.rand(H, H).astype(np.float32)
    out_path = str(tmp_path / "compare.png")
    save_comparison(orig, pred, out_path, epoch=1)
    assert pathlib.Path(out_path).exists(), "Compare PNG not created"


def test_smoke_2epoch(tmp_path):
    """Smoke test: 2 epoch 合成数据跑通，state.json 生成，shape 对，不报错。

    不依赖真实 NIH 数据路径。用 SyntheticDataset 替换。
    """
    import torch.nn.functional as F
    from torch.utils.data import DataLoader

    device = torch.device("cpu")
    H = 16
    channel_n = 8
    batch_size = 2
    epochs = 2
    steps_min, steps_max = 4, 8
    state_path = str(tmp_path / "state.json")
    out_dir = tmp_path

    ds = SyntheticDataset(n=4, resolution=H)
    loader = DataLoader(ds, batch_size=batch_size, shuffle=False, num_workers=0, pin_memory=False)

    model = PersistenceNCA(channel_n=channel_n, fire_rate=0.5, device=device, hidden_size=32)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)

    pool = SamplePool(pool_size=8, h=H, w=H, channel_n=channel_n, device=device)
    pool_init = [ds[i].to(device) for i in range(len(ds))]
    pool.seed(torch.stack(pool_init, dim=0))

    best_psnr = -float("inf")

    for epoch in range(1, epochs + 1):
        model.train()
        epoch_losses = []

        for batch_imgs in loader:
            batch_imgs = batch_imgs.to(device)
            B = batch_imgs.size(0)
            actual_B = min(B, 8)
            pool_batch, pool_indices = pool.sample(actual_B, replace=1)
            pool_batch = pool_batch[:B].clone()
            pool_indices = pool_indices[:B]
            pool_batch[:, :, :, :1] = batch_imgs[:B]

            steps = random.randint(steps_min, steps_max)
            optimizer.zero_grad()

            x_out = pool_batch
            for _ in range(steps):
                x_out = model.update(x_out)

            loss = F.mse_loss(x_out[:, :, :, :1], batch_imgs[:B])
            loss.backward()
            optimizer.step()
            pool.commit(x_out, pool_indices)
            epoch_losses.append(loss.item())

        train_loss = float(np.mean(epoch_losses))

        # val
        psnr_list = []
        ssim_list = []
        model.eval()
        with torch.no_grad():
            for val_imgs in loader:
                val_imgs = val_imgs.to(device)
                B = val_imgs.size(0)
                x_val = torch.zeros(B, H, H, channel_n, device=device)
                x_val[:, :, :, :1] = val_imgs
                for _ in range(steps_max):
                    x_val = model.update(x_val)
                pred = x_val[:, :, :, :1]
                for b in range(B):
                    psnr_list.append(psnr_numpy(pred[b, :, :, 0].numpy(), val_imgs[b, :, :, 0].numpy()))
                    ssim_list.append(ssim_numpy(pred[b, :, :, 0].numpy(), val_imgs[b, :, :, 0].numpy()))

        val_psnr = float(np.mean(psnr_list))
        val_ssim = float(np.mean(ssim_list))
        if val_psnr > best_psnr:
            best_psnr = val_psnr

        write_state(
            state_path=state_path,
            epoch=epoch,
            train_loss=train_loss,
            val_psnr=val_psnr,
            val_ssim=val_ssim,
            diverged=False,
            extra={"best_psnr": best_psnr, "converged": False},
        )

        # shape 检查
        assert x_out.shape == (B, H, H, channel_n), f"x_out shape wrong: {x_out.shape}"
        assert pred.shape == (B, H, H, 1), f"pred shape wrong: {pred.shape}"

    # 验证 state.json
    assert pathlib.Path(state_path).exists(), "state.json not created after 2 epochs"
    with open(state_path) as f:
        d = json.load(f)
    assert d["epoch"] == 2, f"Expected epoch=2 in state.json, got {d['epoch']}"
    assert "train_loss" in d
    assert "val_psnr" in d
    assert "val_ssim" in d
    assert "diverged" in d

    print(f"[smoke] PASSED: loss={d['train_loss']:.4f} psnr={d['val_psnr']:.2f}dB ssim={d['val_ssim']:.4f}")
