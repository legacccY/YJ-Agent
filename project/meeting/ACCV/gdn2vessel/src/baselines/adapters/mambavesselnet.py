"""
mambavesselnet.py — Adapter for MambaVesselNet++ (MVN++).

官方 repo  : https://github.com/CC0117/MambaVesselNet  (MIT)
官方论文   : TOMM 2025 arXiv 2411.11946
官方超参   : Adam lr=1e-4; CosineAnnealingLR min_lr=1e-7; epochs=200; batch=16;
             loss=Dice+CE（官方 utils/criterion.py）。
             input_size: TODO — repo train.py 是 3D，arXiv 2D 分支 input size 未同步。
             Source: BASELINE_SPEC §1 + github.com/CC0117/MambaVesselNet

架构特点   : 3D Mamba-based vessel segmentation（MONAI UnetrBasicBlock/UnetrUpBlock 骨架）。
             vendor mvn.py 是 3D Conv3d 架构（spatial_dims=3），非 2D。
             2D 视网膜血管分割需要适配：用 2D placeholder 或 spatial_dims=2 配置。
             vendor 已 curl 到 third_party/MambaVesselNet/（MIT）。

env_tag    : 'mamba'（依赖 mamba_ssm + monai）

重要说明   :
  - vendor mvn.py（mvnNet）全部是 3D（Conv3d），直接用于 2D 视网膜需要
    spatial_dims=2 或换 2D 分支——官方 repo 仅有 3D train.py，arXiv 提到 2D 变体但代码未同步。
  - TODO_researcher: MambaVesselNet++ 2D 视网膜 input_size 未在官方 repo 中明示；
    需查 arXiv 2411.11946 正文或联系作者 issue 确认 2D 分支实现。
  - 本 adapter 在 mamba_venv + monai 满足时尝试 2D 配置实例化；
    若 vendor 3D 限制无法绕过，降档 C 引文献数字（BASELINE_SPEC §3 退路）。

Windows 规范 :
  - 无 scipy.stats
  - 无 multiprocessing
  - 路径用 pathlib.Path
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Optional

import torch
import torch.nn as nn

# 确保 src/ 在 sys.path
_src_dir = Path(__file__).parent.parent.parent
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from baselines.base_adapter import BaselineAdapter, ENV_MAMBA, KIND_ARCHITECTURE
from baselines.registry import register

# vendor 路径（curl 已完成）
_VENDOR_DIR = Path(__file__).parent.parent / "third_party" / "MambaVesselNet"


# --------------------------------------------------------------------------- #
#  Runtime 依赖检查 helper
# --------------------------------------------------------------------------- #

def _require_mvn_env() -> None:
    """
    检查 MambaVesselNet++ 所需运行时依赖。
    需要：mamba_ssm + monai。

    Raises:
        RuntimeError: 依赖缺失时抛出，含 HPC 指引。
    """
    missing = []
    try:
        import mamba_ssm  # noqa: F401
    except ImportError:
        missing.append("mamba-ssm")

    try:
        import monai  # noqa: F401
    except ImportError:
        missing.append("monai")

    if missing:
        raise RuntimeError(
            f"MambaVesselNet++ 需要以下依赖（当前缺失：{missing}）。\n"
            "请在 HPC mamba_venv 中安装（见 BASELINE_SPEC §3）：\n"
            "  pip install mamba-ssm causal-conv1d  # HF torch29-cu126 wheel\n"
            "  pip install monai\n"
            f"vendor: {_VENDOR_DIR}"
        )


# --------------------------------------------------------------------------- #
#  Loss helper — Dice+CE（官方 criterion）
# --------------------------------------------------------------------------- #

class _DiceCELoss:
    """
    Dice + CE loss — 官方 MambaVesselNet++ criterion。
    signature: (logits, target, fov_mask) -> scalar
    官方代码无 FOV masking（全图计算），fov_mask 接收但忽略。
    """

    def __call__(
        self,
        logits: torch.Tensor,
        target: torch.Tensor,
        fov_mask: torch.Tensor,
    ) -> torch.Tensor:
        import torch.nn.functional as F

        # CE part
        ce = F.binary_cross_entropy_with_logits(logits, target, reduction="mean")

        # Dice part（smooth=1e-5）
        smooth = 1e-5
        prob = torch.sigmoid(logits)
        num = (prob * target).sum(dim=list(range(1, logits.ndim)))
        denom = prob.sum(dim=list(range(1, logits.ndim))) + target.sum(dim=list(range(1, logits.ndim)))
        dice_score = (2.0 * num + smooth) / (denom + smooth)
        dice_loss = 1.0 - dice_score.mean()

        return ce + dice_loss


# --------------------------------------------------------------------------- #
#  2D adapter wrapper（vendor mvn.py 是 3D，此处用 2D fallback）
# --------------------------------------------------------------------------- #

class _MVNWrapper2D(nn.Module):
    """
    MambaVesselNet++ 的 2D 包装器。

    官方 vendor mvn.py（mvnNet）全部用 Conv3d（spatial_dims=3），
    MONAI UnetrBasicBlock/UnetrUpBlock 支持 spatial_dims 参数切换。

    此包装器尝试以 spatial_dims=2 实例化 mvnNet（通过 MONAI 2D 路径）。
    若 MONAI 2D + mamba 可行，正常返回；否则抛 RuntimeError。

    TODO_researcher: 官方 2D input_size 未明示；根据 arXiv 文本和 BASELINE_SPEC §1
    暂用 256×256（与 VM-UNet 对齐）。需联系作者 issue 或查 arXiv 2D 实验章节确认。
    """

    def __init__(self, in_chans: int = 1, out_chans: int = 1,
                 feature_dims=None):
        super().__init__()
        if feature_dims is None:
            feature_dims = [48, 96, 192, 384, 768]

        # 把 vendor 目录加入 sys.path
        mvn_dir = _VENDOR_DIR / "model_mvn"
        if str(_VENDOR_DIR) not in sys.path:
            sys.path.insert(0, str(_VENDOR_DIR))

        from model_mvn.mvn import mvnNet
        # spatial_dims=2 让 MONAI blocks 切 2D Conv，但 mvnNet 内部固定 Conv3d
        # → 此处直接用 spatial_dims=2（若 MONAI 支持），否则抛出
        try:
            self.net = mvnNet(
                in_chans=in_chans,
                out_chans=out_chans,
                feature_dims=feature_dims,
                spatial_dims=2,
                norm_name="instance",
                res_block=True,
            )
        except TypeError:
            # 若 mvnNet 不接受 spatial_dims=2（固化 Conv3d），抛友好错误
            raise RuntimeError(
                "MambaVesselNet++ vendor mvn.py 中 mvnNet 固定 Conv3d（spatial_dims=3），\n"
                "无法直接用于 2D 视网膜分割。\n"
                "TODO_researcher: 需查 arXiv 2411.11946 或联系作者确认 2D 分支实现。\n"
                "当前策略：降档 C（见 BASELINE_SPEC §3 退路），引文献 Dice=0.711。"
            )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


# --------------------------------------------------------------------------- #
#  Adapter
# --------------------------------------------------------------------------- #

@register
class MambaVesselNetAdapter(BaselineAdapter):
    """
    MambaVesselNet++ baseline adapter.

    官方 repo : https://github.com/CC0117/MambaVesselNet (MIT)
    env_tag   : 'mamba' — 需 mamba_venv + monai
    vendor    : third_party/MambaVesselNet/（MIT，已 curl）

    ⚠️ 架构警告：vendor mvn.py 是 3D（Conv3d），2D 分支官方未同步代码。
       build_model 在 mamba_venv + monai 满足时尝试 spatial_dims=2 实例化；
       若 MONAI 2D 路径可行则正常运行，否则抛 RuntimeError（降档 C）。
       TODO_researcher: 2D input_size 待确认（暂用 256×256）。
    """

    name: str = "mamba_vessel_net"
    kind: str = KIND_ARCHITECTURE
    source_repo: str = "https://github.com/CC0117/MambaVesselNet"
    env_tag: str = ENV_MAMBA

    def build_model(self, cfg: Dict[str, Any]) -> nn.Module:
        """
        构建 MambaVesselNet++ 2D 模型（依赖 mamba_ssm + monai）。

        cfg keys (from configs/baselines/mambavesselnet.yaml):
          in_chans     : int (default 1)
          out_chans    : int (default 1)
          feature_dims : list (default [48,96,192,384,768])

        Raises:
            RuntimeError: mamba_ssm/monai 缺失，或 2D 不可行时。
        """
        _require_mvn_env()

        in_chans = int(cfg.get("in_chans", 1))
        out_chans = int(cfg.get("out_chans", 1))
        feature_dims = list(cfg.get("feature_dims", [48, 96, 192, 384, 768]))

        return _MVNWrapper2D(
            in_chans=in_chans,
            out_chans=out_chans,
            feature_dims=feature_dims,
        )

    def build_loss(self, cfg: Dict[str, Any]) -> _DiceCELoss:
        """官方 loss = Dice + CE（官方 criterion.py）。"""
        return _DiceCELoss()

    def build_optimizer(
        self,
        model: nn.Module,
        cfg: Dict[str, Any],
    ) -> torch.optim.Optimizer:
        """Adam lr=1e-4（官方 BASELINE_SPEC §1，TOMM25）。"""
        lr = float(cfg.get("lr", 1e-4))
        return torch.optim.Adam(model.parameters(), lr=lr)

    def build_scheduler(
        self,
        optimizer: torch.optim.Optimizer,
        cfg: Dict[str, Any],
    ) -> Optional[Any]:
        """CosineAnnealingLR T_max=200 eta_min=1e-7（官方）。"""
        epochs = int(cfg.get("epochs", 200))
        min_lr = float(cfg.get("min_lr", 1e-7))
        return torch.optim.lr_scheduler.CosineAnnealingLR(
            optimizer, T_max=epochs, eta_min=min_lr
        )

    def preprocess_cfg(self) -> Dict[str, Any]:
        """
        官方预处理：未在 repo 中明示（3D train.py）。
        2D 分支暂用 256×256（与 BASELINE_SPEC §1 TODO 对应）。
        # TODO_researcher: 2D input_size + augmentation 待查 arXiv 2411.11946
        #                  或联系 CC0117 issue 确认。
        """
        return {
            "channels": "green_raw",
            "normalize": {
                "mean": [0.0],                 # TODO: 官方未明示
                "std": [1.0],                  # TODO: 官方未明示
            },
            "input_mode": "fullimg",
            "patch_size": None,
            "clahe": False,
            "extra": {
                "resize": 256,                 # TODO_researcher: 2D input_size 待确认
                "batch_size": 16,              # 官方 bs=16（BASELINE_SPEC §1）
                "note": (
                    "MambaVesselNet++ vendor is 3D (Conv3d). "
                    "2D adaptation: spatial_dims=2 via MONAI. "
                    "Input size TODO: see arXiv 2411.11946 2D section. "
                    "Source: BASELINE_SPEC §1 + TOMM25."
                ),
            },
        }

    def forward_adapt(
        self,
        model: nn.Module,
        x: torch.Tensor,
        device: torch.device,
    ) -> torch.Tensor:
        """
        全图推理（2D，resize 到 256×256 后 forward）。

        Args:
            model : _MVNWrapper2D 实例，eval 模式，已 .to(device)。
            x     : (B, 1, H, W) 灰度全图，已在 device 上。
            device: 推理设备。

        Returns:
            (B, 1, H, W) logits。

        # TODO_researcher: resize 目标尺寸（256？）待 2D input_size 确认后更新。
        """
        import torch.nn.functional as F

        model.eval()
        B, C, H, W = x.shape
        assert C == 1, (
            f"MambaVesselNetAdapter: 期望单通道输入 (B,1,H,W)，实际 C={C}"
        )

        # TODO: resize 尺寸待 2D input_size 确认
        x_resized = F.interpolate(x, size=(256, 256), mode="bilinear", align_corners=False)

        with torch.no_grad():
            logits_256 = model(x_resized)  # (B, 1, 256, 256)

        # resize 回原始尺寸
        logits = F.interpolate(logits_256, size=(H, W), mode="bilinear", align_corners=False)

        assert logits.shape == (B, 1, H, W), (
            f"MambaVesselNetAdapter.forward_adapt: shape mismatch, got {logits.shape}"
        )
        return logits
