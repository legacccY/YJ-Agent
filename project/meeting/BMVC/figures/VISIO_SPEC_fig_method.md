# Visio Drawing Spec — BMVC Method Figure (fig_method v3)

**画法**：手绘 Visio，无需 AI 生图
**比例**：16:9 横向（推荐画布 11" × 6.1875"，或 1920 × 1080 px）
**导出**：Visio → Export As PDF（保留矢量）→ 覆盖 `figures/fig_method.pdf`；同时 Save As SVG → `figures/fig_method.svg`
**版本说明**：v3 — Visio 手绘版，沿用 v2 上下双路对比故事，所有 AI 难画的"照片裁剪"/"复杂缩略图"改成 Visio 原生形状 + 抽象 glyph。NanoBanana v2 prompt 备份在 `PROMPT_fig_method_nanobanana.v2_backup.md`，v1 备份在 `.v1_backup.md`。

---

## 1. 全局画布与参考线

| 项 | 值 |
|---|---|
| 画布尺寸 | 11" × 6.1875"（Letter Landscape, 16:9）|
| 标尺单位 | inches |
| 网格 | 0.0625" minor / 0.125" major（View → Grid, Snap to Grid ON）|
| 字体 | Inter 或 Calibri（Visio 默认 Calibri 即可）|
| 留白 | 上下左右各 0.25" 边距 |

**关键参考线**（View → Add Guide）：
- 垂直分隔线 `x = 7.50"`（TRAINING 70% / INFERENCE 30%）
- 水平参考线 `y = 5.50"`（TOP BAND 底边）
- 水平参考线 `y = 3.65"`（PATH A 底 / PATH B 顶 之间）
- 水平参考线 `y = 2.00"`（PATH B 底 / Universality 顶）
- 水平参考线 `y = 0.75"`（LEGEND 顶边）

**配色（Visio 主题色 → 自定义）**：

| 名 | HEX | RGB | 用途 |
|---|---|---|---|
| Steel Blue | `#0072B2` | 0, 114, 178 | IQA 边框 / Stage header / 主箭头 / q̄ pill |
| Warm Orange | `#E69F00` | 230, 159, 0 | Path A 虚线边框 / ⚠ / 顶部 q̄ shared arch |
| Bluish Green | `#009E73` | 0, 158, 115 | Path B 实线边框 / ✓ / 校准成功 / Universality ✓ |
| Light Grey | `#CCCCCC` | 204, 204, 204 | 分隔线 / 内部 separator / mean pill |
| Faint Grey | `#F7F7F7` | 247, 247, 247 | Band 背景填充 |
| Charcoal | `#333333` | 51, 51, 51 | 主文字 |
| Mid Grey | `#666666` | 102, 102, 102 | 注释 / italic 副标签 |
| Arrow Grey | `#4D4D4D` | 77, 77, 77 | 连接箭头 |

Visio 操作：Design → Variants → Colors → Create New Theme Colors，把上面 8 色全填进自定义主题，后面所有 shape 用主题色引用，调色统一。

---

## 2. 容器层级（Visio Container 功能）

3 层嵌套容器（Insert → Container → Plain）：

```
[L0 Canvas 11" × 6.1875"]
├── [L1 TRAINING container]  x=0.25, y=0.85, w=7.20, h=5.05
│   ├── [L2 TOP BAND]             y=4.40, h=1.05
│   ├── [L2 PATH A strip]         y=3.20, h=1.10  (dashed orange border)
│   ├── [L2 PATH B strip]         y=1.95, h=1.20  (solid green border)
│   └── [L2 UNIVERSALITY strip]   y=1.05, h=0.80
├── [L1 INFERENCE container]  x=7.55, y=0.85, w=3.20, h=5.05
└── [L1 LEGEND strip]         x=0.25, y=0.30, w=10.50, h=0.45
```

容器属性：
- L1 / L2 容器 **无边框** 仅靠 Faint Grey `#F7F7F7` 填充区分区域
- TRAINING / INFERENCE 之间的竖线：单独画 `x=7.50, y=0.85, y=5.90` Light Grey 1 pt
- 顶部画一条横线 `y=5.95, x=0.25-10.75` Light Grey 0.5 pt（标题分割）

---

## 3. 顶部标题区（y=5.95-6.40）

| 元素 | 位置 | 样式 |
|---|---|---|
| "TRAINING — post-hoc calibration on ITB validation split" | 居中于 TRAINING 容器顶 (x=3.85, y=6.15) | Steel Blue, Small Caps, 12 pt, Bold |
| "INFERENCE — single image" | 居中于 INFERENCE 容器顶 (x=9.15, y=6.15) | Steel Blue, Small Caps, 12 pt, Bold |

---

## 4. TOP BAND（5-head IQA）— y=4.40-5.45

**背景**：Faint Grey 填充 + 无边框。

**子元素从左到右**：

1. **Dermoscopy input 占位圆**
   - 形状：Ellipse `0.55" × 0.55"` at `x=0.45, y=4.65`
   - 填充：Light Grey 渐变（实际可用浅粉灰静态色 `#F0DDDD` + 1 pt charcoal 边框）
   - 内部：手绘一个简化病灶 glyph（深色椭圆 + 不规则圆弧），或直接用 Visio 形状库 Symbol → Medical → "Lesion"，或留一个深棕色 `#8B5A3C` 椭圆 `0.30×0.20`
   - 下方文字：`x  dermoscopy input`（Charcoal 7 pt italic, 居中 at y=4.45）

2. **箭头** → `x=1.05→1.45, y=4.92` Arrow Grey 1.5 pt

3. **5-head IQA fan**（5 个 mini-rectangles 垂直堆叠）
   - 容器位置：`x=1.50, y=4.50` w=1.20, h=0.95
   - 5 个 rounded rectangle 各 `1.00" × 0.13"`，corner radius 0.02，垂直间隔 0.03
   - 每个 rect：白填充 + Steel Blue 1 pt 边框
   - 每个 rect 内部右侧文字（6 pt Charcoal small caps）：
     - Row 1: `Sharpness`
     - Row 2: `Brightness`
     - Row 3: `Completeness`
     - Row 4: `Colour temp.`
     - Row 5: `Contrast`
   - 每个 rect 内部左侧 mini-glyph（`0.10×0.10` Charcoal 单色）：
     - Sharpness: 3×3 网格 + 几条对角细线（模糊 kernel）
     - Brightness: 4 根竖条递增高度（直方图）
     - Completeness: 一个空心方框 + 角点斜线（裁剪框）
     - Colour temp: 3 根横条 (R/G/B 抽象，灰阶处理)
     - Contrast: 一条 S 型曲线
   - Visio 里 5 个 glyph 都手绘成 0.10×0.10 的 Charcoal 笔画图形

4. **会聚箭头**：5 条短斜线（Arrow Grey 1 pt）从 fan 右边 `x=2.70` 汇聚到一个 mean pill 的左边 `x=3.00, y=4.92`

5. **"mean" pill**：rounded rectangle `0.40" × 0.20"` at `x=3.00, y=4.82`，Light Grey 1 pt 边框，白填充，居中文字 `mean` 7 pt Charcoal

6. **箭头** → `x=3.40→3.85, y=4.92` Arrow Grey 1.5 pt

7. **q̄ pill**（视觉中心之一）：rounded rectangle `0.50" × 0.30"` at `x=3.85, y=4.77`，Steel Blue **2 pt** 边框（加粗强调），白填充，居中文字 `q̄` Charcoal 14 pt Bold

8. **q̄ shared dotted arch**（顶部弧形，跨越 Path A 落到 Path B 的 QCTS）
   - 从 q̄ pill 右上 `(4.35, 4.95)` 起，弧顶到达 `(5.50, 5.55)`，落点到 Path B QCTS 顶 `(5.10, 3.15)`
   - 线型：Warm Orange 1.5 pt **Dotted**，箭头开放雪佛龙
   - 弧顶上方文字（Mid Grey 6 pt italic）：`q̄ shared`
   - Visio 操作：Freeform → Curve（或用 Arc tool 拼两段三次贝塞尔）

9. **Band 底部 caption**：`frozen 5-head IQA module`，Mid Grey 6 pt italic, 居中于 y=4.42

---

## 5. PATH A — Standard TS（failure）— y=3.20-4.30

**Strip 边框**：Warm Orange 1.5 pt **DASHED**（Visio: Line → Dashes → 选第 4 个 dash 样式）+ 白填充
**Header**（strip 内部顶部居中）：`PATH A — STANDARD TS` Warm Orange Small Caps 10 pt Bold

**6 个列对齐模块**（同列 x 与 Path B 严格对齐）：

| Col | x (中心) | 元素 | 形状 | 内容 |
|---|---|---|---|---|
| 1 | 0.85 | Input icon | Ellipse `0.35×0.35` | 同 TOP BAND 病灶简化版，下方标签 `x` 7 pt |
| 2 | 2.20 | Backbone `f_θ` | Rounded rect `1.00×0.70` | Bold 8 pt 标题 `Backbone f_θ`，内部 4 条横线表示 conv stack，右上角 ❄ snowflake (Unicode `❄` Mid Grey 8 pt) |
| 3 | 3.40 | `z` label | 仅文字 in arrow | Charcoal italic 8 pt 文字 `z`，放在 col2→col4 连接箭头上方 |
| 4 | 4.30 | Standard TS | Rounded rect `0.80×0.55` | Bold 8 pt 标题 `Standard TS`，内部 🌡 thermometer glyph (Unicode `🌡` Charcoal 14 pt) 居中，右上角 🔥 flame (Mid Grey 8 pt) |
| 5 | 5.20 | `p` label | 仅文字 in arrow | Charcoal italic 8 pt `p` |
| 6 | 6.30 | End-state ⚠ | 警告三角 `0.50×0.45` | Warm Orange 填充三角，内部白色 `!` 字符，下方标签 `ρ sign-flip` Charcoal 8 pt（**无数值**） |

**列间连接箭头**：Arrow Grey 1.5 pt 水平直线，端点贴模块边

**Col 6 可选小内嵌**（信息密度提升）：在 ⚠ 右上方 `0.45×0.25` 白底 Light Grey 1 pt 边框 mini-panel，里面手绘一条 S 型曲线穿过对角虚线（reliability diagram thumbnail，纯灰阶），无任何数字标签

---

## 6. PATH B — QCTS（fix）— y=1.95-3.15

**Strip 边框**：Bluish Green **2 pt** **SOLID**（加粗以示 contribution）+ 白填充
**Header**：`PATH B — QCTS (ours)` Bluish Green Small Caps 10 pt Bold

**6 个列对齐模块（x 严格同 Path A）**：

| Col | x | 元素 | 形状 | 内容 |
|---|---|---|---|---|
| 1 | 0.85 | Input icon | 同 Path A | 完全复用（同图右键 Copy → Paste，强化"共享 backbone"视觉） |
| 2 | 2.20 | Backbone `f_θ` | 同 Path A | 完全复用 |
| 3 | 3.40 | `z` label | 同 Path A | 同 |
| 4 | 4.30 | **QCTS** | Rounded rect `1.20×0.85` (比 TS 大，强调主角) | Bold 9 pt 标题 `QCTS`，内部居中一行 8 pt 公式 `T(q̄) = softplus(T₀ + α(1−q̄))`，🌡 + 小齿轮 ⚙ 在标题右侧，右上角 🔥 flame |
| 5 | 5.20 | `p` label | 同 Path A | 同 |
| 6 | 6.30 | End-state ✓ | 圆形 `0.50×0.50` Bluish Green 填充 + 白色 ✓ 字符 | 下方标签 `calibrated` Charcoal 8 pt |

**顶部 dotted arch** 落点 = Col 4 QCTS top edge centre `(5.10, 3.15)`（已在 §4 #8 描述）

**Col 6 可选小内嵌**：reliability mini-chart 显示曲线紧贴对角（与 Path A 的内嵌镜像对比）

---

## 7. UNIVERSALITY STRIP — y=1.05-1.85

**背景**：Faint Grey 填充 + 无边框
**3 个 backbone icon 横排，居中**：

| Pos | x | 名 | 简化 glyph (`0.50×0.40`) |
|---|---|---|---|
| 1 | 1.80 | **CNN** | 4 个堆叠 conv 矩形（递减宽度），Charcoal 1 pt |
| 2 | 3.60 | **ViT** | 3×3 patch grid + 顶上一个小 attention head 圆 |
| 3 | 5.40 | **Hybrid** (ConvNeXt / Swin) | conv blocks + 半透 attention overlay (Mid Grey hatch) |

每个 icon 下方：
- 紧贴下方 0.05" 处：Bluish Green ✓ (Unicode `✓` 14 pt Bold)
- 再下方：backbone 家族名 Small Caps 7 pt Charcoal

**Strip 末尾居中 caption**（y=1.10）：`QCTS generalises across backbones` Mid Grey italic 8 pt

---

## 8. INFERENCE COLUMN — x=7.55-10.75

**容器**：Faint Grey 填充 + 无边框（与 TRAINING 用 §2 提到的中央竖线分隔）

**Header**（已在 §3）

**垂直堆叠模块（向下箭头连接，Arrow Grey 1.5 pt）**：

| Row | y | 元素 | 尺寸 | 内容 |
|---|---|---|---|---|
| 1 | 5.30 | Input | Ellipse `0.50×0.50` | 同 TOP BAND 病灶圆（缩小版），下方标签 `x` |
| 2 | 4.50 | IQA condensed | Rounded rect `0.80×0.35` | 5 条横线表示 5-head 简化版，右侧 → q̄ pill |
| 3 | 4.50 | q̄ pill | `0.45×0.25` | Steel Blue 1.5 pt 边框，内文 `q̄` 12 pt |
| 4 | 3.65 | Backbone `f_θ` | Rounded rect `0.90×0.50` | 与 TRAINING 同款 + ❄ |
| 5 | 2.75 | QCTS box | Rounded rect `0.90×0.45` | Bluish Green 1.5 pt 边框，内文 `QCTS(q̄)` 9 pt（**无公式**，公式只在 Path B 那唯一一处） |
| 6 | 1.90 | softmax pill | `0.70×0.25` | Light Grey 1 pt 边框，内文 `softmax` 8 pt |
| 7 | 1.10 | Output | Bar chart `0.90×0.35` | 2 条横条，1 条 Bluish Green (calibrated)，1 条 Mid Grey；下方标签 `calibrated p` Bluish Green 8 pt Bold |

**Row 2-3 是同一行**：IQA 横排 → q̄。其余都向下流。

---

## 9. LEGEND STRIP — y=0.30-0.75

**顶边**：x=0.25-10.75 Light Grey 0.5 pt **dotted** 横线（与主图分隔）
**内容**：5 个图标 + 标签水平排列居中

| 图标 | 标签 | x 起点 |
|---|---|---|
| ❄ | `frozen weights` | 1.00 |
| 🔥 | `fitted parameters (T₀, α)` | 3.00 |
| 📷 | `input image` | 5.50 |
| ⚠ | `TS reversal` | 7.20 |
| ✓ | `calibrated output` | 8.80 |

字号：标签 Charcoal 8 pt regular；图标 Charcoal 12 pt。无边框包围。

---

## 10. 文字 / 数字红线（违反必须删）

写完图后**逐项核查**：

- [ ] 全图无任何 ρ / QCDI / ECE / AUC 数值
- [ ] 全图无样本量（n=300/360/660/1500/2298/10015）
- [ ] 全图无 [0,1] 区间括号
- [ ] 全图无 reversal 幅度数字（+0.241、−0.249 等）
- [ ] 全图无 reliability diagram 的坐标轴刻度数字（如有 mini-chart 内嵌，只画曲线 + 对角线，无 ticks）
- [ ] 唯一允许的数学符号：QCTS 模块内的 `T(q̄) = softplus(T₀ + α(1−q̄))`
- [ ] `ρ sign-flip` 作为 Path A 末端**文字标签**允许（无数值附着）
- [ ] ❄ 🔥 📷 ⚠ ✓ 🌡 ⚙ 这些 Unicode 图标允许，无其他 emoji
- [ ] Path A 边框 **dashed**，Path B 边框 **solid**（B&W 打印冗余）
- [ ] Path A / B 6 列严格 x 对齐（拉参考线后逐一对齐 + Align Center）
- [ ] 仅 3 种饱和色（Steel Blue / Warm Orange / Bluish Green），其余 grayscale
- [ ] 画布 ≥70% 白色

---

## 11. Visio 操作 checklist（顺序执行）

```
1. File → New → Letter Landscape, 11×6.1875 inch
2. Design → Variants → Colors → Create New Theme Colors（输入 §1 8 色）
3. View → Add Guides（5 条参考线，§1 数值）
4. Insert → Container → Plain（L1 / L2 共 4 个容器，§2 坐标）
5. 中央竖线 + 顶部横线（§2 末段）
6. 顶部标题文字（§3）
7. 顶 BAND：dermoscopy 圆 → IQA fan (5 mini-rect) → mean pill → q̄ pill → 顶部 dotted arch（§4）
8. PATH A：6 列模块，复制对齐（§5）
9. PATH B：复制 Path A col 1-3，重画 col 4-6（§6）
10. Universality strip：3 backbone icon（§7）
11. Inference column：7 行垂直堆叠（§8）
12. Legend strip：5 个 icon + 标签（§9）
13. 顶部 dotted arch 最后画（盖在所有模块上层）
14. View → Pan & Zoom → 整图肉眼 check
15. 按 §10 逐条核查红线
16. File → Save As → PDF（保留矢量），输出 fig_method.pdf
17. File → Save As → SVG，输出 fig_method.svg
18. 备份旧版：cp figures/fig_method.pdf figures/fig_method.v2_backup.pdf（若存在）
19. 覆盖到 figures/ 目录
```

---

## 12. 配套备份与替换

| 文件 | 状态 |
|---|---|
| `PROMPT_fig_method_nanobanana.md` | 已被 v3 Visio 版替换（即将再次覆盖为本文件 → 不，本文件单独存为 `VISIO_SPEC_fig_method.md`） |
| `PROMPT_fig_method_nanobanana.v2_backup.md` | v2 NanoBanana prompt（双路对比版）|
| `PROMPT_fig_method_nanobanana.v1_backup.md` | v1 NanoBanana prompt（4-stage 水平版）|
| `figures/fig_method.pdf` | 待用户 Visio 画完后覆盖 |
| `figures/fig_method.svg` | 待用户 Visio 画完后覆盖 |

主文 LaTeX 引用 `\includegraphics{figures/fig_method}` 不变，PDF 覆盖即可。

---

## 13. 复杂度说明（为什么这个结构"够复杂"）

- **3 层容器嵌套**：L0 canvas / L1 TRAINING vs INFERENCE / L2 TOP-A-B-Universality 四 band
- **跨 band 共享数据流**：q̄ pill 在 TOP BAND，但被 Path B QCTS 用顶部弧形 dotted arch 拉过去（视觉上贯穿 3 band）
- **严格列对齐**：Path A / B 6 列 x 坐标完全相同，是"对比"的核心视觉机制
- **5-head IQA fan**：5 个 mini-rect 各带独立 glyph，信息密度大
- **2 路 reliability mini-chart**：Path A / B 末端可选内嵌曲线（一条穿过对角、一条贴对角），无数字
- **Universality strip**：3 backbone × ✓ × 名称，回应 Claim 2 universality
- **Inference 列**：7 行垂直 pipeline，独立于 TRAINING
- **Legend strip**：5 icon 解释 ❄ 🔥 📷 ⚠ ✓
- **总元素数**：≈ 50 形状 + 15 箭头 + 25 文字 ≈ 90 个对象（典型顶会主图复杂度）
