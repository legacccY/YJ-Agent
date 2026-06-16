# /paper-scout — 一键起论文探路战队

一条命令调起标准探路编队（researcher×4 + reviewer），把一篇论文「跑实验之前」的情报 + framing 风险一次性摸清。

用法：`/paper-scout <project>`（如 `nca-jepa` / `iclr`）。无参 → 用本窗口认领的项目（`.portfolio/locks/*.claim`）。

## 流程（我当 lead 执行）

1. **认窗 + 读档**：确认本窗口项目（claim 文件），Read 该项目 STORY（01_STORY / STORY_FRAMEWORK）+ ACCEPTANCE + registry，掌握 claims / 跑偏定义 / 当前阶段。
2. **并行起 4 researcher(sonnet) + 1 reviewer(opus)**（一批发出，互相独立）。重启 CC 后用 `subagent_type: researcher/reviewer`；未重启则 `general-purpose` + `model: sonnet/opus` + 内嵌角色。每个给完整冷启动：项目一句话 + 卖点 + 背景档路径 + 红线（researcher 喂 no-hallucinate；reviewer caveman OFF）+ drift 契约（服务哪 claim/能力）+ 输出格式。
   - **researcher 1 — 竞品版图**：最新 SOTA / 抢牌竞品 / 我们的真空白。
   - **researcher 2 — 官方超参核查**：方法专属超参联网查官方源，对照现 config，标 🟢官方/🟡自定/🔴缺源。
   - **researcher 3 — 理论文献加固**：命题找支撑/对照文献 + 证明严谨度（哪些必须降级 we-sketch）。
   - **researcher 4 — venue 定位**：主线 + 退路各自最佳会场 + 官方 CFP 截稿（查不到标 TODO）。
   - **reviewer — 对抗审稿 + 反跑偏**：扮顶会多角色找致命伤 + 扫 over-claim/跑偏，severity 标注，数字疑点交 verifier 不自决。
3. **综合落盘**：把五方回汇写成 `<project>/05_探路_<date>.md`（带 URL，TODO 诚实标，主线注解区分情报 vs 决策）。
4. **给决断点**：致命级 framing 缺口 → AskUserQuestion 让用户拍；安全修正 → 提议派 writer 落地。

## 红线
- 全程**纯软活**（检索/审稿/写报告）。**不碰训练 / HPC 提交 / 删除**（主线串行 + 训练锁）。
- researcher 事实带引用、查不到标 TODO 绝不臆想；reviewer caveman OFF。
- 报告只情报 + 建议，**不擅自改 STORY/理论文档**——改动等用户拍。
- 数字疑点交 verifier（Bash/Grep 核 csv），researcher/reviewer 不下数字结论。

## 节流
4-5 个 agent 并行但每个紧凑冷启 + caveman 压缩回汇 + effort budget（sonnet 两轮搜不到即标 TODO/升级）。读重活在 sonnet 侧，省主线 context。
