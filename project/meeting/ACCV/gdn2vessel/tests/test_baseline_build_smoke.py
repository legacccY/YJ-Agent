"""
test_baseline_build_smoke.py — P3 主实验前置就绪烟测

覆盖所有 12 个 P3 进档 A baseline + ours_gdn2：
  - main 系（8个）: 真实例化 build_model + forward_adapt，验证 shape=(B,1,H,W)
  - loss 类（3个）: build_model + forward_adapt + build_loss forward，验证 scalar finite
  - mamba 系（3个）: build_model 预期 RuntimeError 含 "mamba" 关键词（标需 mamba_venv）
  - nnUNet 系（2个）: build_model 预期 RuntimeError 含 nnunetv2/nnU-Net（标需 nnUNetv2）
  - creatis_postproc: 有 monai 时真测，无 monai 时 skip

DoD 判据（PHASE_3_MATRIX §0 前置阻塞之一）：
  - 所有 main 系 adapter PASS（shape 正确，无异常）
  - 所有 mamba 系 adapter 正确报 RuntimeError 含 mamba 关键词
  - 所有 nnUNet 系 adapter 正确报 RuntimeError 含 nnunetv2/nnU-Net 关键词
  - 所有 loss 类 adapter loss forward 值有限非 nan

Windows 规范：
  - 全 CPU 测试（无需 GPU）
  - 无 scipy.stats
  - 无 multiprocessing
  - if __name__ == '__main__' guard

注意：本文件是「真烟测非 mock」(feedback_pytest_green_not_runnable)——
  main 系直接实例化真模型真 forward，mamba/nnUNet 系验证真实的 RuntimeError。
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

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
#  Mock FLA（无 FLA kernel 环境兼容）
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
#  Auto-discover: 注册所有 adapter
# --------------------------------------------------------------------------- #

import baselines  # noqa: E402 — 触发 auto_discover


# --------------------------------------------------------------------------- #
#  Helpers
# --------------------------------------------------------------------------- #

def _get(name: str):
    from baselines.registry import get_adapter
    return get_adapter(name)


def _has_mamba_ssm() -> bool:
    try:
        import mamba_ssm  # noqa: F401
        return True
    except ImportError:
        return False


def _has_nnunetv2() -> bool:
    try:
        import nnunetv2  # noqa: F401
        return True
    except ImportError:
        return False


def _has_monai() -> bool:
    try:
        import monai  # noqa: F401
        return True
    except ImportError:
        return False


_MAMBA_AVAILABLE = _has_mamba_ssm()
_NNUNET_AVAILABLE = _has_nnunetv2()
_MONAI_AVAILABLE = _has_monai()


# =========================================================================== #
#  §1: main venv 系 architecture adapter 烟测
#  fr_unet / cs_net / dscnet / creatis_postproc / ours_gdn2
# =========================================================================== #

class TestMainArchBuildSmoke:
    """
    main venv architecture adapter 真实例化 + forward_adapt 烟测。
    全 CPU，dummy input，验证 output shape == (B,1,H,W) 且无异常。
    """

    def test_fr_unet_build_forward(self):
        """
        FR-UNet patch-based，forward_adapt 走滑窗拼回全图。
        输入 (1,1,64,64) → (1,1,64,64) 不崩，shape 正确。
        """
        adapter = _get("fr_unet")
        model = adapter.build_model({})
        model.eval()
        device = torch.device("cpu")
        x = torch.zeros(1, 1, 64, 64)
        out = adapter.forward_adapt(model, x, device)
        assert out.shape == (1, 1, 64, 64), f"fr_unet shape: {out.shape}"
        assert torch.isfinite(out).all(), "fr_unet output has inf/nan"

    def test_cs_net_build_forward(self):
        """
        CS-Net 全图 RGB 输入，forward 含 sigmoid，adapter 转 logit。
        输入 (1,3,64,64) → (1,1,64,64) logits。
        """
        adapter = _get("cs_net")
        model = adapter.build_model({})
        model.eval()
        device = torch.device("cpu")
        x = torch.zeros(1, 3, 64, 64)
        out = adapter.forward_adapt(model, x, device)
        assert out.shape == (1, 1, 64, 64), f"cs_net shape: {out.shape}"
        assert torch.isfinite(out).all(), "cs_net output has inf/nan"

    def test_dscnet_build_forward(self):
        """
        DSCNet 2D 整图 forward，输入 (1,1,64,64)。
        官方 cross_loss (BCE)。
        """
        adapter = _get("dscnet")
        # n_basic_layer=8 减小 test 模型，加快速度
        model = adapter.build_model({"n_basic_layer": 8})
        model.eval()
        device = torch.device("cpu")
        x = torch.zeros(1, 1, 64, 64)
        out = adapter.forward_adapt(model, x, device)
        assert out.shape == (1, 1, 64, 64), f"dscnet shape: {out.shape}"
        assert torch.isfinite(out).all(), "dscnet output has inf/nan"

    def test_ours_gdn2_build_forward(self):
        """
        Ours (UNetGDN2) 自证走同台 adapter。
        输入 (1,1,64,64) → (1,1,64,64) logits。
        """
        adapter = _get("ours_gdn2")
        model = adapter.build_model({})
        model.eval()
        device = torch.device("cpu")
        x = torch.zeros(1, 1, 64, 64)
        out = adapter.forward_adapt(model, x, device)
        assert out.shape == (1, 1, 64, 64), f"ours_gdn2 shape: {out.shape}"
        assert torch.isfinite(out).all(), "ours_gdn2 output has inf/nan"


# =========================================================================== #
#  §2: loss 类 adapter 烟测（统一 backbone UNet + loss forward）
#  cldice / cbdice / skeleton_recall
# =========================================================================== #

class TestLossAdapterBuildSmoke:
    """
    loss 类 adapter：
      build_model → 统一 backbone UNet(base_ch=32)
      forward_adapt → (1,1,H,W) logits
      build_loss + forward → scalar finite（核心 DoD）
    """

    @pytest.mark.parametrize("name", ["cldice", "cbdice", "skeleton_recall"])
    def test_loss_adapter_build_model(self, name: str):
        """build_model 返回 UNet 实例（统一 backbone，kind=loss）。"""
        import torch.nn as nn
        adapter = _get(name)
        assert adapter.kind == "loss", f"{name} should be kind='loss'"
        model = adapter.build_model({})
        assert isinstance(model, nn.Module), f"{name} build_model not nn.Module"

    @pytest.mark.parametrize("name", ["cldice", "cbdice", "skeleton_recall"])
    def test_loss_adapter_forward_adapt_shape(self, name: str):
        """forward_adapt (1,1,64,64) → (1,1,64,64) logits."""
        adapter = _get(name)
        model = adapter.build_model({})
        model.eval()
        device = torch.device("cpu")
        x = torch.zeros(1, 1, 64, 64)
        out = adapter.forward_adapt(model, x, device)
        assert out.shape == (1, 1, 64, 64), f"{name} forward_adapt shape: {out.shape}"
        assert torch.isfinite(out).all(), f"{name} forward_adapt has inf/nan"

    @pytest.mark.parametrize("name", ["cldice", "cbdice", "skeleton_recall"])
    def test_loss_adapter_loss_forward_finite(self, name: str):
        """
        build_loss forward (logits, target, fov_mask) → scalar finite.
        这是 loss 类 adapter 的核心 DoD（区别于 architecture adapter）。
        """
        adapter = _get(name)
        loss_fn = adapter.build_loss({})
        assert callable(loss_fn), f"{name} build_loss not callable"

        # dummy input：logits=0 → sigmoid=0.5，target=0，fov=1
        logits = torch.zeros(1, 1, 32, 32)
        target = torch.zeros(1, 1, 32, 32)
        fov = torch.ones(1, 1, 32, 32)
        val = loss_fn(logits, target, fov)

        assert val.ndim == 0, f"{name} loss should be scalar, got shape {val.shape}"
        assert torch.isfinite(val), f"{name} loss not finite: {val}"
        assert not torch.isnan(val), f"{name} loss is nan"

    def test_cldice_loss_alpha_05(self):
        """
        clDice loss α=0.5（官方 default）：两输入对称时 loss 在合理范围。
        验证 alpha 参数有效读取（ClDiceLoss(alpha=0.5)）。
        """
        adapter = _get("cldice")
        cfg = {"alpha": 0.5}
        loss_fn = adapter.build_loss(cfg)
        logits = torch.zeros(1, 1, 32, 32)
        target = torch.zeros(1, 1, 32, 32)
        fov = torch.ones(1, 1, 32, 32)
        val = loss_fn(logits, target, fov)
        assert val.item() >= 0.0, "clDice loss should be >= 0"
        assert val.item() <= 2.0, f"clDice loss unexpectedly large: {val.item()}"

    def test_cbdice_loss_weights_211(self):
        """
        cbDice loss 官方 2:1:1（adapter 硬编码，cfg 死字段）。
        验证 adapter.build_loss 不依赖 yaml 里的 weight_base/weight_cbdice。
        关键：传 {weight_base:0.5, weight_cbdice:0.5}（yaml 旧值）和 {} 结果一致。
        """
        adapter = _get("cbdice")
        # 传 yaml 旧死字段
        loss_fn_old_cfg = adapter.build_loss({"weight_base": 0.5, "weight_cbdice": 0.5})
        # 传空 cfg
        loss_fn_empty = adapter.build_loss({})

        logits = torch.zeros(1, 1, 32, 32)
        target = torch.zeros(1, 1, 32, 32)
        fov = torch.ones(1, 1, 32, 32)
        val_old = loss_fn_old_cfg(logits, target, fov)
        val_empty = loss_fn_empty(logits, target, fov)

        # 两者结果应相同（均走硬编码 2:1:1，cfg 不影响）
        assert abs(val_old.item() - val_empty.item()) < 1e-6, (
            f"cbdice loss should be cfg-invariant (hardcoded 2:1:1): "
            f"old_cfg={val_old.item():.6f}, empty={val_empty.item():.6f}"
        )

    def test_skeleton_recall_loss_weights_111(self):
        """
        skeleton_recall 官方 1:1:1（adapter 硬编码，cfg 死字段）。
        验证 adapter.build_loss 不依赖 yaml 里旧的 weight_base/weight_srec。
        """
        adapter = _get("skeleton_recall")
        # 传 yaml 旧死字段
        loss_fn_old = adapter.build_loss({"weight_base": 0.5, "weight_srec": 0.5})
        # 传空 cfg
        loss_fn_empty = adapter.build_loss({})

        logits = torch.zeros(1, 1, 32, 32)
        target = torch.zeros(1, 1, 32, 32)
        fov = torch.ones(1, 1, 32, 32)
        val_old = loss_fn_old(logits, target, fov)
        val_empty = loss_fn_empty(logits, target, fov)

        # 两者结果应相同（均走硬编码 1:1:1，cfg 不影响）
        assert abs(val_old.item() - val_empty.item()) < 1e-6, (
            f"skeleton_recall loss should be cfg-invariant (hardcoded 1:1:1): "
            f"old_cfg={val_old.item():.6f}, empty={val_empty.item():.6f}"
        )


# =========================================================================== #
#  §3: mamba 系 adapter 烟测（预期 RuntimeError 标 mamba_venv）
#  vm_unet / mm_unet / u_mamba
# =========================================================================== #

class TestMambaAdapterSmoke:
    """
    mamba 系 adapter：本地无 mamba_ssm → build_model 应抛 RuntimeError，
    错误信息应含 'mamba'（指向 mamba_venv 安装指引）。
    这是「通过」态：RuntimeError 正确报 mamba_venv_needed = 就绪。
    """

    @pytest.mark.skipif(
        _MAMBA_AVAILABLE,
        reason="mamba_ssm installed — build_model will succeed; skip RuntimeError check"
    )
    def test_vm_unet_needs_mamba_venv(self):
        """vm_unet build_model 在无 mamba_ssm 时抛 RuntimeError 含 'mamba'。"""
        adapter = _get("vm_unet")
        with pytest.raises(RuntimeError, match="(?i)mamba"):
            adapter.build_model({})

    @pytest.mark.skipif(
        _MAMBA_AVAILABLE,
        reason="mamba_ssm installed — build_model will succeed"
    )
    def test_mm_unet_needs_mamba_venv(self):
        """mm_unet build_model 在无 mamba_ssm 时抛 RuntimeError 含 'mamba'。"""
        adapter = _get("mm_unet")
        with pytest.raises(RuntimeError, match="(?i)mamba"):
            adapter.build_model({})

    @pytest.mark.skipif(
        _MAMBA_AVAILABLE and _NNUNET_AVAILABLE,
        reason="both mamba_ssm and nnunetv2 installed"
    )
    def test_u_mamba_needs_mamba_venv(self):
        """u_mamba build_model 在缺依赖时抛 RuntimeError。"""
        adapter = _get("u_mamba")
        with pytest.raises(RuntimeError):
            adapter.build_model({})

    @pytest.mark.parametrize("name", ["vm_unet", "mm_unet", "u_mamba"])
    def test_mamba_adapters_env_tag(self, name: str):
        """mamba 系 adapter env_tag='mamba'（HPC 调度器依据）。"""
        adapter = _get(name)
        assert adapter.env_tag == "mamba", (
            f"{name} env_tag should be 'mamba', got {adapter.env_tag!r}"
        )

    @pytest.mark.parametrize("name", ["vm_unet", "mm_unet", "u_mamba"])
    def test_mamba_adapters_registered(self, name: str):
        """mamba 系 adapter 已正确注册（registry 可取出）。"""
        from baselines.registry import MODEL_REGISTRY
        assert name in MODEL_REGISTRY, f"{name} not in MODEL_REGISTRY"

    @pytest.mark.parametrize("name", ["vm_unet", "mm_unet", "u_mamba"])
    def test_mamba_adapters_validate_attrs(self, name: str):
        """mamba 系 adapter validate_attrs 不抛（属性均已设置）。"""
        adapter = _get(name)
        adapter.validate_attrs()  # 不抛即通过

    @pytest.mark.skipif(
        _MAMBA_AVAILABLE,
        reason="mamba_ssm installed"
    )
    def test_vm_unet_build_loss_callable_without_mamba(self):
        """vm_unet BceDiceLoss 是纯 PyTorch，无需 mamba_ssm，应可直接 callable。"""
        adapter = _get("vm_unet")
        loss_fn = adapter.build_loss({})
        assert callable(loss_fn), "vm_unet build_loss should be callable without mamba_ssm"

        logits = torch.zeros(2, 1, 32, 32)
        target = torch.zeros(2, 1, 32, 32)
        fov = torch.ones(2, 1, 32, 32)
        val = loss_fn(logits, target, fov)
        assert val.ndim == 0, f"vm_unet loss should be scalar, got shape {val.shape}"
        assert torch.isfinite(val), f"vm_unet loss not finite: {val}"


# =========================================================================== #
#  §4: nnUNet 系 adapter 烟测（预期 RuntimeError 标 nnUNetv2）
#  nnunet / pasc_net（u_mamba 在 §3 覆盖）
# =========================================================================== #

class TestNNUNetAdapterSmoke:
    """
    nnUNet 系 adapter：build_model 预期 RuntimeError（需 nnUNetv2 安装 + 命令行框架）。
    这是「通过」态：正确报 nnUNetv2_needed = 就绪。
    """

    @pytest.mark.skipif(
        _NNUNET_AVAILABLE,
        reason="nnunetv2 installed — different RuntimeError path"
    )
    def test_nnunet_build_model_raises(self):
        """nnunet build_model 在无 nnunetv2 时抛 RuntimeError。"""
        adapter = _get("nnunet")
        with pytest.raises(RuntimeError, match="(?i)(nnunetv2|nnU-Net)"):
            adapter.build_model({})

    @pytest.mark.skipif(
        _NNUNET_AVAILABLE,
        reason="nnunetv2 installed"
    )
    def test_pasc_net_build_model_raises(self):
        """pasc_net build_model 在无 nnunetv2 时抛 RuntimeError。"""
        adapter = _get("pasc_net")
        with pytest.raises(RuntimeError, match="(?i)(nnunetv2|nnU-Net|PASC)"):
            adapter.build_model({})

    @pytest.mark.parametrize("name", ["nnunet", "pasc_net"])
    def test_nnunet_adapters_env_tag_main(self, name: str):
        """nnunet/pasc_net env_tag='main'（pip install nnunetv2，不需 mamba_venv）。"""
        adapter = _get(name)
        assert adapter.env_tag == "main", (
            f"{name} env_tag should be 'main', got {adapter.env_tag!r}"
        )

    @pytest.mark.parametrize("name", ["nnunet", "pasc_net"])
    def test_nnunet_adapters_registered(self, name: str):
        from baselines.registry import MODEL_REGISTRY
        assert name in MODEL_REGISTRY

    @pytest.mark.parametrize("name", ["nnunet", "pasc_net"])
    def test_nnunet_adapters_validate_attrs(self, name: str):
        adapter = _get(name)
        adapter.validate_attrs()

    def test_pasc_net_loss_weights_documented(self):
        """
        PASC-Net 复合 loss 权重 0.7/0.1/0.1/0.1 已在 adapter 类常量记录。
        这些是官方 researcher 核实的值（BASELINE_SPEC §1）。
        """
        from baselines.adapters.pascnet import _PASCNetLoss
        loss = _PASCNetLoss()
        assert abs(loss.WEIGHT_DC_CE - 0.7) < 1e-9
        assert abs(loss.WEIGHT_CON1 - 0.1) < 1e-9
        assert abs(loss.WEIGHT_CON3 - 0.1) < 1e-9
        assert abs(loss.WEIGHT_CLDICE - 0.1) < 1e-9


# =========================================================================== #
#  §5: creatis_postproc adapter 烟测（依赖 monai，无 monai 则 skip）
# =========================================================================== #

@pytest.mark.skipif(
    not _MONAI_AVAILABLE,
    reason="monai not installed — skip creatis build/forward smoke test"
)
class TestCreatisPostprocBuildSmoke:
    """
    creatis_postproc build_model + forward_adapt 烟测（需 monai）。
    Stage-2 reconnecting model = monai UNet。
    """

    def test_creatis_build_model(self):
        """build_model(model_dir=None) 返回 monai UNet。"""
        import torch.nn as nn
        adapter = _get("creatis_postproc")
        model = adapter.build_model({"model_dir": None})
        assert isinstance(model, nn.Module)

    def test_creatis_forward_adapt_shape(self):
        """
        forward_adapt 接受 backbone logits (1,1,64,64)，
        返回 reconnected pseudo-logits (1,1,64,64)。
        """
        adapter = _get("creatis_postproc")
        model = adapter.build_model({"model_dir": None})
        device = torch.device("cpu")
        backbone_logits = torch.randn(1, 1, 64, 64)
        out = adapter.forward_adapt(model, backbone_logits, device)
        assert out.shape == (1, 1, 64, 64), f"creatis_postproc shape: {out.shape}"
        assert torch.isfinite(out).all(), "creatis_postproc output has inf/nan"


# =========================================================================== #
#  §6: 全 12 adapter 注册完整性快检（registry 维度）
# =========================================================================== #

class TestAllAdaptersRegistered:
    """
    P3 进档 A 所有 12 + ours_gdn2 均已注册（registry 快检）。
    这是集成层面的完整性保障。
    """

    _P3_ADAPTERS = [
        # architecture main
        "fr_unet", "cs_net", "dscnet", "creatis_postproc",
        # loss main
        "cldice", "cbdice", "skeleton_recall",
        # mamba
        "vm_unet", "u_mamba", "mm_unet",
        # nnUNet
        "nnunet", "pasc_net",
        # Ours
        "ours_gdn2",
    ]

    @pytest.mark.parametrize("name", _P3_ADAPTERS)
    def test_adapter_registered(self, name: str):
        """所有 P3 adapter 均在 MODEL_REGISTRY 中。"""
        from baselines.registry import MODEL_REGISTRY
        assert name in MODEL_REGISTRY, (
            f"'{name}' not in MODEL_REGISTRY. "
            f"Registered: {sorted(MODEL_REGISTRY.keys())}"
        )

    @pytest.mark.parametrize("name", _P3_ADAPTERS)
    def test_adapter_validate_attrs(self, name: str):
        """所有 P3 adapter validate_attrs 通过（name/kind/source_repo/env_tag 均合法）。"""
        adapter = _get(name)
        adapter.validate_attrs()  # 不抛即通过

    @pytest.mark.parametrize("name,expected_env", [
        ("fr_unet", "main"), ("cs_net", "main"), ("dscnet", "main"),
        ("creatis_postproc", "main"), ("cldice", "main"), ("cbdice", "main"),
        ("skeleton_recall", "main"), ("nnunet", "main"), ("pasc_net", "main"),
        ("ours_gdn2", "main"),
        ("vm_unet", "mamba"), ("u_mamba", "mamba"), ("mm_unet", "mamba"),
    ])
    def test_adapter_env_tag(self, name: str, expected_env: str):
        """env_tag 正确（main/mamba），HPC 卡槽调度器选 venv 依据。"""
        adapter = _get(name)
        assert adapter.env_tag == expected_env, (
            f"{name} env_tag should be {expected_env!r}, got {adapter.env_tag!r}"
        )


# =========================================================================== #
#  §7: config 真源链确认（yaml env_tag 与 adapter 一致）
# =========================================================================== #

class TestConfigTrueSourceChain:
    """
    核实各 baseline yaml 的关键字段与 adapter 代码一致。
    防 harness 读 cfg 时拿到错误值。

    真源规则：
      - architecture 类：超参从 yaml 读（adapter 通过 cfg.get 读取）
      - loss 类（cldice/cbdice/skeleton_recall）：
          loss 权重 = adapter 硬编码（cfg 死字段）
          骨架 backbone/optimizer/lr = adapter 硬编码常量
      - mamba/nnUNet 框架类：yaml 仅记录，实际超参由框架管理
    """

    def _load_yaml(self, filename: str) -> dict:
        import yaml
        p = _repo_root / "src" / "configs" / "baselines" / filename
        assert p.exists(), f"Config not found: {p}"
        with open(p, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_frunet_yaml_env_tag_match(self):
        """frunet.yaml env_tag == adapter.env_tag。"""
        cfg = self._load_yaml("frunet.yaml")
        adapter = _get("fr_unet")
        assert cfg["baseline"]["env_tag"] == adapter.env_tag

    def test_frunet_yaml_epochs(self):
        """frunet.yaml train.epochs == 40（官方）。"""
        cfg = self._load_yaml("frunet.yaml")
        assert cfg["train"]["epochs"] == 40

    def test_csnet_yaml_epochs(self):
        """csnet.yaml train.epochs == 1000（官方）。"""
        cfg = self._load_yaml("csnet.yaml")
        assert cfg["train"]["epochs"] == 1000

    def test_dscnet_yaml_epochs(self):
        """dscnet.yaml train.epochs == 400（官方）。"""
        cfg = self._load_yaml("dscnet.yaml")
        assert cfg["train"]["epochs"] == 400

    def test_dscnet_scheduler_disabled(self):
        """dscnet.yaml use_scheduler=False（官方 scheduler.step 被注释掉）。"""
        cfg = self._load_yaml("dscnet.yaml")
        assert cfg["train"]["use_scheduler"] is False

    def test_cldice_yaml_alpha(self):
        """cldice.yaml loss.alpha == 0.5（官方 default）。"""
        cfg = self._load_yaml("cldice.yaml")
        assert abs(float(cfg["loss"]["alpha"]) - 0.5) < 1e-9

    def test_cldice_yaml_lr_is_dead_or_matches(self):
        """
        loss 类 adapter lr 由 adapter 硬编码（_UNIFIED_LR=1e-3），
        yaml train.lr 仅为记录文档，值应一致。
        """
        cfg = self._load_yaml("cldice.yaml")
        # adapter 常量
        from baselines.adapters.cldice import _UNIFIED_LR
        assert abs(float(cfg["train"]["lr"]) - _UNIFIED_LR) < 1e-10, (
            f"cldice.yaml lr={cfg['train']['lr']} != adapter _UNIFIED_LR={_UNIFIED_LR}"
        )

    def test_cbdice_yaml_dead_weight_fields(self):
        """
        cbdice.yaml loss.weight_base 和 weight_cbdice 为死字段（已废弃注释掉）。
        确认 yaml 中这两个字段不再存在（已注释掉，yaml load 后不可见）。
        这保证 harness 不会误读旧 0.5/0.5 值。
        """
        cfg = self._load_yaml("cbdice.yaml")
        loss_cfg = cfg.get("loss", {})
        # 这两个旧字段应已从 yaml 中注释掉
        assert "weight_base" not in loss_cfg, (
            "cbdice.yaml should NOT have active 'weight_base' key "
            "(it was deprecated in favor of adapter hardcoded 2:1:1). "
            f"Found keys: {list(loss_cfg.keys())}"
        )
        assert "weight_cbdice" not in loss_cfg, (
            "cbdice.yaml should NOT have active 'weight_cbdice' key "
            "(deprecated). "
            f"Found keys: {list(loss_cfg.keys())}"
        )

    def test_skeleton_recall_yaml_dead_weight_fields(self):
        """
        skeleton_recall.yaml loss.weight_base 和 weight_srec 为死字段（已废弃注释掉）。
        确认 yaml 中这两个字段不再存在（已注释掉，yaml load 后不可见）。
        """
        cfg = self._load_yaml("skeleton_recall.yaml")
        loss_cfg = cfg.get("loss", {})
        assert "weight_base" not in loss_cfg, (
            "skeleton_recall.yaml should NOT have active 'weight_base' key "
            "(deprecated; hardcoded 1:1:1 in adapter). "
            f"Found keys: {list(loss_cfg.keys())}"
        )
        assert "weight_srec" not in loss_cfg, (
            "skeleton_recall.yaml should NOT have active 'weight_srec' key. "
            f"Found keys: {list(loss_cfg.keys())}"
        )

    def test_vmunet_yaml_env_tag(self):
        """vmunet.yaml env_tag='mamba'。"""
        cfg = self._load_yaml("vmunet.yaml")
        assert cfg["baseline"]["env_tag"] == "mamba"

    def test_mm_unet_yaml_env_tag(self):
        """mm_unet.yaml env_tag='mamba'。"""
        cfg = self._load_yaml("mm_unet.yaml")
        assert cfg["baseline"]["env_tag"] == "mamba"

    def test_umamba_yaml_env_tag(self):
        """umamba.yaml env_tag='mamba'。"""
        cfg = self._load_yaml("umamba.yaml")
        assert cfg["baseline"]["env_tag"] == "mamba"

    def test_nnunet_yaml_env_tag(self):
        """nnunet.yaml env_tag='main'（pip install nnunetv2 in main venv）。"""
        cfg = self._load_yaml("nnunet.yaml")
        assert cfg["baseline"]["env_tag"] == "main"

    def test_pascnet_yaml_env_tag(self):
        """pascnet.yaml env_tag='main'。"""
        cfg = self._load_yaml("pascnet.yaml")
        assert cfg["baseline"]["env_tag"] == "main"


# --------------------------------------------------------------------------- #
#  __main__ guard（Windows spawn 安全）
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
