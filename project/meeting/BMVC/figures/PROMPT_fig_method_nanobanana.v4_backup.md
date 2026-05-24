# NanoBanana Prompt — BMVC Method Figure v4 (ITB | QCTS split, CVPR-polish, innovation-forward)

**配色**：Okabe-Ito（Steel Blue #0072B2 / Warm Orange #E69F00 / Bluish Green #009E73）
**比例**：16:9 横向
**目标输出**：PNG 1920×1080 → 转 SVG/PDF 覆盖 `figures/fig_method.{svg,pdf}`
**版本说明**：v4 — 左 ITB + 右 QCTS 两半结构，顶部贯穿 q̄ pipe，强调"q̄ 同时驱动两边"是核心 novelty。CVPR-style 干净排版，每个新颖元素加 ★ 创新徽章。前面 v1/v2 备份保留。

---

## 设计意图（每条都是创新点）

| 半边 | 创新点 (要在图里显式徽章 ★) |
|---|---|
| 左 ITB | **★1 quality-stratified benchmark**：先用 q̄ 把测试集分 4 strata，再独立评估 (vs flat test set) |
| 顶部 q̄ pipe | **★2 single scalar drives BOTH stratification AND calibration**：q̄ 同时进 ITB 分桶 和 QCTS 温度（前人 post-hoc 校准没人这么做） |
| 右 QCTS | **★3 T 是 q̄ 的函数**：温度曲线 T(q̄)，不是 constant T (vs Standard TS) |
| 右 QCTS 内 | **★4 from inductive biases**：B1 monotonicity + B2 positivity + B3 smoothness → softplus（不是 ad-hoc 拟合） |

**严禁**：任何 ρ / QCDI / ECE / AUC 数值；样本量；Q-VIB 字样；冗余文字。
**唯一允许公式**：右半 QCTS 模块内的 `T(q̄) = softplus(T₀ + α(1−q̄))` 一行。

---

## 使用方法

1. 复制下方整段 prompt 喂 NanoBanana / Gemini Vision
2. 若 ★ 徽章不显眼，加 "make every ★ innovation badge a small filled Bluish Green star with 'NEW' or '★ ours' caption beside it"
3. 若 T(q̄) 曲线和 Std TS 直线对比不强，加 "in the central chart, overlay the orange dashed horizontal Std TS line and the green softplus QCTS curve in the SAME axes, with a small annotation arrow pointing at the gap labelled 'quality-aware shift'"
4. 选 1 张 → vectormagic 转 SVG → Illustrator 微调 → 覆盖 fig_method.pdf

---

## Prompt（复制粘贴整段）

```
A polished CVPR / NeurIPS top-conference style framework figure for a
medical image calibration paper. The figure is split into TWO halves
joined by a horizontal q-bar pipe at the top: LEFT HALF shows the
construction of a quality-stratified benchmark ITB, RIGHT HALF shows
Quality-Conditioned Temperature Scaling (QCTS). The figure must look
exactly like a classic CVPR method overview: crisp rectangular module
blocks, light-grey dataflow arrows with italic dimension labels, every
contribution clearly marked with a small "★ ours" star badge, generous
white space, no decorative noise, no 3D, no glow. Information density
is high but every label is short (1-4 words). Aspect ratio 16:9.

=== CVPR-STYLE GLOBAL POLISH ===

- Canvas: pure white #FFFFFF, 1920x1080 px.
- All rectangles: 4-px corner radius. Border thickness 1 pt standard,
  1.5 pt emphasised, 2 pt for "★ ours" contribution boxes.
- Dataflow arrows: Dark Grey #4D4D4D, 1.5 pt, 12-degree open
  chevron arrowheads, all strictly horizontal or vertical (no curves
  except the top q-bar pipe and the manifold split).
- Module fills: pure white #FFFFFF.
- Panel backdrops: very faint Grey #F7F7F7, near-invisible.
- Each panel grouped under a small-caps Charcoal #333333 header in
  14 pt bold, with a thin Light Grey #CCCCCC horizontal rule beneath
  the header.
- Each new contribution carries a small filled Bluish Green #009E73
  five-point star badge (~14 px) with a 7-pt small-caps Bluish Green
  caption beside it, e.g. "NEW", "★ OURS", "B1+B2+B3".
- Dataflow arrows carry tiny italic Mid Grey 7-pt dimension labels
  (e.g. "x", "z", "q-bar", "T(q-bar)", "p") sitting just above the arrow.

=== TOP : SHARED q-bar PIPE (the key novelty link) ===

A horizontal Warm Orange #E69F00 thick rounded pipe (8-pt stroke) runs
across the full width of the canvas at y ~ 12% from the top, slightly
above both half-headers. Centred on this pipe, a prominent Steel Blue
#0072B2 capsule (~140x60 px) with bold 26-pt centred symbol "q-bar"
(letter q with a clean overline). To the left of the capsule, a short
inflow arrow from a small "5-head IQA" icon (a fan of 5 tiny stacked
mini-rects with a small ❄ snowflake corner) feeds into the q-bar
capsule. From the q-bar capsule, TWO orange drop-arrows descend: one
into the top of the LEFT half (feeding ITB stratification), one into
the top of the RIGHT half (feeding QCTS temperature).

Centred above the q-bar capsule, a small filled Bluish Green ★ star
badge with caption in 8-pt small-caps Bluish Green:
       "★ NEW — single scalar drives both stratification and calibration"

A thin italic Mid Grey 7-pt caption below the pipe at canvas edges:
       "per-input quality scalar from a frozen 5-head IQA module"

The visible visual takeaway: q-bar is the ONE shared input that joins
both halves; this is the paper's structural innovation.

=== LEFT HALF : ITB BENCHMARK (quality-stratified) ===

Header (small-caps Charcoal 14 pt bold, top-centred above the panel):
       "ITB — Image Triage Benchmark"
       ★ NEW badge to the right of the header, caption "quality-
       stratified evaluation".

The panel runs vertically as a clean top-to-bottom flow:

(a) TOP : INPUT POOL
  A 5x3 tidy grid of 15 tiny circular dermoscopy thumbnails (~36 px
  each), each visibly different quality (sharp / slightly blurred /
  dark / off-centred). Group all 15 inside a faint Light Grey 1-pt
  rounded container labelled in 7-pt italic Mid Grey at the top-left
  corner: "mixed quality pool".

(b) MIDDLE : SCORING FUNNEL
  An Orange #E69F00 trapezoidal funnel below the pool. Inside the
  funnel: a clean monochrome gauge / dial icon with a needle (no
  numeric scale, only tiny tick marks and a clear Steel Blue needle).
  The funnel's narrow neck emits a single Warm Orange 6-pt rounded
  pipe descending downwards.

  The pipe then SPLITS into 4 tributary pipes (a clean curved-corner
  "manifold" graphic, each tributary 4-pt stroke Warm Orange), each
  tributary labelled at its bend in small-caps Steel Blue 8-pt:
        HQ        EDGE        LQ        DIVERSE

(c) BOTTOM : 4 STRATUM BUCKETS (side-by-side, 8-px gaps)
  Each bucket is a clean rounded-rect (~140x110 px) with distinct
  border treatment so that each stratum is identifiable in 1-bit
  black-and-white print:

    BUCKET HQ      : Warm Orange #E69F00 1-pt thin border, white fill.
                     Contains 5 visibly SHARP dermoscopy thumbnails.
                     A tiny ❄ crystal-clarity icon at top-right corner.
    BUCKET EDGE    : Light Grey #CCCCCC 1-pt thin border, white fill.
                     Contains 3 BORDERLINE thumbnails (mildly blurred).
                     Tiny "??" subscript at top-right.
    BUCKET LQ      : Steel Blue #0072B2 2-pt THICK border, white fill.
                     Contains 5 OBVIOUSLY degraded thumbnails (blur /
                     dark / off-centre). Small storm-cloud icon at top.
                     Below the bucket title, a tiny "★ critical
                     stratum" caption in 7-pt Steel Blue small-caps.
    BUCKET DIVERSE : Bluish Green #009E73 1-pt thin border, white fill.
                     Contains 5 thumbnails arranged on a thin 6-tone
                     Fitzpatrick skin-tone strip across the bucket's
                     bottom edge. ★ NEW badge with caption "Fitz I-VI".

  Below the row of buckets, one tiny Mid Grey 7-pt centred italic
  caption: "stratified evaluation, per-stratum metrics".

(d) BOTTOM ABSTRACT METRIC ROW
  A thin horizontal baseline at the bottom of the left half holding
  four tiny unlabeled abstract metric glyphs in Charcoal monochrome:
  a small ruler shape, a small balance-scale shape, a small upward-
  trend curve, and a small Greek-letter-style symbol. NO text labels
  beside the glyphs. NO numerical values. Each glyph sits under a
  faint vertical drop-line connecting back to its bucket above,
  signalling "each stratum is evaluated independently across multiple
  metrics".

=== RIGHT HALF : QCTS MECHANISM (the core contribution) ===

Header (small-caps Charcoal 14 pt bold, top-centred above the panel):
       "QCTS — Quality-Conditioned Temperature Scaling"
       Large ★ OURS badge in Bluish Green to the right of the header.

The panel is laid out as a left-to-right pipeline with a centrepiece
chart, all inside a faint Grey rounded panel.

(a) LEFT COLUMN : x → backbone → z
  Top-left: a small circular dermoscopy thumbnail (~50 px) labelled
  beneath in 7-pt italic "x".
  Downward arrow into a clean white rounded-rect "Backbone f_theta"
  (~130x85 px, 1.5-pt Dark Grey border) containing a small layered
  conv-block silhouette and a ❄ snowflake at its top-right corner.
  Output arrow rightward, labelled "z" in 8-pt italic Mid Grey on the
  arrow.

(b) CENTRE : QCTS CONTRIBUTION BOX (★ OURS)
  A prominent white rounded-rect (~340x240 px) with 2-pt Bluish Green
  #009E73 border. A small filled Bluish Green ★ star + "OURS" caption
  in the top-right corner of this box. Inside, vertically stacked:

   (i) TEMPERATURE-CURVE COMPARISON CHART (~280x110 px):
       Clean white background, thin Light Grey axis lines, NO tick
       numbers. X-axis labelled in 7-pt italic Mid Grey "q-bar" at the
       right end; Y-axis labelled "T" at the top of y-axis. Two curves
       OVERLAID:
        - A thin DASHED Warm Orange #E69F00 horizontal line at mid-y
          value, labelled in 6-pt italic Warm Orange "Std TS
          (constant T)" at its right end with a tiny ★? caption "no
          q-bar dependence — fails".
        - A smooth solid Bluish Green #009E73 softplus-shaped curve
          starting HIGH at q-bar = 0 and asymptoting LOWER on the
          right at q-bar = 1, labelled in 6-pt italic Bluish Green
          "QCTS T(q-bar)" at its right end, with a tiny ★ OURS badge.
       A small annotation arrow between the two curves at mid-x points
       to the vertical gap, labelled in 6-pt italic Charcoal "quality-
       aware shift". A small 🔥 flame icon in the chart's top-right
       corner indicates the (T_0, alpha) two-parameter fit on a
       validation split.

  (ii) FORMULA STRIP (just below the chart, centred 9-pt math Charcoal):
              T(q-bar) = softplus( T_0 + alpha (1 - q-bar) )
       This is the ONLY formula in the entire figure.
       Three tiny tags floating around the formula in small-caps 7-pt
       Bluish Green, each beside a filled ★ Bluish Green star:
              ★ B1 monotonicity
              ★ B2 positivity
              ★ B3 smoothness
       A thin "→" arrow from these three tags to the formula symbolises
       "derived from inductive biases", with a 6-pt italic Mid Grey
       caption beneath: "derivation, not ad-hoc fit".

  (iii) BELOW the formula, a small THERMOMETER icon + small DIAL/GAUGE
       icon side by side, with an incoming arrow on the LEFT labelled
       "q-bar" (delivered from the top q-bar pipe via the right-half
       drop arrow) and an outgoing arrow on the RIGHT labelled
       "T(q-bar)" feeding into the next stage.

(c) RIGHT COLUMN : z / T(q-bar) → softmax → calibrated p
  After the QCTS box: a small "÷" divide icon in a tiny circle showing
  "z ÷ T(q-bar)", then arrow into a clean small softmax rounded pill,
  then arrow into a horizontal probability bar-chart thumbnail
  (~100x44 px) showing two bars: top short bar Mid Grey labelled
  "benign", bottom long bar Bluish Green labelled "malignant".
  Captioned beneath in 9-pt Bluish Green bold: "calibrated p".

(d) BOTTOM STRIP OF RIGHT HALF : RELIABILITY BEFORE / AFTER
  Two tiny reliability-diagram thumbnails (~80x55 px) side by side,
  each on a thin Light Grey square frame with a dotted diagonal but NO
  tick numbers:
   LEFT thumb — caption "Std TS" in 7-pt italic Warm Orange:
       a wandering Charcoal curve that visibly CROSSES the diagonal.
   RIGHT thumb — caption "QCTS (ours)" in 7-pt italic Bluish Green:
       a Bluish Green curve that visibly HUGS the diagonal.
  A "→" arrow between them with caption "before / after" in 6-pt italic
  Mid Grey. NO numerical values.

=== BOTTOM LEGEND STRIP ===

A horizontal row spanning the full canvas just above the bottom margin,
separated from the main figure by a thin dotted Light Grey horizontal
hairline. Six compact entries left-to-right, each = small icon + 8-pt
Charcoal label:

   ❄ frozen weights
   🔥 fitted parameters (T_0, alpha)
   ⬇ q-bar drop-feed
   [orange dashed line]  Std TS (baseline, fails)
   [green solid curve]   QCTS (ours, fixes)
   ★ innovation marker

NO box around the legend.

=== STYLE SPECIFICATIONS (CVPR polish) ===

PALETTE (exactly 3 saturated colours; everything else greyscale):
  Steel Blue       #0072B2  — q-bar capsule, ITB-LQ critical border,
                              IQA accent, gauge needle, stratum labels
  Warm Orange      #E69F00  — top q-bar pipe, scoring funnel + 4
                              tributaries, ITB-HQ border, Std TS
                              reference line, baseline reliability
  Bluish Green     #009E73  — QCTS box border + curve, ITB-Diverse
                              border, calibrated p bar, every ★
                              innovation badge

  Module fill        #FFFFFF
  Panel backdrop     #F7F7F7  (very subtle)
  Standard border    #CCCCCC
  Body text          #333333
  Secondary text     #666666  (italic, 6-7 pt)
  Arrow stroke       #4D4D4D  (1.5 pt)

NO other colours. NO gradients, NO drop shadows, NO 3D effects, NO
glow, NO photographic noise, NO watercolour textures.

TYPOGRAPHY (MINIMAL):
  Clean grotesque sans-serif (Inter / Helvetica / DejaVu Sans).
  Panel headers      : small-caps, 14 pt bold, Charcoal
  Stratum labels     : small-caps, 8 pt, Steel Blue
  Module titles      : bold, 9 pt, Charcoal (sparse)
  Italic captions    : 6-7 pt, Mid Grey (very sparse)
  Dimension labels   : italic 7 pt, Mid Grey, sitting above arrows
  Formula            : 9 pt math, Charcoal (ONE INSTANCE ONLY)
  ★ badge captions   : small-caps, 7-8 pt, Bluish Green
  NO body paragraphs. Most labels 1-3 words.

GEOMETRY:
  All rectangles 4-px corner radius. Module borders 1-1.5 pt; "★ ours"
  contribution boxes 2 pt. Pipes 6-8 pt rounded strokes. Arrows 1.5 pt
  with sharp arrowheads. Inter-module padding 12-16 px.

INFORMATION DENSITY (CVPR sweet spot):
  Every module contains either an icon, a chart, or a 1-3 word label —
  rarely two of these together. The temperature-curve chart is the
  visual focal point of the right half. The scoring funnel + 4 buckets
  are the visual focal point of the left half. The top q-bar pipe is
  the structural bridge.

INNOVATION CALLOUTS (must all be present):
  ★1 above the top q-bar pipe — "single scalar drives both stratification
     and calibration"
  ★2 on the LEFT half header — "quality-stratified evaluation"
  ★3 in the central chart — "T(q-bar) curve vs constant T(qC)" gap
     annotation
  ★4 floating around the formula — "B1 + B2 + B3 → softplus derivation"

GLOBAL CHECK:
  - >= 70% of canvas is pure white / faint grey.
  - Exactly 3 saturated colours appear.
  - LEFT half visually dominated by the orange scoring funnel + 4
    distinct strata buckets; RIGHT half visually dominated by the green
    T(q-bar) softplus curve and the QCTS contribution box.
  - The top q-bar pipe visibly joins both halves, marked with a clear
    ★ NEW badge — this is the paper's structural novelty.
  - NO numerical results, NO sample sizes, NO ECE / AUC / QCDI / rho
    values. The ONLY math expression is T(q-bar) = softplus(T_0 +
    alpha(1 - q-bar)).
  - Figure must remain fully readable in 1-bit black-and-white print
    (border thickness + dashed-vs-solid line + icon shape distinguish
    every comparison without colour).
  - Aspect ratio strictly 16:9. Output resolution >= 1920x1080.
```

---

## 调整指令（若首版不满意）

| 问题 | 追加指令 |
|------|---------|
| 不像 CVPR 风格 | "tighten alignment grid, sharpen arrowheads, remove ALL decorative elements, increase white space to 70%+, use only flat 2D rectangles with crisp 1-1.5 pt borders" |
| 创新点不突出 | "make every ★ star badge larger (~18 px) and place a small 'NEW' or '★ OURS' caption immediately beside it in small-caps Bluish Green 8-pt" |
| 左右两半界限不清 | "draw a clearly visible vertical 1-pt dotted Light Grey divider exactly at canvas centre x = 960; ITB scoring funnel must sit entirely left of this line, QCTS box entirely right" |
| 顶部 q-bar pipe 不显眼 | "make the top q-bar pipe a 10-pt rounded Warm Orange stroke spanning the full canvas width; place the Steel Blue q-bar capsule exactly at the centre at canvas y = 10%; both halves must show an unmistakable orange drop arrow descending into their top edge" |
| 4 strata 桶看不出区别 | "give each ITB bucket a clearly different border: HQ orange thin, EDGE grey thin, LQ steel-blue 2-pt thick with a small ★ critical caption, DIVERSE green thin with a 6-tone Fitzpatrick strip at its base" |
| T(q̄) 曲线不像 softplus / 对比不强 | "the T(q-bar) curve must be a clean softplus shape: high on the left, monotonically decreasing, asymptoting on the right; overlay it on the SAME axes as the dashed orange Std TS horizontal line; draw a small bracket annotation between them at mid-x labelled 'quality-aware shift'" |
| 出现数字 / 样本量 | "remove every numerical label, sample count, interval bracket, axis tick value; keep ONLY the symbolic formula T(q-bar) = softplus(T_0 + alpha(1 - q-bar))" |
| 文字过多 | "reduce every sub-label to 1-3 words; remove every italic caption not strictly necessary; rely on icons + chart shapes to carry meaning" |
| 颜色饱和 / 第 4 色 | "desaturate borders by 15%; eliminate any colour not exactly Steel Blue #0072B2 / Warm Orange #E69F00 / Bluish Green #009E73; all other elements greyscale" |

---

## 备份与覆盖

- 主 prompt 历史版本：
  - `.v1_backup.md` — 4-stage 水平 pipeline
  - `.v2_backup.md` — TS-vs-QCTS 上下双路对比
- 当前 v4 = 主文件 `PROMPT_fig_method_nanobanana.md`
- 配套备选：
  - `VISIO_SPEC_fig_method.md` — v3 Visio 手绘 spec
  - `HANDDRAW_REF_fig_method.md` — 速查
- 已生成草图 SVG：`fig_method.svg`（v2 风格，可作为参考）

生成 PNG 后：

```bash
# vectormagic 或 Illustrator Image Trace 转 SVG
# Illustrator 导出 PDF → 覆盖 figures/fig_method.pdf
```

主文 LaTeX `\includegraphics{figures/fig_method}` 不变。
