# {PROJECT_NAME} — Overview

Last Updated: {YYYY-MM-DD}
Current Focus: Phase {N} — {阶段名}
Blocker: {当前阻塞项，没有则写 None}
Next Decision: {下一个需要决策的事项}

---

## Phase Progress

| Phase | Name       | Status | Key Result                    | Run ID / Date |
|-------|------------|--------|-------------------------------|---------------|
| 1     | {名称}     | TODO   | —                             | —             |
| 2     | {名称}     | TODO   | —                             | —             |
| 3     | {名称}     | TODO   | —                             | —             |
| N     | {名称}     | ACTIVE | —                             | —             |

Status 选项: TODO / ACTIVE / DONE / BLOCKED

---

## Critical Numbers（每个数字必须关联 run_id）

| Metric | Value | Run ID | Config | Verified |
|--------|-------|--------|--------|---------|
| {指标名} | {值} | {run_id} | {config_file} | [ ] |

规则：写进论文的每个数字必须在此表中有对应 run_id，否则不能引用。

---

## Sub-papers

| Topic | Venue | Deadline | Status | Path |
|-------|-------|----------|--------|------|
| {主题} | {会议} | {日期} | {状态} | ./papers/sub_{topic}/ |

---

## Quick Links

- Active Plan: ./plans/phase_{N}_active.md
- Registry: ./experiments/registry.json
- State: ./experiments/state.json
- Latest results: ./experiments/runs/{latest_run_id}/final_metrics.json
