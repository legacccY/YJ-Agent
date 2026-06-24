# FetalSSBench — 胎儿/产科超声半监督分割统一 benchmark

> **一句话**：首个跨任务、跨标注比例的胎儿/产科超声半监督分割统一 benchmark（PSFHS+HC18+FUGC），配自适应置信阈值小增量 + 结构难度不对称分析。
> **venue**：ACCV 2026 主会（CORE-B，benchmark+小增量形可接，无需 radical novelty）｜退路 WACV App / MICCAI workshop / ISBI
> **status**：planning（G5 pilot GRAY-PASS，正式立项 2026-06-24）
> **来源**：`/ideate` run-011 候选 A（`project/ideation/runs/2026-06-24_run-011_accv-fetalus-diffsemiseg/`）

## 铁律
- 纯 B 族 benchmark+小增量，**只用公开数据**，复现零偏离，数字一律 Bash/Grep 核 csv 不信 Read
- **评估集不可泄漏**：held-out test 绝不混入训练/无标注池
- 半监督方法用官方实现（SSL4MIS），超参查官方源不臆想
- 对齐导师王水花方向（胎儿超声 CMIS + 半监督 + 扩散/未标注），但不重做她已发

## 读档顺序（新窗口一跳读全）
00_README（本文）→ `01_STORY.md`（核心 Claim + 章节弧 + R-rules）→ `02_ACCEPTANCE.md`（二元验收 + lever + 阈值）→ `DATA_INVENTORY.md`（数据细目）→ `04_LOG.md` 最新 entry →（动手）`src/` + pilot `project/meeting/_run011_pilot/`

## 双核心贡献
1. **Benchmark**：3 数据集 × 5 标注比例(1/2/5/10/20%) × 5 半监督 baseline 统一评测；标注效率曲线 + 排名稳定性 + 结构难度不对称(PS 难/FH 易)。
2. **小增量**：自适应置信阈值（随训练进展/伪标签质量动态调阈），证其在低标注区稳定提升。

## G5 pilot 已验（GRAY-PASS）
PSFHS 上 Sup vs MeanTeacher 曲线干净单调、MT 增益随标注比例单调递减、增益集中难结构 PS。**债=PSFHS 监督 baseline 已强 headroom 薄 → 设计须加低比例(1/2%)+更难数据(FUGC)+多 baseline**。详见 `project/meeting/_run011_pilot/G5_VERDICT.md`。
