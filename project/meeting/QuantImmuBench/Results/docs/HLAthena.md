# HLAthena — 工具交付说明

> 项目：QuantImmuBench（癌症个性化新抗原疫苗协作项目）
> 任务：HPC 部署测试现有预测工具，收集 4 类信息（输入格式 / 参数 / 输出含义 / 工具简介）+ benchmark 结果。
> 版本与数字截至 2026-06-28（DS2 ELISpot 全量重算后）。详细环境配置命令见同目录《环境配置命令_回顾记录.md》。

> ⚠️ **重要定位说明（先读）**：HLAthena 预测的是 **MHC-I 提呈概率（presentation）**，**不是 T 细胞免疫原性**。论文原文明确指出「我们没有建模被 HLA 提呈的肽段能否与 TCR 互作，该问题尚未解决」。因此本工具在 QuantImmuBench 中**只能作为「提呈代理（presentation proxy）」基线**，与 PRIME / DeepImmuno / PredIG 等真正的免疫原性工具**任务层次不同，不可同列、不可 apples-to-apples 直接并比**。其 benchmark 表现接近随机属于任务定义差异，并非部署缺陷。

---

## 1. 工具简介

- **原理 / 方法**：全连接神经网络（单隐藏层；allele-specific 用 tanh、隐藏单元 50，pan-allele 用 ReLU、隐藏单元 250），在大规模质谱（MS）免疫肽组数据上训练，预测内源肽段被 HLA-I 提呈的概率。不依赖 netMHCpan。
- **训练数据**：单等位细胞系 LC-MS/MS 鉴定的洗脱肽段，覆盖 95 个 HLA 等位。
- **特点 / 优势**：大规模 MS 免疫肽组训练；提呈预测对人群覆盖广；可纳入剪切位点上下文与基因表达提升精度。
- **局限**：只预测提呈、不预测免疫原性（核心 caveat）；无公开 GitHub（仅论文 Supplementary Code + Docker 镜像）；Docker 镜像约 6 年未更新；仅供研究使用（research-only）。
- **论文**：Sarkizova et al., *A large peptidome dataset improves HLA class I epitope prediction across most of the human population*, Nature Biotechnology, 2020, 38:199–209。DOI: 10.1038/s41587-019-0322-9。
- **代码 / 部署源**：无公开 GitHub；Web server http://hlathena.tools （上限 10000 肽/批）；Docker 镜像 `ssarkizova/hlathena-external:dev`（约 909MB，可转 Singularity 上 HPC）。
- **许可证**：仅供研究使用（research purposes only），无显式开源协议；商用须联系 Broad Institute。引用 benchmark 数字前建议向作者确认合规。

---

## 2. 输入数据模板 / 格式

- **文件格式**：tab 分隔（带表头）或 FASTA。
- **必填列**：`peptide`（氨基酸序列）。
- **肽段长度**：8 / 9 / 10 / 11-mer。
- **HLA 格式**：以等位代号传入（如 `A0101`）；本项目部署实测以去冒号短格式 `A0101` 跑通。
- **可选列（决定调用哪个模型）**：
  - `exists_ctex=true` + `ctex_up` / `ctex_dn`（上下游各 30 个氨基酸）→ 启用 MSiC；
  - `exists_expr=true` + 表达量（TPM）→ 启用 MSiCE。
- **是否需基因组 / 测序数据**：非必须；不提供仅跑 MSi，提供 RNA 表达可提精度。
- **输入样例**（本项目实测烟测）：8 条 8–11mer 测试肽，单列 `peptide` + 指定等位 `A0101`。

---

## 3. 参数设置

| 参数 | 说明 | 本项目用值 |
|---|---|---|
| 模型选择 | `MSi`（仅肽序列）/ `MSiC`（+剪切位点上下文）/ `MSiCE`（+表达量）/ `MSiCEB`（+基因提呈偏好） | MSi（主路，仅提供肽序列） |
| `--alleles` | 预测的等位代号 | 实测 `A0101`（烟测）；benchmark 按各患者等位逐一调用 |

- 模型选择由提供的可选列自动决定：只给肽序列 → MSi；给上下文 → MSiC；给表达 → MSiCE。
- 部署方式：Docker `ssarkizova/hlathena-external:dev` 转 Singularity，参数与 Web server 一致。

---

## 4. 输出格式及含义

- **输出文件**：`<runID>-predictions.txt`（17 列）。
- **关键列**：
  - `MSi_<allele>`：**提呈概率分数**，连续值，**越高越可能被 HLA-I 提呈**。
  - `prank.MSi`：提呈分百分位排名。
  - `best.MSi_allele`：最佳匹配等位。
- **分数类型 / 方向 / 范围**：连续提呈概率，约 [0, 1]，越高越强提呈。参考阈值（MSiC，官方）：≥0.95 strong / ≥0.90 normal / ≥0.80 weak（MSi 是否适用同阈值待官方核实）。
- **能否定量免疫强弱**：❌ **否**——输出是提呈概率，不是免疫强弱分。
- **输出样例**（实测）：肽 `IDLLKEIY` 在等位 A0101 下 `MSi=0.844`。

---

## 5. 最新 benchmark 结果（DS2 ELISpot）

> 数据源：`analysis/metrics_ds2_16tools.csv` + `analysis/per_patient_spearman_16tools.csv`（2026-06-28 IMPROVE 跑通后全量重算）。
> ⚠️ HLAthena 为**提呈代理基线**，下列数字接近随机，**不与免疫原性工具同列比较**。

- **覆盖率**：n_pep = **92**（DS2 共 101 个肽中评得 92 个）。覆盖不全原因：本地仅有 A\*02:01 的 allele-specific 模型，其余 6 个罕见等位缺模型 → 对应肽段 NaN；per-patient 仅 8 名患者纳入（缺 1 名）。
- **per-patient Fisher-z 加权 ρ（主指标）**：**−0.011**，95% CI [−0.249, +0.228]（n_patients = 8，0 名被剔除）——CI 跨 0，无显著患者内相关。
- **全局 Spearman ρ（max 聚合，对照）**：ρ = **+0.091**（p = 0.390，不显著）。
- **AUC（max，SFC > 0）**：**0.415**。

**小结**：AUC ≈ 0.42、max 聚合 ρ ≈ +0.09 且不显著，per-patient CI 跨 0，整体接近随机。这印证了「提呈 ≠ 免疫原性」——提呈预测无法代理免疫强弱定量。

---

## 6. 部署环境简述

- **部署状态**：SMOKE_PASS（本机 WSL2 Docker，2026-06-24）；DS2 benchmark 以 A\*02:01 specific 模型部分跑通（92 肽）。
- **平台**：CPU 即可（小网络）。
- **路线**：WSL2 `docker pull` → `docker save` → SCP → HPC `singularity build`（HPC 无 Docker，但有 Singularity 3.11.3）。
- **关键坑 + 解**：镜像 standalone 运行时从作者 GCS bucket `gs://msmodels` 现拉模型（镜像内 /models 为空），内置 `gcloud_key.json` 凭证已失效（`buckets.get` 401）。解法：bucket 对象**匿名可下**，直接匿名下载所需模型文件（A0101 模型 + pan-pan CV + linear/ecdf，约 136MB），布置到 /models 与 /models_panpan，并 patch `predict_docker.bash` 关闭 `fetch_models`，再挂载本地模型运行。**注意勿下载整个 `models_panpan/` 前缀，会膨胀至数百 GB。**
- **未跑全量原因**：全量需下载全部约 65 个等位的 specific 模型（每个约 100MB，共约 6.5GB）+ R 端较慢；而 HLAthena 仅作提呈代理（预期近随机），投入产出比低，故停在 smoke-deployed + 部分 benchmark。
- 详细命令见同目录《环境配置命令_回顾记录.md》及 `scripts/hlathena/NOTES.md`。
