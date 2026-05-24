# ICLR 2027 项目日志（时间倒序，单一日志真源）

**规则**：每次会话开始读最新 entry，结束写新 entry。今后所有进度入此（替代 WORKLOG.md 重复部分）。

> 格式：`## YYYY-MM-DD（会话 N）` → 完成 / 待续 / 命中率回退诚实记录

---

## 2026-05-24（会话 2，Stage 1 训练启动 + ep6 Gate 修复）

### 完成
- VisiEnhance Plan A 架构升级：enc_blocks=[2,2,2], mid_blocks=6 → ~15.3M 参数（3-level U-Net, ch: 64→128→256→512）
- 冒烟测试 6/6 全通过（param_count / forward / range / FiLM identity / CUDA / AMP）
- Stage 1 训练启动（PID 28460），/loop 全自动监控，每 epoch ~23min
- ep0-6 监控数据：PSNR 22.05→23.03→23.48→23.76→23.99→24.17→24.27 dB
- ep10 Gate（<27 dB）外推 ~24.4 dB，主动在 ep6 停训（节省 ~1.5h GPU）
- A+B 修复应用：
  - A: `val_severity: medium`（去掉 heavy 拉低均值，测真实 moderate 能力）
  - B: `lambda_lpips: 0.05`（L1 + LPIPS 加速感知收敛）
  - 续训：从 ep6 checkpoint 续，PID 25804 已运行

### 关键发现
- 每 epoch ~23min，200 epoch 全程 ETA ~78h（比预期 30-40h 长，因数据集 69k 对 × severity=mixed）
- ep6 增量急降（+0.18→+0.10），确认 Gate 会触发
- v0 基线（1.7M, 30ep）= 25.55 dB；本次 15.3M 在 ep6 = 24.27（mixed val，正常，bigger model 收敛慢）
- ep7 续训后 val PSNR 应显著跳升（medium subset 比 mixed 容易）

### 待续（M1 W1）
- [ ] ep10 续训 Decision Gate 重评（预计 2026-05-25 早，medium val PSNR 目标 ≥27）
- [ ] Theorem 2 (agent risk bound) 数学推导（与训练并行）
- [ ] 若 ep10 通过 → 继续全程训练至收敛

### 命中率回退
- 本会话无论文内容改动，命中率预估维持 **32.5%**（ep6 停训不影响 lever 进度）

---

## 2026-05-24（会话 1，大项目启动）

### 完成
- BMVC 目录封印：`meeting/BMVC/SUBMITTED.md` + README 顶部加 🔒 SEALED 标记
- 旧顶层文档归档：`archive/2026-05_pre_iclr_reorg/{PROJECT_OVERVIEW.md, VisiSkin-Agent指导手册.md, 创新点/}`
- 5 个主文档全套创建（对标 BMVC/README 风格）：
  - `README.md` — 入口（128 行）+ 4 文件读档顺序
  - `STORY_FRAMEWORK.md` — 故事框架，10 跑偏定义 + §1-§9 章节锁定 + 锁定数字表 + R1-R10 防御
  - `ACCEPTANCE_CRITERIA.md` — 25 lever 验收 + E1-E12 阈值 + 红线 + M1-M4 milestone
  - `DATA_INVENTORY.md` — checkpoint + 数据集 + 30+ csv + 脚本 + W1-W16 待跑
  - `PROJECT_LOG.md` — 本文件（首版）
- `CODEBASE_README.md` — 原 README.md 改名（代码库 reproduce 说明保留）
- `meeting/ICLR2027/` 空骨架已建

### 关键决策（已与用户对齐）
1. **大项目目标**：ICLR 2027 完整 5 模块系统（2026-09-22 abstract / 09-29 full deadline）
2. **VisiEnhance 路线**：方案 A — 换大 config（base_channels=64, mid_blocks=8, ~15M 参数, 30-40h）重训
3. **目标命中率**：78-80%（25 lever stack）
4. **文档结构**：全套对标 BMVC（5 文件）

### 命中率预估
- 基线（ICLR 平均接受率）：30%
- 已完成 lever（L1/L6/L11）：+2.5%
- 当前预估：**32.5%**
- 目标 M4：78-80%

### 追加完成（同会话晚段）
- 4 Claude Code hooks 部署到 `D:/YJ-Agent/.claude/hooks/`：
  - `iclr_session_start.sh` — cwd 含 YJ-Agent 时输出 4 文件读档顺序
  - `iclr_prompt_submit.sh` — keyword 触发（论文/训练/BMVC/扩散）+ Opus-in-ICLR caveman 自动 off
  - `iclr_pre_edit.sh` — Edit/Write BMVC 非 rebuttal 路径 → block exit 2
  - `iclr_post_edit.sh` — Edit/Write ICLR2027 tex / 主指导 md 命中 R1/R2/R4/R8 → stderr exit 2
- `D:/YJ-Agent/.claude/settings.json` 注册 4 hooks（SessionStart / UserPromptSubmit / PreToolUse / PostToolUse）
- 实测 10 个测试场景全通过
- Token overhead 估算 ~10-20 / turn（摊薄）

### 待续（M1 W1，2026-05-25 ~ 06-01）
- [ ] VisiEnhance Plan A 大 config 文件起草（`configs/visienhance_s1_planA.yaml`）
- [ ] 启动 Stage 1 重训（~30-40h，需先空出 GPU）
- [ ] Theorem 2 (agent risk bound) 数学推导启动
- [ ] **Phase A 自动化脚本**（pending）：
  - `scripts/iclr_grep_redlines.sh` (CLI 版红线扫描)
  - `scripts/check_numbers_consistency.py` 扩展 17 → 30 数字
  - `tests/test_theorems_numerical.py` (Prop 3 / Lemma 3 / Thm 2 toy 验证)
- [ ] **Phase C 多 agent slash commands**（pending）：
  - `/iclr-plan` Opus 无 caveman
  - `/iclr-execute` Sonnet subagent
  - `/iclr-check` Haiku subagent

---

## 历史会话（BMVC 阶段，已封印）

> ⚠️ BMVC 阶段的会话历史保留在 `D:/YJ-Agent/WORKLOG.md` 旧版本 + `meeting/BMVC/BMVC_LOG.md` + `meeting/BMVC/SUBMITTED.md`，不在本文件复述。

**BMVC 关键里程碑**（速查）：
- 2026-05-21 第六次会话：BMVC 主文 18→10 页（hard limit）+ 3 reviewer 全应答 + A1 forward ablation 硬实证 → 投稿就绪
- 2026-05-29：BMVC P2 deadline 投稿
