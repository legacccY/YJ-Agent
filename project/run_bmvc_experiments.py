"""BMVC P2 完整实验流水线。

Experiments:
  1. QCTS on Std VIB (D): 3-seed stability, report mean alpha +/- std
  2. QCTS on EfficientNet-B3 (A): generalizability demo
  3. Functional form ablation: softplus vs linear vs piecewise
  4. Cross-dataset QCDI: HAM10000 + PAD-UFES from existing predictions
  5. Per-degradation ECE analysis on ITB-LQ

Usage:
  cd D:/YJ-Agent/project
  python run_bmvc_experiments.py
"""

import json
import os
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from PIL import Image
from scipy.optimize import minimize
from scipy.stats import spearmanr
from torch.utils.data import DataLoader, TensorDataset
from torchvision import models, transforms
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent))
from benchmark.metrics import compute_binary_ece, summary_metrics
from models.q_vib_encoder import QVIBEncoder
from models.qad_classifier import QADClassifier

os.environ["OMP_NUM_THREADS"] = "4"

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
ROOT = Path("D:/YJ-Agent")
PROJ = Path(__file__).parent
OUT = PROJ / "results"
OUT.mkdir(exist_ok=True)

METADATA_CSV = ROOT / "data/raw/isic2020/train-metadata.csv"
IMG_DIR = ROOT / "data/raw/isic2020/train-image/image"
SCORE_COLS = ["sharpness", "brightness", "completeness", "color_temp", "contrast"]
CHECK_DIMS = ["sharpness", "brightness", "color_temp", "contrast"]

print(f"[device] {DEVICE}")


# ══════════════════════════════════════════════════════════════════════════════
# Utils: QCTS functional forms
# ══════════════════════════════════════════════════════════════════════════════

def softplus(x):
    return np.log1p(np.exp(np.clip(x, -30, 30)))


def qcts_softplus(params, qbar):
    T0, alpha = params
    return softplus(T0 + alpha * (1.0 - qbar))


def qcts_linear(params, qbar):
    T0, alpha = params
    return np.maximum(T0 + alpha * (1.0 - qbar), 0.1)


def qcts_piecewise(params, qbar):
    """3 bins: LQ (q_bar<0.45), mid (0.45-0.55), HQ (q_bar>0.55)."""
    T_lq, T_mid, T_hq = params
    T_lq = np.maximum(T_lq, 0.05)
    T_mid = np.maximum(T_mid, 0.05)
    T_hq = np.maximum(T_hq, 0.05)
    T = np.where(qbar < 0.45, T_lq, np.where(qbar > 0.55, T_hq, T_mid))
    return T


def nll_loss(T, logits, targets):
    T = np.maximum(T, 1e-3)
    scaled = logits / T
    log_prob_pos = -np.log1p(np.exp(-scaled))
    log_prob_neg = -np.log1p(np.exp(scaled))
    nll = -(targets * log_prob_pos + (1 - targets) * log_prob_neg)
    return float(nll.mean())


def nll_softplus(params, logits, qbar, targets):
    return nll_loss(qcts_softplus(params, qbar), logits, targets)


def nll_linear(params, logits, qbar, targets):
    return nll_loss(qcts_linear(params, qbar), logits, targets)


def nll_piecewise(params, logits, qbar, targets):
    return nll_loss(qcts_piecewise(params, qbar), logits, targets)


def prob_from_logit_temp(logits, T):
    return 1.0 / (1.0 + np.exp(-logits / np.maximum(T, 1e-3)))


def compute_rho(prob, qbar):
    ent = -(prob * np.log(prob + 1e-9) + (1 - prob) * np.log(1 - prob + 1e-9))
    rho, _ = spearmanr(ent, qbar)
    return float(rho)


# ══════════════════════════════════════════════════════════════════════════════
# Part 1: Load common assets
# ══════════════════════════════════════════════════════════════════════════════

def load_assets():
    print("[assets] Loading common data...")
    q_labels = pd.read_csv(ROOT / "data/quality_labels_all.csv")
    abcd_cache = pd.read_csv(ROOT / "data/abcd_cache.csv")
    ef_index = pd.read_csv(ROOT / "data/efficientnet_index.csv")
    ef_all = np.load(ROOT / "data/efficientnet_features.npy", mmap_mode="r")
    isic_split = pd.read_csv(ROOT / "data/isic_split.csv")
    metadata = pd.read_csv(METADATA_CSV)[["isic_id", "target"]]
    itb_preds = pd.read_csv(OUT / "itb_predictions.csv")
    return q_labels, abcd_cache, ef_index, ef_all, isic_split, metadata, itb_preds


def _extract_isic_id(path_str):
    m = re.search(r"(ISIC_\d+)", str(path_str))
    return m.group(1) if m else None


# ══════════════════════════════════════════════════════════════════════════════
# Part 2: QCTS on Std VIB (D) — 3-seed stability + best-seed ITB eval
# ══════════════════════════════════════════════════════════════════════════════

def build_stdvib_val_tensors(q_labels, abcd_cache, ef_index, ef_all, isic_split, metadata):
    val_ids = set(isic_split[isic_split["split"] == "val"]["isic_id"])
    q_labels = q_labels.copy()
    q_labels["isic_id"] = q_labels["original_path"].apply(_extract_isic_id)
    q_val = q_labels[
        (q_labels["isic_id"].isin(val_ids)) & (q_labels["source"] == "isic2020")
    ].copy()
    q_val = (q_val
             .merge(metadata, on="isic_id", how="inner")
             .merge(abcd_cache, on="degraded_path", how="inner")
             .merge(ef_index, on="degraded_path", how="inner"))
    print(f"  [val/D] {len(q_val)} samples")
    abcd_arr = q_val[["A", "B", "C", "D"]].values.astype(np.float32)
    q_arr = q_val[SCORE_COLS].values.astype(np.float32)
    qbar_arr = q_arr.mean(axis=1)
    targets = q_val["target"].values.astype(np.int64)
    row_idxs = q_val["efnet_row_idx"].values
    ef_arr = ef_all[row_idxs].astype(np.float32)
    return (torch.tensor(abcd_arr), torch.tensor(q_arr), torch.tensor(qbar_arr),
            torch.tensor(ef_arr), torch.tensor(targets))


def load_stdvib():
    ckpt = torch.load(ROOT / "checkpoints/stdvib/best_qad.pth", map_location=DEVICE)
    encoder = QVIBEncoder(
        abcd_dim=4, q_dim=5, d_model=128, n_heads=4, latent_dim=64, efnet_dim=1280
    ).to(DEVICE).eval()
    classifier = QADClassifier(
        latent_dim=64, hidden_dim=128, num_classes=2, dropout=0.2
    ).to(DEVICE).eval()
    encoder.load_state_dict(ckpt["encoder"])
    classifier.load_state_dict(ckpt["classifier"])
    encoder.tokenizer.forward = lambda q: torch.zeros(q.shape[0], device=q.device)
    return encoder, classifier


def get_stdvib_val_logits(encoder, classifier, abcd_t, q_t, qbar_t, ef_t, targets_t,
                           batch_size=512):
    dataset = TensorDataset(abcd_t, q_t, qbar_t, ef_t, targets_t)
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=False, num_workers=0)
    all_logits, all_qbar, all_targets = [], [], []
    with torch.no_grad():
        for abcd_b, q_b, qbar_b, ef_b, tgt_b in tqdm(loader, desc="  [D val infer]"):
            mu, _ = encoder(abcd_b.to(DEVICE), q_b.to(DEVICE), efnet_feat=ef_b.to(DEVICE))
            logits_2 = classifier(mu)
            binary_logit = logits_2[:, 1] - logits_2[:, 0]
            all_logits.append(binary_logit.cpu().numpy())
            all_qbar.append(qbar_b.numpy())
            all_targets.append(tgt_b.numpy())
    return np.concatenate(all_logits), np.concatenate(all_qbar), np.concatenate(all_targets)


def fit_qcts_multiseed(logits, qbar, targets, n_seeds=3, form="softplus"):
    """Fit QCTS with n_seeds independent random inits. Returns all results for stability reporting."""
    results = []
    nll_fn_map = {
        "softplus": nll_softplus,
        "linear": nll_linear,
        "piecewise": nll_piecewise,
    }
    bounds_map = {
        "softplus": [(-5, 5), (0, 10)],
        "linear": [(0.1, 5), (0, 10)],
        "piecewise": [(0.05, 5), (0.05, 5), (0.05, 5)],
    }
    x0_dim = {"softplus": 2, "linear": 2, "piecewise": 3}
    nll_fn = nll_fn_map[form]
    bounds = bounds_map[form]
    dim = x0_dim[form]

    for seed in range(n_seeds):
        rng = np.random.default_rng(seed)
        x0 = rng.uniform(0.1, 1.0, size=dim)
        res = minimize(
            nll_fn, x0, args=(logits, qbar, targets),
            method="L-BFGS-B", bounds=bounds,
            options={"maxiter": 500},
        )
        results.append({"seed": seed, "params": res.x, "nll": res.fun})

    # Best params (lowest NLL)
    best = min(results, key=lambda r: r["nll"])
    return best["params"], results


def apply_qcts_itb(itb_preds, baseline_key, params, form="softplus"):
    """Apply fitted QCTS to an ITB baseline's predictions."""
    form_fn = {"softplus": qcts_softplus, "linear": qcts_linear, "piecewise": qcts_piecewise}
    df = itb_preds[itb_preds["baseline"] == baseline_key].copy()
    p = df["prob_pos"].clip(1e-7, 1 - 1e-7).values
    logits = np.log(p / (1 - p))
    qbar = df["qbar"].values
    T = form_fn[form](params, qbar)
    prob_q = 1.0 / (1.0 + np.exp(-logits / np.maximum(T, 1e-3)))
    df = df.copy()
    df["prob_qcts"] = prob_q
    return df


def eval_qcts_itb(df_qcts, baseline_key, form_name):
    rows = []
    for subset in sorted(df_qcts["subset"].unique()):
        sub = df_qcts[df_qcts["subset"] == subset]
        prob = sub["prob_qcts"].values
        targets = sub["target"].values
        qbar = sub["qbar"].values
        m = summary_metrics(prob, targets, qbar)
        rows.append({
            "baseline": f"{baseline_key}+QCTS-{form_name}",
            "baseline_name": f"{baseline_key} + QCTS ({form_name})",
            "subset": subset,
            "n": len(sub),
            **{k: v for k, v in m.items() if k != "qbar_ece_segments"},
        })
        print(f"    [{baseline_key}+QCTS-{form_name}] {subset}: AUC={m['auc']:.3f} ECE={m['ece']:.3f}")
    return rows


def run_qcts_stdvib(q_labels, abcd_cache, ef_index, ef_all, isic_split, metadata, itb_preds):
    print("\n" + "="*60)
    print("PART 2: QCTS on Std VIB (D)")
    print("="*60)

    print("[2a] Building val tensors...")
    abcd_t, q_t, qbar_t, ef_t, targets_t = build_stdvib_val_tensors(
        q_labels, abcd_cache, ef_index, ef_all, isic_split, metadata)

    print("[2b] Std VIB val inference...")
    encoder, classifier = load_stdvib()
    val_logits, val_qbar, val_targets = get_stdvib_val_logits(
        encoder, classifier, abcd_t, q_t, qbar_t, ef_t, targets_t)
    del encoder, classifier
    torch.cuda.empty_cache() if DEVICE.type == "cuda" else None

    # 3-seed stability
    print("[2c] Fitting QCTS (softplus, 3 seeds)...")
    best_params, all_results = fit_qcts_multiseed(val_logits, val_qbar, val_targets, n_seeds=3)
    alphas = [r["params"][1] for r in all_results]
    T0s = [r["params"][0] for r in all_results]
    print(f"  alpha values: {alphas}")
    print(f"  alpha mean={np.mean(alphas):.4f} +/- std={np.std(alphas):.4f}")
    print(f"  T0 mean={np.mean(T0s):.4f} +/- std={np.std(T0s):.4f}")
    T0, alpha = best_params
    T_lq = softplus(T0 + alpha)
    T_hq = softplus(T0)
    print(f"  Best: T0={T0:.4f} alpha={alpha:.4f}  T(q=0)={T_lq:.3f}  T(q=1)={T_hq:.3f}")

    # Save params
    params_dict = {
        "T0": float(T0), "alpha": float(alpha),
        "alpha_mean": float(np.mean(alphas)), "alpha_std": float(np.std(alphas)),
        "T0_mean": float(np.mean(T0s)), "T0_std": float(np.std(T0s)),
        "all_seeds": [{"seed": r["seed"], "T0": float(r["params"][0]),
                       "alpha": float(r["params"][1]), "nll": float(r["nll"])}
                      for r in all_results],
    }
    with open(OUT / "qcts_params.json", "w") as f:
        json.dump(params_dict, f, indent=2)
    print(f"  Saved: qcts_params.json")

    # Save T(q_bar) curve data for figure
    qbar_grid = np.linspace(0.0, 1.0, 200)
    T_curve = softplus(T0 + alpha * (1.0 - qbar_grid))
    T_curves_seeds = np.array([softplus(r["params"][0] + r["params"][1] * (1.0 - qbar_grid))
                                for r in all_results])
    np.save(OUT / "qcts_T_curve.npy", np.stack([qbar_grid, T_curve]))
    np.save(OUT / "qcts_T_curves_seeds.npy", np.vstack([qbar_grid[None], T_curves_seeds]))
    print(f"  Saved: qcts_T_curve.npy, qcts_T_curves_seeds.npy")

    # Evaluate on ITB
    print("[2d] Evaluating D+QCTS on ITB...")
    df_qcts = apply_qcts_itb(itb_preds, "D", best_params, form="softplus")
    rows = eval_qcts_itb(df_qcts, "D", "softplus")
    ece_lq = next(r["ece"] for r in rows if r["subset"] == "ITB-LQ")
    ece_hq = next(r["ece"] for r in rows if r["subset"] == "ITB-HQ")
    qcdi = ece_lq - ece_hq
    all_prob = df_qcts["prob_qcts"].values
    all_qbar = df_qcts["qbar"].values
    rho = compute_rho(all_prob, all_qbar)
    for r in rows:
        r["qcdi"] = qcdi
        r["rho"] = rho
    print(f"  QCDI={qcdi:.4f}  rho={rho:.4f}")

    qcts_df = pd.DataFrame(rows)
    qcts_df.to_csv(OUT / "qcts_itb_results.csv", index=False)
    print(f"  Saved: qcts_itb_results.csv")

    # Save QCTS predictions for downstream figures
    df_qcts_save = df_qcts.copy()
    df_qcts_save["baseline"] = "D+QCTS"
    df_qcts_save["prob_pos"] = df_qcts_save["prob_qcts"]
    df_qcts_save.drop(columns=["prob_qcts"], inplace=True)
    df_qcts_save.to_csv(OUT / "qcts_itb_predictions.csv", index=False)
    print(f"  Saved: qcts_itb_predictions.csv")

    return best_params, val_logits, val_qbar, val_targets


# ══════════════════════════════════════════════════════════════════════════════
# Part 3: QCTS on EfficientNet-B3 (A) — generalizability demo
# ══════════════════════════════════════════════════════════════════════════════

ISIC_TRANSFORM = transforms.Compose([
    transforms.Resize(300),
    transforms.CenterCrop(300),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
])


def load_efficientnet_b3():
    ckpt = torch.load(ROOT / "checkpoints/efficientnet_b3_isic.pth", map_location=DEVICE)
    in_features = ckpt["in_features"]
    model = models.efficientnet_b3(weights=None)
    model.classifier = torch.nn.Sequential(
        torch.nn.Dropout(p=0.3, inplace=True),
        torch.nn.Linear(in_features, 2),
    )
    model.load_state_dict(ckpt["model"])
    model = model.to(DEVICE).eval()
    return model


def get_efnet_val_logits(model, isic_split, metadata, q_labels):
    """Run EfficientNet-B3 inference on ISIC val images (original, not degraded)."""
    val_ids = set(isic_split[isic_split["split"] == "val"]["isic_id"])
    val_meta = metadata[metadata["isic_id"].isin(val_ids)].copy()

    # Get q_bar for val images: average over degraded versions
    q_labels2 = q_labels.copy()
    q_labels2["isic_id"] = q_labels2["original_path"].apply(_extract_isic_id)
    q_val = (q_labels2[q_labels2["isic_id"].isin(val_ids) & (q_labels2["source"] == "isic2020")]
             .groupby("isic_id")[SCORE_COLS].mean().reset_index())
    q_val["qbar"] = q_val[SCORE_COLS].mean(axis=1)
    val_meta = val_meta.merge(q_val[["isic_id", "qbar"]], on="isic_id", how="inner")
    print(f"  [val/A] {len(val_meta)} images (original)")

    all_logits, all_qbar, all_targets = [], [], []
    with torch.no_grad():
        for _, row in tqdm(val_meta.iterrows(), total=len(val_meta), desc="  [A val infer]"):
            img_path = IMG_DIR / f"{row['isic_id']}.jpg"
            if not img_path.exists():
                continue
            img = Image.open(img_path).convert("RGB")
            x = ISIC_TRANSFORM(img).unsqueeze(0).to(DEVICE)
            logit_2 = model(x)
            binary_logit = (logit_2[0, 1] - logit_2[0, 0]).item()
            all_logits.append(binary_logit)
            all_qbar.append(float(row["qbar"]))
            all_targets.append(int(row["target"]))

    return np.array(all_logits), np.array(all_qbar), np.array(all_targets)


def run_qcts_efnet(isic_split, metadata, q_labels, itb_preds):
    print("\n" + "="*60)
    print("PART 3: QCTS on EfficientNet-B3 (A)")
    print("="*60)

    print("[3a] Loading EfficientNet-B3...")
    model = load_efficientnet_b3()

    print("[3b] Val inference...")
    val_logits_a, val_qbar_a, val_targets_a = get_efnet_val_logits(
        model, isic_split, metadata, q_labels)
    del model
    torch.cuda.empty_cache() if DEVICE.type == "cuda" else None
    print(f"  Val set: n={len(val_logits_a)}")

    print("[3c] Fitting QCTS on A (3 seeds)...")
    best_params_a, all_results_a = fit_qcts_multiseed(
        val_logits_a, val_qbar_a, val_targets_a, n_seeds=3)
    alphas_a = [r["params"][1] for r in all_results_a]
    T0_a, alpha_a = best_params_a
    print(f"  alpha values: {alphas_a}")
    print(f"  alpha mean={np.mean(alphas_a):.4f} +/- std={np.std(alphas_a):.4f}")
    print(f"  Best: T0={T0_a:.4f} alpha={alpha_a:.4f}")

    params_a = {
        "T0": float(T0_a), "alpha": float(alpha_a),
        "alpha_mean": float(np.mean(alphas_a)), "alpha_std": float(np.std(alphas_a)),
        "all_seeds": [{"seed": r["seed"], "T0": float(r["params"][0]),
                       "alpha": float(r["params"][1]), "nll": float(r["nll"])}
                      for r in all_results_a],
    }
    with open(OUT / "qcts_a_params.json", "w") as f:
        json.dump(params_a, f, indent=2)
    print(f"  Saved: qcts_a_params.json")

    print("[3d] Evaluating A+QCTS on ITB...")
    df_qcts_a = apply_qcts_itb(itb_preds, "A", best_params_a, form="softplus")
    rows_a = eval_qcts_itb(df_qcts_a, "A", "softplus")
    ece_lq_a = next(r["ece"] for r in rows_a if r["subset"] == "ITB-LQ")
    ece_hq_a = next(r["ece"] for r in rows_a if r["subset"] == "ITB-HQ")
    qcdi_a = ece_lq_a - ece_hq_a
    all_prob_a = df_qcts_a["prob_qcts"].values
    rho_a = compute_rho(all_prob_a, df_qcts_a["qbar"].values)
    for r in rows_a:
        r["qcdi"] = qcdi_a
        r["rho"] = rho_a
    print(f"  QCDI={qcdi_a:.4f}  rho={rho_a:.4f}")

    # Compare A vs A+QCTS
    a_preds = itb_preds[itb_preds["baseline"] == "A"]
    for subset in ["ITB-LQ", "ITB-HQ"]:
        sub = a_preds[a_preds["subset"] == subset]
        ece_before = compute_binary_ece(sub["prob_pos"].values, sub["target"].values)
        row_after = next((r for r in rows_a if r["subset"] == subset), None)
        ece_after = row_after["ece"] if row_after else None
        print(f"  A {subset}: ECE {ece_before:.3f} → {ece_after:.3f} (QCTS)")

    pd.DataFrame(rows_a).to_csv(OUT / "qcts_a_itb_results.csv", index=False)
    print(f"  Saved: qcts_a_itb_results.csv")

    return best_params_a


# ══════════════════════════════════════════════════════════════════════════════
# Part 4: Functional form ablation (on Std VIB)
# ══════════════════════════════════════════════════════════════════════════════

def run_form_ablation(val_logits, val_qbar, val_targets, itb_preds):
    print("\n" + "="*60)
    print("PART 4: Functional Form Ablation")
    print("="*60)

    forms = {
        "softplus": (nll_softplus, [(-5, 5), (0, 10)], 2),
        "linear":   (nll_linear,   [(0.1, 5), (0, 10)], 2),
        "piecewise": (nll_piecewise, [(0.05, 5)] * 3, 3),
    }
    form_fn_T = {
        "softplus": qcts_softplus,
        "linear": qcts_linear,
        "piecewise": qcts_piecewise,
    }

    ablation_rows = []
    for form_name, (nll_fn, bounds, dim) in forms.items():
        best_nll = np.inf
        best_params = None
        for seed in range(3):
            rng = np.random.default_rng(seed)
            x0 = rng.uniform(0.1, 1.0, size=dim)
            res = minimize(nll_fn, x0, args=(val_logits, val_qbar, val_targets),
                           method="L-BFGS-B", bounds=bounds, options={"maxiter": 500})
            if res.fun < best_nll:
                best_nll = res.fun
                best_params = res.x

        # Eval on ITB
        df_qcts = apply_qcts_itb(itb_preds, "D", best_params, form=form_name)
        rows = eval_qcts_itb(df_qcts, "D", form_name)
        ece_lq = next(r["ece"] for r in rows if r["subset"] == "ITB-LQ")
        ece_hq = next(r["ece"] for r in rows if r["subset"] == "ITB-HQ")
        qcdi = ece_lq - ece_hq
        all_prob = df_qcts["prob_qcts"].values
        rho = compute_rho(all_prob, df_qcts["qbar"].values)
        val_nll = best_nll
        print(f"  [{form_name}] LQ ECE={ece_lq:.4f} HQ ECE={ece_hq:.4f} "
              f"QCDI={qcdi:.4f} rho={rho:.4f} val_NLL={val_nll:.4f}")
        ablation_rows.append({
            "form": form_name,
            "ece_lq": ece_lq, "ece_hq": ece_hq,
            "qcdi": qcdi, "rho": rho, "val_nll": val_nll,
        })

    abl_df = pd.DataFrame(ablation_rows)
    abl_df.to_csv(OUT / "qcts_form_ablation.csv", index=False)
    print(f"  Saved: qcts_form_ablation.csv")
    print(abl_df.to_string(index=False))
    return abl_df


# ══════════════════════════════════════════════════════════════════════════════
# Part 5: Cross-dataset QCDI from existing predictions
# ══════════════════════════════════════════════════════════════════════════════

def _qcdi_from_df(pred_df, lq_thresh=0.45, hq_thresh=0.50):
    """Compute QCDI = ECE(LQ) - ECE(HQ) for each baseline in pred_df."""
    rows = []
    for bl in sorted(pred_df["baseline"].unique()):
        sub = pred_df[pred_df["baseline"] == bl]
        prob = sub["prob_pos"].values
        targets = sub["target"].values
        qbar = sub["q_bar"].values if "q_bar" in sub.columns else sub["qbar"].values

        lq_mask = qbar < lq_thresh
        hq_mask = qbar > hq_thresh
        if lq_mask.sum() < 10 or hq_mask.sum() < 10:
            continue
        ece_lq = compute_binary_ece(prob[lq_mask], targets[lq_mask])
        ece_hq = compute_binary_ece(prob[hq_mask], targets[hq_mask])
        qcdi = ece_lq - ece_hq
        ent = -(prob * np.log(prob + 1e-9) + (1 - prob) * np.log(1 - prob + 1e-9))
        rho, pval = spearmanr(ent, qbar)
        rows.append({
            "baseline": bl, "n_lq": int(lq_mask.sum()), "n_hq": int(hq_mask.sum()),
            "ece_lq": ece_lq, "ece_hq": ece_hq, "qcdi": qcdi, "rho": float(rho),
        })
    return pd.DataFrame(rows)


def run_cross_dataset_qcdi():
    print("\n" + "="*60)
    print("PART 5: Cross-Dataset QCDI")
    print("="*60)

    ham_preds = pd.read_csv(OUT / "external_ham10000_predictions.csv")
    pad_preds = pd.read_csv(OUT / "external_pad_ufes_predictions.csv")
    itb_results = pd.read_csv(OUT / "itb_results.csv")

    # ITB QCDI from main results
    itb_qcdi_rows = []
    for bl in sorted(itb_results["baseline"].unique()):
        lq_row = itb_results[(itb_results["baseline"] == bl) & (itb_results["subset"] == "ITB-LQ")]
        hq_row = itb_results[(itb_results["baseline"] == bl) & (itb_results["subset"] == "ITB-HQ")]
        if len(lq_row) and len(hq_row):
            ece_lq = lq_row["ece"].values[0]
            ece_hq = hq_row["ece"].values[0]
            itb_qcdi_rows.append({"baseline": bl, "dataset": "ITB (ISIC)", "qcdi": ece_lq - ece_hq,
                                   "ece_lq": ece_lq, "ece_hq": ece_hq})

    ham_qcdi = _qcdi_from_df(ham_preds)
    ham_qcdi["dataset"] = "HAM10000"
    pad_qcdi = _qcdi_from_df(pad_preds)
    pad_qcdi["dataset"] = "PAD-UFES"

    print("\n  HAM10000 QCDI:")
    for _, row in ham_qcdi.iterrows():
        print(f"    {row['baseline']}: QCDI={row['qcdi']:.4f} "
              f"(LQ ECE={row['ece_lq']:.3f}, HQ ECE={row['ece_hq']:.3f})")

    print("\n  PAD-UFES QCDI:")
    for _, row in pad_qcdi.iterrows():
        print(f"    {row['baseline']}: QCDI={row['qcdi']:.4f} "
              f"(LQ ECE={row['ece_lq']:.3f}, HQ ECE={row['ece_hq']:.3f})")

    # QCDI cross-dataset consistency (Kendall tau)
    from scipy.stats import kendalltau
    common_bls = set(ham_qcdi["baseline"]) & set(pad_qcdi["baseline"]) & \
                 set(r["baseline"] for r in itb_qcdi_rows)
    common_bls = sorted(common_bls)
    if len(common_bls) >= 4:
        itb_q = [next(r["qcdi"] for r in itb_qcdi_rows if r["baseline"] == b) for b in common_bls]
        ham_q = [ham_qcdi[ham_qcdi["baseline"] == b]["qcdi"].values[0] for b in common_bls]
        pad_q = [pad_qcdi[pad_qcdi["baseline"] == b]["qcdi"].values[0] for b in common_bls]
        tau_ih, p_ih = kendalltau(itb_q, ham_q)
        tau_ip, p_ip = kendalltau(itb_q, pad_q)
        print(f"\n  Kendall τ (ITB vs HAM10000): {tau_ih:.3f} (p={p_ih:.3f})")
        print(f"  Kendall τ (ITB vs PAD-UFES): {tau_ip:.3f} (p={p_ip:.3f})")

    # Also compute cross-dataset rho (entropy~q_bar) comparison
    rho_rows = []
    for dataset_name, df in [("ITB (ISIC)", None), ("HAM10000", ham_preds), ("PAD-UFES", pad_preds)]:
        if df is None:
            continue
        qbar_col = "q_bar" if "q_bar" in df.columns else "qbar"
        for bl in sorted(df["baseline"].unique()):
            sub = df[df["baseline"] == bl]
            prob = sub["prob_pos"].values.clip(1e-7, 1 - 1e-7)
            ent = -(prob * np.log(prob) + (1 - prob) * np.log(1 - prob))
            qbar = sub[qbar_col].values
            rho, pval = spearmanr(ent, qbar)
            rho_rows.append({"dataset": dataset_name, "baseline": bl, "rho": float(rho), "pval": float(pval)})

    rho_df = pd.DataFrame(rho_rows)
    rho_df.to_csv(OUT / "cross_dataset_rho.csv", index=False)

    all_qcdi = pd.DataFrame(itb_qcdi_rows)
    cross_qcdi = pd.concat([all_qcdi[["baseline","dataset","qcdi","ece_lq","ece_hq"]],
                             ham_qcdi[["baseline","dataset","qcdi","ece_lq","ece_hq"]],
                             pad_qcdi[["baseline","dataset","qcdi","ece_lq","ece_hq"]]], ignore_index=True)
    cross_qcdi.to_csv(OUT / "cross_dataset_qcdi.csv", index=False)
    print(f"  Saved: cross_dataset_qcdi.csv, cross_dataset_rho.csv")

    return cross_qcdi, rho_df


# ══════════════════════════════════════════════════════════════════════════════
# Part 6: Per-degradation ECE on ITB-LQ
# ══════════════════════════════════════════════════════════════════════════════

def run_per_degradation(itb_preds, q_labels):
    print("\n" + "="*60)
    print("PART 6: Per-Degradation ECE (ITB-LQ)")
    print("="*60)

    DIM_LABEL = {
        "sharpness":  r"Blur ($q_1\downarrow$)",
        "brightness": r"Low brightness ($q_2\downarrow$)",
        "color_temp": r"Color temp ($q_4\downarrow$)",
        "contrast":   r"Low contrast ($q_5\downarrow$)",
    }

    itb_sub = pd.read_csv(OUT / "itb_subsets.csv")
    lq = itb_sub[itb_sub["subset"] == "ITB-LQ"].copy().reset_index(drop=True)
    lq["degraded_path"] = lq["image_path"].apply(str)
    q_sub = q_labels[CHECK_DIMS + ["degraded_path"]].copy()
    lq = lq.merge(q_sub, on="degraded_path", how="left").dropna(subset=CHECK_DIMS).reset_index(drop=True)

    # Use bottom-20th-percentile of each dim (consistent with Fig 3)
    rows = []
    show_bls = ["I", "J", "D", "F", "D+QCTS"]

    # Load QCTS predictions
    qcts_preds = None
    qcts_path = OUT / "qcts_itb_predictions.csv"
    if qcts_path.exists():
        qcts_preds = pd.read_csv(qcts_path)
        qcts_preds = qcts_preds[qcts_preds["subset"] == "ITB-LQ"].reset_index(drop=True)

    for bl in show_bls:
        if bl == "D+QCTS":
            if qcts_preds is None:
                continue
            bl_df = qcts_preds.reset_index(drop=True)
        else:
            bl_all = itb_preds[(itb_preds["baseline"] == bl) & (itb_preds["subset"] == "ITB-LQ")]
            bl_df = bl_all.reset_index(drop=True)
        if len(bl_df) == 0:
            continue

        min_len = min(len(bl_df), len(lq))
        for dim in CHECK_DIMS:
            thresh = np.percentile(lq[dim].values[:min_len], 20)
            mask = (lq[dim].values[:min_len] <= thresh)
            if mask.sum() < 10:
                continue
            prob = bl_df["prob_pos"].values[:min_len][mask]
            tgt = lq["target"].values[:min_len][mask]
            ece = compute_binary_ece(prob, tgt)
            rows.append({"baseline": bl, "dim": dim, "dim_label": DIM_LABEL[dim],
                         "n": int(mask.sum()), "ece": ece})
            print(f"  [{bl}] {DIM_LABEL[dim]}: ECE={ece:.4f} n={mask.sum()}")

    deg_df = pd.DataFrame(rows)
    deg_df.to_csv(OUT / "per_degradation_ece.csv", index=False)
    print(f"  Saved: per_degradation_ece.csv")
    return deg_df


# ══════════════════════════════════════════════════════════════════════════════
# Part 7: QCDI summary for all baselines (ITB)
# ══════════════════════════════════════════════════════════════════════════════

def compute_all_qcdi(itb_preds):
    print("\n" + "="*60)
    print("PART 7: QCDI Summary for All Baselines")
    print("="*60)

    # Load QCTS predictions and merge
    qcts_path = OUT / "qcts_itb_predictions.csv"
    combined = itb_preds.copy()
    if qcts_path.exists():
        qcts_df = pd.read_csv(qcts_path)
        combined = pd.concat([combined, qcts_df], ignore_index=True)

    rows = []
    for bl in sorted(combined["baseline"].unique()):
        sub = combined[combined["baseline"] == bl]
        lq = sub[sub["subset"] == "ITB-LQ"]
        hq = sub[sub["subset"] == "ITB-HQ"]
        if len(lq) == 0 or len(hq) == 0:
            continue
        ece_lq = compute_binary_ece(lq["prob_pos"].values, lq["target"].values)
        ece_hq = compute_binary_ece(hq["prob_pos"].values, hq["target"].values)
        qcdi = ece_lq - ece_hq
        # Taxonomy
        if qcdi > 0.10:
            taxonomy = "Quality-Oblivious"
        elif qcdi > 0.04:
            taxonomy = "Quality-Fragile"
        else:
            taxonomy = "Quality-Aware"
        rows.append({"baseline": bl, "ece_lq": ece_lq, "ece_hq": ece_hq,
                     "qcdi": qcdi, "taxonomy": taxonomy})
        print(f"  {bl}: QCDI={qcdi:.4f} ({taxonomy})")

    qcdi_df = pd.DataFrame(rows).sort_values("qcdi", ascending=False)
    qcdi_df.to_csv(OUT / "all_qcdi_summary.csv", index=False)
    print(f"  Saved: all_qcdi_summary.csv")
    return qcdi_df


# ══════════════════════════════════════════════════════════════════════════════
# Part 8: QCDI Threshold Sensitivity (reads from existing CSVs, no GPU needed)
# ══════════════════════════════════════════════════════════════════════════════

def run_threshold_sensitivity():
    """Sweep LQ threshold to show taxonomy classification is robust to threshold choice."""
    from scipy.stats import kendalltau
    print("\n" + "="*60)
    print("PART 8: Threshold Sensitivity")
    print("="*60)

    itb = pd.read_csv(OUT / "itb_predictions.csv")
    qcts_p = pd.read_csv(OUT / "qcts_itb_predictions.csv")
    qcts_p["baseline"] = "D+QCTS"
    # Use only ISIC 2020 subsets (exclude ITB-Diverse which is FitzPatrick17k)
    itb_isic = itb[itb["subset"] != "ITB-Diverse"].copy()
    all_preds = pd.concat([itb_isic, qcts_p[qcts_p["subset"] != "ITB-Diverse"]],
                          ignore_index=True)

    # Deduplicate: keep one row per (baseline, subset, prob_pos, target) —
    # some images appear in both ITB-LQ and ITB-Edge; we drop duplicates by
    # (baseline, prob_pos rounded to 6dp) to keep unique predictions.
    all_preds["_key"] = all_preds["baseline"] + "_" + all_preds["prob_pos"].round(6).astype(str)
    all_preds = all_preds.drop_duplicates(subset="_key").drop(columns="_key")
    print(f"  Unique predictions: {len(all_preds)} across {len(all_preds['baseline'].unique())} methods")

    lq_thresholds = np.round(np.arange(0.38, 0.47, 0.01), 2)
    hq_thresh = 0.50  # fixed HQ threshold

    rows = []
    for tau_lq in lq_thresholds:
        for bl in sorted(all_preds["baseline"].unique()):
            sub  = all_preds[all_preds["baseline"] == bl]
            qbar = sub["qbar"].values
            prob = sub["prob_pos"].values.clip(1e-7, 1 - 1e-7)
            tgts = sub["target"].values

            lq_mask = qbar < tau_lq
            hq_mask = qbar > hq_thresh
            if lq_mask.sum() < 15 or hq_mask.sum() < 15:
                continue
            ece_lq = compute_binary_ece(prob[lq_mask], tgts[lq_mask])
            ece_hq = compute_binary_ece(prob[hq_mask], tgts[hq_mask])
            qcdi   = ece_lq - ece_hq
            rows.append({"tau_lq": float(tau_lq), "baseline": bl,
                         "n_lq": int(lq_mask.sum()), "n_hq": int(hq_mask.sum()),
                         "ece_lq": ece_lq, "ece_hq": ece_hq, "qcdi": qcdi})

    df = pd.DataFrame(rows)
    df.to_csv(OUT / "threshold_sensitivity.csv", index=False)
    print(f"  Saved: threshold_sensitivity.csv")

    # Report QCDI range per method and taxonomy consistency
    ref_tau = 0.45
    ref_df = df[df["tau_lq"] == ref_tau][["baseline", "qcdi"]].set_index("baseline")
    print("\n  QCDI range across thresholds (taxonomy stability):")
    for bl in sorted(df["baseline"].unique()):
        bl_df = df[df["baseline"] == bl]
        qmin, qmax = bl_df["qcdi"].min(), bl_df["qcdi"].max()
        ref_q = float(ref_df.loc[bl, "qcdi"]) if bl in ref_df.index else float("nan")
        tax = "Oblivious" if ref_q > 0.10 else ("Fragile" if ref_q > 0.04 else "Aware")
        print(f"    {bl:10s}: [{qmin:.4f}, {qmax:.4f}]  ref={ref_q:.4f}  ({tax})")

    # Kendall tau between adjacent threshold rankings
    bls_common = sorted(df["baseline"].unique())
    taus_list = sorted(df["tau_lq"].unique())
    tau_vals = []
    for i in range(len(taus_list) - 1):
        t1, t2 = taus_list[i], taus_list[i+1]
        q1 = [df[(df["tau_lq"] == t1) & (df["baseline"] == b)]["qcdi"].values[0]
              for b in bls_common if len(df[(df["tau_lq"] == t1) & (df["baseline"] == b)]) > 0]
        q2 = [df[(df["tau_lq"] == t2) & (df["baseline"] == b)]["qcdi"].values[0]
              for b in bls_common if len(df[(df["tau_lq"] == t2) & (df["baseline"] == b)]) > 0]
        min_len = min(len(q1), len(q2))
        if min_len >= 4:
            kt, kp = kendalltau(q1[:min_len], q2[:min_len])
            tau_vals.append(kt)
    if tau_vals:
        print(f"\n  Kendall tau (adjacent thresholds): mean={np.mean(tau_vals):.3f}, "
              f"min={np.min(tau_vals):.3f}")

    return df


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("BMVC P2: Full Experiment Suite")
    print("=" * 60)

    # Load assets
    q_labels, abcd_cache, ef_index, ef_all, isic_split, metadata, itb_preds = load_assets()

    # Part 2: QCTS on Std VIB (D)
    best_params_d, val_logits, val_qbar, val_targets = run_qcts_stdvib(
        q_labels, abcd_cache, ef_index, ef_all, isic_split, metadata, itb_preds)

    # Part 3: QCTS on EfficientNet-B3 (A)
    try:
        best_params_a = run_qcts_efnet(isic_split, metadata, q_labels, itb_preds)
    except Exception as e:
        print(f"  [warn] EfficientNet-B3 QCTS skipped: {e}")
        best_params_a = None

    # Part 4: Functional form ablation
    run_form_ablation(val_logits, val_qbar, val_targets, itb_preds)

    # Part 5: Cross-dataset QCDI
    run_cross_dataset_qcdi()

    # Part 6: Per-degradation ECE
    run_per_degradation(itb_preds, q_labels)

    # Part 7: QCDI summary
    compute_all_qcdi(itb_preds)

    # Part 8: Threshold sensitivity (CSV-only, no GPU)
    run_threshold_sensitivity()

    print("\n" + "=" * 60)
    print("All experiments done.")
    print("Next: run gen_bmvc_figures.py to regenerate all figures.")
    print("=" * 60)


if __name__ == "__main__":
    main()
