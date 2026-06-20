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
| A11 | **MambaVesselNet++** | architecture(SSM) | github.com/CC0117/MambaVesselNet | MIT | **mamba** | DRIVE Dice 0.711⚠️metric 口径待核 |
| A12 | **OCTAMamba** | architecture(SSM) | github.com/zs1314/octamamba | Apache-2.0 | **mamba** | ⚠️OCTA 域，更适合 P5 跨域非 P3 主表 |

→ **档 A = 12 个**，达 ≥12。但 A9-A12 是 mamba 依赖（cu126/sm_89 兼容待验），A12 域不对口。**留余量见档 B。**

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
| DSCNet | TODO | TODO | TODO | 400 | TODO | TODO | CE+TCLoss(权重 TODO) | TODO（supp PDF 403） |
| nnU-Net | SGD m0.99 nesterov wd3e-5 | 1e-2 | PolyLR | 1000 | 自动 | 自动 patch | DC+CE 深监督 | 自动流水线 |
| PASC-Net | Adam | 0.01 | TODO | TODO | 2 | 512（FIVES 2048 裁） | Dice+cl+con(权重 TODO) | TODO |
| clDice(loss) | 配 backbone | — | — | — | — | — | soft-clDice α≈0.5 | 随 backbone |
| cbDice(loss) | 配 backbone（官方 nnU-Net SGD PolyLR 1e-2） | — | — | — | — | — | cbDice β=0.5 | 随 backbone |
| SkelRecall(loss) | 配 backbone（官方 nnU-Net SGD m0.99 PolyLR 1e-2） | — | — | — | 2 | 512×512 | weight_srec=1 | 随 backbone |
| VM-UNet | AdamW | 1e-3 | CosineAnneal min1e-5 | 300 | 32 | 256 | BceDice | flip+rotation |
| U-Mamba | 继承 nnU-Net | nnU-Net | nnU-Net | nnU-Net | 自动 | 自动 | nnU-Net | nnU-Net |
| MambaVesselNet++ | Adam | 1e-4 | Cosine min1e-7 | 200(2D) | 16 | TODO | Dice+CE | TODO |
| OCTAMamba | AdamW | 1e-4 | TODO | 400 | 2 | 224 | DiceLoss | TODO |

**档 B 补充超参**：SA-UNetv2 = Adam lr1e-3，0.5BCE+0.5MCC，DropBlock0.15/bs7，epochs150+early stop，整图 592（DRIVE）。MM-UNet = AdamW lr0.001 warmup2+cosine min1e-7，bs5(DRIVE)/2(STARE)，epochs500，input608/704，loss TODO。TFFM = AdamW lr1e-3 bs10 epochs500 input512，Tversky+soft-clDice λ0.5，backbone=UNet++ +EfficientNet-B0。

**TODO 槽位**（researcher 二轮回填或 coder 直读官方源码核）：
- DSCNet：optimizer/lr/batch/input（supp PDF 403 → 直读 GitHub raw `S0_Main.py`）。
- PASC-Net：epochs + loss 三项权重系数。
- clDice：lr/optimizer/epochs/batch（appendix E 403）。
- cbDice：DRIVE 2D 的 epochs/batch（继承 nnU-Net 默认 or 自定）。
- MambaVesselNet++：2D input size + **metric 口径**（Dice 0.711 远低于同行 0.83，疑 metric 定义不同，核准再用）。
- OCTAMamba/MM-UNet/MambaVesselNet++：augmentation。

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
- ⚠️ **可行性待验，别假设能装上**：mamba-ssm 官方对 cu126/sm_89 的支持矩阵需 researcher 二轮查（Serp-Mamba 最严苛固定 cu122+torch2.1+py310）。
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
| harness 骨架（adapter ABC/registry/evaluate.py/base_dataset 重构 train_pilot→train_harness，复用 metrics.py+tools_topology.py+drive.py） | **coder**（可拆 2-3 sonnet：dataset 层/eval 层/registry 层无冲突） | ⬜ 待派（可即起，不 gate P1/P2） |
| 回填 §1 TODO 超参 + mamba cu126 兼容矩阵 + DSCNet/clDice 直读官方源码 | **researcher**（3-5 并行） | ⬜ 待派（与骨架并行） |
| 各 baseline adapter 实现 | **coder**（多 sonnet） | ⬜ 待超参回填 |
| 红队 §2.4 反向公平点 + §3 mamba 诚实跳过 + OCTAMamba 是否进主表 | **skeptic** | ⬜ 待设计成形 |
| 训练（batch 分批拍板） | **主线串行** gpu_slot | 🛑 gate P1+P2 PASS |
| 跑后聚合三轴 + 核数对 ACCEPTANCE | **analyst + verifier** | ⬜ |

### 需主线/Opus 复核或 skeptic 红队的风险点
1. ⚠️ §2.4 loss 类「反向公平」（loss 钉死统一、architecture 尊重官方）— 边界反向，最易引审稿质疑。
2. ⚠️ §3 mamba 跳过的诚实标注 + 「≥12 同框架」目标在能装上集合达成。
3. ⚠️ OCTAMamba（OCTA 域）是否进 P3 主表 vs 移 P5 跨域。
4. ⚠️ §4 ~340 GPU·h 大笔算力，batch-1 校准后再拍全量。
5. ⚠️ SA-UNet 无 LICENSE（红线：license 未确认不纳入发表）→ 用前确认或用 SA-UNetv2。
6. ⚠️ PASC-Net arXiv preprint 状态、MambaVesselNet++ metric 口径 — 引用时标注。

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
