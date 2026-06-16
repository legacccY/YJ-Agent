"""
S7 -- 静默发散检测 (silent-bug 哨兵 #7)

权威定义: 03_pilot_NIH_ChestXray14.md §7.7
  "静默发散检测: ep10 后 loss>3 持续 -> 自动标 dead 取消 (复现报告 §B.3 signature)"

参考: project_log/reference_nca_divergence_signature.md
  "NCA 发散 signature: loss 死平 >3 + Dice 0 = 发散立即重提; 同 seed 也会炸
   (非 bit 复现)"

核心 signature: 训练早期 (ep<=10) loss 较高是正常的 (warmup), 但若 ep10 之后
loss 仍 "死平" 在 >3 的高位、持续若干 epoch 不下降, 这是典型的 NCA 发散信号
(梯度爆炸/消失导致模型卡在某个高 loss 平台, 而不是正常下降轨迹中的噪声波动)。

本文件提供:
  1. `check_silent_divergence(loss_history, ...) -> (is_dead, reason)`
     给定 per-epoch loss 序列, 检测是否符合"死平发散"signature。
  2. `__main__` self-test:
       - 健康轨迹 (loss 持续下降) -> is_dead=False
       - 死平 5.0 轨迹 (ep10 后 loss 卡在 5.0 不动) -> is_dead=True

可被训练脚本 import:
    from s7_silent_divergence import check_silent_divergence

    # 训练循环, 每个 epoch 结束后:
    is_dead, reason = check_silent_divergence(loss_history)
    if is_dead:
        print(f"DEAD RUN detected: {reason}")
        # 标记 state.json 并 abort / 不再续跑
"""

from __future__ import annotations

import torch


def check_silent_divergence(
    loss_history: list[float],
    warmup_epochs: int = 10,
    high_loss_threshold: float = 3.0,
    flat_window: int = 5,
    flat_std_threshold: float = 0.05,
) -> tuple[bool, str]:
    """
    检测"静默发散"signature: warmup 之后 loss 持续处于高位且基本不变 (死平)。

    Parameters
    ----------
    loss_history : list[float]
        逐 epoch 的 loss 值 (按时间顺序, index 0 = epoch 1)。
    warmup_epochs : int
        warmup epoch 数, 在此之前的高 loss 视为正常, 不参与死平判定。
        pilot §7.7: "ep10 后"。
    high_loss_threshold : float
        判定"高位"的 loss 阈值。pilot §7.7 / signature: >3。
    flat_window : int
        判定"持续"所需的连续 epoch 数窗口。pilot §7.7: "持续>5 ep"
        (本函数用 >= flat_window 个连续 epoch 满足"高且平"判定为 dead)。
    flat_std_threshold : float
        窗口内 loss 标准差低于此值视为"死平" (不是单纯高, 而是高且不变化)。
        若窗口内 loss 仍在下降 (std 大但趋势向下), 不应误判为 dead --
        但本函数采用保守策略: 只要窗口内 loss 全部 > threshold 且标准差很小,
        即认为"卡住了", 不论是否曾经下降过。

    Returns
    -------
    (is_dead, reason) : tuple[bool, str]
        is_dead=True 表示检测到死平发散 signature, reason 给出具体窗口与数值。
        is_dead=False 时 reason 为简短说明 (例如 "loss 在 warmup 内" 或 "未检出死平窗口")。
    """
    n = len(loss_history)

    if n <= warmup_epochs:
        return False, f"训练 epoch 数 ({n}) 未超过 warmup_epochs ({warmup_epochs}), 暂不判定。"

    post_warmup = loss_history[warmup_epochs:]  # ep(warmup_epochs+1) 起

    if len(post_warmup) < flat_window:
        return False, (f"warmup 后仅有 {len(post_warmup)} 个 epoch (< flat_window={flat_window}), "
                        f"数据不足以判定死平。")

    losses_t = torch.tensor(post_warmup, dtype=torch.float32)

    # 滑动窗口检测: 任一连续 flat_window 个 epoch 全部 > threshold 且 std < flat_std_threshold
    for start in range(0, len(post_warmup) - flat_window + 1):
        window = losses_t[start:start + flat_window]
        all_high = bool((window > high_loss_threshold).all())
        is_flat = bool(window.std(unbiased=False).item() < flat_std_threshold)
        if all_high and is_flat:
            ep_start = warmup_epochs + start + 1  # 1-indexed epoch number
            ep_end = ep_start + flat_window - 1
            reason = (
                f"检测到死平发散 signature: epoch {ep_start}-{ep_end} loss 持续 > "
                f"{high_loss_threshold} (窗口值={window.tolist()}, "
                f"std={window.std(unbiased=False).item():.4f} < {flat_std_threshold}). "
                f"符合 NCA 发散 signature (loss 死平>3 持续>{flat_window-1}ep), 建议标 dead, 取消该 run。"
            )
            return True, reason

    return False, f"未在 warmup 后检出死平窗口 (检查了 {len(post_warmup) - flat_window + 1} 个窗口)。"


def _healthy_trajectory(n_epochs: int = 30) -> list[float]:
    """模拟健康训练轨迹: loss 从 ~5 指数衰减到 ~0.3, 带小噪声。"""
    g = torch.Generator().manual_seed(0)
    epochs = torch.arange(1, n_epochs + 1, dtype=torch.float32)
    base = 0.3 + 4.7 * torch.exp(-epochs / 8.0)
    noise = (torch.rand(n_epochs, generator=g) - 0.5) * 0.05
    return (base + noise).tolist()


def _dead_trajectory(n_epochs: int = 30, dead_value: float = 5.0) -> list[float]:
    """模拟死平发散轨迹: 前几个 epoch 略有波动, 之后 (含 ep10 之后) 卡死在 5.0。"""
    g = torch.Generator().manual_seed(1)
    traj = []
    for ep in range(1, n_epochs + 1):
        if ep <= 8:
            # 前期看起来还在动 (从随机初始化的高 loss 略微波动)
            val = dead_value + 0.5 + (torch.rand(1, generator=g).item() - 0.5) * 0.5
        else:
            # ep9 起卡死在 dead_value 附近, 极小噪声
            val = dead_value + (torch.rand(1, generator=g).item() - 0.5) * 0.01
        traj.append(val)
    return traj


def _borderline_decreasing_trajectory(n_epochs: int = 30) -> list[float]:
    """
    模拟"虽然 loss > 3 但仍在持续下降"的轨迹 (不应被判 dead, 因为不是"死平"):
    loss 从 10 缓慢线性下降到 3.5, 全程未死平。
    """
    epochs = torch.arange(1, n_epochs + 1, dtype=torch.float32)
    return (10.0 - 0.2 * epochs).tolist()


if __name__ == "__main__":
    n_pass = 0
    n_fail = 0

    # --- Test 1: 健康轨迹应不被判 dead ---
    healthy = _healthy_trajectory(30)
    is_dead, reason = check_silent_divergence(healthy)
    print(f"[INFO] healthy trajectory: loss[ep1]={healthy[0]:.3f}, loss[ep30]={healthy[-1]:.3f}, "
          f"is_dead={is_dead}, reason={reason}")
    if not is_dead:
        print("[PASS] Test1: 健康下降轨迹未被判 dead")
        n_pass += 1
    else:
        print(f"[FAIL] Test1: 健康轨迹被误判 dead -> {reason}")
        n_fail += 1

    # --- Test 2: 死平 5.0 轨迹应被判 dead ---
    dead = _dead_trajectory(30, dead_value=5.0)
    is_dead2, reason2 = check_silent_divergence(dead)
    print(f"[INFO] dead trajectory (last 5): {dead[-5:]}, is_dead={is_dead2}")
    print(f"       reason: {reason2}")
    if is_dead2:
        print("[PASS] Test2: 死平 5.0 轨迹被正确判 dead")
        n_pass += 1
    else:
        print(f"[FAIL] Test2: 死平 5.0 轨迹未被判 dead -> {reason2}")
        n_fail += 1

    # --- Test 3: ep10 前的高 loss (warmup 内) 不应触发 dead ---
    early_high_only = [8.0] * 8 + _healthy_trajectory(22)
    is_dead3, reason3 = check_silent_divergence(early_high_only, warmup_epochs=10)
    if not is_dead3:
        print(f"[PASS] Test3: warmup 内的高 loss 不触发 dead -> {reason3}")
        n_pass += 1
    else:
        print(f"[FAIL] Test3: warmup 内高 loss 被误判 dead -> {reason3}")
        n_fail += 1

    # --- Test 4: loss>3 但持续下降 (非死平) 不应被判 dead ---
    decreasing = _borderline_decreasing_trajectory(30)
    is_dead4, reason4 = check_silent_divergence(decreasing)
    print(f"[INFO] decreasing-but->3 trajectory: loss[ep10]={decreasing[9]:.3f}, "
          f"loss[ep30]={decreasing[-1]:.3f}, is_dead={is_dead4}")
    if not is_dead4:
        print(f"[PASS] Test4: loss>3 但持续下降的轨迹未被误判 dead -> {reason4}")
        n_pass += 1
    else:
        print(f"[FAIL] Test4: 持续下降的轨迹被误判 dead -> {reason4}")
        n_fail += 1

    print(f"\n=== s7_silent_divergence self-test: {n_pass} passed, {n_fail} failed ===")
    if n_fail == 0:
        print("OVERALL: PASS")
    else:
        print("OVERALL: FAIL")
        raise SystemExit(1)
