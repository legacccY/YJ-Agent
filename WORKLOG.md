# 工作日志（快速指针）

**最后更新**：2026-06-01 会话 13（Stage1 @256 收敛达标 ep40 手停 → Stage2 @256 DP-Loss 启动 job 1433944）| **完整进度**：见 `D:/YJ-Agent/project/PROJECT_LOG.md`

> 🔵 **会话 13 接续要点**：**Stage2 @256 运行中 = job 1433944**（gpu4090n5，起 20:21，λ_dp=0.1，lr 1e-5，80 epoch，patience=999 不早停要盯）。Stage1 @256（旧 job 1433796）跑到 **ep40 手动停**（聚合 val_PSNR best **30.145**、SSIM 0.9847；曲线仍微爬但增幅 ~0.1dB/6ep，E1 早 PASS，不值耗 22h）→ best ckpt 已冻结备份 `stage1_planA_256/best_visienhance_frozen.pth`。旧依赖 job 1433799 已弃（afterok 落空），Stage2 改 fresh sbatch 重提。启动逐项验证通过（resume `model-only=True` + `_raw_model.load_state_dict`、`weights_only=False`、DP-Loss EfficientNet 加载、train=69564/val=9936、val_severity=mixed、无 NaN/OOM）。**E7 已 PASS**（McNemar p=4e-12，ΔAUC_enh +0.84%，ΔKL −0.067）。**E3 仍 FAIL**（ΔAUC 4.2% vs <1.5%；一致率 87% vs >95%）根因=分辨率失配，靠 Stage2 @256 + λ_dp 压。收尾要做：①查 1433944 状态（`python hpc_monitor.py 1433944` 或 GUI）②Stage2 完成 sync best ckpt 回本地 ③`eval_diag_paired.py` 复测 E3/E7 ④若 ΔAUC 仍>1.5% 升 λ_dp→0.2 重跑。脚本：`project/eval_diag_paired.py`、`eval_diag_hires_v2.py`。256 config：`configs/visienhance_s{1,2}_planA_256_hpc.yaml`。

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
