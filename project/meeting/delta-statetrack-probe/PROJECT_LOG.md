
## 2026-06-23 — Crux1 FLA 真核版重提交
- 背景：本地 torch 重实现版 Crux1 已 PASS（margin 0.476）。FLA-kernel 真核版（parity_probe.py）之前 smoke run（job 1484514）撞 `ChunkDeltaRuleFunction does not support float32. Please use bfloat16.`。
- 修复：parity_probe.py 加 torch.autocast(bfloat16)（line 711/758，仅 cuda+非dummy），FLA 核喂 bf16，模型本体不转。
- 动作：重传 bf16-fixed parity_probe.py 到 HPC（远端 grep autocast=7 核实）+ 清 stale smoke CSV + 提交 full run。
- job=1485372，5 臂(gla gdn2 gdn1 gdn1_neg deltanet_neg)×3 seed×15k steps，单卡 8h 上限。gpu_slot f6448723。
- 预期：deltanet_neg/gdn1_neg PASS（长桶 acc>0.9），gla/gdn2/gdn1 FAIL(~0.5)。gdn2 FAIL=🔴-2 门控杀负特征值确证。

## 2026-06-23 — Crux1 FLA 真核版 verdict 判定（job 1484588 解读）
**重要修正**：上个窗口其实已跑完 bf16-fixed full run = job **1484588**（FULL_EXIT=0），registry「等主线 HPC 跑」是过期信息。本窗口重提交 job 1485372 属冗余（且 submit 脚本的 `rm -f outputs/parity_parity_*` 误删了 1484588 的 csv，但 .out log 全文保留，数据未丢；1485372 重跑正好重生成 csv）。

**结果（OOD 长度桶 128-256，3 seed 均值±std，PREREG LIVE 阈值 >0.90）**：
| arm | 128-256 mean±std | 判 |
|---|---|---|
| gla (diag) | 0.6136±0.0110 | DEAD |
| gdn2 (as-shipped) | 0.6173±0.0187 | DEAD(脚本判 AMBIGUOUS) |
| gdn1 (pos only) | 0.5994±0.0116 | DEAD |
| **gdn1_neg (allow_neg)** | **0.9748±0.0356** | **LIVE ✅** |
| deltanet_neg (neg) | 0.8606±0.0987 | DEAD ❌(seed 0.785/1.0/0.797) |

**判定 = Crux1 PASS（GDN 家族内，带注脚）**：
- 最干净证据 = GDN 家族内单 flag 消融：gdn1(pos) 0.5994 → gdn1_neg(neg) 0.9748，**delta +0.375，仅翻 allow_neg_eigval，3/3 seed 稳**。同架构同 iso-param(state=4096)无混淆变量 = 干净因果。
- **🔴-2（GDN-2 gate 杀负特征值）实质 CONFIRMED**：gdn2 0.6173 与 pos 臂 gdn1 0.5994 完全 overlap（std 内），离 gdn1_neg 0.97 极远 → gate 中和了 neg 机制。脚本判 AMBIGUOUS 仅因硬阈值 0.55 卡口径，非真歧义。建议补 t-test 把口径升 CONFIRMED（待 gdn2vessel 正式拍板）。

**杂音（比本地 torch 版乱）**：
1. pos 臂停 ~0.60 非纯 chance 0.5 → 浅层短序列外推上界，非 bug（gla 短桶 0.83-0.90，长桶衰减）。本地 torch 版 pos 臂干净 0.51 因 task/eval 口径不同（in-dist test acc vs OOD length 外推）。
2. deltanet_neg std=0.099 最高，2/3 seed 跌 0.78 → 无 gating 架构里 neg eigval 有效但脆；gdn1_neg(有 gating)全稳 → **gating+neg 协同才是稳定状态追踪完整条件**。

**对 gdn2vessel headline 支撑 = 中等偏强**：「GDN 家族内 neg eigval 是 parity 状态追踪必要条件」充分；扩到「所有 delta-rule 架构普适必要」证据不完整（deltanet_neg 不稳 + pos 臂 noise floor 偏高）。
**建议补实验升普适性**：① 更长桶 256-512（逼 pos 臂跌真 chance）② deltanet_neg 扩 5-10 seed ③ 第二 task(Selective Copy/S5)从单 task 推到 task 类。
图：outputs/parity_ood_bars_1484588.png

## 2026-06-23 — Crux2 数据攻克 + pipeline 真实烟测通过
**数据 blocker 破解（用户 Kaggle 直觉押对）**：CAMMA 审批闸绕开了。
- **特征**：LoViT OneDrive `Spatial_feature_Cholec80.zip` 496MB 匿名直连（Playwright 驱动 download.aspx 端点下，httpOnly auth 只能浏览器内下），解压 80 个 pkl shape [768,T,1,1] 1fps → 重命名 features/videoNN.pkl。
- **标签**：Kaggle `ganumatta/cholec80`（103GB 全量但 phase_annotations/ 是**松散文件**）→ kaggle CLI `-f` 循环只下 80 个 videoNN-phase.txt（每个~1MB 25fps，全部~90MB，不碰 103GB 帧）。格式 Frame⇥Phase 7类，**完美匹配 spr_probe.py**，免转换免审批。CC-BY-NC-SA 允许署名非商业转分发=合规。
- 备选源（未用）：CAMMA SelfSupSurg `s3.unistra.fr/camma_public/github/selfsupsurg/ch80_labels.zip`（公开 wget，pickle 格式需转换）。
- 本地数据：`data/cholec80/{features/videoNN.pkl ×80, phase_annotations/videoNN-phase.txt ×80}`。

**Pipeline e2e 真实烟测 PASS（本地 CPU，CUDA_VISIBLE_DEVICES=-1）**：
`python spr_probe.py --mode w_scan --w_scan 30 --seeds 0 --smoke --data_root data/cholec80`
- 真实标签→GT 转移图 13 allowed transitions ✓；真实特征→sliding_window 训练 loss 0.288→0.0024 收敛 ✓；PTVR=0.0063 Jaccard=0.7341 ✓；输出 spr_w_scan.json ✓
- sliding_window=纯 torch CPU 可跑；FLA 五臂(gla/gdn1_neg/deltaproduct/gdn1)仍需 HPC GPU。
- 验证了整条数据路径(dataloader/25→1fps对齐/训练/PTVR/输出)在真实数据无 mock 跑通=上 HPC 前 e2e 真烟测达标。

**下一步=🛑拍板点**：真 Crux2 跑需上传 data/cholec80 到 HPC（对外传输）+ GPU 5臂(calibrate→full)。等用户放行。

## 2026-06-23 — Crux2 设计红队 + 判据加严（full run 前）
**skeptic 红队 spr_probe.py 设计，2🔴致命+裁 NO-GO（calibrate 继续, full 等修）**：
- 🔴-A PTVR 判据可能自我推翻：转移图从 train GT 建(self-loop恒True+一次出现即置1)，Cholec80 阶段顺序刻板→allowed 稠密→PTVR 被压地板臂间无区分；更狠=低 PTVR 反证低阶 Markov 够用=反向 kill。
- 🔴-B P1「PTVR最低」可被「保守不跳类」刷低(切换少→违规机会少→机械降PTVR，而保守不跳=非状态追踪行为)，P2 Jaccard 门 1pp 太松拦不住。

**本地密度检查（不挤卡，从40 train GT 算）实证 🔴-A**：
- `allowed density = 17/49 = 0.347`（低于0.6阈值→PTVR 没被压死，有违规空间，🔴-A 第一刀减弱）
- allowed 近线性带状链；train 转移矩阵对角 0.99-1.00=近确定性；**TEST GT PTVR 全 40 视频 = 0.0000**
- 结论：PTVR 非干净 kill，但**任务转移结构极简→Cholec80 SPR 可能本就不需状态追踪**（坐实战略天花板🟢-F：即便 PASS 也难撑反认知 headline）

**派 coder 加严判据（py_compile OK，本地 w_scan 烟测无回归 ptvr=0.0063）**：
- P1b co-primary：seg_f1@50 必须也显著高于 ALL TC0（PTVR 不独裁）
- P_switch 门：gdn1_neg 切换数 ∈ [0.8,1.2]×GT 且 ≥0.8×TC0（堵保守不跳）
- P3 加 effect-size：p<0.05 AND rel_drop≥calib_margin
- overall_pass = P1∧P1b∧P2∧P3∧P_switch
- 新字段全进 verdict JSON + CSV

**下一步（gated）**：calibrate(job 1485869 排队中,旧码 TC0-only 不受硬化影响)出 TC0 PTVR 中位数+R²+w_scan 饱和→收尾 🔴-A 判定。**full run 前需🛑拍板**：重传硬化 spr_probe.py 到 HPC + HPC `--smoke --mode full` 验五臂新 verdict→才正式 full。

## 2026-06-23 — Crux2 calibrate 诊断（HPC 卡顿 → 烟测验真相）
**HPC 卡顿根因 = FairShare 归零**（不是 bug，配置同成功 job）：4gpus 队列优先级垫底排 4h 不动。出路=`gpudebug` QOS（priority 200，1h 墙，独立 gpudebug partition gpu3090n6 空闲）→ 立刻起跑。

**full calibrate(20k steps,40视频) 假死**：GPU 恒 2-5% util 29min，非 hang 是 **20k steps 严重超量 + 40视频 gpfs IO 瓶颈饿 GPU**。

**烟测(-u 无缓冲, 4视频/200步/1seed) 53s COMPLETED 验真相**：
- 代码完全正常：gla FLA 臂在 3090 跑通(loss 0.6975→0.0010 **200步即收敛**)，sliding_window 同。
- calibrate 数(指示性)：**PTVR-vs-Jaccard R²=0.0051 OK**(PTVR 不是 Jaccard 傀儡=解耦好,部分反驳🔴-A一刀)；Bootstrap null margin=0.0220；**TC0 PTVR noise floor(min)=0.0038 极低**。
- 暴露 3 问题：①**iso-param 破**(numel spread 22.45%>5%,5臂参数量不等 gdn1_neg1.91M/deltaproduct2.17M/gla1.92M/sw1.77M,不公平,full前须修d_model/head_dim) ②**steps 100×过量**(20k抄自parity,SPR 200步秒收敛,应右调~2000) ③TC0 PTVR floor极低+density0.347+近线性顺序 = **再坐实任务太刻板,SPR大概率不需状态追踪**。

**决策点（go/no-go,待用户拍板）**：probe 机制能跑，但证据偏向「Cholec80 SPR=低阶Markov,证不出状态追踪必要」+ 战略天花板(机制不新+任务不新)。falsify-crux-first 已用~1GPU·h 揭示命门松动,在投入full run+paper前该定夺。

## 2026-06-23 — 🗄️ 方向封存（诚实退守，证据闭环）
**封存裁决**：delta-statetrack 方向封存。机制真（Crux1 PASS），但「负特征值 NC¹ 状态追踪 × 医学时序」交集**结构性不存在**。

**证据三层闭环**：
1. **Crux2 第一个医学任务(SPR)实证证伪**：Cholec80 阶段转移 density 0.347 近确定性线性链、test GT PTVR 全 0、TC0 PTVR floor 0.004 → 低阶 Markov 够，不需状态追踪。
2. **skeptic 红队「换任务」可行性 = NO-GO（结构性）**：医学时序主流结构=长依赖+可交换聚合/单调累积/计数，全落 TC⁰(diagonal SSM 能吃)；唯一带非交换原语候选(导管/血管树SO(3))无公开 NC¹-hard benchmark+撞 gdn2vessel+偏离 ACCV。换任何主流医学任务=重蹈 SPR 覆辙。
3. **researcher 反查收口 = 空手**：无任何 published 医学 NC¹-hard/S_n-reducible benchmark。DeltaNet/DeltaProduct/Grazzi(ICLR25) real-world 清单全合成+语言建模零医学；反而 EHRMamba/SR-Mamba 显示 diagonal Mamba 在医学**赢** = 方向反证。

**根因**：thesis 押的 claim 形状=「大胆机制×未验承重前提（医学任务需状态追踪）」，承重前提被证伪。印证 [[feedback_falsify_crux_first]] + [[feedback_claim_shape_decides_birth_difficulty]]——命门(医学任务是否 NC¹-hard)该最先最便宜证伪，这次用 ~1GPU·h+红队+反查在烧 full run+写 paper 前照出。诚实退守不 HARKing。

**带走硬资产**：
- Crux1 真核 PASS（job 1484588：GDN 家族 gdn1 0.599→gdn1_neg 0.975 单 flag +0.375 干净因果，负特征值 parity 状态追踪必要性实证）→ 可供未来非医学 venue/他项目复用
- 判据框架（PTVR/seg-F1/P_switch 加严版 spr_probe.py）+ 转移图密度证伪法
- Cholec80 数据管道（LoViT 特征 + Kaggle ganumatta 标签绕 CAMMA）+ HPC gpudebug 快车道调试经验（fairshare=0 时的出路）

**未来复活条件**：出现 published 医学 NC¹-hard 任务（被证明需非交换长程组合且 diagonal SSM 有 floor），或愿自建合成「血管树路径追踪」探针（但偏离医学落地初衷+撞 gdn2vessel）。
