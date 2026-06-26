# PHASE 2 — 实证规律（回填 + 标裂缝，✅ PASS）

> **状态**：✅ PASS（2026-06-25，`04_LOG.md` Entry 10）。本文件为**回填存档 + 风险裂缝留痕**。承重规律 3（结构难度不对称）已统计显著坐实；规律 1/2 重定义为诚实表述。**§5 显著标注「规律 3 裂缝」——一审最可能塌的点，须在 Phase 3/写作闭环加固。**

---

## ① 阶段目标 & 服务哪条 Claim/lever

**目标**：从 Phase 1 的 150 run 中提炼 ≥1 个统计显著、可解释的实证规律，构成论文的「实证发现」支柱。
**服务**：核心 Claim 的「**揭示效率曲线/排名稳定性/结构难度不对称三规律**」（引自 `01_STORY.md` 章节弧 §5）；对齐 `02_ACCEPTANCE.md` **lever ②（≥1 可报告规律，95%CI/Wilcoxon 显著且可解释）**。

---

## ② 输入 / 前置依赖

- `results/master_wide.csv`（150 run）+ `results/master_long.csv`（225 行，per-structure，供 PS/FH 不对称）。
- analyst 判读 + 主线 Bash 自核 ≥4 关键值（R1 纪律，已全吻合）。
- 纯分析阶段，**无训练**。

---

## ③ 三规律分析任务（已完成）

| 规律 | 分析方法 | 判定 | 服务章节 |
|---|---|---|---|
| **规律 1 — 收益递减** | 各比例 SSL 增益趋势 + Spearman ρ | ⚠️ **GRAY**（信号弱，重述） | §5 实验/发现 |
| **规律 2 — 排名(不)稳定** | Kendall-τ 跨比例/跨集排名相关 | 重定义为「**无普适最优方法**」（正向发现） | §5 + Benchmark 必要性论证 |
| **规律 3 — 结构难度不对称** | PS vs FH 监督基线 + SSL 正增益率 + Wilcoxon/Mann-Whitney | ✅ **PASS（承重）** | §5 + 与小增量闭环 |

---

## ④ DoD 验收阈值（已达）+ 锁定数字

> 阈值真源 = `02_ACCEPTANCE.md` § Phase 2。本节记**实测数字 + 自检命令**。**所有数字 Grep 核 `master_*.csv`（R1），入 tex 前必过 verifier。**

### 🔒 锁定数字（不可凭印象改写，全部从 csv 核算）

**规律 3（承重，PASS）**：
| 量 | 值 | 出处/检验 |
|---|---|---|
| supervised PS dice（难结构） | **0.7462** | `master_long.csv` structure=PS, method=supervised |
| supervised FH dice（易结构） | **0.9033** | `master_long.csv` structure=FH, method=supervised |
| SSL 正增益率 PS | **56.7%** | PS 上 SSL 方法相对 sup 为正的占比 |
| SSL 正增益率 FH | **15.0%** | FH 上同口径 |
| 不对称显著性 | Wilcoxon **p=0.0468** / Mann-Whitney **p=0.0028** | PS vs FH 增益分布检验 |

**规律 1（GRAY，重述）**：
- 准确表述 = 「**高比例 SSL 趋同收敛到 supervised（增益压缩到零）**」，**非**「低比例 SSL 显著更好」。
- PSFHS gain 1%/2% > 10%/20%（Mann-Whitney p=0.03–0.05）；HC18 Spearman **ρ=−0.27（p=0.036）**。
- HC18 天花板强（1% sup 已 0.835）→ 收益递减不可见。

**规律 2（无普适最优）**：
- Kendall-τ 跨比例 PSFHS=**0.12** / HC18=**0.08**；跨集 τ=**0.2（p>0.8）** 全近随机。
- 1% 下最优：PSFHS=supervised、HC18=CPS（两集不同）→ 随 ratio 剧烈洗牌。
- **这是 benchmark 核心正向发现**（无单一最优 → 统一评测必要），非「稳定性 FAIL」。

```bash
# 关键值自核示例（R1 纪律，禁 Read 信数据）
# supervised PS / FH 基线
grep ",supervised," results/master_long.csv | grep ",PS," | awk -F, '{s+=$NF;n++} END{print "PS sup mean=",s/n}'
grep ",supervised," results/master_long.csv | grep ",FH," | awk -F, '{s+=$NF;n++} END{print "FH sup mean=",s/n}'
```

**判定**：`02_ACCEPTANCE.md` § Phase 2 PASS 条件 =「≥1 规律统计显著(95%CI/Wilcoxon)且可解释」满足（规律 3 坐实）→ **PASS**。

---

## ⑤ 风险 & 回退 —— ⚠️ 规律 3 裂缝（一审最可能塌点，必读）

> **这是 Phase 2 最重要的一节。承重规律 3 statistically PASS，但有两条裂缝，一审可能据此攻塌。Phase 3 + 写作须主动闭环加固，不可掩盖（R4 不夸大）。**

### 🔴 裂缝 1：PS 绝对均增益微负（−0.0117）
- 规律 3 PASS 的承重在「**PS 增益显著 > FH 增益**」（相对不对称），**不是** SSL 在 PS 上绝对超 supervised。
- PS 上 SSL 方法均增益 = **−0.0117**（绝对微负）；正增益率 56.7% 仅指「多于一半 setting 为正」，非平均为正。
- **风险**：一审读成「你这 SSL 在难结构也没用」。
- **加固**：写作严格守 R4——措辞固定为「SSL 增益**系统性集中**于难结构（相对易结构），但绝对增益薄」；配 Phase 3 自适应阈值在「难结构 + 低标注」交叉区把绝对增益做正，叙事闭环。

### 🔴 裂缝 2：方向不一致反例（HDC / CVPR2025）
- 个别方法（如 HDC，CVPR2025）在 FH 上增益**反 > PS**，与「难结构增益更大」主方向不一致。
- **风险**：一审举反例质疑规律 3 不是普适规律而是方法依赖。
- **加固**：（a）规律 3 措辞限定为「**跨方法聚合**的不对称」非「每个方法都满足」；（b）显式在正文/supplementary 列方向一致 vs 不一致方法计数（仿 BMVC「反转 corruption 数 = X/N」做法），诚实呈现 spread；（c）若反例多到动摇聚合显著性 → 退守 GRAY，转 `STORY_REFINEMENT.md` 重定义承重点。

### 🟡 裂缝 3：功效有限
- n=3 seed，部分格 CI 宽、功效有限；p 值解释保守。
- PSFHS @1% UAMT 高方差（seed Dice 0.26/0.49/0.81）= 6 图训练固有随机，**非 bug**。
- **加固**：limitation 诚实写「极低标注区方差大、功效有限」；如时间允许补 seed 增功效。

### 回退路径
1. 裂缝可控（守 R4 措辞 + 诚实呈 spread）→ 规律 3 维持承重，进 Phase 3/写作。
2. 裂缝 2 反例动摇聚合显著性 → 触发 `02_ACCEPTANCE.md` § Phase 2 **GRAY** 分支（R9 GRAY 不砍）：补低比例/FUGC 更难数据再判，仍弱则降 venue（WACV App / workshop）不硬撑。
3. **规律 3 全塌 + 规律 1/2 也无显著** → 论文降级为「纯 benchmark 协议贡献」，靠 lever ① + 「无普适最优」（规律 2 正向发现）撑底线 venue。

---

## ⑥ 对齐哪条 ACCEPTANCE

`02_ACCEPTANCE.md` § **Phase 2 — 实证规律**：PASS = ≥1 规律统计显著(95%CI/Wilcoxon)且可解释；**FAIL（GRAY 不砍）** = 所有规律 CI 宽/不显著 → R9 GRAY 补数据再判。本阶段规律 3 PASS，规律 1 GRAY、规律 2 重定义为正向发现。

---

## ⑦ 佐证引用（带出处）

- **统计检验口径**：Wilcoxon signed-rank（配对）/ Mann-Whitney U（独立两样本）/ Spearman ρ / Kendall-τ —— 标准非参数检验。
- **竞品无系统跨结构对比**：FUGC（ISBI2025，arXiv 2601.15572）/ HDC（CVPR2025）/ DSTCT（MICCAI2024）/ ERSR（JBHI2025）各自单集，无人系统对比多集结构难度异质性 = 本文 novel 空间。
- **可解释依据**：高基线（FH=0.9033）无增益空间、难结构低基线（PS=0.7462）unlabeled 有信息增量 → SSL 增益集中难结构低标注交叉区。

---

## ⑧ 预期产出物清单（已交付）

- `figures/fig_efficiency_curves.pdf`（标注效率曲线，服务规律 1）
- `figures/fig_ssl_gain.pdf`（SSL 增益 vs 标注比例，服务规律 1）
- `figures/fig_struct_asymmetry.pdf`（PS vs FH 不对称，服务规律 3 承重）
- 三规律判定记录（本文件 + `04_LOG.md` Entry 10）
- **待建**（裂缝 1/2 触发时）：`STORY_REFINEMENT.md`（重定义承重点的退守文档）

---

## ⑨ 完成判定（5 步流程）

1. 查 `02_ACCEPTANCE.md` § Phase 2 验收阈值。
2. 逐条对照：≥1 规律显著(规律 3 Wilcoxon p=0.0468)且可解释 → 满足。
3. 全条 PASS → 写 `04_LOG.md`（已记 Entry 10）+ 评估是否进 Phase 3。
4. 跑反跑偏检查：数字 Grep 核 csv（R1，已自核 ≥4 值吻合）；规律 3 措辞守 R4 不夸大（承重在相对不对称非绝对增益）；**显式标记裂缝 1/2 防一审塌（本文件 §5）**。
5. **不存在「基本完成」**——规律 3 统计显著 + 裂缝已留痕加固方案 → **PASS 存档**。
