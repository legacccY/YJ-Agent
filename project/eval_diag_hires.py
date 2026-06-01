"""E3/E7 诊断保持评估 (256 域, 修复 oracle 分辨率失配).

之前 IMG=128 把 256 原图压糊 -> B3 oracle AUC 0.91->0.54 失效, ΔAUC 不可信.
此版: 256 域推理, oracle 走训练协议 (256 已是原生 -> CenterCrop 224 -> ImageNet norm).
对比 Stage1(no DP) vs Stage2(DP) 的 ΔAUC + 分类一致率, 判 DP-Loss 真实价值.
cwd=project.
"""
import random
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import torch
from sklearn.metrics import roc_auc_score
from torchvision import transforms

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data.enhance_dataset import _degrade_numpy
from eval_stage2_compare import (load_visienhance, load_visiscore, load_b3,
                                 CFG, CKPTS, VISISCORE, B3, LABELS, SPLIT, META)  # noqa

IMG = 256        # 原图原生分辨率; B3 VAL_TFM = Resize(256)->CenterCrop(224)
CROP = 224
_TT = transforms.ToTensor()
_NORM = transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])


def center_crop_224(x):
    o = (IMG - CROP) // 2
    return x[..., o:o + CROP, o:o + CROP]


def build_df(n_max=3000):
    lbl = pd.read_csv(LABELS); lbl["isic_id"] = lbl["original_path"].apply(lambda p: Path(p).stem)
    sp = pd.read_csv(SPLIT); tids = set(sp.loc[sp.split == "test", "isic_id"].astype(str))
    meta = pd.read_csv(META)[["isic_id", "target"]]
    df = lbl[lbl.isic_id.isin(tids)].drop_duplicates("original_path").merge(meta, on="isic_id")
    df = df[df.original_path.apply(lambda p: Path(p).exists())]
    if n_max and len(df) > n_max:
        df = df.sample(n_max, random_state=7)
    return df.reset_index(drop=True)


@torch.no_grad()
def eval_diag(model, visiscore, b3, df, device):
    def b3_prob(imgs_256):
        x = _NORM(center_crop_224(imgs_256))
        return torch.softmax(b3(x), dim=-1)[:, 1].cpu().numpy()

    pr, pd_, pe, ys = [], [], [], []
    for s in range(0, len(df), 16):
        rows = df.iloc[s:s + 16]
        lows, refs = [], []
        for j, row in rows.iterrows():
            img = cv2.imread(str(row.original_path))
            if img is None:
                continue
            img = cv2.resize(img, (IMG, IMG), interpolation=cv2.INTER_AREA)
            deg = _degrade_numpy(img, "moderate", random.Random(7 + j))
            refs.append(_TT(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)))
            lows.append(_TT(cv2.cvtColor(deg, cv2.COLOR_BGR2RGB)))
            ys.append(int(row.target))
        if not lows:
            continue
        x_low = torch.stack(lows).to(device)
        x_ref = torch.stack(refs).to(device)
        q = visiscore(x_low)
        x_enh = model(x_low, q)
        pr.extend(b3_prob(x_ref))
        pd_.extend(b3_prob(x_low))            # 退化图不增强 baseline
        pe.extend(b3_prob(x_enh))

    pr, pd_, pe, ys = map(np.array, (pr, pd_, pe, ys))
    auc_ref = roc_auc_score(ys, pr)
    auc_deg = roc_auc_score(ys, pd_)
    auc_enh = roc_auc_score(ys, pe)
    consist = float(np.mean((pr > 0.5) == (pe > 0.5)))
    return auc_ref, auc_deg, auc_enh, abs(auc_enh - auc_ref), consist, int(ys.sum()), len(ys)


def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    visiscore = load_visiscore(VISISCORE, device)
    b3 = load_b3(B3, device)
    df = build_df()
    print(f"device={device}  n_test_imgs={len(df)}  pos={int(df.target.sum())}")

    rows = []
    for name, path in CKPTS.items():
        model = load_visienhance(CFG, path, device)
        ar, adg, ae, d, cons, npos, ntot = eval_diag(model, visiscore, b3, df, device)
        print(f"{name:20s} AUC_ref={ar:.4f} AUC_deg={adg:.4f} AUC_enh={ae:.4f} "
              f"|dAUC|={d:.4f} 一致率={cons:.3f} (pos={npos}/{ntot})")
        rows.append({"model": name, "auc_ref": round(ar, 4), "auc_deg": round(adg, 4),
                     "auc_enh": round(ae, 4), "dAUC": round(d, 4), "consistency": round(cons, 4)})

    print("\n" + pd.DataFrame(rows).to_string(index=False))
    Path("results").mkdir(exist_ok=True)
    pd.DataFrame(rows).to_csv("results/stage2_diag_hires.csv", index=False)
    print("\nsaved -> results/stage2_diag_hires.csv")


if __name__ == "__main__":
    main()
