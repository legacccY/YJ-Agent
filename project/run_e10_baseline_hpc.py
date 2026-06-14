"""E10 通用 SOTA baseline 对比 (HPC GPU): VisiEnhance (v5 FiLM DP) vs 1 个 SOTA baseline.

zero-shot: baseline 用官方预训练权重直接 inference, 无 quality-conditioning / 无 DP-loss.
唯一变量 = "我们的 DP 增强 vs 通用 SOTA 增强". 严格配对 (同图同 degrade(moderate)):
单遍循环同时收 VisiEnhance/baseline 的 per-image PSNR/SSIM (vs 高质原图) + B3 softmax.

names[0]=VisiEnhance, names[1]=baseline -> paired ΔAUC/ΔKL = baseline − VisiEnhance.
预期叙事 (E10 核心): baseline PSNR/SSIM 可能有竞争力 (纯图像质量优化), 但 dAUC/
dangerous_flip 明显劣 (无 diagnosis-preserving 约束) -> 坐实 quality-conditioning+DP 卖点.

口径锁 (会话 28): PSNR=per-image mean. 降质=存盘 mixed 文件 (light+medium+heavy),
对齐 run_e1_ablation_hpc EnhanceDataset(severity='mixed') 协议 -> VisiEnhance PSNR 与
E1 32.74dB 同 caliber (残差仅来自 melanoma 平衡子集 vs E1 全 test split). 红线 4 (不用约值).

用法: python run_e10_baseline_hpc.py --method nafnet
产出: results/e10_<method>.csv. cwd=code/.
"""
import argparse
import importlib
import random
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import torch
from skimage.metrics import peak_signal_noise_ratio, structural_similarity
from sklearn.metrics import roc_auc_score
from torchvision import transforms

sys.path.insert(0, ".")

import eval_stage2_compare as E
import eval_diag_paired as P
from data.enhance_dataset import _degrade_numpy
from omegaconf import OmegaConf

ROOT = "/gpfs/work/bio/jiayu2403/visienhance"
E.LABELS = P.LABELS = f"{ROOT}/data/quality_labels_nocrop_hpc.csv"
E.SPLIT = P.SPLIT = f"{ROOT}/data/isic_split.csv"
E.META = P.META = f"{ROOT}/data/train-metadata.csv"
E.VISISCORE = f"{ROOT}/checkpoints/best_visiscore.pth"
E.B3 = f"{ROOT}/checkpoints/efficientnet_b3_isic.pth"

VE_NAME = "VisiEnhance (v5 FiLM DP)"
VE_CFG = f"{ROOT}/configs/visienhance_s2_planA_256_v5_hpc.yaml"
VE_CKPT = f"{ROOT}/checkpoints/visienhance/stage2_planA_256_v5/best_visienhance.pth"
WEIGHTS_DIR = f"{ROOT}/checkpoints/baselines"

IMG, CROP = 256, 224
NEG_PER_POS = 30
BOOT = 2000
_TT = transforms.ToTensor()
_NORM = transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])


def center_crop_224(x):
    o = (IMG - CROP) // 2
    return x[..., o:o + CROP, o:o + CROP]


@torch.no_grad()
def collect(models, visiscore, b3, df, device):
    """单遍同图同退化 -> 每模型: B3 softmax(ref/deg/enh) + per-image PSNR/SSIM(enh vs ref)."""
    def b3_soft(x256):
        return torch.softmax(b3(_NORM(center_crop_224(x256))), dim=-1).cpu().numpy()

    R, D, ys = [], [], []
    Esoft = {n: [] for n in models}
    Epsnr = {n: [] for n in models}
    Essim = {n: [] for n in models}
    for s in range(0, len(df), 4):
        rows = df.iloc[s:s + 4]
        lows, refs = [], []
        for j, row in rows.iterrows():
            ref = cv2.imread(str(row.original_path))
            low = cv2.imread(str(row.degraded_path))   # 存盘 mixed 降质 (对齐 E1)
            if ref is None or low is None:
                continue
            if ref.shape[:2] != (IMG, IMG):
                ref = cv2.resize(ref, (IMG, IMG), interpolation=cv2.INTER_AREA)
            if low.shape[:2] != (IMG, IMG):
                low = cv2.resize(low, (IMG, IMG), interpolation=cv2.INTER_AREA)
            refs.append(_TT(cv2.cvtColor(ref, cv2.COLOR_BGR2RGB)))
            lows.append(_TT(cv2.cvtColor(low, cv2.COLOR_BGR2RGB)))
            ys.append(int(row.target))
        if not lows:
            continue
        x_low = torch.stack(lows).to(device)
        x_ref = torch.stack(refs).to(device)
        q = visiscore(x_low)
        R.append(b3_soft(x_ref)); D.append(b3_soft(x_low))
        ref_np = x_ref.cpu()
        for name, m in models.items():
            enh = m(x_low, q).clamp(0, 1)
            Esoft[name].append(b3_soft(enh))
            enh_np = enh.cpu()
            for i in range(enh_np.shape[0]):
                r = (ref_np[i].permute(1, 2, 0).numpy() * 255).astype(np.uint8)
                e = (enh_np[i].permute(1, 2, 0).numpy() * 255).clip(0, 255).astype(np.uint8)
                Epsnr[name].append(peak_signal_noise_ratio(r, e, data_range=255))
                Essim[name].append(structural_similarity(r, e, channel_axis=2, data_range=255))
    R = np.concatenate(R); D = np.concatenate(D); ys = np.array(ys)
    Esoft = {k: np.concatenate(v) for k, v in Esoft.items()}
    return R, D, Esoft, Epsnr, Essim, ys


def build_df_stored():
    """E1-caliber 子集: 存盘预生成降质文件 + mixed 严重度 (全 light+medium+heavy) +
    melanoma 平衡 (NEG_PER_POS 个 neg *图* / pos *图*). 对齐 run_e1_ablation_hpc 的
    EnhanceDataset(severity='mixed') 降质算子, 使 VisiEnhance PSNR 与 E1 32.74dB 同口径
    (残差仅 = 此 melanoma 富集子集 vs E1 全 test split)."""
    lbl = pd.read_csv(E.LABELS); lbl["isic_id"] = lbl["original_path"].apply(lambda p: Path(p).stem)
    sp = pd.read_csv(P.SPLIT); tids = set(sp.loc[sp.split == "test", "isic_id"].astype(str))
    meta = pd.read_csv(P.META)[["isic_id", "target"]]
    df = lbl[lbl.isic_id.isin(tids)].merge(meta, on="isic_id")          # 不 drop_duplicates -> 全 3 档 = mixed
    df = df[df.original_path.apply(lambda p: Path(p).exists())
            & df.degraded_path.apply(lambda p: Path(p).exists())]
    pos_ids = df[df.target == 1].isic_id.unique()
    neg_ids = df[df.target == 0].isic_id.unique()
    rng = np.random.RandomState(7)
    k = min(len(neg_ids), NEG_PER_POS * len(pos_ids))
    keep = set(pos_ids) | set(rng.choice(neg_ids, k, replace=False))
    return df[df.isic_id.isin(keep)].sample(frac=1, random_state=7).reset_index(drop=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--method", required=True, help="baselines/run_<method>_inference.py 的 <method>")
    args = ap.parse_args()
    method = args.method.lower()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    visiscore = E.load_visiscore(E.VISISCORE, device)
    b3 = E.load_b3(E.B3, device)
    ve = E.load_visienhance(OmegaConf.load(VE_CFG), VE_CKPT, device)
    base_mod = importlib.import_module(f"baselines.run_{method}_inference")
    base = base_mod.build(device, WEIGHTS_DIR)
    method_name = getattr(base_mod, "DISPLAY_NAME", method)

    models = {VE_NAME: ve, method_name: base}    # names[0]=VisiEnhance, names[1]=baseline
    df = build_df_stored()
    print(f"E10 {method_name}  device={device}  n={len(df)}  "
          f"pos={int(df.target.sum())}  neg={int((df.target==0).sum())}")

    R, D, Esoft, Epsnr, Essim, ys = collect(models, visiscore, b3, df, device)
    names = list(models)
    VE, BL = names[0], names[1]

    print("\n--- 每模型 (E1 图像质量 + E3 诊断保持) ---")
    csv_rows = []
    for nm in names:
        m = P.model_metrics(R, D, Esoft[nm], ys)
        psnr, ssim = float(np.mean(Epsnr[nm])), float(np.mean(Essim[nm]))
        e3_auc = "PASS" if abs(m["dAUC"]) < 0.015 else ("borderline" if abs(m["dAUC"]) < 0.03 else "FAIL")
        e3_con = "PASS" if m["consistency"] > 0.95 else "FAIL"
        ya = (R[:, 1] > 0.5) == (ys == 1)
        yb = (Esoft[nm][:, 1] > 0.5) == (ys == 1)
        b, c, p = P.mcnemar(ya, yb)
        print(f"{nm}: PSNR={psnr:.2f}(per-img)  SSIM={ssim:.4f}  dAUC={m['dAUC']:+.4f}({e3_auc})  "
              f"一致率={m['consistency']:.4f}({e3_con})  KL={m['kl']:.4f}  dflip={m['dangerous_flip']:.4f}  "
              f"McNemar(enh-vs-ref) b={b} c={c} p={p:.3g}")
        csv_rows.append({"model": nm, "psnr_perimg": round(psnr, 2), "ssim": round(ssim, 4),
                         "dAUC": round(m["dAUC"], 4), "consistency": round(m["consistency"], 4),
                         "kl": round(m["kl"], 4), "dangerous_flip": round(m["dangerous_flip"], 4),
                         "mcnemar_enh_ref_p": round(p, 4)})

    # 配对 bootstrap baseline − VisiEnhance (同一组重采样)
    print(f"\n--- 配对 baseline−VisiEnhance (bootstrap B={BOOT}, E10) ---")
    n = len(ys); rng = np.random.RandomState(0)
    dauc, dkl = [], []
    for _ in range(BOOT):
        idx = rng.randint(0, n, n)
        if len(np.unique(ys[idx])) < 2:
            continue
        m_ve = P.model_metrics(R, D, Esoft[VE], ys, idx)
        m_bl = P.model_metrics(R, D, Esoft[BL], ys, idx)
        dauc.append(m_bl["auc_enh"] - m_ve["auc_enh"])
        dkl.append(m_bl["kl"] - m_ve["kl"])
    dauc, dkl = np.array(dauc), np.array(dkl)
    def ci(v): return float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))
    a_lo, a_hi = ci(dauc); k_lo, k_hi = ci(dkl)
    print(f"ΔAUC_enh (baseline−VE) = {dauc.mean():+.4f}  CI[{a_lo:+.4f},{a_hi:+.4f}]  "
          f"baseline 显著更差(<0)={'是' if a_hi < 0 else '否'}")
    print(f"ΔKL    (baseline−VE) = {dkl.mean():+.4f}  CI[{k_lo:+.4f},{k_hi:+.4f}]  "
          f"baseline 显著更差(>0)={'是' if k_lo > 0 else '否'}")

    c_ve = (Esoft[VE][:, 1] > 0.5) == (ys == 1)
    c_bl = (Esoft[BL][:, 1] > 0.5) == (ys == 1)
    b, c, p = P.mcnemar(c_ve, c_bl)
    print(f"McNemar(VE vs baseline 预测正确): b(VE对BL错)={b} c(VE错BL对)={c} p={p:.3g}")

    Path("results").mkdir(exist_ok=True)
    paired = {"model": f"PAIRED({BL}−{VE})", "dAUC": round(float(dauc.mean()), 4),
              "dAUC_ci_lo": round(a_lo, 4), "dAUC_ci_hi": round(a_hi, 4),
              "dKL": round(float(dkl.mean()), 4), "dKL_ci_lo": round(k_lo, 4),
              "dKL_ci_hi": round(k_hi, 4), "mcnemar_b": b, "mcnemar_c": c, "mcnemar_p": p}
    out = f"results/e10_{method}.csv"
    pd.DataFrame(csv_rows + [paired]).to_csv(out, index=False)
    print(f"\nsaved -> {out}")


if __name__ == "__main__":
    main()
