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

def _parse_channels(val: Any, default: int = 3) -> int:
    """
    容错解析 channels 配置值。

    csnet.yaml 的 preprocess 段历史上用了 channels: "rgb" 字符串；
    model 段用 int。两处均需解析。

    映射规则（官方 in_channels 已核：iMED-Lab/CS-Net dataloader/drive.py,
              Image.open → ToTensor → (3,H,W) RGB，确认 2026-06-25）：
      3 / 'rgb' / 'RGB'                → 3
      1 / 'green' / 'gray' / 'grey'   → 1
      其他 int 字符串                  → int(val)
    """
    if isinstance(val, int):
        return val
    if isinstance(val, str):
        low = val.strip().lower()
        if low in ('rgb',):
            return 3
        if low in ('green', 'gray', 'grey', 'grayscale'):
            return 1
        try:
            return int(low)
        except ValueError:
            pass
    # fallback
    return default


@register
class CSNetAdapter(BaselineAdapter):
    """
    CS-Net / CS2-Net baseline adapter.

    官方 repo : https://github.com/iMED-Lab/CS-Net (MIT)
    超参来源  : BASELINE_SPEC §1; researcher 二轮核实。
    特殊点    : RGB 全图 512×512 输入（3 通道）；官方 forward 含 sigmoid 输出概率。

    通道来源确认（2026-06-25）：
      iMED-Lab/CS-Net dataloader/drive.py 用 PIL.Image.open（无 .convert()）→
      transforms.ToTensor() → shape (3, H, W) RGB，/255，无 CLAHE，无 mean/std。
      故 in_channels=3，color_mode='rgb'。
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

        channels 字段容错：'rgb'→3 / 'green'/'gray'→1 / int 直接用。
        历史上 preprocess.channels 曾写 "rgb" 字符串，_parse_channels 负责兼容。
        """
        return CSNet(
            classes=int(cfg.get("classes", 1)),
            channels=_parse_channels(cfg.get("channels", 3), default=3),
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
        全图推理适配器（含官方推理尺寸对齐）。

        官方 CS-Net test 协议（BASELINE_SPEC §1 + preprocess_cfg test_only.resize=512）：
          整图 resize 到 512×512 推理，再 resize 回原尺寸。
          来源：iMED-Lab/CS-Net dataloader/drive.py test_transform = Resize(512)+ToTensor()。

        evaluate.py 接口约定：
          - preprocess_benchmark_image 返回 pad_to_32 整图（H'×W'），orig_H/W = native。
          - forward_adapt 返回 (B,1,H',W') logits，evaluate.py 再做 [:orig_H,:orig_W] 裁回。

        所以此处做：
          (B,3,H',W') → resize 到 512×512 → CSNet → resize 回 (B,1,H',W')

        训练时是 random_crop(512)，模型永远只见 512×512 patch。
        eval 喂整图不 resize 会造成 ~30 点 Dice 下降（已实测复现）。

        Args:
            model : CSNet 实例，eval 模式，已 .to(device)。
            x     : (B, 3, H', W') RGB 输入，pad_to_32 尺寸，已在 device 上。
            device: 推理设备。

        Returns:
            (B, 1, H', W') logits（与输入同尺寸，prob → logit，evaluate.py [:orig_H,:orig_W] 裁回）。
        """
        assert x.shape[1] == 3, (
            f"CSNetAdapter: 期望 3 通道 RGB 输入 (B,3,H,W), 实际 C={x.shape[1]}"
        )

        _INFER_SIZE = 512  # 官方 test resize 目标（BASELINE_SPEC §1）

        _, _, H_inp, W_inp = x.shape

        # ---- step 1: resize 到 512×512（官方 test_transform Resize(512)）----
        if H_inp != _INFER_SIZE or W_inp != _INFER_SIZE:
            x_512 = F.interpolate(
                x,
                size=(_INFER_SIZE, _INFER_SIZE),
                mode='bilinear',
                align_corners=False,
            )
        else:
            x_512 = x

        # ---- step 2: CSNet forward（512×512）----
        model.eval()
        with torch.no_grad():
            prob_512 = model(x_512)  # (B, 1, 512, 512), values in [0,1]

        # ---- step 3: 概率 → logits（防 log(0) 溢出）----
        prob_clamp = prob_512.clamp(1e-6, 1.0 - 1e-6)
        logits_512 = torch.log(prob_clamp / (1.0 - prob_clamp))

        # ---- step 4: resize logits 回 (H_inp, W_inp)（配合 evaluate.py [:orig_H,:orig_W] 裁回）----
        if H_inp != _INFER_SIZE or W_inp != _INFER_SIZE:
            logits = F.interpolate(
                logits_512,
                size=(H_inp, W_inp),
                mode='bilinear',
                align_corners=False,
            )
        else:
            logits = logits_512

        assert logits.shape[1] == 1 and logits.ndim == 4, (
            f"CSNetAdapter.forward_adapt: expected (B,1,H,W), got {logits.shape}"
        )
        return logits

    def preprocess_benchmark_image(
        self,
        npz_image: "np.ndarray",
        image_id: str,
        dataset_name: str,
        data_root: Optional[str] = None,
    ) -> "Tuple[np.ndarray, Tuple[int, int]]":
        """
        CS-Net benchmark 预处理 override。

        官方 CS-Net 使用 RGB 3ch 输入（/255，无 CLAHE，无 mean/std）。
        benchmark NPZ 里存的是 green+CLAHE+norm 的 (H,W) float32，不能直接用。
        此处从原始图像磁盘重载，走官方 CS-Net 预处理管道（RGB /255）。

        与训练/官方推理管道对齐：
          train_harness → DRIVEDataset/CHASEDataset(color_mode='rgb')
          → _load_image → cv2.cvtColor BGR→RGB → /255 → (H,W,3) float32
          → random_crop(512) → (512,512,3)  [模型永远只见 512×512 patch]
          官方 test: resize 到 512×512（dataloader/drive.py test_transform = Resize(512)+ToTensor()）
          benchmark eval: 此函数返回 BGR→RGB → /255 → pad_to_mult(32) 的整图（H'×W'）；
          forward_adapt 内部负责 resize-to-512 推理 + resize-back-to-(H'×W')，
          再由 evaluate.py 做 [:orig_H,:orig_W] 裁回 native 尺寸算指标。
          ⚠️ 旧注释「无需 resize，CS-Net 全卷积」已更正：模型训练全为 512×512 patch，
           整图不 resize 直接推理会导致 Dice 下降 ~30 点（2026-06-26 实测）。

        路径约定（与各 dataset 的 _img_path 一致，保证不漂移）：
          DRIVE:      training/images/{id:02d}_training.tif
                      image_id 为整数字符串（如 '37'）→ int 后格式化两位
          CHASE:      images/{image_id}_test.tif
                      image_id 已含前缀（如 'test_01' / 'training_17'）
          STARE:      images/{image_id}.ppm（或 .ppm.gz）
          FIVES/HRF:  通用：data_root/images/ 下 glob 含 image_id 的文件
          其他:       同 FIVES/HRF 通用逻辑

        data_root 为 None 或路径不存在时：直接 raise RuntimeError（不静默 fallback
        到绿通道堆叠——那会让 dice 崩掉但无任何错误提示，难以排查）。
        主线跑 benchmark eval 时必须传真实 --data_root（对应数据集根目录）。

        输出 shape: (H', W', 3) float32，evaluate.py 检测 ndim==3 后走
          .permute(2,0,1).unsqueeze(0) → (1,3,H',W')

        Args:
            npz_image:    (H, W) float32 from NPZ (green+CLAHE+norm).  本函数不用此值，
                          仅保留参数签名与基类一致（万一未来 raise 改为 warn+fallback 时用）。
            image_id:     str image identifier stored in NPZ manifest (e.g. '37', 'test_01').
            dataset_name: lowercase dataset name stored in NPZ (e.g. 'drive', 'chase').
            data_root:    原图数据集根目录（必须传真实路径，否则 raise）。

        Returns:
            (proc_image, (orig_H, orig_W)):
              proc_image — (H', W', 3) float32 RGB /255, padded to 32-multiple.
              (orig_H, orig_W) — original un-padded size.

        Raises:
            RuntimeError: data_root 为 None 或图像文件找不到。
        """
        import cv2 as _cv2
        import numpy as _np
        import pathlib as _pl

        PAD_MULT = 32

        def _pad_to_mult(arr: _np.ndarray, mult: int) -> _np.ndarray:
            h, w = arr.shape[:2]
            ph = (mult - h % mult) % mult
            pw = (mult - w % mult) % mult
            if arr.ndim == 3:
                return _np.pad(arr, ((0, ph), (0, pw), (0, 0)), mode='constant')
            return _np.pad(arr, ((0, ph), (0, pw)), mode='constant')

        # ---- data_root 必须有效 ----
        if data_root is None:
            raise RuntimeError(
                f"CSNetAdapter.preprocess_benchmark_image: data_root=None。\n"
                f"CS-Net 需要原始 RGB 图像（/255），NPZ 只存 green+CLAHE+norm 单通道，\n"
                f"无法直接用于 CS-Net（会导致 dice 崩至 ~0.1-0.5）。\n"
                f"请在 evaluate.py 命令行传入 --data_root <真实数据集目录>，\n"
                f"对应 image_id={image_id!r} dataset={dataset_name!r}。"
            )

        root = _pl.Path(data_root)
        ds = dataset_name.lower().strip()

        # ---- 按数据集构建候选路径（与各 dataset._img_path 保持一致）----
        candidates = []
        if ds == 'drive':
            # DRIVEDataset._img_path: training/images/{sid:02d}_training.tif
            # image_id 从 NPZ = str(int_id)，如 '37'
            try:
                sid_int = int(image_id)
                sid_str = f'{sid_int:02d}'
            except ValueError:
                sid_str = str(image_id)
            candidates = [
                root / 'training' / 'images' / f'{sid_str}_training.tif',
            ]
        elif ds in ('chase', 'chase_db1'):
            # CHASEDataset._img_path: images/{image_id}_test.tif
            # image_id 已是完整前缀，如 'test_01' / 'training_17'
            candidates = [
                root / 'images' / f'{image_id}_test.tif',
            ]
        elif ds == 'stare':
            # STAREDataset: images/{image_id}.ppm  (or .ppm.gz)
            candidates = [
                root / 'images' / f'{image_id}.ppm',
                root / 'images' / f'{image_id}.ppm.gz',
            ]
        else:
            # 通用：在 data_root/images/ 下 glob 含 image_id 的文件
            img_dir = root / 'images'
            if img_dir.exists():
                candidates = [
                    p for p in img_dir.iterdir()
                    if str(image_id) in p.name
                ]

        # ---- 加载原图 BGR → RGB /255 ----
        img_bgr = None
        found_path = None
        for p in candidates:
            # .ppm.gz：STARE 压缩格式，需特殊读取
            if str(p).endswith('.ppm.gz') and p.exists():
                try:
                    from datasets.stare import _load_ppm_gz as _lpg
                    img_bgr = _lpg(p)
                    found_path = p
                    break
                except Exception as _e:
                    raise RuntimeError(
                        f"CSNetAdapter: 无法读取 STARE ppm.gz {p}: {_e}"
                    ) from _e
            if p.exists():
                _tmp = _cv2.imread(str(p))
                if _tmp is not None:
                    img_bgr = _tmp
                    found_path = p
                    break

        if img_bgr is None:
            raise RuntimeError(
                f"CSNetAdapter.preprocess_benchmark_image: 找不到原图。\n"
                f"  dataset={dataset_name!r}  image_id={image_id!r}\n"
                f"  data_root={data_root!r}\n"
                f"  已搜路径: {[str(p) for p in candidates]}\n"
                f"请确认 --data_root 指向正确的数据集根目录，\n"
                f"且图像文件存在于对应子目录中。"
            )

        img_rgb = _cv2.cvtColor(img_bgr, _cv2.COLOR_BGR2RGB)
        orig_H, orig_W = img_rgb.shape[:2]
        img_f = img_rgb.astype(_np.float32) / 255.0   # (H, W, 3) RGB /255
        img_pad = _pad_to_mult(img_f, PAD_MULT)        # (H', W', 3) H'%32==0

        return img_pad, (orig_H, orig_W)
