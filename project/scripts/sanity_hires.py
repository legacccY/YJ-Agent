"""Sanity: enhance/visiscore 能否在 256 推理 + 预生成图/原图实际像素.
决定 E3 诊断评估能否换到 256 域让 B3 oracle 恢复有效. cwd=project."""
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from eval_stage2_compare import load_visienhance, load_visiscore, CFG, CKPTS, VISISCORE, LABELS  # noqa

dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# 1) 实际像素尺寸
lbl = pd.read_csv(LABELS).iloc[0]
for col in ["degraded_path", "original_path"]:
    im = cv2.imread(str(lbl[col]))
    print(f"{col}: {None if im is None else im.shape}")
raw = list(Path("D:/YJ-Agent/data/raw/isic2020/train-image/image").glob("*.jpg"))[:1]
if raw:
    print(f"raw isic original: {cv2.imread(str(raw[0])).shape}")

# 2) enhance + visiscore forward @128/256/384
vs = load_visiscore(VISISCORE, dev)
enh = load_visienhance(CFG, CKPTS["Stage2 (DP, HPC)"], dev)
for sz in [128, 256, 384]:
    try:
        x = torch.rand(2, 3, sz, sz, device=dev)
        with torch.no_grad():
            q = vs(x)
            y = enh(x, q)
        print(f"size {sz}: visiscore->{tuple(q.shape)}  enhance->{tuple(y.shape)}  OK")
    except Exception as e:
        print(f"size {sz}: FAIL {type(e).__name__}: {e}")
