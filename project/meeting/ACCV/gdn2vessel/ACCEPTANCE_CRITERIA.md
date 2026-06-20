# gdn2vessel 验收标准（顶会亮度目标分解）

**目标**：按 CVPR/ICCV/MICCAI 顶会亮度建，ACCV 2026 作保底。不设周期上限——**唯一推进条件 = 每阶段硬阈值全 PASS**，不赶 deadline 牺牲质量。
**最后更新**：2026-06-20

> 完成判定铁律：**不存在「基本完成」「差不多了」。要么逐条全 PASS，要么继续补。** 任一 FAIL → 不标完成，回去补；非硬伤无解 → 写诚实回退 + 停下报用户（stage-gate FAIL 放行是拍板点）。

---

## 🎯 录用亮度 lever 分解表

| Lever | 目标版本（顶会亮度） | 不达标后果 | 状态 |
|---|---|---|---|
| L1. 双核心证透 | C（记忆续连）独头干净消融 + 核心 2（空间 re-ID）显式机制+指标 | headline 塌 → 不可投 | ⬜ P2/P4 |
| L2. 杀手锏 benchmark | 自造断点续连 benchmark（对齐 creatis 合成协议）+ ε_β0/SR/re-ID | 核心 claim 无铁证 → 降为 overclaim | ⬜ P1 |
| L3. baseline 全谱同台 | ≥12（SSM+拓扑+经典+冠脉+2025-2026 最新） | 漏比关键竞品 = reject | ⬜ P3 |
| L4. 数据集超量 | ≥10 集全做满（视网膜5+冠脉3+OCTA2+跨域），允许 1-2 边缘集失败 | 数据偏单 = 泛化质疑 | ⬜ P3/P5 |
| L5. 消融超量 | ≥8-10 组，每个机制 ≥1 干净对照 | 消融不系统 = novelty 存疑 | ⬜ P4 |
| L6. 拓扑/续连赢 SOTA | clDice/Betti/ε_β0/re-ID ≥1 轴显著赢 SOTA；裸 Dice 持平不输 | 无胜负点 = reject | ⬜ P3 |
| L7. 可解释性 | ≥3 张「记忆认出同根血管」可视化（王水花方向） | 卖点弱 | ⬜ P6 |
| L8. CV 方法贡献叙述 | 新机制/原理/benchmark 先行，医学=validation | 被读成换模块/纯临床 = reject | ⬜ P7 |
| L9. 写作/对抗审稿 | 数字三方对账 0 偏离 + reviewer 十角色 0 致命 + skeptic 攻 claim | 防御漏洞被审稿命中 | ⬜ P7 |
| L10. 复现/双盲 | 复现零偏离 + Code release + 双盲脱敏合规 | 红线/不送审 | ⬜ P7 |

---

## 🚧 每阶段硬阈值（出口 gate，逐条 PASS 才进下阶段）

### P0 环境 & kill-shot
- [ ] 关 2：单层 GDN-2 fwd/bwd 在 4090(sm_89) GPU 跑通（退路 `naive_chunk_gated_delta_rule` 纯 PyTorch 先验正确）
- [ ] 关 3：GDN-2 记忆模块塞小 U-Net，DRIVE 上 ①不发散 ②Dice ≥ 纯 CNN
- [ ] **不妥协闸**：kernel 连 naive 退路都不通 OR pilot 主集发散/输纯 CNN → 砍（拍板点，写诚实回退）

### P1 数据 & 断点续连 benchmark
- [ ] 10+ 集就位（datasets.json 登记 + 许可证逐个确认）
- [ ] 断点合成协议可复现（对齐 creatis plug-and-play，参数固定可复现）
- [ ] 续连指标实现：ε_β0 / SR（直接用）+ re-ID 率（自定义，同根血管匹配）
- [ ] **防泄漏**：benchmark 测试集 held-out 零拼训练样本；记忆 key 不碰 GT 拓扑（grep 验证）

### P2 核心模型实现
- [ ] pytest 全通（记忆模块/re-ID 头/Frangi 门/多向合并 单测）
- [ ] grep 确认 Frangi 与记忆 key **不读 GT/分割结果**
- [ ] flatten 序列 ≤~1K；可退化纯 CNN 兜底可跑
- [ ] **红线**：不重写 kernel；scan 不写成贡献

### P3 主实验
- [ ] DRIVE/CHASE/FIVES/STARE 主集深做，≥12 baseline 同框架（无漏比）
- [ ] 三轴指标全算（Dice/IoU/AUC + clDice/Betti/Skeleton Recall + ε_β0/SR/re-ID）
- [ ] seed ≥3，数字 Bash/Grep 核 csv（禁 Read 看数据）
- [ ] **不妥协**：拓扑或续连维度 ≥1 轴显著赢 SOTA + 裸 Dice 持平不输；禁调参作弊凑赢 Dice

### P4 消融
- [ ] ≥8-10 组消融
- [ ] C 有/无 干净对照证「有 C 续连率/re-ID 率显著↑」（headline 铁证，可归因）
- [ ] re-ID 头有/无、Frangi 门有/无、序列长度扫、多向数、delta-rule vs 普通线性 attn
- [ ] **红线**：机制纠缠不可归因 = 跑偏

#### 🔒 re-ID 可归因预登记表（2026-06-20 skeptic 致命-2 补 → 2026-06-20 命门 v2 修：补 A1' 等参臂 + 判据2 改 ε_β0 配平分层 CDE，skeptic 三轮复核 0🔴，设计阶段写死，禁跑完找说法）

| 臂 | bottleneck 特征源 | re-ID 头 | 作用 |
|---|---|---|---|
| **A0'（零假设臂）** | 纯 CNN bottleneck（无记忆/无注意力模块，use_memory=False） | 同一个 re-ID 头 | 容量/机制全无的地板 |
| **A1'（等参对照臂）** | 等参普通线性注意力模块（保留 q/k/v/out 投影+LayerNorm+同插入深度+同 Frangi 门通路，仅把有状态 delta-rule 关联记忆换成无状态 linear attn；可训练参数总量与 A2 差 ≤±5%） | 同头 | 隔离「加注意力模块的容量」贡献 |
| **A2（完整）** | GDN-2 有状态 delta-rule 关联记忆增强特征（delta 更新 + 递推状态 S_t） | 同头 | headline |
| A3（断记忆梯度） | 记忆特征但 detach 记忆训练 | 同头 | 隔离头 vs 记忆训练贡献 |
| A4（bonus，封泄漏） | 记忆特征 | 同头 + **预测骨架断点**（非 GT 骨架，Ren MICCAI2024 范式） | 证 GT 拓扑无实质优势 |

> 所有臂**同 seed≥3 / 同 split / 同超参 / 同训练预算（epochs）**，只切对照变量。A1' 等参口径以全模型可训练 numel 计，差 >±5% 须回 planner 重对齐再跑（禁默许超阈）。三臂 numel 实测值写进论文表脚注留痕。

**预登记判据（写死，FAIL = Claim 2 塌或降级 → 停下报用户拍板）**：

1. **主判据（机制可归因，归因链 A2 > A1' > A0'）**：
   - (1a) `re-ID率(A2) − re-ID率(A1') > 0` 且每集内 per-image 配对**精确排列检验**显著（n≥6：枚举 2^n 符号排列，单侧 p < 0.05；**n<6 小集预登记特例见下**）+ 配对 Wilcoxon 一致同号。**这是 headline 核心：证有状态 delta-rule 关联记忆（delta 更新+递推状态 S_t）超出等参 stateless 容量的净贡献。** FAIL → 增益来自容量非关联记忆 → Claim 2 机制塌。
   - (1b) `re-ID率(A1') − re-ID率(A0') > 0`（同检验）。佐证「加注意力模块」容量贡献（**辅助证据，A1'≈A0' 不致命**——只说明容量本身没用、增益全在 delta-rule 关联记忆，反而更利 headline；据结果在论文如实陈述，禁跑完改判定方向）。
   - **n<6 小集预登记特例（防 STARE n=4 机械卡 p=0.0625）**：n<6 时 2^n 符号排列单侧最小可达 p=1/2^n（n=4→0.0625>0.05 不可达）。故对 n<6 的集，主判据 (1a) 达标线预登记为「**方向为正（A2>A1' 同号）+ 该 n 下精确排列取得最小可达 p（即全部配对同向）**」，记为「该集达标」；不机械套 0.05。同时该小集**并入 pooled 跨集符号检验**作为补证。**n<6 集的单集 p 仅作方向佐证，Claim 2 的统计承重在 pooled 跨集检验 + n≥6 集的逐集 p<0.05**。CHASE(n=8,最小 p=0.0039)/HRF(n=18)/FIVES(n=20) 不受此特例影响，仍按 p<0.05。**此特例跑前写死，禁跑完发现卡 0.0625 再改（HARKing）。**
   - **跨集一致性**（替代旧 pool）：每集内独立做 (1a)，A2>A1' 方向在 ≥3/4 集成立（小集按上特例判达标）。
   - 统计实现：**禁 scipy.stats（OMP 红线）**，排列检验/Wilcoxon 手算（numpy + itertools 枚举），bootstrap 95% CI 手算（≥1000 resample 跨 test 图，CI 下界 > 0）。

2. **「认出≠填上」= memory 对 re-ID 的直接效应（ε_β0 配平分层 CDE；ε_β0 是中介非混杂，禁 over-control）**
   命门问的是：填充质量（ε_β0）持平时，记忆是否仍认得更准 = memory 对 re-ID 是否有**超出填充质量改善**的直接贡献。ε_β0 是因果链 memory→续连更好(ε_β0↓)→认出同根 上的**中介**，控制中介 = over-control bias（会抹真效应），故**作废旧 partial_corr(...|ε_β0) 及任何「结局模型放 ε_β0 取 memory 系数」的回归**（与 reid_verdict_v2.py:131 旧 LMM 数学同构，pilot 已实证塌缩为 p=0.486）。**唯一 PASS/FAIL 门 = ε_β0 配平子集分层（受控直接效应 CDE，匹配设计，非 over-control）**：
   - 做法：每集内，A2 与 A1' 在**同一图**天然配对，看同图 ε_β0 是否相近；仅纳入 `|ε_β0(A2)−ε_β0(A1')|` 落在该集 ε_β0 IQR 内的图（=**两臂填充质量相当**的子集，非「固定 ε_β0 水平」——筛的是 Δε_β0 落 IQR），在该子集内重做 (1a) 的配对精确排列检验。
   - **PASS 线（预登记，单侧，禁跑完调）**：两臂填充质量相当子集内 `re-ID率(A2) − re-ID率(A1') > 0` 且配对排列单侧 p < 0.10（子集更小故 .10，仍单侧预登记；子集 n<6 套上「方向为正+最小可达 p」特例）。
   - **意义**：填充质量一样好时记忆仍认得更准 → re-ID 是 memory 的直接效应（CDE），非 ε_β0 副产物。FAIL（持平子集内方向反或不显著）→ re-ID 仅 ε_β0 副产物 → Claim 2 降级为「记忆改善续连」（无独立 re-ID claim）。
   - **辅助刻画（不设门、不论成败，但须真写进论文正文）**：探索性中介分解报 TE/NDE/NIE 三件套（手算 OLS：中介模型 `ε_β0~memory_on+dataset`、结局模型 `reid_rate~memory_on+ε_β0+dataset`，NDE=结局模型 memory_on 系数，cluster bootstrap 按 image_id 报 CI）。**仅描述效应分布，不作 PASS/FAIL 依据**——NDE 因 block 经 ε_β0 中介路径而系统性偏小是**预期**（与旧 over-control 同构），**不以 NDE 论 Claim2 成败**，论文如实标注「NDE 偏小源于中介路径被截断，非无直接效应」。**TE/NDE/NIE 三件套必须真写进论文正文（主动暴露不利数字 = 严谨；省掉 = 藏，会被审稿抓）。**

3. **A4 封泄漏（不变，维持原判据）**：`|re-ID率(A4 预测骨架) − re-ID率(A2 GT骨架)| < 0.05` → GT 拓扑无实质优势，自监督泄漏质疑解除。
   > 保留理由：A4 与容量混杂/over-control 两条命门正交（管 GT-拓扑泄漏，非机制归因），skeptic 未质疑，维持 0.05 严阈。

> 阈值（A2−A1' 主判据 >0 + p<.05，小集特例；分层 CDE p<.10 单侧；A4 0.05）= 设计阶段预登记下限，**禁跑完上下调**。等参 ±5% = numel 对齐上限。判据2 唯一门 = ε_β0 配平分层 CDE，NDE 三件套仅辅助不设门（禁逻辑或择优放假阳）。所有统计禁 scipy.stats（OMP 红线），手算实现。

### P5 泛化/跨域/跨器官
- [ ] 冠脉(XCAD/DCA1/CHUAC) + OCTA(OCTA-500/ROSE) + 跨域(Crack500/Roads 附录)
- [ ] 跨域协议 FIVES→{DRIVE,STARE,CHASE,HRF} + DRIVE→CHASE/STARE
- [ ] ≥10 集；跨域不崩；边缘集允许 1-2 失败
- [ ] **红线**：许可证未确认不纳入发表；跨域禁调参作弊

### P6 可解释性
- [ ] ≥3 张支撑 headline 的可解释图（记忆检索热图/re-ID 匹配/容量衰减）
- [ ] 图含数字/比例的，主线派 verifier 或自核 ≥2 关键值与 csv 一致
- [ ] **红线**：禁 cherry-pick 误导；解释不超数据

### P7 写作 + 对抗审稿 + 投稿
- [ ] 14 页 LNCS，related work 硬区分 GDKVM（R3 模板）
- [ ] 数字三方对账（registry↔STORY↔tex）0 偏离
- [ ] reviewer 十角色 0 致命 + skeptic 攻 claim 通过
- [ ] 双盲脱敏合规 + 编译 0 error/0 undef + Code release
- [ ] **拍板**：投稿（venue 顶会优先，ACCV 保底）

---

## 🚨 红线（任意触发立即停手）

1. ❌ 断点续连 benchmark 测试集拼入训练样本 / in-sample 评估
2. ❌ vesselness 或记忆 key 用 GT / 分割结果监督（鸡生蛋 + 泄漏）
3. ❌ 凭印象写数字（必须 Bash/Grep 核 csv）
4. ❌ 复现偏离（私加裁剪/降 lr/改步数/换实现凑收敛；baseline 不按官方）
5. ❌ scan/reorder 当核心贡献（撞 Serp-Mamba）
6. ❌ related work 不区分 GDKVM
7. ❌ 绝对化 claim（"universal"/"always"/"prove"）

---

## 📝 task 完成判定流程

```
Step 1: 查本文件找该 task 的硬阈值
Step 2: 逐条对照实际产出
Step 3: 全条 PASS → 更新 PROJECT_LOG + 移下一项
        任一 FAIL → 不标完成，回去补
Step 4: 跑 grep 防御检查（R1-R7 + 红线）
Step 5: 大阶段收口跑 /stage-gate（verifier 核数 + opus reviewer 严判 PASS/FAIL）
```
