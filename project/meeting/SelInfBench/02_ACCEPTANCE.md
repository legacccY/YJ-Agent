# SelInfBench — ACCEPTANCE CRITERIA

> 验收判据 + 书面 kill criteria 唯一真源。改阈值 = 拍板点。2026-06-18 立项首版（源 G6 charter C025 R7）。
> 2026-06-18 重写（Entry 5 暴雷后，用户拍板放行）：A2/A3/K3 弃宽度比 deflation，改条件覆盖率 + 去偏移位。

## 核心验收判据（投稿前必须全过）

> 2026-06-18 订正：宽度比 deflation = `√(2M)−1` 纯 M 恒等式 artifact，永久弃用为有效性证据；真证据 = 条件覆盖率 + 去偏移位（详 01_STORY 方法红线）。

- **A1 偏差真实可测**：≥1 医学 benchmark 上 sweep best 落在 naive CI 外 = winner's curse 可测。✅ HAM10000 已坐实（best 0.7467 > naive 上界 0.7330）。
- **A2 校正有效（合成实验坐实）**：修正合成（target 对齐被选 config 真值 mu_{i*} + naive 单点 CI + 扫 σ_mu/σ∈{0,0.5,1,2,5}）下，winner's curse 真区制（σ_mu ≤ 噪声量级）naive 条件覆盖 **<90%** 且点偏差显著为正，data fission 覆盖 **≥93%** 且去偏 ≈0；弱区制（σ_mu 大）gap 消失（证非 artifact）。✅ 已达标（`results/coverage_sim_v2.csv`，N_rep=2000）：σ_mu/σ=0 时 naive 覆盖 0.794（M=18）/ 0.715（M=36）、点偏差 +0.0266 / +0.0298，data fission 覆盖 0.946 / 0.949、去偏 ≈0；弱区制 σ_mu/σ=5 时 naive 覆盖回 0.948 / 0.932、偏差降 +0.0069 / +0.0083，data fission 0.954 / 0.957。naive 宽度固定 0.0784（不含 M）、df 0.1109、宽度比恒 √2 → 坐实宽度比是 artifact，真信号在覆盖率 + 偏差。
- **A3 普适性（真 benchmark · 去偏移位）**：≥3 真实医学 benchmark（HAM / ISIC / BraTS）上报**去偏移位 acc_best − g_star**（data fission 校正幅度）+ 自助/条件覆盖率，证移位一致为正（系统高估）且 naive 欠覆盖。**明确弃「deflation 随 M 单调增」宽度比判据**（√(2M)−1 trivially PASS，证不了东西）。⏳ A2 通过后扩 ISIC/BraTS（难度体检避 AUROC 触顶坍信号）。
- **A4 工具可交付**：报告值校正器（data fission 实现）可挂任意 sweep 日志，给出**去偏点估计 + 恢复名义条件覆盖的有效区间**（交付指标 = 覆盖率 + 去偏移位，非 deflation%）。⏳ 立项后工程化。

## 雄心档位（诚实分级）

- **退路档达标线（TMLR）**：A1 + A2（合成下 naive 欠覆盖 + data fission 修回 + 去偏）+ 校正器交付（A4）= 可信报告方法论贡献，站得住。
- **顶会升级线（ICLR / NeurIPS D&B）**：再 + A3（≥3 benchmark 去偏移位一致为正 + naive 欠覆盖）+ A4 工具广用性 = meta-science 实证 + 可复用工具。

## 书面 kill criteria（立项即生效，触发即诚实回退）

- **K1（实证 · gating）**：扩展到 ≥3 个真实医学 benchmark 后，去偏移位方向不一致 / 多数 benchmark naive 不欠覆盖 → 降格 workshop / D&B。复查：首轮 2 周。
- **K2（撞车）**：selective inference for ML benchmarking 被竞对先发系统覆盖医学影像 → 重定位或砍。
- **K3（理论）✅ 已签字关闭（2026-06-18）**：前提「真实论文按 sweep/seed-max 报告」成立——文献证据充分（Koopmans 2025 / Gustafsson 2024 / Sculley 2018 / Renard 2020，详 01_STORY 报告习惯文献支撑）。caveat：未找到「sweep 后取 max 报告」的精确比率统计，证据多为「不报 std + 不做检验」侧证 + seed 选择实测制造统计显著高估（Gustafsson 2024），措辞守「主流报告习惯与 winner's curse 一致」辖域。
- **K4（资源）**：> 40 GPU·h 仍无稳定显著去偏移位 / 覆盖率破裂 → 停。
- 复查节奏：每 2 周。签字：用户 legacccy / 2026-06-17。

## 复现红线（全程）

- selective inference / data fission 实现按 Lee et al. 2016 / Leiner+ JASA2023 官方构造，禁私改条件分布或分裂参数凑显著；选择事件刻画须与真实 sweep 流程一致。
- 数字一律 Bash/Grep 核 csv（`results/coverage_sim_v2.csv` 等），入文前过 verifier，不信 Read。
- 覆盖率 / 去偏移位辖域措辞守 STORY 红线，禁把单 sweep 结论泛化成普适常数。
- **禁用宽度比 deflation 当有效性证据**：`df_width/naive_width − 1 ≡ √(2M)−1` 是纯 M artifact（σ 约掉），与真假 winner's curse 无关，永不进 headline / 验收 / 校正器主指标。
