"""Headline 图: VisiEnhance 系统性「美化」黑色素瘤 (红线 R8 实证).

读 dump_dflip_figure_data.py 产物:
  (a) slopegraph: 74 个 ref-正确-报阳 mel 的 B3 mel-prob  ref -> deg -> enh, 0.5 决策线,
      均值轨迹加粗, 标注 enhance 把 N/74 压到 0.5 以下.
  (b) enhance-caused flip 病灶三联 (ref|deg|enh) 网格: 病灶磨平 + mel-prob 标注.
输出 report/figures/fig_dflip.{pdf,png}. cwd=project.
"""
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import gridspec

OUT = Path("../project/meeting/ICLR2027") if False else Path("results")
FIG_DIR = Path("report") / "figures"
PANEL_DIR = Path("results/dflip_panels")

# 配色
C_REF, C_DEG, C_ENH = "#2c7fb8", "#999999", "#d7301f"
THR = 0.5


def load():
    df = pd.read_csv("results/dflip_persample.csv")
    mel = df[(df.target == 1) & (df.pr > THR)].copy()      # ref 正确报阳的 mel
    panels = []
    for f in sorted(PANEL_DIR.glob("*.npz")):
        z = np.load(f)
        panels.append({"id": f.stem, "ref": z["ref"], "deg": z["deg"], "enh": z["enh"],
                       "pr": float(z["pr"]), "pd": float(z["pd"]), "pe": float(z["pe"]),
                       "attr": str(z["attr"])})
    # B (enhance 主动翻) 优先, 按 ref 置信度高->低 (越自信被翻越冲击)
    panels.sort(key=lambda p: (p["attr"] != "B_enh", -p["pr"]))
    return mel, panels


def panel_a(ax, mel):
    x = [0, 1, 2]
    n_flip = int(((mel.pr > THR) & (mel.pe < THR)).sum())
    for _, r in mel.iterrows():
        col = C_ENH if (r.pr > THR and r.pe < THR) else "#bdbdbd"
        a = 0.55 if (r.pr > THR and r.pe < THR) else 0.18
        ax.plot(x, [r.pr, r.pd, r.pe], "-", color=col, alpha=a, lw=0.8, zorder=1)
    ax.plot(x, [mel.pr.mean(), mel.pd.mean(), mel.pe.mean()], "-o", color="black",
            lw=2.6, ms=7, zorder=3, label="mean (n=%d)" % len(mel))
    ax.axhline(THR, ls="--", color="k", lw=1.0, alpha=0.7)
    ax.text(2.02, THR + 0.01, "decision threshold 0.5", fontsize=8, va="bottom", ha="right")
    ax.set_xticks(x)
    ax.set_xticklabels(["reference\n(clean)", "degraded", "enhanced\n(VisiEnhance)"])
    ax.set_ylabel("B3 melanoma probability")
    ax.set_ylim(-0.02, 1.02)
    ax.set_xlim(-0.15, 2.15)
    ax.set_title("(a) Enhancement suppresses melanoma confidence\n"
                 r"mean $\bar p$ %.2f$\rightarrow$%.2f (ref$\rightarrow$enh);  "
                 "%d/%d true melanomas flip below 0.5" %
                 (mel.pr.mean(), mel.pe.mean(), n_flip, len(mel)), fontsize=9.5, pad=10)
    ax.legend(loc="lower left", fontsize=8, frameon=False)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


def panel_b(fig, gs_b, panels, ncols=4):
    show = panels[:ncols]
    inner = gridspec.GridSpecFromSubplotSpec(3, ncols, subplot_spec=gs_b,
                                             hspace=0.06, wspace=0.06)
    row_lab = ["reference", "degraded", "enhanced"]
    key = ["ref", "deg", "enh"]
    prob = ["pr", "pd", "pe"]
    for c, p in enumerate(show):
        for r in range(3):
            ax = fig.add_subplot(inner[r, c])
            ax.imshow(p[key[r]]); ax.set_xticks([]); ax.set_yticks([])
            pv = p[prob[r]]
            col = C_ENH if pv < THR else "#1a9850"
            ax.text(0.5, -0.10, "mel p=%.2f" % pv, transform=ax.transAxes,
                    ha="center", va="top", fontsize=8, color=col,
                    fontweight="bold" if r == 2 else "normal")
            if c == 0:
                ax.set_ylabel(row_lab[r], fontsize=9)
            if r == 2:                       # enhanced 行红框
                for sp in ax.spines.values():
                    sp.set_color(C_ENH); sp.set_linewidth(2.2)
    # 标题落在 inner 顶部
    ax0 = fig.add_subplot(gs_b); ax0.axis("off")
    ax0.set_title("(b) Enhance-caused flips: malignant cues (asymmetry, irregular\n"
                  "border, colour variegation) smoothed away as low-quality noise",
                  fontsize=9.5, pad=10)


def main():
    mel, panels = load()
    n_b = int(((mel.pr > THR) & (mel.pe < THR)).sum())
    n_enh = sum(p["attr"] == "B_enh" for p in panels)
    print(f"mel(ref正确报阳)={len(mel)}  flip={n_b}  panels={len(panels)} (B_enh={n_enh})")

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig = plt.figure(figsize=(13, 5.6))
    gs = gridspec.GridSpec(1, 2, width_ratios=[1.05, 1.55], wspace=0.2)
    gs.update(top=0.84, bottom=0.08, left=0.06, right=0.985)
    panel_a(fig.add_subplot(gs[0]), mel)
    panel_b(fig, gs[1], panels, ncols=min(4, len(panels)))
    fig.savefig(FIG_DIR / "fig_dflip.pdf", bbox_inches="tight")
    fig.savefig(FIG_DIR / "fig_dflip.png", dpi=180, bbox_inches="tight")
    print(f"saved -> {FIG_DIR}/fig_dflip.pdf|png")


if __name__ == "__main__":
    main()
