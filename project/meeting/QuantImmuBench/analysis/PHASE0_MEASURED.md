# QuantImmune Phase0 命门：IEDB/CEDAR 连续 magnitude 真数据实测裁定

> 服务 quantimmu-bench / 袁 QuantImmune 立项 Phase0。**IEDB 实测窗**，2026-06-24。
> 本档把 `reference/PHASE0_iedb_fillrate.md` 的全部 TODO 用真数据钉死，取代区间估计。
> 数据源：IEDB `tcell_full_v3.csv`（本地 1.34 GB，573,409 行）+ IEDB IQ-API（query-api.iedb.org）+ CEDAR API（cedar-api.iedb.org）三源交叉。
> 红线：所有数字 pandas/curl 实测，分块读全 csv，三源对账；脚本 `analysis/phase0_fillrate_measured.py` 可复现。

## ⭐ 裁定：命门 **FAIL**（高置信，三源交叉确认）

**承重前提**：连续 ground-truth magnitude（SFC / %tetramer / SI）在肿瘤/neoepitope 子集跨 ≥2 study 且 ≥10³ 正例。

| 判据 | 要求 | 实测 | 判定 |
|---|---|---|---|
| 连续 magnitude 正例数（肿瘤/neoepitope） | ≥ 10³ | **~87–104 唯一肽**（CEDAR 癌症库功能 assay 上界） | **FAIL（差 ~10×）** |
| 跨独立 study | ≥ 2 | **36 PMID**（CEDAR） | PASS |

→ **判据二（跨 study）PASS，判据一（量级 ≥10³）FAIL**。问题不是"单一来源"，而是**连续数值被系统性稀疏记录**——多数研究只报 positive/negative 定性，少数才填连续值。

## 实测证据（三源交叉）

### 1. IEDB 全库 tcell_full_v3（本地 csv 分块实测，权威）
- 总行数 **573,409**（= IQ-API 计数，完全吻合，交叉核验通过）。
- 连续 quant 非空（**全方法**）：**5,773**（其中 Positive 5,453）。
- 但大头是 **MHC binding/亲和力 assay**（IC50/SPR），非免疫原性强度：

| method | 总行 | quant 非空 | 填充率 |
|---|---|---|---|
| binding assay | 3,772 | 1,951 | 51.7% |
| SPR | 1,728 | 1,689 | 97.7% |
| **ELISPOT** | 278,562 | **861** | **0.31%** |
| ICS | 54,859 | 243 | 0.44% |
| **multimer/tetramer** | 35,137 | **161** | **0.46%** |

- **免疫原性强度功能 assay（ELISPOT+tetramer+ICS）连续 magnitude = 1,265 行（全病种）**，正例 1,082。
- 其中**肿瘤**子集：
  - disease 标 cancer/melanoma/… × 功能 assay × quant 非空 = **5 行 / 5 正 / 2 PMID**。
  - Homo sapiens 源（self/neo 候选**上界**）= **9 行 / 9 正 / 6 PMID**；真肿瘤分子仅 DBL 原癌基因(3)+MART-1(2)+DNMT1(1)≈6。
  - 1,265 行连续 magnitude 被病毒/感染霸占（West Nile 200 / HHV-6 197 / 流感 / Vaccinia / TB…），肿瘤近乎缺席。
  - ⚠️ caveat：disease 字段稀疏（978/1265 NULL），单 disease 过滤会**低估**肿瘤 → 用 CEDAR（癌症专库）兜底。

### 2. CEDAR 癌症专库 API（兜底肿瘤上界，最相关）
- 全库 tcell **153,251** 行；连续 quant 非空（全方法）2,703（Positive 2,348，大头仍 binding）。
- **功能 assay 连续 magnitude（ELISPOT 64 + tetramer 70 + ICS 24）= 158 行 total**。
- 正例 **104** / 唯一肽 **87** / 跨 **36 PMID**。
- → 这是**专门的癌症表位数据库**，连续免疫原性强度数据全库才 ~87–104 唯一肽 ≈ 10²。**最权威的肿瘤连续 magnitude 上界。**

### 3. TESLA（金标准对照，researcher 核 Cell 2020）
- 608 肽 / 37 免疫原性正例（6%）；**公开数据仅 binary "validated/not"，逐肽连续 tetramer 频率从未发布**；单一 consortium（2 执行实验室，1 PMID）。
- 三判据全 FAIL（连续量不存在 / 正例 37 / 单 study）。补充表 mmc 不含原始频率，Synapse 仅基因组原始文件。

## 退守建议（= 命中率回退方向 = 拍板点，需袁/徐伊琳定）
连续 magnitude 回归地基（公开源）**不成立**。三条可选 claim 形状：
1. **序数分级回归**（positive-high/-intermediate/-low）——量大可达 10³（待 CEDAR 序数档纯癌子集实测确认），但是序数非连续。
2. **响应频率回归**（responded/tested）——IEDB 有 number_of_subjects_tested/positive 列，连续比例可做 GT，肿瘤子集量待核。
3. **自补 ELISpot 实测产连续 GT**——袁老师 Wave3 已有 ELISpot 正式测试管道（DS1/DS2），不依赖公开源。**最稳**。

### ✅ 用户拍板 = 选 ② 响应频率回归；GT 量级已实测 PASS（2026-06-25）
退守前先证伪选项②的命门（GT 够不够 ≥10³）。API 实测：

| 源 | 响应频率 GT 可用行 | vs ≥10³ |
|---|---|---|
| CEDAR 癌症库 `response_frequency_` 非空 | **58,736** | **PASS ~50×** |
| CEDAR tested+positive 双非空（可算频率） | 59,843 | PASS |
| CEDAR tested>1（真多受试者非单人） | 45,776 | PASS |
| IEDB 全库 response_frequency 非空（对照） | 293,811 | PASS |

→ **响应频率回归 GT 在 CEDAR 癌症库就有 ~10⁴–10⁵，量级命门大幅 PASS**（连续 magnitude 仅 ~10² 的 ~200–500 倍）。方向地基稳。
- ⚠️ 仍待精化（下一步）：①去重到唯一肽 + 跨 PMID study 数 ②response frequency = 群体「%responded」≠ 逐肽免疫强度，需向审稿人界定为「群体响应率回归」非「单细胞强度」 ③肿瘤 neoepitope vs TAA/shared-antigen 子集切分（CEDAR 含共享抗原非纯 neo）④tested=1 退化样本（freq 仅 0/1）需过滤，用 tested>1 的 45,776 为干净基。

## 附：ELISpot benchmark × IEDB overlap（红队 🟠-2 污染量化）
- ELISpot benchmark 7,238 唯一肽 vs IEDB 229,625 肽：**overlap 82.2%（9mer 子串）/ 2.5%（精确 181）**。
- 但 9mer overlap 多为突变长肽的非突变 flanking 区与 IEDB WT 表位共享 9mer，非必然直接训练泄漏。
- 污染对 AUC 乐观偏差（`analysis/overlap_auc_bias.csv`）：**仅 pTuneos 实质**（full 0.778 → clean-8mer 0.604，Δ +0.174），其余 7 工具 |Δ|<0.02 可忽略；exact-only 剔除几乎无效（DS2 仅 1 个 8mer 精确命中）。
- ⚠️ DS2 n_neg=11，pTuneos Δ 的 bootstrap CI=[−0.11,+0.29] 含 0 → **方法学 caveat 非确证**。PPT 如实报"pTuneos 0.78 存在 9mer IEDB 偏差，clean-8mer 降至 0.60，但阴性样本极少 CI 含 0"。

## 复现
- `analysis/phase0_fillrate_measured.py`（分块读全 csv，输出 `phase0_fillrate_measured.csv` + `phase0_method_quant_fill.csv`）。
- IEDB/CEDAR API 计数命令见本档"实测证据"；`data/magnitude_rows.json`（IEDB 1265 行）+ `data/cedar_magnitude_rows.json`（CEDAR 158 行）。
- overlap：`analysis/iedb_overlap_check.py --iedb data/iedb_peptides.csv` → `iedb_overlap_hits.csv` + `iedb_overlap_whitelist.csv`；AUC 偏差 `analysis/overlap_auc_bias.csv`。
- ⚠️ `data/tcell_full_v3.csv`(1.34GB) + `iedb_peptides.csv`(229k 肽) 不进 git（体积），留本地；派生计数表进 analysis/。

## 引用
- IEDB tcell_full_v3 — http://www.iedb.org/downloader.php?file_name=doc/tcell_full_v3.zip ；IQ-API https://query-api.iedb.org/tcell_export
- CEDAR API — https://cedar-api.iedb.org/tcell_export ；CEDAR NAR 2023 PMC9825495
- TESLA — Wells et al. Cell 2020, PMC7652061（608 肽/37 正例/binary only）
