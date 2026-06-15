"""
L10 ICLR fairness: Fitzpatrick I-VI stratified calibration + equivalence test.
Uses full fitz17k cross-domain predictions (results/external_fitz17k_predictions.csv).

Outputs (NEW files only; never touches BMVC fairness_fitzpatrick_breakdown.*):
  results/fairness_fitzpatrick_iclr_full.csv   (long table)
  results/fairness_fitzpatrick_iclr_full.json  (max-min gap + V-VI vs I-IV TOST)

Numbers computed from CSV. No hardcoded results.
"""
import os
import json
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
PRED = os.path.join(PROJ, "results", "external_fitz17k_predictions.csv")
META = os.path.join(os.path.dirname(PROJ), "data", "raw", "fitzpatrick17k", "fitzpatrick17k.csv")
OUT_CSV = os.path.join(PROJ, "results", "fairness_fitzpatrick_iclr_full.csv")
OUT_JSON = os.path.join(PROJ, "results", "fairness_fitzpatrick_iclr_full.json")

ECE_GAP_THRESH = 0.05
TOST_BOUND = 0.05  # AUC equivalence margin
N_BOOT = 1000
SEED = 42

# Fitzpatrick scale 1-6 -> roman label
SCALE2ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI"}
SINGLE = ["I", "II", "III", "IV", "V", "VI"]
GROUPS = {
    "I-II": [1, 2],
    "III-IV": [3, 4],
    "V-VI": [5, 6],
}


def _ece(prob, tgt, n_bins=15):
    bins = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    n = len(tgt)
    if n == 0:
        return float('nan')
    for lo, hi in zip(bins[:-1], bins[1:]):
        m = (prob >= lo) & (prob < hi)
        if m.sum() < 3:
            continue
        ece += (m.sum() / n) * abs(tgt[m].mean() - prob[m].mean())
    return float(ece)


def _auc(prob, tgt):
    if len(np.unique(tgt)) < 2:
        return float('nan')
    return float(roc_auc_score(tgt, prob))


def _ece_bootstrap_ci(prob, tgt, n_boot=N_BOOT, seed=SEED):
    n = len(tgt)
    if n < 3:
        return float('nan'), float('nan')
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        vals.append(_ece(prob[idx], tgt[idx]))
    vals = np.array([v for v in vals if not np.isnan(v)])
    if len(vals) == 0:
        return float('nan'), float('nan')
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


def _auc_boot_dist(prob, tgt, n_boot=N_BOOT, seed=SEED):
    """Bootstrap distribution of AUC (NaN-dropped)."""
    n = len(tgt)
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        a = _auc(prob[idx], tgt[idx])
        vals.append(a)
    return np.array(vals)


def tost_equivalence(prob_deep, tgt_deep, prob_light, tgt_light,
                     bound=TOST_BOUND, n_boot=N_BOOT, seed=SEED):
    """TOST on AUC difference (deep V-VI minus light I-IV).
    Bootstrap the difference distribution; H0: |diff| >= bound, equivalence if both
    one-sided tests reject (i.e. CI of diff inside (-bound, +bound)).
    p_lower: P(diff <= -bound) ; p_upper: P(diff >= +bound) under bootstrap dist.
    Equivalence p = max(p_lower, p_upper); equivalent if p < 0.05.
    """
    rng = np.random.default_rng(seed)
    nd, nl = len(tgt_deep), len(tgt_light)
    diffs = []
    for _ in range(n_boot):
        di = rng.integers(0, nd, nd)
        li = rng.integers(0, nl, nl)
        ad = _auc(prob_deep[di], tgt_deep[di])
        al = _auc(prob_light[li], tgt_light[li])
        if np.isnan(ad) or np.isnan(al):
            continue
        diffs.append(ad - al)
    diffs = np.array(diffs)
    auc_deep = _auc(prob_deep, tgt_deep)
    auc_light = _auc(prob_light, tgt_light)
    point_diff = auc_deep - auc_light
    if len(diffs) == 0:
        return {
            "auc_deep_VVI": auc_deep, "auc_light_IIV": auc_light,
            "auc_diff": point_diff, "n_deep": nd, "n_light": nl,
            "tost_p_lower": float('nan'), "tost_p_upper": float('nan'),
            "tost_p": float('nan'), "equivalent": None,
            "diff_ci_lo": float('nan'), "diff_ci_hi": float('nan'),
            "bound": bound,
        }
    # one-sided p-values from bootstrap dist of diff
    p_lower = float(np.mean(diffs <= -bound))   # mass beyond lower margin
    p_upper = float(np.mean(diffs >= bound))    # mass beyond upper margin
    p_tost = max(p_lower, p_upper)
    ci_lo = float(np.percentile(diffs, 2.5))
    ci_hi = float(np.percentile(diffs, 97.5))
    equivalent = bool((p_tost < 0.05) and (ci_lo > -bound) and (ci_hi < bound))
    return {
        "auc_deep_VVI": auc_deep, "auc_light_IIV": auc_light,
        "auc_diff": point_diff, "n_deep": nd, "n_light": nl,
        "tost_p_lower": p_lower, "tost_p_upper": p_upper,
        "tost_p": p_tost, "equivalent": equivalent,
        "diff_ci_lo": ci_lo, "diff_ci_hi": ci_hi, "bound": bound,
    }


def main():
    pred = pd.read_csv(PRED)
    meta = pd.read_csv(META, usecols=["md5hash", "fitzpatrick_scale"])
    meta = meta.rename(columns={"md5hash": "image_id"})
    # drop unknown skin type (-1) and out-of-range
    meta = meta[meta["fitzpatrick_scale"].isin([1, 2, 3, 4, 5, 6])]

    df = pred.merge(meta, on="image_id", how="inner")
    n_total_pred_imgs = pred["image_id"].nunique()
    n_joined_imgs = df["image_id"].nunique()
    print(f"[join] pred unique imgs={n_total_pred_imgs}, "
          f"joined (known skintype) unique imgs={n_joined_imgs}")

    rows = []
    summary = {
        "meta": {
            "pred_csv": "results/external_fitz17k_predictions.csv",
            "meta_csv": "data/raw/fitzpatrick17k/fitzpatrick17k.csv",
            "n_bins": 15, "n_boot": N_BOOT, "seed": SEED,
            "ece_gap_thresh": ECE_GAP_THRESH, "tost_bound": TOST_BOUND,
            "pred_unique_images": int(n_total_pred_imgs),
            "joined_unique_images_known_skintype": int(n_joined_imgs),
        },
        "baselines": {},
    }

    baselines = df[["baseline", "baseline_name"]].drop_duplicates()
    baselines = baselines.sort_values("baseline").values.tolist()

    for code, name in baselines:
        sub = df[df["baseline"] == code]
        bl_rows = []

        # single skin types I-VI
        single_ece = {}
        for scale, roman in SCALE2ROMAN.items():
            s = sub[sub["fitzpatrick_scale"] == scale]
            prob = s["prob_pos"].to_numpy()
            tgt = s["target"].to_numpy().astype(int)
            n = len(tgt)
            npos = int(tgt.sum()) if n else 0
            auc = _auc(prob, tgt) if n else float('nan')
            ece = _ece(prob, tgt) if n else float('nan')
            ci_lo, ci_hi = _ece_bootstrap_ci(prob, tgt) if n else (float('nan'), float('nan'))
            single_ece[roman] = ece
            rec = dict(baseline=code, baseline_name=name, skin_group=roman,
                       n=n, n_pos=npos, auc=auc, ece_15=ece,
                       ece_ci_lo=ci_lo, ece_ci_hi=ci_hi)
            rows.append(rec)
            bl_rows.append(rec)

        # grouped I-II / III-IV / V-VI
        for gname, scales in GROUPS.items():
            s = sub[sub["fitzpatrick_scale"].isin(scales)]
            prob = s["prob_pos"].to_numpy()
            tgt = s["target"].to_numpy().astype(int)
            n = len(tgt)
            npos = int(tgt.sum()) if n else 0
            auc = _auc(prob, tgt) if n else float('nan')
            ece = _ece(prob, tgt) if n else float('nan')
            ci_lo, ci_hi = _ece_bootstrap_ci(prob, tgt) if n else (float('nan'), float('nan'))
            rec = dict(baseline=code, baseline_name=name, skin_group=gname,
                       n=n, n_pos=npos, auc=auc, ece_15=ece,
                       ece_ci_lo=ci_lo, ece_ci_hi=ci_hi)
            rows.append(rec)
            bl_rows.append(rec)

        # max-min ECE gap across 6 single skin types
        eces = [single_ece[r] for r in SINGLE if not np.isnan(single_ece[r])]
        if eces:
            gap = float(max(eces) - min(eces))
            gap_pass = bool(gap < ECE_GAP_THRESH)
        else:
            gap = float('nan')
            gap_pass = None

        # TOST: deep V-VI (5,6) vs light I-IV (1,2,3,4)
        deep = sub[sub["fitzpatrick_scale"].isin([5, 6])]
        light = sub[sub["fitzpatrick_scale"].isin([1, 2, 3, 4])]
        tost = tost_equivalence(
            deep["prob_pos"].to_numpy(), deep["target"].to_numpy().astype(int),
            light["prob_pos"].to_numpy(), light["target"].to_numpy().astype(int),
        )

        summary["baselines"][code] = {
            "baseline_name": name,
            "ece_by_skintype": {r: single_ece[r] for r in SINGLE},
            "ece_maxmin_gap": gap,
            "ece_gap_pass": gap_pass,
            "tost_VVI_vs_IIV": tost,
        }

    out = pd.DataFrame(rows)
    out.to_csv(OUT_CSV, index=False)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"[write] {OUT_CSV} ({len(out)} rows)")
    print(f"[write] {OUT_JSON}")

    # console report for F = Ours
    print("\n===== F (Q-VIB Full = Ours) =====")
    fb = summary["baselines"].get("F")
    if fb:
        for r in SINGLE:
            print(f"  {r:>4}: ECE={fb['ece_by_skintype'][r]:.4f}")
        print(f"  max-min ECE gap = {fb['ece_maxmin_gap']:.4f} "
              f"({'PASS' if fb['ece_gap_pass'] else 'FAIL'} @<{ECE_GAP_THRESH})")
        t = fb["tost_VVI_vs_IIV"]
        print(f"  AUC V-VI(deep)={t['auc_deep_VVI']:.4f} (n={t['n_deep']}), "
              f"I-IV(light)={t['auc_light_IIV']:.4f} (n={t['n_light']})")
        print(f"  AUC diff={t['auc_diff']:.4f}, diff 95%CI=[{t['diff_ci_lo']:.4f},{t['diff_ci_hi']:.4f}]")
        print(f"  TOST p={t['tost_p']:.4f} -> equivalent={t['equivalent']} (bound +-{TOST_BOUND})")


if __name__ == "__main__":
    main()
