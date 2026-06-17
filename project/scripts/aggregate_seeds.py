"""Aggregate per-seed ITB result CSVs into itb_results_3seed_agg.csv.

Reads:
  results/itb_results_s42.csv
  results/itb_results_s123.csv
  results/itb_results_s2024.csv

Writes:
  results/itb_results_3seed_agg.csv
  columns: baseline, subset, auc_mean, auc_std, ece_mean, ece_std, n_seeds

Usage:
  cd D:/YJ-Agent/project
  python scripts/aggregate_seeds.py [--seeds 42 123 2024] [--out results/itb_results_3seed_agg.csv]
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

SEED_FILES_DEFAULT = [
    "results/itb_results_s42.csv",
    "results/itb_results_s123.csv",
    "results/itb_results_s2024.csv",
]
OUT_DEFAULT = "results/itb_results_3seed_agg.csv"


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--files", nargs="+", default=SEED_FILES_DEFAULT,
                   help="Per-seed result CSVs (must each have baseline/subset/auc/ece cols)")
    p.add_argument("--out", default=OUT_DEFAULT)
    return p.parse_args()


def aggregate(files: list[str]) -> pd.DataFrame:
    dfs = []
    for fn in files:
        path = Path(fn)
        if not path.exists():
            print(f"  [WARN] missing {path}, skipping")
            continue
        df = pd.read_csv(path)
        df["_src"] = str(path)
        dfs.append(df)

    if not dfs:
        raise FileNotFoundError("No seed result CSVs found. Run run_experiments.py --seed first.")

    combined = pd.concat(dfs, ignore_index=True)
    print(f"  Combined {len(combined)} rows from {len(dfs)} file(s)")
    print(f"  Baselines: {sorted(combined['baseline'].unique().tolist())}")
    print(f"  Subsets:   {sorted(combined['subset'].unique().tolist())}")

    agg = (
        combined
        .groupby(["baseline", "subset"])
        .agg(
            auc_mean=("auc", "mean"),
            auc_std=("auc", "std"),
            ece_mean=("ece", "mean"),
            ece_std=("ece", "std"),
            n_seeds=("auc", "count"),
        )
        .reset_index()
    )
    # std with n=1 gives NaN — treat as 0
    agg["auc_std"] = agg["auc_std"].fillna(0.0)
    agg["ece_std"] = agg["ece_std"].fillna(0.0)

    # Integrity check: warn if any baseline pair has suspiciously identical auc_mean
    baselines = agg["baseline"].unique().tolist()
    for s in agg["subset"].unique():
        sub = agg[agg["subset"] == s].set_index("baseline")
        for i, b1 in enumerate(baselines):
            for b2 in baselines[i + 1:]:
                if b1 not in sub.index or b2 not in sub.index:
                    continue
                v1 = float(sub.loc[b1, "auc_mean"])
                v2 = float(sub.loc[b2, "auc_mean"])
                if abs(v1 - v2) < 1e-9:
                    print(
                        f"  [WARN] {b1} and {b2} have identical auc_mean={v1:.10f} "
                        f"on {s}. Verify that ckpts are distinct (run ckpt-check)."
                    )

    return agg


def main():
    args = parse_args()
    print(f"Aggregating {len(args.files)} seed files -> {args.out}")
    agg = aggregate(args.files)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    agg.to_csv(out, index=False)
    print(f"\nWrote {len(agg)} rows to {out}")
    print(agg.to_string(index=False))


if __name__ == "__main__":
    main()
