# W8 Build Map — 九章重排收口（旧 Q-VIB main.tex 换新九章）

项目: ICLR 2027 唯一 D+A 系统论文（anonymized）
服务: 九章重排最后一棒 W8 = 把旧 698 行 Q-VIB 结构 main.tex 换成新九章（C0 决策面动机 + C1 诊断保持增强 + C2 query-for-retake 闭环 agent + C3 诚实边界）
新 headline（会话 41 拍板，STORY 已重铸）: closed-loop quality-triage agent（建设式增强 + retake），非 Q-VIB SOTA
禁复活: Q-VIB SOTA headline / abstract 0.707 幽灵数（与 Table1 真源 0.585 矛盾）/ agent 全局小于等于 Direct 的全局优 claim
身份: 本文件是 W8 执行依据，落盘防 context 断链。主线按本图机械删/重排 input，writer 写 3 段散文（abstract/§1.4/§9），收口 grep 验残留。
日期: 2026-06-17（北京时间）；作者 planner（Opus）；caveman OFF
只设计，不动 main.tex、不跑、不改 draft。

================================================================
## 0. 现状速记（main.tex = 698 行旧 Q-VIB 结构）

| 旧结构区块 | 行号 | 旧 label | 新九章处置 |
|---|---|---|---|
| abstract | 18-38 | — | 重写（删 0.707/calibration-only headline）|
| §1 Introduction | 41-90 | sec:intro | §1 保留壳，§1.4 contributions（73-90）重写为 C0-C3 |
| §2 Related Work | 93-162 | sec:related | 删 body，换 s2_related.tex |
| §3 Q-VIB 章 | 165-186 | sec:qvib | 整章删（Q-VIB 降脚注；理论退 supp A1）|
| §4 Enhancement | 189-224 | sec:enhance | 删 body，换 s4_c1_enhance.tex（自带 section）|
| §5 Closed-Loop Agent | 227-247 | sec:agent | 删 body，换 s5_c2_agent.tex（自带 section）|
| §6 ITB Benchmark | 250-269 | sec:benchmark | 删 body，换 s6_setup.tex（benchmark 降为 setup）|
| §7 Experiments | 272-602 | sec:exp | 删全部 body 子节，换 s71/s7_c1/s7_c3/s77 重排 |
| §8 Discussion | 605-648 | sec:discussion | 删 body，换 s8_discussion.tex（自带 section）|
| §9 Conclusion | 651-656 | sec:conclusion | 重写（建设式收口）|
| Ethics/Repro | 659-679 | sec:ethics/repro | 保留（核 cref 指向）|
| appendix inputs | 681-693 | — | 保留（A3/A18/A19 入哪与 cref 修见 §6）|

================================================================
## 1. 删除清单（逐段：删 / 保留 / 换 input）

行号以现 main.tex（698 行）为准。建议从尾部 §8 往 §2 倒序删，再正序插，避免行号漂移。

| # | 行号 | 段名 | 处置 | 替换为 |
|---|---|---|---|---|
| D1 | 18-38 | 旧 abstract（Q-VIB calibration / AUC 0.707 headline）| 删 | writer 重写新 abstract（§3）|
| D2 | 73-90 | §1.4 旧 contributions C1-C4（含 C4 ITB benchmark + 25-lever）| 删 | writer 重写 §1.4 = C0-C3（§4）|
| K1 | 41-72 | §1.1-§1.3 Intro（problem + why-fall-short + closed-loop hook）| 保留（已建设式，§1.3 已含 GradProm/selective/calibration 缺陷）| 微调 cite BMVC 不搬数 |
| D3 | 93-162 | §2 Related body（含旧 IB Q-VIB generalises VIB 卖点 L102-107）| 删整段 body | input drafts/s2_related（自带 section Related Work，label sec:related）|
| D4 | 164-186 | §3 sec:qvib 整章（Quality Assessment + Q-VIB bottleneck + input A1_compact）| 整章删（Q-VIB 降脚注，理论退 supp）| 无（新 §3 = 决策面，见 I2）|
| D5 | 188-224 | §4 sec:enhance body（旧版 completeness not recoverable 绝对化 L194 违 R1）| 删 body | input drafts/s4_c1_enhance（自带 section，label sec:enhance）|
| D6 | 226-247 | §5 sec:agent body（旧四通道 + input A2_3 / A3 corollary）| 删 body | input drafts/s5_c2_agent（自带 section，label sec:agent）|
| D7 | 249-269 | §6 sec:benchmark body（旧 9 baseline + 25-lever 当 contribution L263-269）| 删 body | input drafts/s6_setup（自带 section，label sec:setup；benchmark 降 setup）|
| K2 | 272-286 | §7 section Experiments，label sec:exp + Setup paragraph | 保留 section 头；删 282-286 重复 Setup 段（被 s6 覆盖）| 仅留 section Experiments，label sec:exp 一行 |
| D8 | 288-301 | §7.1 Main Results sec:exp-main + input table1_main（旧 9-baseline Q-VIB 表，含 0.585/0.707）| 整段删 | 无（新 §7.1 = 决策面，见 I7a）|
| D9 | 303-313 | §7.2 sec:exp-fidelity（E1/E12/E2）| 删（已并入 s7_c1 §7.6）| 见 I7b |
| D10 | 315-400 | §7.3 sec:exp-preserve（E3/E7/E8/E9/E10/dflip fig + input table1_e10_sota）| 删 body（被 s7_c1 重写覆盖；dflip fig 已在 s7_c1 内）| input drafts/s7_c1_results（I7b）|
| D11 | 402-461 | §7.4 sec:exp-salvage（E5/E6/Thm2 P1P3 routing）| 删 body | input drafts/s7_c3_boundary（I7c）|
| D12 | 463-478 | §7.5 Universality sec:exp-universal + input table2_universality | BMVC 占，整段删（R10）| 无 |
| D13 | 480-509 | §7.6 Cross-Domain sec:exp-cross（HAM/PAD/Fitz/DermNet/APTOS）| BMVC 占，整段删 | 无 |
| D14 | 511-568 | §7.7 DCA sec:exp-dca（含 BMVC fig:dca 版 513-526 + 0.585 幽灵口径混写）| 删 body（DCA 保留但走 ICLR 重跑版 draft）| input drafts/s77_dca_triage（自带 sec:exp-triage + sec:exp-dca 双锚，I7d）|
| D15 | 570-602 | §7.8 Fairness sec:exp-fair（sex/age/Fitzpatrick I-VI）| BMVC 占，整段删 | 无 |
| D16 | 605-648 | §8 Discussion body（含旧 limitation 引 sec:exp-cross/fair）| 删 body | input drafts/s8_discussion（自带 section，label sec:discussion）|
| D17 | 651-656 | §9 Conclusion body | 删 body | writer 重写新 §9（§5）|
| K3 | 659-671 | Ethics Statement | 保留；核 cref sec:exp-fair 改向 |
| K4 | 673-679 | Reproducibility Statement | 保留 |
| K5 | 681-693 | appendix input 块 | 保留；A3_corollary1 去留 + cref 修见 §6 |

BMVC 四段确认删: universality(table2, D12)、cross-domain(D13)、fairness(D15)、fig:dca BMVC 版(D14 内 513-526)。DCA 散文换 s77（ICLR n=300 重跑诚实负），BMVC 版 fig 必删（风险 R-3）。
table1_main（旧 9-baseline Q-VIB 表）确认删（D8 内）: 含 0.585/0.707，是 0.707 幽灵数 + Q-VIB SOTA 载体。
旧 abstract（D1）确认删: 第一句 Q-VIB calibration headline + L33-36 AUC 0.707 / ECE 0.098 是幽灵数主载体。

================================================================
## 2. 新九章 input 顺序（精确骨架）

包裹规则（已勘明核对）:
- 自带 section（直接 input 不加壳）: s2_related、s4_c1_enhance(sec:enhance)、s5_c2_agent(sec:agent)、s6_setup(sec:setup)、s3_decision_surface(sec:decision-surface)、s8_discussion(sec:discussion)。
- 仅 subsection、需父 section 包裹: s71_c0_results(sec:exp-surface)、s7_c1_results(sec:exp-preserve/dploss/sota/ablations)、s7_c3_boundary(sec:exp-boundary)、s77_dca_triage(sec:exp-triage + sec:exp-dca)。四者共用一个 section Experiments，label sec:exp 父壳。

新 body 完整 input 骨架（替换 main.tex 41-656 全部 body），缩进示意:

    [section]Introduction  label sec:intro
    K1 保留 41-72 §1.1-§1.3；D2 §1.4 由 writer 重写为 C0-C3（build map §4）
    [paragraph]Contributions   <- writer 重写四 bullet = C0/C1/C2/C3

    input drafts/s2_related          自带 section，label sec:related
    input drafts/s3_decision_surface 自带 section，label sec:decision-surface
    input drafts/s4_c1_enhance       自带 section，label sec:enhance（含内部 input A2_prop3_lemma3_compact）
    input drafts/s5_c2_agent         自带 section，label sec:agent（含内部 input A2_3_theorem2_compact）
    input drafts/s6_setup            自带 section，label sec:setup

    [section]Experiments  label sec:exp    <- §7 父壳
    K2 保留 section 头；删旧 Setup 段（s6 覆盖）+ 旧 Main Results 段（D8）
    input drafts/s71_c0_results      §7.1 subsection sec:exp-surface
    input drafts/s7_c1_results       §7.2-7.6（含内部 input drafts/s7_e10_sota）
    input drafts/s7_c3_boundary      §7.4/7.8 subsection sec:exp-boundary
    input drafts/s77_dca_triage      §7.7 subsection sec:exp-triage + sec:exp-dca

    input drafts/s8_discussion       自带 section，label sec:discussion
    [section]Conclusion  label sec:conclusion    <- D17 writer 重写（build map §5）

保留的 theory input（compact 主文版，在哪）:
- A2_prop3_lemma3_compact: 已在 s4_c1_enhance.tex 内部 L81 input 自动落 §4，主线无须额外加。
- A2_3_theorem2_compact: 已在 s5_c2_agent.tex 内部 L117 input 自动落 §5。
- A1_qvib_compact: 旧在 §3 sec:qvib（D4 删）不再进主文（Q-VIB 退 supp）；4 定理只在 appendix A1。
- A3_corollary1_compact: 旧在 §5 sec:cor1（D6 删）Cor1 原 link BMVC，BMVC 占；主文不引，appendix A3 supp 保留（见 §6-9）。

§7 内嵌 input 链（注意）:
- s7_c1_results.tex L48 input drafts/s7_e10_sota 拉入 s7_e10_sota.tex 自带 tab:e10 表（全 TODO）+ E10 prose。主线无须单独 input s7_e10_sota，它由 s7_c1 拉进来。
- 警告: table1_e10_sota.tex 与 s7_e10_sota.tex 双 label tab:e10 冲突（风险 R-1）。

================================================================
## 3. abstract 重写 brief（给 writer，删 0.707）

焊死第一句（建设式 closed-loop，禁 Q-VIB/calibration-only/0.707）:
We present a closed-loop quality-triage system for skin-lesion diagnosis on degraded consumer imagery, which decides per input whether to diagnose directly, to apply diagnosis-preserving enhancement, or to query for a retake, instead of passively enhancing or blindly deferring.

必含已核数字（全 STORY 锁定，verifier PASS）:
- VisiScore 5 维质量 PLCC 0.924 / SRCC 0.895。
- C0 决策面: reliability x recoverability，per-dimension x per-severity（AUC-led，blur 最脆 -0.0911；contrast S5 唯一 HURT -0.0355）。
- C1 诊断保持 E3: dAUC -0.012 / 一致率 0.9575 / McNemar p=0.573（enh 约等于 ref）；DP-Loss E7: dAUC +0.0205 / McNemar p=2.3e-45（Lemma 3 实证）。
- C2 query-for-retake = 文献首次采集闭环；Thm2 局部条件界（band tau_enh 到 tau_high）。
- C3 诚实负: triage 全局不优于 Direct（Direct sens 0.818 大于 best variant 0.788）；melanoma 救援净负。

绝对禁止入 abstract（writer 红线）:
- 禁 AUC 0.707 / ECE 0.098（幽灵数）
- 禁 Q-VIB 是更强诊断方法 / generalises VIB
- 禁 agent 全局小于等于 Direct / triage globally outperforms
- 禁 否定式 headline passive enhancement is unsafe（违 R14，要建设式）
- 禁 任何 BMVC 占的数（跨域 rho / ImageNet-C / 5-backbone / fairness）

写作要点: 先建设式（how to enhance safely + retake），再 honest（triage 全局负是 retake gate 动机，诚实 = 可信度来源），不藏负结果。

================================================================
## 4. §1.4 contributions 重写 brief（给 writer，四 bullet = C0-C3）

旧四 bullet（C1 Q-VIB / C2 VisiEnhance / C3 agent / C4 ITB benchmark + 25-lever）全删，换:

- C0（动机，不当独立 contribution，写成动机句不写 item 卖点）: 刻画 reliability x recoverability decision surface（per-dimension x per-severity，AUC-led，含 completeness 第 5 维 + recoverability 轴），motivates quality-aware triage。BMVC 的 per-dimension ECE/QCTS 视角（cited not reused）不覆盖此角度。
  STORY 强制: C0 不单列为 contribution，§1.4 四 bullet 由 C1/C2/C3 扛。C0 写成 motivating observation，不写 we propose a degradation surface。
- C1 Diagnosis-preserving enhancement + MI 下界: feature-level DP-Loss 让增强在 moderate 退化窗口不损诊断，Lemma 3 互信息下界 I(Z_enh;Y) 大于等于 I(Z_ref;Y) 减 beta sqrt(epsilon)（beta 约 0.74）+ 实证 E7（dAUC +0.0205 / p=2.3e-45）。
- C2 query-for-retake agent（独家钩子）: 四通道路由（direct/cautioned/enhance/query-for-retake），采集闭环（文献首次，非 abstain/defer）+ Thm2 局部条件界（band 内增强收益大于 0，band 外不成立）。
- C3 诚实边界: severe/melanoma 增强净负（E6 dAUC -0.056；E5 melanoma 救 4 毁 81）= query-for-retake 闸门最硬动机；triage 全局诚实负（Direct 0.818 大于 0.788）。

写作红线: we derive / under assumption 非 we prove（R2）；GradProm 差异化在 §2/§8（R12）；无绝对化（R1）；无 Q-VIB 增益 claim（R13）。

================================================================
## 5. §9 Conclusion brief（给 writer）

旧 §9（Q-VIB end-to-end theoretical closure + benchmark 收口）重写为建设式 + 诚实双调:
- 一句总结: a closed-loop quality-triage system that decides when to enhance vs. when to request a retake，backed by a diagnosis-preserving MI lower bound（Lemma 3）+ a local conditional risk guarantee（Thm 2）。
- 诚实收口: we chart where enhancement helps（moderate window）and where it must yield to re-acquisition（severe contrast / melanoma），and we report rather than hide that global fixed-threshold triage does not yet beat direct diagnosis，pointing to learned routing thresholds as future work。
- 禁: 任何 SOTA / Q-VIB / benchmark-as-deliverable / 0.707。建设式 + 诚实，不空喊。

================================================================
## 6. Label crosswalk + dangling 风险清单

### 6a. 新九章 draft 引用的 label
| draft 引 | 解析到 | 状态 |
|---|---|---|
| s4 ref lem:dp / prop:entropy | A2_prop3_lemma3_compact（s4 内 input）| OK 存在 |
| s5 ref thm:agent-compact | A2_3_theorem2_compact（s5 内 input）| OK 存在 |
| s5/s7_c3 cref sec:exp-salvage | 旧 label 被删（D11）；新等价 = s7_c3 的 sec:exp-boundary | 改引（6c）|
| s5/s7_c3/s8 cref sec:exp-dca / sec:exp-triage | s77 自带双锚 sec:exp-triage + sec:exp-dca | OK 双锚已设 |
| s8 cref sec:exp-c0 | 无此 label；新 = s71 的 sec:exp-surface | 改引（6c）|
| s7_c1 cref tab:e10 / fig:dflip | s7_e10_sota(tab:e10) + s7_c1 自带 fig:dflip | 警告 tab:e10 双定义（R-1）|
| s3 cref sec:method-enhance / s71 sec:exp-decision-surface | s3 应为 sec:enhance；s71 应为 sec:exp-surface | draft 内部 cref 名不一致需统一（6c）|

### 6b. 被删 label 谁还在引它（实测 grep）
| 被删 label | 删除位置 | 残留引用源 | 处置 |
|---|---|---|---|
| sec:qvib | D4 | appendix/A21_rebuttal.tex L85 | 改指 app:a1 或删句 |
| sec:exp-cross | D13（BMVC）| A21_rebuttal.tex L47, L55 | 删 A21 这两处引用 + 所在句（cross-domain 不在本篇）|
| sec:exp-fair | D15（BMVC）| main.tex Ethics L667 | 改写 Ethics 该句（fairness 不在本篇）|
| sec:exp-salvage | D11（换 sec:exp-boundary）| A20_cost_benefit L184、A2_3_theorem2_compact L20、s5、s7_c3、s71 | 全部改引 sec:exp-boundary |
| sec:benchmark | D7（换 sec:setup）| A4_itb_construction L73 | 改引 sec:setup |
| sec:exp-main / sec:exp-fidelity | D8/D9 | 仅 main.tex 内部（被删 body 自引）| OK 随删无外部 dangling |
| tab:main / tab:universality | D8/D12 | table1_main/table2_universality（随表删）| OK 随删 |
| prop:elbo / lem:mono / thm:drift / prop:entmono | Q-VIB 4 定理退 supp A1 | A0_notation、A1_qvib、A21（全 appendix 内部互引）| OK A1 supp 保留这 4 定理，label 仍存在不 dangling |
| cor:composite-compact | A3_corollary1_compact（Cor1）| main.tex L85/L610(删) + A0_notation L35 + A21 L90 | 保留 appendix A3 supp 则 label 仍定义 = 不 dangling（6c-9）|

### 6c. crosswalk 改引指令
1. sec:exp-salvage 改 sec:exp-boundary（全仓: A20 L184、A2_3_theorem2_compact L20、s5_c2_agent L26/113/154）。统一把所有 sec:exp-salvage 引用改成 sec:exp-boundary。
2. sec:exp-c0 改 sec:exp-surface（s8_discussion L100）。
3. sec:method-enhance 改 sec:enhance（s3_decision_surface L84）。
4. sec:exp-decision-surface 改 sec:exp-surface（s71 L52 内部 ref）。
5. sec:qvib（A21 L85）改指 app:a1 或删句（Q-VIB 退 supp）。
6. sec:exp-cross（A21 L47/55）删所在句/段（cross-domain BMVC 占）。
7. sec:exp-fair（main.tex Ethics L667）删 cref，泛述 subgroup fairness（cited companion work）或删从句。
8. sec:benchmark 改 sec:setup（A4_itb_construction L73）。
9. Cor1 决策: A3_corollary1 保留为 appendix supp，主文不引（D6 已删 §5 cor1）。A0_notation L35 + A21 L90 的 Cor1 引用因 A3 supp 仍 input（K5），label 在 supp 内定义即不 dangling，无须改。确认 K5 appendix input 块保留 input appendix/A3_corollary1。

crosswalk 条数: 8 类被删 label，9 条改引指令（含 1 条 保留即可不改 的 Cor1 决策）。

================================================================
## 7. W8 执行拆分

### 7a. 主线机械做（删 / 重排 input / sed 改引）
1. 按 §1 倒序删 main.tex body（D1-D17，保留 K1-K5），§8 往 §2 删。
2. 按 §2 骨架插 9 个 input（s2/s3/s4/s5/s6 + §7 父壳含 s71/s7_c1/s7_c3/s77 + s8）。
3. 按 §6c sed 改引（指令 1-8），sed 9 确认 A3 input 保留。
4. 不动 draft 内容（draft 的 cref 名统一在 sed 范围内或确认已用新 label）。

### 7b. writer 写（caveman OFF，3 段散文 + 2 小修）
1. 新 abstract（§3 brief，删 0.707，焊 closed-loop）。
2. 新 §1.4 contributions（§4 brief，C0-C3）。
3. 新 §9 Conclusion（§5 brief，建设式 + 诚实）。
4. 小修 A21_rebuttal（删 sec:exp-cross/qvib 引用句）+ main.tex Ethics（sec:exp-fair 句）。

### 7c. 收口 grep 验（零残留 + 章节顺序 + 0 dangling）
- (1) BMVC / Q-VIB / 0.707 幽灵数零残留: grep main.tex 期望 0 命中 0.707 / universal / cross-domain / Fitzpatrick / fairness / ImageNet-C / table2_universality / input table1_main / Q-VIB generalises。
- (2) 新九章 input 顺序: grep input drafts/s 应见 s2 s3 s4 s5 s6 s71 s7_c1 s7_c3 s77 s8 顺序。
- (3) 0 dangling cref: grep main.tex appendix/*.tex drafts/*.tex 中 sec:exp-cross sec:exp-fair sec:exp-universal sec:exp-main sec:exp-fidelity sec:qvib sec:exp-salvage sec:exp-c0 sec:method-enhance tab:main tab:universality 期望仅 supp A1 内部互引；编译后查 .log Reference undefined。
- (4) duplicate label tab:e10: grep label tab:e10 期望唯一一处。
- (5) 脱敏（投稿前，非 W8 必须）: grep VisiSkin/Q-VIB/VisiScore/VisiEnhance（R4）。

================================================================
## 8. 风险清单（前置 TODO / 拍板点 / 复核建议）

R-1 [红] duplicate label tab:e10: s7_e10_sota.tex L31（全 TODO 表）与 table1_e10_sota.tex L16 都定义 tab:e10。s7_c1 L48 只 input s7_e10_sota 走 TODO 版。LaTeX 报 duplicate（若 table1_e10_sota 仍被某处 input）。处置: 收口 grep(4) 查；二选一 用 table1_e10_sota（需 coder 核哪个有 job 1448952 真值），或填 s7_e10_sota 的 TODO（dAUC 区间 -0.12 到 -0.07 / p 小于 1e-150 / PSNR 32.79 已锁，派 coder 从 results/e10_*.csv 填）。建议主线/Opus 决定保留哪个表文件。

R-2 [红] E1 no-FiLM 33.06 配对值丢失: s7_c1 L84 todo HPC 恢复。e1_film_ablation.json 丢失，本地无 no-FiLM ckpt（在 HPC stage1_planA_256_noFiLM）。入 main.tex 前必恢复，否则 E8 PSNR 中性 需软化措辞。处置: 前置 TODO 拉 HPC job 1442290/1442337 .out 取 33.06 或重跑 noFiLM eval。HPC 拉取 = 拍板点，主线串行做。

R-3 [红] fig:dca 必重画（非 BMVC 版）: s77 L54-56 todo。fig_dca_triage.pdf 须确认是 ICLR 重跑版（ITB-LQ n=300），非 BMVC DCA 图。若是 BMVC 版 = 违 R10 必替换。处置: 派 coder/analyst 核 report/figures/fig_dca_triage.pdf 来源；是 BMVC 版则重画。收口前必清。

R-4 +TokFT maxNB 口径: 风险点要求用 0.179（dca_results.csv/STORY 锁定）非 summary 的 0.1798。已核 s77 用 0.179 OK（dca_summary.json: dca_max_nb 的 Q-VIB+TokFT=0.1793，bootstrap CI block max_nb_point=0.1798）。draft 已对无 drift，writer/verifier 入 tex 时勿误抄 0.1798。处置: 核对 OK，备查。

R-5 TAU band edges 待 verifier: s5 L94-98 todo 三档阈值（0.25/0.35/0.50 讨论值）未印，body 只用符号 tau_low 小于 tau_enh 小于 tau_high。处置: 派 verifier 从 agent_vs_direct_risk.csv 确认后填；未确认前保持符号，禁凭印象印数。

R-6 AT-CXR bib 缺: s5 L160 todo atcxr2025 arXiv id/作者/venue 未定。处置: 派 researcher 查 AT-CXR 确切 arXiv id。

R-7 retake routing CI + per-band risk-reduction CI 待 re-verify: s7_c3 L96/L110 注释。从 main.tex L441-453 迁移的 retake fraction（0.055/0.651/0.889）+ risk-reduction（-0.305/-0.189/-0.127）入主文前 verifier re-check。处置: 派 verifier 核 results 源。

R-8 s6 setup 多处 todo verifier: dataset 源/split/B3 身份/moderate-tier 组成（L35/L50/L53/L92）未对 DATA_INVENTORY 核。处置: 派 verifier 核 degrade.py + 训练 config + E10 job 1448952。

R-9 A3/A18/A19 appendix 去留: A3_corollary1 = Cor1（Q-VIB link BMVC，BMVC 占）STORY 标 supp 框架或删。K5 建议保留为 supp（label 不 dangling，6c-9），主文不引。处置: 主线确认 appendix input 块保留 A3。

R-10 C0.3 多方法 UQ（s3 §3.5 L89-92 全 todo）+ universality 已删，§3.5 是否留空壳。处置: 建议删 §3.5 壳或留 todo 注 deferred，非主腿不致命。

================================================================
## 9. 一句话风险概括
最大风险 = R-1 duplicate tab:e10 + E10 数字仍是 TODO（s7_e10_sota 占位未填，job 1448952 真值已锁但未落表）。W8 重排骨架可机械完成，但 E10 表是空的、E1 no-FiLM 配对值丢在 HPC、fig:dca 来源待验，这三处不清则 main.tex 编译有 dangling/空表，需 coder + verifier + 主线（HPC 拉取）收尾才能真正 W8 闭环。

建议主线/Opus 复核: R-1（哪个 e10 表文件留）+ R-9（A3 supp 去留）是结构决策，超出纯机械重排，宜拍板确认。
