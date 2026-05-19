"""Convert hand-edited SVGs in meeting/BMVC/figures back to PDF (+ PNG).

The 4 BMVC figures live as `fig*_*.svg` and were edited in Illustrator
after the initial matplotlib export. LaTeX embeds the `.pdf` siblings,
so this script regenerates them from the SVGs.

PNG is re-rasterised at high resolution for slide / preview use.
"""
from __future__ import annotations

import pathlib
import sys

from svglib.svglib import svg2rlg
from reportlab.graphics import renderPDF

FIG_DIR = pathlib.Path("project/meeting/BMVC/figures")
NAMES = [
    "fig1_teaser",
    "fig2_problem",
    "fig3_qcts",
    "fig4_generalization",
    "fig_method",
]


def main() -> int:
    if not FIG_DIR.is_dir():
        print(f"[ERR] expected {FIG_DIR.resolve()} to exist", file=sys.stderr)
        return 1

    for name in NAMES:
        svg = FIG_DIR / f"{name}.svg"
        pdf = FIG_DIR / f"{name}.pdf"
        if not svg.exists():
            print(f"[SKIP] {svg.name} not found")
            continue
        drawing = svg2rlg(str(svg))
        renderPDF.drawToFile(drawing, str(pdf))
        print(f"[OK] {svg.name} -> {pdf.name} ({pdf.stat().st_size//1024} KB)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
