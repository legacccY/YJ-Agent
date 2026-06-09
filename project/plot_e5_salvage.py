"""
E5 SalvageRate figure for ICLR paper.

Reads results/e5_salvage_persample.csv and produces a two-panel figure:
  (a) SalvageRate (solid) and DamageRate (dashed) vs norm-q-bar routing signal,
      binned by quantile of q-bar, with the 0.55 target reference line.
  (b) Per-severity (mild/moderate/severe) grouped bars: SalvageRate vs DamageRate,
      annotated with mean norm-q-bar.

Definitions:
  salvageable = (correct_deg == 0)
  salvaged    = salvageable & (correct_enh == 1)
  SalvageRate = #salvaged / #salvageable
  damaged     = (correct_deg == 1) & (correct_enh == 0)
  DamageRate  = #damaged / #correct_deg

Outputs (cwd = project/):
  report/figures/fig_e5_salvage.pdf
  report/figures/fig_e5_salvage.png  (dpi=300)
"""

import os
import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ---- config ----------------------------------------------------------------
CSV = "results/e5_salvage_persample.csv"
OUTDIR = "report/figures"
OUTSTEM = "fig_e5_salvage"
N_BINS = 10
TARGET = 0.55
SEV_ORDER = ["mild", "moderate", "severe"]

# Color-blind friendly (Okabe-Ito)
C_SALVAGE = "#0072B2"  # blue
C_DAMAGE = "#D55E00"   # vermillion
C_TARGET = "#999999"   # grey

plt.rcParams.update({
    "font.size": 9,
    "axes.titlesize": 10,
    "axes.labelsize": 9,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "legend.fontsize": 8,
    "axes.spines.top": False,
    "axes.spines.right": False,
})


# ---- metrics ----------------------------------------------------------------
def salvage_rate(d):
    salvageable = d[d.correct_deg == 0]
    if len(salvageable) == 0:
        return np.nan, 0
    salvaged = salvageable[salvageable.correct_enh == 1]
    return len(salvaged) / len(salvageable), len(salvageable)


def damage_rate(d):
    base = d[d.correct_deg == 1]
    if len(base) == 0:
        return np.nan, 0
    damaged = base[base.correct_enh == 0]
    return len(damaged) / len(base), len(base)


def main():
    df = pd.read_csv(CSV)
    os.makedirs(OUTDIR, exist_ok=True)

    # ---- per-severity (for panel b + report) -------------------------------
    sev_sr, sev_dr, sev_qbar = {}, {}, {}
    for s in SEV_ORDER:
        d = df[df.sev == s]
        sev_sr[s] = salvage_rate(d)[0]
        sev_dr[s] = damage_rate(d)[0]
        sev_qbar[s] = d.qbar_route.mean()
        print(f"{s:9s}: SalvageRate={sev_sr[s]:.3f}  "
              f"DamageRate={sev_dr[s]:.3f}  norm-qbar={sev_qbar[s]:.3f}")

    # ---- quantile bins over q-bar (for panel a) ----------------------------
    # qcut for roughly equal sample counts per bin (more stable rates).
    bins = pd.qcut(df.qbar_route, q=N_BINS, duplicates="drop")
    centers, sr_vals, dr_vals = [], [], []
    for interval, d in df.groupby(bins, observed=True):
        centers.append(d.qbar_route.mean())
        sr_vals.append(salvage_rate(d)[0])
        dr_vals.append(damage_rate(d)[0])
    centers = np.array(centers)
    sr_vals = np.array(sr_vals)
    dr_vals = np.array(dr_vals)

    # ---- figure -------------------------------------------------------------
    fig, (axa, axb) = plt.subplots(1, 2, figsize=(8.4, 3.4))

    # (a) rate vs q-bar
    axa.axhline(TARGET, color=C_TARGET, ls=":", lw=1.2,
                label=f"target {TARGET:.2f}")
    axa.plot(centers, sr_vals, "-o", color=C_SALVAGE, lw=1.8, ms=4,
             label="SalvageRate")
    axa.plot(centers, dr_vals, "--s", color=C_DAMAGE, lw=1.8, ms=4,
             label="DamageRate")
    axa.set_xlabel("norm-q̄ routing signal (higher = cleaner)")
    axa.set_ylabel("rate")
    axa.set_ylim(-0.03, 1.0)
    axa.set_title("(a) Rate vs routing signal")
    axa.legend(loc="center right", frameon=False)
    axa.annotate("dirtier → more salvageable",
                 xy=(0.02, 0.96), xycoords="axes fraction",
                 ha="left", va="top", fontsize=8, color=C_SALVAGE)

    # (b) per-severity grouped bars
    x = np.arange(len(SEV_ORDER))
    w = 0.36
    sr_b = [sev_sr[s] for s in SEV_ORDER]
    dr_b = [sev_dr[s] for s in SEV_ORDER]
    axb.axhline(TARGET, color=C_TARGET, ls=":", lw=1.2)
    bsr = axb.bar(x - w / 2, sr_b, w, color=C_SALVAGE, label="SalvageRate")
    bdr = axb.bar(x + w / 2, dr_b, w, color=C_DAMAGE, label="DamageRate")
    for rect, v in zip(bsr, sr_b):
        axb.text(rect.get_x() + rect.get_width() / 2, v + 0.015,
                 f"{v:.3f}", ha="center", va="bottom", fontsize=8)
    for rect, v in zip(bdr, dr_b):
        axb.text(rect.get_x() + rect.get_width() / 2, v + 0.015,
                 f"{v:.3f}", ha="center", va="bottom", fontsize=8)
    # annotate mean q-bar under each severity label
    labels = [f"{s}\n(q̄={sev_qbar[s]:.3f})" for s in SEV_ORDER]
    axb.set_xticks(x)
    axb.set_xticklabels(labels)
    axb.set_ylabel("rate")
    axb.set_ylim(0, 1.0)
    axb.set_title("(b) Per-severity salvage vs damage")
    axb.legend(loc="upper left", frameon=False)

    fig.tight_layout()
    pdf = os.path.join(OUTDIR, OUTSTEM + ".pdf")
    png = os.path.join(OUTDIR, OUTSTEM + ".png")
    fig.savefig(pdf, bbox_inches="tight")
    fig.savefig(png, dpi=300, bbox_inches="tight")
    print(f"saved: {pdf}")
    print(f"saved: {png}")


if __name__ == "__main__":
    main()
