"""R1 官方版收口 eval-only（零偏离 ch32/steps16/rescale + 官方 BackboneNCA）。
冻结官方 anchor：single / pseudo10 per-volume Dice + bootstrap 95% CI + R4。
⚠️ 必须在 R1 训练【停止后】运行（Experiment reload 最新 ckpt；训练中跑会读到半写 ckpt）。
输出 r1_official_* 不覆盖旧 fast 版（r1_hippocampus_*）。
用法：python code/finalize_r1_official.py
"""
import os, sys, json, csv, subprocess
import numpy as np
import torch

SEED = 42
np.random.seed(SEED); torch.manual_seed(SEED)

def git_commit():
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"],
            cwd=r"D:\YJ-Agent", stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "unknown"

ROOT = r"D:\YJ-Agent\project\meeting\Med-NCA"
OFFICIAL = os.path.join(ROOT, "M3D-NCA-official")
sys.path.insert(0, OFFICIAL); os.chdir(OFFICIAL)

from src.datasets.Nii_Gz_Dataset_3D import Dataset_NiiGz_3D
from src.models.Model_BackboneNCA import BackboneNCA   # 官方原版（CPU rand，零偏离）
from src.utils.Experiment import Experiment
from src.agents.Agent_Med_NCA import Agent_Med_NCA

DEVICE = "cuda:0" if torch.cuda.is_available() else "cpu"

# 官方 hippocampus config.dt 全套（与 run_r1_hippocampus.py 一致）
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
    'train_model': 1,
    'input_size': [(16, 16), (64, 64)],
    'rescale': True,
    'data_split': [0.7, 0, 0.3],
}]

dataset = Dataset_NiiGz_3D(slice=2)
device = torch.device(config[0]['device'])
ca1 = BackboneNCA(config[0]['channel_n'], config[0]['cell_fire_rate'], device,
                  hidden_size=config[0]['hidden_size'], input_channels=config[0]['input_channels']).to(device)
ca2 = BackboneNCA(config[0]['channel_n'], config[0]['cell_fire_rate'], device,
                  hidden_size=config[0]['hidden_size'], input_channels=config[0]['input_channels']).to(device)
ca = [ca1, ca2]
agent = Agent_Med_NCA(ca)
exp = Experiment(config, dataset, ca, agent)   # reload 最新 ckpt + data_split.dt
dataset.set_experiment(exp)
exp.set_model_state('train')

n_params = sum(p.numel() for m in ca for p in m.parameters())
epochs_target = exp.get_max_steps()
epochs_trained = exp.currentStep
commit = git_commit()
print(f"[R1-official] reload ckpt: epochs_trained={epochs_trained}/{epochs_target} "
      f"params={n_params} (expect 70016) commit={commit} device={DEVICE}", flush=True)

def bootstrap_ci(vals, n=1000, seed=0):
    rng = np.random.default_rng(seed)
    vals = np.asarray(vals, dtype=float)
    means = [rng.choice(vals, len(vals), replace=True).mean() for _ in range(n)]
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))

per = {}
for ens, tag in [(False, "single"), (True, "pseudo10")]:
    ch0 = agent.getAverageDiceScore(pseudo_ensemble=ens)[0]
    per[tag] = ch0
    vals = list(ch0.values())
    mean, std = float(np.mean(vals)), float(np.std(vals))
    lo, hi = bootstrap_ci(vals)
    with open(os.path.join(ROOT, "results", f"r1_official_{tag}.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["patient_id", "dice", "seed", "git_commit"])
        for pid, d in ch0.items(): w.writerow([pid, d, SEED, commit])
    summary = {"tag": tag, "impl": "official_BackboneNCA", "config": "ch32_steps16_rescale",
               "n": len(vals), "dice_mean": round(mean, 4), "dice_std": round(std, 4),
               "ci95": [round(lo, 4), round(hi, 4)], "paper_target": 0.886,
               "threshold": 0.86, "verdict": "PASS" if mean >= 0.86 else "FAIL",
               "epochs_target": epochs_target, "epochs_trained": epochs_trained,
               "params": n_params, "seed": SEED, "git_commit": commit}
    print(f"[R1-official-{tag}] {json.dumps(summary)}", flush=True)
    with open(os.path.join(ROOT, "results", f"r1_official_{tag}_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

# R4 official
pids = [p for p in per["single"] if p in per["pseudo10"]]
diffs = np.array([per["pseudo10"][p] - per["single"][p] for p in pids], dtype=float)
lo, hi = bootstrap_ci(diffs)
r4 = {"impl": "official", "mean_diff": float(diffs.mean()),
      "ci95": [round(lo, 6), round(hi, 6)], "n_pairs": len(pids),
      "verdict": "PASS" if lo > 0 else "FAIL",
      "epochs_trained": epochs_trained, "seed": SEED, "git_commit": commit}
print(f"[R4-official] {json.dumps(r4)}", flush=True)
with open(os.path.join(ROOT, "results", "r4_official_summary.json"), "w") as f:
    json.dump(r4, f, indent=2)
print("\n[DONE] R1 官方 anchor 冻结。下一步：重算 C1(steps16)/V1/V2/efficiency 用官方 ckpt → 替换报告。", flush=True)
