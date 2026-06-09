"""E6 安全边界评估: severe 降质段, 增强后 dAUC 无显著退化.

协议与 eval_diag_paired.py 完全一致, 唯一区别:
  _degrade_numpy severity = "severe"（不是 "moderate"）

流程: test 高质原图 -> _degrade_numpy("severe") @256 -> VisiEnhance(v5) 增强 @256
      -> CenterCrop224 -> B3 softmax
算: auc_ref / auc_deg / auc_enh / dAUC / bootstrap 95% CI / 一致率 / KL / dangerous_flip
PASS 判定: CI 含 0 (ci_lo < 0 < ci_hi) -> 无显著退化 -> PASS
           ci_hi < 0 -> 增强显著拉低 AUC -> FAIL
输出: results/e6_severe.csv
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
from omegaconf import OmegaConf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data.enhance_dataset import _degrade_numpy
from eval_stage2_compare import load_visienhance, load_visiscore, load_b3  # noqa: model loaders

# ── 路径常量（本地 D:/）──────────────────────────────────────────────────────
ROOT      = "D:/YJ-Agent"
LABELS    = f"{ROOT}/data/quality_labels_nocrop.csv"
SPLIT     = f"{ROOT}/data/isic_split.csv"
META      = f"{ROOT}/data/raw/isic2020/train-metadata.csv"
VISISCORE = f"{ROOT}/checkpoints/best_visiscore.pth"
B3        = f"{ROOT}/checkpoints/efficientnet_b3_isic.pth"
CKPT_V5   = f"{ROOT}/project/checkpoints/visienhance/stage2_planA_256_v5/best_visienhance.pth"

# ── 超参（与 eval_diag_paired 完全一致）──────────────────────────────────────
IMG         = 256
CROP        = 224
NEG_PER_POS = 30
BOOT        = 2000
SEVERITY    = "severe"   # ← E6 唯一改动

# model cfg (Plan A 15M)
CFG = OmegaConf.create({"model": {"base_channels": 64, "enc_blocks": [2, 2, 2],
                                   "mid_blocks": 6, "dec_blocks": [2, 2, 2]}})

_TT   = transforms.ToTensor()
_NORM = transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def center_crop_224(x):
    """(B, C, 256, 256) -> (B, C, 224, 224) 中心裁剪."""
    o = (IMG - CROP) // 2
    return x[..., o:o + CROP, o:o + CROP]


def build_df():
    """与 eval_diag_paired.build_df 完全一致: test split + merge target + NEG_PER_POS=30 采样."""
    lbl = pd.read_csv(LABELS)
    lbl["isic_id"] = lbl["original_path"].apply(lambda p: Path(p).stem)
    sp = pd.read_csv(SPLIT)
    tids = set(sp.loc[sp.split == "test", "isic_id"].astype(str))
    meta = pd.read_csv(META)[["isic_id", "target"]]
    df = lbl[lbl.isic_id.isin(tids)].drop_duplicates("original_path").merge(meta, on="isic_id")
    df = df[df.original_path.apply(lambda p: Path(p).exists())]
    pos = df[df.target == 1]
    neg = df[df.target == 0]
    if NEG_PER_POS is not None:
        neg = neg.sample(min(len(neg), NEG_PER_POS * len(pos)), random_state=7)
    return pd.concat([pos, neg]).sample(frac=1, random_state=7).reset_index(drop=True)


def kl_rows(P, Q, eps=1e-6):
    P = np.clip(P, eps, 1)
    Q = np.clip(Q, eps, 1)
    return np.sum(P * np.log(P / Q), axis=1)


@torch.no_grad()
def collect_all(model, visiscore, b3, df, device):
    """单次循环: 同图同退化 -> ref / deg / enh 的 B3 softmax.

    与 eval_diag_paired.collect_all 完全一致, 但:
      - severity = SEVERE（"severe"）
      - 只有 1 个模型, 无需 dict
    """
    def b3_soft(x256):
        """256px 张量 -> softmax (N, 2)."""
        return torch.softmax(b3(_NORM(center_crop_224(x256))), dim=-1).cpu().numpy()

    R, D, E, ys = [], [], [], []
    for s in range(0, len(df), 4):
        rows = df.iloc[s:s + 4]
        lows, refs = [], []
        for j, row in rows.iterrows():
            img = cv2.imread(str(row.original_path))
            if img is None:
                continue
            img = cv2.resize(img, (IMG, IMG), interpolation=cv2.INTER_AREA)
            # ← E6 唯一区别: severity="severe"
            deg = _degrade_numpy(img, SEVERITY, random.Random(7 + j))
            refs.append(_TT(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)))
            lows.append(_TT(cv2.cvtColor(deg, cv2.COLOR_BGR2RGB)))
            ys.append(int(row.target))
        if not lows:
            continue
        x_low = torch.stack(lows).to(device)
        x_ref = torch.stack(refs).to(device)
        q = visiscore(x_low)
        R.append(b3_soft(x_ref))
        D.append(b3_soft(x_low))
        E.append(b3_soft(model(x_low, q)))

    R  = np.concatenate(R)
    D  = np.concatenate(D)
    E  = np.concatenate(E)
    ys = np.array(ys)
    return R, D, E, ys


def compute_metrics(R, D, Em, ys):
    """给定全量数组, 算所有指标."""
    pr, pd_, pe = R[:, 1], D[:, 1], Em[:, 1]
    m = {
        "auc_ref": roc_auc_score(ys, pr),
        "auc_deg": roc_auc_score(ys, pd_),
        "auc_enh": roc_auc_score(ys, pe),
    }
    m["dAUC"]       = m["auc_enh"] - m["auc_ref"]
    m["consistency"] = float(np.mean((pr > 0.5) == (pe > 0.5)))
    m["kl"]          = float(np.mean(kl_rows(R, Em)))
    mask = (ys == 1) & (pr > 0.5)
    m["dangerous_flip"] = float(np.mean(pe[mask] < 0.5)) if mask.sum() else float("nan")
    return m


def bootstrap_dauc(R, D, Em, ys, B=BOOT, seed=0):
    """重采样 B 次, 每次算 dAUC=auc_enh-auc_ref; 跳过单类样本.
    返回 (samples_array, ci_lo, ci_hi).
    与 eval_diag_paired bootstrap 写法一致.
    """
    n = len(ys)
    rng = np.random.RandomState(seed)
    samples = []
    for _ in range(B):
        idx = rng.randint(0, n, n)
        if len(np.unique(ys[idx])) < 2:
            continue
        pr_i  = R[idx, 1]
        pe_i  = Em[idx, 1]
        yi    = ys[idx]
        try:
            dauc_i = roc_auc_score(yi, pe_i) - roc_auc_score(yi, pr_i)
            samples.append(dauc_i)
        except Exception:
            continue
    samples = np.array(samples)
    ci_lo = float(np.percentile(samples, 2.5))
    ci_hi = float(np.percentile(samples, 97.5))
    return samples, ci_lo, ci_hi


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[E6] device={device}  severity={SEVERITY}")

    # 加载模型
    visiscore = load_visiscore(VISISCORE, device)
    b3        = load_b3(B3, device)
    model     = load_visienhance(CFG, CKPT_V5, device)

    # 构建数据集
    df = build_df()
    print(f"[E6] n={len(df)}  pos={int(df.target.sum())}  neg={int((df.target == 0).sum())}")

    # 前向推理
    R, D, E, ys = collect_all(model, visiscore, b3, df, device)

    # 全量指标
    m = compute_metrics(R, D, E, ys)
    print(f"\n[E6] auc_ref={m['auc_ref']:.4f}  auc_deg={m['auc_deg']:.4f}  "
          f"auc_enh={m['auc_enh']:.4f}  dAUC={m['dAUC']:+.4f}")
    print(f"     consistency={m['consistency']:.4f}  KL={m['kl']:.4f}  "
          f"dangerous_flip={m['dangerous_flip']:.4f}")

    # Bootstrap dAUC CI
    samples, ci_lo, ci_hi = bootstrap_dauc(R, D, E, ys, B=BOOT, seed=0)
    print(f"\n[E6] Bootstrap dAUC (B={BOOT}): mean={float(samples.mean()):+.4f}  "
          f"95% CI=[{ci_lo:+.4f}, {ci_hi:+.4f}]")

    # PASS 判定: CI 含 0 = 无显著退化 = PASS; ci_hi < 0 = 显著降 AUC = FAIL
    if ci_hi < 0:
        verdict = "FAIL"
        reason  = "ci_hi < 0: 增强显著拉低诊断 AUC (severe 降质段不安全)"
    elif ci_lo < 0 < ci_hi:
        verdict = "PASS"
        reason  = "CI 含 0: dAUC 无显著退化 (severe 降质段安全边界成立)"
    else:
        # ci_lo > 0: 增强在 severe 段甚至显著提升 AUC, 亦算 PASS
        verdict = "PASS"
        reason  = "ci_lo > 0: 增强在 severe 段显著提升 AUC (超预期)"

    print(f"\n[E6] 判定: {verdict}  ({reason})")

    # 输出 CSV
    Path("results").mkdir(exist_ok=True)
    row = {
        "auc_ref":        round(m["auc_ref"],        4),
        "auc_deg":        round(m["auc_deg"],         4),
        "auc_enh":        round(m["auc_enh"],         4),
        "dAUC":           round(m["dAUC"],            4),
        "dAUC_ci_lo":     round(ci_lo,                4),
        "dAUC_ci_hi":     round(ci_hi,                4),
        "consistency":    round(m["consistency"],     4),
        "kl":             round(m["kl"],              4),
        "dangerous_flip": round(m["dangerous_flip"],  4) if not np.isnan(m["dangerous_flip"]) else float("nan"),
        "pass":           verdict,
    }
    pd.DataFrame([row]).to_csv("results/e6_severe.csv", index=False)
    print("saved -> results/e6_severe.csv")


if __name__ == "__main__":
    main()
