"""
umamba.py — Adapter for U-Mamba (nnU-Net + Mamba bottleneck).

官方 repo  : https://github.com/bowang-lab/U-Mamba  (Apache-2.0)
官方论文   : arXiv 2401.04722
官方超参   : 继承 nnU-Net 全部自配置（optimizer/lr/schedule/epochs/batch/input 均自动）。
             nnU-Net SGD momentum=0.99 nesterov=True wd=3e-5 lr=1e-2 PolyLR 1000ep DC+CE。
             U-Mamba 在 nnU-Net encoder bottleneck 插入 Mamba 层，训练流程 100% 继承 nnU-Net。
             Source: BASELINE_SPEC §1 + github.com/bowang-lab/U-Mamba README.

env_tag    : 'mamba'（需 mamba_venv + nnU-Net v2 安装）

重要说明   :
  - U-Mamba 无法独立于 nnU-Net 框架运行（模型定义、数据 pipeline、训练 loop 全耦合）。
  - 本 adapter 提供干净接口占位 + 友好 RuntimeError（指向 BASELINE_SPEC §3）。
  - HPC mamba_venv 中安装 nnU-Net + mamba_ssm 后可真实运行。
  - 训练通过 nnUNetv2_train 命令行（非本 harness 的 train_harness.py），
    评估通过 nnUNetv2_predict 命令行生成 predict → evaluate.py 接 segmentation mask。
  - TODO: HPC 端 U-Mamba nnU-Net 训练/推理接入方式待主线拍板（见 BASELINE_SPEC §4）。

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


# --------------------------------------------------------------------------- #
#  Runtime 依赖检查 helper
# --------------------------------------------------------------------------- #

def _require_umamba_env() -> None:
    """
    检查 U-Mamba 所需运行时依赖是否满足。
    需要：mamba_ssm + nnunetv2。

    Raises:
        RuntimeError: 任一依赖缺失时抛出，含清晰 HPC 指引。
    """
    missing = []
    try:
        import mamba_ssm  # noqa: F401
    except ImportError:
        missing.append("mamba-ssm")

    try:
        import nnunetv2  # noqa: F401
    except ImportError:
        missing.append("nnunetv2")

    if missing:
        raise RuntimeError(
            f"U-Mamba 需要以下依赖（当前环境缺失：{missing}）。\n"
            "请在 HPC mamba_venv 中安装（见 BASELINE_SPEC §3）：\n"
            "  pip install mamba-ssm causal-conv1d  # HF torch29-cu126 wheel\n"
            "  pip install nnunetv2\n"
            "  git clone https://github.com/bowang-lab/U-Mamba && "
            "cd U-Mamba && pip install -e .\n"
            "训练通过 nnUNetv2_train 命令行，推理通过 nnUNetv2_predict。\n"
            "详见 BASELINE_SPEC §3 + §4 HPC 编排。"
        )


# --------------------------------------------------------------------------- #
#  Loss placeholder — nnU-Net DC+CE（harness 接口占位）
# --------------------------------------------------------------------------- #

class _NNUNetDCCELoss:
    """
    nnU-Net 官方 loss = Deep Supervision DC+CE。
    占位实现：在 nnU-Net 框架外无法独立使用，运行时抛 RuntimeError。
    """

    def __call__(
        self,
        logits: torch.Tensor,
        target: torch.Tensor,
        fov_mask: torch.Tensor,
    ) -> torch.Tensor:
        _require_umamba_env()
        raise RuntimeError(
            "U-Mamba loss 只在 nnU-Net 框架内运行（DC+CE Deep Supervision）。"
            "本 harness 不接管 U-Mamba 训练 loop，见 BASELINE_SPEC §3/§4。"
        )


# --------------------------------------------------------------------------- #
#  Adapter
# --------------------------------------------------------------------------- #

@register
class UMambaAdapter(BaselineAdapter):
    """
    U-Mamba baseline adapter (nnU-Net + Mamba bottleneck).

    官方 repo : https://github.com/bowang-lab/U-Mamba (Apache-2.0)
    env_tag   : 'mamba' — 需 mamba_venv + nnunetv2 安装

    ⚠️ 重要：U-Mamba 训练/推理完全在 nnU-Net 框架内进行，
       本 adapter 不接管训练（build_model/build_optimizer 在 mamba_venv+nnunetv2 环境外抛 RuntimeError）。
       HPC 端通过 nnUNetv2_train + nnUNetv2_predict 命令行，evaluate.py 接 predict 结果。
       TODO: HPC U-Mamba nnU-Net 接入方式待主线 BASELINE_SPEC §4 拍板。
    """

    name: str = "u_mamba"
    kind: str = KIND_ARCHITECTURE
    source_repo: str = "https://github.com/bowang-lab/U-Mamba"
    env_tag: str = ENV_MAMBA

    def build_model(self, cfg: Dict[str, Any]) -> nn.Module:
        """
        构建 U-Mamba 模型（依赖 nnunetv2 + mamba_ssm）。

        U-Mamba 模型定义在 nnU-Net 框架内（umamba/network_architecture/），
        无法在 nnU-Net 外独立构建，此处检查依赖后转发 RuntimeError。

        Raises:
            RuntimeError: mamba_ssm 或 nnunetv2 未安装。
        """
        _require_umamba_env()

        # 依赖满足后，尝试从 nnU-Net 框架加载 U-Mamba 模型
        # TODO: U-Mamba 模型类路径在 nnunetv2 内；需在 HPC mamba_venv 实际测试。
        raise RuntimeError(
            "U-Mamba build_model：即使依赖满足，模型构建仍需通过 nnU-Net 自配置流水线。\n"
            "请使用 nnUNetv2_plan_and_preprocess + nnUNetv2_train 命令行。\n"
            "见 BASELINE_SPEC §3/§4 + github.com/bowang-lab/U-Mamba。\n"
            "TODO: 若需在本 harness 内构建，需研究 U-Mamba 模型类直接实例化接口。"
        )

    def build_loss(self, cfg: Dict[str, Any]) -> _NNUNetDCCELoss:
        """占位 loss（nnU-Net DC+CE，框架外不可用）。"""
        return _NNUNetDCCELoss()

    def build_optimizer(
        self,
        model: nn.Module,
        cfg: Dict[str, Any],
    ) -> torch.optim.Optimizer:
        """
        继承 nnU-Net：SGD momentum=0.99 nesterov=True wd=3e-5 lr=1e-2 PolyLR。
        框架外不可用（占位，抛 RuntimeError）。
        """
        _require_umamba_env()
        raise RuntimeError(
            "U-Mamba optimizer 继承 nnU-Net 框架管理，不在本 harness 内配置。"
        )

    def build_scheduler(
        self,
        optimizer: torch.optim.Optimizer,
        cfg: Dict[str, Any],
    ) -> Optional[Any]:
        """继承 nnU-Net PolyLR（框架管理，此处返回 None 占位）。"""
        return None

    def preprocess_cfg(self) -> Dict[str, Any]:
        """
        继承 nnU-Net 自动预处理流水线（dataset fingerprint 自配置）。
        本 harness 不介入 U-Mamba 预处理。
        """
        return {
            "channels": "green_raw",          # nnU-Net 自动选通道
            "normalize": {
                "mean": [0.0],                 # nnU-Net 自动计算
                "std": [1.0],                  # nnU-Net 自动计算
            },
            "input_mode": "fullimg",
            "patch_size": None,
            "clahe": False,
            "extra": {
                "framework": "nnunetv2",
                "note": (
                    "U-Mamba inherits nnU-Net full preprocessing pipeline. "
                    "Preprocessing via nnUNetv2_plan_and_preprocess. "
                    "Source: BASELINE_SPEC §1 + github.com/bowang-lab/U-Mamba."
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
        U-Mamba 推理在 nnU-Net 框架内（nnUNetv2_predict），
        本 adapter forward_adapt 在 harness 框架外不可用。

        TODO: evaluate.py 接 nnUNetv2_predict 输出的 segmentation mask（.nii.gz / .png）
              而非实时 forward，接入方式待 BASELINE_SPEC §4 拍板。

        Raises:
            RuntimeError: 始终，指向 nnU-Net 命令行推理。
        """
        _require_umamba_env()
        raise RuntimeError(
            "U-Mamba 推理通过 nnUNetv2_predict 命令行，不在 harness forward_adapt 内进行。\n"
            "evaluate.py 接 nnUNetv2_predict 输出 mask，接入方式见 BASELINE_SPEC §4。\n"
            "TODO: 实现 nnU-Net predict 结果读取路径，替换此占位。"
        )
