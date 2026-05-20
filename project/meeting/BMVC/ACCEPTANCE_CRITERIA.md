# BMVC 验收标准（75-77% 命中率目标分解）

**目标**：60 天扩展 + 网上获取约束下命中 75-77%
**Baseline**：30 天版 65-75% → 必须额外撬动 10 个 lever 提升 10-12 个百分点
**最后更新**：2026-05-21

---

## 🎯 命中率分解表（最新状态）

| Lever | 目标版本 | 不达标扣分 | 状态 |
|---|---|---|---|
| L1. 跨域 modality | ImageNet-C + CheXpert + Fundus（共 4） | −5% | ✅ 全部完成 |
| L2. Backbone 数量 | 5 backbone（Std VIB / ResNet-50 / ViT-Tiny / ConvNeXt / Swin） | −3% | ✅ 完成（5 backbone） |
| L3. Quality scalar | 5 种对比（5-head IQA / BRISQUE / CLIP-IQA / LaplacianVar / RF） | −3% | ✅ Table S1 + §5.3 |
| L4. 真实低质照片 | 100-200 张公开真实 dermoscopy | −2% | ✅ 174 张，ECE=0.073 |
| L5. 临床相关性 | DCA + Triage + Published dermatologist baseline | −3~−5% | ✅ DCA max NB=0.192，Triage 20% budget |
| L6. Theory | 完整 1 页 + IB connection + PAC-Bayes sketch | −3% | ✅ §4.3 IB+PAC-Bayes |
| L7. Statistics | Cohen's d + Bonferroni + Power analysis | −2% | ✅ d=0.452, power=0.929, Bonferroni p=0.0015 |
| L8. Reproducibility | Code + Docker + ITB v1.0 + 一键复现 | −3% | ✅ project/release/ 骨架完成（Zenodo 接受后激活） |
| L9. 写作 review | 5-8 轮 + 3 LLM persona + BMVC form × 2 | −2% | 🟡 adversarial review ✅；5 attack 整合 ✅；Round 1 ✅；Round 2-5 ❌ |
| L10. Supplementary | 30-50 页 + pre-emptive rebuttal | −2% | 🟡 ~25 页（A1-A10）；target 30-50 未达 |

**当前预测命中率：≈75%**（L1-L8 全完成；L9/L10 部分完成）
**剩余扣分风险：~2%**（L9 Round 2-5 + L10 页数）

---

## 🔍 W1 D1 已完成项验收（已 PASS）

| 验收项 | 阈值 | 实际 | 状态 |
|---|---|---|---|
| Abstract 第一句 = TS reversal hook | 含 "reverse" + ρ −0.024 → +0.241 | ✅ | PASS |
| Intro 加 reversal hook 段 | ≥1 段 + 指向 §5.4 | ✅ | PASS |
| Table 1 删 Q-VIB | grep Q-VIB itb_paper.tex 无残留 | ✅ | PASS |
| Table 1 加 EDL 行 | 1 行（数字可 TBD） | ✅ | PASS（TBD） |
| §5.2 末段 reversal 强化 | ≥3 句 + 指向 §5.4 | ✅ | PASS |
| §5.4 占位替换 | Table 3 + 正文 ≥ 4 段 + nuanced framing | ✅ | PASS |
| §5.4 fig5 + fig6 引用 | 2 张图引用解析 | ✅（合并为 fig:universality_figs） | PASS |
| 编译干净 | 0 error / 0 undefined ref | ✅ | PASS |
| 主文页数 ≤ 14 | 主文 12 页 + ref 3 页 | ✅ | PASS |
| 防御性数字一致性 | 4 个 abstract 数字与 Table 1 一致 | ✅ | PASS |

---

## 🚧 W1 D2-D7 待验收项

### D2 - EDL infer + Table 1 EDL 数字补
**验收阈值**：
- [ ] `scripts/infer_edl_itb.py` 写完并跑通
- [ ] ITB-LQ / ITB-HQ ECE 数字落 csv：`results/edl/itb_predictions.csv`
- [ ] Table 1 EDL 行 TBD 全部替换为真实数字 + bootstrap 95% CI
- [ ] EDL ρ(H,q̄) 算出，确认 EDL 落在 Quality-Fragile 还是 Quality-Oblivious 区
- [ ] 论文 §5.2 段补 EDL 行为描述

### D2-D4 - §5.5 ImageNet-C 章节
**验收阈值**：
- [ ] 用 `corruption_robustness_itb-lq.csv` 算每 corruption 的 raw_ρ / ts_ρ / qcts_ρ
- [ ] 反转 corruption 数 ≥ 3/14（否则改写为 "ImageNet-C corroborates universal scalar framing without showing reversal"）
- [ ] fig7 散点图（14 corruption × {raw_ρ, ts_ρ}，对角线参考，反转点高亮）→ `figures/fig7_imagenetc_reversal.{pdf,svg,png}`
- [ ] §5.5 正文 ≥ 300 词 + framing 句："To verify that TS reversal is not a dermoscopy artefact, we evaluate the same protocol on ImageNet-C..."
- [ ] q̄ framing 拓宽为 "any per-input quality scalar (learned or a priori)"
- [ ] bootstrap CI 算到每个 corruption ρ

### D5 - 4 主图 METHOD_META 清理
**验收阈值**：
- [ ] `gen_bmvc_figures.py` METHOD_META 删 F/G 条目
- [ ] fig{1,2,3,4} 重跑生成新 SVG/PDF/PNG
- [ ] grep figures/ 无 "F:" / "G:" / "Q-VIB" / "VisiScore" 残留
- [ ] `fig_method.svg` 重跑（已改 5-head IQA，但 svg 未重生）
- [ ] grep fig_method.svg 无 "VisiScore-Net" 字符

### D6 - Limitations / Discussion 调整
**验收阈值**：
- [ ] Limitations 段含：(1) reversal backbone-dependent；(2) ITB synthetic degradation；(3) q̄ 学习成本 + IQA module 分辨率上限
- [ ] Discussion 第一段含：structural reason TS reversal happens（quality-independent scalar 在 weakly quality-aware backbone 上的优化路径）
- [ ] 每张图 caption 末加 takeaway 一句话

### D7 - 数字一致性 final pass + 编译
**验收阈值**：
- [ ] grep "TS always" / "reversal is universal" / "Q-VIB" / "VisiScore-Net" / "anonymous2025" 全部 0 命中（"do not claim ... universal" 例外可接受）
- [ ] 每个 ρ 数字附近有 p-value 或 CI
- [ ] Abstract / Intro / §5.2 / §5.4 / §5.5 中所有 ρ / ECE / QCDI 与 csv 源对照（手工逐条 + grep -E "[\\+\\-][0-9]\\.[0-9]+"）
- [ ] pdflatex × 2 + bibtex + pdflatex × 2 → 0 error / 0 undef
- [ ] 主文 ≤ 14 页

---

## 📋 W2-W8 高层验收阈值（每周必达 minimum）

### W2 (D8-D14)
- [ ] L3 启动：≥ 2 种 quality scalar 跑通（VisiScore-Net + BRISQUE）+ 对比表
- [ ] 过度参数化消融完整：QCTS / QCTS-dimwise / QCTS-bin10 / QCTS-MLP
- [ ] CheXpert 跨域：DenseNet-121 + image quality 评分作 q̄，ITB-style 评测
- [ ] EDL infer 完整版（如 D2 没完成则补）

### W3 (D15-D21)
- [ ] L1 启动：Fundus 跨域（DRIVE / IDRiD + 屈光介质质量评分）
- [ ] L4 启动：网上采集 ≥ 100 张公开真实低质 dermoscopy（来源已列）
- [ ] MC Dropout + Deep Ensemble variance vs q̄ 散点 + bootstrap ρ
- [ ] Sub-population fairness 全维度（age × gender × Fitzpatrick × lesion type × body location）

### W4 (D22-D28)
- [ ] L5 启动：DCA 曲线（模型预测 × 临床 threshold × net benefit）
- [ ] L5 + Triage simulation（confidence threshold 触发转诊的 referral/missed rate）
- [ ] L5 + Published dermatologist baseline reference line（ISIC 2018-2020 challenge human performance）
- [ ] L6 完成：Theory 1 页（softplus uniqueness + IB connection + PAC-Bayes）
- [ ] L4 真实照片采集完成 + 与 programmatic degradation 对照分析

### W5 (D29-D35)
- [ ] Failure mode auto-clustering（HDBSCAN on confidently-wrong embedding）
- [ ] §6 升级（含 failure cluster prototypes）
- [ ] 10-12 主图 + 20+ supplementary 图全部 5-8 版迭代到出版级

### W6 (D36-D42)
- [ ] L9 启动：5 轮 LLM-based adversarial review（GPT-5 / Claude Opus / Gemini × 不同 persona）
- [ ] BMVC 评审 form 自评 × 2 轮
- [ ] Pre-emptive rebuttal in Discussion（消灭 5-8 攻击点）

### W7 (D43-D49)
- [ ] L8 + L10：30-50 页 Supplementary
- [ ] Code release (anonymous GitHub) + Docker + requirements.txt 锁版本 + 一键复现 script + ITB v1.0 license

### W8 (D50-D56)
- [ ] 数字一致性 final pass × 2 轮
- [ ] pdflatex × 3 编译干净
- [ ] 页数压（主文 ≤ 14）
- [ ] buffer × 3 天

---

## 🚨 红线（任意触发立即停手，命中率瞬间崩到 < 30%）

1. ❌ Reader Study 数据伪造（永久红线 1）
2. ❌ 联系诊所 / 线下采集（永久红线 2，违反 2026-05-20 用户确认）
3. ❌ 自引 anonymous2025\* 任何未发表工作
4. ❌ Q-VIB / VisiScore-Net 字样回到 itb_paper.tex
5. ❌ TS reversal absolute claim（"universal" / "always"）

---

## 📝 任何 task 完成判定流程

```
Step 1: 查 ACCEPTANCE_CRITERIA.md 找该 task 的验收阈值
Step 2: 逐条对照实际产出
Step 3: 全条 PASS → 更新 BMVC_LOG.md + 移到下一项
        任一 FAIL → 不要标完成，回去补
Step 4: 跑 grep 防御检查（R1-R7 硬规则）
Step 5: 编译 + 页数检查
```

不存在"基本完成"或"差不多了"。要么全 PASS 要么继续。
