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
| MDFI-Net | 2024/arXiv 2410.15444 | F1/Dice | 0.8379 | split 核实=DRIVE 官方 20/20✓ |
| EFDG-UNet | 2025/PMC12852779 | F1/Dice / AUC | 0.8412 / 0.9886 | 主流簇最高 |
| **HM-Mamba** | 2025/Entropy DOI 10.3390/e27080862 | **F1/Dice** / AUC / IoU | **0.8327** / 0.9132 / 0.7164 | Mamba 家族最高（**主参照**）|
| **VFGS-Net** | 2026-02/arXiv 2602.10978 | **Dice** | **0.8323** | 核实 ✓ |
| HREFNet | 2025/arXiv 2504.13553 | F1/Dice / **clDice** / AUC | 0.8214 / **0.8240** / 0.9856 | 罕见报 clDice |
| ⚠️ MM-UNet | 2025/arXiv 2511.02193 | F1/Dice (Se) | 0.8959 (0.8933) | **高簇·协议不可比**（Table I，绝对值已核）|
| ⚠️ RV-GAN | MICCAI 2021/arXiv 2101.00535 | Dice / AUC | 0.8690 / 0.9887 | **高簇·协议不可比**（Dice 来自 benchmarking 2406.14994 Table 2 Dice 列，AUC 另列；原文 headline 只报 AUC）|

**⚠️ DRIVE 报告值分两簇（2026-06-20 攻坚坐实，协议不可比）**：
- **主流一致簇 ≈ 0.83–0.84**：FSG-Net 0.8323 / HM-Mamba 0.8327 / VFGS-Net 0.8323 / FR-UNet 0.8316 / EFDG-UNet 0.8412。**天花板参照只用此簇。**
- **高簇 ≈ 0.87–0.90**：RV-GAN 0.8690 / MM-UNet 0.8959。远超主流簇 ≈ +0.04–0.06，几乎确定是**评估协议差异**（FOV mask / 测试像素集 / split 口径不同）。**不可与主流簇同表比、不当天花板**；引用须标"协议不同"。RV-GAN 此前标"禁用"修正为：指标类型是 Dice（非混用），但属高簇异常，按协议不可比处理。

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
| MDFI-Net | 2024 | F1/Dice | 0.8581 | split 核实=STARE leave-one-out（LOO 方差大，谨慎引）|
| HM-Mamba | 2025 | F1/Dice | 0.8239 |
| HREFNet | 2025 | F1/Dice / clDice | 0.7629 / 0.8030 | STARE 偏低，疑 split 差异 |
| FA-Net (Universal) | 2025/arXiv 2502.06987 | Dice / **clDice** | 0.8357 / **0.8763** | 多模态 |
| ⚠️ MM-UNet | 2025/arXiv 2511.02193 | F1/Dice | 0.9177 | **高簇·协议不可比**（Table I）|

**STARE Dice 天花板（主流簇）≈ 0.85**（FSG-Net 0.8510 可核 / MDFI-Net 0.8581 LOO 待谨慎）。MM-UNet 0.9177 属高簇协议不可比，不当天花板。**原 STORY 锁定表 STARE 83.21（VFGS-Net）偏低，已上修。**

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
4. **指标类型陷阱**：老论文多报 pixel Accuracy(~0.96)/AUC(~0.98)/Se/Sp，**别误当 Dice**。
5. **两簇协议不可比（DRIVE/STARE 双现）**：高簇（RV-GAN/MM-UNet ~0.87–0.92）vs 主流簇（~0.83–0.85）差 0.04–0.06，是评估协议差异非真实力差。**天花板一律用主流簇，高簇引用必标"协议不同"**。我们自己评估须钉死统一协议（FOV mask/像素集/split），跨论文直接比 Dice 是陷阱。

---

## 3. 盲区 / TODO（2026-06-20 攻坚后更新）

**已闭环**：
- ✅ **RV-GAN 裁决**：86.90/89.57 是 **Dice**（benchmarking 2406.14994 Table 2 Dice 列，AUC 另列 98.87/99.14；指标类型非混用）。**修正前判"禁用"** → 改判**高簇协议不可比**，可引但标"协议不同"、不当天花板。
- ✅ **MM-UNet 绝对值已获**：DRIVE 0.8959 / STARE 0.9177（arXiv 2511.02193 Table I）→ 高簇协议不可比。
- ✅ **MDFI-Net split 核实**：DRIVE 官方 20/20 + STARE leave-one-out（split 干净，非自切漏数据；STARE LOO 方差大谨慎引）。
- ✅ **Birmingham「Multi-scale Vision Mamba-UNet」定位**：Biomed Signal Process Control Vol 112, Art 108435, DOI 10.1016/j.bspc.2025.108435（**无 arXiv**），MVSS Block+DMFII，测 DRIVE/CHASE/STARE/HRF 四集。数字付费墙未获。

**仍未攻下（已穷尽 ResearchSquare/Springer/SemanticScholar/PMC 引用表）**：
- **TA-Mamba DRIVE/CHASE/STARE 绝对 Dice**（ResearchSquare rs-5164628 正文未渲染、Springer 付费墙）→ related work 走定性描述，不报数字不阻投稿。
- **Birmingham MVSS-UNet 具体 F1/AUC**（ScienceDirect 付费墙）→ 同上定性。
- **FIVES split 标准化**：PASC-Net vs benchmarking 论文 split 不同，建可比表需人工对齐。
- ⏳ 主线可试 **XJTLU 机构 Playwright** 下 TA-Mamba/Birmingham 原文（值不值由用户定）。
- **VFGS-Net 完整表已核**：DRIVE 0.8323 / CHASE 0.8143 / STARE 0.8321 / HRF 0.8560。
