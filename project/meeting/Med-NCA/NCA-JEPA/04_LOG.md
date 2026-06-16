# NCA-JEPA — 04_LOG（时间倒序）

> **全史真源**：`../PROJECT_LOG.md`（Med-NCA 总日志，含复现 + NCA-JEPA 全部历史 entry）。
> 本文件 = NCA-JEPA 子项目going-forward 简日志 + 最新状态快照。新 NCA-JEPA 会话在此追一行，详写进 `../PROJECT_LOG.md`。
> 入口读档：`README.md`（命名+状态）→ `01_创新计划` + `02_理论框架`（why+命题）→ `03_pilot`（怎么跑）→ `registry.json`（臂/门/状态）。

---

## 2026-06-17 — 拯救路线 A：谱半径下界验证探针落地
- **新文件**：`eval/spectral_lower_bound.py` — 残差 ρ vs σ_max 系统性验证脚本（claim: ρ(I+J_g)≥1 结构性下界，跨 MLP/Conv/Attn/NCA 族）。
- **口径修正桥接**：eval_anytime.estimate_lf 算的是 σ_max（奇异值）不是 ρ（谱半径）；本脚本同时输出两列分列对比，小维度用显式 `torch.linalg.eigvals` 金标准，大维度幂迭代。
- **4 run 最小验证集**：R0(NCAStep真实残差) / R1(MLP-residual) / R4(MLP-pure DEQ对照) / R5(SN sweep c∈{0.3..2.0})。
- 输出 CSV：`results/spectral_lower_bound/results.csv`。
- **三轮跑完（minimal→full→falsify，纯 CPU 零训练，主线直接 python 跑非 /run-experiment）**：
  - **核心 claim 主体成立（真 ρ 显式 eig，非 σ_max）**：残差组 ρ≥1 跨 4 族 + 多 seed 稳健——MLP 1.168±0.021 / Attn 1.358±0.065 / NCA 1.230±0.062（3 seed）/ Conv 修复退化后 1.341；pure 对照（无 I 项）全 ρ<1（MLP 0.193-0.199, Attn 0.406, Conv 0.341）。SN 强度 c=0.3→2.0 扫描 ρ=1.016→1.578，**怎么压都跨不过 1**（最低 1.016）。恒等式 ρ(I+J_g)≈max|1+λ(J_g)| 数值验证。
  - **证伪测试暴露真实边界（对创新点负责的关键）**：① claim **不是无条件定理**——理论可构造纯负反馈 g（全负实特征值 `g(h)≈−c·h`），SN 顶到 1 时 `I+J_g` 特征值全 ∈(0,1)→ρ<1 反例。coder 的 NegReal 构造混了正特征值没撞到（F7 λ_g=−1.0 仍 ρ=1.105，因正特征值拉高），但数学上反例存在。② 核心恒等式 `λ(I+g)=1+λ(g)` 是已知（i-ResNet Behrmann 2019），非首创。
  - **诚实定位判定**：路线 A = **扎实（理论+实证混合，文献确无人系统做 SN 约束下残差 ρ→1⁺ 实证）但非"惊天大胆定律"**（核心数学已知 + 有人工反例可打穿）。精确 claim 须挂「SN 约束 + 非负反馈 g」条件，不能裸宣称「残差就 ρ≥1」。
  - **图**：`results/spectral_lower_bound/rho_residual_vs_pure.png`（残差 vs pure 跨族 + ρ=1 临界线）、`rho_vs_sn_sweep.png`（SN 怎么压跨不过）。
- **战略待拍（下窗口）**：用户连续表达「创新点平平/要非常大胆」。路线 A 验到头=扎实非惊艳。三选项：① 接受扎实定位走 capability paper（中等会议稳）；② 押路线 B（NCA predictor 抗遗忘，NCAdapt 证 NCA 跨域遗忘比 Transformer 小 100×，JEPA predictor 位无人做，可能更"新"，**待同等严谨度探路验证**）；③ 诚实承认天花板有限考虑换更激进方向（合 memory「挖蓝海别跟现有重合」）。**主线建议：下一步用实验验路线 B 够不够大胆，别再在 A 上打磨。**
- **本窗口给博士生评估交付**：`07_项目评估_给博士生_2026-06-17.md`（大白话版，含真实数字+图+文献，判"能不能做/有没有潜力"）。
- 拯救探路 4 researcher 情报（赛道仍空/竞品/痛点场景/NCA 独特能力）见本 entry 关联调研，关键：NCA-as-SSL-predictor 2026-06 仍全网空白（2604.24990 综述点名 gap），路线 B 抗遗忘=R1 最强候选。

## 2026-06-16 — AMBER 阻断①③④⑤清 + 重测 L_f + GREEN 理论返修 + Gate1 PASS（仅剩②A1补seed训练拍板）
- **① estimate_lf 口径修复（coder）**：`eval_anytime.estimate_lf` 重写——(a) **bug#1 修**：废 `torch.randn` 随机点，改 `NCAPredictor.get_hidden_at_step()` 跑真实 forward 半程拿轨迹状态 h（含 scatter context + anchor 锚定），在 S/4·S/2·3S/4 三点各 power-iteration 取 σ_max 当谱半径上界；(b) **fire 算子固定**：每 power-iter 步 `gen.manual_seed(fire_seed)` 重置使 `cell(h_,generator=gen)` 看同一 fire mask（power iteration 需固定算子）= 与 A2 `deterministic_fire=True` 推理同路径，口径自洽。(c) **bug#2 经核不成立**：`NCAStep.forward` line67 已返 `h+fire*delta`（残差全映射），cell Jacobian 已是 `I+diag(fire)·J_δ`，不需改；reviewer 诊断的「测 δ 非 I+J_δ」与现码不符。
- **✅ 真 ckpt 重测 L_f（全 7 NCA 臂, ep50, missing=0, login CPU, fixed 代码已推 HPC）**：
  - **A1 vanilla(无 SN)=1.366** | **A2 SCP(SN) S16 三 seed=1.0080/1.0076/1.0050(mean 1.0069, population std 0.0013, n=3)** | S 扫描 **S4=1.6103/S8=1.4362/S16=1.0080/S32=1.0032**（单调降逼近 1⁺）。
  - **三硬结论**：① **全 >1 无一形式收缩**（最低 S32=1.003）；② **SN 显著有效**：A1→A2 压 26%（旧口径 bug 报"仅 1.5%"是假象）→ PC-2 坐实；③ **理论预言 0.2–0.5 本身错**（漏算残差更新 `h+fire·δ` 的 Jacobian `I+diag(fire)·J_δ`，I 项使谱半径天然下界≈1，SN 只压 J_δ 跨不过 1；S↑→1⁺ 即 J_δ 被越压越小趋恒等映射）。
- **🛑 用户拍定方向 = 融合 GREEN**：主 claim「SN 显著压缩谱半径 1.366→1.007(−26%)、逼近收缩临界 1⁺」（定量稳定性结果）；讨论节「残差 I 项使形式收缩 L_f<1 结构性不可达」当独家理论洞察。02 §10/§11 的 L_f<1 绿灯 → 有界膨胀 + 逼近 1⁺。
- **⑤ 理论返修（writer，opus，caveman OFF）**：02/01/03 全部 L_f claim 按实测返修——02 主叙事(有界膨胀)本已对，改遗留数值预言(0.2-0.5/0.35→实测)、红灯口径(L_f<1 绿灯/>1→bug → SN 压缩判据+不可达非bug)、上界 √2→√3(含两路 Conv，解释 S4=1.610 超 √2)、补 SN 实测段 + 残差极限洞察 + worst-case (1+L_f)^S 上界过松口径(L_f>1 上界爆炸但实测健康收敛=真稳定靠 SN 压缩+动力学非 Lipschitz 收缩)；01 行108/114 残留旧「Lipschitz<1→Banach 唯一不动点收敛」错 claim 改掉；03 行221 红灯口径同步。
- **✅ verifier 三方核账**：L_f 单值/降幅−26%/两个 A2 的 (1+L_f)^S 全对入论文；抓 3 处 writer 已修：(1+1.366)^16 ~6e5.4→~9.6e5、§2.1证(c)残留 √2→√3、std=0.0013 标 population std(n=3) 口径。
- **④ registry 同步**：Gate3「anytime 一等」→ 稳定性(L_f)+省参核心、anytime 降辅项；current 全更新。
- **③ ✅ Gate1 PASS（A2 三 seed S16 canary 轨迹, HPC .out 提取）**：final loss s42=0.095/s123=0.100/s2024=0.098（std≈0.002≪0.1），全程单调降(0.21→0.10) 无双峰/无发散/无 NaN、grad_stats 末值正常 → 3/3 收敛 + canary 健康 + σ_final<0.1 + 无双盆地 全满足。
- **AMBER→GREEN（稳定性核心成立）**：阻断①③④⑤全清 + Gate1 PASS + L_f claim 诚实返修。**仅剩 ② A1 补 seed123/2024**（vanilla 配对 A2 三 seed 坐实 SN −26% 统计）=训练拍板点，待用户「跑」。
- 本轮文件：eval_anytime.py+nca_predictor.py(coder 修)、02/01/03(writer 返修)、registry(Gate3+current)、results/anytime_*_lffix.csv×7（重测）。HPC 推 fixed 代码（eval 推理非训练，未占训练锁）。

## 2026-06-16 — pilot 全 7 job 训完 + eval + /stage-gate 严判 = 🟡 AMBER（不放行）
- **训练全完**：7 job 全 COMPLETED 50ep。eval_anytime 出全部 Q(k)+L_f csv（results/anytime_*.csv），aggregate 出 trade-off 图（results/tradeoff.png）。
- **verifier(V-gate) 核绿**：8 csv 数字零 drift、Q 全单调；a2 S16 三 seed L_f mean=1.0263 std=0.0031；final-loss 0.095/0.100/0.098(std≈0.002)。三 seed eval 数差异（L_f/Q 各不同）反证 ckpt 未被并发覆盖（不同文件）。
- **核心实测**（全 Bash 核 csv）：
  - A0+(ViT早退): Q(1)=0.975（窄、近无损）；NCA 各臂 Q(1)=0.63–0.85 < A0+ → **raw anytime 上 ViT 压顶，NCA 不占优**。
  - a2 S 扫描 trade-off 单调：S4 L_f=1.940/Q1=0.850 → S32 L_f=1.003/Q1=0.631（S↑→L_f→1⁺ 逼近收缩临界、Q1↓）。stability↔anytime 张力实测成立（合 Bassily）。
  - **全 L_f>1（1.003–1.940），无一形式收缩**。
- **🛑 reviewer(R-gate,opus) 抓到致命伤 → AMBER**：
  1. 🔴 **L_f 实测全 >1 顶撞理论 + 命中自定红灯**：02 写 L_f 典型 0.2–0.5（数值例 0.35），§10/§11 绿灯明文「L_f<1.0，>1.0→SN 有 bug 先修」。实测全 >1 → 按自定 if-then 应「先修再判」，不能推 Gate 过。
  2. 🔴 **L_f 估计器口径 bug（主线诊断）**：`eval_anytime.estimate_lf()` ① 在 `torch.randn` 随机点估 Jacobian（非真实迭代状态，docstring 与实现不符）；② 测 `J_cell`（更新增量 δ）而非残差全映射 `I+J_δ`(+fire_rate)。任一致 L_f 系统性偏高 → L_f>1 大概率是测量错非 SN 失败。
  3. ❌ **PC-1 不达**：A1 vanilla 只跑 seed42（非 3/3），且单 seed A1 未塌缩 → 「vanilla 塌缩、三件套治好」反例没立住、对照失效。
  4. 🟠 **PC-2「可控」未坐实**：A2 L_f≈1.026 ≈ A1 L_f=1.041（SN 仅移 ~1.5%），「SN 控了什么」答不上（待 #2 修后重测）。
  5. 🟠 **Gate1 canary 项无实测**（results 只有 Q(k)，无 std/rank/KoLeo 轨迹）；Gate2（下游 AUROC）PENDING 未跑（合理，后续阶段）。
  6. 🟠 **registry.gates.Gate3 仍写 anytime「一等」**，与已降辅项的 01/03 脱节，须同步。
- **三态总判 = AMBER**（03:246「Gate1 过但能力/非劣弱」）：严格说 L_f 红灯未清连 Gate1 都不能判过。给 AMBER 非 RED 的理由 = L_f>1 极可能是 #2 估计器 bug + A2 收敛面（loss std 0.002/无发散/无双峰）真实健康。
- **诚实定性**：A2 anytime 按 §9.1 自定阈值落 RED（Q1≤0.731<0.95，劣于 A0+），已降辅项；稳定性硬项因 L_f 口径问题悬置（修后再判）。
- **阻断清单（不放行，须先清）**：① 修 estimate_lf 口径（真实状态 + I+J_δ + fire）→ 重测全臂 L_f；② A1 补 seed123/2024 + A1↔A2 L_f 配对；③ 出 A2 三 seed canary 轨迹核 Gate1；④ registry Gate3 同步；⑤ 02 全文 L_f 数值预言(0.2-0.5/0.35/(1+L_f)^S)按实测返修或标待验。
- **命中率**：若 #1 修后 L_f<1 → 回 Gate1 PASS 走 GREEN（稳定性核心）；若真>1 → 转退路 B（「latent NCA+SN 仍 L_f>1 无法形式收缩」当独家负结果发稳定性理论）。
- 训练锁已请用户删（powershell-via-bash 被门禁拦）。本轮文件：3 个 S config + 多处 framing 收敛(writer) + L_f bug 诊断 + 全 eval csv/图。

## 2026-06-16 — A1/A2 NCA 臂 pilot 批量首训启动（HPC，用户放行）
- **用户拍板放行训练**：canary 串行先验 → 4 卡并行批量。持 `.portfolio/locks/training.lock`（全 7 job 镜像）。
- **trade-off 扫描前件落地**：建 `configs/a2_scp_nca_vits_nih10k_S{4,8,32}.yaml`（除 `nca_steps` 外与 a2 S16 完全一致，复现零偏离）；`hpc/sbatch_pilot.sh` 加 `a2_s4/a2_s8/a2_s32` 映射；eval_anytime aggregate 按文件名当 label，吃新 S 命名无需改。
- **🟢 canary A2_s42（job 1450889）健康** = scp_nca 训练 loop 真 GPU 首验通过（NCA 臂从没端到端训过的集成风险解除）：ep1 loss 0.318 → ep1 avg 0.209 → ep4 loss 0.200，有限无 NaN，warmup lr 正常，~120ms/iter。`[ERR]` 误报（grep 抓到 `torch.cuda.amp.autocast` 弃用警告字样）。
- **批量 7 job 提交**（qos 4 卡，pend 自动排队）：1450889 a2_s42(canary) / 1450891 a1_s42(vanilla 发散对照) / 1450892 a2s4_s42 / 1450893 a2s8_s42 / 1450894 a2s32_s42 / 1450895 a2_s123 / 1450896 a2_s2024。后三 PENDING(QOSMaxJobsPerUserLimit，正常)。config sanity 确认 predictor_type/S 值全对。
- **监控**：Monitor `_hpc_mon_batch.py` 盯全 7 job state+loss+发散/错误/终态（A1 vanilla 发散是预期对照非 bug）。
- **目的**：A2 三 seed(42/123/2024)→Gate1 收敛判定；S∈{4,8,16,32}→§9.1 trade-off 主图（A0+ 基准线已在 Q1=0.975）；A1 vs A2→稳定化三件套是否压塌缩/发散。
- **⚠️ 并发暴露两个 infra bug（已修，非训练语义偏离）**：首批 4 job（a2s4/a2s32/a2_s123/a2_s2024）报 `Traceback` 但 slurm 标 COMPLETED（sbatch 末尾 echo 吞了 python 退出码）。根因二连：① `distributed.py` 固定 `MASTER_PORT=40112`+`MASTER_ADDR=localhost`，同节点多 job 抢端口→`init_process_group` 失败→落回 ws=1 但 `train.py:275` 仍无条件调 DDP→「Default process group has not been initialized」崩；② checkpoint 路径 `folder/jepa-latest.pth.tar` **不含 seed**，同臂多 seed 并发会互撞且只剩末位 ckpt。
- **修复（纯 infra，不碰 lr/步数/架构/数据，复现零偏离）**：① sbatch 按 `SLURM_JOB_ID` 注入唯一 `MASTER_PORT`；② `distributed.py` 改 `setdefault` 认 env 端口；③ `train.py` folder 加 `_seed{N}` 后缀隔离。3 个运行中 job（889/891/893，老码）不受推码影响，继续健康；4 个失败 resubmit（898/899/900/901，新码）端口/目录全唯一，a2s4(898) 复跑没再崩。
- **3 活 job 收敛健康**（监控实时）：a2_s42 loss→0.159、a1_s42→0.147、a2s8_s42→0.191（均 ep 多步，无 NaN）。
- **下一步**：全批 COMPLETED → 各 ckpt 跑 eval_anytime（注意 ckpt 路径：老码 889/891/893 无 seed 后缀，新码 898-901 有 `_seed{N}`）→ aggregate 出 trade-off 图 → Gate1/Gate3 判定。删训练锁。

## 2026-06-16 — A0+ 臂落地 + stability-vs-anytime trade-off 升一等指标
- **拍板执行探路两大 framing 决策**（探路报告 §5 致命伤①②）：用户拍板后 2 researcher 并行查官方源 → 落档。
- **新增 A0+ 臂**（4→5 臂）：early-exit ViT predictor = N 层 ViT + 每层 `Linear(pred_emb,enc_emb)` L2 head + **等权聚合**（MSDNet 官方 `ParallelCriterion` weight=1，ICLR'18 1703.09844；MeViT 2106.15183 证 early-exit+regression 可行）。参数 ≈ A0 不偷加。打死「ViT 也能 early-exit」reviewer 攻击（reject 级）。
- **意外强 novelty**：全网零 anytime-SSL-predictor 先例——early-exit 全在分类/判别 fine-tune，没人在 JEPA latent-regression predictor 位做早退 → ②牌空白确认，写入 related work。
- **②anytime 升一等指标**（03_pilot 新 §9.1）：stability-vs-anytime trade-off。Q(k) 曲线族（多 L_f/SN 强度 + A0+ 同台）+ anytime-gain(Q8/Q64) vs stability-margin(1−L_f) 散点。理论根 Bassily 2018（1804.01619「收敛快⇄稳定差」）+ DEQ Bai 2019（1909.01377 收缩-表达张力）。02 新增**性质 4.2**（稳定化压缩 anytime 有效区间 k*，🟡）。
- **诚实预案**：测出「稳定区 anytime 无意义」也是可发表负结果（best-compromise S），不藏。阈值（gain≥0.85/<0.7）标工程 go/no-go 非论文 claim。
- **口径修正**：01 §四②行「ViT 结构上做不到」→「默认全或无，加早退头可 anytime 但需额外 head+loss 且 SSL predictor 位无先例」；Q(k)=cosine（latent regression）非分割 Dice。
- 落档：03_pilot §5/§9.1/§14 + 01 §七/§八/§十三/§十五 + 02 §4.1/§7/§8 + registry(a0plus 臂/Gate3)。
- **3 TODO 已查清（红线10，researcher 第 3 派）**：① loss-weight 全程等权 w=1（MSDNet 正文+源码硬编码，无变体）；② exit-head=LayerNorm+Linear（MeViT MLP-EE 退化版 + I-JEPA predictor_proj）；③ stop-grad 全回传（I-JEPA/MSDNet/MeViT 三源一致，predictor 内无 detach），stop-grad 变体留 Phase1 实测。**官方默认与代码骨架完全吻合，零返工**。
- **A0+ 代码已落地**：`ijepa/src/models/earlyexit_vit_predictor.py`（`EarlyExitViTPredictor`：训练返回各 exit list、推理 `exit_layer=k` 单点）+ `helper.py` 分支 + `train.py` loss_fn list 等权 + config `a0plus_earlyexit_vit_vits_nih10k.yaml`。
- **评估工具链已落地（§9.1 一等指标产出）**：`nca_predictor.py` forward 加 `exit_step`（NCA 早退）+ **`eval_anytime.py`**（eval 模式出 Q(k) csv+曲线+L_f power iteration；aggregate 模式出 trade-off 主图曲线族+副图散点）。本地 CPU smoke 全通（`_scratch/smoke_a0plus.py` 6 项 + eval_anytime 双臂 + aggregate 图）。
- **参数实测核对**：A0=11.0M / A0+=11.76M(+6.7%) / NCA=3.22M；改了 4 处「A0+ 与 NCA 同量级」错述（NCA 实际省参 3.4×）。
- **工作报告**：`06_A0+_anytime_trade-off_落地_2026-06-16.md`（交付 + 完成度审计 + 继续命令）。
- **诚实缺口（见 06 §7）**：① 真数据 smoke + 训练未跑（待拍，串行红线）；② **SN 强度旋钮设计问题**——PyTorch spectral_norm 固定 σ→1 不能设目标 L_f，§9.1「扫 L_f」改用 nca_steps S∈{4,8,16,32} 当主旋钮 + L_f 实测，真扫 L_f 需另加约束机制（Phase1 开放项，不臆想）；③ hpc sbatch 加 a0plus 映射 + 多 S 配置待补。
- **本地真数据全链路 smoke 通过**（`_scratch/smoke_train_a0plus.py`，GPU）：真 MBMaskCollator + encoder + EMA + a0plus + loss list 等权 + backward + EMA，1 step 全过；A0+ 6 exit shape 全 == target；**等权 loss 初值 0.4796 ≈ A0 baseline 0.476**（job 1450052）→ 集成正确、真训练会健康。`hpc/sbatch_pilot.sh` 加 a0plus 映射。
- **✅ HPC 真数据 smoke 通过**（用户选项落地）：VPN 通 → 推 7 文件（earlyexit/nca/helper/train/config/sbatch/eval_anytime）→ HPC import 链 OK → login CPU 真 NIH 全链路 smoke `loss=0.4796`（与本地一致，≈A0 baseline 0.476），rc=0。`_scratch/_hpc_push_a0plus.py` 一键推+smoke。
- **✅ A0+ seed42 首训健康完成**（job 1450845，持 training.lock→完删）：sacct COMPLETED ExitCode 0:0，跑满 50ep，avg loss 0.088（6-exit 等权均值，浅层拉高，正常），VERDICT HEALTHY，无报错。31min（比 A0 16min 慢=6 exit 多反传）。
- **✅ A0+ anytime 真信号**（eval_anytime on jepa-ep50，ckpt 载入 missing=0）：Q(k)=0.975/0.986/0.992/0.994/0.997/1.000（k=1..6），**单调上升=anytime 有效**（合 Jazbec conditional monotonicity）；anytime-gain Q(4)/Q(6)=0.994。csv `results/anytime_a0plus_s42.csv`（已核）。
- **⚠️ 战略洞察（诚实）**：A0+ **Q(1)=0.975 已极高 → ViT early-exit 几乎无损、anytime 动态范围窄**。即「ViT 也能 early-exit 且本任务几乎完美」——②牌压力实锤。NCA 要赢不能靠「anytime 更准」，得差异化（稳定性维度 / 更激进早退 / 省参下的 anytime）。这正是 §9.1 trade-off 要诚实呈现的，须 A1/A2 的 Q(k) 同台才完整。
- **下一步**：拍 A1/A2 训练（NCA 臂，待用户「跑」）→ 各自 eval_anytime Q(k) → aggregate 出 trade-off 图（A0+ 基准线已就位）→ 看 NCA 动态范围 vs A0+ → Gate1/3。


- **5 路并行探路**（4 researcher sonnet + 1 reviewer opus，组合台系统首次实战）→ 报告 `05_探路_2026-06-16.md`。
- **致命发现**：①稳定区=anytime 最弱区（trade-off 须升 pilot 一等指标）②三张牌打 ViT 稻草人（缺 early-exit ViT 对照臂 A0+）③Kvalsund&Stovold 2026（2604.12720）实证 NCA 振荡吸引子非固定点（须主动引区隔）④resilience MICCAI 2026 占④不确定性牌；RadJEPA 2026-01 占医学 JEPA（ViT predictor）；NCA-as-SSL-predictor 仍全网空白。
- **venue**：NeurIPS 2026 已过；ICLR 2027 ~9 月（主线 3 月冲刺）；MICCAI 2027 ~2 月（退路 C）。2027 CFP 未出盯官网。
- **超参**：5/6 官方源，deterministic 自创已正确标；nca_steps=16 加 ablation {8,16,32}。
- **✅ 安全修正落地**（caveman off 精修）：01/02/README「可证稳定」→「稳定性可分析可控」；02「定理 6.1」→「性质 6.1」🟢→🟡（无证明不叫定理）；02 §5.1(b) 上界冒等式 → 标 🟡「至多…需实测」；02 加 Kvalsund 防御注（像素 vs latent）；01 加 RadJEPA related-work 行；03_pilot 头 A0 状态统一（A0 done / A1A2 pending）。
- **待用户拍的大 framing 决策（未动）**：加 A0+ early-exit ViT 对照臂 + stability-vs-anytime trade-off 升一等指标。
- 系统：teams flag 开 + /paper-scout skill 建；自定义 agent/team 需**重启 CC** 激活。本轮产出未 commit（待收工）。

## 2026-06-16 — 实验阶段启 + HPC 部署验通
- 地基搭建完：`facebookresearch/ijepa` 集成 + NCA predictor + 8 哨兵；smoke 全过。
- HPC 全量部署验通：`/gpfs/work/bio/jiayu2403/nca-jepa/`，env `yjcu124py310`，NIH 112120 图全解压、pilot 10k 子集泄漏 0。
- 哨兵门 **7/8 PASS**（s4 边界非 bug）。
- **A0 baseline 训练健康跑通**：job 1450052，loss 0.476→0.056@ep10，50ep ~16min。
- 红线10 官方超参联网复核完成：`configs/PROVENANCE.md`（~90% 真 CheXWorld 官方值，偏差全有意/已澄清，A0 不需重训）。
- **下一步**：A0 训完 → Gate0 → A1/A2 多 seed。**待用户放行**（训练串行红线，HPC 提交主线亲自做）。

> 早于本日的复现+pilot 设计 entry 见 `../PROJECT_LOG.md`。
