# DeepImmuno — 信息收集卡（PPT 素材）

> Wave 1（最易，先上）。事实来自官方 repo + 论文，实测项标 TODO。

## 0. 定位 / 一句话
深度学习（CNN）预测肽段对 CD8+ T 细胞的免疫原性（HLA-I 限制）；附带 GAN 生成免疫原性肽段功能。**输出连续 0-1 免疫原性分 → 可用于强弱排名。**

## 1. 输入数据模板 / 格式
- 文件格式：CSV
- 必填列：peptide 序列 + HLA allele
- **肽段长度限制：仅支持 9-mer 和 10-mer**（其他长度输出归零）
- HLA 格式：如 `HLA-A*0201`、`HLA-B*5801`
- 是否需基因组数据：否（只要肽段 + HLA）
- **实测输入样例**（✅ 2026-06-22 WSL 跑通）：批量模式输入 = **无表头 CSV，两列 `peptide,HLA`**：
  ```
  HPPLMNVER,HLA-A*0201
  NLVPMVATV,HLA-A*0201
  GILGFVFTL,HLA-A*0201
  ```

## 2. 运行参数设置
- 无暴露超参；CNN（打分）与 GAN（生成）为两个独立模块
- 两种运行模式：
  - `--mode single --epitope <肽段> --hla <HLA>`（单条，结果打印到 stdout）
  - `--mode multiple --intdir <输入csv> --outdir <输出目录>`（批量；⚠️ outdir 末尾不带斜杠）
- **实测命令行**（✅ 跑通）：
  ```
  python deepimmuno-cnn.py --mode single --epitope HPPLMNVER --hla "HLA-A*0201"
  python deepimmuno-cnn.py --mode multiple --intdir input.csv --outdir <out>
  ```
  （须在 repo 根目录运行——脚本用相对路径 `./data/`、`./models/` 读权重）

## 3. 输出数据格式 + 含义
- 单条模式：stdout 直接打印分数（如 `0.5324646830558777`）
- 批量模式：输出文件 **`deepimmuno-cnn-result.txt`**，**tab 分隔**，3 列：
  | 列 | 含义 |
  |---|---|
  | peptide | 肽段序列 |
  | HLA | HLA 等位基因 |
  | immunogenicity | 免疫原性分（连续 0-1，越高越强）|
- 分数类型：连续（作者声明无绝对阈值，常用 0.5 参考）
- **能否定量免疫强弱**：✅ 是（连续 0-1，可排名）
- **实测输出样例**（✅ 2026-06-22）：
  ```
  peptide    HLA          immunogenicity
  HPPLMNVER  HLA-A*0201   0.5324648
  NLVPMVATV  HLA-A*0201   0.95676666   # CMV pp65, 已知强免疫 → 高分合理
  GILGFVFTL  HLA-A*0201   0.8871707    # 流感 M1, 已知强免疫 → 高分合理
  ```

## 4. 简介（特点 / 优势）
- 方法：CNN（基于肽段 + HLA 伪序列）
- 特点：兼有预测 + GAN 生成；提供 Web 服务器（deepimmuno.research.cchmc.org）
- 优势：纯肽段+HLA 即可，无需基因组数据，无许可证工具依赖，CPU 可跑
- 局限：**肽段长度死限 9/10-mer**

## 部署记录
- repo：https://github.com/frankligy/DeepImmuno
- 论文：*DeepImmuno: deep learning-empowered prediction and generation of immunogenic peptides for T-cell immunity*, Briefings in Bioinformatics 2021, DOI 10.1093/bib/bbab160
- 语言 / 框架：Python 3.6+；**TensorFlow 2.3.0**（CNN）+ PyTorch 1.4.0（GAN）；NumPy 1.18.5 / Pandas 1.1.1
- 外部许可证工具：无
- GPU 需求：非强制，CPU 可运行
- 坑：TF 2.3 较老 → **protobuf 必须降到 3.20.3**（否则 `Descriptors cannot be created directly` 报错）；CUDA10.1 库缺失会自动回退 CPU（推理够快，无需 GPU）
- 部署状态：✅ **SMOKE_PASS**（2026-06-22 WSL2 Ubuntu24.04 本地跑通单条+批量两模式）
- **部署环境**：WSL2 Ubuntu 24.04，conda env `deepimmuno`（python3.8 + tensorflow==2.3.0 + numpy==1.18.5 + pandas==1.1.1 + protobuf==3.20.3）
- **repo 路径**：`~/quantimmu/tools_repos/DeepImmuno`（WSL 原生 ext4；Windows NTFS 因 repo 含 `HLA-A*0101.json` 非法 `*` 文件名无法 checkout）
- 烟测产物：`~/quantimmu/smoke/deepimmuno/deepimmuno-cnn-result.txt`
