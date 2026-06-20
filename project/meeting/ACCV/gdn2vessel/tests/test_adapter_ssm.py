"""
test_adapter_ssm.py — pytest for SSM + nnU-Net framework baseline adapters.

覆盖:
  注册 + registry 取用:
    1. vm_unet / u_mamba / mamba_vessel_net 在 MODEL_REGISTRY 中
    2. nnunet / pasc_net 在 MODEL_REGISTRY 中
  validate_attrs:
    3. 所有 5 个 adapter 的 name/kind/source_repo/env_tag 均合法
  env_tag 正确性:
    4. vm_unet / u_mamba / mamba_vessel_net → env_tag='mamba'
    5. nnunet / pasc_net → env_tag='main'
  config 字段齐:
    6. preprocess_cfg 必要字段齐（channels/input_mode/patch_size/clahe/normalize/extra）
    7. vmunet preprocess_cfg: input_mode=fullimg, resize=256
    8. mamba_vessel_net preprocess_cfg: resize TODO 占位存在
    9. nnunet preprocess_cfg: framework=nnunetv2
   10. pasc_net preprocess_cfg: framework=nnunetv2, trainer=PASCTrainer
  build_loss callable:
   11. vm_unet build_loss 返回 callable
   12. nnunet / pasc_net build_loss 返回对象（框架外调用抛 RuntimeError）
  source_repo 验证:
   13. 所有 adapter source_repo 以 https:// 开头
  kind 验证:
   14. 所有 5 个 adapter kind='architecture'
  runtime RuntimeError (本地无 mamba/nnunet 依赖):
   15-19. build_model 在缺依赖时抛 RuntimeError（skipif 有真实依赖时）
  BceDiceLoss 接口（vm_unet 专属，无 mamba_ssm 依赖，直接测 loss 逻辑）:
   20. vm_unet BceDiceLoss 计算标量，值有限
  yaml config 字段（读取 yaml 文件核实关键字段）:
   21-25. 各 yaml 中 baseline.name / baseline.env_tag / train.epochs 等关键值正确

Windows 规范:
  - num_workers=0
  - 无 scipy.stats
  - 无 multiprocessing
  - 路径用 pathlib.Path / 绝对路径

设计原则:
  - 全 CPU 测试，无需 GPU
  - 不依赖真实数据集，完全合成小张量
  - 需 mamba/nnunet 运行时的真模型构建用 @pytest.mark.skipif 跳过
  - 每个 test 独立，无共享副作用
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
#  Mock FLA（防止无 FLA 环境炸，与 test_adapter_classic.py 策略一致）
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
#  依赖可用性检测（skipif 条件）
# --------------------------------------------------------------------------- #

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


# --------------------------------------------------------------------------- #
#  Imports — auto_discover 注册所有 adapter
# --------------------------------------------------------------------------- #

import baselines  # noqa: E402 — 触发 auto_discover，注册所有 adapters


# --------------------------------------------------------------------------- #
#  Helper: 获取 adapter 实例
# --------------------------------------------------------------------------- #

def _get(name: str):
    from baselines.registry import get_adapter
    return get_adapter(name)


# --------------------------------------------------------------------------- #
#  Test 1: 注册验证（MODEL_REGISTRY 包含所有 5 个 adapter）
# --------------------------------------------------------------------------- #

class TestRegistration:
    """@register 后所有 5 个 adapter 均在 MODEL_REGISTRY 中。"""

    def test_vm_unet_registered(self):
        from baselines.registry import MODEL_REGISTRY
        assert "vm_unet" in MODEL_REGISTRY, (
            f"vm_unet not in MODEL_REGISTRY. Found: {sorted(MODEL_REGISTRY.keys())}"
        )

    def test_u_mamba_registered(self):
        from baselines.registry import MODEL_REGISTRY
        assert "u_mamba" in MODEL_REGISTRY, (
            f"u_mamba not in MODEL_REGISTRY. Found: {sorted(MODEL_REGISTRY.keys())}"
        )

    def test_mamba_vessel_net_registered(self):
        from baselines.registry import MODEL_REGISTRY
        assert "mamba_vessel_net" in MODEL_REGISTRY, (
            f"mamba_vessel_net not in MODEL_REGISTRY. Found: {sorted(MODEL_REGISTRY.keys())}"
        )

    def test_nnunet_registered(self):
        from baselines.registry import MODEL_REGISTRY
        assert "nnunet" in MODEL_REGISTRY, (
            f"nnunet not in MODEL_REGISTRY. Found: {sorted(MODEL_REGISTRY.keys())}"
        )

    def test_pasc_net_registered(self):
        from baselines.registry import MODEL_REGISTRY
        assert "pasc_net" in MODEL_REGISTRY, (
            f"pasc_net not in MODEL_REGISTRY. Found: {sorted(MODEL_REGISTRY.keys())}"
        )

    def test_registry_get_adapter_vm_unet(self):
        """get_adapter 能取到 vm_unet 实例。"""
        adapter = _get("vm_unet")
        assert adapter is not None
        assert adapter.name == "vm_unet"

    def test_registry_get_adapter_nnunet(self):
        """get_adapter 能取到 nnunet 实例。"""
        adapter = _get("nnunet")
        assert adapter is not None
        assert adapter.name == "nnunet"


# --------------------------------------------------------------------------- #
#  Test 2: validate_attrs 通过
# --------------------------------------------------------------------------- #

class TestValidateAttrs:
    """name/kind/source_repo/env_tag 均已正确赋值，validate_attrs 不抛。"""

    @pytest.mark.parametrize("name", [
        "vm_unet", "u_mamba", "mamba_vessel_net", "nnunet", "pasc_net"
    ])
    def test_validate_attrs_passes(self, name: str):
        adapter = _get(name)
        adapter.validate_attrs()  # 不抛即通过


# --------------------------------------------------------------------------- #
#  Test 3: env_tag 正确性
# --------------------------------------------------------------------------- #

class TestEnvTag:
    """SSM adapter = 'mamba'，nnU-Net 框架 adapter = 'main'。"""

    @pytest.mark.parametrize("name", ["vm_unet", "u_mamba", "mamba_vessel_net"])
    def test_ssm_adapters_env_tag_mamba(self, name: str):
        adapter = _get(name)
        assert adapter.env_tag == "mamba", (
            f"{name} should have env_tag='mamba', got {adapter.env_tag!r}"
        )

    @pytest.mark.parametrize("name", ["nnunet", "pasc_net"])
    def test_nnunet_adapters_env_tag_main(self, name: str):
        adapter = _get(name)
        assert adapter.env_tag == "main", (
            f"{name} should have env_tag='main', got {adapter.env_tag!r}"
        )


# --------------------------------------------------------------------------- #
#  Test 4: kind = 'architecture'（所有 5 个均为 architecture 类）
# --------------------------------------------------------------------------- #

class TestKind:
    """所有 SSM + nnU-Net adapter 均为 architecture kind。"""

    @pytest.mark.parametrize("name", [
        "vm_unet", "u_mamba", "mamba_vessel_net", "nnunet", "pasc_net"
    ])
    def test_kind_architecture(self, name: str):
        adapter = _get(name)
        assert adapter.kind == "architecture", (
            f"{name} should have kind='architecture', got {adapter.kind!r}"
        )


# --------------------------------------------------------------------------- #
#  Test 5: source_repo 以 https:// 开头
# --------------------------------------------------------------------------- #

class TestSourceRepo:
    """source_repo 是合法 HTTPS URL。"""

    @pytest.mark.parametrize("name,expected_substring", [
        ("vm_unet", "JCruan519"),
        ("u_mamba", "bowang-lab"),
        ("mamba_vessel_net", "CC0117"),
        ("nnunet", "MIC-DKFZ"),
        ("pasc_net", "IPMI-NWU"),
    ])
    def test_source_repo_https_url(self, name: str, expected_substring: str):
        adapter = _get(name)
        assert adapter.source_repo.startswith("https://"), (
            f"{name} source_repo should be https URL, got: {adapter.source_repo!r}"
        )
        assert expected_substring in adapter.source_repo, (
            f"{name} source_repo should contain {expected_substring!r}, "
            f"got: {adapter.source_repo!r}"
        )


# --------------------------------------------------------------------------- #
#  Test 6: preprocess_cfg 字段完整性
# --------------------------------------------------------------------------- #

class TestPreprocessCfg:
    """preprocess_cfg 包含所有必要字段。"""

    _REQUIRED_KEYS = ["channels", "input_mode", "patch_size", "clahe", "normalize", "extra"]

    @pytest.mark.parametrize("name", [
        "vm_unet", "u_mamba", "mamba_vessel_net", "nnunet", "pasc_net"
    ])
    def test_preprocess_cfg_has_required_keys(self, name: str):
        adapter = _get(name)
        cfg = adapter.preprocess_cfg()
        for key in self._REQUIRED_KEYS:
            assert key in cfg, (
                f"{name}.preprocess_cfg() missing key: {key!r}. "
                f"Got keys: {sorted(cfg.keys())}"
            )

    def test_vmunet_preprocess_cfg_fullimg(self):
        adapter = _get("vm_unet")
        cfg = adapter.preprocess_cfg()
        assert cfg["input_mode"] == "fullimg", (
            f"vm_unet input_mode should be 'fullimg', got {cfg['input_mode']!r}"
        )
        assert cfg["patch_size"] is None
        assert cfg["clahe"] is False
        # 检查 resize=256 在 extra 中
        assert "resize" in cfg["extra"], "vm_unet extra should have 'resize' key"
        assert cfg["extra"]["resize"] == 256, (
            f"vm_unet resize should be 256, got {cfg['extra']['resize']}"
        )

    def test_umamba_preprocess_cfg_framework(self):
        adapter = _get("u_mamba")
        cfg = adapter.preprocess_cfg()
        assert cfg["extra"]["framework"] == "nnunetv2", (
            "u_mamba extra.framework should be 'nnunetv2'"
        )

    def test_mamba_vessel_net_preprocess_cfg_resize_exists(self):
        """MambaVesselNet++ preprocess_cfg extra 中有 resize 占位。"""
        adapter = _get("mamba_vessel_net")
        cfg = adapter.preprocess_cfg()
        assert "resize" in cfg["extra"], (
            "mamba_vessel_net extra should have 'resize' key (placeholder)"
        )

    def test_nnunet_preprocess_cfg_framework(self):
        adapter = _get("nnunet")
        cfg = adapter.preprocess_cfg()
        assert cfg["extra"]["framework"] == "nnunetv2", (
            "nnunet extra.framework should be 'nnunetv2'"
        )

    def test_pasc_net_preprocess_cfg_trainer(self):
        adapter = _get("pasc_net")
        cfg = adapter.preprocess_cfg()
        assert cfg["extra"]["framework"] == "nnunetv2", (
            "pasc_net extra.framework should be 'nnunetv2'"
        )
        assert cfg["extra"]["trainer"] == "PASCTrainer", (
            f"pasc_net extra.trainer should be 'PASCTrainer', "
            f"got {cfg['extra'].get('trainer')!r}"
        )


# --------------------------------------------------------------------------- #
#  Test 7: build_loss 接口
# --------------------------------------------------------------------------- #

class TestBuildLoss:
    """build_loss 返回 callable。"""

    def test_vm_unet_build_loss_callable(self):
        """vm_unet loss 是纯 PyTorch，无需 mamba_ssm，可直接测试 callable。"""
        adapter = _get("vm_unet")
        loss_fn = adapter.build_loss({})
        assert callable(loss_fn), "vm_unet build_loss should return callable"

    def test_vm_unet_loss_scalar(self):
        """vm_unet BceDiceLoss 计算标量，值有限。"""
        adapter = _get("vm_unet")
        loss_fn = adapter.build_loss({})

        logits = torch.zeros(2, 1, 32, 32)
        target = torch.zeros(2, 1, 32, 32)
        fov = torch.ones(2, 1, 32, 32)
        loss_val = loss_fn(logits, target, fov)

        assert loss_val.ndim == 0, f"Expected scalar loss, got shape {loss_val.shape}"
        assert torch.isfinite(loss_val), f"Loss is not finite: {loss_val}"

    def test_mamba_vessel_net_build_loss_callable(self):
        """mamba_vessel_net loss 是纯 PyTorch，可直接测试 callable。"""
        adapter = _get("mamba_vessel_net")
        loss_fn = adapter.build_loss({})
        assert callable(loss_fn), "mamba_vessel_net build_loss should return callable"

    def test_mamba_vessel_net_loss_scalar(self):
        """mamba_vessel_net DiceCELoss 计算标量，值有限。"""
        adapter = _get("mamba_vessel_net")
        loss_fn = adapter.build_loss({})

        logits = torch.zeros(2, 1, 32, 32)
        target = torch.zeros(2, 1, 32, 32)
        fov = torch.ones(2, 1, 32, 32)
        loss_val = loss_fn(logits, target, fov)

        assert loss_val.ndim == 0, f"Expected scalar loss, got shape {loss_val.shape}"
        assert torch.isfinite(loss_val), f"Loss is not finite: {loss_val}"

    def test_nnunet_build_loss_returns_object(self):
        """nnunet build_loss 返回对象（框架外调用会 RuntimeError，不在此测）。"""
        adapter = _get("nnunet")
        loss_fn = adapter.build_loss({})
        assert loss_fn is not None, "nnunet build_loss should return non-None"

    def test_pasc_net_build_loss_has_correct_weights(self):
        """pasc_net loss 对象含正确的官方权重常量。"""
        from baselines.adapters.pascnet import _PASCNetLoss
        loss = _PASCNetLoss()
        assert abs(loss.WEIGHT_DC_CE - 0.7) < 1e-9, f"Expected 0.7, got {loss.WEIGHT_DC_CE}"
        assert abs(loss.WEIGHT_CON1 - 0.1) < 1e-9, f"Expected 0.1, got {loss.WEIGHT_CON1}"
        assert abs(loss.WEIGHT_CON3 - 0.1) < 1e-9, f"Expected 0.1, got {loss.WEIGHT_CON3}"
        assert abs(loss.WEIGHT_CLDICE - 0.1) < 1e-9, f"Expected 0.1, got {loss.WEIGHT_CLDICE}"


# --------------------------------------------------------------------------- #
#  Test 8: build_model RuntimeError（缺依赖时）
# --------------------------------------------------------------------------- #

class TestBuildModelRuntimeError:
    """
    缺少 mamba_ssm / nnunetv2 时 build_model 抛 RuntimeError，
    并给出清晰的 HPC 指引。

    skipif：若依赖真实存在则跳过该 test（避免误判）。
    """

    @pytest.mark.skipif(
        _MAMBA_AVAILABLE,
        reason="mamba_ssm available — build_model will not raise RuntimeError"
    )
    def test_vm_unet_build_model_raises_without_mamba(self):
        adapter = _get("vm_unet")
        with pytest.raises(RuntimeError, match="mamba"):
            adapter.build_model({})

    @pytest.mark.skipif(
        _MAMBA_AVAILABLE and _NNUNET_AVAILABLE,
        reason="both mamba_ssm and nnunetv2 available"
    )
    def test_u_mamba_build_model_raises_without_deps(self):
        adapter = _get("u_mamba")
        with pytest.raises(RuntimeError):
            adapter.build_model({})

    @pytest.mark.skipif(
        _MAMBA_AVAILABLE and _MONAI_AVAILABLE,
        reason="both mamba_ssm and monai available"
    )
    def test_mamba_vessel_net_build_model_raises_without_deps(self):
        adapter = _get("mamba_vessel_net")
        with pytest.raises(RuntimeError):
            adapter.build_model({})

    @pytest.mark.skipif(
        _NNUNET_AVAILABLE,
        reason="nnunetv2 available — will raise different RuntimeError"
    )
    def test_nnunet_build_model_raises_without_nnunetv2(self):
        adapter = _get("nnunet")
        with pytest.raises(RuntimeError, match="nnunetv2|nnU-Net"):
            adapter.build_model({})

    @pytest.mark.skipif(
        _NNUNET_AVAILABLE,
        reason="nnunetv2 available — will raise different RuntimeError"
    )
    def test_pasc_net_build_model_raises_without_nnunetv2(self):
        adapter = _get("pasc_net")
        with pytest.raises(RuntimeError, match="nnunetv2|nnU-Net|PASC"):
            adapter.build_model({})


# --------------------------------------------------------------------------- #
#  Test 9: forward_adapt RuntimeError（框架依赖型 adapter）
# --------------------------------------------------------------------------- #

class TestForwardAdaptRuntimeError:
    """
    u_mamba / nnunet / pasc_net 的 forward_adapt 在框架外应抛 RuntimeError。

    skipif：若依赖真实存在则跳过。
    """

    @pytest.mark.skipif(
        _MAMBA_AVAILABLE and _NNUNET_AVAILABLE,
        reason="u_mamba deps available"
    )
    def test_u_mamba_forward_adapt_raises(self):
        adapter = _get("u_mamba")
        model = torch.nn.Identity()  # dummy model（forward_adapt 不用到真实模型）
        x = torch.zeros(1, 1, 64, 64)
        with pytest.raises(RuntimeError):
            adapter.forward_adapt(model, x, torch.device("cpu"))

    @pytest.mark.skipif(
        _NNUNET_AVAILABLE,
        reason="nnunetv2 available"
    )
    def test_nnunet_forward_adapt_raises(self):
        adapter = _get("nnunet")
        model = torch.nn.Identity()
        x = torch.zeros(1, 1, 64, 64)
        with pytest.raises(RuntimeError):
            adapter.forward_adapt(model, x, torch.device("cpu"))

    @pytest.mark.skipif(
        _NNUNET_AVAILABLE,
        reason="nnunetv2 available"
    )
    def test_pasc_net_forward_adapt_raises(self):
        adapter = _get("pasc_net")
        model = torch.nn.Identity()
        x = torch.zeros(1, 1, 64, 64)
        with pytest.raises(RuntimeError):
            adapter.forward_adapt(model, x, torch.device("cpu"))


# --------------------------------------------------------------------------- #
#  Test 10: build_optimizer / build_scheduler 接口（无依赖的部分）
# --------------------------------------------------------------------------- #

class TestOptimizerScheduler:
    """
    vm_unet / mamba_vessel_net 的 build_optimizer / build_scheduler
    在缺 mamba_ssm 时仍可构造（optimizer 不需要 mamba kernel）。
    """

    @pytest.mark.skipif(
        _MAMBA_AVAILABLE,
        reason="mamba available, build_model will succeed, different test needed"
    )
    def test_vm_unet_build_optimizer_type(self):
        """vm_unet optimizer = AdamW（不依赖 mamba_ssm）。"""
        adapter = _get("vm_unet")
        # 用一个 tiny dummy model 构建 optimizer
        dummy_model = torch.nn.Linear(4, 4)
        opt = adapter.build_optimizer(dummy_model, {})
        assert isinstance(opt, torch.optim.AdamW), (
            f"vm_unet optimizer should be AdamW, got {type(opt)}"
        )

    @pytest.mark.skipif(
        _MAMBA_AVAILABLE,
        reason="mamba available"
    )
    def test_vm_unet_build_optimizer_lr(self):
        adapter = _get("vm_unet")
        dummy_model = torch.nn.Linear(4, 4)
        opt = adapter.build_optimizer(dummy_model, {"lr": 1e-3})
        lr = opt.param_groups[0]["lr"]
        assert abs(lr - 1e-3) < 1e-10, f"Expected lr=1e-3, got {lr}"

    @pytest.mark.skipif(
        _MAMBA_AVAILABLE,
        reason="mamba available"
    )
    def test_vm_unet_build_scheduler_type(self):
        adapter = _get("vm_unet")
        dummy_model = torch.nn.Linear(4, 4)
        opt = adapter.build_optimizer(dummy_model, {})
        sched = adapter.build_scheduler(opt, {"epochs": 300, "min_lr": 1e-5})
        assert isinstance(sched, torch.optim.lr_scheduler.CosineAnnealingLR), (
            f"vm_unet scheduler should be CosineAnnealingLR, got {type(sched)}"
        )

    @pytest.mark.skipif(
        _MAMBA_AVAILABLE,
        reason="mamba available"
    )
    def test_mamba_vessel_net_build_optimizer_type(self):
        """mamba_vessel_net optimizer = Adam（不依赖 mamba_ssm）。"""
        adapter = _get("mamba_vessel_net")
        dummy_model = torch.nn.Linear(4, 4)
        opt = adapter.build_optimizer(dummy_model, {})
        assert isinstance(opt, torch.optim.Adam), (
            f"mamba_vessel_net optimizer should be Adam, got {type(opt)}"
        )

    @pytest.mark.skipif(
        _MAMBA_AVAILABLE,
        reason="mamba available"
    )
    def test_mamba_vessel_net_build_optimizer_lr(self):
        adapter = _get("mamba_vessel_net")
        dummy_model = torch.nn.Linear(4, 4)
        opt = adapter.build_optimizer(dummy_model, {"lr": 1e-4})
        lr = opt.param_groups[0]["lr"]
        assert abs(lr - 1e-4) < 1e-10, f"Expected lr=1e-4, got {lr}"

    @pytest.mark.skipif(
        _MAMBA_AVAILABLE,
        reason="mamba available"
    )
    def test_mamba_vessel_net_build_scheduler_type(self):
        adapter = _get("mamba_vessel_net")
        dummy_model = torch.nn.Linear(4, 4)
        opt = adapter.build_optimizer(dummy_model, {})
        sched = adapter.build_scheduler(opt, {"epochs": 200, "min_lr": 1e-7})
        assert isinstance(sched, torch.optim.lr_scheduler.CosineAnnealingLR), (
            f"mamba_vessel_net scheduler should be CosineAnnealingLR, got {type(sched)}"
        )


# --------------------------------------------------------------------------- #
#  Test 11: yaml config 字段核实
# --------------------------------------------------------------------------- #

class TestYamlConfig:
    """读取 yaml 文件，核实关键字段值。"""

    _configs_dir = _repo_root / "src" / "configs" / "baselines"

    def _load_yaml(self, filename: str) -> dict:
        """加载 yaml 文件返回 dict。"""
        import yaml
        yaml_path = self._configs_dir / filename
        assert yaml_path.exists(), f"Config file not found: {yaml_path}"
        with open(yaml_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_vmunet_yaml_name(self):
        cfg = self._load_yaml("vmunet.yaml")
        assert cfg["baseline"]["name"] == "vm_unet", (
            f"vmunet.yaml baseline.name should be 'vm_unet', got {cfg['baseline']['name']!r}"
        )

    def test_vmunet_yaml_env_tag(self):
        cfg = self._load_yaml("vmunet.yaml")
        assert cfg["baseline"]["env_tag"] == "mamba", (
            f"vmunet.yaml env_tag should be 'mamba', got {cfg['baseline']['env_tag']!r}"
        )

    def test_vmunet_yaml_epochs(self):
        cfg = self._load_yaml("vmunet.yaml")
        assert cfg["train"]["epochs"] == 300, (
            f"vmunet.yaml epochs should be 300, got {cfg['train']['epochs']}"
        )

    def test_vmunet_yaml_lr(self):
        cfg = self._load_yaml("vmunet.yaml")
        assert abs(float(cfg["train"]["lr"]) - 1e-3) < 1e-10, (
            f"vmunet.yaml lr should be 1e-3, got {cfg['train']['lr']}"
        )

    def test_umamba_yaml_env_tag(self):
        cfg = self._load_yaml("umamba.yaml")
        assert cfg["baseline"]["env_tag"] == "mamba"

    def test_umamba_yaml_optimizer(self):
        cfg = self._load_yaml("umamba.yaml")
        assert cfg["train"]["optimizer"] == "SGD"

    def test_umamba_yaml_epochs(self):
        cfg = self._load_yaml("umamba.yaml")
        assert cfg["train"]["epochs"] == 1000  # nnU-Net 默认

    def test_mambavesselnet_yaml_name(self):
        cfg = self._load_yaml("mambavesselnet.yaml")
        assert cfg["baseline"]["name"] == "mamba_vessel_net"

    def test_mambavesselnet_yaml_epochs(self):
        cfg = self._load_yaml("mambavesselnet.yaml")
        assert cfg["train"]["epochs"] == 200  # 官方 200 epochs

    def test_mambavesselnet_yaml_lr(self):
        cfg = self._load_yaml("mambavesselnet.yaml")
        assert abs(float(cfg["train"]["lr"]) - 1e-4) < 1e-10

    def test_nnunet_yaml_env_tag(self):
        cfg = self._load_yaml("nnunet.yaml")
        assert cfg["baseline"]["env_tag"] == "main"

    def test_nnunet_yaml_epochs(self):
        cfg = self._load_yaml("nnunet.yaml")
        assert cfg["train"]["epochs"] == 1000

    def test_nnunet_yaml_optimizer(self):
        cfg = self._load_yaml("nnunet.yaml")
        assert cfg["train"]["optimizer"] == "SGD"

    def test_pascnet_yaml_env_tag(self):
        cfg = self._load_yaml("pascnet.yaml")
        assert cfg["baseline"]["env_tag"] == "main"

    def test_pascnet_yaml_epochs(self):
        cfg = self._load_yaml("pascnet.yaml")
        assert cfg["train"]["epochs"] == 300  # PASC-Net 自定义 300

    def test_pascnet_yaml_loss_weights(self):
        """核实 PASC-Net 官方 loss 权重（0.7/0.1/0.1/0.1）。"""
        cfg = self._load_yaml("pascnet.yaml")
        loss = cfg["loss"]
        assert abs(float(loss["weight_dc_ce"]) - 0.7) < 1e-9
        assert abs(float(loss["weight_con1"]) - 0.1) < 1e-9
        assert abs(float(loss["weight_con3"]) - 0.1) < 1e-9
        assert abs(float(loss["weight_cldice"]) - 0.1) < 1e-9

    def test_pascnet_yaml_trainer(self):
        cfg = self._load_yaml("pascnet.yaml")
        assert cfg["model"]["trainer"] == "PASCTrainer"


# --------------------------------------------------------------------------- #
#  Test 12: vm_unet forward_adapt 接口（有 mamba_ssm 时真测）
# --------------------------------------------------------------------------- #

class TestVMUNetForwardAdaptWithMamba:
    """
    vm_unet forward_adapt 真实测试（需 mamba_ssm）。
    无 mamba_ssm 时跳过。
    """

    @pytest.mark.skipif(
        not _MAMBA_AVAILABLE,
        reason="mamba_ssm not installed — skipping vm_unet true forward test"
    )
    def test_vm_unet_forward_adapt_shape(self):
        """有 mamba_ssm 时：build_model + forward_adapt (1,1,64,64) → (1,1,64,64)。"""
        adapter = _get("vm_unet")
        cfg = {}
        model = adapter.build_model(cfg)
        model.eval()
        device = torch.device("cpu")

        x = torch.zeros(1, 1, 64, 64)
        out = adapter.forward_adapt(model, x, device)

        assert out.shape == (1, 1, 64, 64), (
            f"vm_unet forward_adapt shape mismatch: {out.shape}"
        )
        assert out.ndim == 4


# --------------------------------------------------------------------------- #
#  Test 13: mm_unet adapter（MM-UNet, Morph Mamba UNet）
# --------------------------------------------------------------------------- #

class TestMMUNetAdapter:
    """
    MM-UNet (mm_unet) adapter 测试。
    覆盖：
      - 注册成功（mm_unet 在 MODEL_REGISTRY 中）
      - validate_attrs 通过（name/kind/source_repo/env_tag 合法）
      - env_tag='mamba'
      - kind='architecture'
      - source_repo 含 liujiawen-jpg
      - preprocess_cfg 字段完整 + 关键值正确
      - build_loss 返回 callable（lazy init，不需要 monai 真实安装）
      - build_model 在缺 mamba_ssm 时抛 RuntimeError（含 'mamba' 字样）
      - build_optimizer 返回 AdamW（不依赖 mamba_ssm）
      - build_scheduler 返回 _LinearWarmupCosineAnnealingLR（不依赖 mamba_ssm）
      - yaml config 关键字段正确
    """

    def test_mm_unet_registered(self):
        """mm_unet 在 MODEL_REGISTRY 中。"""
        from baselines.registry import MODEL_REGISTRY
        assert "mm_unet" in MODEL_REGISTRY, (
            f"mm_unet not in MODEL_REGISTRY. Found: {sorted(MODEL_REGISTRY.keys())}"
        )

    def test_mm_unet_validate_attrs(self):
        """validate_attrs 不抛（所有必要属性已设）。"""
        adapter = _get("mm_unet")
        adapter.validate_attrs()  # 不抛即通过

    def test_mm_unet_env_tag(self):
        """env_tag='mamba'（需 mamba_venv）。"""
        adapter = _get("mm_unet")
        assert adapter.env_tag == "mamba", (
            f"mm_unet env_tag should be 'mamba', got {adapter.env_tag!r}"
        )

    def test_mm_unet_kind(self):
        """kind='architecture'。"""
        adapter = _get("mm_unet")
        assert adapter.kind == "architecture", (
            f"mm_unet kind should be 'architecture', got {adapter.kind!r}"
        )

    def test_mm_unet_source_repo(self):
        """source_repo 是 https:// URL，含 liujiawen-jpg。"""
        adapter = _get("mm_unet")
        assert adapter.source_repo.startswith("https://"), (
            f"mm_unet source_repo should be https URL, got: {adapter.source_repo!r}"
        )
        assert "liujiawen-jpg" in adapter.source_repo, (
            f"mm_unet source_repo should contain 'liujiawen-jpg', "
            f"got: {adapter.source_repo!r}"
        )

    def test_mm_unet_preprocess_cfg_keys(self):
        """preprocess_cfg 包含所有必要字段。"""
        _REQUIRED_KEYS = ["channels", "input_mode", "patch_size", "clahe", "normalize", "extra"]
        adapter = _get("mm_unet")
        cfg = adapter.preprocess_cfg()
        for key in _REQUIRED_KEYS:
            assert key in cfg, (
                f"mm_unet preprocess_cfg missing key: {key!r}. "
                f"Got keys: {sorted(cfg.keys())}"
            )

    def test_mm_unet_preprocess_cfg_values(self):
        """preprocess_cfg 关键值正确（3ch RGB, fullimg, ImageNet 归一化）。"""
        adapter = _get("mm_unet")
        cfg = adapter.preprocess_cfg()
        # 3 通道 RGB（MM_Net encoder1=Conv2d(3,64,...)）
        assert cfg["channels"] == "rgb", (
            f"mm_unet channels should be 'rgb', got {cfg['channels']!r}"
        )
        assert cfg["input_mode"] == "fullimg", (
            f"mm_unet input_mode should be 'fullimg', got {cfg['input_mode']!r}"
        )
        assert cfg["patch_size"] is None
        assert cfg["clahe"] is False
        # ImageNet 归一化（官方 config.yml）
        norm = cfg["normalize"]
        assert abs(norm["mean"][0] - 0.485) < 1e-6, (
            f"mm_unet normalize mean[0] should be 0.485, got {norm['mean'][0]}"
        )
        assert abs(norm["std"][0] - 0.229) < 1e-6, (
            f"mm_unet normalize std[0] should be 0.229, got {norm['std'][0]}"
        )
        # resize=608 in extra
        assert "resize" in cfg["extra"], "mm_unet extra should have 'resize' key"
        assert cfg["extra"]["resize"] == 608, (
            f"mm_unet resize should be 608 (DRIVE), got {cfg['extra']['resize']}"
        )

    def test_mm_unet_build_loss_callable(self):
        """build_loss 返回 callable（lazy init，不需 monai 真实可用）。"""
        adapter = _get("mm_unet")
        loss_fn = adapter.build_loss({})
        assert callable(loss_fn), "mm_unet build_loss should return callable"

    @pytest.mark.skipif(
        _MAMBA_AVAILABLE,
        reason="mamba_ssm available — build_model will not raise RuntimeError"
    )
    def test_mm_unet_build_model_raises_without_mamba(self):
        """缺 mamba_ssm 时 build_model 抛 RuntimeError（含 'mamba' 字样）。"""
        adapter = _get("mm_unet")
        with pytest.raises(RuntimeError, match="mamba"):
            adapter.build_model({})

    @pytest.mark.skipif(
        _MAMBA_AVAILABLE,
        reason="mamba available, build_model will succeed, different test needed"
    )
    def test_mm_unet_build_optimizer_adamw(self):
        """build_optimizer 返回 AdamW（不依赖 mamba_ssm）。"""
        adapter = _get("mm_unet")
        dummy_model = torch.nn.Linear(4, 4)
        opt = adapter.build_optimizer(dummy_model, {})
        assert isinstance(opt, torch.optim.AdamW), (
            f"mm_unet optimizer should be AdamW, got {type(opt)}"
        )

    @pytest.mark.skipif(
        _MAMBA_AVAILABLE,
        reason="mamba available"
    )
    def test_mm_unet_build_optimizer_lr(self):
        """build_optimizer lr=0.001（官方）。"""
        adapter = _get("mm_unet")
        dummy_model = torch.nn.Linear(4, 4)
        opt = adapter.build_optimizer(dummy_model, {"lr": 1e-3})
        lr = opt.param_groups[0]["lr"]
        assert abs(lr - 1e-3) < 1e-10, f"mm_unet optimizer lr should be 1e-3, got {lr}"

    @pytest.mark.skipif(
        _MAMBA_AVAILABLE,
        reason="mamba available"
    )
    def test_mm_unet_build_optimizer_wd(self):
        """build_optimizer weight_decay=0.05（官方）。"""
        adapter = _get("mm_unet")
        dummy_model = torch.nn.Linear(4, 4)
        opt = adapter.build_optimizer(dummy_model, {})
        wd = opt.param_groups[0]["weight_decay"]
        assert abs(wd - 0.05) < 1e-10, f"mm_unet wd should be 0.05, got {wd}"

    @pytest.mark.skipif(
        _MAMBA_AVAILABLE,
        reason="mamba available"
    )
    def test_mm_unet_build_scheduler_type(self):
        """build_scheduler 返回 _LinearWarmupCosineAnnealingLR（官方）。"""
        from baselines.adapters.mm_unet import _LinearWarmupCosineAnnealingLR
        adapter = _get("mm_unet")
        dummy_model = torch.nn.Linear(4, 4)
        opt = adapter.build_optimizer(dummy_model, {})
        sched = adapter.build_scheduler(opt, {"warmup_epochs": 2, "epochs": 500, "min_lr": 1e-7})
        assert isinstance(sched, _LinearWarmupCosineAnnealingLR), (
            f"mm_unet scheduler should be _LinearWarmupCosineAnnealingLR, got {type(sched)}"
        )

    def test_mm_unet_yaml_name(self):
        """yaml baseline.name == 'mm_unet'。"""
        import yaml
        yaml_path = _repo_root / "src" / "configs" / "baselines" / "mm_unet.yaml"
        assert yaml_path.exists(), f"mm_unet.yaml not found: {yaml_path}"
        with open(yaml_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert cfg["baseline"]["name"] == "mm_unet", (
            f"mm_unet.yaml baseline.name should be 'mm_unet', got {cfg['baseline']['name']!r}"
        )

    def test_mm_unet_yaml_env_tag(self):
        """yaml baseline.env_tag == 'mamba'。"""
        import yaml
        yaml_path = _repo_root / "src" / "configs" / "baselines" / "mm_unet.yaml"
        with open(yaml_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert cfg["baseline"]["env_tag"] == "mamba", (
            f"mm_unet.yaml env_tag should be 'mamba', got {cfg['baseline']['env_tag']!r}"
        )

    def test_mm_unet_yaml_epochs(self):
        """yaml train.epochs == 500（论文值，TODO-1）。"""
        import yaml
        yaml_path = _repo_root / "src" / "configs" / "baselines" / "mm_unet.yaml"
        with open(yaml_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert cfg["train"]["epochs"] == 500, (
            f"mm_unet.yaml epochs should be 500 (paper), got {cfg['train']['epochs']}"
        )

    def test_mm_unet_yaml_lr(self):
        """yaml train.lr == 1e-3（官方）。"""
        import yaml
        yaml_path = _repo_root / "src" / "configs" / "baselines" / "mm_unet.yaml"
        with open(yaml_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert abs(float(cfg["train"]["lr"]) - 1e-3) < 1e-10, (
            f"mm_unet.yaml lr should be 1e-3, got {cfg['train']['lr']}"
        )

    def test_mm_unet_yaml_weight_decay(self):
        """yaml train.weight_decay == 0.05（官方 config.yml）。"""
        import yaml
        yaml_path = _repo_root / "src" / "configs" / "baselines" / "mm_unet.yaml"
        with open(yaml_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert abs(float(cfg["train"]["weight_decay"]) - 0.05) < 1e-10, (
            f"mm_unet.yaml weight_decay should be 0.05, got {cfg['train']['weight_decay']}"
        )

    def test_mm_unet_yaml_min_lr(self):
        """yaml train.min_lr == 1e-7（官方 config.yml）。"""
        import yaml
        yaml_path = _repo_root / "src" / "configs" / "baselines" / "mm_unet.yaml"
        with open(yaml_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert abs(float(cfg["train"]["min_lr"]) - 1e-7) < 1e-9, (
            f"mm_unet.yaml min_lr should be 1e-7, got {cfg['train']['min_lr']}"
        )

    def test_mm_unet_yaml_loss_type(self):
        """yaml loss.type == 'DiceFocalLoss'（官方）。"""
        import yaml
        yaml_path = _repo_root / "src" / "configs" / "baselines" / "mm_unet.yaml"
        with open(yaml_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert cfg["loss"]["type"] == "DiceFocalLoss", (
            f"mm_unet.yaml loss.type should be 'DiceFocalLoss', got {cfg['loss']['type']!r}"
        )

    def test_mm_unet_yaml_license(self):
        """yaml baseline.license == 'MIT'。"""
        import yaml
        yaml_path = _repo_root / "src" / "configs" / "baselines" / "mm_unet.yaml"
        with open(yaml_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert cfg["baseline"]["license"] == "MIT", (
            f"mm_unet.yaml license should be 'MIT', got {cfg['baseline']['license']!r}"
        )


# --------------------------------------------------------------------------- #
#  __main__ guard（Windows spawn 安全）
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
