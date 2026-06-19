# SelInfBench PROJECT LOG

> 进度留痕。倒序（最新在上）。

---

## Entry 8 — 转投 BIBE 2026 + 补强冲稳中稿（2026-06-19，用户拍板降档 EI）

用户拍板：从 paused(TMLR/D&B) 降档投 **IEEE BIBE 2026**（EI/IEEE，DDL 用户称 06-24 官网未核实，full 8 页双栏）。用户追加要求：**①一定要稳稳中稿（可加实验）②注意故事讲法**。

**四闸复核（本窗）**：
- 资产 Bash 核盘属实：A1✅(truthproxy HAM winner's curse +0.0746) / A2✅稳(coverage_sim_v2 naive 覆盖跌 0.715~0.794 破名义 90%、df 修回 ~0.95、弱区制 gap 消失) / A3 PARTIAL 2/3(HAM 强+BraTS 触顶+ISIC 负) / A4✅校正器建好(`scripts/selinf_corrector.py` 烟测核过 CI 逐位对上)。
- K2 撞车 🟢 不撞（researcher）：无人先发同 claim；prior=Åkesson2024/Zrnic-Fithian2024/Leiner2023。
- ⚠️ 数字隐患钉死：A1 旧 headline 0.7467/0.7330 来自 HPC `c025_deflation.csv` **未回传本地无源 → 🚫 禁入稿**，A1 证据改用本地可核 truthproxy +0.0746。

**新建**：`paper/BUILD_MAP.md`（章节↔判据↔本地可核 csv 数字钉死表 + venue 决策留痕 + 禁用 deflation 红线）+ `paper/figures/`。IEEEtran+pdflatex 已验在 texlive2025。

**下一步（本窗在跑）**：planner 设计补强实验矩阵（核心=扩 ISIC test 阳性数把 2/3→3/3 + 真 benchmark 自助覆盖率）+ skeptic 红队 BIBE 拒稿风险 → 重述 BIBE 故事(医学可复现性角度，headline 改= 拍板点先报) → 补实验 → writer 写稿。

---

## Entry 7 — ICLR 升级探索 = 死，项目暂停于 TMLR/D&B（2026-06-18，用户拍板转别的项目）

用户问"能否升级 80% 稳中 ICLR"→ 探"医学挑战赛 leaderboard 冠军高估审计 + 自适应选择条件推断"升级路 → **两 kill-shot 双杀，升级死，回 TMLR/D&B**。

**调研（3 researcher）**：① Kaggle 医学赛（ISIC2020 3314 队/RSNA）public+private 双分可得；② 最大撞车 Zrnic-Fithian arXiv2411.18569（单轮 winner CI）；③ 公开医学 sweep 数据基本不存在，自跑审计够 TMLR 不够顶会（Åkesson2024 已占医学自跑 best-seed 高估）；④ reduction 缝隙未先发但薄（~70%）。

**skeptic 红队 2 命门 + 2 kill-shot 验**：
- **命门 2 审计腿 🔴 proxy 错位**：Kaggle public→private gap = 对 public split 的自适应过拟合（Roelofs NeurIPS2019 已证整体小），**不是 winner's curse on 真实性能**；private 本身是干净真值代理。要 claim"高估真实泛化"需第三份独立部署分布数据，多数赛没有。kill-shot #1（扒双分）因此 moot——未跑。
- **命门 1 方法腿 🔴 DEAD**：kill-shot #2 合成 pilot（`tools/selinf_method_pilot.py` → `results/method_pilot.csv`，N_rep=3000，主线 Bash 核）证 **naive-on-private 覆盖全程 [0.9417,0.957]**（最坏 R=50 重度自适应也 ~95% 不破），naive-on-public 最低 0.0（public winner's curse 真严重）。→ private 是条件独立 fresh holdout，自动兜底，新条件推断在 leaderboard 场景**无角色**。方法只在"无 private、单 test 反复复用"（=SelInfBench 原方向，TMLR 级）ALIVE。

**结论**：leaderboard 升级到 ICLR 死（两腿同根塌于"Kaggle private 是干净 holdout"）。SelInfBench 诚实天花板 = **TMLR / NeurIPS D&B**，资产扎实（A1 winner's curse 可测 + A2 合成覆盖坐实 + 校正器 + A3 2/3 真 benchmark 去偏 3/3 正向）。唯一活的细缝=单 test 复用下精确条件推断比 Bonferroni 有 power 优势（pilot bonf 0.99 过保守），增量、仍 TMLR。

**🅿️ 项目状态 = PAUSED（暂停，资产完好，非砍）**。用户 2026-06-18 拍板转别的项目（精力转更有胜算的 ICLR 主线/DisagreePred/FMReg）。
**恢复入口（重启时读）**：要发 TMLR/D&B 就走 → ① A3 补强（ISIC test 阳性仅 17 个太少，扩 test 降方差看 winner's curse 是否转正，把 2/3→3/3）② A4 校正器工程化（挂任意 sweep 日志出去偏 CI）③ writer 写稿（A1+A2+A3+校正器）。别再碰 leaderboard 路（已证死，见本 entry）。

---

## Entry 6 — A3 truthproxy 跑完 = PARTIAL（2026-06-18，HPC job 1462992，2/3 winner's curse，退路稳顶会腿不够）

**修正版 A3（test-as-truth winner's curse）HPC 跑完**（gpu4090 job 1462992，~2h45m，slot 199ce2a2 已 release，csv 拉回本地 `results/a3_truthproxy.csv`）。3 benchmark M=18，val 选 best → test 当真值：

| benchmark | val_best | test_selected | winners_curse(val−test) | debias_shift(val−g*) | g* vs naive 距 test |
|---|---|---|---|---|---|
| ISIC2020 | 0.8646 | 0.8726 | **−0.0080** ❌ | +0.0114 | g* 更远(0.0195>0.0080) ❌ |
| BraTS2021 | 0.9951 | 0.9788 | +0.0163 ✅(触顶弱) | +0.0022 | g* 更近 ✅ |
| HAM10000 | 0.9283 | 0.8536 | **+0.0746** ✅强 | +0.0169 | g* 更近 ✅ |

**A3 = PARTIAL**（脚本 VERDICT 同判）：winner's curse>0 **2/3**、debias_shift>0 **3/3**、g* 更近 test **2/3**。
- **ISIC 反例**：test_selected(0.873) > val_best(0.865)，winner's curse 负——test 集 1000 仅 17 阳性，AUROC 方差大（sigma 0.0147），噪声里被选 config 在 test 反而更好。非系统高估。
- **BraTS 触顶**：AUROC~0.99 饱和（难度体检 WARN 在案），winner's curse +0.016 方向对但幅度小。
- **HAM 强**：高估 +0.075、去偏 g* 明显更近 test，干净的 winner's curse。

**判据对照 ACCEPTANCE**：A3 顶会线要 ≥3 benchmark 一致——**未达**（2/3）。**退路档 TMLR/D&B 稳**（A1 winner's curse 可测 ✅ + A2 合成覆盖 ✅ + 校正器 + 2/3 真 benchmark 去偏 3/3 正向）。顶会原方向这条腿不够硬。

**带债 / 方向**：
- A3 弱 → 印证"自跑 sweep 审计"够 TMLR 不够顶会（与 researcher 调研 Åkesson2024 已占医学自跑一致）。顶会需升级路（Kaggle leaderboard 审计，但 skeptic 命门 2 proxy 错位待破）。
- 可选补强：ISIC 扩 test 阳性数（现 17 个太少）降方差再看 winner's curse 是否转正；BraTS 换更难变体避触顶。但这只把 A3 从 2/3 推向 3/3，仍是 TMLR 级，不解决顶会新意。
- **升级 kill-shot 待跑**：① Kaggle 双分 gap 探针（等用户下 CSV，已备 `tools/selinf_kaggle_lb_probe.py`）② 方法腿合成 pilot（private naive 是否已覆盖）。两个定升级生死。

---

## Entry 5 — deflation 指标暴雷：headline 整体重定（2026-06-18，skeptic 三 🔴 → 两必补全 PASS → 项目得救待 ACCEPTANCE 重写）

**重大纠错：Entry 3「K3 解除 / data fission 500% 证明 winner's curse」结论作废。** 主线接 A3 后台跑（slot 46970170）时核脚本数学，逮出致命问题，派 skeptic 红队坐实，再派 coder+researcher 两诊断救场。

**致命问题（主线发现 + skeptic 独立 MC 复核坐实）**：
- 原 headline 指标 deflation = `df_width/naive_width − 1`。data_fission_ci width = 2z·σ·√(1+1/τ²)（τ=1 → 2z·σ·√2，**不含 M**），naive_ci width = 2z·σ/√M，比值里 **σ 全约掉** → deflation ≡ **√(2M)−1**，纯 M 恒等式，与真假 winner's curse 无关。
- HAM M=18 实测 500.0% = √36−1（datafission）、324.26% = √18−1（sqrtM），两者都是 M-恒等式。Entry 3「500%≠324% 证非 artifact」错——两者只差 τ=1 引入的 √2，都是 artifact。
- 后果：A3「deflation 随 M 单调增」对任何数据 trivially PASS，证不了东西 = skeptic 早砍的 K3 √M-陷阱原样复活。
- **A3 sweep 当场 kill**（pid 19816，省剩 ~1h GPU），slot 46970170 released。原始 deflation_pct 列作废。

**skeptic 红队（opus）追加两 🔴（比主线发现更深）**：
- 🔴 旧 coverage_sim 的「naive 0.003 vs datafission 0.947」是**张冠李戴**：naive 区间盖的是 sweep 均值 target，却拿去覆盖被选 config 真值 = 两个参数错配造的人为必败。换公平 naive（被选 config 单点 CI）覆盖 0.93-0.95 不破裂 → **Entry 3 的 A2 有效性证据作废**。
- 🔴 旧合成 target=mu_{i*} 且 mu 间距太开 → 选的是真最好者，winner's curse 在该设定下不存在（实测偏差 +0.0001）。
- 🔴 替代「移位 best−g_star」幅度 = σ·E[max] 确定性函数，零真偏差下照样非零，同病根。

**两必补（coder + researcher 并行）全 PASS**：
- ✅ **必补 1 — 修正合成实验 GO**（`scripts/selinf_coverage_sim_v2.py` → `results/coverage_sim_v2.csv`，N_rep=2000，主线 Bash 核数）：三区间对齐同一 target=mu_{i*} + naive 改单点 CI（中心 acc_{i*}、宽 2z·σ）+ 扫 σ_mu∈{0,0.5,1,2,5}×σ。winner's curse 真区制（σ_mu=0/0.5）下 **naive 覆盖跌到 0.715（M=36）远破 0.90 + 系统正偏差 +0.027~+0.030**，datafission 覆盖 0.944~0.949（修回名义 95%）、去偏 ≈0。弱区制（σ_mu=5）naive 回 0.93-0.95、偏差降到 +0.007 → **gap 来自真 winner's curse 非恒等式**。skeptic 三 🔴 全解。naive width 现固定 0.0784 不含 M、df 0.1109、宽度比恒 √2 → 坐实**宽度比是 artifact，真信号在覆盖率破裂 + 点偏差**。
- ✅ **必补 2 — K3 不触发（researcher 调研，置信 85%）**：医学 benchmark 确实按 sweep/seed max 报告——Koopmans 2025（arXiv:2505.04720，MICCAI 2023 全量 >80% 报最优无方差、仅 10-13% 做统计检验）+ Gustafsson 2024（CompBioMed，nnU-Net 50-seed，best seed 在 hold-out 显著优于 0-76% 其他 seed = 医学影像 winner's curse 实测）+ Sculley 2018 winner's curse 先例 + Renard 2020（25% 论文完全不报方差）。caveat：未找到「sweep 后取 max 报告」的精确比率统计，多为「不报 std + 不做检验」侧证。

**新 headline 方向（待用户拍 ACCEPTANCE/STORY 重写）**：
- 弃「deflation% 通胀倍数」（√(2M)−1 artifact），改 = **① 条件覆盖率破裂**（naive 单点 CI 在 winner's curse 区制覆盖 <90% / datafission 修回 ~95%）+ **② 去偏移位**（acc_{i*} 系统正偏差 vs datafission g_star 去偏≈0），均数据驱动、随 winner's curse 强度（σ_mu）正确缩放。
- A2/A3/K3 待据此重定（skeptic 建议：A2=合成下 naive 覆盖<90% 且 df≥93%；A3=真 benchmark 上去偏移位 + naive 覆盖随 M/σ_mu 联动，弃宽度比）。

**带债 / 下一步**：
- 🛑 拍板点：ACCEPTANCE A2/A3/K3 + STORY headline 重写（改方向，等用户放行）。
- 放行后：(a) 改 `selinf_a3_benchmarks.py` 在真 benchmark（HAM/ISIC/BraTS）上算去偏移位 + 自助覆盖，弃 deflation 列；(b) writer 重写 STORY/ACCEPTANCE；(c) 引用入库：Koopmans2025/Gustafsson2024/Sculley2018/Renard2020。
- 引用全文件：`scripts/selinf_coverage_sim_v2.py`、`results/coverage_sim_v2.csv`、`scripts/selinf_a3_benchmarks.py` L182-227（恒等式来源）、`results/ham_datafission.csv` _STAT_ 三行。

---

---

## Entry 3 — Gate1 A2 GO/NO-GO 跑通（2026-06-18，data fission 真区间 = GO）

coder 修 env bug（torchvision EfficientNet-B3 inplace SiLU + cudnn.benchmark 在 RTX4070 Laptop WDDM 崩 → 关 inplace + cudnn.benchmark=False）后，HAM 18-config sweep + data fission 跑通（local 卡 9bebdda5→939e5da4，~0.36 GPU·h，主线核 log）：

**A2 GO/NO-GO = GO ✅**（结果 `results/ham_datafission.csv` + `datafission_run.log`）：
- sweep M=18，sigma_hat(pooled std)=0.008343，best acc=0.8200（lr=3e-4/dp=0.4/s=2024，落在 naive CI 外=winner's curse 真实）。
- **data fission 有效 CI=[0.7930,0.8392] 宽 0.0463 vs naive 宽 0.0077 → deflation=500.0% > 20% = GO**。
- **K3 解除**：data fission 500% ≠ √M 近似 324.26%（=√18−1 正好印证 skeptic 恒等式诊断）——真区间给出不同且更大的数，证 deflation 非 √M artifact 而是真 winner's curse。

**A2 覆盖率模拟 PASS**（`results/coverage_sim.csv`，N_rep=2000，纯 CPU）：data fission 覆盖 0.947（名义 95%，12/12 cell 全 ≥0.90）、naive 0.003（12/12 cell <0.95=选择破坏有效性）、√M 过宽 1.000。→ data fission 区间有效性坐实。

**下一步 A3**：扩 ISIC2020 + BraTS slice 二分类 sweep（本地 ready）+ deflation-vs-M 曲线（M∈{4,8,18,36}）。需 coder 加 ISIC/BraTS dataset 类 + 难度体检避 AUROC 触顶坍 deflation。local 现被 run-004 占→排队或等。

**带债**：本地 HAM 真值已落地（best 0.82），旧 HPC job1454467 的 324% smoke 不再用。

---

## Entry 2 — Gate1 设计 + skeptic 红队（2026-06-18，用户拍板 data fission）

**planner 出 Gate1 矩阵 → skeptic 红队 2🔴 → 用户拍板补救。**

🔴 **致命发现（同根）**：核 `c025_deflation.csv` 实证——G5 的 deflation = `corrected_ci/naive_ci−1 ≈ √M−1` 是**固定 M 下的数学恒等式**（18 个 val_acc 全挤 0.706–0.747，bias=E[maxZ_{18}]·σ）。喂任何 18-config 噪声都吐 ≈324%，与有没有真 winner's curse 无关。后果：① 324% 作废（非有效区间）；② A3「M=18 单点中位数≥20%」trivially PASS（√18−1=324%»20% 恒成立）= 假 PASS，K3 一句翻盘。

**researcher 救场**：argmax 选择确实能写成多面体（M−1 个线性约束 e_j−e_{i*}，Lee2016 适用，截断正态 pivot + V⁻/V⁺ 公式）。更优 = **data fission**（Leiner+ JASA2023：注入 Z~N(0,σ²) 分裂 f(X)=X+τZ 选择 / g(X)=X−Z/τ 推断，对 g 建标准 CI；Perry+ 2024 证 CI 比多面体更窄、3 行 numpy）。已有 sweep 不能重跑时退 Andrews2024 winference（QJE，R 包）。

**用户拍板（2026-06-18 AskUserQuestion）**：① 换 **data fission** 重算；② A3 改 **deflation-vs-M 曲线斜率**（M∈{4,8,18,36} 单调增 + 真区间随之系统失效，artifact 无此理论 scaling）。已订正 01_STORY（加方法红线）+ 02_ACCEPTANCE（A2 改 data fission GO/NO-GO 前置、A3 改曲线）。

**Gate1 第一步 go/no-go**：data fission 真区间重算 HAM——deflation 仍 ≫20% 才往下跑 3 benchmark；坍则当场 K3 砍（<1 GPU·h，立项前证伪精神）。

**带债**：① 本地 `c025_deflation.csv` 是 2-config smoke（41%），324% 的 18-config HPC job1454467 未回传本地，重算 HAM 须先拿真 sweep 读数；② BraTS 二分类难度体检避 AUROC 触顶坍 deflation；③ 引用：Lee2016(arXiv1311.6238)/Andrews2024 QJE/Leiner2023 JASA(2112.11079)/Perry2024(2408.06323)。

**下一步**：派 coder 实现 data fission 重算 HAM（Gate1 go/no-go）→ 主线跑 → analyst 判。

---

## Entry 1 — 立项 spin-off（2026-06-18，用户已拍板）

**立项决策**：源 = ideation run-002（医学图像 × 不确定性）G6 立项 **C025**。用户 2026-06-17 AskUserQuestion 拍板「立项 C025 + C065」（G6_charter.md 签字）。本 entry 为拍板后 spin-off 执行（建标准 schema + 登 registry），非新决策。

**RQ / headline**：医学 AI benchmark 普遍存在「樱桃挑通胀」——跨 HP/seed sweep 取最优报告让报告值系统性高估，经典 CI 在后选下失效；用 selective inference（Lee 2016）给条件有效区间，首次量化并校正医学影像里的这层通胀。

**与边界**：纯新项目（非主论文拆分）。与 ICLR(VisiSkin) / MedAD-FailMap / FMReg / NCA-PhaseMap 零重叠——meta-science / reproducibility 轨，正交于 UQ / 校准 / 分割。

**立项依据（G5 killshot ✅ PASS，HPC job1454467）**：
- 18-config sweep best AUC = 0.7467，落在 naive 95% CI 上界 0.7330 之外 = winner's curse 真实可测。
- selective inference 校正后 deflation = 324% ≫ 5% 阈 = 樱桃挑通胀坐实非噪声。
- 差异化：selective inference 在 GWAS / Zrnic2023 ML 用过但医学影像零应用；Springer ML2024 只覆盖「选最好预训练模型」不覆盖「同方法多 HP×seed 取最优报告」。
- 脚本/csv：`ideation/runs/2026-06-17_run-002_medimg-uncertainty/06_experiments/G5_killshots/killshot_c025_selective_inference.py`（+ `hpc/killshot_c025_hpc.py`）；结果 `.../c025_deflation.csv`。立项卡 `.../07_report/G6_charter.md` 立项 1。

**诚实天花板**：单设定（HAM10000）324% 坐实 ≠ 多 benchmark 普适。退路档 TMLR 已稳（A1+A2+校正器）；顶会需 ≥3 benchmark deflation 中位数显著（A3 / KILL-1）。书面 kill criteria K1-K4 见 02_ACCEPTANCE。

**带债 / 立项后第一前置**：
- R1（普适性 gating）：扩 ≥3 真实医学 benchmark（BraTS/ISIC 本地就位）看 deflation 中位数是否 ≥ 20%（KILL-1）——决定顶会 vs workshop。
- R2（有效性）：补条件覆盖率模拟，验 selective inference 区间满足 Lee2016 名义覆盖（A2）。
- R3（工具）：通胀校正器工程化，可挂任意 sweep 日志（A4）。
- R4（撞车）：投稿前 researcher 复查 selective-inference-for-ML-benchmarking 医学影像是否被先发（K2）。

**venue**：top ICLR 2027 (reproducibility/meta-science) / NeurIPS D&B｜fallback TMLR。算力 ≤ 40 GPU·h。

**下一步 Gate1**：`/design-experiment selinf` 出扩 benchmark 矩阵（≥3 集 deflation + 条件覆盖率模拟 + 校正器工程化）。数据 BraTS2021/HAM10000/ISIC2020 本地 ready。
