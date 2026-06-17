"""
test_distribution_overlap.py — OVL/BC 固化落盘脚本单元测试
服务: MedAD-FailMap PR-7c 可复现性缺口修复

覆盖:
  D1: OVL 对称性（swap source/target 结果不变）
  D2: 同分布 OVL≈1 （同一数组 vs 自身）
  D3: 不相交分布 OVL≈0（两个不重叠区间）
  D4: 不相交分布 BC≈0
  D5: bin 口径稳定（钉死 bin 常量与代码中 _get_bins 一致）
  D6: 已知简单分布 OVL 精确值验证
  D7: compute_pair_overlap 输出 csv schema
  D8: n_components log bin 覆盖 BraTS(1~35) / IDRiD(1~2000) 不崩溃
  D9: 空输入（N=0）OVL=0/BC=0 不崩溃
  D10: 值越界（area_ratio >1）被 bin 范围忽略，不 crash

全部合成数据，纯 CPU，无真实数据依赖。
"""

import csv
import sys
from pathlib import Path

import numpy as np
import pytest

# 把 code/ 加到 sys.path
CODE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CODE_DIR))

from distribution_overlap import (
    compute_ovl_bc,
    compute_pair_overlap,
    _get_bins,
    BIN_SCHEME_AREA_RATIO,
    BIN_SCHEME_NCOMP,
    N_BINS_AREA_RATIO,
    N_BINS_NCOMP,
    _AREA_RATIO_BINS,
    _NCOMP_BINS,
)


# ============================================================
# Fixture helpers
# ============================================================

def _make_single_col_csv(tmp_path, name, col, values):
    """写单列 csv（col → values），返回 Path。"""
    p = tmp_path / f"{name}.csv"
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[col])
        w.writeheader()
        for v in values:
            w.writerow({col: str(v)})
    return p


# ============================================================
# D1: OVL 对称性
# ============================================================

class TestOVLSymmetry:
    def test_ovl_symmetric(self):
        """D1: OVL(A, B) == OVL(B, A)（顺序不影响结果）"""
        rng = np.random.default_rng(0)
        A = rng.uniform(0.0, 0.5, size=200)
        B = rng.uniform(0.3, 1.0, size=200)
        bins, _, _ = _get_bins("area_ratio")

        ovl_ab, bc_ab = compute_ovl_bc(A, B, bins)
        ovl_ba, bc_ba = compute_ovl_bc(B, A, bins)

        assert ovl_ab == pytest.approx(ovl_ba, abs=1e-10), (
            f"OVL 应对称: OVL(A,B)={ovl_ab:.6f} != OVL(B,A)={ovl_ba:.6f}"
        )
        assert bc_ab == pytest.approx(bc_ba, abs=1e-10), (
            f"BC 应对称: BC(A,B)={bc_ab:.6f} != BC(B,A)={bc_ba:.6f}"
        )

    def test_ovl_symmetric_ncomp(self):
        """D1 (n_components): OVL 对称性在对数 bin 下同样成立"""
        rng = np.random.default_rng(1)
        A = rng.integers(1, 10,   size=100).astype(float)
        B = rng.integers(5, 2000, size=100).astype(float)
        bins, _, _ = _get_bins("n_components")

        ovl_ab, _ = compute_ovl_bc(A, B, bins)
        ovl_ba, _ = compute_ovl_bc(B, A, bins)

        assert ovl_ab == pytest.approx(ovl_ba, abs=1e-10)


# ============================================================
# D2: 同分布 OVL≈1
# ============================================================

class TestSameDistribution:
    def test_same_array_ovl_is_1(self):
        """D2: 同一数组 vs 自身 OVL=1.0（完全重叠）"""
        rng = np.random.default_rng(42)
        A = rng.uniform(0.0, 1.0, size=500)
        bins, _, _ = _get_bins("area_ratio")

        ovl, bc = compute_ovl_bc(A, A, bins)

        assert ovl == pytest.approx(1.0, abs=1e-6), (
            f"同分布 OVL 应≈1，得 {ovl:.6f}"
        )
        assert bc == pytest.approx(1.0, abs=1e-6), (
            f"同分布 BC 应≈1，得 {bc:.6f}"
        )

    def test_same_ncomp_ovl_is_1(self):
        """D2 (n_components): 对数 bin 下同分布 OVL≈1"""
        rng = np.random.default_rng(7)
        A = rng.integers(1, 300, size=300).astype(float)
        bins, _, _ = _get_bins("n_components")

        ovl, bc = compute_ovl_bc(A, A, bins)

        assert ovl == pytest.approx(1.0, abs=1e-6), f"同分布 OVL(ncomp) 应≈1，得 {ovl:.6f}"
        assert bc  == pytest.approx(1.0, abs=1e-6), f"同分布 BC(ncomp)  应≈1，得 {bc:.6f}"


# ============================================================
# D3 + D4: 不相交分布 OVL≈0 / BC≈0
# ============================================================

class TestDisjointDistributions:
    def test_disjoint_ovl_near_zero(self):
        """D3: 两个不重叠区间的 OVL 应接近 0"""
        # A 全在 [0, 0.2]，B 全在 [0.8, 1.0]（不重叠）
        A = np.linspace(0.01, 0.19, 200)
        B = np.linspace(0.81, 0.99, 200)
        bins, _, _ = _get_bins("area_ratio")

        ovl, bc = compute_ovl_bc(A, B, bins)

        assert ovl < 0.05, f"不相交分布 OVL 应<0.05，得 {ovl:.6f}"

    def test_disjoint_bc_near_zero(self):
        """D4: 不相交分布 BC 应接近 0"""
        A = np.linspace(0.01, 0.19, 200)
        B = np.linspace(0.81, 0.99, 200)
        bins, _, _ = _get_bins("area_ratio")

        _, bc = compute_ovl_bc(A, B, bins)

        assert bc < 0.05, f"不相交分布 BC 应<0.05，得 {bc:.6f}"

    def test_disjoint_ncomp_near_zero(self):
        """D3+D4 (n_components): 低 vs 高 n_comp 分布接近不重叠时 OVL 低"""
        # A: n_comp 1-3 (BraTS-like), B: n_comp 100-500 (IDRiD-like)
        A = np.array([1, 1, 2, 2, 3, 1, 2, 1, 3, 2] * 20, dtype=float)
        B = np.array([100, 150, 200, 250, 300, 350, 400, 450, 500, 120] * 20, dtype=float)
        bins, _, _ = _get_bins("n_components")

        ovl, bc = compute_ovl_bc(A, B, bins)

        assert ovl < 0.2, f"低 vs 高 n_comp OVL 应<0.2，得 {ovl:.4f}"
        assert bc  < 0.2, f"低 vs 高 n_comp BC  应<0.2，得 {bc:.4f}"


# ============================================================
# D5: bin 口径稳定（常量一致性验证）
# ============================================================

class TestBinStability:
    def test_area_ratio_bin_edges_shape(self):
        """D5: _AREA_RATIO_BINS 有 101 个 edge（100 bins）"""
        assert len(_AREA_RATIO_BINS) == 101, (
            f"area_ratio bin edges 应为 101，得 {len(_AREA_RATIO_BINS)}"
        )
        assert N_BINS_AREA_RATIO == 100

    def test_ncomp_bin_edges_shape(self):
        """D5: _NCOMP_BINS 有 51 个 edge（50 bins）"""
        assert len(_NCOMP_BINS) == 51, (
            f"n_components bin edges 应为 51，得 {len(_NCOMP_BINS)}"
        )
        assert N_BINS_NCOMP == 50

    def test_area_ratio_bin_range(self):
        """D5: area_ratio bins 从 0 到 1"""
        assert _AREA_RATIO_BINS[0] == pytest.approx(0.0)
        assert _AREA_RATIO_BINS[-1] == pytest.approx(1.0)

    def test_ncomp_bin_range(self):
        """D5: n_components bins 从 ~0.5 到 ~3000"""
        assert _NCOMP_BINS[0] == pytest.approx(0.5, rel=0.01)
        assert _NCOMP_BINS[-1] == pytest.approx(3000.0, rel=0.01)

    def test_bin_scheme_names_unchanged(self):
        """D5: bin scheme 名称常量与 _get_bins 返回一致"""
        _, scheme_ar, n_ar = _get_bins("area_ratio")
        _, scheme_nc, n_nc = _get_bins("n_components")

        assert scheme_ar == BIN_SCHEME_AREA_RATIO
        assert scheme_nc == BIN_SCHEME_NCOMP
        assert n_ar == N_BINS_AREA_RATIO
        assert n_nc == N_BINS_NCOMP

    def test_get_bins_returns_copy(self):
        """D5: _get_bins 返回副本，外部修改不影响内部常量"""
        edges1, _, _ = _get_bins("area_ratio")
        edges1[0] = 999.0
        edges2, _, _ = _get_bins("area_ratio")
        assert edges2[0] == pytest.approx(0.0), (
            "_get_bins 应返回副本，修改外部不影响内部常量"
        )

    def test_same_bins_give_same_result(self):
        """D5: 两次调用相同 bin 方案，结果完全一致"""
        rng = np.random.default_rng(10)
        A = rng.uniform(0, 1, 100)
        B = rng.uniform(0, 1, 100)

        bins1, _, _ = _get_bins("area_ratio")
        bins2, _, _ = _get_bins("area_ratio")

        ovl1, bc1 = compute_ovl_bc(A, B, bins1)
        ovl2, bc2 = compute_ovl_bc(A, B, bins2)

        assert ovl1 == ovl2, "相同 bin 方案两次结果应完全相同"
        assert bc1  == bc2


# ============================================================
# D6: 已知简单分布精确值
# ============================================================

class TestKnownValues:
    def test_uniform_self_ovl(self):
        """D6: 均匀分布自身 OVL=1，BC=1"""
        A = np.random.default_rng(99).uniform(0, 1, 1000)
        bins, _, _ = _get_bins("area_ratio")
        ovl, bc = compute_ovl_bc(A, A, bins)
        assert ovl == pytest.approx(1.0, abs=1e-6)
        assert bc  == pytest.approx(1.0, abs=1e-6)

    def test_ovl_in_range_01(self):
        """D6: OVL 与 BC 均在 [0,1] 范围内"""
        rng = np.random.default_rng(5)
        for _ in range(5):
            A = rng.uniform(0, 1, 100)
            B = rng.uniform(0, 1, 100)
            bins, _, _ = _get_bins("area_ratio")
            ovl, bc = compute_ovl_bc(A, B, bins)
            assert 0.0 <= ovl <= 1.0, f"OVL 超出 [0,1]: {ovl}"
            assert 0.0 <= bc  <= 1.0, f"BC 超出 [0,1]: {bc}"


# ============================================================
# D7: compute_pair_overlap 输出 csv schema
# ============================================================

class TestComputePairOverlap:
    def test_output_csv_schema(self, tmp_path):
        """D7: 输出 csv 含必要列"""
        rng = np.random.default_rng(3)
        A = rng.uniform(0, 1, 100)
        B = rng.uniform(0, 1, 100)

        src_csv = _make_single_col_csv(tmp_path, "src", "area_ratio_brain", A)
        tgt_csv = _make_single_col_csv(tmp_path, "tgt", "area_ratio_fov",   B)

        result = compute_pair_overlap(
            source_csv=str(src_csv),
            target_csv=str(tgt_csv),
            feature="area_ratio",
            source_col="area_ratio_brain",
            target_col="area_ratio_fov",
            pair_name="brats_idrid_test",
            out_dir=str(tmp_path / "out"),
        )

        # 检查返回 dict
        required_keys = ["pair", "feature", "n_bins", "bin_scheme",
                         "OVL", "BC", "n_source", "n_target"]
        for k in required_keys:
            assert k in result, f"返回 dict 缺少键: {k}"

        assert result["n_source"] == 100
        assert result["n_target"] == 100
        assert result["n_bins"]   == N_BINS_AREA_RATIO
        assert result["bin_scheme"] == BIN_SCHEME_AREA_RATIO
        assert 0.0 <= result["OVL"] <= 1.0
        assert 0.0 <= result["BC"]  <= 1.0

        # 检查 csv 文件
        out_csv = tmp_path / "out" / "distribution_overlap_brats_idrid_test_area_ratio.csv"
        assert out_csv.exists(), f"输出 csv 未生成: {out_csv}"

        with open(out_csv, newline="") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 1, "输出 csv 应有 1 行"
        for k in required_keys:
            assert k in rows[0], f"csv 缺少列: {k}"

    def test_output_csv_ncomp_schema(self, tmp_path):
        """D7 (n_components): n_comp 特征输出 csv bin_scheme 正确"""
        rng = np.random.default_rng(4)
        A = rng.integers(1, 50,   size=80).astype(float)
        B = rng.integers(1, 2000, size=80).astype(float)

        src_csv = _make_single_col_csv(tmp_path, "src_nc", "n_components", A)
        tgt_csv = _make_single_col_csv(tmp_path, "tgt_nc", "n_components", B)

        result = compute_pair_overlap(
            source_csv=str(src_csv),
            target_csv=str(tgt_csv),
            feature="n_components",
            source_col="n_components",
            target_col="n_components",
            pair_name="brats_idrid_nc_test",
            out_dir=str(tmp_path / "out_nc"),
        )

        assert result["n_bins"]   == N_BINS_NCOMP
        assert result["bin_scheme"] == BIN_SCHEME_NCOMP


# ============================================================
# D8: n_components 覆盖 BraTS / IDRiD 范围不崩溃
# ============================================================

class TestNCompRange:
    def test_brats_range_no_crash(self):
        """D8: BraTS n_comp [1,35] 在 log bin 下不崩溃"""
        A = np.arange(1, 36, dtype=float)
        B = np.arange(1, 10, dtype=float)
        bins, _, _ = _get_bins("n_components")
        ovl, bc = compute_ovl_bc(A, B, bins)
        assert 0.0 <= ovl <= 1.0
        assert 0.0 <= bc  <= 1.0

    def test_idrid_range_no_crash(self):
        """D8: IDRiD n_comp [1,2000] 在 log bin 下不崩溃"""
        rng = np.random.default_rng(8)
        A = rng.integers(1, 35,   size=50).astype(float)   # BraTS-like
        B = rng.integers(1, 2000, size=54).astype(float)   # IDRiD-like
        bins, _, _ = _get_bins("n_components")
        ovl, bc = compute_ovl_bc(A, B, bins)
        assert 0.0 <= ovl <= 1.0
        assert 0.0 <= bc  <= 1.0


# ============================================================
# D9: 空输入 OVL=0/BC=0 不崩溃
# ============================================================

class TestEmptyInput:
    def test_empty_source_returns_zero(self):
        """D9: source 为空 → OVL=0, BC=0"""
        A = np.array([], dtype=float)
        B = np.array([0.1, 0.2, 0.3], dtype=float)
        bins, _, _ = _get_bins("area_ratio")
        ovl, bc = compute_ovl_bc(A, B, bins)
        assert ovl == 0.0
        assert bc  == 0.0

    def test_empty_target_returns_zero(self):
        """D9: target 为空 → OVL=0, BC=0"""
        A = np.array([0.1, 0.2, 0.3], dtype=float)
        B = np.array([], dtype=float)
        bins, _, _ = _get_bins("area_ratio")
        ovl, bc = compute_ovl_bc(A, B, bins)
        assert ovl == 0.0
        assert bc  == 0.0

    def test_both_empty_returns_zero(self):
        """D9: 两端均空 → OVL=0, BC=0"""
        A = np.array([], dtype=float)
        B = np.array([], dtype=float)
        bins, _, _ = _get_bins("area_ratio")
        ovl, bc = compute_ovl_bc(A, B, bins)
        assert ovl == 0.0
        assert bc  == 0.0


# ============================================================
# D10: 值越界不 crash（bin 范围外被忽略）
# ============================================================

class TestOutOfRangeValues:
    def test_area_ratio_gt1_ignored(self):
        """D10: area_ratio > 1 的值被 bin 范围忽略，不 crash"""
        A = np.array([0.1, 0.2, 1.5, 2.0, 0.3], dtype=float)  # 含 >1
        B = np.array([0.1, 0.2, 0.3], dtype=float)
        bins, _, _ = _get_bins("area_ratio")
        # 不应抛异常
        ovl, bc = compute_ovl_bc(A, B, bins)
        assert 0.0 <= ovl <= 1.0
        assert 0.0 <= bc  <= 1.0

    def test_area_ratio_negative_ignored(self):
        """D10: 负值被 bin 范围忽略，不 crash"""
        A = np.array([-0.1, 0.1, 0.2, 0.3], dtype=float)
        B = np.array([0.1, 0.2, 0.3], dtype=float)
        bins, _, _ = _get_bins("area_ratio")
        ovl, bc = compute_ovl_bc(A, B, bins)
        assert 0.0 <= ovl <= 1.0
        assert 0.0 <= bc  <= 1.0

    def test_missing_source_col_raises(self, tmp_path):
        """D10: source csv 列不存在 → ValueError"""
        src_csv = _make_single_col_csv(tmp_path, "src_bad", "wrong_col",
                                       [0.1, 0.2, 0.3])
        tgt_csv = _make_single_col_csv(tmp_path, "tgt_ok", "area_ratio_fov",
                                       [0.1, 0.2])
        with pytest.raises(ValueError, match="无有效值"):
            compute_pair_overlap(
                source_csv=str(src_csv),
                target_csv=str(tgt_csv),
                feature="area_ratio",
                source_col="area_ratio_brain",   # 不存在此列
                target_col="area_ratio_fov",
                pair_name="bad_test",
                out_dir=None,
            )
