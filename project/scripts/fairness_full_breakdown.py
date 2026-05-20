"""
Sub-population fairness analysis for BMVC quality-aware calibration paper.

Computes per-subgroup ECE, QCDI, and Spearman rho for:
  - Std VIB (baseline D)
  - Std VIB + QCTS (baseline D+QCTS)
  - MC Dropout (baseline I)

Stratifications available (all from Fitzpatrick17k metadata, n=1500 ITB-Diverse):
  1. Fitzpatrick skin type (I-VI) [already done separately]
  2. Lesion type — nine_partition_label (9 categories)
  3. Lesion type — three_partition_label (benign / malignant / non-neoplastic)
  4. Broad lesion category (malignant vs non-malignant)

NOT available in local data (blocked):
  - Sex / Age / Body location — ISIC 2020 Kaggle rich metadata was not
    downloaded (local copy stripped to isic_id/patient_id/target only).
    The Fitzpatrick17k dataset also contains no demographic metadata.

Outputs:
  project/results/fairness_full_breakdown.json
  project/results/fairness_full_breakdown.csv

QCDI definition: ECE(LQ half) - ECE(HQ half), per-group median split on qbar.
LQ: qbar < per-group median; HQ: qbar >= per-group median.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path("D:/YJ-Agent")
sys.path.insert(0, str(ROOT / "project"))

# ── ECE helpers ────────────────────────────────────────────────────────────────

def ece_15bins(prob, tgt):
    """15-bin ECE, matching gen_bmvc_figures.py _ece_simple."""
    bins = np.linspace(0, 1, 16)
    ece, n = 0.0, len(tgt)
    for lo, hi in zip(bins[:-1], bins[1:]):
        m = (prob >= lo) & (prob < hi)
        if m.sum() < 3:
            continue
        ece += (m.sum() / n) * abs(tgt[m].mean() - prob[m].mean())
    return float(ece)


def ece_10bins(prob, tgt):
    """10-bin ECE, matching benchmark/metrics.py."""
    bins = np.linspace(0, 1, 11)
    ece, n = 0.0, len(tgt)
    for lo, hi in zip(bins[:-1], bins[1:]):
        m = (prob >= lo) & (prob < hi)
        if m.sum() < 3:
            continue
        ece += (m.sum() / n) * abs(tgt[m].mean() - prob[m].mean())
    return float(ece)


# ── Core per-group stats ───────────────────────────────────────────────────────

def compute_group_stats(prob_pos, targets, qbar, label, min_n=30, min_half=10):
    """
    Returns a dict with ECE, QCDI (median split), Spearman rho, and group counts.
    If n < min_n, QCDI is returned as NaN with a note.
    """
    n = len(targets)
    n_pos = int(targets.sum())
    n_neg = n - n_pos

    # Overall ECE
    if n_pos > 0 and n_neg > 0 and n >= 5:
        e10 = ece_10bins(prob_pos, targets)
        e15 = ece_15bins(prob_pos, targets)
    else:
        e10 = e15 = float("nan")

    result = {
        "label": label,
        "n": n,
        "n_pos": n_pos,
        "qbar_mean": float(np.mean(qbar)),
        "qbar_median": float(np.median(qbar)),
        "ece_10bins": e10,
        "ece_15bins": e15,
    }

    if n < min_n:
        result.update({
            "n_lq": int(n // 2), "n_hq": n - int(n // 2),
            "ece_lq_10": float("nan"), "ece_hq_10": float("nan"), "qcdi_10": float("nan"),
            "ece_lq_15": float("nan"), "ece_hq_15": float("nan"), "qcdi_15": float("nan"),
            "entropy_vs_qbar_rho": float("nan"), "entropy_vs_qbar_rho_p": float("nan"),
            "note": f"n<{min_n} — QCDI unreliable (small sample)",
        })
        return result

    cut = float(np.median(qbar))
    lq = qbar < cut
    hq = qbar >= cut

    def _safe_ece(fn, mask):
        pp, tg = prob_pos[mask], targets[mask]
        if len(tg) < min_half or tg.sum() == 0 or tg.sum() == len(tg):
            return float("nan")
        return fn(pp, tg)

    el10 = _safe_ece(ece_10bins, lq)
    eh10 = _safe_ece(ece_10bins, hq)
    el15 = _safe_ece(ece_15bins, lq)
    eh15 = _safe_ece(ece_15bins, hq)

    qcdi10 = (el10 - eh10) if not (np.isnan(el10) or np.isnan(eh10)) else float("nan")
    qcdi15 = (el15 - eh15) if not (np.isnan(el15) or np.isnan(eh15)) else float("nan")

    # Spearman rho: entropy vs qbar
    probs2 = np.stack([1 - prob_pos, prob_pos], axis=1).clip(1e-9)
    entropy = -(probs2 * np.log(probs2)).sum(axis=1)
    if n >= 5:
        rho, rho_p = spearmanr(entropy, qbar)
        rho, rho_p = float(rho), float(rho_p)
    else:
        rho, rho_p = float("nan"), float("nan")

    result.update({
        "n_lq": int(lq.sum()),
        "n_hq": int(hq.sum()),
        "ece_lq_10": el10, "ece_hq_10": eh10, "qcdi_10": qcdi10,
        "ece_lq_15": el15, "ece_hq_15": eh15, "qcdi_15": qcdi15,
        "entropy_vs_qbar_rho": rho,
        "entropy_vs_qbar_rho_p": rho_p,
    })
    return result


# ── Load data ──────────────────────────────────────────────────────────────────

print("Loading ITB-Diverse metadata...")
subsets = pd.read_csv(ROOT / "project/results/itb_subsets.csv")
diverse_meta = subsets[subsets["subset"] == "ITB-Diverse"].reset_index(drop=True)
assert len(diverse_meta) == 1500, f"Expected 1500, got {len(diverse_meta)}"

# Fitzpatrick17k metadata
fp17k = pd.read_csv(ROOT / "data/raw/fitzpatrick17k/fitzpatrick17k.csv")[
    ["md5hash", "fitzpatrick_scale", "label", "nine_partition_label", "three_partition_label"]
].rename(columns={"md5hash": "isic_id"})

diverse_meta = diverse_meta.merge(fp17k, on="isic_id", how="left")
nan_count = diverse_meta["label"].isna().sum()
print(f"  ITB-Diverse n=1500, unmatched in fp17k: {nan_count}")

# Predictions
print("Loading predictions...")
preds_all = pd.read_csv(ROOT / "project/results/itb_predictions.csv")
qcts_preds = pd.read_csv(ROOT / "project/results/qcts_itb_predictions.csv")

def get_pred(baseline_code, preds_df=preds_all):
    df = preds_df[
        (preds_df["baseline"] == baseline_code) &
        (preds_df["subset"] == "ITB-Diverse")
    ].reset_index(drop=True)
    assert len(df) == 1500, f"Expected 1500 rows for {baseline_code}, got {len(df)}"
    assert (df["target"].values == diverse_meta["target"].values).all(), \
        f"Target mismatch for {baseline_code}"
    return df["prob_pos"].values

prob_std_vib    = get_pred("D")
prob_mc_dropout = get_pred("I")
prob_qcts       = get_pred("D+QCTS", qcts_preds)

targets_all = diverse_meta["target"].values.astype(float)
qbar_all    = diverse_meta["qbar"].values

BASELINES = {
    "Std VIB":        prob_std_vib,
    "Std VIB + QCTS": prob_qcts,
    "MC Dropout":     prob_mc_dropout,
}

# ── Define stratification groups ───────────────────────────────────────────────

nine_lbl = diverse_meta["nine_partition_label"].values
three_lbl = diverse_meta["three_partition_label"].values
fitz_all  = diverse_meta["fitzpatrick_scale"].values

# --- Nine-partition groups ---
nine_groups = {}
for cat in sorted(diverse_meta["nine_partition_label"].unique()):
    nine_groups[cat] = (nine_lbl == cat)

# --- Three-partition groups ---
three_groups = {
    "benign":         (three_lbl == "benign"),
    "malignant":      (three_lbl == "malignant"),
    "non-neoplastic": (three_lbl == "non-neoplastic"),
}

# --- Binary malignant vs non-malignant ---
binary_groups = {
    "malignant":     (three_lbl == "malignant"),
    "non-malignant": (three_lbl != "malignant"),
}

# --- Fitzpatrick skin type groups (rerun for completeness in unified output) ---
fitz_groups = {
    "I":      (fitz_all == 1),
    "II":     (fitz_all == 2),
    "III":    (fitz_all == 3),
    "IV":     (fitz_all == 4),
    "V":      (fitz_all == 5),
    "VI":     (fitz_all == 6),
    "I-II":   (fitz_all <= 2),
    "III-IV": (fitz_all == 3) | (fitz_all == 4),
    "V-VI":   (fitz_all >= 5),
}

ALL_STRATA = {
    "nine_partition":   nine_groups,
    "three_partition":  three_groups,
    "malignant_binary": binary_groups,
    "fitzpatrick":      fitz_groups,
}

# ── Compute ────────────────────────────────────────────────────────────────────

results = {}

for bl_name, prob_pos in BASELINES.items():
    print(f"\n{'='*65}")
    print(f"  Baseline: {bl_name}")
    print(f"{'='*65}")
    results[bl_name] = {}

    for stratum_name, groups in ALL_STRATA.items():
        results[bl_name][stratum_name] = {}
        print(f"\n  [{stratum_name}]")
        for grp_name, mask in groups.items():
            if mask.sum() == 0:
                continue
            stats = compute_group_stats(
                prob_pos[mask],
                targets_all[mask],
                qbar_all[mask],
                label=grp_name,
            )
            results[bl_name][stratum_name][grp_name] = stats
            note = stats.get("note", "")
            print(
                f"    {grp_name:30s}  n={stats['n']:4d}  "
                f"ECE(15)={stats['ece_15bins']:.4f}  "
                f"QCDI(15)={stats['qcdi_15']:.4f}  "
                f"rho={stats['entropy_vs_qbar_rho']:.3f}"
                + (f"  [{note}]" if note else "")
            )

# ── Data availability metadata ─────────────────────────────────────────────────

results["_metadata"] = {
    "analysis_date": "2026-05-20",
    "itb_diverse_n": 1500,
    "itb_diverse_source": "fitzpatrick17k_only",
    "strata_computed": list(ALL_STRATA.keys()),
    "strata_blocked": {
        "sex": "Not in Fitzpatrick17k metadata. ISIC 2020 local copy stripped to isic_id/patient_id/target only.",
        "age_group": "Not in Fitzpatrick17k metadata. ISIC 2020 local copy stripped to isic_id/patient_id/target only.",
        "body_location": "Not in Fitzpatrick17k metadata. ISIC 2020 local copy stripped to isic_id/patient_id/target only.",
        "note": "All 1500 ITB-Diverse images are from Fitzpatrick17k (clinical web scrape). "
                "The original ISIC 2020 Kaggle train.csv with sex/age_approx/anatom_site_general_challenge "
                "was not downloaded — local ISIC 2020 metadata only has isic_id, patient_id, target. "
                "The 1320 ITB-LQ/HQ/Edge images (ISIC 2020) also lack rich metadata locally. "
                "To unlock sex/age/body_location strata: download original ISIC 2020 Kaggle CSV "
                "(train.csv, ~12 MB) and merge on isic_id.",
    },
    "baselines": list(BASELINES.keys()),
}

# ── Save ───────────────────────────────────────────────────────────────────────

out_json = ROOT / "project/results/fairness_full_breakdown.json"
with open(out_json, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
print(f"\nSaved JSON → {out_json}")

# Flat CSV
rows = []
for bl_name, strata in results.items():
    if bl_name.startswith("_"):
        continue
    for stratum_name, groups in strata.items():
        for grp_name, stats in groups.items():
            row = {"baseline": bl_name, "stratum": stratum_name}
            row.update({k: v for k, v in stats.items() if k != "note"})
            if "note" in stats:
                row["note"] = stats["note"]
            rows.append(row)

df_out = pd.DataFrame(rows)
out_csv = ROOT / "project/results/fairness_full_breakdown.csv"
df_out.to_csv(out_csv, index=False)
print(f"Saved CSV  → {out_csv}")

# ── Summary tables ─────────────────────────────────────────────────────────────

print("\n" + "=" * 90)
print("SUMMARY: QCDI (15-bin) by lesion type [three_partition]")
print(f"{'Group':25s} | {'n':>5} | Std VIB QCDI | QCTS QCDI | MCD QCDI")
print("-" * 75)
for grp in ["malignant", "non-neoplastic", "benign"]:
    s_vib  = results["Std VIB"]["three_partition"].get(grp, {})
    s_qcts = results["Std VIB + QCTS"]["three_partition"].get(grp, {})
    s_mcd  = results["MC Dropout"]["three_partition"].get(grp, {})
    print(
        f"{grp:25s} | {s_vib.get('n', 0):5d} | "
        f"{s_vib.get('qcdi_15', float('nan')):12.4f} | "
        f"{s_qcts.get('qcdi_15', float('nan')):9.4f} | "
        f"{s_mcd.get('qcdi_15', float('nan')):8.4f}"
    )

print("\n" + "=" * 90)
print("SUMMARY: QCDI (15-bin) by nine-partition lesion type [Std VIB vs QCTS]")
print(f"{'Group':35s} | {'n':>5} | {'Std VIB QCDI':>12} | {'QCTS QCDI':>10} | {'Δ QCDI':>8}")
print("-" * 80)
for grp in sorted(nine_groups.keys(), key=lambda x: -nine_groups[x].sum()):
    s_vib  = results["Std VIB"]["nine_partition"].get(grp, {})
    s_qcts = results["Std VIB + QCTS"]["nine_partition"].get(grp, {})
    q_v = s_vib.get("qcdi_15", float("nan"))
    q_q = s_qcts.get("qcdi_15", float("nan"))
    delta = (q_q - q_v) if not (np.isnan(q_v) or np.isnan(q_q)) else float("nan")
    note = " (*)" if "note" in s_vib else ""
    print(
        f"{grp+note:35s} | {s_vib.get('n', 0):5d} | "
        f"{q_v:12.4f} | {q_q:10.4f} | {delta:8.4f}"
    )
print("(*) n < 30: QCDI unreliable")

print("\n" + "=" * 90)
print("SUMMARY: malignant vs non-malignant (15-bin QCDI)")
print(f"{'Group':20s} | {'n':>5} | {'ECE (15)':>9} | {'Std VIB QCDI':>12} | {'QCTS QCDI':>10}")
print("-" * 65)
for grp in ["malignant", "non-malignant"]:
    s_vib  = results["Std VIB"]["malignant_binary"].get(grp, {})
    s_qcts = results["Std VIB + QCTS"]["malignant_binary"].get(grp, {})
    print(
        f"{grp:20s} | {s_vib.get('n', 0):5d} | "
        f"{s_vib.get('ece_15bins', float('nan')):9.4f} | "
        f"{s_vib.get('qcdi_15', float('nan')):12.4f} | "
        f"{s_qcts.get('qcdi_15', float('nan')):10.4f}"
    )

print("\n" + "=" * 90)
print("BLOCKED strata (not computable from local data):")
for k, v in results["_metadata"]["strata_blocked"].items():
    if k != "note":
        print(f"  {k}: {v[:100]}...")
print(f"\n  Resolution: {results['_metadata']['strata_blocked']['note'][:150]}...")

print("\nDone.")
