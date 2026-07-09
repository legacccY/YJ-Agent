# 新切 9mer 下游分析 — F1 判据冻结档（去偏向）

> **本档在任何新切结果产出之前冻结**（2026-07-09）。目的：把老师 §8 前 4 问的判定规则「先定死、后跑」，防止跑完再挑口径 / 把结果读成"符合预期"。跑后只允许**照此规则填结论**，不允许改规则。对应审批计划 `~/.claude/plans/quantimmu-...-staged-glacier.md` 的 §F1。
>
> 数据真源：新切 9mer canonical `data/frozen/pooled_clean_rerun_9mer.csv`（102 突变 × 9 病人；`--min_pep 8` → 纳入 **8 病人**，剔病人 102[n=6]；29 工具，NeoaPred 缺席据实标注）。
> 旧切基线（130 肽，仅作**趋势对照**，不逐值比——肽集/病人数不同）已 Bash 核实，见各条括注。

## 冻结口径（F0）
- 主分析 = 新切 9mer + `--min_pep 8`（8 病人）+ **裸 ρ̄ 作 headline** + `lenctrl`（ctrl=peplen）作 robustness 列同报。
- `--min_pep 3`（9 病人）仅作**敏感性附录**，不作主结论。
- 工具数 = 29（NeoaPred 新切缺席，报告脚注声明原因，不补不换维度集）。
- 每条结论**必挂**：点估 + 95%CI + 配对 p + n_used/n_folds + **n=8 功效 caveat**。

---

## 判据表（跑前冻结）

### ① 多工具 fusion 相对最强单工具的净优势 —— 老师「结果在哪里？」
- **量**：Δ = cv_integration − cv_single（nested-LOPO 诚实估计）；辅以成员选择膨胀 inflation = oracle − cv。
- **判据**：
  - 若 Δ 的 95%（cluster-bootstrap）CI **含 0** 或配对 p ≥ 0.05 → 判「**无可检测净优势**（证实旧断言）」。
  - 若 CI 全 > 0 且 Δ > 0 且 p < 0.05 → 判「**检出净优势**（推翻旧断言）」→ 升级拍板点，回报用户 + 袁老师。
  - 若 Δ 显著 < 0 → 判「融合反而更差」，据实报（多半是剔 DTU 后最强单工具被削）。
- **两 DTU 口径都填**：`fullcov`（含 DTU）与 `fullcov_no_dtu`（剔 DTU）——旧切两版方向不一，必须都报，不挑。
- **旧切趋势对照（130，9 病人，已核）**：fullcov/raw Δ=−0.094 p=0.117；fullcov/lenctrl Δ=+0.037 p=0.547；fullcov_no_dtu/raw Δ=−0.157 p=0.031；fullcov_no_dtu/lenctrl Δ=−0.187 p=0.016。四版**均「无可检测净优势」**，fullcov 版 CI 跨 0、剔 DTU 版显著为负。
- **caveat（必写）**：n=8 病人配对功效极低，"无净优势"很可能是**功效不足**而非真无效——不得读成"证明 fusion 无用"。

### ②a robustness 上 geomean 是否"唯一最优" —— 老师「结果在哪里？」
- **量**：R6 summary 里 geomean 的 `rank`（各 drop 内按 mean_rho）+ `win_rate_top1`（30 seed 夺魁比例）+ 与次优法的 mean_rho 差 vs `std_rho`。
- **判据**：geomean 在 drop=0.1 **且** 0.2 均 `rank==1` **且** 与次优差 > std_rho → 判「**复现** geomean 唯一最优」；否则「**未复现**」（并列 / 被超）。
- **旧切趋势对照（130，已核）**：geomean drop0.1 rank1 mean_rho=0.409 win_rate=0.567；drop0.2 rank1 0.435 win_rate=0.60。旧切里 geomean 确 rank1，但"唯一性"看次优法差距。

### ②b 免疫原类工具取 max 是否最优 —— 老师「结果在哪里？」
- **量**：R2_best_per_tool 里免疫原类工具子集（PRIME/DeepImmuno/Repitope/IEDB_Calis/ImmuneApp/MHCnuggets 等免疫原性专用工具，非结合/呈递类）逐工具 `max_rho_lenctrl` vs `best_lenctrl_rho`。
- **判据**：若 ≥ ⌈免疫原工具数 / 2⌉ 个工具 `max == 最优变体` → 判「**复现** max 最优」；否则「**未复现**」。
- **NeoaPred 缺席**：若它曾是该 headline 关键例证，须**显式声明该证据点新切不可得**，不假装完整。

### ③ robustness 上 median vs geomean —— 老师「结果在哪里？」（⚠️§8③ 存疑）
- **量**：R6 里 median 与 geomean 两法的 mean_rho（drop 0.1 & 0.2）；**跨 30 seed 配对**（同 seed 子采样）符号检验 / Wilcoxon p；Δ = median_mean_rho − geomean_mean_rho。
- **判据**：
  - p < 0.05 且 Δ > 0 → 「**median 优**（证实 §8③）」。
  - p < 0.05 且 Δ < 0 → 「**geomean 优**（推翻 §8③）」。
  - p ≥ 0.05 → 「**差异不可检测**」。
- **⚠️ 关键诚实点**：§8③ 转述「median 略优于 geomean」**与旧切 R6 实测方向相反**（旧切 R6：geomean rank1 0.409 **>** median rank7 0.352，drop0.1/0.2 皆然，已 Bash 核）。→ 说明 §8③ 数字**并非出自现 R6**，来源存疑。**新切一律以现 R6 实测为准据实报**，并在报告点明「§8③ 转述与 R6 不符、新切以 R6 为准」；writer 回溯 §8③ 出处。**禁止为凑"median 略优"而换口径/挑脚本。**

### ④ 单工具 max vs top-k 均值 —— 老师「结果在哪里？」
- **量**：R2_pooling_sweep（29 工具 × 51 变体）+ R2_best_per_tool。对**有信号工具**（`max_rho_lenctrl` 的 bootstrap CI 下界 > 0 者），统计"最优变体是 topk 而非 max"的工具数/比例、及提升是否超各自 CI。
- **判据**：若 > 50% 有信号工具最优变体为 topk 且提升超各自 CI → 判「**复现** max 非最优」；否则「**未复现**」。
- **必标**：`best_lenctrl` 是 **in-sample 乐观上界**（天然 ≥ max），非 held-out 增益——报告须写明，避免夸大。

---

## 措辞黑名单（F2，报告禁用）
「如期 / 与预期一致 / 不出所料 / 正如框架所料 / 果然 / 符合预期」。

## 复核分工（F3，二者独立）
- **verifier**：只核数字——独立重算 Δ/CI/rank/win_rate/median−geomean 配对差/topk-优于-max 比例，比对 CSV 原值，**不看结论文字**。
- **skeptic/reviewer**：只审措辞——扫黑名单词、查每条结论是否挂 CI/p、查是否把"功效不足"误写成"证明无效"。

## 对称报告（F4）
「证实」与「推翻」同模板呈现（同样给 CI/p），不给任一方向额外修辞权重；旧切对照统一标「趋势对照，肽集/病人数不同，不逐值比」。
