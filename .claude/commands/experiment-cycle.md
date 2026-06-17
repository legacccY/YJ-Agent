---
name: experiment-cycle
description: 一键编排整条实验闭环——planner 设计矩阵 → coder 并行实现各 config → 🛑停在拍板点等放行 → 主线跑训练 → analyst 解读 → verifier 核数。把「调研后到写论文前」的中段全自动串起，人只在「跑训练」拍板点介入。用于「跑一轮完整实验」「设计并实现这个消融」「推进下一阶段实验」。
---

# /experiment-cycle — 一键编排实验闭环（设计→写码→🛑跑→分析→核数）

最强编排 skill。把科研闭环中段的六棒（设计→🩺红队→写码→🛑跑→分析→核数）自动串起，主线当 lead 顺序推进，**只在「跑训练」拍板点停下等放行**。

用法：`/experiment-cycle <project> [要验证的 claim/lever]`。无参 → 用本窗认领项目 + STORY 当前阶段目标。

## 流程（主线当 lead，顺序推进）

### Stage 1 — 设计（planner）
认窗 + **读 `.portfolio/registry.json` 取 `home/story/acceptance/log`**（各项目命名不同，以 registry 为真源不硬猜）→ 起 `planner`(opus) 出实验矩阵（run/变量/seed/预期/对齐判据/并行依赖/算力预估）。有前置 TODO（缺超参/数据）→ 先派 `researcher` 补或停报。矩阵落盘项目 LOG。

### Stage 1.5 — 红队设计（skeptic）
矩阵落盘后、写码前，派 `skeptic`(opus) 攻设计：混杂变量 / baseline 选错 / claim 与所测不对齐 / 无效消融白烧算力。**skeptic 卡不住流程**——severity-gated，**致命伤=0 → 直接进 Stage 2**；有 🔴 致命 → 回 planner 修该 run 或停报拍板（带 skeptic 给的出路）。日常小迭代/已红队过的设计可跳过本棒。

### Stage 2 — 实现（coder，可并行）
据矩阵，派 `coder`(sonnet) 实现各 run 的脚本/config。**多个无文件冲突的 config → 一批多 coder 并行**（每个给完整冷启：项目+该 run 规格+Windows 规范+drift 契约）。coder 自测 `py_compile`/pytest，交「就绪」回执。

### Stage 3 — 🛑 拍板点（停！）
所有代码就绪 + config 验通后**停下报**：
```
[experiment-cycle] 就绪：<N> 个 run，脚本 X，config Y，预估 Z GPU·h。
说『跑』即启（主线持训练锁串行 /loop /run-experiment）。
```
**绝不自行启动训练**（串行红线 + 全局互斥 + 真金算力）。等用户放行。

### Stage 4 — 跑（主线亲自，放行后）
用户放行 → 主线持 `training.lock` → `/loop /run-experiment <script> <config>`，state.json 自动监控。多 run 串行（训练互斥红线），逐个跑完。

### Stage 5 — 分析（analyst）
训练 `status:"done"` → 起 `analyst`(sonnet) 读结果 csv/state.json 出趋势/对比/图/异常/建议，对判据标 ✅❌。

### Stage 6 — 核数 + 收尾（verifier）
要写进 paper 的关键数字 → 派 `verifier` 三方对账。一轮小结写进 LOG（`/checkpoint`），报：达没达本 lever 判据 + 建议下一轮 / 进入写作。

## 红线（贯穿全程）
- **训练启停只在 Stage 3/4 由主线串行做**，coder/planner/analyst 全程不碰训练/HPC/删除。
- planner 不自创阈值；coder 复现零偏离 + 超参禁臆想；analyst 不粉饰、禁 Read csv 凭印象；数字疑点交 verifier。
- 任一棒发现偏离 STORY / 改判据方向 → 停报拍板，不照描述硬干。

## 节流
每 agent 紧凑冷启 + caveman 压缩回汇（planner OFF）+ effort budget。读重活交 sonnet，省主线 context。Stage 2 能并行就并行，别串行浪费。
