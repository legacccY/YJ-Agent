"""visiscore q 喂法对照 (HPC): raw-q vs NORM-q 给同一 v5 增强器.

诊断 visiscore 喂错 (raw[0,1]@256 而非 ImageNet-NORM@224) 的后果.
增强模型 (v5) 是 raw-q 训的; 这里对同一模型, 同一输入 x_low, 只变条件 q 的算法:
  raw  : q = visiscore(x_low)                         (现状, 训练口径)
  norm : q = visiscore(NORM(resize224(x_low)))        (visiscore 正确口径)
对每种算 E3/E7 诊断保持 (dAUC/一致率/KL/dflip) + per-image PSNR(enh vs ref).

读法:
  两者指标≈一致 -> 增强器对 q 不敏感 (FiLM 被 flat-q 废确认), E3/E7 数字 robust.
  两者差很大   -> 模型依赖特定 q 分布, 需重训才能用正确 q.

协议 = eval_diag_paired moderate@256. 输出 results/qnorm_compare.csv. cwd=code/.
"""
import random
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from sklearn.metrics import roc_auc_score
from torchvision import transforms
from omegaconf import OmegaConf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data.enhance_dataset import _degrade_numpy
from eval_stage2_compare import load_visienhance, load_visiscore, load_b3  # noqa

ROOT      = "D:/YJ-Agent"
LABELS    = f"{ROOT}/data/quality_labels_nocrop.csv"
SPLIT     = f"{ROOT}/data/isic_split.csv"
META      = f"{ROOT}/data/raw/isic2020/train-metadata.csv"
VISISCORE = f"{ROOT}/checkpoints/best_visiscore.pth"
B3        = f"{ROOT}/checkpoints/efficientnet_b3_isic.pth"
CKPT_V5   = f"{ROOT}/project/checkpoints/visienhance/stage2_planA_256_v5/best_visienhance.pth"

IMG, CROP = 256, 224
NEG_PER_POS = 30
SEVERITY = "moderate"
CFG = OmegaConf.create({"model": {"base_channels": 64, "enc_blocks": [2, 2, 2],
                                   "mid_blocks": 6, "dec_blocks": [2, 2, 2]}})
_TT   = transforms.ToTensor()
_NORM = transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])


def center_crop_224(x):
    o = (IMG - CROP) // 2
    return x[..., o:o + CROP, o:o + CROP]


def build_df():
    lbl = pd.read_csv(LABELS)
    lbl["isic_id"] = lbl["original_path"].apply(lambda p: Path(p).stem)
    sp = pd.read_csv(SPLIT)
    tids = set(sp.loc[sp.split == "test", "isic_id"].astype(str))
    meta = pd.read_csv(META)[["isic_id", "target"]]
    df = lbl[lbl.isic_id.isin(tids)].drop_duplicates("original_path").merge(meta, on="isic_id")
    df = df[df.original_path.apply(lambda p: Path(p).exists())]
    pos = df[df.target == 1]; neg = df[df.target == 0]
    neg = neg.sample(min(len(neg), NEG_PER_POS * len(pos)), random_state=7)
    return pd.concat([pos, neg]).sample(frac=1, random_state=7).reset_index(drop=True)


def q_raw(vs, x_low):
    return vs(x_low)                                           # 现状口径


def q_norm(vs, x_low):
    x224 = F.interpolate(x_low, size=224, mode="bilinear", align_corners=False)
    return vs(_NORM(x224))                                     # visiscore 正确口径


def kl_rows(P, Q, eps=1e-6):
    P = np.clip(P, eps, 1); Q = np.clip(Q, eps, 1)
    return np.sum(P * np.log(P / Q), axis=1)


@torch.no_grad()
def collect(model, vs, b3, df, device):
    def b3_soft(x256):
        return torch.softmax(b3(_NORM(center_crop_224(x256))), dim=-1).cpu().numpy()

    R, D, Er, En, PSr, PSn, ys = [], [], [], [], [], [], []
    for s in range(0, len(df), 4):
        sub = df.iloc[s:s + 4]
        lows, refs, yy = [], [], []
        for j, row in sub.iterrows():
            img = cv2.imread(str(row.original_path))
            if img is None:
                continue
            img = cv2.resize(img, (IMG, IMG), interpolation=cv2.INTER_AREA)
            deg = _degrade_numpy(img, SEVERITY, random.Random(7 + j))
            refs.append(_TT(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)))
            lows.append(_TT(cv2.cvtColor(deg, cv2.COLOR_BGR2RGB)))
            yy.append(int(row.target))
        if not lows:
            continue
        x_low = torch.stack(lows).to(device)
        x_ref = torch.stack(refs).to(device)
        e_raw = model(x_low, q_raw(vs, x_low))
        e_norm = model(x_low, q_norm(vs, x_low))
        R.append(b3_soft(x_ref)); D.append(b3_soft(x_low))
        Er.append(b3_soft(e_raw)); En.append(b3_soft(e_norm))
        # per-image PSNR (vs ref) in [0,1] space
        for i in range(x_ref.shape[0]):
            r = x_ref[i].cpu().numpy()
            PSr.append(10 * np.log10(1.0 / max(((e_raw[i].cpu().numpy() - r) ** 2).mean(), 1e-10)))
            PSn.append(10 * np.log10(1.0 / max(((e_norm[i].cpu().numpy() - r) ** 2).mean(), 1e-10)))
        ys += yy
    return (np.concatenate(R), np.concatenate(D), np.concatenate(Er), np.concatenate(En),
            np.array(PSr), np.array(PSn), np.array(ys))


def metrics(R, Em, ys):
    pr, pe = R[:, 1], Em[:, 1]
    auc_ref = roc_auc_score(ys, pr); auc_enh = roc_auc_score(ys, pe)
    mask = (ys == 1) & (pr > 0.5)
    return {"auc_enh": auc_enh, "dAUC": auc_enh - auc_ref,
            "consistency": float(np.mean((pr > 0.5) == (pe > 0.5))),
            "kl": float(np.mean(kl_rows(R, Em))),
            "dflip": float(np.mean(pe[mask] < 0.5)) if mask.sum() else float("nan")}


def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    vs = load_visiscore(VISISCORE, device)
    b3 = load_b3(B3, device)
    model = load_visienhance(CFG, CKPT_V5, device)
    df = build_df()
    print(f"[qnorm] device={device} n={len(df)} pos={int(df.target.sum())} severity={SEVERITY}")
    R, D, Er, En, PSr, PSn, ys = collect(model, vs, b3, df, device)
    mr = metrics(R, Er, ys); mn = metrics(R, En, ys)
    rows = []
    print(f"\n{'q-mode':8} {'PSNR':>7} {'dAUC':>9} {'consist':>8} {'KL':>7} {'dflip':>7}")
    for tag, m, ps in [("raw", mr, PSr), ("norm", mn, PSn)]:
        print(f"{tag:8} {ps.mean():>7.3f} {m['dAUC']:>+9.4f} {m['consistency']:>8.4f} "
              f"{m['kl']:>7.4f} {m['dflip']:>7.4f}")
        rows.append({"q_mode": tag, "psnr": round(float(ps.mean()), 3),
                     "auc_enh": round(m["auc_enh"], 4), "dAUC": round(m["dAUC"], 4),
                     "consistency": round(m["consistency"], 4), "kl": round(m["kl"], 4),
                     "dflip": round(m["dflip"], 4)})
    # 增强输出在两 q 下差多少
    d_out = float(np.mean(np.abs(Er[:, 1] - En[:, 1])))
    print(f"\n[qnorm] mean|mel_prob(raw)-mel_prob(norm)| = {d_out:.4f}  (≈0 => 增强对 q 不敏感)")
    Path("results").mkdir(exist_ok=True)
    pd.DataFrame(rows).to_csv("results/qnorm_compare.csv", index=False)
    print("saved -> results/qnorm_compare.csv")


if __name__ == "__main__":
    main()
