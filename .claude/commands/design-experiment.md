---
name: design-experiment
description: 一键起 planner 设计实验矩阵——把模糊目标/lever 拆成可跑的 run（变量/seed/预期/对齐 ACCEPTANCE 判据/并行依赖）。用于「设计这个消融」「下一步该跑哪些实验」「怎么验证这个 claim」。
---

# /design-experiment — 一键设计实验矩阵

调起 `planner`(opus) 把一个模糊目标拆成可直接交 coder 实现、主线一键跑的实验矩阵。

用法：`/design-experiment <project> [要验证的 claim/lever]`。无参 → 用本窗口认领项目（`.portfolio/locks/*.claim`）+ STORY 当前阶段目标。

## 流程（主线当 lead）

1. **认窗 + 定目标**：确认本窗项目；**读 `.portfolio/registry.json` 取该项目 `home/story/acceptance/log`**（各项目入口命名不同，以 registry 为真源不硬猜）；若没给 claim/lever，读 story + 当前阶段确定本轮要验证的 lever。
2. **起 planner**（`subagent_type: planner`）。冷启动给：项目 home + 要验证的 claim/lever + 从 registry 取的 story/acceptance 路径 + DATA_INVENTORY/现有 config + drift 契约。
3. **收矩阵**：planner 交实验矩阵表（run_id/变量/控制/config/seed/预期/对应判据 + 并行依赖 + 算力预估 + 前置 TODO）。
4. **落盘 + 决断**：矩阵写进项目 LOG 或 `<project>/实验设计_<date>.md`。有前置 TODO（缺超参→researcher / 缺数据）先报；矩阵就绪 → 提议接 `/experiment-cycle` 实现+跑，或单独派 coder。

## 红线
- planner **只设计不写码不跑**；不自创验收阈值（用 ACCEPTANCE 既定）；复现 baseline 零偏离。
- 偏离 STORY / 改判据方向 → 停报拍板，不照描述硬干。
- 涉及官方默认超参查不到 → 标 TODO 派 researcher，不臆想。
