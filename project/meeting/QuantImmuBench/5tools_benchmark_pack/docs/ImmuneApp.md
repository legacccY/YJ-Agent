# ImmuneApp 工具交付说明

> 项目：Rerun v2 — 5 工具 × 130 肽 × 三层次评估
> 数据红线：本文所有 benchmark 数字精确溯源 HPC 评估输出，未自创。

---

## 1. 工具简介

- **原理 / 方法**：基于注意力机制的 CNN-LSTM 混合框架，用于 HLA-I 表位预测与免疫肽组分析。框架含多个模块，本项目使用 **ImmuneApp-Neo 免疫原性预测模块**（迁移学习）。注意力层可识别关键结合残基，具一定可解释性。仅支持 HLA Class I。
- **特点**：
  - HLA-I 提呈预测达 SOTA 水平（论文报 PPV 0.3720 vs NetMHCpan-4.1 的 0.3313）；Neo 模块称 PPV 较现有方法提升约 2.1 倍
  - 预训练权重随仓库发布，**MIT 许可无障碍**，无 netMHCpan/DTU 依赖
  - 支持 10000+ MHC 等位
- **论文**：*ImmuneApp for HLA-I epitope prediction and immunopeptidome analysis*, Nature Communications, 2024. DOI: **10.1038/s41467-024-53296-0**
- **代码仓库**：https://github.com/bsml320/ImmuneApp ；Web server：https://bioinfo.uth.edu/iapp/
- **许可证**：**MIT**（自由使用/修改/分发）

---

## 2. 输入数据模板 / 格式

- **文件格式**：纯肽段文本（每行一条，无 header）+ 命令行 `-a` 指定 HLA。
- **必填字段**：肽段序列 + HLA 等位。
- **肽段长度**：8–15 AA（`read_peplist()` 硬性校验，仅接受 20 种标准氨基酸）。
- **HLA 格式**：标准 `HLA-A*01:01`（`-a` 后接多个，空格分隔）。
- **是否需基因组数据**：否。

**命令示例**：
```bash
python ImmuneApp_immunogenicity_prediction.py \
  -f input_peptides.txt \
  -a 'HLA-A*02:01' \
  -o results
```

---

## 3. 参数设置

| 参数 | 说明 | 本项目用值 |
|---|---|---|
| `-f` | 肽段文件（每行一条） | 按 HLA allele 切分的 per-allele txt |
| `-a` | HLA 等位列表（空格分隔） | 逐 allele 运行（26 alleles × 2 subsets = 52 次） |
| `-o` | 输出目录 | `outputs/dataset2_MT/<allele>/` |
| 模型变体 | `-Neo`（免疫原性模块） | 默认（跑 `ImmuneApp_immunogenicity_prediction.py`） |

**完整流程**（HPC sbatch）：
```bash
conda activate immuneapp
cd /gpfs/work/bio/zichenli24/tools/ImmuneApp
for txt in inputs/dataset2_MT/*.txt; do
    hla=$(basename "$txt" .txt | sed 's/HLA-//' | sed 's/\([ABC]\)\([0-9][0-9]\)\([0-9][0-9]\)/\1*\2:\3/')
    python ImmuneApp_immunogenicity_prediction.py -f "$txt" -a "$hla" -o "outputs/dataset2_MT/$(basename $txt .txt)"
done
```

---

## 4. 输出格式及含义

- **输出文件**：`ImmuneApp_Immunogenicity_predictions.tsv`（文件名固定；`-o` 指定的是目录）。
- **关键列**：

| 列 | 含义 | 方向 / 范围 |
|---|---|---|
| Allele | HLA 等位基因 | — |
| Peptide | 肽段序列 | — |
| Sample | 样本标识 | — |
| Immunogenicity_score | 免疫原性预测分 | **越高越免疫原**，0–1（sigmoid） |

- **粒度**：per-allele（每肽 × 每 allele 各一行）；本评估取 max 跨 allele × 子肽聚合到 Peptide_ID。
- **合并输出**：52 文件 → `ImmuneApp_Immunogenicity_predictions.tsv`（45,966 行）

---

## 5. 最新 benchmark 结果（DS2 ELISpot，130 肽）

> 数据集：DS2 In Vitro ELISpot，130 肽 / 9 患者。主指标为逐患者 Fisher-Z 加权 Spearman。

| 指标 | 数值 |
|---|---|
| n_pep（覆盖肽数） | 130 / 130（全覆盖） |
| per-patient Fisher-Z 加权 ρ [95% CI]（**主指标**） | **+0.172 [−0.020, +0.351]**（CI 跨 0，**不显著**） |
| Spearman ρ（max 聚合，对照） | **+0.036**（p = 0.681，不显著） |
| AUC（max，SFC > 0） | 0.579 |

**解读**：方向为正但统计未达显著（95%CI 跨越 0）。Fisher-Z +0.172 在 5 工具中排第 4，全局 Spearman 接近 0。AUC 0.579 略优于随机，但整体区分力有限。CNN-LSTM 架构可能对 DS2 这种长肽滑动窗口场景不够敏感。

---

## 6. 部署环境与已知问题

- **跑的版本**：官方权重（随 repo `models/immunogenicity/`）
- **环境**：HPC conda env `immuneapp`（注意：小写 i，非 PascalCase `ImmuneApp`）
- **关键版本 pin**：**Python 3.7 严格**（TF1.15 PyPI 仅发布 3.6/3.7 Linux wheel）+ TensorFlow 1.15.0 + Keras 2.3.1（standalone）+ numpy 1.18.5 + h5py 2.10.0 + protobuf 3.20
- **HPC Job**：1503137（6h，4 CPU，16G RAM，short partition）
- **仓库位置**：`/gpfs/work/bio/zichenli24/tools/ImmuneApp`
- **关键坑**（版本地狱）：
  - **Python 必须严格 3.7**：TF1.15 PyPI wheel 仅发布 py3.6/3.7 Linux 版，3.8+ 无
  - **h5py 必须 2.10.0**：3.x 改 API，读不了 TF1 存的 .h5 权重
  - **protobuf 必须 3.20**：4.x 删除 `descriptor_pool.Add()`
  - **Keras 用 standalone 2.3.1**：代码 `import keras`，非 `from tensorflow import keras`
  - numpy 不要升到 1.24+：TF1.15 依赖 `np.bool`/`np.int` 已弃用别名
  - **conda env 名陷阱**：`ImmuneApp`（PascalCase）env **无 TF**！正确 env 是 `immuneapp`（小写）
  - 运行前须 `cd` 到 repo 根目录（权重用相对路径加载）
