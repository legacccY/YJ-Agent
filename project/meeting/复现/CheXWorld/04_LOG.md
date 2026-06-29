# CheXWorld 复现 pilot — LOG

## 2026-06-28 — Phase 0 建档 + 核查结论

### 核查：CheXWorld 是否已在组合台做过
- **分析层 = 已做且很深**：
  - 全文已扒 `../../Med-NCA/chexworld.txt`
  - 封存项目 NCA-JEPA 定位它为「医学世界模型 SOTA baseline」
  - 官方超参溯源 `../../Med-NCA/NCA-JEPA/configs/PROVENANCE.md`（~90% 真官方值）
  - 方法关系吃透：NCA-JEPA = 复用 CheXWorld 框架只换 predictor（ViT→NCA）
- **复现层 = 零**：从没克隆/训练官方 CheXWorld repo。NCA-JEPA 地基是 `facebookresearch/ijepa`，只训到 A0=ViT baseline，且已 shelved（P8）。
- **结论**：用户要复现的部分确实空白。

### 用户拍板
- 复现深度 = **轻量 pilot 先跑通**（非全量 300ep）
- 项目归属 = **独立复现任务（新建）**，放 `project/meeting/复现/CheXWorld/`，不动封存 NCA-JEPA

### researcher 摸清官方 repo（带源见 plan 文件）
- 入口 `train_jepa.py`（预训练）/ `train_finetune.py`（分类）/ `train_finetune_seg.py`（分割）
- 预训练 `--ssl_type iwm_dual_easy --dataset mimic_nih_chex --model vit_base` 8卡 batch128×accum2 300ep
- 三任务无独立 flag，靠 ssl_type + mask/scale 参数隐式组合（⚠️需读源码确认映射）
- **公开权重** Google Drive `1XdmQaNo0U2ilDEGYnLRz39Eywkom13BP` → eval-only 对照地基
- requirements.txt 无版本 pin（最大复现坑）
- 无 LICENSE = 仅自用

### Phase 0 完成
- 建 `复现/CheXWorld/` + `00_README.md` + `04_LOG.md`（本文）
- PDF 移入本目录

---

## 2026-06-28 — Phase 1 完成 + Phase 2 数据就绪 + 权重 blocker

### Phase 1 clone + 版本矩阵 = PASS
- clone `LeapLabTHU/CheXWorld` → `repo/`（HEAD 0901027，git 忽略）。
- **版本矩阵实测**：本地 py3.12.7 / torch 2.7.0+cu126 / **timm 1.0.22**（`timm.models.layers` 弃用别名仍在，repo 新旧命名空间都通）/ gdown 6.0 / monai/albumentations/pydicom/cv2/sklearn 全有。`timm.models.vision_transformer.{VisionTransformer,checkpoint_filter_fn}` 在 1.0.22 仍可 import。**结论：本地环境兼容，无需建独立 env**。
- **repo patch（偏离清单，repo 已 git 忽略）**：
  1. `models/__init__.py:12` 注释掉 `from .unet_adapter_conv import ...` — repo 漏带 `models.dinov2` 子模块，该 import 崩；仅 dinov2 分割 adapter 用，分类 finetune 不需要。
  2. `data_utils/data_path.py` 重写 `get_dataset_path`：按名映射，`'NIH'` → `D:\chexworld_repro_data`（含 junction `NIH_512`）；未配置名返回 None（保持原 stub 行为，因模块级常量 import 时会调用）。
- import + argparse 裸基准 PASS。
- 三任务↔参数映射已摸清（Explore，见 plan）：`--ssl_type iwm_dual_easy`→`IWM_Dual`+自动 `extra=True`；local=mask、global=`extra_global_scale`、domain=`jepa_vit_add.py` policy net 注入增强参数 a。

### Phase 2 数据准备 = 就绪
- NIH 官方下游 split 已下（Google Drive annotations 子文件夹）：train 75312 / val 11212 / test 25596，copy 到 `repo/annotations/nih/`。
- NIH 224² 图复用共享真源（NCA-JEPA/data/nih_cxr14，112120 png）→ junction `D:\chexworld_repro_data\NIH_512`。
- **NIH 下游 dataset 加载验通**：val 11212 / train(1%)=753 / 224 RGB / 14 类多标签。

### 🛑 BLOCKER：官方预训练权重下载被 Google Drive 配额封顶
- 权重文件 = `chexworld_pretrained.tar`（Drive id `1QKUhIWIicl65UXJIGSh7_rYaq5i08iVn`，单文件）。
- gdown 连试 4 次全返回「Cannot retrieve the public link... or have had many accesses」= 该公开文件触发 Google 每日下载配额上限。直接下载工具（gdown/wget/浏览器直链）均无法绕过，**通常需 ~24h 配额重置，或「复制到自己 Google Drive 再下」（需登录账号）**。
- 无 HuggingFace 镜像（WebSearch 确认只 GitHub+Drive）。
- 影响：Phase 2「官方权重 finetune 对照论文 Table 1」= pilot 主信号被卡。
- 缓解：先跑 **scratch（随机初始化）finetune 烟测**证明 finetune 流水线端到端通（不需权重），主信号待权重到手补。

### 下一步
等 scratch 烟测结果 → 报用户权重 blocker + 选项（等配额/复制到用户 Drive/暂收 pipeline-proof 版）。

---

## 2026-06-28 — 两条流水线烟测全 PASS（pipeline-proof）

用户拍板权重获取 = **手动下载丢进 assets/**（Drive 配额墙，gdown 绕不过）。下载期间并行跑两条管道烟测证明流水线，均本地 RTX4070 单卡 + gloo + 直跑 python（torchrun c10d 在 Windows rendezvous 失败，改 env 变量直启）：

### finetune 流水线烟测 = PASS
- scratch（随机初始化，无 --pretrained）NIH 1% bs16 1ep。
- 结果 `[VAL] mAUC=52.14`（≈随机 50，符合：随机权重+1%数据+1ep）→ 管道全通：dataloader→ViT-B→BCE→训练→AUROC(roc_auc_score)→落盘 outputs_0.log。

### 预训练流水线烟测（Phase 3）= PASS
- `train_jepa.py --ssl_type iwm_dual_easy --dataset nih` ViT-B bs4 1ep（NIH-only 512 图子集）。
- repo patch：`nih.py` 预训练分支 `NIH_512_jpg`→`NIH_512`（用本地 224 png）；造 `D:\chexworld_repro_data\train_val_list.txt`（512 图）。
- 模型全装好：含 `policy_net` in_features=389=384+5 增强参数 → **domain 任务注入接通确认**。
- 训练步 `[Epoch0][19/128] Loss 0.34↓(avg0.57) Loss_Intra(local)+Loss_Extra(global/domain dual) 都降, Grad_Norm0.43, Pred_Var0.01(没塌缩), EMA0.996 ramp` → **三任务 SSL 可自训，无 OOM 无 collapse**。

### 结论（pipeline-proof 阶段）
官方代码两条核心流水线（自监督预训练 + 下游 finetune）在本地环境**完整跑通**，版本矩阵兼容，三任务机制接通。**唯缺**：官方权重 finetune 对照论文 Table 1 真数字（待权重手动下载到 assets/ 后跑 Phase 2 主信号）。

### 待办
- [x] 权重到 assets/（用户手动下载，700MB，model 含 encoder./target_encoder./predictor.）
- [x] Phase 2 本地 reduced finetune（NIH 10%/15ep，--use_target）→ **mAUC 爬升 ep3=66.97→ep6=77.28→ep12=80.32**（scratch 52 → 官方权重 80+，迁移有效，逼近论文 83.58）
- [ ] Phase 4 REPORT.md 填最终数

---

## 2026-06-28 — HPC 全量复现（用户放行）

用户问「为什么不去 HPC 训练」→ 经确认**明确放行全量 HPC 跑**（auto-mode classifier 正确拦下「疑问句≠consent」，补 AskUserQuestion 拿到显式同意）。

**目标**：HPC 全量 NIH finetune 复刻论文 Table-1 NIH=**83.58**（本地 8GB 只能 reduced；HPC 4090×24GB 跑官方 recipe 100%/50ep/bs256）。
**范围说明**：全量 0.5M 预训练（MIMIC+CheXpert+NIH）需巨量 DUA 数据超 pilot 范围；NIH 已在 HPC，故复刻 NIH finetune 这一 headline 数。

**HPC 环境核查**（paramiko 探针）：torch2.6.0+cu124 / timm1.0.15(namespaces OK) / monai/einops/opencv/pandas/sklearn 全有；**缺 albumentations+pydicom**（repo `rsna.py`/`xray_transform.py` 模块级 import 需要）→ 已 `pip install` 进 `yjcu124py310`（albumentations2.0.8/pydicom3.0.2）。NIH 图复用 `nca-jepa/data/nih_cxr14/images-224/images-224`（112120 png）。

**HPC 部署**（`/gpfs/work/bio/jiayu2403/chexworld/`）：
- 建 `{logs,runs,assets,repo,nih_root}` + symlink `nih_root/NIH_512`→nca-jepa NIH 图。
- data_path.py 加 HPC NIH root（本地+HPC 都 try-exists）。
- sbatch `run_ft_nih.sbatch`：account shuihuawang / gpu4090 / qos 4gpus / 1×rtx4090，官方 recipe（100%/50ep/bs256/lr1e-4/ld0.75/dp0.6/--use_target）。
- 上传 repo tar + 700MB 权重（sftp）。

**repo patch 追加（HPC 兼容）**：data_path.py NIH root 列表化（本地 D:\chexworld_repro_data + HPC /gpfs/.../chexworld/nih_root）。

### 进行中（→ 见下方 06-29 收口）
上传 repo+权重 → 经 gpu_slot request hpc 1 → sbatch → 监控 50ep → 填 REPORT Table-1 对照。

---

## 2026-06-29 — 收 pilot 收口（全量复刻未跑完，主动撤队）

### HPC 全量 job 状态核查（paramiko squeue/sacct）
- 首提 job **1500910 = CANCELLED**（sacct: 00:00:00 elapsed，被取消）。
- 重提 job **1500915 = PENDING (Priority)**，submit 06-28T16:09:58。
- gpu4090 严重拥堵（多 job 跑 3-6 天、QOSMaxGRESPerUser/QOSMaxJobs 卡满），scontrol 预估 **StartTime=2026-07-01T02:44（排队约 2 天）**。logs/runs 全空，从未开跑。
- REPORT/LOG 原写 job 1500910 已陈旧 → 已更正。

### 用户拍板「收 pilot，写 REPORT 收口」
- 复现已由本地 reduced 主信号成立（mAUC 81.07/77.33，scratch 52 → +29 强迁移，同量级 83.58）；全量精确复刻仅 bonus。
- 不值得占 4090 配额苦等 2 天 + 无人值守 → `scancel 1500915`（squeue 已清空）+ `gpu_slot release 049f52f5`（队列空无 NEXT）。
- 全量 sbatch 脚本 `repo/run_ft_nih.sbatch` 保留，哪天 4090 空闲可一键重提补 Table-1 精确数。

### 收口结论
- **pilot = ✅ 完成达标**：跑通官方两条流水线 + 三任务接通 + 官方权重 NIH 下游迁移真数字到手。
- REPORT.md 定稿（§0 填 81.07、§4.2b 标全量未跑完、§5 达标判定）。
- 任务结束。诚实边界：未做全量 0.5M/300ep 预训练、8 benchmark 全迁移、Table-1 精确数复刻。
