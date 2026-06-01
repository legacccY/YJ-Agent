"""验证 B3 oracle AUC<0.5 是 class index 反 还是 oracle 真坏.
比较 softmax[:,1] vs [:,0] 对 target 的 AUC. cwd=project."""
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from sklearn.metrics import roc_auc_score
from torchvision import transforms

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from eval_stage2_compare import load_b3, B3, LABELS, SPLIT, META, IMG  # noqa

_TT = transforms.ToTensor()
dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
b3 = load_b3(B3, dev)
norm = transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])

lbl = pd.read_csv(LABELS); lbl["isic_id"] = lbl["original_path"].apply(lambda p: Path(p).stem)
sp = pd.read_csv(SPLIT); tids = set(sp.loc[sp.split == "test", "isic_id"].astype(str))
meta = pd.read_csv(META)[["isic_id", "target"]]
df = lbl[lbl.isic_id.isin(tids)].drop_duplicates("original_path").merge(meta, on="isic_id")
df = df[df.original_path.apply(lambda p: Path(p).exists())].sample(800, random_state=1).reset_index(drop=True)

p1, ys = [], []
with torch.no_grad():
    for s in range(0, len(df), 32):
        rows = df.iloc[s:s + 32]
        imgs = []
        for _, r in rows.iterrows():
            im = cv2.imread(str(r.original_path))
            im = cv2.resize(im, (IMG, IMG), interpolation=cv2.INTER_AREA)
            imgs.append(_TT(cv2.cvtColor(im, cv2.COLOR_BGR2RGB)))
            ys.append(int(r.target))
        x = torch.stack(imgs).to(dev)
        x = F.interpolate(x, size=224, mode="bilinear", align_corners=False)
        prob = torch.softmax(b3(norm(x)), dim=-1)[:, 1].cpu().numpy()
        p1.extend(prob)
p1, ys = np.array(p1), np.array(ys)
print(f"n={len(ys)} pos={ys.sum()}")
print(f"AUC(softmax[:,1] as melanoma) = {roc_auc_score(ys, p1):.4f}")
print(f"AUC(softmax[:,0] as melanoma) = {roc_auc_score(ys, 1 - p1):.4f}")
