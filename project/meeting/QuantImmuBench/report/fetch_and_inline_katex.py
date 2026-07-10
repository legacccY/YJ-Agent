#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_and_inline_katex.py — 一次性资产打包器：把 KaTeX 0.16.11 全离线内联。

产出（供 build_report_v4.py 读取注入，全离线、无 CDN、自包含）：
  report/_assets/katex_inline.css   —— katex.min.css，其中所有 woff2 字体已 base64 内联，
                                        非 woff2（woff/ttf）的 @font-face src 项被删除以减体积
  report/_assets/katex_inline.js    —— katex.min.js + auto-render.min.js 拼接

设计要点：
- 只用 stdlib urllib.request，从 jsdelivr 下载稳定版 0.16.11。
- 字体清单不硬编码：正则抓 katex.min.css 里实际出现的 KaTeX_*.woff2 文件名，去重后逐个下载。
- 下载失败即报错 raise，绝不静默写空文件。
- 每步打印进度 + 最终两文件字节数。

跑法（主线跑，不派 agent 跑代码）：python report/fetch_and_inline_katex.py
"""
import base64
import re
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "_assets"

VER = "0.16.11"
BASE = f"https://cdn.jsdelivr.net/npm/katex@{VER}/dist"
CSS_URL = f"{BASE}/katex.min.css"
KATEX_JS_URL = f"{BASE}/katex.min.js"
AUTORENDER_JS_URL = f"{BASE}/contrib/auto-render.min.js"
FONT_URL = BASE + "/fonts/{name}"          # name 形如 KaTeX_AMS-Regular.woff2

UA = "Mozilla/5.0 (fetch_and_inline_katex; +offline-report-builder)"


def fetch(url: str) -> bytes:
    """下载 url 返回原始字节；HTTP 错误 / 空响应即抛异常，绝不返回空。"""
    print(f"  下载 {url}")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        if r.status != 200:
            raise RuntimeError(f"HTTP {r.status} 下载失败：{url}")
        data = r.read()
    if not data:
        raise RuntimeError(f"下载得到空内容：{url}")
    print(f"    -> {len(data):,} 字节")
    return data


def main():
    ASSETS.mkdir(parents=True, exist_ok=True)

    # 1) 拉 katex.min.css
    print("[1/4] 拉取 katex.min.css")
    css = fetch(CSS_URL).decode("utf-8")

    # 2) 抓 CSS 里实际出现的 woff2 字体名（不硬编码清单），去重保持顺序
    print("[2/4] 解析 woff2 字体引用")
    names = list(dict.fromkeys(re.findall(r"KaTeX_[\w-]+\.woff2", css)))
    if not names:
        raise RuntimeError("katex.min.css 中未找到任何 KaTeX_*.woff2 引用，解析失败")
    print(f"    找到 {len(names)} 个 woff2 字体：{names}")

    # 删除非 woff2 的 src 项（woff / ttf），只保留 woff2。
    # KaTeX 的 @font-face src 形如：
    #   url(fonts/KaTeX_AMS-Regular.woff2) format("woff2"),
    #   url(fonts/KaTeX_AMS-Regular.woff)  format("woff"),
    #   url(fonts/KaTeX_AMS-Regular.ttf)   format("truetype")
    # woff2 恒排第一，故 woff/ttf 项前必带逗号；.woff2 因后接 "2" 不会被 \.woff\) 误伤。
    before = len(css)
    css = re.sub(
        r",?\s*url\(\s*fonts/KaTeX_[\w-]+\.(?:woff|ttf)\s*\)\s*format\(\s*[^)]*\)",
        "",
        css,
    )
    print(f"    删除非 woff2 src 项：CSS {before:,} -> {len(css):,} 字节")

    # 3) 逐个下载 woff2 并 base64 内联替换回 CSS
    print("[3/4] 下载并 base64 内联 woff2 字体")
    for name in names:
        raw = fetch(FONT_URL.format(name=name))
        b64 = base64.b64encode(raw).decode("ascii")
        data_uri = f"data:font/woff2;base64,{b64}"
        # 把路径 fonts/<name> 替换为 data URI，保留其后的 format("woff2")
        needle = f"fonts/{name}"
        if needle not in css:
            raise RuntimeError(f"CSS 中未找到待替换路径 {needle}，替换失败")
        css = css.replace(needle, data_uri)
        print(f"    内联 {name}: {len(raw):,} 字节 -> data URI")

    # 内联后不应再残留任何 fonts/ 相对引用
    leftover = re.findall(r"url\(\s*fonts/[^)]*\)", css)
    if leftover:
        raise RuntimeError(f"CSS 仍残留未内联的字体引用：{leftover[:3]} ...")

    css_out = ASSETS / "katex_inline.css"
    css_out.write_text(css, encoding="utf-8")
    print(f"    写出 {css_out} ({css_out.stat().st_size:,} 字节)")

    # 4) 拉 JS：katex.min.js + auto-render.min.js 拼接
    print("[4/4] 拉取并拼接 JS（katex.min.js + auto-render.min.js）")
    katex_js = fetch(KATEX_JS_URL).decode("utf-8")
    autorender_js = fetch(AUTORENDER_JS_URL).decode("utf-8")
    js = (
        "/* KaTeX " + VER + " katex.min.js */\n"
        + katex_js
        + "\n/* KaTeX " + VER + " contrib/auto-render.min.js */\n"
        + autorender_js
        + "\n"
    )
    js_out = ASSETS / "katex_inline.js"
    js_out.write_text(js, encoding="utf-8")
    print(f"    写出 {js_out} ({js_out.stat().st_size:,} 字节)")

    print("\n[DONE] KaTeX 离线资产就绪：")
    print(f"  {css_out}  {css_out.stat().st_size:,} 字节")
    print(f"  {js_out}  {js_out.stat().st_size:,} 字节")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:                    # 报错不静默、退非零码
        sys.exit(f"[ERR] {type(e).__name__}: {e}")
