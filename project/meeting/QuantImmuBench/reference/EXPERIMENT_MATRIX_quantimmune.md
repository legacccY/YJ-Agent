# QuantImmune 定量回归实验矩阵设计

> planner(opus)，2026-06-24，服务 quantimmu-bench。
> **本设计是给袁老师参考的科研路线（从现有 8tools 二分 benchmark 走向定量 magnitude 回归工具），不是余嘉的 HPC 部署任务**（余嘉部署交付已完成）。只设计不写码不跑。caveman OFF。

## 服务的 Claim（drift 契约）
- **C3（连续回归对疫苗候选肽 top-K 排序优于二分类，临床价值）= headline 主承重**；C1（坐实纯肽+HLA 的 ρ 天花板 ~0.4-0.6）= 副承重；C2（加供体 TCR-seq 破天花板到 ρ~0.6-0.75）= 探索性 stretch，不当主承重。
- **红线**：不自创验收阈值(用学界规范 AUPRC+ISSR top-K+Spearman+真实阳性率)；baseline 复现零偏离；防泄漏不可妥协；超参查不到标 TODO 不臆想。
- **承重前提（命门，最先验）**：定量回归地基 = IEDB/CEDAR quantitative 字段**实际填充率够 ≥10³ 连续样本**。Phase 0 必先证伪。

## 阶段依赖图
```
Phase0(命门 gate,~0 GPU) ─PASS─► Phase1(baseline 复刻) ─► Phase2(QuantImmune 回归) ─► Phase3(验证/投稿)
   └─FAIL─► 方向塌缩,退序数分级/自补 ELISpot
```
铁律：Phase 0 不 PASS 绝不投后续算力。每 Phase 末书面 kill-shot，FAIL 即停报拍板不硬撑。

## Phase 0 — 命门验证（立项前 gate，最便宜先做）
核连续 GT 实际可得量。
| run | 对象 | 操作 | 判据 | 算力 |
|---|---|---|---|---|
| P0-1 | IEDB tcell_full_v3 quantitative 列 | 统计非空连续值(SFC/%tetramer)记录数，按 assay+neo 分层 | 连续样本 ≥10³ | 0 GPU |
| P0-2 | CEDAR quantitative | 同上限癌症；去重净增量 | 同上 | 0 GPU |
| P0-3 | TESLA mmc 补充表 | 核是否含 per-peptide 连续 tetramer 列(正文 403 未核) | 含=可用 | 0 GPU；Synapse/MTA 对外=拍板点 |
| P0-4 | 本地 DS1/DS2 SFC | 统计去重带连续 SFC 配对数+动态范围 | 确认 DS2 仅 101 肽只能当 held-out | 0 GPU |
- **PASS**：P0-1∪P0-2∪P0-3 去重按 assay 分层后 ≥10³ 连续样本且跨 ≥2 study。
- **FAIL(塌缩)**：<10³ 或单一 study → 退(a)序数强弱分级 或(b)自补 ELISpot(需拍板)。
- **K0 kill-shot(零算力)**：直接 value_counts IEDB quantitative 填充率。第一动作，凑不出 10³ 当场证伪，省 Phase1-3 全算力。

## Phase 1 — baseline 复刻（确立 SOTA 天花板+撞车攻击点）
统一连续 GT 上跑所有现有工具的 magnitude 排序，核心回答 binding proxy(NetMHCpan/MHCflurry BA)对 ELISpot magnitude 有多少排序力(撞车靶)。
| run | 被试工具 | 预期 ρ | 判据 |
|---|---|---|---|
| P1-1 | NetMHCpan 4.1 BA | 0.3-0.4 | C1 天花板下沿；撞车靶 |
| P1-2 | MHCflurry 2.0 | 同 | C1；撞车靶 |
| P1-3 | PRIME 2.1 | 排序非校准 | C1 |
| P1-4 | IMPROVE(TODO 核官方超参) | ~0.32(已实测) | 现状 SOTA 候选 |
| P1-5 | PredIG(ISSR+pseudo-leakage 框架) | ISSR/Spearman | 方法学对标 |
| P1-6 | IEDB Immunogenicity | 弱 | 地板 baseline |
| P1-7 | NetTepi/BigMHC IM/neoIM | — | 补全 SOTA |
| **P1-CTRL** | **标签打乱对照** | ρ→0 | **防泄漏命门** |
- 对照：标签打乱(真模型 ρ≈打乱 ρ→学的是泄漏)、affinity 单特征 vs 全模型、bootstrap CI(禁裸点估)。
- 判据：每工具 Spearman/Pearson(带 CI)+ISSR/PPV@top-K+AUPRC。SOTA 天花板=最高 ρ 的 CI 上界(预期 0.3-0.4)。P1-CTRL PASS=真模型 ρ CI 下界>打乱 ρ CI 上界，FAIL→停证伪。
- 算力 ≈2-5 GPU·h(多 CPU 推理)。

## Phase 2 — QuantImmune 回归模型（headline 主战场）
| run | 输入特征 | 预期 | 判据 |
|---|---|---|---|
| P2-A0 | 肽+HLA(最小,C1 基线) | ρ~0.4 | 超 binding baseline? |
| P2-A1 | +stability 代理(NetMHCstabpan) | 微升 | C1 消融 |
| P2-A2 | +avidity 代理(外来度/自相似) | 微升 | C1 消融 |
| P2-A3 | 全代理 | 接近天花板 0.4-0.6 | **C1 主读数：超 binding baseline?** |
| P2-C2 | +供体 TCR-seq(stretch,对外数据=拍板点) | →0.6-0.75? | **C2 探索不当主承重** |
- 防泄漏(不可妥协)：peptide+4 位 HLA 去重 + leave-study-out/患者分组 + 量化 overlap%报剔除前后 + 声明 pseudo-leakage。
- 对照：binding proxy baseline(撞车攻击点对照线，P2-A3 必须 ρ 显著>P1-1/P1-2)；二分工具 top-K vs 连续模型 top-K(C3 核心)；标签打乱。
- 判据：**C1 PASS**=P2-A3 ρ CI 下界>binding baseline CI 上界且达 0.4-0.6；**C3 PASS(headline)**=held-out 病人连续模型 top-K 实测 magnitude 显著>二分工具(配对 CI 下界>0)；C2 不卡 gate。
- 算力 ≈20-60 GPU·h(轻量 MLP/GBM，HPC 单卡可承)。

## Phase 3 — 验证/投稿
- P3-1 跨供体 held-out(命门定理可证伪点：跨供体 ρ>0.7 则推翻 precursor frequency 天花板)；P3-2 真实临床阳性率(1-6%)+平衡集对照(结论会翻转双报)；P3-3 learning curve(ρ vs 样本量，区分天花板 vs 数据不够)。
- 指标全套 AUPRC(主)+ISSR/PPV@top-K+Spearman(CI)，ROC-AUC 仅辅助。related work 必引 TESLA+IMPROVE+PredIG+Comprehensive+Beyond MHC binding。
- 算力 ≈2-15 GPU·h。

## 全局风险/TODO（按紧急度）
1. **🔴 命门**：IEDB/CEDAR quantitative 填充率 = 承重前提，未核前不投建模算力。
2. 🟡 TESLA 连续列未核(mmc，Synapse/MTA=对外拍板点)。
3. 🟡 assay 异质性归一化(跨研究 raw SFC 不可比，需分层+研究内归一化 pipeline)。
4. 🟡 IMPROVE/PredIG/BigMHC 官方超参查不到标 TODO 不臆想。
5. 🟢 ρ=0.32 CI 主线本轮已跑(`bootstrap_ci_ds2.csv`)。
6. magnitude 严格指 SFC/tetramer 强弱非 binding nM(量纲不同，禁混用，binding 连续输出只当 proxy baseline)。

## 交接
→ Phase 0 先派 researcher+主线核 IEDB/CEDAR/TESLA 填充率(0 GPU 命门 gate，出结果前不展开 Phase1+)。→ coder 实现(GT 构建+防泄漏切分+回归头+标签打乱，复用 analysis/)。→ 主线跑(gpu_slot request)。→ analyst 对判据(C1/C3 PASS/FAIL)。→ skeptic Phase0 PASS+Phase2 动手前红队 C3(是否退化二分/撞车能否守住)。
⚠️ 袁老师复核：Phase0 阈值「≥10³」取自 THEORY 样本复杂度粗估(低置信)；C2 是否纳本轮(需 TCR-seq，Phase0 才知)。
