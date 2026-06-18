# SelInfBench — selective inference 纠正医学 AI benchmark 樱桃挑

> 项目入口。深读档顺序：本文 → `01_STORY.md` → `02_ACCEPTANCE.md` → `04_LOG.md` 最新 entry。
> 源 = ideation run-002（医学图像 × 不确定性）G6 立项 **C025**，2026-06-18 用户拍板立项（G6 charter 2026-06-17）。

## 一句话

医学 AI 论文惯例：跨 HP / seed sweep 选最好那次报结果，经典 p 值与置信区间在「后选」下失效（winner's curse）。本文用 **selective inference**（Lee et al. 2016，条件于「这个配置被选中」事件）给出有效的后选区间，**量化「樱桃挑通胀」（cherry-pick inflation）**，把医学 benchmark 报告习惯里的系统性高估显式校正出来。

## 为什么新（researcher 核实）

- selective inference 在 GWAS / 少数 ML（Zrnic 2023）用过，**医学影像零应用**。
- Springer ML2024 只覆盖「选最好预训练模型」，**不覆盖「同方法多 HP × seed 取最优报告」**——这是医学最常见的樱桃挑形式。
- 定位 = reproducibility / meta-science，正交于 UQ / 校准红海。

## 立项依据（G5 killshot ✅ PASS）

| 项 | 结论 |
|---|---|
| HP sweep best | 18-config sweep best AUC = 0.7467 |
| naive CI | naive 95% CI 上界 = 0.7330（best 落在外侧 = winner's curse 真实存在）|
| selective inference 校正 | deflation **324%** ≫ 5% 阈（HPC job1454467）= 樱桃挑通胀坐实非噪声 |

## 诚实天花板（立项即知）

当前 = **单设定（HAM10000）324% deflation**，可能多设定回落。冲顶会需扩到 **≥3 个真实医学 benchmark** 看 deflation 中位数是否仍显著（KILL-1）。书面 kill criteria K1-K4 见 `02_ACCEPTANCE.md`。

## venue

top：ICLR 2027（reproducibility / meta-science track）或 NeurIPS D&B｜fallback：TMLR（稳，至少落一篇退路档）。

## 数据 / 算力

BraTS2021 / HAM10000 / ISIC2020（本地就位，见 `.portfolio/datasets.json`）。算力预算 ≤ 40 GPU·h。

## 文件导航

| 路径 | 内容 |
|---|---|
| `01_STORY.md` | 战略叙事 + headline + 卖点 + 措辞红线 |
| `02_ACCEPTANCE.md` | 验收判据 + 书面 kill criteria K1-K4 |
| `04_LOG.md` | 进度留痕（倒序）|
| `00_provenance/` | 来源溯源（G6 立项卡 + G5 killshot 脚本/csv 指针）|

## 来源全档

立项卡 `project/ideation/runs/2026-06-17_run-002_medimg-uncertainty/07_report/G6_charter.md`（立项 1）。
G5 killshot 脚本 `.../06_experiments/G5_killshots/killshot_c025_selective_inference.py` + HPC 版 `.../hpc/killshot_c025_hpc.py` + 结果 `.../c025_deflation.csv`。
