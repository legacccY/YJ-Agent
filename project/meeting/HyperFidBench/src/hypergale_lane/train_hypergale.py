"""
train_hypergale.py
==================
薄封装调用 vendor/HyperGALE，照官方超参跑 3 seeds，写 state.json + results CSV。

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
  K_neigs=40, num_edges=node_sz=400, readout=linear
  node feat=fc（FC 行向量，400 维）
  split: StratifiedShuffleSplit(test_size=0.1, random_state=42) on site

【Windows 规范】
  multiprocessing_context='spawn' 在 DataLoader 中（PyG DataLoader 默认无 worker，
  HyperGALE 未用 num_workers，默认 num_workers=0，spawn 无需额外设置）。
  if __name__ == '__main__' 守门防 Windows spawn 重入。
  wandb 设为 disabled（不需登录，不影响训练）。
"""

import argparse
import json
import logging
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

# ── 官方超参（source/conf/ yaml 照搬）
OFFICIAL_HYPERGALE_CONFIG = {
    # dataset（source/conf/dataset/fc_abide2.yaml）
    "dataset": {
        "name": "fc_abide2",
        "batch_size": 16,
        "train_set": 0.9,
        "test_set": 0.1,
        "fc_path": "PLACEHOLDER",  # 运行时填
        "node_sz": 400,
        "node_feature_sz": 400,
        "num_classes": 2,
        "perc_edges": 100,
        "node": "fc",
    },
    # model（source/conf/model/hypergale.yaml）
    "model": {
        "name": "HyperGALE",
        "data_creation": "hypergraph",
        "K_neigs": 40,       # 官方最优
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
    "model": {          # config.yaml 里 model 顶层覆盖
        "model_save": True,
    },
}

# 结果 CSV 列（与 BrainGB 泳道对齐）
RESULT_COLS = [
    "run_id", "model", "atlas", "dataset", "seed",
    "test_acc", "test_auc", "fid_pos", "fid_neg",
]

_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FC_PATH = _ROOT / "data" / "external" / "abide2" / "fc_large_data.npy"
DEFAULT_OUTPUT_DIR = _ROOT / "results" / "hypergale"
DEFAULT_STATE_JSON = DEFAULT_OUTPUT_DIR / "state.json"


def build_cfg(fc_path: Path, device: str, seed: int) -> DictConfig:
    """
    从官方超参字典构建 Hydra-compatible OmegaConf DictConfig。
    model 键在顶层 config 里有两处（top-level model_save + 详细 model），
    OmegaConf 需要合并处理。
    """
    # 合并 model（官方 config.yaml 里 defaults: model: hypergale，
    # 再在顶层 model: {model_save: False} 覆盖）
    model_cfg = {
        "name": "HyperGALE",
        "data_creation": "hypergraph",
        "K_neigs": 40,
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
        # steps_per_epoch / total_steps 由 dataloader 填入（open_dict）
    }

    cfg = OmegaConf.create(cfg_dict)
    # 结构化 optimizer 需为 list of DictConfig
    cfg.optimizer = OmegaConf.create(OFFICIAL_HYPERGALE_CONFIG["optimizer"])
    return cfg


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
) -> dict:
    """
    单 seed 完整训练。
    返回 result dict: {test_acc, test_auc, best_acc, best_auc}
    """
    from source.dataset import dataset_factory
    from source.models import model_factory
    from source.components import optimizers_factory, lr_scheduler_factory
    from source.training import training_factory

    set_seed(seed)
    logger.info("=== Seed %d ===", seed)

    cfg = build_cfg(fc_path=fc_path, device=device, seed=seed)

    # model save 路径（按 seed 区分）
    ckpt_path = output_dir / f"best_model_seed{seed}.pt"

    # dataloader（会填 steps_per_epoch / total_steps 进 cfg）
    dataloaders = dataset_factory(cfg)

    model = model_factory(cfg)
    logger.info("Model: %s", cfg.model.name)

    optimizers = optimizers_factory(model=model, optimizer_configs=cfg.optimizer)
    lr_schedulers = lr_scheduler_factory(lr_configs=cfg.optimizer, cfg=cfg)
    trainer = training_factory(
        cfg=cfg,
        model=model,
        optimizers=optimizers,
        lr_schedulers=lr_schedulers,
        dataloaders=dataloaders,
    )

    # 修改 model save 路径为 seed-specific
    with open_dict(cfg):
        cfg.model.model_save = True

    # 覆盖 trainer 的 loss_fn 的 model_save（trainer 自己保存 best_model.pt）
    # 让 trainer 保存到 seed-specific 路径：monkey-patch
    import os
    _orig_ckpt = "best_model.pt"
    _target_ckpt = str(ckpt_path)

    # trainer.train() 内调用 torch.save(model.state_dict(), 'best_model.pt')
    # 我们在当前目录为 output_dir，但 trainer 用相对路径
    # → 切换 cwd 到 output_dir（或直接 patch）
    _orig_dir = os.getcwd()
    output_dir.mkdir(parents=True, exist_ok=True)
    os.chdir(str(output_dir))

    try:
        trainer.train()
    finally:
        os.chdir(_orig_dir)

    # 重命名 best_model.pt → best_model_seed{seed}.pt
    src = output_dir / "best_model.pt"
    if src.exists() and src != ckpt_path:
        src.rename(ckpt_path)
        logger.info("Checkpoint 保存 → %s", ckpt_path)

    best_acc = trainer.best_test_metrics["accuracy"]
    best_auc = trainer.best_test_metrics["auc"]

    logger.info(
        "Seed %d 完成: best_acc=%.4f, best_auc=%.4f",
        seed, best_acc, best_auc,
    )
    return {
        "seed": seed,
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
) -> None:
    """
    主训练循环（3 seeds，对应 Gate1 run-03）。
    """
    import csv

    if smoke:
        # smoke test：改为 1 epoch，仅验算子不跑完整训练
        logger.info("=== SMOKE MODE: epochs=1, seeds=[0] ===")
        # 无法直接改 cfg.training.epochs（build_cfg 里 hardcode），
        # 用环境变量标记，train_per_epoch 里不支持提前退出
        # → smoke 只跑 seed=0，epochs 通过 monkey-patch
        seeds = [0]

    output_dir.mkdir(parents=True, exist_ok=True)
    result_csv = output_dir / "results_hypergale.csv"

    # 初始 state
    write_state(state_path, {
        "status": "running",
        "model": "HyperGALE",
        "dataset": "ABIDE-II",
        "atlas": "Schaefer400",
        "seeds": seeds,
        "start_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "results": [],
    })

    all_results = []

    for seed in seeds:
        # 更新 state
        write_state(state_path, {
            "status": "running",
            "current_seed": seed,
            "completed_seeds": [r["seed"] for r in all_results],
            "results": all_results,
        })

        if smoke:
            # smoke: monkey-patch epochs
            import source.training.Train as TrainMod
            _orig_init = TrainMod.Train.__init__

            def _smoke_init(self, cfg, model, optimizers, lr_schedulers, dataloaders):
                _orig_init(self, cfg, model, optimizers, lr_schedulers, dataloaders)
                self.epochs = 1  # smoke: 1 epoch

            TrainMod.Train.__init__ = _smoke_init
            logger.info("[smoke] epochs patched to 1")

        result = run_one_seed(
            fc_path=fc_path,
            seed=seed,
            device=device,
            output_dir=output_dir,
            state_path=state_path,
        )
        all_results.append(result)

    # 写 CSV（标准列）
    with open(result_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=RESULT_COLS)
        writer.writeheader()
        for r in all_results:
            writer.writerow({
                "run_id": "run-03-hypergale-schaefer",
                "model": "HyperGALE",
                "atlas": "Schaefer400",
                "dataset": "ABIDE-II",
                "seed": r["seed"],
                "test_acc": f"{r['test_acc']:.4f}",
                "test_auc": f"{r['test_auc']:.4f}",
                "fid_pos": "NA",  # Gate2 填
                "fid_neg": "NA",
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
        "dataset": "ABIDE-II",
        "atlas": "Schaefer400",
        "seeds": seeds,
        "results": all_results,
        "summary": {
            "acc_mean": float(np.mean(accs)),
            "acc_std": float(np.std(accs)),
            "auc_mean": float(np.mean(aucs)),
            "auc_std": float(np.std(aucs)),
        },
        "result_csv": str(result_csv),
        "end_time": time.strftime("%Y-%m-%d %H:%M:%S"),
    })

    # Gate1 判据检查（acc 65-70% 对齐文献，HyperGALE 论文报告 75.34%）
    # HyperGALE 在 ABIDE-II 实际高于 BrainGB（后者 ABIDE-I 65-70%）
    # 判据：acc > 65%（保守下界），非发散（acc > 55%）
    gate1_pass = np.mean(accs) > 0.65
    logger.info(
        "Gate1 判定: acc_mean=%.4f %s 0.65 → %s",
        np.mean(accs), ">" if gate1_pass else "<=",
        "PASS" if gate1_pass else "WARN（低于预期，检查实现）",
    )


def parse_args():
    p = argparse.ArgumentParser(description="训练 HyperGALE on ABIDE-II")
    p.add_argument("--fc-path", type=Path, default=DEFAULT_FC_PATH,
                   help="fc_large_data.npy 路径")
    p.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2],
                   help="随机种子列表（默认 0 1 2）")
    p.add_argument("--device", default="cuda:0",
                   help="PyTorch device（默认 cuda:0）")
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
                   help="结果输出目录")
    p.add_argument("--state-json", type=Path, default=DEFAULT_STATE_JSON,
                   help="state.json 路径（/loop 监控）")
    p.add_argument("--smoke", type=int, default=0,
                   help="smoke=1 时跑 1 epoch + seed=0 验算子（不用于判据）")
    return p.parse_args()


if __name__ == "__main__":
    # Windows spawn 守门：必须在此块内启动
    args = parse_args()

    if not args.fc_path.exists():
        logger.error(
            "fc_large_data.npy 不存在: %s\n"
            "请先运行:\n"
            "  python src/hypergale_lane/download_abide2.py\n"
            "  python src/hypergale_lane/build_fc_abide2.py",
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
    )
