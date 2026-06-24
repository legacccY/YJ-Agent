"""
base_adapter.py — BaselineAdapter abstract base class.

按 BASELINE_SPEC §2.3 定义 adapter 接口。
每个 baseline 实现此 ABC，让 evaluate.py / train_harness.py 做到
model-agnostic：只调接口，不感知内部实现细节。

接口约定:
  - forward_adapt: 输入 (B,1,H,W) 单通道 → 输出 (B,1,H,W) logits
    (全图推理时 patch 模型走滑窗 hook 在子类实现，主调方不感知)
  - 所有超参从 cfg dict 读取，子类不硬编码（方便 yaml 驱动）

Windows 安全：无 multiprocessing 调用，无 scipy.stats 导入。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

import torch
import torch.nn as nn


# --------------------------------------------------------------------------- #
#  Literal type tags (避免 typing_extensions 依赖)
# --------------------------------------------------------------------------- #

KIND_ARCHITECTURE = "architecture"   # 整套模型是变量（尊重官方所有配方）
KIND_LOSS = "loss"                   # 仅 loss 是变量（统一 backbone + 超参）
ENV_MAIN = "main"                    # 主 gdn2venv
ENV_MAMBA = "mamba"                  # 独立 mamba_venv（A9-A12）


# --------------------------------------------------------------------------- #
#  BaselineAdapter ABC
# --------------------------------------------------------------------------- #

class BaselineAdapter(ABC):
    """
    Abstract base class for all baseline adapters.

    每个 baseline 继承此类并实现所有 abstract 方法。
    接口设计原则：
      - 量尺（评估）= evaluate.py 强制统一，adapter 只负责给出全图 logits。
      - 配方（训练）= adapter 自定义，通过 build_optimizer / preprocess_cfg 暴露。

    Attributes (class-level, 子类必须赋值):
        name        : str  — 唯一标识，用于 registry key 和 csv 的 baseline 列
        kind        : str  — 'architecture' | 'loss'
        source_repo : str  — 官方 repo URL（用于审稿人可追溯）
        env_tag     : str  — 'main' | 'mamba'（决定 HPC 用哪个 venv）
    """

    # 子类必须覆盖这四个属性
    name: str = ""
    kind: str = KIND_ARCHITECTURE
    source_repo: str = ""
    env_tag: str = ENV_MAIN

    # ---------------------------------------------------------------------- #
    #  Model / loss / optimizer
    # ---------------------------------------------------------------------- #

    @abstractmethod
    def build_model(self, cfg: Dict[str, Any]) -> nn.Module:
        """
        构建并返回 nn.Module。
        cfg 包含该 baseline 的所有超参（从 yaml 加载）。
        返回的模型应处于 CPU 上（外部调用方负责 .to(device)）。

        Args:
            cfg: dict，yaml 解析结果，至少包含 yaml 里的全部 key。

        Returns:
            nn.Module，输出 logits (B, 1, H, W)。
        """
        ...

    @abstractmethod
    def build_loss(self, cfg: Dict[str, Any]) -> Any:
        """
        构建并返回 loss callable。
        architecture 类：返回该方法官方 loss（CE/Dice/etc.）。
        loss 类：返回对应 topology loss。

        signature: loss_fn(logits, target, fov_mask) -> scalar tensor
        其中 logits/target/fov_mask 均为 (B,1,H,W)，device 与 model 一致。

        Args:
            cfg: dict，yaml 解析结果。

        Returns:
            callable，接受 (logits, target, fov_mask) → loss tensor。
        """
        ...

    @abstractmethod
    def build_optimizer(
        self,
        model: nn.Module,
        cfg: Dict[str, Any],
    ) -> torch.optim.Optimizer:
        """
        构建并返回 optimizer（以及可选 scheduler，见下方 build_scheduler）。
        复现零偏离：严格按官方超参（lr/weight_decay/momentum）。
        TODO 超参在 cfg 里用 'TODO_researcher_...' 占位，子类接到 TODO 值时抛 ValueError。

        Args:
            model: build_model 返回并已 .to(device) 的模型。
            cfg:   dict，yaml 解析结果。

        Returns:
            torch.optim.Optimizer 实例。
        """
        ...

    def build_scheduler(
        self,
        optimizer: torch.optim.Optimizer,
        cfg: Dict[str, Any],
    ) -> Optional[Any]:
        """
        构建并返回 LR scheduler（可选，子类 override）。
        默认返回 None（不使用 scheduler）。

        Args:
            optimizer: build_optimizer 返回的 optimizer。
            cfg:       dict，yaml 解析结果。

        Returns:
            scheduler 实例或 None。
        """
        return None

    # ---------------------------------------------------------------------- #
    #  Preprocessing spec
    # ---------------------------------------------------------------------- #

    @abstractmethod
    def preprocess_cfg(self) -> Dict[str, Any]:
        """
        返回该 baseline 官方预处理配置（用于 train_harness 决定数据通道/标准化策略）。
        这是"尊重官方"的预处理申报，不影响评估（evaluate.py 自己决定如何输入）。

        Returns:
            dict，包含：
              channels: 'green_clahe' | 'rgb' | 'green_raw'
              normalize: dict with keys 'mean', 'std' (per-channel lists)
              input_mode: 'fullimg' | 'patch'  (训练时)
              patch_size: int | None
              clahe: bool
              extra: dict  (其他 baseline 专有配置)
        """
        ...

    # ---------------------------------------------------------------------- #
    #  Inference / forward
    # ---------------------------------------------------------------------- #

    @abstractmethod
    def forward_adapt(
        self,
        model: nn.Module,
        x: torch.Tensor,
        device: torch.device,
    ) -> torch.Tensor:
        """
        全图推理适配器（evaluate.py 强制调此接口）。

        BASELINE_SPEC §2.3 核心约束：
          - 输入 x : (B, 1, H, W) 或 (B, 3, H, W)（取决于 preprocess_cfg channels）
                     **统一传入全图**（不管训练时用 patch）
          - 输出   : (B, 1, H, W) logits（无 sigmoid，evaluate.py 自己 threshold）
          - 全图拼接：patch 训练模型（FR-UNet 等）在此做滑窗推理并拼回全图。
            整图训练模型直接 forward。

        Args:
            model:  build_model 返回并已 .to(device) 的模型，处于 eval 模式。
            x:      (B, ?, H, W) 输入张量（已在 device 上）。
            device: torch.device，当前推理设备。

        Returns:
            (B, 1, H, W) logits tensor（在 device 上）。

        Note:
            滑窗推理占位 hook：patch 模型子类在此处实现滑窗，
            本基类提供 _sliding_window_inference 辅助方法。
            # TODO: 待 FR-UNet 等 patch 模型 adapter 实现时填充。
        """
        ...

    # ---------------------------------------------------------------------- #
    #  Benchmark preprocessing hook — adapter-specific image preprocessing
    #  for evaluate_benchmark (断点续连 leaderboard path).
    # ---------------------------------------------------------------------- #

    def preprocess_benchmark_image(
        self,
        npz_image: "np.ndarray",
        image_id: str,
        dataset_name: str,
        data_root: Optional[str] = None,
    ) -> "Tuple[np.ndarray, Tuple[int, int]]":
        """
        Return (preprocessed_image, (orig_H, orig_W)) ready to be wrapped into
        a (1, 1, H', W') tensor and passed to forward_adapt.

        Default implementation (non-FR-UNet adapters):
          - Returns npz_image as-is (green+CLAHE+norm(0.5,0.1), float32 (H,W)).
          - orig_H, orig_W = image height/width (no square padding needed).

        FR-UNet adapter overrides this to apply the official pipeline:
          BT.601 Grayscale → global-stats normalize → per-image minmax → [0,1]
          → frunet_get_square(target_size) → (H_sq, W_sq) + original (H, W).

        Args:
            npz_image:    (H, W) float32 from NPZ 'image' field
                          (green+CLAHE+norm, the default non-FR-UNet distribution).
            image_id:     str image identifier stored in NPZ (e.g. '37').
            dataset_name: lowercase dataset name stored in NPZ (e.g. 'drive').
            data_root:    Optional raw dataset root dir (needed by FR-UNet to
                          reload image with its own pipeline). None for adapters
                          that can use npz_image directly.

        Returns:
            (processed_image, (orig_H, orig_W)):
              processed_image — (H', W') float32, ready for forward_adapt.
              (orig_H, orig_W) — original un-padded size for cropping logit back.

        Note:
            forward_adapt receives (1, 1, H', W') built from processed_image.
            After forward_adapt returns (1, 1, H', W') logits, caller crops back
            to (orig_H, orig_W) before computing metrics.
        """
        # Default: npz_image already has the correct distribution for most adapters
        # (green channel + CLAHE + normalise(0.5, 0.1) — matches BaseVesselDataset).
        import numpy as _np
        img = npz_image.astype(_np.float32)
        orig_H, orig_W = img.shape
        return img, (orig_H, orig_W)

    # ---------------------------------------------------------------------- #
    #  Optional: sliding window helper (patch 模型复用)
    # ---------------------------------------------------------------------- #

    def _sliding_window_inference(
        self,
        model: nn.Module,
        x: torch.Tensor,
        patch_size: int,
        stride: int,
        device: torch.device,
    ) -> torch.Tensor:
        """
        滑窗推理辅助：将全图 x 分 patch 推理后拼回全图 logits。
        结果 = overlap 区域取平均（Gaussian 权重或均匀权重）。

        # TODO: 实现滑窗拼图（FR-UNet patch=64/stride 待定，query researcher）
        #       当前抛 NotImplementedError 作占位，防止 patch 模型 adapter
        #       忘记实现时静默产出错误结果。

        Args:
            model:      eval 模式的模型。
            x:          (B, 1, H, W) 全图输入。
            patch_size: 推理用 patch 边长。
            stride:     滑窗步长（< patch_size 时有 overlap）。
            device:     推理设备。

        Returns:
            (B, 1, H, W) 全图 logits。

        Raises:
            NotImplementedError: 当前版本占位，patch 模型 adapter 必须自行实现。
        """
        # TODO: 实现滑窗拼图（FR-UNet stride 官方未明示，待 researcher 确认）
        raise NotImplementedError(
            "_sliding_window_inference is a placeholder. "
            "Patch-based model adapters must override forward_adapt "
            "and implement their own sliding window logic.\n"
            "See BASELINE_SPEC §2.3 for the expected contract."
        )

    # ---------------------------------------------------------------------- #
    #  Repr
    # ---------------------------------------------------------------------- #

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"name={self.name!r}, kind={self.kind!r}, "
            f"env_tag={self.env_tag!r})"
        )

    # ---------------------------------------------------------------------- #
    #  Validation helper（registry 注册时调用）
    # ---------------------------------------------------------------------- #

    def validate_attrs(self) -> None:
        """
        检查 name/kind/source_repo/env_tag 均已被子类赋值。
        registry.register 装饰器会自动调此方法。

        Raises:
            ValueError: 若任意属性未被子类覆盖（仍为空字符串）。
        """
        missing = []
        if not self.name:
            missing.append("name")
        if self.kind not in (KIND_ARCHITECTURE, KIND_LOSS):
            missing.append(f"kind (got {self.kind!r}, "
                           f"must be {KIND_ARCHITECTURE!r} or {KIND_LOSS!r})")
        if not self.source_repo:
            missing.append("source_repo")
        if self.env_tag not in (ENV_MAIN, ENV_MAMBA):
            missing.append(f"env_tag (got {self.env_tag!r}, "
                           f"must be {ENV_MAIN!r} or {ENV_MAMBA!r})")
        if missing:
            raise ValueError(
                f"{self.__class__.__name__} missing required attrs: {missing}"
            )
