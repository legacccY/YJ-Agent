"""
Figure 2: fig_c1_steps
Inference steps vs mean Dice from r1_c1_steps.csv and c1_steps_summary.json.
"""

import json
import os
import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
import csv

CSV_PATH  = r"D:\YJ-Agent\project\meeting\Med-NCA\results\r1_c1_steps.csv"
JSON_PATH = r"D:\YJ-Agent\project\meeting\Med-NCA\results\c1_steps_summary.json"
OUT_DIR   = r"D:\YJ-Agent\project\meeting\Med-NCA\report\figures"

# ── colour palette ──────────────────────────────────────────────────────────
BLUE    = "#2E6FA3"   # muted blue – main curve
FILL_C  = "#2E6FA3"   # same, semi-transparent fill
ELBOW_C = "#E9C46A"   # amber – elbow annotation
ANCHOR_C = "#E76F51"  # orange-red – anchor point

def load_summary(json_path):
    with open(json_path, encoding="utf-8") as f:
        return json.load(f)

def compute_from_csv(csv_path):
    """Read CSV, group by steps, compute mean+std+ci95 per step."""
    from collections import defaultdict
    groups = defaultdict(list)
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        print(f"[csv] Columns: {reader.fieldnames}")
        for row in reader:
            steps = int(row["steps"])
            dice  = float(row["dice"])
            groups[steps].append(dice)
    result = {}
    for steps, vals in sorted(groups.items()):
        arr = np.array(vals)
        n   = len(arr)
        mean = float(arr.mean())
        std  = float(arr.std())
        ci95 = 1.96 * std / np.sqrt(n)
        result[steps] = {"n": n, "mean": mean, "std": std, "ci95": ci95}
        print(f"[csv]   steps={steps:3d}: n={n}, mean={mean:.4f}, std={std:.4f}, ci95=±{ci95:.4f}")
    return result

def make_figure(summary):
    per_steps = summary["per_steps"]
    steps_arr = np.array([d["steps"] for d in per_steps], dtype=float)
    means_arr = np.array([d["dice_mean"] for d in per_steps], dtype=float)
    ci_lo     = np.array([d["ci95"][0] for d in per_steps], dtype=float)
    ci_hi     = np.array([d["ci95"][1] for d in per_steps], dtype=float)
    std_arr   = np.array([d["dice_std"] for d in per_steps], dtype=float)

    elbow_steps = summary.get("convergence_elbow_steps", 32)
    anchor_steps = summary["anchor"]["steps"]
    anchor_dice  = summary["anchor"]["actual_dice"]

    fig, ax = plt.subplots(figsize=(6.5, 4.0))

    # shaded 95% CI band
    ax.fill_between(steps_arr, ci_lo, ci_hi, color=FILL_C, alpha=0.15,
                    label="95% CI")
    # ±1 SD band (lighter)
    ax.fill_between(steps_arr,
                    means_arr - std_arr,
                    means_arr + std_arr,
                    color=FILL_C, alpha=0.08, label="±1 SD")

    # main mean line
    ax.plot(steps_arr, means_arr, color=BLUE, lw=2.0, marker="o",
            markersize=6, zorder=4, label="Mean Dice")

    # peak = training-steps annotation
    ax.axvline(elbow_steps, color=ELBOW_C, lw=1.3, linestyle="--", zorder=2,
               label=f"Training steps={int(elbow_steps)} (peak)")
    ax.text(elbow_steps + 1.0, 0.50, f"peak @\ntrain steps={int(elbow_steps)}",
            color="#B5852F", fontsize=8.5, va="bottom", ha="left")

    # anchor point
    ax.scatter([anchor_steps], [anchor_dice], color=ANCHOR_C, s=80, zorder=5,
               marker="*", label=f"Anchor: steps={anchor_steps}, Dice={anchor_dice:.3f}")
    ax.annotate(f"steps={anchor_steps}\nDice={anchor_dice:.3f}",
                xy=(anchor_steps, anchor_dice),
                xytext=(anchor_steps - 14, anchor_dice - 0.08),
                fontsize=8.5, color=ANCHOR_C,
                arrowprops=dict(arrowstyle="->", color=ANCHOR_C, lw=0.8))

    # annotation: over-stepping collapse
    ax.annotate("over-stepping:\nsteps$\\geq$48 collapse\n(state over-evolves)",
                xy=(48, means_arr[steps_arr == 48][0]),
                xytext=(31, 0.44),
                fontsize=8, color="#6B7280",
                arrowprops=dict(arrowstyle="->", color="#6B7280", lw=0.8))

    ax.set_xlabel("Inference Steps", fontsize=11)
    ax.set_ylabel("Mean Dice", fontsize=11)
    ax.set_xlim(-1, max(steps_arr) + 4)
    ax.set_ylim(-0.02, 1.0)

    # x-ticks at actual step values
    ax.set_xticks(steps_arr.astype(int))
    ax.set_xticklabels([str(int(s)) for s in steps_arr], fontsize=9)

    ax.grid(True, alpha=0.3, lw=0.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(fontsize=9, framealpha=0.75, loc="upper left")

    plt.tight_layout(pad=1.5)

    pdf_path = os.path.join(OUT_DIR, "fig_c1_steps.pdf")
    png_path = os.path.join(OUT_DIR, "fig_c1_steps.png")
    fig.savefig(pdf_path, bbox_inches="tight")
    fig.savefig(png_path, dpi=200, bbox_inches="tight")
    print(f"Saved: {pdf_path}")
    print(f"Saved: {png_path}")
    plt.close(fig)
    return pdf_path, png_path

if __name__ == "__main__":
    # Verify CSV columns and compute stats for debugging
    csv_stats = compute_from_csv(CSV_PATH)

    # Load pre-computed summary (has ci95 already)
    summary = load_summary(JSON_PATH)
    print(f"\n[summary] Steps sweep : {summary['steps_sweep']}")
    print(f"[summary] Anchor      : steps={summary['anchor']['steps']}, dice={summary['anchor']['actual_dice']}")
    print(f"[summary] Elbow       : {summary.get('convergence_elbow_steps', '?')} steps")

    make_figure(summary)
    print("Figure 2 complete.")
