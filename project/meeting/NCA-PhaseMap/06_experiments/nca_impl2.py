"""独立极简 NCA 实现 — NCA-PhaseMap Gate1 腿①-b (B4)

故意与官方 M3D-NCA 独立实现，用于验证「相变非单实现 artifact」（A4 K3）。

实现差异（vs 官方 BasicNCA.update）：
  官方: stochastic = rand([B,H,W,1]) > fire_rate  （fire_rate 比例的 cell 不更新）
  本实现: mask = rand([B,H,W,1]) < update_rate    （update_rate 比例的 cell 更新）
  数学等价：update_rate = 1 - fire_rate，语义相同但代码路径完全独立。

超参（全对齐官方 r1_hippocampus config，无一偏离）：
    channel_n=16, hidden_size=128, input_channels=1
    3×3 Sobel 感知核（同 BasicNCA.perceive）
    LR=16e-4, betas=(0.5, 0.5), 300 step
    无 grad clip（对齐官方 Agent.py 零 clip_grad_norm_）

不依赖 M3D-NCA 框架（不 import src.*）。

公开 API：
    MinimalNCA(channel_n, device, hidden_size, input_channels)
    .forward(x, steps, update_rate) → x  [B, H, W, channel_n]
"""

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


class MinimalNCA(nn.Module):
    """极简独立 NCA（不依赖 M3D-NCA 框架）。

    update_rate = 1 - fire_rate（与官方 BasicNCA 参数等价，代码实现独立）。
    """

    def __init__(self,
                 channel_n: int = 16,
                 device=None,
                 hidden_size: int = 128,
                 input_channels: int = 1):
        super().__init__()
        self.channel_n      = channel_n
        self.input_channels = input_channels
        self.device         = device or torch.device('cpu')

        # 感知层：channel_n*3（identity + Sobel_x + Sobel_y）→ hidden
        self.fc0 = nn.Linear(channel_n * 3, hidden_size)
        # 输出层：hidden → channel_n；官方 zero_ 初始化
        self.fc1 = nn.Linear(hidden_size, channel_n, bias=False)
        with torch.no_grad():
            self.fc1.weight.zero_()

        self.to(self.device)

    # ── 感知（与 BasicNCA.perceive 逻辑等价） ──────────────────────
    def perceive(self, x: torch.Tensor) -> torch.Tensor:
        """x: [B, channel_n, H, W] → [B, channel_n*3, H, W]"""
        dx_np = np.outer([1, 2, 1], [-1, 0, 1]) / 8.0  # Sobel x
        dy_np = dx_np.T                                  # Sobel y

        def _apply_sobel(x, kernel_np):
            w = torch.from_numpy(kernel_np.astype(np.float32)).to(self.device)
            w = w.view(1, 1, 3, 3).repeat(self.channel_n, 1, 1, 1)
            return F.conv2d(x, w, padding=1, groups=self.channel_n)

        y1 = _apply_sobel(x, dx_np)
        y2 = _apply_sobel(x, dy_np)
        return torch.cat((x, y1, y2), dim=1)  # [B, channel_n*3, H, W]

    # ── 单步更新（核心差异：mask = rand < update_rate） ────────────
    def update(self, x_in: torch.Tensor, update_rate: float) -> torch.Tensor:
        """x_in: [B, H, W, channel_n]，返回同形状更新后状态。

        实现差异 vs 官方：
            官方: stochastic = rand(...) > fire_rate   （1-fire_rate 比例更新）
            本实现: mask = rand(...) < update_rate     （update_rate 比例更新）
            数学等价（update_rate = 1 - fire_rate），代码路径独立。
        """
        x = x_in.transpose(1, 3)  # [B, channel_n, H, W]

        # 感知 + MLP
        dx = self.perceive(x)         # [B, channel_n*3, H, W]
        dx = dx.transpose(1, 3)       # [B, H, W, channel_n*3]
        dx = self.fc0(dx)             # [B, H, W, hidden]
        dx = F.relu(dx)
        dx = self.fc1(dx)             # [B, H, W, channel_n]

        # 稀疏更新掩码（正向写法：rand < update_rate → 1=更新）
        mask = (torch.rand(dx.shape[0], dx.shape[1], dx.shape[2], 1,
                           device=self.device) < update_rate).float()
        dx = dx * mask

        x = x.transpose(1, 3)        # [B, H, W, channel_n]
        x = x + dx
        x = x.transpose(1, 3)        # [B, channel_n, H, W]

        return x.transpose(1, 3)     # [B, H, W, channel_n]

    def forward(self, x: torch.Tensor, steps: int = 16,
                update_rate: float = 0.5) -> torch.Tensor:
        """多步 NCA 推演，保留 input_channels 不变（同官方 BasicNCA.forward）。

        x: [B, H, W, channel_n]
        返回: [B, H, W, channel_n]
        """
        for _ in range(steps):
            x2 = self.update(x, update_rate)
            # 冻结 input channels（同 BasicNCA.forward 末行）
            x = torch.cat([x[..., :self.input_channels],
                           x2[..., self.input_channels:]], dim=-1)
        return x
