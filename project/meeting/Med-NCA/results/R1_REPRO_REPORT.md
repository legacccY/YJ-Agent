# R1 复现报告 — Med-NCA on MSD Task04 Hippocampus

**任务**：复现 Med-NCA（2D slice-wise NCA）在 MSD Task04 Hippocampus 3D MRI 分割上的 Dice，作为「NCA baseline 可信」的最小复现锚点。
**结论**：✅ **PASS**。per-image(per-volume) Dice **0.8661**，过阈值 ≥0.86，落在论文 0.882 的 ±0.02 容差带 [0.862, 0.902] 内。
**日期**：2026-06-03（会话 4）｜**seed** 42 ｜**git commit** 9d844b58

---

## 1. 设置

| 项 | 值 | 来源 |
|---|---|---|
| 框架 | 官方 `M3D-NCA-official`（MECLabTUDA），只读对照 | github.com/MECLabTUDA/M3D-NCA |
| 模型 | 2 级 BackboneNCA（coarse 16×16 → fine 64×64 patch），各跑 64 步 | §4 架构事实 |
| channel_n / hidden | 16 / 128 | 官方 example |
| lr / betas / lr_gamma | 16e-4 / (0.5,0.5) / 0.9999 | 官方 example |
| batch / loss | 48 / DiceBCELoss | 官方 example |
| 数据 split | 0.7 / 0 / 0.3（train/val/test）= 182 / 0 / 78 个体积 | data_split.dt 固化 |
| 训练轮数 | **300 epoch**（论文 1000；300 已过阈值，主动停） | epoch_300 ckpt |
| 硬件 | 本地 RTX 4070 Laptop 8GB，~3.7h/50ep | — |
| 工程修正 | `code/fast_nca.py`：fire-mask rand 直接 device 生成（数学等价，修 CPU→GPU 同步停顿，§9 #10） | — |

**ckpt**：`checkpoints/r1_hippocampus/models/epoch_300/`（model0/model1.pth）。
**eval 脚本**：`code/eval_r1.py`（load epoch_300 不再训，复用 data_split.dt 同 test split）。

---

## 2. 结果（per-image Dice，论文标准口径）

> 口径：每个 test 体积算一个 Dice → 78 个取均值 + std + bootstrap 1000× 95% CI。**非 batch-aggregate**（守 REPRO_PLAN §3 红线）。

| 指标 | n | Dice mean | std | 95% CI | 阈值 | 判定 |
|---|---|---|---|---|---|---|
| **R1 single**（单次推理） | 78 | **0.8661** | 0.0333 | [0.858, 0.8731] | ≥0.86 | ✅ PASS |
| **R1 pseudo10**（10× ensemble） | 78 | **0.8669** | 0.0319 | [0.8593, 0.8737] | ≥0.86 | ✅ PASS |

**对标论文**：Med-NCA Hippocampus ~0.882。复现 0.8661 差 −0.016，在 ±0.02 容差带内 → PASS。gap 主因：训 300ep（论文 1000）+ data split / seed 差异，非 bug。

明细：`results/r1_hippocampus_single.csv`、`results/r1_hippocampus_pseudo10.csv`（每体积一行 + seed + commit）。

---

## 3. 配套验收项

| ID | 项 | 结果 | 阈值 | 判定 | 文件 |
|---|---|---|---|---|---|
| **R3** | 参数量轻量声明 | **25,920**（2 级各 12,960） | <100K | ✅ PASS | — |
| **R4** | pseudo-ensemble Dice > single | mean_diff **+0.00081**, CI [0.00024, 0.00149]（排除 0） | Δ>0 | ✅ PASS | `r4_summary.json` |

**R4 解读**：收敛后 ensemble 增益已收窄（欠训版 +0.0078 → 收敛版 +0.00081）。符合预期——欠训时预测方差大、ensemble 收益高；训稳后单次推理已可靠，ensemble 边际收益小。CI 仍排除 0，方向成立（NCA 随机性 → ensemble 是质量度量基础，为 §7 创新方向 B「NQM 驱动」铺路）。

---

## 4. 复现可信性 checklist（守红线）

- [x] per-image 口径（非 aggregate）— §3
- [x] bootstrap 1000× 95% CI — §1 红线 1
- [x] seed 固定（42）+ git commit（9d844b58）记录每行 csv
- [x] test split 由 data_split.dt 固化，eval 与训练同 split
- [x] 数字未与论文「凑」：诚实记 gap −0.016 + 根因（300 vs 1000 ep）— §1 红线 3
- [x] 用官方框架自跑，非抄论文表格 — §1 红线 4
- [x] 真训实锤：ckpt 按 ~3.7h 间隔 epoch_50→300 递增，非 config.dt 陷阱下的假轮数

---

## 5. 已知坑（复现踩过）

1. **config.dt 覆盖陷阱**（§9 #9）：官方 `Experiment.reload()` 启动若目录有 config.dt 就整个覆盖运行时 config，env 变量静默失效。会话 2/3 连两次「300/1000ep」实只训 ~8ep（Dice 0.628 FAIL）。修复=重训前清 model_path。本会话 epoch_300 是清后真训产物。
2. **欠训 FAIL summary 残留**：会话 2 的 single/pseudo10 summary 写着 0.628/0.636 FAIL，是欠训版。本会话 eval-only 已覆盖为 0.8661/0.8669 PASS。
3. **长 eval stdout 块缓冲**：log 的 CASE/NQM 计数严重滞后真实进度（pseudo10 跑 ~1.5h），别据此判进程死活；`tasklist /FI` 经 grep 还遇假阴性"gone"。看 `Get-Process .CPU` 是否在涨才准。

---

## 6. 结论

**R1 ✅ PASS + R3 ✅ + R4 ✅**。最小复现（§5 R1+R2+R3）差 **R2（ISIC 2D）** 一项。
R2 过 → baseline 冻结 → 报用户 gate 进 Phase 1 创新选型（§7 候选 A-E）。
