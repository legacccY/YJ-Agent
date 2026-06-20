"""
Standard small U-Net baseline for DRIVE retinal vessel segmentation.

Architecture follows the FR-UNet / SA-UNet tradition on DRIVE:
  - Encoder: 4 down-sampling stages with double-conv blocks
  - Bottleneck: double-conv (no memory module)
  - Decoder: 4 up-sampling stages with skip connections

Channel widths:
  - FR-UNet (MedIA 2022) uses [32,64,128,256,512] — widely reproduced.
  - We use [32,64,128,256] + bottleneck 512 (same as FR-UNet default).
  # TODO: verify exact FR-UNet channel config from official repo
  #   https://github.com/lseventeen/FR-UNet (if researcher confirms identical)

Input:  (B, 1, H, W)  — single-channel (green + CLAHE normalised)
Output: (B, 1, H, W)  — logits (no sigmoid; apply sigmoid outside for prob)
"""

from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F


# --------------------------------------------------------------------------- #
#  Building blocks
# --------------------------------------------------------------------------- #

class DoubleConv(nn.Module):
    """(Conv → BN → ReLU) × 2"""
    def __init__(self, in_ch: int, out_ch: int):
        super().__init__()
        self.block = nn.Sequential(
            nn.Conv2d(in_ch, out_ch, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_ch, out_ch, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
        )

    def forward(self, x):
        return self.block(x)


class Down(nn.Module):
    """MaxPool2d(2) → DoubleConv"""
    def __init__(self, in_ch: int, out_ch: int):
        super().__init__()
        self.pool = nn.MaxPool2d(2)
        self.conv = DoubleConv(in_ch, out_ch)

    def forward(self, x):
        return self.conv(self.pool(x))


class Up(nn.Module):
    """Bilinear upsample → concat skip → DoubleConv"""
    def __init__(self, in_ch: int, skip_ch: int, out_ch: int):
        super().__init__()
        self.conv = DoubleConv(in_ch + skip_ch, out_ch)

    def forward(self, x, skip):
        x = F.interpolate(x, size=skip.shape[-2:], mode='bilinear', align_corners=False)
        x = torch.cat([skip, x], dim=1)
        return self.conv(x)


# --------------------------------------------------------------------------- #
#  U-Net
# --------------------------------------------------------------------------- #

class UNet(nn.Module):
    """
    Small U-Net baseline (pure CNN).

    Args:
        in_ch:    input channels (default 1 for green-channel DRIVE)
        out_ch:   output channels (default 1 for binary vessel seg)
        base_ch:  base channel width (default 32; doubled each stage)
                  stages: [base, 2*base, 4*base, 8*base] + bottleneck 16*base
    """

    def __init__(self, in_ch: int = 1, out_ch: int = 1, base_ch: int = 32):
        super().__init__()
        b = base_ch
        # Encoder
        self.enc1 = DoubleConv(in_ch, b)       # (B, b, H, W)
        self.enc2 = Down(b, b * 2)             # (B, 2b, H/2, W/2)
        self.enc3 = Down(b * 2, b * 4)         # (B, 4b, H/4, W/4)
        self.enc4 = Down(b * 4, b * 8)         # (B, 8b, H/8, W/8)
        # Bottleneck
        self.bottleneck = Down(b * 8, b * 16)  # (B, 16b, H/16, W/16)
        # Decoder
        self.dec4 = Up(b * 16, b * 8, b * 8)
        self.dec3 = Up(b * 8, b * 4, b * 4)
        self.dec2 = Up(b * 4, b * 2, b * 2)
        self.dec1 = Up(b * 2, b, b)
        # Head
        self.head = nn.Conv2d(b, out_ch, 1)

    def forward(self, x):
        # Encoder
        e1 = self.enc1(x)
        e2 = self.enc2(e1)
        e3 = self.enc3(e2)
        e4 = self.enc4(e3)
        bot = self.bottleneck(e4)
        # Decoder
        d4 = self.dec4(bot, e4)
        d3 = self.dec3(d4, e3)
        d2 = self.dec2(d3, e2)
        d1 = self.dec1(d2, e1)
        return self.head(d1)
