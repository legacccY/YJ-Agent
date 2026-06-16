# MedAD-FailMap — STORY FRAMEWORK

> 项目核心叙事 + 贡献边界 + 反跑偏。任务与本文冲突 → 停下澄清，不照描述硬干。

## 一、核心 RQ（一句话）

**重建式医学异常检测的失败是否可预测？** 即：能否把「重建误差检不出异常」这件事，刻画成 anomaly 属性与正常集属性的**可外推函数**，从而对任意新图像/新方法 predict 其可靠性。

## 二、为什么这是 capability paper 而非刷 SOTA

不打「我的 AD 方法 AUROC 更高」。打「重建式 AD 这一整类方法**在哪片协变量空间必然失败**，且这个失败边界**可预测、可外推、可操作**」。贡献是 insight + 可操作判据，不是新方法——所以「标准做法配足数据也能做」这句反驳不到点（我们刻画的正是标准做法的边界）。

## 三、三大贡献（按承重排序）

| # | 贡献 | 为何 incumbent 给不出 |
|---|---|---|
| **①（主，novelty 承重）** | **协变量化失败边界 / failure phase diagram**：受控操纵病灶大小×对比度×纹理频率×解剖位置 + 正常集多样性，画出重建式 AD 失败的可外推相图（带边界线，不是聚合 AUROC） | AE4AD 是 mismatch **存在性定理**（不带协变量参数）；MedIAnomaly 是**聚合 benchmark**（不做协变量分层）——两者框架**结构上无协变量维度** |
| **②** | **per-image 可靠性判据**：给定一张新图，predict 重建式 AD 在它上靠不靠谱（reliability selector），借放射学 **conspicuity** 框架（lesion contrast/background complexity）当理论桥 | AE4AD 的存在性定理给不出「这张图上可不可信」的可操作物；conspicuity 桥从没人嫁接到 DL AD 失败建模 |
| **③** | **多方法对比失败边界**：不同 AD 方法（AE/VAE/MemAE/FAE/RD…）的失败边界在同一 phase space 下对比，揭示哪类方法在哪片协变量空间各自失效 | benchmark 只报「哪个方法平均更好」，不报「各方法的失败几何形状」 |

> **三假设（只训正常够 / 重建误差=异常 / 正常误差<病理误差）= 分析工具，不是标题、不是卖点。** 它们是切协变量边界的三把刀。Intro 第一句必须是「失败何时可预测」，不能是「我们证伪三假设」。

## 四、与 incumbent 的精确边界（防撞车红线）

**incumbent = HKUST Cai/Chen/Cheng**（这块地的 dominant group）：
- **MedIAnomaly**（MedIA'25）：7 集 30 方法 benchmark，描述性指出三假设「does not always hold, still unresolved」，**无受控协变量分层**，Section 5 自己挂为 open。
- **AE4AD**（MICCAI'24）：**纯理论**证伪假设②（重建目标≠AD 目标 mismatch）+ constructive（latent 熵 + dim≥D/2），只打一条假设。

**我们走正交轴**：协变量失败边界 + 可预测性。**绝不**把卖点压在「证伪假设」上（= AE4AD 实证延伸 = incremental 死法，与 MedSeg-UQ ★1「前人立理论桩你做实证延伸」同型）。

**邻近但未占满**（核实，留缝完整）：
- Lagogiannis TMI'24 / brain UAD benchmark（arXiv 2512.01534）：按 size/contrast **percentile 分层报 AUROC** = 定性 observation，**非 failure-as-function 建模、不可外推、无 phase boundary、无 per-image 判据**。
- Meissen eBioMedicine'24：**人口学** bias（sex/age/race vs 训练集比例），非 anomaly 属性协变量。
- conspicuity（AJR 1976 起）：放射学读片 signal-detection 框架，**从未迁移到 DL AD 失败建模**。

## 五、目标会场

- **主投**：ICLR / NeurIPS（analysis / capability / rethinking track 收这类「不刷 SOTA、给 insight」论文，先例 MediConfusion ICLR'25、OpenMIBOOD CVPR'25）。
- **退路**：MICCAI / MedIA（贴导师领域、算力低，不白做）。

## 六、反跑偏红线

1. 主轴永远=协变量失败边界 + 可预测性；三假设只作工具，跑偏到「证伪三假设」立即停。
2. 数字一律 Bash/Grep 核 csv 不信 Read；超参查官方源查不到标 TODO；复现零偏离。
3. 理论命题（conspicuity 桥、边界外推性）**先 reviewer 裁再落「已证」**。
4. capability paper：非劣不是目标，**可预测/可外推/可操作**是目标；别滑回刷 AUROC。
5. 抢发风险（HKUST 可能扩 AE4AD 到三假设）→ 紧凑、早 arXiv 占坑、守正交轴降低撞同一篇概率。

## 七、审稿人预对峙（精简）

| 攻击 | 回应 |
|---|---|
| 「AE4AD 已证伪假设②，你=实证延伸 incremental」 | 主轴是协变量失败边界（AE4AD 定理不带协变量参数，结构上给不出），三假设只是工具；我们的承重 novelty 是可外推相图 + per-image 判据，正交于 mismatch 存在性定理 |
| 「benchmark 已观察到小病灶难检」 | 那是聚合 percentile 观察（Lagogiannis/2512.01534），不可外推、无 per-image 判据；我们建可外推函数 + 在 held-out 数据集验证边界预测对了 |
| 「失败边界停在描述性，novelty thin」 | 必须升到**可预测 + 可外推**：phase diagram + 在 held-out 集验证「predict 失败」命中；不止「观察到失败随 X 变」 |
| 「follow HKUST group」 | 协变量轴是其 benchmark + 理论框架都没建模的维度，工作不能被归约成 AE4AD+ε |
| 「conspicuity 是老概念」 | 概念老，但**首次**把放射学 conspicuity 嫁接到 DL AD 失败建模做 per-image reliability，是跨框架桥不是旧概念复用 |
