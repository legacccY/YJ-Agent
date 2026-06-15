"""Zero-shot 推理：用 ITB 训练好的权重在外部数据集上直接 forward。

数据集：ham10000 / pad_ufes
特征：从预计算的 abcd.npy / q.npy / efnet.npy 读取（不重新提特征）。
Baseline A (B3)：需要读原图（raw forward，无法用缓存特征）。

输出：results/external_{dataset}_predictions.csv
  列：baseline, image_id, prob_pos, target, q_bar

Usage:
  cd D:/YJ-Agent/project
  python run_external.py --dataset ham10000
  python run_external.py --dataset pad_ufes
  python run_external.py --dataset ham10000 --baseline F   # 单个 baseline
"""

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image
from torchvision import transforms
from torchvision.models import efficientnet_b3
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent))

from models.q_vib_encoder import QVIBEncoder
from models.qad_classifier import QADClassifier
from models.quality_adaptive_prior import QualityAdaptivePrior
from baselines.focal_loss_baseline import FocalMLP
from benchmark.metrics import summary_metrics

PROJECT_DIR = Path(__file__).parent
DATA_EXT    = PROJECT_DIR.parent / "data" / "external"
RESULTS_DIR = PROJECT_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)

N_MC    = 20
DEVICE  = torch.device("cuda" if torch.cuda.is_available() else "cpu")
PRIOR   = QualityAdaptivePrior(sigma0_sq=0.1, tau=0.5, alpha=5.0).to(DEVICE)

BASELINES = {
    "A":  {"name": "EfficientNet-B3 (Direct)", "type": "b3"},
    "D":  {"name": "Std VIB",        "ckpt": "D:/YJ-Agent/checkpoints/stdvib/best_qad.pth",      "use_tok": False, "use_prior": False},
    "E":  {"name": "Adaptive Prior", "ckpt": "D:/YJ-Agent/checkpoints/adaptive/best_qad.pth",    "use_tok": False, "use_prior": True},
    "F":  {"name": "Q-VIB Full",     "ckpt": "D:/YJ-Agent/checkpoints/efnet/best_qad.pth",       "use_tok": True,  "use_prior": True},
    "G":  {"name": "Q-VIB+TokFT",    "ckpt": "D:/YJ-Agent/checkpoints/efnet_tokft/best_qad.pth", "use_tok": True,  "use_prior": True},
    "TS": {"name": "Std VIB + TS",   "ckpt": "D:/YJ-Agent/checkpoints/stdvib/best_qad.pth",
           "temp_path": "D:/YJ-Agent/checkpoints/stdvib/temperature.json",
           "type": "ts", "use_tok": False, "use_prior": False},
    "H":  {"name": "Focal+LS",       "ckpt": "D:/YJ-Agent/checkpoints/focal/best.pth",  "type": "focal"},
}

B3_TFM = transforms.Compose([
    transforms.Resize(256),
    transforms.CenterCrop(224),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
])


# ── Util ──────────────────────────────────────────────────────────────────────

def _seed_from_path(image_path: str) -> int:
    import hashlib
    return int(hashlib.md5(str(image_path).encode("utf-8")).hexdigest()[:8], 16)


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


def mc_predict(encoder, classifier, abcd_t, q_t, ef_t, n_mc, seed=None):
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
    return torch.stack(probs_list).mean(0), mu, lsq


def deterministic_predict(encoder, classifier, abcd_t, q_t, ef_t, T: float):
    with torch.no_grad():
        mu, lsq = encoder(abcd_t, q_t, efnet_feat=ef_t)
        logits = classifier(mu)
        probs = F.softmax(logits / T, dim=-1)
    return probs, mu, lsq


def compute_kl(mu, lsq, q_t, use_adaptive_prior: bool):
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

def run_b3(index: pd.DataFrame, dataset: str) -> list[dict]:
    """Baseline A: reads raw image, no precomputed features needed."""
    print(f"\n[A] EfficientNet-B3 (Direct) on {dataset}")
    b3 = load_b3_model()
    rows = []
    for _, row in tqdm(index.iterrows(), total=len(index), desc="A"):
        img_bgr = cv2.imread(str(row["image_path"]))
        if img_bgr is None:
            continue
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        pil = Image.fromarray(img_rgb)
        t = B3_TFM(pil).unsqueeze(0).to(DEVICE)
        with torch.no_grad():
            prob = F.softmax(b3(t), -1)[0, 1].item()
        rows.append({
            "baseline": "A", "baseline_name": "EfficientNet-B3 (Direct)",
            "image_id": row["image_id"], "image_path": row["image_path"],
            "prob_pos": prob, "target": int(row["target"]), "q_bar": float(row["q_bar"]),
            "kl_term": 0.0, "prior_var": 0.0,
        })
    return rows


def run_ts(index: pd.DataFrame, abcd: np.ndarray, q: np.ndarray, efnet: np.ndarray, dataset: str) -> list[dict]:
    """Baseline TS: Std VIB + Temperature Scaling."""
    cfg = BASELINES["TS"]
    print(f"\n[TS] {cfg['name']} on {dataset}")
    with open(cfg["temp_path"]) as f:
        T = float(json.load(f)["T"])
    print(f"  T = {T:.4f}")
    encoder, classifier = load_qvib_model(cfg["ckpt"])
    encoder.tokenizer.forward = lambda q: torch.zeros(q.shape[0], device=q.device)

    rows = []
    for i, row in tqdm(index.iterrows(), total=len(index), desc="TS"):
        ii = index.index.get_loc(i)
        abcd_t = torch.tensor(abcd[ii], dtype=torch.float32).unsqueeze(0).to(DEVICE)
        q_t    = torch.tensor(q[ii],    dtype=torch.float32).unsqueeze(0).to(DEVICE)
        ef_t   = torch.tensor(efnet[ii],dtype=torch.float32).unsqueeze(0).to(DEVICE)
        probs, _, _ = deterministic_predict(encoder, classifier, abcd_t, q_t, ef_t, T)
        rows.append({
            "baseline": "TS", "baseline_name": cfg["name"],
            "image_id": row["image_id"], "image_path": row["image_path"],
            "prob_pos": float(probs[0, 1].item()), "target": int(row["target"]),
            "q_bar": float(row["q_bar"]), "kl_term": 0.0, "prior_var": 0.0,
        })
    return rows


def run_focal(index: pd.DataFrame, abcd: np.ndarray, efnet: np.ndarray, dataset: str) -> list[dict]:
    """Baseline H: Focal+LS MLP, input = efnet(1280) + abcd(4)."""
    cfg = BASELINES["H"]
    print(f"\n[H] {cfg['name']} on {dataset}")
    ckpt = torch.load(cfg["ckpt"], map_location=DEVICE)
    model = FocalMLP().to(DEVICE).eval()
    model.load_state_dict(ckpt["model"])

    rows = []
    for i, row in tqdm(index.iterrows(), total=len(index), desc="H"):
        ii = index.index.get_loc(i)
        ef_t = torch.tensor(efnet[ii], dtype=torch.float32).to(DEVICE)
        ab_t = torch.tensor(abcd[ii],  dtype=torch.float32).to(DEVICE)
        x = torch.cat([ef_t, ab_t]).unsqueeze(0)
        with torch.no_grad():
            prob = F.softmax(model(x), -1)[0, 1].item()
        rows.append({
            "baseline": "H", "baseline_name": cfg["name"],
            "image_id": row["image_id"], "image_path": row["image_path"],
            "prob_pos": prob, "target": int(row["target"]),
            "q_bar": float(row["q_bar"]), "kl_term": 0.0, "prior_var": 0.0,
        })
    return rows


def run_qvib(key: str, index: pd.DataFrame, abcd: np.ndarray, q: np.ndarray,
             efnet: np.ndarray, dataset: str) -> list[dict]:
    cfg = BASELINES[key]
    print(f"\n[{key}] {cfg['name']} on {dataset}")
    encoder, classifier = load_qvib_model(cfg["ckpt"])
    if not cfg["use_tok"]:
        encoder.tokenizer.forward = lambda q: torch.zeros(q.shape[0], device=q.device)

    rows = []
    for i, row in tqdm(index.iterrows(), total=len(index), desc=key):
        ii = index.index.get_loc(i)
        abcd_t = torch.tensor(abcd[ii], dtype=torch.float32).unsqueeze(0).to(DEVICE)
        q_t    = torch.tensor(q[ii],    dtype=torch.float32).unsqueeze(0).to(DEVICE)
        ef_t   = torch.tensor(efnet[ii],dtype=torch.float32).unsqueeze(0).to(DEVICE)

        seed = _seed_from_path(row["image_path"])
        probs, mu, lsq = mc_predict(encoder, classifier, abcd_t, q_t, ef_t, N_MC, seed=seed)
        kl, pvar = compute_kl(mu, lsq, q_t, cfg["use_prior"])

        rows.append({
            "baseline": key, "baseline_name": cfg["name"],
            "image_id": row["image_id"], "image_path": row["image_path"],
            "prob_pos": float(probs[0, 1].item()), "target": int(row["target"]),
            "q_bar": float(row["q_bar"]), "kl_term": kl, "prior_var": pvar,
        })
    return rows


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True,
                        choices=["ham10000", "pad_ufes", "fitz17k", "dermnet"])
    parser.add_argument("--baseline", default="all")
    args = parser.parse_args()

    dataset = args.dataset
    # fitz17k features live in data/raw (precompute wrote them there), not data/external
    ROOT_OVERRIDE = {"fitz17k": PROJECT_DIR.parent / "data" / "raw" / "fitzpatrick17k"}
    root    = ROOT_OVERRIDE.get(dataset, DATA_EXT / dataset)

    # Load precomputed features
    idx_path   = root / "index.csv"
    abcd_path  = root / "abcd.npy"
    q_path     = root / "q.npy"
    efnet_path = root / "efnet.npy"

    if not idx_path.exists():
        print(f"ERROR: {idx_path} not found. Run precompute_external_features.py first.")
        sys.exit(1)

    index = pd.read_csv(idx_path).reset_index(drop=True)
    abcd  = np.load(abcd_path)
    q     = np.load(q_path)
    efnet = np.load(efnet_path)

    print(f"\n=== External zero-shot: {dataset} ===")
    print(f"  Samples : {len(index)}")
    print(f"  Positives: {int(index['target'].sum())} ({100*index['target'].mean():.1f}%)")
    print(f"  Features: abcd{abcd.shape}  q{q.shape}  efnet{efnet.shape}")
    print(f"  Device  : {DEVICE}")

    # Determine baselines to run
    keys = list(BASELINES.keys()) if args.baseline.upper() == "ALL" else [args.baseline.upper()]

    all_rows = []
    for k in keys:
        if k not in BASELINES:
            print(f"Unknown baseline: {k}"); continue
        cfg = BASELINES[k]
        btype = cfg.get("type", "qvib")
        if btype == "b3":
            all_rows.extend(run_b3(index, dataset))
        elif btype == "ts":
            all_rows.extend(run_ts(index, abcd, q, efnet, dataset))
        elif btype == "focal":
            all_rows.extend(run_focal(index, abcd, efnet, dataset))
        else:
            all_rows.extend(run_qvib(k, index, abcd, q, efnet, dataset))

    # Save predictions
    out_csv = RESULTS_DIR / f"external_{dataset}_predictions.csv"
    pred_df = pd.DataFrame(all_rows)
    if out_csv.exists():
        existing = pd.read_csv(out_csv)
        ran_keys = set(existing["baseline"].unique())
        new_keys = set(pred_df["baseline"].unique())
        # Keep existing rows that we're NOT re-running
        existing = existing[~existing["baseline"].isin(new_keys)]
        pred_df = pd.concat([existing, pred_df], ignore_index=True)
    pred_df.to_csv(out_csv, index=False)
    print(f"\nPredictions -> {out_csv}")

    # Quick summary
    print("\n--- Summary ---")
    for bl in pred_df["baseline"].unique():
        sub = pred_df[pred_df["baseline"] == bl]
        probs  = sub["prob_pos"].values
        tgts   = sub["target"].values
        q_bar  = sub["q_bar"].values
        m = summary_metrics(probs, tgts, q_bar)
        print(f"  [{bl}] {BASELINES.get(bl,{}).get('name',bl):<30} "
              f"AUC={m['auc']:.3f}  ECE={m['ece']:.3f}  entropy={m['mean_entropy']:.3f}")


if __name__ == "__main__":
    main()
