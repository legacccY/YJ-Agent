# -*- coding: utf-8 -*-
"""probes 单测：attentive 头 forward shape、attentive/knn/linear probe 跑通、无泄漏断言。"""
import numpy as np
import pytest
import torch

import probes as P


def _mock_pooled(n, d, c, pid_start, seed=0):
    rng = np.random.RandomState(seed)
    y = rng.randint(0, 2, size=(n, c)).astype(np.float32)
    x = (rng.randn(n, d).astype(np.float32) + y[:, :1] * 0.5)  # 弱信号
    pids = np.arange(pid_start, pid_start + n, dtype=np.int64)
    return dict(feats=x, labels=y, patient_ids=pids)


def _mock_tokens(n, t, d, c, pid_start, seed=0):
    rng = np.random.RandomState(seed)
    y = rng.randint(0, 2, size=(n, c)).astype(np.float32)
    x = rng.randn(n, t, d).astype(np.float32)
    pids = np.arange(pid_start, pid_start + n, dtype=np.int64)
    return dict(tokens=x, labels=y, patient_ids=pids)


def test_attentive_head_forward_shape():
    head = P.AttentiveProbeHead(embed_dim=32, num_classes=5, num_heads=4)
    x = torch.randn(3, 7, 32)
    out = head(x)
    assert out.shape == (3, 5)


def test_attentive_head_heads_divide_dim():
    # num_heads 必须整除 embed_dim（nn.MultiheadAttention 约束）
    with pytest.raises(Exception):
        P.AttentiveProbeHead(embed_dim=30, num_classes=4, num_heads=4)


def test_run_attentive_probe_mha_cpu():
    tr = _mock_tokens(24, 7, 32, 4, pid_start=0, seed=1)
    te = _mock_tokens(12, 7, 32, 4, pid_start=100, seed=2)
    res = P.run_attentive_probe(tr, te, feature_dim=32, num_heads=4, epochs=2,
                                batch_size=8, device='cpu', head='mha')
    assert isinstance(res['mAUC'], float)
    assert res['n_train'] == 24 and res['n_test'] == 12
    assert len(res['per_class_auc']) == 4


def test_run_knn_probe_cpu():
    tr = _mock_pooled(40, 16, 4, pid_start=0, seed=3)
    te = _mock_pooled(15, 16, 4, pid_start=200, seed=4)
    res = P.run_knn_probe(tr, te, k=20, device='cpu')
    assert isinstance(res['mAUC'], float)
    assert res['n_train'] == 40 and res['n_test'] == 15
    assert len(res['per_class_auc']) == 4


def test_knn_k_capped_to_ntrain():
    tr = _mock_pooled(5, 8, 3, pid_start=0, seed=5)   # Ntr=5 < k=20
    te = _mock_pooled(4, 8, 3, pid_start=50, seed=6)
    res = P.run_knn_probe(tr, te, k=20, device='cpu')  # 不应越界
    assert res['n_train'] == 5


def test_run_linear_probe_still_works():
    tr = _mock_pooled(30, 16, 4, pid_start=0, seed=7)
    te = _mock_pooled(12, 16, 4, pid_start=300, seed=8)
    res = P.run_linear_probe(tr, te, epochs=3, device='cpu')
    assert isinstance(res['mAUC'], float)
    assert res['n_train'] == 30


def test_patient_leak_assert_raises():
    a = [1, 2, 3]
    b = [3, 4, 5]   # 3 重叠
    with pytest.raises(AssertionError):
        P.assert_no_patient_leak(a, b)
    # 无重叠不报
    P.assert_no_patient_leak([1, 2], [3, 4])
