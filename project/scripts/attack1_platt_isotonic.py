"""
Attack 1 rebuttal: quality-stratified Platt scaling + isotonic regression
vs QCTS.

Protocol:
  - Calibration set: ITB-Edge (n=660, quality boundary band)
  - Test set: ITB-LQ (n=300) + ITB-HQ (n=360)
  - Same evaluation metrics as Table 2: QCDI, rho, ECE-LQ, ECE-HQ
  - Compare: Std TS | QCTS | Platt-Quality | Isotonic-Quality

Outputs:
  results/attack1_baseline_comparison.csv
  results/attack1_baseline_comparison.json
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import spearmanr

ROOT = Path("D:/YJ-Agent")
sys.path.insert(0, str(ROOT / "project"))
RESULTS = ROOT / "project/results"


# ── Helpers ───────────────────────────────────────────────────────────────────

def binary_entropy(prob_pos):
    p = np.clip(prob_pos, 1e-9, 1 - 1e-9)
    return -(p * np.log(p) + (1 - p) * np.log(1 - p))


def ece(prob, tgt, n_bins=15):
    bins = np.linspace(0, 1, n_bins + 1)
    e, n = 0.0, len(tgt)
    for lo, hi in zip(bins[:-1], bins[1:]):
        m = (prob >= lo) & (prob < hi)
        if m.sum() < 3:
            continue
        e += (m.sum() / n) * abs(tgt[m].mean() - prob[m].mean())
    return float(e)


def qcdi_and_rho(prob, tgt, qbar):
    lq = qbar < 0.45
    hq = qbar > 0.50
    e_lq = ece(prob[lq], tgt[lq]) if lq.sum() >= 10 else float("nan")
    e_hq = ece(prob[hq], tgt[hq]) if hq.sum() >= 10 else float("nan")
    qcdi = e_lq - e_hq if not (np.isnan(e_lq) or np.isnan(e_hq)) else float("nan")
    entropy = binary_entropy(prob)
    rho, rho_p = spearmanr(entropy, qbar)
    return {
        "ece_lq": e_lq, "ece_hq": e_hq, "qcdi": qcdi,
        "rho": float(rho), "rho_p": float(rho_p),
        "n_lq": int(lq.sum()), "n_hq": int(hq.sum()),
    }


# ── Load data ─────────────────────────────────────────────────────────────────

print("Loading predictions...")
preds = pd.read_csv(RESULTS / "itb_predictions.csv")
qcts_preds = pd.read_csv(RESULTS / "qcts_itb_predictions.csv")

d = preds[preds["baseline"] == "D"].reset_index(drop=True)
ts = preds[preds["baseline"] == "TS"].reset_index(drop=True)

# QCTS predictions from qcts_itb_predictions.csv
dq = qcts_preds[qcts_preds["baseline"] == "D+QCTS"].reset_index(drop=True)

# Splits
edge = d[d["subset"] == "ITB-Edge"].reset_index(drop=True)
lq   = d[d["subset"] == "ITB-LQ"].reset_index(drop=True)
hq   = d[d["subset"] == "ITB-HQ"].reset_index(drop=True)
test = pd.concat([lq, hq], ignore_index=True)

print(f"  Edge n={len(edge)}, LQ n={len(lq)}, HQ n={len(hq)}, Test n={len(test)}")

# Raw logits from prob_pos
def prob_to_logit(p):
    p = np.clip(p, 1e-7, 1 - 1e-7)
    return np.log(p / (1 - p))

edge_logit = prob_to_logit(edge["prob_pos"].values)
edge_qbar  = edge["qbar"].values
edge_tgt   = edge["target"].values.astype(float)

test_logit = prob_to_logit(d[d["subset"].isin(["ITB-LQ","ITB-HQ"])]["prob_pos"].values)
test_qbar  = d[d["subset"].isin(["ITB-LQ","ITB-HQ"])]["qbar"].values
test_tgt   = d[d["subset"].isin(["ITB-LQ","ITB-HQ"])]["target"].values.astype(float)
test_subset = d[d["subset"].isin(["ITB-LQ","ITB-HQ"])]["subset"].values


# ── Method 1: Standard TS (scalar T) ─────────────────────────────────────────

def ts_nll(log_T, logit, tgt):
    T = np.exp(log_T[0])
    p = 1 / (1 + np.exp(-logit / T))
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return -np.mean(tgt * np.log(p) + (1 - tgt) * np.log(1 - p))

res_ts = minimize(ts_nll, [0.0], args=(edge_logit, edge_tgt), method="L-BFGS-B")
T_ts = float(np.exp(res_ts.x[0]))
print(f"\nStd TS: T={T_ts:.4f}")

prob_ts_test = 1 / (1 + np.exp(-test_logit / T_ts))
metrics_ts = qcdi_and_rho(prob_ts_test, test_tgt, test_qbar)
print(f"  QCDI={metrics_ts['qcdi']:.4f}  rho={metrics_ts['rho']:.4f}")


# ── Method 2: QCTS (re-fit on Edge, params: T0, alpha) ───────────────────────

def qcts_nll(params, logit, qbar, tgt):
    T0, alpha = params
    T = T0 + np.log(1 + np.exp(alpha * (1 - qbar)))
    p = 1 / (1 + np.exp(-logit / T))
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return -np.mean(tgt * np.log(p) + (1 - tgt) * np.log(1 - p))

best_nll, best_params = np.inf, [1.0, 0.5]
for t0_init in [0.5, 1.0, 1.5]:
    for alpha_init in [0.3, 0.6, 1.0]:
        res = minimize(
            qcts_nll, [t0_init, alpha_init],
            args=(edge_logit, edge_qbar, edge_tgt),
            method="L-BFGS-B",
            bounds=[(0.01, 5.0), (-1.0, 3.0)],
        )
        if res.fun < best_nll:
            best_nll = res.fun
            best_params = res.x.tolist()

T0_qcts, alpha_qcts = best_params
print(f"\nQCTS (refitted on Edge): T0={T0_qcts:.4f}  alpha={alpha_qcts:.4f}")

T_test = T0_qcts + np.log(1 + np.exp(alpha_qcts * (1 - test_qbar)))
prob_qcts_edge = 1 / (1 + np.exp(-test_logit / T_test))
metrics_qcts_edge = qcdi_and_rho(prob_qcts_edge, test_tgt, test_qbar)
print(f"  QCDI={metrics_qcts_edge['qcdi']:.4f}  rho={metrics_qcts_edge['rho']:.4f}")

# Also use the original QCTS (from qcts_itb_predictions.csv)
qcts_test = dq[dq["subset"].isin(["ITB-LQ","ITB-HQ"])].reset_index(drop=True)
assert len(qcts_test) == len(test), f"QCTS test length mismatch: {len(qcts_test)} vs {len(test)}"
metrics_qcts_orig = qcdi_and_rho(qcts_test["prob_pos"].values, test_tgt, test_qbar)
print(f"\nQCTS (original val-fit): QCDI={metrics_qcts_orig['qcdi']:.4f}  rho={metrics_qcts_orig['rho']:.4f}")


# ── Method 3: Quality-stratified Platt scaling ────────────────────────────────
# Fit a 2-parameter sigmoid (a, b) within each of 3 quality strata
# Strata: LQ (q<0.45), Edge (0.45<=q<=0.50), HQ (q>0.50)

def platt_nll(ab, logit, tgt):
    a, b = ab
    p = 1 / (1 + np.exp(-(a * logit + b)))
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return -np.mean(tgt * np.log(p) + (1 - tgt) * np.log(1 - p))

def fit_platt(logit, tgt):
    res = minimize(platt_nll, [1.0, 0.0], args=(logit, tgt), method="L-BFGS-B")
    return res.x.tolist()

# Edge split into 3 strata for fitting
e_lq_mask  = edge_qbar < 0.45
e_mid_mask = (edge_qbar >= 0.45) & (edge_qbar <= 0.50)
e_hq_mask  = edge_qbar > 0.50

platt_params = {}
for name, mask in [("lq", e_lq_mask), ("mid", e_mid_mask), ("hq", e_hq_mask)]:
    n = mask.sum()
    if n < 10:
        platt_params[name] = [1.0, 0.0]  # fallback: identity
        print(f"  Platt {name}: n={n} too small, using identity")
    else:
        platt_params[name] = fit_platt(edge_logit[mask], edge_tgt[mask])
        print(f"  Platt {name}: n={n}  a={platt_params[name][0]:.4f}  b={platt_params[name][1]:.4f}")

# Apply to test set
t_lq_mask  = test_qbar < 0.45
t_mid_mask = (test_qbar >= 0.45) & (test_qbar <= 0.50)
t_hq_mask  = test_qbar > 0.50

prob_platt = np.zeros(len(test_logit))
for name, mask in [("lq", t_lq_mask), ("mid", t_mid_mask), ("hq", t_hq_mask)]:
    a, b = platt_params[name]
    prob_platt[mask] = 1 / (1 + np.exp(-(a * test_logit[mask] + b)))

metrics_platt = qcdi_and_rho(prob_platt, test_tgt, test_qbar)
print(f"\nQuality-stratified Platt: QCDI={metrics_platt['qcdi']:.4f}  rho={metrics_platt['rho']:.4f}")


# ── Method 4: Quality-binned isotonic regression ──────────────────────────────
# 10 equal-frequency q̄ bins on Edge; within each bin, isotonic regression

from sklearn.isotonic import IsotonicRegression

N_BINS = 10
# Use q̄ quantiles from edge set
quantiles = np.percentile(edge_qbar, np.linspace(0, 100, N_BINS + 1))
quantiles[0] = 0.0
quantiles[-1] = 1.0

iso_models = []
bin_means = []

for i in range(N_BINS):
    lo, hi = quantiles[i], quantiles[i + 1]
    mask = (edge_qbar >= lo) & (edge_qbar <= hi)
    n = mask.sum()
    if n < 5:
        iso_models.append(None)
        bin_means.append((lo + hi) / 2)
        continue
    # Probabilities as "uncalibrated" input
    p_bin = 1 / (1 + np.exp(-edge_logit[mask]))
    t_bin = edge_tgt[mask]
    ir = IsotonicRegression(out_of_bounds="clip")
    ir.fit(p_bin, t_bin)
    iso_models.append(ir)
    bin_means.append((lo + hi) / 2)

# Apply to test set: find nearest q̄ bin and apply its isotonic model
def apply_isotonic(logit, qbar, models, quantiles, n_bins):
    p_raw = 1 / (1 + np.exp(-logit))
    prob_cal = np.zeros_like(p_raw)
    for i in range(n_bins):
        lo, hi = quantiles[i], quantiles[i + 1]
        mask = (qbar >= lo) & (qbar <= hi)
        if mask.sum() == 0:
            continue
        if models[i] is not None:
            prob_cal[mask] = models[i].predict(p_raw[mask])
        else:
            # fallback: use nearest non-None model
            prob_cal[mask] = p_raw[mask]
    return prob_cal

try:
    prob_isotonic = apply_isotonic(test_logit, test_qbar, iso_models, quantiles, N_BINS)
    metrics_isotonic = qcdi_and_rho(prob_isotonic, test_tgt, test_qbar)
    print(f"\nQuality-binned isotonic: QCDI={metrics_isotonic['qcdi']:.4f}  rho={metrics_isotonic['rho']:.4f}")
except ImportError:
    print("\nsklearn not available for isotonic regression")
    metrics_isotonic = {"qcdi": float("nan"), "rho": float("nan")}


# ── Summary table ─────────────────────────────────────────────────────────────

print("\n" + "="*70)
print(f"{'Method':35s} | {'ECE-LQ':>8} | {'ECE-HQ':>8} | {'QCDI':>8} | {'rho':>8}")
print("-"*70)

results = [
    ("Std TS (Edge-fit)",          metrics_ts),
    ("QCTS (val-fit, original)",   metrics_qcts_orig),
    ("QCTS (Edge-fit)",            metrics_qcts_edge),
    ("Platt-Quality (Edge-fit)",   metrics_platt),
    ("Isotonic-Quality (Edge-fit)",metrics_isotonic),
]

for name, m in results:
    print(
        f"  {name:33s} | {m.get('ece_lq', float('nan')):8.4f} | "
        f"{m.get('ece_hq', float('nan')):8.4f} | "
        f"{m.get('qcdi', float('nan')):8.4f} | "
        f"{m.get('rho', float('nan')):8.4f}"
    )

# ── Save ─────────────────────────────────────────────────────────────────────

rows = []
for name, m in results:
    rows.append({"method": name, **m})

df = pd.DataFrame(rows)
out_csv = RESULTS / "attack1_baseline_comparison.csv"
df.to_csv(out_csv, index=False)
print(f"\nSaved CSV  -> {out_csv}")

out_json = RESULTS / "attack1_baseline_comparison.json"
with open(out_json, "w") as f:
    json.dump({name: m for name, m in results}, f, indent=2)
print(f"Saved JSON -> {out_json}")
print("\nDone.")
