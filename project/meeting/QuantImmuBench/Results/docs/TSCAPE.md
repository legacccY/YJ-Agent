# T-SCAPE — 交付说明文档

> ⚠️ **许可证警示（醒目）**：T-SCAPE 采用 **CC BY-NC-ND 4.0（署名—非商业性使用—禁止演绎）**。ND 条款禁止任何衍生，NC 条款禁止商业用途——本工具全部产物**仅限学术非商业研究使用**，不得用于商业场景，不得分发修改后的代码 / 权重。
>
> 服务项目：QuantImmuBench（癌症个性化新抗原疫苗协作项目）。本文为对外交付说明，数字均经 CSV 复核。
> 数据真源：`analysis/metrics_ds2_16tools.csv`（全局指标）、`analysis/per_patient_spearman_16tools.csv`（患者分层）。
> 详细部署命令见同目录《环境配置命令_回顾记录.md》。

---

## 1. 工具简介

**T-SCAPE（T-cell Immunogenicity Scoring via Cross-domain Aided Predictive Engine，2025）** 是基于跨域辅助多任务深度学习的 T 细胞免疫原性预测工具。

- **原理 / 方法**：以 ByteNet 为骨架，通过多任务跨域学习联合 HLA 结合、TCR 结合与免疫原性等多个免疫学任务，跨域共享表示；一套权重通过切换 `--inf_type` 即可输出结合 / 免疫原性 / TCR 等多种预测。前身为 TITANiAN（bioRxiv 2025.05.11.653308）。
- **特点 / 优势**：
  - **MT-only**——只需突变肽 + HLA，无需野生型对照，输入门槛低；
  - 一套权重多任务复用；
  - 输出连续 0–1 分，可定量排名；
  - CPU 即可推理，无 GPU 硬约束。
- **局限**：
  - **Linux-only**，且官方发布代码存在 2 个致命 bug + 1 个推理确定性 bug，需修复后才能跑通（详见第 6 节）；
  - 许可 CC BY-NC-ND 4.0，仅限学术非商用，禁止衍生与分发修改版；
  - 肽段 ≤20mer（最优 9mer），长肽受限。
- **论文 DOI**：10.1126/sciadv.adz8759（*T-SCAPE*，Science Advances 2025）；前身 TITANiAN（bioRxiv 2025.05.11.653308）。
- **repo**：https://github.com/seoklab/T-SCAPE ；权重 HuggingFace `seoklab/T-SCAPE`（全量 54.7GB，癌症用例仅需 `best_param/pmhc_im_neo` ≈ 0.53GB）。
- **许可证**：**CC BY-NC-ND 4.0（学术非商用，禁衍生、禁分发修改版）**。

---

## 2. 输入数据模板 / 格式

- **文件格式**：CSV，必填列 `Allele,peptide`（**peptide 列为小写**，实测核对 `example/inputs/pmhc_im.csv`）。
- **肽段长度**：≤20mer，最优 9mer。
- **HLA 格式**：标准型 `HLA-A*02:01`。
- **是否需基因组数据 / 野生型肽**：均不需要（MT-only）。
- **预处理依赖**：推理前须先经 `mhc_pseudo_matching.py I` 给每行贴 pseudo 序列，并过滤掉不在 `MHC_classI_pseudo.csv` 内的不支持 allele。
- **输入样例**：`HLA-A*02:01,sllmwitqv`（peptide 小写）。

---

## 3. 参数设置

两步流程：

```bash
# Step 1：贴 pseudo 序列 + 过滤不支持 allele（I = MHC class I）
python mhc_pseudo_matching.py I input.csv input_mod.csv
# Step 2：推理
python inference_csv.py --csv_path input_mod.csv --inf_type pmhc_im_neo --output out.csv
```

`--inf_type` 任务选择（关键）：

| 取值 | 任务 |
|---|---|
| `pmhc_im_neo` | **癌症新抗原免疫原性（本项目所用）** |
| `pmhc_im_inf` | 感染病免疫原性 |
| `p_im` | 纯肽免疫原性（不含 HLA） |
| `pmhc_ba_I` / `pmhc_ba_II` | MHC class I / II 结合亲和力 |
| `ptcr_ba` | TCR 结合亲和力 |

推理设备 CPU（`device=cpu`），`batch_size=32`；环境 conda + Python 3.10+ + PyTorch；平台 Linux-only。

---

## 4. 输出格式及含义

输出 CSV，关键列 `Allele,peptide,score`：

| 列 | 含义 |
|---|---|
| `Allele` | HLA-A\*xx:xx |
| `peptide` | 肽序列（小写） |
| `score` | 免疫原性分，**0–1 连续，越高越强免疫原**，**>0.5 判为免疫原** |

- **分数类型**：连续 0–1。
- **分数方向**：越高越免疫原，直接使用，无需翻转。
- **能否定量免疫强弱**：可以（0–1 连续，可排名）。
- **覆盖率**：实测输入 32178 个 unique (MT, HLA) 对进入推理；merge 回贴后产物 MT_TSCAPE 列覆盖 **100%（34247/34247 行，0 NaN）**。实测 score 范围 0.0057–0.7716。

---

## 5. 最新 benchmark 结果（DS2 ELISpot）

> 以下为 IMPROVE 跑通后全量重算结果（P101 / P102 已用修正后 HLA 等位恢复，n_pep=101）。

| 指标 | 数值 |
|---|---|
| n_pep（DS2 唯一肽） | 101 |
| 患者分层 Fisher-z（加权，**主指标**） | **+0.0005**，95% CI [−0.226, +0.227]（9 名患者） |
| Spearman ρ（max 聚合，对照） | **−0.139**（p = 0.167，**n.s.**） |
| AUC（max，SFC > 0） | **0.442** |
| 覆盖率 | 100%（34247 / 34247 行有分，0 NaN） |

> ⚠️ **重要措辞约定（请勿误写）**：全量重算后 **TSCAPE 不再呈现「显著负相关」**。全局 Spearman 方向为负，但 **p 值全部不显著（n.s.）**；患者分层后 Fisher-z 几乎为零（+0.0005，CI 跨 0）。因此正确表述为「方向为负但统计不显著」，**不得写成「显著负」**。

**解读**：TSCAPE 在 DS2 上 AUC（SFC > 0）低于随机线（0.442）、全局相关方向为负但不显著；患者内聚合后相关性趋近 0。综合判断为在本数据集上无有效定量信号，方向与多数工具相反但未达统计显著。

---

## 6. 部署环境简述（含官方 bug 修复）

- 运行平台：本地 WSL2，CPU 推理（`device=cpu`，`batch_size=32`），无 GPU 需求；Linux-only。
- 权重：仅下载 `best_param/pmhc_im_neo`（≈ 0.53GB），避免全量 54.7GB。
- 外部许可证工具：无（自带 pseudo 序列 / 权重）。
- 部署状态：✅ 实测全量完成（merge 后 MT_TSCAPE 列覆盖 34247 行，0 NaN）。

**官方代码 3 个 bug（修复后才跑通，修法均有据非臆想）**：

1. **输入列名 bug**：官方文档写大写列名，实际代码读小写 `peptide`，列名不符则读不到肽段。修：输入 CSV 用小写 `peptide` 列。
2. **`pmhc_im_neo` 任务键缺失 → KeyError 崩溃（最致命）**：README 文档化的癌症命令在所有官方版本与全部 fork 都直接 `KeyError`——`load_state_dict` 块与 `task_dict` 都漏了 `pmhc_im_neo` 键，权重根本未载入。据 `torch.load` 实测（ckpt 含 `model_state_dict`，载入官方 `Finaltask1_perf` 架构为 0-key 失配即结构对得上，免疫原性头输出维恒为 `[3]`）补回该键的 state_dict 载入与 task_dict 条目即修复。
3. **dropout 推理确定性 bug**：`model_fused.py:326` 需加 `training=self.training`，否则推理期 dropout 仍激活导致结果非确定性。该修复对应官方 PR#3（未合并）。

- 部署文件：`HPC/deploy/tscape/`（`prep_tscape_input.py` / `setup_tscape_hpc.sh` / `run_tscape.sh` / `submit_tscape.sbatch` / `merge_tscape.py` / `README.md`）。
- 详细安装与运行命令见同目录《环境配置命令_回顾记录.md》。
