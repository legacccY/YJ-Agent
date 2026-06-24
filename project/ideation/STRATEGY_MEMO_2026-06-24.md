# 战略备忘：选题流水线为什么没出「能用的项目」+ 路 B 校准

> 2026-06-24。三路调研（项目坟场死因 / 流水线本身 / 外部 ACCV 门槛）复盘的结论。
> 核心结论一句话：**流水线没坏，是把最高成功率的路（benchmark/empirical）当成了「不算数的病」，反而一直追最低成功率的 A 族大胆题。**

---

## 一、三大发现

### 发现 1 — 死的全是「大胆 novelty 押命门」，活的全是 benchmark/empirical

把组合台所有项目的「死」和「活」摊开，一条线极干净：

| 状态 | 项目 | 策略类 | 死因（如死） |
|---|---|---|---|
| 💀 死/退 | NCA-JEPA | high-risk novelty | 三支柱全证伪，无有效方向 |
| 💀 死/退 | NCA-PhaseMap | high-risk novelty | Hippo PASS → BraTS 跨集全随机（PASS-local 冒充 PASS-general） |
| 💀 死/退 | DisagreePred | high-risk novelty | n=50 AUROC 0.71 → n=150 崩到 0.43（小样本假阳/回归均值） |
| 💀 死/退 | delta-statetrack | high-risk novelty | 「医学时序需状态追踪」结构性不存在 |
| 💀 退 | MedAD-FailMap | high-risk novelty | 命门跨集外推腿填不出，退守 MICCAI |
| 🟢 活 | quantimmu-bench | benchmark/工程台 | 在投 |
| 🟢 活 | ArtiOODBench | benchmark | 在投 NeurIPS D&B |
| 🟢 活 | SelInfBench | empirical/benchmark | 在投 BIBE |
| 📨 唯一投出 | BMVC | 窄+post-hoc 单模块+增量 | 18 issue 全应答 |

**死的全押 novelty + 未验命门，活的全是 benchmark。这是答案的核心。**

外部调研（1-4 GPU 本科生 / 小团队成功率，带引用）：

| 策略类 | 成功率 | 算力 | 命门风险 | 对小团队 |
|---|---|---|---|---|
| Benchmark / Dataset | ⭐⭐⭐⭐⭐ | 0-1 GPU | 无 | ✅ 最优 |
| Empirical / 复现+分析 | ⭐⭐⭐⭐ | 1-2 GPU | 低 | ✅ |
| Application（已有方法→新域） | ⭐⭐⭐⭐ | 2-4 GPU | 低 | ✅ |
| Incremental 小改进 | ⭐⭐⭐ | 3-4 GPU | 中 | ⚠️ |
| Novel idea（大胆新方法） | ⭐⭐ | 4+ GPU | 高 | ❌ |

死掉的项目全在最后一档（最低成功率），活着的全在最前两档（最高成功率）。

### 发现 2 — ACCV 级别 ≠ 需要 radical novelty

- ACCV = Tier-2 / CORE-B（CVPR/ICCV/ECCV 才是 A*）。2024 录取率 **32.2%**（839 投 270 收），实际比 BMVC（25.9%）、ECCV（27.9%）还高，投稿体量小约 10 倍。
- **不要求 SOTA，不要求 radical novelty**：WACV Application track 官方原话「It is OK not to have algorithmic novelty」；BMVC「Brave New Ideas」重创意轻指标。
- 「够发」最低线 ≈ **2-3 个数据集 + 4-6 个 baseline + 清晰 positioning + 可复现**。SOTA 平均 +2~5% 即可接收，不需 +10%。
- 最常见拒因里「实验不够 / 不可复现」对小团队**完全可避免**——benchmark/empirical 类天然满足。
- 余嘉的独有优势：生信背景 + 可能可得的医院/医学数据。医学影像在 ACCV/WACV/MICCAI 是高概率赛道（医疗数据隐私限制 → benchmark 严重缺，dataset/application 论文价值高）。

### 发现 3 — 流水线没缺闸，是目标校准内部矛盾

流水线（G0-G6 + R1-R10）已极成熟，且**已为坟场里的死法打了补丁**：

- **R9**（防假阴）：欠功效的 null（宽 CI / binary metric）不当死信号，不误杀顶会苗子。
- **R10**（2026-06-22 新加，防假阳）：PASS-local ≠ PASS-general；跨集/普适命门不准丢进 R7 书面 kill criteria 当 IOU 推到立项后——正是 nca-phasemap / disagree 跨集死法的修复。
- **R8**（2026-06-18）：**故意**保底强制晋级 ≥1-2 个 MAIN-tier(A 族) 苗子冲 CVPR/NeurIPS，理由写明是「只活 benchmark = 矫枉过正成另一种病」。

**矛盾点**：G0-G5 的下风险硬闸正确地把漏斗导向 benchmark（对余嘉约束 = 最优解），但 R8 又反过来强推 A 族冲顶会——而 A 族正是反复死的那类。**「benchmark 工厂」的恐惧，把最高成功率的路打成了「不算数」。** 用户感知「没一个能用」，根因正是没把 3 个活着的 benchmark 项目当真项目。

---

## 二、路 B 校准（已拍板 2026-06-24）

**定调**：benchmark / empirical / application 升为**主力策略**，目标 ACCV / WACV / MICCAI / NeurIPS D&B 二梯队（这些不要求 radical novelty，正是余嘉 1-4 GPU + 生信本科生约束下能稳出的档）。A 族大胆 novelty 降为**显式可选 side bet**，不再当主线、不再「保底强塞」。

**停止把 benchmark-only 当病——它是约束下的最优解。3 个活着的项目就是赢。**

R8 的 ceiling_tier 评分保留（诚实标 MAIN/FINDINGS/WORKSHOP 仍是有用信息），但「强制保底晋级 A 族苗子」从默认行为改为 **opt-in**：仅当该轮宪章显式开了 A 族赌注槽才保底。

---

## 三、可操作建议（路 B 主力策略落点）

按余嘉约束 + 生信优势，优先级：

1. **Dataset / Benchmark 论文**（最高成功率，算力最省）：新数据集或已有数据重标注/整理 + 初步 baseline 分析。医学/生信方向尤其有市场。
2. **Empirical study**（复现 + 深度分析）：清晰 research question（「为什么这些方法在 X 场景失效」）+ ≥4-5 baseline + ≥2-3 数据集 + 统计检验。
3. **Application 论文**（已有方法 → 新域/新数据）：投 WACV Application track，明确「系统创新 > 算法突破」。医院合作数据是大模型团队没有的优势。
4. A 族大胆 novelty：仅当宪章显式开 side-bet 槽时产，且 R8/R10 全程盯住命门——明知是高风险赌注，分开记账。

---

## 引用（外部调研）

- ACCV 2024 录取率：https://link.springer.com/content/pdf/10.1007/978-981-96-0885-0.pdf
- BMVC 2024 录取：https://bmvc2024.org/programme/accepted_papers/
- WACV 2026 Reviewer Guidelines（Application track 可无算法 novelty）：https://wacv.thecvf.com/Conferences/2026/ReviewerGuidelines
- CORE Ranking ACCV（B 类）：https://portal.core.edu.au/conf-ranks/167/
- CV 会议对比指南：https://labs.murfy.ai/cv-cvpr-iccv-eccv-wacv-bmvc-a-complete-conference-comparison-guide-185106
- 拒稿原因分析：https://paperpal.com/blog/researcher-resources/5-reasons-for-rejection-after-peer-review
- 医学影像 AI 缺陷（数据集论文价值）：https://arxiv.org/pdf/2505.04720
- 联邦学习医学影像综述：https://arxiv.org/pdf/2306.05980

> 配 [[feedback_claim_shape_decides_birth_difficulty]]（claim 形状定生死）+ [[feedback_falsify_crux_first]]（命门最先证伪）。本备忘是这两条 memory 在「策略类」层面的总账。
