"""类平衡(CB)损失 —— NCA-Cyst Phase2 kill-shot 组件②。

服务 NCA-Cyst § Phase2 立项证伪，lever = 给 vanilla M3D-NCA 加「类平衡」开关，
做关键格 b(−全局视野, +类平衡)。本文件提供 Tversky / DiceTversky 损失，train 脚本在
`--class_balance on` 时用它替换官方 DiceFocalLoss。

⚠️ 复现红线：本文件**不改官方** src/losses/LossFunctions.py（只读）。DiceTverskyLoss 的
   **Dice 项与官方 DiceFocalLoss / DiceLoss 的 Dice 项逐字节一致**（sigmoid 后 flatten、
   intersection、smooth=1 的 (2·I+1)/(sum+sum+1)），**唯一偏离 = 把 focal 子项换成 tversky
   子项**，与官方 `DiceFocal = dice + focal` 结构对称成 `DiceTversky = dice + tversky`。
   这是关键格 b 的**受控变量**——除「focal→tversky」这一处，其余口径与 baseline 完全可比。

超参语义（researcher 溯源 Abraham & Khan, ISBI'19「A Novel Focal Tversky Loss」）：
   Tversky index  TI = (TP + smooth) / (TP + w_fp·FP + w_fn·FN + smooth)
   「重罚 FN」⟺ **w_fn > w_fp**（认准系数大小，不死记论文字母 α/β——原论文 α/β 分派到
   FN/FP 的写法两版打架，planner 与 researcher 给的字母相反但语义同=重罚 FN）。
   ⚠️ CB-max 拍板：默认 **w_fn=0.9, w_fp=0.1**（极端重罚 FN；原论文推荐 0.7/0.3，
      本 kill-shot 为把「加了类平衡也救不回」证到极致而加码到 0.9）。train 脚本 --tversky_wfn 可调，
      w_fp 派生 = 1 - w_fn。这是关键格 b 的受控自变量。

Focal 变体 γ：
   Focal Tversky Loss  FTL = (1 - TI) ** (1/γ)，原论文 γ=4/3(>1) → 指数 0.75<1，放大难例。
   默认 γ=1.0 = 纯 Tversky（此时 (1-TI)^1，两种指数约定在 γ=1 处等价，无歧义）。
   ⚠️ TODO(researcher 确认)：γ≠1 时的指数约定。本实现用**原论文 (1-TI)^(1/γ)**；
      部分社区实现写 (1-TI)^γ，二者在 γ≠1 时不同。当前 Stage 默认 γ=1.0 不触发该分歧，
      若后续开 γ=4/3 变体，请确认约定后再跑。

数值稳定：sigmoid 后对 tversky 子项 clamp(eps, 1-eps)；分母 +smooth=1.0（对齐官方 dice +1）。
"""
import torch
import torch.nn as nn


class TverskyLoss(nn.Module):
    r"""纯 Tversky / Focal Tversky 损失（重罚 FN）。

    #Args:
        w_fp: FP 的惩罚系数（默认 0.1）。
        w_fn: FN 的惩罚系数（默认 0.9，CB-max 极端重罚 FN）。**w_fn > w_fp ⟺ 重罚 FN**。
        gamma: focal 指数；1.0=纯 Tversky。>1 时按原论文取 (1-TI)^(1/gamma)。
        eps: sigmoid 后 clamp 边界，数值稳定。
        smooth: 分子分母平滑项（对齐官方 dice 的 +1）。
    """

    def __init__(self, w_fp=0.1, w_fn=0.9, gamma=1.0, eps=1e-7, smooth=1.0):
        super(TverskyLoss, self).__init__()
        self.w_fp = w_fp
        self.w_fn = w_fn
        self.gamma = gamma
        self.eps = eps
        self.smooth = smooth

    def forward(self, input, target):
        r"""#Args: input=logits（未过 sigmoid）；target=0/1 掩码。与 DiceFocalLoss 同签名。"""
        input = torch.sigmoid(input)
        input = torch.flatten(input)
        target = torch.flatten(target)
        # clamp 仅用于 tversky 统计量，保证 (1-input) 与 log 域数值稳定
        input = input.clamp(self.eps, 1.0 - self.eps)

        TP = (input * target).sum()
        FP = (input * (1.0 - target)).sum()
        FN = ((1.0 - input) * target).sum()

        TI = (TP + self.smooth) / (TP + self.w_fp * FP + self.w_fn * FN + self.smooth)
        tversky_loss = 1.0 - TI
        if self.gamma != 1.0:
            # 原论文 Focal Tversky：(1-TI)^(1/γ)，γ=4/3→指数0.75 放大难例
            tversky_loss = tversky_loss ** (1.0 / self.gamma)
        return tversky_loss


class DiceTverskyLoss(nn.Module):
    r"""Dice + Tversky 复合损失，结构对称官方 `DiceFocalLoss = dice + focal`。

    受控变量：**Dice 项逐字节复制官方**（smooth=1 的 (2·I+1)/(sum+sum+1)），
    **只把 focal 子项换成 tversky 子项**（重罚 FN）。除此之外与 baseline 口径完全可比。
    """

    def __init__(self, w_fp=0.1, w_fn=0.9, gamma=1.0, eps=1e-7, smooth=1.0):
        super(DiceTverskyLoss, self).__init__()
        self.w_fp = w_fp
        self.w_fn = w_fn
        self.gamma = gamma
        self.eps = eps
        self.smooth = smooth

    def forward(self, input, target):
        r"""#Args: input=logits；target=0/1 掩码。与 DiceFocalLoss.forward 同签名。"""
        input = torch.sigmoid(input)
        input = torch.flatten(input)
        target = torch.flatten(target)

        # --- Dice 项：与官方 DiceFocalLoss / DiceLoss 逐字节一致（smooth=1，用未 clamp 的 input）---
        intersection = (input * target).sum()
        dice_loss = 1 - (2. * intersection + 1.) / (input.sum() + target.sum() + 1.)

        # --- Tversky 项（受控偏离：替换官方 focal，重罚 FN）；clamp 仅作用于此子项 ---
        inp = input.clamp(self.eps, 1.0 - self.eps)
        TP = (inp * target).sum()
        FP = (inp * (1.0 - target)).sum()
        FN = ((1.0 - inp) * target).sum()
        TI = (TP + self.smooth) / (TP + self.w_fp * FP + self.w_fn * FN + self.smooth)
        tversky_loss = 1.0 - TI
        if self.gamma != 1.0:
            # 原论文 Focal Tversky：(1-TI)^(1/γ)（见文件头 TODO 约定说明）
            tversky_loss = tversky_loss ** (1.0 / self.gamma)

        return dice_loss + tversky_loss
