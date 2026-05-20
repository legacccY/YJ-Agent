# Teaser Source Folder — Composition Guide

**目的**：主文 Fig.~1 (teaser) 的素材库。用户自行用 Illustrator/Figma/Affinity 等拼图。

---

## 文件命名

```
{Lesion_ID}__{Column}.png
```

| Prefix | 用途 |
|--------|------|
| `L1_HQ` | 第 1 行病灶（ISIC_8713598，本身高质） |
| `L2_Blur` | 第 2 行病灶（ISIC_8370773，原本就因模糊触发过分自信） |
| `L3_Colour` | 第 3 行病灶（ISIC_9383110，原本就因 colour shift 触发过分自信） |
| `L4_Combined` | 第 4 行病灶（ISIC_9989680，原本就因 blur+contrast 联合攻击触发过分自信） |

每个 lesion 都生成了 4 列处理版本（clean / blur / colour / combined）以便你**任选拼法**：
- 推荐做法 A（对角线）：每行只用对应主攻击的那一格 → L1 取 clean、L2 取 blur、L3 取 colour、L4 取 combined
- 推荐做法 B（满矩阵 4×4）：每个病灶都展示 4 种处理，对比同一病灶在不同 attack 下的退化幅度

---

## 推荐 4×3 矩阵（与原版 fig1_teaser 兼容，可直接复用，最 paper-friendly）

| 行 \ 列 | Col 1：Clean HQ | Col 2：Primary attack | Col 3：Std VIB 输出 | Col 4：QCTS 输出 |
|---|---|---|---|---|
| Row 1（L1） | `L1_HQ__col1_clean.png` | (空) | $p_{\text{benign}} = 99.0\%$ ✅ | $p_{\text{benign}} = 99.0\%$ ✅ |
| Row 2（L2） | `L2_Blur__col1_clean.png` | `L2_Blur__col2_blur.png` | $p_{\text{mel}} = 89.0\%$ ⚠️ | $p_{\text{mel}} = 74.8\%$（-14 pp）|
| Row 3（L3） | `L3_Colour__col1_clean.png` | `L3_Colour__col3_colour.png` | $p_{\text{mel}} = 95.5\%$ ⚠️ | $p_{\text{mel}} = 83.0\%$（-13 pp）|
| Row 4（L4） | `L4_Combined__col1_clean.png` | `L4_Combined__col4_combined.png` | $p_{\text{mel}} = 81.2\%$ ⚠️ | $p_{\text{mel}} = 68.4\%$（-13 pp）|

**重要**：所有 4 个病灶 **ground-truth 都是良性**（benign nevus）。

---

## 每张图的 IQA 分数（用作 overlay 文本，可直接抄）

来源：`project/scripts/selected_teaser.json`

| 文件名（任选一列即可） | $\bar q$ | Primary dim ↓ | Std VIB $p_{\text{mel}}$ | QCTS $p_{\text{mel}}$ |
|---|---|---|---|---|
| L1（HQ baseline）        | 0.76 | — (none)             | 0.010 | 0.010 |
| L2（Blur attack）         | 0.38 | $q_1$ (Sharpness)=0.002 | 0.890 | 0.748 |
| L3（Colour shift）        | 0.36 | $q_4$ (Colour temp.)=0.000 | 0.955 | 0.830 |
| L4（Combined blur+contrast）| 0.41 | $q_1, q_5$=0.002 | 0.812 | 0.684 |

---

## 推荐 caption（沿用主文当前 caption，无需重写）

> **Calibration collapse under image quality shift (all four lesions are ground-truth benign).**
> *Row 1*: clean dermoscopy inputs — column 1 is a high-quality clinical reference, columns 2–4 are the same lesion pre-degradation.
> *Row 2*: after blur ($q_1$), colour shift ($q_4$), and combined blur+contrast attacks (primary affected dimension annotated in red).
> *Row 3*: Std VIB assigns 81–96% melanoma probability under any heavy degradation (red); QCTS (orange) brings predictions down by 13–14 pp without retraining.
> *Takeaway:* a quality-aware post-hoc correction softens exactly the cases where a quality-oblivious model would be confidently wrong.

---

## 风格建议

- 圆角矩形 crop 每张图（半径 ~ 8% 边长）
- 行间留 6-8 px 间距，列间 4-6 px
- 每列顶部加列名（"High Quality" / "Blur" / "Colour Shift" / "Combined"）
- 每行右侧加 2 条堆叠概率条：红条 = Std VIB，橙条 = +QCTS，浮 0–100% 标尺
- 主攻击维度（$q_1$ / $q_4$ / $q_1,q_5$）用红色 6-7 pt sans-serif 写在每张图右下角
- 整体 figure 横向占 0.9-1.0 \linewidth，PDF 输出 300 dpi

完成后导出为 `fig1_teaser.pdf` 覆盖到 `figures/`。
