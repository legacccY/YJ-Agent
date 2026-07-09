#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_s89_html.py — 把 §8 前四问「新切 9mer 结果」回复稿(md 终稿) 装配成
自包含单文件 HTML，风格对齐 v3 单工具排名报告。

- 读 md 终稿 → 逐字转 HTML（只做排版/语义分类，绝不改数字/结论/措辞）
- 读 3 张 PNG → base64 内嵌（自包含、可离线打开、无外链无 CDN）
- 复用 v3 的整块 <style>（CSS 变量/深浅主题/.card/.note/.note.watch/.scroll/<figure>/.kpis/.b）
  与 v3 的 <script>（floatTip 悬停标签 + 主题切换）

语义分类（对齐 v3，去偏向的关键）：
  * 「**判定：…**」段          → .note（结论色块）
  * 「**caveat…**」/「**TODO**」/「两点诚实说明…」段 → .note.watch（橙色警示条）
  * 「四点前置说明…避免误读：」+ 其后有序表  → .note.watch 整块
  * 「两条 caveat…否则会高估这条的力度：」+ 其后无序表 → .note.watch 整块
  * 「配图：Fig X…」段         → <figure> + base64 图 + <figcaption>
  * 所有表格                    → .scroll 包裹
  * 顶部注入「摘要与速览」.kpis（5 张判定卡，取值 100% 自 md 判定/总表）

运行（我不跑，交主线）：python report/build_s89_html.py
"""
import base64
import html as _html
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MD = HERE / "给老师_§8四问新切结果_2026-07-09.md"
OUT = HERE / "给老师_§8四问新切结果_2026-07-09.html"

FIGDIR = ROOT / "analysis" / "official" / "newcut9mer" / "figures"
# md 里「配图：Fig X」行按其文件名 key 就地插图，与 md 位置严格一致
FIG_FILES = {
    "figA_newcut_fusion_no_net_gain": FIGDIR / "figA_newcut_fusion_no_net_gain.png",
    "figB_newcut_robustness": FIGDIR / "figB_newcut_robustness.png",
    "figC_newcut_max_vs_bestpooling": FIGDIR / "figC_newcut_max_vs_bestpooling.png",
}
FIG_LETTER = {
    "figA_newcut_fusion_no_net_gain": "A",
    "figB_newcut_robustness": "B",
    "figC_newcut_max_vs_bestpooling": "C",
}

# ----------------------------------------------------------------------------
# v3 的整块 <style>（逐字复用，见 QuantImmuBench_单工具排名报告_v3_2026-07-08.html）
# ----------------------------------------------------------------------------
STYLE = r"""
:root{
  --blue:#0b6ea8;--blue2:#0072B2;--orange:#c77f00;--green:#0a8f5b;--purple:#6b4bb3;--red:#b23a48;
  --ink:#1b2b31;--muted:#5f767d;--line:#e0e8ea;--card:#ffffff;--bg:#f6f9f9;
  --dark:#123039;--code:#eef3f4;--fold:#f1f7f7;--warnbg:#fff6e6;--workbg:#e6f7ef;--litbg:#e8f1fd;--offbg:#f0eefb;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --blue:#4bb3e6;--blue2:#4bb3e6;--orange:#e0a54a;--green:#3fc79a;--purple:#b79aec;--red:#e77;
  --ink:#e7eef0;--muted:#9bb0b7;--line:#284249;--card:#12252b;--bg:#0c181c;
  --dark:#0e2731;--code:#17303a;--fold:#132a31;--warnbg:#3a2f14;--workbg:#123027;--litbg:#122a38;--offbg:#241d38;}}
:root[data-theme="dark"]{
  --blue:#4bb3e6;--blue2:#4bb3e6;--orange:#e0a54a;--green:#3fc79a;--purple:#b79aec;--red:#e77;
  --ink:#e7eef0;--muted:#9bb0b7;--line:#284249;--card:#12252b;--bg:#0c181c;
  --dark:#0e2731;--code:#17303a;--fold:#132a31;--warnbg:#3a2f14;--workbg:#123027;--litbg:#122a38;--offbg:#241d38;}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--ink);
  font-family:"Microsoft YaHei","PingFang SC","Source Han Sans SC","Noto Sans CJK SC",-apple-system,Segoe UI,Roboto,Arial,sans-serif;
  line-height:1.85;font-size:16px;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
.wrap{display:flex;max-width:1560px;margin:0 auto;gap:30px;padding:0 22px;transition:margin-right .22s ease}
nav.toc{position:sticky;top:0;align-self:flex-start;width:238px;max-height:100vh;overflow-y:auto;padding:26px 6px 40px 0;font-size:13.5px;flex:0 0 238px}
nav.toc .brand{font-weight:700;color:var(--blue);font-size:14px;margin:4px 0 16px;line-height:1.5}
nav.toc a{display:block;color:var(--muted);text-decoration:none;padding:4px 12px;border-left:2px solid transparent;border-radius:0 6px 6px 0}
nav.toc a:hover{color:var(--ink);background:var(--card);border-left-color:var(--blue)}
main{flex:1 1 auto;min-width:0;max-width:900px;padding:24px 0 160px}
h1{font-size:26px;line-height:1.4;margin:.1em 0 .3em}
h2{font-size:21px;margin:2.4em 0 .6em;padding-bottom:.3em;border-bottom:2px solid var(--line)}
h2 .n{color:var(--blue);font-weight:800;margin-right:.45em}
h3{font-size:17.5px;margin:1.7em 0 .5em;color:var(--blue)}
h4{font-size:15px;margin:1.2em 0 .4em;font-weight:700}
p{margin:.7em 0}
a{color:var(--blue);text-decoration:none;border-bottom:1px solid color-mix(in srgb,var(--blue) 40%,transparent)}
a:hover{border-bottom-color:var(--blue)}
a.cite{font-size:.85em;white-space:nowrap;padding:0 2px}
ul,ol{margin:.5em 0;padding-left:1.5em}
li{margin:.35em 0}
hr{border:0;border-top:1px solid var(--line);margin:1.6em 0}
small{color:var(--muted)}
code{background:var(--code);padding:1px 6px;border-radius:5px;font-family:Consolas,monospace;font-size:.87em}
/* 悬停参数/术语（浮动标签由 JS 渲染，永不被裁切） */
.p{border-bottom:1.6px dotted var(--blue);cursor:help;font-weight:600;color:var(--blue2)}
.t{border-bottom:1.5px dotted var(--muted);cursor:help}
#floatTip{position:fixed;display:none;z-index:99999;background:var(--dark);color:#fff;padding:8px 12px;border-radius:8px;
  font-size:13px;max-width:300px;line-height:1.6;box-shadow:0 8px 26px rgba(0,0,0,.34);pointer-events:none}
:root[data-theme="dark"] #floatTip{background:#04121a;border:1px solid #2a4a54}
/* 徽章 */
.b{display:inline-block;font-size:11px;font-weight:800;padding:2px 9px;border-radius:20px;vertical-align:middle;margin:0 2px;white-space:nowrap;cursor:help}
.b.work{background:var(--workbg);color:var(--green);border:1.5px solid var(--green)}
.b.lit{background:var(--litbg);color:var(--blue);border:1.5px solid var(--blue)}
.b.off{background:var(--offbg);color:var(--purple);border:1.5px solid var(--purple)}
/* 卡片/提示条 */
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 20px;margin:1.2em 0}
.note{border-left:4px solid var(--blue);border-radius:0 8px 8px 0;padding:12px 18px;margin:1.2em 0;background:var(--card)}
.note.key{border-color:var(--green);background:var(--workbg)}
.note.watch{border-color:var(--orange);background:var(--warnbg)}
.note .lb{font-weight:700;display:block;margin-bottom:.25em}
/* 表格 */
.scroll{overflow-x:auto;margin:1.1em 0;border:1px solid var(--line);border-radius:10px}
table{border-collapse:collapse;width:100%;font-size:13.5px;background:var(--card)}
th,td{border:1px solid var(--line);padding:8px 11px;text-align:left;vertical-align:top}
th{background:var(--dark);color:#fff;font-weight:600}
tbody tr:nth-child(even){background:color-mix(in srgb,var(--card) 93%,var(--blue) 7%)}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums;font-family:"SF Mono",Consolas,monospace}
.up{color:var(--blue2);font-weight:600}.dn{color:var(--orange);font-weight:600}.top{font-weight:800;color:var(--red)}
/* 折叠 */
details{border:1px solid var(--line);border-radius:10px;margin:.9em 0;background:var(--fold);overflow:hidden}
details[open]{background:var(--card)}
summary{cursor:pointer;padding:11px 16px;font-weight:700;color:var(--blue);list-style:none;user-select:none;font-size:14px;display:flex;align-items:center;gap:7px}
summary::-webkit-details-marker{display:none}
/* 速览卡 */
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(158px,1fr));gap:12px;margin:1.1em 0}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:13px 15px}
.kpi .v{font-size:21px;font-weight:800;color:var(--blue);font-variant-numeric:tabular-nums}
.kpi .k{font-size:12.5px;color:var(--muted);margin-top:3px;line-height:1.5}
/* 图 */
figure{margin:1.5em 0;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;text-align:center}
figure img{max-width:100%;height:auto;border-radius:6px}
figcaption{font-size:13px;color:var(--muted);margin-top:.8em;text-align:left;line-height:1.65}
.topbar{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;padding:12px 0;border-bottom:2px solid var(--line);margin-bottom:.4em}
.meta{font-size:13px;color:var(--muted)}
button#tt{background:var(--card);border:1px solid var(--line);color:var(--ink);border-radius:20px;padding:6px 15px;cursor:pointer;font-size:13px}
.legend{font-size:13px;color:var(--muted);background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 16px;margin:1em 0}
@media(max-width:960px){nav.toc{display:none}.wrap{padding:0 15px}}
"""

# ----------------------------------------------------------------------------
# v3 的 <script>（逐字复用：floatTip 悬停标签 + 主题切换）
# ----------------------------------------------------------------------------
SCRIPT = r"""
(function(){
  /* 悬停浮动标签（贴 body，永不被裁切） */
  var tip=document.createElement('div');tip.id='floatTip';document.body.appendChild(tip);
  function showTip(el){var t=el.getAttribute('data-t');if(!t)return;tip.textContent=t;tip.style.display='block';
    var r=el.getBoundingClientRect(),tw=tip.offsetWidth,th=tip.offsetHeight;
    var left=r.left+r.width/2-tw/2;left=Math.max(8,Math.min(left,window.innerWidth-tw-8));
    var top=r.top-th-10;if(top<8)top=r.bottom+10;tip.style.left=left+'px';tip.style.top=top+'px';}
  document.addEventListener('mouseover',function(e){var el=e.target.closest('[data-t]');if(el)showTip(el);});
  document.addEventListener('mouseout',function(e){if(e.target.closest('[data-t]'))tip.style.display='none';});
  /* 主题切换 */
  document.getElementById('tt').addEventListener('click',function(){
    var e=document.documentElement.getAttribute('data-theme');
    var cur=e||(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');
    document.documentElement.setAttribute('data-theme',cur==='dark'?'light':'dark');});
})();
"""

# 顶部左侧 TOC（对齐 task 要求：摘要/①/②a/②b/③/④/⑤小鼠/⑥许可/总表/口径声明）
TOC = """<nav class="toc">
  <div class="brand">v3 §8 前四问<br>新切 9mer 结果落位</div>
  <a href="#s0">摘要与速览</a>
  <a href="#q1">① fusion 净优势</a>
  <a href="#q2a">②a geomean 唯一最优</a>
  <a href="#q2b">②b 免疫原类取 max</a>
  <a href="#q3">③ median vs geomean</a>
  <a href="#q4">④ max 非最优 / top-k</a>
  <a href="#q5">⑤ 小鼠数据</a>
  <a href="#q6">⑥ 许可条款核查</a>
  <a href="#summary">总表：四问 × 判定</a>
  <a href="#scope">口径声明</a>
</nav>"""

# 顶部注入的「摘要与速览」5 张判定卡；取值 100% 取自 md 各节「判定：」句 + 文末总表短语
KPIS = """<h2 id="s0">摘要与速览</h2>
<p class="meta">v3 §8「待讨论」前四问，在新切 9mer canonical + <code>--min_pep 8</code>（纳入 8 病人 / 29 工具）冻结口径下逐条落位。下为判定速览；每条的点估、95%CI/配对 p、样本量与 n=8 功效 caveat 见对应小节与文末总表。</p>
<div class="kpis">
  <div class="kpi"><div class="v">不可检测</div><div class="k">① fusion 相对最强单工具·净优势（证实旧断言）</div></div>
  <div class="kpi"><div class="v">未复现</div><div class="k">②a robustness 上 geomean 唯一最优</div></div>
  <div class="kpi"><div class="v">未复现</div><div class="k">②b 免疫原类工具取 max 最优</div></div>
  <div class="kpi"><div class="v">推翻</div><div class="k">③ median 略优 geomean → 实测 geomean 优</div></div>
  <div class="kpi"><div class="v">弱支持</div><div class="k">④ 单工具 max 非最优 / top-k 更好（严判未复现）</div></div>
</div>"""


# ----------------------------------------------------------------------------
# 行内格式：code / bold / 裸 URL 链接；先护 code 再转义再套 bold/URL
# ----------------------------------------------------------------------------
def esc(s: str) -> str:
    return _html.escape(s, quote=False)


def inline(text: str) -> str:
    codes = []

    def stash(m):
        codes.append(m.group(1))
        return f"\x00{len(codes) - 1}\x00"

    text = re.sub(r"`([^`]+)`", stash, text)
    text = esc(text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(
        r"(https?://[^\s)）]+)",
        r'<a href="\1" target="_blank" rel="noopener">\1</a>',
        text,
    )

    def restore(m):
        return "<code>" + esc(codes[int(m.group(1))]) + "</code>"

    return re.sub(r"\x00(\d+)\x00", restore, text)


# ----------------------------------------------------------------------------
# 块级解析：标题/hr/表格/有序表/无序表/段落
# ----------------------------------------------------------------------------
def parse_blocks(md: str):
    lines = md.split("\n")
    blocks = []
    i, n = 0, len(lines)
    while i < n:
        s = lines[i].strip()
        if s == "":
            i += 1
            continue
        if s.startswith("<!--"):  # 跳过 HTML 注释（drift 契约等，非正文）
            while i < n and "-->" not in lines[i]:
                i += 1
            i += 1
            continue
        if s == "---":
            blocks.append(("hr",))
            i += 1
            continue
        m = re.match(r"(#+)\s+(.*)", s)
        if m:
            blocks.append(("h", len(m.group(1)), m.group(2)))
            i += 1
            continue
        if s.startswith("|"):
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(lines[i].strip())
                i += 1
            blocks.append(("table", rows))
            continue
        if re.match(r"\d+\.\s", s):
            items = []
            while i < n and re.match(r"\d+\.\s", lines[i].strip()):
                items.append(re.sub(r"^\d+\.\s+", "", lines[i].strip()))
                i += 1
            blocks.append(("ol", items))
            continue
        if s.startswith("- "):
            items = []
            while i < n and lines[i].strip().startswith("- "):
                items.append(lines[i].strip()[2:])
                i += 1
            blocks.append(("ul", items))
            continue
        # 段落：并入后续非空、非块起始行（本 md 段落基本单行）
        para = [s]
        i += 1
        while i < n:
            t = lines[i].strip()
            if (
                t == ""
                or t.startswith(("|", "#", "- ", "---", "<!--"))
                or re.match(r"\d+\.\s", t)
            ):
                break
            para.append(t)
            i += 1
        blocks.append(("p", " ".join(para)))
    return blocks


def render_table(rows) -> str:
    def cells(r):
        return [c.strip() for c in r.strip().strip("|").split("|")]

    header = cells(rows[0])
    body = [cells(r) for r in rows[2:]]  # rows[1] 是 |---|---| 分隔行
    out = ['<div class="scroll"><table>', "<thead><tr>"]
    out.append("".join(f"<th>{inline(c)}</th>" for c in header))
    out.append("</tr></thead>\n<tbody>")
    for r in body:
        out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
    out.append("</tbody></table></div>")
    return "\n".join(out)


def b64_png(p: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode("ascii")


def render_figure(text: str) -> str:
    # text 形如「配图：Fig A（已落盘 `...figA...`，PNG+PDF）。」——按文件名 key 就地插图
    key = next((k for k in FIG_FILES if k in text), None)
    if key is None:
        return f"<p>{inline(text)}</p>"
    letter = FIG_LETTER[key]
    src = b64_png(FIG_FILES[key])
    cap = inline(text)  # 图注逐字取 md 的「配图：…」行
    return (
        f'<figure>\n  <img src="{src}" alt="图 {letter}">\n'
        f"  <figcaption>{cap}</figcaption>\n</figure>"
    )


def section_id(txt: str):
    for marker, sid in (
        ("①", "q1"),
        ("②a", "q2a"),
        ("②b", "q2b"),
        ("③", "q3"),
        ("④", "q4"),
        ("⑤", "q5"),
        ("⑥", "q6"),
    ):
        if txt.startswith(marker):
            return sid
    if txt.startswith("总表"):
        return "summary"
    if txt.startswith("口径声明"):
        return "scope"
    if txt.startswith("背景"):
        return "bg"
    return None


def render_para(text: str) -> str:
    t = text
    if t.startswith("配图："):
        return render_figure(t)
    if t.startswith("**判定："):  # 结论色块
        return f'<div class="note">{inline(t)}</div>'
    if t.startswith("**caveat") or t.startswith("**TODO**") or t.startswith("两点诚实说明"):
        return f'<div class="note watch">{inline(t)}</div>'  # 橙色警示条：去偏向关键
    if t.startswith("冻结口径"):
        return f'<div class="card">{inline(t)}</div>'
    if t.startswith("**日期**"):
        return f'<p class="meta">{inline(t)}</p>'
    return f"<p>{inline(t)}</p>"


# 段落末尾命中这些串 → 其后紧跟的列表整块并入 .note.watch（intro + 列表）
WATCH_LIST_TRIGGERS = ("避免误读：", "否则会高估这条的力度：")


def render(blocks) -> str:
    out = []
    summary_done = False
    wrap_list_watch = False
    watch_intro = ""
    for b in blocks:
        kind = b[0]

        if kind == "h":
            level, txt = b[1], b[2]
            if level == 1:
                out.append(f"<h1>{inline(txt)}</h1>")
            elif level == 2:
                # 首个 h2（背景）之前注入「摘要与速览」kpis
                if not summary_done:
                    out.append(KPIS)
                    summary_done = True
                sid = section_id(txt)
                idattr = f' id="{sid}"' if sid else ""
                out.append(f"<h2{idattr}>{inline(txt)}</h2>")
            else:
                out.append(f"<h{level}>{inline(txt)}</h{level}>")
            continue

        if kind == "hr":
            out.append("<hr>")
            continue

        if kind == "table":
            out.append(render_table(b[1]))
            continue

        if kind in ("ol", "ul"):
            tag = "ol" if kind == "ol" else "ul"
            body = "".join(f"<li>{inline(it)}</li>" for it in b[1])
            lst = f"<{tag}>{body}</{tag}>"
            if wrap_list_watch:
                out.append(
                    f'<div class="note watch"><span class="lb">{watch_intro}</span>{lst}</div>'
                )
                wrap_list_watch = False
                watch_intro = ""
            else:
                out.append(lst)
            continue

        if kind == "p":
            txt = b[1]
            if any(txt.rstrip().endswith(x) for x in WATCH_LIST_TRIGGERS):
                wrap_list_watch = True
                watch_intro = inline(txt)  # intro 作 .note.watch 的标签行
                continue
            out.append(render_para(txt))
            continue

    return "\n".join(out)


def main():
    if not MD.exists():
        sys.exit(f"[ERR] 缺 md 终稿 {MD}")
    for k, p in FIG_FILES.items():
        if not p.exists():
            sys.exit(f"[ERR] 缺图 {p}")

    md = MD.read_text(encoding="utf-8")
    body = render(parse_blocks(md))

    doc = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>关于 v3 §8 前四问：新切 9mer 结果落位 · 2026-07-09</title>
<style>{STYLE}</style>
</head>
<body>
<div class="wrap">
{TOC}
<main>
<div class="topbar">
  <div class="meta"><strong>关于 v3 §8 前四问：新切 9mer 结果落位</strong> · 2026-07-09</div>
  <button id="tt">切换深色/浅色</button>
</div>
{body}
<hr>
<p class="meta">本报告自包含、可离线阅读；图片已 base64 内嵌、无外链无 CDN；内容逐字取自 §8 四问回复稿终稿（已过 verifier + reviewer 双核），HTML 仅做排版。2026-07-09。</p>
</main>
</div>
<script>{SCRIPT}</script>
</body>
</html>
"""
    OUT.write_text(doc, encoding="utf-8")
    size = OUT.stat().st_size
    print(f"[DONE] {OUT}")
    print(f"       {size:,} 字节 ({size / 1024 / 1024:.2f} MB)")
    for k, p in FIG_FILES.items():
        print(f"       内嵌 {k}.png ({p.stat().st_size:,} 字节)")


if __name__ == "__main__":
    main()
