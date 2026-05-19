# Phase {N}: {阶段名}

Status: ACTIVE
Started: {YYYY-MM-DD}
Target Deadline: {YYYY-MM-DD}
Responsible: {谁负责执行}

---

## Goal

{一段话描述本阶段目标，说清楚"做什么"和"为什么"}

---

## Success Criteria（全部完成才能推进下一阶段）

- [ ] 指标 A >= {阈值}（当前值: —）
- [ ] 指标 B >= {阈值}（当前值: —）
- [ ] 代码通过测试（`pytest tests/`）
- [ ] 论文对应章节草稿完成（Section {X.Y}）
- [ ] 实验结果已录入 registry.json

---

## Decision Gates（预定义，阶段开始前确认）

在达到以下条件时，执行对应行动，无需等待用户确认：

| 条件 | 行动 |
|------|------|
| Epoch {N} 时 {指标} < {阈值} | 停止训练，转向替代方案 {X} |
| {指标} 连续 {N} epoch 不提升 | 降低 lr 至 {值} 后再试一次 |
| {指标} < {严重阈值} | 立即上报，不自动修复 |
| 达到 Success Criteria | 进入 `/phase-transition` |

---

## Tasks

- [x] {已完成任务}
- [ ] {待完成任务}（Agent: Explore / Plan / Implement / Monitor）
- [ ] {待完成任务}
- [ ] {待完成任务}

---

## Experiment Log

| run_id | config | key_metric | status | note |
|--------|--------|------------|--------|------|
| {timestamp}_{name} | {config.yaml} | {值} | done/running/failed | {备注} |

---

## Blockers

{描述当前阻塞项，没有则写 None}

---

## Notes

{其他需要记录的上下文}
