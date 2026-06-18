# DisagreePred — 预测标注分歧（而非消除分歧取 GT）

> 项目入口。深读档顺序：本文 → `01_STORY.md` → `02_ACCEPTANCE.md` → `04_LOG.md` 最新 entry。
> 源 = ideation run-002（医学图像 × 不确定性）G6 立项 **C065**，2026-06-18 用户拍板立项（G6 charter 2026-06-17）。

## 一句话

LIDC-IDRI 4 位标注者对「该位置算不算结节」存在性分歧巨大——**2669 个被标结节仅 928（34.8%）获 4/4 一致，即 65.2% 存在某种存在性分歧**（Armato 2011 原始统计）；所有研究用 majority-vote 当 GT、把分歧当噪声消除，**无人问 AI 能否预测分歧本身**——「AI 能否在人类专家也犹豫的地方学会犹豫」。本文把**预测分歧本身**当成建模目标。

> ⚠️ 数字订正（2026-06-18 researcher 核源）：旧稿「margin 0.22」用错——0.22 来自 Dong 2017 是结节**边缘锐利度评分**（1-5 量表）的 interobserver disagreement，**不是 detection-level 存在性分歧**。存在性分歧正确口径 = 65.2%（Armato et al. Medical Physics 2011, PMC3041807）。

## 为什么新（R4 taste 48 全 top，零直接竞品）

- framing 新：**预测分歧 vs 消除分歧取 GT**——目标函数本身换掉，不是又一个难度估计代理。
- 临床价值：模型在专家也犹豫处主动标「不确定」，正是可信医学 AI 想要的 deferral 信号。
- ⚠️ 须守住差异化于 EDUE(2403.16594) / 2510.10462（难度估计 / disagreement-guided 训练）——它们用分歧**辅助**别的目标，本文把「预测分歧本身」当**终极目标**。

## 立项依据 + gating

- LIDC-IDRI 4-annotator 存在性分歧结构（65.2% 被标结节非 4/4 一致，Armato 2011）= 真实存在的、可量化的、临床有意义的分歧源。
- **G5 killshot ⏳ 未跑**（数据待下）→ 列为 **KILL-1 gating，立项后首要动作**：下 LIDC 后跑分歧可预测性 baseline，AUROC ≤ 0.60 即核心 claim 死。

## 诚实天花板（立项即知）

framing 强 + taste 高，但**核心 claim 全押在 KILL-1**：分歧能否从图像预测是先验后投入的硬 gate。过不了即砍，过得了才谈 MICCAI。书面 kill criteria K1-K4 见 `02_ACCEPTANCE.md`。

## venue

top：MICCAI 2026｜fallback：MedIA / UNSURE workshop / NeurIPS D&B。

## 数据 / 算力

LIDC-IDRI（TCIA 公开免费，1018 CT，4-annotator，**需下载**）+ QUBIQ 备用。算力预算 ≤ 50 GPU·h。数据状态见 `.portfolio/datasets.json` lidc 条目。

## 文件导航

| 路径 | 内容 |
|---|---|
| `01_STORY.md` | 战略叙事 + headline + 卖点 + 措辞红线 |
| `02_ACCEPTANCE.md` | 验收判据 + 书面 kill criteria K1-K4 |
| `04_LOG.md` | 进度留痕（倒序）|
| `00_provenance/` | 来源溯源（G6 立项卡指针）|

## 来源全档

立项卡 `project/ideation/runs/2026-06-17_run-002_medimg-uncertainty/07_report/G6_charter.md`（立项 2）。
