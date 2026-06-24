"""
test_hypergale_lane.py
======================
pytest 测试套件（Gate1 地基验证）。

测试范围：
  1. FC shape 验证（fc_large_data.npy 内部结构）
  2. hyperedge incidence 维度验证（k-NN 超边形状）
  3. split 无泄漏 assert（patient-level split）
  4. HyperGALE model 前向 shape 检查（mock data，不需真实 GPU）

【注意】
  本脚本只写不跑——主线运行 pytest。
  测试 4（model forward）需要 vendor/HyperGALE 在 sys.path。
  测试 3 需要先跑过 make_split.py 生成 split CSV。

运行命令（主线执行）：
  cd D:/YJ-Agent/project/meeting/HyperFidBench
  python -m pytest src/hypergale_lane/tests/test_hypergale_lane.py -v
"""

import sys
from pathlib import Path

import numpy as np
import pytest
import torch

# ── path setup
_REPO_ROOT = Path(__file__).resolve().parents[3]  # HyperFidBench/
_VENDOR = _REPO_ROOT / "vendor" / "HyperGALE"
_SRC = _REPO_ROOT / "src" / "hypergale_lane"

for p in [str(_VENDOR), str(_SRC)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# ── 数据路径（测试用，文件不存在时 skip）
_FC_PATH = _REPO_ROOT / "data" / "external" / "abide2" / "fc_large_data.npy"
_META_PATH = _REPO_ROOT / "data" / "external" / "abide2" / "abide2_meta.csv"
_SPLIT_CSV = _REPO_ROOT / "data" / "external" / "abide2" / "splits" / "split_90_10.csv"

K_NEIGS = 40
N_ROIS = 400


# ══════════════════════════════════════════════════════════
# Test 1: FC shape 验证
# ══════════════════════════════════════════════════════════

@pytest.mark.skipif(not _FC_PATH.exists(), reason="fc_large_data.npy 不存在，先跑 build_fc_abide2.py")
class TestFCShape:
    def test_load_keys(self):
        """fc_large_data.npy 必须含 corr / label / site 键。"""
        fc_data = np.load(str(_FC_PATH), allow_pickle=True).item()
        assert "corr" in fc_data, "缺键 'corr'"
        assert "label" in fc_data, "缺键 'label'"
        assert "site" in fc_data, "缺键 'site'"

    def test_corr_shape(self):
        """corr shape 应为 (N, 400, 400)。"""
        fc_data = np.load(str(_FC_PATH), allow_pickle=True).item()
        corr = fc_data["corr"]
        assert corr.ndim == 3, f"corr 应为 3D，实际 {corr.ndim}D"
        assert corr.shape[1] == N_ROIS, f"corr.shape[1]={corr.shape[1]} != {N_ROIS}"
        assert corr.shape[2] == N_ROIS, f"corr.shape[2]={corr.shape[2]} != {N_ROIS}"

    def test_label_shape(self):
        """label shape 应为 (N,)，值域 {0, 1}。"""
        fc_data = np.load(str(_FC_PATH), allow_pickle=True).item()
        corr = fc_data["corr"]
        label = fc_data["label"]
        assert label.ndim == 1, f"label 应为 1D，实际 {label.ndim}D"
        assert len(label) == corr.shape[0], "label 长度 != N"
        unique_labels = set(label.tolist())
        assert unique_labels.issubset({0.0, 1.0}), f"label 值域异常: {unique_labels}"

    def test_site_length(self):
        """site 长度应与 corr N 一致。"""
        fc_data = np.load(str(_FC_PATH), allow_pickle=True).item()
        corr = fc_data["corr"]
        site = fc_data["site"]
        assert len(site) == corr.shape[0], f"site 长度 {len(site)} != N={corr.shape[0]}"

    def test_corr_dtype(self):
        """corr 应为 float32（HyperGALE 期望）。"""
        fc_data = np.load(str(_FC_PATH), allow_pickle=True).item()
        corr = fc_data["corr"]
        assert corr.dtype == np.float32, f"corr dtype={corr.dtype} != float32"

    def test_corr_symmetric(self):
        """FC 矩阵应近似对称（Ledoit-Wolf correlation 保证对称）。"""
        fc_data = np.load(str(_FC_PATH), allow_pickle=True).item()
        corr = fc_data["corr"]
        # 检查前 5 个 subject
        for i in range(min(5, corr.shape[0])):
            diff = np.abs(corr[i] - corr[i].T).max()
            assert diff < 1e-5, f"subject {i} 非对称，max_diff={diff:.2e}"

    def test_label_balance(self):
        """ASD/TD 各自 > 20%（过于不平衡提示数据问题）。"""
        fc_data = np.load(str(_FC_PATH), allow_pickle=True).item()
        label = fc_data["label"]
        N = len(label)
        asd_ratio = label.sum() / N
        assert asd_ratio > 0.2, f"ASD 比例 {asd_ratio:.2%} 过低，数据可能有误"
        assert asd_ratio < 0.8, f"ASD 比例 {asd_ratio:.2%} 过高，数据可能有误"

    def test_n_subjects_range(self):
        """ABIDE-II n≈812，允许区间 [700, 900]。"""
        fc_data = np.load(str(_FC_PATH), allow_pickle=True).item()
        N = fc_data["corr"].shape[0]
        assert 700 <= N <= 900, f"N={N} 不在预期范围 [700, 900]（论文报告 812）"


# ══════════════════════════════════════════════════════════
# Test 2: hyperedge incidence 维度
# ══════════════════════════════════════════════════════════

class TestHyperedgeDimensions:
    """
    不需要真实数据，用随机 FC 矩阵验证超边构造函数。
    """

    def _make_random_fc(self, n: int = N_ROIS) -> np.ndarray:
        """生成随机对称 FC 矩阵（不含 NaN）。"""
        rng = np.random.default_rng(42)
        A = rng.normal(size=(n, n)).astype(np.float32)
        return (A + A.T) / 2  # 对称

    def test_hyperedge_shape(self):
        """hyperedge_index shape 应为 (2, N_ROIS * (K+1))。"""
        from build_hyperedges import create_hyper_edges_from_matrix
        fc = self._make_random_fc()
        hei = create_hyper_edges_from_matrix(fc, k=K_NEIGS)
        expected_cols = N_ROIS * (K_NEIGS + 1)
        assert hei.shape == (2, expected_cols), (
            f"hyperedge_index shape {hei.shape} != (2, {expected_cols})"
        )

    def test_hyperedge_dtype(self):
        """hyperedge_index 应为 LongTensor。"""
        from build_hyperedges import create_hyper_edges_from_matrix
        fc = self._make_random_fc()
        hei = create_hyper_edges_from_matrix(fc, k=K_NEIGS)
        assert hei.dtype == torch.long, f"dtype={hei.dtype} != torch.long"

    def test_edge_weight_shape(self):
        """edge_weight shape 应为 (N_ROIS,)。"""
        from build_hyperedges import build_hyperedges_for_subject
        fc = self._make_random_fc()
        hei, ew = build_hyperedges_for_subject(fc, k=K_NEIGS)
        assert ew.shape == (N_ROIS,), f"edge_weight shape {ew.shape} != ({N_ROIS},)"

    def test_node_indices_range(self):
        """hyperedge_index[0]（节点 idx）应在 [0, N_ROIS)。"""
        from build_hyperedges import create_hyper_edges_from_matrix
        fc = self._make_random_fc()
        hei = create_hyper_edges_from_matrix(fc, k=K_NEIGS)
        assert hei[0].min() >= 0
        assert hei[0].max() < N_ROIS, f"节点 idx 超界: max={hei[0].max()}"

    def test_edge_indices_range(self):
        """hyperedge_index[1]（超边 idx）应在 [0, N_ROIS)。"""
        from build_hyperedges import create_hyper_edges_from_matrix
        fc = self._make_random_fc()
        hei = create_hyper_edges_from_matrix(fc, k=K_NEIGS)
        assert hei[1].min() >= 0
        assert hei[1].max() < N_ROIS, f"超边 idx 超界: max={hei[1].max()}"

    def test_no_isolated_nodes(self):
        """每个节点都应出现在至少一条超边中。"""
        from build_hyperedges import create_hyper_edges_from_matrix
        fc = self._make_random_fc()
        hei = create_hyper_edges_from_matrix(fc, k=K_NEIGS)
        unique_nodes = hei[0].unique().numel()
        assert unique_nodes == N_ROIS, (
            f"存在孤立节点：unique_nodes={unique_nodes} < {N_ROIS}"
        )

    def test_num_hyperedges_equals_nodes(self):
        """超边数应等于节点数（num_edges = node_sz = 400，官方设计）。"""
        from build_hyperedges import create_hyper_edges_from_matrix
        fc = self._make_random_fc()
        hei = create_hyper_edges_from_matrix(fc, k=K_NEIGS)
        n_edges = int(hei[1].max().item()) + 1
        assert n_edges == N_ROIS, f"n_edges={n_edges} != N_ROIS={N_ROIS}"

    def test_k_variation(self):
        """不同 K 值时 shape 正确（k=5,10,25 验）。"""
        from build_hyperedges import create_hyper_edges_from_matrix
        fc = self._make_random_fc()
        for k in [5, 10, 25]:
            hei = create_hyper_edges_from_matrix(fc, k=k)
            expected = N_ROIS * (k + 1)
            assert hei.shape == (2, expected), (
                f"k={k}: shape {hei.shape} != (2, {expected})"
            )


# ══════════════════════════════════════════════════════════
# Test 3: split 无泄漏
# ══════════════════════════════════════════════════════════

@pytest.mark.skipif(
    not _SPLIT_CSV.exists(),
    reason="split_90_10.csv 不存在，先跑 make_split.py",
)
class TestSplitNoLeakage:
    def test_no_subject_overlap(self):
        """同 SUB_ID 不同时出现在 train 和 test。"""
        import pandas as pd
        df = pd.read_csv(_SPLIT_CSV)
        train_subs = set(df[df["split"] == "train"]["sub_id"])
        test_subs = set(df[df["split"] == "test"]["sub_id"])
        overlap = train_subs & test_subs
        assert len(overlap) == 0, f"泄漏 SUB_ID: {overlap}"

    def test_split_ratio(self):
        """测试集占比应约为 10%（允许 ±5% 因 stratify 近似）。"""
        import pandas as pd
        df = pd.read_csv(_SPLIT_CSV)
        n_test = (df["split"] == "test").sum()
        ratio = n_test / len(df)
        assert 0.05 <= ratio <= 0.15, f"测试集比例 {ratio:.2%} 不在 [5%, 15%]"

    def test_all_subjects_assigned(self):
        """所有 subject 都有 split 标签。"""
        import pandas as pd
        df = pd.read_csv(_SPLIT_CSV)
        assert (df["split"] == "").sum() == 0, "存在未分配 split 的 subject"
        assert df["split"].isin(["train", "test"]).all(), "split 值异常"

    def test_site_preserved_in_test(self):
        """测试集应覆盖多个 site（stratified split 保证）。"""
        import pandas as pd
        df = pd.read_csv(_SPLIT_CSV)
        test_sites = df[df["split"] == "test"]["site_id"].nunique()
        assert test_sites >= 3, f"测试集 site 数 {test_sites} < 3，stratify 可能失效"


# ══════════════════════════════════════════════════════════
# Test 4: HyperGALE model 前向 shape（mock data）
# ══════════════════════════════════════════════════════════

@pytest.mark.skipif(
    not (_VENDOR / "source" / "models" / "Hypergraph_models" / "HyperGALE.py").exists(),
    reason="vendor/HyperGALE 未就位",
)
class TestHyperGALEForward:
    """
    Mock 2 subjects，只验 forward output shape。
    不需要 GPU（用 CPU）。
    """

    def _make_mock_cfg(self):
        from omegaconf import OmegaConf
        return OmegaConf.create({
            "dataset": {
                "name": "fc_abide2",
                "node_sz": N_ROIS,
                "node_feature_sz": N_ROIS,
                "num_classes": 2,
                "node": "fc",
            },
            "model": {
                "name": "HyperGALE",
                "K_neigs": K_NEIGS,
                "num_layers": 1,
                "hidden_size": 64,
                "dropout": 0.5,
                "readout": "linear",
                "model_save": False,
            },
        })

    def _make_mock_batch(self, n_subjects: int = 2):
        """生成 mock HyperGraphData batch。"""
        from source.dataset.hypergraph_data import HyperGraphData
        from torch_geometric.loader import DataLoader
        from build_hyperedges import build_hyperedges_for_subject

        rng = np.random.default_rng(0)
        data_list = []
        for i in range(n_subjects):
            fc = rng.normal(size=(N_ROIS, N_ROIS)).astype(np.float32)
            fc = (fc + fc.T) / 2
            x = torch.from_numpy(fc)  # (400, 400) node features
            hei, ew = build_hyperedges_for_subject(fc, k=K_NEIGS)
            y = torch.tensor(float(i % 2))
            data = HyperGraphData(x=x, edge_index=hei, edge_weight=ew, y=y)
            data_list.append(data)

        loader = DataLoader(data_list, batch_size=n_subjects, shuffle=False)
        batch = next(iter(loader))
        return batch

    def test_forward_output_shape(self):
        """HyperGALE forward 输出 shape 应为 (batch_size,) 或 (batch_size, 1)。"""
        from source.models.Hypergraph_models.HyperGALE import HyperGALE

        cfg = self._make_mock_cfg()
        model = HyperGALE(cfg)
        model.eval()

        batch = self._make_mock_batch(n_subjects=2)

        with torch.no_grad():
            out = model(batch, epoch=0, iteration=0, test_phase=True)

        # output shape: (2,) or (2, 1)
        assert out.shape[0] == 2, f"batch_size 不匹配: {out.shape}"
        assert out.numel() == 2, f"output 元素数 {out.numel()} != 2"

    def test_forward_no_nan(self):
        """HyperGALE forward 输出不含 NaN。"""
        from source.models.Hypergraph_models.HyperGALE import HyperGALE

        cfg = self._make_mock_cfg()
        model = HyperGALE(cfg)
        model.eval()

        batch = self._make_mock_batch(n_subjects=2)

        with torch.no_grad():
            out = model(batch, epoch=0, iteration=0, test_phase=True)

        assert not torch.isnan(out).any(), f"forward 输出含 NaN: {out}"

    def test_forward_finite(self):
        """HyperGALE forward 输出应为有限值。"""
        from source.models.Hypergraph_models.HyperGALE import HyperGALE

        cfg = self._make_mock_cfg()
        model = HyperGALE(cfg)
        model.eval()

        batch = self._make_mock_batch(n_subjects=2)

        with torch.no_grad():
            out = model(batch, epoch=0, iteration=0, test_phase=True)

        assert torch.isfinite(out).all(), f"forward 输出含 inf: {out}"
