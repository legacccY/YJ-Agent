# BigMHC (-m=im) — 信息收集卡（PPT 素材）

> 4 类信息来源：DEPLOY_TRACKER §Tier-2 + HPC/deploy/bigmhc_im/NOTES.md（2026-06-26 联网核实）。实跑项以「实测」标注。

## 0. 定位 / 一句话

**大规模迁移学习 pMHC 免疫原性预测**（先在数十万条 MHC-I 洗脱配体上预训练 EL → 下游迁移到免疫原性标签 IM），7 个 checkpoint ensemble。  
**输出 BigMHC_IM ∈ [0,1]，越高越免疫原**，可定量排名。  
repo：github.com/KarchinLab/bigmhc；Johns Hopkins Karchin Lab；2023 Nature MI。

## 1. 输入数据模板 / 格式

- **文件格式**：CSV（有表头）
- **必填列 / 字段**：
  - 列 0（`mhc`）：HLA allele
  - 列 1（`pep`）：肽段氨基酸序列
- **肽段长度**：官方无硬限制；实测 benchmark 覆盖 8–14mer，全部无 NaN
- **HLA 格式**：模糊字符串匹配，以下均可（**无需格式转换**）：
  - `HLA-A*02:01`（本 benchmark 标准格式，直接透传）
  - `A*02:01` / `A0201` / `HLAA0201` 等等价
- **是否需基因组数据（RNA-seq/VCF/表达量）**：否
- **是否需野生型（WT）肽**：否（但本 benchmark 同时喂 MT+WT，分别打分）
- **实测输入样例**（实测）：
  ```
  mhc,pep
  HLA-A*24:02,RLETIRNPK
  HLA-A*03:01,RLETIRNPK
  HLA-B*40:01,AAAMRILHN
  ```
- **实测行数**：53582 行（MT+WT 全量）

## 2. 运行参数设置

| 参数 | 说明 | 本 benchmark 用值 |
|---|---|---|
| `-i` | 输入 CSV 路径 | bigmhc_input.csv |
| `-m` | 模型模式：`el`（洗脱配体）/ **`im`（免疫原性）** | **im**（固定） |
| `-a` | allele 在第几列（0-based） | 0 |
| `-p` | peptide 在第几列（0-based） | 1 |
| `-c` | 跳过表头行数 | 1 |
| `-d` | 计算设备：`cpu` / `0`（第一块 GPU）/ `all` | `cpu`（Windows 本地）；HPC 建议 `0` |
| `-o` | 输出路径（不写则 `<input>.prd`） | 显式指定 |
| `-j` | DataLoader workers | Windows 须 1（spawn OOM）；HPC 建议 4-8 |
| `-v` | 打印进度 | 1 |

**完整命令行**（从 `repo/src/` 目录运行，predict.py 有相对路径依赖）：

```bash
cd HPC/deploy/bigmhc_im/repo/src
python predict.py \
  -i=/path/to/bigmhc_inputs/bigmhc_input.csv \
  -m=im -a=0 -p=1 -c=1 -d=cpu \
  -o=/path/to/bigmhc_inputs/bigmhc_output.prd \
  -j=4 -v=1
```

**模型变体**：`-m=im` 时自动加载 7 个 checkpoint ensemble（`bat512/im` ~ `bat32768/im`），取平均分。

⚠️ **Windows 坑**：多 worker DataLoader 在 spawn 模式下大数据 OOM → 本地必须 `--jobs 1`；正式跑在 HPC（Linux）无此限制。  
⚠️ **运行目录**：必须从 `repo/src/` 启动（内部用相对路径 `../../models/` + `../data/pseudoseqs.csv`）。  
⚠️ **git clone ~5GB**（含 Git LFS 模型权重），需 `git lfs install` 后再 clone。

## 3. 输出数据格式 + 含义

- **输出文件格式**：CSV（扩展名 `.prd`，实为标准 CSV）
- **关键列 + 含义**：

| 列名 | 含义 |
|---|---|
| `mhc` | 原始 HLA allele 字符串（未规范化） |
| `pep` | 肽段序列 |
| `tgt` | 标签列（推理时为空 NaN） |
| `len` | 肽长（int8） |
| `BigMHC_IM` | **免疫原性预测分数，∈ [0,1]，越高越免疫原** |

- **分数类型**：连续 [0,1]
- **分数方向**：**越高越免疫原，直接用，无需翻转**
- **能否定量免疫强弱**：✅ 是（0-1 连续，可排名）← 项目核心目标
- **实测输出**（实测）：
  - 覆盖 53582 行（MT+WT）→ 回贴 universe → 34247 行
  - BigMHC_IM 范围：**0.0–0.95**；全 34247 行 **0 NaN**
  - EL 模式官方 `.cmp` 验证 PASS（diff 4.5e-7），权重完整管道正确

**本 benchmark 最终产物**：`BigMHC_DS1DS2_scores.csv`（列：Dataset, Peptide_ID, HLA_Allele, MT_Subpeptide, MT_BigMHC, WT_BigMHC）

## 4. 简介（特点 / 优势）

- **方法**：两阶段迁移学习深度 ensemble。
  1. Stage 1（EL）：在 MHC-I 质谱洗脱配体数据（数十万条）上预训练，学 pMHC 提呈规律
  2. Stage 2（IM）：下游 fine-tune 到有标注的免疫原性数据；7 个不同 batch-size checkpoint ensemble 平均
- **训练数据**：MHC-I 洗脱配体大规模 MS 数据（EL stage）+ IEDB/文献免疫原性标注（IM stage）
- **特点 / 优势**：
  - **pan-allele**：覆盖 >500 等位基因（`data/pseudoseqs.csv`），无需特定 allele 训练
  - HLA 格式宽容（模糊匹配），输入无需转换
  - 预训练规模最大，两阶段迁移为现代范式代表；Nature MI 2023 高可信
  - CPU 推理可行，HPC GPU 显著加速
  - 许可：**BigMHC Academic License（学术非商用）**，发数字 ✅，商用需另签协议
- **局限**：
  - 不直接建模 TCR 识别；IM ensemble 推理 CPU 较慢（7 checkpoint）
  - 需 git-lfs clone（~5GB）
  - Windows 多 worker 有 OOM 坑

## 部署记录

- **repo**：https://github.com/KarchinLab/bigmhc
- **论文**：*Deep neural networks predict class I MHC epitope presentation and transfer learn neoepitope immunogenicity*，2023 · Nature Machine Intelligence，DOI [10.1038/s42256-023-00694-6](https://doi.org/10.1038/s42256-023-00694-6)
- **语言 / 框架**：Python 3.9+；NumPy 1.21.5 / PyTorch 1.13.0 / pandas 1.4.4
- **外部许可证工具**：无
- **GPU 需求**：无强制（`-d=cpu` 即可）；GPU 大幅加速
- **许可**：BigMHC Academic License（学术非商用，Johns Hopkins Karchin Lab）；发数字 ✅
- **部署状态**：✅ **RUN_DONE**（本地 Windows CPU，7 模型 ensemble，53582 对）
- **部署文件**：`HPC/deploy/bigmhc_im/`（prep_input.py / run_bigmhc_im.py / parse_output.py / NOTES.md）
- **实测输出**：`BigMHC_DS1DS2_scores.csv`，34247 行，0 NaN，BigMHC_IM 0.0–0.95

---

**为什么选作对比**：代表「大规模预训练 + 下游迁移」现代范式，Nature MI 2023 高可信，同类比较精度最优、覆盖 >500 等位基因 pan-allele。reviewer 会注意它的缺席。（来源：NEWTOOLS_LIT_MATRIX §二 §6）
