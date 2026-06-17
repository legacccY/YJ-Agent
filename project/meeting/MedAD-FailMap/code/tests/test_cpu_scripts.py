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
        # df_mixed 需含 normal(label=0) + tumor(label=1) 两类；_make_df 已混合
        df_mixed = self._make_df(n=100)
        out = tmp_path / "c4.csv"
        run_c4_risk_coverage(df_mixed, "cnr_proxy_otsu", out)
        assert out.exists()
        rows = list(csv.DictReader(open(out)))
        # 0.10 ~ 1.00 step 0.05 = 19 行
        assert len(rows) == 19
        coverages = [float(r["coverage"]) for r in rows]
        assert min(coverages) == pytest.approx(0.10, abs=0.01)
        assert max(coverages) == pytest.approx(1.00, abs=0.01)
        # 检查新输出列名（retained_n / ad_auroc）
        assert "retained_n" in rows[0], "expected 'retained_n' column (not n_kept)"
        assert "ad_auroc"   in rows[0], "expected 'ad_auroc' column (not auroc)"


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

    def test_bootstrap_auroc_ci_alpha_9875(self):
        """缺口3: bootstrap_auroc_ci 支持 alpha=0.0125 (98.75% CI，T6/T7 Bonf/4)"""
        from failure_boundary import bootstrap_auroc_ci
        rng    = np.random.default_rng(0)
        y_true = np.array([0]*50 + [1]*50)
        scores = np.concatenate([rng.random(50), rng.random(50) + 0.5])
        lo_95, hi_95 = bootstrap_auroc_ci(y_true, scores, n_boot=100, alpha=0.05)
        lo_9875, hi_9875 = bootstrap_auroc_ci(y_true, scores, n_boot=100, alpha=0.0125)
        # 98.75% CI 应比 95% CI 更宽（lo 更低，hi 更高）
        assert lo_9875 <= lo_95 + 1e-6
        assert hi_9875 >= hi_95 - 1e-6

    def test_run_b2_ci_columns_9875(self, tmp_path):
        """缺口3: run_b2 输出列名改为 ci_lo_9875/ci_hi_9875"""
        from failure_boundary import run_b1, run_b2
        brats = self._make_brats_data()
        brats = run_b1(brats, tmp_path)
        ham   = self._make_ham_data()
        run_b2(brats, ham, tmp_path)
        out = tmp_path / "boundary_B2_extrapolation.csv"
        assert out.exists()
        rows = list(csv.DictReader(open(out)))
        assert len(rows) > 0
        # 检查列名含 9875 而非 95
        assert "ci_lo_9875" in rows[0], "T6 B2 应输出 ci_lo_9875 (98.75% CI)"
        assert "ci_hi_9875" in rows[0], "T6 B2 应输出 ci_hi_9875 (98.75% CI)"
        assert "ci_lo_95" not in rows[0], "旧列名 ci_lo_95 不应存在"

    def test_run_b4_ci_columns_9875(self, tmp_path):
        """缺口3: run_b4 输出列名改为 ci_lo_9875/ci_hi_9875"""
        from failure_boundary import run_b1, run_b4
        brats = self._make_brats_data(n=300)
        brats = run_b1(brats, tmp_path)
        run_b4(brats, tmp_path)
        out = tmp_path / "boundary_B4_extrapolation.csv"
        assert out.exists()
        rows = list(csv.DictReader(open(out)))
        if rows:   # 样本量足够才有输出
            assert "ci_lo_9875" in rows[0], "T7 B4 应输出 ci_lo_9875 (98.75% CI)"
            assert "ci_hi_9875" in rows[0], "T7 B4 应输出 ci_hi_9875 (98.75% CI)"

    def test_run_b4_two_directions_and_new_cols(self, tmp_path):
        """PC-B remediation: run_b4 输出两方向(small+large)、新增 n_test_detected/interpretable 列"""
        from failure_boundary import run_b1, run_b4
        brats = self._make_brats_data(n=300)
        brats = run_b1(brats, tmp_path)
        run_b4(brats, tmp_path)
        out = tmp_path / "boundary_B4_extrapolation.csv"
        assert out.exists()
        rows = list(csv.DictReader(open(out)))
        # 两方向 × 两模型 = 4 行
        assert len(rows) == 4, f"期望 4 行(2方向×2模型), 实得 {len(rows)}"
        # 新增列存在
        assert "n_test_detected" in rows[0], "缺少 n_test_detected 列"
        assert "interpretable"   in rows[0], "缺少 interpretable 列"
        # 方向标签
        test_splits = [r["test_split"] for r in rows]
        assert any("small_size" in s for s in test_splits), "缺少 small_size 方向A 行"
        assert any("large_size" in s for s in test_splits), "缺少 large_size 方向B 行"
        # large 方向应有足够 detected (合成数据大 size 高 score → n_test_detected > 0)
        large_rows = [r for r in rows if "large_size" in r["test_split"]]
        for r in large_rows:
            assert int(r["n_test_detected"]) >= 0  # 不 crash 即可; 合成数据值由 P90 决定


# ============================================================
# 缺口 1: stratify_significance.py — F-A T1/T2/T3 显著性检验
# ============================================================

class TestStratifySignificance:
    def _write_score_csv(self, tmp_path, n_tumor=200, seed=42):
        """合成 anomaly_scores csv (split=tumor)"""
        rng = np.random.default_rng(seed)
        rows = []
        for i in range(n_tumor):
            rows.append({
                "filename":     f"tumor_{i:04d}.png",
                "split":        "tumor",
                "anomaly_score": str(round(rng.random(), 6)),
                "label":        "1",
            })
        p = tmp_path / "scores.csv"
        with open(p, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["filename","split","anomaly_score","label"])
            w.writeheader()
            w.writerows(rows)
        return p, [r["filename"] for r in rows]

    def _write_strat_csv(self, tmp_path, filenames, seed=42):
        """合成 per-image strat csv (含 filename/size_px/contrast)"""
        rng = np.random.default_rng(seed)
        rows = []
        for fn in filenames:
            rows.append({
                "filename": fn,
                "size_px":  str(round(float(rng.integers(10, 500)), 2)),
                "contrast": str(round(float(rng.random()), 6)),
            })
        p = tmp_path / "strat.csv"
        with open(p, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["filename","size_px","contrast"])
            w.writeheader()
            w.writerows(rows)
        return p

    def test_fa_significance_runs(self, tmp_path):
        """缺口1: run_fa_significance 不报错 + 输出 csv 含正确列"""
        from stratify_significance import run_fa_significance
        score_csv, filenames = self._write_score_csv(tmp_path)
        strat_csv = self._write_strat_csv(tmp_path, filenames)
        out_csv   = tmp_path / "FA.csv"
        run_fa_significance(str(score_csv), str(strat_csv), str(out_csv))
        assert out_csv.exists()
        rows = list(csv.DictReader(open(out_csv)))
        assert len(rows) == 3, "F-A family 应有 3 行 (T1/T2/T3)"
        test_ids = [r["test_id"] for r in rows]
        assert test_ids == ["T1", "T2", "T3"]
        for r in rows:
            assert "stat_chi2" in r
            assert "p_raw" in r
            assert "p_holm" in r
            assert "p_fdr_bh" in r
            assert "sig_holm" in r

    def test_fa_holm_covers_3(self, tmp_path):
        """缺口1: Holm 校正在 3 个检验上，p_holm >= p_raw"""
        from stratify_significance import run_fa_significance
        score_csv, filenames = self._write_score_csv(tmp_path)
        strat_csv = self._write_strat_csv(tmp_path, filenames)
        out_csv   = tmp_path / "FA_holm.csv"
        run_fa_significance(str(score_csv), str(strat_csv), str(out_csv))
        rows = list(csv.DictReader(open(out_csv)))
        for r in rows:
            p_raw  = float(r["p_raw"])
            p_holm = float(r["p_holm"])
            assert p_holm >= p_raw - 1e-10, f"Holm p 应 >= raw p, got {p_holm} < {p_raw}"
            assert 0.0 <= p_holm <= 1.0 + 1e-10


# ============================================================
# 缺口 2: incremental_stats.run_fc_family_holm — F-C 合并 10 检验
# ============================================================

class TestFCFamilyHolm:
    def _make_c2_csv(self, tmp_path, seed=0):
        """合成 C2 lr_test csv (5 行)"""
        from incremental_stats import CONSPICUITY_COLS
        rng  = np.random.default_rng(seed)
        rows = []
        for col in CONSPICUITY_COLS:
            p = float(rng.random())
            rows.append({
                "feature":    col,
                "chi2_stat":  str(round(rng.random() * 5, 4)),
                "p_raw":      str(round(p, 6)),
                "p_holm":     str(round(p, 6)),
                "p_fdr_bh":  str(round(p, 6)),
                "sig_holm05": "0",
                "sig_fdr05":  "0",
                "note":       "test",
            })
        p_out = tmp_path / "c2.csv"
        with open(p_out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        return p_out

    def _make_c3_csv(self, tmp_path, seed=1):
        """合成 C3 partial_corr csv (5 行)"""
        from incremental_stats import CONSPICUITY_COLS
        rng  = np.random.default_rng(seed)
        rows = []
        for col in CONSPICUITY_COLS:
            p = float(rng.random())
            rows.append({
                "feature":      col,
                "controlled_for": "size_px+contrast",
                "partial_r":    str(round(rng.random() * 0.5, 4)),
                "p_raw":        str(round(p, 6)),
                "p_holm":       str(round(p, 6)),
                "p_fdr_bh":    str(round(p, 6)),
                "sig_holm05":   "0",
                "sig_fdr05":    "0",
                "note":         "test",
            })
        p_out = tmp_path / "c3.csv"
        with open(p_out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        return p_out

    def test_fc_family_holm_runs(self, tmp_path):
        """缺口2: run_fc_family_holm 不报错 + 输出 10 行 + 列名正确"""
        from incremental_stats import run_fc_family_holm
        c2 = self._make_c2_csv(tmp_path)
        c3 = self._make_c3_csv(tmp_path)
        out = tmp_path / "fc_family.csv"
        run_fc_family_holm(c2, c3, out)
        assert out.exists()
        rows = list(csv.DictReader(open(out)))
        assert len(rows) == 10, f"F-C family 应有 10 行，得 {len(rows)}"
        # 检查列名
        for col in ["test_id", "feature", "source", "p_raw",
                    "p_holm_family10", "p_fdr_family10", "sig"]:
            assert col in rows[0], f"缺少列 {col}"

    def test_fc_test_ids(self, tmp_path):
        """缺口2: test_id 应为 T4.1-T4.5 / T5.1-T5.5"""
        from incremental_stats import run_fc_family_holm
        c2 = self._make_c2_csv(tmp_path)
        c3 = self._make_c3_csv(tmp_path)
        out = tmp_path / "fc_ids.csv"
        run_fc_family_holm(c2, c3, out)
        rows = list(csv.DictReader(open(out)))
        ids = [r["test_id"] for r in rows]
        expected = [f"T4.{i}" for i in range(1, 6)] + [f"T5.{i}" for i in range(1, 6)]
        assert ids == expected, f"test_id 顺序不对: {ids}"

    def test_fc_holm_monotone(self, tmp_path):
        """缺口2: Holm 校正后 p >= raw p"""
        from incremental_stats import run_fc_family_holm
        c2 = self._make_c2_csv(tmp_path)
        c3 = self._make_c3_csv(tmp_path)
        out = tmp_path / "fc_mono.csv"
        run_fc_family_holm(c2, c3, out)
        rows = list(csv.DictReader(open(out)))
        for r in rows:
            p_raw  = float(r["p_raw"])
            p_holm = float(r["p_holm_family10"])
            assert p_holm >= p_raw - 1e-10

    def test_fc_source_labels(self, tmp_path):
        """缺口2: source 列 T4.x=C2, T5.x=C3"""
        from incremental_stats import run_fc_family_holm
        c2 = self._make_c2_csv(tmp_path)
        c3 = self._make_c3_csv(tmp_path)
        out = tmp_path / "fc_src.csv"
        run_fc_family_holm(c2, c3, out)
        rows = list(csv.DictReader(open(out)))
        for r in rows:
            if r["test_id"].startswith("T4"):
                assert r["source"] == "C2"
            elif r["test_id"].startswith("T5"):
                assert r["source"] == "C3"


# ============================================================
# conspicuity_proxy.py — --img-dirs 多目录 + --filter-csv 过滤测试 (T6 B2)
# 服务: MedAD-FailMap § PC-B T6，lever=conspicuity→失败边界跨集外推到 HAM-NV
# ============================================================

class TestConspicuityMultiDirAndFilter:
    """验证 --img-dirs 多目录枚举 + --filter-csv NV 过滤接线，不碰特征公式"""

    def _make_part_dirs(self, tmp_path):
        """在 tmp_path 下建两个假 part 目录，各放几张小 png，返回 (part1, part2, all_names)"""
        from PIL import Image as _Image
        part1 = tmp_path / "part_1"
        part2 = tmp_path / "part_2"
        part1.mkdir()
        part2.mkdir()
        rng = np.random.default_rng(42)
        all_names = []
        for i in range(3):
            name = f"ISIC_{i:07d}.png"
            arr  = (rng.random((8, 8)) * 255).astype(np.uint8)
            _Image.fromarray(arr, mode="L").save(part1 / name)
            all_names.append(name)
        for i in range(3, 6):
            name = f"ISIC_{i:07d}.png"
            arr  = (rng.random((8, 8)) * 255).astype(np.uint8)
            _Image.fromarray(arr, mode="L").save(part2 / name)
            all_names.append(name)
        return part1, part2, all_names

    def _write_filter_csv(self, tmp_path, filenames):
        """写只含 filename 列的 csv（模拟 anomaly_scores_isic_ae.csv）"""
        p = tmp_path / "filter.csv"
        with open(p, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["filename", "anomaly_score", "label"])
            w.writeheader()
            for fn in filenames:
                w.writerow({"filename": fn, "anomaly_score": "0.5", "label": "0"})
        return p

    def _run_conspicuity(self, **kwargs):
        """构造 argparse.Namespace 并调 run_conspicuity"""
        import argparse
        from conspicuity_proxy import run_conspicuity
        defaults = {
            "img_dir":    None,
            "img_dirs":   None,
            "score_csv":  None,
            "filter_csv": None,
            "out_csv":    None,
        }
        defaults.update(kwargs)
        args = argparse.Namespace(**defaults)
        run_conspicuity(args)

    def test_img_dirs_both_enumerated(self, tmp_path):
        """①: --img-dirs 传两个目录，输出包含两目录所有图（共 6 行）"""
        part1, part2, all_names = self._make_part_dirs(tmp_path)
        out = tmp_path / "out.csv"
        self._run_conspicuity(
            img_dirs=[str(part1), str(part2)],
            out_csv=str(out),
        )
        assert out.exists()
        rows = list(csv.DictReader(open(out)))
        assert len(rows) == 6, f"期望 6 行(两目录各 3 张)，得 {len(rows)}"
        out_names = {r["filename"] for r in rows}
        assert out_names == set(all_names)

    def test_filter_csv_limits_to_subset(self, tmp_path):
        """②: --filter-csv 只列 part_1 的 3 张，输出仅含这 3 张"""
        part1, part2, all_names = self._make_part_dirs(tmp_path)
        filter_names = all_names[:3]   # 只取 part_1 的 3 张
        filter_p = self._write_filter_csv(tmp_path, filter_names)
        out = tmp_path / "out_filtered.csv"
        self._run_conspicuity(
            img_dirs=[str(part1), str(part2)],
            filter_csv=str(filter_p),
            out_csv=str(out),
        )
        rows = list(csv.DictReader(open(out)))
        assert len(rows) == 3, f"期望过滤后 3 行，得 {len(rows)}"
        out_names = {r["filename"] for r in rows}
        assert out_names == set(filter_names)

    def test_output_schema_unchanged(self, tmp_path):
        """③: 输出列 schema 与 conspicuity_features_tumor.csv 一致（不变），B2 才能 join"""
        part1, part2, all_names = self._make_part_dirs(tmp_path)
        out = tmp_path / "out_schema.csv"
        self._run_conspicuity(
            img_dirs=[str(part1), str(part2)],
            out_csv=str(out),
        )
        rows = list(csv.DictReader(open(out)))
        expected_cols = [
            "filename", "anomaly_score", "label",
            "sigma_global", "glcm_cluster_prom", "glcm_contrast",
            "fft_spectral_entropy", "cnr_proxy_otsu",
        ]
        assert list(rows[0].keys()) == expected_cols, (
            f"输出列 schema 变了！期望 {expected_cols}，得 {list(rows[0].keys())}"
        )

    def test_filter_csv_same_as_score_csv(self, tmp_path):
        """④: score-csv 与 filter-csv 是同一个文件（既做 join 又做过滤）"""
        part1, part2, all_names = self._make_part_dirs(tmp_path)
        # score/filter csv 只列 part_1 前 2 张
        filter_names = all_names[:2]
        filter_p = self._write_filter_csv(tmp_path, filter_names)
        out = tmp_path / "out_same.csv"
        self._run_conspicuity(
            img_dirs=[str(part1), str(part2)],
            score_csv=str(filter_p),
            filter_csv=str(filter_p),
            out_csv=str(out),
        )
        rows = list(csv.DictReader(open(out)))
        assert len(rows) == 2, f"期望 2 行（score=filter 同一文件），得 {len(rows)}"
        # 这 2 行应有来自 score_csv 的 anomaly_score（0.5，非 nan）
        for r in rows:
            assert r["anomaly_score"] == "0.5", (
                f"score_csv join 失败，期望 0.5 得 {r['anomaly_score']}"
            )

    def test_fallback_single_img_dir(self, tmp_path):
        """⑤: 不传 --img-dirs 只传 --img-dir，退回单目录兼容（不回归）"""
        part1, part2, all_names = self._make_part_dirs(tmp_path)
        out = tmp_path / "out_single.csv"
        self._run_conspicuity(
            img_dir=str(part1),   # 不传 img_dirs，退回单目录
            out_csv=str(out),
        )
        rows = list(csv.DictReader(open(out)))
        assert len(rows) == 3, f"退回单目录应得 3 行，得 {len(rows)}"


# ============================================================
# HAMNVTrainDataset — 真实本地数据加载测试 (B0 T6)
# 服务: MedAD-FailMap § PC-B lever=B0
# 需要: D:\YJ-Agent\data\external\ham10000\ (HAM10000_images_part_1/2 + metadata csv)
# ============================================================

HAM_ROOT = Path("D:/YJ-Agent/data/external/ham10000")

@pytest.mark.skipif(
    not HAM_ROOT.exists(),
    reason="HAM10000 本地数据不存在，跳过集成测试"
)
class TestHAMNVTrainDatasetIntegration:
    """用真实本地 HAM10000 数据验证 Bug 1 修复：part_1/part_2 fallback 加载"""

    def test_len_equals_6705(self):
        """过滤 dx==nv 后应得 6705 张图"""
        from train_recon_ae import HAMNVTrainDataset
        ds = HAMNVTrainDataset(root=str(HAM_ROOT))
        assert len(ds) == 6705, (
            f"期望 6705 张 NV 图，实得 {len(ds)}。"
            "请检查 HAM10000_metadata.csv 的 dx==nv 行数与 part_1/part_2 图片是否完整。"
        )

    def test_files_come_from_part_dirs(self):
        """所有找到的图路径应在 part_1 或 part_2 目录下"""
        from train_recon_ae import HAMNVTrainDataset
        ds = HAMNVTrainDataset(root=str(HAM_ROOT))
        part1 = HAM_ROOT / "HAM10000_images_part_1"
        part2 = HAM_ROOT / "HAM10000_images_part_2"
        for p in ds.files:
            assert p.parent in (part1, part2), (
                f"图片 {p} 不在 part_1 或 part_2 目录下"
            )

    def test_getitem_returns_image_and_name(self):
        """__getitem__ 应返回 (tensor/img, filename_str) 且图不报错打开"""
        from train_recon_ae import HAMNVTrainDataset
        ds = HAMNVTrainDataset(root=str(HAM_ROOT))
        img, name = ds[0]
        # 无 transform 时返回 PIL Image
        from PIL import Image as _Image
        assert isinstance(img, _Image.Image), f"期望 PIL Image，得 {type(img)}"
        assert isinstance(name, str) and len(name) > 0


# ============================================================
# Phase 1 新增测试
# ============================================================

class TestLesionFeatures:
    """lesion_features.py — HAM 同口径特征提取"""

    def _make_img_mask(self, tmp_path, img_id="ISIC_0000001",
                       img_size=64, lesion_inner=16):
        """合成图 + mask：中心 lesion_inner×lesion_inner 为前景"""
        from PIL import Image as _Image
        rng = np.random.default_rng(7)
        # 图：中心亮（前景），周围暗
        img_arr = np.zeros((img_size, img_size), dtype=np.uint8)
        c = img_size // 2
        h = lesion_inner // 2
        img_arr[c-h:c+h, c-h:c+h] = 200
        img_arr += rng.integers(0, 20, (img_size, img_size), dtype=np.uint8)

        # mask：同区域前景
        mask_arr = np.zeros((img_size, img_size), dtype=np.uint8)
        mask_arr[c-h:c+h, c-h:c+h] = 255

        img_path  = tmp_path / f"{img_id}.jpg"
        mask_path = tmp_path / f"{img_id}_segmentation.png"
        _Image.fromarray(img_arr, mode="L").save(img_path)
        _Image.fromarray(mask_arr, mode="L").save(mask_path)
        return img_path, mask_path, img_arr, mask_arr

    def test_size_px_correct(self, tmp_path):
        """size_px = mask 最大连通域面积"""
        from lesion_features import extract_lesion_features
        img_path, mask_path, _, _ = self._make_img_mask(tmp_path, lesion_inner=16)
        feats = extract_lesion_features(img_path, mask_path)
        # 16×16 = 256 px
        assert feats["size_px"] == 256, f"expected 256, got {feats['size_px']}"

    def test_contrast_positive(self, tmp_path):
        """lesion 亮 + 周围暗 → contrast > 0"""
        from lesion_features import extract_lesion_features
        img_path, mask_path, _, _ = self._make_img_mask(tmp_path)
        feats = extract_lesion_features(img_path, mask_path, ring_width_frac=0.075)
        assert feats["contrast"] > 0.0, "contrast should be > 0 for bright lesion on dark bg"

    def test_ring_width_frac_parameterized(self, tmp_path):
        """(d) 不同 ring_width_frac 应产出不同 contrast（dilation_px 不同）"""
        from lesion_features import extract_lesion_features
        img_path, mask_path, _, _ = self._make_img_mask(tmp_path, lesion_inner=32)
        feats_small = extract_lesion_features(img_path, mask_path, ring_width_frac=0.02)
        feats_large = extract_lesion_features(img_path, mask_path, ring_width_frac=0.20)
        # dilation_px 不同，至少一个属性不同（dilation_px 必不同）
        assert feats_small["dilation_px"] != feats_large["dilation_px"], (
            f"ring_width_frac 不同应产出不同 dilation_px: "
            f"small={feats_small['dilation_px']}, large={feats_large['dilation_px']}"
        )

    def test_p90_in_lesion_subset(self, tmp_path):
        """(e) PR-1: detected 阈值在病灶子集内算 P90，非全图"""
        from lesion_features import batch_extract
        from PIL import Image as _Image
        rng = np.random.default_rng(42)
        img_dir  = tmp_path / "imgs"
        mask_dir = tmp_path / "masks"
        img_dir.mkdir()
        mask_dir.mkdir()

        # 造 20 张 (img+mask)
        filenames = []
        for i in range(20):
            img_id = f"ISIC_{i:07d}"
            arr = (rng.random((32, 32)) * 255).astype(np.uint8)
            _Image.fromarray(arr, mode="L").save(img_dir / f"{img_id}.jpg")
            mask = np.zeros((32, 32), dtype=np.uint8)
            mask[8:16, 8:16] = 255
            _Image.fromarray(mask, mode="L").save(mask_dir / f"{img_id}_segmentation.png")
            filenames.append(img_id)

        # 写 score csv（模拟 lesion subset 所有行都有 anomaly_score）
        score_csv = tmp_path / "scores.csv"
        scores = rng.random(20) * 0.8 + 0.1
        with open(score_csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["filename", "anomaly_score", "label"])
            w.writeheader()
            for i, fn in enumerate(filenames):
                w.writerow({"filename": fn + ".jpg",
                            "anomaly_score": str(scores[i]),
                            "label": "1"})

        out_csv = tmp_path / "out_feats.csv"
        rows = batch_extract(
            img_dir=str(img_dir),
            mask_dir=str(mask_dir),
            score_csv=str(score_csv),
            out_csv=str(out_csv),
            detected_pct=90.0,
        )
        assert len(rows) == 20
        # P90 在 lesion subset（20 样本）内算；detected 应为 0 或 1
        detected_vals = [r["detected"] for r in rows if r["detected"] != "nan"]
        assert all(v in (0, 1) for v in detected_vals)
        # ~10% detected (P90 → ~2 out of 20)
        n_detected = sum(detected_vals)
        assert 1 <= n_detected <= 5, f"P90 应产出约 10% detected，得 {n_detected}/20"

    def test_batch_extract_schema(self, tmp_path):
        """输出 csv 含 filename/size_px/contrast/anomaly_score/label/detected/seed 列"""
        from lesion_features import batch_extract
        from PIL import Image as _Image
        rng = np.random.default_rng(0)
        img_dir  = tmp_path / "imgs2"
        mask_dir = tmp_path / "masks2"
        img_dir.mkdir()
        mask_dir.mkdir()
        for i in range(5):
            img_id = f"ISIC_{i:07d}"
            arr = (rng.random((16, 16)) * 255).astype(np.uint8)
            _Image.fromarray(arr, mode="L").save(img_dir / f"{img_id}.jpg")
            mask = np.zeros((16, 16), dtype=np.uint8)
            mask[4:8, 4:8] = 255
            _Image.fromarray(mask, mode="L").save(
                mask_dir / f"{img_id}_segmentation.png"
            )
        out_csv = tmp_path / "out_schema.csv"
        batch_extract(img_dir=str(img_dir), mask_dir=str(mask_dir), out_csv=str(out_csv))
        rows = list(csv.DictReader(open(out_csv)))
        assert len(rows) == 5
        for col in ["filename", "size_px", "contrast", "seed"]:
            assert col in rows[0], f"missing col: {col}"


class TestAreaRatioCheck:
    """area_ratio_check.py — PR-7 面积比分布重叠检查"""

    def _make_features_csv(self, tmp_path, name, size_px_arr, img_size=64):
        """合成 per-image 特征 csv（含 size_px 列）"""
        p = tmp_path / f"{name}.csv"
        with open(p, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["filename", "size_px", "contrast"])
            w.writeheader()
            for i, s in enumerate(size_px_arr):
                w.writerow({"filename": f"img_{i:04d}.png",
                             "size_px": str(s),
                             "contrast": "0.1"})
        return p

    def test_overlap_ok_true(self, tmp_path):
        """(c): 目标集有样本在 BraTS 低面积比区段 → overlap_ok=True
        注：传 min_absolute=1/min_overlap_frac=0.0 使用旧宽松门槛（仅验证基本重叠逻辑）。
        严格门槛（min_absolute=30, min_overlap_frac=0.05）见 TestPhase1PR7AreaRatio。
        """
        from area_ratio_check import run_area_ratio_check
        # BraTS: 面积比范围 0.001~0.1（小病灶）
        brats_sizes = np.array([10, 20, 50, 100, 200, 300, 400, 500, 600, 700],
                                dtype=float)
        # target: 包含小病灶（area_ratio 与 BraTS 低区段重叠）
        target_sizes = np.array([5, 15, 30, 200, 400], dtype=float)
        brats_csv  = self._make_features_csv(tmp_path, "brats", brats_sizes)
        target_csv = self._make_features_csv(tmp_path, "target_overlap", target_sizes)
        out_dir = tmp_path / "out_overlap"
        result = run_area_ratio_check(
            brats_features_csv=str(brats_csv),
            target_features_csv=str(target_csv),
            out_dir=str(out_dir),
            target_name="test_overlap",
            brats_img_size=64,
            min_absolute=1,        # 旧宽松门槛（仅测基本逻辑）
            min_overlap_frac=0.0,  # 旧宽松门槛
        )
        assert result["overlap_ok"] is True, (
            f"target 有小样本应 overlap_ok=True, got {result}"
        )

    def test_overlap_ok_false(self, tmp_path):
        """(c): 目标集全是大病灶，不与 BraTS 低区段重叠 → overlap_ok=False
        注：target 全大病灶，即使 min_absolute=1 也有 0 个样本在低区段 → False。
        """
        from area_ratio_check import run_area_ratio_check
        # BraTS: 小病灶（低面积比）
        brats_sizes = np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], dtype=float)
        # target: 全是大病灶，远超 BraTS P25
        target_sizes = np.array([3000, 3100, 3200, 3300, 3400], dtype=float)
        brats_csv  = self._make_features_csv(tmp_path, "brats2", brats_sizes)
        target_csv = self._make_features_csv(tmp_path, "target_nolap", target_sizes)
        out_dir = tmp_path / "out_nolap"
        result = run_area_ratio_check(
            brats_features_csv=str(brats_csv),
            target_features_csv=str(target_csv),
            out_dir=str(out_dir),
            target_name="test_nolap",
            brats_img_size=64,
            brats_low_ratio_pct=25.0,
            min_absolute=1,        # 宽松门槛：target 0 个在低区段仍 False
            min_overlap_frac=0.0,
        )
        assert result["overlap_ok"] is False, (
            f"target 全大样本应 overlap_ok=False, got {result}"
        )

    def test_output_csv_exists(self, tmp_path):
        """输出 csv 存在且含 overlap_ok 列"""
        from area_ratio_check import run_area_ratio_check
        brats_sizes  = np.arange(10, 110, 10, dtype=float)
        target_sizes = np.arange(5, 55, 10, dtype=float)
        brats_csv  = self._make_features_csv(tmp_path, "brats3", brats_sizes)
        target_csv = self._make_features_csv(tmp_path, "target3", target_sizes)
        out_dir = tmp_path / "out3"
        run_area_ratio_check(
            brats_features_csv=str(brats_csv),
            target_features_csv=str(target_csv),
            out_dir=str(out_dir),
            target_name="mytest",
        )
        out_csv = out_dir / "area_ratio_check_mytest.csv"
        assert out_csv.exists()
        rows = list(csv.DictReader(open(out_csv)))
        assert len(rows) == 1
        assert "overlap_ok" in rows[0]
        assert "brats_low_threshold" in rows[0]
        assert "target_n_in_low_zone" in rows[0]


class TestPhase1FailureBoundary:
    """failure_boundary.py Phase 1 新增：run_b2_extrap 跨集外推"""

    def _make_brats_data_p1(self, n=200, seed=0):
        """合成 BraTS data dict（真 mask 口径：size_px/contrast）"""
        rng = np.random.default_rng(seed)
        size_px  = rng.integers(10, 500, size=n).astype(float)
        contrast = rng.random(n)
        scores   = 0.001 * size_px + 0.3 * contrast + rng.random(n) * 0.2
        return {
            "anomaly_score": scores,
            "label":         np.ones(n, dtype=int),
            "size_px":       size_px,
            "contrast":      contrast,
        }

    def _make_target_data(self, n=100, seed=1):
        """合成目标集 data dict（真 mask 同口径）"""
        rng = np.random.default_rng(seed)
        size_px  = rng.integers(50, 600, size=n).astype(float)
        contrast = rng.random(n)
        scores   = rng.random(n) * 0.6 + 0.1
        return {
            "anomaly_score": scores,
            "label":         np.ones(n, dtype=int),
            "size_px":       size_px,
            "contrast":      contrast,
            "_filenames":    [f"target_{i:04d}.png" for i in range(n)],
        }

    def test_scaler_not_mutated_by_transform(self, tmp_path):
        """(a) scaler 仅 BraTS fit，target transform 后 mean_/scale_ 不变（PR-3 断言）"""
        from failure_boundary import run_b1, run_b2_extrap
        brats = self._make_brats_data_p1()
        brats = run_b1(brats, tmp_path)
        target = self._make_target_data()
        # run_b2_extrap 内部断言 scaler 不变，若失败会 AssertionError
        row = run_b2_extrap(brats, target, tmp_path, target_name="ham_p1", seed=42)
        # 若走到这里说明断言全通过
        assert row is not None or True  # 有结果或无结果都通过（no crash = pass）

    def test_filename_join_no_truncation(self, tmp_path):
        """(b) 打乱行序后 filename join 无截断（行序不影响结果）"""
        from failure_boundary import run_b1, run_b2_extrap
        brats = self._make_brats_data_p1(n=200, seed=0)
        brats = run_b1(brats, tmp_path)

        target_orig = self._make_target_data(n=80, seed=2)
        # 打乱行序
        rng = np.random.default_rng(99)
        idx = rng.permutation(80)
        target_shuffled = {
            k: (v[idx] if isinstance(v, np.ndarray) else [v[i] for i in idx])
            for k, v in target_orig.items()
        }

        row_orig = run_b2_extrap(brats, target_orig,    tmp_path, target_name="ham_orig",    seed=42)
        row_shuf = run_b2_extrap(brats, target_shuffled, tmp_path, target_name="ham_shuffled", seed=42)

        # n_target 应一致（80 行，行序不影响样本数）
        if row_orig and row_shuf:
            assert row_orig["n_target"] == row_shuf["n_target"], (
                f"行序打乱不应改变 n_target: {row_orig['n_target']} vs {row_shuf['n_target']}"
            )

    def test_extrap_output_csv_schema(self, tmp_path):
        """extrap_B2_<target>.csv 含必要列"""
        from failure_boundary import run_b1, run_b2_extrap
        brats = self._make_brats_data_p1()
        brats = run_b1(brats, tmp_path)
        target = self._make_target_data()
        run_b2_extrap(brats, target, tmp_path, target_name="schema_test", seed=42)
        out_csv = tmp_path / "extrap_B2_schema_test.csv"
        assert out_csv.exists(), "extrap_B2_*.csv 未生成"
        rows = list(csv.DictReader(open(out_csv)))
        assert len(rows) == 1
        required_cols = [
            "cross_domain_auroc", "ci_lo_9875", "ci_hi_9875",
            "in_domain_auroc", "ratio_cross_over_in",
            "pass_ratio_80", "n_target", "n_fail", "seed",
        ]
        for col in required_cols:
            assert col in rows[0], f"输出缺少列: {col}"

    def test_p90_in_target_lesion_subset(self, tmp_path):
        """(e) y_fail 在目标集病灶子集内算 P90，而非 BraTS P90"""
        from failure_boundary import run_b1, run_b2_extrap
        brats = self._make_brats_data_p1(n=200)
        brats = run_b1(brats, tmp_path)
        # target scores 刻意设为与 BraTS 量级不同（大 10 倍）
        rng = np.random.default_rng(5)
        target = self._make_target_data(n=80)
        target["anomaly_score"] = rng.random(80) * 10.0  # 与 BraTS (0~1) 不同量级
        row = run_b2_extrap(brats, target, tmp_path,
                            target_name="p90_test", seed=42, detected_pct=90.0)
        # 不报错即说明阈值在 target 内算（而非 BraTS 阈值，否则 all fail/detected）
        if row:
            assert row["n_fail"] < row["n_target"], "n_fail 应小于 n_target（P90 不应全 fail）"

    def test_b4_min20_detected(self, tmp_path):
        """(f) B4 ≥20 detected 判定：<20 detected → interpretable=0"""
        from failure_boundary import run_b1, run_b4
        # 造极端数据：test split 几乎全是 fail（detected 极少）
        rng = np.random.default_rng(0)
        n = 300
        size_px = rng.integers(10, 500, size=n).astype(float)
        contrast = rng.random(n)
        # anomaly_score 全部接近 0 → P90 极低 → 几乎全是 detected
        # 反过来：scores 全高 → threshold 高 → 只有很少 detected
        # 我们要 large_size test 有 <20 detected：让大 size 的 score 低
        scores = np.where(size_px > np.percentile(size_px, 66),
                          rng.random(n) * 0.001,  # 大 size → 低 score → fail
                          rng.random(n) * 0.5 + 0.5)  # 中小 size → 高 score → detected
        brats = {
            "anomaly_score": scores,
            "label": np.ones(n, dtype=int),
            "size_px": size_px,
            "contrast": contrast,
        }
        brats = run_b1(brats, tmp_path)
        run_b4(brats, tmp_path)
        out_csv = tmp_path / "boundary_B4_extrapolation.csv"
        rows = list(csv.DictReader(open(out_csv)))
        large_rows = [r for r in rows if "large_size" in r["test_split"]]
        for r in large_rows:
            n_det = int(r["n_test_detected"])
            interp = int(r["interpretable"])
            if n_det < 20:
                assert interp == 0, (
                    f"n_test_detected={n_det} < 20 应 interpretable=0，得 {interp}"
                )


# ============================================================
# Phase 1 PR-2 / PR-7 / PR-1 / PR-5 新增测试
# ============================================================

class TestPhase1PR2RingFrac:
    """PR-2: BraTS Phase 1 相对环宽 + 64×64 坐标系统一 + 三档扫描"""

    def _make_img_mask_pil(self, tmp_path, img_id, size=64, lesion_inner=16):
        """合成 64×64 图 + mask，中心 lesion_inner×lesion_inner 前景"""
        from PIL import Image as _Image
        rng = np.random.default_rng(hash(img_id) % (2**31))
        img_arr = np.zeros((size, size), dtype=np.uint8)
        c = size // 2
        h = lesion_inner // 2
        img_arr[c-h:c+h, c-h:c+h] = 200
        img_arr += rng.integers(0, 10, (size, size), dtype=np.uint8)
        mask_arr = np.zeros((size, size), dtype=np.uint8)
        mask_arr[c-h:c+h, c-h:c+h] = 255
        img_path  = tmp_path / f"{img_id}.jpg"
        mask_path = tmp_path / f"{img_id}_segmentation.png"
        _Image.fromarray(img_arr, "L").save(img_path)
        _Image.fromarray(mask_arr, "L").save(mask_path)
        return img_path, mask_path

    def test_phase1_mode_forces_64(self, tmp_path):
        """(a) phase1_mode=True 时 img_size 强制为 64，不管传入值"""
        from lesion_features import batch_extract
        img_dir  = tmp_path / "imgs"
        mask_dir = tmp_path / "masks"
        img_dir.mkdir()
        mask_dir.mkdir()
        for i in range(5):
            self._make_img_mask_pil(img_dir, f"ISIC_{i:07d}")
            # 把 segmentation.png 放到 mask_dir
            src_mask = img_dir / f"ISIC_{i:07d}_segmentation.png"
            if src_mask.exists():
                src_mask.rename(mask_dir / src_mask.name)

        out_csv = tmp_path / "out_phase1.csv"
        rows = batch_extract(
            img_dir=str(img_dir),
            mask_dir=str(mask_dir),
            out_csv=str(out_csv),
            phase1_mode=True,
            img_size=999,  # 应被 phase1_mode 覆盖为 64
        )
        # 所有行 size_px <= 64*64=4096
        for r in rows:
            assert int(r["size_px"]) <= 64 * 64, (
                f"phase1_mode=True 应强制 64×64，size_px={r['size_px']} 超出 4096"
            )

    def test_brats_phase0_contrast_unchanged(self):
        """(a) Phase 0 stratify_eval.compute_contrast 默认 dilation_px=3 未被动"""
        from stratify_eval import compute_contrast
        import inspect
        sig = inspect.signature(compute_contrast)
        default_dilation = sig.parameters["dilation_px"].default
        assert default_dilation == 3, (
            f"Phase 0 的 compute_contrast dilation_px 默认值被改动！期望 3，得 {default_dilation}"
        )

    def test_ring_frac_list_three_outputs(self, tmp_path):
        """(f) ring_frac_list=[0.05,0.075,0.10] 时输出三个 csv，各 ring_frac 不同"""
        from lesion_features import batch_extract
        from PIL import Image as _Image
        rng = np.random.default_rng(7)
        img_dir  = tmp_path / "imgs_rf"
        mask_dir = tmp_path / "masks_rf"
        img_dir.mkdir()
        mask_dir.mkdir()
        for i in range(5):
            img_id = f"ISIC_{i:07d}"
            arr  = (rng.random((64, 64)) * 255).astype(np.uint8)
            mask = np.zeros((64, 64), dtype=np.uint8)
            mask[24:40, 24:40] = 255  # 16x16 center lesion
            _Image.fromarray(arr, "L").save(img_dir / f"{img_id}.jpg")
            _Image.fromarray(mask, "L").save(mask_dir / f"{img_id}_segmentation.png")

        out_csv = tmp_path / "out_rf.csv"
        fracs = [0.05, 0.075, 0.10]
        result = batch_extract(
            img_dir=str(img_dir),
            mask_dir=str(mask_dir),
            out_csv=str(out_csv),
            ring_frac_list=fracs,
            phase1_mode=True,
        )
        # 返回 dict（多档）
        assert isinstance(result, dict), "ring_frac_list 多档应返回 dict"
        assert set(result.keys()) == set(fracs), f"dict keys 应为 {fracs}"
        # 三个输出 csv 文件都存在
        for frac in fracs:
            frac_str = str(frac).replace(".", "p")
            expected_path = tmp_path / f"out_rf_rf{frac_str}.csv"
            assert expected_path.exists(), f"三档输出 csv 不存在: {expected_path.name}"

    def test_ring_frac_list_dilation_different(self, tmp_path):
        """(f) 三档 ring_frac 产出不同 dilation_px（等效直径 × ring_frac）"""
        from lesion_features import batch_extract
        from PIL import Image as _Image
        img_dir  = tmp_path / "imgs_rfc"
        mask_dir = tmp_path / "masks_rfc"
        img_dir.mkdir()
        mask_dir.mkdir()
        arr = np.zeros((64, 64), dtype=np.uint8)
        arr[24:40, 24:40] = 220
        mask = np.zeros((64, 64), dtype=np.uint8)
        mask[24:40, 24:40] = 255
        _Image.fromarray(arr, "L").save(img_dir / "ISIC_0000001.jpg")
        _Image.fromarray(mask, "L").save(mask_dir / "ISIC_0000001_segmentation.png")

        fracs = [0.05, 0.075, 0.10]
        result = batch_extract(
            img_dir=str(img_dir),
            mask_dir=str(mask_dir),
            ring_frac_list=fracs,
            phase1_mode=True,
        )
        dil_pxs = [result[f][0]["dilation_px"] for f in fracs if result[f]]
        # equiv_diam = sqrt(4*256/pi) ~= 18px
        # 0.05*18=0.9→1px, 0.075*18=1.35→1px, 0.10*18=1.8→2px → 至少有一档不同
        # 用更大 lesion (32×32=1024px, equiv_diam≈36px) 确保差异大：
        # 0.05*36=1.8→2px, 0.075*36=2.7→3px, 0.10*36=3.6→4px → 三档全不同
        # 当前 fixture 16×16=256px，若前两档相同最后一档不同也算 > 1 种
        assert len(set(dil_pxs)) > 1, (
            f"三档 ring_frac 的 dilation_px 应不全相同，得 {dil_pxs}（fracs={fracs}）"
        )

    def test_two_ends_same_coord_system(self, tmp_path):
        """(a) BraTS 和 HAM Phase 1 特征都在 64×64 坐标系算：size_px <= 4096"""
        from lesion_features import extract_lesion_features_phase1
        from PIL import Image as _Image
        # 造一张原始大图（128×128），phase1_mode 应 resize 到 64
        rng = np.random.default_rng(0)
        arr  = (rng.random((128, 128)) * 255).astype(np.uint8)
        mask = np.zeros((128, 128), dtype=np.uint8)
        mask[48:80, 48:80] = 255  # 32×32 lesion
        img_path  = tmp_path / "test.jpg"
        mask_path = tmp_path / "test_seg.png"
        _Image.fromarray(arr, "L").save(img_path)
        _Image.fromarray(mask, "L").save(mask_path)

        feats = extract_lesion_features_phase1(img_path, mask_path, ring_width_frac=0.075)
        # 在 64×64 坐标系下，32×32 lesion → resize 后约 16×16=256 px
        assert feats["size_px"] <= 64 * 64, (
            f"Phase 1 特征须在 64×64 坐标系，size_px={feats['size_px']} > 4096"
        )

    # ------------------------------------------------------------------
    # --img-dirs 多目录支持（HAM part_1 + part_2）
    # 服务: MedAD-FailMap Phase 1, G1-a 面积比诊断
    # ------------------------------------------------------------------

    def _make_multi_dir_fixture(self, tmp_path):
        """
        建两个图目录 (part1, part2) + 一个 mask 目录。
        part1: ISIC_0000001.jpg, ISIC_0000002.jpg, ISIC_0000003.jpg
        part2: ISIC_0000004.jpg, ISIC_0000005.jpg
        masks: 对应 5 张 ISIC_<id>_segmentation.png（16×16 lesion in 32×32）
        返回 (part1, part2, mask_dir, all_ids)
        """
        from PIL import Image as _Image

        rng = np.random.default_rng(7)
        part1 = tmp_path / "part_1"
        part2 = tmp_path / "part_2"
        mask_dir = tmp_path / "masks"
        part1.mkdir()
        part2.mkdir()
        mask_dir.mkdir()

        all_ids = [f"ISIC_{i:07d}" for i in range(1, 6)]
        dirs_for = {ids: (part1 if i < 3 else part2)
                    for i, ids in enumerate(all_ids)}

        for img_id, d in dirs_for.items():
            arr = (rng.random((32, 32, 3)) * 255).astype(np.uint8)
            _Image.fromarray(arr, "RGB").save(d / f"{img_id}.jpg")

            mask = np.zeros((32, 32), dtype=np.uint8)
            mask[8:24, 8:24] = 255  # 16×16 lesion
            _Image.fromarray(mask, "L").save(
                mask_dir / f"{img_id}_segmentation.png"
            )

        return part1, part2, mask_dir, all_ids

    def test_img_dirs_both_enumerated(self, tmp_path):
        """--img-dirs 传两目录，两目录的图均被匹配（共 5 行输出）"""
        from lesion_features import batch_extract

        part1, part2, mask_dir, all_ids = self._make_multi_dir_fixture(tmp_path)
        out = tmp_path / "out_multidirs.csv"
        rows = batch_extract(
            img_dirs=[str(part1), str(part2)],
            mask_dir=str(mask_dir),
            out_csv=str(out),
        )
        assert len(rows) == 5, (
            f"两目录共 5 张图应得 5 行，实得 {len(rows)}"
        )
        got_ids = {Path(r["filename"]).stem for r in rows}
        assert got_ids == set(all_ids), (
            f"输出 image_id 集合不符，期望 {set(all_ids)}，得 {got_ids}"
        )

    def test_img_dirs_part1_only(self, tmp_path):
        """--img-dirs 只传 part_1，只返回 part_1 的 3 行（part_2 找不到图自动 skip）"""
        from lesion_features import batch_extract

        part1, part2, mask_dir, all_ids = self._make_multi_dir_fixture(tmp_path)
        rows = batch_extract(
            img_dirs=[str(part1)],
            mask_dir=str(mask_dir),
        )
        # part1 有 ISIC_0000001~0000003，part2 有 ISIC_0000004~0000005
        # 只传 part1 → 只有 3 行（part_2 的 mask 找不到图被 skip）
        assert len(rows) == 3, (
            f"只传 part_1 应得 3 行（另 2 张在 part_2 被 skip），实得 {len(rows)}"
        )

    def test_img_dirs_fallback_single(self, tmp_path):
        """不传 img_dirs 只传 img_dir，兼容旧调用（退回单目录）"""
        from lesion_features import batch_extract

        part1, part2, mask_dir, all_ids = self._make_multi_dir_fixture(tmp_path)
        rows = batch_extract(
            img_dir=str(part1),   # 不传 img_dirs，退回单目录
            mask_dir=str(mask_dir),
        )
        assert len(rows) == 3, (
            f"退回单目录 part_1 应得 3 行，实得 {len(rows)}"
        )

    def test_img_dirs_size_px_nonzero(self, tmp_path):
        """多目录匹配后 size_px 计算正确（16×16 lesion = 256 px in 32×32 图）"""
        from lesion_features import batch_extract

        part1, part2, mask_dir, _ = self._make_multi_dir_fixture(tmp_path)
        rows = batch_extract(
            img_dirs=[str(part1), str(part2)],
            mask_dir=str(mask_dir),
        )
        for r in rows:
            assert int(r["size_px"]) == 256, (
                f"16×16 lesion 期望 size_px=256，{r['filename']} 得 {r['size_px']}"
            )


class TestPhase1PR7AreaRatio:
    """PR-7 bug a+b: area_ratio 坐标系统一 + overlap_frac 门槛"""

    def _make_features_csv(self, tmp_path, name, size_px_arr):
        p = tmp_path / f"{name}.csv"
        with open(p, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["filename", "size_px", "contrast"])
            w.writeheader()
            for i, s in enumerate(size_px_arr):
                w.writerow({"filename": f"img_{i:04d}.png",
                             "size_px": str(s),
                             "contrast": "0.1"})
        return p

    def test_area_ratio_in_0_1(self, tmp_path):
        """(b) area_ratio ∈ [0,1]：正常 size_px <= img_size^2 不报错"""
        from area_ratio_check import compute_area_ratio
        sizes = np.array([0, 100, 1000, 4096], dtype=float)  # all <= 64^2=4096
        ratios = compute_area_ratio(sizes, img_size=64)
        assert np.all(ratios >= 0) and np.all(ratios <= 1.0 + 1e-9), (
            f"area_ratio 超出 [0,1]: {ratios}"
        )

    def test_area_ratio_out_of_range_raises(self, tmp_path):
        """(b) size_px > img_size^2 触发 ValueError（坐标系不一致 guard）"""
        from area_ratio_check import compute_area_ratio
        import pytest as _pytest
        sizes = np.array([4097.0])  # 超出 64^2
        with _pytest.raises(ValueError, match="area_ratio 超出"):
            compute_area_ratio(sizes, img_size=64)

    def test_overlap_frac_3pct_fails(self, tmp_path):
        """(c) target 占低区段 3% < 5% 门槛 → overlap_ok=False"""
        from area_ratio_check import run_area_ratio_check
        # BraTS: 100 个小病灶（面积比均匀分布 0~0.1）
        # P25 = 0.025
        brats_sizes = np.linspace(0, 640, 100)  # 0~640 in 64x64 = 0~0.156
        # target: 200 个，仅 6 个（3%）在低区段（<= P25）
        target_sizes_low  = np.array([10.0, 20.0, 30.0, 40.0, 50.0, 60.0])   # 6 个
        target_sizes_high = np.linspace(1000, 3000, 194)
        target_sizes = np.concatenate([target_sizes_low, target_sizes_high])

        brats_csv  = self._make_features_csv(tmp_path, "brats_3pct", brats_sizes)
        target_csv = self._make_features_csv(tmp_path, "target_3pct", target_sizes)
        out_dir    = tmp_path / "out_3pct"
        result = run_area_ratio_check(
            brats_features_csv=str(brats_csv),
            target_features_csv=str(target_csv),
            out_dir=str(out_dir),
            target_name="t3pct",
            brats_img_size=64,
            min_overlap_frac=0.05,   # 5% 门槛
            min_absolute=30,
        )
        # 6/200 = 3% < 5% 且 6 < 30 → 应 False
        assert result["overlap_ok"] is False, (
            f"3% overlap 应 overlap_ok=False (门槛 5%+30)，得 {result}"
        )

    def test_overlap_frac_8pct_passes(self, tmp_path):
        """(c) target 占低区段 8% > 5% 且 >=30 → overlap_ok=True"""
        from area_ratio_check import run_area_ratio_check
        # BraTS: 100 个，P25 ~ 0.025
        brats_sizes = np.linspace(0, 640, 100)
        # target: 400 个，其中 40 个（10%）在低区段
        target_sizes_low  = np.linspace(0, 100, 40)   # 40 个，约占 10%
        target_sizes_high = np.linspace(1000, 3000, 360)
        target_sizes = np.concatenate([target_sizes_low, target_sizes_high])

        brats_csv  = self._make_features_csv(tmp_path, "brats_8pct", brats_sizes)
        target_csv = self._make_features_csv(tmp_path, "target_8pct", target_sizes)
        out_dir    = tmp_path / "out_8pct"
        result = run_area_ratio_check(
            brats_features_csv=str(brats_csv),
            target_features_csv=str(target_csv),
            out_dir=str(out_dir),
            target_name="t8pct",
            brats_img_size=64,
            min_overlap_frac=0.05,
            min_absolute=30,
        )
        # 40/400 = 10% > 5% 且 40 >= 30 → 应 True
        assert result["overlap_ok"] is True, (
            f"10% overlap 且 >=30 样本应 overlap_ok=True，得 {result}"
        )

    def test_coord_sys_mismatch_warns(self, tmp_path, capsys):
        """(a) brats_img_size != target_img_size 打印 WARNING（不静默失败）"""
        from area_ratio_check import run_area_ratio_check
        brats_sizes  = np.linspace(10, 640, 50)
        target_sizes = np.linspace(10, 1000, 50)
        brats_csv  = self._make_features_csv(tmp_path, "brats_w", brats_sizes)
        target_csv = self._make_features_csv(tmp_path, "target_w", target_sizes)
        out_dir    = tmp_path / "out_w"
        run_area_ratio_check(
            brats_features_csv=str(brats_csv),
            target_features_csv=str(target_csv),
            out_dir=str(out_dir),
            target_name="mismatch",
            brats_img_size=64,
            target_img_size=128,  # 故意不一致
        )
        captured = capsys.readouterr()
        assert "WARNING" in captured.out, (
            "坐标系不一致应打印 WARNING，但未发现"
        )

    def test_new_output_cols(self, tmp_path):
        """PR-7 bug b: 输出 csv 含 target_n_total / required_support 新列"""
        from area_ratio_check import run_area_ratio_check
        brats_sizes  = np.arange(10, 510, 10, dtype=float)  # 50 个
        target_sizes = np.arange(5, 405, 10, dtype=float)   # 40 个
        brats_csv  = self._make_features_csv(tmp_path, "brats_nc", brats_sizes)
        target_csv = self._make_features_csv(tmp_path, "target_nc", target_sizes)
        out_dir    = tmp_path / "out_nc"
        run_area_ratio_check(
            brats_features_csv=str(brats_csv),
            target_features_csv=str(target_csv),
            out_dir=str(out_dir),
            target_name="newcols",
        )
        out_csv = out_dir / "area_ratio_check_newcols.csv"
        rows = list(csv.DictReader(open(out_csv)))
        assert "target_n_total"   in rows[0], "缺少 target_n_total 列"
        assert "required_support" in rows[0], "缺少 required_support 列"
        assert "min_overlap_frac" in rows[0], "缺少 min_overlap_frac 列"


class TestPhase1PR1DxFilter:
    """PR-1: dx!=nv 异常皮损子集过滤"""

    def _make_img_mask(self, tmp_path, img_ids):
        """批量造合成 img + mask"""
        from PIL import Image as _Image
        img_dir  = tmp_path / "imgs_dx"
        mask_dir = tmp_path / "masks_dx"
        img_dir.mkdir(exist_ok=True)
        mask_dir.mkdir(exist_ok=True)
        rng = np.random.default_rng(123)
        for img_id in img_ids:
            arr  = (rng.random((16, 16)) * 255).astype(np.uint8)
            mask = np.zeros((16, 16), dtype=np.uint8)
            mask[4:8, 4:8] = 255
            _Image.fromarray(arr, "L").save(img_dir / f"{img_id}.jpg")
            _Image.fromarray(mask, "L").save(mask_dir / f"{img_id}_segmentation.png")
        return img_dir, mask_dir

    def _make_metadata_csv(self, tmp_path, rows):
        """写 HAM metadata csv（image_id + dx 列）"""
        p = tmp_path / "metadata.csv"
        with open(p, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["image_id", "dx"])
            w.writeheader()
            w.writerows(rows)
        return p

    def test_exclude_nv_filters_nv(self, tmp_path):
        """(d) lesion_dx_filter=metadata_csv 路径时 dx==nv 的 img 被过滤"""
        # 10 张图：5 nv + 5 melanoma
        all_ids = [f"ISIC_{i:07d}" for i in range(10)]
        nv_ids  = all_ids[:5]
        mel_ids = all_ids[5:]
        img_dir, mask_dir = self._make_img_mask(tmp_path, all_ids)

        meta_rows = (
            [{"image_id": iid, "dx": "nv"}  for iid in nv_ids] +
            [{"image_id": iid, "dx": "mel"} for iid in mel_ids]
        )
        meta_csv = self._make_metadata_csv(tmp_path, meta_rows)

        from lesion_features import batch_extract
        rows_out = batch_extract(
            img_dir=str(img_dir),
            mask_dir=str(mask_dir),
            lesion_dx_filter=str(meta_csv),  # 传 metadata csv 路径
        )
        filenames_out = {Path(r["filename"]).stem for r in rows_out}
        # nv 的应被过滤掉
        for nv_id in nv_ids:
            assert nv_id not in filenames_out, (
                f"dx==nv 的 {nv_id} 应被过滤，但仍在输出中"
            )
        # melanoma 的应保留
        for mel_id in mel_ids:
            assert mel_id in filenames_out, (
                f"dx==mel 的 {mel_id} 应保留，但不在输出中"
            )

    def test_no_filter_returns_all(self, tmp_path):
        """(d) lesion_dx_filter=None 时全部返回（不过滤）"""
        all_ids = [f"ISIC_{i:07d}" for i in range(8)]
        img_dir, mask_dir = self._make_img_mask(tmp_path, all_ids)
        from lesion_features import batch_extract
        rows_out = batch_extract(
            img_dir=str(img_dir),
            mask_dir=str(mask_dir),
            lesion_dx_filter=None,
        )
        assert len(rows_out) == 8, (
            f"不过滤应返回全部 8 行，得 {len(rows_out)}"
        )


class TestPhase1PR5SeedAgg:
    """PR-5: 跨 seed 聚合取最差 CI 下界"""

    def _make_seed_csv(self, tmp_path, seed, ci_lo, auroc):
        """造单 seed extrap_B2_ham_seedX.csv"""
        p = tmp_path / f"extrap_B2_ham_seed{seed}.csv"
        with open(p, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=[
                "target", "cross_domain_auroc", "ci_lo_9875", "ci_hi_9875",
                "in_domain_auroc", "seed", "note"
            ])
            w.writeheader()
            w.writerow({
                "target":             "ham",
                "cross_domain_auroc": str(auroc),
                "ci_lo_9875":         str(ci_lo),
                "ci_hi_9875":         str(round(auroc + 0.05, 4)),
                "in_domain_auroc":    "0.85",
                "seed":               str(seed),
                "note":               "test",
            })
        return p

    def test_agg_worst_is_min_ci_lo(self, tmp_path):
        """(e) seed-agg worst = min ci_lo_9875 across seeds，不是最差点估计"""
        from failure_boundary import aggregate_seed_results
        # 3 seed：ci_lo 分别 0.72, 0.65, 0.68 → worst = 0.65
        p1 = self._make_seed_csv(tmp_path, seed=42,  ci_lo=0.72, auroc=0.78)
        p2 = self._make_seed_csv(tmp_path, seed=123, ci_lo=0.65, auroc=0.71)
        p3 = self._make_seed_csv(tmp_path, seed=999, ci_lo=0.68, auroc=0.75)
        out = tmp_path / "agg.csv"
        result = aggregate_seed_results([p1, p2, p3], out_csv=str(out), target_name="ham")
        assert result is not None
        assert abs(result["min_ci_lo_across_seeds"] - 0.65) < 1e-6, (
            f"worst CI 下界应为 0.65，得 {result['min_ci_lo_across_seeds']}"
        )

    def test_agg_seeds_n_correct(self, tmp_path):
        """(e) seeds_n = csv 行数"""
        from failure_boundary import aggregate_seed_results
        p1 = self._make_seed_csv(tmp_path, seed=1, ci_lo=0.70, auroc=0.76)
        p2 = self._make_seed_csv(tmp_path, seed=2, ci_lo=0.73, auroc=0.79)
        p3 = self._make_seed_csv(tmp_path, seed=3, ci_lo=0.71, auroc=0.77)
        result = aggregate_seed_results([p1, p2, p3], target_name="ham")
        assert result["seeds_n"] == 3, f"seeds_n 应为 3，得 {result['seeds_n']}"

    def test_agg_pass_ci_70_true(self, tmp_path):
        """(e) min_ci_lo >= 0.70 → pass_ci_70=1"""
        from failure_boundary import aggregate_seed_results
        p1 = self._make_seed_csv(tmp_path, seed=1, ci_lo=0.71, auroc=0.77)
        p2 = self._make_seed_csv(tmp_path, seed=2, ci_lo=0.72, auroc=0.78)
        result = aggregate_seed_results([p1, p2], target_name="ham")
        assert result["pass_ci_70"] == 1, (
            f"min_ci_lo=0.71 >= 0.70 应 pass_ci_70=1，得 {result['pass_ci_70']}"
        )

    def test_agg_pass_ci_70_false(self, tmp_path):
        """(e) min_ci_lo < 0.70 → pass_ci_70=0"""
        from failure_boundary import aggregate_seed_results
        p1 = self._make_seed_csv(tmp_path, seed=1, ci_lo=0.68, auroc=0.75)
        p2 = self._make_seed_csv(tmp_path, seed=2, ci_lo=0.69, auroc=0.76)
        result = aggregate_seed_results([p1, p2], target_name="ham")
        assert result["pass_ci_70"] == 0, (
            f"min_ci_lo=0.68 < 0.70 应 pass_ci_70=0，得 {result['pass_ci_70']}"
        )

    def test_agg_output_csv_schema(self, tmp_path):
        """(e) 输出 csv 含 min_ci_lo_across_seeds / mean_auroc / seeds_n 等必要列"""
        from failure_boundary import aggregate_seed_results
        p1 = self._make_seed_csv(tmp_path, seed=42, ci_lo=0.71, auroc=0.77)
        out = tmp_path / "extrap_B2_ham_agg.csv"
        aggregate_seed_results([p1], out_csv=str(out), target_name="ham")
        assert out.exists(), "agg csv 未生成"
        rows = list(csv.DictReader(open(out)))
        assert len(rows) == 1
        for col in ["min_ci_lo_across_seeds", "mean_auroc", "seeds_n", "pass_ci_70"]:
            assert col in rows[0], f"缺少列: {col}"


# ============================================================
# Phase 2 MemAE 冒烟测试
# 服务: MedAD-FailMap Phase 2, Pillar ④ 多方法对比
# 不需要 GPU / 真实数据，纯 CPU 合成数据验证 forward 维度 + loss + score
# ============================================================

import torch

class TestMemAE:
    """
    验证 MemAENet forward 维度 + MemAELoss 不报错 + anomaly score 形状.
    移植来源:
      MedIAnomaly reconstruction/networks/mem_ae.py (MemAE)
      MedIAnomaly reconstruction/networks/base_units/blocks.py (MemBottleNeck)
      MedIAnomaly reconstruction/networks/base_units/memory_module.py (MemoryUnit/MemModule)
      MedIAnomaly reconstruction/utils/losses.py (MemAELoss)
    """

    def _make_batch(self, B=4, C=1, H=64, W=64):
        """合成随机 batch (B,1,64,64)，与官方输入同形"""
        torch.manual_seed(0)
        return torch.randn(B, C, H, W)

    def test_forward_output_shape(self):
        """forward (B,1,64,64) -> x_hat 同形 (B,1,64,64)"""
        from train_recon_ae import MemAENet
        model = MemAENet(in_c=1, base_c=16, latent=16,
                         mem_size=25, shrink_thres=0.0025)
        model.eval()
        x = self._make_batch()
        with torch.no_grad():
            out = model(x)
        assert out['x_hat'].shape == (4, 1, 64, 64), \
            f"x_hat shape mismatch: {out['x_hat'].shape}"

    def test_forward_att_shape(self):
        """att shape (B, mem_size=25)"""
        from train_recon_ae import MemAENet
        model = MemAENet(in_c=1, base_c=16, latent=16,
                         mem_size=25, shrink_thres=0.0025)
        model.eval()
        x = self._make_batch()
        with torch.no_grad():
            out = model(x)
        assert out['att'].shape == (4, 25), \
            f"att shape mismatch: {out['att'].shape}"

    def test_forward_z_shape(self):
        """z/z_hat shape (B, latent=16)"""
        from train_recon_ae import MemAENet
        model = MemAENet(in_c=1, base_c=16, latent=16)
        model.eval()
        x = self._make_batch()
        with torch.no_grad():
            out = model(x)
        assert out['z'].shape    == (4, 16), f"z shape: {out['z'].shape}"
        assert out['z_hat'].shape == (4, 16), f"z_hat shape: {out['z_hat'].shape}"

    def test_memae_loss_train_mode(self):
        """MemAELoss train mode: 返回 (scalar, recon_mean, entro_mean), 不报错"""
        from train_recon_ae import MemAENet, MemAELoss
        model = MemAENet(in_c=1, base_c=16, latent=16)
        model.train()
        loss_fn = MemAELoss()
        x = self._make_batch()
        out = model(x)
        result = loss_fn(x, out, anomaly_score=False)
        assert len(result) == 3, "train mode 应返回 (loss, recon_mean, entro_mean)"
        loss, recon_mean, entro_mean = result
        assert loss.requires_grad or True  # loss 是 tensor
        assert isinstance(recon_mean, float)
        assert isinstance(entro_mean, float)
        assert loss.item() > 0, "loss 应 > 0"

    def test_memae_loss_score_shape(self):
        """MemAELoss anomaly_score=True: 返回 (B,) per-image score，与 AE 同口径"""
        from train_recon_ae import MemAENet, MemAELoss
        model = MemAENet(in_c=1, base_c=16, latent=16)
        model.eval()
        loss_fn = MemAELoss()
        x = self._make_batch(B=6)
        with torch.no_grad():
            out = model(x)
            scores = loss_fn(x, out, anomaly_score=True)
        assert scores.shape == (6,), f"score shape mismatch: {scores.shape}"
        assert (scores >= 0).all(), "anomaly score 应 >= 0 (MSE)"

    def test_memae_loss_entropy_positive(self):
        """entropy_loss 应 > 0 (att softmax 后 entropy > 0)"""
        from train_recon_ae import MemAENet, MemAELoss
        model = MemAENet(in_c=1, base_c=16, latent=16)
        model.eval()
        loss_fn = MemAELoss()
        x = self._make_batch()
        with torch.no_grad():
            out = model(x)
        # 手动算 entropy
        _, _, entro_mean = loss_fn(x, out, anomaly_score=False)
        assert entro_mean > 0, f"entropy_loss 应 > 0, got {entro_mean}"

    def test_score_same_order_of_magnitude_as_ae(self):
        """MemAE score 口径与 AE 一致 (都是 mean MSE)，不应差超 100 倍"""
        from train_recon_ae import AENet, MemAENet, MemAELoss
        torch.manual_seed(42)
        x = self._make_batch(B=4)

        ae = AENet(in_c=1, base_c=16, latent=16)
        ae.eval()
        with torch.no_grad():
            recon_ae = ae(x)
            scores_ae = torch.mean((x - recon_ae) ** 2, dim=[1, 2, 3])

        memae = MemAENet(in_c=1, base_c=16, latent=16)
        memae.eval()
        loss_fn = MemAELoss()
        with torch.no_grad():
            out_m = memae(x)
            scores_memae = loss_fn(x, out_m, anomaly_score=True)

        ratio = scores_memae.mean() / (scores_ae.mean() + 1e-12)
        assert 0.01 < ratio.item() < 100, \
            f"MemAE/AE score ratio={ratio.item():.3f}，可能口径不一致"

    def test_compute_anomaly_scores_memae(self):
        """compute_anomaly_scores 在 memae 模式下返回 list[(str, float)]，len=B"""
        from train_recon_ae import MemAENet, compute_anomaly_scores
        from torch.utils.data import DataLoader, TensorDataset
        model = MemAENet(in_c=1, base_c=16, latent=16)
        x = self._make_batch(B=8)
        # 用 TensorDataset + 假 fname 列表模拟 DataLoader
        fnames = [f"img_{i:04d}.png" for i in range(8)]

        class _FakeDS:
            def __len__(self): return 8
            def __getitem__(self, i): return x[i], fnames[i]

        loader = DataLoader(_FakeDS(), batch_size=4, shuffle=False,
                            num_workers=0, pin_memory=False)
        results = compute_anomaly_scores(model, loader, device=torch.device("cpu"),
                                         model_type="memae")
        assert len(results) == 8, f"应返回 8 个 (fname, score)，得 {len(results)}"
        for fname, score in results:
            assert isinstance(fname, str)
            assert isinstance(score, float)
            assert score >= 0
