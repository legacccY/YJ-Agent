"""ITB 全量实验脚本：Baseline A (EfficientNet-B3) + D/E/F Q-VIB 消融。

Baselines:
  A  EfficientNet-B3 (Direct)   checkpoints/efficientnet_b3_isic.pth  (外部 baseline，无质量感知)
  D  Std VIB                    checkpoints/stdvib/best_qad.pth
  E  Adaptive Prior             checkpoints/adaptive/best_qad.pth
  F  Q-VIB Full (Ours)          checkpoints/efnet/best_qad.pth

每个样本额外输出：kl_term, prior_var (供 Lemma 1 / Fig 5 使用)

Usage:
  cd D:/YJ-Agent/project
  python run_experiments.py               # 跑全部
  python run_experiments.py --baseline D  # 只跑 Std VIB
"""
import argparse, sys
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

ITB_CSV  = "results/itb_subsets.csv"
OUT_CSV  = "results/itb_results.csv"
PRED_CSV = "results/itb_predictions.csv"
N_MC     = 20
DEVICE   = torch.device("cuda" if torch.cuda.is_available() else "cpu")

BASELINES = {
    "A": {"name": "EfficientNet-B3 (Direct)", "type": "b3"},
    "D": {"name": "Std VIB",        "ckpt": "D:/YJ-Agent/checkpoints/stdvib/best_qad.pth",   "use_tok": False, "use_prior": False},
    "E": {"name": "Adaptive Prior", "ckpt": "D:/YJ-Agent/checkpoints/adaptive/best_qad.pth", "use_tok": False, "use_prior": True},
    "F": {"name": "Q-VIB Full",     "ckpt": "D:/YJ-Agent/checkpoints/efnet/best_qad.pth",    "use_tok": True,  "use_prior": True},
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

def load_qvib_model(ckpt_path: str):
    ckpt = torch.load(ckpt_path, map_location=DEVICE)
    encoder = QVIBEncoder(
        abcd_dim=4, q_dim=5, d_model=128, n_heads=4, latent_dim=64, efnet_dim=1280
    ).to(DEVICE).eval()
    classifier = QADClassifier(latent_dim=64, hidden_dim=128, num_classes=2).to(DEVICE).eval()
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

def mc_predict(encoder, classifier, abcd_t, q_t, ef_t, n_mc):
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


# ── Per-baseline runners ───────────────────────────────────────────────────────

def run_b3_baseline(itb: pd.DataFrame, pred_rows: list) -> list[dict]:
    print("\n[A] EfficientNet-B3 (Direct)")
    b3 = load_b3_model()
    rows = []
    for subset in sorted(itb["subset"].unique()):
        sub = itb[itb["subset"] == subset]
        all_probs, all_targets, all_qbar = [], [], []
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
                "prob_pos": float(probs_arr[i, 1]), "target": int(targets_arr[i]),
                "qbar": float(qbar_arr[i]), "kl_term": 0.0, "prior_var": 0.0,
            })
    return rows


def run_qvib_baseline(key: str, cfg: dict, itb: pd.DataFrame, pred_rows: list) -> list[dict]:
    print(f"\n[{key}] {cfg['name']}")
    encoder, classifier = load_qvib_model(cfg["ckpt"])
    if not cfg["use_tok"]:
        encoder.tokenizer.forward = lambda q: torch.zeros(q.shape[0], device=q.device)

    rows = []
    for subset in sorted(itb["subset"].unique()):
        sub = itb[itb["subset"] == subset]
        all_probs, all_targets, all_qbar = [], [], []
        all_kl, all_prior_var = [], []

        for _, row in tqdm(sub.iterrows(), total=len(sub), desc=subset, leave=False):
            img = cv2.imread(str(row["image_path"]))
            if img is None:
                continue
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

            feats  = extract_features(img)
            abcd_t = torch.tensor(feats.abcd, dtype=torch.float32).unsqueeze(0).to(DEVICE)
            q_t    = torch.tensor(feats.q_vector, dtype=torch.float32).unsqueeze(0).to(DEVICE)
            ef_t   = torch.tensor(feats.efnet_feat, dtype=torch.float32).unsqueeze(0).to(DEVICE)

            probs, mu, lsq = mc_predict(encoder, classifier, abcd_t, q_t, ef_t, N_MC)
            kl, pvar = compute_kl(mu, lsq, q_t, cfg["use_prior"])

            all_probs.append(probs[0].cpu().numpy())
            all_targets.append(int(row["target"]))
            all_qbar.append(float(row["qbar"]))
            all_kl.append(kl)
            all_prior_var.append(pvar)

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
                "prob_pos": float(probs_arr[i, 1]), "target": int(targets_arr[i]),
                "qbar": float(qbar_arr[i]),
                "kl_term": float(all_kl[i]), "prior_var": float(all_prior_var[i]),
            })
    return rows


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", default="all", help="A/D/E/F or 'all'")
    args = parser.parse_args()

    itb = pd.read_csv(ITB_CSV)
    print(f"ITB loaded: {len(itb)} samples, {itb['subset'].nunique()} subsets")

    keys = list(BASELINES.keys()) if args.baseline == "all" else [args.baseline.upper()]

    all_rows, pred_rows = [], []
    for k in keys:
        if k not in BASELINES:
            print(f"Unknown baseline: {k}"); continue
        cfg = BASELINES[k]
        if cfg.get("type") == "b3":
            all_rows.extend(run_b3_baseline(itb, pred_rows))
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
