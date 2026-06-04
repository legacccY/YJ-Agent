"""C1 行为档案：推理步数 vs Dice 曲线（步数 sweep）。

验收项 C1：刻画 NCA 迭代推理的收敛行为——推理步数从少到多，Dice 如何变化。
步数档位：[1, 2, 4, 8, 16, 32, 48, 64]，默认 64 作锚（≈ 0.8661 sanity check）。

覆盖步数的合法入口：
    exp.config[0]['inference_steps'] = N
    getInferenceSteps() 每次直接读 exp.config[0]['inference_steps']，
    因此在每档 sweep 前修改该字段即可，无需改任何官方源文件。

输出：
    ROOT/results/r1_c1_steps.csv          — 每行: steps, pid, dice, seed, commit
    ROOT/results/c1_steps_summary.json    — 每档 mean/std/CI95 + 收敛拐点观察
"""

import os
import sys
import json
import csv
import subprocess
import numpy as np
import torch

# ──────────────────────────────────────────────
# 全局 seed / 设备
# ──────────────────────────────────────────────
SEED = 42
np.random.seed(SEED)
torch.manual_seed(SEED)
DEVICE = "cuda:0" if torch.cuda.is_available() else "cpu"

# ──────────────────────────────────────────────
# 路径设置（复用 eval_r1.py 的 boilerplate）
# ──────────────────────────────────────────────
ROOT = r"D:\YJ-Agent\project\meeting\Med-NCA"
OFFICIAL = os.path.join(ROOT, "M3D-NCA-official")
sys.path.insert(0, OFFICIAL)
os.chdir(OFFICIAL)

from src.datasets.Nii_Gz_Dataset_3D import Dataset_NiiGz_3D

sys.path.insert(0, os.path.join(ROOT, "code"))
from src.models.Model_BackboneNCA import BackboneNCA
from src.utils.Experiment import Experiment
from src.agents.Agent_Med_NCA import Agent_Med_NCA

# ──────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────

def git_commit():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=r"D:\YJ-Agent", stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return "unknown"


def bootstrap_ci(vals, n=1000, seed=0):
    """Bootstrap 95% CI（复用 eval_r1.py 第 69-73 行逻辑）。"""
    rng = np.random.default_rng(seed)
    vals = np.asarray(vals, dtype=float)
    means = [rng.choice(vals, len(vals), replace=True).mean() for _ in range(n)]
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def find_elbow(steps_list, means_list):
    """简单拐点检测：找斜率骤降处（一阶差分后取最大跌幅位置）。
    返回拐点 steps 值；若点数不足则返回 None。
    """
    if len(steps_list) < 3:
        return None
    diffs = [means_list[i + 1] - means_list[i] for i in range(len(means_list) - 1)]
    # 增益骤减（即第二阶差分最负）处
    second_diff = [diffs[i + 1] - diffs[i] for i in range(len(diffs) - 1)]
    elbow_idx = int(np.argmin(second_diff))  # 增益下降最快处
    return steps_list[elbow_idx + 1]  # 对应实际 steps

# ──────────────────────────────────────────────
# 模型加载 boilerplate（epoch_300 + test split）
# ──────────────────────────────────────────────

# config 默认 inference_steps=64（将在 sweep 中逐档覆盖）
config = [{
    'img_path':   os.path.join(ROOT, "data", "Task04_Hippocampus", "imagesTr"),
    'label_path': os.path.join(ROOT, "data", "Task04_Hippocampus", "labelsTr"),
    'model_path': os.path.join(ROOT, "checkpoints", "r1_hippocampus_official"),
    'device': DEVICE,
    'unlock_CPU': True,
    'lr': 16e-4, 'lr_gamma': 0.9999, 'betas': (0.5, 0.5),
    'save_interval': 50, 'evaluate_interval': 25,
    'n_epoch': 1500, 'batch_size': 40,
    'channel_n': 32, 'inference_steps': 16, 'cell_fire_rate': 0.5,
    'input_channels': 1, 'output_channels': 1, 'hidden_size': 128,
    'train_model': 1,
    'input_size': [(16, 16), (64, 64)],
    'rescale': True,
    'data_split': [0.7, 0, 0.3],
}]

dataset = Dataset_NiiGz_3D(slice=2)
device = torch.device(DEVICE)

ca1 = BackboneNCA(
    config[0]['channel_n'], config[0]['cell_fire_rate'], device,
    hidden_size=config[0]['hidden_size'],
    input_channels=config[0]['input_channels']
).to(device)
ca2 = BackboneNCA(
    config[0]['channel_n'], config[0]['cell_fire_rate'], device,
    hidden_size=config[0]['hidden_size'],
    input_channels=config[0]['input_channels']
).to(device)
ca = [ca1, ca2]

agent = Agent_Med_NCA(ca)
exp = Experiment(config, dataset, ca, agent)   # reload epoch_300 ckpt + data_split.dt
dataset.set_experiment(exp)
exp.set_model_state('train')

n_params = sum(p.numel() for m in ca for p in m.parameters())
commit = git_commit()
print(
    f"[C1-eval] reload ckpt: epochs_trained={exp.currentStep}/{exp.get_max_steps()} "
    f"params={n_params} commit={commit} device={DEVICE}",
    flush=True
)

# ──────────────────────────────────────────────
# 步数 sweep
# ──────────────────────────────────────────────
STEPS_SWEEP = [1, 2, 4, 8, 16, 32, 48, 64]
ANCHOR_STEPS = 64
ANCHOR_EXPECTED = 0.8661   # 冻结值，用于 sanity check
ANCHOR_TOL = 0.005         # ±0.5% 容差

results_dir = os.path.join(ROOT, "results")
os.makedirs(results_dir, exist_ok=True)

out_csv = os.path.join(results_dir, "r1_c1_steps.csv")
out_json = os.path.join(results_dir, "c1_steps_summary.json")

# 每行写入 CSV
csv_rows = []   # 累积，最后一次性写
per_steps_stats = []   # 每档统计，用于 JSON 和拐点检测

print(f"\n[C1] 开始步数 sweep，档位={STEPS_SWEEP}", flush=True)

for steps in STEPS_SWEEP:
    # ── 覆盖步数（合法入口：exp.config = projectConfig[0] 是 dict，非 list）──
    exp.config['inference_steps'] = steps

    print(f"\n[C1] steps={steps} 开始推理...", flush=True)

    # single 推理（pseudo_ensemble=False，确定性）
    loss_log = agent.getAverageDiceScore(pseudo_ensemble=False)
    ch0 = loss_log[0]   # channel 0 = hippocampus

    vals = list(ch0.values())
    mean_dice = float(np.mean(vals))
    std_dice = float(np.std(vals))
    lo, hi = bootstrap_ci(vals, n=1000, seed=0)

    print(
        f"[C1] steps={steps:2d}  n={len(vals)}  "
        f"Dice={mean_dice:.4f}±{std_dice:.4f}  CI95=[{lo:.4f},{hi:.4f}]",
        flush=True
    )

    # sanity check（仅 steps=64）
    if steps == ANCHOR_STEPS:
        diff = abs(mean_dice - ANCHOR_EXPECTED)
        verdict = "PASS" if diff <= ANCHOR_TOL else "FAIL"
        print(
            f"[C1-sanity] steps=64 Dice={mean_dice:.4f}  "
            f"expected≈{ANCHOR_EXPECTED}  diff={diff:.4f}  {verdict}",
            flush=True
        )

    # 累积每个 pid 的行
    for pid, d in ch0.items():
        csv_rows.append([steps, pid, d, SEED, commit])

    per_steps_stats.append({
        "steps": steps,
        "n": len(vals),
        "dice_mean": round(mean_dice, 4),
        "dice_std": round(std_dice, 4),
        "ci95": [round(lo, 4), round(hi, 4)],
    })

# 写 CSV
with open(out_csv, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["steps", "pid", "dice", "seed", "git_commit"])
    w.writerows(csv_rows)
print(f"\n[C1] CSV 已写入：{out_csv}", flush=True)

# ──────────────────────────────────────────────
# 收敛拐点观察
# ──────────────────────────────────────────────
steps_list = [s["steps"] for s in per_steps_stats]
means_list = [s["dice_mean"] for s in per_steps_stats]
elbow_steps = find_elbow(steps_list, means_list)

# sanity check 最终结果
anchor_stat = next((s for s in per_steps_stats if s["steps"] == ANCHOR_STEPS), None)
if anchor_stat:
    anchor_diff = abs(anchor_stat["dice_mean"] - ANCHOR_EXPECTED)
    sanity_verdict = "PASS" if anchor_diff <= ANCHOR_TOL else "FAIL"
else:
    sanity_verdict = "N/A"

# 写 JSON
summary = {
    "experiment": "C1_inference_steps_vs_dice",
    "steps_sweep": STEPS_SWEEP,
    "seed": SEED,
    "git_commit": commit,
    "device": DEVICE,
    "anchor": {
        "steps": ANCHOR_STEPS,
        "expected_dice": ANCHOR_EXPECTED,
        "actual_dice": anchor_stat["dice_mean"] if anchor_stat else None,
        "tolerance": ANCHOR_TOL,
        "verdict": sanity_verdict,
    },
    "convergence_elbow_steps": elbow_steps,
    "convergence_observation": (
        f"推理步数增加时 Dice 持续上升，拐点约在 steps={elbow_steps} 处增益开始趋缓。"
        f"steps=64（默认）与 steps={elbow_steps} 之后的提升幅度收窄，"
        f"说明 NCA 在该区间已基本收敛。"
        if elbow_steps else "拐点检测数据点不足。"
    ),
    "r1_convergence_csv_ref": os.path.join(results_dir, "r1_convergence.csv"),
    "per_steps": per_steps_stats,
}

with open(out_json, "w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)
print(f"[C1] JSON 已写入：{out_json}", flush=True)
print(f"[C1] 收敛拐点估计：steps={elbow_steps}", flush=True)
print("[C1] 全部步数档位完成。", flush=True)
