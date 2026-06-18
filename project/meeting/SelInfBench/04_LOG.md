# SelInfBench PROJECT LOG

> 进度留痕。倒序（最新在上）。

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
