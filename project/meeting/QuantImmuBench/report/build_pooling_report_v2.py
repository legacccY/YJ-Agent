#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_pooling_report.py — 聚焦报告「合成与融合层结果」装配成自包含 HTML。
复用 build_report_v4 的整套引擎 (STYLE / SCRIPT / md 方言解析 / 图 base64 / 徽章 / 折叠 /
悬停 / KPI), 只换 md 源、标题与 TOC 品牌名; 出新文件不覆盖旧的。

跑法 (主线跑): python report/build_pooling_report.py
"""
import sys
import html as _html
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_report_v4 as eng                              # noqa: E402  复用引擎

MD = HERE / "合成与融合层结果_QuantImmu_2026-07-10_v2.md"
OUT = HERE / "合成与融合层结果_QuantImmu_2026-07-10_v2.html"


def main():
    if not MD.exists():
        sys.exit(f"[ERR] 缺 md {MD}")
    md = MD.read_text(encoding="utf-8")
    eng.HEADINGS.clear()                                   # 引擎 render 会往此 global 追加 h2
    body = eng.render(eng.parse_blocks(md.split("\n")))
    links = "\n".join(f'  <a href="#{sid}">{_html.escape(txt, quote=False)}</a>'
                      for sid, txt in eng.HEADINGS)
    toc = ('<nav class="toc">\n'
           '  <div class="brand">QuantImmu · 合成与融合层结果<br>2026-07-10</div>\n'
           f'{links}\n</nav>')

    doc = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>QuantImmu 合成与融合层结果 · 2026-07-10</title>
<style>{eng.STYLE}</style>
</head>
<body>
<div class="wrap">
{toc}
<main>
<div class="topbar">
  <div class="meta"><strong>QuantImmu 框架：合成（pooling）与融合（rank-fusion）层的结果</strong> · 2026-07-10</div>
  <button id="tt">切换深色/浅色</button>
</div>
{body}
<hr>
<p class="meta">本报告自包含、可离线阅读；图片已 base64 内嵌，无外链无 CDN。数值取自 <code>analysis/official/newcut9mer/</code> 下 R2/R2b/R3–R7 结果表，经独立核对；术语首次出现均有解释，悬停虚线词可看释义。</p>
</main>
</div>
<script>{eng.SCRIPT}</script>
</body>
</html>
"""
    OUT.write_text(doc, encoding="utf-8")
    size = OUT.stat().st_size
    print(f"[DONE] {OUT}")
    print(f"       {size:,} 字节 ({size / 1024 / 1024:.2f} MB) · {len(eng.HEADINGS)} 个 h2 章节")


if __name__ == "__main__":
    main()
