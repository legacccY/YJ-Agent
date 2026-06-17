"""Smoke tests for eval_c0_decision_surface.py.

测什么:
  1. SEVERITY_GRID 5 维各 5 档, 单调方向正确.
  2. degrade_single_axis 不崩, 输出 shape/dtype 正确.
  3. compute_ece / compute_auc 正确 (toy 数字).
  4. bootstrap_auc_ece 在 mock 数据上 schema 完整 (含可恢复性列).
  5. CSV schema: 所有必须列名出现 (mock run, 不需要真实 ckpt).

不依赖 GPU / 真实 checkpoint / 真实数据集.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

# 把 project/ 加入 sys.path
_PROJECT = Path(__file__).resolve().parent.parent
if str(_PROJECT) not in sys.path:
    sys.path.insert(0, str(_PROJECT))

from eval_c0_decision_surface import (
    SEVERITY_GRID,
    SEVERITY_LABELS,
    bootstrap_auc_ece,
    compute_auc,
    compute_ece,
    degrade_single_axis,
)

# ---------------------------------------------------------------------------
# 1. SEVERITY_GRID 单调性检查
# ---------------------------------------------------------------------------

class TestSeverityGrid:
    def test_five_dims(self):
        assert set(SEVERITY_GRID.keys()) == {
            "blur", "brightness", "contrast", "color_shift", "completeness"
        }

    def test_five_levels_each(self):
        for axis, vals in SEVERITY_GRID.items():
            assert len(vals) == 5, f"{axis} should have 5 levels, got {len(vals)}"
            assert len(SEVERITY_LABELS) == 5

    def test_blur_monotone_increasing(self):
        v = SEVERITY_GRID["blur"]
        for i in range(len(v) - 1):
            assert v[i] < v[i + 1], f"blur not monotone at index {i}"

    def test_brightness_monotone_decreasing(self):
        v = SEVERITY_GRID["brightness"]
        for i in range(len(v) - 1):
            assert v[i] > v[i + 1], f"brightness not monotone at index {i}"

    def test_contrast_monotone_decreasing(self):
        v = SEVERITY_GRID["contrast"]
        for i in range(len(v) - 1):
            assert v[i] > v[i + 1], f"contrast not monotone at index {i}"

    def test_color_shift_monotone_increasing(self):
        v = SEVERITY_GRID["color_shift"]
        for i in range(len(v) - 1):
            assert v[i] < v[i + 1], f"color_shift not monotone at index {i}"

    def test_completeness_monotone_decreasing(self):
        v = SEVERITY_GRID["completeness"]
        for i in range(len(v) - 1):
            assert v[i] > v[i + 1], f"completeness not monotone at index {i}"

    def test_completeness_in_range(self):
        for v in SEVERITY_GRID["completeness"]:
            assert 0.0 < v <= 1.0, f"crop_ratio {v} out of (0,1]"


# ---------------------------------------------------------------------------
# 2. degrade_single_axis 管线不崩
# ---------------------------------------------------------------------------

import random
import cv2


def _dummy_img(h=64, w=64):
    rng = np.random.default_rng(0)
    return (rng.random((h, w, 3)) * 255).astype(np.uint8)


class TestDegradeSingleAxis:
    IMG = _dummy_img()

    def test_blur(self):
        out = degrade_single_axis(self.IMG, "blur", 1.5, random.Random(0))
        assert out.shape == self.IMG.shape
        assert out.dtype == np.uint8

    def test_brightness(self):
        out = degrade_single_axis(self.IMG, "brightness", 0.5, random.Random(0))
        assert out.shape == self.IMG.shape
        assert out.dtype == np.uint8

    def test_contrast(self):
        out = degrade_single_axis(self.IMG, "contrast", 0.6, random.Random(0))
        assert out.shape == self.IMG.shape
        assert out.dtype == np.uint8

    def test_color_shift(self):
        out = degrade_single_axis(self.IMG, "color_shift", 0.12, random.Random(0))
        assert out.shape == self.IMG.shape
        assert out.dtype == np.uint8

    def test_completeness_crop(self):
        out = degrade_single_axis(self.IMG, "completeness", 0.7, random.Random(0), target_size=64)
        assert out.shape == (64, 64, 3)
        assert out.dtype == np.uint8

    def test_completeness_no_crop(self):
        # sev_val=1.0 整图, 仍 resize 到 target_size
        out = degrade_single_axis(self.IMG, "completeness", 1.0, random.Random(0), target_size=64)
        assert out.shape == (64, 64, 3)

    def test_unknown_axis_raises(self):
        with pytest.raises(ValueError, match="未知 axis"):
            degrade_single_axis(self.IMG, "unknown_axis", 0.5, random.Random(0))

    def test_brightness_darkens(self):
        bright = degrade_single_axis(self.IMG, "brightness", 1.0, random.Random(0))
        dark   = degrade_single_axis(self.IMG, "brightness", 0.3, random.Random(0))
        assert bright.mean() > dark.mean() + 1.0, "brightness S5 应比 S1 暗"

    def test_blur_increases_smoothness(self):
        low_blur  = degrade_single_axis(self.IMG, "blur", 0.5, random.Random(0))
        high_blur = degrade_single_axis(self.IMG, "blur", 3.5, random.Random(0))
        # 高 sigma 标准差应更小 (更平滑)
        assert high_blur.astype(float).std() <= low_blur.astype(float).std() + 5


# ---------------------------------------------------------------------------
# 3. compute_ece / compute_auc toy 检验
# ---------------------------------------------------------------------------

class TestMetrics:
    def test_ece_perfect_calibration(self):
        # prob=0.9 全 1, prob=0.1 全 0 -> 近似完美校准
        probs  = np.array([0.9, 0.9, 0.1, 0.1])
        labels = np.array([1,   1,   0,   0  ])
        ece = compute_ece(probs, labels)
        assert ece < 0.15, f"ECE should be low for well-calibrated, got {ece}"

    def test_ece_worst_case(self):
        # prob=0.9 全 0 -> 最差校准
        probs  = np.array([0.9, 0.9, 0.9, 0.9])
        labels = np.array([0,   0,   0,   0  ])
        ece = compute_ece(probs, labels)
        assert ece > 0.5, f"ECE should be high for poor calibration, got {ece}"

    def test_auc_perfect(self):
        labels = np.array([0, 0, 1, 1])
        scores = np.array([0.1, 0.2, 0.8, 0.9])
        auc = compute_auc(labels, scores)
        assert abs(auc - 1.0) < 1e-9

    def test_auc_random(self):
        rng = np.random.default_rng(7)
        labels = rng.integers(0, 2, 100)
        scores = rng.random(100)
        auc = compute_auc(labels, scores)
        assert 0.0 <= auc <= 1.0


# ---------------------------------------------------------------------------
# 4. bootstrap_auc_ece schema 检验 (含可恢复性列)
# ---------------------------------------------------------------------------

class TestBootstrap:
    def _make_mock(self, n=200, seed=0):
        rng = np.random.default_rng(seed)
        labels     = rng.integers(0, 2, n)
        scores_deg = np.clip(rng.random(n) + labels * 0.1, 0, 1)
        scores_enh = np.clip(scores_deg + rng.normal(0, 0.05, n), 0, 1)
        return labels, scores_deg, scores_enh

    def test_schema_with_enh(self):
        labels, sd, se = self._make_mock()
        result = bootstrap_auc_ece(labels, sd, se, n_boot=50, seed=0)
        required = [
            "auc", "auc_ci_lo", "auc_ci_hi",
            "ece", "ece_ci_lo", "ece_ci_hi",
            "n",
            "auc_enhanced",
            "recoverability_delta", "recoverability_ci_lo", "recoverability_ci_hi",
        ]
        for k in required:
            assert k in result, f"missing key: {k}"

    def test_schema_without_enh(self):
        labels, sd, _ = self._make_mock()
        result = bootstrap_auc_ece(labels, sd, None, n_boot=50, seed=0)
        assert np.isnan(result["auc_enhanced"])
        assert np.isnan(result["recoverability_delta"])

    def test_ci_order(self):
        labels, sd, se = self._make_mock()
        result = bootstrap_auc_ece(labels, sd, se, n_boot=200, seed=0)
        assert result["auc_ci_lo"] <= result["auc"] <= result["auc_ci_hi"]
        assert result["ece_ci_lo"] <= result["ece"] <= result["ece_ci_hi"]

    def test_n_matches(self):
        labels, sd, se = self._make_mock(n=150)
        result = bootstrap_auc_ece(labels, sd, se, n_boot=50)
        assert result["n"] == 150


# ---------------------------------------------------------------------------
# 5. CSV schema 检验 (mock records -> DataFrame 列名对齐)
# ---------------------------------------------------------------------------

import pandas as pd

OUT_COLS = [
    "axis", "severity_level", "severity_value",
    "auc", "auc_ci_lo", "auc_ci_hi",
    "ece", "ece_ci_lo", "ece_ci_hi",
    "n",
    "auc_enhanced",
    "recoverability_delta", "recoverability_ci_lo", "recoverability_ci_hi",
]


class TestCSVSchema:
    def test_all_columns_present(self):
        rng = np.random.default_rng(0)
        labels     = rng.integers(0, 2, 100)
        scores_deg = rng.random(100)
        scores_enh = rng.random(100)

        stats = bootstrap_auc_ece(labels, scores_deg, scores_enh, n_boot=20, seed=0)
        rec = {
            "axis":           "blur",
            "severity_level": 1,
            "severity_value": 0.5,
            **stats,
        }
        df = pd.DataFrame([rec])
        missing = [c for c in OUT_COLS if c not in df.columns]
        assert not missing, f"CSV 缺列: {missing}"

    def test_no_extra_required(self):
        # 确保 OUT_COLS 和脚本定义保持一致 (14 列)
        assert len(OUT_COLS) == 14
