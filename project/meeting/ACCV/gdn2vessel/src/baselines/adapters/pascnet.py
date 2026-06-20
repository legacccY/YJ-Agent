"""
pascnet.py — Adapter for PASC-Net (nnU-Net based, FIVES SOTA).

官方 repo  : https://github.com/IPMI-NWU/PASC-Net  (Apache-2.0)
官方论文   : arXiv 2507.04008（preprint 状态）
官方超参   : 继承 nnU-Net 基础 + 自定义 trainer；epochs=300；
             loss = 0.7·DC_CE + 0.1·con1 + 0.1·con3 + 0.1·clDice；
             batch/input/preprocess 继承 nnU-Net 自配置。
             Source: BASELINE_SPEC §1（researcher 二轮核实：
               epochs=300 via nnUNetTrainer.py num_epochs=300;
               loss via train_step 直读源码 0.7/0.1/0.1/0.1）。

env_tag    : 'main'（需 nnunetv2 安装 + PASC-Net 自定义 trainer）

重要说明   :
  - PASC-Net 基于 nnU-Net v2，在 nnUNetTrainer 基础上注入自定义 loss。
  - 本 adapter 继承 nnunet.py adapter 的框架运行时策略，
    额外记录 PASC-Net 自定义 loss 权重。
  - 训练通过 nnUNetv2_train --tr PASCTrainer（PASC-Net 自定义 trainer）命令行。
  - PASC-Net arXiv preprint 状态，引用时需标注（BASELINE_SPEC §5）。
  - FIVES 官方报告 Dice=0.9183（SOTA），DRIVE 数字需自跑。

⚠️ License: Apache-2.0（BASELINE_SPEC §0 确认）。

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

def _require_pascnet_env() -> None:
    """
    检查 PASC-Net 所需运行时依赖（nnunetv2）。

    Raises:
        RuntimeError: nnunetv2 未安装时抛出，含安装指引。
    """
    try:
        import nnunetv2  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "PASC-Net 需要 nnunetv2 安装（当前环境未找到）。\n"
            "请安装（见 BASELINE_SPEC §2.2 env 配置）：\n"
            "  pip install nnunetv2\n"
            "  git clone https://github.com/IPMI-NWU/PASC-Net\n"
            "  cd PASC-Net && pip install -e .\n"
            "训练通过 nnUNetv2_train --tr PASCTrainer 命令行。\n"
            "详见 BASELINE_SPEC §4 HPC 编排 + github.com/IPMI-NWU/PASC-Net。\n"
            f"原始 ImportError: {exc}"
        ) from exc


# --------------------------------------------------------------------------- #
#  Loss placeholder — PASC-Net composite loss
# --------------------------------------------------------------------------- #

class _PASCNetLoss:
    """
    PASC-Net 官方复合 loss（占位，框架外不可独立使用）：
    L = 0.7·DC_CE + 0.1·con1 + 0.1·con3 + 0.1·clDice

    Source: BASELINE_SPEC §1 researcher 核实（train_step 实测）。
    """

    # 官方 loss 权重（BASELINE_SPEC §1 核实）
    WEIGHT_DC_CE = 0.7
    WEIGHT_CON1 = 0.1
    WEIGHT_CON3 = 0.1
    WEIGHT_CLDICE = 0.1

    def __call__(
        self,
        logits: torch.Tensor,
        target: torch.Tensor,
        fov_mask: torch.Tensor,
    ) -> torch.Tensor:
        _require_pascnet_env()
        raise RuntimeError(
            "PASC-Net 复合 loss（0.7·DC_CE+0.1·con1+0.1·con3+0.1·clDice）\n"
            "仅在 nnU-Net + PASCTrainer 框架内运行。\n"
            "本 harness 不接管 PASC-Net 训练 loop，见 BASELINE_SPEC §3/§4。"
        )


# --------------------------------------------------------------------------- #
#  Adapter
# --------------------------------------------------------------------------- #

@register
class PASCNetAdapter(BaselineAdapter):
    """
    PASC-Net baseline adapter（nnU-Net based，FIVES SOTA 91.83）。

    官方 repo : https://github.com/IPMI-NWU/PASC-Net (Apache-2.0)
    env_tag   : 'main'（需 pip install nnunetv2 + PASC-Net trainer）

    ⚠️ 预印本：PASC-Net arXiv preprint 状态（arXiv 2507.04008），引用时需标注。
    ⚠️ 重要：PASC-Net 继承 nnU-Net 框架，本 adapter 不接管训练/推理。
       训练通过 nnUNetv2_train --tr PASCTrainer（300 epochs）。

    BASELINE_SPEC §1 官方超参（researcher 二轮核实）：
      epochs  : 300（nnUNetTrainer.py num_epochs=300）
      loss    : 0.7·DC_CE + 0.1·con1 + 0.1·con3 + 0.1·clDice
      input   : 512（FIVES 2048px 裁到 512；DRIVE 标准 512）
      preprocess: 继承 nnU-Net 自配置
    """

    name: str = "pasc_net"
    kind: str = KIND_ARCHITECTURE
    source_repo: str = "https://github.com/IPMI-NWU/PASC-Net"
    env_tag: str = ENV_MAIN

    def build_model(self, cfg: Dict[str, Any]) -> nn.Module:
        """
        PASC-Net 模型由 nnU-Net 框架 + PASCTrainer 构建，无法在 harness 内独立实例化。

        cfg keys (from configs/baselines/pascnet.yaml):
          dataset_name  : str — nnUNet dataset name
          configuration : str — nnU-Net config (e.g. "2d")
          trainer       : str — "PASCTrainer"

        Raises:
            RuntimeError: nnunetv2 未安装，或框架外不可实例化。
        """
        _require_pascnet_env()
        raise RuntimeError(
            "PASC-Net 模型由 nnU-Net 框架 + PASCTrainer 自动构建。\n"
            "请使用以下命令行（见 BASELINE_SPEC §4）：\n"
            "  nnUNetv2_plan_and_preprocess -d <dataset_id> --verify_dataset_integrity\n"
            "  nnUNetv2_train <dataset_id> 2d 0 --tr PASCTrainer\n"
            "推理：nnUNetv2_predict -i <input> -o <output> -d <dataset_id> -c 2d\n"
            "官方 trainer: github.com/IPMI-NWU/PASC-Net/nnunetv2/training/\n"
            "TODO: 若需 harness 内实例化，研究 PASCTrainer 模型初始化接口。"
        )

    def build_loss(self, cfg: Dict[str, Any]) -> _PASCNetLoss:
        """
        PASC-Net 复合 loss 占位（0.7·DC_CE + 0.1·con1 + 0.1·con3 + 0.1·clDice）。
        框架外不可用。
        """
        return _PASCNetLoss()

    def build_optimizer(
        self,
        model: nn.Module,
        cfg: Dict[str, Any],
    ) -> torch.optim.Optimizer:
        """
        继承 nnU-Net：SGD momentum=0.99 nesterov=True wd=3e-5 lr=1e-2。
        框架管理，harness 内不构建。

        Raises:
            RuntimeError: 始终。
        """
        _require_pascnet_env()
        raise RuntimeError(
            "PASC-Net optimizer 继承 nnU-Net PASCTrainer 管理，不在 harness 内配置。\n"
            "已知配置（仅参考）：SGD momentum=0.99 nesterov=True wd=3e-5 lr=1e-2 PolyLR。"
        )

    def build_scheduler(
        self,
        optimizer: torch.optim.Optimizer,
        cfg: Dict[str, Any],
    ) -> Optional[Any]:
        """继承 nnU-Net PolyLR，框架管理，返回 None 占位。"""
        return None

    def preprocess_cfg(self) -> Dict[str, Any]:
        """
        继承 nnU-Net 自配置；已知 FIVES 用 2048→512px 裁剪，DRIVE 标准 512。
        """
        return {
            "channels": "green_raw",
            "normalize": {
                "mean": [0.0],  # nnU-Net 自动
                "std": [1.0],
            },
            "input_mode": "fullimg",
            "patch_size": None,
            "clahe": False,
            "extra": {
                "framework": "nnunetv2",
                "trainer": "PASCTrainer",
                "configuration": "2d",
                "epochs": 300,                 # 官方 300（BASELINE_SPEC §1 核实）
                "fives_resize": 512,           # FIVES 2048 → 512 裁
                # loss 权重（记录用，框架内生效）
                "loss_weights": {
                    "dc_ce": _PASCNetLoss.WEIGHT_DC_CE,
                    "con1": _PASCNetLoss.WEIGHT_CON1,
                    "con3": _PASCNetLoss.WEIGHT_CON3,
                    "cldice": _PASCNetLoss.WEIGHT_CLDICE,
                },
                "note": (
                    "PASC-Net inherits nnU-Net pipeline. "
                    "Preprint status (arXiv 2507.04008). "
                    "FIVES SOTA Dice=0.9183 (official paper). "
                    "Source: BASELINE_SPEC §1 + github.com/IPMI-NWU/PASC-Net."
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
        PASC-Net 推理通过 nnUNetv2_predict 命令行，不在 harness forward_adapt 内。

        TODO: evaluate.py 读取 nnUNetv2_predict 输出 mask，
              接入方式见 BASELINE_SPEC §4（待主线拍板）。

        Raises:
            RuntimeError: 始终，指向命令行推理。
        """
        _require_pascnet_env()
        raise RuntimeError(
            "PASC-Net 推理通过 nnUNetv2_predict 命令行（--tr PASCTrainer）。\n"
            "evaluate.py 应接 nnUNetv2_predict 输出的 segmentation mask 文件。\n"
            "TODO: 实现 mask 文件读取路径，见 BASELINE_SPEC §4。"
        )
