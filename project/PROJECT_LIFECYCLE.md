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

**Step 0（拍板）**：方向 / 目标会议 / 核心 RQ 由用户定。我可先派 researcher 调研可投性 + 竞品，给方案，但立项点等用户拍。

立项拍板后，全自主执行：

1. **建标准 schema**：跑 `/spin-off-paper`（子论文）或从 `project/templates/` 复制骨架。标准目录含：
   - 入口 `README.md` / `STORY_FRAMEWORK.md`（核心主张 + R-rules 防御写法 + § 锁定）
   - `ACCEPTANCE_CRITERIA.md`（二元 PASS/FAIL 验收，lever 分解 + 命中率）
   - `PROJECT_LOG.md` / `04_LOG.md`（时间倒序单一日志真源）
   - `DATA_INVENTORY.md`（本项目数据细目，路径指向共享真源）
2. **登记 registry**：写入 `.portfolio/registry.json`（name/venue/deadline/status/priority/home/story/log）。
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

## 速查

| 场景 | 动作 |
|---|---|
| 起新论文 | 拍板立项 → `/spin-off-paper` → 登 registry+datasets → claim |
| 开新阶段 | `/stage-gate`（过上阶段）→ 自动开下阶段+预填 criteria 待确认 |
| 阶段内推进 | 自主跑,完一块记 LOG/`/checkpoint`,遇拍板点停 |
| 大阶段验收 | `/stage-gate <project>`（opus 严判,不达不放行） |
| 该不该停 | 不可逆/花钱/改战略/对外 → 拍板;否则跑 |
