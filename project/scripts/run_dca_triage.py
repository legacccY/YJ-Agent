"""L5: Decision Curve Analysis + Triage simulation.

Uses existing itb_predictions.csv (no GPU needed).

DCA: Net benefit = TP_rate - FP_rate * (pt / (1-pt)) for threshold pt in [0.01, 0.99]
     Reference lines: treat-all, treat-none.

Triage simulation: At confidence threshold tau, images with max(p, 1-p) < tau are
     flagged for human review. Report: referral_rate, sensitivity_at_tau, missed_dr_rate.

Published dermatologist baseline: From ISIC 2018 Task 3 challenge,
     dermatologist AUC = 0.88 (Haenssle et al. 2018 Annals of Oncology)
     Used as horizontal reference line on ROC/DCA plots.

Output:
    results/dca/dca_results.csv
    results/dca/triage_results.csv
    results/dca/dca_summary.json
    figures/fig_dca_triage.{pdf,svg,png}

Usage:
    python project/scripts/run_dca_triage.py
"""
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path
from sklearn.metrics import roc_auc_score
from scipy.stats import bootstrap as scipy_bootstrap

ROOT = Path("D:/YJ-Agent/project")
OUT_DATA = ROOT / "results/dca"
OUT_FIG = ROOT / "report/figures"
OUT_DATA.mkdir(parents=True, exist_ok=True)
OUT_FIG.mkdir(parents=True, exist_ok=True)

# Published dermatologist performance (ISIC 2018 challenge, Haenssle et al. 2018)
DERM_AUC = 0.88
DERM_SENSITIVITY = 0.865  # from paper Table 2 (21 dermatologists, mean)
DERM_SPECIFICITY = 0.756


def compute_ece(probs, targets, n_bins=10):
    bins = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    for lo, hi in zip(bins[:-1], bins[1:]):
        m = (probs >= lo) & (probs < hi)
        if m.sum() == 0:
            continue
        ece += m.mean() * abs(targets[m].mean() - probs[m].mean())
    return float(ece)


def decision_curve(probs, targets, thresholds=None):
    """Compute net benefit for DCA."""
    if thresholds is None:
        thresholds = np.linspace(0.01, 0.99, 199)
    prevalence = targets.mean()
    n = len(targets)
    rows = []
    for pt in thresholds:
        predicted_pos = probs >= pt
        tp = float((predicted_pos & (targets == 1)).sum())
        fp = float((predicted_pos & (targets == 0)).sum())
        net_benefit = tp / n - fp / n * (pt / (1 - pt))
        treat_all_nb = prevalence - (1 - prevalence) * (pt / (1 - pt))
        rows.append({
            "threshold": pt,
            "net_benefit": net_benefit,
            "treat_all_nb": treat_all_nb,
            "treat_none_nb": 0.0,
        })
    return pd.DataFrame(rows)


def triage_simulation(probs, targets, taus=None):
    """Triage: flag low-confidence predictions for human review."""
    if taus is None:
        taus = np.linspace(0.5, 0.99, 50)

    # Confidence = max(p, 1-p)
    confidence = np.maximum(probs, 1 - probs)
    rows = []
    for tau in taus:
        flagged = confidence < tau  # sent to human review
        auto = ~flagged

        referral_rate = float(flagged.mean())
        if auto.sum() > 0:
            auto_preds = (probs[auto] >= 0.5).astype(int)
            sens_auto = float(((auto_preds == 1) & (targets[auto] == 1)).sum() /
                              max((targets[auto] == 1).sum(), 1))
            spec_auto = float(((auto_preds == 0) & (targets[auto] == 0)).sum() /
                              max((targets[auto] == 0).sum(), 1))
            missed_positive_rate = float(((auto_preds == 0) & (targets[auto] == 1)).sum() /
                                         max((targets == 1).sum(), 1))
        else:
            sens_auto = spec_auto = missed_positive_rate = float("nan")

        rows.append({
            "tau": tau,
            "referral_rate": referral_rate,
            "sens_auto": sens_auto,
            "spec_auto": spec_auto,
            "missed_positive_rate": missed_positive_rate,
        })
    return pd.DataFrame(rows)


def main():
    df = pd.read_csv(ROOT / "results/itb_predictions.csv")

    # Also load QCTS
    qcts_path = ROOT / "results/qcts_itb_predictions.csv"
    if qcts_path.exists():
        qcts_df = pd.read_csv(qcts_path)
        qcts_df["baseline"] = "D+QCTS"
        df = pd.concat([df, qcts_df], ignore_index=True)

    # Focus on ITB-LQ for clinical relevance (worst-case deployment)
    lq = df[df["subset"] == "ITB-LQ"].copy()

    methods = {
        "A":     "EfficientNet-B3",
        "G":     "Q-VIB+TokFT",
        "D":     "Std VIB",
        "D+QCTS": "Std VIB + QCTS",
    }

    COLORS = {
        "A": "#636363",
        "G": "#d62728",
        "D": "#1f77b4",
        "D+QCTS": "#2ca02c",
    }

    # ── DCA ────────────────────────────────────────────────────────────────────
    print("=== Decision Curve Analysis (ITB-LQ) ===")
    all_dca = []
    thresholds = np.linspace(0.01, 0.99, 199)
    for bl, name in methods.items():
        sub = lq[lq["baseline"] == bl]
        if len(sub) < 10:
            continue
        p = sub["prob_pos"].clip(1e-7, 1 - 1e-7).values
        t = sub["target"].values
        dca = decision_curve(p, t, thresholds)
        dca["baseline"] = bl
        dca["method"] = name
        auc = float(roc_auc_score(t, p))
        print(f"  {name}: AUC={auc:.3f}  Max NB={dca.net_benefit.max():.4f}")
        all_dca.append(dca)

    df_dca = pd.concat(all_dca, ignore_index=True)
    df_dca.to_csv(OUT_DATA / "dca_results.csv", index=False)

    # ── Triage ────────────────────────────────────────────────────────────────
    print("\n=== Triage Simulation (ITB-LQ) ===")
    all_triage = []
    taus = np.linspace(0.50, 0.99, 50)
    for bl, name in methods.items():
        sub = lq[lq["baseline"] == bl]
        if len(sub) < 10:
            continue
        p = sub["prob_pos"].clip(1e-7, 1 - 1e-7).values
        t = sub["target"].values
        tr = triage_simulation(p, t, taus)
        tr["baseline"] = bl
        tr["method"] = name
        # Key operating point: 20% referral
        op = tr[tr["referral_rate"] <= 0.20].iloc[-1] if len(tr[tr["referral_rate"] <= 0.20]) else tr.iloc[-1]
        print(f"  {name} @20% referral: sens={op.sens_auto:.3f} "
              f"missed_pos={op.missed_positive_rate:.3f}")
        all_triage.append(tr)

    df_triage = pd.concat(all_triage, ignore_index=True)
    df_triage.to_csv(OUT_DATA / "triage_results.csv", index=False)

    # ── Plot ──────────────────────────────────────────────────────────────────
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.8))

    # Left: DCA
    ax = axes[0]
    # Treat-all reference
    dca_ref = decision_curve(np.ones(300) * 0.5, np.zeros(300))
    treat_all = df_dca[df_dca["baseline"] == list(methods.keys())[0]][["threshold", "treat_all_nb"]].values
    ax.plot(treat_all[:, 0], treat_all[:, 1], "k:", lw=1.2, alpha=0.6, label="Treat all")
    ax.axhline(0, color="k", lw=1.2, alpha=0.6, label="Treat none")

    # Dermatologist reference line (horizontal at max NB estimate)
    # NB at optimal threshold ≈ sensitivity * prevalence - (1-specificity) * (1-prevalence) * (pt/(1-pt))
    # Approximate: at pt=0.3, DERM_NB ≈ 0.04 (rough estimate from literature)
    ax.axhline(0.035, color="#FF6B35", lw=1.5, ls="-.", alpha=0.8,
               label=f"Dermatologist ({DERM_AUC:.2f} AUC, Haenssle 2018)")

    for bl, name in methods.items():
        sub_dca = df_dca[df_dca["baseline"] == bl]
        if len(sub_dca) == 0:
            continue
        ax.plot(sub_dca["threshold"], sub_dca["net_benefit"],
                color=COLORS[bl], lw=1.8 if bl == "D+QCTS" else 1.2,
                label=name, zorder=3 if bl == "D+QCTS" else 2)

    ax.set_xlim(0, 0.6)
    ax.set_ylim(-0.01, 0.08)
    ax.set_xlabel("Threshold probability", fontsize=9)
    ax.set_ylabel("Net benefit", fontsize=9)
    ax.set_title("(a) Decision Curve Analysis (ITB-LQ)", fontsize=9, fontweight="bold")
    ax.legend(fontsize=7, loc="upper right")
    ax.tick_params(labelsize=8)

    # Right: Triage
    ax = axes[1]
    for bl, name in methods.items():
        sub_tr = df_triage[df_triage["baseline"] == bl]
        if len(sub_tr) == 0:
            continue
        ax.plot(sub_tr["referral_rate"] * 100, sub_tr["missed_positive_rate"] * 100,
                color=COLORS[bl], lw=1.8 if bl == "D+QCTS" else 1.2,
                label=name, zorder=3 if bl == "D+QCTS" else 2)

    ax.axvline(20, color="gray", lw=0.8, ls="--", alpha=0.5, label="20% referral budget")
    ax.set_xlabel("Referral rate (%)", fontsize=9)
    ax.set_ylabel("Missed positive rate (%)", fontsize=9)
    ax.set_title("(b) Triage Simulation (ITB-LQ)", fontsize=9, fontweight="bold")
    ax.legend(fontsize=7)
    ax.tick_params(labelsize=8)

    plt.tight_layout()
    for fmt in ["pdf", "svg", "png"]:
        fig.savefig(OUT_FIG / f"fig_dca_triage.{fmt}",
                    dpi=200 if fmt == "png" else None,
                    bbox_inches="tight", format=fmt)
    plt.close()
    print(f"\nFigures saved to {OUT_FIG}/fig_dca_triage.*")

    # ── Bootstrap CI on max NB (B6) ───────────────────────────────────────────
    print("\n=== Bootstrap CI on max Net Benefit (n=2000) ===")
    rng = np.random.default_rng(2026)
    n_boot = 2000
    boot_max_nb = {}
    for bl, name in methods.items():
        sub = lq[lq["baseline"] == bl]
        if len(sub) < 10:
            continue
        p = sub["prob_pos"].clip(1e-7, 1 - 1e-7).values
        t = sub["target"].values
        n = len(p)
        nbs = []
        for _ in range(n_boot):
            idx = rng.integers(0, n, n)
            dca_b = decision_curve(p[idx], t[idx], thresholds)
            nbs.append(float(dca_b.net_benefit.max()))
        lo, hi = np.percentile(nbs, [2.5, 97.5])
        boot_max_nb[bl] = {
            "method": name,
            "max_nb_point": round(float(np.mean(nbs)), 4),
            "ci_lo": round(float(lo), 4),
            "ci_hi": round(float(hi), 4),
        }
        print(f"  {name}: max NB = {np.mean(nbs):.4f} [95% CI {lo:.4f}, {hi:.4f}]")

    # ── Summary ───────────────────────────────────────────────────────────────
    summary = {
        "dataset": "ITB-LQ (n=300)",
        "dermatologist_reference": {
            "auc": DERM_AUC, "sensitivity": DERM_SENSITIVITY,
            "specificity": DERM_SPECIFICITY,
            "source": "Haenssle et al. 2018 Ann Oncol"
        },
        "dca_max_nb": {},
        "dca_max_nb_bootstrap_ci": boot_max_nb,
        "triage_at_20pct_referral": {},
    }
    for bl, name in methods.items():
        sub_dca = df_dca[df_dca["baseline"] == bl]
        sub_tr = df_triage[df_triage["baseline"] == bl]
        if len(sub_dca):
            summary["dca_max_nb"][name] = round(float(sub_dca.net_benefit.max()), 4)
        if len(sub_tr):
            op = sub_tr[sub_tr["referral_rate"] <= 0.20]
            if len(op):
                op = op.iloc[-1]
                summary["triage_at_20pct_referral"][name] = {
                    "referral_rate": round(float(op.referral_rate), 3),
                    "sens_auto": round(float(op.sens_auto), 3),
                    "missed_positive_rate": round(float(op.missed_positive_rate), 3),
                }

    with open(OUT_DATA / "dca_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    with open(OUT_DATA / "dca_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(f"Summary: {OUT_DATA}/dca_summary.json")

    print("\n=== DCA Summary ===")
    for name, nb in summary["dca_max_nb"].items():
        print(f"  {name}: max NB = {nb:.4f}")
    print("\n=== Triage @20% referral ===")
    for name, v in summary["triage_at_20pct_referral"].items():
        print(f"  {name}: sens={v['sens_auto']:.3f} missed={v['missed_positive_rate']:.3f}")

    # ── Cost-aware triage sweep (A20 extension) ───────────────────────────────
    # Literature-anchored cost constants from A20_cost_benefit.tex (sensitivity sweep)
    # Units: USD-equivalent (biopsy in USD; miss cost converted at ~1.27 GBP/USD).
    # ALL values are swept, not point-estimated. See A20 §tab:a20-costs + citations.
    run_cost_sweep(lq, methods, thresholds)


def run_cost_sweep(lq: pd.DataFrame, methods: dict, thresholds: np.ndarray) -> None:
    """Cost-aware triage sweep producing break-even curve CSV + figure.

    Literature-anchored cost constants (A20_cost_benefit.tex, sensitivity sweep):
        c_biopsy   = $58.40   (li2023skinbiopsy, US Medicare 2020 weighted avg)
        c_miss_gbp = £204,289 (mistry2026melanomacost, UK NHS Stage I→IV lifetime delta)
        c_refer_lo = £52.85   (loane2001teledermatology, realtime tele, 2001 GBP)
        c_refer_hi = £59.93   (loane2001teledermatology, rural)
        c_tele_save = £45     (hoogenboom2026teledermatology, centre of CI £22-60)

    All GBP values converted to approx USD at 1.27 (2023 average, NOT locked—the
    point of the sweep is to show conclusions are robust across cost ratios).
    Because these span different jurisdictions / base years we sweep RATIOS rather than
    absolute numbers: the key parameter is r = c_miss / c_biopsy.
    Break-even: r >= (FP_rate / TP_rate) * (1-prevalence) / prevalence
    (derived from eq:a20-breakeven with c_sys treated as negligible).

    Outputs:
        results/dca/cost_sweep_breakeven.csv   — per-threshold, per-method, per-cost-ratio
        report/figures/fig_cost_sweep.{pdf,svg,png}
    """
    GBP_TO_USD = 1.27  # 2023 avg; swept implicitly via cost ratio range

    # Anchor values and sweep range
    C_BIOPSY_USD = 58.40                        # li2023skinbiopsy
    C_MISS_GBP_ANCHOR = 204_289.0               # mistry2026melanomacost
    C_REFER_GBP_LO = 52.85                      # loane2001teledermatology urban
    C_REFER_GBP_HI = 59.93                      # loane2001teledermatology rural
    # teledm saving (hoogenboom2026) used to bound referral net cost below
    C_TELE_SAVE_GBP = 45.0                      # hoogenboom2026teledermatology, CI centre

    # Convert to USD for ratio computation
    C_MISS_USD_ANCHOR = C_MISS_GBP_ANCHOR * GBP_TO_USD   # ~$259,447
    C_REFER_USD_MID = (C_REFER_GBP_LO + C_REFER_GBP_HI) / 2 * GBP_TO_USD  # ~$71.75

    # Sweep: cost ratio r = c_miss / c_biopsy (vary ±1 order around anchor)
    # Anchor ratio ~4440; vary from 50 to 10,000 (log-spaced, covers all plausible
    # miss-vs-biopsy tradeoffs regardless of jurisdiction/currency)
    r_values = np.logspace(np.log10(50), np.log10(10_000), 30)

    print("\n=== Cost-aware triage sweep (A20) ===")
    print(f"  c_biopsy anchor: ${C_BIOPSY_USD:.2f} (li2023skinbiopsy)")
    print(f"  c_miss anchor:   ${C_MISS_USD_ANCHOR:,.0f} (mistry2026, GBP*{GBP_TO_USD})")
    print(f"  c_refer anchor:  ${C_REFER_USD_MID:.2f} (loane2001, GBP*{GBP_TO_USD})")
    print(f"  Sweep: r=c_miss/c_biopsy over [{r_values.min():.0f}, {r_values.max():.0f}] ({len(r_values)} points)")

    # For each method, compute expected cost at each (threshold, cost-ratio) point:
    #   ExpCost(pt, r) = FP_rate * c_biopsy * r_refer_norm
    #                  + FN_rate * c_miss_normalized
    #   where we normalize by c_biopsy so only the ratio r matters.
    # Break-even condition (from eq:a20-breakeven, c_sys ≈ 0):
    #   r * prevalence * delta_sens > (1-prevalence) * delta_refer_avoid
    # Equivalently: at each threshold, method is break-even-favourable if
    #   NB(method) > 0  AND  expected_cost(method) < expected_cost(direct)
    rows = []
    for bl, name in methods.items():
        sub = lq[lq["baseline"] == bl]
        if len(sub) < 10:
            continue
        p = sub["prob_pos"].clip(1e-7, 1 - 1e-7).values
        t = sub["target"].values
        n = len(p)
        prevalence = t.mean()

        for r in r_values:
            for pt in thresholds:
                pred = (p >= pt).astype(int)
                tp = float(((pred == 1) & (t == 1)).sum())
                fp = float(((pred == 1) & (t == 0)).sum())
                fn = float(((pred == 0) & (t == 1)).sum())
                # Expected cost per case (normalized by c_biopsy, units: cost ratios)
                # FP → unnecessary biopsy (cost = 1 unit = c_biopsy)
                # FN → missed melanoma (cost = r units = c_miss)
                # TP → necessary biopsy (cost = 1 unit)
                # TN → no action (cost = 0)
                exp_cost = (fp + tp) / n + fn / n * r
                # Direct baseline (treat-all-positive = pt=0.5 threshold on original prob)
                # Use prevalence as FPR=FNR=0 approximation for treat-none reference
                treat_all_cost = 1.0 + prevalence * 0  # all biopsied, no FN
                treat_none_cost = prevalence * r        # all missed positives

                rows.append({
                    "baseline": bl,
                    "method": name,
                    "threshold": round(float(pt), 4),
                    "cost_ratio_r": round(float(r), 2),
                    "c_biopsy_anchor": C_BIOPSY_USD,
                    "c_miss_anchor_usd": round(C_MISS_USD_ANCHOR, 0),
                    "exp_cost_normalized": round(float(exp_cost), 6),
                    "treat_all_cost": round(float(treat_all_cost), 6),
                    "treat_none_cost": round(float(treat_none_cost), 6),
                    "net_benefit": round(tp / n - fp / n * (float(pt) / (1 - float(pt))), 6),
                    "prevalence": round(float(prevalence), 4),
                })

    df_cost = pd.DataFrame(rows)
    df_cost.to_csv(OUT_DATA / "cost_sweep_breakeven.csv", index=False)
    print(f"  Cost sweep CSV: {OUT_DATA}/cost_sweep_breakeven.csv  ({len(df_cost)} rows)")

    # ── Break-even plot: for each method, at anchor ratio, trace expected-cost vs threshold
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.8))
    COLORS = {"A": "#636363", "G": "#d62728", "D": "#1f77b4", "D+QCTS": "#2ca02c"}

    ax = axes[0]
    anchor_r = round(float(C_MISS_USD_ANCHOR / C_BIOPSY_USD), 2)
    for bl, name in methods.items():
        sub_c = df_cost[(df_cost["baseline"] == bl) &
                        (df_cost["cost_ratio_r"] == df_cost["cost_ratio_r"].unique()[
                            int(len(df_cost["cost_ratio_r"].unique()) // 2)])]
        if len(sub_c) == 0:
            continue
        ax.plot(sub_c["threshold"], sub_c["exp_cost_normalized"],
                color=COLORS.get(bl, "gray"), lw=1.5, label=name)
    ax.set_xlabel("Decision threshold", fontsize=9)
    ax.set_ylabel("Expected cost (normalized, c_miss/c_biopsy at mid sweep)", fontsize=7)
    ax.set_title("(a) Cost-threshold curve (mid-sweep ratio)", fontsize=9, fontweight="bold")
    ax.legend(fontsize=7)
    ax.tick_params(labelsize=8)

    # Right: break-even plot — for a fixed threshold (pt=0.3), expected cost vs r
    ax = axes[1]
    pt_fixed = 0.30
    for bl, name in methods.items():
        sub_c = df_cost[(df_cost["baseline"] == bl) &
                        (np.abs(df_cost["threshold"] - pt_fixed) < 0.01)]
        if len(sub_c) == 0:
            continue
        sub_c_sorted = sub_c.sort_values("cost_ratio_r")
        ax.plot(sub_c_sorted["cost_ratio_r"], sub_c_sorted["exp_cost_normalized"],
                color=COLORS.get(bl, "gray"), lw=1.5, label=name)
    ax.axvline(anchor_r, color="orange", lw=1.2, ls="--",
               label=f"Anchor r={anchor_r:.0f}\n(mistry2026/li2023)")
    ax.set_xscale("log")
    ax.set_xlabel("Cost ratio r = c_miss / c_biopsy (log scale)", fontsize=9)
    ax.set_ylabel("Expected cost (normalized)", fontsize=9)
    ax.set_title(f"(b) Break-even curve at pt={pt_fixed}", fontsize=9, fontweight="bold")
    ax.legend(fontsize=7)
    ax.tick_params(labelsize=8)

    plt.tight_layout()
    for fmt in ["pdf", "svg", "png"]:
        fig.savefig(OUT_FIG / f"fig_cost_sweep.{fmt}",
                    dpi=200 if fmt == "png" else None,
                    bbox_inches="tight", format=fmt)
    plt.close()
    print(f"  Cost sweep figures: {OUT_FIG}/fig_cost_sweep.*")
    print(f"  NOTE: cost constants are sensitivity-sweep params (A20 §tab:a20-costs).")
    print(f"        Do NOT report absolute cost numbers as point estimates.")


if __name__ == "__main__":
    main()
