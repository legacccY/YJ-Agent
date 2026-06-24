# Phase0 命门实测：IEDB tcell_full_v3 连续 magnitude 填充率

> 服务对象：quantimmu-bench 数据组 Phase0 **命门** —— 判定袁 QuantImmune「magnitude 强弱回归」是否有 ground truth。
> 承重前提：连续值（SFC / %tetramer / SI）在肿瘤/neoepitope 子集、跨 ≥2 study、达 ≥10³ 正例。
> 数据文件：`data/external/tcell_full_v3.csv`（1.3 GB，双行表头，**573,409 数据行**）。
> 所有数字均 Bash + pandas chunksize 实测原文件，无臆想。测量脚本与复现命令见文末。

---

## 1. 核心结论：命门 FAIL（高置信）

**判据**：肿瘤/neoepitope 子集内，functional assay 的连续 magnitude **正例** ≥ 10³ 条且跨 ≥ 2 study。

**实测**：肿瘤子集 functional assay quantitative 非空**正例 = 6 条 / 3 study**（不限正例也只有 **7 条**）。

| 判据项 | 阈值 | 实测 | 结果 |
|---|---|---|---|
| 肿瘤子集 functional quant 正例条数 | ≥ 1000 | **6** | FAIL（差 ~167×） |
| 跨 study 数 | ≥ 2 | 3 | （达标但样本量塌） |

→ **FAIL，置信高**。差距三个数量级，不是边界擦伤，是结构性空缺。袁 QuantImmune「magnitude 强弱回归」在 IEDB tcell_full_v3 上**没有可用的连续值 ground truth**。

根因：IEDB T cell assay 的连续值（`Quantitative measurement`）整体填充率仅 **1.01%**，且这 1% 里绝大部分是 **MHC binding 亲和力 / 结构数据（IC50、KD、SPR、晶体分辨率）**，不是免疫原性强弱（SFC / %tetramer / SI）。functional assay 的连续值本就极稀，落到肿瘤子集后几乎归零。

---

## 2. 全库填充率 + 按 Method 分组（来源 csv 列 `Assay:Quantitative measurement`=列124，`Assay:Method`=列118）

**全库**：total = 573,409；`Quantitative measurement` 非空 = **5,773**；填充率 = **1.01%**。

| Method | total | quant_nonnull | pct | units_top | 类别 |
|---|---|---|---|---|---|
| binding assay | 3,772 | 1,951 | **51.72%** | 1/s:825; M^-1s^-1:748; nM:360 | ⚠️ MHC binding（非免疫原性） |
| SPR | 1,728 | 1,689 | **97.74%** | nM:1658; KD[nM]:31 | ⚠️ MHC binding |
| x-ray crystallography | 455 | 454 | 99.78% | angstroms:454 | ⚠️ 结构（非强弱） |
| 51 chromium | 13,315 | 241 | 1.81% | (no_unit):241 | functional（杀伤） |
| ELISPOT | 278,562 | 861 | **0.31%** | (no_unit):861 | functional（SFC，命门主角） |
| ICS | 54,859 | 243 | 0.44% | (no_unit):243 | functional |
| multimer/tetramer | 35,137 | 161 | 0.46% | (no_unit):161 | functional（%tetramer） |
| 3H-thymidine | 57,437 | 118 | 0.21% | (no_unit):118 | functional（增殖 SI） |
| in vivo assay | 8,933 | 35 | 0.39% | (no_unit):35 | functional |
| ELISA | 40,739 | 14 | 0.03% | (no_unit):14 | functional |
| cytometric bead array / in vitro assay / bioassay / CFSE / BrdU 等 | — | **0** | 0% | — | functional 但无连续值 |

完整 25 行见 `analysis/iedb_fillrate_by_method.csv`。

**关键拆分（免疫原性 vs binding）**：
- functional 免疫原性 assay（ELISPOT+ICS+tetramer+3H+51Cr+ELISA+invivo）quant 非空合计 ≈ **1,573 条**（全库，未限肿瘤/正例）。
- MHC binding / 结构（binding assay + SPR + x-ray）quant 非空合计 ≈ **4,094 条** = 占全部 5,773 非空值的 **71%**。
- 即：库里仅有的连续值，七成是「肽-MHC 结合多牢」，不是「T 细胞反应多强」。**这两个口径必须分开，混报会把命门假性救活。**
- ELISPOT 是免疫原性主力 Method（27.8 万行，占全库 49%），但 SFC 数值填充率只有 **0.31%**——绝大多数行只留了 Positive/Negative 定性标签，丢了原始 SFC。

注：functional assay 的 `Units` 列普遍为空（表中 `(no_unit)`），但 `Quantitative measurement` 仍有真实数值。已抽样核实原值：
`ELISPOT quant=190/67/166.7`、`TETRAMER quant=0.74/3.7/3.5`——值真实，单位靠 Method 推（SFC / %）。填充率统计未被空 Units 干扰。

---

## 3. 肿瘤 / neoepitope 子集专节（命门战场）

**子集定义**：`Disease`（列51/73）或 1st immunogen `Name/Source Organism`（列56/65）或 Epitope `Source Organism`（列23）命中
`cancer|carcinoma|melanoma|neoplasm|tumor|tumour|sarcoma|leukemia|lymphoma|glioma|myeloma|blastoma|malignan` 或 `mutant|neoantigen|neoepitope`。

| 指标 | 实测值 | 说明 |
|---|---|---|
| 肿瘤子集总行数 | **57,085** | 子集本身不小 |
| 子集内全部 study（PMID 去重） | 1,275 | study 数充足 |
| **functional quant 非空 正例** | **6** | 命门判据主角 → ≪ 10³ |
| functional quant 非空（不限正例） | **7** | 仍 ≪ 10³ |
| 上述跨 study（PMID 去重） | **3** | |

抽样肿瘤 functional quant 原值（核实非空有数）：
`multimer/tetramer 0.15 (Positive)`、`10.54 (Positive)`、`12.5 (Positive)`、`0.48 (Positive-Low)`、`0.33 (Positive-Low)`。

→ 肿瘤子集里，免疫原性连续强弱值实际可用条数是**个位数**。回归任务无训练料。

---

## 4. 套判据（PASS/FAIL）

| 命门判据 | 阈值 | 实测 | 判定 |
|---|---|---|---|
| 肿瘤子集 functional 连续 magnitude 正例条数 ≥ 10³ | 1000 | **6** | ❌ FAIL |
| 且跨 ≥ 2 study | 2 | 3 | ✅（但条数已塌，无意义） |

**最终：命门 FAIL，置信高。** 与预判一致。诚实回退：IEDB tcell_full_v3 不能为「magnitude 强弱回归」提供 ground truth。

---

## 5. 退守料（若放弃连续回归，转序数 / 响应频率）

**全库**：
- 响应频率料：`Number of Subjects Tested` & `Number of Subjects Positive` 双非空 = **301,048 行**（充足）。
- 序数三档（定性强度）：Positive-High = **5,813**，Positive-Intermediate = **5,116**，Positive-Low = **17,985**。

**肿瘤子集内**：
- 响应频率（Tested & Positive 双非空）= **19,625 行** → 退守「响应频率回归」有充足料。
- 序数三档：Positive-High = **556**，Positive-Intermediate = **186**，Positive-Low = **1,842**（合计 **2,584** 条带强度档）。

→ 两条退守路线在肿瘤子集都站得住：
  (a) **响应频率回归**（19,625 行，连续 [0,100]%，跨 study 充足）——比定性强度料多一个数量级，是更现实的「免疫原性强弱」代理。
  (b) **序数三档分类**（Positive-High/Intermediate/Low，肿瘤子集 2,584 条）——粒度粗但样本可用。
两者都不是原始 SFC/%tetramer 连续回归，需袁老师确认能否接受代理口径。

---

## 6. 复现命令

列索引（0-based，双行表头第2行 field 名）：
`3=PMID, 11=Epitope Name, 23=Epitope Source Organism, 51/73=Disease, 56=1st immunogen Name, 65=immunogen Source Organism, 118=Method, 119=Response measured, 120=Units, 122=Qualitative Measurement, 124=Quantitative measurement, 125=Subjects Tested, 126=Subjects Positive, 127=Response Frequency, 141=MHC Restriction`

```bash
# 总行数
wc -l data/external/tcell_full_v3.csv   # 573411 含2行表头 → 573409 数据行

# 表头双行 + 列定位
python -c "import csv;f=open('data/external/tcell_full_v3.csv');r=csv.reader(f);cat=next(r);fld=next(r);[print(i,c,fn) for i,(c,fn) in enumerate(zip(cat,fld))]"
```

完整测量脚本（全库填充率 + 按 method 分组 + 肿瘤子集 + 退守料一次扫完，pandas chunksize=50000，na_filter=False 防空串误判）已运行，产出：
- 本报告所有数字
- `analysis/iedb_fillrate_by_method.csv`（method, total, quant_nonnull, pct, units_top）

判定要点（防口径误用）：
- functional 免疫原性 quant 与 MHC binding quant **必须分列**——后者 71% 占比会假性救活命门。
- `Units` 空不等于 `Quantitative measurement` 空，填充率以列124 非空为准（已抽样核原值确认）。
- 「正例」= `Qualitative Measurement` 以 Positive 开头；functional = Method 不含 binding/dissociation/SPR/x-ray/cellular MHC。

---

## 7. 一句话给主线

**命门 FAIL（高置信）**：肿瘤子集 functional 连续 magnitude 正例仅 **6 条 / 3 study**（阈值 ≥10³），全库 quant 填充率 1.01% 且 71% 是 MHC binding 非免疫原性。「magnitude 强弱回归」无 ground truth。退守料充足：肿瘤子集响应频率 19,625 行 + 序数三档 2,584 条，可转代理口径（需袁老师拍板）。
