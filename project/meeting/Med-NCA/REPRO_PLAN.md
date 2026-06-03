# Med-NCA 复现 → 创新 工作计划（独立顶会论文）

**定位**：独立新顶会论文（非 ICLR VisiSkin 大项目子模块）
**策略**：最小复现做信任锚点 → 创新点做顶会卖点（不做广度优先 8 数据集全复现）
**算力**：本地 Windows GPU 调试 + 跑 2D；XJTLU HPC 跑 3D 大体积（混合）
**最后更新**：2026-06-02 | **作者**：legacccy（余嘉）
**原始研究日志**：`Plan.md`（保留，含 web-search 溯源 + 通用复现手册，本文档为其升级版正式工作文档）

> 本文档把 ICLR 大项目的 6 件套纪律框架（红线 / 跑偏定义 / 数字溯源 / 工程血泪 / 量化验收 / lever stack）迁移到 Med-NCA。
> **唯一真源**：任何 Med-NCA 实验完成判定以本文档 §5 验收表为准，不存在「基本复现」。

---

## §0 一句话故事（反跑偏锚点）

> NCA（神经元胞自动机）是 13k 参数、50kB 存储、可在树莓派上跑的「one-cell」分割模型。Med-NCA 用两级（粗→细 patch）架构把它推到高分辨率医学分割。**本项目先用最小复现锚定「NCA baseline 可信」，再在其上做一个能打顶会的创新点。**

**任何会话动手前先回答**：我现在做的事，服务于「最小复现可信」还是「创新点卖点」？两者都不沾的操作 = 跑偏。

---

## §1 永久红线（不可碰，违反走回退记录）

从大项目迁移 + NCA 专属：

1. **数字凭印象写禁止** —— 每个报告数字必须 csv 核算 + bootstrap 95% CI + run_id/seed。复现 Dice 必须 per-image mean，不能 batch-aggregate（见 §3 口径）。
2. **所有数据只能从公开资源获取** —— MSD / ISIC / BUSI / CheXMask 公开下载，不联系作者要私有数据、不采集线下样本。
3. **复现数字不可与论文「凑」** —— 复现值 PASS/FAIL 以 §5 容差带判定；若复现不出，诚实记录 gap + 根因，绝不手调种子去「凑」论文数字。
4. **创新点不可伪造对比** —— baseline（UNet/nnUNet/原 Med-NCA）必须自己重跑或 cite-as-paper，不抄论文表格当自己结果。
5. **训练串行** —— 绝不同时启两个训练（本地或 HPC），必须等前一个完成。
6. **改 degradation / 预处理管线先验像素对齐** —— 大项目栽在裁剪 bug（降质图与原图像素错位逼模型 hallucinate）。任何 resize/crop/augment 改动后，先验 input↔GT 空间对齐再训。

---

## §2 跑偏定义（命中任意一条立即停手）

1. **开始全 8 数据集广度复现** —— 策略已定最小复现，8 数据集是陷阱（4-5 月沉没成本，顶会要 novelty 不要全复现）。
2. **凭论文 PDF 写架构数字** 而非读官方代码 `M3D-NCA-official/src/`（PDF 与代码已发现不符：见 §4 Sobel vs learned conv）。
3. **创新点选「工程优化」类**（量化/剪枝/换 backbone）当主卖点 —— 顶会要的是 method novelty 不是 engineering report。
4. **复现还没 PASS 就开始写创新代码** —— 没有可信 baseline，创新的 Δ 无意义。
5. **直接改官方代码原地训练** 而不 fork 隔离 —— 官方 repo 留作 ground-truth 对照，自己代码进独立目录。
6. **报 Dice 用 batch-aggregate 口径**（见 §3）当论文标准报法。

---

## §3 数字溯源纪律（指标口径统一）

大项目栽过「PSNR 两种口径差 4 dB」的坑。Med-NCA 主指标 Dice 同样要钉死口径：

| 口径 | 定义 | 用途 |
|---|---|---|
| **per-image Dice mean**（论文标准） | 每张图算 Dice → 对 N 张取均值 + std | **报告 / 验收唯一标准** |
| batch-aggregate Dice | 整 batch 的 TP/FP/FN 汇总后算一次 | 仅训练监控，禁止当报告值 |

**强制**：
- 每个复现/创新数字落 `results/<exp_id>.csv`（per-image 一行）+ bootstrap 1000× 95% CI + seed + git commit hash。
- 官方框架的 `getAverageDiceScore()` 先核对它是 per-image 还是 aggregate，不确定就自己重算一遍对齐。
- Pseudo-ensemble（10× 推理取平均）和单次推理 Dice 分开报，不混。

---

## §4 架构事实（已读官方代码核对，非凭 PDF）

> 来源：`M3D-NCA-official/src/models/`、`src/examples/train_Med_NCA.py`。**与 Plan.md PDF 推断的差异已标 ⚠️**。

### Med-NCA (2D) 真实结构
- **细胞状态**：`channel_n=16`（ch0=输入图，ch1..15 初始 0），grayscale `input_channels=1`。
- **感知 perceive**：
  - `BasicNCA` ⚠️ = **固定 Sobel x/y 滤波** + identity，concat 成 `channel_n*3=48` 维 → 非可学习卷积。
  - `BackboneNCA` = 可学习 conv 变体（创新对照可两者都试）。
- **更新规则**：fc0(48→128) → ReLU → fc1(128→16, **bias=False 且零初始化** → 初始 Δx=0 保稳定) → 随机 fire_mask(rate=0.5) → 残差 `x = x + Δx*mask`，**前 input_channels 通道每步还原**（不被更新覆盖）。
- **两级**：coarse `16×16`（下采样）跑 64 步通信全局 → 上采样 → fine `64×64` 取 patch 跑 64 步，仅 patch 算 loss。（example 用 `input_size=[(16,16),(64,64)]`，论文高分辨率用 256→64 patch，按数据调。）

### 真实超参（example，非 PDF 表）
| 参数 | 值 | 备注 |
|---|---|---|
| lr | `16e-4` | ⚠️ PDF 未给具体值 |
| betas | `(0.5, 0.5)` | Adam，非默认 (0.9,0.999) |
| lr_gamma | 0.9999 | 每步衰减 |
| batch_size | 48 | |
| n_epoch | 1000 | |
| inference_steps | 64 | |
| fire_rate | 0.5 | |
| hidden_size | 128 | |
| loss | **DiceBCELoss** | ⚠️ PDF 说 Dice Focal；example 用 DiceBCE，需核对论文版 |
| data_split | 0.7 / 0 / 0.3 | train/val/test |

### M3D-NCA (3D)
- 3D conv k=7 替代 2D，n-level（Hippocampus=1, Prostate=2），batch duplication 稳定训练。步数 `s = max(W,H,D)/((k-1)/2)`。

---

## §5 量化验收（复现阶段 PASS/FAIL）

> 论文锁定 Dice（per-image mean）。容差带 = 论文值 ±0.02 算 PASS（NCA 随机性 + 数据 split 差异）。FAIL 必须 PROJECT_LOG 写 gap + 根因。

| ID | 任务 | 论文 Dice | PASS 阈值 | 维度 | 优先级 |
|---|---|---|---|---|---|
| **R1** | MRI Hippocampus (3D, MSD Task04) | ~0.882 | ≥0.86 | 3D 锚点 | 🥇 必做 |
| **R2** | 1 个 2D 数据集（建议 ISIC 皮肤 or Lung） | 皮肤~0.772 / Lung~0.941 | ±0.02 | 2D 锚点 | 🥇 必做 |
| **R3** | 参数量 < 100K | <10⁵ | 硬核对 | 轻量声明 | 🥇 必做 |
| **R4** | Pseudo-ensemble Dice > 单次 Dice | Δ>0 | CI 排除 0 | 质量度量基础 | 🥈 转创新前 |
| **R5** | NQM 方差与误差正相关 | ρ>0 显著 | p<0.05 | 创新可能用到 | 🥈 按需 |

**最小复现 = R1+R2+R3 全 PASS**。达成即冻结 baseline、转 §7 创新。R4/R5 视创新方向是否依赖再补。

---

## §6 路线图（最小复现 → 创新 → 投稿）

### Phase 0 — 环境 + 最小复现（目标 2-3 周）
**算力**：本地 Windows 调试通 → 3D（R1）上 HPC，2D（R2）本地或 HPC。

- [ ] **P0.1 环境**：`conda create -n mednca python=3.9` + 官方 requirements（注意 `torchio==0.18.82` 旧版，Windows 装可能要降 numpy；冲突则记录在 ENV_NOTES）。本地先 CPU 跑通 1 个 batch 验证代码路径。
- [ ] **P0.2 fork 隔离**：官方 `M3D-NCA-official/` 只读对照；自己工作目录 `code/`（改 config / 加 state.json / 加 per-image csv eval）。
- [ ] **P0.3 数据**：MSD Task04 Hippocampus（下载 ~ 几百 MB）。2D 选 ISIC 2018（公开直下，无需申请，避开 PadChest 申请周期）。
- [ ] **P0.4 R1 跑通**：Hippocampus 训练 → per-image Dice ≥0.86。HPC 训练用 paramiko + 脚本自写 `state.json`（大项目教训：loop 监控 context 压缩后断链，靠脚本自报状态才可靠）。本地 Start-Process 开窗 + arm Monitor。
- [ ] **P0.5 R2 跑通**：ISIC/Lung 2D → Dice ±0.02。
- [ ] **P0.6 R3**：打印 `sum(p.numel())` 核对 <100K。
- [ ] **P0.7 收口**：3 项 PASS → 写 PROJECT_LOG「baseline 冻结」+ 存 ckpt + csv。

### Phase 1 — 创新点锁定（目标 1 周，gate）
- [ ] **P1.1 选向**：从 §7 候选选 **1 个主创新 + 1 个备选**，写半页「为什么这个能打顶会」（novelty + 可证伪 + 1 句话故事）。
- [ ] **P1.2 可行性探针**：小实验（<1 天）验证创新方向有信号，再投入。无信号立即换备选。
- [ ] **P1.3 报用户 gate**：创新点 + 预期 Δ + 风险，等确认再进 Phase 2。

### Phase 2 — 创新实验（目标 4-8 周）
- [ ] 建 ACCEPTANCE 式 E-test（创新点的 PASS/FAIL 阈值，对标 §5 风格）
- [ ] baseline 对比（自跑 Med-NCA / UNet / nnUNet）+ 消融 + bootstrap CI
- [ ] 鲁棒性 / 跨数据集泛化（NCA 卖点：scale/translation 不变性、抗 artifact）

### Phase 3 — 投稿（目标 2-3 周）
- [ ] 选会 + deadline（候选：MICCAI / ISBI / WACV / NeurIPS Datasets&Benchmarks；待定）
- [ ] 跑 `/pre-submit-check`（数字溯源 + 图表验证 + 匿名化）
- [ ] `/validate-figures` 逐图核轴域/数字一致

---

## §7 创新方向候选（Phase 1 选型，待 gate）

来自 Plan.md §7 + NCA 文献，按「顶会 novelty 潜力」排序，**非工程优化类优先**：

| # | 方向 | 卖点 | 风险 | novelty |
|---|---|---|---|---|
| A | **动态步数 NCA**：按图像/区域复杂度自适应迭代步数（早停 emergent convergence） | 省算 + 理论可证（收敛判据） | 自适应判据难定 | 高 |
| B | **NQM 驱动 active learning / human-in-loop**：用 NCA 方差挑最该标注的样本 | 临床落地故事强 + 标注效率 | 需多轮标注实验 | 高 |
| C | **NCA 半/弱监督分割**：利用 emergent behavior 做少标注 | 数据高效，顶会爱 | 弱监督基线多，要打赢 | 中高 |
| D | **NCA + Foundation Model**：SAM/MedSAM 特征初始化 NCA 状态 | 蹭 FM 热度 + 轻量 | 可能变「调包」缺 novelty | 中 |
| E | NCA for 4D/视频医学图像（时间连续性） | 新场景 | 数据难找 | 中 |

> ⚠️ **避坑**：硬件量化/剪枝/树莓派实测（Plan.md §7.6）= 工程 report，**不选为主卖点**（§2 跑偏 #3）。

---

## §8 参考资料（从 Plan.md 保留，已核对）

### 仓库 / 论文
- 官方框架（已 clone 至 `M3D-NCA-official/`）：https://github.com/MECLabTUDA/M3D-NCA （Med-NCA 2D + M3D-NCA 3D 统一框架）
- Med-NCA IPMI 2023：https://arxiv.org/abs/2302.03473
- MED-NCA MedIA 2025（8 数据集 + NCA-VIS，本地有 PDF）
- Growing NCA 理论基础：https://distill.pub/2020/growing-ca/

### 数据集（最小复现只需 Task04 + ISIC）
| 任务 | 维度 | 源 | 备注 |
|---|---|---|---|
| Hippocampus | 3D MRI | MSD Task04 medicaldecathlon.com | R1 锚点，~195 样本 |
| ISIC 2018 皮肤 | 2D RGB | challenge.isic-archive.com | R2 候选，直下无需申请 |
| Lung X-ray | 2D | ChestX-ray8 + CheXMask | R2 备选，Dice 高易复现 |
| Prostate/Liver/Spleen | 3D | MSD Task05/03/09 | 仅创新需要时再下 |
| Breast BUSI | 2D 超声 | Kaggle aryashah2k | std 大(0.308)，不选锚点 |
| Heart | 2D | PadChest + CheXMask | ⚠️ PadChest 需申请，避开 |

---

## §9 工程血泪清单（大项目迁移，每次训练前扫一遍）

1. **训练串行**，绝不并发两个。
2. **HPC 训练脚本自写 `state.json`**（epoch/loss/dice/timestamp），不靠 loop 监控记忆。
3. **本地 Start-Process 开窗后立即 arm Monitor**，不只靠 ScheduleWakeup。
4. **Windows 训练规范**：DataLoader `num_workers` spawn 安全、路径用 raw string、`KMP_DUPLICATE_LIB_OK`、长下载/安装用 Start-Process 开新窗不后台。
5. **删临时文件用 PowerShell `Remove-Item`，绝不 `rm`**（权限白名单外会级联取消整批）。
6. **改预处理后先验像素对齐**（§1 红线 6）。
7. **指标口径**：报告值 per-image，监控值 aggregate，不混（§3）。
8. **装 CUDA torch 前先 `df -h` 看盘**：cu118 wheel ~2.5GB，conda env 默认在 C 盘；C 盘 <6GB 必先把 env 建到 D 盘（`conda create -p D:\...\envs\mednca`）或腾空间。会话 1 在此栽过（`[Errno 28] No space left`，C 盘仅 2.3GB）。
9. **重训前必清 model_path 目录**：官方 `Experiment.reload()`(Experiment.py:82) 启动时若目录存在 `config.dt` 就**整个覆盖运行时 config**，`n_epoch` 被旧值锁死、env 变量静默失效。会话 3 栽过（连两次「300/1000ep」实际只训 ~8 epoch）。`Remove-Item -Recurse checkpoints/<exp>` 后再训。注意：summary 里 `epochs` 字段是 python 变量照抄，**不能当真实训练轮数**，真实轮数 = `range(currentStep, get_max_steps()+1)`。
10. **NCA 训练慢的真因是计算密集非数据**：64 步顺序推理×N 级不可并行，GPU 利用率低时先别急着怪 DataLoader。`Model_BasicNCA.update:71` 的 fire-mask `torch.rand` 默认 CPU 生成再 `.to(device)`，每步一次同步停顿 → 用 `code/fast_nca.py` 的 device-rand subclass 修（数学等价，不改官方）。修后 GPU 满载但仍 60-90s/epoch（4070 Laptop），1000ep ≈ 20h，属正常成本。
11. **本地单 GPU 上绝不并发第二个训练/推理 job**。会话 4 栽过：R1（Hippocampus）在本地 4070（8GB）跑到 ep72 时，为「并行」启了 R2 smoke，GPU 显存一度逼近满（7869/8188 MiB）；随后 `Stop-Process` 杀 smoke 的控制事件波及 R1 进程，触发 Intel MKL 的 `forrtl: error ... window-CLOSE event`（KERNELBASE/KERNEL32/ntdll 栈），**R1 进程假活（CPU 近 0、已脱离 GPU）实则卡死**。损失 ep50~72，从 `epoch_50` ckpt resume 找回。教训：① 单卡训练期间不碰 GPU（第二个 job 走 HPC 或排队等第一个完）；② 进程假活看三件：GPU 显存是否仍占、`nvidia-smi --query-compute-apps` 里有没有该 pid、CPU 时间是否还在涨——log 冻结+脱离 GPU+CPU 不动 = 死，即便进程还在；③ 这正是 §1 红线 5「训练串行」的物理依据，别只当纪律。

---

## §10 下一步（Phase 0 起手）

1. 建工作目录骨架（`code/` `configs/` `data/` `results/` `checkpoints/` + ENV_NOTES.md + PROJECT_LOG.md）
2. 装环境（本地 conda），CPU 跑通官方 1 batch 验证代码路径
3. 下 MSD Task04 Hippocampus
4. R1 训练（HPC）→ per-image Dice 核对

> **gate 提醒**：Phase 0 三项 PASS 前不碰创新代码。Phase 1 选向需报用户确认再进 Phase 2。
</content>
</invoke>
