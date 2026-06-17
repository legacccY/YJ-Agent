# 工业化留痕目录结构（Structure）

> 选题流水线每跑一轮 = `runs/<date>_run-NNN_<slug>/` 一个独立文件夹，**全过程留痕透明**：从约束→文献→原始候选→逐闸筛选→自动实验探路→立项报告，每一步落盘可追溯，谁都能复盘"为什么这个活了那个死了"。
> 留痕铁律：**只增不删**。被砍候选不删行、被否方向存档，negative pool 是复盘 + 训练直觉的资产。

---

## 顶层（体系级，所有轮共用）

```
project/ideation/
├── 00_README.md            病因+总图+三支柱+怎么跑
├── 01_CHARTER.template.md  宪章模板（每轮复制填）
├── 02_RUBRICS.md           全部量规 R1-R7
├── 03_GATES.md             G0-G6 逐闸细则
├── 04_POOL.schema.md       候选池 jsonl 字段
├── 05_TOOLING.md           工具规格 + 实现状态
├── 06_STRUCTURE.md         本文：目录留痕规范
└── runs/                   每轮一个独立留痕文件夹
```

## 每轮（`runs/<date>_run-NNN_<slug>/`）

```
00_charter.md               【锁定宪章】本轮约束的唯一真源，签字后不改
                            （硬排除/算力/venue档/风险/雄心上限/默认kill线）

01_requirements/            【要求】宪章展开成机器可执行的约束清单
├── hard_constraints.md     硬约束（命中即砍，G2 二元 checklist 本轮实例）
├── venue_bar.md            目标顶会的录用标准 + 本轮"超过上限"的判据
└── exclusions.md           硬排除清单（含与封存项目的差异化阈）

02_literature/              【文献】收集到的信息原料
├── corpus.jsonl            撞车检测语料库（S2/arXiv 拉的近年论文 title+abstract）
├── sota_landscape.md       researcher 调研的竞品/SOTA 版图
├── gaps.jsonl              gapmine 挖的 future-work gap 簇
└── citations/              关键论文存档（按主题）

03_raw_candidates/          【原始候选】G1 每个 ideator 按策略分文件
├── S1-gap.jsonl            从 future-work 挖的
├── S2-cross.jsonl          跨域迁移
├── S3-contradiction.jsonl  矛盾/复现失败
├── S4-dataset.jsonl        dataset-first
├── S5-salvage.jsonl        死项目残值
└── S6-sota-limit.jsonl     SOTA 失效边界

04_pool/                    【候选池主台账】
├── pool.jsonl             live 池（逐闸 append 分数+status，schema 见 04_POOL.schema）
└── snapshots/             每过一闸存一份不可变快照
    ├── pool_after_G1_dedup.jsonl
    ├── pool_after_G2.jsonl
    ├── pool_after_G3.jsonl ...

05_screening/              【筛选结果】按闸/轮分目录，每闸留完整裁决
├── G2_collision/          撞车检测原始输出（每候选最近邻论文+余弦）+ kill 清单
├── G3_scoring/            InnoEval 打分表 + Swiss 对战记录 + 12维taste + rerank
├── G4_redteam/            skeptic 红队报告 + pre-mortem + 最大风险假设
└── G5_killshot/           杀手锏实验的 go/kill 裁决汇总

06_experiments/            【自动实验探路】多轮筛选后自动出计划→验证
├── plans/                 planner 出的 <1GPU·h 杀手锏实验设计（每候选一份）
└── results/               跑完的 csv/state.json + verifier 核数 + 结论

07_report/                 【立项报告】
├── funnel.md             漏斗各级数字（100→...→1）
├── project_cards/        幸存候选完整立项卡（双venue+轨迹+kill criteria）
└── killed_clusters.md    被砍 top 原因聚类（复盘资产）
```

---

## 留痕规则（强制）

1. **00_charter.md 锁定后是本轮宪章唯一真源**，G1-G6 全程对照它执行 kill；要改 → 新开一轮，不改旧的。
2. **pool.jsonl append-only**：过闸更新 status + 追加分数字段，**不删被砍行**；每闸末存 snapshot 不可变副本。
3. **每个 kill 必留 reason + 证据**（撞车留最近邻论文 URL，红队留致命伤原文，预实验留 csv 路径）。
4. **自动实验探路全留**：06_experiments/ 存设计 + 原始结果 + verifier 核数，立项后这些直接进项目 schema 当首批 baseline。
5. **一轮收口写 07_report/funnel.md**：能让任何人 5 分钟看懂这轮怎么从 100 candidates 收敛到立项的。

---

## 与现有流程衔接

- `/ideate` 启动即建本结构（复制本目录骨架）。
- G6 幸存 → `/spin-off-paper` 时，把 `07_report/project_cards/<id>.md` + `06_experiments/results/` 灌进新项目的 STORY/ACCEPTANCE/首条 LOG，**选题轨迹无缝转成项目立项依据**。
- 被砍方向进 `07_report/killed_clusters.md`，下轮 G0 宪章可引用避免重挖。
