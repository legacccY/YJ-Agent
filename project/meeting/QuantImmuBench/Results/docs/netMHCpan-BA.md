# netMHCpan-4.1 -BA（结合亲和力 proxy 基线）— 交付说明文档

> 🔴 **许可证红线（最高优先，必读）**：netMHCpan-4.1 为 **DTU（丹麦技术大学）学术许可**。**未经 DTU 书面同意，不得向第三方发布或分享由 netMHCpan 输出衍生的任何 benchmark 数字。** 本工具所有输出行均标记 `pending_DTU_consent = True`，投稿 / 对外发布前必须先取得 DTU 书面同意并相应处理。
>
> 服务项目：QuantImmuBench（癌症个性化新抗原疫苗协作项目）。本文为对外交付说明，数字均经 CSV 复核。
> 数据真源：`analysis/metrics_ds2_16tools.csv`（全局指标）、`analysis/per_patient_spearman_16tools.csv`（患者分层）。
> 详细部署命令见同目录《环境配置命令_回顾记录.md》。

---

## 1. 工具简介

**netMHCpan-4.1（-BA 模式）** 是 pMHC I 类结合亲和力预测的领域标准工具，本 benchmark 中作为**结合亲和力 proxy 基线**——用「结合越强」这一信号去近似「越可能免疫原」，检验单纯结合亲和力对免疫原性定量的解释力上限。

- **原理 / 方法**：基于 NNAlign 框架的人工神经网络集成，对给定 HLA allele 与肽段预测结合亲和力（`-BA` 模式同时给出 nM 亲和力与 `%Rank_BA` 百分位排名）。`%Rank_BA` 越低代表结合越强。本 benchmark 将其取负（`netmhcpan_ba_score = -Rnk_BA`），使「分数越高 = 结合越强 = 越可能免疫原」与其他工具方向一致。
- **特点 / 优势**：领域金标准、覆盖 allele 广、运行快（CPU）；作为结合亲和力 proxy，可与真正的免疫原性工具对照，区分「结合」与「免疫原性」两类信号。
- **局限**：仅预测结合亲和力，不直接建模 TCR 识别 / 免疫原性；作为 proxy 其与 ELISpot 强弱的相关性本就预期有限。
- **repo / 来源**：DTU Health Tech，netMHCpan-4.1（学术许可申请获取）。
- **许可证**：**DTU 学术许可——跑出的 benchmark 数字未经 DTU 书面同意禁止对第三方发布（见顶部红线）。**

---

## 2. 输入数据模板 / 格式

- **文件格式**：`.pep` 文件，每行一条肽序列；按 allele 分文件（`prep_netmhcpan_ba.py` 从 `master_backbone.csv` 生成 per-allele `.pep` + `pep_index.csv` + `allele_map.tsv`）。
- **HLA 格式**：随上下文不同——

  | 上下文 | 格式 | 示例 |
  |---|---|---|
  | `master_backbone.csv` | `HLA-A*02:01` | 带 `*` 带 `:` |
  | netMHCpan CLI `-a` | `HLA-A02:01` | 去 `*`，保留 `:` |
  | `.pep` 文件名 | `HLA-A02-01.pep` | 去 `*`，`:` → `-` |

  转换：`hla_to_netmhcpan(h) = h.replace('*', '')`。
- **是否需基因组数据 / 野生型肽**：均不需要（MT、WT 子肽分别打分）。

---

## 3. 参数设置

按 allele 循环调用 netMHCpan，使用 `-BA`（输出结合亲和力）与 `-xls`（输出表格）模式：

```bash
# Step 1（本地）：生成 per-allele .pep + index
python prep_netmhcpan_ba.py
# Step 2：上传 inputs 目录至 HPC
# Step 3（HPC）：按 allele 批量打分
sbatch run_netmhcpan_ba.sh        # 内部循环 allele，逐个 netMHCpan -BA -xls
# Step 4：解析 *_out.xls + pep_index → 汇总 CSV
python parse_netmhcpan_ba.py
```

HPC 二进制：`/gpfs/work/bio/$HPC_USER/quantimmu/ext_tools/netMHCpan-4.1/netMHCpan`（已按 HPC 路径打补丁，见 `HPC/deploy/hpc_dtu_setup.sh`）。

---

## 4. 输出格式及含义

汇总产物 `netmhcpan_ba_DS1DS2_scores.csv`：

| 列 | 类型 | 含义 |
|---|---|---|
| `bb_idx` | int | join key（对应 `master_backbone.csv`） |
| `netmhcpan_ba_Aff_nM` | float | 亲和力 nM，**越低越强结合** |
| `netmhcpan_ba_Rnk_BA` | float | `%Rank_BA`，**越低越强结合** |
| `netmhcpan_ba_score` | float | `-Rnk_BA`，**越高越强结合 = 越可能免疫原** |
| `is_MT` | bool str | `True` = MT_Subpeptide；`False` = WT_Subpeptide |
| `pending_DTU_consent` | str | 恒为 `True`——见顶部许可红线 |

- **分数方向**：`netmhcpan_ba_score`（= −Rnk_BA）越高越强，与其他工具一致；原始 `Aff_nM` / `Rnk_BA` 则越低越强结合。
- 同一个 `bb_idx` 可能出现两次（MT 与 WT 子肽各一行）。
- **覆盖率**：DS2 全部 101 肽均有分（n_pep=101）。

---

## 5. 最新 benchmark 结果（DS2 ELISpot）

> 🔴 以下数字由 netMHCpan 输出衍生，**`pending_DTU_consent = True`，未经 DTU 书面同意不得对第三方发布**（投稿前处理）。为 IMPROVE 跑通后全量重算结果（P101 / P102 已用修正后 HLA 等位恢复，n_pep=101）。

| 指标 | 数值 |
|---|---|
| n_pep（DS2 唯一肽） | 101 |
| 患者分层 Fisher-z（加权，**主指标**） | **+0.155**，95% CI [−0.079, +0.373]（9 名患者） |
| Spearman ρ（max 聚合，对照） | **+0.090**（p = 0.370，n.s.） |
| AUC（max，SFC > 0） | **0.468** |
| 覆盖率 | 100%（DS2 全部 101 肽有分） |

**解读**：作为纯结合亲和力 proxy，netMHCpan-BA 在 max 聚合下相关性弱（ρ≈+0.09，不显著）、AUC 接近随机；但患者分层 Fisher-z（+0.155）为本批工具中相对较高，提示「结合强弱」在患者内仍携带一定免疫原性信号，与「结合 ≠ 免疫原性」的整体结论一致。

---

## 6. 部署环境简述

- 运行平台：XJTLU HPC（per-allele 循环，CPU 推理，SLURM 提交）。
- GPU 需求：无。
- 部署状态：✅ 跑通（netMHCpan-4.1 已装并按 HPC 路径打补丁）。
- 部署文件：`HPC/deploy/netmhcpan_ba/`（`prep_netmhcpan_ba.py` / `run_netmhcpan_ba.sh` / `parse_netmhcpan_ba.py` / `README.md`）；许可配置见 `HPC/deploy/hpc_dtu_setup.sh`。
- 详细安装与运行命令见同目录《环境配置命令_回顾记录.md》。
