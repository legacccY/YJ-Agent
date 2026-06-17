"""
Generate A5_2_c0_surface_ci.tex from c0_decision_surface.csv.
Usage: python project/scripts/gen_surface_table.py
"""
import csv
import pathlib

CSV_PATH = pathlib.Path("D:/YJ-Agent/project/results/c0_decision_surface.csv")
OUT_PATH = pathlib.Path(
    "D:/YJ-Agent/project/meeting/ICLR2027/appendix/A5_2_c0_surface_ci.tex"
)

AXES_RAW = ["blur", "brightness", "contrast", "color_shift", "completeness"]
AXIS_LABELS = {
    "blur":         r"\textbf{Blur}",
    "brightness":   r"\textbf{Brightness}",
    "contrast":     r"\textbf{Contrast}",
    "color_shift":  r"\textbf{Colour Shift}",
    "completeness": r"\textbf{Completeness}",
}

def sig_mark(delta, lo, hi):
    if lo > 0:
        return r"$\bigstar$"
    if hi < 0:
        return r"$\dagger$"
    return r"\text{n.s.}"


def load_data(path):
    data = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            data[(row["axis"], row["severity_level"])] = row
    return data


def build_tex(data):
    lines = []
    A = lines.append

    # ---- preamble comment ----
    A(r"% Auto-generated from project/results/c0_decision_surface.csv")
    A(r"% DO NOT EDIT MANUALLY — regenerate via project/scripts/gen_surface_table.py")
    A(r"")

    # ---- section header ----
    A(r"\section{Full Reliability \texttimes{} Recoverability Surface}")
    A(r"\label{app:surface}")
    A(r"")
    A(r"Tables~\ref{tab:surface-auc} and~\ref{tab:surface-delta} report the complete")
    A(r"$5 \times 5$ grid underlying the surface visualised in \cref{fig:c0-surface}")
    A(r"(see \cref{sec:exp-surface} for experimental setup).")
    A(r"Each cell aggregates $n = 360$ C0-score predictions.")
    A(r"Confidence intervals are 2\,000-sample percentile bootstrap (95\,\%).")
    A(r"Significance markers in Table~\ref{tab:surface-delta}:")
    A(r"$\bigstar$~=~CI entirely above zero (enhancement reliably helps);")
    A(r"$\dagger$~=~CI entirely below zero (enhancement hurts);")
    A(r"\text{n.s.}~=~CI crosses zero.")
    A(r"Source: \texttt{project/results/c0\_decision\_surface.csv}.")
    A(r"")

    # ==========================================================
    # TABLE 1 — Reliability AUC (degraded + enhanced)
    # ==========================================================
    A(r"\begin{table}[htbp]")
    A(r"\centering")
    A(
        r"\caption{Reliability AUC for degraded images ($\mathrm{AUC_{deg}}$, with "
        r"95\,\% bootstrap CI) and enhanced images ($\mathrm{AUC_{enh}}$) across "
        r"all degradation axes and severity levels ($n=360$ per cell).}"
    )
    A(r"\label{tab:surface-auc}")
    A(r"\small")
    A(r"\setlength{\tabcolsep}{3pt}")
    # cols: axis | for each S: AUC_deg  CI_lo  CI_hi  AUC_enh  => 4 cols per S + 1 axis = 21
    A(r"\begin{tabular}{l" + "rrrr" * 5 + r"}")
    A(r"\toprule")

    # header row 1
    hdr1 = r"Axis"
    for s in range(1, 6):
        hdr1 += r" & \multicolumn{4}{c}{S" + str(s) + r"}"
    hdr1 += r" \\"
    A(hdr1)

    # cmidrules
    cmi = ""
    for i in range(5):
        col_start = 2 + i * 4
        col_end   = col_start + 3
        cmi += rf"\cmidrule(lr){{{col_start}-{col_end}}}"
    A(cmi)

    # header row 2
    hdr2 = r""
    for _ in range(5):
        hdr2 += (
            r" & $\mathrm{AUC_{deg}}$"
            r" & \multicolumn{2}{c}{95\,\%\,CI}"
            r" & $\mathrm{AUC_{enh}}$"
        )
    hdr2 += r" \\"
    A(hdr2)
    A(r"\midrule")

    for ax in AXES_RAW:
        row_vals = AXIS_LABELS[ax]
        row_sev  = r"\multicolumn{1}{r}{\footnotesize sev.\,}"
        for s in ["1", "2", "3", "4", "5"]:
            r = data[(ax, s)]
            auc_d = float(r["auc"])
            lo_d  = float(r["auc_ci_lo"])
            hi_d  = float(r["auc_ci_hi"])
            auc_e = float(r["auc_enhanced"])
            sv    = float(r["severity_value"])
            row_vals += (
                f" & ${auc_d:.3f}$"
                f" & ${lo_d:.3f}$"
                f" & ${hi_d:.3f}$"
                f" & ${auc_e:.3f}$"
            )
            row_sev += r" & \multicolumn{4}{c}{\footnotesize " + f"{sv:.3g}" + r"}"
        A(row_vals + r" \\")
        A(row_sev  + r" \\")
        A(r"\addlinespace[2pt]")

    A(r"\bottomrule")
    A(r"\end{tabular}")
    A(r"\end{table}")
    A(r"")

    # ==========================================================
    # TABLE 2 — Recoverability delta + CI + significance
    # ==========================================================
    A(r"\begin{table}[htbp]")
    A(r"\centering")
    A(
        r"\caption{Recoverability $\Delta = \mathrm{AUC_{enh}} - \mathrm{AUC_{deg}}$ "
        r"with 95\,\% bootstrap CI and significance markers "
        r"($\bigstar$~CI$>0$; $\dagger$~CI$<0$; \text{n.s.}~CI crosses zero). "
        r"$n=360$ per cell; 2\,000-sample percentile bootstrap.}"
    )
    A(r"\label{tab:surface-delta}")
    A(r"\small")
    A(r"\setlength{\tabcolsep}{3pt}")
    # cols: axis | for each S: delta  ci_lo  ci_hi  sig  => 4 cols per S
    A(r"\begin{tabular}{l" + "rrrr" * 5 + r"}")
    A(r"\toprule")

    hdr1b = r"Axis"
    for s in range(1, 6):
        hdr1b += r" & \multicolumn{4}{c}{S" + str(s) + r"}"
    hdr1b += r" \\"
    A(hdr1b)
    A(cmi)  # reuse same cmidrule string

    hdr2b = r""
    for _ in range(5):
        hdr2b += (
            r" & $\Delta$"
            r" & $\mathrm{CI_{lo}}$"
            r" & $\mathrm{CI_{hi}}$"
            r" & sig."
        )
    hdr2b += r" \\"
    A(hdr2b)
    A(r"\midrule")

    for ax in AXES_RAW:
        row_vals = AXIS_LABELS[ax]
        row_sev  = r"\multicolumn{1}{r}{\footnotesize sev.\,}"
        for s in ["1", "2", "3", "4", "5"]:
            r = data[(ax, s)]
            delta = float(r["recoverability_delta"])
            lo    = float(r["recoverability_ci_lo"])
            hi    = float(r["recoverability_ci_hi"])
            sv    = float(r["severity_value"])
            mark  = sig_mark(delta, lo, hi)
            row_vals += (
                f" & ${delta:+.4f}$"
                f" & ${lo:.4f}$"
                f" & ${hi:.4f}$"
                f" & {mark}"
            )
            row_sev += r" & \multicolumn{4}{c}{\footnotesize " + f"{sv:.3g}" + r"}"
        A(row_vals + r" \\")
        A(row_sev  + r" \\")
        A(r"\addlinespace[2pt]")

    A(r"\bottomrule")
    A(r"\end{tabular}")
    A(r"\end{table}")

    return "\n".join(lines)


def main():
    data = load_data(CSV_PATH)
    tex  = build_tex(data)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(tex, encoding="utf-8")
    print(f"Written: {OUT_PATH}")
    print(f"Lines:   {tex.count(chr(10)) + 1}")

    # --- spot-check 3 reference cells ---
    checks = [
        ("contrast",     "5", -0.0355),
        ("blur",         "5", +0.0634),
        ("completeness", "5", +0.0236),
    ]
    for ax, sev, expected in checks:
        r = data[(ax, sev)]
        actual = float(r["recoverability_delta"])
        ok = abs(actual - expected) < 5e-4
        print(f"  {ax} S{sev} delta={actual:.4f} expected~{expected:.4f} {'OK' if ok else 'MISMATCH'}")


if __name__ == "__main__":
    main()
