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
    NIHPairDataset,
    PersistenceNCA,
    SmallUNet,
    SamplePool,
    apply_damage,
    build_seed_damage,
    build_seed_reconstruct,
    build_seed_trajectory,
    psnr_numpy,
    ssim_numpy,
    save_comparison,
    save_trajectory_comparison,
    compute_monotonicity_violation_rate,
    compute_roi_mask,
    compute_change_in_roi_frac,
    compute_front_expansion_violation_rate,
    compute_laplacian_variance,
    compute_linear_interp_metrics,
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


# ==============================================================================
# trajectory mode 新增测试
# ==============================================================================

class SyntheticPairDataset(torch.utils.data.Dataset):
    """合成纵向对 Dataset，返回 (t0, t1) 各 (H, W, 1) float32 [0,1]。

    t0 和 t1 有明显差异（t1 = t0 + gaussian noise clip），模拟疾病变化。
    """

    def __init__(self, n: int = 8, resolution: int = 16) -> None:
        self.n = n
        self.resolution = resolution
        rng = np.random.RandomState(7)
        self._t0 = [
            torch.from_numpy(rng.rand(resolution, resolution, 1).astype(np.float32))
            for _ in range(n)
        ]
        # t1 = t0 + 0.3*noise，模拟有差异
        self._t1 = [
            torch.clamp(t0 + 0.3 * torch.from_numpy(rng.randn(resolution, resolution, 1).astype(np.float32)), 0.0, 1.0)
            for t0 in self._t0
        ]

    def __len__(self) -> int:
        return self.n

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor]:
        return self._t0[idx], self._t1[idx]


def test_build_seed_trajectory_shape_and_visible():
    """build_seed_trajectory: shape 对，可见通道 = t0，隐藏通道 = 0。"""
    B, H, W, C = 3, 16, 16, 8
    t0 = torch.rand(B, H, W, 1)
    seed = build_seed_trajectory(t0, C)
    assert seed.shape == (B, H, W, C), f"Expected {(B,H,W,C)}, got {seed.shape}"
    # 可见通道 = t0
    assert torch.allclose(seed[:, :, :, :1], t0), "Visible channel should equal t0"
    # 隐藏通道 = 0
    assert seed[:, :, :, 1:].abs().max().item() < 1e-6, "Hidden channels should be zero"


def test_compute_monotonicity_violation_rate_monotone():
    """单调序列（严格降）=> 违反率 = 0。"""
    # dist_to_t1 严格单调降
    dists = [0.10, 0.08, 0.05, 0.02]
    rate = compute_monotonicity_violation_rate(dists)
    assert rate == 0.0, f"Monotone sequence should have 0 violations, got {rate}"


def test_compute_monotonicity_violation_rate_non_monotone():
    """非单调序列（有反弹）=> 违反率 = 1。"""
    dists = [0.10, 0.08, 0.09, 0.02]   # 0.08 -> 0.09 是反弹
    rate = compute_monotonicity_violation_rate(dists)
    assert rate == 1.0, f"Non-monotone sequence should have violation=1, got {rate}"


def test_save_trajectory_comparison(tmp_path):
    """save_trajectory_comparison 生成 t0|snap...|t1 横拼 PNG 不报错。"""
    H = 32
    t0_np = np.random.rand(H, H).astype(np.float32)
    t1_np = np.random.rand(H, H).astype(np.float32)
    snaps = [np.random.rand(H, H).astype(np.float32) for _ in range(4)]
    out_path = str(tmp_path / "traj.png")
    save_trajectory_comparison(t0_np, snaps, t1_np, out_path)
    assert pathlib.Path(out_path).exists()
    # 检查宽度 = (2 + len(snaps)) * H
    from PIL import Image as PILImage
    img = PILImage.open(out_path)
    assert img.size == ((2 + len(snaps)) * H, H), f"Unexpected size: {img.size}"


def test_identity_model_trajectory_loss_nonzero():
    """恒等 NCA 在 trajectory mode 下 loss 必须 > 0（防退化假 PASS）。

    恒等 NCA：seed=t0，delta=0，输出=t0。
    但 target=t1 != t0（有明显差异），所以 MSE(output, t1) > 0。
    """
    device = torch.device("cpu")
    channel_n = 8
    H = 16
    model = make_identity_model(channel_n, device)
    model.eval()

    rng = torch.Generator()
    rng.manual_seed(13)
    t0 = torch.rand(2, H, H, 1, generator=rng)
    # t1 明显不同（+0.3 保证差异大于阈值）
    t1 = torch.clamp(t0 + 0.3, 0.0, 1.0)

    with torch.no_grad():
        seed = build_seed_trajectory(t0, channel_n)
        x_out = seed.clone()
        for _ in range(4):
            x_out = model.update(x_out)
        loss = torch.nn.functional.mse_loss(x_out[:, :, :, :1], t1).item()

    print(f"[test] identity NCA trajectory loss = {loss:.6f}")
    assert loss > 1e-4, (
        f"Identity NCA must have loss > 0 in trajectory mode (got {loss:.6f}). "
        "Output=t0 but target=t1, so MSE > 0 confirms non-degenerate test."
    )


def test_identity_model_trajectory_dist_to_t1_approx_baseline():
    """恒等 NCA dist_to_t1 at step 64 应 ≈ baseline MSE(t0, t1)。

    恒等 NCA 输出不变（= t0 seed），所以最终态到 t1 的距离
    应约等于 t0 到 t1 的距离（平凡基线）。
    这确保 dist_to_t1 指标有意义：若 NCA 无学习，指标 = baseline。
    """
    device = torch.device("cpu")
    channel_n = 8
    H = 16
    model = make_identity_model(channel_n, device)
    model.eval()

    rng = np.random.RandomState(99)
    t0 = torch.from_numpy(rng.rand(4, H, H, 1).astype(np.float32))
    noise = torch.from_numpy((rng.randn(4, H, H, 1) * 0.3).astype(np.float32))
    t1 = torch.clamp(t0 + noise, 0.0, 1.0)

    with torch.no_grad():
        seed = build_seed_trajectory(t0, channel_n)
        x = seed.clone()
        for _ in range(64):
            x = model.update(x)
        pred = x[:, :, :, :1]

    # dist_to_t1 from NCA output
    dist_nca = float(torch.mean((pred - t1) ** 2).item())
    # baseline: dist_to_t1 from t0 itself
    dist_baseline = float(torch.mean((t0 - t1) ** 2).item())

    print(f"[test] identity NCA dist_to_t1={dist_nca:.6f}  baseline={dist_baseline:.6f}")
    # 恒等 NCA 输出 = 输入 t0，所以两个距离应该非常接近（误差 < 1e-5）
    assert abs(dist_nca - dist_baseline) < 1e-5, (
        f"Identity NCA output=t0, so dist_to_t1 should ≈ baseline. "
        f"Got dist_nca={dist_nca:.6f}, baseline={dist_baseline:.6f}"
    )


def test_smoke_trajectory_2epoch(tmp_path):
    """mode=trajectory: 2 epoch 合成数据跑通，state.json 含 trajectory 字段。"""
    import torch.nn.functional as F
    from torch.utils.data import DataLoader

    device = torch.device("cpu")
    H = 16
    channel_n = 8
    batch_size = 2
    epochs = 2
    steps_min, steps_max = 4, 8
    traj_eval_steps = [4, 8]
    state_path = str(tmp_path / "state_trajectory.json")
    out_dir = tmp_path / "trajectory"
    traj_out_dir = out_dir / "trajectory"
    out_dir.mkdir(parents=True, exist_ok=True)
    traj_out_dir.mkdir(parents=True, exist_ok=True)

    ds = SyntheticPairDataset(n=8, resolution=H)
    loader = DataLoader(ds, batch_size=batch_size, shuffle=False, num_workers=0, pin_memory=False)

    model = PersistenceNCA(channel_n=channel_n, fire_rate=0.5, device=device, hidden_size=32)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)

    pool = SamplePool(pool_size=8, h=H, w=H, channel_n=channel_n, device=device)
    t0_init = torch.stack([ds[i][0] for i in range(len(ds))], dim=0)
    pool.seed_from_batch(build_seed_trajectory(t0_init, channel_n))

    for epoch in range(1, epochs + 1):
        model.train()
        epoch_losses = []
        for t0_batch, t1_batch in loader:
            B = t0_batch.size(0)
            pool_batch, pool_indices = pool.sample(B, replace=1)
            pool_batch = pool_batch[:B].clone()
            pool_indices = pool_indices[:B]

            optimizer.zero_grad()
            n_r = min(1, B)
            fresh_seed = build_seed_trajectory(t0_batch[:n_r], channel_n)
            pool_batch[:n_r] = fresh_seed

            steps = random.randint(steps_min, steps_max)
            x_out = pool_batch
            for _ in range(steps):
                x_out = model.update(x_out)

            loss = F.mse_loss(x_out[:, :, :, :1], t1_batch[:B])
            loss.backward()
            optimizer.step()
            pool.commit(x_out.detach(), pool_indices)
            epoch_losses.append(loss.item())
            assert x_out.shape == (B, H, H, channel_n), f"x_out shape: {x_out.shape}"

        # val + 中间态指标（简化版）
        model.eval()
        dists_to_t1_per_step = {s: [] for s in traj_eval_steps}
        dists_from_t0_per_step = {s: [] for s in traj_eval_steps}
        mono_to_t1_violations = []
        mono_from_t0_violations = []
        baseline_psnr_list = []
        final_psnr_to_t1_list = []
        final_psnr_to_t0_list = []
        psnr_list = []
        ssim_list = []

        with torch.no_grad():
            for t0_val, t1_val in loader:
                B_val = t0_val.size(0)
                max_step = max(traj_eval_steps)
                x_eval = build_seed_trajectory(t0_val, channel_n)
                snapshots = {}
                for s in range(1, max_step + 1):
                    x_eval = model.update(x_eval)
                    if s in traj_eval_steps:
                        snapshots[s] = x_eval[:, :, :, :1].clone()

                pred_final = snapshots[max(traj_eval_steps)]
                for b in range(B_val):
                    t0_np = t0_val[b, :, :, 0].numpy()
                    t1_np = t1_val[b, :, :, 0].numpy()
                    baseline_psnr_list.append(psnr_numpy(t0_np, t1_np))
                    sample_d_t1, sample_d_t0 = [], []
                    for s in traj_eval_steps:
                        snap_np = snapshots[s][b, :, :, 0].numpy()
                        d_t1 = float(np.mean((snap_np - t1_np) ** 2))
                        d_t0 = float(np.mean((snap_np - t0_np) ** 2))
                        dists_to_t1_per_step[s].append(d_t1)
                        dists_from_t0_per_step[s].append(d_t0)
                        sample_d_t1.append(d_t1)
                        sample_d_t0.append(d_t0)
                    mono_to_t1_violations.append(compute_monotonicity_violation_rate(sample_d_t1))
                    mono_from_t0_violations.append(compute_monotonicity_violation_rate([-d for d in sample_d_t0]))
                    pred_np = pred_final[b, :, :, 0].numpy()
                    final_psnr_to_t1_list.append(psnr_numpy(pred_np, t1_np))
                    final_psnr_to_t0_list.append(psnr_numpy(pred_np, t0_np))
                    psnr_list.append(psnr_numpy(pred_np, t1_np))
                    ssim_list.append(ssim_numpy(pred_np, t1_np))

        train_loss = float(np.mean(epoch_losses))
        # 修2/3/4：smoke 测试用简化计算（合成数据无真实 ROI，用占位值验证字段存在）
        # 实际这些指标在真实 train() 循环中由对应函数计算
        _roi_dummy = np.ones((H, H), dtype=bool)  # dummy ROI（全图）for smoke
        _t0_dummy = ds[0][0][:, :, 0].numpy()
        _t1_dummy = ds[0][1][:, :, 0].numpy()
        _lin = compute_linear_interp_metrics(_t0_dummy, _t1_dummy, traj_eval_steps, _roi_dummy)
        extra = {
            "mode": "trajectory",
            "converged": False,
            "mono_to_t1_violation_rate": float(np.mean(mono_to_t1_violations)),
            "mono_from_t0_violation_rate": float(np.mean(mono_from_t0_violations)),
            "baseline_psnr_t0_to_t1": float(np.mean(baseline_psnr_list)),
            "final_psnr_to_t1": float(np.mean(final_psnr_to_t1_list)),
            "final_psnr_to_t0": float(np.mean(final_psnr_to_t0_list)),
            "traj_eval_steps": traj_eval_steps,
            # 修2
            "change_in_roi_frac": 0.0,
            "front_expansion_violation_rate": 0.0,
            # 修3
            "linear_interp_change_in_roi_frac": _lin["linear_change_in_roi_frac_mean"],
            "linear_interp_final_psnr_to_t1": _lin["linear_final_psnr_to_t1"],
            "unet_final_psnr_to_t1": None,
            # 修4
            "laplacian_var_pred": 0.0,
            "laplacian_var_t1": 0.0,
            # pass flags（smoke 不判对错，只验字段存在）
            "pass_mapping": False,
            "pass_monotone": False,
            "pass_locality": False,
            "pass_non_degenerate": False,
            "pass_summary": False,
        }
        write_state(
            state_path=state_path,
            epoch=epoch,
            train_loss=train_loss,
            val_psnr=float(np.mean(psnr_list)),
            val_ssim=float(np.mean(ssim_list)),
            diverged=False,
            extra=extra,
        )

    assert pathlib.Path(state_path).exists()
    with open(state_path) as f:
        d = json.load(f)
    assert d["epoch"] == 2
    assert d["mode"] == "trajectory"
    # 必须包含 trajectory 专有字段（原有 + skeptic 修2/3/4 新增）
    for key in (
        "mono_to_t1_violation_rate",
        "mono_from_t0_violation_rate",
        "baseline_psnr_t0_to_t1",
        "final_psnr_to_t1",
        "final_psnr_to_t0",
        "traj_eval_steps",
        "change_in_roi_frac",
        "front_expansion_violation_rate",
        "linear_interp_change_in_roi_frac",
        "linear_interp_final_psnr_to_t1",
        "laplacian_var_pred",
        "laplacian_var_t1",
        "pass_mapping",
        "pass_monotone",
        "pass_locality",
        "pass_non_degenerate",
        "pass_summary",
    ):
        assert key in d, f"Missing trajectory key: {key}"
    # baseline PSNR 应该是有限正数
    assert np.isfinite(d["baseline_psnr_t0_to_t1"]) and d["baseline_psnr_t0_to_t1"] > 0
    print(
        f"[smoke-trajectory] loss={d['train_loss']:.4f} "
        f"baseline_psnr={d['baseline_psnr_t0_to_t1']:.2f}dB "
        f"mono_viol_t1={d['mono_to_t1_violation_rate']:.2f}"
    )


# ==============================================================================
# skeptic 修2/3/4 新增测试
# ==============================================================================

def test_compute_roi_mask_basic():
    """ROI mask：差异集中区域应被标为 True，无差异区域 False。"""
    H = 32
    t0 = np.zeros((H, H), dtype=np.float32)
    t1 = np.zeros((H, H), dtype=np.float32)
    # 右下角 8x8 区域有差异
    t1[24:32, 24:32] = 0.8
    mask = compute_roi_mask(t0, t1, smooth_sigma=1.0, threshold=0.05)
    assert mask.shape == (H, H)
    # 右下角应被标记
    assert mask[28, 28], "Lesion area should be in ROI mask"
    # 左上角应不在 ROI
    assert not mask[0, 0], "Background should not be in ROI mask"


def test_change_in_roi_frac_concentrated():
    """变化集中在 ROI 内 => frac 高（接近 1）。"""
    H = 16
    roi = np.zeros((H, H), dtype=bool)
    roi[4:12, 4:12] = True    # 中央 8x8 是 ROI
    # snap_a 全零，snap_b 只在 ROI 内有变化
    snap_a = np.zeros((H, H), dtype=np.float32)
    snap_b = np.zeros((H, H), dtype=np.float32)
    snap_b[4:12, 4:12] = 0.5  # 变化全在 ROI 内
    frac = compute_change_in_roi_frac(snap_a, snap_b, roi)
    assert frac > 0.95, f"ROI-concentrated change should give frac≈1, got {frac:.4f}"


def test_change_in_roi_frac_global():
    """变化均匀铺满全图 => frac ≈ ROI 面积比例（低，约 25%）。"""
    H = 16
    roi = np.zeros((H, H), dtype=bool)
    roi[4:12, 4:12] = True    # 8x8 / 16x16 = 25%
    snap_a = np.zeros((H, H), dtype=np.float32)
    snap_b = np.ones((H, H), dtype=np.float32) * 0.5   # 全图均匀变化
    frac = compute_change_in_roi_frac(snap_a, snap_b, roi)
    # 期望 ≈ 0.25（ROI 面积比），由于均匀能量分布
    assert frac < 0.5, f"Global change should give low frac (≈0.25), got {frac:.4f}"
    print(f"[test] global change frac={frac:.4f} (expected ≈0.25)")


def test_compute_laplacian_variance_blurry_vs_sharp():
    """清晰图 Laplacian 方差 > 糊图（高频能量代理）。"""
    rng = np.random.RandomState(42)
    # 清晰噪声图（高频丰富）
    sharp = rng.rand(64, 64).astype(np.float32)
    # 糊图：取均值平滑（高频极低）
    blurry = np.ones((64, 64), dtype=np.float32) * 0.5
    lap_sharp = compute_laplacian_variance(sharp)
    lap_blurry = compute_laplacian_variance(blurry)
    print(f"[test] lap_var sharp={lap_sharp:.6f} blurry={lap_blurry:.8f}")
    assert lap_sharp > lap_blurry * 10, (
        f"Sharp image should have much higher Laplacian var than blurry. "
        f"Got sharp={lap_sharp:.6f}, blurry={lap_blurry:.8f}"
    )


def test_compute_linear_interp_metrics():
    """线性插值基线：final_psnr_to_t1 应为高值（因为 step=T 时 = t1），frac 约 ROI 面积比。"""
    H = 32
    rng = np.random.RandomState(7)
    t0 = rng.rand(H, H).astype(np.float32)
    t1 = np.clip(t0 + 0.3 * rng.randn(H, H).astype(np.float32), 0.0, 1.0)
    eval_steps = [8, 16, 24, 32]
    roi = (np.abs(t1 - t0) > 0.1)
    metrics = compute_linear_interp_metrics(t0, t1, eval_steps, roi)
    assert "linear_final_psnr_to_t1" in metrics
    assert "linear_change_in_roi_frac_mean" in metrics
    assert "linear_mono_to_t1_violation_rate" in metrics
    # 线性插值在最后一步 = t1，PSNR 应该非常高
    assert metrics["linear_final_psnr_to_t1"] > 80.0, (
        f"Linear interp at step T should equal t1, PSNR should be huge. "
        f"Got {metrics['linear_final_psnr_to_t1']:.2f}dB"
    )
    # 线性插值单调违反率应为 0（严格单调降）
    assert metrics["linear_mono_to_t1_violation_rate"] == 0.0, (
        f"Linear interp should be monotone, violation={metrics['linear_mono_to_t1_violation_rate']}"
    )
    print(f"[test] linear_interp: psnr={metrics['linear_final_psnr_to_t1']:.1f}dB "
          f"frac={metrics['linear_change_in_roi_frac_mean']:.4f} "
          f"mono_viol={metrics['linear_mono_to_t1_violation_rate']:.2f}")


def test_small_unet_forward_shape():
    """SmallUNet forward shape 正确，输出 [0,1]。"""
    device = torch.device("cpu")
    model = SmallUNet(base_ch=8).to(device)
    x = torch.rand(2, 1, 32, 32)
    with torch.no_grad():
        out = model(x)
    assert out.shape == (2, 1, 32, 32), f"Expected (2,1,32,32), got {out.shape}"
    assert out.min().item() >= 0.0 and out.max().item() <= 1.0, "Output should be [0,1]"


def test_nihpairdataset_same_vp_filter(tmp_path):
    """NIHPairDataset: require_same_view=True 过滤生效（构造小 mock CSV 测试）。

    3 个患者：P1/P3 同 VP（保留），P2 不同 VP（丢弃）。
    val_split=0.3 -> 1 pid 进 val，2 pid 进 train。
    验证：总计 2 对保留（P1+P3），P2 的不同VP对被丢弃。
    """
    import csv as csv_mod
    from PIL import Image as PILImg

    mock_csv = tmp_path / "mock_meta.csv"
    img_dir = tmp_path / "imgs"
    img_dir.mkdir()

    fnames = [
        "p1_t0.png", "p1_t1_pa.png",
        "p2_t0.png", "p2_t1_ap.png",
        "p3_t0.png", "p3_t1_pa.png",
    ]
    for fn in fnames:
        PILImg.fromarray(np.zeros((32, 32), dtype=np.uint8)).save(str(img_dir / fn))

    rows = [
        {"Image Index": "p1_t0.png",   "Finding Labels": "No Finding", "Patient ID": "P1",
         "Follow-up #": "0", "View Position": "PA"},
        {"Image Index": "p1_t1_pa.png", "Finding Labels": "Nodule",    "Patient ID": "P1",
         "Follow-up #": "1", "View Position": "PA"},   # 同 VP -> 保留
        {"Image Index": "p2_t0.png",   "Finding Labels": "No Finding", "Patient ID": "P2",
         "Follow-up #": "0", "View Position": "PA"},
        {"Image Index": "p2_t1_ap.png", "Finding Labels": "Nodule",    "Patient ID": "P2",
         "Follow-up #": "1", "View Position": "AP"},   # 不同 VP -> 丢弃
        {"Image Index": "p3_t0.png",   "Finding Labels": "No Finding", "Patient ID": "P3",
         "Follow-up #": "0", "View Position": "PA"},
        {"Image Index": "p3_t1_pa.png", "Finding Labels": "Nodule",    "Patient ID": "P3",
         "Follow-up #": "1", "View Position": "PA"},   # 同 VP -> 保留
    ]
    with open(str(mock_csv), "w", newline="", encoding="utf-8") as f:
        writer = csv_mod.DictWriter(
            f, fieldnames=["Image Index", "Finding Labels", "Patient ID",
                           "Follow-up #", "View Position"]
        )
        writer.writeheader()
        writer.writerows(rows)

    # require_same_view=True 应只保留 P1 和 P3（共 2 对）
    # val_split=0.3 -> val_n_pids=max(1,int(2*0.3))=1，train 1 pid，val 1 pid
    ds_train = NIHPairDataset(
        img_dir=str(img_dir),
        csv_path=str(mock_csv),
        resolution=16,
        seed=42,
        val_split=0.3,
        split="train",
        finding="Nodule",
        require_same_view=True,
    )
    ds_val = NIHPairDataset(
        img_dir=str(img_dir),
        csv_path=str(mock_csv),
        resolution=16,
        seed=42,
        val_split=0.3,
        split="val",
        finding="Nodule",
        require_same_view=True,
    )
    # same_vp_pairs = 2（P1,P3），total_before_vp = 3（P1,P2,P3）
    # train+val 加起来应该是 2（P2 的对被丢弃）
    total = len(ds_train.pairs) + len(ds_val.pairs)
    assert total == 2, f"Expected 2 same-VP pairs (P1+P3), got {total}"
    # val+train 各 1 pair（2 pids，0.3 val_split -> 1 val pid）
    assert len(ds_val.pairs) == 1 and len(ds_train.pairs) == 1, (
        f"Expected 1 train + 1 val, got train={len(ds_train.pairs)} val={len(ds_val.pairs)}"
    )
    t0_img, t1_img = ds_train[0]
    assert t0_img.shape == (16, 16, 1), f"t0 shape: {t0_img.shape}"
    assert t1_img.shape == (16, 16, 1), f"t1 shape: {t1_img.shape}"


