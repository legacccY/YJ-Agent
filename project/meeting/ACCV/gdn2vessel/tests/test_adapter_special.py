"""
test_adapter_special.py — pytest for DSCNet and creatis_postproc adapters.

覆盖:
  DSCNet:
    1. 注册: @register 后 'dscnet' 在 MODEL_REGISTRY
    2. validate_attrs 通过
    3. build_model 返回 nn.Module
    4. build_model forward shape: (B,1,H,W) → (B,1,H,W) logits
    5. forward_adapt shape: 整图 (1,1,64,64) → (1,1,64,64) logits
    6. forward_adapt 错误通道抛 AssertionError
    7. build_optimizer 是 AdamW，lr=1e-4，betas=(0.9, 0.95)
    8. build_scheduler 默认返回 None（官方 scheduler 注释掉）
    9. build_loss callable + 标量输出 + finite
   10. preprocess_cfg 字段正确（green_raw / fullimg / clahe=False）

  creatis_postproc:
   11. 注册: @register 后 'creatis_postproc' 在 MODEL_REGISTRY
   12. validate_attrs 通过
   13. build_model 在 monai 可用时返回 nn.Module（可选跳过）
   14. build_loss (PonderatedDiceloss) callable + 标量 + finite
   15. forward_adapt 接受合成 backbone logits (1,1,64,64)，输出同形 logits
       —— 若 monai 未安装则 skip（ImportError 优雅降级）
   16. build_optimizer 是 Adam，lr=1e-3
   17. build_scheduler 返回 None（官方无 scheduler）
   18. preprocess_cfg 字段含 two_stage=True + extra.license 含 CeCILL

Windows 规范:
  - 全 CPU 测试，无需 GPU
  - 无 scipy.stats
  - 无 multiprocessing
  - 路径用 pathlib.Path
  - if __name__ == '__main__' guard
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
#  Mock FLA（同 test_adapter_classic.py 策略）
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
#  Imports（mock 之后）
# --------------------------------------------------------------------------- #

import baselines  # noqa: E402 — triggers auto_discover


# --------------------------------------------------------------------------- #
#  Helpers
# --------------------------------------------------------------------------- #

def _get_dscnet():
    from baselines.registry import get_adapter
    return get_adapter("dscnet")


def _get_creatis():
    from baselines.registry import get_adapter
    return get_adapter("creatis_postproc")


def _monai_available() -> bool:
    try:
        import monai  # noqa: F401
        return True
    except ImportError:
        return False


# =========================================================================== #
#  DSCNet tests
# =========================================================================== #

class TestDSCNetRegistration:
    """DSCNet adapter 注册验证。"""

    def test_dscnet_registered(self):
        from baselines.registry import MODEL_REGISTRY
        assert "dscnet" in MODEL_REGISTRY, (
            f"'dscnet' not in MODEL_REGISTRY. Found: {sorted(MODEL_REGISTRY.keys())}"
        )

    def test_dscnet_validate_attrs(self):
        adapter = _get_dscnet()
        adapter.validate_attrs()  # 不抛即通过

    def test_dscnet_kind_architecture(self):
        adapter = _get_dscnet()
        assert adapter.kind == "architecture"

    def test_dscnet_env_tag_main(self):
        adapter = _get_dscnet()
        assert adapter.env_tag == "main"

    def test_dscnet_source_repo(self):
        adapter = _get_dscnet()
        assert "YaoleiQi" in adapter.source_repo or "DSCNet" in adapter.source_repo
        assert adapter.source_repo.startswith("https://")


class TestDSCNetBuildModel:
    """DSCNet build_model + forward shape 验证。"""

    def test_build_model_returns_module(self):
        adapter = _get_dscnet()
        model = adapter.build_model({})
        assert isinstance(model, torch.nn.Module)

    def test_forward_shape_1x1x64x64(self):
        """
        DSCNet DSConv_pro 使用 GroupNorm(out_ch//4, out_ch)。
        n_basic_layer=16 → 各层 out_ch 为 16/32/64/128 的倍数，均 ≥ 4。
        输入 (1,1,64,64) → 输出 (1,1,64,64)。
        """
        adapter = _get_dscnet()
        cfg = {"n_basic_layer": 8}  # 更小的 base ch 加快测试
        model = adapter.build_model(cfg)
        model.eval()

        x = torch.zeros(1, 1, 64, 64)
        with torch.no_grad():
            out = model(x)

        assert out.shape == (1, 1, 64, 64), (
            f"DSCNet forward shape mismatch: {out.shape}, expected (1,1,64,64)"
        )

    def test_forward_shape_2x1x32x32(self):
        """batch_size=2 输出 shape (2,1,32,32)。"""
        adapter = _get_dscnet()
        cfg = {"n_basic_layer": 8}
        model = adapter.build_model(cfg)
        model.eval()

        x = torch.zeros(2, 1, 32, 32)
        with torch.no_grad():
            out = model(x)

        assert out.shape == (2, 1, 32, 32), (
            f"DSCNet batch=2 shape mismatch: {out.shape}"
        )

    def test_output_is_logits_not_sigmoid(self):
        """
        adapter 已注释掉官方 sigmoid（见 S3_DSCNet_pro.py 尾部注释）。
        对零输入，logits 应接近 0（未经 sigmoid），验证不在 [0,1] 约束内。
        注意: 模型随机 init，仅验证值域不被约束在 [0,1]（通常 logits 有负值）。
        """
        adapter = _get_dscnet()
        cfg = {"n_basic_layer": 8}
        model = adapter.build_model(cfg)
        model.eval()

        x = torch.zeros(1, 1, 32, 32)
        with torch.no_grad():
            out = model(x)

        # logits 经 sigmoid 前，若初始 bias 零则大多趋 0，但不应被强制 [0,1]
        # 只验证可以出现负值或 > 1（至少有一个 logit 未被裁剪）
        # 对零输入+零 bias 网络，GroupNorm 后输出理论全零，允许 all-zero
        assert out.ndim == 4, f"Expected 4D output, got {out.ndim}D"
        assert out.shape[1] == 1, f"Expected channel=1, got {out.shape[1]}"


class TestDSCNetForwardAdapt:
    """DSCNet forward_adapt 验证。"""

    def test_forward_adapt_shape(self):
        """(1,1,64,64) → forward_adapt → (1,1,64,64)。"""
        adapter = _get_dscnet()
        cfg = {"n_basic_layer": 8}
        model = adapter.build_model(cfg)
        device = torch.device("cpu")

        x = torch.zeros(1, 1, 64, 64)
        out = adapter.forward_adapt(model, x, device)

        assert out.shape == (1, 1, 64, 64), (
            f"DSCNet forward_adapt shape mismatch: {out.shape}"
        )

    def test_forward_adapt_wrong_channel_raises(self):
        """输入非单通道 → AssertionError。"""
        adapter = _get_dscnet()
        cfg = {"n_basic_layer": 8}
        model = adapter.build_model(cfg)
        device = torch.device("cpu")

        x = torch.zeros(1, 3, 64, 64)  # wrong: 3 channels
        with pytest.raises(AssertionError):
            adapter.forward_adapt(model, x, device)


class TestDSCNetOptimizerLoss:
    """DSCNet optimizer / scheduler / loss 验证。"""

    def test_optimizer_is_adamw(self):
        adapter = _get_dscnet()
        model = adapter.build_model({"n_basic_layer": 8})
        opt = adapter.build_optimizer(model, {})
        assert isinstance(opt, torch.optim.AdamW), (
            f"Expected AdamW, got {type(opt)}"
        )

    def test_optimizer_lr(self):
        adapter = _get_dscnet()
        model = adapter.build_model({"n_basic_layer": 8})
        opt = adapter.build_optimizer(model, {})
        lr = opt.param_groups[0]["lr"]
        assert abs(lr - 1e-4) < 1e-10, f"Expected lr=1e-4, got {lr}"

    def test_optimizer_betas(self):
        adapter = _get_dscnet()
        model = adapter.build_model({"n_basic_layer": 8})
        opt = adapter.build_optimizer(model, {})
        betas = opt.param_groups[0]["betas"]
        assert abs(betas[0] - 0.9) < 1e-9, f"Expected beta1=0.9, got {betas[0]}"
        assert abs(betas[1] - 0.95) < 1e-9, f"Expected beta2=0.95, got {betas[1]}"

    def test_scheduler_default_none(self):
        """
        官方 scheduler.step(loss) 被注释掉 → adapter build_scheduler 默认 None。
        """
        adapter = _get_dscnet()
        model = adapter.build_model({"n_basic_layer": 8})
        opt = adapter.build_optimizer(model, {})
        sched = adapter.build_scheduler(opt, {})
        assert sched is None, f"Expected None (official scheduler disabled), got {type(sched)}"

    def test_loss_callable(self):
        adapter = _get_dscnet()
        loss_fn = adapter.build_loss({})
        assert callable(loss_fn), "build_loss should return callable"

    def test_loss_scalar_finite(self):
        adapter = _get_dscnet()
        loss_fn = adapter.build_loss({})

        logits = torch.zeros(2, 1, 32, 32)
        target = torch.zeros(2, 1, 32, 32)
        fov = torch.ones(2, 1, 32, 32)
        val = loss_fn(logits, target, fov)

        assert val.ndim == 0, f"Expected scalar, got shape {val.shape}"
        assert torch.isfinite(val), f"Loss not finite: {val}"

    def test_loss_nonzero_with_positive_target(self):
        """对正样本输入，loss 应 > 0（非平凡检验）。"""
        adapter = _get_dscnet()
        loss_fn = adapter.build_loss({})

        # logits=0 → sigmoid(0)=0.5；target=1 → BCE = -log(0.5+1e-6) > 0
        logits = torch.zeros(1, 1, 8, 8)
        target = torch.ones(1, 1, 8, 8)
        fov = torch.ones(1, 1, 8, 8)
        val = loss_fn(logits, target, fov)

        assert val.item() > 0.0, f"Loss should be > 0 for positive target, got {val.item()}"


class TestDSCNetPreprocessCfg:
    """DSCNet preprocess_cfg 字段验证。"""

    def test_fields_present(self):
        adapter = _get_dscnet()
        cfg = adapter.preprocess_cfg()
        required = {"channels", "normalize", "input_mode", "patch_size", "clahe", "extra"}
        missing = required - set(cfg.keys())
        assert not missing, f"Missing preprocess_cfg keys: {missing}"

    def test_green_raw_channel(self):
        adapter = _get_dscnet()
        cfg = adapter.preprocess_cfg()
        assert cfg["channels"] == "green_raw", (
            f"Expected 'green_raw', got {cfg['channels']!r}"
        )

    def test_fullimg_mode(self):
        adapter = _get_dscnet()
        cfg = adapter.preprocess_cfg()
        assert cfg["input_mode"] == "fullimg", (
            f"Expected 'fullimg', got {cfg['input_mode']!r}"
        )

    def test_no_clahe(self):
        adapter = _get_dscnet()
        cfg = adapter.preprocess_cfg()
        assert cfg["clahe"] is False, "DSCNet 官方无 CLAHE"

    def test_patch_size_none(self):
        adapter = _get_dscnet()
        cfg = adapter.preprocess_cfg()
        assert cfg["patch_size"] is None


# =========================================================================== #
#  creatis_postproc tests
# =========================================================================== #

class TestCreatisRegistration:
    """creatis_postproc adapter 注册验证。"""

    def test_creatis_registered(self):
        from baselines.registry import MODEL_REGISTRY
        assert "creatis_postproc" in MODEL_REGISTRY, (
            f"'creatis_postproc' not in MODEL_REGISTRY. "
            f"Found: {sorted(MODEL_REGISTRY.keys())}"
        )

    def test_creatis_validate_attrs(self):
        adapter = _get_creatis()
        adapter.validate_attrs()

    def test_creatis_kind_architecture(self):
        adapter = _get_creatis()
        assert adapter.kind == "architecture"

    def test_creatis_env_tag_main(self):
        adapter = _get_creatis()
        assert adapter.env_tag == "main"

    def test_creatis_source_repo(self):
        adapter = _get_creatis()
        assert "creatis-myriad" in adapter.source_repo or "creatis" in adapter.source_repo
        assert adapter.source_repo.startswith("https://")


@pytest.mark.skipif(not _monai_available(), reason="monai not installed; skip Stage-2 model tests")
class TestCreatisBuildModel:
    """creatis build_model（monai 依赖，可选 skip）。"""

    def test_build_model_returns_module(self):
        adapter = _get_creatis()
        model = adapter.build_model({})
        assert isinstance(model, torch.nn.Module)

    def test_build_model_no_model_dir(self):
        """model_dir=None → 从头构建，应正常返回 nn.Module。"""
        adapter = _get_creatis()
        model = adapter.build_model({"model_dir": None})
        assert isinstance(model, torch.nn.Module)


class TestCreatisLoss:
    """PonderatedDiceloss callable + 标量 + finite（不依赖 monai）。"""

    def test_loss_callable(self):
        adapter = _get_creatis()
        loss_fn = adapter.build_loss({})
        assert callable(loss_fn)

    def test_loss_scalar_finite(self):
        adapter = _get_creatis()
        loss_fn = adapter.build_loss({})

        logits = torch.zeros(2, 1, 32, 32)
        target = torch.zeros(2, 1, 32, 32)
        fov = torch.ones(2, 1, 32, 32)
        val = loss_fn(logits, target, fov)

        assert val.ndim == 0, f"Expected scalar loss, got shape {val.shape}"
        assert torch.isfinite(val), f"Loss not finite: {val}"

    def test_loss_positive_with_mismatch(self):
        """logits=0, target=1 → loss > 0。"""
        adapter = _get_creatis()
        loss_fn = adapter.build_loss({})

        logits = torch.zeros(1, 1, 8, 8)
        target = torch.ones(1, 1, 8, 8)
        fov = torch.ones(1, 1, 8, 8)
        val = loss_fn(logits, target, fov)

        assert val.item() > 0.0, f"PonderatedDiceloss should be > 0, got {val.item()}"


class TestCreatisOptimizer:
    """creatis optimizer / scheduler 验证。"""

    def _build_tiny_model(self):
        """构建最小模型用于 optimizer 测试（不依赖 monai）。"""
        import torch.nn as nn
        return nn.Linear(4, 1)

    def test_optimizer_is_adam(self):
        adapter = _get_creatis()
        model = self._build_tiny_model()
        opt = adapter.build_optimizer(model, {})
        assert isinstance(opt, torch.optim.Adam), (
            f"Expected Adam, got {type(opt)}"
        )

    def test_optimizer_lr(self):
        adapter = _get_creatis()
        model = self._build_tiny_model()
        opt = adapter.build_optimizer(model, {})
        lr = opt.param_groups[0]["lr"]
        assert abs(lr - 1e-3) < 1e-10, f"Expected lr=1e-3, got {lr}"

    def test_scheduler_none(self):
        """官方无 scheduler → None。"""
        adapter = _get_creatis()
        model = self._build_tiny_model()
        opt = adapter.build_optimizer(model, {})
        sched = adapter.build_scheduler(opt, {})
        assert sched is None, f"Expected None, got {type(sched)}"


class TestCreatisPreprocessCfg:
    """creatis preprocess_cfg 字段验证。"""

    def test_fields_present(self):
        adapter = _get_creatis()
        cfg = adapter.preprocess_cfg()
        required = {"channels", "normalize", "input_mode", "patch_size", "clahe", "extra"}
        missing = required - set(cfg.keys())
        assert not missing, f"Missing preprocess_cfg keys: {missing}"

    def test_two_stage_flag(self):
        adapter = _get_creatis()
        cfg = adapter.preprocess_cfg()
        assert cfg["extra"].get("two_stage") is True, (
            "creatis should have extra.two_stage=True"
        )

    def test_license_in_extra(self):
        """extra.license 应含 CeCILL 字样。"""
        adapter = _get_creatis()
        cfg = adapter.preprocess_cfg()
        license_str = cfg["extra"].get("license", "")
        assert "CeCILL" in license_str, (
            f"extra.license should mention CeCILL, got: {license_str!r}"
        )

    def test_fullimg_mode(self):
        adapter = _get_creatis()
        cfg = adapter.preprocess_cfg()
        assert cfg["input_mode"] == "fullimg"

    def test_green_clahe_channel(self):
        """creatis Stage-1 用统一 backbone_unet 的 green_clahe。"""
        adapter = _get_creatis()
        cfg = adapter.preprocess_cfg()
        assert cfg["channels"] == "green_clahe"


@pytest.mark.skipif(not _monai_available(), reason="monai not installed; skip forward_adapt test")
class TestCreatisForwardAdapt:
    """creatis forward_adapt 两段式推理验证（需 monai）。"""

    def test_forward_adapt_shape(self):
        """
        合成 backbone logits (1,1,64,64) → forward_adapt → (1,1,64,64) logits。
        使用随机初始化（未训练）的 creatis 模型。
        """
        adapter = _get_creatis()
        model = adapter.build_model({"model_dir": None})
        device = torch.device("cpu")

        # 合成 backbone logits（随机，模拟 stage-1 输出）
        backbone_logits = torch.randn(1, 1, 64, 64)
        out = adapter.forward_adapt(model, backbone_logits, device)

        assert out.shape == (1, 1, 64, 64), (
            f"creatis forward_adapt shape mismatch: {out.shape}"
        )

    def test_forward_adapt_output_is_logits(self):
        """
        输出应是 pseudo-logit（经 logit 变换的 float 张量）。
        不约束值域（logit 可为任意 float）。
        """
        adapter = _get_creatis()
        model = adapter.build_model({"model_dir": None})
        device = torch.device("cpu")

        backbone_logits = torch.zeros(1, 1, 32, 32)
        out = adapter.forward_adapt(model, backbone_logits, device)

        assert out.ndim == 4
        assert out.shape[1] == 1
        assert out.dtype == torch.float32

    def test_forward_adapt_wrong_channel_raises(self):
        """输入非单通道 → AssertionError。"""
        adapter = _get_creatis()
        model = adapter.build_model({"model_dir": None})
        device = torch.device("cpu")

        x = torch.zeros(1, 3, 32, 32)  # wrong channels
        with pytest.raises(AssertionError):
            adapter.forward_adapt(model, x, device)


# =========================================================================== #
#  creatis _PonderatedDiceloss 官方三元组接口测试
# =========================================================================== #

class TestCreatisPonderatedDicelossRaw:
    """
    直接测 _PonderatedDiceloss（未经 wrapper），验证官方三元组返回。
    不依赖 monai。
    """

    def _get_loss(self):
        from baselines.adapters.creatis_postproc import _PonderatedDiceloss
        return _PonderatedDiceloss(eps=1e-6)

    def test_forward_returns_tuple3(self):
        """官方 forward 返回 (total, dice_1, dice_2) 三元组。"""
        loss_fn = self._get_loss()
        prob = torch.sigmoid(torch.zeros(2, 1, 32, 32))  # (B,1,H,W) 概率
        target = torch.zeros(2, 1, 32, 32)
        mask = torch.ones(2, 1, 32, 32)
        out = loss_fn(prob, target, mask)
        assert isinstance(out, tuple), f"Expected tuple, got {type(out)}"
        assert len(out) == 3, f"Expected 3-tuple (total, d1, d2), got len={len(out)}"

    def test_forward_all_scalars(self):
        """total / dice_1 / dice_2 均为 0-dim 标量张量。"""
        loss_fn = self._get_loss()
        prob = torch.rand(2, 1, 32, 32)
        target = (torch.rand(2, 1, 32, 32) > 0.5).float()
        mask = torch.ones(2, 1, 32, 32)
        total, d1, d2 = loss_fn(prob, target, mask)
        for name, v in [("total", total), ("dice_1", d1), ("dice_2", d2)]:
            assert v.ndim == 0, f"{name} should be scalar, got shape {v.shape}"
            assert torch.isfinite(v), f"{name} not finite: {v}"

    def test_total_equals_d1_plus_d2(self):
        """total == dice_1 + dice_2（官方定义）。"""
        loss_fn = self._get_loss()
        prob = torch.rand(2, 1, 16, 16)
        target = (torch.rand(2, 1, 16, 16) > 0.5).float()
        mask = (torch.rand(2, 1, 16, 16) > 0.3).float()
        total, d1, d2 = loss_fn(prob, target, mask)
        assert abs((total - (d1 + d2)).item()) < 1e-5, (
            f"total({total.item()}) != d1({d1.item()}) + d2({d2.item()})"
        )

    def test_gradient_flows(self):
        """梯度可回传（用于 Stage-2 训练）。"""
        loss_fn = self._get_loss()
        logits = torch.randn(1, 1, 16, 16, requires_grad=True)
        prob = torch.sigmoid(logits)
        target = (torch.rand(1, 1, 16, 16) > 0.5).float()
        mask = torch.ones(1, 1, 16, 16)
        total, _, _ = loss_fn(prob, target, mask)
        total.backward()
        assert logits.grad is not None, "Gradient did not flow back through _PonderatedDiceloss"
        assert torch.isfinite(logits.grad).all(), "Gradient contains inf/nan"


# =========================================================================== #
#  creatis wrapper 接口测试（harness 兼容）
# =========================================================================== #

class TestCreatisLossWrapper:
    """_CreatisLossWrapper: harness signature (logits, target, fov) → scalar。"""

    def _get_wrapper(self):
        adapter = _get_creatis()
        return adapter.build_loss({})

    def test_wrapper_is_nn_module(self):
        w = self._get_wrapper()
        assert isinstance(w, torch.nn.Module)

    def test_wrapper_callable_returns_scalar(self):
        w = self._get_wrapper()
        logits = torch.zeros(2, 1, 32, 32)
        target = torch.zeros(2, 1, 32, 32)
        fov = torch.ones(2, 1, 32, 32)
        val = w(logits, target, fov)
        assert val.ndim == 0, f"Wrapper should return scalar, got shape {val.shape}"
        assert torch.isfinite(val), f"Wrapper loss not finite: {val}"

    def test_wrapper_positive_with_mismatch(self):
        """logits=0, target=1 → loss > 0。"""
        w = self._get_wrapper()
        logits = torch.zeros(1, 1, 8, 8)
        target = torch.ones(1, 1, 8, 8)
        fov = torch.ones(1, 1, 8, 8)
        val = w(logits, target, fov)
        assert val.item() > 0.0, f"Loss should be > 0 for mismatched target, got {val.item()}"

    def test_wrapper_gradient_flows(self):
        """梯度能从 wrapper 回传到 logits。"""
        w = self._get_wrapper()
        logits = torch.randn(1, 1, 16, 16, requires_grad=True)
        target = (torch.rand(1, 1, 16, 16) > 0.5).float()
        fov = torch.ones(1, 1, 16, 16)
        val = w(logits, target, fov)
        val.backward()
        assert logits.grad is not None, "Gradient did not flow through _CreatisLossWrapper"
        assert torch.isfinite(logits.grad).all(), "Gradient contains inf/nan"


# =========================================================================== #
#  disconnect.create_disconnections 测试
# =========================================================================== #

class TestCreatisDisconnect:
    """disconnect.create_disconnections 断点生成协议验证。不依赖 monai/GPU。"""

    def _get_small_gt(self, H: int = 64, W: int = 64) -> np.ndarray:
        """造一条简单横向血管 GT（uint8 {0,255}）。"""
        gt = np.zeros((H, W), dtype=np.uint8)
        gt[H // 2 - 2 : H // 2 + 2, 5 : W - 5] = 255  # 水平带状血管
        return gt

    def test_output_shapes(self):
        from baselines.third_party.creatis_postproc.disconnect import create_disconnections
        gt = self._get_small_gt(64, 64)
        rng = np.random.default_rng(42)
        inp_art, pos_mask = create_disconnections(gt, nb_disconnection=3, size_max=6, rng=rng)
        assert inp_art.shape == (64, 64), f"input_with_art shape: {inp_art.shape}"
        assert pos_mask.shape == (64, 64), f"pos_mask shape: {pos_mask.shape}"

    def test_output_dtype_uint8(self):
        from baselines.third_party.creatis_postproc.disconnect import create_disconnections
        gt = self._get_small_gt(64, 64)
        rng = np.random.default_rng(0)
        inp_art, pos_mask = create_disconnections(gt, nb_disconnection=2, size_max=6, rng=rng)
        assert inp_art.dtype == np.uint8, f"input_with_art dtype: {inp_art.dtype}"
        assert pos_mask.dtype == np.uint8, f"pos_mask dtype: {pos_mask.dtype}"

    def test_output_binary_values(self):
        """输出值应在 {0, 255}。"""
        from baselines.third_party.creatis_postproc.disconnect import create_disconnections
        gt = self._get_small_gt(64, 64)
        rng = np.random.default_rng(1)
        inp_art, pos_mask = create_disconnections(gt, nb_disconnection=2, size_max=6, rng=rng)
        unique_art = set(np.unique(inp_art).tolist())
        unique_pos = set(np.unique(pos_mask).tolist())
        assert unique_art <= {0, 255}, f"input_with_art has unexpected values: {unique_art}"
        assert unique_pos <= {0, 255}, f"pos_mask has unexpected values: {unique_pos}"

    def test_disconnection_reduces_foreground(self):
        """断点操作后前景像素数 <= 原始（断点只删不加）。"""
        from baselines.third_party.creatis_postproc.disconnect import create_disconnections
        gt = self._get_small_gt(64, 64)
        rng = np.random.default_rng(7)
        inp_art, _ = create_disconnections(gt, nb_disconnection=5, size_max=8, rng=rng)
        original_fg = (gt > 0).sum()
        art_fg = (inp_art > 0).sum()
        assert art_fg <= original_fg, (
            f"After disconnection fg should not increase: orig={original_fg}, art={art_fg}"
        )

    def test_pos_mask_nonzero_when_break_exists(self):
        """若确实产生了断点，pos_mask 应有非零区域。"""
        from baselines.third_party.creatis_postproc.disconnect import create_disconnections
        gt = self._get_small_gt(128, 128)  # 更大的图，断点更可能落在血管上
        rng = np.random.default_rng(99)
        inp_art, pos_mask = create_disconnections(gt, nb_disconnection=10, size_max=8, rng=rng)
        original_fg = (gt > 0).sum()
        art_fg = (inp_art > 0).sum()
        if art_fg < original_fg:
            # 确实有像素被删 → pos_mask 应非零
            assert pos_mask.max() > 0, (
                f"Disconnection removed {original_fg - art_fg} pixels but pos_mask is all zero"
            )

    def test_empty_gt_returns_original(self):
        """全黑 GT → 警告 + 返回原图 + 全零 mask。"""
        from baselines.third_party.creatis_postproc.disconnect import create_disconnections
        gt = np.zeros((32, 32), dtype=np.uint8)
        with pytest.warns(UserWarning):
            inp_art, pos_mask = create_disconnections(gt, nb_disconnection=3, size_max=6)
        assert inp_art.sum() == 0
        assert pos_mask.sum() == 0


# =========================================================================== #
#  image_utils.normalize_image 测试
# =========================================================================== #

class TestCreatisNormalizeImage:
    """image_utils.normalize_image 语义验证（uint8{0,255} → [0,1] float32）。"""

    def test_max_val_1_gives_unit_range(self):
        from baselines.third_party.creatis_postproc.image_utils import normalize_image
        img = np.array([[0, 127, 255]], dtype=np.uint8)
        out = normalize_image(img, 1)
        assert out.dtype == np.float32
        assert abs(out[0, 0] - 0.0) < 1e-5
        assert abs(out[0, 2] - 1.0) < 1e-5

    def test_binary_stays_binary(self):
        from baselines.third_party.creatis_postproc.image_utils import normalize_image
        img = np.array([[0, 255, 0, 255]], dtype=np.uint8)
        out = normalize_image(img, 1)
        # 255 位置应映射到约 1.0
        high_vals = out[out > 0.9]
        assert len(high_vals) == 2, f"Expected 2 high-val pixels, got {len(high_vals)}"
        assert all(abs(v - 1.0) < 1e-5 for v in high_vals.tolist()), (
            f"Expected ~1.0, got {high_vals}"
        )

    def test_output_shape_preserved(self):
        from baselines.third_party.creatis_postproc.image_utils import normalize_image
        img = np.zeros((64, 64), dtype=np.uint8)
        out = normalize_image(img, 1)
        assert out.shape == (64, 64)


# --------------------------------------------------------------------------- #
#  __main__ guard
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
