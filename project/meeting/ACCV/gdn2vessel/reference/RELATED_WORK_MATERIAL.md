# gdn2vessel — §2 Related Work 材料库（核源版）

**用途**：§2 四块文献组织 + GDKVM 硬区分 R3 模板核准 + baseline 全谱核对 + creatis 协议精读。供 P7 写作 + P3 baseline 选型。
**纪律**：每条带 arXiv/会议+年；查不到标 TODO。数字见 [`SOTA_NUMBERS.md`](SOTA_NUMBERS.md)。
**最后更新**：2026-06-20（researcher×4 扇出核源）

---

## §2 块 A — 血管/管状分割（CNN 经典 + SSM/Mamba 家族）

### CNN 经典 baseline
U-Net / UNet++ / AttU-Net / IterNet (AAAI20) / SA-UNet (2020) / CS²-Net / FR-UNet (JBHI22) / SCS-Net / CS-Net / RV-GAN (MICCAI21, 数字禁用见 SOTA_NUMBERS)。

### SSM/Mamba 血管家族（PHASE_3 baseline 全谱核实）

| 方法 | arXiv/会议+年 | 数据集/任务 | 核心机制(scan) | 与我们区分 |
|---|---|---|---|---|
| **Serp-Mamba** | arXiv 2409.04356, IEEE TMI 2024 | **UWF-SLO 广角眼底**(PRIME-FP20)，**非 DRIVE/CHASE** | SIA serpentine scan 沿血管走向蛇形+可学 offset | scan 是其核心 claim（撞车高危）；无 KV 续连记忆；**数据集不重叠→同台性弱** |
| **HM-Mamba** | Entropy 2025, DOI 10.3390/e27080862 (无 arXiv) | DRIVE/CHASE/STARE/IOSTAR/LES-AV | 分层多尺度 + tubular conv + 频域 + gated Mamba；scan 非贡献 | 贡献=多尺度+频域；无关联记忆续连。**Mamba 家族最强同台对手** |
| **VM-UNet** | arXiv 2402.02491, 2024 | ISIC/Synapse，**无血管专用集** | 纯 SSM VSS block，标准4向 | 通用 backbone；常作 baseline |
| **U-Mamba** | arXiv 2401.04722, 2024 | 通用医学 nnU-Net 框架 | CNN+Mamba hybrid | 通用 backbone |
| **OCTAMamba** | arXiv 2409.08000, ICASSP25 Oral | OCTA 造影(非眼底彩照) | Quad-Stream + 多尺度膨胀非对称 conv | OCTA 模态；P5 跨域可纳 |
| **TopoMamba** | arXiv 2604.25545v2, 2026 | Synapse/ISIC/CVC，**无眼底血管** | 对角/反对角 TopoA-Scan | scan(对角)是其 claim（撞车）；对象非血管 |
| **VFGS-Net** | arXiv 2602.10978, 2026-02 | DRIVE/CHASE/STARE/HRF | BA-Mamba2 行列分解双向 scan + 频域 channel attn | 贡献=频域引导；无 delta-rule 记忆。**直接同台对手** |
| **MM-UNet** | arXiv 2511.02193, 2025-11 IEEE | DRIVE/STARE | Morph Mamba Conv 形变采样 + RSSG | 贡献=形变采样；无关联记忆 |
| **MambaVesselNet++** | arXiv 2507.19931, ACM TOMM 2025 | PH2/IXI(3D 脑血管)，非眼底主 | Hi-Encoder + bifocal fusion | 任务广，非眼底；无 KV 续连 |
| **Swin-UMamba** | arXiv 2402.03302, MICCAI24 | Abdomen/Endo/Micro，无眼底血管 | Mamba + ImageNet 预训练 | 通用 backbone baseline |
| **TA-Mamba** | Multimedia Systems 2025, DOI 10.1007/s00530-025-01671-2 (无 arXiv) | DRIVE/CHASE/STARE | serpentine spatial conv + 频率 attn + topo connectivity | **声张 topo connectivity（撞车中危）**；无显式断点续连检索；具体 Dice 未获(付费墙 TODO) |

**补查建议**（防漏比）：COMMA (arXiv 2503.02332, 3D 血管 Mamba) / Multi-scale Vision Mamba-UNet (Birmingham, 专做 retinal, arXiv id TODO) / TFFM (arXiv 2601.19136, 拓扑方向)。

---

## §2 块 B — 拓扑/连通性方法

| 方法 | arXiv/会议+年 | 类型 | 机制 | 与「模型内记忆续连」区分 |
|---|---|---|---|---|
| **clDice** | arXiv 2003.07311, CVPR21 | loss+metric | 软骨架交集 Dice，可微 | 纯 loss/metric，不在模型内做身份记忆 |
| **cbDice** | arXiv 2407.01517, MICCAI24 | loss | clDice + 血管半径边界感知 | 同 clDice，纯 loss |
| **TopoLoss (Hu)** | NeurIPS 2019 | loss | persistent homology Betti 约束 | 全局拓扑数约束，不做断点定位 |
| **Betti Matching** | arXiv 2211.15272, ICML23 | loss+metric | induced matching of persistence barcodes | 全局持久同调，不在网络内检索 |
| **Warping Loss** | arXiv 2112.07812, NeurIPS22 | loss | homotopy 临界点 O(n) | 纯 loss，不做续连记忆 |
| **Skeleton Recall** | arXiv 2404.03010, 2024 | loss | CPU 轻量骨架 recall，省 >90% 算力 | 资源高效拓扑约束 |
| **Topograph** | arXiv 2411.03228, 2024 | loss+framework | component graph 编码拓扑 | 图后处理+loss，非模型内记忆 |
| **DSCNet** | arXiv 2307.08388, ICCV23 | 架构 | Dynamic Snake Conv 自适应弯曲管状 + 持久同调 loss | 架构级感受野自适应；无断点续连机制 |
| **DconnNet** | arXiv 2304.00145, CVPR23 | 架构 | 方向子空间解耦 + 交互解码 | 方向连通性建模在特征空间；单次前向，无跨断点身份记忆 |
| **PASC-Net** | arXiv 2507.04008, 2025 | 架构 | plug-and-play shape conv + 层级 topo 约束 | 结构约束；无模型内关联记忆。**FIVES 天花板持有者** |
| **TFFM** | arXiv 2601.19136, WACV26W | 架构 | latent 图注意力 + Tversky/clDice hybrid | 特征增强，非续连 |
| **creatis (Corvo)** | arXiv 2404.10506, MICCAI24W | **learned post-processing** | residual U-Net 接分割器输出做续连 | **关键区分：显式两阶段后处理（接 mask 非原图），无端到端梯度，无 delta-rule 记忆。我们 benchmark 协议对齐它** |

**写作区分主线**：clDice/cbDice/Betti = loss/metric，不在模型内做身份记忆；creatis = post-processing 两阶段；图算法 = 后处理。**我们 = delta-rule 矩阵态在前向内完成空间身份检索 + 续连（end-to-end，模型内机制）。**

---

## §2 块 C — 线性注意力/DeltaNet（★ novelty 命脉 + GDKVM 硬区分 ★）

### 谱系表
| 方法 | arXiv/会议+年 | 机制 | 视觉/分割应用 |
|---|---|---|---|
| DeltaNet | arXiv 2406.06484, NeurIPS24 | delta rule 替加法更新，Householder 并行 | 无(LM) |
| GLA | arXiv 2312.06635, 2023 | 线性注意力 + data-dependent gating | 无(LM) |
| Mamba-2 | arXiv 2405.21060, ICML24 | SSD 统一 SSM 与注意力 | 有(Vision Mamba 衍生) |
| RWKV Eagle/Finch | arXiv 2404.05892, 2024 | matrix-valued states + 动态递归 | 无(LM) |
| TTT | arXiv 2407.04620, ICML24 | inference 时梯度更新隐状态 | 有(衍生) |
| Gated DeltaNet (GDN-1) | arXiv 2412.06464, ICLR25 | 标量衰减 α_t 统一 delta+gating | 无(LM) |
| **GDN-2（我们锚）** | **arXiv 2605.22791, NVIDIA 2026-05** | **解耦 channel-wise erase gate b_t(key侧) + write gate w_t(value侧)；GDN-1 是其退化特例** | **零应用（核实见下）** |
| KDA (Kimi) | 仅见于 GDN-2 引用，无独立 arXiv (TODO) | channel-wise key decay，但 erase/write 仍单标量 | 无 |

### GDN-2 novelty 核实（claim「视觉/分割零应用」= 真）
- 原论文 (arXiv 2605.22791) 评测全是 LM/commonsense/long-context retrieval，**无任何视觉任务**。
- 官方 repo NVlabs/GatedDeltaNet-2 **纯 NLP，无 vision 代码**。
- 广搜「GDN-2 vision/segmentation/medical 2026」**零命中**。
- **结论：截至 2026-06-20，GDN-2 视觉/分割零已发表应用，claim 核实为真。**

### ★ GDKVM 硬区分（命脉，每事实核准 PASS）
- **身份**：「GDKVM: Echocardiography Video Segmentation via Spatiotemporal Key-Value Memory with Gated Delta Rule」，arXiv 2512.10252，**ICCV 2025**，Rui Wang 等。
- **任务**：心超 **video** 心腔分割，跨帧时序（CAMUS + EchoNet-Dynamic）。✓
- **Gated Delta Rule 角色**：存中间记忆态 + LKVA 建 **inter-frame**（跨帧）关联。✓
- **R3 固定模板（逐句核准通过）**：
  > "Unlike GDKVM [ICCV25] which uses gated delta KV memory across echo video frames (temporal), we operate within a single image (spatial) and add explicit same-vessel re-identification."
  - "gated delta KV memory" ✓ / "across echo video frames (temporal)" ✓ / "within a single image (spatial)" ✓ / "same-vessel re-identification" = 我们 claim（正交，reviewer 不质疑 GDKVM 侧事实）
- **撞车定级**：最近邻但**任务域正交**（时序 video vs 单图空间）。related work 必须正面区分（R3 红线）。

**真撞车查验**：检索确认**无任何方法用 delta-rule/DeltaNet 关联记忆做血管分割断点续连**——技术层次无直接撞车。

---

## §2 块 D — 可微 vesselness / Frangi

- **Frangi-Net** (arXiv 1711.03345, 2017)：把 2D Frangi 重公式化为可训练网络，**学 Frangi 权重做分割**（Frangi 是 backbone）。
- **区分我们**：我们用 **Frangi 输出当外部门信号调制 GDN-2 记忆的 erase/write 强度**（Frangi 是旁路信号源，backbone 是关联记忆）——非「学 Frangi 做分割」。
- 其他：arXiv 2312.15273（Frangi 作伪标签预训练）/ arXiv 2402.14509（vesselness 滤波融合输入）——均为预处理/伪标签/融合输入，**无人将 Hessian vesselness 设计为门控调制线性注意力记忆**。

---

## ⚠️ creatis 2404.10506 精读（我们 P1 benchmark 协议对齐它——两处关键修正）

**论文**：「Restoring Connectivity in Vascular Segmentation using a Learned Post-Processing Model」(MICCAI24W)。

**合成断点协议（精确）**：
- 断点尺寸 `d ~ N(s/(i+1), σ)`，`i`=血管半径，`s ∈ {6,8,10,12}` px（mean 参数），`σ=4`(2D: DRIVE/STARE) / `σ=2`(3D: IXI)。
- 半径采样 `P(i) = 2^(p-i)/(2^p-1)`，`p`=最大半径（细血管→更长断点）。
- 每断点：随机选骨架像素，移除 disk 半径内像素，移除数 `n ~ N(N/2, N/4)`，`N`=disk 内像素总数。

**⚠️ 修正 1**：**原文无 boundary blur / 高斯模糊步骤**——直接像素移除。我们 P1 的「Gaussian 边界 blur」是**自设增量，非 creatis 协议**，写作必须如实区分（不能写成「对齐 creatis 含 blur」）。

**⚠️ 修正 2**：**原文无 SR (Success Rate) 指标**——creatis 只用 DSC、ASSD、ε_β0 **三指标**（**也无 AUC**，之前误列）。**SR 不来自 creatis**，详见下方 SR 裁决。

**ε_β0 精确定义**：`ε_β0 = |β₀ - β₀_gt| / β₀_gt`（归一化连通分量数相对误差，越小越好）。

**架构/训练**：residual U-Net (G_reco)，Adam lr=1e-3，2D 1000ep/3D 3000ep，weighted Dice loss，**输入是分割器输出 mask 非原图**（= 两阶段后处理，区分句素材）。
**数据**：训练 STARE(20)+OpenCCO 合成树(20)，测试 DRIVE(40 2D)/Bullitt(33 3D)。

---

## ⚖️ SR 指标裁决 + 续连/连通性指标全景（2026-06-20 攻坚）

**SR 裁决**：穷尽 creatis / CAPE(2504.00753) / CoANet / Skeleton-Recall / TLTS / APLS——**血管/曲线续连领域无名为 SR 的标准指标**。最接近的「merge success rate」在 connectomics（Berman MIDL2022 arXiv 2112.02039 = 正确合并对数/全部正确对数），非血管主流。
→ **STORY 里「ε_β0/SR」的 SR 必须二选一**：①论文中**自定义并写公式**（标 "novel metric proposed in this work"，如 SR = 正确续连断裂对/GT 全部断裂对），或 ②**换已确立标准指标**（下表，推荐 APLS / Conn / Betti-err）。**不可当"标准指标"裸引**。

**续连/连通性指标全景（§4.2 选型参照）**：
| 指标 | 定义 | 出处 | 量身份 or 量填上 |
|---|---|---|---|
| ε_β0 | \|β0-β0_gt\|/β0_gt 归一化连通分量数误差 | creatis 2404.10506 | 填上 |
| β0/β1-Err | \|β-β_gt\| 绝对差 | Skeleton Recall 2404.03010 / clDice | 填上 |
| clDice | 软骨架 F1 (Tprec·Tsens) | CVPR21 2003.07311 | 填上 |
| APLS | 控制点对最短路径长度差，缺路罚1，0-1 | SpaceNet 2018, CosmiQ/apls | 路由连通 |
| TLTS | 端点对路径长偏差<阈(5%)的比例 | ECCV20 1911.12467 | 路径保真 |
| Conn (CoANet) | 无断点 segment 数/GT 总 segment 数 | IEEE TIP21 CoANet | 填上(segment级) |
| ARI / VOI | connectomics 实例聚类相似/条件熵 | connectomics 标准 | **量身份** |
| MOTA / IDF1 | track 检测+关联综合 / 轨迹级一致率 | MOT 标准 | **量身份** |

**★ re-ID 借 MOT IDF1 有先例（推翻"无先例"）**：**Deep Open Snake Tracker for Vessel Tracing (arXiv 2107.09049)** 已把 MOTA/IDF1/IDS 引入**血管追踪**评估连接误差。→ 我们 re-ID 率借 MOT 框架**有合法引用锚点**；novelty 在「模型内关联记忆做单图空间 re-ID + 指标应用到 2D 眼底续连」，不在"首次借 MOT"。

---

## 盲区 / TODO 汇总（攻坚后）
- TA-Mamba / Birmingham MVSS-UNet (BSPC Vol112 Art108435, 无 arXiv) 绝对 Dice 未获（付费墙）→ related work 定性描述不报数字，不阻投稿。
- KDA 无独立 arXiv（引 GDN-2 时标 "cited in [GDN-2]"）。
- **SR 裁决已出**：无标准 SR → 自定义写公式 or 换标准指标（用户拍）。
- creatis boundary blur + SR 均为我方自设（非 creatis 协议），P1 写作勿误称"对齐 creatis"含此二者。
- ε_β0 修正：creatis 只 DSC/ASSD/ε_β0 三指标，无 AUC。
