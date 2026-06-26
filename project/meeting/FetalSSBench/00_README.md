# FetalSSBench — 胎儿/产科超声半监督分割统一 benchmark

> **一句话**：首个跨任务、跨标注比例的胎儿/产科超声半监督分割统一 benchmark（PSFHS+HC18+FUGC），核心发现 = **SSL 增益强结构依赖（高基线易结构可靠无益，跨结构不对称稳健显著）**；附诚实负结果——调好的固定置信阈值已足够，自适应阈值（FreeMatch SAT）不额外加分。
> **定位（2026-06-26 锁定，原双核→单核）**：**benchmark + 结构难度不对称 = 唯一主轴承重**（招1+2，p=7e-8/0.0012 铁实）；自适应阈值 Phase3 实测 GRAY（PSFHS 承重区 ΔdicePS 中位 −0.0008/p=0.42 无显著增量）→ 降为「调好固定阈值已够」**诚实负结果附录**，不当并列贡献（守 R4）。WACV/ACCV benchmark 不需新方法超 SOTA。
> **venue**：ACCV 2026 主会（CORE-B，benchmark+小增量形可接，无需 radical novelty）｜退路 WACV App / MICCAI workshop / ISBI
> **status**：planning（G5 pilot GRAY-PASS，正式立项 2026-06-24）
> **来源**：`/ideate` run-011 候选 A（`project/ideation/runs/2026-06-24_run-011_accv-fetalus-diffsemiseg/`）

## 铁律
- 纯 B 族 benchmark+小增量，**只用公开数据**，复现零偏离，数字一律 Bash/Grep 核 csv 不信 Read
- **评估集不可泄漏**：held-out test 绝不混入训练/无标注池
- 半监督方法用官方实现（SSL4MIS），超参查官方源不臆想
- 对齐导师王水花方向（胎儿超声 CMIS + 半监督 + 扩散/未标注），但不重做她已发

## 读档顺序（新窗口一跳读全）
00_README（本文）→ `01_STORY.md`（核心 Claim + 章节弧 + R-rules）→ `02_ACCEPTANCE.md`（二元验收 + lever + 阈值）→ `DATA_INVENTORY.md`（数据细目）→ `04_LOG.md` 最新 entry →（动手）`PLAN/MASTER_PLAN.md`（**阶段计划总入口**）+ `src/` + pilot `project/meeting/_run011_pilot/`

## 📋 阶段计划文件夹 `PLAN/`（怎么做——2026-06-25 建）
> 既有 4 文件答「是什么/验收什么」，`PLAN/` 答「每阶段跑哪些 run/写哪些节/每步 DoD/算力」，验收阈值引用 `02_ACCEPTANCE` 不复制。仿 BMVC 多文档协同 + Lever 分解。
- `PLAN/MASTER_PLAN.md` — 顶层导航：4 phase 一览 + 依赖 DAG + 80% 信心总账指针
- `PLAN/PHASE_1_BENCHMARK.md` / `PHASE_2_REGULARITIES.md` — 已 PASS 回填存档
- `PLAN/PHASE_3_ADAPTIVE_THRESHOLD.md` — 自适应阈值核心贡献（待做，最细）
- `PLAN/PHASE_4_WRITING_SUBMISSION.md` — 写作弧 + 投稿 + 双 venue 回退
- `PLAN/LEVER_MATRIX.md` — **80% 中稿信心总账（12 lever）**
- `PLAN/STORY_REFINEMENT.md` — 规律3 裂缝加固（改 STORY = 拍板点）
- `PLAN/DATA_FUGC_ACQUISITION.md` — FUGC 取数作战（Zenodo 16893174 Open 可直下）
- `reference/ADAPTIVE_THRESHOLD_hparams.md` — FreeMatch/FlexMatch 官方公式真源

## 核心贡献（2026-06-26 定位锁定：单核 + 诚实负附录）
1. **【主轴·承重】Benchmark + 结构难度不对称**：3 数据集 × 5 标注比例(1/2/5/10/20%) × 5 半监督 baseline 统一评测；标注效率曲线 + 排名稳定性(无普适最优) + **SSL 增益强结构依赖**（高基线易结构 FH/head 可靠无益/受损 p=7e-8，跨结构差异稳健 p=0.0012；PS 难=低基线+极端小前景 2.5% 双因叠加）。
2. **【附录·诚实负】自适应置信阈值**：Phase3 实测 FreeMatch SAT vs 最优固定 τ∈{.7,.8,.9}，PSFHS 承重难低区 **ΔdicePS 中位 −0.0008/Wilcoxon p=0.42/Holm 全不显著 = GRAY**。诚实结论「调好的固定阈值已够，自适应不额外加分」——预注册正负均报，**不当并列贡献**（守 R4，避免拿 null 当核心）。本身是有信息量的负发现（自适应阈值机制在胸超分割不优于调好的固定阈值）。

## G5 pilot 已验（GRAY-PASS）
PSFHS 上 Sup vs MeanTeacher 曲线干净单调、MT 增益随标注比例单调递减、增益集中难结构 PS。**债=PSFHS 监督 baseline 已强 headroom 薄 → 设计须加低比例(1/2%)+更难数据(FUGC)+多 baseline**。详见 `project/meeting/_run011_pilot/G5_VERDICT.md`。
