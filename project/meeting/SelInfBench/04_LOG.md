# SelInfBench PROJECT LOG

> 进度留痕。倒序（最新在上）。

---

## ⏳ 续跑交接（2026-06-18 12:30，A3 重跑中，新窗口接力看这里）

> ⚠️ A3 首跑(slot 46970170)异常：跑 ~2h(GPU 89% 实证在算)但 exit0 + log 0字节 + csv 没落盘 = 疑被外部清掉、stdout 全缓冲 buffer 丢光。**已重跑**(下条)，这次 `python -u` 不缓冲 log 实时流。

**A3 deflation-vs-M sweep 重跑中**（GPU local 卡 **gpu_slot id=6ce4a6b4** 占用中，run b3d9r43jz，PYTHONUNBUFFERED）：
- 脚本 `scripts/selinf_a3_benchmarks.py`（ISIC2020+BraTS2021 二分类 ×M∈{4,8,18,36} data fission deflation + 难度体检）。
- log `results/a3_run.log`（**这次实时流，非空且在长=在跑；停止增长+有 VERDICT=跑完**），输出 `results/a3_deflation_vs_M.csv`。
- **判完成**：`a3_deflation_vs_M.csv` 存在 + log 尾有 `A3 VERDICT` → 跑完。
- **跑完必做**：`python tools/gpu_slot.py release 6ce4a6b4` 清账（会吐 NEXT 取排队任务）。
- **跑完下一步**：analyst 读 a3_deflation_vs_M.csv 判 A3（3 benchmark deflation 随 M 单调增 + 斜率同向为正 + data fission 随 M 系统失效=PASS；BraTS 若 AUROC>0.95 触顶 deflation 坍=任务过易 artifact 非 winner's curse 不存在,脚本已 WARN,换更难变体）→ verifier 核数。
- ⚠️ 若 a3_run.log 非空但报错/崩 → 看尾部，多半又是 RTX4070 env bug（已知 inplace SiLU+cudnn.benchmark，selinf_datafission.py 有修法可抄）。

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
