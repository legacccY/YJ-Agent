# SelInfBench PROJECT LOG

> 进度留痕。倒序（最新在上）。

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
