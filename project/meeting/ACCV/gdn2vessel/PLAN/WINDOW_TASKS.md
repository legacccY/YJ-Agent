# gdn2vessel 多窗任务 + 完成线（DoD）

> 真源 = Conductor 图 `.portfolio/pipelines/gdn2vessel.json`（看 `python tools/pipeline.py status gdn2vessel`）。
> 本文件 = 每个节点的**硬完成线**：到线就 `done`，**不被往前推到下个棒**。
> 承 `PROJECT_LOG.md` Entry 14 待续 4 条。本轮 = 修命门设计 → 重投正式命门（92 GPU·h，拍板点）。

## 共同红线（所有窗）
- 只碰本棒 territory 的文件，不串别棒。
- 四红线：数字 Bash/Grep 核 csv 不信 Read · 超参/架构查官方源查不到标 TODO · 复现零偏离 · 评估集不泄漏。
- 到拍板点 / 做完就**停**，不自动往下个棒冲。
- 各窗 `done` 后全汇 `integrate`（主窗跑真 e2e 烟测）= 放行 92 GPU·h 训练前的总闸。
- 计划外岔路先问用户，不盲跑（项目铁律）。

---

## 节点 scout-baseline（C 窗 · researcher）
**服务**：P3 baseline 全谱 / L3 lever。
**territory**：`reference/` + `PLAN/BASELINE_SPEC.md §5` 状态表。
**完成线（5 TODO 各有结论，查到=带官方源链 / 查不到=显式标 TODO）**：
- [ ] creatis LICENSE：CeCILL 确认 or 不可用
- [ ] cbDice/SkelRecall 官方混合权重（nnUNet 1:1:1?）
- [ ] DSCNet TCLoss（DRIVE 官方只 BCE?）
- [ ] normalize + augment 各 baseline 官方默认
- [ ] MambaVesselNet 2D 可行 or 降档 C
**停**：5 行状态表填满即 `done`。不顺手改 baseline 代码。

---

## 节点 design（A 窗 · planner → skeptic 复核）
**服务**：命门 = Claim2 re-ID 可归因 / L1 lever。
**territory**：设计稿（出草案，**不改** `ACCEPTANCE_CRITERIA.md` 本体——那是 gate-accept 拍板点）。读 Entry 14 待续1 + ACCEPTANCE P4 判据2(L61-72) + PHASE_4 第8项。
**完成线**：
- [ ] planner 出修订设计：A1' 等参臂定义清楚（QKV+门+LN 同 A2，换普通线性 attn 替 delta-rule）→ 三臂 A2>A1'>A0' 才干净归因「关联记忆机制」
- [ ] 统计方案改：中介直接效应分解 or ε_β0 配平分层，**删 over-control 措辞**
- [ ] 写出新 ACCEPTANCE P4 判据2 **草案**（partial_corr 作废 → 双判据）
- [ ] skeptic 复核 = **0 致命🔴**（有🔴 回 planner 修，不算完）
**停**：0🔴 后停在 `gate-accept` 拍板点。**A 窗不准改 ACCEPTANCE 文件**——出草案就 `done`，改阈值由主窗报用户拍板。

---

## 节点 impl-verdict（B 窗 · coder）⚠️ 2026-06-20 design 定案后范围更新
**服务**：命门统计工具，须**严格对齐新 ACCEPTANCE P4 判据2**（design 已把 LMM→ε_β0 配平分层 CDE）。
**territory**：`src/reid_verdict_v2.py` + `tests/`。读 `ACCEPTANCE_CRITERIA.md` P4 判据1-3 全文照实现。
**完成线（按新判据2 重写 verdict，非旧 4 项小补）**：
- [ ] **作废旧 partial_corr + 旧 LMM**（reid_verdict_v2.py:131 旧 LMM 删/弃用，pilot 已证塌 p=0.486）
- [ ] **主判据(1a/1b)**：三臂 A2>A1'>A0' 每集内 per-image 配对**精确排列检验**（n≥6 枚举 2^n 单侧 p<.05；**n<6 小集特例**=方向为正+最小可达 p）+ 配对 Wilcoxon 同号；跨集一致性 ≥3/4 集
- [ ] **判据2 = ε_β0 配平分层 CDE**：每集筛 `|ε_β0(A2)−ε_β0(A1')|` 落该集 IQR 内的图子集，子集内重做配对排列 p<.10 单侧
- [ ] **辅助 TE/NDE/NIE 三件套**（手算 OLS，cluster bootstrap by image_id，仅描述不设门）
- [ ] 多集路径聚合 + image_id 加数据集前缀（防撞）
- [ ] 本地真 e2e 烟测（非 mock，造 3 臂×多集假数据）跑通 + pytest 绿
**红线**：禁 scipy.stats（OMP），排列/Wilcoxon/bootstrap/OLS 全手算（numpy+itertools）。**禁跑完调阈值（HARKing）**。
**停**：上述全过即 `done`。不碰 src 其他文件、不跑 HPC、不改 ACCEPTANCE。

---

## 节点 impl-drive（D 窗 · coder）
**服务**：DRIVE benchmark / Entry 14 待续4。
**territory**：`src/datasets/drive.py`。
**完成线**：
- [ ] drive.py 用 base_vessel canonical API（签名对齐 chase/fives/stare 已落地）
- [ ] 本地 load 1 图烟测通 + pytest 绿
- held-out 划分：**停在拍板点**，不自己定（DRIVE test 无 GT，须用户拍）
**停**：迁移 + 烟测过即 `done`。held-out 报主窗拍板，不擅自划分。

---

## 节点 creatis-repro（F 窗 · coder）2026-06-20 拍板生
**服务**：Claim1「in-model vs post-processing 续连」唯一正面对照 / L6 lever。承 creatis 自复现裁定。
**territory**：`creatis_postproc` adapter 代码 + `tests/`。**不碰** BASELINE_SPEC（baseline-fix 窗占着）/reid_verdict_v2/drive。
**完成线**：
- [ ] 按 arXiv 2404.10506 §3.1 真实现 plug-and-play reco 续连后处理（现 adapter 仅占位）→ 挂统一 backbone 输出后的两段式
- [ ] 复现零偏离：协议/超参只用 §3.1 官方，查不到标 TODO 不臆想
- [ ] pytest 绿 + 本地烟测（造小输入跑后处理不崩）
**停**：实现+烟测过即 `done`。BASELINE_SPEC §5 状态行**不自己改**（交主窗合并，避撞 baseline-fix）。

## 节点 baselineB-pick（G 窗 · researcher）2026-06-20 拍板生
**服务**：保 ≥12 baseline 超量 / L3 lever。承 MambaVessel++ 降档C 补位裁定。
**territory**：`reference/`。**不碰** BASELINE_SPEC（baseline-fix 窗占着）。
**完成线**：
- [ ] 从档B（SA-UNetv2/MM-UNet/TFFM）查官方 repo，定哪个**有 2D 实现的 SSM/血管 baseline** 能真跑顶替 MambaVessel++
- [ ] 确认：2D 代码存在可跑 + license + DRIVE/视网膜超参（查不到标 TODO）
- [ ] 结论写 `reference/` 一个新档或追现有调研档（不碰 BASELINE_SPEC）
**停**：定出补位 baseline + 核源即 `done`。roster 改交主窗合并进 BASELINE_SPEC。

## 节点 sweep-launcher（H 窗 · coder）2026-06-20 加，train 关键路径
**服务**：正式命门启动器 / L1 lever。train 拍板点等它。
**territory**：`scripts/`（批量提交脚本 + sbatch 模板）。**不碰** model/reid_verdict/adapters。
**完成线**：
- [ ] 写命门批量提交脚本：4 集(CHASE/STARE/HRF/FIVES)×3 臂(memory/linear_attn/cnn)×3 seed = 36 组合，各自独立 output_dir
- [ ] 支持 **batch-1 模式**（3 臂×4 集×1 seed = 12 run 先验）
- [ ] 末尾自动调 reid_verdict_v2 聚合三臂 CSV 出 verdict
- [ ] HPC checklist：sbatch 模板含 `mkdir -p logs/`、提交前去 CRLF、看产出文件不信 jobid（[[feedback_hpc_submit_checklist]]）
- [ ] 本地 dry-run（不真提交，打印 36 条命令确认参数对）
**停**：脚本写完 + dry-run 验过即 `done`。**不真提交 HPC**（主线串行 + 拍板点）。

## 节点 impl-mmunet（I 窗 · coder）2026-06-20 加，P3 baseline 补位
**服务**：保 ≥12 baseline / L3 lever。承 baselineB-pick 选定 MM-UNet。
**territory**：`mm_unet` adapter + `third_party/`。**不碰** BASELINE_SPEC 主表（交主窗合并）/其他 adapter。
**完成线**：
- [ ] vendor MM-UNet（github.com/liujiawen-jpg/MM-UNet，MIT，commit 2026-03-09）+ 写 adapter 顶替降档的 MambaVessel++
- [ ] 复现零偏离：超参用官方 `config.yml`（DRIVE/STARE），查不到标 TODO（见 BASELINE_B_PICK §跑前TODO）
- [ ] pytest 绿 + 本地 build 烟测（mamba 依赖缺时 RuntimeError 占位，对齐其他 SSM adapter）
**停**：vendor+adapter+烟测过即 `done`。

## 拍板点（主窗持，各窗碰到就停下报）
1. **gate-accept**：改 ACCEPTANCE P4 判据2（阈值变更）。✅ 2026-06-20 用户放行（partial_corr→CDE 分层 + A1' 臂）。
2. **train**：投正式命门 92 GPU·h（4 集×3 臂×3 seed）+ HPC 上传新代码。⬜ 待 impl-verdict+integrate 过。
3. **DRIVE held-out**：✅ 2026-06-20 裁定 = **DRIVE 不做断点 benchmark，走 CHASE**（8 张官方 held-out test GT）。DRIVE 只标准分割对照（train16/val4），不进断点轴。drive.py TEST_IDS TODO 据此关。

## P3 baseline 拍板裁定（2026-06-20，winC scout-baseline 翻出 → 用户裁）
- **creatis 无 LICENSE**：✅ 裁定 = **自己复现协议**（按 arXiv 2404.10506 §3.1 plug-and-play reco 实现，挂统一 backbone 输出后）。→ 下一轮新任务：coder 据 §3.1 真实现 `creatis_postproc` adapter（现仅占位），复现零偏离。法律上自实现绕开 vendor license 问题。
- **MambaVesselNet++ 只 3D**：✅ 裁定 = **降档 C + 档B 补位**。MambaVessel++ 降档 C（只引文献数字 DRIVE 0.711，标 2D code-unavailable）；从档B（SA-UNetv2/MM-UNet/TFFM）提 1 个有 2D 实现的 SSM/血管 baseline 补位，保 ≥12 全谱。→ 下一轮新任务：researcher 定哪个档B 顶替 + coder 加 adapter。

> 这俩裁定产生**下一轮 2 个新任务**（creatis 自复现 adapter + 档B 补位 baseline），本轮 impl-verdict/baseline-fix 跑完后排。
