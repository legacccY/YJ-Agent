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

#### 🔒🔒 命门方向 A 预登记（2026-06-21 写死，planner 设计 + skeptic 红队 0 致命过 + 用户拍方向 A；跑前留痕，禁 HARKing）

**背景**：CHASE Stage-1 命门初跑 A2(delta-rule 有状态记忆)≈A1'(等参 stateless linear attn)≈A0'(纯CNN)≈0.50 随机（旧 seg-mask `reid_rate`）。**根因 = 测量管道断裂（代码层硬事实）**：`evaluate.py:708` 的 `reid_rate` 纯读 seg mask（`compute_all_metrics(pred_bin,...)`，`metrics.py:679` 只看分割掩膜是否覆盖 gap 两段），**从不调 re-ID 头的 K×K 配对 logits**；而 re-ID 头被 `reid_loss.py` 三道 detach 屏障隔离、其输出 eval 从不用 → claim 的机制（memory→头→同根匹配）结构性够不到 headline 指标。叠加 A1' 死参（`unet_gdn2.py:1120` proj_erase/proj_g/alpha_e ×0.0 零梯度，等参对照无效）+ 机制窗口窄（raster scan 同根 token 隔 1-3，delta-rule 短程 tied 文献预期）。**非真 null，是测量错位。**

**机制性假说 H（单一，跑前写死）**：A2≈A1' 源于「测量指标不对齐机制 + A1' 死参 + 检索窗口窄」三处工程缺陷。修后预测 **A2 > A1' 在对齐指标 `reid_rate_head` 上成立**（有状态 delta-rule 关联记忆有超出 stateless linear attn 的净贡献）。

**唯一指标变更（修测量非松阈值）**：判据 1a/1b/2/A4 中「re-ID率」从旧 seg-mask `reid_rate` 换成新 `reid_rate_head`（由 re-ID 头**离散 argmax 配对决策**判，**裁判 = GT vessel_segment_map 同根标签 Y，head 只贡献「选哪个伙伴」，连续 logit 仅作 match/no-match 门不进打分** → 切开「用被 L_match 训练的头判头」自证循环，skeptic 🔴-1）。**判据阈值数字一字不动**（1a p<0.05、CDE p<0.10、A4 0.05、跨集 ≥3/4、小集特例全冻结）。旧 seg-mask `reid_rate` **并列报但不作判据**（反 HARKing 诚实留痕，论文写明代码层指标错位证据）。

**分阶段修复（skeptic 🟢-6 采纳，做根因拆分）**：
- **Stage-1a（先做）= M1 新指标 + M4 修死参，不动 scan**：跑 CHASE 单集×3seed。若 `reid_rate_head` 上已 A2>A1'（判据 1a 过）→ 证根因 = 测量错位，**M3 骨架 scan 不必做**（省 R4 撞 Serp-Mamba 风险）。
- **Stage-1b（条件触发）= 上 M3 骨架 scan**（Frangi input-derived 导序，**禁 GT skeleton**，三臂一致施加，scan 当标准工程不当贡献 R4）：仅当 Stage-1a 仍 A2≈A1' 才做，给 delta-rule 检索窗口后重跑 CHASE。
- **全命门（过 CHASE 才跑）= 4 集×3 臂(+A4)×3 seed**，一次成型。

**一次验证（禁 p-hack）**：配置本地真烟测通过后冻结，每 stage 跑**一次**，**禁反复调 scan 参数/阈值/lambda 直到 A2>A1' 出现**。

**硬退出判据（写死，这是 Claim2 记忆机制最后一次修复机会）**：Stage-1a+1b 全做完、全命门仍 `reid_rate_head` 上 A2≈A1'（判据 1a FAIL + 持平子集 CDE FAIL，跨集方向不一致/pooled 不显著）→ **真 null 坐实，Claim2 记忆机制不再救** → headline 转 benchmark-led（杀手锏断点 benchmark + 续连指标 ε_β0/SR + 可解释图 + 诚实报告 delta-rule 在 ≤1K 容量下不超 stateless）→ stage-gate FAIL 拍板点停下报用户。**禁再找新缺陷续命。**

**留痕审计（PHASE_4 ⑧）**：A1' 修死参后审计 proj_erase/proj_g/alpha_e grad norm ≠ 0（已实测 3.04/0.831/0.526）+ 三臂 numel 差 ≤±5%，写论文附录。

> **A-I 结果（2026-06-21 跑完）**：CHASE Stage-1a M1+M4 跑出 → 对齐指标 `reid_rate_head` 跳到 0.94（旧 seg-mask 0.46，证头真学会匹配、老指标测错东西），**但 A2(0.9437)≈A1'(0.9401) 仍平**。二诊（researcher+analyst 收敛 90%+）：测量已对齐，但 **re-ID 头融合架构让 dec_feat(decoder 局部 128×128) 抄近路压没 memory(o_seq 32×32)**——头 ep10 即靠局部空间邻近解任务，delta-rule 没机会。非真 null。→ 触发 A-v2。

#### 🔒🔒🔒 命门方向 A-v2 预登记（2026-06-21 写死；planner 设计 + skeptic 红队 2🔴 修 + 复核 0 致命 + researcher 理论锚核实 + 用户拍 Option A；**Claim2 记忆机制最后一次设计调整**）

**机制性假说 H（单一，跑前写死）**：A2≈A1' 源于「① re-ID 头局部近路（dec_feat 高分辨率压没 memory）+ ② 评估未在 delta-rule 理论占优区度量」。delta-rule 相对 stateless linear attn 的净优势**理论上只发生在 state crowding（同一感受野内同时竞争写入有限状态维 d 的身份数 k 大）处**，避免 catastrophic overwriting / key collision；low-crowding 处两臂本就该 tied。修后预测 **A2−A1' 的 `reid_rate_head` delta 随 crowding 单调上升：high-crowding 子集 A2>A1' 显著，low-crowding 子集 tied**（剂量-反应，非单点）。**判据轴 = state-crowding（关联密度 k），不是 gap 距离/序列长度**（距离是两臂共享维度分不开，STORY L37-42 铁律）。

**理论锚（researcher 2026-06-21 核实坚实，写论文用）**：Schlag 2021（ICML，形式界：状态维 d 个正交关联上限，超之检索出错）+ DeltaNet arXiv 2406.06484 §2.2（"key collisions when L>d"）+ VLA arXiv 2605.11196 §5.2/§6.5/Prop.3（对照实验解耦 K 关联数 vs T 序列长度，证 **K 是驱动因素非距离**，per-head 容量 = d_h）。⚠️外推边界：MQAR key 离散近正交，血管 feature 连续、碰撞率无直接实验对应——论文须显式声明此外推。（2602.04852 不支撑此命题，禁引。）

**两处修复（三臂一致施加，测量/架构修复非自变量）**：
- **M-A memory-only 头**：`ReIDReadoutHead` 加 `use_loc_feat=False`，砍 dec_feat 路、头只吃 memory `o_seq`。三臂一致。detach 三屏障不动。
- **M-B state-crowding 子集判据**：k(i)=query i 局部窗口（半径 R_win=bottleneck 感受野按 stride 算定的架构常量，input-derived）内**不同 vessel segment id 去重数**。判据在 high-crowding 子集(k≥k_thresh) vs low-crowding 子集上分别算 `reid_rate_head`。**子集从无 hard-neg 的标准主 benchmark 自然分布筛**（单图~100 gap 天然含高 crowding 区），候选池**全 K 无人工门**。**不注入 hard negative**（删，防构造性 cherry-pick + 保命门 benchmark = P3 主续连 benchmark 可比）。

**跑前写死数值**：k 度量=窗口去重 seg id 数 / R_win=stride 算定理论感受野 / k_thresh=各集自然 k 分布**中位数**（+ 均值 + 60 分位稳健性并报方向须一致）/ 候选池全 K / hard neg=删 / 判据阈值 1a p<0.05·CDE p<0.10·A4 0.05·跨集≥3/4·小集特例（A-I 一字不动）/ r_chance=该子集 1÷平均候选数（每集每子集分算）/ epochs 300 / severity Medium。

**主判据（dose-response 交互，skeptic 裁决一，关死循环+强化 headline）**：不是「high-crowding A2>A1'」单点，而是 **「A2−A1' delta 随 crowding 单调上升：high-crowding 子集 per-image 配对 A2>A1' 显著(p<0.05 小集特例) + low-crowding 子集 tied(方向不显著)」的联合交互模式**。只 high 显著 low 也显著 → 非 crowding 特异 → 归因存疑。bonus 并报 top-quartile crowding 方向（不设门）。

**(a)/(b) 归因切分（描述性读数，skeptic 🟠-2，不设 PASS/FAIL 门）**：high-crowding 子集同报 A1' 与 A2 各自相对 r_chance 位置——A1' 塌到 ≈r_chance(|·|<0.05)=被动垫底=容量复发=归因弱；A1' 显著>r_chance 只是<A2=delta-rule 主动优=headline 强。**承重门始终是 A2>A1' per-image 配对检验（r_chance 在配对中约掉）**；(a)/(b) 仅描述归因强度，不设门（同 v1 NDE 三件套纪律）。r_chance 跨集不可比，只比同集同子集配对 delta。

**判据 1b 容量排除（必报）**：A2>A1'(1a 过) 且 A1'≈A0'(1b 方向不显著) = 增益全在 delta-rule、容量本身没用 = 最强 headline（STORY L74）。memory-only 下 A0' headless→reid_rate_head NaN→1b 回退 seg-mask。

**k 的 R5 辖域声明（skeptic 🟠-1）**：k 用 GT vessel_segment_map 计数，但**仅作评估时难度分层、三臂共享同一 k 划分、不回流任何臂的训练/前向/memory**（合法「按难度分桶报指标」，与「GT 监督机制」正交）。论文须显式声明。可选鲁棒性对照：用 input-derived crowding 代理（Frangi 局部峰数/骨架分叉密度）重算验证子集划分高度重合。

**指标**：判据结局量 = `reid_rate_head`（high/low-crowding 子集，memory-only 头，标准 benchmark）。旧 seg-mask `reid_rate` + 全 gap reid_rate_head + 距离切子集 reid_rate_head **三者并列报不作判据**（诚实留痕，距离仅次要刻画）。

**一次验证（禁 p-hack）**：本地真 e2e 烟测通过+各集 k_thresh/R_win/r_chance/high-crowding 子集 n(≥4) 落档后冻结。CHASE 先验(3臂×3seed)跑一次→过 dose-response 主判据→全命门(4集×3臂(+A4)×3seed)一次成型。**禁反复调 R_win/k_thresh/子集设计直到 A2>A1' 出现。**

**🔒🔒 无条件铁闸（skeptic 🟠-3，与上方 A-I 硬退出判据合并为唯一退出门，最高优先）**：**A-v2 是 Claim2 记忆机制绝对最后一次设计调整。全命门跑完，若 high-crowding 子集 `reid_rate_head` 上仍 A2≈A1'（dose-response 不成立 / 配对方向不一致 / pooled 不显著）→ 真 null 坐实 → 无条件转 benchmark-led**（杀手锏断点 benchmark + 续连指标 ε_β0/SR + reid_rate_head 指标本身作贡献 + 可解释图 + 诚实报告 delta-rule 在 ≤1K 容量/k 下不超 stateless）→ stage-gate FAIL 拍板点停下报。**四点名红线（机械判定，禁绕）：FAIL 后禁换轴、禁换指标、禁换子集定义、禁扩 seed 凑显著。禁再找新缺陷续命。**

**留痕审计**：① 三臂 memory-only 头 numel ≤±5%；② A1' 死参 grad≠0（A-I 实测沿用）；③ R_win/k_thresh(中位数+均值+60分位)/r_chance/各集 high+low-crowding 子集 n + (a)/(b) 读数 + dose-response 曲线写论文附录。

**算力**：CHASE 先验 9 run ≈23 GPU·h（门控）→ 全命门 36+12(A4) run ≈125 GPU·h。CHASE benchmark cache **无须重生**（删 hard neg 用自然分布，cache 不变）。

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
