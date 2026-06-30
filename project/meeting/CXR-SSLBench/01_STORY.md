# CXR-SSLBench — STORY（反跑偏主文）

> 读前提：本文是写作与实验的「不可偏离主线」。任何 tex/实验/claim 与本文冲突 → 停下澄清，不照临时描述硬干。
> 配套：`00_README.md`（入口）/ `02_ACCEPTANCE.md`（二元验收）/ 立项提案全文 `~/.claude/plans/ccf-c-vivid-yeti.md`。

## 一句话主张（reframe，零承重命门）

胸片自监督（SSL）范式选择**非单调最优，而是 regime 依赖**——最优范式随「标注量 × 域 × 病理 × probe/finetune」切换；把横评定位出的系统失败 regime 操作化成轻量 fix。

## 为什么这个形状（BMVC 易产形状，learnt from 死活对照）

参 [[feedback_benchmark_is_optimal_strategy]] + [[feedback_claim_shape_decides_birth_difficulty]]：A 族大胆 novelty 押命门全死（NCA-JEPA/PhaseMap/disagree/delta/MedAD），B 族 benchmark/empirical 全活（quantimmu/ArtiOOD/selinf）。本项目刻意做 **B 族**：
- **承重 claim 是经验发现，结果朝哪落都成立**（不押任何「方法必须涨」的未验前提）。
- 方法贡献是 **stretch / opt-in**，挂掉不动主贡献。

## 核心 Claim 分层

### 承重（C1–C4，主贡献，独立于方法成败）
- **C1 无单一最优（双向预登记）**：跨 5 范式无范式在所有 regime 通杀。**两向都 publishable**（受控重训前预登记）：洗牌存活=范式选择 regime 依赖；洗牌消失=野外 SSL 范式差距是语料/配方 artifact 非范式内禀。C1 不依赖强制 rank flip，承重摊 C1+C2+C3（pilot 100% top-3 极差仅 0.33 点、单 seed，别让单条小翻转扛大梁）。
- **C2 数据效率 gap**：范式间差距在 **1% 标注最大**、100% 收敛趋同；数据效率曲线（1/10/100%）量化。
- **C3 probe-finetune 解离**：世界模型（CheXWorld/JEPA）**linear-probe 偏弱**、finetune/attentive 追回——表征好坏与 probe 协议强耦合，单一 probe 结论会误导。
- **C4 跨域退化因范式而异**：NIH→VinDr/CheXpert 跨域掉点幅度按范式分化，无统一鲁棒冠军。

### stretch（C5–C6，挂掉不影响主贡献）
- **C5 方法 fix 回收增益**：CPF-Gate（逐病理跨范式特征门控融合）或 ReStat（源自由跨域特征统计重校准）在横评定位的 failure cell 上回收增益。
- **C6 鲁棒/校准 finding**：腐蚀曲线 + 罕见病理分层 + ECE 校准的反直觉经验定律。

## 章节弧（顶刊形态，venue 待 pilot 后拍）
1. **Intro**：SSL 范式爆发但选型靠拍脑袋；把「哪个 SSL 最好」证伪成「regime 依赖」，给 operational guidance。
2. **Related**：去 first 化（X-WIN arXiv 2511.14918 已抢「首次 WM 横评」）；差异化 = 最受控（同语料/backbone/预算重训）+ 数据效率曲线 + failure taxonomy + 方法 fix。
3. **Benchmark 设计**：5 范式 × 3 集 × 1/10/100% × {linear/attentive/knn + finetune} × 3–5 seed；统计 Friedman+CD+DeLong+Holm。
4. **C1–C4 经验发现**（主结果）。
5. **方法（CPF-Gate / ReStat）**：在 failure cell 上的 fix（C5，opt-in）。
6. **鲁棒性 + 校准**（C6）。
7. **结论 + operational guidance 表**。

## 防御写法 R-rules（写 tex 时强制）
- **R1 去 first**：禁写「首次纳入 world model 横评」（X-WIN 已抢）。一律「最受控 / 最系统 / 补 X-WIN 未做轴」。
- **R2 承重/stretch 分明**：方法章（C5/C6）措辞为「附加 fix」，禁让主贡献依赖方法涨点。
- **R3 数字零臆造**：所有表内数字来自 `results/*.csv`，入 tex 前过 verifier（Bash 核 csv，不信 Read）。参 [[feedback_verify_paper_numbers]]。
- **R4 超参零臆想**：MAE/DINO/MoCo-v3 ViT-B 配方派 researcher 查官方源，查不到标 TODO，绝不照搬别库。参 [[feedback_no_hallucinate_settings]] / [[feedback_repro_zero_deviation]]。
- **R5 无泄漏**：probe/test 患者级 disjoint（NIH splits 已患者 0 重叠）；跨域评估禁拼训练集；汇报数字确认 held-out。参 [[feedback_no_default_downgrade]] 反面纪律。
- **R6 预登记 failure cell**：全评估矩阵跑完后**先冻结** failure cell 定义再做方法，防 HARKing（事后挑对方法有利的 cell）。

## 不得碰 / 红线
- 不为「方法必须涨」改 benchmark 设计或挑 cell（违 R2/R6）。
- 复现零偏离：5 范式同数据/backbone/预算受控重训，禁私加裁剪/降 lr/改步数凑收敛。
- HPC 传新数据/新代码 = 拍板点，先报。
