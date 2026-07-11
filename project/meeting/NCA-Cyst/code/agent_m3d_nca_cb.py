"""前景优先 patch 采样 agent —— NCA-Cyst Phase2 kill-shot 组件①。

服务 NCA-Cyst § Phase2 立项证伪，lever = 给 vanilla M3D-NCA 加「类平衡」开关，
做关键格 b(−全局视野, +类平衡)。

机理（THEORY_LEDGER 铁证）：细级 patch 随机采样抽不到 0.0065% 的囊肿体素 → 训练
patch 的 GT 全 0 → `Agent_Multi_NCA.batch_step` 的 `if 1 in targets` 不成立 → 不算 loss、
梯度≈0。本组件改**patch 落点**：含囊肿 case 的训练 patch 保证覆盖 ≥1 前景体素。

⚠️ 复现红线：本文件**不改官方** src/agents/Agent_M3D_NCA.py（只读），用**子类**覆盖。
   - `class_balance != 'on'`（含 off）或 `full_img=True`（推理全图分支不做 patch 采样）：
     **全部委托 `super().get_outputs`**，即逐行走官方原路径、RNG 消耗顺序完全一致 → 格 a/baseline
     零偏离、可 diff 验。
   - `class_balance == 'on'` 且训练分支：复制官方 get_outputs 的「setup + 训练(else)分支」，
     **唯一改动 = patch 起点选择那一段**（官方 L204-209 的 `while True: ... break`）换成
     前景优先拒绝采样 `_choose_patch_pos`。其余（下采样/model 调用/upscale/concat/切片）逐字节照抄。

   为什么只覆盖训练分支：官方 `full_img=True`（test/推理）走的是全图推理分支，本就不做随机
   patch 采样，与类平衡无关 → 直接委托 super，避免复制上百行可视化代码、也保证评估口径不变。
"""
import os
import sys
import math
import random
from pathlib import Path

import numpy as np
import torch

# 官方 M3D-NCA repo 根加进 sys.path（与 train_kits23 / kits23_dataset 同法）。
_OFFICIAL_ROOT = Path(os.environ.get(
    "M3DNCA_OFFICIAL_ROOT",
    str(Path(__file__).resolve().parents[2] / "Med-NCA" / "M3D-NCA-official")))
if str(_OFFICIAL_ROOT) not in sys.path:
    sys.path.insert(0, str(_OFFICIAL_ROOT))

from src.agents.Agent_M3D_NCA import Agent_M3D_NCA  # noqa: E402


class Agent_M3D_NCA_CB(Agent_M3D_NCA):
    r"""M3D-NCA agent + 前景优先 patch 采样（类平衡组件①）。

    行为由 config 的 `class_balance` 键控制（train 脚本从 --class_balance 写入）：
      - 'on'  → 训练 patch 采样走前景优先拒绝采样。
      - 其它/None → 完全等价官方 Agent_M3D_NCA（委托 super）。
    retry 上限由 config 的 `cb_max_retries` 控制（默认 20）。
    """

    # 烟测自检：copy-paste 占比只在首个 patch 打印一次（避免刷屏）。
    _cb_selfcheck_done = False

    def _choose_patch_pos(self, targets_loc_temp, b, size, max_x, max_y, max_z):
        r"""为 batch 元素 b 选 patch 起点 (pos_x, pos_y, pos_z)。【CB-max 组件① 囊肿中心采样】

        升级动机（skeptic 判「弱 CB(≥1 体素)→b 假阴性」）：仅命中 ≥1 前景体素时囊肿多半只有
        一角落进 patch，占比仍极低。改为**以随机选中的一个囊肿体素为 patch 中心**取 patch，
        让整颗囊肿尽量落进 patch。

        逻辑：该 case 本层 GT 含前景(囊肿) → 随机选一个前景体素坐标 c，patch 中心=c，
        起点 = c - size//2，越界 clamp 到 [0, max]（**不缩 patch 尺寸**——尺寸仍 config 锁定，
        保「只翻 CB 开关、其余与格 a 全同」的控制变量原则）；该 case 无前景 → 随机。

        .. note:: 当前 config 下粗级 patch = 下采样全图（max_x/y/z 常为 0），中心采样退化为整图
            （pos 恒 0，囊肿本就全在图内）；组件② copy-paste 才是抬占比主力。max>0（有裁剪空间）
            的 config 下中心采样生效。

        RNG 说明：本方法只在 class_balance='on'（关键格 b，独立实验条件）下调用，不要求与官方
        RNG 流一致；off/baseline 从不进这里（委托 super），故零偏离得以保证。

        #Args:
            targets_loc_temp: 本层 GT 张量 (batch, X, Y, Z[, C])。
            b: batch 内元素下标。
            size: patch 尺寸 (sx, sy, sz)。
            max_x/max_y/max_z: 各维起点上界（含），= 官方 `shape - size` 值。
        """
        # 拷到 CPU 一次（前景坐标枚举），避免反复 GPU 同步
        tgt_b = targets_loc_temp[b].detach().to('cpu')
        fg = (tgt_b > 0).nonzero(as_tuple=False)   # (N, ndim) 前景体素坐标
        if fg.shape[0] == 0:
            # 无囊肿可采 → 随机（x,y,z 顺序沿用官方）
            return (random.randint(0, max_x),
                    random.randint(0, max_y),
                    random.randint(0, max_z))

        # 随机选一个囊肿体素作 patch 中心
        c = fg[random.randint(0, fg.shape[0] - 1)]
        cx, cy, cz = int(c[0]), int(c[1]), int(c[2])   # 前 3 维为 spatial

        def _clamp(center, half, hi):
            p = center - half
            if p < 0:
                p = 0
            elif p > hi:
                p = hi
            return p

        pos_x = _clamp(cx, size[0] // 2, max_x)
        pos_y = _clamp(cy, size[1] // 2, max_y)
        pos_z = _clamp(cz, size[2] // 2, max_z)
        return pos_x, pos_y, pos_z

    def _copy_paste_augment(self, inputs_loc, targets_loc, b, size):
        r"""patch 内囊肿 copy-paste 增广，把前景占比顶进目标区间。【CB-max 组件②】

        受控偏离（合成密度增广，v1 硬粘贴）：在已取好的训练 patch 内，把囊肿体素**连同其 CT
        image 强度(通道 0:input_channels) + label 一起**硬复制到 patch 内其他「非空气组织」落点若干份，
        把 patch 内前景占比人为顶到 cb_copy_paste_target_frac（默认 0.02=2%，文献有效区间 1-5%）。
        只搬 image 通道 + label（hidden 状态通道保留落点原值）；粘贴份数 = ceil(target_frac·patch体素
        / 当前前景体素)，硬上限 cb_copy_paste_cap（默认 8）防爆。

        TODO(researcher 待查)：v1 为**硬粘贴不做 blend**，边界可能突兀；若 reviewer 质疑，可升级为
            Poisson/高斯 blend，参考 medical lesion copy-paste 标准实现（如 CarveMix / SelfMix / TumorCP）。

        只在 class_balance='on' 生效；off 路径完全不进本方法。就地修改 inputs_loc[b] / targets_loc[b]。

        #Returns: (n_paste, frac_before, frac_after) 供烟测自检打印占比。
        """
        ic = self.exp.get_from_config('input_channels')
        target_frac = self.exp.get_from_config('cb_copy_paste_target_frac')
        if target_frac is None:
            target_frac = 0.02
        cap = self.exp.get_from_config('cb_copy_paste_cap')
        if cap is None:
            cap = 8

        img = inputs_loc[b]        # view: (sx, sy, sz, Ct) —— 前 ic 通道为 CT image
        lbl = targets_loc[b]       # view: (sx, sy, sz, Cl)
        patch_vox = int(size[0]) * int(size[1]) * int(size[2])

        # 当前 patch 前景体素坐标（用 label 通道 0）
        fg = (lbl[..., 0] > 0).nonzero(as_tuple=False)   # (N, 3)
        n_fg = int(fg.shape[0])
        frac_before = n_fg / patch_vox
        if n_fg == 0:
            return 0, frac_before, frac_before   # 无前景可搬（中心采样越界等极端情形）

        # 已达目标 → 不搬
        if frac_before >= target_frac:
            return 0, frac_before, frac_before

        # 粘贴份数 = ceil(target_frac·patch体素 / 当前前景体素)，硬上限 cap
        n_paste = int(math.ceil(target_frac * patch_vox / max(n_fg, 1)))
        n_paste = max(0, min(n_paste, int(cap)))
        if n_paste == 0:
            return 0, frac_before, frac_before

        # 源囊肿块：前景体素相对质心的偏移 + 其 image 强度
        center = fg.float().mean(dim=0).round().long()          # (3,)
        rel = fg - center                                        # (N, 3) 相对偏移
        src_img = img[fg[:, 0], fg[:, 1], fg[:, 2], 0:ic]        # (N, ic) 源 CT 强度

        # 合法落点集合 = patch 内「非空气组织」区（image 通道0 强度 > patch 均值），避免贴纯背景空气
        img0 = img[..., 0]
        thr = img0.mean()
        cand = (img0 > thr).nonzero(as_tuple=False)              # (M, 3)
        if cand.shape[0] == 0:
            cand = None   # 退化：无组织落点则用 patch 中心区随机

        sx, sy, sz = int(size[0]), int(size[1]), int(size[2])
        for _ in range(n_paste):
            if cand is not None:
                dst_c = cand[random.randint(0, cand.shape[0] - 1)]
            else:
                dst_c = torch.tensor([random.randint(0, sx - 1),
                                      random.randint(0, sy - 1),
                                      random.randint(0, sz - 1)],
                                     device=rel.device, dtype=rel.dtype)
            dst = dst_c + rel                                    # (N, 3) 目标坐标
            dst[:, 0].clamp_(0, sx - 1)
            dst[:, 1].clamp_(0, sy - 1)
            dst[:, 2].clamp_(0, sz - 1)
            # 硬粘贴：image 通道搬源强度，label 置 1（hidden 通道保留落点原值）
            img[dst[:, 0], dst[:, 1], dst[:, 2], 0:ic] = src_img
            lbl[dst[:, 0], dst[:, 1], dst[:, 2], :] = 1.0

        n_fg_after = int((lbl[..., 0] > 0).sum())
        frac_after = n_fg_after / patch_vox
        return n_paste, frac_before, frac_after

    def get_outputs(self, data, full_img=False, tag="", **kwargs):
        r"""见文件头。CB-on 训练分支自定义采样，其余委托官方 super。"""
        cb = self.exp.get_from_config('class_balance')
        if full_img or cb != 'on':
            # off / 推理全图 → 逐行官方（RNG 消耗顺序一致，零偏离，可 diff 验）
            return super().get_outputs(data, full_img=full_img, tag=tag, **kwargs)

        # ============================================================================
        #  以下为 class_balance='on' 的训练分支：
        #  复制官方 Agent_M3D_NCA.get_outputs 的「setup + 训练(else)分支」，
        #  **唯一改动**在下方标注 [CB-HOOK] 处（patch 起点选择）。其余逐字节照抄官方。
        # ============================================================================
        id, inputs, targets = data

        if len(targets.shape) < 5:
            targets = torch.unsqueeze(targets, 4)

        # Set scaling factor
        scale_fac = 2
        if self.exp.get_from_config('scale_factor') is not None:
            scale_fac = self.exp.get_from_config('scale_factor')

        # Choose Pooling
        max_pool = torch.nn.MaxPool3d(2, 2, 0)

        targets_loc = targets

        # Scale Image to Initial Size
        full_res = inputs
        full_res_gt = targets
        inputs_loc = inputs

        # Scale image down square(scale_factor) -> Replace with single downscaling step
        for i in range(self.exp.get_from_config('train_model') * int(math.log2(scale_fac))):
            inputs_loc = inputs_loc.transpose(1, 4)
            inputs_loc = max_pool(inputs_loc)
            inputs_loc = inputs_loc.transpose(1, 4)
            targets_loc = targets_loc.transpose(1, 4)
            targets_loc = max_pool(targets_loc)
            targets_loc = targets_loc.transpose(1, 4)

        input_channel = self.exp.get_from_config('input_channels')

        # During training run inference on patches
        # For number of downscaling levels
        for m in range(self.exp.get_from_config('train_model') + 1):
            # If last step -> run normal inference on final patch
            if m == self.exp.get_from_config('train_model'):
                if type(self.getInferenceSteps()) is list:
                    stp = self.getInferenceSteps()[m]
                else:
                    stp = self.getInferenceSteps()
                outputs = self.model[m](inputs_loc, steps=stp, fire_rate=self.exp.get_from_config('cell_fire_rate'))
            else:
                # Create higher res image for next level -> Replace with single downscaling step
                next_res = full_res
                for i in range(self.exp.get_from_config('train_model') - (m + 1)):
                    next_res = next_res.transpose(1, 4)
                    next_res = max_pool(next_res)
                    next_res = next_res.transpose(1, 4)
                # Create higher res groundtruth for next level -> Replace with single downscaling step
                next_res_gt = full_res_gt
                for i in range(self.exp.get_from_config('train_model') - (m + 1)):
                    next_res_gt = next_res_gt.transpose(1, 4)
                    next_res_gt = max_pool(next_res_gt)
                    next_res_gt = next_res_gt.transpose(1, 4)

                # Run model inference on patch
                outputs = self.model[m](inputs_loc, steps=self.getInferenceSteps()[m], fire_rate=self.exp.get_from_config('cell_fire_rate'))

                # Upscale lowres features to next level
                up = torch.nn.Upsample(scale_factor=scale_fac, mode='nearest')
                outputs = torch.permute(outputs, (0, 4, 1, 2, 3))
                outputs = up(outputs)
                outputs = torch.permute(outputs, (0, 2, 3, 4, 1))
                # Concat lowres features with higher res image
                inputs_loc = torch.concat((next_res[..., :input_channel], outputs[..., input_channel:]), 4)

                # Array to store intermediate states
                targets_loc = next_res_gt
                size = self.exp.get_from_config('input_size')[0]
                inputs_loc_temp = inputs_loc
                targets_loc_temp = targets_loc

                # Array to store next states
                inputs_loc = torch.zeros((inputs_loc_temp.shape[0], size[0], size[1], size[2], inputs_loc_temp.shape[4])).to(self.exp.get_from_config('device'))
                targets_loc = torch.zeros((targets_loc_temp.shape[0], size[0], size[1], size[2], targets_loc_temp.shape[4])).to(self.exp.get_from_config('device'))
                full_res_new = torch.zeros((full_res.shape[0], int(full_res.shape[1] / scale_fac), int(full_res.shape[2] / scale_fac), int(full_res.shape[3] / scale_fac), full_res.shape[4])).to(self.exp.get_from_config('device'))
                full_res_gt_new = torch.zeros((full_res.shape[0], int(full_res.shape[1] / scale_fac), int(full_res.shape[2] / scale_fac), int(full_res.shape[3] / scale_fac), full_res_gt.shape[4])).to(self.exp.get_from_config('device'))

                # Scaling factors
                factor = self.exp.get_from_config('train_model') - m - 1
                factor_pow = math.pow(2, factor)

                # Choose random patch of image for each element in batch
                for b in range(inputs_loc.shape[0]):
                    # [CB-HOOK] 唯一改动：官方 `while True: pos_*=random.randint(...); break`（纯随机）
                    #           换成前景优先拒绝采样。受控变量，机理见文件头。
                    pos_x, pos_y, pos_z = self._choose_patch_pos(
                        targets_loc_temp, b, size,
                        inputs_loc_temp.shape[1] - size[0],
                        inputs_loc_temp.shape[2] - size[1],
                        inputs_loc_temp.shape[3] - size[2])

                    # Randomized start position for patch
                    pos_x_full = int(pos_x * factor_pow)
                    pos_y_full = int(pos_y * factor_pow)
                    pos_z_full = int(pos_z * factor_pow)
                    size_full = [int(full_res.shape[1] / scale_fac), int(full_res.shape[2] / scale_fac), int(full_res.shape[3] / scale_fac)]

                    # Set current patch of inputs and targets
                    inputs_loc[b] = inputs_loc_temp[b, pos_x:pos_x + size[0], pos_y:pos_y + size[1], pos_z:pos_z + size[2], :]
                    if len(targets_loc.shape) > 4:
                        targets_loc[b] = targets_loc_temp[b, pos_x:pos_x + size[0], pos_y:pos_y + size[1], pos_z:pos_z + size[2], :]
                    else:
                        targets_loc[b] = targets_loc_temp[b, pos_x:pos_x + size[0], pos_y:pos_y + size[1], pos_z:pos_z + size[2]]

                    # Update full res image to patch of full res image
                    full_res_new[b] = full_res[b, pos_x_full:pos_x_full + size_full[0], pos_y_full:pos_y_full + size_full[1], pos_z_full:pos_z_full + size_full[2], :]
                    full_res_gt_new[b] = full_res_gt[b, pos_x_full:pos_x_full + size_full[0], pos_y_full:pos_y_full + size_full[1], pos_z_full:pos_z_full + size_full[2], :]

                    # [CB-max 组件②] patch 内囊肿 copy-paste 增广（就地改 inputs_loc[b]/targets_loc[b]）。
                    #   v1 只增广进入 loss 的细级 patch（train_model=1 时 final 级直接用 inputs_loc）；
                    #   多级 full_res_new 传播的一致性增广留 TODO（当前 config train_model=1 不影响 loss）。
                    n_paste, frac_b, frac_a = self._copy_paste_augment(inputs_loc, targets_loc, b, size)
                    if not self._cb_selfcheck_done:
                        print(f"[CB-max] copy-paste 自检 b={b}: 粘贴{n_paste}份, 前景占比 "
                              f"{frac_b:.4%} -> {frac_a:.4%} (目标 "
                              f"{self.exp.get_from_config('cb_copy_paste_target_frac')})")
                        self._cb_selfcheck_done = True

                full_res = full_res_new
                full_res_gt = full_res_gt_new

        # Add pooling - not functional
        if self.exp.get_from_config('Persistence'):
            if np.random.random() < self.exp.get_from_config('pool_chance'):
                self.epoch_pool.addToPool(outputs.detach().cpu(), id)

        return outputs[..., self.input_channels:self.input_channels + self.output_channels], targets_loc
