# PHASE 3 — 主实验 + baseline 全谱同台

## ① 目标（锁定）
主集深做 + ≥12 baseline 同框架公平比，三轴指标全算，确立「拓扑/续连维度赢 SOTA、裸 Dice 持平不输」的胜负点。

## ② 入口依赖
P1 PASS（数据 + benchmark + 指标就位）+ P2 PASS（模型就位）。

## ③ 任务清单
1. **主集深做**：DRIVE / CHASE_DB1 / FIVES / STARE（固定 split 见 datasets.json）。
2. **baseline 全谱（≥12，同框架同 split）**：nnU-Net + SSM(HM-Mamba/Serp-Mamba/VM-UNet/U-Mamba/OCTAMamba/TopoMamba/VFGS-Net/MM-UNet/MambaVesselNet++) + 拓扑(DSCNet/cbDice/Skeleton Recall/PASC-Net/TFFM) + 经典(FR-UNet/SA-UNet/SCS-Net/CS-Net)。
3. **三轴指标**：重叠(Dice/IoU/AUC/Se/Sp) + 拓扑(clDice/Betti β₀β₁/Skeleton Recall) + 续连(ε_β0/SR/re-ID 率)。
4. **断点 benchmark 主结果**：在 P1 benchmark 上跑全 baseline，续连/re-ID 率对比（headline 铁证）。
5. seed ≥3，数字落 csv。

## ④ ACCEPTANCE 硬阈值（不妥协）
- [ ] ≥12 baseline 同台无漏比（关键竞品全在）
- [ ] 三轴指标全算，seed ≥3，std 报告
- [ ] **拓扑(clDice/Betti) 或续连(ε_β0/SR/re-ID) ≥1 轴显著赢 SOTA**
- [ ] **裸 Dice 持平不输**（不强求赢饱和指标，禁调参作弊凑赢）
- [ ] 数字 Bash/Grep 核 csv（禁 Read 看数据），入 tex 前过 verifier

## ⑤ 自由发挥区
训练超参搜索（复现纪律内）、seed 数加码、HPC 4 卡如何分配数据集并行、是否加更多 baseline。

## ⑥ 跑偏定义 / 红线
- ❌ baseline 漏比关键竞品 = reject
- ❌ baseline 不按官方复现（复现零偏离）
- ❌ Dice 调参作弊凑赢饱和指标
- ❌ 数字凭印象/Read 编造（红线，参 verify_paper_numbers 教训）

## ⑦ 退路 + 派谁 + 出口 gate
- 退路：若拓扑/续连也没赢 → stage-gate FAIL，写诚实回退报用户（不硬撑不 HARKing），可降 venue 或回 P2/P4 找因。
- 派谁：设计矩阵派 `planner` + `skeptic` 红队设计；baseline 复现派 `coder`；主线串行跑训练（gpu_slot 申请，4 卡并行）；跑后派 `analyst` 解读 + `verifier` 核数。
- **出口 gate**：≥1 轴赢 SOTA + Dice 不输 + 无漏比 → 进 P4。大阶段收口跑 `/stage-gate`。
