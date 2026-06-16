"""
S6 -- determinism 留痕 (silent-bug 哨兵 #6)

权威定义: 03_pilot_NIH_ChestXray14.md §7.6
  "determinism 留痕: 记 cudnn flags + seed"

背景 (复现报告 §B.3 / project_hpc 经验): atomic 操作的非确定性是已知的
跨 run 不可复现来源之一。pilot §4 要求 "A2 开 deterministic" 且 §6
Deterministic Mode 三件套之一是 cudnn.deterministic/benchmark/
use_deterministic_algorithms + 固定 fire-mask seed; §15 红线 6
"所有 run 记 seed + cudnn flags + job ID, 可追溯"。

本文件提供:
  1. `set_determinism(seed)` -- 一站式设置所有相关随机源 (python random,
     numpy, torch CPU/CUDA, cudnn flags, use_deterministic_algorithms)。
  2. `log_determinism() -> dict` -- 读取并返回当前所有相关 flags/seed 状态,
     供训练脚本写入 results/state.json 或日志, 实现"留痕"。
  3. `__main__` self-test: 调用 set_determinism 后, log_determinism 应
     反映出预期状态; 并验证同 seed 下两次随机数序列一致 (确定性生效)。

可被训练脚本 import:
    from s6_determinism_log import set_determinism, log_determinism

    set_determinism(seed=42)
    state["determinism"] = log_determinism()  # 写入 results/state.json
"""

from __future__ import annotations

import os
import random

import numpy as np
import torch


def set_determinism(
    seed: int,
    cudnn_deterministic: bool = True,
    cudnn_benchmark: bool = False,
    use_deterministic_algorithms: bool = True,
    warn_only: bool = True,
) -> None:
    """
    一站式设置确定性相关的全局状态 (供 A2 / deterministic mode 在训练入口调用)。

    Parameters
    ----------
    seed : int
        统一种子, 同时设置 python random / numpy / torch (CPU + 所有 CUDA device)。
    cudnn_deterministic : bool
        torch.backends.cudnn.deterministic
    cudnn_benchmark : bool
        torch.backends.cudnn.benchmark (deterministic 模式下应为 False,
        因为 benchmark=True 会让 cudnn 自动选择可能非确定性的算法)。
    use_deterministic_algorithms : bool
        torch.use_deterministic_algorithms(...)。某些算子在 deterministic
        模式下没有确定性实现, 会抛 RuntimeError; warn_only 控制是否仅警告。
    warn_only : bool
        传给 torch.use_deterministic_algorithms 的 warn_only 参数。
        pilot 阶段建议 True (有些 op 没有确定性 kernel, 不应直接炸掉训练),
        但仍记录"已尝试开启"这一事实。
    """
    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

    torch.backends.cudnn.deterministic = cudnn_deterministic
    torch.backends.cudnn.benchmark = cudnn_benchmark

    if use_deterministic_algorithms:
        try:
            torch.use_deterministic_algorithms(True, warn_only=warn_only)
        except TypeError:
            # 旧版本 torch 不支持 warn_only kwarg
            torch.use_deterministic_algorithms(True)

    # CUBLAS 确定性 (matmul on CUDA) 需要的环境变量, 必须在 CUDA context 创建前设置;
    # 这里仅设置环境变量并记录, 实际生效与否由 log_determinism 报告。
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")


def log_determinism() -> dict:
    """
    返回当前确定性相关状态的快照字典, 供写入 results/state.json / 日志。

    Returns
    -------
    dict with keys:
        seed_python: int | None        -- 无法直接读取 python random 的种子值
                                           (random 模块不暴露当前 seed), 记 None,
                                           但记录 PYTHONHASHSEED 环境变量作为代理。
        pythonhashseed: str | None
        torch_initial_seed: int        -- torch.initial_seed() (CPU RNG 种子)
        cuda_available: bool
        cudnn_deterministic: bool | None
        cudnn_benchmark: bool | None
        use_deterministic_algorithms: bool  -- torch.are_deterministic_algorithms_enabled()
        cublas_workspace_config: str | None -- 环境变量, CUDA matmul 确定性相关
        torch_version: str
        cuda_version: str | None
    """
    cuda_available = torch.cuda.is_available()

    return {
        "pythonhashseed": os.environ.get("PYTHONHASHSEED"),
        "torch_initial_seed": torch.initial_seed(),
        "cuda_available": cuda_available,
        "cudnn_deterministic": torch.backends.cudnn.deterministic if cuda_available else None,
        "cudnn_benchmark": torch.backends.cudnn.benchmark if cuda_available else None,
        "use_deterministic_algorithms": torch.are_deterministic_algorithms_enabled(),
        "cublas_workspace_config": os.environ.get("CUBLAS_WORKSPACE_CONFIG"),
        "torch_version": torch.__version__,
        "cuda_version": torch.version.cuda if cuda_available else None,
    }


def print_determinism_report(state: dict | None = None) -> None:
    """打印 log_determinism() 结果的人类可读版本 (供训练脚本启动时调用留痕)。"""
    if state is None:
        state = log_determinism()
    print("=== Determinism state ===")
    for k, v in state.items():
        print(f"  {k:28s}: {v}")


if __name__ == "__main__":
    n_pass = 0
    n_fail = 0

    # --- Test 1: set_determinism + log_determinism 基本字段存在且类型正确 ---
    set_determinism(seed=1234, warn_only=True)
    state = log_determinism()
    print_determinism_report(state)

    required_keys = {
        "pythonhashseed", "torch_initial_seed", "cuda_available",
        "cudnn_deterministic", "cudnn_benchmark", "use_deterministic_algorithms",
        "cublas_workspace_config", "torch_version", "cuda_version",
    }
    if required_keys.issubset(state.keys()):
        print("[PASS] Test1: log_determinism 返回所有必需字段")
        n_pass += 1
    else:
        missing = required_keys - state.keys()
        print(f"[FAIL] Test1: 缺少字段 -> {missing}")
        n_fail += 1

    # Test 1b: torch_initial_seed 应等于设置的 seed (CPU)
    if state["torch_initial_seed"] == 1234:
        print(f"[PASS] Test1b: torch_initial_seed == 1234")
        n_pass += 1
    else:
        print(f"[FAIL] Test1b: torch_initial_seed={state['torch_initial_seed']} != 1234")
        n_fail += 1

    # Test 1c: use_deterministic_algorithms 应为 True
    if state["use_deterministic_algorithms"] is True:
        print("[PASS] Test1c: use_deterministic_algorithms == True")
        n_pass += 1
    else:
        print(f"[FAIL] Test1c: use_deterministic_algorithms={state['use_deterministic_algorithms']}, 期望 True")
        n_fail += 1

    # --- Test 2: 同 seed 下两次随机数序列应一致 (确定性生效的端到端验证) ---
    set_determinism(seed=999, warn_only=True)
    seq1 = torch.randn(5).clone()
    np_seq1 = np.random.rand(5).copy()
    py_seq1 = [random.random() for _ in range(3)]

    set_determinism(seed=999, warn_only=True)
    seq2 = torch.randn(5).clone()
    np_seq2 = np.random.rand(5).copy()
    py_seq2 = [random.random() for _ in range(3)]

    torch_match = torch.allclose(seq1, seq2)
    np_match = np.allclose(np_seq1, np_seq2)
    py_match = py_seq1 == py_seq2

    if torch_match and np_match and py_match:
        print("[PASS] Test2: 同 seed 下 torch/numpy/random 三者随机序列均一致 (确定性生效)")
        n_pass += 1
    else:
        print(f"[FAIL] Test2: 随机序列不一致 -> torch_match={torch_match}, np_match={np_match}, py_match={py_match}")
        n_fail += 1

    # --- Test 3: cudnn flags 在 CPU-only 环境下应为 None (无 CUDA), 有 CUDA 时应符合设置 ---
    if torch.cuda.is_available():
        ok = (state["cudnn_deterministic"] is True) and (state["cudnn_benchmark"] is False)
        if ok:
            print("[PASS] Test3: CUDA 可用, cudnn_deterministic=True, cudnn_benchmark=False")
            n_pass += 1
        else:
            print(f"[FAIL] Test3: cudnn flags 不符预期 -> "
                  f"deterministic={state['cudnn_deterministic']}, benchmark={state['cudnn_benchmark']}")
            n_fail += 1
    else:
        if state["cudnn_deterministic"] is None and state["cudnn_benchmark"] is None:
            print("[PASS] Test3: CUDA 不可用, cudnn flags 记为 None (符合预期)")
            n_pass += 1
        else:
            print(f"[FAIL] Test3: CUDA 不可用但 cudnn flags 非 None -> {state}")
            n_fail += 1

    print(f"\n=== s6_determinism_log self-test: {n_pass} passed, {n_fail} failed ===")
    if n_fail == 0:
        print("OVERALL: PASS")
    else:
        print("OVERALL: FAIL")
        raise SystemExit(1)
