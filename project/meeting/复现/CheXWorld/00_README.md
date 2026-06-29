# CheXWorld 独立复现 pilot — 任务入口

**一句话**：复现 CVPR 2025 论文 CheXWorld（医学影像世界模型）官方代码，轻量 pilot 跑通管道 + 用官方公开权重在 1 个下游 benchmark 拿可对照论文的真数字。独立学习任务，**不动封存的 NCA-JEPA**。

> 任务类型 = 复现学习（非投稿项目），不登记 registry。状态真源 = 本目录 `04_LOG.md`。

## 论文身份
- **CheXWorld: Exploring Image World Modeling for Radiograph Representation Learning**
- Yang Yue 等，清华 LeapLab，CVPR 2025，arXiv 2504.13820
- 官方 repo：`github.com/LeapLabTHU/CheXWorld`（**无 LICENSE = All rights reserved，仅自用复现，勿对外再分发权重/代码**）

## 核心方法（一段）
自监督医学影像世界模型，JEPA 框架（context/target encoder + EMA + predictor，latent 空间预测）。三个世界建模任务统一在一次 forward：
1. **local** 局部解剖结构（mask-重建，预测被遮区域特征）
2. **global** 全局解剖布局（给相对位移 Δ 预测异位 crop 特征）
3. **domain** 域变化（给增强参数 a 预测逆变换后特征，等变表示）
ViT-B，~0.5M frontal CXR（MIMIC+NIH+CheXpert），300ep。8 下游 benchmark 迁移超 SSL baseline + 医学基础模型。

## 已有分析资产（复用，不重做）
- 全文已扒：`../../Med-NCA/chexworld.txt`（含公式/8 benchmark 表/消融表）
- 官方超参溯源：`../../Med-NCA/NCA-JEPA/configs/PROVENANCE.md`（~90% 真官方值）
- 方法关系：封存项目 NCA-JEPA 复用 CheXWorld 框架只换 predictor（ViT→NCA），见 `../../Med-NCA/NCA-JEPA/01_创新计划.md`

## 读档顺序
1. `00_README.md`（本文）
2. `04_LOG.md` 最新 entry（状态/进度）
3. `REPORT.md`（复现结论，跑完后生成）
4. 论文 PDF：本目录 `Yue 等 - CheXWorld ....pdf` / 全文 txt 见上

## 执行计划（plan 真源）
`C:\Users\yj200\.claude\plans\d-yj-agent-project-meeting-yue-chexworl-snappy-seahorse.md`

Phase 0 建档 → Phase 1 clone+版本矩阵 → Phase 2 eval-only 对照(主信号) → Phase 3 预训练管道烟测 → Phase 4 报告收口。

## 关键事实速查（researcher 核，带源见 plan）
| 项 | 值 |
|---|---|
| 预训练入口 | `train_jepa.py`（基于 MAE+I-JEPA）|
| 下游分类/分割 | `train_finetune.py` / `train_finetune_seg.py`（默认用 target/EMA encoder）|
| 三任务开关 | 无独立 flag，靠 `--ssl_type iwm_dual_easy` + mask/scale 参数隐式组合 |
| 公开权重 | Google Drive `1XdmQaNo0U2ilDEGYnLRz39Eywkom13BP`（pretrained + 下游 splits）|
| 依赖坑 | requirements.txt 全部无版本 pin → 先核版本矩阵 |
| 现成数据 | NIH ChestX-ray14 224 版（HPC + 本地 Kaggle），见 `.portfolio/datasets.json` |

## 算力 / 数据
- HPC `gpu4090`（account `shuihuawang`，qos `4gpus`，单卡默认），经 `tools/gpu_slot.py` 申请卡槽
- 本地 RTX4070 8GB 仅 <5min 烟测
- 数据真源：`D:/YJ-Agent/.portfolio/datasets.json`

## 拍板点
- 下新数据集 / HPC 上传新代码数据 = 对外传输，先报
- 训练（eval-only finetune + 预训练 smoke）= 自主，经 gpu_slot 起
