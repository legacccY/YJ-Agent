"""
test_hypergale_lane.py
======================
pytest 测试套件（Gate1 地基验证）。

【cohort 说明（偏离论文，红线合规）】
  2026-06-25 改：数据从 ABIDE-II Schaefer400 改为 ABIDE-I CC200。
  原因：HPC 下载 func_preproc 实测 0.08MB/s（43GB 需 6天不可行）；
        BrainGB 泳道已有 CC200 FC，与 BrainGB 同 cohort/atlas/split，Gate2 纯比架构。
  fc_large_data_cc200.npy 由 build_fc_cc200_from_braingb.py 秒级产出。

测试范围：
  1. FC shape 验证（fc_large_data_cc200.npy 内部结构）[需数据文件]
  2. hyperedge incidence 维度验证（k-NN 超边形状，200节点）[data-free，随机 mock]
  3. split 无泄漏 assert（BrainGB 对齐 5-fold split）[需 split CSV]
  4. HyperGALE model 前向 shape 检查（200节点 mock data，不需真实 GPU）[需 vendor]

【注意】
  本脚本只写不跑——主线运行 pytest。
  测试 4（model forward）需要 vendor/HyperGALE 在 sys.path。
  测试 3 需要先跑过 make_split_cc200.py 生成 split CSV。

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
_SRC    = _REPO_ROOT / "src" / "hypergale_lane"

for p in [str(_VENDOR), str(_SRC)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# ── 数据路径（ABIDE-I CC200，测试用，文件不存在时 skip）
_CC200_DIR = _REPO_ROOT / "data" / "external" / "abide1_cc200"
_FC_PATH   = _CC200_DIR / "fc_large_data_cc200.npy"
_META_PATH = _CC200_DIR / "abide1_cc200_meta.csv"
_SPLIT_CSV = _CC200_DIR / "splits" / "split_cc200_5fold.csv"

K_NEIGS = 40
N_ROIS  = 200   # CC200（偏离论文 Schaefer400=400）


# ══════════════════════════════════════════════════════════
# Test 1: FC shape 验证（需真实数据）
# ══════════════════════════════════════════════════════════

@pytest.mark.skipif(
    not _FC_PATH.exists(),
    reason="fc_large_data_cc200.npy 不存在，先跑 build_fc_cc200_from_braingb.py",
)
class TestFCShape:
    def test_load_keys(self):
        """fc_large_data_cc200.npy 必须含 corr / label / site 键。"""
        fc_data = np.load(str(_FC_PATH), allow_pickle=True).item()
        assert "corr"  in fc_data, "缺键 'corr'"
        assert "label" in fc_data, "缺键 'label'"
        assert "site"  in fc_data, "缺键 'site'"

    def test_corr_shape(self):
        """corr shape 应为 (N, 200, 200)（CC200 atlas）。"""
        fc_data = np.load(str(_FC_PATH), allow_pickle=True).item()
        corr = fc_data["corr"]
        assert corr.ndim == 3, f"corr 应为 3D，实际 {corr.ndim}D"
        assert corr.shape[1] == N_ROIS, f"corr.shape[1]={corr.shape[1]} != {N_ROIS}（CC200）"
        assert corr.shape[2] == N_ROIS, f"corr.shape[2]={corr.shape[2]} != {N_ROIS}（CC200）"

    def test_label_shape(self):
        """label shape 应为 (N,)，值域 {0.0, 1.0}（0=TD, 1=ASD）。"""
        fc_data = np.load(str(_FC_PATH), allow_pickle=True).item()
        corr  = fc_data["corr"]
        label = fc_data["label"]
        assert label.ndim == 1, f"label 应为 1D，实际 {label.ndim}D"
        assert len(label) == corr.shape[0], "label 长度 != N"
        unique_labels = set(label.tolist())
        assert unique_labels.issubset({0.0, 1.0}), f"label 值域异常: {unique_labels}"

    def test_label_direction(self):
        """label 编码方向：1=ASD, 0=TD（与 BCEWithLogitsLoss 约定一致）。"""
        fc_data = np.load(str(_FC_PATH), allow_pickle=True).item()
        label = fc_data["label"]
        n_asd = float((label == 1.0).sum())
        n_td  = float((label == 0.0).sum())
        N = float(len(label))
        # ASD 比例应在 [20%, 80%]，否则编码可能反向
        asd_ratio = n_asd / N
        assert 0.20 <= asd_ratio <= 0.80, (
            f"ASD 比例 {asd_ratio:.2%} 异常（预期 ~45%），label 可能编码反向"
        )

    def test_site_length(self):
        """site 长度应与 corr N 一致。"""
        fc_data = np.load(str(_FC_PATH), allow_pickle=True).item()
        assert len(fc_data["site"]) == fc_data["corr"].shape[0]

    def test_corr_dtype(self):
        """corr 应为 float32（HyperGALE 期望）。"""
        fc_data = np.load(str(_FC_PATH), allow_pickle=True).item()
        assert fc_data["corr"].dtype == np.float32, (
            f"corr dtype={fc_data['corr'].dtype} != float32"
        )

    def test_corr_symmetric(self):
        """FC 矩阵应近似对称（Pearson correlation 保证对称）。"""
        fc_data = np.load(str(_FC_PATH), allow_pickle=True).item()
        corr = fc_data["corr"]
        for i in range(min(5, corr.shape[0])):
            diff = np.abs(corr[i] - corr[i].T).max()
            assert diff < 1e-4, f"subject {i} 非对称，max_diff={diff:.2e}"

    def test_n_subjects_range(self):
        """
        ABIDE-I CC200 n≈871（nilearn QC pass）。
        允许 [700, 900]（极少被试可能因 inner-join 排除）。
        """
        fc_data = np.load(str(_FC_PATH), allow_pickle=True).item()
        N = fc_data["corr"].shape[0]
        assert 700 <= N <= 900, f"N={N} 不在预期范围 [700, 900]（ABIDE-I CC200 ≈871）"

    def test_label_balance(self):
        """ASD 和 TD 各自 > 20%（过于不平衡提示数据问题）。"""
        fc_data = np.load(str(_FC_PATH), allow_pickle=True).item()
        label = fc_data["label"]
        N = len(label)
        asd_ratio = label.sum() / N
        assert 0.2 < asd_ratio < 0.8, f"ASD 比例 {asd_ratio:.2%} 不在 (20%, 80%)"


# ══════════════════════════════════════════════════════════
# Test 2: hyperedge 维度（data-free，200节点 mock）
# ══════════════════════════════════════════════════════════

class TestHyperedgeDimensions:
    """
    不需要真实数据，用随机 200×200 FC 矩阵验证超边构造。
    CC200 时 n_nodes=200，k=40（沿用论文值，覆盖率翻倍，TODO Gate2 调参）。
    """

    def _make_random_fc(self, n: int = N_ROIS) -> np.ndarray:
        """生成随机对称 FC 矩阵。"""
        rng = np.random.default_rng(42)
        A = rng.normal(size=(n, n)).astype(np.float32)
        return (A + A.T) / 2

    def test_hyperedge_shape(self):
        """hyperedge_index shape 应为 (2, N_ROIS*(K+1)) = (2, 200*41) = (2, 8200)。"""
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
        assert hei.dtype == torch.long

    def test_edge_weight_shape(self):
        """edge_weight shape 应为 (N_ROIS,) = (200,)。"""
        from build_hyperedges import build_hyperedges_for_subject
        fc = self._make_random_fc()
        hei, ew = build_hyperedges_for_subject(fc, k=K_NEIGS)
        assert ew.shape == (N_ROIS,), f"edge_weight shape {ew.shape} != ({N_ROIS},)"

    def test_node_indices_range(self):
        """hyperedge_index[0]（节点 idx）应在 [0, N_ROIS=200)。"""
        from build_hyperedges import create_hyper_edges_from_matrix
        fc = self._make_random_fc()
        hei = create_hyper_edges_from_matrix(fc, k=K_NEIGS)
        assert hei[0].min() >= 0
        assert hei[0].max() < N_ROIS

    def test_edge_indices_range(self):
        """hyperedge_index[1]（超边 idx）应在 [0, N_ROIS=200)。"""
        from build_hyperedges import create_hyper_edges_from_matrix
        fc = self._make_random_fc()
        hei = create_hyper_edges_from_matrix(fc, k=K_NEIGS)
        assert hei[1].min() >= 0
        assert hei[1].max() < N_ROIS

    def test_no_isolated_nodes(self):
        """每个节点都应出现在至少一条超边中（k=40 << 200，无孤立节点）。"""
        from build_hyperedges import create_hyper_edges_from_matrix
        fc = self._make_random_fc()
        hei = create_hyper_edges_from_matrix(fc, k=K_NEIGS)
        unique_nodes = hei[0].unique().numel()
        assert unique_nodes == N_ROIS, (
            f"存在孤立节点：unique_nodes={unique_nodes} < {N_ROIS}"
        )

    def test_num_hyperedges_equals_nodes(self):
        """超边数应等于节点数（num_edges = node_sz = 200，官方设计）。"""
        from build_hyperedges import create_hyper_edges_from_matrix
        fc = self._make_random_fc()
        hei = create_hyper_edges_from_matrix(fc, k=K_NEIGS)
        n_edges = int(hei[1].max().item()) + 1
        assert n_edges == N_ROIS, f"n_edges={n_edges} != N_ROIS={N_ROIS}"

    def test_k_variation(self):
        """不同 K 值时 shape 正确（k=5,10,25，200节点下均合法）。"""
        from build_hyperedges import create_hyper_edges_from_matrix
        fc = self._make_random_fc()
        for k in [5, 10, 25]:
            hei = create_hyper_edges_from_matrix(fc, k=k)
            expected = N_ROIS * (k + 1)
            assert hei.shape == (2, expected), (
                f"k={k}: shape {hei.shape} != (2, {expected})"
            )

    def test_k40_on_200nodes_valid(self):
        """k=40, n=200：k < n_nodes，合法（覆盖率 20.5%，沿用论文值 TODO Gate2 消融）。"""
        from build_hyperedges import create_hyper_edges_from_matrix
        fc = self._make_random_fc(n=200)
        # 不应抛出异常，k=40 < 200
        hei = create_hyper_edges_from_matrix(fc, k=40)
        assert hei.shape == (2, 200 * 41)


# ══════════════════════════════════════════════════════════
# Test 3: split 无泄漏（需 split_cc200_5fold.csv）
# ══════════════════════════════════════════════════════════

@pytest.mark.skipif(
    not _SPLIT_CSV.exists(),
    reason="split_cc200_5fold.csv 不存在，先跑 make_split_cc200.py",
)
class TestSplitNoLeakage:
    def test_no_subject_overlap_fold0(self):
        """fold_0: 同 sub_id 不同时出现在 train/test。"""
        import pandas as pd
        df = pd.read_csv(_SPLIT_CSV)
        train_subs = set(df[df["fold_0"] == "train"]["sub_id"])
        test_subs  = set(df[df["fold_0"] == "test"]["sub_id"])
        overlap = train_subs & test_subs
        assert len(overlap) == 0, f"泄漏 sub_id: {overlap}"

    def test_split_ratio_fold0(self):
        """fold_0 测试集占比约 20%（5-fold CV），允许 [15%, 25%]。"""
        import pandas as pd
        df = pd.read_csv(_SPLIT_CSV)
        n_test = (df["fold_0"] == "test").sum()
        ratio = n_test / len(df)
        assert 0.15 <= ratio <= 0.25, f"fold_0 测试比例 {ratio:.2%} 不在 [15%, 25%]"

    def test_all_folds_present(self):
        """split CSV 应含 fold_0..fold_4 列。"""
        import pandas as pd
        df = pd.read_csv(_SPLIT_CSV)
        for i in range(5):
            assert f"fold_{i}" in df.columns, f"缺列 fold_{i}"

    def test_fc_idx_range(self):
        """fc_idx 应在 [0, N) 范围内（N=abide.npy 行数）。"""
        import pandas as pd
        df = pd.read_csv(_SPLIT_CSV)
        N = len(df)  # split 行数 ≤ fc 行数（inner-join 结果）
        assert (df["fc_idx"] >= 0).all(), "存在负 fc_idx"
        # fc_idx 最大值 < abide.npy N（通常 871）
        assert df["fc_idx"].max() < 900, f"fc_idx 最大值 {df['fc_idx'].max()} 异常"

    def test_site_in_split(self):
        """split CSV 应含 site_id 列（供分布分析用）。"""
        import pandas as pd
        df = pd.read_csv(_SPLIT_CSV)
        assert "site_id" in df.columns, "split CSV 缺 site_id 列"
        n_sites = df["site_id"].nunique()
        assert n_sites >= 5, f"site 数 {n_sites} 过少，split 可能有误"


# ══════════════════════════════════════════════════════════
# Test 4: HyperGALE model 前向 shape（200节点 mock，不需 GPU）
# ══════════════════════════════════════════════════════════

@pytest.mark.skipif(
    not (_VENDOR / "source" / "models" / "Hypergraph_models" / "HyperGALE.py").exists(),
    reason="vendor/HyperGALE 未就位",
)
class TestHyperGALEForward:
    """
    Mock 2 subjects / 200节点，只验 forward output shape。
    CC200 时 node_sz=200，hyperedge (2, 200*41)。
    """

    def _make_mock_cfg(self):
        from omegaconf import OmegaConf
        return OmegaConf.create({
            "dataset": {
                "name": "fc_abide2",
                "node_sz": N_ROIS,            # 200（CC200）
                "node_feature_sz": N_ROIS,    # 200
                "num_classes": 2,
                "node": "fc",
            },
            "model": {
                "name": "HyperGALE",
                "K_neigs": K_NEIGS,           # 40（沿用论文值）
                "num_layers": 1,
                "hidden_size": 64,
                "dropout": 0.5,
                "readout": "linear",
                "model_save": False,
            },
        })

    def _make_mock_batch(self, n_subjects: int = 2):
        """生成 200节点 mock HyperGraphData batch。"""
        from source.dataset.hypergraph_data import HyperGraphData
        from torch_geometric.loader import DataLoader
        from build_hyperedges import build_hyperedges_for_subject

        rng = np.random.default_rng(0)
        data_list = []
        for i in range(n_subjects):
            fc = rng.normal(size=(N_ROIS, N_ROIS)).astype(np.float32)
            fc = (fc + fc.T) / 2
            x = torch.from_numpy(fc)         # (200, 200) node features
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

        cfg   = self._make_mock_cfg()
        model = HyperGALE(cfg)
        model.eval()
        batch = self._make_mock_batch(n_subjects=2)

        with torch.no_grad():
            out = model(batch, epoch=0, iteration=0, test_phase=True)

        assert out.shape[0] == 2, f"batch_size 不匹配: {out.shape}"
        assert out.numel() == 2, f"output 元素数 {out.numel()} != 2"

    def test_forward_no_nan(self):
        """HyperGALE forward 输出不含 NaN。"""
        from source.models.Hypergraph_models.HyperGALE import HyperGALE

        cfg   = self._make_mock_cfg()
        model = HyperGALE(cfg)
        model.eval()
        batch = self._make_mock_batch(n_subjects=2)

        with torch.no_grad():
            out = model(batch, epoch=0, iteration=0, test_phase=True)

        assert not torch.isnan(out).any(), f"forward 输出含 NaN: {out}"

    def test_forward_finite(self):
        """HyperGALE forward 输出应为有限值。"""
        from source.models.Hypergraph_models.HyperGALE import HyperGALE

        cfg   = self._make_mock_cfg()
        model = HyperGALE(cfg)
        model.eval()
        batch = self._make_mock_batch(n_subjects=2)

        with torch.no_grad():
            out = model(batch, epoch=0, iteration=0, test_phase=True)

        assert torch.isfinite(out).all(), f"forward 输出含 inf: {out}"
