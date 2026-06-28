# BigMHC（-m=im 免疫原性模式）— 工具交付说明

> 项目：QuantImmuBench（癌症个性化新抗原疫苗协作项目）
> 任务：HPC 部署测试现有预测工具，收集 4 类信息 + benchmark 结果。
> 版本与数字截至 2026-06-28（DS2 ELISpot 全量重算后）。详细环境配置命令见同目录《环境配置命令_回顾记录.md》。

> ⚠️ **许可证提示**：BigMHC 采用 **BigMHC Academic License（学术非商用）**。学术研究、教学、非营利机构自由使用、可发表数字；商用须另与 Johns Hopkins Karchin Lab 签署商业协议。本项目属学术非商用，合规。

---

## 1. 工具简介

- **原理 / 方法**：大规模迁移学习的 pMHC 免疫原性预测，分两阶段——
  1. Stage 1（EL）：在数十万条 MHC-I 洗脱配体质谱数据上预训练，学习 pMHC 提呈规律；
  2. Stage 2（IM）：下游迁移微调到有标注的免疫原性数据。`-m=im` 模式自动加载 7 个不同 batch-size 的 checkpoint 做 ensemble，取平均分。
- **训练数据**：MHC-I 洗脱配体大规模 MS 数据（EL 阶段）+ IEDB / 文献免疫原性标注（IM 阶段）。
- **特点 / 优势**：pan-allele，覆盖 >500 个等位基因，无需特定 allele 训练；HLA 格式宽容（模糊匹配），输入无需转换；代表「大规模预训练 + 下游迁移」现代范式，Nature MI 2023 高可信；CPU 可推理，GPU 显著加速。
- **局限**：不直接建模 TCR 识别；IM ensemble（7 个 checkpoint）CPU 推理较慢；需 git-lfs 克隆约 5GB；Windows 多 worker DataLoader 有 OOM 坑。
- **论文**：*Deep neural networks predict class I MHC epitope presentation and transfer learn neoepitope immunogenicity*, Nature Machine Intelligence, 2023。DOI: 10.1038/s42256-023-00694-6。
- **代码**：https://github.com/KarchinLab/bigmhc （Johns Hopkins Karchin Lab）。
- **许可证**：BigMHC Academic License（学术非商用，发表数字允许）。

---

## 2. 输入数据模板 / 格式

- **文件格式**：CSV（带表头）。
- **必填列**：
  - 第 0 列 `mhc`：HLA 等位；
  - 第 1 列 `pep`：肽段氨基酸序列。
- **肽段长度**：官方无硬限制；本 benchmark 覆盖 8–14mer，全部无 NaN。
- **HLA 格式**：模糊字符串匹配，以下均可且无需转换：`HLA-A*02:01`（本项目标准格式，直接透传）/ `A*02:01` / `A0201` / `HLAA0201`。
- **是否需基因组 / WT 肽**：均否（本 benchmark 同时喂 MT + WT，分别打分）。
- **输入样例**（实测）：
  ```
  mhc,pep
  HLA-A*24:02,RLETIRNPK
  HLA-A*03:01,RLETIRNPK
  HLA-B*40:01,AAAMRILHN
  ```
  实测输入 53582 行（MT + WT 全量）。

---

## 3. 参数设置

| 参数 | 说明 | 本项目用值 |
|---|---|---|
| `-i` | 输入 CSV 路径 | bigmhc_input.csv |
| `-m` | 模型模式：`el`（洗脱配体）/ `im`（免疫原性） | **im**（固定） |
| `-a` | allele 所在列（0-based） | 0 |
| `-p` | peptide 所在列（0-based） | 1 |
| `-c` | 跳过表头行数 | 1 |
| `-d` | 计算设备：`cpu` / `0`（首块 GPU）/ `all` | cpu（本地）；HPC 建议 0 |
| `-o` | 输出路径（不写则 `<input>.prd`） | 显式指定 |
| `-j` | DataLoader workers | Windows 须 1（spawn OOM）；HPC 建议 4–8 |
| `-v` | 打印进度 | 1 |

**完整命令**（须从 `repo/src/` 目录运行，predict.py 有相对路径依赖）：
```bash
cd repo/src
python predict.py -i=bigmhc_input.csv -m=im -a=0 -p=1 -c=1 -d=cpu -o=bigmhc_output.prd -j=4 -v=1
```
- `-m=im` 时自动加载 7 个 checkpoint（`bat512/im` ~ `bat32768/im`）ensemble，取平均分。

---

## 4. 输出格式及含义

- **输出文件**：扩展名 `.prd`（实为标准 CSV）。
- **关键列**：

| 列名 | 含义 |
|---|---|
| `mhc` | 原始 HLA 等位字符串（未规范化） |
| `pep` | 肽段序列 |
| `tgt` | 标签列（推理时为空 NaN） |
| `len` | 肽长（int8） |
| `BigMHC_IM` | **免疫原性预测分数，∈ [0, 1]，越高越免疫原** |

- **分数类型 / 方向 / 范围**：连续 [0, 1]，**越高越免疫原，直接使用，无需翻转**。
- **能否定量免疫强弱**：✅ 是（0–1 连续，可排名）——契合项目核心目标。
- **实测输出**：覆盖 53582 行（MT + WT），回贴 universe 后 34247 行，**0 NaN**，BigMHC_IM 范围 0.0–0.95；EL 模式官方 `.cmp` 验证 PASS（差异 4.5e-7），证明权重与管道正确。最终产物 `BigMHC_DS1DS2_scores.csv`。

---

## 5. 最新 benchmark 结果（DS2 ELISpot）

> 数据源：`analysis/metrics_ds2_16tools.csv` + `analysis/per_patient_spearman_16tools.csv`（2026-06-28 全量重算）。im 模式 = 7 模型 ensemble。

- **覆盖率**：n_pep = **101**（DS2 全部 101 个肽，肽段层 34247 行 0 NaN，覆盖完整）。
- **per-patient Fisher-z 加权 ρ（主指标）**：**−0.014**，95% CI [−0.242, +0.215]（n_patients = 9）——CI 跨 0，无显著患者内相关。
- **全局 Spearman ρ（max 聚合，对照）**：ρ = **−0.041**（p = 0.684，不显著）。
- **AUC（max，SFC > 0）**：**0.499**。

**小结**：BigMHC 在 DS2 ELISpot 上 ρ 接近 0（略负）、AUC ≈ 0.50，per-patient CI 跨 0，本数据集上未显现免疫强弱定量能力。需注意 DS2 样本量小（101 肽），结论受限于该集规模。

---

## 6. 部署环境简述

- **部署状态**：RUN_DONE（本地 Windows，CPU，7 模型 ensemble，53582 对）。
- **平台**：Python 3.9+；NumPy 1.21.5 / PyTorch 1.13.0 / pandas 1.4.4 / psutil 5.9.4；无强制 GPU（`-d=cpu` 即可），GPU 大幅加速。
- **关键坑**：
  1. 须从 `repo/src/` 启动（内部相对路径找 `../../models/` 与 `../data/pseudoseqs.csv`）；
  2. git clone 约 5GB（含 Git LFS 权重），须先 `git lfs install`；
  3. Windows 多 worker DataLoader spawn 模式 OOM → 本地必须 `-j=1`；HPC（Linux）无此限制。
- 详细命令见同目录《环境配置命令_回顾记录.md》及 `HPC/deploy/bigmhc_im/NOTES.md`。
