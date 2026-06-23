# pTuneos — 信息收集卡（PPT 素材）

> Wave 2（最难，依赖学术许可 + 老环境 + 全基因组数据）。事实来自官方 repo + 论文。

## 0. 定位 / 一句话
个性化新抗原**全流程优先级排序 pipeline**——从原始 WES/RNA-seq 出发，5 个免疫原性特征构 ML 分类器（Pre&RecNeo）+ 综合打分（RefinedNeo）输出排名。**非单一免疫原性评分工具，是端到端 pipeline。**

## 1. 输入数据模板 / 格式
- **WES 模式**：原始 WES（FASTQ）+ RNA-seq + `config_WES.yaml`
- **VCF 模式**：突变 VCF（Mutect2）+ 表达谱（Kallisto）+ 拷贝数（sequenza）+ 肿瘤细胞含量 + HLA + `config_VCF.yaml`
- 完整 pipeline **不接受单纯肽段 CSV**，需配套患者基因组数据（官方核实：RefinedNeo 公式 `P=[A·tanh(E)·N·C]·…`，A=VAF / E=TPM / C=cellular prevalence 全来自测序，乘法关系任缺则 P=0）。
- **⭐ 例外（关键发现）**：pTuneos 内部的 **Pre&RecNeo 识别子模型**（输出列 `model_pro`）**只吃 5 个纯肽+HLA 特征** `[Hydrophobicity, Recognition, Self_similarity, MT_Binding_EL, WT_Binding_EL]`，输入 TSV 仅 `MT_pep / WT_pep / HLA_type` 三列 → **可单独喂 ELISpot 肽段跑分**（绕过 VCF→VEP 链）。这是我们让 pTuneos 进 5 工具 benchmark 的方式（见下「ELISpot 跑分」）。
- **实测输入样例**：
  - 完整 pipeline（VCF 模式）：`config_VCF.yaml` + VCF_example_data（镜像自带）
  - Pre&RecNeo（肽段模式）：TSV 三列 `MT_pep<TAB>WT_pep<TAB>HLA_type`（如 `MLGEQLFPL  MLGERLFPL  HLA-A*02:01`）

## 2. 运行参数设置
- 通过 YAML 配置文件（config_WES.yaml / config_VCF.yaml）调各模块参数（vep_path / netMHCpan_path / pyclone_path / peptide_length / fpkm_cutoff 等）
- **实测命令行（完整 pipeline，example VCF）**：
  ```bash
  docker run -w /root/pTuneos bm2lab/ptuneos:v2.1 python pTuneos.py VCF -i config_VCF.yaml
  ```
- **实测命令行（Pre&RecNeo 跑肽段，自写 wrapper `ptuneos_pre_recneo.py`）**：
  ```bash
  export PATH=/root/software/netMHCpan-4.0:$PATH
  python ptuneos_pre_recneo.py --input <peptides.tsv> --output <out.tsv> \
      --models /root/pTuneos/train_model --blastdb <blastdb>/peptide --nproc 20
  ```
  （wrapper 复刻官方 `InVivoModelAndScore()` 的 5 特征→RF predict_proba，批 netMHCpan/blastp 加速；对官方 example 40 肽对账 model_pro 完全一致 r=1.0）

## 3. 输出数据格式 + 含义
- **Pre&RecNeo（`model_pro`）**：免疫原性识别概率（0-1 连续），RF 模型基于 5 个纯肽+HLA 特征 → **这是与其他 4 工具可比的 per-peptide 免疫原性分**。
- **RefinedNeo（`combined_prediction_score` / `immuno_effect_score`）**：患者级**优先级排序**分，在 Pre&RecNeo 基础上乘进表达量/VAF/克隆性 → 需肿瘤测序，非 per-peptide 可比量。
- 患者水平：所有表位 RefinedNeo 分之和 = 总体免疫原性指标
- 分数类型：连续排名分
- **能否定量免疫强弱**：✅ 是
- **实测输出样例（完整 pipeline，example VCF）**：`scripts/out/ptuneos_example/test_final_neo_model.tsv`（40 新抗原 × 28 列；`combined_prediction_score`=RefinedNeo 范围 **0.42072–1.12834**；全 HLA-A\*02:01 单患者；核心列 Recognition_score / Hydrophobicity_score / Self_sequence_similarity / MT,WT_Binding_EL / model_pro / cellular_prevalence）。
- **实测输出样例（Pre&RecNeo，ELISpot 肽段）**：`scripts/ptuneos/ptuneos_unique_output.tsv`（32178 唯一肽对，列加 model_pro + hydro_defaulted）→ 合表 `scripts/out/merged_all_tools_5tools.xlsx`（列 MT_pTuneos）。
  - **benchmark 结果（DS2, metrics_ds2.csv 核实）**：pTuneos **AUC-ROC 最高**（max/>0=0.7525、mean/>0=0.7813，全 5 工具第一）；但 >10/>median 阈值掉到 0.46–0.58（门槛效应）；Spearman ρ=0.136（p=0.174，不显著）。
  - **特点**：model_pro 高度零膨胀（~93% 为 0.0，RF predict_proba 量化 10 挡）→ pTuneos 本质是"有/无免疫原性"二分器（二分强），不适合连续强弱排序。caveat：DS2 阴性仅 11，排名非统计显著。

## 4. 简介（特点 / 优势）
- 方法：ML 分类器（Pre&RecNeo, RandomForest 5 特征）+ 综合打分函数（RefinedNeo），端到端 pipeline
- 特点：从原始测序数据一站式到排名；患者级聚合指标；识别子模型可单独跑肽段
- 优势：定量 + 整合多组学特征（表达/加工/自身相似性）；Pre&RecNeo 与 binding-only 工具互补
- 局限：**部署难度最高**——Python 2.7（EOL）+ Ubuntu 16.04 老链 + netMHCpan 许可 + 多工具协调；完整 RefinedNeo 需全基因组（不能只给肽段），仅 Pre&RecNeo 可吃纯肽。疏水性模型仅 9/10/11mer，非此长度疏水性默认 0.5（4/5 特征仍真实）。

## 部署记录
- repo：https://github.com/bm2-lab/pTuneos
- 论文：*pTuneos: prioritizing tumor neoantigens from next-generation sequencing data*, Genome Medicine 2019, DOI 10.1186/s13073-019-0679-x
- 语言 / 框架：**Python 2.7（EOL）** + R 3.2.3 + sequenza 2.1.2
- 外部工具（需单独装/许可）：**NetMHCpan 4.0（DTU 学术许可）** + VEP + GATK 3.8 + Picard + BWA + samtools + kallisto + OptiType
- GPU 需求：不需要（但测试环境 88 核 256GB RAM）
- 部署策略：官方 Docker 镜像隔离 Py2.7/Ubuntu16.04 老环境。**镜像 = `bm2lab/ptuneos:v2.1`**（5.03GB；`:latest` 不存在，tag 仅 v2.1，Docker Hub API 查得）已拉到本地
- **🎯 镜像自带全套（实测，2026-06-22）**：
  - **netMHCpan-4.0 打包在 `/root/software/netMHCpan-4.0`** → **不用单独申请 netMHCpan-4.0 许可**（镜像内含）
  - netchop / netctlpan_1.1 / netMHCpan-2.3 也自带
  - **VCF_example_data + WES_example_data 都在** `/root/pTuneos/`，config_VCF.yaml / config_WES.yaml 现成
  - pTuneos 主程序 `/root/pTuneos/pTuneos.py`
- VCF 模式输入（config_VCF.yaml）：vcf_file(mutect2) + expression(Kallisto tsv) + copynumber(sequenza) + tumor_cellularity + hla_str + peptide_length=9 —— example 全有，跳过比对，**轻**
- **部署状态：✅ example VCF 端到端跑通 + Pre&RecNeo 跑 ELISpot**（2026-06-23）。
  - ① 完整 pipeline（本地 WSL2 docker）：VEP cache 14G 下完 + 连环修 8 个老代码/缺库坑 → 出 40 新抗原 RefinedNeo 分（`scripts/out/ptuneos_example/test_final_neo_model.tsv`）。8 坑见 04_LOG Entry 19。
  - ② Pre&RecNeo 跑 ELISpot：抠出识别子模型（5 纯肽特征 RF），批处理 wrapper 跑 32178 唯一肽对 → 进 5 工具 benchmark（对账官方 example r=1.0）。
  - **HPC 状态**：ptuneos.sif（1.7G）已 build，但 singularity 非 root 访问 /root 拒 + 无 fakeroot + VEP cache 缺 → **HPC 未真跑，以上为本地 docker 验证**。HPC 真跑需 fakeroot 或重打包到非 /root。
- 旧缺口（已解）：~~VEP cache~~ 已下完解压验证；~~end-to-end 卡 vep path~~ 已通。
- **镜像内真实工具路径**（config 占位符 `your/path/to/...` 须改成这些）：
  - vep_path = `/root/software/ensembl-vep/vep`
  - netMHCpan_path = `/root/software/netMHCpan-4.0/netMHCpan`
  - pyclone_path = `/usr/local/bin/PyClone`
  - 自带：GATK/BWA/samtools/kallisto/picard/vcftools/trimmomatic（/root/software/）
- **唯一缺口 = VEP cache**（真实人类基因组注释库 GRCh37/38，~15-25GB，**镜像只带 dummy 测试 cache**，需 `vep_install` 或官方下载到 `vep_cache_path`）。这是 end-to-end 跑通的最后一块。
- 内核修复：WSL `vsyscall=emulate` 已开 → 容器内老 netMHCpan 二进制不再 segfault
- example 烟测：`docker run -w /root/pTuneos bm2lab/ptuneos:v2.1 python pTuneos.py VCF -i config_VCF.yaml`（改好路径 + 备 VEP cache 后）
