# DEPLOY_TRACKER — 30 工具部署状态总表（10 呈递 + 20 免疫原性）

> 真源：每工具状态 + job_id + 阻塞写这里。详细 4 类信息写 `TOOLS/<tool>.md`。
> 服务 QuantImmu §工具部署总表（lever = 扩为袁 md 30 工具进度视图）。框架真源 = `paper/QuanImmu-Paper-Outline.md` §2.2「30 tools surveyed」表 2。

---

## 🎯 目标 vs 现状（30 工具进度，单一真源）

> 袁老师 md（论文大纲 §2.2 / §1.4 卖点 3）要求系统评测 **30 种工具 = 10 种呈递预测（presentation/binding）+ 20 种免疫原性预测（immunogenicity）**。
> **当前 26/30 接入 benchmark**（2026-06-29：19 基 + 主窗本地批 MHCnuggets/TransHLA/MUNIS/**neoag** + netMHCpan-EL/ImmugenX/**MixMHCpred** 窗产主窗merge）；真源 `merged_all_tools_26tools.xlsx`（34247×75，27 工具列含 MHCflurry 分2）。距 30 缺 ~3-4：andy90 + Seq2Neo（tools2 在跑/解 netCTLpan，poller 盯）+ 备份候选（TLImm 等）。**netMHCpan-Aff 弃**（冗余：netmhcpan_ba 已是 BA-score+netMHCpan_EL）；**NetMHCstabpan 弃换 MixMHCpred**（fakeroot 挡+弱值→PWM 方法更有参考价值）。NeoaPred🗄️搁置/MAAP/Inference/DeepNeo=团队邮件 bonus。
> ⚠️ **计数口径**：19 = apples 主榜（含 HLAthena proxy 单列另计）。呈递 5（4 apples + BigMHC_EL，HLAthena proxy 另列）+ 免疫原 14（含 ICERFIRE/NetTepi）。
> **DTU 工具 `netmhcpan_ba` / `TSCAPE` / `netMHCstabpan` / `ICERFIRE` / `NetTepi` = pending DTU consent**（学术许可禁第三方再分发其软件上跑出的 benchmark 数字，投稿前需取书面同意）。
> 状态图例：✅ 已进 benchmark｜⚠️ 降级/proxy 进 benchmark（标注层次不可 apples-to-apples）｜🔄 部署中/阻塞待跑｜❌ 缺（待补/归属）。下面两张分组表是 30 工具目标的**进度真源**；本文件后半的 10 工具规范表/Tier 分表 = 部署细节归档。

### 表 A — 呈递 / binding 组（目标 10，现 5 ✅ + HLAthena proxy；攻坚补满）

| # | 工具 | 输出分名 | 状态 | 跑的版本 / caveat | 许可 | 归属 |
|---|---|---|---|---|---|---|
| P1 | **netMHCpan-4.1 (BA)** | `netmhcpan_ba`（−Aff，越大越强）| ✅ 进 benchmark | geomean pooling ρ=0.3956 = 全榜聚合最强（max 仅 0.0901）；**DTU pending consent** | DTU 学术（禁再分发数字）| 余嘉 |
| P2 | **MHCflurry 2.0 (presentation)** | `MHCflurry_presentation` | ✅ 进 benchmark | mhcflurry 2.2.1 torch 后端，65 allele 全支持 | Apache-2.0 | 余嘉 |
| P3 | **MHCflurry 2.0 (affinity)** | `MHCflurry_affinity_neg`（−Aff）| ✅ 进 benchmark | 同 P2 同一次推理；top3mean pooling spread 0.50 最大 | Apache-2.0 | 余嘉 |
| P4 | **HLAthena** | presentation proxy 单列 | ⚠️ proxy 进 benchmark | 65-allele 模型；ELISpot AUC 0.51 / ρ 0.08 近随机 = 印证 presentation≠immunogenicity；**仅 presentation baseline proxy，不与免疫原性工具 apples-to-apples** | 学术 | 李紫晨/余嘉 |
| P5 | **netMHCpan Aff / EL 独立列** | netMHCpan_Aff / `netMHCpan_EL` | 🟡 EL ✅ / Aff 待 | **EL ✅ 进表（tools1 窗 2026-06-29，零 HPC：发现 `-xls` 输出本含 EL 列→重 parse 既有 65 个 *_out.xls）**→`netmhcpan_el_DS1DS2_scores.csv`(68494 行 0 nan)→merge 23tools.xlsx(100%)；**DTU pending consent**。Aff 列同法待接 | DTU 学术 | 余嘉/tools1 |
| P6 | **MAAP** | — | ❌ 身份未明 | researcher 两轮多源全检零命中（"MAAP" 在生信均指无关工具：基因组指纹/微阵列等）；袁大纲只给缩写无引用 → **需向袁/徐索取确切全称+DOI/repo**（消歧候选：MHCflurry PS 别名 / MARIA / NetMHC 变体笔误）| TODO | 待袁/徐 |
| P7 | ~~NetMHCstabpan~~ → **MixMHCpred 3.0**（替换）| `MT_MixMHCpred`（Score）| ✅ 进 benchmark | **stabpan 弃**（HPC 无 subuid→fakeroot 挡 apptainer build=pTuneos 同坑，且 stability proxy 弱值，不绕）→ **换更有参考价值的 MixMHCpred 3.0**（Gfeller，**PWM/motif 方法**=对全 NN 类呈递工具方法学正交，Genome Med 2025，HPC `tools_repos/MixMHCpred` 已有零 fakeroot）。2026-06-29 HPC 跑通 11903 肽×39 支持 allele（26 罕见 HLA-C/A66 不支持→NaN）→ patch 26tools.xlsx **91.5% 覆盖**；**per-patient fisherz 0.1411** CI[-0.095,0.362] n=8（binding 信号同 ImmugenX 档）；Score 越高越强不翻；学术免费引 Tadros 2025 | 学术免费(Gfeller) | 余嘉 |
| P8 | **BigMHC_EL** | `BigMHC_EL` | ✅ 进 benchmark | 2026-06-29 接表；`-m=el` base bat{N} 模型，本地 CPU 全量 53582 对（`.cmp` 验证 PASS diff 4.5e-7）；per-patient fisherz 0.108（胜 IM −0.014）；JHU 学术可发非 DTU | 学术非商用 | 余嘉 |
| P9 | **TransHLA**（新候选，2025）| `MT_TransHLA`（prob）| ✅ 进 benchmark | 2026-06-29 本地 WSL2 **RTX4070 GPU** 全量 11903 unique 肽跑通（env transhla py3.10+**transformers4.46.3**[版本矩阵：5.12 删 all_tied_weights_keys 报错→降 4.46；esm2-650M 断流重下]）+patch 进 `merged_all_tools_21tools.xlsx`（34247×65，MT/WT 100%）；**per-patient fisherz 0.0675** CI[-0.167,0.295]（n=9，弱信号 HLA-agnostic 预期同 Repitope）；MIT 可发；⚠️HLA-agnostic（同肽各 allele 同值，报告标 caveat） | MIT | 余嘉 |
| P10 | **MHCnuggets**（新候选）| `MT_MHCnuggets`（−ic50）| ✅ 进 benchmark | 2026-06-29 本地 WSL2 CPU 全量跑通+patch 进 `merged_all_tools_20tools.xlsx`（34247×63，MT 94.1% 填充）；**per-patient fisherz 0.2024** CI[-0.036,0.419]（n=8，正信号同 MHCflurry affinity 档）；env mhcnuggets py3.10+**TF2.10.1/keras2.10**（版本矩阵：TF2.21 keras3 删 `lr`→降 2.10 匹配，未改其码）；JHU BSD-like 可发；⚠️closest_allele 软迁移 | JHU BSD-like | 余嘉 |

### 表 B — 免疫原性组（目标 20，现 14 ✅ + NetTepi 低覆盖；攻坚补满）

| # | 工具 | 输出分名 | 状态 | 跑的版本 / caveat | 许可 | 归属 |
|---|---|---|---|---|---|---|
| I1 | **DeepImmuno** | DeepImmuno | ✅ 进 benchmark | 官方权重；WSL2 全跑通 | 学术 | 余嘉 |
| I2 | **PredIG** | PredIG | ✅ 进 benchmark | 官方镜像（docker recombinant）；边界显著 ρ=0.2286 | 学术 | 余嘉 |
| I3 | **IMPROVE** | IMPROVE | ✅ 进 benchmark·降级 | 官方 Predict；**Expression 特征降级**（feature_calc 缺 self_similarity/antigen.garnish/stabpan）；count-safe top3mean ρ=0.3227 全榜最强稳健 | 学术 | 余嘉 |
| I4 | **NeoTImmuML ★** | NeoTImmuML | ✅ 进 benchmark·降级 | **自训版**（复刻官方 RF+LGB+XGB，**非官方权重**，官方权重不可得）；PPT/论文须标 ★ 非官方、不对标原论文 | 学术 | 余嘉 |
| I5 | **pTuneos** | pTuneos | ✅ 进 benchmark | Pre&RecNeo 子模型（官方逻辑，对账官方 r=1.0）；本地端到端跑通，HPC sif 受 fakeroot 限 | 学术 | 余嘉 |
| I6 | **PRIME** | PRIME | ✅ 进 benchmark | 官方权重（PRIME 2.1 + MixMHCpred 3.0，对账官方 diff=0）；Fisher-Z ρ=0.2794 最强单工具 | 学术免费（Gfeller lab）| 李紫晨/余嘉 |
| I7 | **ImmuneApp** | Immunogenicity_score | ✅ 进 benchmark | 官方权重（py3.7+TF1.15）| 学术 | 李紫晨/余嘉 |
| I8 | **deepHLApan** | deepHLApan（Imm/Bind 双分）| ✅ 进 benchmark | 官方镜像 `biopharm/deephlapan:v1.1`；⚠️肽长混杂警示，去混杂后无信号，不作能力证据 | 学术 | 李紫晨/余嘉 |
| I9 | **BigMHC_IM** | `BigMHC_IM` | ✅ 进 benchmark | `-m=im` 7 模型 ensemble；34247 行 0 NaN | 学术非商用 | 余嘉 |
| I10 | **CNNeo (CNNeoPP)** | `CNNeo` | ✅ 进 benchmark·自训 | 自训 FCNN_TF（PyTorch+TF-IDF，复刻 notebook 超参零改，ValAcc~75%）| MIT | 余嘉 |
| I11 | **IEDB Immunogenicity (Calis)** | `IEDB_Calis` | ✅ 进 benchmark | IEDB_Immunogenicity-3.0 纯统计；42 allele-specific mask，其余默认 mask | NPOSL-3.0 | 余嘉 |
| I12 | **Repitope** | ImmunogenicityScore | ✅ 进 benchmark | R 4.3.3 ERT 后端；**HLA-agnostic（不吃 HLA）→ 同肽各 allele 填同值（caveat 须标）**；8-11mer 外 NaN | MIT | 余嘉 |
| I13 | **T-SCAPE ★** | `MT_TSCAPE` | ✅ 进 benchmark（待 merge）| 官方权重 + 修 2 个官方 repo bug（peptide 列名小写 + pmhc_im_neo 加载）；MT-only；负相关 ρ=-0.1386；**DTU/CC BY-NC-ND 4.0 学术非商用·ND 禁衍生发布·pending consent** | CC BY-NC-ND 4.0 | 余嘉 |
| I14 | **NeoaPred** | `MT_NeoaPred`（Foreignness）| 🗄️ **搁置（用户 2026-06-29 拍板）** | 结构 foreignness **物理模拟**工具（OpenMM 弛豫）；反复 HPC TIMEOUT（job 1496801 跑满 16h 被 kill，前 job 9.5h 没起）→ **不再死磕**，第 20 槽改用干净 CPU 备份工具填。残留：HPC `full_a/outs/part_000~007/foreignness.csv` 部分覆盖，真想要可捡（覆盖率低）。卡槽 b3cc9faf 已 release。**非 NO-GO（区别 ImmunoStruct 永久排除），是搁置** | Apache-2.0 | 余嘉 |
| I15 | **ICERFIRE 1.0** | `icerfire_score`（100−rank）| ✅ 进 benchmark | 2026-06-29 patch 进活真源；**per-patient fisherz 0.3077 登顶全工具** CI[0.078,0.507] 显著（>PRIME 0.279>IMPROVE 0.250）；**DTU pending consent**（发表数字待袁老师拍板）| DTU 学术 | 余嘉 |
| I16 | **Seq2Neo** | `Seq2Neo_immuno`（连续 0-1）| 🔄 kit 就绪·阻塞 | `immuno` 子模块单喂肽+HLA（`seq2neo immuno --mode multiple`，CSV `Pep,HLA`）；`HPC/deploy/seq2neo/` 4 文件就绪；**阻塞=netCTLpan 1.1.b（DTU）未部署 + linux-only**；AFL-3.0 可发；IJMS 2022 | AFL-3.0 | 余嘉 |
| I17 | **DeepNeo / DeepNeo-v2** | — | 🔴 BLOCKED-待作者回信 | **抢救穷尽（researcher 2026-06-29）**：Wayback 唯一快照(2023-01-09)是代码提交前空壳 README、raw 仅存 1 张 png；无 fork（forks 404）、无 Zenodo/figshare/HF deposit（NAR Data Avail 仅指已死的 deepneo.net）、kaistomics 现存仓无 v1 残留（DeepNeo-BCR=无关 B 细胞版）。**唯一路=邮件通讯作者 Jung Kyoon Choi `jungkyoon@kaist.ac.kr`**（发前用 PMC10320182 核拼写）索 v1 代码+权重。→ 并行物色替代双输出免疫原工具补位，不空等 | TODO | 余嘉/待作者 |
| I18 | **内部 Inference 8-class** | Inference class_0..7 | ❌ 待源码 | 袁 md §3.1 引用（class_2/3 +0.31）；**徐伊琳组源码未确认** → 需向徐伊琳组索接口/源码 | 内部 | 徐伊琳组 |
| I19 | **NetTepi 1.0** | `MT_NetTepi` | ⚠️ 进表·低覆盖 | 2026-06-29 patch 进表；per-patient fisherz 弱 0.023（n=8）；仅 13 HLA **零 HLA-C** → 本地仅 8/35 allele=34.2% 行有分；依赖 NetMHCcons+NetMHCstab+Calis2013；**DTU pending consent** | DTU 学术 | 余嘉 |
| I20 | **ImmugenX** | `MT_ImmugenX`（sigmoid 0-1）| ✅ 进 benchmark（待 merge）| 2026-06-29 本地 WSL2 **CPU** 全量 53582 对跑通（官方 TorchScript JIT，pMHC-only genesis_pub_config，无外部 binary）→ `scripts/out/newtools/ImmugenX_DS1DS2_scores.csv`（34247 行 **MT/WT 100% 覆盖**，65 allele 全支持，0 NaN）；ImmugenX∈[0.0714,0.8577] mean 0.252；env=py3.9+**pip CPU torch1.12.0+cpu**（版本矩阵：conda torch1.12 与 numpy 双 BLAS/iomp5 冲突 `free(): double free in tcache`→改 pip cpu wheel 解；移冗余 torchtext）；副产 Stability 列落库不进主表；方向越高越强不翻转；**许可=Academic Software License v1.0（GPL 式），Section 0 明示「输出非衍生软件不受约束」→ benchmark 数字可发表，非 DTU pending**（唯一红线=别把 runner 代码/JIT 权重进公开 repo）；per-patient 信号读数 pending merge 后 metrics 节点（需 per-peptide pooling）；PLOS Comput Biol 2024 DOI 10.1371/journal.pcbi.1012511，AUROC 0.619 | Academic SW License v1.0 | 余嘉 |

**🎯 免疫原补位候选（攻坚扩搜 2026-06-29，免依赖 blocker 即补满 20）**：
- **MUNIS** ✅ **进 benchmark**（2026-06-29 本地 WSL2 RTX4070 GPU 全量 50574 对跑通+patch 22tools.xlsx，MT 94.1%；**per-patient fisherz 0.0477** CI[-0.190,0.280] n=8 弱信号=EL 呈递模型印证 presentation≠immunogenicity）— Nat Mach Intell 2025（PMC11847706）；repo github.com/jwohlwend/munis；Zenodo `10.5281/zenodo.14219509`（840MB 权重）；**CC-BY-4.0 可发**；肽 8-15mer + HLA-I（编码 `HLA-A02:01`，clean_mhc_name 去星号）；ESM-2-8M 5-model ensemble；env munis_env torch2.3.1+**setuptools<80**（pl2.0.2 需老 pkg_resources，esm2-8M 断流重下）；score=EL prob 不翻向。
- **immunogenicity_predictor (andy90)** ✅ kit 就绪·HPC 跑 — repo github.com/andy90/immunogenicity_predictor；**MIT**；`HPC/deploy/andy90_immpred/` 四件套就绪（py_compile✅，官方核：amp=self*foreign/binding，amplitude 越高越强直接用，输出列 `HLA,peptide,amplitude,immunogenic`）；肽 8-11mer + HLA-I。⚠️**实质需 netMHCpan binary（算 binding %Rank）→ HPC 跑非纯本地**；✅**版本已定（用户 2026-06-29 放行）：用 HPC 现有 netMHCpan 4.1 + 论文注明刻度 caveat，不装 4.0**。烟测仍须核实际 col13 是否 %Rank（确认列位再全量）。
- **TRAP** ⚠️备选 — github.com/ChloeHJ/TRAP；CC-BY-NC-SA；肽 9-10mer（窄）+ 需 NetMHCpan rank 特征；权重在 Google Drive；CPU 可跑。
> → 用 MUNIS + andy90 即把免疫原补到 20，**不依赖 DeepNeo(blocked)/MAAP(身份未明)/内部 Inference(团队)**——这三个变 bonus。

**未做成 / 放弃（不计入 20，诚实标注，勿假装已有）**：
- **MHLAPre** — ❌ **未做成**（🔴 权重缺：全网 GitHub/Kaggle/Zenodo/HF 搜空；ProcessData npy 缺 + 预处理拼装码被注释 → 自训路也不通；唯一出路 = 邮件作者 23B903048@stu.hit.edu.cn）。许可：repo 无 LICENSE。归属：李紫晨/余嘉。
- **ImmunoStruct** — ❌ **NO-GO 诚实放弃**（三重硬 blocker：infer 锁预构建 PyG 图无通用推理入口 + AF2 不可承受 ~500GB MSA+数百 GPU·h + HLA 覆盖训 27 vs DS 65 不足）。Yale 许可不挡但工程封死。归属：余嘉 §Tier-3。

**一句话结账（2026-06-29 攻坚口径，30 可达不靠 blocker）**：**22/30 接入**（呈递 7[+MHCnuggets ρ=0.2024 +TransHLA ρ=0.0675] + 免疫原 15[+MUNIS ρ=0.0477]），今天本地端到端跑通 3 工具（MHCnuggets/TransHLA/MUNIS）。剩 8 槽分 3 并行窗（DAG tools1/2/3 + paper）攻：andy90/Seq2Neo/ImmugenX/netMHCpan Aff·EL/NetMHCstabpan + MAAP/Inference/DeepNeo(bonus)。攻坚扩搜后**30 凑满路径全可部署/许可自由，不依赖任何 blocker**：
- 呈递 10 = P1-4 + BigMHC_EL✅ + TransHLA(kit就绪) + MHCnuggets(kit就绪) + netMHCpan Aff列 + EL列 + NetMHCstabpan(解glibc)。
- 免疫原 20 = I1-13 + ICERFIRE✅ + NetTepi✅ + NeoaPred(解HPC) + Seq2Neo(解netCTLpan) + ImmugenX + **MUNIS** + **andy90**。
- **bonus（解了更好不解也满 30）**：DeepNeo(BLOCKED 待作者)、MAAP(待袁/徐全称)、内部 Inference(待徐伊琳组)。
- 仅 MHLAPre(无权重)、ImmunoStruct(NO-GO) 永久排除。**不降级——每个 30 内槽位都有许可自由的实工具。**

---

## 规范状态总表（首批 10 工具·部署细节归档）

> 📌 30 工具进度真源 = 顶部「表 A / 表 B」。本表是**首批 10 工具（余嘉核心 5 + Wave3 5）的逐工具部署细节归档**，仍是这 10 个的细节真源；下方两张分表（第一批 5 / Wave3 5）= 更细的部署步骤归档，状态以本表为准。
> 教训：旧表「状态」列单维枚举混了三件事（部署到第几步 / 跑哪个版本 / 进没进 benchmark），导致 NeoTImmuML（自训版进了 benchmark）被读成"没做成"、PRIME/ImmuneApp/deepHLApan（已进 benchmark）被读成"停在烟测"。本表按维度拆列。
> **benchmark 列以 `analysis/metrics_ds2_9tools.csv` 为真源回填**（9 工具各 9 行 = 3 聚合×3 阈值；MHLAPre 0 行 = 唯一未进）。
>
> ⚠️ **2026-06-27 HLA-FIX caveat（部署状态不变，benchmark 数字变）**：本表「进 benchmark」列只表「工具是否跑通进表」，**与部署完成度无关、不受 HLA-FIX 影响**。但 benchmark 的**结论数字**已因 P101/P102 等位伪迹修正而变：PredIG 全局 Spearman 显著性失效、TSCAPE 翻显著负、deepHLApan 有 merge bug。HLA-dependent 工具的 P101/P102 格已置 NaN 待 Phase B 重推理。**当前有效 benchmark 真源 = `analysis/metrics_ds2_fixed_exclP101P102.csv`（corrected-excl），非 `metrics_ds2_9tools.csv`**。详见 04_LOG Entry HLA-FIX / HLA-FIX2。

| # | 工具 | 归属 | clone | env | 烟测 | **进 benchmark** | 跑的版本 | 结论 |
|---|---|---|---|---|---|---|---|---|
| 1 | DeepImmuno | 余嘉(1) | ✅ | ✅ | ✅ | ✅ | 官方权重 | **完成** |
| 2 | PredIG | 余嘉(1) | ✅ | ✅镜像 | ✅ | ✅ | 官方镜像 | **完成** |
| 3 | pTuneos | 余嘉(1) | ✅ | ✅镜像 | ✅ | ✅ | Pre&RecNeo 子模型(官方逻辑) | **完成**(本地端到端;HPC sif 受 fakeroot 限) |
| 4 | IMPROVE | 余嘉(1) | ✅ | ✅ | 🟡 | ✅ | 官方 Predict, Expression 特征降级 | **完成**(主路;feature_calc 缺 self_sim/garnish/stabpan) |
| 5 | NeoTImmuML | 余嘉(1) | ✅ | ✅ | ⚠️ | ✅ | **自训版**(复刻官方 RF+LGB+XGB, 非官方权重) | **完成·降级标注**(官方权重不可得→自训替代;PPT 标★非官方,不对标原论文) |
| 6 | PRIME | 李紫晨(3) | ✅ | ✅ | ✅ r=1.0 | ✅ | 官方权重 | **完成** |
| 7 | ImmuneApp | 李紫晨(3) | ✅ | ✅ | ✅ | ✅ | 官方权重 | **完成** |
| 8 | deepHLApan | 李紫晨(3) | ✅ | ✅镜像 | ✅ | ✅ | 官方镜像 | **完成** |
| 9 | HLAthena | 李紫晨(3) | ✅ | ✅镜像 | ✅ | ✅ **单列 proxy** | 官方 65-allele 模型 | **完成·presentation proxy**(预测提呈非免疫原性;ELISpot 近随机 AUC 0.51;不与免疫原性工具 apples-to-apples) |
| 10 | **MHLAPre** | 李紫晨(3) | ✅ | ☐ | ❌ | ❌ | — | **未做成**(🔴 无权重+ProcessData npy 缺+预处理拼装码被注释→自训路也不通;全网搜权重空;唯一出路=邮件作者 23B903048@stu.hit.edu.cn) |

**一句话结账**：10 工具 → **9 进 benchmark**（8 免疫原性工具 apples-to-apples + HLAthena 1 个 presentation proxy 单列）+ **1 个 MHLAPre 完全阻塞未做成**。NeoTImmuML 是「官方权重缺、用自训版进表并诚实降级标注」，**不是没做成**。
> 归属：「余嘉(1)」= 余嘉核心 5 工具（第一批）；「李紫晨(3)」= 2026-06-24 袁老师分工归李紫晨的 Wave3 5 工具，余嘉**超额做的**（PRIME/ImmuneApp/deepHLApan/HLAthena 已跑通，可移交参考，不回退）。

---

## §Tier-3 扩张工具（2026-06-26，重型 GPU+结构，D-tools3 窗）

> 三工具 recipe 经 researcher×3 联网钉死。**关键发现：T-SCAPE 只需 `best_param/pmhc_im_neo`=0.53GB（非全 54.7GB，那是 BA/EL 等不用的 task），→ 改本地 WSL2 跑免 HPC**。NeoaPred Docker Hub 在 HPC 不通→本地 WSL2 docker。**ImmunoStruct = NO-GO 诚实放弃**（三重硬 blocker）。

| # | 工具 | 归属 | 输入 | 部署状态 | 进 benchmark | 结论 |
|---|---|---|---|---|---|---|
| T3-1 | **T-SCAPE** | 余嘉 §Tier-3 | CSV（Allele,peptide），MT-only，≤20mer，HLA `HLA-A*02:01` | ✅ **RUN_DONE**（本地 WSL2 CPU，全量 32178 推理完，merge→tscape_scores.csv）| ✅ 待 merge | 33939/34247 有分（308 NaN=allele 不在 MHC_classI_pseudo.csv），score 0.0057-0.7716；CC BY-NC-ND 4.0 **学术非商用**；**用官方权重+修复 2 个官方 repo bug 跑**（输入列名 peptide 小写 + pmhc_im_neo 加载/task_dict，patch 依据见 04_LOG Entry T3，非原版代码）；权重仅 0.53GB；repo seoklab/T-SCAPE，Sci Adv DOI 10.1126/sciadv.adz8759 |
| T3-2 | **NeoaPred** | 余嘉 §Tier-3 | CSV（ID,Allele,WT,Mut），严格 9mer，HLA 缩写型 `A2402` | 🔄 **HPC_FULL**（端到端 smoke PASS；本地全量实测 ~60h 不可行[OpenMM 弛豫并行不加速，内存带宽限]→ 用户拍板上 HPC：docker save 3.6GB→上传→singularity build→gpu4090 节点 48核 N=24 并行 sbatch）| ⏳ pending | scope=严格 9mer（5692 unique，11384 弛豫）；输出 Foreignness_Score 越高越强，只产 MT 列；Apache-2.0，DOI 10.1093/bioinformatics/btae547 AUROC 0.81；env 全在 /var/software（非 /root）→ singularity 非 root 可读，绕 pTuneos 坑 |
| T3-3 | **ImmunoStruct** | 余嘉 §Tier-3 | — | ❌ **NO-GO（诚实放弃）** | ❌ 永不 | 三重硬 blocker：①infer 脚本锁预构建 PyG 图、无通用「肽+HLA」推理入口 ②AF2 不可承受（34247 行需 ~500GB MSA 库+数百 GPU·h ColabFold）③HLA 覆盖不足（训 27 vs DS 65）。Yale 许可不挡但工程封死。repo KrishnaswamyLab/ImmunoStruct，Nat MI 2025。**stretch 工具跑不通=诚实 block 非失败** |

### NeoaPred 部署文件（HPC/deploy/neoapred/）

| 文件 | 作用 |
|---|---|
| `HPC/deploy/neoapred/prep_neoapred_input.py` | master_backbone → 严格 9mer 过滤 → unique(MT,WT,HLA)=5692 → HLA 转缩写型 A2402 → neoapred_input.csv（ID,Allele,WT,Mut）+ map；--smoke N |
| `HPC/deploy/neoapred/run_neoapred_docker.sh` | 封装官方 docker detach 流程（起容器→cp→exec PepFore→cp 回→停删）|
| `HPC/deploy/neoapred/build_singularity_hpc.sh` | HPC fallback 模板（docker save→sftp→singularity build）；标 TODO /root 访问坑待验 |
| `HPC/deploy/neoapred/merge_neoapred.py` | 读 MhcPep_foreignness.csv + map → 回贴 bb_idx → neoapred_scores.csv（bb_idx, MT_NeoaPred）|
| `HPC/deploy/neoapred/README.md` | 部署步骤 + 4 类信息 + 已知坑 + 命令 |

> ⚠️ NeoaPred：HLA 缩写型 `A2402`（非 HLA-A*24:02）；严格 9mer；Python3.6 锁死（Docker 绕）。

### T-SCAPE 部署文件（HPC/deploy/tscape/）

| 文件 | 作用 |
|---|---|
| `HPC/deploy/tscape/prep_tscape_input.py` | 读 master_backbone → unique (MT, HLA) 对 → tscape_input.csv + tscape_input_map.csv；支持 --smoke N |
| `HPC/deploy/tscape/setup_tscape_hpc.sh` | DTN 登录节点：clone repo + patch dropout bug（:326）+ conda env + HF 权重下载 |
| `HPC/deploy/tscape/run_tscape.sh` | GPU 节点推理：mhc_pseudo_matching + inference_csv 两步 |
| `HPC/deploy/tscape/submit_tscape.sbatch` | SLURM sbatch（gpu4090, shuihuawang, 1 卡）|
| `HPC/deploy/tscape/merge_tscape.py` | 读 T-SCAPE output.csv + map → 回贴 bb_idx → tscape_scores.csv（列 bb_idx,MT_TSCAPE）|
| `HPC/deploy/tscape/README.md` | 部署步骤 + 4 类信息 + 已知坑 + 烟测命令；顶部标「学术非商用 CC BY-NC-ND 4.0」|

> ⚠️ **许可：CC BY-NC-ND 4.0，仅限学术非商用**。ND 条款禁止衍生发布，投稿/报告需标注。
> ⚠️ **dropout patch 必打**：clone 后改 `src/model_fused.py` 第 326 行加 `training=self.training`，否则推理结果非确定性（PR #3 未合并）。
> ⚠️ 权重 54.7GB，务必在 DTN 预下，GPU 节点不联网。

---

## §Tier-2 扩张工具（2026-06-26，apples-to-apples 扩充）

| # | 工具 | 归属 | 输入 | 部署状态 | 进 benchmark | 结论 |
|---|---|---|---|---|---|---|
| T2-1 | **ICERFIRE 1.0** | 余嘉 §Tier-2 | 无表头 CSV mut,wt,HLA（HLA 去星去冒号）| ⚠️ **BLOCKED_PENDING**（binary 待 DTU 下载 health-software@dtu.dk）| ❌ pending | 脚本就绪，CLI/列名 TODO 待下载核实；pending_DTU_consent=True |
| T2-2 | **BigMHC -m=im** | 余嘉 §Tier-2 | CSV（mhc,pep；HLA-A*02:01 格式，无需转换）| ✅ **RUN_DONE**（本地 Windows CPU，7模型 ensemble，53582 对）| ✅ 待 merge | 34247 行 MT+WT 0 NaN，BigMHC_IM 0.0-0.95；**EL 对官方 .cmp 验证 PASS(diff 4.5e-7)**=权重完整管道正确；im=7模型 ensemble(bat{512..32768}/im 各4微调层+从父EL目录补基层)；repo git历史臃肿→`fetch_repo2.py` 无API逐文件下2.5GB绕限流；⚠️Windows 须 `--jobs`小(spawn pickle大数据OOM)+RAM独占(与他job并发OOM-kill)；`-t`=tgtcol非线程；学术非商用，发数字✅；输出 `BigMHC_DS1DS2_scores.csv`(MT/WT_BigMHC) |

### BigMHC -m=im 部署文件（HPC/deploy/bigmhc_im/）

| 文件 | 作用 |
|---|---|
| `HPC/deploy/bigmhc_im/prep_input.py` | 读 uniq_pep_hla.csv（53582 行）→ bigmhc_inputs/bigmhc_input.csv（mhc,pep；双列+表头）；--smoke N |
| `HPC/deploy/bigmhc_im/run_bigmhc_im.py` | Python 启动器：调 repo/src/predict.py -m=im -d=cpu；--smoke / --device / --jobs |
| `HPC/deploy/bigmhc_im/parse_output.py` | 读 bigmhc_output.prd（mhc,pep,tgt,len,BigMHC_IM）→ join universe.csv → BigMHC_DS1DS2_scores.csv（4-key + MT_BigMHC + WT_BigMHC）|
| `HPC/deploy/bigmhc_im/NOTES.md` | repo 结构 / predict.py CLI / 输出列名 / HLA 格式 / CPU 强制 / 许可 / LFS / 坑 |

> ⚠️ **许可：BigMHC Academic License（学术非商用，Johns Hopkins Karchin Lab）**：非商用研究/教学/非营利自由使用；发数字✅；商用需另签协议。
> ⚠️ **git clone 需 git-lfs**（~5GB 含模型权重）；clone 到 `HPC/deploy/bigmhc_im/repo/`。
> 输出方向：BigMHC_IM ∈ [0,1]，越高越免疫原性，直接用（无需翻转）。
> 输出列名 `BigMHC_IM` 已核实自 src/cli.py `_parseModel`（`args.modelname = "BigMHC_IM"`）。

### ICERFIRE 1.0 部署文件（HPC/deploy/icerfire/）

| 文件 | 作用 |
|---|---|
| `HPC/deploy/icerfire/prep_icerfire.py` | 读 master_backbone → 无表头 icerfire_input.csv + icerfire_index.csv（行序 join key）|
| `HPC/deploy/icerfire/run_icerfire.sh` | SLURM sbatch 骨架；CLI 命令占位 TODO 待 README 核实 |
| `HPC/deploy/icerfire/parse_icerfire.py` | 读 ICERFIRE 输出 + index → 回贴 bb_idx → icerfire_DS1DS2_scores.csv；方向翻转 icerfire_score=100-rank |
| `HPC/deploy/icerfire/README.md` | 输入格式、HLA 转换、方向翻转、pending 红线、TODO |

> ⚠️ **pending_DTU_consent=True**：ICERFIRE binary 尚未在 HPC，需向 health-software@dtu.dk 申请学术下载后才能真跑；所有输出列标 pending_DTU_consent=True。
> 输出方向：ICERFIRE 原始 rank 0=最强免疫原；脚本内翻转为 icerfire_score=100-rank（越高越强，与其他工具方向一致）。

---

## §Tier-0 扩张工具（2026-06-26，CPU 轻量·MIT 自由·本地可跑）

| # | 工具 | 归属 | 输入 | 部署状态 | 进 benchmark | 结论 |
|---|---|---|---|---|---|---|
| T0-1 | **CNNeo (CNNeoPP)** | 余嘉 §Tier-0 | CSV（peptide,hla；标准 HLA-A*02:01），8-14mer，MT+WT 均喂 | ✅ **RUN_DONE**（本地 Windows 自训 FCNN_TF ValAcc~75% + 推理 53582 对）| ✅ 待 merge | score 0.13-0.96，34247 行 0 NaN；FCNN_TF（PyTorch+TF-IDF，复刻 notebook 超参零改）；MIT；repo AaronChen007/neoantigen；输出 `CNNeo_DS1DS2_scores.csv`(MT/WT_CNNeo) |
| T0-2 | **MHCflurry 2.0** | 余嘉 §Tier-0 | CSV（peptide,allele；标准 HLA-A*02:01，无需转换）| ✅ **RUN_DONE**（本地 conda env qib_mhcflurry，65 allele 全支持，53582 对）| ✅ 待 merge | Apache-2.0；mhcflurry 2.2.1 torch 后端；烟测已知强免疫原肽 sanity 通过；34247 行 0 NaN；输出 `MHCflurry_DS1DS2_scores.csv`(MT/WT_presentation + MT/WT_affinity_neg)；⚠️env 内须 PYTHONUTF8=1（yaml GBK 坑）|
| T0-3 | **IEDB Immunogenicity (Calis)** | 余嘉 §Tier-0 | per-allele 肽 txt（HLA 去星去冒号 HLA-A0201）| ✅ **RUN_DONE**（本地 Windows 纯统计秒级，65 allele）| ✅ 待 merge | NPOSL-3.0 自由可发；42 支持 allele 用 allele-specific mask，其余默认 mask（P1,P2,Cterm）；34247 行 0 NaN；输出 `IEDB_Calis_DS1DS2_scores.csv`(MT/WT_IEDB_Calis)；工具 = IEDB_Immunogenicity-3.0 py3 |
| T0-4 | **Repitope** | 余嘉 §Tier-0 | 肽列表（8-11mer，⚠️HLA-agnostic 不吃 HLA）| ✅ **RUN_DONE**（本地 R 4.3.3 cores=6，7437 肽 CPP 特征+ERT）| ✅ 待 merge | MIT 自由可发；34247 行 MT/WT 各 22391 有分（12-14mer NaN=超 8-11mer 限），ImmunogenicityScore 0.06-0.61；**HLA-agnostic→同肽各 allele 填同值(caveat 须标)**；extraTrees(ERT后端)CRAN已下架→Archive装源码版+Rtools43编译；Mendeley FST 实测仅127MB(`*_RepitopeV3.fst`)；修2 coder bug(ofile/`$MinimumFeatureSet`)；repo masato-ogishi/Repitope v3.1.7；输出 `Repitope_DS1DS2_scores.csv`(MT/WT_Repitope) |

### CNNeo 部署文件（HPC/deploy/cnneo/）

| 文件 | 作用 |
|---|---|
| `HPC/deploy/cnneo/prep_input.py` | 读 uniq_pep_hla.csv（53582 行）→ unique (peptide,hla) 对 → cnneo_input.csv + cnneo_input_map.csv；--smoke N |
| `HPC/deploy/cnneo/run_cnneo.py` | 训练+推理一体：首次自动从 repo/training_data/training_data.xlsx 训练 FCNN_TF（或 --model cnn_biobert），保存 weights/；输出 cnneo_raw_output.csv（peptide,hla,score,label）；--smoke N |
| `HPC/deploy/cnneo/parse_output.py` | 读 cnneo_raw_output.csv → join universe.csv → CNNeo_DS1DS2_scores.csv（4-key + MT_CNNeo + WT_CNNeo）|
| `HPC/deploy/cnneo/NOTES.md` | repo 结构 / 框架 / 权重状态 / HLA 格式 / 肽长 / 训练 recipe / 已知坑 |
| `HPC/deploy/cnneo/repo/` | git clone AaronChen007/neoantigen（含 training_data.xlsx + 三个 ipynb）|
| `HPC/deploy/cnneo/weights/` | 训练后权重目录（fcnn_tf_model.pth + fcnn_tf_vectorizer.pkl）|

> 输出方向：CNNeo score ∈ [0,1]，越高越免疫原（softmax class=1 概率），直接用（无需翻转）。
> 关键坑：FCNN_BioBERT 子模型需 BA/TAP 等额外特征列，当前输入不支持，排除；FCNN_TF 和 CNN_BioBERT 仅需 peptide+HLA，均可用。
> 首次跑时长：FCNN_TF 训练 CPU ~5-15 分钟（epochs=45）；CNN_BioBERT 训练 CPU ~数小时（BioBERT 嵌入重），推荐 GPU 节点。

---

## 本地部署环境（重要）
- **本机 WSL2 Ubuntu 24.04**（GPU 直通 RTX 4070 可见）= 本地部署/烟测主战场。这些工具多为 Linux-only 老链（TF2.3 / Py2.7 / netMHCpan Linux 二进制），**Windows 跑不动**（且 DeepImmuno repo 含 `HLA-A*0101.json` 非法 `*` 文件名，NTFS 无法 checkout）→ 一律在 WSL2 ext4 原生部署。
- WSL 部署根目录：`~/quantimmu/`（`tools_repos/` 各工具 repo + `smoke/` 烟测产物）；conda 在 `~/miniconda3`。
- HPC（dtn.hpc.xjtlu.edu.cn / jiayu2403）= 正式跑大数据时用；本地 WSL2 先把每个工具跑通 + 摸清 4 类信息。

## 状态总表（第一批 5 工具·部署细节归档）

> 📌 进度结论以**顶部规范状态总表**为准；本表保留部署/阻塞细节供查。

| 工具 | Wave | clone | 环境 | 权重下载 | example 烟测 | 4类信息收齐 | 状态 | 阻塞 |
|---|---|---|---|---|---|---|---|---|
| DeepImmuno | 1 | ✅ | ✅ | ✅ | ✅ | ✅ | **SMOKE_PASS** | 无（WSL2 全跑通，单条+批量）|
| PredIG | 1 | ✅ | ✅镜像 | ✅ | ✅ | ✅ | **SMOKE_PASS** | 无（docker 镜像跑通 recombinant，输出 PredIG 分）|
| NeoTImmuML | 1 | ✅ | ☐ | — | ☐ | ✅ | **PARTIAL** | notebook 无预训练权重+须R算78特征；信息齐，跑通需重训 |
| IMPROVE | 2 | ✅ | ✅ | ✅(LFS) | 🟡 步骤2 | ✅ | **PARTIAL** | Predict步✅；DTU工具(netMHCpan-4.1/stabpan/2.8)全✅通；feature_calc 还差 self_similarity/antigen.garnish |
| pTuneos | 2 | ✅ | ✅镜像 | ✅自带 | ✅端到端 | ✅ | **DONE(本地)** | example VCF 端到端跑通(VEP cache+修8坑→40新抗原)；Pre&RecNeo 子模型跑 ELISpot 32178 肽对进 benchmark(对账官方 r=1.0)。HPC sif 受限(非root/fakeroot)未真跑 |

状态枚举：TODO / IN_PROGRESS / SMOKE_PASS / DONE / BLOCKED（标原因，不假装跑通）

### HPC 部署状态（dtn.hpc.xjtlu.edu.cn / `/gpfs/work/bio/jiayu2403/quantimmu/`）
> 上表是本地 WSL2 验证；团队要求最终在 HPC。HPC 环境：Singularity 3.11.3 + module miniconda3/22.11.1；出网 github/pypi/DTU 通、Docker Hub 不通。

| 工具 | HPC 状态 | 说明 |
|---|---|---|
| DeepImmuno | ✅ **SMOKE_PASS** | env `envs/deepimmuno`，单条烟测 0.5324646830558777（=本地）|
| IMPROVE | ✅ **Predict SMOKE_PASS** | env `envs/improve`(py3.11+np2.4+sk1.9)；Predict Simple 出 mean_prediction_rf 100 行(=本地)。feature_calc 待 DTU 工具传 HPC |
| NeoTImmuML | ✅ env ready | env `envs/neotimmuml`(py3.10+lgbm4.6+xgb3.2)，demo 加载 OK。notebook 性质需重训才预测(同本地) |
| PredIG | ✅ **SMOKE_PASS** | predig.sif(4.6G) `singularity run --writable-tmpfs -B ...` recombinant 烟测 PredIG=0.0061380286(=本地) |
| pTuneos | 🟡 sif built / ✅本地端到端 | ptuneos.sif(1.7G)build✅。HPC run 受限：镜像程序在 /root，singularity 非root访问拒+无fakeroot(无subuid映射)。**本地 WSL2 docker 已端到端跑通**(example VCF 40 新抗原 + Pre&RecNeo 跑 ELISpot 进 benchmark)。HPC 真跑需 fakeroot 或重打包到非/root + VEP cache |
| netMHCstabpan | ⚠️ 容器待配 | 二进制需 glibc≥2.29(predig.sif有2.35) **且** tcsh(predig.sif没装) → wrapper跑不了。仅 IMPROVE feature_calc Stability 特征需(Predict 已✅不受影响)。彻底解=建 ubuntu+tcsh sif 或直调 binary 绕 wrapper |
| netMHCpan-4.1 | ✅ HPC 跑通 | 传配好的(53M含三件) + 重配 NMHOME → test.pep 11 行（HPC el8 原生跑，不用 vsyscall）|
| netMHCpan-2.8 | ✅ HPC 跑通 | test.pep 11 行 |
| netMHCstabpan-1.0 | ⚠️ glibc 挡 | 二进制需 **GLIBC_2.29**，HPC el8 仅 **glibc 2.28** → 原生跑不了（与本地 vsyscall 相反的兼容问题）。仅 IMPROVE feature_calc 的 Stability 特征需它（Predict 步不需，HPC 已✅）→ 需 singularity 容器(新 glibc)包它，随 PredIG/pTuneos 镜像批一起 |
| NeoTImmuML env | 🔄 | conda py3.10 装中 |

---

## 部署排序逻辑（易→难，许可解耦）
- **Wave 1（无学术许可依赖，先上）**：DeepImmuno（最干净）→ PredIG（容器绕依赖）→ NeoTImmuML（先找源码 URL）。
- **Wave 2（依赖 netMHCpan 等学术许可，到位后上）**：IMPROVE（核心简单卡外部工具）→ pTuneos（最难，老环境+全基因组）。

---

## 每工具标准部署 6 步
按 `project/HPC_WORKFLOW.md` + paramiko 模板（HPC: dtn.hpc.xjtlu.edu.cn / jiayu2403 / gpu4090）：
1. **本地 clone repo + 读官方 README/example** → 把已知事实填 `TOOLS/<tool>.md`。
2. **建隔离环境**：conda env（DeepImmuno/IMPROVE/NeoTImmuML）或 Singularity/Docker（PredIG/pTuneos）。版本严格按官方 pin（红线：超参/版本禁臆想，查不到标 TODO）。
3. **DTN 预下权重/模型**（GPU 节点不能联网，登录节点 wget/git-lfs 到 cache）。
4. **bundled example 烟测**：用 repo 自带 example 跑通，存 stdout + 输出文件，确认产出分数。
5. **记录 4 类信息**进 `TOOLS/<tool>.md`（输入模板 / 参数 / 输出格式含义 / 简介特点）。
6. **更新本表 + 04_LOG**（状态 + job_id/路径）。

> 拍板点：HPC 上传新代码/数据/许可证 = 对外传输，每次上传前一行报。其余自主推进。

---

## 学术许可申请清单（许可均已解决，状态同步至 2026-06-24）

| 许可工具 | 用途 | 申请处 | 状态 |
|---|---|---|---|
| netMHCpan-4.1 | pTuneos + IMPROVE 的 HLA 结合预测 | DTU Health Tech | ✅ **HPC 装+跑通** `ext_tools/netMHCpan-4.1`（官方 test.pep PASS）|
| netMHCpan-4.0 | pTuneos scoring | （pTuneos 镜像内置）| ✅ **镜像自带** `bm2lab/ptuneos:v2.1` 内 `/root/software/netMHCpan-4.0`，免单独申请 |
| **netMHCpan-2.8** | netMHCstabpan 的后端（必需）| DTU services.healthtech.dtu.dk/services/NetMHCpan-2.8/ | ✅ **HPC 跑通** `ext_tools/netMHCpan-2.8`（el8 原生跑，test.pep 11 行；WSL2 曾 segfault → 已挪 HPC 解决）|
| netMHCstabpan-1.0 | IMPROVE 的 HLA 稳定性 | DTU Health Tech | ⚠️ **HPC glibc 挡**：二进制需 GLIBC_2.29，HPC el8 仅 2.28 → 需新 glibc 容器。**仅 IMPROVE feature_calc 的 Stability 特征用它，Predict 步与 benchmark 不受影响** |
| PRIME | IMPROVE 的 TCR 识别分 | Gfeller lab github.com/GfellerLab/PRIME（学术免费）| ✅ **已 clone** HPC `tools_repos/PRIME` |
| MixMHCpred | IMPROVE / PRIME 依赖 | Gfeller lab github.com/GfellerLab/MixMHCpred（学术免费）| ✅ **已 clone** HPC `tools_repos/MixMHCpred` |
| self_similarity | IMPROVE 的 Self-similarity 特征 | github.com/SRHgroup/self_similarity | ✅ **已 clone** HPC `tools_repos/self_similarity` |

> ⚠️ **benchmark 发布限制**：netMHCpan/netMHCstabpan 学术许可第 7(v)/10 条 —— 未经 DTU 书面同意不得向第三方发布在其软件上跑的 benchmark 结果。本项目是 benchmark → 论文/对外报告含 netMHCpan 对比数字前需取 DTU 书面同意（投稿阶段处理）。
> DTU 工具 = Linux 二进制，装 WSL2 `~/quantimmu/ext_tools/`。net 工具脚本是 tcsh（已 `apt install tcsh`）。

---

## 袁老师输入数据（第二阶段）
- 状态：未到（datasets.json `yuan_input_data` status=todo）。
- 到位后：按各工具输入格式写格式转换脚本（`scripts/`）→ 正式跑 → 补真实输出到 TOOLS md。

---

## 第二批 5 工具（Wave 3，原李紫晨负责，现并入余嘉测试）

> 2026-06-24 调研建档完成（5 researcher 并行查官方 repo/paper/依赖/输入输出/许可）。后续 4 工具部署+进 benchmark，MHLAPre 阻塞。逐工具 4 类信息见 `TOOLS/<tool>.md`，论文/许可见 `REFERENCES.md`/`PROVENANCE.md`。

### 状态总表（Wave3 5 工具·部署细节归档）

> 📌 进度结论以**顶部规范状态总表**为准；本表保留部署/阻塞细节供查。

| 工具 | clone | 环境 | 权重 | example 烟测 | 4类信息 | 状态 | 阻塞 |
|---|---|---|---|---|---|---|---|
| PRIME | ✅ | ✅ `envs/prime` | ✅(随repo) | ✅ **r=1.0** | ✅ | **SMOKE_PASS** | 无（PRIME2.1+MixMHCpred3.0 跑通，147 行对账官方 diff=0）|
| ImmuneApp | ✅(tarball) | ✅ `envs/immuneapp` | ✅随repo | ✅ | ✅ | **SMOKE_PASS** | 无（HPC py3.7+TF1.15.0 跑通，出 Immunogenicity_score；坑=staged 装 TF 防 pip 回溯）|
| deepHLApan | ✅(Docker镜像) | ✅(镜像内) | ✅ | ✅ | ✅ | **SMOKE_PASS** | 无（本机 WSL2 docker `biopharm/deephlapan:v1.1` 跑通 binding+immuno 双分；坑=outdir 须先建）|
| HLAthena | ✅(Docker镜像) | ✅(镜像内) | ✅(65allele 6.6G) | ✅ | ✅ | **BENCHMARK_DONE(proxy)** | GCS 死锁绕过(匿名下65-allele模型+patch fetch_models=false 挂载)。**全量 ELISpot benchmark 完成**：HPC 分块跑 266/336 chunk(70 失败=len-8 在登录节点高负载下 cgroup 内存 kill)，**逐肽 max 聚合覆盖 DS2 100/101 肽**→ merge 进 9tools。结果 **AUC 0.51(max>0)/ρ 0.08 n.s.= 近随机**，印证 presentation≠immunogenicity。⚠️ 仅 presentation proxy 单列，不与免疫原性工具 apples-to-apples。数字核 `analysis/metrics_ds2_9tools.csv` |
| MHLAPre | ✅(15M) | ☐ | ❌缺 | ❌ | ✅ | **阻塞·不可复现** | 🔴 无权重 + ProcessData npy 缺 + **预处理管线代码也缺**（Pretreatment.py 无 main、生成 hla_epit_cdr3.npy 的拼装码被注释）→ 自训路也不通。全网(GitHub/Kaggle/Zenodo/HF)搜权重空。唯一路=邮件作者(23B903048@stu.hit.edu.cn)。已摸清列名 |

### 部署排序（易→难）
**PRIME（最易，已半 clone）→ ImmuneApp → deepHLApan → HLAthena(proxy) → MHLAPre（权重阻塞，末位）**

### ⚠️ 两个可行性红旗（部署前必读，防踩坑）
1. **HLAthena 不是免疫原性工具**：预测 MHC-I 提呈（presentation），论文明确不预测免疫原性；独立 benchmark ELISpot AUC~0.6、PPV 0.3063 近随机。→ 进 benchmark **只能当 presentation baseline proxy，须标注层次不同，不与 PRIME/deepHLApan/ImmuneApp/MHLAPre 等免疫原性工具 apples-to-apples 并列**。
2. **MHLAPre 权重缺**：README 称权重+训练数据太大未上传，需邮件作者（23B903048@stu.hit.edu.cn）；且 repo 无 LICENSE、CUDA10.2 旧、IEDB 训练数据与 ELISpot benchmark 可能 overlap（数据泄露）。→ 部署前置阻塞，可能要权重或重训。

### 共性观察
- 这 5 个里 4 个（PRIME/deepHLApan/ImmuneApp/MHLAPre）有免疫原性连续输出，**理论可进 ELISpot benchmark**（HLAthena 仅 proxy）。
- 4 个有 HLA 格式差异需预处理（deepHLApan 无星号 `HLA-A01:01`，others `HLA-A*01:01`），肽长限制各异（PRIME 8-14 / 其余多 8-15），benchmark 喂数据时按各自格式转换。
- **多数训练数据含 IEDB → 与 ELISpot benchmark 测试集 overlap 风险普遍**，正式 benchmark 前需统一排重（与第一批同此 caveat）。
