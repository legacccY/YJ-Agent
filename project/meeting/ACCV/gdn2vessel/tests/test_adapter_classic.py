"""
test_adapter_classic.py — pytest for FR-UNet and CS-Net adapters.

覆盖:
  1. 注册: @register 后 fr_unet / cs_net 均出现在 MODEL_REGISTRY
  2. FR-UNet build_model 输出正确 shape (B,1,H,W)（patch 输入）
  3. CS-Net build_model 输出正确 shape (B,1,H,W)（全图 RGB 输入）
  4. FR-UNet forward_adapt 滑窗推理在合成全图 (1,1,96,96) 上拼回全图 shape 正确
  5. CS-Net forward_adapt 全图推理输出 (B,1,H,W) logits shape 正确
  6. FR-UNet forward_adapt 输出 shape 与输入 (B,1,H,W) 严格相同（含非整数倍尺寸）
  7. preprocess_cfg 返回必要字段（channels / input_mode / patch_size / clahe）
  8. build_optimizer / build_scheduler 类型验证
  9. validate_attrs 通过（name/kind/source_repo/env_tag 均正确）
 10. build_loss 可调用（callable）并返回合理标量

Windows 规范:
  - num_workers=0 (DataLoader 未用, 但声明合规)
  - 无 scipy.stats
  - 无 multiprocessing
  - 路径用 pathlib.Path / 绝对路径
  - if __name__ == '__main__' guard

设计原则:
  - 全 CPU 测试，无需 GPU（CI 无卡场景可用）
  - 不依赖真实数据集，完全合成小张量
  - 每个 test 独立，无共享副作用
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import numpy as np
import pytest
import torch

# --------------------------------------------------------------------------- #
#  sys.path 设置
# --------------------------------------------------------------------------- #

_repo_root = Path(__file__).parent.parent
_src_dir = _repo_root / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))


# --------------------------------------------------------------------------- #
#  Mock FLA（同 test_baseline_harness.py 策略，避免无 FLA 环境炸）
# --------------------------------------------------------------------------- #

def _mock_fla() -> None:
    if "fla" in sys.modules:
        return
    fake_fla = types.ModuleType("fla")
    fake_ops = types.ModuleType("fla.ops")
    fake_gdr = types.ModuleType("fla.ops.gated_delta_rule")
    fake_naive = types.ModuleType("fla.ops.gated_delta_rule.naive")
    fake_chunk = types.ModuleType("fla.ops.gated_delta_rule.chunk")

    def _fake_fn(q, k, v, beta, g):
        return v.clone(), None

    fake_naive.naive_chunk_gated_delta_rule = _fake_fn
    fake_chunk.chunk_gated_delta_rule = _fake_fn

    sys.modules.setdefault("fla", fake_fla)
    sys.modules.setdefault("fla.ops", fake_ops)
    sys.modules.setdefault("fla.ops.gated_delta_rule", fake_gdr)
    sys.modules.setdefault("fla.ops.gated_delta_rule.naive", fake_naive)
    sys.modules.setdefault("fla.ops.gated_delta_rule.chunk", fake_chunk)


_mock_fla()


# --------------------------------------------------------------------------- #
#  Imports（放在 mock 之后）
# --------------------------------------------------------------------------- #

import baselines  # noqa: E402 — 触发 auto_discover，注册所有 adapters


# --------------------------------------------------------------------------- #
#  Helper: 获取 adapter 实例
# --------------------------------------------------------------------------- #

def _get_frunet():
    from baselines.registry import get_adapter
    return get_adapter("fr_unet")


def _get_csnet():
    from baselines.registry import get_adapter
    return get_adapter("cs_net")


# --------------------------------------------------------------------------- #
#  Test 1: 注册验证
# --------------------------------------------------------------------------- #

class TestRegistration:
    """@register 后两个 adapter 均在 MODEL_REGISTRY 中。"""

    def test_fr_unet_registered(self):
        from baselines.registry import MODEL_REGISTRY
        assert "fr_unet" in MODEL_REGISTRY, (
            f"fr_unet not in MODEL_REGISTRY. Found: {sorted(MODEL_REGISTRY.keys())}"
        )

    def test_cs_net_registered(self):
        from baselines.registry import MODEL_REGISTRY
        assert "cs_net" in MODEL_REGISTRY, (
            f"cs_net not in MODEL_REGISTRY. Found: {sorted(MODEL_REGISTRY.keys())}"
        )

    def test_fr_unet_validate_attrs(self):
        adapter = _get_frunet()
        adapter.validate_attrs()  # 不抛即通过

    def test_cs_net_validate_attrs(self):
        adapter = _get_csnet()
        adapter.validate_attrs()  # 不抛即通过

    def test_fr_unet_kind_architecture(self):
        adapter = _get_frunet()
        assert adapter.kind == "architecture"

    def test_cs_net_kind_architecture(self):
        adapter = _get_csnet()
        assert adapter.kind == "architecture"

    def test_fr_unet_env_tag_main(self):
        adapter = _get_frunet()
        assert adapter.env_tag == "main"

    def test_cs_net_env_tag_main(self):
        adapter = _get_csnet()
        assert adapter.env_tag == "main"


# --------------------------------------------------------------------------- #
#  Test 2: build_model shape 验证
# --------------------------------------------------------------------------- #

class TestBuildModel:
    """build_model 返回模型，forward 输出形状正确。"""

    def test_fr_unet_patch_forward_shape(self):
        """
        FR-UNet 在 patch 输入 (2, 1, 48, 48) 上 forward → (2, 1, 48, 48)。
        训练时用 patch（评估时走滑窗，见 test_sliding_window）。
        """
        adapter = _get_frunet()
        cfg = {}  # 全用默认
        model = adapter.build_model(cfg)
        model.eval()

        x = torch.zeros(2, 1, 48, 48)
        with torch.no_grad():
            out = model(x)

        assert out.shape == (2, 1, 48, 48), (
            f"FR-UNet patch forward shape mismatch: {out.shape}"
        )

    def test_cs_net_fullimg_forward_shape(self):
        """
        CS-Net 在全图输入 (2, 3, 64, 64) 上 forward → (2, 1, 64, 64)。
        官方整图 512，这里用 64 做快速测试（卷积尺寸无关）。
        注意: CSNet.forward 末尾含 sigmoid，输出 [0,1]。
        """
        adapter = _get_csnet()
        cfg = {}
        model = adapter.build_model(cfg)
        model.eval()

        # 使用 64×64（必须是 16 的倍数，4 次 MaxPool2d 后至少 1×1）
        x = torch.zeros(2, 3, 64, 64)
        with torch.no_grad():
            out = model(x)

        assert out.shape == (2, 1, 64, 64), (
            f"CS-Net full-image forward shape mismatch: {out.shape}"
        )
        # 输出应在 [0,1]（官方含 sigmoid）
        assert out.min() >= 0.0 and out.max() <= 1.0 + 1e-5, (
            f"CS-Net output should be in [0,1] (sigmoid), got [{out.min():.4f}, {out.max():.4f}]"
        )

    def test_fr_unet_build_model_returns_nn_module(self):
        adapter = _get_frunet()
        model = adapter.build_model({})
        assert isinstance(model, torch.nn.Module)

    def test_cs_net_build_model_returns_nn_module(self):
        adapter = _get_csnet()
        model = adapter.build_model({})
        assert isinstance(model, torch.nn.Module)


# --------------------------------------------------------------------------- #
#  Test 3: forward_adapt — FR-UNet 滑窗推理
# --------------------------------------------------------------------------- #

class TestFRUNetSlidingWindow:
    """FR-UNet forward_adapt 滑窗推理在合成全图上拼回正确 shape。"""

    def test_sliding_window_shape_square(self):
        """
        合成全图 (1, 1, 96, 96) → forward_adapt → (1, 1, 96, 96)。
        96 是 48 的倍数，最简单的对齐情形。
        """
        adapter = _get_frunet()
        model = adapter.build_model({})
        device = torch.device("cpu")

        x = torch.zeros(1, 1, 96, 96)
        out = adapter.forward_adapt(model, x, device)

        assert out.shape == (1, 1, 96, 96), (
            f"FR-UNet sliding window (96x96) shape mismatch: {out.shape}"
        )

    def test_sliding_window_shape_non_multiple(self):
        """
        合成全图 (1, 1, 100, 100)（非 patch_size 倍数）→ (1, 1, 100, 100)。
        验证 padding + 裁回逻辑正确。
        """
        adapter = _get_frunet()
        model = adapter.build_model({})
        device = torch.device("cpu")

        x = torch.zeros(1, 1, 100, 100)
        out = adapter.forward_adapt(model, x, device)

        assert out.shape == (1, 1, 100, 100), (
            f"FR-UNet sliding window (100x100) shape mismatch: {out.shape}"
        )

    def test_sliding_window_shape_rectangular(self):
        """
        非正方形输入 (1, 1, 64, 96) → (1, 1, 64, 96)。
        """
        adapter = _get_frunet()
        model = adapter.build_model({})
        device = torch.device("cpu")

        x = torch.zeros(1, 1, 64, 96)
        out = adapter.forward_adapt(model, x, device)

        assert out.shape == (1, 1, 64, 96), (
            f"FR-UNet sliding window (64x96) shape mismatch: {out.shape}"
        )

    def test_sliding_window_batch_size_2(self):
        """batch_size=2 时也能正确拼图。"""
        adapter = _get_frunet()
        model = adapter.build_model({})
        device = torch.device("cpu")

        x = torch.zeros(2, 1, 96, 96)
        out = adapter.forward_adapt(model, x, device)

        assert out.shape == (2, 1, 96, 96), (
            f"FR-UNet sliding window batch=2 shape mismatch: {out.shape}"
        )

    def test_sliding_window_small_image(self):
        """
        输入小于一个 patch (1, 1, 32, 32) → (1, 1, 32, 32)。
        测试 padding 兜底逻辑。
        """
        adapter = _get_frunet()
        model = adapter.build_model({})
        device = torch.device("cpu")

        x = torch.zeros(1, 1, 32, 32)
        out = adapter.forward_adapt(model, x, device)

        assert out.shape == (1, 1, 32, 32), (
            f"FR-UNet sliding window (32x32 < patch_size) shape mismatch: {out.shape}"
        )

    def test_sliding_window_wrong_channel_raises(self):
        """输入非单通道时应该断言失败（AssertionError）。"""
        adapter = _get_frunet()
        model = adapter.build_model({})
        device = torch.device("cpu")

        x = torch.zeros(1, 3, 64, 64)  # 错误：3 通道
        with pytest.raises(AssertionError):
            adapter.forward_adapt(model, x, device)


# --------------------------------------------------------------------------- #
#  Test 4: forward_adapt — CS-Net 全图推理
# --------------------------------------------------------------------------- #

class TestCSNetForwardAdapt:
    """CS-Net forward_adapt 全图推理输出 logits (B,1,H,W)。"""

    def test_forward_adapt_shape(self):
        """(2, 3, 64, 64) → (2, 1, 64, 64) logits。"""
        adapter = _get_csnet()
        model = adapter.build_model({})
        device = torch.device("cpu")

        x = torch.zeros(2, 3, 64, 64)
        out = adapter.forward_adapt(model, x, device)

        assert out.shape == (2, 1, 64, 64), (
            f"CS-Net forward_adapt shape mismatch: {out.shape}"
        )

    def test_forward_adapt_returns_logits(self):
        """
        forward_adapt 应返回 logits（非概率）。
        CSNet 内部含 sigmoid，adapter 把 prob → logit。
        对于零输入，logit 应接近 0（sigmoid(0.5)≈0.622，logit=log(0.622/0.378)≈0.5）。
        关键: 值域不限 [0,1]，即 logits 可超 1 或低于 0 是正常的。
        此处只验证 4D shape（避免数值依赖 random init）。
        """
        adapter = _get_csnet()
        cfg = {}
        model = adapter.build_model(cfg)
        device = torch.device("cpu")

        x = torch.zeros(1, 3, 64, 64)
        out = adapter.forward_adapt(model, x, device)

        assert out.ndim == 4, f"Expected 4D tensor, got {out.ndim}D"
        assert out.shape[1] == 1, f"Expected channel=1, got {out.shape[1]}"

    def test_forward_adapt_wrong_channel_raises(self):
        """输入非 3 通道时应该断言失败。"""
        adapter = _get_csnet()
        model = adapter.build_model({})
        device = torch.device("cpu")

        x = torch.zeros(1, 1, 64, 64)  # 错误：1 通道
        with pytest.raises(AssertionError):
            adapter.forward_adapt(model, x, device)


# --------------------------------------------------------------------------- #
#  Test 5: preprocess_cfg 字段验证
# --------------------------------------------------------------------------- #

class TestPreprocessCfg:
    """preprocess_cfg 返回必要字段，值符合约定。"""

    def test_fr_unet_preprocess_cfg_fields(self):
        adapter = _get_frunet()
        cfg = adapter.preprocess_cfg()

        assert "channels" in cfg
        assert "input_mode" in cfg
        assert "patch_size" in cfg
        assert "clahe" in cfg
        assert "normalize" in cfg
        assert "extra" in cfg

    def test_fr_unet_preprocess_cfg_patch_mode(self):
        adapter = _get_frunet()
        cfg = adapter.preprocess_cfg()

        assert cfg["input_mode"] == "patch", "FR-UNet 应是 patch 模式"
        assert cfg["patch_size"] == 48, f"官方 patch=48, got {cfg['patch_size']}"
        assert cfg["clahe"] is False, "FR-UNet 官方无 CLAHE"
        assert cfg["extra"]["stride"] == 6, f"官方 stride=6, got {cfg['extra']['stride']}"

    def test_cs_net_preprocess_cfg_fields(self):
        adapter = _get_csnet()
        cfg = adapter.preprocess_cfg()

        assert "channels" in cfg
        assert "input_mode" in cfg
        assert "patch_size" in cfg
        assert "clahe" in cfg
        assert "normalize" in cfg

    def test_cs_net_preprocess_cfg_fullimg_rgb(self):
        adapter = _get_csnet()
        cfg = adapter.preprocess_cfg()

        assert cfg["input_mode"] == "fullimg", "CS-Net 应是 fullimg 模式"
        assert cfg["channels"] == "rgb", "CS-Net 应是 RGB 三通道"
        assert cfg["patch_size"] is None, "CS-Net 整图模式 patch_size=None"
        assert cfg["clahe"] is False, "CS-Net 官方无 CLAHE"
        assert cfg["extra"]["resize"] == 512, f"官方 resize=512, got {cfg['extra']['resize']}"


# --------------------------------------------------------------------------- #
#  Test 6: build_optimizer / build_scheduler 类型验证
# --------------------------------------------------------------------------- #

class TestBuildOptimizerScheduler:
    """optimizer/scheduler 返回正确类型。"""

    def test_fr_unet_optimizer_is_adam(self):
        adapter = _get_frunet()
        model = adapter.build_model({})
        opt = adapter.build_optimizer(model, {})
        assert isinstance(opt, torch.optim.Adam), f"Expected Adam, got {type(opt)}"

    def test_fr_unet_optimizer_lr(self):
        adapter = _get_frunet()
        model = adapter.build_model({})
        opt = adapter.build_optimizer(model, {})
        lr = opt.param_groups[0]["lr"]
        assert abs(lr - 1e-4) < 1e-10, f"Expected lr=1e-4, got {lr}"

    def test_fr_unet_optimizer_wd(self):
        adapter = _get_frunet()
        model = adapter.build_model({})
        opt = adapter.build_optimizer(model, {})
        wd = opt.param_groups[0]["weight_decay"]
        assert abs(wd - 1e-5) < 1e-12, f"Expected wd=1e-5, got {wd}"

    def test_fr_unet_scheduler_is_cosine(self):
        adapter = _get_frunet()
        model = adapter.build_model({})
        opt = adapter.build_optimizer(model, {})
        sched = adapter.build_scheduler(opt, {})
        assert isinstance(sched, torch.optim.lr_scheduler.CosineAnnealingLR), (
            f"Expected CosineAnnealingLR, got {type(sched)}"
        )

    def test_cs_net_optimizer_is_adam(self):
        adapter = _get_csnet()
        model = adapter.build_model({})
        opt = adapter.build_optimizer(model, {})
        assert isinstance(opt, torch.optim.Adam), f"Expected Adam, got {type(opt)}"

    def test_cs_net_optimizer_lr(self):
        adapter = _get_csnet()
        model = adapter.build_model({})
        opt = adapter.build_optimizer(model, {})
        lr = opt.param_groups[0]["lr"]
        assert abs(lr - 1e-4) < 1e-10, f"Expected lr=1e-4, got {lr}"

    def test_cs_net_optimizer_wd(self):
        adapter = _get_csnet()
        model = adapter.build_model({})
        opt = adapter.build_optimizer(model, {})
        wd = opt.param_groups[0]["weight_decay"]
        assert abs(wd - 5e-4) < 1e-12, f"Expected wd=5e-4, got {wd}"

    def test_cs_net_scheduler_is_lambdalr(self):
        """CS-Net PolyLR 用 LambdaLR 实现。"""
        adapter = _get_csnet()
        model = adapter.build_model({})
        opt = adapter.build_optimizer(model, {})
        sched = adapter.build_scheduler(opt, {})
        assert isinstance(sched, torch.optim.lr_scheduler.LambdaLR), (
            f"Expected LambdaLR (PolyLR), got {type(sched)}"
        )

    def test_cs_net_poly_lr_decay(self):
        """PolyLR: 第 0 epoch lr_factor=1.0，第 500 epoch factor<1。"""
        import math
        adapter = _get_csnet()
        model = adapter.build_model({})
        opt = adapter.build_optimizer(model, {"lr": 1.0e-4})
        sched = adapter.build_scheduler(opt, {"epochs": 1000, "scheduler_poly_p": 0.9})
        # epoch 0: factor = (1 - 0/1000)^0.9 = 1.0
        factor_0 = sched.get_last_lr()[0] / 1e-4
        assert abs(factor_0 - 1.0) < 1e-6, f"PolyLR factor@epoch0 should be 1.0, got {factor_0}"
        # step 500 次后 factor = (1 - 500/1000)^0.9 ≈ 0.5357
        for _ in range(500):
            sched.step()
        lr_500 = opt.param_groups[0]["lr"]
        expected_factor = math.pow(0.5, 0.9)
        assert abs(lr_500 / 1e-4 - expected_factor) < 1e-4, (
            f"PolyLR@500 factor={lr_500/1e-4:.4f}, expected ~{expected_factor:.4f}"
        )


# --------------------------------------------------------------------------- #
#  Test 7: build_loss callable 验证
# --------------------------------------------------------------------------- #

class TestBuildLoss:
    """build_loss 返回 callable，可计算标量 loss。"""

    def test_fr_unet_loss_callable_scalar(self):
        adapter = _get_frunet()
        loss_fn = adapter.build_loss({})
        assert callable(loss_fn)

        logits = torch.zeros(2, 1, 48, 48)
        target = torch.zeros(2, 1, 48, 48)
        fov = torch.ones(2, 1, 48, 48)
        loss_val = loss_fn(logits, target, fov)

        assert loss_val.ndim == 0, f"Expected scalar loss, got shape {loss_val.shape}"
        assert torch.isfinite(loss_val), f"Loss is not finite: {loss_val}"

    def test_cs_net_loss_callable_scalar(self):
        """CS-Net loss 接受 prob（CSNet 输出是 sigmoid 概率）。"""
        adapter = _get_csnet()
        loss_fn = adapter.build_loss({})
        assert callable(loss_fn)

        # CS-Net 模型输出是概率 [0,1]，直接传 sigmoid 值
        prob = torch.rand(2, 1, 64, 64) * 0.1 + 0.45  # [0.45, 0.55]
        target = torch.zeros(2, 1, 64, 64)
        fov = torch.ones(2, 1, 64, 64)
        loss_val = loss_fn(prob, target, fov)

        assert loss_val.ndim == 0, f"Expected scalar loss, got shape {loss_val.shape}"
        assert torch.isfinite(loss_val), f"Loss is not finite: {loss_val}"


# --------------------------------------------------------------------------- #
#  Test 8: source_repo 非空验证
# --------------------------------------------------------------------------- #

class TestSourceRepo:
    def test_fr_unet_source_repo(self):
        adapter = _get_frunet()
        assert adapter.source_repo.startswith("https://"), (
            f"source_repo should be URL, got: {adapter.source_repo!r}"
        )
        assert "FR-UNet" in adapter.source_repo or "lseventeen" in adapter.source_repo

    def test_cs_net_source_repo(self):
        adapter = _get_csnet()
        assert adapter.source_repo.startswith("https://"), (
            f"source_repo should be URL, got: {adapter.source_repo!r}"
        )
        assert "CS-Net" in adapter.source_repo or "iMED-Lab" in adapter.source_repo


# --------------------------------------------------------------------------- #
#  __main__ guard（Windows spawn 安全）
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
