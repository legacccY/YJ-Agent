"""R2 Dice=0 诊断：加载 epoch_300，对每个 test volume 打印
GT 前景体素 / 预测前景体素 / 输入范围 / 原始 dice。
区分「训练塌成全背景」vs「数据/eval bug」。在 HPC GPU 节点跑。
"""
import os, sys
import numpy as np
import torch

ROOT = os.environ.get("MEDNCA_ROOT", "/gpfs/work/bio/jiayu2403/mednca")
OFFICIAL = os.path.join(ROOT, "M3D-NCA-official")
sys.path.insert(0, OFFICIAL)
os.chdir(OFFICIAL)
sys.path.insert(0, os.path.join(ROOT, "code"))

from src.datasets.Nii_Gz_Dataset_3D import Dataset_NiiGz_3D
from fast_nca import FastBackboneNCA as BackboneNCA
from src.utils.Experiment import Experiment
from src.agents.Agent_Med_NCA import Agent_Med_NCA

DEVICE = "cuda:0" if torch.cuda.is_available() else "cpu"
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
print(f"reload epochs={exp.currentStep}/{exp.get_max_steps()} device={DEVICE}", flush=True)

loader = torch.utils.data.DataLoader(dataset, batch_size=1)
n_shown = 0
with torch.no_grad():
    for i, data in enumerate(loader):
        data_prep = agent.prepare_data(data, eval=True)
        data_id, inputs, targets = data_prep
        outputs, targets_out = agent.get_outputs(data_prep, full_img=True, tag="0")
        img = inputs[0, ..., 0].detach().cpu().numpy()
        gt = targets_out[..., 0].detach().cpu().numpy()
        raw = outputs[..., 0].detach().cpu().numpy()
        prob = 1/(1+np.exp(-raw))   # sigmoid
        pred_fg = int((prob > 0.5).sum())
        gt_fg = int((gt > 0.5).sum())
        print(f"[{i}] id={str(data_id)[:30]} img[min={img.min():.3f} max={img.max():.3f} mean={img.mean():.3f}] "
              f"gt_unique={np.unique(gt)[:5]} gt_fg={gt_fg} | raw[min={raw.min():.3f} max={raw.max():.3f}] "
              f"prob_max={prob.max():.3f} pred_fg={pred_fg}", flush=True)
        n_shown += 1
        if n_shown >= 12:
            break
print("=== debug done ===", flush=True)
