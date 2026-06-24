"""
tests/test_braingb_lane.py
HyperFidBench Gate1 / BrainGB-ABIDE-I 泳道 pytest 单测

覆盖：
  1. build_graphs: FC 矩阵 shape + 无 nan 断言
  2. make_split: patient-level split 无泄漏（同 SUB_ID 不跨 train/test）
  3. make_split: 每 fold 分层正确（两类各有样本）
  4. eval_fidelity: fidelity 输出非 nan（mock model + mock DataLoader）

约定：
  - 全部使用 mock / 合成数据，无需下载真实 ABIDE，无需 GPU，无需 BrainGB 训练权重
  - 不执行任何训练、不走 nilearn 下载
  - 主线按 `python -m pytest tests/test_braingb_lane.py -x -q` 跑
"""

import sys
import os
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

# 保证能 import src/braingb_lane
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "src" / "braingb_lane"))


# ---------------------------------------------------------------------------
# 辅助：合成 ABIDE 数据
# ---------------------------------------------------------------------------

def _make_fake_abide_npy(tmp_path: Path, n_subjects: int = 40, n_roi: int = 10):
    """
    生成最小合成 abide.npy，格式对齐 BrainGB load_data_abide 期望：
        data["corr"]  : (N, n_roi, n_roi) float32
        data["label"] : (N,) int  1=ASD, 0=TD
        data["sub_ids"]: (N,) 唯一被试 ID
        data["site_ids"]: (N,) site
    """
    rng = np.random.default_rng(42)
    corr = rng.standard_normal((n_subjects, n_roi, n_roi)).astype(np.float32)
    # 对称化 + 对角线置 0
    for i in range(n_subjects):
        corr[i] = (corr[i] + corr[i].T) / 2
        np.fill_diagonal(corr[i], 0.0)
    labels = np.array([i % 2 for i in range(n_subjects)], dtype=int)  # 交替 ASD/TD
    sub_ids = np.arange(10000, 10000 + n_subjects)
    # 分配 5 个假 site
    site_ids = np.array([i % 5 for i in range(n_subjects)])

    data_dict = {
        "corr": corr,
        "label": labels,
        "sub_ids": sub_ids,
        "site_ids": site_ids,
    }
    npy_path = tmp_path / "abide.npy"
    np.save(str(npy_path), data_dict)
    return npy_path, data_dict


def _make_fake_pheno_csv(tmp_path: Path, n_subjects: int = 40):
    """生成合成 split_phenotypic.csv，列对齐 make_split.py 期望。"""
    rng = np.random.default_rng(42)
    sub_ids = np.arange(10000, 10000 + n_subjects)
    dx_group = np.array([1 if i % 2 == 0 else 2 for i in range(n_subjects)])  # 1=ASD, 2=TD
    site_ids = np.array([i % 5 for i in range(n_subjects)])
    df = pd.DataFrame({
        "SUB_ID": sub_ids,
        "SITE_ID": site_ids,
        "DX_GROUP": dx_group,
        "label": (dx_group == 1).astype(int),
    })
    csv_path = tmp_path / "split_phenotypic.csv"
    df.to_csv(str(csv_path), index=False)
    return csv_path, df


# ---------------------------------------------------------------------------
# 1. build_graphs: FC 矩阵 shape 和 nan 检查
# ---------------------------------------------------------------------------

class TestBuildGraphs:
    """验证 pearson_corr 产出 shape 正确、无 nan、对角线为 0。"""

    def test_pearson_corr_shape(self):
        from braingb_lane.build_graphs import pearson_corr
        rng = np.random.default_rng(0)
        ts = rng.standard_normal((10, 100))  # (n_roi=10, n_timepoints=100)
        corr = pearson_corr(ts)
        assert corr.shape == (10, 10), f"期望 (10,10)，得 {corr.shape}"

    def test_pearson_corr_no_nan(self):
        from braingb_lane.build_graphs import pearson_corr
        rng = np.random.default_rng(1)
        ts = rng.standard_normal((20, 150))
        corr = pearson_corr(ts)
        assert not np.any(np.isnan(corr)), "FC 矩阵含 nan，pearson_corr 未正确处理"

    def test_pearson_corr_diagonal_zero(self):
        from braingb_lane.build_graphs import pearson_corr
        rng = np.random.default_rng(2)
        ts = rng.standard_normal((10, 80))
        corr = pearson_corr(ts)
        np.testing.assert_array_equal(
            np.diag(corr), np.zeros(10),
            err_msg="对角线应为 0（自相关已置 0）"
        )

    def test_pearson_corr_symmetric(self):
        from braingb_lane.build_graphs import pearson_corr
        rng = np.random.default_rng(3)
        ts = rng.standard_normal((15, 120))
        corr = pearson_corr(ts)
        np.testing.assert_allclose(
            corr, corr.T, atol=1e-6,
            err_msg="FC 矩阵应对称"
        )

    def test_corr_range(self):
        """Pearson 相关系数值域 [-1, 1]（对角线置 0 后）"""
        from braingb_lane.build_graphs import pearson_corr
        rng = np.random.default_rng(4)
        ts = rng.standard_normal((10, 100))
        corr = pearson_corr(ts)
        assert np.all(corr >= -1.0 - 1e-6), "FC 值低于 -1"
        assert np.all(corr <= 1.0 + 1e-6), "FC 值高于 1"

    def test_abide_npy_format(self, tmp_path):
        """合成 abide.npy 格式对齐 BrainGB load_data_abide 期望。"""
        npy_path, data_dict = _make_fake_abide_npy(tmp_path, n_subjects=10, n_roi=5)
        data = np.load(str(npy_path), allow_pickle=True).item()
        assert "corr" in data, "abide.npy 缺 'corr' key"
        assert "label" in data, "abide.npy 缺 'label' key"
        assert data["corr"].shape[0] == data["label"].shape[0], \
            "corr 和 label 被试数不一致"
        assert data["corr"].ndim == 3, "corr 应为 3D (N, n_roi, n_roi)"
        assert data["corr"].shape[1] == data["corr"].shape[2], \
            "FC 矩阵应为方阵"


# ---------------------------------------------------------------------------
# 2. make_split: patient-level split 无泄漏
# ---------------------------------------------------------------------------

class TestMakeSplit:
    """验证 patient-level StratifiedKFold split 的核心红线。"""

    def test_no_sub_id_leakage(self, tmp_path):
        """
        红线：同一 SUB_ID 不同时出现在 train 和 test（不跨 fold）。
        由于 make_split 每个 SUB_ID 只占一行，天然满足；
        此测试显式验证 split_df 中无重复 SUB_ID。
        """
        from braingb_lane.make_split import make_split

        pheno_csv, pheno_df = _make_fake_pheno_csv(tmp_path, n_subjects=40)
        braingb_dir = tmp_path
        # 将 pheno 写成 split_phenotypic.csv 在 braingb_dir
        split_df = make_split(
            braingb_abide_dir=braingb_dir,
            output_dir=tmp_path,
            n_splits=5,
            seed=112078,
        )
        # 无重复 SUB_ID
        assert not split_df["SUB_ID"].duplicated().any(), \
            "SUB_ID 有重复，patient-level split 完整性被破坏"

    def test_same_sub_id_not_in_both_train_and_test(self, tmp_path):
        """
        更严格版：对每个 SUB_ID，不存在任何 fold 中同时标 train 和 test。
        （这里因每 SUB_ID 只有 1 行，逻辑上不可能，但留作防御性断言。）
        """
        from braingb_lane.make_split import make_split

        _make_fake_pheno_csv(tmp_path, n_subjects=40)
        split_df = make_split(
            braingb_abide_dir=tmp_path,
            output_dir=tmp_path,
            n_splits=5,
            seed=112078,
        )
        fold_cols = [c for c in split_df.columns if c.startswith("fold_")]
        for sub_id, group in split_df.groupby("SUB_ID"):
            for col in fold_cols:
                vals = set(group[col].unique())
                # 每个 SUB_ID 在每个 fold 只有 1 行，vals 必为单元素集
                assert len(vals) == 1, \
                    f"SUB_ID={sub_id} 在 {col} 中出现多个角色 {vals}（不应出现）"

    def test_stratified_both_classes_in_test(self, tmp_path):
        """每个 fold 的 test 集两类（ASD/TD）都有样本。"""
        from braingb_lane.make_split import make_split

        _make_fake_pheno_csv(tmp_path, n_subjects=40)
        split_df = make_split(
            braingb_abide_dir=tmp_path,
            output_dir=tmp_path,
            n_splits=5,
            seed=112078,
        )
        fold_cols = [c for c in split_df.columns if c.startswith("fold_")]
        for col in fold_cols:
            test_labels = split_df.loc[split_df[col] == "test", "label"]
            assert test_labels.nunique() == 2, \
                f"{col} test 集只有 1 类，StratifiedKFold 出错"

    def test_output_csv_columns(self, tmp_path):
        """split_indices.csv 含预期列（供 eval_fidelity.py 读取）。"""
        from braingb_lane.make_split import make_split

        _make_fake_pheno_csv(tmp_path, n_subjects=20)
        split_df = make_split(
            braingb_abide_dir=tmp_path,
            output_dir=tmp_path,
            n_splits=5,
            seed=112078,
        )
        assert "SUB_ID" in split_df.columns
        assert "label" in split_df.columns
        assert "fold_0" in split_df.columns
        assert "fold_4" in split_df.columns

    def test_train_test_cover_all_subjects(self, tmp_path):
        """train + test = 全集（无被试丢失）。"""
        from braingb_lane.make_split import make_split

        _make_fake_pheno_csv(tmp_path, n_subjects=20)
        split_df = make_split(
            braingb_abide_dir=tmp_path,
            output_dir=tmp_path,
            n_splits=5,
            seed=112078,
        )
        for col in [c for c in split_df.columns if c.startswith("fold_")]:
            vals = split_df[col].unique()
            assert set(vals) <= {"train", "test"}, \
                f"{col} 含未知值: {vals}"
            n_covered = split_df[col].isin(["train", "test"]).sum()
            assert n_covered == len(split_df), f"{col} 有 {len(split_df)-n_covered} 行未被分配"


# ---------------------------------------------------------------------------
# 3. eval_fidelity: fidelity 输出非 nan（mock model + mock loader）
# ---------------------------------------------------------------------------

class TestEvalFidelity:
    """
    验证 eval_fidelity.compute_fidelity_for_loader 在 mock 输入下产出非 nan。
    不加载 BrainGB 真实权重，不走 GNNExplainer 真实优化（mock algorithm）。
    """

    def _make_mock_graph_data(self, n_nodes: int = 10, n_feat: int = 10):
        """构造最小 PyG Data 对象（单 graph）"""
        import torch
        from torch_geometric.data import Data

        x = torch.randn(n_nodes, n_feat)
        # 完全图 edge_index (无自环)
        src, dst = [], []
        for i in range(n_nodes):
            for j in range(n_nodes):
                if i != j:
                    src.append(i)
                    dst.append(j)
        edge_index = torch.tensor([src, dst], dtype=torch.long)
        edge_attr = torch.randn(edge_index.shape[1])
        y = torch.tensor([1])
        batch = torch.zeros(n_nodes, dtype=torch.long)
        return Data(x=x, edge_index=edge_index, edge_attr=edge_attr, y=y,
                    num_nodes=n_nodes, batch=batch)

    def test_fidelity_non_nan_with_mock(self, tmp_path):
        """
        用 mock Explainer 验证 compute_fidelity_for_loader 返回有限数（非 nan）。
        mock Explainer.forward 返回 mock Explanation with valid masks。
        """
        import torch
        from unittest.mock import MagicMock, patch
        from torch_geometric.data import Data

        # mock Explanation 对象
        n_nodes, n_feat, n_edges = 10, 10, 90
        mock_explanation = MagicMock()
        mock_explanation.node_mask = torch.ones(n_nodes, n_feat)  # 全 1 节点 mask
        mock_explanation.edge_mask = torch.ones(n_edges)           # 全 1 边 mask

        # mock fidelity 函数返回有限值（模拟 PyG fidelity 正常路径）
        mock_fid_pos = torch.tensor(0.15)
        mock_fid_neg = torch.tensor(0.32)

        # mock Explainer
        mock_explainer = MagicMock()
        mock_explainer.return_value = mock_explanation

        # mock DataLoader（返回单个 batch）
        data = self._make_mock_graph_data(n_nodes=n_nodes, n_feat=n_feat)
        mock_loader = [data]

        device = torch.device("cpu")

        with patch(
            "torch_geometric.explain.metric.fidelity",
            return_value=(mock_fid_pos, mock_fid_neg),
        ):
            # 直接调用核心函数（不走 GPU/GNNExplainer）
            from braingb_lane.eval_fidelity import compute_fidelity_for_loader
            results = compute_fidelity_for_loader(
                mock_explainer, mock_loader, device, max_samples=1
            )

        assert len(results) == 1, f"期望 1 个结果，得 {len(results)}"
        fid_pos, fid_neg = results[0]
        assert not np.isnan(fid_pos), f"fid+ 为 nan（期望非 nan）"
        assert not np.isnan(fid_neg), f"fid- 为 nan（期望非 nan）"
        assert np.isfinite(fid_pos), f"fid+ 非有限数: {fid_pos}"
        assert np.isfinite(fid_neg), f"fid- 非有限数: {fid_neg}"

    def test_fidelity_graceful_nan_on_exception(self, tmp_path):
        """
        模拟 fidelity 抛异常时，compute_fidelity_for_loader 返回 (nan, nan) 而非崩溃。
        （eval_fidelity.py 已做 try/except 兜底）
        """
        import torch
        from unittest.mock import MagicMock

        # 让 explainer 调用时抛异常
        def bad_explainer(*args, **kwargs):
            raise RuntimeError("模拟 GNNExplainer 失败")

        data = self._make_mock_graph_data()
        mock_loader = [data]
        device = torch.device("cpu")

        from braingb_lane.eval_fidelity import compute_fidelity_for_loader
        results = compute_fidelity_for_loader(bad_explainer, mock_loader, device, max_samples=1)

        assert len(results) == 1
        fid_pos, fid_neg = results[0]
        assert np.isnan(fid_pos), "异常时 fid+ 应为 nan"
        assert np.isnan(fid_neg), "异常时 fid- 应为 nan"

    def test_fidelity_csv_written(self, tmp_path):
        """write_state 能正确写 json（不依赖 GPU / 模型）。"""
        import torch
        from braingb_lane.eval_fidelity import write_state

        state_path = tmp_path / "state.json"
        write_state(state_path, {
            "run_id": "run-04",
            "status": "fidelity_done",
            "gate1_pass": True,
            "mean_fid_pos": 0.12,
            "mean_fid_neg": 0.35,
        })
        assert state_path.exists(), "state.json 未写出"
        import json
        with open(state_path) as f:
            state = json.load(f)
        assert state["gate1_pass"] is True
        assert state["run_id"] == "run-04"


# ---------------------------------------------------------------------------
# 4. train_braingb: build_braingb_args 超参校验
# ---------------------------------------------------------------------------

class TestTrainBrainGB:
    """
    验证 build_braingb_args 返回值与官方超参一致（不跑任何训练）。
    """

    def test_official_hyperparams(self):
        """官方超参（researcher 2026-06-24 核实）不被覆盖。"""
        from braingb_lane.train_braingb import build_braingb_args

        args = build_braingb_args()
        assert args.lr == 1e-4, f"lr 期望 1e-4，得 {args.lr}"
        assert args.weight_decay == 1e-4, f"weight_decay 期望 1e-4，得 {args.weight_decay}"
        assert args.epochs == 100, f"epochs 期望 100，得 {args.epochs}"
        assert args.hidden_dim == 360, f"hidden_dim 期望 360，得 {args.hidden_dim}"
        assert args.n_GNN_layers == 2, f"n_GNN_layers 期望 2，得 {args.n_GNN_layers}"
        assert args.dropout == 0.5, f"dropout 期望 0.5，得 {args.dropout}"
        assert args.train_batch_size == 16, f"train_batch_size 期望 16，得 {args.train_batch_size}"
        assert args.k_fold_splits == 5, f"k_fold_splits 期望 5，得 {args.k_fold_splits}"
        assert args.pooling == "concat", f"pooling 期望 concat，得 {args.pooling}"
        assert args.node_features == "adj", f"node_features 期望 adj，得 {args.node_features}"
        assert args.gcn_mp_type == "weighted_sum", \
            f"gcn_mp_type 期望 weighted_sum，得 {args.gcn_mp_type}"
        assert args.gat_mp_type == "attention_weighted", \
            f"gat_mp_type 期望 attention_weighted，得 {args.gat_mp_type}"
        assert args.num_heads == 2, f"num_heads 期望 2，得 {args.num_heads}"

    def test_write_state_atomic(self, tmp_path):
        """write_state 原子写不留 .tmp 残留。"""
        from braingb_lane.train_braingb import write_state

        state_path = tmp_path / "state.json"
        write_state(state_path, {"status": "running", "epoch": 5, "acc": 0.65})

        assert state_path.exists(), "state.json 未生成"
        tmp_path_check = state_path.with_suffix(".tmp")
        assert not tmp_path_check.exists(), ".tmp 残留（原子写失败）"

        import json
        with open(state_path) as f:
            s = json.load(f)
        assert s["epoch"] == 5
        assert s["acc"] == pytest.approx(0.65)
