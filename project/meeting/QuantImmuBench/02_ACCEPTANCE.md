# 02_ACCEPTANCE — QuantImmu 投稿达标判据（BiB）

> **本档目的**：把袁老师论文大纲（`paper/QuanImmu-Paper-Outline.md`，权威框架）附录 B「投稿前 to-do」+ 全文 §2.6 evaluation protocol / §7 Figures & Tables / §4.3 Limitations 的要求，逐条转成**可验收的达标判据（gate）**。每个 gate = 判据 + 当前状态 + 可验收门槛（文件/数字/表图级，拒绝「基本完成」） + 建议归属。
>
> **服务声明**：服务 QuantImmu §投稿达标判据；lever = 把袁 md 要求转可验收 gate。与权威框架冲突即停、报告，不照写。
>
> **数字纪律（红线）**：本档所有「当前状态」引用的数字，**只用 `_scratch/ALIGN_FACTS.md` 已核值**（主线 2026-06-29 Bash 直核 csv 产出）。袁 md 声称值（口径 = 92 突变 / 8 患者 inference 子集）一律标注「袁 md 声称值（本地无支撑 / 待核）」，绝不与本地真源混表。拿不准的数字写 `\todo{核 verifier}` 占位。
>
> **状态图例**：✅ 达标 / ⚠️ 部分达标或有阻塞待解 / ❌ 未做或缺失。
>
> **真源 csv（不改）**：`analysis/per_patient_spearman_16tools.csv`（实 17 工具，命名偏旧）、`pooling_best_per_tool_17tools.csv`、`pooling_global_spearman_17tools.csv`、`metrics_ds2_16tools.csv`、`fusion_methods.csv`、`fusion_vs_single_paired.csv`、`fusion_single_floor.csv`、`quantimmune/results/lopo_*.csv`。

---

## 总览：8 个 gate 状态速览

| Gate | 主题 | 当前状态 | 阻塞 / 拍板点 |
|---|---|---|---|
| G1 | 工具补齐至 30（10 呈递 + 20 免疫原性） | ❌（当前 17 = 4 呈递 + 13 免疫原性） | 缺 13 工具；MHLAPre 彻底阻塞 |
| G2 | 四数据集口径统一（人 ds1/ds2 + 鼠 B16F10/CT26） | ❌（鼠数据缺、nested-LOPO 缺） | **口径冲突 = 投稿前拍板点**（见 G2） |
| G3 | 三重严格检验齐全（nested-LOPO + ablation + robustness） | ❌（全缺或仅部分等价物） | robustness 删 10/20% 无 csv |
| G4 | fusion 扩至 12 法 | ⚠️（当前 4 法，无 geomean 单列） | 缺 8 法 + 跨维复现性判定 |
| G5 | 主指标 Spearman + 全量 Pearson 补充 | ⚠️（Spearman 主指标已有，补充材料不全） | 缺 mw / ds1 / 30 seed / 逐病人分布 |
| G6 | 显著性诚实呈现 | ⚠️（本地已核持平 p 值，但论文措辞未写，未达「已成文诚实呈现」） | 写作时每个「最优」必旁注 |
| G7 | 外部验证表态 + HLA-II 仅 future work | ⚠️（大纲已含，待成文落实） | HLA-II 不得进 Results |
| G8 | 许可 / 双盲合规 | ⚠️（DTU 工具数字 pending consent） | **DTU 书面同意 = 投稿前拍板点** |

---

## G1 — 工具补齐至 30（10 呈递 + 20 免疫原性）

**判据（袁 md 附录 B-1、§2.2 表 2、§3.1 表 5）**：清单补齐到 **10 种呈递预测 + 20 种免疫原性预测 = 30**，填袁 md 表 2（工具清单）与表 5（单工具 max 基线）。

**当前状态**：⚠️/❌ — 本地实测 **17 工具（4 呈递 + 13 免疫原性）**，距 30 缺 13。
- 呈递 / 结合类（4，已核）：`netmhcpan_ba`（DTU）、`MHCflurry_presentation`、`MHCflurry_affinity_neg`、`HLAthena`（presentation proxy，AUC≈0.51 近随机，单列不计主榜）。
- 免疫原性类（13，已核）：DeepImmuno、PredIG、IMPROVE、NeoTImmuML（★自训版，非官方）、pTuneos（Pre&RecNeo 子模型）、PRIME、ImmuneApp、deepHLApan、BigMHC（-m=im）、CNNeo（自训）、IEDB_Calis、Repitope、TSCAPE（DTU）。
- 缺 13：呈递缺 ~6（netMHCpan Aff/EL 独立列、MAAP、NetMHCstabpan 独立预测列、BigMHC_EL 等）；免疫原缺 ~7（Seq2Neo、DeepNeo/DeepNeo-v2、ICERFIRE（DTU pending）、内部 Inference 8-class、NeoaPred（HPC pending）等）。
- **彻底阻塞**：MHLAPre（权重缺，唯一无法部署）。已放弃：ImmunoStruct（三重 blocker，NO-GO）。

**可验收门槛**：
1. 表 2 中呈递类条目 = 10、免疫原性类条目 = 20（合计 30），无占位空行；若投稿前确实无法达 30，则在方法节明文写「接入 N 工具」并把 30 改为实际数（**不得在文中称 30 而表内 < 30**）。
2. 表 2 每行齐备 5 个属性列：**输出分名 / 原生任务（二分类·连续·概率）/ 是否提供 MT-WT / 9mer vs 可变窗 / 引用文献**。
3. 表 5（max 基线）覆盖表 2 全部工具，每工具一个突变级 Spearman 值（max-pool 下 LOPO==oracle==均值），数字源自本地 csv 或新跑 csv，禁臆造。
4. 自训 / proxy 工具（NeoTImmuML★、CNNeo、HLAthena proxy）在表内显式标注非官方 / 代理性质。

**建议归属**：余嘉（已部署核心 + Wave3）+ 李紫晨（后 5 工具）补缺口部署；MHLAPre / DTU pending 工具的取舍由袁老师拍板。

---

## G2 — 四数据集口径统一（人 ds1/ds2 + 鼠 B16F10/CT26）

**判据（袁 md 附录 B-2、§2.1 表 1）**：四个数据集（人 ds1、人 ds2、鼠 B16F10、鼠 CT26）**全部跑通同一三步范式（逐行打分 → pooling → rank-fusion）+ nested-LOPO**，避免口径不一致，结果落表 1（数据集汇总）。

**当前状态**：❌ — 仅人 ds2（主分析集）跑通三步范式；nested-LOPO 缺（仅有单层 LOPO 等价物）；鼠数据缺失。
- 人 DS1：`data/Elispot_Dataset1.xlsx`（16KB，6 例黑色素瘤）✅ 干净，袁 md = netMHCpan+PRIME 合并补充/复现集。
- 人 DS2（主分析集）：`data/Elispot_Dataset2.xlsx`（29KB，HLA-FIX 修正版）✅ 已跑。
- 鼠 B16F10 / CT26：❌ 仓库完全缺失（袁 md §2.1 要求）。
- nested-LOPO：❌ 缺双层；本地仅 `quantimmune/lopo_eval.py` 单层（见 G3）。

> **⚠️ 投稿前拍板点（口径冲突，必须袁老师 / 朱同学统一）**：
> - **袁 md 声称口径**：DS2 = **92 突变 / 8 有效病人**（inference 子集，P102 在 inference 中近缺席）。
> - **本地已核口径（HLA-FIX 第 7 版）**：DS2 = 9 患者 P101–P110（**缺 P103**）；**101 有效肽**（90 阳 / 11 阴，SFC>0）；HLA-FIX 剔除 P101/P102 后 **7 有效患者**。
> - 两套口径（92 突变/8 患者 vs 101 肽/9 患者→7 有效）不一致，**直接影响表 1、表 5–10 全部 n 与分母**。投稿前必须由袁老师 / 朱同学书面统一，writer 不得自行选边照写。

**可验收门槛**：
1. 表 1 含全部四数据集行，每行齐备：物种 / 病人(样本)数 / 有标签突变数 / 肽–HLA 行数 / 覆盖工具数 —— 数字与各自 csv 对账一致。
2. 四集均有「同一三步范式 + nested-LOPO」的可运行脚本与产出 csv（鼠用 `camp.py` 参考实现）；不可只人源跑、鼠源留空。
3. DS2 的 n（突变数 / 有效病人数）**全文统一**为拍板后的单一口径，表 1 / 各结果表 / 正文不得并存两套数字。
4. 聚合键明文：鼠 `27AA_Sequence_MT`；人 `Patient_ID|Peptide_ID`（`mut_key`）。

**建议归属**：鼠数据收集 = 数据组（王子源 / 谢孟翰 / 袁老师）；nested-LOPO 跑通 = 徐伊琳（框架 HPC 部署）+ 余嘉；**口径冲突拍板 = 袁老师 / 朱同学**。

---

## G3 — 三重严格检验齐全（nested-LOPO + ablation + robustness）

**判据（袁 md §2.6、§3.3.2–3.3.4、附录 A）**：三重检验全部到位——
- **nested-LOPO**：外层留一病人评测、内层选超参 θ，报告 **oracle vs LOPO 一致性**（相等 = 零过拟合）；
- **ablation**：维度留一（leave-one-dimension-out，表 7）+ 加权方式对比；
- **robustness**：随机删 **10% 与 20%** 突变 × 多组固定种子，比较**子采样均值 / 中位 / 胜率**（表 9 / 图 3）。

**当前状态**：❌ — 三项全缺或仅有非对应等价物。
- nested-LOPO：❌ 仅 `quantimmune/lopo_eval.py` 单层（Ridge/FixAvg/GBDT），无内层选超参的双层结构。
- ablation：❌ 本地无维度留一 + 加权 ablation 的产出 csv。
- robustness 删 10/20%：❌ 本地**完全无支撑 csv**（缺 `robustness_subsample` 类产出）。袁 md 声称值（geomean 删 10% +0.4643 / 删 20% +0.4488 / max 满数据 +0.4834）**本地无支撑、待跑**，写文前不得引用为已核数。

**可验收门槛**：
1. nested-LOPO：产出 csv 含每外层 fold 的 LOPO test 表现 + oracle 表现两列，正文 / 表 8 明确报告二者一致性（差值或一致性陈述）。
2. ablation：表 7 给维度留一结果（每维去除后的 LOPO Spearman，标出最承重维度）+ 加权方式对比结论（袁 md 预期「加权塌回等权」，须以本地 csv 实证，不得照搬声称值）。
3. robustness：表 9 + 图 3 可出——含 10% 与 20% 两档子采样的**均值 / 中位 / 胜率**三列，多组固定种子（袁 md §7 补充材料要求 30 组随机种子，见 G5），geomean 与 max 的对比可呈现。
4. 三项各自有对应可运行脚本（袁 md 附录 A：`nested_lopo_ensemble.py` / `sixdim_ablation_weights.py` / `robustness_subsample.py` 等）与产物 csv，禁用声称值占位充当结果。

**建议归属**：徐伊琳（框架 HPC 部署，三重检验脚本主力）+ 余嘉协跑；朱同学（pooling/fusion 研究原创者）确认方法学口径。

---

## G4 — fusion 扩至 12 法

**判据（袁 md §2.5 表 4、§3.3.1 表 6）**：列全 **12 种 fusion**（mean-rank、geomean、median、powmean、max、min、加权变体、softmax-rank、stacking/线性回归、constrained 等），填表 4 定义 + 表 6（3/4/6/7 维下 12 法 LOPO Spearman），并判定 **geomean 跨 3/4/6/7 维复现性**。

**当前状态**：⚠️ — 本地 fusion 仅 **4 法**，**无 geomean 单列、无删 10/20% robustness**。
- 已核 4 法（`fusion_methods.csv` DS2_main）：
  - `rankmean_surv6`（mean-rank 类）Fisher-z ρ = 0.3336，95%CI [0.108, 0.527]，DS1 sensitivity = **−0.157（不复现）**；
  - `fixavg_surv6` ρ = 0.3281，CI [0.101, 0.523]，DS1 = **−0.160（不复现）**；
  - `ridge_surv6` ρ = −0.3008，CI [−0.499, −0.072]，DS1 = 0.107；
  - `gbdt_surv6` ρ = −0.0421，CI [−0.267, 0.188]，DS1 = −0.118。
  - （ridge/gbdt 负 = 训练类在小样本 n=9 过拟合。）
- geomean：❌ 本地无单列结果（袁 md headline 的核心法则未跑）。

**可验收门槛**：
1. 表 4 枚举满 12 种 fusion 定义（公式或明确算子说明），含 **geomean 单列**；重点定义 geomean rank-fusion（共识/AND 型）及其与 max（OR 型）的对立直觉。
2. 表 6 给 3/4/6/7 维下全部 12 法的 LOPO Spearman（与拍板后 DS2 口径一致），每个值源自 csv。
3. 跨维复现性判定可出：明确 geomean 是否为「唯一在 3/4/6/7 维一致 ≥ mean 的 fusion」（袁 md headline 论据），以本地新跑 csv 实证；若复现性不成立，则**回退该 headline 并报告**（不得照搬声称值硬写）。
4. DS1 sensitivity 列保留并诚实呈现 mean-rank 类不复现（−0.157 / −0.160），不得为美化 headline 删去。

**建议归属**：朱同学（fusion 方法原创）+ 徐伊琳（扩 8 法 + 跨维跑通）+ 余嘉协跑。

---

## G5 — 主指标 Spearman + 全量 Pearson 补充

**判据（袁 md §2.6、附录 B-3、§7 补充材料）**：主文以 **per-patient Spearman 等权平均**为主指标；补充材料补全 **Pearson 对照表 + 可变窗(mw)口径结果 + ds1 复现 + 逐病人 Spearman 分布 + 30 组随机种子明细 + 配对检验完整统计**。

**当前状态**：⚠️ — Spearman 主指标已有（本地 per-patient Fisher-Z 已核），补充材料多项缺。
- 主指标已核（`per_patient_spearman_16tools.csv`，DS2 9 患者，Fisher-Z 加权）：PRIME ρ=0.2794 [0.050, 0.481]（最强、显著）；IMPROVE ρ=0.2502 [0.021, 0.455]（显著、count-safe 最稳）；PredIG ρ=0.2286 [−0.003, 0.437]（边界，CI 含 0）；其余 ≤0.13 或负、CI 含 0 不显著。
- 全局 max Spearman（`metrics_ds2_16tools.csv`，agg=max,>0,n≈101）：IMPROVE ρ=0.2518 p=0.0111（唯一双口径显著）；PredIG ρ=0.2005 p≈0.044。天花板 ρ<0.4。
- Pearson 全量补充：❌ 待补全。
- 可变窗(mw)：❌ / ds1 复现：⚠️（ds1 数据在但需跑） / 逐病人分布：⚠️ / 30 seed 明细：❌（依赖 G3 robustness） / 配对检验完整统计：✅ 已有（见 G6）。

**可验收门槛**：
1. 主文所有结果表 / 主图以 **per-patient Spearman 等权平均**为主指标，每个 ρ 配 95%CI（本地 Fisher-Z CI 口径）。
2. 补充材料含**全量 Pearson 对照表**（覆盖主文同样工具 / 方法，满足袁 md「Spearman 与 Pearson 同时呈现」）。
3. 补充材料含：可变窗(mw)口径结果（含「9AAonly 一致优于可变窗 4/4」的支撑数据）+ ds1 复现表 + 逐病人 Spearman 分布（袁 md 称 0.17–0.80 区间，须本地实证）+ 30 组随机种子明细 + 配对检验完整统计表。
4. 每个 ECE/AUC/ρ 类指标配 bootstrap CI 或 p 值（投稿防御写法），无裸点估计。

**建议归属**：余嘉（补 Pearson / mw / ds1 / 逐病人分布跑批）+ 徐伊琳（30 seed 随 robustness 一并产出）。

---

## G6 — 显著性诚实呈现

**判据（袁 md 附录 B-4、§3.3.5）**：所有「第一 / 最优」措辞旁必须注明**是否统计显著**；整合相对最强单工具的增量须诚实呈现为「持平 vs 显著」。

**当前状态**：⚠️（数字已核，但论文措辞未写 → 尚未达「已成文诚实呈现」，避免「已达标」错觉）— 本地配对检验已核「整合 vs 最强单工具统计持平」，落文后方可置 ✅。
- 配对检验（`fusion_vs_single_paired.csv`，best_single = MT_deepHLApan ρ̄=0.2519）：
  - fixavg：Δz=0.0037，p_two=**0.974**，sign_p=1.0 → 统计持平；
  - rankmean：Δz=0.0399，p_two=**0.833**，sign_p=1.0 → 统计持平。
  - 方向与袁 md §3.3.5 headline 一致（袁 md 称 Δ≈+0.038、p≈0.70，主要由单一病人 P101 驱动；为声称值，主文引用须标注口径）。
- 单工具地板（`fusion_single_floor.csv`）最高：MT_deepHLApan 0.2519、MT_IMPROVE 0.2499、MT_PRIME 0.2482。
- ⚠️ deepHLApan 在 per-patient 榜（ρ=0.2243）有**肽长混杂警示**，不作能力证据；作为 best_single 基线时须在脚注说明此 caveat。

**可验收门槛**：
1. 全文**无未标注的「最优 / 第一 / 最佳」措辞**——每处旁注配对检验结论（p 值 + 持平/显著）。
2. §3.3.5 明文报告「整合相对最强单工具统计持平」，给出本地已核 p 值（fixavg p=0.974、rankmean p=0.833）或拍板后口径下的对应值，并指出单病人（P101）驱动的脆弱性。
3. 凡用本地数字处用本地已核值；凡引袁 md 声称值（如 Δ≈+0.038、p≈0.70）处标注「inference 子集口径、待核」，不与本地真源混。
4. deepHLApan 相关排名处附肽长混杂 caveat 脚注。

**建议归属**：余嘉（writer 落文）+ verifier（投稿前数字三方对账）。

---

## G7 — 外部验证表态 + HLA-II 仅 future work

**判据（袁 md 附录 B-5/B-6、§4.3 Limitations、§4.4 Future work）**：Discussion 明确**所有增量结论待独立外部队列验证**；**HLA-II 仅作 Future work，不进 Results**（除非投稿前真有结果）。

**当前状态**：⚠️ — 大纲已含相应表态，待成文落实。
- §4.3 Limitations 大纲已列：整合 vs 最强单工具不显著（样本小、单病人驱动）；设计层 selection bias 未进 CV（用哪些工具/类别/pooling 是看全数据定的）→ 整合数字偏乐观；仅 8 有效病人 → ±0.03–0.05 难言显著；CV 协议本身无泄漏；所有增量结论待外部独立队列验证。
- §4.4 Future work 大纲已列 HLA-II 扩展。
- Results 当前无 HLA-II 内容 ✅（保持）。

**可验收门槛**：
1. Discussion（§4.3）成文含全部 5 条 Limitations，其中「所有增量结论待外部独立队列验证」必须明文出现。
2. **selection bias 未进 CV** 一条必须保留（BiB 审稿看重的诚实点），不得为美化删去。
3. HLA-II **零字进入 Results / 主图 / 主表**；仅出现在 §4.4 Future work。
4. 防御写法核查：无「we prove」「SOTA / best in literature」类绝对化措辞；增量结论一律加「待外部验证」限定。

**建议归属**：余嘉（writer 落文）+ reviewer（投稿前对抗审稿核 Limitations 完整性）。

---

## G8 — 许可 / 双盲合规

**判据（项目许可红线 + BiB 双盲）**：DTU 工具数字 pending DTU consent，投稿前取书面同意；各工具许可标注合规；对外档双盲 0 个人 / 机构名。

**当前状态**：⚠️ — DTU 工具数字已用于本地结果但 consent 未到位。
- DTU pending consent（学术许可禁第三方再分发含其数字）：`netmhcpan_ba`、`TSCAPE`、`netMHCstabpan` 等。`netmhcpan_ba` 是 G1/G4 关键工具（pooling 后 geomean ρ=0.3956；与袁 md netAffneg topk(k=20,α=0)+0.3946 数值接近但**算子不同**，本地同工具 topk_w 仅 0.1062，非已坐实数字桥，对应待重跑核）—— 一旦 consent 不到位，该 headline 数字须撤或替换。
- 许可性质：BigMHC 学术非商用；TSCAPE CC BY-NC-ND；NeoTImmuML★ 自训非官方。
- 双盲：对外档（投稿稿、GAP_ROADMAP/ALIGNMENT 类）须 0 个人/机构/导师/HPC 名；内部档（00_README/STORY/LOG）人名保留。

**可验收门槛**：
1. 所有 DTU 工具（netmhcpan_ba / TSCAPE / netMHCstabpan / ICERFIRE 等）的数字在投稿稿出现前，取得 **DTU 书面同意**；未取得则该工具数字从主文撤下或替换为可分发等价物（**拍板点**）。
2. 许可标注：BigMHC（非商用）、TSCAPE（CC BY-NC-ND）、NeoTImmuML（自训★非官方）在 Methods / 工具表或 Code Availability 中如实声明。
3. 投稿稿（PDF + 补充 + 代码仓 README）**0 个人 / 机构 / 导师 / HPC 名**，作者信息走期刊匿名通道；图表 / 路径 / 致谢不泄机构。
4. Code Availability 列关键脚本（`camp.py`、`score_pooling_lopo.py`、`robustness_7dim_fusions.py` 等）+ 复现说明，且不含受限工具的再分发数据。

**建议归属**：袁老师（DTU 书面同意 = 拍板）；余嘉 / gh-publisher（双盲脱敏 + 隐私扫描 + 许可标注）。

---

## 投稿前拍板点汇总（停下报告，writer 不自决）

1. **DS2 口径冲突**（G2）：92 突变/8 患者（袁 md）vs 101 肽/9 患者→7 有效（本地 HLA-FIX 7）—— 袁老师 / 朱同学统一。
2. **DTU consent**（G8）：netmhcpan_ba / TSCAPE 等 pending，关系 headline 数字 —— 袁老师拍板。
3. **30 工具是否真达标**（G1）：若投稿前到不了 30，文中数字与「30」措辞如何回退 —— 袁老师拍板。
4. **geomean headline 是否成立**（G3/G4）：本地无 robustness/geomean 支撑，待跑后若不复现须回退 §3.3.4–3.3.5 headline —— 见实测后报告。

> 凡 writer 落文时遇上述任一未拍板项，写 `\todo{待拍板：<项>}` 占位，不自行选边。
