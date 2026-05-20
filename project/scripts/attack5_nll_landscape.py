"""
Attack 5 rebuttal: alpha NLL landscape flatness analysis.

Shows that the NLL landscape is flat for alpha in [0.3, 1.0], explaining
why 3 seeds produce alpha in {0.34, 0.96, 0.37}.

Protocol:
  - Fix T0 at the best-fit value (1.17)
  - Vary alpha from -0.1 to 1.3 in steps of 0.05
  - Compute NLL on ITB-Edge (proxy for the val set used in QCTS fitting)
  - Also compute 2D landscape: alpha x T0 grid

Outputs:
  results/attack5_nll_landscape.csv   -- alpha sweep table
  results/attack5_nll_landscape.json  -- full results with 2D grid
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


def binary_entropy(prob_pos):
    p = np.clip(prob_pos, 1e-9, 1 - 1e-9)
    return -(p * np.log(p) + (1 - p) * np.log(1 - p))


def qcts_temperature(T0, alpha, qbar):
    return T0 + np.log(1 + np.exp(alpha * (1 - qbar)))


def nll_qcts(T0, alpha, logit, qbar, tgt):
    T = qcts_temperature(T0, alpha, qbar)
    p = 1 / (1 + np.exp(-logit / T))
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return float(-np.mean(tgt * np.log(p) + (1 - tgt) * np.log(1 - p)))


# ── Load data ─────────────────────────────────────────────────────────────────

print("Loading data...")
preds = pd.read_csv(RESULTS / "itb_predictions.csv")
d = preds[preds["baseline"] == "D"].reset_index(drop=True)

# Use ITB-Edge as proxy calibration/validation set
edge = d[d["subset"] == "ITB-Edge"].reset_index(drop=True)
print(f"  ITB-Edge n={len(edge)}")

def prob_to_logit(p):
    p = np.clip(p, 1e-7, 1 - 1e-7)
    return np.log(p / (1 - p))

logit_edge = prob_to_logit(edge["prob_pos"].values)
qbar_edge  = edge["qbar"].values
tgt_edge   = edge["target"].values.astype(float)

# Use all ITB as secondary set
logit_all = prob_to_logit(d["prob_pos"].values)
qbar_all  = d["qbar"].values
tgt_all   = d["target"].values.astype(float)

# Load QCTS original params
import json as _json
with open(RESULTS / "qcts_params.json") as f:
    params = _json.load(f)
T0_best = params["T0"]
alpha_best = params["alpha"]
print(f"  Original QCTS: T0={T0_best:.4f}  alpha={alpha_best:.4f}")

# The 3-seed alphas from the paper
SEED_ALPHAS = [0.34, 0.96, 0.37]
SEED_T0S    = [1.17, 1.17, 1.17]  # approximate


# ── 1D alpha sweep (T0 fixed at best) ─────────────────────────────────────────

print("\n--- 1D alpha sweep (T0 fixed) ---")
alpha_range = np.arange(-0.1, 1.35, 0.05)

rows_edge = []
rows_all  = []

for alpha in alpha_range:
    nll_e = nll_qcts(T0_best, alpha, logit_edge, qbar_edge, tgt_edge)
    nll_a = nll_qcts(T0_best, alpha, logit_all,  qbar_all,  tgt_all)
    rows_edge.append({"alpha": round(float(alpha), 4), "nll": nll_e, "dataset": "edge"})
    rows_all.append( {"alpha": round(float(alpha), 4), "nll": nll_a, "dataset": "full_itb"})

df_edge = pd.DataFrame(rows_edge)
df_all  = pd.DataFrame(rows_all)

nll_min_e = df_edge["nll"].min()
nll_min_a = df_all["nll"].min()

# Print landscape
print(f"\n  alpha    NLL(Edge)  delta   NLL(All ITB) delta")
print(f"  -------  ---------  ------  ------------ ------")
for _, re, ra in zip(range(len(alpha_range)), rows_edge, rows_all):
    flat_e = abs(re["nll"] - nll_min_e) < 0.003
    flat_a = abs(ra["nll"] - nll_min_a) < 0.003
    marker = " <-- flat" if flat_e else ""
    print(
        f"  {re['alpha']:6.3f}   {re['nll']:.6f}  {re['nll']-nll_min_e:+.5f}  "
        f"{ra['nll']:.6f}  {ra['nll']-nll_min_a:+.5f}{marker}"
    )

# Range where NLL < min + 0.002
flat_range_e = df_edge[abs(df_edge["nll"] - nll_min_e) < 0.002]["alpha"]
flat_range_a = df_all[ abs(df_all["nll"]  - nll_min_a) < 0.002]["alpha"]

print(f"\n  Flat region (NLL within 0.002 of min):")
print(f"    Edge:     alpha in [{flat_range_e.min():.2f}, {flat_range_e.max():.2f}]")
print(f"    Full ITB: alpha in [{flat_range_a.min():.2f}, {flat_range_a.max():.2f}]")

# Check seed alphas
print(f"\n  NLL at seed alphas (T0={T0_best:.4f}):")
for a, t0 in zip(SEED_ALPHAS, SEED_T0S):
    nll_e = nll_qcts(t0, a, logit_edge, qbar_edge, tgt_edge)
    nll_a = nll_qcts(t0, a, logit_all,  qbar_all,  tgt_all)
    print(f"    alpha={a:.2f}: NLL(Edge)={nll_e:.6f} (delta={nll_e-nll_min_e:+.5f})  "
          f"NLL(All)={nll_a:.6f} (delta={nll_a-nll_min_a:+.5f})")


# ── 2D landscape: alpha x T0 ─────────────────────────────────────────────────

print("\n--- 2D grid (alpha x T0) on Edge ---")
t0_range    = np.arange(0.5, 2.6, 0.25)
alpha_range2 = np.arange(-0.1, 1.35, 0.15)

grid = {}
for T0 in t0_range:
    for alpha in alpha_range2:
        nll_e = nll_qcts(float(T0), float(alpha), logit_edge, qbar_edge, tgt_edge)
        grid[f"{T0:.2f}_{alpha:.2f}"] = float(nll_e)

nll_min_2d = min(grid.values())
print(f"  2D min NLL = {nll_min_2d:.6f}")
print(f"  Flat region (delta < 0.002): {sum(1 for v in grid.values() if v - nll_min_2d < 0.002)} cells / {len(grid)}")


# ── Save ─────────────────────────────────────────────────────────────────────

df_combined = pd.concat([df_edge, df_all], ignore_index=True)
out_csv = RESULTS / "attack5_nll_landscape.csv"
df_combined.to_csv(out_csv, index=False)
print(f"\nSaved CSV  -> {out_csv}")

results = {
    "best_params": {"T0": T0_best, "alpha": alpha_best},
    "seed_alphas": SEED_ALPHAS,
    "flat_region_edge": {
        "lo": float(flat_range_e.min()),
        "hi": float(flat_range_e.max()),
        "threshold": 0.002,
    },
    "flat_region_full_itb": {
        "lo": float(flat_range_a.min()),
        "hi": float(flat_range_a.max()),
        "threshold": 0.002,
    },
    "nll_at_seed_alphas_edge": {
        str(a): nll_qcts(T0_best, a, logit_edge, qbar_edge, tgt_edge)
        for a in SEED_ALPHAS
    },
    "nll_min_edge": float(nll_min_e),
    "nll_min_full_itb": float(nll_min_a),
    "1d_alpha_sweep_edge": {str(r["alpha"]): r["nll"] for r in rows_edge},
    "2d_grid_edge": grid,
}

out_json = RESULTS / "attack5_nll_landscape.json"
with open(out_json, "w") as f:
    json.dump(results, f, indent=2)
print(f"Saved JSON -> {out_json}")
print("\nDone.")
