# QuantImmune 序数退守路线实验矩阵

> planner(opus)，2026-06-24，服务 quantimmu-bench / QuantImmune 方向（帮徐伊琳/袁老师，余嘉配合不主导）。只设计不写码不跑。caveman OFF。
> 触发：原连续 magnitude 回归 Phase0 命门倾向 FAIL（`PHASE0_iedb_fillrate.md`）。本矩阵把 claim 退守为「序数分级/响应频率回归」。决策综述见 `RETREAT_ROUTE_ordinal.md`（推荐 D benchmark 主路；本档是若走 A 序数方法的详细矩阵）。
> 与原连续矩阵 `EXPERIMENT_MATRIX_quantimmune.md` 并列保留，不覆盖。

## 0. 退守 claim 形状（推荐：A 保底 + B 升级 + C 连续 stretch）
| 形状 | 信号 | GT 可得性 | 判断 |
|---|---|---|---|
| **(A) 序数三档**(high/int/low) | IEDB/CEDAR 序数标签 | 混合源 ≥10³，纯癌 TODO | **主推**，指标成熟，地基最接近够用 |
| **(B) 响应频率**(beta-binomial) | responded/tested | DeepImmuno 取 9056(≥4 subject) | 并列/可融合，频率信息量大但纯癌量 TODO + 撞 DeepImmuno |
| **(C) 连续 SFC** | 数值 SFC | 肿瘤正例 10¹-10² FAIL | 降 stretch，仅小集 held-out 探针 |
> A vs B：B(频率)理论更优(真连续+beta-binomial 正确建模小分母方差)，但前提=纯癌 tested/responded 填充率够(比序数更不确定)。**设计成 A 保底、B 升级**：Phase0' 同时核 A/B 填充率，B 够则升 B。

## 阶段依赖图
```
Phase0'(序数/频率 GT gate,~0GPU) ─PASS─► Phase1'(baseline 序数化) ─► Phase2'(序数/频率回归) ─► Phase3'(跨供体验证)
   └─FAIL(纯癌<10³/单study)─► 混合源 proof-of-concept + 标缺口 / 自补 ELISpot(拍板)
```

## Phase 0' — 序数/频率 GT 填充率核查（新承重前提，命门 gate，0 GPU）
⚠️ 核的是与连续 SFC **独立的字段**（序数三档标签 + tested/responded 计数），不能复用原 Phase0 结论。
| run | 对象 | 操作 | 判据 |
|---|---|---|---|
| P0'-1 | IEDB `Assay Qualitative Measure` 序数列 | 肿瘤子集统计 high/int/low 各档非空 + 跨 PMID | 纯癌三档 ≥10³ 且 ≥2 study，中间档不退化 |
| P0'-2 | IEDB tested/responded | 肿瘤子集两者均非空配对数 + tested 分母分布 | (B)≥10³ 且 tested 中位 ≥TODO(beta-binomial 最小分母查文献) |
| P0'-3 | CEDAR 全库 | 解析序数+计数非空，去重净增量 | 计入总量 |
| P0'-4 | TANTIGEN 4 级序数 | 核肿瘤抗原序数标签是否 magnitude 强弱 | magnitude 则计入，否则标"非 magnitude" |
| P0'-5 | 本地 DS1/DS2 | SFC 按学界三档阈值离散化统计各档数 | 确认 DS2 仅 101 肽当 held-out 不进训练 |
| P0'-6 | TESLA mmc | 核 per-peptide tetramer 频率列(可离散化 held-out) | 含=干净 held-out；Synapse/MTA 对外=拍板点 |
- **PASS(A)**：纯癌序数 ≥10³ 跨 ≥2 study + 三档不极度退化(最小档占比 ≥TODO%)。**B 额外**：频率 ≥10³ + tested 分布支持 beta-binomial。
- **FAIL**：混合源(病毒+癌)proof-of-concept + 标缺口 / 自补 ELISpot(拍板)。
- **⚠️ 陷阱**：用 `Assay Qualitative Measure` 的 T-cell 定性 high/int/low (b)，**别混 MHC binding IC50 分档 (a)**。
- **K0' kill-shot(0 算力第一动作)**：`value_counts` IEDB 肿瘤子集序数三档；与 K0(连续) + 频率三个 query 一份表一起跑，凑不出当场证伪。
- 算力 ≈0 GPU·h(~2-4h CPU)。

## Phase 1' — baseline 序数化复刻（SOTA 序数排序天花板 + 撞车对照）
转换逻辑：现有工具输出连续分/二分概率，**没一个直接输序数**。复刻 = 取连续分按与序数 GT 单调排序关系评(序数/排序指标)，**不重训成序数头**(零偏离红线)。
| run | 被试 | 复刻 | 判据 |
|---|---|---|---|
| P1'-1 | NetMHCpan 4.1 BA | 连续 BA→排序 vs 序数 GT | **撞车靶**：序数模型必须显著超它 |
| P1'-2 | MHCflurry 2.0 BA | 同 | 撞车靶 |
| P1'-3~7 | PRIME/BigMHC/IMPROVE/PredIG/neoIM/T-SCAPE | 连续分→排序(官方超参 TODO) | SOTA 候选 |
| P1'-8 | IEDB Immunogenicity | 单分→排序 | 地板 baseline |
| **P1'-CTRL** | 标签打乱 | 序数 GT 置换重评 | **防泄漏命门**(真工具序数指标须显著>打乱) |
- **指标**(学界规范不自创阈值，带 bootstrap CI)：Spearman ρ(Beyond MHC binding 范式) + Kendall τ(TODO 核 τ-b 并列) + **QWK**(DR grading 金标准，TODO 核合格区间) + 序数 AUPRC per-threshold + ISSR/PPV@top-K(high 档排进 top-K)。
- **撞车判据**：序数模型(Phase2')须 ≥1 序数指标 CI 下界显著超 binding baseline CI 上界。
- 防泄漏四层：peptide+4 位 HLA 去重 + leave-study-out + homology reduction + 量化 overlap%。
- **K1' kill-shot**：先只跑 P1'-1(BA)+CTRL，BA 序数 ρ 已接近所有工具上限/打乱不归零 → 信号全在 binding 门槛或泄漏，当场暴露。
- 算力 ≈2-5 GPU·h。

## Phase 2' — 序数/频率回归模型（headline 主战场）
序数头：CORN/CORAL(rank-consistent，A 首选，github Raschka coral-pytorch tabular 教程) / ordinal logistic(mord，轻量 baseline) / beta-binomial(B 路，正确处理小分母)。
| run | 输入特征 | 头 | 判据 |
|---|---|---|---|
| P2'-A0 | 肽+HLA(最小,C1'基线) | CORN | 超 binding baseline? |
| P2'-A1/A2 | +stability/+avidity 代理 | CORN | C1' 消融 |
| P2'-A3 | 全代理 | CORN | **C1' 主读数：序数排序显著超 binding baseline?** |
| P2'-A3' | 全代理 | ordinal logistic | 头敏感性(换头结论应不变) |
| P2'-B0 | 全代理 | beta-binomial 频率 | **B headline(若 P0'-2 PASS)**；与 A3 同向=自洽 check |
| P2'-C2 | +供体 TCR-seq(stretch,对外=拍板点) | CORN | C2 探索不当主承重 |
- 对照：binding proxy baseline(撞车线)、二分工具 top-K vs 序数 top-K(C3' 核心)、标签打乱、A/B 一致性 check。
- **C1' PASS**：P2'-A3 ≥1 序数指标 CI 下界 > binding baseline CI 上界(绝对合格阈值 TODO，相对判据硬)。**C3' PASS(headline)**：held-out 病人序数 top-K 高档命中显著>二分工具。
- 离散化阈值在 train fold 内定(不用全集分位防泄漏)。
- **K2' kill-shot**：先 P2'-A0 vs P1'-1，最小模型序数排序≈BA 且加代理零增益 → 信号全在 binding 门槛撞车守不住，停报。
- 算力 ≈20-50 GPU·h(序数头比连续收敛快)。

## Phase 3' — 跨供体验证
| run | 内容 | 判据 |
|---|---|---|
| P3'-1 | 跨供体 leave-donor-out | **命门定理可证伪点**：跨供体序数 Spearman 稳定>0.7/τ>0.55 则推翻天花板。预期<该值 |
| P3'-2 | 真实临床比例(1-6% high 档)+平衡集对照 | 双报(结论会翻转) |
| P3'-3 | learning curve(序数指标 vs 样本量) | 区分天花板撞顶 vs 数据不够 |
| P3'-4 | TESLA/本地 DS 连续探针(C stretch) | 质性验证(样本小不承诺功效)，桥接连续 magnitude 叙事 |
- 算力 ≈2-15 GPU·h。

## 全局算力：Phase0' 0 GPU(命门 gate) → Phase1' 2-5 → Phase2' 20-50 → Phase3' 2-15 = **~25-70 GPU·h**(PASS 后才花，比连续略省)。

## 承重前提（命门，最先验）
1. 🔴 **新命门**：IEDB/CEDAR **纯癌子集**序数三档(A)+响应频率(B) ≥10³ 跨 ≥2 study(与连续独立字段，未核前不投 Phase1'+)。
2. 🔴 **撞车守得住吗**：序数模型须显著超 binding baseline(K2' 暴露)。
3. 🟡 序数指标合格阈值(QWK/τ/序数 AUC)学界报告口径 = TODO researcher，不自创。
4. 🟡 连续 ρ→序数指标天花板映射 = TODO(双正态对 log-SFC 不严格，需真实 copula 积分)。
5. 🟡 beta-binomial 最小分母(查 DeepImmuno PMC7781330)。
6. 🟡 assay 异质性归一化(分层+研究内归一化)。
7. 🟡 官方超参查不到标 TODO。
8. 🛑 拍板点：claim 回退方向(A/B/混合源/自补) + TESLA/TCR-seq 对外获取 + 自补 ELISpot。

## 交接
→ researcher 先派(0 GPU 命门前置)：序数指标学界阈值 + 连续→序数映射 + beta-binomial 最小分母 + IEDB 序数/计数字段确切列名。→ 主线+researcher 跑 K0'/Phase0' 命门(0 GPU，出结果前不展开 Phase1'+)。→ coder 实现(序数离散化+频率构造+防泄漏切分+CORN/beta-binomial 头+序数指标+标签打乱，复用 analysis/)。→ 主线跑(gpu_slot)。→ analyst 判 C1'/C3' + A/B 一致性。→ verifier 核序数关键数字。→ skeptic Phase0' PASS+Phase2' 前红队(序数离散化是否人为制造可分性/撞车守不守得住/序数化是否只是把"测不出连续信号"包装成序数任务)。
⚠️ 复核：Phase0' 阈值 ≥10³ 沿用连续粗估，序数极不平衡(high 档稀少)实际可能需 >10³；A vs B headline 依赖 Phase0' 实测先跑再定；序数 novelty 是否够需袁老师判(DeepImmuno 已用三档先验，差异化落在"纯癌序数 benchmark+防泄漏+撞车对照"系统性而非序数任务首创)。
