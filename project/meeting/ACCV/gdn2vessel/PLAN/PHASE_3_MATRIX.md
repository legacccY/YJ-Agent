# PHASE 3 — 主实验精确可执行 run 矩阵

**服务**：lever L3（≥12 baseline 同台无漏比）+ L6（拓扑/续连 ≥1 轴显著赢 SOTA + 裸 Dice 持平不输）。
**升格自**：BASELINE_SPEC §4 算力编排 → 精确 run 清单 + 卡分配 + 分批拍板 + 判据对齐。
**真源约束**：数据集路径/split 引 `.portfolio/datasets.json`；超参引 `BASELINE_SPEC §1`（官方核实，TODO 不臆想）；SOTA 参照线引 `reference/SOTA_NUMBERS.md`；评估量尺引 `src/configs/_base_eval.yaml`。
**产出**：planner 设计（M 窗 p3-prep）→ skeptic 红队 0🔴 → 主线落档。
**最后更新**：2026-06-20

> ⚠️ 本文件是 run 清单 + 编排设计，**非已跑结果**。真跑 gate 在「train_harness.py 建成 + batch-1 校准拍板」之后。

---

## 0. 前置阻塞（跑 batch-1 前必清）
1. 🔴 **train_harness.py 不存在** — BASELINE_SPEC §2.2 设计的统一训练台缺；现有 `train_pilot.py` 仅 `--model unet|unet_gdn2`，不吃 config/adapter。14 adapter+registry+evaluate.py 全在，但「按 config 训练任意 adapter」入口缺失。须先派 coder 按 §2（sbatch 模板接口约定）建。**batch-1 第一阻塞，整个 P3 主路径命脉。**
2. 🟡 **DRIVE test GT 缺失**（datasets.json `drive_testgt_gap`）— grand-challenge 官方包不含 test GT。本矩阵主实验统一用 `split=val`（对齐 _base_eval splits:[val]）规避；DRIVE 标准 20/20 test 表待完整包拍板下载后回填（不阻塞 batch-1）。**口径=拍板点（见 §7 🟠-2）。**
3. 🟡 **mamba_venv 未建** — vm_unet/u_mamba/mm_unet 走 mamba 环境，HPC `TORCH_CUDA_ARCH_LIST="8.9"` build（BASELINE_SPEC §3）；build 不通则降档 C 引文献数字。**不阻塞 batch-1**（建议 batch-1 先跑 main 8 run，mamba 等 build 后补，见 §6）。
4. 🟡 **config vs adapter 超参真源歧义** — BASELINE_SPEC 状态表说 adapter 已对齐官方，但部分 yaml 仍占位/旧值。**已核 cbdice：adapter `cbdice.py:102` 硬编码官方 2:1:1，yaml 0.5/0.5 是死字段（无代码读）= 非复现偏离**，但留 harness 契约雷（见 §7 🟠-1）。其余 frunet/csnet/dscnet augment/normalize 真源链须 coder 建 harness 时一次性确认。

---

## 1. 进档 A 的 12 baseline + Ours（registry 注册名 = 真源）

| # | registry name | kind | env_tag | 训练路径 | 备注 |
|---|---|---|---|---|---|
| 1 | `fr_unet` | architecture | main | train_harness | patch 48 训→滑窗评估 |
| 2 | `cs_net` | architecture | main | train_harness | 整图 512 |
| 3 | `dscnet` | architecture | main | train_harness | DSConv 纯 PyTorch；cross_loss(BCE) |
| 4 | `creatis_postproc` | architecture(两段式) | main | train_harness（两阶段）| ★Claim1 唯一正面对照；Stage-2 需断点训练数据 |
| 5 | `cldice` | loss | main | train_harness（统一 backbone）| α0.5 |
| 6 | `cbdice` | loss | main | train_harness（统一 backbone）| 官方 2:1:1（adapter 硬编码，真源） |
| 7 | `skeleton_recall` | loss | main | train_harness（统一 backbone）| 1:1:1 |
| 8 | `vm_unet` | architecture(SSM) | mamba | train_harness | input 256；mamba build |
| 9 | `u_mamba` | architecture(SSM) | mamba | **特殊：nnUNetv2 命令行** | 见 §5 |
| 10 | `mm_unet` | architecture(SSM) | mamba | train_harness | 顶替降档的 mamba_vessel_net |
| 11 | `nnunet` | architecture | main | **特殊：nnUNetv2 命令行** | 见 §5 |
| 12 | `pasc_net` | architecture(nnUNet-based) | main | **特殊：nnUNetv2 命令行** | preprint 状态标注 |
| — | `ours_gdn2` | architecture(Ours) | main | train_harness | **自证走同台，不开后门** |

> `mamba_vessel_net` 已降档 C（repo 仅 3D），不入此表、仅引文献数字 DRIVE 0.711 标 unavailable。

### env 分组
- **main venv（gdn2venv）**：fr_unet, cs_net, dscnet, creatis_postproc, cldice, cbdice, skeleton_recall, nnunet, pasc_net, ours_gdn2 = **10 个**
- **mamba_venv**：vm_unet, u_mamba, mm_unet = **3 个**

---

## 2. 主集 + split（引 datasets.json `vessel_collection_kaggle`）

| dataset | data_root (HPC) | split | 评估 split | n(评估) |
|---|---|---|---|---|
| DRIVE | `/gpfs/work/bio/jiayu2403/gdn2vessel/data/vessel/DRIVE` | 20/20 固定 | **val**（test GT 缺，§0.2） | 20 |
| CHASE | `.../data/vessel/CHASE` | 20/8 | val | 8 |
| FIVES | `.../data/vessel/FIVES` | 600/200 | val | 200（大集，跑久） |
| STARE | `.../data/vessel/STARE` | fixed 10/10 | val | 10 |

> 评估量尺统一 `_base_eval.yaml`：fov_masked=true / threshold=0.5 / input_mode=fullimg（patch 模型滑窗拼回全图）/ seeds=[42,1,2]。
> **STARE LOO 注**：官方标准 = leave-one-out（20 折）算力爆炸。本矩阵 STARE 用 **fixed-split（前10训/后10测，对齐 reference/SOTA_NUMBERS.md TA-Mamba fixed-split 可比口径）规避 20× 成本**——偏离官方 LOO，须在论文 setup 显式声明口径。**拍板点：STARE 是否值得 20× 跑真 LOO**，默认 fixed-split（skeptic 🟢：L6 不押 STARE 裸 Dice，诚实标口径即可）。

---

## 3. 全量 run 数（精确）

| 组 | baseline 数 | × 集 | × seed | run 数 |
|---|---|---|---|---|
| main（含 Ours，含 nnunet/pasc_net 特殊路径） | 10 | 4 | 3 | **120** |
| mamba（vm_unet/u_mamba/mm_unet，按能 build 成功计） | 3 | 4 | 3 | **36** |
| **合计（上限，mamba 全成）** | 13 | | | **156** |

> 与 BASELINE_SPEC §4「168=14×4×3」差异：§4 含已降档 C 的 mamba_vessel_net（−12）；故 13 实体×4×3 = **156 run 上限**（mamba 挂一个 −12）。统一以本表 156 为准。
> u_mamba/nnunet/pasc_net 走 nnUNetv2 命令行，内部 fold 语义须与 train_harness 系 seed 语义对齐（§5，拍板点）。

---

## 4. GPU·h 估 + 4 卡编排（HPC gpu4090，qos=4gpus，MaxWall 7 天）

### 单 run 估（数量级，待 batch-1 实测校准）
- 小集（DRIVE/CHASE/STARE，10-28 图）architecture：~1.5-2 GPU·h
- FIVES（600 训图）：~4-6 GPU·h（拉高总账）
- loss 类（统一 backbone）：~1.5 GPU·h
- nnUNet 系：⚠️ 官方 1000ep 单 fold ~10+ GPU·h，**须限 epoch 或减 fold，拍板**

### 总 GPU·h（数量级）
≈ **300-360 GPU·h**（对齐 BASELINE_SPEC §4 ~340 量级；FIVES 200×3seed×13 是大头）。4 卡并行 ≈ **75-90 卡·h 墙钟**，qos 7 天可分批。

### 4 卡编排（按数据集分卡，天然独立无冲突）
```
卡0 = DRIVE  队列：[全 baseline × seed42,1,2]  ← batch-1 在此卡
卡1 = CHASE  队列：[全 baseline × 3 seed]
卡2 = STARE  队列：[全 baseline × 3 seed]
卡3 = FIVES  队列：[全 baseline × 3 seed]   ← 大集独占，跑最久
```
每卡内串行：main(gdn2venv) + mamba(切 mamba_venv) + nnUNet(命令行) 混排队列；一个 release 自动取下一个（gpu_slot.py）。

---

## 5. nnUNet 系特殊路径（nnunet / pasc_net / u_mamba）

不走 train_harness，是 nnUNetv2 命令行框架（`nnUNetv2_plan_and_preprocess` → `nnUNetv2_train` → `nnUNetv2_predict`）：
- **训练**：命令行，需先把 4 集转 nnUNet `Dataset_XXX` 格式（imagesTr/labelsTr）。
- **评估接入待拍板**：nnUNetv2_predict 输出 → 喂 evaluate.py 算统一三轴；evaluate.py 现接 adapter+ckpt，不接 nnUNet 原生输出。
- **🛑 拍板点**：桥接方案 + 「seed/fold」语义对齐（nnUNet 默认 5-fold，我们要 3 seed）+ epoch 限制（官方 1000ep 太贵）。**建议排 batch-2，batch-1 不含**。

---

## 6. 🛑 分批拍板（大笔算力 = 拍板点，绝不一次裸铺）

### batch-1（验流程 + 校准 GPU·h）
- **范围（main 优先）= DRIVE × {fr_unet, cs_net, dscnet, creatis_postproc, cldice, cbdice, skeleton_recall, ours_gdn2} × seed42 = 8 run（全 main venv）**；mamba 系（vm_unet/mm_unet）**等 mamba_venv build 通后单独补 2 run**（避免 build 失败拖垮 batch-1）。**不含 nnUNet 系**（特殊路径单独验）。
- DRIVE 用 val split（test GT 缺）。
- **+1 FIVES 探针**（🟠/靶点E）：顺带挂 1 个 `FIVES × fr_unet × seed42` 单独校准大集单 run 成本（防 DRIVE 外推严重低估 FIVES）。
- **目的**：① 验 train_harness 主路径全链（train→best.pth→evaluate→三轴 csv）② 验 mamba build ③ 校准 GPU·h（含 FIVES 探针）④ verifier 核 csv schema 22 列 + topo_source 全列同值 ⑤ **复现达标核对**（见 §7 🟠-3）。
- **出口**：analyst 看无 bug + GPU·h 校准 + 三轴 sane（Dice 0.7-0.85 非 0/NaN）+ 复现达标 → 拍板铺 batch-2。

### batch-2（DRIVE 剩余 seed + 其余 3 集全量，铺前拍板）
- DRIVE × seed{1,2} + {CHASE, STARE, FIVES} × 全 baseline × 3 seed。
- nnUNet 系（nnunet/pasc_net/u_mamba）桥接验通后并入。
- **绝不在 batch-1 未校准前裸铺。**

### batch-3（断点续连 benchmark 同台，headline 铁证）
- 全 baseline 在 P1 断点 benchmark 上跑 → 续连轴 ε_β0/SR/re-ID（PHASE_3 §3.4）。
- 依赖 P1 断点协议冻结 + benchmark_cache precompute（CHASE 已冻[DEP-2]，STARE/HRF/FIVES 需先跑 precompute_benchmark.py）。
- **与 P4 命门 re-ID 归因区分**：batch-3 = 全 baseline 续连率横比（L6/L3）；P4 = Ours 内部 A0'/A1'/A2 机制归因（Claim2，别窗）。skeptic 已核：续连三轴（ε_β0/SR/reid_rate）从 baseline `pred_mask`+GT 算，**不需模型有 re-ID 头 → 12 baseline 公平同台可算**（evaluate.py:706 / metrics.py:617-706）。

---

## 7. 每 run 对齐 ACCEPTANCE 判据（L3 + L6）

### 支撑 L3（≥12 baseline 同台无漏比）
- §1 表 12 baseline + Ours 全在同一 evaluate.py 量尺下出 csv → 「同框架无漏比」机械满足。
- 关键竞品覆盖：经典(fr_unet/cs_net) ✅ / 拓扑-loss(cldice/cbdice/skeleton_recall) ✅ / 拓扑-arch(dscnet/pasc_net) ✅ / SSM(vm_unet/u_mamba/mm_unet) ✅ / 公平主干(nnunet) ✅ / **续连对照(creatis_postproc) ✅**。
- 档 C 仅引文献数字，related-work 标「非同框架复现」。

### 支撑 L6（≥1 轴显著赢 SOTA + 裸 Dice 不输）
预登记口径（禁跑完调）：
- **「赢 SOTA」对谁比**：
  - 裸 Dice 天花板 = `reference/SOTA_NUMBERS.md` **主流簇**（DRIVE ~0.83-0.84 / CHASE ~0.82-0.85 / STARE ~0.85 / FIVES ~0.918）。高簇（RV-GAN/MM-UNet ~0.87-0.92）协议不可比，不当天花板。
  - 拓扑轴（clDice）直接竞品 = 同台 cldice/cbdice/skeleton_recall/pasc_net + 文献 TA-Mamba(clDice 0.83-0.85)/HREFNet/FA-Net（标「非同框架」）。
  - 续连轴（ε_β0/SR/re-ID）= 几乎无人占的真空轴，同台 creatis_postproc 唯一直接对手；headline 主战场。
- **「显著」怎么算**：seed≥3 报 mean±std；与对手比 = per-image 配对检验（同 test 图配对），**手算排列检验/Wilcoxon（numpy+itertools，禁 scipy.stats=OMP 红线）**，bootstrap 95% CI 手算（≥1000 resample）。小集 n<6 套命门同款特例（方向为正+最小可达 p），统计承重在 n≥6 集（CHASE n=8/FIVES n=200）+ pooled 跨集。
- **L6 PASS 线（预登记）**：拓扑(clDice/Betti) 或 续连(ε_β0/SR/re-ID) **≥1 轴**，Ours 显著赢同台最强对手 + ≥1 文献 SOTA；**同时裸 Dice 主流簇内持平不输**（Ours Dice ≥ 同台最强 architecture baseline − std，且 ≥ 主流簇下沿）。
- **🟠-3 复现达标闸（skeptic 红队补，batch-1 校准时核）**：同台 baseline 是我们复现的，**若某 baseline 复现裸 Dice 显著低于其文献报告值（>2-3 点）→「Ours 赢它」不当胜利证据，降级为同框架对照并文中标复现差距**。Ours 胜利须双重：① 显著赢同台 baseline 簇 **且** ② Ours 自身裸 Dice 落文献主流簇内（证台子未整体偏低）。防「赢自己弱复现、输文献」假胜。
- **红线**：禁调参作弊凑赢饱和 Dice；拓扑/续连也没赢 → stage-gate FAIL 写诚实回退（PHASE_3 §⑦）。

### 落档可带的 🟠 残差（skeptic 0🔴 + 3🟠，batch-1 前收口）
- **🟠-1 cbdice loss 真源契约**：cbdice.yaml `loss.weight_*` 是死字段（无代码读，adapter:102 硬编码官方 2:1:1）。已在本轮把 yaml 该节标废。**建 train_harness 契约写死「loss 权重唯一真源=adapter.build_loss()，cfg 不得覆盖 loss 内部权重」**，防 harness 退回 0.5/0.5 复现偏离。
- **🟠-2 DRIVE 口径拍板**：①优先=下完整包补 test GT 走标准 20-test 同 SOTA 口径；②退路=全程 val，表头标「val split」不与文献 test 并排同列。L6 拓扑/续连轴同台自比不吃此口径。
- **🟠-3 复现达标闸**：见上，写入 batch-1 校准 checklist。

### 数字纪律
所有 csv 数字 Bash/Grep 核（禁 Read 看数据，红线3）；入 tex 前过 verifier 三方对账。

---

## 8. 依赖 DAG

```
train_harness.py 建成 ─┐
config 真源链确认 ─────┤→ batch-1(DRIVE×8 main×s42 + FIVES探针) → analyst+verifier 校准+复现达标 → 🛑拍板
researcher 补 §1 TODO ─┘                                                          │
mamba_venv build ──────────────────────────────────────────────────────────────┤→ batch-2(4集×全baseline×3seed, 4卡并行)
nnUNet 转格式+evaluate桥接(拍板) ───────────────────────────────────────────────┘
P1断点协议冻结 + precompute_benchmark(STARE/HRF/FIVES) ─→ batch-3(续连轴同台) → L6 续连证据
```

---

## 9. 交接
- → **coder**：① 建 `src/train_harness.py`（最高优先，sbatch 模板接口约定，带 🟠-1 loss 真源契约）② 确认 config/adapter 超参真源链 + 同步缺口 config ③ nnUNet 转格式 + evaluate 桥接（batch-2 前）。
- → **researcher**：核 vmunet train.py wd/normalize/rotation + csnet PIL RandEnhance 负值语义 + dscnet MONAI prob（§1 剩余真 TODO）。
- → **主线串行**：gpu_slot 申请 → batch-1（main 8 run + FIVES 探针）→ batch-2 → batch-3。
- → **analyst**：batch-1 后看三轴 csv sane + GPU·h 校准 + 复现达标；全量后趋势/出图对 L6。
- → **verifier**：核 csv schema 22 列 + topo_source 全列同值 + 关键 Dice/clDice 对 SOTA 主流簇。

## 10. skeptic 红队裁决（2026-06-20，0🔴 放行）
逐攻 planner 6 靶点到根因，**0 致命伤**。核心：L6 胜负点稳押拓扑/续连轴，续连三轴对 12 baseline 公平同台可算（不依赖对手没有的 re-ID 头），不吃 val/test 口径。靶点 D（最像红线）核到 adapter 已硬编码官方 2:1:1、yaml 是死字段=文档不一致非复现偏离。3🟠（🟠-1 loss 契约 / 🟠-2 DRIVE 口径 / 🟠-3 复现达标闸）落档可带，batch-1 前收口。低置信标注：skeptic 未实跑 evaluate.py（territory 只攻不跑），续连公平性基于静态读码——batch-1 实跑时 analyst 须盯「某 baseline 输出空 mask 系统性拿 reid=0 vs Ours 天然占优」是否成立。
