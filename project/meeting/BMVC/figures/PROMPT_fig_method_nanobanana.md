# NanoBanana Prompt — BMVC Method Figure (fig_method v2)

**配色**：Okabe-Ito 学术标准（Steel Blue #0072B2 + Warm Orange #E69F00 + Bluish Green #009E73）
**比例**：16:9 横向
**目标输出**：SVG (可缩放) + PNG 300 dpi
**保存为**：`figures/fig_method.pdf` （覆盖现版本）+ `figures/fig_method.svg`

---

## 使用方法

1. 复制下方 **整块** 英文 prompt（含 STYLE SPECIFICATIONS 段落）
2. 粘贴到 NanoBanana / Gemini Vision / DALL-E 3 / Midjourney v6
3. 若首次输出不够紧凑/信息密度不足，加一句 "denser, less whitespace between modules, fit 4 stages tightly into 16:9"
4. 选最佳一张导出 SVG（NanoBanana 默认输出 PNG → 用 https://vectormagic.com 或 Illustrator Image Trace 转 SVG）

---

## Prompt（复制粘贴整段）

```
A highly detailed, information-dense academic paper framework diagram in the style of top-tier CVPR/NeurIPS/BMVC publications. The diagram illustrates the end-to-end "Quality-Aware Calibration" pipeline for medical AI under image quality shift: dermoscopy lesion image is scored by a 5-head Image Quality Assessment (IQA) module to produce a per-input quality scalar q-bar, routed into the Image Triage Benchmark (ITB) partition, passed through a frozen classification backbone, and finally calibrated by Quality-Conditioned Temperature Scaling (QCTS). Arranged as a rich four-stage left-to-right horizontal pipeline on a clean white background, 16:9 aspect ratio, with embedded monochrome thumbnail visualisations, dense dimensional annotations along data-flow arrows, and a compact metric panel in the bottom-right corner.

=== GLOBAL LAYOUT ===

Four stages arranged left-to-right at constant vertical centre-line, separated by thin Light Grey (#CCCCCC) vertical dividers. Each stage occupies roughly 25% of canvas width. Above each stage block, a small-caps Steel Blue (#0072B2) header reads "STAGE 1 — INPUT & IQA", "STAGE 2 — ITB PARTITION", "STAGE 3 — FROZEN BACKBONE", "STAGE 4 — QCTS CALIBRATION", followed by a thin Light Grey horizontal rule below the header. NO coloured banner bars. Pure white module fills throughout; colour appears only on module borders, arrows, and small accent icons.

Main data-flow arrows (Dark Grey #4D4D4D, 1.5 px) connect stages horizontally with arrowheads; data-dimension labels in Medium Grey (#666666) italic 7-pt sit just above each arrow ("x ∈ R^(3×H×W)", "q-bar ∈ [0,1]", "z ∈ R^K", "p ∈ Δ^(K-1)").

=== STAGE 1: INPUT & IQA ===

A very faint Grey #F7F7F7 background panel groups Stage 1. Inside:

(a) Top-left: a small (~80×80 px) rounded-corner circular crop of a dermoscopy lesion image (representative pink-brown pigmented lesion) labelled "x  dermoscopy input" beneath it in Charcoal #333333 7-pt sans-serif.

(b) An arrow flows from the input image rightward into a vertical fan of FIVE PARALLEL small CNN icons, each a tiny white rounded-rectangle (~35×20 px) with Steel Blue #0072B2 1-pt border. The five CNN icons are stacked vertically with 4-px gaps and labelled (top to bottom, 6-pt small-caps):
    - "q₁  Sharpness"      [embed a small monochrome blur-kernel grid thumbnail]
    - "q₂  Brightness"     [embed a small monochrome luminance histogram thumbnail]
    - "q₃  Completeness"   [embed a small monochrome crop-boundary frame thumbnail]
    - "q₄  Colour temp."   [embed a small monochrome RGB-channel bar thumbnail]
    - "q₅  Contrast"       [embed a small monochrome contrast-curve thumbnail]
On the right side of the fan, all five outputs converge into a single horizontal "average" symbol (a thin Light Grey #CCCCCC pill labelled "mean") and emit a single horizontal arrow into a small Steel Blue #0072B2-bordered pill containing the bold formula "q̄ ∈ [0,1]".

(c) Caption strip below the fan in Medium Grey #666666 6-pt italics: "5-head IQA, frozen after pre-training".

=== STAGE 2: ITB PARTITION ===

A very faint Grey #F7F7F7 background panel groups Stage 2. Inside:

(a) A vertical stack of FOUR horizontal coloured bar-blocks representing the ITB partition, each ~110 px wide × 18 px tall, stacked top-to-bottom with 4-px gaps. From top to bottom:
    - HQ stratum: Warm Orange #E69F00 thin border, white fill, labelled "ITB-HQ   q̄ > 0.50   n = 360"
    - Edge stratum: Light Grey #CCCCCC border, white fill, labelled "ITB-Edge   q̄ ∈ [0.45, 0.50]   n = 660"
    - LQ stratum: Steel Blue #0072B2 THICK 1.5-pt border (emphasised), white fill, labelled "ITB-LQ   q̄ < 0.45   n = 300   ★ critical"
    - Diverse stratum: Bluish Green #009E73 thin border, white fill, labelled "ITB-Diverse   Fitzpatrick I–VI   n = 1,500"

(b) An incoming arrow from the Stage-1 "q̄" pill enters the left edge of the partition stack with a small angled-fan icon indicating "binning by q̄". A black-dotted-line bracket on the right edge of the stack groups the four bars under a small text label "evaluation strata".

(c) Below the partition stack, a tiny single-row image strip shows 4 small (~22×22 px) example lesion thumbnails — one per stratum — illustrating that each stratum contains visually distinct quality profiles. Each thumbnail tied to its bar by a thin Light Grey vertical line.

=== STAGE 3: FROZEN BACKBONE ===

A very faint Grey #F7F7F7 background panel groups Stage 3. Inside:

(a) A central tall white rounded-rectangle (~120×140 px) with 1.5-pt Dark Grey #4D4D4D border and a small ❄ snowflake icon in Medium Grey #666666 6-pt in the top-right corner indicating "frozen". The box is labelled in bold Charcoal #333333 8-pt centred at top: "Backbone f_θ". Below the label, three internal silhouettes stacked vertically with very thin Light Grey separators, each labelled in 6-pt small-caps Medium Grey:
    - "EfficientNet-B3   (Std VIB)"
    - "ResNet-50 / ViT-Tiny"
    - "ConvNeXt-T / Swin-T"
Each silhouette shows a tiny abstract layered-blocks icon (small grey rectangles tiling).

(b) The input arrow enters the left edge of the backbone box from the Stage-2 partition output, labelled "x" in Medium Grey 7-pt italic. The output arrow exits the right edge labelled "z ∈ R^K  (logits)" in Medium Grey 7-pt italic.

(c) Caption strip below the backbone box in Medium Grey #666666 6-pt italics: "frozen weights, no retraining".

=== STAGE 4: QCTS CALIBRATION ===

A very faint Grey #F7F7F7 background panel groups Stage 4. The Bluish Green #009E73 accent appears here exclusively because Stage 4 is the paper's contribution. Inside:

(a) A vertical stack of two main components:

   TOP: a white rounded-rectangle (~140×60 px) with 1.5-pt Warm Orange #E69F00 border, labelled in bold 8-pt at top "QCTS  (2 params)". Inside, two short rows in 8-pt math font:
        T(q̄) = softplus(T₀ + α·(1 − q̄))
        T₀, α  ←  L-BFGS arg min NLL on D_val
   On the left side of this box, a small Warm Orange #E69F00 arrow incoming from Stage 1's "q̄ pill" (drawn as a long curved dotted arrow that spans the top of the entire figure, label "q̄ shared") delivers the per-input quality scalar.
   On the right side of this box, the resulting "T(q̄)" emits a downward arrow into the next block.

   BOTTOM: a white rounded-rectangle (~140×55 px) with 1.5-pt Bluish Green #009E73 border, labelled in bold 8-pt at top "Calibrated softmax". Inside, the formula:
        p = softmax( z / T(q̄) )
   The "z" input arrow enters from the left (coming horizontally from Stage 3's backbone output, labelled "z").
   The output arrow exits the right edge of this bottom box to the right edge of the figure, labelled "p ∈ Δ^(K-1)  (calibrated)" in Charcoal #333333 7-pt bold.

(b) To the right of the output arrow, a tiny horizontal probability bar chart thumbnail (~50×24 px) showing 2 bars representing P(benign), P(malignant), with the benign bar coloured Bluish Green #009E73 and labelled "p (calibrated)".

=== TOP-OF-CANVAS FEEDBACK BAND ===

Above all four stages, a single long thin Warm Orange #E69F00 dotted arrow arches from the "q̄ ∈ [0,1]" pill at the right of Stage 1 over Stages 2 and 3, landing on the top edge of the Stage-4 QCTS box. Label this arrow centred above its arch in Medium Grey #666666 6-pt italic: "q̄ shared between ITB stratification and QCTS temperature".

=== BOTTOM-RIGHT METRIC PANEL ===

In the bottom-right corner of the canvas, a small white rounded-rectangle box (~150×64 px) with a thin Bluish Green #009E73 1-pt border, labelled at top in small-caps Bluish Green 7-pt "RESULTS  (Std VIB on ITB-LQ)". Three short rows inside in Charcoal #333333 7-pt:
    QCDI  +0.016 → +0.004    (−73% vs standard TS)
    ρ(H, q̄)  −0.153 → −0.249  (p < 10⁻³⁰)
    no retraining, 2 params fit on D_val

=== STYLE SPECIFICATIONS ===

PALETTE (Okabe-Ito):
  Primary    Steel Blue       #0072B2   — Stage-1 IQA borders, Stage-2 LQ emphasis border, section headers, main arrows
  Secondary  Warm Orange      #E69F00   — Stage-2 HQ border, Stage-4 QCTS top-box border, the top-band shared-q̄ arrow
  Accent     Bluish Green     #009E73   — Stage-2 Diverse border, Stage-4 output box border, calibrated-probability bar, RESULTS panel border
  Module fill  Pure White     #FFFFFF   — every rectangular module
  Area background  Faint Grey #F7F7F7   — the four stage grouping panels (very subtle, barely visible)
  Standard border  Light Grey #CCCCCC   — Stage-2 Edge border, internal separators, partition outlines
  Body text  Charcoal         #333333   — primary labels
  Arrow/lines  Dark Grey      #4D4D4D   — connecting arrows (1.5 px)
  Secondary text  Medium Grey #666666   — dimensional annotations, caption strips, sub-labels
NO other colours. NO gradients, NO drop shadows, NO 3D effects, NO photographic noise, NO decorative glow.

TYPOGRAPHY:
  All labels in clean grotesque sans-serif (e.g., Helvetica, Inter, or DejaVu Sans).
  Stage headers: small-caps, 9 pt, Steel Blue.
  Module titles: bold 8 pt, Charcoal.
  Sub-labels and formulae: regular 7 pt, Charcoal.
  Dimensional annotations and captions: italic 6–7 pt, Medium Grey.
  NO bold flourish text. NO decorative fonts. NO emojis except the single ❄ snowflake icon inside Stage-3.

GEOMETRY:
  All rectangles: 4 px corner radius.
  Border thicknesses: standard 1 pt, emphasised modules 1.5 pt.
  Arrow strokes: 1.5 pt with simple solid arrowheads (12-degree open chevron); the single feedback arrow at the top uses a 1 pt dotted line.
  Generous 6–8 px padding inside every module; 12–16 px between modules.
  No module overlaps any other module.

INFORMATION DENSITY:
  Every module box must contain at least one of: a sub-label, an embedded monochrome thumbnail, or a formula. No empty boxes.
  Embedded thumbnails are flat monochrome (Charcoal on white) at ~12–18 px size.
  Captions sit just below or beside their parent module; never floating freely.

GLOBAL CHECK:
  ≥ 70% of canvas area is pure white.
  Only 3 saturated colours appear (Steel Blue, Warm Orange, Bluish Green); all other elements are grey-scale.
  The figure must be fully readable in 1-bit black-and-white print.
  Aspect ratio strictly 16:9. Output resolution 1920×1080 px at minimum; vector SVG preferred.
```

---

## 调整指令（若首版不满意）

| 问题 | 追加指令 |
|------|---------|
| 模块太散 | "tighter horizontal spacing between stages, reduce padding to 8 px, fit content into 80% of canvas width" |
| 颜色饱和 | "desaturate borders by 15%, ensure ≥ 70% white area" |
| 缩略图过大 | "shrink embedded thumbnails to 12 px max, keep labels readable" |
| 公式太小 | "increase formula font to 9 pt, keep all other labels at original size" |
| 箭头杂乱 | "use only horizontal/vertical arrows except the single top feedback arch; all arrowheads identical" |
| 模块文字溢出 | "expand module width by 15%, abbreviate captions if needed" |

---

## 备份原 fig_method 提醒

原版 fig_method.svg / fig_method.pdf 在 `figures/`。生成新版前建议：
```bash
cp figures/fig_method.svg figures/fig_method_v1_backup.svg
cp figures/fig_method.pdf figures/fig_method_v1_backup.pdf
```

满意后用新 PDF 覆盖原文件，主文 LaTeX 不需要改 `\includegraphics{figures/fig_method}`。
