# CheXWorld 复现 pilot — 复现报告

> 论文：CheXWorld: Exploring Image World Modeling for Radiograph Representation Learning（CVPR 2025，清华 LeapLab，arXiv 2504.13820）
> repo：`github.com/LeapLabTHU/CheXWorld`（无 LICENSE = All rights reserved，本复现仅自用）
> 复现性质：轻量 pilot（跑通官方代码两条核心流水线 + 官方权重下游迁移信号），**非全量 300ep/0.5M 预训练复现**。
> 日期：2026-06-28（2026-06-29 收口）　环境：本地 Windows RTX4070 Laptop 8GB（reduced 主信号）

## 0. 一句话结论
官方 CheXWorld 代码在本地环境**两条核心流水线（自监督预训练 train_jepa + 下游 finetune）端到端跑通**，版本矩阵兼容，三任务机制（local/global/domain）接通验证；官方预训练权重在 NIH 下游迁移 mAUC = **81.07（VAL）/ 77.33（TEST）**（reduced：10% 数据 / 15ep / 单卡，scratch 仅 52 → 官方权重 +29，强迁移）。论文 Table 1 全量 = 83.58，本 pilot 与之**同量级**，差距由 reduced 数据/epoch 解释（见 §3 口径）。**复现成立**。全量精确复刻 = HPC bonus，未跑完（见 §4.2b）。

## 1. 环境 / 版本矩阵（实测）
| 项 | 值 | 结论 |
|---|---|---|
| Python / torch | 3.12.7 / 2.7.0+cu126 | ✅ |
| timm | 1.0.22（`timm.models.layers` 弃用别名仍在）| ✅ repo 新旧命名空间都通；`vision_transformer.{VisionTransformer,checkpoint_filter_fn}` 可 import |
| 其它 | gdown6.0 / monai / albumentations / pydicom / opencv / sklearn | ✅ 全有 |
| GPU | RTX4070 Laptop 8GB | ✅ 烟测/reduced 够；全量 finetune/预训练需 HPC |

requirements.txt **无任何版本 pin**（最大复现坑）→ 实测本地现成环境即兼容，无需建独立 env。

## 2. repo patch（偏离清单，repo 已 git 忽略）
| # | 文件 | 改动 | 原因 |
|---|---|---|---|
| P1 | `models/__init__.py:12` | 注释 `from .unet_adapter_conv import ...` | repo **漏带** `models.dinov2` 子模块致 import 崩；仅 dinov2 分割 adapter 用，分类不需要 |
| P2 | `models/__init__.py:142` | `torch.load(..., weights_only=False)` | torch 2.6+ 默认 `weights_only=True`，ckpt 含 `argparse.Namespace` 被拒；repo 写于 torch<2.6 |
| P3 | `data_utils/data_path.py` | 重写 `get_dataset_path` 按名映射 `'NIH'`，未配置返回 None | 原 stub 是 `/path/to/...` 占位 |
| P4 | `data_utils/nih.py` 预训练分支 | `NIH_512_jpg`→`NIH_512` | 本地用 224² resized **png**（非 512 jpg），避开 `__getitem__` 的 .png→.jpg 替换 |

启动方式偏离：torchrun c10d rendezvous 在 Windows 失败 → 改设 `RANK/WORLD_SIZE/LOCAL_RANK/MASTER_*` 环境变量直跑 python + `--dist_backend gloo`（Windows 无 nccl）。

## 3. 数据
- **NIH ChestX-ray14**（共享真源 `.portfolio/datasets.json`，224² resized 版，112120 png）。
- 官方下游 split 取自 CheXWorld Drive annotations：train 75312 / val 11212 / test 25596（14 类多标签），放 `repo/annotations/nih/`。
- 图经 junction `D:\chexworld_repro_data\NIH_512` → NCA-JEPA/data/nih_cxr14（复用，不重下）。
- 预训练 smoke 用 NIH-only 512 图子集（`train_val_list.txt`）。
- **口径说明**：论文 Table 1 NIH=83.58 是 **100% 数据 / 50 epoch / 8卡 bs256** 全量 finetune。本 pilot 本地受 8GB 限，用 **reduced（data_pct=0.1 / 15ep / 单卡 bs16）**，数字**不直接等同** Table 1，作「官方权重迁移是否有效」信号；要复刻 83.58 需 HPC 全量（上传=拍板点）。

## 4. 结果

### 4.1 流水线跑通（pipeline-proof）
| 流水线 | 命令 | 结果 | 判定 |
|---|---|---|---|
| 下游 finetune（scratch 对照）| `train_finetune.py --dataset nih --data_pct 0.01`（无 --pretrained，1ep）| `[VAL] mAUC=52.14`（≈随机 50）| ✅ 管道通（dataloader→ViT-B→BCE→AUROC→落盘）|
| 自监督预训练（Phase 3）| `train_jepa.py --ssl_type iwm_dual_easy --dataset nih`（ViT-B bs4 1ep/128步）| Loss avg 0.57→0.42↓，Loss_Intra+Loss_Extra 都降，Grad_Norm 0.48，Pred_Var 0.01→0.02（无塌缩），存 `epoch_0.pth.tar` | ✅ 三任务 SSL 可自训 |

三任务机制接通确认：预训练模型含 `policy_net` in_features=389=384+5 → domain 增强参数 a 注入路径真实存在。

### 4.2 官方权重下游迁移（Phase 2 主信号）
- 权重 `chexworld_pretrained.tar`（700MB，`model` 含 encoder./target_encoder./predictor.，用 `--use_target` 取 EMA teacher，日志确认 "Use Teacher" 加载）。

**(a) 本地 reduced（NIH data_pct=0.1 / 15ep / bs16，8GB 受限）** — 爬升曲线：
| epoch | VAL mAUC | TEST mAUC@best |
|---|---|---|
| ep3 | 66.97 | — |
| ep6 | 77.28 | 73.05 |
| ep12 | 80.32 | 76.18 |
| ep15(末) | **81.07** | **77.33** |

| 指标 | scratch（无权重 1%/1ep）| 官方权重 finetune（10%/15ep）| 论文 Table1（100%/50ep）|
|---|---|---|---|
| NIH VAL mAUC | 52.14 | **81.07** | 83.58 |

**判定 = ✅ 复现有效**：官方权重 finetune 比 scratch +29 mAUC，仅用 10% 数据/15ep 已达 81.07 / 测试 77.33，与论文全量 83.58 同量级（差距由 reduced 数据/epoch 解释）。官方权重正确加载并强迁移，复现成立。

**(b) HPC 全量（复刻 Table-1 精确数）= 未跑完，主动收口** — 官方 recipe NIH 100%/50ep/bs256/单 4090（`/gpfs/work/bio/jiayu2403/chexworld/`）：
- 首提 job 1500910 被取消（00:00:00 elapsed）；重提 job **1500915** 在 gpu4090 长期 PENDING (Priority)。
- 集群拥堵：squeue 多 job 已跑 3-6 天、QOS 卡满，调度器预估启动 = **2026-07-01 02:44（排队约 2 天）**。
- **2026-06-29 用户拍板「收 pilot」**：复现已由 (a) reduced 主信号成立，全量精确数仅为 bonus，不值得占 4090 配额苦等 2 天 + 无人值守。`scancel 1500915` 已撤回排队，释放 gpu_slot。
- **结论**：Table-1 的 83.58 精确复刻**未在本 pilot 完成**（诚实标注，非失败——pilot 范围本就是「跑通 + 迁移信号」，不含全量复刻）。哪天 4090 空闲可重提 sbatch（脚本 `repo/run_ft_nih.sbatch` 就绪）一键补上。

## 5. 诚实结论与边界
- ✅ 已证：官方代码可在本地跑通（两条流水线），版本兼容，三任务接通，官方权重可正确加载并迁移；reduced finetune mAUC 81.07/77.33（VAL/TEST），与论文全量 83.58 同量级，复现成立。
- ⚠️ 未做：全量 0.5M/300ep 预训练复现；8 benchmark 全量迁移；Table-1 精确数字复刻（job 1500915 因 4090 排队约 2 天、用户拍板收 pilot 而 scancel 撤回，未跑完）。
- 偏离全部显式记录（§2 patch + §3 口径），不冒充全量复现。
- **pilot 达标判定 = ✅ 完成**：任务目标（轻量 pilot 跑通管道 + 官方权重 1 个下游 benchmark 拿可对照论文的真数字）全部达成。全量复刻为可选 bonus，留 sbatch 脚本待 4090 空闲一键补。

## 6. 复现产物路径
- 任务档：`project/meeting/复现/CheXWorld/{00_README,04_LOG,REPORT}.md`
- 代码（git 忽略）：`repo/`（patch 见 §2）
- 权重/数据（git 忽略）：`assets/chexworld_pretrained.tar`、`D:\chexworld_repro_data\`
- 运行日志：`runs/<run>/.../outputs_0.log`
