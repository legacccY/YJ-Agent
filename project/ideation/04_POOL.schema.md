# 候选池 schema — `runs/<date>_pool.jsonl`

> 选题池 = 单一台账，每个候选一行 JSON，逐闸追加分数 + 存活状态。仿 run-experiment 的 state.json 模式，防 context 压缩断链。
> 一行一候选，append-only（砍掉的不删，标 status，留作负样本 + 复盘）。

## 字段

```jsonc
{
  // —— G1 产出时写入 ——
  "id": "C001",                    // 候选编号
  "gen_date": "2026-06-17",
  "strategy": "S1-gap",            // S1-gap / S2-cross / S3-contradiction / S4-dataset / S5-salvage / S6-sota-limit
  "one_liner": "一句话选题",        // 无术语（Heilmeier Q1）
  "problem": "要解决的问题 + 为什么重要",
  "approach": "初步攻击路径",
  "why_new": "凭什么是新的（差异化角度）",
  "venue_top": "顶会档",
  "venue_fallback": "退路档",
  "datasets": ["引用 .portfolio/datasets.json 或公开源"],
  "compute_est": "算力估（GPU·h，对照宪章 C）",
  "cluster": 3,                    // G1 多样性聚类簇号
  "mechanism_anchor": "phenomenon", // G1 A族必填：phenomenon（锚在可观测反常/数据特性）/ mechanism（指名具体机制）/ MISSING（答不上）；B族(S3/S4)天然填 phenomenon
  "anchor_note": "一句话说明锚点：具体是哪个现象或机制",  // G1 A族必填，B族建议填

  // —— G2 机器筛追加 ——
  "g2_collision": {"max_cos": 0.72, "nearest": "arXiv:xxxx 标题", "source": "specter2|s2|openalex"},
  "g2_gap_support": "future-work 出处 / null",
  "g2_kill": null,                 // null=过；否则 "硬排除|撞车|算力|可行|无gap|已解|DDL"

  // —— G3 评分追加 ——
  "g3_innoeval": {"q_novelty": 7, "c_novelty": 5, "feasibility": 5, "significance": 6, "validity": 6, "clarity": 8},  // q_novelty×0.20 + c_novelty×0.10 + feasibility×0.25 + significance×0.25 + validity×0.10 + clarity×0.10
  "g3_pattern": null,              // null | "pure_recombination"（C-Novelty≥7 且 Q-Novelty≤4，扣 0.5）
  "g3_weighted": 6.20,             // Σ(维×权) ±惩罚
  "g3_swiss_wins": 4,              // 5 轮 Swiss 累计胜场
  "g3_rank": 3,                    // final rerank 后名次
  "g3_taste12": [4,3,5,4,3,2,5,4,4,5,5,3],  // 仅 top10 跑，12 维 0-5
  "researcher_brief": "情报回汇路径 / 关键发现",

  // —— G4 红队追加 ——
  "g4_heilmeier": "8 问作答路径 / 答不出的条目",
  "g4_skeptic": {"fatal": 0, "verdict": "可推进", "residual": ["残差..."]},
  "g4_riskiest": ["最大风险假设1", "假设2"],   // 喂 G5
  "g5_design": "杀手锏实验设计（planner）",

  // —— G5 预实验追加 ——
  "g5_result": {"job": "gpu_slot id", "csv": "结果路径", "verdict": "claim 没死|证伪"},

  // —— G6 立项追加 ——
  "kill_criteria": "R7 书面 kill criteria（幸存才填）",

  // —— 贯穿状态 ——
  "status": "alive | killed@G2 | killed@G3 | ... | promoted@G6",
  "kill_reason": "被砍原因 / null"
}
```

## 用法

- G1 ideator 各自吐 JSONL 片段 → 主线 cat 合并 + 去重 → `runs/<date>_pool.jsonl`。
- 每过一闸，主线/工具就地 append 字段、更新 `status`。
- 砍掉的**不删行**——negative pool 是下次复盘 + 训练直觉的资产（组合台死项目残值同理）。
- 一轮结束在 `runs/<date>_选题报告.md` 汇总：漏斗各级数字 + 幸存立项卡 + 被砍 top 原因聚类。
