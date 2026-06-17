"""test_probe_persistence.py
Smoke tests for probe_persistence.py
- shape 对、state.json 生成、两 mode 各 2 epoch 跑通
- 关键反退化断言：恒等模型（fc1 强制 0，delta 恒 0）在两 mode loss 都必须 > 0

Med-NCA Gate 1 / Direction B
不跑实际 NIH 数据（smoke 模式用合成数据，速度快）
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
import torch.nn.functional as F

CODE_DIR = pathlib.Path(__file__).parent
sys.path.insert(0, str(CODE_DIR))

from probe_persistence import (
    NIHNormalDataset,
    PersistenceNCA,
    SamplePool,
    apply_damage,
    build_seed_damage,
    build_seed_reconstruct,
    psnr_numpy,
    ssim_numpy,
    save_comparison,
    write_state,
)


# ==============================================================================
# 辅助：合成 Dataset
# ==============================================================================

class SyntheticDataset(torch.utils.data.Dataset):
    """合成灰度图 Dataset，返回 (H, W, 1) float32 [0,1]。"""

    def __init__(self, n: int = 8, resolution: int = 16) -> None:
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


def make_identity_model(channel_n: int, device: torch.device) -> PersistenceNCA:
    """返回恒等 NCA：fc1 权重强制 0，update 产生 delta=0，输入=输出。"""
    model = PersistenceNCA(channel_n=channel_n, fire_rate=0.5, device=device, hidden_size=32)
    with torch.no_grad():
        model.fc1.weight.zero_()
    return model


# ==============================================================================
# 基础单元测试
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
    assert out.shape == x.shape


def test_identity_nca_produces_zero_delta():
    """恒等模型（fc1=0）的 delta 应为 0，update(x) == x。"""
    device = torch.device("cpu")
    channel_n = 8
    model = make_identity_model(channel_n, device)
    model.eval()
    x = torch.randn(2, 16, 16, channel_n)
    with torch.no_grad():
        out = model.update(x)
    diff = (out - x).abs().max().item()
    assert diff < 1e-5, f"Identity NCA delta should be 0, max diff={diff}"


def test_sample_pool_commit_no_error():
    """SamplePool commit 用 LongTensor index，不报错，形状一致。"""
    device = torch.device("cpu")
    H, W, C = 8, 8, 4
    pool = SamplePool(pool_size=16, h=H, w=W, channel_n=C, device=device)
    batch, indices = pool.sample(batch_size=4, replace=1)
    assert batch.shape == (4, H, W, C)
    pool.commit(batch, indices)


def test_build_seed_damage_shape():
    """build_seed_damage 输出 shape 和可见通道值正确。"""
    B, H, W, C = 2, 16, 16, 8
    img = torch.rand(B, H, W, 1)
    seed = build_seed_damage(img, C)
    assert seed.shape == (B, H, W, C)
    assert torch.allclose(seed[:, :, :, :1], img)
    assert seed[:, :, :, 1:].abs().max().item() < 1e-6


def test_apply_damage_zeros_patch():
    """apply_damage 应在每个样本里抹掉一块区域。"""
    B, H, W, C = 4, 16, 16, 8
    x = torch.ones(B, H, W, C)
    damaged = apply_damage(x, damage_frac=0.5)
    assert damaged.shape == x.shape
    for b in range(B):
        assert damaged[b].min().item() < 0.5, f"Sample {b} not damaged"


def test_build_seed_reconstruct_shape_and_blurry():
    """build_seed_reconstruct 输出 shape 对，可见通道是糊图（不等于原图）。"""
    B, H, W, C = 2, 16, 16, 8
    img = torch.rand(B, H, W, 1)
    seed = build_seed_reconstruct(img, C, low_res=4)
    assert seed.shape == (B, H, W, C)
    diff = (seed[:, :, :, :1] - img).abs().mean().item()
    assert diff > 1e-4, f"Blurry seed should differ from original, diff={diff}"
    assert seed[:, :, :, 1:].abs().max().item() < 1e-6


def test_psnr_ssim_identical():
    img = np.random.rand(64, 64).astype(np.float32)
    assert psnr_numpy(img, img) > 90.0
    assert abs(ssim_numpy(img, img) - 1.0) < 0.01


def test_psnr_ssim_noise():
    rng = np.random.RandomState(0)
    img = rng.rand(64, 64).astype(np.float32)
    noise = rng.rand(64, 64).astype(np.float32)
    assert psnr_numpy(img, noise) < 30.0


def test_write_state(tmp_path):
    """write_state 生成 state.json 并包含必要字段（含 mode）。"""
    state_path = str(tmp_path / "state.json")
    write_state(
        state_path=state_path,
        epoch=5,
        train_loss=0.01,
        val_psnr=22.0,
        val_ssim=0.8,
        diverged=False,
        extra={"mode": "damage", "best_psnr": 22.0, "converged": False},
    )
    assert pathlib.Path(state_path).exists()
    with open(state_path) as f:
        d = json.load(f)
    for key in ("epoch", "train_loss", "val_psnr", "val_ssim", "diverged", "timestamp", "mode"):
        assert key in d, f"Missing key: {key}"
    assert d["epoch"] == 5
    assert d["mode"] == "damage"


def test_save_comparison(tmp_path):
    """save_comparison 生成 [seed|pred|orig] PNG 不报错。"""
    H = 32
    seed_vis = np.random.rand(H, H).astype(np.float32)
    pred = np.random.rand(H, H).astype(np.float32)
    orig = np.random.rand(H, H).astype(np.float32)
    out_path = str(tmp_path / "compare.png")
    save_comparison(seed_vis, pred, orig, out_path)
    assert pathlib.Path(out_path).exists()


# ==============================================================================
# 关键反退化断言：恒等模型在两 mode loss 都必须 > 0
# ==============================================================================

def test_identity_model_damage_loss_nonzero():
    """恒等 NCA（delta=0）在 mode=damage 下 loss 必须 > 0（防退化假 PASS）。

    恒等 NCA 无法填补损伤区，输出 = 已损伤状态，MSE 对原图 > 0。
    """
    device = torch.device("cpu")
    channel_n = 8
    H = 16
    model = make_identity_model(channel_n, device)
    model.eval()

    # 有纹理的原图（不全 0，否则损伤区也是 0，loss 为 0）
    rng = torch.Generator()
    rng.manual_seed(42)
    img = torch.rand(2, H, H, 1, generator=rng)

    with torch.no_grad():
        seed = build_seed_damage(img, channel_n)
        damaged = apply_damage(seed, damage_frac=0.5)
        x_out = damaged.clone()
        for _ in range(4):
            x_out = model.update(x_out)
        loss = F.mse_loss(x_out[:, :, :, :1], img).item()

    print(f"[test] identity NCA damage loss = {loss:.6f}")
    assert loss > 1e-4, (
        f"Identity NCA must have loss > 0 in damage mode (got {loss:.6f}). "
        "Non-zero loss confirms this is a real test, not a degenerate setup."
    )


def test_identity_model_reconstruct_loss_nonzero():
    """恒等 NCA（delta=0）在 mode=reconstruct 下 loss 必须 > 0（防退化假 PASS）。

    恒等 NCA 输出 = 糊图 seed，与原图有明显 MSE > 0。
    """
    device = torch.device("cpu")
    channel_n = 8
    H = 16
    model = make_identity_model(channel_n, device)
    model.eval()

    rng = torch.Generator()
    rng.manual_seed(42)
    img = torch.rand(2, H, H, 1, generator=rng)

    with torch.no_grad():
        seed = build_seed_reconstruct(img, channel_n, low_res=4)
        x_out = seed.clone()
        for _ in range(4):
            x_out = model.update(x_out)
        loss = F.mse_loss(x_out[:, :, :, :1], img).item()

    print(f"[test] identity NCA reconstruct loss = {loss:.6f}")
    assert loss > 1e-4, (
        f"Identity NCA must have loss > 0 in reconstruct mode (got {loss:.6f}). "
        "Non-zero loss confirms blurry seed != original."
    )


# ==============================================================================
# Smoke test：两 mode 各 2 epoch 跑通（合成数据）
# ==============================================================================

def _run_smoke_mode(mode: str, tmp_path: pathlib.Path) -> dict:
    """共用 smoke runner，返回最终 state.json 内容。"""
    from torch.utils.data import DataLoader

    device = torch.device("cpu")
    H = 16
    channel_n = 8
    batch_size = 2
    epochs = 2
    steps_min, steps_max = 4, 8
    state_path = str(tmp_path / f"state_{mode}.json")
    out_dir = tmp_path / mode
    out_dir.mkdir(parents=True, exist_ok=True)

    ds = SyntheticDataset(n=8, resolution=H)
    loader = DataLoader(ds, batch_size=batch_size, shuffle=False, num_workers=0, pin_memory=False)

    model = PersistenceNCA(channel_n=channel_n, fire_rate=0.5, device=device, hidden_size=32)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)

    pool = SamplePool(pool_size=8, h=H, w=H, channel_n=channel_n, device=device)
    init_imgs = torch.stack([ds[i] for i in range(len(ds))], dim=0)
    if mode == "damage":
        pool.seed_from_batch(build_seed_damage(init_imgs, channel_n))
    else:
        pool.seed_from_batch(build_seed_reconstruct(init_imgs, channel_n, low_res=4))

    for epoch in range(1, epochs + 1):
        model.train()
        epoch_losses = []
        for batch_imgs in loader:
            B = batch_imgs.size(0)
            pool_batch, pool_indices = pool.sample(B, replace=1)
            pool_batch = pool_batch[:B].clone()
            pool_indices = pool_indices[:B]

            optimizer.zero_grad()

            if mode == "damage":
                n_r = min(1, B)
                pool_batch[:n_r] = build_seed_damage(batch_imgs[:n_r], channel_n)
                steps_t1 = random.randint(steps_min, steps_max)
                x = pool_batch
                for _ in range(steps_t1):
                    x = model.update(x)
                x = apply_damage(x, damage_frac=0.5)
                steps_t2 = random.randint(steps_min, steps_max)
                for _ in range(steps_t2):
                    x = model.update(x)
                x_out = x
            else:
                n_r = min(1, B)
                pool_batch[:n_r] = build_seed_reconstruct(batch_imgs[:n_r], channel_n, low_res=4)
                steps = random.randint(steps_min, steps_max)
                x_out = pool_batch
                for _ in range(steps):
                    x_out = model.update(x_out)

            loss = F.mse_loss(x_out[:, :, :, :1], batch_imgs[:B])
            loss.backward()
            optimizer.step()
            pool.commit(x_out.detach(), pool_indices)
            epoch_losses.append(loss.item())

            assert x_out.shape == (B, H, H, channel_n), f"x_out shape: {x_out.shape}"

        train_loss = float(np.mean(epoch_losses))
        write_state(
            state_path=state_path,
            epoch=epoch,
            train_loss=train_loss,
            val_psnr=0.0,
            val_ssim=0.0,
            diverged=False,
            extra={"mode": mode, "converged": False},
        )

    assert pathlib.Path(state_path).exists()
    with open(state_path) as f:
        d = json.load(f)
    assert d["epoch"] == 2
    assert d["mode"] == mode
    return d


def test_smoke_damage_2epoch(tmp_path):
    """mode=damage: 2 epoch 合成数据跑通，state.json 生成，shape 对。"""
    d = _run_smoke_mode("damage", tmp_path)
    print(f"[smoke-damage] loss={d['train_loss']:.4f}")
    assert "train_loss" in d and "diverged" in d


def test_smoke_reconstruct_2epoch(tmp_path):
    """mode=reconstruct: 2 epoch 合成数据跑通，state.json 生成，shape 对。"""
    d = _run_smoke_mode("reconstruct", tmp_path)
    print(f"[smoke-reconstruct] loss={d['train_loss']:.4f}")
    assert "train_loss" in d and "diverged" in d
