"""FastBackboneNCA: 与官方 BackboneNCA 数学完全等价，唯一区别是把 fire-rate
随机 mask 直接在 device 上生成，消除官方 Model_BasicNCA.update (line 71-72)
每步一次的 CPU->GPU 同步传输 —— 那是 64 步 x 2 级 x 每 batch 的同步停顿，
导致 GPU 利用率仅 3%。语义/分布不变（仍是 Bernoulli(1-fire_rate) mask），
只把 RNG 流从 CPU 挪到 GPU。不修改官方文件（§2 跑偏 #5 只禁原地改官方）。
"""
import torch
import torch.nn.functional as F
from src.models.Model_BackboneNCA import BackboneNCA


class FastBackboneNCA(BackboneNCA):
    def update(self, x_in, fire_rate):
        x = x_in.transpose(1, 3)
        dx = self.perceive(x)
        dx = dx.transpose(1, 3)
        dx = self.fc0(dx)
        dx = F.relu(dx)
        dx = self.fc1(dx)
        if fire_rate is None:
            fire_rate = self.fire_rate
        # 官方：torch.rand([...]) 在 CPU 生成再 .to(device)  ->  此处直接 device 生成
        stochastic = (torch.rand(dx.size(0), dx.size(1), dx.size(2), 1,
                                 device=dx.device) > fire_rate).float()
        dx = dx * stochastic
        x = x + dx.transpose(1, 3)
        x = x.transpose(1, 3)
        return x
