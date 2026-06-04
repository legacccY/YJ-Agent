"""
Figure 1: fig_r1_convergence
Training loss and eval Dice vs epoch from r1_official_train.log.
Log may contain wide-character spacing (chars separated by spaces); we collapse before parsing.
"""

import re
import os
import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np

LOG_PATH = r"D:\YJ-Agent\project\meeting\Med-NCA\results\r1_official_train.log"
OUT_DIR  = r"D:\YJ-Agent\project\meeting\Med-NCA\report\figures"

# ── colour palette ──────────────────────────────────────────────────────────
BLUE    = "#2E6FA3"   # muted blue – training loss
TEAL    = "#2A9D8F"   # teal – eval Dice
GREY    = "#6B7280"   # warm grey – reference lines
PAPER_C = "#E76F51"   # orange-red – paper target
FAST_C  = "#9B8EC4"   # muted purple – fast-impl anchor

def collapse(line: str) -> str:
    """Collapse runs of whitespace to single space, then strip."""
    return re.sub(r"\s+", " ", line).strip()

def parse_log(path):
    # File is UTF-16 LE (Windows wide-char log) — open with utf-16 encoding.
    # The BOM (\xff\xfe) is handled automatically by 'utf-16'.
    try:
        with open(path, "r", encoding="utf-16") as f:
            raw_lines = f.readlines()
    except UnicodeDecodeError:
        # Fallback to utf-8 if encoding differs
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            raw_lines = f.readlines()

    lines = [collapse(l) for l in raw_lines]

    # ── (a) training loss: lines like "176 loss = 0.1538408…" ────────────────
    loss_pat = re.compile(r"^(\d+) loss = ([\d.]+)")
    train_epochs, train_losses = [], []
    for ln in lines:
        m = loss_pat.match(ln)
        if m:
            train_epochs.append(int(m.group(1)))
            train_losses.append(float(m.group(2)))

    # ── (b) eval Dice: "Average Dice Loss 3d: 0, 0.8640…" ───────────────────
    #  Eval runs every 25 epochs. We determine the eval epoch by finding the
    #  next "Epoch: N" header *after* each Dice line; eval happened just before
    #  epoch N, so eval_epoch = N - 1.
    dice_pat = re.compile(r"^Average Dice Loss 3d: 0, ([\d.]+)")
    std_pat  = re.compile(r"^Standard Deviation 3d: 0, ([\d.]+)")
    epoch_hdr = re.compile(r"^Epoch: (\d+)$")

    # collect all Dice / Std positions
    dice_vals, std_vals, dice_pos = [], [], []
    for i, ln in enumerate(lines):
        m = dice_pat.match(ln)
        if m:
            dice_vals.append(float(m.group(1)))
            dice_pos.append(i)
        m2 = std_pat.match(ln)
        if m2:
            std_vals.append(float(m2.group(1)))

    # for each Dice line, look forward for next "Epoch: N" header
    eval_epochs, eval_dice, eval_std = [], [], []
    for idx, pos in enumerate(dice_pos):
        following_epoch = None
        for j in range(pos + 1, min(pos + 20, len(lines))):
            m = epoch_hdr.match(lines[j])
            if m:
                following_epoch = int(m.group(1)) - 1   # eval was at epoch N-1
                break
        # If no following epoch (training still running / last block), use
        # the last known training epoch rounded to nearest 25.
        if following_epoch is None:
            # last train epoch
            if train_epochs:
                last_ep = train_epochs[-1]
                following_epoch = int(round(last_ep / 25.0)) * 25
            else:
                following_epoch = (idx + 1) * 25

        eval_epochs.append(following_epoch)
        eval_dice.append(dice_vals[idx])
        if idx < len(std_vals):
            eval_std.append(std_vals[idx])
        else:
            eval_std.append(0.0)

    print(f"[parse] Train loss points : {len(train_epochs)}")
    print(f"[parse] Eval Dice points  : {len(eval_dice)}")
    if train_epochs:
        print(f"[parse] Epoch range       : {train_epochs[0]}–{train_epochs[-1]}")
    if eval_dice:
        print(f"[parse] Eval epochs       : {eval_epochs}")
        print(f"[parse] Eval Dice values  : {[round(d,4) for d in eval_dice]}")
    return (train_epochs, train_losses), (eval_epochs, eval_dice, eval_std)

def make_figure(train_data, eval_data):
    (tr_ep, tr_loss), (ev_ep, ev_dice, ev_std) = train_data, eval_data

    fig, axes = plt.subplots(1, 2, figsize=(9, 3.8))

    # ── Panel A: Training loss ────────────────────────────────────────────────
    ax = axes[0]
    ax.plot(tr_ep, tr_loss, color=BLUE, lw=1.0, alpha=0.85, label="Train loss")
    # smoothed overlay (rolling mean 10)
    if len(tr_loss) >= 10:
        kernel = np.ones(10) / 10
        smoothed = np.convolve(tr_loss, kernel, mode="valid")
        ax.plot(tr_ep[9:], smoothed, color=BLUE, lw=2.0, alpha=0.5, linestyle="--",
                label="Smoothed (w=10)")
    ax.set_xlabel("Epoch", fontsize=11)
    ax.set_ylabel("Training Loss (1 – Dice)", fontsize=11)
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)
    ax.grid(True, alpha=0.3, lw=0.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(fontsize=9, framealpha=0.7)
    ax.text(0.97, 0.95, "Training ongoing", transform=ax.transAxes,
            ha="right", va="top", fontsize=8, color=GREY,
            style="italic")
    ax.set_title("(A) Training Loss", fontsize=11, pad=6)

    # ── Panel B: Eval Dice ────────────────────────────────────────────────────
    ax = axes[1]
    ev_ep_arr  = np.array(ev_ep, dtype=float)
    ev_dice_arr = np.array(ev_dice, dtype=float)
    ev_std_arr  = np.array(ev_std, dtype=float)

    ax.plot(ev_ep_arr, ev_dice_arr, color=TEAL, lw=1.8, marker="o",
            markersize=6, zorder=3, label="Eval Dice (mean)")
    ax.fill_between(ev_ep_arr,
                    ev_dice_arr - ev_std_arr,
                    ev_dice_arr + ev_std_arr,
                    color=TEAL, alpha=0.15, label="±1 SD")

    # Reference lines
    paper_target = 0.886
    fast_anchor  = 0.866
    xmax = max(1500, max(ev_ep_arr) + 50) if len(ev_ep_arr) else 1500

    ax.axhline(paper_target, color=PAPER_C, lw=1.2, linestyle="--",
               label=f"Paper target {paper_target:.3f}")
    ax.axhline(fast_anchor,  color=FAST_C,  lw=1.2, linestyle=":",
               label=f"Fast-impl anchor {fast_anchor:.3f}")

    ax.set_xlabel("Epoch", fontsize=11)
    ax.set_ylabel("Mean Dice", fontsize=11)
    ax.set_xlim(0, xmax)
    ax.set_ylim(0.50, 0.95)
    ax.grid(True, alpha=0.3, lw=0.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(fontsize=8.5, framealpha=0.7, loc="lower right")
    ax.text(0.97, 0.05, "Training ongoing\n(curve will extend to 1500 epochs)",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=7.5,
            color=GREY, style="italic")
    ax.set_title("(B) Eval Mean Dice", fontsize=11, pad=6)

    plt.tight_layout(pad=1.5)

    pdf_path = os.path.join(OUT_DIR, "fig_r1_convergence.pdf")
    png_path = os.path.join(OUT_DIR, "fig_r1_convergence.png")
    fig.savefig(pdf_path, bbox_inches="tight")
    fig.savefig(png_path, dpi=200, bbox_inches="tight")
    print(f"Saved: {pdf_path}")
    print(f"Saved: {png_path}")
    plt.close(fig)
    return pdf_path, png_path

if __name__ == "__main__":
    train_data, eval_data = parse_log(LOG_PATH)
    if not train_data[0]:
        print("ERROR: No training loss data parsed. Printing first 20 cleaned lines:")
        try:
            enc = "utf-16"
            with open(LOG_PATH, "r", encoding=enc, errors="replace") as f:
                for i, ln in enumerate(f):
                    if i >= 20: break
                    sys.stdout.buffer.write(f"  {i}: {collapse(ln)}\n".encode("utf-8", errors="replace"))
        except Exception as e:
            print(f"  Debug read failed: {e}")
        sys.exit(1)
    make_figure(train_data, eval_data)
    print("Figure 1 complete.")
