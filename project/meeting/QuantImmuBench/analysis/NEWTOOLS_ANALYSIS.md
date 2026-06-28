# 7 新工具 benchmark 结果分析（DS2 corrected-full）

> 服务 quantimmu-bench。analyst 编队产出，2026-06-27；**2026-06-28 IMPROVE 跑通后全量重算更新**。数字真源 `metrics_ds2_16tools.csv`（17 工具×9 行=3 聚合×3 阈值）+ `per_patient_spearman_16tools.csv`（per-patient Fisher-Z 加权）。红线：数字 Bash/Grep 核 csv。
> 模式 = corrected-full（HLA-FIX 后，P101/P102 HLA-dep 行置 NaN）。
>
> **⚠️ 2026-06-28 更新说明**：IMPROVE Phase B 重推理跑通（n_pep 86→101），触发 P101/P102 全量重算，**连带多数工具的 AUC / best-agg Spearman / per-patient CI 都有变动**（非仅 IMPROVE）。下表全部以当前 csv 为准；本轮关键翻转见 §二.0。旧版（06-27）数字已废，勿混用。

## 一、17 工具横评表（新工具加粗）

| 工具 | 类别 | AUC(max,>0) | AUPRC | best-agg Spearman | p | per-patient fisherz | CI95% | CI 排 0 | caveat |
|---|---|---|---|---|---|---|---|---|---|
| pTuneos | 旧 | 0.718 | 0.943 | +0.119(max) | 0.238 | 0.121 | [-0.112,0.341] | 否 | reinf |
| PredIG | 旧 | 0.663 | 0.942 | +0.279(mean) | **0.005** | 0.229 | [-0.003,0.437] | 否(勉强) | reinf · **三聚合 global 均显著(0.20/0.28/0.20,p<0.05)** |
| NeoTImmuML★ | 旧 | 0.655 | 0.942 | +0.097(mean) | 0.337 | 0.033 | [-0.194,0.256] | 否 | — |
| **Repitope** | **新** | **0.620** | 0.930 | +0.085(mean) | 0.399 | 0.119 | [-0.112,0.338] | 否 | HLA-agnostic · 数据最全(n=9) |
| IMPROVE | 旧 | **0.616** | 0.921 | **+0.323(top3)** | **0.001** | **0.250** | **[0.021,0.455]** | **是** | ✅Phase B 重推理完成(n86→101)·global+per-patient 双显著·全榜最稳 |
| ImmuneApp | 旧 | 0.591 | 0.909 | +0.092(top3) | 0.359 | 0.157 | [-0.076,0.374] | 否 | reinf |
| **IEDB_Calis** | **新** | 0.528 | 0.877 | +0.096(max) | 0.339 | 0.112 | [-0.121,0.334] | 否 | 经典统计基线 |
| PRIME | 旧 | 0.517 | 0.915 | +0.214(top3) | **0.031** | **0.279** | **[0.050,0.481]** | **是** | reinf · 最强 per-patient(但 global max n.s.) |
| **MHCflurry_presentation** | **新** | 0.513 | 0.898 | +0.171(top3) | 0.087 | 0.124 | [-0.108,0.342] | 否 | 提呈代理 |
| **BigMHC** | **新** | 0.500 | 0.892 | -0.094(mean) | 0.349 | -0.014 | [-0.242,0.215] | 否 | reinf · 无信号 |
| **MHCflurry_affinity_neg** | **新** | 0.476 | 0.898 | -0.268(mean) | **0.007** | 0.203 | [-0.028,0.413] | 否 | ⚠️ 聚合方向翻转·不稳健·**per-patient CI 现含 0(掉出显著)** |
| DeepImmuno | 旧 | 0.469 | 0.893 | -0.110(mean) | 0.274 | 0.015 | [-0.214,0.242] | 否 | reinf |
| **netmhcpan_ba** | **新** | 0.468 | 0.912 | **+0.348(mean)** | **0.0004** | 0.155 | [-0.079,0.373] | 否 | ⚠️ DTU pending · mean 聚合下全场最强 |
| deepHLApan | 旧 | 0.445 | 0.905 | -0.092(mean) | 0.363 | 0.224 | [-0.007,0.433] | 否(勉强) | reinf · ⚠️max/topk count 混杂 |
| **TSCAPE** | **新** | 0.442 | 0.879 | -0.191(mean) | 0.056 | 0.001 | [-0.226,0.227] | 否 | ⚠️ 三聚合负但**已全部不显著**(p=0.17/0.06/0.11)·方向待核·CC-BY-NC-ND |
| HLAthena | 旧 | 0.415 | 0.864 | +0.192(top3) | 0.067 | -0.011 | [-0.249,0.228] | 否 | proxy |
| **CNNeo** | **新** | 0.398 | 0.874 | -0.109(mean) | 0.280 | -0.204 | [-0.413,0.026] | 否 | reinf · 唯一近显著负 per-patient |

注：best-agg = 三聚合中 p 最小那行；AUC(max,>0) 是统一口径（mean/>10 等组合下部分工具 AUC 更高，见 `fig_auc_17tools_corrected`）。

## 二、关键发现

**0. 2026-06-28 重算后关键翻转（vs 06-27 旧版）**
- **IMPROVE 强化、坐稳头名**：global max ρ 0.243→**0.252**(p 0.014→**0.011**)、top3 best-agg ρ 0.283→**0.323**(p 0.008→**0.001**)、AUC(max,>0) 0.545→**0.616**、per-patient fisherz 0.255→0.250 CI[0.021,0.455]。**IMPROVE 现在是全 17 工具里唯一 global(p=0.011) 与 per-patient(CI 排 0) 双双显著的工具**——最稳健的弱-正相关信号。
- **显著工具集 3→2**：per-patient CI 排 0 由旧版 {PRIME, IMPROVE, MHCflurry_affinity_neg} **收缩为 {IMPROVE, PRIME}**。MHCflurry_affinity_neg(fisherz 0.203 CI[-0.028,0.413]) **掉出 per-patient 显著**。⚠️ 此变动疑非纯 IMPROVE 触发（15tools 旧 per-patient 已是 0.203），建议 verifier 核 06-27 md 旧值 0.248[0.003,0.464] 来源。
- **TSCAPE 不再「全聚合显著负」**：三聚合 ρ=-0.139/-0.191/-0.159，p=0.17/0.06/0.11，**全部 n.s.**（旧版 p 全<0.05）。仍为负、方向待核，但「显著负」结论已不成立——PPT 须改口径。
- **PredIG 转为 global 三聚合均显著**：max/mean/top3 ρ=0.20/0.28/0.20，p 全<0.05（旧版标「HLA-FIX 后不再显著」已过时）；但 per-patient CI[-0.003,0.437] 仍勉强含 0。

1. **新工具整体没破旧工具天花板**。新工具组 per-patient fisherz 均值 **0.062**，旧工具组 **0.144**。旧工具最强 PRIME 0.279 [0.050,0.481] 与 IMPROVE 0.250 [0.021,0.455]；新工具最强 netmhcpan_ba 0.155（CI 含 0）、MHCflurry_affinity_neg 0.203（CI 含 0）。全 17 工具 per-patient CI_lo>0（统计显著正相关）只有 **2 个**：**IMPROVE、PRIME**（均为旧工具）。

2. **netmhcpan_ba（纯结合亲和力）在 mean 聚合下仍是全局最强 Spearman**：rho=+0.348 p=0.0004，对应 AUC(mean,>10)=0.693。但 (a) 仅 mean 聚合触发，max/top3 均 n.s.；(b) DTU pending 数字未获许可；(c) per-patient fisherz 仅 0.155 CI 含 0。说明「患者内所有 HLA 结合力取均值」捕捉到某信号，但聚合敏感、不稳健、个体内不显著——再次印证「结合 ≠ 免疫原性」需谨慎解读。

3. **TSCAPE 全聚合一致为负但已不显著**（max/mean/top3 = -0.139/-0.191/-0.159，p=0.17/0.06/0.11，**重算后全部 n.s.**），AUC 0.44。仍疑似**分数语义反转**（高分=低应答）或耐受性预测倾向，但「显著负」证据已消失。⚠️ **未擅自取反**（守复现零偏离红线），PPT 如实报负+标「方向待核、当前不显著」。需 verifier 回溯 T-SCAPE 分数定义/运行日志再定论。

4. **MHCflurry_affinity_neg 聚合方向翻转**：max +0.128(n.s.) / mean -0.268(p=0.007) / top3 +0.235(p=0.018)。三聚合方向不一致 = 对「取最强结合 vs 平均结合」敏感；per-patient fisherz 0.203 CI[-0.028,0.413] 重算后含 0（掉出显著）。报告时不能只引「最好 p 值」，须说明聚合依赖性。

5. **Repitope（唯一 HLA-agnostic）AUC 0.620 排第四**，说明肽序列层面信号存在；但 per-patient fisherz 0.119 CI 含 0，中游。数据最全（n=9，reinference_pending=False）。

## 三、对项目目标的对齐

**「免疫强弱定量」整体结论：仍是「普遍弱相关」，IMPROVE 重算后结论不变（仅天花板上沿略升）。** 17 工具中 per-patient fisherz 无一 >0.30（最高 PRIME 0.279、IMPROVE 0.250），中位数约 0.12，全落「弱相关」区间。global best-agg 单工具上限 = IMPROVE top3mean ρ=0.323（最强稳健口径）/ netmhcpan_ba mean ρ=0.348（DTU pending+仅 mean）。**没有任何工具实现「弱→中等(ρ>0.4)」跨级提升**——离立项叙事的 0.4–0.6 天花带下沿仍有明显差距，间接强化「现有工具难做强弱定量」这一空白。新工具的价值在于**方法学覆盖面**（统计/HLA-agnostic/纯结合/提呈/LLM/迁移/多域 7 类范式全测过）——直接服务 QuantImmune 自研算法的立项依据。

## 四、配图（已出）

- `figures/fig_spearman_17tools_corrected.png/pdf` — 17 工具 Spearman 条形（corrected，含 PredIG/TSCAPE 翻转），新旧分色
- `figures/fig_auc_17tools_corrected.png/pdf` — 17 工具 AUC 条形，标 0.5/0.75 线
- `figures/fig_newtools_fisherz.png` — per-patient Fisher-Z 排序+CI
- `figures/fig_newtools_spearman_heatmap.png` — Spearman 热图（工具×聚合，p<0.05 标星）

## 五、待办（非阻塞）

- TSCAPE 方向诊断（verifier 核分数语义，确认是否系统反转）。
- netmhcpan_ba DTU consent 解除后重评（mean 聚合最强信号待许可才能发）。
- Phase B 重推理 PRIME/IMPROVE（当前最强但 reinference_pending）确认排名稳定。
