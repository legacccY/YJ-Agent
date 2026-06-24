# QuantImmune 退守路线决策综述（给徐伊琳/袁老师拍板）

> 服务 quantimmu-bench / QuantImmune 方向。本窗（route-ordinal-retreat）2026-06-24 派 4 路 opus 编队（planner 矩阵 / researcher 先例撞车 / theorist 回报 / skeptic 红队）综合产出。caveman OFF。
> 触发：原连续 magnitude 回归路线 Phase0 命门倾向 FAIL（`PHASE0_iedb_fillrate.md`）。本档评估退守路线 + 推荐 + 拍板点。
> ⚠️ **claim 形状回退方向 = 命中率回退方向 = 拍板点**，本档只呈证据+推荐，最终由袁老师/徐伊琳定，不擅自改。

---

## ⭐ 一句话决策（最关键）

**四路线候选 A（序数三档）/ B（响应频率）/ C（自补 ELISpot）/ D（纯 benchmark），四方编队收敛到同一推荐：**
> **押 D（现有工具定量能力 benchmark 论文，不做新工具）为主路 + A/B 简单 baseline 当 contribution + C 缩成跨供体 held-out 评测金标准；同时把 claim 形状从「novel method」降到「benchmark/empirical」。**

核心理由三条：
1. **退守不绕开命门**（theorist 定理级）：序数/频率/自补三条都受同一个 precursor frequency 天花板封顶（换指标不换地基，下详）。退守不能靠「换 Y 编码」抬天花板。
2. **A/B 都有撞车/塌缩风险**：响应频率 = DeepImmuno 已占（🔴 撞车）；序数三档 = 半蓝海但 DeepImmuno 已用序数先验、且离二分太近 novelty 缩水。
3. **D 承重前提最少、证据在手、符合死活对照**：benchmark 族全活（memory `benchmark_is_optimal_strategy`：quantimmu/ArtiOOD/selinf 全活，A 族大胆 novelty 全死）。

---

## 一、退守不绕开命门（theorist 定理级，全文支点）

命门定理（序数版）：在「只给肽+HLA」约束下，序数化 Y₃=g(Y)（g 保序）后，
$$\tau_{\max}(X\to Y_3) \le \frac{2}{\pi}\arcsin\rho_{\max} < \frac{2}{\pi}\arcsin(0.6)\approx 0.41$$
- **rank 统计量对单调变换不变** + **数据处理不等式** 双重锁死：序数化只动 Y 侧编码，补不回 X 侧缺失的 precursor frequency 信息。
- 命门天花板 ρ_max≈0.4-0.6 经换算 = **τ_max≈0.26-0.41 / Spearman≈0.39-0.58 / QWK≈0.35-0.52**（双正态近似，量级待真实分布校准 TODO）。
- **核心警示**：把「序数 τ≈0.3 天花板」误读成「比连续更宽松的新天花板」= SelInfBench「参数恒等式伪装成发现」同构坑。换指标 ≠ 换地基。
- **自补 ELISpot（C）也不绕命门**：解决 GT 数量（Phase0 数据墙）不解决信息上界——自补再多连续 SFC，X 里仍无 precursor frequency，ρ_max 纹丝不动。自补价值 = 把 ρ 从 0.32 推向天花板 0.5，**不是把天花板抬到 0.8**。唯一抬天花板路径仍是喂供体特异信息（HLA 分型/TCR-seq）。

## 二、四路线对比表

| 路线 | 监督信号 | GT 可得性 | 撞车 | 新颖性 | 理论天花板 | 承重前提 | 综合判 |
|---|---|---|---|---|---|---|---|
| **A 序数三档** | IEDB/CEDAR positive-high/-int/-low | 字段系统存在，**纯癌子集量 TODO** | 🟡 半蓝海（DeepImmuno 用了序数先验，没人当 ordinal target 显式做） | 中（离二分近，缩水） | τ≈0.26-0.41/QWK≈0.35-0.52 | 中（纯癌三档 ≥10³ 未实测，中间档可能塌） | 🟡 可走，须定位 benchmark 非 novel 方法 |
| **B 响应频率** | responded/tested（beta-binomial） | DeepImmuno 取 9056（≥4 subject filter），**纯癌子集量 TODO** | 🔴 **DeepImmuno 已占** | 弱 | 比 A 更糙（sigmoid 投影） | 高（$\hat\pi$ 与 SFC **实证可解耦** B4 红旗 + 偷换问题定义） | 🟡 仅辅助标签，不当主承重 |
| **C 自补 ELISpot** | 自产连续 SFC | 需自产 ≥10³ 跨供体 | 🟢 低 | 同连续 | **天花板不变 ρ≈0.4-0.6** | 最高（wet-lab 人年级+多中心+天花板锁死） | 🔴 当训练路负回报；缩成评测小集 🟢 |
| **D 纯 benchmark** | 不做新工具，系统测现有工具定量能力 | **证据在手**（8tools 已部署+ρ=0.32 已测） | 🟢 最低（无系统定量 benchmark） | 中（第一个系统化定量 benchmark） | N/A（不押建模） | **最少** | ✅ 最稳，BMVC 一次过形状 |

**新颖性排序**：连续 SFC（干净蓝海 unaddressed gap）> 序数三档（半蓝海）> 响应频率（撞 DeepImmuno）。
**理论回报排序**（若做新工具）：A 序数三档 > C 自补 > B 频率。

## 三、推荐路线（四方共识）

**D 主路 + A/B baseline + C 评测集，claim 形状降到 benchmark/empirical：**
- **headline**：「现有 N 个免疫原性工具的定量（序数/响应频率/排序）能力系统 benchmark + 诚实天花板刻画 + 一个简单强 baseline + 跨供体评测集」。窄、可观测、承重前提全在手。
- **训练量**用公开源（IEDB 序数/响应频率）撑；**评测**用自补的干净跨供体小集（~100-200 肽，复用 Wave3 ELISpot 管道）。
- **A/B 当 D 内部的 baseline contribution**（锦上添花非承重）：baseline 真超 binding proxy → 升级方法论文（进可攻）；不行 → 纯 benchmark（退可守）。这把单点押注变成选择权。
- **避坑**：退守后**别再押「第一个定量回归工具」当 headline**（= 把退守又包装成大胆 claim，重蹈 A 族难产）。退守正确姿势 = 同时把 claim 形状从 novel method 降到 benchmark，不只换标签粒度继续押 novelty。
- **区隔 DeepImmuno**（B 必做）：related work 写清「DeepImmuno 用 responded/tested 做二分 AUC，我们首次报连续 ρ/MAE + 临床 top-K 排序」。

## 四、🛑 拍板前 0-GPU 命门核查（<2h，拍板前必做，否则在 TODO 上拍板）

拉 IEDB `tcell_full_v3.csv` 一次性核三件事（K0' kill-shot）：
1. **肿瘤子集 `Positive-Intermediate` 序数档记录数 + 跨 PMID 数** → 判 A 是否退化二分（中间档是序数信号所在；若 <100 则序数=换皮二分，A 与连续路死于同一根因）。
2. **肿瘤子集 `Number of Subjects Tested ≥4` 的 (peptide,HLA) 去重数 + responded/tested 直方图** → 判 B（≥10³ 且中间值 0.2-0.8 占比 >20% 才不退化二分；neoepitope 患者私有突变 → ≥4 独立受试者测同一肽在肿瘤侧可能极稀疏）。
3. **连续 SFC 填充率**（原 Phase0 残留）→ 同一份表三个 value_counts 一起出，给连续/序数/频率三答案。
> ⚠️ **陷阱**：IEDB 两种 high/int/low——(a) MHC binding IC50 分档 vs (b) T-cell assay `Assay Qualitative Measure` 定性测量。退守要用 **(b)**，别混入 (a)（researcher 已踩一次）。

## 四'、命门核查实测结果（2026-06-24 已跑，授权后）

主线下 IEDB tcell_full_v3（1.33 GB）实跑 `analysis/phase0_fillrate_check.py`（结果 `analysis/phase0_fillrate_actual.csv`）。**IEDB 573,409 行，肿瘤子集 50,384**：

| 路线 | 肿瘤子集实测 | 判定 |
|---|---|---|
| 连续 SFC | quantitative 非空 **455**(0.9%) <10³ | 🔴 **FAIL 实证坐实** |
| A 序数三档 | high 472+int **160**+low 1545=2177 跨 35-316 PMID | 🟡 CONDITIONAL PASS（总够，中间档 160 薄→实质可能退化 high-vs-low 二档） |
| B 响应频率 | ≥4-tested **3813**，中间值 0.2-0.8 占 **32.4%** | 🟢 **PASS（量最足、不退化二分）** |

**反转**：实测 B 最足（推翻"纯肿瘤稀疏"预判）。但 B 撞 DeepImmuno（正用此字段）+ theorist B4 红旗（与 SFC 解耦）。**scope caveat**：肿瘤子集含共享抗原（NY-ESO/MAGE/病毒相关），限真私有 neoepitope 则 B 大幅缩水（待 Antigen 二次过滤）。

→ **数据可得性 B>A>连续，但「数据足≠claim 好」。推荐不变：D benchmark 主路最稳（不依赖单一路线数据够）。** 若做新工具序数路线 A 可走（中间档薄需注意）。

## 五、序数实验体系（若走 A，详见 EXPERIMENT_MATRIX_ordinal_retreat.md）
- **指标**（学界规范不自创阈值）：主 Quadratic Weighted Kappa（DR grading 标准，substantial 0.61-0.80）+ 排序 Kendall τ/Spearman ρ（pMHC benchmark 范式）+ 序数 AUPRC per-threshold + ISSR top-K。合格绝对阈值 TODO researcher，相对判据（超 binding baseline）是硬的。
- **方法+官方实现**：CORN/CORAL（github Raschka coral-pytorch，含 tabular MLP 教程，小样本可用，rank-consistent）+ ordinal logistic（mord）+ beta-binomial（B 路）。建议叠 ranking loss（路线 D' pairwise，对跨 study 批次更鲁棒）。
- **防泄漏四层**：peptide+4 位 HLA 去重 + leave-study-out + homology reduction + 量化 overlap%；序数离散化阈值在 train fold 内定不可用全集分位。
- **标签打乱对照**：序数头打乱 GT 重训应崩到随机（防泄漏命门）。

## 六、拍板点（呈袁老师/徐伊琳）
1. **claim 形状**：D 纯 benchmark（推荐）/ A 序数方法 / B 频率 / C 自补 —— 命中率回退方向，呈定。
2. 拍板前先跑第四节 0-GPU 命门核查（A/B 可行性确权）。
3. C 自补 ELISpot 的产能：现成 3 个月能产多少跨供体配对？<300 则当训练路不可行、当评测补强可行。
4. TESLA Synapse/MTA + TCR-seq 对外数据获取 = 拍板点。

## 七、TODO（不臆想）
- 纯癌 neoepitope 序数三档/响应频率跨 study 是否 ≥10³（第四节核查，A/B 命门）。
- 序数指标合格绝对阈值（QWK>0.4 是否学界通用、τ-b 并列处理）+ 连续 ρ→序数指标天花板精确映射（双正态假设对 log-SFC 重尾不严格，需真实 copula 数值积分）。
- B4 红旗实证强度：responder fraction 与 SFC magnitude 解耦是个案还是系统性。
- 隐藏撞车点 bioRxiv 2022.07.05.497667（用了 Positive-High/Int/Low，待人工核是 ordinal 还是 collapse）。
- IMPROVE/PredIG/BigMHC/CORN 官方超参查不到标 TODO。

## 引用
- DeepImmuno PMC7781330（响应频率回归+序数先验先例，≥4 subject filter）
- explorationpub 2024 (10.37349/ei.2023.00091)（连续 magnitude unaddressed gap）
- CEDAR PMC9825495（序数三档字段）/ 2025 neo-epitope meta CancerImmunolImmunother（CEDAR 16k neo-peptides/180 studies 量级）
- CORN arXiv 2111.08851 / coral-pytorch（github Raschka）
- QWK DR grading（substantial 0.61-0.80）；Kendall τ pMHC benchmark PMC6224037
- 命门定理：本项目 THEORY_quant.md + Jenkins&Moon 2012（precursor frequency）
