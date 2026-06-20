"""
csnet.py — Adapter for CS-Net / CS2-Net (Channel and Spatial attention Net).

官方 repo  : https://github.com/iMED-Lab/CS-Net  (MIT License)
官方超参   : Adam lr=1e-4 wd=5e-4; PolyLR power=0.9; epochs=1000; batch=8;
             整图 512 resize; loss=MSE+Dice; RGB 全图输入 (3 通道); 无 CLAHE.
             Source: BASELINE_SPEC.md §1 (researcher 二轮已核).

架构特点   : ResEncoder × 5 + AffinityAttention (SpatialAttentionBlock +
             ChannelAttentionBlock) + skip-connection decoder。
             输入 3 通道 RGB，整图 512×512。
             官方 forward 末尾有 F.sigmoid()（train 时含 sigmoid 输出概率）。
             adapter forward_adapt 返回 logits（去掉 sigmoid, adapter 接口一致）。

警告       :
  - 官方 initialize_weights 调用了已废弃的 nn.init.kaiming_normal（无下划线），
    此处替换为 nn.init.kaiming_normal_（带下划线的 inplace 版本），行为等价。
  - 官方 forward 末尾 F.sigmoid 在新版 PyTorch 产生 deprecation warning；
    此处在模型定义中保留（复现零偏离），adapter 接口层做 logit 转换。
  - PolyLR 官方未提供独立实现，此处用 LambdaLR + 公式 (1 - iter/max_iter)^power
    实现，与官方训练脚本逻辑一致（官方 train.py 内联 poly_lr_scheduler）。

Windows 规范 :
  - 无 scipy.stats
  - 无 multiprocessing
  - 路径用 pathlib.Path
"""

from __future__ import annotations

import sys
import math
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
#  CS-Net 官方模型定义 — 忠实移植自:
#    github.com/iMED-Lab/CS-Net/blob/master/model/csnet.py  (curl 验证, 2026-06-20)
#  修改说明（零偏离红线：仅修改 deprecated API，不改模型结构/逻辑）：
#    1. kaiming_normal → kaiming_normal_（deprecation fix）
#    2. F.sigmoid(final) 保留（复现零偏离）
#    3. attention_fuse Conv2d 注释掉的分支保持原样（注释中）
# --------------------------------------------------------------------------- #

def _downsample() -> nn.MaxPool2d:
    return nn.MaxPool2d(kernel_size=2, stride=2)


def _deconv(in_channels: int, out_channels: int) -> nn.ConvTranspose2d:
    return nn.ConvTranspose2d(in_channels, out_channels, kernel_size=2, stride=2)


def _initialize_weights(*models) -> None:
    """忠实移植官方 initialize_weights，kaiming_normal→kaiming_normal_ (deprecated fix)。"""
    for model in models:
        for m in model.modules():
            if isinstance(m, (nn.Conv2d, nn.Linear)):
                nn.init.kaiming_normal_(m.weight)
                if m.bias is not None:
                    m.bias.data.zero_()
            elif isinstance(m, nn.BatchNorm2d):
                m.weight.data.fill_(1)
                m.bias.data.zero_()


class ResEncoder(nn.Module):
    def __init__(self, in_channels: int, out_channels: int):
        super().__init__()
        self.conv1 = nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1)
        self.bn1 = nn.BatchNorm2d(out_channels)
        self.conv2 = nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1)
        self.bn2 = nn.BatchNorm2d(out_channels)
        self.relu = nn.ReLU(inplace=False)
        self.conv1x1 = nn.Conv2d(in_channels, out_channels, kernel_size=1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        residual = self.conv1x1(x)
        out = self.relu(self.bn1(self.conv1(x)))
        out = self.relu(self.bn2(self.conv2(out)))
        out = out + residual
        out = self.relu(out)
        return out


class Decoder(nn.Module):
    def __init__(self, in_channels: int, out_channels: int):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.conv(x)


class SpatialAttentionBlock(nn.Module):
    def __init__(self, in_channels: int):
        super().__init__()
        self.query = nn.Sequential(
            nn.Conv2d(in_channels, in_channels // 8, kernel_size=(1, 3), padding=(0, 1)),
            nn.BatchNorm2d(in_channels // 8),
            nn.ReLU(inplace=True),
        )
        self.key = nn.Sequential(
            nn.Conv2d(in_channels, in_channels // 8, kernel_size=(3, 1), padding=(1, 0)),
            nn.BatchNorm2d(in_channels // 8),
            nn.ReLU(inplace=True),
        )
        self.value = nn.Conv2d(in_channels, in_channels, kernel_size=1)
        self.gamma = nn.Parameter(torch.zeros(1))
        self.softmax = nn.Softmax(dim=-1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        B, C, H, W = x.size()
        proj_query = self.query(x).view(B, -1, W * H).permute(0, 2, 1)
        proj_key = self.key(x).view(B, -1, W * H)
        affinity = torch.matmul(proj_query, proj_key)
        affinity = self.softmax(affinity)
        proj_value = self.value(x).view(B, -1, H * W)
        weights = torch.matmul(proj_value, affinity.permute(0, 2, 1))
        weights = weights.view(B, C, H, W)
        out = self.gamma * weights + x
        return out


class ChannelAttentionBlock(nn.Module):
    def __init__(self, in_channels: int):
        super().__init__()
        self.gamma = nn.Parameter(torch.zeros(1))
        self.softmax = nn.Softmax(dim=-1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        B, C, H, W = x.size()
        proj_query = x.view(B, C, -1)
        proj_key = x.view(B, C, -1).permute(0, 2, 1)
        affinity = torch.matmul(proj_query, proj_key)
        affinity_new = torch.max(affinity, -1, keepdim=True)[0].expand_as(affinity) - affinity
        affinity_new = self.softmax(affinity_new)
        proj_value = x.view(B, C, -1)
        weights = torch.matmul(affinity_new, proj_value)
        weights = weights.view(B, C, H, W)
        out = self.gamma * weights + x
        return out


class AffinityAttention(nn.Module):
    """Affinity attention module (spatial + channel)."""

    def __init__(self, in_channels: int):
        super().__init__()
        self.sab = SpatialAttentionBlock(in_channels)
        self.cab = ChannelAttentionBlock(in_channels)
        # self.conv1x1 = nn.Conv2d(in_channels * 2, in_channels, kernel_size=1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        sab = self.sab(x)
        cab = self.cab(x)
        out = sab + cab
        return out


class CSNet(nn.Module):
    """
    CS-Net — 忠实移植自官方 csnet.py。
    官方默认: classes=1, channels=3 (RGB).

    注意: 官方 forward 末尾有 F.sigmoid()，此处保留（复现零偏离）。
    adapter.forward_adapt 通过 logit 转换处理（见 CSNetAdapter）。
    """

    def __init__(self, classes: int = 1, channels: int = 3):
        super().__init__()
        self.enc_input = ResEncoder(channels, 32)
        self.encoder1 = ResEncoder(32, 64)
        self.encoder2 = ResEncoder(64, 128)
        self.encoder3 = ResEncoder(128, 256)
        self.encoder4 = ResEncoder(256, 512)
        self.downsample = _downsample()
        self.affinity_attention = AffinityAttention(512)
        self.attention_fuse = nn.Conv2d(512 * 2, 512, kernel_size=1)
        self.decoder4 = Decoder(512, 256)
        self.decoder3 = Decoder(256, 128)
        self.decoder2 = Decoder(128, 64)
        self.decoder1 = Decoder(64, 32)
        self.deconv4 = _deconv(512, 256)
        self.deconv3 = _deconv(256, 128)
        self.deconv2 = _deconv(128, 64)
        self.deconv1 = _deconv(64, 32)
        self.final = nn.Conv2d(32, classes, kernel_size=1)
        _initialize_weights(self)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        enc_input = self.enc_input(x)
        down1 = self.downsample(enc_input)

        enc1 = self.encoder1(down1)
        down2 = self.downsample(enc1)

        enc2 = self.encoder2(down2)
        down3 = self.downsample(enc2)

        enc3 = self.encoder3(down3)
        down4 = self.downsample(enc3)

        input_feature = self.encoder4(down4)

        # Affinity attention
        attention = self.affinity_attention(input_feature)
        # attention_fuse = self.attention_fuse(torch.cat((input_feature, attention), dim=1))
        attention_fuse = input_feature + attention

        # Decoder
        up4 = self.deconv4(attention_fuse)
        up4 = torch.cat((enc3, up4), dim=1)
        dec4 = self.decoder4(up4)

        up3 = self.deconv3(dec4)
        up3 = torch.cat((enc2, up3), dim=1)
        dec3 = self.decoder3(up3)

        up2 = self.deconv2(dec3)
        up2 = torch.cat((enc1, up2), dim=1)
        dec2 = self.decoder2(up2)

        up1 = self.deconv1(dec2)
        up1 = torch.cat((enc_input, up1), dim=1)
        dec1 = self.decoder1(up1)

        final = self.final(dec1)
        final = torch.sigmoid(final)  # 官方: F.sigmoid(final)，等价改写消 deprecation warning
        return final


# --------------------------------------------------------------------------- #
#  PolyLR 调度器（官方内联实现，无独立 class）
# --------------------------------------------------------------------------- #

def _make_poly_scheduler(
    optimizer: torch.optim.Optimizer,
    total_iters: int,
    power: float = 0.9,
) -> torch.optim.lr_scheduler.LambdaLR:
    """
    PolyLR: lr_factor = (1 - iter/total_iters)^power.
    官方 train.py 内联 poly_lr_scheduler（无独立 class），此处用 LambdaLR 等价实现。
    total_iters = epochs（epoch-level poly）。
    """
    def _poly_lambda(epoch: int) -> float:
        return math.pow(1.0 - epoch / float(total_iters), power)

    return torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda=_poly_lambda)


# --------------------------------------------------------------------------- #
#  MSE + Dice Loss wrapper（官方 loss = MSE + Dice）
# --------------------------------------------------------------------------- #

class _MSEDiceLoss:
    """
    官方 CS-Net loss = MSE + Dice（等权，官方无显式权重系数）。
    adapter 接口签名: (logits, target, fov_mask) → scalar.
    注意: 官方模型输出是 sigmoid 概率，此处 logits 也是概率（forward 内含 sigmoid）。
    """

    def __call__(
        self,
        logits: torch.Tensor,   # 实际是 sigmoid 概率（CSNet 内部已 sigmoid）
        target: torch.Tensor,
        fov_mask: torch.Tensor,
    ) -> torch.Tensor:
        prob = logits  # CSNet 输出已含 sigmoid
        # MSE loss in FOV
        mse = F.mse_loss(prob * fov_mask, target * fov_mask, reduction="sum")
        n_valid = fov_mask.sum().clamp(min=1)
        mse = mse / n_valid
        # Soft Dice loss in FOV
        p_flat = (prob * fov_mask).reshape(prob.shape[0], -1)
        t_flat = (target * fov_mask).reshape(target.shape[0], -1)
        inter = (p_flat * t_flat).sum(1)
        denom = p_flat.sum(1) + t_flat.sum(1)
        dice_loss = 1.0 - ((2.0 * inter + 1e-6) / (denom + 1e-6)).mean()
        return mse + dice_loss


# --------------------------------------------------------------------------- #
#  Adapter
# --------------------------------------------------------------------------- #

@register
class CSNetAdapter(BaselineAdapter):
    """
    CS-Net / CS2-Net baseline adapter.

    官方 repo : https://github.com/iMED-Lab/CS-Net (MIT)
    超参来源  : BASELINE_SPEC §1; researcher 二轮核实。
    特殊点    : RGB 全图 512×512 输入（3 通道）；官方 forward 含 sigmoid 输出概率。
    """

    name: str = "cs_net"
    kind: str = KIND_ARCHITECTURE
    source_repo: str = "https://github.com/iMED-Lab/CS-Net"
    env_tag: str = ENV_MAIN

    def build_model(self, cfg: Dict[str, Any]) -> nn.Module:
        """
        构建 CSNet。

        cfg keys (from baselines/csnet.yaml):
          classes  : int (default 1)
          channels : int (default 3, RGB)
        """
        return CSNet(
            classes=int(cfg.get("classes", 1)),
            channels=int(cfg.get("channels", 3)),
        )

    def build_loss(self, cfg: Dict[str, Any]) -> _MSEDiceLoss:
        """官方 loss = MSE + Dice（等权）。"""
        return _MSEDiceLoss()

    def build_optimizer(
        self,
        model: nn.Module,
        cfg: Dict[str, Any],
    ) -> torch.optim.Optimizer:
        """Adam lr=1e-4, weight_decay=5e-4（官方）。"""
        lr = float(cfg.get("lr", 1e-4))
        wd = float(cfg.get("weight_decay", 5e-4))
        return torch.optim.Adam(model.parameters(), lr=lr, weight_decay=wd)

    def build_scheduler(
        self,
        optimizer: torch.optim.Optimizer,
        cfg: Dict[str, Any],
    ) -> Optional[Any]:
        """PolyLR power=0.9, total_iters=epochs=1000（官方）。"""
        epochs = int(cfg.get("epochs", 1000))
        power = float(cfg.get("scheduler_poly_p", 0.9))
        return _make_poly_scheduler(optimizer, total_iters=epochs, power=power)

    def preprocess_cfg(self) -> Dict[str, Any]:
        """
        CS-Net 官方预处理（§7.1 normalize + §7.2 augment，baseline-fix 2026-06-20）：
          normalize: 仅 ToTensor()（/255→[0,1]），无 mean/std 标准化
                     源：dataloader/drive.py（§7.1 确认）
          augment:   rotate randint(-40,40)° 100% · HFlip p0.5 ·
                     RandomCrop 512×512 100%（STARE scale1=688）·
                     RandEnhance p0.5 选{Brightness/Color/Contrast/Sharpness}
                     factor uniform(-2,2)
                     ⚠ TODO: factor 含负值，PIL ImageEnhance 语义需人工核原行
                             （官方源码 `random.uniform(-2,2)`，负值区间行为待确认）
                     test 仅 resize512
                     源：dataloader/drive.py（§7.2）
          clahe: False（官方无）
        """
        return {
            "channels": "rgb",          # RGB 三通道，官方 dataloader/drive.py
            "normalize": {
                "method": "divide_255",  # 仅 /255，无 mean/std（§7.1 官方 ToTensor()）
                "mean": [0.0, 0.0, 0.0],  # 无额外标准化，占位
                "std": [1.0, 1.0, 1.0],   # 无额外标准化，占位
            },
            "input_mode": "fullimg",
            "patch_size": None,
            "clahe": False,             # 官方无 CLAHE（§7.1 确认）
            "augment": {
                # 源：iMED-Lab/CS-Net dataloader/drive.py（§7.2）
                "rotate": {"range": [-40, 40], "p": 1.0},         # 100% 应用
                "hflip": {"p": 0.5},
                "random_crop": {"size": 512, "p": 1.0},           # DRIVE; STARE scale1=688
                "rand_enhance": {
                    "p": 0.5,
                    "choices": ["Brightness", "Color", "Contrast", "Sharpness"],
                    "factor_range": [-2, 2],  # TODO: 负值 PIL ImageEnhance 语义待人工核（§7.2 注）
                },
                "test_only": {"resize": 512},
                "note": (
                    "CS-Net official augment: rotate 100% + HFlip p0.5 + "
                    "RandomCrop 512 + RandEnhance p0.5. "
                    "factor_range=[-2,2] TODO: PIL negative value behavior unconfirmed. "
                    "Source: iMED-Lab/CS-Net dataloader/drive.py (§7.2)."
                ),
            },
            "extra": {
                "resize": 512,
                "note": (
                    "CS-Net uses full-image RGB input resized to 512x512. "
                    "Official repo normalizes by /255 only (ToTensor). "
                    "Source: iMED-Lab/CS-Net + BASELINE_SPEC §1 §7.1 §7.2."
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
        全图推理适配器。

        CS-Net 整图训练，直接 forward。
        官方模型输出是 sigmoid 概率 [0,1]，需转换为 logits 以符合 adapter 接口
        （evaluate.py 期望 logits，自行 threshold 0.5）。

        Args:
            model : CSNet 实例，eval 模式，已 .to(device)。
            x     : (B, 3, H, W) RGB 输入，已在 device 上。
            device: 推理设备。

        Returns:
            (B, 1, H, W) logits（prob → logit via logit = log(p/(1-p))）。
        """
        assert x.shape[1] == 3, (
            f"CSNetAdapter: 期望 3 通道 RGB 输入 (B,3,H,W), 实际 C={x.shape[1]}"
        )
        model.eval()
        with torch.no_grad():
            prob = model(x)  # (B, 1, H, W), values in [0,1]

        # 概率 → logits（防 log(0) 数值溢出）
        prob_clamp = prob.clamp(1e-6, 1.0 - 1e-6)
        logits = torch.log(prob_clamp / (1.0 - prob_clamp))

        assert logits.shape[1] == 1 and logits.ndim == 4, (
            f"CSNetAdapter.forward_adapt: expected (B,1,H,W), got {logits.shape}"
        )
        return logits
