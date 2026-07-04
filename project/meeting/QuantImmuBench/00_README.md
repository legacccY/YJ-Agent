# QuantImmu — 新抗原免疫原性「突变级定量」框架 + 30 工具系统 benchmark（论文项目）

> 📐 **权威框架 = `paper/QuanImmu-Paper-Outline.md`（袁老师定稿，投 Briefings in Bioinformatics）。本地所有档以此对齐。** 任何本地结论、数字口径、章节结构与该 outline 冲突时，以 outline 为准，本地不擅自改写，遇冲突停下报袁老师/朱同学拍板。

> **入口读档顺序**：本文 `00_README.md` → `01_STORY.md`（claims + 锁定数字 + 跑偏定义）→ `02_ACCEPTANCE.md`（各 lever 验收措辞）→ `paper/QuanImmu-Paper-Outline.md`（袁老师权威框架）→ `DEPLOY_TRACKER.md`（工具部署状态总表）→ `04_LOG.md` 最新 entry。
>
> 对齐辅助档：`reference/GAP_ROADMAP_vs_outline.md`（本地 vs outline 缺口清单 + 补齐路线）· `paper/ALIGNMENT_TO_OUTLINE.md`（本地真源数字 ↔ outline 声称值逐条对账）。
>
> 🧪 **跑实验前必读**：`03_EXPERIMENT_PLAN.md`（run-once 严谨实验+消融阶段计划：Phase 0 新官方数据地基重建协议 + 实验矩阵 R1-R9 + 消融 AB-1..11 + 冻结清单 + 5 拍板点 + 不卡执行策略。一次跑出 paper-ready 数据、零返工的唯一执行依据）。
>
> 🔧 **工具补跑进度真源**：`TOOL_RERUN_STATUS.md`（30 工具在新官方数据 43 补跑肽上的重跑状态 + 已固化通用 pattern + HPC 踩坑库。续窗 grind 接力看这里）。
>
> 🪖 **多窗大编队作战令**：`MULTIWIN_TOOL_FLEET_PLAN.md`（5 干活窗 + 1 主窗分 slice 补跑 30 工具的统一计划：铁律/验收/DoD/自由发挥/不堵塞不降级。开多窗先读这里认领 slice）。
>
> 📖 **新人/复盘**：`项目全解_从头到尾.md`（故事版全貌：这是什么、做了什么、踩了哪些坑、现状）。
>
> 📊 **干净结果总表（2026-07-01，writer 单一数据来源）**：`RESULTS_CLEAN_SUMMARY.md`——从零重建后所有锁定数字，按 outline § 组织 + 真源 csv + 诚实局限。写 tex 只用这份，别用重建前旧数（旧表已标 legacy）。
> 🔗 **单一真源 + 溯源（2026-07-04，Entry 54）**：管道一键重建 = `scripts/rebuild_canonical.py --verify`（证新旧 canonical 0 差异）→ `analysis/official/run_downstream.py --run`（下游全刷新）。每个 headline 数字 ← 脚本 ← csv 真源见 `PROVENANCE_TABLE.md`（Tier 0-4 溯源）。canonical=`data/frozen/pooled_clean_9mer.csv`（sha 见 `data/frozen/PROVENANCE.json`）。
> 📚 **headline 文献支撑（2026-07-04）**：「结合/呈递工具 ≥ 免疫原性专用工具」是学界已知（TESLA Cell2020/Buckley BiB2022 同期刊/综述），非数据错——先例+现成 Discussion 句子+引用+分类稳健性见 `reference/LIT_binding_vs_immunogenicity_2026-07-04.md`。卖点=系统化确认+新数据(Braun2025)+定量 Spearman，非新机制。工具分类拍板见决策档问题⑥。
>
> 📨 **给袁老师沟通档（2026-07-01）**：`给袁老师_两个方法学问题.md`——两个重建中发现的方法学问题（① 肽长混杂/长肽上 max 随窗口数虚高，附顺序统计量公式 ② geomean/mean-rank/median 在秩指标下数学近亲，附泰勒展开证明）。待与老师讨论。
>
> 🧭 **方法学重构提案（2026-07-01，待袁老师/朱同学拍板）**：`reference/METHODOLOGY_REFOUNDATION_PROPOSAL.md`。官方 130 肽 9mer 口径下 outline 两个细粒度 headline（§3.2 免疫原→max、§3.3.4 geomean 唯一第一）不复现，根因=**评价功效（n=9 太小），非 bug 非数据反转**；配 TESLA/IMPROVE 先例 + 三部曲解法（换肽级估计量/去 selection bias/外部队列）+ analyst 决定性检验 verdict（修①肽级够救 pooling/fusion lever）。**改论文战略定位=老师拍板级，未实施。** 见 04_LOG Entry 37。

---

## 一句话定位

**QuantImmu** 是一个把任意上游预测工具的输出转成**突变级（mutation-level）连续免疫原性强度分**的统一框架，并在该框架下**系统评测 30 种工具（10 呈递 + 20 免疫原性）**，跨人（ds1/ds2）与小鼠（B16F10/CT26）、以 ELISpot 为真值、以 **Spearman 秩相关**为主指标。投 **Briefings in Bioinformatics**（系统性 benchmark / problem-solving protocol 类）。

三个卖点（须进标题/摘要）：

1. **Quantitative（连续强度，非二分类）** —— 临床要的是在一个病人几十个突变里做精细排序，免疫原性本是连续强度，应以 Spearman 衡量而非 AUC 二分类。
2. **Mutation-level（突变级，非肽–分型级）** —— 工具在「肽–等位基因」对上打分，但临床决策单元是**突变**；如何把多条候选肽–HLA 行聚合（pooling）到突变级是被忽视的关键方法学选择。
3. **30-tool systematic benchmark（10 呈递 + 20 免疫原性）** —— 统一无泄漏口径、公平定量比较 30 种异质工具，并研究如何最优整合。

三步范式（方法学主体，详见 outline §2.3）：

- **Step 1 逐行打分 + 定向（orientation）**：每条肽–HLA 行取标量并统一成「越大越免疫原」；亲和力取 `−Aff(nM)`；可选 **DAI（MT vs WT）**；逐病人 min-shift + RMS 归一化（仅用病人自身特征，CV 无泄漏基础）。
- **Step 2 pooling（多行 → 突变级 1 分）**：四法 max / topk_w(k,α) / softmax(T) / rankdecay(γ)。
- **Step 3 rank-fusion（多维 rank → 综合分）**：各维病人内转 rank 再融合（mean-rank、geomean 等）。

三重严格检验（outline §3.3 方法学高潮）：**nested-LOPO**（外层留一病人评测、内层选超参，报告 oracle vs LOPO）+ **ablation**（维度留一 + 加权对比）+ **robustness**（随机删 10%/20% 突变 × 多种子，比子采样均值/胜率而非单点）。

---

## 当前状态总表（2026-06-29，真源数字见 `_scratch/ALIGN_FACTS.md` / `analysis/*.csv`）

> ⚠️ **本节数字已被 2026-07-01「从零重建」取代（LOG Entry 40-44）。最新真源 = `RESULTS_CLEAN_SUMMARY.md` + `data/frozen/pooled_clean_9mer.csv`。下表工具接入清单仍有效，但所有 pooling/fusion/单工具指标数字以干净重建为准，勿用本节旧数写 tex。**

> ⚠️ 本节数字一律取本地已核值。袁 md 中本地无支撑的声称值（如 fusion 删 10% geomean +0.4643、单工具 max subset92 值）标注「袁 md 声称值，本地待核」，不混入本地真源。完整对账见 `paper/ALIGNMENT_TO_OUTLINE.md`。

### A. 30 工具接入进度（目标 10 呈递 + 20 免疫原性；✅ 30/30 接入达成 2026-06-30）

> ✅ **30/30 接入达成**。真源 = `scripts/out/merged_all_tools_29tools.xlsx`（34247×81，**30 distinct score 工具**）+ `analysis/metrics_ds2_29tools.csv`（30 distinct，Bash 核过）。文件名 "29tools" 因 MHCflurry 计 1 工具占 2 列。**逐工具状态真源 = `DEPLOY_TRACKER.md` 表 A/表 B + 04_LOG Entry 30-COMPLETE**。
> ✅ **官方 130 肽口径也 30/30 达成**（2026-07-01）：`merge_official_30.py` 报告 **PENDING 0**，`merged_all_tools_30_official.csv`(34703×84) 30 工具全并入。收尾两个：TSCAPE 本地补满 130/130（纠 54.7GB 误解，0.53GB 本地 WSL2 跑）+ Seq2Neo 本地 pip 跑通（绕过 docker 三源拉不动死路：`pip install Seq2Neo` + 本地早有的 netMHCpan-4.1/netCTLpan-1.1，无需 DTU 申请）。详见 `TOOL_RERUN_STATUS.md` + 04_LOG Entry 32/33。

| 类别 | 目标 | 本地已接入 | 已接入清单 | 备注 |
|---|---|---|---|---|
| 呈递 / 结合 | 10 | **10 ✅** | netmhcpan_ba（DTU）· MHCflurry_presentation · MHCflurry_affinity_neg · HLAthena（proxy AUC≈0.51）· netMHCpan_EL（DTU）· MixMHCpred（替 stabpan）· BigMHC_EL · TransHLA · MHCSeqNet（替 MAAP）· MHCnuggets | MAAP 身份未明→MHCSeqNet 替；NetMHCstabpan 弃换 MixMHCpred（fakeroot 挡）|
| 免疫原性 | 20 | **20 ✅** | DeepImmuno · PredIG · IMPROVE（Expr 降级）· NeoTImmuML★（自训）· pTuneos（子模型）· PRIME · ImmuneApp · deepHLApan · BigMHC_IM · CNNeo（自训）· IEDB_Calis · Repitope · TSCAPE（DTU）· ICERFIRE（DTU）· NetTepi（DTU 低覆盖）· ImmugenX · MUNIS · Neoag · andy90（低覆盖）· DeepNetBim（license=null）| Seq2Neo/DeepNeo/Inference = bonus（外部阻塞，解了 31+，不解 30 已满）|
| **合计** | **30** | **30 ✅** | | 永久排除：MHLAPre（无权重）/ImmunoStruct（NO-GO 三重 blocker）；NeoaPred 🗄️搁置（OpenMM 物理模拟反复 HPC TIMEOUT，neoag 替）|

### B. 四数据集进度

> 🔴 **2026-06-30 数据真源切换（红线）**：DS2 唯一标准 = 袁老师下发官方更正数据 `data/OFFICIAL_DO_NOT_TOUCH/ELISPOT_OFFICIAL_Braun2025_MOESM4.xlsx`（**只读不可改**）。旧 `Elispot_Dataset2.xlsx`（101 肽）已废→ `data/_archive_superseded_20260630/`。完整红线 + 差异 + 待办见 `data/README_DATA_OFFICIAL.md`。

| 数据集 | 物种 | 状态 | 说明 |
|---|---|---|---|
| ds1（`Elispot_Dataset1.xlsx`，16KB，6 例黑色素瘤）| 人 | ✅ 在仓 | netMHCpan+PRIME 合并补充/复现集（官方更正版只含 DS2，DS1 独立保留）|
| **ds2 官方版**（`OFFICIAL_DO_NOT_TOUCH/ELISPOT_OFFICIAL_Braun2025_MOESM4.xlsx`，52KB，🔴只读，**主分析集**）| 人 | ✅ 唯一标准 | Braun *Nature* 2025 MOESM4（HLA bug 已采纳我方修正）。两页：**In Vitro 130 肽**/9 患者（P101–P110 缺 P103）+ **Ex Vivo 36 行**（pool×逐周）。⚠️旧 101 肽口径作废；官方多 29 肽（28 阳/1 阴），101 共有肽 Elispot 逐个一致；官方无我方 5 列注释（WT 序列需回贴）。⚠️现有 metrics_ds2_* 全基于旧 101 肽，待新 130 肽**重跑才生效** |
| B16F10 | 鼠 | ❌ 缺失 | outline §2.1 要求，归数据组（王子源/谢孟翰/袁老师） |
| CT26 | 鼠 | ❌ 缺失 | 同上 |

### C. 三层结果 + 三重检验进度

> ⚠️⚠️ **口径红线（回填 2026-06-30，必读）**：下表「✅ 已跑」的方法学产物**全部绑「旧 101 肽 DS2 + 9 工具子集」** = 输入 `quantimmune/model_matrix_v2.csv`（183 行突变级：DS1 患者 1-6 + DS2 P101-110 共 9 患者；工具维仅 DeepImmuno/PredIG/IMPROVE/NeoTImmuML/pTuneos/PRIME/ImmuneApp/deepHLApan/HLAthena 9 个，fusion/LOPO 用其中 surv6 即 3-7 维子集）。**三重检验方法学链跑通≠官方口径定稿**：① 数据待换官方 130 肽（2026-06-30 数据真源切换，见 §B）② 工具维待扩到全 30。两者皆需在 conductor 第二代 merge→pool→freeze 后重跑（`TOOL_RERUN_STATUS.md`）。数字真源见各 csv，Bash 核过。

| 环节 | outline 章节 | 本地状态 | 备注（旧 101 肽 + 9 工具口径，数字 Bash 核） |
|---|---|---|---|
| 单工具 max-pooling 基线 | §3.1 | 🟡 部分 | DS2 旧口径：per-patient Fisher-Z 最强 PRIME 0.279 [0.050,0.481]、IMPROVE 0.250 [0.021,0.455]；30 工具全量见 `per_patient_spearman_29tools.csv`；天花板 ρ<0.4 |
| 单工具 × pooling | §3.2 | 🟡 部分 | `pooling_sweep_17tools.py`（8 算子，超集 outline 4 法）；规律复现：结合类要聚合（netmhcpan_ba geomean 0.3956），免疫原类 max 即最优。⚠️袁 md netAffneg topk(k=20,α=0)+0.3946 与本地 geomean 0.3956 数值近但算子不同，待按 k=20 核 |
| 多工具 fusion | §3.3.1 | ✅ **已跑（旧口径）** | `analysis/fusion_12methods.csv`：**12 法 ×{3,4,6,7}维全跑**。最优 median@6维 fisherz **0.3736** [0.152,0.560]、geomean@6 0.3553；max@6 仅 0.267；gbdt 负=小样本过拟合。（取代旧「仅 4 法」记录）|
| nested-LOPO | §3.3.3 | ✅ **已跑（旧口径）** | `quantimmune/results/nested_lopo.csv`+summary：surv6 双层，**ρ=0.3281** [0.101,0.523] n=9 患者，θ 每折选 fixavg；**vs 打乱 null ρ=0.0090** [-0.220,0.237] → 真信号非泄漏；LOPO=oracle（consistency delta=0，paired-spearman=1.0）。（取代旧「仅单层 LOPO」记录）|
| ablation | §3.3.2 | ✅ **已跑（旧口径）** | `analysis/ablation_dim_weights.csv`：维度留一最承重维=**pTuneos**(Δ−0.034)、PRIME 反害(+0.025)；加权对比 learned_simplex 过拟合害事(Δ−0.241)、inv_var(−0.123)，**等权最稳**。|
| robustness 删 10/20% | §3.3.4（图3核心）| ✅ **已跑（旧口径）** | `robustness_subsample_results.csv`+summary：30 seed × drop 10/20%（7 维）。**median 法 top1 胜率最高**（10% drop=0.60、20%=0.33），fusion 胜最强单工具 baseline 在 10% drop 下 93-100% seed。⚠️袁 md geomean +0.4643/+0.4488 = 不同口径声称值，本地未复现该绝对量级 |
| 显著性配对检验 | §3.3.5 | 🟡 部分 | `fusion_vs_single_paired.csv`：整合 vs 最强单工具**统计持平**（fixavg Δz=0.0037 p=0.974；rankmean Δz=0.0399 p=0.833），方向对齐袁 md headline |
| 综合排名 + 部署 | §3.4 | ❌ 缺 | `rank_T01_deploy.py` 等部署脚本未做 |
| 小鼠全框架 | 跨节 | ❌ 缺 | `camp.py` 等小鼠管线 0%（数据未到位）|

**一句话现状（2026-06-30 回填校正）**：① **工具 = 30/30 接入达成**（旧 101 肽口径），官方 130 肽重跑 29/30 工具完成。② **三重检验方法学链全跑通**（fusion-12 / nested-LOPO+null / ablation / robustness 四件套据实已存在，此前 §C 误标「缺」），但**全绑「旧 101 肽 + 9 工具子集 model_matrix_v2」**。③ **真正剩的活**：在官方 130 肽 + 全 30 工具上重跑下游（conductor 8/15，待 merge→pool→freeze→重出四件套）+ 综合排名/部署 §3.4 + 小鼠数据与全框架（数据未到位）。详细缺口见 `reference/GAP_ROADMAP_vs_outline.md`。

---

## 我（余嘉 / legacccy）的子任务

在 HPC 上**部署并测试预测工具**，每个工具测试运行后收集 4 类信息，最终以 **PPT** 形式记录：

1. 输入数据的模板 / 格式
2. 预测工具运行的参数设置（可调参数的类型及功能）
3. 输出数据的格式及含义
4. 工具的简要介绍（特点、优势）

**余嘉的 5 工具（✅ 全部署 + 跑通 ELISpot benchmark + 4 类信息 + PPT，核心任务已完成）**：PredIG · DeepImmuno · pTuneos · IMPROVE · NeoTImmuML

- ⚠️ **分工纠正（2026-06-24 袁老师分组消息，见 04_LOG Entry 25）**：后 5 工具（PRIME · deepHLApan · ImmuneApp · MHLAPre · HLAthena）是李紫晨的活；余嘉此前做的 Wave3 部署 + benchmark（PRIME/ImmuneApp/deepHLApan 进 benchmark、HLAthena proxy）属**超额/可移交李紫晨参考**，不回退（已做的 benchmark 仍有效）。
- ⚠️ **NeoTImmuML = 自训版**（官方权重不可得 → 复刻官方 RF+LGB+XGB，PPT 标★非官方）；**pTuneos = Pre&RecNeo 子模型**；**IMPROVE = Expression 特征降级**。结论一律诚实分级，无「5/5 完美跑通」。
- ❌ **MHLAPre 唯一彻底阻塞**：无权重 + ProcessData npy 缺 + 预处理拼装码被注释，唯一出路邮件作者。**ImmunoStruct 已 NO-GO**（三重 blocker）。
- 余嘉后续重心 = 工具部署 + 配合 QuantImmu 组（徐伊琳）/ 数据组（王子源、谢孟翰），并把本地 benchmark 资产对齐袁老师 outline。

---

## 团队分工（背景）

- **预测工具组**：李紫晨（后 5 工具）+ 余嘉（前 5 工具 + Wave3 超额，本档）。
- **QuantImmu 框架组**：徐伊琳 —— HPC 部署 QuantImmu / Inference 模块（含内部 Inference 8-class 源码）。
- **数据收集组**：王子源、谢孟翰 —— 文献搜索 + 数据收集（含小鼠 B16F10/CT26，袁老师提供输入数据）。
- **pooling / fusion 研究**：朱同学 —— **pooling 范式原创**（本地 pooling/fusion 整合自其发现，三步范式 Step 2/3 的方法学来源）。
- **统筹**：袁老师 —— 项目牵头 + outline 定稿。

---

## HPC / 部署规范

- HPC：`dtn.hpc.xjtlu.edu.cn` / 用户 `jiayu2403` / 分区 `gpu4090`（详见 `project/HPC_WORKFLOW.md` + memory `project_hpc_xjtlu`）。
- 这些工具多为 **CPU 推理**（XGBoost / RandomForest / CNN inference），基本不占 GPU 卡槽；某步要 GPU 才走 `tools/gpu_slot.py request`。
- **拍板点**：HPC 上传新代码 / 数据 / 许可证 = 对外传输，每次上传前一行报；本地 clone、写脚本、读 README、填 md 自主推进。
- 部署一个工具的标准 6 步见 `DEPLOY_TRACKER.md` 顶部。

---

## 文档结构

```
QuantImmuBench/
├── 00_README.md                       # 本文：定位 + 权威框架指针 + 状态总表 + 子任务
├── 01_STORY.md                        # claims + 锁定数字 + 跑偏定义 + R-rules
├── 02_ACCEPTANCE.md                   # 各 lever 验收措辞
├── 04_LOG.md                          # 时间倒序日志
├── paper/
│   ├── QuanImmu-Paper-Outline.md      # 📐 袁老师权威框架（投 BiB）
│   └── ALIGNMENT_TO_OUTLINE.md        # 本地真源数字 ↔ outline 声称值逐条对账
├── reference/
│   ├── GAP_ROADMAP_vs_outline.md      # 本地 vs outline 缺口清单 + 补齐路线
│   ├── LANDSCAPE_tools.md / LANDSCAPE_datasets.md / BENCHMARK_METHODOLOGY.md
│   ├── REDTEAM_benchmark.md / VERIFY_numbers.md / THEORY_quant.md / REVIEW_deliverables.md
│   └── EXPERIMENT_MATRIX_quantimmune.md
├── DEPLOY_TRACKER.md                  # 工具部署状态总表 + 标准流程 + 许可清单
├── REFERENCES.md                      # 工具论文/DOI/repo 出处 + 外部依赖 + 数据集
├── PROVENANCE.md                      # 代码归属（我们写的 vs 外部）+ 许可/再分发限制
├── TOOLS/                             # 每工具一份 info 文档（= PPT 素材）
├── data/                             # ds1/ds2 + HLA-FIX 上报
├── analysis/                         # benchmark 指标/出图/报告（figures_R_v3 终版）
├── quantimmune/                      # QuantImmu 框架代码 + LOPO 产物
├── HPC/                             # 从 HPC 拉回的部署脚本 + ELISpot 正式跑产物
└── scripts/                         # 部署 / 烟测 / 格式转换脚本（均我们写的，见 PROVENANCE）
```

---

## 许可红线（写档 / 投稿必带）

- **netmhcpan_ba / TSCAPE**：pending DTU consent（DTU 学术许可禁第三方再分发，含其跑出的数字）→ 投稿前取书面同意。
- **BigMHC**：学术非商用；**TSCAPE**：CC BY-NC-ND；**NeoTImmuML 自训★非官方**。
- **netMHCstabpan-1.0** 仍 glibc 挡（HPC el8 仅 glibc 2.28，需 ≥2.29）→ 仅 IMPROVE feature_calc 的 Stability 特征用它，不影响 benchmark。
- **双盲**：对外档（`GAP_ROADMAP` / `ALIGNMENT_TO_OUTLINE`）须 0 个人/机构/导师/HPC 名；内部档（`00_README` / `01_STORY` / `04_LOG`）人名保留。

---

## 注

本项目已从「轻量工程台」**升级为 QuantImmu 论文项目 schema**，论文档见 `01_STORY.md` / `02_ACCEPTANCE.md` + 权威框架 `paper/QuanImmu-Paper-Outline.md`。后续写 tex / 核数字 / 跑实验前，先读对应 STORY + ACCEPTANCE 对齐 claim 与验收口径。
