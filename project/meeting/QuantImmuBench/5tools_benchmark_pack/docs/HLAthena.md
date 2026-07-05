# HLAthena 工具交付说明

> 项目：Rerun v2 — 5 工具 × 130 肽 × 三层次评估
> 数据红线：本文所有 benchmark 数字精确溯源 HPC 评估输出，未自创。

> ⚠️ **重要定位说明（先读）**：HLAthena 预测的是 **MHC-I 提呈概率（presentation）**，**不是 T 细胞免疫原性**。论文原文明确指出「我们没有建模被 HLA 提呈的肽段能否与 TCR 互作，该问题尚未解决」。因此本工具仅作为「提呈代理（presentation proxy）」基线，**与免疫原性工具任务层次不同，不可同列、不可 apples-to-apples 直接并比**。其 benchmark 表现接近随机属于任务定义差异，并非部署缺陷。

---

## 1. 工具简介

- **原理 / 方法**：全连接神经网络（单隐藏层；allele-specific 用 tanh、隐藏单元 50，pan-allele 用 ReLU、隐藏单元 250），在大规模质谱（MS）免疫肽组数据上训练，预测内源肽段被 HLA-I 提呈的概率。不依赖 netMHCpan。
- **训练数据**：单等位细胞系 LC-MS/MS 鉴定的洗脱肽段，覆盖 95 个 HLA 等位。
- **特点 / 优势**：大规模 MS 免疫肽组训练；提呈预测对人群覆盖广；可纳入剪切位点上下文（ctex_up/ctex_dn）+ 基因表达（TPM）提升精度（本项目启用 MSiCE 模式）。
- **局限**：只预测提呈、不预测免疫原性（核心 caveat）；无公开 GitHub（仅论文 Supplementary Code + Docker 镜像）；Docker 镜像约 6 年未更新；仅供研究使用。
- **论文**：Sarkizova et al., *A large peptidome dataset improves HLA class I epitope prediction across most of the human population*, Nature Biotechnology, 2020, 38:199–209. DOI: **10.1038/s41587-019-0322-9**
- **代码 / 部署源**：Docker 镜像 `ssarkizova/hlathena-external:dev`（~909MB → Singularity SIF）
- **许可证**：仅供研究使用（research purposes only），无显式开源协议。

---

## 2. 输入数据模板 / 格式

- **文件格式**：tab 分隔（带表头）。
- **必填列**：`pep`（氨基酸序列）、`ctex_up`、`ctex_dn`（上下游各 30 AA，`--run_ctex true` 时必填）。
- **肽段长度**：8/9/10/11-mer。
- **HLA 格式**：标准格式（如 `HLA-A*02:01`），命令行 `--alleles` 传入。
- **可选列**：`TPM`（表达量，启用 MSiCE 模式）、`expr_col_name`（指定表达量列名）、`logtransform_expr`（表达量 log 变换）。
- **是否需基因组数据**：需 UniProt 蛋白序列生上下文（ctex_up/ctex_dn）→ 本项目通过 `prepare_inputs_rerun.py` 抓取 79 个 UniProt 序列。

**输入示例**（`d2_patient101.txt`）：
```
pep	ctex_up	ctex_dn	TPM	peptide_id	patient_id	elispot	window_size	position
SLLMWITQV	----------------------------QQ	QQ--------------------------	0.36	P101_S1	101	80	9	0
...
```

---

## 3. 参数设置

| 参数 | 说明 | 本项目用值 |
|---|---|---|
| `--runID` | 运行标识 | `d2_p<PatientID>` |
| `--rundir` | 输出根目录 | `outputs/` |
| `--peptides` | 输入肽段文件 | `inputs/d2_patient<PID>.txt` |
| `--alleles` | 预测等位基因列表 | 各患者 HLA（逗号分隔） |
| `--run_ctex` | 启用剪切位点上下文 | `true` |
| `--expr_col_name` | 表达量列名 | `TPM` |
| `--logtransform_expr` | 表达量 log 变换 | `true` |
| `--peptide_col_name` | 肽段列名 | `pep` |
| 模型选择 | 自动（给 ctex → MSiC；给 TPM → MSiCE） | MSiCE（启用上下文+表达量） |

**完整命令**（Singularity）：
```bash
singularity exec --bind /gpfs/work/bio/zichenli24/tools/hlathena_models:/models \
    --bind /gpfs/work/bio/zichenli24/tools/hlathena_models_pan:/models_panpan \
    hlathena.sif predict \
    --runID d2_p101 \
    --rundir outputs/ \
    --peptides inputs/d2_patient101.txt \
    --alleles "HLA-A*66:01,HLA-B*40:01,HLA-B*57:01,HLA-C*06:02" \
    --run_ctex true \
    --expr_col_name TPM \
    --logtransform_expr true \
    --peptide_col_name pep
```

---

## 4. 输出格式及含义

- **输出文件**：`<runID>/mspred.txt`（17+ 列，tab 分隔）。
- **关键列**：

| 列 | 含义 | 方向 / 范围 |
|---|---|---|
| pep | 肽段序列 | — |
| ctex_up / ctex_dn | 上下文序列 | — |
| TPM | 表达量 | — |
| peptide_id | 肽 ID | — |
| clevnn | 剪切位点神经网络分 | 越高越可能被剪切 |
| model_\<allele\> | allele-specific 模型 MHC-I 提呈概率 | 连续，约 [0,1] |
| MSi_\<allele\> | 整合剪切位点+表达的 MSiCE 最终提呈分 | **越高越可能被提呈**（**本评估用**） |

- **聚合方式**：每条子肽取跨 allele 最佳 `MSi_<allele>` 值 → 按 Peptide_ID 取 max-pool → 得到 `HLAthena_presentation_scores.csv`（130 肽，分数 [0.49, 1.0]）
- **⚠️ 重申**：输出是**提呈概率**，非免疫原性强弱分。免疫原性评估用它仅作「提呈先决条件」的 proxy baseline。

---

## 5. 最新 benchmark 结果（DS2 ELISpot，130 肽）

> 数据集：DS2 In Vitro ELISpot，130 肽 / 9 患者。⚠️ HLAthena 为**提呈代理基线**，下列数字不与免疫原性工具同列比较。

| 指标 | 数值 |
|---|---|
| n_pep（覆盖肽数） | 130 / 130（全覆盖） |
| per-patient Fisher-Z 加权 ρ [95% CI]（**主指标**） | **+0.200 [+0.010, +0.377]**（CI 不含 0，Fisher-Z 层面**显著**） |
| Spearman ρ（max 聚合，对照） | **+0.137**（p = 0.121，不显著） |
| AUC（max，SFC > 0） | 0.438 |

**解读**：Fisher-Z 层面达到显著（+0.200，95%CI > 0）——说明提呈信息对免疫强弱有一定预测力（提呈是免疫原性的必要非充分条件）。但全局 Spearman 不显著（p=0.121），AUC 仅 0.438 接近随机。这印证了提呈 ≠ 免疫原性：提呈信号方向正确但定量能力有限。

---

## 6. 部署环境与已知问题

- **跑的版本**：`ssarkizova/hlathena-external:dev` Docker → Singularity SIF，启用 MSiCE 模式（ctex + TPM）
- **环境**：HPC login node（dtn.hpc.xjtlu.edu.cn）+ Singularity 3.11.3。CPU 推理，无需 GPU。**必须在有网的 login node 跑**（镜像内 `predict_docker.bash` 会从 Google Cloud Storage 下载模型）。
- **模型**：33 个等位基因 specific 模型（~3.3GB）+ pan-allele 模型。从 `gs://msmodels/` 匿名下载（内置凭证已失效，但 bucket 匿名可读）。
- **关键坑**：
  - **SIF 根文件系统只读**：`mkdir /models` 失败 → 必须 bind-mount 宿主编译目录到 `/models` 和 `/models_panpan`
  - **Google Cloud Storage 下载极慢**（中国大陆）：登榜节点逐患者跑，模型增量缓存（首次每个 allele ~30MB，30-60 秒）
  - **ECDF 文件缺失**：`/models_panpan/ecdf/ecdf_panpan_*.RDS` 缺部分 allele → 最终回归步骤崩溃，但 mspred.txt 在此之前已写出（可用），ECDF 排名列缺失不影响 MSi 原始分数
  - **per-length 分文件**：部分患者产出 mspred_8/9/10/11_features_summary.txt 而非合并的 mspred.txt → 先 `head -1` 取表头，再 `tail -n +2` 拼接
  - **UniProt 上下文序列**：79 个蛋白通过 REST API 抓取（`prepare_inputs_rerun.py`），需在 login node 执行（计算节点无外网）
  - Web server 备选：http://hlathena.tools（上限 10000 肽/批），可作为交叉验证
