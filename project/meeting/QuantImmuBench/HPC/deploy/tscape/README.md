# T-SCAPE — QuantImmuBench §Tier-3 部署说明

> 服务项目：quantimmu-bench §工具扩张v2 lever=部署 T-SCAPE apples-to-apples 免疫原性工具

---

> ## ⚠️ 许可声明（顶部醒目标注，使用前必读）
>
> **本工具产物仅限学术非商用。**
> T-SCAPE 采用 **CC BY-NC-ND 4.0** 许可（Creative Commons 署名-非商业-禁止演绎 4.0）：
> - **NC（非商业）**：禁止商业用途
> - **ND（禁止演绎）**：禁止对 T-SCAPE 输出进行再发布或衍生作品
> - 仅允许 QuantImmuBench 内部学术评测使用
> - 论文/报告引用时需注明：T-SCAPE (seoklab, CC BY-NC-ND 4.0)，Sci Adv 2025

---

## 工具简介

**T-SCAPE**（T-cell Specificity and Cross-reactivity Analysis in Peptide-MHC Environments）

- **发表**：Science Advances 2025, DOI: 10.1126/sciadv.adz8759
- **作者**：seoklab（首尔国立大学 Chaok Seok 课题组）
- **定位**：2025 SOTA 跨域辅助免疫原性预测工具，基于 pMHC 结构感知的跨域泛化模型
- **类别**：apples-to-apples（免疫原性直接预测，非结合亲和力 proxy）
- **repo**：https://github.com/seoklab/T-SCAPE
- **权重**：https://huggingface.co/seoklab/T-SCAPE（`best_param/` 10 个 task 子目录，共 54.7GB）
- **许可**：CC BY-NC-ND 4.0，**学术非商用**
- **平台**：Linux-only（Windows 不支持）

---

## 输入格式

| 字段 | 要求 |
|---|---|
| CSV 列 | `Allele,Peptide`（T-SCAPE 要求此表头，顺序固定） |
| HLA 格式 | 标准 WHO 格式：`HLA-A*02:01`（含 `*` 和 `:`，**无需转换**） |
| 肽长 | ≤20mer（MHC-I 最优 9mer，超过 20mer 跳过） |
| 配对需求 | **MT-only**（只需突变肽+HLA，无需 WT） |
| 范围 | master_backbone.csv 所有 unique (MT_Subpeptide, HLA_Allele) 对 |

---

## 参数说明（推理）

### Step A: mhc_pseudo_matching.py

```
python mhc_pseudo_matching.py I <input.csv> <input_modified.csv>
```

- `I` = MHC class I（固定参数）
- 功能：过滤到 `MHC_classI_pseudo.csv` 支持的 allele（不支持的行被去掉）
- 输入：tscape_input.csv（列 Allele,Peptide）
- 输出：input_modified.csv（过滤后，格式同输入）

### Step B: inference_csv.py

```
python inference_csv.py --csv_path <input_modified.csv> \
    --inf_type pmhc_im_neo \
    --output <output.csv>
```

- `--inf_type pmhc_im_neo`：cancer neoantigen 任务（**必须此值**，见已知坑 #4）
- 输入：input_modified.csv
- 输出：output.csv（保留 Allele,Peptide 列 + 追加 score 列）

---

## 输出说明

| 列 | 含义 |
|---|---|
| `Allele` | 输入 HLA 等位基因（透传） |
| `Peptide` | 输入肽序列（透传） |
| `score` | 免疫原性预测分（0-1，**>0.5 = 免疫原，越高越强**） |

- **方向无需翻转**：score 越高越强，与 benchmark 其他工具方向一致
- merge 后产生列 `MT_TSCAPE`（= score，MT-only 故无 WT_TSCAPE）
- score 范围 0-1，连续浮点

---

## 已知坑（必读）

### 坑 1：dropout bug（必须 patch，否则推理结果非确定性）

**症状**：同一输入每次跑出不同 score，无法复现。

**根因**：`src/model_fused.py` 第 326 行：
```python
# 错误（原始代码，推理时 dropout 仍激活）：
F.dropout(e, self.dropout)

# 正确（patch 后，推理时 training=False 关闭 dropout）：
F.dropout(e, self.dropout, training=self.training)
```

**修复**：`setup_tscape_hpc.sh` Step 2 自动 patch（sed 命令）。**每次 clone 后必须重新 patch**（PR #3 已提交但官方未合并）。

**验证**：
```bash
grep 'training=self\.training' src/model_fused.py | head -3
```

### 坑 2：权重体积 54.7GB，DTN 预下，GPU 节点不联网

HF 全量 `best_param/` 约 54.7GB（10 个 task）。我们只用 `pmhc_im_neo` 子目录（约 5-6GB）。**必须在登录节点（DTN）预下，GPU 节点不联网、计费从启动算**。

```bash
# 推荐：只下 pmhc_im_neo（节省磁盘）
python -c "
from huggingface_hub import snapshot_download
snapshot_download('seoklab/T-SCAPE', local_dir='/gpfs/work/bio/jiayu2403/quantimmu/t_scape',
                  allow_patterns=['best_param/pmhc_im_neo/*'])
"
```

### 坑 3：无 requirements.txt pin，依赖版本坑

T-SCAPE 无固定依赖版本（无 `requirements.txt`）。安装后如遇版本冲突，需手动降级。
**TODO**：首次跑通后记录实际版本（`conda list -n tscape > tscape_env_frozen.txt`）存档。

### 坑 4：inf_type 必须 pmhc_im_neo，否则分数异常

T-SCAPE 支持多种任务类型（viral/self 等），癌症新抗原必须用 `pmhc_im_neo`。误用其他 `inf_type` 会产生"正常"的 score 但含义不同（见 Issue #1）。

### 坑 5：Linux-only，Windows 不支持

T-SCAPE 依赖 Linux 原生二进制和 CUDA 驱动，不能在 Windows 本地跑。必须在 HPC（Linux gpu4090）或 WSL2 上跑。

### 坑 6：mhc_pseudo_matching 过滤不支持的 allele

部分 HLA allele 不在 T-SCAPE 的 `MHC_classI_pseudo.csv` 中，会被 Step A 过滤。对应 bb_idx 在 `tscape_scores.csv` 中 `MT_TSCAPE=NaN`。benchmark 合并时这些行按 NaN 处理（不参与该工具的 Spearman 相关系数计算）。

---

## 完整运行步骤

### 前置（一次性，在本地或 HPC 登录节点）

```bash
# Step 0: 准备输入（本地 Python 即可）
python HPC/deploy/tscape/prep_tscape_input.py \
    --backbone scripts/out/master_backbone.csv \
    --out-dir scripts/out/newtools/
# 产生：scripts/out/newtools/tscape_input.csv
#       scripts/out/newtools/tscape_input_map.csv

# Step 0b: 烟测准备（5 肽验证格式）
python HPC/deploy/tscape/prep_tscape_input.py \
    --backbone scripts/out/master_backbone.csv \
    --out-dir scripts/out/newtools/ \
    --smoke 5
```

### HPC 安装（一次性，在 DTN 登录节点执行）

```bash
# SSH 到 DTN（对外下载 = 拍板点，主线串行）
ssh jiayu2403@dtn.hpc.xjtlu.edu.cn

# 执行安装脚本（clone + patch + conda env）
bash setup_tscape_hpc.sh
# ⚠️ Step 4 权重下载默认注释掉，确认磁盘后取消注释再执行
```

### HPC 推理

```bash
# 上传输入（本地 → HPC）
# scp scripts/out/newtools/tscape_input.csv \
#     jiayu2403@dtn.hpc.xjtlu.edu.cn:/gpfs/work/bio/jiayu2403/quantimmu/t_scape/inputs/

# 提交 SLURM job
sbatch submit_tscape.sbatch

# 查看进度
squeue -u jiayu2403
tail -f /gpfs/work/bio/jiayu2403/quantimmu/t_scape/logs/tscape_<JOBID>.out
```

### 合并结果（本地）

```bash
# 下载 T-SCAPE 输出（HPC → 本地）
# scp jiayu2403@dtn.hpc.xjtlu.edu.cn:/gpfs/work/bio/jiayu2403/quantimmu/t_scape/outputs/tscape_output.csv \
#     scripts/out/newtools/tscape_output.csv

# 合并回贴 bb_idx
python HPC/deploy/tscape/merge_tscape.py \
    --tscape-out scripts/out/newtools/tscape_output.csv \
    --map scripts/out/newtools/tscape_input_map.csv \
    --out-csv scripts/out/newtools/tscape_scores.csv
# 产生：scripts/out/newtools/tscape_scores.csv（列 bb_idx, MT_TSCAPE）
```

### 烟测命令（5 肽验证推理流程，在 HPC GPU 节点）

```bash
# 准备 5 肽输入（本地）
python HPC/deploy/tscape/prep_tscape_input.py \
    --backbone scripts/out/master_backbone.csv \
    --out-dir scripts/out/newtools/ \
    --smoke 5

# 上传 smoke 输入，在 HPC GPU 节点直接跑（不提交 sbatch，节省调试时间）：
# srun --partition=gpu4090 --gres=gpu:1 --time=00:10:00 --pty bash
# bash run_tscape.sh \
#     /gpfs/.../t_scape/inputs/tscape_input.csv \
#     /gpfs/.../t_scape/outputs/tscape_smoke_output.csv
```

---

## 文件说明

| 文件 | 作用 |
|---|---|
| `prep_tscape_input.py` | 读 master_backbone → unique (MT, HLA) → tscape_input.csv + tscape_input_map.csv；支持 --smoke N |
| `setup_tscape_hpc.sh` | DTN 一次性安装：clone + dropout patch + conda env + 权重下载说明 |
| `run_tscape.sh` | GPU 节点推理：Step A mhc_pseudo_matching + Step B inference_csv |
| `submit_tscape.sbatch` | SLURM 提交脚本（gpu4090, shuihuawang, 1 卡, 4h） |
| `merge_tscape.py` | 读 T-SCAPE output + map → 回贴 bb_idx → tscape_scores.csv |
| `README.md` | 本文 |

---

## 输出文件

| 文件 | 位置 | 列 |
|---|---|---|
| `tscape_input.csv` | `scripts/out/newtools/` | `Allele,Peptide` |
| `tscape_input_map.csv` | `scripts/out/newtools/` | `Peptide,Allele,bb_idx_list` |
| `tscape_output.csv` | HPC outputs/ → 下载到 newtools/ | `Allele,Peptide,score` |
| `tscape_scores.csv` | `scripts/out/newtools/` | `bb_idx,MT_TSCAPE` |

---

## 参考

- repo: https://github.com/seoklab/T-SCAPE
- paper: Science Advances 2025, DOI: 10.1126/sciadv.adz8759
- HF weights: https://huggingface.co/seoklab/T-SCAPE
- dropout PR #3: https://github.com/seoklab/T-SCAPE/pull/3
- score 方向 Issue #1: https://github.com/seoklab/T-SCAPE/issues/1

---

## TODO（未找到官方源，待确认）

- [ ] `pmhc_im_neo` 权重实际大小（全量 54.7GB 是全 10 task；单 pmhc_im_neo 子目录估计 ~5-6GB，**TODO: 下载前核实**）
- [ ] GPU 显存需求（TODO: 核实 24GB RTX4090 是否足够推理全量 34K 肽；单批推理若 OOM 需调 batch size，T-SCAPE 有无 batch 参数待查 repo README）
- [ ] 全量 34247 肽推理估计耗时（TODO: 首次烟测后记录）
- [ ] conda 路径（HPC 上 `/gpfs/work/bio/jiayu2403/.conda` vs `~/miniconda3`，setup 脚本有 TODO 标注）
- [ ] huggingface-cli 在 HPC 是否可用，或需 `pip install huggingface_hub` 后用 Python API
