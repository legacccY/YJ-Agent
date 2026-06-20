# gdn2vessel 多窗任务 + 完成线（DoD）

> 真源 = Conductor 图 `.portfolio/pipelines/gdn2vessel.json`（看 `python tools/pipeline.py status gdn2vessel`）。
> 本文件 = 每个节点的**硬完成线**：到线就 `done`，**不被往前推到下个棒**。
> 承 `PROJECT_LOG.md` Entry 14 待续 4 条。本轮 = 修命门设计 → 重投正式命门（92 GPU·h，拍板点）。

## 共同红线（所有窗）
- 只碰本棒 territory 的文件，不串别棒。
- 四红线：数字 Bash/Grep 核 csv 不信 Read · 超参/架构查官方源查不到标 TODO · 复现零偏离 · 评估集不泄漏。
- 到拍板点 / 做完就**停**，不自动往下个棒冲。
- 各窗 `done` 后全汇 `integrate`（主窗跑真 e2e 烟测）= 放行 92 GPU·h 训练前的总闸。
- 计划外岔路先问用户，不盲跑（项目铁律）。

---

## 节点 scout-baseline（C 窗 · researcher）
**服务**：P3 baseline 全谱 / L3 lever。
**territory**：`reference/` + `PLAN/BASELINE_SPEC.md §5` 状态表。
**完成线（5 TODO 各有结论，查到=带官方源链 / 查不到=显式标 TODO）**：
- [ ] creatis LICENSE：CeCILL 确认 or 不可用
- [ ] cbDice/SkelRecall 官方混合权重（nnUNet 1:1:1?）
- [ ] DSCNet TCLoss（DRIVE 官方只 BCE?）
- [ ] normalize + augment 各 baseline 官方默认
- [ ] MambaVesselNet 2D 可行 or 降档 C
**停**：5 行状态表填满即 `done`。不顺手改 baseline 代码。

---

## 节点 design（A 窗 · planner → skeptic 复核）
**服务**：命门 = Claim2 re-ID 可归因 / L1 lever。
**territory**：设计稿（出草案，**不改** `ACCEPTANCE_CRITERIA.md` 本体——那是 gate-accept 拍板点）。读 Entry 14 待续1 + ACCEPTANCE P4 判据2(L61-72) + PHASE_4 第8项。
**完成线**：
- [ ] planner 出修订设计：A1' 等参臂定义清楚（QKV+门+LN 同 A2，换普通线性 attn 替 delta-rule）→ 三臂 A2>A1'>A0' 才干净归因「关联记忆机制」
- [ ] 统计方案改：中介直接效应分解 or ε_β0 配平分层，**删 over-control 措辞**
- [ ] 写出新 ACCEPTANCE P4 判据2 **草案**（partial_corr 作废 → 双判据）
- [ ] skeptic 复核 = **0 致命🔴**（有🔴 回 planner 修，不算完）
**停**：0🔴 后停在 `gate-accept` 拍板点。**A 窗不准改 ACCEPTANCE 文件**——出草案就 `done`，改阈值由主窗报用户拍板。

---

## 节点 impl-verdict（B 窗 · coder）
**服务**：命门统计工具 / Entry 14 待续3。
**territory**：`src/reid_verdict_v2.py` + `tests/`。
**完成线（4 个 settled 项 + 真烟测）**：
- [ ] 多集路径聚合
- [ ] image_id 加数据集前缀（防撞）
- [ ] 平台斜率检查
- [ ] FIVES 子采样 seed42 固定
- [ ] 本地真 e2e 烟测（非 mock）跑通 + pytest 绿
- LMM 加 C(dataset)：**留 TODO 不做**（等 A 窗 design 统计定案）
**红线**：禁 scipy.stats（OMP），手算残差。
**停**：4 项 + 烟测过即 `done`。不碰 src 其他文件、不跑 HPC。

---

## 节点 impl-drive（D 窗 · coder）
**服务**：DRIVE benchmark / Entry 14 待续4。
**territory**：`src/datasets/drive.py`。
**完成线**：
- [ ] drive.py 用 base_vessel canonical API（签名对齐 chase/fives/stare 已落地）
- [ ] 本地 load 1 图烟测通 + pytest 绿
- held-out 划分：**停在拍板点**，不自己定（DRIVE test 无 GT，须用户拍）
**停**：迁移 + 烟测过即 `done`。held-out 报主窗拍板，不擅自划分。

---

## 拍板点（主窗持，各窗碰到就停下报）
1. **gate-accept**：改 ACCEPTANCE P4 判据2（阈值变更）。
2. **train**：投正式命门 92 GPU·h（4 集×3 臂×3 seed）+ HPC 上传新代码。
3. **DRIVE held-out 定义**（impl-drive 内）。
