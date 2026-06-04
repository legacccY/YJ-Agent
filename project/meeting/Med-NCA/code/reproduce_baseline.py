"""reproduce_baseline.py — E1「一键复跑脚本」

从冻结 checkpoint 做 eval-only 推理，复现论文 baseline 数字，
给审稿人 / 未来的自己一键重建地基的能力。

已支持实验：
  R1  Hippocampus   single 0.8661 / pseudo10 0.8669   (epoch_300 frozen)
  R2  Prostate      (预留，ckpt 不存在则跳过；论文 0.838±0.083)

用法：
  python code/reproduce_baseline.py            # 复现所有已训完的实验
  python code/reproduce_baseline.py --run R1   # 只跑 R1

输出：
  results/reproduce_check.json   — 汇总 MATCH/MISMATCH 记录
  stdout 每行形如：
    [REPRODUCE] R1 single: got 0.8661 vs frozen 0.8661 → MATCH
"""

import argparse
import csv
import json
import os
import subprocess
import sys

import numpy as np
import torch

# ── 全局设定 ──────────────────────────────────────────────────────────────────
SEED = 42
np.random.seed(SEED)
torch.manual_seed(SEED)

MATCH_TOL = 1e-3   # |got - frozen| < 1e-3 → MATCH

ROOT     = r"D:\YJ-Agent\project\meeting\Med-NCA"
OFFICIAL = os.path.join(ROOT, "M3D-NCA-official")
CODE_DIR = os.path.join(ROOT, "code")

# ── 冻结参考值（单一真源，人工维护）────────────────────────────────────────────
FROZEN = {
    "R1": {
        "single":   0.8661,
        "pseudo10": 0.8669,
        "epochs_trained": 301,   # eval_r1.py 产出的实际训练步数
        "params":   25920,
    },
    # R2 训练完成后在此补充冻结值
    "R2": {
        "single":   None,   # TBD
        "pseudo10": None,   # TBD
    },
}

# ── 数据集配置字典（扩展新实验只需在此添加一项）──────────────────────────────
DATASET_CONFIGS = {
    "R1": {
        "label":        "R1 Hippocampus",
        "csv_stem":     "r1_hippocampus",
        "dataset_type": "NiiGz",          # 控制 dataset 构造方式
        "img_path":     os.path.join(ROOT, "data", "Task04_Hippocampus", "imagesTr"),
        "label_path":   os.path.join(ROOT, "data", "Task04_Hippocampus", "labelsTr"),
        "model_path":   os.path.join(ROOT, "checkpoints", "r1_hippocampus"),
        "channel_n":    16,
        "cell_fire_rate": 0.5,
        "hidden_size":  128,
        "input_channels": 1,
        "output_channels": 1,
        "inference_steps": 64,
        "batch_size":   48,
        "n_epoch":      300,
        "input_size":   [(16, 16), (64, 64)],
        "data_split":   [0.7, 0, 0.3],
    },
    # R2 = Prostate (MSD Task05)。配置为官方实证（run_r2_prostate.py / train_Med_NCA.ipynb）：
    #   单模态 T2（ADC 截断）→ input_channels=1；整腺二值（label>0）→ output_channels=1；
    #   channel_n=32, input_size=[(64,64),(256,256)], batch=20, 2-stage。
    "R2": {
        "label":        "R2 Prostate",
        "csv_stem":     "r2_prostate",
        "dataset_type": "NiiGz",          # 3D nii，复用 R1 同款 dataset
        "img_path":     os.path.join(ROOT, "data", "Task05_Prostate", "imagesTr"),
        "label_path":   os.path.join(ROOT, "data", "Task05_Prostate", "labelsTr"),
        "model_path":   os.path.join(ROOT, "checkpoints", "r2_prostate"),
        "channel_n":    32,
        "cell_fire_rate": 0.5,
        "hidden_size":  128,
        "input_channels": 1,
        "output_channels": 1,
        "inference_steps": 64,
        "batch_size":   20,
        "n_epoch":      300,
        "input_size":   [(64, 64), (256, 256)],
        "data_split":   [0.7, 0, 0.3],
    },
}


# ── 工具函数 ──────────────────────────────────────────────────────────────────
def git_commit():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT, stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return "unknown"


def bootstrap_ci(vals, n=1000, seed=0):
    rng  = np.random.default_rng(seed)
    vals = np.asarray(vals, dtype=float)
    means = [rng.choice(vals, len(vals), replace=True).mean() for _ in range(n)]
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def ckpt_epoch_dir_exists(model_path):
    """检查 checkpoints/<run>/models/ 下是否有至少一个 epoch_* 子目录。"""
    models_dir = os.path.join(model_path, "models")
    if not os.path.isdir(models_dir):
        return False
    return any(
        d.startswith("epoch_") and os.path.isdir(os.path.join(models_dir, d))
        for d in os.listdir(models_dir)
    )


def verdict_line(run_id, tag, got, frozen):
    """打印并返回 MATCH/MISMATCH 字符串。"""
    if frozen is None:
        status = "FROZEN_NOT_SET"
    elif abs(got - frozen) < MATCH_TOL:
        status = "MATCH"
    else:
        status = "MISMATCH"
    frozen_str = f"{frozen:.4f}" if frozen is not None else "N/A"
    print(f"[REPRODUCE] {run_id} {tag}: got {got:.4f} vs frozen {frozen_str} → {status}",
          flush=True)
    return status


# ── 单次实验 eval ─────────────────────────────────────────────────────────────
def run_eval(run_id: str, cfg: dict, commit: str, results: list):
    """
    对 run_id（如 'R1'）做 eval-only 推理。
    - 构造模型，load Experiment（自动 reload 最新 ckpt + data_split.dt）
    - 算 single / pseudo10 per-image Dice + bootstrap 95% CI
    - 与 FROZEN 对比，输出 MATCH/MISMATCH
    - 结果追加进 results 列表，同时写 CSV summary
    """
    model_path = cfg["model_path"]
    label      = cfg["label"]

    # ── ckpt 存在性检查 ────────────────────────────────────────────────────────
    if not ckpt_epoch_dir_exists(model_path):
        print(f"[REPRODUCE] {run_id} ckpt not found, skipping  "
              f"(expected: {model_path}/models/epoch_*/)", flush=True)
        results.append({"run": run_id, "skipped": True,
                        "reason": "ckpt not found"})
        return

    print(f"\n[REPRODUCE] === {run_id} ({label}) ===", flush=True)

    # ── 构造 config list（Experiment 需要 list[dict]）────────────────────────
    exp_config = [{
        "img_path":         cfg["img_path"],
        "label_path":       cfg["label_path"],
        "model_path":       model_path,
        "device":           DEVICE,
        "unlock_CPU":       True,
        "lr":               16e-4,
        "lr_gamma":         0.9999,
        "betas":            (0.5, 0.5),
        "save_interval":    50,
        "evaluate_interval": 25,
        "n_epoch":          cfg["n_epoch"],
        "batch_size":       cfg["batch_size"],
        "channel_n":        cfg["channel_n"],
        "inference_steps":  cfg["inference_steps"],
        "cell_fire_rate":   cfg["cell_fire_rate"],
        "input_channels":   cfg["input_channels"],
        "output_channels":  cfg["output_channels"],
        "hidden_size":      cfg["hidden_size"],
        "train_model":      1,
        "input_size":       cfg["input_size"],
        "data_split":       cfg["data_split"],
    }]

    # ── 构造 dataset ───────────────────────────────────────────────────────────
    dataset_type = cfg.get("dataset_type", "NiiGz")
    if dataset_type == "NiiGz":
        from src.datasets.Nii_Gz_Dataset_3D import Dataset_NiiGz_3D
        dataset = Dataset_NiiGz_3D(slice=2)
    elif dataset_type == "ISIC2D":
        from dataset_isic2d import ISIC2D_RGB_Dataset
        dataset = ISIC2D_RGB_Dataset()
    else:
        raise ValueError(f"Unknown dataset_type: {dataset_type!r}")

    # ── 构造模型 + agent + Experiment ─────────────────────────────────────────
    device = torch.device(DEVICE)

    # 两个尺度各一个 BackboneNCA（与 run_r1_hippocampus.py / run_r2_isic.py 一致）
    ca1 = BackboneNCA(
        cfg["channel_n"], cfg["cell_fire_rate"], device,
        hidden_size=cfg["hidden_size"],
        input_channels=cfg["input_channels"],
    ).to(device)
    ca2 = BackboneNCA(
        cfg["channel_n"], cfg["cell_fire_rate"], device,
        hidden_size=cfg["hidden_size"],
        input_channels=cfg["input_channels"],
    ).to(device)
    ca    = [ca1, ca2]
    agent = Agent_Med_NCA(ca)

    # Experiment.__init__ 自动 reload 最新 ckpt + data_split.dt
    exp = Experiment(exp_config, dataset, ca, agent)
    dataset.set_experiment(exp)
    exp.set_model_state("train")   # 与 eval_r1.py 行为一致（set_model_state 内部切 eval 模式）

    n_params        = sum(p.numel() for m in ca for p in m.parameters())
    epochs_target   = exp.get_max_steps()
    epochs_trained  = exp.currentStep

    print(f"[REPRODUCE] {run_id} reload done: "
          f"epochs={epochs_trained}/{epochs_target}  "
          f"params={n_params}  commit={commit}  device={DEVICE}",
          flush=True)

    # ── per-image Dice + bootstrap CI ─────────────────────────────────────────
    os.makedirs(os.path.join(ROOT, "results"), exist_ok=True)
    run_lower = run_id.lower()
    run_record = {
        "run":          run_id,
        "label":        label,
        "skipped":      False,
        "epochs_target":  epochs_target,
        "epochs_trained": epochs_trained,
        "params":       n_params,
        "seed":         SEED,
        "git_commit":   commit,
        "tags":         {},
    }

    for ens, tag in [(False, "single"), (True, "pseudo10")]:
        loss_log = agent.getAverageDiceScore(pseudo_ensemble=ens)
        ch0  = loss_log[0]   # {patient_id: dice}
        vals = list(ch0.values())
        mean = float(np.mean(vals))
        std  = float(np.std(vals))
        lo, hi = bootstrap_ci(vals)

        # ── 写 CSV（与 eval_r1.py 格式相同，可覆盖历史文件）──────────────────
        out_csv = os.path.join(ROOT, "results",
                               f"{cfg.get('csv_stem', run_lower)}_{tag}.csv")
        with open(out_csv, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["patient_id", "dice", "seed", "git_commit"])
            for pid, d in ch0.items():
                w.writerow([pid, d, SEED, commit])

        # ── 与冻结值对比 ───────────────────────────────────────────────────────
        frozen_val = FROZEN.get(run_id, {}).get(tag)
        status     = verdict_line(run_id, tag, mean, frozen_val)

        run_record["tags"][tag] = {
            "n":          len(vals),
            "dice_mean":  round(mean, 4),
            "dice_std":   round(std, 4),
            "ci95":       [round(lo, 4), round(hi, 4)],
            "frozen_ref": frozen_val,
            "verdict":    status,
        }

    results.append(run_record)


# ── main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Med-NCA E1: eval-only baseline reproduction check")
    parser.add_argument("--run", nargs="*", default=list(DATASET_CONFIGS.keys()),
                        help="要复现的实验 ID，如 R1 R2（默认全部）")
    args = parser.parse_args()

    run_ids = [r.upper() for r in args.run]
    commit  = git_commit()
    print(f"[REPRODUCE] seed={SEED}  git_commit={commit}  device={DEVICE}",
          flush=True)
    print(f"[REPRODUCE] target runs: {run_ids}", flush=True)

    results = []
    for run_id in run_ids:
        if run_id not in DATASET_CONFIGS:
            print(f"[REPRODUCE] Unknown run_id={run_id!r}, skipping", flush=True)
            continue
        run_eval(run_id, DATASET_CONFIGS[run_id], commit, results)

    # ── 写汇总 JSON ───────────────────────────────────────────────────────────
    summary_path = os.path.join(ROOT, "results", "reproduce_check.json")
    os.makedirs(os.path.dirname(summary_path), exist_ok=True)
    out = {
        "seed":       SEED,
        "git_commit": commit,
        "tol":        MATCH_TOL,
        "runs":       results,
    }
    with open(summary_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\n[REPRODUCE] summary → {summary_path}", flush=True)

    # ── 终行汇总 ──────────────────────────────────────────────────────────────
    mismatches = [
        f"{r['run']}/{tag}"
        for r in results if not r.get("skipped")
        for tag, info in r.get("tags", {}).items()
        if info.get("verdict") == "MISMATCH"
    ]
    if mismatches:
        print(f"[REPRODUCE] DONE — MISMATCH items: {mismatches}", flush=True)
    else:
        print("[REPRODUCE] DONE — all checked items MATCH (or skipped)", flush=True)


# ── 路径 + 导入（在 if __main__ 外，使 run_eval 可被外部调用）─────────────────
#   必须在 sys.path 设好后才能 import，所以在模块顶层 import 段之后、main() 之前做。
sys.path.insert(0, OFFICIAL)
sys.path.insert(0, CODE_DIR)
os.chdir(OFFICIAL)   # official src.* 里有相对路径依赖

from src.utils.Experiment import Experiment          # noqa: E402
from src.agents.Agent_Med_NCA import Agent_Med_NCA  # noqa: E402
from fast_nca import FastBackboneNCA as BackboneNCA  # noqa: E402

DEVICE = "cuda:0" if torch.cuda.is_available() else "cpu"

if __name__ == "__main__":
    main()
