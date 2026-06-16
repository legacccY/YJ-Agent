"""
S3 -- 塌缩 canary (silent-bug 哨兵 #3)

权威定义: 03_pilot_NIH_ChestXray14.md §7.3
  "塌缩 canary: 嵌入 std/有效秩/KoLeo 低于阈值 -> flag
   (别把低 loss 当成功, JEPA 头号假阳性)"

JEPA 系训练最大的假阳性: loss 一路下降到很小, 看起来"训得很好",
但实际上是 representation collapse -- 所有 token 嵌入坍缩到同一个点
(或低维子空间), 预测变得"trivial" (预测一个常数就能让 L2 loss 很小)。

本哨兵提供三个互补的塌缩检测量, 全部基于 token 嵌入矩阵 E (N x D):
  1. std       -- 嵌入逐维标准差的均值 (全部坍缩到一点 -> std -> 0)
  2. effective rank -- 对协方差矩阵的奇异值做归一化后的"熵秩"
                      (信息分布在少数方向 -> rank 低; 即使 std 不为 0,
                       若所有方向退化成 1 个主方向, rank ~ 1)
  3. KoLeo entropy  -- 基于最近邻距离的熵估计 (DINOv2 用于防塌缩的
                      Kozachenko-Leonenko 微分熵估计量; 嵌入点彼此
                      靠得很近 -> 熵很低/很负)

可被训练脚本 import:
    from s3_collapse_canary import compute_canary, CANARY_THRESHOLDS

    canary = compute_canary(embeddings)  # embeddings: (N, D) Tensor
    if canary["flagged"]:
        print("WARNING: representation collapse detected:", canary)
"""

from __future__ import annotations

import torch


# 默认阈值 -- pilot §9 要求"取 A0 正常训练 50% 分位"作为阈值;
# 这里给出保守的兜底默认值, 训练脚本应在拿到 A0 baseline 的实际分布后
# 用 calibrate_thresholds() 或手动覆盖这些值。
CANARY_THRESHOLDS = {
    "std_min": 0.05,        # 嵌入逐维 std 的均值, 低于此值疑似坍缩
    "effective_rank_min": 2.0,  # 有效秩 (熵秩), 低于此值疑似坍缩到低维子空间
    "koleo_entropy_min": -5.0,  # KoLeo 微分熵估计, 过低 (很负) 表示样本点彼此极近
}


def _embedding_std(embeddings: torch.Tensor) -> float:
    """逐维标准差的均值 (跨样本维度计算 std, 再对各维度求平均)。"""
    return embeddings.std(dim=0, unbiased=False).mean().item()


def _effective_rank(embeddings: torch.Tensor, eps: float = 1e-12) -> float:
    """
    有效秩 (effective / entropy rank):
      对中心化嵌入做 SVD 得奇异值 sigma_i,
      归一化为概率分布 p_i = sigma_i / sum(sigma),
      有效秩 = exp(熵(p)) = exp(-sum p_i log p_i)。

    直觉: 若信息均匀分布在 D 个方向, p_i ~ 1/D, 熵 = log D, rank ~ D。
    若全部能量集中在 1 个方向, 熵 -> 0, rank -> 1。
    若全部坍缩到一点 (所有 sigma ~ 0), 返回 0 (退化情形)。
    """
    x = embeddings.float()
    x = x - x.mean(dim=0, keepdim=True)
    if x.shape[0] < 2:
        return 0.0
    try:
        s = torch.linalg.svdvals(x)
    except Exception:
        # 极端退化 (全 0 矩阵等) SVD 仍可工作, 但兜底防止异常崩溃
        return 0.0
    total = s.sum().item()
    if total < eps:
        return 0.0
    p = s / (s.sum() + eps)
    p = p.clamp_min(eps)
    entropy = -(p * p.log()).sum().item()
    return float(torch.exp(torch.tensor(entropy)).item())


def _koleo_entropy(embeddings: torch.Tensor, eps: float = 1e-8) -> float:
    """
    KoLeo (Kozachenko-Leonenko) 微分熵估计 (DINOv2 anti-collapse term 的核心量):
        H_hat = (1/N) * sum_i log(N * d_i) , 其中 d_i = 到最近邻的欧氏距离
    (常数项省略, 只取与"点是否分散"相关的部分)

    直觉: 若点彼此分散, 最近邻距离 d_i 较大, log 项较大 (熵高);
    若点彼此重合/极近 (塌缩), d_i -> 0, log(N*d_i) -> -inf (熵 -> 很负)。

    返回 float; 嵌入先做 L2 归一化 (与 DINOv2 实现一致, 在球面上算最近邻)。
    """
    x = embeddings.float()
    n = x.shape[0]
    if n < 2:
        return 0.0
    x = torch.nn.functional.normalize(x, dim=-1, eps=eps)
    # pairwise 欧氏距离
    dist = torch.cdist(x, x, p=2)  # (N, N)
    dist.fill_diagonal_(float("inf"))
    min_dist, _ = dist.min(dim=1)  # (N,)
    min_dist = min_dist.clamp_min(eps)
    h_hat = torch.log(n * min_dist).mean().item()
    return h_hat


def compute_canary(
    embeddings: torch.Tensor,
    thresholds: dict | None = None,
) -> dict:
    """
    计算塌缩 canary 三件套并与阈值比较。

    Parameters
    ----------
    embeddings : torch.Tensor, shape (N, D)
        N 个 token/样本嵌入向量, 每个维度 D。
        (若上游是 (B, T, D), 调用前先 reshape 成 (B*T, D))
    thresholds : dict, optional
        覆盖默认阈值 CANARY_THRESHOLDS 中的任意键。

    Returns
    -------
    dict:
        std: float
        effective_rank: float
        koleo_entropy: float
        flagged: bool          -- 任一指标低于阈值即为 True
        flags: dict[str, bool] -- 每个指标各自是否触发
    """
    if embeddings.dim() != 2:
        raise ValueError(f"expected 2D tensor (N, D), got shape={tuple(embeddings.shape)}")

    th = dict(CANARY_THRESHOLDS)
    if thresholds:
        th.update(thresholds)

    std_val = _embedding_std(embeddings)
    rank_val = _effective_rank(embeddings)
    koleo_val = _koleo_entropy(embeddings)

    flags = {
        "std": std_val < th["std_min"],
        "effective_rank": rank_val < th["effective_rank_min"],
        "koleo_entropy": koleo_val < th["koleo_entropy_min"],
    }
    flagged = any(flags.values())

    return {
        "std": std_val,
        "effective_rank": rank_val,
        "koleo_entropy": koleo_val,
        "flagged": flagged,
        "flags": flags,
        "thresholds": th,
    }


def calibrate_thresholds(embeddings_list: list[torch.Tensor], quantile: float = 0.5) -> dict:
    """
    辅助函数: 给定一批 "已知健康" (A0 正常训练) 的嵌入快照, 计算三指标的
    分布并取指定分位数作为阈值 (pilot §9: "取 A0 正常训练 50% 分位")。

    Parameters
    ----------
    embeddings_list : list of (N, D) Tensor
        多个训练 step / 多个 seed 的嵌入快照。
    quantile : float
        分位数, 默认 0.5 (中位数)。

    Returns
    -------
    dict, 同 CANARY_THRESHOLDS 的 key, 可直接传给 compute_canary(thresholds=...)
    """
    stds, ranks, koleos = [], [], []
    for emb in embeddings_list:
        stds.append(_embedding_std(emb))
        ranks.append(_effective_rank(emb))
        koleos.append(_koleo_entropy(emb))

    def _q(vals):
        t = torch.tensor(vals, dtype=torch.float32)
        return torch.quantile(t, quantile).item()

    return {
        "std_min": _q(stds),
        "effective_rank_min": _q(ranks),
        "koleo_entropy_min": _q(koleos),
    }


if __name__ == "__main__":
    n_pass = 0
    n_fail = 0

    torch.manual_seed(0)
    n_samples, dim = 256, 64

    # --- 正常随机嵌入 (高斯, 各维独立, 应远离塌缩) ---
    healthy = torch.randn(n_samples, dim)
    healthy_canary = compute_canary(healthy)
    print(f"[INFO] healthy embeddings canary: "
          f"std={healthy_canary['std']:.4f}, "
          f"effective_rank={healthy_canary['effective_rank']:.4f}, "
          f"koleo_entropy={healthy_canary['koleo_entropy']:.4f}, "
          f"flagged={healthy_canary['flagged']}")

    if not healthy_canary["flagged"]:
        print("[PASS] Test1: 健康随机嵌入未被 flag")
        n_pass += 1
    else:
        print(f"[FAIL] Test1: 健康随机嵌入被错误 flag -> {healthy_canary['flags']}")
        n_fail += 1

    # --- 塌缩嵌入: 所有 token 嵌入完全相同 (representation collapse 极端情形) ---
    collapsed_vec = torch.randn(1, dim)
    collapsed = collapsed_vec.repeat(n_samples, 1)
    collapsed_canary = compute_canary(collapsed)
    print(f"[INFO] collapsed embeddings canary: "
          f"std={collapsed_canary['std']:.6f}, "
          f"effective_rank={collapsed_canary['effective_rank']:.6f}, "
          f"koleo_entropy={collapsed_canary['koleo_entropy']:.6f}, "
          f"flagged={collapsed_canary['flagged']}")

    if collapsed_canary["flagged"]:
        print(f"[PASS] Test2: 全相同塌缩嵌入被正确 flag -> {collapsed_canary['flags']}")
        n_pass += 1
    else:
        print(f"[FAIL] Test2: 全相同塌缩嵌入未被 flag (应至少 std/koleo 触发)")
        n_fail += 1

    # --- 对比验证: 塌缩嵌入的三个指标都应显著低于健康嵌入 ---
    if (collapsed_canary["std"] < healthy_canary["std"] and
            collapsed_canary["effective_rank"] < healthy_canary["effective_rank"] and
            collapsed_canary["koleo_entropy"] < healthy_canary["koleo_entropy"]):
        print("[PASS] Test3: 塌缩嵌入三指标均低于健康嵌入 (符合预期方向)")
        n_pass += 1
    else:
        print(f"[FAIL] Test3: 塌缩 vs 健康指标方向不符预期 -> "
              f"collapsed={collapsed_canary}, healthy={healthy_canary}")
        n_fail += 1

    # --- 低秩 (但非完全塌缩) 嵌入: 所有点落在一条直线上 (rank=1 子空间) ---
    direction = torch.randn(1, dim)
    coeffs = torch.randn(n_samples, 1)
    low_rank = coeffs @ direction  # (N, D), rank 1
    low_rank_canary = compute_canary(low_rank)
    print(f"[INFO] low-rank embeddings canary: "
          f"std={low_rank_canary['std']:.4f}, "
          f"effective_rank={low_rank_canary['effective_rank']:.4f}, "
          f"koleo_entropy={low_rank_canary['koleo_entropy']:.4f}, "
          f"flagged={low_rank_canary['flagged']}")

    if low_rank_canary["effective_rank"] < healthy_canary["effective_rank"]:
        print("[PASS] Test4: 低秩嵌入的 effective_rank 显著低于健康嵌入")
        n_pass += 1
    else:
        print(f"[FAIL] Test4: 低秩嵌入 effective_rank 未低于健康嵌入")
        n_fail += 1

    # --- calibrate_thresholds 基本可用性 ---
    calibrated = calibrate_thresholds([healthy, healthy * 0.9], quantile=0.5)
    if all(k in calibrated for k in ("std_min", "effective_rank_min", "koleo_entropy_min")):
        print(f"[PASS] Test5: calibrate_thresholds 返回完整字典 -> {calibrated}")
        n_pass += 1
    else:
        print(f"[FAIL] Test5: calibrate_thresholds 返回不完整 -> {calibrated}")
        n_fail += 1

    print(f"\n=== s3_collapse_canary self-test: {n_pass} passed, {n_fail} failed ===")
    if n_fail == 0:
        print("OVERALL: PASS")
    else:
        print("OVERALL: FAIL")
        raise SystemExit(1)
