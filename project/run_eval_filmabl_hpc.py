"""FiLM 诊断消融 (HPC): with-FiLM(S1) vs no-FiLM(S1) 的 dAUC/一致率/dflip/KL.

两 ckpt 同 recipe (stage1_planA_256), 唯一差 film_scale 0.1 vs 0.0.
关键: monkeypatch load_visienhance 按路径含 'noFiLM' 选 film_scale (否则 no-FiLM 加载错).
复用 eval_diag_paired 严格配对协议. cwd 必须 = code/.
输出 .out 里 '每模型' 行 = FiLM 在/不在对诊断保持的影响.
"""
import sys
sys.path.insert(0, ".")

import torch
import eval_stage2_compare as E

ROOT = "/gpfs/work/bio/jiayu2403/visienhance"
E.LABELS = f"{ROOT}/data/quality_labels_nocrop_hpc.csv"
E.SPLIT = f"{ROOT}/data/isic_split.csv"
E.META = f"{ROOT}/data/train-metadata.csv"
E.VISISCORE = f"{ROOT}/checkpoints/best_visiscore.pth"
E.B3 = f"{ROOT}/checkpoints/efficientnet_b3_isic.pth"
E.CKPTS = {
    "with-FiLM (S1)": f"{ROOT}/checkpoints/visienhance/stage1_planA_256/best_visienhance.pth",
    "no-FiLM (S1)":   f"{ROOT}/checkpoints/visienhance/stage1_planA_256_noFiLM/best_visienhance.pth",
}

import eval_diag_paired as P
from models.visienhance import VisiEnhanceNet


def load_with_filmscale(cfg, path, device):
    m = cfg.model
    fs = 0.0 if "noFiLM" in path else 0.1
    net = VisiEnhanceNet(base_channels=m.base_channels, enc_blocks=list(m.enc_blocks),
                         mid_blocks=m.mid_blocks, dec_blocks=list(m.dec_blocks),
                         film_scale=fs).to(device)
    ck = torch.load(path, map_location=device, weights_only=False)
    net.load_state_dict(ck["model"])
    print(f"  loaded film_scale={fs}  {path}", flush=True)
    return net.eval()


P.load_visienhance = load_with_filmscale
P.main()
