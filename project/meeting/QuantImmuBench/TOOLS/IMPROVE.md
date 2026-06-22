# IMPROVE — 信息收集卡（PPT 素材）

> Wave 2（依赖学术许可）。事实来自官方 repo + 论文，实测项标 TODO。

## 0. 定位 / 一句话
随机森林预测新表位（neoepitope）免疫原性，基于 22 个特征（MHC 结合亲和力 + PRIME TCR 识别分 + 肽段疏水性 + 肿瘤微环境特征等）；三个变体（Simple / TME_excluded / TME_included）。**输出连续 0-1 概率 → 专为排名优先级设计。**

## 1. 输入数据模板 / 格式
- 文件格式：TSV（tab 分隔）
- 必填列：mutant peptide sequence + wild-type peptide sequence + HLA allele（4 位分辨率）
- 可选列：表达量 / 细胞普遍率 / 肿瘤微环境参数（决定用哪个模型变体）
- 肽段长度：8-12 AA
- 是否需基因组数据：TME 变体需 RNA-seq（Kallisto）；Simple 变体只要肽段+HLA
- **实测输入样例**：TODO

## 2. 运行参数设置
**⚠️ 两步流程**（关键结构，2026-06-22 实测）：
- **步骤 1 `bin/feature_calculations.py`**：算 22 特征，需全套外部工具
  - `--file <输入tsv>` `--dataset <名>` `--ProgramDir <外部工具根目录>` `--outfile <算好特征tsv>` `--TmpDir <临时目录>`
  - 外部工具(netMHCpan/netMHCstabpan/PRIME/MixMHCpred/self_similarity)放同一 `--ProgramDir` 文件夹
- **步骤 2 `bin/Predict_immunogenicity.py`**：在算好的特征上跑 RF 集成（**零外部工具**）
  - `--file <算好特征tsv>` `--model {Simple|TME_excluded|TME_included}` `--outfile <输出tsv>`
  - 每变体加载 5 个 RF（rf0-rf4 集成）
- 三变体：Simple（肽段+HLA 即可）/ TME_excluded（+MuPeXI PrioScore + PyClone 细胞普遍率）/ TME_included（+RNA-seq CYT + MCP-Counter）
- 注：repo 自带 `data/calculated_features_test.tsv`（已算好特征）→ **步骤 2 可独立先跑通验证模型+输出格式**
- **实测命令行**：跑通后补

## 3. 输出数据格式 + 含义
- 输出：TSV（输入全列 + 追加预测列），关键列 **`mean_prediction_rf`** = 5-fold×50 RF 集成平均的免疫原性概率（连续 0-1，越高越强）
- 三变体各出一分（Simple/TME_excluded/TME_included）
- 分数类型：连续
- **能否定量免疫强弱**：✅ 是（连续概率，设计上就用于排名优先级）
- **实测输出样例**（✅ 2026-06-22 Predict Simple，100 行）：
  ```
  Mut_peptide    HLA_allele   mean_prediction_rf
  EEFLNSWML      HLA-B40:02   0.5146
  KAQPVTQATSF    HLA-B07:02   0.2459
  SVQTAKGMALF    HLA-A26:01   0.3193
  ```

## 4. 简介（特点 / 优势）
- 方法：RandomForest（22 特征，广泛 T 细胞识别数据验证）
- 特点：三变体适配有无 TME 数据
- 优势：连续分 + 专为新表位排名设计 + 整合 TCR 识别（PRIME）
- 局限：**外部工具链多且部分需学术许可**（部署主要卡点）

## 部署记录
- repo：https://github.com/SRHgroup/IMPROVE_tool ；论文 repo：https://github.com/SRHgroup/IMPROVE_paper
- 论文：*IMPROVE: a feature model to predict neoepitope immunogenicity through broad-scale validation of T-cell recognition*, Frontiers in Immunology 2024, DOI 10.3389/fimmu.2024.1360281
- 语言 / 框架：Python 3.7.6 + scikit-learn（RandomForestClassifier）；预训练 **models.zip = 1.9GB 经 git-lfs**（`--depth 1` clone 只得 135B 指针，须 `git lfs pull`）
- **外部许可证工具（步骤1 feature_calc 卡点）**：
  - NetMHCpan 4.1 ✅ 已装跑通（`~/quantimmu/ext_tools/netMHCpan-4.1`）
  - NetMHCstabpan 1.0（Stability 特征）✅ **已通**（`~/quantimmu/ext_tools/netMHCstabpan-1.0`）—— 后端 netMHCpan-2.8 也 ✅ 通。原 2.8 在 WSL2 segfault，根因=内核 `CONFIG_LEGACY_VSYSCALL_NONE=y`，修法=WSL `.wslconfig` 加 `kernelCommandLine=vsyscall=emulate` 重启 → 老二进制不崩。**HPC 不用了**。另：netMHCstabpan 也要单独下 data.tar.gz(6.8MB) 才有 data/version
  - PRIME / MixMHCpred（Gfeller，免许可）✅ 已 clone `~/quantimmu/tools_repos/`
  - self_similarity（github SRHgroup/self_similarity）+ MuPeXI + MCP-Counter（TME 变体）+ antigen.garnish（Foreignness）：待补
- GPU 需求：不需要（RF）
- 部署状态：✅ **步骤2(Predict) SMOKE_PASS**（2026-06-22 Simple 变体自带 example 跑通，输出 mean_prediction_rf 100 行）；步骤1(feature_calc) 卡 netMHCstabpan(2.8 segfault)，待 HPC 补
- **环境坑（重要）**：models.zip 里是**用 numpy 2.x retrained 的 pkl** → 必须用现代环境 + `Predict_immunogenicity_CLEAN_retrain.py`（不是 py3.7 老脚本，老环境报 `No module named numpy._core`）。建 conda env `improve_new` = python3.11 + numpy2.4 + scikit-learn1.9 + pandas3.0（sklearn 版本不符只警告不报错，能加载）。retrain 脚本 `base_dir` 硬编码需改成本机 repo 路径。
- repo 路径：`~/quantimmu/tools_repos/IMPROVE_tool`（models.zip 经 git-lfs 解压到 models/<变体>/，各 250 pkl）
- 烟测产物：`~/quantimmu/smoke/improve/out_simple.tsv`
