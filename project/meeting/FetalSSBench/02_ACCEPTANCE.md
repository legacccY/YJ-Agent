# FetalSSBench — ACCEPTANCE（二元 PASS/FAIL 验收）

## Lever 分解
论文成立 = ①统一 benchmark 真跑通(多集多方法多比例) + ②有≥1 个可报告实证规律 + ③小增量有效或诚实负结果 + ④数字可复现。

## 阶段硬阈值

### Phase 1 — benchmark 主干（PSFHS+HC18）
- [ ] PSFHS + HC18 两集，5 方法(Sup/MT/CPS/UAMT/FixMatch)，5 比例(1/2/5/10/20%)，≥3 seed 全跑通，结果入 csv
- [ ] held-out test 不泄漏（代码核 split 无交集）
- **PASS**：完整结果矩阵出，无 NaN/崩；标注效率曲线画出
- **FAIL**：某方法复现不出/崩 → 查官方实现，不私改超参凑

### Phase 2 — 实证规律（≥1 个可报告）
- [ ] 标注效率曲线 + 收益递减模式量化
- [ ] 排名稳定性 Kendall-τ（跨比例/跨集排名是否洗牌）
- [ ] 结构难度不对称（PS vs FH，难结构 SSL 增益更大？）
- **PASS**：≥1 个规律统计显著(95%CI/Wilcoxon)且可解释
- **FAIL（GRAY 不砍）**：所有规律 CI 宽/不显著 → R9 GRAY，补低比例/更难数据(FUGC)再判，仍弱则降 venue 不硬撑

### Phase 3 — 自适应阈值增量
- [ ] 自适应阈值 vs 固定阈值，跨集跨比例
- **PASS**：低标注/难结构稳定提升(≥多数 setting 正)且统计显著
- **FAIL（GRAY）**：增量≈0 → 诚实写"固定阈值已够"，benchmark 仍成立(增量非论文唯一支柱)

### Phase 4 — 写作+投稿
- [ ] 数字三方对账(csv↔tex↔registry)，verifier 过
- [ ] 图 validate-figures 过
- [ ] 匿名化

## 红线（FAIL 即停，不放行）
- 评估集泄漏（test 混训练）→ 全部结果作废重跑
- 数字 Read 编造 → 红线4
- 半监督方法私改超参凑收敛 → 复现零偏离红线
- spread 薄就夸大成"显著优势" → 跑偏，诚实写

## 可接受最坏结局
落一篇 WACV App / MICCAI workshop / ISBI（benchmark+小增量底线达成）。
