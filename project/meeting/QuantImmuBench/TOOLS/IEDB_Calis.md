# IEDB Immunogenicity / Calis 2013 — 信息收集卡（PPT 素材）

> 4 类信息来源：DEPLOY_TRACKER §Tier-0 + HPC/deploy/iedb_calis/NOTES.md（2026-06-26 核实）。实跑项以「实测」标注。

## 0. 定位 / 一句话

**经典统计免疫原性打分工具（无机器学习，无权重文件）**：依据 HLA I 类呈递肽各位置氨基酸的 immunogenicity propensity 分值线性加权求和，用 allele-specific anchor mask 屏蔽锚位贡献。2013 年发布，是新抗原流水线中引用频次最高的经典基准，被 pVACseq、iNeo-Suite 等默认集成。  
**输出分无硬边界（通常 -1.5 ~ +1.5），越高越免疫原**。纯 CPU 秒级。NPOSL-3.0 自由可发。

## 1. 输入数据模板 / 格式

- **文件格式**：纯文本 `.txt`，每行一条肽序列（大写标准 20 种氨基酸），**无表头，无 HLA 列**
- **输入策略**：工具每次调用只处理**一个 HLA allele**；本 benchmark 按 HLA_Allele 分组，每组一个 txt 文件（`prep_input.py` 自动生成 ~65 个）
- **HLA 格式**：命令行 `--allele` 参数；格式 = **去 `*` 去 `:`**，例如 `HLA-A*02:01 → HLA-A0201`
  - 本 benchmark 转换由 `prep_input.py` 完成（`str.replace("*","").replace(":","")` 仅首个 `:`）
- **肽段长度**：无硬限制；**9-mer 最优**（position weight 向量长 9）；8-mer 和 10-mer+ 均有处理规则（C-term 调整）；本 benchmark universe 8–15mer 全部可打分，无因肽长产生 NaN
- **是否需基因组数据**：否
- **是否需野生型（WT）肽**：否（本 benchmark MT+WT 分别用同 allele 打分）
- **实测输入样例**（实测）：
  ```
  FIAGLIAIV
  LITGRLQSL
  NLVPMVATV
  ```
  （文件名如 `HLA-A0201.txt`，对应 `--allele=HLA-A0201`）
- **支持 allele 数**：**42 个**（allele-specific anchor mask）；其余使用默认 mask（P1, P2, C-term）

### 42 个支持 allele（原文核实）

```
小鼠：H-2-Db, H-2-Dd, H-2-Kb, H-2-Kd, H-2-Kk, H-2-Ld
HLA-A：A0101, A0201, A0202, A0203, A0206, A0211, A0301, A1101, A2301, A2402,
       A2601, A2902, A3001, A3002, A3101, A3201, A3301, A6801, A6802, A6901
HLA-B：B0702, B0801, B1501, B1502, B1801, B2705, B3501, B3901, B4001, B4002,
       B4402, B4403, B4501, B4601, B5101, B5301, B5401, B5701, B5801
```

⚠️ **Caveat**：benchmark universe 中 HLA-C allele 及部分 HLA-A/B 亚型（共约 48/65 个）不在支持列表，使用默认 anchor mask（等价于通用 P1,P2,C-term），不反映该 allele 特异性锚位，须在报告中标注。

## 2. 运行参数设置

### CLI 参数

| 参数 | 说明 |
|---|---|
| `--allele=HLA-A0201` | 指定 allele（去 * 去 :），使用 allele-specific mask |
| `--custom_mask=2,3,9` | 自定义 mask 位置（本 benchmark 不用） |
| `--allele_list` | 打印所有 42 个支持 allele |
| 不加 `--allele` | 使用默认 mask（P1, P2, C-term） |

### 典型命令行

```bash
# 有 allele 支持：使用 allele-specific mask
python predict_immunogenicity.py --allele=HLA-A0201 HLA-A0201.txt

# 不在支持列表的 allele：回退默认 mask
python predict_immunogenicity.py HLA-B4601.txt

# 列出支持 allele
python predict_immunogenicity.py --allele_list
```

### 安装（无需 pip，直接下载）

```bash
wget https://downloads.iedb.org/tools/immunogenicity/LATEST/IEDB_Immunogenicity-3.0.tar.gz
tar -zxvf IEDB_Immunogenicity-3.0.tar.gz
cd immunogenicity/
```

### 本 benchmark 流水线

```bash
# Step 1: 本地生成按 allele 分组的 txt 文件
python HPC/deploy/iedb_calis/prep_input.py

# Step 2: 批量循环打分（65 allele，秒级完成）
bash HPC/deploy/iedb_calis/run_iedb_calis.sh    # 或本地等价循环

# Step 3: 解析 + 回贴 universe
python HPC/deploy/iedb_calis/parse_output.py
```

## 3. 输出数据格式 + 含义

### stdout 格式（原始输出，每次调用一个 allele）

```
allele: HLA-A0201
masking: custom
masked variables: [1, 2, 9]

peptide,length,score
FIAGLIAIV,9,0.45678
LITGRLQSL,9,0.23456
```

- 输出按 score **降序**排列（parse_output.py 用肽序列 join，不依赖行顺序）

### 关键列

| 列 | 含义 |
|---|---|
| `peptide` | 肽段序列 |
| `length` | 肽长（int） |
| `score` | **immunogenicity score，无硬边界（通常 -1.5 ~ +1.5），越高越免疫原** |

### 最终产物（`IEDB_Calis_DS1DS2_scores.csv`）

| 列 | 含义 |
|---|---|
| `Dataset` | DS1 / DS2 |
| `Peptide_ID` | 原始 ID |
| `HLA_Allele` | HLA-A*xx:xx |
| `MT_Subpeptide` | 突变肽序列 |
| `MT_IEDB_Calis` | MT 侧免疫原性分数 |
| `WT_IEDB_Calis` | WT 侧免疫原性分数 |

- **分数类型**：连续无界线性分（通常 -1.5 ~ +1.5）
- **分数方向**：**越高越免疫原，直接用，无需翻转**
- **能否定量免疫强弱**：✅ 是（连续分，可排名）← 项目核心目标
- **实测输出**（实测）：34247 行，**0 NaN**（工具对所有肽长均有输出；不支持 allele 用默认 mask 仍给分）

## 4. 简介（特点 / 优势）

- **方法**：纯统计线性加权。每个氨基酸在各位置的 immunogenicity propensity 分值来自 IEDB 数据库实验数据统计；对各非锚位求和。allele-specific mask 屏蔽 HLA 锚位（P1, P2, C-term 等），避免这些位置的 HLA 结合信号干扰免疫原性估计。无机器学习训练，无梯度，无权重文件
- **训练数据**：无（统计量来自文献/IEDB 实验汇总）
- **特点 / 优势**：
  - **零依赖，无许可限制，纯 Python 秒级**：pip free，65 allele 秒级跑完
  - 完全可解释：每个 score 可逐位追溯氨基酸贡献
  - 被 pVACseq、iNeo-Suite 等主流新抗原流水线默认集成，是领域最高引用经典基准
  - NPOSL-3.0，数字完全自由发布，无 DTU 限制
- **局限**：
  - 不考虑 TCR 识别概率、蛋白酶处理或 TAP 转运效率
  - 只依据氨基酸理化性质，无序列上下文学习
  - 对不支持 allele 回退默认 mask，锚位特异性失去
  - 分数无硬边界（不是 0-1 概率），需注意跨工具比较时单位不一致

## 部署记录

- **工具**：IEDB_Immunogenicity-3.0（Python 3，~4KB 脚本）
- **下载**：https://downloads.iedb.org/tools/immunogenicity/LATEST/IEDB_Immunogenicity-3.0.tar.gz
- **论文**：*Properties of MHC Class I Presented Peptides That Enhance Immunogenicity*，2013 · PLOS Computational Biology，DOI [10.1371/journal.pcbi.1003266](https://doi.org/10.1371/journal.pcbi.1003266)（原文对应编号 pcbi.1003266；NOTES 中引用号为 e1003253，以此 DOI 为权威）
- **语言 / 框架**：纯 Python 3（无 ML 框架依赖）
- **外部许可证工具**：无
- **GPU 需求**：无
- **许可**：NPOSL-3.0（开源，数字可自由发布 ✅，无 DTU 禁再分发限制）
- **部署状态**：✅ **RUN_DONE**（本地 Windows，纯统计秒级，65 allele 全量）
- **部署文件**：`HPC/deploy/iedb_calis/`（prep_input.py / run_iedb_calis.sh / parse_output.py / NOTES.md）
- **实测输出**：`IEDB_Calis_DS1DS2_scores.csv`，34247 行，0 NaN

---

**为什么选作对比**：建立 2013 年的历史对照基准——现代深度学习工具必须显著高于这条线才算真进步。被 pVACseq、iNeo-Suite 等主流流水线默认集成，是引用频次最高的 class-I 免疫原性工具之一。任何新工具不超过它即可判无效。（来源：NEWTOOLS_LIT_MATRIX §二 §1）
