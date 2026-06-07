"""落盘 dflip headline 图所需数据 (本地 GPU, 无需 HPC).

复用 eval_diag_paired 的 build_df + 严格配对协议 (同图同退化 seed=7+j).
输出:
  results/dflip_persample.csv          每图 isic_id,target,j,pr,pd,pe (B3 mel-prob: ref/deg/enh_S2)
  results/dflip_panels/{isic_id}.npz   每个 dangerous-flip 病灶: ref/deg/enh 256x256x3 uint8 + pr/pd/pe/attr

dangerous_flip = (ys==1 & pr>0.5 & pe<0.5);  attr: B=enh主动翻(pd>=0.5) / A=退化已翻(pd<0.5).
cwd=project.
"""
import os
import random
from pathlib import Path

BATCH = int(os.environ.get("DFLIP_BATCH", "4"))
MAXN = int(os.environ.get("DFLIP_MAX", "0"))   # >0: 只处理前 N 行 (调试)

import cv2
import numpy as np
import pandas as pd
import torch

from eval_diag_paired import build_df, center_crop_224, _NORM, _TT, IMG
from eval_stage2_compare import load_visienhance, load_visiscore, load_b3
import eval_stage2_compare as E   # 路径常量经 wrapper patch 后从这里取 (本地/HPC 通用)


def to_uint8(t):
    """CHW float[0,1] tensor -> HWC uint8 RGB."""
    a = t.detach().cpu().clamp(0, 1).numpy().transpose(1, 2, 0)
    return (a * 255 + 0.5).astype(np.uint8)


@torch.no_grad()
def main():
    torch.backends.cudnn.benchmark = False     # 稳定优先 (laptop 4070 illegal-access)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    visiscore = load_visiscore(E.VISISCORE, device)
    b3 = load_b3(E.B3, device)
    models = {name: load_visienhance(E.CFG, path, device) for name, path in E.CKPTS.items()}
    S2 = list(models)[1]                    # Stage2 v4 (DP)
    df = build_df()
    if MAXN > 0:
        df = df.head(MAXN).reset_index(drop=True)
    print(f"device={device}  n={len(df)}  pos={int(df.target.sum())}  S2={S2}", flush=True)

    def b3_mel(x256):
        return torch.softmax(b3(_NORM(center_crop_224(x256))), dim=-1)[:, 1].cpu().numpy()

    Path("results/dflip_panels").mkdir(parents=True, exist_ok=True)
    rows_out = []
    # 缓存 flip 候选用图: 先一遍拿概率, 再对 flip 二次取图 (省显存)
    cache = {}          # global_idx -> (isic_id, j, ref_t_cpu, deg_t_cpu, x_low_idx_in_batch)
    gi = 0
    for s in range(0, len(df), BATCH):
        rows = df.iloc[s:s + BATCH]
        lows, refs, metas = [], [], []
        for j, row in rows.iterrows():
            img = cv2.imread(str(row.original_path))
            if img is None:
                continue
            img = cv2.resize(img, (IMG, IMG), interpolation=cv2.INTER_AREA)
            from data.enhance_dataset import _degrade_numpy
            deg = _degrade_numpy(img, "moderate", random.Random(7 + j))
            refs.append(_TT(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)))
            lows.append(_TT(cv2.cvtColor(deg, cv2.COLOR_BGR2RGB)))
            metas.append((row.isic_id, int(row.target), int(j)))
        if not lows:
            continue
        x_low = torch.stack(lows).to(device)
        x_ref = torch.stack(refs).to(device)
        q = visiscore(x_low)
        x_enh = models[S2](x_low, q)
        if s % 400 == 0:
            print(f"  s={s}/{len(df)}", flush=True)
            torch.cuda.empty_cache()
        pr = b3_mel(x_ref); pd_ = b3_mel(x_low); pe = b3_mel(x_enh)
        for k, (isic_id, tgt, j) in enumerate(metas):
            rows_out.append({"isic_id": isic_id, "target": tgt, "j": j,
                             "pr": float(pr[k]), "pd": float(pd_[k]), "pe": float(pe[k])})
            # dangerous-flip 病灶: 存三联图
            if tgt == 1 and pr[k] > 0.5 and pe[k] < 0.5:
                attr = "B_enh" if pd_[k] >= 0.5 else "A_deg"
                np.savez_compressed(
                    f"results/dflip_panels/{isic_id}.npz",
                    ref=to_uint8(x_ref[k]), deg=to_uint8(x_low[k]), enh=to_uint8(x_enh[k]),
                    pr=float(pr[k]), pd=float(pd_[k]), pe=float(pe[k]), attr=attr)
        gi += len(metas)

    out = pd.DataFrame(rows_out)
    out.to_csv("results/dflip_persample.csv", index=False)
    mask = (out.target == 1) & (out.pr > 0.5)
    flip = mask & (out.pe < 0.5)
    enh_caused = (flip & (out.pd >= 0.5)).sum()
    print(f"\nsaved results/dflip_persample.csv  ({len(out)} rows)")
    print(f"mask(ref正确报阳mel)={int(mask.sum())}  flip={int(flip.sum())}  "
          f"B_enh主动翻={int(enh_caused)}  panels -> results/dflip_panels/*.npz")


if __name__ == "__main__":
    main()
