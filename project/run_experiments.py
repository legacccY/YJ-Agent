"""ITB 全量实验脚本：Baseline A (EfficientNet-B3) + D/E/F Q-VIB 消融 + TS 校准。

Baselines:
  A   EfficientNet-B3 (Direct)   checkpoints/efficientnet_b3_isic.pth  (外部 baseline，无质量感知)
  D   Std VIB                    checkpoints/stdvib/best_qad.pth
  E   Adaptive Prior             checkpoints/adaptive/best_qad.pth
  F   Q-VIB Full (Ours)          checkpoints/efnet/best_qad.pth
  G   Q-VIB+TokFT (Suppl.)       checkpoints/efnet_tokft/best_qad.pth
  TS  Std VIB + Temperature Scaling (post-hoc, Guo et al. 2017)

每个样本额外输出：kl_term, prior_var (供 Lemma 1 / Fig 5 使用)

Usage:
  cd D:/YJ-Agent/project
  python run_experiments.py               # 跑全部
  python run_experiments.py --baseline D  # 只跑 Std VIB
  python run_experiments.py --baseline TS # 只跑 Temperature Scaling
"""
import argparse, json, sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from PIL import Image
from torchvision import transforms
from torchvision.models import efficientnet_b3
import torch.nn as nn
from omegaconf import OmegaConf
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent))
from models.q_vib_encoder import QVIBEncoder
from models.qad_classifier import QADClassifier
from models.quality_adaptive_prior import QualityAdaptivePrior
from agent.tools import quality_assess, extract_features
from benchmark.metrics import summary_metrics
from baselines.focal_loss_baseline import FocalMLP

ITB_CSV  = "results/itb_subsets.csv"
OUT_CSV  = "results/itb_results.csv"
PRED_CSV = "results/itb_predictions.csv"
N_MC     = 20
DEVICE   = torch.device("cuda" if torch.cuda.is_available() else "cpu")

SEED_CKPT_DIRS = {
    "D": "D:/YJ-Agent/checkpoints/stdvib",
    "E": "D:/YJ-Agent/checkpoints/adaptive",
    "F": "D:/YJ-Agent/checkpoints/efnet",
    "G": "D:/YJ-Agent/checkpoints/efnet_tokft",
}

BASELINES = {
    "A":  {"name": "EfficientNet-B3 (Direct)", "type": "b3"},
    "D":  {"name": "Std VIB",        "ckpt": "D:/YJ-Agent/checkpoints/stdvib/best_qad.pth",      "use_tok": False, "use_prior": False},
    "E":  {"name": "Adaptive Prior", "ckpt": "D:/YJ-Agent/checkpoints/adaptive/best_qad.pth",    "use_tok": False, "use_prior": True},
    "F":  {"name": "Q-VIB Full",     "ckpt": "D:/YJ-Agent/checkpoints/efnet/best_qad.pth",       "use_tok": True,  "use_prior": True},
    "G":  {"name": "Q-VIB+TokFT",    "ckpt": "D:/YJ-Agent/checkpoints/efnet_tokft/best_qad.pth", "use_tok": True,  "use_prior": True},
    "TS": {"name": "Std VIB + TS",   "ckpt": "D:/YJ-Agent/checkpoints/stdvib/best_qad.pth",      "type": "ts",
           "temp_path": "D:/YJ-Agent/checkpoints/stdvib/temperature.json",
           "use_tok": False, "use_prior": False},
    "H":  {"name": "Focal+LS",       "ckpt": "D:/YJ-Agent/checkpoints/focal/best.pth",            "type": "focal"},
    "I":  {"name": "MC Dropout",     "ckpt": "D:/YJ-Agent/checkpoints/mcdropout/best_qad.pth",   "type": "mcdropout",
           "dropout": 0.3, "use_tok": False, "use_prior": False},
    "J":  {"name": "Deep Ensemble",  "type": "ensemble",
           "ckpts": [
               "D:/YJ-Agent/checkpoints/stdvib/best_qad.pth",
               "D:/YJ-Agent/checkpoints/stdvib_s123/best_qad.pth",
               "D:/YJ-Agent/checkpoints/stdvib_s2024/best_qad.pth",
               "D:/YJ-Agent/checkpoints/stdvib_s456/best_qad.pth",
               "D:/YJ-Agent/checkpoints/stdvib_s789/best_qad.pth",
           ],
           "use_tok": False, "use_prior": False},
}

# ImageNet preprocessing for EfficientNet-B3
B3_TFM = transforms.Compose([
    transforms.Resize(256),
    transforms.CenterCrop(224),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
])

# Quality-adaptive prior (default params from training)
PRIOR = QualityAdaptivePrior(sigma0_sq=0.1, tau=0.5, alpha=5.0).to(DEVICE)


# ── Model loaders ─────────────────────────────────────────────────────────────

def load_qvib_model(ckpt_path: str, efnet_dim: int = 1280, dropout: float = 0.2):
    ckpt = torch.load(ckpt_path, map_location=DEVICE)
    encoder = QVIBEncoder(
        abcd_dim=4, q_dim=5, d_model=128, n_heads=4, latent_dim=64, efnet_dim=efnet_dim
    ).to(DEVICE).eval()
    classifier = QADClassifier(latent_dim=64, hidden_dim=128, num_classes=2, dropout=dropout).to(DEVICE).eval()
    encoder.load_state_dict(ckpt["encoder"])
    classifier.load_state_dict(ckpt["classifier"])
    return encoder, classifier


def load_b3_model():
    model = efficientnet_b3(weights=None)
    model.classifier[1] = nn.Linear(1536, 2)
    ckpt = torch.load("D:/YJ-Agent/checkpoints/efficientnet_b3_isic.pth", map_location=DEVICE)
    model.load_state_dict(ckpt["model"])
    return model.to(DEVICE).eval()


# ── Inference ─────────────────────────────────────────────────────────────────

def _seed_from_path(image_path: str) -> int:
    """Stable per-sample seed from image_path (deterministic, order-independent)."""
    import hashlib
    return int(hashlib.md5(str(image_path).encode("utf-8")).hexdigest()[:8], 16)


def mc_predict(encoder, classifier, abcd_t, q_t, ef_t, n_mc, seed: int | None = None):
    """MC sampling. When seed is provided, RNG is reset for per-sample reproducibility."""
    if seed is not None:
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    with torch.no_grad():
        mu, lsq = encoder(abcd_t, q_t, efnet_feat=ef_t)
        probs_list = []
        for _ in range(n_mc):
            z = encoder.reparameterize(mu, lsq)
            probs_list.append(F.softmax(classifier(z), -1))
    return torch.stack(probs_list).mean(0), mu, lsq   # (B,2), (B,d), (B,d)


def compute_kl(mu, lsq, q_t, use_adaptive_prior: bool) -> float:
    with torch.no_grad():
        if use_adaptive_prior:
            kl = PRIOR.kl_divergence(mu, lsq, q_t)
            prior_var = float(PRIOR.prior_variance(q_t).mean().item())
        else:
            sigma_sq = lsq.exp().clamp(1e-8)
            kl = 0.5 * (sigma_sq + mu.pow(2) - 1.0 - lsq).sum(dim=-1)
            prior_var = 1.0
        return float(kl.mean().item()), prior_var


def deterministic_predict(encoder, classifier, abcd_t, q_t, ef_t, T: float):
    """TS: deterministic forward (use mu, no sampling), divide logits by T, softmax."""
    with torch.no_grad():
        mu, lsq = encoder(abcd_t, q_t, efnet_feat=ef_t)
        logits = classifier(mu)
        probs = F.softmax(logits / T, dim=-1)
    return probs, mu, lsq


# ── Per-baseline runners ───────────────────────────────────────────────────────

def run_b3_baseline(itb: pd.DataFrame, pred_rows: list) -> list[dict]:
    print("\n[A] EfficientNet-B3 (Direct)")
    b3 = load_b3_model()
    rows = []
    for subset in sorted(itb["subset"].unique()):
        sub = itb[itb["subset"] == subset]
        all_probs, all_targets, all_qbar = [], [], []
        all_ids = []
        for _, row in tqdm(sub.iterrows(), total=len(sub), desc=subset, leave=False):
            img_bgr = cv2.imread(str(row["image_path"]))
            if img_bgr is None:
                continue
            img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            pil = Image.fromarray(img_rgb)
            t = B3_TFM(pil).unsqueeze(0).to(DEVICE)
            with torch.no_grad():
                logits = b3(t)
                prob = F.softmax(logits, -1)[0].cpu().numpy()
            all_probs.append(prob)
            all_targets.append(int(row["target"]))
            all_qbar.append(float(row["qbar"]))
            all_ids.append(str(row["isic_id"]))

        if not all_probs:
            continue
        probs_arr   = np.array(all_probs)
        targets_arr = np.array(all_targets)
        qbar_arr    = np.array(all_qbar)
        m = summary_metrics(probs_arr[:, 1], targets_arr, qbar_arr)
        row_out = {"baseline": "A", "baseline_name": "EfficientNet-B3 (Direct)", "subset": subset,
                   "n": len(targets_arr),
                   **{k: v for k, v in m.items() if k != "qbar_ece_segments"}}
        print(f"  {subset}: AUC={m['auc']:.3f}  ECE={m['ece']:.3f}  F1={m['f1']:.3f}")
        rows.append(row_out)
        for i in range(len(targets_arr)):
            pred_rows.append({
                "baseline": "A", "baseline_name": "EfficientNet-B3 (Direct)", "subset": subset,
                "image_name": all_ids[i],
                "prob_pos": float(probs_arr[i, 1]), "target": int(targets_arr[i]),
                "qbar": float(qbar_arr[i]), "kl_term": 0.0, "prior_var": 0.0,
            })
    return rows


def run_ts_baseline(itb: pd.DataFrame, pred_rows: list) -> list[dict]:
    """Std VIB + Temperature Scaling: deterministic logits / T, softmax."""
    cfg = BASELINES["TS"]
    print(f"\n[TS] {cfg['name']}")
    with open(cfg["temp_path"]) as f:
        T = float(json.load(f)["T"])
    print(f"  Temperature T = {T:.4f}  (loaded from {cfg['temp_path']})")

    encoder, classifier = load_qvib_model(cfg["ckpt"])
    encoder.tokenizer.forward = lambda q: torch.zeros(q.shape[0], device=q.device)

    rows = []
    for subset in sorted(itb["subset"].unique()):
        sub = itb[itb["subset"] == subset]
        all_probs, all_targets, all_qbar = [], [], []
        all_ids = []
        for _, row in tqdm(sub.iterrows(), total=len(sub), desc=subset, leave=False):
            img = cv2.imread(str(row["image_path"]))
            if img is None:
                continue
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

            feats  = extract_features(img)
            abcd_t = torch.tensor(feats.abcd,        dtype=torch.float32).unsqueeze(0).to(DEVICE)
            q_t    = torch.tensor(feats.q_vector,    dtype=torch.float32).unsqueeze(0).to(DEVICE)
            ef_t   = torch.tensor(feats.efnet_feat,  dtype=torch.float32).unsqueeze(0).to(DEVICE)

            probs, _, _ = deterministic_predict(encoder, classifier, abcd_t, q_t, ef_t, T)
            all_probs.append(probs[0].cpu().numpy())
            all_targets.append(int(row["target"]))
            all_qbar.append(float(row["qbar"]))
            all_ids.append(str(row["isic_id"]))

        if not all_probs:
            continue
        probs_arr   = np.array(all_probs)
        targets_arr = np.array(all_targets)
        qbar_arr    = np.array(all_qbar)
        m = summary_metrics(probs_arr[:, 1], targets_arr, qbar_arr)
        rows.append({"baseline": "TS", "baseline_name": cfg["name"], "subset": subset,
                     "n": len(targets_arr),
                     **{k: v for k, v in m.items() if k != "qbar_ece_segments"}})
        print(f"  {subset}: AUC={m['auc']:.3f}  ECE={m['ece']:.3f}  entropy={m['mean_entropy']:.3f}")
        for i in range(len(targets_arr)):
            pred_rows.append({
                "baseline": "TS", "baseline_name": cfg["name"], "subset": subset,
                "image_name": all_ids[i],
                "prob_pos": float(probs_arr[i, 1]), "target": int(targets_arr[i]),
                "qbar": float(qbar_arr[i]), "kl_term": 0.0, "prior_var": 0.0,
            })
    return rows


def run_focal_baseline(itb: pd.DataFrame, pred_rows: list) -> list[dict]:
    """Focal+LS (Baseline H): FocalMLP 1284D input, deterministic forward."""
    cfg = BASELINES["H"]
    print(f"\n[H] {cfg['name']}")
    ckpt = torch.load(cfg["ckpt"], map_location=DEVICE)
    model = FocalMLP().to(DEVICE).eval()
    model.load_state_dict(ckpt["model"])
    print(f"  Loaded checkpoint: epoch={ckpt.get('epoch', '?')+1}  val_auc={ckpt.get('val_auc', float('nan')):.4f}")

    rows = []
    for subset in sorted(itb["subset"].unique()):
        sub = itb[itb["subset"] == subset]
        all_probs, all_targets, all_qbar = [], [], []
        all_ids = []

        for _, row in tqdm(sub.iterrows(), total=len(sub), desc=subset, leave=False):
            img = cv2.imread(str(row["image_path"]))
            if img is None:
                continue
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

            feats  = extract_features(img)
            abcd_t = torch.tensor(feats.abcd,       dtype=torch.float32).to(DEVICE)   # (4,)
            ef_t   = torch.tensor(feats.efnet_feat, dtype=torch.float32).to(DEVICE)   # (1280,)

            x = torch.cat([ef_t, abcd_t], dim=-1).unsqueeze(0)   # (1, 1284)
            with torch.no_grad():
                logits = model(x)
                probs  = F.softmax(logits, dim=-1)[0].cpu().numpy()

            all_probs.append(probs)
            all_targets.append(int(row["target"]))
            all_qbar.append(float(row["qbar"]))
            all_ids.append(str(row["isic_id"]))

        if not all_probs:
            continue

        probs_arr   = np.array(all_probs)
        targets_arr = np.array(all_targets)
        qbar_arr    = np.array(all_qbar)
        m = summary_metrics(probs_arr[:, 1], targets_arr, qbar_arr)
        row_out = {"baseline": "H", "baseline_name": cfg["name"], "subset": subset,
                   "n": len(targets_arr),
                   **{k: v for k, v in m.items() if k != "qbar_ece_segments"}}
        print(f"  {subset}: AUC={m['auc']:.3f}  ECE={m['ece']:.3f}  entropy={m['mean_entropy']:.3f}")
        rows.append(row_out)

        for i in range(len(targets_arr)):
            pred_rows.append({
                "baseline": "H", "baseline_name": cfg["name"], "subset": subset,
                "image_name": all_ids[i],
                "prob_pos": float(probs_arr[i, 1]), "target": int(targets_arr[i]),
                "qbar": float(qbar_arr[i]), "kl_term": 0.0, "prior_var": 0.0,
            })
    return rows


def run_qvib_baseline(key: str, cfg: dict, itb: pd.DataFrame, pred_rows: list) -> list[dict]:
    print(f"\n[{key}] {cfg['name']}")
    encoder, classifier = load_qvib_model(cfg["ckpt"], efnet_dim=cfg.get("efnet_dim", 1280))
    if not cfg["use_tok"]:
        encoder.tokenizer.forward = lambda q: torch.zeros(q.shape[0], device=q.device)

    rows = []
    for subset in sorted(itb["subset"].unique()):
        sub = itb[itb["subset"] == subset]
        all_probs, all_targets, all_qbar = [], [], []
        all_kl, all_prior_var = [], []
        all_ids = []

        for _, row in tqdm(sub.iterrows(), total=len(sub), desc=subset, leave=False):
            img = cv2.imread(str(row["image_path"]))
            if img is None:
                continue
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

            feats  = extract_features(img)
            abcd_t = torch.tensor(feats.abcd, dtype=torch.float32).unsqueeze(0).to(DEVICE)
            q_t    = torch.tensor(feats.q_vector, dtype=torch.float32).unsqueeze(0).to(DEVICE)
            ef_t   = torch.tensor(feats.efnet_feat, dtype=torch.float32).unsqueeze(0).to(DEVICE)

            sample_seed = _seed_from_path(row["image_path"])
            probs, mu, lsq = mc_predict(encoder, classifier, abcd_t, q_t, ef_t, N_MC, seed=sample_seed)
            kl, pvar = compute_kl(mu, lsq, q_t, cfg["use_prior"])

            all_probs.append(probs[0].cpu().numpy())
            all_targets.append(int(row["target"]))
            all_qbar.append(float(row["qbar"]))
            all_kl.append(kl)
            all_prior_var.append(pvar)
            all_ids.append(str(row["isic_id"]))

        if not all_probs:
            continue

        probs_arr   = np.array(all_probs)
        targets_arr = np.array(all_targets)
        qbar_arr    = np.array(all_qbar)

        m = summary_metrics(probs_arr[:, 1], targets_arr, qbar_arr)
        row_out = {"baseline": key, "baseline_name": cfg["name"], "subset": subset,
                   "n": len(targets_arr),
                   **{k: v for k, v in m.items() if k != "qbar_ece_segments"}}
        print(f"  {subset}: AUC={m['auc']:.3f}  ECE={m['ece']:.3f}  entropy={m['mean_entropy']:.3f}")
        rows.append(row_out)

        for i in range(len(targets_arr)):
            pred_rows.append({
                "baseline": key, "baseline_name": cfg["name"], "subset": subset,
                "image_name": all_ids[i],
                "prob_pos": float(probs_arr[i, 1]), "target": int(targets_arr[i]),
                "qbar": float(qbar_arr[i]),
                "kl_term": float(all_kl[i]), "prior_var": float(all_prior_var[i]),
            })
    return rows


def run_mcdropout_baseline(cfg: dict, itb: pd.DataFrame, pred_rows: list) -> list[dict]:
    """MC Dropout: encoder mean (no reparameterization) + dropout active in classifier."""
    print(f"\n[I] {cfg['name']}")
    encoder, classifier = load_qvib_model(cfg["ckpt"], dropout=cfg.get("dropout", 0.3))
    encoder.tokenizer.forward = lambda q: torch.zeros(q.shape[0], device=q.device)

    # Enable dropout at inference for the classifier only
    def enable_dropout(m):
        if isinstance(m, nn.Dropout):
            m.train()
    classifier.apply(enable_dropout)

    N_MCD = 30
    rows = []
    for subset in sorted(itb["subset"].unique()):
        sub = itb[itb["subset"] == subset]
        all_probs, all_targets, all_qbar = [], [], []
        all_ids = []

        for _, row in tqdm(sub.iterrows(), total=len(sub), desc=subset, leave=False):
            img = cv2.imread(str(row["image_path"]))
            if img is None:
                continue
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

            feats  = extract_features(img)
            abcd_t = torch.tensor(feats.abcd,       dtype=torch.float32).unsqueeze(0).to(DEVICE)
            q_t    = torch.tensor(feats.q_vector,   dtype=torch.float32).unsqueeze(0).to(DEVICE)
            ef_t   = torch.tensor(feats.efnet_feat, dtype=torch.float32).unsqueeze(0).to(DEVICE)

            sample_seed = _seed_from_path(row["image_path"])
            torch.manual_seed(sample_seed)
            if torch.cuda.is_available():
                torch.cuda.manual_seed_all(sample_seed)

            with torch.no_grad():
                # Deterministic encoder mean (no sampling noise)
                mu, _ = encoder(abcd_t, q_t, efnet_feat=ef_t)
                # 30 passes through dropout-active classifier
                probs_mc = torch.stack([
                    F.softmax(classifier(mu), dim=-1) for _ in range(N_MCD)
                ]).mean(0)

            all_probs.append(probs_mc[0].cpu().numpy())
            all_targets.append(int(row["target"]))
            all_qbar.append(float(row["qbar"]))
            all_ids.append(str(row["isic_id"]))

        if not all_probs:
            continue

        probs_arr   = np.array(all_probs)
        targets_arr = np.array(all_targets)
        qbar_arr    = np.array(all_qbar)
        m = summary_metrics(probs_arr[:, 1], targets_arr, qbar_arr)
        row_out = {"baseline": "I", "baseline_name": cfg["name"], "subset": subset,
                   "n": len(targets_arr),
                   **{k: v for k, v in m.items() if k != "qbar_ece_segments"}}
        print(f"  {subset}: AUC={m['auc']:.3f}  ECE={m['ece']:.3f}  entropy={m['mean_entropy']:.3f}")
        rows.append(row_out)

        for i in range(len(targets_arr)):
            pred_rows.append({
                "baseline": "I", "baseline_name": cfg["name"], "subset": subset,
                "image_name": all_ids[i],
                "prob_pos": float(probs_arr[i, 1]), "target": int(targets_arr[i]),
                "qbar": float(qbar_arr[i]), "kl_term": 0.0, "prior_var": 0.0,
            })
    return rows


def run_ensemble_baseline(cfg: dict, itb: pd.DataFrame, pred_rows: list) -> list[dict]:
    """Deep Ensemble: average predictions from 5 independently trained Std VIB models."""
    print(f"\n[J] {cfg['name']} ({len(cfg['ckpts'])} models)")
    models = []
    for ckpt_path in cfg["ckpts"]:
        if not Path(ckpt_path).exists():
            print(f"  WARNING: missing {ckpt_path}, skipping")
            continue
        enc, cls = load_qvib_model(ckpt_path)
        enc.tokenizer.forward = lambda q: torch.zeros(q.shape[0], device=q.device)
        models.append((enc, cls))
    print(f"  Loaded {len(models)} ensemble members")

    rows = []
    for subset in sorted(itb["subset"].unique()):
        sub = itb[itb["subset"] == subset]
        all_probs, all_targets, all_qbar = [], [], []
        all_ids = []

        for _, row in tqdm(sub.iterrows(), total=len(sub), desc=subset, leave=False):
            img = cv2.imread(str(row["image_path"]))
            if img is None:
                continue
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

            feats  = extract_features(img)
            abcd_t = torch.tensor(feats.abcd,       dtype=torch.float32).unsqueeze(0).to(DEVICE)
            q_t    = torch.tensor(feats.q_vector,   dtype=torch.float32).unsqueeze(0).to(DEVICE)
            ef_t   = torch.tensor(feats.efnet_feat, dtype=torch.float32).unsqueeze(0).to(DEVICE)

            with torch.no_grad():
                member_probs = []
                for enc, cls in models:
                    mu, _ = enc(abcd_t, q_t, efnet_feat=ef_t)
                    member_probs.append(F.softmax(cls(mu), dim=-1))
                avg_probs = torch.stack(member_probs).mean(0)

            all_probs.append(avg_probs[0].cpu().numpy())
            all_targets.append(int(row["target"]))
            all_qbar.append(float(row["qbar"]))
            all_ids.append(str(row["isic_id"]))

        if not all_probs:
            continue

        probs_arr   = np.array(all_probs)
        targets_arr = np.array(all_targets)
        qbar_arr    = np.array(all_qbar)
        m = summary_metrics(probs_arr[:, 1], targets_arr, qbar_arr)
        row_out = {"baseline": "J", "baseline_name": cfg["name"], "subset": subset,
                   "n": len(targets_arr),
                   **{k: v for k, v in m.items() if k != "qbar_ece_segments"}}
        print(f"  {subset}: AUC={m['auc']:.3f}  ECE={m['ece']:.3f}  entropy={m['mean_entropy']:.3f}")
        rows.append(row_out)

        for i in range(len(targets_arr)):
            pred_rows.append({
                "baseline": "J", "baseline_name": cfg["name"], "subset": subset,
                "image_name": all_ids[i],
                "prob_pos": float(probs_arr[i, 1]), "target": int(targets_arr[i]),
                "qbar": float(qbar_arr[i]), "kl_term": 0.0, "prior_var": 0.0,
            })
    return rows


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", default="all", help="A/D/E/F or 'all'")
    parser.add_argument("--seed", type=int, default=None, help="Seed variant (123 or 2024); None = seed 42 default")
    args = parser.parse_args()

    # Override checkpoint paths for seed variants
    if args.seed is not None:
        suffix = f"_s{args.seed}"
        for bl, base_dir in SEED_CKPT_DIRS.items():
            BASELINES[bl]["ckpt"] = f"{base_dir}{suffix}/best_qad.pth"
        global OUT_CSV, PRED_CSV
        OUT_CSV  = f"results/itb_results_s{args.seed}.csv"
        PRED_CSV = f"results/itb_predictions_s{args.seed}.csv"

        # ── Sanity: F and G ckpts must be distinct files ──────────────────────
        # Bug history: run_s22_seeds.py/run_s22_missing.py mistakenly called
        # train_qad.py for G instead of finetune_tokenizer.py, producing G ckpts
        # byte-for-byte identical to F (MD5 collision, confirmed s123 & s2024).
        # Downstream effect: itb_predictions_s{seed}.csv had F==G predictions,
        # causing silent AUC duplication in 3seed_agg.
        import hashlib
        def _md5(p):
            try:
                with open(p, "rb") as _f:
                    return hashlib.md5(_f.read()).hexdigest()
            except FileNotFoundError:
                return None

        f_ckpt = BASELINES["F"]["ckpt"]
        g_ckpt = BASELINES["G"]["ckpt"]
        hf, hg = _md5(f_ckpt), _md5(g_ckpt)
        if hf is not None and hg is not None and hf == hg:
            raise RuntimeError(
                f"[ABORT] F and G checkpoints are byte-identical (MD5={hf[:12]})!\n"
                f"  F: {f_ckpt}\n"
                f"  G: {g_ckpt}\n"
                "This means G was incorrectly trained with train_qad.py instead of\n"
                "finetune_tokenizer.py. Fix: run run_g_tokft_seeds.py to regenerate\n"
                "G seed checkpoints from the corresponding F seed ckpt."
            )
        elif hf is not None and hg is not None:
            print(f"  [ckpt-check] F MD5={hf[:12]}  G MD5={hg[:12]}  OK (distinct)")

    itb = pd.read_csv(ITB_CSV)
    print(f"ITB loaded: {len(itb)} samples, {itb['subset'].nunique()} subsets")
    if args.seed:
        print(f"Seed variant: {args.seed}")

    keys = list(BASELINES.keys()) if args.baseline == "all" else [args.baseline.upper()]

    all_rows, pred_rows = [], []
    for k in keys:
        if k not in BASELINES:
            print(f"Unknown baseline: {k}"); continue
        cfg = BASELINES[k]
        if cfg.get("type") == "b3":
            all_rows.extend(run_b3_baseline(itb, pred_rows))
        elif cfg.get("type") == "ts":
            all_rows.extend(run_ts_baseline(itb, pred_rows))
        elif cfg.get("type") == "focal":
            all_rows.extend(run_focal_baseline(itb, pred_rows))
        elif cfg.get("type") == "mcdropout":
            all_rows.extend(run_mcdropout_baseline(cfg, itb, pred_rows))
        elif cfg.get("type") == "ensemble":
            all_rows.extend(run_ensemble_baseline(cfg, itb, pred_rows))
        else:
            all_rows.extend(run_qvib_baseline(k, cfg, itb, pred_rows))

    # Save summary
    out = pd.DataFrame(all_rows)
    out_path = Path(OUT_CSV)
    if out_path.exists():
        existing = pd.read_csv(out_path)
        existing = existing[~existing["baseline"].isin(keys)]
        out = pd.concat([existing, out], ignore_index=True)
    out.to_csv(out_path, index=False)
    print(f"\nResults -> {OUT_CSV}")

    # Save per-sample predictions
    pred_out = pd.DataFrame(pred_rows)
    pred_path = Path(PRED_CSV)
    if pred_path.exists():
        ep = pd.read_csv(pred_path)
        ep = ep[~ep["baseline"].isin(keys)]
        pred_out = pd.concat([ep, pred_out], ignore_index=True)
    pred_out.to_csv(pred_path, index=False)
    print(f"Predictions -> {PRED_CSV}")
    print(out[["baseline","baseline_name","subset","auc","ece","mean_entropy"]].to_string(index=False))


if __name__ == "__main__":
    main()
