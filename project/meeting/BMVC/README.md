# BMVC P2 投稿目录

**Deadline**：2026-07-15 ~ 07-18（60 天扩展路线）
**目标命中率**：**75-77%**（网上获取约束 + LLM-based adversarial review）
**当前状态**：W1 D1 完成（5-20）— §5.4 universality 落地，故事框架定稿

---

## ⚡ 任何新会话第一步：读这 3 个文件（顺序固定）

> ⚠️ **最怕另开 Sonnet 跑偏**。任何 Claude / Sonnet / Opus 会话进入本目录前，必须按顺序读完下列 3 个文件，否则会丢失关键约束。

### 1️⃣ [`STORY_FRAMEWORK.md`](STORY_FRAMEWORK.md) — **故事框架主文档（反跑偏）**
- 7 个跑偏定义 + 三条核心论点（Claim 1/2/3）
- 章节顺序锁定（§1 → §7）
- **锁定数字表**（Table 1 / Table 3 / QCTS 参数 / Zero-shot / ImageNet-C）— 写作时直接抄
- 防御性写作 7 条硬规则（R1-R7）

### 2️⃣ [`ACCEPTANCE_CRITERIA.md`](ACCEPTANCE_CRITERIA.md) — **75-77% 命中率验收标准**
- 10 个 lever 命中率分解表 + 不达标扣分
- 每个 W1-W8 任务的具体验收阈值
- 红线清单（5 条触发即崩）
- task 完成判定流程（不存在"基本完成"）

### 3️⃣ [`DATA_INVENTORY.md`](DATA_INVENTORY.md) — **数据全景表**
- 5 个训练好的 backbone + checkpoint 路径
- 10 个核心结果 csv 路径
- W1-W8 已完成 vs 待跑实验清单
- 关键脚本路径 + 数据集元信息

### 4️⃣ [`BMVC_LOG.md`](BMVC_LOG.md) — 单一日志真源（按时间顺序）
- 5-19/5-20 策略调整 + 已完成项详细 entry
- 60 天 8 周日程表
- 防御性写作 checklist

---

## 📂 当前活跃文件

```
project/meeting/BMVC/
├── README.md                  ← 本文件（精简入口）
├── STORY_FRAMEWORK.md         ← ★ 故事框架（反跑偏主文档）
├── ACCEPTANCE_CRITERIA.md     ← ★ 75-77% 验收标准
├── DATA_INVENTORY.md          ← ★ 数据全景表
├── BMVC_LOG.md                ← 时间顺序日志
├── itb_paper.tex              ← 论文主文件（W1 D1 后：12 页正文 + 3 页 ref）
├── itb_paper.pdf              ← 当前编译输出
├── table1_main.tex            ← Table 1（已删 Q-VIB 3 行，加 EDL 行 TBD）
├── table2_ablation.tex        ← QCTS form ablation
├── table3_universality.tex    ← Table 3（3 backbone × {raw/TS/QCTS}）NEW
├── egbib.bib                  ← 文献（无 anonymous 自引）
├── bmvc2k.cls/.bst            ← BMVC 模板
└── figures/                   ← 主图 + fig5/fig6（fig7 待 D2-D4）

archive/                       ← 历史 plan，不再使用
```

---

## 🔬 BMVC 三条核心论点（详见 STORY_FRAMEWORK.md）

1. **TS reversal 是真实现象，两种 manifestation**
   - Std VIB: ρ sign-flip（−0.024 → +0.241）
   - ViT-Tiny: QCDI sign-flip（+0.023 → −0.029）
   - ResNet-50: neutral（强 quality-aware backbone 不反转）

2. **QCTS = universal post-hoc fix**：2 参数 softplus，from B1-B3 inductive biases，跨 VIB/CNN/Transformer 三家族

3. **q̄ = universal per-input quality scalar**：learned (dermoscopy) 或 a priori (ImageNet-C severity) 都适用

---

## ⚠️ 严禁事项（违反即跑偏，详见 STORY_FRAMEWORK.md 第 7 条 + ACCEPTANCE_CRITERIA.md 红线）

- ❌ 改 Abstract 第一句离开 TS reversal hook
- ❌ 写"TS always reverses" / "reversal is universal" 等绝对化措辞
- ❌ Q-VIB / VisiScore-Net / anonymous2025\* 字样重新出现
- ❌ 凭印象写数字（必须 csv 核算）
- ❌ Reader Study 数据伪造（永久红线 1）
- ❌ 联系诊所 / 线下采集（永久红线 2）
- ❌ 改 §5 章节顺序（5.2→5.3→5.4→5.5→5.6 已锁）

---

## 📋 当前进度速览（详见 ACCEPTANCE_CRITERIA.md）

| Lever | 状态 | 备注 |
|---|---|---|
| §5.4 Universality (3 backbone) | ✅ W1 D1 落地 | Table 3 + fig5/6 + nuanced framing |
| §5.5 ImageNet-C | 🚧 数据就位，写作待 D2-D4 | 14 corruption × 5 severity csv 已生成 |
| EDL baseline | 🚧 训练完 AUC 0.8622，ITB 推理待 D2 | Table 1 EDL 行 TBD |
| L1 跨域 (CheXpert) | ❌ W2 D13-D14 | |
| L1 跨域 (Fundus) | ❌ W3 D15-D17 | |
| L2 backbone (ConvNeXt/Swin) | ❌ W1 D5-D7 训练 | |
| L3 quality scalar 对比 | ❌ W2 D10 | |
| L4 真实低质照片 | ❌ W3 D15-D18 | |
| L5 DCA / Triage / dermatologist baseline | ❌ W4 | |
| L6 Theory 1 页 | ❌ W4 D26-D27 | |
| L8 Reproducibility | ❌ W7 | |
| L9 LLM adversarial review × 5 | ❌ W6 | |
| L10 Supplementary 30-50 页 | ❌ W7 | |

---

## 🚦 任何会话开始前 checklist

```
1. cd D:/YJ-Agent/project/meeting/BMVC
2. Read STORY_FRAMEWORK.md
3. Read ACCEPTANCE_CRITERIA.md（查当前任务的验收阈值）
4. Read DATA_INVENTORY.md（确认要用的数据是否就位）
5. Read BMVC_LOG.md 最新 entry
6. grep itb_paper.tex 确认无 Q-VIB / VisiScore 残留
7. 开始动手前 → 把任务在 TaskCreate 里登记
```

**如果用户描述的任务与 STORY_FRAMEWORK.md 冲突 → 停下来澄清，不要按用户描述执行**。
