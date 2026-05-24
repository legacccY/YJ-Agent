# 手绘参考速查 — BMVC fig_method (Visio / 纸笔皆可)

详细 spec 见 `VISIO_SPEC_fig_method.md`。本文件 = 一眼看懂的草图 + 红线，扫完直接开画。

---

## 1. 整体草图（按比例 16:9）

```
┌──────────────────────────────────────────────────────────────┬─────────────────┐
│  TRAINING — post-hoc calibration on ITB val split            │ INFERENCE       │
│                                                              │ single image    │
│  ┌── TOP BAND : 5-head IQA (shared) ──────────────┐          │ ┌─────────────┐ │
│  │ (📷) → ┌─Sharp───┐                             │          │ │   (📷)      │ │
│  │       ├─Bright──┤                              │          │ │     ↓       │ │
│  │       ├─Compl───┤ → [mean] → ⦅ q̄ ⦆            │          │ │  [IQA]→⦅q̄⦆ │ │
│  │       ├─Colour──┤                              │          │ │     ↓       │ │
│  │       └─Contr───┘                              │          │ │  ┌f_θ❄┐    │ │
│  └─────────────────────────────────┬───────────────┘          │ │  └────┘    │ │
│                                    │ ⤴ q̄ shared (dotted)     │ │     ↓       │ │
│  ┌── PATH A: STANDARD TS  (dashed orange) ─────────┐         │ │ ┌QCTS(q̄)┐  │ │
│  │ (📷) ─→ ┌f_θ❄┐ ─z→ ┌🌡 Std TS 🔥┐ ─p→  ⚠       │         │ │ └───────┘  │ │
│  │        └────┘    └────────────┘   ρ sign-flip   │         │ │     ↓       │ │
│  └──────────────────────────────────────────────────┘         │ │  [softmax]  │ │
│                                                              │ │     ↓       │ │
│  ┌── PATH B: QCTS (ours)  (solid green, thicker) ──┐         │ │ ▁▁▆▆ ✓     │ │
│  │ (📷) ─→ ┌f_θ❄┐ ─z→ ┌🌡 QCTS 🔥⚙       ┐ ─p→  ✓ │         │ │ calibrated p│ │
│  │        └────┘    │ T(q̄)=softplus(    │  calib   │         │ └─────────────┘ │
│  │                  │  T₀+α(1−q̄))      │           │         │                 │
│  │                  └───────────────────┘           │         │                 │
│  └──────────────────────────────────────────────────┘         │                 │
│                                                              │                 │
│  ┌── UNIVERSALITY (faint grey) ────────────────────┐         │                 │
│  │   [CNN]    [ViT]    [Hybrid]                    │         │                 │
│  │     ✓        ✓         ✓                        │         │                 │
│  │     QCTS generalises across backbones           │         │                 │
│  └──────────────────────────────────────────────────┘         │                 │
└──────────────────────────────────────────────────────────────┴─────────────────┘
   ····················································· (dotted hairline) ······
   ❄ frozen   🔥 fitted (T₀,α)   📷 input   ⚠ TS reversal   ✓ calibrated
```

**视觉中心** = Path A 末端 ⚠ 与 Path B 末端 ✓ 上下并排，眼睛先扫到这里。
**故事**：同 backbone + 同 logit z → 两种温度 → 两种结果。

---

## 2. 元素清单（按绘制顺序）

| # | 元素 | 用什么形状 |
|---|---|---|
| 1 | 画布 + 中央竖线 + 顶横线 + 5 条参考线 | View → Guides |
| 2 | TRAINING / INFERENCE 标题 | 文字 Steel Blue Small Caps 12 pt |
| 3 | TOP BAND 背景 Faint Grey 填充 | Rectangle 无边框 |
| 4 | Dermoscopy 圆 (深棕椭圆 + 圆框) | Ellipse |
| 5 | 5-head IQA fan: 5 个 mini rect 堆叠 | Rounded rect ×5 |
| 6 | 每 rect 里 mini glyph (kernel / 直方图 / 框 / 横条 / S 曲线) | Visio 笔画 |
| 7 | mean pill + q̄ pill | Rounded rect |
| 8 | 顶部 dotted arch (Warm Orange) | Freeform arc |
| 9 | PATH A 外框 dashed orange | Rounded rect Dash 样式 4 |
| 10 | PATH A 6 列模块 (input → f_θ → Std TS → ⚠) | 复用形状 |
| 11 | PATH B 外框 solid green 2 pt | Rounded rect |
| 12 | PATH B 6 列 (前 3 列复制 Path A，后 3 列重画) | 复用 + 重画 |
| 13 | QCTS 模块比 TS 大，内含公式 | Rounded rect 1.20×0.85 |
| 14 | Universality 3 backbone icon + ✓ + 名 | 笔画 + Unicode ✓ |
| 15 | Inference 列 7 行垂直 stack | Rounded rect + 向下箭头 |
| 16 | Legend 5 icon + 标签 | Unicode + 文字 |

---

## 3. 配色速查 (Visio 自定义主题)

```
Steel Blue   #0072B2  IQA / Stage header / 主箭头 / q̄ pill
Warm Orange  #E69F00  Path A dashed / ⚠ / 顶部 dotted arch
Bluish Green #009E73  Path B solid / ✓ / 校准成功
Light Grey   #CCCCCC  分隔线 / mean pill / separator
Faint Grey   #F7F7F7  Band 背景
Charcoal     #333333  主文字
Mid Grey     #666666  italic 副标签 / arch caption
Arrow Grey   #4D4D4D  所有连接箭头 (1.5 pt)
```

仅 **3 种饱和色**。其余全 grayscale。

---

## 4. 字号速查

```
Title              12 pt Bold Small Caps  Steel Blue
Path header        10 pt Bold Small Caps  Path 主色
Module title        8 pt Bold              Charcoal
Sub-label / formula 7-8 pt regular         Charcoal
Italic caption      6-7 pt italic          Mid Grey
Glyph / Unicode 图标 8-14 pt              Charcoal / 主题色
```

---

## 5. 严格列对齐（PATH A / B 最关键）

```
        Col 1   Col 2     Col 3   Col 4         Col 5   Col 6
        input   backbone  z       temperature   p       end
x 中心  0.85    2.20      3.40    4.30          5.20    6.30

A:      (📷) ─→ f_θ❄  ─z─→ Std TS🔥  ─p─→  ⚠ ρ sign-flip
B:      (📷) ─→ f_θ❄  ─z─→ QCTS🔥⚙   ─p─→  ✓ calibrated
                                公式只在这里
```

画完后**拉一条垂直参考线**逐列检查上下两路对齐。

---

## 6. 红线 7 条（违反必删）

1. ❌ 任何 ρ / QCDI / ECE / AUC **数值**（如 +0.241, −0.249, 0.146）
2. ❌ 任何样本量（n=300, n=360, n=660, n=1500, n=2298, n=10015）
3. ❌ 任何区间括号 `[0,1]` / 维度标注 `R^K` / `Δ^(K-1)`
4. ❌ Mini reliability chart 的坐标轴刻度数字（只画曲线 + 对角线）
5. ❌ Q-VIB / VisiScore-Net / anonymous2025\* 字样
6. ❌ 第 4 种饱和色（除 Steel Blue / Warm Orange / Bluish Green）
7. ❌ Path A / B 6 列 x 坐标不对齐

唯一允许的数学：`T(q̄) = softplus(T₀ + α(1−q̄))` 只在 Path B QCTS 模块。
`ρ sign-flip` 作为 Path A 末端**文字标签**允许（无数值附着）。

---

## 7. 画完自查（3 分钟）

```
[ ] 1-bit 黑白打印能区分 Path A vs B 吗？
    (dashed vs solid 边框 + ⚠ vs ✓ icon 两层冗余)
[ ] 中央竖线把 TRAINING / INFERENCE 干净分开了吗？
[ ] q̄ shared dotted arch 从 q̄ pill 弧到 Path B QCTS 顶 ✓
[ ] Path A / B 6 列拉参考线对齐 ✓
[ ] 3 backbone icon + ✓ + 名水平居中
[ ] Legend 5 个 icon 在底部一行
[ ] 整体 ≥70% 白色
[ ] 全图无任何具体结果数字 (grep ρ/QCDI/ECE/AUC/0\.[0-9]{3})
```

---

## 8. 导出

```
Visio: File → Save As → PDF (vector) → fig_method.pdf
       File → Save As → SVG          → fig_method.svg
覆盖到 D:\YJ-Agent\project\meeting\BMVC\figures\
主文 LaTeX \includegraphics{figures/fig_method} 不动
```
