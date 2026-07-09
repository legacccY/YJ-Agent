#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_report.py — 把 _report_body.html 装配成自包含 HTML 报告。
- 3 张核心图 base64 内嵌（公式已改用纯 HTML/CSS，无需 MathJax）
- 清理占位注释
产物：QuantImmuBench_单工具排名_复现级报告_2026-07-08.html
运行：python report/build_report.py
"""
import base64, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BODY = HERE / "_report_v3.html"
OUT  = HERE / "QuantImmuBench_单工具排名报告_v3_2026-07-08.html"

FIGDIR = ROOT / "analysis" / "official" / "recompute_effN" / "figures"
FIGS = {
    "__FIG_RANKING__":  FIGDIR / "fig_rerun_9mer_maxpool_ranking.png",
    "__FIG_DUMBBELL__": FIGDIR / "fig_rerun_9mer_newcut_vs_oldSLP_dumbbell.png",
    "__FIG_DAI__":      FIGDIR / "fig_rerun_9mer_dai_ranking.png",
}

def b64_png(p: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode("ascii")

def main():
    if not BODY.exists(): sys.exit(f"[ERR] 缺 {BODY}")
    html = BODY.read_text(encoding="utf-8")
    for token, p in FIGS.items():
        if not p.exists(): sys.exit(f"[ERR] 缺图 {p}")
        n = html.count(token)
        html = html.replace(token, b64_png(p))
        print(f"[ok] {token} → base64 ({p.stat().st_size:,} 字节, 替换 {n} 处)")
    for m in ["<!--V3NEXT-->","<!--V3ASSISTANT-->"]:
        html = html.replace(m, "")
    OUT.write_text(html, encoding="utf-8")
    print(f"\n[DONE] {OUT}")
    print(f"       {OUT.stat().st_size:,} 字节 ({OUT.stat().st_size/1024/1024:.2f} MB)")

if __name__ == "__main__":
    main()
