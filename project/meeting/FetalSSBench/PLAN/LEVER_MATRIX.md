# FetalSSBench — Lever Matrix（80% 信心总账）

> **目标命中率口径**：乐观路径 ~80%（FUGC 到位 + 规律3 加固 + 自适应显著 + 5 seed + 写作干净）。
> **现状基线**：~55-60%（Phase 1/2 已 PASS，但 FUGC 未到、规律3 有裂缝、自适应未做、仍 3 seed）。
> **口径声明（重要，与 BMVC 同）**：命中率 = **内部信心自评**，用于排优先级与暴露风险，**非 venue 真实接收率**。ACCV 2024 接收率 32.2%（CORE-B），WACV「benchmark 不以算法新颖度拒稿」。
> **80% 口径不动**（drift 契约）。
> **caveman OFF**：决策文件，完整书写。
> **最后更新**：2026-06-25（Phase 2 PASS 后）

---

## 🎯 Lever 分解表（满分 100）

| # | Lever | 目标版本 | 不达标扣分 | 当前状态 |
|---|---|---|---|---|
| **L1** | 覆盖广度 | 3 集 × 5 比例 × 5 方法 × ≥5 seed 全跑通 | 缺 FUGC −8 | 🟡 PASS（2 集 150 run 已跑满），缺 FUGC −8 待补；seed 仍 3 见 L4 |
| **L2** | 承重规律显著 + 可解释 | 规律3 Holm 后显著 + 机制立得住（高基线无 headroom / 难结构低基线 unlabeled 有信息） | 裂缝未堵 −10 | 🟡 PASS（Wilcoxon p=0.0468/MW p=0.0028）但有裂缝（PS 绝对均增益 −0.0117 微负；HDC 单集 FH 增益反 >PS）→ **−10 待加固**（见 STORY_REFINEMENT） |
| **L3** | 自适应阈值显著增益 | 难低区多数 setting 正 + Holm 显著 | ≈0 诚实 −6 | ⚪ **GRAY 实测(2026-06-26)**：PSFHS 承重 G1 难低区 ΔdicePS 中位 −0.0008/Wilcoxon p=0.42/Holm 全不显著 → 无稳定增量，诚实写「最优固定阈值已够」**−6**（预注册正负均报兑现，非失败）；招3 降「诚实负结果/可选附录」，承重不依赖它 |
| **L4** | 统计严谨 | ≥5 seed + bootstrap 95% CI + Holm 多重校正 | n=3 CI 宽 −5 | 🟡 现 3 seed，部分格 CI 宽功效有限 → 升 5 seed 待补，−5 |
| **L5** | 与 FUGC/HDC/ERSR 区分 | Related Work 显式切割段（本文 = 跨结构难度统一 benchmark + 阈值机制对照） | 撞车 −8 | ⬜ 待写（HDC CVPR2025 / FUGC 单任务 / ERSR JBHI25 dual-scoring 各有先例需切割） |
| **L6** | held-out 零泄漏 | 代码核 split 无交集（含 HC18 多视角不混 train/test） | 泄漏 −25 红线全废 | ✅ PASS（Phase 1 已核，HC18 779 主视角去多视角防泄漏） |
| **L7** | 数字三方对账 | csv ↔ tex ↔ registry 一致，verifier 过 | drift −12 | ⬜ 待做（写作期，对齐 Phase 4） |
| **L8** | 开源完整 | 代码 + split + config camera-ready 前公开 | dataset track 拒 −15 | ⬜ 待整理（harness/split/config 已在 repo，需规范化） |
| **L9** | 诚实 limitation | 绝对增益/n/FUGC 口径诚实，不夸大 | 夸大 −10 | 🟡 R4 已立框（绝对微负照实），待写成 Limitations 段 |
| **L10** | 图质量 | 5-6 图 + 数值与 csv 一致 + validate-figures 过 | 图错 −6 | 🟡 现 3 图（efficiency/ssl_gain/struct_asymmetry），补 2-3（adaptive_gain/closed_loop/regression 散点） |
| **L11** | motivation 说服力 | 标注成本（70s/张）+ 人员短缺 + 评测碎片化 | 弱 −3 | 🟡 佐证已备（ProPL 不含 PSFHS/FUGC、FUGC 单任务），待写成 Intro |
| **L12** | 叙事闭环 | 自适应在规律3 指明区兑现增益（诊断→处方→疗效） | 脱节 −7 | ⚪ **GRAY 实测**：疗效未兑现（SAT 增益≈0）→ 闭环「诊断→处方→疗效」断在疗效。**改叙事**：诊断（极端类不平衡）+ 处方（SAT）成立，但实测证「调好的固定阈值已捕获该 headroom，自适应不额外加分」=诚实负结果本身有信息量。承重不依赖闭环（招1+2 独立） |

---

## 📊 命中率推演

- **满分 100**（全 lever 达标）。
- **乐观路径 → ~80%**：FUGC 到位（解 L1 −8）+ 规律3 加固堵裂缝（解 L2 −10）+ 自适应显著（解 L3 −6）+ 升 5 seed（解 L4 −5）+ Related 切割（解 L5 −8）+ 写作干净（L9/L11 落地）。
- **现状基线 → ~55-60%**：L1/L2/L4/L5/L7/L8/L9/L10/L12 多项待补或带扣分。

> 命中率非线性叠加，上表扣分为风险权重示意，不做简单加减；实际以「乐观 ~80% / 现状 ~55-60%」两锚点 + 下方 Top3 风险定优先级。

---

## 🚨 剩余风险 Top 3

1. **规律3 被 HDC 反例攻塌**（L2，最承重）：HDC（CVPR2025）数据上 FH（高基线）增益反 > PS，与「低基线 → 增益大」方向不完全一致；且本文 PS 绝对均增益微负（−0.0117）。若审稿人抓「你的承重规律连绝对增益都没有」→ 规律3 塌 → 论文核心发现失血。**对策见 STORY_REFINEMENT（收窄 claim + 补 seed + 第三集 + 自适应闭环联动）。**
2. **FUGC 掉成双集**（L1）：FUGC 需申请，拿不到则 benchmark 从「3 集」降「2 集」，跨结构难度连续谱断在两点（PS/FH），易被批 cherry-pick。**对策：积极推进申请；拿不到则 R6 诚实双集，并用 PSFHS 双结构 + HC18 撑起难度梯度论证。**
3. ~~**自适应增益 ≈ 0**~~ → **已实测落定 GRAY（2026-06-26）**：Phase3 PSFHS 承重 G1 难低区 ΔdicePS 中位 −0.0008/p=0.42，SAT 无稳定增量。**已按预注册 GRAY 出口诚实处理**（L3 −6，招3 降可选附录，承重靠招1+2 独立）。**风险已实现并消化，不再是未知风险**——论文定位转「benchmark + 结构难度不对称」为唯一主轴，自适应阈值作「诚实负结果（调好固定阈值已够）」附录。**新 Top3 候补**：HC18/FUGC 若与 PSFHS 矛盾（待跑完核），或 5-seed 升级后规律3 显著性变化。

---

## 与 ACCEPTANCE / STORY 的映射

- L1/L6 ← Phase 1（benchmark 主干）；L2/L4 ← Phase 2（实证规律）；L3/L12 ← Phase 3（自适应增量）；L5/L7/L8/L9/L10/L11 ← Phase 4（写作+投稿）。
- L2 裂缝加固方案在 `STORY_REFINEMENT.md`（措辞改动 = 拍板点，未回写 01_STORY）。
- L3 实施细节在 `PHASE_3_ADAPTIVE_THRESHOLD.md`（新增阈值草案待用户冻结）。
