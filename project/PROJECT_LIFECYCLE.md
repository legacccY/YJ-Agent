# 项目生命周期 SOP — 新项目 / 新阶段规范开启 + 自主运行边界

组合台所有论文项目共用。**新项目立项、新阶段开启、日常推进、拍板点**的唯一流程真源。CLAUDE.md 指向此文件。

---

## 🤖 自主运行模式（默认）

**默认一直跑**：不达拍板点就别停下等指令——做完一个子任务自动推进下一个明确子任务，做完记 LOG，继续。空等 / 反复征求同意 = 反模式。

### 自主区（直接做 + 落档 + 继续，无须问）

写改 tex/正文/bib、核数字（verifier）、对抗审稿（reviewer）、补实验代码、调研文献/官方源、出图、补指针、写 LOG / `/checkpoint`、修小 bug、跑 pytest、阶段内推进到下一个已明确的子任务、stage-gate PASS 后自动开下阶段（预填 criteria 待确认）。

派 sonnet 工人并行（无文件冲突的独立子任务）也属自主，无须每次征求同意。

### 🛑 拍板点（必须停下报用户，等明确放行才动）

| 拍板点 | 为什么 | 我先做到哪一步 |
|---|---|---|
| **启动训练 / HPC 提交 / 上传** | 花真金算力+时间+全局互斥（串行红线） | config 验通 + 持训练锁就绪 → 停，报「就绪,说『跑』即启」 |
| **新项目立项**（方向/目标会议/核心 RQ） | 战略，定错全盘偏 | 可先调研可投性 → 停,给方案让你定 |
| **投稿 / 对外发布 / force push 改写远端历史** | 不可逆、对外 | 准备好产物 → 停,等你拍 |
| **偏离 STORY / 改 ACCEPTANCE 阈值 / 命中率回退方向** | 动项目根基 | 停,说清冲突 + 选项,不照描述硬干 |
| **stage-gate 判 FAIL 后是否放行** | 严闸门,放水=失守 | 默认不放行,写诚实回退,等你裁 |
| **危险删除 / 覆写封印文件** | 不可逆（hook 也会拦） | 停,先报要删什么 + 为何 |
| **大笔 API / 算力花费** | 花钱 | 停,报预估成本 |
| **真实歧义**（任务与现有事实/STORY 冲突，无合理默认） | 防跑偏 | 停,问清 |

> 判定法：动作**不可逆 / 花真金资源 / 改项目战略根基 / 对外** → 拍板。否则自主跑。拿不准偏向「先把可逆部分做完，到不可逆处停下报」。

### 阶段推进（stage-gate PASS 后，自动 + 待确认）

PASS → 自动：①旧阶段归档 ②从 STORY/ACCEPTANCE 预填下阶段 success criteria 草稿 + 初始化 active 文件 ③一句话报「已开 Phase N+1，criteria 草稿见 X，确认/改」。**不空等**，但 criteria 你过目。FAIL → 见拍板点。

---

## 🆕 新项目开启 SOP

**Step −1（强烈推荐）— 走选题工业流水线 `/ideate`**：组合台 4 个项目「最初大胆 claim 全死、被迫降格」的病根=立项靠一次性手感、没批量、没工具验证撞车、没立项前廉价证伪。**新方向不要单点拍脑袋立**，先跑 `/ideate "<种子>"`：G0 宪章定约束 → G1 批量产 ~100 候选 → G2 工具撞车硬筛 → G3 加权+Swiss 排序 → G4 skeptic 红队+pre-mortem → **G5 <1GPU·h 杀手锏立项前证伪** → G6 幸存 1-3 个带双venue+书面kill criteria 呈拍板。体系全档 `project/ideation/00_README.md`。

**Step 0（拍板）**：方向 / 目标会议 / 核心 RQ 由用户定。走完 `/ideate` 的候选已带完整证据轨迹直接拍；若跳过流水线直接给方向，至少派 researcher 调研可投性 + 竞品 → **G-theory：派 `/theory-audit <p> kickoff`**（theorist 半形式化推导核心假设链+回报预测，三层防线防幻觉，产**冻结假设链** `reference/THEORY_LEDGER.md`，防 NCA-JEPA「100×」/SelInf deflation 恒等式式理论塌缩）→ **再派 `skeptic` 红队前提**（核心假设可行性 / 撞车 / 理论会不会塌，防 MedSeg-UQ 式立项后才塌缩）。theorist 推导 + skeptic 裁决随立项材料一起呈用户拍板；但立项点等用户拍。

立项拍板后，全自主执行：

1. **建标准 schema**：跑 `/spin-off-paper`（子论文）或从 `project/templates/` 复制骨架。标准目录含：
   - 入口 `README.md` / `STORY_FRAMEWORK.md`（核心主张 + R-rules 防御写法 + § 锁定）
   - `ACCEPTANCE_CRITERIA.md`（二元 PASS/FAIL 验收，lever 分解 + 命中率）
   - `PROJECT_LOG.md` / `04_LOG.md`（时间倒序单一日志真源）
   - `DATA_INVENTORY.md`（本项目数据细目，路径指向共享真源）
2. **登记双索引**（一个动作两处都写，缺一即断链 — 2026-06-20 gdn2vessel 踩坑：只登 registry 没登 CLAUDE.md，新窗口选它读不到阶段档）：
   - a. `.portfolio/registry.json` 的 `projects`（name/venue/deadline/status/priority/home/story/acceptance/log）— 给 SessionStart hook 报进度用。
   - b. **`CLAUDE.md`「进具体某项目动手前」入口清单补一行** — 给新窗口读档用，格式：`- **<key> / <Name>**（任务含 <关键词>；status=<x>）：<home>/00_README.md → 01_STORY → 02_ACCEPTANCE → 04_LOG 最新 entry`。**registry 报进度 ≠ 报读档；读档指令真源是这张清单，登 registry 时必同步登它。**
   - c. 跑 `python tools/check_registry_pointers.py` 自检：registry 与 CLAUDE.md 入口清单一一对齐才算建档完成。
3. **关联数据集**：项目用到的数据集进 `.portfolio/datasets.json`（本地+HPC+source+状态），脚本只引此真源，不硬编码。
4. **认领**：写 `.portfolio/locks/<project>.claim`。
5. **首条 LOG**：记立项决策（方向/会议/RQ/边界）。
6. 报一句话立项完成 + 第一阶段目标，进入自主推进。

---

## 📐 新阶段开启 SOP

阶段 = STORY 里一段有明确 success criteria 的工作（如 M2 实验收官 → M3 写作）。

1. **gate 前置**：上一阶段收口 → `/stage-gate <project>`（verifier 核数字 → opus reviewer 对 ACCEPTANCE 严判）。FAIL 不进。
2. **PASS → 自动开**（见上「阶段推进」）：归档旧阶段、预填新 criteria 草稿、初始化 active 文件、报用户确认。
3. **criteria 确认后**：自主推进，按自主区规则一直跑，遇拍板点停。
4. 阶段内每完成一块 → LOG 追加 / `/checkpoint`（hook 会在改多没记时提醒）。

---

## 🔗 关联机制（已自动化）

- `drift_guard`（每条动手指令）：注入服务哪 §/lever + 四红线 + 数据集真源指针。
- `new_file_pointer`（新建源文件）：没登指针即提醒。
- `stage_progress`（收尾）：改多没写 LOG 提醒 `/checkpoint`，大阶段提醒 `/stage-gate`。
- `training_lock`（训练前）：全局互斥；拍板放行后持锁启动。

---

## 🔬 科研闭环标准流水线（每条腿 → agent → 交接点）

阶段内推进按这条流水线走，**每条腿派对应 agent，别主线串行硬扛**。九角色覆盖全闭环：

```
调研        → researcher      带引用结论（文献/官方超参/SOTA）
  ↓ 交接：结论 + 官方超参 → planner 用作设计输入
设计实验    → planner         实验矩阵（run/变量/seed/预期/对齐 ACCEPTANCE 判据/可并行）
  ↓ 交接：矩阵表 → skeptic 红队（执行前堵雷）
🩺红队设计  → skeptic         攻混杂/baseline/claim-测不对齐/无效消融；0 致命即过，有 🔴 回 planner 修。不卡流程
  ↓ 交接：过红队的矩阵 → coder 按表逐 run 实现
写实验代码  → coder           训练脚本/model/loss/预处理/画图，自测 pytest，标「就绪」
  ↓ 交接：就绪代码 + config → 主线（拍板点，不外包）
🛑 跑训练   → 主线 /loop /run-experiment   持训练锁串行，state.json 自动监控
  ↓ 交接：state.json status=done + 结果 csv → analyst 解读
分析结果    → analyst         趋势/消融对比/出图/异常/建议下一步，对判据标 ✅❌
  ↓ 交接：要写进 paper 的数字 → verifier 先核
核数字      → verifier        三方对账 registry↔STORY↔tex，Bash 核 csv 禁 Read
  ↓ 交接：已核数字 → writer 只用已核值
写论文      → writer          写/改 §X，遵守 R-rules 防御写法
  ↓ 交接：草稿 → reviewer 攻
审稿/反跑偏 → reviewer        十角色对抗 + STORY 审计，severity 标注
  ↓
大阶段收口  → /stage-gate     verifier + opus reviewer 严判 PASS/FAIL，不达不放行

横切：optimizer（自优化协作系统） · drift_guard/training_lock/stage_progress/use_the_squad/coder_handoff_gate/results_ready（hook 自动护栏）
```

**一键编排 skill**（不用手记每棒派谁）：
- `/paper-scout` —— 调研腿（researcher 扇出）。
- `/design-experiment <project>` —— 设计腿（planner）。
- `/experiment-cycle <project>` —— **设计→写码→🛑跑→分析→核数** 整条中段自动串，人只在跑训练拍板点介入。
- `/analyze-results <project>` —— 分析腿（analyst），训练 done 后 `results_ready` hook 会提醒跑。

---

## 速查

| 场景 | 动作 |
|---|---|
| 找新方向 | `/ideate "<种子>"`（G0-G6 选题流水线，立项前批量筛+证伪，全档 `project/ideation/`）|
| 理论支撑/证伪 | `/theory-audit <project> [kickoff\|diagnose\|selfcheck]`（三层防线：theorist 推导→skeptic 证伪→verifier 核数。立项证可行性+预测回报 / 失败从理论侧三分流归因 / 推导自检。落冻结假设链 `reference/THEORY_LEDGER.md`，专治理论塌缩）|
| 起新论文 | （流水线 G6 幸存后）拍板立项 → `/spin-off-paper` → 登 registry+datasets → claim |
| 开新阶段 | `/stage-gate`（过上阶段）→ 自动开下阶段+预填 criteria 待确认 |
| 阶段内推进 | 自主跑,完一块记 LOG/`/checkpoint`,遇拍板点停 |
| 大阶段验收 | `/stage-gate <project>`（opus 严判,不达不放行） |
| 该不该停 | 不可逆/花钱/改战略/对外 → 拍板;否则跑 |
