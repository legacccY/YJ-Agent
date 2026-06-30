# QuantImmuBench — Run-Once 严谨实验 + 消融 阶段计划

> **建档**：2026-06-30 ｜ **状态**：Phase 0 待启 ｜ **投稿**：Briefings in Bioinformatics
> **服务**：QuantImmu 三步框架全篇（逐行打分 → pooling → rank-fusion），覆盖论文表 5–10 + 图 1–4 + 三重检验 + 全部消融，对齐 `02_ACCEPTANCE.md` G1–G8。
> **铁律**：一次跑出可直接进论文的数据，零返工；不允许降级，只允许找新方法。
> **读档前置**：`paper/QuanImmu-Paper-Outline.md`（袁老师权威大纲）→ `02_ACCEPTANCE.md` → `reference/GAP_ROADMAP_vs_outline.md` → 本文件。

---

## 0. 本阶段为什么存在（Context）

项目已推进到「论文严谨实验」阶段：要一次性产出全部表/图/三重检验/消融的 paper-ready 数据。返工代价极大（30 工具 × 9 患者 × 多算子矩阵），故所有易返工的设计决定必须在跑前冻死。

**决定性地基变更（2026-06-30）**：唯一准则 ground-truth 数据换为新 RCC 肾癌新抗原疫苗数据
`data/OFFICIAL_DO_NOT_TOUCH/ELISPOT_OFFICIAL_Braun2025_MOESM4.xlsx`（Braun 2025 MOESM4）。
- **禁用旧 `Elispot_Dataset2.xlsx`，禁自行改数据。**
- 整条分析链 ground truth 换桩 → 30 工具预测 / 聚合键 / HLA 全部从新 xlsx 重建。这是 run-once 第一道工序，也是最大返工风险源。

**已拍板 scope**：人类数据全软件先跑满（鼠 B16F10/CT26 缺数据，列独立 gated 子阶段，不阻塞本阶段）；全 30 工具跑（DTU 5 工具结果标 pending consent 但进分析）；单窗 + Conductor DAG 驱动（不开多窗——Phase 0 是硬串行冻结闸，多窗并写冻结表会砸零返工目标；补跑是增量非全量）。

---

## 1. 已 Bash 自核的硬地基（authoritative，非转述）

| 事实 | 值 | 核验方式 |
|---|---|---|
| 官方真源 | `data/OFFICIAL_DO_NOT_TOUCH/ELISPOT_OFFICIAL_Braun2025_MOESM4.xlsx`（52KB） | ls + openpyxl |
| 分析单元 | Sheet「In Vitro」**130 肽 / 9 患者**（101,102,104-110，缺 103） | openpyxl 计数 |
| 每患者肽数 | 101:12 / 102:8 / 104:17 / 105:19 / 106:16 / 107:12 / 108:15 / 109:16 / 110:15（全 ≥8）→ per-patient Spearman 9 患者全可用无 NaN | openpyxl |
| ground truth | `Elispot` 列（连续 SFC，−33.7~392.3）；**118 阳 / 12 阴**（极不平衡） | openpyxl |
| 混杂变量 | `Treatment`(Vaccine+ipi 72/alone 58，患者级恒定) / `Variant_Type`(SNV 101/DEL 23/INS 5) / `TPM` / `CCF` / `Clonal` / `Mutation_type` | openpyxl |
| **🔴 头号返工风险** | 新 130 肽里 **29 肽在最新预测 `scripts/out/merged_all_tools_29tools.xlsx`（183 键）中完全缺失**；缺的含全数据 **top-10 应答者 6 个**（最强 392.3/376.3）。silent dropna → 退回旧肽子集，Spearman 系统性偏低 | 集合差自核 |
| **HLA 新旧比对** | **8/9 患者一致**，仅 **P104 DIFF**（新 A3001 vs 旧 A0301）。P101/P102 已 match（旧已 HLA-FIX） | 逐患者 HLA 集对比 |

**补跑量判定 = 增量（非全量）**：① 29 缺失肽 × 30 工具（全无预测）；② P104 的 17 肽 × 新等位 A3001（旧 A0301 预测作废）。合计 ~46 肽规模。NeoaPred（结构工具，GPU 慢）走 HPC 单卡，其余 CPU 工具本地扇出。

**可复用脚本骨架**（输入全换新冻结表）：`analysis/pooling_sweep_17tools.py`（8 算子）、`analysis/fusion_12methods.py`（12 法含 geomean）、`quantimmune/nested_lopo_ensemble.py`（外/内层+oracle）、`quantimmune/lopo_eval.py`（Fisher-z）。**新写**：`robustness_subsample_official.py`（删 10/20% × 30 seed，当前缺）。

---

## 2. QuantImmu 三步框架（实验必须覆盖每步）

- **Step 1 逐行打分 + 定向**：每条肽–HLA 行取标量，统一为「越大越免疫原」；亲和力取 `−Aff(nM)`；逐病人归一化（min-shift + RMS：`y=x−min`，`y/√mean(y²)`，仅用病人自身特征 → 无泄漏）。可选 DAI（MT vs WT）：相减型 `max(MT−WT,0)` / 对数比值型 `max(log₂(Aff_WT/Aff_MT),0)`。
- **Step 2 pooling（多行 → 肽级 1 分）**：四法 `max / topk_w(k,α) / softmax(T) / rankdecay(γ)`，本地 8 算子超集。生物假设：结合/亲和类要聚合（大 k 等权近翻倍）、免疫原类取最强（max/小 topk 即峰）。
- **Step 3 rank-fusion（多维 rank → 综合分）**：各维病人内转 rank，再融合（mean-rank / geomean 等），扩至 12 法含 **geomean 单列**。

---

## 3. Phase 0 — 数据地基重建协议（硬串行前置，一切实验依赖）

### 3.1 冻结的设计决定

- **分析单元（主）= 肽级 n=130**，键 `Patient_ID|Peptide_ID`。理由：ELISpot 逐 Vaccine_Peptide 测；旧管线 + 大纲聚合键即 peptide-keyed；9 患者全 ≥8 肽无 NaN。
- **突变级 collapse**（by `Patient_ID|Gene_and_Protein_Change`，113 突变里仅 13 个 >1 肽，100/113 本就单肽）→ 入附录，**列拍板点**（ELISpot 跨重叠肽聚合规则需袁/朱定，默认暂 max 标 `\todo`）。卖点措辞诚实改：「聚合子肽×HLA 到被试肽层」≠「折叠多肽到突变」（后者本数据 88% 不发生）。
- **Step 2 pooling 轴** = 每条长肽在 Vaccine_Peptide 上滑窗短表位（主 9AAonly / 补 8-11mer）× 该患者 HLA-I 等位（去重 ≤6）→ 工具对每 (短表位,HLA) 打分 → pool 到肽级 1 分。

### 3.2 工序（严格顺序，产物冻结到 `data/frozen/`，每步带校验门）

| 序 | 工序 | 输出冻结产物 | 校验门 |
|---|---|---|---|
| **P0-0** | 逐患者 HLA 新旧比对（已做：8 OK / P104 DIFF） | 重跑名单 = 29 缺失肽 + P104×A3001 | <5min，已确认增量 |
| P0-a | GT 表构建（从官方 xlsx） | `ds2_official_groundtruth.csv` | 行数==130、Elispot 非空==130、阳118/阴12、患者集对 |
| P0-b | HLA 格式转换 + 校验 | `patient_hla.csv`（B5701→HLA-B\*57:01，去重，仅 A/B/C） | 正则匹配、P109 去重、人工抽核 P101/P102/P104 |
| P0-c | 子肽 × HLA 展开 | `subpep_hla_expansion.csv`（主 9mer / 补 8-11mer） | 每 Peptide_ID ≥1 行、无空 seq |
| P0-d | 工具预测对齐（**含补跑 29 缺失肽 + P104×A3001**） | `merged_all_tools_30_official.csv` + 每工具缺失率列 | **fail-loud**：缺失率>0 即停、禁 silent dropna；每工具每肽 ≥1 非 NaN 子肽行 |
| P0-e | pooling 到肽级 | `pooled_peptide_level_30tools.csv` + `n_subpep` 列 | round(8) 后算、count 混杂诊断列就位 |
| P0-f | provenance 冻结 | `PROVENANCE.json`（xlsx sha256 / 行数 / 工具版本 / 规则 / 复用清单） | sha256 锁官方 xlsx |

### 3.3 工具预测「复用 vs 重跑」判定法（P0-d 核心）

工具预测 = (短表位序列, HLA 等位) 的确定性函数 → 建缓存逐对判定：
1. 从旧 29-tool 原始表抽 `(subpep_seq, HLA_allele, tool, score)` 建 `cache_old`。
2. 新展开每个 (seq, HLA)：命中且 HLA 未变 → **复用**；未命中（29 新肽/新长度）→ **重跑**；HLA 变更患者（P104）→ 该患者该等位全部 **重跑**。
3. 输出 `REUSE_DECISION.csv`（逐患者 × 工具标 reuse/rerun/partial）。
4. 保守缺省：HLA 变更患者全重跑。

### 3.4 Phase 0 paper-ready 验收

6 冻结 csv + PROVENANCE 全过行数门；**肽行覆盖==130（fail-loud 守行不守列：禁 silent dropna 整肽）**，工具列暂缺标显式 `pending` + 覆盖率表记账（不 silent NaN）；per-patient 试算 9 患者全非 NaN；count 混杂格全标；P101/P102/P104 HLA 抽核正确；官方 xlsx sha256 锁定。冻结表分层 v1（已落地工具）→ v2（NeoaPred 补列），分析先在 v1 跑、不卡。

---

## 4. 实验矩阵（R1–R9）

输入全 = Phase 0 冻结表；输出写 `analysis/official/`（**不覆盖旧 DS2 csv**）。
主指标 = **per-patient Spearman（Fisher-z 加权 9 患者等权）+ 95%CI**，round(8) 后算；全局 max + Pearson 入补充。

| run | 表/图 | 被试变量 | 控制（固定） | seed | 预期 | 判据 |
|---|---|---|---|---|---|---|
| **R1** | 表5/图1 | 30 工具 max-pool 基线 | pooling=max，肽级 n=130 | 确定性 | 免疫原类领先 ρ≈0.2-0.32，亲和类 max 垫底，天花板 <0.4 | G1,G5 |
| **R2** | 图2（核心洗牌） | 30 工具 × 8 pooling 算子（+敏感网格） | 肽级，count-safe 选优（>0.5 剔） | 确定性 | pooling **重排**：亲和类大 k 等权近翻倍，免疫原类 max 即峰 | Claim(i),G4 |
| **R3** | 表6 | 12 fusion 法 × {3,4,6,7}维 | LOPO per-patient，病人内转 rank | 学习型 seed=0 | geomean 跨维一致居前，**geomean 单列**，学习型不稳 | Claim(ii),G4 |
| **R4** | 表7 | (a)维度留一 (b)4 加权方式 | fusion=geomean & mean-rank | 确定性 | 找最承重维；**加权塌回等权**（实证不照搬） | G3 |
| **R5** | 表8 | nested-LOPO 整合 vs 最强单 | 外层留病人 / 内层选 θ | seed=0 | LOPO ρ̄ ≈ oracle ρ̄（零过拟合），增量小 | G3 |
| **R6** | 图3/表9（核心） | fusion 法 × {删10%,删20%} | 7 维，比均值/中位/胜率 | **30 seeds {0..29}** | geomean 双居前；max 满数据虚高但子采样塌；跨维唯一稳 | Claim(ii),G3,G5 |
| **R7** | §3.3.5 | 每对方法配对显著检验 | 配对单元=病人(n=9) | bootstrap seed=0 | 整合 vs 最强单 **统计持平**，逐处标持平/显著 | G6 |
| **R8** | 图4/表10 | 全方法统一排名 + 部署建议 | 肽级 n=130 统一口径 | 继承 | 排名 + 两部署方案（务实=单 affinity pooling / 按需=geomean） | G6 |
| **R9** | 补充 | Pearson / 逐病人分布 / mw / ds1 | 各自口径 | 30 seed | Pearson 与 Spearman 同呈、9AAonly 优于可变窗、ds1 mean-rank 类不复现 | G5,G7 |

图1=R1 可视化 / 图2=R2 洗牌（核心）/ 图3=R6 鲁棒性（核心）/ 图4=R8 排名 / 图5=三步范式 schematic（无数字）。

---

## 5. 消融矩阵（AB-1..AB-11，纯 CPU，可与 R1-R9 同批并行）

| ab | 轴 | 档位 | 挂 | 用途 |
|---|---|---|---|---|
| AB-1 | pooling 算子 | 8 算子 + 敏感网格（softmax T∈{.03..2} / topk_w k∈{1..100}×α∈{0,.5,1,2} / rankdecay γ∈{1..20}） | 表3/R2 | 算子敏感度 |
| AB-2 | fusion 法 | 12 法 | 表6/R3 | geomean 跨维一致 |
| AB-3 | 维度留一 | 逐维去除 | 表7/R4 | 最承重维 |
| AB-4 | 加权方式 | 等权 / 4 加权（按 ρ / CI / 1-var / softmax-ρ） | 表7/R4 | **塌回等权** 实证 |
| AB-5 | 归一化 | min-shift+RMS(主) / z-score / 纯 rank / 不归一 | 补充 | 对归一化稳健 |
| AB-6 | DAI 开关 | off / 相减 / 对数比值 | 补充 | Step1 定向消融 |
| AB-7 | **Treatment 分层** | 全130 / alone58 / ipi72 | 补充 | 排疗法混杂（新数据特有，主动加） |
| AB-8 | Variant_Type 分层 | 全 / SNV-only 101 | 补充 | 排 INDEL 影响 |
| AB-9 | 分析单元 | 肽级130(主) / 突变 collapse | 补充/**拍板点** | collapse 是否改结论 |
| AB-10 | 窗口口径 | 9AAonly(主) / 可变窗 8-11mer | 补充 | 9AAonly 优于可变窗实证 |
| AB-11 | count 混杂剔除 | 开（剔>0.5）/ 关 | R2 全程 | sum 涨幅多为肽长假象 |

---

## 6. Run-Once 冻结清单（跑前锁死，改一项 = 全重跑）

**数据口径**：官方 xlsx sha256 锁；分析单元肽级 n=130（突变 collapse 待拍板）；9 患者 min_pep=3（保留 NaN 守卫）；GT=Elispot **连续 SFC，负值不 clip、不二值化**；键 `Patient_ID|Peptide_ID`。
**HLA/展开**：B5701→HLA-B\*57:01，去重，仅 A/B/C；主 9AAonly / 补 8-11mer；重跑名单 = 29 缺失肽 + P104×A3001。
**指标/检验**：per-patient Spearman Fisher-z（clip .9999，min_n=3）9 患者等权 + 95%CI；**round(8) 后算**；count 阈值 0.5；**不确定性主用 bootstrap-over-patients CI**（重抽 9 患者），Fisher-z 解析 CI 对照；ρ_i 必并列 n_i；AUC 仅补充、阈值锁 Elispot>0、标注 n_neg=12 不进 headline；配对检验=病人(n=9) bootstrap + sign test（Δz/p_two/sign_p）。
**多重检验**：预登记对排名做 FDR(BH)，headline 单点 Bonferroni；发现一律用「跨子采样 win-rate 方向一致」而非单次 p<0.05。
**fusion 胜出判据预登记（不预焊 geomean headline）**：某法须「点估计 ndim-中位 AND 子采样 win-rate 双榜领先」才称 dominant，否则报「无单一 fusion 主导，按鲁棒性推荐稳健默认」。**承重 headline 落 Claim iii**（整合 ≈ 最强单工具、按鲁棒性部署，无论 geomean 怎么跳都成立）。
**算子/法集 / 许可**：pooling/fusion 超参集冻结；30 工具清单（DTU 5 标 pending consent；自训/proxy 标注）；ceiling 用生物学上界叙事（ρ_max≈0.4-0.6）**不臆造数值**。

**查不到的官方超参标 TODO 绝不臆想**：
- `TODO researcher/朱`：topk_w 的 α 与袁 md `topk(k,α)` 算子映射（旧 topk_w 0.1062 ≠ 袁 0.3946，不宣称数字桥）。
- `TODO 朱`：powmean p / softmax_rank T / stacking meta 特征 / constrained 约束确切形式。
- `TODO researcher`：nested-LOPO 内层 Ridge alpha grid / dof_target 官方依据。

---

## 7. 约束 / 限制 / 拍板点（停下报，不自决）

1. **分析单元 + ELISpot collapse 口径**（影响所有表 n/分母）→ 袁/朱定（默认肽级 n=130）。
2. **维度集定义**（3/4/6/7 维含哪些工具，旧建在 17 工具，新 30 工具须重定）→ 朱/袁对账。**本设计最大不确定源，跑前必须冻结。**
3. **DTU consent**（G8，netmhcpan_ba/TSCAPE/netMHCstabpan/ICERFIRE/NetTepi）→ 袁老师书面同意，否则撤/替换数字。
4. **30 工具是否真达标**（G1，当前 29 缺 1）→ 不到则文中诚实写「N 工具」。
5. **geomean headline 复现性**：若 R6/R3 跑出 geomean 非「唯一双检验通过」→ 回退 §3.3.4-5，停下报，不照搬袁 md +0.4643/+0.4488。

### 返工根因前置堵死（5 条已知坑 + skeptic 3 致命）

| 坑 | 堵法 |
|---|---|
| count 混杂（sum 96% 由子肽数定） | P0-e 产 n_subpep + AB-11 + 阈值 0.5 逐格诊断 |
| 浮点 tie 不稳（升降序 ρ 不一致） | 冻结 round(8) |
| HLA 伪迹（旧 P101/P102 等位错） | 官方真源重建 + P0-b 抽核 + P104 强制重跑 |
| 无泄漏 | per-patient 归一化只用自身 + LOPO 留病人 + nested 外/内隔离 + selection bias 诚实进 Limitations 不删 |
| n_i<min_pep | NaN 守卫保留 |
| **🔴 29 缺失肽（含 top 应答者）** | P0-d 补跑 + fail-loud join（缺失率>0 即停） |
| **🔴 118/12 不平衡** | Spearman 连续主指标、AUC 降附表、阈值锁 >0 标 n_neg=12 |
| **🔴 Treatment 混杂** | per-patient 天然免疫；global-pool 数字加分层、不进 headline |

---

## 8. 依赖顺序 + 并行块 + 算力

```
Phase 0（硬串行前置）: P0-0 HLA比对(已做) → P0-a→b→c→d(补29肽+P104+fail-loud)→e→f 冻结
   └─ 冻结后纯 CPU 一次并行扇出（Conductor DAG）─┐
      块A(单工具): R1, R2, AB-1, AB-10, AB-11
      块B(多工具,依赖维度集冻结): R3, R4, R5, R6(30seed), AB-2
      块C(消融/补充): AB-5..9, R9
   └─ B/C 完成 → R7 配对显著(依赖 R3/R5/R6) → R8 统一排名(依赖 R1-R6)
   └─ 图1-4(coder 出图,依赖对应 csv) → verifier 核关键值
```
- **串行红线**：Phase 0 先冻结；R7/R8 依赖上游 csv。R1-R6 + 全 AB 在 Phase 0 后一次并行（各写独立 csv 无冲突）。
- **算力**：R1-R9 + AB 分析侧合计 **<1 CPU·h，本地一次跑完，零 GPU**。Phase 0 工具补跑（增量 ~46 肽）：NeoaPred 走 `gpu_slot.py` 申 HPC 单卡，其余 CPU 工具本地扇出；**上传新数据/代码 = 拍板先报**。

### 8.1 不卡执行策略（本地优先 / HPC 不等）— 用户硬约束

**目标**：任何一步都不空等。该本地就本地，HPC 工具后台跑、绝不阻塞主分析链。

1. **本地优先补跑**：29 缺失肽 + P104×A3001 的工具补跑，所有 CPU 工具（多数免疫原工具 DeepImmuno/PredIG/IMPROVE/PRIME/pTuneos/IEDB_Calis… + CPU 呈递工具 MHCflurry/MHCnuggets…）**立即本地扇出跑完**，不排队不申卡不等。
2. **HPC 工具后台非阻塞**：NeoaPred（唯一真慢的 GPU 结构物理工具，曾 HPC TIMEOUT）`gpu_slot.py` 申卡后**后台跑**，主线**不 sleep 守、不等它回来**就往下推。
3. **fail-loud 的正确语义（关键澄清）**：fail-loud 守的是「**肽行 100% 覆盖，禁 silent dropna 整肽**」= 数据完整性。**工具列暂缺 ≠ 肽缺**：某工具列用显式 `pending` 状态 + 覆盖率表记账，不是 silent NaN。两者不冲突——肽必须全，工具可分批落地。
4. **冻结表分层 + 增量解锁**：`merged_all_tools_30_official.csv` 先用「已落地工具子集」冻 `_v1`，R1-R9 分析**立即在 v1 上跑出可用结果**（<1 CPU·h 本地）；NeoaPred 回来后增量补列冻 `_v2`，**只重跑涉及该工具的格**（R1 该工具行、R3 含该维的 fusion），不全表重跑。
5. **NeoaPred 不回的兜底**：若 HPC 最终超时/不回 → 按 §7 拍板 4「30 工具是否达标」诚实处理：用 29 工具发、NeoaPred 标 future，**绝不卡论文**。不预设降级话术，但路堵死时诚实降不硬等。

---

## 9. 每 Run 的 paper-ready 验收（满足即直接进论文不返工）

- **Phase 0**：见 §3.4。
- **R1**：30 工具（或诚实 N）各一肽级 ρ+CI 源自冻结 csv，verifier 核 ≥2 值。
- **R2**：每工具 max vs count-safe 最优 Δ，混杂格标，重排方向成立。
- **R3**：12 法 × 4 维全填、**geomean 单列在**、每值 CI、学习型 LOPO 无泄漏标注。
- **R4**：最承重维 + 加权 vs 等权结论（实证塌回或反例诚实）。
- **R5**：LOPO ρ̄ 与 oracle ρ̄ 两列 + 一致性陈述 + 整合 vs 最强单读数。
- **R6**：删10/20%×30seed 均值/中位/胜率三列，geomean 双居前或诚实回退，跨维复现性判定明确。
- **R7**：每「最优/第一」配 p 值 + 持平/显著，整合 vs 最强单持平实证。
- **R8**：统一排名 + 两部署方案，口径与全文一致。
- **R9**：Pearson/逐病人/mw/ds1 不复现诚实呈现，同口径。
- **全局闸**：数字 Bash/Grep 直核冻结 csv（不信 Read），入 tex 过 verifier；DTU 标 pending consent；对外稿双盲；未拍板处 `\todo` 不选边。**大阶段收口跑 `/stage-gate quantimmu-bench`** 让 reviewer 对 G1-G8 严判 PASS/FAIL。

---

## 10. 交接

- **→ coder**：Phase 0 六步脚本（重点 §3.3 复用判定 + HLA 转换 + 子肽×HLA 展开 + 30 工具对齐，复用旧 `merge_metrics`/`pooling_sweep_17tools`/`fusion_12methods`/`nested_lopo_ensemble` 骨架但输入换冻结表）；R1-R9 + AB 跑批脚本；**新写 `robustness_subsample_official.py`**；图1-4。写完交主线/HPC 跑，不自启训练。
- **→ 主线**：Phase 0 工具补跑若需 NeoaPred GPU → `gpu_slot.py` 申卡（HPC 优先）；上传新数据/代码先报拍板。
- **→ researcher/朱**：§6 前置 TODO（算子映射 / fusion 超参 / 维度集 / 内层 grid）。
- **→ analyst**：R6 跨维复现性 + R7 持平解读，判 geomean 是否真「唯一双检验通过」。
- **→ verifier**：每表 ≥2 关键值核冻结 csv。
- **→ 袁老师/朱（拍板）**：§7 五个拍板点，尤其拍板 1（分析单元）+ 拍板 2（维度集）跑前必须对齐冻结。
