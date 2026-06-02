"""R1: Med-NCA (2D slice-wise) on MSD Task04 Hippocampus.
Faithful to official src/examples/train_Med_NCA.py + per-patient Dice CSV + bootstrap 95% CI.
Acceptance R1: per-image (per-volume) Dice mean >= 0.86.
"""
import os, sys, json, csv, time
import numpy as np
import torch

ROOT = r"D:\YJ-Agent\project\meeting\Med-NCA"
OFFICIAL = os.path.join(ROOT, "M3D-NCA-official")
sys.path.insert(0, OFFICIAL)
os.chdir(OFFICIAL)  # src imports + relative paths

from src.datasets.Nii_Gz_Dataset_3D import Dataset_NiiGz_3D
from src.models.Model_BackboneNCA import BackboneNCA
from src.losses.LossFunctions import DiceBCELoss, DiceLoss
from src.utils.Experiment import Experiment
from src.agents.Agent_Med_NCA import Agent_Med_NCA

N_EPOCH = int(os.environ.get("R1_EPOCHS", "300"))   # paper uses 1000; start 300, extend if Dice<0.86
DEVICE = "cuda:0" if torch.cuda.is_available() else "cpu"

config = [{
    'img_path':   os.path.join(ROOT, "data", "Task04_Hippocampus", "imagesTr"),
    'label_path': os.path.join(ROOT, "data", "Task04_Hippocampus", "labelsTr"),
    'model_path': os.path.join(ROOT, "checkpoints", "r1_hippocampus"),
    'device': DEVICE,
    'unlock_CPU': True,
    'lr': 16e-4, 'lr_gamma': 0.9999, 'betas': (0.5, 0.5),
    'save_interval': 50, 'evaluate_interval': 25,
    'n_epoch': N_EPOCH, 'batch_size': 48,
    'channel_n': 16, 'inference_steps': 64, 'cell_fire_rate': 0.5,
    'input_channels': 1, 'output_channels': 1, 'hidden_size': 128,
    'train_model': 1,
    'input_size': [(16, 16), (64, 64)],
    'data_split': [0.7, 0, 0.3],
}]

print(f"[R1] device={DEVICE} epochs={N_EPOCH}", flush=True)

dataset = Dataset_NiiGz_3D(slice=2)
device = torch.device(config[0]['device'])
ca1 = BackboneNCA(config[0]['channel_n'], config[0]['cell_fire_rate'], device,
                  hidden_size=config[0]['hidden_size'], input_channels=config[0]['input_channels']).to(device)
ca2 = BackboneNCA(config[0]['channel_n'], config[0]['cell_fire_rate'], device,
                  hidden_size=config[0]['hidden_size'], input_channels=config[0]['input_channels']).to(device)
ca = [ca1, ca2]
agent = Agent_Med_NCA(ca)
exp = Experiment(config, dataset, ca, agent)
dataset.set_experiment(exp)
exp.set_model_state('train')

# R3: parameter count check (<100K)
n_params = sum(p.numel() for m in ca for p in m.parameters())
print(f"[R3] total params = {n_params} ({'PASS <100K' if n_params < 1e5 else 'FAIL >=100K'})", flush=True)

loader = torch.utils.data.DataLoader(dataset, shuffle=True, batch_size=exp.get_from_config('batch_size'))
loss_function = DiceBCELoss()

t0 = time.time()
agent.train(loader, loss_function)
print(f"[R1] train done in {(time.time()-t0)/60:.1f} min", flush=True)

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
    out_csv = os.path.join(ROOT, "results", f"r1_hippocampus_{tag}.csv")
    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    with open(out_csv, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["patient_id", "dice"])
        for pid, d in ch0.items(): w.writerow([pid, d])
    verdict = "PASS" if mean >= 0.86 else "FAIL"
    summary = {"tag": tag, "n": len(vals), "dice_mean": round(mean, 4),
               "dice_std": round(std, 4), "ci95": [round(lo, 4), round(hi, 4)],
               "threshold": 0.86, "verdict": verdict, "epochs": N_EPOCH, "params": n_params}
    print(f"[R1-{tag}] {json.dumps(summary)}", flush=True)
    with open(os.path.join(ROOT, "results", f"r1_hippocampus_{tag}_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
