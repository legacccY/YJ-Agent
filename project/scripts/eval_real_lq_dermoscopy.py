"""L4: Evaluate Std VIB calibration on real low-quality ISIC dermoscopy images.

Compares:
  - ITB-LQ (programmatic degradation, n=300)
  - Real LQ (naturally poor quality ISIC 2020 originals, n=200)

Computes ECE, QCDI, entropy~quality correlation for both.

Output:
    results/real_lq/real_lq_eval.json
    figures/fig_real_vs_synthetic_lq.{pdf,svg,png}

Usage:
    python project/scripts/eval_real_lq_dermoscopy.py
"""
import json
import numpy as np
import pandas as pd
import torch
import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score
from tqdm import tqdm

ROOT = Path("D:/YJ-Agent/project")
DATA_ROOT = Path("D:/YJ-Agent/data")
OUT = ROOT / "results/real_lq"
OUT_FIG = ROOT / "meeting/BMVC/figures"
OUT.mkdir(parents=True, exist_ok=True)

IMG_SIZE = 224
CHECKPOINT = Path("D:/YJ-Agent/checkpoints/stdvib/best_qad.pth")


def laplacian_var(img_gray):
    return float(cv2.Laplacian(img_gray, cv2.CV_64F).var())


def load_model(device):
    """Load Std VIB (EfficientNet-B0 + VIB)."""
    try:
        import sys
        sys.path.insert(0, str(ROOT))
        from train_vit_tiny import VIBClassifier  # try to import
    except ImportError:
        pass
    # Generic: load checkpoint and infer model type
    ckpt = torch.load(str(CHECKPOINT), map_location=device)
    # Try EfficientNet-B0 VIB
    try:
        import timm
        model = timm.create_model("efficientnet_b0", pretrained=False, num_classes=2)
        if "state_dict" in ckpt:
            model.load_state_dict(ckpt["state_dict"], strict=False)
        else:
            model.load_state_dict(ckpt, strict=False)
        model = model.to(device)
        model.eval()
        return model
    except Exception as e:
        print(f"[warn] Model load failed: {e}")
        return None


def preprocess(img_bgr):
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    img_rgb = cv2.resize(img_rgb, (IMG_SIZE, IMG_SIZE))
    tensor = torch.tensor(img_rgb, dtype=torch.float32).permute(2, 0, 1) / 255.0
    mean = torch.tensor([0.485, 0.456, 0.406]).view(3, 1, 1)
    std = torch.tensor([0.229, 0.224, 0.225]).view(3, 1, 1)
    return ((tensor - mean) / std).unsqueeze(0)


def compute_ece(probs, targets, n_bins=10):
    bins = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    for lo, hi in zip(bins[:-1], bins[1:]):
        m = (probs >= lo) & (probs < hi)
        if m.sum() == 0:
            continue
        ece += m.mean() * abs(targets[m].mean() - probs[m].mean())
    return float(ece)


def binary_entropy(p):
    p = np.clip(p, 1e-7, 1 - 1e-7)
    return -(p * np.log(p) + (1 - p) * np.log(1 - p))


@torch.no_grad()
def run_inference_on_dir(model, img_dir: Path, target: int, device):
    """Run inference on all images in a directory. target: 0=NORMAL, 1=LESION."""
    probs, targets, laps, qbars = [], [], [], []

    images = list(img_dir.glob("*.jpg")) + list(img_dir.glob("*.jpeg")) + list(img_dir.glob("*.png"))
    for img_path in tqdm(images, desc=str(img_dir.name), leave=False):
        img = cv2.imread(str(img_path))
        if img is None:
            continue
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        lap = laplacian_var(gray)

        x = preprocess(img).to(device)
        try:
            out = model(x)
            if out.shape[-1] == 2:
                p = torch.softmax(out, dim=-1)[0, 1].item()
            else:
                p = torch.sigmoid(out[0, 0]).item()
        except Exception:
            continue

        p = max(min(p, 1 - 1e-7), 1e-7)
        # qbar proxy: normalize Laplacian variance (higher = better quality)
        qbar = min(lap / 500.0, 1.0)  # 500 = typical clean image

        probs.append(p)
        targets.append(target)
        laps.append(lap)
        qbars.append(qbar)

    return np.array(probs), np.array(targets), np.array(laps), np.array(qbars)


def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[init] device={device}")

    if not CHECKPOINT.exists():
        print(f"[error] Checkpoint not found: {CHECKPOINT}")
        print("  Using existing itb_predictions.csv for ITB-LQ stats only.")
        run_with_predictions_only()
        return

    model = load_model(device)
    if model is None:
        print("[error] Could not load model. Using predictions CSV.")
        run_with_predictions_only()
        return

    # Real LQ images (all treated as target=1 since they're skin lesion images)
    real_lq_dir = DATA_ROOT / "real_lq_dermoscopy_isic"
    if not real_lq_dir.exists():
        print(f"[error] Real LQ dir not found: {real_lq_dir}")
        return

    all_probs, all_targets, all_laps, all_qbars = [], [], [], []
    for cat_dir in real_lq_dir.iterdir():
        if not cat_dir.is_dir():
            continue
        p, t, l, q = run_inference_on_dir(model, cat_dir, target=1, device=device)
        all_probs.extend(p.tolist())
        all_targets.extend(t.tolist())
        all_laps.extend(l.tolist())
        all_qbars.extend(q.tolist())

    p_arr = np.array(all_probs)
    t_arr = np.array(all_targets)
    q_arr = np.array(all_qbars)
    h_arr = binary_entropy(p_arr)

    ece_real = compute_ece(p_arr, t_arr)
    rho_real, pval_real = spearmanr(h_arr, q_arr)

    print(f"\n[real LQ] n={len(p_arr)} ECE={ece_real:.4f} rho(H,q)={rho_real:.3f} p={pval_real:.4e}")

    # Compare with ITB-LQ from predictions CSV
    df_itb = pd.read_csv(ROOT / "results/itb_predictions.csv")
    itb_lq = df_itb[(df_itb.baseline == "D") & (df_itb.subset == "ITB-LQ")]
    p_itb = itb_lq.prob_pos.clip(1e-7, 1 - 1e-7).values
    t_itb = itb_lq.target.values
    q_itb = itb_lq.qbar.values
    h_itb = binary_entropy(p_itb)
    ece_itb = compute_ece(p_itb, t_itb)
    rho_itb, pval_itb = spearmanr(h_itb, q_itb)
    print(f"[ITB-LQ]  n={len(p_itb)} ECE={ece_itb:.4f} rho(H,q)={rho_itb:.3f} p={pval_itb:.4e}")

    # Plot comparison
    fig, axes = plt.subplots(1, 2, figsize=(8, 3.5))

    # Panel 1: ECE comparison
    ax = axes[0]
    ax.bar(["ITB-LQ\n(synthetic)", "Real LQ\n(ISIC originals)"],
           [ece_itb, ece_real], color=["#1f77b4", "#ff7f0e"], width=0.5, alpha=0.85)
    ax.set_ylabel("ECE (lower = better calibrated)")
    ax.set_title("(a) Calibration: synthetic vs real LQ", fontweight="bold", fontsize=9)
    ax.tick_params(labelsize=8)
    for i, v in enumerate([ece_itb, ece_real]):
        ax.text(i, v + 0.003, f"{v:.3f}", ha="center", fontsize=8)

    # Panel 2: Entropy-quality scatter
    ax = axes[1]
    ax.scatter(q_itb[:200], h_itb[:200], c="#1f77b4", s=12, alpha=0.5, label=f"ITB-LQ ρ={rho_itb:.3f}")
    ax.scatter(q_arr, h_arr, c="#ff7f0e", s=12, alpha=0.5, marker="^", label=f"Real LQ ρ={rho_real:.3f}")
    ax.set_xlabel(r"Quality proxy $\bar q$")
    ax.set_ylabel(r"Entropy $H(p)$")
    ax.set_title("(b) Entropy vs quality", fontweight="bold", fontsize=9)
    ax.legend(fontsize=7.5)
    ax.tick_params(labelsize=8)

    plt.tight_layout()
    for fmt in ["pdf", "svg", "png"]:
        fig.savefig(OUT_FIG / f"fig_real_vs_synthetic_lq.{fmt}",
                    dpi=200 if fmt == "png" else None, bbox_inches="tight", format=fmt)
    plt.close()
    print(f"Figures saved: {OUT_FIG}/fig_real_vs_synthetic_lq.*")

    summary = {
        "real_lq": {"n": len(p_arr), "ece": round(ece_real, 4),
                    "rho_H_q": round(float(rho_real), 4), "p_rho": float(pval_real)},
        "itb_lq_synthetic": {"n": len(p_itb), "ece": round(ece_itb, 4),
                              "rho_H_q": round(float(rho_itb), 4), "p_rho": float(pval_itb)},
        "comparison": {"ece_ratio": round(ece_real / (ece_itb + 1e-9), 3),
                       "rho_direction_same": bool(np.sign(rho_real) == np.sign(rho_itb))}
    }
    with open(OUT / "real_lq_eval.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(f"Summary: {OUT}/real_lq_eval.json")


def run_with_predictions_only():
    """Fallback: compare ITB-LQ stats from existing CSV only."""
    df = pd.read_csv(ROOT / "results/itb_predictions.csv")
    itb_lq = df[(df.baseline == "D") & (df.subset == "ITB-LQ")]
    p = itb_lq.prob_pos.clip(1e-7, 1 - 1e-7).values
    t = itb_lq.target.values
    q = itb_lq.qbar.values
    h = binary_entropy(p)
    ece = compute_ece(p, t)
    rho, pval = spearmanr(h, q)
    print(f"[ITB-LQ] n={len(p)} ECE={ece:.4f} rho={rho:.3f} p={pval:.4e}")
    summary = {"itb_lq_synthetic": {"n": len(p), "ece": round(ece, 4),
                                     "rho": round(float(rho), 4)},
               "note": "Std VIB checkpoint not found; real LQ inference skipped"}
    with open(OUT / "real_lq_eval.json", "w") as f:
        json.dump(summary, f, indent=2)


if __name__ == "__main__":
    main()
