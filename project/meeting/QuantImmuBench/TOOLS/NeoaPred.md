# NeoaPred — 信息收集卡（PPT 素材）

> 结构 foreignness 路线（绕序列特征，从复合物三维结构打分）。事实来自官方 repo + 论文 + 本项目实测，待全量补的项标「全量 HPC 跑中，待补」。

## 0. 定位 / 一句话
基于**结构 foreignness（结构异己性）** 的新抗原免疫原性预测工具。两个子模型串联：**PepConf**（从肽-HLA 序列预测复合物三维结构）→ **PepFore**（在三维结构上对突变肽相对野生肽的「异己程度」打分）。**输出 Foreignness_Score 连续值（约 0-1，越高免疫原性越强）→ 可定量排名**。论文报告 AUROC 0.81 / AUPRC 0.54。

## 1. 输入数据模板 / 格式
- 文件格式：CSV
- 必填列 / 字段：`ID,Allele,WT,Mut`（PepFore 模式需突变肽 Mut + 野生肽 WT **配对**；PepConf 模式只需 `ID,Allele,Pep`）
- 肽段长度限制：论文 7-14 mer 可跑，**最优 8-9 mer**；本项目按**严格 9 mer**口径，非 9 mer 子肽填 NaN
- HLA 格式：**缩写型 `A2402`**（⚠️ 非 `HLA-A*24:02`；规则 = 去 `HLA-` / 去 `*` / 去 `:`）；内置 200 个 HLA-I 模板（66 个 A + 105 个 B + 29 个 C，累计频率 > 0.94）
- 是否需基因组数据（RNA-seq/VCF/表达量）：否
- **实测输入样例**（PepFore 模式，WT/Mut 各 9 aa）：
  ```
  ID,Allele,WT,Mut
  ID_0,A2402,RLETIRDPK,RLETIRNPK
  ```

## 2. 运行参数设置
- 主要参数：
  - `--input_file <csv>`：输入 CSV
  - `--output_dir <dir>`：输出目录
  - `--mode {PepFore|PepConf}`：**PepFore = 结构 + foreignness 全链路**（项目所用）；**PepConf = 只预测结构**
- 模型变体 / 模式选择：见上 `--mode`
- GPU 需求：**非强制**（OpenMM 结构弛豫吃 CPU；可设 `OMP_NUM_THREADS` / `OPENMM_CPU_THREADS` 限制线程数）
- **实测命令行**：
  ```
  neoapred --input_file input.csv --output_dir out/ --mode PepFore
  ```

## 3. 输出数据格式 + 含义
- 输出文件：`<output_dir>/Foreignness/MhcPep_foreignness.csv`
- 关键列 + 含义：`ID,Allele,WT,Mut,Foreignness_Score` —— **`Foreignness_Score` = 结构异己性分，越高免疫原性越强；> 0.5 视为候选新抗原**，范围约 [0, 1]
- 分数类型：连续
- **能否定量免疫强弱**：✅ 是（连续 Foreignness_Score，可排名）← 项目核心目标
- 中间产物：`InitPep/`（初始结构）+ `Structure/`（`*_relaxed.pdb` 弛豫后构象）
- ⚠️ OpenMM 弛豫**非确定性**：同一肽多次运行分数会略有差异（同量级）
- **实测输出样例**：本地 5 肽端到端烟测产出真实分数 0.0003–0.0008（全量 benchmark 结果：全量 HPC 跑中，待补）

## 4. 简介（特点 / 优势）
- 方法：深度学习两段式 —— PepConf（序列→肽-HLA 复合物结构）+ PepFore（结构 foreignness 打分）
- 训练数据：免疫原性标注的肽-HLA 数据（论文报告 AUROC 0.81 / AUPRC 0.54）
- 特点 / 优势：
  - **结构路线**：直接从三维复合物结构提取异己性，而非只靠序列/结合亲和力特征，机制角度互补于序列类工具
  - 输出连续分可定量排名，> 0.5 给出候选阈值
  - 内置 200 个 HLA-I 模板（覆盖累计频率 > 0.94）
  - 外部结构工具（MSMS / APBS / PDB2PQR / PDB2XYZRN）已随镜像内置
- 局限：
  - **严格依赖 Python 3.6**（PyMesh2 0.1.14 锁死）→ 必须容器隔离
  - **HLA 与肽长口径苛刻**：HLA 须用缩写型、最优 8-9 mer，本项目按严格 9 mer 取子肽
  - OpenMM 弛豫**非确定性 + 算力重**（全量 5692 个 unique 9 mer × 2 = 11384 次弛豫，本地 ~60 h 不可行，弛豫不随并行线性加速，受内存带宽限制）
  - PepFore 只对突变肽（MT）打 foreignness，本项目输出仅产 `MT_NeoaPred` 列

## 部署记录
- repo：https://github.com/Dulab2020/NeoaPred
- 论文：*NeoaPred*（structure-based foreignness 免疫原性预测）, Bioinformatics 2024, DOI 10.1093/bioinformatics/btae547（AUROC 0.81 / AUPRC 0.54）
- 语言 / 框架 / 依赖：Python **3.6 锁死**（PyMesh2 0.1.14）+ OpenMM（结构弛豫）
- 外部许可证工具：MSMS / APBS / PDB2PQR / PDB2XYZRN（均随镜像内置，env 在 `/var/software`）；许可证 **Apache-2.0**
- Docker 镜像：`panda1103/neoapred:1.0.0`
- GPU 需求：非强制（弛豫为 CPU 计算）
- **部署状态：✅ SMOKE_PASS（本地 + HPC），全量跑中**
  - 本地 WSL2 Docker 端到端 5 肽烟测 **PASS**（真实分数 0.0003–0.0008）
  - 全量 5692 个 unique 9 mer（DS1 + DS2 的 9 mer 子肽，共 11384 次弛豫）本地 ~60 h 不可行 → 转 HPC
  - HPC 路径：`docker save`（3.6 GB）→ `singularity build` → gpu4090 节点 48 核并行 `sbatch`（job **1496520**，跑中）
  - HPC Singularity 烟测同样 **PASS**（env 全在 `/var/software` 而非 `/root`，非 root 可读，绕过权限坑）
- scope：严格 9 mer；非 9 mer 子肽填 NaN；PepFore 只打 MT foreignness → 仅产 `MT_NeoaPred` 列
- 全量 benchmark 分数 / 性能复现：全量 HPC 跑中，待补
