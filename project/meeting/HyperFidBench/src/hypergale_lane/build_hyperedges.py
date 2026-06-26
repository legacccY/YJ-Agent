"""
build_hyperedges.py
===================
k-NN 超边构造，照搬 vendor/HyperGALE/source/dataset/construct_hyperaph.py。

【官方实现说明】
  HyperGALE 的超边构造在 create_hyper_edges_from_matrix() 中：
  - 每个节点 i 找其 top-(K+1) 最相关 ROI（含自身），形成一条超边。
  - 超边 ID = 节点 ID（num_edges = num_nodes = 400）。
  - 输出 hyperedge_index: shape (2, N * (K+1))
      [0] = 节点 idx（哪些节点属于该超边）
      [1] = 超边 idx（第几条超边）
  - edge_weight: shape (num_edges,) = ones（后被 learned_he_weights 替换）

【本脚本职责】
  离线验证超边维度正确性 + 生成调试用可视化统计。
  实际训练时，超边在 create_hypergraph_data() 里 per-sample 动态构建，
  不需要预先离线保存（vendor 就是这样设计的）。

  本脚本主要用于：
  1. 验证 fc_large_data.npy 加载后超边维度是否符合 HyperGALE 期望。
  2. 独立检查 k-NN 超边统计（连通度、孤立节点等）。
  3. pytest test_hypergale_lane.py 的被调用模块。

K_neigs = 40（官方最优值，超参禁臆想，已核 source/conf/model/hypergale.yaml）
"""

from pathlib import Path
from typing import Tuple, Optional
import logging

import numpy as np
import torch

logger = logging.getLogger(__name__)

# 官方超参（source/conf/model/hypergale.yaml）
K_NEIGS_DEFAULT = 40
N_ROIS = 400


def create_hyper_edges_from_matrix(
    matrix: np.ndarray,
    k: int = K_NEIGS_DEFAULT,
) -> torch.Tensor:
    """
    与 vendor/source/dataset/construct_hyperaph.py:create_hyper_edges_from_matrix
    完全相同的实现（复现零偏离）。

    参数
    ----
    matrix : (n_nodes, n_nodes) FC 矩阵（单个 subject）
    k      : K_neigs=40（官方默认）

    返回
    ----
    hyperedge_index : LongTensor shape (2, n_nodes * (k+1))
      [0] = 节点 idx
      [1] = 超边 idx（= 中心节点 idx）
    """
    n_nodes = matrix.shape[0]
    hyper_edge_index = torch.zeros(
        [2, n_nodes * (k + 1)], dtype=torch.long
    )
    for node in range(n_nodes):
        # top-(k+1) 最大绝对相关（含自身）
        connected_nodes = np.argpartition(matrix[node, :], -k - 1)[-k - 1:]
        for idx, connected_node in enumerate(connected_nodes):
            hyper_edge_index[0, node * (k + 1) + idx] = connected_node
            hyper_edge_index[1, node * (k + 1) + idx] = node
    return hyper_edge_index


def build_hyperedges_for_subject(
    fc_matrix: np.ndarray,
    k: int = K_NEIGS_DEFAULT,
) -> Tuple[torch.Tensor, torch.Tensor]:
    """
    单 subject FC 矩阵 → (hyperedge_index, edge_weight)。

    返回
    ----
    hyperedge_index : (2, n_nodes*(k+1)) LongTensor
    edge_weight     : (n_edges,) FloatTensor，全 1（与官方一致）
    """
    hyper_edge_index = create_hyper_edges_from_matrix(fc_matrix, k=k)
    n_edges = int(hyper_edge_index[1].max().item()) + 1  # = n_nodes = 400
    edge_weight = torch.ones(n_edges, dtype=torch.float32)
    return hyper_edge_index, edge_weight


def validate_hyperedge_dimensions(
    fc_path: Path,
    k: int = K_NEIGS_DEFAULT,
    n_sample: int = 3,
) -> None:
    """
    验证 fc_large_data.npy 加载后超边维度是否符合 HyperGALE 期望。
    仅打印统计，不返回值（供主线/pytest 用）。

    期望维度：
      hyperedge_index : (2, 400*(40+1)) = (2, 16400)
      edge_weight     : (400,)
    """
    fc_data = np.load(str(fc_path), allow_pickle=True).item()
    corr = fc_data["corr"]   # (N, 400, 400)
    labels = fc_data["label"]
    site = fc_data["site"]

    logger.info(
        "fc_large_data 统计: N=%d, corr_shape=%s, ASD=%d, TD=%d",
        corr.shape[0], corr.shape, int(labels.sum()), int((labels == 0).sum()),
    )

    expected_he_cols = N_ROIS * (k + 1)
    for i in range(min(n_sample, corr.shape[0])):
        hei, ew = build_hyperedges_for_subject(corr[i], k=k)
        assert hei.shape == (2, expected_he_cols), (
            f"subject {i}: hyperedge_index shape {hei.shape} != (2, {expected_he_cols})"
        )
        assert ew.shape == (N_ROIS,), (
            f"subject {i}: edge_weight shape {ew.shape} != ({N_ROIS},)"
        )
        # 检查孤立节点
        unique_nodes = hei[0].unique().numel()
        unique_edges = hei[1].unique().numel()
        logger.info(
            "subject %d: hei=%s, ew=%s, unique_nodes=%d, unique_edges=%d",
            i, tuple(hei.shape), tuple(ew.shape), unique_nodes, unique_edges,
        )

    logger.info("维度验证 PASS: hyperedge_index=(2,%d), edge_weight=(%d,)",
                expected_he_cols, N_ROIS)


def parse_args():
    import argparse
    p = argparse.ArgumentParser(description="验证 HyperGALE 超边构造维度")
    _root = Path(__file__).resolve().parents[2]
    p.add_argument(
        "--fc-path",
        type=Path,
        default=_root / "data" / "external" / "abide1_cc200" / "fc_large_data_cc200.npy",
        help="fc_large_data_cc200.npy 路径（ABIDE-I CC200，build_fc_cc200_from_braingb.py 产出）",
    )
    p.add_argument("--k", type=int, default=K_NEIGS_DEFAULT, help="K_neigs（默认40）")
    p.add_argument("--n-sample", type=int, default=3, help="抽查 subject 数")
    return p.parse_args()


if __name__ == "__main__":
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    args = parse_args()
    if not args.fc_path.exists():
        print(f"fc_large_data_cc200.npy 不存在: {args.fc_path}")
        print("请先运行 build_fc_cc200_from_braingb.py")
        sys.exit(1)
    validate_hyperedge_dimensions(args.fc_path, k=args.k, n_sample=args.n_sample)
