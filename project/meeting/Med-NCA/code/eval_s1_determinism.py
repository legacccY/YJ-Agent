"""S1 (验收项 B): 确定性 eval 复跑。
同 config 同 seed=42 重跑 R1 single 推理，与冻结的 r1_hippocampus_single.csv
逐 patient 比对 → max abs diff < 1e-4 即确定性 eval 可复跑 PASS。
不覆盖冻结 csv，结果另写 results/s1_determinism_summary.json。
"""
import os, sys, json, csv, subprocess
import numpy as np
import torch

SEED = 42
np.random.seed(SEED)
torch.manual_seed(SEED)

def git_commit():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=r"D:\YJ-Agent", stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "unknown"

ROOT = r"D:\YJ-Agent\project\meeting\Med-NCA"
OFFICIAL = os.path.join(ROOT, "M3D-NCA-official")

# --- 先读冻结 csv 作参照（在 os.chdir 之前用绝对路径）---
FROZEN_CSV = os.path.join(ROOT, "results", "r1_official_single.csv")
frozen = {}
with open(FROZEN_CSV, newline="") as f:
    for row in csv.DictReader(f):
        frozen[row["patient_id"]] = float(row["dice"])
print(f"[S1] frozen reference: {len(frozen)} patients from {FROZEN_CSV}", flush=True)

sys.path.insert(0, OFFICIAL)
os.chdir(OFFICIAL)
from src.datasets.Nii_Gz_Dataset_3D import Dataset_NiiGz_3D
sys.path.insert(0, os.path.join(ROOT, "code"))
from src.models.Model_BackboneNCA import BackboneNCA
from src.utils.Experiment import Experiment
from src.agents.Agent_Med_NCA import Agent_Med_NCA

DEVICE = "cuda:0" if torch.cuda.is_available() else "cpu"
config = [{
    'img_path':   os.path.join(ROOT, "data", "Task04_Hippocampus", "imagesTr"),
    'label_path': os.path.join(ROOT, "data", "Task04_Hippocampus", "labelsTr"),
    'model_path': os.path.join(ROOT, "checkpoints", "r1_hippocampus_official"),
    'device': DEVICE, 'unlock_CPU': True,
    'lr': 16e-4, 'lr_gamma': 0.9999, 'betas': (0.5, 0.5),
    'save_interval': 50, 'evaluate_interval': 25,
    'n_epoch': 1500, 'batch_size': 40,
    'channel_n': 32, 'inference_steps': 16, 'cell_fire_rate': 0.5,
    'input_channels': 1, 'output_channels': 1, 'hidden_size': 128,
    'train_model': 1, 'input_size': [(16, 16), (64, 64)],
    'rescale': True,
    'data_split': [0.7, 0, 0.3],
}]

dataset = Dataset_NiiGz_3D(slice=2)
device = torch.device(config[0]['device'])
ca = [BackboneNCA(config[0]['channel_n'], config[0]['cell_fire_rate'], device,
                  hidden_size=config[0]['hidden_size'],
                  input_channels=config[0]['input_channels']).to(device) for _ in range(2)]
agent = Agent_Med_NCA(ca)
exp = Experiment(config, dataset, ca, agent)
dataset.set_experiment(exp)
exp.set_model_state('train')
commit = git_commit()
print(f"[S1] reload ckpt epochs={exp.currentStep}/{exp.get_max_steps()} device={DEVICE} commit={commit}", flush=True)

# single 推理（确定性，pseudo_ensemble=False）
loss_log = agent.getAverageDiceScore(pseudo_ensemble=False)
rerun = loss_log[0]  # {pid: dice}

# 逐 patient 比对
common = [p for p in frozen if p in rerun]
diffs = {p: abs(rerun[p] - frozen[p]) for p in common}
max_diff = max(diffs.values()) if diffs else float("nan")
mean_rerun = float(np.mean([rerun[p] for p in common]))
mean_frozen = float(np.mean([frozen[p] for p in common]))

THRESH = 1e-4
verdict = "PASS" if max_diff < THRESH else "FAIL"
summary = {
    "check": "S1_deterministic_eval",
    "n_compared": len(common),
    "n_frozen": len(frozen), "n_rerun": len(rerun),
    "max_abs_diff": max_diff,
    "mean_dice_rerun": round(mean_rerun, 6),
    "mean_dice_frozen": round(mean_frozen, 6),
    "threshold": THRESH, "verdict": verdict,
    "seed": SEED, "device": DEVICE, "git_commit": commit,
    "note": "single 推理 (pseudo_ensemble=False) 同 seed 复跑 vs 冻结 csv",
}
print(f"[S1] {json.dumps(summary)}", flush=True)
with open(os.path.join(ROOT, "results", "s1_determinism_summary.json"), "w") as f:
    json.dump(summary, f, indent=2)
print("[S1] done", flush=True)
