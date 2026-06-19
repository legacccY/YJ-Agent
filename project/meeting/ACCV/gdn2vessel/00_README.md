# gdn2vessel — ACCV 2026 立项入口

**一句话**：用 Gated DeltaNet-2（NVIDIA 2026-05 线性注意力，解耦 erase/write 门 + delta-rule 关联记忆，零视觉版）做连通性保持的血管/管状结构分割，headline = **跨遮挡/低对比断点的血管续连（reconnection / re-identification）**。

- 导师：王水花（XJTLU，医学影像+CV+可解释 AI）
- venue：ACCV 2026（截稿约 2026-07-05 待官网核实，双盲，14 页 LNCS，OpenReview，~32% 录用，CCF C/CORE B）
- 完整立项 plan（已批准）：`C:\Users\yj200\.claude\plans\d-yj-agent-project-meeting-accv-2024-acc-keen-pony.md`
- 参考 ACCV2024 论文：`project/meeting/ACCV/2024/`

## 📕 本项目铁律（用户 2026-06-20 拍板，最高优先）

> **遇到计划外的任何问题，一律先来问用户怎么办，千万不能盲跑。**

适用：依赖装失败、数据集源失效/需账号、driver/CUDA 不匹配、kernel 编不通、pilot 异常、任何与 plan 不符的岔路。诊断到根因即停，给选项请用户拍，**不擅自重试/换方案**。
（已有教训：cu128→cu126 的 driver 退路当时该先问；FLA wheel 缺失、kaggle.json 传 HPC 被拦——后两个已按铁律停下问。）

## 读档顺序

00_README（本文）→ 批准 plan → PROJECT_LOG.md 最新 entry → STORY/ACCEPTANCE（待建）。

## 三创新承重分配（skeptic 收敛）

- **C 独头承重**：delta-rule 矩阵态当血管"身份记忆"，遮挡后用 key 查回 value 续上。消融=有 C / 无 C 干净对照。
- **B 作 C 的机制**：解耦擦/写门，vesselness 用**可微 Frangi 层（input-derived）**调制，绝不用分割结果/GT（破鸡生蛋+防泄漏）。
- **A 降工程**：固定血管友好输入重排，走标准 GDN-2 kernel（不重写 kernel、不当 claim，避撞 TopoMamba/TA-Mamba）。
- **杀手锏实验**：自造人工断点/遮挡 benchmark + 续连率指标（矩阵第一优先）。
- **容量约束**：GDN-2 放 encoder 降采样深层，flatten 序列 ≤~1K（长序列检索会衰减）。
