# MedAD-FailMap — 项目入口

> 重建式/无监督医学异常检测（AD）的**失败何时可预测**。Capability/analysis paper，不刷 SOTA。
> 立项日：2026-06-16。来源：MedSeg-UQ 塌缩后大部队探路（`project/meeting/方向探路_2026-06-16.md`）。

## 一句话

医学影像里大家用「重建误差」当异常信号，但它**何时会失效没人能预测**。本文把失败系统刻画成 anomaly 属性（病灶大小/对比度/纹理/位置 + 正常集多样性）的**可外推函数**——画出 failure phase diagram，并给「给一张图 predict 该方法靠不靠谱」的 per-image 可靠性判据。

## 读档顺序（每次进项目先读）

1. `00_README.md`（本文）— 入口 + 一句话
2. `01_STORY.md` — 核心 RQ + 三大贡献 + 与 incumbent 的边界 + 反跑偏红线 + 审稿人预对峙
3. `02_ACCEPTANCE.md` — 验收标准 + Gate 定义（capability paper 判据，非刷分）
4. `03_phase0_plan.md` — Phase 0 可行性预检设计（三道证伪闸 PC-A/C/B + Gate 0 决策表）
5. `04_LOG.md` 最新 entry — 当前阶段
6. 数据真源：`.portfolio/datasets.json`（MedIAnomaly 7 集 + 本地复用）

## 当前状态

**planning（立项当天）**。下一步 = Phase 0 可行性预检（搭最小重建 AD pipeline + 协变量分层 sanity）。**跑实验是拍板点 + 持训练锁**。

## 红线（继承 MedSeg-UQ 血泪）

- **别打成「证伪三假设」**：那是 incumbent（HKUST Cai 组 AE4AD）的地盘，会被判 incremental。主轴永远是**协变量失败边界 + 可预测性**，三假设只是分析工具。
- 数字一律 Bash/Grep 核 csv 不信 Read；超参查官方源查不到标 TODO；复现零偏离。
- 理论/命题**先 reviewer 裁再落「已证」**（MedSeg-UQ 自验通过就写已成，连塌三轮）。
