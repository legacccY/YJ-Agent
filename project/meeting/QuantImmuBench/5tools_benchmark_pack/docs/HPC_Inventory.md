# Rerun v2 — HPC 目录完整清单（Input / Output / Log）

> 最后更新: 2026-06-30 22:00 CST  
> HPC 路径: `/gpfs/work/bio/zichenli24/rerun_v2/`  
> 连接方式: `ssh zichenli24@dtn.hpc.xjtlu.edu.cn` (dtn=login node, 有网)

---

## 总览

```
/gpfs/work/bio/zichenli24/rerun_v2/
├── 00_source/              # 源数据 (88 KB)
├── 01_DeepHLApan/          # inputs 2.5M + outputs 5.0M + logs 3.5K
├── 02_PRIME/               # inputs 257K + outputs 9.7M + logs 2.0K
├── 03_ImmuneApp/           # inputs 3.1M + outputs 6.3M + logs 262K
├── 04_HLAthena/            # inputs 1.1M + outputs 23M + logs 194K
├── 05_MHLAPre/             # inputs 2.9M + outputs 2.2M + models 4.7M + logs 2.5K
├── 06_analysis/            # outputs 1.5K + logs 193K
├── _hpc_scripts/           # sbatch 提交脚本 (23 KB)
├── _build_all.py           # 全量构建脚本
└── README.md               # 项目说明
```

**总计**: ~62 MB（不含 04_HLAthena 的 55 个 tmp_* 临时目录，可清理）

---

## 一、00_source — 源数据 (88 KB)

| 文件 | 大小 | 说明 |
|------|------|------|
| `Elispot_Dataset2_complete.xlsx` | 36 KB | 130 肽 × 9 患者 (P101-P110, 缺 P103)，含 Vaccine_Peptide, WT Peptide Seq, ELISpot SFC, 6×HLA, TPM, UniProt ID |
| `HLA_nomenclature_map.xlsx` | 5 KB | HLA 命名转换表 (compact/standard/deeplapan/prime 四种格式) |

---

## 二、01_DeepHLApan — Input / Output / Log

**环境**: Singularity (`biopharm/deephlapan:v1.1` SIF)  
**HLA 格式**: `HLA-A02:01` (无星号)  
**Job 历史**: 1503062(❌gpu), 1503089(✅MT), 1503092(✅WT)

### Inputs (2.5 MB)
| 文件 | 行数 | 说明 |
|------|------|------|
| `DeepHLApan_dataset2_MT.csv` | ~29K | 130 肽展开为 8-11mer × MT × 26 HLA |
| `DeepHLApan_dataset2_WT.csv` | ~23K | 同上，WT 版本 |

### Outputs (5.0 MB)
| 文件 | 行数 | 关键列 |
|------|------|--------|
| `dataset2_MT/DeepHLApan_dataset2_MT_predicted_result.csv` | 29,017 | `binding_score` + `immunogenity_score` (⚠️ 方向疑点) |
| `dataset2_MT/DeepHLApan_dataset2_MT_predicted_result_rank.csv` | 29,017 | percentile rank 版本 |
| `dataset2_WT/DeepHLApan_dataset2_WT_predicted_result.csv` | ~23K | WT 预测 |
| `dataset2_WT/DeepHLApan_dataset2_WT_predicted_result_rank.csv` | ~23K | WT rank 版本 |

### Logs (3.5 KB)
| 文件 | 内容 |
|------|------|
| `dhl_gpudebug_1503062.out/err` | ❌ GPU 尝试失败 (TF 版本问题) |
| `dhl_mt_1503089.out/err` | ✅ MT 预测通过 |
| `dhl_wt_1503092.out/err` | ✅ WT 预测通过 |

---

## 三、02_PRIME — Input / Output / Log

**环境**: conda `prime` (py3.11 + PRIME v2.1 C++ + MixMHCpred v3.0)  
**验证**: 对官方 test/out_compare.txt diff=0 (r=1.0)  
**Job 历史**: 1503077(❌cpudebug), 1503081(✅short)

### Inputs (257 KB)
| 文件 | 行数 | 说明 |
|------|------|------|
| `PRIME_database2_MT.txt` | ~4,400 | 130 肽展开为纯肽段列表 |
| `PRIME_database2_WT.txt` | ~4,400 | WT 版 |
| `HLA_alleles.txt` | 26 | 26 个 HLA alleles 列表 |

### Outputs (9.7 MB)
| 文件 | 行数 | 关键列 |
|------|------|--------|
| `dataset2_MT_prime.txt` | 8,804 | `%Rank`, `Score`, `%RankBinding`, `BestAllele` |
| `dataset2_WT_prime.txt` | ~8,800 | 同上 |

> **评估取**: `Score` (best allele column, 越高越免疫原)

### Logs (2.0 KB)
| 文件 | 内容 |
|------|------|
| `prime_cpudebug_1503077.out/err` | ❌ cpudebug 分区 1h 墙钟不够 |
| `1503081.out/err` | ✅ short 分区跑通 |

---

## 四、03_ImmuneApp — Input / Output / Log

**环境**: conda `immuneapp` (⚠️ 小写! py3.7 + TF1.15 + Keras2.3.1)  
**Job 历史**: 1503102❌, 1503106❌, 1503109❌, 1503112❌, **1503137✅**

### Inputs (3.1 MB)
```
inputs/
├── dataset2_MT/  (26 个 txt, 每 allele 一个)
│   ├── HLA-A0101.txt
│   ├── HLA-A0201.txt
│   ├── ...
│   └── HLA-B5701.txt
└── dataset2_WT/  (26 个 txt)
    └── ... (同上结构)
```
格式: 每行一条肽 (纯文本, 无 header)

### Outputs (6.3 MB)
```
outputs/
├── dataset2_MT/
│   ├── HLA-A0101/ImmuneApp_Immunogenicity_predictions.tsv
│   ├── HLA-A0201/ImmuneApp_Immunogenicity_predictions.tsv
│   └── ... (26 个 folder)
├── dataset2_WT/  (26 个 folder)
└── all_results/
    └── ImmuneApp_Immunogenicity_predictions.tsv  ← 合并文件 (45,967 行, 2.3 MB)
```
合并文件列: `Allele` / `Peptide` / `Sample` / `Immunogenicity_score`

> **评估取**: `Immunogenicity_score` (max 跨 allele × 子肽 → Peptide_ID)

### Logs (262 KB)
| Job ID | 状态 | 说明 |
|--------|------|------|
| 1503102 | ❌ | 首次尝试 (ImmuneApp env, 无 TF) |
| 1503106 | ❌ | 第二次尝试 |
| 1503109 | ❌ | 第三次尝试 |
| 1503112 | ❌ | 第四次尝试 |
| **1503137** | ✅ | **修复: conda activate immuneapp (小写!) → 52 文件全部处理** |

---

## 五、04_HLAthena — Input / Output / Log

**环境**: Singularity (`ssarkizova/hlathena-external:dev` SIF)  
**跑法**: login node 直接跑 (需外网下载 Google Cloud Storage 模型)  
**模式**: MSiCE (ctex_up/ctex_dn 上下文 + TPM 表达量)  
**模型**: 33 alleles × ~100MB = ~3.3GB (缓存于 `/gpfs/work/bio/zichenli24/tools/hlathena_models/`)

### Inputs (1.1 MB)
```
inputs/
├── d1_patient1.txt ... d1_patient6.txt   (DS1, 6 患者)
└── d2_patient101.txt ... d2_patient110.txt (DS2, 9 患者, 缺 P103)
```
DS2 输入格式 (tab 分隔):
| pep | ctex_up | ctex_dn | TPM | peptide_id | patient_id | elispot | window_size | position |
|-----|---------|---------|-----|------------|------------|---------|-------------|----------|

> 上下文序列由 `prepare_inputs_rerun.py` 从 79 个 UniProt 序列生成

### Outputs (65 KB, cleaned 2026-06-30)
```
outputs/
└── HLAthena_presentation_scores.csv     ← 最终合并 (131 行, head+130 肽)
```
列: `Peptide_ID, presentation_score` (score 范围 ~[0.49, 1.0], 越高越可能被提呈)
> 55 个 tmp_* 中间目录已于 2026-06-30 清理 (~23 MB)，mspred 已合并到 CSV，无需保留。

### Logs (~194 KB, partially stale)

---

## 六、05_MHLAPre — Input / Output / Models / Log

**环境**: conda `mhlapre` (PyTorch 1.12.1+cu102, **CPU 模式**)  
**原因**: RTX 4090 sm_89 不兼容 PyTorch 1.12.1 的 cu102 kernel  
**Job 历史**: 1503103(❌gpu), 1503156(❌CUDA), **1503158(✅cpu)**

### Inputs (2.9 MB)
| 文件 | 行数 | 说明 |
|------|------|------|
| `dataset2_MT.csv` | 29,016 | 训练: peptide/HLA/label/patient |
| `dataset2_WT.csv` | 22,586 | 训练 |
| `dataset2_MT_predict.csv` | 25,470 | 预测: peptide/allele/patient |
| `dataset2_WT_predict.csv` | 20,496 | 预测 |
| `dataset1_MT_predict.csv` | 321 | DS1 预测 (82 肽) |
| `dataset1_WT_predict.csv` | 321 | DS1 预测 |
| `README.txt` | — | 列说明 |

### Outputs (2.2 MB)
| 文件 | 关键列 | Mean Score |
|------|--------|------------|
| `dataset2_MT_predicted.csv` | `prediction_score` | 0.69 |
| `dataset2_WT_predicted.csv` | `prediction_score` | 0.25 |
| `dataset1_MT_predicted.csv` | `prediction_score` | — |
| `dataset1_WT_predicted.csv` | `prediction_score` | — |

### Models (4.7 MB)
| 文件 | 说明 |
|------|------|
| `mhlapre_best.pth` | TextCNN ~300K params, 30 epochs on DS2 |

### Logs (2.5 KB)
| Job ID | 内容 |
|--------|------|
| 1503103 | ❌ GPU 首次尝试 |
| 1503156 | ❌ `CUDA error: no kernel image is available for execution on the device` |
| **1503158** | ✅ CPU 模式跑通 |

---

## 七、06_analysis — 评估输出

**脚本**: `/gpfs/work/bio/zichenli24/tools/analysis/eval_v5_three_tier.py`  
**方法**: Fisher-Z 加权 → 全局 Spearman → AUC (SFC>0)  
**Job 历史**: 1503128(2tool), 1503219(4tool), 1503436(❌err), **1503437(✅5tool)**

### Outputs (1.5 KB)
| 文件 | 内容 |
|------|------|
| `metrics_three_tier.csv` | 5 工具 × 15 指标 (详见下表) |
| `per_patient_details.csv` | 45 行 (5 tools × 9 patients), 列: patient/n/rho/z/weight/Tool |

### metrics_three_tier.csv 完整内容:

| 列 | PRIME | DeepHLApan | ImmuneApp | HLAthena | MHLAPre |
|----|-------|------------|-----------|----------|---------|
| is_immunogenicity_tool | True | True | True | **False** | True |
| n_peptides_total | 130 | 130 | 130 | 130 | 130 |
| n_peptides_covered | 130 | 130 | 130 | 130 | 130 |
| FisherZ_rho | 0.2033 | 0.0092 | 0.1715 | 0.2001 | 0.2235 |
| FisherZ_95CI | [0.013, 0.379] | [-0.182, 0.200] | [-0.020, 0.351] | [0.010, 0.377] | [0.034, 0.397] |
| FisherZ_significant | **True** | False | False | **True** | **True** |
| Global_rho | +0.226 | −0.129 | +0.036 | +0.137 | +0.264 |
| Global_p | 0.0096 | 0.1440 | 0.6813 | 0.1206 | 0.0024 |
| AUC (SFC>0) | 0.586 | 0.404 | 0.579 | 0.438 | 0.997⚠️ |

### Logs (193 KB)
| 文件 | 内容 |
|------|------|
| `eval_1503128.out/err` | 2 工具试跑 (PRIME + DeepHLApan) |
| `1503219.out/err` | 4 工具 (无 HLAthena) |
| `1503436.out/err` | 5 工具 ❌ (HLAthena patch 失败) |
| **`1503437.out/err`** | ✅ **5 工具最终评估** |

---

## 八、_hpc_scripts — 提交脚本 (23 KB)

| 文件 | 对应 Job | 状态 |
|------|----------|------|
| `run_deephlapan.sbatch` | 1503089/1503092 | ✅ |
| `run_prime.sbatch` | 1503081 | ✅ |
| `run_immuneapp.sbatch` | 1503137 | ✅ |
| `run_hlathena.sbatch` | login node 直接跑 | ✅ |
| `run_mhlapre.sbatch` | 1503158 (CPU) | ✅ |
| `run_evaluation.sbatch` | 1503437 | ✅ |
| `sync_to_hpc.sh` | — | 同步脚本 |
| `check_status.sh` | — | 状态检查 |

---

## 九、可清理文件

以下为中间产物，保留不影响分析，删除可释放 ~20 MB:

- `04_HLAthena/outputs/tmp_*/` — 55 个临时目录 (每患者 2-5 次尝试)，仅最后成功的 `mspred.txt` 有价值，已合并到 `HLAthena_presentation_scores.csv`
- `03_ImmuneApp/outputs/dataset2_MT/HLA-*/` — 26+26 个 per-allele 目录，已合并到 `all_results/`
- `03_ImmuneApp/logs/` — 前 4 次失败尝试的 log (262 KB)
- `01_DeepHLApan/logs/dhl_gpudebug_1503062.*` — GPU 失败尝试
