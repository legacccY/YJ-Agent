#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_report_v4.py — 把「QuantImmu 框架研究进展报告」md 终稿装配成
自包含单文件 HTML（研究型，非问答体）。

设计原则（对齐用户反馈）：
- 研究叙事，不是逐条答老师问；语言白话、零内部黑话/车轱辘话。
- 复用 v3/s89 的整套设计系统（深浅主题 / 折叠 details / 悬停浮标 floatTip /
  徽章 / KPI 卡 / 图 base64 内嵌），并补状态徽章（已完成/部分/未做）。
- 图 base64 内嵌，自包含可离线；无外链无 CDN。
- 出新文件不覆盖旧的。

md 方言（本脚本解析）：
  行内：**加粗**  `代码`  [文字](url)  裸URL
        [[work:文字]] / [[lit:文字]] / [[off:文字]]  三色徽章
        [[done]] / [[part]] / [[miss]]                状态徽章（已完成/部分/未做）
        {{术语|悬停解释}}                              悬停出中文浮标
  块级：# / ## §.. / ### / ####   标题（## 自动进 TOC + 锚点）
        ---                        分隔线
        | .. | .. |               表格（.scroll 包裹）
        1. / -                     有序 / 无序列表
        :::fig KEY | 图注          单行图指令（base64 内嵌）
        :::kpis ... :::            KPI 卡网格（每行「值 | 说明」）
        :::note [key|watch] ... :::  提示条（默认蓝 / key 绿 / watch 橙）
        :::details 摘要 ... :::     折叠区（内部再解析块级）
  （折叠/提示条内部支持标题/表格/列表/段落/图/嵌套 details。）

运行（主线跑，不派 agent 跑代码）：python report/build_report_v4.py
"""
import base64
import html as _html
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MD = HERE / "研究进展报告_QuantImmu框架_2026-07-10.md"
OUT = HERE / "研究进展报告_QuantImmu框架_2026-07-10.html"

FIGDIR = ROOT / "analysis" / "official" / "newcut9mer" / "figures"
FIG_FILES = {
    "figA": FIGDIR / "figA_newcut_fusion_no_net_gain.png",
    "figB": FIGDIR / "figB_newcut_selection_ladder.png",
    "figC": FIGDIR / "figC_newcut_max_vs_bestpooling.png",
    "figD": FIGDIR / "figD_newcut_pooling_lopo.png",
    "figE": FIGDIR / "figE_newcut_fusion_authoritative.png",
}

# ---------------------------------------------------------------------------
# 设计系统 <style>（承 v3/s89，+ 状态徽章 / kpi 变体 / 状态矩阵）
# ---------------------------------------------------------------------------
STYLE = r"""
:root{
  --blue:#0b6ea8;--blue2:#0072B2;--orange:#c77f00;--green:#0a8f5b;--purple:#6b4bb3;--red:#b23a48;
  --ink:#1b2b31;--muted:#5f767d;--line:#e0e8ea;--card:#ffffff;--bg:#f6f9f9;
  --dark:#123039;--code:#eef3f4;--fold:#f1f7f7;--warnbg:#fff6e6;--workbg:#e6f7ef;--litbg:#e8f1fd;--offbg:#f0eefb;--redbg:#fdecee;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --blue:#4bb3e6;--blue2:#4bb3e6;--orange:#e0a54a;--green:#3fc79a;--purple:#b79aec;--red:#e77;
  --ink:#e7eef0;--muted:#9bb0b7;--line:#284249;--card:#12252b;--bg:#0c181c;
  --dark:#0e2731;--code:#17303a;--fold:#132a31;--warnbg:#3a2f14;--workbg:#123027;--litbg:#122a38;--offbg:#241d38;--redbg:#3a1c22;}}
:root[data-theme="dark"]{
  --blue:#4bb3e6;--blue2:#4bb3e6;--orange:#e0a54a;--green:#3fc79a;--purple:#b79aec;--red:#e77;
  --ink:#e7eef0;--muted:#9bb0b7;--line:#284249;--card:#12252b;--bg:#0c181c;
  --dark:#0e2731;--code:#17303a;--fold:#132a31;--warnbg:#3a2f14;--workbg:#123027;--litbg:#122a38;--offbg:#241d38;--redbg:#3a1c22;}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--ink);
  font-family:"Microsoft YaHei","PingFang SC","Source Han Sans SC","Noto Sans CJK SC",-apple-system,Segoe UI,Roboto,Arial,sans-serif;
  line-height:1.85;font-size:16px;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
.wrap{display:flex;max-width:1580px;margin:0 auto;gap:30px;padding:0 22px}
nav.toc{position:sticky;top:0;align-self:flex-start;width:250px;max-height:100vh;overflow-y:auto;padding:26px 6px 40px 0;font-size:13.5px;flex:0 0 250px}
nav.toc .brand{font-weight:700;color:var(--blue);font-size:14px;margin:4px 0 14px;line-height:1.55}
nav.toc a{display:block;color:var(--muted);text-decoration:none;padding:4px 12px;border-left:2px solid transparent;border-radius:0 6px 6px 0;border-bottom:none}
nav.toc a:hover{color:var(--ink);background:var(--card);border-left-color:var(--blue)}
main{flex:1 1 auto;min-width:0;max-width:912px;padding:24px 0 160px}
h1{font-size:26px;line-height:1.42;margin:.1em 0 .3em}
h2{font-size:21px;margin:2.5em 0 .6em;padding-bottom:.3em;border-bottom:2px solid var(--line)}
h2 .n{color:var(--blue);font-weight:800;margin-right:.4em}
h3{font-size:17.5px;margin:1.7em 0 .5em;color:var(--blue)}
h4{font-size:15px;margin:1.2em 0 .4em;font-weight:700}
p{margin:.7em 0}
a{color:var(--blue);text-decoration:none;border-bottom:1px solid color-mix(in srgb,var(--blue) 40%,transparent)}
a:hover{border-bottom-color:var(--blue)}
ul,ol{margin:.5em 0;padding-left:1.5em}
li{margin:.35em 0}
hr{border:0;border-top:1px solid var(--line);margin:1.6em 0}
small{color:var(--muted)}
code{background:var(--code);padding:1px 6px;border-radius:5px;font-family:Consolas,monospace;font-size:.87em}
/* 公式（纯 HTML/CSS 渲染，免插件） */
.mf{font-family:"Cambria Math","Times New Roman",Georgia,serif;font-size:1.04em;white-space:nowrap}
.mf i,.mv{font-style:italic}
.frac{display:inline-flex;flex-direction:column;vertical-align:-0.55em;text-align:center;margin:0 .18em;line-height:1.15}
.frac>.num{border-bottom:1.4px solid currentColor;padding:0 .35em .05em}
.frac>.den{padding:.05em .35em 0}
.mf sub{font-size:.72em;vertical-align:-.28em}
.mf sup{font-size:.72em;vertical-align:.42em}
/* 悬停术语（浮标由 JS 渲染，永不被裁切） */
.t{border-bottom:1.5px dotted var(--blue);cursor:help;font-weight:600;color:var(--blue2)}
#floatTip{position:fixed;display:none;z-index:99999;background:var(--dark);color:#fff;padding:8px 12px;border-radius:8px;
  font-size:13px;max-width:320px;line-height:1.62;box-shadow:0 8px 26px rgba(0,0,0,.34);pointer-events:none}
:root[data-theme="dark"] #floatTip{background:#04121a;border:1px solid #2a4a54}
/* 徽章：来源三色 + 状态三色 */
.b{display:inline-block;font-size:11px;font-weight:800;padding:2px 9px;border-radius:20px;vertical-align:middle;margin:0 2px;white-space:nowrap}
.b.work{background:var(--workbg);color:var(--green);border:1.5px solid var(--green);cursor:help}
.b.lit{background:var(--litbg);color:var(--blue);border:1.5px solid var(--blue);cursor:help}
.b.off{background:var(--offbg);color:var(--purple);border:1.5px solid var(--purple);cursor:help}
.b.done{background:var(--workbg);color:var(--green);border:1.5px solid var(--green)}
.b.part{background:var(--warnbg);color:var(--orange);border:1.5px solid var(--orange)}
.b.miss{background:var(--redbg);color:var(--red);border:1.5px solid var(--red)}
/* 卡片 / 提示条 */
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 20px;margin:1.2em 0}
.note{border-left:4px solid var(--blue);border-radius:0 8px 8px 0;padding:12px 18px;margin:1.2em 0;background:var(--card)}
.note.key{border-color:var(--green);background:var(--workbg)}
.note.watch{border-color:var(--orange);background:var(--warnbg)}
.note .lb{font-weight:700;display:block;margin-bottom:.25em}
.note>:first-child{margin-top:0}.note>:last-child{margin-bottom:0}
/* 表格 */
.scroll{overflow-x:auto;margin:1.1em 0;border:1px solid var(--line);border-radius:10px}
table{border-collapse:collapse;width:100%;font-size:13.5px;background:var(--card)}
th,td{border:1px solid var(--line);padding:8px 11px;text-align:left;vertical-align:top}
th{background:var(--dark);color:#fff;font-weight:600}
tbody tr:nth-child(even){background:color-mix(in srgb,var(--card) 93%,var(--blue) 7%)}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums;font-family:"SF Mono",Consolas,monospace}
/* 折叠 */
details{border:1px solid var(--line);border-radius:10px;margin:.9em 0;background:var(--fold);overflow:hidden}
details[open]{background:var(--card)}
details>summary{cursor:pointer;padding:11px 16px;font-weight:700;color:var(--blue);list-style:none;user-select:none;font-size:14px;display:flex;align-items:center;gap:7px}
details>summary::-webkit-details-marker{display:none}
details>summary::before{content:"＋";color:var(--blue);font-weight:800;flex:0 0 auto}
details[open]>summary::before{content:"－"}
details>summary::after{content:"点击展开 ▾";margin-left:auto;flex:0 0 auto;color:var(--muted);font-size:11.5px;font-weight:600;background:var(--litbg);border:1px solid var(--line);padding:1px 9px;border-radius:12px;white-space:nowrap}
details[open]>summary::after{content:"点击收起 ▴"}
details>summary:hover{background:color-mix(in srgb,var(--card) 55%,var(--blue) 9%)}
details>summary:hover::after{background:var(--blue);color:#fff;border-color:var(--blue)}
.dbody{padding:2px 18px 14px}
.dbody>:first-child{margin-top:.4em}
/* 证据块（绿） */
details.ev>summary::after{content:"查看证据 ▾"}
details.ev[open]>summary::after{content:"收起 ▴"}
details.ev{background:color-mix(in srgb,var(--card) 82%,var(--green) 18%);border-color:color-mix(in srgb,var(--line) 60%,var(--green) 40%)}
details.ev>summary{color:var(--green)}
details.ev>summary::before{content:"✓";color:var(--green)}
/* KPI 速览卡 */
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(168px,1fr));gap:12px;margin:1.2em 0}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.kpi .v{font-size:19px;font-weight:800;color:var(--blue);font-variant-numeric:tabular-nums;line-height:1.25}
.kpi .k{font-size:12.5px;color:var(--muted);margin-top:5px;line-height:1.5}
/* 图 */
figure{margin:1.5em 0;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;text-align:center}
figure img{max-width:100%;height:auto;border-radius:6px}
figcaption{font-size:13px;color:var(--muted);margin-top:.8em;text-align:left;line-height:1.66}
figcaption .fl{font-weight:700;color:var(--ink)}
.topbar{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;padding:12px 0;border-bottom:2px solid var(--line);margin-bottom:.4em}
.meta{font-size:13px;color:var(--muted)}
button#tt{background:var(--card);border:1px solid var(--line);color:var(--ink);border-radius:20px;padding:6px 15px;cursor:pointer;font-size:13px}
@media(max-width:980px){nav.toc{display:none}.wrap{padding:0 15px}}
"""

SCRIPT = r"""
(function(){
  var tip=document.createElement('div');tip.id='floatTip';document.body.appendChild(tip);
  function showTip(el){var t=el.getAttribute('data-t');if(!t)return;tip.textContent=t;tip.style.display='block';
    var r=el.getBoundingClientRect(),tw=tip.offsetWidth,th=tip.offsetHeight;
    var left=r.left+r.width/2-tw/2;left=Math.max(8,Math.min(left,window.innerWidth-tw-8));
    var top=r.top-th-10;if(top<8)top=r.bottom+10;tip.style.left=left+'px';tip.style.top=top+'px';}
  document.addEventListener('mouseover',function(e){var el=e.target.closest('[data-t]');if(el)showTip(el);});
  document.addEventListener('mouseout',function(e){if(e.target.closest('[data-t]'))tip.style.display='none';});
  document.getElementById('tt').addEventListener('click',function(){
    var e=document.documentElement.getAttribute('data-theme');
    var cur=e||(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');
    document.documentElement.setAttribute('data-theme',cur==='dark'?'light':'dark');});
})();
"""


# ---------------------------------------------------------------------------
# KaTeX 0.16.11 离线资产注入（自包含、无 CDN）
# 由 fetch_and_inline_katex.py 预生成 _assets/katex_inline.{css,js}（字体已 base64）。
# 存在则内联进 STYLE / SCRIPT（两个 wrapper 报告都用 {eng.STYLE}/{eng.SCRIPT}，自动获得公式）；
# 缺资产时静默跳过，报告照常出，仅公式不渲染 —— 绝不因缺资产报错。
# ---------------------------------------------------------------------------
_KATEX_CSS = HERE / "_assets" / "katex_inline.css"
_KATEX_JS = HERE / "_assets" / "katex_inline.js"
if _KATEX_CSS.exists():
    STYLE += "\n/* ===== KaTeX 0.16.11 内联（离线，字体 base64）===== */\n"
    STYLE += _KATEX_CSS.read_text(encoding="utf-8")
if _KATEX_JS.exists():
    SCRIPT += "\n/* ===== KaTeX 0.16.11（katex + auto-render，离线）===== */\n"
    SCRIPT += _KATEX_JS.read_text(encoding="utf-8")
    # 独立 IIFE：DOM 就绪后对全文做公式渲染；资产缺失（无 renderMathInElement）时不报错。
    SCRIPT += r"""
(function(){
  function _renderMath(){
    if(window.renderMathInElement){
      renderMathInElement(document.body,{
        delimiters:[
          {left:'$$',right:'$$',display:true},
          {left:'$',right:'$',display:false}
        ],
        throwOnError:false
      });
    }
  }
  if(document.readyState==='loading'){
    document.addEventListener('DOMContentLoaded',_renderMath);
  }else{ _renderMath(); }
})();
"""


# ---------------------------------------------------------------------------
# 行内格式
# ---------------------------------------------------------------------------
def esc(s: str) -> str:
    return _html.escape(s, quote=False)


NUL = "\x00"


def inline(text: str) -> str:
    store = []

    def stash(kind, payload):
        store.append((kind, payload))
        return f"{NUL}{len(store) - 1}{NUL}"

    # -1 数学公式 $$...$$ / $...$：原样透传给浏览器里的 KaTeX auto-render 渲染。
    #    须在其余一切规则（%%raw、代码、徽章、esc、加粗…）之前 stash 掉，
    #    保证公式内容不被转义、不被 ** / `` / [[..]] 等规则吃掉。
    #    先 $$（display）再 $（inline），均非贪婪、单行。
    text = re.sub(r"\$\$(.+?)\$\$", lambda m: stash("math", (True, m.group(1))), text)
    text = re.sub(r"\$([^$]+?)\$", lambda m: stash("math", (False, m.group(1))), text)
    # 0 原始 HTML 透传 %%...%%（公式/分式用，不转义）
    text = re.sub(r"%%(.+?)%%", lambda m: stash("raw", m.group(1)), text)
    # 1 代码
    text = re.sub(r"`([^`]+)`", lambda m: stash("code", m.group(1)), text)
    # 2 悬停 {{术语|解释}}
    text = re.sub(r"\{\{([^|{}]+)\|([^{}]+)\}\}",
                  lambda m: stash("tip", (m.group(1), m.group(2))), text)
    # 3 徽章 [[work:..]] / [[done]]
    def badge(m):
        raw = m.group(1)
        if ":" in raw:
            cls, rest = raw.split(":", 1)
            if "|" in rest:                      # [[work:文字|自定义悬停]]
                label, tip = rest.split("|", 1)
                return stash("badge", (cls.strip(), label.strip(), tip.strip()))
            return stash("badge", (cls.strip(), rest.strip(), None))
        return stash("badge", (raw.strip(), None, None))
    text = re.sub(r"\[\[([^\]]+)\]\]", badge, text)
    # 4 md 链接 [文字](url)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)",
                  lambda m: stash("link", (m.group(1), m.group(2))), text)
    # 5 转义
    text = esc(text)
    # 6 加粗
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    # 7 裸 URL
    text = re.sub(r"(?<![\">])(https?://[^\s)）]+)",
                  r'<a href="\1" target="_blank" rel="noopener">\1</a>', text)

    BADGE_TXT = {"done": "已完成", "part": "部分", "miss": "未做"}
    BADGE_DEFAULT_TIP = {
        "work": "本项目在这次评测中的处理 / 决定",
        "lit": "引自公开发表的论文 / 通行做法，均带可点链接",
        "off": "引自各工具官方的设定 / 文档",
    }

    def restore(m):
        kind, payload = store[int(m.group(1))]
        if kind == "math":
            disp, expr = payload              # 带定界符原样吐回，交浏览器 KaTeX 渲染
            return f"$${expr}$$" if disp else f"${expr}$"
        if kind == "raw":
            return payload                    # 原始 HTML（公式），不转义
        if kind == "code":
            return "<code>" + esc(payload) + "</code>"
        if kind == "tip":
            term, tp = payload
            return f'<span class="t" data-t="{esc(tp)}">{esc(term)}</span>'
        if kind == "badge":
            cls, txt, tip = payload
            label = txt if txt is not None else BADGE_TXT.get(cls, cls)
            if tip is None:
                tip = BADGE_DEFAULT_TIP.get(cls)   # work/lit/off 有默认悬停；done/part/miss 无
            data_t = f' data-t="{esc(tip)}"' if tip else ""
            return f'<span class="b {esc(cls)}"{data_t}>{esc(label)}</span>'
        if kind == "link":
            txt, url = payload
            return f'<a href="{esc(url)}" target="_blank" rel="noopener">{esc(txt)}</a>'
        return ""

    return re.sub(rf"{NUL}(\d+){NUL}", restore, text)


# ---------------------------------------------------------------------------
# 块级解析（支持 ::: 折叠 / 提示条 / kpis / fig 指令，内部递归）
# ---------------------------------------------------------------------------
def parse_blocks(lines):
    blocks = []
    i, n = 0, len(lines)
    while i < n:
        raw = lines[i]
        s = raw.strip()
        if s == "":
            i += 1
            continue
        if s.startswith("<!--"):
            while i < n and "-->" not in lines[i]:
                i += 1
            i += 1
            continue
        # ::: 指令
        m = re.match(r":::(\w+)(.*)$", s)
        if m:
            directive = m.group(1)
            arg = m.group(2).strip()
            # 块指令：吃到匹配的 ::: （支持一层嵌套 details）
            # fig 走同一路径：用开头行的 arg，闭合 ::: 被吃掉，忽略内部
            depth = 1
            inner = []
            i += 1
            while i < n:
                ln = lines[i]
                st = ln.strip()
                if re.match(r":::\w", st):
                    depth += 1
                    inner.append(ln)
                    i += 1
                    continue
                if st == ":::":
                    depth -= 1
                    i += 1
                    if depth == 0:
                        break
                    inner.append(ln)
                    continue
                inner.append(ln)
                i += 1
            blocks.append((directive, arg, inner))
            continue
        if s == "---":
            blocks.append(("hr",))
            i += 1
            continue
        hm = re.match(r"(#{1,4})\s+(.*)", s)
        if hm:
            blocks.append(("h", len(hm.group(1)), hm.group(2)))
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
        # 段落（并入后续普通行）
        para = [s]
        i += 1
        while i < n:
            t = lines[i].strip()
            if (t == "" or t.startswith(("|", "#", "- ", "---", "<!--", ":::"))
                    or re.match(r"\d+\.\s", t)):
                break
            para.append(t)
            i += 1
        blocks.append(("p", " ".join(para)))
    return blocks


def render_table(rows) -> str:
    def cells(r):
        return [c.strip() for c in r.strip().strip("|").split("|")]
    header = cells(rows[0])
    body = [cells(r) for r in rows[2:] if set(r.strip()) - set("|-: ")] if len(rows) > 2 else []
    out = ['<div class="scroll"><table>', "<thead><tr>"]
    out.append("".join(f"<th>{inline(c)}</th>" for c in header))
    out.append("</tr></thead>\n<tbody>")
    for r in body:
        out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
    out.append("</tbody></table></div>")
    return "\n".join(out)


def b64_png(p: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode("ascii")


def render_fig(arg: str) -> str:
    if "|" in arg:
        key, cap = arg.split("|", 1)
    else:
        key, cap = arg, ""
    key = key.strip()
    p = FIG_FILES.get(key)
    if not p or not p.exists():
        return f'<p><em>[图缺失：{esc(key)}]</em></p>'
    return (f'<figure>\n  <img src="{b64_png(p)}" alt="{esc(key)}">\n'
            f'  <figcaption>{inline(cap.strip())}</figcaption>\n</figure>')


def render_kpis(inner) -> str:
    out = ['<div class="kpis">']
    for ln in inner:
        s = ln.strip()
        if not s or "|" not in s:
            continue
        v, k = s.split("|", 1)
        out.append(f'  <div class="kpi"><div class="v">{inline(v.strip())}</div>'
                   f'<div class="k">{inline(k.strip())}</div></div>')
    out.append("</div>")
    return "\n".join(out)


HEADINGS = []  # (id, text) for TOC


def slug(text: str, idx: int) -> str:
    return f"sec{idx}"


def render(blocks) -> str:
    out = []
    for b in blocks:
        kind = b[0]
        if kind == "h":
            level, txt = b[1], b[2]
            if level == 2:
                sid = f"sec{len(HEADINGS)}"
                HEADINGS.append((sid, txt))
                # 段号高亮：以「§」或数字开头的前缀染蓝
                mm = re.match(r"(§?[\d.]+|概览|附录[A-Z]?)\s+(.*)", txt)
                if mm:
                    inner_h = f'<span class="n">{esc(mm.group(1))}</span>{inline(mm.group(2))}'
                else:
                    inner_h = inline(txt)
                out.append(f'<h2 id="{sid}">{inner_h}</h2>')
            else:
                out.append(f"<h{level}>{inline(txt)}</h{level}>")
            continue
        if kind == "hr":
            out.append("<hr>")
            continue
        if kind == "table":
            out.append(render_table(b[1]))
            continue
        if kind == "ol" or kind == "ul":
            tag = "ol" if kind == "ol" else "ul"
            body = "".join(f"<li>{inline(it)}</li>" for it in b[1])
            out.append(f"<{tag}>{body}</{tag}>")
            continue
        if kind == "p":
            out.append(f"<p>{inline(b[1])}</p>")
            continue
        if kind == "fig":
            out.append(render_fig(b[1]))
            continue
        if kind == "kpis":
            out.append(render_kpis(b[2]))
            continue
        if kind == "note":
            cls = b[1].strip()
            cls = f" {cls}" if cls in ("key", "watch") else ""
            out.append(f'<div class="note{cls}">{render(parse_blocks(b[2]))}</div>')
            continue
        if kind == "details":
            summary = inline(b[1].strip())
            out.append(f'<details><summary>{summary}</summary>'
                       f'<div class="dbody">{render(parse_blocks(b[2]))}</div></details>')
            continue
        if kind == "ev":
            summary = inline(b[1].strip())
            out.append(f'<details class="ev"><summary>{summary}</summary>'
                       f'<div class="dbody">{render(parse_blocks(b[2]))}</div></details>')
            continue
    return "\n".join(out)


def build_toc() -> str:
    links = "\n".join(f'  <a href="#{sid}">{esc(txt)}</a>' for sid, txt in HEADINGS)
    return ('<nav class="toc">\n'
            '  <div class="brand">QuantImmu 框架<br>研究进展报告 · 2026-07-10</div>\n'
            f'{links}\n</nav>')


def main():
    if not MD.exists():
        sys.exit(f"[ERR] 缺 md 终稿 {MD}")
    missing = [k for k, p in FIG_FILES.items() if not p.exists()]
    if missing:
        print(f"[WARN] 缺图 {missing}（将以占位提示渲染）")

    md = MD.read_text(encoding="utf-8")
    body = render(parse_blocks(md.split("\n")))
    toc = build_toc()

    doc = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>QuantImmu 框架研究进展报告 · 2026-07-10</title>
<style>{STYLE}</style>
</head>
<body>
<div class="wrap">
{toc}
<main>
<div class="topbar">
  <div class="meta"><strong>QuantImmu：突变级定量免疫原性评测框架 · 研究进展报告</strong> · 2026-07-10</div>
  <button id="tt">切换深色/浅色</button>
</div>
{body}
<hr>
<p class="meta">本报告自包含、可离线阅读；图片已 base64 内嵌，无外链无 CDN。全部数值取自 <code>analysis/official/newcut9mer/</code> 下 R1–R7 结果表，经独立 Bash 核对；术语首次出现均有解释，鼠标悬停虚线词可看释义。</p>
</main>
</div>
<script>{SCRIPT}</script>
</body>
</html>
"""
    OUT.write_text(doc, encoding="utf-8")
    size = OUT.stat().st_size
    print(f"[DONE] {OUT}")
    print(f"       {size:,} 字节 ({size / 1024 / 1024:.2f} MB) · {len(HEADINGS)} 个 h2 章节")


if __name__ == "__main__":
    main()
