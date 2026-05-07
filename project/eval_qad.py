"""Q-VIB Ablation Evaluation.

Runs ablation experiments comparing:
  Baseline 1: Standard VIB (fixed N(0,I) prior, no quality tokenizer)
  Baseline 2: Q-VIB adaptive prior only (no quality tokenizer)
  Baseline 3: Q-VIB full (adaptive prior + quality tokenizer)  [Ours]

Metrics (global + per q_bar quintile):
  - AUC-ROC (primary metric for melanoma detection)
  - Accuracy, Sensitivity, Specificity at optimal threshold (Youden's J)
  - ECE (Expected Calibration Error)
  - Mean predictive entropy

Uses precomputed ABCD cache -- no live MobileSAM during evaluation.

Usage:
    python eval_qad.py --config configs/qad.yaml --ckpt D:/YJ-Agent/checkpoints/best_qad.pth
"""

import argparse
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from omegaconf import OmegaConf
from sklearn.metrics import roc_auc_score, roc_curve
from torch.utils.data import DataLoader
from tqdm import tqdm

from data.qad_dataset import QADDataset, qad_collate_fn
from models.q_vib_encoder import QVIBEncoder
from models.qad_classifier import QADClassifier
from models.quality_adaptive_prior import QualityAdaptivePrior


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="configs/qad.yaml")
    p.add_argument("--ckpt", default="D:/YJ-Agent/checkpoints/best_qad.pth")
    p.add_argument("--n_mc", type=int, default=20, help="MC samples for predictive entropy")
    p.add_argument("--out", default="results/eval_report_qad.md")
    p.add_argument("--batch_size", type=int, default=512)
    return p.parse_args()


def predictive_entropy(
    encoder: QVIBEncoder,
    classifier: QADClassifier,
    abcd: torch.Tensor,
    q: torch.Tensor,
    n_mc: int,
    efnet_feat: torch.Tensor | None = None,
) -> tuple[torch.Tensor, torch.Tensor]:
    """MC estimate of predictive distribution and entropy."""
    probs_list = []
    with torch.no_grad():
        mu, log_sigma_sq = encoder(abcd, q, efnet_feat=efnet_feat)
        for _ in range(n_mc):
            z = encoder.reparameterize(mu, log_sigma_sq)
            logits = classifier(z)
            probs_list.append(F.softmax(logits, dim=-1))

    mean_probs = torch.stack(probs_list).mean(dim=0)  # (B, K)
    entropy = -(mean_probs * mean_probs.log().clamp(-20)).sum(dim=-1)  # (B,)
    return mean_probs, entropy


def compute_ece(probs: np.ndarray, targets: np.ndarray, n_bins: int = 10) -> float:
    """Expected Calibration Error."""
    confidences = probs.max(axis=-1)
    predictions = probs.argmax(axis=-1)
    correct = (predictions == targets).astype(float)

    bin_edges = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    for lo, hi in zip(bin_edges[:-1], bin_edges[1:]):
        mask = (confidences > lo) & (confidences <= hi)
        if mask.sum() == 0:
            continue
        acc_bin = correct[mask].mean()
        conf_bin = confidences[mask].mean()
        ece += mask.mean() * abs(acc_bin - conf_bin)
    return float(ece)


def best_threshold_metrics(probs: np.ndarray, targets: np.ndarray):
    """Sensitivity and specificity at Youden's J optimal threshold."""
    if targets.sum() == 0 or targets.sum() == len(targets):
        return 0.5, float("nan"), float("nan")
    fpr, tpr, thresholds = roc_curve(targets, probs[:, 1])
    j = tpr - fpr
    idx = np.argmax(j)
    sens = float(tpr[idx])
    spec = float(1 - fpr[idx])
    return float(thresholds[idx]), sens, spec


def run_ablation(
    variant: str,
    loader: DataLoader,
    encoder: QVIBEncoder,
    classifier: QADClassifier,
    device: torch.device,
    n_mc: int,
    use_tokenizer: bool,
    use_adaptive_prior: bool,
    prior: QualityAdaptivePrior,
) -> dict:
    """Collect predictions for one ablation variant using precomputed ABCD + EfficientNet cache."""
    all_probs, all_entropy, all_targets, all_qbar = [], [], [], []

    orig_tokenizer_fwd = None
    if not use_tokenizer:
        orig_tokenizer_fwd = encoder.tokenizer.forward
        encoder.tokenizer.forward = lambda q: torch.zeros(q.shape[0], device=q.device)

    orig_prior_variance = None
    if not use_adaptive_prior:
        orig_prior_variance = prior.prior_variance
        prior.prior_variance = lambda q_: torch.ones(q_.shape[0], device=q_.device)

    for batch in tqdm(loader, desc=variant, leave=False):
        abcd = batch["abcd"].to(device)
        q = batch["q"].to(device)
        targets = batch["target"]
        efnet_feat = batch["efnet_feat"].to(device) if "efnet_feat" in batch else None

        mean_probs, entropy = predictive_entropy(encoder, classifier, abcd, q, n_mc, efnet_feat=efnet_feat)

        all_probs.append(mean_probs.cpu().numpy())
        all_entropy.append(entropy.cpu().numpy())
        all_targets.append(targets.numpy())
        all_qbar.append(q.mean(dim=-1).cpu().numpy())

    if orig_tokenizer_fwd is not None:
        encoder.tokenizer.forward = orig_tokenizer_fwd
    if orig_prior_variance is not None:
        prior.prior_variance = orig_prior_variance

    probs = np.concatenate(all_probs)
    entropy = np.concatenate(all_entropy)
    targets = np.concatenate(all_targets)
    qbar = np.concatenate(all_qbar)

    # Global metrics
    acc = float((probs.argmax(-1) == targets).mean())
    ece = compute_ece(probs, targets)
    auc = float(roc_auc_score(targets, probs[:, 1]))
    thresh, sens, spec = best_threshold_metrics(probs, targets)

    # Per q_bar quintile
    quintiles = np.percentile(qbar, [0, 20, 40, 60, 80, 100])
    seg_results = []
    for lo, hi in zip(quintiles[:-1], quintiles[1:]):
        mask = (qbar >= lo) & (qbar <= hi)
        if mask.sum() < 10:
            continue
        seg_auc = (
            float(roc_auc_score(targets[mask], probs[mask, 1]))
            if targets[mask].sum() > 0 and targets[mask].sum() < mask.sum()
            else float("nan")
        )
        seg_ece = compute_ece(probs[mask], targets[mask])
        seg_entropy = float(entropy[mask].mean())
        seg_results.append({
            "q_bar_lo": float(lo),
            "q_bar_hi": float(hi),
            "q_bar_mean": float(qbar[mask].mean()),
            "auc": seg_auc,
            "ece": seg_ece,
            "entropy": seg_entropy,
            "n": int(mask.sum()),
        })

    # Spearman correlation: entropy vs q_bar (Proposition 2: should be negative)
    from scipy.stats import spearmanr
    rho, pval = spearmanr(qbar, entropy)
    entropy_qbar_corr = {"spearman_rho": float(rho), "pval": float(pval)}

    return {
        "variant": variant,
        "acc": acc,
        "ece": ece,
        "auc": auc,
        "sensitivity": sens,
        "specificity": spec,
        "mean_entropy": float(entropy.mean()),
        "entropy_qbar_corr": entropy_qbar_corr,
        "segments": seg_results,
    }


def write_report(results: list[dict], out_path: str):
    lines = [
        "# Q-VIB Ablation Evaluation Report",
        "",
        "## Global Metrics",
        "",
        "| Variant | AUC-ROC | ECE | Sensitivity | Specificity | Acc | Mean Entropy | Entropy~q̅ (ρ) |",
        "|---------|---------|-----|-------------|-------------|-----|--------------|---------------|",
    ]
    for r in results:
        rho = r["entropy_qbar_corr"]["spearman_rho"]
        pval = r["entropy_qbar_corr"]["pval"]
        pval_str = f"{pval:.2e}" if pval < 0.001 else f"{pval:.3f}"
        lines.append(
            f"| {r['variant']} | {r['auc']:.3f} | {r['ece']:.3f} | "
            f"{r['sensitivity']:.3f} | {r['specificity']:.3f} | "
            f"{r['acc']:.3f} | {r['mean_entropy']:.3f} | {rho:.3f} (p={pval_str}) |"
        )

    lines += ["", "## Per-q̅-Quintile Metrics", ""]
    for r in results:
        lines += [
            f"### {r['variant']}",
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
    print(f"Report written to {out_path}")


def main():
    args = parse_args()
    cfg = OmegaConf.load(args.config)
    device = torch.device("cuda" if cfg.device.cuda and torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    split_csv = cfg.data.get("split_csv", None)
    test_ds = QADDataset(
        quality_csv=cfg.data.labels_csv,
        metadata_csv=cfg.data.metadata_csv,
        abcd_cache_csv=cfg.data.abcd_cache_csv,
        efnet_features_npy=cfg.data.get("efnet_features_npy", None),
        efnet_index_csv=cfg.data.get("efnet_index_csv", None),
        split_csv=split_csv,
        split="test" if split_csv else None,
    )
    val_ds = test_ds  # alias for backward compatibility
    print(f"Eval set: {len(val_ds)} samples ({'test split' if split_csv else 'all data'})")
    print(f"  Positive (melanoma): {val_ds.df['target'].sum()} / {len(val_ds)}")

    val_loader = DataLoader(
        test_ds,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=cfg.data.num_workers,
        collate_fn=qad_collate_fn,
        multiprocessing_context="spawn",
        persistent_workers=True,
        pin_memory=False,
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
    ).to(device)

    classifier = QADClassifier(
        latent_dim=cfg.model.encoder.latent_dim,
        hidden_dim=cfg.model.classifier.hidden_dim,
        num_classes=cfg.model.classifier.num_classes,
    ).to(device)

    ckpt = torch.load(args.ckpt, map_location=device)
    encoder.load_state_dict(ckpt["encoder"])
    classifier.load_state_dict(ckpt["classifier"])
    encoder.eval()
    classifier.eval()
    print(f"Loaded checkpoint: {args.ckpt}")

    ablations = [
        ("Baseline 1: Std VIB",           False, False),
        ("Baseline 2: Adaptive Prior only", False, True),
        ("Ours: Q-VIB Full",               True,  True),
    ]

    results = []
    for name, use_tok, use_prior in ablations:
        print(f"\nRunning: {name}")
        r = run_ablation(
            name, val_loader, encoder, classifier,
            device, args.n_mc, use_tok, use_prior, prior,
        )
        results.append(r)
        print(
            f"  AUC={r['auc']:.3f}  ECE={r['ece']:.3f}  "
            f"Sens={r['sensitivity']:.3f}  Spec={r['specificity']:.3f}  "
            f"H={r['mean_entropy']:.3f}"
        )

    write_report(results, args.out)


if __name__ == "__main__":
    main()
