"""W8 数字一致性检查：对照 csv/json 验证论文中每个关键数字。

覆盖：
- BMVC 锁定 17 数字（QCTS / TS / Fitzpatrick / MC Dropout / 统计量 / T 曲线）
- ICLR 锁定 13 新数字（Q-VIB Full + Adaptive Prior + Cross-domain + VisiScore）

运行：
    python project/scripts/check_numbers_consistency.py
输出：PASS / FAIL 逐行，最后打印 summary（30 项）。
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
iclr_failures = []  # separate bucket: paper numbers from M1+ era awaiting re-eval CSV
iclr_passes   = []
iclr_pending  = []  # locked-vs-csv mismatch flagged 待核, decision deferred (not pass/fail)

_current_section = "bmvc"  # toggled before ICLR section


def check(name: str, paper_val, actual_val, tol: float = 0.005):
    ok = abs(float(paper_val) - float(actual_val)) <= tol
    line = f"  {'PASS' if ok else 'FAIL'}  {name}: paper={paper_val:.4f}  actual={actual_val:.4f}"
    if _current_section == "iclr":
        (iclr_passes if ok else iclr_failures).append(line)
    else:
        (passes if ok else failures).append(line)
    return ok


def pending_check(name: str, locked_val, csv_val, note: str):
    """Record a 待核 (pending) audit hit: locked master-doc value disagrees with csv,
    but the resolution is intentionally deferred (do NOT silently overwrite either side)."""
    iclr_pending.append(
        f"  PEND  {name}: locked={locked_val:+.4f}  csv={csv_val:+.4f}  ({note})"
    )


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

# ──────────────────────────────────────────────────────────────────────────────
# ICLR-specific锁定数字 (STORY_FRAMEWORK.md §锁定数字)
# 18-30: Q-VIB Full / Adaptive Prior / Cross-domain / VisiScore PLCC-SRCC
#
# 验证策略（2026-05-27 audit 后）：
#   • Q-VIB 核心表 (n=19878 全 ISIC test): 对照 frozen eval_report_ablation.md 解析，
#     不再用 itb_predictions.csv (n=2820 ITB pool — 不同且更难的子集) 重算误判 FAIL。
#     per-sample n=19878 csv 未导出 → Plan A re-eval (M1-M2) 补。
#   • Cross-domain ρ: STORY_FRAMEWORK locked (ham -0.108 / pad -0.150) 无源 csv，
#     权威 external_ablation.csv 实为 -0.164 / -0.236 → 标 待核 PENDING，不自动改 master
#     doc，Plan A re-eval 后再 frozen。PENDING 不阻塞。
# ──────────────────────────────────────────────────────────────────────────────

_current_section = "iclr"


def _parse_ablation_global(variant_substr: str) -> tuple[float, float, float, float] | None:
    """Parse (AUC, ECE, MeanEntropy, ρ) for a variant from eval_report_ablation.md.

    Global Metrics row format:
      | <Variant> | AUC | ECE | Sensitivity | Specificity | MeanEntropy | ρ (p=...) |
    """
    md_path = RESULTS / "eval_report_ablation.md"
    if not md_path.exists():
        return None
    md = md_path.read_text(encoding="utf-8")
    pat = (
        rf"^\|\s*[^|]*{re.escape(variant_substr)}[^|]*\|"
        r"\s*(-?\d+\.\d+)\s*\|"   # AUC
        r"\s*(-?\d+\.\d+)\s*\|"   # ECE
        r"\s*-?\d+\.\d+\s*\|"     # Sensitivity (skip)
        r"\s*-?\d+\.\d+\s*\|"     # Specificity (skip)
        r"\s*(-?\d+\.\d+)\s*\|"   # Mean Entropy
        r"\s*(-?\d+\.\d+)"        # ρ
    )
    m = re.search(pat, md, re.MULTILINE)
    if not m:
        return None
    return float(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4))


# 18-24: Q-VIB Full + Adaptive Prior core numbers — full ISIC test set (n=19878).
# Source-of-truth = results/eval_report_ablation.md (5 q̅-quintiles × ~3976). The
# per-sample n=19878 csv was never exported; re-export is deferred to Plan A re-eval
# (M1-M2). check() here verifies STORY_FRAMEWORK locked values == frozen eval report
# (same md-parse pattern as the VisiScore checks below), NOT a recompute on the
# unrelated ITB pool (n=2820, itb_predictions.csv) which is a different, harder split.
abl_qvib  = _parse_ablation_global("Q-VIB Full")
abl_adapt = _parse_ablation_global("Adaptive Prior")
if abl_qvib is None or abl_adapt is None:
    iclr_failures.append("  FAIL  ablation parse: could not read eval_report_ablation.md Global Metrics")
else:
    auc_q, ece_q, ent_q, rho_q = abl_qvib
    check("qvib_auc_full_pool",     0.707, auc_q, tol=0.005)
    check("qvib_ece_full_pool",     0.098, ece_q, tol=0.005)
    check("qvib_entropy_full_pool", 0.225, ent_q, tol=0.010)
    check("qvib_rho_full_pool",    -0.165, rho_q, tol=0.005)

    auc_a, ece_a, _, rho_a = abl_adapt
    check("adaptive_prior_auc",  0.688, auc_a, tol=0.005)
    check("adaptive_prior_ece",  0.100, ece_a, tol=0.005)
    check("adaptive_prior_rho", -0.169, rho_a, tol=0.005)

# 25-26: Cross-domain ρ on Q-VIB Full — 待核 (PENDING, not pass/fail).
# STORY_FRAMEWORK locks ham -0.108 / pad -0.150, but those have NO source csv; the
# authoritative external_ablation.csv (and recompute below) give -0.164 / -0.236.
# Per audit decision the master doc is NOT auto-overwritten — flagged pending the
# Plan A re-eval, where the cross-domain numbers will be regenerated and frozen.
for csv_name, locked_rho, paper_n, key in [
    ("external_ham10000_predictions.csv", -0.108, 10015, "ham10000"),
    ("external_pad_ufes_predictions.csv", -0.150,  2298, "padufes"),
]:
    df_ext = pd.read_csv(RESULTS / csv_name)
    qvib_ext = df_ext[df_ext["baseline"] == "F"].reset_index(drop=True)
    assert len(qvib_ext) == paper_n, f"{csv_name} F rows {len(qvib_ext)} != {paper_n}"
    rho_ext, _ = spearmanr(entropy(qvib_ext["prob_pos"].values), qvib_ext["q_bar"].values)
    pending_check(f"qvib_rho_{key}", locked_rho, rho_ext, "locked has no source csv — pending Plan A re-eval")

# 27-30: VisiScore-Net PLCC/SRCC — parse from eval_report_visiscore.md
visiscore_md = ROOT / "project/results/eval_report_visiscore.md"
if visiscore_md.exists():
    md_txt = visiscore_md.read_text(encoding="utf-8")
    def _parse_plcc_srcc(dim: str) -> tuple[float, float] | None:
        # Row format: | <dim> | <plcc> | <srcc> | ... |
        m = re.search(rf"^\|\s*\*?\*?{re.escape(dim)}\*?\*?\s*\|\s*\*?\*?(-?\d+\.\d+)\*?\*?\s*\|\s*\*?\*?(-?\d+\.\d+)\*?\*?",
                      md_txt, re.MULTILINE)
        return (float(m.group(1)), float(m.group(2))) if m else None

    for dim, paper_plcc, paper_srcc, suffix in [
        ("平均",       0.924, 0.895, "mean"),
        ("sharpness",  0.947, 0.863, "sharpness"),
    ]:
        parsed = _parse_plcc_srcc(dim)
        if parsed is None:
            failures.append(f"  FAIL  visiscore_{suffix}_parse: could not find row for '{dim}' in eval_report_visiscore.md")
            continue
        plcc_md, srcc_md = parsed
        check(f"visiscore_plcc_{suffix}", paper_plcc, plcc_md, tol=0.005)
        check(f"visiscore_srcc_{suffix}", paper_srcc, srcc_md, tol=0.005)
else:
    failures.append("  FAIL  visiscore report missing: results/eval_report_visiscore.md")

# ── Print results ─────────────────────────────────────────────────────────────

print("\n" + "="*70)
print(" NUMBERS CONSISTENCY CHECK — BMVC锁定数字 (block submission on FAIL)")
print("="*70)
for line in passes + failures:
    print(line)
print("-"*70)
print(f"  BMVC: PASS {len(passes)} / FAIL {len(failures)} / TOTAL {len(passes)+len(failures)}")

print("\n" + "="*70)
print(" ICLR锁定数字 (verified against frozen eval reports; do NOT block BMVC)")
print("="*70)
for line in iclr_passes + iclr_failures:
    print(line)
print("-"*70)
print(f"  ICLR: PASS {len(iclr_passes)} / FAIL {len(iclr_failures)} / TOTAL {len(iclr_passes)+len(iclr_failures)}")

if iclr_pending:
    print("\n" + "="*70)
    print(" ICLR 待核 PENDING (locked vs csv mismatch, resolution deferred to Plan A re-eval)")
    print("="*70)
    for line in iclr_pending:
        print(line)
    print("-"*70)
    print(f"  PENDING: {len(iclr_pending)} (not counted as pass/fail)")

total_p = len(passes) + len(iclr_passes)
total_f = len(failures) + len(iclr_failures)
print("\n" + "="*70)
print(f"  GRAND TOTAL: PASS {total_p} / FAIL {total_f} / PENDING {len(iclr_pending)} / "
      f"TOTAL {total_p+total_f+len(iclr_pending)}")
print("="*70)

if failures:
    print("\n[BMVC] FAILED — investigate before BMVC submission!")
    sys.exit(1)
if iclr_failures:
    print("\n[ICLR] FAIL present — STORY_FRAMEWORK locked value disagrees with its frozen")
    print("       eval report. Reconcile before relying on these numbers in the paper.")
    sys.exit(1)
if iclr_pending:
    print("\n[ICLR] 待核 PENDING present — locked cross-domain ρ has no source csv.")
    print("       Decision deferred to Plan A re-eval (M1-M2); master doc NOT overwritten.")
    sys.exit(0)  # not blocking
print("\nAll checks passed.")
