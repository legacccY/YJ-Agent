# 8tools Benchmark 深度重析

> 服务 quantimmu-bench。analyst(opus) 本地 pandas/scipy/sklearn 实算，2026-06-24。验证袁「组合最优」假设。
> 口径锁定(已三方对账)：指标=DS2 101 肽，肽级分数=max over 全部(HLA×Window_Size)子肽，标签=Elispot>0(90 正/11 负)。8 工具肽级 max-agg AUC 重算与 metrics_ds2_8tools.csv(max,>0) 逐工具精确吻合。
> 澄清：「8/9/10/11-mer」=滑窗子肽长度 Window_Size(8-14)，**不是**肽全长(DS2 全长肽 15-29mer)。现成 length_stratified_auc.csv 是 fallback 占位(非真分层)，本分析从 merged_all_tools_8tools.xlsx 逐子肽重算替代。

## 单工具总体 (max-agg/>0)
| 工具 | AUC(>0) | Spearman ρ |
|---|---|---|
| **pTuneos** | **0.7525** ← AUC 最优 | 0.1363 |
| PredIG | 0.6611 | 0.1983 |
| NeoTImmuML | 0.6551 | 0.0218 |
| IMPROVE | 0.6207 | **0.2434** ← ρ 最优 |
| ImmuneApp | 0.5889 | 0.0885 |
| PRIME | 0.5276 | 0.1163 |
| DeepImmuno | 0.4813 | −0.1168 |
| deepHLApan | 0.4188 | 0.0415 |

## (1) 肽长(Window_Size)分层 AUC
| 工具 | 8 | 9 | 10 | 11 | 12 | 13 | 14 |
|---|---|---|---|---|---|---|---|
| DeepImmuno | – | 0.513 | 0.477 | – | – | – | – |
| **PredIG** | 0.654 | 0.607 | 0.712 | 0.726 | **0.734** | 0.723 | 0.687 |
| IMPROVE | 0.637 | 0.601 | 0.651 | 0.550 | 0.687 | – | – |
| NeoTImmuML | 0.643 | 0.613 | 0.559 | 0.661 | 0.595 | 0.675 | – |
| **pTuneos** | 0.644 | **0.722** | 0.715 | 0.631 | 0.673 | 0.632 | 0.536 |
| PRIME | 0.527 | 0.547 | 0.535 | 0.541 | 0.568 | 0.548 | 0.480 |
| ImmuneApp | 0.577 | 0.616 | 0.558 | 0.552 | 0.575 | 0.606 | 0.613 |
| deepHLApan | 0.347 | 0.391 | 0.432 | 0.409 | 0.390 | 0.434 | 0.368 |
(– = 工具不支持该长度。DeepImmuno 仅 9/10mer，IMPROVE 限 8-12，NeoTImmuML 限 8-13)
→ **PredIG 中长肽(11-13mer)最稳(峰 12mer 0.734)，pTuneos 短肽(9-10mer)最强(0.722/0.715)**。各工具长度偏好不同 = 互补依据。

## (3) 两两 Spearman 相关(n=101)
| 对 | ρ | 解读 |
|---|---|---|
| IMPROVE+PRIME | **0.688** | 高度冗余(PRIME 是 IMPROVE 输入特征) |
| DeepImmuno+deepHLApan | 0.503 | 中度冗余 |
| PredIG+ImmuneApp | 0.419 | 中度相关 |
| NeoTImmuML+deepHLApan | **−0.161** | 最正交 |
| pTuneos+deepHLApan | −0.127 | 正交 |
→ 28 个对里只 IMPROVE+PRIME 一对高冗余，多数 ρ 在 ±0.3 内 = **普遍低相关，确有互补空间**。

## (4) Ensemble vs 单工具最优 ⭐
| 组合 | AUC(>0) | ρ | 对单工具最优 |
|---|---|---|---|
| 单工具最优 pTuneos | 0.7525 | – | 基准 |
| 单工具最优 IMPROVE | – | 0.2434 | ρ 基准 |
| **TOP3(pTuneos+PredIG+NeoTImmuML) rankmean** | **0.8146** | 0.1939 | AUC +0.062 ⚠️**不显著** |
| pTuneos+NeoTImmuML rankmean | 0.7985 | 0.1005 | AUC +0.046 |
| TOP4(+IMPROVE) rankmean | 0.7833 | **0.2505** | AUC +0.031 / ρ +0.007 |
| pTuneos+PredIG+IMPROVE rankmean | 0.7379 | **0.2780** | ρ +0.035 ⚠️不显著 |
| ALL8 rankmean | 0.6990 | 0.1883 | AUC −0.054(被弱工具拖累) |
| ALL8 zmean | 0.6556 | 0.2028 | AUC −0.097 |

## 关键发现
- **「组合最优」假设：部分成立但统计上证不实。** TOP3 rankmean AUC=0.8146 表面>pTuneos 0.7525(+0.062)，**但配对 bootstrap(2000 次,n=101)算 ΔAUC 95% CI=[−0.091,+0.230] 跨 0** → 提升不显著。pTuneos 单工具 CI[0.593,0.889] 与 TOP3 ens CI[0.688,0.917] 大幅重叠。结论：**DS2 90 正/11 负 n=101 上，ensemble 没统计意义跑赢单工具最优**，袁「组合最优」需更大样本，现有数据只能说「组合点估略高、方向一致、不显著」。
- **必须挑对工具组合，盲目全组合反而更差**：ALL8 任何组合(rankmean 0.699/zmean 0.656)都**低于** pTuneos 0.7525 —— deepHLApan(0.419)/DeepImmuno(0.481) 低于随机的工具进池直接拉低 AUC。组合增益只在「先按 AUC 选 top-3/4 强工具」时出现。
- **pTuneos 是 AUC 单冠，IMPROVE 是 ρ 单冠 —— 两指标挑出的最优工具不是同一个。** ensemble 小幅价值正来自这种互补(TOP4 ρ=0.2505、pTuneos+PredIG+IMPROVE ρ=0.2780 都比任一单工具 ρ 高)。

## 异常/风险
- **deepHLApan AUC=0.4188 低于随机 = 分数饱和塌缩，非 bug**(已 Bash 核分布)：肽级 max-agg 分布 count=98、mean=0.9768、中位 0.9932、min 0.8429 —— 98 肽绝大多数顶到 ~0.99 几乎无区分度；正肽均分 0.9760 反略低于负肽 0.9840(方向反)，ρ=0.0415 p=0.685。deepHLApan 对 DS2 这批肽全判「高免疫原性」天花板饱和。
- **DeepImmuno AUC=0.4813+ρ=−0.1168** 也弱：仅支持 9/10mer，max-agg 后两长度都≈随机，工具本身变长滑窗失配。
- **样本量/类不平衡 = 头号风险**：DS2 仅 11 负样本（Bash 核实分布：1 个 Elispot==0 + 10 个 Elispot<0 背景扣减负 SFC = 真无反应；阴性定义干净 = SFC≤0，非阈值人为切的弱阳）。所有 AUC/ρ 的 CI 都宽，ensemble 显著性测不出主因就是负例太少。
- **HLA 分层 n 太小**：56 allele 里只 9 个≥15 肽，极值(deepHLApan AUC=1.000、PRIME=0.059 在 n=18)是小样本噪声，不宜单独解读。

## 建议下一步
- **验「组合最优」需扩负样本**：11 负例撑不起 ensemble 显著性，要袁老师更多确认阴性肽把负例提到≥30 再重测 bootstrap CI 是否离 0。（⚠️ 不可纳 DS1 合并——DS1 全阳无阴性，合并只会让不平衡更糟，扩负例唯一正路是补真实 ELISpot 阴性肽。）
- **若坚持出 ensemble 结论，推荐 TOP4 rankmean(pTuneos+PredIG+NeoTImmuML+IMPROVE)**：ρ=0.2505 全表最优、AUC=0.7833 仅次 TOP3，4 工具长度覆盖互补，配套规则「先剔除 AUC<0.5 的 deepHLApan/DeepImmuno 再组合」。
- 做「按肽长选工具」路由 ensemble(短肽 pTuneos、中长肽 PredIG，length-aware 加权)。
- deepHLApan/DeepImmuno 报告里明确标「DS2 失配(饱和/长度受限)，不纳推荐组合」。

## 产物（图+csv）
- `analysis/figures_deepdive/fig_corr_heatmap.png` — 8 工具肽级分数 Spearman 相关热图
- `analysis/figures_deepdive/fig_length_strat_auc.png` — Window_Size(8-14mer) 分层各工具 AUC 柱(含 0.5 随机线)
- `analysis/figures_deepdive/fig_ensemble_vs_single.png` — 单工具 vs ensemble AUC 对比(红虚线 pTuneos 0.7525 基准)
- 衍生 csv：len_strat_auc_recomputed.csv / hla_strat_auc.csv / spearman_corr_matrix.csv / ensemble_results.csv
