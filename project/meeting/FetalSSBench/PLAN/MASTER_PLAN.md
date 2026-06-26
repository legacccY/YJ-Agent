# FetalSSBench — MASTER_PLAN（阶段计划顶层导航）

> **一句话**：本文件是 FetalSSBench 四阶段执行计划的入口。它回答「**怎么做、按什么顺序做、每步做完算不算数**」，是动手时的施工图。
> **服务的核心 Claim**（引自 `01_STORY.md`）：首个跨 3 数据集 × 5 标注比例 × 5 方法的胎儿/产科超声半监督分割统一 benchmark，揭示效率曲线/排名稳定性/结构难度不对称三规律，并配自适应置信阈值小增量。
> **venue**：ACCV 2026 主会（CORE-B，paper 截止 **2026-07-05**，dataset 须 camera-ready 2026-10-04 前公开）；退路 WACV App / MICCAI workshop / ISBI。
> **最后更新**：2026-06-25

---

## 📖 读档顺序（新窗口/新 agent 动手前必走）

1. `00_README.md` —— 项目一句话 + 双核贡献 + 铁律。
2. `01_STORY.md` —— 核心 Claim + 命门假设 + 章节弧 + R-rules（R1-R6，反跑偏主文）。
3. `02_ACCEPTANCE.md` —— 二元 PASS/FAIL 验收 + lever 分解 + 各阶段硬阈值（**所有验收阈值的唯一真源**）。
4. `DATA_INVENTORY.md` —— 三数据集细目（PSFHS ✅ / HC18 ✅ / FUGC ⚠️ 需申请）。
5. `04_LOG.md` 最新 entry —— 当前到哪一步、HPC 状态、待决拍板点。
6. **本文件 `PLAN/MASTER_PLAN.md`** —— 选定当前阶段 → 跳对应 `PLAN/PHASE_x_*.md` 深读后施工。

> **PLAN/ 与既有 4 文件的分工**：`00/01/02/DATA_INVENTORY` 回答「**这篇论文是什么、要证什么、验收什么、有什么数据**」（战略 + 契约）；`PLAN/` 回答「**每个阶段具体怎么落地、跑哪些 run、写哪些节、做完怎么判**」（战术 + 施工）。**PLAN 不复制验收阈值，一律引用 `02_ACCEPTANCE.md` 的条目**——阈值改动只改那一处，PLAN 永远指向它。

---

## 🗺️ 四阶段一览

| Phase | 文件 | 状态 | 服务 lever（引自 02_ACCEPTANCE） | 算力估 | 核心产出 |
|---|---|---|---|---|---|
| **1 — Benchmark 主干** | `PHASE_1_BENCHMARK.md` | ✅ **PASS**（回填存档） | lever ① 统一 benchmark 真跑通 + ④ 可复现 | 已耗 ~12-18 GPU·h（HPC 10 chunk） | `results/master_wide.csv`(150 run) + `master_long.csv`(225 行) |
| **2 — 实证规律** | `PHASE_2_REGULARITIES.md` | ✅ **PASS**（回填 + 标裂缝） | lever ② ≥1 可报告规律 | 纯分析（无训练） | 3 规律判定 + 3 图（efficiency/ssl_gain/struct_asymmetry） |
| **3 — 自适应阈值增量** | `PHASE_3_ADAPTIVE_THRESHOLD.md`（待建，本批不写） | ⬜ 待做（拍板后启） | lever ③ 小增量有效或诚实负结果 | 估 ~8-12 GPU·h（低标注/难结构子集） | 自适应 vs 固定阈值对比 + 增量统计 |
| **4 — 写作 + 投稿** | `PHASE_4_WRITING_SUBMISSION.md` | ⬜ 待做（写细） | lever ②③ 落成稿 + ④ 数字三方对账 | 纯写作 | `main.tex` 成稿 + 投稿包（ACCV 2026） |

> Phase 3 文件本批次不建（主线指派为 MASTER_PLAN + PHASE_1/2/4）。Phase 3 启动前应走 `/design-experiment` 派 planner 设计实现矩阵——这是 `04_LOG.md` Entry 10 标记的拍板点。

---

## 🔗 依赖 DAG（波次驱动）

```
Wave 1（并行，已完成）
  ├─ Phase 1 benchmark 主干 ───┐
  └─ 前置研究(SSL4MIS 超参) ────┤
                                ▼
Wave 2（串行，已完成）
  └─ Phase 2 三规律分析 ◀── 依赖 Phase 1 的 master_*.csv
                                │
                                ▼
        ┌─────────── 拍板点（04_LOG Entry 10）───────────┐
        │  Phase 2 PASS → 走 Phase 3（小增量）还是直接写作？│
        │  Phase 3 涉及实现新方法 = 工程量，建议先 /design-experiment │
        └───────────────────────────────────────────────┘
                                │
Wave 3（拍板后）                 ▼
  ├─ Phase 3 自适应阈值（HPC 跑，经 gpu_slot.py 申请卡槽）── 可选/可诚实负结果
  └─ 可选：FUGC 扩 benchmark 深度（需先申请数据）
                                │
                                ▼
Wave 4（投稿冲刺）
  └─ Phase 4 写作 + 投稿（verifier 核数 → writer 写 → reviewer 审 → pre-submit-check）
```

**当前位置**：Wave 2 完成、Wave 3 拍板点待决（见 `04_LOG.md` Entry 10）。Phase 4 可与 Phase 3 部分并行起草（benchmark 设计/规律章节不依赖 Phase 3 结果）。

---

## 📊 信心总账（指针）

> **内部 80% 信心口径**（不改，引自立项决策）：论文成立的承重 = lever ① benchmark 真跑通 + lever ② ≥1 规律显著。这两条已 PASS（Phase 1 + 规律 3 结构难度不对称 Wilcoxon p=0.0468 / Mann-Whitney p=0.0028）。lever ③ 小增量为加分项，诚实负结果亦不塌论文（02_ACCEPTANCE 已明示「增量非论文唯一支柱」）。
> **逐 lever 信心账明细** → 见 `PLAN/LEVER_MATRIX.md`（80% 信心总账，本文件不复制其内容，避免双源漂移）。

---

## ⚠️ 三处反跑偏锚点（贯穿全 PLAN）

1. **数字零自创**（R1）：所有入 tex/PLAN 的数字一律 Grep/Bash 核 `results/master_*.csv`，禁 Read 看数据编造；拿不准写 `\todo{核 verifier}` 占位。
2. **评估集不泄漏**（R2 / 02_ACCEPTANCE 红线）：held-out test 固定 seed，绝不混训练/无标注池；HC18 已去多视角防泄漏（779 主视角）。
3. **承重在相对不对称非绝对增益**（R4）：规律 3 PASS 的措辞是「PS 增益显著 > FH」，**不是** SSL 绝对超 supervised（PS 均增益 −0.0117 微负）。任何写作不得把它夸成「SSL 普遍提升」。
