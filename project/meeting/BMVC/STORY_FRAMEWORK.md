# BMVC 故事框架（反跑偏主文档）

**目标命中率**：75-77%（60 天扩展 + 网上获取约束下的上限）
**最后更新**：2026-05-20
**适用范围**：任何 Claude / Sonnet / Opus 会话写 BMVC 内容前必读

---

## ⛔ 跑偏定义（命中下列任何一条立即停止操作）

1. **改动 Abstract 第一句**离开 TS reversal hook
2. **写"TS always reverses"/"reversal is universal"**等绝对化措辞
3. **凭印象写数字**而非从 `results/backbones/*.csv` 核算
4. **重新加入 Q-VIB / VisiScore-Net / anonymous2025\* 字样**
5. **删掉防御性措辞**（"derived from inductive biases"、"most pronounced on weakly quality-aware backbones"、"we sketch why"）
6. **改动 §5 章节顺序**（5.2→5.3→5.4→5.5→5.6 已固定，见下方故事弧）
7. **把 reversal 单一化为 ρ flip 或 QCDI flip**——必须保留"两种 empirical signatures"双层 framing

---

## 🎯 三条核心论点（论文一切内容服务于此）

### Claim 1：TS reversal 是真实现象，两种 manifestation

> Standard temperature scaling — 默认 post-hoc calibrator — 在 quality-stratified setting 下系统性误导弱 quality-aware backbone。具体：
> - **Std VIB**：ρ sign-flip（−0.024 → +0.241）
> - **ViT-Tiny**：QCDI sign-flip（+0.023 → −0.029，TS 牺牲 HQ 救 LQ）
> - **ResNet-50**：neutral（已强 quality-aware，TS 无作用）

**绝对禁止**：写"TS always reverses" / "reversal is universal across architectures"
**必须写**：reversal 是 **weakly quality-aware backbone 的属性**，不是 dermoscopy artefact，也不是 architecture-universal。

### Claim 2：QCTS 是 universal post-hoc fix

> 两参数 softplus(T₀ + α(1−q̄))，从 3 个 inductive biases (B1 monotonicity / B2 positivity / B3 smoothness) 推导出来。不是 theorem，是 derivation sketch。

**绝对禁止**：写"we prove" / "theorem" / "uniqueness"
**必须写**："derived from inductive biases" / "we sketch why" / "the simplest candidate satisfying B1-B3"

### Claim 3：q̄ 是 universal per-input quality scalar

> Image quality scalar 可以是 learned (dermoscopy q̄) 或 known a priori (corruption severity)。QCTS 不依赖具体 q̄ 的来源。

**适用**：ImageNet-C 章节（§5.5）、CheXpert 跨域（W2 D13-D14）、Fundus（W3 D15-D17）
**绝对禁止**：把 q̄ 绑死在 VisiScore-Net / 5-head IQA module 上（这只是 dermoscopy domain 的实现）

---

## 📐 故事弧（章节顺序锁定）

```
§1 Intro
├── §1.1 问题陈述：medical AI 部署在 consumer devices，quality varies
├── §1.2 quality-oblivious calibration = fundamental blind spot
├── §1.3 ★ Reversal hook ★（Std VIB ρ −0.024 → +0.241 + ViT-Tiny QCDI flip + ResNet-50 neutral）
└── §1.4 QAC / QCDI / Taxonomy / ITB / QCTS 框架介绍

§2 Related Work（calibration / medical AI benchmarks / IQA / dermatology AI 四块）

§3 QAC + QCDI + Taxonomy（3 类：Oblivious / Fragile / Aware）

§4 ITB Benchmark + QCTS
├── §4.1 ITB construction
├── §4.2 QCTS formulation
├── §4.3 ★ Derivation from inductive biases ★（B1+B2+B3，排除 linear/ReLU/piecewise/exp）
└── §4.4 Optimisation

§5 Experiments
├── §5.1 Setup（training / metrics）
├── §5.2 Main results
│   ├── Table 1（7 baselines × ITB-LQ/HQ × {AUC,ECE,QCDI,ρ}）
│   └── ★ §5.2 末段 reversal 强化 ★（指向 §5.4）
├── §5.3 QCTS Analysis
│   ├── fig3 (T(q̄) curve / per-deg ECE / qbar bin)
│   └── Table 2 ablation (softplus vs linear vs piecewise)
├── §5.4 Universality (NEW)
│   ├── Table 3（3 backbone × {raw/+TS/+QCTS}）
│   └── fig:universality_figs (a) per-bin T* (b) QCDI flip
├── §5.5 ImageNet-C (NEW)
│   ├── q̄ framing = "any per-input quality scalar (learned or a priori)"
│   ├── fig7 scatter (raw_ρ vs ts_ρ on 14-19 corruptions)
│   └── 反转 corruption 数 / 总数 = X/19
└── §5.6 Generalisation/Fairness
    └── fig4 (HAM/PAD zero-shot + Fitz V-VI)

§6 Discussion + Limitations
├── §6.1 Structural reason TS reversal happens
├── §6.2 QCTS ceiling = post-hoc 本质（不修 feature extraction）
├── §6.3 Failure mode audit（3-mode breakdown）
└── §6.4 Limitations（必须含：reversal backbone-dependent，ITB synthetic degradation，q̄ 学习成本）

§7 Conclusion
```

---

## 🔒 锁定数字（不可凭印象改写，全部从 csv 核算）

### Table 1 (Main results, ITB-LQ n=300 / ITB-HQ n=360)

| Method | AUC-LQ | ECE-LQ | AUC-HQ | ECE-HQ | QCDI | ρ |
|---|---|---|---|---|---|---|
| EfficientNet-B3 | 0.751 | 0.345 | 0.938 | 0.068 | +0.277 | −0.123 |
| Focal+LS | 0.708 | 0.533 | 0.884 | 0.492 | +0.041 | −0.059 |
| MC Dropout (30×) | 0.693 | 0.615 | 0.808 | 0.473 | +0.142 | −0.114 |
| Deep Ensemble (5×) | 0.711 | 0.440 | 0.868 | 0.339 | +0.101 | −0.123 |
| EDL | TBD | TBD | TBD | TBD | TBD | TBD |
| Std VIB | 0.553 | 0.146 | 0.587 | 0.129 | +0.016 | −0.153 |
| Std VIB + TS | 0.582 | 0.175 | 0.732 | 0.160 | +0.015 | **+0.241** |
| **Std VIB + QCTS** | 0.563 | **0.079** | 0.580 | 0.075 | **+0.004** | **−0.249** |

### Table 3 (Universality, 3 backbones × {raw / +TS / +QCTS})

| Backbone | Method | ECE-LQ | ECE-HQ | QCDI | ρ |
|---|---|---|---|---|---|
| Std VIB | Raw | 0.146 | 0.129 | +0.016 | −0.153 |
| Std VIB | +TS | 0.175 | 0.160 | +0.015 | **+0.241** ⚠️ ρ flip |
| Std VIB | +QCTS | 0.079 | 0.075 | +0.004 | −0.249 |
| ResNet-50 | Raw | 0.050 | 0.036 | +0.014 | −0.368 |
| ResNet-50 | +TS | 0.029 | 0.025 | +0.004 | −0.368 |
| ResNet-50 | +QCTS | 0.046 | 0.031 | +0.014 | −0.380 |
| ViT-Tiny | Raw | 0.058 | 0.036 | +0.023 | −0.160 |
| ViT-Tiny | +TS | 0.043 | 0.072 | **−0.029** ⚠️ QCDI flip | −0.160 |
| ViT-Tiny | +QCTS | 0.058 | 0.075 | −0.017 | −0.266 |

数据源：`project/results/backbones/section54_summary.csv`

### QCTS 拟合参数（3 backbone）

| Backbone | T₀ | α | T(q̄=0) | T(q̄=1) |
|---|---|---|---|---|
| Std VIB | 1.17 | 0.96 | 2.24 | 1.44 |
| ResNet-50 | 0.55 | 0.24 | 0.99 | 0.92 |
| ViT-Tiny | 0.52 | 1.40 | 1.93 | 0.95 |

### Zero-shot 验证（§5.6）

| Dataset | n | Std VIB ρ | Std VIB+QCTS ρ | p |
|---|---|---|---|---|
| HAM10000 | 10,015 | −0.033 | −0.108 | < 10⁻²⁶ |
| PAD-UFES | 2,298 | −0.075 | −0.150 | < 10⁻¹² |

### ImageNet-C robustness 总览

| Backbone | Clean AUC | Mean Corruption AUC | AUC drop |
|---|---|---|---|
| ResNet-50 | 0.691 | 0.623 | 0.068 |
| ViT-Tiny | 0.718 | 0.645 | 0.073 |

---

## 🛡️ 防御性写作硬规则（违反即跑偏）

| 编号 | 严禁写法 | 必须写法 |
|---|---|---|
| R1 | "TS always reverses" / "universal reversal" | "most pronounced on weakly quality-aware backbones" |
| R2 | "we prove" / "theorem" / "uniqueness" | "derived from inductive biases" / "we sketch why" |
| R3 | "doctors confirmed" / "clinicians validated" | "decision-curve analysis suggests" / "triage simulation indicates" |
| R4 | "Q-VIB" / "VisiScore-Net" / "anonymous2025\*" | "5-head IQA module" / 删去自引 |
| R5 | "best ECE in literature" / "state-of-the-art" | 用具体数字 + bootstrap CI |
| R6 | bare numbers | 每个 ρ 数字附 p-value，每个 ECE/QCDI 附 bootstrap 95% CI |
| R7 | 把 q̄ 绑死成 VisiScore-Net | "any per-input quality scalar (learned or a priori)" |

---

## 📊 已实验完成 vs 待跑（按 BMVC_LOG 60 天日程）

### ✅ 已完成（数据已就位）
- ResNet-50 / ViT-Tiny 训练（best AUC 0.884 / 0.903）
- 4 backbone QCTS 拟合（section54_summary.csv）
- fig5 per-bin optimal T* + fig6 TS reversal bar
- ImageNet-C 14 corruption × 5 severity × ITB-LQ 300 张
- EDL baseline 训练（best AUC 0.8622，但 ITB 推理未做）
- HAM10000 / PAD-UFES zero-shot
- ITB-Diverse Fitzpatrick V-VI fairness

### 🚧 W1 剩余（D2-D7）
- D2-D4：§5.5 ImageNet-C 章节 + fig7 散点（raw_ρ vs ts_ρ × 14 corruption）
- D2：EDL infer 跑 ITB → Table 1 EDL 行补数字
- D5-D7：fig_method.svg 重跑 + 4 主图删 F/G + Limitations/Discussion 调整

### 📋 W2-W8（命中率提升关键 lever，详见 ACCEPTANCE_CRITERIA.md）
W2：过度参数化消融完整 / 5 种 quality scalar 对比 / CheXpert 跨域
W3：Fundus 跨域 / 公开真实低质 dermoscopy 100-200 张 / Sub-population fairness
W4：DCA / Triage simulation / Theory 1 页
W5：Failure clustering / 图表全部重做
W6：5 轮 LLM-based adversarial review
W7：30-50 页 Supplementary + Code/Docker release
W8：编译 + buffer

---

## 🚨 任何会话开始前必读 checklist

1. ✅ 读本文件至少一遍
2. ✅ 读 `BMVC_LOG.md` 最新 entry
3. ✅ 读 `ACCEPTANCE_CRITERIA.md` 确认当前任务的验收阈值
4. ✅ grep itb_paper.tex 确认无 Q-VIB / VisiScore 残留
5. ✅ 任何新数字写入前 → 先 grep 数据源 csv

**如果用户描述的任务与本文件冲突 → 停下来澄清，不要按用户描述执行**（用户可能忘了已有约束）。
