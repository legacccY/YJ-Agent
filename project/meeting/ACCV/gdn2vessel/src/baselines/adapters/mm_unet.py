"""
mm_unet.py — Adapter for MM-UNet (Morph Mamba UNet).

官方 repo  : https://github.com/liujiawen-jpg/MM-UNet  (MIT License)
官方论文   : arXiv 2511.02193 (2025)
官方超参   : AdamW lr=0.001, betas=(0.9,0.95), weight_decay=0.05(end=0.04),
             LinearWarmupCosineAnnealingLR warmup=2ep, max_epochs=500(论文)/3000(config),
             min_lr=1e-7;
             DRIVE bs=5 input=608×608; STARE bs=2(论文)/5(config) input=704×704;
             loss=monai.losses.DiceFocalLoss(smooth_nr=0, smooth_dr=1e-5,
                  to_onehot_y=False, sigmoid=True), weight=1.0;
             ImageNet 归一化 mean=[0.485,0.456,0.406] std=[0.229,0.224,0.225].
             Source: github.com/liujiawen-jpg/MM-UNet train.py + config.yml
                     + arXiv 2511.02193

架构特点   : ResNet-34 结构 Encoder（自实现无需预训练权重）+ MMConv
             (Morphological Mamba Conv，deformable DSC + Mamba SSM) +
             RCG（Recurrent Correction Gate）+ CBAM + HPPF。
             依赖 mamba-ssm CUDA kernel（env_tag='mamba'）。
             输入：3 通道 RGB，608×608（DRIVE）。
             forward 输出：logits（无 sigmoid；各 SideoutBlock 末尾是 Conv2d）。
             vendor 已 curl 到 third_party/MM-UNet/（MIT License）。

env_tag    : 'mamba'（需独立 mamba_venv，见 BASELINE_SPEC §3）

TODO（4 个已知盲区，禁止臆造填值）:
  TODO-1: epochs — config.yml=3000 vs 论文=500；此处以论文 500 为准，
          需 researcher 核 train.sh 最终确认。
  TODO-2: DiceFocalLoss alpha/gamma — monai 默认 gamma=2.0，
          官方 train.py 未传参（用 monai 默认），需确认 monai 版本默认值。
  TODO-3: STARE bs — config.yml=5 vs 论文=2；此处以论文 2 为准，
          需 researcher 确认。
  TODO-4: 8GB 显存 input 608×608 疑 OOM；正式训练走 HPC (24GB)，
          本机仅做烟测（降 size 至 256 cpu 模式）。

Windows 规范 :
  - 无 scipy.stats
  - 无 multiprocessing
  - 路径用 pathlib.Path
  - pin_memory=False（spawn worker 不支持）
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

# vendor 路径
_VENDOR_DIR = Path(__file__).parent.parent / "third_party" / "MM-UNet"


# --------------------------------------------------------------------------- #
#  LinearWarmupCosineAnnealingLR（官方 src/optimizer.py 忠实移植，MIT License）
#  Source: github.com/liujiawen-jpg/MM-UNet/src/optimizer.py
# --------------------------------------------------------------------------- #

import math
import warnings


class _LinearWarmupCosineAnnealingLR(torch.optim.lr_scheduler._LRScheduler):
    """
    官方 LinearWarmupCosineAnnealingLR（MONAI 实现，MIT License）。
    线性 warmup → cosine 衰减到 eta_min。
    Source: github.com/liujiawen-jpg/MM-UNet/src/optimizer.py（忠实移植，无修改）
    """

    def __init__(
        self,
        optimizer: torch.optim.Optimizer,
        warmup_epochs: int,
        max_epochs: int,
        warmup_start_lr: float = 0.0,
        eta_min: float = 0.0,
        last_epoch: int = -1,
    ) -> None:
        self.warmup_epochs = warmup_epochs
        self.max_epochs = max_epochs
        self.warmup_start_lr = warmup_start_lr
        self.eta_min = eta_min
        super().__init__(optimizer, last_epoch)

    def get_lr(self):
        if not self._get_lr_called_within_step:
            warnings.warn(
                "To get the last learning rate computed by the scheduler, "
                "please use `get_last_lr()`.",
                UserWarning,
            )
        if self.last_epoch == 0:
            return [self.warmup_start_lr] * len(self.base_lrs)
        elif self.last_epoch < self.warmup_epochs:
            return [
                group["lr"] + (base_lr - self.warmup_start_lr) / (self.warmup_epochs - 1)
                for base_lr, group in zip(self.base_lrs, self.optimizer.param_groups)
            ]
        elif self.last_epoch == self.warmup_epochs:
            return self.base_lrs
        elif (self.last_epoch - 1 - self.max_epochs) % (
            2 * (self.max_epochs - self.warmup_epochs)
        ) == 0:
            return [
                group["lr"]
                + (base_lr - self.eta_min)
                * (1 - math.cos(math.pi / (self.max_epochs - self.warmup_epochs)))
                / 2
                for base_lr, group in zip(self.base_lrs, self.optimizer.param_groups)
            ]
        return [
            (
                1
                + math.cos(
                    math.pi
                    * (self.last_epoch - self.warmup_epochs)
                    / (self.max_epochs - self.warmup_epochs)
                )
            )
            / (
                1
                + math.cos(
                    math.pi
                    * (self.last_epoch - self.warmup_epochs - 1)
                    / (self.max_epochs - self.warmup_epochs)
                )
            )
            * (group["lr"] - self.eta_min)
            + self.eta_min
            for group in self.optimizer.param_groups
        ]

    def _get_closed_form_lr(self):
        if self.last_epoch < self.warmup_epochs:
            return [
                self.warmup_start_lr
                + self.last_epoch
                * (base_lr - self.warmup_start_lr)
                / (self.warmup_epochs - 1)
                for base_lr in self.base_lrs
            ]
        return [
            self.eta_min
            + 0.5
            * (base_lr - self.eta_min)
            * (
                1
                + math.cos(
                    math.pi
                    * (self.last_epoch - self.warmup_epochs)
                    / (self.max_epochs - self.warmup_epochs)
                )
            )
            for base_lr in self.base_lrs
        ]


# --------------------------------------------------------------------------- #
#  Loss helper — DiceFocalLoss wrapper（官方 monai loss）
# --------------------------------------------------------------------------- #

class _DiceFocalLossWrapper:
    """
    MM-UNet 官方 loss = monai.losses.DiceFocalLoss。
    官方 train.py:
      loss_functions = {'dice_focal_loss':
          monai.losses.DiceFocalLoss(smooth_nr=0, smooth_dr=1e-5,
                                     to_onehot_y=False, sigmoid=True)}
      loss_weights = {'dice_focal_loss': 1.0}

    signature: (logits, target, fov_mask) -> scalar
    官方未做 FOV masking，fov_mask 接收但忽略（与官方一致）。

    TODO-2: DiceFocalLoss alpha/gamma 官方未显式传参（用 monai 默认）。
            monai 默认 gamma=2.0, lambda_dice=1.0, lambda_focal=1.0。
            需确认 monai 版本以对齐精确超参。
    """

    def __init__(self) -> None:
        self._loss_fn = None  # lazy init（避免 import 时要求 monai 已装）

    def _get_loss_fn(self):
        if self._loss_fn is not None:
            return self._loss_fn
        try:
            import monai.losses as monai_losses
        except ImportError as exc:
            raise RuntimeError(
                "MM-UNet loss 需要 monai，当前环境未安装。\n"
                "请在 mamba_venv 中 pip install monai\n"
                f"原始 ImportError: {exc}"
            ) from exc
        self._loss_fn = monai_losses.DiceFocalLoss(
            smooth_nr=0,
            smooth_dr=1e-5,
            to_onehot_y=False,
            sigmoid=True,
            # alpha/gamma 未显式传参，使用 monai 默认
            # TODO-2: 需确认 monai 版本默认值（gamma=2.0?）
        )
        return self._loss_fn

    def __call__(
        self,
        logits: torch.Tensor,
        target: torch.Tensor,
        fov_mask: torch.Tensor,
    ) -> torch.Tensor:
        loss_fn = self._get_loss_fn()
        # 官方无 FOV masking，fov_mask 忽略（与官方 train.py 一致）
        return loss_fn(logits, target)


# --------------------------------------------------------------------------- #
#  Adapter
# --------------------------------------------------------------------------- #

@register
class MMUNetAdapter(BaselineAdapter):
    """
    MM-UNet (Morph Mamba UNet) baseline adapter.

    官方 repo : https://github.com/liujiawen-jpg/MM-UNet (MIT License)
    env_tag   : 'mamba' — 需 mamba_venv（mamba-ssm + causal-conv1d）
    vendor    : third_party/MM-UNet/（MIT License，已 curl）

    ⚠️ build_model 依赖 mamba_ssm CUDA kernel：
       本地（主 env）无 mamba_ssm → 抛 RuntimeError 并给出 HPC 指引。
       HPC mamba_venv 中正常实例化。

    forward 输出说明：
       MM_Net.forward() 末尾返回多个 SideoutBlock 输出之和（各末尾均为
       nn.Conv2d，无激活函数），即 logits（非 prob）。
       本 adapter forward_adapt 接收 logits，直接返回 logits，
       与 harness evaluate.py 统一 threshold 约定对齐。
    """

    name: str = "mm_unet"
    kind: str = KIND_ARCHITECTURE
    source_repo: str = "https://github.com/liujiawen-jpg/MM-UNet"
    env_tag: str = ENV_MAMBA

    def build_model(self, cfg: Dict[str, Any]) -> nn.Module:
        """
        构建 MM_Net（依赖 mamba_ssm）。

        cfg keys (from configs/baselines/mm_unet.yaml):
          num_classes     : int (default 1)
          num_slices_list : list (default [64,32,16,8])
          out_indices     : list (default [0,1,2,3])
          heads           : list (default [1,2,4,4])

        ⚠️ MM_Net encoder1 硬编码 Conv2d(3, 64, ...)，
           输入必须为 3 通道（RGB 或 灰度 repeat×3）。

        Raises:
            RuntimeError: 若 mamba_ssm 未安装（需 mamba_venv）。
        """
        # 先检查 mamba_ssm 是否可用
        try:
            import mamba_ssm  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "MM-UNet 需要 mamba-ssm CUDA kernel，当前环境未安装。\n"
                "请在 HPC mamba_venv 中运行（见 BASELINE_SPEC §3）：\n"
                "  pip install mamba-ssm causal-conv1d（HF torch29-cu126 wheel）\n"
                "  TORCH_CUDA_ARCH_LIST='8.9' pip install mamba-ssm --no-build-isolation\n"
                f"原始 ImportError: {exc}"
            ) from exc

        # 把 vendor 目录加进 sys.path（MM_Net 在 src/UM_Net/MMUNet.py）
        vendor_src_dir = _VENDOR_DIR / "src" / "UM_Net"
        if str(vendor_src_dir) not in sys.path:
            sys.path.insert(0, str(vendor_src_dir))

        from MMUNet import MM_Net

        num_classes = int(cfg.get("num_classes", 1))
        num_slices_list = list(cfg.get("num_slices_list", [64, 32, 16, 8]))
        out_indices = list(cfg.get("out_indices", [0, 1, 2, 3]))
        heads = list(cfg.get("heads", [1, 2, 4, 4]))

        model = MM_Net(
            num_classes=num_classes,
            num_slices_list=num_slices_list,
            out_indices=out_indices,
            heads=heads,
        )
        return model

    def build_loss(self, cfg: Dict[str, Any]) -> _DiceFocalLossWrapper:
        """
        官方 loss = monai.losses.DiceFocalLoss（官方 train.py）。
        lazy init，不在 import 时要求 monai 已装。
        """
        return _DiceFocalLossWrapper()

    def build_optimizer(
        self,
        model: nn.Module,
        cfg: Dict[str, Any],
    ) -> torch.optim.Optimizer:
        """
        AdamW lr=0.001, weight_decay=0.05, betas=(0.9, 0.95)。
        官方用 timm.optim.optim_factory.create_optimizer_v2，
        此处直接用 PyTorch AdamW 对齐等价超参（无需 timm 依赖）。
        Source: github.com/liujiawen-jpg/MM-UNet/train.py
          optimizer = optim_factory.create_optimizer_v2(model,
              opt='adamw', weight_decay=0.05, lr=0.001, betas=(0.9, 0.95))
        """
        lr = float(cfg.get("lr", 1e-3))
        wd = float(cfg.get("weight_decay", 0.05))
        betas = tuple(cfg.get("betas", [0.9, 0.95]))
        return torch.optim.AdamW(
            model.parameters(), lr=lr, weight_decay=wd, betas=betas
        )

    def build_scheduler(
        self,
        optimizer: torch.optim.Optimizer,
        cfg: Dict[str, Any],
    ) -> Optional[Any]:
        """
        LinearWarmupCosineAnnealingLR warmup=2ep, max_epochs=500, eta_min=1e-7。
        官方 Source: github.com/liujiawen-jpg/MM-UNet/train.py
          scheduler = LinearWarmupCosineAnnealingLR(optimizer,
              warmup_epochs=config.trainer.warmup,   # 2
              max_epochs=config.trainer.num_epochs)  # 3000 in config.yml

        TODO-1: epochs — config.yml=3000 vs 论文=500。
                此处以论文 500 为准；eta_min=1e-7（来自 config.yml min_lr）。
                需 researcher 核 train.sh 最终确认。
        """
        warmup_epochs = int(cfg.get("warmup_epochs", 2))
        max_epochs = int(cfg.get("epochs", 500))  # TODO-1: 论文500 vs config 3000
        eta_min = float(cfg.get("min_lr", 1e-7))
        return _LinearWarmupCosineAnnealingLR(
            optimizer,
            warmup_epochs=warmup_epochs,
            max_epochs=max_epochs,
            eta_min=eta_min,
        )

    def preprocess_cfg(self) -> Dict[str, Any]:
        """
        官方预处理：
          - 3 通道 RGB（encoder1 = Conv2d(3, 64, ...)，非单通道）
          - ImageNet 归一化 mean=[0.485,0.456,0.406] std=[0.229,0.224,0.225]
            Source: config.yml dataset.DRIVE.image_mean / image_std
          - DRIVE: input=608×608
          - STARE: input=704×704
          - input_mode=fullimg（全图推理，官方用 monai SlidingWindowInferer overlap=0.5）
        """
        return {
            "channels": "rgb",                  # 3 通道 RGB（官方 encoder1=Conv2d(3,...)）
            "normalize": {
                "mean": [0.485, 0.456, 0.406],  # ImageNet mean（官方 config.yml）
                "std": [0.229, 0.224, 0.225],   # ImageNet std（官方 config.yml）
            },
            "input_mode": "fullimg",            # 全图推理（官方 SlidingWindowInferer）
            "patch_size": None,
            "clahe": False,
            "extra": {
                "resize": 608,                  # DRIVE 官方 input=608（STARE=704）
                # TODO-3: STARE bs — config.yml=5 vs 论文=2，以论文 2 为准
                "dataset_resize": {
                    "DRIVE": 608,               # 官方 config.yml DRIVE image_size
                    "STARE": 704,               # 官方 config.yml STARE image_size
                },
                "sliding_window_overlap": 0.5,  # 官方 SlidingWindowInferer overlap=0.5
                "note": (
                    "MM-UNet input=608×608 (DRIVE), 704×704 (STARE), 3ch RGB. "
                    "Encoder1=Conv2d(3,64,...), not grayscale. "
                    "TODO-4: 8GB VRAM input608 疑 OOM，正式训练走 HPC (24GB). "
                    "Source: github.com/liujiawen-jpg/MM-UNet train.py + config.yml"
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
        全图推理：resize 到 608×608 → MM_Net forward → resize 回原尺寸。

        MM_Net.forward() 输出 logits（无 sigmoid）：
          各 SideoutBlock 末尾为 nn.Conv2d（无激活），多尺度输出加和后
          插值到输入尺寸返回 —— 即 logits，非概率。

        Args:
            model : MM_Net 实例，eval 模式，已 .to(device)。
            x     : (B, 3, H, W) RGB 全图，已在 device 上。
            device: 推理设备。

        Returns:
            (B, 1, H, W) logits（与 harness evaluate.py threshold 约定对齐）。

        ⚠️ MM_Net 期望 3 通道输入；如 harness 传入单通道，
           此处自动 repeat 至 3 通道。
        """
        import torch.nn.functional as F

        model.eval()
        B, C, H, W = x.shape

        # MM_Net encoder1 = Conv2d(3, 64, ...)，强制 3 通道
        if C == 1:
            x = x.repeat(1, 3, 1, 1)
        elif C != 3:
            raise ValueError(
                f"MMUNetAdapter.forward_adapt: 期望 1 或 3 通道输入，实际 C={C}"
            )

        # resize 到 608×608（DRIVE 官方训练/推理尺寸）
        # TODO-4: 8GB 显存 input608 疑 OOM；本机只烟测（--smoke 降至 256）
        x_resized = F.interpolate(
            x, size=(608, 608), mode="bilinear", align_corners=False
        )

        with torch.no_grad():
            logits_608 = model(x_resized)  # MM_Net forward 输出 logits（无 sigmoid）

        # resize 回原始尺寸
        logits = F.interpolate(
            logits_608, size=(H, W), mode="bilinear", align_corners=False
        )

        assert logits.shape == (B, 1, H, W), (
            f"MMUNetAdapter.forward_adapt: shape mismatch, got {logits.shape}"
        )
        return logits
