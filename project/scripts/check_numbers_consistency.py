"""W8 数字一致性检查：对照 csv/json 验证论文中每个关键数字。

运行：
    python project/scripts/check_numbers_consistency.py
输出：PASS / FAIL 逐行，最后打印 summary。
"""
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path("D:/YJ-Agent")
TEX  = ROOT / "project/meeting/BMVC/itb_paper.tex"
RESULTS = ROOT / "project/results"

failures = []
passes   = []


def check(name: str, paper_val, actual_val, tol: float = 0.005):
    ok = abs(float(paper_val) - float(actual_val)) <= tol
    (passes if ok else failures).append(
        f"  {'PASS' if ok else 'FAIL'}  {name}: paper={paper_val:.4f}  actual={actual_val:.4f}"
    )
    return ok


# ── Load source data ──────────────────────────────────────────────────────────

preds = pd.read_csv(RESULTS / "itb_predictions.csv")
qcts  = pd.read_csv(RESULTS / "qcts_itb_predictions.csv")
itb_s = pd.read_csv(RESULTS / "itb_subsets.csv")

d     = preds[preds["baseline"] == "D"].reset_index(drop=True)
ts    = preds[preds["baseline"] == "TS"].reset_index(drop=True)
dq    = qcts[qcts["baseline"] == "D+QCTS"].reset_index(drop=True)

def ece(p, t, n=15):
    bins = np.linspace(0, 1, n + 1)
    e, n_total = 0.0, len(t)
    for lo, hi in zip(bins[:-1], bins[1:]):
        m = (p >= lo) & (p < hi)
        if m.sum() < 3: continue
        e += (m.sum() / n_total) * abs(t[m].mean() - p[m].mean())
    return float(e)

def entropy(p):
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return -(p * np.log(p) + (1 - p) * np.log(1 - p))

lq  = d["subset"] == "ITB-LQ"
hq  = d["subset"] == "ITB-HQ"
qlq = dq["subset"] == "ITB-LQ"
qhq = dq["subset"] == "ITB-HQ"

# ── Abstract / §5.2 core numbers ────────────────────────────────────────────

# Full pool rho: raw -0.153, TS +0.241
rho_raw, _ = spearmanr(entropy(d["prob_pos"].values), d["qbar"].values)
rho_ts,  _ = spearmanr(entropy(ts["prob_pos"].values), ts["qbar"].values)
check("rho_raw_full_pool", -0.153, rho_raw, tol=0.002)
check("rho_ts_full_pool",  +0.241, rho_ts,  tol=0.002)

# QCTS ECE-LQ 0.079, ECE-HQ 0.075
ece_qcts_lq = ece(dq[qlq]["prob_pos"].values, dq[qlq]["target"].values)
ece_qcts_hq = ece(dq[qhq]["prob_pos"].values, dq[qhq]["target"].values)
check("ece_qcts_lq", 0.079, ece_qcts_lq, tol=0.003)
check("ece_qcts_hq", 0.075, ece_qcts_hq, tol=0.003)

# Std VIB ECE-LQ 0.146 (before QCTS)
ece_vib_lq = ece(d[lq]["prob_pos"].values, d[lq]["target"].values)
check("ece_vib_lq", 0.146, ece_vib_lq, tol=0.003)

# QCDI: +0.015 (Std TS) vs +0.004 (QCTS)
ts_lq = ts["subset"] == "ITB-LQ"
ts_hq = ts["subset"] == "ITB-HQ"
ece_ts_lq = ece(ts[ts_lq]["prob_pos"].values, ts[ts_lq]["target"].values)
ece_ts_hq = ece(ts[ts_hq]["prob_pos"].values, ts[ts_hq]["target"].values)
qcdi_ts   = ece_ts_lq - ece_ts_hq
qcdi_qcts = ece_qcts_lq - ece_qcts_hq
check("qcdi_ts",   +0.015, qcdi_ts,   tol=0.005)
check("qcdi_qcts", +0.004, qcdi_qcts, tol=0.003)

# QCTS rho -0.249
rho_qcts, _ = spearmanr(entropy(dq["prob_pos"].values), dq["qbar"].values)
check("rho_qcts_full_pool", -0.249, rho_qcts, tol=0.003)

# ── §5.3 seed alphas ─────────────────────────────────────────────────────────

with open(RESULTS / "qcts_params.json") as f:
    params = json.load(f)
check("qcts_T0",    1.170, params["T0"],    tol=0.002)
check("qcts_alpha", 0.955, params["alpha"], tol=0.002)

# ── §5.6 Fitzpatrick V-VI numbers ────────────────────────────────────────────

fp_csv = pd.read_csv(RESULTS / "fairness_fitzpatrick_breakdown.csv")
vvi_vib  = fp_csv[(fp_csv["baseline"]=="Std VIB")    & (fp_csv["label"]=="V-VI")]
vvi_qcts = fp_csv[(fp_csv["baseline"]=="Std VIB + QCTS") & (fp_csv["label"]=="V-VI")]

if len(vvi_vib) and len(vvi_qcts):
    rho_vvi_vib  = float(vvi_vib["entropy_vs_qbar_rho"].iloc[0])
    rho_vvi_qcts = float(vvi_qcts["entropy_vs_qbar_rho"].iloc[0])
    check("rho_vvi_vib",  -0.134, rho_vvi_vib,  tol=0.003)
    check("rho_vvi_qcts", -0.306, rho_vvi_qcts, tol=0.003)

# ── §5.2 MC Dropout LQ-stratum rho +0.350 ────────────────────────────────────

mc = preds[preds["baseline"] == "I"]
mc_lq = mc[mc["subset"] == "ITB-LQ"]
rho_mc_lq, _ = spearmanr(entropy(mc_lq["prob_pos"].values), mc_lq["qbar"].values)
check("rho_mc_dropout_lq", +0.350, rho_mc_lq, tol=0.005)

# ── L7 statistics ─────────────────────────────────────────────────────────────

with open(RESULTS / "statistics_l7.json") as f:
    stats = json.load(f)
d_qcts = next((r["d"] for r in stats["cohens_d"] if r["baseline"] == "D+QCTS"), float("nan"))
power  = stats["power_analysis"]["power_QCTS_vs_StdVIB"]
check("cohens_d_qcts",  0.452, d_qcts, tol=0.005)
check("power",          0.929, power,  tol=0.005)

# ── QCTS params: T(qbar=0)=2.24, T(qbar=1)=1.44 ─────────────────────────────

import math
T0, alpha = params["T0"], params["alpha"]
T_at_0 = math.log1p(math.exp(T0 + alpha))
T_at_1 = math.log1p(math.exp(T0))
check("T_at_qbar_0", 2.24, T_at_0, tol=0.02)
check("T_at_qbar_1", 1.44, T_at_1, tol=0.02)

# ── Print results ─────────────────────────────────────────────────────────────

print("\n" + "="*70)
print(" NUMBERS CONSISTENCY CHECK")
print("="*70)
for line in passes:
    print(line)
for line in failures:
    print(line)
print("="*70)
print(f"  PASS: {len(passes)}   FAIL: {len(failures)}")
if failures:
    print("\nFailed checks — investigate before submission!")
    sys.exit(1)
else:
    print("\nAll checks passed.")
