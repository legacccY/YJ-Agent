# SelInfBench — STORY FRAMEWORK

> 战略叙事唯一真源。改 headline / 卖点 = 拍板点（CLAUDE.md 拍板点 4），先报。
> 2026-06-18 立项首版（源 ideation run-002 G6 C025）。

## Headline

**医学 AI benchmark 普遍存在「樱桃挑通胀」：跨 HP / seed sweep 取最优报告的习惯让报告值系统性高估，经典置信区间在这种后选下失效；用 selective inference 给出条件有效区间，首次量化并校正医学影像里的这层通胀。**

## 三支柱卖点

1. **真实存在的偏差**（非假想）：18-config sweep best AUC 0.7467 落在 naive 95% CI 上界 0.7330 之外 = winner's curse 在医学 benchmark 上可测。⚠️ **G5 的 deflation 324% 是 `√M−1` 近似（max-of-Gaussian 期望偏移），非真有效区间**——见下「方法红线」，正式量改用 data fission 重算。
2. **方法对口、领域空白**：post-selection inference（argmax 选择事件可写成多面体 M−1 个线性约束，Lee 2016 适用；更优 = data fission，Leiner+ JASA2023 / Perry+ 2024 证 CI 更窄）专治「条件于被选中事件」的有效推断，GWAS/ML 用过但**医学影像零应用**；填的是「同方法多 HP×seed 取最优报告」这个最常见却没人校正的樱桃挑形式。
3. **meta-science 工具产出**（D&B 友好）：交付一个可挂到任意医学 benchmark sweep 上的「报告值通胀校正器」（基于 data fission / 截断正态有效区间），而非又一个 SOTA 模型——reproducibility / 可信报告角度的贡献。

## 方法红线（2026-06-18 skeptic 红队定，违反即跑偏）

- **deflation 必须用有效区间，禁用 √M 近似**：G5 的 `corrected_ci/naive_ci−1 ≈ √M−1` 是固定 M 下的数学恒等式，喂任何 18-config 噪声都吐 ≈324%，与有没有真 winner's curse 无关——审稿人一句话 K3 翻盘。正式 deflation 用 **data fission**（重跑 sweep 时注入 Z~N(0,σ²) 分裂选择/推断，对 g(X) 建标准 CI，理论最干净 CI 最窄）重算；已有 sweep 不能重跑时退 Andrews2024 winference / Lee2016 多面体截断正态 pivot。
- **A3 改「deflation-vs-M 曲线」**：固定 M 单点中位数对 √M 近似恒真、对真区间又可能恒假，阈值与所测不对齐。普适性证据 = deflation 随 sweep 规模 M∈{4,8,18,36} 单调增且真区间随之系统失效（artifact 无此理论 M-scaling）。
- **Gate1 第一步 go/no-go**：先用 data fission 真区间重算 HAM——deflation 仍 ≫20% 才往下跑 3 benchmark；坍到个位数 → 当场 K3 命中砍，省 3-benchmark 算力。

## 关键概念厘清（措辞红线，违反即跑偏）

- **通胀 ≠ 模型差**：deflation 量化的是「报告习惯」带来的高估，不是说被测方法本身无效。claim 全程指向 reporting practice，不踩「这些医学 AI 都是错的」的过宽断言。
- **selective inference 有效性前提**：校正区间的有效性依赖选择事件可被多面体 / 条件分布刻画（Lee 2016 假设）。若真实论文选择流程不可建模，须诚实标注「在可建模的 sweep 选择下」的辖域，**禁把单 sweep 结论泛化成"所有医学论文都通胀 324%"**。
- **deflation 是相对量**：324% 是 HAM 单设定下的相对收缩，写作只引相对 deflation 趋势，不把绝对数字当普适常数。
- **诚实天花板**：单设定坐实 ≠ 多 benchmark 普适，standout 取决于 ≥3 benchmark 的 deflation 中位数（KILL-1），不在叙事里预支。

## 对手 / 差异化

- **Springer ML2024（选最好预训练模型）**：只覆盖「跨模型选择」，不覆盖「同方法多 HP×seed 取最优报告」——本文补后者。须 related work 显式引 + 切清边界。
- **Zrnic 2023 / selective inference for ML**：方法先例，但未落到医学影像 benchmark 报告习惯——本文是首个医学应用 + 校正器交付。
- **撞车风险（KILL-2）**：若有竞对先发把 selective inference 系统覆盖医学影像 benchmark → 重定位或砍，投稿前 researcher 复查。

## 数据

BraTS2021 / HAM10000 / ISIC2020（本地就位）。G5 已在 HAM10000 上跑通；立项后扩 ≥2 个独立医学 benchmark 验 deflation 普适性。
