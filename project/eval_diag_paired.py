"""E7 配对显著性 + McNemar: Stage1(no DP) vs Stage2(DP) 严格配对.

一次前向同时收 ref/deg/enh_S1/enh_S2 的逐图 B3 softmax (同图同退化) -> 严格配对.
输出:
  - 每模型: AUC_ref/deg/enh, dAUC, 一致率, KL(ref||enh), dangerous_flip  (+ E3 判定)
  - 配对 (S2-S1): ΔAUC_enh / ΔKL 的 bootstrap 95% CI (同一组重采样)  -> E7 方向 + 显著性
  - McNemar: (a) enh vs ref 各模型 (E3 诊断保持)  (b) S2 vs S1 预测正确性 (E7)
协议: degrade(moderate) @256 -> enhance @256 -> CenterCrop224 -> B3. cwd=project.
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

IMG, CROP = 256, 224
NEG_PER_POS = 30
BOOT = 2000
# E9: optional {ckpt_name: cfg} for mixed-architecture eval (FiLM Stage1 vs crossattn
# Stage2). None -> single CFG for all ckpts (v5/v6 behaviour, both FiLM). Set by v7 wrapper.
CFG_MAP = None
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
    pos, neg = df[df.target == 1], df[df.target == 0]
    if NEG_PER_POS is not None:
        neg = neg.sample(min(len(neg), NEG_PER_POS * len(pos)), random_state=7)
    return pd.concat([pos, neg]).sample(frac=1, random_state=7).reset_index(drop=True)


@torch.no_grad()
def collect_all(models, visiscore, b3, df, device):
    """单次循环, 同图同退化 -> ref/deg/{enh per model} 的 B3 softmax. 严格配对."""
    def b3_soft(x256):
        return torch.softmax(b3(_NORM(center_crop_224(x256))), dim=-1).cpu().numpy()

    R, D, ys = [], [], []
    E = {name: [] for name in models}
    for s in range(0, len(df), 4):
        rows = df.iloc[s:s + 4]
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
        R.append(b3_soft(x_ref)); D.append(b3_soft(x_low))
        for name, m in models.items():
            E[name].append(b3_soft(m(x_low, q)))
    R = np.concatenate(R); D = np.concatenate(D); ys = np.array(ys)
    E = {k: np.concatenate(v) for k, v in E.items()}
    return R, D, E, ys


def kl_rows(P, Q, eps=1e-6):
    P = np.clip(P, eps, 1); Q = np.clip(Q, eps, 1)
    return np.sum(P * np.log(P / Q), axis=1)


def model_metrics(R, D, Em, ys, idx=None):
    if idx is not None:
        R, D, Em, ys = R[idx], D[idx], Em[idx], ys[idx]
    pr, pd_, pe = R[:, 1], D[:, 1], Em[:, 1]
    m = {"auc_ref": roc_auc_score(ys, pr), "auc_deg": roc_auc_score(ys, pd_),
         "auc_enh": roc_auc_score(ys, pe)}
    m["dAUC"] = m["auc_enh"] - m["auc_ref"]
    m["consistency"] = float(np.mean((pr > 0.5) == (pe > 0.5)))
    m["kl"] = float(np.mean(kl_rows(R, Em)))
    mask = (ys == 1) & (pr > 0.5)
    m["dangerous_flip"] = float(np.mean(pe[mask] < 0.5)) if mask.sum() else float("nan")
    return m


def mcnemar(correct_a, correct_b):
    """McNemar exact-ish: b=a对b错, c=a错b对. 返回 (b, c, p)."""
    from scipy.stats import binomtest
    b = int(np.sum(correct_a & ~correct_b))
    c = int(np.sum(~correct_a & correct_b))
    n = b + c
    p = 1.0 if n == 0 else binomtest(min(b, c), n, 0.5).pvalue
    return b, c, p


def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    visiscore = load_visiscore(VISISCORE, device)
    b3 = load_b3(B3, device)
    models = {name: load_visienhance((CFG_MAP or {}).get(name, CFG), path, device)
              for name, path in CKPTS.items()}
    df = build_df()
    print(f"device={device}  n={len(df)}  pos={int(df.target.sum())}  neg={int((df.target==0).sum())}")

    R, D, E, ys = collect_all(models, visiscore, b3, df, device)
    names = list(models)
    S1, S2 = names[0], names[1]    # Stage1=no DP, Stage2=DP

    # 每模型指标 + E3 判定
    print("\n--- 每模型 (E3 诊断保持) ---")
    for nm in names:
        m = model_metrics(R, D, E[nm], ys)
        e3_auc = "PASS" if abs(m["dAUC"]) < 0.015 else ("borderline" if abs(m["dAUC"]) < 0.03 else "FAIL")
        e3_con = "PASS" if m["consistency"] > 0.95 else "FAIL"
        # McNemar enh vs ref (预测正确性)
        ya = (R[:, 1] > 0.5) == (ys == 1)
        yb = (E[nm][:, 1] > 0.5) == (ys == 1)
        b, c, p = mcnemar(ya, yb)
        print(f"{nm}: dAUC={m['dAUC']:+.4f}({e3_auc})  一致率={m['consistency']:.4f}({e3_con})  "
              f"KL={m['kl']:.4f}  dflip={m['dangerous_flip']:.4f}  "
              f"McNemar(enh-vs-ref) b={b} c={c} p={p:.3g}")

    # 配对 bootstrap S2 - S1 (同一组重采样)
    print(f"\n--- 配对 S2-S1 (bootstrap B={BOOT}, E7) ---")
    n = len(ys); rng = np.random.RandomState(0)
    dauc, dkl = [], []
    for _ in range(BOOT):
        idx = rng.randint(0, n, n)
        if len(np.unique(ys[idx])) < 2:
            continue
        m1 = model_metrics(R, D, E[S1], ys, idx)
        m2 = model_metrics(R, D, E[S2], ys, idx)
        dauc.append(m2["auc_enh"] - m1["auc_enh"])
        dkl.append(m2["kl"] - m1["kl"])
    dauc, dkl = np.array(dauc), np.array(dkl)
    def ci(v): return np.percentile(v, 2.5), np.percentile(v, 97.5)
    a_lo, a_hi = ci(dauc); k_lo, k_hi = ci(dkl)
    print(f"ΔAUC_enh (S2-S1) = {dauc.mean():+.4f}  CI[{a_lo:+.4f},{a_hi:+.4f}]  "
          f"显著>0={'是' if a_lo > 0 else '否'}")
    print(f"ΔKL    (S2-S1) = {dkl.mean():+.4f}  CI[{k_lo:+.4f},{k_hi:+.4f}]  "
          f"显著<0(DP更好)={'是' if k_hi < 0 else '否'}")

    # McNemar S2 vs S1 (预测正确性, E7 显著性)
    c1 = (E[S1][:, 1] > 0.5) == (ys == 1)
    c2 = (E[S2][:, 1] > 0.5) == (ys == 1)
    b, c, p = mcnemar(c1, c2)
    print(f"McNemar(S2 vs S1 预测正确): b(S1对S2错)={b} c(S1错S2对)={c} p={p:.3g}  "
          f"E7(p<0.01)={'PASS' if p < 0.01 else 'FAIL'}")

    Path("results").mkdir(exist_ok=True)
    pd.DataFrame([{"dAUC_S2_S1": round(float(dauc.mean()), 4), "dAUC_ci_lo": round(a_lo, 4),
                   "dAUC_ci_hi": round(a_hi, 4), "dKL_S2_S1": round(float(dkl.mean()), 4),
                   "dKL_ci_lo": round(k_lo, 4), "dKL_ci_hi": round(k_hi, 4),
                   "mcnemar_b": b, "mcnemar_c": c, "mcnemar_p": p}]
                 ).to_csv("results/stage2_diag_paired.csv", index=False)
    print("\nsaved -> results/stage2_diag_paired.csv")


if __name__ == "__main__":
    main()
