"""
nnunet.py — Adapter for nnU-Net (architecture-class baseline, 公平主干).

官方 repo  : https://github.com/MIC-DKFZ/nnUNet  (Apache-2.0)
官方论文   : Nature Methods 2021
官方超参   : SGD momentum=0.99 nesterov=True wd=3e-5 lr=1e-2 PolyLR 1000ep
             DC+CE 深监督; batch/input/preprocess 全自动（dataset fingerprint）。
             Source: BASELINE_SPEC §1 + github.com/MIC-DKFZ/nnUNet

env_tag    : 'main'（需 nnunetv2 安装，pip install nnunetv2）

重要说明   :
  - nnU-Net 的所有超参（patch size / batch size / normalization / 模型结构）
    由 nnU-Net fingerprint 自动配置，不可手动覆盖（这是 nnU-Net 设计哲学 = "公平主干"）。
  - 训练通过 nnUNetv2_train 命令行（本 harness train_harness.py 不接管）。
  - 评估通过 nnUNetv2_predict 命令行生成 predict，evaluate.py 读取 mask。
  - build_model / build_optimizer 在 nnunetv2 未安装时抛 RuntimeError。
  - TODO: evaluate.py 接 nnUNetv2_predict 输出 mask 的路径约定待主线拍板（BASELINE_SPEC §4）。

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

from baselines.base_adapter import BaselineAdapter, ENV_MAIN, KIND_ARCHITECTURE
from baselines.registry import register


# --------------------------------------------------------------------------- #
#  Runtime 依赖检查 helper
# --------------------------------------------------------------------------- #

def _require_nnunet_env() -> None:
    """
    检查 nnU-Net 所需运行时依赖。

    Raises:
        RuntimeError: nnunetv2 未安装时抛出，含安装指引。
    """
    try:
        import nnunetv2  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "nnU-Net 需要 nnunetv2 安装（当前环境未找到）。\n"
            "请安装（见 BASELINE_SPEC §2.2 env 配置）：\n"
            "  pip install nnunetv2\n"
            "训练通过 nnUNetv2_train 命令行，推理通过 nnUNetv2_predict。\n"
            "详见 github.com/MIC-DKFZ/nnUNet + BASELINE_SPEC §4 HPC 编排。\n"
            f"原始 ImportError: {exc}"
        ) from exc


# --------------------------------------------------------------------------- #
#  Loss placeholder — nnU-Net DC+CE Deep Supervision
# --------------------------------------------------------------------------- #

class _NNUNetDCCELoss:
    """
    nnU-Net 官方 loss = Dice+CE with Deep Supervision。
    框架外不可独立使用，仅作接口占位。
    """

    def __call__(
        self,
        logits: torch.Tensor,
        target: torch.Tensor,
        fov_mask: torch.Tensor,
    ) -> torch.Tensor:
        _require_nnunet_env()
        raise RuntimeError(
            "nnU-Net DC+CE Deep Supervision loss 仅在 nnU-Net 框架内运行。"
            "本 harness 不接管 nnU-Net 训练 loop，见 BASELINE_SPEC §3/§4。"
        )


# --------------------------------------------------------------------------- #
#  Adapter
# --------------------------------------------------------------------------- #

@register
class NNUNetAdapter(BaselineAdapter):
    """
    nnU-Net baseline adapter（"公平主干"架构基准）。

    官方 repo : https://github.com/MIC-DKFZ/nnUNet (Apache-2.0)
    env_tag   : 'main'（需 pip install nnunetv2）

    ⚠️ 重要：nnU-Net 所有超参由 dataset fingerprint 自动配置。
       本 adapter 遵循「复现零偏离」红线——不手动覆盖任何 nnU-Net 自动超参。
       训练/推理通过 nnU-Net 官方命令行，本 harness 仅提供接口占位。

    BASELINE_SPEC §1 超参（仅记录 nnU-Net 框架的已知默认值）：
      optimizer : SGD momentum=0.99 nesterov=True wd=3e-5 lr=1e-2
      schedule  : PolyLR（nnU-Net 内置）
      epochs    : 1000（nnU-Net 默认）
      loss      : DC+CE Deep Supervision
      batch/input/preprocess : 全自动（fingerprint）
    """

    name: str = "nnunet"
    kind: str = KIND_ARCHITECTURE
    source_repo: str = "https://github.com/MIC-DKFZ/nnUNet"
    env_tag: str = ENV_MAIN

    def build_model(self, cfg: Dict[str, Any]) -> nn.Module:
        """
        nnU-Net 模型由框架自动构建，无法在 harness 内独立实例化。

        cfg keys (from configs/baselines/nnunet.yaml):
          dataset_name    : str — nnUNet dataset name (e.g. "Dataset001_DRIVE")
          configuration   : str — nnU-Net config (e.g. "2d")
          trainer         : str — nnUNetTrainer (default "nnUNetTrainer")

        Raises:
            RuntimeError: nnunetv2 未安装，或框架内不可直接实例化。
        """
        _require_nnunet_env()
        raise RuntimeError(
            "nnU-Net 模型由框架自动构建（plan_and_preprocess 后自动决定架构）。\n"
            "请使用以下命令行训练（见 BASELINE_SPEC §4）：\n"
            "  nnUNetv2_plan_and_preprocess -d <dataset_id> --verify_dataset_integrity\n"
            "  nnUNetv2_train <dataset_id> 2d 0 --tr nnUNetTrainer\n"
            "推理：nnUNetv2_predict -i <input> -o <output> -d <dataset_id> -c 2d\n"
            "TODO: 若需在 harness 内实例化，研究 nnU-Net get_network_from_plans() 接口。"
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
        nnU-Net 官方 optimizer 配置（仅记录，框架管理不在 harness 内构建）。
        SGD momentum=0.99 nesterov=True wd=3e-5 lr=1e-2。

        Raises:
            RuntimeError: 始终，nnU-Net optimizer 由框架管理。
        """
        _require_nnunet_env()
        raise RuntimeError(
            "nnU-Net optimizer 由框架（nnUNetTrainer）管理，不在 harness 内配置。\n"
            "已知配置（仅参考）：SGD momentum=0.99 nesterov=True wd=3e-5 lr=1e-2 PolyLR。\n"
            "见 github.com/MIC-DKFZ/nnUNet nnunetv2/training/nnUNetTrainer/nnUNetTrainer.py。"
        )

    def build_scheduler(
        self,
        optimizer: torch.optim.Optimizer,
        cfg: Dict[str, Any],
    ) -> Optional[Any]:
        """nnU-Net PolyLR 由框架管理，此处返回 None 占位。"""
        return None

    def preprocess_cfg(self) -> Dict[str, Any]:
        """
        nnU-Net 预处理全自动（dataset fingerprint 决定）。
        此处记录已知配置以供参考，不作为 harness 实际预处理。
        """
        return {
            "channels": "green_raw",
            "normalize": {
                "mean": [0.0],  # nnU-Net 自动计算 z-score 归一化
                "std": [1.0],
            },
            "input_mode": "fullimg",
            "patch_size": None,   # nnU-Net 自动确定 patch size
            "clahe": False,
            "extra": {
                "framework": "nnunetv2",
                "configuration": "2d",   # 2D 视网膜用 2d configuration
                "epochs": 1000,          # nnU-Net 默认
                "note": (
                    "nnU-Net full auto pipeline. All preprocessing via "
                    "nnUNetv2_plan_and_preprocess. "
                    "Source: BASELINE_SPEC §1 + github.com/MIC-DKFZ/nnUNet."
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
        nnU-Net 推理通过 nnUNetv2_predict 命令行，不在 harness forward_adapt 内。

        TODO: evaluate.py 读取 nnUNetv2_predict 输出 mask（PNG/NIfTI），
              接入方式见 BASELINE_SPEC §4（待主线拍板）。

        Raises:
            RuntimeError: 始终，指向命令行推理。
        """
        _require_nnunet_env()
        raise RuntimeError(
            "nnU-Net 推理通过 nnUNetv2_predict 命令行，不在 harness forward_adapt 内进行。\n"
            "evaluate.py 应接 nnUNetv2_predict 输出的 segmentation mask 文件。\n"
            "TODO: 实现 mask 文件读取路径，见 BASELINE_SPEC §4。"
        )
