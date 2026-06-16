"""
S5 -- z-shuffle 对照 (silent-bug 哨兵 #5)

权威定义: 03_pilot_NIH_ChestXray14.md §7.5
  "z-shuffle 对照: 打乱 mask/z -> 下游应掉 (>=3 AUROC); 不掉 = z 没接进去"

这是检测"条件信息 z (本 pilot 只做 mask M, 见 §4) 是否真的被模型使用"的
经典对照实验: 把 mask indices (或更一般地, 条件 z) 在样本间随机打乱/重排,
若模型/下游对 z 不敏感, 打乱后下游指标 (AUROC) 不应明显下降 -- 这恰恰说明
z 从未真正影响过预测, 即"z 没接进去" (典型的管线 silent bug: 例如 FiLM
条件分支的输出被加到了错误的张量上, 或 mask token 与 PE 没有正确拼接)。

本文件提供:
  1. `shuffle_z(z, generator=None)` -- 通用工具: 打乱 batch 维度上的条件 z。
  2. `zshuffle_downstream_check(...)` -- 框架函数: 给定一个"评估函数"
     (输入 z, 输出某个下游指标, 例如 AUROC), 比较 (原始 z) vs (打乱 z)
     的指标差异, 判断是否符合"打乱应导致指标显著下降"的预期。
  3. `__main__` self-test: 用合成数据构造两个评估函数 --
       (a) "z 真正接入" 的模型 (打乱 z 应导致指标显著下降)
       (b) "z 没接入" 的模型 (打乱 z 指标几乎不变, 应被 flag)
     验证 zshuffle_downstream_check 能正确区分两种情形。

可被训练脚本 import:
    from s5_zshuffle_control import shuffle_z, zshuffle_downstream_check
"""

from __future__ import annotations

from dataclasses import dataclass

import torch


def shuffle_z(z: torch.Tensor, generator: torch.Generator | None = None) -> torch.Tensor:
    """
    打乱条件 z 的 batch 维 (dim=0) 顺序 (per-sample shuffle, 不改变 z 本身的内容/形状,
    只改变"哪个 z 配哪个样本")。

    Parameters
    ----------
    z : torch.Tensor, shape (B, ...)
        条件信息 (本 pilot: mask indices 的 one-hot / mask token; 更一般地可以是
        任意 per-sample 的条件张量)。
    generator : torch.Generator, optional
        若提供, 用于复现打乱顺序。

    Returns
    -------
    torch.Tensor, 与 z 同 shape, batch 维按随机 permutation 重排。
    """
    b = z.shape[0]
    if generator is not None:
        perm = torch.randperm(b, generator=generator)
    else:
        perm = torch.randperm(b)
    return z[perm]


@dataclass
class ZShuffleResult:
    metric_original: float
    metric_shuffled: float
    drop: float  # metric_original - metric_shuffled (假设指标越大越好, 如 AUROC)
    z_is_wired: bool  # drop >= min_drop -> True (z 确实被使用)
    reason: str


def zshuffle_downstream_check(
    eval_fn,
    z: torch.Tensor,
    *eval_fn_args,
    min_drop: float = 3.0,
    n_shuffles: int = 1,
    generator: torch.Generator | None = None,
    **eval_fn_kwargs,
) -> ZShuffleResult:
    """
    对照检验: 打乱条件 z 后, 下游指标应明显下降 (>= min_drop)。

    Parameters
    ----------
    eval_fn : Callable[..., float]
        评估函数, 签名 eval_fn(z, *eval_fn_args, **eval_fn_kwargs) -> float
        (返回一个"越大越好"的指标, 例如 linear probe AUROC, 百分制或 0-1 制
        均可, 只要 min_drop 与指标的尺度匹配; pilot 用 AUROC 百分点, 阈值 3
        对应 ">=3 AUROC")。
    z : torch.Tensor, shape (B, ...)
        原始条件 z。
    min_drop : float
        判定"z 确实被使用"所需的最小指标下降量。pilot §7.5: >=3 (AUROC 点数)。
    n_shuffles : int
        重复打乱次数, 取打乱后指标的均值 (减少单次随机置换的方差)。
    generator : torch.Generator, optional
        随机种子控制。

    Returns
    -------
    ZShuffleResult:
        metric_original: 原始 z 下的指标
        metric_shuffled: 打乱 z 下的指标 (n_shuffles 次均值)
        drop: metric_original - metric_shuffled
        z_is_wired: drop >= min_drop (True = z 确实被使用, 对照通过)
        reason: 文字说明
    """
    metric_original = float(eval_fn(z, *eval_fn_args, **eval_fn_kwargs))

    shuffled_metrics = []
    for i in range(n_shuffles):
        gen = generator
        if gen is not None and n_shuffles > 1:
            # 为每次 shuffle 派生不同种子, 避免重复同一种 permutation
            gen = torch.Generator()
            gen.manual_seed(int(generator.initial_seed()) + i)
        z_shuf = shuffle_z(z, generator=gen)
        shuffled_metrics.append(float(eval_fn(z_shuf, *eval_fn_args, **eval_fn_kwargs)))

    metric_shuffled = sum(shuffled_metrics) / len(shuffled_metrics)
    drop = metric_original - metric_shuffled
    z_is_wired = drop >= min_drop

    if z_is_wired:
        reason = (f"打乱 z 后指标下降 {drop:.3f} (>= {min_drop}), "
                  f"z 看起来确实被模型/下游使用。")
    else:
        reason = (f"打乱 z 后指标仅下降 {drop:.3f} (< {min_drop}), "
                  f"疑似 z 没有真正接入管线 (FiLM/mask token 等条件注入可能短路)。")

    return ZShuffleResult(
        metric_original=metric_original,
        metric_shuffled=metric_shuffled,
        drop=drop,
        z_is_wired=z_is_wired,
        reason=reason,
    )


# =====================================================================
# Self-test: 合成 "z 接入" vs "z 未接入" 两种评估函数
# =====================================================================
def _make_synthetic_data(n: int, dim: int, seed: int = 0):
    g = torch.Generator().manual_seed(seed)
    # 每个样本的"内容"特征 x, 和与 x 配对的条件 z (z 与 x 相关 -- 模拟
    # mask 的位置依赖图像内容, 例如 mask 住的 patch 索引)
    x = torch.randn(n, dim, generator=g)
    z = torch.randn(n, dim, generator=g)  # 条件向量, 与 x 同维方便算内积
    # "真值标签" 由 x 与 z 的关系共同决定 (模拟: 预测目标依赖 "在 z 指定的
    # 条件下, x 的某种变换")
    y = (x * z).sum(dim=1)  # (N,)
    return x, z, y


def _auroc_like_metric(scores: torch.Tensor, labels: torch.Tensor) -> float:
    """
    简化的 AUROC 风格指标 (基于 Spearman 相关的单调映射, 不依赖 sklearn):
    用 scores 与 labels 的皮尔逊相关系数, 映射到 [50, 100] 区间模拟 AUROC 百分点
    (corr=1 -> 100, corr=0 -> 50, corr=-1 -> 0)。仅用于 self-test, 真实训练中
    应替换为 sklearn.metrics.roc_auc_score 的 linear probe 结果。
    """
    scores = scores.float()
    labels = labels.float()
    if scores.std() < 1e-8 or labels.std() < 1e-8:
        corr = 0.0
    else:
        corr = torch.corrcoef(torch.stack([scores, labels]))[0, 1].item()
        if corr != corr:  # NaN guard
            corr = 0.0
    return 50.0 + 50.0 * corr


def _eval_fn_z_wired(z: torch.Tensor, x: torch.Tensor, y: torch.Tensor) -> float:
    """模拟 "z 确实接入" 的下游评估: 预测分数依赖 (x, z) 的交互 (与 y 的生成方式一致)。"""
    scores = (x * z).sum(dim=1)
    return _auroc_like_metric(scores, y)


def _eval_fn_z_not_wired(z: torch.Tensor, x: torch.Tensor, y: torch.Tensor) -> float:
    """模拟 "z 没接入" 的下游评估: 预测分数只用 x, 完全忽略 z (典型的条件注入短路 bug)。"""
    # y 的生成依赖 (x,z), 但若评估时只用 x 自身的某个统计量, 与 y 的相关性较弱且与 z 无关
    scores = x.sum(dim=1)
    return _auroc_like_metric(scores, y)


if __name__ == "__main__":
    n_pass = 0
    n_fail = 0

    torch.manual_seed(0)
    gen = torch.Generator().manual_seed(42)

    x, z, y = _make_synthetic_data(n=512, dim=16, seed=1)

    # --- Test 1: shuffle_z 基本性质 (shape 不变, 内容是原 z 的某个 permutation) ---
    z_shuf = shuffle_z(z, generator=gen)
    same_shape = z_shuf.shape == z.shape
    is_permutation = torch.allclose(
        torch.sort(z.flatten())[0], torch.sort(z_shuf.flatten())[0]
    )
    if same_shape and is_permutation:
        print("[PASS] Test1: shuffle_z 保持 shape 且为原 z 元素的重排")
        n_pass += 1
    else:
        print(f"[FAIL] Test1: shuffle_z 异常 -> same_shape={same_shape}, is_permutation={is_permutation}")
        n_fail += 1

    # --- Test 2: "z 接入" 模型 -> 打乱后指标应显著下降 (z_is_wired=True) ---
    result_wired = zshuffle_downstream_check(
        _eval_fn_z_wired, z, x, y,
        min_drop=3.0, n_shuffles=5, generator=torch.Generator().manual_seed(7),
    )
    print(f"[INFO] z-wired case: metric_original={result_wired.metric_original:.2f}, "
          f"metric_shuffled={result_wired.metric_shuffled:.2f}, drop={result_wired.drop:.2f}, "
          f"z_is_wired={result_wired.z_is_wired}")
    if result_wired.z_is_wired:
        print(f"[PASS] Test2: z 接入模型, 打乱 z 后指标显著下降 -> {result_wired.reason}")
        n_pass += 1
    else:
        print(f"[FAIL] Test2: z 接入模型应被判定 z_is_wired=True -> {result_wired}")
        n_fail += 1

    # --- Test 3: "z 未接入" 模型 -> 打乱后指标几乎不变 (z_is_wired=False, 应被 flag) ---
    result_not_wired = zshuffle_downstream_check(
        _eval_fn_z_not_wired, z, x, y,
        min_drop=3.0, n_shuffles=5, generator=torch.Generator().manual_seed(7),
    )
    print(f"[INFO] z-not-wired case: metric_original={result_not_wired.metric_original:.2f}, "
          f"metric_shuffled={result_not_wired.metric_shuffled:.2f}, drop={result_not_wired.drop:.2f}, "
          f"z_is_wired={result_not_wired.z_is_wired}")
    if not result_not_wired.z_is_wired:
        print(f"[PASS] Test3: z 未接入模型, 打乱 z 后指标几乎不变, 正确被 flag -> {result_not_wired.reason}")
        n_pass += 1
    else:
        print(f"[FAIL] Test3: z 未接入模型应被判定 z_is_wired=False -> {result_not_wired}")
        n_fail += 1

    print(f"\n=== s5_zshuffle_control self-test: {n_pass} passed, {n_fail} failed ===")
    if n_fail == 0:
        print("OVERALL: PASS")
    else:
        print("OVERALL: FAIL")
        raise SystemExit(1)
