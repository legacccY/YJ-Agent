<!-- ⚠️ 2026-07-01：数据处理+评判标准已从零重建（LOG Entry 40-44）。本档 §7 锁定数字部分过时，最新真源=RESULTS_CLEAN_SUMMARY.md。claim 措辞待袁老师定 2 点（见 给袁老师_两个方法学问题.md）。 -->
<!-- ============================================================
本档为 QuantImmuBench 项目的 headline 锚定文件（项目 STORY / 框架真源）。
- 权威框架 = `paper/QuanImmu-Paper-Outline.md`（袁老师定稿，BiB 投稿版大纲）。本档与其冲突时以袁 md 为准。
- 旧 `paper/STORY.md`（2026-06-26 锁定的窄框架 = magnitude gap + per-patient）已**降级**为本框架下的 §3.1 单工具基线 / per-patient 评估协议的子章节素材，其防御写法与引用修正在本档 §7 完整继承，不丢弃。
- 沿承旧 STORY 的 HLA-FIX 待办：PredIG 全局显著性在剔除污染患者 P101/P102 后失效（max-pool ρ 0.198→0.104 p=0.343 ns；mean-agg 0.280→0.188 p=0.084 ns）；IMPROVE 仍稳健显著；TSCAPE 翻为显著负；deepHLApan 另有 merge bug 双重不可信。per-patient 头条数字待 Phase B 正确等位重推理后据 corrected-excl 复核。本档锁定的 headline / 数字在投稿前（= 拍板点）不擅动。详见 04_LOG Entry HLA-FIX。
============================================================ -->

# QuantImmuBench — 项目 STORY / Headline 框架（QuantImmu 对齐版，2026-06-29）

> 本档是项目写作与立项的锚定文件。所有章节、claim、措辞以此为准；偏离须停下澄清。
> 数字红线：写进任何档的数字只用本档 §7 的「本地已核真源」清单；袁 md 声称值一律带「袁 md 声称值（口径待核）」标注，绝不与本地真源混排。入 tex 前一律过 verifier。DTU 工具数字标 `pending DTU consent`。对外档双盲（0 个人 / 机构 / 导师 / HPC 主机名）。

---

## 1. 论文名与 Venue

- **论文名**：**QuantImmu**（袁 md §0 候选标题 ⭐ 1：*QuantImmu: a quantitative, mutation-level framework for benchmarking and integrating neoantigen immunogenicity predictors*）。
- **主投**：**Briefings in Bioinformatics（BiB）**。BiB 偏好「系统性评估 / benchmark / problem-solving protocol」类工作，匹配本项目「系统评测 30 种工具 + 提出定量整合框架」的定位，看重公平横评与方法学严格性，不要求 radical novelty。
- **Fallback（承袭旧 STORY 双 venue 策略）**：NeurIPS Datasets & Benchmarks track（若改冲 ML 顶会），或 ML4H / MLCB workshop（门槛低、出反馈快，先拿审稿意见）。
- **全文口径**：以 **Spearman 秩相关**为主指标，**Pearson 作为附表 / 补充材料**呈现（与项目既定口径一致）。结果目标覆盖人源（ds1、ds2）与小鼠（B16F10、CT26）；小鼠数据当前仓库缺失，列 GAP（§8）。

---

## 2. 三卖点（必现于标题 / 摘要，袁 md §0）

QuantImmu 相对既有新抗原免疫原性工具与 benchmark 的三个差异化卖点，三者缺一不可：

1. **Quantitative（定量，连续强度而非二分类）**：现有主流工具把免疫原性建模为二分类（免疫原 / 非免疫原）并以 AUC 评测；但免疫原性本质是**连续强度**，临床需要的是精细排序。QuantImmu 以 ELISpot 反应（斑点数 SFC）为连续真值，用 Spearman 衡量预测分与反应强度的秩一致性。
2. **Mutation-level（突变级，而非肽–分型级）**：现有工具在「肽–等位基因（peptide–allele）」对上打分，但一个突变对应多条候选肽–HLA 行，临床决策单元是**突变**。如何把多行聚合（pooling）到突变级，是一个被忽视但关键的方法学选择。QuantImmu 把评估单元从肽–分型层提升到突变层。
3. **30-tool systematic benchmark（30 工具系统横评 = 10 呈递 + 20 免疫原性）**：现有 benchmark 多停留在二分类 / 肽层、工具数有限；缺少把大量异质工具放在**同一突变级定量口径 + 统一无泄漏协议**下比较、并研究**如何最优整合**的工作。
   - ⚠️ **本地真相**：当前仓库实测约 17 个分数源（4 呈递 / 结合 + 13 免疫原性，见 §7），距袁 md 目标 30（10+20）尚缺约 13 个。「30 工具」是投稿目标而非当前已成数；写作中工具数以实接入数为准，表 2 / 表 5 留占位逐一补齐（袁 md 附录 B to-do 第 1 条）。

---

## 3. 三贡献（对齐袁 md §1.4，逐条与标题呼应）

1. **提出 QuantImmu —— 定量评估免疫原性的统一框架（三步范式 + 无泄漏 LOPO 协议）**。三步范式：
   - **Step 1 逐行打分 + 定向（orientation）**：每条肽–HLA 行取标量并统一为「越大越免疫原」；亲和力取 `−Aff(nM)`；可选 **DAI（MT vs WT）** 两形式：相减型 `max(MT−WT, 0)`、对数比值型 `max(log₂(Aff_WT / Aff_MT), 0)`。配合逐病人归一化（min-shift + RMS，仅用病人自身特征、不碰标签 / 他人 → 交叉验证无泄漏基础）。
   - **Step 2 pooling（多行 → 突变级 1 分）**：袁 md 框架 4 法 `max / topk_w(k,α) / softmax(T) / rankdecay(γ)`（本地实测脚本 `pooling_sweep_17tools.py` 实现 8 个 pooling 算子，是袁 md 4 法的超集）。
   - **Step 3 rank-fusion（多维 rank → 综合分）**：各维在病人内转 rank 后融合（mean-rank、geomean 等）。
2. **把评估从肽–分型层提升到突变层（mutation-level），并系统刻画 pooling 这一关键步骤**。聚合键（突变定义）：人 `Patient_ID | Peptide_ID`（`mut_key`），小鼠 `27AA_Sequence_MT`。
3. **系统评测 30 种免疫原性相关工具（10 呈递 + 20 免疫原性），跨人 / 鼠数据**，给出三层完整结果与严格鲁棒性检验：单工具 max 基线 → 单工具 × pooling → 多工具 × fusion，配合 ablation、nested-LOPO、随机删 10% / 20% 鲁棒性三重检验。

---

## 4. 承重 Claim（对齐袁 md Key Points §5，数字用 §7 本地已核值）

> 措辞原则：「点估居前」不写「最优 / 最强 / SOTA」；袁 md 框架结论而本地无支撑的，明确标「袁 md 框架结论，本地实验待补」，绝不冒充本地已核。

### Claim (i)（强，本地实测支撑）—— pooling 的选择会系统性重排工具优劣

在统一突变级口径下，pooling 算子的选择会改变工具排名，且**重排方向由工具类别决定**：

- **结合 / 亲和力类 → 要聚合**（大 k、α=0 的 top-k 等权平均 / geomean，信号近翻倍）。本地已核：`netmhcpan_ba` 从 max 基线 ρ=0.0901 经 geomean 聚合升至 **ρ=0.3956**（Δ +0.3055，count-safe 最优）；`PredIG` max 0.2005 → geomean 0.3651（Δ +0.1646）；`MHCflurry_affinity_neg` max 0.128 → top3mean 0.2348。⚠️ `netmhcpan_ba` 为 DTU 工具，数字标 `pending DTU consent`。⚠️ **数字桥诚实声明**：袁 md 称 `netAffneg_9 topk(k=20,α=0) = +0.3946`，本地 `netmhcpan_ba` 最优 pooling 为 geomean 0.3956 —— 二者**数值接近但属不同 pooling 算子**（本地同一工具的 topk_w 实测仅 0.1062，远非 0.3946），数值相近纯属不同算子的巧合。袁 md 的 topk(k=20,α=0) 究竟对应本地哪个算子，**待按 k=20,α=0 重跑 topk 核实**，在此之前**不宣称袁 md 与本地存在任何已坐实的数字桥**。
- **免疫原性类（PRIME / PredIG / pTuneos 等）→ 取最强**（max 或小 top-k 即达峰）。本地已核：`pTuneos` max 即最优（ρ=0.1186，count-safe Δ=0）；`PRIME` max 0.1582 → top3mean 0.2143（小 top-k 即足）；`CNNeo` pooling 救不了（max 0.0853，Δ=0）。
- ⚠️ **去混杂规则**：`sum` 类聚合的涨幅多为肽长混杂假象，用 `|ρ(pooled, 子肽数)| > 0.5` 剔除后取 count-safe 最优值（避免肽长冒充排序能力）。`deepHLApan` 去混杂后无信号（softmax ρ=−0.0536）。
- **支撑文件**：`analysis/pooling_best_per_tool_17tools.csv`、`analysis/pooling_global_spearman_17tools.csv`。

### Claim (ii)（袁 md headline，本地实验待补）—— geomean rank-fusion 唯一通过双重检验

袁 md §3.3.4 / Key Points 主张：在多工具整合中，**geomean rank-fusion** 是唯一同时通过「跨配置（3/4/6/7 维）复现性」与「删突变（10% / 20%）鲁棒性」双重检验的整合法则（袁 md 声称 geomean 删 10% +0.4643 / 删 20% +0.4488 双双第一，而 max 满数据 +0.4834 虚高但子采样塌陷 = 点估计陷阱）。

- ⚠️ **本地真相**：本地 fusion 仅 4 法（`rankmean_surv6` / `fixavg_surv6` / `ridge_surv6` / `gbdt_surv6`，见 `analysis/fusion_methods.csv`），**无 geomean 单列、无删 10% / 20% robustness 子采样实验、无跨维复现性扫描**。袁 md 声称的 geomean 鲁棒性数字**本地完全无支撑 csv**（缺 `robustness_subsample.py` 产物）。
- **结论定性**：此 claim 为**袁 md 框架结论**，是论文方法学高潮（图 3 / 表 9），但**本地 robustness / geomean fusion 实验待补**。⚠️ **归属纠正**（与 `GAP_ROADMAP` 一致）：补齐这条所需的 **robustness 删 10% / 20% 子采样 + fusion 扩 12 法（含 geomean 单列）**，连同 nested-LOPO、ablation，全是**纯 CPU 本地实验**（操作现有 17 工具 score csv，<0.1 CPU·h、0 GPU、不需新工具部署、不需 HPC）—— 属**余嘉本窗可立即推进的最高优先（P0）**，**并非须等徐伊琳组 HPC 框架**。仅小鼠全框架（依赖缺失的鼠数据）、工具部署补齐、DTU 许可才是外部卡死项。在本地实验跑出前，本档及任何对外稿件不得把 geomean 鲁棒性数字当本地已核呈现。详见 §8 GAP 与 `GAP_ROADMAP`。

### Claim (iii)（中强，本地实测支撑）—— 整合相对最强单工具统计持平 → 按鲁棒性而非点估计部署

样本有限时，多工具整合相对最强单工具的增量在统计上持平：

- 本地已核（`analysis/fusion_vs_single_paired.csv`，best_single = `MT_deepHLApan` ρ̄=0.2519）：`fixavg` Δz=0.0037、p_two=0.974、sign_p=1.0 → **统计持平**；`rankmean` Δz=0.0399、p_two=0.833、sign_p=1.0 → **统计持平**。`ridge` / `gbdt` 转负（−0.3008 / −0.0421）= 训练类 fusion 在小样本（n=9）过拟合。
- 方向与袁 md §3.3.5 一致（袁 md 称 Δ≈+0.038、p≈0.70、主要由单一病人 P101 驱动）。
- **可操作结论**：因统计持平，部署应按「零过拟合 + 依赖最少 + 鲁棒 + 可解释」而非点估计选择。袁 md §3.4 给两条方案：务实默认 = 单 affinity pooling（`netAffneg_9 topk k=20,α=0`，仅依赖 netMHCpan、最稳）；按需备选 = 多维 free-pooling + geomean（点估计与鲁棒性双优，代价是多管线依赖）。
- **支撑文件**：`analysis/fusion_methods.csv`、`analysis/fusion_vs_single_paired.csv`、`analysis/fusion_single_floor.csv`。

---

## 5. 旧窄框架（C1 / C2 / C3）收编为 QuantImmu 框架内子结论

旧 `paper/STORY.md` 的三条 claim 不是另一篇论文，而是 QuantImmu 框架内的具体落点，收编如下：

- **旧 C1（单工具弱相关 / 天花板 ρ<0.4）→ 并入袁 md §3.1 单工具 max 基线（结果 ①）**。
  统一协议下单工具 max-pool 突变级 Spearman 普遍弱：全工具 |ρ|<0.33，天花板 ρ<0.4（四方夹逼 0.33–0.43）；全局 max 口径仅 IMPROVE（ρ=0.2518、p=0.0111，唯一双口径显著）与 PredIG（ρ=0.2005、p≈0.044）显著。HLAthena（presentation proxy，AUC≈0.51 近随机）印证「呈递 ≠ 免疫原性 ≠ magnitude」。这是 QuantImmu 三层结果的第一层基线，不是独立 claim。支撑：`analysis/metrics_ds2_16tools.csv`。

- **旧 C2（per-patient 评估协议揭示个体差异）→ 并入袁 md §2.6 evaluation protocol + §3 per-patient 主指标**。
  主指标为 per-patient 单独算 ρ_i 再聚合（Fisher-Z 加权 / median），而非全局 pool。本地已核（`analysis/per_patient_spearman_16tools.csv`，DS2 9 患者，Fisher-Z 加权）：**PRIME ρ=0.2794 [0.050, 0.481] 显著**、**IMPROVE ρ=0.2502 [0.021, 0.455] 显著**（唯二 CI 排零，IMPROVE count-safe 最稳）；PredIG ρ=0.2286（CI 含 0，边界）。⚠️ deepHLApan ρ=0.2243（CI 含 0）为**肽长混杂警示例，不作能力证据**（best-binder 下分数与肽长 ρ≈0.57，去混杂后塌到 ≈0）。这是袁 md 「评估协议 = 卖点之一」的实例化，per-patient 聚合是 QuantImmu 无泄漏协议的核心组件。

- **旧 C3（magnitude gap position framing）→ 并入袁 md Discussion §4.2 / §4.3**。
  「为什么 Spearman≈0.4 是有竞争力的信号而非弱相关」（袁 md §4.2：跨病人平均显著优于随机；神经抗原免疫原性是公认极难问题；per-patient 在 0.17–0.80 剧烈波动 → 当强力排序输入用，非唯一裁判）+ 诚实局限（袁 md §4.3：整合 vs 最强单工具不显著、设计层 selection bias 未进 CV、仅 8 有效病人、所有增量结论待外部独立队列验证）。旧 C3 的 position 叙事（magnitude 是被系统性忽视的 gap + 标签塌缩证据 + 生物学上界 ρ_max≈0.4–0.6）作为 Introduction / Discussion 的 framing 素材，服务于「为什么这个 benchmark 重要」，但 contribution 主轴是 benchmark 实测，不喧宾夺主。

> 收编原则（承袭旧 STORY 的 claim 形状纪律）：benchmark 实测是承重主轴（稳），position 叙事是 framing（拔高靠论证不靠大规模实验），避免「两头不到岸」。

---

## 6. 章节结构（对齐袁 md，BiB 投稿版）

| 节 | 内容 | 承重 / 对应 claim |
|---|---|---|
| Abstract | 4 段式（Motivation / Results / Key findings / Availability）：错配 → QuantImmu 三步框架 → 30 工具三层结果 → 三重检验 → geomean fusion + 持平部署建议 | 三卖点 + Claim i/ii/iii |
| 1. Introduction | 临床背景 + 两个错配（二分类 vs 定量、肽–HLA 层 vs 突变层）+ 第三 gap（缺统一定量横评）+ 三贡献 + roadmap | C3 framing + 三贡献 |
| 2. Materials and Methods | 2.1 数据集（人 ds1/ds2 + 鼠 B16F10/CT26）2.2 30 工具表 2.3 QuantImmu 三步范式 2.4 pooling 表 2.5 12 fusion 表 2.6 评估协议（per-patient Spearman + nested-LOPO + ablation + robustness + 配对显著性）2.7 实现 | 方法学 |
| 3. Results | 3.1 单工具 max 基线（旧 C1）3.2 单工具 × pooling 重排（Claim i）3.3 多工具 12 fusion + 三重检验（Claim ii，含 3.3.5 持平 = Claim iii）3.4 统一排名 + 部署建议 | C1 + Claim i/ii/iii |
| 4. Discussion | 4.1 方法学要点 4.2 为何 ρ≈0.4 有竞争力（旧 C3）4.3 诚实局限 4.4 future work（HLA-II + 外部队列） | C3 |
| 5. Key Points | BiB 要求 3–5 条要点（= 三卖点 + Claim i/ii/iii 收束） | — |
| 6. 常规部分 + 7. Figures & Tables + 附录 A 脚本映射 / B to-do | 投稿打包 | — |

---

## 7. 数字红线 / 禁区（写作全程守）

### 7.1 本地已核真源 csv 清单（写进任何档的数字只能来自此处）
- `analysis/per_patient_spearman_16tools.csv`（实 17 工具，命名偏旧）—— per-patient Fisher-Z 主指标。
- `analysis/pooling_best_per_tool_17tools.csv` / `pooling_global_spearman_17tools.csv` —— pooling 重排。
- `analysis/metrics_ds2_16tools.csv` —— 全局 max Spearman 基线。
- `analysis/fusion_methods.csv` / `fusion_vs_single_paired.csv` / `fusion_single_floor.csv` —— fusion 与持平检验。
- `quantimmune/results/lopo_*.csv` —— LOPO。
> 纪律（[[feedback_verify_paper_numbers]]）：数字一律 Bash / Grep 直核 csv，**禁 Read 看数据当真**（曾幻觉编造不存在的 csv）。入 tex 前过 verifier 三方对账。拿不准的写 `\todo{核 verifier}` 占位，不瞎填。

### 7.2 袁 md 声称值待核规则
袁 md 部分数字基于 **inference 子集（92 突变 / 8 有效病人）** 口径，本地无对应 csv（缺 `score_pooling_subset92_results.csv`），对不上本地 per-patient / max 值。规则：
- 这类值一律标「袁 md 声称值（口径 = 92 突变 / 8 病人 inference 子集，本地无支撑 / 待核）」，**绝不混入本地真源表**。
- ⚠️ **不存在已坐实的数字桥**：袁 md `netAffneg_9 topk(k=20,α=0) +0.3946` 与本地 `netmhcpan_ba` geomean 0.3956 **数值接近但算子不同**（本地同工具 topk_w 实测仅 0.1062）；袁 md 的 topk(k=20,α=0) 对应本地哪个算子**待按 k=20,α=0 重跑 topk 核实**，不可凭数值接近断定「对得上」。
- 完全无支撑的袁 md 数字（geomean 鲁棒性删 10% +0.4643 / 删 20% +0.4488 / max 满数据 +0.4834；§3.1 单工具 PRIME +0.286 / deephlapan_Imm +0.280 / PredIG +0.322 等）→ 标「待补实验」，见 §8。

### 7.3 DTU 许可红线
- `netmhcpan_ba`、`TSCAPE` = **pending DTU consent**（DTU 学术许可禁第三方再分发含其数字），投稿前须取书面同意。其数字一律标 `pending DTU consent`。
- BigMHC 学术非商用；TSCAPE CC BY-NC-ND；NeoTImmuML★ = 自训版（官方权重不可得），标非官方。

### 7.4 数据集口径
> 🔴 **2026-06-30 数据真源切换（红线）**：DS2 唯一标准 = 袁老师下发官方更正数据 `data/OFFICIAL_DO_NOT_TOUCH/ELISPOT_OFFICIAL_Braun2025_MOESM4.xlsx`（**只读，不可改**；Braun *Nature* 2025 MOESM4，HLA 拖拽 bug 已采纳我方修正）。旧 `Elispot_Dataset2.xlsx`（101 肽）**已废**→ `data/_archive_superseded_20260630/`。一律读官方文件。详见 `data/README_DATA_OFFICIAL.md`。
- DS2（主分析集，官方版）：两页 —— **In Vitro 130 肽 / 9 患者**（P101–P110 缺 P103）+ **Ex Vivo 36 行**（9 患者 × 4 Pool × 逐周 Week0–24，两治疗组）。⚠️ 旧 101 肽口径**作废**（旧为过滤子集；官方 In Vitro = 130 肽全量，多 29 肽 = 28 阳/1 阴；101 共有肽 Elispot 逐个一致）。⚠️ 官方版无我方旧表 5 列注释（`WT Peptide Seq` 等，DAI 命脉，需从归档旧表按 `Peptide_ID` 回贴）。
- HLA 真值（官方版已修正）：P101 `{A*66:01,B*40:01,B*57:01,C*06:02}`、P102 `{A*02:01,B*35:03,B*38:01}`（确认仅 3 等位）。
- ⚠️ **口径拍板点**：官方 130 肽 vs 袁 md「92 突变/8 病人」vs 旧「101 肽/9 患者→7 有效」三套不一致 → 投稿前需袁老师/朱同学统一。
- ⚠️ **现有结果待重跑**：`analysis/metrics_ds2_*` / `per_patient_spearman_*` / pooling / fusion 全部基于旧 101 肽口径，需在官方 130 肽上**重跑才生效**（改 paper 数字，已由用户 2026-06-30 授权方向）。
- DS1（`data/Elispot_Dataset1.xlsx`，6 例黑色素瘤）= 人源补充 / 复现集（官方更正版只含 DS2，DS1 独立保留）。
- 小鼠 B16F10 / CT26：**仓库完全缺失**（袁 md §2.1 要求），列 GAP。

### 7.5 双盲
对外档（GAP_ROADMAP / ALIGNMENT / 投稿稿件）0 个人 / 机构 / 导师 / HPC 主机名。本档为内部 STORY，人名可保留于 §10 团队分工，但不得写进任何会对外的措辞。

### 7.6 引用修正（承袭旧 STORY，researcher 2026-06-26 核）
- explorationpub = **2023**（非 2024）；NetTepi = **Trolle & Nielsen, Immunogenetics 2014**（非 Andreatta / NAR）。
- explorationpub 三句逐字引未证实 → 转述去引号。
- 「CD8 magnitude 独立 TMB」无 canonical 出处 → 降档「T 细胞 breadth 关联复发延迟」+ 引 Sahin BNT122 Nature 2023。
- NeoPepDB 不存在（= NEPdb 笔误）；neoIM 专有不可纳入；「Nature Cancer 2025 reproducibility crisis」疑幻觉，勿引。

### 7.7 不夸大原则
- 「点估居前」不用「最优 / 最强 / SOTA」；每个 ρ 配 p-value / CI；承认生物学上界（precursor frequency 封顶 ρ_max≈0.4–0.6）；position claim 主动对冲对立假设（「没人做」既是机会也可能是「没人做得动」）。
- **投稿 = 拍板点**：做到 submission-ready 草稿即停，呈用户拍板，绝不擅自投稿 / 对外发布。

---

## 8. GAP / 待补（袁 md 承诺 vs 本地现状，详见 GAP_ROADMAP）

| 袁 md 承诺 | 本地现状 | 缺口 |
|---|---|---|
| 30 工具（10 呈递 + 20 免疫原性） | 实测约 17（4 呈递结合 + 13 免疫原性） | 缺约 13（呈递 ~6 + 免疫原 ~7；MHLAPre 权重缺彻底阻塞） |
| 12 种 fusion | 本地仅 4 法（rankmean/fixavg/ridge/gbdt） | 缺 geomean / median / powmean / softmax-rank / stacking / constrained 等 8 法 |
| robustness 删 10% / 20% 子采样（图 3 核心，Claim ii 支撑） | **完全无** | 缺 `robustness_subsample.py` 产物 → Claim ii 本地无支撑 |
| nested-LOPO 双层（内层选超参） | 仅单层 LOPO（`quantimmune/lopo_eval.py`） | 缺内层超参选择 |
| ablation（维度留一 + 加权） | 无 | 缺 |
| 小鼠 B16F10 / CT26 全框架 | 数据 + 脚本 0% | 数据组 + `camp.py` 等 |
| 部署脚本（rank_T01_deploy 等） | 无 | 缺 |

> 这些缺口分两类，归属须分清（与 `GAP_ROADMAP` 一致）：
> - **余嘉本窗纯软件可立即推进（P0，最高优先）**：nested-LOPO 双层、ablation（维度留一 + 加权）、robustness 删 10% / 20% 子采样、fusion 扩 12 法（含 geomean 单列）—— 这四类全是**纯 CPU 本地实验**，操作现有 17 工具 score csv，<0.1 CPU·h、0 GPU、不需 HPC、不需新工具部署。**它们是图 3 核心证据（Claim ii）的本地证据来源，不应误搁置等徐伊琳组。**
> - **外部卡死项**：小鼠 B16F10 / CT26 全框架（依赖缺失的鼠数据，数据组）、30 工具补齐（工具部署组）、DTU 许可（袁老师拍板）、部署脚本与小鼠协议（框架部署组）。
> 本档承重 claim 严格区分「本地已核」（Claim i / iii、旧 C1 / C2）与「袁 md 框架结论待本窗本地补」（Claim ii、geomean 鲁棒性）。

---

## 9. 关键数字速查（已核 csv，2026-06-29）

**per-patient Fisher-Z 主指标（DS2 9 患者）**：PRIME 0.2794 [0.050,0.481]✓ / IMPROVE 0.2502 [0.021,0.455]✓ / PredIG 0.2286(CI含0) / deepHLApan 0.2243(混杂警示) / MHCflurry_aff_neg 0.2027 / 余 ≤0.16 不显著。

**全局 max Spearman（DS2 n≈101）**：IMPROVE ρ=0.2518 p=0.0111（唯一双口径显著）/ PredIG ρ=0.2005 p≈0.044 / 天花板 ρ<0.4。

**pooling 重排（max → count-safe 最优）**：netmhcpan_ba 0.0901→geomean 0.3956(DTU) / PredIG 0.2005→geomean 0.3651 / IMPROVE 0.2518→top3mean 0.3227 / PRIME 0.1582→top3mean 0.2143 / pTuneos 0.1186→max 0.1186 / CNNeo 0.0853→max 0.0853 / TSCAPE −0.1386(DTU,负)。

**fusion vs 最强单（best_single MT_deepHLApan ρ̄0.2519）**：fixavg Δz=0.0037 p=0.974 持平 / rankmean Δz=0.0399 p=0.833 持平 / ridge −0.3008(过拟合) / gbdt −0.0421。单工具地板：MT_deepHLApan 0.2519 / MT_IMPROVE 0.2499 / MT_PRIME 0.2482。

---

## 10. 团队分工（内部背景，不入对外稿）

余嘉 = 工具部署测试（前 5 工具核心 + 超额 Wave3）；李紫晨 = 后 5 工具；徐伊琳 = QuantImmu 框架 HPC 部署；王子源 / 谢孟翰 = 数据收集（含小鼠）；朱同学 = pooling 研究原创（本地 pooling / fusion 整合源自其发现）；袁老师 = 框架定稿 + 数据组统筹。
