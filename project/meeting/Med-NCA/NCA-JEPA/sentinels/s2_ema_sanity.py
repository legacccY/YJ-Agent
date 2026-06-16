"""
S2 -- EMA sanity (silent-bug 哨兵 #2)

权威定义: 03_pilot_NIH_ChestXray14.md §7.2
  "EMA sanity: target != context; target encoder 不吃梯度"

I-JEPA 标配: target encoder 是 context encoder 的 EMA (momentum 0.996->1.0)。
两个常见 silent bug:
  (a) target encoder 参数被错误地设成 context encoder 的引用/拷贝, 导致两者
      逐字节相同 (EMA update 没生效, 或者 deepcopy 没做)。
  (b) target encoder 的参数 requires_grad=True, optimizer 把它也更新了
      (没有 detach / no_grad / 没 freeze), EMA "追自身漂移", 理论 §5 EMA 益处失效。

可被训练脚本 import:
    from s2_ema_sanity import check_ema_sanity

    # 训练循环初始化后、第一次 EMA update 之后调用:
    result = check_ema_sanity(context_encoder, target_encoder)
    assert result["ok"], result["reason"]
"""

from __future__ import annotations

import copy

import torch
import torch.nn as nn


def check_ema_sanity(
    context_encoder: nn.Module,
    target_encoder: nn.Module,
    require_diff_after_update: bool = True,
    min_param_diff: float = 1e-12,
) -> dict:
    """
    检查 target encoder 与 context encoder 的关系是否符合 EMA target 的预期。

    检查项:
      1. target encoder 所有参数 requires_grad == False (不吃梯度)。
      2. target encoder 参数与 context encoder 参数不是同一对象 (不共享内存/引用)。
      3. (可选) 若两者参数当前逐元素相同, 标记 warning -- 在 EMA momentum 接近 0
         的训练初始 step 这是正常的 (target 刚 deepcopy 完 context), 但若在训练
         若干 step / 多次 EMA update 之后仍完全相同, 说明 EMA update 没有生效。
         本函数只做"当前是否相同"的事实报告, 由调用方根据训练阶段决定是否视为异常
         (通过 require_diff_after_update 控制是否把"相同"判为 fail)。

    Parameters
    ----------
    context_encoder, target_encoder : nn.Module
        结构应一致 (state_dict keys 对齐)。
    require_diff_after_update : bool
        若 True, 且两者参数逐元素相同 (说明本次调用是在 EMA update 后做的检查),
        则判定为 fail, reason 中说明 "EMA update 未生效或调用时机过早"。
        若 False (例如在初始化刚 deepcopy 之后调用), 参数相同视为正常, 仅报告。
    min_param_diff : float
        判定"参数不同"所需的最小 L2 差异 (跨所有参数求和), 低于此值视为"相同"。

    Returns
    -------
    dict with keys:
        ok: bool                       -- 总体是否通过
        target_requires_grad: bool     -- target encoder 是否有任意参数 requires_grad=True
        params_identical: bool         -- 两者参数是否逐元素相同 (在 tol 内)
        total_param_diff: float        -- 所有参数差异的 L2 范数之和
        shared_storage: bool           -- 是否存在参数对象共享底层 storage (引用未拷贝)
        reason: str                    -- 若 ok=False, 说明原因; 否则为 "ok"
    """
    target_params = dict(target_encoder.named_parameters())
    context_params = dict(context_encoder.named_parameters())

    reasons = []

    # --- 检查 1: target 不吃梯度 ---
    bad_grad_names = [n for n, p in target_params.items() if p.requires_grad]
    target_requires_grad = len(bad_grad_names) > 0
    if target_requires_grad:
        reasons.append(
            f"target encoder 有 {len(bad_grad_names)} 个参数 requires_grad=True "
            f"(例如: {bad_grad_names[:3]}), target encoder 应 freeze (requires_grad=False)。"
        )

    # --- 检查 2: 是否共享底层存储 (引用未拷贝) ---
    shared_storage = False
    shared_names = []
    common_keys = set(target_params.keys()) & set(context_params.keys())
    if not common_keys:
        reasons.append("target encoder 与 context encoder 的参数名 (named_parameters) 没有交集, 结构不匹配?")
    for name in common_keys:
        tp, cp = target_params[name], context_params[name]
        if tp.data_ptr() == cp.data_ptr():
            shared_storage = True
            shared_names.append(name)
    if shared_storage:
        reasons.append(
            f"target encoder 与 context encoder 共享 {len(shared_names)} 个参数的底层存储 "
            f"(例如: {shared_names[:3]}), 应为独立 deepcopy, 否则 EMA update 会就地改坏 context。"
        )

    # --- 检查 3: 参数是否逐元素相同 ---
    total_diff = 0.0
    for name in common_keys:
        tp, cp = target_params[name], context_params[name]
        if tp.shape != cp.shape:
            reasons.append(f"参数 {name} shape 不一致: target {tp.shape} vs context {cp.shape}")
            continue
        total_diff += (tp.detach().float() - cp.detach().float()).norm().item()

    params_identical = total_diff < min_param_diff

    if params_identical and require_diff_after_update:
        reasons.append(
            f"target encoder 与 context encoder 参数逐元素相同 (total_diff={total_diff:.3e}), "
            f"在 EMA update 之后这表示 EMA momentum update 未生效 (检查 ema_update 是否真的写回了 target.data)。"
        )

    ok = (not target_requires_grad) and (not shared_storage) and (
        (not params_identical) if require_diff_after_update else True
    ) and len(common_keys) > 0 and not any("shape 不一致" in r for r in reasons)

    return {
        "ok": ok,
        "target_requires_grad": target_requires_grad,
        "params_identical": params_identical,
        "total_param_diff": total_diff,
        "shared_storage": shared_storage,
        "reason": "ok" if ok else "; ".join(reasons),
    }


def ema_update(target_encoder: nn.Module, context_encoder: nn.Module, momentum: float) -> None:
    """
    标准 EMA 参数更新 (I-JEPA 风格), 供 self-test 与训练脚本复用:
        target_param <- momentum * target_param + (1 - momentum) * context_param
    在 torch.no_grad() 下进行, 就地更新 target_encoder 的参数。
    """
    with torch.no_grad():
        t_params = dict(target_encoder.named_parameters())
        c_params = dict(context_encoder.named_parameters())
        for name, tp in t_params.items():
            if name in c_params:
                cp = c_params[name]
                tp.data.mul_(momentum).add_(cp.data, alpha=(1.0 - momentum))


def freeze_target_encoder(target_encoder: nn.Module) -> None:
    """把 target encoder 所有参数设为 requires_grad=False (供训练脚本初始化时调用)。"""
    for p in target_encoder.parameters():
        p.requires_grad_(False)


def _make_toy_encoder(seed: int) -> nn.Module:
    g = torch.Generator().manual_seed(seed)
    m = nn.Sequential(nn.Linear(8, 16), nn.ReLU(), nn.Linear(16, 8))
    with torch.no_grad():
        for p in m.parameters():
            p.copy_(torch.randn(p.shape, generator=g))
    return m


if __name__ == "__main__":
    n_pass = 0
    n_fail = 0

    # --- Setup: context encoder + 正确构造的 target encoder (deepcopy + freeze) ---
    context_encoder = _make_toy_encoder(seed=0)
    target_encoder = copy.deepcopy(context_encoder)
    freeze_target_encoder(target_encoder)

    # Test 1: 刚 deepcopy 完, 参数应相同, 但若我们以 require_diff_after_update=False 检查应 PASS
    result = check_ema_sanity(context_encoder, target_encoder, require_diff_after_update=False)
    if result["ok"] and not result["target_requires_grad"] and not result["shared_storage"]:
        print(f"[PASS] Test1: 初始化后 (require_diff=False) sanity ok -> {result}")
        n_pass += 1
    else:
        print(f"[FAIL] Test1: 初始化后 sanity 应 ok -> {result}")
        n_fail += 1

    # 模拟一步 context encoder 的"训练更新" (梯度下降走一步), 让两者出现差异
    with torch.no_grad():
        for p in context_encoder.parameters():
            p.add_(torch.randn_like(p) * 0.1)

    # 做一次 EMA update
    ema_update(target_encoder, context_encoder, momentum=0.996)

    # Test 2: EMA update 后, target != context, target 不吃梯度 -> 应 PASS (ok=True)
    result2 = check_ema_sanity(context_encoder, target_encoder, require_diff_after_update=True)
    if result2["ok"]:
        print(f"[PASS] Test2: EMA update 后 sanity ok -> "
              f"params_identical={result2['params_identical']}, "
              f"total_param_diff={result2['total_param_diff']:.6f}, "
              f"target_requires_grad={result2['target_requires_grad']}")
        n_pass += 1
    else:
        print(f"[FAIL] Test2: EMA update 后应 ok -> {result2}")
        n_fail += 1

    # --- Bug case A: target encoder 是引用 (没 deepcopy) ---
    bad_target_ref = context_encoder  # 直接引用, 共享存储
    result3 = check_ema_sanity(context_encoder, bad_target_ref, require_diff_after_update=False)
    if (not result3["ok"]) and result3["shared_storage"]:
        print(f"[PASS] Test3: 共享引用的 target encoder 被正确检出 -> reason={result3['reason']}")
        n_pass += 1
    else:
        print(f"[FAIL] Test3: 共享引用的 target encoder 未被检出 -> {result3}")
        n_fail += 1

    # --- Bug case B: target encoder 忘记 freeze (requires_grad=True) ---
    bad_target_grad = copy.deepcopy(context_encoder)
    # 不调用 freeze_target_encoder -> requires_grad 仍为 True
    with torch.no_grad():
        for p in bad_target_grad.parameters():
            p.add_(torch.randn_like(p) * 0.1)  # 制造差异, 排除"相同"这一条
    result4 = check_ema_sanity(context_encoder, bad_target_grad, require_diff_after_update=True)
    if (not result4["ok"]) and result4["target_requires_grad"]:
        print(f"[PASS] Test4: 未 freeze 的 target encoder 被正确检出 -> reason={result4['reason']}")
        n_pass += 1
    else:
        print(f"[FAIL] Test4: 未 freeze 的 target encoder 未被检出 -> {result4}")
        n_fail += 1

    # --- Bug case C: EMA update 没生效 (target 与 context 仍逐元素相同) ---
    target_stale = copy.deepcopy(context_encoder)
    freeze_target_encoder(target_stale)
    # 不做 ema_update, 直接检查 (模拟"调了 ema_update 但函数是空操作"的 bug)
    result5 = check_ema_sanity(context_encoder, target_stale, require_diff_after_update=True)
    if (not result5["ok"]) and result5["params_identical"]:
        print(f"[PASS] Test5: 未生效的 EMA (参数仍相同) 被正确检出 -> reason={result5['reason']}")
        n_pass += 1
    else:
        print(f"[FAIL] Test5: 未生效的 EMA 未被检出 -> {result5}")
        n_fail += 1

    print(f"\n=== s2_ema_sanity self-test: {n_pass} passed, {n_fail} failed ===")
    if n_fail == 0:
        print("OVERALL: PASS")
    else:
        print("OVERALL: FAIL")
        raise SystemExit(1)
