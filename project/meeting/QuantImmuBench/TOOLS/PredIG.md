# PredIG — 信息收集卡（PPT 素材）

> Wave 1（容器绕依赖）。事实来自官方 repo + 论文，实测项标 TODO。

## 0. 定位 / 一句话
T 细胞表位免疫原性预测（XGBoost），覆盖癌症新抗原 / 非经典抗原 / 病原体抗原三类；整合蛋白酶体切割 + TAP 转运 + HLA-I 结合 + 物化描述符等 12 个特征。**输出 PredIG score 连续 0-1 → 可定量排名。**

## 1. 输入数据模板 / 格式
- 三种模式（CSV 或 FASTA）：
  1. CSV-Uniprot：peptide / HLA-I allele / UniProt ID
  2. CSV-Recombinant：peptide / HLA-I allele / amino acid sequence
  3. FASTA：蛋白序列文件 + CSV（HLA-I allele 4 位分辨率，如 `HLA-A_02:01`）
- 肽段长度：FASTA 模式默认生成 8-14 AA 表位
- 是否需基因组数据：否
- **实测输入样例**：TODO

## 2. 运行参数设置
- 三类抗原特异模型可选：PredIG-NeoAntigen / PredIG-NonCanonical / PredIG-Pathogen
- 无暴露的超参调节接口
- **实测命令行**：TODO

## 3. 输出数据格式 + 含义
- 输出：CSV，列含 ID / epitope / HLA_allele / **PredIG score（0-1 连续概率，1=最高免疫原性）** + 12 个特征列
- 分数类型：连续
- **能否定量免疫强弱**：✅ 是（0-1 连续，可排名）+ 12 特征可解释
- **实测输出样例**：TODO

## 4. 简介（特点 / 优势）
- 方法：XGBoost（R），可解释（SHAP）
- 特点：三类抗原专用模型；提供官方容器
- 优势：连续分 + 可解释特征 + Docker/Singularity 容器（HPC 部署友好，绕大部分依赖）
- 局限：核心依赖外部工具（NetCleave / NetCTLpan / MHCflurry / NOAH），其中 NetCTLpan 可能需 DTU 许可（容器或已打包，待实测确认 → TODO）

## 部署记录
- repo：https://github.com/BSC-CNS-EAPM/PredIG ；容器 repo：https://github.com/BSC-CNS-EAPM/predig-containers
- 论文：*PredIG: an interpretable predictor of T-cell epitope immunogenicity*, Genome Medicine 2025, DOI 10.1186/s13073-025-01569-8
- 语言 / 框架：**R**（XGBoost 1.7.5.1 + shapforxgboost / ROCR / pROC / Peptides）
- 外部许可证工具：NetCleave v2.0 / NetCTLpan 1.1 / MHCflurry v2.0 / NOAH v1.0（NetCTLpan 可能需 DTU 许可，容器是否打包待核 TODO）
- GPU 需求：不需要
- **部署策略（实测确认）**：官方 Docker 镜像 `bsceapm/predig:latest` 打包全套 predictors（NetCleave/NOAH/netctlpan/MHCflurry）—— 主 repo 只有 R 脚本 + 模型，predictors 在镜像里。运行需挂载两个卷：工作目录→`/predig`、UniProt 库→`/uniprot`
- 命令结构：`docker run -v <workdir>:/predig -v <uniprotdir>:/uniprot bsceapm/predig <input> --output <out> --model {neoant|noncan|path}`
- **部署状态：✅ SMOKE_PASS**（2026-06-22）。镜像 `bsceapm/predig:latest`（14.4GB）已拉到本地（Docker Hub 经 VPN 本地代理 7897 拉成，daemon.json 配 proxies）。容器入口 `run.py`（在 /Immuno/）
- **实测命令**（recombinant 模式，避开 UniProt 库）：
  ```
  docker run --rm -v <workdir>:/work bsceapm/predig:latest /work/input.csv \
    -o /work/out.csv --modelXG neoant --type recombinant
  ```
  入参：`input_file`（位置参）+ `-o 输出` + `--modelXG {neoant|noncan|path}` + `--type {uniprot|recombinant|fasta}` + `--alleles`（fasta 模式用）
- 输入（recombinant）：CSV 列 `epitope,HLA_allele,protein_seq,protein_name`
- 输出（实测 out.csv，与 README 文档一致）：`ID,epitope,HLA_allele,PredIG,NOAH,NetCleave,Hydrophobicity_peptide,MW_peptide,Charge_peptide,Stab_peptide,TCR_contact,...` —— **PredIG 列 = 0-1 免疫原性分**（实测 SLLMWITQV=0.0061）
- 全链跑通：MHCflurry→NOAH→tapmat_pred_fsa(netCTLpan)→XGBoost，CPU 自动（无 GPU 警告无害）
- 烟测产物：`~/quantimmu/smoke/predig/out.csv`
