# gdn2vessel — SOTA 数字表（核源版）

**用途**：§2 Related Work + STORY「SOTA 天花板」锁定表 + L6（拓扑/续连赢 SOTA 参照线）的数字来源。
**纪律**：每个数字附出处（标题 / arXiv 或会议 / 年）。**这些是别人报告的数字，不是我们的——禁止当作我们结果。** 我们自己的数字一律 Bash/Grep 核 csv 后落锁定表。
**最后更新**：2026-06-20（researcher×4 扇出核源）

> ⚠️ **split 不可比总警告**：DRIVE 官方 20/20 split vs 各家自切、CHASE 不同 split、FIVES 不同 4:1 划分——跨论文数字**不可直接比**，每个数字入 tex 必标 split 出处。

---

## 1. 视网膜血管 SOTA 数字表

### DRIVE

| 方法 | 年/来源 | 指标 | 值 | 备注 |
|---|---|---|---|---|
| U-Net (baseline) | — (HM-Mamba 复现) | F1/Dice | 0.8088 | baseline 参照 |
| UNet++ | — | F1/Dice | 0.8230 | |
| IterNet | 2019/AAAI20 | F1/Dice | 0.8205 | |
| SA-UNet | 2020 | F1/Dice / AUC | 0.8263 / 0.9864 | |
| FR-UNet | JBHI 2022 | F1/Dice / AUC | 0.8316 / 0.9889 | 经典强 baseline |
| AttU-Net | — | F1/Dice | 0.8308 | FSG-Net 表 |
| HRNet | — | F1/Dice | 0.8383 | FSG-Net 表 |
| FSG-Net | 2025/arXiv 2501.18921 | F1/Dice / AUC | 0.8323 / 0.9824 | |
| MDFI-Net | 2024/arXiv 2410.15444 | F1/Dice | 0.8379 | |
| EFDG-UNet | 2025/PMC12852779 | F1/Dice / AUC | 0.8412 / 0.9886 | |
| **HM-Mamba** | 2025/Entropy DOI 10.3390/e27080862 | **F1/Dice** / AUC / IoU | **0.8327** / 0.9132 / 0.7164 | Mamba 家族最高 |
| **VFGS-Net** | 2026-02/arXiv 2602.10978 | **Dice** | **0.8323** | 粗调研值核实 ✓ |
| HREFNet | 2025/arXiv 2504.13553 | F1/Dice / **clDice** / AUC | 0.8214 / **0.8240** / 0.9856 | 罕见报 clDice |
| ⛔ RV-GAN | MICCAI 2021 | "F1" 86.90 | **可疑禁用** | 原文只报 AUC，86.90 疑为 MCC/Acc 混用 |

**DRIVE Dice 天花板 ≈ 0.83–0.84**（EFDG-UNet 0.8412 / MDFI-Net 0.8379 最高可核值）。裸 Dice 已饱和（各家差 <1%）。

### CHASE_DB1

| 方法 | 年/来源 | 指标 | 值 |
|---|---|---|---|
| IterNet | — | F1/Dice | 0.8073 |
| SA-UNet | — | F1/Dice / AUC | 0.8153 / 0.9905 |
| FR-UNet | — | F1/Dice | 0.8051 |
| FSG-Net | 2025 | F1/Dice / AUC | 0.8102 / 0.9938 |
| EFDG-UNet | 2025 | F1/Dice / AUC | 0.8469 / 0.9932 |
| **HM-Mamba** | 2025 | F1/Dice / IoU | **0.8197** / 0.6839 | 粗调研值核实 ✓ |
| VFGS-Net | 2026-02 | Dice | 0.8143 |
| HREFNet | 2025 | F1/Dice / **clDice** / AUC | 0.8046 / **0.8293** / 0.9878 |

**CHASE Dice 天花板 ≈ 0.82–0.85**（EFDG-UNet 0.8469 最高）。

### STARE

| 方法 | 年/来源 | 指标 | 值 |
|---|---|---|---|
| FR-UNet | — | F1/Dice | 0.8130 |
| AttU-Net | — | F1/Dice | 0.8477 |
| **FSG-Net** | 2025/arXiv 2501.18921 | **F1/Dice** / AUC / Sen | **0.8510** / 0.9897 / 0.8661 | **STARE 最高，> 原 STORY 写的 83.21** |
| MDFI-Net | 2024 | F1/Dice | 0.8581 | ⚠️ 极高，需核 split |
| HM-Mamba | 2025 | F1/Dice | 0.8239 |
| HREFNet | 2025 | F1/Dice / clDice | 0.7629 / 0.8030 | STARE 偏低，疑 split 差异 |
| FA-Net (Universal) | 2025/arXiv 2502.06987 | Dice / **clDice** | 0.8357 / **0.8763** | 多模态 |

**STARE Dice 天花板 ≈ 0.85**（FSG-Net 0.8510 可核 / MDFI-Net 0.8581 待核 split）。**原 STORY 锁定表的 STARE 83.21（VFGS-Net）偏低，应上修。**

### HRF

| 方法 | 年/来源 | 指标 | 值 |
|---|---|---|---|
| FSG-Net | 2025 | F1/Dice / AUC | 0.8157 / 0.9874 |
| VFGS-Net | 2026-02 | Dice | 0.8560 | HRF 上较高 |

**HRF 数字最稀缺**，主流 2025 方法只 FSG-Net 报。

### FIVES

| 方法 | 年/来源 | 指标 | 值 |
|---|---|---|---|
| UNet | — (PASC-Net 复现) | F1/Dice | 80.80±1.34 |
| clDice loss + UNet | — | F1/Dice | 85.92±0.76 |
| CS²-Net | — | F1/Dice | 88.59±0.55 |
| nnUNet | — | F1/Dice | 89.40±0.49 |
| CoANet | — | F1/Dice | 89.66±0.50 |
| **PASC-Net** | 2025/arXiv 2507.04008 | **F1/Dice** / **clDice** / IoU | **91.83±0.43** / **91.74±0.42** / 85.83±0.63 | 粗调研值核实 ✓，**含 clDice** |

**FIVES Dice 天花板 ≈ 0.918**（PASC-Net）。**FIVES split 大坑**：benchmarking 论文 (arXiv 2406.14994) 的 FR-UNet 90.37 与 PASC-Net 91.83 用不同 split，不可直接比。

---

## 2. 关键观察（战略）

1. **裸 Dice 全面饱和**（DRIVE ~0.84 / CHASE ~0.85 / STARE ~0.85 / FIVES ~0.92）——印证 STORY 基调：裸 Dice 持平不输即可，胜负压拓扑/续连轴。
2. **clDice/拓扑指标报告者极少 = 我们的空白窗口**。可核到报 clDice 的仅：HREFNet（DRIVE/CHASE/STARE）、PASC-Net（FIVES）、FA-Net（STARE）、TFFM（仅 zero-shot）。主流 2025 强作（FSG-Net/HM-Mamba/EFDG-UNet）**全不报 clDice**。Betti/junction-F1 几乎无人报（TFFM 是少数例外）。→ 续连/re-ID 轴更是无人占据。
3. **天花板参照锁定**：DRIVE 0.8327（HM-Mamba，Mamba 家族可比对手）/ FIVES 0.9183+0.9174 clDice（PASC-Net）作主参照。
4. **指标类型陷阱**：老论文多报 pixel Accuracy(~0.96)/AUC(~0.98)/Se/Sp，**别误当 Dice**。RV-GAN 86.90/89.57 几乎确定是指标混用，全文付费墙未核，**禁止引用**。

---

## 3. 盲区 / TODO

- ⛔ **RV-GAN F1/Dice 真值未核**（Springer 付费墙）——86.90/89.57 来源可疑，禁用，需人工核 MICCAI 2021 全文 Table。
- **MDFI-Net STARE 0.8581 / DRIVE 0.8379 偏高**——需核 split 是否官方。
- **FIVES split 标准化**：PASC-Net vs benchmarking 论文 split 不同，建可比表需人工对齐。
- **TA-Mamba DRIVE/CHASE/STARE 具体 Dice 未获**（Springer 付费墙，仅 Multimedia Systems 2025 DOI 10.1007/s00530-025-01671-2）。
- **MM-UNet 绝对 Dice 未获**（只有 +1.64%/+1.25% 相对提升）。
- **VFGS-Net 完整表已核**（arXiv 2602.10978v1）：DRIVE 0.8323 / CHASE 0.8143 / STARE 0.8321 / HRF 0.8560。
