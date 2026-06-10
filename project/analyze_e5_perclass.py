"""Per-class E5 salvage/damage breakdown — the metric that judges mask-L1 (v6).

会话 22 揪出: aggregate SalvageRate (0.737) is benign-dominated and hides that enhancement
HARMS melanoma (salvage 5.2% / damage 31% on v5). The decisive v6 question is whether
mask-weighted L1 lifts melanoma salvage and cuts melanoma damage. This script computes the
per-class numbers from an e5_salvage_persample.csv and (optionally) diffs two runs.

Definitions (per class, over all severities; rate valid, counts are x3 the unique images):
  salvageable = degraded misclassified (correct_deg==0)
  salvaged    = salvageable that enhancement fixes (correct_enh==1)
  SalvageRate = salvaged / salvageable
  damaged     = degraded-correct that enhancement breaks (correct_deg==1 & correct_enh==0)
  DamageRate  = damaged / (correct_deg==1)

Usage:
  python project/analyze_e5_perclass.py project/results/e5_salvage_v6_persample.csv
  python project/analyze_e5_perclass.py V6.csv --baseline project/results/e5_salvage_persample.csv
"""
import argparse
import pandas as pd


def per_class(csv_path):
    df = pd.read_csv(csv_path)
    cd, ce = df["correct_deg"].astype(int), df["correct_enh"].astype(int)
    out = {}
    for tgt, name in [(1, "melanoma"), (0, "benign")]:
        m = df["target"] == tgt
        salvageable = ((cd == 0) & m).sum()
        salvaged = ((cd == 0) & (ce == 1) & m).sum()
        correct_deg = ((cd == 1) & m).sum()
        damaged = ((cd == 1) & (ce == 0) & m).sum()
        out[name] = {
            "salvageable": int(salvageable), "salvaged": int(salvaged),
            "SalvageRate": salvaged / salvageable if salvageable else 0.0,
            "correct_deg": int(correct_deg), "damaged": int(damaged),
            "DamageRate": damaged / correct_deg if correct_deg else 0.0,
            "net": int(salvaged - damaged),
        }
    return out


def show(tag, pc):
    print(f"\n=== {tag} ===")
    print(f"{'class':10}{'salv/able':>14}{'SalvageRate':>13}{'dmg/correct':>14}{'DamageRate':>12}{'net':>7}")
    for name in ("melanoma", "benign"):
        d = pc[name]
        print(f"{name:10}{d['salvaged']:>6}/{d['salvageable']:<7}{d['SalvageRate']:>12.1%}"
              f"{d['damaged']:>7}/{d['correct_deg']:<6}{d['DamageRate']:>11.1%}{d['net']:>7}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--baseline", default=None, help="v5 persample csv to diff against")
    args = ap.parse_args()

    new = per_class(args.csv)
    show(args.csv.split("/")[-1], new)

    if args.baseline:
        base = per_class(args.baseline)
        show("baseline " + args.baseline.split("/")[-1], base)
        print("\n=== melanoma delta (v6 - baseline) — the mask-L1 verdict ===")
        mn, mb = new["melanoma"], base["melanoma"]
        print(f"  SalvageRate: {mb['SalvageRate']:.1%} -> {mn['SalvageRate']:.1%} "
              f"({mn['SalvageRate']-mb['SalvageRate']:+.1%})")
        print(f"  DamageRate:  {mb['DamageRate']:.1%} -> {mn['DamageRate']:.1%} "
              f"({mn['DamageRate']-mb['DamageRate']:+.1%})")
        print(f"  net salvaged-damaged: {mb['net']} -> {mn['net']} ({mn['net']-mb['net']:+d})")
        verdict = ("mask-L1 HELPS melanoma" if mn["net"] > mb["net"]
                   else "mask-L1 does NOT help melanoma")
        print(f"  VERDICT: {verdict}")


if __name__ == "__main__":
    main()
