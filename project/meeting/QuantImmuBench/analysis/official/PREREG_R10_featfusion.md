# PREREG — R10 特征学习融合判决性负检验 (冻结判据)

> 服务: QuantImmuBench §3.3 集成框架 / C2「有方法贡献的融合」。
> 性质: **判决性负检验 (confirmatory NEGATIVE test, 预期 NULL)** —— 目的是把「连喂真免疫学
> 特征的学习融合都打不过最强单工具」钉死, 并产 L0→L4 逐层增量曲线。**不是期待翻盘。**
> 冻结日期: 2026-07-03。冻结后不可事后改判据 / 换主指标 / 换标签口径 (改 = HARKing)。

---

## 0. 数据 (只读, 已核实)

- 主数据 = `data/frozen/pooled_clean_9mer.csv` (130 肽 / 9 患者 DS2 / 9mer 口径)。
- 特征源 = `data/frozen/ds2_official_groundtruth.csv` (按 `mut_key` merge, 130↔130 完美对齐)。
  可用列 (Bash 核): `TPM_PurifiedTumorRNA`(117/130) / `CCF`(121/130) / `Clonal`(122/130) /
  `Variant_Type`(SNV101/DEL23/INS5/NA1) / `Mutation_type`(Driver17/Passenger112/NA1) /
  `Vaccine_Peptide`(130, MT 长肽) / `Short_Epitope`(130, MT 短表位 8-11mer) /
  `Gene_and_Protein_Change`(130, 如 `PIK3CA|p.E545K`)。
  **⚠️ 无任何 WT 序列列, 无 WT netMHCpan 分数列** (Bash 核: `pooled 含 WT 的列: []`)。
- 标签源 = `data/OFFICIAL_DO_NOT_TOUCH/ELISPOT_OFFICIAL_Braun2025_MOESM4.xlsx`
  sheet `"In Vitro"`, 列 `Ttest_pvalue_InVitroStim` (S1 已静态核过存在)。

## 1. 分层特征 (L0→L4 + covariate-only)

| 层 | 增量 | 说明 |
|---|---|---|
| **L0** | SURV6 六工具 `_max` 6 维 | PredIG/IMPROVE/pTuneos/PRIME/ImmuneApp/deepHLApan (同 R3/R5 口径) |
| **L1** | +`log1p(TPM)`,`CCF`,`Clonal`,`is_indel`,`is_driver` | 免疫学 covariate |
| **L2** | +DAI 两形式 +`DAI_missing` | **⚠️ 无 WT 打分 → DAI 全 NaN, DAI_missing 常量=1, 该层无真增量。留 `--wt_scores` 接口待补 (TODO)** |
| **L3** | +理化 (HydroCore/PropHydroAro/Aro/PropSmall/PropAcidic/PropBasic/Inst/pI/mw) +SelfSim | 纯手写氨基酸性质表 + BLOSUM62; SelfSim 用 best-effort SNV WT 重建; foreignness=NotImplementedError |
| **L4** | +工具分歧元特征 (rank_var/rank_entropy/present_immuno_gap/tool_gap) | 跨工具一致度 |
| **covariate-only** | L1-L3 **非工具**免疫学特征, **drop 全部工具分 + 工具派生(DAI/L4 meta)** | 归因闸对照 (skeptic🟠#2) |

层为累积 (L4 = 全部)。特征-层-kind 映射写 `R10_featfusion_manifest.json`。

## 2. 🔒 唯一 confirmatory = R-L1-lg (a-priori, 不可改)

- **confirmatory 检验**: **L1 logistic** OOF 分, per-patient **控肽长** Spearman(vs Elispot SFC)
  经 `paired_patient_test(ctrl='peplen')` vs **最强单 netMHCpan_BA_max**。
  - 选 L1 (非 L4): n=9 极小样本, a-priori 选最小信息层 (奥卡姆), 避免 L4 高维过拟合 + 多重比较膨胀。
  - 选 logistic (非 RF): 主模型, 确定性无 seed。
- **其余** 层 × 模型 × 估计量 (含 AUPRC) = **exploratory**, 全体 Holm 校正后报告, 不作 headline。

## 3. 🔒 归因闸 (confirmatory「赢」的必要条件)

confirmatory 若「赢」 (paired p<0.05 且方向为正), **还须同时满足**:
> **full(=L1 logistic) ρ̄ > max(netMHCpan_BA_max ρ̄, covariate-only logistic ρ̄)**

否则模型只学到「driver/indel 更免疫原」粗规律 (covariate-only 也能拿到), 非「整合工具」,
归因错位, **不算 confirmatory 成立**。三个 ρ̄ 全报, 闸口 PASS/FAIL 显式打印。

## 4. 🔒 主/副指标 + 预期 NULL

- **主指标** = per-patient Fisher-z Spearman(OOF 分, Elispot SFC 连续), 等权聚合。与 R1-R9 同源,
  故与 netMHCpan_BA_max / geomean 旧基线严格可比。
- **副指标** = 130 肽级 AUPRC(vs 二元标签), cluster bootstrap over patients **BCa** CI。
  **独立 estimand (混病人内/间信号 + 疫苗肽选择效应), 仅 exploratory 附注, 绝不当 headline。**
- **预期结果 = NULL**。三分流任一皆诚实呈报, 不挑对自己有利的:
  1. confirmatory 真显著 (且过归因闸) → 罕见, 报「有条件的方法贡献」。
  2. 肽级 AUPRC 显著但 per-patient 不显著 → 报「估计量依赖, 主指标下无收益」。
  3. 都不显著 → 报「连喂真免疫学特征学习融合也打不过最强单」(预期主线)。

## 5. 🔒 二元训练标签 (预登记两候选)

- **主口径** = `Ttest_pvalue_InVitroStim < 0.05` (≈76 阳/54 阴, 平衡)。headline 引此口径。
- **敏感性** = `Elispot SFC > 0` (≈118 阳/12 阴, 极不平衡, 仅旁证)。
- 两口径都跑, 主口径出结果。

## 6. 🔒 防泄漏对照 + 功效前置

- **shuffle 标签对照**: 患者内打乱二元标签跑完整 LOPO, AUPRC 须塌回 prevalence、per-patient ρ̄≈0。
  **任一层 shuffle 仍显著 = 全线作废** (pipeline 有泄漏)。
- **n=9 有效 K + MDE 前置核算**: 配对检验过滤后有效 K (两法该病人均 n>3), 报最小可达
  p = 2/2^K。**K=9→p_min≈0.0039; K=5→0.0625 (够不到 0.05)**。跑前先核 K, K<6 则 confirmatory
  功效不足, 结论只能报「未能拒绝 NULL」不可读成「证明整合无效」。

## 7. leak-free LOPO 协议 (命门)

每 fold (留一患者):
1. **患者内无标签归一化** (min-shift + RMS): 每特征在每患者内独立归一 (min→0 再除 RMS),
   **只用该患者自身特征值, 无标签**, 故对 test 患者亦 leak-free。RMS=0 → 置 0。
2. **训练折标准化器**: mean/std **只在 8 训练患者** fit, transform 测试患者 (与第 1 步是两套变换)。
3. **缺失填充**: 用**训练折均值** (test 亦用训练折均值填)。
4. **模型只在 8 患者 fit**, 预测留出患者。拼 9 折 OOF → 130 维 leak-free 分。

- **M1 logistic (主)**: `LogisticRegression(penalty='l2')`, C 由 **nested inner-LOPO** 网格
  `[0.01,0.03,0.1,0.3,1]` 选 (内层在 8 训练患者上再 LOPO, 选内层 per-patient ρ̄ 最高的 C),
  确定性无 seed。
- **M2 浅 RF (副)**: `RandomForestClassifier(max_depth=3, n_estimators=100, min_samples_leaf=5)`,
  seed{1,2,3,4,5} 报均值±std。参数 a-priori 固定于 task 给定范围, 不 tune。
- 禁 deep gbdt / MLP。

---

**签署**: coder (Opus), 2026-07-03。冻结判据以本文件为准, 脚本头注复述。
