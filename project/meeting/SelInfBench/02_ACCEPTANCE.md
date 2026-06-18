# SelInfBench — ACCEPTANCE CRITERIA

> 验收判据 + 书面 kill criteria 唯一真源。改阈值 = 拍板点。2026-06-18 立项首版（源 G6 charter C025 R7）。

## 核心验收判据（投稿前必须全过）

> 2026-06-18 skeptic 红队订正：A2/A3 弃 √M 近似改 data fission 有效区间（详 01_STORY 方法红线）。

- **A1 偏差真实可测**：≥1 医学 benchmark 上 sweep best 落在 naive CI 外（winner's curse 可测）。✅ HAM10000 已坐实（best 0.7467 > naive 上界 0.7330）。
- **A2 校正有效且非平凡（GO/NO-GO 前置）**：用 **data fission**（或 Lee2016 截断正态 pivot）重算 HAM deflation——① 合成实验下该区间条件覆盖率达名义 95%（naive 显著 <95% 证选择破坏有效性）；② HAM 真区间下 deflation 仍显著 > 20%（非 √M artifact）。⏳ Gate1 第一步，坍则 K3 砍。原 G5 324% 作废（√M 恒等式）。
- **A3 普适性（曲线非单点）**：deflation 随 sweep 规模 M∈{4,8,18,36} **单调增且真区间随之系统失效**（artifact 无此理论 M-scaling），≥3 benchmark 上斜率方向一致。⏳ A2 通过后扩 ISIC/BraTS（难度体检避 AUROC 触顶坍 deflation）。
- **A4 工具可交付**：通胀校正器（data fission 实现）可挂任意 sweep 日志、给出后选有效区间 + deflation。⏳ 立项后工程化。

## 雄心档位（诚实分级）

- **退路档达标线（TMLR）**：A1 + A2 + 单 benchmark 诚实标注 + 校正器交付 = 可信报告方法论贡献，站得住。
- **顶会升级线（ICLR / NeurIPS D&B）**：再 + A3（≥3 benchmark deflation 中位数显著）+ A4 工具广用性 = meta-science 实证 + 可复用工具。

## 书面 kill criteria（立项即生效，触发即诚实回退）

- **K1（实证 · gating）**：扩展到 ≥3 个真实医学 benchmark 后，deflation **中位数 < 20%**（HAM 单设定 324% 多设定回落）→ 降格 workshop / D&B。复查：首轮 2 周。
- **K2（撞车）**：selective inference for ML benchmarking 被竞对先发系统覆盖医学影像 → 重定位或砍。
- **K3（理论）**：若证实真实论文报告习惯不构成 winner's curse（deflation 仅 sweep artifact，真实报告并不取 sweep max）→ 砍。
- **K4（资源）**：> 40 GPU·h 仍无稳定显著 deflation → 停。
- 复查节奏：每 2 周。签字：用户 legacccy / 2026-06-17。

## 复现红线（全程）

- selective inference 实现按 Lee et al. 2016 / Zrnic 2023 官方构造，禁私改条件分布凑显著；选择事件刻画须与真实 sweep 流程一致。
- 数字一律 Bash/Grep 核 csv（`c025_deflation.csv`），入文前过 verifier，不信 Read。
- deflation 辖域措辞守 STORY 红线，禁把单 sweep 结论泛化成普适常数。
