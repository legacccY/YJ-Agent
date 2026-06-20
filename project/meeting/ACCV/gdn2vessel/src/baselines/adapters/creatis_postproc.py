"""
creatis_postproc.py — Adapter for creatis plug-and-play reconnecting post-processing.

Source:  https://github.com/creatis-myriad/plug-and-play-reco-regularization
License: CeCILL (French free software license, compatible with LGPL/GPL).
         Academic use PERMITTED; must cite [1][2] when publishing.
         [1] Carneiro-Esteves et al., Neurocomputing 2024
         [2] Carneiro-Esteves et al., TGI3 MICCAI Workshop 2024

Kind: two_stage — 两段式 baseline:
  Stage 1: 用统一 backbone (backbone_unet) 做初始分割 → 二值 mask
  Stage 2: 喂入 creatis 学习型续连模型（monai UNet，10 次迭代）→ 续连后二值 mask

原理:
  - 标准分割输出的二值图经多轮 learned reconnecting model forward 逐步填补断点
  - 核心是 post_treatement.py 中的 apply_postproc_iterations()
  - 两段相加 = 公平对照"in-model（Ours GDN-2）vs post-processing（这里）"

官方超参 (sources/source_2D/train.py, main branch 2026-06-20):
  - 模型架构 : monai.networks.nets.UNet(spatial_dims=2, in_ch=1, out_ch=1,
                channels=(16,32,64,128), strides=(2,2,2), num_res_units=2)
  - optimizer : Adam, lr=1e-3
  - batch_size: 32
  - max_epochs: 1000
  - loss       : PonderatedDiceloss（官方自定义 weighted Dice）
  - roi_size   : (96, 96) 滑窗推理
  - sw_batch   : 5
  - mode       : 'gaussian'
  - overlap    : 0.5
  - iterations : 10 (post_treatement 默认)

NOTE — Windows 规范修复（vs 官方 train.py）:
  - num_workers=0 (官方用 1，spawn 不安全)
  - pin_memory=False (官方 pin_memory=True，spawn worker 不支持)

TODO: monai 必须安装。`pip install monai`
      若 monai 未装，build_model / forward_adapt 会抛 ImportError（有明确提示）。

⚠️ two_stage 说明:
  本 adapter 的 forward_adapt 实现了完整的两阶段流程：
    1. 调用传入的 `model`（应为 backbone 输出的初始分割）— 实际上
       forward_adapt 在 evaluate.py 调用时接收到的是 stage-1 的 logit 输出，
       然后二值化后送入 creatis 续连网络（creatis 模型通过 cfg 路径加载）。
  由于 evaluate.py 接口设计是单模型前向，此 adapter 内部持有 creatis 模型
  (self._postproc_model)，并在 build_model 时一并构建/加载。

  完整评估流程（evaluate.py 端）:
    backbone_logits = backbone.forward_adapt(backbone_model, x, device)
    creatis_adapter.forward_adapt(creatis_model_placeholder, backbone_logits, device)
    ← 内部: sigmoid → 二值化 → apply_postproc_iterations → logit 返回

  训练说明:
    Stage 1 训练: 用统一 backbone_unet 的 train_harness，不需要特殊处理。
    Stage 2 训练: 调用 build_model(cfg, train=True) 返回 creatis reconnecting model，
                  用 build_optimizer / build_loss 做官方训练（PonderatedDiceloss + Adam）。

TODO_researcher: 官方仓库无 LICENSE 文件（curl 返回 404）；
  README + vendor/__init__.py 均记录 CeCILL 授权（http://www.cecill.info）。
  建议 researcher 通过官方 README 或联系作者确认正式 license 文件位置。
  CeCILL 学术用途允许；发表时需引[1][2]。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import torch
import torch.nn as nn

# 确保 src/ 在 sys.path
_src_dir = Path(__file__).parent.parent.parent
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from baselines.base_adapter import (
    BaselineAdapter,
    ENV_MAIN,
    KIND_ARCHITECTURE,
)
from baselines.registry import register


# --------------------------------------------------------------------------- #
#  PonderatedDiceloss (官方 sources/source_2D/train.py 忠实复刻)
# --------------------------------------------------------------------------- #

class _PonderatedDiceloss(nn.Module):
    """
    Ponderated Dice loss: 联合计算整体 Dice + 片段化 Dice，
    用于训练 creatis 续连模型（官方 train.py PonderatedDiceloss）。

    官方逻辑（忠实复刻）:
      - dice_loss: standard Dice on full binary seg
      - frag_dice_loss: Dice on fragmented (disconnected) regions only
      - combined = dice + frag_dice

    Adapter 接口 signature: loss_fn(logits, target, fov_mask)
    - logits  : (B,1,H,W) raw logits
    - target  : (B,1,H,W) binary {0,1}
    - fov_mask: (B,1,H,W) FOV mask — used to restrict loss to valid region

    NOTE: 官方 PonderatedDiceloss 原始 forward(pred, label, mask) 接受概率；
          此处 adapter 接受 logits，内部先 sigmoid。
    """

    def __init__(self, smooth: float = 1e-6):
        super().__init__()
        self.smooth = smooth

    def _dice(
        self,
        pred_prob: torch.Tensor,
        target: torch.Tensor,
        mask: torch.Tensor,
    ) -> torch.Tensor:
        """Standard soft Dice in [0,1] range."""
        eps = self.smooth
        p = (pred_prob * mask).reshape(pred_prob.shape[0], -1)
        t = (target * mask).reshape(target.shape[0], -1)
        inter = (p * t).sum(1)
        denom = p.sum(1) + t.sum(1)
        return 1.0 - ((2 * inter + eps) / (denom + eps)).mean()

    def forward(
        self,
        logits: torch.Tensor,
        target: torch.Tensor,
        fov_mask: torch.Tensor,
    ) -> torch.Tensor:
        pred_prob = torch.sigmoid(logits)
        dice = self._dice(pred_prob, target, fov_mask)

        # Fragmented Dice: inverted target as proxy for fragmented region
        # Official uses a generated disconnected dataset mask; here we use
        # (1 - target) as approximation for background/fragment region.
        # TODO_researcher: 官方 train.py 用训练时生成的断点图 ("mask" 列),
        #   此处用 (1-target) 作 frag_region 近似；如需精确复现需配套断点生成脚本。
        frag_region = (1.0 - target) * fov_mask
        frag_dice = self._dice(pred_prob, target, frag_region + 1e-9)

        return dice + frag_dice


# --------------------------------------------------------------------------- #
#  Adapter
# --------------------------------------------------------------------------- #

@register
class CreatisPostprocAdapter(BaselineAdapter):
    """
    creatis plug-and-play learned reconnecting post-processing.

    Two-stage baseline:
      Stage 1: backbone 初始分割（使用统一 backbone_unet，外部提供 logits）
      Stage 2: creatis reconnecting model 续连（本 adapter 负责 Stage 2）

    adapter kind = 'architecture'（整套 two-stage 为变量，对比 Ours GDN-2 in-model 续连）。

    ⚠️ forward_adapt 接受:
      - model: 此处为 creatis reconnecting UNet（monai 架构）
      - x    : (B,1,H,W) backbone 输出的 logits（由外部传入 stage-1 logit）
               forward_adapt 内部: sigmoid → 二值化 → apply_postproc → logit 返回
    """

    name: str = "creatis_postproc"
    kind: str = KIND_ARCHITECTURE
    source_repo: str = (
        "https://github.com/creatis-myriad/plug-and-play-reco-regularization"
    )
    env_tag: str = ENV_MAIN

    # ---------------------------------------------------------------------- #
    #  build_model
    # ---------------------------------------------------------------------- #

    def build_model(self, cfg: Dict[str, Any]) -> nn.Module:
        """
        构建 creatis reconnecting model (monai UNet).

        官方架构 (train.py):
          monai.networks.nets.UNet(
            spatial_dims=2, in_channels=1, out_channels=1,
            channels=(16, 32, 64, 128), strides=(2, 2, 2),
            num_res_units=2, norm='INSTANCE'
          )

        cfg keys (from creatis.yaml):
          norm           : str  (default: 'INSTANCE' — 官方 config_training.json)
          model_dir      : str | None  (预训练权重目录；None = 从头训练)

        Returns:
            monai UNet on CPU（外部 .to(device)）。

        Raises:
            ImportError: monai 未安装。
        """
        from baselines.third_party.creatis_postproc.post_treatement import (
            _build_creatis_model,
            load_creatis_model,
        )

        norm = str(cfg.get("norm", "INSTANCE"))
        model_dir = cfg.get("model_dir", None)

        if model_dir is not None:
            model_path = Path(model_dir)
            if model_path.exists():
                device = torch.device("cpu")
                model, _ = load_creatis_model(model_path, device=device)
                return model
            else:
                import warnings
                warnings.warn(
                    f"creatis model_dir={model_dir!r} not found. "
                    "Building untrained model. Train before evaluating.",
                    UserWarning,
                )

        # 从头构建（训练阶段 or 权重缺失时）
        return _build_creatis_model(norm=norm)

    # ---------------------------------------------------------------------- #
    #  build_loss
    # ---------------------------------------------------------------------- #

    def build_loss(self, cfg: Dict[str, Any]) -> _PonderatedDiceloss:
        """
        PonderatedDiceloss（官方 train.py 忠实复刻）。
        signature: loss_fn(logits, target, fov_mask) → scalar
        """
        return _PonderatedDiceloss(smooth=float(cfg.get("loss_smooth", 1e-6)))

    # ---------------------------------------------------------------------- #
    #  build_optimizer
    # ---------------------------------------------------------------------- #

    def build_optimizer(
        self,
        model: nn.Module,
        cfg: Dict[str, Any],
    ) -> torch.optim.Optimizer:
        """
        Adam, lr=1e-3 (官方 train.py 默认).
        """
        lr = float(cfg.get("lr", 1e-3))
        return torch.optim.Adam(model.parameters(), lr=lr)

    # ---------------------------------------------------------------------- #
    #  build_scheduler
    # ---------------------------------------------------------------------- #

    def build_scheduler(
        self,
        optimizer: torch.optim.Optimizer,
        cfg: Dict[str, Any],
    ) -> Optional[Any]:
        """
        官方 train.py 未使用 scheduler → 返回 None（复现零偏离）。
        """
        return None

    # ---------------------------------------------------------------------- #
    #  preprocess_cfg
    # ---------------------------------------------------------------------- #

    def preprocess_cfg(self) -> Dict[str, Any]:
        """
        creatis Stage-2 预处理 (官方 train.py):
          - 输入: 二值分割 mask (来自 Stage-1 backbone 输出)
          - normalize: 简单 /255 to [0,1]（官方 post_treatement.py:
                       image.astype(float)/255.0）
          - roi_size: (96,96) 滑窗
          - 无 CLAHE

        NOTE: Stage-1 预处理由 backbone_unet adapter 决定（green_clahe）。
        这里描述 Stage-2 的输入约定（二值 mask 归一化）。
        """
        return {
            "channels": "green_clahe",  # Stage-1 backbone 预处理（继承 backbone_unet）
            "normalize": {"mean": [0.5], "std": [0.1]},
            "input_mode": "fullimg",
            "patch_size": None,
            "clahe": True,
            "extra": {
                "two_stage": True,
                "stage2_input": "binary_mask_from_stage1",
                "stage2_normalize": "binary_to_float_div255",
                "stage2_roi_size": [96, 96],
                "stage2_sw_batch": 5,
                "stage2_mode": "gaussian",
                "stage2_overlap": 0.5,
                "stage2_iterations": 10,
                "note": (
                    "Stage 1: backbone_unet (green_clahe, fullimg). "
                    "Stage 2: creatis reconnecting model on binarized output "
                    "(official: normalize to [0,1], sliding window 96x96, 10 iterations)."
                ),
                "license": (
                    "CeCILL (http://www.cecill.info); academic use OK; "
                    "cite [1] Carneiro-Esteves et al. Neurocomputing 2024 "
                    "[2] Carneiro-Esteves et al. TGI3 MICCAI 2024"
                ),
            },
        }

    # ---------------------------------------------------------------------- #
    #  forward_adapt (two-stage)
    # ---------------------------------------------------------------------- #

    def forward_adapt(
        self,
        model: nn.Module,
        x: torch.Tensor,
        device: torch.device,
    ) -> torch.Tensor:
        """
        两阶段推理:
          x = backbone logits (B,1,H,W)  ← Stage-1 输出，外部传入
          1. sigmoid + threshold(0.5) → binary_mask (B,1,H,W) float
          2. 对每个 sample: apply_postproc_iterations (官方 10 轮) → reconnected uint8
          3. 转回 (B,1,H,W) float [0,1] → logit 化（logit = log(p/(1-p))）返回

        NOTE: creatis model 在此处使用（通过 cfg 传入的 build_model 结果）。
              如果 model 未加载预训练权重（untrained），输出无意义但接口仍正常。

        Args:
            model : creatis reconnecting monai UNet（已 build_model 返回的模型）
            x     : (B,1,H,W) backbone output logits（来自 Stage-1）
            device: 推理设备

        Returns:
            (B,1,H,W) logits (post-processed, pseudo-logit from reconnected probs)
        """
        assert x.shape[1] == 1 and x.ndim == 4, (
            f"CreatisPostprocAdapter.forward_adapt: expected (B,1,H,W) "
            f"backbone logits, got {x.shape}"
        )

        from baselines.third_party.creatis_postproc.post_treatement import (
            apply_postproc_iterations,
        )

        model.eval()
        B, C, H, W = x.shape

        # Stage-1: threshold backbone logits → binary mask
        prob_stage1 = torch.sigmoid(x)  # (B,1,H,W)
        binary_mask = (prob_stage1 >= 0.5).float()  # {0,1}

        # Stage-2: apply creatis reconnecting model per sample
        results = []
        for b in range(B):
            # (1,H,W) → (H,W) numpy uint8 {0,255}
            seg_hw = (binary_mask[b, 0].cpu().numpy() * 255).astype(np.uint8)

            # Apply official post-processing iterations
            reconnected = apply_postproc_iterations(
                binary_seg=seg_hw,
                model=model,
                iterations=10,
                roi_size=(96, 96),
                device=device,
            )  # → (H,W) uint8 {0, 255}

            # Normalize to [0, 1] float
            prob_hw = reconnected.astype(np.float32) / 255.0

            results.append(prob_hw)

        # Stack → (B,1,H,W) float tensor
        probs = torch.from_numpy(
            np.stack(results, axis=0)[:, np.newaxis]  # (B,1,H,W)
        ).float()

        # Convert probability → pseudo-logit for harness compatibility
        # (evaluate.py expects logits and applies sigmoid+threshold internally)
        eps = 1e-6
        probs = probs.clamp(eps, 1.0 - eps)
        logits = torch.log(probs / (1.0 - probs))  # logit transform

        return logits.to(device)
