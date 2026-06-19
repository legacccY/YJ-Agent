# SelInfBench — STORY FRAMEWORK

> 战略叙事唯一真源。改 headline / 卖点 = 拍板点（CLAUDE.md 拍板点 4），先报。
> 2026-06-18 立项首版（源 ideation run-002 G6 C025）。
> 2026-06-18 重写（Entry 5 暴雷后，用户拍板放行）：弃「deflation 通胀倍数」headline，证据换成条件覆盖率破裂 + 去偏移位。

## Headline（2026-06-19 转投 BIBE 2026 重述，用户拍板「临床可复现优先」）

> **venue：IEEE BIBE 2026（EI/IEEE，full 8 页双栏，DDL 2026-06-24 待用户官方核实）。从 TMLR/D&B 降档——资产已撞顶会天花板（A3 仅 2/3），EI 量级正合适。**

**临床可复现切入（BIBE 叙事主线）**：医学影像 AI 论文惯例报告超参 / seed sweep 里的**最优数**，这让报告的精度系统性虚高（winner's curse），并使临床医生 / 工程师据以选型部署所依赖的置信区间失效。本文 (1) 在真实医学 benchmark（HAM10000 皮肤镜 / BraTS 脑 MRI）上实测可量化的 winner's curse；(2) 证明经典置信区间欠覆盖被选模型的真实精度，而基于 data fission 的校正能恢复名义覆盖；(3) 交付一个即插即用的报告值校正器，任何 benchmark sweep 都可挂用以给出去偏点估计与有效区间。

**拟标题方向**：*Are Reported Accuracies in Medical Imaging AI Benchmarks Trustworthy? Diagnosing and Correcting the Winner's Curse via Data Fission*（标题含 "Medical Imaging" + "Trustworthy Reporting" 关键词，强化 BIBE scope fit）。

**方法层不变（仅叙事重排）**：data fission 仍是核心校正手段，但降为「解决临床可复现痛点的手段」而非叙事主角；校正器工具作为可交付物前置强调。

## 三支柱卖点

1. **偏差真实可测、有效性可恢复**（非假想，证据 = 条件覆盖率 + 去偏移位）：18-config sweep best AUC 0.7467 落在 naive 95% CI 上界 0.7330 之外 = winner's curse 在医学 benchmark 上可测（A1）。修正合成实验（target 对齐被选 config 真值 mu_{i*}、naive 用单点 CI、扫 σ_mu/σ）进一步坐实：winner's curse 真区制（σ_mu/σ=0）下 naive 单点 CI 仅覆盖 0.794（M=18）/ 0.715（M=36），远破名义 90%，且点估计系统正偏 +0.0266 / +0.0298（acc_{i*} 高估真值）；data fission 把覆盖修回 0.946 / 0.949（名义 95%）、去偏 ≈0。**真信号 = 条件覆盖率破裂 + 点偏差，不是宽度。**
2. **方法对口、领域空白**：post-selection inference（argmax 选择事件可写成多面体 M−1 个线性约束，Lee 2016 适用；本文主用 data fission，Leiner+ JASA2023 / Perry+ 2024）专治「条件于被选中事件」的有效推断，GWAS/ML 用过但**医学影像零应用**；填的是「同方法多 HP×seed 取最优报告」这个最常见却没人校正的樱桃挑形式。data fission 实现已在合成实验下验明覆盖率正确（恢复名义 95%）、去偏正确（残偏 ≈0）。
3. **meta-science 工具产出**（D&B 友好）：交付一个可挂到任意医学 benchmark sweep 上的「报告值校正器」，给出**去偏点估计 + 恢复名义条件覆盖的有效区间**（基于 data fission），而非又一个 SOTA 模型——reproducibility / 可信报告角度的贡献。

## 方法红线（2026-06-18 skeptic 红队定 + Entry 5 暴雷订正，违反即跑偏）

- **弃宽度比 deflation 作为 headline 指标**：旧指标 deflation = `df_width/naive_width − 1` 经实测坐实是 **`√(2M)−1` 纯 M 数学恒等式**（data fission 宽 = 2z·σ·√2 不含 M，naive 宽 = 2z·σ/√M，比值里 σ 全约掉），喂任何噪声都吐固定值，与真假 winner's curse 无关——审稿人一句话 K3 翻盘。**宽度比/deflation% 永不作为有效性证据写进 headline 或验收。**
- **真证据 = 条件覆盖率 + 去偏移位**：① naive 单点 CI 在 winner's curse 真区制条件覆盖率跌破 90%、data fission 修回 ~95%（合成 coverage_sim_v2 坐实）；② 点估计系统正偏（acc_{i*} 高估被选 config 真值），data fission 去偏后残偏 ≈0。两者均随 winner's curse 强度（σ_mu/σ）正确缩放——弱区制（σ_mu/σ=5）naive 覆盖回 0.948/0.932、偏差降到 +0.0069/+0.0083，gap 随之消失，证非恒等式 artifact。
- **data fission 实现本身正确这一事实保留**：合成实验下覆盖率修回名义 95%、去偏 ≈0，方法构造无误（Leiner+ JASA2023）。暴雷的是「拿宽度比当 headline 指标」，不是 data fission 方法本身。
- **弃真数据 debias_shift = val_best − g_star 当 A3 证据（2026-06-19 skeptic 红队抓出）**：该量构造性偏正——零真 winner's curse 下蒙特卡洛 P(>0)≈0.95、随 σ 单调放大，与真偏差脱钩（`a3_truthproxy.csv` 里 ISIC winner's curse=−0.008 为负但 debias_shift=+0.011 为正，自证矛盾）。与旧 deflation 同病根。**A3 承重改用**：① winner's curse = val_best − test_selected（独立 test 当真值的真高估，HAM/BraTS 正）+ ② g_star 是否比 naive 更接近独立 test（方向检验，ISIC 诚实 FAIL）+ ③ A2 合成覆盖率破裂&修回。注意区分：A2 合成实验的 mean_point_bias（相对已知真值 target 的偏差，弱区制塌回 0）是干净的，被弃的是 A3 真数据 debias_shift。若要复活 debias_shift 须配零信号 null 校准报净值。
- **真 benchmark（A3）报去偏移位 + 条件/自助覆盖，弃 deflation-vs-M 曲线**：在 HAM/ISIC/BraTS 上报去偏移位 acc_best − g_star（data fission 校正幅度）一致为正 + naive 欠覆盖，而非宽度比随 M 单调增（后者 trivially PASS，证不了东西）。

## 关键概念厘清（措辞红线，违反即跑偏）

- **偏差 ≠ 模型差**：本文量化的是「报告习惯（sweep/seed-max）」带来的高估，不是说被测方法本身无效。claim 全程指向 reporting practice，不踩「这些医学 AI 都是错的」的过宽断言。
- **selective inference 有效性前提**：校正区间的有效性依赖选择事件可被多面体 / 条件分布刻画（Lee 2016 假设）/ data fission 分裂构造成立。若真实论文选择流程不可建模，须诚实标注「在可建模的 sweep 选择下」的辖域。
- **辖域守纪律，禁泛化**：合成实验的覆盖率/偏差数字属特定 σ_mu/σ 设定，单/少 benchmark 坐实 ≠ 普适常数；**禁把单 sweep 结论泛化成「所有医学论文都欠覆盖 X%」**，写作只引相对趋势 + 辖域内结论。
- **K3 caveat 据实写**：文献证据支持「主流医学报告习惯（报最优、罕报方差、罕做统计检验）与 winner's curse 一致」，且 seed 选择实测制造统计显著高估（Gustafsson 2024）；但**未找到「sweep 后取 max 报告」的精确比率统计**，多为「不报 std + 不做检验」的侧证——措辞别夸成「已普查证实取 max」。
- **诚实天花板**：单设定坐实 ≠ 多 benchmark 普适，standout 取决于 ≥3 benchmark 上去偏移位一致为正 + naive 欠覆盖（A3 / KILL-1），不在叙事里预支。

## 对手 / 差异化

- **Springer ML2024（选最好预训练模型）**：只覆盖「跨模型选择」，不覆盖「同方法多 HP×seed 取最优报告」——本文补后者。须 related work 显式引 + 切清边界。
- **Zrnic 2023 / selective inference for ML**：方法先例，但未落到医学影像 benchmark 报告习惯——本文是首个医学应用 + 校正器交付。
- **撞车风险（KILL-2）**：若有竞对先发把 selective inference 系统覆盖医学影像 benchmark → 重定位或砍，投稿前 researcher 复查。

## 报告习惯文献支撑（K3 已签字关闭，researcher 核，置信 85%）

- Koopmans et al. 2025, "False Promises in Medical Imaging AI? Assessing Validity of Outperformance Claims", arXiv:2505.04720（MICCAI 2023 全量 >80% 报最优、仅 10-13% 做统计检验）。
- Gustafsson et al. 2024, "Random effects during training: Implications for deep learning-based medical image segmentation", Computers in Biology and Medicine, DOI:10.1016/j.compbiomed.2024.109129（nnU-Net 50-seed，best seed 显著优于 0-76% 其他 seed = seed 选择实测制造统计显著高估）。
- Sculley et al. 2018, "Winner's Curse? On Pace, Progress, and Empirical Rigor", ICLR 2018 Workshop。
- Renard et al. 2020, "Variability and reproducibility in deep learning for medical image segmentation", Scientific Reports, PMC7426407（25% 论文不报方差）。
- caveat：未找到「sweep 后取 max 报告」的精确比率统计，证据多为「不报 std + 不做检验」的侧证——措辞写「主流报告习惯与 winner's curse 一致」，不写「已普查证实取 max」。

## 数据

BraTS2021 / HAM10000 / ISIC2020（本地就位）。A1 已在 HAM10000 上坐实（best 落 naive CI 外）；A2 合成实验（coverage_sim_v2）已坐实覆盖率破裂 + 去偏；A3 待在 ≥3 真实医学 benchmark 上报去偏移位 + 自助/条件覆盖。⚠️ 旧 G5「deflation 324% / 500%」作废（√(2M)−1 恒等式 artifact，详 04_LOG Entry 5）。
