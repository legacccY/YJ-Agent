# §7.7 DCA / Triage — ICLR 重跑修复 plan

**建立**：2026-06-15
**触发原因**：会话中 Read 层出现幻觉，凭空"读出"不存在的 `results/agent_triage_sim.csv`（数字 43.2%/10.3% 假数据，差点填进 §7.7 = 踩红线4）。已叫停。

## 已 Glob/Grep/Bash 核验的地面真相（未被污染）

- `results/agent_triage_sim.csv` — **不存在**（Glob: No files found）→ 之前读到的是幻觉
- `main.tex:402` = `\emph{[Pending: net-benefit decision-curve analysis ...]}` → paper 仍是占位，**干净未污染**
- 真 DCA 脚本：`scripts/run_dca_triage.py`（读 `results/itb_predictions.csv`，无需 GPU）
- 脚本输出：`results/dca/{dca_results.csv, triage_results.csv}` + `dca_summary.json`
- 现有 `results/dca/*.csv` mtime = **2026-06-05**（比 ICLR pred 旧 10 天）= BMVC 产物 → 红线10 必须为 ICLR 重跑
- `results/itb_predictions.csv` mtime = 2026-06-15 00:50（ICLR-current，25381 行），BMVC 版已备份为 `itb_predictions_bmvc_repro_bak.csv`

## 执行步骤（全程不依赖 Read，用 Bash/Grep）

1. 重跑（覆盖 06-05 旧 csv）：
   ```bash
   cd /d/YJ-Agent/project && python scripts/run_dca_triage.py
   ```
2. 确认输出刷新（mtime 变今天 + stdout 打印的 max NB / 95% CI）：
   ```bash
   stat -c '%y %n' results/dca/dca_results.csv results/dca/triage_results.csv
   cat results/dca/dca_summary.json
   ```
3. 用 Grep/Bash（**不用 Read**）取真数字：treat-all vs 模型 net-benefit、20% referral budget 下的 triage retained accuracy / referral rate。
4. Edit `main.tex:402` 占位 → 真数字，注明来源 csv。
5. 跑 `/validate-figures` 核 §7.7 数字一致性。
6. 记 PROJECT_LOG.md：§7.7 从 Pending → 实数，红线10 合规（ICLR 重跑非搬 BMVC）。

## 红线提醒
- 红线4：所有 paper 数字必须 csv 可核算，禁幻觉
- 红线10：BMVC 产物不可直接搬，必须 ICLR 重跑
