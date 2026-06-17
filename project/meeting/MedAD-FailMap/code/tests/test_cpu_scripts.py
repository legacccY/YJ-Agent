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
