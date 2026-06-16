"""
pytest 冒烟测试 — MedAD-FailMap Phase 0 CPU 脚本
服务: MedAD-FailMap Phase 0 CI

覆盖:
  - stratify_eval.py: compute_mask_covariate, compute_contrast, percentile_bin
  - conspicuity_proxy.py: feat_sigma_global, feat_glcm, feat_fft_spectral_entropy,
                          feat_cnr_proxy_otsu, _otsu_threshold_numpy
  - incremental_stats.py: chi2_sf_approx, holm_correction, fdr_bh_correction,
                           pearson_r_numpy, linear_residuals,
                           run_c2_lr_test, run_c3_partial_corr, run_c4_risk_coverage
  - failure_boundary.py:  fit_boundary, run_b1, run_b2, run_b3, run_b4,
                           bootstrap_auroc_ci

所有测试用合成数据，不需要真实数据集，纯 CPU 几秒内跑完。
train_recon_ae.py (需 GPU/torch, 集成测试范围) 不在此冒烟测试范围。
"""

import csv
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

# 把 code/ 加到 sys.path (相对于 tests/ 上一级)
CODE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CODE_DIR))


# ============================================================
# stratify_eval.py 测试
# ============================================================

class TestStratifyEval:
    def test_compute_mask_covariate_empty(self):
        from stratify_eval import compute_mask_covariate
        mask = np.zeros((64, 64), dtype=np.uint8)
        assert compute_mask_covariate(mask) == 0

    def test_compute_mask_covariate_full(self):
        from stratify_eval import compute_mask_covariate
        mask = np.ones((64, 64), dtype=np.uint8) * 255
        size = compute_mask_covariate(mask)
        assert size == 64 * 64

    def test_compute_mask_covariate_small_region(self):
        from stratify_eval import compute_mask_covariate
        mask = np.zeros((64, 64), dtype=np.uint8)
        mask[10:20, 10:20] = 255   # 10x10 = 100 px
        size = compute_mask_covariate(mask)
        assert size == 100

    def test_compute_contrast_zero_mask(self):
        from stratify_eval import compute_contrast
        img  = np.random.rand(64, 64).astype(np.float32)
        mask = np.zeros((64, 64), dtype=np.uint8)
        c = compute_contrast(img, mask)
        assert c == 0.0

    def test_compute_contrast_positive(self):
        from stratify_eval import compute_contrast
        # 背景全黑 (0.0), 病灶区亮 (1.0) — 环带在黑色背景上, contrast 应该 > 0
        img  = np.zeros((64, 64), dtype=np.float32)
        mask = np.zeros((64, 64), dtype=np.uint8)
        mask[28:36, 28:36] = 255  # 病灶 mask (8x8)
        img[28:36, 28:36]  = 1.0  # 病灶像素值 = 1.0; 环带 = 0.0 (背景)
        c = compute_contrast(img, mask, dilation_px=3)
        assert c > 0.5  # |1.0 - 0.0| = 1.0, pooled -> ~1.0

    def test_percentile_bin_basic(self):
        from stratify_eval import percentile_bin
        vals = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], dtype=float)
        bins = percentile_bin(vals, n_bins=3)
        assert bins.shape == (10,)
        # 应该有 3 个不同的 bin 值
        assert len(np.unique(bins)) == 3


# ============================================================
# conspicuity_proxy.py 测试
# ============================================================

class TestConspicuityProxy:
    def _random_img(self, seed=0):
        rng = np.random.default_rng(seed)
        return rng.random((64, 64)).astype(np.float32)

    def test_sigma_global(self):
        from conspicuity_proxy import feat_sigma_global
        img = self._random_img()
        s = feat_sigma_global(img)
        assert isinstance(s, float)
        assert 0.0 <= s <= 1.0

    def test_sigma_uniform(self):
        from conspicuity_proxy import feat_sigma_global
        img = np.ones((64, 64), dtype=np.float32) * 0.5
        assert feat_sigma_global(img) == pytest.approx(0.0, abs=1e-6)

    def test_glcm_returns_two_floats(self):
        from conspicuity_proxy import feat_glcm
        img = self._random_img()
        cp, ct = feat_glcm(img)
        assert isinstance(cp, float)
        assert isinstance(ct, float)
        assert cp >= 0.0
        assert ct >= 0.0

    def test_fft_spectral_entropy(self):
        from conspicuity_proxy import feat_fft_spectral_entropy
        img = self._random_img()
        h = feat_fft_spectral_entropy(img)
        assert isinstance(h, float)
        assert h > 0.0

    def test_otsu_threshold_range(self):
        from conspicuity_proxy import _otsu_threshold_numpy
        img = self._random_img()
        t = _otsu_threshold_numpy(img)
        assert 0.0 <= t <= 1.0

    def test_cnr_proxy_uniform(self):
        from conspicuity_proxy import feat_cnr_proxy_otsu
        img = np.ones((64, 64), dtype=np.float32) * 0.5
        # uniform -> fg=bg -> CNR=0
        c = feat_cnr_proxy_otsu(img)
        assert c == pytest.approx(0.0, abs=1e-4)

    def test_cnr_proxy_bimodal(self):
        from conspicuity_proxy import feat_cnr_proxy_otsu
        # 两组均值相差大且各有内部方差 -> CNR 应明显 > 0
        rng = np.random.default_rng(7)
        img = np.zeros((64, 64), dtype=np.float32)
        img[:32, :] = rng.normal(0.1, 0.05, (32, 64)).clip(0, 1).astype(np.float32)
        img[32:, :] = rng.normal(0.8, 0.05, (32, 64)).clip(0, 1).astype(np.float32)
        c = feat_cnr_proxy_otsu(img)
        assert c > 1.0  # |0.8-0.1|/0.05 ~= 14, 即使 Otsu 不完美也应 >> 1

    def test_extract_features_end_to_end(self, tmp_path):
        """end-to-end: 写一张假图到磁盘, 调 extract_features"""
        from conspicuity_proxy import extract_features
        from PIL import Image
        img_arr = (np.random.rand(64, 64) * 255).astype(np.uint8)
        img_path = tmp_path / "test_img.png"
        Image.fromarray(img_arr, mode="L").save(img_path)
        sigma, cp, ct, fft_ent, cnr = extract_features(img_path, size=64)
        assert all(isinstance(v, float) for v in [sigma, cp, ct, fft_ent, cnr])


# ============================================================
# incremental_stats.py 测试
# ============================================================

class TestIncrementalStats:
    def _make_df(self, n=100, seed=42):
        """合成 SimpleDF: anomaly_score, label, conspicuity feats, size_px, contrast"""
        rng = np.random.default_rng(seed)
        labels = rng.integers(0, 2, size=n)
        scores = rng.random(n) + labels * 0.3
        rows = []
        for i in range(n):
            rows.append({
                "label":            str(labels[i]),
                "anomaly_score":    str(scores[i]),
                "sigma_global":     str(rng.random()),
                "glcm_cluster_prom": str(rng.random() * 100),
                "glcm_contrast":    str(rng.random() * 10),
                "fft_spectral_entropy": str(rng.random() * 10),
                "cnr_proxy_otsu":   str(rng.random()),
                "size_px":          str(rng.integers(10, 500)),
                "contrast":         str(rng.random()),
            })
        from incremental_stats import _rows_to_df
        return _rows_to_df(rows)

    def test_holm_correction_monotone(self):
        from incremental_stats import holm_correction
        pvals = np.array([0.001, 0.01, 0.05, 0.10])
        adj   = holm_correction(pvals)
        assert len(adj) == 4
        # adjusted p 应该 >= 原始 p
        assert np.all(adj >= pvals - 1e-10)
        # 不超过 1.0
        assert np.all(adj <= 1.0 + 1e-10)

    def test_fdr_bh_monotone(self):
        from incremental_stats import fdr_bh_correction
        pvals = np.array([0.001, 0.01, 0.05, 0.10])
        adj   = fdr_bh_correction(pvals)
        assert len(adj) == 4
        assert np.all(adj <= 1.0 + 1e-10)

    def test_chi2_sf_approx_large(self):
        from incremental_stats import chi2_sf_approx
        # chi2(1) = 3.84 -> p ~= 0.05
        p = chi2_sf_approx(3.84, df=1)
        assert abs(p - 0.05) < 0.01

    def test_chi2_sf_approx_zero(self):
        from incremental_stats import chi2_sf_approx
        p = chi2_sf_approx(0.0, df=1)
        assert p == pytest.approx(1.0)

    def test_pearson_r_numpy_perfect(self):
        from incremental_stats import pearson_r_numpy
        x = np.arange(10, dtype=float)
        y = 2.0 * x + 1.0
        r, p = pearson_r_numpy(x, y)
        assert r == pytest.approx(1.0, abs=1e-5)
        assert p < 0.001

    def test_pearson_r_numpy_uncorrelated(self):
        from incremental_stats import pearson_r_numpy
        rng = np.random.default_rng(0)
        x   = rng.random(100)
        y   = rng.random(100)
        r, p = pearson_r_numpy(x, y)
        assert abs(r) < 0.4   # 随机数相关性应该小

    def test_linear_residuals_zero_for_perfect(self):
        from incremental_stats import linear_residuals
        n = 20
        X = np.arange(n, dtype=float).reshape(-1, 1)
        y = 3.0 * X.ravel() + 2.0
        resid = linear_residuals(X, y)
        assert np.max(np.abs(resid)) < 1e-8

    def test_c2_lr_test_runs(self, tmp_path):
        from incremental_stats import run_c2_lr_test, CONSPICUITY_COLS
        df     = self._make_df(n=80)
        out    = tmp_path / "c2.csv"
        run_c2_lr_test(df, CONSPICUITY_COLS, out)
        assert out.exists()
        with open(out) as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == len(CONSPICUITY_COLS)
        for row in rows:
            assert "chi2_stat" in row
            assert "p_holm" in row
            assert "p_fdr_bh" in row

    def test_c3_partial_corr_runs(self, tmp_path):
        from incremental_stats import run_c3_partial_corr, CONSPICUITY_COLS
        df  = self._make_df(n=80)
        out = tmp_path / "c3.csv"
        run_c3_partial_corr(df, CONSPICUITY_COLS, ["size_px", "contrast"], out)
        assert out.exists()
        rows = list(csv.DictReader(open(out)))
        assert len(rows) == len(CONSPICUITY_COLS)

    def test_c4_risk_coverage_runs(self, tmp_path):
        from incremental_stats import run_c4_risk_coverage
        df  = self._make_df(n=100)
        out = tmp_path / "c4.csv"
        run_c4_risk_coverage(df, "cnr_proxy_otsu", out)
        assert out.exists()
        rows = list(csv.DictReader(open(out)))
        # 0.10 ~ 1.00 step 0.05 = 19 行
        assert len(rows) == 19
        coverages = [float(r["coverage"]) for r in rows]
        assert min(coverages) == pytest.approx(0.10, abs=0.01)
        assert max(coverages) == pytest.approx(1.00, abs=0.01)


# ============================================================
# failure_boundary.py 测试
# ============================================================

class TestFailureBoundary:
    def _make_brats_data(self, n=200, seed=0):
        rng = np.random.default_rng(seed)
        size_px  = rng.integers(10, 500, size=n).astype(float)
        contrast = rng.random(n)
        # 大 size + 高 contrast -> 容易检出 (anomaly score 高)
        scores   = 0.001 * size_px + 0.3 * contrast + rng.random(n) * 0.2
        labels   = np.ones(n, dtype=int)   # all tumor
        return {
            "anomaly_score": scores,
            "label":         labels,
            "size_px":       size_px,
            "contrast":      contrast,
        }

    def _make_ham_data(self, n=100, seed=1):
        rng = np.random.default_rng(seed)
        return {
            "anomaly_score":  rng.random(n),
            "label":          rng.integers(0, 2, size=n).astype(int),
            "sigma_global":   rng.random(n),
            "cnr_proxy_otsu": rng.random(n),
        }

    def test_fit_boundary_lr(self):
        from failure_boundary import fit_boundary
        rng = np.random.default_rng(0)
        X   = rng.random((50, 2))
        y   = rng.integers(0, 2, size=50)
        clf = fit_boundary(X, y, "lr")
        proba = clf.predict_proba(X)[:, 1]
        assert proba.shape == (50,)
        assert np.all((proba >= 0) & (proba <= 1))

    def test_fit_boundary_gbm(self):
        from failure_boundary import fit_boundary
        rng = np.random.default_rng(0)
        X   = rng.random((50, 2))
        y   = rng.integers(0, 2, size=50)
        clf = fit_boundary(X, y, "gbm")
        proba = clf.predict_proba(X)[:, 1]
        assert proba.shape == (50,)

    def test_bootstrap_auroc_ci(self):
        from failure_boundary import bootstrap_auroc_ci
        rng    = np.random.default_rng(0)
        y_true = np.array([0]*50 + [1]*50)
        scores = np.concatenate([rng.random(50), rng.random(50) + 0.5])
        lo, hi = bootstrap_auroc_ci(y_true, scores, n_boot=100)
        assert 0.0 <= lo <= hi <= 1.0

    def test_run_b1_outputs_csv(self, tmp_path):
        from failure_boundary import run_b1
        brats = self._make_brats_data()
        result = run_b1(brats, tmp_path)
        out = tmp_path / "boundary_B1_coefs.csv"
        assert out.exists()
        rows = list(csv.DictReader(open(out)))
        assert len(rows) >= 2   # size_only + size+contrast + gbm
        for r in rows:
            assert "in_domain_auroc" in r

    def test_run_b2_outputs_csv(self, tmp_path):
        from failure_boundary import run_b1, run_b2
        brats = self._make_brats_data()
        brats = run_b1(brats, tmp_path)
        ham   = self._make_ham_data()
        run_b2(brats, ham, tmp_path)
        out = tmp_path / "boundary_B2_extrapolation.csv"
        assert out.exists()

    def test_run_b3_outputs_csv(self, tmp_path):
        from failure_boundary import run_b1, run_b3
        brats = self._make_brats_data()
        brats = run_b1(brats, tmp_path)
        run_b3(brats, tmp_path)
        out = tmp_path / "boundary_B3_baseline.csv"
        assert out.exists()
        rows = list(csv.DictReader(open(out)))
        assert len(rows) >= 1

    def test_run_b4_outputs_csv(self, tmp_path):
        from failure_boundary import run_b1, run_b4
        brats = self._make_brats_data(n=300)
        brats = run_b1(brats, tmp_path)
        run_b4(brats, tmp_path)
        out = tmp_path / "boundary_B4_extrapolation.csv"
        assert out.exists()
        rows = list(csv.DictReader(open(out)))
        assert len(rows) >= 1

    def test_holm_correction(self):
        from failure_boundary import holm_correction
        pvals = np.array([0.01, 0.04, 0.02])
        adj   = holm_correction(pvals)
        assert len(adj) == 3
        assert np.all(adj >= pvals - 1e-10)
        assert np.all(adj <= 1.0 + 1e-10)
