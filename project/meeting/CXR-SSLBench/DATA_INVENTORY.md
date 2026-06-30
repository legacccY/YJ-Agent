# CXR-SSLBench — DATA_INVENTORY

> 真源 = `.portfolio/datasets.json`。本文只列本项目用到的细目 + 用途，路径以真源为准，不硬编码、不软链。

## 数据集（3 域，跨域矩阵）

| key（datasets.json） | 角色 | 路径真源 | 状态 |
|---|---|---|---|
| `nih_cxr14` | 主语料（自训 + 主评估，in-domain） | HPC `/gpfs/work/bio/jiayu2403/nca-jepa/data/nih_cxr14/`（112120 png）+ splits（1/10/100% + test=25596，患者 0 重叠） | ✅ HPC 验通；本地已删（清盘） |
| `vindrcxr_domainB` | 跨域评估 B（NIH→VinDr） | local `D:/YJ-Agent/data/external/vindr_cxr`（512² PNG） | ⚠️ 分类标签可用性派 researcher 核（NCA-JEPA 用它是 label-free） |
| `chexpert` | 跨域评估 C（bonus） | local `project/data/external/chexpert/`（partial 762MB/11.5GB） | ⚠️ 待续下；CheXpert 当 bonus，NIH→VinDr 单跨域可立住 C4 |

## 权重资产（5 范式）

| 范式 | backbone | 来源 | 状态 |
|---|---|---|---|
| World-model SSL | CheXWorld ViT-B/16@224 | `project/meeting/复现/CheXWorld/repo/` + `assets/chexworld_pretrained.tar` + HPC `/gpfs/.../chexworld/` | ✅ 权重+repo+官方 recipe(FINETUNE.md) |
| MAE | Medical-MAE ViT-B | Google Drive 1.34G（pilot 已用 medical_mae） | ✅ HPC 下到（pilot 入表） |
| DINO | RAD-DINO ViT-B | HF microsoft/rad-dino | ✅ HPC 下到（pilot 入表 rad_dino） |
| JEPA | RadJEPA / I-JEPA ViT-B | HF（pilot 存疑试） | ⚠️ 待确认 loader |
| 监督参考 | imagenet ViT-B/16 timm | timm | ✅ pilot 入表 imagenet_sup_vitb |
| MoCo-v3 | ViT-B | 官方配方派 researcher 查（R4） | TODO 全盘需补第 5 范式 |

> 受控横评铁律：5 范式**同数据/同 backbone(ViT-B)/同预算重训**才算受控（plan 红队第 3 发）。pilot 用现成权重看苗头，全盘 Phase 1 须自训。

## 复用管道
- NCA-JEPA：CheXWorld JEPA 框架 + NIH 管道 + `build_splits.py`（`project/meeting/Med-NCA/NCA-JEPA/`）。
- pilot harness：`code/`（paths/backbones/datasets/extract_features/probes/metrics_auc/run_pilot/eval_collect），HPC `/gpfs/.../cxr-sslbench/code/`。
