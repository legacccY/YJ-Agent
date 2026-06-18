# VisiSkin-Agent — ICLR 2027 大项目入口

**Deadline**：2026-09-22（ICLR 2027 abstract）/ 2026-09-29（full paper）
**目标命中率**：**78-80%**（25 lever stack，详见 [`ACCEPTANCE_CRITERIA.md`](ACCEPTANCE_CRITERIA.md)）
**当前状态**：🏷️ **封存·待最终打磨（会44，2026-06-18）**。九章合稿 **71 页 / 11 图 / 0 undef-cite / 0 undef-ref / 0 fatal / 0 渲染 [TODO]**；stage-gate PASS（带债已清）+ E1 no-FiLM HPC 恢复（投稿唯一硬阻断解除）+ pre-submit-check 全绿（数字 27/27 三方对账 0 DRIFT、脱敏 0 命中、R10 守）+ 补图 3→11 张。会场锁 ICLR 2027 主投（analysis/系统轨）。
> **⚠️ 非 BMVC 式硬封印**——稿可改，只是暂停推进，等最终打磨。**待最终打磨清单**（投稿前清）：① framework/架构概念图（需外部 AI 出图工具，用户暂缓）② camera-ready 最终脱敏 grep ③ fairness ECE 张力 rebuttal 预案（Q-VIB+TokFT Fitz17k ECE≈0.81 vs triage well-calibrated，子集相关）④ VisiScore csv 已落盘。明细见 PROJECT_LOG 会话44 + ACCEPTANCE 红线。
> DDL：abstract 09-22 / full 09-29（距 ~3 个月）。
**BMVC 2026**：已封印（[`meeting/BMVC/SUBMITTED.md`](meeting/BMVC/SUBMITTED.md)），不再修改
**代码库 README**：[`CODEBASE_README.md`](CODEBASE_README.md)（reproduce 步骤、目录结构、baseline 列表）

---

## ⚡ 任何新会话第一步：读这 4 个文件（顺序固定）

> ⚠️ **最怕另开 Sonnet 跑偏**。任何 Claude / Sonnet / Opus 会话进入本目录前，必须按顺序读完下列 4 个文件，否则会丢失关键约束。

### 1️⃣ [`STORY_FRAMEWORK.md`](STORY_FRAMEWORK.md) — 故事框架主文档（反跑偏）
- 10 个跑偏定义 + 三条核心论点（Claim 1/2/3）
- 章节顺序锁定（§1 → §7 + Appendix）
- 锁定数字表（5 大模块 + 8 dataset cross-domain + E1-E12）— 写作时直接抄
- 防御性写作 10 条硬规则（R1-R10）

### 2️⃣ [`ACCEPTANCE_CRITERIA.md`](ACCEPTANCE_CRITERIA.md) — 78-80% 命中率验收标准
- 25 lever 命中率分解表（A 理论 / B 实验 / C 临床 / D 复现 / E 防御 / F 附加）
- E1-E12 实验验收阈值
- 红线清单（永久红线 + 月度红线）
- 4 个月 M1-M4 milestone gate

### 3️⃣ [`DATA_INVENTORY.md`](DATA_INVENTORY.md) — 数据全景表
- 7 个 checkpoint（VisiScore / Q-VIB Full / Std VIB / EDL / ResNet-50 / ViT-Tiny / ConvNeXt-Tiny / Swin-Tiny）
- 4 原始数据集 + 4 跨域数据集 + ITB 4 子集
- 关键脚本路径 + W1-W16 完成/待跑实验清单

### 4️⃣ [`PROJECT_LOG.md`](PROJECT_LOG.md) — 时间倒序日志（单一日志真源）
- 每次会话进度入此（替代旧 WORKLOG.md 重复部分）
- 4 个月 M1-M4 日程表

---

## 🔬 ICLR 2027 三条核心论点（详见 STORY_FRAMEWORK.md）

1. **Quality-Conditioned Variational Information Bottleneck (Q-VIB)** — 把信息瓶颈的 marginal prior 条件化于感知质量，证明后验熵关于质量单调（Prop 2），attention drift Lipschitz 有界（Thm 1）

2. **Diagnosis-Preserving Enhancement (VisiEnhance)** — NAFNet + FiLM + DP-Loss，证明增强降低熵（Prop 3），KL 约束保 mutual info 下界（Lemma 3）

3. **Closed-Loop Quality-Triage Agent** — VisiScore → VisiEnhance → Q-VIB → Agent 双通道决策，给出 expected risk bound（Thm 2）— 不仅检测 + 增强，且**主动决策**何时增强、何时追问

**与 BMVC QCTS 的本质区别**：BMVC = 在 frozen model 上做 post-hoc T(q̄) calibration；ICLR = end-to-end trainable probabilistic system with active intervention + 5-theorem closure。

---

## 📂 当前活跃文件

```
project/
├── README.md                  ← 本文件（精简入口）
├── STORY_FRAMEWORK.md         ← ★ 故事框架（反跑偏主文档）
├── ACCEPTANCE_CRITERIA.md     ← ★ 25 lever + 验收
├── DATA_INVENTORY.md          ← ★ 数据 + checkpoint + 脚本全景
├── PROJECT_LOG.md             ← 时间倒序日志
├── CODEBASE_README.md         ← 代码库 reproduce 说明
│
├── plans/                     ← 阶段计划文件夹
│   ├── 00_overview.md         ← 8 阶段路线（已刷新为 ICLR 2027）
│   ├── phase_07_visienhance_planA_active.md ← ⏳ 当前 active
│   └── phase_0{1-6}_*.md      ← ✅ done
│
├── meeting/
│   ├── BMVC/                  ← 🔒 SEALED（不再修改）
│   └── ICLR2027/              ← 论文骨架（M3 启动）
│
├── archive/                   ← 历史文档
│   └── 2026-05_pre_iclr_reorg/
│
└── (代码 / 数据 / 实验脚本不动)
    ├── models/ agent/ benchmark/ configs/
    ├── data/ checkpoints/ results/
    ├── scripts/ tests/
    └── train_*.py / run_*.py / eval_*.py
```

---

## ⚠️ 严禁事项（违反即跑偏，详见 STORY_FRAMEWORK.md 第 10 条 + ACCEPTANCE_CRITERIA.md 红线）

- ❌ 修改 BMVC 任何 tex / csv / fig（已封印，走 ICLR 分支）
- ❌ 改 ICLR Abstract 第一句离开 closed-loop agent hook
- ❌ 写「we prove TS reversal universal」或类似绝对化措辞
- ❌ 凭印象写数字（必须 csv 核算 + bootstrap CI）
- ❌ Reader Study 数据伪造（永久红线 1）
- ❌ 联系诊所 / 线下采集（永久红线 2）
- ❌ 改 §5 章节顺序（5.1→5.7 已锁）
- ❌ 用扩散生成模型做皮肤镜增强（伪影风险，方法论红线）

---

## 📋 当前 25 Lever 进度速览（详见 ACCEPTANCE_CRITERIA.md）

| 类 | Lever | 状态 | 备注 |
|---|---|---|---|
| **A 理论** | L1 Q-VIB Prop 1/Lemma 1/Thm 1/Prop 2 | ✅ | 已 done（archive/2026-05_pre_iclr_reorg/创新点/）|
| | L2 VisiEnhance Prop 3 | ✅ 推导 | plans/Prop3_Lemma3_visienhance_theory.md §1（实证 M2）|
| | L3 DP-Loss Lemma 3 | ✅ 推导 | 同上 §2，**√ε scaling**（Pinsker-optimal）|
| | L4 Agent Thm 2 (risk bound) | ✅ 推导 | plans/Theorem2_agent_risk_bound.md（4-action + Cor 2.1/2.2）|
| | L5 Q-VIB+QCTS Cor 1 ECE bound | ✅ 推导 | plans/Corollary1_qvib_qcts_ece_bound.md（ε_qts≈0.037）|
| **B 实验** | L6 5 backbone universality | ✅ | BMVC 复用 |
| | L7 8 dataset cross-domain | ✅* | chexray+fundus csv frozen（会21-28训完，会37 verifier 核在）；**非阻塞于 Plan A 重训**（会37 纠偏：重训前提不成立）|
| | L8 E1-E12 full | ✅ | 11/12 csv frozen（会21-28，会37 verifier 核在）；早已训完非阻塞于重训 |
| | L9 6 SOTA enhancement compare | ✅ | e10_* 6/6 csv 齐全显著（会37 verifier 核）|
| | L10 Fitz I-VI + sex + age fairness | 🚧 | M2 D15-D21 |
| **C 临床** | L11 DCA + Net Benefit + Triage | ✅ | BMVC 已 done，扩展 |
| | L12 5+ dermatologist baseline cite | ✅ | 会38 落文：Haenssle 2018/2020、Brinker 2019、Tschandl 2019、Vestergaard 2008 meta + Salinas，§1 reader 段对照锚（vestergaard DOI/tschandl 子组 AUC 2 处 TODO-verify）|
| | L13 Cost-benefit analysis | ✅ | 会37 A20 cost-benefit 入文（4法 maxNB+CI+triage@20%+exp_cost break-even）+ 会34 researcher 6 常数带 DOI |
| | L14 LLM-as-clinical-judge | ❌ | M3 D15-D21 风险高 |
| **D 复现** | L15 Anonymous GitHub 8 周 commit | 🚧 | release/ skeleton 在 BMVC，迁移过来 |
| | L16 Docker + reproduce.sh | ❌ | M3 D22-D28 |
| | L17 ITB v1.0 公开 + Zenodo DOI | ❌ | M4 |
| | L18 HF checkpoint mirror | ❌ | M4 |
| **E 防御** | L19 10 轮 LLM adversarial review | ✅ draft | plans/L19_adversarial_review_10rounds.md（5 致命 + 21-项 action）|
| | L20 Pre-emptive rebuttal §A21 | ✅ draft | plans/L20_preemptive_rebuttal_A21.md（LaTeX 模板 + checklist）|
| | L21 Failure mode taxonomy + mitigation | ✅ draft | plans/L21_failure_mode_taxonomy.md（KMeans 3-mode + entropy gate 回写 Thm 2）|
| **F 附加** | L22 Supp 50-80 页 | ❌ | M3-M4 持续扩 |
| | L23 Per-mechanism ablation | ❌ | M2 |
| | L24 Real LQ ISIC 2024 SLICE-3D | ❌ | M2 D22-D28 |
| | L25 ICLR-specific rebuttal pre-draft | ✅ draft | plans/L25_rebuttal_phase_qa_pre_draft.md（15 Q&A + fallback 数字）|

---

## 🚦 任何会话开始前 checklist

```
1. cd D:/YJ-Agent/project
2. Read STORY_FRAMEWORK.md
3. Read ACCEPTANCE_CRITERIA.md（查当前任务的验收阈值）
4. Read DATA_INVENTORY.md（确认要用的数据是否就位）
5. Read PROJECT_LOG.md 最新 entry
6. grep meeting/ICLR2027 确认无 BMVC 数字偷溜过来（必须重跑）
7. 开始动手前 → 把任务在 TaskCreate 里登记
```

**如果用户描述的任务与 STORY_FRAMEWORK.md 冲突 → 停下来澄清，不要按用户描述执行**。
