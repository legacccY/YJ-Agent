# R2 复现报告 — Med-NCA on MSD Task05 Prostate

**任务**：复现 Med-NCA（2D slice-wise NCA）在 MSD Task05 Prostate 3D MRI 分割上的 Dice，作为「NCA baseline 可信」最小复现锚点的第二项（R2 = Prostate）。
**结论**：🟡 **部分复现 / 未达标（FAIL）但非崩溃** — 官方原版 per-volume Dice **0.672 ± 0.148**（n=9，301 epoch），未达论文 0.838，但**模型正常学会分割**（推翻会话 6 fast 版的 0.0 全背景发散）。最小复现地基 R2 锚点 **未 PASS**，但 gap 已诚实归因（见 §3.2）。
**日期**：2026-06-04（会话 7 训练）/ 2026-06-05（会话 8 回填）｜**seed** 42 ｜**HPC job** 1435378（官方原版）/ 1435267（旧 fast 版，作废）

---

## 1. 设置（官方原版，零偏离 — 守 REPRO_PLAN §1#8）

| 项 | 值 | 来源 |
|---|---|---|
| 框架 | 官方 `M3D-NCA-official`（MECLabTUDA），只读对照 | github.com/MECLabTUDA/M3D-NCA |
| 模型 | **官方原版 `BackboneNCA`**（非 fast subclass），2-stage（coarse 64×64 → fine 256×256），各 64 推理步 | `train_Med_NCA.ipynb` cell-5 |
| channel_n | **32**（hippocampus 为 16） | `train_Med_NCA.ipynb` cell-5 |
| input_size | coarse `(64,64)` / fine `(256,256)` | notebook cell-5 |
| lr / betas / lr_gamma | **16e-4** / **(0.5, 0.5)** / 0.9999 | 官方 example（同 R1） |
| 梯度裁剪 | **无**（官方无裁剪，零偏离禁加） | 论文 + 官方码实证 |
| batch_size | **20** | notebook cell-5 |
| loss | DiceBCELoss | 官方框架标准 |
| inference_steps | **64** | 官方 example |
| 训练轮数 | **301 epoch**（论文 1000） | HPC job 1435378 ckpt epoch_50..300 |
| 输入模态 | **单模态 T2（img[..., 0]）**，忽略 ADC | 官方 `Dataset_3D.py:51` 强制取 channel0（非我方偏离） |
| 标签 | **整腺二值（label > 0 → 1）**，不区分 PZ/TZ | 官方 `Dataset_3D.py:56-57` |
| 数据 split | 0.7 / 0 / 0.3 = **23 train / 9 test**（共 32 例 MSD 标准） | split seed 42 固化 |
| 切片轴向 | z 轴（轴位，`slice=2`） | notebook 默认；与 R1 相同 |

**ckpt**：`checkpoints/r2_prostate/models/epoch_300/`（HPC，model0/model1.pth），ckpt 时间戳 epoch_50(11:40)→epoch_300(13:59) 按 ~28min 间隔递增，**真训 301ep 实锤**（非 config.dt 假轮数）。
**训练耗时**：HPC gpu4090，job 1435378 elapsed **02:50:26**（11:11→14:02）。
**eval 脚本**：`code/run_r2_prostate.py`（含 eval 模式），eval 用相同 data_split.dt 固化 test split（9 例）。

---

## 2. 论文靶子与 PASS 判据

> 来源：Med-NCA IPMI 2023，arXiv:2302.03473，**Table 1**

| 方法 | Prostate Dice | std |
|---|---|---|
| **Med-NCA（论文）** | **0.838** | 0.083 |
| UNet Baseline | 0.799 | 0.099 |

**PASS 判据（满足其一即算通过）**：
- **条件 A**：bootstrap 1000× 95% CI 含 0.838
- **条件 B**：点估 ≥ 0.81 **且** > UNet 基线 0.799

评测口径：per-volume mean Dice（每例取一个 Dice → n=9 取均值），**非 batch-aggregate**（守 §3 红线）。

---

## 3. 结果

### 3.1 官方原版结果（per-volume Dice，论文标准口径）

> 口径：每个 test 体积算一个 Dice → 9 个取均值 + std + bootstrap 1000× 95% CI。

| 指标 | n | Dice mean | std | 95% CI | 判据 A（CI含0.838）| 判据 B（≥0.81 且 >0.799）| 判定 |
|---|---|---|---|---|---|---|---|
| **R2 single**（单次推理） | 9 | **0.672** | 0.148 | [0.575, 0.765] | ✗ | ✗ | 🟡 FAIL |
| **R2 pseudo10**（10× ensemble） | 9 | **0.686** | 0.143 | [0.595, 0.777] | ✗ | ✗ | 🟡 FAIL |

明细：`results/r2_prostate_single.csv`、`results/r2_prostate_pseudo10.csv`（每体积一行 + seed）。

**对标论文**：Med-NCA Prostate 0.838 ± 0.083；UNet 0.799。**gap = −0.166**（single）。
**ensemble 方向成立**：pseudo10 (0.686) > single (0.672)，Δ+0.014，与 R1 一致（NCA 随机推理 → ensemble 小幅增益）。

### 3.2 gap 诚实归因（守红线 §1#3，不调参凑数）

R2 官方原版 **0.672 未达论文 0.838**，gap −0.166。诚实候选归因（按可能性排序，均不构成「凑数」修改）：

1. **训练轮数 301 vs 论文 1000**（最可能）：与 R1 同向 —— R1 300ep 得 0.866 vs 论文 0.882（gap −0.016）。prostate 配置更激进（ch32/256²），收敛更慢，301ep 大概率欠训。**若延至 1000ep 可能显著缩小 gap，但属正常复现成本非偏离**。
2. **n=9 test 小样本高方差**：std 0.148（hippocampus 0.033 的 4.5×），CI 宽 [0.575, 0.765]。9 例里单例异常即大幅拉低均值。论文 std 0.083 亦印证 prostate 本身高方差。
3. **data split 随机性**：32 例仅 23 train / 9 test，split seed 不同可致数 % 波动；论文具体 split 未公开。
4. **单模态 T2（弃 ADC）**：官方框架 `Dataset_3D.py` 本身丢 ADC（代码实证，非我方偏离），但论文 Table 1 是否用双模态未明确 → 列为待核查项，**不擅自改代码加 ADC**（守零偏离）。

> **判定**：R2 锚点 **未 PASS**，诚实记 gap + 归因。**不靠延长 epoch/换 split/加模态去凑 0.838**（除非作者批准延至官方 1000ep 这一非偏离动作）。

---

## 4. ★ 关键复现发现：NCA 训练对实现细节（RNG 流）极端敏感

> 本节是本复现研究**最有价值的发现**，对 NCA 复现社区有 caveat 意义。

**现象对照**（同一官方 prostate 配置，唯一差异 = fire-mask RNG 来源）：

| 实现 | fire-mask `torch.rand` 位置 | 数学等价？ | Prostate Dice | 结果 |
|---|---|---|---|---|
| 我方 `FastBackboneNCA`（job 1435267）| GPU 直接生成（提速，省 CPU→GPU 同步） | ✅ 仍 Bernoulli(0.5) | **0.0** | logits 爆 -1e9 → 全背景发散 |
| 官方原版 `BackboneNCA`（job 1435378）| CPU 生成再 `.to(device)` | — | **0.672** | 正常收敛 |

**机理**：fire-mask 每步对每个 cell 以 50% 概率更新（随机 dropout 式稳定化）。把 `torch.rand` 从 CPU 挪到 GPU 虽数学等价（同分布），但**改变了 RNG 流 → 随机 fire-mask 序列不同 → 训练轨迹不同**。Hippocampus（ch16/64²，温和配置）两版都收敛；Prostate（ch32/256²/64步，处数值稳定边缘）下，fast 版的 mask 序列把 NCA 状态推向爆炸，官方版的 CPU-rand 序列恰好稳定。

**实证链**（会话 7 揪出）：
- 官方溯源：prostate = steps64/ch32/256²/lr16e-4/无裁剪 = 我方一字不差 → 配置忠实，非配置错。
- diff 两 repo 源码（batch_step / BasicNCA / BackboneNCA）逐字相同 → 非 repo 差异。
- 忠实 smoke（job 1435372，官方原版）loss ep1=1.25→ep5=1.01、Dice@5ep=0.33（fast 同点 0.0）→ 真凶坐实。

**复现 caveat（报告级结论）**：NCA 的迭代式更新对随机性来源高度敏感，**任何「数学等价」的工程提速（改 RNG 设备/顺序）都可能在临界配置下破坏复现**。复现 NCA 必须用官方原版随机路径，提速版仅可用于已验证收敛后的下游。→ 这也是 REPRO_PLAN §1#8「零偏离」红线的实证依据。

---

## 5. 配套验收项

| ID | 项 | 结果 | 阈值 | 判定 | 文件 |
|---|---|---|---|---|---|
| **R3** | 参数量轻量声明 | **70,016**（channel_n=32，2-stage 各 35,008） | < 100K | ✅ PASS | — |
| **R4** | pseudo-ensemble Dice > single | mean_diff **+0.014**（0.686 vs 0.672）| Δ > 0 | ✅ 方向成立 | `r2_prostate_*_summary.json` |
| **Efficiency D2** | 四件套 | params 70,016 / peak_mem 121.6MB / 173.6ms per slice / ~310 GMACs | 见 json | ✅ 已测 | `results/r2_efficiency.json` |

---

## 6. 复现可信性 checklist（守红线）

- [x] per-volume 口径（非 aggregate）— §3
- [x] bootstrap 1000× 95% CI — §1 红线 1
- [x] seed 固定（42）+ HPC job ID 记录
- [x] test split 由 data_split.dt 固化，eval 与训练同 split
- [x] 数字未与论文「凑」：诚实记 gap −0.166 + 四项归因（§3.2）
- [x] 用官方框架自跑，非抄论文表格
- [x] 真训实锤：ckpt 按 ~28min 间隔 epoch_50→300 递增，非 config.dt 假轮数
- [x] **零偏离**：官方原版 `BackboneNCA` + 无裁剪 + 官方超参一字不差（§1#8）

---

## 7. 已知坑 / 注意事项

1. **★ fast subclass RNG 陷阱**（本报告 §4，最重要）：数学等价的提速 subclass 因改 RNG 流，在 prostate 临界配置下致发散。复现一律用官方原版。
2. **config.dt 覆盖陷阱**（继承 R1）：重训前清 `model_path` 下旧 config.dt，否则 Experiment.reload() 静默覆盖 epoch 配置。HPC 提交脚本 `_hpc_r2full.py` 已含 `rm -rf checkpoints/r2_prostate` 清理。
3. **小样本 n=9 高方差**：bootstrap CI 宽 [0.575, 0.765]，单例异常对均值影响大。
4. **双模态原始数据**：MSD Task05 原始 `(H,W,Z,2)`（T2+ADC）；官方框架强制 `img[...,0]` 丢 ADC（代码实证）。

---

## 8. 复现环境

| 项 | HPC（主训练） |
|---|---|
| 机器 | XJTLU HPC gpu4090 节点 |
| GPU | RTX 4090 24GB |
| conda env | `yjcu124py310` |
| PyTorch | 2.x + cu124 |
| Python | 3.10 |
| Slurm job | **1435378**（官方原版 301ep，COMPLETED 02:50:26）｜1435267（fast 版，作废）|

---

## 9. 数字溯源

| 项 | 值 |
|---|---|
| 结果明细 CSV | `results/r2_prostate_single.csv`，`results/r2_prostate_pseudo10.csv`（会话 8 从 HPC 下载）|
| seed | 42 |
| HPC job ID | **1435378**（官方原版）｜1435267（fast 发散版，作废）|
| ckpt 路径（HPC） | `checkpoints/r2_prostate/models/epoch_300/` |
| eval 脚本 | `code/run_r2_prostate.py` |
| 数据路径（HPC） | `/gpfs/work/bio/jiayu2403/mednca/data/Task05_Prostate` |
| 数据下载脚本 | `code/download_task05.ps1` |
| 提交脚本 | `_hpc_r2full.py`（含清目录 + 官方原版 env） |

---

## 10. 结论

🟡 **R2 未达标（FAIL，0.672 vs 论文 0.838，gap −0.166）但非崩溃** + R3 ✅（70,016 <100K）+ Efficiency ✅ + R4 ✅ 方向成立。

- R2 官方原版**正常学会分割**（vs fast 版 0.0 全背景发散），gap 主因大概率欠训（301 vs 1000ep）+ n=9 小样本高方差。
- **★ 最有价值产出 = NCA 复现脆弱性发现**（§4）：数学等价提速改 RNG → prostate 0.672 崩到 0.0，坐实零偏离红线。
- **最小复现锚点**：R1 ✅（官方版 eval 中，fast 版 0.866 已 PASS）+ R3 ✅ + **R2 🟡 未达标**。
- 后续选项（作者决策）：① 接受 0.672 作为「诚实部分复现」写入报告；② 申请延至官方 1000ep 重训（非偏离）追平 gap。
