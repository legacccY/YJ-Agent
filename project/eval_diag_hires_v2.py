"""E3/E7 诊断保持评估 v2: 全阳性 + bootstrap 95% CI + KL 散度 + 危险翻转率.

v1 (eval_diag_hires.py) 修了 oracle 分辨率失配 (256 域, center-crop 224 复刻 B3 VAL_TFM),
但 sample(3000) 只剩 pos=56 -> AUC CI 极宽, Stage1 vs Stage2 的 ΔAUC 差不显著.

本版改进:
  1. 用全部 test 唯一原图 (不 sample 掉阳性) -> pos 最大化.
  2. paired bootstrap (B=2000, 按图重采样) -> AUC_enh / ΔAUC / KL 的 95% CI.
  3. DP-Loss 真正该赢的指标 (Lemma 3 = 逐图诊断特征保持, population AUC 会稀释):
       - consistency : argmax(ref) == argmax(enh) 一致率
       - dangerous_flip : 真黑色素瘤(y=1)中 ref 判阳(argmax=1) 但 enh 翻阴 的比例 (增强致漏诊)
       - KL(P_ref || P_enh) : B3 softmax 信念保持, 越小越好
协议同 v1: degrade(moderate) @256 -> enhance @256 -> CenterCrop224 -> B3. cwd=project.
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
NEG_PER_POS = 30     # 每个阳性配多少阴性 (控规模, 同时压低 base rate 失真); None=全用
BOOT = 2000
_TT = transforms.ToTensor()
_NORM = transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])


def center_crop_224(x):
    o = (IMG - CROP) // 2
    return x[..., o:o + CROP, o:o + CROP]


def build_df():
    lbl = pd.read_csv(LABELS); lbl["isic_id"] = lbl["original_path"].apply(lambda p: Path(p).stem)
    sp = pd.read_csv(SPLIT); tids = set(sp.loc[sp.split == "test", "isic_id"].astype(str))
    meta = pd.read_csv(META)[["isic_id", "target"]]
    df = lbl[lbl.isic_id.isin(tids)].drop_duplicates("original_path").merge(meta, on="isic_id")
    df = df[df.original_path.apply(lambda p: Path(p).exists())]
    pos = df[df.target == 1]
    neg = df[df.target == 0]
    if NEG_PER_POS is not None:
        n_neg = min(len(neg), NEG_PER_POS * len(pos))
        neg = neg.sample(n_neg, random_state=7)
    out = pd.concat([pos, neg]).sample(frac=1, random_state=7).reset_index(drop=True)
    return out


@torch.no_grad()
def collect(model, visiscore, b3, df, device):
    """逐图收 B3 softmax(2维) for ref/deg/enh + label. 返回 per-image 数组 (供 bootstrap)."""
    def b3_soft(imgs_256):
        x = _NORM(center_crop_224(imgs_256))
        return torch.softmax(b3(x), dim=-1).cpu().numpy()   # (B,2)

    R, D, E, ys = [], [], [], []
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
        R.append(b3_soft(x_ref)); D.append(b3_soft(x_low)); E.append(b3_soft(x_enh))
    return (np.concatenate(R), np.concatenate(D), np.concatenate(E), np.array(ys))


def kl_rows(P, Q, eps=1e-6):
    """逐行 KL(P||Q), P/Q shape (N,2)."""
    P = np.clip(P, eps, 1); Q = np.clip(Q, eps, 1)
    return np.sum(P * np.log(P / Q), axis=1)


def metrics(R, D, E, ys, idx=None):
    if idx is not None:
        R, D, E, ys = R[idx], D[idx], E[idx], ys[idx]
    pr, pd_, pe = R[:, 1], D[:, 1], E[:, 1]
    out = {}
    out["auc_ref"] = roc_auc_score(ys, pr)
    out["auc_deg"] = roc_auc_score(ys, pd_)
    out["auc_enh"] = roc_auc_score(ys, pe)
    out["dAUC"] = out["auc_enh"] - out["auc_ref"]          # 带符号 (负=增强后下降)
    out["consistency"] = float(np.mean((pr > 0.5) == (pe > 0.5)))
    out["kl_ref_enh"] = float(np.mean(kl_rows(R, E)))
    # 危险翻转: 真阳 y=1 且 ref 判阳(argmax=1), enh 翻阴(argmax=0) 的比例
    mask = (ys == 1) & (pr > 0.5)
    out["dangerous_flip"] = float(np.mean(pe[mask] < 0.5)) if mask.sum() > 0 else float("nan")
    out["n_dangerous_base"] = int(mask.sum())
    return out


def ci(R, D, E, ys, key, B=BOOT):
    n = len(ys); rng = np.random.RandomState(0); vals = []
    for _ in range(B):
        idx = rng.randint(0, n, n)
        if len(np.unique(ys[idx])) < 2:      # 重采样里没阳性 -> 跳过
            continue
        try:
            vals.append(metrics(R, D, E, ys, idx)[key])
        except ValueError:
            continue
    vals = np.array([v for v in vals if not np.isnan(v)])
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    visiscore = load_visiscore(VISISCORE, device)
    b3 = load_b3(B3, device)
    df = build_df()
    print(f"device={device}  n_test_imgs={len(df)}  pos={int(df.target.sum())}  "
          f"neg={int((df.target == 0).sum())}  (NEG_PER_POS={NEG_PER_POS})")

    rows = []
    for name, path in CKPTS.items():
        model = load_visienhance(CFG, path, device)
        R, D, E, ys = collect(model, visiscore, b3, df, device)
        m = metrics(R, D, E, ys)
        # CI: 关键指标
        ci_enh = ci(R, D, E, ys, "auc_enh")
        ci_d = ci(R, D, E, ys, "dAUC")
        ci_kl = ci(R, D, E, ys, "kl_ref_enh")
        print(f"\n===== {name} =====")
        print(f"  AUC_ref={m['auc_ref']:.4f}  AUC_deg={m['auc_deg']:.4f}  "
              f"AUC_enh={m['auc_enh']:.4f}  [{ci_enh[0]:.3f},{ci_enh[1]:.3f}]")
        print(f"  dAUC={m['dAUC']:+.4f}  [{ci_d[0]:+.3f},{ci_d[1]:+.3f}]  "
              f"(含0={'是' if ci_d[0] <= 0 <= ci_d[1] else '否'})")
        print(f"  KL(ref||enh)={m['kl_ref_enh']:.4f}  [{ci_kl[0]:.3f},{ci_kl[1]:.3f}]")
        print(f"  consistency={m['consistency']:.4f}  "
              f"dangerous_flip={m['dangerous_flip']:.4f} (base n={m['n_dangerous_base']})")
        rows.append({"model": name, **{k: (round(v, 4) if isinstance(v, float) else v)
                                       for k, v in m.items()},
                     "auc_enh_ci": f"[{ci_enh[0]:.3f},{ci_enh[1]:.3f}]",
                     "dAUC_ci": f"[{ci_d[0]:+.3f},{ci_d[1]:+.3f}]",
                     "kl_ci": f"[{ci_kl[0]:.3f},{ci_kl[1]:.3f}]"})

    out = pd.DataFrame(rows)
    print("\n" + out.to_string(index=False))
    Path("results").mkdir(exist_ok=True)
    out.to_csv("results/stage2_diag_hires_v2.csv", index=False)
    print("\nsaved -> results/stage2_diag_hires_v2.csv")


if __name__ == "__main__":
    main()
