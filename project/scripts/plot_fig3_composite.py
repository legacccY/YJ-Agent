"""
plot_fig3_composite.py
-----------------------
ICLR 2027 VisiSkin-Agent  Fig3: Enhancement Analysis (3-panel composite)

Panel A  [KEY] Fidelity vs Diagnosis Tradeoff  (from e10_*.csv)
  x=PSNR(dB), y=paired ΔAUC; 6 baselines + VisiEnhance (ours, vermillion star)
  VisiEnhance sits in safe corner (high PSNR, ΔAUC≈0)

Panel B  Per-Degradation PSNR  (from e2_perdim.csv)
  grouped bar: psnr_deg (grey) vs psnr_enh (colored); 4 axes
  contrast annotated ❌ (<degraded input)

Panel C  dflip Diagnostic-Flip Slopegraph  (from dflip_persample_v6.csv)
  74 ref-correct melanoma samples; slope ref→deg→enh
  highlighted: 11 flips pushed below 0.5 threshold by enhancement

Output:  project/meeting/ICLR2027/figures/fig3_enhancement.pdf  (vector)

Usage:
    python scripts/plot_fig3_composite.py
    python scripts/plot_fig3_composite.py --smoke 1 --cpu
"""

import argparse
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np
import pandas as pd

# ── Global style (matches Fig2/Fig4) ─────────────────────────────────────────
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
    "font.family":   "sans-serif",
    "font.size":     9,
    "axes.linewidth":0.8,
    "pdf.fonttype":  42,
    "ps.fonttype":   42,
})

RESULTS_DIR = "D:/YJ-Agent/project/results"
OUT_PATH    = "D:/YJ-Agent/project/meeting/ICLR2027/figures/fig3_enhancement.pdf"

# ── CLI ───────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument("--smoke", type=int, default=0, help="smoke test: use mock data")
parser.add_argument("--cpu",   action="store_true",  help="force cpu (ignored here, no GPU ops)")
parser.add_argument("--out",   default=OUT_PATH,      help="output pdf path")
args = parser.parse_args()

os.makedirs(os.path.dirname(args.out), exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────────
# DATA LOADING
# ─────────────────────────────────────────────────────────────────────────────

def load_panel_a(smoke=False):
    """Panel A: fidelity-vs-tradeoff from e10_*.csv.
    Returns list of dicts + ve dict (VisiEnhance).
    Numbers must NOT be altered - read directly from csv row positions.
    """
    if smoke:
        baselines = [
            {"model": "MIRNet-v2",   "psnr": 13.48, "dAUC": -0.0872, "ci_lo": np.nan, "ci_hi": np.nan},
            {"model": "NAFNet",      "psnr": 22.04, "dAUC": -0.1148, "ci_lo": np.nan, "ci_hi": np.nan},
            {"model": "Real-ESRGAN", "psnr": 21.61, "dAUC": -0.0832, "ci_lo": np.nan, "ci_hi": np.nan},
            {"model": "Restormer",   "psnr": 22.30, "dAUC": -0.0964, "ci_lo": np.nan, "ci_hi": np.nan},
            {"model": "SwinIR",      "psnr": 21.69, "dAUC": -0.1335, "ci_lo": np.nan, "ci_hi": np.nan},
            {"model": "Uformer-B",   "psnr": 22.28, "dAUC": -0.0939, "ci_lo": np.nan, "ci_hi": np.nan},
        ]
        ve = {"model": "VisiEnhance", "psnr": 32.79, "dAUC": -0.0172, "ci_lo": np.nan, "ci_hi": np.nan}
        return baselines, ve

    CSV_MAP = {
        "MIRNet-v2":   "e10_mirnetv2.csv",
        "NAFNet":      "e10_nafnet.csv",
        "Real-ESRGAN": "e10_realesrgan.csv",
        "Restormer":   "e10_restormer.csv",
        "SwinIR":      "e10_swinir.csv",
        "Uformer-B":   "e10_uformer.csv",
    }
    baselines = []
    for label, fname in CSV_MAP.items():
        path = os.path.join(RESULTS_DIR, fname)
        df = pd.read_csv(path)
        row = df.iloc[1]   # idx 1 = baseline model row (idx 0 = VisiEnhance)
        rec = {
            "model": label,
            "psnr":  float(row["psnr_perimg"]),
            "dAUC":  float(row["dAUC"]),
            "ci_lo": float(row["dAUC_ci_lo"]) if str(row.get("dAUC_ci_lo", "")).strip() not in ("", "nan") else np.nan,
            "ci_hi": float(row["dAUC_ci_hi"]) if str(row.get("dAUC_ci_hi", "")).strip() not in ("", "nan") else np.nan,
        }
        baselines.append(rec)
        print(f"[A] {label}: psnr={rec['psnr']:.2f} dAUC={rec['dAUC']:.4f}")

    df0 = pd.read_csv(os.path.join(RESULTS_DIR, "e10_mirnetv2.csv"))
    ve_row = df0.iloc[0]
    ve = {
        "model": "VisiEnhance",
        "psnr":  float(ve_row["psnr_perimg"]),
        "dAUC":  float(ve_row["dAUC"]),
        "ci_lo": float(ve_row["dAUC_ci_lo"]) if str(ve_row.get("dAUC_ci_lo", "")).strip() not in ("", "nan") else np.nan,
        "ci_hi": float(ve_row["dAUC_ci_hi"]) if str(ve_row.get("dAUC_ci_hi", "")).strip() not in ("", "nan") else np.nan,
    }
    print(f"[A] VisiEnhance: psnr={ve['psnr']:.2f} dAUC={ve['dAUC']:.4f}")
    return baselines, ve


def load_panel_b(smoke=False):
    """Panel B: per-degradation PSNR from e2_perdim.csv.
    Returns DataFrame with columns: axis, psnr_deg, psnr_enh.
    Numbers must NOT be altered.
    """
    if smoke:
        return pd.DataFrame([
            {"axis": "brightness",   "psnr_deg": 13.70, "psnr_enh": 37.68},
            {"axis": "blur",         "psnr_deg": 36.67, "psnr_enh": 35.82},
            {"axis": "color_shift",  "psnr_deg": 25.83, "psnr_enh": 33.77},
            {"axis": "contrast",     "psnr_deg": 32.29, "psnr_enh": 29.11},
        ])
    path = os.path.join(RESULTS_DIR, "e2_perdim.csv")
    df = pd.read_csv(path)
    print(f"[B] e2_perdim.csv  rows={len(df)}")
    for _, r in df.iterrows():
        print(f"  {r['axis']}: psnr_deg={r['psnr_deg']:.2f}  psnr_enh={r['psnr_enh']:.2f}")
    return df[["axis", "psnr_deg", "psnr_enh"]].copy()


def load_panel_c(smoke=False):
    """Panel C: dflip slopegraph from dflip_persample_v6.csv.
    Returns (mel_df, flip_mask) where mel_df has columns pr, pd, pe.
    Numbers must NOT be altered.
    """
    if smoke:
        rng = np.random.default_rng(42)
        n = 20
        pr = rng.uniform(0.55, 0.99, n)
        pd_ = rng.uniform(0.3, 0.9, n)
        pe = rng.uniform(0.3, 0.85, n)
        # force 3 flips
        pe[:3] = rng.uniform(0.1, 0.45, 3)
        return pd.DataFrame({"pr": pr, "pd": pd_, "pe": pe})

    path = os.path.join(RESULTS_DIR, "dflip_persample_v6.csv")
    df = pd.read_csv(path)
    # ref-correct positive mel: target==1 AND pr>0.5
    mel = df[(df["target"] == 1) & (df["pr"] > 0.5)].copy().reset_index(drop=True)
    print(f"[C] mel_ref_correct={len(mel)}  flip(pe<0.5)={int((mel['pe']<0.5).sum())}")
    return mel[["pr", "pd", "pe"]].copy()


# ─────────────────────────────────────────────────────────────────────────────
# PANEL DRAWING
# ─────────────────────────────────────────────────────────────────────────────

# Baseline colors (colorblind-safe Okabe)
BASELINE_COLORS = [
    OKABE["blue"],
    OKABE["skyblue"],
    OKABE["green"],
    OKABE["orange"],
    OKABE["purple"],
    OKABE["black"],
]


def draw_panel_a(ax, baselines, ve):
    """Fidelity vs diagnosis tradeoff scatter."""
    THR = 0.0   # y=0 safe line

    # Quadrant shading
    ax.axhspan(ymin=-0.22, ymax=0, xmin=0, xmax=1, alpha=0.05, color="red",   zorder=0)
    ax.axhspan(ymin=0, ymax=0.02, xmin=0, xmax=1, alpha=0.05, color="green",  zorder=0)
    ax.axhline(0, color="gray", linewidth=0.8, linestyle="--", alpha=0.6)

    # Baselines
    for i, rec in enumerate(baselines):
        c = BASELINE_COLORS[i % len(BASELINE_COLORS)]
        yerr_lo = abs(rec["dAUC"] - rec["ci_lo"]) if not np.isnan(rec["ci_lo"]) else 0
        yerr_hi = abs(rec["ci_hi"] - rec["dAUC"]) if not np.isnan(rec["ci_hi"]) else 0
        ax.errorbar(
            rec["psnr"], rec["dAUC"],
            yerr=[[yerr_lo], [yerr_hi]] if (yerr_lo > 0 or yerr_hi > 0) else None,
            fmt="o", color=c, markersize=6, capsize=3,
            linewidth=1.0, label=rec["model"], zorder=3,
        )
        ax.annotate(
            rec["model"],
            xy=(rec["psnr"], rec["dAUC"]),
            xytext=(4, 3), textcoords="offset points",
            fontsize=7, color=c,
        )

    # VisiEnhance (ours) – vermillion star, prominent
    ax.plot(
        ve["psnr"], ve["dAUC"],
        marker="*", color=OKABE["vermillion"],
        markersize=13, zorder=6, linestyle="None",
        label="VisiEnhance (ours)",
    )
    ax.annotate(
        "VisiEnhance\n(PSNR 32.79 dB, ΔAUC −0.017)",
        xy=(ve["psnr"], ve["dAUC"]),
        xytext=(-85, -24), textcoords="offset points",
        fontsize=7.5, color=OKABE["vermillion"],
        arrowprops=dict(arrowstyle="->", color=OKABE["vermillion"], lw=0.8),
        bbox=dict(boxstyle="round,pad=0.25", fc="white",
                  ec=OKABE["vermillion"], alpha=0.88),
        zorder=7,
    )

    # Quadrant text
    ax.text(13.8, 0.010, "diagnosis-safe zone",
            fontsize=7, color=OKABE["green"], fontstyle="italic", va="center")
    ax.text(13.8, -0.200, "high-fidelity but\ndiagnosis-harmful",
            fontsize=7, color="#c0392b", fontstyle="italic", va="center")

    ax.set_xlabel("Per-image PSNR (dB)", fontsize=9)
    ax.set_ylabel("Paired ΔAUC (enhanced − reference)", fontsize=9)
    ax.set_xlim(11, 36)
    ax.set_ylim(-0.22, 0.02)
    ax.tick_params(labelsize=8)
    ax.legend(loc="lower right", fontsize=7, framealpha=0.9,
              handlelength=1.2, borderpad=0.4)
    # Panel label
    ax.text(-0.12, 1.05, "A", transform=ax.transAxes,
            fontsize=11, fontweight="bold", va="top")


def draw_panel_b(ax, df_b):
    """Per-degradation PSNR grouped bar chart."""
    # Fixed display order
    ORDER = ["brightness", "blur", "color_shift", "contrast"]
    LABELS = ["Brightness", "Blur", "Color shift", "Contrast"]
    PSNR_ENH = {
        "brightness": 37.68,   # values from csv directly
        "blur":       35.82,
        "color_shift":33.77,
        "contrast":   29.11,
    }
    PSNR_DEG = {r["axis"]: r["psnr_deg"] for _, r in df_b.iterrows()}
    PSNR_ENH_CSV = {r["axis"]: r["psnr_enh"] for _, r in df_b.iterrows()}

    x = np.arange(len(ORDER))
    w = 0.35

    c_deg = "#aaaaaa"
    c_enh = OKABE["blue"]
    c_fail = OKABE["vermillion"]   # contrast bar color (below degraded)

    bars_deg = ax.bar(x - w/2,
                      [PSNR_DEG.get(k, 0) for k in ORDER],
                      width=w, color=c_deg, label="Degraded input", zorder=2)
    enh_heights = [PSNR_ENH_CSV.get(k, 0) for k in ORDER]
    bar_colors  = [c_fail if k == "contrast" else c_enh for k in ORDER]
    bars_enh = []
    for xi, (h, c) in enumerate(zip(enh_heights, bar_colors)):
        b = ax.bar(xi + w/2, h, width=w, color=c, zorder=2)
        bars_enh.append(b)

    # Value labels on enhanced bars
    for xi, (k, h) in enumerate(zip(ORDER, enh_heights)):
        yoff = 0.4
        ax.text(xi + w/2, h + yoff, f"{h:.2f}",
                ha="center", va="bottom", fontsize=7.0,
                color=c_fail if k == "contrast" else OKABE["blue"],
                fontweight="bold" if k == "contrast" else "normal")

    # Annotation on contrast: PSNR < degraded input (failure case)
    ci = ORDER.index("contrast")
    ax.annotate(
        "[FAIL] PSNR < degraded\n(29.11 dB)",
        xy=(ci + w/2, PSNR_ENH_CSV["contrast"]),
        xytext=(10, 18), textcoords="offset points",
        fontsize=7, color=c_fail,
        arrowprops=dict(arrowstyle="->", color=c_fail, lw=0.7),
    )

    ax.set_xticks(x)
    ax.set_xticklabels(LABELS, fontsize=8)
    ax.set_ylabel("PSNR (dB)", fontsize=9)
    ax.set_ylim(0, 45)
    ax.tick_params(labelsize=8)
    ax.axhline(0, color="black", linewidth=0.4)

    # Legend: degraded + enhanced (blue) + enhanced-fail (vermillion)
    import matplotlib.patches as mpatches
    leg_handles = [
        mpatches.Patch(color=c_deg,  label="Degraded input"),
        mpatches.Patch(color=c_enh,  label="Enhanced (VisiEnhance)"),
        mpatches.Patch(color=c_fail, label="Enhanced – fails (contrast)"),
    ]
    ax.legend(handles=leg_handles, fontsize=7, loc="upper right",
              framealpha=0.9, borderpad=0.4, handlelength=1.0)

    ax.text(-0.12, 1.05, "B", transform=ax.transAxes,
            fontsize=11, fontweight="bold", va="top")


def draw_panel_c(ax, mel):
    """dflip slopegraph: ref → deg → enh melanoma prob for 74 correctly-detected cases."""
    THR = 0.5
    x = [0, 1, 2]
    flip_mask = (mel["pr"] > THR) & (mel["pe"] < THR)
    n_flip = int(flip_mask.sum())
    n_total = len(mel)

    # Background (non-flip) lines
    for _, r in mel[~flip_mask].iterrows():
        ax.plot(x, [r["pr"], r["pd"], r["pe"]],
                color="#bbbbbb", alpha=0.25, lw=0.7, zorder=1)

    # Flip lines (vermillion, highlighted)
    for _, r in mel[flip_mask].iterrows():
        ax.plot(x, [r["pr"], r["pd"], r["pe"]],
                color=OKABE["vermillion"], alpha=0.65, lw=1.1, zorder=2)

    # Mean trajectory
    ax.plot(x, [mel["pr"].mean(), mel["pd"].mean(), mel["pe"].mean()],
            "-o", color="black", lw=2.2, ms=6, zorder=4,
            label=f"Mean (n={n_total})")

    # Decision threshold
    ax.axhline(THR, ls="--", color="black", lw=0.9, alpha=0.7)
    ax.text(2.06, THR + 0.015, "decision\nthreshold 0.5",
            fontsize=6.5, va="bottom", ha="right")

    # Annotate: N flips by enhancement
    ax.annotate(
        f"{n_flip}/{n_total} true melanomas\nflip below 0.5 after enhancement",
        xy=(2, mel.loc[flip_mask, "pe"].mean()),
        xytext=(-60, -38), textcoords="offset points",
        fontsize=7, color=OKABE["vermillion"],
        arrowprops=dict(arrowstyle="->", color=OKABE["vermillion"], lw=0.7),
        bbox=dict(boxstyle="round,pad=0.2", fc="white",
                  ec=OKABE["vermillion"], alpha=0.85),
        zorder=5,
    )

    ax.set_xticks(x)
    ax.set_xticklabels(["Reference\n(clean)", "Degraded", "Enhanced\n(VisiEnhance)"],
                       fontsize=8)
    ax.set_ylabel("B3 melanoma probability", fontsize=9)
    ax.set_ylim(-0.02, 1.02)
    ax.set_xlim(-0.22, 2.22)
    ax.tick_params(labelsize=8)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.legend(loc="lower left", fontsize=7, frameon=False)

    ax.text(-0.12, 1.05, "C", transform=ax.transAxes,
            fontsize=11, fontweight="bold", va="top")


# ─────────────────────────────────────────────────────────────────────────────
# COMPOSE
# ─────────────────────────────────────────────────────────────────────────────

def main():
    smoke = bool(args.smoke)
    print(f"[INFO] smoke={smoke}  out={args.out}")

    baselines, ve = load_panel_a(smoke)
    df_b          = load_panel_b(smoke)
    mel           = load_panel_c(smoke)

    # ── layout: [A wide | B medium | C medium] ─────────────────────────────
    fig = plt.figure(figsize=(13.5, 4.0))
    gs  = gridspec.GridSpec(
        1, 3,
        width_ratios=[1.55, 1.0, 1.0],
        wspace=0.38,
        left=0.07, right=0.97, top=0.88, bottom=0.14,
    )
    ax_a = fig.add_subplot(gs[0])
    ax_b = fig.add_subplot(gs[1])
    ax_c = fig.add_subplot(gs[2])

    draw_panel_a(ax_a, baselines, ve)
    draw_panel_b(ax_b, df_b)
    draw_panel_c(ax_c, mel)

    # Save vector PDF (primary) + PNG sidecar
    pdf_path = args.out
    png_path = pdf_path.replace(".pdf", ".png")
    fig.savefig(pdf_path, bbox_inches="tight")
    fig.savefig(png_path, dpi=200, bbox_inches="tight")
    print(f"[SAVED] {pdf_path}")
    print(f"[SAVED] {png_path}")
    plt.close(fig)
    print("[DONE] fig3_enhancement")


if __name__ == "__main__":
    main()
