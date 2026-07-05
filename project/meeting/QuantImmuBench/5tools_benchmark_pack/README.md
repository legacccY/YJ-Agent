# 5 工具 × 130 肽 新抗原免疫原性三层横评 — 可复现包

> **一句话**：DeepHLApan / PRIME / ImmuneApp / HLAthena / MHLAPre 五个工具，在 130 条 Dataset2 新抗原肽（ELISpot 为真值）上做横向 benchmark。本包从**已存工具输出**一键复现 PPT 里那张「三层横评表」（患者内 Fisher-Z 加权 Spearman / 全局 Spearman / AUC），数字逐值可核。

---

## 一、一键复现（唯一要跑的命令）

```bash
pip install -r requirements.txt      # pandas / numpy / scipy / scikit-learn / openpyxl
python run.py
```

`run.py` 会：① 读 `tool_outputs/` 里 5 工具已存的推理输出 + `data/` 里 130 肽 ELISpot 真值 → 重算三层横评表，写到 `results/`；② 自动与 `expected_results/`（原始 HPC 产出）逐值核对，打印 **PASS/FAIL**。

预期输出（与 PPT 一致）：

```
      Tool  is_immunogenicity_tool  FisherZ_rho    FisherZ_95CI  Global_rho    AUC
   MHLAPre                    True       0.2235  [0.034, 0.397]      0.2642 0.9968
     PRIME                    True       0.2033  [0.013, 0.379]      0.2264 0.5855
  HLAthena                   False       0.2001  [0.010, 0.377]      0.1368 0.4375
 ImmuneApp                    True       0.1715 [-0.020, 0.351]      0.0364 0.5787
DeepHLApan                    True       0.0092 [-0.182, 0.200]     -0.1289 0.4040
PASS ✓ 复现结果与 PPT 参考表逐值一致
```

> ⚠️ 关于排序：**MHLAPre 的 AUC=0.9968 是数据泄露产物**（自训复刻版、训练/预测同批数据），不可当真实能力；诚实评估（GroupKFold 留一患者 CV）AUC≈0.53，脚本见 `dataset_scripts/mhlapre_groupkfold_cv.py`。**HLAthena 是「提呈」工具**，仅作 presentation baseline 单列，不与免疫原性工具直接排名。剔除这两条 caveat 后，**PRIME（+0.203）是已发表免疫原性工具里最优**，但绝对值仍有限——五工具均未达强相关。

---

## 二、目录结构

```
5tools_benchmark_pack/
├── run.py                     # ★ 一键入口：复现 + 自动核对
├── evaluate_three_tier.py     # ★ 评估核心（三层指标，口径见文件头注释）
├── requirements.txt
├── README.md                  # 本文件
│
├── data/                      # 数据集（真值）
│   ├── Elispot_Dataset2_complete.xlsx   # 130 肽 + ELISpot SFC + HLA + TPM（评估真值）
│   └── HLA_nomenclature_map.xlsx        # HLA 命名格式转换表（26 等位基因）
│
├── tool_outputs/              # 5 工具已存的推理输出（评估直接读这里）
│   ├── DeepHLApan_merged_results.xlsx   # backbone + binding/immunogenic 分
│   ├── ImmuneApp_merged_results.xlsx    # backbone + Immunogenicity_score
│   ├── MHLAPre_merged_results.xlsx      # backbone + MHLAPre_Score
│   ├── HLAthena_merged_results.xlsx     # backbone + presentation_score（肽级）
│   └── PRIME_dataset2_MT_prime.txt      # PRIME 原生 raw 输出（含 Score_bestAllele）
│
├── expected_results/          # 原始 HPC 产出，作复现核对基准
│   ├── metrics_three_tier.csv
│   └── per_patient_details.csv
│
├── results/                   # run.py 生成（复现产物）
│
├── dataset_scripts/           # 【附录】数据集处理脚本（构建 130 肽 + 各工具输入）
│   ├── _build_all.py                    # MOESM4 原表 → 130 肽 → 5 工具输入
│   ├── _build_mhlapre_inputs.py         # MHLAPre 训练/预测输入（带 label）
│   ├── build_merged_results.py          # 5 工具输出 → merged xlsx
│   ├── mhlapre_groupkfold_cv.py         # MHLAPre 诚实评估（去数据泄露）
│   └── investigate_deephlapan.py        # DeepHLApan 分数方向排查
│
├── tool_run_scripts/          # 【附录】5 工具在 HPC 上的推理脚本（sbatch/容器命令）
│   └── run_*.sbatch, submit_all.sh, ...
│
└── docs/                      # 【附录】5 工具逐个说明（原理/输入/输出/坑）+ 环境配置命令
```

---

## 三、三层评估口径（`evaluate_three_tier.py` 已对 expected 逐值核验，diff=0）

| 步骤 | 做法 |
|---|---|
| **pooling（子肽→肽级）** | 每条 130 肽按 8-11mer 滑窗展开为「子肽 × HLA」并各自打分后，取该 Peptide_ID 全部行的 **max** 作肽级分（方向统一：越大越免疫原） |
| **各工具评估分列** | DeepHLApan→`immunogenic_score`｜PRIME→`Score_bestAllele`｜ImmuneApp→`Immunogenicity_score`｜HLAthena→`presentation_score`（本已肽级）｜MHLAPre→`MHLAPre_Score` |
| **Tier-1 主指标** | 患者内 Fisher-Z 加权 Spearman：每患者内 ρ → 偏差校正 `z=arctanh(clip(ρ,±0.999))−ρ/(2(n−1))` → 逆方差权重 `w=n−3` → `z̄=Σwz/Σw` → `ρ_agg=tanh(z̄)`；95%CI=`tanh(z̄±1.96/√Σw)`；仅计肽数 n≥4 的患者（9 患者 P101–P110 缺 P103，肽数累加=130） |
| **Tier-2 对照** | 全局 Spearman：130 肽混合算一次 |
| **Tier-3 辅助** | AUC：label = ELISpot>0（有无免疫反应二分类判别力） |

---

## 四、从零重跑工具（附录，需 HPC）

本包的一键复现**只覆盖「工具输出 → 三层表」**这一段（本地可跑）。5 工具本身的推理需 HPC + Singularity 容器 + 各自老环境（TF1.15 / PyTorch1.12 / C++ 编译），无法单机一键复现，脚本作参考放在 `tool_run_scripts/` + `docs/环境配置命令.md`。完整链路：

```
data/MOESM4 原表 ──_build_all.py──▶ 130 肽 + 5 工具输入
   └─(HPC: tool_run_scripts/submit_all.sh 各容器推理)──▶ 各工具 raw 输出
        └─build_merged_results.py──▶ tool_outputs/*_merged_results.xlsx
             └─evaluate_three_tier.py──▶ results/ 三层横评表  ★ 本包一键段
```

> `dataset_scripts/` 里的路径为原 HPC 环境写死（`/gpfs/work/bio/zichenli24/...` 与 `D:\D_Agent\...`），仅作参考，本地重跑数据集构建需按实际路径调整并备齐 MOESM4 原始 xlsx。

---

## 五、诚实 Caveat（写 PPT/论文必读）

- **MHLAPre**：自训复刻版（官方权重不可得），训练/预测同批数据 → AUC=0.997 是**数据泄露**，Fisher-Z 也高估。真实性能用 GroupKFold（按患者分组）CV，AUC≈0.53。对外引用只用 CV 值。
- **HLAthena**：MHC-I 提呈预测工具，非免疫原性工具。Fisher-Z 显著但 AUC=0.44（近随机）→ 印证「提呈 ≠ 免疫原性」。仅作 presentation baseline 单列。
- **DeepHLApan**：`immunogenic_score` 极度聚集在 0.97 附近、方差极小 → 对 DS2 基本无区分力（Fisher-Z≈0，全局 ρ 反向）。
- **数据集**：130 肽含 28 个 indel + 1 SNV（曾被遗漏，从 101 恢复到 130）；indel 无 WT 序列（frameshift 处野生型滑窗无生物学意义，非 bug）。
- 所有 benchmark 数字可从 `results/` ← `tool_outputs/` ← 各工具推理完整溯源。
