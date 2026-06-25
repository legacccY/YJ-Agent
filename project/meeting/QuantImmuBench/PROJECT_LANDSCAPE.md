# QuantImmuBench 项目全景与决策综述

> 致袁老师 · 余嘉整理 · 2026-06-24
> 本文整合本轮 8 人调研编队（工具普查、数据集普查、benchmark 方法学对标、红队审计、理论可行性论证、本地深度重析）的全部产出，目标是一页纸看懂「现状 + 蓝海 + 命门 + 建议」，供您对 QuantImmune 立项方向拍板。
> 所有关键数字均经本地 csv 核对，文献结论均带来源；不确定项一律显式标注，未掩盖盲区。

---

## 1. 一句话现状

余嘉子任务（HPC 部署测试 + 信息收集）已基本成型：**10 个新抗原免疫原性工具完成部署测试，其中 9 个进入统一 benchmark** —— 8 个免疫原性工具 apples-to-apples 对比（pTuneos、PredIG、IMPROVE、NeoTImmuML、ImmuneApp、PRIME、DeepImmuno、deepHLApan）+ HLAthena 1 个 presentation proxy 单列（预测提呈非免疫原性，ELISpot 上近随机 AUC 0.51，正面印证「提呈≠免疫原性」）；唯一 MHLAPre 判为不可复现（无权重+预处理码缺）未做成。约定的四类信息（工具能力 / 数据需求 / 性能表现 / 部署难度）已采集，PPT（17 slide）+ Word 报告成稿。本综述即在此之上回答「下一步该往哪走」。
> 进度数字真源 = `DEPLOY_TRACKER.md` 顶部规范状态总表 + `analysis/metrics_ds2_9tools.csv`。

---

## 2. 八工具 Benchmark 的诚实结论（保守版，可直接进 PPT）

测试集为本地 ELISpot Dataset2（DS2，101 条肽，90 阳 / 11 阴；标签按 ELISpot SFC > 0 切分）。结论刻意取**保守且防弹**的版本——它比激进版更站得住，也更有利于您的立项动机。

- **现有工具判别力普遍偏弱，且彼此统计上不可区分。** AUC 最优点估为 pTuneos 0.7525，但 2000 次 bootstrap 95% CI = [0.598, 0.888]，宽达 ±0.15；排名第二的 PredIG（0.661）、NeoTImmuML（0.655）、IMPROVE（0.621）的 CI 均与之大面积重叠，且除 pTuneos 外的工具 CI 下界都跌破 0.5（随机线）。**根因是阴性样本仅 11 个**，少数类主导了不确定性，任何「最优工具」的强排序语言都不成立。
  > ⚠️ 措辞红线：避免对外说「pTuneos 0.78 最优 / 最强」。那个 0.78 是「单一聚合 × 单一阈值 × 11 阴性」三重最优角落的脆弱点——同一工具换 >median 阈值后 AUC 掉到 0.46（低于随机），不是稳健能力。诚实表述为「现有工具在本 ELISpot 集判别力普遍弱，无统计显著最优工具」。

- **第二批新纳入的 3 个工具（PRIME、ImmuneApp、deepHLApan）相对第一批无增量。** 在全部聚合 × 阈值组合下，没有任何一个超过第一批的最优点估；该结论不依赖排名精度，且 IEDB 泄漏方向（多数工具用 IEDB 训练）只会让分数虚高、对「无增量」结论顺风，故稳健可保留。

- **定量强弱（magnitude）能力整体很弱。** 预测分与 ELISpot 实测值的 Spearman 相关，本地 DS2 实测最优仅 IMPROVE ρ = 0.24（文献中 IMPROVE 在自有大集上报 ρ ≈ 0.32）；多数工具 ρ 在 0 附近。这恰恰说明：**现有工具几乎没有为"预测反应强弱"而设计**——这正是下一节蓝海的由来。

- **组合（ensemble）点估略高但不显著。** TOP3 排序均值 AUC = 0.815 表面高于单工具 0.7525（+0.06），但配对 bootstrap ΔAUC 的 95% CI = [−0.091, +0.230] 跨 0，证不实。且盲目把 8 个全组合反而更差（被低于随机的 deepHLApan / DeepImmuno 拖累）。「组合最优」目前只能说「点估略高、方向一致、不显著」，需扩负样本才能验证。

---

## 3. ⭐ 蓝海机会（QuantImmune 立项的核心支撑）

**预测 T 细胞反应"强弱"（response magnitude，对 ELISpot SFC 这类连续量做回归）是学界公认尚未填补的空白，且不撞车。**

- 多源独立证据指向同一结论。2024 年专题综述（Exploration of Immunology, DOI 10.37349/ei.2023.00091）直接写道：*"No tool in this review was explicitly developed to predict T cell response magnitude... Magnitude prediction remains an unaddressed gap."* 我们逐一核验了所有自称"定量"的工具：PRIME 官方 README 自认其分数"非 quantitative response magnitude，只是排序指标"；ICERFIRE 作者主动把量级标签"塌缩成单一二分类"；neoIM 虽专为 ELISpot 设计仍做分类；T-SCAPE(2025) 是最接近的 SOTA 但仍输出二分概率。**真正对反应强弱做连续回归的工具 = 0 个。**

- **但"蓝海"有附加条件——差异化必须真正落在连续标签上。** 必须使用**真连续的 ELISpot SFC 标签 + 报告 r / ρ / MAE 等回归指标**；否则一旦退化成又一个二分类器，就立刻失去与 T-SCAPE / NeoTImmuML 的区隔，蓝海塌缩成红海。

- 撞车防御的唯一真实攻击点：审稿人会把 NetMHCpan / MHCflurry 的连续结合亲和力（BA, nM 值）当作"已有定量 baseline"质疑。**对策：把 binding affinity proxy 设为对照基线，并证明对 ELISpot 量级的回归显著优于它**（文献实测 binding 与 ELISpot 量级仅弱相关，这一关可过）。

---

## 4. ⚠️ 命门 / 立项前必须先验证的前提

**最大的结构性风险是：想做回归，却可能没有足够的连续标签作 ground truth。**

- 绝大多数公开新抗原数据集是二元标签（PRIME / NEPdb / dbPepNeo2 / NeoTImmuML / harmonized 全 binary），做不了回归。
- **唯一系统性带定量 magnitude 字段的公开源 = IEDB 及其癌症子库 CEDAR**（schema 明确同时记录 qualitative 与 quantitative，含 ELISPOT SFC / % tetramer 等）；**TESLA** 原文有逐肽 tetramer 频率（按强弱排序的金标准设计），但不在简易表格公开下载（测序在 Synapse、需 MTA，二手库多已降为 binary）。

> 🔴 **立项前的零成本必做项：核实 IEDB / CEDAR 的 magnitude 字段实际填充率。** 很多记录可能只有 pos/neg 而无连续值——**若 quantitative 列实际填充稀疏、且 TESLA 补充表不含连续列，则"想做回归但无连续标签"会直接塌缩立项。** 这件事必须在投入模型与算力之前先做掉（只需导出几个字段统计填充率）。退路：若公开源不足，则退守"序数强弱分级"或自补 ELISpot 标注。

- 即便 IEDB 可用，仍有两个工程坑须正视：① assay 高度异质（不同实验室 SFC 不可比、未归一化），raw SFC 跨研究回归噪声极大，需按 assay 类型分层 + 研究内归一化；② IEDB 本身是多数工具的训练源，benchmark 必须做序列去重 + leave-study-out 防泄漏。

---

## 5. 理论天花板的诚实预期（避免过度承诺）

理论侧（方差分解 + 信息论上界）给出一个对外承诺时必须守住的红线：

- **纯"肽 + HLA"输入对 magnitude 的可解释方差被生物学结构性封顶。** 决定反应强弱的头号因子是 naïve precursor frequency（初始 T 细胞克隆数），它近线性决定幅度（Jenkins & Moon 2012），却由宿主 TCR 库与胸腺选择决定，**无法从肽 + HLA 序列推出**。叠加 ELISpot 测量噪声（inter-lab CV 可达 40%），ρ 天花板粗估落在 **0.4–0.6（低置信，待真实 benchmark 校准）**。

- **因此请勿承诺颠覆性增益（如 ρ → 0.8）。** 文献实测 IMPROVE ρ ≈ 0.32 已达估计天花板的约 2/3，是"接近但未触顶"，仍可榨 0.1–0.2，但不在"努力就能到 0.8"的乐观区。要破天花板，理论上唯一路径是额外喂入供体特异信息（HLA 分型 / TCR-seq / precursor 代理），属探索性 stretch goal，不宜当主承重。

- **建议 headline 押"临床 top-K 排序增量"（理论编号 C3）**：连续模型在 held-out 病人上的 top-K 推荐质量优于二分类——因为临床只能合成 top-K 肽，排序质量直接等于临床价值。这条不需要赌破天花板，是最现实、最可证伪、也最有临床说服力的卖点。把"坐实纯序列天花板"（C1）当作诚实的能力刻画，把"喂供体数据破天花板"（C2）标为探索性目标即可。

---

## 6. 下一步建议清单（请您拍板）

| # | 行动 | 成本 | 状态 | 用途 |
|---|---|---|---|---|
| ① | **核实 IEDB / CEDAR 的 magnitude 字段实际填充率**（+ 核 TESLA 补充表是否含连续列） | 零算力，数日 | 待启动 | **立项命门**：决定 magnitude 回归到底有没有连续 ground truth，做不了就别立 |
| ② | benchmark 主指标补 **AUPRC + top-K 命中率(ISSR/PPV@K) + 与各工具训练集的 overlap 量化**，ROC-AUC 仅作辅助 | 低，纯重算 | 待补 | 对齐学界规范（IMPROVE / PredIG 标准），防极端类不平衡下 ROC-AUC 误导，防泄漏攻击 |
| ③ | **扩充负样本 / 补连续标注**（DS2 仅 11 阴，把负例提到 ≥ 30 再重测） | 中，需新数据 | 待启动 | 让"组合最优"与定量回归的显著性真正测得出 |
| ④ | bootstrap 95% CI（AUC 与 ρ） | 零算力 | **已完成** | 已坐实"判别力统计不可区分"，结果见 `analysis/bootstrap_ci_ds2.csv` |

**一句话决策建议**：八工具 benchmark 的诚实结论（现有工具判别力普遍弱、统计不可区分、新工具无增量、定量能力弱）不仅站得住，反而**强化了 QuantImmune 做连续 magnitude 回归的立项动机**。但立项之前，请务必先做掉清单第 ① 项——它是整个方向的命门开关。

---

### 附：来源索引

- 工具普查与撞车扫描：`reference/LANDSCAPE_tools.md`（核心证据 explorationpub 2024, DOI 10.37349/ei.2023.00091「unaddressed gap」）
- 数据集普查：`reference/LANDSCAPE_datasets.md`（CEDAR PMC9825495 / IEDB / TESLA）
- benchmark 方法学对标：`reference/BENCHMARK_METHODOLOGY.md`（IMPROVE PMC11021644 / PredIG 10.1186/s13073-025-01569-8）
- 红队审计：`reference/REDTEAM_benchmark.md`（🔴-1 pTuneos「最优」统计不可区分）
- 理论可行性：`reference/THEORY_quant.md`（precursor frequency 锁 ρ ~ 0.4–0.6；Jenkins & Moon 2012 PMC3334329）
- 本地深度重析：`analysis/DEEPDIVE_8tools.md` + `analysis/bootstrap_ci_ds2.csv`
