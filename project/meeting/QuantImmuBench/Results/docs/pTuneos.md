# pTuneos — 工具交付说明

> 交付文档（QuantImmuBench 新抗原免疫原性 benchmark，核心工具之一）。
> 涵盖六部分：工具简介 / 输入格式 / 参数设置 / 输出含义 / 最新 benchmark 结果（DS2 ELISpot）/ 部署环境。
> 全部基准数字已对 `analysis/metrics_ds2_16tools.csv` 与 `analysis/per_patient_spearman_16tools.csv` 逐一复核。

---

## 1. 工具简介

- **定位**：个性化新抗原**全流程优先级排序 pipeline**——从原始 WES / RNA-seq 出发，一站式产出新抗原排名。**不是单一免疫原性评分工具，而是端到端 pipeline。**
- **方法原理**：
  - **Pre&RecNeo**：随机森林（RandomForest）识别子模型，基于 5 个纯肽 + HLA 特征 `[Hydrophobicity, Recognition, Self_similarity, MT_Binding_EL, WT_Binding_EL]` 输出免疫原性识别概率；
  - **RefinedNeo**：在 Pre&RecNeo 基础上乘进表达量（TPM）、变异等位频率（VAF）、克隆性（cellular prevalence）等测序量，输出患者级综合优先级分（公式 `P = [A·tanh(E)·N·C]·…`）。
- **本项目的用法（关键）**：完整 RefinedNeo 需患者全基因组数据，无法只喂肽段；但其 **Pre&RecNeo 识别子模型只吃 3 列 TSV（MT_pep / WT_pep / HLA_type）**，可单独喂 ELISpot 肽段跑分，这正是 pTuneos 进入本 benchmark 的方式（与其它工具的 per-peptide 免疫原性分可比）。
- **特点与优势**：从测序数据一站式到排名；整合多组学特征（表达 / 加工 / 自身相似性）；识别子模型可单独跑肽段，与纯结合类工具互补。
- **主要局限**：**部署难度最高**——Python 2.7（EOL）+ Ubuntu 16.04 老链 + netMHCpan 许可 + 多工具协调；完整 RefinedNeo 必须全基因组，不能只给肽段；疏水性模型仅 9/10/11-mer，非此长度疏水性默认 0.5（其余 4/5 特征仍真实）。
- **出处**：
  - 论文：*pTuneos: prioritizing tumor neoantigens from next-generation sequencing data*, **Genome Medicine**, 2019，DOI [10.1186/s13073-019-0679-x](https://doi.org/10.1186/s13073-019-0679-x)。
  - 代码仓库：https://github.com/bm2-lab/pTuneos
- **许可证**：pTuneos 自身代码依上游 repo（bm2-lab/pTuneos）许可。**注意**：依赖的 netMHCpan-4.0（镜像内置）属 DTU 系工具，含其结果的对外 benchmark 发布受 DTU 学术许可约束。

---

## 2. 输入数据模板 / 格式

两类输入：

- **完整 pipeline**（不接受单纯肽段 CSV）：
  - WES 模式：原始 WES（FASTQ）+ RNA-seq + `config_WES.yaml`；
  - VCF 模式：突变 VCF（Mutect2）+ 表达谱（Kallisto）+ 拷贝数（sequenza）+ 肿瘤细胞含量 + HLA + `config_VCF.yaml`。
- **Pre&RecNeo 子模型**（本项目跑分用）：TSV 三列 `MT_pep<TAB>WT_pep<TAB>HLA_type`。
  - HLA 格式：星号型，如 `HLA-A*02:01`；
  - 示例：`MLGEQLFPL  MLGERLFPL  HLA-A*02:01`。

---

## 3. 参数设置

- **完整 pipeline**：通过 YAML 配置文件调各模块参数（vep_path / netMHCpan_path / pyclone_path / peptide_length / fpkm_cutoff 等）。
- **实测命令（完整 pipeline，example VCF）**：
  ```bash
  docker run -w /root/pTuneos bm2lab/ptuneos:v2.1 python pTuneos.py VCF -i config_VCF.yaml
  ```
- **实测命令（Pre&RecNeo 跑肽段，自写 wrapper `ptuneos_pre_recneo.py`）**：
  ```bash
  export PATH=/root/software/netMHCpan-4.0:$PATH
  python ptuneos_pre_recneo.py --input <peptides.tsv> --output <out.tsv> \
      --models /root/pTuneos/train_model --blastdb <blastdb>/peptide --nproc 20
  ```
  （wrapper 复刻官方 `InVivoModelAndScore()` 的 5 特征 → RF predict_proba；对官方 example 40 肽对账 `model_pro` 完全一致，r = 1.0。）

---

## 4. 输出格式及含义

- **Pre&RecNeo（`model_pro`）**：免疫原性识别概率（0–1 连续），RF 基于 5 个纯肽 + HLA 特征 → **这是与其它工具可比的 per-peptide 免疫原性分（越高越免疫原）**。
- **RefinedNeo（`combined_prediction_score` / `immuno_effect_score`）**：患者级优先级排序分，乘进表达量 / VAF / 克隆性 → 需肿瘤测序，**非 per-peptide 可比量**。
- **方向**：分数越高越免疫原 / 越优先。
- **范围**：`model_pro` ∈ [0, 1]；完整 pipeline 的 `combined_prediction_score` 实测范围约 0.42–1.13。
- **⚠️ 重要特性**：`model_pro` **高度零膨胀（约 93% 为 0.0，RF predict_proba 仅量化为 ~10 个挡位）** → pTuneos 本质偏「有 / 无免疫原性」二分器，连续强弱排序能力有限。

---

## 5. 最新 benchmark 结果（DS2 ELISpot）

> 数据集 DS2（ELISpot 验证集）；2026-06-28 全量重算的 16 工具榜单。主指标为逐患者 Fisher-z，对照口径为全局 Spearman（max 聚合），AUC 取 SFC > 0。

- **覆盖率**：肽级口径 **n_pep = 101**（满覆盖）；子肽行口径（34247 行）下 MT_pTuneos 主输出覆盖 **100%（34247/34247）**（Pre&RecNeo 子模型）；hydro_defaulted 标记 **88.3%**。
- **逐患者一致性（per-patient，9 名患者，Fisher-z 加权，主指标）**：fisherz_weighted = **+0.121**，95% CI **[−0.112, +0.341]**（跨 0，不显著）。
- **全局 Spearman ρ（max 聚合，对照）**：ρ = **+0.119**（p = 0.238，**不显著**）。
- **AUC（max，SFC > 0）**：**0.718**。
- **结论（诚实标注）**：pTuneos 的 **AUC（`>0`）= 0.718 在四工具中最高**，「能不能引出反应」的二分判别较强；但 **Spearman 相关不显著**、`model_pro` 严重零膨胀，**对免疫反应「强弱程度」的连续定量能力弱**。这与其工具定位一致（识别 + 优先级，而非连续强弱评分）。
- **caveat**：本结果来自 **Pre&RecNeo 子模型**（非完整 RefinedNeo pipeline）；DS2 阴性样本仅 11 个，排名类指标的统计功效有限。

---

## 6. 部署环境简述

- **环境类型**：官方 Docker 镜像隔离 Python 2.7 / Ubuntu 16.04 老环境（`bm2lab/ptuneos:v2.1`，5.03GB；tag 仅 v2.1，无 `:latest`）。CPU 推理。
- **镜像自带**：netMHCpan-4.0（`/root/software/netMHCpan-4.0`，免单独申请）、netchop、netctlpan_1.1、netMHCpan-2.3、VCF/WES example 数据、主程序 `/root/pTuneos/pTuneos.py`。
- **部署状态**：本地 WSL2 docker 已端到端验证（example VCF 跑出 40 新抗原 + Pre&RecNeo 跑通 ELISpot 进 benchmark）。**HPC 端 `ptuneos.sif`（1.7GB）已 build，但 Singularity 非 root / 无 fakeroot 无法访问镜像内 `/root` → HPC 未真跑**，以上为本地 docker 验证结果。
- **关键坑**：①完整 pipeline 唯一缺口曾是 VEP cache（真实人类基因组注释库 ~15GB，镜像只带 dummy，已自行下完）；②老 netMHCpan 二进制在 WSL 下会 segfault → 内核加 `vsyscall=emulate` 解决；③连环修复 8 个老代码 / 缺库坑（详见 04_LOG Entry 19）。
- **详细逐条命令**见同目录《环境配置命令_回顾记录.md》，此处不重复。
