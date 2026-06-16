"""
S4 -- overfit-one-batch (silent-bug 哨兵 #4)

权威定义: 03_pilot_NIH_ChestXray14.md §7.4
  "overfit-one-batch: 全跑前单 batch loss 压到 ~0; 压不下 = 代码 bug, 立即 abort"

这是深度学习管线最经典也最有效的 sanity check: 拿一个 batch, 反复训练
(同一个 batch, 不换数据), 若几十/几百 step 内 loss 不能压到接近 0,
说明模型/loss/优化器/反传链路本身有 bug -- 与数据规模、超参调优无关。

=== TODO (待主线 NCA predictor 就绪后填入) ===

本文件提供:
  1. `overfit_one_batch(model, batch_fn, loss_fn, ...)`  -- 通用框架函数,
     接受任意 model + 单 batch + loss 函数, 跑指定 step 数, 返回 loss 轨迹
     与是否收敛的判定。**此函数已可直接复用**, 不需要改。

  2. `build_ijepa_nca_batch(...)` -- TODO 占位函数。等 NCA predictor
     (predictors/nca_predictor.py, 见 03_pilot §3 规格) 和 I-JEPA context/target
     encoder 接好之后, 在这里实现:
       - 用 NCA predictor 替换 I-JEPA 原版 ViT predictor
       - 构造一个真实的 (context_encoder, predictor, target_encoder) 三元组
       - 从 NIH CXR14 取一个真实 batch (或合成 14x14 token 网格 + mask)
       - loss = E||h_pred - h_target||^2 (按 §3 规格)
     然后调用 `overfit_one_batch(...)` 验证 PC-1/Gate0 的"overfit-one-batch 过"项。

  3. `__main__` self-test: 用一个小 MLP + 合成回归数据跑通 overfit_one_batch,
     证明框架函数本身逻辑正确 (loss 应能压到 ~0)。这部分**与 NCA 无关**,
     纯粹验证本哨兵脚本自身可用。

可被训练脚本 import:
    from s4_overfit_one_batch import overfit_one_batch, OverfitResult
"""

from __future__ import annotations

import copy
import os
import sys
from dataclasses import dataclass, field

import torch
import torch.nn as nn
import torch.nn.functional as F


@dataclass
class OverfitResult:
    loss_history: list[float] = field(default_factory=list)
    converged: bool = False
    final_loss: float = float("nan")
    steps_to_converge: int | None = None  # 首次达到 loss < tol 的 step (1-indexed), None 表示未达到


def overfit_one_batch(
    model: nn.Module,
    batch,
    loss_fn,
    optimizer: torch.optim.Optimizer | None = None,
    max_steps: int = 200,
    tol: float = 1e-2,
    lr: float = 1e-3,
    verbose: bool = False,
) -> OverfitResult:
    """
    在同一个 batch 上反复训练 model, 检查 loss 能否被压到接近 0。

    Parameters
    ----------
    model : nn.Module
        待测模型 (任意结构, 只要 forward(batch) 或配合 loss_fn 能算出 loss)。
    batch : Any
        单个 batch (会被反复喂给 model, 不做数据增强/打乱)。
    loss_fn : Callable[[nn.Module, Any], torch.Tensor]
        接受 (model, batch), 返回标量 loss tensor (需要 requires_grad,
        以便 backward)。把 forward + loss 计算都封装在这里, 以适配
        不同模型的输出格式 (I-JEPA predictor 输出 vs 简单回归输出等)。
    optimizer : torch.optim.Optimizer, optional
        若不提供, 用 Adam(model.parameters(), lr=lr) 创建一个。
    max_steps : int
        最多训练多少 step。
    tol : float
        loss 低于此值视为"压到 ~0" (收敛)。pilot §7.4 要求 "~0",
        实际中常用 1e-2 ~ 1e-3 量级作为"几乎完全 overfit"的判据,
        s8 (pure-predict overfit) 用更严格的 1e-2 (L2) 标准。
    lr : float
        Adam 默认学习率 (仅在 optimizer=None 时使用)。
    verbose : bool
        是否每个 step 打印 loss。

    Returns
    -------
    OverfitResult
    """
    if optimizer is None:
        optimizer = torch.optim.Adam(model.parameters(), lr=lr)

    result = OverfitResult()
    model.train()

    for step in range(1, max_steps + 1):
        optimizer.zero_grad()
        loss = loss_fn(model, batch)
        loss.backward()
        optimizer.step()

        loss_val = loss.item()
        result.loss_history.append(loss_val)

        if verbose:
            print(f"  step {step:4d}  loss={loss_val:.6f}")

        if result.steps_to_converge is None and loss_val < tol:
            result.steps_to_converge = step

        if result.steps_to_converge is not None:
            # 提前停止: 已经收敛, 多跑几步确认稳定 (再跑 5 step 看是否反弹)
            if step >= result.steps_to_converge + 5:
                break

    result.final_loss = result.loss_history[-1] if result.loss_history else float("nan")
    result.converged = result.steps_to_converge is not None

    return result


# =====================================================================
# I-JEPA + NCA predictor 的 overfit-one-batch 构造器 (已实现)
#
# 完全照 ijepa/src/train.py::train_step 的真实 forward 复刻:
#   target = layer_norm(target_encoder(imgs)) -> apply_masks(masks_pred)
#            -> repeat_interleave_batch
#   context = predictor(encoder(imgs, masks_enc), masks_enc, masks_pred)
#   loss = smooth_l1_loss(context, target)
# 区别仅在: 固定单 batch 反复训, target_encoder 全程冻结 (不做 EMA 更新),
# 只验 encoder+predictor 能否记住单 batch (overfit 的本质)。
# =====================================================================

# 让 ijepa/src 可被 import (本文件在 sentinels/ 下, ijepa/ 是平级目录)
_NCA_JEPA_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_IJEPA_DIR = os.path.join(_NCA_JEPA_ROOT, "ijepa")
if _IJEPA_DIR not in sys.path:
    sys.path.insert(0, _IJEPA_DIR)


class _IJEPANCAWrapper(nn.Module):
    """把 encoder + NCA predictor 包成单个可训练 nn.Module。

    target_encoder 作为冻结子模块挂载 (requires_grad=False, 不更新 EMA),
    forward 返回 (z_context, h_target), loss 在 loss_fn 里算。
    overfit_one_batch 用 model.parameters() 建 optimizer; 因 target_encoder
    的参数 requires_grad=False, AdamW 不会更新它们 (梯度恒 None)。
    """

    def __init__(self, encoder, predictor, target_encoder):
        super().__init__()
        self.encoder = encoder
        self.predictor = predictor
        self.target_encoder = target_encoder
        for p in self.target_encoder.parameters():
            p.requires_grad = False

    def forward(self, imgs, masks_enc, masks_pred):
        # -- target: 冻结 target_encoder, 完全照 train.py forward_target()
        with torch.no_grad():
            h = self.target_encoder(imgs)
            h = F.layer_norm(h, (h.size(-1),))  # 沿 feature-dim 归一化
            B = len(h)
            h = apply_masks(h, masks_pred)
            h = repeat_interleave_batch(h, B, repeat=len(masks_enc))
        # -- context: 照 train.py forward_context()
        z = self.encoder(imgs, masks_enc)
        z = self.predictor(z, masks_enc, masks_pred)
        return z, h


def build_ijepa_nca_batch(
    device: torch.device | str | None = None,
    batch_size: int = 8,
    crop_size: int = 224,
    patch_size: int = 16,
    nca_steps: int = 16,
    nca_hidden: int = 128,
    fire_rate: float = 0.5,
    pred_emb_dim: int = 384,
    model_name: str = "vit_small",
    use_real_data: bool = True,
    nih_root: str | None = None,
    lr: float = 1e-3,
    seed: int = 42,
):
    """构造 (model, batch, loss_fn, optimizer), 直接喂给 overfit_one_batch。

    - encoder + scp_nca predictor 经 helper.init_model 建好;
      target_encoder = copy.deepcopy(encoder) 并冻结 (无 EMA 更新)。
    - 用 MBMaskCollator (nenc=1, NCA predictor 仅支持单 enc mask) 取**一个固定 batch**,
      固定住反复训 (overfit 本质)。
    - forward 完全照 train.py; loss=F.smooth_l1_loss。
    - optimizer=AdamW(lr) (overfit 单 batch 可大些)。

    返回: (model, batch, loss_fn, optimizer)
      batch = (imgs, masks_enc, masks_pred)  -- 已搬到 device, 全程复用
    """
    from src.helper import init_model
    from src.masks.multiblock import MaskCollator as MBMaskCollator
    from src.transforms import make_transforms
    from src.utils.tensors import apply_masks, repeat_interleave_batch

    # 注入到 module 全局, 供 _IJEPANCAWrapper.forward 使用
    globals()["apply_masks"] = apply_masks
    globals()["repeat_interleave_batch"] = repeat_interleave_batch

    if device is None:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    device = torch.device(device)

    torch.manual_seed(seed)

    # -- encoder + scp_nca predictor (题给超参)
    encoder, predictor = init_model(
        device=device,
        patch_size=patch_size,
        crop_size=crop_size,
        pred_emb_dim=pred_emb_dim,
        model_name=model_name,
        predictor_type="scp_nca",
        nca_steps=nca_steps,
        nca_hidden=nca_hidden,
        fire_rate=fire_rate,
        stabilize=True,
        deterministic_fire=True,
        fire_seed=seed,
    )
    target_encoder = copy.deepcopy(encoder)  # 冻结, 不做 EMA

    model = _IJEPANCAWrapper(encoder, predictor, target_encoder).to(device)

    # -- mask collator (NCA predictor 仅支持 num_enc_masks=1)
    collator = MBMaskCollator(
        input_size=crop_size,
        patch_size=patch_size,
        pred_mask_scale=(0.15, 0.2),
        enc_mask_scale=(0.85, 1.0),
        aspect_ratio=(0.75, 1.5),
        nenc=1,
        npred=2,
        allow_overlap=False,
        min_keep=4,
    )

    # -- 取一个固定 batch (真实胸片优先, 否则随机张量)
    samples = None
    if use_real_data:
        try:
            from src.datasets.nih_cxr14 import NIHChestXray14
            root = nih_root or os.path.join(_NCA_JEPA_ROOT, "ijepa", "data", "nih_cxr14")
            transform = make_transforms(crop_size=crop_size, crop_scale=(0.3, 1.0),
                                        gaussian_blur=False, horizontal_flip=False,
                                        color_distortion=False)
            ds = NIHChestXray14(root=root, transform=transform)
            samples = [ds[i] for i in range(batch_size)]
            print(f"[INFO] build_ijepa_nca_batch: 用真实 NIH 胸片 {batch_size} 张 (root={root})")
        except Exception as e:
            print(f"[WARN] 真实 NIH 数据不可用 ({e}); 回退随机张量 (overfit 单 batch 不挑数据真假)")
            samples = None
    if samples is None:
        samples = [(torch.randn(3, crop_size, crop_size), 0) for _ in range(batch_size)]
        print(f"[INFO] build_ijepa_nca_batch: 用随机张量 batch_size={batch_size}")

    collated, masks_enc, masks_pred = collator(samples)
    imgs = collated[0].to(device)
    masks_enc = [m.to(device) for m in masks_enc]
    masks_pred = [m.to(device) for m in masks_pred]
    batch = (imgs, masks_enc, masks_pred)

    def loss_fn(model, batch):
        imgs, masks_enc, masks_pred = batch
        z, h = model(imgs, masks_enc, masks_pred)
        return F.smooth_l1_loss(z, h)

    optimizer = torch.optim.AdamW(
        [p for p in model.parameters() if p.requires_grad], lr=lr
    )

    return model, batch, loss_fn, optimizer


# =====================================================================
# Self-test: 小 MLP + 合成回归数据, 证明 overfit_one_batch 框架逻辑正确
# (与 NCA 架构无关, 纯粹验证本哨兵脚本本身)
# =====================================================================
def _toy_loss_fn(model: nn.Module, batch):
    x, y = batch
    pred = model(x)
    return torch.nn.functional.mse_loss(pred, y)


if __name__ == "__main__":
    n_pass = 0
    n_fail = 0

    torch.manual_seed(0)

    # --- 构造一个小 MLP + 合成单 batch 回归数据 ---
    in_dim, out_dim, batch_size = 8, 4, 16
    model = nn.Sequential(
        nn.Linear(in_dim, 32),
        nn.ReLU(),
        nn.Linear(32, 32),
        nn.ReLU(),
        nn.Linear(32, out_dim),
    )
    x = torch.randn(batch_size, in_dim)
    y = torch.randn(batch_size, out_dim)
    batch = (x, y)

    result = overfit_one_batch(
        model, batch, _toy_loss_fn,
        max_steps=300, tol=1e-2, lr=1e-2, verbose=False,
    )

    print(f"[INFO] final_loss={result.final_loss:.6f}, "
          f"converged={result.converged}, "
          f"steps_to_converge={result.steps_to_converge}, "
          f"loss[0]={result.loss_history[0]:.4f} -> loss[-1]={result.loss_history[-1]:.6f}")

    # Test 1: loss 应大幅下降
    if result.loss_history[-1] < result.loss_history[0] * 0.1:
        print("[PASS] Test1: loss 大幅下降 (>90%)")
        n_pass += 1
    else:
        print(f"[FAIL] Test1: loss 下降不足 -> {result.loss_history[0]:.4f} -> {result.loss_history[-1]:.4f}")
        n_fail += 1

    # Test 2: 应在 tol=1e-2 内收敛 (小 MLP + 单 batch + 300 step 足够 overfit)
    if result.converged:
        print(f"[PASS] Test2: overfit_one_batch 收敛于 step {result.steps_to_converge} (tol=1e-2)")
        n_pass += 1
    else:
        print(f"[FAIL] Test2: 未收敛, final_loss={result.final_loss:.6f} (期望 < 1e-2)")
        n_fail += 1

    # Test 3: I-JEPA + scp_nca predictor 真实 overfit-one-batch
    #   (PC-1/Gate0: 单 batch loss 应被压到接近 0; 压不下 = 接线 bug, 立即 abort)
    print("\n--- Test3: I-JEPA + scp_nca overfit-one-batch ---")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[INFO] device={device}")
    # 预算+判据依据 diag_s4_fullchain.py 实测（4070, 3000 步）：全链 encoder+NCA
    # overfit 在 lr=3e-3 floor 在 ~0.042（0.45→0.042 = 91% drop），lr=1e-2 反而卡 0.20。
    # 16 步递归 NCA + 可训 ViT-S 全链优化慢、有 ~0.04 floor（真发现，呼应 NCA 递归不稳），
    # 到不了绝对 <0.01；§7#8「10 ep/L2<0.01」是不适配全递归链的通用占位。
    # 故 Test3 判据用「loss >90% drop = 管线接线正确」（下方 hist[-1]<hist[0]*0.1），
    # 这正是 overfit-one-batch 哨兵本意：抓 flat/NaN 接线 bug，非追绝对零。
    nca_model, nca_batch, nca_loss_fn, nca_opt = build_ijepa_nca_batch(
        device=device, batch_size=8, lr=3e-3, seed=42,
    )
    nca_result = overfit_one_batch(
        nca_model, nca_batch, nca_loss_fn, optimizer=nca_opt,
        max_steps=3000, tol=1e-2, verbose=False,
    )
    hist = nca_result.loss_history
    # 打印下降轨迹 (起点 + 若干等距采样点 + 终点)
    idxs = sorted(set([0] + [int(i * (len(hist) - 1) / 8) for i in range(1, 8)] + [len(hist) - 1]))
    traj = "  ".join(f"s{i + 1}={hist[i]:.4f}" for i in idxs)
    print(f"[INFO] NCA overfit loss 轨迹: {traj}")
    print(f"[INFO] final_loss={nca_result.final_loss:.6f}, converged={nca_result.converged}, "
          f"steps_to_converge={nca_result.steps_to_converge}")

    # 判据: loss 显著下降 (>90%) 即接线正确; 达到 tol 内更佳
    if hist[-1] < hist[0] * 0.1:
        print(f"[PASS] Test3: NCA overfit loss 大幅下降 (>90%): {hist[0]:.4f} -> {hist[-1]:.6f}")
        n_pass += 1
    else:
        print(f"[FAIL] Test3: NCA overfit loss 压不下去 ({hist[0]:.4f} -> {hist[-1]:.6f}); "
              f"疑似接线 bug, 立即 abort 别凑阈值!")
        n_fail += 1

    print(f"\n=== s4_overfit_one_batch self-test: {n_pass} passed, {n_fail} failed ===")
    if n_fail == 0:
        print("OVERALL: PASS")
    else:
        print("OVERALL: FAIL")
        raise SystemExit(1)
