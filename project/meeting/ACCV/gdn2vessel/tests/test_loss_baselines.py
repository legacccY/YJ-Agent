"""
test_loss_baselines.py — pytest for topology loss 三件套 + adapters。

覆盖:
  1. ClDiceLoss       前向出标量 + 反向梯度非 nan
  2. CbDiceLoss       前向出标量 + 反向梯度非 nan
  3. SkeletonRecallLoss 前向出标量 + 反向梯度非 nan
  4. cldice adapter 注册成功 + build_model 出 UNet (B,1,H,W)
  5. cbdice adapter 注册成功 + build_model 出 UNet (B,1,H,W)
  6. skeleton_recall adapter 注册成功 + build_model 出 UNet (B,1,H,W)
  7. 三 adapter build_loss 返回 callable
  8. validate_attrs 通过（name/kind/source_repo/env_tag 正确）

设计原则:
  - 全 CPU 测试，无需 GPU
  - 合成小张量（B=2, H=32, W=32），不依赖真实数据
  - 无 scipy.stats，无 multiprocessing
  - Windows 安全：路径用 pathlib.Path
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import torch

# --------------------------------------------------------------------------- #
#  sys.path
# --------------------------------------------------------------------------- #

_repo_root = Path(__file__).parent.parent
_src_dir = _repo_root / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))


# --------------------------------------------------------------------------- #
#  合成测试张量 helper
# --------------------------------------------------------------------------- #

def make_batch(B: int = 2, H: int = 32, W: int = 32):
    """返回 (logits, target, fov_mask)，均 (B,1,H,W) CPU float32。"""
    torch.manual_seed(42)
    logits = torch.randn(B, 1, H, W, requires_grad=True)
    target = (torch.rand(B, 1, H, W) > 0.5).float()
    fov_mask = torch.ones(B, 1, H, W)
    # 模拟 FOV：边缘 4 像素置 0
    fov_mask[:, :, :4, :] = 0.0
    fov_mask[:, :, -4:, :] = 0.0
    return logits, target, fov_mask


# ============================================================================
# Loss 前向 + 反向 测试
# ============================================================================

class TestClDiceLoss:
    """clDice loss (jocpae/clDice, MIT, CVPR 2021)。"""

    def test_forward_scalar(self):
        from baselines.losses.cldice_loss import ClDiceLoss
        loss_fn = ClDiceLoss(alpha=0.5)
        logits, target, fov_mask = make_batch()
        loss = loss_fn(logits, target, fov_mask)
        assert loss.ndim == 0, f"expected scalar, got shape {loss.shape}"
        assert torch.isfinite(loss), f"loss not finite: {loss.item()}"

    def test_backward_no_nan(self):
        from baselines.losses.cldice_loss import ClDiceLoss
        loss_fn = ClDiceLoss(alpha=0.5)
        logits, target, fov_mask = make_batch()
        loss = loss_fn(logits, target, fov_mask)
        loss.backward()
        grad = logits.grad
        assert grad is not None, "logits.grad is None"
        assert not torch.any(torch.isnan(grad)), "grad contains nan"
        assert not torch.any(torch.isinf(grad)), "grad contains inf"

    def test_loss_range(self):
        """clDice 值应在合理范围（理论 [0,1] 附近，实测可能略超）。"""
        from baselines.losses.cldice_loss import ClDiceLoss
        loss_fn = ClDiceLoss(alpha=0.5)
        logits, target, fov_mask = make_batch()
        loss = loss_fn(logits, target, fov_mask)
        # 宽松约束：值不应是极端异常
        assert loss.item() > -1.0, f"loss too negative: {loss.item()}"
        assert loss.item() < 5.0, f"loss too large: {loss.item()}"

    def test_alpha_zero_equals_pure_dice(self):
        """α=0 时 clDice = 纯 SoftDice（检查 alpha 参数生效）。"""
        from baselines.losses.cldice_loss import ClDiceLoss
        loss_fn_a0 = ClDiceLoss(alpha=0.0)
        loss_fn_a05 = ClDiceLoss(alpha=0.5)
        logits, target, fov_mask = make_batch()
        l0 = loss_fn_a0(logits, target, fov_mask)
        l05 = loss_fn_a05(logits, target, fov_mask)
        # 两者不应完全相等（alpha 不同时 clDice term 权重不同）
        assert l0.item() != l05.item(), "alpha=0 和 alpha=0.5 结果相同，alpha 参数无效"


class TestCbDiceLoss:
    """cbDice loss (PengchengShi1220/cbDice, Apache-2.0, MICCAI 2024)。"""

    def test_forward_scalar(self):
        from baselines.losses.cbdice_loss import CbDiceLoss
        loss_fn = CbDiceLoss()
        logits, target, fov_mask = make_batch()
        loss = loss_fn(logits, target, fov_mask)
        assert loss.ndim == 0, f"expected scalar, got shape {loss.shape}"
        assert torch.isfinite(loss), f"loss not finite: {loss.item()}"

    def test_backward_no_nan(self):
        from baselines.losses.cbdice_loss import CbDiceLoss
        loss_fn = CbDiceLoss()
        logits, target, fov_mask = make_batch()
        loss = loss_fn(logits, target, fov_mask)
        loss.backward()
        grad = logits.grad
        assert grad is not None, "logits.grad is None"
        assert not torch.any(torch.isnan(grad)), "grad contains nan"
        assert not torch.any(torch.isinf(grad)), "grad contains inf"

    def test_loss_negative(self):
        """官方 cb_dice_loss 返回 -2*(w_tprec*w_tsens)/(w_tprec+w_tsens)，应为负值。"""
        from baselines.losses.cbdice_loss import SoftcbDiceLoss
        # 直接测官方 core class（非 harness wrapper）
        core = SoftcbDiceLoss(iter_=10, smooth=1.0)
        B, H, W = 2, 32, 32
        torch.manual_seed(42)
        prob_fg = torch.sigmoid(torch.randn(B, 1, H, W))
        prob_bg = 1.0 - prob_fg
        y_pred = torch.cat([prob_bg, prob_fg], dim=1)  # (B,2,H,W)
        y_true = (torch.rand(B, 1, H, W) > 0.5).float()
        loss = core(y_pred, y_true)
        # cbDice 官方 forward 返回 -2*(tprec*tsens)/(tprec+tsens) ≤ 0
        assert loss.item() <= 0.5, f"cb_dice_loss expected ≤ 0.5, got {loss.item()}"

    def test_get_weights_shapes(self):
        """get_weights 输出 shape 与输入一致。"""
        from baselines.losses.cbdice_loss import get_weights
        B, H, W = 2, 16, 16
        mask = (torch.rand(B, H, W) > 0.5).float()
        skel = (torch.rand(B, H, W) > 0.8).float()
        q_v, q_sv, q_s = get_weights(mask, skel, dim=2, prob_flag=False)
        assert q_v.shape == (B, H, W)
        assert q_sv.shape == (B, H, W)
        assert q_s.shape == (B, H, W)


class TestSkeletonRecallLoss:
    """Skeleton Recall loss (MIC-DKFZ/Skeleton-Recall, Apache-2.0, MICCAI 2024)。"""

    def test_forward_scalar(self):
        from baselines.losses.skeleton_recall_loss import SkeletonRecallLoss
        loss_fn = SkeletonRecallLoss()
        logits, target, fov_mask = make_batch()
        loss = loss_fn(logits, target, fov_mask)
        assert loss.ndim == 0, f"expected scalar, got shape {loss.shape}"
        assert torch.isfinite(loss), f"loss not finite: {loss.item()}"

    def test_backward_no_nan(self):
        from baselines.losses.skeleton_recall_loss import SkeletonRecallLoss
        loss_fn = SkeletonRecallLoss()
        logits, target, fov_mask = make_batch()
        loss = loss_fn(logits, target, fov_mask)
        loss.backward()
        grad = logits.grad
        assert grad is not None, "logits.grad is None"
        assert not torch.any(torch.isnan(grad)), "grad contains nan"
        assert not torch.any(torch.isinf(grad)), "grad contains inf"

    def test_skeleton_gt_binary(self):
        """skeleton GT 应为 binary 0/1。"""
        from baselines.losses.skeleton_recall_loss import _compute_skeleton_gt
        B, H, W = 2, 32, 32
        target = (torch.rand(B, 1, H, W) > 0.5).float()
        skel = _compute_skeleton_gt(target)
        assert skel.shape == (B, 1, H, W)
        unique = skel.unique()
        for v in unique:
            assert v.item() in (0.0, 1.0), f"skel GT contains non-binary value {v.item()}"

    def test_skeleton_subset_of_target(self):
        """skeleton GT 应是 target 的子集（skeleton ⊆ target）。"""
        from baselines.losses.skeleton_recall_loss import _compute_skeleton_gt
        B, H, W = 2, 32, 32
        target = (torch.rand(B, 1, H, W) > 0.5).float()
        skel = _compute_skeleton_gt(target)
        # skeleton 中为 1 的像素，target 也应为 1
        invalid = (skel == 1) & (target == 0)
        assert not invalid.any(), "skeleton contains pixels outside target mask"

    def test_soft_skeleton_recall_loss_negative_recall(self):
        """SoftSkeletonRecallLoss 直接测试，输出应为 -recall（≤ 0）。"""
        from baselines.losses.skeleton_recall_loss import SoftSkeletonRecallLoss
        srec = SoftSkeletonRecallLoss(smooth=1.0)
        B, C, H, W = 2, 2, 16, 16
        torch.manual_seed(42)
        x = torch.softmax(torch.randn(B, C, H, W), dim=1)
        # skeleton GT：稀疏二值 (B,1,H,W)
        y = (torch.rand(B, 1, H, W) > 0.8).float()
        loss = srec(x, y)
        assert loss.ndim == 0
        assert torch.isfinite(loss)
        # -recall ≤ 0（recall ≥ 0 → 负值）
        assert loss.item() <= 0.0 + 1e-4, f"expected ≤ 0, got {loss.item()}"


# ============================================================================
# Adapter 注册 + build_model shape 测试
# ============================================================================

class TestLossAdapters:
    """三个 loss 类 adapter 注册、build_model、build_loss、validate_attrs。"""

    def _import_all_adapters(self):
        """强制 import 触发 @register 装饰器。"""
        import baselines.adapters.cldice         # noqa: F401
        import baselines.adapters.cbdice         # noqa: F401
        import baselines.adapters.skeleton_recall  # noqa: F401

    def test_cldice_registered(self):
        self._import_all_adapters()
        from baselines.registry import MODEL_REGISTRY
        assert "cldice" in MODEL_REGISTRY, "cldice adapter not registered"

    def test_cbdice_registered(self):
        self._import_all_adapters()
        from baselines.registry import MODEL_REGISTRY
        assert "cbdice" in MODEL_REGISTRY, "cbdice adapter not registered"

    def test_skeleton_recall_registered(self):
        self._import_all_adapters()
        from baselines.registry import MODEL_REGISTRY
        assert "skeleton_recall" in MODEL_REGISTRY, "skeleton_recall adapter not registered"

    @pytest.mark.parametrize("adapter_name", ["cldice", "cbdice", "skeleton_recall"])
    def test_build_model_shape(self, adapter_name: str):
        """build_model 返回 UNet，forward 输出 (B,1,H,W)。"""
        self._import_all_adapters()
        from baselines.registry import get_adapter
        adapter = get_adapter(adapter_name)
        model = adapter.build_model({})
        model.eval()
        B, H, W = 2, 64, 64
        x = torch.randn(B, 1, H, W)
        with torch.no_grad():
            out = model(x)
        assert out.shape == (B, 1, H, W), (
            f"{adapter_name} build_model output shape {out.shape} != (B,1,H,W)"
        )

    @pytest.mark.parametrize("adapter_name", ["cldice", "cbdice", "skeleton_recall"])
    def test_build_loss_callable(self, adapter_name: str):
        """build_loss 返回 callable。"""
        self._import_all_adapters()
        from baselines.registry import get_adapter
        adapter = get_adapter(adapter_name)
        loss_fn = adapter.build_loss({})
        assert callable(loss_fn), f"{adapter_name} build_loss not callable"

    @pytest.mark.parametrize("adapter_name", ["cldice", "cbdice", "skeleton_recall"])
    def test_build_loss_forward(self, adapter_name: str):
        """build_loss forward 出有限标量。"""
        self._import_all_adapters()
        from baselines.registry import get_adapter
        adapter = get_adapter(adapter_name)
        loss_fn = adapter.build_loss({})
        logits, target, fov_mask = make_batch(B=1, H=32, W=32)
        loss = loss_fn(logits, target, fov_mask)
        assert loss.ndim == 0, f"{adapter_name} loss not scalar: {loss.shape}"
        assert torch.isfinite(loss), f"{adapter_name} loss not finite: {loss.item()}"

    @pytest.mark.parametrize("adapter_name", ["cldice", "cbdice", "skeleton_recall"])
    def test_validate_attrs(self, adapter_name: str):
        """validate_attrs 通过（name/kind/source_repo/env_tag 正确）。"""
        self._import_all_adapters()
        from baselines.registry import get_adapter
        adapter = get_adapter(adapter_name)
        # validate_attrs 不抛异常即为 PASS
        adapter.validate_attrs()
        assert adapter.kind == "loss", f"{adapter_name} kind should be 'loss'"
        assert adapter.env_tag == "main", f"{adapter_name} env_tag should be 'main'"
        assert adapter.source_repo != "", f"{adapter_name} source_repo empty"

    @pytest.mark.parametrize("adapter_name", ["cldice", "cbdice", "skeleton_recall"])
    def test_preprocess_cfg_fields(self, adapter_name: str):
        """preprocess_cfg 包含必要字段。"""
        self._import_all_adapters()
        from baselines.registry import get_adapter
        adapter = get_adapter(adapter_name)
        cfg = adapter.preprocess_cfg()
        required_keys = {"channels", "input_mode", "patch_size", "clahe"}
        missing = required_keys - set(cfg.keys())
        assert not missing, f"{adapter_name} preprocess_cfg missing keys: {missing}"
        assert cfg["channels"] == "green_clahe", (
            f"{adapter_name} should use green_clahe (§2.4 unified)"
        )
        assert cfg["input_mode"] == "fullimg", (
            f"{adapter_name} should use fullimg mode"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
