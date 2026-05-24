"""Fit QCTS on ITB-Edge as calibration proxy and evaluate on ITB-LQ + ITB-HQ.

Usage:
    python scripts/run_qcts.py \
        --predictions data/itb_predictions.csv \
        --output_dir outputs/qcts
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qcts import QCTSCalibrator
from itb import evaluate_on_itb


def prob_to_logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-7, 1 - 1e-7)
    return np.log(p / (1 - p))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", default="data/itb_predictions.csv")
    parser.add_argument("--baseline", default="D", help="Baseline code to calibrate (D = Std VIB)")
    parser.add_argument("--output_dir", default="outputs/qcts")
    parser.add_argument("--n_seeds", type=int, default=3)
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load
    df = pd.read_csv(args.predictions)
    base = df[df["baseline"] == args.baseline].reset_index(drop=True)
    print(f"Loaded {len(base)} predictions for baseline '{args.baseline}'")

    # Calibration set: ITB-Edge
    edge = base[base["subset"] == "ITB-Edge"]
    cal_logit  = prob_to_logit(edge["prob_pos"].values)
    cal_qbar   = edge["qbar"].values
    cal_target = edge["target"].values.astype(float)

    # Test set: ITB-LQ + ITB-HQ
    test = base[base["subset"].isin(["ITB-LQ", "ITB-HQ"])].reset_index(drop=True)
    test_logit  = prob_to_logit(test["prob_pos"].values)
    test_qbar   = test["qbar"].values
    test_target = test["target"].values.astype(float)
    test_subset = test["subset"].values

    # Fit
    print(f"Fitting QCTS on ITB-Edge (n={len(edge)})...")
    cal = QCTSCalibrator(n_seeds=args.n_seeds)
    cal.fit(cal_logit, cal_qbar, cal_target)
    print(f"  {cal}")

    # Predict
    prob_qcts = cal.predict(test_logit, test_qbar)

    # Evaluate
    metrics = evaluate_on_itb(
        prob_qcts, test_target, test_qbar, test_subset,
        method_name=f"QCTS ({args.baseline})",
    )

    # Save
    params_path = out_dir / "qcts_params.json"
    with open(params_path, "w") as f:
        json.dump({"T0": cal.T0_, "alpha": cal.alpha_}, f, indent=2)
    print(f"\nSaved params to {params_path}")

    metrics_path = out_dir / "qcts_metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2, default=str)
    print(f"Saved metrics to {metrics_path}")

    preds_df = test.copy()
    preds_df["prob_pos_qcts"] = prob_qcts
    preds_path = out_dir / "qcts_predictions.csv"
    preds_df.to_csv(preds_path, index=False)
    print(f"Saved predictions to {preds_path}")

    print(f"\n=== QCTS Results ===")
    print(f"  ECE-LQ : {metrics['ece_lq']:.4f}")
    print(f"  ECE-HQ : {metrics['ece_hq']:.4f}")
    print(f"  QCDI   : {metrics['qcdi']:+.4f}")
    print(f"  rho    : {metrics['rho']:+.4f}  (p={metrics['rho_p']:.2e})")


if __name__ == "__main__":
    main()
