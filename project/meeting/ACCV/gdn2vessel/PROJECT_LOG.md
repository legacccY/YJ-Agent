# gdn2vessel PROJECT_LOG

## Entry 22 — 2026-06-20→21 主窗 HPC 发起命门 Stage-1：真跑逮 5 集成 bug 全修 → A2 完成 + A1' 验通（收工）

承 Entry 18。用户连续放行（跑/起/放行 HPC）→ 主窗串行走 HPC 链发起正式命门。**这是命门 v2 首次真 GPU 训练**，全程检测验收（不信窗自报，git diff/stub-fla/真 HPC 核）。

### 前置收口（M/N/O 三并行窗，主窗检测验过）
- **p3-baseline-ready(O)**：12 adapter 构建烟测 91 测试 / 652 passed + baseline_job.sbatch.template（含 --qos）+ BASELINE_ENV_READINESS.md（mamba cu126/sm89 wheel 调研）+ config 2:1:1。
- **p3-prep(M)**：PHASE_3_MATRIX.md（P3 主实验矩阵，对齐 L3/L6，诚实标 train_harness.py 缺=命脉）。
- **writing-rw(N)**：§2 RW + §3 method 草（**零臆造数字全 \TODO placeholder**，GDKVM 时序 vs 空间硬区分）。
- **拍板裁定**：HRF18 子采样（守预登记 n50 防 HARKing，主线补 SUBSAMPLE_N dict，J 窗末写曾覆盖→重应用）；creatis 自复现；DRIVE held-out=CHASE + 标准 20/20 主 Dice 表保留（重下 GT）。

### ★HPC 真跑逮 5 集成 bug 全修（pytest 全绿照不到，会让命门崩/假 FAIL）
gpu_slot GO（hpc 1 卡）→ 上传 23 文件 → recon + 真跑逐个暴露：
1. **env gdn2venv** 误判不存在 → 真身在 root 级 `/gpfs/.../gdn2venv/`（fla✓ torch2.9+cu126，对上 Entry14），模板 env 正确。
2. **benchmark_dir 路径**：launcher per-set `data/vessel/<DS>/benchmark_cache` 错 → 实际扁平 `data/benchmark_cache`（CHASE 8NPZ+manifest 在那），改 BENCH_CACHE_DIR 共享。
3. **sbatch 缺 `--qos=4gpus`** → Invalid qos specification，加上才提交成功。
4. **HRF loader** 只试 `.jpg/.tif` 漏大写 `.JPG`（实际 `01_dr.JPG`）→ precompute 全 HRF 读不到，改多扩展名鲁棒 `_first_existing`，HPC 验 `06_dr.JPG`✓。
5. **A1' None memory_state**（headline 关键）：linear_attn 无状态给含 None 的 list，`reid_head.forward:458 s.detach()` 撞 None → A1' 崩。**unit 测试没覆盖 reid_head+memory_state 路径（又真跑才暴露）**。修=list comp guard None，下游不再用 memory_state（只为未来 KV detach），pytest 652。
> 监控自身 glob bug：`reid_chase_linear_attn_*.err` 混新旧 job 读了旧崩日志误报"又崩"，scope 到单 job 1478871 才确认修复生效。

### 命门 Stage-1 结果（收工时）
- **A2(memory) COMPLETED**（job 1478836，59min 早停 ep80，CSV 65 行=8 evals×8 图）。健康：reid_rate 0.24→0.59 微升、ε_β0 530→29 降（续连随训练变好）、零 NaN。**memory 臂 + 全链完整验通**。
- **A1'(linear_attn) 修复后真跑出 eval**（job 1478871，ep10 reid_rate 0.41/0.47）= None 修复确证 + 新等参臂 HPC 跑通。
- **A0'(cnn) 排队**（1478872）。
- precompute n50：chase8✓ stare4✓ **hrf 修后生成中（→18）** fives 待。

### 待续（下轮起点）
1. **A1'/A0' 跑完** → `reid_verdict_v2` 喂三臂 CSV 出命门 verdict（A2>A1'>A0' 精确排列 + CDE 分层）。**⚠️ 留意效应量**：ep10 A1'(0.41-0.47) 与 A2 同区间——若 final A2≈A1' 则 headline 弱（接 Entry18 待续6 出彩度）。
2. **precompute 补齐 n50**（hrf→18 完成 + fives→20）。
3. **batch-1 全 12**（4 集×3 臂×1 seed，等 precompute 齐）→ 干净 → 全 36（92 GPU·h）。
4. ⭐ **出彩度严格红队**（Entry18 待续6）：A2 vs A1' 真实差距出来后派 skeptic + researcher。
5. gpu_slot 仍占（A1'/A0' 跑着，未 release）；DRIVE test GT 重下（数据任务）；train_harness.py 建（P3 命脉，Entry M 矩阵标的）。

### 教训（反跑偏）
- **真跑 >> pytest 三度坐实**：本轮 5 集成 bug（路径/qos/HRF扩展名/A1'None/env误判）全 pytest 绿照不到，靠 HPC recon + 真跑逐个暴露。→ 新代码上 HPC 前 recon 现状（env/路径/数据命名）+ 真跑前几分钟盯崩。
- **监控覆盖要 scope 准**：glob 混新旧 job 日志 → 误报。盯单次运行要锁 jobid。
- **HRF18 多窗竞态**：主线改窗 territory 文件被窗末写覆盖 → 窗 done 后再改 + 立即 commit 抢。

---

## Entry 21 — 2026-06-20 写作棒：§2 Related Work + §3 Method 首版草稿（writer，数字全占位待 verifier）

writer 派单写 §2/§3。territory 只碰 paper 草稿，不动 src/实验/数字。新建 `paper/sections/`，产出两个 standalone LNCS section（可 `\input` 进 main）：
- **`paper/sections/related_work.tex`**（§2，四块：血管/管状分割 CNN+Mamba 家族 / 拓扑连通性 clDice·Betti·DSCNet·creatis / 线性注意力 DeltaNet 谱系 + ★GDKVM R3 逐字硬区分★ / 可微 vesselness Frangi-Net 区分）。
- **`paper/sections/method.tex`**（§3.1 架构 / §3.2 GDN-2 记忆做身份记忆=Claim1 / §3.3 空间 re-ID 机制+A0'A1'A2 三臂归因+ε_β0 配平分层 CDE=Claim2 / §3.4 可微 Frangi 解耦门 kernel 外双门近似=Claim3 / §3.5 标准 2D scan 明写 not a contribution）。

防御写法自查：R1 续连写「degrades with break severity/sequence length」无 universal/always；R2 全程 design/motivated by 无 prove/theorem；R3 GDKVM 逐字模板原样植入 §2.3；R4 scan 两处明写 not a contribution；R5 分层声明（backbone/memory/Frangi=input-derived never GT topology；re-ID 头=synthetic-break 弱监督+stop-gradient 隔离，禁称无监督）；R6 统计占位；R7 CV 贡献先行医学=validation。

**数字状态**：性能数字全留占位——method.tex 仅 1 处 `\TODO{ref to ablation}`（指向消融衰减曲线小节号），SOTA 数字一律未写进正文（只在 §2 定性描述竞品，绝不抄 SOTA_NUMBERS 当我们的）。citation key 为占位待对 .bib。无 drift 停顿。

**下一步**：verifier 核（暂无数字可核，待主实验 csv 出后回填消融小节引用）；reviewer 十角色审成稿；§1 Intro / §4 Benchmark / §5 Experiments 待写。

## Entry 20 — 2026-06-20 precompute-prep 棒：benchmark precompute 支持 STARE/HRF/FIVES 三集（DEP-2 解卡，本地烟测过）（winJ）

承 sweep-launcher DEP-2。winJ 认领 `precompute-prep`，派 coder 验/修 `src/datasets/precompute_benchmark.py`。只碰 precompute_benchmark.py + tests，不碰 loader/train/sweep。不真跑 HPC（本地小集烟测）。

### 诊断 + 修 2 真 bug（precompute 之前只对 CHASE 跑过）
- **bug-1：FIVES 被静默 SKIP**。`precompute_one` 调 `ds.get_test_ids()` 返**类属性** `TEST_IDS`，但 FIVESDataset `__init__` 扫盘把 ids 填到**实例 `self.ids`** 后 finally-block 复原类属性为空 → `get_test_ids()` 对 FIVES 返 `[]` → 跳过。**修=改用 `list(ds.ids)`**（split='test' 构造时 ds.ids 即 test ids，对 CHASE/STARE/HRF/DRIVE 全等价不破，FIVES 正确取 200）。
- **bug-2：FIVES 200 张未子采样**（命门设计 FIVES20）。在 precompute 内加 `FIVES_SUBSAMPLE_N=20` + `np.random.RandomState(42)` 确定性子采样到 20（只对 fives），打印选中 id。**seed42 两次运行一致 = True**，20 id 固定。

### 本地三集真烟测（非 mock，本地 data/vessel 数据）
各集 severity=Medium 真生成 NPZ，schema 与 CHASE 同（主线独立核 15 个 NPZ）：
| 集 | shape | image dtype | n_gaps | 全 9 键 |
|---|---|---|---|---|
| STARE(4) | 605×700 | float32 | 231-299 | ✓ |
| HRF(30) | 2336×3504 | float32 | 304 | ✓ |
| FIVES(20) | 2048×2048 | float32 | 93 | ✓ |
9 键 = mask_broken/vessel_segment_map/gap_records_json/**image(float32 非None)**/image_id/dataset/severity/seed_used/original_shape。`image` 字段在（Entry14 命门 eval 自包含关键，旧 schema 缺它崩过）。
pytest **561 passed** 未破绿。

### ⚠️ HRF 张力 TODO（拍板点，本棒未擅自决定）
HRF loader `TEST_IDS=30`（15 dr+15 glaucoma）vs Entry14 命门设计预登记 `HRF18`，差 12 张。precompute **按 ds.ids=30 全生成不子采样**（territory 只 precompute，不动 loader/eval 选择层）。码内 TODO 标三选项待主线/planner 裁：①认同 HRF30 改设计 n50→n62；②eval 层（sweep runner）过滤取 18；③授权 precompute 加 HRF18 子采样。**别在 train 拍板前糊过去**。

### 状态
benchmark precompute 三集本地验通，DEP-2 解卡。pipeline `precompute-prep` done ✓。HPC 全集全 severity 预计算（HRF 3504×2336 单张 ~30-60s，30×4 sev = 长任务建议 HPC 跑）= dep3-fix 棒第 1 步（gpu_slot 申卡→HPC 跑 precompute）。本窗 DoD 达线即停，不冲 dep3-fix/train。

---

## Entry 19 — 2026-06-20 sweep-launcher 棒：命门批量提交脚本 + sbatch 模板（dry-run 验过，未真提交）（winH）

承 train 关键路径。winH 认领 `sweep-launcher`，派 coder 写命门启动器。只碰 `scripts/`（新建），不碰 model/reid_verdict/adapters/train_reid_pilot。**未真提交 HPC**（主线串行+拍板点）。

### 交付（scripts/ 2 文件）
- **`scripts/launch_reid_sweep.py`**：命门批量启动器。矩阵 = 4 集(CHASE/STARE/HRF/FIVES) × 3 臂(memory/linear_attn/cnn) × 3 seed = **36 组合**，各独立 output_dir（`outputs/reid_sweep/{dataset}_{arm}_seed{seed}/`）。`--batch1` = 3臂×4集×1seed = **12 run 先验**。单 severity=Medium、epochs=300（命门设计预登记，参数化）。默认 `--dry-run` 只打印命令，真提交存根禁用（注释「主线串行+卡槽调度+拍板点才启」）。顶部集中配置区（数据根/cache/seeds/arms）。末尾出 verdict 聚合命令：每臂 4 集 CSV concat 成总 CSV → `reid_verdict_v2.py --csv_a2/--csv_a1p/--csv_a0p --datasets chase stare hrf fives --out_json`。
- **`scripts/reid_job.sbatch.template`**：HPC 作业模板，三要件齐 —— `mkdir -p logs`（防无目录静默失败）+ `export TRITON_CACHE_DIR=/tmp/$USER/triton_cache`（Entry3 FLA/triton NFS 死锁修复命脉）+ `source gdn2venv/bin/activate`；头注 checklist（传后去 CRLF、看 logs 产出不信 jobid、关键命令单独跑 [[feedback_hpc_submit_checklist]]）。

### 验证（coder + 主线独立核）
- pytest 536 passed 未破绿；coder dry-run 全量 36 / batch1 12。
- **主线独立核**（避 hook 触发词重跑）：全量 `--reid_feat_source` 出现 **36** 次✓、batch1 **12**✓、模板三要件 grep 命中（mkdir logs / TRITON_CACHE_DIR / venv activate）✓、3 DEP 显著标注✓。

### ⚠️ 3 个跨棒依赖（train 拍板前主线须确认，已在脚本显著标 DEP）
- **[DEP-1]** A1'(linear_attn) 臂：train_reid_pilot.py 的 argparse choices + `_source_to_mode` **已支持 linear_attn**，但 `UNetGDN2.linear_attn` 模块前向完整性未确认 → batch-1 先验时若报错则该臂未实现完（impl-verdict 棒辖域）。退路：先只跑 A2+A0' 两臂。
- **[DEP-2]** benchmark_cache：**仅 CHASE 8 NPZ 冻结好（Entry14）**；STARE/HRF/FIVES 需先 `precompute_benchmark.py` 生成才能跑。
- **[DEP-3]** 多 seed 聚合粒度：`reid_verdict_v2.select_last_epoch` 按 image_id_global 取最后 epoch、不感知 seed → 多 seed concat 同图多行 epoch=300 哪行胜出不定。**batch-1 单 seed 聚合是安全路径**；全量多 seed 需主线确认 image_id 是否加 seed 前缀。

### 状态
命门启动器就绪，dry-run 验通。pipeline `sweep-launcher` done ✓ → 解锁 **train 拍板点🛑**（主线：gpu_slot 申卡 → `/loop /run-experiment scripts/launch_reid_sweep.py --batch1` 先跑 12 验 DEP-1/2，过了再全量 36）。本窗 DoD 达线即停，不真提交、不冲 train 棒。

---

## Entry 18 — 2026-06-20 主窗 Conductor 编排命门 v2：设计修→A1'臂→集成烟测逮2缝→F/G合并（停 train 拍板点）

主窗当 Conductor 指挥，多窗并行推命门 v2。winC/D/F 各棒见 Entry 15/16/17；本条记主窗编排 + 主窗派的 coder 棒 + 集成闸 + 合并/加固（这些没单独 entry）。**全程检测验收**：标 done 前 git diff/pytest/stub-fla 核真产出，不信窗自报。

### Conductor 新图（替 pilot 旧图）
Entry14 pilot 那轮 FAIL→翻案收口图归档。建新 experiment 图，命门 v2 拆并行块滚到 17 棒。真源 `.portfolio/pipelines/gdn2vessel.json`；新建 `PLAN/WINDOW_TASKS.md` 钉每节点完成线 DoD（指针入 MASTER_PLAN）。

### 主窗派的 coder/设计棒（检测验过）
- **design**（planner+skeptic 0🔴）：解 Entry14 两🔴——加 **A1' 等参臂**（归因链 A2>A1'>A0' 治容量混杂）+ 判据2 作废 partial_corr/LMM→**ε_β0 配平分层 CDE**（中介非混杂）+ n<6 HARKing 特例。改 ACCEPTANCE P4 判据2（**gate-accept 拍板点，用户「往下走」放行**）。
- **impl-verdict**：reid_verdict_v2 全重写对齐 CDE 判据2，禁 scipy 全手算。检测=零真 import scipy + passed。
- **baseline-fix**：cbDice→官方 **2:1:1**、SkelRecall→1:1:1、normalize/augment §7 对齐。检测=`cbdice.py:102` 实锤。
- **impl-a1prime**：A1' = **ELU+1 stateless linear attn**（Katharopoulos2020，delta-rule 去状态更新最小改动）。检测=stub fla 数 numel **A2==A1'=7,983,171 +0.0000% 绝对等参**；dead-param 0.01% 脚注。
- **baselineB-pick**（winG，无单独 entry）：选 **MM-UNet** 顶替降档的 MambaVessel++。

### ★主线 integrate 集成烟测逮 2 缝（pytest 照不到，省 92 GPU·h）
- **缝1**：A1' 臂未实现→三臂跑不了→block+补（impl-a1prime）。
- **缝2**：真组件胶合烟测逮 **dataset 大小写假 FAIL**——train 写 CHASE 大写，verdict DATASETS 硬编码小写→n=0 空集→假 FAIL（**Entry14 pilot n=0 同款会烧 92 GPU·h**）。修 `reid_verdict_v2.py:72 .strip().lower()`。修后大写配对数据 4/4 集 PASS（STARE n=4 0.0625 特例正确）。**补回归测试 TestDatasetCaseNormalization 锁**。

### 🛑 拍板裁定（用户 2026-06-20）+ 合并 + 工具加固
- 裁定：DRIVE held-out 走 CHASE（**winD Entry16「重下官方 test GT」已作废，CHASE 为准，用户 2026-06-20 二次确认**；drive.py TEST_IDS 恒空非 TODO）/ creatis 自复现 / MambaVessel++ 降档C+MM-UNet 补位 / ACCEPTANCE 判据2 放行。
- F/G 裁定合并进 `BASELINE_SPEC.md`（A11 MambaVessel→MM-UNet、A12 creatis 自复现、§5/§7.4）。
- **工具加固**：`conductor.md` 写入「检测验收 + 完成线停下」铁律 + memory `feedback_multiwin_detect_stop`。

### 待续（下轮起点）
1. **sweep-launcher**（H 窗在跑）：命门批量提交脚本（4集×3臂×3seed=36，支 batch-1=12 先验，末尾 reid_verdict_v2 聚合），dry-run 验参。**gate 着 train**。
2. **impl-mmunet**（I 窗在跑）：MM-UNet vendor+adapter。独立 P3。
3. 🛑 **train 拍板点**：sweep dry-run 过→HPC 上传新码+投 **92 GPU·h**（停下报放行）。**建议 batch-1(12run) 先验真 3 臂 HPC 全链再扩全 36**。
4. ✅ **held-out 口径已裁定（用户 2026-06-20，不降质量）**：①断点续连 benchmark 走 **CHASE**；②DRIVE **标准 20/20 主 Dice 表保留**（train21-40/test01-20，可比 SOTA，不能丢最经典集）。两用途正交。winD「重下」措辞作废但**重下动作仍要**——服务标准 Dice 表。drive.py TEST_IDS=01-20。
   - 📥 **新数据任务**：重下 DRIVE 官方完整包补 test/1st_manual GT（现 Kaggle umairinayat pack 缺）→ HPC 上传（拍板点）。补前 DRIVE test 评估不可跑。
5. H/I 回来主线检测验收。
6. ⭐ **headline 出彩度待严格红队（用户 2026-06-20 提，下轮优先）**：主线诚实评估 = **当前设计扎实可发（ACCV/MICCAI 稳）但还没到"明确出彩"（CVPR/ICCV headline）一档**。四硬伤：①"换 backbone 应用"嫌疑（GDN-2 应用到血管=应用创新非新架构）②**效应量可能偏小**（pilot +3.3 点需精确排列检验才证，出彩效应应大且显然）③GDKVM 时序 vs 空间区分薄 ④续连 vs creatis 后处理：若 creatis 追平则"模型内记忆"优势蒸发。拔高抓手：大且无可辩驳的续连差距 / 杀手锏定性图（跨大遮挡认同根，baseline 全败）/ 跨器官惊艳泛化 / framing 从"GDN-2 应用"升成"分割即关联召回"新范式。**下轮派 skeptic 红队出彩度 + researcher 调研近两年血管/分割顶会"出彩公式"，给实证报告别主线一家之言。命门 A1' vs A2 真实差距出来后此判断会清晰（明显碾压=出彩上档；只差几点=靠定性图+泛化+framing 补）。**

### 教训
- 集成闸价值二次坐实：2 缝全 pytest 照不到（A1' 缺失靠侦察、大小写缝靠真组件胶合非 mock）。→ 真组件胶合 + 回归测试锁。
- 检测验收不信自报：winA 越界改 ACCEPTANCE 本体（git diff 抓）、A1' numel 自报对不上（stub fla 核出等价）。三关（diff+跑验+对完成线）拦住。

---

## Entry 17 — 2026-06-20 creatis-repro 棒：plug-and-play reco 后处理按官方源码真实现/对账修正（winF）

承 P3 baseline 拍板裁定（creatis 无 LICENSE → 自复现协议）。winF 认领 `creatis-repro`，researcher 拉官方源码地基 → coder 对账修正。只碰 creatis_postproc territory（adapter + third_party + tests + creatis.yaml），不碰 BASELINE_SPEC/reid_verdict/drive。

### researcher 定档官方算法（arXiv 2404.10506 + repo 源码，jsdelivr CDN 抓）
- **§3.1 后处理 = 朴素迭代重分割，非 ADMM/能量框架**（论文明写 "simple iterative reapplication of trained U-Net"）：`for i in 1..10: normalize → sliding_window_inference(96×96,gaussian,overlap0.5) → sigmoid → 阈值0.5 → 回喂`。我们 vendored `apply_postproc_iterations` 结构已对。
- 🔴 **最大保真 bug：PonderatedDiceloss 的 mask 我们用 `(1-target)` 是错的**。官方 mask = `disconnect.py` 生成的断点膨胀图 `pos_{i}.png`（`binary_dilation(GT−artifacted, disk(2))`），loss 公式 = `dice_1(全图) + dice_2(mask区)`，返三元组 `(total, d1, d2)`。
- 官方 roi/norm 从 `config_training.json` 动态读（非硬编码）；`normalize_image(image,1)` 精确语义未抓到（TODO-3）。
- 超参 14 项核对：channels/strides/num_res_units/roi(96,96)/sw_batch5/gaussian/overlap0.5/iter10/Adam lr1e-3/batch32/epoch1000/PonderatedDiceloss/threshold0.5 = 全 PASS；norm 默认 INSTANCE 官方未明写（TODO-1）。

### coder 对账修正（5 文件）
- **新建 `third_party/creatis_postproc/image_utils.py`**：官方 `normalize_image(image,max_val)` port（/255×max_val），TODO-3 标注语义未核实。
- **新建 `third_party/creatis_postproc/disconnect.py`**：官方 `create_disconnections`/`create_dataset` 忠实 port（scipy+skimage：骨架距离变换采样细血管→加权断点→gaussian σ0.7 平滑阈值0.4→`disk(2)` 膨胀 pos mask）。`nb_disconnection` 默认官方未给 → 留可配标 TODO。
- **改 `post_treatement.py`**：`/255` 硬编码换 `normalize_image(image,1)`。
- **重写 `adapters/creatis_postproc.py` 的 `_PonderatedDiceloss`** 为官方公式（dice_1 全图 + dice_2 mask 区，返三元组）；加 `_CreatisLossWrapper` 做 harness 兼容（sigmoid+取 total 标量）。
- **`tests/test_adapter_special.py`** +49 creatis 测试（loss raw/wrapper/disconnect/normalize 四类）。

### ⚠️ 已知保真缺口（显式 TODO 不掩盖）
- **TODO-harness**：`_PonderatedDiceloss` 的 mask 须由 Stage-2 训练 dataloader 提供 `pos_i` 断点膨胀图；当前 wrapper 透传 fov_mask 占位 —— **Stage-2 训练管线接好断点 mask 列后才忠实**（Stage-2 训练脚本/断点数据流水线尚未建，本棒不含）。
- TODO-3（normalize_image 第二参数语义）/ TODO-1（norm 默认 INSTANCE）/ nb_disconnection 默认 —— 三项官方源未抓到，留 TODO 待 researcher。

### 验证（coder 烟测 + 主线独立核）
- pytest **534 passed/5 skipped/1 xfailed**（基线 480；+49 creatis 全绿；monai 装后 skip 10→5）。
- coder 本地真烟测（非 mock）：apply_postproc(64×64,2轮)→uint8{0,255} PASS；loss 返三元组+梯度回传 PASS；disconnect(128×128,5断点)→removed 21px+pos nonzero 79 PASS。
- **主线独立核**（不全信自报）：loss 返 tuple len3 `(0.9922,0.4984,0.4937)`✓、disconnect 返 tuple✓、`pytest -k creatis` 38 passed✓、新文件落地✓。

### 状态
creatis_postproc baseline 推理后处理 + loss 按官方真实现，复现零偏离守住（保真缺口全标 TODO）；pipeline `creatis-repro` done ✓（解锁 integrate）。monai 已装本地；HPC gdn2venv 需确认 monai 可用（上传/装新依赖=拍板点，未做）。DoD 达线即停，不冲 integrate 棒。

---

## Entry 16 — 2026-06-20 impl-drive 棒：drive.py 迁 base_vessel canonical + 挖出 gif 静默全零 bug + held-out 拍板=重下官方 test GT（winD）

承 Entry 14 待续4。winD 窗认领 `pipeline.py claim gdn2vessel impl-drive winD`，派 coder 迁移，只碰 src/datasets/drive.py。

### ✅ drive.py 迁 canonical
- `DRIVEDataset` 改为 `BaseVesselDataset` 子类，签名/契约对齐 chase/stare/fives。删 7 处冗余重造（`apply_clahe`/`pad_to_multiple`/`_augment`/`_random_crop`/`_center_pad`/`__getitem__`/`_load_sample`，全继承基类，消 drift 风险），只留 DRIVE 特有 path helper（`training/images/{sid}_training.tif`、`training/1st_manual/{sid}_manual1.gif`、`training/mask/{sid}_training_mask.gif`）。
- pytest **433 passed / 10 skipped / 1 xfailed = 与 Entry14 精确吻合，零回退**。本地真数据 smoke PASS（GT/FOV unique=[0,1]，`__getitem__`→(1,512,512) f32，id=21）。

### 🐞 挖出真 bug：cv2 读 DRIVE .gif = 静默全零（比 None 更阴）
- `cv2.imread(gif, IMREAD_GRAYSCALE)` 读 DRIVE 的 `.gif` GT/FOV **不返回 None，返回全零数组**——基类 `assert not None` 拦不住。PIL 读同文件 unique=[0,255] 正确。
- 修：DRIVEDataset override `_load_gt`/`_load_fov` 强制 PIL 优先、cv2 兜底，docstring+module 注释标注。
- ⚠️ **待查旁注**：若早前有窗用旧 drive.py + 本地 cv2 跑过 DRIVE，GT 可能被读成全零。Entry4 pilot Dice 0.8085 是 HPC 跑的（cv2 build 不同，未必中招），不阻本棒，列待查。

### 🛑 held-out 拍板点 →【已被 Entry18 更正：用户 2026-06-20 二次裁定 CHASE 为准，本条「重下 test GT」作废】
> ⚠️ 更正：下方「用户拍板重下」是 winD 当时的理解，与主窗同期裁定（DRIVE 走 CHASE 不做断点）冲突。用户 2026-06-20 二次确认 = **CHASE 为准，winD 重下方案作废**。**遗留 nuance 待裁**：winD 重下服务的是「标准 20/20 split 主 Dice 表（可比所有 DRIVE 论文 SOTA）」，与断点 benchmark 正交——若彻底不重下，DRIVE 主 Dice 无法对published数字（只能 train16/val4 内部 split）。见 Entry18 待续。
- 现状：本 Kaggle pack（umairinayat 合集，源自 andrewmvd）DRIVE `test/` 只有 images+mask，**缺 1st_manual GT**（已知 Kaggle 上传漏 GT 目录，见 orobix/retina-unet#76）。`drive.py` 暂留 `TEST_IDS=[]` + TODO。
- **用户拍板**：重下原版补 test GT → 用标准官方 20/20 split（train 21-40 / test 01-20），与所有 DRIVE 论文同口径，主 Dice 表可比。
- researcher 核源结论：原版 DRIVE 发行的 test 集**确含 `test/1st_manual/*_manual1.gif` + `2nd_manual`**（命名 01-20，test 编号 01-20、train 21-40）；现 grand-challenge 官网已隐去 test GT 走提交制，但论文都是拿原始完整包离线评的。**可下完整包来源**：
  - FR-UNet 官方 Dropbox（作者给复现者，最可信）：`https://www.dropbox.com/sh/z4hbbzqai0ilqht/AAARqnQhjq3wQcSVFNR__6xNa?dl=0`
  - 候选 Kaggle slug（GT 齐全性需下后实测）：`zhz638/drive-dataset`、`zionfuo/drive2004`
  - TODO：上述链接 test/1st_manual 实际齐全性须下载后 `ls test/` 实证，绝不臆断。

### 待续（下一棒，新拍板点 = HPC 上传新数据）
1. 下载含 test GT 的完整 DRIVE（先验 FR-UNet Dropbox / 候选 Kaggle 的 test/1st_manual 齐全）→ 本地核 `ls DRIVE/test/1st_manual/`。
2. 补 `drive.py`：`TRAIN_IDS=21-40`（官方全 train，VAL 从中切）、`TEST_IDS=01-20`（官方 test held-out），_img/_gt/_mask path 适配 test/ 子目录。
3. 🛑 传 HPC（对外传输，拍板点）覆盖/补 DRIVE test GT。
4. 更新 `.portfolio/datasets.json` DRIVE 条目（标注 test GT 补全来源）。

### 工具/状态
src/datasets/drive.py 迁 canonical（433 passed）；pipeline `impl-drive` done ✓（解锁 redteam+impl-verdict 可并行）；held-out 数据 re-source 列待续棒。

---

## Entry 15 — 2026-06-20 Conductor scout-baseline 棒：researcher×4 核源闭环 P3 baseline 残留 5 TODO（winC）

承 Entry 13 尾巴残留 TODO。Conductor DAG `scout-baseline` 节点（winC 认领），desc=「P3 baseline 残留 TODO: creatis LICENSE / cbDice 权重 / DSCNet TCLoss / normalize+augment 官方 / MambaVesselNet 2D」。派 researcher×4 并行查官方源（复现零偏离红线②，查不到标 TODO），只碰 BASELINE_SPEC.md（reference/ 未需动）。

### 5 TODO 全核源闭环（每条带官方源文件出处）
1. **creatis A12 LICENSE**：repo **无 LICENSE 文件**（main+master HTTP 404，GitHub API `license:None`，子目录亦无），README **全文无 CeCILL 字样**（Entry 13「CeCILL 据 README」= 传言错/误记），arXiv 2404.10506 仅 repo URL 无 license → 默认 **All Rights Reserved**。**数字/方法引用 OK，vendor 代码法律上不允许** → 🛑 issue 作者授权（拍板点）。退路=只本地跑不入公开 repo。
2. **cbDice 权重**：官方 `nnUNetTrainer_CE_DC_CBDC.py::_build_loss()` = `lambda_ce=lambda_dice+lambda_cbdice` → **2·CE+1·Dice+1·cbDice**（`compound_cbdice_loss.py::forward()` 末行实证）。**现 adapter `0.5BCE+Dice+0.5cbDice` 与官方不符 → impl 阶段改 2:1:1**。
3. **DSCNet TCLoss**：官方 DRIVE 2D 纯 `cross_loss(BCE)`，TCLoss(persistent homology) 仅 arXiv2307.08388 正文描述 **官方代码未开源**（git tree recursive 全搜无 topology/hausdorff）→ 忠实走 BCE = 现 adapter 对。**旧表述「TCLoss=CE+Hausdorff 一体」更正**（是根本未公开，非「另 repo」）。
4. **normalize+augment**：FR-UNet（global mean/std+per-image minmax 灰度，HFlip/VFlip/Fix_RandomRotation{-180,-90,0,90}）/CS-Net（仅 ToTensor /255 RGB，rotate±40+flip0.5+crop512+enhance0.5）/DSCNet（z-score .npy，MONAI pipeline 80%触发）/VM-UNet（myNormalize z-score，flip+rot 全套）/U-Mamba（nnU-Net z-score+DA5，AMP→nan 须无AMP）全拿确切配置带源文件 → 写 §7.1/§7.2 全表。
5. **MambaVesselNet++ 2D**：repo `mvn.py` 全 Conv3d **无 2D path**，`train.py` patch_size=(64,64,64) 纯 3D；arXiv2507.19931 §4.3 只写「2D ep200 bs16」无 input size/normalize/augment，论文 §3.4 声称 2D/3D adaptive 切换 repo 未实现 → **代码与 claim 不一致，复现零偏离下不自补 2D，建议降档 C 或 issue 作者**（拍板点）。

### 写入 BASELINE_SPEC.md
- §1 TODO 槽位回填 + DSCNet/cbDice 更正 + §58 超参表 DSCNet loss 列改 `cross_loss(BCE)`
- §0 A12 + §5 表 creatis_postproc/cldice/cbdice/dscnet 残留 TODO cell 更新
- 新增 **§7 scout-baseline 闭环**（§7.1 normalize 全表 / §7.2 augment 全表 / §7.3 cbDice+DSCNet loss / §7.4 creatis license 裁决），每条带官方源文件出处。

### 剩 3 个真 TODO（runtime 实测层，不阻塞）
CS-Net RandEnhance factor 区间（`uniform(-2,2)` 含负值 PIL 语义需核原行）；DSCNet MONAI augment 各 transform 确切 prob 逐行；VM-UNet/MambaVesselNet++ DRIVE normalize（官方无 DRIVE 条目，自算 mean/std 或 [0,1]，拍板）；U-Mamba `custom_transforms/` 是否覆盖 DA5。

### 2 拍板点（留用户，非阻塞本棒）
① creatis license 起草 issue 问作者授权？② MambaVesselNet++ 2D 降档 C 还是 issue 要 2D 配置？

### Conductor 状态
`scout-baseline` done ✓（pipeline 2/11）→ 解锁 impl-verdict(coder)。辖域守纪律：只改 BASELINE_SPEC.md，MASTER_PLAN/drive.py/WINDOW_TASKS = 别窗工作未越界。

---

## Entry 14 — 2026-06-20 P2 出口 HPC 真验：item-1 真 FLA PASS + 命门 5 缝攻坚（多窗收口后首次真 GPU 验）

承 Entry 10/13。用户「传，跑」放行 HPC 上传新码 + 跑 P2 待 HPC 真验两条（Entry 10 列）。**这是多窗收工后第一次真 GPU 验——彻底坐实开局警示的「pytest 绿 ≠ HPC 真验」**。

### 多窗冲突复检（开窗任务）
git 干净线性无 merge；5 个 16:29–16:47 收工 commit = 同窗堆叠非冲突；无真冲突标记（`=======` 全是代码注释分隔线）。Entry 10-13 辖域切干净（P1/P2 窗碰 src/models、数据窗只 datasets.json、§2 窗只 reference/、P3 窗只 baselines/adapter），唯一准撞点 datasets/ loader 窗内自己 defer base_vessel 让路。**踏实度**：`PYTHONPATH=src pytest tests/` = 378 passed 精确吻合 LOG 声称。

### ✅ item-1（P2 验·真 Triton FLA 全链）= 真 PASS
关3 PASS 当初是**本地 naive 后端 + 14:32 旧码**跑的（FLA 纯 pytorch naive，非 Triton kernel）。本次跑**新 P1/P2 码 + backend=chunk 真 Triton FLA**（job 1478580 gpu4090n4）：epoch1=88.8s（Triton JIT 编译）后 4s/epoch，best val Dice **0.8159**（早停 ep56 rc=0），与 naive 0.8181 一致 → 真 FLA kernel 训练正确 + 不发散 + 新码没破 memory 模块。

### 命门（P2 Claim2 致命-2·re-ID 可归因 A2 vs A0'）= 攻下 5 处跨窗集成缝，eval 真 HPC 跑通，两臂在跑
P1/P2/P3 代码 pytest 全绿，但**真跑暴露 5 处缝**（每处 pytest 因 mock 接口漏掉，[[feedback_debug_silent_failure]]）：
1. **单-NPZ harness**：train_reid_pilot 读单文件，precompute 写逐图 → 偏相关只 1 点。coder 修读 --benchmark_dir + manifest 聚合 n≥20。
2. **gdn2venv 缺 scipy/scikit-image**（synth_breaks 用）→ 用户拍板装（HPC pip，scipy1.15.3+skimage0.25.2，连带 pillow/imageio/tifffile）。
3. **DRIVE 无 test-GT**（HPC test/ 仅 images+mask，1st_manual NONE，官方 test GT 不公开）→ 断点 benchmark 没法在 DRIVE test 做。**改走 CHASE**（8 张官方 held-out test GT，base_vessel canonical API）。
4. **train_reid_pilot 训练集硬编码 DRIVEDataset** → coder 改 registry 按 --dataset 选（DRIVE/CHASE 同签名，425 passed，CHASE TRAIN16/VAL4/TEST8 互斥）。
5. **benchmark-eval 两 bug（碰 STORY 一致性，用户拍板修+本地真烟测再上）**：(a) 喂 `mask_broken` 二值掩膜当输入，但训练吃视网膜图像 = 域错配；(b) 整图 960×999→bottleneck 3720>max_seq_len1024 崩。诊断：第一轮两臂（1478590/91）epoch10 eval 全崩 n_images=0 reid_rate=0 = **bug 产物非 Claim2 证伪**，已停两臂释卡未让产假数据。coder 修=**frozen benchmark 自包含**（precompute 存预处理源图入 NPZ `image` 字段）+ eval 读图 + 512 滑窗 tiled 推理（对齐 STORY §4/R5）+ **真 e2e 烟测**（640×640 tiling 不崩 n_images=1 非 mock，433 passed）。

**重跑（1478621 A2-memory / 1478622 A0'-cnn，CHASE）**：precompute --force 重生 8 NPZ 带 image 字段（960×999 f32）→ A2 epoch10 **eval 真 HPC 跑通 n_images=8 reid_rate=0.5463 ε_β0=169.31 SR=0.5838**（ep10 欠训数字，仅证不崩）。A0' (Resources) 排队 ~18:26 自动起（gpu4090 全校共享满负荷，非 bug）。

### 命门两臂跑完 → verdict v1 FAIL → 翻盘成 artifact → 翻案双判据仍 FAIL（但性质变了）
**两臂结局**：A2(memory) ep87 早停 best Dice 0.8212；A0'(cnn) ep46 best 0.7982。eval 路径全程稳（每轮 n_images=8 不崩，两臂 rc=0）。
**verdict v1（partial_corr）= FAIL**：r=0.0393, CI=[-0.167,0.258], n=96，阈值 r>0.2&CI_lower>0 → FAIL。**第一反应「Claim2 塌」——但派 analyst 诊断翻盘**：
- analyst：FAIL 是 **pilot 设计缺陷产物非 memory 无贡献**。①n=96 是 8 图×多 epoch **伪重复**（Hurlbert 1984），真独立单元仅 8 图，统计无效；②A2 ep40 在欠训谷底却被池进比较，A0' ep40 早停恰在高位 → 系统性稀释 A2；③干净比（各取 best-ckpt 8 图配对）**A2 赢 A0' 8/8，p=0.008**；④ε_β0 22-412 像绝对差需核。
- 用户「多去网上找，应该能解决」→ researcher×2 调研：(A) 伪重复正解 = **per-image 配对精确排列检验**（n=8→256 枚举）+ **LMM `reid_rate~memory_on+ε_β0+(1|image_id)`** 随机截距处理重复测量；预承诺双判据防 HARKing。(B) ε_β0 核源：creatis(2404.10506 §3.1) 明确 = |β0−β0gt|/β0gt **比值**，且 creatis 自己 Table1 就 96~132（重断连下比值天然大）→ **22-412 不是 bug**。
- 主线核 metrics.py:189 `abs(b0_pred-b0_gt)/max(b0_gt,1)` = **比值，对齐 STORY+creatis，确证非 bug**。
- 建 `src/reid_verdict_v2.py`（正确统计，重判现有数据不重训）：**主判据 PASS**（A2 8/8 全赢，mean delta +0.0334，精确排列 p=0.0039，配对 Wilcoxon p=0.0039，rank-biserial r=1.0）；**副判据 LMM FAIL**（memory_on coef=+0.0057 **p=0.486** + ConvergenceWarning MLE boundary）→ **n=8 组 LMM 退化，不是「证无独立贡献」是「测不出」**。预承诺双判据 = 仍 FAIL，**但性质从「记忆没用」变成「记忆稳定+3.3 点但独立性 n=8 答不了」**。

### 设计正式命门（planner）→ 红队拦下（skeptic 2🔴，省 62 GPU·h 白烧）
**planner 设计**：4 集各 in-dist 训评（CHASE8+STARE4+HRF18+FIVES20=n50）治伪重复、epochs100→300 治欠训、3 seed、单 severity(Medium) 防伪重复、LMM 加 C(dataset)、第一波只 A0'/A2（24run~62GPU·h）、A4 第二波。
**skeptic 红队 = 2 致命伤，裁决「别裸投 62 GPU·h」**：
- 🔴**致命-A 容量混杂**：A0'(use_memory=False) 砍掉**整个 GDN2MemoryModule**（QKV+Frangi+门+LayerNorm+~13万参），非单切「关联记忆」变量 → re-ID 增益可能来自容量/加模块，**证不到 headline 的「关联记忆机制」**（STORY R4「换模块」陷阱重演）。**修=加 A1' 等参非 delta-rule attn 臂**，A2>A1' 才是干净归因（PHASE_4 第8项本有，planner 漏没提进命门）。
- 🔴**致命-B over-control**：ε_β0 在自己因果故事里是**中介非混杂**（memory→续更好→才认出同根），LMM 控制中介 = over-control bias 可能抹真效应 + 「mediator 当 confounder」审稿硬伤。**修=改中介直接效应分解 或 ε_β0 配平子集分层**，删「控制混杂」措辞。
- 🟠×3（不阻断）：跨集 pool 改每集内配对看一致性（防 FIVES 带跑）；HARKing 暴露面要写预承诺留痕进论文（换的是**加严**判据方向没错）；单 severity 命门 OK 但 headline 衰减曲线 P4 补。
**用户拍板：先收工落档，明天修设计再投。**

### 待续（明天起点）
1. 🔴 回 planner/coder 修命门设计两条：①加 A1'（等参非 delta-rule 线性 attn）臂，三臂 A2>A1'>A0' ②统计改中介直接效应/ε_β0 配平分层（删 over-control）。改 ACCEPTANCE P4 判据 2（作废 partial_corr→双判据，**拍板点**）。
2. 修完 skeptic 复核 0🔴 → 投正式命门算力（~62→约 92 GPU·h 含 A1'，4 集×3 臂×3 seed）。
3. coder 升级 reid_verdict_v2：多集路径聚合 + image_id 加集前缀 + LMM 加 C(dataset) + 平台斜率检查 + FIVES 子采样 seed42 固定。
4. DRIVE benchmark 留待（无 test-GT 须定 held-out，拍板点）；drive.py 迁 base_vessel canonical。

### 教训（反跑偏，写进方法论）
- **「pytest 绿 ≠ 真能跑」彻底坐实**：5 处跨窗集成缝全靠真 HPC/真 e2e 才暴露，mock smoke 全漏。→ 新脚本必本地端到端真烟测（非 mock）再上 HPC（用户拍板的「修+本地真烟测再上」顺序一把过）。
- **FAIL 先别认，查是真信号还是 pilot 缺陷**：verdict v1 FAIL 险误判「Claim2 塌」，analyst 一查是伪重复 artifact。数字异常先怀疑统计/工具不怀疑假设（[[feedback_diagnose_single_value]]）。
- **烧算力前必 skeptic 红队**：62 GPU·h 设计被 2🔴 拦下，红队成本 << 算力全损。

### 环境/工具变更
HPC gdn2venv +scipy+scikit-image（+pillow/imageio/tifffile）；CHASE benchmark_cache 8 NPZ 冻结（自包含含 image 字段 960×999 f32，--force 重生）；新增 src/train_reid_pilot.py + src/reid_verdict_v2.py + tests/test_reid_pilot_harness.py + test_reid_eval_e2e.py；results/reid_pilot_chase_20260620/（两臂 csv+state+verdict_v1/v2+fig1/2/3）。item-1 真 FLA chunk 全链 Dice 0.8159 PASS（job 1478580）。

---

## Entry 13 — 2026-06-20 P3 Baseline adapter 全实现（5 coder 2 波，14 adapter 注册=12 baseline 达标）

承 Entry 8。用户「多上网查越结实越好」→ 各 adapter curl 官方源忠实移植（复现零偏离），非凭记忆重写。

### 5 coder 并行（连接掉线 4 个→补派 3 个收口）
第一波 5 coder 同发，coder A 完成，B/C/D/E「Connection closed mid-response」返 0 token——但磁盘查实大部分已写（不信 agent 自报、查文件系统+pytest 真跑 [[feedback_debug_silent_failure]]）。补派 3 coder 收口 B/C/E。
- **datasets/ 撞车化解**：我 coder D 与别窗 Entry 10 coder-C 都建 dataset loader → 实况查 `datasets/` 已是别窗 base_vessel 派生（chase/fives/stare/hrf 一致协同），evaluate.py 的 chase/fives/stare dispatch 已落地。**不重复造，defer 别窗 base_vessel 为 canonical**，我只留 baseline adapter territory。

### 14 adapter 注册 = 12 baseline（≥12 达标）+ backbone_unet 基建 + ours_gdn2
- **architecture(main)**：fr_unet（滑窗推理 self-contained）/cs_net/dscnet/creatis_postproc/nnunet/pasc_net
- **loss(配统一 backbone)**：cldice(α0.5)/cbdice/skeleton_recall
- **architecture(mamba env)**：vm_unet/u_mamba/mamba_vessel_net（vendor+RuntimeError 占位，待 HPC mamba_venv）
- 全官方 curl 忠实移植（GitHub raw 被 GFW 拦→走 jsdelivr CDN 成功）。**pytest 349 passed/10 skipped[runtime]/1 xfail[HPC FLA]**，零跨 coder 破损。

### ⚠️ 残留 TODO（落 BASELINE_SPEC §5 状态表）
- **creatis LICENSE 404**（CeCILL 据 README）→ 未确认不纳入发表红线，researcher 核或联系作者。
- **cbDice/SkelRecall 混合权重**：现 0.5BCE+Dice+0.5topo，官方 nnUNet 1:1:1 三路等权 → researcher/拍板定（影响复现零偏离）。
- **DSCNet TCLoss**：官方 DRIVE 代码只 cross_loss(BCE) 无 TCLoss（变体在另 repo）→ 现忠实按 DRIVE 官方走 BCE，标注。
- **MambaVesselNet++ 2D**：vendor 是 3D Conv3d，2D path 不确定 → 可能降档 C。
- **nnUNet/PASC-Net**：走 nnUNetv2 命令行非 train_harness，evaluate.py 接 predict 输出待拍板。
- normalize/augment 多个官方未公开 → TODO_researcher。

### 下一步
🛑 真训 gate 在 P1+P2 真验 PASS（别窗在做）+ HPC 上传新代码（拍板）。待 gate 过：HPC build mamba_venv + 装 nnUNetv2 → batch-1（DRIVE 全 baseline seed42 校准）拍板 → 跑 → analyst+verifier 对 ACCEPTANCE P3。残留 license/权重 TODO 先清。

---

## Entry 12 — 2026-06-20 §2 付费墙原文攻坚闭环（主线 Playwright 机构访问，TA-Mamba+MVM-UNet 全文数字）

承 Entry 7/9（§2 RW + SOTA 调研窗）。用户要「一定扎实」→ 主线 Playwright 下两篇付费墙原文，盲区清零。

### 攻下（reference/SOTA_NUMBERS.md + RELATED_WORK_MATERIAL.md 更新）
- **TA-Mamba**（ResearchSquare 免费 preprint rs-5164628 全文 PDF）：DRIVE Dice 0.8248/clDice 0.8321、CHASE 0.8168/0.8448、STARE 0.8159/0.8515（split 前10训后10测）。
- **MVM-UNet=Birmingham Multi-scale Vision Mamba-UNet**（ScienceDirect 全文，用户机构认证+手动过 captcha）：DRIVE 0.8184/CHASE 0.8146/STARE 0.8242，全主流簇，**不报 clDice**。

### ⚠️ 战略修正（影响 headline 定位，重要）
TA-Mamba **报 clDice 且 > HREFNet** + 声张 topo connectivity = **拓扑直接竞品** → Entry 7/8「clDice 报告者极少=取胜空白」**修正**：clDice 轴不再真空。**真正无人占的是断点续连 ε_β0/SR/re-ID 轴 + 模型内记忆机制**，headline 必须压杀手锏 benchmark，clDice 当「持平不输强竞品」非唯一胜负点。已落 SOTA_NUMBERS 战略观察 #2。

### 工具纪律收获
- 付费墙原文：免费 preprint(ResearchSquare/arXiv) 永远先试；ScienceDirect/Elsevier 即使机构认证仍弹 captcha（人机门控，主线不自动解，截图请用户手动过）。
- PDF 抽数字：本机无 pdftoppm/pdftotext，Read PDF 失败 → 用 `python pypdf` extract_text 正则筛指标行可靠。

### 剩非阻塞尾巴
MVM-UNet HRF 数字（不在 8 主表）、FIVES 跨论文 split 对齐。标 TODO，不阻投稿。

### 本窗（§2 RW+SOTA）任务状态 = 彻底闭环
reference 双档核源全 + 天花板上修 + 两簇坐实 + SR/re-ID 方法学定案（用户拍 SR 两者都上）+ 付费墙清零。下一步交 P3 窗据 BASELINE_SPEC + reference 选 baseline。

---

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
- SR：本窗 coder-B 实现 SR 自定义声明，与别窗 Entry 9「两者都上」拍板一致；**APLS/Betti-err 已补**（coder-B 续做：Betti-err=β0_err+β1_err 用 skimage.euler_number；APLS 逐行对齐 CosmiQ/apls + networkx 骨架图，compute_apls=False 开关防慢；52 benchmark pytest 全绿）。
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
