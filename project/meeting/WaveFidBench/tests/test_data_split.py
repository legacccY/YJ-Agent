"""
test_data_split.py — WaveFidBench pytest

测试覆盖：
1. patient split 模式下同 subject 不跨 train/test（造假 subject ID 测）
2. slice 模式有泄漏警告日志（WARNING 级别含关键词）
3. 比例之和 ≠ 1 时 split 报错

mock：不连真数据（造假 dataframe），coder 不跑，主线跑真烟测
"""

import os
import sys
import tempfile
import warnings
import logging
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# 让 pytest 能找到 src/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def _make_fake_df(n_patients: int = 20, slices_per_patient: int = 5) -> pd.DataFrame:
    """构造假 dataframe：每个 subject 有多张切片，filepath 包含 subject ID。"""
    records = []
    labels = ["NonDemented", "VeryMildDemented", "MildDemented", "ModerateDemented"]
    for i in range(n_patients):
        subj_id = f"OAS1_{i:04d}"
        label = labels[i % len(labels)]
        for j in range(slices_per_patient):
            records.append({
                "filepath": f"/fake/data/{subj_id}_MR1/slice_{j:03d}.jpg",
                "label": label,
            })
    return pd.DataFrame(records)


# =========================================================
# 测试 1：patient split — 同 subject 不跨 train/test
# =========================================================

class TestPatientSplit:
    def _run_patient_split(self, df, cfg):
        """调用 data_split.py 中的 split_patient 函数。"""
        from data_split import split_patient
        import tempfile
        out_dir = Path(tempfile.mkdtemp())
        return split_patient(df, cfg, out_dir)

    def _make_cfg(self, **kwargs):
        base = {
            "train_ratio": 0.70,
            "val_ratio": 0.15,
            "test_ratio": 0.15,
            "random_seed": 42,
            "subject_id_regex": r"^(OAS1_\d+)",
        }
        base.update(kwargs)
        return base

    def test_no_subject_crosses_train_test(self):
        """patient split 后 train/test subject 无交叉。"""
        from data_split import extract_subject_id

        df = _make_fake_df(n_patients=40, slices_per_patient=5)
        cfg = self._make_cfg()
        splits = self._run_patient_split(df, cfg)

        regex = cfg["subject_id_regex"]
        train_subjects = set(
            df.iloc[splits["train"]]["filepath"].apply(
                lambda p: extract_subject_id(p, regex)
            )
        )
        test_subjects = set(
            df.iloc[splits["test"]]["filepath"].apply(
                lambda p: extract_subject_id(p, regex)
            )
        )
        val_subjects = set(
            df.iloc[splits["val"]]["filepath"].apply(
                lambda p: extract_subject_id(p, regex)
            )
        )

        assert len(train_subjects & test_subjects) == 0, (
            f"train/test 共享 subject：{train_subjects & test_subjects}"
        )
        assert len(val_subjects & test_subjects) == 0, (
            f"val/test 共享 subject：{val_subjects & test_subjects}"
        )
        assert len(train_subjects & val_subjects) == 0, (
            f"train/val 共享 subject：{train_subjects & val_subjects}"
        )

    def test_all_samples_assigned(self):
        """patient split 的三份总和 = 总样本数。"""
        df = _make_fake_df(n_patients=40, slices_per_patient=5)
        cfg = self._make_cfg()
        splits = self._run_patient_split(df, cfg)

        total = sum(len(v) for v in splits.values())
        assert total == len(df), f"分配总数 {total} != 样本数 {len(df)}"

    def test_each_split_nonempty(self):
        """三份均非空。"""
        df = _make_fake_df(n_patients=40, slices_per_patient=5)
        cfg = self._make_cfg()
        splits = self._run_patient_split(df, cfg)

        for name, idx in splits.items():
            assert len(idx) > 0, f"{name} split 为空"

    def test_subject_id_extraction(self):
        """subject ID 提取函数正确。"""
        from data_split import extract_subject_id

        regex = r"^(OAS1_\d+)"
        cases = [
            ("/data/OAS1_0001_MR1/slice_000.jpg", "OAS1_0001"),
            ("/data/OAS1_9999_MR1/slice_100.jpg", "OAS1_9999"),
        ]
        for filepath, expected in cases:
            result = extract_subject_id(filepath, regex)
            assert result == expected, f"提取失败：{filepath} -> {result}（期望 {expected}）"


# =========================================================
# 测试 2：slice 模式有泄漏警告
# =========================================================

class TestSliceSplitLeakageWarning:
    def test_slice_mode_emits_leakage_warning(self, caplog):
        """slice_split 必须以 WARNING 级别发出含「泄漏」或「slice-level」关键词的警告。"""
        from data_split import split_slice
        import tempfile

        df = _make_fake_df(n_patients=10, slices_per_patient=5)
        cfg = {
            "train_ratio": 0.70,
            "val_ratio": 0.15,
            "test_ratio": 0.15,
            "random_seed": 42,
        }
        out_dir = Path(tempfile.mkdtemp())

        with caplog.at_level(logging.WARNING, logger="data_split"):
            split_slice(df, cfg, out_dir)

        # 检查至少有一条含关键词的 WARNING
        warning_msgs = [
            r.message for r in caplog.records if r.levelno >= logging.WARNING
        ]
        assert len(warning_msgs) > 0, "slice 模式未发出任何 WARNING"

        combined = " ".join(str(m) for m in warning_msgs).lower()
        has_keyword = any(kw in combined for kw in ["泄漏", "slice-level", "leakage", "leak"])
        assert has_keyword, (
            f"WARNING 未含「泄漏」/「slice-level」/「leakage」关键词。实际: {warning_msgs}"
        )

    def test_slice_mode_does_not_raise(self):
        """slice_split 在正常输入下不应抛异常。"""
        from data_split import split_slice
        import tempfile

        df = _make_fake_df(n_patients=10, slices_per_patient=5)
        cfg = {
            "train_ratio": 0.70,
            "val_ratio": 0.15,
            "test_ratio": 0.15,
            "random_seed": 42,
        }
        out_dir = Path(tempfile.mkdtemp())
        # 不抛即通过
        splits = split_slice(df, cfg, out_dir)
        assert "train" in splits and "val" in splits and "test" in splits


# =========================================================
# 测试 3：比例校验
# =========================================================

class TestSplitRatioValidation:
    def test_invalid_ratio_raises(self):
        """train+val+test 比例不等于 1 时 split_slice 应 AssertionError。"""
        from data_split import split_slice
        import tempfile

        df = _make_fake_df(n_patients=10, slices_per_patient=5)
        cfg_bad = {
            "train_ratio": 0.60,
            "val_ratio": 0.20,
            "test_ratio": 0.30,  # 总和 1.10，不合法
            "random_seed": 42,
        }
        out_dir = Path(tempfile.mkdtemp())
        with pytest.raises(AssertionError):
            split_slice(df, cfg_bad, out_dir)
