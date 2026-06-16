"""Proper 3-model ablation evaluation for Q-VIB.

Loads three independently trained checkpoints:
  Baseline 1: Standard VIB         (configs/qad_stdvib.yaml)
  Baseline 2: Adaptive Prior only  (configs/qad_adaptive.yaml)
  Ours:       Q-VIB Full           (configs/qad_efnet.yaml)

Each model is evaluated on the held-out test split.
This avoids post-hoc ablation bias (using one model with components zeroed).

Usage:
    python eval_ablation.py
"""

import argparse
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from omegaconf import OmegaConf
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score, roc_curve
from torch.utils.data import DataLoader
from tqdm import tqdm

from data.qad_dataset import QADDataset, qad_collate_fn
from models.q_vib_encoder import QVIBEncoder
from models.qad_classifier import QADClassifier
from models.quality_adaptive_prior import QualityAdaptivePrior


VARIANTS = [
    {
        "name": "Baseline 1: Std VIB",
        "config": "configs/qad_stdvib.yaml",
        "ckpt":   "D:/YJ-Agent/checkpoints/stdvib/best_qad.pth",
    },
    {
        "name": "Baseline 2: Adaptive Prior only",
        "config": "configs/qad_adaptive.yaml",
        "ckpt":   "D:/YJ-Agent/checkpoints/adaptive/best_qad.pth",
    },
    {
        "name": "Ours: Q-VIB Full",
        "config": "configs/qad_efnet.yaml",
        "ckpt":   "D:/YJ-Agent/checkpoints/efnet/best_qad.pth",
    },
]


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="results/eval_report_ablation.md")
    p.add_argument("--n_mc", type=int, default=20)
    p.add_argument("--batch_size", type=int, default=512)
    p.add_argument(
        "--save-persample",
        default=None,
        metavar="PATH",
        help=(
            "If set, dump a per-sample CSV for the 'Ours: Q-VIB Full' variant only "
            "(cols: logit_pos, prob_pos, conf, correct, entropy_H, qbar).  "
            "Used to compute bootstrap CI for AUC/ECE/rho without altering any "
            "aggregated metric or model weights."
        ),
    )
    return p.parse_args()


def compute_ece(probs: np.ndarray, targets: np.ndarray, n_bins: int = 10) -> float:
    confidences = probs.max(axis=-1)
    predictions = probs.argmax(axis=-1)
    correct = (predictions == targets).astype(float)
    bin_edges = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    for lo, hi in zip(bin_edges[:-1], bin_edges[1:]):
        mask = (confidences > lo) & (confidences <= hi)
        if mask.sum() == 0:
            continue
        ece += mask.mean() * abs(correct[mask].mean() - confidences[mask].mean())
    return float(ece)


def best_threshold_metrics(probs: np.ndarray, targets: np.ndarray):
    if targets.sum() == 0 or targets.sum() == len(targets):
        return float("nan"), float("nan")
    fpr, tpr, _ = roc_curve(targets, probs[:, 1])
    idx = np.argmax(tpr - fpr)
    return float(tpr[idx]), float(1 - fpr[idx])


def eval_model(variant: dict, args, device: torch.device) -> dict:
    cfg = OmegaConf.load(variant["config"])

    test_ds = QADDataset(
        quality_csv=cfg.data.labels_csv,
        metadata_csv=cfg.data.metadata_csv,
        abcd_cache_csv=cfg.data.abcd_cache_csv,
        efnet_features_npy=cfg.data.get("efnet_features_npy", None),
        efnet_index_csv=cfg.data.get("efnet_index_csv", None),
        split_csv=cfg.data.get("split_csv", None),
        split="test" if cfg.data.get("split_csv", None) else None,
    )

    loader = DataLoader(
        test_ds, batch_size=args.batch_size, shuffle=False,
        num_workers=cfg.data.num_workers, collate_fn=qad_collate_fn,
        multiprocessing_context="spawn", persistent_workers=True, pin_memory=False,
    )

    prior = QualityAdaptivePrior(
        sigma0_sq=cfg.model.prior.sigma0_sq,
        tau=cfg.model.prior.tau,
        alpha=cfg.model.prior.alpha,
    ).to(device)

    encoder = QVIBEncoder(
        abcd_dim=4, q_dim=5,
        d_model=cfg.model.encoder.d_model,
        n_heads=cfg.model.encoder.n_heads,
        latent_dim=cfg.model.encoder.latent_dim,
        efnet_dim=cfg.model.encoder.get("efnet_dim", 0),
        use_tokenizer=cfg.model.encoder.get("use_tokenizer", True),
    ).to(device)

    classifier = QADClassifier(
        latent_dim=cfg.model.encoder.latent_dim,
        hidden_dim=cfg.model.classifier.hidden_dim,
        num_classes=cfg.model.classifier.num_classes,
    ).to(device)

    ckpt = torch.load(variant["ckpt"], map_location=device)
    encoder.load_state_dict(ckpt["encoder"])
    classifier.load_state_dict(ckpt["classifier"])
    encoder.eval()
    classifier.eval()

    all_probs, all_entropy, all_targets, all_qbar = [], [], [], []
    # also collect per-MC logits for per-sample dump (only if requested)
    all_logits_pos = []

    with torch.no_grad():
        for batch in tqdm(loader, desc=variant["name"], leave=False):
            abcd = batch["abcd"].to(device)
            q = batch["q"].to(device)
            targets = batch["target"]
            efnet_feat = batch["efnet_feat"].to(device) if "efnet_feat" in batch else None

            mu, log_sigma_sq = encoder(abcd, q, efnet_feat=efnet_feat)

            probs_list = []
            logits_list = []
            for _ in range(args.n_mc):
                z = encoder.reparameterize(mu, log_sigma_sq)
                lgts = classifier(z)
                logits_list.append(lgts)
                probs_list.append(F.softmax(lgts, dim=-1))

            mean_probs = torch.stack(probs_list).mean(0)
            entropy = -(mean_probs * mean_probs.log().clamp(-20)).sum(-1)
            # mean logit of positive class across MC samples (for per-sample dump)
            mean_logits = torch.stack(logits_list).mean(0)

            all_probs.append(mean_probs.cpu().numpy())
            all_entropy.append(entropy.cpu().numpy())
            all_targets.append(targets.numpy())
            all_qbar.append(q.mean(-1).cpu().numpy())
            all_logits_pos.append(mean_logits[:, 1].cpu().numpy())

    probs       = np.concatenate(all_probs)
    entropy     = np.concatenate(all_entropy)
    targets     = np.concatenate(all_targets)
    qbar        = np.concatenate(all_qbar)
    logits_pos  = np.concatenate(all_logits_pos)

    auc  = float(roc_auc_score(targets, probs[:, 1]))
    ece  = compute_ece(probs, targets)
    acc  = float((probs.argmax(-1) == targets).mean())
    sens, spec = best_threshold_metrics(probs, targets)
    rho, pval  = spearmanr(qbar, entropy)

    quintiles = np.percentile(qbar, [0, 20, 40, 60, 80, 100])
    segments = []
    for lo, hi in zip(quintiles[:-1], quintiles[1:]):
        mask = (qbar >= lo) & (qbar <= hi)
        if mask.sum() < 10:
            continue
        seg_auc = (
            float(roc_auc_score(targets[mask], probs[mask, 1]))
            if 0 < targets[mask].sum() < mask.sum() else float("nan")
        )
        segments.append({
            "q_bar_lo": float(lo), "q_bar_hi": float(hi),
            "q_bar_mean": float(qbar[mask].mean()),
            "auc": seg_auc,
            "ece": compute_ece(probs[mask], targets[mask]),
            "entropy": float(entropy[mask].mean()),
            "n": int(mask.sum()),
        })

    result = {
        "name": variant["name"],
        "auc": auc, "ece": ece, "acc": acc,
        "sensitivity": sens, "specificity": spec,
        "mean_entropy": float(entropy.mean()),
        "entropy_rho": float(rho), "entropy_pval": float(pval),
        "segments": segments,
        # carry arrays for optional per-sample dump (not written into report)
        "_probs": probs,
        "_entropy": entropy,
        "_targets": targets,
        "_qbar": qbar,
        "_logits_pos": logits_pos,
    }
    print(
        f"  AUC={auc:.3f}  ECE={ece:.3f}  "
        f"Sens={sens:.3f}  Spec={spec:.3f}  "
        f"H={result['mean_entropy']:.3f}  ρ={rho:.3f}"
    )
    return result


def write_report(results: list[dict], out_path: str):
    lines = [
        "# Q-VIB Proper Ablation Report (3 independently trained models)",
        "",
        "## Global Metrics",
        "",
        "| Variant | AUC-ROC | ECE | Sensitivity | Specificity | Mean Entropy | Entropy~q̅ (ρ) |",
        "|---------|---------|-----|-------------|-------------|--------------|---------------|",
    ]
    for r in results:
        pval_str = f"{r['entropy_pval']:.2e}" if r['entropy_pval'] < 0.001 else f"{r['entropy_pval']:.3f}"
        lines.append(
            f"| {r['name']} | {r['auc']:.3f} | {r['ece']:.3f} | "
            f"{r['sensitivity']:.3f} | {r['specificity']:.3f} | "
            f"{r['mean_entropy']:.3f} | {r['entropy_rho']:.3f} (p={pval_str}) |"
        )

    lines += ["", "## Per-q̅-Quintile: ECE and Entropy", ""]
    for r in results:
        lines += [
            f"### {r['name']}",
            "",
            "| q̅ range | AUC | ECE | Entropy | N |",
            "|---------|-----|-----|---------|---|",
        ]
        for seg in r["segments"]:
            auc_str = f"{seg['auc']:.3f}" if not (isinstance(seg['auc'], float) and seg['auc'] != seg['auc']) else "N/A"
            lines.append(
                f"| [{seg['q_bar_lo']:.2f},{seg['q_bar_hi']:.2f}] | {auc_str} | "
                f"{seg['ece']:.3f} | {seg['entropy']:.3f} | {seg['n']} |"
            )
        lines.append("")

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport -> {out_path}")


def dump_persample(result: dict, out_path: str) -> None:
    """Write per-sample CSV for bootstrap CI computation.

    Columns:
        logit_pos   – mean MC logit of class 1 (used in AUC ranking)
        prob_pos    – mean MC probability of class 1  (P(melanoma))
        conf        – max(prob_pos, 1-prob_pos) = confidence (used in ECE bins)
        correct     – 1 if argmax(probs) == target, else 0
        entropy_H   – predictive entropy H = -sum(p * log p)
        qbar        – mean quality scalar over the 5-channel quality vector

    Aggregates computed from this file must reproduce the eval_report_ablation.md
    values to within floating-point precision.
    NOTE: Only dumps the Q-VIB Full variant; other variants are skipped.
    """
    import pandas as pd

    probs      = result["_probs"]       # (N, 2)
    entropy    = result["_entropy"]     # (N,)
    targets    = result["_targets"]     # (N,)
    qbar       = result["_qbar"]        # (N,)
    logits_pos = result["_logits_pos"]  # (N,)

    conf    = np.maximum(probs[:, 0], probs[:, 1])
    correct = (probs.argmax(-1) == targets).astype(np.int8)

    df = pd.DataFrame({
        "logit_pos":  logits_pos.astype(np.float32),
        "prob_pos":   probs[:, 1].astype(np.float32),
        "conf":       conf.astype(np.float32),
        "correct":    correct,
        "entropy_H":  entropy.astype(np.float32),
        "qbar":       qbar.astype(np.float32),
        "target":     targets.astype(np.int8),
    })

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"Per-sample dump ({len(df)} rows) -> {out}")
    # Sanity-check: reproduced AUC/ECE must match report values to 1e-3
    from sklearn.metrics import roc_auc_score
    auc_check = float(roc_auc_score(targets, probs[:, 1]))
    ece_check = compute_ece(probs, targets)
    print(f"  Sanity AUC={auc_check:.3f}  ECE={ece_check:.3f}  "
          f"(must match eval_report_ablation.md Q-VIB Full row)")


def main():
    args = parse_args()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    results = []
    for variant in VARIANTS:
        ckpt_path = Path(variant["ckpt"])
        if not ckpt_path.exists():
            print(f"[SKIP] checkpoint not found: {ckpt_path}")
            continue
        print(f"\n--- {variant['name']} ---")
        results.append(eval_model(variant, args, device))

    if results:
        write_report(results, args.out)
        # Optional per-sample dump (Q-VIB Full only, for bootstrap CI)
        if args.save_persample:
            full_results = [r for r in results if "Q-VIB Full" in r["name"]]
            if full_results:
                dump_persample(full_results[0], args.save_persample)
            else:
                print("[WARN] --save-persample requested but Q-VIB Full variant not found/skipped.")


if __name__ == "__main__":
    main()
