---
name: analyze-results
description: 一键起 analyst 解读实验结果——读 state.json + 结果 csv，算趋势/消融对比/出图/找异常/建议下一步，对照 ACCEPTANCE 判据标 ✅❌。用于「分析这轮结果」「跑完看看说明什么」「画指标曲线」。
---

# /analyze-results — 一键解读实验结果

调起 `analyst`(sonnet) 把跑完的一堆 csv/state.json 变成洞察 + 图 + 下一步建议。训练 `status:"done"` 后 `results_ready.js` hook 会提醒跑此命令。

用法：`/analyze-results <project> [run_name 或 csv 路径]`。无参 → 用本窗项目最新 `log/experiment_state.json` 指向的结果。

## 流程（主线当 lead）

1. **认窗 + 定数据**：确认本窗项目；**读 `.portfolio/registry.json` 取 `home/acceptance`**（判据路径各项目不同，以 registry 为真源）；定位结果——读 `log/experiment_state.json` 取 run_name/checkpoint/结果 csv 路径，或用户指定 csv。
2. **起 analyst**（`subagent_type: analyst`）。冷启动给：项目 home + 结果 csv/state.json 路径 + 从 registry 取的 acceptance 路径（对应判据）+ drift 契约。
3. **收报告**：analyst 交趋势/对比表 + 关键发现 + 异常 + 建议下一步 + 生成图路径（数字带 csv 来源）。
4. **落盘 + 接力**：把分析写进项目 LOG。要写进 paper 的数字 → 提议派 `verifier` 三方对账后再交 writer；发现需补的实验 → 提议接 `/design-experiment` 或 `/experiment-cycle`。

## 红线
- analyst **趋势/数字一律 Bash+python 算，禁 Read csv 凭印象**（反幻觉红线）。
- **不粉饰**：结果偏离 STORY/预期如实报（诚实回退红线），不挑好看的卖。
- 不下「数字错」终判（交 verifier）；不改论文/代码/config。
- 出图落项目 `results/`/`figures/`，报告给路径。
