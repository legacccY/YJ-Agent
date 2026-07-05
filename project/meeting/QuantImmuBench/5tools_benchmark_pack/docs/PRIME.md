# PRIME 工具交付说明

> 项目：Rerun v2 — 5 工具 × 130 肽 × 三层次评估
> 数据红线：本文所有 benchmark 数字精确溯源 HPC 评估输出，未自创。

---

## 1. 工具简介

- **原理 / 方法**：PRIME（PRedictor of IMmunogenic Epitopes）预测 neo-epitope **免疫原性**的轻量打分模型。整合三类信息：MixMHCpred HLA-I 提呈分 + 肽段 TCR 接触位点氨基酸频率特征 + 肽长，输出连续免疫原性排名分。非深度学习（线性/logistic 类轻量模型）。
- **特点**：
  - 直接输出免疫原性连续分数（可量化强弱），契合「强弱定量」目标
  - **依赖链最短**：唯一外部依赖是 MixMHCpred，无 netMHCpan/DTU 学术许可负担，是 5 工具中部署最易的
  - 输入只需突变肽段 + HLA 等位，不要 WT 肽/表达量/基因组数据
  - C++ 编译主体（`g++ -O3`），轻量高效
- **论文**：
  - PRIME 1.0 — *Prediction of neo-epitope immunogenicity reveals TCR recognition determinants...*, Cell Reports Medicine, 2021. DOI: **10.1016/j.celrep.2021.100194**
  - PRIME 2.0 — *Improved predictions of antigen presentation and TCR recognition with MixMHCpred2.2 and PRIME2.0...*, Cell Systems, 2023. DOI: **10.1016/j.cels.2022.12.002**
- **代码仓库**：https://github.com/GfellerLab/PRIME （v2.1）；依赖 https://github.com/GfellerLab/MixMHCpred （v3.0+）
- **许可证**：学术非商用免费；商用须向 Ludwig Institute 申请。MixMHCpred 同属 Gfeller lab，学术免费，无 DTU 许可。

---

## 2. 输入数据模板 / 格式

- **文件格式**：纯文本（每行一条肽段）。
- **必填字段**：肽段序列 + HLA 等位（命令行 `-a` 指定，多个逗号分隔）。
- **肽段长度**：8–14 AA。
- **HLA 格式**：`A0101`/`A01:01`/`HLA-A01:01`/`HLA-A*01:01` 均可，自动解析。
- **是否需基因组数据**：否。

**示例**：
```
VMLQAPLFT
GILGFVFTL
...
```
命令行：`-a A0101,A2501,B0801,B1801`

---

## 3. 参数设置

| 参数 | 说明 | 本项目用值 |
|---|---|---|
| `-i` | 输入肽段文件 | `PRIME_database2_MT.txt` / `PRIME_database2_WT.txt` |
| `-o` | 输出文件 | `dataset2_MT_prime.txt` / `dataset2_WT_prime.txt` |
| `-a` | HLA 等位列表（逗号分隔） | 26 个等位基因（跨 9 患者） |
| `-mix` | MixMHCpred 路径 | `/gpfs/work/bio/zichenli24/tools/MixMHCpred` |

**完整命令**（HPC sbatch）：
```bash
./PRIME -i PRIME_database2_MT.txt -o dataset2_MT_prime.txt \
    -a A0101,A0201,A0301,A1101,A2402,A2501,A2601,A2902,A3001,A3101,\
A3201,A3303,A6601,A6801,A6802,A6901,B0702,B0801,B1302,B1501,\
B1801,B2705,B3501,B3503,B3801,B4001,B4402,B5101,B5501,B5701 \
    -mix /gpfs/work/bio/zichenli24/tools/MixMHCpred
```

---

## 4. 输出格式及含义

- **输出文件**：文本（空格/tab 分隔），含 header。
- **关键列**：

| 列 | 含义 | 方向 / 范围 |
|---|---|---|
| Peptide | 肽段序列 | — |
| %Rank（best allele） | 跨所有 allele 最低 PRIME %Rank | **越低越强**，0–100 |
| Score（best allele） | 对应最优 allele 的 PRIME Score | **越高越强**（连续） |
| %RankBinding（best allele） | MixMHCpred 纯结合 %Rank（对照） | 越低结合越强 |
| BestAllele | 最优等位基因 | — |

- **本评估用**：PRIME Score（取 max 跨 allele × 子肽 → 每 Peptide_ID 一条）
- 烟测验证：147 行官方 test 输出与 `test/out_compare.txt` 完全一致（diff=0），r=1.0

---

## 5. 最新 benchmark 结果（DS2 ELISpot，130 肽）

> 数据集：DS2 In Vitro ELISpot，130 肽 / 9 患者。主指标为逐患者 Fisher-Z 加权 Spearman。

| 指标 | 数值 |
|---|---|
| n_pep（覆盖肽数） | 130 / 130（全覆盖） |
| per-patient Fisher-Z 加权 ρ [95% CI]（**主指标**） | **+0.203 [+0.013, +0.379]**（CI 不含 0，**显著**） |
| Spearman ρ（max 聚合，对照） | **+0.226**（p = 0.010，**显著**） |
| AUC（max，SFC > 0） | 0.586 |

**解读**：PRIME 是 5 个已发表工具中表现最好的——Fisher-Z +0.203 且 95%CI 严格 > 0，全局 Spearman 也显著（p=0.010）。AUC 0.586 虽然是弱分类器但方向正确。结论：PRIME 对免疫强度连续定量有一定预测力，但绝对值仍有限（ρ ~ 0.2）。

---

## 6. 部署环境与已知问题

- **跑的版本**：官方权重（PRIME v2.1 + MixMHCpred v3.0），已验证 r=1.0
- **环境**：HPC conda env `prime`（Python 3.11 + numpy/pandas/scipy）。PRIME 主体为 C++（`g++ -O3` 编译）+ Perl + Shell；MixMHCpred 3.0 为 Python 实现。CPU 推理，无 GPU 需求。
- **HPC Job**：1503136（8h，4 CPU，16G RAM，short partition）
- **仓库位置**：`/gpfs/work/bio/zichenli24/tools/PRIME` + `/gpfs/work/bio/zichenli24/tools/MixMHCpred`
- **关键坑**：
  - 唯一外部依赖 MixMHCpred v3.0+（v3.0 是 Python 实现，无需编译，可选 MAFFT）
  - 肽长 8–14 AA，超出范围不处理
  - 多 allele 时输出展开为多列（每 allele 各出 %Rank + Score + %RankBinding）
