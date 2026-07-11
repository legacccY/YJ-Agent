# NCA-Cyst — 验收判据（唯一真源）

> 二元 PASS/FAIL，不存在「基本完成」。半天级大阶段完成跑 `/stage-gate`。
> 动 coder 前 git commit 冻结本文（防 HARKing）。

---

## 当前生效判据块（Phase 1 baseline，2026-07-08）

本期只验「管线活着 + 建立诚实 baseline 对照」，**不验创新**（创新模块下阶段立项）。

### A1 — 官方二分类管线复现（Phase 1a）
- **判据**：官方 config（`label[label>0]=1`）在 KiTS23 跑通，loss 从 ~1.25 **下降**（非卡 5.0），验证 Dice > 0，无报错。
- **阈值**：本地小样本烟测通过 + HPC 全量至少 1 个 seed 收敛（不发散跑到目标 epoch）。
- **状态**：✅ PASS（2026-07-10 gate）— 烟测通过 + binary_all seed0 Dice 0.8313 / loss 0.1417 / 1000ep done，越过「高分辨率 3D 历史 0/11 全发散」命门。

### A2 — M3D-NCA 囊肿 Dice（Phase 1b）
- **判据**：`label=(label==3)` 囊肿二分类，M3D-NCA 出**多 seed（≥3）** 囊肿 Dice，报收敛率 + 均值±std。
- **阈值**：无预设「必须多高」——baseline 是**测量**不是达标。诚实报数，与文献 0.17–0.45 对照定位。
- **状态**：✅ PASS（2026-07-10 gate）— seed0/1/2 = 5.80e-6/4.63e-6/5.47e-6，收敛率 3/3，均值 5.30e-6±6.05e-7，均 1000ep done。测量完成（Dice≈0 是结果非成绩）。

### A3 — UNet3D 同口径对照（Phase 1c）
- **判据**：同 split / 同预处理 / 同评估，UNet3D 出囊肿 Dice，与 M3D-NCA 同表。
- **阈值**：无预设。诚实：若 UNet 没那么差，如实报，不为故事硬压。
- **状态**：✅ PASS（2026-07-10 gate，conditional）— UNet3D seed0 Dice 2.31e-7 / loss 0.5486 / TIMEOUT ep903。K3 不触发（≈0 近随机，故事前提成立）。⚠️ **投稿前 must-fix**：补 ≥3 seed + 1000ep 严格同口径 + 修 tqdm 保留 trace（当前单 seed/未跑完/轨迹丢失，审稿人可质疑对称性）。

---

## 评估口径（关键，基于本期囊肿分布实测）

实测（`06_experiments/kits23_cyst_dist.csv`，489 例全扫）：
- **248 例含囊肿（label==3），241 例无囊肿**（近五五开）。
- 囊肿体素占比：中位 **6.5e-05**（百万分之 65）、最大 1.2%、最小 4.2e-07 → **极端类不平衡**（近随机的机理根因）。

**口径决策（Phase 1b）**：
1. **囊肿 Dice 主指标 = 在含囊肿的 test case 上算**（GT 有囊肿才有 Dice 定义），遵循 KiTS 惯例，用官方 `kits23_compute_metrics` 对齐。
2. **无囊肿 case 单独报假阳性率 / 体素级 FP**（模型在没囊肿的肾上乱标多少），作为鲁棒性副指标。
3. split 仍用官方 `[0.7,0,0.3]`，但**报「test 集里含囊肿 case 数」**，避免分母含糊。
4. ⚠️ 中位囊肿仅 65/百万体素——在下采样到 (320,320,24) 时可能被抹掉。若 M3D-NCA 囊肿 Dice 极低，**先核是不是下采样丢了目标**（这正是我们全局视野论点的伏笔，但 baseline 阶段只诚实记录不 claim）。

---

## Decision Gates（预定义自动触发，防白烧 GPU）

| 条件 | 行动 |
|---|---|
| ep10 后 loss>3 且 Dice<0.05 | 静默发散 → 立即 scancel，记 seed，换 seed 重试 |
| 任何 epoch loss 突增到 >3 | NCA 无安全期崩溃 → 记录，判收敛率 |
| 推理步数 ≠ 训练步数 | 禁止（NCA 非 over-step-stable） |
| 单 seed 发散 | 不判死方法，报多 seed 收敛率（生死由 epoch1 GPU 随机性掷定） |

---

## 书面 kill criteria（触发即诚实回退，不硬撑）

- **K1**：M3D-NCA 官方 config 在 KiTS23 多 seed **全发散**（重演前列腺 0/11）→ 停下报，考虑（a）降分辨率作受控变量讨论（需拍板）/（b）换更小 patch 官方支持配置 / （c）诚实记录 NCA 在此数据不收敛，重估方向。**不私自改超参凑收敛。**
- **K2**：数据适配后 label 分布异常（如囊肿全丢）→ 停下查预处理，不带病训练。
- **K3**：UNet 对照若在囊肿上**并不近随机**（Dice 显著 >0.45）→ 故事前提动摇，停下报拍板，可能需收窄 claim 或换设定。

---

## 复现红线（零偏离官方 M3D-NCA）

- 禁私加梯度裁剪 / 降 lr / 改步数 / 换实现 / 提速 subclass 凑收敛。
- 官方超参逐值照抄（见 `00_README` / 计划书），改动只限数据路径 + label 模式开关。
- 数字一律 Bash/Grep 核 csv，不信 Read。
- 护原始 KiTS23 数据，扁平化用派生不动原始。

---

## 雄心档位

- **中等会议线（本期够用）**：M3D-NCA + UNet baseline 在 KiTS23 囊肿上的诚实对照 + 管线可复现。
- **standout 升级线（下阶段）**：全局视野模块把囊肿 Dice 从近随机显著拉起（需另立项 + 红队）。

---

## Phase 2 立项前 kill-shot 判据（预注册，防 HARKing｜草稿待 git commit 冻结）

> 目的=**因果区分** baseline 囊肿 Dice≈0 到底是「极端类不平衡（H2b，一阶）」还是「缺全局视野（H2a）」。双红队（skeptic+theorist）判 H2 命门存疑，用户拍板「先跑 2×2 kill-shot 再定 Phase2」。planner 设计→skeptic 红队砸中致命伤（CB 欠力假阴性）→本块固化修复。**跑 b 前须 git commit 本块冻结**（呼应 [[feedback_falsify_crux_first]] + [[feedback_validate_test_before_negative_verdict]]）。

### 实验矩阵 2×2 = `--global_view {off,on}` × `--class_balance {off,on}`

| 格 | GV | CB | 内容 | 状态 |
|---|---|---|---|---|
| **a** | off | off | vanilla M3D-NCA cyst（官方 DiceFocalLoss，实测 focal 项退化成 BCE=无有效类平衡）| = A2 复用，anchor **5.30e-6±6.05e-7**（3seed）|
| **b** | off | on | **关键格**：vanilla NCA + **CB-max 堆栈**，仍 −全局视野 | Stage1 先跑（决定 kill）|
| **c** | on | off | +全局视野模块，官方损失 | Stage2 条件跑（仅 b 失败才跑）|
| **d** | on | on | +全局视野 + CB-max | Stage2 条件跑 |

**分阶段执行**：Stage1 先跑 b（3seed，~36 GPU·h，**无须实现 GV 模块**）。b≥kill 线 → 止步报拍板；b 仍≈0 → 过 novelty gate 后实现 GV 跑 c/d。

### CB-max 堆栈（skeptic 致命伤修复：给 CB「最强合理形态」，否则 b 假阴性）

实测佐证（`06_experiments/kits23_cyst_dist.csv`，248 含囊肿 case）：囊肿绝对体素中位 **2317**（p25=585/min=17），细级 patch (128,128,64)=1.05M 体素 → 整颗中位囊肿落入 patch 内占比也仅 **~0.22% ≪ 文献有效区间 1–5%**。故 CB 须三组件叠满把 patch 内前景占比顶进有效区间：

1. **囊肿中心裁剪**：patch 以囊肿 bbox 为中心 / patch 尺寸缩到囊肿量级，目标 patch 内前景占比 **≥1%**（核心组件，最该补）。
2. **copy-paste / lesion oversampling 增广**：复制囊肿体素抬高前景占比。
3. **极端 Tversky loss**（β≫α 重罚 FN，如 w_FN=0.7/w_FP=0.3 起，可加码到 0.9/0.1），不改官方 loss，本项目 code/ 新写。

> **铁律**：只有**最强 CB（CB-max）的 b 仍 <0.05** 才可 claim「非 CB 问题」。跑弱 CB 的 b = 埋假阳性 greenlight 雷。CB/GV 均为**受控自变量**，`--class_balance off / --global_view off` 时零偏离官方（保 a/baseline 可比），代码注释诚实标注「偏离官方的受控变量」。

### 判据（改绝对亮线为「相对效应量 + 3seed CI + 全格 ordering」）

含囊肿 test case 上 3seed 均值 Dice（官方 `kits23_compute_metrics`，同 split [0.7,0,0.3]、同 seed {0,1,2}）：

| 分支 | 触发条件 | 结论 → 行动 |
|---|---|---|
| **🔴 H2 塌（kill，稳健无需修复即可采信）** | **b ≥ 0.10**（CB-max 单独就逃出 ≈0，−GV）| 类不平衡一阶主因、全局视野非必要 → **Phase2 转向**（如「散布小目标类不平衡分割 benchmark」B 族路线）→ 停下报拍板 |
| **🟢 H2 站得住（greenlight）** | **b < 0.05** 且 **d ≥ 0.10** 且 **d − max(b,c) ≥ 0.10**（3seed CI 不重叠）| CB-max 单独救不动、须叠 GV 才拉起 → GV 是 enabler → greenlight Phase2（守整卷 GV scope）|
| **🟡 暧昧/死区** | 0.05 ≤ b < 0.10；或全格 <0.10（含天花板压制）；或 d 效应但 b 也部分抬 | 停下报拍板。**预注册：全格 ≈0 = inconclusive = 默认不立项**（保守失败安全，别读成「H2 没被杀死→推进」）|

**因果读法**：Δ_CB(−GV)=b−a（CB 单独效应）｜Δ_GV(−CB)=c−a（红队预测≈0，粗级已有整卷全局却仍≈0 的直接检验）｜Δ_GV(+CB)=d−b（GV 边际增益=是否 enabler）。GV 真 enabler ⟺ b≈a 且 Δ_GV(+CB) 大；CB 一阶主因 ⟺ Δ_CB(−GV) 大。**0.10 绝对线仅作参考锚，主判据=跨 seed CI 分离 + ordering**（seed 锁不住 NCA，报收敛率+均值±std）。

### 前置 gate（防跑偏）

- **G-freeze**：跑 b 前 git commit 冻结本块（防 HARKing）。
- **G-novelty**（仅 c/d 前触发）：实现 GV 花 GPU 前派 researcher 二次核「全图 pooling→broadcast NCA 分割」novelty（当前 negative-evidence 空白，须人工过 arXiv NCA 全表 + OpenReview）。撞车 → c/d 不跑、Phase2 转向。
- **G-GVscope**（仅 c/d 前）：GV 池化范围须对齐 H2 claim 的**整卷**尺度（非仅 patch-global proxy），否则 c/d 的 null 是假阴性、正结果也不验整卷 GV；若只做 patch-scope 须显式收窄 claim。
- **eval 对齐**：a（=A2 复用）与 b 须同 eval harness；若 A2 评估口径与 b 不完全一致 → 重跑 a 并列。

---

## Phase 2-C 判据（方向 C：3D NCA 不确定性 × 囊肿｜草稿，待 b 格确认地基后 git-freeze）

> 用户 2026-07-11 拍板方向转向 C。权威叙事=`THEORY_LEDGER.md` H4。planner 设计 + skeptic 红队 + researcher 校准三方整合。**git-freeze 时点=b 格出结果、确认囊肿 Dice 拉离 0 之后、pilot 跑之前**（防 HARKing）。

### 🔴 地基前置（skeptic 预注册，先于一切）
- **C 挂在「b 格 CB-max 把囊肿 Dice 拉离 0（部分召回）」上**。b 格对方向 A=墓碑（Dice≥0.10→类不平衡一阶主因→A 死），对 C=地基（部分召回模型让不确定性有实质可谈）。
- **stop 条件**：b 格全 seed 仍 Dice<~0.05（拉不动）→ C 无底物（零召回模型的 rollout 方差反映通用纹理/边缘非囊肿位置，评测协议退化）→ **预定义 stop，A 与 C 同时失实质 → Phase2 整体重估，停下报拍板**。

### RQ + 判据（planner 4 RQ + skeptic 扩充）
| RQ | 判据 |
|---|---|
| RQ1（命门 pilot，最先跑，~2-6 GPU·h 纯推理）| 三条**同时**过：① 方差图对漏检囊肿 failure-detection **AUPRC 显著 > 强度/边缘 baseline**（证方差囊肿特异非通用纹理）；② 选定模型上 AURC/selective-Dice **非退化**（有真阳性可排序）；③ 至少一校准指标在**囊肿正体素子集**有定义（非背景稀释）。|
| RQ2（vanilla 弱则救）| resilience 式扰动(σ=0.02,12步,1−IoU)/多尺度聚合/TTA 至少一种 cyst-prong AUPRC 显著 > vanilla+single-rollout（3seed CI 不重叠）|
| RQ3（校准+决策）| Prong A 肾 ROI ECE≤阈 + retention 单调；Prong B case-level「有无漏检囊肿」flag AUROC≥0.70 |
| RQ4（承重 delta·多尺度）| 粗级(m=0,囊肿被抹掉)vs 细级(m=1) 不确定性行为系统差异（Wilcoxon p<0.05）+ 方向可解释（联动 H1）——2D 单尺度竞品结构上碰不到 |

### 双 prong eval（planner，防零召回退化）
- **Prong A**（肾/瘤，模型能干）：AURC/ΔDice@90/ECE/retention——证不确定性机制健全。
- **Prong B**（囊肿，delta 承重）：不做选择性分割，做漏检定位 failure-detection **AUPRC**（类不平衡最有信息）。

### 校准要点（researcher，替换 planner 占位）
- **σ 地板阈 = 数据驱动**：本地 vanilla rollout 实测背景 σ 分位数，**不用硬编码 1e-3**（NQM 论文不报 std 绝对量级）。pilot 先测全脏器 vs 囊肿带 σ 直方图。
- **NQM 口径对齐**：N=10 rollout voxel std，面积归一 NQM=Σstd/Σmean（arxiv 2309.02954）。
- **指标库复用**：AURC=TorchUncertainty `metrics.classification.AURC` + resilience repo `evaluate_uncertainty.py`（含 AURC/AUROC/AUPRC）；AUSE/分割 ECE 无现成库→按 Ilg 2018 自实现（勿自造口径）。

### baseline（skeptic：必对照标准 UQ 不只 resilience）
- 3-seed deep ensemble（**已有 seed0/1/2，免费 epistemic 强基线**）+ MC-dropout/TTA + resilience(2D 移植 3D) 对照。真优势=零成本多 rollout 不改架构 + 首次测极端不平衡近零召回区制，**非 NCA 骨干本身**。
- ⚠️ **TODO researcher**（第 4 条，agent 完成后补）：核「KiTS/肾囊肿 MC-dropout UQ」空白真伪。
- MC-dropout 需训 dropout 变体=破零偏离→**拍板点，默认不做**。

### venue
UNSURE workshop（吃 benchmark/UQ framing、不要 Dice SOTA、接受率 65-71%）为主；MIDL/MELBA 上探。摆 B 族 benchmark 形状，不 claim 方法 novelty。博士生+导师定。
