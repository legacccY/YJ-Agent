# QuantImmuBench 8 工具 ELISpot Benchmark（DS2）

Generated: 2026-06-24
Source: merged_all_tools_8tools.xlsx (34247 rows = subpeptide x HLA)
New tools added: PRIME, ImmuneApp, deepHLApan (vs first batch: DeepImmuno/PredIG/IMPROVE/NeoTImmuML/pTuneos)

---

## 0. 口径对齐声明

严格复刻第一批方法（analysis/BENCHMARK_REPORT.md）：
- DS2（101 肽段，33922 行），ELISpot 真值取每个 Peptide_ID 第一行（同值）
- 聚合：max / mean / top3mean（per Peptide_ID，跨子肽 x HLA 窗口）
- AUC 阈值：ELISpot >0 (n_pos=90) / >10 (n_pos=64) / >median=22.67 (n_pos=50)
- Spearman：分数 vs 连续 ELISpot SFU（有效样本，排除 NaN 分）

旧 5 工具复现验证：max|AUC diff ≤ 0.004（浮点精度范围内），口径对齐 PASS。

---

## 1. 覆盖情况 / NaN 说明

| 工具 | 有效 Peptide_ID (聚合后) | NaN 行数 | 说明 |
|------|--------------------------|----------|------|
| DeepImmuno | 101 | 22889/33922 | 仅 9-10mer |
| PredIG | 101 | 0 | 全覆盖 8-14mer |
| IMPROVE | 101 | 7457 | 8-12mer |
| NeoTImmuML | 101 | 3508 | 8-13mer |
| pTuneos | 101 | 0 | 全覆盖 |
| **PRIME** | **100** | **210（全部集中在 1 个 Peptide_ID: 16097-102-24）** | 该肽段所有 HLA allele 均无分（MixMHCpred 不支持的罕见 allele）→ AUC 分母为 100 肽，n_pos=89 |
| **ImmuneApp** | **101** | **0** | 全覆盖，无缺失 |
| **deepHLApan** | **98** | **2065（跨 10 个 Peptide_ID，部分行 NaN）** | NaN 来自特定 HLA allele 组合（非特定稀有 allele 完全不支持，而是部分 allele 在特定肽段内 NaN）→ AUC 分母为 98 肽，n_pos=88，n_neg=10 |

---

## 2. 主对比表（agg=max, Threshold >0）

| 排名 | 工具 | n_pep | AUC-ROC | AUPRC | Spearman rho | Spearman p | 备注 |
|------|------|-------|---------|-------|--------------|------------|------|
| 1 | pTuneos | 101 | **0.7525** | 0.9494 | 0.1363 | 0.1741 | 第一批 |
| 2 | PredIG | 101 | 0.6611 | 0.9411 | 0.1983 | 0.0468* | 第一批 |
| 3 | NeoTImmuML | 101 | 0.6551 | 0.9421 | 0.0218 | 0.8285 | 第一批 |
| 4 | IMPROVE | 101 | 0.6207 | 0.9221 | **0.2434** | **0.0142*** | 第一批 |
| 5 | **ImmuneApp** | 101 | 0.5889 | 0.9080 | 0.0885 | 0.3786 | **新** |
| 6 | **PRIME** | 100 | 0.5276 | 0.9146 | 0.1163 | 0.2491 | **新，1 肽段缺失** |
| 7 | DeepImmuno | 101 | 0.4813 | 0.8951 | -0.1168 | 0.2449 | 第一批 |
| 8 | **deepHLApan** | 98 | 0.4188 | 0.9038 | 0.0415 | 0.6847 | **新，3 肽段缺失** |

*标注 = p<0.05 显著

---

## 3. 各工具最优 AUC（任意聚合方式）

| 排名 | 工具 | 最优聚合 | 最优阈值 | AUC-ROC | Spearman rho | Spearman p |
|------|------|----------|---------|---------|--------------|------------|
| 1 | pTuneos | mean | >0 | **0.7813** | 0.0297 | 0.7679 |
| 2 | PredIG | mean | >0 | 0.7495 | 0.2797 | 0.0046** |
| 3 | IMPROVE | top3mean | >10 | 0.6805 | 0.3202 | 0.0011** |
| 4 | NeoTImmuML | max | >0 | 0.6551 | 0.0218 | 0.8285 |
| 5 | **ImmuneApp** | mean | >0 | 0.6444 | 0.0434 | 0.6666 |
| 6 | **PRIME** | top3mean | >median | 0.6042 | 0.1682 | 0.0944 |
| 7 | **deepHLApan** | top3mean | >10 | 0.5728 | 0.0475 | 0.6422 |
| 8 | DeepImmuno | mean | >0 | 0.5192 | -0.1494 | 0.1360 |

---

## 4. Spearman（定量强弱预测，agg=max）

| 排名 | 工具 | rho | p-value | 显著? |
|------|------|-----|---------|-------|
| 1 | IMPROVE | 0.2434 | 0.0142 | 是 |
| 2 | PredIG | 0.1983 | 0.0468 | 是 |
| 3 | pTuneos | 0.1363 | 0.1741 | 否 |
| 4 | **PRIME** | 0.1163 | 0.2491 | 否 |
| 5 | **ImmuneApp** | 0.0885 | 0.3786 | 否 |
| 6 | **deepHLApan** | 0.0415 | 0.6847 | 否 |
| 7 | NeoTImmuML | 0.0218 | 0.8285 | 否 |
| 8 | DeepImmuno | -0.1168 | 0.2449 | 否 |

---

## 5. 关键发现

**5a. 新 3 工具没有一个打败 pTuneos（AUC 0.752）或 PredIG（AUC 0.661）**

- ImmuneApp 排第 5（AUC=0.589），是新 3 个里最好的，但仍低于 pTuneos/PredIG/NeoTImmuML
- PRIME 排第 6（AUC=0.528），接近随机
- deepHLApan 排最末（AUC=0.419），低于随机（<0.5），max 聚合表现差于随机分类器

**5b. 定量 Spearman 新工具全部不显著**

- 三新工具 Spearman rho 均 < 0.17，p 均 > 0.09，无法对 ELISpot SFU 做有意义的连续预测
- 第一批中 IMPROVE (rho=0.243, p=0.014) 和 PredIG (rho=0.198, p=0.047) 仍是最优定量预测工具

**5c. ImmuneApp 聚合方式敏感：mean 比 max 高 0.056 AUC**

- ImmuneApp max>0: 0.589；mean>0: 0.644（差距 +0.055）
- 提示 ImmuneApp 分数的代表性受到窗口选取方式影响较大

**5d. deepHLApan 实质上无判别力**

- 所有聚合方式下 AUC 范围 0.42-0.57，agg=max/>0 下 AUC=0.419
- NaN 跨越 10 个 Peptide_ID（部分行缺失），n_neg 从 11 降至 10，样本更少
- Spearman rho=0.042（不显著），综合结论：deepHLApan 在本 ELISpot 数据集上无有效预测信号

---

## 6. 对袁老师课题的启示

| 需求 | 推荐工具 | 理由 |
|------|---------|------|
| 阳性/阴性判别（ELISpot >0） | **pTuneos**（AUC 0.781 mean agg）/ **PredIG**（AUC 0.750 mean agg） | 两者 AUC 最高，第二批新工具均未超过 |
| 定量强弱排序（ELISpot SFU） | **IMPROVE**（rho=0.320 top3mean，p=0.001）/ **PredIG**（rho=0.280，p=0.005） | 唯二显著 Spearman，新工具无显著相关 |
| 部署简便性（全覆盖，无 NaN） | **PredIG**、**pTuneos**、**ImmuneApp** | NaN=0，覆盖全部 HLA+长度 |

新 3 工具在本 ELISpot benchmark 上**没有提供增量价值**，不建议替换现有第一批推荐工具（pTuneos/PredIG/IMPROVE）。

---

## 7. 图

| 图号 | 路径 | 内容 |
|------|------|------|
| Fig 6 | analysis/figures/fig6_8tools_auc_comparison.png | 8 工具 AUC-ROC 柱状图（3 个阈值 x 8 工具，agg=max，橙色区=新工具） |
| Fig 7 | analysis/figures/fig7_8tools_spearman.png | Spearman rho 对比（agg=max，橙色=新工具，*=p<0.05） |
| Fig 8 | analysis/figures/fig8_8tools_roc_curves.png | ROC 曲线 8 工具对比（agg=max，>0，虚线=新工具） |

---

## 8. Caveats（继承第一批 + 新增）

1. **样本量极小**：DS2 仅 101 肽、11 个阴性，AUC 置信区间宽，新旧工具排名差异（< 0.05 AUC）在统计上不显著
2. **PRIME 缺 1 肽段**（16097-102-24，n=210 行全 NaN）：有效样本 n=100，n_pos=89，与其他工具 n=101/90 略有差异，影响直接 AUC 比较
3. **deepHLApan 缺 3 肽段**（n=98，n_neg=10 vs 其他 n_neg=11）：阴性样本更少，AUC 估计更不稳定
4. **新工具训练数据来源**：PRIME/ImmuneApp/deepHLApan 均使用 IEDB 来源数据训练，与本 ELISpot 数据集可能存在数据 overlap，如有 overlap 则各指标偏乐观（实测仍无好结果，实际独立性待查）
5. **AUPRC 高 baseline**：>0 阈值下 baseline AUPRC=0.891（90/101），工具 AUPRC 0.89-0.97 提升有限
6. **pTuneos top3mean 与旧 csv 微小差异**：最大 delta=0.004（浮点/排序差异），不影响结论
