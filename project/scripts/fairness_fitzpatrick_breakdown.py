"""
Fitzpatrick skin-type fairness breakdown for BMVC paper.

Computes per-skin-type (I-VI) and grouped (I-II / III-IV / V-VI) ECE and QCDI for:
  - Std VIB (baseline D)
  - Std VIB + QCTS (baseline D+QCTS)
  - MC Dropout (baseline I)  [for paper cross-check: known QCDI 0.157 I-II, 0.182 V-VI]
  - Focal+LS (baseline H)    [shown in paper figure (c)]

on ITB-Diverse subset (n=1500, FitzPatrick17k images).

QCDI within group = ECE(low-qbar half) - ECE(high-qbar half), using per-group median as cutoff.
This matches the definition in gen_bmvc_figures.py (group_qcdi function).

Also computes rho (Spearman correlation) between entropy and qbar per skin type.

Outputs:
  project/results/fairness_fitzpatrick_breakdown.json
  project/results/fairness_fitzpatrick_breakdown.csv
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path("D:/YJ-Agent")
sys.path.insert(0, str(ROOT / "project"))

# ── ECE function matching gen_bmvc_figures.py (15 bins, same as figure) ──────

def _ece_simple(prob, tgt, n_bins=15):
    """ECE with 15 bins, matching gen_bmvc_figures.py _ece_simple."""
    bins = np.linspace(0, 1, n_bins + 1)
    ece, n = 0.0, len(tgt)
    for lo, hi in zip(bins[:-1], bins[1:]):
        m = (prob >= lo) & (prob < hi)
        if m.sum() < 3:
            continue
        ece += (m.sum() / n) * abs(tgt[m].mean() - prob[m].mean())
    return float(ece)


def compute_binary_ece_10(prob_pos, targets, n_bins=10):
    """Classwise ECE with 10 bins (matching benchmark/metrics.py)."""
    bins = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    n = len(targets)
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (prob_pos >= lo) & (prob_pos < hi)
        if mask.sum() < 3:
            continue
        frac_pos = targets[mask].mean()
        mean_prob = prob_pos[mask].mean()
        ece += (mask.sum() / n) * abs(frac_pos - mean_prob)
    return float(ece)


# ── Load data ──────────────────────────────────────────────────────────────────

# ITB-Diverse metadata (subset rows)
subsets = pd.read_csv(ROOT / "project/results/itb_subsets.csv")
diverse_meta = subsets[subsets["subset"] == "ITB-Diverse"].reset_index(drop=True)

# FitzPatrick17k metadata → get fitzpatrick_scale via md5hash = isic_id
fp17k = pd.read_csv(ROOT / "data/raw/fitzpatrick17k/fitzpatrick17k.csv")[
    ["md5hash", "fitzpatrick_scale", "label"]
].rename(columns={"md5hash": "isic_id"})

diverse_meta = diverse_meta.merge(fp17k, on="isic_id", how="left")
print(f"ITB-Diverse with Fitzpatrick scale: {len(diverse_meta)} rows")
print(f"Unmapped (NaN fitzpatrick_scale): {diverse_meta['fitzpatrick_scale'].isna().sum()}")
print(f"fitzpatrick_scale dist:\n{diverse_meta['fitzpatrick_scale'].value_counts().sort_index()}\n")

# ── Load predictions ───────────────────────────────────────────────────────────

preds_all = pd.read_csv(ROOT / "project/results/itb_predictions.csv")
qcts_preds = pd.read_csv(ROOT / "project/results/qcts_itb_predictions.csv")

def get_pred(baseline_code, preds_df=preds_all):
    df = preds_df[(preds_df["baseline"] == baseline_code) & (preds_df["subset"] == "ITB-Diverse")].reset_index(drop=True)
    assert len(df) == 1500, f"Expected 1500 rows for {baseline_code}, got {len(df)}"
    assert (df["target"].values == diverse_meta["target"].values).all(), f"Target mismatch for {baseline_code}"
    return df["prob_pos"].values

prob_std_vib    = get_pred("D")
prob_mc_dropout = get_pred("I")
prob_focal_ls   = get_pred("H")
prob_qcts       = get_pred("D+QCTS", qcts_preds)

targets_all = diverse_meta["target"].values.astype(float)
qbar_all    = diverse_meta["qbar"].values
fitz_all    = diverse_meta["fitzpatrick_scale"].values

print(f"Predictions loaded. n=1500 each.")
print(f"qbar range: [{qbar_all.min():.3f}, {qbar_all.max():.3f}], mean={qbar_all.mean():.3f}\n")

# ── Helper ─────────────────────────────────────────────────────────────────────

def compute_group_stats(prob_pos, targets, qbar, label, min_n=30, min_half=10):
    """Compute ECE, QCDI (median split within group), and Spearman rho."""
    n = len(targets)
    pos = int(targets.sum())
    neg = n - pos

    # Overall ECE
    if pos > 0 and neg > 0 and n >= 5:
        ece_overall_10  = compute_binary_ece_10(prob_pos, targets)
        ece_overall_15  = _ece_simple(prob_pos, targets)
    else:
        ece_overall_10 = ece_overall_15 = float("nan")

    # LQ / HQ split using per-group median (matching gen_bmvc_figures.py)
    if n < min_n:
        return {
            "label": label, "n": n, "n_pos": pos,
            "ece_10bins": ece_overall_10, "ece_15bins": ece_overall_15,
            "ece_lq_10": float("nan"), "ece_hq_10": float("nan"), "qcdi_10": float("nan"),
            "ece_lq_15": float("nan"), "ece_hq_15": float("nan"), "qcdi_15": float("nan"),
            "qbar_mean": float(np.mean(qbar)), "qbar_median": float(np.median(qbar)),
            "entropy_vs_qbar_rho": float("nan"), "entropy_vs_qbar_rho_p": float("nan"),
            "note": f"n<{min_n} — QCDI unreliable",
        }

    cut = np.median(qbar)
    lq_mask = qbar < cut
    hq_mask = qbar >= cut

    def safe_ece_10(mask):
        pp, tg = prob_pos[mask], targets[mask]
        if len(tg) < min_half or tg.sum() == 0 or tg.sum() == len(tg):
            return float("nan")
        return compute_binary_ece_10(pp, tg)

    def safe_ece_15(mask):
        pp, tg = prob_pos[mask], targets[mask]
        if len(tg) < min_half or tg.sum() == 0 or tg.sum() == len(tg):
            return float("nan")
        return _ece_simple(pp, tg)

    ece_lq_10 = safe_ece_10(lq_mask)
    ece_hq_10 = safe_ece_10(hq_mask)
    ece_lq_15 = safe_ece_15(lq_mask)
    ece_hq_15 = safe_ece_15(hq_mask)

    qcdi_10 = (ece_lq_10 - ece_hq_10) if not (np.isnan(ece_lq_10) or np.isnan(ece_hq_10)) else float("nan")
    qcdi_15 = (ece_lq_15 - ece_hq_15) if not (np.isnan(ece_lq_15) or np.isnan(ece_hq_15)) else float("nan")

    # Spearman rho: entropy vs qbar
    probs2  = np.stack([1 - prob_pos, prob_pos], axis=1).clip(1e-9)
    entropy = -(probs2 * np.log(probs2)).sum(axis=1)
    rho, rho_p = spearmanr(entropy, qbar) if n >= 5 else (float("nan"), float("nan"))

    return {
        "label": label,
        "n": n,
        "n_pos": pos,
        "n_lq": int(lq_mask.sum()),
        "n_hq": int(hq_mask.sum()),
        "qbar_mean": float(np.mean(qbar)),
        "qbar_median": float(cut),
        "ece_10bins": ece_overall_10,
        "ece_15bins": ece_overall_15,
        "ece_lq_10": ece_lq_10,
        "ece_hq_10": ece_hq_10,
        "qcdi_10": qcdi_10,
        "ece_lq_15": ece_lq_15,
        "ece_hq_15": ece_hq_15,
        "qcdi_15": qcdi_15,
        "entropy_vs_qbar_rho": float(rho),
        "entropy_vs_qbar_rho_p": float(rho_p),
    }


# ── Per skin type + group analysis ────────────────────────────────────────────

# Groups: individual I-VI + paper's 3-group breakdown + I-II, V-VI, plus full pool
GROUPS = {
    "I":        (fitz_all == 1),
    "II":       (fitz_all == 2),
    "III":      (fitz_all == 3),
    "IV":       (fitz_all == 4),
    "V":        (fitz_all == 5),
    "VI":       (fitz_all == 6),
    "I-II":     (fitz_all == 1) | (fitz_all == 2),
    "III-IV":   (fitz_all == 3) | (fitz_all == 4),
    "V-VI":     (fitz_all == 5) | (fitz_all == 6),
    "All (known)": (fitz_all >= 1) & (fitz_all <= 6),
    "All (incl. unknown)": np.ones(len(fitz_all), dtype=bool),
}

BASELINES = {
    "Std VIB":       prob_std_vib,
    "Std VIB + QCTS": prob_qcts,
    "MC Dropout":    prob_mc_dropout,
    "Focal+LS":      prob_focal_ls,
}

results = {}
for bl_name, prob_pos in BASELINES.items():
    print(f"\n{'='*60}")
    print(f"  Baseline: {bl_name}")
    print(f"{'='*60}")
    results[bl_name] = {}
    for grp_name, mask in GROUPS.items():
        if mask.sum() == 0:
            continue
        stats = compute_group_stats(
            prob_pos[mask],
            targets_all[mask],
            qbar_all[mask],
            label=grp_name,
        )
        results[bl_name][grp_name] = stats
        note = stats.get("note", "")
        print(
            f"  Fitz {grp_name:14s}  n={stats['n']:4d}  "
            f"ECE(15)={stats['ece_15bins']:.4f}  "
            f"QCDI(15)={stats['qcdi_15']:.4f}  "
            f"rho={stats['entropy_vs_qbar_rho']:.3f}"
            + (f"  [{note}]" if note else "")
        )

# ── Summary: QCDI gap V-VI vs I-II ───────────────────────────────────────────

print("\n" + "=" * 65)
print("QCDI comparison across skin-type groups (15-bin ECE, median split):")
print(f"{'Baseline':22s} | {'I-II QCDI':>10} | {'III-IV QCDI':>11} | {'V-VI QCDI':>10} | {'V-VI - I-II':>12}")
print("-" * 75)
for bl_name in BASELINES:
    q_iii   = results[bl_name].get("I-II",   {}).get("qcdi_15", float("nan"))
    q_iiiiv = results[bl_name].get("III-IV", {}).get("qcdi_15", float("nan"))
    q_vvi   = results[bl_name].get("V-VI",   {}).get("qcdi_15", float("nan"))
    gap     = q_vvi - q_iii if not (np.isnan(q_vvi) or np.isnan(q_iii)) else float("nan")
    print(f"{bl_name:22s} | {q_iii:10.4f} | {q_iiiiv:11.4f} | {q_vvi:10.4f} | {gap:12.4f}")

print("\nECE overall (15-bin, all skin types known):")
for bl_name in BASELINES:
    ece = results[bl_name].get("All (known)", {}).get("ece_15bins", float("nan"))
    rho = results[bl_name].get("All (known)", {}).get("entropy_vs_qbar_rho", float("nan"))
    print(f"  {bl_name:22s}: ECE={ece:.4f}  rho(H,qbar)={rho:.3f}")

# ── Save results ──────────────────────────────────────────────────────────────

out_path = ROOT / "project/results/fairness_fitzpatrick_breakdown.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
print(f"\nSaved JSON → {out_path}")

# Flat CSV
rows_csv = []
for bl_name, groups in results.items():
    for grp_name, stats in groups.items():
        row = {"baseline": bl_name}
        row.update({k: v for k, v in stats.items() if k != "note"})
        if "note" in stats:
            row["note"] = stats["note"]
        rows_csv.append(row)

df_out = pd.DataFrame(rows_csv)
csv_path = ROOT / "project/results/fairness_fitzpatrick_breakdown.csv"
df_out.to_csv(csv_path, index=False)
print(f"Saved CSV  → {csv_path}")

# ── Paper-ready table ─────────────────────────────────────────────────────────

print()
print("=" * 90)
print("Paper-ready table: Per-Fitzpatrick ECE (15 bins) and QCDI (median split within group)")
print("Focus: Std VIB vs Std VIB + QCTS")
print("=" * 90)
hdr = (
    f"{'Skin Type':14s} | {'n':>5} | {'n_pos':>5} | "
    f"{'VIB ECE':>8} | {'VIB QCDI':>9} | "
    f"{'QCTS ECE':>9} | {'QCTS QCDI':>10} | "
    f"{'QCDI Δ':>8} | {'rho VIB':>8} | {'rho QCTS':>9}"
)
print(hdr)
print("-" * len(hdr))

TYPE_ORDER = ["I", "II", "III", "IV", "V", "VI", "I-II", "III-IV", "V-VI", "All (known)"]
for grp in TYPE_ORDER:
    s_vib  = results["Std VIB"].get(grp, {})
    s_qcts = results["Std VIB + QCTS"].get(grp, {})
    if not s_vib:
        continue
    ece_v  = s_vib.get("ece_15bins", float("nan"))
    qcdi_v = s_vib.get("qcdi_15", float("nan"))
    ece_q  = s_qcts.get("ece_15bins", float("nan"))
    qcdi_q = s_qcts.get("qcdi_15", float("nan"))
    delta  = (qcdi_q - qcdi_v) if not (np.isnan(qcdi_v) or np.isnan(qcdi_q)) else float("nan")
    rho_v  = s_vib.get("entropy_vs_qbar_rho", float("nan"))
    rho_q  = s_qcts.get("entropy_vs_qbar_rho", float("nan"))
    note   = s_vib.get("note", "")
    flag   = " (*)" if note else ""
    print(
        f"{grp+flag:14s} | {s_vib['n']:5d} | {s_vib['n_pos']:5d} | "
        f"{ece_v:8.4f} | {qcdi_v:9.4f} | "
        f"{ece_q:9.4f} | {qcdi_q:10.4f} | "
        f"{delta:8.4f} | {rho_v:8.3f} | {rho_q:9.3f}"
    )
print("(*) n < 30: QCDI unreliable due to small sample")

print()
print("MC Dropout cross-check (for paper §5.6 claim: QCDI 0.157 I-II, 0.182 V-VI):")
for grp in ["I-II", "V-VI"]:
    s = results["MC Dropout"].get(grp, {})
    print(
        f"  MC Dropout {grp}: n={s.get('n','?')}, "
        f"ECE_LQ(15)={s.get('ece_lq_15', float('nan')):.4f}, "
        f"ECE_HQ(15)={s.get('ece_hq_15', float('nan')):.4f}, "
        f"QCDI(15)={s.get('qcdi_15', float('nan')):.4f}"
    )
