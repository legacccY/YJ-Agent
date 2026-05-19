# phase-transition

阶段切换流程。当前阶段所有 Success Criteria 完成后运行。

## 触发场景

用户说"完成阶段 N"、"进入下一阶段"、"阶段 N 做完了"、"phase transition"。

## 执行步骤

### Step 1：读取当前阶段状态

1. 读取 `./plans/phase_{N}_active.md`
2. 读取 `./OVERVIEW.md`
3. 确认 Success Criteria 的完成情况

如果 Success Criteria 未全部完成：
- 列出未完成项
- 问用户："以下 Success Criteria 尚未完成，确认跳过还是继续完成？"
- 若用户确认跳过，记录跳过原因

### Step 2：确认关键数字已入 registry.json

读取 `./experiments/registry.json`，检查：
- 本阶段引用的关键指标是否都有对应 run_id
- 如果有数字未入表：提示用户补录后再继续

### Step 3：生成 phase_{N}_done.md

基于 `phase_{N}_active.md` 中的内容，生成精简摘要（< 50 行）：

```markdown
# Phase {N}: {阶段名} — DONE

Completed: {今天日期}
Duration: {天数} 天

## Key Results
| Metric | Value | Run ID |
|--------|-------|--------|
| {从 Success Criteria 提取} | {值} | {run_id} |

## Deliverables
- [x] 代码: {路径}
- [x] 实验: {run_id}
- [x] 论文章节: Section {X.Y}

## Critical Decisions Made
- {从 Decision Gates 提取实际发生的决策}
```

保存到 `./plans/phase_{N}_done.md`。

### Step 4：更新 OVERVIEW.md

在 Phase Progress 表中：
- 将 Phase {N} 的 Status 改为 DONE
- 填入 Key Result 和 Run ID
- 将 Phase {N+1} 的 Status 改为 ACTIVE

在 Critical Numbers 表中：
- 添加本阶段新产生的关键指标（如果尚未录入）

更新 `Last Updated` 和 `Current Focus` 字段。

### Step 5：初始化 phase_{N+1}_active.md

从 `./project/templates/template_phase_active.md` 复制，填入：
- Phase 编号和名称
- 开始日期（今天）
- Goal（询问用户或根据 OVERVIEW 推断）
- 空的 Success Criteria 和 Decision Gates（让用户填写）

提示用户："请在 `plans/phase_{N+1}_active.md` 中填写 Success Criteria 和 Decision Gates，下次启动阶段前确认。"

### Step 6：更新 CLAUDE.md

将 `Phase: {N}/... — {旧阶段名}` 更新为 `Phase: {N+1}/... — {新阶段名}`。

### Step 7：删除旧的 phase_{N}_active.md

确认 phase_{N}_done.md 已写入后，删除 phase_{N}_active.md。

### Step 8：汇总报告

```
✅ 阶段 {N} 已完成并归档
✅ Phase_{N}_done.md 已创建
✅ OVERVIEW.md 已更新
✅ Phase_{N+1}_active.md 已初始化

下一步：
1. 填写 plans/phase_{N+1}_active.md 的 Success Criteria 和 Decision Gates
2. 运行 /run-experiment 开始下一阶段的实验
```

## 注意事项

- 不要在阶段完成摘要中放大量代码或中间结果
- Decision Gates 里"实际发生的决策"才需要记录，未触发的 gate 不需要
- phase_N_done.md 是永久存档，不应再修改
