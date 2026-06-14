"""ICLR Table 1 — QCTS row regeneration (会话 28).

QCTS 是后验温度校准 (post-hoc). 拟合需 val cache (quality_labels_all/abcd_cache/
efficientnet_index.csv 本地缺) -> 改用已存盘的拟合参数 results/qcts_params.json (best-NLL
seed), 套用到 *新* itb_predictions.csv 的 D (Std VIB) 预测重建 logit. 确定性 -> 与 BMVC
逐位复现, 但为 ICLR 管线自产 (红线 10: 不直接搬 BMVC csv).

读: results/itb_predictions.csv (新 D 预测) + results/qcts_params.json
写: results/qcts_itb_predictions.csv + results/qcts_itb_results.csv (baseline=D+QCTS)
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd

import sys
sys.path.insert(0, ".")
from run_qcts import qcts_temperature
from benchmark.metrics import summary_metrics

RES = Path("results")

params = json.loads((RES / "qcts_params.json").read_text())
T0, alpha = params["T0"], params["alpha"]
print(f"[QCTS] applying T0={T0:.4f} alpha={alpha:.4f} (best-NLL seed, from qcts_params.json)")

preds = pd.read_csv(RES / "itb_predictions.csv")
d = preds[preds["baseline"] == "D"].copy()
assert len(d) > 0, "no D (Std VIB) rows in itb_predictions.csv"

p = d["prob_pos"].clip(1e-7, 1 - 1e-7).values
logits = np.log(p / (1 - p))
T = np.maximum(qcts_temperature([T0, alpha], d["qbar"].values), 1e-3)
prob_qcts = 1.0 / (1.0 + np.exp(-logits / T))

out = pd.DataFrame({
    "baseline": "D+QCTS",
    "baseline_name": "Std VIB + QCTS (softplus)",
    "subset": d["subset"].values,
    "prob_pos": prob_qcts,
    "target": d["target"].values,
    "qbar": d["qbar"].values,
    "kl_term": 0.0,
    "prior_var": 0.0,
})
out.to_csv(RES / "qcts_itb_predictions.csv", index=False)
print(f"[saved] qcts_itb_predictions.csv  n={len(out)}")

# per-subset summary
rows = []
for sub in sorted(out["subset"].unique()):
    s = out[out["subset"] == sub]
    m = summary_metrics(s["prob_pos"].values, s["target"].values, s["qbar"].values)
    rows.append({"baseline": "D+QCTS", "baseline_name": "Std VIB + QCTS (softplus)",
                 "subset": sub, "n": len(s),
                 **{k: v for k, v in m.items() if k != "qbar_ece_segments"}})
    print(f"  {sub}: AUC={m['auc']:.3f} ECE={m['ece']:.3f}")
pd.DataFrame(rows).to_csv(RES / "qcts_itb_results.csv", index=False)
print("[saved] qcts_itb_results.csv")
