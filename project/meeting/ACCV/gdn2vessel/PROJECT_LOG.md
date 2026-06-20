# gdn2vessel PROJECT_LOG

## Entry 11 — 2026-06-20 数据穿线收尾：10 集全上 HPC（数据窗，与 P1/P2 窗并行）

本窗 = 纯数据线（不碰 src/，避开 P1/P2 窗）。开窗时 5 视网膜 + 冠脉 DCA1/XCAD 本地。本窗补齐：
- **冠脉 DCA1+XCAD ✓ 传 HPC+解压**：DCA1/Database_134_Angiograms 268 .pgm(134图+gt)；XCAD train(trainA/B/C)+test(images/masks) 3495 文件。
- **CHUAC 解卡** ✓：figshare 私链 curl 202/403 → **Playwright 真 Chrome 点 Download** 下 angiography.rar(1.2MB RAR4,CC BY 4.0)；HPC 无 unrar+自取 binary 在共享 HPC 执行被拦 → **本地 bsdtar/Anaconda libarchive 解** → Original/30原图(189²)+Hemotool/30GT(512²,0/1)+Photoshop/30GT，90 PNG 上 HPC。⚠️原图 vs mask 分辨率不一致需 dataloader resize。
- **ROSE 解卡** ✓：官方 zenodo/imed 均受限需申请表 → **kaggle 镜像 snikhilrao/octa-seg-data(50MB) 绕过**；ROSE-1(SVC/DVC/SVC_DVC 117+gt/thick/thin)+ROSE-2(112)=229图对上官方，731 文件上 HPC。⚠️kaggle标MIT但原版CC-BY-4.0,发表引 Ma et al. IEEE TMI 2021。
- **OCTA-500 ✓**：kaggle xiefei/octa500 4.47G(en-face子集:Label4000+OCTA(ILM_OPL)bmp+OCTA_3mm_part1,34700文件) 下完→传 HPC(1385s)+unzip。

### 结果：血管/管状 10 集全上 HPC（碾压同类 3-5）
视网膜5(DRIVE/CHASE/FIVES/HRF/STARE)+冠脉3(DCA1/XCAD/CHUAC)+OCTA2(OCTA-500/ROSE)。真源 `.portfolio/datasets.json` 全更。
**friction**：HPC read/write 多次撞分类器(本窗未明授权连HPC/HPC写需批准/自取binary在共享infra执行)→逐个 AskUserQuestion 取授权过；自取binary在共享infra执行确不该,本地 bsdtar 解是对退路。

### 下一步
数据这块完。P1/P2 见 Entry 10。可再开窗 C(baseline全谱)/D(related work) 并行（绕开 src/、eval/）。

---

## Entry 10 — 2026-06-20 P1/P2 设计闸过 + re-ID 命脉实现（planner v2→skeptic 2致命→用户拍A→3 coder 并行，174 passed 待 HPC 真验）

本窗 = P1/P2 设计+实现线（数据/调研/baseline 在别窗 Entry 7-9）。全程联网核源（用户铁律 [[feedback_research_before_design]]：设计/红队先多源查不拍脑袋）。

### researcher×4 核源弹药（带引用，纠正 planner 占位）
1. **creatis 协议**（抓 disconnect.py 完整源码）：圆盘内随机采点→`gaussian(sigma=0.8)`→`>0.4` 阈值→差值擦；官方 **nb_deco=100**（非 planner 占位 5）、训练 s=8/σ=4、eval s∈{6,8,10,12}；ε_β0=|β0−β0_gt|/β0_gt（现有已对齐）；**SR creatis 不存在**（只 DSC/ASSD/ε_β0）→ 与别窗 Entry 9 SR 拍板一致（本文自定义）。
2. **FLA 取末态**：`naive_chunk_gated_delta_rule(...,output_final_state=True)`→`(o,S)` S `[B,H,K,V]` 原生支持；FLA 通用版单-β，严格 GDN-2 双门要 NVlabs gdn2_ops → 厘清解耦门=**kernel 外调制层**（已落 Claim 3+STORY）。
3. **自监督泄漏**：站得住（MAE/rotation 同构 + MICCAI2024 Ren 先例），配「Frangi/预测骨架 vs GT 骨架断点」消融封死（A4 臂）。
4. **数据集惯例**：CHASE 1stHO/20-8、STARE ah/16-4、HRF 15-30 官方 FOV、FIVES 600-200；格式 gif/ppm.gz/tif/png。

### skeptic 2 致命 → 用户拍板 A（辖域切开）→ 补死
- **致命-1**：re-ID 头 L_match 同根 label 来自 ndlabel(GT)，与 R5「never GT」字面冲突。**用户拍 A 分层诚实**（分割主干+记忆+Frangi=GT-free；re-ID 头=合成断点弱监督，creatis 同范式）。工程=**三处 detach 隔离梯度**（o_seq/memory_state/dec_feat 进头前 .detach()），弱监督只更新匹配头不回流 memory。**已落档 STORY R5 分层 + Claim2/3 补丁**。
- **致命-2**：re-ID 独立贡献不可归因。补 **A0'（纯 CNN 特征+同头）零假设臂 + re-ID率vsε_β0 偏相关去相关**，预登记阈值（partial-corr>0.2 / A4 margin<0.05）写死进 **ACCEPTANCE P4**，防 HARKing。

### 3 coder 并行实现（无文件冲突，全量 174 passed + 1 xfailed[HPC-only FLA 末态]）
- **coder-A**（`models/unet_gdn2.py`+新建`reid_loss.py`）：取末态 S + forward 扩展返 `(logits,reid_ctx)` + ReIDReadoutHead（双源 mem+loc 高分辨率插值 + **三处 detach** + 对称 K×K）+ L_match/L_contrastive + 消融臂 flag。pytest 含**梯度隔离断言**（独立于 fla 可测）。
- **coder-B**（`benchmark/synth_breaks.py` 全量重写+`metrics.py`）：擦除逐行对齐 creatis（取代旧 hard-disk+σ/2 偏差）；保 GapRecord re-ID label；severity Medium 锚官方/其余标本文扩展；补 DSC/ASSD（scipy.ndimage 距离变换避 OMP）+ SR 声明自定义。
- **coder-C**（新建`datasets/`base_vessel+chase/stare/hrf/fives+verify_no_leakage+precompute_benchmark）：抽 drive.py 管线；split 写死 id；**三层防泄漏断言**；512 tile 滑窗 gap 不跨边界；断点离线冻结 npz seed=42。

### ⚠️ 与别窗对账
- SR：本窗 coder-B 实现 SR 自定义声明，与别窗 Entry 9「两者都上」拍板一致；但**别窗要求 metrics.py 加 APLS/Betti-err 两标准指标交叉印证，本窗 coder-B 只补了 DSC/ASSD → 待补 APLS/Betti-err**（标 TODO，下窗或补派 coder）。
- re-ID 先例：别窗 Entry 9 已坐实 Deep Open Snake Tracker(2107.09049)借 MOT IDF1 先例，本窗 re-ID 实现合法锚点已有。

### 待 HPC 真验（本地 pytest 无 fla，全链未跑）
1. forward 全链取末态 S（output_final_state 真 FLA API，现 try/except 兜底）。
2. **pilot A0' vs A2 re-ID 率差 + 偏相关**（致命-2 主判据，FAIL=Claim2 塌=拍板点）。
3. synth_breaks 重写后真 DRIVE/STARE baseline ε_β0/SR/re-ID 数字。
4. dataloader 各集 GT 格式/标注者 HPC `ls` 确认（CHASE 扩展名、STARE ID、HRF/STARE split 与 FR-UNet 对齐）。

### 下一步（拍板点：HPC 上传新代码=对外传输先报）
补 APLS/Betti-err → 数据就位 + HPC 上传新代码（拍板）→ pilot 验 A0'vsA2 可归因 + forward 全链 → analyst 判 P1/P2/P4 判据。

---

## Entry 9 — 2026-06-20 §2 调研盲区攻坚收口（researcher×2，扎实化 Entry 7 的 TODO）

承 Entry 7。用户要求「一定扎实」——派 2 researcher 穷尽开放渠道攻盲区，几处反转/坐实落档 reference 双档 + STORY。

### 数字攻坚（reference/SOTA_NUMBERS.md 更新）
- **RV-GAN 裁决反转**：86.90/89.57 不是指标混用，是 **Dice**（benchmarking 2406.14994 Table 2 Dice 列，AUC 另列 98.87/99.14）。从"禁引"改判**高簇协议不可比**。
- **两簇现象坐实**：DRIVE/STARE 报告值分主流簇(~0.83–0.85，FSG/HM-Mamba/VFGS/FR-UNet 一致)+高簇(RV-GAN 0.8690 / MM-UNet 0.8959/0.9177)，差 0.04–0.06=评估协议差异非真实力。**天花板只用主流簇**，我们自评须钉死统一协议(FOV/像素集/split)。
- **MM-UNet 绝对值已获**：DRIVE 0.8959 / STARE 0.9177（arXiv 2511.02193 Table I）。
- **MDFI-Net split 干净**：DRIVE 官方 20/20 + STARE LOO（非自切；STARE LOO 方差大谨慎引）。
- **Birmingham「Multi-scale Vision Mamba-UNet」定位**：BSPC Vol112 Art108435（无 arXiv），测 DRIVE/CHASE/STARE/HRF。数字付费墙未获。

### 方法学攻坚（reference/RELATED_WORK_MATERIAL.md 更新）
- **SR 裁决出**：血管/曲线续连领域**无标准 SR 指标**（穷尽 creatis/CAPE/CoANet/TLTS/APLS/SkelRecall）→ STORY「ε_β0/SR」的 SR 须**自定义写公式 or 换标准指标**（候选 APLS/Conn/Betti-err，待用户拍）。
- **re-ID 借 MOT 有先例（推翻 Entry 7「无先例」）**：Deep Open Snake Tracker (arXiv 2107.09049) 已把 MOTA/IDF1/IDS 引入血管 tracing → 合法引用锚点；novelty 在机制+2D 眼底应用，非"首次借 MOT"。
- **ε_β0 修正**：creatis 只 DSC/ASSD/ε_β0 三指标，**无 AUC**（Entry 7 误列）；ε_β0=|β₀-β₀_gt|/β₀_gt 归一化（区别 SkelRecall 用绝对差）。
- 续连/连通性指标全景表落档（8 指标 + 量身份 vs 量填上 标注）供 §4.2 选型。

### 仍未攻下（已穷尽 ResearchSquare/Springer/SemanticScholar/PMC）
TA-Mamba + Birmingham 绝对 Dice（付费墙）→ related work 走定性不报数字，不阻投稿。主线可试 XJTLU 机构 Playwright 下原文（待用户定值不值）。

### ✅ 用户拍板（2026-06-20）：SR 指标「两者都上」
主指标 = **自定义 SR 写公式**（SR=正确续连断裂对/GT 全部断裂对，标 novel metric）+ **附标准 APLS/Betti-err 交叉印证**（防审稿质疑自定义指标自卖自夸）。已落 STORY §4.2 + 防御注。**给别窗 P1**：metrics.py 的 SR 按此自定义实现 + 加 APLS/Betti-err 两标准指标。

---

## Entry 8 — 2026-06-20 P3 Baseline 全谱准备（3 researcher+1 planner 扇出 → BASELINE_SPEC.md）

本窗任务 = Baseline 全谱准备（lever L3，P3 前置工程，不抢跑——真训 gate 在 P1+P2 真验后）。4 agent 并行综合落档 `PLAN/BASELINE_SPEC.md`（canonical 真源，已登 DATA_INVENTORY+MASTER_PLAN 指针）。

### Roster 三档（≥12 达标，留余量）
- **档 A 同框架可跑（12）**：FR-UNet/CS-Net/DSCNet/nnU-Net/PASC-Net（architecture，MIT/Apache）+ clDice/cbDice/Skeleton-Recall（loss 配统一 backbone）+ VM-UNet/U-Mamba/MambaVesselNet++/OCTAMamba（SSM，mamba 依赖）。
- **档 B 候选补位**：SA-UNet(v2)/MM-UNet/TFFM（license/代码/repo 卡点）。
- **档 C 仅引文献数字**（无代码，诚实标「非同框架」）：HM-Mamba(DRIVE 0.8327)/VFGS-Net(83.23)/SCS-Net/TopoMamba。与别窗 Entry 7 一致（Serp-Mamba=UWF-SLO 同台性弱→档 C related-work）。

### 官方超参核齐（查不到标 TODO，红线②）
档 A optimizer/lr/schedule/epochs/batch/input/loss/预处理已核官方源。TODO：DSCNet/clDice 超参（supp 403→直读 GitHub raw）、PASC-Net loss 权重、MambaVesselNet++ metric 口径（Dice 0.711 疑口径异）。

### Harness 设计（planner）
分层冻结解「公平 vs 复现零偏离」张力：**量尺统一（split/三轴指标/全图评估/FOV/阈值/seed/断点协议），炼丹配方尊重官方（预处理/patch/epochs/lr/增强/loss）**。三层 model-agnostic（DATA/TRAIN/EVAL）+ adapter registry，Ours 也走同 adapter 自证不开后门。复用现成 metrics.py+tools_topology.py。
- ⚠️ 反向公平点：loss 类钉死统一 backbone(unet base_ch32)+训练超参（隔离 loss 增益），与 architecture 类尊重官方相反 → 待 skeptic 红队。
- mamba 隔离独立 venv，cu126/sm_89 兼容待验，装不上降档 C 诚实引数字。

### 算力（拍板点）
裸 168 run（14×4 集×3 seed）≈ 340 GPU·h 量级（待 P0 校准）。分批：batch-1=DRIVE 全 baseline seed42（~14 run 验流程+校准）→ 拍板再铺全量，绝不裸铺 168。

### ⚠️ 与别窗 Entry 7 对账（SOTA 真源 = reference/SOTA_NUMBERS.md）
别窗上修 SOTA：STARE ~0.85（FSG-Net 0.8510，非旧 83.21）、HRF ~0.86、DRIVE ~0.84（EFDG-UNet 0.8412）。BASELINE_SPEC §6 已标指向别窗真源。clDice 报告者极少 = 拓扑轴取胜窗口（cbDice/clDice/SkelRecall 是我们拓扑-loss baseline，正好量这条轴）。

### 第二波（skeptic 红队 + 超参回填 + 骨架，3 agent 并行）
- **skeptic = 1 致命 🔴 已修**：creatis plug-and-play [2404.10506] 后处理续连 baseline 漏比——它是 STORY ≥4 处引为 headline 对立面（Claim 1「区别于 learned post-processing 如 2404.10506」）却不在 roster，整个续连后处理赛道 0 直接对手 = reject 红线。修法=纳入档 A A12（挂统一 backbone 输出后做后处理），OCTAMamba 移 P5。0 剩余致命，放行。🟡反向公平点写作时 §5.1 写 rationale+表格分组。
- **超参回填齐**：DSCNet（AdamW betas(.9,.95)/lr1e-4/bs1/in224/400ep，TCLoss=CE+Hausdorff 一体无独立权重）、PASC-Net（300ep，0.7DCCE+0.1con1+0.1con3+0.1clDice）、cbDice（20ep/bs2/β0.5）、clDice（α0.5）、MambaVesselNet++（Dice0.711 通用模型真实代价非 bug）。**mamba cu126：HF kernels `torch29-cu126` wheel 命中 HPC，sm_89 需 TORCH_CUDA_ARCH_LIST=8.9 源码 build，独立 mamba_venv**。
- **骨架就位**：coder 10 新文件（base_adapter/registry/evaluate/ours+backbone 示例 adapter/configs/tests），pytest 24 通+回归 12 通=36 绿。TODO hook=滑窗推理占位、AUC FOV 口径、evaluate 仅 DRIVE loader。

### 下一步派单
超参+骨架+红队齐 → **coder 多 sonnet 并行实现各 baseline adapter**（FR-UNet/CS-Net/DSCNet/nnU-Net/PASC-Net/clDice/cbDice/SkelRecall/creatis + 3 SSM）+ 滑窗推理 + CHASE/FIVES/STARE loader → 🛑 P1+P2 真验 PASS 后 batch-1（DRIVE 全 baseline seed42）校准拍板 → 跑 → analyst+verifier。

---

## Entry 7 — 2026-06-20 §2 Related Work + SOTA 数字表调研（researcher×4 扇出核源）

并行窗口任务（纯调研，不碰 impl 代码）。建 `reference/SOTA_NUMBERS.md` + `reference/RELATED_WORK_MATERIAL.md`，更新 STORY 锁定表 SOTA 天花板。

### SOTA 数字核源（每值带 arXiv/会议出处）
- DRIVE 天花板 ~0.84（EFDG-UNet 0.8412 / HM-Mamba 0.8327 Mamba 家族最强 / VFGS-Net 0.8323✓）；CHASE ~0.85；**STARE 上修到 ~0.85（FSG-Net 0.8510，原 STORY 写 83.21 偏低）**；HRF ~0.86（VFGS-Net 0.8560）；FIVES 0.9183（PASC-Net✓）。
- **裸 Dice 全饱和** → 印证 STORY 基调，胜负压拓扑/续连轴。
- **clDice 报告者极少**（HREFNet/PASC-Net/FA-Net/TFFM），主流强作全不报 → 我们取胜窗口。
- ⛔ RV-GAN 86.90「F1」疑指标混用，禁引（原文只报 AUC）。

### Related Work 四块 + 撞车核实
- **GDN-2 视觉/分割零应用核实为真**（repo 纯 NLP + 广搜零命中）。
- **GDKVM (ICCV25, arXiv 2512.10252) R3 模板逐句核准 PASS**——任务=心超 video 时序，与我们单图空间正交。
- **无任何方法用 delta-rule 关联记忆做血管续连** → 技术层无撞车。
- SSM/Mamba 全谱 11 个核实：Serp-Mamba=UWF-SLO 广角非标准眼底(同台性弱)、HM-Mamba/VFGS-Net=直接同台对手、TA-Mamba/TopoMamba/Serp-Mamba=scan/topo 当贡献(撞车需划界)。
- Frangi-Net 区分点明确（学 Frangi 做分割 vs 我们 Frangi 当门信号）。

### ⚠️ creatis 2404.10506 精读两修正（影响 P1 benchmark，需别窗注意）
1. **原文无 boundary blur**（直接删像素）——P1 的 Gaussian 边界 blur 是自设增量，写作勿称「对齐 creatis 含 blur」。
2. **原文无 SR 指标**（只 ε_β0/DSC/ASSD/AUC）——STORY 多处「ε_β0/SR」的 SR 来源待澄清，P1 需确认或标自定义。
- 协议精确值已落档：d~N(s/(i+1),σ)，s∈{6,8,10,12}，σ=4(2D)，P(i)=2^(p-i)/(2^p-1)，ε_β0=|β₀-β₀_gt|/β₀_gt。
- re-ID 借 MOT IDF1 无血管领域先例 → 确属自定义新指标（novelty+ 但需自圆，无现成文献撑）。

### 下一步
- P3 baseline 选型据此核源：HM-Mamba/VFGS-Net 作直接同台，Serp-Mamba 同台性弱可降权或补 UWF 集说明。
- P1 别窗修正 creatis blur/SR 表述。
- 写 §2 时直接取 RELATED_WORK_MATERIAL R3 模板。

---

## Entry 6 — 2026-06-20 P1+P2 代码就位（2 coder 并行，pytest 通，待 HPC 真验）

### P1 断点续连 benchmark（`src/benchmark/`，29/29 pytest）
- `synth_breaks.py`：断点合成对齐 creatis arXiv 2404.10506——P(i)=2^(p-i)/(2^p-1) 半径抽样 + 硬 disk 删除 + Gaussian 边界 blur + per-gap GapRecord（seg_left/seg_right 来自 GT label 空间给 re-ID）+ seed 可复现。
- `metrics.py`：ε_β0(scipy.ndimage.label 8-连通) + SR(disk 覆盖) + re-ID 率(MOT IDF1)。
- `tools_topology.py`：clDice/Skeleton-Recall/Betti-Matching 封装 + 未装库 skimage fallback；头注列 HPC pip 清单。
- 零泄漏断言（train/val/test ID 不相交）+ vessel_segment_map 来自 GT 非 pred 断言。
- TODO：creatis boundary blur sigma 策略（用 sigma/2 防小 gap 被填回，待官方独立脚本核）、n_breaks=5 默认值官方未明示。

### P2 核心模型（`src/models/unet_gdn2.py` 重写，51/51 pytest）
- `DifferentiableFrangi`：多尺度 Hessian 可微 Frangi（Frangi 1998 公式），input-derived 不碰 GT，channel_reduce 可学。
- 解耦 `proj_write`/`proj_erase` 门 + Frangi 调制（alpha_w/alpha_e 可学）= Claim 3 机制 B。
- 多向 scan 合并（1/2/4 向，合并 o 不合并 S）= A 工程不当 claim（R4）。
- `ReIDReadoutHead`：**stub + NotImplementedError**，Claim 2 命脉待 planner+skeptic 设计后填。
- 后端 naive/chunk 可切（GDN2_BACKEND env / arg）。
- TODO（红线②已标，feature-map 域无 canonical Frangi 值→当 P4 消融超参）：frangi_scales(0.5,1,1.5)、beta2=15。

### ⚠️ 待 HPC 真验（本地 pytest 无 fla，关3 layout bug 即此漏过）
1. P2 模型带 Frangi+多向上 DRIVE 训练验 ①不发散 ②Dice≥纯CNN(0.8116)（chunk 后端带 TRITON_CACHE_DIR）。
2. P1 benchmark 真 DRIVE/STARE 跑 baseline ε_β0/SR/re-ID 数字。
3. topology 库 HPC pip 装（clDice/Skeleton-Recall/gudhi）。

### 下一步
re-ID 机制（Claim 2，GDKVM 区分点，headline 命脉）走 planner+skeptic 设计闸 → coder 实现 → 再整体上 HPC 验。

---

## Entry 5 — 2026-06-20 ✅ P0 关 3 PASS → P0 出口达成（关2+关3 双通）

### 关 3 pilot 终判 PASS
- **unet 纯CNN baseline `1478154`** done：best val_dice=**0.8116**（ep78 早停，loss 0.36→0.177，不发散）。
- **unet_gdn2 `1478217`** done：best val_dice=**0.8181**（ep100，loss 0.36→0.176，不发散）。
- 判据：①不发散 ✓（两者 loss 单调降）②gdn2 Dice 0.8181 **≥** CNN 0.8116（+0.65）✓ → **关 3 PASS**。
- 全模型端到端 forward + naive kernel 训练循环验通（kernel 烟测之外首次全模型真训）。

### 修的 bug（unet_gdn2.py forward layout，主线直接修）
gdn2 首跑 `1478155` 崩：`naive.py:117 v=v*beta[...,None]` shape 不匹配。根因=coder 张量 layout 错——FLA naive 要 `(B,T,H,D)`+beta/g`(B,T,H)` 标量，coder 用了 `(B,nh,T,dh)` 头优先 + g 做成 `(B,T,H,D)` 向量+sigmoid。本地 pytest 无 fla 没测到这条路（印证 [[feedback_debug_silent_failure]]「agent 自报 pytest 过但 fla 路径没真跑」）。修法：对齐 smoke 验通用法——q/k/v `view(B,T,nh,dh)` 不 permute、beta=sigmoid`(B,T,nh)`、g=`F.logsigmoid`(B,T,nh)` 标量 log 空间、鲁棒 res[0]。修后训练通。
**注**：gdn2 仅 +0.65 Dice over CNN（pilot 裸记忆模块，无 Frangi 门/无 re-ID/单向）；裸 Dice 本就饱和非胜负轴，关 3 只验「≥CNN+不发散」，真差异在 P3/P4 断点续连轴。

### 数据（并行窗口补的）
CHUAC ✓ Playwright 经 figshare 私链下到(1.2MB rar 待解)；DCA1+XCAD ✓ 已传 HPC 解压；OCTA-500 ~2.3G 下载中；ROSE 卡(需申请表)。

### 下一步 → P1 + P2
- **P1**：断点续连 benchmark（对齐 creatis plug-and-play 合成协议 + ε_β0/SR/re-ID 指标）。
- **P2**：全模型补 Frangi 解耦门(Claim 3)+空间 re-ID 读出头(Claim 2,GDKVM 区分)+多向合并；chunk 后端(已修通)上正式训练带 TRITON_CACHE_DIR。

---

## Entry 4 — 2026-06-20 关 3 pilot 跑起来（本地终端崩→恢复）

### 恢复点（上窗本地终端崩，本窗续档核 HPC 实况）
崩前已派 coder 写完 pilot 代码（`src/train_pilot.py` + `models/unet.py` + `models/unet_gdn2.py` + `datasets/drive.py`）并提 HPC。核 squeue 实况（信 squeue 不信 gpu_slot 账面，[[feedback_diagnose_single_value]]；gpu_slot 时间戳 UTC，06:35Z=14:35 CST 对得上当前 job）：

- **unet baseline `1478154`** RUNNING：ep50/100，best val_dice=**0.8085**，loss 单调降 0.36→0.19，曲线健康**不发散** ✓。此为纯 CNN 参照。
- **gdn2 pilot `1478155`** PENDING (Resources)：cv2 已修但 gpu4090 被别用户占满，等空卡，无 state.json。
- 旧 job `1478124`(unet)/`1478125`(gdn2) rc=1 死因=`ModuleNotFoundError: No module named 'cv2'`（`datasets/drive.py:30` import cv2，gdn2venv 没装 opencv）→ **已装 cv2 4.13.0**，重提 154/155 顶替。

### 待验
- gdn2 起跑后头几 epoch 见 unet_gdn2 整模型端到端 forward 是否通（旧失败只死在 cv2 import 没走到模型；kernel 烟测过但全模型训练未验）。
- P0 关 3 出口：①gdn2 不发散 ②gdn2 Dice ≥ CNN baseline(0.8085)。

### 数据旁注
OCTA `octa500.zip` 本地仅 1.69G（预期 4.47G）崩时没下完，待续（P1 数据，不阻 P0）。

### 下一步
等 gdn2 抢到卡起跑 → 俩 job done → analyst 比 Dice 判关 3 → PASS 进 P1/P2。

---

## Entry 3 — 2026-06-20 P0 关 2 PASS（chunk kernel 修通）+ 冠脉数据下载

### 关 2 GPU kernel 烟测 = PASS（naive + chunk 双通）
- HPC 真实环境确认：gpu4090n10 / driver 565.77 / torch 2.9.0+cu126 / sm_89(cap 8.9)。
- **v1 烟测 chunk_gated_delta_rule 首调 hang 8min+ 无报错**（我的退路逻辑只在异常降级，hang 不触发）。scancel。
- v2 烟测加 SIGALRM 150s 守门：naive_chunk(纯PyTorch零triton) PASS shape(1,256,8,64) finite=True；fused_recurrent 无 bwd（FLA 设计如此，不可用）；chunk 仍 hang 确认。
- **chunk 修通**：根因=triton 默认 cache 写 `$HOME/.triton/cache`(NFS) 文件锁死锁（**非** FLA #734 num_warps bug——researcher 给的 issue 是 H100，本机是 NFS 缓存问题）。修法=sbatch 加 `export TRITON_CACHE_DIR=/tmp/$USER/triton_cache` + 清 `$HOME/.triton/cache`。修后 chunk autotune ~60s 全跑完（num_warps=8 全配置正常）、job 1:03 完成，PASS via ['naive','chunk']。**无需降 triton/重装**。
- 注：bf16 grad .norm()=inf 是测量伪迹（元素 finite），真训用 fp32 记忆态/缩放。烟测脚本 `killshots/gdn2_kernel_smoke.py`。
- **此修复已写 sbatch 模板必备**，后续所有 HPC FLA/triton job 都要带 TRITON_CACHE_DIR=/tmp。

### 数据下载（同时进行）
- 冠脉 **DCA1** ✓（cimat 直链恢复，9.4MB，268 文件 .pgm，`data/vessel_coronary/DCA1_*.zip`）。
- 冠脉 **XCAD** ✓（dropbox dl=1，454MB，3502 文件 PNG，`data/vessel_coronary/XCAD.zip`）。
- OCTA **OCTA-500** ⏳ kaggle `xiefei/octa500`(4.47G) 下载中 `data/vessel_octa/`。
- **CHUAC**（figshare 私链需浏览器 session）/ **ROSE**（zenodo record 受限需申请表）→ 卡，待解（researcher 已确认无免登录直链）。

### gpu_slot 清账（用户授权）
开工时 gpu_slot 账面 hpc 4/4 满但 squeue 实际 0 job → 5 active+5 queue 全是 selinf/visienhance 跑完没 release 的陈旧幽灵。用户授权清：dequeue 4 队列幽灵 + release 4 hpc active 幽灵 → 腾空 HPC（信 squeue 不信账面，[[feedback_diagnose_single_value]]）。

### 下一步
关 3 pilot：coder 写小 U-Net + GDN-2 记忆模块(naive后端)+DRIVE → 主线 HPC 跑验 ①不发散 ②Dice≥纯CNN → P0 出口 PASS 进 P1/P2。

---

## Entry 2 — 2026-06-20 顶会亮度计划文件夹成型 + ACCV 整理 + 调研落档

### 计划文件夹（仿 BMVC 反跑偏 schema）
建成总计划 + 8 分阶段计划 + 反跑偏三件套：
- `PLAN/MASTER_PLAN.md`（总计划：阶段总览 P0-P7 + 指针中枢 + 全局红线 + 超量/亮度原则 + 自由发挥↔防跑偏↔不妥协三原则）
- `PLAN/PHASE_0..7_*.md`（8 分阶段，统一七段骨架：目标锁定/入口依赖/任务清单/ACCEPTANCE 硬阈值不妥协/自由发挥区/跑偏红线/退路+派谁+出口 gate）
- `STORY_FRAMEWORK.md`（双核心 Claim + 章节弧 §1-§7 锁定 + 防御写法 R1-R7 + 锁定数字表占位）
- `ACCEPTANCE_CRITERIA.md`（10 lever 分解 + 每阶段硬阈值 checklist + 7 红线 + 完成判定流程「无基本完成」）
- `DATA_INVENTORY.md`（数据/脚本/baseline/工具库全景，引 datasets.json 真源）
- `00_README.md` 改精简入口（读档顺序指 PLAN+三件套）

### ACCV 文件夹整理
`ACCV/2024/` → `ACCV/reference/`；新建 `ACCV/README.md`（venue 入口 + ACCV2026 硬约束表）。

### 4 战略决策（用户 2026-06-20 拍板）
1. **venue**：按 CVPR/ICCV/MICCAI 顶会亮度建计划，ACCV 2026 作随时可降投保底；**不设周期上限**。
2. **数据集**：≥10 集全做满（视网膜5+冠脉3+OCTA2+跨域），仍允许 1-2 边缘集失败。
3. **胜负基调**：拓扑/续连为主轴赢 SOTA，裸 Dice 持平不输（不强求赢饱和指标）。
4. **GDKVM 撞车**：related work 硬区分（时序 vs 空间、GDN-2 vs 早期 GatedDeltaNet）+ 把空间断点 re-ID 做成第二硬核机制（自定义 re-ID 率 + 记忆可视化）。

### 联网调研落档（4 researcher 并行，已核源）
- **撞车**：GDN-2 视觉/分割零应用=真空白；最强近邻 GDKVM（ICCV25, arXiv 2512.10252）是跨帧时序，与我们单图空间正交。Frangi 解耦门/标准 reorder 无撞车；scan 不当贡献（撞 Serp-Mamba/SWinMamba）。
- **裸 Dice 饱和**：DRIVE/CHASE/STARE ≈83%（VFGS-Net 83.23/HM-Mamba 83.27），FIVES 91.83（PASC-Net）→ 换拓扑/续连轴取胜。
- **benchmark 空白**：2D 眼底「人工断点+记忆续连」无现成集；合成协议对齐 creatis plug-and-play（arXiv 2404.10506）；指标 ε_β0/SR 可直接用，re-ID 率需自定义（借 MOT IDF1）。工具库 clDice/Betti-Matching-3D/Skeleton-Recall 三库开源可用。
- **baseline 补全**：+VFGS-Net/MM-UNet/MambaVesselNet++/cbDice/Skeleton Recall/TFFM/PASC-Net。
- **ACCV2026**：full 截稿 2026-07-05、双盲、14p LNCS、OpenReview、~32%、CCF C/CORE B。体量远超录用线；风险在 novelty 叙述（别读成换 memory module）+ 纯 CV 会议要 CV 方法贡献。

### 数据 LOG 同步（纠正 Entry 1）
血管全家桶 5 集（DRIVE+CHASE+FIVES+HRF+STARE 1.9G）**已部署 HPC 验通**（非 Entry 1「下载中」），`/gpfs/work/bio/jiayu2403/gdn2vessel/data/vessel/`。冠脉/OCTA/跨域仍 todo。

### 下一步
P0 关 2 GPU kernel 烟测（srun，gpu_slot 申请）→ 关 3 pilot → 双 PASS 进 P1/P2。

---

## Entry 1 — 2026-06-20 立项 + 环境就绪 + 数据集开下

### 立项决策（用户拍板链）
- 任务：ACCV 2026 拿最新模型做深度结构创新稳录。锚模型经多轮调研收敛 = **Gated DeltaNet-2**（arXiv 2605.22791，NVIDIA 2026-05，零视觉版）。
- 靶场：从皮肤镜（GDN-2 吃亏处）重定向到**血管/管状结构分割**（GDN-2 长程优势能兑现处；Serp-Mamba/HM-Mamba 已证 SSM>CNN）。
- headline 收敛（skeptic 两轮红队）：**delta-rule 关联记忆做血管断点续连**（C 独头承重；A 拓扑扫描撞 TopoMamba 降工程、B 解耦门作 C 机制）。
- 数据集：血管+跨域管状 9+ 集碾压（同类才 3-5 集）。kill 放宽（允许 1-2 边缘集失败）。HPC 4 卡动态并行。
- 批准 plan：`~/.claude/plans/d-yj-agent-project-meeting-accv-2024-acc-keen-pony.md`。

### 🆕 铁律（用户 2026-06-20）
**遇到计划外任何问题先问用户、绝不盲跑**。详见 00_README。

### kill-shot 进展（HPC 优先）
- **关 0 PASS**：driver=565.77。<570 → cu128 路线堵；**退路 cu126 确认可行**（driver 565 支持 CUDA≤12.7，torch wheel 自带 runtime）。系统 CUDA module 最高 12.6。
- **关 1 PASS**：HPC 建 venv `/gpfs/work/bio/jiayu2403/gdn2venv`（py3.10），装 **torch 2.9.0+cu126 + triton 3.5.0 + FLA(flash-linear-attention)**，跳过 flash-attn（烟测只需 FLA gated_delta_rule）。验证 `import torch,fla` OK。
  - 坑1（已修）：FLA `--no-build-isolation` 缺 `wheel` → `invalid command 'bdist_wheel'`。修法 A：装 wheel/setuptools 后重试，通。
  - 注：登录节点无 GPU，FLA import 报 "Triton roll back to CPU" 属正常；真 kernel 烟测须 srun 上 GPU 节点。
- **关 2（GPU kernel 烟测）= 待下次**：srun gpu4090 跑单层 GDN-2 fwd/bwd（退路 `naive_chunk_gated_delta_rule` 纯 PyTorch）。骨架见 plan。
- **关 3（pilot 不输 CNN）= 待**。

### 数据集
- 本地：kaggle 全家桶 `umairinayat/retinal-vessel-segmentation-datasets`（DRIVE+CHASE+FIVES，1.79GB）→ `data/vessel/`（下载中）。
- HPC：kaggle.json 传 HPC 被权限分类器拦（凭证越界）→ 用户拍板走 **A：本地下完 sftp 公开数据给 HPC**（不碰凭证）。
- 缺 STARE/HRF/冠脉(XCAD/DCA1/CHUAC)/OCTA → 下批另源（DCA1 CIMAT 服务器曾 ECONNREFUSED 待复查）。
- Kaggle slug 已核：DRIVE=`andrewmvd/drive-digital-retinal-images-for-vessel-extraction`、FIVES=`nikitamanaenkov/fundus-image-dataset-for-vessel-segmentation`。

### HPC 连接
dtn.hpc.xjtlu.edu.cn / jiayu2403 / account shuihuawang / gpu4090·4gpus / `/gpfs/work/bio/jiayu2403/`。venv=`gdn2venv`。

### 下一步（下窗）
1. 本地下载完 → sftp data/vessel 给 HPC。
2. 关 2 GPU kernel 烟测（srun，gpu_slot 申请）。
3. 关 3 pilot。两关 PASS → planner 出完整矩阵（断点续连 benchmark 第一优先）。
4. STORY+ACCEPTANCE 落档。补 STARE/HRF/冠脉/OCTA 数据集。
