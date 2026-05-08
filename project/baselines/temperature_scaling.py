"""Temperature Scaling for Std VIB (Baseline D).

Fits a single scalar T on val split to minimize NLL. Standard Guo et al. (2017)
post-hoc calibration. Output: checkpoints/stdvib/temperature.json with {"T": float}.

Usage:
    cd D:/YJ-Agent/project
    python -m baselines.temperature_scaling
"""
import json
import sys
from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import DataLoader

sys.path.insert(0, str(Path(__file__).parent.parent))

from data.qad_dataset import QADDataset, qad_collate_fn
from models.q_vib_encoder import QVIBEncoder
from models.qad_classifier import QADClassifier

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

CKPT_PATH = "D:/YJ-Agent/checkpoints/stdvib/best_qad.pth"
OUT_PATH  = "D:/YJ-Agent/checkpoints/stdvib/temperature.json"


def collect_val_logits():
    ds = QADDataset(
        quality_csv="D:/YJ-Agent/data/quality_labels_all.csv",
        metadata_csv="D:/YJ-Agent/data/raw/isic2020/train-metadata.csv",
        abcd_cache_csv="D:/YJ-Agent/data/abcd_cache.csv",
        efnet_features_npy="D:/YJ-Agent/data/efficientnet_features.npy",
        efnet_index_csv="D:/YJ-Agent/data/efficientnet_index.csv",
        split_csv="D:/YJ-Agent/data/isic_split.csv",
        split="val",
        source_filter=["isic2020"],
    )
    n_pos = int((ds.df["target"] == 1).sum())
    print(f"Val: {len(ds)} samples, {n_pos} positives ({n_pos/len(ds)*100:.2f}%)")

    dl = DataLoader(ds, batch_size=256, shuffle=False, num_workers=0,
                    collate_fn=qad_collate_fn)

    ckpt = torch.load(CKPT_PATH, map_location=DEVICE)
    encoder = QVIBEncoder(abcd_dim=4, q_dim=5, d_model=128, n_heads=4,
                           latent_dim=64, efnet_dim=1280).to(DEVICE).eval()
    classifier = QADClassifier(latent_dim=64, hidden_dim=128, num_classes=2).to(DEVICE).eval()
    encoder.load_state_dict(ckpt["encoder"])
    classifier.load_state_dict(ckpt["classifier"])
    # Std VIB: tokenizer disabled (use_tok=False at training)
    encoder.tokenizer.forward = lambda q: torch.zeros(q.shape[0], device=q.device)

    all_logits, all_targets = [], []
    with torch.no_grad():
        for batch in dl:
            abcd = batch["abcd"].to(DEVICE)
            q    = batch["q"].to(DEVICE)
            ef   = batch.get("efnet_feat")
            ef   = ef.to(DEVICE) if ef is not None else None
            mu, _ = encoder(abcd, q, efnet_feat=ef)
            logits = classifier(mu)
            all_logits.append(logits.cpu())
            all_targets.append(batch["target"])
    return torch.cat(all_logits), torch.cat(all_targets)


def fit_temperature(logits: torch.Tensor, targets: torch.Tensor) -> tuple[float, float, float]:
    T = nn.Parameter(torch.ones(1) * 1.5)
    optim = torch.optim.LBFGS([T], lr=0.05, max_iter=200)
    crit = nn.CrossEntropyLoss()

    def closure():
        optim.zero_grad()
        loss = crit(logits / T.clamp_min(1e-3), targets)
        loss.backward()
        return loss

    nll_before = float(crit(logits, targets).item())
    optim.step(closure)
    nll_after = float(crit(logits / T.clamp_min(1e-3), targets).item())
    return float(T.item()), nll_before, nll_after


def main():
    print("Collecting val logits from Std VIB...")
    logits, targets = collect_val_logits()
    print(f"  shape: {tuple(logits.shape)}")

    print("Fitting temperature via LBFGS...")
    T, nll_before, nll_after = fit_temperature(logits, targets)
    print(f"  T = {T:.4f}")
    print(f"  NLL before = {nll_before:.4f}")
    print(f"  NLL after  = {nll_after:.4f}  (Δ={nll_before - nll_after:+.4f})")

    Path(OUT_PATH).parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump({"T": T, "nll_before": nll_before, "nll_after": nll_after}, f, indent=2)
    print(f"Saved {OUT_PATH}")


if __name__ == "__main__":
    main()
