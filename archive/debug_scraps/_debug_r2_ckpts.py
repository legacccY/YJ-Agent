"""R2 塌缩时间线诊断：逐 ckpt(epoch_50..300) eval mean Dice，
看是一直 0（从未学会）还是先好后塌（晚期发散）。HPC GPU 跑。
"""
import os, sys, glob
import numpy as np
import torch

ROOT = os.environ.get("MEDNCA_ROOT", "/gpfs/work/bio/jiayu2403/mednca")
OFFICIAL = os.path.join(ROOT, "M3D-NCA-official")
sys.path.insert(0, OFFICIAL); os.chdir(OFFICIAL)
sys.path.insert(0, os.path.join(ROOT, "code"))
from src.datasets.Nii_Gz_Dataset_3D import Dataset_NiiGz_3D
from fast_nca import FastBackboneNCA as BackboneNCA
from src.utils.Experiment import Experiment
from src.agents.Agent_Med_NCA import Agent_Med_NCA

DEVICE = "cuda:0"
config = [{
    'img_path':   os.path.join(ROOT, "data", "Task05_Prostate", "imagesTr"),
    'label_path': os.path.join(ROOT, "data", "Task05_Prostate", "labelsTr"),
    'model_path': os.path.join(ROOT, "checkpoints", "r2_prostate"),
    'device': DEVICE, 'unlock_CPU': True,
    'lr': 16e-4, 'lr_gamma': 0.9999, 'betas': (0.5, 0.5),
    'save_interval': 50, 'evaluate_interval': 25,
    'n_epoch': 300, 'batch_size': 20,
    'channel_n': 32, 'inference_steps': 64, 'cell_fire_rate': 0.5,
    'input_channels': 1, 'output_channels': 1, 'hidden_size': 128,
    'train_model': 1, 'input_size': [(64, 64), (256, 256)],
    'data_split': [0.7, 0, 0.3],
}]
dataset = Dataset_NiiGz_3D(slice=2)
device = torch.device(DEVICE)
ca = [BackboneNCA(32, 0.5, device, hidden_size=128, input_channels=1).to(device) for _ in range(2)]
agent = Agent_Med_NCA(ca)
exp = Experiment(config, dataset, ca, agent)
dataset.set_experiment(exp)
exp.set_model_state('test')

mdir = os.path.join(ROOT, "checkpoints", "r2_prostate", "models")
epochs = sorted(int(d.split('_')[1]) for d in os.listdir(mdir) if d.startswith('epoch_'))
print("ckpts:", epochs, flush=True)

for ep in epochs:
    m0 = torch.load(os.path.join(mdir, f"epoch_{ep}", "model0.pth"), map_location=device)
    m1 = torch.load(os.path.join(mdir, f"epoch_{ep}", "model1.pth"), map_location=device)
    ca[0].load_state_dict(m0); ca[1].load_state_dict(m1)
    ca[0].eval(); ca[1].eval()
    with torch.no_grad():
        loss_log = agent.getAverageDiceScore(pseudo_ensemble=False)
        vals = list(loss_log[0].values())
    mean = float(np.mean(vals)) if vals else float('nan')
    print(f"[ckpt epoch_{ep}] mean_dice={mean:.4f} n={len(vals)}", flush=True)
print("=== timeline done ===", flush=True)
