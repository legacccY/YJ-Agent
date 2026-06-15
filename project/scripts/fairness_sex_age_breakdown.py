"""
Sex / age fairness breakdown for L10 (ICLR).

Per-subpopulation ECE (15-bin) + bootstrap 95% CI + max-min ECE gap, sliced by:
  - sex:  M (male) / F (female)
  - age:  3 bins  <40 / 40-60 / >60   (age_approx from ISIC2020 metadata)

Source of demographics: ISIC2020 training ground-truth metadata
  data/raw/isic2020/ISIC_2020_Training_GroundTruth_v2.csv
joined on image_name == ITB isic_id.

ONLY ISIC2020-sourced ITB subsets carry sex/age (ITB-Edge / ITB-HQ / ITB-LQ).
ITB-Diverse = FitzPatrick17k (no sex/age) → excluded automatically (no metadata match).

ECE definition reuses `_ece_simple` (15 bins) from
  scripts/fairness_fitzpatrick_breakdown.py
for cross-analysis consistency.

Requires a predictions CSV that has an `image_name` column (see plans/L10_image_id_patch.md).

Outputs:
  results/fairness_sex_age_breakdown.csv
  results/fairness_sex_age_breakdown.json

Usage:
  cd D:/YJ-Agent/project
  python scripts/fairness_sex_age_breakdown.py
  python scripts/fairness_sex_age_breakdown.py --preds results/itb_predictions_withid.csv
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("D:/YJ-Agent")
sys.path.insert(0, str(ROOT / "project"))

ISIC_META = ROOT / "data/raw/isic2020/ISIC_2020_Training_GroundTruth_v2.csv"

# Min samples to report a subpop (CI unreliable below this).
MIN_N = 30
N_BOOT = 1000
BOOT_SEED = 42


# ── ECE function matching fairness_fitzpatrick_breakdown.py (15 bins) ────────────

def _ece_simple(prob, tgt, n_bins=15):
    """ECE with 15 bins, identical to fairness_fitzpatrick_breakdown.py._ece_simple."""
    bins = np.linspace(0, 1, n_bins + 1)
    ece, n = 0.0, len(tgt)
    if n == 0:
        return float("nan")
    for lo, hi in zip(bins[:-1], bins[1:]):
        m = (prob >= lo) & (prob < hi)
        if m.sum() < 3:
            continue
        ece += (m.sum() / n) * abs(tgt[m].mean() - prob[m].mean())
    return float(ece)


def _bootstrap_ece_ci(prob, tgt, n_boot=N_BOOT, seed=BOOT_SEED):
    """Bootstrap 95% CI on 15-bin ECE via case resampling."""
    n = len(tgt)
    if n < 5:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    boots = np.empty(n_boot, dtype=float)
    for b in range(n_boot):
        idx = rng.integers(0, n, size=n)
        boots[b] = _ece_simple(prob[idx], tgt[idx])
    boots = boots[~np.isnan(boots)]
    if boots.size == 0:
        return float("nan"), float("nan")
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return float(lo), float(hi)


# ── Subpopulation slicers ────────────────────────────────────────────────────────

def _age_bin(age):
    """3 bins: <40, 40-60, >60.  40-60 is inclusive of 40, exclusive of 60-boundary."""
    if pd.isna(age):
        return None
    if age < 40:
        return "<40"
    if age <= 60:
        return "40-60"
    return ">60"


def _subpop_stats(prob, tgt, label):
    """ECE(15-bin), n, n_pos, bootstrap 95% CI for one subpop."""
    n = len(tgt)
    pos = int(tgt.sum())
    if n < MIN_N or pos == 0 or pos == n:
        ece = _ece_simple(prob, tgt) if n >= 5 else float("nan")
        return {
            "label": label, "n": n, "n_pos": pos,
            "ece_15bins": ece, "ece_ci_lo": float("nan"), "ece_ci_hi": float("nan"),
            "note": f"n<{MIN_N} or single-class — CI unreliable",
        }
    ece = _ece_simple(prob, tgt)
    ci_lo, ci_hi = _bootstrap_ece_ci(prob, tgt)
    return {
        "label": label, "n": n, "n_pos": pos,
        "ece_15bins": ece, "ece_ci_lo": ci_lo, "ece_ci_hi": ci_hi,
    }


def _max_min_gap(subpop_results):
    """max-min ECE gap across subpops with valid (non-nan, reportable) ECE."""
    eces = [r["ece_15bins"] for r in subpop_results
            if not np.isnan(r["ece_15bins"]) and "note" not in r]
    if len(eces) < 2:
        return float("nan")
    return float(max(eces) - min(eces))


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preds", default="results/itb_predictions_withid.csv",
                    help="ITB predictions CSV (must have image_name, baseline, prob_pos, target).")
    ap.add_argument("--out-prefix", default="results/fairness_sex_age_breakdown")
    args = ap.parse_args()

    preds_path = ROOT / "project" / args.preds if not Path(args.preds).is_absolute() else Path(args.preds)
    preds = pd.read_csv(preds_path)
    if "image_name" not in preds.columns:
        raise SystemExit(
            f"ERROR: {preds_path} has no 'image_name' column. "
            f"Apply plans/L10_image_id_patch.md and re-run eval first."
        )

    meta = pd.read_csv(ISIC_META)[["image_name", "sex", "age_approx"]]
    # Normalize sex to M / F
    sex_map = {"male": "M", "female": "F", "M": "M", "F": "F"}
    meta["sex"] = meta["sex"].map(sex_map)
    meta["age_bin"] = meta["age_approx"].apply(_age_bin)

    df = preds.merge(meta, on="image_name", how="left")
    n_total = len(df)
    n_mapped = df["sex"].notna().sum()
    print(f"Predictions rows: {n_total}  |  ISIC2020 demographic match: {n_mapped} "
          f"({n_mapped / n_total * 100:.1f}%)")
    print(f"(unmatched = ITB-Diverse / FitzPatrick17k, excluded from sex/age)\n")

    SEX_ORDER = ["M", "F"]
    AGE_ORDER = ["<40", "40-60", ">60"]

    results = {}
    csv_rows = []

    for baseline, g in df.groupby("baseline"):
        bl_name = g["baseline_name"].iloc[0] if "baseline_name" in g.columns else str(baseline)
        results[str(baseline)] = {"baseline_name": bl_name, "sex": {}, "age": {}}
        print(f"{'=' * 60}\n  Baseline {baseline}  ({bl_name})\n{'=' * 60}")

        # ── Sex ──
        sex_stats = []
        for s in SEX_ORDER:
            sub = g[g["sex"] == s]
            if len(sub) == 0:
                continue
            st = _subpop_stats(sub["prob_pos"].values,
                               sub["target"].values.astype(float), f"sex={s}")
            results[str(baseline)]["sex"][s] = st
            sex_stats.append(st)
            csv_rows.append({"baseline": baseline, "baseline_name": bl_name,
                             "axis": "sex", **st})
            note = st.get("note", "")
            print(f"  sex={s:1s}  n={st['n']:4d}  n_pos={st['n_pos']:3d}  "
                  f"ECE={st['ece_15bins']:.4f}  "
                  f"CI=[{st['ece_ci_lo']:.4f},{st['ece_ci_hi']:.4f}]"
                  + (f"  [{note}]" if note else ""))
        sex_gap = _max_min_gap(sex_stats)
        results[str(baseline)]["sex_ece_gap"] = sex_gap
        csv_rows.append({"baseline": baseline, "baseline_name": bl_name,
                         "axis": "sex", "label": "MAX-MIN GAP", "n": "", "n_pos": "",
                         "ece_15bins": sex_gap, "ece_ci_lo": "", "ece_ci_hi": ""})
        print(f"  --> sex ECE gap (max-min) = {sex_gap:.4f}  "
              f"({'PASS' if sex_gap < 0.05 else 'FAIL'} <0.05)\n")

        # ── Age ──
        age_stats = []
        for a in AGE_ORDER:
            sub = g[g["age_bin"] == a]
            if len(sub) == 0:
                continue
            st = _subpop_stats(sub["prob_pos"].values,
                               sub["target"].values.astype(float), f"age={a}")
            results[str(baseline)]["age"][a] = st
            age_stats.append(st)
            csv_rows.append({"baseline": baseline, "baseline_name": bl_name,
                             "axis": "age", **st})
            note = st.get("note", "")
            print(f"  age={a:5s}  n={st['n']:4d}  n_pos={st['n_pos']:3d}  "
                  f"ECE={st['ece_15bins']:.4f}  "
                  f"CI=[{st['ece_ci_lo']:.4f},{st['ece_ci_hi']:.4f}]"
                  + (f"  [{note}]" if note else ""))
        age_gap = _max_min_gap(age_stats)
        results[str(baseline)]["age_ece_gap"] = age_gap
        csv_rows.append({"baseline": baseline, "baseline_name": bl_name,
                         "axis": "age", "label": "MAX-MIN GAP", "n": "", "n_pos": "",
                         "ece_15bins": age_gap, "ece_ci_lo": "", "ece_ci_hi": ""})
        print(f"  --> age ECE gap (max-min) = {age_gap:.4f}  "
              f"({'PASS' if age_gap < 0.05 else 'FAIL'} <0.05)\n")

    # ── Save ──
    out_prefix = ROOT / "project" / args.out_prefix \
        if not Path(args.out_prefix).is_absolute() else Path(args.out_prefix)
    json_path = out_prefix.with_suffix(".json")
    csv_path = out_prefix.with_suffix(".csv")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    pd.DataFrame(csv_rows).to_csv(csv_path, index=False)
    print(f"Saved JSON -> {json_path}")
    print(f"Saved CSV  -> {csv_path}")


if __name__ == "__main__":
    main()
