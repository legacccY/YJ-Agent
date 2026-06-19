"""R6: query-for-retake agent vs SOTA selective-prediction / abstention baselines.

서비스: ICLR→ACCV/WACV 논문 C2 lever (query-for-retake as novel mechanism).
레버 설명: query-for-retake is the **first re-acquisition channel** in this setting;
  SOTA abstention methods (Chow / Ensemble / MC-Dropout / SelectiveNet) can only
  *defer* a case — they cannot request re-acquisition.
  R6 establishes: (a) what the risk-coverage tradeoff looks like for each method,
  (b) melanoma miss-rate at matched coverage, (c) honest comparison.

诚实底线 (C2.4 锁定，不改):
  全局 net benefit / 整体 sensitivity 仍 불초과 Direct diagnosis.
  R6 건립하는 것: retake = 정직한 정교 메커니즘 novelty (abstain ≠ re-acquire).
  If retake globally underperforms Direct → report as-is (expected, honest route).

Methods compared (all on ITB-LQ, n=300):
  Direct     : EfficientNet-B3 (Direct, no abstention, baseline A)
  Chow       : max-softmax confidence threshold (Chow 1970 / Geifman&El-Yaniv 2017)
               Source: same EfficientNet-B3 predictions, threshold on max(p, 1-p)
  DeepEnsemble: 3-seed Std VIB mean prediction, variance for abstention
               (s42/s123/s2024 — only 3 of the 5 seeds used in training have ITB-LQ preds;
                DeepEnsemble here = 3-member; 5-member ckpts s456/s789 missing, flagged TODO)
  MCDropout  : MC-Dropout (T=30 passes, N_MCD=30 in run_experiments.py),
               confidence of mean prediction used as selection score
               (per-sample variance not saved; mean confidence = proxy, flagged)
  SelectiveNet: trained selective head (g function) — ckpt loaded if available,
               skipped with WARNING if checkpoints/selectivenet_c*/best.pth missing
               (run train_selectivenet.py first)
  Retake     : query-for-retake agent — qbar as abstention signal (qbar < tau => retake/abstain)
               NOTE: in ITB-LQ, ALL images are low-quality; qbar varies 0.054–0.450.
               The retake channel is fundamentally different: it triggers RE-ACQUISITION,
               not just deferral. On ITB-LQ (static benchmark), we model it as:
               abstain when qbar < tau, predict on the rest.

Metrics:
  risk_coverage_auc : area under risk-coverage curve (lower = better selective predictor)
  melanoma_miss_rate: FN / total_pos at matched coverage (20%, 50%, 80%)
  coverage          : fraction predicted (1 - abstention_rate)
  risk              : error rate on covered fraction (1 - accuracy)
  For melanoma_miss_rate sweep: at each coverage level tau

Red lines:
  ① 官方 초파라미터 that are unknown → marked TODO, not guessed
  ② 诚实 negative results 如实 output, not suppressed
  ③ Per-class (melanoma) breakdown always included
  ④ 不启动训练 — main line calls Start-Process

Windows:
  DataLoader: multiprocessing_context='spawn', pin_memory=False
  Path: pathlib.Path
  PLCC/SRCC: pure numpy (no scipy.stats)

Usage:
  python project/run_r6_selective_compare.py
  python project/run_r6_selective_compare.py --smoke --cpu   # dry-run

Output:
  project/results/r6_selective_compare.csv       (method × metrics summary)
  project/results/r6_risk_coverage_curves.csv    (per-method per-threshold curves)
  project/results/r6_melanoma_miss_rate.csv      (per-method per-coverage)
  project/results/r6_summary.json
"""

import argparse
import json
import os
import sys
import warnings
from pathlib import Path

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import torch
import torch.nn as nn
import torch.nn.functional as F
from sklearn.metrics import roc_auc_score

ROOT = Path("D:/YJ-Agent/project")
CKPT_ROOT = Path("D:/YJ-Agent/checkpoints")
OUT_DIR  = ROOT / "results"
FIG_DIR  = ROOT / "report/figures"
OUT_DIR.mkdir(parents=True, exist_ok=True)
FIG_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(ROOT))

# ── Coverage target levels for SelectiveNet (official: Geifman & El-Yaniv 2019) ──
SEL_COVERAGE_TARGETS = [0.70, 0.75, 0.80, 0.85, 0.90, 0.95]

# ── Matched coverage thresholds for melanoma miss-rate comparison ─────────────
MATCHED_COVERAGES = [0.20, 0.50, 0.80]   # abstain 80%/50%/20%

DEVICE = torch.device("cpu")   # R6 是 evaluation only, CPU충분


# ── Helpers ───────────────────────────────────────────────────────────────────

def risk_coverage_curve(
    uncertainty_scores: np.ndarray,   # higher = more uncertain = more likely to abstain
    targets: np.ndarray,
    probs: np.ndarray,                # prob_pos for classification
    n_points: int = 100,
) -> pd.DataFrame:
    """
    Vary abstention threshold tau from low (predict all) to high (abstain all).
    At each tau: abstain samples with uncertainty > tau.
    Coverage = fraction predicted. Risk = 1 - accuracy on predicted.
    """
    thresholds = np.percentile(
        uncertainty_scores, np.linspace(0, 100, n_points + 1)
    )
    rows = []
    for tau in thresholds:
        # Keep samples with uncertainty <= tau (confident enough to predict)
        kept = uncertainty_scores <= tau
        coverage = kept.mean()
        if kept.sum() == 0:
            rows.append({
                "tau": float(tau), "coverage": 0.0,
                "risk": float("nan"), "n_kept": 0,
                "melanoma_miss_rate": float("nan"),
            })
            continue
        preds = (probs[kept] >= 0.5).astype(int)
        risk  = float((preds != targets[kept]).mean())

        # melanoma miss rate: how many melanoma in the *full* set are missed
        # (either abstained or predicted 0)
        pred_full = np.zeros(len(targets), dtype=int)   # abstained = predict nothing
        pred_full[kept] = preds
        n_pos = (targets == 1).sum()
        if n_pos > 0:
            mel_miss = float(((pred_full == 0) & (targets == 1)).sum() / n_pos)
        else:
            mel_miss = float("nan")

        rows.append({
            "tau": float(tau), "coverage": float(coverage),
            "risk": float(risk), "n_kept": int(kept.sum()),
            "melanoma_miss_rate": mel_miss,
        })
    return pd.DataFrame(rows)


def rc_auc(rc_df: pd.DataFrame) -> float:
    """Area under risk-coverage curve (trapezoidal, coverage as x-axis)."""
    df = rc_df.dropna(subset=["risk"]).sort_values("coverage")
    if len(df) < 2:
        return float("nan")
    return float(np.trapz(df["risk"].values, df["coverage"].values))


def melanoma_miss_at_coverage(rc_df: pd.DataFrame, target_coverage: float) -> float:
    """Interpolate melanoma_miss_rate at a target coverage level."""
    df = rc_df.dropna(subset=["melanoma_miss_rate"]).sort_values("coverage")
    if len(df) < 2:
        return float("nan")
    return float(np.interp(target_coverage, df["coverage"].values, df["melanoma_miss_rate"].values))


def risk_at_coverage(rc_df: pd.DataFrame, target_coverage: float) -> float:
    df = rc_df.dropna(subset=["risk"]).sort_values("coverage")
    if len(df) < 2:
        return float("nan")
    return float(np.interp(target_coverage, df["coverage"].values, df["risk"].values))


# ── Data loading ──────────────────────────────────────────────────────────────

def load_itb_lq() -> pd.DataFrame:
    """Load ITB-LQ n=300 from main predictions CSV (baseline A = EfficientNet-B3)."""
    pred_csv = OUT_DIR / "itb_predictions.csv"
    df = pd.read_csv(pred_csv)
    lq = df[df["subset"] == "ITB-LQ"].copy()
    return lq


def load_ensemble_seeds() -> dict[str, pd.DataFrame]:
    """Load per-seed ITB-LQ predictions for Deep Ensemble variance computation."""
    seeds = {}
    for s in ["s42", "s123", "s2024"]:
        p = OUT_DIR / f"itb_predictions_{s}.csv"
        if not p.exists():
            warnings.warn(f"Missing seed predictions: {p}")
            continue
        df = pd.read_csv(p)
        lq = df[(df["subset"] == "ITB-LQ") & (df["baseline"] == "D")].copy()
        seeds[s] = lq.reset_index(drop=True)
    return seeds


# ── SelectiveNet inference (load trained g head) ──────────────────────────────

def _try_load_selectivenet(coverage_target: float):
    """
    Load SelectiveNet g head for a given coverage target.
    Returns g_head (eval mode) or None if ckpt not found.
    """
    c_str = f"{int(coverage_target*100):02d}"
    ckpt_path = CKPT_ROOT / f"selectivenet_c{c_str}/best.pth"
    if not ckpt_path.exists():
        return None, None

    try:
        from models.q_vib_encoder import QVIBEncoder
        from models.qad_classifier import QADClassifier
        from train_selectivenet import SelectionHead, LATENT_DIM, HIDDEN_DIM
    except ImportError as e:
        warnings.warn(f"Cannot import SelectiveNet components: {e}")
        return None, None

    ckpt = torch.load(ckpt_path, map_location=DEVICE, weights_only=False)

    # Frozen backbone
    enc_ckpt = torch.load(
        CKPT_ROOT / "stdvib/best_qad.pth", map_location=DEVICE, weights_only=False
    )
    encoder = QVIBEncoder(
        abcd_dim=4, q_dim=5, d_model=128, n_heads=4, latent_dim=LATENT_DIM, efnet_dim=1280,
    ).to(DEVICE).eval()
    encoder.load_state_dict(enc_ckpt["encoder"])
    encoder.tokenizer.forward = lambda q: torch.zeros(q.shape[0], device=DEVICE)
    for p in encoder.parameters():
        p.requires_grad_(False)

    g_head = SelectionHead(LATENT_DIM, HIDDEN_DIM).to(DEVICE).eval()
    g_head.load_state_dict(ckpt["g_head"])

    return encoder, g_head


def run_selectivenet_inference(
    lq_df: pd.DataFrame,
    coverage_target: float,
) -> np.ndarray | None:
    """
    Run SelectiveNet g(x) on ITB-LQ images to get selection scores.
    Returns numpy array of selection scores (higher = more certain = keep).
    Returns None if ckpt unavailable.
    Needs image features: requires agent/tools.extract_features (uses GPU/CPU).
    """
    encoder, g_head = _try_load_selectivenet(coverage_target)
    if encoder is None:
        return None

    try:
        from agent.tools import extract_features
        import cv2
        from PIL import Image
    except ImportError as e:
        warnings.warn(f"SelectiveNet inference import failed: {e}")
        return None

    scores = []
    for _, row in lq_df.iterrows():
        img_path = str(row.get("image_name", ""))
        # Retrieve image via ITB subsets CSV for path
        # (itb_predictions.csv has image_name = isic_id, need actual file path)
        # Fallback: use itb_subsets.csv to get image_path
        continue   # placeholder: full inference requires image loading below

    # Full inference path: load ITB subsets for file paths
    itb_subsets = pd.read_csv(OUT_DIR / "itb_subsets.csv")
    lq_sub = itb_subsets[itb_subsets["subset"] == "ITB-LQ"].reset_index(drop=True)

    # Align with lq_df by isic_id order
    main_ids = lq_df["image_name"].tolist() if "image_name" in lq_df.columns else []
    if main_ids:
        lq_sub = lq_sub[lq_sub["isic_id"].isin(set(main_ids))]
        # Re-order to match lq_df
        id_to_row = {r.isic_id: r for _, r in lq_sub.iterrows()}

    import cv2
    g_scores = []
    for img_id in main_ids:
        row_s = id_to_row.get(img_id)
        if row_s is None:
            g_scores.append(0.5)
            continue
        img = cv2.imread(str(row_s.image_path))
        if img is None:
            g_scores.append(0.5)
            continue
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        try:
            from agent.tools import extract_features
            feats = extract_features(img)
            abcd_t = torch.tensor(feats.abcd, dtype=torch.float32).unsqueeze(0).to(DEVICE)
            q_t    = torch.tensor(feats.q_vector, dtype=torch.float32).unsqueeze(0).to(DEVICE)
            ef_t   = torch.tensor(feats.efnet_feat, dtype=torch.float32).unsqueeze(0).to(DEVICE)
            with torch.no_grad():
                mu, _ = encoder(abcd_t, q_t, efnet_feat=ef_t)
                g_val = g_head(mu).item()
            g_scores.append(g_val)
        except Exception as ex:
            warnings.warn(f"SelectiveNet g inference failed for {img_id}: {ex}")
            g_scores.append(0.5)

    return np.array(g_scores, dtype=np.float32)


# ── Method definitions ────────────────────────────────────────────────────────

def build_methods(lq_all: pd.DataFrame, seeds: dict, smoke: bool) -> list[dict]:
    """
    Build list of method dicts with keys:
      name, probs, targets, uncertainty_scores
    uncertainty_scores: higher = more uncertain = more likely to abstain
    """
    methods = []

    # ── Direct: no abstention (baseline, reference line) ─────────────────────
    lq_A = lq_all[lq_all["baseline"] == "A"].reset_index(drop=True)
    methods.append({
        "name": "Direct (EfficientNet-B3)",
        "key": "direct",
        "probs": lq_A["prob_pos"].values.copy(),
        "targets": lq_A["target"].values.copy(),
        "uncertainty_scores": np.zeros(len(lq_A)),  # never abstains
        "note": "Reference: no abstention",
    })

    # ── Chow's rule: max-softmax threshold ────────────────────────────────────
    # Confidence = max(p, 1-p); uncertainty = 1 - confidence
    # Source: Chow 1970, Geifman & El-Yaniv 2017 (SelectiveNet paper baseline)
    p_A = lq_A["prob_pos"].values
    conf_chow = np.maximum(p_A, 1.0 - p_A)
    unc_chow  = 1.0 - conf_chow
    methods.append({
        "name": "Chow's rule (max-softmax)",
        "key": "chow",
        "probs": p_A.copy(),
        "targets": lq_A["target"].values.copy(),
        "uncertainty_scores": unc_chow,
        "note": "Chow 1970 / Geifman&El-Yaniv 2017; abstain = low max-softmax confidence",
    })

    # ── Deep Ensemble (3-seed) ────────────────────────────────────────────────
    # Uncertainty = predictive variance across seeds
    # NOTE: only 3 seeds available (s42/s123/s2024); s456/s789 ckpts missing
    # TODO: re-run run_experiments.py --baseline J with s456/s789 to get 5-seed ensemble
    if len(seeds) >= 2:
        probs_matrix = np.stack([s["prob_pos"].values for s in seeds.values()])  # (S, N)
        mean_p = probs_matrix.mean(0)
        var_p  = probs_matrix.var(0)
        tgt_ens = list(seeds.values())[0]["target"].values
        methods.append({
            "name": f"Deep Ensemble ({len(seeds)}-seed)",
            "key": "ensemble",
            "probs": mean_p,
            "targets": tgt_ens.copy(),
            "uncertainty_scores": var_p,   # higher variance = less certain
            "note": (f"Deep Ensemble {len(seeds)}-seed (s42/s123/s2024); "
                     f"uncertainty = predictive variance. "
                     f"TODO: s456/s789 ckpts missing, ideally 5-seed per paper."),
        })
    else:
        warnings.warn("Deep Ensemble: < 2 seed CSVs found, skipping")

    # ── MC-Dropout ────────────────────────────────────────────────────────────
    # Using confidence of mean prediction as selection score (proxy)
    # NOTE: per-sample T-pass variance not saved in itb_predictions.csv (I baseline)
    # The T=30 passes are averaged before saving prob_pos.
    # Using confidence = max(p, 1-p) of mean prediction as uncertainty proxy.
    # TODO: re-run run_mcdropout_baseline with variance logging for exact MC-Dropout UQ.
    lq_I = lq_all[lq_all["baseline"] == "I"].reset_index(drop=True)
    if len(lq_I) > 0:
        p_I = lq_I["prob_pos"].values
        conf_I = np.maximum(p_I, 1.0 - p_I)
        unc_I  = 1.0 - conf_I
        methods.append({
            "name": "MC-Dropout (T=30, mean-conf proxy)",
            "key": "mcdropout",
            "probs": p_I.copy(),
            "targets": lq_I["target"].values.copy(),
            "uncertainty_scores": unc_I,
            "note": ("MC-Dropout T=30 (N_MCD=30 in run_experiments.py). "
                     "Uncertainty proxy = 1 - max(p, 1-p) of averaged prediction. "
                     "TODO: exact MC-Dropout UQ requires re-running inference with "
                     "per-sample variance logging (not yet saved in itb_predictions.csv I baseline)."),
        })
    else:
        warnings.warn("MC-Dropout (baseline I) not found in ITB-LQ predictions")

    # ── SelectiveNet (per coverage target) ───────────────────────────────────
    # Load all available coverage targets; skip silently if ckpt missing
    sel_added = False
    for c in SEL_COVERAGE_TARGETS:
        c_str = f"{int(c*100):02d}"
        ckpt_path = CKPT_ROOT / f"selectivenet_c{c_str}/best.pth"
        if not ckpt_path.exists():
            continue
        g_scores = run_selectivenet_inference(lq_A, coverage_target=c)
        if g_scores is None:
            continue
        # SelectiveNet: g(x) in [0,1]; uncertainty = 1 - g(x)
        unc_sel = 1.0 - g_scores
        methods.append({
            "name": f"SelectiveNet (c={c:.2f})",
            "key": f"selectivenet_c{c_str}",
            "probs": p_A.copy(),
            "targets": lq_A["target"].values.copy(),
            "uncertainty_scores": unc_sel,
            "note": (f"SelectiveNet Geifman&El-Yaniv 2019; lambda=32, alpha=0.5, "
                     f"coverage_target={c:.2f}; g head on frozen stdvib encoder."),
        })
        sel_added = True

    if not sel_added:
        print("WARNING: No SelectiveNet checkpoints found.")
        print("  -> Run: python project/train_selectivenet.py --coverage all")
        print("  -> Then re-run this script to include SelectiveNet comparison.")

    # ── Query-for-retake (our agent) ─────────────────────────────────────────
    # Abstention signal = qbar (image quality score)
    # Low qbar = low quality = trigger retake channel
    # In ITB-LQ: qbar ∈ [0.054, 0.450] — all images are low quality
    # Abstain (trigger retake) when qbar < tau (i.e., uncertainty = 1 - qbar)
    # This is orthogonal to prediction confidence: we abstain based on IMAGE QUALITY,
    # not model uncertainty. This is the key mechanism novelty vs Chow/Ensemble/MCDrop.
    lq_D = lq_all[lq_all["baseline"] == "D"].reset_index(drop=True)  # Std VIB
    if len(lq_D) > 0:
        qbar_D = lq_D["qbar"].values
        p_D    = lq_D["prob_pos"].values
        # uncertainty = 1 - qbar (low quality = high uncertainty for retake)
        unc_retake = 1.0 - qbar_D
        methods.append({
            "name": "Query-for-Retake (qbar threshold)",
            "key": "retake",
            "probs": p_D.copy(),
            "targets": lq_D["target"].values.copy(),
            "uncertainty_scores": unc_retake,
            "note": ("Query-for-retake: abstain when qbar < tau (image quality signal). "
                     "Orthogonal to prediction confidence. Prediction model = Std VIB. "
                     "KEY DISTINCTION: retake triggers re-acquisition (new image request); "
                     "other methods defer to human. On ITB-LQ static benchmark, "
                     "modelled as abstention on qbar signal."),
        })
    else:
        warnings.warn("Std VIB (baseline D) not found for query-for-retake method")

    return methods


# ── Compute all metrics ───────────────────────────────────────────────────────

def compute_all_metrics(methods: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Returns:
      summary_df       : method × {rc_auc, mel_miss@20%, mel_miss@50%, mel_miss@80%, ...}
      curves_df        : all risk-coverage curves
      mel_miss_df      : melanoma miss rate per method per coverage target
    """
    summary_rows = []
    all_curves = []
    mel_miss_rows = []

    for m in methods:
        name   = m["name"]
        key    = m["key"]
        probs  = m["probs"]
        tgts   = m["targets"]
        unc    = m["uncertainty_scores"]

        # Direct: no abstention — single operating point
        is_direct = key == "direct"

        if is_direct:
            # No abstention: coverage = 1.0, risk = error rate
            preds = (probs >= 0.5).astype(int)
            risk  = float((preds != tgts).mean())
            n_pos = (tgts == 1).sum()
            mel_miss_full = float(((preds == 0) & (tgts == 1)).sum() / max(n_pos, 1))
            try:
                auc_roc = roc_auc_score(tgts, probs)
            except Exception:
                auc_roc = float("nan")

            rc_df = pd.DataFrame([{
                "tau": 0.0, "coverage": 1.0, "risk": risk,
                "n_kept": int(len(tgts)), "melanoma_miss_rate": mel_miss_full,
            }])
            rc_auc_val = float("nan")  # undefined for single point

            # Melanoma miss rate at each coverage target (all 1.0 since no abstention)
            for cv in MATCHED_COVERAGES:
                mel_miss_rows.append({
                    "method": name, "key": key,
                    "coverage_target": cv,
                    "melanoma_miss_rate": mel_miss_full,
                    "risk": risk,
                })
            summary_rows.append({
                "method": name, "key": key,
                "rc_auc": rc_auc_val,
                "risk_at_full_coverage": risk,
                "auc_roc": auc_roc,
                "mel_miss_at_cov20": mel_miss_full,
                "mel_miss_at_cov50": mel_miss_full,
                "mel_miss_at_cov80": mel_miss_full,
                "n": int(len(tgts)),
                "n_pos": int(n_pos),
                "note": m.get("note", ""),
            })
        else:
            rc_df = risk_coverage_curve(unc, tgts, probs)
            rc_auc_val = rc_auc(rc_df)
            try:
                auc_roc = roc_auc_score(tgts, probs)
            except Exception:
                auc_roc = float("nan")

            mel_misses = {}
            risks = {}
            for cv in MATCHED_COVERAGES:
                mm = melanoma_miss_at_coverage(rc_df, cv)
                rk = risk_at_coverage(rc_df, cv)
                mel_misses[cv] = mm
                risks[cv] = rk
                mel_miss_rows.append({
                    "method": name, "key": key,
                    "coverage_target": cv,
                    "melanoma_miss_rate": mm,
                    "risk": rk,
                })

            n_pos = int((tgts == 1).sum())
            summary_rows.append({
                "method": name, "key": key,
                "rc_auc": rc_auc_val,
                "risk_at_full_coverage": risk_at_coverage(rc_df, 1.0),
                "auc_roc": auc_roc,
                "mel_miss_at_cov20": mel_misses.get(0.20, float("nan")),
                "mel_miss_at_cov50": mel_misses.get(0.50, float("nan")),
                "mel_miss_at_cov80": mel_misses.get(0.80, float("nan")),
                "n": int(len(tgts)),
                "n_pos": n_pos,
                "note": m.get("note", ""),
            })

        rc_df["method"] = name
        rc_df["key"] = key
        all_curves.append(rc_df)

    summary_df  = pd.DataFrame(summary_rows)
    curves_df   = pd.concat(all_curves, ignore_index=True)
    mel_miss_df = pd.DataFrame(mel_miss_rows)
    return summary_df, curves_df, mel_miss_df


# ── Plot ──────────────────────────────────────────────────────────────────────

METHOD_COLORS = {
    "direct":      "#636363",
    "chow":        "#1f77b4",
    "ensemble":    "#ff7f0e",
    "mcdropout":   "#2ca02c",
    "retake":      "#d62728",
}

def plot_risk_coverage(curves_df: pd.DataFrame, methods: list[dict], out_path: Path):
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.0))

    # Left: Risk-Coverage curves
    ax = axes[0]
    for m in methods:
        key  = m["key"]
        name = m["name"]
        sub  = curves_df[curves_df["key"] == key].sort_values("coverage")
        sub  = sub.dropna(subset=["risk"])
        if len(sub) == 0:
            continue
        color = METHOD_COLORS.get(key.split("_")[0], "#9467bd")
        lw = 2.0 if key == "retake" else 1.4
        ls = "-" if key != "direct" else "--"
        ax.plot(sub["coverage"], sub["risk"], color=color, lw=lw, ls=ls, label=name)

    ax.set_xlabel("Coverage (fraction predicted)", fontsize=9)
    ax.set_ylabel("Risk (error rate on covered)", fontsize=9)
    ax.set_title("(a) Risk-Coverage Curve (ITB-LQ, n=300)", fontsize=9, fontweight="bold")
    ax.legend(fontsize=7, loc="upper right")
    ax.tick_params(labelsize=8)
    ax.set_xlim(0, 1)

    # Right: Melanoma miss rate at coverage
    ax = axes[1]
    for m in methods:
        key  = m["key"]
        name = m["name"]
        sub  = curves_df[curves_df["key"] == key].sort_values("coverage")
        sub  = sub.dropna(subset=["melanoma_miss_rate"])
        if len(sub) == 0:
            continue
        color = METHOD_COLORS.get(key.split("_")[0], "#9467bd")
        lw = 2.0 if key == "retake" else 1.4
        ls = "-" if key != "direct" else "--"
        ax.plot(sub["coverage"], sub["melanoma_miss_rate"], color=color, lw=lw, ls=ls, label=name)

    ax.set_xlabel("Coverage (fraction predicted)", fontsize=9)
    ax.set_ylabel("Melanoma miss rate (FN / total melanoma)", fontsize=9)
    ax.set_title("(b) Melanoma Miss Rate vs Coverage (ITB-LQ)", fontsize=9, fontweight="bold")
    ax.legend(fontsize=7, loc="upper right")
    ax.tick_params(labelsize=8)
    ax.set_xlim(0, 1)

    plt.tight_layout()
    for fmt in ["pdf", "png"]:
        fig.savefig(out_path.with_suffix(f".{fmt}"),
                    dpi=200 if fmt == "png" else None,
                    bbox_inches="tight")
    plt.close()
    print(f"  Figure saved: {out_path}.pdf / .png")


# ── Honest negative check ─────────────────────────────────────────────────────

def honest_negative_check(summary_df: pd.DataFrame) -> dict:
    """
    Verify C2.4 诚实底线:
      - R6 does NOT claim retake globally beats Direct
      - Report honestly if retake underperforms Direct at full coverage
    Returns dict with honesty flags.
    """
    flags = {}
    direct_row = summary_df[summary_df["key"] == "direct"]
    retake_row = summary_df[summary_df["key"] == "retake"]

    if len(direct_row) == 0 or len(retake_row) == 0:
        return {"check": "incomplete", "note": "direct or retake row missing"}

    direct_risk = direct_row.iloc[0]["risk_at_full_coverage"]
    retake_risk = retake_row.iloc[0]["mel_miss_at_cov80"]  # retake at 80% coverage

    flags["direct_risk_at_full_coverage"] = round(float(direct_risk), 4)
    flags["retake_mel_miss_at_cov80"] = round(float(retake_risk), 4)
    flags["C2_4_check"] = (
        "PASS (retake does not globally beat Direct — honest negative as expected)"
        if direct_risk <= float(retake_row.iloc[0]["risk_at_full_coverage"])
        else "NOTE: retake risk lower than Direct at full coverage — double-check coverage alignment"
    )
    return flags


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="Use small subset for quick test")
    ap.add_argument("--cpu",   action="store_true", help="Force CPU")
    args = ap.parse_args()

    global DEVICE
    if args.cpu:
        DEVICE = torch.device("cpu")

    print("=== R6: Selective Prediction Comparison (ITB-LQ n=300) ===")
    print(f"  device={DEVICE}")

    # Load data
    lq_all = load_itb_lq()
    seeds  = load_ensemble_seeds()
    print(f"  ITB-LQ loaded: {lq_all['baseline'].nunique()} baselines, "
          f"total {len(lq_all)} rows")
    print(f"  Ensemble seeds loaded: {list(seeds.keys())}")

    if args.smoke:
        # Quick smoke: only keep first 50 rows per baseline
        print("  SMOKE mode: truncating to 50 rows per baseline")
        lq_all = pd.concat(
            [grp.head(50) for _, grp in lq_all.groupby("baseline")],
            ignore_index=True,
        )
        seeds = {k: v.head(50) for k, v in seeds.items()}

    # Build methods
    methods = build_methods(lq_all, seeds, smoke=args.smoke)
    print(f"\n  Methods ready: {[m['name'] for m in methods]}")

    # Compute metrics
    print("\n=== Computing risk-coverage metrics ===")
    summary_df, curves_df, mel_miss_df = compute_all_metrics(methods)

    # Print summary
    print("\n=== Summary (ITB-LQ, n=300) ===")
    cols_show = ["method", "rc_auc", "risk_at_full_coverage", "auc_roc",
                 "mel_miss_at_cov20", "mel_miss_at_cov50", "mel_miss_at_cov80"]
    print(summary_df[cols_show].to_string(index=False, float_format="{:.4f}".format))

    # Honest negative check (C2.4)
    honesty = honest_negative_check(summary_df)
    print(f"\n=== Honest Negative Check (C2.4) ===")
    for k, v in honesty.items():
        print(f"  {k}: {v}")

    # Save outputs
    print("\n=== Saving outputs ===")
    summary_df.to_csv(OUT_DIR / "r6_selective_compare.csv", index=False)
    print(f"  {OUT_DIR}/r6_selective_compare.csv")

    curves_df.to_csv(OUT_DIR / "r6_risk_coverage_curves.csv", index=False)
    print(f"  {OUT_DIR}/r6_risk_coverage_curves.csv")

    mel_miss_df.to_csv(OUT_DIR / "r6_melanoma_miss_rate.csv", index=False)
    print(f"  {OUT_DIR}/r6_melanoma_miss_rate.csv")

    # Plot
    fig_path = FIG_DIR / "fig_r6_selective_compare"
    plot_risk_coverage(curves_df, methods, fig_path)

    # JSON summary
    summary_json = {
        "dataset": "ITB-LQ (n=300)",
        "methods_run": [m["name"] for m in methods],
        "methods_skipped": [],
        "honesty_check": honesty,
        "metrics": {},
    }
    for _, row in summary_df.iterrows():
        summary_json["metrics"][row["key"]] = {
            "method": row["method"],
            "rc_auc": round(float(row["rc_auc"]), 4) if not np.isnan(row["rc_auc"]) else None,
            "risk_at_full_coverage": round(float(row["risk_at_full_coverage"]), 4)
                if not np.isnan(row["risk_at_full_coverage"]) else None,
            "auc_roc": round(float(row["auc_roc"]), 4) if not np.isnan(row["auc_roc"]) else None,
            "mel_miss_at_cov20": round(float(row["mel_miss_at_cov20"]), 4)
                if not np.isnan(row["mel_miss_at_cov20"]) else None,
            "mel_miss_at_cov50": round(float(row["mel_miss_at_cov50"]), 4)
                if not np.isnan(row["mel_miss_at_cov50"]) else None,
            "mel_miss_at_cov80": round(float(row["mel_miss_at_cov80"]), 4)
                if not np.isnan(row["mel_miss_at_cov80"]) else None,
            "note": row["note"],
        }

    selectivenet_available = any("selectivenet" in m["key"] for m in methods)
    if not selectivenet_available:
        summary_json["methods_skipped"].append(
            "SelectiveNet: checkpoints not found. "
            "Run: python project/train_selectivenet.py --coverage all (GPU ~15min), "
            "then re-run this script."
        )
    mcdropout_note = next(
        (m["note"] for m in methods if m["key"] == "mcdropout"), ""
    )
    if "TODO" in mcdropout_note:
        summary_json["methods_skipped"].append(
            "MC-Dropout exact UQ: per-sample T-pass variance not saved. "
            "Using confidence of mean prediction as proxy. "
            "TODO: re-run run_mcdropout_baseline with variance logging for exact method."
        )

    with open(OUT_DIR / "r6_summary.json", "w") as f:
        json.dump(summary_json, f, indent=2)
    print(f"  {OUT_DIR}/r6_summary.json")

    print("\n=== Done ===")
    print("  NOTE: SelectiveNet comparison requires training first.")
    print("  NOTE: Deep Ensemble uses 3-seed (s42/s123/s2024), ideally 5-seed.")
    print("  NOTE: MC-Dropout uses confidence proxy, not exact predictive variance.")
    if not selectivenet_available:
        print("\n  -> To add SelectiveNet:")
        print("     python project/train_selectivenet.py --coverage all  [~15min GPU]")
        print("     python project/run_r6_selective_compare.py  [re-run for full comparison]")


if __name__ == "__main__":
    main()
