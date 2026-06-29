# neoag — 部署说明（QuantImmuBench §工具部署 第 30 工具，免疫原槽收尾）

> 建档：2026-06-29。服务 quantimmu-bench §工具部署 lever=补满 30 工具最后 1 个免疫原槽（替搁置 NeoaPred）。
> repo：**github.com/vincentlaboratories/neoag**
> 论文：Cancer Immunol Res 2019, **DOI 10.1158/2326-6066.CIR-19-0155**
> 许可：**non-commercial research license**（学术非商用，**数字可发表**）。
> 模型：R/caret **GBM**，权重自带 repo 内 `Final_gbm_model.rds`。
> 运行：**CPU 秒~分钟级**（GBM predict 轻量，无 GPU/无外部二进制依赖）。

---

## ⚠️⚠️ 头号告警：官方 API 未核（本机无外网）

部署时本机 Bash **无外网**（`curl github HTTP 000 / SSL exit 35`），**未能直连核 neoag 官方 repo**。
按红线「查不到标 TODO 绝不臆造」，下列 neoag 专属细节**全部标 TODO，待主窗 clone repo 后核实**：

| 未核项 | 当前占位（best-guess，需核） | 在哪改 |
|---|---|---|
| 官方 input CSV 列名 / 格式 | 本部署用 canonical 列 `mt_peptide,wt_peptide,mut_pos_1based`，由 run_neoag.R 适配官方 feature 函数 | run_neoag.R §`build_official_input` |
| 突变位号 base | **1-based 肽内位置**（差异残基在肽中第几位，从 1） | prep_input.py `POS_BASE` 常量 |
| 官方特征 R 脚本 + 函数名 | **空占位**（`OFFICIAL_R_SOURCES`/`FEATURE_FN_NAME`，未填则 R 硬停） | run_neoag.R §OFFICIAL API ADAPTER |
| predict 取分方式 | `type="prob"` + 正类列名（未填）；caret GBM 常见 | run_neoag.R `PREDICT_TYPE`/`PREDICT_POS_CLASS` |
| 分数方向 | **越高越免疫原 → 不翻转**（默认） | parse_output.py `DEFAULT_FLIP` / patch `FLIP` |
| `Final_gbm_model.rds` 在 repo 内路径 | 默认 `<repo>/Final_gbm_model.rds` | run_neoag.R `--model` / 默认值 |

> **绝不在未核实下输出臆造分数**：run_neoag.R 的 `compute_neoag_scores()` 在 ADAPTER 未填妥时
> `stop()` 硬停并打印需填什么。主窗 clone 后按 README + `R/` 目录脚本 + rds 训练特征名填妥再跑。

---

## 工具简介

预测**突变肽（neoantigen）的免疫原性**。模型吃 **mutant 肽 + WT/reference 肽 + 突变位号**（**不吃 HLA**），
经 GBM 输出连续 immunogenicity score。**肽-对级**打分（一个 (MT,WT) 对 → 一个分），HLA-agnostic。

---

## 4 类信息（工具横评标准格式）

| 项 | 值 |
|----|----|
| 工具版本 | neoag（GitHub vincentlaboratories，⚠️TODO 核 branch/tag） |
| 许可 | non-commercial research license（数字可发表，学术非商用） |
| 输入格式 | mutant 肽 + WT 肽 + 突变位号（**不吃 HLA**）；8-11mer；⚠️TODO 核官方确切列名/位号 base |
| 输出分数 | 连续 immunogenicity score（GBM）；⚠️TODO 核方向（默认越高越免疫原） |
| 运行平台 | **CPU 秒~分钟级**（R/caret GBM，无外部二进制） |
| 分类 | 序列特征 GBM，**肽-对级**(MT vs WT)，HLA-agnostic，突变肽免疫原性 |

---

## 输入格式（重要 caveat）

- neoag 吃 **(mutant 肽, WT 肽, 突变位号)**，**不吃 HLA** → 同一 (MT,WT) 对对所有 HLA_Allele 行广播同值
  （同 Repitope / TransHLA 的 HLA-agnostic 处理）。
- 突变位号由 **MT_Subpeptide vs WT_Subpeptide 逐位比对取差异残基 index** 算得（prep_input.py）。
- **只取恰好 1 个残基差异的对**：0 差异(同肽) / >1 差异 / MT≠WT 长度 → 记入 `neoag_skipped.csv`，parse 填 NaN。
- 肽长 **8-11mer**（Class-I 范围；MT/WT 须同长才能定义单残基替换）。

---

## 分数方向（⚠️TODO 官方未核）

| 原始输出 | 默认方向 | 输出列 | 变换 |
|---|---|---|---|
| GBM immunogenicity score | **越高越免疫原（默认，待核）** | `MT_Neoag` | **不翻转直接用**（默认） |

- ⚠️ 主窗 clone 后核官方 README 方向：若**越低越免疫原** → parse_output.py 加 `--flip`（或 patch `FLIP=True`）取负。
- `WT_Neoag` **结构性全 NaN**：neoag 不对 WT 单独打 neoantigen 分（WT 只作参考）；保留列仅为 MT_/WT_ 双列 schema 对齐，主线可丢弃。

---

## 部署四件套（本目录）

| 文件 | 作用 |
|---|---|
| `prep_input.py` | universe.csv → unique (MT,WT) 对 + 8-11mer 过滤 + 单残基突变位号 → `neoag_input.csv` + skipped |
| `run_neoag.R` | 官方 GBM 忠实包装（setwd(repo) + source 官方 R + load rds + predict，算法零改）；⚠️含待填 OFFICIAL API ADAPTER |
| `run_neoag.py` | 启动器：调 Rscript run_neoag.R（无逐 HLA 分组，单次跑全 input），产 `neoag_raw.csv` |
| `parse_output.py` | neoag_raw.csv 按 (MT,WT) 对 join universe → 同对各 HLA 广播 → `Neoag_DS1DS2_scores.csv` |
| `NOTES.md` | 本文件 |

合表补丁（在 scripts/ 下，不在本目录）：`scripts/patch_add_neoag.py`（base 24tools → out 25tools）。

---

## 依赖安装

### 1. clone repo（主窗跑，本 agent 不 clone）
```bash
git clone https://github.com/vincentlaboratories/neoag
# clone 到 <REPO>，下文 --repo 指向它；确认含 Final_gbm_model.rds
```

### 2. R 依赖（neoag 原版 R3.5.2；本机 R4.3.3 / HPC R module，⚠️TODO 核版本兼容）
```r
# 本机 Windows R：E:\R-4.3.3\bin\Rscript.exe；HPC 用集群 R module
install.packages(c("caret", "gbm", "Peptides", "data.table", "doParallel"))
# ⚠️TODO clone 后核 repo 的 DESCRIPTION / 脚本头实际依赖清单（上为 best-guess，可能有缺漏）
# ⚠️TODO caret/gbm 跨 R 大版本对 rds 反序列化兼容性：R3.5.2 训练的 rds 在 R4.3.3 读取可能报
#         class/版本警告 → 先 --smoke 1 验 readRDS + predict 不崩。
```

---

## 运行流水线（主窗跑，本 agent 不跑任何代码）

```bash
# 变量
ROOT=D:/YJ-Agent/project/meeting/QuantImmuBench
NEOAG=$ROOT/HPC/deploy/neoag
CLONE=/path/to/neoag                                 # git clone 目标（含 Final_gbm_model.rds）
RSCRIPT=E:/R-4.3.3/bin/Rscript.exe                   # 本机；HPC 用集群 R module 的 Rscript

# Step 0（一次性）：clone repo + 填 run_neoag.R 的 OFFICIAL API ADAPTER（见本文头号告警）
git clone https://github.com/vincentlaboratories/neoag $CLONE

# Step 1: 准备输入（unique MT/WT 对 + 8-11mer + 单残基突变位号，~秒级）
python $NEOAG/prep_input.py

# Step 2: 烟测（前 1-2 对，验 readRDS + 官方特征 + predict + raw 结构）
python $NEOAG/run_neoag.py --repo $CLONE --rscript $RSCRIPT --smoke 2

# Step 3: 全量（CPU 秒~分钟级）
python $NEOAG/run_neoag.py --repo $CLONE --rscript $RSCRIPT

# Step 4: 回贴 universe（~秒级）
python $NEOAG/parse_output.py
#   → scripts/out/newtools/Neoag_DS1DS2_scores.csv（34247 行）

# Step 5: 合进大表（base 24tools → 25tools；主线串行，避免并发写 xlsx）
python $ROOT/scripts/patch_add_neoag.py
python $ROOT/analysis/merge_metrics_NNtools.py
```

---

## 已知坑

1. **官方 API 未核**（最高，见头号告警）：run_neoag.R 的 OFFICIAL API ADAPTER 未填妥会硬停；
   主窗 clone 后照 README + R/ 脚本 + rds 训练特征名填 `OFFICIAL_R_SOURCES`/`FEATURE_FN_NAME`/`PREDICT_*`。
2. **突变位号 base**：prep 默认 1-based 肽内位。官方若 0-based → 改 prep_input.py `POS_BASE=0`；
   若官方要蛋白坐标 → 本数据无蛋白坐标，无法提供（标 TODO，需上游补坐标或确认 neoag 用肽内位）。
3. **rds 跨 R 版本兼容**：R3.5.2 训练的 GBM rds 在 R4.3.3 读取可能 class/版本警告 → 先 --smoke 验。
4. **单残基差异约束**：只跑恰好 1 残基差异的 (MT,WT) 对；多残基/indel/长度不等的突变全 NaN
   （neoag 模型按单点替换设计；覆盖率看 prep 统计 + parse 覆盖统计）。
5. **分数方向**：默认越高越免疫原不翻转；clone 后务必核官方 README 确认，错了 parse 加 `--flip`。
6. **WT_Neoag 全 NaN**：neoag 是 (MT,WT) 对级单分，无独立 WT neoantigen 分；schema 保留列，主线可丢。
7. **训练集重叠 caveat**：neoag GBM 训练于其论文数据；与 benchmark 肽可能部分重叠，report 标注。

---

## 残留 TODO（勿臆造，需主窗核）

- [ ] **clone repo + 填 run_neoag.R OFFICIAL API ADAPTER**（OFFICIAL_R_SOURCES / FEATURE_FN_NAME / PREDICT_TYPE / PREDICT_POS_CLASS）。
- [ ] 核官方 **input CSV 列名 / 格式**（确认本部署 canonical → 官方 feature 函数的映射对）。
- [ ] 核**突变位号 base**（1-based 肽内 vs 0-based vs 蛋白坐标）→ 定 prep `POS_BASE`。
- [ ] 核 **Final_gbm_model.rds 在 repo 内路径** + predict 正类列名。
- [ ] 核**分数方向**（越高/越低越免疫原）→ 定 parse `DEFAULT_FLIP` / patch `FLIP`。
- [ ] 核 **R 依赖清单**（repo DESCRIPTION/脚本头实际依赖）+ R3.5.2→R4.3.3 兼容性（--smoke 验 readRDS+predict）。
- [ ] 全量跑后看 prep + parse 覆盖统计（多少对被单残基约束/超长滤掉）。
