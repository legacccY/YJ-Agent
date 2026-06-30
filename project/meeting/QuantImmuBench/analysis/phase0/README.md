# Phase 0 数据地基重建 (QuantImmuBench)

服务 `03_EXPERIMENT_PLAN.md` §3。从官方 ELISPOT xlsx 重建冻结地基，判旧预测复用/重跑，pool 到肽级，冻结 provenance。

唯一准则数据（只读，禁改）：`data/OFFICIAL_DO_NOT_TOUCH/ELISPOT_OFFICIAL_Braun2025_MOESM4.xlsx` sheet `In Vitro`（130 肽 / 9 患者）。所有产物写 `data/frozen/`。

## 跑序

| 步 | 脚本 | 产物 | 依赖 |
|---|---|---|---|
| 1 | `p0a_build_groundtruth.py` | `ds2_official_groundtruth.csv` (130 肽真源 + Elispot) | 官方 xlsx |
| 2 | `p0b_patient_hla.py` | `patient_hla.csv` (逐患者新 HLA-I 等位, 标准化) | 官方 xlsx |
| 3 | `p0_reuse_decision.py` | `REUSE_DECISION.csv` + `RERUN_PEPTIDE_LIST.csv` | p0a + p0b + 旧 `merged_all_tools_29tools.xlsx` |
| 4 | `p0c_subpep_expansion.py` | `subpep_hla_expansion.csv` (重跑肽子肽×HLA 展开) | p0_reuse |
| — | **【主线/外部】补跑工具 + 合并** | `scripts/out/merged_all_tools_30_official.csv` (子肽×HLA 长表) | p0c 展开表 + 旧可复用部分 |
| 5 | `p0e_pool_to_peptide.py` | `pooled_peptide_level_30tools.csv` (130 行, 8 pooling×工具) | 上一步长表 + p0a |
| 6 | `p0f_freeze_provenance.py` | `PROVENANCE.json` (全产物 sha256 指纹) | p0a..p0e |

## 关键说明

- **第 5 步依赖外部补跑**：`merged_all_tools_30_official.csv` 不由本目录脚本产，需主线先按 `RERUN_PEPTIDE_LIST.csv` 补跑 29 缺失肽（全工具）+ P104 新等位 A3001，再与旧 merged 可复用部分合并导出。该表缺失时 `p0e` 清晰报错给依赖说明，不 silent。
- **地基事实（校验门断言/预期）**：130 肽（118 阳/12 阴）；旧预测缺 29 肽 → rerun_full；HLA 仅 P104 DIFF（新 A3001 vs 旧 A0301）→ P104 17 肽 rerun_partial。
- **工具列约定**：长表工具分数列前缀 `MT_<tool>`（沿用 `merged_all_tools_*.xlsx` 惯例）。
- 每脚本独立可跑、`argparse`、零 GPU、纯 numpy Spearman（禁 scipy 防 OMP#15）、pathlib 路径。
- `PROVENANCE.json` 的 `tool_versions` 留 TODO 占位，待 researcher 确认 30 工具版本号填入。
