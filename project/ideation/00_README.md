# 选题工业流水线（Ideation Pipeline）— 组合台立项前置体系

> 组合台所有**新项目立项前**的唯一前置流水线。把「拍脑袋定一个大胆方向 → 跑了才发现塌」改成「批量产 100 个候选 → 规则化漏斗逐级筛杀 → 立项前廉价证伪 → 才立项」。
> CLAUDE.md / PORTFOLIO.md / PROJECT_LIFECYCLE.md 的「新项目立项」一步指向此体系。
> 建立 2026-06-17。设计依据见本文末「研究依据」。

---

## 0. 为什么要这条流水线（病因诊断）

组合台 4 个项目，**每个最初最大胆的 claim 都死了**，被迫一路降格退守：

| 项目 | 立项时的大胆 claim | 结局 |
|---|---|---|
| MedSeg-UQ | 顶会理论下界 | ★1 minimax 不存在 / ★3 拼接不成立 → 塌缩存档 |
| NCA-JEPA | NCA 抗遗忘 / 轨迹即表示 | 5 路线①③死④弱，"撑不起非常大胆" → 封存 |
| ICLR VisiSkin | Q-VIB SOTA | 判死不复活，拆两篇降格 Thm2 |
| MedAD-FailMap | 三假设全绿 | ②跨集外推腿无读数，带债推进 |

**共同死法 4 种**（本流水线每一闸针对性堵）：

1. **立项乐观无事前对手** —— 立项=乐观的自己自我确认，闸口(stage-gate/reviewer)杀在花完算力之后。→ **G4 红队 + G5 立项前证伪**前移。
2. **理论先行、实证滞后** —— 漂亮理论故事先立项，跑了才知实证不撑。→ **G5 强制 <1 GPU·h 杀手锏预实验**，核心 claim 立项前先验。
3. **挑"蓝海"一碰就塌** —— 优化"大胆/新"没优化"能活"。很多 claim "没人做过"正因为一碰就塌。→ **G2 工具撞车检测 + 可行性硬闸 + G3 excited-reader 测试**。
4. **顶会执念** —— 默认全 ICLR/NeurIPS，本可发表的工作被顶会尺子量成"失败"。→ **G0/G6 强制双 venue 分档**（顶会版 + 退路版同时写）。

> 核心理念：**把组合台现有的"事后才严"（verifier/reviewer/stage-gate 极诚实极能杀，但杀在闸口）提前到"事前就严"。** 立项门槛建在证据上，不建在希望上。

---

## 1. 体系总图（G0→G6 六闸漏斗）

```
G0 宪章 Charter       定约束搜索空间                              人(Opus主线+用户)主导
   │  输出: charter.md（领域/硬排除/算力预算/venue档/风险/默认kill线）
   ▼  喂 config，不是候选
G1 批量产出 Generate   ideator×N 多策略扇出 → 去重+多样性聚类       ideator(sonnet)×N
   │  100 候选 → 去重(SPECTER2 cos 0.8) → ~50 唯一            通过率 ~50%
   ▼
G2 机器硬筛 Screen     二元 kill checklist + 工具撞车检测           自动(tools/) + 主线
   │  ~50 → ~20   撞车>0.85 / 超算力预算 / 无 gap / 命中排除清单 → 砍   通过率 ~40%
   ▼
G3 评分排序 Rank       补情报 → InnoEval加权 + Swiss pairwise        researcher + 主线
   │  ~20 → 8-10   硬阈: Feasibility<4 或 Novelty<5 即砍          通过率 ~45%
   ▼
G4 红队预演 Pre-mortem skeptic 攻三死法 + pre-mortem → RAT          skeptic(opus)
   │  8-10 → ~5    列致命路径，提炼最大风险假设                   通过率 ~55%
   ▼
G5 杀手锏预实验 Kill-shot 设计<1GPU·h 廉价证伪 → 跑 → 核心claim没死  planner→🛑主线跑→verifier
   │  ~5 → 2-3     ⚠️训练经 gpu_slot.py 调度                     通过率 ~50%
   ▼
G6 立项拍板 Go        完整双 venue + 书面 kill criteria             用户拍板
      2-3 → 1      → /spin-off-paper 建 schema + 登 registry
```

总漏斗 100→1，≈1%，与 VC deal funnel（leads→investment ~0.5-1.5%）同量级。这是**特性不是 bug**——大量便宜地杀，剩下的才贵地养。

---

## 2. 三大支柱（用户要的"批量化 + 约束规则 + 体系"）

**支柱 A — 批量化（不是 1-2 个，是 50-100 个）**
Stanford 实证：单主题 4000 seed idea 里 95% 是重复。所以批量必配**强制去重 + 多样性聚类**，否则下游全浪费在重复上。G1 用 6 种正交生成策略 × ideator 扇出，再 SPECTER2 余弦 0.8 去重 + 聚类保多样。

**支柱 B — 约束规则（硬约束写死在宪章，不靠每次手感）**
G0 宪章把搜索空间一次性钉死：领域边界、**硬排除清单**（NCA/JEPA 家族、已死方向表亲，见 [[feedback_explore_novel_not_overlap]]）、算力预算（本机 1×4070 8GB + HPC 4×4090）、venue 双档、风险偏好、默认 kill criteria。G2/G3 把约束转成**二元 kill 闸 + 硬阈**（可行性<4 直接砍，不进入加权），机器执行，不留情面。

**支柱 C — 体系（漏斗 + 候选池台账 + 工具，不是堆 agent）**
候选池 `pool.jsonl` 是单一台账，每个候选一行，逐闸追加分数 + 存活状态。已有 9 角色 agent 当**执行器**嵌进各闸（ideator/researcher/skeptic/planner/verifier），不新造一堆角色。工具层 `tools/ideation_*.py` 做撞车检测 + gap 挖掘，免费 API 额度内跑。

---

## 3. 怎么跑（一键）

```
/ideate "<方向种子或宪章要点>"      # 主线当 lead，按 G0→G6 编排
```

- **G0–G1** 自动：主线据种子草拟宪章（用户过目改）→ 起 ideator×N 批量产出 → 去重聚类落 `pool.jsonl`。
- **G2–G3** 自动：跑撞车检测工具 + researcher 补情报 + 打分排序，淘汰大部，落分进池。
- **G4** 自动：skeptic 对 top 8-10 红队 + pre-mortem。
- **G5 🛑 拍板点**：杀手锏预实验要跑训练 → 经 `gpu_slot.py` 调度，主线串行跑（自主区，有空卡即起）。
- **G6 🛑 拍板点**：幸存 2-3 个带完整双 venue + 书面 kill criteria 呈用户，**立项是用户的决策**，拍了才 `/spin-off-paper`。

详细每闸的输入/输出/负责 agent/通过率/kill 条件见 [`03_GATES.md`](03_GATES.md)。

---

## 4. 文件结构

| 文件 | 作用 |
|---|---|
| `00_README.md` | 本文：病因 + 总图 + 三支柱 + 怎么跑 |
| `01_CHARTER.template.md` | G0 宪章模板（每次立项探索复制一份填） |
| `02_RUBRICS.md` | 全部评分量规（12 维 taste + InnoEval 加权 + Heilmeier + kill criteria 模板）|
| `03_GATES.md` | G0–G6 逐闸细则（方法/负责 agent/通过率/kill 条件/I-O）|
| `04_POOL.schema.md` | 候选池 `pool.jsonl` 字段 schema |
| `05_TOOLING.md` | 撞车检测 + gap 挖掘工作流（API/SPECTER2）+ 工具实现状态 |
| `06_STRUCTURE.md` | **工业化留痕目录规范**：每轮 `runs/<date>_run-NNN_<slug>/` 的子目录布局 + 只增不删铁律 |
| `runs/` | 每轮一个独立留痕文件夹（约束→文献→候选→逐闸筛选→自动实验→立项报告全留痕）|

**策略存活台账**（每轮 G6 后更新，数据驱动调配额）：

| 策略 | 族 | 产出候选（inferred tag） | G6 存活 | G5/G6 死亡 |
|---|---|---|---|---|
| S3-contradiction | B | selinf（benchmark 樱桃挑通胀） | ✓ 立项 | — |
| S4-dataset | B | disagree（标注分歧可预测）/ nca-phasemap（稀疏度相变） | ✓×2 立项 | — |
| S1-gap | A | C015（公平+长尾，run-005） | — | ✗ G5 杀（缝合空机制） |
| S6-sota-limit | A | C105（mech-interp 搬皮肤，run-005） | — | ✗ G5 杀（缝合空机制） |
| S2-cross | A | run-004 世界模型×医学（多条） | — | ✗ G5/G6 无强赢家 |

> 注：selinf/disagree/nca-phasemap 精确策略 tag 为 inferred（主线据现象型归 B 族），run-002/003 pool 有真 tag 以真 tag 为准。每轮补录：「哪策略产的，存活/死亡 + 死因」。配额按此表数据在下轮 G0 宪章时动态调。

**轮次台账**：
- `runs/2026-06-17_run-001_nca-wm-medseg-uq/` — NCA-WM/MedSeg-UQ 残值挖
- `runs/2026-06-17_run-002_medimg-method/` — 医学影像全模态·方法创新型(CVPR/MICCAI/NeurIPS)·70/30 稳健·≤两周中训（charter 锁定，G1 进行中）
- `runs/2026-06-17_run-003_nca-medimg/` — NCA × 医学影像单轴（剔除世界模型轴）
- `runs/2026-06-17_run-004_medimg-worldmodel/` — 世界模型 × 医学影像（与 run-003 正交，硬排除 NCA/JEPA 家族）·60/40·ML 顶会主投。全漏斗 `104→(G2)69→(G3)45→(G4 0致命)12→(G5)终判`。**G5 无强去风险赢家**：C049 PASS 但 floor effect（rollout 卖点软）/ C047 GRAY（同模态 proxy 太弱）/ C042 GRAY（归一化假象）/ C077 KILL。**2026-06-18 G6 用户拍板=B+C：先补 C047 真 CHAOS 跨模态 G5 去风险，暂不立项**；对齐后仍分歧→立 C047，塌→回 C049 reframe 兜底。决策档 `07_report/G6_decision.md`。下一步=researcher 解 CHAOS 闸→planner 设计→coder→主线跑。

运行时挂件：`.claude/agents/ideator.md`（批量产出工）+ `.claude/commands/ideate.md`（编排 skill）+ `tools/ideation_collision.py` / `ideation_gapmine.py`（已实现+测试）。

---

## 5. 研究依据（外部最佳实践，4 路 researcher 联网采集）

本体系不是凭空设计，每个机制对应一条实证：

- **批量去重必需**：Si et al. 2024（Stanford，[arXiv:2409.04109](https://arxiv.org/abs/2409.04109)）—— 4000 seed 中 95% 重复；LLM 自评 pairwise 准确率仅 53.3%（≈随机），所以 G3 用 Swiss pairwise 不用 LLM 单条打分，且保留人工 final rerank（human rerank 使 top idea 重叠仅 17/49）。
- **Feasibility 必须单独闸**：同上，评审 feasibility 与 overall 分相关 r<0.1（几乎被忽略）→ G2/G3 把可行性设硬阈，不混进加权。
- **Novelty 不能信 LLM 自报**：AI Scientist 把 SGD micro-batching 误判为新颖（[arXiv:2502.14297](https://arxiv.org/html/2502.14297v2)）→ G2 用 Semantic Scholar / OpenAlex / SPECTER2 工具显式比对 top-K。
- **多样性防同质**：Nova（[arXiv:2410.14255](https://arxiv.org/abs/2410.14255)）迭代检索规划 + k-means 聚类使独特 idea 3.4×；co-scientist（[arXiv:2502.18864](https://arxiv.org/abs/2502.18864)）Proximity Agent 聚类 → G1 多样性聚类。
- **Generate→Debate→Evolve**：co-scientist 高分假设进化变体重入 Elo 锦标赛 → G3 Swiss + G4 红队后可回修重排。
- **选题量规**：Hamming「reasonable attack」、Heilmeier 8 问、Uri Alon 难度×增益矩阵 + inner-voice、Jason Wei headroom、Chris Olah「excited to read it?」、EA ITN → 综合成 [`02_RUBRICS.md`](02_RUBRICS.md) 的 12 维。
- **漏斗 + kill criteria**：Cooper Stage-Gate（go/kill/hold/recycle + gatekeeper）、RICE/ICE、Gary Klein pre-mortem（风险识别 +30%）、Lean RAT（先测最大风险假设）、VC deal funnel 转化率 → G0–G6 的 gate 设计 + 通过率。

完整引用见 [`03_GATES.md`](03_GATES.md) 各闸脚注。
