# Med-NCA 前期准备计划（baseline 地基平台）

**定位**：独立新顶会论文的**前期准备**——把 Med-NCA baseline 备成一个「真正稳、可复跑、行为已刻画」的地基平台。
**计划边界**：本计划**只负责地基**。创新点的选择与设计完全由作者（legacccy）独立决定。本文档**不预设、不推荐、不排序**任何创新方向；助理在此计划内不提供方向倾向。
**算力**：本地 Windows GPU 调试 + 跑 2D；XJTLU HPC 跑 3D 大体积（混合）。
**版本**：**v1.0 定稿**（2026-06-03，会话 5）— 复现范围锁定论文自有数据集（hippocampus + prostate），验收对标 RIDGE/MICCAI 复现框架，创新选向留作者独立决策。
**作者**：legacccy（余嘉）｜**原始研究日志**：`Plan.md`（保留，含 web-search 溯源 + 通用复现手册）

> **唯一真源**：地基是否就绪以本文档 §5「地基就绪验收」为准。不存在「基本复现」「差不多稳」的模糊判定——逐项 PASS 才算。
> **定稿后变更规则**：A-F 验收项的增删改 = 改版本号 + PROJECT_LOG 记一笔，不静默改。

---

## §0 一句话定位（反跑偏锚点）

> NCA（神经元胞自动机）是 13k 参数、可在树莓派上跑的「one-cell」分割模型；Med-NCA 用两级（粗→细 patch）把它推到高分辨率医学分割。**本计划做一件事：把这个 baseline 锚成可信、可复跑、行为已量测的地基。地基就绪 = 计划终点，之后由作者独立选创新方向。**

**任何会话动手前先回答**：我现在做的事，是在「把地基备稳」吗？如果是在替作者构思 / 暗示创新方向、或在地基没就绪时就碰创新代码 —— 都是跑偏，立即停手。

---

## §1 永久红线（不可碰，违反走回退记录）

1. **数字凭印象写禁止** —— 每个报告数字必须 csv 核算 + bootstrap 95% CI + run_id/seed。复现 Dice 必须 per-image mean，不能 batch-aggregate（见 §3 口径）。
2. **所有数据只能从公开资源获取** —— MSD / ISIC / BUSI / CheXMask 公开下载，不联系作者要私有数据、不采集线下样本。
3. **复现数字不可与论文「凑」** —— 复现值 PASS/FAIL 以 §5 容差带判定；复现不出就诚实记 gap + 根因，绝不手调种子去「凑」论文数字。
4. **baseline 不可伪造** —— baseline（原 Med-NCA / 未来任何对照）必须自己重跑或 cite-as-paper，不抄论文表格当自己结果。
5. **训练串行** —— 绝不同时启两个训练（本地或 HPC），必须等前一个完成（物理依据见 §9 #11）。
6. **改 degradation / 预处理 / resize / crop 管线先验像素对齐** —— 任何空间变换改动后，先验 input↔GT 对齐再训。
7. **助理不替作者构思创新** —— 本计划内助理只搭地基、做中性量测、报客观风险，不提创新点、不暗示方向、不排序候选。
8. **复现必须完全按官方，零偏离**（🔴 最高优先，2026-06-04 作者立）—— 配置、源码、超参、推理步数、lr、优化器、betas、batch、归一化逐字对齐官方权威源（官方 repo notebook / config.dt / `src/` 源码）。**禁止任何「为让它收敛/达标」的私自改动**：梯度裁剪、降 lr、改步数、换实现、warmup 等一律禁。**连我方提速 subclass 也禁**（FastBackboneNCA 等 GPU-rand 改写改了 RNG 流 → 复现阶段一律用官方原版 `BackboneNCA`，提速版只用于已复现成功后的下游实验）。官方精确配置在我方环境复现不出（发散/不达标）→ 只能诚实记「复现失败 + 根因」，绝不靠偏离凑数字冒充复现。**任何偏离若确有必要，三道闸全过才行**：① 先穷尽证明官方原版无法复现（多 seed / 查环境）② 报告显式标注「这是对官方的偏离，非官方复现」③ 经作者（legacccy）批准。违反 = 复现作废、走回退记录。

---

## §2 方法纪律（防跑偏，仅限严谨性，不涉创新方向）

> 本节只管「复现/地基做得对不对」，不管「创新往哪走」。方向是作者的事。

1. **凭论文 PDF 写架构数字 = 跑偏** —— 必须读官方代码 `M3D-NCA-official/src/`（PDF 与代码已发现不符：§4 Sobel vs learned conv、DiceBCE vs Dice Focal）。
2. **复现还没 PASS 就开始写创新代码 = 跑偏** —— 没有可信、稳定、已刻画的 baseline，任何 Δ 都无意义。
3. **直接改官方代码原地训练 = 跑偏** —— 官方 repo 留作 ground-truth 对照，自己代码进独立 `code/` 目录。
4. **报 Dice 用 batch-aggregate 口径当报告值 = 跑偏**（见 §3）。
5. **地基数字不可复跑 = 不算就绪** —— 同 config 同 seed 重跑必须能拿到同一数字（§5-B）。一个跑一次就再也复现不出的数，不能当地基。

---

## §3 数字溯源纪律（指标口径统一）

| 口径 | 定义 | 用途 |
|---|---|---|
| **per-image Dice mean**（论文标准） | 每张图算 Dice → 对 N 张取均值 + std | **报告 / 验收唯一标准** |
| batch-aggregate Dice | 整 batch 的 TP/FP/FN 汇总后算一次 | 仅训练监控，禁止当报告值 |

**强制**：
- 每个数字落 `results/<exp_id>.csv`（per-image 一行）+ bootstrap 1000× 95% CI + seed + git commit hash。
- 官方框架的 `getAverageDiceScore()` 先核对它是 per-image 还是 aggregate，不确定就自己重算对齐。
- Pseudo-ensemble（10× 推理取平均）与单次推理 Dice 分开报，不混。
- **真实训练轮数**用 `exp.get_max_steps()` / `exp.currentStep` 取，**绝不用** python 变量 `N_EPOCH`（§9 #9 的 config.dt 陷阱会让后者说谎）。

---

## §4 架构事实（已读官方代码核对，非凭 PDF）

> 来源：`M3D-NCA-official/src/models/`、`src/examples/train_Med_NCA.py`。与 Plan.md PDF 推断的差异已标 ⚠️。

### Med-NCA (2D) 真实结构
- **细胞状态**：`channel_n=16`（ch0=输入图，ch1..15 初始 0），grayscale `input_channels=1`。
- **感知 perceive**：
  - `BasicNCA` ⚠️ = **固定 Sobel x/y 滤波** + identity，concat 成 `channel_n*3=48` 维 → 非可学习卷积。
  - `BackboneNCA` = 可学习 conv 变体。
- **更新规则**：fc0(48→128) → ReLU → fc1(128→16, **bias=False 且零初始化** → 初始 Δx=0 稳定) → 随机 fire_mask(rate=0.5) → 残差 `x = x + Δx*mask`，**前 input_channels 通道每步还原**。
- **两级**：coarse `16×16`（下采样）跑 64 步通信全局 → 上采样 → fine `64×64` 取 patch 跑 64 步，仅 patch 算 loss。

### 真实超参（official example，非 PDF 表）
| 参数 | 值 | 备注 |
|---|---|---|
| lr | `16e-4` | ⚠️ PDF 未给具体值 |
| betas | `(0.5, 0.5)` | Adam，非默认 |
| lr_gamma | 0.9999 | 每步衰减 |
| batch_size | 48 | |
| n_epoch | 1000 | |
| inference_steps | 64 | |
| fire_rate | 0.5 | |
| hidden_size | 128 | |
| loss | **DiceBCELoss** | ⚠️ PDF 说 Dice Focal |
| data_split | 0.7 / 0 / 0.3 | train/val/test |

### M3D-NCA (3D)
- 3D conv k=7 替代 2D，n-level（Hippocampus=1, Prostate=2），batch duplication 稳定训练。步数 `s = max(W,H,D)/((k-1)/2)`。

### ⚠️ 复现只用论文自己的数据集（不用自建 ISIC）
- **决策（用户定，2026-06-03）**：复现严格按论文，**只用官方两个数据集 hippocampus + prostate**，不用我们自适配的 ISIC（避免「自建数据集对着来路不明靶子 PASS」的完整性漏洞）。
- **核实（web，Med-NCA IPMI 2023 Table 1）**：官方 `MECLabTUDA/Med-NCA` 与 `M3D-NCA` 只评 hippocampus + prostate，无 ISIC。官方 Dice：

  | 数据集 | Med-NCA | UNet baseline | 来源 |
  |---|---|---|---|
  | Hippocampus (MSD Task04) | **0.886 ± 0.042** | 0.858 ± 0.044 | IPMI'23 Table 1 |
  | Prostate (MSD Task05) | **0.838 ± 0.083** | 0.799 ± 0.099 | IPMI'23 Table 1 |

- **R1 复现核对**：我们 0.8661 vs 论文 0.886 ± 0.042 → 落在 1 个 std 内，PASS 成立（之前用的 0.882 是近似，0.886 为 Table 1 精确值）。
- **R2 = Prostate**（取代旧 ISIC 方案）：3D MRI、2-level NCA，可复用 R1 的 `Dataset_NiiGz_3D` 路径（**不需** ISIC 的 RGB 适配器）。⚠️ prostate **std 0.083 ≈ hippocampus 两倍**，且 MSD Task05 仅 ~32 个标注体积（70/30 → ~22 train / ~10 test）→ 小样本高方差，容差带见 §5-A。⚠️ prostate 是多区域标注（PZ+TZ）→ 复现前先核对论文是按整腺二值还是按区域算 Dice。
- **ISIC 处置**：`run_r2_isic.py` / `dataset_isic2d.py` 保留不删（作者将来选向若需 2D 皮肤可复用），但**移出复现地基范围**。

---

## §5 地基就绪验收（PASS/FAIL — 计划终点判定）

> **对标依据（2026-06-03 web 核实）**：本节标准对齐医学影像复现的公开框架——**RIDGE**（Reproducibility / Integrity / Dependability / Generalizability / Efficiency 五维，arXiv 2401.08847）、MICCAI 复现 checklist、ML-医学影像复现专章（NBK597469）。核心规则已内化：① 固化**确切 test 样本清单**（否则不可复现）；② 报 bootstrap CI，**不**用「重复 N 次 CV 把 SE 人为缩小」的伪精度；③ 跨数据集验证「至关重要」（≥2 独立数据集）；④ Efficiency 要量 params + FLOPs + 推理时间 + VRAM；⑤ release 要 pip/Docker + GPU/OS 规格 + ckpt + 预处理代码。

> 「地基就绪」= 下列 **A-F 六组全 PASS**。任一未过 = 地基未就绪 = 不得进入创新选向。
> Dice PASS 判定按每个锚点单列（见 §5-A，R1/R2 用「bootstrap CI 含论文均值」而非统一 ±0.02——因 prostate 方差是 hippocampus 两倍）。FAIL 必须 PROJECT_LOG 写 gap + 根因。

### A. 复现锚点（论文两个数据集都复现 —— 不只靠一个）
| ID | 任务 | 论文 Dice (IPMI'23 Table 1) | PASS 判定 | 状态 |
|---|---|---|---|---|
| **R1** | Hippocampus (3D, MSD Task04) | 0.886 ± 0.042 | per-image mean 的 bootstrap CI 含 0.886，或点估 ≥0.86 | ✅ 0.8661 |
| **R2** | Prostate (3D, MSD Task05) | 0.838 ± 0.083 | per-image mean 的 bootstrap CI 含 0.838，或点估 ≥0.81 且 > UNet 0.799 | ⏳ **未训（hard gate）** |
| **R3** | 参数量 < 100K | 论文 12,480 | 硬核对 <10⁵ | ✅ 25,920 |

> **A 组 PASS 条件**：R1+R2+R3 全过。**复现论文的两个数据集都对上 = 把论文整张评估表复现了**，跨数据集验证是复现专章点名的「paramount」要求。
> **prostate 容差带说明（事前定，非事后凑）**：prostate std 0.083 ≈ hippocampus 两倍，且 test 仅 ~10 例 → 用「CI 含论文均值」判定（统计上 = 与论文一致），比硬性 ±0.02 更稳健；副核对 = 是否超 UNet 0.799。守 §1 红线 3（不手调凑数）。

### B. 复现稳定性（噪声地板 —— 让未来任何 Δ 可解释）
| ID | 检查 | PASS 条件 |
|---|---|---|
| **S0** | 固化确切 test 样本清单 | `data_split.dt` 解出的 test id 全列入 `results/test_ids_{r1,r2}.txt`（复现专章硬要求：不列样本 = 不可复现） |
| **S1** | 同 config 同 seed 重跑 eval | per-image Dice 与冻结值差 < 1e-4（确定性 eval 可复跑） |
| **S2** | 多 seed（≥3）重训同 config | 记录 baseline Dice 的 seed 间 std → 「噪声地板」；报 bootstrap 95% CI，**不**报「多跑几次缩小的 SE」（复现专章点名的伪精度反例） |

> **为什么必须有**：将来任何改动带来的 Δ，只有大于这个噪声地板才算真信号。没量过地板，地基上盖的楼都悬空。
> **接地（NBK597469 / RIDGE）**：S0 是「Integrity/可复现」的硬条件——必须能说清*哪些*样本进了 test；S2 是「Dependability」——但专章明确警告别用「任意多次 CV 把 SE 压到任意小」造假精度，所以用 bootstrap CI + 固定 seed 集报，不玩 SE 数字游戏。**S0-S2 全中性量测，不指向任何方向。**

### C. baseline 客观行为档案 + 复现「论文自己的声明」（中性 —— 作者选向时自取）
> 这一组分两半：① 复现 Med-NCA 论文**自己宣称的性质**（轻量 / 鲁棒 / 内建质控）——这是「baseline 是否如其所述」的复现，不是选方向；② 客观行为量测存档。

| ID | 量测 | PASS / 落盘条件 | 说明 |
|---|---|---|---|
| **R3** | 论文声明①：轻量 | 参数量 + FLOPs + 模型存储 KB | ✅ 25,920 参数（FLOPs/KB 待补，并 D2） |
| **V1** | 论文声明②：尺度/平移/形状不变 + 抗伪影鲁棒 | 对 test 施加 scale/translate/MRI-artifact 扰动，Dice 退化曲线落盘，核对「仅轻微退化」是否复现 | ⏳ 未做（论文核心卖点，必须验真） |
| **V2** | 论文声明③：内建质量控制 (NQM) | 复现 M3D-NCA 的 NQM：**10× 随机推理取方差** → 检出 Dice<0.8 的 failure；论文锚 hippocampus **94.6%** / prostate **50%** 检出率，核对量级是否复现 | ⏳ 未做（= R5 的论文锚） |
| **R4** | pseudo-ensemble Dice vs 单次 | CI 排除 0（方向成立即可） | ✅ 已测 +0.00081 |
| **R5** | NQM/预测方差 与 误差 的相关性 | ρ + p 值落盘（**只量测、不判 PASS 门槛**） | ⏳ 未做 |
| **C1** | 收敛曲线 + 推理步数 vs Dice | 曲线 csv 落盘 | ⏳ 未做 |

> **定位声明**：V1/V2 是**复现论文自己的声明**（Med-NCA 卖点就是 robustness/invariance + 内建质控，§8 论文明写）——验它们 = 验「baseline 是否真如论文所述」，属复现完整性，**不是助理在暗示往鲁棒性/不确定性方向做创新**。R4/R5/C1 是客观行为档案。**助理只量测、落盘、报客观事实（如「收敛后 ensemble 增益 +0.00081」），不解读这些数据「适合做什么创新」、不据此推荐方向。** 信号弱也照实记，那是事实不是 FAIL。

### D. 算力预算 + Efficiency 报表（地基要「能盖楼」不只「能站人」）
> 对标 RIDGE「Efficiency」维度：轻量声明不能只报参数量，要 params + FLOPs + 推理时间 + 峰值 VRAM 四件套。

| ID | 检查 | PASS 条件 |
|---|---|---|
| **D1** | 单 variant 训练成本实测 | R1/R2 各自 s/epoch + 300ep / 1000ep 墙钟实测落盘 |
| **D2** | Efficiency 四件套 | params + FLOPs（每张图 forward）+ 单图推理时间 + 峰值 VRAM，R1/R2 各一行落 `results/efficiency.csv` |
| **D3** | 本地 vs HPC 分工写定 | 哪类实验本地、哪类上 HPC，VRAM 上限（8GB）下的 batch 边界确认（含是否 OOM） |
| **D4** | 快速迭代 proxy 配置 | 一个低分辨率/子集的小规模对照配置，单次 < 1h，供未来快速试错 |

> **为什么必须有**：① 论文级实验要跑几十个 variant，不知成本/上限/没快跑 proxy = 盖不了楼；② Efficiency 四件套是 NCA「轻量」卖点的硬证据，审稿人会要（RIDGE 明列）。

### E. 工程可复跑（一键重建地基）
> 对标复现专章 release 要求：pip/Docker 装依赖、share OS/GPU/threading 规格、share 冻结 ckpt + 预处理代码、列确切样本（已并入 S0）。

| ID | 检查 | PASS 条件 |
|---|---|---|
| **E1** | 一键复跑脚本 | 单脚本从冻结 ckpt 复现 R1+R2 全部数字（eval-only） |
| **E2** | 环境锁定 | conda env 依赖版本固化（`requirements.lock` + ENV_NOTES），记录 OS / GPU 型号 / CUDA / torch 版本 / 线程设置 |
| **E3** | 冻结 ckpt + state.json 纪律 | ckpt 路径 + seed + commit 在报告中可溯源；HPC 训练自写 state.json |
| **E4** | 预处理代码可复跑 | Hippocampus/Prostate 的 nii 加载、slice 展开、归一化预处理脚本随 ckpt 一并冻结（专章：预处理代码必须可复现） |

### F. 文档冻结
| ID | 检查 | PASS 条件 |
|---|---|---|
| **F1** | baseline 冻结报告 | `results/BASELINE_FROZEN.md`：A-E 全部 PASS 证据 + 数字 + ckpt 路径 + 复跑命令 |

**地基就绪 = A∧B∧C∧D∧E∧F 全 PASS。** 达成即在 PROJECT_LOG 记「地基冻结」，交棒给作者选创新方向（§7）。

---

## §6 路线图（前期准备 → 地基冻结 → 交棒）

### Phase 0 — 环境 + 复现锚点（A 组 + 部分 E）
- [x] **P0.1 环境**：conda mednca(py3.9) + 官方 requirements + CUDA torch 验通。
- [x] **P0.2 fork 隔离**：官方 `M3D-NCA-official/` 只读；工作目录 `code/`。
- [x] **P0.3 数据**：Hippocampus（R1）解压配对完整；**Prostate（R2，MSD Task05）待下载**。
- [x] **P0.4 R1**：Hippocampus per-image Dice 0.8661 ✅ PASS（vs 论文 0.886 ± 0.042）。
- [ ] **P0.5 R2 = Prostate**（取代 ISIC）：下 MSD Task05 → 核对 Dice 口径（整腺二值 vs PZ+TZ 区域）→ 复用 R1 的 `Dataset_NiiGz_3D` + 2-level → per-image Dice vs 0.838 ± 0.083（判定见 §5-A）。⚠️ 训前先 `Remove-Item -Recurse checkpoints/r2_prostate`（防 config.dt 陷阱 §9 #9）。⚠️ prostate 体积比 hippocampus 大，先 2-epoch smoke 验 VRAM/不 OOM，必要时上 HPC。
- [x] **P0.6 R3**：参数量 25,920 ✅ PASS（论文 12,480 量级）。

### Phase P — 地基加固（B + C + D + E + F）
> Phase 0 的 R1+R2+R3 只是「复现对」，离「地基稳」还差稳定性、论文声明复现、行为档案、算力预算、可复跑、冻结报告。

- [ ] **P.S 复现稳定性**（B 组）：S0 固化 test 样本清单 + S1 同 seed eval 可复跑 + S2 多 seed 方差（噪声地板，报 bootstrap CI 不玩 SE）。
- [ ] **P.C 论文声明复现 + 行为档案**（C 组）：V1 鲁棒/不变性退化曲线 + V2 内建质控（方差↔误差）+ R5（NQM-误差相关）+ C1（收敛曲线 / 步数-Dice），中性量测落盘。
- [ ] **P.D 算力预算 + Efficiency**（D 组）：D1 成本实测 + D2 四件套(params/FLOPs/推理时间/VRAM) + D3 本地/HPC 分工 + D4 proxy 配置。
- [ ] **P.E 工程复跑**（E 组）：E1 一键脚本 + E2 环境锁(含 OS/GPU/CUDA 规格) + E3 state.json + E4 预处理代码冻结。
- [ ] **P.F 冻结报告**（F 组）：`results/BASELINE_FROZEN.md` 汇总 A-E 证据。

### 交棒 — 创新选向（作者独立决策区，详 §7）
> A-F 全 PASS 后，本计划结束。后续创新点的选择、实验设计、投稿规划由作者另起文档，助理不在本计划内提供方向。

---

## §7 创新选向 —— 作者独立决策区（本计划不介入）

> **本节刻意留空。** 创新方向、卖点、候选清单的构思与排序由作者 legacccy 独立完成。
>
> 助理在前期准备计划内的职责到「地基冻结」为止：
> - ✅ 把 baseline 复现对、量稳、行为档案测全（§5 A-C）；
> - ✅ 报客观风险与客观量测（如「收敛后 ensemble 增益 +0.00081」是事实陈述）；
> - ❌ **不**列创新候选、**不**暗示某方向更有 novelty、**不**排序、**不**替作者判断「这个能不能打顶会」。
>
> 地基就绪后，作者决定方向，再另建 `INNOVATION_PLAN.md`，届时助理按作者指定方向提供执行支持。

---

## §8 参考资料（事实，2026-06-03 web 核实）

### 官方仓库 / 原论文（baseline 正源）
- **Med-NCA 专用 repo**（2D，IPMI 2023 正源）：https://github.com/MECLabTUDA/Med-NCA （训练 notebook `train_Med_NCA.ipynb`；**只含 hippocampus + prostate，无 ISIC**）
- M3D-NCA repo（3D，MICCAI 2023，已 clone 至 `M3D-NCA-official/`）：https://github.com/MECLabTUDA/M3D-NCA
- Med-NCA IPMI 2023：https://arxiv.org/abs/2302.03473
- M3D-NCA MICCAI 2023（内建质量控制 = V2 锚）：https://arxiv.org/abs/2309.02954
- MED-NCA MedIA 扩展版（8 数据集 + NCA-VIS，本地有 PDF；复现地基不依赖，作者选向时背景参考）
- Growing NCA 理论基础：https://distill.pub/2020/growing-ca/

### 复现严谨性方法论（§5 验收对标依据）
- **RIDGE 框架**（Reproducibility/Integrity/Dependability/Generalizability/Efficiency）：https://arxiv.org/abs/2401.08847
- ML-医学影像复现专章（NBK597469）：https://www.ncbi.nlm.nih.gov/books/NBK597469/
- MICCAI 复现 checklist（投稿用）

### NCA 文献景观（事实清单，助理不排序、不推荐、不评判 novelty）
> 仅供作者选向时自查背景，本计划不在此处做任何方向倾向。
- NCA 泛化能力（域泛化，Korevaar 等 2024）：https://arxiv.org/abs/2408.15557
- MedSegDiffNCA（diffusion×NCA 皮肤分割 2025）：https://arxiv.org/html/2501.02447v1
- 皮肤分割 NCA（UNCA，ISIC2017）：ScienceDirect S1746809424006050

### 数据集（地基只用论文自己的两个：Task04 + Task05）
| 任务 | 维度 | 源 | 备注 |
|---|---|---|---|
| Hippocampus | 3D MRI | MSD Task04 medicaldecathlon.com | R1 锚点 ✅，论文 0.886 ± 0.042 |
| Prostate | 3D MRI | MSD Task05 medicaldecathlon.com | R2 锚点 ⏳，论文 0.838 ± 0.083；多区域标注(PZ+TZ) |
| ~~ISIC 2018 皮肤~~ | 2D RGB | — | **移出复现范围**（自建数据集，非论文用；代码 `run_r2_isic.py` 留作未来备用） |

---

## §9 工程血泪清单（每次训练前扫一遍）

1. **训练串行**，绝不并发两个（物理依据见 #11）。
2. **HPC 训练脚本自写 `state.json`**（epoch/loss/dice/timestamp），不靠 loop 监控记忆。
3. **本地 Start-Process 开窗后立即 arm Monitor**，不只靠 ScheduleWakeup。
4. **Windows 训练规范**：DataLoader `num_workers=0`（spawn 安全）、路径 raw string、`KMP_DUPLICATE_LIB_OK`、长下载/装包用 Start-Process 开新窗不后台。
5. **删临时文件用 PowerShell `Remove-Item`，绝不 `rm`**（权限白名单外会级联取消整批）。
6. **改预处理后先验像素对齐**（§1 红线 6）。
7. **指标口径**：报告值 per-image，监控值 aggregate，不混（§3）。
8. **装 CUDA torch 前先 `df -h` 看盘**：cu118 wheel ~2.5GB，conda env 默认在 C 盘；C 盘 <6GB 必先腾空间或把 env 建到 D 盘。会话 1 栽过（`[Errno 28] No space left`）。
9. **重训前必清 model_path 目录**：官方 `Experiment.reload()`(Experiment.py:82) 启动若目录有 `config.dt` 就**整个覆盖运行时 config**，`n_epoch` 被旧值锁死、env 变量静默失效。会话 3 栽过（连两次「300/1000ep」实只训 ~8 epoch）。`Remove-Item -Recurse checkpoints/<exp>` 后再训。summary 里 `epochs` 字段是 python 变量照抄，**不能当真实轮数**，真实轮数 = `exp.currentStep` / `exp.get_max_steps()`。
10. **NCA 训练慢真因 = 计算密集非数据**：64 步顺序推理×N 级不可并行。`Model_BasicNCA.update:71` 的 fire-mask `torch.rand` 默认 CPU 生成再 `.to(device)`，每步一次同步停顿 → 用 `code/fast_nca.py` 的 device-rand subclass 修（数学等价）。修后 GPU 满载仍 60-90s/epoch（4070 Laptop），1000ep ≈ 20h，属正常成本。
11. **本地单 GPU 上绝不并发第二个训练/推理 job**。会话 4 栽过：R1 跑到 ep72 时为「并行」启 R2 smoke，显存逼满（7869/8188 MiB）；`Stop-Process` 杀 smoke 的控制事件波及 R1，触发 MKL `forrtl: error ... window-CLOSE event`，**R1 进程假活（CPU 近 0、脱离 GPU）实则卡死**，损失 ep50~72。教训：① 单卡训练期不碰 GPU（第二个 job 走 HPC 或排队）；② 进程假活看三件：GPU 显存是否仍占、`nvidia-smi --query-compute-apps` 有无该 pid、CPU 时间是否在涨——log 冻结+脱离 GPU+CPU 不动 = 死；③ 这是 §1 红线 5 的物理依据。
12. **Windows 11 解 tar 别看退出码**。会话 5 栽过：下 Task05_Prostate.tar（含 macOS `._*` 资源叉），PowerShell 自带 `tar`(bsdtar) 对 `._*` 吐 warning 并返回**退出码 1**，脚本 `if ($LASTEXITCODE -ne 0)` 误判 EXTRACT_FAILED 直接 exit，文件根本没解（tar 下载其实完好）。修：① 解压用 `tar --exclude='._*' -xf`；② **成功判定按解出的文件数，不看退出码**（`Test-Path imagesTr` + count `.nii.gz`）；③ 实在不行用 Git Bash 的 GNU tar 解（会话 5 即这么救的，GNU tar 对 `._*` 不报致命）。MSD tar 几乎都带 macOS 垃圾，下任何 Task0X 都先 `find -name '._*' -delete`。

---

## §10 下一步（地基冻结路径）

**当前状态**：A 组差 R2（= Prostate）；B/C/D/E/F 组未起。

1. **下 MSD Task05 Prostate** + 核对 Dice 口径（整腺二值 vs PZ+TZ）。
2. **R2（A 组收口）**：清 `checkpoints/r2_prostate` → 2-epoch smoke 验 VRAM/不 OOM + 量 s/epoch（顺带 D1/D2）→ 放长训 → per-image Dice vs 0.838 ± 0.083（判定见 §5-A）。
3. **R2 PASS → 起 Phase P**：S0-S2 稳定性 → V1/V2/R5/C1 论文声明+行为档案 → D2-D4 算力 → E1-E4 复跑 → F1 冻结报告。
4. **A-F 全 PASS → PROJECT_LOG 记「地基冻结」→ 交棒**：作者独立选向，另起 `INNOVATION_PLAN.md`。

> **gate 提醒**：A-F 任一未过前不碰创新代码。创新方向不在本计划讨论范围。
