# NanoBanana Prompt — fig_method v5

**版本** v5：参考 reference + 缩 ❄/🔥 + 框色承担 train/frozen + 框内禁底色。备份 `.v4_backup.md`。**比例** 14:8。

---

## Prompt（复制整段）

```
Information-dense CVPR / NeurIPS-style academic method figure. Landscape 14:8, pure white background. Two panels: (a) we BUILT a quality-stratified benchmark; (b) we INSERTED a 2-param fix.

LAYOUT — Left panel (a) 55%, right (b) 45%, separated by a thin Light Grey #CCCCCC 1-pt vertical rule. Each under a small-caps Steel Blue #0072B2 14-pt header on a faint underline. A faint Light Grey 1-pt DASHED arrow runs from panel (a)'s ITB Stratification box DOWN into panel (b)'s backbone input. Top-right legend (white box, 8-pt, 4 rows): Steel Blue ❄ Frozen; Warm Orange 🔥 Trainable; Dark Grey solid arrow Forward; Vermillion #D55E00 dashed arrow Gradient (training only).

FRAME-COLOUR RULE (CRITICAL) — training status encoded ONLY by frame colour, never by inner fill. Frozen: Light Grey #CCCCCC 1-pt frame. Trainable T(q-bar) hub: Warm Orange #E69F00 3-pt THICK frame. Panel-(a) destination: Bluish Green #009E73 1.8-pt frame. Critical sub-stratum: Steel Blue 2-pt frame. ALL module interiors pure white #FFFFFF — NO inner tints, soft fills, gradients, glows. ❄ and 🔥 icons are tiny (~10-12 px) at top-right of their frame, secondary only; frame colour is the primary signal.

PANEL (a) BENCHMARK BUILD (rhythm: small → small → small → BIG REVEAL)
Four modules left-to-right on one centre-line, arrows strictly horizontal 1.5-pt Dark Grey.
(1) RAW DATASETS — Light Grey 1-pt frame. Four stacked ~36-px circular dermoscopy lesion thumbnails, varied skin tones. Tag row: "ISIC 2020 · FitzPatrick17k · HAM10000 · PAD-UFES".
(2) PROGRAMMATIC DEGRADATION — Light Grey 1-pt frame. 5-cell grid of degraded lesion thumbnails, each tagged 7-pt small-caps Steel Blue: q1 sharpness · q2 brightness · q3 completeness · q4 colour-temp · q5 contrast.
(3) 5-HEAD IQA NET — Light Grey 1-pt frame + tiny Steel Blue ❄ top-right. Compact ConvNet → 5-heads silhouette. Math 8-pt: q ∈ [0,1]^5, q-bar = (1/5) Σ q_i.
(4) ITB STRATIFICATION (DESTINATION, 1.3× LARGER) — Bluish Green 1.8-pt frame. Four side-by-side sub-boxes, equal height:
   LQ (n=300) — Steel Blue 2-pt frame + tiny "★ critical"
   EDGE (n=660) — Light Grey 1-pt frame
   HQ (n=360) — Warm Orange 1-pt frame
   DIVERSE Fitz I-VI (n=1,500) — Bluish Green 1-pt frame + thin 6-tone skin-tone strip at base
Italic 8-pt Mid Grey #666666 spanning caption: "149,100 quality annotations".

PANEL (b) QCTS INSERTION (HERO: two muted frozen tracks converge on one focal orange hub)
Trainable T(q-bar) hub is FOCAL — geometric centre of panel (b), 1.5× larger than any other module, Warm Orange 3-pt THICK frame, white fill, small flat Warm Orange 🔥 (~12 px) top-right, learned-curve inset inside.
Input "x" (small circular dermoscopy thumbnail) at far left FORKS into TWO muted horizontal tracks:
   UPPER — Frozen Std VIB Backbone (Light Grey 1-pt frame, tiny ❄), emits "z" along the upper edge.
   LOWER — Frozen 5-head IQA Net (Light Grey 1-pt frame, tiny ❄), emits "q-bar" along the lower edge.
Both tracks BEND inward with clean curved-corner connectors and CONVERGE at the hub's left edge.
Inside the hub: math line T(q-bar) = softplus( T_0 + alpha (1 - q-bar) ); tiny inset chart of the learned softplus — smooth Bluish Green curve high at q-bar=0, asymptoting low at q-bar=1; one thin Light Grey dashed horizontal Std TS reference. No tick numbers.
From the hub, Dark Grey 1.5-pt arrow exits right into a small SOFTMAX node "softmax( z / T(q-bar) )", then → "p" ending at a tiny horizontal Steel Blue probability-bar.
GRADIENT-FLOW CALLOUT (below hub): small Vermillion #D55E00 1-pt DASHED rounded rectangle tagged 7-pt small-caps "TRAINING-TIME ONLY". A Vermillion dashed 1.5-pt arrow rises from it UP into the hub's bottom edge — proves the orange node is the ONLY thing trained, and only at validation-time.

ALIGNMENT — Panel (a) modules share one horizontal centre-line; module 4 is 1.3× wider but still centre-aligned. Panel (b) upper & lower tracks symmetric about the hub's vertical centre-line; convergence bend angles equal. Headers, panel widths, the cross-panel dashed arrow snap to a clean grid. Inter-module padding 14-18 px.

STYLE — Okabe-Ito strict: #0072B2 Steel Blue · #E69F00 Warm Orange (focal) · #009E73 Bluish Green (panel-a destination only) · #D55E00 Vermillion (gradient loop only). White fills throughout. Light Grey #CCCCCC borders for frozen / supporting modules. Flat clean sans-serif (Inter / Helvetica). Small-caps panel titles. Italic math. Italic 7-pt Mid Grey dimension labels above arrows (x, z, q-bar, T(q-bar), p). NO coloured backgrounds, inner tints, gradients, shadows, 3D, glows, emoji-style icons (flat glyphs only), marketing aesthetic. Every module ≥ 2 sub-elements. CVPR / NeurIPS publication-grade, B/W-print legible. Flat 2D vector. Aspect ratio strictly 14:8. Output ≥ 1920×1080.
```

---

## 不满意时追加

- 框内底色：`every module interior pure white; remove inner tints, soft fills, gradients, glows`
- ❄/🔥 过大：`shrink icons to ~10 px max, top-right corner; frame colour dominates trainable signal`
- 对齐失序：`snap panel-(a) modules to one centre-line; panel-(b) tracks symmetric about hub's vertical centre-line`
- Hub 不焦点：`orange hub 1.5× larger, 3-pt thick orange frame, geometrically centred; both frozen tracks converge into its left edge`
- 第 5 色：`remove any colour not in {#0072B2 #E69F00 #009E73 #D55E00 #CCCCCC #666666 #333333 #FFFFFF}`
