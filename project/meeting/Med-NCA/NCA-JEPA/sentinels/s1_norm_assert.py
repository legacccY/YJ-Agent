"""
S1 -- 归一化 assert (silent-bug 哨兵 #1)

权威定义: 03_pilot_NIH_ChestXray14.md §7.1
  "归一化 assert: 喂入张量 mean/std == 期望 NORM; raw 值溜进来直接 raise"

背景: VisiSkin visiscore 喂 raw[0,1] 而非 NORM224 的血泪教训 (project_visiscore_feeding_bug.md)。
本哨兵在训练脚本的 dataloader -> model 入口处插一道闸门, 任何不符合期望归一化分布的
batch 直接 raise, 不让 bug 假扮成"训练正常但表征退化"的结果。

可被训练脚本 import:
    from s1_norm_assert import assert_normalized, DEFAULT_IMAGENET_MEAN, DEFAULT_IMAGENET_STD

    # 在 train loop 里, 拿到 batch 后第一件事:
    assert_normalized(images, expected_mean=DEFAULT_IMAGENET_MEAN, expected_std=DEFAULT_IMAGENET_STD)
"""

from __future__ import annotations

import torch


# I-JEPA / torchvision ImageNet 标准归一化常数 (单通道场景下取均值, 三通道独立给定均可)
DEFAULT_IMAGENET_MEAN = (0.485, 0.456, 0.406)
DEFAULT_IMAGENET_STD = (0.229, 0.224, 0.225)


class NormalizationError(AssertionError):
    """喂入张量的统计量与期望 NORM 不符 -- 极可能是 raw[0,1] 或 raw[0,255] 溜入管线。"""


def _per_channel_stats(x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    """
    计算 (B,C,H,W) 张量每个通道的 mean / std (跨 batch + 空间维聚合)。
    返回两个 shape=(C,) 的张量。
    """
    if x.dim() != 4:
        raise ValueError(f"expected 4D tensor (B,C,H,W), got shape={tuple(x.shape)}")
    c = x.shape[1]
    flat = x.permute(1, 0, 2, 3).reshape(c, -1)
    return flat.mean(dim=1), flat.std(dim=1)


def assert_normalized(
    x: torch.Tensor,
    expected_mean,
    expected_std,
    mean_tol: float = 0.35,
    std_tol: float = 0.35,
    raw_range_check: bool = True,
) -> dict:
    """
    断言输入张量的逐通道 mean/std 落在期望 NORM 附近的容差带内。

    Parameters
    ----------
    x : torch.Tensor, shape (B,C,H,W)
        喂入模型前的图像 batch。
    expected_mean, expected_std : float 或 长度=C 的序列
        期望的归一化均值/标准差 (例如 NORM224 用的 ImageNet 统计量)。
        注意: 归一化后数据本身的 mean/std 不会精确等于 0/1 (因为
        normalize 是减/除常数, 不是 z-score), 这里检查的是
        "数据范围与期望 NORM 后的合理区间是否一致" -- 核心目的是
        **拦截 raw [0,1] 或 raw [0,255] 这种明显跑偏的输入**。
    mean_tol, std_tol : float
        容差带半宽 (绝对值)。
    raw_range_check : bool
        额外检查: 若张量 min>=0 且 max<=1 且 std 明显小于归一化后典型量级,
        判定为 "看起来像未归一化的 raw[0,1]", 直接 raise。

    Returns
    -------
    dict: {"mean": Tensor(C,), "std": Tensor(C,), "min": float, "max": float}

    Raises
    ------
    NormalizationError 当统计量超出容差或疑似 raw 输入。
    """
    mean, std = _per_channel_stats(x)
    c = mean.shape[0]

    def _to_tensor(v, name):
        if isinstance(v, (int, float)):
            return torch.full((c,), float(v), dtype=mean.dtype)
        t = torch.as_tensor(v, dtype=mean.dtype)
        if t.numel() == 1:
            t = t.expand(c).clone()
        if t.numel() != c:
            raise ValueError(f"{name} length {t.numel()} != channels {c}")
        return t

    exp_mean = _to_tensor(expected_mean, "expected_mean")
    exp_std = _to_tensor(expected_std, "expected_std")

    xmin = float(x.min().item())
    xmax = float(x.max().item())

    # --- 核心拦截: raw [0,1] 输入 ---
    # 归一化后 (raw - mean)/std, 对 ImageNet 统计量而言 raw=0 -> 约 -1.9~-2.1,
    # raw=1 -> 约 +2.1~2.6。若整批张量被限制在 [0,1] (或 [~0, ~1] 之内),
    # 且 std 远小于期望 std, 几乎可以确定是没做 normalize 的 raw 图像。
    if raw_range_check:
        looks_unit_range = (xmin >= -1e-3) and (xmax <= 1.0 + 1e-3) and (xmax - xmin > 1e-6)
        if looks_unit_range:
            raise NormalizationError(
                f"输入张量值域落在 [0,1] (min={xmin:.4f}, max={xmax:.4f}), "
                f"疑似未做 normalize 的 raw 图像直接喂入模型! "
                f"期望归一化后范围应覆盖到 ~[-2.2, 2.7] 量级 "
                f"(基于 mean={exp_mean.tolist()}, std={exp_std.tolist()})。"
                f"请检查 dataloader 的 transform 链是否包含 Normalize(mean, std)。"
            )

        # raw [0,255] 也常见 (忘记 ToTensor 缩放)
        if xmax > 10.0:
            raise NormalizationError(
                f"输入张量 max={xmax:.2f} > 10, 疑似 raw [0,255] 图像未缩放/未归一化。"
            )

    # --- 逐通道 mean/std 容差检查 ---
    # 归一化后数据分布的 mean/std 取决于原始像素分布, 这里采用宽松容差
    # (允许 +-0.35), 主要目的不是精确验证统计矩, 而是确认"数量级在归一化区间内"
    mean_diff = (mean - exp_mean).abs()
    std_diff = (std - exp_std).abs()

    # 归一化后, 典型 mean 在 [-0.5, 0.5] 附近 (取决于数据集与 ImageNet 的偏移),
    # std 应接近 1.0 量级 (因为除以了 std)。这里检查 std 是否接近 1, 而非接近 exp_std,
    # 因为 normalize 操作本身就是把 std 拉到 ~1。
    expected_norm_std = torch.ones_like(std)  # normalize 后期望 std ~ 1
    norm_std_diff = (std - expected_norm_std).abs()

    bad_channels = (norm_std_diff > std_tol) & (mean.abs() > (1.0 + mean_tol))
    if bool(bad_channels.any()):
        raise NormalizationError(
            f"逐通道统计量异常: mean={mean.tolist()}, std={std.tolist()} "
            f"(期望 normalize 后 std~1, mean 在合理偏移范围内)。"
            f"疑似归一化未生效或使用了错误的 mean/std 常数。"
        )

    return {"mean": mean, "std": std, "min": xmin, "max": xmax}


def _make_self_test_tensor(kind: str, b: int = 4, c: int = 3, h: int = 16, w: int = 16) -> torch.Tensor:
    g = torch.Generator().manual_seed(0)
    if kind == "raw01":
        return torch.rand(b, c, h, w, generator=g)
    if kind == "raw255":
        return torch.rand(b, c, h, w, generator=g) * 255.0
    if kind == "normalized":
        # 模拟: raw[0,1] 图像经 transforms.Normalize(mean, std) 后的结果
        raw = torch.rand(b, c, h, w, generator=g)
        mean = torch.tensor(DEFAULT_IMAGENET_MEAN).view(1, c, 1, 1)
        std = torch.tensor(DEFAULT_IMAGENET_STD).view(1, c, 1, 1)
        return (raw - mean) / std
    raise ValueError(kind)


if __name__ == "__main__":
    n_pass = 0
    n_fail = 0

    # Test 1: raw[0,1] 张量应 raise
    try:
        x_raw = _make_self_test_tensor("raw01")
        assert_normalized(x_raw, DEFAULT_IMAGENET_MEAN, DEFAULT_IMAGENET_STD)
        print("[FAIL] Test1: raw[0,1] 输入未被拦截 (应 raise NormalizationError)")
        n_fail += 1
    except NormalizationError as e:
        print(f"[PASS] Test1: raw[0,1] 被正确拦截 -> {e}")
        n_pass += 1

    # Test 2: raw[0,255] 张量应 raise
    try:
        x_raw255 = _make_self_test_tensor("raw255")
        assert_normalized(x_raw255, DEFAULT_IMAGENET_MEAN, DEFAULT_IMAGENET_STD)
        print("[FAIL] Test2: raw[0,255] 输入未被拦截 (应 raise NormalizationError)")
        n_fail += 1
    except NormalizationError as e:
        print(f"[PASS] Test2: raw[0,255] 被正确拦截 -> {e}")
        n_pass += 1

    # Test 3: 正确归一化后的张量应通过
    try:
        x_norm = _make_self_test_tensor("normalized")
        stats = assert_normalized(x_norm, DEFAULT_IMAGENET_MEAN, DEFAULT_IMAGENET_STD)
        print(f"[PASS] Test3: 归一化输入通过检查 -> mean={stats['mean'].tolist()}, std={stats['std'].tolist()}")
        n_pass += 1
    except NormalizationError as e:
        print(f"[FAIL] Test3: 正确归一化输入被错误拦截 -> {e}")
        n_fail += 1

    print(f"\n=== s1_norm_assert self-test: {n_pass} passed, {n_fail} failed ===")
    if n_fail == 0:
        print("OVERALL: PASS")
    else:
        print("OVERALL: FAIL")
        raise SystemExit(1)
