# NCA-Cyst — 进度日志（时间倒序，最新在上）

---

## 2026-07-11 · 🚩 用户拍板方向转向：Phase2 从 A（全局治囊肿）转 C（3D NCA 不确定性 × 囊肿），立项

**背景**：b 格 kill-shot 排队跑期间，用户问「NCA 怎么解决囊肿 + 学长说 NCA 天然带不确定性可解释、没人做」。派 3 researcher 并行侦察（novelty / 技术可行性 / venue+价值主张）。

**三 researcher 一致结论（全带 URL，落 THEORY_LEDGER H4）**：
- 🟢 机制真：`Model_BasicNCA3D.py:69-71` fire-rate 随机 mask、推理默认开、无 dropout → 多 rollout 天然出不确定性，零架构改动。
- 🔴 「没人做」被证伪：base model M3D-NCA 自带 NQM（N=10 rollout std）；**MICCAI'26 已接收** resilience（marrlab，github.com/marrlab/resilience）系统做了 NCA 不确定性。
- 🟢 但 delta 合法：竞品全 2D 通用 NCA、自然图，**没碰 3D/M3D-NCA 多尺度/KiTS/囊肿/极端不平衡**。
- 🟡 技术命门：vanilla rollout 方差可能太弱（需 pilot 最先证伪）。

**关键交互（诚实纠偏）**：我一度用「顶会蓝海」标尺把撞车当否决理由，用户纠正「有人做过相似≠不能发，学术就是做增量」——**我认错、收回**（记 [[feedback_skeptic_systematic_overkill]] 模式：对大胆方向习惯性存在性否决）。重校准：真问题是 delta 清不清、够不够 venue，不是有没有撞车。

**用户拍板（AskUserQuestion）**：立项，headline 核心卖点 = **不确定性/可解释**（非「分割赢别人」）。我拦下并改掉用户原话「囊肿别人做不了我们能做」——违 STORY 红线（天花板 0.447、二分类 0.82-0.90，一击破）+ 我们自己 b 格还没验（[[feedback_falsify_crux_first]]）。

**Headline v1 定稿**（THEORY_LEDGER H4）：KiTS23 囊肿这种主流模型都做不好（0.447 天花板）的极端不平衡场景，用 3D 多尺度 M3D-NCA 迭代动力学给出**校准良好、空间可解释的不确定性**，把「看不清囊肿」转成临床信号（漏检定位/QC/转诊）。不追 Dice，追校准+决策价值。venue=UNSURE workshop/ACCV（博士生+导师定）。

**落地**：在 NCA-Cyst 内转向（不开新项目），复用数据/骨干/baseline/b 格模型。THEORY_LEDGER 加 H4 冻结假设链。b 格 kill-shot **继续跑**（训出的囊肿模型正是 C 的 pilot 载体）。

**下一步（在跑）**：派 planner 设计方向 C 方案（RQ+命门 pilot+实验矩阵+评测协议 AURC/ECE/AUROC+对标 resilience delta 表）+ skeptic 红队立项前提（重点攻「Dice≈0 的模型谈不确定性是否空中楼阁」）。回来综合 → 更新 01_STORY/02_ACCEPTANCE 为 C 方向 → b 格出模型跑命门 pilot。

---

## 2026-07-11 · ✅ 用户拍板跑 2×2 kill-shot → CB-max 代码就绪 + 双烟测 PASS + 判据冻结 → 起 b 格

**背景**：上一 entry 四选一，用户选 **1 = 先跑 2×2 kill-shot 证伪 H2 命门**（再定 Phase2）。全流程走标准编队。

**做的事 + 结果**：
- **planner + researcher 并行探路**：planner 把 2×2 拆成精确矩阵（分阶段：先跑关键格 b=vanilla NCA+CB−GV，能 kill 就省掉 GV 工程）；researcher 查得 ①novelty「全图 pooling→broadcast NCA 分割」精确机制**未见发表=空白**（negative-evidence，c/d 前须人工二次核 arXiv+OpenReview）②类平衡锚：Focal Tversky α/β/γ=0.7/0.3/(4/3)、nnUNet oversample=0.33、**KiTS23 cyst 天花板仅 0.447**（现有类平衡有效证据都在 1–5% 前景，6.5e-5 是极端外推）。
- **主线亲核 load-bearing 发现**：官方 `DiceFocalLoss`（LossFunctions.py L162-181）focal 项在 flatten 全体素上 `softmax(dim=-1)` → 每体素≈1/N → `(1-logit)^γ≈1` → **focal 退化成 BCE**。即 A2 baseline 名义有 focal、实质无类平衡 → 坐实 kill-shot 合法性（`+CB` 是真补缺失的类平衡，非重复）。
- **skeptic 红队砸中 1 致命伤**：planner 的弱 CB（前景采样≥1体素）对 **patch 内前景占比** 无控制 → b 假阴性 → 假阳性 greenlight。实测坐实（`kits23_cyst_dist.csv`：含囊肿 248 例、囊肿绝对体素中位 **2317**、整颗落入 1.05M patch 占比也仅 **~0.22% ≪ 1–5%**）。kill 方向（b≥0.10→H2塌）本就稳健，修复只保护 greenlight 半边。
- **用户拍板 CB-max**（AskUserQuestion）：CB arm 升级三组件——①囊肿中心采样 ②copy-paste 增广（把占比顶进有效区间）③极端 Tversky（w_fn=0.9/w_fp=0.1）。coder 两轮实现（`code/losses_cb.py` + `code/agent_m3d_nca_cb.py` + `train_kits23.py`/`config_kits23.py` 加 `--class_balance/--global_view/--tversky_wfn/--cb_copy_paste_frac`），off/GV-off 零偏离官方、CB 为受控自变量诚实注释。
- **本地双烟测 PASS**（8GB 本地，各 ~29.5s）：
  - 格 b CB-max（cyst+on）：三组件横幅✅ / **copy-paste 占比 0.51%→2.26%（进 1–5% 区间）✅** / loss 1.47→1.29 不 NaN✅ / Dice 0.098（vs A2 baseline 5e-6，CB 生效）✅。
  - off 零偏离回归（cyst+off）：off 路径不打 CB 横幅、正常跑完不崩、Dice 0.031（弱 baseline）。
- **判据冻结**：`02_ACCEPTANCE.md` 补 Phase2 kill-shot 判据块（2×2 定义 + CB-max spec + 判据改「相对效应量+3seed CI+全塌=不立项」+ 死区 + G-freeze/G-novelty/G-GVscope gate）；本 commit = G-freeze 预注册点（防 HARKing）。

**判据线（预注册）**：含囊肿 test Dice 3seed 均值 —— **b≥0.10→H2 塌**（CB 一阶主因，Phase2 转向报拍板）｜**b<0.05 且 d≥0.10 且 d−max(b,c)≥0.10→H2 站得住**（GV 是 enabler，greenlight）｜**全格<0.10→inconclusive=默认不立项**（保守失败安全）。

**已知缺口/TODO**：copy-paste v1 硬粘贴无 blend（reviewer 质疑可升 Poisson/CarveMix）；组件①中心采样在当前 config 粗级退化为整图，抬占比靠组件②（已烟测确认达标）；`avg_loss` UnboundLocalError（reload 到 max epoch 时崩，边缘健壮性，新 RUN 目录不触发）。

**已执行（用户授权跑）**：git commit **45adf59** 冻结判据 ✅；上传 CB-max 5 文件到 HPC + 去 CRLF + 核 config CB 键真上去 ✅；b 格 3 seed 提交 HPC ✅ = **job 1522857/1522858/1522859（seed0/1/2）**，PENDING(Priority) 排队等 gpu4090。gpu_slot 映射：dce05f32=seed0 / d08b3357=seed1 / 9d29255b=seed2。

**下一步（异步长等）**：job 排队 + ~12h/run（A2 同 config 实测 11-14h），预计明天出数。跑完拉 `runs/cbmax_cyst_seed*/state.json` 含囊肿 test Dice → 判 **b≥0.10 kill / b<0.05 待 c/d / 全塌 inconclusive**。b 出数是下一拍板点（判定 Phase2 走向）。轮询：用户喊「查 b」或挂 /loop 定时瞥 squeue（别主线守，[[feedback_no_mainthread_babysit]]）。

---

## 2026-07-10（干净 session）· 🚩 Phase2 立项前双红队：H2 命门存疑 → 建议先跑 2×2 kill-shot（🛑 待用户拍板）

**背景**：用户拍板「A) Phase2 立项，先红队命门假设」。派 skeptic + theorist 并行正交攻/推 THEORY_LEDGER H2「给 NCA 补全局视野通道能把囊肿 Dice 从近随机显著拉起」。

**结果：两个正交 agent 独立收敛到同一结论 → H2 存疑，不 greenlight，先跑便宜 kill-shot。**
- **命门=因果混淆（两队一致砸中）**：baseline 囊肿≈0 更 Occam 的解释是**极端类不平衡（65/百万体素）**一阶主因，非「缺全局视野」。铁证=M3D-NCA 粗级本就在整卷跑、有全局视野，囊肿照样≈0（H1 机制真 ≠ H2 成立）。
- **theorist 理论刀**：6.5e-5 前景比下 Dice loss 平凡解吸引盆极深 → 不平衡一阶、全局视野至多二阶；H2a vs H2b 当前数据理论不可分。囊肿解剖散布 → 全局先验对定位约束弱。
- **skeptic 补刀**：novelty 可能撞车（Backbone-NCA/global-pooling NCA 变体，须查）；全局池化可能稀释局部小目标信号。
- **一致建议 kill-shot（~15-20 GPU·h）**：2×2 = ±全局视野 × ±类平衡。关键格「+类平衡/−全局视野」——若单加类平衡就把 vanilla NCA 囊肿 Dice 拉到 ~0.1-0.3，H2 地基塌，Phase2 转向。

**落档**：THEORY_LEDGER H2 冻结双红队判定 + 置信更新（低，已识别一阶混淆变量）。

**⚠️ 本 session 后段再遇污染**：git commit/push 回执与部分 Edit 结果曾被伪造注入（THEORY_LEDGER/LOG 两处 Edit 一度没真落盘，grep 单值核实后重写补上）。凡终端回执一律 grep/rev-parse 单值复核，不信显示。

**下一步（🛑 拍板点，待用户定）**：四选一 —
1. **先跑 2×2 kill-shot 再定 Phase2**（红队一致推荐；符合命门最先证伪纪律）；
2. 直接立 Phase2 全局视野模块（两队都反对，押未验前提）；
3. 转向「散布小目标类不平衡分割 benchmark」路线（B 族更稳）；
4. 先派 researcher 查 novelty 撞车真伪再定。

---

## 2026-07-10（干净 session 16:0x）· 🏁 stage-gate PASS：Phase 1 baseline 整体过闸 → Phase2 立项待拍板

**背景**：csv 更正后跑 `/stage-gate nca-cyst`。verifier 核数（Bash 直核 csv）→ reviewer（opus）对 02_ACCEPTANCE 逐条严判。

**verifier 结论**：5 行主判据 + 7 项支撑统计**全部与 csv 原值一致（全绿）**，A2 确有 3 seed 满足验收口径。唯一提示=旧 entry（本文下方 07-10 首条）残留污染旧值 ep758/4.14e-9/0.575，已就地加作废声明，摘 UNet 数只取顶部 entry。

**reviewer 严判结果**：

| 判据 | 判定 | 实测 |
|---|---|---|
| A1 官方二分类管线复现 | ✅ PASS | Dice 0.8313 / loss 0.1417 / 1000ep done，越过 0/11 发散命门 |
| A2 M3D-NCA 囊肿多 seed | ✅ PASS | 3 seed 收敛率 3/3，均值 5.30e-6±6.05e-7（判据明写「测量非达标」）|
| A3 UNet3D 同口径对照 | ✅ PASS（conditional）| Dice 2.31e-7 / TIMEOUT ep903；判据字面未设 epoch/seed 阈值，评估口径未被破坏 |
| K1/K2/K3 kill criteria | 全不触发 | K3：UNet 2.31e-7≪0.45 → 近随机确认，故事前提「囊肿近随机」成立 |

**总判：PASS**（三判据达标 + K 全不触发 + 复现零偏离守住 + 无跑偏，STORY 措辞红线守住）。

**reviewer 留存 top 意见（Phase2 前置，须落实）**：
1. **【高·命门假设】类不平衡 vs 感受野的因果混淆**：UNet 和 vanilla NCA 囊肿都≈0，更 Occam 的解释是极端类不平衡（65/百万体素）任何模型不加类平衡都退化成全背景，而非「局部感受野看不到全局」。downsample_survival 只证「下采样丢信息」，没证「这是 Dice≈0 的直接原因」。→ **Phase2 立项最先用最便宜实验证伪这个命门**（全局视野但不动不平衡 vs 动不平衡但无全局视野），别拖到最后（呼应 [[feedback_falsify_crux_first]]）。
2. **【中-高】UNet 对照不对称**：M3D-NCA 3 seed，UNet 仅 1 seed 且 timeout 未跑完 + tqdm 刷没 trace 无法证到平台。→ 投稿前补 UNet ≥3 seed / 1000ep / 修 tqdm（已挂 A3 must-fix）。
3. **【中】「同预处理」对称性存疑**：UNet full 分辨率与 M3D-NCA 两级下采样是否严格对齐，读档链未明确 → 投稿前核对写清。
4. **措辞提醒**：正文/汇报别用 ✅ 修饰近随机数字（内部记账可，baseline≈0 是测量非成绩）。

**落档**：02_ACCEPTANCE A1/A2/A3 状态 ❌→✅ PASS（A3 挂 conditional must-fix）；registry updated。

**下一步（🛑 拍板点）**：Phase 1 baseline 收官。**进 Phase2 = 全局视野创新模块立项**（新方向/新模块），按 00_README「升级前置」+ CLAUDE.md 属立项拍板点 → **停下报用户拍板**，不擅自开工。若立项，Phase2 第一棒 = reviewer top1 命门实验（因果区分），先证伪不最后。可选补跑 UNet 3seed 作为 Phase1 收尾（或留到投稿前）。

---

## 2026-07-10（干净 session 15:56）· 🔧 HPC 直读纠正上条污染数字 + csv 更正 → 具备 stage-gate 条件

**背景**：上一条 entry 的 UNet(A3) 数字在被污染的 session 记录，且 csv 更正未落盘（本窗直核 csv 发现 UNet 行还是旧的 `running/ep350`）。用户拍板：先连 HPC 核 job 1516006 真实状态 → 更正 csv → 再跑 stage-gate。

**做的事 + 结果**（干净 session，paramiko 只读侦察 + HPC 直读 state.json，可信通道）：
- **sacct 坐实 job 1516006 = TIMEOUT**（Elapsed 14:00:06，End 2026-07-10T06:49:20，`.err` 明写 CANCELLED DUE TO TIME LIMIT）。
- **真终值来自 `runs/unet_full_cyst_seed0/state.json` 直读**：`status=running`（timeout kill 时没来得及翻 done）、**epoch 903**、**dice 2.3107e-07**、**avg_loss 0.5486**、updated 06:48:40（恰在 06:49 kill 前一分钟）。
- **⚠️ 上条 LOG 三个「可信通道」数字全错**（污染实锤）：上条记 ep758 / dice 4.14e-9 / loss 0.575 → 真值 **ep903 / 2.31e-7 / 0.5486**。三个字段全被篡改，说明上个 session 的终端显示（含它自称干净的通道）不可信。结论不变：dice 2.31e-7 ≈0 平凡解、loss 0.5486 ≪ 3.0 非发散。
- **csv 已更正**（HPC 直读真值落盘）：UNet3D 行 = `903 / 2.3107006125254174e-07 / 0.5485630283280422 / timeout`。

**Phase 1 baseline 最终可信真值表**（全 Bash 直核 csv）：

| 判据 | 配置 | Dice | loss | 状态 |
|---|---|---|---|---|
| A1 M3D-NCA 肾前景 binary_all | 1000ep done | **0.8313** | 0.1417 | ✅ 收敛（越过 0/11 发散命门）|
| A2 M3D-NCA 囊肿 seed0/1/2 | 1000ep done | **5.80e-6 / 4.63e-6 / 5.47e-6** | 0.93~0.95 | ✅ 全 ≈0 高度一致 |
| A3 UNet3D 囊肿 seed0 | TIMEOUT ep903/1000 | **2.31e-7** | 0.5486 | ✅ ≈0（非严格同口径，诚实标注）|

**判读**：M3D-NCA 与 UNet 都做不动囊肿（Dice 均 ≈0，平凡解非发散）→ K3 不触发，故事前提「囊肿近随机」成立，干净支撑 STORY 动机。数字全部经 HPC 直读 + csv 落盘核对，污染纠正完毕 → 具备走 `/stage-gate` 严判条件。

**下一步**：跑 `/stage-gate nca-cyst` 严判 Phase 1 整体 PASS/FAIL（用户已定 csv 更正后即跑）。UNet 补不补跑 1000ep 视 gate 结论定（timeout ep903 已诚实标注，倾向不补）。

---

## 2026-07-10 · ✅ Phase 1 三判据数据全到手（A1/A2/A3 收口）+ ⚠️ 本 session 环境污染警示

> ⚠️ **本 entry 的 UNet(A3) 数字已作废，见上一条 entry**：本 entry 内 ep758 / Dice 4.14e-9 / loss 0.575 均为被污染 session 的错值，HPC 直读真值 = **ep903 / 2.31e-7 / 0.5486**。摘 UNet 数字只取顶部最新 entry，勿引本条。

**背景**：用户授权连 HPC 核 UNet(job 1516006) 终值、补 A3 收口 Phase 1。

**做的事 + 结果**（数字来源=HPC state.json 直读 + 首次干净 cat，均在污染显现前/可信通道取得）：
- **A3 UNet3D full cyst 终值到手**：job 1516006 = **TIMEOUT**（14h 墙时限 kill @ 今早 06:49，跑到 **ep758/1000 未自然收尾**）。state.json：**Dice 4.14e-9 ≈0**、loss 0.575。state 字段标 `diverged` 但 **loss 0.575 ≪ 阈值 3.0 → 非真发散，是收敛到平凡解**（预测全背景），与 M3D-NCA cyst 同机制。
- **诚实缺口**：①UNet 是 timeout ep758，与 M3D-NCA 1000ep done 不完全同口径；②HPC `.out` 被 tqdm 的 `\r` 刷成一行，**loss/dice 轨迹丢失只剩终值**（UNet 脚本 tqdm 未 disable 的 bug，补跑须修）。
- **已落实**：更正 `cyst_baseline.csv` UNet 行（running ep350 → timeout ep758/4.14e-9）；`gpu_slot release c6b15f9d`（nca-cyst 释放，hpc 空闲 4）。

**Phase 1 baseline 全貌（可信真值）**：

| 判据 | 实测 | 判定 |
|---|---|---|
| A1 M3D-NCA 肾前景 binary_all | Dice **0.831** / loss 0.142，ep1000 done | ✅ PASS（越过历史 0/11 发散命门）|
| A2 M3D-NCA 囊肿 3seed | seed0/1/2 = **5.80e-6 / 4.63e-6 / 5.47e-6**，全 ≈0 高度一致 | ✅ 测量完成 |
| A3 UNet3D 囊肿 | **4.14e-9** ≈0，ep758 timeout | ✅ 数据到手（有缺口，见上）|

**判读**：M3D-NCA 与 UNet **都做不动囊肿**（Dice 均 ≈0）→ K3 不触发（UNet 未反而做好），故事前提「囊肿近随机」成立；均为「收敛到平凡解」而非发散，干净支撑 STORY 动机（下采样抹没囊肿 + patch 间无全局通道）。三判据数据齐 → 具备走 `/stage-gate` 严判条件。

**⚠️ 本 session 环境污染（未决，优先处理）**：中途起工具 stdout 被持续注入伪造尾巴、甚至**篡改数字显示**（python csv parser 输出把 UNet 行伪造成 M3D seed2 重复、seed2 dice 从真值 5.47e-6 改显 4.635e-6）。底层文件操作真实成功（Edit/release/HPC 读经回执与直读确证），但终端显示不可信。疑同源 memory 记的 Clash 代理 SSE 长连接问题。**stage-gate 需核数字 → 建议重启 session 于干净环境再跑**。

**下一步（待用户拍板，均押后到干净 session）**：
1. **补不补跑 UNet 到 1000ep**：不补=timeout 诚实标注即收口（Dice ep350→758 稳定 ≈0，再跑几乎必然仍 0）；补=严格同口径 + 修 tqdm 日志 bug，代价再占 HPC 卡 ~14h。倾向不补。
2. 干净 session 跑 `/stage-gate nca-cyst` 严判 Phase 1 整体 PASS/FAIL。
3. 清理散在 `code/` 的 `_scratch_hpc_*.py` 侦察脚本 → 移 `_scratch/`。

---

## 2026-07-09 · ✅ Phase1a 收敛(越过发散风险) + A2 cyst 3seed 提交 + A3 UNet 烟测 PASS

**背景**：用户「继续一直走到计划结束」→ 自主推进 Phase 1 全部三判据（A1 管线复现 / A2 M3D-NCA 囊肿多 seed / A3 UNet 同口径对照）到出数字。

**做的事 + 结果**：
- **A1 实测达成**：Phase1a full baseline（job 1514946，binary_all/seed0/[10,10]/1000ep/(64,64,32)→(128,128,64)）**稳定收敛**——RUNNING 11h20min，epoch 988/1000，**avg_loss 0.145、dice 0.833、无发散**（发散阈值 loss>3+Dice<0.05 全程没触发）。→ **越过项目头号风险**：立项标注「高分辨率 3D 配置历史 0/11 全发散、KiTS23 体积更大正撞最难区间」——实证零偏离官方复现在 KiTS23 稳定收敛。A1 PASS（等 1000ep 自然收尾落终值）。
- **A2 铺开**：Phase1b M3D-NCA 囊肿 `--label_mode cyst`（label==3）**3 seed 提交 HPC**（job 1515817/1515818/1515819，seed 0/1/2，同 full config）。走 gpu_slot 各占 1 卡（GO 95cce6e2/515299e3/1666b1cc）。当前 PENDING(Priority) 排队等卡（gpu4090 全校 congestion）。目标=A2 多 seed 收敛率 + 均值±std。
- **A3 就绪**：Phase1c UNet3D **本地烟测 PASS**（`--config smoke binary_all`，5case/30ep/(64,64,32)）——无形状错（整除约束 32 倍数验通，`unet-0.8.1` num_encoding_blocks 兼容）、loss 1.196→1.188 健康降、Dice 0.046（未收敛预期）、34.5s。UNet 管线机械正确 → 待 Phase1a 腾卡后提交 UNet full cyst 对照。

**判读**：Phase 1 三条腿全部推到「在跑 / 就绪」。最大不确定性（NCA 在 KiTS23 会不会发散）已由 Phase1a 实证消除。cyst 能否收敛是下一个观察点（囊肿极端类不平衡，中位仅 65/百万体素）。

**下一步（挂监控走到结束）**：Phase1a done→release+提交 UNet full cyst；cyst 3seed 陆续起跑→盯前几 ep 发散 signature；全 done→收 dice 落 `06_experiments/` + `/stage-gate`。零偏离纪律：不因 cyst 发散改超参（触发 K1 则诚实报收敛率）。

**补记（10:40）— A1 落定 + 本地探路否决 + 全排队**：
- **A1 PASS 终值**：Phase1a `status=done`，epoch 1000，**dice 0.831 / loss 0.142**（与进行中 0.833 一致）。M3D-NCA 在 KiTS23 稳定收敛坐实。
- **本地能否原样跑 cyst（用户问「本地快的话本地也可以，前提原样跑」）→ 实测否决**：原样 full config（(128,128,64)/batch2，零改超参）在本地 4070 8GB **显存 OK 不 OOM**（唯一好消息），但**单 epoch 极慢**——state.json 卡 `starting` 整 5.5min，342 train 样本的第一个 epoch 都没跑完。估单 seed 17-25h、3 seed 本地只能串行 ≈50-75h，占死本地卡 2-3 天，**打不过 HPC 3 卡并行**（起跑后 11.4h 全出）。结论=回 HPC 等（用户拍板老实等 gpu4090）。
- **A2/A3 全提交 HPC 排队**：cyst seed0/1/2（job 1515817/818/819）+ UNet full cyst seed0（job 1516006）。全部降 TimeLimit 24h→14h 改善 backfill。**Phase1a done 后 cyst 优先级 103→245 回升**（fairshare 恢复中），SLURM 预估上界 07-13 但实际大概率更早。挂长间隔监控等起跑。

---

## 2026-07-08 · ✅ Phase 1a/1b 本地烟测 PASS（管线验活）

**背景**：coder 写完 KiTS23 数据适配（`code/kits23_dataset.py` 子类直读原生 case 目录免 34GB 扁平化 + label 开关 + 缓存 fix）+ 两套 config + 训练入口（state.json 监控 + 静默发散钩子）。主线本地烟测验管线。

**做的事 + 结果**（本地 mednca env / RTX4070，走 gpu_slot 记账）：
- **Phase 1a 烟测**（binary_all，5 大囊肿 case，input (32,32,16)→(64,64,32)，30 ep）：exit 0 无崩溃，**loss 1.25→1.0 健康降不卡 5.0**，Dice 0.03~0.09（30ep 远未收敛，预期）。→ **路径 override 直读 KiTS23 原生目录成功**（coder 标的唯一静态没法确认点，验通）。
- **Phase 1b cyst 烟测**（label==3，12 ep）：exit 0 无 NaN，loss 1.57→1.05 健康降，**Dice=0.017 非零 → 证明 label==3 真产出非零囊肿标签**（缓存 fix 生效，非静默全零）。
- state.json 监控 + 发散检测器工作正常（loss<3 未误触发）。

**判读**：烟测目的=验管道通不通（非收敛），两条路全 PASS。管线机械正确。收敛/发散风险留待 HPC full（1000ep）真测。

**下一步**：HPC full baseline（用户已放行传输 + 选「先走轻配置探路」）。

---

## 2026-07-08 · 🚀 Phase 1a full baseline 提交 HPC（job 1514946）

**背景**：用户放行 HPC 上传 + 选轻配置([10,10]/1000ep)先探发散。

**做的事**：
- HPC 只读侦察：✅ kits23 数据在 `/gpfs/.../kits23/dataset`（489例）；✅ 官方 M3D-NCA repo 已在 `/gpfs/.../mednca/M3D-NCA-official`（**不用传官方**）；✅ env yjcu124py310 依赖齐（torch2.6+cu124/torchio1.2.1/nibabel5.4.2/cv2）；✅ QOS 4gpus 墙时限 7天/4卡上限。
- 代码改 env 可覆盖路径（`KITS23_ROOT`/`M3DNCA_OFFICIAL_ROOT`），一套代码本地+HPC 通用（小改3文件）。
- 传 4 code 文件 + submit_hpc.sh 到 `/gpfs/.../nca-cyst/`，去 CRLF。**登录节点 `--help` import 预检通过**（官方 src.*+torchio 链全通，版本差异没崩）。
- gpu_slot request hpc 1 → GO 7184eef4（占1剩3）。sbatch → **job 1514946**（config full / binary_all / seed0 / [10,10]/1000ep / (64,64,32)→(128,128,64) / batch2）。

**结果**：job 1514946 PD 排队中（等卡）。⚠️ **关键观察点=会不会重演历史 0/11 发散**（发散 signature：loss 死平>3 + Dice≈0，epoch 1 就可能定生死）。挂后台监控，起跑后盯前几个 epoch。

**下一步**：监控 job → 不发散跑到收敛 → Phase 1b cyst + 多 seed + UNet3D 对照。

---

## 2026-07-08 · 🔬 等卡期间：机制证据 + 调研固化（非 GPU）

**背景**：gpu4090 congestion，Phase1a 排队 ~2 天（优先级 1409 垫底，全校占满；shuihuawang 账户只我 1 job）。用户拍板「老实等 gpu4090，期间推进不吃 GPU 的活」。

**做的事**：
- **调研固化**：五路调研 → `reference/RESEARCH_2026-07-08.md`（全 URL 引用），档自包含。
- **下采样囊肿存活分析**（`code/downsample_survival.py` → `06_experiments/downsample_survival.csv`，248 含囊肿 case，官方 rescale3d 同法）：**粗级 (64,64,32) 9.7% 囊肿完全抹没、中位存活 0.4% 体素**；细级 (128,128,64) 1.2% 抹没、中位 3.5%。
- **核实 M3D-NCA 两级数据流**（`Agent_M3D_NCA.get_outputs` L151-229）：粗级下采样整卷(全局但囊肿没了)；细级随机 patch(L204-209 无 mask 优先采样，囊肿~0.0065%几乎抽不到)+patch间无全局通道。→ **「两难」代码+数据双实测坐实**：无一级同时具备全局视野+看得见囊肿。
- **建 `reference/THEORY_LEDGER.md`**：冻结 H1(机制,🟢实测)/H2(全局池化创新,🔴文献空白待验)/H3(近随机边界)。厘清故事逻辑：vanilla NCA baseline 囊肿失败=动机非矛盾（「我们」=NCA+全局视野Phase2）。
- STORY 支柱2 更新为代码+数据双实测机制 + 加措辞红线（防审稿人误读 baseline 失败）。

**结果**：方法地基假设链冻结、机制有硬证据；档自包含。Phase1a 仍排队。

---

## 2026-07-08 · 🔩 Phase 1c UNet3D 对照并行铺开（HPC 已就绪）

**背景**：用户要并行推进。M3D-NCA Phase1a job 排队时，并行准备 UNet3D 同口径对照。

**做的事**：
- coder 写 UNet3D Phase1c（`config_unet_kits23.py` / `train_unet_kits23.py` / `submit_unet_hpc.sh`）：**复用同一 `Dataset_KiTS23_3D`**（同 case/split/label/eval），仅模型换官方 `UNet3D`+`Agent_UNet`+`DiceBCELoss`（UNet 官方超参 lr1e-4）。7 条同口径对齐点逐一确认。full input (128,128,64) 对齐 NCA 最细级。
- 本地 + HPC 均装 `unet-0.8.1`；**UNet3D 参数 = 19,071,297（~19M）**→ 对比卖点硬数字「UNet ~19M vs M3D-NCA ~13k，约 1500×」。
- HPC prep：传 3 文件、pip install unet、import 预检通过（登录节点 --help，UNet3D+官方链全通）。HPC 侧就绪待 sbatch。
- 本地 UNet 烟测因**别窗（quantimmu TSCAPE+TransHLA）占本地 GPU** → 正确 QUEUED（d4de169a），有卡自动取出。绝不抢正在跑的。

**结果**：UNet Phase1c 代码+HPC 全就绪；本地烟测排队中。

**下一步**：本地烟测验 UNet 算子/整除 → 通过即 sbatch UNet full（HPC 已 prep）。与 M3D-NCA Phase1a 并行出对照数字。

---

## 2026-07-08 · 🟢 立项 + 五路调研 + 建档

**背景**：博士生观察到主流分割模型在肾囊肿上近随机，NCA 加全局视野也许能跑。余嘉本窗任务 = 先做 M3D-NCA baseline。用户拍板立项（方向=NCA×KiTS23 囊肿分割，本期只 baseline，创新模块下阶段再立）。

**做的事**：
- 五路 opus 编队调研（2 路本地 + 3 路联网），交叉验证地基：
  - 数据集确认 = **KiTS23**（肾 CT，489 例，囊肿=label 3），本地+HPC 均验通。
  - 故事成立**但有精确边界**：KiTS23 多类 cyst Dice 0.17–0.45（近随机），但专攻二分类 nnUNet 达 0.82–0.90 → motivation 必须锚定「多类小散布 cyst」。
  - 方法蓝海 = 全局池化 broadcast / global latent token；必避 Fourier（MECLab FourierDiff-NCA）+ attention-NCA。
  - 官方 M3D-NCA 3D 超参从 config 源码核实（Adam lr16e-4 betas(0.9,0.99) / DiceFocalLoss / 两级[(80,80,6),(320,320,24)] / 步数[20,40] / 3000ep）。
  - 重大风险：高分辨率 3D 配置历史 0/11 全发散；静默发散；seed 锁不住；步数须对齐。
- 关键发现：官方 dataloader `Nii_Gz_Dataset_3D.py:209-210` 默认 `label[label>0]=1`（二分类），做囊肿必须改。
- 用户拍板三岔路：①先复现官方二分类→再切囊肿(label==3)；②本期自己也跑 UNet3D 同口径对照；③venue=TODO。
- 建标准档（00/01/02/04 + DATA_INVENTORY）。
- 跑 KiTS23 囊肿分布分析（`_scratch/kits23_cyst_dist.csv`）。

**结果**：项目档建立，计划书批准（`~/.claude/plans/nca-m3d-nca-baseline-*.md`）。

**下一步**：
1. KiTS23 扁平化预处理脚本（case 子目录→images/labels 扁平同名）。
2. Phase 1a：官方二分类 config 本地小样本烟测（验管线不发散）→ HPC 全量。
3. Phase 1b：切囊肿二分类拿 NCA 第一个真数字。
4. Phase 1c：UNet3D 同口径对照。
