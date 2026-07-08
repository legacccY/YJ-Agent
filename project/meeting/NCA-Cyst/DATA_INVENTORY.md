# NCA-Cyst — 数据细目

> 路径/下载源真源 = `.portfolio/datasets.json` key=`kits23`。本文只做本项目视角的细目，不硬编码别处引用的路径。

## KiTS23

- **全称**：2023 Kidney Tumor Segmentation Challenge
- **模态**：腹部 CT（皮髓质期增强），各向异性 `.nii.gz`
- **样本**：489 例（本地实测 case 目录数），每例 `imaging.nii.gz` + `segmentation.nii.gz` + `instances/`（多标注者亚区）
- **标注语义**：`0=背景  1=kidney  2=tumor  3=cyst`（**囊肿 = label 3**）
- **本地路径**：`data/kits23_repo/dataset/case_XXXXX/`（49GB，单例 imaging ~226MB）
- **HPC 路径**：`/gpfs/work/bio/jiayu2403/kits23/dataset/`（已验通，训练可直读）
- **来源**：官方 `github.com/neheller/kits23`（imaging 从 HF `neheller/KiTS-Challenge-Imaging` 逐例拉）
- **官方评估**：`kits23_compute_metrics` 可复用做 Dice 对齐

## 囊肿分布（本期自测，`06_experiments/kits23_cyst_dist.csv`，489 例全扫）

- **含囊肿(label==3) case 数：248 / 489**（**241 例完全无囊肿**，近五五开）
- **囊肿体素占比**：中位 **6.5e-05**（百万分之 65）、最大 1.2%、最小 4.2e-07 → 极端类不平衡（近随机机理根因）
- ⚠️ 中位囊肿仅 65/百万体素，下采样到 (320,320,24) 时可能被抹掉 → Phase 1b 评估口径见 `02_ACCEPTANCE`
- 复算：`code/kits23_cyst_dist.py`

## 数据适配（Phase 1a 前置）

官方 dataloader 要扁平目录（`images/case_XXXXX.nii.gz` + `labels/` 同名），KiTS23 是逐例子目录 → 写预处理脚本软链/派生成扁平结构（`code/`）。**不改原始数据**。

## split

官方 `[0.7, 0, 0.3]`（train/test=70/30，无 val）。M3D-NCA 与 UNet3D 用**同一 split**（同口径对照）。
