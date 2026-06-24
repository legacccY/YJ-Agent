"""
train_braingb.py
HyperFidBench Gate1 / BrainGB-ABIDE-I 泳道 / run-01 GCN / run-02 GAT / run-05 multiatlas

薄封装调 vendor/BrainGB 训练。不修改 BrainGB 内部任何代码。
官方超参（来自 vendor/BrainGB/examples/example_main.py argparse 默认值，researcher 2026-06-24 核实）：
    lr=1e-4, weight_decay=1e-4, epochs=100, hidden_dim=360, n_GNN_layers=2, n_MLP_layers=1
    dropout=0.5, train_batch_size=16, test_batch_size=16, k_fold_splits=5
    gcn_mp_type=weighted_sum, gat_mp_type=attention_weighted, num_heads=2
    pooling=concat, node_features=adj, mixup=1, seed=112078

Windows 规范：
    - if __name__ == '__main__' 守卫（multiprocessing spawn 安全）
    - DataLoader 不用 num_workers > 0 默认（避免 Windows spawn 坑）
    - 路径全用 pathlib.Path 或正斜杠

输出：
    results/braingb_results.csv   （列：run_id,model,atlas,dataset,seed,test_acc,test_auc）
    results/state.json            （训练进度，/loop 监控用）
"""

import argparse
import json
import logging
import random
import os
import sys
import time
from pathlib import Path
from typing import List

import numpy as np
import torch
from sklearn.model_selection import StratifiedKFold
from torch_geometric.loader import DataLoader

# torch 2.6+ 把 torch.load 的 weights_only 默认翻 True；BrainGB(老 torch pin) 重载自己
# 处理好的缓存(我们自建 abide.npy 派生，可信)时未传 False。本 shim 仅在 wrapper 层兼容
# torch 版本漂移，不改 vendor 算法逻辑（复现零偏离不受影响）。
_orig_torch_load = torch.load
def _torch_load_compat(*a, **k):
    k.setdefault("weights_only", False)
    return _orig_torch_load(*a, **k)
torch.load = _torch_load_compat

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# 项目根目录（脚本在 src/braingb_lane/，往上两级）
REPO_ROOT = Path(__file__).resolve().parents[2]
BRAINGB_DIR = REPO_ROOT / "vendor" / "BrainGB"
RESULTS_DIR = REPO_ROOT / "results" / "braingb"

# 将 vendor/BrainGB 加入 sys.path，使 `from src.xxx import` 生效
if str(BRAINGB_DIR) not in sys.path:
    sys.path.insert(0, str(BRAINGB_DIR))

# 切换 cwd 到 BrainGB 目录（BrainGB 内部路径基于 __file__ 的相对路径）
os.chdir(str(BRAINGB_DIR / "examples"))


def seed_everything(seed: int):
    """固定随机种子（照抄 BrainGB example_main.py）"""
    random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def write_state(state_path: Path, state: dict):
    """写 state.json（CLAUDE.md 监控规范：训练脚本自己写 state 才可靠）"""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = state_path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    tmp.replace(state_path)  # 原子写（防 /loop 读到半写文件）


def build_braingb_args(
    model_name: str = "gcn",
    dataset_name: str = "ABIDE",
    node_features: str = "adj",
    pooling: str = "concat",
    gcn_mp_type: str = "weighted_sum",
    gat_mp_type: str = "attention_weighted",
    num_heads: int = 2,
    n_GNN_layers: int = 2,
    n_MLP_layers: int = 1,
    hidden_dim: int = 360,
    gat_hidden_dim: int = 8,
    edge_emb_dim: int = 256,
    bucket_sz: float = 0.05,
    lr: float = 1e-4,
    weight_decay: float = 1e-4,
    dropout: float = 0.5,
    epochs: int = 100,
    train_batch_size: int = 16,
    test_batch_size: int = 16,
    k_fold_splits: int = 5,
    seed: int = 112078,
    test_interval: int = 5,
    mixup: int = 1,
    repeat: int = 1,
    enable_nni: bool = False,
    diff: float = 0.2,
):
    """
    构造 BrainGB 期望的 args Namespace。
    所有默认值来自 vendor/BrainGB/examples/example_main.py argparse 默认，不臆想。
    """
    import argparse
    args = argparse.Namespace(
        model_name=model_name,
        dataset_name=dataset_name,
        node_features=node_features,
        pooling=pooling,
        gcn_mp_type=gcn_mp_type,
        gat_mp_type=gat_mp_type,
        num_heads=num_heads,
        n_GNN_layers=n_GNN_layers,
        n_MLP_layers=n_MLP_layers,
        hidden_dim=hidden_dim,
        gat_hidden_dim=gat_hidden_dim,
        edge_emb_dim=edge_emb_dim,
        bucket_sz=bucket_sz,
        lr=lr,
        weight_decay=weight_decay,
        dropout=dropout,
        epochs=epochs,
        train_batch_size=train_batch_size,
        test_batch_size=test_batch_size,
        k_fold_splits=k_fold_splits,
        seed=seed,
        test_interval=test_interval,
        mixup=mixup,
        repeat=repeat,
        enable_nni=enable_nni,
        diff=diff,
        view=1,  # BrainDataset 默认 view=1（fMRI）
    )
    return args


def run_experiment(
    run_id: str,
    model_name: str,
    dataset_name: str,
    atlas: str,
    seeds: List[int],
    args,
    state_path: Path,
    results_path: Path,
):
    """
    单个实验配置（run_id）跑完整 5-fold CV × N seeds。
    对齐 BrainGB example_main.py 的训练/评估流程，不改内部逻辑。
    """
    from examples.build_model import build_model
    from examples.get_transform import get_transform
    from examples.train_and_evaluate import train_and_evaluate, evaluate
    from src.dataset import BrainDataset
    from src.utils import get_y

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info(f"[{run_id}] device={device}, model={model_name}, atlas={atlas}")

    # BrainGB 数据集路径（与 example_main.py 一致）
    examples_dir = BRAINGB_DIR / "examples"
    if dataset_name == "ABIDE":
        root_dir = str(examples_dir / "datasets" / "ABIDE")
    else:
        root_dir = str(examples_dir / "datasets")

    # 加载数据集（BrainDataset 会读 abide.npy 并缓存 processed/）
    transform = get_transform(args.node_features)
    dataset = BrainDataset(root=root_dir, name=dataset_name, pre_transform=transform)
    y = get_y(dataset)
    num_features = dataset[0].x.shape[1]
    nodes_num = dataset.num_nodes
    logger.info(f"[{run_id}] 数据集大小={len(dataset)}, num_features={num_features}, nodes_num={nodes_num}")

    all_accs, all_aucs = [], []

    write_state(state_path, {
        "run_id": run_id,
        "status": "running",
        "model": model_name,
        "atlas": atlas,
        "dataset": dataset_name,
        "epoch": 0,
        "seed_idx": 0,
        "fold_idx": 0,
        "acc": None,
        "auc": None,
        "timestamp": time.time(),
    })

    for seed_idx, seed in enumerate(seeds):
        logger.info(f"[{run_id}] === Seed {seed} ({seed_idx+1}/{len(seeds)}) ===")
        seed_everything(seed)

        skf = StratifiedKFold(n_splits=args.k_fold_splits, shuffle=True, random_state=seed)
        fold_accs, fold_aucs = [], []

        for fold_idx, (train_index, test_index) in enumerate(skf.split(dataset, y)):
            logger.info(f"[{run_id}] Seed={seed} Fold={fold_idx} train={len(train_index)} test={len(test_index)}")
            # Windows numpy 默认 int32，PyG index_select 要 int64(long) → 显式转 torch.long
            train_index = torch.as_tensor(train_index, dtype=torch.long)
            test_index = torch.as_tensor(test_index, dtype=torch.long)

            model = build_model(args, device, model_name, num_features, nodes_num)
            optimizer = torch.optim.Adam(
                model.parameters(), lr=args.lr, weight_decay=args.weight_decay
            )

            train_set = dataset[train_index]
            test_set = dataset[test_index]

            # Windows spawn 安全：num_workers=0, pin_memory=False
            train_loader = DataLoader(
                train_set,
                batch_size=args.train_batch_size,
                shuffle=False,
                num_workers=0,
                pin_memory=False,
            )
            test_loader = DataLoader(
                test_set,
                batch_size=args.test_batch_size,
                shuffle=False,
                num_workers=0,
                pin_memory=False,
            )

            # 训练（直接调 BrainGB 官方函数）
            test_micro, test_auc, test_macro = train_and_evaluate(
                model, train_loader, test_loader, optimizer, device, args
            )
            # 最终评估
            test_micro, test_auc, test_macro = evaluate(model, device, test_loader)
            logger.info(
                f"[{run_id}] Seed={seed} Fold={fold_idx} "
                f"acc={test_micro*100:.2f}% auc={test_auc*100:.2f}%"
            )

            fold_accs.append(test_micro)
            fold_aucs.append(test_auc)

            # 存 checkpoint（run-04 fidelity 需真训练权重，非随机初始化；纯 instrumentation 不改训练）
            # 只存第一个 seed 的 fold 0，供 eval_fidelity 用
            if seed_idx == 0 and fold_idx == 0:
                ckpt_path = state_path.parent / f"{run_id}_seed{seed}_fold0.pt"
                torch.save(model.state_dict(), ckpt_path)
                logger.info(f"[{run_id}] 已存 checkpoint: {ckpt_path}")

            # 更新 state
            write_state(state_path, {
                "run_id": run_id,
                "status": "running",
                "model": model_name,
                "atlas": atlas,
                "dataset": dataset_name,
                "epoch": args.epochs,
                "seed_idx": seed_idx,
                "fold_idx": fold_idx,
                "acc": float(np.mean(fold_accs)),
                "auc": float(np.mean(fold_aucs)),
                "timestamp": time.time(),
            })

        seed_acc = float(np.mean(fold_accs))
        seed_auc = float(np.mean(fold_aucs))
        all_accs.append(seed_acc)
        all_aucs.append(seed_auc)
        logger.info(
            f"[{run_id}] Seed={seed} 均值: acc={seed_acc*100:.2f}% auc={seed_auc*100:.2f}%"
        )

        # 写当前 seed 结果到 csv
        import csv
        results_path.parent.mkdir(parents=True, exist_ok=True)
        header = ["run_id", "model", "atlas", "dataset", "seed", "test_acc", "test_auc",
                  "fid_pos", "fid_neg"]
        row = [run_id, model_name, atlas, dataset_name, seed,
               seed_acc, seed_auc, None, None]
        write_result_row(results_path, header, row)

    final_acc = float(np.mean(all_accs))
    final_auc = float(np.mean(all_aucs))
    logger.info(
        f"[{run_id}] === 最终结果: acc={final_acc*100:.2f}±{np.std(all_accs)*100:.2f}% "
        f"auc={final_auc*100:.2f}±{np.std(all_aucs)*100:.2f}% ==="
    )

    write_state(state_path, {
        "run_id": run_id,
        "status": "done",
        "model": model_name,
        "atlas": atlas,
        "dataset": dataset_name,
        "epoch": args.epochs,
        "acc": final_acc,
        "auc": final_auc,
        "timestamp": time.time(),
    })

    return {"acc": final_acc, "auc": final_auc}


def write_result_row(csv_path: Path, header: list, row: list):
    """追加写结果行（若文件不存在则写 header）"""
    import csv as csv_mod
    write_header = not csv_path.exists()
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv_mod.writer(f)
        if write_header:
            writer.writerow(header)
        writer.writerow(row)


def main():
    parser = argparse.ArgumentParser(
        description="HyperFidBench Gate1 BrainGB 训练封装（run-01 GCN / run-02 GAT / run-05 multiatlas）"
    )
    parser.add_argument(
        "--run_id",
        type=str,
        default="run-01-braingb-gcn-cc200",
        help="实验 ID（写入结果 csv）",
    )
    parser.add_argument(
        "--model_name",
        type=str,
        default="gcn",
        choices=["gcn", "gat"],
        help="模型，gcn=run-01/05, gat=run-02",
    )
    parser.add_argument(
        "--dataset_name",
        type=str,
        default="ABIDE",
        choices=["ABIDE"],
        help="数据集（Gate1 BrainGB 泳道仅 ABIDE）",
    )
    parser.add_argument(
        "--atlas",
        type=str,
        default="cc200",
        help="Atlas 标签（写入 csv，实际数据已由 build_graphs.py 按 atlas 构建好）",
    )
    parser.add_argument(
        "--seeds",
        type=int,
        nargs="+",
        default=[0, 1, 2],
        help="运行的随机种子列表，默认 [0, 1, 2]",
    )
    # 官方超参（argparse 默认值照搬 BrainGB example_main.py，不改）
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--weight_decay", type=float, default=1e-4)
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--hidden_dim", type=int, default=360)
    parser.add_argument("--n_GNN_layers", type=int, default=2)
    parser.add_argument("--n_MLP_layers", type=int, default=1)
    parser.add_argument("--dropout", type=float, default=0.5)
    parser.add_argument("--train_batch_size", type=int, default=16)
    parser.add_argument("--test_batch_size", type=int, default=16)
    parser.add_argument("--k_fold_splits", type=int, default=5)
    parser.add_argument("--gcn_mp_type", type=str, default="weighted_sum")
    parser.add_argument("--gat_mp_type", type=str, default="attention_weighted")
    parser.add_argument("--num_heads", type=int, default=2)
    parser.add_argument("--pooling", type=str, default="concat")
    parser.add_argument("--node_features", type=str, default="adj")
    parser.add_argument("--mixup", type=int, default=1)
    parser.add_argument("--test_interval", type=int, default=5)
    parser.add_argument(
        "--output_dir",
        type=str,
        default=str(RESULTS_DIR),
        help="结果输出目录（含 braingb_results.csv 和 state.json）",
    )
    # smoke test 入口（最小 forward 不训练）
    parser.add_argument(
        "--smoke",
        type=int,
        default=0,
        help="smoke=1: 只跑 1 fold × 1 epoch × seed=0，验证算子不报错（主线跑）",
    )

    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    state_path = output_dir / "state.json"
    results_path = output_dir / "braingb_results.csv"

    if args.smoke:
        logger.info("=== SMOKE MODE: 1 fold, 1 epoch, seed=0 ===")
        args.epochs = 1
        args.k_fold_splits = 2
        seeds = [0]
    else:
        seeds = args.seeds

    # 构造 BrainGB args（分离出去，方便 pytest mock）
    braingb_args = build_braingb_args(
        model_name=args.model_name,
        dataset_name=args.dataset_name,
        node_features=args.node_features,
        pooling=args.pooling,
        gcn_mp_type=args.gcn_mp_type,
        gat_mp_type=args.gat_mp_type,
        num_heads=args.num_heads,
        n_GNN_layers=args.n_GNN_layers,
        n_MLP_layers=args.n_MLP_layers,
        hidden_dim=args.hidden_dim,
        dropout=args.dropout,
        lr=args.lr,
        weight_decay=args.weight_decay,
        epochs=args.epochs,
        train_batch_size=args.train_batch_size,
        test_batch_size=args.test_batch_size,
        k_fold_splits=args.k_fold_splits,
        seed=seeds[0],
        test_interval=args.test_interval,
        mixup=args.mixup,
    )

    run_experiment(
        run_id=args.run_id,
        model_name=args.model_name,
        dataset_name=args.dataset_name,
        atlas=args.atlas,
        seeds=seeds,
        args=braingb_args,
        state_path=state_path,
        results_path=results_path,
    )


if __name__ == "__main__":
    main()
