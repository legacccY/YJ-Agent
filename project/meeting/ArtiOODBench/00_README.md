# ArtiOODBench — 医学影像 OOD 检测基准的 artifact 污染诊断

> 入口读档：本文 → `01_STORY.md`（headline + lever）→ `02_ACCEPTANCE.md`（判据/kill criteria）→ `04_LOG.md` 最新 entry。
> 来源：ideation run-006（现象优先选题）G6 立项，2026-06-18 用户拍板。选题轨迹见 `project/ideation/runs/2026-06-18_run-006_phenom-medimg-failure/`（漏斗 138→C107，立项卡 `07_report/project_cards/C107.md`）。

## 一句话

现有医学影像 OOD detection benchmark 的方法排名，很大程度被 **scanner / 采集 artifact** 驱动而非病理语义——不看任何病理内容的 artifact-only 手工特征就能高 AUROC 区分 ID vs OOD。于是「方法 A 比方法 B 更会检测 OOD」可能只是「方法 A 更会读 scanner 指纹」。本项目系统量化此污染，提出去污染协议并重排现有 benchmark。

## 现象锚（G5 已去风险）

artifact-only 43 维特征（强度直方图 + GLCM Haralick + 边缘暗角比 + FFT 高低频能量比），**全部 resize 到 224² 消除分辨率直接泄漏后**，区分 NIH vs VinDr 两 CXR 数据集 **AUROC = 0.9213 ± 0.009**（n=1000）。best 单维：glcm 0.83 / hist 0.82。
→ csv：`results/c107_artifact_ood_killshot.csv`（从 ideation run-006 06_experiments 复制）。

## venue 双档

- 顶会档（冲）：**CVPR 2027**（analysis / benchmark-critique track）
- 退路档（保）：NeurIPS Datasets & Benchmarks / MICCAI / TMLR / ICBINB

## 状态

planning（G6 立项，schema 初建）。下一步：researcher 全面对齐先驱（OpenMIBOOD arXiv:2503.16247 / PMC10532230 3D / MedIAnomaly）锁差异化 → 设计去污染协议 + 选 ≥3 benchmark 对跑重排。

## 数据集（真源 `.portfolio/datasets.json`）

- `nih_cxr14`（ID，本地+HPC ready）/ `vindrcxr_domainB`（OOD，本地 ready）/ `medianomaly_bench`（7 集，BraTS2021 ready 余 todo）。
- 引用前查真源，别硬编码。
