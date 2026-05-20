"""
Attack 2 rebuttal: τ threshold sensitivity for TS reversal claim.

Shows that rho sign-flip (raw rho < 0, TS rho > 0 on full pool OR changes in
LQ sub-pool) holds across τ_LQ ∈ {0.40, 0.43, 0.45, 0.48, 0.50}.

Also tests with Laplacian variance substituted as qbar proxy.

Outputs:
  results/threshold_sensitivity.csv   -- per-τ rho table
  results/threshold_sensitivity.json  -- full results
"""

import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr, bootstrap

ROOT = Path("D:/YJ-Agent")
sys.path.insert(0, str(ROOT / "project"))

RESULTS = ROOT / "project/results"


def binary_entropy(prob_pos):
    p = np.clip(prob_pos, 1e-9, 1 - 1e-9)
    return -(p * np.log(p) + (1 - p) * np.log(1 - p))


def rho_with_ci(entropy, qbar, n_boot=2000, seed=42):
    """Spearman rho + 95% bootstrap CI (manual percentile bootstrap)."""
    rho, p = spearmanr(entropy, qbar)
    if len(entropy) < 10:
        return float(rho), float(p), float("nan"), float("nan")

    rng = np.random.default_rng(seed)
    n = len(entropy)
    boot_rhos = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.integers(0, n, size=n)
        boot_rhos[i] = spearmanr(entropy[idx], qbar[idx]).statistic

    ci_lo = float(np.percentile(boot_rhos, 2.5))
    ci_hi = float(np.percentile(boot_rhos, 97.5))
    return float(rho), float(p), ci_lo, ci_hi


# ── Load predictions ──────────────────────────────────────────────────────────

print("Loading predictions …")
preds = pd.read_csv(RESULTS / "itb_predictions.csv")

d_preds  = preds[preds["baseline"] == "D"].reset_index(drop=True)   # Std VIB raw
ts_preds = preds[preds["baseline"] == "TS"].reset_index(drop=True)  # Std VIB + TS

assert len(d_preds) == len(ts_preds) == 2820
assert (d_preds["qbar"].values == ts_preds["qbar"].values).all(), \
    "qbar mismatch between D and TS rows"

qbar_iqa = d_preds["qbar"].values         # IQA-derived quality scores (same for both)
entropy_d  = binary_entropy(d_preds["prob_pos"].values)
entropy_ts = binary_entropy(ts_preds["prob_pos"].values)

# ── Load Laplacian variance as alternative qbar ─────────────────────────────────

print("Loading Laplacian variance …")
with open(RESULTS / "quality_scalar_cache.pkl", "rb") as f:
    cache = pickle.load(f)

lap_itb_raw = np.array(cache["lap_itb"], dtype=float)  # in itb_subsets.csv order
assert len(lap_itb_raw) == 2820, f"lap_itb length mismatch: {len(lap_itb_raw)}"

# Align lap_itb to d_preds row order using (subset, target, round(qbar,5)) key.
itb_sub = pd.read_csv(RESULTS / "itb_subsets.csv")
assert len(itb_sub) == 2820

key_to_lap = {}
for i, row in itb_sub.iterrows():
    key = (row["subset"], int(row["target"]), round(float(row["qbar"]), 5))
    key_to_lap[key] = float(lap_itb_raw[i])

lap_aligned = np.array([
    key_to_lap.get(
        (row["subset"], int(row["target"]), round(float(row["qbar"]), 5)),
        np.nan
    )
    for _, row in d_preds.iterrows()
])

nan_count = np.isnan(lap_aligned).sum()
if nan_count > 0:
    print(f"  WARNING: {nan_count} unmatched Laplacian entries — filling with median")
    lap_aligned[np.isnan(lap_aligned)] = np.nanmedian(lap_aligned)

# Normalise Laplacian to [0,1] (higher = sharper = better quality, same direction as IQA qbar)
lap_min, lap_max = lap_aligned.min(), lap_aligned.max()
qbar_lap = (lap_aligned - lap_min) / (lap_max - lap_min + 1e-12)

print(f"  Laplacian normalised range: [{qbar_lap.min():.3f}, {qbar_lap.max():.3f}]")
print(f"  Spearman(IQA qbar, Lap qbar) = {spearmanr(qbar_iqa, qbar_lap).statistic:.3f}")

# ── Analysis ─────────────────────────────────────────────────────────────────

TAU_VALUES = [0.40, 0.43, 0.45, 0.48, 0.50]
results = {}

for qbar_name, qbar in [("IQA_qbar", qbar_iqa), ("Laplacian_qbar", qbar_lap)]:
    print(f"\n{'='*70}")
    print(f"  qbar proxy: {qbar_name}")
    print(f"{'='*70}")
    results[qbar_name] = {}

    # 1. Full pool
    rho_d,  p_d,  ci_lo_d,  ci_hi_d  = rho_with_ci(entropy_d,  qbar)
    rho_ts, p_ts, ci_lo_ts, ci_hi_ts = rho_with_ci(entropy_ts, qbar)
    sign_flip_full = (rho_d < 0) and (rho_ts > 0)
    print(f"\n  Full pool (n={len(qbar)})")
    print(f"    Raw rho = {rho_d:.4f}  [{ci_lo_d:.3f}, {ci_hi_d:.3f}]  p={p_d:.2e}")
    print(f"    TS  rho = {rho_ts:.4f}  [{ci_lo_ts:.3f}, {ci_hi_ts:.3f}]  p={p_ts:.2e}")
    print(f"    Sign flip (raw<0, TS>0): {sign_flip_full}")

    results[qbar_name]["full_pool"] = {
        "n": len(qbar),
        "raw_rho": rho_d, "raw_p": p_d, "raw_ci": [ci_lo_d, ci_hi_d],
        "ts_rho": rho_ts, "ts_p": p_ts, "ts_ci": [ci_lo_ts, ci_hi_ts],
        "sign_flip": sign_flip_full,
    }

    # 2. τ sweep on LQ sub-pool (qbar < τ)
    print(f"\n  τ sweep (qbar < τ sub-pool):")
    print(f"  {'τ':>5}  {'n':>5}  {'raw rho':>8}  {'TS rho':>8}  {'Δrho':>8}  sign-flip")
    results[qbar_name]["tau_sweep"] = {}

    for tau in TAU_VALUES:
        mask = qbar < tau
        n_tau = mask.sum()
        if n_tau < 20:
            print(f"  {tau:.2f}  {n_tau:>5}  (too few samples, skipped)")
            continue

        e_d_sub  = entropy_d[mask]
        e_ts_sub = entropy_ts[mask]
        q_sub    = qbar[mask]

        r_d,  p_d_,  cl_d,  ch_d  = rho_with_ci(e_d_sub,  q_sub)
        r_ts, p_ts_, cl_ts, ch_ts = rho_with_ci(e_ts_sub, q_sub)
        sign_flip = (r_d < 0) and (r_ts > 0)
        delta_rho = r_ts - r_d

        print(
            f"  {tau:.2f}  {n_tau:>5}  {r_d:>+8.4f}  {r_ts:>+8.4f}"
            f"  {delta_rho:>+8.4f}  {'YES [FLIP]' if sign_flip else 'no'}"
        )
        results[qbar_name]["tau_sweep"][str(tau)] = {
            "n": int(n_tau),
            "raw_rho": r_d, "raw_p": p_d_, "raw_ci": [cl_d, ch_d],
            "ts_rho": r_ts, "ts_p": p_ts_, "ts_ci": [cl_ts, ch_ts],
            "sign_flip": sign_flip,
            "delta_rho": delta_rho,
        }

    # 3. HQ sub-pool (qbar > 0.50)
    mask_hq = qbar > 0.50
    n_hq = mask_hq.sum()
    r_d_hq, p_d_hq, _, _ = rho_with_ci(entropy_d[mask_hq],  qbar[mask_hq])
    r_ts_hq, p_ts_hq, _, _ = rho_with_ci(entropy_ts[mask_hq], qbar[mask_hq])
    print(f"\n  HQ sub-pool (qbar > 0.50, n={n_hq})")
    print(f"    Raw rho = {r_d_hq:.4f}  p={p_d_hq:.2e}")
    print(f"    TS  rho = {r_ts_hq:.4f}  p={p_ts_hq:.2e}")
    results[qbar_name]["hq_pool"] = {
        "n": int(n_hq),
        "raw_rho": r_d_hq, "raw_p": p_d_hq,
        "ts_rho": r_ts_hq, "ts_p": p_ts_hq,
    }

# ── Save ─────────────────────────────────────────────────────────────────────

out_json = RESULTS / "threshold_sensitivity.json"
with open(out_json, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
print(f"\nSaved → {out_json}")

# Flat CSV for paper
rows = []
for qbar_name, qr in results.items():
    # full pool row
    fp = qr["full_pool"]
    rows.append({
        "qbar_proxy": qbar_name, "tau": "full",
        "n": fp["n"],
        "raw_rho": fp["raw_rho"], "raw_p": fp["raw_p"],
        "ts_rho": fp["ts_rho"], "ts_p": fp["ts_p"],
        "delta_rho": fp["ts_rho"] - fp["raw_rho"],
        "sign_flip": fp["sign_flip"],
    })
    for tau_str, tr in qr["tau_sweep"].items():
        rows.append({
            "qbar_proxy": qbar_name, "tau": tau_str,
            "n": tr["n"],
            "raw_rho": tr["raw_rho"], "raw_p": tr["raw_p"],
            "ts_rho": tr["ts_rho"], "ts_p": tr["ts_p"],
            "delta_rho": tr["delta_rho"],
            "sign_flip": tr["sign_flip"],
        })

df = pd.DataFrame(rows)
out_csv = RESULTS / "threshold_sensitivity.csv"
df.to_csv(out_csv, index=False)
print(f"Saved → {out_csv}")

print("\n✅ Done.")
