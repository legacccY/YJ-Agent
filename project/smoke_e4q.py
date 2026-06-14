"""E4Q local smoke (CPU): validate compute_e4_qvib wiring (abcd OTSU + efnet-b0 +
Q-VIB encoder/classifier shapes) on 16 real test images, BEFORE HPC submission.
VisiEnhance forward is replaced by identity (x_enh=x_low) -- VisiEnhance convT
crashes on local GPU (cuDNN/illegal-mem, session28), not needed to test this path."""
import sys

import torch
from omegaconf import OmegaConf
from torch.utils.data import DataLoader, Subset

sys.path.insert(0, ".")

from data.enhance_dataset import EnhanceDataset
from eval_visienhance import compute_e4_qvib, load_efnet_b0, load_qvib, load_visiscore

device = torch.device("cpu")
cfg = OmegaConf.load("configs/visienhance_s2_planA_256_v5_local.yaml")
dcfg = cfg.data

visiscore = load_visiscore(cfg.frozen_models.visiscore_ckpt, device)
encoder, classifier = load_qvib(cfg.frozen_models.qvib_ckpt, device)
efnet = load_efnet_b0(device)

identity_model = lambda x, q: x

ds = EnhanceDataset(dcfg.labels_csv, dcfg.split_csv, split="test",
                     img_size=dcfg.img_size, severity="mixed")
ds = Subset(ds, list(range(16)))
loader = DataLoader(ds, batch_size=8, shuffle=False, num_workers=0)

out = compute_e4_qvib(identity_model, visiscore, encoder, classifier, efnet, loader, device, n_mc=4)
print("OK", out)
