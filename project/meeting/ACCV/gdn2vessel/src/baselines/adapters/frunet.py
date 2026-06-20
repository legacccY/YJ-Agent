"""
frunet.py — Adapter for FR-UNet (Full-Resolution U-Net).

官方 repo  : https://github.com/lseventeen/FR-UNet  (MIT License)
官方论文   : JBHI 2022
官方超参   : Adam lr=1e-4 wd=1e-5; CosineAnnealingLR T_max=40; epochs=40;
             batch=512 patch 48×48 stride=6; BCELoss; 灰度单通道输入;
             channel-wise mean/std + minmax 归一化; AMP fp16.
             Source: BASELINE_SPEC.md §1 (researcher 二轮已核).

架构特点   : Full-Resolution multi-scale U-Net，保持 full-resolution 特征图，
             横向密集跳连，5 个输出头平均（out_ave=True）。
             训练时走 patch (48×48)，评估时走滑窗拼回全图。

重要说明   :
  - FR-UNet 是本 harness 唯一 patch-based baseline。
  - forward_adapt 实现 self-contained 滑窗推理（patch=48, stride=6）。
  - InitWeights_He 依赖 timm.trunc_normal_；若 timm 未装则 fallback 到
    kaiming_normal + 跳过 LayerNorm 初始化（不影响 inference 精度测试）。
  - 官方模型定义忠实移植自官方 fr_unet.py（curl 验证，commit: main branch）。

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
import torch.nn.functional as F

# 确保 src/ 在 sys.path
_src_dir = Path(__file__).parent.parent.parent
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from baselines.base_adapter import BaselineAdapter, ENV_MAIN, KIND_ARCHITECTURE
from baselines.registry import register


# --------------------------------------------------------------------------- #
#  InitWeights_He — 忠实移植自 FR-UNet/models/utils.py
#  官方依赖 timm.trunc_normal_；此处做软依赖，timm 缺失时 fallback 不报错。
# --------------------------------------------------------------------------- #

def _he_init(module: nn.Module, neg_slope: float = 1e-2) -> None:
    """逐模块 He 初始化，忠实移植自官方 utils.py 中 InitWeights_He.__call__。"""
    if isinstance(module, (nn.Conv2d, nn.Conv3d,
                           nn.ConvTranspose2d, nn.ConvTranspose3d)):
        nn.init.kaiming_normal_(module.weight, a=neg_slope)
        if module.bias is not None:
            nn.init.constant_(module.bias, 0)
    elif isinstance(module, nn.Linear):
        try:
            from timm.models.layers import trunc_normal_
            trunc_normal_(module.weight, std=neg_slope)
        except ImportError:
            nn.init.kaiming_normal_(module.weight, a=neg_slope)
        if module.bias is not None:
            nn.init.constant_(module.bias, 0)
    elif isinstance(module, nn.LayerNorm):
        nn.init.constant_(module.bias, 0)
        nn.init.constant_(module.weight, 1.0)


# --------------------------------------------------------------------------- #
#  FR-UNet 官方模型定义 — 忠实移植自 github.com/lseventeen/FR-UNet/models/fr_unet.py
#  (curl 验证，2026-06-20)。零改动，仅移除 from .utils import InitWeights_He 替换为本地实现。
# --------------------------------------------------------------------------- #

class _conv(nn.Module):
    def __init__(self, in_c: int, out_c: int, dp: float = 0):
        super().__init__()
        self.in_c = in_c
        self.out_c = out_c
        self.conv = nn.Sequential(
            nn.Conv2d(out_c, out_c, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(out_c),
            nn.Dropout2d(dp),
            nn.LeakyReLU(0.1, inplace=True),
            nn.Conv2d(out_c, out_c, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(out_c),
            nn.Dropout2d(dp),
            nn.LeakyReLU(0.1, inplace=True),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.conv(x)


class _feature_fuse(nn.Module):
    def __init__(self, in_c: int, out_c: int):
        super().__init__()
        self.conv11 = nn.Conv2d(in_c, out_c, kernel_size=1, padding=0, bias=False)
        self.conv33 = nn.Conv2d(in_c, out_c, kernel_size=3, padding=1, bias=False)
        self.conv33_di = nn.Conv2d(
            in_c, out_c, kernel_size=3, padding=2, bias=False, dilation=2
        )
        self.norm = nn.BatchNorm2d(out_c)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x1 = self.conv11(x)
        x2 = self.conv33(x)
        x3 = self.conv33_di(x)
        return self.norm(x1 + x2 + x3)


class _up(nn.Module):
    def __init__(self, in_c: int, out_c: int, dp: float = 0):
        super().__init__()
        self.up = nn.Sequential(
            nn.ConvTranspose2d(in_c, out_c, kernel_size=2, padding=0, stride=2, bias=False),
            nn.BatchNorm2d(out_c),
            nn.LeakyReLU(0.1, inplace=False),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.up(x)


class _down(nn.Module):
    def __init__(self, in_c: int, out_c: int, dp: float = 0):
        super().__init__()
        self.down = nn.Sequential(
            nn.Conv2d(in_c, out_c, kernel_size=2, padding=0, stride=2, bias=False),
            nn.BatchNorm2d(out_c),
            nn.LeakyReLU(0.1, inplace=True),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.down(x)


class _block(nn.Module):
    def __init__(
        self,
        in_c: int,
        out_c: int,
        dp: float = 0,
        is_up: bool = False,
        is_down: bool = False,
        fuse: bool = False,
    ):
        super().__init__()
        self.in_c = in_c
        self.out_c = out_c
        if fuse:
            self.fuse = _feature_fuse(in_c, out_c)
        else:
            self.fuse = nn.Conv2d(in_c, out_c, kernel_size=1, stride=1)

        self.is_up = is_up
        self.is_down = is_down
        self.conv = _conv(out_c, out_c, dp=dp)
        if self.is_up:
            self.up = _up(out_c, out_c // 2)
        if self.is_down:
            self.down = _down(out_c, out_c * 2)

    def forward(self, x: torch.Tensor):
        if self.in_c != self.out_c:
            x = self.fuse(x)
        x = self.conv(x)
        if not self.is_up and not self.is_down:
            return x
        elif self.is_up and not self.is_down:
            return x, self.up(x)
        elif not self.is_up and self.is_down:
            return x, self.down(x)
        else:
            return x, self.up(x), self.down(x)


class FR_UNet(nn.Module):
    """
    Full-Resolution U-Net — 忠实移植自官方 fr_unet.py。
    官方默认: num_classes=1, num_channels=1, feature_scale=2, dropout=0.2,
              fuse=True, out_ave=True.
    filters = [32, 64, 128, 256, 512] (after feature_scale=2 除以).
    """

    def __init__(
        self,
        num_classes: int = 1,
        num_channels: int = 1,
        feature_scale: int = 2,
        dropout: float = 0.2,
        fuse: bool = True,
        out_ave: bool = True,
    ):
        super().__init__()
        self.out_ave = out_ave
        filters = [64, 128, 256, 512, 1024]
        filters = [int(x / feature_scale) for x in filters]

        self.block1_3 = _block(num_channels, filters[0], dp=dropout, is_up=False, is_down=True, fuse=fuse)
        self.block1_2 = _block(filters[0], filters[0], dp=dropout, is_up=False, is_down=True, fuse=fuse)
        self.block1_1 = _block(filters[0] * 2, filters[0], dp=dropout, is_up=False, is_down=True, fuse=fuse)
        self.block10 = _block(filters[0] * 2, filters[0], dp=dropout, is_up=False, is_down=True, fuse=fuse)
        self.block11 = _block(filters[0] * 2, filters[0], dp=dropout, is_up=False, is_down=True, fuse=fuse)
        self.block12 = _block(filters[0] * 2, filters[0], dp=dropout, is_up=False, is_down=False, fuse=fuse)
        self.block13 = _block(filters[0] * 2, filters[0], dp=dropout, is_up=False, is_down=False, fuse=fuse)

        self.block2_2 = _block(filters[1], filters[1], dp=dropout, is_up=True, is_down=True, fuse=fuse)
        self.block2_1 = _block(filters[1] * 2, filters[1], dp=dropout, is_up=True, is_down=True, fuse=fuse)
        self.block20 = _block(filters[1] * 3, filters[1], dp=dropout, is_up=True, is_down=True, fuse=fuse)
        self.block21 = _block(filters[1] * 3, filters[1], dp=dropout, is_up=True, is_down=False, fuse=fuse)
        self.block22 = _block(filters[1] * 3, filters[1], dp=dropout, is_up=True, is_down=False, fuse=fuse)

        self.block3_1 = _block(filters[2], filters[2], dp=dropout, is_up=True, is_down=True, fuse=fuse)
        self.block30 = _block(filters[2] * 2, filters[2], dp=dropout, is_up=True, is_down=False, fuse=fuse)
        self.block31 = _block(filters[2] * 3, filters[2], dp=dropout, is_up=True, is_down=False, fuse=fuse)

        self.block40 = _block(filters[3], filters[3], dp=dropout, is_up=True, is_down=False, fuse=fuse)

        self.final1 = nn.Conv2d(filters[0], num_classes, kernel_size=1, padding=0, bias=True)
        self.final2 = nn.Conv2d(filters[0], num_classes, kernel_size=1, padding=0, bias=True)
        self.final3 = nn.Conv2d(filters[0], num_classes, kernel_size=1, padding=0, bias=True)
        self.final4 = nn.Conv2d(filters[0], num_classes, kernel_size=1, padding=0, bias=True)
        self.final5 = nn.Conv2d(filters[0], num_classes, kernel_size=1, padding=0, bias=True)
        self.fuse_out = nn.Conv2d(5, num_classes, kernel_size=1, padding=0, bias=True)

        self.apply(lambda m: _he_init(m))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x1_3, x_down1_3 = self.block1_3(x)
        x1_2, x_down1_2 = self.block1_2(x1_3)
        x2_2, x_up2_2, x_down2_2 = self.block2_2(x_down1_3)
        x1_1, x_down1_1 = self.block1_1(torch.cat([x1_2, x_up2_2], dim=1))
        x2_1, x_up2_1, x_down2_1 = self.block2_1(torch.cat([x_down1_2, x2_2], dim=1))
        x3_1, x_up3_1, x_down3_1 = self.block3_1(x_down2_2)
        x10, x_down10 = self.block10(torch.cat([x1_1, x_up2_1], dim=1))
        x20, x_up20, x_down20 = self.block20(torch.cat([x_down1_1, x2_1, x_up3_1], dim=1))
        x30, x_up30 = self.block30(torch.cat([x_down2_1, x3_1], dim=1))
        _, x_up40 = self.block40(x_down3_1)
        x11, x_down11 = self.block11(torch.cat([x10, x_up20], dim=1))
        x21, x_up21 = self.block21(torch.cat([x_down10, x20, x_up30], dim=1))
        _, x_up31 = self.block31(torch.cat([x_down20, x30, x_up40], dim=1))
        x12 = self.block12(torch.cat([x11, x_up21], dim=1))
        _, x_up22 = self.block22(torch.cat([x_down11, x21, x_up31], dim=1))
        x13 = self.block13(torch.cat([x12, x_up22], dim=1))

        if self.out_ave:
            output = (
                self.final1(x1_1)
                + self.final2(x10)
                + self.final3(x11)
                + self.final4(x12)
                + self.final5(x13)
            ) / 5
        else:
            output = self.final5(x13)

        return output  # (B, num_classes, H, W) logits（无 sigmoid，官方只输出 raw）


# --------------------------------------------------------------------------- #
#  BCELoss wrapper — 与 base_adapter 接口签名对齐 (logits, target, fov_mask)
# --------------------------------------------------------------------------- #

class _BCELossWithMask:
    """
    官方 FR-UNet 用 nn.BCELoss（训练时加 sigmoid）。
    adapter 接口要求 (logits, target, fov_mask) → scalar。
    此处等价实现：BCEWithLogitsLoss masked。
    """

    def __call__(
        self,
        logits: torch.Tensor,
        target: torch.Tensor,
        fov_mask: torch.Tensor,
    ) -> torch.Tensor:
        loss = F.binary_cross_entropy_with_logits(logits, target, reduction="none")
        n_valid = fov_mask.sum().clamp(min=1)
        return (loss * fov_mask).sum() / n_valid


# --------------------------------------------------------------------------- #
#  Adapter
# --------------------------------------------------------------------------- #

@register
class FRUNetAdapter(BaselineAdapter):
    """
    FR-UNet (Full-Resolution U-Net) baseline adapter.

    官方 repo : https://github.com/lseventeen/FR-UNet (MIT)
    超参来源  : BASELINE_SPEC §1; researcher 二轮核实。
    特殊点    : 唯一 patch-based baseline，forward_adapt 实现滑窗拼回全图。
    """

    name: str = "fr_unet"
    kind: str = KIND_ARCHITECTURE
    source_repo: str = "https://github.com/lseventeen/FR-UNet"
    env_tag: str = ENV_MAIN

    # 官方训练时 patch 配置
    _PATCH_SIZE: int = 48
    _STRIDE: int = 6  # 官方: patch 48×48 stride6（BASELINE_SPEC §1 & 官方论文 JBHI22）

    def build_model(self, cfg: Dict[str, Any]) -> nn.Module:
        """
        构建 FR_UNet。

        cfg keys (from baselines/frunet.yaml):
          num_classes   : int (default 1)
          num_channels  : int (default 1, 灰度单通道)
          feature_scale : int (default 2, filters=[32,64,128,256,512])
          dropout       : float (default 0.2)
          fuse          : bool (default True)
          out_ave       : bool (default True, 5头平均)
        """
        return FR_UNet(
            num_classes=int(cfg.get("num_classes", 1)),
            num_channels=int(cfg.get("num_channels", 1)),
            feature_scale=int(cfg.get("feature_scale", 2)),
            dropout=float(cfg.get("dropout", 0.2)),
            fuse=bool(cfg.get("fuse", True)),
            out_ave=bool(cfg.get("out_ave", True)),
        )

    def build_loss(self, cfg: Dict[str, Any]) -> _BCELossWithMask:
        """官方 loss = BCELoss（此处等价为 BCEWithLogitsLoss + FOV mask）。"""
        return _BCELossWithMask()

    def build_optimizer(
        self,
        model: nn.Module,
        cfg: Dict[str, Any],
    ) -> torch.optim.Optimizer:
        """Adam lr=1e-4, weight_decay=1e-5（官方）。"""
        lr = float(cfg.get("lr", 1e-4))
        wd = float(cfg.get("weight_decay", 1e-5))
        return torch.optim.Adam(model.parameters(), lr=lr, weight_decay=wd)

    def build_scheduler(
        self,
        optimizer: torch.optim.Optimizer,
        cfg: Dict[str, Any],
    ) -> Optional[Any]:
        """CosineAnnealingLR T_max=40（官方）。"""
        t_max = int(cfg.get("scheduler_T_max", 40))
        return torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=t_max)

    def preprocess_cfg(self) -> Dict[str, Any]:
        """
        FR-UNet 官方预处理：灰度单通道，channel-wise mean/std + minmax 归一化，无 CLAHE。
        训练时切 patch 48×48（stride=6），评估时传全图由 forward_adapt 滑窗拼回。
        mean/std: TODO_researcher — 官方 README/code 未公开具体值，
                  BASELINE_SPEC 给出 minmax 归一化；此处 mean=0 std=1 为 minmax 后等价占位。
                  实际训练时需查官方 dataset.py 确认。
        """
        return {
            "channels": "green_raw",   # 灰度单通道，官方用绿通道或灰度（视网膜场景）
            "normalize": {
                "mean": [0.0],         # TODO: 官方未公开精确 mean/std，minmax 后占位
                "std": [1.0],          # TODO: 官方未公开精确 mean/std，minmax 后占位
            },
            "input_mode": "patch",
            "patch_size": self._PATCH_SIZE,
            "clahe": False,            # 官方无 CLAHE
            "extra": {
                "stride": self._STRIDE,
                "batch_size_train": 512,  # 官方 bs=512 patch/batch
                "note": (
                    "FR-UNet trains on grayscale patches 48×48 stride=6. "
                    "Evaluation: sliding-window inference reassembled to full image. "
                    "Source: JBHI22 + BASELINE_SPEC §1."
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
        滑窗推理：将全图 x 分 patch 48×48 stride=6 推理，overlap 区域取均值拼回全图。

        Args:
            model : FR_UNet 实例，处于 eval 模式，已 .to(device)。
            x     : (B, 1, H, W) 全图单通道输入，已在 device 上。
            device: 推理设备。

        Returns:
            (B, 1, H, W) logits（未 sigmoid）。

        实现说明:
          - 边缘不足一个 patch 时用 reflect padding 填满再裁回。
          - 重叠区域取均值（sum / count）。
          - 纯 torch 实现，无额外依赖。
        """
        model.eval()
        patch_size = self._PATCH_SIZE
        stride = self._STRIDE

        B, C, H, W = x.shape
        assert C == 1, f"FRUNetAdapter: 期望单通道输入 (B,1,H,W), 实际 C={C}"

        # ---------- pad 到 patch_size 的整数倍（边缘 reflect） ----------
        pad_h = (patch_size - H % patch_size) % patch_size
        pad_w = (patch_size - W % patch_size) % patch_size
        # 先让 H/W 至少能容纳一个 patch
        if H < patch_size:
            pad_h = patch_size - H
        if W < patch_size:
            pad_w = patch_size - W
        x_pad = F.pad(x, (0, pad_w, 0, pad_h), mode="reflect")
        _, _, H_pad, W_pad = x_pad.shape

        # ---------- 滑窗收集坐标 ----------
        ys = list(range(0, H_pad - patch_size + 1, stride))
        xs = list(range(0, W_pad - patch_size + 1, stride))
        # 确保末尾 patch 覆盖到边缘
        if not ys or ys[-1] + patch_size < H_pad:
            ys.append(H_pad - patch_size)
        if not xs or xs[-1] + patch_size < W_pad:
            xs.append(W_pad - patch_size)

        # ---------- 推理并累加 ----------
        acc = torch.zeros(B, 1, H_pad, W_pad, device=device, dtype=x.dtype)
        cnt = torch.zeros(B, 1, H_pad, W_pad, device=device, dtype=x.dtype)

        with torch.no_grad():
            for y in ys:
                for xi in xs:
                    patch = x_pad[:, :, y : y + patch_size, xi : xi + patch_size]
                    logit = model(patch)  # (B,1,patch_size,patch_size)
                    acc[:, :, y : y + patch_size, xi : xi + patch_size] += logit
                    cnt[:, :, y : y + patch_size, xi : xi + patch_size] += 1.0

        # ---------- 均值 + 裁回原始尺寸 ----------
        out_pad = acc / cnt.clamp(min=1e-6)
        out = out_pad[:, :, :H, :W]

        assert out.shape == (B, 1, H, W), (
            f"FRUNetAdapter.forward_adapt: shape mismatch, got {out.shape}, expected {(B,1,H,W)}"
        )
        return out
