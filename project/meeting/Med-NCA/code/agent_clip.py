"""ClipAgent_Med_NCA: Agent_Med_NCA + 梯度裁剪。

修 R2 prostate 发散（输出 logits 爆至 -1e9 → sigmoid 全 0 → 预测全背景、
6 个 ckpt 全 Dice 0）。根因 = Med-NCA 把 NCA 展开 64 步 × 2 级 = 128 次串行
更新反传，在 channel_n=32 / 256×256 这套更大配置下梯度爆炸，官方 batch_step
（Agent_Multi_NCA）裸 loss.backward()+step() 没有裁剪兜住。hippocampus 小尺度
（ch16/64×64）容忍了，prostate 没兜住。

只重写 batch_step（基于 Agent_Multi_NCA 版，逐字保留 + 插一行 clip_grad_norm_），
2-stage get_outputs / optimizer list / scheduler 全继承不动。不改官方文件（守 §2 #3）。

裁剪阈值经 self.grad_clip 注入（run 脚本从 env R2_GRAD_CLIP 设），默认 1.0。
"""
import os
import torch
from src.agents.Agent_Med_NCA import Agent_Med_NCA


class ClipAgent_Med_NCA(Agent_Med_NCA):
    def batch_step(self, data, loss_f):
        data = self.prepare_data(data)
        outputs, targets = self.get_outputs(data)
        for m in range(self.exp.get_from_config('train_model') + 1):
            self.optimizer[m].zero_grad()
        loss = 0
        loss_ret = {}
        for m in range(outputs.shape[-1]):
            if 1 in targets[..., m]:
                loss_loc = loss_f(outputs[..., m], targets[..., m])
                loss = loss + loss_loc
                loss_ret[m] = loss_loc.item()

        if loss != 0:
            loss.backward()
            clip = getattr(self, "grad_clip", None)
            if clip is None:
                clip = float(os.environ.get("R2_GRAD_CLIP", "1.0"))
            # 裁剪两级 NCA 全部参数的总梯度范数
            params = [p for mdl in self.model for p in mdl.parameters()]
            torch.nn.utils.clip_grad_norm_(params, clip)
            for m in range(self.exp.get_from_config('train_model') + 1):
                self.optimizer[m].step()
                self.scheduler[m].step()
        return loss_ret
