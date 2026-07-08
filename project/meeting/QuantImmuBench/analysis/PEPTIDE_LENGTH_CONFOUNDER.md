# 肽长×ELISpot 混杂 — 存在性证据链 + 矫正法深度研究

> 服务 QuantImmuBench。2026-07-05。数字均已 Bash 独立复算（禁 Read 看数据）。
> 数据 = DS2 官方口径 `data/frozen/pooled_clean_9mer.csv`（130 肽 / 9 患者，肽=15–33mer 疫苗 SLP，Elispot=连续 SFC）。
> 脚本 = `_scratch/peplen_confounder_hardening.py`（存在性）+ `_scratch/correction_compare.py`（矫正）。机制见 `peptide_length_confounder/MECHANISM_NOTES.md`。
> 📖 矫正公式详解（PPT P7 展开版，物理意义+逻辑+局限+paper-ready methods 段）见 `peptide_length_confounder/CORRECTION_FORMULA_EXPLAINED.md`。

---

## TL;DR（三句话）

1. **「疫苗肽越长 ELISpot 越高」是真的、队列内稳健的**：per-patient ρ̄=+0.380（bootstrap 95%CI[+0.196,+0.558]，8/9 患者正），控 TPM/CCF 后仍 +0.299、控子肽计数后仍 +0.314，都不过 0。机制上**很可能是真实 SLP 生物学**（**前提：配肽等质量——Ott 2017 佐证、Braun 原句待人工核 Supplementary**；若成立则等质量 + ELISpot 技术偏倚都反向 → 排除剂量伪迹），非技术假象。
2. **但「肽长强烈搅动工具排名」被核实证伪**：用公平口径（匹配患者集 + 丢小样本退化点）后，每工具的纯长度污染很温和——跨工具 Δρ 均值仅 +0.016、最大 TSCAPE +0.102；之前「HLAthena 掉 0.377」的招牌例子**大半是一个小 n bug（P101 只 3 点→虚假 ρ=1.0）而非长度**。
3. **矫正仍值得做，但作为「双口径并报」而非「换主口径」**：长度效应对不同工具确实非均匀（该矫正、不能当均匀噪音），评估侧偏相关（A）与残差化 ELISpot 标签（B，用户原提案）结论几乎一致；推荐 raw + 控长双列并报，且把小 n 退化审计一并修掉。

---

## 一、逻辑与问题

用户命题分两步：**(1) 先证「长肽 ELISpot 更高」存在 → (2) 再提矫正**。矫正目的不是提分，是**更准地从 ELISpot 拿到突变本身的免疫原性**——把「肽长」这个 nuisance 从标签里剥掉。判据：若长度效应对各方法**非均匀**，就必须矫正（不能当均匀噪音丢）。

---

## 二、存在性（成立，且稳健）

| 检验 | 口径 | 结果 | 判读 |
|---|---|---|---|
| 全局 Spearman(肽长, ELISpot) | n=130 | ρ=+0.319，置换 p=0.0004；Pearson +0.326 | 正相关（描述性，未控患者聚类） |
| **per-patient ρ̄（主口径）** | Fisher-z 等权，k=9 | **ρ̄=+0.380**，sign-perm p=0.0078，8/9 患者正（仅 P102=0） | 主证据 |
| cluster-bootstrap 病人 CI | n_boot=2000 | 95%CI **[+0.196,+0.558]**，不过 0 | 非单患者驱动 |
| **控 TPM+CCF**（残差偏相关） | k=8，complete-case | **ρ̄=+0.299**，CI[+0.078,+0.492] | 存活 → 非搭肿瘤表达/克隆性便车 |
| **控 n_subpep**（单控偏相关） | k=9 | **ρ̄=+0.314**，CI[+0.113,+0.491] | 存活 → 非纯机械子肽计数膨胀，有独立净效应 |
| 分层 SNV / indel | 全局 | +0.309（n=101）/ +0.449（n=28） | 两层皆正，非 indel 单独驱动 |
| 分层 Driver / Passenger | 全局 | +0.708（n=17，未控患者聚类）/ +0.251（n=112） | Driver 肽长耦合最强（n 小，勿当 headline） |

> ⚠️ 分层 per-patient 口径偏边际：SNV 亚组 per-patient ρ̄=+0.297 CI[**+0.048**,+0.511]、Passenger 亚组 +0.245 CI[**+0.002**,+0.461]——CI 下界贴近 0，属临界显著，别强 claim「所有分层均显著」。主证据以全样本 per-patient ρ̄=+0.380 及控混杂版为准。

**结论**：DS2 内长肽→高 ELISpot 稳健存在，且独立于表达/克隆性/子肽计数。**跨队列复现不可得**——DS1 全 82 肽皆 9mer（零长度方差），鼠数据缺；存在性为单队列（诚实标注，待外部验证）。

#### 稳健性七道检验（详见 `peptide_length_confounder/METHODS_AND_FORMULAS.md` §四；脚本 `_scratch/peplen_existence_robustness.py` 从零实现、不 import 引擎=独立交叉验证）
| 检验 | 结果 | 判读 |
|---|---|---|
| 独立复算（不用引擎） | ρ̄=0.3802，逐位一致 | 交叉验证通过 |
| **LOPO 逐患者留一** | ρ̄∈[+0.302,+0.422]，9 次全>0（去最强 P101 仍 +0.302） | 非单患者驱动 |
| **患者内置换检验**（B=5000） | p=0.0004 | 尊重患者聚类的零分布下高度显著 |
| 符号检验 8/9 正 | 双尾二项 p=0.039 | 方向一致性显著 |
| per-patient Pearson（原值） | +0.435 | 比秩相关更强 → 非秩伪迹 |
| 8-11mer 口径 | +0.380（一致） | 口径无关（肽长按突变恒定） |
| 单/双控（TPM/CCF/子肽数/TPM+CCF） | CI 均不过 0 | 独立于各混杂 |
| **四混杂同控（TPM+CCF+子肽数+indel）** | +0.215，CI[**−0.057**,+0.466]，k=8 | 点估计仍正，但 8 患者下同控 4 协变量**功效不足、CI 跨 0**（诚实标注，非效应消失） |

综合：主口径在独立复算 / LOPO / 患者内置换 / 符号 / Pearson / 换口径 六道下全部稳健方向一致 CI 不过 0；唯一边界是四混杂同控的小样本功效损失。

### 机制（真生物学，非伪迹）——见 MECHANISM_NOTES
- Braun 2025 = NeoVax SLP pipeline，ELISpot 用 **15–33mer 长肽本身**刺激 + 10–14 天体外扩增，配肽**按质量（µg/mL）**（Ott 2017 独立佐证 `2 µg/ml`/`0.3 mg` 每肽）。
- **等质量 → 长肽摩尔数更少 → 表位拷贝更少 → 该更低**；ELISpot 技术偏倚也偏向短肽（短肽直载 MHC-I 免加工）。**两条都反向 → 排除「剂量/质量伪迹」（用户设想的等摩尔→更多重量方向不成立，实为等质量）。**
- 正相关更像**真实 SLP 生物学**：长肽携更多 CD4 辅助表位 + 更充分加工/交叉呈递 → 更强 T 应答（Melief 经典）。⚠️保留口径：assay 带体外扩增，长肽经 CD4-help 被系统性放大，是真免疫原性但**≠纯 in vivo 保护**，别过度卖。

### 估计量论证（为何真生物学仍该矫正）
长度效应**是真的**，但它是**疫苗构造（construct）的属性**（他们把 SLP 合成成多长），**不是突变的属性**。QuantImmuBench 的估计量 = **突变本身的免疫原性**。一个 mutation-level 预测器若靠追踪 construct-level 的长度拿分，就是把构造级信号记到突变级账上 → 该剥离。**矫正 = 从真实但构造级的长度效应里分出突变的贡献，不是「抹掉一个假信号」。** 这也正面回应「肽长是 nuisance 还是真 driver」的红队攻击：它是真 driver，但对本估计量而言是需控的构造级协变量。

---

## 三、矫正法四路并比（核实后的公平口径）

四路：**A** 评估侧偏相关控 peplen（两侧去长度）；**B** 残差化 ELISpot 标签（只从标签去 peplen，不动工具分＝用户原提案）；**C** 联合多控 peplen+n_subpep+is_indel；**D** 长度分箱内秩归一（敏感性）。

### ⚠️ 核实暴露的两个陷阱（已修正为「匹配患者集」口径）
1. **患者集不一致**：偏相关硬底 4 点，会剔掉小 n 患者；raw 不剔 → raw 与矫正比的是不同患者，delta 被污染。
2. **小 n 退化 ρ=±1**：覆盖有缺口的工具在某患者只有 3 个非空值时出现虚假 ρ=±1，被 clip-Fisher-z 夸大。全 30 工具仅 **2 个**中招：**HLAthena（P101, n_eff=3, ρ=1.0）** 与 **NetTepi（P102, n_eff=3, ρ=−1.0）**。
   - 后果：HLAthena raw 被从真实 ~0.207 虚高到 **0.627**。之前「HLAthena 0.627→控长 0.250 掉 0.377 = 长度伪迹」的招牌例子，**大半是这个小 n bug、不是长度**——丢掉 P101 后 HLAthena raw+0.207 → 控长+0.250（控长反而略升）。

**公平口径 = 每工具 raw 与各矫正用同一批患者（n_eff≥4、peplen 有变异、丢 |ρ|>0.999 退化点）。** 下表为该口径。

### 匹配患者集：纯长度效应（Δ=raw−控长A）
| 类别 | 工具（Δ=raw−控长A） |
|---|---|
| **真被长度轻抬（正 Δ，控长后降）** | TSCAPE +0.102、ImmuneApp +0.077、IEDB_Calis +0.075、Seq2Neo +0.070、IMPROVE +0.054、ICERFIRE +0.052 |
| 基本不动（\|Δ\|<0.04） | MHCnuggets +0.034、MHCseqNet +0.039、MUNIS +0.035、netMHCstabpan +0.030、TransHLA +0.028、PredIG +0.022、PRIME +0.012、MHCflurry +0.006 … |
| **被长度压着（负 Δ，控长后升）** | netMHCpan_BA −0.040、netMHCpan_EL −0.036、NeoaG −0.054、andy90 −0.067、NeoTImmuML −0.068 |
| 覆盖过稀/退化，不可靠 | NeoaPred（k=1）、DeepNetBim（k=0，max-pool 退化常量） |

跨工具 Δ（仅 k≥2 可靠工具）：**均值 +0.016，std 0.045，max +0.102（TSCAPE），min −0.068（NeoTImmuML）**（NeoaPred k=1 / DeepNetBim k=0 已剔为覆盖过稀不可靠）。

### 三个诊断结论
1. **要不要矫正 → 要**：长度效应**非均匀**（有工具被抬、有工具被压），故不能当均匀噪音丢。但**幅度温和**（多数工具几个百分点），不是戏剧性重排。区分两量：ρ̄(肽长,ELISpot)=0.38 是**肽长自身**与标签的相关（强）；工具被污染要它自己的分也跟长度走，多数工具没有 → 控长对多数工具只动几分。**0.38 强 ≠ 排名被强搅动。**
2. **选哪路 → A 与 B 几乎一致**（B=用户原提案「矫正 ELISpot 标签」，与评估侧偏相关 A 结论收敛），说明矫正对「单侧去 vs 两侧去」稳健；C（多控）更激进。**推荐 A 或 B 双口径并报**；C 作 robustness 附表。B 单独不宜当唯一主口径（它预设标签里长度效应全是 nuisance，与估计量论证同前提，须与 A 并列）。
3. **排名稳健**：raw vs 控长 Kendall τ≈0.61–0.76（匹配口径：vs A=0.76 / vs B=0.67 / vs C=0.61；非匹配对照口径 0.52–0.60）——控长会温和重排（HLAthena 因小 n bug 从虚高位次回落，netMHCpan_BA 略升），但真正强的工具（MHCnuggets/netMHCpan_BA/MHCflurry/PRIME）稳在前列。

### 3a. 机制：为什么控长对多数工具只动几分（两层，已验；脚本 `_scratch/peplen_mechanism.py`，图 `fig_peplen_mech_toollevel.png` / `fig_peplen_mech_pooling.png`）

**层一 · 控长改动 delta ∝ ρ_XZ（工具分自身与肽长的相关）。** 从偏相关公式一阶展开：
```
delta = ρ_XY − ρ_{XY·Z} ≈ [ρ_YZ/√(1−ρ_YZ²)]·ρ_XZ − [1/√(1−ρ_YZ²) − 1]·ρ_XY
      ≈ 0.411·ρ_XZ − 0.081·ρ_XY     (代入 ρ_YZ=肽长↔ELISpot≈0.38)
```
ρ_YZ=0.38 对所有工具是同一常数；真正决定某工具被不被拉的是它**自己**的 ρ_XZ。混杂要经过工具才污染它。数据验证（28 可靠工具）：
- 工具级 **corr(ρ_XZ, delta_A) = Pearson 0.72 / Spearman 0.70**。
- **22/28（79%）工具 |ρ_XZ|<0.2**（中位数 0.13，远小于 ρ_YZ=0.38），这些工具平均 |delta| 仅 **0.035**。
- 逐患者剂量-反应：|ρ_XZ|<0.2 的点平均 delta −0.01；|ρ_XZ|≥0.4 的点平均 +0.13。
→ 所以「肽长自身相关 0.38 很强」与「多数工具没被搅动」不矛盾：0.38 是 ρ_YZ，工具被拉要 ρ_XZ 大，而多数工具 ρ_XZ≈0（甚至因 −0.081·ρ_XY 项控长后略升）。

**层二 · ρ_XZ 由 pooling 算子决定——长度经「窗口数（子肽数≈肽长，ρ=0.755）」传导，敏感度看算子随袋变大的抬升程度。** 跨 27 工具平均 |ρ_XZ|（源 `mechanism_pooling.csv`）：

| pooling | 平均\|ρ_XZ\| | 控长改动 | 档 |
|---|---|---|---|
| **sum 求和** | **0.614** | +0.137 | 灾难（机械正比窗口数，项目已弃用） |
| top-20 / top-8 均值(a0) | 0.240 / 0.236 | +0.048 / +0.045 | 偏高（从更大池选 k 个最高，选择增益） |
| top-3 均值(a0) | 0.185 | +0.027 | 略高 |
| geomean / **max** / mean / softmax / rankdecay / top-100 | 0.10–0.16 | ≈0 | 低（对袋大小近不变或仅顺序统计量温和抬升） |

- **sum 是灾难级**（0.61）：求和机械正比于窗口数——正是项目弃用 sum 的原因。
- **max/mean/geomean/softmax/rankdecay/大 k top-k 全低**（0.10–0.16）：项目主分析给免疫原性工具用 max、坚决不用 sum，恰是长度最稳的一档。
- **中段 top-k（k=3–20 等权）比 max 还略敏感**（0.19–0.24，非单调）：「从更多窗口里挑 k 个最高再平均」的选择增益在中等 k 最强，两头（k=1=max、k=100≈mean）反而弱 → 项目给结合工具用的 top-k(α=0,大 k) 聚合，是除 sum 外最该控长的。
→ 本质是**多示例学习 max/top-k pooling 对可变袋大小的顺序统计量偏倚**，偏倚大小由分数分布上界（校准/饱和程度）调制：越饱和/校准的工具越不受长度影响（也解释 netMHCpan_BA 太饱和、长肽真信号被 max 天花板削掉 → 控长后反升）。

**可行动结论**：「要不要控长」不该一刀切，取决于该工具用哪种 pooling——sum 必须控、中段 top-k 值得控、max/mean/geomean 基本免疫；更根本的减混杂手段是让工具输出校准好的连续分。

### 3b. Fusion（geomean）在控长下 headline 存活性（已验，源 `analysis/official/R3_fusion_12methods_official.csv` 的 `rho_lenctrl` 列）
- **geomean 仍是最稳的无监督整合法**：在 headline 的 best-dim 配置（3/6/7 维）下，控长后 geomean 在 8 个无监督 rank-fusion 里**仍居首（#1/8）**（6 维 raw+0.402→控长+0.330；7 维 +0.449→控长+0.407）。核心 claim「geomean 是最稳整合规则」**存活**。
- **但对最强单工具的领先软化为持平**：控长后 geomean（6/7 维 0.33–0.41）**不再明显高于**最强单工具（netMHCpan_BA 控长≈0.432）——从「融合胜单工具」降为**大致持平**（与 G6「integration vs best single 诚实报 tied/significant」一致）。
- 学习型（ridge/stacking/constrained）在部分配置控长下反超 geomean，但它们全数据选维、未进 CV，有 selection bias caveat，不作 headline。

### 3c. Fusion 交叉验证：整合优势主要是成员选择偏差（WS1，核心；脚本 `analysis/fusion_cv/fusion_nested_cv.py`，结果 `fusion_nested_cv.csv`）
**问题**：无监督 geomean 融合本身无泄漏，但**SURV6 六工具的成员选择从没进过 CV**（硬编码、看全数据定的）——项目 §4.3 自承的 selection bias。**做**：nested-LOPO（外层留一患者、内层前向贪心从全覆盖工具池选融合成员），geomean 钉死，退化守卫 + 候选池限每患者≥8 肽（剔 HLAthena/NeoaPred 等稀疏工具防小 n 虚高），裸+控长两版，含 shuffle null。
- **校验**：`fixed_surv6=0.366` 精确复现 R3 六维 geomean；oracle(0.525)≥cv(0.352) 作弊上界成立。
- **公平臂（全覆盖全工具）结论（裸口径）**：honest CV 整合 **0.352 已低于**最强单工具 MHCnuggets **0.447**（Δ=−0.094）；控长口径 Δ=+0.037。两口径 paired p=0.117 / 0.547——**n=9 功效不足、未能检出差异（"未能检出" ≠ "证明相等"，入稿须写 underpowered）**。整合点估已不胜单工具，是比"持平"更强的降温依据。
- **两个必须分开的量（reviewer 纠偏）**：
  - **固定 SURV6 headline 本身几乎没被膨胀**：`fixed_surv6=0.366 ≈ honest CV 整合 0.352`（差 ~0.01）。所以别说"headline 数被夸大 0.17"。
  - **0.17 = 前向贪心"重选成员"这个过程的过拟合上界**（oracle 全数据贪心 0.525 − honest CV 0.352）：它量化的是"若按数据重选融合成员能虚高多少"，不是现有固定 SURV6 的虚高。geomean 整合 = MHCnuggets 9/9 折稳选，成员数/折均值 3.3。
- **诚实 caveat**：n=9 下"选最强 of 24 工具"的 CV 有固有虚高 null（shuffle：单工具臂 null≈0.27 > 整合臂 null≈0.15，单工具过拟合内层噪声更狠）→ **只信配对差与选择膨胀两个量，不信绝对值**。
- **no-DTU 臂是 consent-critical、不是可无视的悲观界**：no_dtu 整合显著更差（裸 Δ=−0.157 p=0.031 / 控长 Δ=−0.187 p=0.016，`consent_critical=True`）。机制上是剔 netMHCpan_BA 削弱整合而单工具 MHCnuggets(非DTU) 未动——但若 DTU 书面同意拿不到（G8），no_dtu 是**唯一可投的臂**，那里"整合显著劣于单工具"→ **反而强化"consent 失败时应部署单工具 MHCnuggets"**。（且 fullcov-控长臂的最强单本身切成 netMHCpan_BA，比较两端都缠 consent。）
- **落点**：G4/G6 headline「geomean 整合是稳健赢家」应降温为「honest CV 下整合点估已不胜最强单工具（n=9 功效不足未能检出差异）；且按数据重选成员会虚高约 0.17」= **袁老师拍板点**（不擅改 canonical/headline）。注意"最强单工具"身份随口径变（新 130 肽口径=MHCnuggets 0.447，旧 G6 口径=deepHLApan 0.252）。

### 3d. 深挖收口（WS2–5，数据在手 + 快验证）
- **WS2 控长重选 best-pooling + 重排榜**：13/30 工具裸口径 vs 控长选到**不同 pooling 变体**（裸常选大 k top-k 搭长度便车，如 MHCflurry topk_k20→rankdecay_g2）；工具榜按控长重排，**HLAthena 从 rank 1 跌到 18**（0.627→0.250），geomean/powmean 升进 top-8。→ 裸口径选优确被长度污染，控长口径更干净。
- **WS3 控长对二分类 AUPRC**：长度对**二分类判别**的影响（裸 vs 残差化 AUPRC 排名 Kendall=0.63）比对**连续排序**（≈0.76）更大；残差化后 AUPRC 中位降 0.021，掉最多的是 TSCAPE/netMHCstabpan(DTU)/PredIG/IMPROVE。标签=官方 xlsx `Ttest_pvalue<0.05`（76 阳/54 阴，略偏阳 58%）；校验 netMHCpan_BA AUPRC=0.7155 对齐 S1。
- **WS4 饱和度假说（部分成立）**：4 个饱和度量里 2 个方向对（nunique_ratio 与 |ρ_XZ| Spearman +0.19、ceiling_tie_frac −0.23）、2 个反向（std_norm/top_decile_mass）——**弱支持、非干净确认**。DeepNetBim（完全饱和、nunique_ratio 0.008）定性符合。诚实标：层二机制在 pooling 层稳、在工具饱和度层只弱支持。
- **WS5 退化审计扩全 51 变体**：小 n 退化三元组从 `_max` 的 2 个升到全变体 **95 个**，小 k top-k/softmax 占 44%；控长重选选到的变体基本避开退化（仅 HLAthena topk_k3_a0p5 命中 1 个）。

---

## 四、推荐（不动主口径，供袁老师拍板）

1. **矫正确有必要**（长度效应非均匀），但定位为 **raw + 控长双口径并报**，非「换 canonical 主口径」。措辞从「肽长混杂/矫正掉」降温为「肽长效应（部分真 SLP 生物学）；报 raw 与控长两版供读者判」。
2. **优先修那个独立 bug**：per-patient Fisher-z 应按**有效 n**（去 NaN 后）门控、并处理退化 ρ=±1；否则 HLAthena/NetTepi 等覆盖有缺口的工具被单个小 n 患者虚高。**已核实**：生产主榜 `R1_single_maxpool_official.csv` 确实带虚高 HLAthena raw=0.627、NetTepi=−0.275；而 `R1_recomputed_effN8.csv`（effN≥8 门控）已给出修正值 HLAthena=0.207、NetTepi=0.293——**修法其实已存在，只是没设为 headline**。建议把 effN 门控口径设为主榜；且「HLAthena 0.627→控长 0.250」的长度对照应在 effN 门控基线上重算（原对照建在未门控的虚高基线上，夸大了长度效应）。
3. **矫正法**：主推 A（评估侧偏相关控 peplen）或 B（残差化标签），双口径并报；C 多控作 robustness。全部用匹配患者集 + 丢退化点。

---

## 五、原则化 CV 融合选择引擎 + 13 条方法学 rationale ledger（§3c 深化收口）

> 服务 Claim (ii)/(iii) + 旧 C3；lever = 用原则化交叉验证替代「看全数据硬编码」的融合成员选择。对齐 **G3**（nested-LOPO oracle vs CV 一致性）、**G4/G6**（integration vs best single 诚实报）。
> §3c 已给结论骨架，本节把「选择引擎的完整证据」+「SURV6 定位」+「13 条受控 rationale」摊开。数字全部来自 `analysis/fusion_cv/*.csv`（引擎自检零偏离 PASS → 正式跑 6 csv → verifier 六命门 PASS → #4/#5 修 design gap 重核）。**主口径 = raw、nested-LOPO、算子钉 geomean。**

### 5.1 选择引擎主结论 —— CV-最优是小 k，单工具 MHCnuggets 已足

不再硬编码 SURV6 六维，而是问：**若把「用哪些工具、几个、怎么聚合」都交给无泄漏的 nested-LOPO 数据驱动地选，会选出什么？** 结论一致指向**小规模**：

- **CV-最优是小 k**。学习曲线（raw greedy，源 `k_curve.csv`）：单工具最强 = **MHCnuggets ρ̄=0.4466**（k=1，此时 max-pool 下 CV≡oracle、无选择膨胀）；名义 CV 峰在 k=7（0.4495）仅比 k=1 高 **0.003**，且与单工具 paired-p≈0.96 **完全不可分**——要为这 0.003 付 7 工具的部署/许可代价，不成立。**「大融合有 CV 增益」在本数据不存在，勿把 k=7 名义峰抽出当卖点。**
- **选择膨胀被量化**。oracle（全数据贪心）随 k 单调升 0.4466→0.5435，而 CV 在 0.317~0.4495 徘徊；**inflation = oracle−CV 在 k≥2 稳定 0.09~0.15**——这正是「按数据重选成员」能虚高多少的直接读数。
- **换哪种选择程序都不超单工具**（raw，算子固定 geomean，源 `select_engine.csv`）：forward / backward / exhaustive / topk 五种程序 CV 全在 **0.327~0.400**，`delta_vs_best_single` **全负**，主程序 `paired_p_vs_best_single` 全 >0.05（forward 0.117 / backward 0.31 / exhaustive 0.48 / topk 0.36）。
- **38 个「统计上分不出高下」的候选**（含 best_single 自身）：连 MHCnuggets 与 CV-最优都 p=0.64 不可分。措辞上因此**不是**「geomean 六维证明最优」，而是「**CV-最优 + 一批（38 个）统计上无法区分的候选 + 工具入选频率**」。
- **稳定性只认一个工具**（cluster-bootstrap B=200，源 `select_stability.csv`）：仅 **MHCnuggets 过 0.6 共识阈**（`select_freq_boot`=0.795、9-fold 入选=1.00）；次高 `netMHCpan_BA`=0.411（DTU，不过阈）、`IEDB_Calis`=0.372（不过阈）。算子 churn：geomean 占 77.8% 的折 → 算子层同样稳。
- **抓到的是真信号、不是泄漏**（源 `select_null.csv`）：患者置换 null 下真 CV=0.3525 显著高于置换分布（`perm_p`=0.01）；random-k-subset 的 observed=in-sample oracle 天花板（k=3 obs=0.525, p=0.001）=选择过程有真判别力、非噪声拟合。

**净结论（措辞纪律）**：honest CV 下**无可检测的整合净优势**——CV-最优实为小 k、稳定入选仅 MHCnuggets，五种选择程序都不超单工具；这不是「证伪整合优势」，是「在 n=9 功效下未能检出整合净优势，且按数据重选成员会虚高 0.09~0.15」。**对齐 G4/G6 ⚠️**：integration vs best single 诚实报为持平/劣（点估已不胜），非「稳健赢家」。

### 5.2 SURV6 定位 —— 与 CV 互证、非否定（0.3657 精确复现、几乎不虚高、0.17 是重选成员的过拟合上界）

SURV6 六维 geomean 是 selection-informed 先验（成员看全数据硬编码定）；CV 是正交的、数据驱动的路径。二者方向一致 = **互证**，把差异量化成「SURV6 的 CV 残差」而非对立：

- **精确复现**：`fixed_surv6`=0.3657（raw）/ 0.2945（lenctrl），逐位复现 R3 六维 geomean → 引擎与生产口径对齐、无实现漂移。
- **SURV6 headline 本身几乎没被膨胀**：0.3657 ≈ honest CV 整合 0.352（差 ~0.01）。因此**不能说「headline 数被夸大 0.17」**。
- **0.17 是「按数据重选融合成员」这一过程的过拟合上界**（oracle 全数据贪心 0.525 − honest CV 0.352），量化的是「若真按数据重选成员能虚高多少」，不是现有固定 SURV6 的虚高。
- 层级关系：SURV6(0.3657) < 单工具 MHCnuggets(0.4466) < CV oracle 上界(0.525)。SURV6 成员从未进过 CV（硬编码看全数据定）——正是 §4.3 自承的 selection bias 的实例。
- **写作立场（互证非否定）**：SURV6 应定位为 selection-informed 先验，CV 是正交的数据驱动校验，方向一致 = 互相印证朱同学 pooling/fusion 工作的稳健性；差异只是「SURV6 的 CV 残差」这一诚实量化，**不是否定该工作**。是否改 headline 表述归袁老师 + 朱同学拍板。

### 5.3 13 条 rationale ledger —— 每个方法学决策的受控实证理由

每条只变一处的受控对照（源 `rationale_ledger.csv`，18 行含子行）。每行 = 决策点 / 选定 / 备选 / Δ / verdict：

| # | 决策点（choice） | 选定（chosen） | 备选（alt） | Δ | verdict |
|---|---|---|---|---|---|
| 1 | nested-CV vs 全数据选 | nested-LOPO | oracle(in-sample) | 膨胀 +0.173 | 全数据选=上界，nested 才诚实 |
| 2 | nested 双层 vs 单层 LOPO | nested 双层 | 单层 LOPO | 0.0（恒等 \|单层−oracle\|<1e-9） | geomean within-patient 独立 → 单层≡in-sample 非真 CV，膨胀同 #1，不当独立数报 |
| 3 | 留患者 vs 留肽 | 留患者(LOPO) | 留肽 | −0.002（≈持平） | ★承认 bundle 折粒度、不 claim 纯单变量 |
| 4 | 守卫 vs 裸指标（全30池） | 守卫选 MHCnuggets 0.4466 | 裸选 HLAthena 0.6272（小n伪迹） | +0.181 | 守卫剔退化相关、挡假冠军 |
| 5 | cover 池 vs 全30（裸 shuffle-null） | cover 0.2733 | 全30 0.5908 | +0.317 | 全30 含 min<8 稀疏工具打乱后仍虚高 → cover 池过滤有价值 |
| 5b | cover vs 全30（守卫 shuffle-null） | cover=全30=0.3906 | — | 0 | 守卫已中和稀疏膨胀，与池过滤是**重叠防线**（非矛盾、非池过滤无用） |
| 6/6b | 聚合等权 vs 逆方差/均值 | Fisher-z 等权 0.525 | invvar 0.545 / 均值ρ 0.492 | — | 等权不让大 n 患者主导 |
| 7 | per-patient vs pooled | per-patient 0.525 | pooled 0.510 | +0.015 | pooled 受跨患者标度混杂 |
| 8/8b | 贪心 vs 穷举 | 贪心(forward) | 穷举 | 0（k=2/k=3） | 贪心是合格优化器；泛化由 oracle−CV 答，别混 |
| 9 | ε/maxdim 敏感性 | 默认 (0.01,6) 0.352 | 峰 (0.02,6) 0.401 | 0.049 | 峰位小漂移，敏感性提示 |
| 10 | 算子 CV 选 vs 钉 geomean | 钉 geomean | 算子 CV 选 | −0.006 | 算子选 DOF 几乎不增益，钉 geomean 省自由度 |
| 11 | DTU 入池 vs 剔 DTU | 含 DTU 0.352 | 剔 DTU 0.290 | 无符号翻转 → `consent_critical=False` | 主结论不依赖 DTU |
| 12 | raw vs lenctrl | raw（主口径） | lenctrl | −0.043，成员不一致 | 控肽长后 CV-最优成员从 {MHCnuggets;netMHCpan_BA;IEDB_Calis} 变 {netMHCpan_BA;MHCnuggets;PRIME}；敏感性提示，主口径仍 raw |
| 13/13b/13c | 算子 geomean vs mean_rank/median/max | geomean | mean_rank / median / max | +0.025 / +0.040 / +0.183 | 同成员集下 geomean 共识/AND 型最稳 |

> 读法：#1/#2 撑「诚实 CV 口径」、#4/#5/#5b 撑「守卫 + 池过滤双防线」、#10/#13 撑「钉 geomean」、#11 撑「主结论 consent-robust」、#12 是控肽长敏感性 caveat（成员漂移）。

### 5.4 四图

- `../figures/fig_fusioncv_kcurve.png` —— k 学习曲线：CV(0.4466→0.4495) vs oracle(0.4466→0.5435)，inflation 带（§5.1）。
- `../figures/fig_fusioncv_procedures.png` —— 五种选择程序 CV + `delta_vs_best_single`（全负）+ paired-p（全 >0.05）（§5.1）。
- `../figures/fig_fusioncv_toolfreq.png` —— cluster-bootstrap 工具入选频率：仅 MHCnuggets 过 0.6 共识阈（§5.1）。
- `../figures/fig_fusioncv_ledger.png` —— 13 条 rationale ledger 的 Δ 森林图（§5.3）。

### 5.5 对齐验收 + 诚实局限

- **G3 ⚠️（部分）**：oracle vs CV 一致性已实证并量化（inflation 0.09~0.15、nested≡单层恒等 #2、null p=0.01 真信号）——但仅 DS2 单集、单层等价于 in-sample 已诚实标注；**跨集（DS1/鼠）复现未做 → G3 全套仍缺**（DS1 全 9mer 无长度方差、鼠数据缺）。
- **G4/G6 ✅（诚实报）**：五程序 delta_vs_best_single 全负、paired-p 全 >0.05、38 不可分带 → integration vs best single 如实报为「点估已不胜、n=9 功效不足未能检出差异」，不写「稳健赢家」。
- **诚实局限**：①单集 DS2、n=9（有效 8）→ 只信配对差与选择膨胀两个量，绝对值有固有虚高 null（§3c 已述）；②跨集复现（DS1/鼠）未做；③lenctrl 口径下 CV-最优成员漂移（#12），主口径 raw 的成员优先级非控长不变量；④no-DTU 臂 consent-critical（§3c），consent 失败时结论强化为「部署单工具 MHCnuggets」。

---

## 六、局限与 TODO

- **单队列**：DS1 全 9mer 无法复现肽长效应，鼠数据缺 → 存在性仅 DS2（n=130, 9 患者），诚实标「待外部验证」。
- **小患者数**：k=9（有效 8），bootstrap CI 已给、不过 0；P102 低方差（peplen nunique=3）天然测不出。
- **机制口径**：Braun 2025 精确配肽浓度经小模型 WebFetch 提取（带引号非逐字），`10 µg`/`µg ml⁻¹` 建议人工核 Methods/Supplementary 原句（TODO）；等质量方向已由 Ott 2017 独立佐证，可靠。
- **未做**：分箱内秩归一（D）仅列未深挖。fusion（geomean）控长下 headline 已验（见 §3b：geomean 仍无监督#1，但对最强单工具从领先软化为持平）。
- **paper 小节**：这两个发现（肽长真实但温和的差异性混杂 + 小 n Fisher-z 虚高 bug）有 benchmark 完整性价值，是否写成稿级小节等袁老师拍板 + 用户确认价值。
