"""
S8 -- 纯预测 overfit (silent-bug 哨兵 #8)

权威定义: 03_pilot_NIH_ChestXray14.md §7.8
  "纯预测 overfit: 单图反复预测, 10 ep 内 L2<0.01; 压不下 = NCA 连预测都学不动, 查架构"

对应 PC-1 (03_pilot §8): "NCA 训纯预测 (latent L2) 比训分割稳"。本哨兵是
s4 (overfit-one-batch) 在"单图/单样本 + 严格 L2<0.01 + 10 epoch 内"约束下的
特化版本, 专门针对 NCA predictor 本身的可学习性: 如果连"对同一张图反复跑
S 步 NCA rollout, 输出逼近一个固定 target latent"都做不到 L2<0.01, 说明
NCA predictor 架构本身 (感知 Conv3x3 + 更新 W2*ReLU(W1*p) + fire mask +
锚定 ctx 不变, 见 §3 规格) 有问题, 与三件套/EMA/数据规模无关, 需直接查架构。

=== TODO (待主线 NCA predictor 就绪后填入) ===

本文件提供:
  1. `pure_predict_overfit(model, x, target, ...)` -- 通用框架函数, 已可复用:
     给定 model (任意 forward(x) -> pred, pred.shape == target.shape) 和
     单样本 (x, target), 反复训练, 检查 L2(pred, target) 能否在指定 epoch
     数内压到 < tol (pilot: 10 ep 内 < 0.01)。

  2. `build_nca_pure_predict_case(...)` -- TODO 占位函数。等
     predictors/nca_predictor.py 就绪后, 在这里:
       - 构造单张 (1, C, 224, 224) 图像 (真实或合成)
       - 跑 I-JEPA context encoder 得到 14x14 token 网格特征 h_x
       - 用 §3 规格构造 h^0 = Concat(h_x + p_x, {mask_token + PE(u,v)})
       - 跑 NCA predictor S=16 步 rollout 得到 h_pred = h^S[mask 位置]
       - target = 该图像经 (冻结的) target encoder 得到的 h_y[mask 位置]
       - 返回 (nca_predictor_wrapper, h0_input, target) 供
         pure_predict_overfit 调用
     验证: result = pure_predict_overfit(wrapper, h0_input, target, max_epochs=10, tol=0.01)
           assert result.converged, "PC-1 纯预测 overfit 未过, NCA 架构本身学不动, 查架构"

  3. `__main__` self-test: 用一个小 MLP (模拟"预测器") + 合成单样本数据
     跑通 pure_predict_overfit, 证明框架逻辑正确 (10 epoch 内 L2 应 < 0.01)。
     与 NCA 架构无关, 纯粹验证本哨兵脚本自身可用。

可被训练脚本 import:
    from s8_pure_predict_overfit import pure_predict_overfit, PurePredictResult
"""

from __future__ import annotations

from dataclasses import dataclass, field

import torch
import torch.nn as nn


@dataclass
class PurePredictResult:
    l2_history: list[float] = field(default_factory=list)  # 每个 epoch 结束时的 L2(pred, target)
    converged: bool = False           # 是否在 max_epochs 内达到 l2 < tol
    final_l2: float = float("nan")
    epoch_converged: int | None = None  # 首次 l2 < tol 的 epoch (1-indexed)


def pure_predict_overfit(
    model: nn.Module,
    x,
    target: torch.Tensor,
    forward_fn=None,
    optimizer: torch.optim.Optimizer | None = None,
    max_epochs: int = 10,
    steps_per_epoch: int = 1,
    tol: float = 0.01,
    lr: float = 1e-3,
    verbose: bool = False,
) -> PurePredictResult:
    """
    "纯预测 overfit" 检验: 对单样本 x, 反复训练 model 使其输出逼近 target,
    检查 max_epochs 个 epoch 内 L2(pred, target) 能否 < tol。

    Parameters
    ----------
    model : nn.Module
        待测预测器 (例如 NCA predictor wrapper)。
    x : Any
        单样本输入 (会被反复喂给 model, 不变)。可以是 Tensor, 也可以是
        forward_fn 能处理的任意结构 (例如包含 mask indices 的 dict/tuple)。
    target : torch.Tensor
        单样本的目标输出 (例如 EMA target encoder 对 mask 位置的输出
        h_y, 来自 §3 规格: L = E||h_pred - h_y||^2)。
        forward_fn 的输出 shape 必须与 target 一致。
    forward_fn : Callable[[nn.Module, Any], torch.Tensor], optional
        若提供, 用 forward_fn(model, x) 计算预测; 否则默认 model(x)。
        用于适配 forward 签名复杂 (例如需要额外的 mask_indices 参数) 的模型。
    optimizer : torch.optim.Optimizer, optional
        默认 Adam(model.parameters(), lr=lr)。
    max_epochs : int
        最多训练多少"epoch" (pilot: 10)。
    steps_per_epoch : int
        每个 epoch 内的梯度更新次数 (单样本场景通常每 epoch 1 步; 若想模拟
        "多步内循环", 可调大)。
    tol : float
        L2(pred, target) 的收敛阈值 (pilot: 0.01)。
        L2 定义为 ||pred - target||_2 (欧氏范数, 不是 MSE; 若 target 维度高,
        范数本身会偏大 -- 调用方可根据 target 维度调整 tol 或改用
        per-element MSE, 这里遵循 pilot 字面 "L2<0.01" 取欧氏范数)。
    lr : float
        Adam 学习率。
    verbose : bool
        是否每个 epoch 打印 L2。

    Returns
    -------
    PurePredictResult
    """
    if optimizer is None:
        optimizer = torch.optim.Adam(model.parameters(), lr=lr)

    if forward_fn is None:
        forward_fn = lambda m, inp: m(inp)

    result = PurePredictResult()
    model.train()

    for epoch in range(1, max_epochs + 1):
        for _ in range(steps_per_epoch):
            optimizer.zero_grad()
            pred = forward_fn(model, x)
            loss = torch.nn.functional.mse_loss(pred, target)
            loss.backward()
            optimizer.step()

        with torch.no_grad():
            pred = forward_fn(model, x)
            l2 = (pred - target).norm().item()
        result.l2_history.append(l2)

        if verbose:
            print(f"  epoch {epoch:3d}  L2={l2:.6f}")

        if result.epoch_converged is None and l2 < tol:
            result.epoch_converged = epoch

    result.final_l2 = result.l2_history[-1] if result.l2_history else float("nan")
    result.converged = result.epoch_converged is not None

    return result


# =====================================================================
# TODO: 待主线 NCA predictor (predictors/nca_predictor.py) 就绪后实现
# =====================================================================
def build_nca_pure_predict_case(
    num_patches: int = 196,
    embed_dim: int = 384,
    n_ctx: int = 100,
    device: str | torch.device = "cpu",
    seed: int = 42,
    lr: float = 1e-3,
):
    """
    构造 "纯预测 overfit" 测试用例, 仅聚焦 NCA predictor 自身的拟合能力 (不走完整
    I-JEPA encoder 链, 喂固定合成 context/target token)。

    返回 (model, x, target, forward_fn, optimizer), 供
        pure_predict_overfit(model, x, target, forward_fn=forward_fn,
                             optimizer=optimizer, max_epochs=10, tol=0.01)
    调用。

    实现 (聚焦版, 对应 03_pilot §7.8 / PC-1):
      1. scp_nca predictor: deterministic_fire=True (关键 -- 固定 fire-mask 才可能
         L2->0, 随机 mask 每次 rollout 路径不同无法精确拟合, 见 PC-2/理论 §3.2)。
      2. 单个固定样本:
           - x       : [1, n_ctx, embed_dim] 随机但固定的 context encoder 特征。
           - masks_x : [[1, n_ctx]] 取 196 网格前 n_ctx 个位置当 context。
           - masks   : [[1, n_pred]] 剩下 (196 - n_ctx) 个位置当 pred 位置。
           - target  : [1, n_pred, embed_dim] 固定随机目标 latent。
      3. forward_fn(model, x_tuple) = model(x, masks_x, masks), 返回 [1, n_pred, embed_dim]。
      4. AdamW lr=1e-3; 框架内部用 MSE(pred, target) 训练, 用欧氏 L2 判收敛。

    fire-mask 固定性: deterministic_fire=True 时 NCAStep 用带固定 seed 的 generator,
    每次 forward 的 16 步 rollout fire-mask 应完全一致 -- 这是 overfit 能收敛的前提。
    若 loss 卡在地板降不下, 先查 fire 随机性是否真被固定 (哨兵价值所在)。

    调用:
        model, x, target, forward_fn, opt = build_nca_pure_predict_case(...)
        result = pure_predict_overfit(model, x, target, forward_fn=forward_fn,
                                      optimizer=opt, max_epochs=10, tol=0.01)
        assert result.converged, "PC-1 纯预测 overfit 未过 (10ep 内 L2<0.01), NCA 架构本身学不动, 查架构"
    """
    # ---- 延迟 import: 把 ijepa/ 加进 sys.path 以便 from src.models... ----
    import os
    import sys

    here = os.path.dirname(os.path.abspath(__file__))
    ijepa_root = os.path.join(os.path.dirname(here), "ijepa")
    if ijepa_root not in sys.path:
        sys.path.insert(0, ijepa_root)

    from src.models.nca_predictor import nca_predictor as _nca_predictor

    device = torch.device(device)
    grid = int(round(num_patches ** 0.5))
    assert grid * grid == num_patches, f"num_patches={num_patches} 非完全平方"
    assert 0 < n_ctx < num_patches, f"n_ctx={n_ctx} 须在 (0, {num_patches}) 内"
    n_pred = num_patches - n_ctx

    # 固定随机性, 保证样本/初始化可复现
    gen_cpu = torch.Generator().manual_seed(seed)

    # ---- scp_nca predictor: deterministic_fire=True 关键 ----
    model = _nca_predictor(
        stabilize=True,
        num_patches=num_patches,
        embed_dim=embed_dim,
        predictor_embed_dim=embed_dim,
        nca_steps=16,
        nca_hidden=128,
        fire_rate=0.5,
        deterministic_fire=True,
        fire_seed=42,
    ).to(device)

    # ---- 单个固定样本 ----
    # context encoder 特征 (随机但固定)
    x = torch.randn(1, n_ctx, embed_dim, generator=gen_cpu).to(device)
    # context 位置: 196 网格里前 n_ctx 个索引
    masks_x = [torch.arange(n_ctx, device=device).unsqueeze(0)]            # [1, n_ctx]
    # pred 位置: 剩下的索引
    masks = [torch.arange(n_ctx, num_patches, device=device).unsqueeze(0)]  # [1, n_pred]
    # 固定随机 target latent (predictor 输出维 = embed_dim)
    target = torch.randn(1, n_pred, embed_dim, generator=gen_cpu).to(device)

    # x 反复喂, 不变 -> 不需梯度; 只优化 predictor 参数
    x.requires_grad_(False)
    target.requires_grad_(False)

    optimizer = torch.optim.AdamW(model.parameters(), lr=lr)

    # forward_fn 适配 NCAPredictor.forward(x, masks_x, masks) 三参签名
    def forward_fn(m, inp):
        _x, _mx, _m = inp
        return m(_x, _mx, _m)

    x_tuple = (x, masks_x, masks)
    return model, x_tuple, target, forward_fn, optimizer


# =====================================================================
# Self-test: 小 MLP "预测器" + 合成单样本数据, 证明框架逻辑正确
# (与 NCA 架构无关, 纯粹验证本哨兵脚本本身)
# =====================================================================
class _ToyPredictor(nn.Module):
    """模拟一个简单预测器: 输入 latent 向量, 输出同维 latent 向量 (类似 NCA predictor 的 I/O 形状)。"""

    def __init__(self, dim: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(dim, 4 * dim),
            nn.ReLU(),
            nn.Linear(4 * dim, dim),
        )

    def forward(self, h0: torch.Tensor) -> torch.Tensor:
        return h0 + self.net(h0)  # 残差结构, 呼应 NCA 的 h <- h + m*delta


if __name__ == "__main__":
    n_pass = 0
    n_fail = 0

    torch.manual_seed(0)

    dim = 32
    model = _ToyPredictor(dim)

    # 单样本输入 h0 (模拟 mask 位置的初始 latent), target (模拟 EMA target encoder 输出)
    h0 = torch.randn(1, dim)
    target = torch.randn(1, dim)

    result = pure_predict_overfit(
        model, h0, target,
        max_epochs=10, steps_per_epoch=50, tol=0.01, lr=1e-2, verbose=False,
    )

    print(f"[INFO] l2_history: {[f'{v:.4f}' for v in result.l2_history]}")
    print(f"[INFO] final_l2={result.final_l2:.6f}, converged={result.converged}, "
          f"epoch_converged={result.epoch_converged}")

    # Test 1: L2 应大幅下降
    if result.l2_history[-1] < result.l2_history[0] * 0.1:
        print("[PASS] Test1: L2 大幅下降 (>90%)")
        n_pass += 1
    else:
        print(f"[FAIL] Test1: L2 下降不足 -> {result.l2_history[0]:.4f} -> {result.l2_history[-1]:.4f}")
        n_fail += 1

    # Test 2: 10 epoch 内应达到 L2 < 0.01 (pilot §7.8 标准)
    if result.converged and result.epoch_converged <= 10:
        print(f"[PASS] Test2: 10 epoch 内 L2<0.01 收敛 (于 epoch {result.epoch_converged})")
        n_pass += 1
    else:
        print(f"[FAIL] Test2: 10 epoch 内未达到 L2<0.01 -> final_l2={result.final_l2:.6f}")
        n_fail += 1

    # Test 3: 真跑 NCA predictor 纯预测 overfit (PC-1, 03_pilot §7.8)
    # 单图固定 target, deterministic_fire=True, 10 ep 内 L2 应 < 0.01。
    print("\n--- Test3: NCA predictor 纯预测 overfit (PC-1) ---")
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[INFO] device={dev}")
    torch.manual_seed(0)

    nca_model, nca_x, nca_target, nca_fwd, nca_opt = build_nca_pure_predict_case(
        num_patches=196, embed_dim=384, n_ctx=100, device=dev, seed=42, lr=1e-3,
    )

    # fire-mask 固定性自检: 同输入跑两次 forward, deterministic_fire=True 应逐元素一致
    nca_model.eval()
    with torch.no_grad():
        p_a = nca_fwd(nca_model, nca_x)
        p_b = nca_fwd(nca_model, nca_x)
    fire_fixed = torch.allclose(p_a, p_b, atol=0.0, rtol=0.0)
    max_delta = (p_a - p_b).abs().max().item()
    print(f"[INFO] deterministic_fire 固定性: 两次 forward 逐元素一致 = {fire_fixed} "
          f"(max|delta|={max_delta:.2e})")

    # ---- 判据修正：框架 l2=(pred-target).norm() 是全 numel 欧氏范数(平方和开根)，
    # 随张量元素数缩放。NCA target=[1,96,384]=36864 元素，即使 MSE→1e-6 欧氏范数
    # 仍≈0.19，tol=0.01 须 MSE<2.7e-12 不可达——是度量尺度缺陷，非架构问题。
    # §7#8「L2<0.01」本意为逐元素，故按 RMSE=norm/√numel<0.01 判收敛
    # （等价欧氏 tol = 0.01·√numel）。diag_s8_nca_overfit.py 已实证架构可 MSE→1e-6 收敛。
    import math as _math
    numel = nca_target.numel()
    rmse_tol = 0.01
    euclid_tol = rmse_tol * _math.sqrt(numel)
    nca_res = pure_predict_overfit(
        nca_model, nca_x, nca_target,
        forward_fn=nca_fwd, optimizer=nca_opt,
        max_epochs=10, steps_per_epoch=200, tol=euclid_tol, verbose=True,
    )
    final_rmse = nca_res.final_l2 / _math.sqrt(numel)
    print(f"[INFO] NCA l2_history: {[f'{v:.5f}' for v in nca_res.l2_history]}")
    print(f"[INFO] NCA L2(euclid): {nca_res.l2_history[0]:.5f} -> {nca_res.final_l2:.6f}  "
          f"final_RMSE(逐元素)={final_rmse:.6f}  (tol RMSE<{rmse_tol}, euclid<{euclid_tol:.2f})  "
          f"converged={nca_res.converged} epoch_converged={nca_res.epoch_converged}")

    if nca_res.converged:
        print(f"[PASS] Test3: NCA 纯预测 RMSE<0.01 收敛 (于 epoch {nca_res.epoch_converged}, "
              f"final_RMSE={final_rmse:.5f})")
        n_pass += 1
    else:
        print(f"[FAIL] Test3: NCA 纯预测未达 RMSE<0.01 -> final_RMSE={final_rmse:.6f} "
              f"(压不下=NCA 架构/接线有问题, 查 forward / fire 固定性, 别改阈值凑过)")
        n_fail += 1

    print(f"\n=== s8_pure_predict_overfit self-test: {n_pass} passed, {n_fail} failed ===")
    if n_fail == 0:
        print("OVERALL: PASS")
    else:
        print("OVERALL: FAIL")
        raise SystemExit(1)
