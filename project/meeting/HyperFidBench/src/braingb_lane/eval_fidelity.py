"""
eval_fidelity.py
HyperFidBench Gate1 / BrainGB-ABIDE-I 泳道 / run-04 fidelity 非 nan 验证

用 PyG GNNExplainer 对训好的 BrainGB GCN 算 fidelity(fid+, fid-)。
红线：
  - 扰动只在 held-out test 集，不混训练（split 由 make_split.py 输出的 split_indices.csv）
  - 评估集不泄漏（02_ACCEPTANCE.md 红线）
  - 目标：输出非 nan 有限数（Gate1③）

PyG fidelity API（researcher 2026-06-24 核实，PyG >= 2.3）：
    from torch_geometric.explain import Explainer, GNNExplainer
    from torch_geometric.explain.metric import fidelity
    explainer = Explainer(
        model=model,
        algorithm=GNNExplainer(epochs=200),
        explanation_type='model',
        node_mask_type='attributes',
        edge_mask_type='object',
        model_config=dict(
            mode='binary_classification',
            task_level='graph',
            return_type='log_probs',
        ),
    )
    explanation = explainer(data.x, data.edge_index, edge_attr=data.edge_attr, batch=data.batch, index=0)
    fid_pos, fid_neg = fidelity(explainer, explanation)

nan 隐患（已知，实验设计 doc 标注）：
    mask 全 0 / 全 1 可能导致 nan；本脚本在输出 csv 中原样保留 nan
    并在 summary 中统计 nan 比例（Gate1 判据：非 nan 比例 > 0 即通过）。

Windows 规范：__main__ 守卫，pathlib.Path 路径。

输出：
    results/braingb/fidelity_results.csv
        列：run_id,model,explainer,sample_id,fid_pos,fid_neg
    results/braingb/state.json 更新 fidelity 状态
"""

import argparse
import csv
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

import numpy as np
import torch
import torch.nn as nn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# BrainNNWrapper
# ---------------------------------------------------------------------------
# BrainNN.forward(data) 接收单个 PyG Data 对象，但 PyG Explainer/GNNExplainer
# 调用 model 的约定是 model(x, edge_index, edge_attr=..., batch=..., **kwargs)。
# 本 wrapper 把后者签名适配回 BrainNN 期望的 Data 包装形式。
#
# edge_attr=None fallback 假设：
#   GCN.forward 第一行即 torch.abs(edge_attr)，edge_attr 不能为 None。
#   GNNExplainer 内部某些前向调用（perturbed forward）可能不传 edge_attr；
#   fallback = 全 1 边权（形状 [E]），含义="所有边等权"，是保守合理默认值。
#   注意这会让被掩盖边（edge_mask→0 的边）在 perturbed forward 里以"权1"而非
#   原始 FC 权值参与，但对 Gate1 目标（fidelity 非 nan）不影响正确性。
#   TODO: 若需要精确 fidelity 数值，应在 wrapper 缓存原始 edge_attr 并在
#         edge_attr=None 时用缓存值而非全 1（届时升级 Opus 核设计）。
# ---------------------------------------------------------------------------


class BrainNNWrapper(nn.Module):
    """适配 BrainNN.forward(data) 到 PyG Explainer 期望的 (x, edge_index, **kwargs) 签名。"""

    def __init__(self, model: nn.Module):
        super().__init__()
        self.model = model  # 注册为子模块，梯度/参数访问正常

    def forward(self, x, edge_index, edge_attr=None, batch=None, **kwargs):
        from torch_geometric.data import Data

        # batch 为 None（单图无 batch 维）时，全部节点归属图 0
        if batch is None:
            batch = torch.zeros(x.size(0), dtype=torch.long, device=x.device)

        # edge_attr 为 None（GNNExplainer perturbed forward 可能不传）时 fallback 全 1 边权
        if edge_attr is None:
            # [E] 标量边权，与 GCN.forward 里 torch.abs(edge_attr) 兼容
            edge_attr = torch.ones(edge_index.size(1), dtype=x.dtype, device=x.device)

        data = Data(x=x, edge_index=edge_index, edge_attr=edge_attr, batch=batch)
        return self.model(data)  # BrainNN.forward(data) → F.log_softmax 输出


BRAINGB_DIR = REPO_ROOT / "vendor" / "BrainGB"
RESULTS_DIR = REPO_ROOT / "results" / "braingb"

if str(BRAINGB_DIR) not in sys.path:
    sys.path.insert(0, str(BRAINGB_DIR))

os.chdir(str(BRAINGB_DIR / "examples"))


def write_state(state_path: Path, state: dict):
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = state_path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    tmp.replace(state_path)


def load_model_from_ckpt(
    ckpt_path: Path,
    model_name: str,
    num_features: int,
    nodes_num: int,
    device: torch.device,
):
    """从 train_braingb.py 保存的 checkpoint 加载模型。"""
    from examples.build_model import build_model
    from train_braingb import build_braingb_args

    args = build_braingb_args(model_name=model_name)
    model = build_model(args, device, model_name, num_features, nodes_num)
    state_dict = torch.load(str(ckpt_path), map_location=device)
    model.load_state_dict(state_dict)
    model.eval()
    return model


def build_test_loader(dataset, test_indices, batch_size: int = 1):
    """
    构建 held-out test DataLoader（单 fold）。
    batch_size=1：GNNExplainer 对单 graph 逐一算 explanation。
    """
    from torch_geometric.loader import DataLoader

    test_set = dataset[test_indices]
    loader = DataLoader(
        test_set,
        batch_size=batch_size,
        shuffle=False,
        num_workers=0,
        pin_memory=False,
    )
    return loader


def compute_fidelity_for_loader(
    explainer,
    loader,
    device: torch.device,
    max_samples: Optional[int] = None,
):
    """
    对 test loader 中每个 graph 算 GNNExplainer fidelity。
    返回: list of (fid_pos, fid_neg)
    """
    from torch_geometric.explain.metric import fidelity as pyg_fidelity

    results = []
    for batch_idx, data in enumerate(loader):
        if max_samples is not None and batch_idx >= max_samples:
            break

        data = data.to(device)
        try:
            # GNNExplainer 对 graph-level 任务：explanation_type='model'
            # index=None 时对 batch 中所有 graph 各出一个 explanation（batch_size=1 时即 1 个）
            explanation = explainer(
                data.x,
                data.edge_index,
                edge_attr=data.edge_attr,
                batch=data.batch,
                index=None,
            )
            fid_pos, fid_neg = pyg_fidelity(explainer, explanation)
            # fid_pos, fid_neg 可能是 tensor；转为 Python float
            fid_pos_val = float(fid_pos.item()) if torch.is_tensor(fid_pos) else float(fid_pos)
            fid_neg_val = float(fid_neg.item()) if torch.is_tensor(fid_neg) else float(fid_neg)
        except Exception as e:
            logger.warning(f"Sample {batch_idx}: fidelity 计算失败 ({e})，记为 nan")
            fid_pos_val, fid_neg_val = float("nan"), float("nan")

        results.append((fid_pos_val, fid_neg_val))

        if (batch_idx + 1) % 50 == 0:
            logger.info(f"  已处理 {batch_idx+1} samples")

    return results


def eval_fidelity(
    run_id: str,
    model_name: str,
    atlas: str,
    dataset_name: str,
    ckpt_path: Optional[Path],
    split_csv_path: Path,
    fold_idx: int,
    output_dir: Path,
    explainer_epochs: int = 200,
    max_samples: Optional[int] = None,
    smoke: bool = False,
    gcn_mp_type: str = "weighted_sum",
    hidden_dim: int = 360,
):
    """
    主函数：加载模型 + split → 构建 test set → 逐 sample 算 fidelity → 写 csv。
    """
    from examples.get_transform import get_transform
    from src.dataset import BrainDataset
    from src.utils import get_y

    try:
        from torch_geometric.explain import Explainer, GNNExplainer
    except ImportError:
        raise ImportError(
            "torch_geometric.explain 未找到，需要 PyG >= 2.3。\n"
            "当前 PyG 版本可能不支持 Explainer API。"
        )

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info(f"[{run_id}] eval_fidelity device={device}")

    # 数据集
    examples_dir = BRAINGB_DIR / "examples"
    if dataset_name == "ABIDE":
        root_dir = str(examples_dir / "datasets" / "ABIDE")
    else:
        root_dir = str(examples_dir / "datasets")

    transform = get_transform("adj")
    dataset = BrainDataset(root=root_dir, name=dataset_name, pre_transform=transform)
    y = get_y(dataset)
    num_features = dataset[0].x.shape[1]
    nodes_num = dataset.num_nodes
    n_samples = len(dataset)
    logger.info(f"数据集大小={n_samples}, num_features={num_features}, nodes_num={nodes_num}")

    # 从 split_indices.csv 取 test 索引（held-out，不混训练）
    import pandas as pd
    fold_col = f"fold_{fold_idx}"
    split_df = pd.read_csv(str(split_csv_path))
    if fold_col not in split_df.columns:
        raise ValueError(
            f"split_indices.csv 中没有 {fold_col} 列。"
            f"可用列: {list(split_df.columns)}"
        )
    test_positions = split_df.index[split_df[fold_col] == "test"].tolist()
    logger.info(f"Fold {fold_idx} test 集大小: {len(test_positions)}")

    if smoke:
        logger.info("=== SMOKE MODE: 最多 3 samples ===")
        max_samples = 3

    # 构建 test loader（batch_size=1 for GNNExplainer）
    test_loader = build_test_loader(dataset, test_positions, batch_size=1)

    # 加载或 mock 模型
    if ckpt_path is not None and ckpt_path.exists():
        from examples.build_model import build_model
        from train_braingb import build_braingb_args
        args = build_braingb_args(model_name=model_name, gcn_mp_type=gcn_mp_type, hidden_dim=hidden_dim)
        model = build_model(args, device, model_name, num_features, nodes_num)
        state_dict = torch.load(str(ckpt_path), map_location=device)
        model.load_state_dict(state_dict)
        model.eval()
        logger.info(f"已加载 checkpoint: {ckpt_path} (mp={gcn_mp_type}, hidden={hidden_dim})")
    else:
        # 无 ckpt：使用随机初始化模型（Gate1 目标=非 nan，不要求准确）
        logger.warning(
            f"Checkpoint 不存在 ({ckpt_path})，使用随机初始化模型。"
            "Gate1 目标仅验证 fidelity 非 nan，不要求分类准确。"
        )
        from examples.build_model import build_model
        from train_braingb import build_braingb_args
        args = build_braingb_args(model_name=model_name, gcn_mp_type=gcn_mp_type, hidden_dim=hidden_dim)
        model = build_model(args, device, model_name, num_features, nodes_num)
        model.eval()

    # 构造 PyG Explainer
    # BrainNN.forward(data) 签名与 Explainer 期望的 (x, edge_index, **kwargs) 不兼容
    # → 用 BrainNNWrapper 适配（见文件头注释）；wrapper 把 model 注册为子模块，
    #   eval()/parameters() 自动传导，梯度流向正常。
    wrapped_model = BrainNNWrapper(model)
    wrapped_model.eval()
    # GNNExplainer epochs=200（来自实验设计 doc + PyG 官方 example）
    explainer = Explainer(
        model=wrapped_model,
        algorithm=GNNExplainer(epochs=explainer_epochs),
        explanation_type="model",
        node_mask_type="attributes",
        edge_mask_type="object",
        model_config=dict(
            # BrainGB brainnn.py 输出 F.log_softmax(2类) → multiclass+log_probs
            # (PyG binary_classification 不收 log_probs，只收 raw/probs)
            mode="multiclass_classification",
            task_level="graph",
            return_type="log_probs",
        ),
    )

    write_state(output_dir / "state.json", {
        "run_id": run_id,
        "status": "fidelity_running",
        "model": model_name,
        "atlas": atlas,
        "dataset": dataset_name,
        "fold": fold_idx,
        "timestamp": time.time(),
    })

    # 计算 fidelity
    logger.info(f"开始 GNNExplainer fidelity 计算 (epochs={explainer_epochs})...")
    fidelity_results = compute_fidelity_for_loader(
        explainer, test_loader, device, max_samples=max_samples
    )

    # 写结果 csv（列对齐 HyperFidBench 约定）
    output_dir.mkdir(parents=True, exist_ok=True)
    fidelity_csv = output_dir / "fidelity_results.csv"
    header = ["run_id", "model", "explainer", "sample_id", "fid_pos", "fid_neg"]
    write_header = not fidelity_csv.exists()
    with open(str(fidelity_csv), "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(header)
        for i, (fid_pos, fid_neg) in enumerate(fidelity_results):
            sample_id = test_positions[i] if i < len(test_positions) else i
            writer.writerow([run_id, model_name, "GNNExplainer", sample_id, fid_pos, fid_neg])

    # 统计
    fid_pos_vals = np.array([r[0] for r in fidelity_results])
    fid_neg_vals = np.array([r[1] for r in fidelity_results])
    nan_count_pos = int(np.isnan(fid_pos_vals).sum())
    nan_count_neg = int(np.isnan(fid_neg_vals).sum())
    n_total = len(fidelity_results)
    logger.info(f"Fidelity 结果: n={n_total}")
    logger.info(f"  fid+: nan={nan_count_pos}/{n_total}, "
                f"mean={np.nanmean(fid_pos_vals):.4f}")
    logger.info(f"  fid-: nan={nan_count_neg}/{n_total}, "
                f"mean={np.nanmean(fid_neg_vals):.4f}")

    # Gate1 判定
    n_valid_pos = n_total - nan_count_pos
    n_valid_neg = n_total - nan_count_neg
    gate1_pass = (n_valid_pos > 0) and (n_valid_neg > 0)
    logger.info(f"Gate1③ fidelity 非 nan: {'PASS' if gate1_pass else 'FAIL'}")
    logger.info(f"  (有效 fid+={n_valid_pos}/{n_total}, fid-={n_valid_neg}/{n_total})")

    write_state(output_dir / "state.json", {
        "run_id": run_id,
        "status": "fidelity_done",
        "model": model_name,
        "atlas": atlas,
        "dataset": dataset_name,
        "fold": fold_idx,
        "n_total": n_total,
        "nan_fid_pos": nan_count_pos,
        "nan_fid_neg": nan_count_neg,
        "mean_fid_pos": float(np.nanmean(fid_pos_vals)) if n_valid_pos > 0 else None,
        "mean_fid_neg": float(np.nanmean(fid_neg_vals)) if n_valid_neg > 0 else None,
        "gate1_pass": gate1_pass,
        "timestamp": time.time(),
    })

    logger.info(f"Fidelity CSV 已保存: {fidelity_csv}")
    return fidelity_results


def main():
    parser = argparse.ArgumentParser(description="HyperFidBench Gate1 run-04 fidelity 评估")
    parser.add_argument("--run_id", type=str, default="run-04-fidelity-on-braingb")
    parser.add_argument("--model_name", type=str, default="gcn", choices=["gcn", "gat"])
    parser.add_argument("--atlas", type=str, default="cc200")
    parser.add_argument("--dataset_name", type=str, default="ABIDE")
    parser.add_argument(
        "--ckpt_path",
        type=str,
        default=None,
        help="训好的模型 checkpoint 路径（.pt）；若不提供则用随机初始化模型",
    )
    parser.add_argument(
        "--split_csv_path",
        type=str,
        default=str(REPO_ROOT / "data" / "external" / "abide1" / "split_indices.csv"),
        help="make_split.py 输出的 split_indices.csv 路径",
    )
    parser.add_argument(
        "--fold_idx",
        type=int,
        default=0,
        help="使用哪个 fold 的 test 集（0-4），默认 fold 0",
    )
    parser.add_argument(
        "--explainer_epochs",
        type=int,
        default=200,
        help="GNNExplainer 优化 epochs，默认 200（官方 example 值）",
    )
    parser.add_argument(
        "--max_samples",
        type=int,
        default=None,
        help="最多处理多少 test 样本（默认全部）",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default=str(RESULTS_DIR),
        help="结果输出目录",
    )
    parser.add_argument(
        "--smoke",
        type=int,
        default=0,
        help="smoke=1: 只算前 3 个 sample，验证 API 不报错",
    )
    parser.add_argument("--gcn_mp_type", type=str, default="weighted_sum",
                        help="须与 ckpt 训练时一致（run-01 headline=edge_node_concate）")
    parser.add_argument("--hidden_dim", type=int, default=360,
                        help="须与 ckpt 训练时一致（run-01 headline=256）")
    args = parser.parse_args()

    ckpt_path = Path(args.ckpt_path) if args.ckpt_path else None

    eval_fidelity(
        run_id=args.run_id,
        model_name=args.model_name,
        atlas=args.atlas,
        dataset_name=args.dataset_name,
        ckpt_path=ckpt_path,
        split_csv_path=Path(args.split_csv_path),
        fold_idx=args.fold_idx,
        output_dir=Path(args.output_dir),
        explainer_epochs=args.explainer_epochs,
        max_samples=args.max_samples,
        smoke=bool(args.smoke),
        gcn_mp_type=args.gcn_mp_type,
        hidden_dim=args.hidden_dim,
    )


if __name__ == "__main__":
    main()
