# NCA-PhaseMap PROJECT LOG

> 进度留痕。倒序（最新在上）。

---

## Entry 15 — 🗄️ 封存（第三次重启降级版也 FAIL，用户拍板，2026-06-22）

**终局**：同一主题三次 FAIL，不再重启——①2026-06-17 立项(C044) → ②2026-06-18 Gate1 K1/A2/A4 FAIL → ③2026-06-22 第三次重启降级版机制段 K-new-3 FAIL。

**这次封存原因（诚实，不粉饰）**：现象段做成了，机制段没成。
- ✅ **现象段 solid**：补1/补3 坐实「条件性相变」——BraTS no-clip w=0.30/ur*0.66、Hippo no-clip w=0.20/ur*0.34，双数据集 5seed 宽概率过渡带（非尖锐非纯随机）；clip 是锐化旋钮（2×2 toy验）；数据集定临界位置。
- ❌ **机制段 K-new-3 FAIL**：臂2（ckpt 辅证）有干净相关（σ↓/d↑ edge-of-chaos），但臂1（真训练主证）**先驱判负**——σ/d 与 dice 同步崩（n_neg=0 从不先驱、88%同步）+ 早期预测弱（σ AUC0.37 反向/d 0.58 n不足）。机制量证不了**先驱/因果**，只能 claim 相关。按预登记冻结 K-new-3「时序同步非先驱→降 TMLR」触发。

**为什么不降 TMLR 继续而是封存**：用户判第三次重启降级版机制也 fail，现象段虽 solid 但不值得为 TMLR 再投入，止损封存。

**带走的硬资产**（可后续他用）：
1. 条件性相变现象（补1/补3，双数据集 5seed 真数据）。
2. clip 旋钮 2×2（toy验，clip 锐化相边界、数据集定位置）。
3. 臂2 σ↓/d↑ ckpt 相关机制（edge-of-chaos 描述性签名）。
4. 理论审计吸收态相变骨架（`reference/THEORY_LEDGER.md`，finite-size 概率带）。
5. **反跑偏纪律链**（本程最值）：skeptic 拦循环论证、真烟测抓 path A 随机权重无信号、ρ 背景态→前景态修正、先驱诚实判负不 HARKing——每一步都没让机制段跑偏成假阳。
6. 一套可复用机制探针（probe_sigma/dn/ckpt_inference + G_mech_traj 时序 + G_sensitivity 符号检验 + mech_early_predict AUC），换项目可用。

**复活门槛**：需要全新的、能证先驱/因果的机制角度（现有三量 σ/d/ρ 已证同步非先驱），否则不重启。

---

## Entry 14 — 🔴 补2 臂1 跑完：σ/d 同步非先驱 + 早期预测弱 → K-new-3 触发，机制段诚实降 TMLR（2026-06-22）

**臂1 全跑**（G_mech_traj 真训练逐 step 测 σ/d，21 run=5config×3seed no-clip + 2 clip 对照，gpu_slot local GO d658abb1 exit0 已 release，mech_interval=10/sigma_rollout=150）。7 config csv 各 ~900 行完整。

**先驱符号检验（G_sensitivity --mech，27 组×run，判据跑前冻结）**：
```
σ VERDICT=MIXED  n_neg=0  n_pos=69  n_zero=498  total=567
d VERDICT=MIXED  n_neg=0  n_pos=69  n_zero=498
→ NOT_PRECURSOR：n_neg=0（从不先于 dice 塌）、88%同步、其余滞后
```
**早期预测 AUC（mech_early_predict，step≤50，n=15: +9塌/-6活）**：
```
sigma_mean_neg AUC=0.389 CI[0.07,0.72] NOT_PREDICTIVE（<0.5 反向）
sigma_last_neg AUC=0.370 NOT_PREDICTIVE
d_mean         AUC=0.574 CI[0.25,0.87] DIRECTION_N_SMALL
d_last         AUC=0.583 CI[0.29,0.87] DIRECTION_N_SMALL
→ K_NEW3_EARLY_PREDICT_WEAK（d 弱方向、σ 反向、n 不足）
```

**🔴 K-new-3 触发（两部判据都没过，预登记冻结判据，不 HARKing）**：
- 先驱 FAIL（NOT_PRECURSOR，同 A3 梯度同步非先驱同款）
- 早期预测 FAIL（WEAK）
- 按冻结 K-new-3「时序同步非先驱 or 早期不预测 → 降 TMLR/workshop 不冲 ACCV」→ **触发**。

**诚实定性（不粉饰）**：σ/d 与 update 稀疏度/塌缩区有**干净关联**（臂2 坐实 σ↓/d↑ edge-of-chaos），但**不是塌缩先驱**——机制量与 dice **同步崩**，证不了因果/先驱。机制段天花板 = **相关 + 描述性 edge-of-chaos 签名**，够不到「机制预言塌缩」的 ACCV 因果档。

**🛑 拍板点（stage-gate FAIL 方向，CLAUDE.md 拍板点5）**：机制段诚实降 TMLR/MIDL（现象段补1/补3 条件性相变 solid + 臂2 相关性机制做辅）。不擅自改判据救、不把相关粉饰成因果。venue 降级待用户拍。

**带走的硬资产**：①补1/补3 条件性相变现象（双数据集 5seed，rho0.98/0.20宽带）②clip 旋钮 2×2（toy验）③臂2 σ↓/d↑ edge-of-chaos 相关机制 ④理论审计吸收态骨架 ⑤反跑偏纪律链（skeptic 拦循环+烟测抓 path A 无信号+先驱诚实判负）。

---

## Entry 13 — 补2 臂1 代码就绪（G_mech_traj + G_sensitivity 扩 + mech_early_predict，2026-06-22）

**新建/改动文件**：
- `06_experiments/G_mech_traj.py`：臂1 主脚本。fork G_gradient_traj run_traj，每 k=5 step deepcopy 快照测 σ(t)/d(t)/ρ(t)。被试：BraTS ur{0.50,0.65,0.80}+Hippo ur{0.30,0.45}×seed{42,43,44}×clip{None,+对照}，300 step。入口 `--run_id brats_050` / `--all` / `--smoke 1`。
- `06_experiments/G_sensitivity.py`（扩）：加 `--mech` 模式，读 G_mech_traj_*.csv，σ/d 各跑 27 组符号检验。**符号方向各量独立**：σ 降=sign<0 先驱；d 升=sign<0 先驱（P_X 倒置高百分位）。旧 grad 模式完全兼容。
- `06_experiments/mech_early_predict.py`：早期预测 AUC。step<=50 σ/d 特征→最终 collapse 标签，单变量 AUC + bootstrap 1000 CI + LOO-AUC（纯 numpy）。collapse 阈从 B0 读（BraTS=0.012883/Hippo=0.116746）。

**静态检查**：py_compile ✅ 全三文件通过。

**算力提示**：σ 快照 N_roll=200 步×60 快照/run 是大头。主线降本：`--mech_interval 10 --sigma_rollout 150`。

---

## Entry 12 — 🎯 补2 臂2 信号验证强 PASS：σ↓ + d↑ 双独立机制腿，edge-of-chaos 骨架（2026-06-22）

**臂2 全跑**（官方 r1_hippocampus epoch_300 健康 ckpt，固定权重变 inference-ur，12 ur×3 seed，gpu_slot local GO c08332db exit0 已 release）。ckpt 真加载（"Reload State 300"，ca1_std=0.094/ca2_std=0.106≫0.01 init，ckpt_verified=True）。

**σ/ρ/d(N=16) vs inference-ur（Bash 核 csv，均值/seed）**：
```
σ:        0.25→0.961 ... 0.80→0.813   单调↓ span=0.149
d(N=16):  0.25→0.000 ... 0.80→1.179   单调↑ span=1.179
ρ_fg:     0.25→1.139 ... 0.80→1.148   flat span=0.015（无信号，淘汰）
```

**🎯 信号 crux 强 PASS（path A 随机权重无信号 → 真 ckpt 权重双腿有信号）**：
- **σ 单调降**：update 越稀疏→branching ratio 越低→趋吸收态；高 ur(塌缩区) σ=0.81<<1 亚临界。
- **d(N=16) 单调升**：update 越稀疏→damage spreading 越大→趋混沌/不稳定。
- 合 = 「稀疏更新推网络向不稳定（σ↓吸收 + d↑混沌）→ 塌缩」= 干净 edge-of-chaos 机制骨架。
- **σ vs d 真独立两腿**（branching vs damage spreading 不同物理），非 σ≈ρ 冗余；**ρ_fg flat 淘汰**。两腿优于预期的「σ≈ρ+d」。
- d(N=4,8)=0 非 bug，步数太少传不开，N=16 正确尺度。

**诚实定性**：臂2=**辅证**（测 inference-ur 非 training-ur，proxy 一层，不证因果）。**主证靠臂1**（真训练时序，证先驱+早期预测）。

**ρ 修正回顾**：背景态 x0=0 时 ρ≈1.0000 flat（f'(0)≈0），改前景态后 ρ≈1.14 但仍 flat——ρ 这条腿对本问题无判别力，机制段主押 σ+d。

**下一步**：coder 建臂1（`G_mech_traj.py` fork G_gradient_traj 逐 step 测 σ/d + `G_sensitivity` 扩三量符号检验 + 早期预测 AUC）→ 跑真训练 → analyst 判 K-new-3（先驱 27/27 + 早期 AUC + 臂2 方向一致）。d(N) 已验有信号可直接用，ρ 可降权或留对照。

---

## Entry 11 — 补2 机制段启动：三量选型(researcher×3) + skeptic 抓循环论证致命伤 + planner 重设计（2026-06-22）

**用户拍板**：M1 机制探针是现在最该砸的（现象已立，机制段卡 ACCV 档 K-new-3）；选型三量三角验证；不考虑时间。

**机制量选型（researcher×3 并行，带文献）**：
- **脉冲传播半径 d(N)**（先驱/空间）：α-async CA 二阶相变 [nlin/0703044]+ERF [Luo2016]。⚠️ **arXiv 2310.14809 经核不是正式 metric 出处**（只有 2px/step 非正式估计），设计文档过度引用，须改标。
- **branching ratio σ**（吸收态标准序参量）：MR estimator [Wilting&Priesemann 2018 Nat Commun]，pip `mrestimator`，子采样鲁棒，RNN 先例 [2606.10384]。σ=1 APT 临界。
- **谱半径 ρ(J)/λ_max**（收缩域理论对照）：power iteration [locuslab/deq]，λ_max=0 是 CA 相变判据 [2606.14521]。
- NCA 主流文献（Growing/Med/Identity）全无这类分析 = 真空白差异化。

**🩺 skeptic 红队抓 2 致命伤（编码前拦下，红队价值实锤）**：
- 🔴 **循环论证**：训练后权重测三量 vs 终态 collapse = 网络塌了→输出全背景→σ<1/d≈0/ρ 退化是吸收态定义本身 = 零解释力。是对旧 M1「探针先于训练防循环」原则的回退。
- 🔴 **缺时序**：A3 已先例（梯度与 dice 同步非先驱），终态测量证不了先驱，最高只能 claim 相关。
- 🟠 σ≈ρ 可能数学同源（都是线性化吸收态主特征值）。

**planner 重设计（修两伤，落 `实验设计_2026-06-22_补2机制段.md`）**：①路A 解耦——三量在**受控随机初始化网络**测纯 fire_rate 依赖（破循环，fc1 非零修 nan bug + 不读训练 csv）；②时序臂——塌缩 run 逐 step 记三量 vs dice，复用 G_sensitivity 27 组符号检验证先驱；③corr(σ,ρ) 降双独立腿措辞；④K-new-3 数字门槛冻结（阈来自文献非自创）。~2.5 GPU·h。

**下一步**：researcher 核 d(N) metric 正式出处（🔴 阻塞）→ coder 实现探针（修 M1 + 新建 σ/ρ/corr + 扩 G_traj 加三量）→ 跑 → analyst 判 K-new-3。

**补2 coder 产出（2026-06-22 进行中）**：
- `06_experiments/probe_sigma.py` — σ（branching ratio）探针，受控 init，mrestimator，ur 网格×5 seed×{hippo,brats}
- `06_experiments/probe_rho.py` — ρ(J) 谱半径探针，power iteration + autograd vjp，同网格
- `06_experiments/probe_corr.py` — corr(σ,ρ) 后处理，Pearson+Spearman，|r|≥0.9 触发双腿措辞
- `06_experiments/probe_dn.py` — d(N) 脉冲传播半径探针，双副本法+预生成共享 mask，θ=peak/e，ur 网格×5 seed×{hippo,brats,synthetic}×N∈{4,8,16,32}
- coder 风险标注：mrestimator API（最高，双路回退）、autograd vjp inplace op、非对称 J（σ_max vs λ_max，论文标"最大奇异值=谱半径保守上界"）、stochastic mask seed 固定、[MASK-1] 手动 update 须主线对照 BasicNCA.update 行 55-80 确认零偏离。

**d(N) metric 出处定（researcher 二轮）**：标准=damage spreading **前沿半径**（双副本+差值+最大前沿距离，cond-mat/9811159+review 0803.1602）；连续 NCA 阈 θ=峰值×(1/e)（Lieb-Robinson 指数衰减+ERF e⁻²，无 NCA 专属出处=proposed）；v(α) 无解析式（DP 幂律）。**论文定位「inspired by damage spreading」proposed heuristic，审稿风险中等**。arXiv 2310.14809 确认非源、删引。

**🔴 真烟测抓到 path A 实证死掉（[[feedback_pytest_green_not_runnable]] 价值实锤）**：四探针 py_compile 全绿，但**受控随机初始化网络上全无信号**：
- `probe_rho` smoke：**ρ≈1.0000 flat**（1.000040/0.999966，所有 ur 钉在 1）——随机未训练网 fc1~0.01→Δ≈0→E[J]=I+p·Δ≈I→ρ≈1 与 ur 无关。
- `probe_dn` smoke：**d_front=0 n_active=1**（扰动传播信号<θ=peak/e）。
- `probe_sigma` smoke：**σ non-finite**（活跃时序退化）+ 代码 bug（mrestimator `fitfunc` 参数错 + f-string 格式符 bug）。
- **根因**：机制（传播/分支/谱结构）是**训练学出来的属性，不在随机权重里**。skeptic 破循环到随机初始化=破了循环也丢了信号（其盲区，烟测才暴露）。**测量函数本身没问题，只差真训练权重。**

**用户拍板（path A 死后）= 两者都跑**：①主证=**时序/早期预测臂**（真训练中逐 step 测三量，证先驱+早期值预测塌缩，破循环靠时序先于结果）；②辅证=**固定官方预训练 ckpt 跨 inference-ur** 探三量（有信号+单网不循环）。重派 planner 出两臂修正设计 + coder 复用测量函数+修 bug。

**臂2 coder 改动（2026-06-22）**：
- `06_experiments/probe_sigma.py` — 修2 bug：①`full_analysis` 去掉不兼容的 `fitfunc` 参数；②f-string 格式符条件表达式改为先算字符串再插值（L438 等同类全扫）
- `06_experiments/probe_rho.py` — 加 `--x0_mode {zero,foreground}`（默认 foreground）：foreground 模式取真实 patch 跑 8 步演化态做线性化点（破「x0=0 时 f'(0)≈0→ρ≈1 无信号」问题）；csv 新增 x0_mode 列
- `06_experiments/probe_ckpt_inference.py` — 【新建】臂2 主脚本：载官方 r1_hippocampus epoch_300 ckpt（via Experiment.reload()→load_state），自检 ca1/ca2 fc1.weight.std()>>0.01，冻结权重，变 inference-ur 测 σ/ρ(foreground)/d，输出 results/probe_ckpt_inference.csv（列：ur,fire_rate,inference_ur,mech,value,mask_seed,x0_mode,ckpt_verified,N）

---

## Entry 10 — 补3 Hippo no-clip 解开真命门：clip 是旋钮（toy验 partial），数据集只定位置（2026-06-22）

**补3 本地跑**（用户「跑」，gpu_slot local GO ced6331d，exit0，~10min，已 release）。Hippo no-clip 扩 ur{0.25..0.70}×5seed=40run。脚本加 `--dataset hippo` 支持（HipSliceDataset 官方管线，烟测验过 n=6498/reload state300）。

**Hippo no-clip 逐 ur（Bash 核 csv）**：
```
ur=0.25→1/5  0.30→0/5(活)  0.35→3/5  0.40→4/5  0.45→4/5  0.50→5/5(塌)  0.60→5/5  0.70→5/5
collapse_rate=[.2,0,.6,.8,.8,1,1,1]  w=0.20  ur*≈0.34-0.37  中段MIXED  diverged全0
```

**🎯 命门解开（skeptic Hippo 反例消解 + theorist no-clip预测双数据集坐实）**：原 Hippo「尖锐 STABLE_SHARP」是 **clip=1.0** 测的；no-clip 下 Hippo **也是宽概率带（w=0.20）**。

**2×2（analyst 严判）**：
| | clip=1.0 | no-clip(官方) |
|---|---|---|
| Hippo | ur*0.375 w~0.05 尖锐(3seed) | ur*0.34 w0.20 宽MIXED(5seed) |
| BraTS | ur*0.587 w~0.025 "尖锐"⚠️单seed+ur0.75复活 | ur*0.66 w0.30 宽MIXED(5seed) |

**机制 claim「clip 控宽窄、数据集控位置」**：两判据方向✅（同集 clip→noclip 一致变宽 Hippo4×/BraTS12×；同 clip 两集 ur* 差 0.21-0.32 显著）。**分档=toy验(partial)，不坐实**——BraTS clip=1.0 仅 seed42 单 seed + ur=0.75 复活异常。

**诚实定性**：官方 no-clip 下相变本就宽（两数据集都 w≥0.20、中段 seed 随机），clip 人为锐化。**禁反过来把 clip 尖锐当主结果 / 禁写「NCA 有尖锐相变」**。

**待补短板（analyst 提，ACCV 7/5 截稿 13 天紧）**：①BraTS clip=1.0 补 seed43/44（坐实 2×2，~5run 便宜）；②M1 probe bug 修（机制段，根因 `fc1.weight.zero_()`+单步 forward 响应恒零，换探针物理量）；③ur* 口径统一（collapse_rate 首跨 0.5 线性插值）。无 M1 读数 → 降 TMLR/MIDL analysis。

**🛑 停报拍板**：下一步走向（补 2×2 / 修 M1 / 冲 ACCV vs 收 TMLR）。图 `figures/补3_2x2_clip_knob.png`。

---

## Entry 9 — 🎯 补1 生死闸门跑完（本地 40run）：判定**灰区**（不 KILL 不翻案），停报拍板 headline（2026-06-22）

**补1 本地跑**（用户指定本地，gpu_slot local GO 69570345，exit0，~12min，已 release）。BraTS no-clip 扩 ur{0.45..0.80}×5seed。

**逐 ur collapse_rate（Bash 核 csv + analyst 复核一致）**：
```
ur=0.45→0/5(全活,dice0.629-0.696)  0.50→0/5(0.647-0.704)  0.55→1/5  0.60→1/5
ur=0.65→2/5  0.70→4/5  0.75→4/5  0.80→5/5(全塌,dice0.001)   diverged 全0
collapse_rate=[0,0,.2,.2,.4,.8,.8,1.0] 单调  Spearman rho=0.982 p<0.001
```

**analyst 判定（对 THEORY_LEDGER §4 冻结证伪条件，唯一判定）= 灰区（拍板点4停报）**：
- 翻案 ❌：过渡宽 w=0.30（最后0/5档ur0.50→首个5/5档ur0.80）>> 0.10，中段全 MIXED 无断崖。
- K-new-1 KILL ❌：非全 MIXED，有确定端点 0/5 + 5/5。
- 灰区 ✅：高端 5/5 = **真相变**（吸收态锁死、同 seed 塌后 dice 逐字相等、与中段塌缩同质，**非平凡饱和**）+ 过渡 >0.10。

**关键**：ur*≈0.6625（vs Hippo 0.375，漂 +0.29，超 ACCEPTANCE K1 PASS 区间[0.25,0.45]→普适尖锐版 A4 同步 FAIL，但降级版已弃该 claim）。种内非单调（seed43: ur0.70塌/0.75活/0.80塌）= w 宽的真随机来源，非 bug。

**与理论审计互证**：结果**证伪 theorist「全 MIXED 无相变」预测**（低端确有 0/5、高端确有 5/5=确定相变存在）→ **skeptic 拒绝理论先验 KILL 是对的**。但中段宽过渡带（概率性）又**部分印证** theorist 的 finite-size 概率带。真相 = BraTS no-clip 有**宽概率过渡带**，非尖锐非纯随机。

**analyst 建议**：①headline 改灰区诚实措辞（宽概率过渡带 + clip 是临界宽窄旋钮 vs Hippo 尖锐，对照叙事）；②**补3 Hippo no-clip 复核最优先**（<0.1 GPU·h，决定真命门——Hippo no-clip 尖不尖锐 → clip 旋钮机制成立 or BraTS 另有原因）；③不扩 10 seed（改不了灰区）。

**🛑 停报拍板**（灰区=偏离 STORY headline=拍板点4）：headline 怎么改 + 下一步走向，待用户定。图 `figures/补1_collapse_rate_curve.png`。

**status**：active，灰区待拍板。

---

## Entry 8 — 理论审计三层防线（/theory-audit diagnose）：理论给机制骨架但不预判 KILL，补1 实证说了算（2026-06-22）

**触发**：用户问「有推导过理论吗」。跑 /theory-audit nca-phasemap diagnose，归因核心威胁 A2（BraTS no-clip 全 MIXED）。产物 `reference/THEORY_LEDGER.md`（证伪条件已冻结防 HARKing）。

**三层结果**：
- **Layer1 theorist + 投票第2 theorist（2/2 同向）**：独立都推到「NCA 塌缩=吸收态相变，有限网格(64²)+前景稀疏(n_active~40-400)+逐cell伯努利噪声 → 临界本征是**概率带(B)非确定尖锐相变**，clip/前景占比是旋钮」。置信 65-80%，预测补1 全 MIXED。
- **Layer2 skeptic 4 致命伤把主归因①降级为「未坐实候选」**：①finite-size scaling 方向用反（有限数据测 MIXED 恰是确证尖锐临界的标准信号，非「无相变」证据）；②**Hippo 反例**（同机制 Hippo 尖锐 3/3,0/3 → 确定相变可达 → BraTS MIXED 必来自数据集特异因素②/③非 NCA 本征）；③理论不可证伪；④确认偏误贴合 KILL 倾向。**判决：K-new-1 KILL 必须由补1 实证触发，绝不能理论先验预判**（两 theorist 犯同一方向错=投票盲区）。
- **Layer3 verifier**：数字全核✅（B3 塌缩率 2/1/2/3/3、阈 0.012882、grad 同步归零、impl2 0/15）。揪出潜在 bug：G_traj ur=0.45 seed=42 step179 塌但 B2 标 collapsed=0（脚本差异 or seed级随机直接证据）。

**净产出**：(a) 降级版 headline 机制骨架立住=「条件性概率相变 + clip/前景占比旋钮」（三方认可，胜过原「普适尖锐」）；(b) 揪出真命门=**Hippo no-clip 尖锐性待核**（决定 Hippo 反例有效性/①能否复活）；(c) 正中 [[feedback_falsify_crux_first]]，没掉进「理论自洽当地基对」坑。

**用户拍板**：①补1 维持 5 seed（判据是整段单调非单档，5 够；borderline 再扩 10）；②补3/4 等补1 出结果再决。

**待办（落 ledger §7）**：Hippo no-clip 尖锐性核、G_traj/B2 标注矛盾查、n_active 真值、clip 压方差定量链。

---

## Entry 7 — 补1（生死闸门）就绪+上传 HPC，卡 QOS 提交配额，挂轮询等排空（2026-06-22）

**做了**：
- 改 `B1_B2_B3_sweep.py`：`build_grid_b3` 加 `--ur_list`/`--out_suffix`（纯增量、向后兼容）。本地烟测 PASS（exit0、grid=40run/8ur/5seed/no-clip、collapse_thresh=0.012882 与既有 B3 一致、新参数全流程通）。
- 新建 `_hpc/sb_B3ext.sh`：补1 提交脚本，输出 `B3_ext_brats_seed.csv`（**不覆盖**旧 `B3_seed.csv`）。
- 上传 HPC + 远端验证：sweep size 一致(22475)、`ur_list`/`out_suffix` 改动在位、`py_compile` OK、`.sh` 去 CRLF。

**补1 配置**（打核心威胁 A2）：BraTS no-clip，ur∈{0.45,0.50,0.55,0.60,0.65,0.70,0.75,0.80}×5seed=40run，注入 `DICE_BG_BRATS=0.005421 SIGMA_BG_BRATS=0.002487`（B0 冻结阈，不重标）。~0.3 GPU·h。
- K-new-1 KILL：全档 MIXED（无 5/5 无 0/5）→ 彻底收口不再重启。
- 翻案 PASS：collapse_rate 单调跨 0→1（低端≥1档 0/5 + 高端≥1档 5/5 + 过渡 ≤0.10ur）。

**🚧 阻塞（计划外，跨窗争用）**：`sbatch` 被拒 `QOSMaxSubmitJobPerUserLimit`。诊断 squeue：gdn2vessel 提了 job array `1484215_[0-7]`=gsweep（3 RUNNING + 5 PENDING）占满 QOS `4gpus` 单用户提交上限 8（且 MaxJobsPerUser=4 运行位）。补1 短期挤不进。`gpu_slot.py` GO 了但只记 phasemap 自己的账、不知 gdn2vessel 直 sbatch 的 array 吃了 HPC 配额——已 release 假占的 f3f58467。

**决策（用户拍板）**：自动轮询等排空——挂 ScheduleWakeup 每 ~25min 查 squeue，gdn2vessel array 掉到 <8 提交位+有空卡 → 自动 gpu_slot request + sbatch 补1。不抢 gdn2vessel。

**复用启动器**：`06_experiments/_scratch_launch_b3ext.py`（已上传+提交逻辑，含 squeue 验证；resubmit 直接复跑）。

**下一步**：轮询命中 → sbatch → 看 `B3_ext_brats_seed.csv` 产出 → analyst 判 K-new-1。

---

## Entry 6 — 🔄 第三次重启（用户拍板，run-009 重筛 C044 胜出，降级版冲 ACCV）（2026-06-22）

**诚实定性**：本项目历史 = ①2026-06-17 立项(C044) → ②2026-06-18 Gate1 三项 FAIL 封存（K1/A2/A4）。**本次是第三次重启同一主题**，触 stage-gate FAIL 放行红线。用户在充分知情（run-009 全程了解 NCA 5 轮天花板 + C044/PhaseMap 全部硬伤）下拍板复活。

**复活依据**：run-009（NCA 迭代=test-time compute × 医学影像）核心命题**实锤死**（健康 official ckpt 重测：步数-Dice 倒 U，16 步峰 0.864、64 步崩 0.019，非小问题、非作者瞎说，是 NCA 步数≈训练步数本性）。转向 NCA 顺本性特长冲 ACCV。重筛 4 存活候选（S6-002 / S5-006 / S4b-011 烟测已FAIL / C044），**C044 横向胜出**：唯一实验已做完（三轮坐实）+ 外部不撞车（2508.06389 三重正交）+ 最顺本性（自组织/训练动力学分析）+ 不赌步数。

**降级叙事（弃旧主 claim）**：
- ❌ 弃：「NCA **尖锐、可前验、seed 稳定的普适**临界相边界」（Gate1 K1/A2 已证伪）。
- ✅ 改：「NCA 医学分割训练中 update 稀疏度功能塌缩的**条件性**刻画——Hippo+clip=1.0 有确定断崖，BraTS/no-clip/跨 seed 不稳；正面贡献 = 刻画相变**成立/不成立的条件** + 谱半径/信息传播机制解释（PRIMER §6.4/6.7）+ NCA 训练**安全 fire_rate 区间实践指南**」。

**🔴 必须正面处理的硬伤（不掩盖）**：
- **A2 FAIL 是核心威胁**：BraTS 5ur×5seed 塌缩率全 MIXED（2/5,1/5,2/5,3/5,3/5）= 相变可能是**随机塌缩概率事件而非确定边界**。补实验后仍翻不了案 → 「相变」概念站不住，须诚实收口。
- A4：第二实现 dice 0.3 vs 官方 0.7 = 无效对照，须找真对齐实现。
- M1 传播半径 probe bug（全 nan 静默失败）= 机制段无实证基础，必修。

**venue**：顶档 ACCV 2026（CCF-C，analysis 可发不需碾压 SOTA）；退路 MIDL/ISBI 2027 / TMLR。注：gdn2vessel 已投同会 ACCV 2026（Transformer 血管，不撞）。

**4 项补实验（Gate1-重启 TODO）**：① 修 M1 probe bug→跑机制探针；② BraTS no-clip 扩 ur(0.45–0.80,步长0.05,5seed)→判临界漂移vs消失；③ Hippo vs BraTS 差异机制假设(前景占比/patch)+单变量实验；④ 找对齐第二实现替 MinimalNCA。

**重启版 kill criteria（比上次硬，防第四次重启）**：
- **K-new-1**：4 补实验后跨 seed 相变仍随机（A2 翻不了案）→ 承认无确定相变，**彻底收口不再重启**。
- **K-new-2**：BraTS 全程任何条件无断崖 → 降纯 Hippo 单集 analysis（弱）或收口。
- **K-new-3**：机制段（谱半径/传播半径↔ur 临界）拿不出实证关联 → 诚实 TMLR/workshop 不冲。

**下一步**：`/design-experiment nca-phasemap` 设计 4 补实验矩阵 → 跑 → Gate1-重启严判。状态 shelved → **active（ACCV）**。

---

## Entry 5 — Gate1 全跑完 + 去留判决：headline 在 BraTS 没复现，重降级/KILL 待拍（2026-06-18，analyst）

**全实验落地**（HPC，全本地下载 `06_experiments/results/`）：B0/B1/B2/B3/B4/G/M1 七作业全完。analyst 出 `05_Gate1_去留报告.md` + figures/（K1/A2/A3/A4 各一图）。

**逐判据（数字主线 Bash 核 csv 原值）**：
- **K1 临界尖锐普适 → 🔴 FAIL**：BraTS no-clip（官方主条件）塌缩 ur=[0.625, 0.725, 0.75] **散点非单调**——0.625 塌、0.65/0.675/0.7 活、0.725/0.75 再塌。无单调断崖，过渡宽 ≫0.10。触 ACCEPTANCE K1「临界消失」。（clip=1.0 反而有干净断崖 ur*≈0.60，但非官方条件不计）。
- **A2 seed 稳定 → 🔴 FAIL**：B3 临界区 5ur×5seed no-clip，每 ur 塌缩率 2/5,1/5,2/5,3/5,3/5——**全 MIXED，无一全塌或全活**。塌缩是 seed 随机概率事件，非 seed 稳定边界。与 Hippo G5 STABLE_SHARP（0.40 三 seed 全塌）完全相反。B1/B2 的「非单调」即 seed-randomness 假象。
- **A4 第二实现 → 🔴 FAIL**：MinimalNCA_impl2 在 Hippo ur 0.3-0.5 全 0/15 塌缩，且最活档 dice 仅 0.21-0.35（官方 ~0.70），基础性能不对等=无效对照，无相变。
- **A3 梯度因果 → 🟢 PASS**：G_traj no-clip 塌缩档，grad_norm 与 dice_proxy 同步崩溃，梯度非前驱（K4 未触发）。支柱2「塌缩非梯度驱动」在 no-clip 下仍成立。
- **M1 传播半径探针 → ⚪ probe bug**：27 行全 n_active_pixels=0 / d_mean NaN，静默失败（theta=0.1 或 pulse 注入逻辑错），无有效机制信号。

**🔴-6 副产**：clip 改变相变形态（clip 有干净断崖、no-clip 没有）——证 G5 历史「尖锐断崖」依赖非官方 clip=1.0。是方法学诚实点，非 headline。

**analyst 判决=重降级（不全 KILL）**：撤「可前验普适尖锐临界」主叙事；保留 Hippo 单集相变 + A3 梯度方向 + 🔴-6 clip 影响，降 TMLR/MIDL/ICBINB analysis/负结果轨。建议补一轮 BraTS no-clip 全区间 0.45-0.80 5seed 确认无稳定塌缩区，再定彻底 KILL vs 降级。

**🛑 拍板点（stage-gate FAIL）→ 用户拍板 = ①KILL 封存**（2026-06-18）。止损：残值（A3 梯度方向 + 🔴-6 clip 方法学 + Hippo 单集相变）做不成有分量论文，封存留资产，资源回 P1 ICLR / 其他在跑项目。registry status→shelved。clip 发现可后续他用。NCA 本身未否决，仅此 update-稀疏度-临界单轴在 BraTS 证伪。HPC 卡槽全 release，结果全本地存档。

---

## Entry 4 — Gate1 开跑（2026-06-18，用户拍板 no-clip 主条件+开跑）

**拍板落实**：用户拍 ① 🔴-6 no-clip 改主条件（已在 STORY/ACCEPTANCE 写入，脚本 `run_one_cell` 默认 `clip_norm=None`=no-clip 主条件，B1 跑 {None,1.0} 两档对照、B3 仅 no-clip）② 数值订正（STORY line 12/16-17 区间表述，A1 过渡宽 ≤0.10）③ 开跑。

**发现并修 B0 崩溃 bug**：上轮 B0 job 1461115（11:35）崩于 `data_brats.py:135` `AttributeError: module 'PIL' has no attribute 'Image'`（`__import__('PIL').Image` 不自动加载子模块）。修为 `from PIL import Image as _PILImage`。本地烟测通过：BraTSSliceDataset 建成 1489 切片（1948 flair − 459 低前景<2%，no_mask=0），img/lbl (1,64,64)，fg=3.1%。重传 HPC（单文件，BraTS 1948 对数据已在不重传）。

**幽灵槽清理**：旧 nca-phasemap 槽 529bca01（B0 崩溃后没 release）→ `gpu_slot.py release` → 重申请 `GO 6f38bd06`（hpc 占 1/4 剩 2）。

**B0 已提交**：job=1462504 RUNNING gpu4090n4（sb_B0，walltime 20min）。产 BraTS+Hippo dice_bg/σ_bg → collapse 阈 `max(0.01, dice_bg+3σ)` 冻 config。

**下一步链（B0 done 后）**：注入 DICE_BG_BRATS/SIGMA_BG_BRATS → 提 B1 粗扫（9ur×{None,1.0}=18run）→ 读临界区 → B2 加密（±0.10 步0.025）→ B3 seed（5ur×5seed no-clip）+ 并行 G 梯度时序 + M1B4 探针。全完派 analyst 解读 → 写去留报告（必要性/天花板/风险）。

---

## Entry 3 — Gate1 实验脚本交付（2026-06-18，coder）

**脚本目录**：`project/meeting/NCA-PhaseMap/06_experiments/`

| 脚本 | 功能 |
|---|---|
| `data_brats.py` | P0 BraTSSliceDataset：tumor+annotation 配对，min-max 归一，前景<2% 排除，接口=HipSliceDataset |
| `B0_baseline.py` | 全背景解基线：产 dice_bg/σ_bg（BraTS+Hippo 两集），collapse 阈 = max(0.01, dice_bg+3σ) 冻 config |
| `B1_B2_B3_sweep.py` | 腿① 临界扫描：B1 粗扫/B2 加密/B3 seed，no-clip 主条件，clip=1.0 可选 flag，diverged 严记 |
| `B4_impl2.py` + `nca_impl2.py` | 腿①-b 第二独立 NCA 实现（mask=rand<update_rate 正向，超参全对齐官方） |
| `G_gradient_traj.py` | 腿② 梯度时序：每 step 落 per-layer grad_norm+dice_proxy+前景占比+diverged |
| `G_sensitivity.py` | 腿② 后处理：27 组 P_g×P_f×N 阈值敏感性，读 traj csv 算 sign(t_grad−t_func) 全稳性 |
| `M1_probe.py` | 腿③ 传播半径探针：单脉冲前向，d(ur) 形状曲线，标 proposed metric (arXiv 2310.14809) |

**collapse 判据（冻结）**：`collapse := (not diverged) and final_dice < max(0.01, dice_bg + 3·σ_bg)`，B0 跑后写 config 冻结，所有脚本从 config 读阈值。

---

## Entry 2 — Gate1 实验矩阵设计 + 红队收口（2026-06-18）

**流水线**：/design-experiment → planner 出矩阵 → skeptic 红队 → researcher 核超参 → 全纳修订定稿。落 `实验设计_Gate1_2026-06-18.md`。

**矩阵三腿（~85 run / ~1.7 GPU·h / 4 卡墙钟 ~0.5h，HPC）**：
- 腿① K1/A4 普适性：B0 全背景基线标定 → B1 粗扫 → B2 加密 → B3 5seed（BraTS 第二数据集临界复现）。
- 腿①-b A4 第二独立实现 B4（Hippo 上换 NCA 实现验非单实现 artifact）。
- 腿② A3/K4 因果：G1/G2/G3 梯度时序（塌/活/临界三档，逐 step 轨迹定梯度先死 vs 网络先垮）。
- 腿③ R1 机制 M1：单脉冲传播半径探针（预期大概率 K2）。

**skeptic 红队 2🔴+3🟡 全修**：
- 🔴-1 BraTS 前景 median 5%（实测）→ 绝对 `dice<0.01` 假性触发 collapse → 新增 B0 标定 + collapse 改相对自适应 `max(0.01, dice_bg+3σ)` + 真/假 KILL 流程 + 诚实回退备选。
- 🔴-2 A4「第二独立实现」漏腿 → 加 B4 对照（选 b，~0.1 GPU·h 补成整条）。
- 🟡-3+🟡-7 腿③ q=ur×T 单调=零预言力 → 判据从「穿阈」改「非单调拐点」，明说大概率 K2。
- 🟡-4 腿② 阈值拍脑袋 → 加 27 组敏感性扫描，符号全稳才升级 A3 因果。
- 🟡-5 K1 区间 [0.25,0.50] 过宽 → 挂钩实测 ur*_hippo±0.10，**预登记冻进 ACCEPTANCE + git 留痕防 HARKing**。

**🔴-6 researcher 逮到复现红线偏离（重磅）**：官方 Med-NCA `Agent.py` L102-103 **零 `clip_grad_norm_`**，G5 三重实证全带非官方 CLIP_NORM=1.0。致命=clip 把真实步长夹平 → A3「塌缩与名义 max_grad 无关 r=0.238」是 **clip artifact**，动摇 headline 支柱2。处置：no-clip 改主条件（对齐官方），clip=1.0 降对照解释 G5，腿①B1/B2+腿②G* 加 clip 维度，A3 必在 no-clip 重测。**已报用户拍板**。

**两拍板点报用户**：①🔴-6 no-clip 复现订正（G5 需 no-clip 复核，可能修正支柱2）②STORY headline 数值订正（过渡宽 ≤0.05→≤0.10、ur*≈0.375→区间）。+ P0 数据口径（BraTS train 无 mask，拟用 test/tumor+annotation 配对当扫描集）。

**下一步**：用户拍 🔴-6/数值订正/P0 口径 → 派 coder 写 P0 适配器 + no-clip 训练脚本 + B0/B4/腿②记录脚本 → HPC 卡槽申请跑（4 卡空）。

---

## Entry 1 — 立项（2026-06-17，用户拍板）

**立项决策**：源 = ideation run-003（NCA × 医学图像）G6 唯一存活旗舰 **C044**。用户拍板「立项 C044」。

**RQ / headline**：NCA 医学分割训练中 update 稀疏度（fire_rate/async 同一旋钮）存在尖锐可前验的功能塌缩临界相边界（update_rate≈0.375 / fire_rate≈0.625），越过即塌缩到平凡背景解，与梯度幅度无关——首次系统刻画。

**与边界**：纯新项目（非主论文拆分），与 ICLR/MedAD-FailMap/FMReg 零重叠。属 NCA 家族但**不在 nca-jepa/Med-NCA-AB 封存范围**（registry nca-jepa 条目已加 2026-06-17 scope 校正：封存仅限那两支实证死路 + NCA×世界模型交叉；NCA×医学影像单轴 run-003 不在内）。

**立项依据（G5 三重独立实证，主线核 csv 原值）**：
- 原 C044（36 cell）：19/36 功能塌缩（dice→0.0011，diverged 0/36=塌缩非发散），与 max_grad_norm 无关（r=0.238 p=0.16）。
- C044b（单轴 update_rate 细扫 12 cell）：临界 ur 0.35→0.40 断崖 dice 0.104→0.001（−94.9%）= SHARP。
- C044c（4 ur × 3 seed = 12 run）：STABLE_SHARP——ur=0.35 三 seed 全活、ur=0.40 三 seed 全塌。
- killshot 历程：C062 one-shot KILL（真塌）/ C001 anytime KILL（UNet 碾压）/ C044 PASS。researcher 核实不撞车（2508.06389 三重正交）+ 真空白。skeptic 红队 3🔴全可补救（语义错位→reframe / 共线→单旋钮非 confound / 撞车稻草人→不撞+reframe 更强）。
- csv：`ideation/runs/2026-06-17_run-003_nca-medimg/06_experiments/results/c044*.csv`；立项卡 `.../07_report/G6_proposal_card_C044.md`。

**诚实天花板**：当前中等会议料（单数据集 Hippocampus、小模型、存活区 dice 0.10-0.37）。standout 需立项后机制升级（ur 临界↔可前验量）+ BraTS/第二实现普适性。书面 kill criteria K1-K4 见 02_ACCEPTANCE。

**带债 / 立项后第一前置**：
- R1（机制）：ur 临界能否关联到可前验量（信息传播半径 × 更新稀疏度临界比）——决定 standout vs 中等会议。
- R2（普适性）：临界相变在 BraTS/第二独立实现是否复现（K1）。
- R3（因果）：梯度时序分析定"塌缩非梯度驱动"是相关还是因果（A3/K4）。

**下一步 Gate1**：`/design-experiment nca-phasemap` 出中训矩阵（第二数据集临界复现 + 梯度时序 + 机制量探索）。数据 Med-NCA Hippocampus 本地+HPC ready；BraTS 切片本地有（MedAD-FailMap/data/BraTS2021）。
