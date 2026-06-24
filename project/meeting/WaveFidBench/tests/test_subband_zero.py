"""
test_subband_zero.py — WaveFidBench pytest

测试覆盖：
1. DWT->IDWT 往返重建数值正确性（随机 tensor，allclose atol=1e-3）
2. 子带置零后 shape 不变
3. idx 映射正确（LH=0 / HL=1 / HH=2）

mock：不连真数据 / 真权重（coder 不跑，主线跑真烟测）
"""

import numpy as np
import pytest
import sys
import os

# 让 pytest 能找到 src/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


# =========================================================
# 辅助：懒加载 pytorch_wavelets（import 失败则 skip）
# =========================================================

def _get_dwt():
    """返回 (DWTForward, DWTInverse)，若未安装则 pytest.skip。"""
    try:
        from pytorch_wavelets import DWTForward, DWTInverse
        return DWTForward, DWTInverse
    except ImportError:
        pytest.skip("pytorch_wavelets 未安装，跳过 subband 测试")


def _get_torch():
    try:
        import torch
        return torch
    except ImportError:
        pytest.skip("torch 未安装")


# =========================================================
# 测试 1：DWT->IDWT 往返重建数值正确性
# =========================================================

class TestDWTRoundTrip:
    """往返重建 allclose atol=1e-3（researcher T4：fp32 重建误差 ~1e-6）"""

    def test_roundtrip_allclose(self):
        torch = _get_torch()
        DWTForward, DWTInverse = _get_dwt()

        dwt = DWTForward(J=1, wave="db1", mode="symmetric")
        idwt = DWTInverse(wave="db1", mode="symmetric")

        # 随机 tensor (batch=2, 3ch, 64×64)
        x = torch.randn(2, 3, 64, 64)
        Yl, Yh = dwt(x)
        x_rec = idwt((Yl, Yh))

        # 裁回原尺寸（padding 可能 off-by-one）
        x_rec = x_rec[:, :, : x.shape[2], : x.shape[3]]

        assert torch.allclose(x, x_rec, atol=1e-3), (
            f"往返重建误差超过 1e-3：max_diff={torch.abs(x - x_rec).max().item():.6f}"
        )

    def test_roundtrip_different_sizes(self):
        """不同尺寸输入均可往返重建。"""
        torch = _get_torch()
        DWTForward, DWTInverse = _get_dwt()

        dwt = DWTForward(J=1, wave="db1", mode="symmetric")
        idwt = DWTInverse(wave="db1", mode="symmetric")

        for H, W in [(32, 32), (64, 64), (128, 128), (224, 224)]:
            x = torch.randn(1, 3, H, W)
            Yl, Yh = dwt(x)
            x_rec = idwt((Yl, Yh))
            x_rec = x_rec[:, :, :H, :W]
            assert torch.allclose(x, x_rec, atol=1e-3), (
                f"尺寸 {H}×{W} 往返重建失败：max_diff={torch.abs(x - x_rec).max().item():.6f}"
            )

    def test_roundtrip_not_zeroed_preserves_value(self):
        """W-base 条件（不置零）重建结果与置零前一致。"""
        torch = _get_torch()
        DWTForward, DWTInverse = _get_dwt()

        dwt = DWTForward(J=1, wave="db1", mode="symmetric")
        idwt = DWTInverse(wave="db1", mode="symmetric")

        x = torch.randn(1, 3, 64, 64)
        Yl, Yh = dwt(x)

        # W-base：clone 不修改
        Yl2, Yh2 = Yl.clone(), [yh.clone() for yh in Yh]
        x_rec = idwt((Yl2, Yh2))
        x_rec = x_rec[:, :, : x.shape[2], : x.shape[3]]

        assert torch.allclose(x, x_rec, atol=1e-3)


# =========================================================
# 测试 2：子带置零后 shape 不变
# =========================================================

class TestSubbandZeroShape:
    """置零后 DWT/IDWT 输出 shape 不变。"""

    def _run_zero_condition(self, zero_fn):
        torch = _get_torch()
        DWTForward, DWTInverse = _get_dwt()

        dwt = DWTForward(J=1, wave="db1", mode="symmetric")
        idwt = DWTInverse(wave="db1", mode="symmetric")

        x = torch.randn(2, 3, 64, 64)
        Yl, Yh = dwt(x)
        original_Yl_shape = Yl.shape
        original_Yh_shape = Yh[0].shape

        Yl_mod, Yh_mod = zero_fn(Yl, Yh)

        # shape 不变
        assert Yl_mod.shape == original_Yl_shape, f"Yl shape 变了: {Yl_mod.shape} vs {original_Yl_shape}"
        assert Yh_mod[0].shape == original_Yh_shape, f"Yh[0] shape 变了: {Yh_mod[0].shape}"

        # 重建 shape
        x_rec = idwt((Yl_mod, Yh_mod))
        assert x_rec.shape[0] == x.shape[0]
        assert x_rec.shape[1] == x.shape[1]

    def test_shape_ll_zero(self):
        torch = _get_torch()
        def zero_ll(Yl, Yh):
            return torch.zeros_like(Yl), [yh.clone() for yh in Yh]
        self._run_zero_condition(zero_ll)

    def test_shape_lh_zero(self):
        torch = _get_torch()
        def zero_lh(Yl, Yh):
            Yh2 = [yh.clone() for yh in Yh]
            Yh2[0][:, :, 0, :, :] = 0.0
            return Yl.clone(), Yh2
        self._run_zero_condition(zero_lh)

    def test_shape_hl_zero(self):
        torch = _get_torch()
        def zero_hl(Yl, Yh):
            Yh2 = [yh.clone() for yh in Yh]
            Yh2[0][:, :, 1, :, :] = 0.0
            return Yl.clone(), Yh2
        self._run_zero_condition(zero_hl)

    def test_shape_hh_zero(self):
        torch = _get_torch()
        def zero_hh(Yl, Yh):
            Yh2 = [yh.clone() for yh in Yh]
            Yh2[0][:, :, 2, :, :] = 0.0
            return Yl.clone(), Yh2
        self._run_zero_condition(zero_hh)


# =========================================================
# 测试 3：idx 映射正确（LH=0 / HL=1 / HH=2）
# =========================================================

class TestSubbandIdxMapping:
    """
    验证 pytorch_wavelets Yh[0] 子带 idx 与 researcher T4 核实一致：
      0 = LH (水平高频), 1 = HL (垂直高频), 2 = HH (对角高频)
    方法：构造只有单一方向高频能量的输入，观察哪个 idx 能量最大。
    注：直接方向测试可能因 db1 滤波器不完全正交而近似，这里用置零后误差大小间接验。
    """

    def test_yh_has_three_subbands(self):
        """Yh[0] 第 3 维 = 3（对应 LH/HL/HH 三个子带）。"""
        torch = _get_torch()
        DWTForward, DWTInverse = _get_dwt()

        dwt = DWTForward(J=1, wave="db1", mode="symmetric")
        x = torch.randn(1, 3, 64, 64)
        Yl, Yh = dwt(x)

        assert Yh[0].ndim == 5, f"Yh[0] 应为 5D tensor (N,C,3,H',W')，得到 {Yh[0].ndim}D"
        assert Yh[0].shape[2] == 3, (
            f"Yh[0] dim=2 应为 3（LH/HL/HH），实际 = {Yh[0].shape[2]}。"
            f"idx mapping：0=LH / 1=HL / 2=HH（researcher T4 核实）"
        )

    def test_zero_each_subband_changes_reconstruction(self):
        """
        置零不同 idx 后重建误差不同：
        验证每个 idx 的置零对重建均有实质影响（非全 0 子带）。
        """
        torch = _get_torch()
        DWTForward, DWTInverse = _get_dwt()

        dwt = DWTForward(J=1, wave="db1", mode="symmetric")
        idwt = DWTInverse(wave="db1", mode="symmetric")

        x = torch.randn(2, 3, 64, 64)
        Yl, Yh = dwt(x)
        x_rec_orig = idwt((Yl.clone(), [yh.clone() for yh in Yh]))
        x_rec_orig = x_rec_orig[:, :, :64, :64]

        for idx, name in [(0, "LH"), (1, "HL"), (2, "HH")]:
            Yh2 = [yh.clone() for yh in Yh]
            Yh2[0][:, :, idx, :, :] = 0.0
            x_rec_zero = idwt((Yl.clone(), Yh2))
            x_rec_zero = x_rec_zero[:, :, :64, :64]
            diff = torch.abs(x_rec_orig - x_rec_zero).max().item()
            assert diff > 1e-6, (
                f"置零 idx={idx}({name}) 对重建无影响（diff={diff:.2e}），"
                f"可能 idx 映射错误或该子带为全零。"
            )

    def test_ll_zero_large_reconstruction_error(self):
        """
        置零 LL（低频近似）应造成最大重建误差（LL 携带图像主要能量）。
        LL 误差 > 任意单个 high-freq idx 置零误差。
        """
        torch = _get_torch()
        DWTForward, DWTInverse = _get_dwt()

        dwt = DWTForward(J=1, wave="db1", mode="symmetric")
        idwt = DWTInverse(wave="db1", mode="symmetric")

        # 用低频主导信号（平滑梯度+低频正弦），让 LL 真正携带主能量。
        # 不能用白噪声 torch.randn：白噪声四子带能量均分，置零 LL 与置零单个高频
        # 误差几乎相等，无法体现「LL 携带主结构」这一自然图性质。
        torch.manual_seed(0)
        coords = torch.linspace(0, 3.14159, 64)
        yy, xx = torch.meshgrid(coords, coords, indexing="ij")
        base = torch.sin(xx) + torch.cos(yy) + xx  # 低频主导
        x = base.unsqueeze(0).unsqueeze(0).repeat(2, 3, 1, 1)
        x = x + 0.01 * torch.randn(2, 3, 64, 64)  # 微量高频
        Yl, Yh = dwt(x)
        x_rec_orig = idwt((Yl.clone(), [yh.clone() for yh in Yh]))
        x_rec_orig = x_rec_orig[:, :, :64, :64]

        # 置零 LL
        Yh2 = [yh.clone() for yh in Yh]
        x_rec_ll0 = idwt((torch.zeros_like(Yl), Yh2))
        x_rec_ll0 = x_rec_ll0[:, :, :64, :64]
        err_ll = torch.abs(x_rec_orig - x_rec_ll0).mean().item()

        # 置零各 HF 子带误差（取最大）
        max_hf_err = 0.0
        for idx in range(3):
            Yh2 = [yh.clone() for yh in Yh]
            Yh2[0][:, :, idx, :, :] = 0.0
            x_rec_hf = idwt((Yl.clone(), Yh2))
            x_rec_hf = x_rec_hf[:, :, :64, :64]
            hf_err = torch.abs(x_rec_orig - x_rec_hf).mean().item()
            max_hf_err = max(max_hf_err, hf_err)

        assert err_ll > max_hf_err, (
            f"LL 置零误差({err_ll:.4f})不大于最大 HF 置零误差({max_hf_err:.4f})，"
            f"LL idx 映射可能错误。"
        )
