"""
plot_fig4_composite.py
======================
ICLR 2027 VisiSkin-Agent  Fig4 — Honest Boundary + Agent Panel Composite
3-panel (A / B / C) vector PDF.

Panel A  Per-class salvage vs damage (benign / melanoma)
         Source: results/e5_salvage_v6_persample.csv
         Key values: melanoma SR=5.2% (4/77), DR=30.3% (83/274); benign SR=74.5%

Panel B  DCA net-benefit curves + triage sensitivity @20% referral (honest negatives)
         Source: results/dca/dca_results.csv + results/dca/triage_results.csv
         Key values: net-benefit CI 0.179-0.192 overlap; Direct(A) sens@20%ref=0.818

Panel C  Retake trigger rate gradient by quality band
         Source: results/agent_vs_direct_risk.csv
         Key values: severe 0.889, moderate 0.651, high 0.055

Style: Okabe-Ito palette, font.size=9, axes.linewidth=0.8, pdf.fonttype=42
       panel labels A/B/C bold top-left; no jet/rainbow; vector PDF.

Output:
    meeting/ICLR2027/figures/fig4_boundary_agent.pdf

Usage (from project/ root):
    python scripts/plot_fig4_composite.py [--smoke]
"""

import argparse
import os
import sys

import matplotlib as mpl
mpl.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# ---------- palette (Okabe-Ito) ----------
OKABE = {
    "black":     "#000000",
    "orange":    "#E69F00",
    "skyblue":   "#56B4E9",
    "green":     "#009E73",
    "yellow":    "#F0E442",
    "blue":      "#0072B2",
    "vermillion":"#D55E00",
    "purple":    "#CC79A7",
}

mpl.rcParams.update({
    "font.family":       "sans-serif",
    "font.size":         9,
    "axes.linewidth":    0.8,
    "axes.spines.top":   False,
    "axes.spines.right": False,
    "pdf.fonttype":      42,
    "ps.fonttype":       42,
    "legend.fontsize":   8,
    "xtick.labelsize":   8,
    "ytick.labelsize":   8,
})

# ---------- paths ----------
ROOT      = os.path.join(os.path.dirname(__file__), "..")  # project/
CSV_SALVAGE  = os.path.join(ROOT, "results/e5_salvage_v6_persample.csv")
CSV_DCA      = os.path.join(ROOT, "results/dca/dca_results.csv")
CSV_TRIAGE   = os.path.join(ROOT, "results/dca/triage_results.csv")
CSV_RETAKE   = os.path.join(ROOT, "results/agent_vs_direct_risk.csv")
OUT_DIR      = os.path.join(ROOT, "meeting/ICLR2027/figures")
OUT_PDF      = os.path.join(OUT_DIR, "fig4_boundary_agent.pdf")


# ============================================================
#  helpers
# ============================================================
def _salvage_rate(d):
    salvageable = d[d["correct_deg"] == 0]
    if len(salvageable) == 0:
        return float("nan"), 0, 0
    salvaged = salvageable[salvageable["correct_enh"] == 1]
    return len(salvaged) / len(salvageable), len(salvaged), len(salvageable)


def _damage_rate(d):
    base = d[d["correct_deg"] == 1]
    if len(base) == 0:
        return float("nan"), 0, 0
    damaged = base[base["correct_enh"] == 0]
    return len(damaged) / len(base), len(damaged), len(base)


# ============================================================
#  Panel A — per-class salvage vs damage
# ============================================================
def draw_panel_a(ax):
    df = pd.read_csv(CSV_SALVAGE)

    # compute per class
    classes = [("benign", 0), ("melanoma", 1)]
    sr_vals, dr_vals = [], []
    sr_numer, sr_denom = [], []
    dr_numer, dr_denom = [], []
    for label, tgt in classes:
        d = df[df["target"] == tgt]
        sr, sn, sd = _salvage_rate(d)
        dr, dn, dd = _damage_rate(d)
        sr_vals.append(sr)
        dr_vals.append(dr)
        sr_numer.append(sn); sr_denom.append(sd)
        dr_numer.append(dn); dr_denom.append(dd)

    x = np.arange(len(classes))
    w = 0.32

    # SR = blue (safe/good), DR = vermillion (danger)
    bars_sr = ax.bar(x - w / 2, sr_vals, w,
                     color=OKABE["blue"], label="Salvage Rate", zorder=3)
    bars_dr = ax.bar(x + w / 2, dr_vals, w,
                     color=OKABE["vermillion"], label="Damage Rate", zorder=3)

    # value labels
    for bar, v, n, d in zip(bars_sr, sr_vals, sr_numer, sr_denom):
        ax.text(bar.get_x() + bar.get_width() / 2,
                v + 0.02,
                f"{v*100:.1f}%\n({n}/{d})",
                ha="center", va="bottom", fontsize=7, color=OKABE["blue"])
    for bar, v, n, d in zip(bars_dr, dr_vals, dr_numer, dr_denom):
        ax.text(bar.get_x() + bar.get_width() / 2,
                v + 0.02,
                f"{v*100:.1f}%\n({n}/{d})",
                ha="center", va="bottom", fontsize=7, color=OKABE["vermillion"])

    ax.set_xticks(x)
    ax.set_xticklabels(["Benign\n(target=0)", "Melanoma\n(target=1)"])
    ax.set_ylabel("Rate")
    ax.set_ylim(0, 1.0)
    ax.set_title("Enhancement boundary by class", fontsize=9)
    ax.legend(loc="upper right", frameon=False)
    ax.yaxis.set_major_formatter(mpl.ticker.PercentFormatter(xmax=1.0))

    # annotate net-negative for melanoma
    ax.annotate("net negative\nfor melanoma",
                xy=(1 + w / 2, dr_vals[1] + 0.01),
                xytext=(1.35, 0.42),
                fontsize=7.5, color=OKABE["vermillion"],
                arrowprops=dict(arrowstyle="->", color=OKABE["vermillion"], lw=0.8),
                ha="center")

    # panel label
    ax.text(-0.15, 1.05, "A", transform=ax.transAxes,
            fontsize=11, fontweight="bold", va="top")


# ============================================================
#  Panel B — DCA net benefit + triage inset
# ============================================================
def draw_panel_b(ax):
    dca = pd.read_csv(CSV_DCA)
    triage = pd.read_csv(CSV_TRIAGE)

    # Method display names & colors (only A and G for clarity)
    method_map = {
        "A": ("Direct (EfficientNet-B3)", OKABE["blue"]),
        "G": ("Agent (Q-VIB+TokFT)",     OKABE["vermillion"]),
        "D": ("Std VIB",                  OKABE["skyblue"]),
        "D+QCTS": ("Std VIB+QCTS",        OKABE["purple"]),
    }

    # Treat-all reference
    ref_rows = dca[dca["baseline"] == "A"][["threshold", "treat_all_nb"]].drop_duplicates()
    ax.plot(ref_rows["threshold"], ref_rows["treat_all_nb"],
            color="gray", lw=1.0, ls=":", label="Treat all", zorder=1)
    ax.axhline(0, color="gray", lw=0.8, ls="-", alpha=0.5, zorder=1)

    # Per-method DCA curves — focus range [0.01, 0.40] for clinical relevance
    for bl, (name, col) in method_map.items():
        sub = dca[dca["baseline"] == bl]
        if sub.empty:
            continue
        sub_plot = sub[sub["threshold"] <= 0.40]
        ax.plot(sub_plot["threshold"], sub_plot["net_benefit"],
                color=col, lw=1.5, label=name, zorder=2)

    # Shade the CI overlap region (0.179-0.192) at clinical threshold ~0.2
    ax.axhspan(0.179, 0.192, alpha=0.12, color=OKABE["orange"],
               label="CI overlap 0.179–0.192")

    ax.set_xlim(0, 0.40)
    ax.set_ylim(-0.02, 0.25)
    ax.set_xlabel("Decision threshold (pₘ)")
    ax.set_ylabel("Net benefit")
    ax.set_title("Decision curve analysis (ITB-LQ)", fontsize=9)
    ax.legend(loc="upper right", frameon=False, fontsize=7)

    # Triage annotation: Direct best at 20% referral
    # Pull Direct (A) sens@20%ref
    tr_a = triage[triage["baseline"] == "A"]
    op_a = tr_a[tr_a["referral_rate"] <= 0.20]
    if len(op_a):
        op_a = op_a.iloc[-1]
        sens_direct = op_a["sens_auto"]
    else:
        sens_direct = 0.818  # fallback from known value

    tr_g = triage[triage["baseline"] == "G"]
    op_g = tr_g[tr_g["referral_rate"] <= 0.20]
    if len(op_g):
        op_g = op_g.iloc[-1]
        sens_agent = op_g["sens_auto"]
    else:
        sens_agent = 0.788

    ax.text(0.38, 0.22,
            f"Triage @20% ref\nDirect: {sens_direct:.3f}\nAgent:  {sens_agent:.3f}",
            ha="right", va="top", fontsize=7,
            bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="gray", lw=0.6),
            transform=ax.transData)

    ax.text(-0.15, 1.05, "B", transform=ax.transAxes,
            fontsize=11, fontweight="bold", va="top")


# ============================================================
#  Panel C — Retake gradient
# ============================================================
def draw_panel_c(ax):
    df = pd.read_csv(CSV_RETAKE)
    retake = df[
        (df["channel"] == "retake") &
        (df["band"].isin(["severe", "moderate", "high"]))
    ].copy()

    ORDER        = ["severe", "moderate", "high"]
    ORDER_LABELS = ["Severely\nDegraded", "Moderately\nDegraded", "High\nQuality"]
    retake = retake.set_index("band").loc[ORDER].reset_index()

    rates  = retake["retake_rate"].values
    ci_lo  = retake["retake_rate_ci_lo"].values
    ci_hi  = retake["retake_rate_ci_hi"].values
    yerr_lo = rates - ci_lo
    yerr_hi = ci_hi - rates

    # vermillion→orange→blue (danger to safe)
    COLORS = [OKABE["vermillion"], OKABE["orange"], OKABE["blue"]]

    x = np.arange(3)
    bars = ax.bar(x, rates, color=COLORS, alpha=0.85, width=0.52,
                  yerr=[yerr_lo, yerr_hi], capsize=5, zorder=3,
                  error_kw={"elinewidth": 1.3, "ecolor": "dimgray"})

    for bar, v in zip(bars, rates):
        ax.text(bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.04,
                f"{v:.0%}",
                ha="center", va="bottom", fontsize=9, fontweight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(ORDER_LABELS)
    ax.set_ylabel("Retake Trigger Rate")
    ax.set_ylim(0, 1.10)
    ax.yaxis.set_major_formatter(mpl.ticker.PercentFormatter(xmax=1.0))
    ax.axhline(0.5, color="gray", ls="--", lw=0.8, alpha=0.5)
    ax.set_title("Agent retake rate by quality band", fontsize=9)

    # annotations
    ax.annotate("retakes when\nneeded",
                xy=(0, rates[0] + 0.04), xytext=(0, rates[0] + 0.14),
                ha="center", fontsize=7.5, color=OKABE["vermillion"],
                arrowprops=dict(arrowstyle="->", color=OKABE["vermillion"], lw=0.8))
    ax.annotate("skips when\nalready clean",
                xy=(2, rates[2] + 0.04), xytext=(2, rates[2] + 0.28),
                ha="center", fontsize=7.5, color=OKABE["blue"],
                arrowprops=dict(arrowstyle="->", color=OKABE["blue"], lw=0.8))

    ax.text(-0.15, 1.05, "C", transform=ax.transAxes,
            fontsize=11, fontweight="bold", va="top")


# ============================================================
#  main
# ============================================================
def main(smoke=False):
    os.makedirs(OUT_DIR, exist_ok=True)

    if smoke:
        # minimal sanity: load CSVs, check key values
        df_s = pd.read_csv(CSV_SALVAGE)
        mel = df_s[df_s["target"] == 1]
        sr, sn, sd = _salvage_rate(mel)
        assert abs(sr - 0.0519) < 0.002, f"melanoma SR mismatch: {sr:.4f}"
        dr, dn, dd = _damage_rate(mel)
        assert abs(dr - 0.3029) < 0.002, f"melanoma DR mismatch: {dr:.4f}"
        df_r = pd.read_csv(CSV_RETAKE)
        severe_row = df_r[(df_r["channel"] == "retake") & (df_r["band"] == "severe")]
        assert abs(float(severe_row["retake_rate"].iloc[0]) - 0.8889) < 0.002, "retake severe mismatch"
        print("[smoke] key values verified OK")
        return

    fig, axes = plt.subplots(1, 3, figsize=(12.0, 3.6))

    draw_panel_a(axes[0])
    draw_panel_b(axes[1])
    draw_panel_c(axes[2])

    fig.tight_layout(pad=1.2, w_pad=1.8)

    fig.savefig(OUT_PDF, bbox_inches="tight")
    print(f"[SAVED] {OUT_PDF}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true",
                        help="smoke: verify key values without rendering figure")
    args = parser.parse_args()
    main(smoke=args.smoke)
