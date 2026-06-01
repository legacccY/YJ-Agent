# ICLR 2027 项目日志（时间倒序，单一日志真源）

**规则**：每次会话开始读最新 entry，结束写新 entry。今后所有进度入此（替代 WORKLOG.md 重复部分）。

> 格式：`## YYYY-MM-DD（会话 N）` → 完成 / 待续 / 命中率回退诚实记录

---

## 2026-06-01（会话 13，Stage1 @256 收敛达标 ep40 手停 → Stage2 @256 DP-Loss 启动 job 1433944）

### 起因
开门查 256 重训进度：Stage1（job 1433796）跑到 ep39/200 良好，用户问可否停了跑下一阶段。

### 决策：Stage1 ep40 手停（非自然早停）
- **进度曲线**（聚合 MSE 口径 val_PSNR）：ep34 30.07(best)→ ep40 **30.145**(新高)，train_loss 单调降 0.0148→0.0128，SSIM 0.9847（128 时仅 0.946，大涨）。
- **判断**：曲线仍微爬但增幅 ~0.1dB/6ep；patience=30 自然早停还要耗 ~22h 换边际几个 0.01dB；E1（聚合 30+ = 每图 ~33dB）早 PASS；真正卡命中率的是 E3（ΔAUC 天花板），gated on Stage2 DP-Loss 而非 Stage1 多跑 → 手停切 Stage2 性价比最高。
- best ckpt = ep40 权重（396 tensor，torch.load `weights_only=False` 可加载，30.145）。

### 执行（严格串行防失败，全部历史坑预排除）
1. 备份 best → `stage1_planA_256/best_visienhance_frozen.pth`（184MB，防 scancel 撞落盘写一半）。
2. `scancel 1433796`（Stage1）→ best ckpt mtime/尺寸未变，未损坏。
3. 旧 Stage2 依赖 job 1433799（`afterok:1433796`）随 Stage1 取消变 `DependencyNeverSatisfied` → scancel 弃用。
4. fresh `sbatch submit_s2_256.sh` → **新 job 1433944** @ gpu4090n5（20:21 起）。

### 启动验证（6 历史失败模式逐条排除）
| 坑 | 状态 |
|---|---|
| module load→6s FAIL | ✓ submit_s2 绝对 python 路径 |
| `module.`前缀→30s FAIL | ✓ `_raw_model.load_state_dict`(line 374) + 存的也是 `_raw_model.state_dict()` |
| torch2.6 weights_only | ✓ resume 用 `weights_only=False`(line 373)，numpy scalar 不报错 |
| 包/权重缺 | ✓ visiscore/qad/lpips-alex/efnet 全加载 |
| NaN | ✓ lr 1e-5 + λ_dp 0.1 保守 |
| 空数据集 | ✓ train=69564/val=9936（HPC 路径 CSV） |
| Stage2 PSNR 下滑 | ✓ val_severity=mixed |
- resume 日志：`Resumed from best_visienhance.pth (epoch 0, model-only=True)` ✓；DP-Loss EfficientNet-B0 extractor 加载 ✓（会话 9 死过这次活）；仅 DDP `Grad strides` 无害警告，无 traceback/NaN/OOM。

### 待续（会话 14）
- 盯 1433944（patience=999 不早停，80 epoch）：DP-loss 应非零、val_PSNR 不应像会话 10 下滑（val_severity 已修）。
- Stage2 完成 → sync best 回本地 → `eval_diag_paired.py` 复测 E3/E7（256 原生 eval 应消除分辨率失配天花板）。
- 若 ΔAUC 仍 >1.5% → 升 λ_dp 0.1→0.2 重跑 Stage2（config 注释已留）。

---

## 2026-06-01（会话 12，E7 实证 PASS + E3 失败根因确诊=分辨率失配 → 启动 256 重训全自动链）

### 起因
会话 11 修了 DP-Loss 三 bug 后重训出 Stage2（PSNR 32.56，Stage1 32.85）。本会话续做增强模型**诊断保持评估**（E3/E7），目标按 ACCEPTANCE 硬线 `|ΔAUC|<1.5%` / 一致率 `>95%`，不走 fallback 降水。

### 关键发现 1：eval 上采样 bug 已修，B3 oracle 复活
- **bug**（`eval_stage2_compare.py:118`）：IMG=128 → `F.interpolate(128→224 bilinear)` 上采样糊图喂 B3 → B3 oracle 连 ref 都掉到 AUC 0.54（随机），ΔAUC 全废。
- **B3 真实训练协议**（`finetune_efficientnet.py:48`）：`VAL_TFM = Resize(256)→CenterCrop(224)`，期望 256 原生 center-crop，非上采样。
- **修复**（`eval_diag_hires.py` / `_v2` / `_paired`）：IMG=256 → `center_crop_224`，无上采样 → oracle 恢复 **AUC_ref 0.917**。

### 关键发现 2：E7（DP-Loss 消融）实证 PASS ✓✓（可进论文）
- 严格配对（同图同退化，一次前向收 ref/deg/enh_S1/enh_S2），`eval_diag_paired.py`，n=3627 pos=117：
  | 配对指标 (S2−S1) | 值 | 95% CI | 判定 |
  |---|---|---|---|
  | ΔAUC_enh | +0.84% | [+0.18%, +1.54%] | 显著>0 ✓ |
  | ΔKL(ref‖enh) | −0.067 | [−0.084, −0.050] | 显著<0（DP 更保信念）✓ |
  | McNemar(S2 vs S1) | b=44, c=136 | **p=4e−12** | **E7 PASS** ✓ |
- DP-Loss 把 no-DP 判错的 136 例救回、只弄坏 44 → 净 +92。**Lemma 3 实证成立且极显著。**
- 结果 csv：`results/stage2_diag_{hires,hires_v2,paired}.csv`。

### 关键发现 3：E3（绝对线）仍 FAIL，根因=分辨率失配天花板
- Stage2：\|ΔAUC\|=4.2%（<1.5% ❌，连 fallback<3% 都没过），一致率 87.0%（>95% ❌）。enh-vs-ref McNemar b=379 c=92 → 增强把 ref 判对的 ~12% 搞错。
- **根因**：VisiEnhance 全程 **train@128**（所有 config `img_size:128`），但 **B3(224) + VisiScore(224 backbone) 皆 224 原生**，评估被迫 @256 → 128 模型在 2× 没见过分辨率推理，增强打折 + reviewer 一眼可见硬伤。
- **不降水决策**（用户拍板「不能因困难降论文水平」）：256 重训对齐分辨率，从根上消除天花板。E7 已证 DP-Loss 有效 → 256 重训是放大已验证机制，非赌博。

### 执行：256 重训全自动链（HPC gpu4090，4×GPU DDP）
- 降质数据本就是 256px（dataset 原 downscale 到 128）→ **无需重生成**。
- 新 config：`configs/visienhance_s1_planA_256_hpc.yaml`（img_size256 / batch8 / from scratch / severity mixed）+ `_s2_planA_256_hpc.yaml`（续 S1 best / DP λ_dp=0.1，原 0.05 太弱）。
- 新 submit：`submit_s{1,2}_256.sh`（4GPU DDP，48h）。
- **SLURM 依赖链**：Job **1433796**(Stage1 RUNNING gpu4090n5) → `sbatch --dependency=afterok:1433799`... 实为 **1433799**(Stage2 PENDING Dependency)，Stage1 exit 0 自动起。
- **smoke PASS**：RUNNING 后 batch 8@256 仅 10.8GB/24GB，4 GPU 84-100% 利用，5.18 it/s（~7min/epoch），无 OOM/traceback。

### 待续（会话 13）
1. 查 1433796/1433799 状态（`python hpc_monitor.py <job>`，或 HPC_WORKFLOW 工具）。
2. 两阶段收敛后 **sync best ckpt 回本地** → `eval_diag_paired.py` 复测 E3/E7（IMG 已 256，与训练分辨率对齐）。
3. 若 ΔAUC 仍 >1.5%：升 **λ_dp→0.2** 重跑 Stage2（submit_s2_256 改 config），或 DP-Loss 升 feature-level。
4. 达标后回写 STORY_FRAMEWORK §4 + ACCEPTANCE E3/E7 + paper §7 frozen 数字。

### 命中率
- E7 实证落地（DP-Loss 显著，硬结果）→ Lemma 3 从「推导」变「推导+实证」，强化 Claim 2。E3 当前 FAIL 但根因确诊+正确修复路径在跑，不确定性从「机制是否有效」降为「分辨率对齐后能否压到 1.5%」（更可控）。

---

## 2026-05-30（会话 9，VisiEnhance nocrop 续训到收敛 + PSNR 定义澄清 → E1 实际达标）

### 起因
会话 8 收工时 nocrop 验证停在 ep15（val 28.01）。本会话从 `last_visienhance.pth` resume 续训（PID 22296，12:16 起，约 8h），用户睡前指示「训练到极限了停了看结果」。

### 续训结果（ep17→56，config `visienhance_s1_planA_nocrop.yaml`，loss λ_l1=1.0 / λ_lpips=0.01）
- 轨迹：ep17 27.82 → ep40 28.95 → **ep44 起 28.97 锁死，ep44–56 连续 12 epoch 不动**（聚合 PSNR 平台）。
- ETA 显示还剩 28.5h 才到 ep200 上限 → 续跑纯烧时间，**已 kill PID 22296**。
- best checkpoint：`checkpoints/visienhance/stage1_planA_nocrop/best_visienhance.pth`（@ep44/51）。

### 🔑 关键澄清：训练日志 28.97 是「聚合 MSE PSNR」，论文标准报法（每图均值）= 32.5，E1 实际 PASS
- 独立写 `scripts/eval_nocrop_e1.py`，**同时算两种 PSNR 定义**，在 val split（n=3312，与训练同集）对照：
  | PSNR 定义 | input | enhanced |
  |---|---|---|
  | 聚合 MSE（`train_visienhance.validate()` 用：`10log10(1/全集平均MSE)`）| 16.44 | **28.92** ←复现训练 28.97 ✓ |
  | 每图均值（图像复原论文标准：BasicSR/所有 SR-denoise benchmark）| 22.33 | **33.10** ← **E1≥30 PASS** ✓ |
- test split（n=6626）：每图均值 enhanced **32.74**、gain +10.6。
- 两定义因 PSNR 的 log 非线性必然不同（Jensen：好图 PSNR 极高拉高均值）。input baseline 同规律佐证（16.4 聚合 vs 22.1 每图）→ 非 bug，是定义差。**不是挑数字**：两个都算清、都复现、都入 json。
- 结果 json：`results/visienhance_nocrop_e1.json`(test) + `results/visienhance_nocrop_e1_val.json`(val)。

### 结论：Stage 1 nocrop 实际达标，无须 Plan B
- **E1：PSNR 32.5 dB（每图均值，论文报法）≥30 PASS；SSIM 0.946 ≥0.92 PASS。**
- 视觉验证（`scripts/make_visienhance_demo.py` → `demo_nocrop_ep51.png`，6 样本 degraded/enhanced/ref）：增强图清晰还原、贴近 reference，无 hallucination，守红线 R8。
- 会话 8「裁剪 bug = 卡死真因」彻底证实：去裁剪后从 25.5 死点 → 32.5（每图）/28.9（聚合），oracle 37.5 余量充足。

### ⚠️ 待回写 / 对齐（会话 10）
1. **统一全项目 PSNR 定义口径**：决定 paper/ACCEPTANCE E1 用每图均值（推荐，领域标准）还是聚合；两者都在 json 留档。若用每图均值，需在 train_visienhance.validate 旁注明日志是聚合（偏保守），避免日后自己看混。
2. 全量重生成 light + heavy（`regen_nocrop.py --levels light heavy`）合 mixed 训练集 → Stage 2(DP-loss) → Stage 3(hinge)。
3. eval_visienhance.py 适配 nocrop 预生成数据（原脚本 severity="moderate" on-the-fly，与 nocrop medium 预生成不匹配，E3/E4/E5/E6 需对齐数据源）。
4. 回写 STORY_FRAMEWORK §4 + ACCEPTANCE E1 + paper §7 Table（用 frozen 32.5/0.946）。

### 命中率
- Stage 1 实验侧定型且**达标**（E1 PASS，可复现脚本+json 齐全）。最大不确定（PSNR 能否过 30）已正向消解。下一步 Stage 2/3 + 全量数据。

---

## 2026-05-29（会话 8，VisiEnhance PSNR 天花板诊断 + 裁剪 bug 根治 + 无裁剪重训验证）

### 起因
续训 Plan A（15M）跑到 ep42 仍卡 val_PSNR 25.5，与 1.7M v0（25.55）**完全相同** → 用户问是否停下改实验。

### 诊断（三层脚本，`project/scripts/diag_*.py`，全部新建）
- **容量证伪**：9× 参数同 PSNR，不是容量问题。
- **`diag_visienhance_ceiling.py`**：旧裁剪 val(medium) baseline 15.87 / **oracle 仿射上界仅 26.43** / 模型 25.54（已达上界 96%）→ 不是模型，是数据天花板。
- **`diag_degradation_decomp.py`**：光度退化可逆到 50.94 dB、模糊单独 38.73 dB —— 单项都不致命。
- **`diag_crop_killer.py`（决定性）**：复刻 `degrade.py` 管线 toggle crop → WITH crop oracle 31.75 / WITHOUT crop **39.84**（+8 dB）。
- **元凶**：`degrade.py` 的 `apply_random_crop`（ratio 0.75-0.89, prob 0.5）。裁剪+缩放使降质图与原图**像素错位**，restoration 网络被迫 hallucinate 被裁组织（违反红线 R8），PSNR 对任何容量都崩 → 解释了 1.7M=15M=25.5。

### 修复（用户拍板「工作量再大也要对论文最强的办法」）
- **设计决策**：裁剪/取景错位**不属增强任务**，归 **Theorem 2 query-for-retake 通道**（强化 Claim 3）。增强只处理像素对齐的可逆退化（亮度/对比度/色偏/模糊/JPEG）。
- `data/degrade.py`：`degrade_image` 加 `crop_prob` 参数（None=默认；0=关裁剪）。
- `scripts/regen_nocrop.py`：按 csv 行重生成无裁剪配对 → **medium 全量 49700 张** → `data/paired_dataset_nocrop/medium/` + `data/quality_labels_nocrop.csv`（原 `paired_dataset` 保留不动，可回滚）。
- 重生成后真实数据 oracle 上界 **26.43 → 37.49 dB**（`diag_nocrop_ceiling.py` 实测）。

### 验证训练（`configs/visienhance_s1_planA_nocrop.yaml`，fresh init，medium-only，60ep 上限）
- 轨迹：baseline 16.47 → ep0 24.24 → ep5 26.31 → ep8 27.12 → ep15 **28.01** → ep16 27.88（用户主动收工停训）。
- **裁剪假设确认无疑**：旧死点 25.5 已甩开 +2.5 dB 且持续上升，oracle 余量到 37.5。
- checkpoint：`checkpoints/visienhance/stage1_planA_nocrop/best_visienhance.pth`（best **28.008** @ep15, SSIM 0.9795）。
- 旧卡死进程（PID 15384，planA 裁剪数据）已 kill；验证进程（PID 15984）收工时 kill。

### 待续（会话 9）
1. **续训 nocrop 到收敛**（resume `stage1_planA_nocrop/last`）；若卡 ~28 不过 30 → 加 MSE loss 项 / 提 lr / LPIPS→0 重试。
2. 达标后**全量重生成 light + heavy**（`regen_nocrop.py --levels light heavy`），合 mixed 训练集。
3. 完整 Stage 1→2(DP-loss)→3(quality hinge) + E1-E12。
4. **回写主文档**（本会话只记录决策，未改）：STORY_FRAMEWORK §4 Claim 2/3 + ACCEPTANCE E1 阈值 + phase_07 plan，把 crop→query-channel 正式写成设计决策。

### 命中率
- 本会话扫清 M1-M2 最大实验障碍（PSNR≥30 从「不可能」变「可达」），且把 bug 转成强化 Theorem 2 的 contribution。诊断脚本 = 可复现证据链。实验侧实质推进，待续训达标后落 E1 数字。

---

## 2026-05-27（会话 7，Appendix 全面 LaTeX 化 + 主文正文 + bib，纯写作零实验）

### 完成（全在 `meeting/ICLR2027/`，pdflatex+bibtex 全程 exit 0）
- **A1 Q-VIB full proofs** `appendix/A1_qvib.tex`：Prop1 ELBO(5 步) + Lemma1 单调 + Lemma2 softmax ℓ∞→ℓ1(清理源文档含糊段，给干净 Jacobian 算子范数证明) + Thm1 attention drift(4 步) + Prop2 熵单调(4 步)。**5-theorem closure LaTeX 化全齐**(A1+A2+A2.3+A3)。+ `A1_qvib_compact.tex` 接 §3。
- **主文 Abstract→§9 正文填充**：Intro(problem/gaps/hook/C1-C4) + Related Work + §3-§6 + §8(failure 3-mode 49/32/19 + limitations) + §9。§7 只搭结构留 TODO 占位(红线4：未冻结数字不写)。+ Ethics Statement + Reproducibility Statement(ICLR 标准节)。
- **A4 ITB 构建协议** `A4_itb_construction.tex`：源池/质量打分/降质模型/子集定义/组成表(LQ300/HQ360/Edge660/Diverse1500=2820，从 itb_subsets.csv 实读)/QC/release。**纠错**：实为 Edge660/Diverse1500(非旧约 ~500/~600)；ITB= 真实curation+合成降质混合(LQ=ISIC heavy/Edge=light+medium/Diverse=Fitz original)，与 VisiEnhance 训练用 paired_dataset 149K 不同。
- **A18 Failure modes** `A18_failure_modes.tex`：源 `failure_mode_clusters_v2.json`(权威)。KMeans k=3 n=57(阈值 FP>0.85/FN<0.15)，质心表(49.1/31.6/19.3%)，per-mode→4-action，entropy gate 实证动机。
- **A19 LLM-judge 协议** `A19_llm_judge.tex`：3 LLM panel + 200 case 分层 + 4 轴 rubric + Cohen/Fleiss κ>0.5 floor + disclaimer。设计参数是 protocol(非结果)，ratings/κ pending。
- **A20 Cost-benefit** `A20_cost_benefit.tex`：cost model + net-benefit + triage simulation 方法论，数字 pending。
- **A21 Pre-emptive rebuttal** `A21_rebuttal.tex`：L20 草稿**重写非 paste**，5-concern，label 全换真实名，**删光未冻结/编造数字**(real-LQ ECE0.13/artifact≤5%/cross-modality ρ 等)，不点名 BMVC venue(脱敏)。
- **A23 Reader-study disclaimer** + **A26 Reproducibility**(环境/seed/split/Zenodo，CODEBASE_README 去匿名后取 infra) + **A0 Notation 表**。
- **references.bib**(19 篇外部引用) + preamble natbib + 全文 `\citep/\citet/\citealp` 接线。
- **DATA_INVENTORY 纠错**：Edge/Diverse/LQ/HQ 计数+阈值对齐 csv。
- **BMVC 匿名 repo（`release/`，非封印区）**：主页 `README.md` 重写（标题对齐投稿主文 `itb_paper.tex`=QCTS、headline 置顶、硬件纠错 A100→消费级 GPU）；匿名审计修 4 项 —— **P1 致命去匿名**（`GITHUB_SETUP.md`/`git_init_with_history.sh` 含身份词 legacccy/yj200/余嘉/xjtlu/liverpool → `.gitignore` 排除 + 脚本自删 + 去 commit message 泄漏）、P2 DATASET_CARD 标题对齐、P3 质量区间对齐真实 csv、P4 data/README 死链。封印 `meeting/BMVC/` 零改动（仅 read 确认标题）。

### 当前 paper 状态
- **33 页**(主文 9 章 stub-filled + Ethics/Repro + Appendix A0/A1/A2/A2.3/A3/A4/A18/A19/A20/A21/A23/A26)，bibtex 19 ref 全 defined，零 undefined cite/ref，全 tex 零 banned 字样(Q-VIB/VisiScore/Bayesian/we prove/doctors confirmed/BMVC/MICCAI/作者名)。

### 待续（全部 gated on 实验，本会话纯写作不能碰）
- §7 result tables(Table1/E3/E5/cross-domain/fairness) + A5/A16/A17/A22/A24 → **必须 Plan A 重训 + re-eval 后才有 frozen 数字**(红线4)
- 续训 ep15→200(`/loop /run-experiment`)
- Plan A re-eval 后：重导 n=19878 per-sample csv + 决定 cross-domain 锁定值

### 命中率
- 本会话纯写作产出(theory LaTeX + 防御附录 + repro)，无新实验 → 命中率维持 ~38%。A 类(L1-L5 全 LaTeX 化)+ E 类(L19/L20/L21 全 LaTeX 化)写作侧 deliverable 落地，降低 reviewer 第一轮风险。

---

## 2026-05-27（会话 6，锁定数字 audit + hook 假阳性 + 5-theorem β/√ε 一致性）

### 完成
- **ICLR2027 paper 骨架搭建 + Appendix A2 LaTeX 化（L2/L3）**：
  - `meeting/ICLR2027/`：`preamble.tex`（匿名宏 `\qvib`→"QC-VIB" 等 + 定理环境 + 数学算子）、`main.tex`（§1-§9 锁定结构 stub + Contributions C1-C4 + Appendix input）、`appendix/A2_prop3_lemma3.tex`（Prop 3 五步 + Lemma 3 四步**完整证明**，√ε canonical）、`A2_prop3_lemma3_compact.tex`（§4.4 正文 compact 陈述）、`.gitignore`（latex 产物）
  - **匿名策略**：模型名走 `\newcommand` 宏（脱敏字符串），tex 不出现内部名 → 过 redline hook（hook 实测拦下 "VisiSkin-Agent"/"Bayesian" 两处误写，已修）+ 投稿前一行切换
  - **A2.3 Theorem 2 + A3 Corollary 1 LaTeX 化（L4/L5）**：`A2_3_theorem2.tex`（4-action setup + policy + Lemma 2.1-2.4 + 主定理 4-case proof + Cor 2.1/2.2）、`A3_corollary1.tex`（Murphy 分解 4-step + ε_qts≈0.037 → ECE_comp≤0.116）+ §5.2/§5.3 compact；main.tex 取消注释 input
  - 踩坑：`\ae` 与 LaTeX 内置 æ 连字冲突 → action 宏改 `\actd/\acte/\actq/\actr`
  - **编译验证**：pdflatex（texlive 2025）两遍 exit 0，**9 页**（A2+A2.3+A3），无未定义引用
  - 剩 A1 (Q-VIB Prop1/Lemma1/Thm1/Prop2) LaTeX 化（源 `V-QIB数学推导.md`）+ 主文正文填充（M3）
- **5-theorem 理论一致性审计 + β/√ε 统一**（LaTeX 化前去风险）：
  - 审计 Theorem2 / Prop3_Lemma3 / Corollary1 三文档常数自洽性
  - ✅ Theorem2（τ_enh≈0.35/τ_high≈0.55/c_e=0.02/δ_TV=0.098 与 toy test 一致）、Corollary1（L_T≈0.239→K_T≈0.461→ε_qts≈0.037→ECE_comp≤0.116 链自洽）均干净
  - ❌ **Prop3_Lemma3 β 常数三处打架**：header/L3 正式陈述写 `β=M·L_q·√2` + linear `−βε`；修正段写 `β=M·L_q/√2` + `−β√ε`；§1.3 数值用 `β=4`（bug）
  - **正解唯一**（Pinsker: TV≤√(ε/2) → Fannes: ΔI≤M·L_q·√ε/√2）：**√ε scaling, β=M·L_q/√2≈0.735**，与 toy test(`test_lemma3_sqrt_epsilon_scaling`, β_theory=0.735)+ 会话3 TODO 一致
  - **统一修复（用户拍板）**：Prop3_Lemma3（header/P3 残差 2β√ε/L3 陈述/Step4 去 correction 叙述/§1.3 数值 0.33 nats ~80× gap）+ STORY_FRAMEWORK §核心论点 Claim2 Lemma3 行（`−βε`→`−β√ε`）+ test docstring（L3'→L3）；Theorem2 无 β 项（确认）、Corollary1 本就干净
  - 验证：无 linear βε / ·√2 / L3' 残留，β√ε 13 处，test **10/10 PASS**
  - **解决会话3 遗留 TODO**："V2.0plan 老草稿 βε linear 改 β√ε" ✅
- **锁定数字 audit 30 项完整核账**（`scripts/check_numbers_consistency.py`）：
  - **问题 A — Q-VIB 核心表（n=19878）数字真实，审计脚本之前指错对象**：
    - AUC 0.707 / ECE 0.098 / Entropy 0.225 / ρ −0.165 + Adaptive Prior 0.688/0.100/−0.169 真实出处 = `results/eval_report_ablation.md`（5 q̅-分位 ×~3976 = 19882 ≈ 19878，p=8e-121 印证大样本）
    - 旧脚本拿 `itb_predictions.csv`（n=2820 ITB pool，更难的对抗子集）重算 → 必然 FAIL（ECE 0.31 vs 0.098 等）
    - **修复**：7 个核心 check 改从 `eval_report_ablation.md` 解析（同 VisiScore md-parse 写法）→ **ICLR 11/11 PASS**
    - per-sample n=19878 csv 从未导出（只存 md 聚合）→ **Plan A re-eval（M1-M2）必须重导出**
  - **问题 B — Cross-domain ρ locked 无源 csv**：
    - STORY_FRAMEWORK locked ham10000 −0.108 / pad-ufes −0.150 全项目**搜不到任何出处**
    - 权威 `external_ablation.csv`（有 p 值、n 对、baseline F）实为 **ham −0.164 (p=5e-61) / pad −0.236 (p=1e-30)**，与重算完全一致
    - **决定（用户拍板）**：先不改 master doc 数字，只在 STORY_FRAMEWORK 表加 `⚠️待核` 标注；审计脚本降级为 PENDING（不 FAIL 不 PASS，不阻塞）；延 Plan A re-eval 后再 frozen
    - 脚本现状：**BMVC 17/17 + ICLR 11/11 PASS + 2 PENDING，exit 0**
- **hook 假阳性根治**（会话 5 只分离双模式，未解决根因）：
  - 根因：doc 写作检查 pattern 命中的是 STORY_FRAMEWORK 的 R1-R10 规则表本身（规则手册必须引用禁用词当反例）+ ACCEPTANCE 匿名红线
  - 修复（`iclr_post_edit.js` 实际执行 + sh/ps1 parity 同步）：doc 模式 (a) 去掉 `anonymous2025`（脱敏由 tex 全量检查负责），(b) 跳过引号包裹的匹配（negative lookbehind on `" “ ” 「 」`）
  - 验证：doc 3/3 exit 0、非引号 banned 仍 flag(exit 2)、tex 引号内仍 flag(exit 2)
- **Lemma 3 √ε toy** 确认 `test_theorems_numerical.py` 10/10 PASS（`test_lemma3_sqrt_epsilon_scaling_paired_latent` paired Gaussian + Lipschitz toy 验 slope vs β_theory=0.735，已存在，本会话验证）

### 待续
- 续训 ep15→200（`/loop /run-experiment` + resume，实验部分）
- **Plan A re-eval（M1-M2）后必办**：① 重导 n=19878 per-sample csv（补 per-sample 可复现）② 决定 cross-domain 锁定值（−0.108→−0.164 / −0.150→−0.236 或保留待解释）
- STORY_FRAMEWORK Table 1（ITB-LQ/HQ）源 `eval_report_all.csv` 仍不存在（标 待重跑，正常）

### 命中率
- 本会话无回退，纯诚信加固（audit + hook）。命中率维持会话 5 的 ~38%

---

## 2026-05-25（会话 5，会话截断核查 + hook 假阳性修复）

### 完成
- **核查会话 3 末段截断**：对照操作时间线逐一核实 15 个操作的落盘状态
  - ✅ L25 文件完整（668 行，末行 "8. 待续" 正常结尾）
  - ✅ PROJECT_LOG "E 类 3/3" entry 存在
  - ✅ README / ACCEPTANCE_CRITERIA L19-L21 ✅ draft 已更新
  - ✅ ps1 hook Bayesian 模式已同步
  - ❌ README.md L25 索引仍 ❌（会话末被截）→ **已修复 → ✅ draft**
  - ❌ ACCEPTANCE_CRITERIA.md L25 索引仍 ❌ → **已修复 → ✅ draft**
- **修复 `iclr_post_edit.js` hook 假阳性**：
  - 根因：`Q-VIB\b|VisiSkin-Agent|VisiScore-Net|VisiEnhance-Net` 模型名在 planning doc 触发误报
  - 修复：分离双模式 — tex 文件全量检查，planning doc 只查写作质量规则（`TS always reverses|universal reversal|doctors confirmed|clinically validated|clinical decision support`）
  - sh/ps1 待同步（JS 是实际执行 hook，已足够）

### 下一步
- 续训 ep 15→200（`/loop /run-experiment` + resume checkpoint）
- sh/ps1 hook 同步（无阻塞但保持一致性）

---

## 2026-05-25（会话 4，训练崩溃修复）

### 完成
- **诊断 train_visienhance.py 崩溃**：`ConnectionResetError [WinError 64]` — wandb 内部 asyncio service process 在 Windows 命名管道断链时未捕获异常，训练在 ep 15 崩溃
- **彻底修复**：
  - `os.environ["WANDB_DISABLE_SERVICE"] = "1"` — 禁 wandb 内部 service process（根治）
  - `wandb.init` / `wandb.log` / `wandb.finish` 全套 try/except 防御
  - 训练逻辑、checkpoint、state.json 写入不受 wandb 崩溃影响
- **训练状态**：ep 15/200，val_psnr=25.059，checkpoint 完好（`stage1_planA/last_visienhance.pth`）

### 下一步
- 从 ep 15 续训：`/loop /run-experiment project/train_visienhance.py project/configs/visienhance_s1_planA.yaml --resume D:/YJ-Agent/checkpoints/visienhance/stage1_planA/last_visienhance.pth`
- ep 10 Decision Gate 补评估（ep 15 已过，可直接看当前 val_psnr 趋势）

---

## 2026-05-24（会话 3，A 类 5/5 + E 类 3/3 + Phase A 脚本全套）

### 续完成（同会话晚段，E 类防御性写作 3/3 全 done）
- **L19 10 轮 adversarial review**：`plans/L19_adversarial_review_10rounds.md`
  - R1-R10 reviewer profile 矩阵 + 每轮深度攻击 + severity 标注
  - 5 个 severity-5 致命攻击 surface：R3 clinical realist / R6 OOD pessimist / R9 scope critic / R10 safety / R1 stats hawk (必写)
  - 21-项 action table 分配到 M2-M4
- **L20 Pre-emptive rebuttal §A21**：`plans/L20_preemptive_rebuttal_A21.md`
  - LaTeX 模板, 5 subsection (stats / clinical / OOD / scope / safety), ~1.5-2 页
  - Abstract / §1.4 / §8 配套修改清单
  - 10 项 R-numbered 写作 alignment checklist
- **L21 Failure mode taxonomy**：`plans/L21_failure_mode_taxonomy.md`
  - KMeans k=3 cluster 3 mode 详解（heavy_blur 49% / color_distorted 32% / ambiguous 19%）
  - per-mode 4-action 映射 (M1→retake / M2→enhance / M3→refuse)
  - **关键发现**：M3 (q=0.38, ambiguous) 在 salvage band 内但 enhance 无效 → **Theorem 2 policy 加 secondary entropy gate**（已 backport 修订 Thm 2 doc §1.2 + Case 2）
  - P1 实证 (q<0.35 retake_rate 100%) + P3 实证 (q∈[0.35,0.40] quality_improved 仅 16.2%) 已 live verify

### 命中率推进（会话晚段）
- E 类 3/3 lever 全 done → 协同 +3% unlock
- A 类 +5% + E 类 +3% = +8% 已 unlock
- 当前预估命中率：**30% (基线) + 8% = 38%** (M1 W1 阶段超额完成, 原计划只 32.5%)
- 距 78-80% 目标还需 +40-42% (B/C/D/F 类 lever, M1 W2 - M4)

### 副产物：Theorem 2 policy 修订
原 Eq.(2) 单 quality threshold partition → 修订为 quality + entropy 双 gate. 主结论 Eq.(7-9) 不变. **这是 L21 实证 driven 的理论 refinement**, 反向证明 doc + 实证迭代的价值. 

---

## 2026-05-24（会话 3，A 类 5/5 推导 + Phase A 脚本全套）

### 完成（训练并行期间）
- **L4 Theorem 2 (agent risk bound)** 完整推导：`plans/Theorem2_agent_risk_bound.md`
  - decision-theoretic 4-action space {direct, enhance, query, refuse}
  - 4 lemmas (entropy-risk coupling / enhancement gain / threshold window / query-refuse safety) + main theorem 4-case proof
  - Corollary 2.1 (agent never worse) + 2.2 (population-level)
  - Δ 显式 bound + τ_enh ≈ 0.35 / τ_high ≈ 0.55 估计
- **L2 Proposition 3 + L3 Lemma 3** publication-grade 升级：`plans/Prop3_Lemma3_visienhance_theory.md`
  - Prop 3: 显式 (A1)-(A4) + 5-step proof (Q-VIB ELBO → encoder var → σ²(q̄) gap → quality lift → bound)
  - Lemma 3 关键修正：$\sqrt{\epsilon}$ scaling (Pinsker-optimal), 非 $\epsilon$ linear；显式 β = M·L_q/√2
  - 三阶段训练理论 motivation 写清
- **L5 Corollary 1 (Q-VIB + QCTS ECE bound)** 推导：`plans/Corollary1_qvib_qcts_ece_bound.md`
  - $\text{ECE}_{\text{comp}} \leq \min(\text{ECE}_{\text{QV}}, \text{ECE}_{\text{QCTS}}) + \epsilon_{\text{qts}}$
  - $\epsilon_{\text{qts}} \approx 0.037$ 数字预测 + 4-step proof
  - R10 防御写法模板 (cite BMVC 不搬数字)
- **Theorems toy 数值验证 9/9 PASS**：`tests/test_theorems_numerical.py`
  - Prop 3 entropy 单调性 + counter-control
  - Lemma 3 Pinsker upper bound on MI drop
  - Thm 2 P1/P2/P3 + Cor 2.1 + bootstrap CI excludes 0 + Lemma 2.1 Gibbs coupling
- **Phase A 自动化脚本全套**：
  - `scripts/iclr_grep_redlines.sh` CLI 红线扫描（默认 paper material 干净，`--include-guidance` 扫指导 doc）
  - `scripts/check_numbers_consistency.py` 17 → 30 数字（拆 BMVC block / ICLR audit 两段）

### 关键发现
- **STORY_FRAMEWORK §锁定数字 vs 实际 csv 9 项 audit hit**：
  - test set n=19878 的 Q-VIB Full AUC/ECE/Entropy/ρ 在项目里没有对应 csv 导出
  - Cross-domain ρ (HAM10000 −0.108 / PAD-UFES −0.150) 与实测 (−0.164 / −0.236) 偏差大
  - 含义：要么 (a) 历史 eval 没存 csv → Plan A 完成后必须补；要么 (b) 锁定数字 stale → 更新 STORY_FRAMEWORK
- **A 类协同效应解锁**：5/5 lever 推导 done → A 类 +5% 命中率全解锁 (从 +2.5% 跳到 +5%)
- **Lemma 3 推导发现 $\sqrt{\epsilon}$ scaling**：投稿前必须把 V2.0plan 老草稿的 "βε linear" 改成 "β√ε"，否则 reviewer 用 Pinsker counterexample 撕

### 待续（M1 W2 D12-D14 + 后续）
- [ ] 续训进行中（PID=25804，val_severity=medium + lpips=0.05，从 ep6 续）→ ep10 Decision Gate 重评
- [ ] **L2-L5 推导 LaTeX 化** (M2 D1-D7) → §3-§5 主文 + Appendix A1-A3 (~15 页 supp)
- [ ] **Lemma 3 √ε scaling toy 升级**：用 paired Gaussian latent + Lipschitz toy classifier verify slope = β
- [ ] Plan A Stage 2 (DP-Loss) 训练 → 验证 P1 (DP-Loss ≤ 0.05) + P2 (ΔAUC) + P3 (ECE-MI 相关)
- [ ] STORY_FRAMEWORK §锁定数字 决策：补 n=19878 csv 还是更新数字

### 命中率回退
- 本会话**无回退**，反而推进：A 类协同从 +2.5% 拉满到 +5%
- 当前预估命中率：**32.5% + 2.5%（A 类协同满血）= 35%**（M1 W1 阶段目标达成）
- 距 78-80% 目标还需 +43-45%（B/C/D/E/F 类 lever, M1 W2 - M4 持续推进）

---

## 2026-05-24（会话 2，Stage 1 训练启动 + ep6 Gate 修复）

### 完成
- VisiEnhance Plan A 架构升级：enc_blocks=[2,2,2], mid_blocks=6 → ~15.3M 参数（3-level U-Net, ch: 64→128→256→512）
- 冒烟测试 6/6 全通过（param_count / forward / range / FiLM identity / CUDA / AMP）
- Stage 1 训练启动（PID 28460），/loop 全自动监控，每 epoch ~23min
- ep0-6 监控数据：PSNR 22.05→23.03→23.48→23.76→23.99→24.17→24.27 dB
- ep10 Gate（<27 dB）外推 ~24.4 dB，主动在 ep6 停训（节省 ~1.5h GPU）
- A+B 修复应用：
  - A: `val_severity: medium`（去掉 heavy 拉低均值，测真实 moderate 能力）
  - B: `lambda_lpips: 0.05`（L1 + LPIPS 加速感知收敛）
  - 续训：从 ep6 checkpoint 续，PID 25804 已运行

### 关键发现
- 每 epoch ~23min，200 epoch 全程 ETA ~78h（比预期 30-40h 长，因数据集 69k 对 × severity=mixed）
- ep6 增量急降（+0.18→+0.10），确认 Gate 会触发
- v0 基线（1.7M, 30ep）= 25.55 dB；本次 15.3M 在 ep6 = 24.27（mixed val，正常，bigger model 收敛慢）
- ep7 续训后 val PSNR 应显著跳升（medium subset 比 mixed 容易）

### 待续（M1 W1）
- [ ] ep10 续训 Decision Gate 重评（预计 2026-05-25 早，medium val PSNR 目标 ≥27）
- [ ] Theorem 2 (agent risk bound) 数学推导（与训练并行）
- [ ] 若 ep10 通过 → 继续全程训练至收敛

### 命中率回退
- 本会话无论文内容改动，命中率预估维持 **32.5%**（ep6 停训不影响 lever 进度）

---

## 2026-05-24（会话 1，大项目启动）

### 完成
- BMVC 目录封印：`meeting/BMVC/SUBMITTED.md` + README 顶部加 🔒 SEALED 标记
- 旧顶层文档归档：`archive/2026-05_pre_iclr_reorg/{PROJECT_OVERVIEW.md, VisiSkin-Agent指导手册.md, 创新点/}`
- 5 个主文档全套创建（对标 BMVC/README 风格）：
  - `README.md` — 入口（128 行）+ 4 文件读档顺序
  - `STORY_FRAMEWORK.md` — 故事框架，10 跑偏定义 + §1-§9 章节锁定 + 锁定数字表 + R1-R10 防御
  - `ACCEPTANCE_CRITERIA.md` — 25 lever 验收 + E1-E12 阈值 + 红线 + M1-M4 milestone
  - `DATA_INVENTORY.md` — checkpoint + 数据集 + 30+ csv + 脚本 + W1-W16 待跑
  - `PROJECT_LOG.md` — 本文件（首版）
- `CODEBASE_README.md` — 原 README.md 改名（代码库 reproduce 说明保留）
- `meeting/ICLR2027/` 空骨架已建

### 关键决策（已与用户对齐）
1. **大项目目标**：ICLR 2027 完整 5 模块系统（2026-09-22 abstract / 09-29 full deadline）
2. **VisiEnhance 路线**：方案 A — 换大 config（base_channels=64, mid_blocks=8, ~15M 参数, 30-40h）重训
3. **目标命中率**：78-80%（25 lever stack）
4. **文档结构**：全套对标 BMVC（5 文件）

### 命中率预估
- 基线（ICLR 平均接受率）：30%
- 已完成 lever（L1/L6/L11）：+2.5%
- 当前预估：**32.5%**
- 目标 M4：78-80%

### 追加完成（同会话晚段）
- 4 Claude Code hooks 部署到 `D:/YJ-Agent/.claude/hooks/`：
  - `iclr_session_start.sh` — cwd 含 YJ-Agent 时输出 4 文件读档顺序
  - `iclr_prompt_submit.sh` — keyword 触发（论文/训练/BMVC/扩散）+ Opus-in-ICLR caveman 自动 off
  - `iclr_pre_edit.sh` — Edit/Write BMVC 非 rebuttal 路径 → block exit 2
  - `iclr_post_edit.sh` — Edit/Write ICLR2027 tex / 主指导 md 命中 R1/R2/R4/R8 → stderr exit 2
- `D:/YJ-Agent/.claude/settings.json` 注册 4 hooks（SessionStart / UserPromptSubmit / PreToolUse / PostToolUse）
- 实测 10 个测试场景全通过
- Token overhead 估算 ~10-20 / turn（摊薄）

### 待续（M1 W1，2026-05-25 ~ 06-01）
- [ ] VisiEnhance Plan A 大 config 文件起草（`configs/visienhance_s1_planA.yaml`）
- [ ] 启动 Stage 1 重训（~30-40h，需先空出 GPU）
- [ ] Theorem 2 (agent risk bound) 数学推导启动
- [ ] **Phase A 自动化脚本**（pending）：
  - `scripts/iclr_grep_redlines.sh` (CLI 版红线扫描)
  - `scripts/check_numbers_consistency.py` 扩展 17 → 30 数字
  - `tests/test_theorems_numerical.py` (Prop 3 / Lemma 3 / Thm 2 toy 验证)
- [ ] **Phase C 多 agent slash commands**（pending）：
  - `/iclr-plan` Opus 无 caveman
  - `/iclr-execute` Sonnet subagent
  - `/iclr-check` Haiku subagent

---

## 历史会话（BMVC 阶段，已封印）

> ⚠️ BMVC 阶段的会话历史保留在 `D:/YJ-Agent/WORKLOG.md` 旧版本 + `meeting/BMVC/BMVC_LOG.md` + `meeting/BMVC/SUBMITTED.md`，不在本文件复述。

**BMVC 关键里程碑**（速查）：
- 2026-05-21 第六次会话：BMVC 主文 18→10 页（hard limit）+ 3 reviewer 全应答 + A1 forward ablation 硬实证 → 投稿就绪
- 2026-05-29：BMVC P2 deadline 投稿
