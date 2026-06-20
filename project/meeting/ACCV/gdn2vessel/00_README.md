# gdn2vessel — ACCV 2026 立项入口

**一句话**：用 Gated DeltaNet-2（NVIDIA 2026-05 线性注意力，解耦 erase/write 门 + delta-rule 关联记忆，零视觉版）做连通性保持的血管/管状结构分割，headline = **跨遮挡/低对比断点的空间续连（reconnection）+ 同根血管 re-identification**。

- 导师：王水花（XJTLU，医学影像+CV+可解释 AI）
- venue：ACCV 2026（截稿 2026-07-05，双盲，14 页 LNCS，OpenReview，~32% 录用，CCF C/CORE B）作**保底**；计划按**顶会亮度（CVPR/ICCV/MICCAI）**标准建，**不设周期上限**。
- 完整批准 plan（GDN-2 选型链）：`C:\Users\yj200\.claude\plans\d-yj-agent-project-meeting-accv-2024-acc-keen-pony.md`
- 计划文件夹搭建 plan：`C:\Users\yj200\.claude\plans\eager-hugging-toucan.md`

## 📕 本项目铁律（用户 2026-06-20 拍板，最高优先）

> **遇到计划外的任何问题，一律先来问用户怎么办，千万不能盲跑。**

适用：依赖装失败、数据集源失效/需账号、driver/CUDA 不匹配、kernel 编不通、pilot 异常、任何与 plan 不符的岔路。诊断到根因即停，给选项请用户拍，**不擅自重试/换方案**。

## 📖 读档顺序（每次进项目固定）

1. **本文（00_README）** — 立项一句话 + 铁律 + 双核心贡献
2. **[`PLAN/MASTER_PLAN.md`](PLAN/MASTER_PLAN.md)** — ★总计划（阶段总览 + 指针 + 全局红线 + 超量/亮度原则）
3. **[`STORY_FRAMEWORK.md`](STORY_FRAMEWORK.md)** — ★反跑偏主文（双核心 Claim + 章节弧 + 防御写法 R-rules）
4. **[`ACCEPTANCE_CRITERIA.md`](ACCEPTANCE_CRITERIA.md)** — ★顶会亮度验收（lever 分解 + 每阶段硬阈值 + 红线）
5. **[`DATA_INVENTORY.md`](DATA_INVENTORY.md)** — ★数据/脚本/结果/baseline 全景
6. **[`PROJECT_LOG.md`](PROJECT_LOG.md)** 最新 entry — 当前进度
7. 进具体阶段动手 → 读对应 `PLAN/PHASE_x_*.md`

**调研参考（reference/，researcher 核源落档）**：
- [`reference/SOTA_NUMBERS.md`](reference/SOTA_NUMBERS.md) — 视网膜血管 SOTA 数字表（核源版，含 split 陷阱 + RV-GAN 禁用）
- [`reference/RELATED_WORK_MATERIAL.md`](reference/RELATED_WORK_MATERIAL.md) — §2 四块文献 + GDKVM R3 模板核准 + creatis 协议精读（两修正）

## 🎯 双硬核贡献（skeptic 收敛 + 2026-06-20 调研升级）

- **核心 1 = C（独头承重）**：delta-rule 矩阵态当血管「身份记忆」，遮挡后用 key 查回 value 续上。消融=有 C / 无 C 干净对照。
- **核心 2 = 空间 re-ID 机制**（与 GDKVM 时序版的硬区分点）：把断点两侧「是否同一条血管」做成显式 re-identification，自定义 re-ID 率指标。
- **机制 = B（作 C 的机制，非独立 claim）**：解耦擦/写门，vesselness 用**可微 Frangi 层（input-derived）**调制，绝不用分割结果/GT（破鸡生蛋 + 防泄漏）。
- **工程降声张 = A**：固定血管友好输入重排走标准 GDN-2 kernel（不重写 kernel、**scan 不当贡献**，避撞 Serp-Mamba/TopoMamba/TA-Mamba）。
- **杀手锏实验**：自造人工断点/遮挡 benchmark（合成协议对齐 creatis plug-and-play arXiv 2404.10506）+ 续连率/re-ID 率指标（矩阵第一优先）。
- **容量约束**：GDN-2 放 encoder 降采样深层，flatten 序列 ≤~1K（长序列检索会衰减）。

## ⚠️ 撞车风险（2026-06-20 调研，必须正面处理）

- **GDKVM（ICCV2025, arXiv 2512.10252）** = GatedDeltaNet+KV memory+分割，但**跨帧时序心超视频**，我们是**单图内空间**。related work 必须硬区分（时序 vs 空间 + GDN-2 vs 早期 GatedDeltaNet），并以核心 2（空间 re-ID）拉开差距。
- GDN-2 视觉/分割**零应用 = 真空白**；2D 眼底「人工断点+记忆续连」benchmark 也是真空白。
