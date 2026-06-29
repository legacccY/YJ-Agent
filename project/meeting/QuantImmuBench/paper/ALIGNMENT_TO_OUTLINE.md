# paper/ 现有成稿 → 袁老师 QuantImmu 框架 对齐说明

> 建档 2026-06-29。本档记录 `paper/` 下旧成稿（窄框架）与权威框架 `paper/QuanImmu-Paper-Outline.md`（袁老师定稿）的差距 + 待改清单。
> **本次任务（文档对齐）不重写 `main.tex` / `sections/*.tex` 正文**（量大，属后续 writer 编队执行）；本档只列差距与改法，供下一阶段动手。
> 数字红线：tex 改写时数字只用 `_scratch/ALIGN_FACTS.md` 已核值过 verifier；袁 md 声称值标待核。

## 1. 两套框架的关系

| | 旧成稿（`main.tex` + `sections/*.tex`，2026-06-26/27）| 袁 md 权威框架（QuanImmu-Paper-Outline.md）|
|---|---|---|
| 标题 | *Existing Neoantigen Immunogenicity Predictors Do Not Quantify T-Cell Response Magnitude: A Benchmark and the Case for Per-Patient Evaluation* | *QuantImmu: a quantitative, mutation-level framework for benchmarking and integrating neoantigen immunogenicity predictors* |
| 主角 | magnitude gap（现有工具做不了定量）+ per-patient 评估 | **QuantImmu 三步框架**（逐行打分→pooling→rank-fusion）|
| 工具数 | 8-9 跑通 | 30（10 呈递 + 20 免疫原性）|
| 数据 | 仅 ds2（+ ds1 少量） | 人 ds1/ds2 + 鼠 B16F10/CT26 |
| 核心实验 | 全局横评 + bootstrap CI + per-patient 聚合 | pooling 4 法 + fusion 12 法 + nested-LOPO + ablation + 删突变 robustness |
| 三层 results | 无（4.1-4.4 平铺）| §3.1 单工具 max 基线 → §3.2 单工具×pooling → §3.3 多工具 fusion+三重检验 |

**结论**：旧成稿 = 袁 md 框架的**一个子集**（≈袁 md §3.1 单工具 + §2.6 per-patient 协议 + §4 Discussion position）。不是另一篇，是袁框架内的部分章节。对齐 = 把旧成稿扩写进袁 md 的三层 + 三步范式结构，**框架以袁 md 为权威**。

## 2. 逐节差距 + 改法（待后续 writer 编队执行）

| 节（文件）| 现状 | 对齐袁 md 改法 |
|---|---|---|
| **title**（main.tex）| 窄 magnitude gap | 换袁 md ⭐候选 1：QuantImmu 框架名 + 三卖点（quantitative/mutation-level/30-tool）|
| **abstract**（0_abstract.tex）| gap + benchmark + per-patient | 改袁 md 4 段式（Motivation 错配 / Results=QuantImmu 三步+30 工具+人鼠 / Key findings=pooling 重排+geomean+持平 / Availability）|
| **1 intro**（1_intro.tex）| 能力阶梯 L1-L4 + magnitude gap | 保留 position 叙事，加袁 md 两个错配（二分类vs定量、肽层vs突变层）+ 第三 gap（缺统一定量系统评测）+ 三贡献 |
| **2 related**（2_related.tex）| 能力阶梯 taxonomy + 标签塌缩证据 | 保留，补 30 工具分类铺垫 + pooling 这一被忽视的方法学轴 |
| **3 setup**（3_setup.tex）| DS1/DS2 + 9 工具 + 七步 harmonization | 扩为袁 md §2：四数据集（补鼠）+ 30 工具表 2 + **三步范式 §2.3（核心方法学主体，新增）** + pooling 表 3 + fusion 表 4 + evaluation protocol（nested-LOPO/ablation/robustness）|
| **4 results**（4_results.tex）| 4.1 全局横评 4.2 敏感性 4.3 per-patient 4.4 proxy | 重构为袁 md §3 三层：§3.1 单工具 max（30 工具）→ §3.2 单工具×pooling（洗牌图，核心）→ §3.3 fusion+三重检验（geomean/nested-LOPO/ablation/robustness/显著性）→ §3.4 综合排名+部署 |
| **5 discussion**（5_discussion.tex）| 天花板 + magnitude gap + 局限 + QuantImmune | 保留，对齐袁 md §4：方法学要点（pooling/fusion 三轴）+ 为何 ρ≈0.4 有竞争力 + 诚实局限（整合持平/selection bias/n 小/外部验证）+ future work（HLA-II）|
| **6 conclusion**（6_conclusion.tex）| 三 claim 收束 | 换袁 md §5 Key Points 5 条 |
| **9 availability**（9_availability.tex）| 代码/数据声明 | 对齐袁 md §6：列关键脚本（含待补 nested-LOPO/robustness）+ DTU pending |
| **figures** | fig6-9（auc/spearman/roc/perpatient）| 补袁 md 主图：图 1 30 工具 max 基线（人/鼠）、图 2 pooling 洗牌、图 3 fusion 鲁棒性、图 4 统一排名、图 5 框架示意 |

## 3. 待改依赖（卡什么）
- Results §3.2/§3.3 扩写**依赖实验补齐**：fusion 扩 12 法、nested-LOPO、ablation、删 10/20% robustness（见 `reference/GAP_ROADMAP_vs_outline.md`）。**实验没补前，tex 这些节只能占位标 TODO。**
- 30 工具表 2 依赖工具补齐（缺 13）。
- 鼠数据章节依赖数据组提供 B16F10/CT26。
- 口径统一（92/8 vs 101/9 HLA-FIX 7）= 投稿前拍板点，定了才能锁 setup 表 1 数字。

## 4. 不做（本次范围外）
本次只建本档 + 各 md 档对齐；`main.tex`/`sections/*.tex` 正文重写 = 实验补齐 + 口径拍板后的后续 writer 编队任务。
