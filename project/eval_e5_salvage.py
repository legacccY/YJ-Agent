"""E5 双通道效率: SalvageRate (norm-q 路由版).

会话21 发现 visiscore 喂错 (raw 而非 NORM224) 致 q̄ 退化. 本脚本:
  - 增强: 用 raw-q 作 FiLM 条件 (模型训练口径, 已验证比 norm-q 更优, 见 qnorm_compare)
  - 路由/分层: 用 norm-q̄ = visiscore(NORM(resize224(deg))).mean (正确质量信号, agent 路由用)
两个 q 分离 = 用户拍的「独立 norm-q 路由标量」.

q̄ 尺度即便用 NORM 仍压缩 (severe≈0.446, 到不了 ACCEPTANCE 的 <0.25), 故弃死阈值,
改按退化 severity {mild,moderate,severe} 分层 + 报每层 norm-q̄ (可解释 + 不武断).

定义:
  pred=(B3 mel_prob>0.5); correct=(pred==target)
  salvageable=NOT correct_deg;  salvaged=salvageable AND correct_enh
  SalvageRate=#salvaged/#salvageable;  DamageRate=#(correct_deg AND NOT correct_enh)/#correct_deg
输出 results/e5_salvage.csv. cwd=code/ (HPC 由 run_e5_hpc.py 覆盖路径).
"""
import random
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
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
OUT_SUFFIX = ""   # v6 launcher sets "_v6" so re-eval does not overwrite v5 baseline csv

IMG, CROP = 256, 224
NEG_PER_POS = 30
SEVERITIES = ["mild", "moderate", "severe"]
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


@torch.no_grad()
def collect(model, vs, b3, df, device):
    def mel_prob(x256):
        return torch.softmax(b3(_NORM(center_crop_224(x256))), dim=-1)[:, 1].cpu().numpy()

    rows = []
    for sev in SEVERITIES:
        for s in range(0, len(df), 4):
            sub = df.iloc[s:s + 4]
            lows, ys = [], []
            for j, row in sub.iterrows():
                img = cv2.imread(str(row.original_path))
                if img is None:
                    continue
                img = cv2.resize(img, (IMG, IMG), interpolation=cv2.INTER_AREA)
                deg = _degrade_numpy(img, sev, random.Random(7 + j))
                lows.append(_TT(cv2.cvtColor(deg, cv2.COLOR_BGR2RGB)))
                ys.append(int(row.target))
            if not lows:
                continue
            x_low = torch.stack(lows).to(device)
            q_raw = vs(x_low)                                   # 增强条件 (训练口径)
            x224 = F.interpolate(x_low, size=224, mode="bilinear", align_corners=False)
            qbar_route = vs(_NORM(x224)).mean(dim=1).cpu().numpy()   # 路由信号 (正确口径)
            pd_ = mel_prob(x_low)
            pe = mel_prob(model(x_low, q_raw))
            for k, y in enumerate(ys):
                rows.append({"sev": sev, "target": y, "qbar_route": float(qbar_route[k]),
                             "correct_deg": int((pd_[k] > 0.5) == (y == 1)),
                             "correct_enh": int((pe[k] > 0.5) == (y == 1))})
    return pd.DataFrame(rows)


def stats(d):
    salvageable = int((d.correct_deg == 0).sum())
    salvaged = int(((d.correct_deg == 0) & (d.correct_enh == 1)).sum())
    correct_deg = int((d.correct_deg == 1).sum())
    damaged = int(((d.correct_deg == 1) & (d.correct_enh == 0)).sum())
    return {"n": len(d), "qbar_route_mean": round(float(d.qbar_route.mean()), 4),
            "salvageable": salvageable, "salvaged": salvaged,
            "SalvageRate": round(salvaged / salvageable, 4) if salvageable else float("nan"),
            "DamageRate": round(damaged / correct_deg, 4) if correct_deg else float("nan"),
            "n_pos": int((d.target == 1).sum())}


def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[E5] device={device}  severities={SEVERITIES} (enhance=raw-q, route=norm-q)")
    vs = load_visiscore(VISISCORE, device)
    b3 = load_b3(B3, device)
    model = load_visienhance(CFG, CKPT_V5, device)
    df = build_df()
    print(f"[E5] base test n={len(df)} pos={int(df.target.sum())} x{len(SEVERITIES)} sev")
    data = collect(model, vs, b3, df, device)
    print(f"[E5] total={len(data)}  norm-qbar range [{data.qbar_route.min():.3f},{data.qbar_route.max():.3f}]")

    out = []
    print(f"\n{'stratum':14}{'n':>6}{'norm-q̄':>9}{'salvable':>9}{'SalvageRate':>12}{'DamageRate':>11}{'n_pos':>6}")
    # 按 severity 分层 (主)
    for sev in SEVERITIES:
        st = stats(data[data.sev == sev]); st = {"stratum": f"sev:{sev}", **st}
        out.append(st)
        print(f"{st['stratum']:14}{st['n']:>6}{st['qbar_route_mean']:>9}{st['salvageable']:>9}"
              f"{st['SalvageRate']:>12}{st['DamageRate']:>11}{st['n_pos']:>6}")
    # 按 norm-q̄ 三分位 (副, 数据驱动 band)
    qt = data.qbar_route.quantile([1/3, 2/3]).values
    data["qband"] = np.where(data.qbar_route < qt[0], "low",
                             np.where(data.qbar_route < qt[1], "mid", "high"))
    print(f"  (norm-q̄ terciles: low<{qt[0]:.3f} mid<{qt[1]:.3f} high)")
    for b in ["low", "mid", "high"]:
        st = stats(data[data.qband == b]); st = {"stratum": f"qband:{b}", **st}
        out.append(st)
        print(f"{st['stratum']:14}{st['n']:>6}{st['qbar_route_mean']:>9}{st['salvageable']:>9}"
              f"{st['SalvageRate']:>12}{st['DamageRate']:>11}{st['n_pos']:>6}")

    Path("results").mkdir(exist_ok=True)
    pd.DataFrame(out).to_csv(f"results/e5_salvage{OUT_SUFFIX}.csv", index=False)
    data.to_csv(f"results/e5_salvage{OUT_SUFFIX}_persample.csv", index=False)
    print(f"\nsaved -> results/e5_salvage{OUT_SUFFIX}.csv (+ _persample.csv)")


if __name__ == "__main__":
    main()
