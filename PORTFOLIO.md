# YJ-Agent 科研组合台 — PORTFOLIO（跨论文唯一入口）

> 任何会话开门第一读。多篇顶会顶刊并行的协调根。状态真源 = `.portfolio/registry.json` + `.portfolio/locks/`。
> 最后更新：2026-06-16

---

## 📌 在跑论文

| 项目 | 会场 | Deadline | 状态 | 优先级 | home |
|---|---|---|---|---|---|
| **ICLR** VisiSkin-Agent | ICLR 2027 | 09-22 abs / 09-29 full | 🟢 active：M2 收官→M3 写作 | P1 | `project/` |
| **NCA-JEPA** | TBD→NeurIPS/ICLR | pilot Gate0 ~D2 | 🟡 pilot-ready：Phase0 待放行(HPC) | P2 | `project/meeting/Med-NCA/NCA-JEPA/` |
| **BMVC** QCTS | BMVC 2026 | 已投 05-24 | 🔒 sealed：仅 rebuttal | P9 | `project/meeting/BMVC/` |

未来槽位：HuimaiMed/脉枢（命名见 memory）。新论文 → `/spin-off-paper` 自动登记 registry + 建标准 schema。
- **MedSeg-UQ（医学分割+不确定性，pre-立项调研中）**：选题/文献/理论矩阵见 `project/meeting/MedSeg-UQ/00_选题调研_2026-06-16.md`。主推方向 ★1 Calibration–Dice trade-off 下界（纯顶会向）。待拍板立项。

> **项目规范真源**：新项目立项 / 新阶段开启 / 自主运行边界 / 拍板点清单全在 [`project/PROJECT_LIFECYCLE.md`](project/PROJECT_LIFECYCLE.md)。默认自主一直跑，只在拍板点停。

---

## 🚦 多窗口规则（多终端各跑一篇时）

1. **开窗即认领**：session_start 报当前训练锁 + 他窗认领；写某项目前先认领 `.portfolio/locks/<project>.claim`。
2. **训练全局互斥**：任何本地 `Start-Process` 训练 / HPC `sbatch` 前查 `locks/training.lock`，被占即停（串行红线，跨所有窗口 + 本地 GPU + HPC）。
3. **写作隔离**：各项目写自己的日志 / registry；本 PORTFOLIO.md 只由持 portfolio 写锁的窗口改。
4. 锁机制详见 `.portfolio/README.md`。

---

## 🧑‍🤝‍🧑 Agent 团队 + 模型路由

主线 = Opus 编排（决策 / 写作 / 训练管控，串行高风险项亲自做）。工人 = Sonnet，**卡住 → 升级 Opus**。

| Agent | model | caveman | 何时派 |
|---|---|---|---|
| `researcher` | sonnet | ON | 查文献 / 官方源码 / 超参（带引用） |
| `writer` | opus | **OFF** | 写改 tex 章节（数字先过 verifier） |
| `verifier` | sonnet | ON | 核数字：Bash/Grep 核 csv，禁 Read |
| `reviewer` | opus | **OFF** | 对抗审稿 L19 十角色 + 反跑偏审计 |

训练 / HPC 提交 / 危险删除 **不外包**，永远主线串行。详见 `.claude/agents/`。

---

## 🛡️ 反跑偏底线（全项目通用）

- 进任一项目动手前，按其 `00_README.md` 读档顺序读 STORY + ACCEPTANCE。
- **数字一律 Bash/Grep 核 csv，不信 Read**（曾幻觉编造 csv，险踩红线）。数字入 tex 前过 verifier。
- 复现零偏离 / 超参禁臆想（查不到标 TODO，绝不照搬别库）。
- BMVC 已封印（pre_edit hook 守）。任务与项目 STORY 冲突 → 停下澄清，不照用户描述硬干。
- **写作 caveman 自动关**（tex / 正文 / rebuttal 文字保真）；caveman 仅内部沟通 / 对话。

---

## 📂 标准流水线（按任务类型）

| 任务 | 动作 |
|---|---|
| 新论文 | `/spin-off-paper` |
| 跑实验 | `/loop /run-experiment`（state.json + 训练锁） |
| 查文献/超参 | 派 `researcher`(sonnet) |
| 写章节 | 派 `writer`(opus, caveman off)，数字先 `verifier` |
| 核数字 | 派 `verifier`(sonnet) |
| 出图 | `/validate-figures` + `academic-figure-prompt` |
| 对抗审稿 | 派 `reviewer`(opus) |
| 阶段切换 | `/phase-transition` |
| 投稿前 | `/pre-submit-check`（三方对账） |

> GitHub 日常协同（branch/PR/gh CLI）+ 仓库地图 + 公开主页脱敏红线：见 [`project/HOWTO_GITHUB.md`](project/HOWTO_GITHUB.md)。

---

## 各项目下一步

- **ICLR**：M3 写作起步。读 `project/README.md` → STORY_FRAMEWORK → ACCEPTANCE_CRITERIA → DATA_INVENTORY → PROJECT_LOG。
- **NCA-JEPA**：等用户放行 Phase 0（HPC，~48 GPU·hrs，Gate0-3 决策门）。读 `project/meeting/Med-NCA/NCA-JEPA/00_README.md`。
- **BMVC**：被动等审稿，到则 rebuttal（`meeting/BMVC/rebuttal/`）。

> 详细历史日志各项目 `04_LOG.md` / `PROJECT_LOG.md`。旧根级 WORKLOG 已归档 `project/archive/2026-06_portfolio_reorg/`。
