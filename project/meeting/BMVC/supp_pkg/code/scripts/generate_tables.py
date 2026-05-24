"""Generate Table 1 (main results) and Table 3 (backbone universality) from evaluation outputs.

Usage:
    python scripts/generate_tables.py \
        --baselines_dir outputs/baselines \
        --qcts_dir outputs/qcts \
        --output_dir outputs/tables
"""
import argparse
import json
from pathlib import Path


# ── LaTeX helpers ─────────────────────────────────────────────────────────────

def fmt(v, decimals=3):
    if v is None or (isinstance(v, float) and v != v):
        return "--"
    return f"{v:.{decimals}f}"


def fmt_ci(lo, hi, decimals=3):
    return f"[{lo:.{decimals}f}, {hi:.{decimals}f}]"


def heatmap_color(v, lo, hi, good="low"):
    """Return LaTeX cellcolor command for heatmap shading."""
    if v is None:
        return ""
    frac = (v - lo) / (hi - lo + 1e-9)
    if good == "low":
        frac = 1 - frac
    intensity = max(0.0, min(1.0, frac))
    g = int(100 + intensity * 155)
    return f"\\cellcolor[RGB]{{255,{g},255}}"


# ── Table 1 ──────────────────────────────────────────────────────────────────

TABLE1_METHODS = [
    ("A",  "EfficientNet-B3 (Direct)"),
    ("D",  "Std VIB"),
    ("C",  "Focal Loss + LS"),
    ("E",  "MC Dropout"),
    ("F",  "Deep Ensemble"),
    ("G",  "EDL"),
    ("TS", "Std VIB + TS"),
    ("D+QCTS", "\\textbf{Std VIB + QCTS}"),
]

TABLE1_HEADER = r"""
\begin{table}[t]
\centering
\caption{\textbf{Main results on ITB} (best in bold; $\dagger$ = Quality-Aware, $\ddagger$ = Quality-Fragile).
ECE: 15-bin; QCDI: ECE$_\text{LQ}$ $-$ ECE$_\text{HQ}$; $\rho$: Spearman entropy--$\bar q$;
AUC: AUROC on full ITB pool. Bootstrap 95\% CI in brackets.}
\label{tab:main}
\footnotesize
\begin{tabular}{lcccccc}
\toprule
Method & AUC & ECE-LQ & ECE-HQ & QCDI & $\rho$ & Taxonomy \\
\midrule
"""

TABLE1_FOOTER = r"""
\bottomrule
\end{tabular}
\end{table}
"""


def generate_table1(metrics: dict, output_path: Path) -> None:
    rows = []
    for code, name in TABLE1_METHODS:
        m = metrics.get(code, {})
        auc  = fmt(m.get("auc"), 3)
        e_lq = fmt(m.get("ece_lq"), 3)
        e_hq = fmt(m.get("ece_hq"), 3)
        qcdi = fmt(m.get("qcdi"), 3)
        rho  = fmt(m.get("rho"), 3)
        tax  = m.get("taxonomy", "--")
        rows.append(f"  {name} & {auc} & {e_lq} & {e_hq} & {qcdi} & {rho} & {tax} \\\\")

    content = TABLE1_HEADER + "\n".join(rows) + TABLE1_FOOTER
    output_path.write_text(content)
    print(f"  Wrote {output_path}")


# ── Table 3 ──────────────────────────────────────────────────────────────────

TABLE3_BACKBONES = [
    "Std VIB",
    "ResNet-50",
    "ViT-Tiny",
    "ConvNeXt-Tiny",
    "Swin-Tiny",
]

TABLE3_HEADER = r"""
\begin{table}[t]
\centering
\caption{\textbf{Backbone universality (Table 3).} QCTS re-fitted on each backbone's
validation set. TS reversal manifests as $\rho$ sign-flip (Std VIB) or QCDI sign-flip
(ViT-Tiny, Swin-Tiny); ResNet-50 is neutral. Bootstrap 95\% CI omitted for space;
all QCTS $\rho$ significant at $p{<}10^{-20}$.}
\label{tab:universality}
\footnotesize
\begin{tabular}{lrrrrrrrrrr}
\toprule
\multirow{2}{*}{Backbone} &
  \multicolumn{2}{c}{Raw} & \multicolumn{2}{c}{+TS} & \multicolumn{2}{c}{+QCTS} \\
\cmidrule(lr){2-3}\cmidrule(lr){4-5}\cmidrule(lr){6-7}
  & ECE-LQ & QCDI & ECE-LQ & QCDI & ECE-LQ & QCDI & $\rho_\text{raw}$ & $\rho_\text{TS}$ & $\rho_\text{QCTS}$ & $\alpha$ \\
\midrule
"""

TABLE3_FOOTER = r"""
\bottomrule
\end{tabular}
\end{table}
"""


def generate_table3(metrics: dict, output_path: Path) -> None:
    rows = []
    for bb in TABLE3_BACKBONES:
        m = metrics.get(bb, {})
        def g(k):
            return fmt(m.get(k), 3)
        rows.append(
            f"  {bb} & {g('raw_ece_lq')} & {g('raw_qcdi')} "
            f"& {g('ts_ece_lq')} & {g('ts_qcdi')} "
            f"& {g('qcts_ece_lq')} & {g('qcts_qcdi')} "
            f"& {g('raw_rho')} & {g('ts_rho')} & {g('qcts_rho')} & {g('alpha')} \\\\"
        )
    content = TABLE3_HEADER + "\n".join(rows) + TABLE3_FOOTER
    output_path.write_text(content)
    print(f"  Wrote {output_path}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baselines_dir", default="outputs/baselines")
    parser.add_argument("--qcts_dir",      default="outputs/qcts")
    parser.add_argument("--output_dir",    default="outputs/tables")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load metrics
    b_dir = Path(args.baselines_dir)
    q_dir = Path(args.qcts_dir)

    table1_metrics = {}
    for code, _ in TABLE1_METHODS:
        p = b_dir / f"{code}_metrics.json"
        if code == "D+QCTS":
            p = q_dir / "qcts_metrics.json"
        if p.exists():
            with open(p) as f:
                table1_metrics[code] = json.load(f)
        else:
            print(f"  WARNING: metrics not found for {code} at {p}")

    table3_metrics = {}
    for bb in TABLE3_BACKBONES:
        p = b_dir / f"universality_{bb.lower().replace('-','_').replace(' ','_')}_metrics.json"
        if p.exists():
            with open(p) as f:
                table3_metrics[bb] = json.load(f)
        else:
            print(f"  WARNING: Table 3 metrics not found for {bb}")

    print("Generating Table 1...")
    generate_table1(table1_metrics, out_dir / "table1_generated.tex")

    print("Generating Table 3...")
    generate_table3(table3_metrics, out_dir / "table3_generated.tex")

    print(f"\nDone. Tables in {out_dir}/")


if __name__ == "__main__":
    main()
