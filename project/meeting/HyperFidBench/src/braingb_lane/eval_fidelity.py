"""
eval_fidelity.py
HyperFidBench Gate2 / BrainGB-ABIDE-I 泳道 / run-05 fidelity-sparsity 曲线 + AUFSC

升级（2026-06-26）：从单点 topk=50 → 扫 sparsity 出 fidelity-sparsity 曲线 + AUFSC

【根因】单点 topk=50 对 ~40000 边密集 FC 图 = 0.125% sparsity：
  complement 子图保留 99.875% 原图 → 预测不变 → fid+ 结构性 ≡ 0。
  单点 topk 报法本就不是 benchmark 标准。

【修复策略】
  GNNExplainer 训一次 soft mask（Explainer 不传 threshold_config）
  → 同一 soft mask 在 sparsity_list 每个水平分别阈值化
  → 每个 sparsity 算 fid+/fid-
  → 聚合：AUFSC（梯形法）+ characterization score（GraphFramEx）

【保留不动（A/B/C）】
  A: node_mask_type=None（去 node mask 防 complement 归零特征）
  B: edge_size=0.05（稀疏正则；threshold_config 移出 Explainer 构造）
  C: BrainNNWrapper._cached_edge_attr（perturbed forward 用缓存 edge_attr）

【PyG 2.5.3 API —— 已标 TODO 需 HPC 核实】
  # TODO 核 PyG 2.5.3: explanation.threshold(ThresholdConfig(...)) 是否存在且返回副本
  #   推断：PyG 2.3+ 加此方法、返回新 Explanation 对象（非原地）；2.5.3 应同
  #   若 HPC 报 AttributeError → 手动 copy + 赋 edge_mask
  # TODO 核 PyG 2.5.3: fidelity_curve_auc 是否存在
  #   推断：2.5.3 无此函数（较新 API）；已用 np.trapz 手算 AUFSC

【AUFSC】AUC of f(s) = fid+(s)/(1-fid-(s)) on sparsity axis（梯形法）
【charact】GraphFramEx 调和均值 = 2·fid+·(1-fid-)/(fid++(1-fid-))

nan 隐患（保留）：mask 全 0/1 可能导致 nan，原样保留并统计

Windows 规范：__main__ 守卫，pathlib.Path 路径，DataLoader pin_memory=False, num_workers=0

输出：
    results/braingb/fidelity_results.csv
        列：run_id,model,explainer,sparsity,topk,sample_id,fid_pos,fid_neg
    results/braingb/state.json：
        sparsity_list / sparsity_stats(per-sparsity mean+charact) / aufsc / gate2_pass
"""

import argparse
import csv
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import List, Optional

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
# BrainNNWrapper（改动 C，保留）
# ---------------------------------------------------------------------------
# BrainNN.forward(data) 接收单个 PyG Data 对象，但 PyG Explainer/GNNExplainer
# 调用 model 的约定是 model(x, edge_index, edge_attr=..., batch=..., **kwargs)。
# 本 wrapper 把后者签名适配回 BrainNN 期望的 Data 包装形式。
#
# edge_attr fallback 策略（改动 C）：
#   GCN.forward 第一行即 torch.abs(edge_attr)，edge_attr 不能为 None。
#   改动 C：wrapper 缓存首次传入的真实 edge_attr（_cached_edge_attr）；
#     perturbed forward 无 edge_attr 时优先用缓存，最终 fallback 才用全 1。
# ---------------------------------------------------------------------------


class BrainNNWrapper(nn.Module):
    """适配 BrainNN.forward(data) 到 PyG Explainer 期望的 (x, edge_index, **kwargs) 签名。"""

    def __init__(self, model: nn.Module):
        super().__init__()
        self.model = model  # 注册为子模块，梯度/参数访问正常
        self._cached_edge_attr = None  # 改动 C：缓存真实 edge_attr，供 perturbed forward 用

    def forward(self, x, edge_index, edge_attr=None, batch=None, **kwargs):
        from torch_geometric.data import Data

        # batch 为 None（单图无 batch 维）时，全部节点归属图 0
        if batch is None:
            batch = torch.zeros(x.size(0), dtype=torch.long, device=x.device)

        # 改动 C：edge_attr 三级 fallback
        if edge_attr is not None:
            # 有真实 edge_attr：更新缓存
            self._cached_edge_attr = edge_attr
        elif self._cached_edge_attr is not None:
            # 无真实值但缓存存在（GNNExplainer perturbed forward）：用缓存保真 FC 权值
            edge_attr = self._cached_edge_attr
        else:
            # 最终 fallback：全 1 边权（首次调用前不应发生，保守兜底）
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


# ---------------------------------------------------------------------------
# AUFSC + characterization score 计算工具
# ---------------------------------------------------------------------------

def _compute_aufsc(
    sparsity_arr: np.ndarray,
    fid_pos_arr: np.ndarray,
    fid_neg_arr: np.ndarray,
) -> float:
    """
    AUFSC：AUC of fidelity_score(s) = fid+(s) / (1 - fid-(s)) on sparsity axis.
    梯形法 np.trapz。基准：GraphFramEx / GNNShap benchmark。

    # TODO 核 PyG 2.5.3: fidelity_curve_auc 是否在 torch_geometric.explain.metric 存在
    #   推断：PyG 2.5.3 无此函数（较新 API），此处用 np.trapz 手算，行为等价。
    #   若将来升级 PyG 想用官方实现，可 try-import fidelity_curve_auc。
    """
    denom = np.clip(1.0 - fid_neg_arr, 1e-6, None)
    score = fid_pos_arr / denom
    valid = ~(np.isnan(score) | np.isnan(sparsity_arr))
    if valid.sum() < 2:
        return float("nan")
    return float(np.trapz(score[valid], sparsity_arr[valid]))


def _compute_charact(fid_pos: float, fid_neg: float) -> float:
    """
    Characterization score（GraphFramEx，w+=w-=0.5）:
        charact = 2 * fid+ * (1 - fid-) / (fid+ + (1 - fid-))
    即 调和均值(fid+, 1-fid-)。
    """
    if np.isnan(fid_pos) or np.isnan(fid_neg):
        return float("nan")
    num = 2.0 * fid_pos * (1.0 - fid_neg)
    denom = fid_pos + (1.0 - fid_neg)
    if abs(denom) < 1e-9:
        return float("nan")
    return float(num / denom)


# ---------------------------------------------------------------------------
# 数据 / 模型加载
# ---------------------------------------------------------------------------

def load_model_from_ckpt(
    ckpt_path: Path,
    model_name: str,
    num_features: int,
    nodes_num: int,
    device: torch.device,
    gcn_mp_type: str = "weighted_sum",
    hidden_dim: int = 360,
):
    """从 train_braingb.py 保存的 checkpoint 加载模型。"""
    from examples.build_model import build_model
    from train_braingb import build_braingb_args

    args = build_braingb_args(
        model_name=model_name,
        gcn_mp_type=gcn_mp_type,
        hidden_dim=hidden_dim,
    )
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
        pin_memory=False,  # Windows spawn worker 不支持 pin_memory
    )
    return loader


# ---------------------------------------------------------------------------
# 核心：sparsity sweep fidelity 计算
# ---------------------------------------------------------------------------

def compute_fidelity_sparsity_sweep(
    explainer,
    loader,
    device: torch.device,
    sparsity_list: List[float],
    max_samples: Optional[int] = None,
) -> List[dict]:
    """
    对 test loader 中每个 graph：
      1. 训一次 soft mask（Explainer 无 threshold_config → 连续 edge_mask）
      2. 同一 soft mask 在每个 sparsity 水平分别阈值化 → 计算 fid+/fid-

    返回: list of dict
        {sample_id_local, sparsity, topk, fid_pos, fid_neg}
        （每 sample × 每 sparsity 一条记录）

    # TODO 核 PyG 2.5.3: explanation.threshold(ThresholdConfig(...)) 行为
    #   推断：PyG 2.3+ 加此方法，返回新 Explanation 对象（不原地修改原 explanation）。
    #   若 HPC 报 AttributeError → 需升级 PyG 或手动 copy explanation 后赋 edge_mask。
    # TODO 核 PyG 2.5.3: ThresholdConfig(threshold_type="topk", value=N) 签名
    #   推断：PyG 2.5.3 与 2.8 一致，无 breaking change。
    """
    from torch_geometric.explain.metric import fidelity as pyg_fidelity
    from torch_geometric.explain import ThresholdConfig

    all_records: List[dict] = []

    for batch_idx, data in enumerate(loader):
        if max_samples is not None and batch_idx >= max_samples:
            break

        data = data.to(device)
        num_edges = data.edge_index.size(1)  # |E| 该图实际边数

        # --- Step 1: 训一次 soft mask ---
        try:
            explanation = explainer(
                data.x,
                data.edge_index,
                edge_attr=data.edge_attr,
                batch=data.batch,
                index=None,
            )
        except Exception as e:
            logger.warning(
                f"Sample {batch_idx}: GNNExplainer 失败 ({e})，全 sparsity 记 nan"
            )
            for s in sparsity_list:
                topk = max(1, min(round(s * num_edges), num_edges))
                all_records.append({
                    "sample_id_local": batch_idx,
                    "sparsity": s,
                    "topk": topk,
                    "fid_pos": float("nan"),
                    "fid_neg": float("nan"),
                })
            continue

        # --- Step 2: 每个 sparsity 阈值化 + 算 fidelity ---
        for s in sparsity_list:
            # topk = round(s × |E|)，边界 clip [1, |E|]
            topk = max(1, min(round(s * num_edges), num_edges))

            try:
                # TODO 核 PyG 2.5.3: ThresholdConfig 签名同 2.8（推断）
                tc = ThresholdConfig(threshold_type="topk", value=topk)

                # TODO 核 PyG 2.5.3: explanation.threshold(tc) 返回副本（推断）
                # 推断：返回新 Explanation 对象，edge_mask 为 0/1 二值
                thresholded = explanation.threshold(tc)

                fid_pos, fid_neg = pyg_fidelity(explainer, thresholded)
                fid_pos_val = (
                    float(fid_pos.item()) if torch.is_tensor(fid_pos) else float(fid_pos)
                )
                fid_neg_val = (
                    float(fid_neg.item()) if torch.is_tensor(fid_neg) else float(fid_neg)
                )
            except Exception as e:
                logger.warning(
                    f"Sample {batch_idx} sparsity={s:.2f}: fidelity 失败 ({e})，记 nan"
                )
                fid_pos_val, fid_neg_val = float("nan"), float("nan")

            all_records.append({
                "sample_id_local": batch_idx,
                "sparsity": s,
                "topk": topk,
                "fid_pos": fid_pos_val,
                "fid_neg": fid_neg_val,
            })

        if (batch_idx + 1) % 10 == 0:
            logger.info(f"  已处理 {batch_idx + 1} samples")

    return all_records


# ---------------------------------------------------------------------------
# 主评估函数
# ---------------------------------------------------------------------------

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
    sparsity_list: Optional[List[float]] = None,
):
    """
    主函数：加载模型 + split → 构建 test set
    → GNNExplainer soft mask（每 sample 一次）
    → sparsity sweep（每个水平阈值化 + fidelity）
    → AUFSC + charact → 写 csv + state.json
    """
    if sparsity_list is None:
        sparsity_list = [0.05, 0.1, 0.2, 0.3, 0.4, 0.5]

    from examples.get_transform import get_transform
    from src.dataset import BrainDataset
    from src.utils import get_y

    try:
        from torch_geometric.explain import Explainer, GNNExplainer
        from torch_geometric.explain import ThresholdConfig  # noqa: F401  核 import 是否可用
    except ImportError:
        raise ImportError(
            "torch_geometric.explain 未找到，需要 PyG >= 2.3。\n"
            "当前 PyG 版本可能不支持 Explainer API。"
        )

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info(f"[{run_id}] eval_fidelity device={device}")
    logger.info(f"Sparsity sweep: {sparsity_list}")

    # --- 数据集 ---
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
    logger.info(
        f"数据集大小={n_samples}, num_features={num_features}, nodes_num={nodes_num}"
    )

    # --- split → held-out test 索引 ---
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
        logger.info("=== SMOKE MODE: 最多 3 samples × 全 sparsity ===")
        max_samples = 3

    # --- 构建 test loader ---
    test_loader = build_test_loader(dataset, test_positions, batch_size=1)

    # --- 加载或 mock 模型 ---
    if ckpt_path is not None and ckpt_path.exists():
        from examples.build_model import build_model
        from train_braingb import build_braingb_args

        args = build_braingb_args(
            model_name=model_name,
            gcn_mp_type=gcn_mp_type,
            hidden_dim=hidden_dim,
        )
        model = build_model(args, device, model_name, num_features, nodes_num)
        state_dict = torch.load(str(ckpt_path), map_location=device)
        model.load_state_dict(state_dict)
        model.eval()
        logger.info(
            f"已加载 checkpoint: {ckpt_path} (mp={gcn_mp_type}, hidden={hidden_dim})"
        )
    else:
        logger.warning(
            f"Checkpoint 不存在 ({ckpt_path})，使用随机初始化模型。"
            "Gate2 目标：验证 fidelity-sparsity 曲线不退化（非 nan + 高 sparsity fid+ >0）。"
        )
        from examples.build_model import build_model
        from train_braingb import build_braingb_args

        args = build_braingb_args(
            model_name=model_name,
            gcn_mp_type=gcn_mp_type,
            hidden_dim=hidden_dim,
        )
        model = build_model(args, device, model_name, num_features, nodes_num)
        model.eval()

    # --- 构造 PyG Explainer（改动 B 保留 edge_size=0.05；移除 threshold_config → 保留 soft mask）---
    # 改动 A（保留）：node_mask_type=None
    # 改动 B（保留边稀疏正则）：edge_size=0.05
    # 升级：不传 threshold_config → explainer 返回连续 edge_mask（soft mask）
    #       后续在 compute_fidelity_sparsity_sweep 里按 sparsity 手动阈值化
    wrapped_model = BrainNNWrapper(model)
    wrapped_model.eval()
    explainer = Explainer(
        model=wrapped_model,
        algorithm=GNNExplainer(epochs=explainer_epochs, edge_size=0.05),
        explanation_type="model",
        node_mask_type=None,      # 改动 A：去 node_mask 防 complement 归零特征
        edge_mask_type="object",
        # threshold_config 不传：保留 soft mask，后续手动 sparsity sweep 阈值化
        model_config=dict(
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
        "sparsity_list": sparsity_list,
        "timestamp": time.time(),
    })

    # --- 核心计算：sparsity sweep ---
    logger.info(
        f"开始 GNNExplainer sparsity sweep "
        f"(epochs={explainer_epochs}, sparsity={sparsity_list})..."
    )
    all_records = compute_fidelity_sparsity_sweep(
        explainer,
        test_loader,
        device,
        sparsity_list=sparsity_list,
        max_samples=max_samples,
    )
    logger.info(f"共生成 {len(all_records)} 条记录（samples × sparsity）")

    # --- 写 CSV（升级列格式）---
    output_dir.mkdir(parents=True, exist_ok=True)
    fidelity_csv = output_dir / "fidelity_results.csv"
    header = [
        "run_id", "model", "explainer",
        "sparsity", "topk",
        "sample_id", "fid_pos", "fid_neg",
    ]
    write_header = not fidelity_csv.exists()
    with open(str(fidelity_csv), "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(header)
        for rec in all_records:
            loc = rec["sample_id_local"]
            sample_id_abs = test_positions[loc] if loc < len(test_positions) else loc
            writer.writerow([
                run_id,
                model_name,
                "GNNExplainer",
                rec["sparsity"],
                rec["topk"],
                sample_id_abs,
                rec["fid_pos"],
                rec["fid_neg"],
            ])

    # --- Per-sparsity 聚合统计 ---
    sparsity_stats: dict = {}
    for s in sparsity_list:
        s_recs = [r for r in all_records if r["sparsity"] == s]
        pos_vals = np.array([r["fid_pos"] for r in s_recs], dtype=float)
        neg_vals = np.array([r["fid_neg"] for r in s_recs], dtype=float)

        mean_pos = (
            float(np.nanmean(pos_vals)) if not np.all(np.isnan(pos_vals)) else None
        )
        mean_neg = (
            float(np.nanmean(neg_vals)) if not np.all(np.isnan(neg_vals)) else None
        )
        if mean_pos is not None and mean_neg is not None:
            charact = _compute_charact(mean_pos, mean_neg)
        else:
            charact = None

        sparsity_stats[str(s)] = {
            "mean_fid_pos": mean_pos,
            "mean_fid_neg": mean_neg,
            "charact": charact,
        }
        _pos_str = f"{mean_pos:.4f}" if mean_pos is not None else "None"
        _neg_str = f"{mean_neg:.4f}" if mean_neg is not None else "None"
        _ch_str = f"{charact:.4f}" if charact is not None else "None"
        logger.info(
            f"  sparsity={s:.2f}: fid+={_pos_str}, fid-={_neg_str}, charact={_ch_str}"
        )

    # --- AUFSC（梯形法，非 PyG 官方 fidelity_curve_auc）---
    sp_arr = np.array(sparsity_list, dtype=float)
    pos_arr = np.array(
        [sparsity_stats[str(s)]["mean_fid_pos"] or float("nan") for s in sparsity_list],
        dtype=float,
    )
    neg_arr = np.array(
        [sparsity_stats[str(s)]["mean_fid_neg"] or float("nan") for s in sparsity_list],
        dtype=float,
    )
    aufsc = _compute_aufsc(sp_arr, pos_arr, neg_arr)
    logger.info(f"AUFSC (np.trapz)={aufsc:.4f}" if not np.isnan(aufsc) else "AUFSC=nan")

    # --- gate2_pass：AUFSC 非 nan 且高 sparsity(>=0.3) 端 fid+ 有非零值 ---
    high_sp_pos = [
        sparsity_stats[str(s)]["mean_fid_pos"]
        for s in sparsity_list
        if s >= 0.3 and sparsity_stats[str(s)]["mean_fid_pos"] is not None
    ]
    gate2_pass = bool(
        not np.isnan(aufsc)
        and len(high_sp_pos) > 0
        and any(v > 0.0 for v in high_sp_pos)
    )
    logger.info(f"Gate2 fidelity-sparsity 曲线非退化: {'PASS' if gate2_pass else 'FAIL'}")

    write_state(output_dir / "state.json", {
        "run_id": run_id,
        "status": "fidelity_done",
        "model": model_name,
        "atlas": atlas,
        "dataset": dataset_name,
        "fold": fold_idx,
        "sparsity_list": sparsity_list,
        "sparsity_stats": sparsity_stats,
        "aufsc": float(aufsc) if not np.isnan(aufsc) else None,
        "gate2_pass": gate2_pass,
        "timestamp": time.time(),
    })

    logger.info(f"Fidelity CSV 已保存: {fidelity_csv}")
    return all_records


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="HyperFidBench Gate2 run-05 fidelity-sparsity 曲线 + AUFSC"
    )
    parser.add_argument("--run_id", type=str, default="run-05-fidelity-sparsity-sweep")
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
        help="GNNExplainer 优化 epochs，默认 200",
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
        help="smoke=1: 只算前 3 个 sample × 全 sparsity，验证 API 不报错",
    )
    parser.add_argument(
        "--gcn_mp_type",
        type=str,
        default="weighted_sum",
        help="须与 ckpt 训练时一致（run-01 headline=edge_node_concate）",
    )
    parser.add_argument(
        "--hidden_dim",
        type=int,
        default=360,
        help="须与 ckpt 训练时一致（run-01 headline=256）",
    )
    parser.add_argument(
        "--sparsity_list",
        type=str,
        default="0.05,0.1,0.2,0.3,0.4,0.5",
        help=(
            "扫描的 sparsity 水平，逗号分隔浮点数。"
            "默认 '0.05,0.1,0.2,0.3,0.4,0.5'（GraphFramEx 标准 6 点）。"
            "smoke 模式下仍跑全部 sparsity（仅限 3 samples）。"
        ),
    )
    args = parser.parse_args()

    ckpt_path = Path(args.ckpt_path) if args.ckpt_path else None

    # 解析 sparsity_list
    sparsity_list = [
        float(x.strip()) for x in args.sparsity_list.split(",") if x.strip()
    ]
    if not sparsity_list:
        raise ValueError("--sparsity_list 解析为空，请检查输入格式（示例：0.05,0.1,0.2）")

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
        sparsity_list=sparsity_list,
    )


if __name__ == "__main__":
    main()
