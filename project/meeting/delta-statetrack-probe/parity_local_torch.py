"""
parity_local_torch.py — Delta Crux 1 本地快速初判（纯 PyTorch，零 FLA/triton 依赖）
===================================================================================
服务：gdn2vessel § delta 状态追踪命门 Crux 1 — 负特征值 delta rule 是否碾压对角 SSM 解 parity OOD

科学依据：Grazzi et al. 2411.12537
  "Unlocking State-Tracking in Linear RNNs Through Negative Eigenvalues"
  定理核心：对角 SSM（g_t ∈ (0,1)）无法 OOD 泛化 parity；
           delta rule 开负特征值（β∈(0,2)，特征值 1-β∈(-1,1) 可负）则可。

任务 = Parity（主判据）
  输入：随机 0/1 token 流 (B,T)
  标签：per-token 累积 XOR，token-level cross-entropy，vocab=2
  ★ 决定性指标 = OOD 长度泛化
    训练长度：均匀 [3, 40]
    评估长度：桶 40-64 / 64-128 / 128-256（报 acc）
    对角 SSM 理论预测：OOD acc → 0.5（chance）
    delta_neg    理论预测：OOD acc ≈ 1.0（保持）

三臂（唯一变量 = recurrence，backbone/容量/预算完全相同）
  diag       GLA 类 对角线性递推，g_t = sigmoid(·) ∈ (0,1)，应 OOD 崩
             S_t = diag(g_t) ⊙ S_{t-1} + k_t v_t^T   [d_state × d_v 矩阵态]
             o_t = S_t q_t
  delta_neg  beta ∈ (0,2) → 特征值 (1-beta) ∈ (-1,1) 可负，应 OOD 过
             S_t = (I - beta_t k_t k_t^T) S_{t-1} + beta_t v_t k_t^T
             k_t L2-normalize，o_t = S_t q_t
  delta_pos  beta ∈ (0,1) → 特征值 (1-beta) ∈ (0,1) 始终正，消融：应也崩
             证「负特征值才是关键」

容量统一（head_dim × head_dim = 16×16 = 256，单头，2 层）：
  diag     ：state = d_state × d_v = 16×16 矩阵（对角门 × 矩阵态）
  delta_neg：state = d_k × d_k = 16×16（Householder 反射更新）
  delta_pos：同 delta_neg

实现策略：naive 顺序循环 over T（无 triton，本地 RTX4070 8GB 跑 T≤256 足够快）

verdict 判据（preregistered）
  delta_neg 长桶 >0.9  → STATE_TRACKING_LIVE
  diag      长桶 ≤0.55 → DIAGONAL_FAIL（预期）
  delta_pos 长桶 ≤0.55 → 证负特征值必要性

sanity 断言（打印不 crash）
  delta_neg 训练内（3-40 长）acc 训完仍 <0.6 → 打印 IMPL_BUG_SUSPECT（定理保证能收敛）

Windows 规范
  DataLoader：multiprocessing_context='spawn'，pin_memory=False
  相关系数：纯 numpy，无 scipy
  路径：pathlib.Path，不用反斜杠字符串

依赖：torch + numpy（仅此两者）
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import random
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

# ---------------------------------------------------------------------------
# 输出目录
# ---------------------------------------------------------------------------
_HERE      = Path(__file__).resolve().parent
_OUT_DIR   = _HERE / "outputs"


# ===========================================================================
# Mixer 1：diag — 对角线性递推（GLA 类，预测 OOD 崩）
# ===========================================================================

class DiagMixer(nn.Module):
    """
    对角 SSM，单头，矩阵态 S: (d_k, d_v)。
    每步：
        q_t, k_t, v_t = linear projections of h_t    [d_k / d_k / d_v]
        g_t = sigmoid(linear(h_t))                    [(d_k,)，各向同性衰减门]
        S_t = diag(g_t) @ S_{t-1} + outer(k_t, v_t)  [d_k × d_v]
        o_t = S_t^T q_t                               [d_v]
    注意：g_t ∈ (0,1) 使得所有特征值 ∈ (0,1)，理论无法完成 parity OOD。
    """

    def __init__(self, d_model: int, d_state: int):
        super().__init__()
        self.d_model = d_model
        self.d_state = d_state   # = d_k = d_v（容量统一）
        self.q_proj = nn.Linear(d_model, d_state, bias=False)
        self.k_proj = nn.Linear(d_model, d_state, bias=False)
        self.v_proj = nn.Linear(d_model, d_state, bias=False)
        self.g_proj = nn.Linear(d_model, d_state, bias=True)   # 衰减门
        self.o_proj = nn.Linear(d_state, d_model, bias=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: (B, T, d_model) → (B, T, d_model)"""
        B, T, _ = x.shape
        d = self.d_state

        q = self.q_proj(x)   # (B,T,d)
        k = self.k_proj(x)   # (B,T,d)
        v = self.v_proj(x)   # (B,T,d)
        g = torch.sigmoid(self.g_proj(x))  # (B,T,d)，∈ (0,1)

        # 初始化矩阵态 S: (B, d_k, d_v) = (B, d, d)
        S = torch.zeros(B, d, d, dtype=x.dtype, device=x.device)
        outs = []
        for t in range(T):
            g_t = g[:, t, :]          # (B, d)
            k_t = k[:, t, :]          # (B, d)
            v_t = v[:, t, :]          # (B, d)
            q_t = q[:, t, :]          # (B, d)

            # S_t = diag(g_t) S_{t-1} + k_t v_t^T
            # diag(g_t) @ S  →  g_t[:, :, None] * S
            S = g_t.unsqueeze(-1) * S + torch.bmm(
                k_t.unsqueeze(-1),   # (B, d, 1)
                v_t.unsqueeze(-2),   # (B, 1, d)
            )
            # o_t = S^T q_t  →  S: (B,d_k,d_v), q: (B,d_k) → o: (B,d_v)
            o_t = torch.bmm(
                S.transpose(1, 2),   # (B, d_v, d_k)
                q_t.unsqueeze(-1),   # (B, d_k, 1)
            ).squeeze(-1)             # (B, d_v)
            outs.append(o_t)

        out = torch.stack(outs, dim=1)   # (B, T, d)
        return self.o_proj(out)           # (B, T, d_model)


# ===========================================================================
# Mixer 2：delta_neg — delta rule + 负特征值（β∈(0,2)，预测 OOD 过）
# ===========================================================================

class DeltaNegMixer(nn.Module):
    """
    Delta rule，beta ∈ (0,2)，特征值 (1-beta) ∈ (-1,1) 可负。
    对照 Grazzi et al. / DeltaNet 官方实现：
        k_t  L2-normalize（使 I - beta*k*k^T 是干净反射，eigenvalue = 1-beta）
        beta_t = 2 * sigmoid(linear(h_t))   ∈ (0,2)
        S_t = (I - beta_t * k_t k_t^T) S_{t-1} + beta_t * v_t k_t^T
        o_t = S_t q_t
    """

    def __init__(self, d_model: int, d_state: int):
        super().__init__()
        self.d_model = d_model
        self.d_state = d_state
        self.q_proj    = nn.Linear(d_model, d_state, bias=False)
        self.k_proj    = nn.Linear(d_model, d_state, bias=False)
        self.v_proj    = nn.Linear(d_model, d_state, bias=False)
        self.beta_proj = nn.Linear(d_model, 1, bias=True)    # 标量 beta
        self.o_proj    = nn.Linear(d_state, d_model, bias=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: (B, T, d_model) → (B, T, d_model)"""
        B, T, _ = x.shape
        d = self.d_state

        q    = self.q_proj(x)                                # (B,T,d)
        k_raw= self.k_proj(x)                                # (B,T,d)，待 normalize
        v    = self.v_proj(x)                                # (B,T,d)
        # L2 normalize k（Grazzi 2411.12537 §3 要求）
        k    = F.normalize(k_raw, p=2, dim=-1)               # (B,T,d)，||k_t||=1
        # beta ∈ (0,2) — 负特征值关键
        beta = 2.0 * torch.sigmoid(self.beta_proj(x))        # (B,T,1)，∈(0,2)

        S = torch.zeros(B, d, d, dtype=x.dtype, device=x.device)
        outs = []
        for t in range(T):
            k_t    = k[:, t, :]         # (B,d)
            v_t    = v[:, t, :]         # (B,d)
            q_t    = q[:, t, :]         # (B,d)
            beta_t = beta[:, t, :]      # (B,1)

            # Householder-like 更新：S_t = (I - beta*k*k^T) S_{t-1} + beta*v*k^T
            # = S_{t-1} - beta * k*(k^T S_{t-1}) + beta * v * k^T
            # 先算 k^T S_{t-1}：  kS: (B, 1, d) @ (B, d, d) = (B, 1, d)
            kS = torch.bmm(k_t.unsqueeze(1), S)              # (B,1,d)
            # S_{t-1} - beta * outer(k, kS)
            # k: (B,d,1), kS: (B,1,d) → (B,d,d)
            S = S - beta_t.unsqueeze(-1) * torch.bmm(
                k_t.unsqueeze(-1), kS                        # (B,d,d)
            ) + beta_t.unsqueeze(-1) * torch.bmm(
                v_t.unsqueeze(-1),                           # (B,d,1)
                k_t.unsqueeze(-2),                           # (B,1,d)
            )
            # o_t = S q_t
            o_t = torch.bmm(S, q_t.unsqueeze(-1)).squeeze(-1)  # (B,d)
            outs.append(o_t)

        out = torch.stack(outs, dim=1)   # (B,T,d)
        return self.o_proj(out)           # (B,T,d_model)


# ===========================================================================
# Mixer 3：delta_pos — delta rule，beta ∈ (0,1)（始终正特征值，消融）
# ===========================================================================

class DeltaPosMixer(nn.Module):
    """
    Delta rule，beta ∈ (0,1)，特征值 (1-beta) ∈ (0,1) 始终正。
    与 delta_neg 唯一差别：beta = sigmoid(·) ∈ (0,1)（不乘2）。
    消融对照：预测 OOD 崩 → 证「负特征值才是关键」。
    """

    def __init__(self, d_model: int, d_state: int):
        super().__init__()
        self.d_model = d_model
        self.d_state = d_state
        self.q_proj    = nn.Linear(d_model, d_state, bias=False)
        self.k_proj    = nn.Linear(d_model, d_state, bias=False)
        self.v_proj    = nn.Linear(d_model, d_state, bias=False)
        self.beta_proj = nn.Linear(d_model, 1, bias=True)
        self.o_proj    = nn.Linear(d_state, d_model, bias=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: (B, T, d_model) → (B, T, d_model)"""
        B, T, _ = x.shape
        d = self.d_state

        q     = self.q_proj(x)
        k_raw = self.k_proj(x)
        v     = self.v_proj(x)
        k     = F.normalize(k_raw, p=2, dim=-1)
        # beta ∈ (0,1) — 始终正特征值（消融）
        beta  = torch.sigmoid(self.beta_proj(x))              # (B,T,1)，∈(0,1)

        S = torch.zeros(B, d, d, dtype=x.dtype, device=x.device)
        outs = []
        for t in range(T):
            k_t    = k[:, t, :]
            v_t    = v[:, t, :]
            q_t    = q[:, t, :]
            beta_t = beta[:, t, :]

            kS = torch.bmm(k_t.unsqueeze(1), S)
            S = S - beta_t.unsqueeze(-1) * torch.bmm(
                k_t.unsqueeze(-1), kS
            ) + beta_t.unsqueeze(-1) * torch.bmm(
                v_t.unsqueeze(-1),
                k_t.unsqueeze(-2),
            )
            o_t = torch.bmm(S, q_t.unsqueeze(-1)).squeeze(-1)
            outs.append(o_t)

        out = torch.stack(outs, dim=1)
        return self.o_proj(out)


# ===========================================================================
# FFN 块
# ===========================================================================

class FFN(nn.Module):
    def __init__(self, d_model: int, expand: int = 4):
        super().__init__()
        self.fc1 = nn.Linear(d_model, d_model * expand, bias=False)
        self.fc2 = nn.Linear(d_model * expand, d_model, bias=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.fc2(F.gelu(self.fc1(x)))


# ===========================================================================
# 2 层 backbone（pre-norm residual）
# ===========================================================================

class ParityBackbone(nn.Module):
    """
    2 层：每层 = pre-norm residual mixer + pre-norm residual FFN
      x = x + mixer(LN(x))
      x = x + FFN(LN(x))
    """

    def __init__(self, d_model: int, mixer_cls, d_state: int, n_layers: int = 2):
        super().__init__()
        self.n_layers    = n_layers
        self.mixer_norms = nn.ModuleList([nn.LayerNorm(d_model) for _ in range(n_layers)])
        self.ffn_norms   = nn.ModuleList([nn.LayerNorm(d_model) for _ in range(n_layers)])
        self.mixers      = nn.ModuleList([mixer_cls(d_model, d_state) for _ in range(n_layers)])
        self.ffns        = nn.ModuleList([FFN(d_model) for _ in range(n_layers)])

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        for i in range(self.n_layers):
            x = x + self.mixers[i](self.mixer_norms[i](x))
            x = x + self.ffns[i](self.ffn_norms[i](x))
        return x


# ===========================================================================
# 完整模型（embed → backbone → head）
# ===========================================================================

class ParityModel(nn.Module):
    """Embedding(2,d) → ParityBackbone → Linear(d,2)，weight tying。"""

    def __init__(self, vocab_size: int, d_model: int, backbone: ParityBackbone):
        super().__init__()
        self.embed    = nn.Embedding(vocab_size, d_model)
        self.backbone = backbone
        self.head     = nn.Linear(d_model, vocab_size, bias=False)
        self.head.weight = self.embed.weight   # weight tying

    def forward(self, ids: torch.Tensor) -> torch.Tensor:
        """ids: (B,T) long → logits: (B,T,vocab_size)"""
        x = self.embed(ids)      # (B,T,d_model)
        x = self.backbone(x)     # (B,T,d_model)
        return self.head(x)       # (B,T,vocab_size)


# ===========================================================================
# Parity 任务生成
# ===========================================================================

def build_parity_batch(
    B: int,
    T: int,
    device: torch.device,
    rng: np.random.Generator,
) -> Tuple[torch.Tensor, torch.Tensor]:
    """
    tokens:  (B,T) ∈ {0,1}，random
    labels:  (B,T)，labels[t] = XOR(tokens[0..t])（前缀 parity）
    纯 numpy 生成，转 torch。
    """
    tokens = rng.integers(0, 2, size=(B, T), dtype=np.int64)
    parity = np.cumsum(tokens, axis=1) % 2
    return (
        torch.from_numpy(tokens).to(device),
        torch.from_numpy(parity).to(device),
    )


# ===========================================================================
# OOD 评估桶
# ===========================================================================

_EVAL_BUCKETS = [
    ("40-64",   40,  64),
    ("64-128",  64,  128),
    ("128-256", 128, 256),
]


# ===========================================================================
# LR 调度（cosine + warmup）
# ===========================================================================

class CosineWarmup:
    def __init__(self, opt, total_steps: int, warmup_steps: int, base_lr: float):
        self.opt          = opt
        self.total_steps  = total_steps
        self.warmup_steps = max(1, warmup_steps)
        self.base_lr      = base_lr

    def step(self, s: int) -> None:
        if s < self.warmup_steps:
            lr = self.base_lr * s / self.warmup_steps
        else:
            prog = (s - self.warmup_steps) / max(1, self.total_steps - self.warmup_steps)
            lr   = self.base_lr * 0.5 * (1.0 + math.cos(math.pi * prog))
        for pg in self.opt.param_groups:
            pg["lr"] = lr


# ===========================================================================
# 训练单臂
# ===========================================================================

_ARM_CLS = {
    "diag":      DiagMixer,
    "delta_neg": DeltaNegMixer,
    "delta_pos": DeltaPosMixer,
}


def train_one_arm(
    arm_name: str,
    seed: int,
    d_model: int,
    d_state: int,
    n_layers: int,
    steps: int,
    lr: float,
    warmup_steps: int,
    batch_size: int,
    train_lo: int,
    train_hi: int,
    n_eval_per_bucket: int,
    n_eval_len_per_bucket: int,
    context_len: int,
    device: torch.device,
    log_every: int,
) -> Dict:
    """
    训练一组 (arm, seed)，返回各桶 OOD acc。
    """
    torch.manual_seed(seed)
    np.random.seed(seed)
    random.seed(seed)
    rng = np.random.default_rng(seed)

    mixer_cls = _ARM_CLS[arm_name]
    backbone  = ParityBackbone(d_model, mixer_cls, d_state, n_layers)
    model     = ParityModel(vocab_size=2, d_model=d_model, backbone=backbone).to(device)

    param_count = sum(p.numel() for p in model.parameters())
    print(f"  [{arm_name}|seed={seed}] params={param_count:,}  device={device}")

    opt   = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-2, betas=(0.9, 0.999))
    sched = CosineWarmup(opt, steps, warmup_steps, lr)

    # ---- 训练 ----
    model.train()
    for s in range(1, steps + 1):
        sched.step(s)
        T = int(rng.integers(train_lo, train_hi + 1))
        ids, labels = build_parity_batch(batch_size, T, device, rng)
        logits = model(ids)                               # (B,T,2)
        B2, T2, V = logits.shape
        loss = F.cross_entropy(
            logits.reshape(B2 * T2, V),
            labels.reshape(B2 * T2),
            ignore_index=-100,
        )
        opt.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()

        if s % log_every == 0 or s == steps:
            print(f"  [{arm_name}|seed={seed}] step={s}/{steps}  loss={loss.item():.4f}  T={T}")

    # ---- sanity：in-distribution acc（训练范围内收敛检查）----
    model.eval()
    with torch.no_grad():
        _sanity_rng = np.random.default_rng(seed + 777)
        _sid, _slab = build_parity_batch(256, 30, device, _sanity_rng)
        _sl   = model(_sid)
        _sacc = ((_sl.argmax(-1) == _slab).float().mean()).item()
    if _sacc < 0.6:
        print(
            f"  [SANITY] {arm_name}|seed={seed}: in-dist acc={_sacc:.3f} < 0.6 → "
            f"IMPL_BUG_SUSPECT（定理保证 delta_neg 能收敛；diag/delta_pos 允许低）"
        )
    else:
        print(f"  [SANITY] {arm_name}|seed={seed}: in-dist acc={_sacc:.3f} OK")

    # ---- OOD 评估 ----
    bucket_acc: Dict[str, float] = {}
    with torch.no_grad():
        for bname, blo, bhi in _EVAL_BUCKETS:
            eval_rng  = np.random.default_rng(seed + 99999)
            lengths   = eval_rng.integers(blo, bhi + 1, size=n_eval_len_per_bucket)
            total_ok  = 0
            total_n   = 0
            per_batch = max(16, n_eval_per_bucket // n_eval_len_per_bucket)
            for ln in lengths:
                ln = min(int(ln), context_len)
                erng = np.random.default_rng(seed + 88888 + ln)
                eids, elabs = build_parity_batch(per_batch, ln, device, erng)
                logits_e = model(eids)
                preds    = logits_e.argmax(-1)
                mask     = (elabs != -100)
                total_ok += ((preds == elabs) & mask).sum().item()
                total_n  += mask.sum().item()
            acc = total_ok / max(total_n, 1)
            bucket_acc[bname] = acc
            tag = "LIVE" if acc > 0.90 else ("CHANCE" if acc <= 0.55 else "MID")
            print(
                f"  [{arm_name}|seed={seed}] OOD bucket {bname}: "
                f"acc={acc:.4f} [{tag}]"
            )

    long_acc = bucket_acc.get("128-256", float("nan"))
    return {
        "arm":            arm_name,
        "seed":           seed,
        "d_model":        d_model,
        "d_state":        d_state,
        "n_layers":       n_layers,
        "steps":          steps,
        "lr":             lr,
        "in_dist_acc":    float(_sacc),
        "long_acc_128_256": float(long_acc),
        "bucket_40_64":   float(bucket_acc.get("40-64",   float("nan"))),
        "bucket_64_128":  float(bucket_acc.get("64-128",  float("nan"))),
        "bucket_128_256": float(bucket_acc.get("128-256", float("nan"))),
    }


# ===========================================================================
# Verdict（纯 numpy，无 scipy）
# ===========================================================================

def print_verdict(results: List[Dict]) -> None:
    """聚合各臂长桶 acc，打印 verdict 表。"""
    from collections import defaultdict
    arm_long: Dict[str, List[float]] = defaultdict(list)
    for r in results:
        arm_long[r["arm"]].append(r["long_acc_128_256"])

    print("\n" + "="*60)
    print("VERDICT TABLE  (OOD 128-256 桶 acc，越高越好，chance=0.5)")
    print("-"*60)
    arm_means: Dict[str, float] = {}
    for arm in ["diag", "delta_pos", "delta_neg"]:
        accs = arm_long.get(arm, [])
        if not accs:
            print(f"  {arm:12s}: NO DATA")
            continue
        arr  = np.array(accs, dtype=float)
        mean = float(np.mean(arr))
        std  = float(np.std(arr, ddof=1) if len(arr) > 1 else 0.0)
        arm_means[arm] = mean
        if mean > 0.90:
            tag = "STATE_TRACKING_LIVE ✓"
        elif mean <= 0.55:
            tag = "DIAGONAL_FAIL / CHANCE"
        else:
            tag = f"AMBIGUOUS ({mean:.3f})"
        print(f"  {arm:12s}: mean={mean:.4f} ± {std:.4f}  → {tag}")

    print("-"*60)
    # 一行总结
    dn   = arm_means.get("delta_neg", float("nan"))
    diag = arm_means.get("diag",      float("nan"))
    dp   = arm_means.get("delta_pos", float("nan"))

    if math.isnan(dn) or math.isnan(diag):
        summary = "数据不完整，暂无总结"
    elif dn > 0.90 and diag <= 0.55:
        crush = "碾压"
        summary = (
            f"delta_neg={dn:.3f}  diag={diag:.3f}  delta_pos={dp:.3f}"
            f" → 负特征值 delta {crush} 对角 ✓"
        )
    elif dn > 0.90 and diag > 0.55:
        summary = (
            f"delta_neg={dn:.3f}  diag={diag:.3f}  delta_pos={dp:.3f}"
            f" → delta_neg LIVE 但 diag 未完全崩（检查容量/训练是否均衡）"
        )
    elif dn <= 0.55:
        summary = (
            f"delta_neg={dn:.3f}  diag={diag:.3f}  delta_pos={dp:.3f}"
            f" → 负特征值 delta 未碾压对角 ⚠ 检查 IMPL_BUG_SUSPECT"
        )
    else:
        summary = (
            f"delta_neg={dn:.3f}  diag={diag:.3f}  delta_pos={dp:.3f}"
            f" → 结果 AMBIGUOUS（建议提高 steps 或检查实现）"
        )
    print(f"\n  总结：{summary}")
    print("="*60)

    # 消融：delta_pos vs delta_neg
    if not math.isnan(dp) and not math.isnan(dn):
        if dp <= 0.55 and dn > 0.90:
            print(
                "  消融结论：delta_pos FAIL（正特征值不够）& delta_neg LIVE"
                " → 负特征值是 parity OOD 泛化的必要条件 ✓"
            )
        elif dp > 0.90:
            print(
                "  消融结论：delta_pos 也 LIVE — 可能 steps 不够 diag 崩，"
                "或 beta 未被正确约束到 (0,1)，请检查实现"
            )


# ===========================================================================
# CLI
# ===========================================================================

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "parity_local_torch.py — Delta Crux 1 本地初判（纯 PyTorch，无 FLA/triton）\n"
            "服务 gdn2vessel § delta 状态追踪命门\n\n"
            "快跑命令（3000步，分钟级）：\n"
            "  python parity_local_torch.py --steps 3000 --device cuda\n\n"
            "烟测（验管路，秒级）：\n"
            "  python parity_local_torch.py --smoke --device cpu\n\n"
            "完整三臂（默认）：\n"
            "  python parity_local_torch.py --arms diag delta_neg delta_pos\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # 臂
    p.add_argument(
        "--arms", nargs="+",
        default=["diag", "delta_neg", "delta_pos"],
        choices=["diag", "delta_neg", "delta_pos"],
        help="要跑的臂（默认三臂全跑）",
    )

    # 架构（极小容量，本地快跑）
    p.add_argument("--d_model",  type=int, default=64,  help="模型宽度（默认 64，本地快）")
    p.add_argument("--d_state",  type=int, default=16,  help="状态维（默认 16，矩阵态 16×16=256）")
    p.add_argument("--n_layers", type=int, default=2,   help="层数（默认 2，Grazzi 对齐）")

    # 训练
    p.add_argument("--steps",        type=int,   default=3000, help="训练步数（默认 3000，分钟级）")
    p.add_argument("--lr",           type=float, default=1e-3, help="学习率（默认 1e-3）")
    p.add_argument("--warmup_steps", type=int,   default=300,  help="warmup 步数（默认 300）")
    p.add_argument("--batch_size",   type=int,   default=128,  help="batch size（默认 128）")
    p.add_argument("--train_lo",     type=int,   default=3,    help="训练序列最短（默认 3）")
    p.add_argument("--train_hi",     type=int,   default=40,   help="训练序列最长（默认 40）")

    # 评估
    p.add_argument("--context_len",             type=int, default=256,
                   help="最大评估长度（默认 256）")
    p.add_argument("--n_eval_per_bucket",        type=int, default=256,
                   help="每桶评估序列数（默认 256）")
    p.add_argument("--n_eval_len_per_bucket",    type=int, default=8,
                   help="每桶采样的不同长度数（默认 8）")

    # seeds
    p.add_argument("--seeds", nargs="+", type=int, default=[0],
                   help="随机种子列表（默认 [0]，多种子加 1 2）")

    # 输出
    p.add_argument("--out_dir", type=str,
                   default=str(_OUT_DIR),
                   help="输出目录（CSV + verdict JSON）")

    # flags
    p.add_argument("--smoke",  action="store_true",
                   help="烟测：steps=100, batch=32, seeds=[0], 仅验管路")
    p.add_argument("--device", type=str, default="cuda",
                   help="运行设备（cuda 或 cpu，默认 cuda）")
    p.add_argument("--log_every", type=int, default=200,
                   help="每 N 步打印 loss（默认 200）")

    return p.parse_args()


# ===========================================================================
# main
# ===========================================================================

def main() -> None:
    args = parse_args()

    # smoke mode 覆盖
    if args.smoke:
        args.steps                   = 100
        args.batch_size              = 32
        args.seeds                   = [0]
        args.log_every               = 50
        args.n_eval_per_bucket       = 64
        args.n_eval_len_per_bucket   = 4
        args.context_len             = 64
        print(
            f"[parity_local] SMOKE MODE: steps=100 batch=32 seeds=[0] "
            f"context_len=64 — 仅验管路，不保证模型收敛"
        )

    # device
    if args.device == "cuda":
        if not torch.cuda.is_available():
            print("[parity_local] WARNING: cuda 不可用，退回 cpu", file=sys.stderr)
            device = torch.device("cpu")
        else:
            device = torch.device("cuda")
    else:
        device = torch.device("cpu")
    print(f"[parity_local] device={device}  torch={torch.__version__}")

    # 输出目录
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path     = out_dir / "parity_local_results.csv"
    verdict_path = out_dir / "parity_local_verdict.json"

    fieldnames = [
        "arm", "seed", "d_model", "d_state", "n_layers",
        "steps", "lr", "in_dist_acc",
        "long_acc_128_256", "bucket_40_64", "bucket_64_128", "bucket_128_256",
    ]

    # 断点续跑：跳过已完成
    done_keys: set = set()
    if csv_path.exists():
        with open(csv_path, "r", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                done_keys.add((row["arm"], int(row["seed"])))
        print(f"[parity_local] 已有 {len(done_keys)} 条结果，跳过重复")

    fout       = open(csv_path, "a", newline="", encoding="utf-8")
    csv_writer = csv.DictWriter(fout, fieldnames=fieldnames)
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        csv_writer.writeheader()
    # 若文件已存在但没 header（追加模式）：如果 done_keys 空说明刚建，补 header
    if not done_keys:
        # 文件刚建或空 → 写 header
        fout.seek(0, 2)  # 确认在末尾
        if fout.tell() == 0:
            csv_writer.writeheader()
            fout.flush()

    all_results: List[Dict] = []
    total = len(args.arms) * len(args.seeds)
    done  = 0

    for arm in args.arms:
        for seed in args.seeds:
            if (arm, seed) in done_keys:
                print(f"[parity_local] skip {arm}|seed={seed}（已存在）")
                continue
            done += 1
            print(f"\n[parity_local] [{done}/{total}] arm={arm}  seed={seed}")
            r = train_one_arm(
                arm_name=arm,
                seed=seed,
                d_model=args.d_model,
                d_state=args.d_state,
                n_layers=args.n_layers,
                steps=args.steps,
                lr=args.lr,
                warmup_steps=args.warmup_steps,
                batch_size=args.batch_size,
                train_lo=args.train_lo,
                train_hi=args.train_hi,
                n_eval_per_bucket=args.n_eval_per_bucket,
                n_eval_len_per_bucket=args.n_eval_len_per_bucket,
                context_len=args.context_len,
                device=device,
                log_every=args.log_every,
            )
            all_results.append(r)
            csv_writer.writerow(r)
            fout.flush()
            print(
                f"  -> long_acc(128-256)={r['long_acc_128_256']:.4f} | "
                f"40-64={r['bucket_40_64']:.4f} | "
                f"64-128={r['bucket_64_128']:.4f}"
            )

    fout.close()
    print(f"\n[parity_local] 扫描完成。CSV: {csv_path}")

    if not all_results:
        print("[parity_local] 无新结果（全部已跳过）。读已有 CSV 出 verdict。")
        with open(csv_path, "r", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                all_results.append({
                    "arm":             row["arm"],
                    "seed":            int(row["seed"]),
                    "long_acc_128_256": float(row["long_acc_128_256"]),
                    "bucket_40_64":    float(row["bucket_40_64"]),
                    "bucket_64_128":   float(row["bucket_64_128"]),
                    "bucket_128_256":  float(row["bucket_128_256"]),
                })

    # Verdict
    print_verdict(all_results)

    # 写 JSON
    verdict_data = {
        "config": {
            "d_model":   args.d_model,
            "d_state":   args.d_state,
            "n_layers":  args.n_layers,
            "steps":     args.steps,
            "lr":        args.lr,
            "batch_size": args.batch_size,
            "train_lo":  args.train_lo,
            "train_hi":  args.train_hi,
        },
        "results": all_results,
    }
    with open(verdict_path, "w", encoding="utf-8") as f:
        json.dump(verdict_data, f, indent=2, ensure_ascii=False)
    print(f"[parity_local] verdict JSON: {verdict_path}")


if __name__ == "__main__":
    main()
