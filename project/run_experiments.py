"""ITB 全量实验脚本：对所有 baseline 跑 4 个子集评测。

Baselines:
  D  Std VIB          checkpoints/stdvib/best_qad.pth
  E  Adaptive Prior   checkpoints/adaptive/best_qad.pth
  F  Q-VIB Full       checkpoints/efnet/best_qad.pth   (Ours)

Usage:
  cd D:/YJ-Agent/project
  python run_experiments.py               # 跑全部
  python run_experiments.py --baseline D  # 只跑 Std VIB
"""
import argparse, json, sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from omegaconf import OmegaConf
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent))
from models.q_vib_encoder import QVIBEncoder
from models.qad_classifier import QADClassifier
from models.quality_adaptive_prior import QualityAdaptivePrior
from agent.tools import quality_assess, extract_features
from benchmark.metrics import summary_metrics

import cv2

ITB_CSV  = "results/itb_subsets.csv"
OUT_CSV   = "results/itb_results.csv"
PRED_CSV  = "results/itb_predictions.csv"
N_MC      = 20
DEVICE   = torch.device("cuda" if torch.cuda.is_available() else "cpu")

BASELINES = {
    "D": {"name": "Std VIB",         "ckpt": "D:/YJ-Agent/checkpoints/stdvib/best_qad.pth",    "use_tok": False, "use_prior": False},
    "E": {"name": "Adaptive Prior",  "ckpt": "D:/YJ-Agent/checkpoints/adaptive/best_qad.pth",  "use_tok": False, "use_prior": True},
    "F": {"name": "Q-VIB Full",      "ckpt": "D:/YJ-Agent/checkpoints/efnet/best_qad.pth",     "use_tok": True,  "use_prior": True},
}

EFNET_DIM = 1280  # Q-VIB Full 用 EfficientNet 特征


def load_model(ckpt_path: str):
    ckpt = torch.load(ckpt_path, map_location=DEVICE)
    encoder = QVIBEncoder(abcd_dim=4, q_dim=5, d_model=128, n_heads=4, latent_dim=64, efnet_dim=EFNET_DIM).to(DEVICE).eval()
    classifier = QADClassifier(latent_dim=64, hidden_dim=128, num_classes=2).to(DEVICE).eval()
    encoder.load_state_dict(ckpt["encoder"])
    classifier.load_state_dict(ckpt["classifier"])
    return encoder, classifier


def mc_predict(encoder, classifier, abcd_t, q_t, ef_t, n_mc):
    probs_list = []
    with torch.no_grad():
        mu, lsq = encoder(abcd_t, q_t, efnet_feat=ef_t)
        for _ in range(n_mc):
            z = encoder.reparameterize(mu, lsq)
            probs_list.append(F.softmax(classifier(z), -1))
    return torch.stack(probs_list).mean(0)  # (B, 2)


def run_baseline(key: str, cfg: dict, itb: pd.DataFrame, pred_rows: list) -> tuple[list[dict], list]:
    print(f"\n[{key}] {cfg['name']}")
    encoder, classifier = load_model(cfg["ckpt"])

    # 禁用 tokenizer / prior（消融）
    if not cfg["use_tok"]:
        encoder.tokenizer.forward = lambda q: torch.zeros(q.shape[0], device=q.device)

    rows = []
    for subset in sorted(itb["subset"].unique()):
        sub = itb[itb["subset"] == subset]
        all_probs, all_targets, all_qbar = [], [], []

        for _, row in tqdm(sub.iterrows(), total=len(sub), desc=subset, leave=False):
            img = cv2.imread(str(row["image_path"]))
            if img is None:
                continue
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

            feats = extract_features(img)
            abcd_t = torch.tensor(feats.abcd, dtype=torch.float32).unsqueeze(0).to(DEVICE)
            q_t    = torch.tensor(feats.q_vector, dtype=torch.float32).unsqueeze(0).to(DEVICE)
            ef_t   = torch.tensor(feats.efnet_feat, dtype=torch.float32).unsqueeze(0).to(DEVICE)

            probs = mc_predict(encoder, classifier, abcd_t, q_t, ef_t, N_MC)
            all_probs.append(probs[0].cpu().numpy())
            all_targets.append(int(row["target"]))
            # 用 itb_subsets.csv 的预计算 qbar，保证与子集定义一致
            all_qbar.append(float(row["qbar"]))

        if not all_probs:
            continue

        probs_arr   = np.array(all_probs)
        targets_arr = np.array(all_targets)
        qbar_arr    = np.array(all_qbar)

        m = summary_metrics(probs_arr, targets_arr, qbar_arr)
        row_out = {"baseline": key, "baseline_name": cfg["name"], "subset": subset,
                   "n": len(targets_arr), **{k: v for k, v in m.items() if k != "qbar_ece_segments"}}
        print(f"  {subset}: AUC={m['auc']:.3f}  ECE={m['ece']:.3f}  F1={m['f1']:.3f}")
        rows.append(row_out)

        # per-sample predictions for calibration curves
        for i in range(len(targets_arr)):
            pred_rows.append({
                "baseline": key, "baseline_name": cfg["name"], "subset": subset,
                "prob_pos": float(probs_arr[i, 1]), "target": int(targets_arr[i]), "qbar": float(qbar_arr[i]),
            })

    return rows, pred_rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", default="all", help="D/E/F or 'all'")
    args = parser.parse_args()

    itb = pd.read_csv(ITB_CSV)
    print(f"ITB loaded: {len(itb)} samples across {itb['subset'].nunique()} subsets")

    keys = list(BASELINES.keys()) if args.baseline == "all" else [args.baseline.upper()]

    all_rows = []
    pred_rows = []
    for k in keys:
        if k not in BASELINES:
            print(f"Unknown baseline: {k}")
            continue
        rows, preds = run_baseline(k, BASELINES[k], itb, pred_rows)
        all_rows.extend(rows)

    out = pd.DataFrame(all_rows)
    out_path = Path(OUT_CSV)
    if out_path.exists():
        existing = pd.read_csv(out_path)
        existing = existing[~existing["baseline"].isin(keys)]
        out = pd.concat([existing, out], ignore_index=True)
    out.to_csv(out_path, index=False)
    print(f"\nResults saved to {OUT_CSV}")
    print(out.to_string())

    pred_out = pd.DataFrame(pred_rows)
    pred_path = Path(PRED_CSV)
    if pred_path.exists():
        ep = pd.read_csv(pred_path)
        ep = ep[~ep["baseline"].isin(keys)]
        pred_out = pd.concat([ep, pred_out], ignore_index=True)
    pred_out.to_csv(pred_path, index=False)
    print(f"Per-sample predictions saved to {PRED_CSV}")


if __name__ == "__main__":
    main()
