# PHASE 4 — 写作 + 投稿（⬜ 待做，写细）

> **状态**：⬜ 待做。可与 Phase 3 部分并行起草（benchmark 设计 + 规律章节不依赖 Phase 3 结果）。
> **硬截止**：ACCV 2026 paper **2026-07-05**（主投）；dataset 须 camera-ready **2026-10-04** 前公开。
> **目标**：把 lever ①②③ 落成投稿质量成稿 + 通过数字三方对账（lever ④）。

---

## ① 阶段目标 & 服务哪条 Claim/lever

**目标**：将 Phase 1（benchmark 主干）+ Phase 2（实证规律）+ Phase 3（小增量，或诚实负结果）写成 ACCV 2026 投稿稿，数字全部三方对账可复现，匿名化。
**服务**：核心 Claim 的全部支柱落地为文字；对齐 `02_ACCEPTANCE.md` **lever ②③（落成稿）+ lever ④（数字三方对账 csv↔tex↔registry，verifier 过 + 图 validate-figures 过 + 匿名化）**。

---

## ② 输入 / 前置依赖

- Phase 1 ✅ `results/master_*.csv`；Phase 2 ✅ 三规律判定 + 3 图；Phase 3（待）自适应阈值结果或诚实负结果。
- `01_STORY.md` 章节弧（写作弧的唯一蓝本，**不得偏离**）。
- ACCV 2026 LaTeX 模板（官方下载，`\todo{核 ACCV 官方 style 文件名}`——查不到标 TODO 不臆造）。
- 竞品论文（Related Work 区分用）：FUGC / HDC / DSTCT / ERSR。

---

## ③ 写作弧（对齐 `01_STORY.md` 章节弧，逐节施工）

> **铁律**：章节顺序 = `01_STORY.md` 章节弧，不重排、不改 Claim。每节标注承重点 + 防御写法。

| 节 | 内容 | 承重 / 防御要点 |
|---|---|---|
| **Abstract** | 一句话 Claim + 三规律 + 小增量；hook = 「碎片化评测 → 首个统一跨任务 benchmark」 | 不写 SOTA/novelty（R5）；数字（PS 0.7462/FH 0.9033/p 值）与正文一致 |
| **§1 Intro** | 胎儿超声标注昂贵（~70s/图 + 全球产科扫查人员短缺）→ 半监督关键；现有评测**碎片化**（各选各数据/比例/seed，ProPL 不含 PSFHS/FUGC，FUGC 单任务）→ 缺统一 benchmark | motivation 引 CALOPUS（PMC9478819）；hook 落在「碎片化」非「方法新」 |
| **§2 Related Work** | 半监督医学分割(MT/CPS/UAMT/FixMatch) + 胎儿超声分割(CMIS/PSFHS/HC18/FUGC) + 标注效率研究 | **显式区分**：FUGC/HDC/DSTCT/ERSR 各自**单集** vs 我们**跨结构跨集系统对比**——这是 novel 空间，必须点明 |
| **§3 Benchmark 设计** | 3 集 × 5 比例 × 5 方法 × 3 seed；统一 split/协议/评估；**held-out 不泄漏**（HC18 779 单视角去多视角防泄漏） | R2：明写 split 固定 seed + 无交集核验；坑1（HC18 mask 椭圆重建）写入 supplementary |
| **§4 小增量** | 自适应置信阈值机理 + 实现（随训练/伪标签质量动态调阈） | 若 Phase 3 负结果 → 诚实写「固定阈值已够」，benchmark 仍成立（02_ACCEPTANCE 明示增量非唯一支柱） |
| **§5 实验/发现** | 效率曲线（规律 1，重述「高比例趋同收敛」）+ 排名稳定性 Kendall-τ（规律 2「无普适最优」）+ **PS/FH 难度不对称（规律 3 承重）** + 自适应阈值增益 + 统计检验 | **与规律 3 闭环**：自适应阈值正为「难结构+低标注」交叉区设计；裂缝 1/2 诚实呈 spread（见 `PHASE_2` §5） |
| **§6 Conclusion** | 实用指南（临床标注决策：哪方法/多少标注在哪结构最稳）+ 诚实 limitation | limitation 必含：n=3 功效有限 / 极低标注方差大 / FUGC 是否拿到 / 规律 3 绝对增益薄 |

---

## ④ DoD 验收阈值（写作完成判定）

> 阈值真源 = `02_ACCEPTANCE.md` § Phase 4。本节列**自检命令**，不复制阈值定义。

```bash
# 1. 数字三方对账：tex 里每个数字回核 csv
grep -oE "0\.[0-9]+" main.tex     # 逐条对 results/master_*.csv（禁 Read 信数据，R1）
# 2. 每个 ρ/p 配检验、每个 dice 配来源 → 人工逐条 + verifier 过
# 3. 匿名化：无作者名/单位/导师名/自引未发表
grep -iE "wang|xjtlu|余嘉|jiayu|legacc" main.tex   # 期望 0 命中
# 4. 图 validate-figures 过（数字/比例核 ≥2 关键值与稿/csv 一致）
# 5. 编译干净 0 error / 0 undefined ref；主文页数 ≤ ACCV 上限（\todo{核 ACCV 页数上限}）
```

- [ ] 数字三方对账 csv↔tex↔registry，**verifier 过**（不是 writer 自核）。
- [ ] 图 `validate-figures` 过 + 主线核 ≥2 关键值。
- [ ] 匿名化 grep 0 命中。
- [ ] 编译干净、页数合规。
- [ ] limitation 诚实段（含规律 3 绝对增益薄 + 功效有限）。
- **判定**：`02_ACCEPTANCE.md` § Phase 4 三条（三方对账 / 图过 / 匿名化）全 PASS。

---

## ⑤ 投稿 checklist（仿 BMVC，逐条勾）

- [ ] **数字回 csv 禁 Read**（R1）：Abstract/§3/§5 每个 dice/ρ/p 逐条 Grep 核 `master_*.csv`，verifier 过后入稿。
- [ ] **图路径规范**：图存 `figures/`，`\includegraphics` 从 main.tex 算相对路径；含数字/比例的图交付后主线派 verifier 核 ≥2 关键值与 csv 一致再接稿。
- [ ] **双盲匿名**：删作者/单位/导师名/自引未发表（grep 见 ④）；致谢留空或匿名占位。
- [ ] **dataset camera-ready 前公开**：ACCV 要求 dataset 须 2026-10-04 前公开。本文用全公开集（PSFHS/HC18 Zenodo 已公开，FUGC 需申请）→ benchmark 代码/split/harness 须打包公开（Zenodo / anonymous GitHub）。
- [ ] **limitation 诚实段**：n=3 功效有限 / 极低标注方差大 / 规律 3 绝对增益薄（裂缝 1）/ 方向不一致反例计数（裂缝 2）/ FUGC 是否拿到（拿不到诚实写「双数据集」，R6）。
- [ ] **R-rules 防御 grep**：无「SOTA」「best in literature」「we prove」「novel method」绝对化措辞（R4/R5）。
- [ ] **`/pre-submit-check`**：投稿前跑（数字三方对账 + 脱敏 + 图验证）。

### ⑤b 双 venue 回退策略

| 优先级 | venue | 截止 | 触发条件 | 依据 |
|---|---|---|---|---|
| **主投** | **ACCV 2026 主会** | paper 2026-07-05 / dataset 公开 2026-10-04 | 默认；benchmark+小增量形可接 | 官方接受「Datasets and Performance Analysis」类，CORE-B，2024 接收率 32.2%（accv2026.org） |
| 退路 1 | **WACV 2027 Applications** | `\todo{核 WACV 2027 截止}` | 赶不上 ACCV / strong reject 风险 | 明文「benchmark 不以算法新颖度单独拒稿」「new way of benchmarking 算 novelty」（wacv2025 reviewer guidelines），对 benchmark 友好 |
| 退路 2 | **MICCAI workshop / ISBI** | `\todo{核对应截止}` | 双主投均不成 | `02_ACCEPTANCE.md` § 可接受最坏结局（benchmark+小增量底线达成） |

---

## ⑥ 对齐哪条 ACCEPTANCE

`02_ACCEPTANCE.md` § **Phase 4 — 写作+投稿**：数字三方对账(csv↔tex↔registry) verifier 过 / 图 validate-figures 过 / 匿名化。**红线**：数字 Read 编造 = 红线 4；spread 薄夸大成显著优势 = 跑偏（诚实写）。

---

## ⑦ 佐证引用（带出处）

- **ACCV 2026**：paper 截止 2026-07-05，CORE-B，2024 接收率 32.2%，接受「Datasets and Performance Analysis」类，dataset 须 camera-ready（2026-10-04）前公开（accv2026.org）。
- **WACV 兜底依据**：「benchmark 不以算法新颖度单独拒稿」「new way of benchmarking 算 novelty」（wacv2025 reviewer guidelines）。
- **motivation**：产科超声每图标注 ~70s + 全球产科扫查人员短缺（CALOPUS，PMC9478819）。
- **竞品单集 vs 我们跨集**：FUGC（ISBI2025，arXiv 2601.15572）/ HDC（CVPR2025）/ DSTCT（MICCAI2024）/ ERSR（JBHI2025）。
- ACCV 官方 LaTeX style 文件名 + 页数上限 + WACV/ISBI 退路截止 = `\todo{投稿前核官方源，不臆造}`。

---

## ⑧ 预期产出物清单

- `main.tex`（成稿）+ ACCV style 文件
- `figures/`：fig_efficiency_curves / fig_ssl_gain / fig_struct_asymmetry（+ Phase 3 自适应阈值图）
- 投稿包：匿名 PDF + supplementary（含坑1 HC18 mask 重建说明 + 完整 split + 超参表）
- benchmark 公开物：代码/split/harness 打包（Zenodo / anonymous GitHub），满足 dataset camera-ready 前公开
- `STORY_REFINEMENT.md`（若规律 3 裂缝触发退守，承接 `PHASE_2` §5）

---

## ⑨ 完成判定（5 步流程）

1. 查 `02_ACCEPTANCE.md` § Phase 4 验收阈值。
2. 逐条对照：三方对账过 / 图过 / 匿名化过。
3. 全条 PASS → 写 `04_LOG.md` + 跑 `/pre-submit-check`。
4. 跑反跑偏检查：数字 Grep 核 csv（R1，verifier 而非 writer 自核）；R4/R5 防御 grep 无绝对化措辞；匿名化 grep 0 命中。
5. **不存在「基本完成」**——三方对账 + 图 + 匿名化全 PASS + 编译干净页数合规 → 投稿放行（投稿本身 = 拍板点，停下报用户）。
