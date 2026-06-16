# -*- coding: utf-8 -*-
# =============================================================================
# NCA-JEPA — 残差迭代谱半径下界验证探针
#
# Claim（拯救路线 A, lever = 残差式迭代映射谱半径下界普适性）：
#   残差映射 F(h) = h + g(h) 的单步 Jacobian = I + J_g
#   谱半径 ρ(I+J_g) 有结构性下界 ≈1，无论如何 spectral-norm 压 g
#   → 严格收缩（ρ<1）在残差结构下不可达；
#   且跨模型族（MLP/Conv/Attn）普适。
#
# 【核心口径说明：ρ vs σ_max】
#   eval_anytime.py::estimate_lf 用 autograd-JVP power iteration 算的是
#   σ_max = ‖J‖_2（最大奇异值/谱范数），不是 ρ（谱半径 = max|λ|）。
#   σ_max ≥ ρ 恒成立；claim 的下界故事对 ρ 才成立，对 σ_max 几乎平凡
#   （反例：J_g ≈ −εI 时 σ_max(I+J_g)=1−ε < 1）。
#   本脚本同时输出 ρ 和 σ_max 两列，分列显示，桥接 eval_anytime 旧口径。
#
# 【计算方法】
#   小维度（d*H*W ≤ DIM_EXACT_THRESH = 1024）：
#     - 用 torch.autograd.functional.jacobian 显式构造完整 Jacobian 矩阵 J ∈ R^{n×n}
#     - torch.linalg.eigvals(J) → ρ = max|λ|  (金标准，无迭代误差)
#     - torch.linalg.svdvals(J)[0] → σ_max
#     - 同时输出 J_g 自身的最大特征值模，验证 λ(I+J_g) = 1+λ(J_g)
#   大维度：
#     - σ_max：JVP power iteration（同 eval_anytime estimate_lf 骨架）
#     - ρ：对 J（非 J^T J）做幂迭代，取主特征值模（处理复特征值时取 ‖v_next‖/‖v‖）
#     - 两者都标注 "(power-iter approx)"
#
# 【falsify run-set（新，v2）】
#   主动攻击 claim 的危险 case：
#   1. Conv 修复：ConvNCAg 所有权重 kaiming 随机初始化（修复 zero-init 退化问题）
#   2. 反对称权重 g（antisym）：W = A - Aᵀ，特征值纯虚 ±βi → 测 ρ(I+J_g)
#   3. 负实特征值接近 -1 的线性 g（neg_real）：J_g = diag(-0.8,-0.9,-0.95,...)
#      SN 约束（sn_scale=1.0）和无约束（sn_scale=2.0）各测一次
#   4. 多 seed（mlp/attn/nca 各跑 seed=0,1,2），报 ρ mean±std
#
# 用法：
#   # smoke 单次（CPU，小 d，验管线）
#   python eval/spectral_lower_bound.py --smoke --dim 64
#
#   # 最小可跑集（4 runs）
#   python eval/spectral_lower_bound.py --run-set minimal
#
#   # 证伪专项（falsify run-set，主动攻击 claim）
#   python eval/spectral_lower_bound.py --run-set falsify
#
#   # 单次指定参数
#   python eval/spectral_lower_bound.py --g-type mlp --mode residual --sn-scale 1.0 --dim 256 --seed 42
#
#   # 多 seed 扫描
#   python eval/spectral_lower_bound.py --g-type mlp --mode residual --seeds 0 1 2
#
# 输出 CSV：results/spectral_lower_bound/results.csv
#   列：run_id, g_type, mode, sn_scale, dim, seed, rho, sigma_max,
#       lambda_g_max_mod, lambda_g_real, lambda_g_imag,
#       rho_method, sigma_method, notes
# =============================================================================

import os
import sys
import csv
import math
import argparse
import itertools
from pathlib import Path
from typing import Callable, Tuple, Optional

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

# ------- 路径注入（可选：R0 读 NCAStep）-------------------------------
_HERE = Path(__file__).resolve().parent
_IJEPA_ROOT = _HERE.parent / "ijepa"
if str(_IJEPA_ROOT) not in sys.path:
    sys.path.insert(0, str(_IJEPA_ROOT))

# =====================================================================
# 阈值：维度 ≤ 此值时用显式 Jacobian（金标准），否则幂迭代
# =====================================================================
DIM_EXACT_THRESH = 1024


# =====================================================================
# 工具：受控 spectral-norm 重缩放
# =====================================================================

def _sigma_max_weight(W: torch.Tensor) -> float:
    """算单个权重矩阵的最大奇异值（2D reshape）。"""
    W2 = W.view(W.shape[0], -1)
    return torch.linalg.svdvals(W2)[0].item()


def apply_sn_scale(module: nn.Module, c: float) -> None:
    """受控旋钮：对 module 内所有 Conv2d / Linear 权重做 W <- c * W/σ_max(W)。
    这是手动重缩放，**非** PyTorch spectral_norm（后者固定 σ→1 不能调强度）。
    注释：受控旋钮，非生产 SN。
    """
    with torch.no_grad():
        for m in module.modules():
            if isinstance(m, (nn.Conv2d, nn.Linear)):
                sigma = _sigma_max_weight(m.weight)
                if sigma > 1e-8:
                    m.weight.copy_(m.weight * (c / sigma))


# =====================================================================
# g 模块定义
# =====================================================================

class MLPg(nn.Module):
    """g(h) = W₂·ReLU(W₁·h)，作用于展平向量。
    输入 h: [d]（单样本展平），输出 [d]。"""

    def __init__(self, d: int, hidden: Optional[int] = None):
        super().__init__()
        hidden = hidden or max(d, 64)
        self.fc1 = nn.Linear(d, hidden)
        self.fc2 = nn.Linear(hidden, d)

    def forward(self, h: torch.Tensor) -> torch.Tensor:
        # h: [d] 或 [1, d]
        shape = h.shape
        x = h.view(-1)
        x = F.relu(self.fc1(x))
        x = self.fc2(x)
        return x.view(shape)


class ConvNCAg(nn.Module):
    """NCA 风格 g：类 NCAStep 感知+MLP，但作用于单张 [C, H, W] 特征图（确定性，fire_rate=0）。
    Jacobian = d(fire*delta)/dh，fire=1（确定性，去除随机性保证 Jacobian 确定）。
    输入输出 h: [C, H, W]（无 batch 维，配合 Jacobian 构造）。

    [v2 修复] 不再在 __init__ 零初始化 fc1（探针脚本需要非零 J_g）。
    零初始化是训练起步约定，在 build_experiment 的生产分支里可按需开。
    探针里统一走 build_experiment 的随机初始化覆盖逻辑。
    """

    def __init__(self, C: int, H: int, W: int, hidden: int = 64):
        super().__init__()
        self.C, self.H, self.W = C, H, W
        # 感知两路 conv3x3
        self.p0 = nn.Conv2d(C, C, 3, padding=1, padding_mode='reflect')
        self.p1 = nn.Conv2d(C, C, 3, padding=1, padding_mode='reflect')
        # 更新 MLP（1x1 conv）
        self.fc0 = nn.Conv2d(C * 3, hidden, 1)
        self.fc1 = nn.Conv2d(hidden, C, 1, bias=False)
        # 注意：官方 NCA 训练约定在此零初始化 fc1，但探针脚本需非零权重才能
        # 得到非零 J_g。零初始化由 build_experiment 按 g_type/use_zero_init 参数控制。
        # 此处改为默认 kaiming_normal_，保证探针开箱即用。
        nn.init.kaiming_normal_(self.fc1.weight, nonlinearity='relu')

    def forward(self, h: torch.Tensor) -> torch.Tensor:
        # h: [C, H, W] -> 加 batch 维做卷积 -> 去掉
        x = h.unsqueeze(0)  # [1, C, H, W]
        perc = torch.cat([x, self.p0(x), self.p1(x)], dim=1)  # [1, 3C, H, W]
        delta = self.fc1(F.relu(self.fc0(perc)))  # [1, C, H, W]
        return delta.squeeze(0)  # [C, H, W]


class AttnResidualg(nn.Module):
    """Pre-LN 单头 self-attention 残差块（标准 Transformer 顺序）。
    输入 h: [S, D]（S=序列长，D=维），输出 [S, D]（仅 attention 增量，不含 FFN）。
    """

    def __init__(self, S: int, D: int):
        super().__init__()
        self.S, self.D = S, D
        self.ln = nn.LayerNorm(D)
        self.attn = nn.MultiheadAttention(D, num_heads=1, batch_first=False)

    def forward(self, h: torch.Tensor) -> torch.Tensor:
        # h: [S, D] -> [S, 1, D]（MHA 期待 [S, B, D]）
        x = h.unsqueeze(1)
        normed = self.ln(x)
        # self-attention，关闭 dropout（eval 模式时默认 0）
        attn_out, _ = self.attn(normed, normed, normed, need_weights=False)
        return attn_out.squeeze(1)  # [S, D]


# =====================================================================
# 证伪专项 g 类（v2 新增）
# =====================================================================

class AntiSymLinearG(nn.Module):
    """反对称权重线性 g：g(h) = W·h，W = A - Aᵀ（A 随机）。
    反对称矩阵特征值纯虚：λ = ±βi（β≥0）。
    则 J_g = W，J_F = I + W，特征值 = 1 ± βi。
    ρ(I+W) = max_k √(1 + βk²) ≥ 1，理论上 claim 仍成立。
    SN 约束（apply_sn_scale）会压 σ_max(W) 到目标值，
    但反对称矩阵 σ_max = β_max（最大纯虚特征值的模），
    所以 SN<1 时 β_max<1，ρ(I+W) = √(1+β_max²) > 1 仍恒成立。
    目的：验证复纯虚特征值路径下 claim 是否有反例。
    输入/输出 h: [d]（展平向量）。
    """

    def __init__(self, d: int):
        super().__init__()
        self.d = d
        # A 随机，W = A - Aᵀ（反对称）
        A = torch.randn(d, d)
        W = A - A.t()  # 反对称：W = -Wᵀ
        # 注册为 buffer（非参数，不参与 SN 缩放的正常 Linear weight 接口）
        # apply_sn_scale 扫 Conv2d/Linear，这里用 Parameter + Linear 接口
        # 让 apply_sn_scale 能识别并缩放
        self.linear = nn.Linear(d, d, bias=False)
        with torch.no_grad():
            self.linear.weight.copy_(W)

    def forward(self, h: torch.Tensor) -> torch.Tensor:
        shape = h.shape
        x = h.view(-1)
        return self.linear(x).view(shape)


class NegRealLinearG(nn.Module):
    """负实特征值线性 g：g(h) = W·h，W 特征值含大量负实 λ ∈ {-0.8,-0.85,-0.9,-0.95}。
    构造方法：随机正交 Q（via QR），对角 D 填目标负实特征值，W = Q·D·Qᵀ（实对称）。
    实对称矩阵特征值均为实数，因此 λ(I+W) = 1 + λ(W)。
    当 λ_min(W) 接近 -1 时：λ(I+W) 接近 0 → ρ(I+W) 接近 0。
    这是 claim 最危险的反例构型：如果 SN<1 约束下仍能有 λ_g < -1，则 ρ < 0
    （模<1，即真正的 claim 反例）。
    目的：直接探测"负实特征值接近 -1"路径是否能造出 ρ < 1。

    参数 neg_eig_vals: 对角特征值列表，其余用 +0.1 填充（让 SN 不为 0）。
    实际 SN = max|λ| = max(|neg_eig_vals|, 0.1)。
    apply_sn_scale(g, c) 后，SN → c，特征值等比缩放。
    """

    def __init__(self, d: int, neg_eig_vals: Optional[list] = None):
        super().__init__()
        self.d = d
        if neg_eig_vals is None:
            # 默认：前 d//2 用负实值（越来越接近 -1），后 d//2 用 +0.1
            # 覆盖多个典型负实值
            n_neg = max(1, d // 2)
            vals = []
            targets = [-0.80, -0.85, -0.90, -0.95]
            for i in range(n_neg):
                vals.append(targets[i % len(targets)])
            for i in range(d - n_neg):
                vals.append(0.10)
            neg_eig_vals = vals
        assert len(neg_eig_vals) == d, f"neg_eig_vals 长度 {len(neg_eig_vals)} != d={d}"

        # 构造随机正交矩阵 Q via QR 分解
        A = torch.randn(d, d)
        Q, _ = torch.linalg.qr(A)  # Q: [d, d] 正交矩阵
        D = torch.tensor(neg_eig_vals, dtype=torch.float32)  # [d]
        # W = Q · diag(D) · Qᵀ（实对称，特征值恰为 neg_eig_vals）
        W = Q @ torch.diag(D) @ Q.t()

        self.linear = nn.Linear(d, d, bias=False)
        with torch.no_grad():
            self.linear.weight.copy_(W)

        # 记录理论最危险特征值（最负的那个）
        self._neg_eig_min = min(neg_eig_vals)

    def forward(self, h: torch.Tensor) -> torch.Tensor:
        shape = h.shape
        x = h.view(-1)
        return self.linear(x).view(shape)


# =====================================================================
# 残差包装（mode 切换）
# =====================================================================

class ResidualWrapper(nn.Module):
    """F(h) = h + g(h)：residual 模式。"""

    def __init__(self, g: nn.Module):
        super().__init__()
        self.g = g

    def forward(self, h: torch.Tensor) -> torch.Tensor:
        return h + self.g(h)


class PureWrapper(nn.Module):
    """F(h) = g(h)：pure/DEQ 模式（无 I 项）。
    g 内部结构与 residual 完全相同，唯一差异是有无 I 项。"""

    def __init__(self, g: nn.Module):
        super().__init__()
        self.g = g

    def forward(self, h: torch.Tensor) -> torch.Tensor:
        return self.g(h)


# =====================================================================
# Jacobian 构造与谱分析
# =====================================================================

def build_explicit_jacobian(F_func: Callable, h0: torch.Tensor) -> torch.Tensor:
    """显式构造完整 Jacobian 矩阵 J ∈ R^{n×n}（金标准，仅小维度用）。
    F_func: h (展平向量, [n]) -> 输出 (展平向量, [n])
    h0: 展平基点 [n]，requires_grad=False。
    返回 J: [n, n]，J[i,j] = ∂F_i/∂h_j。
    """
    n = h0.numel()
    h = h0.detach().clone().requires_grad_(True)
    out = F_func(h)
    # 按行计算（每行一个 grad）
    rows = []
    for i in range(n):
        grad = torch.autograd.grad(
            out[i], h, retain_graph=(i < n - 1), create_graph=False
        )[0]
        rows.append(grad.detach().clone())
    J = torch.stack(rows, dim=0)  # [n, n]
    return J


def spectral_analysis_exact(
    F_func: Callable,
    g_func: Callable,
    h0: torch.Tensor,
    mode: str
) -> Tuple[float, float, float, float, float]:
    """金标准谱分析（小维度，显式 eig/svd）。
    返回 (rho, sigma_max, lambda_g_max_mod, lambda_g_dominant_real, lambda_g_dominant_imag)。
    lambda_g_dominant_{real,imag}：J_g 主特征值（最大|λ|对应）的实虚部。
    验证恒等式: λ(I+J_g) = 1+λ(J_g)（仅 residual 模式）。
    """
    n = h0.numel()

    def F_flat(h_flat: torch.Tensor) -> torch.Tensor:
        return F_func(h_flat.view(h0.shape)).view(-1)

    def g_flat(h_flat: torch.Tensor) -> torch.Tensor:
        return g_func(h_flat.view(h0.shape)).view(-1)

    # J_F（全映射 Jacobian）
    J_F = build_explicit_jacobian(F_flat, h0.view(-1))

    # ρ(J_F) = max|λ(J_F)|
    eigs_F = torch.linalg.eigvals(J_F)             # complex tensor
    rho = eigs_F.abs().max().item()

    # σ_max(J_F) = 最大奇异值
    sigma_max = torch.linalg.svdvals(J_F)[0].item()

    # J_g 谱（验证恒等式 + 提取主特征值实虚部）
    J_g = build_explicit_jacobian(g_flat, h0.view(-1))
    eigs_g = torch.linalg.eigvals(J_g)
    lambda_g_max_mod = eigs_g.abs().max().item()

    # 主特征值（最大|λ|对应的那个）的实虚部
    dominant_idx = eigs_g.abs().argmax()
    dominant_eig = eigs_g[dominant_idx]
    lambda_g_dominant_real = dominant_eig.real.item()
    lambda_g_dominant_imag = dominant_eig.imag.item()

    # 恒等式验证（仅 residual 模式，I+J_g 的特征值应等于 1+λ(J_g)）
    if mode == "residual":
        # 理论：ρ(I+J_g) ≈ max|1+λ_k(J_g)|，而非 1+max|λ_k(J_g)|
        # 以下只做一致性打印，不纳入 CSV
        expected_eigs = 1.0 + eigs_g  # complex
        max_expected = expected_eigs.abs().max().item()
        diff = abs(rho - max_expected)
        if diff > 1e-3:
            print(f"    [warn] 恒等式偏差 {diff:.4f}: ρ(J_F)={rho:.4f} vs max|1+λ(J_g)|={max_expected:.4f}")

    return (float(rho), float(sigma_max), float(lambda_g_max_mod),
            float(lambda_g_dominant_real), float(lambda_g_dominant_imag))


def spectral_analysis_poweriter(
    F_func: Callable,
    g_func: Callable,
    h0: torch.Tensor,
    mode: str,
    n_iter: int = 50
) -> Tuple[float, float, float, float, float]:
    """大维度幂迭代估计。
    σ_max: JVP power iteration（‖J^T J v‖ 方向，同 eval_anytime 骨架）。
    ρ: 对 J（非 J^T J）做幂迭代，取 ‖Jv_{t+1}‖/‖Jv_t‖ 估主特征值模。
    lambda_g_max_mod: 对 J_g 同样幂迭代（ρ_g，用于近似验证恒等式）。
    lambda_g_dominant_real/imag: 幂迭代无法精确拿复特征值实虚部，返回 nan。
    """
    n = h0.numel()

    def jvp_F(h_base: torch.Tensor, v: torch.Tensor) -> torch.Tensor:
        """J_F · v via autograd。"""
        h_ = h_base.detach().view(h0.shape).requires_grad_(True)
        out = F_func(h_)
        (jv,) = torch.autograd.grad(
            out, h_, grad_outputs=v.view(h0.shape), create_graph=False)
        return jv.view(-1).detach()

    def jvp_g(h_base: torch.Tensor, v: torch.Tensor) -> torch.Tensor:
        h_ = h_base.detach().view(h0.shape).requires_grad_(True)
        out = g_func(h_)
        (jv,) = torch.autograd.grad(
            out, h_, grad_outputs=v.view(h0.shape), create_graph=False)
        return jv.view(-1).detach()

    h_flat = h0.view(-1).detach()

    # σ_max: power iteration on J^T J
    v = torch.randn(n, device=h0.device)
    v = v / (v.norm() + 1e-12)
    sigma_max = 0.0
    for _ in range(n_iter):
        jv = jvp_F(h_flat, v)
        sigma_new = jv.norm().item()
        v = jv / (jv.norm() + 1e-12)
        sigma_max = sigma_new

    # ρ: 对 J_F 直接幂迭代（比值估主特征值模）
    v2 = torch.randn(n, device=h0.device)
    v2 = v2 / (v2.norm() + 1e-12)
    rho = 0.0
    for _ in range(n_iter):
        jv2 = jvp_F(h_flat, v2)
        norm_new = jv2.norm().item()
        norm_cur = v2.norm().item()
        if norm_cur > 1e-12:
            rho = norm_new / norm_cur
        v2 = jv2 / (jv2.norm() + 1e-12)

    # ρ_g: J_g 幂迭代
    v3 = torch.randn(n, device=h0.device)
    v3 = v3 / (v3.norm() + 1e-12)
    lambda_g_max_mod = 0.0
    for _ in range(n_iter):
        jv3 = jvp_g(h_flat, v3)
        norm_new = jv3.norm().item()
        norm_cur = v3.norm().item()
        if norm_cur > 1e-12:
            lambda_g_max_mod = norm_new / norm_cur
        v3 = jv3 / (jv3.norm() + 1e-12)

    return float(rho), float(sigma_max), float(lambda_g_max_mod), float("nan"), float("nan")


def analyze_spectral(
    F_func: Callable,
    g_func: Callable,
    h0: torch.Tensor,
    mode: str
) -> Tuple[float, float, float, float, float, str, str]:
    """自动选择显式 eig vs 幂迭代。
    返回 (rho, sigma_max, lambda_g_max_mod, lambda_g_real, lambda_g_imag, rho_method, sigma_method)。
    """
    n = h0.numel()
    if n <= DIM_EXACT_THRESH:
        rho, sigma_max, lam_g, lam_g_re, lam_g_im = spectral_analysis_exact(
            F_func, g_func, h0, mode)
        return rho, sigma_max, lam_g, lam_g_re, lam_g_im, "exact-eig", "exact-svd"
    else:
        rho, sigma_max, lam_g, lam_g_re, lam_g_im = spectral_analysis_poweriter(
            F_func, g_func, h0, mode)
        return rho, sigma_max, lam_g, lam_g_re, lam_g_im, "power-iter", "power-iter"


# =====================================================================
# 构造函数：按 g_type / mode / dim 组装 F, g, h0
# =====================================================================

def build_experiment(
    g_type: str,
    mode: str,
    sn_scale: float,
    dim: int,
    fire_rate: float,
    seed: int,
    device: torch.device
):
    """
    返回 (F_func, g_func, h0, notes_str, actual_dim)。
    F_func / g_func 接受展平或原始形状 tensor → 输出同维度 tensor。

    支持 g_type: mlp / conv / attn / nca / antisym / neg_real
    """
    torch.manual_seed(seed)
    notes = ""

    if g_type == "mlp":
        g_module = MLPg(d=dim).to(device)
        apply_sn_scale(g_module, sn_scale)
        h0 = torch.randn(dim, device=device)

        if mode == "residual":
            F_module = ResidualWrapper(g_module)
        else:
            F_module = PureWrapper(g_module)

        F_func = lambda h: F_module(h)
        g_func = lambda h: g_module(h)
        notes = f"MLPg d={dim} hidden={max(dim,64)}"

    elif g_type == "conv":
        # Conv 感知：拆成 C=dim//4, H=W=2（保证 C*H*W=dim 以内），小 d 易验
        C = max(1, dim // 16)
        H = W = max(2, int(math.isqrt(dim // C)))
        # 调整使 C*H*W == dim（可能有差，向上取整后记录）
        actual_dim = C * H * W
        if actual_dim != dim:
            notes = f"ConvNCAg: C={C} H={H} W={W} actual_dim={actual_dim}（原 dim={dim} 已调整）"
            dim = actual_dim
        g_module = ConvNCAg(C=C, H=H, W=W, hidden=max(C, 16)).to(device)
        apply_sn_scale(g_module, sn_scale)
        h0 = torch.randn(C, H, W, device=device)  # shape [C, H, W]

        if mode == "residual":
            F_module = ResidualWrapper(g_module)
        else:
            F_module = PureWrapper(g_module)

        F_func = lambda h: F_module(h)
        g_func = lambda h: g_module(h)
        notes = notes or f"ConvNCAg C={C} H={H} W={W}"

    elif g_type == "attn":
        # Attn：S=序列长，D=head_dim，S*D=dim
        D = max(8, dim // 4)
        S = max(2, dim // D)
        actual_dim = S * D
        if actual_dim != dim:
            notes = f"AttnResidualg: S={S} D={D} actual_dim={actual_dim}（原 dim={dim} 已调整）"
            dim = actual_dim
        g_module = AttnResidualg(S=S, D=D).to(device)
        apply_sn_scale(g_module, sn_scale)
        h0 = torch.randn(S, D, device=device)  # [S, D]

        if mode == "residual":
            F_module = ResidualWrapper(g_module)
        else:
            F_module = PureWrapper(g_module)

        F_func = lambda h: F_module(h)
        g_func = lambda h: g_module(h)
        notes = notes or f"AttnResidualg S={S} D={D}"

    elif g_type == "nca":
        # R0：复用 NCAStep（确定性 fire，fire_rate 参数化）
        try:
            from src.models.nca_predictor import NCAStep
        except ImportError:
            raise ImportError(
                "无法 import NCAStep，请确保脚本从 NCA-JEPA 根目录运行 "
                "或 ijepa/ 已在 PYTHONPATH。"
            )
        # 展平 dim → C=dim, H=W=1（纯 per-cell 感知，最简 NCA 形式）
        # 或：C=sqrt(dim), H=W=sqrt(dim)（更接近实际用法）
        C = max(1, int(math.isqrt(dim)))
        if C * C != dim:
            # 回退到最大完全平方数 ≤ dim
            C = int(math.isqrt(dim))
            while C * C > dim:
                C -= 1
        H = W = C
        actual_dim = C * H * W  # = C^3
        # 重置 dim
        actual_dim = C * C * C   # NCA: [C, H, W] 展平 = C*H*W，H=W=C
        # 简化：C=4, H=W=4 → dim=64，或 C=8, H=W=8 → dim=512
        # 当 dim 不是完全立方数时，取 C=int(dim^(1/3))
        # 实际：NCAStep 取 [B=1, C, H, W]，这里 H=W=4 C=dim//16
        C2 = max(1, dim // 16)
        H2 = W2 = 4
        actual_dim2 = C2 * H2 * W2
        g_module = NCAStep(dim=C2, hidden=max(C2 * 2, 16),
                           fire_rate=0.0,   # 确定性：fire_rate=0 → fire mask 全 1
                           spectral=False).to(device)
        # NCAStep.__init__ 将 fc1 零初始化（训练起步约定）。
        # 探针需要随机权重才能测非零 J_g，用 trunc_normal_ 覆盖（与 NCAPredictor._init_weights 不碰 Conv 的约定不同，
        # 这里是探针脚本，明确覆盖，模拟训练后状态）。
        nn.init.trunc_normal_(g_module.fc1.weight, std=0.02)
        apply_sn_scale(g_module, sn_scale)

        # NCAStep.forward 接受 [B, C, H, W]，这里 B=1
        # 包装成 [C, H, W] 接口
        def nca_g(h_chw: torch.Tensor) -> torch.Tensor:
            """NCA g：输入 [C,H,W]，输出 [C,H,W]（delta，不含 h 本身）。"""
            x = h_chw.unsqueeze(0)  # [1, C, H, W]
            out = g_module(x)       # NCAStep 返回 h + fire*delta，这里 fire=1
            # g(h) = out - h（剥离 residual 部分，仅返回 delta）
            return (out - x).squeeze(0)

        def nca_F_residual(h_chw: torch.Tensor) -> torch.Tensor:
            return h_chw + nca_g(h_chw)

        def nca_F_pure(h_chw: torch.Tensor) -> torch.Tensor:
            return nca_g(h_chw)

        h0 = torch.randn(C2, H2, W2, device=device)

        if mode == "residual":
            F_func = nca_F_residual
            g_func = nca_g
        else:
            F_func = nca_F_pure
            g_func = nca_g

        notes = (f"NCAStep C={C2} H={H2} W={W2} actual_dim={actual_dim2} "
                 f"fire_rate=0(确定性) sn_scale={sn_scale}")
        dim = actual_dim2

    elif g_type == "antisym":
        # [证伪专项 a] 反对称权重线性 g：W = A - Aᵀ，特征值纯虚 ±βi
        # 理论预测：ρ(I+W) = max_k √(1+βk²) > 1，claim 应成立
        g_module = AntiSymLinearG(d=dim).to(device)
        apply_sn_scale(g_module, sn_scale)
        h0 = torch.randn(dim, device=device)

        if mode == "residual":
            F_module = ResidualWrapper(g_module)
        else:
            F_module = PureWrapper(g_module)

        F_func = lambda h: F_module(h)
        g_func = lambda h: g_module(h)
        # 记录缩放后的实际 SN（供 notes 展示）
        actual_sn = _sigma_max_weight(g_module.linear.weight)
        notes = (f"AntiSymLinearG d={dim} W=A-Aᵀ(纯虚特征值) "
                 f"sn_scale={sn_scale} actual_sn={actual_sn:.4f} "
                 f"[证伪专项a: 复特征值反对称]")

    elif g_type == "neg_real":
        # [证伪专项 b] 负实特征值接近 -1 的线性 g：W = Q·diag(λ)·Qᵀ
        # λ 含 -0.80, -0.85, -0.90, -0.95（交替）
        # SN 约束（apply_sn_scale）会对 W 做 W←c·W/σ_max(W)
        # 实对称 W 的 σ_max = max|λ| = 0.95（SN缩放前）
        # apply_sn_scale(g, 1.0) 后：最负特征值 = -0.95/0.95 ≈ -1.0
        # apply_sn_scale(g, 0.9) 后：最负特征值 = -0.95*0.9/0.95 = -0.9
        # 关键测试：SN<1 时，λ_g_min 能否到 ≤ -1？
        #   → SN=1.0 时 λ_g_min ≈ -1.0，则 1+λ_g_min ≈ 0，ρ(I+W) ≈ 0 < 1？
        #   → 这是 claim 最危险的反例候选。
        # 注意：apply_sn_scale 是按 σ_max(W) 缩放，实对称矩阵 σ_max = max|λ|
        # 所以 sn_scale=1.0 后 max|λ| = 1.0，最负特征值 = -0.95/0.95 * 1.0 = -1.0
        # λ(I+W) 中对应分量 = 1 + (-1.0) = 0.0，ρ 会极小接近 0！
        # sn_scale=0.9 时：最负 λ_g = -0.9，λ(I+W) = 0.1，ρ 仍 < 1
        # sn_scale=1.5 时：最负 λ_g = -1.5，λ(I+W) = -0.5，|λ(I+W)|=0.5 < 1
        # → 当 |λ_g_min| < 1（即 sn_scale * 0.95/0.95 < 1 → sn_scale < 1）时：
        #   最负 λ(I+W) = 1 - sn_scale > 0，ρ < 1 仍可能
        # 这直接检验"SN<1 且纯线性实对称"是否 ρ<1（这是 DEQ 收缩的经典条件）
        g_module = NegRealLinearG(d=dim).to(device)
        apply_sn_scale(g_module, sn_scale)
        h0 = torch.randn(dim, device=device)

        if mode == "residual":
            F_module = ResidualWrapper(g_module)
        else:
            F_module = PureWrapper(g_module)

        F_func = lambda h: F_module(h)
        g_func = lambda h: g_module(h)
        actual_sn = _sigma_max_weight(g_module.linear.weight)
        # 理论最危险点（SN缩放后最负特征值）
        # 原始 max|λ| = 0.95，缩放后 max|λ| = actual_sn
        # 最负 λ_g ≈ -actual_sn（因原始最负 = -0.95 = -max|λ|）
        theoretical_min_lambda_g = -actual_sn
        notes = (f"NegRealLinearG d={dim} λ_g∈{{-0.80~-0.95,+0.10}} "
                 f"sn_scale={sn_scale} actual_sn={actual_sn:.4f} "
                 f"理论最负λ_g≈{theoretical_min_lambda_g:.4f} "
                 f"理论ρ(I+W)≈{max(0.0, 1+theoretical_min_lambda_g):.4f} "
                 f"[证伪专项b: 负实特征值接近-1，claim最危险反例候选]")

    else:
        raise ValueError(f"未知 g_type={g_type}，支持: mlp/conv/attn/nca/antisym/neg_real")

    return F_func, g_func, h0, notes, dim


# =====================================================================
# 单次 run
# =====================================================================

def run_one(
    run_id: str,
    g_type: str,
    mode: str,
    sn_scale: float,
    dim: int,
    seed: int,
    fire_rate: float,
    device: torch.device,
    verbose: bool = True
) -> dict:
    """跑一次谱分析，返回结果 dict。"""
    F_func, g_func, h0, notes, actual_dim = build_experiment(
        g_type=g_type, mode=mode, sn_scale=sn_scale,
        dim=dim, fire_rate=fire_rate, seed=seed, device=device
    )

    rho, sigma_max, lambda_g_max_mod, lambda_g_real, lambda_g_imag, rho_method, sigma_method = (
        analyze_spectral(F_func, g_func, h0, mode)
    )

    # 辅助：lambda_g_real/imag 保留 6 位，nan 直接写 nan
    def _fmt(v):
        return round(v, 6) if not (v != v) else float("nan")  # nan check

    row = dict(
        run_id=run_id,
        g_type=g_type,
        mode=mode,
        sn_scale=sn_scale,
        dim=actual_dim,
        seed=seed,
        rho=round(rho, 6),
        sigma_max=round(sigma_max, 6),
        lambda_g_max_mod=round(lambda_g_max_mod, 6),
        lambda_g_real=_fmt(lambda_g_real),
        lambda_g_imag=_fmt(lambda_g_imag),
        rho_method=rho_method,
        sigma_method=sigma_method,
        notes=notes,
    )

    if verbose:
        check = "OK" if rho <= sigma_max + 1e-4 else "FAIL(rho>sigma_max!)"
        lam_g_str = (f"{lambda_g_real:+.4f}{lambda_g_imag:+.4f}i"
                     if lambda_g_real == lambda_g_real  # not nan
                     else "nan")
        def _safe_print(s: str) -> None:
            """Windows GBK 终端安全打印：无法编码的字符替换为 '?'。"""
            print(s.encode(sys.stdout.encoding or "utf-8", errors="replace")
                    .decode(sys.stdout.encoding or "utf-8", errors="replace"))

        _safe_print(f"  [{run_id}] {g_type}/{mode}/sn={sn_scale}/d={actual_dim}/seed={seed}")
        _safe_print(f"    rho={rho:.5f} ({rho_method})  sigma_max={sigma_max:.5f} ({sigma_method})")
        _safe_print(f"    lam_g_mod={lambda_g_max_mod:.5f}  lam_g={lam_g_str}  rho<=sigma_max: {check}")
        _safe_print(f"    notes: {notes}")

    return row


# =====================================================================
# 最小可跑集：4 个 runs
# =====================================================================

MINIMAL_RUNS = [
    # R0: NCAStep（官方 NCA，d≈dim//16*16 小值），确定性 fire
    dict(run_id="R0-NCA-res", g_type="nca", mode="residual",
         sn_scale=1.0, dim=64, seed=42, fire_rate=0.0),
    # R1: MLP residual + SN
    dict(run_id="R1-MLP-res", g_type="mlp", mode="residual",
         sn_scale=1.0, dim=64, seed=42, fire_rate=0.5),
    # R4: MLP pure (DEQ 对照)，g 内部结构与 R1 完全相同
    dict(run_id="R4-DEQ-ctrl", g_type="mlp", mode="pure",
         sn_scale=1.0, dim=64, seed=42, fire_rate=0.5),
    # R5: MLP residual + SN sweep（6 个 sn_scale）
    *[
        dict(run_id=f"R5-SN-sweep-c{c}", g_type="mlp", mode="residual",
             sn_scale=c, dim=64, seed=42, fire_rate=0.5)
        for c in [0.3, 0.5, 0.7, 1.0, 1.5, 2.0]
    ],
]


# =====================================================================
# 完整 run_set（含跨模型族）
# =====================================================================

FULL_RUNS = MINIMAL_RUNS + [
    # Conv g
    dict(run_id="R2-Conv-res", g_type="conv", mode="residual",
         sn_scale=1.0, dim=64, seed=42, fire_rate=0.5),
    dict(run_id="R3-Conv-pure", g_type="conv", mode="pure",
         sn_scale=1.0, dim=64, seed=42, fire_rate=0.5),
    # Attn g
    dict(run_id="R6-Attn-res", g_type="attn", mode="residual",
         sn_scale=1.0, dim=64, seed=42, fire_rate=0.5),
    dict(run_id="R7-Attn-pure", g_type="attn", mode="pure",
         sn_scale=1.0, dim=64, seed=42, fire_rate=0.5),
    # 更大 dim（幂迭代路径）
    dict(run_id="R8-MLP-res-d256", g_type="mlp", mode="residual",
         sn_scale=1.0, dim=256, seed=42, fire_rate=0.5),
    dict(run_id="R9-MLP-pure-d256", g_type="mlp", mode="pure",
         sn_scale=1.0, dim=256, seed=42, fire_rate=0.5),
]


# =====================================================================
# 证伪专项 run_set（v2 新增：主动攻击 claim 的危险 case）
# =====================================================================

# 1. Conv 修复重测（kaiming_normal_ 已在 ConvNCAg.__init__ 里修复）
_FALSIFY_CONV = [
    dict(run_id="F1-Conv-res-fixed", g_type="conv", mode="residual",
         sn_scale=1.0, dim=64, seed=42, fire_rate=0.0,
         _note_override="[v2修复] kaiming_normal_初始化，J_g应非零"),
    dict(run_id="F2-Conv-pure-fixed", g_type="conv", mode="pure",
         sn_scale=1.0, dim=64, seed=42, fire_rate=0.0,
         _note_override="[v2修复] kaiming_normal_初始化，DEQ对照"),
]

# 2. 反对称权重（复纯虚特征值）：SN<1 和 SN=1 各测
_FALSIFY_ANTISYM = [
    dict(run_id="F3-AntiSym-res-sn1.0", g_type="antisym", mode="residual",
         sn_scale=1.0, dim=64, seed=42, fire_rate=0.0),
    dict(run_id="F4-AntiSym-res-sn0.5", g_type="antisym", mode="residual",
         sn_scale=0.5, dim=64, seed=42, fire_rate=0.0),
    dict(run_id="F5-AntiSym-pure-sn1.0", g_type="antisym", mode="pure",
         sn_scale=1.0, dim=64, seed=42, fire_rate=0.0),
]

# 3. 负实特征值接近 -1（最危险反例候选）：多种 SN 缩放
# sn_scale=1.0 时理论 λ_g_min ≈ -1.0 → λ(I+W)_min ≈ 0 → ρ 极小
# sn_scale=0.9 时 λ_g_min ≈ -0.9 → λ(I+W)_min = 0.1 → ρ < 1
# sn_scale=1.5 时 λ_g_min ≈ -1.5 → λ(I+W)_min = -0.5 → |.| = 0.5 < 1
# → 这三个 residual run 如果 ρ<1，则是 claim 直接反例！
_FALSIFY_NEGREAL = [
    dict(run_id="F6-NegReal-res-sn0.9", g_type="neg_real", mode="residual",
         sn_scale=0.9, dim=64, seed=42, fire_rate=0.0),
    dict(run_id="F7-NegReal-res-sn1.0", g_type="neg_real", mode="residual",
         sn_scale=1.0, dim=64, seed=42, fire_rate=0.0),
    dict(run_id="F8-NegReal-res-sn1.5", g_type="neg_real", mode="residual",
         sn_scale=1.5, dim=64, seed=42, fire_rate=0.0),
    dict(run_id="F9-NegReal-pure-sn1.0", g_type="neg_real", mode="pure",
         sn_scale=1.0, dim=64, seed=42, fire_rate=0.0),
]

# 4. 多 seed：mlp/attn/nca 各跑 seed=0,1,2，验 ρ≥1 稳健
_FALSIFY_MULTISEED = [
    dict(run_id=f"MS-{gt}-res-s{s}", g_type=gt, mode="residual",
         sn_scale=1.0, dim=64, seed=s, fire_rate=0.0)
    for gt in ["mlp", "attn", "nca"]
    for s in [0, 1, 2]
]

FALSIFY_RUNS = (
    _FALSIFY_CONV
    + _FALSIFY_ANTISYM
    + _FALSIFY_NEGREAL
    + _FALSIFY_MULTISEED
)


# =====================================================================
# CSV 输出
# =====================================================================

FIELDNAMES = [
    "run_id", "g_type", "mode", "sn_scale", "dim", "seed",
    "rho", "sigma_max", "lambda_g_max_mod",
    "lambda_g_real", "lambda_g_imag",
    "rho_method", "sigma_method", "notes"
]


def save_csv(rows: list, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n[写出] {out_path}  ({len(rows)} rows)")


# =====================================================================
# main
# =====================================================================

def main():
    p = argparse.ArgumentParser(
        description="NCA-JEPA 残差谱半径下界验证探针 (claim 拯救路线 A)"
    )
    p.add_argument("--g-type", default="mlp",
                   choices=["mlp", "conv", "attn", "nca", "antisym", "neg_real"],
                   help="g 模块类型（antisym/neg_real 为证伪专项）")
    p.add_argument("--mode", default="residual",
                   choices=["residual", "pure"],
                   help="residual=h+g(h) / pure=g(h) DEQ 对照")
    p.add_argument("--sn-scale", type=float, default=1.0,
                   help="受控重缩放强度 c（W←c·W/σ_max(W)）")
    p.add_argument("--dim", type=int, default=64,
                   help="特征维度（≤1024 用显式 eig，否则幂迭代）")
    p.add_argument("--seed", type=int, default=42,
                   help="单 seed（与 --seeds 互斥；--seeds 优先）")
    p.add_argument("--seeds", type=int, nargs="+", default=None,
                   help="多 seed 列表（如 --seeds 0 1 2）；单次模式下扫多 seed")
    p.add_argument("--fire-rate", type=float, default=0.0,
                   help="NCA fire_rate（conv/nca g_type 用；=0 确定性）")
    p.add_argument("--run-set", default=None,
                   choices=["minimal", "full", "falsify"],
                   help="预定义 run 列表；指定后忽略其他参数。"
                        "falsify=证伪专项（conv修复+复特征值+多seed）")
    p.add_argument("--smoke", action="store_true",
                   help="只跑 R0 NCA + R1 MLP residual 两个 run（smoke 验管线）")
    p.add_argument("--smoke-falsify", action="store_true",
                   help="smoke 证伪专项：F7-NegReal-res-sn1.0 + F3-AntiSym-res-sn1.0（2 runs）")
    p.add_argument("--out", default=None,
                   help="CSV 输出路径（默认 results/spectral_lower_bound/results.csv）")
    p.add_argument("--device", default="cpu")
    args = p.parse_args()

    device = torch.device(args.device)
    _HERE_ROOT = Path(__file__).resolve().parent.parent
    out_path = Path(args.out) if args.out else (
        _HERE_ROOT / "results" / "spectral_lower_bound" / "results.csv"
    )

    # 决定 run 列表
    if args.smoke:
        runs = [MINIMAL_RUNS[0], MINIMAL_RUNS[1]]  # R0 + R1 只
        print("=== SMOKE MODE: R0-NCA-res + R1-MLP-res ===\n")
    elif args.smoke_falsify:
        # 证伪专项 smoke：最危险的两个 case
        runs = [
            dict(run_id="SF1-NegReal-res-sn1.0", g_type="neg_real", mode="residual",
                 sn_scale=1.0, dim=64, seed=42, fire_rate=0.0),
            dict(run_id="SF2-Conv-res-fixed", g_type="conv", mode="residual",
                 sn_scale=1.0, dim=64, seed=42, fire_rate=0.0),
            dict(run_id="SF3-AntiSym-res-sn1.0", g_type="antisym", mode="residual",
                 sn_scale=1.0, dim=64, seed=42, fire_rate=0.0),
        ]
        print("=== SMOKE-FALSIFY MODE: NegReal+Conv-fixed+AntiSym (3 runs) ===\n")
    elif args.run_set == "minimal":
        runs = MINIMAL_RUNS
        print(f"=== run-set=minimal ({len(runs)} runs) ===\n")
    elif args.run_set == "full":
        runs = FULL_RUNS
        print(f"=== run-set=full ({len(runs)} runs) ===\n")
    elif args.run_set == "falsify":
        runs = FALSIFY_RUNS
        print(f"=== run-set=falsify ({len(runs)} runs, 证伪专项) ===\n")
    else:
        # 单次自定义（支持 --seeds 多 seed 扫）
        seeds_to_run = args.seeds if args.seeds else [args.seed]
        runs = []
        for s in seeds_to_run:
            runs.append(dict(
                run_id=f"custom-{args.g_type}-{args.mode}-sn{args.sn_scale}"
                       f"-d{args.dim}-s{s}",
                g_type=args.g_type,
                mode=args.mode,
                sn_scale=args.sn_scale,
                dim=args.dim,
                seed=s,
                fire_rate=args.fire_rate,
            ))
        if len(seeds_to_run) > 1:
            print(f"=== 单次自定义 run × {len(seeds_to_run)} seeds ===\n")
        else:
            print(f"=== 单次自定义 run ===\n")

    rows = []
    for r in runs:
        row = run_one(
            run_id=r["run_id"],
            g_type=r["g_type"],
            mode=r["mode"],
            sn_scale=r["sn_scale"],
            dim=r["dim"],
            seed=r["seed"],
            fire_rate=r.get("fire_rate", 0.0),
            device=device,
            verbose=True,
        )
        rows.append(row)

    save_csv(rows, out_path)

    def _sp(s: str) -> None:
        """安全打印：对无法在当前终端编码的字符用 '?' 替换。"""
        enc = sys.stdout.encoding or "utf-8"
        print(s.encode(enc, errors="replace").decode(enc, errors="replace"))

    # 简要结论打印
    _sp("\n=== Summary ===")
    for row in rows:
        # 判据：residual 模式 claim 说 rho>=1，pure/DEQ claim 说 rho<1（对照成立）
        # neg_real/antisym residual：如果 rho<1 -> claim 反例！
        rho_val = row["rho"]
        is_residual = (row["mode"] == "residual")
        if is_residual and rho_val >= 0.99:
            tag = "[CLAIM OK: rho>=1]"
        elif is_residual and rho_val < 0.99:
            tag = "[!!! CLAIM VIOLATED !!!: residual rho<1]"
        elif not is_residual and rho_val < 1.0:
            tag = "[CLAIM OK: pure rho<1]"
        else:
            tag = "[CHECK: pure rho>=1]"

        # lambda_g 实虚部（nan 时显示 N/A）
        lre = row.get("lambda_g_real", float("nan"))
        lim = row.get("lambda_g_imag", float("nan"))
        if lre == lre:  # not nan
            lam_str = f"lam_g={lre:+.4f}{lim:+.4f}i"
        else:
            lam_str = "lam_g=N/A(power-iter)"

        _sp(f"  {row['run_id']:38s}  rho={rho_val:.5f}  sigma={row['sigma_max']:.5f}"
            f"  {lam_str}  {tag}")

    # 多 seed 汇总（如果有同 g_type/mode/sn_scale 的多 seed runs）
    from collections import defaultdict
    multi_seed_groups = defaultdict(list)
    for row in rows:
        key = (row["g_type"], row["mode"], row["sn_scale"], row["dim"])
        multi_seed_groups[key].append(row["rho"])
    _sp("\n=== Multi-seed rho stats (groups with >=2 seeds) ===")
    any_printed = False
    for (gt, md, sn, d), rhos in multi_seed_groups.items():
        if len(rhos) >= 2:
            arr = np.array(rhos)
            _sp(f"  {gt}/{md}/sn={sn}/d={d}: "
                f"rho mean={arr.mean():.5f} std={arr.std():.5f} "
                f"min={arr.min():.5f} max={arr.max():.5f} (n={len(rhos)})")
            any_printed = True
    if not any_printed:
        _sp("  (no multi-seed groups)")


if __name__ == "__main__":
    main()
