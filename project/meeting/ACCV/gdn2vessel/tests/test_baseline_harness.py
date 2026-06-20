"""
test_baseline_harness.py — pytest for baseline harness 骨架。

覆盖：
  1. registry 注册 / 取用（register 装饰器 + get_adapter 工厂）
  2. 两个示例 adapter (ours_gdn2 / backbone_unet) build_model 输出正确 shape
  3. evaluate.py 重叠轴纯 numpy 实现（_compute_overlap_metrics + _roc_auc_numpy）
  4. evaluate_adapter 在合成小图上跑通三轴（CPU，无 GPU）并输出 CSV
  5. adapter validate_attrs 错误捕获（防漏填 name/kind）

Windows 规范：
  - num_workers=0
  - if __name__ == '__main__' guard
  - 绝对路径（tmpdir via tmp_path fixture）
  - 无 scipy.stats
  - FLA mock（同 test_shapes.py 策略）
"""

from __future__ import annotations

import csv
import os
import sys
import types
import tempfile
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
#  Mock FLA（同 test_shapes.py，避免无 FLA 环境 import 炸）
# --------------------------------------------------------------------------- #

def _mock_fla():
    if "fla" in sys.modules:
        return  # 已 mock 或已装
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
#  Fixture: 小型合成 DRIVE-like 数据集（无需真实数据）
# --------------------------------------------------------------------------- #

@pytest.fixture
def synth_drive_root(tmp_path: Path) -> Path:
    """
    在 tmp_path 内生成一个 DRIVE-like 目录结构（单张 64×64 假图）。
    image: uint8 随机，saved as .tif via PIL/opencv
    gt:    简单竖线当血管，saved as .gif
    mask:  全 1，saved as .gif
    """
    try:
        from PIL import Image
    except ImportError:
        pytest.skip("PIL (Pillow) required for synth_drive_root fixture")

    root = tmp_path / "DRIVE"
    for subdir in [
        "training/images",
        "training/1st_manual",
        "training/mask",
    ]:
        (root / subdir).mkdir(parents=True, exist_ok=True)

    H, W = 64, 64
    rng = np.random.default_rng(0)

    # 只生成 1 张（id=21），split='all' 用所有 TRAINING_IDS，这里只 mock val split
    # DRIVEDataset.VAL_IDS = [37,38,39,40] — 生成这 4 张
    for sid in [37, 38, 39, 40]:
        # image (RGB tif → green channel 才是真正用的)
        img_arr = rng.integers(80, 200, (H, W, 3), dtype=np.uint8)
        Image.fromarray(img_arr, mode="RGB").save(
            str(root / "training" / "images" / f"{sid}_training.tif")
        )

        # GT: 中间竖线（5 pixel wide）当血管
        gt_arr = np.zeros((H, W), dtype=np.uint8)
        gt_arr[:, W // 2 - 2 : W // 2 + 3] = 255
        Image.fromarray(gt_arr, mode="L").save(
            str(root / "training" / "1st_manual" / f"{sid}_manual1.gif")
        )

        # FOV mask: 全 1
        mask_arr = np.ones((H, W), dtype=np.uint8) * 255
        Image.fromarray(mask_arr, mode="L").save(
            str(root / "training" / "mask" / f"{sid}_training_mask.gif")
        )

    return root


@pytest.fixture
def tiny_ckpt(tmp_path: Path) -> Path:
    """
    保存一个 backbone_unet 的随机初始化 state_dict 作为 mock ckpt。
    """
    from models.unet import UNet
    model = UNet(in_ch=1, out_ch=1, base_ch=32)
    ckpt_path = tmp_path / "best.pth"
    torch.save(model.state_dict(), str(ckpt_path))
    return ckpt_path


@pytest.fixture
def tiny_gdn2_ckpt(tmp_path: Path) -> Path:
    """
    保存一个 UNetGDN2 (base_ch=16) 随机初始化 state_dict。
    """
    from models.unet_gdn2 import UNetGDN2
    model = UNetGDN2(in_ch=1, out_ch=1, base_ch=16, use_memory=False, backend="naive")
    ckpt_path = tmp_path / "gdn2_best.pth"
    torch.save(model.state_dict(), str(ckpt_path))
    return ckpt_path


# --------------------------------------------------------------------------- #
#  Test 1: registry 注册 / 取用
# --------------------------------------------------------------------------- #

class TestRegistry:
    """registry 注册 / get_adapter / list_adapters 测试。"""

    def test_auto_discover_registers_known_adapters(self):
        """auto_discover 后 backbone_unet 和 ours_gdn2 必须在 registry 里。"""
        import baselines  # 触发 auto_discover
        from baselines.registry import MODEL_REGISTRY

        assert "backbone_unet" in MODEL_REGISTRY, (
            f"backbone_unet not found. Registered: {sorted(MODEL_REGISTRY.keys())}"
        )
        assert "ours_gdn2" in MODEL_REGISTRY, (
            f"ours_gdn2 not found. Registered: {sorted(MODEL_REGISTRY.keys())}"
        )

    def test_get_adapter_returns_instance(self):
        """get_adapter 返回 adapter 实例（非 class）。"""
        import baselines
        from baselines.registry import get_adapter
        from baselines.base_adapter import BaselineAdapter

        adapter = get_adapter("backbone_unet")
        assert isinstance(adapter, BaselineAdapter)

    def test_get_adapter_creates_new_instance_each_call(self):
        """每次 get_adapter 返回不同实例（无状态，避免共享引用）。"""
        import baselines
        from baselines.registry import get_adapter

        a1 = get_adapter("backbone_unet")
        a2 = get_adapter("backbone_unet")
        assert a1 is not a2

    def test_get_adapter_unknown_name_raises(self):
        """不存在的 adapter name 抛 KeyError（附已注册列表）。"""
        import baselines
        from baselines.registry import get_adapter

        with pytest.raises(KeyError, match="not found"):
            get_adapter("nonexistent_baseline_xyz")

    def test_list_adapters_sorted(self):
        """list_adapters 返回排序 list，包含已注册的 adapter。"""
        import baselines
        from baselines.registry import list_adapters

        names = list_adapters()
        assert isinstance(names, list)
        assert names == sorted(names), "list_adapters must be sorted"
        assert "backbone_unet" in names
        assert "ours_gdn2" in names

    def test_register_validates_attrs(self):
        """register 装饰器对 name 为空的 class 抛 ValueError。"""
        from baselines.registry import register
        from baselines.base_adapter import BaselineAdapter

        with pytest.raises((ValueError, TypeError)):
            @register
            class BadAdapter(BaselineAdapter):
                name = ""  # 故意空
                kind = "architecture"
                source_repo = "http://example.com"
                env_tag = "main"

                def build_model(self, cfg): ...
                def build_loss(self, cfg): ...
                def build_optimizer(self, model, cfg): ...
                def preprocess_cfg(self): return {}
                def forward_adapt(self, model, x, device): ...


# --------------------------------------------------------------------------- #
#  Test 2: adapter build_model shape
# --------------------------------------------------------------------------- #

class TestAdapterBuildModel:
    """两个示例 adapter build_model 输出 shape 验证。"""

    def test_backbone_unet_output_shape(self):
        """BackboneUNetAdapter.build_model → UNet(32) → output (B,1,H,W)。"""
        import baselines
        from baselines.registry import get_adapter

        adapter = get_adapter("backbone_unet")
        model = adapter.build_model({})
        model.eval()

        B, H, W = 1, 64, 64
        with torch.no_grad():
            x = torch.randn(B, 1, H, W)
            out = model(x)

        assert out.shape == (B, 1, H, W), f"Expected (1,1,64,64), got {out.shape}"

    def test_backbone_unet_base_ch_locked(self):
        """BackboneUNetAdapter 忽略 cfg 中的 base_ch，固定 32。"""
        import baselines
        from baselines.registry import get_adapter
        from models.unet import UNet

        adapter = get_adapter("backbone_unet")
        # 传 base_ch=16（应被忽略）
        model = adapter.build_model({"base_ch": 16})
        # 参数量应等于 UNet(base_ch=32)
        ref_model = UNet(in_ch=1, out_ch=1, base_ch=32)
        assert (
            sum(p.numel() for p in model.parameters())
            == sum(p.numel() for p in ref_model.parameters())
        ), "backbone_unet must lock base_ch=32 regardless of cfg"

    def test_ours_gdn2_output_shape_no_memory(self):
        """OursGDN2Adapter.build_model(use_memory=False) → (B,1,H,W)。"""
        import baselines
        from baselines.registry import get_adapter

        adapter = get_adapter("ours_gdn2")
        cfg = {"base_ch": 16, "use_memory": False, "backend": "naive"}
        model = adapter.build_model(cfg)
        model.eval()

        B, H, W = 1, 64, 64
        with torch.no_grad():
            x = torch.randn(B, 1, H, W)
            out = model(x)

        assert out.shape == (B, 1, H, W), f"Expected (1,1,64,64), got {out.shape}"

    def test_ours_gdn2_output_shape_with_memory(self):
        """OursGDN2Adapter.build_model(use_memory=True) → (B,1,H,W)。"""
        import baselines
        from baselines.registry import get_adapter

        adapter = get_adapter("ours_gdn2")
        cfg = {"base_ch": 16, "use_memory": True, "backend": "naive"}
        model = adapter.build_model(cfg)
        model.eval()

        B, H, W = 1, 64, 64
        with torch.no_grad():
            x = torch.randn(B, 1, H, W)
            out = model(x)

        assert out.shape == (B, 1, H, W), f"Expected (1,1,64,64), got {out.shape}"

    def test_forward_adapt_contract(self):
        """forward_adapt 返回 (B,1,H,W) logits（不带 sigmoid）。"""
        import baselines
        from baselines.registry import get_adapter

        for adapter_name in ["backbone_unet", "ours_gdn2"]:
            adapter = get_adapter(adapter_name)
            cfg = {"base_ch": 16, "use_memory": False}  # ours_gdn2 用
            model = adapter.build_model(cfg)
            model.eval()

            device = torch.device("cpu")
            x = torch.randn(1, 1, 64, 64)
            logits = adapter.forward_adapt(model, x, device)

            assert logits.ndim == 4, f"{adapter_name}: logits must be 4D"
            assert logits.shape[1] == 1, f"{adapter_name}: logits must have out_ch=1"
            assert logits.shape[2:] == (64, 64), \
                f"{adapter_name}: spatial dims must match input"


# --------------------------------------------------------------------------- #
#  Test 3: 重叠轴纯 numpy 实现
# --------------------------------------------------------------------------- #

class TestOverlapMetrics:
    """_compute_overlap_metrics + _roc_auc_numpy 单元测试。"""

    def _import_metrics(self):
        from evaluate import _compute_overlap_metrics, _roc_auc_numpy
        return _compute_overlap_metrics, _roc_auc_numpy

    def test_perfect_prediction(self):
        """pred == gt → dice=1, iou=1, se=1, sp=1。"""
        _cm, _ = self._import_metrics()
        H, W = 32, 32
        gt = np.zeros((H, W), dtype=np.uint8)
        gt[10:20, 10:20] = 1
        fov = np.ones((H, W), dtype=np.uint8)
        metrics = _cm(gt.copy(), gt, fov)

        assert abs(metrics["dice"] - 1.0) < 1e-4, f"dice={metrics['dice']}"
        assert abs(metrics["iou"] - 1.0) < 1e-4
        assert abs(metrics["se"] - 1.0) < 1e-4
        assert abs(metrics["sp"] - 1.0) < 1e-4

    def test_empty_prediction(self):
        """pred = all 0, gt 有前景 → dice ≈ 0, se ≈ 0, sp ≈ 1。"""
        _cm, _ = self._import_metrics()
        H, W = 32, 32
        gt = np.zeros((H, W), dtype=np.uint8)
        gt[10:20, 10:20] = 1
        pred = np.zeros((H, W), dtype=np.uint8)
        fov = np.ones((H, W), dtype=np.uint8)
        metrics = _cm(pred, gt, fov)

        assert metrics["dice"] < 0.1, f"dice={metrics['dice']}"
        assert metrics["se"] < 0.1, f"se={metrics['se']}"
        assert metrics["sp"] > 0.9, f"sp={metrics['sp']}"

    def test_fov_mask_excludes_outside(self):
        """FOV=0 区域不计入指标（预测错误在 FOV 外不影响 dice）。"""
        _cm, _ = self._import_metrics()
        H, W = 32, 32
        gt = np.zeros((H, W), dtype=np.uint8)
        gt[10:20, 10:20] = 1                  # GT 在 FOV 内
        pred = gt.copy()
        pred[0:5, 0:5] = 1                    # 额外误报在 FOV 外
        fov = np.zeros((H, W), dtype=np.uint8)
        fov[5:27, 5:27] = 1                   # FOV 覆盖 GT 区域但不含 [0:5,0:5]
        metrics_with_fov = _cm(pred, gt, fov)
        metrics_no_fov = _cm(pred, gt, np.ones((H, W), dtype=np.uint8))

        # FOV 内误报 = 0，dice 应 = 1
        assert abs(metrics_with_fov["dice"] - 1.0) < 1e-3
        # 全图有误报，dice < 1
        assert metrics_no_fov["dice"] < 1.0

    def test_roc_auc_random_better_than_half(self):
        """完美 prob（GT=1 → prob=0.99，GT=0 → prob=0.01）→ AUC ≈ 1.0。"""
        _, _roc = self._import_metrics()
        rng = np.random.default_rng(42)
        labels = rng.integers(0, 2, 100).astype(np.float32)
        # 给正样本高 score，负样本低 score
        scores = np.where(labels == 1, 0.9 + 0.1 * rng.random(100),
                          0.0 + 0.1 * rng.random(100)).astype(np.float32)
        auc = _roc(scores, labels)
        assert auc > 0.95, f"Expected AUC>0.95 for near-perfect scores, got {auc}"

    def test_roc_auc_degenerate(self):
        """全 0 label → AUC = 0.5（退化）。"""
        _, _roc = self._import_metrics()
        labels = np.zeros(50, dtype=np.float32)
        scores = np.random.rand(50).astype(np.float32)
        auc = _roc(scores, labels)
        assert auc == 0.5, f"Expected 0.5 for degenerate, got {auc}"


# --------------------------------------------------------------------------- #
#  Test 4: evaluate_adapter 端到端（合成小图）
# --------------------------------------------------------------------------- #

class TestEvaluateAdapter:
    """evaluate_adapter 在合成 DRIVE 数据上跑通三轴并写 CSV。"""

    def test_backbone_unet_evaluate_produces_csv(
        self,
        synth_drive_root: Path,
        tiny_ckpt: Path,
        tmp_path: Path,
    ):
        """
        backbone_unet adapter + mock ckpt + 合成 DRIVE 数据 → 写出 CSV，
        验证：CSV 文件存在、行数正确、列名完整、dice 列为 float。
        """
        from evaluate import evaluate_adapter

        csv_path = tmp_path / "eval_out.csv"

        rows = evaluate_adapter(
            adapter_name="backbone_unet",
            ckpt_path=str(tiny_ckpt),
            data_root=str(synth_drive_root),
            dataset="DRIVE",
            split="val",      # VAL_IDS = [37,38,39,40] → 4 张
            seed=42,
            threshold=0.5,
            output_csv=str(csv_path),
            device_str="cpu",
            use_external_topo=False,  # 强制 fallback，不依赖 clDice 包
        )

        # 返回值检查
        assert isinstance(rows, list), "evaluate_adapter must return list"
        assert len(rows) == 4, f"Expected 4 rows (val split), got {len(rows)}"

        # CSV 文件存在
        assert csv_path.exists(), "CSV file not created"

        # 读 CSV 核列名 + 行数
        with open(str(csv_path), newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            csv_rows = list(reader)

        assert len(csv_rows) == 4, f"Expected 4 CSV rows, got {len(csv_rows)}"

        required_cols = [
            "dataset", "baseline", "kind", "seed", "split",
            "dice", "iou", "auc", "se", "sp",
            "cldice", "betti_b0_err", "betti_b1_err", "skeleton_recall", "topo_source",
            "epsilon_beta0", "success_rate", "reid_rate", "n_gaps",
            "ckpt_path", "eval_input_mode", "threshold", "git_commit",
        ]
        for col in required_cols:
            assert col in csv_rows[0], f"Column {col!r} missing from CSV"

        # dice 是合理 float
        for row in csv_rows:
            dice_val = float(row["dice"])
            assert 0.0 <= dice_val <= 1.0, f"dice={dice_val} out of [0,1]"

        # baseline 列对
        for row in csv_rows:
            assert row["baseline"] == "backbone_unet"
            assert row["eval_input_mode"] == "fullimg"

    def test_evaluate_no_csv_output(
        self,
        synth_drive_root: Path,
        tiny_ckpt: Path,
    ):
        """output_csv=None 时，不写文件，只返回 rows。"""
        from evaluate import evaluate_adapter

        rows = evaluate_adapter(
            adapter_name="backbone_unet",
            ckpt_path=str(tiny_ckpt),
            data_root=str(synth_drive_root),
            dataset="DRIVE",
            split="val",
            seed=1,
            output_csv=None,
            device_str="cpu",
            use_external_topo=False,
        )
        assert len(rows) == 4

    def test_epsilon_beta0_computed(
        self,
        synth_drive_root: Path,
        tiny_ckpt: Path,
        tmp_path: Path,
    ):
        """续连轴的 epsilon_beta0 应被计算（无 break_results 时也算）。"""
        from evaluate import evaluate_adapter

        rows = evaluate_adapter(
            adapter_name="backbone_unet",
            ckpt_path=str(tiny_ckpt),
            data_root=str(synth_drive_root),
            split="val",
            output_csv=None,
            device_str="cpu",
            use_external_topo=False,
        )
        for row in rows:
            assert "epsilon_beta0" in row
            assert isinstance(row["epsilon_beta0"], float)
            assert row["epsilon_beta0"] >= 0.0

    def test_success_rate_nan_without_break_results(
        self,
        synth_drive_root: Path,
        tiny_ckpt: Path,
    ):
        """无 break_results → success_rate = NaN（原图无 gap，续连轴跳过）。"""
        from evaluate import evaluate_adapter
        import math

        rows = evaluate_adapter(
            adapter_name="backbone_unet",
            ckpt_path=str(tiny_ckpt),
            data_root=str(synth_drive_root),
            split="val",
            output_csv=None,
            device_str="cpu",
            use_external_topo=False,
        )
        for row in rows:
            assert math.isnan(row["success_rate"]), (
                f"success_rate should be NaN without break_results, "
                f"got {row['success_rate']}"
            )


# --------------------------------------------------------------------------- #
#  Test 5: adapter validate_attrs 边界
# --------------------------------------------------------------------------- #

class TestAdapterValidation:
    """BaselineAdapter.validate_attrs() 边界测试。"""

    def test_validate_passes_for_valid_adapter(self):
        """合法 adapter 不抛异常。"""
        import baselines
        from baselines.registry import get_adapter

        adapter = get_adapter("backbone_unet")
        adapter.validate_attrs()  # 不应抛

    def test_validate_fails_for_bad_kind(self):
        """kind 非法值 → validate_attrs 抛 ValueError。"""
        from baselines.base_adapter import BaselineAdapter

        class FakeAdapter(BaselineAdapter):
            name = "fake"
            kind = "wrong_kind"       # 非法
            source_repo = "http://x"
            env_tag = "main"

            def build_model(self, cfg): ...
            def build_loss(self, cfg): ...
            def build_optimizer(self, model, cfg): ...
            def preprocess_cfg(self): return {}
            def forward_adapt(self, model, x, device): ...

        with pytest.raises(ValueError, match="kind"):
            FakeAdapter().validate_attrs()

    def test_validate_fails_for_bad_env_tag(self):
        """env_tag 非法值 → validate_attrs 抛 ValueError。"""
        from baselines.base_adapter import BaselineAdapter

        class FakeAdapter2(BaselineAdapter):
            name = "fake2"
            kind = "architecture"
            source_repo = "http://x"
            env_tag = "conda"          # 非法

            def build_model(self, cfg): ...
            def build_loss(self, cfg): ...
            def build_optimizer(self, model, cfg): ...
            def preprocess_cfg(self): return {}
            def forward_adapt(self, model, x, device): ...

        with pytest.raises(ValueError, match="env_tag"):
            FakeAdapter2().validate_attrs()

    def test_preprocess_cfg_returns_dict(self):
        """两个示例 adapter 的 preprocess_cfg 均返回 dict，含必要 key。"""
        import baselines
        from baselines.registry import get_adapter

        required_keys = {"channels", "normalize", "input_mode", "patch_size", "clahe"}
        for name in ["backbone_unet", "ours_gdn2"]:
            adapter = get_adapter(name)
            pcfg = adapter.preprocess_cfg()
            assert isinstance(pcfg, dict), f"{name}.preprocess_cfg must return dict"
            for k in required_keys:
                assert k in pcfg, f"{name}.preprocess_cfg missing key {k!r}"


# --------------------------------------------------------------------------- #
#  Windows __main__ guard
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    # 可直接 python tests/test_baseline_harness.py 运行（Windows spawn 安全）
    pytest.main([__file__, "-v", "--tb=short"])
