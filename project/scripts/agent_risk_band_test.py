"""Theorem 2 SalvageRate band test: agent vs direct risk by quality band.

Tests whether the closed-loop agent (Theorem 2, §5.2) reduces diagnostic risk
relative to direct (no-agent) classification, and whether the risk reduction is
concentrated in the theoretical operating window [tau_enh, tau_high].

ACCEPTANCE thresholds (ACCEPTANCE_CRITERIA.md L4, E5):
    moderate band: qbar in [0.35, 0.50]   -> agent should improve (Delta > 0)
    severe band:   qbar < 0.25             -> agent routes to retake / referral

Data sources (both read-only, no GPU):
    1. e5_salvage_v6_persample.csv   -- enhancement channel per-sample
       cols: sev, target, qbar_route, correct_deg, correct_enh, qband
       correct_deg = direct baseline (no enhancement)
       correct_enh = agent (with enhancement)
    2. itb_agent_eval.csv            -- retake channel per-sample
       cols: subset, isic_id, ..., initial_qbar, final_qbar, final_prob,
             retake_count, retake_triggered, target

Output:
    results/agent_vs_direct_risk.csv

Bootstrap CI uses pure numpy (not scipy.stats) to avoid Windows OMP Error #15.

Usage:
    cd D:/YJ-Agent/project
    python scripts/agent_risk_band_test.py
    python scripts/agent_risk_band_test.py --n_boot 2000 --seed 42
    python scripts/agent_risk_band_test.py --dry-run   # smoke check, no output written
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

# ── Paths ──────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent  # D:/YJ-Agent/project
SALVAGE_CSV = ROOT / "results/e5_salvage_v6_persample.csv"
AGENT_CSV = ROOT / "results/itb_agent_eval.csv"
OUT_CSV = ROOT / "results/agent_vs_direct_risk.csv"

# ── ACCEPTANCE thresholds (ACCEPTANCE_CRITERIA.md, do NOT change) ─────────────
TAU_ENH = 0.35    # lower bound of moderate band
TAU_HIGH = 0.50   # upper bound of moderate band (Thm 2: Delta>0 iff qbar in [tau_enh, tau_high])
TAU_SEVERE = 0.25  # severe threshold (qbar < tau_severe -> expected low salvage / high risk)

N_BOOT_DEFAULT = 2000
SEED_DEFAULT = 42
CI_LEVEL = 0.95


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--salvage-csv", default=str(SALVAGE_CSV),
                   help="Path to e5_salvage_v6_persample.csv")
    p.add_argument("--agent-csv", default=str(AGENT_CSV),
                   help="Path to itb_agent_eval.csv")
    p.add_argument("--out", default=str(OUT_CSV),
                   help="Output CSV path")
    p.add_argument("--n_boot", type=int, default=N_BOOT_DEFAULT,
                   help="Bootstrap resamples (default: 2000)")
    p.add_argument("--seed", type=int, default=SEED_DEFAULT,
                   help="RNG seed for bootstrap")
    p.add_argument("--dry-run", action="store_true",
                   help="Load and validate inputs only; do not write output CSV")
    return p.parse_args()


# ── Pure-numpy bootstrap CI (no scipy.stats; Windows OMP safe) ────────────────
def bootstrap_ci_diff(
    stat_a: np.ndarray,
    stat_b: np.ndarray,
    n_boot: int,
    rng: np.random.Generator,
    ci: float = CI_LEVEL,
) -> tuple[float, float, float]:
    """Percentile bootstrap CI for mean(stat_a) - mean(stat_b).

    Parameters
    ----------
    stat_a, stat_b : 1-D arrays of per-sample scores (0/1 for accuracy/risk)
    Returns (point_diff, ci_lo, ci_hi)
    """
    n_a, n_b = len(stat_a), len(stat_b)
    diffs = np.empty(n_boot, dtype=np.float64)
    for i in range(n_boot):
        diffs[i] = (
            rng.choice(stat_a, size=n_a, replace=True).mean()
            - rng.choice(stat_b, size=n_b, replace=True).mean()
        )
    alpha = 1.0 - ci
    lo = float(np.percentile(diffs, 100 * alpha / 2))
    hi = float(np.percentile(diffs, 100 * (1 - alpha / 2)))
    point = float(stat_a.mean() - stat_b.mean())
    return point, lo, hi


def bootstrap_ci_mean(
    stat: np.ndarray,
    n_boot: int,
    rng: np.random.Generator,
    ci: float = CI_LEVEL,
) -> tuple[float, float, float]:
    """Percentile bootstrap CI for mean(stat)."""
    n = len(stat)
    boot_means = np.array([rng.choice(stat, size=n, replace=True).mean() for _ in range(n_boot)])
    alpha = 1.0 - ci
    lo = float(np.percentile(boot_means, 100 * alpha / 2))
    hi = float(np.percentile(boot_means, 100 * (1 - alpha / 2)))
    return float(stat.mean()), lo, hi


# ── Channel 1: enhancement channel (salvage per-sample) ───────────────────────
def run_enhancement_band_test(
    df_salv: pd.DataFrame,
    n_boot: int,
    rng: np.random.Generator,
) -> list[dict]:
    """Test risk reduction by enhancement agent across qbar bands.

    direct_risk  = 1 - correct_deg   (no enhancement)
    agent_risk   = 1 - correct_enh   (with enhancement)
    risk_delta   = agent_risk - direct_risk  (negative = agent reduces risk)

    Bands (on qbar_route):
        severe:   qbar < TAU_SEVERE
        moderate: TAU_ENH <= qbar <= TAU_HIGH   [Thm 2 operating window]
        high:     qbar > TAU_HIGH
        all:      whole dataset
    """
    qbar = df_salv["qbar_route"].values
    correct_deg = df_salv["correct_deg"].values.astype(float)
    correct_enh = df_salv["correct_enh"].values.astype(float)
    target = df_salv["target"].values

    bands = {
        "severe":   qbar < TAU_SEVERE,
        "moderate": (qbar >= TAU_ENH) & (qbar <= TAU_HIGH),
        "high":     qbar > TAU_HIGH,
        "all":      np.ones(len(qbar), dtype=bool),
    }

    rows = []
    for band_name, mask in bands.items():
        if mask.sum() == 0:
            continue
        cg = correct_deg[mask]
        ce = correct_enh[mask]
        tgt = target[mask]
        n = int(mask.sum())
        n_pos = int(tgt.sum())

        direct_risk = 1.0 - cg
        agent_risk = 1.0 - ce

        # SalvageRate: of deg-wrong cases, fraction that enh fixes
        deg_wrong = cg == 0
        salvage_rate = float(ce[deg_wrong].mean()) if deg_wrong.sum() > 0 else float("nan")
        salvage_n = int(deg_wrong.sum())

        # DamageRate: of deg-correct cases, fraction that enh breaks
        deg_right = cg == 1
        damage_rate = float(1.0 - ce[deg_right].mean()) if deg_right.sum() > 0 else float("nan")
        damage_n = int(deg_right.sum())

        # Bootstrap CI for risk_delta = mean(agent_risk) - mean(direct_risk)
        # Note: these are paired samples (same image), so we bootstrap paired diffs
        paired_diff = agent_risk - direct_risk  # per-sample risk change
        risk_delta_pt, rd_lo, rd_hi = bootstrap_ci_mean(paired_diff, n_boot, rng)
        ci_excludes_zero = (rd_lo > 0) or (rd_hi < 0)

        rows.append({
            "channel": "enhancement",
            "band": band_name,
            "tau_lo": TAU_ENH if band_name == "moderate" else (TAU_SEVERE if band_name == "severe" else float("nan")),
            "tau_hi": TAU_HIGH if band_name == "moderate" else (TAU_SEVERE if band_name == "severe" else float("nan")),
            "n": n,
            "n_pos": n_pos,
            "direct_acc": float(cg.mean()),
            "agent_acc": float(ce.mean()),
            "direct_risk": float(direct_risk.mean()),
            "agent_risk": float(agent_risk.mean()),
            "risk_delta": risk_delta_pt,       # agent_risk - direct_risk (neg = better)
            "risk_delta_ci_lo": rd_lo,
            "risk_delta_ci_hi": rd_hi,
            "ci_excludes_zero": ci_excludes_zero,
            "salvage_rate": salvage_rate,
            "salvage_n": salvage_n,
            "damage_rate": damage_rate,
            "damage_n": damage_n,
            # ACCEPTANCE thresholds for this band
            "acceptance_threshold": ">55%" if band_name == "moderate" else ("<25%" if band_name == "severe" else "N/A"),
            # E5 judgment: moderate salvage>55% PASS, severe is an E5 nuance (see ACCEPTANCE note)
            "salvage_acceptance": _judge_salvage(band_name, salvage_rate),
        })

    return rows


def _judge_salvage(band: str, rate: float) -> str:
    """Apply ACCEPTANCE_CRITERIA E5 judgement to salvage rate.

    NOTE from ACCEPTANCE (E5 nuance): 'old severe salvage<25% criterion conflicts
    with this measurement method; high severe salvage != unsafe because salvage
    counts overall misclassification correction not melanoma-specific miss.'
    So severe <25% is flagged but annotated with the nuance.
    """
    if np.isnan(rate):
        return "N/A (no wrong cases)"
    if band == "moderate":
        return "PASS" if rate > 0.55 else "FAIL"
    if band == "severe":
        # Per ACCEPTANCE nuance: the <25% criterion conflicts with this measurement.
        # Flag but do not hard-judge.
        return f"NUANCE: {rate:.3f} (see ACCEPTANCE E5 note; criterion conflicts with per-sample salvage method)"
    return "N/A"


# ── Channel 2: retake channel (itb_agent_eval) ────────────────────────────────
def run_retake_band_test(
    df_agent: pd.DataFrame,
    n_boot: int,
    rng: np.random.Generator,
) -> list[dict]:
    """Test agent retake behaviour by initial_qbar band.

    Since direct_prob is not available in itb_agent_eval.csv, we characterise
    the retake channel by:
        - retake_rate: fraction of cases where agent triggered retake
        - agent_risk:  1 - (final_pred == target)  using final_prob > 0.5 threshold
        - quality_gain: mean(final_qbar - initial_qbar) for retake cases

    For Theorem 2 P1: moderate band should have high retake_rate (agent intervenes).
    For Theorem 2 P3: severe band should have high retake_rate too (policy routes away).
    Bootstrap CI on retake_rate and agent_risk.

    NOTE: without direct_prob, agent vs direct risk delta cannot be computed here.
    The enhancement channel (salvage CSV) provides the direct risk comparison.
    """
    qbar = df_agent["initial_qbar"].values
    final_prob = df_agent["final_prob"].values
    target = df_agent["target"].values
    retake_triggered = df_agent["retake_triggered"].values.astype(float)
    quality_gain = (df_agent["final_qbar"] - df_agent["initial_qbar"]).values

    final_pred = (final_prob > 0.5).astype(float)
    agent_correct = (final_pred == target).astype(float)

    bands = {
        "severe":   qbar < TAU_SEVERE,
        "moderate": (qbar >= TAU_ENH) & (qbar <= TAU_HIGH),
        "high":     qbar > TAU_HIGH,
        "all":      np.ones(len(qbar), dtype=bool),
    }

    rows = []
    for band_name, mask in bands.items():
        if mask.sum() == 0:
            continue
        rt = retake_triggered[mask]
        ac = agent_correct[mask]
        qg = quality_gain[mask]
        tgt = target[mask]
        n = int(mask.sum())
        n_pos = int(tgt.sum())

        retake_rate_pt, rr_lo, rr_hi = bootstrap_ci_mean(rt, n_boot, rng)
        agent_risk_pt, ar_lo, ar_hi = bootstrap_ci_mean(1.0 - ac, n_boot, rng)

        # Quality gain for retake cases only
        retake_cases = rt == 1
        qg_retake_mean = float(qg[retake_cases].mean()) if retake_cases.sum() > 0 else float("nan")

        rows.append({
            "channel": "retake",
            "band": band_name,
            "tau_lo": TAU_ENH if band_name == "moderate" else (TAU_SEVERE if band_name == "severe" else float("nan")),
            "tau_hi": TAU_HIGH if band_name == "moderate" else (TAU_SEVERE if band_name == "severe" else float("nan")),
            "n": n,
            "n_pos": n_pos,
            "retake_rate": retake_rate_pt,
            "retake_rate_ci_lo": rr_lo,
            "retake_rate_ci_hi": rr_hi,
            "agent_risk": agent_risk_pt,
            "agent_risk_ci_lo": ar_lo,
            "agent_risk_ci_hi": ar_hi,
            "quality_gain_retake_cases": qg_retake_mean,
            "n_retake": int(retake_cases.sum()),
            # Thm 2 P1: moderate retake_rate should be high (agent intervenes in operating window)
            # Thm 2 P3: severe retake_rate should be 100% (agent refuses/routes away)
            "thm2_expectation": (
                "P1: high retake_rate expected" if band_name == "moderate"
                else "P3: retake_rate~1.0 expected" if band_name == "severe"
                else "N/A"
            ),
        })

    return rows


def main() -> None:
    args = parse_args()
    rng = np.random.default_rng(args.seed)

    # ── Load inputs ──────────────────────────────────────────────────────────
    salv_path = Path(args.salvage_csv)
    agent_path = Path(args.agent_csv)

    if not salv_path.exists():
        raise FileNotFoundError(f"Salvage CSV not found: {salv_path}")
    if not agent_path.exists():
        raise FileNotFoundError(f"Agent eval CSV not found: {agent_path}")

    df_salv = pd.read_csv(salv_path)
    df_agent = pd.read_csv(agent_path)

    print(f"Loaded salvage CSV: {len(df_salv)} rows from {salv_path.name}")
    print(f"Loaded agent CSV:   {len(df_agent)} rows from {agent_path.name}")

    # Basic validation
    required_salv = {"qbar_route", "correct_deg", "correct_enh", "target"}
    required_agent = {"initial_qbar", "final_qbar", "final_prob", "target", "retake_triggered"}
    missing_s = required_salv - set(df_salv.columns)
    missing_a = required_agent - set(df_agent.columns)
    if missing_s:
        raise ValueError(f"salvage CSV missing columns: {missing_s}")
    if missing_a:
        raise ValueError(f"agent CSV missing columns: {missing_a}")

    print(f"\nACCEPTANCE thresholds: moderate=[{TAU_ENH},{TAU_HIGH}], severe<{TAU_SEVERE}")
    print(f"Bootstrap: n_boot={args.n_boot}, seed={args.seed}, CI={CI_LEVEL*100:.0f}%")

    if args.dry_run:
        print("\n[dry-run] Input validation passed. No output written.")
        return

    # ── Run band tests ────────────────────────────────────────────────────────
    print("\n=== Enhancement channel (e5_salvage_v6_persample) ===")
    enh_rows = run_enhancement_band_test(df_salv, args.n_boot, rng)
    for r in enh_rows:
        ci_tag = "CI_EXCLUDES_0" if r["ci_excludes_zero"] else "CI_CONTAINS_0"
        print(
            f"  [{r['band']:8s}] n={r['n']:5d}  "
            f"direct_risk={r['direct_risk']:.3f}  agent_risk={r['agent_risk']:.3f}  "
            f"delta={r['risk_delta']:+.3f} [{r['risk_delta_ci_lo']:+.3f},{r['risk_delta_ci_hi']:+.3f}] "
            f"({ci_tag})  "
            f"salvage={r['salvage_rate']:.3f}  "
            f"acceptance={r['salvage_acceptance']}"
        )

    print("\n=== Retake channel (itb_agent_eval) ===")
    ret_rows = run_retake_band_test(df_agent, args.n_boot, rng)
    for r in ret_rows:
        print(
            f"  [{r['band']:8s}] n={r['n']:4d}  "
            f"retake_rate={r['retake_rate']:.3f} [{r['retake_rate_ci_lo']:.3f},{r['retake_rate_ci_hi']:.3f}]  "
            f"agent_risk={r['agent_risk']:.3f} [{r['agent_risk_ci_lo']:.3f},{r['agent_risk_ci_hi']:.3f}]  "
            f"| {r['thm2_expectation']}"
        )

    # ── Combine and write ────────────────────────────────────────────────────
    all_rows = enh_rows + ret_rows
    df_out = pd.DataFrame(all_rows)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df_out.to_csv(out_path, index=False)
    print(f"\nOutput: {out_path}  ({len(df_out)} rows)")

    # ── Summary judgment ─────────────────────────────────────────────────────
    mod_enh = next((r for r in enh_rows if r["band"] == "moderate"), None)
    sev_enh = next((r for r in enh_rows if r["band"] == "severe"), None)
    mod_ret = next((r for r in ret_rows if r["band"] == "moderate"), None)
    sev_ret = next((r for r in ret_rows if r["band"] == "severe"), None)

    print("\n=== Theorem 2 band test summary ===")
    if mod_enh:
        print(
            f"  [Enh-moderate] SalvageRate={mod_enh['salvage_rate']:.3f}  "
            f"risk_delta={mod_enh['risk_delta']:+.3f} [{mod_enh['risk_delta_ci_lo']:+.3f},{mod_enh['risk_delta_ci_hi']:+.3f}]  "
            f"acceptance={mod_enh['salvage_acceptance']}"
        )
    if sev_enh:
        print(
            f"  [Enh-severe]   SalvageRate={sev_enh['salvage_rate']:.3f}  "
            f"acceptance={sev_enh['salvage_acceptance']}"
        )
    if mod_ret:
        print(
            f"  [Ret-moderate] retake_rate={mod_ret['retake_rate']:.3f} [{mod_ret['retake_rate_ci_lo']:.3f},{mod_ret['retake_rate_ci_hi']:.3f}]  "
            f"expectation={mod_ret['thm2_expectation']}"
        )
    if sev_ret:
        print(
            f"  [Ret-severe]   retake_rate={sev_ret['retake_rate']:.3f} [{sev_ret['retake_rate_ci_lo']:.3f},{sev_ret['retake_rate_ci_hi']:.3f}]  "
            f"expectation={sev_ret['thm2_expectation']}"
        )
    print(
        "\n  NOTE: enhancement channel uses e5_salvage (direct=no-enh, agent=with-enh). "
        "Retake channel uses itb_agent_eval (agent final_prob only; no direct_prob available "
        "in this CSV—risk delta for retake channel requires Plan A Stage 3 re-export)."
    )


if __name__ == "__main__":
    main()
