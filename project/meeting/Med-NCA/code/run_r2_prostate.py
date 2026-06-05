"""R2: Med-NCA (2D slice-wise) on MSD Task05 Prostate.

Architecture: same Med-NCA 2-stage coarse→fine as R1, using Agent_Med_NCA.
  - Stage 0 (coarse): input_size[0] = (64, 64), scale 1/4 of fine
  - Stage 1 (fine):   input_size[1] = (256, 256)
  - train_model = 1  →  range(train_model+1) = 2 stages

Dataset facts (from official Nii_Gz_Dataset_3D.py):
  - Prostate MSD Task05 has 2 modalities (T2+ADC, shape [..., 2]) but
    preprocessing3d line 67-68 and preprocessing line 51 both do img[..., 0]
    → SINGLE-CHANNEL input (T2 only), input_channels = 1
  - Labels have 2 foreground classes (PZ=1, TZ=2) but
    __getitem__ line 210 does label[label > 0] = 1
    → WHOLE-GLAND BINARY label, output_channels = 1

Prostate config source: train_Med_NCA.ipynb (official MECLabTUDA notebook),
  cell-5: channel_n=32, input_size=[(64,64),(256,256)], batch_size=20

PASS criterion (from Med-NCA IPMI 2023, arXiv 2302.03473, Table 1):
  - Bootstrap 95% CI for per-volume Dice mean contains 0.838, OR
  - Point estimate >= 0.81 AND > UNet baseline 0.799
"""
import os, sys, json, csv, time, subprocess
import numpy as np
import torch

SEED = int(os.environ.get("R2_SEED", "42"))   # 多 seed 脆弱性扫描；seed 非官方方法 config
np.random.seed(SEED)
torch.manual_seed(SEED)

def git_commit():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=r"D:\YJ-Agent", stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "unknown"

ROOT = os.environ.get("MEDNCA_ROOT", r"D:\YJ-Agent\project\meeting\Med-NCA")
OFFICIAL = os.path.join(ROOT, "M3D-NCA-official")
sys.path.insert(0, OFFICIAL)
os.chdir(OFFICIAL)  # src imports + relative paths

from src.datasets.Nii_Gz_Dataset_3D import Dataset_NiiGz_3D
sys.path.insert(0, os.path.join(ROOT, "code"))
from fast_nca import FastBackboneNCA                          # GPU-rand 提速版（math-equivalent，RNG 流不同）
from src.models.Model_BackboneNCA import BackboneNCA as OfficialBackboneNCA  # 官方原版（CPU rand）
from src.losses.LossFunctions import DiceBCELoss
from src.utils.Experiment import Experiment
from src.agents.Agent_Med_NCA import Agent_Med_NCA as OfficialAgent_Med_NCA  # 官方原版（无裁剪）
from agent_clip import ClipAgent_Med_NCA                       # 官方 + 梯度裁剪

# Respect CUDA_VISIBLE_DEVICES from environment
DEVICE = "cuda:0" if torch.cuda.is_available() else "cpu"
N_EPOCH = int(os.environ.get("R2_EPOCHS", "300"))   # paper uses 1000; start 300, extend if Dice < 0.81
# ---- 忠实/诊断开关（env 驱动；默认 = 官方精确配置零偏离）----
R2_LR = float(os.environ.get("R2_LR", "16e-4"))               # 官方 16e-4
R2_GRAD_CLIP = float(os.environ.get("R2_GRAD_CLIP", "0"))     # <=0 = 无裁剪（官方）；>0 = ClipAgent
R2_STEPS = int(os.environ.get("R2_STEPS", "64"))              # 官方 notebook 64（config.dt 存档为 16）
R2_MODEL_IMPL = os.environ.get("R2_MODEL_IMPL", "official")   # official=官方 CPU-rand；fast=GPU-rand 提速版
BackboneNCA = OfficialBackboneNCA if R2_MODEL_IMPL == "official" else FastBackboneNCA
# 独立 model_path 后缀：防污染/防踩 config.dt 陷阱
MODEL_TAG = os.environ.get("R2_MODEL_TAG", "r2_prostate")

# ---- R2 Prostate config ----
# Source: official train_Med_NCA.ipynb cell-5 (prostate notebook)
# Key differences vs R1 hippocampus:
#   channel_n: 16 → 32  (notebook specifies 32 for prostate)
#   input_size: [(16,16),(64,64)] → [(64,64),(256,256)]  (prostate images much larger)
#   batch_size: 48 → 20  (larger patch size needs less batch)
#   input_channels: 1 (same — only T2 modality used, despite 2-channel data)
#   output_channels: 1 (same — whole-gland binary, despite 2-class labels)
config = [{
    'img_path':   os.path.join(ROOT, "data", "Task05_Prostate", "imagesTr"),
    'label_path': os.path.join(ROOT, "data", "Task05_Prostate", "labelsTr"),
    'model_path': os.path.join(ROOT, "checkpoints", MODEL_TAG),
    'device': DEVICE,
    'unlock_CPU': True,
    'lr': R2_LR, 'lr_gamma': 0.9999, 'betas': (0.5, 0.5),
    'save_interval': 50, 'evaluate_interval': 25,
    'n_epoch': N_EPOCH, 'batch_size': 20,
    'channel_n': 32,           # prostate: 32 (vs hippocampus 16)
    'inference_steps': R2_STEPS, 'cell_fire_rate': 0.5,
    'input_channels': 1,       # single channel: T2 only (img[...,0] in preprocessing)
    'output_channels': 1,      # whole-gland binary (label[label>0]=1 in __getitem__)
    'hidden_size': 128,
    'train_model': 1,
    # coarse (64,64) → upscale 4x → fine (256,256)
    'input_size': [(64, 64), (256, 256)],
    'data_split': [0.7, 0, 0.3],
}]

print(f"[R2] device={DEVICE} epochs={N_EPOCH}", flush=True)

# slice=2: split along z-axis (axial), same as R1
dataset = Dataset_NiiGz_3D(slice=2)
device = torch.device(config[0]['device'])
ca1 = BackboneNCA(config[0]['channel_n'], config[0]['cell_fire_rate'], device,
                  hidden_size=config[0]['hidden_size'], input_channels=config[0]['input_channels']).to(device)
ca2 = BackboneNCA(config[0]['channel_n'], config[0]['cell_fire_rate'], device,
                  hidden_size=config[0]['hidden_size'], input_channels=config[0]['input_channels']).to(device)
ca = [ca1, ca2]
# clip>0 → 用带梯度裁剪的 ClipAgent；否则用官方原版 agent（零偏离）
if R2_GRAD_CLIP > 0:
    agent = ClipAgent_Med_NCA(ca)
    agent.grad_clip = R2_GRAD_CLIP
else:
    agent = OfficialAgent_Med_NCA(ca)
exp = Experiment(config, dataset, ca, agent)
dataset.set_experiment(exp)
exp.set_model_state('train')
print(f"[R2] impl={R2_MODEL_IMPL} steps={R2_STEPS} lr={R2_LR} "
      f"grad_clip={R2_GRAD_CLIP} agent={type(agent).__name__} model_tag={MODEL_TAG}", flush=True)

# R3: parameter count check (<100K)
n_params = sum(p.numel() for m in ca for p in m.parameters())
print(f"[R3] total params = {n_params} ({'PASS <100K' if n_params < 1e5 else 'WARN >=100K (prostate uses channel_n=32)'})", flush=True)

loader = torch.utils.data.DataLoader(dataset, shuffle=True, batch_size=exp.get_from_config('batch_size'))
loss_function = DiceBCELoss()

t0 = time.time()
agent.train(loader, loss_function)
print(f"[R2] train done in {(time.time()-t0)/60:.1f} min", flush=True)

# 真实训练轮数：从 Experiment 取，绝不信 python 变量 N_EPOCH
epochs_target = exp.get_max_steps()
epochs_trained = exp.currentStep
commit = git_commit()
print(f"[R2] epochs_target={epochs_target} epochs_trained={epochs_trained} "
      f"(N_EPOCH var={N_EPOCH}) seed={SEED} commit={commit}", flush=True)
if epochs_trained < epochs_target:
    print(f"[R2][WARN] 未训满：trained {epochs_trained} < target {epochs_target}", flush=True)

# ---- Eval: per-patient Dice + bootstrap CI ----
def bootstrap_ci(vals, n=1000, seed=0):
    rng = np.random.default_rng(seed)
    vals = np.asarray(vals, dtype=float)
    means = [rng.choice(vals, len(vals), replace=True).mean() for _ in range(n)]
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))

for ens, tag in [(False, "single"), (True, "pseudo10")]:
    loss_log = agent.getAverageDiceScore(pseudo_ensemble=ens)
    ch0 = loss_log[0]  # {patient_id: dice}
    vals = list(ch0.values())
    mean, std = float(np.mean(vals)), float(np.std(vals))
    lo, hi = bootstrap_ci(vals)

    # PASS判定（IPMI'23 Table 1）：
    # 条件A：bootstrap 95% CI 含论文 0.838
    # 条件B：点估 >= 0.81 且 > UNet baseline 0.799
    pass_a = (lo <= 0.838 <= hi)
    pass_b = (mean >= 0.81 and mean > 0.799)
    verdict = "PASS" if (pass_a or pass_b) else "FAIL"

    out_csv = os.path.join(ROOT, "results", f"r2_prostate_{tag}.csv")
    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    with open(out_csv, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["patient_id", "dice", "seed", "git_commit"])
        for pid, d in ch0.items(): w.writerow([pid, d, SEED, commit])

    summary = {
        "tag": tag, "n": len(vals),
        "dice_mean": round(mean, 4), "dice_std": round(std, 4),
        "ci95": [round(lo, 4), round(hi, 4)],
        "paper_target": 0.838, "unet_baseline": 0.799,
        "pass_ci_contains_paper": pass_a,
        "pass_point_estimate": pass_b,
        "verdict": verdict,
        "epochs_target": epochs_target, "epochs_trained": epochs_trained,
        "params": n_params, "seed": SEED, "git_commit": commit,
        "label_mode": "whole_gland_binary",
        "input_modality": "T2_only_channel0",
        "channel_n": config[0]['channel_n'],
        "input_size": config[0]['input_size'],
    }
    print(f"[R2-{tag}] {json.dumps(summary)}", flush=True)
    with open(os.path.join(ROOT, "results", f"r2_prostate_{tag}_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
