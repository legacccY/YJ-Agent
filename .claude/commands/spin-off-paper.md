# spin-off-paper

从主项目剥离子论文的流程。识别到可独立投稿的发现时运行。

## 触发场景

用户说"从主项目拆一篇文章"、"拆出子论文"、"单独投 {会议}"、"BMVC/EMNLP/ECCV 单独投"。

## 执行步骤

### Step 1：确认子论文核心要素（先问再做）

依次向用户确认：
1. **核心主张（RQ）**：这篇文章的核心贡献是什么？（一句话）
2. **与主论文的边界**：哪些内容是子论文独有的，哪些会和主论文重叠？重叠 > 30% 需要警告。
3. **目标会议/期刊**：{名称}，页数限制，截止日期
4. **数据需求**：需要哪些实验？主项目的哪些实验可以复用？

将回答写入 `papers/sub_{topic}/INFO.md`。

### Step 2：检查可复用实验

读取 `./experiments/registry.json`，筛选 tags 或 note 与子论文相关的 run：
- 列出可直接引用的 run（格式：`run_id | key_metric | paper_reference`）
- 列出需要新增的实验（格式：`实验名称 | 预计时间 | 优先级`）

如果需要新实验，检查 `experiments/state.json`：
- 如果 status = running：警告 GPU 冲突，新实验须排队
- 如果 status != running：可立即规划

### Step 3：创建项目目录结构（对齐组合台真实 schema）

新项目一律建在 `project/meeting/<Name>/`，用标准 00_README schema（与 gdn2vessel/FMReg/SelInfBench 等一致）：

```
project/meeting/<Name>/
├── 00_README.md                # ★入口：一句话 + 铁律 + 读档顺序（自带）+ 双核心贡献
├── 01_STORY.md                 # 反跑偏主文：核心 Claim + 章节弧 + 防御写法 R-rules
├── 02_ACCEPTANCE.md            # 二元 PASS/FAIL 验收：lever 分解 + 每阶段硬阈值 + 红线
├── 04_LOG.md                   # 时间倒序单一日志真源（首条 = 立项决策）
├── DATA_INVENTORY.md           # 本项目数据细目，路径只指向 .portfolio/datasets.json 真源
├── PLAN/                       # （可选）分阶段计划 MASTER_PLAN + PHASE_x
├── figures/                    # 独立图表目录（不共享主论文路径）
└── src/ + tests/               # 实验代码 + pytest
```

复制 `project/templates/` 骨架起步；`00_README.md` 必须自带「读档顺序」段（00_README → 01_STORY → 02_ACCEPTANCE → DATA_INVENTORY → 04_LOG → 阶段 PLAN），新窗口靠它一跳读全。

**关键原则**：所有文件独立存储，不用软链接指向主论文目录；数字/数据集只引共享真源（`.portfolio/registry.json` / `.portfolio/datasets.json`），不硬编码、不软链。

### Step 4：初始化 submission_state.json

```json
{
  "paper": "{title}",
  "venue": "{会议}",
  "deadline": "{YYYY-MM-DD}",
  "page_limit": {N},
  "status": "planning",
  "sections_done": [],
  "sections_pending": ["intro", "related", "method", "experiments", "conclusion"],
  "figures_done": [],
  "figures_pending": ["fig1", "fig2", "fig3"],
  "experiments_reused": ["{run_id_1}", "{run_id_2}"],
  "experiments_needed": ["{实验描述}"],
  "last_updated": "{today}"
}
```

### Step 5：设置 pre-commit 数字一致性规则

如果子论文引用了主论文已有的实验数字（run_id），在 `INFO.md` 中记录：
```
## Shared Data Points（与主论文共享的实验数据）
- Table 1 Row 2: run_id={timestamp}，主论文 Table 3 Row 1 同一数字
  → 如主论文重跑此实验，子论文 Table 1 Row 2 必须同步更新
```

### Step 6：输出执行 Checklist

```
子论文剥离完成，后续操作 Checklist：

立项：
[x] INFO.md 已创建（核心主张、边界、目标会议）
[x] 目录结构已创建
[x] submission_state.json 已初始化

实验：
[ ] 可复用实验已在 registry.json 中标注 paper_reference
[ ] 需要新增的实验已规划（见 INFO.md）
[ ] 新实验 run 完成后更新 submission_state.json

写作：
[ ] main.tex 初始化（从模板或会议官方模板）
[ ] gen_figures.py 从主论文复制并独立化
[ ] references.bib 建立（不继承主论文引用）

投稿前：
[ ] 运行 /validate-figures 验证所有图表
[ ] 运行 /pre-submit-check 检查数字一致性
[ ] 与主论文内容重叠度 < 30% 确认
[ ] 匿名化处理（代码链接、自引、致谢）
```

### Step 7：登记组合台真源（强制，对齐 PROJECT_LIFECYCLE）

子论文也是组合台一员，必须登记，否则 session_start / 多窗口协调 / 新窗口读档看不到。**登「双索引」——缺一即断链**（2026-06-20 gdn2vessel 踩坑：只登 registry 没登 CLAUDE.md，新窗口选它读不到阶段档）：

1. **registry**（报进度用）：写入 `.portfolio/registry.json` 的 `projects`：`{name, venue, deadline, status:"planning", priority, home, story, acceptance, log}`。
2. **CLAUDE.md 入口清单**（读档用，**别漏**）：在 `CLAUDE.md`「进具体某项目动手前」清单补一行，格式：
   ```
   - **<key> / <Name>**（cwd 含 <home> 或任务含 <关键词>；status=planning）：<home>/00_README.md → `01_STORY.md` → `02_ACCEPTANCE.md` → `04_LOG.md` 最新 entry
   ```
   > registry 只让 hook 报进度；**读哪些档的指令真源是 CLAUDE.md 这张清单**。两处必须同时写。
3. **数据集**：用到的进 `.portfolio/datasets.json`（本地+HPC+source+状态）；脚本只引此真源，不硬编码。
4. **认领**：写 `.portfolio/locks/<project>.claim` 认领本窗。
5. **首条 LOG**：立项决策（方向/会议/RQ/边界）记入该项目 `04_LOG.md` 首条 entry。
6. **自检兜底**：跑 `python tools/check_registry_pointers.py`，registry 与 CLAUDE.md 入口清单一一对齐才算建档完成（drift guard，不靠记性）。

> 立项点（方向/会议/核心 RQ）是**拍板点**：先问用户定，不自作主张。详见 `project/PROJECT_LIFECYCLE.md`。

## 警告规则

- 如果目标会议与主论文目标会议同期（< 2 个月）：提示 GPU 时间冲突风险
- 如果子论文核心实验尚未完成：不建议立项，先完成实验再剥离
- 如果重叠度可能 > 30%：明确提示双重投稿风险，用户确认后再继续
