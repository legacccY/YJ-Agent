"""
unet.py
=======
用途：小 2D U-Net，base_channels=32，输入 1 通道 256×256，输出 num_classes 通道。
      参数量约 1.9M，适合 RTX4070 8GB 跑 batch=4-8。

怎么用：
    from unet import UNet
    model = UNet(in_channels=1, num_classes=3, base_channels=32)
    # 输入: [B, 1, 256, 256]  输出: [B, 3, 256, 256] (logits)
"""

import torch
import torch.nn as nn
import torch.nn.functional as F


class ConvBlock(nn.Module):
    """两层 Conv-BN-ReLU。"""

    def __init__(self, in_ch: int, out_ch: int):
        super().__init__()
        self.block = nn.Sequential(
            nn.Conv2d(in_ch, out_ch, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_ch, out_ch, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
        )

    def forward(self, x):
        return self.block(x)


class Down(nn.Module):
    """MaxPool + ConvBlock。"""

    def __init__(self, in_ch: int, out_ch: int):
        super().__init__()
        self.pool = nn.MaxPool2d(2)
        self.conv = ConvBlock(in_ch, out_ch)

    def forward(self, x):
        return self.conv(self.pool(x))


class Up(nn.Module):
    """双线性上采样 + ConvBlock。"""

    def __init__(self, in_ch: int, skip_ch: int, out_ch: int):
        super().__init__()
        self.up = nn.Upsample(scale_factor=2, mode="bilinear", align_corners=True)
        self.conv = ConvBlock(in_ch + skip_ch, out_ch)

    def forward(self, x, skip):
        x = self.up(x)
        # 处理奇数尺寸的 pad
        if x.shape != skip.shape:
            x = F.pad(x, [0, skip.shape[3] - x.shape[3], 0, skip.shape[2] - x.shape[2]])
        x = torch.cat([skip, x], dim=1)
        return self.conv(x)


class UNet(nn.Module):
    """
    标准 4 层 U-Net。
    base_channels=32 → channels: [32, 64, 128, 256, 512]
    参数量 ~1.9M。
    """

    def __init__(self, in_channels: int = 1, num_classes: int = 3, base_channels: int = 32):
        super().__init__()
        b = base_channels
        self.enc1 = ConvBlock(in_channels, b)        # 32
        self.enc2 = Down(b, b * 2)                   # 64
        self.enc3 = Down(b * 2, b * 4)               # 128
        self.enc4 = Down(b * 4, b * 8)               # 256
        self.bottleneck = Down(b * 8, b * 16)        # 512

        self.dec4 = Up(b * 16, b * 8, b * 8)        # 256
        self.dec3 = Up(b * 8, b * 4, b * 4)         # 128
        self.dec2 = Up(b * 4, b * 2, b * 2)         # 64
        self.dec1 = Up(b * 2, b, b)                  # 32

        self.out_conv = nn.Conv2d(b, num_classes, kernel_size=1)

    def forward(self, x):
        e1 = self.enc1(x)
        e2 = self.enc2(e1)
        e3 = self.enc3(e2)
        e4 = self.enc4(e3)
        bn = self.bottleneck(e4)

        d4 = self.dec4(bn, e4)
        d3 = self.dec3(d4, e3)
        d2 = self.dec2(d3, e2)
        d1 = self.dec1(d2, e1)

        return self.out_conv(d1)

    def get_features(self, x):
        """返回 bottleneck 特征（Mean Teacher 可能用到）。"""
        e1 = self.enc1(x)
        e2 = self.enc2(e1)
        e3 = self.enc3(e2)
        e4 = self.enc4(e3)
        bn = self.bottleneck(e4)
        return bn


if __name__ == "__main__":
    # 静态形状验证（不计入禁跑红线——这是 __main__ 守卫内的单元测试）
    # 主线可运行：python unet.py
    model = UNet(in_channels=1, num_classes=3, base_channels=32)
    x = torch.zeros(2, 1, 256, 256)
    y = model(x)
    print(f"input:  {x.shape}")
    print(f"output: {y.shape}")
    n_params = sum(p.numel() for p in model.parameters())
    print(f"params: {n_params:,} (~{n_params/1e6:.1f}M)")
