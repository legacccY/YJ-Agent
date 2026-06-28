# IEDB Class I Immunogenicity (Calis 2013) — Deploy Notes

> 服务：quantimmu-bench benchmark 扩张 v2 第一波  lever=部署IEDB_Calis
> 建档：2026-06-26

---

## 工具概述

**IEDB Class I Immunogenicity Predictor v3.0**
- 论文：Calis JJA et al. (2013) "Properties of MHC class I presented peptides that enhance immunogenicity." *PLoS Comput Biol* 9(10):e1003253
- 方法：纯统计模型，无机器学习训练权重。对每个肽段的各位置氨基酸按 immunogenicity propensity 分值加权求和（锚位 mask 掉），越高越免疫原。
- 许可：**NPOSL-3.0**（Netscape Public License 变种，开源/学术/商业均可使用，**数字可自由发布，不触发 DTU 限制**）

---

## 官方下载 / CLI（已核实）

```bash
# 官方下载链接（核实日期：2026-06-26，版本 3.0，大小约 4KB）
wget https://downloads.iedb.org/tools/immunogenicity/LATEST/IEDB_Immunogenicity-3.0.tar.gz
tar -zxvf IEDB_Immunogenicity-3.0.tar.gz
cd immunogenicity/

# CLI（官方 README 确认）
python predict_immunogenicity.py example/test.txt                    # 默认 mask
python predict_immunogenicity.py --allele=HLA-A0201 input.txt        # allele-specific mask
python predict_immunogenicity.py --custom_mask=2,3,9 input.txt       # 自定义 mask
python predict_immunogenicity.py --allele_list                        # 列出 42 个支持 allele
```

**run_iedb_calis.sh 会在 HPC 自动下载并解压，无需手动安装。**

---

## 输入格式

- 纯文本文件，每行一条肽序列（大写氨基酸，标准 20 种氨基酸字母）
- 每次调用只处理一个 HLA allele（通过 `--allele` 指定）
- 本 deploy kit 做法：按 HLA_Allele 分组，每组一文件（`prep_input.py` 生成）

---

## 输出格式（stdout）

```
allele: HLA-A0201          ← 有 --allele 时才有此行
masking: custom            ← custom = allele-specific  /  default = P1,P2,C-term
masked variables: [1, 2, 9]

peptide,length,score       ← CSV 表头（parse_output.py 以此行为数据开始标记）
FIAGLIAIV,9,0.45678
LITGRLQSL,9,0.23456
```

- **按 score 降序排列**（parse_output.py 用肽序列 join，不依赖行顺序）
- `score` = immunogenicity score，越高越免疫原

---

## 输出方向

**直接用，方向正确**：score 越高 → 免疫原性越强，与 benchmark 其他工具（DeepImmuno / PRIME / ImmuneApp 等）方向一致，**无需翻转**。

---

## 肽长支持

- 工具对肽长无硬性限制，但针对 **9-mer 最优**（position weight 向量长 9）
- 8-mer：C-term 位置权重调整，score 仍有效（本 benchmark 中有 8-mer）
- 10-mer+：C-term 前插入额外权重 0.30，score 依然有效
- 本 benchmark universe 肽长范围：通常 8-15mer（全部可跑，无 NaN 因肽长）

---

## HLA 处理策略

### 支持的 allele（42 个，使用 allele-specific anchor mask）

来自 `predict_immunogenicity.py` 源码 `allele_dict.keys()`（核实于 v3.0）：

```
H-2-Db, H-2-Dd, H-2-Kb, H-2-Kd, H-2-Kk, H-2-Ld（小鼠）
HLA-A0101, HLA-A0201, HLA-A0202, HLA-A0203, HLA-A0206, HLA-A0211
HLA-A0301, HLA-A1101, HLA-A2301, HLA-A2402, HLA-A2601, HLA-A2902
HLA-A3001, HLA-A3002, HLA-A3101, HLA-A3201, HLA-A3301, HLA-A6801, HLA-A6802, HLA-A6901
HLA-B0702, HLA-B0801, HLA-B1501, HLA-B1502, HLA-B1801, HLA-B2705
HLA-B3501, HLA-B3901, HLA-B4001, HLA-B4002, HLA-B4402, HLA-B4403
HLA-B4501, HLA-B4601, HLA-B5101, HLA-B5301, HLA-B5401, HLA-B5701, HLA-B5801
```

HLA 格式转换：`HLA-A*02:01 → HLA-A0201`（去 `*` 去 `:`）

### 不支持的 allele（使用默认 anchor mask P1, P2, C-term）

本 benchmark universe.csv 中有 **65 个唯一 HLA allele**，其中约 **17 个**在支持列表内，约 **48 个**不在（全部 HLA-C allele + 部分 HLA-A/B subtypes）。

⚠️ **Caveat（已在输出 CSV 注释中标注）**：

不支持的 allele 使用默认 anchor mask 打分，等价于把该 allele 当作「通用 mask P1,P2,C-term」处理。这意味着：
- 同一肽与**不支持**的 allele 配对时，得分是序列本征值（不反映该 allele 的锚位特性）
- 同一肽在支持/不支持 allele 下的得分可能细微不同（因 mask 位置略有差异）
- HLA-C 全部不在支持列表，相关行均使用默认 mask

---

## WT 处理

本 benchmark 所有 34247 行均有非空 `WT_Subpeptide`。`parse_output.py` 对 MT 和 WT 分别 join：

```
join key = (peptide.upper(), hla_to_iedb(HLA_Allele))
```

MT 和 WT 用同一 allele 对应的 mask 打分，结果分别填 `MT_IEDB_Calis` 和 `WT_IEDB_Calis`。

---

## 三件套文件说明

| 文件 | 作用 | 运行时机 |
|---|---|---|
| `prep_input.py` | 读 uniq_pep_hla.csv → 按 allele 分组写 txt 文件 + allele_manifest.csv | **本地**（Windows/Linux 均可） |
| `run_iedb_calis.sh` | HPC SLURM：下载工具 + 循环 allele 批量打分 → per-allele scores txt | **HPC** sbatch |
| `parse_output.py` | 读 scores 文件 + universe.csv → IEDB_Calis_DS1DS2_scores.csv | **本地**（HPC scores 取回后） |

---

## 完整运行流程

```bash
# 1. 本地：生成输入文件
cd D:/YJ-Agent/project/meeting/QuantImmuBench/HPC/deploy/iedb_calis/
python prep_input.py
# 输出：scripts/out/newtools/iedb_calis_inputs/（allele_manifest.csv + ~65 个 .txt 文件）

# 2. 上传至 HPC
scp -r scripts/out/newtools/iedb_calis_inputs/ \
    jiayu2403@dtn.hpc.xjtlu.edu.cn:/gpfs/work/bio/jiayu2403/quantimmu/iedb_calis_run/inputs/

# 3. HPC：提交 SLURM 作业
sbatch HPC/deploy/iedb_calis/run_iedb_calis.sh

# 4. 烟测（可选，在 HPC 登录节点快验）
bash HPC/deploy/iedb_calis/run_iedb_calis.sh --smoke

# 5. 取回 scores
scp -r jiayu2403@dtn.hpc.xjtlu.edu.cn:/gpfs/work/bio/jiayu2403/quantimmu/iedb_calis_run/scores/ \
    scripts/out/newtools/iedb_calis_scores/

# 6. 本地：解析回贴
python parse_output.py
# 输出：scripts/out/newtools/IEDB_Calis_DS1DS2_scores.csv
```

---

## 预期输出

- 文件：`scripts/out/newtools/IEDB_Calis_DS1DS2_scores.csv`
- 列：`Dataset, Peptide_ID, HLA_Allele, MT_Subpeptide, MT_IEDB_Calis, WT_IEDB_Calis`
- 行数：34247（覆盖全 universe）
- 分数范围：通常 -1.5 ~ +1.5（无硬边界，免疫原肽分值偏高）
- NaN：不支持的肽（实际上不应出现，因工具支持所有肽长）

---

## 与其他工具的对比关系

- **优势**：纯统计，可解释性强，无 HLA allele 限制（支持列表外 allele 用默认 mask）
- **局限**：不考虑 TCR 识别概率、蛋白酶处理或转运效率；仅用氨基酸理化性质
- 在 benchmark 中作为**经典统计 baseline**，与 DeepImmuno / PRIME / ImmuneApp 等深度学习工具对比
