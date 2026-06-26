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

⚠️ two_stage 说明（evaluate_benchmark 路径）:
  evaluate.py evaluate_benchmark 调用路径：
    adapter = get_adapter('creatis_postproc')        # 新实例
    model = adapter.build_model(cfg).to(device)      # build_model 内部加载 Stage-1 backbone
                                                      # 到 adapter._stage1_model（实例属性）
    model.load_state_dict(ckpt_stage2)               # ckpt = Stage-2 creatis 权重
    ...
    inp_t = preprocess_image(npz_image)              # green+CLAHE+norm (H,W) → (1,1,H,W)
    logits = adapter.forward_adapt(model, inp_t, device)
    # 内部：self._stage1_model(inp_t) → backbone logits → sigmoid+bin → Stage-2 → logit 返回

  两段式关键：
    - build_model 时从 cfg['stage1_ckpt'] 加载 Stage-1 backbone 到 self._stage1_model。
    - forward_adapt 检测 self._stage1_model 是否存在：
        有 → inp_t 是原始图像 tensor → Stage-1 forward → Stage-2 forward
        无 → 兼容旧路径（train_harness Stage-2 训练时，inp_t 是 backbone logits）。

  cfg keys（evaluate_benchmark 路径必填）:
    stage1_ckpt    : str  — Stage-1 ckpt best.pth 路径（backbone_unet 或 fr_unet）
    stage1_adapter : str  — Stage-1 架构类型（默认 'backbone_unet'；
                            用户拍板=批1 FR-UNet ckpt 复用，设为 'fr_unet'）
    stage1_base_ch : int  — Stage-1 backbone_unet base_ch（默认 32；fr_unet 时忽略）

  训练说明:
    Stage 1 训练: 用统一 backbone_unet 的 train_harness，不需要特殊处理。
    Stage 2 训练: 调用 build_model(cfg) 返回 creatis reconnecting model，
                  用 build_optimizer / build_loss 做官方训练（PonderatedDiceloss + Adam）。
                  ⚠️ Stage-2 训练时 cfg 中不传 stage1_ckpt，避免触发 Stage-1 加载。

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
    Ponderated Dice loss — 官方 train.py PonderatedDiceloss 忠实复刻。

    官方 forward(input, target, mask) 接受概率（sigmoid 已在外部施加）；
    此处 adapter 接受 logits，内部先 sigmoid（注释保留）。

    官方公式（train.py）:
      dice_1: 全图 Dice
        intersection_1 = sum(input * target)
        union_1        = sum(input) + sum(target)
        dice_1         = mean(1 - (2*inter + eps) / (union + eps))

      dice_2: mask（断点膨胀图 pos_i）区域 Dice
        target_2       = target * mask
        intersection_2 = sum(input * mask * target_2)
        union_2        = sum(input * mask) + sum(target_2)
        dice_2         = mean(1 - (2*inter + eps) / (union + eps))

      return (dice_1 + dice_2, dice_1, dice_2)  ← 三元组，官方如此

    mask 真源:
      官方 disconnect.py: pos = binary_dilation(fragments, disk(2)) → pos_{i}.png
      即断点区域的膨胀 mask，由 Stage-2 训练 dataloader 的 "mask" 列提供。

      ⚠️ TODO_harness: 现有 harness 接口 loss_fn(logits, target, fov_mask) 传 FOV mask，
        不是断点膨胀 mask。二者语义不同，不可互用。
        精确复现须 Stage-2 训练 dataloader 提供 pos_i 列传入此处。
        _CreatisLossWrapper 目前透传 fov_mask 作为 mask 占位；
        当断点 mask 接好后，替换调用侧传参即可（无需改此类）。

    forward 签名:
        input  : (B,1,H,W) 概率（adapter wrapper 层做 sigmoid，此处接概率）
        target : (B,1,H,W) binary {0,1}
        mask   : (B,1,H,W) 断点膨胀 mask（Stage-2 dataloader pos_i；
                  harness 未接好时由 wrapper 传 fov_mask 占位）

    Returns:
        (total, dice_1, dice_2) — 三元组，官方 train.py 如此，勿改为标量
    """

    def __init__(self, eps: float = 1e-6):
        super().__init__()
        self.eps = eps

    def forward(
        self,
        input: torch.Tensor,
        target: torch.Tensor,
        mask: torch.Tensor,
    ):
        """
        Args:
            input  : (B,1,H,W) 概率（sigmoid 已在 wrapper 施加）
            target : (B,1,H,W) binary float {0,1}
            mask   : (B,1,H,W) 断点膨胀 mask（pos_i）

        Returns:
            (total, dice_1, dice_2): tuple[Tensor, Tensor, Tensor]
              total 为标量，dice_1/dice_2 均为标量。
        """
        eps = self.eps
        dims = list(range(1, input.dim()))  # 对 spatial+channel 维求和

        # --- dice_1: 全图 Dice ---
        intersection_1 = torch.sum(input * target, dim=dims)
        union_1 = (
            torch.sum(input, dim=dims)
            + torch.sum(target, dim=dims)
        )
        dice_1 = torch.mean(
            1.0 - (2.0 * intersection_1 + eps) / (union_1 + eps)
        )

        # --- dice_2: mask 区域（断点膨胀图）Dice ---
        # 官方: target_2 = target * mask; inter_2 = sum(input*mask*target_2)
        target_2 = target * mask
        intersection_2 = torch.sum(input * mask * target_2, dim=dims)
        union_2 = (
            torch.sum(input * mask, dim=dims)
            + torch.sum(target_2, dim=dims)
        )
        dice_2 = torch.mean(
            1.0 - (2.0 * intersection_2 + eps) / (union_2 + eps)
        )

        return dice_1 + dice_2, dice_1, dice_2


class _CreatisLossWrapper(nn.Module):
    """
    Harness 兼容包装层：loss_fn(logits, target, fov_mask) → scalar。

    供 build_loss 返回，让 harness 透明调用（harness 期望标量返回）。
    内部步骤：
      1. sigmoid(logits) → prob
      2. 调用 _PonderatedDiceloss.forward(prob, target, mask)
         mask = fov_mask（占位，见 TODO_harness）
      3. 取 total（三元组[0]）返回标量

    TODO_harness: mask 参数应为 Stage-2 dataloader 提供的 pos_i 断点膨胀图，
      不是 FOV mask。当 Stage-2 训练管线接好断点 mask 列时，
      调用侧须替换 fov_mask 为实际 pos_i 张量，此 wrapper 无需改动。
      在此之前，dice_2 项计算的是「GT∩FOV 区域的 Dice」而非「断点区域 Dice」，
      与官方训练语义有差异——此为已知保真缺口，须训练管线提供 pos_i 后才消除。
    """

    def __init__(self, loss_fn: _PonderatedDiceloss):
        super().__init__()
        self.loss_fn = loss_fn

    def forward(
        self,
        logits: torch.Tensor,
        target: torch.Tensor,
        fov_mask: torch.Tensor,
    ) -> torch.Tensor:
        # logits → prob（官方原始 forward 接概率；此处 adapter 接 logits 内部转）
        prob = torch.sigmoid(logits)
        total, _d1, _d2 = self.loss_fn(prob, target, fov_mask)
        return total


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

    # 实例属性：Stage-1 backbone model（evaluate_benchmark 两段式路径）
    # 由 build_model(cfg) 在 cfg['stage1_ckpt'] 存在时设置；否则 None（兼容旧接口）。
    _stage1_model: Optional[nn.Module] = None

    # ---------------------------------------------------------------------- #
    #  build_model
    # ---------------------------------------------------------------------- #

    def build_model(self, cfg: Dict[str, Any]) -> nn.Module:
        """
        构建 creatis reconnecting model (monai UNet，Stage 2).

        官方架构 (train.py):
          monai.networks.nets.UNet(
            spatial_dims=2, in_channels=1, out_channels=1,
            channels=(16, 32, 64, 128), strides=(2, 2, 2),
            num_res_units=2, norm='INSTANCE'
          )

        cfg keys (from creatis.yaml):
          norm           : str  (default: 'INSTANCE' — 官方 config_training.json)
          model_dir      : str | None  (预训练权重目录；None = 从头训练)
          stage1_ckpt    : str | None  (Stage-1 ckpt best.pth 路径；
                                        设置后 forward_adapt 走完整两段式流程)
          stage1_adapter : str  (Stage-1 架构类型：'backbone_unet'(默认) / 'fr_unet'；
                                  用户拍板：批1 FR-UNet ckpt 复用，置 'fr_unet')
          stage1_base_ch : int  (backbone_unet base_ch，默认 32；fr_unet 时忽略)

        Side effect（evaluate_benchmark 路径）:
          若 cfg['stage1_ckpt'] 存在且文件可读，构建并加载 Stage-1 backbone_unet
          到 self._stage1_model（实例属性），以便 forward_adapt 做完整两段推理。
          若 stage1_ckpt 未设置，self._stage1_model = None（兼容 Stage-2 训练路径）。

        Returns:
            monai UNet（Stage-2 reconnecting model）on CPU（外部 .to(device)）。

        Raises:
            ImportError: monai 未安装。
        """
        from baselines.third_party.creatis_postproc.post_treatement import (
            _build_creatis_model,
            load_creatis_model,
        )

        norm = str(cfg.get("norm", "INSTANCE"))
        model_dir = cfg.get("model_dir", None)

        # ------------------------------------------------------------------ #
        #  Stage-1 backbone 加载（evaluate_benchmark 两段式路径）
        # ------------------------------------------------------------------ #
        stage1_ckpt    = cfg.get("stage1_ckpt", None)
        stage1_adapter = str(cfg.get("stage1_adapter", "backbone_unet")).lower()

        # 保存 stage1_adapter 类型供 preprocess_benchmark_image 使用
        self._stage1_adapter_type: str = stage1_adapter

        if stage1_ckpt is not None:
            stage1_path = Path(stage1_ckpt)
            if stage1_path.exists():
                # ---------------------------------------------------------- #
                #  Stage-1 架构分支
                # ---------------------------------------------------------- #
                if stage1_adapter == "fr_unet":
                    # 用户拍板：批1 FR-UNet ckpt 复用当 Stage-1。
                    # FR_UNet 官方默认参数（frunet.py 忠实移植）：
                    #   feature_scale=2 → filters=[32,64,128,256,512]
                    #   num_classes=1, num_channels=1, dropout=0.2,
                    #   fuse=True, out_ave=True
                    from baselines.adapters.frunet import FR_UNet as _FR_UNet
                    s1_model = _FR_UNet(
                        num_classes=1,
                        num_channels=1,
                        feature_scale=2,
                        dropout=0.2,
                        fuse=True,
                        out_ave=True,
                    )
                    s1_info = "FR_UNet(feature_scale=2, out_ave=True)"
                else:
                    # 默认：backbone_unet（models/unet.py UNet）
                    from models.unet import UNet as _UNet
                    base_ch = int(cfg.get("stage1_base_ch", 32))
                    s1_model = _UNet(in_ch=1, out_ch=1, base_ch=base_ch)
                    s1_info = f"backbone_unet UNet(base_ch={base_ch})"

                s1_ckpt_data = torch.load(str(stage1_path), map_location="cpu",
                                          weights_only=True)
                if isinstance(s1_ckpt_data, dict) and "state_dict" in s1_ckpt_data:
                    s1_ckpt_data = s1_ckpt_data["state_dict"]
                s1_model.load_state_dict(s1_ckpt_data)
                s1_model.eval()
                self._stage1_model: Optional[nn.Module] = s1_model
                print(
                    f"[CreatisPostprocAdapter] Stage-1 loaded: "
                    f"{stage1_path.name}  adapter={stage1_adapter!r}  ({s1_info})"
                )
            else:
                import warnings
                warnings.warn(
                    f"[CreatisPostprocAdapter] stage1_ckpt={stage1_ckpt!r} not found. "
                    "forward_adapt will use legacy mode (expects backbone logits as input). "
                    "Set stage1_ckpt to a valid best.pth for benchmark eval.",
                    UserWarning,
                )
                self._stage1_model = None
        else:
            # Stage-2 训练路径：不加载 Stage-1（forward_adapt 兼容旧 backbone-logits 输入）
            self._stage1_model = None
            # stage1_ckpt 未设置时仍记录 adapter 类型（默认 backbone_unet）
            self._stage1_adapter_type = stage1_adapter

        # ------------------------------------------------------------------ #
        #  Stage-2 creatis reconnecting model 构建
        # ------------------------------------------------------------------ #
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

    def build_loss(self, cfg: Dict[str, Any]) -> _CreatisLossWrapper:
        """
        PonderatedDiceloss（官方 train.py 忠实复刻）+ harness 兼容包装。

        Returns:
            _CreatisLossWrapper: loss_fn(logits, target, fov_mask) → scalar (total Dice)
              内部调用 _PonderatedDiceloss(prob, target, mask)，返回三元组取 total。

        NOTE — TODO_harness: fov_mask 在 Stage-2 训练时须替换为 pos_i 断点膨胀 mask。
          详见 _CreatisLossWrapper 和 _PonderatedDiceloss docstring。
        """
        inner = _PonderatedDiceloss(eps=float(cfg.get("loss_smooth", 1e-6)))
        return _CreatisLossWrapper(inner)

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
    #  preprocess_benchmark_image override
    #  当 stage1_adapter='fr_unet' 时，必须用 FR-UNet 官方预处理（BT.601 灰度
    #  + per-image minmax），否则 Stage-1 看到 green+CLAHE+norm(0.5,0.1) → OOD。
    # ---------------------------------------------------------------------- #

    def preprocess_benchmark_image(
        self,
        npz_image,
        image_id: str,
        dataset_name: str,
        data_root=None,
    ):
        """
        Two-stage creatis benchmark 预处理。

        Stage-1 = FR-UNet 时：
          委托给 FRUNetAdapter.preprocess_benchmark_image()
          → BT.601 Grayscale + per-image minmax + frunet_get_square padding
          （与 FR-UNet 训练期输入完全一致，消除 OOD）

        Stage-1 = backbone_unet 时：
          走默认路径：npz_image（green+CLAHE+norm(0.5,0.1)），直接返回。

        Args:
            npz_image:    (H, W) float32 — NPZ 'image' field (green+CLAHE+norm).
            image_id:     str, e.g. '37'.
            dataset_name: lowercase, e.g. 'drive'.
            data_root:    raw dataset root（FR-UNet 分支需要；backbone_unet 不用）.

        Returns:
            (processed_image, (orig_H, orig_W))
        """
        import numpy as _np

        # 判断 stage1_adapter 类型（若 build_model 尚未调用，_stage1_adapter_type
        # 可能未设置，此处 getattr fallback 到 'backbone_unet' 安全）
        adapter_type = getattr(self, "_stage1_adapter_type", "backbone_unet")

        if adapter_type == "fr_unet":
            # 委托给 FR-UNet adapter 的官方预处理路径
            from baselines.adapters.frunet import FRUNetAdapter as _FRUNetAdapter
            _fru = _FRUNetAdapter()
            return _fru.preprocess_benchmark_image(
                npz_image=npz_image,
                image_id=image_id,
                dataset_name=dataset_name,
                data_root=data_root,
            )
        else:
            # backbone_unet（默认）：green+CLAHE+norm(0.5,0.1) 直接用
            img = npz_image.astype(_np.float32)
            orig_H, orig_W = img.shape
            return img, (orig_H, orig_W)

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
        两阶段推理（支持两种调用路径）：

        路径 A — evaluate_benchmark 完整两段（self._stage1_model 已在 build_model 加载）:
          x = (B,1,H,W) 预处理图像 tensor，来自 preprocess_benchmark_image()：
              - stage1_adapter='fr_unet'：BT.601 grayscale + per-image minmax（无 CLAHE）
              - stage1_adapter='backbone_unet'：green+CLAHE+norm(0.5,0.1)
          1. Stage-1: self._stage1_model(x) → backbone logits
          2. sigmoid + threshold(0.5) → binary_mask
          3. Stage-2: apply_postproc_iterations (10 轮) → reconnected uint8
          4. 转回 (B,1,H,W) pseudo-logits 返回

        路径 B — 兼容旧接口（self._stage1_model is None，Stage-2 训练 / 外部传 logits）:
          x = (B,1,H,W) backbone output logits（Stage-1 已在外部计算）
          1. sigmoid + threshold(0.5) → binary_mask
          2. Stage-2: apply_postproc_iterations → reconnected uint8
          3. 转回 pseudo-logits 返回

        NOTE: creatis model（Stage-2）在此使用。如果 model 未加载预训练权重，
              输出无意义但接口仍正常（train_harness Stage-2 训练时正是此情形）。

        Args:
            model : creatis reconnecting monai UNet（Stage-2，build_model 返回的模型）
            x     : (B,1,H,W)
                    路径 A: 预处理图像（stage1_ckpt 设置后 build_model 启动时）
                    路径 B: backbone logits（stage1_ckpt 未设置或旧接口时）
            device: 推理设备

        Returns:
            (B,1,H,W) logits（pseudo-logit from reconnected probs，evaluate.py 做 sigmoid+thr）
        """
        assert x.shape[1] == 1 and x.ndim == 4, (
            f"CreatisPostprocAdapter.forward_adapt: expected (B,1,H,W), got {x.shape}"
        )

        from baselines.third_party.creatis_postproc.post_treatement import (
            apply_postproc_iterations,
        )

        model.eval()
        B, C, H, W = x.shape
        x = x.to(device)

        # ------------------------------------------------------------------ #
        #  路径 A: 完整两段式（evaluate_benchmark — 图像 tensor 输入）
        # ------------------------------------------------------------------ #
        if self._stage1_model is not None:
            s1 = self._stage1_model.to(device)
            s1.eval()
            with torch.no_grad():
                stage1_out = s1(x)
                # s1 可能返回 (logits, reid_ctx) tuple（ours_gdn2 等），取 logits
                if isinstance(stage1_out, tuple):
                    stage1_logits = stage1_out[0]
                else:
                    stage1_logits = stage1_out
            # sigmoid → binary mask
            prob_stage1 = torch.sigmoid(stage1_logits)
            binary_mask = (prob_stage1 >= 0.5).float()
        else:
            # ---------------------------------------------------------------- #
            #  路径 B: x 是 backbone logits（兼容旧接口 / Stage-2 训练中间态）
            # ---------------------------------------------------------------- #
            prob_stage1 = torch.sigmoid(x)
            binary_mask = (prob_stage1 >= 0.5).float()

        # ------------------------------------------------------------------ #
        #  Stage-2: apply creatis reconnecting model per sample
        # ------------------------------------------------------------------ #
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
