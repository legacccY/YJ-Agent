# 工作日志（快速指针）

**最后更新**：2026-06-07 ICLR 会话 19（盯 v5 job 1440985〔RUNNING **ep40/80**，ETA~7h；**val_PSNR 30.17 守 E1**、**val_DP 0.293→0.198(−32%) feature-DP 真起效**、但已趋平 + hinge 仍泛化不动〕→ 测 dflip 受阻：**dangerous_flip 不在训练指标，须跑 `eval_diag_paired.py`**；**本地 4070 跑 eval 三连崩 CUDA illegal-access**〔崩点乱跳/batch4 也崩/非 OOM = 硬件层不稳，软改无解，会话18 结论再验证〕+ HPC 4 卡配额被训练占满 → **CPU(`CUDA_VISIBLE_DEVICES=-1`) 唯一即时稳路** ~30-50min，收工时未出结果。改动：eval_diag_paired batch16→4、diag_dflip_v4 加 FORCE_CPU、eval_stage2_compare CKPTS 指 v5。**欠债**：framing 回写仍顺延）| **完整进度**：见 `D:/YJ-Agent/project/PROJECT_LOG.md`（ICLR 主线，会话 19 详 entry）+ `project/meeting/Med-NCA/PROJECT_LOG.md`（Med-NCA）

> 🔵 **会话 20 接续从这开始**：① **出 ep37 dflip 预览**（本地已 sync v5 ep37 best ckpt）：`cd project && CUDA_VISIBLE_DEVICES=-1 python eval_diag_paired.py > eval_v5_cpu.log 2>&1`（CPU ~30-50min；**本地 4070 GPU 别试，跑这前向必崩 illegal-access**；想看进度加 tqdm+`python -u`）→ 看 dangerous_flip vs v4 的 0.176。② **最终定论**：盯 job 1440985 训完（ep80，~7h）→ HPC sync 最终 best → **HPC GPU 跑 eval**（卡空、3min）出最终 dflip + E3/E7。③ **framing 回写**（会话17/18/19 一直顺延）：E3 降级 motivation、主推 E7+dflip、回写 STORY §4 + Claim2/3 + ACCEPTANCE E3/E7。④ fig_dflip 接进 paper + `/validate-figures`。

> 🆕 **新独立子项目 Med-NCA**（顶会复现→创新，与 ICLR 主线并行）：计划 `project/meeting/Med-NCA/REPRO_PLAN.md`、日志 `.../PROJECT_LOG.md`。**会话 7（06-04）：揪出 R2 发散真因 = 我方 `FastBackboneNCA` 提速 subclass 改了 RNG 流（非官方配置错）—— 上网溯源官方配置一字不差 + diff 源码相同 + 忠实 smoke（官方 BackboneNCA）loss 健康降 Dice@5ep=0.33 坐实。🔴 作者立永久红线 §1#8「复现完全按官方零偏离」（禁加裁剪/降lr/换实现/提速 subclass）。旧 R1 0.8661（fast版）+ 早期加裁剪方案均作废。** **会话 8（06-05）：R1 官方版 PASS（0.8644 三源一致）+ R2 官方版 0.672 FAIL 非崩溃 + 全套行为档案官方重算 + 6 页 6 图 LaTeX 复现报告。** **会话 9（06-05）：核实 R2 配置 11/12 项一字不差官方、唯一缺口=epoch（301 vs 1000）；诊断收敛趋势=未饱和（loss ep125→300 0.37→0.27 没平 + 验证 Dice ep275 冲 0.795 贴 UNet 基线）→ 延 1000ep 重训提交 HPC job 1436075（RUNNING，~10h），监控 `hpc_mednca_gui.py 1436075`。** 下一步：盯 1436075 ep1000 eval vs 0.838 看 gap 缩多少 → R2 是否翻 PASS。

> 🔵 **会话 17 接续要点（下一步从这开始）**：v4 Stage2 已评完并取消（job 1434527 取消让 mednca 上）。**E7 PASS**（DP vs no-DP：ΔAUC +0.0299 显著、ΔKL −0.29 显著、McNemar p=4e-59）；**E3 仍卡**（dAUC −0.020 borderline、一致率 0.945、**dangerous_flip 0.176 三版 hinge 都没压下**）。**🔴 dflip 根因（`diag_dflip_v4.py`）：13 个翻转里 85% 是 enhance 主动把阳翻阴（非退化），且非 borderline（含 pr=1.0），enhance 平均把 mel 置信度 0.92→0.81 → 系统性「美化」黑色素瘤、红线 R8 实证。**
>
> **下一步（会话 18）**：
> ① **优先出 dflip figure**（零训练、最有冲击力）：mel 置信度 ref→deg→enh 下滑曲线 + 11 例 enhance-caused flip 病灶磨平对比图。
> ② **framing 转向**：E3 降级为 motivation 证据，主推 E7 + dflip 实证 → 坐实 Claim 3 / Theorem 2（query-for-retake）。回写 STORY_FRAMEWORK §4 + ACCEPTANCE E3/E7。
> ③ loss 真要救 dflip：弃加 hinge λ，转 **mask 加权 L1（病灶区不准磨平）** 或 **feature-level DP（B3 中间特征对齐）**。
>
> **本地已存**：v4 best ckpt `project/checkpoints/visienhance/stage2_planA_256_v4/best_visienhance.pth`（ep46 PSNR-best）；eval 结果 `project/results/stage2_diag_paired.csv`（dAUC/KL/McNemar）；诊断脚本 `project/diag_dflip_v4.py`。
>
> ⚠️ **教训重申**：HPC 迭代必须每轮记日志 + commit config，会话 16 的 v3/v4 又没记、靠产物还原（第二次踩同一坑）。

---

## 🎯 当前焦点

**ICLR 2027 大项目启动**（Deadline 2026-09-22，**121 天**）
- 目标命中率：**78-80%**（25 lever stack）
- 当前 M1 W1：VisiEnhance Plan A 重训准备 + Theorem 2 推导

**BMVC**：✅ 已封印（2026-05-24），不再修改 — 详见 `project/meeting/BMVC/SUBMITTED.md`

---

## 📋 主指导文档（按读档顺序）

| 优先级 | 文件 | 用途 |
|---|---|---|
| 🥇 入口 | `project/README.md` | ICLR 2027 项目入口 + 4 文件读档顺序 |
| 🥈 反跑偏 | `project/STORY_FRAMEWORK.md` | 10 跑偏定义 + §1-§9 锁定 + 锁定数字 + R1-R10 |
| 🥉 验收 | `project/ACCEPTANCE_CRITERIA.md` | 25 lever + E1-E12 + 红线 + M1-M4 milestone |
| 数据 | `project/DATA_INVENTORY.md` | checkpoint + 数据集 + 30+ csv + 脚本 + W1-W16 |
| 日志 | `project/PROJECT_LOG.md` | 时间倒序，每次会话进度 |

---

## 🔥 会话 10 定论（2026-05-31）：PSNR 口径统一 + light/heavy nocrop 生成 + Stage 2 停训

- **PSNR 口径专节**已补入 `ACCEPTANCE_CRITERIA.md`（per-image mean = 论文标准；batch-aggregate = 训练监控，差 ~4 dB）
- **regen_nocrop.py** 修复 merge 逻辑（不覆盖已有 CSV），生成 light + heavy 各 49700 张，`quality_labels_nocrop.csv` 共 149100 行 ✅
- **eval_visienhance.py** 加 `--labels-csv` override，E1 现可正确指向 nocrop CSV
- **Stage 2 (DP-Loss)** 启动并跑至 ep5：loss 持续下降（0.0181→0.0129），但 val_PSNR 从 ep1 峰值 29.844 持续下滑至 29.6 ← 用户决策停训
- **下次待确认**：Stage 2 PSNR 下滑原因（λ_DP 过大？lr 过高？）→ 调参后重跑，或直接跳 Stage 3

## 🔥 会话 9 定论（2026-05-30）：VisiEnhance Stage 1 nocrop 收敛，E1 实际达标（PSNR 定义澄清）

- **续训** PID 22296 (12:16 起 ~8h) ep17→56：ep44 起聚合 PSNR 28.97 平台锁死 12 epoch，已 kill。
- **🔑 PSNR 定义澄清**（val n=3312 对照，两种都复现）：
  - 聚合 MSE（训练日志用）：input 16.44 → enh **28.92**（复现训练 28.97）
  - 每图均值（论文标准报法）：input 21.95 → enh **32.50** → **E1≥30 PASS**；test split 32.74
  - 非 bug 非挑数字，是 PSNR log 非线性；input baseline 同规律佐证。
- **E1 结论**：PSNR **32.5**(每图)PASS / SSIM **0.946** PASS。**无须 Plan B。**
- **视觉**：`project/demo_nocrop_ep51.png`（degraded/enhanced/ref ×6）清晰无伪影，守 R8。
- 脚本新增：`scripts/eval_nocrop_e1.py`(双 PSNR 定义) + `scripts/make_visienhance_demo.py`。json：`results/visienhance_nocrop_e1.json`+`_val.json`。
- **会话 10 待办**：统一全项目 PSNR 口径 → 全量 light/heavy 重生成 → Stage 2/3 → 回写 STORY/ACCEPTANCE/paper。

## 🔥 会话 8 发现（2026-05-29）：PSNR≥30 卡死真因 = 退化管线随机裁剪 bug

- **诊断**：Plan A 15M 模型 ep42 卡 25.5，与 1.7M v0 **完全相同** → 容量证伪
- **三层诊断脚本**（`project/scripts/diag_*.py`）：
  - oracle 仿射上界仅 26.43 dB（旧裁剪数据），模型已达 96% → 不是模型问题
  - 退化分解：光度可逆到 50 dB / 模糊单独 38 dB，但组合后崩到 26
  - **元凶 = `degrade.py` 的 `apply_random_crop`（ratio 0.75-0.89, prob 0.5）**：裁剪+缩放使降质图与原图**像素错位**，强迫模型 hallucinate 被裁组织（违反红线 R8），任何容量都崩
- **修复**：crop 不属增强任务，归 Theorem 2 的 **query-for-retake 通道**
  - `degrade.py` 加 `crop_prob` 参数（可关裁剪）
  - 无裁剪重生成 medium（49700 张）→ `data/paired_dataset_nocrop/` + `quality_labels_nocrop.csv`
  - 重生成后 oracle 上界 **26.43 → 37.49 dB**（+11 dB）
- **验证训练**（`configs/visienhance_s1_planA_nocrop.yaml`，fresh init）：val_PSNR 16.47(baseline)→ ep16 **28.0**（旧死点 25.5，已甩开 +2.5 dB 且续升），**裁剪假设确认无疑**
  - checkpoint：`checkpoints/visienhance/stage1_planA_nocrop/best_visienhance.pth`（best 28.008 @ep15）
  - ep16 主动收工停训（未跑完 60ep）

## ⏭️ 下次接续（会话 9）

1. **续训 nocrop 到收敛**（resume `stage1_planA_nocrop/last`），观察是否过 30；若卡 ~28 → 加 MSE loss 项 / 提 lr / LPIPS→0
2. 达标后**全量重生成 light + heavy**（`regen_nocrop.py --levels light heavy`）
3. 完整 Stage 1→2(DP-loss)→3(hinge) + E1-E12
4. **回写文档**：STORY_FRAMEWORK §4 + ACCEPTANCE E1 + plan_07，把 crop→query-channel 写成设计决策（强化 Claim 3 / Theorem 2）

## 🚀 下一步（M1 W1-W2，2026-05-27 ~ 06-08）

会话 7（2026-05-27）完成（纯写作零实验，详见 PROJECT_LOG）：
- [x] **Appendix A1 LaTeX 化**（Q-VIB Prop1/Lemma1/Lemma2/Thm1/Prop2 full proofs）→ 5-theorem closure LaTeX 全齐 ✅
- [x] **主文 Abstract→§9 正文填充** + Ethics/Reproducibility statement（§7 result 留 TODO 占位）✅
- [x] **Appendix A0/A4/A18/A19/A20/A21/A23/A26 LaTeX 化** + references.bib(19 ref) + citation 接线 ✅
- [x] DATA_INVENTORY ITB 计数纠错（Edge660/Diverse1500）✅
- [x] paper **33 页**，bibtex 全 defined，零 undefined，零 banned 字样 ✅
- [x] **BMVC 匿名 repo 主页重写** `release/README.md`（标题对齐投稿 itb_paper.tex + headline 置顶 + 硬件纠错）✅
- [x] **release 匿名审计修复**：P1 致命去匿名（GITHUB_SETUP/造史脚本含身份词 → .gitignore 排除 + 自删）+ P2/P3/P4 一致性（DATASET_CARD 标题/区间、data/README 死链）✅

待续（全部 gated on 实验，写作侧已到边界）：
- [ ] **续训待启动**（从 ep 15 续，`stage1_planA/last_visienhance.pth`，`/loop /run-experiment`）
- [ ] §7 result tables + A5/A16/A17/A22/A24 → **必须 Plan A 重训 + re-eval 后才有 frozen 数字**
- [ ] **Plan A re-eval 后必办**：重导 n=19878 per-sample csv + 决定 cross-domain 锁定值(−0.108→−0.164/−0.150→−0.236)

详细 task 清单见 `project/plans/phase_07_visienhance_planA_active.md`

---

## 🔬 关键数字速查（ICLR 2027）

| 模块 | 状态 | 核心数字 |
|---|---|---|
| VisiScore-Net | ✅ done | PLCC 0.924 / SRCC 0.895 |
| Q-VIB Full | ✅ done | AUC 0.707, ECE 0.098, ρ=−0.165 (p<10⁻²⁴) |
| 5 backbone universality | ✅ done | section54_summary.csv |
| VisiEnhance Stage 1 v0 | ❌ 裁剪 bug | PSNR 25.55 dB（误判容量，实为裁剪致像素错位）|
| **VisiEnhance Plan A** | ⏳ M1-M2 | PSNR ≥ 30, \|ΔAUC\|<1.5%, SalvageRate>55% |
| 5-theorem closure | ✅ 5/5 推导 done (实证待 Plan A) | Prop 1-3 + Lemma 1-3 + Thm 1-2 + Cor 1 全 publication-grade，详 `project/plans/{Theorem2,Prop3_Lemma3,Corollary1}*.md` |

---

## ⚠️ 永久红线（CLAUDE.md 复用）

1. Reader Study 数据**不可伪造** — 用 DCA + Triage simulation + 已发表 dermatologist baseline + LLM-judge protocol (§A23 disclaimer) 替代
2. **所有材料只能从网上公开资源获取** — 不联系诊所、不采集线下样本、不依赖人际网络
3. **不用扩散生成模型做皮肤镜增强**（伪影发明病灶，临床红线）
4. **数字凭印象写禁止** — 每个数字必须 csv 核算 + bootstrap 95% CI + run_id
5. **BMVC 数字不可直接搬入 ICLR**（必须重跑或 cite-as-paper）
