"""Failure case analysis for paper Section 5.3 + Figure 11.

Identifies samples where:
  (a) F (Q-VIB Full, Ours) wrong but A (B3 Direct) correct  -> architecture limit
  (b) F correct but A wrong                                  -> Q-VIB advantage
  (c) Both wrong                                             -> hard case
  (d) F correct + low entropy + good quality                 -> ideal behaviour

Output:
  results/failure_cases.csv         — top-K from each category with image_path
  results/figures/fig11_failure_grid.png — 4 columns × 3 rows = 12 panels

Usage:
    cd D:/YJ-Agent/project
    python analyze_failure.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import cv2
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

PRED_CSV    = "results/itb_predictions.csv"
SUBSETS_CSV = "results/itb_subsets.csv"
OUT_CSV     = "results/failure_cases.csv"
FIG_PATH    = "results/figures/fig11_failure_grid.png"

DECISION_THRESH = 0.5
HIGH_CONF      = 0.7   # |p - 0.5| > 0.2 → confident
LOW_CONF       = 0.55  # close to 0.5 → uncertain


def load_aligned(subset_name: str) -> pd.DataFrame:
    """Join F and A predictions with image_path via row-order alignment."""
    preds   = pd.read_csv(PRED_CSV)
    subsets = pd.read_csv(SUBSETS_CSV)
    sub_meta = subsets[subsets["subset"] == subset_name].reset_index(drop=True)
    f = preds[(preds["baseline"] == "F") & (preds["subset"] == subset_name)].reset_index(drop=True)
    a = preds[(preds["baseline"] == "A") & (preds["subset"] == subset_name)].reset_index(drop=True)
    assert len(f) == len(a) == len(sub_meta), \
        f"Length mismatch on {subset_name}: F={len(f)}, A={len(a)}, sub={len(sub_meta)}"
    assert (f["target"].values == sub_meta["target"].values).all(), \
        f"Target mismatch on {subset_name} between predictions and subsets"
    return pd.DataFrame({
        "subset":      subset_name,
        "image_path":  sub_meta["image_path"].values,
        "isic_id":     sub_meta["isic_id"].values,
        "target":      f["target"].values,
        "qbar":        f["qbar"].values,
        "f_prob":      f["prob_pos"].values,
        "a_prob":      a["prob_pos"].values,
    })


def categorize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["f_pred"]   = (df["f_prob"] >= DECISION_THRESH).astype(int)
    df["a_pred"]   = (df["a_prob"] >= DECISION_THRESH).astype(int)
    df["f_correct"] = (df["f_pred"] == df["target"]).astype(int)
    df["a_correct"] = (df["a_pred"] == df["target"]).astype(int)
    df["f_entropy"] = -(df["f_prob"] * np.log(df["f_prob"].clip(1e-9))
                       + (1 - df["f_prob"]) * np.log((1 - df["f_prob"]).clip(1e-9)))

    def assign(row):
        if row["f_correct"] == 1 and row["a_correct"] == 0:
            return "F_recovers"
        if row["f_correct"] == 0 and row["a_correct"] == 1:
            return "F_misses_A_gets"
        if row["f_correct"] == 0 and row["a_correct"] == 0:
            return "Both_wrong"
        return "Both_correct"

    df["category"] = df.apply(assign, axis=1)
    return df


def pick_top_k(df: pd.DataFrame, category: str, target: int, k: int = 3) -> pd.DataFrame:
    """Pick k most illustrative samples in (category, target) bucket."""
    sub = df[(df["category"] == category) & (df["target"] == target)].copy()
    if category == "F_recovers":
        # Largest |f_prob - 0.5| in correct direction (most confident correct prediction)
        sub["score"] = np.where(target == 1, sub["f_prob"], 1 - sub["f_prob"])
    elif category == "F_misses_A_gets":
        # F most confidently wrong: largest |f_prob - 0.5| in wrong direction
        sub["score"] = np.where(target == 1, 1 - sub["f_prob"], sub["f_prob"])
    elif category == "Both_wrong":
        sub["score"] = np.where(target == 1, 1 - sub["f_prob"], sub["f_prob"]) + \
                       np.where(target == 1, 1 - sub["a_prob"], sub["a_prob"])
    else:
        # Both correct + lowest entropy (cleanest)
        sub["score"] = -sub["f_entropy"]
    return sub.sort_values("score", ascending=False).head(k)


def main():
    # Aggregate across HQ + LQ + Edge (skip Diverse: different label semantics)
    parts = [load_aligned(s) for s in ["ITB-HQ", "ITB-LQ", "ITB-Edge"]]
    df = pd.concat(parts, ignore_index=True)
    df = categorize(df)

    print(f"Loaded {len(df)} samples across HQ/LQ/Edge")
    print(df.groupby(["category", "target"]).size().unstack(fill_value=0))

    # Pick samples for fig11
    selections = []
    for cat in ["F_recovers", "F_misses_A_gets", "Both_wrong"]:
        for target in [0, 1]:
            picks = pick_top_k(df, cat, target, k=2)
            selections.append(picks)
    sel = pd.concat(selections, ignore_index=True)
    print(f"\nSelected {len(sel)} samples for grid")

    sel.to_csv(OUT_CSV, index=False)
    print(f"Saved {OUT_CSV}")

    # ── Figure 11: 4 rows × 3 cols failure grid ───────────────────────────────
    cats = ["F_recovers", "F_misses_A_gets", "Both_wrong"]
    cat_titles = {
        "F_recovers":      "(a) Q-VIB recovers (B3 wrong)",
        "F_misses_A_gets": "(b) Q-VIB misses (B3 right)",
        "Both_wrong":      "(c) Both wrong (hard case)",
    }
    target_titles = {0: "Benign (target=0)", 1: "Melanoma (target=1)"}

    fig, axes = plt.subplots(3, 4, figsize=(8.0, 6.5))
    for col_idx, cat in enumerate(cats):
        for row_idx, target in enumerate([0, 1]):
            picks = pick_top_k(df, cat, target, k=2)
            for j in range(2):
                ax = axes[row_idx * 1 + (1 if cat == "Both_wrong" and j == 1 else 0)][col_idx + (j if cat=="Both_wrong" else 0)]  # placeholder

    # Simpler layout: 3 cols × 4 rows = 12 cells (2 per cat-target)
    plt.close(fig)
    fig, axes = plt.subplots(4, 3, figsize=(7.5, 9.0))
    row = 0
    for target in [1, 0]:   # melanoma first
        for cat in cats:
            picks = pick_top_k(df, cat, target, k=1)
            if len(picks) == 0:
                continue
            r = picks.iloc[0]
            ax = axes[row][cats.index(cat)]
            img = cv2.imread(str(r["image_path"]))
            if img is not None:
                img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                ax.imshow(img)
            ax.axis("off")
            color_f = "#2E8B57" if r["f_correct"] else "#D63A3A"
            color_a = "#2E8B57" if r["a_correct"] else "#D63A3A"
            ax.set_title(
                f"{cat_titles[cat]}\n"
                f"target={'MEL' if target==1 else 'BEN'}  q̄={r['qbar']:.2f}\n"
                f"F={r['f_prob']:.2f}  B3={r['a_prob']:.2f}",
                fontsize=7,
            )
            ax.spines[:].set_visible(True)
            for s in ax.spines.values():
                s.set_color(color_f)
                s.set_linewidth(2)
        row += 1
        # second pass for diversity
        for cat in cats:
            picks = pick_top_k(df, cat, target, k=2)
            if len(picks) < 2:
                continue
            r = picks.iloc[1]
            ax = axes[row][cats.index(cat)]
            img = cv2.imread(str(r["image_path"]))
            if img is not None:
                img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                ax.imshow(img)
            ax.axis("off")
            color_f = "#2E8B57" if r["f_correct"] else "#D63A3A"
            ax.set_title(
                f"target={'MEL' if target==1 else 'BEN'}  q̄={r['qbar']:.2f}\n"
                f"F={r['f_prob']:.2f}  B3={r['a_prob']:.2f}",
                fontsize=7,
            )
            ax.spines[:].set_visible(True)
            for s in ax.spines.values():
                s.set_color(color_f)
                s.set_linewidth(2)
        row += 1

    fig.suptitle("Figure 11: Qualitative failure modes (Q-VIB Full vs B3 Direct)\n"
                 "Green border = F correct; Red border = F wrong",
                 fontsize=9.5, y=0.995)
    fig.tight_layout(pad=0.4, rect=[0, 0, 1, 0.97])
    Path(FIG_PATH).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG_PATH, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved {FIG_PATH}")


if __name__ == "__main__":
    main()
