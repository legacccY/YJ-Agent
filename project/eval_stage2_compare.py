"""One-off: compare Stage 1 (no DP) vs Stage 2 (DP-Loss, HPC) under identical eval.

判 Stage 2 DP-Loss 是否真有价值：
  - PSNR/SSIM   : nocrop 预生成 medium, test split, 每图均值（论文报法，像素对齐）
  - 诊断保持     : test 高质原图 on-the-fly degrade(moderate) -> enh -> B3 oracle
                   ΔAUC (need target, merge train-metadata) + 分类一致率(argmax ref vs enh)

复用 eval_visienhance 的 model loaders。cwd 必须是 project/。
"""
import random
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from sklearn.metrics import roc_auc_score
from torch.utils.data import DataLoader
from torchvision import transforms
from tqdm import tqdm

from data.enhance_dataset import EnhanceDataset, _degrade_numpy
from models.visienhance import VisiEnhanceNet
from models.visiscore import VisiScoreNet
from omegaconf import OmegaConf


def load_visienhance(cfg, path, device):
    m = cfg.model
    net = VisiEnhanceNet(base_channels=m.base_channels, enc_blocks=list(m.enc_blocks),
                         mid_blocks=m.mid_blocks, dec_blocks=list(m.dec_blocks)).to(device)
    ck = torch.load(path, map_location=device, weights_only=False)
    net.load_state_dict(ck["model"])
    return net.eval()


def load_visiscore(path, device):
    net = VisiScoreNet().to(device)
    ck = torch.load(path, map_location=device, weights_only=False)
    net.load_state_dict(ck["model"] if "model" in ck else ck)
    return net.eval()


def load_b3(path, device):
    # 必须用 torchvision (训练脚本 finetune_efficientnet.py 用的), 且复现自定义分类头.
    # 之前用 timm -> key 不匹配 strict=False 静默丢分类头 -> oracle 随机 (AUC~0.5).
    import torch.nn as nn
    from torchvision.models import efficientnet_b3
    net = efficientnet_b3(weights=None)
    net.classifier = nn.Sequential(nn.Dropout(p=0.3, inplace=True),
                                   nn.Linear(net.classifier[1].in_features, 2))
    ck = torch.load(path, map_location=device, weights_only=False)
    missing, unexpected = net.load_state_dict(ck["model"] if "model" in ck else ck, strict=False)
    assert not missing and not unexpected, f"b3 load mismatch: {missing[:3]} / {unexpected[:3]}"
    return net.to(device).eval()

ROOT = "D:/YJ-Agent"
LABELS = f"{ROOT}/data/quality_labels_nocrop.csv"
SPLIT = f"{ROOT}/data/isic_split.csv"
META = f"{ROOT}/data/raw/isic2020/train-metadata.csv"
VISISCORE = f"{ROOT}/checkpoints/best_visiscore.pth"
B3 = f"{ROOT}/checkpoints/efficientnet_b3_isic.pth"
IMG = 128
_TT = transforms.ToTensor()

CKPTS = {
    "Stage1 (no DP)":  f"{ROOT}/checkpoints/visienhance/stage1_planA_nocrop/best_visienhance.pth",
    "Stage2 (DP, HPC)": f"{ROOT}/project/checkpoints/visienhance/stage2_planA_256_v5/best_visienhance.pth",
}

# model cfg (Plan A 15M)
CFG = OmegaConf.create({"model": {"base_channels": 64, "enc_blocks": [2, 2, 2],
                                  "mid_blocks": 6, "dec_blocks": [2, 2, 2]}})


@torch.no_grad()
def eval_psnr(model, visiscore, device, n_max=4000):
    from skimage.metrics import peak_signal_noise_ratio, structural_similarity
    ds = EnhanceDataset(LABELS, SPLIT, split="test", img_size=IMG, severity="medium")
    if n_max and len(ds) > n_max:
        ds.df = ds.df.sample(n_max, random_state=0).reset_index(drop=True)
    loader = DataLoader(ds, batch_size=16, shuffle=False, num_workers=0)
    ps, ss = [], []
    for x_low, x_ref in tqdm(loader, desc="PSNR", ncols=70):
        x_low = x_low.to(device)
        q = visiscore(x_low)
        x_enh = model(x_low, q).cpu()
        for i in range(x_enh.shape[0]):
            r = (x_ref[i].permute(1, 2, 0).numpy() * 255).astype(np.uint8)
            e = (x_enh[i].permute(1, 2, 0).numpy() * 255).clip(0, 255).astype(np.uint8)
            ps.append(peak_signal_noise_ratio(r, e, data_range=255))
            ss.append(structural_similarity(r, e, channel_axis=2, data_range=255))
    return float(np.mean(ps)), float(np.mean(ss)), len(ps)


@torch.no_grad()
def eval_diag(model, visiscore, b3, device, n_max=2000):
    """高质原图 -> degrade(moderate) -> enh -> B3 oracle. ΔAUC + 一致率."""
    lbl = pd.read_csv(LABELS)
    lbl["isic_id"] = lbl["original_path"].apply(lambda p: Path(p).stem)
    sp = pd.read_csv(SPLIT)
    test_ids = set(sp.loc[sp["split"] == "test", "isic_id"].astype(str))
    meta = pd.read_csv(META)[["isic_id", "target"]]

    df = lbl[lbl["isic_id"].isin(test_ids)].drop_duplicates("original_path")
    df = df.merge(meta, on="isic_id", how="inner")
    df = df[df["original_path"].apply(lambda p: Path(p).exists())]
    # 注: nocrop csv 质量分是"降质图"的分, 不能用来筛"高质原图"(会误杀).
    # 直接用全部 test 唯一原图, on-the-fly degrade(moderate) 后测诊断保持.
    if n_max and len(df) > n_max:
        df = df.sample(n_max, random_state=7)
    df = df.reset_index(drop=True)

    norm = transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])

    def b3_pred(imgs):
        x = F.interpolate(imgs, size=224, mode="bilinear", align_corners=False)
        return torch.softmax(b3(norm(x)), dim=-1)[:, 1].cpu().numpy()

    pr, pe, ys = [], [], []
    for s in tqdm(range(0, len(df), 16), desc="diag", ncols=70):
        rows = df.iloc[s:s + 16]
        lows, refs = [], []
        for j, row in rows.iterrows():
            img = cv2.imread(str(row["original_path"]))
            if img is None:
                continue
            img = cv2.resize(img, (IMG, IMG), interpolation=cv2.INTER_AREA)
            deg = _degrade_numpy(img, "moderate", random.Random(7 + j))
            refs.append(_TT(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)))
            lows.append(_TT(cv2.cvtColor(deg, cv2.COLOR_BGR2RGB)))
            ys.append(int(row["target"]))
        if not lows:
            continue
        x_low = torch.stack(lows).to(device)
        x_ref = torch.stack(refs).to(device)
        q = visiscore(x_low)
        x_enh = model(x_low, q)
        pr.extend(b3_pred(x_ref))
        pe.extend(b3_pred(x_enh))

    pr, pe, ys = np.array(pr), np.array(pe), np.array(ys)
    auc_ref = roc_auc_score(ys, pr)
    auc_enh = roc_auc_score(ys, pe)
    consist = float(np.mean((pr > 0.5) == (pe > 0.5)))       # argmax 一致率
    return auc_ref, auc_enh, abs(auc_enh - auc_ref), consist, int(ys.sum()), len(ys)


def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"device={device}")
    visiscore = load_visiscore(VISISCORE, device)
    b3 = load_b3(B3, device)

    rows = []
    for name, path in CKPTS.items():
        print(f"\n===== {name} =====")
        model = load_visienhance(CFG, path, device)
        psnr, ssim, npx = eval_psnr(model, visiscore, device)
        ar, ae, d, cons, npos, ntot = eval_diag(model, visiscore, b3, device)
        print(f"  PSNR={psnr:.2f}  SSIM={ssim:.4f}  (n={npx})")
        print(f"  AUC_ref={ar:.4f}  AUC_enh={ae:.4f}  |dAUC|={d:.4f}  "
              f"一致率={cons:.3f}  (pos={npos}/{ntot})")
        rows.append({"model": name, "psnr": round(psnr, 2), "ssim": round(ssim, 4),
                     "auc_ref": round(ar, 4), "auc_enh": round(ae, 4),
                     "dAUC": round(d, 4), "consistency": round(cons, 4)})

    print("\n===== 对比 =====")
    print(pd.DataFrame(rows).to_string(index=False))
    Path("results").mkdir(exist_ok=True)
    pd.DataFrame(rows).to_csv("results/stage2_compare.csv", index=False)
    print("\nsaved -> results/stage2_compare.csv")


if __name__ == "__main__":
    main()
