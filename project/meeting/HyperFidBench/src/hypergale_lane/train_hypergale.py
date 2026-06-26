"""
train_hypergale.py
==================
薄封装调用 vendor/HyperGALE，照官方超参跑 3 seeds，写 state.json + results CSV。

【偏离论文声明（红线合规注释）】
  HyperGALE 论文原用 ABIDE-II / Schaefer400 (400节点) / StratifiedShuffleSplit(site,42)。
  本脚本改用 ABIDE-I / CC200 (200节点) / BrainGB 同 split，原因：
    1. HPC 下载 ABIDE-I func_preproc 实测 0.08MB/s，43GB 需 6天，不可行。
    2. BrainGB 泳道已产出 CC200 FC，与 BrainGB 同 cohort/atlas/split，Gate2 纯比架构。
  fc.py L35 自动推断 node_sz = final_pearson.shape[1]（200），无需硬改 config。
  K_neigs=40 沿用论文值（TODO 注释标明待 Gate2 调参验证）。

【Split 策略（--split-csv 路径）】
  默认：vendor 内部 StratifiedShuffleSplit(site, seed=42)（论文设置）。
  推荐：--split-csv data/external/abide1_cc200/splits/split_cc200_5fold.csv
         --fold 0（或 1..4）
  指定 --split-csv 后 bypass vendor dataloader，用 make_split_cc200.py 产出的
  fc_idx 对齐 split，与 BrainGB 泳道完全同 patient-level split。

【官方入口】
  vendor/HyperGALE/__main__.py 用 @hydra.main 启动，repeat_time=10。
  本脚本绕过 Hydra CLI，直接用 OmegaConf 构建 cfg，以便：
  1. 固定 3 seeds（Gate1 协议：seed 0/1/2）。
  2. 关闭 wandb（offline 或 disabled 避免登录）。
  3. 写 state.json（/loop 监控所需）。
  4. 输出标准 CSV（run_id,model,atlas,dataset,seed,test_acc,test_auc,...）。

【官方超参（source/conf/ yaml 照搬，禁臆想）】
  lr=1e-5, base_lr=1e-4, target_lr=1e-5, weight_decay=1e-4
  poly scheduler, power=2, milestones=[0.3,0.6,0.9]
  epochs=200, hidden=64, num_layers=1, dropout=0.5, batch=16, Adam
  K_neigs=40  # TODO: 论文用 Schaefer400(400节点)，cc200(200节点)下 k=40 覆盖率翻倍，
              # 待 Gate2 消融 k=10/20/40。此处保留 k=40 不臆改。
  node_sz/node_feature_sz: fc.py 自动推断，200 节点不需硬改 config
  node feat=fc（FC 行向量，cc200 时 200 维）
  split: StratifiedShuffleSplit(test_size=0.1, random_state=42) on site（论文默认）
         或 --split-csv 外部 split（BrainGB 同 split 模式）

【Windows 规范（此脚本跑在 HPC Linux，但保留规范注释）】
  if __name__ == '__main__' 守门防 Windows spawn 重入。
  wandb 设为 disabled（不需登录，不影响训练）。
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

# ── vendor path 注入（HyperGALE 无 pip install，直接 sys.path 引）
_VENDOR_PATH = Path(__file__).resolve().parents[2] / "vendor" / "HyperGALE"
if str(_VENDOR_PATH) not in sys.path:
    sys.path.insert(0, str(_VENDOR_PATH))

import numpy as np
import torch
from omegaconf import OmegaConf, DictConfig, open_dict

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── 官方超参（source/conf/ yaml 照搬，禁臆想）
OFFICIAL_HYPERGALE_CONFIG = {
    # dataset（source/conf/dataset/fc_abide2.yaml）
    # "name"="fc_abide2" 是 vendor/HyperGALE dataset_factory 内部类名，不可改（与 cohort 无关）
    # fc.py L35 自动推断 node_sz = final_pearson.shape[1]，cc200 时自动变 200
    "dataset": {
        "name": "fc_abide2",
        "batch_size": 16,
        "train_set": 0.9,
        "test_set": 0.1,
        "fc_path": "PLACEHOLDER",  # 运行时填
        "node_sz": 200,            # cc200 默认（fc.py 会自动覆盖为实际值）
        "node_feature_sz": 200,    # cc200 默认（fc.py 会自动覆盖为实际值）
        "num_classes": 2,
        "perc_edges": 100,
        "node": "fc",
    },
    # model（source/conf/model/hypergale.yaml）
    "model": {
        "name": "HyperGALE",
        "data_creation": "hypergraph",
        "K_neigs": 40,       # 官方值（Schaefer400 400节点）
        # TODO: cc200(200节点) 下 k=40 覆盖率 20.5%（原 10.25%），待 Gate2 消融
        "num_layers": 1,
        "hidden_size": 64,
        "dropout": 0.5,
        "readout": "linear",
        "model_save": True,  # 保存 best model 供 Gate2 XAI 用
    },
    # optimizer（source/conf/optimizer/adam.yaml）
    "optimizer": [
        {
            "name": "Adam",
            "lr": 1.0e-5,
            "match_rule": None,
            "except_rule": None,
            "no_weight_decay": False,
            "weight_decay": 1.0e-4,
            "lr_scheduler": {
                "mode": "poly",
                "base_lr": 1.0e-4,
                "target_lr": 1.0e-5,
                "decay_factor": 0.1,
                "exp_decay_factor": 0.001,
                "milestones": [0.3, 0.6, 0.9],
                "poly_power": 2.0,
                "lr_decay": 0.98,
                "warm_up_from": 0.0,
                "warm_up_steps": 0,
            },
        }
    ],
    # training（source/conf/training/train.yaml）
    "training": {
        "name": "Train",
        "epochs": 200,
        "l2": 0.0,
    },
    # top-level（source/conf/config.yaml）
    "device": "cuda:0",
    "repeat_time": 1,   # 本脚本外循环控制 seed，每次 repeat=1
    "log_path": "result",
    "is_wandb": False,  # 关闭 wandb
}

# 结果 CSV 列（与 BrainGB 泳道对齐）
RESULT_COLS = [
    "run_id", "model", "atlas", "dataset", "seed", "fold",
    "test_acc", "test_auc", "fid_pos", "fid_neg",
]

_ROOT = Path(__file__).resolve().parents[2]
# ── 【偏离论文声明】cohort 换 ABIDE-I CC200（原论文 ABIDE-II Schaefer400）
# 路径由 build_fc_cc200_from_braingb.py 产出，HPC 上用 --fc-path 覆盖
DEFAULT_FC_PATH    = _ROOT / "data" / "external" / "abide1_cc200" / "fc_large_data_cc200.npy"
DEFAULT_OUTPUT_DIR = _ROOT / "results" / "hypergale"
DEFAULT_STATE_JSON = DEFAULT_OUTPUT_DIR / "state.json"


def build_cfg(fc_path: Path, device: str, seed: int) -> DictConfig:
    """
    从官方超参字典构建 Hydra-compatible OmegaConf DictConfig。
    fc.py L35 会覆盖 node_sz/node_feature_sz 为实际 FC 维度，无需手动对齐。
    """
    model_cfg = {
        "name": "HyperGALE",
        "data_creation": "hypergraph",
        "K_neigs": 40,
        # TODO: k=40 是论文 Schaefer400 值，cc200(200节点) 下覆盖率翻倍，待 Gate2 调参验证
        "num_layers": 1,
        "hidden_size": 64,
        "dropout": 0.5,
        "readout": "linear",
        "model_save": True,
    }
    dataset_cfg = dict(OFFICIAL_HYPERGALE_CONFIG["dataset"])
    dataset_cfg["fc_path"] = str(fc_path)

    cfg_dict = {
        "dataset": dataset_cfg,
        "model": model_cfg,
        "optimizer": OFFICIAL_HYPERGALE_CONFIG["optimizer"],
        "training": OFFICIAL_HYPERGALE_CONFIG["training"],
        "device": device,
        "repeat_time": 1,
        "log_path": "result",
        "is_wandb": False,
    }

    cfg = OmegaConf.create(cfg_dict)
    cfg.optimizer = OmegaConf.create(OFFICIAL_HYPERGALE_CONFIG["optimizer"])
    return cfg


def build_dataloaders_from_split_csv(
    cfg: DictConfig,
    fc_path: Path,
    split_csv: Path,
    fold: int,
) -> list:
    """
    Bypass vendor StratifiedShuffleSplit，用外部 split CSV 切 train/test。

    策略：
      1. 读 fc_large_data_cc200.npy → 全量 graph_data_list
      2. 读 split_csv（make_split_cc200.py 产出）→ fc_idx + fold_N 列
      3. 按 fc_idx + fold_N 值切 train/test list
      4. 返回 [train_dataloader, test_dataloader]（与 vendor dataset_factory 接口一致）

    注：fc.py 的 load_fc_data 会自动更新 cfg.dataset.node_sz/node_feature_sz，
        这里直接调用它保持一致，然后用 construct_hyperaph.create_hypergraph_data。
    """
    import pandas as pd
    from source.dataset.fc import load_fc_data
    from source.dataset.construct_hyperaph import create_hypergraph_data
    from torch_geometric.loader import DataLoader

    logger.info("外部 split 模式: split_csv=%s, fold=%d", split_csv, fold)

    # 加载 FC 数据（同时更新 cfg.node_sz/node_feature_sz）
    final_pearson, labels, site = load_fc_data(cfg)
    N = final_pearson.shape[0]
    logger.info("FC 数据: N=%d, node_sz=%d", N, cfg.dataset.node_sz)

    # 构建全量超图 data list
    graph_data_list, site_out = create_hypergraph_data(cfg, final_pearson, labels, site)

    # 读 split CSV
    split_df = pd.read_csv(split_csv)
    fold_col = f"fold_{fold}"
    if fold_col not in split_df.columns:
        raise ValueError(
            f"split_csv 无 '{fold_col}' 列，实际列: {list(split_df.columns)}"
        )

    # fc_idx → split 映射（只保留在 [0, N) 范围内的有效行）
    valid_mask = (split_df["fc_idx"] >= 0) & (split_df["fc_idx"] < N)
    split_df = split_df[valid_mask].copy()

    train_fc_idx = split_df[split_df[fold_col] == "train"]["fc_idx"].tolist()
    test_fc_idx  = split_df[split_df[fold_col] == "test"]["fc_idx"].tolist()

    logger.info(
        "Split fold_%d: train=%d, test=%d (fc_idx aligned)",
        fold, len(train_fc_idx), len(test_fc_idx),
    )

    train_list = [graph_data_list[i] for i in train_fc_idx]
    test_list  = [graph_data_list[i] for i in test_fc_idx]

    train_dataloader = DataLoader(
        train_list, batch_size=cfg.dataset.batch_size, shuffle=True
    )
    test_dataloader = DataLoader(
        test_list, batch_size=cfg.dataset.batch_size, shuffle=False
    )

    # 填 cfg 的 steps_per_epoch / total_steps（lr scheduler 需要）
    train_length = len(train_list)
    with open_dict(cfg):
        cfg.steps_per_epoch = (train_length - 1) // cfg.dataset.batch_size + 1
        cfg.total_steps = cfg.steps_per_epoch * cfg.training.epochs

    logger.info(
        "steps_per_epoch=%d, total_steps=%d",
        cfg.steps_per_epoch, cfg.total_steps,
    )
    return [train_dataloader, test_dataloader]


def set_seed(seed: int) -> None:
    """设置全局随机种子，保证可复现。"""
    import random
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)


def write_state(state_path: Path, state: dict) -> None:
    """写 state.json（/loop 监控所需）。"""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)


def run_one_seed(
    fc_path: Path,
    seed: int,
    device: str,
    output_dir: Path,
    state_path: Path,
    split_csv: Path = None,
    fold: int = 0,
) -> dict:
    """
    单 seed 完整训练。
    split_csv=None → 走 vendor 内部 StratifiedShuffleSplit（论文默认）。
    split_csv=Path → bypass vendor，用外部 fc_idx split（BrainGB 同 split 模式）。
    返回 result dict: {seed, fold, test_acc, test_auc, ckpt}
    """
    from source.models import model_factory
    from source.components import optimizers_factory, lr_scheduler_factory
    from source.training import training_factory

    set_seed(seed)
    logger.info("=== Seed %d, Fold %d ===", seed, fold)

    cfg = build_cfg(fc_path=fc_path, device=device, seed=seed)

    # model save 路径（按 seed+fold 区分）
    ckpt_path = output_dir / f"best_model_seed{seed}_fold{fold}.pt"

    # ── dataloader（两种模式）
    if split_csv is not None and split_csv.exists():
        dataloaders = build_dataloaders_from_split_csv(
            cfg=cfg, fc_path=fc_path, split_csv=split_csv, fold=fold
        )
    else:
        # 论文默认：vendor StratifiedShuffleSplit(site, seed=42)
        if split_csv is not None:
            logger.warning("--split-csv %s 不存在，回退到 vendor 内部 split", split_csv)
        from source.dataset import dataset_factory
        dataloaders = dataset_factory(cfg)

    model = model_factory(cfg)
    logger.info("Model: %s, node_sz=%d", cfg.model.name, cfg.dataset.node_sz)

    optimizers   = optimizers_factory(model=model, optimizer_configs=cfg.optimizer)
    lr_schedulers = lr_scheduler_factory(lr_configs=cfg.optimizer, cfg=cfg)
    trainer = training_factory(
        cfg=cfg,
        model=model,
        optimizers=optimizers,
        lr_schedulers=lr_schedulers,
        dataloaders=dataloaders,
    )

    with open_dict(cfg):
        cfg.model.model_save = True

    # trainer 用相对路径保存 best_model.pt → 切换 cwd 到 output_dir
    _orig_dir = os.getcwd()
    output_dir.mkdir(parents=True, exist_ok=True)
    os.chdir(str(output_dir))

    try:
        trainer.train()
    finally:
        os.chdir(_orig_dir)

    # 重命名 best_model.pt → best_model_seed{seed}_fold{fold}.pt
    src = output_dir / "best_model.pt"
    if src.exists() and src != ckpt_path:
        src.rename(ckpt_path)
        logger.info("Checkpoint → %s", ckpt_path)

    best_acc = trainer.best_test_metrics["accuracy"]
    best_auc = trainer.best_test_metrics["auc"]

    logger.info(
        "Seed %d Fold %d 完成: best_acc=%.4f, best_auc=%.4f",
        seed, fold, best_acc, best_auc,
    )
    return {
        "seed": seed,
        "fold": fold,
        "test_acc": float(best_acc),
        "test_auc": float(best_auc),
        "ckpt": str(ckpt_path),
    }


def main(
    fc_path: Path,
    seeds: list,
    device: str,
    output_dir: Path,
    state_path: Path,
    smoke: bool = False,
    split_csv: Path = None,
    fold: int = 0,
) -> None:
    """
    主训练循环（3 seeds，对应 Gate1 run-03）。
    """
    import csv

    if smoke:
        logger.info("=== SMOKE MODE: epochs=1, seeds=[0] ===")
        seeds = [0]

    output_dir.mkdir(parents=True, exist_ok=True)
    result_csv = output_dir / "results_hypergale.csv"

    # atlas 标签（cc200 路线）
    atlas_label   = "CC200"     # 偏离论文 Schaefer400，原因见顶部注释
    dataset_label = "ABIDE-I"   # 偏离论文 ABIDE-II，原因见顶部注释
    split_mode    = f"BrainGB_fold{fold}" if (split_csv and split_csv.exists()) else "vendor_site_stratified"

    # 初始 state
    write_state(state_path, {
        "status": "running",
        "model": "HyperGALE",
        "dataset": dataset_label,
        "atlas": atlas_label,
        "split_mode": split_mode,
        "fold": fold,
        "seeds": seeds,
        "start_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "results": [],
    })

    all_results = []

    for seed in seeds:
        write_state(state_path, {
            "status": "running",
            "current_seed": seed,
            "fold": fold,
            "completed_seeds": [r["seed"] for r in all_results],
            "results": all_results,
        })

        if smoke:
            # source/training/__init__.py 有 `from .Train import Train`，使
            # source.training.Train 被 shadow 成类(非 module)→ 直接从 package 拿类
            from source.training import Train as TrainClass
            _orig_init = TrainClass.__init__

            def _smoke_init(self, cfg, model, optimizers, lr_schedulers, dataloaders):
                _orig_init(self, cfg, model, optimizers, lr_schedulers, dataloaders)
                self.epochs = 1  # smoke: 1 epoch

            TrainClass.__init__ = _smoke_init
            logger.info("[smoke] epochs patched to 1")

        result = run_one_seed(
            fc_path=fc_path,
            seed=seed,
            device=device,
            output_dir=output_dir,
            state_path=state_path,
            split_csv=split_csv,
            fold=fold,
        )
        all_results.append(result)

    # 写 CSV（标准列）
    with open(result_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=RESULT_COLS)
        writer.writeheader()
        for r in all_results:
            writer.writerow({
                "run_id":    f"run-03-hypergale-cc200-fold{fold}",
                "model":     "HyperGALE",
                "atlas":     atlas_label,
                "dataset":   dataset_label,
                "seed":      r["seed"],
                "fold":      r["fold"],
                "test_acc":  f"{r['test_acc']:.4f}",
                "test_auc":  f"{r['test_auc']:.4f}",
                "fid_pos":   "NA",  # Gate2 填
                "fid_neg":   "NA",
            })

    # 汇总统计
    accs = [r["test_acc"] for r in all_results]
    aucs = [r["test_auc"] for r in all_results]
    logger.info(
        "=== 汇总 ===\n"
        "  test_acc: mean=%.4f, std=%.4f, values=%s\n"
        "  test_auc: mean=%.4f, std=%.4f, values=%s",
        np.mean(accs), np.std(accs), [f"{a:.4f}" for a in accs],
        np.mean(aucs), np.std(aucs), [f"{a:.4f}" for a in aucs],
    )
    logger.info("结果 CSV → %s", result_csv)

    # 最终 state
    write_state(state_path, {
        "status": "done",
        "model": "HyperGALE",
        "dataset": dataset_label,
        "atlas": atlas_label,
        "split_mode": split_mode,
        "fold": fold,
        "seeds": seeds,
        "results": all_results,
        "summary": {
            "acc_mean": float(np.mean(accs)),
            "acc_std":  float(np.std(accs)),
            "auc_mean": float(np.mean(aucs)),
            "auc_std":  float(np.std(aucs)),
        },
        "result_csv": str(result_csv),
        "end_time": time.strftime("%Y-%m-%d %H:%M:%S"),
    })

    # Gate1 判据检查
    # 改 CC200/ABIDE-I 后预期与 BrainGB CC200 接近（65-70% 范围）
    # 判据：acc > 65%（保守下界），非发散（> 55%）
    # 注意 accs 是百分比(如 64.98)，阈值用 65.0 不是 0.65（曾 bug: 53>0.65 永远假 PASS）
    gate1_pass = np.mean(accs) > 65.0
    logger.info(
        "Gate1 判定 [CC200/ABIDE-I]: acc_mean=%.4f %s 65.0 → %s",
        np.mean(accs), ">" if gate1_pass else "<=",
        "PASS" if gate1_pass else "WARN（低于预期，检查实现 / 考虑 k 调参）",
    )


def parse_args():
    p = argparse.ArgumentParser(
        description="训练 HyperGALE on ABIDE-I CC200（BrainGB 同 cohort/atlas/split）"
    )
    p.add_argument(
        "--fc-path", type=Path, default=DEFAULT_FC_PATH,
        help="fc_large_data_cc200.npy 路径（build_fc_cc200_from_braingb.py 产出）",
    )
    p.add_argument(
        "--split-csv", type=Path, default=None,
        help=(
            "外部 split CSV（make_split_cc200.py 产出，含 fc_idx+fold_N 列）。"
            "指定后 bypass vendor StratifiedShuffleSplit，走 BrainGB 同 split。"
            "不指定则走 vendor 内部 site-stratified split（论文默认）。"
        ),
    )
    p.add_argument(
        "--fold", type=int, default=0,
        help="用 split_csv 的哪一 fold（0-4，默认 0）。--split-csv 未指定时忽略。",
    )
    p.add_argument(
        "--seeds", type=int, nargs="+", default=[0, 1, 2],
        help="随机种子列表（默认 0 1 2）",
    )
    p.add_argument(
        "--device", default="cuda:0",
        help="PyTorch device（默认 cuda:0）",
    )
    p.add_argument(
        "--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
        help="结果输出目录",
    )
    p.add_argument(
        "--state-json", type=Path, default=DEFAULT_STATE_JSON,
        help="state.json 路径（/loop 监控）",
    )
    p.add_argument(
        "--smoke", type=int, default=0,
        help="smoke=1 时跑 1 epoch + seed=0 验算子（不用于判据）",
    )
    return p.parse_args()


if __name__ == "__main__":
    # Windows spawn 守门：必须在此块内启动
    args = parse_args()

    if not args.fc_path.exists():
        logger.error(
            "fc_large_data_cc200.npy 不存在: %s\n"
            "请先运行:\n"
            "  python src/hypergale_lane/build_fc_cc200_from_braingb.py \\\n"
            "      --abide-npy vendor/BrainGB/examples/datasets/ABIDE/abide.npy \\\n"
            "      --output    data/external/abide1_cc200/fc_large_data_cc200.npy",
            args.fc_path,
        )
        sys.exit(1)

    main(
        fc_path=args.fc_path,
        seeds=args.seeds,
        device=args.device,
        output_dir=args.output_dir,
        state_path=args.state_json,
        smoke=bool(args.smoke),
        split_csv=args.split_csv,
        fold=args.fold,
    )
