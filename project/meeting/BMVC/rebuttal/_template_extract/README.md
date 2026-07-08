# Official BMVC 2026 Rebuttal Template

This template is inspired by the CVPR 2026 and ECCV 2026 rebuttal templates, and adapts their author-response structure for BMVC 2026.


## Instructions
- Modify the example document `rebuttal.tex` following the instructions therein
- Please make sure to look at all `TODO REBUTTAL` comments, which provide important instructions and todo items
- Either compile with `pdflatex` as

        pdflatex rebuttal
        bibtex rebuttal
        pdflatex rebuttal
        pdflatex rebuttal
        pdflatex rebuttal

    or compile with plain `latex` as

        latex rebuttal
        bibtex rebuttal
        latex rebuttal
        latex rebuttal
        latex rebuttal
        dvips rebuttal
        pstopdf rebuttal.ps
