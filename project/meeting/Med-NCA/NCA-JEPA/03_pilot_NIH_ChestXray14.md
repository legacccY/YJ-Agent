# NCA-JEPA Pilot 执行计划 — NIH ChestX-ray14 小规模试跑

> **命名规范（单一真源）**：**NCA-JEPA** = 项目/架构家族名；**SCP-JEPA**（Stable Cellular Predictor JEPA）= 加了稳定化三件套的具体方法 = 实验 A2 臂。
>
> 本文是**唯一权威 pilot 执行计划**，合并并取代 `_archive/pilot实验设计_v1.md` 与 `01_创新计划.md §6`。
> 配套读：`01_创新计划.md`（why / 竞争版图 / 退路）+ `02_理论框架.md`（命题与验证路径）。
> 最后更新：2026-06-16。状态：**A0 baseline 已健康跑通**（job 1450052，loss 0.476→0.059@ep50；HPC 部署 + 哨兵 7/8 验通）。**A1/A2 多 seed + Gate 0-3 判定待用户拍板开跑**（训练启停归用户，串行红线）。详见 `04_LOG.md` / `registry.json`（A0 数字以 HPC job 输出为准，需 HPC 侧核）。

---

## 0. 一句话与判向逻辑

**一句话**：投入 4 周主攻前，先用 NIH ChestX-ray14 的一个 ~10k frontal 子集，在 I-JEPA 官方框架上**只换预测器**，用 ~48 GPU·小时验证 4 个最危险假设（PC-1~4），结果直接喂决策门 Gate 0–3，判定大项目走 **GREEN 主攻 / AMBER 限时再赌 / RED 退保底**。

**为什么 pilot 能「为大项目判断方向」**：每个危险假设都对应一条预定义 if-then。pilot 不追 SOTA、不出终版数字，只要**信号**（趋势 + 效应量 + 多 seed 一致）。任一关键假设红灯，立刻转对应退路（B/C/D），不硬推、不续命。

```
PC-1 NCA 连纯预测都稳不住吗？ ─┐
PC-2 三件套压得住塌缩吗？      ├─► Gate 0/1 ─► 稳？→ Gate 2 非劣？→ Gate 3 能力？─► GREEN
PC-3 fire-rate 方差编码质量吗？ │              └ 不稳 → RED 路线 B（稳定性理论论文）
PC-4 下游会掉崖吗？           ─┘              非劣差>5 → 路线 C（诊断工具论文）
```

---

## 1. 为什么 NIH ChestX-ray14 + 为什么 frontal

| 项 | 事实（已上网核实 2026-06） | 对 pilot 的意义 |
|---|---|---|
| 规模 | 112,120 张 X 光 / 30,805 患者 / 14 病理标签 + No Finding | 取 ~10k 子集足够看预训练趋势 |
| 视角 | **全部 frontal（PA + AP），本数据集无侧位** | 用户说的「frontal images」=整个数据集，无需过滤侧位 |
| 可得版本 | 官方 NIH Box 原图（1024²，~45GB）；**Kaggle 224×224 resized 版**（`khanfashee/nih-chest-x-ray-14-224x224-resized`） | pilot 用 224² resized 版，省下载/省预处理，对齐 224² 输入 |
| 对齐 | CheXWorld（CVPR 2025）也用 CXR 公开集做 JEPA | baseline 可比、任务同构 |

> 标签 >90% 准确（NLP 从报告抽取，有噪声）——pilot 下游 probe 容忍此噪声，因为只看 A2 vs A0 的**相对**差，不看绝对 AUROC 上限。

---

## 2. 数据准备

**下载**（开跑前执行，本次不做）：
- 优先：Kaggle `khanfashee/nih-chest-x-ray-14-224x224-resized`（已 224²，PNG）。
- 备选：NIH 官方 Box 原图 + 自行 resize 到 224²（若要 1024² 原始细节，主攻阶段再用）。

**HPC 目录布局**（项目根 `/gpfs/work/bio/jiayu2403/nca-jepa/`）：
```
data/nih_cxr14/
  images_224/                 # 112,120 PNG（或 pilot 子集 ~10k）
  Data_Entry_2017.csv         # 官方元数据（patient_id / 标签 / view）
  train_val_list.txt          # 官方 train+val（86,524）
  test_list.txt               # 官方 test（25,596）
  splits/
    pretrain_10k.txt          # pilot 预训练子集（从 train_val 按 patient 采）
    probe_train_{1,10,100}.txt# 下游 linear probe 训练子集
    probe_test.txt            # 下游评估（held，患者不与 pretrain 重叠）
```

**切分铁律**：**按 `patient_id` 切分**，禁同一患者的不同片子跨 train/val/probe（ChestX-ray14 已知泄漏陷阱，用官方 `train_val_list / test_list` 起步）。pilot 子集从官方 train_val 里按患者采 ~10k；下游 probe_test 从官方 test 取。

---

## 3. 代码地基（反跑偏：复用官方库，不从零搭 JEPA）

| 来源 | 用途 |
|---|---|
| `github.com/facebookresearch/ijepa`（arXiv 2301.08243） | **主地基**。复用 context/target encoder + EMA + mask 采样 + 训练 pipeline，**只换 predictor 模块** |
| `github.com/LeapLabTHU/CheXWorld`（CVPR 2025, arXiv 2504.13820） | 医学 JEPA SOTA baseline + CXR 条件注入（mask/Δ/增强）模式参考 |

**NCA predictor 模块规格**（引 `02_理论框架.md §0.2`，在 latent 14×14 token 网格上，非像素）：
```
初始化：h⁰ = Concat(h_x + p_x, {mask_token + PE(u,v)})
重复 S 步（S=16，远小于像素 Med-NCA 的 128）：
  感知：p = Conv3×3(h) + h           # 局部邻域
  更新：Δ = W₂·ReLU(W₁·p)           # W₂ 零初始化 → Δ⁰≈0
  fire：m ~ Bernoulli(0.5)           # 随机激活
  残差：h ← h + m ⊙ Δ
  锚定：h[ctx] ← h_x                 # context 位置强制不变，防漂移
输出：ĥ_y = h^S[mask 位置]
损失：L = E‖ĥ_y − h_y‖²，h_y 来自 EMA target encoder
```
NCA predictor 参数 **≤ A0 的 ViT predictor**（卖点之一是省参，不偷加参）。条件 z 经 FiLM 注入。

---

## 4. 固定设置（全臂一致）

| 项 | 取值 | 理由 |
|---|---|---|
| backbone | ViT-S/16 | pilot 求快；主攻再上 ViT-B |
| 分辨率 | 224² | 对齐 CheXWorld + Kaggle resized 版 |
| 预训练数据 | NIH ChestX-ray14 ~10k frontal 子集 | 够看趋势，不用全 112k |
| 预训练 epoch | 50（PC-1/2 短跑）/ 100（如需更稳轨迹） | 看趋势足够 |
| NCA 步数 S | 16 | latent 网格小，指数敏感性弱（理论 §1.2） |
| target encoder | EMA(context)，momentum 0.996→1.0 | I-JEPA 标配 + 稳定锚（理论 §5） |
| 条件 z | **只做 mask M**（局部任务）；位移 Δ 留主攻 | 缩面，先验证机制 |
| 下游探针 | ChestX-ray14 held + VinDr-CXR/RSNA（可选），linear probe @1%/10%/100% | 轻、快出信号 |
| seed | gate 判定臂跑 **3 seed** | 多 seed 一致才算数（复现报告教训） |
| 确定性 | 记 cudnn flags + seed；A2 开 deterministic | atomic 非确定性教训，至少留痕 |

---

## 5. 对照臂（5 臂，控变量）

| 臂 | predictor | 步数 | 验什么 |
|---|---|---|---|
| **A0** | ViT predictor（I-JEPA 原版，单次前向） | 1 | 管线 sanity + 下游上限。A0 学不动=管线坏，与 NCA 无关 |
| **A0+** | **early-exit ViT predictor**（N 层，每层接 L2 head，等权聚合，MSDNet 式） | 1…N（可在第 k<N 层早退） | **anytime 不劣化对照**：「努力过的 ViT」也能 anytime（实测 Q(1)=0.975 几乎无损）。验 NCA 在 1/3.4 参数下 anytime 是否仍不劣于 A0+，并把差异引到稳定性可测轴。打死「ViT 也能 early-exit」攻击 |
| **A1** | vanilla NCA（无约束） | S=16 | 反例：直接搬入是否塌缩/发散（故事需要，时间紧可砍） |
| **A2** | **SCP-JEPA**（三件套：SN+EMA+Det） | S=16 | **Pillar 1 主臂**：稳定化是否治好 A1 的病 + 下游不劣于 A0 |
| **A3** | = A2 的 ckpt（不单独训练） | S=16 | 在 A2 上评 ①②③④ 能力 |

**A0+ 设计依据（红线 10，官方源）**：
- 结构：取 A0 的 N 层 ViT predictor，每层后加一个 `nn.Linear(pred_emb_dim, encoder_emb_dim)` 早退头，第 k 层的头输出该深度的预测特征 ĥ_y^(k)。
- loss：`L = Σ_{k=1}^{N} ‖head_k(h_k) − h_y‖²`，**等权聚合**（MSDNet 官方 `ParallelCriterion` weight=1，[ICLR 2018 openreview Hk2aImxAb] / [github.com/gaohuang/MSDNet]）。
- 参数（实测 vit_small/depth6）：A0=11.0M，**A0+=11.76M（+6.7%，6 个 norm+Linear 早退头，early-exit 必要开销）**，NCA(A2)=3.22M。A0+≈A0 同 ViT predictor 量级 → anytime 在 ViT 量级内**公平对照**；NCA 用 1/3.4 参数仍 anytime = 省参加分（非偷加参，反而 NCA 更省）。
- early-exit + 回归任务可行性先例：MeViT（arXiv:2106.15183，覆盖 classification + regression）。
- ⚠️ **全网零 anytime-SSL-predictor 先例**：MSDNet/A-ViT/MeViT 全在分类或判别 fine-tune 做 anytime，**没人在 JEPA latent-regression predictor 位做早退**。即「ViT 也能 early-exit」这攻击本身亦无官方先例——A0+ 是我们自建的诚实对手，非现成 baseline。此事实同时强化②牌 novelty（写入 related work）。
- **官方源已查清（红线 10，researcher 2026-06-16）**：① loss-weight = 全程**等权 w=1**（MSDNet 正文+Lua 源码硬编码，无递增/递减变体）；② exit-head = `LayerNorm + Linear(pred_emb→enc_emb)`（MeViT MLP-EE 退化版 + I-JEPA `predictor_proj`，7 种 head 无专为 SSL regression 设计者，用最简）；③ stop-grad = **全回传**（I-JEPA/MSDNet/MeViT 三源一致，predictor 内无 detach），stop-grad 变体留 Phase1 实测对比（非默认）。
- **代码已落地**：predictor 模块 `ijepa/src/models/earlyexit_vit_predictor.py`（`EarlyExitViTPredictor`，forward 训练返回各 exit list、推理 `exit_layer=k` 单点）；接入 `helper.py`（`predictor_type='earlyexit_vit'` 分支 + `exit_stop_grad`）+ `train.py`（`loss_fn` list 等权聚合）；config `configs/a0plus_earlyexit_vit_vits_nih10k.yaml`。**训练待用户拍**（串行红线）。

---

## 6. 稳定化三件套（A2 = SCP-JEPA）

| 组件 | 机制 | 理论依据 | 实现 |
|---|---|---|---|
| Spectral Normalization | 约束每步更新 Lipschitz | 有界膨胀（理论 §1.1，不声称 L_f<1）| `spectral_norm` 包 conv/fc |
| EMA Target Anchoring | 稳定预测目标，防追自身漂移 | I-JEPA EMA + NCA 特有放大收益（理论 §5）| momentum 0.996→1.0 |
| Deterministic Mode | 消 cuDNN/atomic 非确定性 | 跨 run 可复现（理论 §3.2）| `cudnn.deterministic=True`、`benchmark=False`、`use_deterministic_algorithms(True)`、固定 fire-mask seed |

**互补必要性**见 `02_理论框架.md §6` 定理 6.1（任一缺失在某稳定性度量留漏洞，Phase 1 做消融验证）。

---

## 7. Silent-bug 哨兵（强制，跑任何大实验前先全过）

任一红灯 = 管线 bug，**先修再跑**，别让 bug 假扮结果（VisiSkin visiscore 喂 raw 血泪）。

1. **归一化 assert**：喂入张量 mean/std == 期望 NORM；raw 值溜进来直接 raise
2. **EMA sanity**：target ≠ context；target encoder 不吃梯度
3. **塌缩 canary**：嵌入 std/有效秩/KoLeo 低于阈值 → flag（**别把低 loss 当成功**，JEPA 头号假阳性）
4. **overfit-one-batch**：全跑前单 batch loss 压到 ≈0；压不下 = 代码 bug，立即 abort
5. **z-shuffle 对照**：打乱 mask/z → 下游应掉（≥3 AUROC）；不掉 = z 没接进去
6. **determinism 留痕**：记 cudnn flags + seed
7. **静默发散检测**：ep10 后 loss>3 持续 → 自动标 dead 取消（复现报告 §B.3 signature）
8. **纯预测 overfit**：单图反复预测，10 ep 内 L2<0.01；压不下 = NCA 连预测都学不动，查架构

---

## 8. 4 个危险假设 PC-1~4（pilot 核心）

| # | 假设 | 检法（ViT-S，NIH 10k 子集，mask-only JEPA） | 时间 | 绿灯标准 / 红灯动作 |
|---|---|---|---|---|
| **PC-1** | NCA 训纯预测（latent L2）比训分割稳 | 无约束 NCA（A1），3 seed × 50 ep | 6h | 3/3 无发散、canary 健康。**0/3 → NCA 连纯预测都稳不住，直接转路线 B** |
| **PC-2** | 三件套压得住塌缩 | A2（三件套），对比 PC-1 | 6h | 3/3 存活 + loss 平滑 + 终点 loss 跨 seed std<0.1。**仍不稳 → 加梯度裁剪+降 lr 再一轮** |
| **PC-3** | fire-rate 方差编码预测质量（不确定性牌） | A2 冻结 ckpt，10× 推理，方差 vs 预测误差 Spearman ρ | 2h | ρ≥0.3, p<0.05。**ρ≈0 → 弃不确定性牌（本就被抢），叙事压到 ①②③** |
| **PC-4** | NCA 预测器下游不掉崖 | A2 ckpt，VinDr/ChestX-ray14 1% linear probe vs A0 | 8h | ΔAUROC>−5。**差>5 → 转路线 C** |

**~48 GPU·小时（单卡 4090 计），多卡铺 seed 1–2 天完。**

---

## 9. 量化指标三 Pillar

**Pillar 1 — 稳定性**
- loss 轨迹：无 NaN、无 flat-high（>3 持续>5 ep）；3/3 seed 健康
- 塌缩 canary：token 嵌入 std / 有效秩 / KoLeo 全程 > 阈值（取 A0 正常训练 50% 分位）
- 跨 seed 一致：3 seed 终点 loss std < 0.1
- 盆地双峰：无双峰，所有 seed ep1 loss 同簇（复现报告 §3.3 signature）

**Pillar 2 — 表示质量（非劣，不求赢）**
- linear probe AUROC @1%/10%/100%（ChestX-ray14 held + VinDr/RSNA 可选）：**A2 均值 − A0 均值 > −3**
- 旋转 OOD（{15°,30°,90°}）掉幅：A2 ≤ A0（副指标，不设硬门）

**Pillar 3 — 独有能力**（真护城河 = ① 稳定性 + 省参；② 已被 A0+ 打平降为辅项）
- **① 稳定性可测（硬项）**：见 Pillar 1 + §10 命题 1.1（NCA cell Jacobian L_f，ViT 无对照）。
- **② 随时推理 × 稳定性（差异化辅项，非一等）**：见下 §9.1 专节——anytime 已被 A0+ 打平，重定位为「省参 + 稳定约束下不劣化」。
- ③ 可解释：通道状态呈可解释解剖结构，≥2 人认可（定性）
- ④ 不确定性（次要）：ρ≥0.3，**且同台对标 resilience（arXiv 2605.26726，扰动推理态）+ MC dropout，讲清差异（训练原生 vs 外挂）**

### 9.1 stability-vs-anytime trade-off（差异化辅项，不再单撑一等）

> **定位（已被 A0+ 实测重定位）**：本节最初按「anytime 一等卖点」设计，但 A0+（early-exit ViT 对照臂）实测把这个定位推翻了——A0+ 的 Q(1)=0.975、anytime-gain Q(4)/Q(6)=0.994（job 1450845，ckpt jepa-ep50，`results/anytime_a0plus_s42.csv` 已核），即**努力过的 ViT early-exit 在本 latent-cosine 任务上几乎无损、anytime 动态范围本就极窄**。机制清楚：cosine 自洽性测的是 representation 方向收敛，JEPA latent regression 在 ViT 浅层就 saturation 早收敛——这是「指标偏向 ViT 强项」，不代表 dense/segmentation 下游也无损（ViT-B 分类第 5 层早退掉 −21.8%，LGViT arXiv:2308.00255）。
>
> 因此 anytime **不再单独充一等卖点**，重定位为「**省参 + 稳定性约束下与 A0+ 相当（不劣化）**」的辅项。NCA 真正差异化的护城河在另两轴：① **3.4× 省参**（predictor 11.76M→3.22M，已核）；② **可测稳定性**（NCA cell Jacobian 谱半径 L_f，ViT 给不出此量）。本节的产出价值由此从「证 anytime 更优」收敛为「证 anytime 在省参 + 稳定约束下不劣化，并把差异引到稳定性可测轴」。
>
> **理论根（仍是张力的根，但结论方向调整）**：迭代算法「收敛快 ⇄ 稳定差」是已知 trade-off（Bassily et al. 2018, arXiv:1804.01619「a faster converging algorithm has to be less stable, and vice versa」）；DEQ（Bai 2019, arXiv:1909.01377）示压缩映射 L<1 保证唯一不动点 + 线性收敛，但 spectral norm 约束降表达力。NCA 侧：步数越少对局部扰动越稳（arXiv:2310.14809）。这条张力解释了为何稳定区 anytime 动态范围窄——与 A0+ 实测的「窄动态范围」一致，故 NCA 不去争 anytime 幅度，而是争「同等不劣化下更省参 + 可给出稳定性量」。

**怎么测（受控性修正）**：
> ⚠️ **不能「扫 L_f」**：PyTorch `spectral_norm` 把每层最大奇异值固定 σ→1，**不能设定目标 L_f**（04_LOG 已记此设计问题）。真正能受控调的旋钮是步数 S。
1. **受控自变量 = S（`nca_steps ∈ {4, 8, 16, 32}`）**：除 S 外全臂完全一致（复现零偏离，已建 `configs/a2_scp_nca_vits_nih10k_S{4,8,32}.yaml`）。
2. **因变量 = L_f（power iteration 实测）**：每配置训练后用 power iteration 估 NCA cell Jacobian 谱半径 L_f（见 §10 命题 1.1），作为**观察到的**稳定性量，不预设、不当受控因子。
3. 每配置在 val 上跑到第 k 步即提前终止，记 **Q(k)=ĥ_y^(k) 与满步 ĥ_y^(S) 的 cosine**（latent regression 任务，**不是分割 Dice**），k=1,2,4,8,16,32（不超过该配置的 S）。
4. **A0+ 早退曲线叠同一张图**：A0+ 第 k 层 head 输出对应 ĥ_y^(k)，与 NCA 第 k 步同台 → anytime 不劣化对照（A0+ 基准线 Q(1)=0.975 已就位）。
> **因果口径**：S 与 L_f、Q(k) 的关系是**观察性关联**（S 不同 → 训出的动力学不同 → 实测 L_f 与 Q(k) 不同），**不宣称受控因果 trade-off**（无法在固定 L_f 下单独操纵 S，反之亦然）。论文只报「跨 S 配置观察到 L_f 与 anytime-gain 的关联趋势」，措辞用 "we observe an association"，不用 "causes"/"induces"。

**怎么画（claim 轴已重定向，避免视觉反杀）**：
> ⚠️ **绝不动 A0+ 的 Q(k) 线**（cherry-pick 红线）。但若主图只画原始 Q(k) vs k，A0+ 曲线会全程压顶（Q(1)=0.975 起步就高），视觉上直接讲「ViT 全程更准」——反杀我方。所以**保留诚实 Q(k) 主图的同时，把 claim 轴引到 NCA 独有的两个维度**：
- **主图 A（诚实 anytime，x=参数归一 budget）**：x 轴不用裸 k，改用「**参数归一推理 budget**」= k × predictor 参数量（NCA 3.22M / A0+ 11.76M），y=Q(k)。同等参数预算下 NCA 能多跑步，省参直接进图；A0+ 原始 Q(k) 不变，只是横坐标按各自参数缩放。明确标注「anytime 质量平手，差异在到达同质量的参数成本」。
- **主图 B（stability-margin 单独图，NCA 独家）**：x=配置（按实测 L_f 或 S 排序），y=stability margin / 发散行为指标（L_f、跨 seed loss std、rollout 残差）。**A0+ 在此图上给不出任何点**（ViT 单次前向无 cell Jacobian、无可测谱半径）——这是 NCA 结构上独有、ViT 无法对照的差异化轴，构成真护城河。
- **副图（标量散点，观察性关联）**：x=stability margin（按实测 L_f 排序，标注非受控），y=anytime-gain = Q(8)/Q(16)（受 S 上限约束），看跨 S 配置的关联趋势。**措辞为 "observed association across S configurations"，不宣称因果**。
- **一句话 claim**：图组传达「**anytime 与 A0+ 平手（不劣化）；差异化在稳定性可测轴（主图 B，NCA 独有）+ 省参（主图 A）**」，不传达「NCA anytime 更准」。

**判定阈值（⚠️ 工程 go/no-go 设计决策，非论文 claim；A2 训练进行中，以下是「待验」标准，不是「已达」）**：

> 旧判据「NCA anytime-gain ≥ 0.85」已被 A0+ 推翻失效——A0+ 不加任何约束都到 0.994，单看 NCA 自身 gain 高低无法证明任何相对优势。改为**相对 A0+ 的占优式、可证伪判据**：

- **GREEN（anytime 不劣化达成）**：A2 在某稳定配置下，**k=1（最激进早退）仍 Q(1) ≥ 0.95**，且 anytime 整体不劣于 A0+（A0+ Q(1)=0.975 为基准，A2 落在其 ±0.03 带内即视为「平手/不劣化」），**且在参数归一对比下成立**（同 anytime 质量、1/3.4 参数 → 省参轴占优）。此时 claim = 「省参 3.4× 下 anytime 不劣化于 A0+」，达成。
- **AMBER（0.70–0.85 灰区预案，防续命）**：若 A2 在 k=1 的 Q(1) 落在 0.70–0.85（明显弱于 A0+ 0.975），**不临时找理由续命、不调阈值**：直接降级 anytime 卖点为「best-compromise S=X」的工程说明，主收敛路线全压稳定性 + 省参两轴（主图 B + 主图 A），anytime 仅作「在 best-compromise S 下与 A0+ 的诚实对比」呈现，不再当辅项卖点。
- **RED（anytime 整体劣化）**：所有稳定配置 Q(1) < 0.70 或全程显著低于 A0+ → 诚实写「NCA anytime 在本 latent-cosine 任务上劣于 ViT early-exit」，anytime 完全退出 contribution，只剩稳定性 + 省参。**这是可发表的诚实结论**，不藏。
- **统一口径**：无论哪态，**不宣称「NCA anytime 更准」**——A0+ 实测已封死这条路。最强也只到「不劣化 + 更省参 + 附带可测稳定性」。

---

## 10. 理论锚验证（PC ↔ 命题，引 `02_理论框架.md §9`）

pilot 同时是理论的**可证伪检验**：

| 理论位置 | 在 pilot 哪测 | 量 | 绿灯 |
|---|---|---|---|
| 命题 1.1 L_f 有界 | PC-1/PC-2 | power iteration 估 Jacobian 谱半径（A1↔A2 + S 扫描）| SN 显著压缩谱半径（实测 A1 1.366→A2 1.007，−26%）+ S↑ 单调逼近 1⁺。形式收缩 L_f<1 因残差 I 项结构性不可达（写入讨论，>1.0 非 bug）|
| 命题 1.2 S 步膨胀 | PC-1/PC-2 | 算 (1+L_f)^S（S=16）| (1+L_f)^S 是 worst-case 膨胀上界；L_f>1 时必然爆炸（A2 S16 约 10⁴·⁸），不作硬阈判据，真实稳定性看训练是否健康收敛（loss 跨 seed std≈0.002、无发散）|
| 命题 2.1 方差有界 | PC-3 | 10× 推理方差 vs 步数 | 不随 t 发散 |
| 命题 2.2 NQM | PC-3 | ρ(方差, 预测误差) | ρ≥0.3, p<0.05 |
| 命题 3.2 双盆地消除 | PC-2 | 同 seed Det on/off，loss std | Det on: std<0.05（3 seed）|
| 假说 4.1 更新衰减 | Phase 2 | ‖Δ^t‖ 拟合指数衰减 R² | R²>0.85 → 假说成立 |
| 命题 5.1 EMA 效益 | Gate 1 消融 | 不同 τ 下 loss 平滑度 | τ=0.996 优于 τ=0.9 |

---

## 11. 决策门 Gate 0–3（预定义 if-then，不达标按预案走）

- **Gate 0（管线 sanity, ~D-end1）**：A0 probe 显著 > from-scratch（ΔAUROC≥+5）**且** overfit-one-batch 过 **且** z-shuffle 下游掉≥3。
  - ✅ → Gate 1 ｜ ❌ → **管线 bug，不是 NCA 问题**，修管线不推进
- **Gate 1（Pillar 1 稳定, ~D2）**：A2 3 seed 全跑完无发散/NaN + canary 全程健康 + 跨 seed std<0.1 + 无双峰。
  - ✅ → Gate 2（A1 展示出 A2 修好的病=加分）｜ ❌ → 🔴 **RED 路线 B**
- **Gate 2（Pillar 2 非劣）**：A2 vs A0 ΔAUROC>−3 → Gate 3 ｜ 差 3–5 → 放宽到 −5 + 强化 ①② 叙事 ｜ 差>5 → 🔵 **路线 C**
- **Gate 3（Pillar 3 能力，战略预期已按 A0+ 实测下调）**：
  - **主收敛路线 = 稳定性主**（不靠名义凑两项）。四张牌的真实强度已被实测/竞品重排：
    - **① 稳定性 = 硬项**（NCA 独家发散数据 + 可测 L_f，ViT 结构上给不出）——这是必须达成的核心贡献。
    - **② anytime = 辅项（已被 A0+ 打平）**：A0+ Q(1)=0.975 实测证明 ViT early-exit 在本任务几乎无损，anytime 不再当独立强项，重定位为「省参 + 稳定约束下不劣化于 A0+」（§9.1 GREEN/AMBER/RED 判据）。
    - **④ 不确定性 = 已被 resilience（arXiv 2605.26726）抢**，只作对标区分，不当贡献项。
    - **③ 可解释 = 仅定性加分**（≥2 人认可），不计入硬达标。
  - **判定**：① 达标（稳定性硬项）→ 🟢 **GREEN 以稳定性为核心推进**；② 不劣化 + 省参一并坐实则为加分辅项，未坐实按 §9.1 AMBER/RED 降级，**不影响 GREEN 主线**。① 不达标 → 🔴 **路线 B**（稳定性理论论文，独家失败数据作核心资产）。

**三态**：Gate1+(Gate2|Gate3) 双绿 = GREEN 主攻；Gate1 过但能力/非劣弱 = AMBER 限时 1 周再赌一个性质，仍无则降级或退保底；Gate1 否 = RED 退保底。

**退路（都不白做，Phase 0 产物可复用）**：
- **B 稳定性理论**（Gate0/1 红 / Gate3 零能力）→「迭代预测器在 SSL 中的稳定性：表征/分析/修复」，独家失败数据作核心资产 → NeurIPS/ICLR
- **C 诊断工具**（PC-4 红 / Gate2 差>5）→「世界模型预测失败时：用细胞预测器可视化 JEPA 盲区」→ CVPR/ECCV
- **D 轻量推理**（仅随时推理达标 + 下游不掉崖）→「随时推理的世界模型」→ MICCAI/MIDL

---

## 12. 排期（Phase 0，约 2 天 / ~48 GPU·小时）

| 天 | 活 |
|---|---|
| D1 | 拉 I-JEPA 官方库 + NIH 10k 子集就绪 + 建 8 哨兵；跑通 A0 baseline；**Gate 0 判定** |
| D1–2 | 实现 NCA predictor（A1 vanilla）+ 三件套（A2）+ FiLM；跑 A1/A2 各 3 seed → PC-1/PC-2 |
| D2 | PC-3（A2 ckpt 10× 推理）+ PC-4（1% probe vs A0）；**Gate 1/2/3 判定** |
| D2 晚 | 写 pilot 结论 1–2 页（图 + 三态判定 + 下一步）+ 决策门留痕，存档 |

> Phase 1（稳定+基线，D3–14）、Phase 2（能力，D15–21）、Phase 3（升 ViT-B/0.5M，D22–30）见 `01_创新计划.md §10`，gated on Phase 0 全绿。

---

## 13. HPC 执行细节（XJTLU gpu4090）

- **连接**：host `dtn.hpc.xjtlu.edu.cn` / user `jiayu2403` / 校外先开 **XJTLU VPN**
- **SLURM**：account `shuihuawang`（导师配额，≤4 GPU）/ partition `gpu4090` / qos `4gpus`
- **项目根**：`/gpfs/work/bio/jiayu2403/nca-jepa/`（与复现 `…/mednca/` 平行）
  ```
  nca-jepa/
    ijepa/                  # clone 官方库
    predictors/nca_predictor.py   # 我们只换的模块
    configs/{a0,a1,a2}_vits_nih10k.yaml
    data/nih_cxr14/
    checkpoints/{a0,a1,a2}_seed{42,123,2024}/
    logs/{job_id}.err       # 训练进度在 .err
    results/state.json      # 训练脚本自写，监控单一真源
    results/pilot_*.csv
  ```
- **多 seed 并行**：3 seed 铺 ≤4 卡，PC-1/2 一夜跑完
- **监控**：训练脚本**自写 `results/state.json`**（context 压缩后断链教训，监控靠 state.json 不靠 loop）；复用 `D:\YJ-Agent\hpc_*.py`（snapshot / watch）
- **sbatch 骨架**：
  ```bash
  #!/bin/bash
  #SBATCH --account=shuihuawang
  #SBATCH --partition=gpu4090
  #SBATCH --qos=4gpus
  #SBATCH --gres=gpu:1
  #SBATCH --job-name=ncajepa_a2_s42
  #SBATCH --output=logs/%j.err
  cd /gpfs/work/bio/jiayu2403/nca-jepa
  python ijepa/main.py --config configs/a2_vits_nih10k.yaml --seed 42
  ```

---

## 14. 交付物（单一真源）

- `results/pilot_*.csv` — 每臂（含 A0+）逐 epoch 轨迹 + 塌缩指标（std/rank/KoLeo）+ 下游探针 AUROC + 逐 k 步 Q(k)
- 稳定性三联图 — loss / 塌缩 canary / rollout 残差（A1 vs A2）
- **stability-vs-anytime 图组（差异化辅项，§9.1）** — 主图 A（参数归一 budget，anytime 不劣化 + 省参进图）+ 主图 B（stability-margin，NCA 独家、A0+ 无对照点）+ 副图（anytime-gain vs 实测 L_f 散点，观察性关联）。A0+ 原始 Q(k) 线不改
- 理论锚验证表 — L_f / (1+L_f)^S / λ_eff·S / NQM ρ 实测 vs 理论预测
- **1–2 页 pilot 结论** + GREEN/AMBER/RED 三态判定 + 决策门留痕（每个 Gate 的实测数字 vs 阈值）

---

## 15. 反跑偏红线（贴墙）

1. 只验 3 Pillar + 4 PC，**不顺手加任务/加模态/堆定理**
2. 哨兵不过不跑大实验
3. 决策门数字达不到就按预案走，**不临时找理由续命**（VisiSkin 跑偏教训）
4. 即使走 B/C/D，Phase 0 产物可复用，不算白做
5. 下游评估**只评 checkpoint，不重训**（复现报告规矩）
6. 所有 run 记 **seed + cudnn flags + job ID**，可追溯
7. **不确定性牌已被 resilience（arXiv 2605.26726）抢**，不当头牌、不回避对标
8. **复用官方 I-JEPA 库，不从零搭 JEPA**（把 silent-bug 面降到最小）
9. 数字凭印象写禁止 — 每个数字 csv 核算 + 多 seed 一致 + run_id（ICLR 主线红线 4 复用）
10. **🔴 超参/设置/实现细节禁止臆想** — backbone/lr/weight_decay/增强/mask/NCA cell 架构等，一律**联网查官方论文 + 源代码**确认（CheXWorld `opts.py`/`PRETRAIN.md`、I-JEPA repo、Med-NCA `M3D-NCA-official/src/`）；查不到就标 `TODO 待查`，**绝不"按常见做法/照搬别的库"填值**。违反等同红线 4。本会话已撞两次：① NCA cell 写成单 conv（官方是两路 conv+identity cat×3）② config 把 CheXWorld 开着的增强臆想成"医学影像应关"+ weight_decay 照搬 I-JEPA 0.04（CheXWorld 是 0.05）。
