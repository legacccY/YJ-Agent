<!-- ============================================================
QuantImmuBench 溯源表（PROVENANCE_TABLE）——管道单一真源 + 可复现溯源
- 目的：把每个最终数字 / 图 / 表 ← 生成脚本 ← 输入真源的三层链路写清，供投稿复现 + 防散落。
- 数字纪律：本表所有数字 = 主线已 Bash 核实的干净重建口径（真源 = RESULTS_CLEAN_SUMMARY.md
  + data/frozen/pooled_clean_9mer.csv），不含旧 101 肽口径值。写者零自创数字。
- 本表是「地图」不是「结果档」：任何 headline 引用以下游 csv / summary.json 为准，本表只标路径与字段。
============================================================ -->

# QuantImmuBench — 数字 / 图 / 表溯源表（PROVENANCE_TABLE）

> **一键复现**（两步，从 raw 冻结层重放到全下游）：
> 1. `python scripts/rebuild_canonical.py --verify` —— 重建 canonical（`--verify` 证新旧 0 差异，断言 `new.equals(canon) == True`）。
> 2. `python analysis/official/run_downstream.py --run` —— 读 canonical 重跑全部下游分析（Tier 3 各 csv）。
>
> 五层链路：**Tier 0 raw 冻结 → Tier 1 merged base → Tier 2 canonical → Tier 3 下游分析 → Tier 4 叙事 / 图 / ppt**。每层一张三列表（最终产物 | 生成脚本 | 输入真源），末尾一张「关键 headline 数字 ← 字段 ← csv」逐条溯源表。
>
> 冻结物（Tier 0/1/2）带 sha256，登记于 `data/frozen/PROVENANCE.json`；核完整性用 sha 而非重跑。

---

## Tier 0 — raw 真源（冻结，不重跑，工具部署产物）

| 最终产物 | 生成脚本 | 输入真源 |
|---|---|---|
| `data/frozen/ds2_official_groundtruth.csv` | `analysis/phase0/p0a_build_groundtruth.py` | `data/OFFICIAL_DO_NOT_TOUCH/ELISPOT_OFFICIAL_Braun2025_MOESM4.xlsx` —— `In Vitro` sheet = 130 肽 ground truth（唯一真值）；`Ex Vivo` sheet = 36 行池级逐周（未用）。sha256 见 `PROVENANCE.json` 键 `official_xlsx`。**只读，不可改。** |
| `scripts/out_official/<Tool>_official.csv`（39 个） | `scripts/build_official_from_raw.py` | 30 工具 raw 输出（HPC deploy 产物，冻结不重跑） |

---

## Tier 1 — merged base（冻结）

| 最终产物 | 生成脚本 | 输入真源 |
|---|---|---|
| `scripts/out/merged_all_tools_30_official.csv`（34703 行长表） | `scripts/merge_official_30.py` | `scripts/out_official/<Tool>_official.csv`（39 个）+ backbone |

---

## Tier 2 — canonical（`scripts/rebuild_canonical.py` 一键重建）

`rebuild_canonical.py` 把下列步骤按固定序链成一条管道；`--verify` 重放后断言与已冻结 canonical `new.equals(canon) == True`（0 差异）。

| 最终产物 | 生成脚本 | 输入真源 |
|---|---|---|
| **`data/frozen/pooled_clean_9mer.csv`（130×1536，sha256=`debadd108…`）★主分析 canonical** | `scripts/rebuild_canonical.py`（9mer 主链，见下方步骤序） | `scripts/out/merged_all_tools_30_official.csv` |
| `data/frozen/pooled_clean_8to11mer.csv`（sha256=`843ead08…`，补充口径） | `scripts/rebuild_canonical.py`（8-11mer 支路） | `scripts/out/merged_all_tools_30_official.csv` |
| `data/frozen/PROVENANCE.json`（登记两个 pooled + 上游 sha） | `analysis/phase0/p0f_freeze_provenance.py` | 两个 `pooled_clean_*.csv` + 上游冻结物 sha256 |

**9mer 主链步骤序（`rebuild_canonical.py` 内部，顺序固定）**：
1. `patch_covfix_8tools` —— 8 工具补覆盖。
2. `patch_deephlapan_indel` —— INDEL 展开。
3. `patch_deephlapan_indel`（SNV110）—— 固化原手工丢失步骤（历史手工 pipeline 曾丢此步，现固化进脚本）。
4. `analysis/phase0/p0e2_pool_clean.py --ninemer` —— 池化 + 清洗 → 输出 `pooled_clean_9mer.csv`。

**8-11mer 支路步骤序**：`patch_covfix_8to11` → 同上 deephlapan 两步 → `p0e2_pool_clean.py --w811` → 输出 `pooled_clean_8to11mer.csv`。

---

## Tier 3 — 下游分析（`analysis/official/run_downstream.py --run` 一键重跑，读 canonical）

全部读 Tier 2 canonical（`pooled_clean_9mer.csv` 主口径 / `pooled_clean_8to11mer.csv` 补充口径）。

| outline § | 生成脚本 | 输出 csv |
|---|---|---|
| §3.1 表 5 | `R1_official.py` | `R1_single_maxpool_official.csv` |
| §3.1 图 1 真源 | `recompute_effN/recompute_R1_effN.py` | `recompute_effN/R1_recomputed_effN8.csv`（+ 8to11mer 变体） |
| §3.1 图 1 | `recompute_effN/plot_R1_effN.py` | `figures/fig1_spearman_30tools_9mer_effN8.png` |
| §3.2 | `R2_official.py` | `R2_pooling_sweep_official.csv` + `R2_best_per_tool.csv` |
| §3.3.1 | `R3_official.py` | `R3_fusion_12methods_official.csv` |
| §3.3.2 | `R4_official.py` | `R4_ablation_official.csv` |
| §3.3.3 | `R5_official.py`（+ `--shuffle`） | `R5_nested_lopo_official.csv` + `.summary.json`（+ shuffle） |
| §3.3.3 null | `R5_permutation_null.py`（1000 次置换） | `R5_permutation_null.summary.json` —— 经验 p=**0.013**（null mean≈0，real 0.275 落 98.8 分位，12/1000 ≥ real） |
| §3.3.4 | `R6_official.py` | `R6_robustness_official_results.csv` + `_summary.csv` |
| §3.3.5 | `R7_official.py` | `R7_paired_significance_official.csv` + `.summary.json` |
| §3.4 | `R8_official.py` | `R8_unified_ranking_official.csv` |
| §7 补充 | `R9/S1/S2/Q2_*` | 对应 csv |

---

## Tier 4 — 叙事 / 图 / ppt

| 最终产物 | 生成脚本 / 来源 | 输入真源 |
|---|---|---|
| `RESULTS_CLEAN_SUMMARY.md`（当前主叙事真源） | 人工汇编 | Tier 3 各 csv / summary.json |
| `QuantImmuBench_progress_v4_rev5_2026-07-04.pptx` | 人工汇编 | `figures/`（含 `fig1_spearman_30tools_9mer_effN8.png` 等） |

---

## 关键 headline 数字 ← 字段 ← csv（逐条溯源）

> 每条 = 数字（主线已 Bash 核实） ← 取自 csv 的哪个字段 ← 哪个 csv / summary.json 文件。引 tex 前仍须过 verifier 三方对账。

| outline § | headline 数字 | 字段 | 输入真源文件 |
|---|---|---|---|
| §3.1 | top-1 **MHCnuggets ρ=+0.4466**（max\|ρ\|） | `fisherz_rho` | `recompute_effN/R1_recomputed_effN8.csv` |
| §3.1 | top-2 **netMHCpan_BA +0.3917** | `fisherz_rho` | `recompute_effN/R1_recomputed_effN8.csv` |
| §3.1 | top-3 **MHCflurry +0.3079** | `fisherz_rho` | `recompute_effN/R1_recomputed_effN8.csv` |
| §3.1 | effN 敏感性：top-2 在 effN **5/8/10** 三档稳定 | 三档 ρ 列 | `recompute_effN/R1_effN_sensitivity_5_8_10.csv` |
| §3.2 | 亲和 / 结合类 best pooling = **聚合类**（netMHCpan_BA = `topk_k20_a0p5` 等，无一为 max） | `best_lenctrl` | `R2_best_per_tool.csv` |
| §3.3.3 | nested-LOPO **ρ=0.275**（控肽长 0.257） | LOPO ρ 字段 | `R5_nested_lopo_official.summary.json` |
| §3.3.3 | **oracle=0.297**，LOPO↔oracle **gap=0.018** | oracle ρ / gap 字段 | `R5_nested_lopo_official.summary.json` |
| §3.3.3 null | shuffle-null（1000 次置换）经验 p = **0.013**（real 0.275 落 98.8 分位） | `empirical_p_onesided` | `R5_permutation_null.summary.json` |
| §3.3.5 | 整合（SURV6 geomean）**=0.366** vs 最强单 MHCnuggets **=0.4466**，**Δ=−0.081**，**p=0.46（裸）/ 0.22（控肽长）** | 配对检验 Δ / p 字段 | `R7_paired_significance_official.summary.json` |
| §2.1 数据 | **130 肽 = 101 SNV + 29 非SNV** | `Variant_Type` | OFFICIAL `In Vitro` sheet（`ELISPOT_OFFICIAL_Braun2025_MOESM4.xlsx`） |
| §2.1 数据 | indel 展开口径**不对称**：SNV 全展开 8-14mer / DEL+INS 28 肽仅 9mer | 派生自 `Variant_Type` + 展开逻辑 | 同上 xlsx + Tier 2 canonical 展开步骤 |

---

## 复现与合规备注

- **完整性优先用 sha 不重跑**：Tier 0/1/2 冻结物核 sha256（`PROVENANCE.json`），仅需重放时才跑 `rebuild_canonical.py --verify`。
- **DTU 许可**：netMHCpan_BA、TSCAPE 等 DTU 工具数字 pending DTU consent（STORY §7.3 / ACCEPTANCE G8），投稿前须取书面同意；本表登记其溯源路径不代表已获再分发许可。
- **§3.3.3 shuffle-null 已回填**（2026-07-04）：1000 次置换经验 p=0.013（null mean≈0，real 0.275 落 98.8 分位，12/1000 ≥ real），信号显著非泄漏。真源 `R5_permutation_null.summary.json` + `R5_permutation_null_draws.csv`。
