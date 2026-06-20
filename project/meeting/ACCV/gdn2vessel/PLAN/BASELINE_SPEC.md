# gdn2vessel P3 — Baseline 全谱准备规格（BASELINE_SPEC）

**服务**：lever L3（baseline 全谱同台 ≥12）+ P3 主实验。
**产出方式**：3 researcher（官方源/超参/license）+ 1 planner（harness 设计）并行扇出综合，2026-06-20。
**最后更新**：2026-06-20
**真源约束**：超参一律官方源核实，**查不到标 TODO 绝不臆想**（红线②）；license 逐个确认能否学术发表（红线）；复现零偏离（红线④）。数据集路径引 `.portfolio/datasets.json`，split 引 `vessel_collection_kaggle.split`。

> ⚠️ 状态：本文件是**准备规格**，非已跑结果。真跑 baseline 训练 gate 在 P1+P2 真验 PASS 之后（现都「代码就位待 HPC 真验」）。所有性能数字为**官方论文报告值（sanity 参照）**，非我们复现值——我们的数字实验后由 verifier 核 csv 回填，此刻严禁当我们的结果引用。

---

## 0. Baseline roster（三档分级）

### 档 A — 同框架可跑（有官方代码 + license OK，进 P3 主表）

| # | 方法 | 类别 | repo | license | env | 任务域/备注 |
|---|---|---|---|---|---|---|
| A1 | **FR-UNet** | architecture | github.com/lseventeen/FR-UNet | MIT | main | 视网膜+冠脉；patch 48×48 |
| A2 | **CS-Net / CS2-Net** | architecture | github.com/iMED-Lab/CS-Net | MIT | main | 曲线结构通用；整图 512 RGB |
| A3 | **DSCNet** | architecture(+TCLoss) | github.com/YaoleiQi/DSCNet | MIT | main | DRIVE+Roads+CCTA；DSConv 需 CUDA 编译 |
| A4 | **nnU-Net** | architecture(公平主干) | github.com/MIC-DKFZ/nnUNet | Apache-2.0 | main | 自配置；retinal 数字需自跑 |
| A5 | **PASC-Net** | architecture(nnUNet-based) | github.com/IPMI-NWU/PASC-Net | Apache-2.0 | main | FIVES SOTA 91.83；⚠️arXiv preprint 状态 |
| A6 | **clDice** | **loss**（配统一 backbone） | github.com/jocpae/clDice | MIT | main | soft-clDice loss |
| A7 | **cbDice** | **loss**（配统一 backbone） | github.com/PengchengShi1220/cbDice | Apache-2.0 | main | MICCAI24；nnU-Net 集成 |
| A8 | **Skeleton Recall** | **loss**（配统一 backbone） | github.com/MIC-DKFZ/Skeleton-Recall | Apache-2.0 | main | ECCV24；architecture-agnostic |
| A9 | **VM-UNet** | architecture(SSM) | github.com/JCruan519/VM-UNet | Apache-2.0 | **mamba** | 通用 Mamba baseline；无 DRIVE 官方数字需自训 |
| A10 | **U-Mamba** | architecture(SSM) | github.com/bowang-lab/U-Mamba | Apache-2.0 | **mamba** | nnUNet+Mamba |
| A11 | **MambaVesselNet++** | architecture(SSM) | github.com/CC0117/MambaVesselNet | MIT | **mamba** | DRIVE Dice 0.711 = 通用模型真实代价非 bug（已核） |
| A12 | **creatis plug-and-play** | **postproc 续连** | github.com/creatis-myriad/plug-and-play-reco-regularization | ⚠️**无 LICENSE**（默认 All Rights Reserved，详 §7.4） | main | ★skeptic 🔴 必补：headline 唯一正面对照（learned post-processing 续连，挂统一 backbone 输出后），坐实 Claim 1「in-model vs post-processing」；含 2D STARE 训练流程可比 |

→ **档 A = 12 个**，达 ≥12。A9-A11 mamba 依赖（cu126 兼容已查可行，见 §3）。**A12 creatis 是 skeptic 红队补的续连赛道唯一直接对手（原 OCTAMamba 因 OCTA 域不对口移 P5 跨域，见 §5 风险裁决）。**留余量见档 B。

### 档 B — 候选/补位（凑余量，防档 A 挂几个）

| 方法 | 类别 | repo | license | 卡点 |
|---|---|---|---|---|
| **SA-UNet / SA-UNetv2** | architecture | github.com/clguo/SA-UNet | ⚠️**无 LICENSE**（v1 Keras/TF）；v2 arXiv2509.11774 PyTorch | license 需确认 / v1 非 PyTorch 需用 v2 |
| **MM-UNet** | architecture(SSM) | github.com/liujiawen-jpg/MM-UNet | MIT | 代码 "Coming soon" 待补全；input 608/704 显存贵 |
| **TFFM** | architecture module | tffm-module.github.io（GitHub URL 未确认） | CC BY 4.0（代码 license TODO） | repo 可达性未确认；WACV26 **Workshop** |

### 档 C — 仅引文献数字（无开源代码，related-work 引用，诚实标「非同框架复现」）

| 方法 | DRIVE Dice | CHASE Dice | STARE Dice | 来源 |
|---|---|---|---|---|
| **HM-Mamba** | 0.8327 | 0.8197 | 0.8239 | Entropy 2025 (PMC12385817)，无代码 |
| **VFGS-Net** | 83.23±0.33 | 81.43±0.35 | 83.21±0.36 | arXiv 2602.10978，无代码 |
| **SCS-Net** | 综合三集 Dice 88.72±0.67（口径待核） | — | Se 0.8207 | MedIA 2021，无官方代码 |
| **TopoMamba** | 无视网膜数字 | — | — | arXiv 2604.25545，无代码 → 仅 related-work 提 SSM，不进对比表 |

---

## 1. 官方超参表（档 A，复现用；TODO = 官方未明示，禁臆想）

| 方法 | optimizer | lr | schedule | epochs | batch | input | loss | 预处理 |
|---|---|---|---|---|---|---|---|---|
| FR-UNet | Adam wd1e-5 | 1e-4 | CosineAnneal T=40 | 40 | 512 | **patch 48×48 stride6** | BCELoss | **灰度**+minmax，无 CLAHE |
| CS-Net | Adam wd5e-4 | 1e-4 | PolyLR p=0.9 | 1000 | 8 | 整图 512（resize） | MSE+Dice | RGB，无 CLAHE |
| DSCNet | AdamW betas(.9,.95) | 1e-4 | ReduceLROnPlateau | 400(val@ep200) | 1 | ROI 224 | **`cross_loss`(BCE)**（官方 DRIVE 实测；TCLoss 未开源，见 §7.3） | ROI crop |
| nnU-Net | SGD m0.99 nesterov wd3e-5 | 1e-2 | PolyLR | 1000 | 自动 | 自动 patch | DC+CE 深监督 | 自动流水线 |
| PASC-Net | nnU-Net(自配置) | nnU-Net | nnU-Net | 300 | 自动(~2) | 512（FIVES 2048 裁） | 0.7·DC_CE+0.1·con1+0.1·con3+0.1·clDice | nnU-Net |
| clDice(loss) | 配 backbone | — | — | — | — | — | soft-clDice **α=0.5（repo default 确认）** | 随 backbone |
| cbDice(loss) | nnU-Net V2 SGD PolyLR 1e-2 | — | — | **20** | **2** | — | cbDice β=0.5（DRIVE 最佳 NSD） | 随 backbone |
| SkelRecall(loss) | nnU-Net SGD m0.99 PolyLR 1e-2 | — | — | — | 2 | 512×512 | weight_srec=1 | 随 backbone |
| VM-UNet | AdamW | 1e-3 | CosineAnneal min1e-5 | 300 | 32 | 256 | BceDice | flip+rotation |
| U-Mamba | 继承 nnU-Net | nnU-Net | nnU-Net | nnU-Net | 自动 | 自动 | nnU-Net | nnU-Net |
| MambaVesselNet++ | Adam | 1e-4 | Cosine min1e-7 | 200(2D) | 16 | TODO | Dice+CE | TODO |
| OCTAMamba | AdamW | 1e-4 | TODO | 400 | 2 | 224 | DiceLoss | TODO |

**档 B 补充超参**：SA-UNetv2 = Adam lr1e-3，0.5BCE+0.5MCC，DropBlock0.15/bs7，epochs150+early stop，整图 592（DRIVE）。MM-UNet = AdamW lr0.001 warmup2+cosine min1e-7，bs5(DRIVE)/2(STARE)，epochs500，input608/704，loss TODO。TFFM = AdamW lr1e-3 bs10 epochs500 input512，Tversky+soft-clDice λ0.5，backbone=UNet++ +EfficientNet-B0。

**TODO 槽位**（researcher 二轮已回填大部，下为状态）：
- ✅ DSCNet：AdamW betas(.9,.95)/lr1e-4/bs1/ROI224/400ep（直读 GitHub raw `S0_Main.py`+`S3_Train_Process.py`）。**⚠️ 旧表述「TCLoss=CE+Hausdorff 一体」更正（scout-baseline 复核 2026-06-20）**：官方 DRIVE 2D 训练代码 `S3_Train_Process.py` = `from S3_Loss import cross_loss; criterion=cross_loss()` **纯 BCE**，`S3_Loss.py` 全文只有 `crossentry`/`cross_loss`(BCE)/`Dropoutput_Layer`（另一论文变体），**无 TCLoss/无 Hausdorff/无 topology loss**（git tree recursive 全搜无对应文件）。TCLoss（persistent homology）只在论文 arXiv 2307.08388 正文描述，官方代码未开源 → **复现忠实走 BCE，不自补 TCLoss（复现零偏离）**。现 adapter `cross_loss(BCE)` 写法 = 对。
- ✅ PASC-Net：300ep（`nnUNetTrainer.py num_epochs=300`）+ loss=0.7·DC_CE+0.1·con1+0.1·con3+0.1·clDice（train_step 实测）。
- ✅ cbDice **权重已核源更正（scout-baseline 2026-06-20）**：官方 `nnUNetTrainer_CE_DC_CBDC.py::_build_loss()` = `lambda_ce = lambda_dice + lambda_cbdice` → **`2.0·CE + 1.0·Dice + 1.0·cbDice`**（CE 刻意加倍维持 CE 与拓扑 loss 总量对齐，`compound_cbdice_loss.py::forward()` 末行实证）。**现 adapter 写 `0.5·BCE + Dice + 0.5·cbDice` 与官方不符 → impl 阶段须改成 2:1:1（CE:Dice:cbDice），官方用 RobustCrossEntropyLoss 多类 CE，二值近似 BCE 但比例必须对齐**。训练设置 DRIVE 2D=nnU-Net V2 20ep/bs2/β0.5（arXiv2407.01517 Table 2）。
- ✅ clDice：α=0.5（repo `cldice.py` default）；loss 类配统一 backbone 无需官方 DRIVE 训练设置。
- ✅ MambaVesselNet++：Dice 0.711 = 通用多模态模型真实代价（非 bug、非 metric 异，标准 2GP/(G+P)），200ep/bs16/Adam+Cosine。**⚠️ 2D 复现裁决（scout-baseline 2026-06-20）**：repo `model_mvn/mvn.py` 全 Conv3d **无 2D path**，`train.py` patch_size=(64,64,64) 纯 3D 脑血管 CT；arXiv 2507.19931 §4.3 只写「2D epoch=200 bs=16」**无 input size/无 normalize/无 augment**，论文 §3.4 声称的 2D/3D adaptive 切换 repo 未实现 → **代码与论文 claim 不一致，复现零偏离下不自补 2D 实现，建议降档 C（不进 L3 同框架对比，仅引文献数字标 unavailable）或 issue 作者**。拍板点。
- ⬜ 剩余真 TODO：clDice 官方 DRIVE lr/optimizer（appendix E 403，repo 无训练脚本——loss 类用统一 backbone 不阻塞）；CS-Net RandEnhance factor 区间（源码 `random.uniform(-2,2)` 含负值，PIL ImageEnhance 语义需人工核原行）；DSCNet MONAI augment 各 transform 确切 prob 阈值（摘要版 0.3/0.5，需逐行核 `prob=`）；VM-UNet/MambaVesselNet++ DRIVE normalize（官方无 DRIVE 条目，自算训练集 mean/std 或 [0,1]，拍板）；U-Mamba `custom_transforms/` 目录内容（需 clone 确认是否覆盖 nnU-Net DA5 默认）。

---

## 2. 统一 Baseline Harness 设计（planner 产出，condensed）

### 2.1 核心张力 → 分层冻结

P3 同时要「同框架公平比」（逼统一）+「复现零偏离」（逼尊重官方差异）。解法 = **分层冻结，只在评估契约层强制统一**：
> **凡是「量尺」就统一（评估拿什么数据/什么指标/在哪算），凡是「炼丹配方」就尊重官方（怎么把模型练到官方水平）。**

### 2.2 三层结构（model-agnostic）

```
Layer A DATA  : BaseVesselDataset 统一 split/FOV/GT + 各 adapter 声明官方 preprocess
Layer B TRAIN : train_pilot.py → train_harness.py（循环不变，model/loss/optim 从 adapter 取）
Layer C EVAL  : evaluate.py 统一三轴评估（best.pth → 全图推理 → 三轴 → 统一 csv），断点 benchmark 同台
```

目录建议：`src/baselines/{registry.py, base_adapter.py, adapters/*.py, losses/*.py, third_party/官方repo vendoring}` + `src/datasets/base_dataset.py` + `src/train_harness.py` + `src/evaluate.py` + `src/configs/{_base_eval.yaml, baselines/*.yaml}`。

**关键**：Ours（UNetGDN2）也包成 adapter 走同一台子，自证不给自己开后门（审稿人盯的公平点）。

### 2.3 公平性矩阵（🔒统一 vs 🟢尊重官方）

| 🔒 统一（量尺） | 🟢 尊重官方（配方） |
|---|---|
| 数据 split（datasets.json 固定） | 预处理（CLAHE/通道/标准化） |
| 测试集 held-out 零拼训练（红线1） | 训练 input（patch vs 整图） |
| 三轴指标实现（同一 evaluate.py） | 官方 epochs/lr/optimizer/scheduler |
| **评估全图推理**（patch 模型滑窗拼回全图再算指标） | 官方数据增强 |
| FOV-masked + 阈值 0.5 | 官方 loss（architecture 类） |
| seed [42,1,2]（≥3） | — |
| 断点 benchmark 协议（同一组合成断点） | — |

**评估全图 vs 训练 patch 关键澄清**：FR-UNet 训练用 64patch（官方）= 尊重；评估时滑窗推理拼回 584×565 全图再算 Dice/clDice/ε_β0 = 与整图模型同一张全图可比。错法 = patch 上算 FR-UNet Dice、全图算 Ours Dice 并排（分母/拓扑不可比）。`evaluate.py` 强制所有 adapter 输出先 → 全图 logits。

### 2.4 ⚠️ 反向公平点（loss 类，skeptic 红队 + Opus 复核）

architecture 类**尊重整套官方**（变量=整个模型）；**loss 类反过来钉死统一超参**（变量=单个 loss，backbone+训练必须钉死才能隔离 loss 增益）。
- **loss 类统一 backbone = `src/models/unet.py`（base_ch32 标准 U-Net）** = Ours 的 CNN 主干同款 → 拓扑 loss 增益可干净归因到「loss」而非「主干差异」。
- 边界在 loss 类上是反的 = 设计最微妙处，**已交 skeptic 红队**（见 §5）。

### 2.5 三轴指标接入（复用现成，不重写）

`src/benchmark/metrics.py`（续连 ε_β0/SR/re-ID）+ `src/benchmark/tools_topology.py`（拓扑 clDice/Betti/SkelRecall）已现成，evaluate.py 直接调。
- 统一 csv schema：`dataset,baseline,kind,seed,split, dice,iou,auc,se,sp, cldice,betti_b0_err,betti_b1_err,skeleton_recall,topo_source, epsilon_beta0,success_rate,reid_rate,n_gaps, ckpt_path,eval_input_mode,threshold,git_commit`。
- `topo_source` 列记官方库 or fallback（禁混用，verifier 一眼查全列同值）；`git_commit` 列让数字可追溯。
- **口径 TODO**：AUC 在 FOV 内 vs 全图（核主流 vessel paper 口径，避免与 SOTA 表口径不一致）；re-ID 率只在断点 benchmark 集算（原图无 gap）。

---

## 3. Mamba 硬依赖隔离（A9-A12 + 档 B MM-UNet）

`mamba-ssm`/`causal-conv1d` 有 CUDA kernel 编译依赖，与主 `gdn2venv`（torch2.9+cu126+triton+FLA）可能冲突。
- **方案 = 独立 venv `mamba_venv`**，adapter `env_tag:mamba` 标记 → HPC 提交脚本选 venv。
- ✅ **cu126 可行性已查（researcher 二轮）**：mamba-ssm 官方 PyPI wheel 仅 cu11x（无 cu12x），但 **HuggingFace `kernels-community/mamba-ssm` 有 `torch29-cxx11-cu126` 预编译 wheel 命中 HPC gdn2venv（torch2.9+cu126）**。⚠️ **sm_89(RTX4090) 官方默认编译目标不含**（只 sm_75/80/87/90/100/120）→ 需 `TORCH_CUDA_ARCH_LIST="8.9" pip install mamba-ssm --no-build-isolation` 源码 build（torch 先装好），或核 HF wheel 是否内含 sm_89 kernel（需解包 .whl 查）。建 `mamba_venv` 后先 `python -c "from mamba_ssm import Mamba"` 烟测。仍装不上 → 降档 C 诚实引数字。
- **退路（诚实纪律）**：装不上的 → 用官方纯 PyTorch fallback（如有）→ 仍不行 → **降到档 C 引文献数字 + 诚实标「非同框架复现」**，绝不强凑。故档 A 留余量（档 B 补位），「≥12 同框架」在能装上的集合里达成。
- **Serp-Mamba 不进档 A**：UWF-SLO 域专用 + 定制 wheel 坑最深 + 无 DRIVE 官方数字 → 仅 related-work 引用。

---

## 4. HPC 算力编排（拍板点）

- **裸 job 数** = 14 候选 × 4 主集（DRIVE/CHASE/FIVES/STARE）× 3 seed = **168 run**（上限，mamba 挂几个会减）。
- **GPU·h 粗估** = 单 run 均值 ~2 GPU·h（FIVES 600 训图拉高）→ **~340 GPU·h 量级**（⚠️数量级估计，待 P0 pilot 单 run 实测校准）。4 卡 ≈ 85 卡·h 墙钟，qos 7 天可分批。
- **4 卡编排** = 按数据集分卡（天然独立无冲突）：卡0=DRIVE 队列、卡1=CHASE、卡2=STARE、卡3=FIVES（大集独占跑久）；每卡内串行 baseline×seed 队列，release 自动取下一个；mamba job 各卡切 `mamba_venv`。
- **🛑 分批拍板（大笔算力 = 拍板点）**：batch-1 = 只 DRIVE × 全 baseline × seed42（~14 run，验流程 + 校准 GPU·h）→ analyst/verifier 看无 bug + 校准 → 再拍板铺 batch-2 全量。**绝不一次性裸铺 168 run。**

---

## 5. 依赖顺序 + 下一步派单

### 依赖 DAG
```
P1 PASS(断点协议冻结) ─┐
P2 PASS(Ours+re-ID+Frangi) ─┤→ harness 骨架(可并行先做) → coder 各 adapter → skeptic 红队 → 🛑batch-1 校准拍板 → gpu_slot 跑 → analyst+verifier
researcher 回填官方超参 ─┘
```
**可并行**：harness 骨架（base_adapter/registry/evaluate.py，不依赖具体超参值）与 researcher 回填 §1 TODO 并行。
**串行**：各 adapter 官方 train 配置依赖超参回填；全量训练依赖 P1 协议冻结 + batch-1 校准拍板。

### 下一步派单
| 步骤 | 派 | 状态 |
|---|---|---|
| harness 骨架（base_adapter/registry/evaluate.py/2 示例 adapter/configs/tests，复用 metrics.py+tools_topology.py） | **coder** | ✅ **完成**（10 新文件，pytest 24 通+回归 12 通；TODO hook=滑窗推理占位、AUC FOV 口径、evaluate 仅 DRIVE loader） |
| 回填 §1 TODO 超参 + mamba cu126 兼容矩阵 | **researcher** | ✅ **完成**（DSCNet/PASC-Net/cbDice/clDice/MambaVesselNet++ 齐，mamba HF cu126 wheel 命中） |
| 红队 §2.4 反向公平 + mamba 诚实 + OCTAMamba 主表 | **skeptic** | ✅ **完成**（1🔴 creatis 已修，0 剩余致命，放行） |
| 各 baseline adapter 实现（12 个）+ 滑窗推理 + 多数据集 loader | **coder**（5 sonnet 并行，2 波，4 连接掉线后补派） | ✅ **完成**（14 adapter 注册=12 baseline+infra+ours；349 passed/10 skipped[runtime]/1 xfail[HPC FLA]；curl 走 jsdelivr CDN 绕 GFW；datasets/ 与别窗 base_vessel 协同） |
| 训练（batch 分批拍板） | **主线串行** gpu_slot | 🛑 gate P1+P2 PASS |
| 跑后聚合三轴 + 核数对 ACCEPTANCE | **analyst + verifier** | ⬜ |

### ✅ 12 baseline adapter 实现状态（registry 注册名）
| adapter | kind | env | 实现 | 残留 TODO |
|---|---|---|---|---|
| fr_unet | architecture | main | ✅ 官方 curl 忠实移植 + 滑窗推理 self-contained | normalize mean/std 需按训练集自算（占位 mean=0/std=1）；**augment 已补（HFlip/VFlip p0.5 + Fix_RandomRotation 四向等概率，§7.2 对齐，baseline-fix 2026-06-20）** |
| cs_net | architecture | main | ✅ 官方 curl 忠实移植 | normalize 仅 /255 已标注（§7.1 对）；**augment 已补（rotate 100%+HFlip p0.5+RandomCrop+RandEnhance p0.5，factor_range TODO PIL 负值语义待确认，baseline-fix 2026-06-20）** |
| dscnet | architecture | main | ✅ DSConv 纯 PyTorch + cross_loss(BCE) | ✅ **TCLoss 核实闭环（scout-baseline 2026-06-20）**：官方 DRIVE 只 `cross_loss(BCE)` = 对；**normalize 修正（whole_dataset_stats z-score，非 per-image，§7.1 baseline-fix 2026-06-20）**；augment MONAI pipeline 已补（§7.2，各 transform prob TODO 需逐行核） |
| creatis_postproc | architecture(两段式) | main | ✅ 官方 curl + postproc 挂 backbone 输出后 | ⚠️ **LICENSE 核实闭环（scout-baseline 2026-06-20）= 无 LICENSE 文件**（main+master 404，README 无 CeCILL 字样=传言错，arXiv 无 license）→ 默认 All Rights Reserved，**数字/方法引用 OK，但 vendor 代码法律上不允许**，须 issue 作者确认授权（详 §7.4，拍板点）；Stage-2 需 monai + 断点训练数据 |
| cldice | loss | main | ✅ 官方 soft_dice_cldice α0.5 配统一 backbone | — |
| cbdice | loss | main | ✅ 官方移植去 monai/nnUNet 依赖 | ✅ **impl 已对齐官方比例（baseline-fix 2026-06-20）**：`2·BCE+1·Dice+1·cbDice`（官方 nnUNetTrainer_CE_DC_CBDC lambda_ce=lambda_dice+lambda_cbdice，2:1:1） |
| skeleton_recall | loss | main | ✅ 官方 SoftSkeletonRecallLoss 移植 | ✅ **impl 已对齐官方比例（baseline-fix 2026-06-20）**：`1·BCE+1·Dice+1·SkelRecall`（官方 DC_SkelREC_and_CE_loss weight_ce=1 weight_dice=1 weight_srec=1，1:1:1）；skel GT forward 内实时算（略慢） |
| vm_unet | architecture | **mamba** | ✅ vendor + adapter，无 mamba_ssm 时 RuntimeError | wd/normalize/rotation 官方未明示；需 HPC mamba_venv build |
| u_mamba | architecture | **mamba** | ✅ adapter 占位（nnUNet 命令行路径） | 需 nnUNet 自配置 + mamba_venv |
| mamba_vessel_net | architecture | **mamba** | ✅ vendor + MVNWrapper2D | ⚠️ vendor 是 3D Conv3d，2D path 不确定→可能降档 C（§3 退路） |
| nnunet | architecture | main | ✅ adapter 占位（nnUNetv2 命令行） | 需 nnUNetv2 安装 + DRIVE 转格式；evaluate.py 接 nnUNetv2_predict 输出待拍板 |
| pasc_net | architecture | main | ✅ adapter 占位（PASCTrainer，loss 权重已记） | 同 nnunet；preprint 状态标注 |

> **代码骨架/接口全就位，本地 pytest 接口层全绿**。真训需：mamba 系 HPC build mamba_venv；nnUNet 系装 nnUNetv2 + 转格式（走命令行非 train_harness，evaluate 接入待拍板）；creatis license 核实。这些是 runtime/HPC 事项，gate 在 P1+P2 真验 + batch-1 拍板。

### skeptic 红队裁决（2026-06-20，1 致命已修）
- 🔴**已修**：creatis plug-and-play 漏比关键竞品（headline 对立面却不比 = reject 红线）→ 已纳入档 A A12（postproc 续连），OCTAMamba 移 P5。连锁两件一起改完，档 A 回 ≥12。
- 🟡**待写作处理**：§2.4 反向公平不是双标（跟随 clDice/cbDice/SkelRecall 三篇原文「固定 backbone 比 loss」做法），但 §5.1 setup 须显式写 rationale + 表格 loss 类/architecture 类分组表头，化解审稿观感。
- 🟢**可放行残差**：mamba 诚实降档写法正确（≥12 落能装上集合）；SA-UNet 无 LICENSE → 用 SA-UNetv2 前 researcher 核 v2 license，仍无则整条退出对比仅 related 引用；loss 类统一 backbone=Ours 主干同款是正确受控变量（非给 baseline 配弱主干）。
- 总判：**0 剩余致命，可进 coder 全量 adapter 实现。**

### 其余引用标注（写作时处理）
- PASC-Net arXiv preprint 状态、MambaVesselNet++ Dice 0.711（通用模型代价非 bug）— 引用时标注。

---

## 6. SOTA 天花板（参照「要赢多少」，非我们数字）

> **★ canonical 真源 = `../reference/SOTA_NUMBERS.md`**（别窗 Entry 7 researcher×4 核源，每值带出处）。下表速览，以真源为准。

| 数据集 | 最高 Dice | 方法（来源） |
|---|---|---|
| DRIVE | ~0.84 | EFDG-UNet 0.8412 / HM-Mamba 0.8327（Mamba 最强）/ VFGS-Net 0.8323 |
| CHASE_DB1 | ~0.85 | （见真源）/ HM-Mamba 0.8197 |
| STARE | ~0.85 | **FSG-Net 0.8510**（旧 STORY 写 83.21 偏低，已上修）/ VFGS-Net 83.21 |
| HRF | ~0.86 | VFGS-Net 0.8560 |
| FIVES | ~0.9183 | PASC-Net |

> 基调（MASTER_PLAN 决策3）：裸 Dice 已饱和 → 胜负压拓扑(clDice/Betti)/续连(ε_β0/SR/re-ID)轴，裸 Dice 持平不输即可，禁调参作弊凑赢。
> **取胜窗口（别窗核实）**：clDice 报告者极少（仅 HREFNet/PASC-Net/FA-Net/TFFM），主流强作全不报拓扑轴 → 这正是我们 cbDice/clDice/Skeleton-Recall 拓扑-loss baseline + Ours 续连机制要打的轴。
> ⛔ RV-GAN 86.90「F1」疑指标混用，禁引（别窗核实，原文只报 AUC）。

---

## 关键引用（repo + license + 官方数字溯源）

档 A：FR-UNet(github.com/lseventeen/FR-UNet, MIT, JBHI22 DRIVE F1 0.8316) · CS-Net(github.com/iMED-Lab/CS-Net, MIT) · DSCNet(github.com/YaoleiQi/DSCNet, MIT, ICCV23 DRIVE Dice 82.06) · nnU-Net(github.com/MIC-DKFZ/nnUNet, Apache) · PASC-Net(github.com/IPMI-NWU/PASC-Net, Apache, FIVES 91.83, preprint 2507.04008) · clDice(github.com/jocpae/clDice, MIT, CVPR21) · cbDice(github.com/PengchengShi1220/cbDice, Apache, MICCAI24 DRIVE Dice 82.5) · Skeleton Recall(github.com/MIC-DKFZ/Skeleton-Recall, Apache, ECCV24 DRIVE Dice 80.99) · VM-UNet(github.com/JCruan519/VM-UNet, Apache) · U-Mamba(github.com/bowang-lab/U-Mamba, Apache) · MambaVesselNet++(github.com/CC0117/MambaVesselNet, MIT, TOMM25) · OCTAMamba(github.com/zs1314/octamamba, Apache, ICASSP25)

档 C：HM-Mamba(Entropy25, PMC12385817) · VFGS-Net(arXiv2602.10978) · SCS-Net(MedIA21) · TopoMamba(arXiv2604.25545)

---

## 7. scout-baseline 闭环（2026-06-20，researcher×4 核源回填）

> 服务 conductor `scout-baseline` 棒，清 Entry 13 残留 5 TODO。**复现零偏离**：全表官方源码直读为证，查不到显式标 TODO 绝不臆想。仅碰 reference/ + 本文件。

### 7.1 官方 normalize（预处理层，尊重官方配方）

| 方法 | 图像模式 | normalize | 源文件 |
|---|---|---|---|
| FR-UNet | 灰度单通道 | **两步**：①全集 global mean/std `Normalize([mean],[std])` ②per-image minmax→[0,1]（预处理阶段 pickle 存盘，无 CLAHE） | `data_process.py::normalization()` |
| CS-Net | RGB 三通道 | **仅 `ToTensor()`（/255→[0,1]），无 mean/std** | `dataloader/drive.py` |
| DSCNet | 灰度单通道 | **z-score**：`(image-mean)/std`，mean/std 由 `S1_Pre_Getmeanstd.py` 全训练集计算存 `.npy`（非固定常数）；label `/max` | `S3_Dataloader.py` |
| VM-UNet | RGB 三通道 | 自定义 `myNormalize` 按数据集预算 mean/std 后 z-score 再 rescale→[0,255]。**⚠️ 官方无 DRIVE 条目**（只 ISIC/Synapse）→ DRIVE 需自算 mean/std 或 [0,1]（TODO 拍板） | `utils.py::myNormalize` |
| U-Mamba | 继承 nnU-Net v2 | nnU-Net 自动：CT=[0.5,99.5]百分位裁剪+全集 z-score；其他模态=per-patient z-score | `nnUNetv2_plan_and_preprocess`（无覆盖） |

### 7.2 官方 augmentation（尊重官方配方；查不到标 TODO）

| 方法 | augment（transform + 参数 + 概率） | 源文件 |
|---|---|---|
| FR-UNet | HFlip p0.5 · VFlip p0.5 · `Fix_RandomRotation` 等概率选 {-180°,-90°,0°,90°}（各25%）。image+gt 同 seed 同步。仅 training。**无 elastic/无 color** | `dataset.py` + `utils/helpers.py` |
| CS-Net | rotate `randint(-40,40)`° 100% · HFlip p0.5 · RandomCrop 512×512 100%（STARE scale1=688）· RandEnhance p0.5 选{Brightness/Color/Contrast/Sharpness} factor `uniform(-2,2)`（**TODO 负值区间 PIL 语义需人工核原行**）。test 仅 resize512 | `dataloader/drive.py` |
| DSCNet | **MONAI dict pipeline**，外层 80% 触发（20% pass）：Orientation 70% · Affine或2D-Elastic 70%二选一（Affine: trans±30px/rot±π/36/scale±0.15；Elastic: spacing20/mag1/trans10-20/rot±π/36）· ScaleIntensityRange 50% · GaussianNoise或Smooth 50%互斥。**TODO 各 transform 确切 prob 逐行核** | `S3_Data_Augumentation.py` |
| VM-UNet | HFlip p0.5 · VFlip p0.5 · rot[0,360]° p0.5 · rot90(k0-3) p0.5 · ±20° p0.5 · resize→256 bicubic。无 elastic/color | `configs/config_setting.py` + `datasets/dataset.py` |
| U-Mamba | nnU-Net v2 默认 DA5（裁剪/旋转/缩放/镜像/高斯噪声+模糊/亮度对比/低分模拟/gamma）。**⚠️ AMP→Mamba nan，须用无 AMP trainer**（官方 README）。**TODO `custom_transforms/` 是否覆盖默认需 clone 确认** | nnU-Net 框架默认 |

### 7.3 cbDice 权重 / DSCNet TCLoss（loss 核源，已并入 §1 TODO 槽位）

- **cbDice**：官方 `2.0·CE + 1.0·Dice + 1.0·cbDice`（`nnUNetTrainer_CE_DC_CBDC.py::_build_loss()` 显式 `lambda_ce=lambda_dice+lambda_cbdice`；`compound_cbdice_loss.py::forward()` 末行 `weight_ce*ce+weight_dice*dc+weight_cbdice*cbdice`）。现 adapter `0.5BCE+Dice+0.5cbDice` **错→ impl 改 2:1:1**。
- **DSCNet TCLoss**：官方 DRIVE 2D **纯 BCE**（`cross_loss`），TCLoss(persistent homology) 仅 arXiv2307.08388 正文描述、**官方代码未实现/未公开**，git tree 全搜无 topology/hausdorff 文件 → **忠实走 BCE，不自补**。现 adapter 对。

### 7.4 ⚠️ creatis (A12) LICENSE 裁决（拍板点，影响发表合规）

**核实闭环**：repo 无 LICENSE/COPYING 文件（main+master HTTP 404，GitHub API `license:None`，子目录亦无），**README 全文无 CeCILL 字样**（Entry 13「CeCILL 据 README」=传言错/误记），arXiv 2404.10506 代码可用性声明仅含 repo URL 无 license 术语。
- **法律性质** = 无 license 文件 = 默认 **All Rights Reserved**（中/法/美法域：公开不等于授权使用/修改/再分发）[choosealicense.com/no-permission]。
- **可做**：论文里作 baseline 跑实验 + cite 两篇论文 + 引用方法/数字 = 学术引用，风险低。
- **不可做**：**vendor 其代码进我们公开 repo = 代码再分发，无授权法律上不允许**。
- **行动（拍板点）**：① GitHub issue 问作者授权（"What license? want to use as baseline in academic publication + include in supplementary repo"）；② 退路=只本地跑不在公开 repo 含其代码（风险极低）；③ 若作者确认 CeCILL-B(类BSD,保留attribution即可vendor)/CeCILL-C(类LGPL,仅改动文件传染)/CeCILL(全copyleft,衍生须同license)→按变体定 vendor 策略。**A12 是 skeptic 红队补的 headline 唯一正面对照，license 不清前不在公开 repo vendor 代码**。

**关键引用（scout-baseline）**：cbDice `nnUNetTrainer_CE_DC_CBDC.py`/`compound_cbdice_loss.py` · DSCNet `S3_Loss.py`/`S3_Train_Process.py`(BCE) + arXiv2307.08388(TCLoss未开源) · FR-UNet `data_process.py`/`dataset.py`/`helpers.py` · CS-Net `dataloader/drive.py` · DSCNet `S3_Dataloader.py`/`S3_Data_Augumentation.py` · VM-UNet `config_setting.py`/`utils.py`/`datasets/dataset.py` · U-Mamba README + nnUNet discussion#2363 · MambaVesselNet++ `mvn.py`(纯3D)+arXiv2507.19931§4.3 · creatis GitHub API(license:None)+arXiv2404.10506+CeCILL(Wikipedia/TLDRLegal)+choosealicense.com/no-permission
