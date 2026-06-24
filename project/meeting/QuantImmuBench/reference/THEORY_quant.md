# 定量强弱预测可行性理论论证

> 服务 quantimmu-bench（袁 QuantImmune）。theorist(opus) 半形式化推导，2026-06-24。kickoff(立项可行性+回报)+diagnose(失败三分流)。
> ⚠️ 纯生物学一阶推导+信息论上界估算，不含实验。多处天花板估算依赖未直接核到的 ground-truth 噪声参数，已标 TODO。「方差分解上限」视为**待验猜想**，不当定论卖。

## 一、形式化：把「magnitude 可不可预测」写成方差分解
观测反应强度 $Y$(ELISpot SFC/tetramer 频率)，输入仅「肽+HLA」$X$。可行性 = 条件方差能压多小：
$$\rho_{\max}^2 \le \frac{\mathrm{Var}(\mathbb{E}[Y\mid X])}{\mathrm{Var}(Y)}$$
右边是硬上界：纯肽+HLA 模型 ρ² 超不过它。全论证逐项估这个分式。

## 二、信号存在性：magnitude 由什么决定，哪些可从肽+HLA 推出
SFC ≈ N_precursor × p_recruit(avidity) × E_expansion × q_secrete（乘性扩增链）。逐因子：

| 因子 | 含义 | 决定方向 | 可从肽+HLA 预测? | 档 |
|---|---|---|---|---|
| ① binding affinity/presentation | 能否提呈 | 必要门槛但**饱和**(强结合≠强反应) | ✅ NetMHCpan/MHCflurry 强项 | 文献 |
| ② pMHC stability(半衰期) | 表面停留时长 | 正相关，比 affinity 更接近真信号 | ✅ 部分(NetMHCstabpan) | 文献 |
| ③ TCR-pMHC functional avidity | 招募哪些克隆/扩增多快 | **强决定** magnitude | ⚠️ 部分：取决宿主 TCR 库，肽+HLA 只定义靶面；可推「外来度/自体相似度」当代理 | 文献 |
| ④ naïve precursor frequency | 初始 T 细胞数 | **直接近线性**决定幅度(Jenkins/Moon) | ❌ **基本不可**：宿主 TCR 库+胸腺选择产物，同肽+HLA 跨供体差异巨大 | 文献 |
| ⑤ 抗原表达量/克隆性/处理 | 体内实际呈递量 | 正相关 | ❌ 体外加肽旁路，体内不可从序列推 | 推导 |

**判决（信号存在性）**：纯肽+HLA **存在**对 magnitude 的真信号但注定**部分**——头号驱动 precursor frequency 结构性缺席。不是「方向死」，是天花板被生物学锁在中等。突破须额外喂供体特异数据(TCR-seq/HLA 分型/precursor 估计) = 袁项目能否做增量的命门。

文献锚点：
- precursor frequency 近线性决定 magnitude — Moon Immunity 2007 + Jenkins&Moon J Immunol 2012(PMC3334329)。**袁项目最致命一条**。
- functional avidity 决定招募/扩增，阈值以上扩增有结构性随机 — Science Immunology 2025(adu6730)。
- affinity≠immunogenicity(饱和) — 多篇。
- 反应是连续谱不是二分 — arXiv 2511.18626 + T-SCAPE。**正面**支撑连续建模更对。

## 三、信息论上限：ground-truth 噪声把 ρ 天花板压到哪
ELISpot 噪声(最好情况，标准化后)：intra-assay CV≤7.4%、inter-assay≤17-22%、**inter-lab≤40%**(手工计数 26.7% vs 自动 6.7%)。袁数据若多源拼装大概率落上半段。
衰减公式 $\rho_{obs}=\rho_{true}\sqrt{r_{xx}r_{yy}}$。粗估(**⚠️低置信，量级演示**)：CV≈30% → r_yy≈0.92 → 单测量噪声压缩有限。真正吃天花板的是 §二结构性不可达方差(precursor+宿主库)，不靠多测消除。
→ ρ_max 量级估计落 **0.4–0.6**（对数尺度排序相关，低置信，TODO 待真实 magnitude benchmark 校准）。

**实测 IMPROVE ρ=0.320 接近上限还是远未到**：对照天花板 0.4-0.6，0.32/0.5≈0.64 即已达约 2/3，是「接近但未触顶」，还有 ~0.1-0.2 可榨，但不在「努力就能 ρ→0.8」的乐观区。
⚠️ **必须先 bootstrap ρ=0.32 的 CI**（DS2 阴性仅 11，CI 可能 ±0.15 甚至含 0）— 否则拿噪声点和低置信天花板比，双重不确定。

## 四、为什么现有工具止步二分：信号不存在(方向死) vs 数据不存在(可解)
- **解释 A（信号不存在→方向死）**：§二已证伪强版本(存在 ①②③代理真信号)；弱版本(信号有但太弱 ρ 永远<0.4)仍可能。
- **解释 B（缺连续 ground-truth→可解）**：证据强烈偏 B —— IMPROVE 训练数据=二分识别标签(17500 候选/467 识别)非 SFC 连续值，工具止步二分**因监督信号就是二分的**；文献明确呼吁转连续；袁的 ELISpot SFC 连续值正是稀缺资产。
- **判决**：现有工具止步二分**主要是数据/标签形状问题(B)**，非信号不存在，但叠加真实弱版 A(天花板被 precursor frequency 锁中等)。**对袁项目=方向可做(有连续标签是真资产)，但别承诺 ρ→0.8 颠覆性增益。**

## 五、预测回报：走通能到什么 ρ，增量在哪
| claim | 假设 | 可证伪预测 | 档 | 置信 |
|---|---|---|---|---|
| **C1** 纯肽+HLA 回归可达 ρ≈0.4–0.6 | ①②③代理占可观份额 | 多 benchmark ρ 稳定 0.4-0.6 且不随数据量涨(撞顶) | 待验猜想 | 低 |
| **C2** 加供体数据(TCR-seq)可破天花板到 ρ≈0.6–0.75 | precursor/avidity 可从供体 TCR 库部分估 | 喂 TCR-seq 模型 ρ 显著>纯肽+HLA | 待验猜想 | 低 |
| **C3** 连续模型对疫苗排序 top-K 优于二分 | 临床只能合成 top-K，排序质量=临床价值 | held-out 病人上连续模型 top-5 实测平均 SFC>二分 | 待验猜想 | 中 |

**回报判决**：最现实回报 = **C3(临床排序增量)+C1(坐实纯序列天花板)**，不需赌 C2。**建议袁项目 headline 押 C3(连续排序 top-K 优于二分，临床直接价值)，C1 当诚实天花板刻画，C2 标探索性 stretch goal 不当主承重。**
样本复杂度粗估：ρ 从 0.32 推到天花板 0.5 需 O(10³-10⁴)配对(肽,HLA,SFC)连续样本，且必须跨多供体多中心(否则学批次非生物信号)。

## 六、失败模式三分流（diagnose）
- **① 假设错(方向真空白)**：标签打乱重训若 ρ 仍≈真实 → 学的是批次/泄漏非生物信号(**最便宜先做**)；纯 affinity 单特征 ρ vs 全模型几乎不差 → magnitude 信号只剩饱和门槛。
- **② 实现错**：换 seed/split ρ 方差爆 → 样本太小或泄漏。**先 bootstrap ρ 的 CI**，含 0 则根本测不出 ρ，谈天花板为时过早(**第二便宜必做**)。变长滑窗特征对齐 off-by-one 也会稀释信号。
- **③ 数据不够**：ρ vs 样本量 learning curve 仍上升未饱和 → 加数据该涨，资源问题。
**三分流判决（当前最可能）**：基于 DS2 阴性仅 11、排名非显著、ρ=0.32 CI 未报，**当前最可能是 ②+③ 叠加(样本欠功效+ρ 未确权)，不是 ① 方向死**。最便宜下一步 = **bootstrap ρ=0.32 的 95% CI**(零 GPU)。

## 七、对袁项目理论建议
1. 目标方向成立但天花板诚实写(precursor frequency 缺席锁 ρ~0.4-0.6 低置信，别承诺 ρ→0.8)。
2. **headline 押 C3(临床排序增量)不押 C2(破天花板)**。
3. 动手前必做两件零成本：(a) bootstrap 现有 ρ=0.32 的 CI (b) 标签打乱对照(防泄漏假信号)。
4. 若破天花板，唯一理论路径=喂供体特异信息(HLA 分型已有/TCR-seq/precursor 代理)。
5. 数据是主矛盾，投入优先扩多中心连续 SFC 配对标注，非换更复杂架构。

## 八、命门定理
> 在「只给肽+HLA」约束下，magnitude 可解释方差上界被 **naïve precursor frequency 的供体特异性结构性封顶**(Jenkins/Moon 证近线性决定)，$\rho_{\max}^2 \le 1-\frac{\mathrm{Var}(precursor+宿主TCR库)}{\mathrm{Var}(Y)}$ 严格<1，缺口不随测量重复或样本量消除。
> 可证伪：若某纯肽+HLA 模型在跨供体 held-out 稳定达 ρ>0.7，则命门被推翻。
> 不值得 Lean 形式化（核心是经验生物学量+初等统计恒等式）。

## 九、残留 TODO
- TODO-1(verifier)：bootstrap IMPROVE DS2 ρ=0.32 的 95% CI（阴性仅 11，可能不显著）。**← 本轮主线已跑，见 04_LOG Entry 25 / analysis/bootstrap_ci_ds2.csv**
- TODO-2(researcher)：查 TESLA/T-SCAPE/DeepNeo 是否报过 magnitude 连续回归 R²/ρ（非二分 AUC），替换 §三§五低置信天花板估计。
- TODO-3(researcher)：查 ELISpot SFC 方差分解(生物变异 vs 供体 vs 测量占比)。
- TODO-4：§3.2 CV→r_yy 映射是粗糙近似，袁真实数据噪声结构需复孔/重测实算。

## 一句话判决
**方向可行但回报封顶**：连续 magnitude 目标生物学成立(现有工具止步二分主要是标签形状问题 B 非信号被证伪)，但纯肽+HLA 的 ρ 天花板被 precursor frequency 供体特异性结构锁在中等(粗估 0.4-0.6 低置信)；当前最大理论风险=拿 CI 未确权的 ρ=0.32(DS2 阴性仅 11)谈天花板。动手前先 bootstrap CI+标签打乱两件零成本对照。

### 引用
- Jenkins&Moon J Immunol 2012 PMC3334329 / Moon Immunity 2007 — precursor frequency 近线性决定 magnitude
- Science Immunology 2025 adu6730 — avidity 阈值+随机扩增
- ELISpot 可重复性 — Cells 2015 PMC4381207 / BMC Immunol 2017 PMC5339961 / PMC3990961
- IMPROVE PMC11021644 / TESLA Cell 2020 / PredIG 10.1186/s13073-025-01569-8
