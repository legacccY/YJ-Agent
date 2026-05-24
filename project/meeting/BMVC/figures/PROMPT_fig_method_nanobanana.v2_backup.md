# NanoBanana Prompt — BMVC Method Figure v2 (TS-vs-QCTS contrast)

**配色**：Okabe-Ito（Steel Blue #0072B2 + Warm Orange #E69F00 + Bluish Green #009E73）
**比例**：16:9 横向
**目标输出**：PNG 1920×1080 (NanoBanana 原生) → 后期 vectormagic / Illustrator Image Trace 转 SVG → PDF
**保存为**：`figures/fig_method.pdf`（覆盖现版本）+ `figures/fig_method.svg`
**版本说明**：v2 — 上下双路对比布局，强调 "TS reversal → QCTS fix" 故事弧，零具体数字，icon-driven。v1 备份在 `PROMPT_fig_method_nanobanana.v1_backup.md`。

---

## 设计要点（对应 STORY_FRAMEWORK 三条 claim）

| Claim | 视觉承载 |
|---|---|
| 1 — TS reversal 是真实现象 | Path A 末端红色 ⚠ + "ρ sign-flip" 标签（不给具体数值） |
| 2 — QCTS 是 universal post-hoc fix | Path B 末端绿色 ✓ + 公式 `T(q̄)=softplus(T₀+α(1−q̄))` + 末段 3 backbone icon 排排坐 |
| 3 — q̄ 是 universal scalar | 顶部 5-head IQA fan + 共享弧形 dotted arrow 把 q̄ 同时送给 ITB 分层和 QCTS |

**视觉中心**：图正中两个温度计模块（🌡 TS vs 🌡 QCTS）+ 末端 ⚠/✓ icon 的对比——决策瞬间。

**严禁**：任何 ρ、QCDI、ECE、AUC、n=300、+0.241 等具体结果数字。唯一允许的公式是 `T(q̄)=softplus(T₀+α(1−q̄))`。

---

## 使用方法

1. 复制下方 **整块** 英文 prompt（含 STYLE SPECIFICATIONS 段落）
2. 粘贴到 NanoBanana / Gemini Vision
3. 若首版上下对齐不严或 icon 过大，加 "tighter vertical alignment between Path A and Path B; shrink all icons to 14 px max"
4. 满意后导出 PNG → vectormagic 转 SVG → Illustrator 微调 → 导出 PDF 覆盖 `figures/fig_method.pdf`

---

## Prompt（复制粘贴整段）

```
A highly detailed academic framework diagram for a medical image
calibration paper, in the style of top-tier CVPR / NeurIPS / BMVC
publications. The diagram contrasts two post-hoc calibration paths on
the same frozen dermoscopy classifier: Standard Temperature Scaling
(failure path) versus Quality-Conditioned Temperature Scaling (our fix).
A narrow Inference column on the right shows the deployed single-image
pipeline. Clean white background, 16:9 aspect ratio, rich monochrome
icons, no numerical results, no decorative noise.

=== GLOBAL LAYOUT ===

Canvas split by a thin Light Grey (#CCCCCC) vertical divider into two
zones:
  - LEFT 70%  = TRAINING (titled "TRAINING — post-hoc calibration on
                ITB validation split", small-caps Steel Blue #0072B2 9-pt
                header)
  - RIGHT 30% = INFERENCE (titled "INFERENCE — single image", small-caps
                Steel Blue 9-pt header)

Inside the TRAINING zone, three horizontal bands stack top-to-bottom
with 12 px gaps:
  (1) TOP BAND     — shared 5-head IQA module producing q-bar
  (2) MIDDLE BAND  — two parallel pipelines (Path A above, Path B below)
                     sharing the same backbone logit z, diverging into
                     two different temperature modules and two different
                     end-state icons (warning vs check)
  (3) BOTTOM BAND  — 3 backbone icon strip (CNN / ViT / Hybrid) tagged
                     with check marks, captioned "QCTS generalises across
                     backbones"

A single Warm Orange #E69F00 dotted arrow arches from the q-bar pill in
the TOP BAND, over Path A, landing on the QCTS module in Path B; label
above its arch in Medium Grey #666666 6-pt italic "q-bar shared".

Main data-flow arrows are Dark Grey #4D4D4D, 1.5 pt, with simple
arrowheads. Inter-module spacing 12-16 px. All rectangles have 4-px
corner radius.

=== TOP BAND : 5-head IQA (shared) ===

A faint Grey #F7F7F7 background pill groups this band. Inside, left to
right:

(a) A small (~80x80 px) rounded circular crop of a representative
    pink-brown dermoscopy lesion image labelled "x  dermoscopy input"
    below in Charcoal #333333 7-pt sans-serif.

(b) An arrow flows rightward into a vertical fan of FIVE parallel small
    CNN icons, each a tiny white rounded-rectangle (~35x20 px) with
    Steel Blue #0072B2 1-pt border, stacked vertically with 4-px gaps.
    Each icon contains a tiny monochrome thumbnail (no text data values):
        - Sharpness     : a small blur-kernel grid thumbnail
        - Brightness    : a small luminance histogram thumbnail
        - Completeness  : a small crop-boundary frame thumbnail
        - Colour temp.  : a small RGB channel bar thumbnail
        - Contrast      : a small contrast-curve thumbnail
    Tiny small-caps 6-pt labels sit to the right of each icon (one to
    two words, no numbers).

(c) The five outputs converge into a single horizontal "mean" pill
    (Light Grey #CCCCCC border, white fill, label "mean") and emit one
    arrow into a prominent Steel Blue #0072B2-bordered pill containing
    the bold label "q-bar" (no numerical range, no interval brackets).

(d) Below the fan, a Medium Grey #666666 6-pt italic caption: "frozen
    5-head IQA module".

=== MIDDLE BAND : two parallel pipelines ===

Both pipelines share the same backbone logit z but diverge at the
temperature step. They are drawn as two horizontal strips, vertically
aligned column-by-column so the reader can compare them at a glance.
Each strip is a white rounded-rectangle of equal width and equal height,
stacked top (Path A) above bottom (Path B) with 8 px gap.

--- PATH A : Standard Temperature Scaling (failure path) ---

Outer border: Warm Orange #E69F00 1.5 pt DASHED (signalling caution).
Header label centred at the top of the strip in small-caps 8 pt
Warm Orange: "PATH A — STANDARD TS".

Inside, six small modules in a single row from left to right with thin
horizontal arrows between them:
  1. A small circular dermoscopy crop icon (same as TOP BAND but smaller)
     captioned "x".
  2. A white rounded-rectangle labelled "Backbone f_theta" with a small
     ❄ snowflake icon in the top-right corner (Medium Grey #666666) to
     mark "frozen". Inside, a tiny abstract layered-blocks silhouette.
  3. A small Charcoal #333333 italic 7-pt label "z" sitting on the
     connecting arrow (no dimension, no R^K).
  4. A white rounded-rectangle labelled "Standard TS" with a small
     thermometer icon (🌡 monochrome charcoal). A tiny 🔥 flame icon at
     the top-right corner marks "fitted on validation NLL".
  5. A connecting arrow labelled "p" (no superscript, no simplex
     notation).
  6. A prominent end-state icon: a Warm Orange #E69F00 warning triangle
     ⚠ at ~28x28 px, accompanied by a small Charcoal label below
     "ρ sign-flip" (text only, NO numerical value). Optional tiny inset:
     a 22x22 px reliability-diagram thumbnail showing a curve that
     crosses the diagonal (monochrome charcoal).

--- PATH B : QCTS (our fix) ---

Outer border: Bluish Green #009E73 1.5 pt SOLID (signalling our
contribution).
Header label centred at the top of the strip in small-caps 8 pt
Bluish Green: "PATH B — QCTS (ours)".

Inside, six small modules in the same column positions as Path A:
  1. The same small circular dermoscopy crop icon captioned "x".
  2. The same Backbone f_theta box with ❄ snowflake (identical to
     Path A — emphasise the SHARED backbone).
  3. The same "z" italic label on the connecting arrow.
  4. A white rounded-rectangle labelled "QCTS" with a small thermometer
     icon (🌡 monochrome charcoal) AND a small dial / gauge icon next
     to it suggesting "tunable by q-bar". A tiny 🔥 flame icon in the
     top-right corner marks "fitted (T_0, alpha)". Inside this box,
     centred, one single line of math in 8-pt math font:
         T(q-bar) = softplus( T_0 + alpha * (1 - q-bar) )
     (this is the ONLY formula allowed in the entire figure).
     An incoming Warm Orange dotted arrow enters this box from the top
     (the q-bar shared arch from the TOP BAND).
  5. A connecting arrow labelled "p".
  6. A prominent end-state icon: a Bluish Green #009E73 check mark ✓ at
     ~28x28 px, accompanied by a small Charcoal label below "calibrated"
     (NO numerical value). Optional tiny inset: a 22x22 px
     reliability-diagram thumbnail showing a curve hugging the diagonal
     (monochrome charcoal).

The strict column alignment between Path A and Path B (input → backbone
→ z label → temperature module → p label → end-state) is the central
visual device of the figure: a reader's eye scans top vs bottom in each
column to spot the difference.

=== BOTTOM BAND : universality strip ===

Below Path B, a thin horizontal strip with a faint Grey #F7F7F7 fill
contains THREE small backbone icons arranged horizontally, evenly spaced,
each ~50x36 px:
    [CNN icon]   [ViT icon]   [Hybrid icon (e.g. ConvNeXt / Swin)]
Each icon is a tiny abstract silhouette in Charcoal #333333:
    - CNN     : stacked rectangular conv blocks
    - ViT     : a grid of patch tokens + a small attention-head glyph
    - Hybrid  : layered blocks with a small attention overlay
Below each icon, a tiny Bluish Green #009E73 ✓ check mark and the
backbone family name in 6-pt small-caps Charcoal.

Centred caption below the strip in Medium Grey #666666 7-pt italic:
"QCTS generalises across backbones".

=== INFERENCE COLUMN (right 30%) ===

A self-contained panel with faint Grey #F7F7F7 background fill,
separated from TRAINING by the vertical divider line. Header at the
top in small-caps Steel Blue 9-pt: "INFERENCE — single image".

Vertical stack of compact modules with downward arrows (1.5 pt Dark
Grey):
  1. A small circular dermoscopy crop icon (~50x50 px) captioned "x".
  2. A tiny condensed IQA fan icon (5 stacked mini-rectangles) →
     a small Steel Blue-bordered pill labelled "q-bar".
  3. A small Backbone f_theta box with ❄ snowflake (smaller version of
     Path A/B backbone).
  4. A small QCTS box (Bluish Green border) with the abbreviation
     "QCTS(q-bar)" only — no formula here (formula already in Path B).
  5. A small softmax pill labelled "softmax".
  6. End-state: a small horizontal probability bar-chart thumbnail
     (~50x24 px) showing 2 bars (one in Bluish Green for the
     calibrated-confidence class), captioned in Bluish Green 7-pt
     bold "calibrated p".

NO loop-back arrows, NO duplicate IQA fan (the inference IQA is a
condensed version of the TRAINING TOP BAND).

=== LEGEND STRIP (bottom of canvas) ===

Centred horizontal legend across the lower edge of the canvas
(below the universality strip and below the inference panel), thin
Light Grey #CCCCCC dotted top border. Five compact entries in a single
row, each entry = small icon + 7-pt Charcoal label:

  ❄ frozen weights   🔥 fitted parameters (T_0, alpha)   📷 input image
  ⚠ TS reversal      ✓ calibrated output

No box around the legend; the dotted top border alone separates it from
the main figure. NO data values inside the legend.

=== STYLE SPECIFICATIONS ===

PALETTE (Okabe-Ito, exactly 3 saturated colours):
  Steel Blue       #0072B2  — IQA module borders, stage headers,
                              main arrows, q-bar pill border
  Warm Orange      #E69F00  — Path A dashed border, ⚠ warning, top
                              shared-q-bar dotted arch
  Bluish Green     #009E73  — Path B solid border, ✓ check, calibrated
                              probability bar, universality check marks
  Module fill      #FFFFFF  — every rectangular module
  Area backdrop    #F7F7F7  — TOP BAND, BOTTOM BAND, INFERENCE panel
                              (very subtle)
  Standard border  #CCCCCC  — separators, divider line, mean pill
  Body text        #333333  — primary labels
  Arrow / line     #4D4D4D  — connecting arrows (1.5 pt)
  Secondary text   #666666  — captions, italic sub-labels

NO other colours. NO gradients, NO drop shadows, NO 3D effects, NO
glow, NO photographic noise, NO watercolour textures.

TYPOGRAPHY:
  Clean grotesque sans-serif (Inter / Helvetica / DejaVu Sans).
  Stage headers      : small-caps, 9 pt, Steel Blue
  Path / band labels : small-caps, 8 pt, in the path's accent colour
  Module titles      : bold, 8 pt, Charcoal
  Sub-labels         : regular, 7 pt, Charcoal
  Italic captions    : 6-7 pt, Medium Grey
  Math formula       : 8 pt math font (single allowed formula in QCTS box)
  NO decorative fonts, NO emojis except the symbol set used as icons
  (❄ 🔥 📷 ⚠ ✓ 🌡).

GEOMETRY:
  All rectangles: 4 px corner radius.
  Border thickness: standard 1 pt, emphasised modules 1.5 pt.
  Path A border: DASHED. Path B border: SOLID. All other borders solid.
  Arrow strokes: 1.5 pt solid; only the top shared-q-bar arch is dotted.
  Internal padding: 6-8 px. Inter-module gap: 12-16 px.
  Strict column alignment between Path A and Path B (same x-positions
  for input, backbone, z label, temperature module, p label, end-state).

INFORMATION DENSITY:
  Every module contains either an icon or a short label, never both
  longer than one line. Embedded thumbnails (~12-18 px) are flat
  monochrome charcoal on white.
  NO axis tick labels, NO numerical results, NO sample sizes, NO
  ECE / AUC / QCDI / rho values, NO interval brackets like [0,1].
  The ONLY math expression in the figure is the QCTS formula inside
  the Path B QCTS module:
      T(q-bar) = softplus(T_0 + alpha * (1 - q-bar))

GLOBAL CHECK:
  - >= 70% of canvas area is pure white.
  - Exactly 3 saturated colours appear (Steel Blue, Warm Orange,
    Bluish Green); all other elements are greyscale.
  - The figure must remain readable in 1-bit black-and-white print
    (colour redundancy: dashed-vs-solid border + ⚠-vs-✓ icon both
    distinguish Path A from Path B without colour).
  - Aspect ratio strictly 16:9. Output resolution 1920x1080 minimum.
  - Path A and Path B occupy strictly the same horizontal column
    positions; visual diff between rows is the takeaway.
```

---

## 调整指令（若首版不满意）

| 问题 | 追加指令 |
|------|---------|
| 上下两路未严格对齐 | "enforce strict column alignment between Path A and Path B: the input icon, backbone box, z label, temperature module, p label, and end-state must share identical x-positions across rows" |
| Path A 看上去不像 failure | "make Path A border strictly DASHED Warm Orange and place a larger ⚠ icon at its end; Path B border strictly SOLID Bluish Green with ✓" |
| q-bar 共享弧太轻 | "make the top dotted q-bar arch Warm Orange 1.5 pt with clearly visible arrowhead landing on the QCTS box; label 'q-bar shared' in italic Medium Grey above its apex" |
| 末端 universality strip 太挤 | "give the 3-backbone strip its own horizontal band with 16 px padding above and below; centre the row; backbone icons exactly 50 px wide each" |
| Inference column 太宽 | "narrow the inference column to exactly 28% canvas width, stack modules vertically with 10 px gaps" |
| 出现数字 / 数据 | "remove ALL numerical labels, sample sizes, interval brackets, axis ticks; keep ONLY the symbolic formula T(q-bar)=softplus(T_0+alpha(1-q-bar)) inside the QCTS box" |
| 颜色饱和 | "desaturate borders by 15%, ensure >=70% white area; keep only Steel Blue, Warm Orange, Bluish Green saturated, all else greyscale" |
| 模块文字溢出 | "abbreviate sub-labels to <=12 characters; if a label still overflows, drop it in favour of the module's icon" |

---

## 备份与覆盖

原 v1 prompt 已备份在 `figures/PROMPT_fig_method_nanobanana.v1_backup.md`。生成新版 PNG 后：

```bash
# 旧 SVG / PDF 也建议备份
cp figures/fig_method.svg figures/fig_method.v1_backup.svg
cp figures/fig_method.pdf figures/fig_method.v1_backup.pdf

# 转换流程
# 1. NanoBanana 导出 PNG -> 命名 fig_method.png
# 2. 用 vectormagic.com 或 Illustrator Image Trace 转 SVG -> fig_method.svg
# 3. 用 Illustrator / Inkscape 微调文字 / 对齐
# 4. 导出 PDF -> fig_method.pdf
```

满意后用新 PDF 覆盖原文件，主文 LaTeX 无需改 `\includegraphics{figures/fig_method}`。
