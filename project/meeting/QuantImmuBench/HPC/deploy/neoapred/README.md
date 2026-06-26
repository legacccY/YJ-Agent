# NeoaPred 部署文档

> 项目：QuantImmuBench 工具扩张 v2 — Tier-3 重型工具
> 工具：NeoaPred (PepFore 模式，结构 foreignness 免疫原性预测)
> 许可：Apache-2.0
> 论文：DOI 10.1093/bioinformatics/btae547
> 性能：AUROC 0.81（原论文，CD8+ T 细胞免疫原性分类）

---

## 工具简介

NeoaPred 通过预测新抗原（neoantigen）肽段相对于野生型（WT）序列的**结构外来性（structural foreignness）**评估免疫原性。

- **方法**：PepFore 模式 — 用 AlphaFold 结构预测 + OpenMM 弛豫 + MSMS/APBS 计算静电/溶剂可及性，量化 MT 肽 vs WT 肽的结构差异
- **输出**：`Foreignness_Score`（0–1 连续，越高越可能引发免疫应答）
- **推荐阈值**：>0.5 为候选免疫原性肽
- **输入约束**：严格 9mer，需 MT + WT 配对，HLA 需为缩写型（如 `A2402`）
- **repo**：https://github.com/Dulab2020/NeoaPred

---

## 输入格式

### NeoaPred 输入 CSV（`neoapred_input.csv`）

| 列 | 说明 | 示例 |
|---|---|---|
| `ID` | 唯一标识，自增 | `ID_0` |
| `Allele` | HLA 缩写型（去 `HLA-` 去 `*` 去 `:`） | `A2402` |
| `WT` | 野生型 9mer 子肽 | `ELKFVTLVF` |
| `Mut` | 突变型 9mer 子肽 | `KLKFVTLVF` |

⚠️ **HLA 格式必须是缩写型**：`HLA-A*24:02` → `A2402`（locus 字母 + 4 位数字，如 A2402/B5701/C0702）。非此格式会导致 NeoaPred 报错或静默失败。

⚠️ **严格 9mer**：MT 和 WT 子肽必须都是 9 个氨基酸。非 9mer 子肽不能喂给 NeoaPred，最终结果中填 NaN。

### 模板示例

```
ID,Allele,WT,Mut
ID_0,A2402,RLETIRDPK,RLETIRNPK
ID_1,A0301,RLETIRDPK,RLETIRNPK
ID_2,B4001,RLETIRDPK,RLETIRNPK
```

---

## 输出格式

### 关键输出文件

```
<output_dir>/
  test_out/
    Foreignness/
      MhcPep_foreignness.csv     ← 主要分数文件
```

### `MhcPep_foreignness.csv` 关键列

| 列 | 说明 |
|---|---|
| `ID` | 与输入 CSV ID 对应 |
| `Foreignness_Score` | MT 肽结构外来性分数（0–1，越高越强免疫原） |
| （其他列） | TODO: 实跑后确认完整列结构 |

> 方向已与 benchmark 其他工具统一：**越高越强免疫原，无需翻转**。

---

## 部署步骤

### 主路：本地 WSL2 Docker（无 HPC 限制时优先）

#### Step 0：准备输入文件

```bash
# 全量（5692 条 unique 9mer）
python HPC/deploy/neoapred/prep_neoapred_input.py

# 烟测（5 条）
python HPC/deploy/neoapred/prep_neoapred_input.py --smoke 5
# → scripts/out/newtools/neoapred_input.csv
# → scripts/out/newtools/neoapred_input_map.csv
```

#### Step 1：运行 NeoaPred Docker

```bash
# 烟测（先跑 5 条确认流程）
bash HPC/deploy/neoapred/run_neoapred_docker.sh \
    scripts/out/newtools/neoapred_input.csv \
    neoapred_smoke_out/

# 全量（⚠️ 耗时很长，见「已知坑」）
bash HPC/deploy/neoapred/run_neoapred_docker.sh \
    scripts/out/newtools/neoapred_input.csv \
    neoapred_full_out/

# 若需 GPU 加速（非必须，见「已知坑」）：
GPUS=all bash HPC/deploy/neoapred/run_neoapred_docker.sh \
    scripts/out/newtools/neoapred_input.csv \
    neoapred_full_out/
```

#### Step 2：回贴结果到 master_backbone

```bash
python HPC/deploy/neoapred/merge_neoapred.py \
    --foreignness-csv neoapred_full_out/test_out/Foreignness/MhcPep_foreignness.csv \
    --map-csv         scripts/out/newtools/neoapred_input_map.csv \
    --backbone        scripts/out/master_backbone.csv \
    --out-dir         scripts/out/newtools
# → scripts/out/newtools/neoapred_scores.csv（列: bb_idx, MT_NeoaPred）
```

---

### 备用路：HPC Singularity（XJTLU gpu4090 不通 Docker Hub）

参见 `build_singularity_hpc.sh`，完整三步流程：

1. **本地** `docker save panda1103/neoapred:1.0.0 | gzip > neoapred.tar.gz`
2. **sftp/scp** 传 HPC：`scp neoapred.tar.gz jiayu2403@gpu4090.xjtlu.edu.cn:/gpfs/work/bio/jiayu2403/quantimmu/sif/`
3. **HPC** `singularity build neoapred.sif docker-archive://neoapred.tar`

⚠️ HPC Singularity 路有多个 TODO 待验，建议先跑本地 Docker 主路确认结果正确性。

---

## 已知坑 & 注意事项

### 1. HLA 必须用缩写型

NeoaPred 只接受 `A2402`、`B5701`、`C0702` 等**缩写型**（locus 字母 + 4 位数字），
**不接受** `HLA-A*24:02` 或 `HLA-A24:02` 格式。
`prep_neoapred_input.py` 已自动转换，但手动构造输入时务必检查。

### 2. 严格 9mer

PepFore 模式只支持 9mer。benchmark 数据集中仅有 6065 行为严格 9mer（MT+WT 均 9mer），
占总 34247 行的 ~18%。其余长度行最终 `MT_NeoaPred` 列为 NaN。

### 3. OpenMM CPU 弛豫极慢

NeoaPred 的结构弛豫依赖 OpenMM，为 CPU 密集型操作。GPU 加速为可选项（OpenMM 可利用 CUDA）。
TODO: 单条肽精确耗时待实跑确认；估算全量 5692 条在单机 CPU 上可能需数天。
建议先烟测 5-10 条估算单条耗时，再规划总体时间。

### 4. Python 3.6 锁死

NeoaPred 容器内使用 Python 3.6（`neoa` conda env），不兼容较新 Python 语法。
`prep_neoapred_input.py` 和 `merge_neoapred.py` 均在**容器外**运行，不受此限制。

### 5. MSMS/APBS/PDB2PQR/PDB2XYZRN 均镜像内置

无需在宿主机另装这些工具，镜像内已包含完整依赖链。

### 6. HPC Singularity 的 /root 访问风险

参考 pTuneos/HLAthena 部署经验（04_LOG）：部分 Docker 镜像将程序/conda env 放在 `/root/`，
Singularity 以非 root 运行时访问受限。NeoaPred 程序位于 `/var/software/`，风险较低，
但 conda env 路径需实跑验证（见 `build_singularity_hpc.sh` TODO 注释）。

---

## 4 类交付信息（benchmark 对齐）

### ① 输入模板

见「输入格式」节，CSV 格式，必填列 `ID,Allele,WT,Mut`。

### ② 关键参数

| 参数 | 值 | 说明 |
|---|---|---|
| `--mode` | `PepFore` | 全链路结构 foreignness 模式（含 AlphaFold+OpenMM） |
| 肽长度 | 严格 9mer | MT+WT 均必须为 9aa |
| HLA 格式 | 缩写型 `A2402` | 非标准格式导致运行失败 |
| 输出路径 | `<output_dir>/Foreignness/MhcPep_foreignness.csv` | 固定子路径 |

### ③ 输出格式含义

- `Foreignness_Score`：MT 肽相对 WT 肽的结构外来性，0–1 连续分数
- 越高 = MT 肽与 WT 肽结构差异越大 = 免疫系统更容易将其识别为「外来」
- benchmark 回贴列名：`MT_NeoaPred`（方向统一：越高越强免疫原）
- 推荐阈值 >0.5（原论文，可调）

### ④ 工具简介

NeoaPred（2024，Bioinformatics）是国内 Dulab 团队开发的新抗原免疫原性预测工具，
核心创新为结合**结构预测**（AlphaFold）+ **物理化学计算**（OpenMM/MSMS/APBS）
量化 neoantigen 的结构外来性（foreignness），区别于纯序列/MHC 亲和力方法。

- 方法：PepFore（Peptide Foreignness）全链路结构模式
- AUROC：0.81（CD8+ T 细胞免疫原性分类，论文原始结果）
- 许可证：Apache-2.0
- 论文：DOI 10.1093/bioinformatics/btae547
- repo：https://github.com/Dulab2020/NeoaPred

---

## 文件列表

```
HPC/deploy/neoapred/
  prep_neoapred_input.py    读 backbone → 过滤 9mer → 写 NeoaPred 输入 CSV + map
  run_neoapred_docker.sh    本地 WSL2 Docker 运行封装（主路）
  build_singularity_hpc.sh  HPC Singularity 构建模板（备用路）
  merge_neoapred.py         NeoaPred 输出 → 回贴 bb_idx → 写 neoapred_scores.csv
  README.md                 本文件

scripts/out/newtools/（运行时产出）
  neoapred_input.csv        NeoaPred 输入（ID,Allele,WT,Mut），5692 条 unique 9mer
  neoapred_input_map.csv    ID → bb_idxs 映射（一对多）
  neoapred_scores.csv       回贴结果（bb_idx, MT_NeoaPred[, WT_NeoaPred]）
```
