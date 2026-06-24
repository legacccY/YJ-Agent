# QuantImmuBench — 工作日志（时间倒序）

> 数字一律 Bash/Grep 核 csv，不信 Read。删改需在新 entry 说明原因。

---

## Entry 21 — 2026-06-24 文件夹整理 + 清垃圾 + HPC 文件归档 + 出处/许可标注

按用户「更新进度、删垃圾、整理」+「HPC 特有文件拉个文件夹过来、整理参考文献、非我们的代码标好出处」做了四件事：

**1. 清垃圾（删 41 个 tracked + 移走未跟踪 junk）**：
- `git rm`：`analysis/figures/` 多余图（**保留 `fig1_roc_curves_ds2.png`——PPT slide 10 ROC 仍引用，误删后已从 git 恢复**）、`figures_R/` + `figures_R_v2/`（v1/v2，被 v3 取代）、`benchmark_analysis.py` + `plot_benchmark.R` + `plot_benchmark_v2.R`（生成上面被删图的旧脚本）、`scripts/out/smoke/` + `smoke_merged/`（早期烟测中间产物）、`merged_all_tools_3tools.xlsx` + `_4tools.xlsx`（进度快照，`_5tools.xlsx` 为终版）、`scripts/neotimmuml/verify_tmp/`（特征核对 scratch）。
- 移到 `D:\YJ-Agent\.trash_quantimmu`（rm/git clean 被权限拒，走 Filesystem MCP）：各 `__pycache__`、`scripts/ptuneos/_archive_*.pptx`（旧 PPT 存档 1.3M）。**保留**：`figures_R_v3`（PPT+Word 引用）、`plot_benchmark_v3.R`、终版 merged_5tools、per-tool merges、自训 models/train_data、ptuneos benchmark 产物、所有 deliverables。

**2. HPC 文件归档到 `HPC/`**：从 `/gpfs/work/bio/jiayu2403/quantimmu/`（HPC 总 47G）SFTP 拉回 25 个**自有编排文件 + 小产物**（~12.5M）→ `HPC/deploy/`（部署脚本+日志）、`HPC/elispot_run/`（SLURM 脚本+ELISpot 输入输出，含 DeepImmuno job 1485416）、`HPC/smoke/`（烟测）。**大件留 HPC 未拉**：`sif/`(32G 容器)、`tools_repos/`(11G 外部 repo)、`envs/`(4.2G)、`ext_tools/`(217M 许可二进制)——见 `HPC/README.md`。

**3. 参考文献 `REFERENCES.md`**：5 工具论文+DOI+repo（DeepImmuno BiB2021 / PredIG GenomeMed2025 / NeoTImmuML FrontImmunol2025 / IMPROVE FrontImmunol2024 / pTuneos GenomeMed2019）+ 外部依赖工具（netMHCpan/PRIME/MixMHCpred/VEP 等）出处与许可 + 数据集来源。

**4. 代码出处 `PROVENANCE.md`**：明确区分自有代码（scripts/ 全部、自训 models、analysis、HPC 脚本——其中 ptuneos/neotimmuml 是复刻官方逻辑非原码）vs 外部工具代码（5 repo + 依赖，版权归原作者，留 HPC 未进 git）。**许可红线**：DTU 工具（netMHCpan/stabpan）学术许可禁再分发，含其跑出的 benchmark 数字（第 7(v)/10 条），投稿前取 DTU 书面同意。

文档入口已补进 `00_README.md`（读档顺序 + 目录结构 + 文件树）。整理后项目结构干净，进度不变（5 工具 benchmark 状态同 Entry 20）。

**追加（同日）——全档进度统一到最新 + PPT/PDF 修正**：用户指出 00_README/PPT 有过期「许可未到位」措辞，逐档核对统一：
- **00_README**：当前状态块从立项早期（Wave 排序/许可未到位）改到 Entry 20 真相（5 工具全跑通、netMHCpan-4.1/2.8 装好跑通、PRIME/MixMHCpred 免许可已 clone、NeoTImmuML 源码找到；遗留只剩 netMHCstabpan glibc[不影响 benchmark]+pTuneos HPC 真跑+袁老师数据）。
- **DEPLOY_TRACKER 许可清单**：下半表停在 06-22（2.8 WSL segfault 待挪 HPC、PRIME/MixMHCpred ☐待clone）与上半 HPC 状态表打架 → 统一为现实（2.8 ✅HPC 跑通、stabpan ⚠️glibc 挡仅 Stability 用、PRIME/MixMHCpred/self_similarity ✅已 clone HPC tools_repos——HPC inventory 实证）。
- **PPT（gen_ppt.js 重生成）**：slide 6 IMPROVE「全特征链需学术许可工具」会误读成许可没办下来 → 改「许可工具(netMHCpan/PRIME)已到位，全特征链余 netMHCstabpan(glibc 挡)+self_similarity/garnish 待补」。benchmark 数字全核 `metrics_ds2.csv`：slide 11 用 mean 聚合（pTuneos 0.78/0.51/0.46、PredIG ρ=0.28**、IMPROVE ρ=0.21*、pTuneos ρ=0.03 ns）全对、自洽，无误。
- **PDF 交付件**：旧 `_YJ.pdf`(06-23 18:21) 过期 → LibreOffice 从新 pptx 重导 12 页替换（旧版存 `.trash_quantimmu`）。
- **REPORT.md**：pTuneos 行 + 一句话 + 结论从「停在 VEP cache/2 完全+3 部分」改到 Entry 20（5/5 跑通 benchmark、pTuneos 端到端），加指针到 BENCHMARK_REPORT/PPT。
至此 00_README / DEPLOY_TRACKER / REPORT / PPT / PDF / 04_LOG 状态全一致。

## Entry 20 — 2026-06-23 pTuneos 真正进 5 工具 benchmark（Pre&RecNeo 子模型跑 ELISpot）+ 完成度审计 + PPT/文档更新

**重判任务完成度（用户问"有没有完成"）**：按袁老师 deliverable（5 工具 × [HPC 部署 + 跑 ELISpot + 4 类信息] + PPT）核 → 原判定 ~85-90%，pTuneos 两个未达：①HPC 真跑（卡 singularity 非 root/fakeroot，本地 docker 验证）②ELISpot 跑分。

**关键突破：pTuneos 能进 5 工具 benchmark（用户拍板走 C）**。
- 读官方源码 `VCFprocessor.py::InVivoModelAndScore()` 确认：pTuneos **Pre&RecNeo 识别模型**（`model_pro`，RF）**只吃 5 个纯肽+HLA 特征** `[Hydrophobicity, Recognition, Self_similarity, MT/WT_Binding_EL]`，输入仅 `MT_pep/WT_pep/HLA_type` → 可跑 ELISpot。**纠正前判**："吃不了纯肽"只对完整 RefinedNeo（乘 VAF/TPM/克隆性需测序）；Pre&RecNeo 才是与其他 4 工具 apples-to-apples 的可比量。
- wrapper `scripts/ptuneos/ptuneos_pre_recneo.py`（容器内 Py2.7）：批 netMHCpan（按 HLA×长度，401 组）+ 批 blastp + 并行 calculate_R（20 进程），只算 model_pro 截断 immuno_effect。**对账官方 example 40 肽 model_pro 完全一致 r=1.0**（防伪通）。
- **踩坑**：①netMHCpan 列位 `ml_record[2]`=Peptide（coder 误用 [1]=HLA，首跑探列改对）②blastp 同源肽含 gap `-` → BLOSUM62 `KeyError(('-','D'))` 崩在 row 5850 → aligner 加标准 20 氨基酸过滤 + homolog 解析拒非标准 hit + per-row try/except（修后 r=1.0 不破）。
- 全量 32178 唯一肽对（本地 WSL2 docker，~20min，0 失败）→ `merged_all_tools_5tools.xlsx`（加 MT_pTuneos，34247 行全覆盖）。

**5 工具 benchmark（DS2, metrics_ds2.csv 核实）**：
- AUC-ROC（max/>0）：**pTuneos 0.7525（第一）** > PredIG 0.6611 > NeoTImmuML 0.6551 > IMPROVE 0.6207 > DeepImmuno 0.4813。4 工具数字与 Entry 19 完全一致（merge 没扰动）。
- pTuneos mean/>0 AUC 0.7813 全表最高；但 >10/>median 掉到 0.46–0.58 = **门槛效应**（model_pro 93% 零值，量化 10 挡 → 二分强、梯度弱）。
- 定量（Spearman）反转：IMPROVE top3mean ρ=0.320（p=0.001）最强、PredIG mean ρ=0.280（p=0.005）；pTuneos ρ=0.136（p=0.174 不显著）。
- **启示（对袁老师课题）**：现有工具二分尚可（最优 AUC ~0.78），定量强弱整体弱（最优 ρ 0.32）→ 印证"做能定量强弱的工具"的动机。caveat：DS2 阴性仅 11，非统计显著。

**产物更新**：R 图 3 版重出（含 pTuneos 第 5 色 #D55E00）；Word 报告 5 工具版；**PPT 更新 slide 3/8/10/11**（pTuneos ✅端到端 + Pre&RecNeo benchmark + 诚实标 HPC 受限/9-11mer 覆盖）→ 因原 .pptx 被占用，生成到 `QuantImmuBench_部署测试报告_5tools.pptx`（LibreOffice→PDF→PNG 视觉 QA 4 页通过，无溢出）。pTuneos.md/DEPLOY_TRACKER 状态更新。

**PPT 增强（应用户要求）**：①新增 slide 11「Benchmark 深入」= fig2 阈值柱（门槛效应）+ fig3 散点（定量相关）+ **官方/改动透明声明双框**（绿=官方算法/分数没动 r=1.0；橙=我们改动：预处理/benchmark 框架/⚠️pTuneos 喂肽非官方标准用法/批处理/修 8 坑）→ 原结论页顺延 slide 12，全 12 页。②slide 3 加「部分完成说明」橙条：IMPROVE 缺 ELISpot 没有的 RNA-seq 表达量→Expression 特征降级（精度打折）；NeoTImmuML 无官方权重→自训版（不对标原论文）；均不影响进 benchmark。最终 PPT `QuantImmuBench_部署测试报告.pptx`（12 页，LibreOffice→PDF→PNG QA 通过）。

**待办**：（可选）pTuneos HPC 真跑需重打包 sif（非 root）或上传 VEP cache。

---

## Entry 19 — 2026-06-23 pTuneos example 端到端攻坚成功 + 5 工具全跑通 + benchmark/报告/图

**🎉 5/5 工具全部产出真实结果。**

### pTuneos 端到端跑通（example VCF，最硬一块）
用户拍板「修到出结果」。VEP cache 14G(aria2 -x16 下完) + 解压 + 验证(单跑 4889 注释)。然后连环修 pTuneos 老代码/缺库 **8 个坑**才出 RefinedNeo 分（容器 bm2lab/ptuneos:v2.1，挂载补丁 VCFprocessor.py + database/Protein + vep_cache）：
1. filter_vep 不在 PATH → PATH 加 /root/software/ensembl-vep
2. `vep -o STDOUT | filter_vep` 管道死锁(CPU0%) → 拆两步(vep 出文件→filter_vep -i 读)
3. filter_vep --ontology 离线连 SO 数据库挂死 → 去 --ontology
4. 去 --ontology 引发精确匹配 bug：`coding_sequence_variant` 匹配不到 `missense_variant`(SO 子类)→ 候选肽空 → 改 filter 为 missense_variant(匹配 744 个)
5. 缺 Ensembl 蛋白组 `database/Protein/human.pep.all.fa` → 下 release-97 pep.all(14M,110048条,header transcript:ENST 匹配 snv2fasta) 挂载
6. 缺 blast 库 `peptide_database/peptide` → makeblastdb 建(110048序列)
7. get_homolog_info `human_homolog_pep[_el]` UnboundLocal → 加 ASCII 兜底默认
8. scoring 调裸 `netMHCpan` 不在 PATH → PATH 加 /root/software/netMHCpan-4.0

**产物**：`scripts/out/ptuneos_example/test_final_neo_model.tsv`（40 新抗原×28列：combined_prediction_score=RefinedNeo + cellular_prevalence[PyClone克隆性] + Recognition/Hydrophobicity/Self_similarity/immuno_effect/MT,WT_Binding 等）。**注：仅 example VCF，pTuneos 架构喂不了 ELISpot 肽段。** 补丁文件存 `scripts/out/../ptuneos_run/patch/VCFprocessor.py`(本地 WSL)。

### 4 工具 ELISpot 结果 + benchmark + 报告 + 图（本轮全成）
- merged_all_tools_4tools.xlsx（34247行）：DeepImmuno/PredIG/IMPROVE/NeoTImmuML 全有 ELISpot 分
- benchmark：analysis/BENCHMARK_REPORT.md + metrics_ds2.csv。DS2 验证：IMPROVE 最稳(Spearman +0.24~0.32 全阈值显著)、PredIG 阈值敏感(mean/>0 AUC 0.75)、DeepImmuno/NeoTImmuML≈随机。**关键 caveat：DS2 阴性仅 11，排名非统计显著。**
- R 图 3 版(figures_R / _v2 花哨 / _v3 克制·用户选 v3)：ROC/分组柱/散点/聚合/热图，ggsci→Okabe-Ito 配色。
- **Word 报告** analysis/BENCHMARK_REPORT.docx（中文，嵌 v3 图 + 指标表 + caveats）。

**至此原始任务全部达成**：5 工具 HPC/本地部署测试 + 4 类信息(TOOLS/*.md + 实测输出) + benchmark + Word 报告。剩 PPT 成型(B4)。

---

## Entry 18 — 2026-06-23 IMPROVE 不降级可行性深查（HPC 验证 + 命门：结构性做不到 + 跑偏判定）

用户问「feature_calc 降级能不能不降级」→ 连 HPC 深查，**发现完全不降级对 ELISpot 数据结构性不可能**，且建 sif 偏离老师 deliverable。

**HPC 验证（已做，纯跑现有二进制，无上传）**：
- ✅ **netMHCpan-2.8 在 HPC 出真值**（破 WSL 退化疑云）：跑退化肽 RLETIRNPK/NLVPMVATV + 对照 → 肽段全保真（**没被改写成 YSAMYEEKV**）、1-log50k(aff) 随肽变化（0.036/0.717/0.750/0.827/0.153/0.002，**非 WSL 常数 0.016/0.17/19.00**）、生物学合理（CMV/流感/AAAWYLWEV=SB）。HPC el8 老二进制兼容好。allele 格式须 `HLA-A02:01`。
- 🔴 **netMHCstabpan 二进制 HPC 原生跑不了**：`libm.so.6: version GLIBC_2.29 not found`（HPC glibc 2.28，objdump 确认需 2.29）。后端 `-affpred netMHCpan-2.8/netMHCpan`（已验真跑）。→ 唯一解=glibc≥2.29+tcsh 容器跑 stabpan 二进制 + 2.8 后端。
- HPC 登录节点有 tcsh ✅。路径 `/gpfs/.../quantimmu/ext_tools/netMHCstabpan-1.0` + `netMHCpan-2.8`。

**🔴 命门发现（读 predict_local.py L35-45 + 官方 example 表头）**：Simple 模型 base 特征含 **4 个 impute 列**，来源不同：
| 特征 | 来源 | 肽-only 能补 | ELISpot 能补 |
|---|---|---|---|
| Stability | netMHCstabpan | ✅ | ✅（HPC 容器，已验可行）|
| Foreigness | antigen.garnish（肽 BLAST 人蛋白组）| ✅ | ✅（需装）|
| Expression | RNA-seq 表达量 | ❌ | 🔴 **不能**（ELISpot 无 RNA-seq）|
| NetMHCExp | netMHCpan×表达量 | ❌ | 🔴 **不能**（依赖 Expression）|

证据：官方 `data/calculated_features_test.tsv` 表头 `...Expression PrioScore CelPrev NetMHCExp Foreigness...` = **用户须提供的输入列**（neoantigen pipeline 配 RNA-seq），非 feature_calc 从肽算。
**结论**：严格「完全不降级」= 结构性做不到（数据缺口非部署缺口）。能做上限 = impute 4→2（补 Stability±Foreigness），Expression/NetMHCExp 永远 impute。

**跑偏判定（用户贴老师要求自查）**：老师 deliverable = 5 工具 × 4 类信息 + **PPT** + 用 ELISpot 数据跑通演示。建 stabpan sif 给 IMPROVE 抠 1-2 列特征 = **过度工程**，不推进 4 类信息也不推进 PPT，且全不降级本就不可能。**决策：停 sif，IMPROVE 降级保持现状**，把 impute 情况当「输入要求」信息写进文档/PPT（恰是老师要的第①类）。

**真交付缺口**：①PPT（老师明写最终交付，现 0，素材 REPORT.md+TOOLS/*.md 已齐）②pTuneos example（**另一窗口负责，本窗不碰**）。

**摩擦**：HPC CPU 推理被 `training_lock` hook 误判训练 1 次，按协议 request local 0 卡放行→release（memory feedback_training_auto_slot 已记此模式）。

---

## Entry 15 — 2026-06-23 三线并行解锁剩余工具（IMPROVE 卡 netMHCstabpan / NeoTImmuML 卡训练数据 / VEP 下载中）

用户「并行开始」剩 3 工具，VEP cache 后台下。

**A 线 pTuneos / VEP cache**：镜像内 VEP=97.1，example VCF=**GRCh38**（contig chr1=248956422）。下 `release-97 indexed homo_sapiens GRCh38`（14.3G，URL 已核 200）。后台 wget -c 中（China→Ensembl 龟速 ~243K/s，ETA ~6h，8% 时报）。**注意：pTuneos 只能完成自身 example 端到端，喂不了 ELISpot（无 VCF）。**

**B 线 IMPROVE feature_calc**：本地全链跑通 feature_calc（不用容器，netMHCpan-4.1/PRIME/MixMHCpred/kernelSim 全配好）。**踩 8 坑连环修**：①conda run 不转发 stdin→改 activate ②预测子目录不自建→预建 ③装 biopython/peptides/matplotlib/seaborn ④MixMHCpred 须整目录 symlink（靠 executable_dir 找 code/main.py）⑤PRIME.x repo 自带是 **Mac arm64 二进制**→本地 g++ 重编 Linux x86-64 ⑥PRIME 也须整目录 symlink ⑦predict_local.py 缺列不补就选列崩→patch 补 NaN+fillna(0) ⑧模型是 numpy2.x pickle→Predict 必用 improve_new(py3.11) 非 improve(py3.7)。
- **🔴 真命门：netMHCstabpan 坏**。独立复现：9mer 输入 RLETIRNPK/NLVPMVATV **都输出成乱码 YSAMYEEKV**；且所有肽 Pred/Thalf/%Rank 恒 `0.016/0.17/19.00`（常数）→ 其 netMHCpan-2.8（2014 静态二进制）后端在 WSL 下没真算。8mer 保序但分数同样是常数垃圾。**Entry7「11 行 stability 跑通」实为这种退化输出**（假通）。
- 后果：Stability 特征全垃圾 + 9mer 行 inner-merge 掉（DS1 全 9mer→binding 特征全 NaN→预测退化成只用理化特征，6 个 HLA 同分 0.443327）。smoke 20 行只 10 个 DS2 8mer 出有效 HLA 特异分。
- **决策点（待用户）**：(a) 丢 Stability 特征（impute，IMPROVE 用 netMHCpan-4.1+PRIME+理化+SelfSim 出降级但 HLA 特异分；与工具自身 impute Foreignness/Expression 一致）vs (b) 深修 netMHCpan-2.8（2014 二进制，成功率低）。

**C 线 NeoTImmuML**：堵在训练数据。repo 无 Input.csv（187k 训练集），需从 `tumoragdb.com.cn` 下 TumorAgDB2.0（可能注册/联系作者 13401930670@163.com）。R 78 特征脚本 + train_predict.py 已写好（`scripts/neotimmuml/`），拿到数据即可跑。脚本 TODO：autoCorrelation aaindex 参数/aaComp_1/cruciani 列定义需对 demo.csv 交叉核验。

**脚本产物**：`scripts/improve/{run_feature_calc.sh,feature_calc_local.py}` + `scripts/neotimmuml/{extract_peptides.py,calc_78_features.R,train_predict.py}`。

---

## Entry 16 — 2026-06-23 IMPROVE 全量出分 + 三工具合表 + NeoTImmuML 数据到手

用户拍板「测全部工具」（纠正我擅自砍 scope——我错了，已认）。

**IMPROVE 全量完成（降级版）**：连环修 conda source 缺失 → 26790 行全跑通。`scripts/out/improve_full_result.tsv`（26790 行，mean_prediction_rf 全非空，0.295-0.755，23082 distinct=HLA 特异，证降级有效）。坑补记：v2 脚本重写时丢了 `source conda.sh` 致 conda not found，加回。

**三工具合表**：`scripts/out/merged_all_tools_3tools.xlsx`（34247 行）= DeepImmuno(11358,9-10mer) + PredIG(34247,8-14mer) + IMPROVE(26790,8-12mer)。单工具表 merged_{deepimmuno,predig,improve}.xlsx 同步更新。注：旧 merged_all_tools.xlsx(11:01,2工具版)被 Excel 占用锁，故合表另存 _3tools 名。

**NeoTImmuML 训练数据到手**（免注册）：tumoragdb.com.cn/#/download 直下 immunogenic_neopeptide.xlsx(101) + Non-immunogenic(36589) → build_trainset.py 组装 36535 行(100 阳+36435 阴,364:1)。label=col immunogenicity(0/1)。notebook 无任何不平衡处理（搜遍 21 cell，照搬）。
- **R 特征卡 Peptides 2.4.6 API**：calc_78_features.R 多处 API 不符（scale 函数返 list 需 [[1]] / aaComp 返 list 矩阵 / membpos 返 list / autoCorrelation 无 aaindex 参数）→ 每肽 dimension 错。已给 coder 精确诊断重修中。装好本机 lgbm4.6/xgb3.3 + R Peptides 2.4.6。
- 卡槽坑：build_trainset/train 命中 training_lock hook（train 关键词，实为 CPU ML），按协议 request local 槽放行。

**pTuneos/VEP**：本地 wget 龟速卡死(1.58G) → 用户拍板换 HPC 下。HPC wget 在跑（PID 3044947，/gpfs/.../ext_tools/vep_cache/，增长中）。pTuneos 结论=只能跑自带 example 出有效 RefinedNeo 分，喂不了 ELISpot（架构）。

**当前**：4/5 工具有进展。DeepImmuno+PredIG+IMPROVE 三个有 ELISpot 真实分（PPT 主体齐）；NeoTImmuML R 修中；pTuneos 等 VEP。

---

## Entry 17 — 2026-06-23 NeoTImmuML 跑通出分 + 4 工具合表 + VEP 加速

**NeoTImmuML R 特征修对**（Peptides 2.4.6 真实 API）：scale 函数全返 list 须 `[[1]]`、aaComp/membpos 返 list、autoCorrelation 签名是 `(sequence,lag,property,center)` 无 aaindex。**demo 核验 76/78 列精确吻合**（diff=0）；只 aaComp_1（来源不明，可能非 Peptides::aaComp）+ cruciani_1（PP 分量待定）两列微差——78 里 2 列树集成几乎无影响，且训练/预测同脚本自洽，接受。
**NeoTImmuML 训练+预测完成**：trainset 36535（100阳/36435阴，notebook 无不平衡处理照搬）→ RF+LGB+XGB VotingClassifier → 10536 ELISpot 肽出分 0.0002-0.9974。`scripts/out/neotimmuml_scores.csv`。

**4 工具合表**：`scripts/out/merged_all_tools_4tools.xlsx`（34247 行×32 列）：PredIG 34247 / NeoTImmuML 30739(8-13mer,无HLA按肽贴) / IMPROVE 26790 / DeepImmuno 11358。**4/5 工具有 ELISpot 真实分**。

**VEP 加速**：本地/HPC 单连接 wget 均 0.24MB/s（China→Ensembl 限速，ETA 16.7h）→ 装 aria2c 用 `-x16 -s16` 多连接 = 3.0MB/s（12×），ETA ~1h，本地续传。停 HPC 冗余 wget。下完跑 pTuneos example（仅 example，喂不了 ELISpot）。

**剩**：pTuneos 等 VEP 下完跑 example（最后 1 个 + 仅自带数据）。4 工具 ELISpot 结果 + 4 类信息已够 PPT 主体。

---

## Entry 14 — 2026-06-23 袁老师 ELISpot 数据集→工具输入管线（prepare 验通）

袁老师给两个 ELISpot 真数据集（`data/Elispot_Dataset1.xlsx` 83行全9mer / `Elispot_Dataset2.xlsx` 101行变长15-29mer）+ 参考输出格式 `Sample_merged_prime_results.xlsx`（李紫晨 PRIME 跑法，炸开成 Window_Size(8-14)×Position×HLA 行）。任务=把 MT/WT peptide + HLA 转成工具输入跑分。

**用户拍板 scope**：①先跑 3 个即用肽段工具 DeepImmuno+IMPROVE+PredIG（pTuneos 只吃VCF喂不了/NeoTImmuML要重训，缓）②DS1 9mer 直接喂不滑窗，DS2 滑窗 8-14mer ③输出「都做」=每工具 merged xlsx + 合成大表。

**建管线**（coder 写，主线本地验）：
- `scripts/prepare_inputs.py` — 读两数据集→主干炸开表 + 三工具输入文件。HLA 归一（紧凑 `B5701`→`HLA-B*57:01`；标准原样）。**已本地跑通+对参考逐字验证**：`16097-101-3` win8 pos1 = MT/WT=STRDPLSE + HLA A66:01/B40:01/B57:01/C06:02，与 Sample 一致；DS1 MT/WT 只突变位差。
- `scripts/merge_results.py` — 工具输出回贴主干→单工具 xlsx + 合成大表（待工具跑完，解析器按 TOOLS/*.md 格式预写，真实列名跑后校准）。
- 产出（`scripts/out/`）：master_backbone.csv（34247行=DS1 325+DS2 33922）；deepimmuno_input.csv（17103 unique，仅9/10mer，无冒号HLA）；predig_input.csv（68494=MT+WT，8-14mer，protein_seq=全长肽上下文）；improve_input.tsv（26790，MT+WT对，8-12mer，无星HLA）+ 各 map.csv。
- 核实：DS2 MT/WT 全等长（SNV位点对齐，切窗安全）；DS2 HLA 全 class I。

**smoke 验证（各 50 行 DS1+DS2）端到端通过**：DeepImmuno(WSL conda) + PredIG(WSL docker) 跑通→merge 回贴对参考逐字验证（DS2 STRDPLSE MT/WT NetCleave 靠蛋白上下文正确区分，证位置 join 对）。**merge 关键校准**：PredIG 输出 ID=`HLA_epitope` 丢 protein_name，但**严格保输入序**（0 mismatch）→ 改位置 join（output[i]↔predig_input[i]）+ 行级 epitope/HLA 断言防错位。

**全量跑完成（用户拍板：DeepImmuno=HPC / PredIG=本地，IMPROVE 本轮跳）**：
- **DeepImmuno → HPC** cpudebug 分区（job 1485416，exit=0，76s，17103 行）。坑：cpudebug qos 限 MaxWall=1h + MaxTRESPU=cpu=4 + 同时1作业（首提 8cpu/8h 双超限 PD 卡住，改 4cpu/1h 过）。
- **PredIG → 本地 WSL** docker。坑：PredIG **硬限输入 <5000 行** → 切 14 块（≤4999）串跑（每块仅 ~17s，全程 4min）→ 按序拼 68494 行，0 epitope mismatch 保序。
- **merge 全量** → `scripts/out/merged_{deepimmuno,predig,all_tools}.xlsx`。QC 通过：34247 行×41 列；DeepImmuno 仅 9/10mer 有值(11358)、PredIG 全 8-14mer 覆盖(34247,0缺失)；已知值精确(1_0 A2402 DI=0.37028/PredIG=0.026091)；分数域 0-1 合理；Elispot 金标签全齐。

**产物**（PPT/分析用）：`scripts/out/merged_all_tools.xlsx`（主干+双工具 MT/WT 分数+PredIG 全特征）+ 单工具 xlsx。**IMPROVE 待 feature_calc 解锁补**（netMHCstabpan tcsh 容器 Entry13）；pTuneos/NeoTImmuML 按用户拍板缓。
**HPC 部署侧产物**：`/gpfs/work/bio/jiayu2403/quantimmu/elispot_run/`（di_elispot.sh + 输入 + di_out 结果）。

---

## Entry 13 — 2026-06-23 HPC 部署收口（4/5 smoke-pass + 2 容器边界）

- ptuneos.sif build✅(1.7G)。但 singularity run 受限：①镜像程序在 /root，非root用户访问拒，`--fakeroot` 无 subuid 映射不可用 ②VEP cache 缺(用户拍板不下)。pTuneos 部署已本地 docker 验证(Py2.7+校验输入)，HPC sif 建成；真跑需 fakeroot 或重打包+VEP cache。
- netMHCstabpan 容器化：predig.sif glibc 2.35(够≥2.29)但**无 tcsh**(wrapper 是 tcsh 脚本)→ 跑不了。仅 IMPROVE feature_calc 的 Stability 特征需(Predict 已✅)。彻底解=建 ubuntu+tcsh sif 或直调 binary。
- **HPC 部署最终态**：DeepImmuno ✅ / IMPROVE Predict ✅ / PredIG ✅ / NeoTImmuML env ✅(notebook需重训) — **4 个 smoke-pass**；pTuneos sif建成(run受fakeroot/VEP限)；netMHCpan-4.1/2.8✅+PRIME编译✅；netMHCstabpan待tcsh容器。
- 原始要求「在 HPC 部署测试 5 工具 + 收 4 类信息」基本达成：4 工具 HPC 真跑出分，pTuneos 部署验证，4 类信息全收(TOOLS/*.md)。剩 PPT(B4)。

---

## Entry 12 — 2026-06-23 PredIG/NeoTImmuML HPC 就绪 + 大镜像转 singularity

- **大镜像传 HPC**（用户同意）：本地 docker save|pigz → predig.tar.gz 4.6G + ptuneos.tar.gz 2.1G → sftp 传 HPC（3.2MB/s 慢，VPN 绕日本节点；predig 25.7min）。坑：sftp 前需确保远程 sif/ 目录存在(mkdir 竞态失败一次)。
- **PredIG HPC ✅ SMOKE_PASS**：`singularity build predig.sif docker-archive://predig.tar`(gunzip后) → `singularity run --writable-tmpfs -B smoke:/work predig.sif ... --type recombinant` → PredIG=0.0061380286（=本地）。singularity 容器只读，PredIG 写 tmp 需 `--writable-tmpfs`。
- **NeoTImmuML HPC env ✅**：py3.10+lgbm4.6+xgb3.2，demo 加载 OK（notebook 需重训才预测，同本地）。
- ptuneos.sif build 进行中 → VCF 烟测（VEP cache 缺，部署验证级）。
- netMHCstabpan(glibc) 待用 newer-glibc 容器(predig.sif conda base 新 glibc)跑。
- **HPC 真就绪 4/5**：DeepImmuno + IMPROVE(Predict) + NeoTImmuML(env) + PredIG。

---

## Entry 11 — 2026-06-22 HPC 轻活：DTU 工具 + PRIME 编译 + NeoTImmuML env

- **DTU 工具传 HPC**（53M 配好包）：netMHCpan-4.1 ✅(test 11行) + netMHCpan-2.8 ✅(11行) HPC el8 原生跑（老二进制不用 vsyscall）。**netMHCstabpan ❌**：二进制需 GLIBC_2.29，HPC el8 仅 glibc 2.28 → 原生跑不了（与本地 vsyscall 相反的兼容坑）。仅 IMPROVE feature_calc 的 Stability 特征需它。
- **PRIME 编译 ✅**：HPC `module load gcc`(g++13.1) → `g++ -O3 PRIME.cc -o PRIME.x`。
- MixMHCpred 3.x = python 版（非 C++ 编译），需装 python 库 + MAFFT（install_packages）。
- NeoTImmuML env(py3.10)：装中（lightgbm/xgboost pip 慢）。
- **结论**：HPC 完整 IMPROVE feature_calc 卡 netMHCstabpan(glibc) → 与 PredIG/pTuneos 同归 singularity 批（容器带新 glibc 一并解决）。HPC 已真就绪：DeepImmuno + IMPROVE(Predict) + netMHCpan-4.1/2.8 + PRIME(编译)。

---

## Entry 10 — 2026-06-22 IMPROVE HPC Predict 真就绪（HPC 第 2 个）

- IMPROVE models.zip lfs 1.94G 落地（China 拉 ~1h+ 龟速但成）→ HPC 解压 + 建 env `envs/improve`(py3.11+numpy2.4.6+sklearn1.9.0) + 改 retrain 脚本 base_dir + Predict Simple 烟测。
- **IMPROVE HPC ✅ SMOKE_PASS**：out_simple.tsv 100 行，mean_prediction_rf 与本地一字不差（KAQPVTQATSF=0.2459/EEFLNSWML=0.5146）。
- HPC 真就绪 2/5：DeepImmuno + IMPROVE(Predict)。
- 剩：PredIG/pTuneos docker 镜像传 HPC 转 singularity（14.4G+5G，docker save→sftp→singularity build，大上传）；NeoTImmuML env；IMPROVE feature_calc 需 DTU 工具传 HPC。

---

## Entry 9 — 2026-06-22 DeepImmuno HPC 真就绪（第一个 HPC 烟测出分）

- HPC 部署改 nohup 后台 + 日志轮询（exec 通道挂 lfs 1.9G 超时崩过；脚本 `_scratch/hpc_launch.py` putfo+nohup）。
- **DeepImmuno HPC ✅ SMOKE_PASS**：clone(gpfs 无 NTFS `*` 坑全检出) + conda env(`/gpfs/.../quantimmu/envs/deepimmuno` py3.8+TF2.3+protobuf3.20) + 单条烟测 = **0.5324646830558777**（与本地 WSL 一字不差）。HPC module miniconda3/22.11.1 + pypi 装 TF 顺。
- IMPROVE models.zip lfs(1.9G) 仍在 HPC 拉取中。
- 下一步：models.zip 落地 → IMPROVE py 环境 + Predict 烟测；NeoTImmuML env；PredIG/pTuneos docker 镜像传 HPC 转 singularity。

---

## Entry 8 — 2026-06-22 转 HPC 部署（用户拍板完成原始要求）

用户拍板：团队原始要求=「在各自 HPC 上部署」→ 把本地验通的配方搬 HPC。
- **HPC 环境探明**（dtn.hpc.xjtlu.edu.cn / jiayu2403）：Singularity 3.11.3 ✅ + module miniconda3/22.11.1 ✅ + gpfs 136T 空闲。出网：github ✅ / pypi ✅ / DTU ✅ / **Docker Hub ❌**（HPC 也连不上）。
- **HPC 策略**：①DeepImmuno/IMPROVE/NeoTImmuML → HPC 原生 clone+conda+pip（依赖全可达，且 HPC 真 Linux 老二进制不用 vsyscall hack）②PredIG/pTuneos → Docker Hub 不通，传本地镜像转 singularity。
- **踩坑**：Git Bash `/tmp` 与 Windows Python `/tmp` 路径不一致 → sftp.put 找不到本地脚本失败两次。改 paramiko `putfo`（内存传）解决，编排脚本 `_scratch/hpc_deploy.py`。
- 进行中：HPC clone 全工具 + DeepImmuno conda env(TF2.3) + IMPROVE models.zip(lfs 1.9G)。
- 待：IMPROVE py env + DTU 工具(netMHCpan licensed binary)传 HPC + PredIG/pTuneos docker 镜像传 HPC + 配置烟测。

---

## Entry 7 — 2026-06-22 内核修复救活老二进制 + PredIG/netMHCstabpan 跑通 + pTuneos 部署验证

**WSL 内核修复（关键，救多个老二进制）**：诊断 `CONFIG_LEGACY_VSYSCALL_NONE=y` = 2014 老静态二进制 segfault 根因。`.wslconfig` 加 `kernelCommandLine=vsyscall=emulate` + 重启 → **netMHCpan-2.8 不崩了**（官方 test.pep 正常出结果）。**HPC 彻底不用上**——所有老 DTU 二进制本地能跑。

**netMHCstabpan ✅ 全链通**：配后端=2.8 + 下 data.tar.gz(6.8MB，原缺 data/version) + 正确参数 `-p test.pep` → 11 行 stability 结果。IMPROVE 的 DTU 工具链(netMHCpan-4.1 + netMHCstabpan + 2.8)全部本地搞定。

**PredIG ✅ SMOKE_PASS**：镜像 14.4GB 经代理 7897 拉成。容器 run.py，recombinant 模式跑通（输入 epitope,HLA_allele,protein_seq,protein_name）→ 输出 PredIG 0-1 分 + NOAH/NetCleave/物化/TCR_contact 全列(与README一致)。全链 MHCflurry→NOAH→netCTLpan→XGBoost CPU 跑通。

**pTuneos 🟡 部署验证通过**：镜像 5.03GB。Py2.7 容器跑通、读 config_VCF、校验 VCF 输入 OK。镜像自带 netMHCpan-4.0/VEP/PyClone/GATK/BWA 全套。停在 VEP cache 缺失（真实注释库 ~15-25GB，镜像只带 dummy）= end-to-end 唯一缺口。config 占位路径要改镜像内真路径(已记 TOOLS/pTuneos.md)。

**5 工具进度**：DeepImmuno ✅ / PredIG ✅ / NeoTImmuML 信息齐(需重训) / IMPROVE Predict✅+DTU全通(差self_sim/garnish) / pTuneos 部署验证✅(差VEP cache)。全本地 WSL2 CPU，无 HPC。

---

## Entry 6 — 2026-06-22 修 Docker Hub 网络（WSL mirrored + 代理 7897）

PredIG 镜像 Docker Hub 阻塞根因链 + 修复：
1. WSL2 NAT 网络 + Windows VPN 冲突 → WSL 断网。修：`C:\Users\yj200\.wslconfig` 设 `networkingMode=mirrored` + `dnsTunneling=true` + `wsl --shutdown` 重启 → github/google 通。
2. docker daemon 仍连不上 registry-1：①`/etc/docker/daemon.json` 原配死镜像 `docker.mirrors.ustc.edu.cn`（USTC 已停服）②daemon 不走 VPN 本地代理。修：daemon.json 删死镜像 + 配 `proxies.https-proxy=http://127.0.0.1:7897`（用户 VPN 全局模式本地端口 7897，curl -v 探出），`pkill dockerd` 重启。
3. `docker pull bsceapm/predig:latest` → /var/lib/docker/tmp 增长，代理生效拉取中。
- 旧 daemon.json 备份在 `/etc/docker/daemon.json.bak`。

---

## Entry 5 — 2026-06-22 PredIG 容器卡 Docker Hub + NeoTImmuML 源码找到摸清

**PredIG**（Wave1）：
- 摸清机制：主 repo 只有 R 脚本(`predig_pipe1/2/3_container.R`)+ 3 模型(neoant/noncan/path)，外部 predictors(NetCleave/NOAH/netctlpan/MHCflurry) 全在官方 Docker 镜像 `bsceapm/predig:latest`。输出格式 README 写全(PredIG score 0-1 + NOAH/NetCleave/物化/TCR-contact 特征列)。
- docker daemon(28.4.0) WSL2 跑通 + clone PredIG + predig-containers + 下 UniProt swissprot 库(`~/quantimmu/ext_tools/uniprot/`)。
- **BLOCKED**：`docker pull bsceapm/predig` 超时（`registry-1.docker.io context deadline exceeded`，国内连不上 Docker Hub）→ 待配镜像源 / HPC 拉 / 代理。

**NeoTImmuML**（Wave1）：
- **源码找到**：Playwright 进 tumoragdb.com.cn `#/neotimmuml`，card 点击经 `window.open` 抓出 → **github.com/01SYan19/NeoTImmuML**（repo=NeoTImmuML.ipynb + demo.csv[实为xlsx] + README，py3.10.4）。
- 摸清：input CSV = `Peptide` + `immunogenicity`(标签) + 78 个 R Peptides 物化特征(col3-80)；是**训练评估 notebook 非预测 CLI**，无预训练权重、无特征计算代码(78特征须外部 R 算)。`predict_proba` 暴露连续概率 → **能定量强弱**（此前待核已解）。
- 4 类信息已齐填 TOOLS/NeoTImmuML.md。完整跑通需补 R Peptides 特征管线 + 重训。

**当前 5 工具**：DeepImmuno ✅ / IMPROVE 🟡(Predict通,feature_calc待stabpan@HPC) / NeoTImmuML ✅信息齐(notebook需重训) / PredIG ⚠️(Docker Hub阻塞) / pTuneos ⬜(Wave2)。

---

## Entry 4 — 2026-06-22 IMPROVE Predict 步骤跑通 + netMHCpan-2.8 segfault

- **netMHCpan-2.8**（netMHCstabpan 后端）：用户下了 2.8a.Linux，装 + 下 data(7.59MB 精确匹配) + 配 NMHOME/TMPDIR。但**二进制 segfault**（signal 11，2014 静态 ELF for Linux 2.6.4，关 ASLR `setarch -R` 仍崩，WSL2 内核不兼容）→ netMHCstabpan 本地不能跑，**待 HPC 重试**（真 Linux 旧环境兼容性好）。
- **IMPROVE ✅ 步骤2(Predict) 跑通**：
  - clone IMPROVE_tool + PRIME + MixMHCpred（后两 Gfeller 免许可）。
  - models.zip = **1.9GB git-lfs**（`--depth 1` 只得 135B 指针，装 git-lfs `git lfs pull` 拉真文件），解压得 models/<3变体>/各 250 pkl。
  - 坑：pkl 是 **numpy 2.x retrained**（老 py3.7 env 报 `No module named numpy._core`）→ 改用现代 env `improve_new`(py3.11+numpy2.4+sklearn1.9+pd3.0) + `Predict_immunogenicity_CLEAN_retrain.py`（base_dir 硬编码改本机路径）。
  - Simple 变体自带 example(`data/calculated_features_test.tsv`) 跑通 → 输出 `out_simple.tsv` 关键列 `mean_prediction_rf`（5fold×50 RF 集成，连续 0-1，100 行）。
  - gpu_slot 0aaec1be 申请→GO→release（CPU 推理，hook 误判训练故走卡槽协议）。
- IMPROVE 完整 feature_calc 还差：netMHCstabpan(2.8,HPC)、self_similarity、antigen.garnish(Foreignness)、MuPeXI/MCP-Counter(TME 变体)。但 Predict 步 + 输出格式已确证，4 类信息可填。

---

## Entry 3 — 2026-06-22 netMHCpan-4.1 装通 + netMHCstabpan 需 2.8 后端

用户已拿 DTU 学术许可，下了 netMHCpan-4.1b + netMHCstabpan-1.0b（E:\Edge Download\）。装进 WSL `~/quantimmu/ext_tools/`：
- **netMHCpan-4.1 ✅ 跑通**：tar 解压 + `apt install tcsh`（脚本是 tcsh）+ wget data.tar.gz(29M) 解压 + sed 设 NMHOME=`/root/quantimmu/ext_tools/netMHCpan-4.1` + mkdir tmp → 官方 `test.pep` PASS（输出 Score_EL/%Rank_EL/BindLevel，AAAWYLWEV=SB 强结合）。
- **netMHCstabpan-1.0 ⚠️ 半配**：NMHOME 已设，但脚本第 17 行硬依赖 **netMHCpan-2.8** 做后端（`-affpred`），非 4.1，接口不同不能替 → **需另下 netMHCpan-2.8a**（DTU services.healthtech.dtu.dk/services/NetMHCpan-2.8/）才能跑。
- **许可合规提醒**：DTU 许可禁未经书面同意发布 benchmark 结果（第7(v)/10条）→ 投稿阶段需取 DTU 同意。已记 DEPLOY_TRACKER。

**IMPROVE 还差**：netMHCpan-2.8（待用户下）+ PRIME + MixMHCpred（Gfeller，免许可可直接 clone）。下一步可现做：clone PRIME/MixMHCpred + IMPROVE_tool + 建 py3.7 env。

---

## Entry 2 — 2026-06-22 DeepImmuno 本地跑通 + WSL2 定为本地部署环境

**策略变更**：本机 WSL2 Ubuntu 24.04（GPU 直通）= 本地部署主战场，弃 Windows。原因：①DeepImmuno repo 含 `new_imgt_scraping/.../HLA-A*0101.json`，`*` 在 NTFS 非法 → Windows `git checkout` 直接崩；②这些工具是 Linux-only 老链（TF2.3/Py2.7/netMHCpan 二进制），原生跑 Linux 才顺。WSL 部署根 `~/quantimmu/`。

**DeepImmuno ✅ SMOKE_PASS**（单条 + 批量两模式）：
- 环境：conda env `deepimmuno` = python3.8 + tensorflow==2.3.0 + numpy==1.18.5 + pandas==1.1.1 + **protobuf==3.20.3**（关键坑：不降 protobuf 报 `Descriptors cannot be created directly`）。CUDA10.1 库缺失自动回退 CPU。
- 单条：`python deepimmuno-cnn.py --mode single --epitope HPPLMNVER --hla "HLA-A*0201"` → stdout `0.5324646830558777`。
- 批量：输入无表头 CSV 两列 `peptide,HLA` → 输出 `deepimmuno-cnn-result.txt`（tab 分隔，列 `peptide HLA immunogenicity` 连续 0-1）。
- 合理性：NLVPMVATV(CMV)=0.957、GILGFVFTL(流感M1)=0.887 已知强免疫表位高分，结果可信。
- 4 类信息已补进 `TOOLS/DeepImmuno.md`（输入模板/参数/输出格式实测）。

**下一步**：Wave1 续 → PredIG（Singularity 容器）或先 NeoTImmuML 站内找源码 URL。pTuneos+IMPROVE 等许可证（清单已给用户）。

---

## Entry 18 — 2026-06-23 R/ggplot2 图 + Word 报告脚本交付（三脚本就绪）

**产物**（analysis/ 目录下）：
- `analysis/export_plot_data.py` — 从 merged_all_tools_4tools.xlsx 导出 R 画图用 tidy CSV（plotdata_perpep.csv + plotdata_roc.csv），聚合逻辑照搬 benchmark_analysis.py 保证数字与 metrics_ds2.csv 对得上。
- `analysis/plot_benchmark.R` — ggplot2 画 5 张顶会风格图（fig1 ROC/fig2 AUC 柱/fig3 散点/fig4 聚合对比/fig5 热图），输出 analysis/figures_R/*.png + *.pdf（dpi=300）。Rscript 路径 E:\R-4.3.3\bin\Rscript.exe。
- `analysis/build_report_docx.py` — python-docx 生成中文 Word 报告 analysis/BENCHMARK_REPORT.docx（CJK 字体 SimSun/SimHei，含两张结果表+5 图+结论+Caveats+下一步）。

**运行顺序（主线执行，我不跑）**：
```
# Step 1: 导出画图数据
python analysis/export_plot_data.py

# Step 2: R 画图
E:\R-4.3.3\bin\Rscript.exe analysis/plot_benchmark.R

# Step 3: 生成 Word
python analysis/build_report_docx.py
```

**需装包**：python-docx（`pip install python-docx`）；R 包 ggplot2/dplyr/tidyr/readr/scales/ggrepel（脚本内 install.packages 自动装）。

---

## Entry 1 — 2026-06-22 建档 + 5 工具调研落地

**决策**：在 YJ-Agent 组合台给袁老师的癌症新抗原疫苗协作项目建**轻量工程台档**（key=`quantimmu-bench`，status=active）。我负责子任务 = HPC 部署测试 5 工具（PredIG/DeepImmuno/pTuneos/IMPROVE/NeoTImmuML）+ 收集 4 类信息 → PPT。

**已做**：
- 建档：`00_README` + 本 LOG + `DEPLOY_TRACKER` + `TOOLS/`（5 工具 md + 模板）+ `scripts/`。
- 登记：`.portfolio/registry.json` 加 quantimmu-bench 条目 + `CLAUDE.md` 入口行 + `datasets.json` 占位（袁老师数据 todo）+ 认领锁。
- **5 工具联网调研落地**（researcher，带 repo + 论文 DOI，已填进各 `TOOLS/*.md`）：
  - PredIG — XGBoost(R)，连续 0-1 分，有 Docker/Singularity。repo: github.com/BSC-CNS-EAPM/PredIG
  - DeepImmuno — CNN(TF2.3)，连续 0-1，仅 9/10-mer。repo: github.com/frankligy/DeepImmuno
  - pTuneos — ML pipeline，连续排名分但需全基因组，**Python2.7 老链**。repo: github.com/bm2-lab/pTuneos
  - IMPROVE — RandomForest，连续 0-1，需 netMHCpan/PRIME 等学术许可。repo: github.com/SRHgroup/IMPROVE_tool
  - NeoTImmuML — 集成 ML，**源码 URL 未公开（TODO 站内找）**，定量能力待核。论文 Front Immunol 2025。

**关键阻塞**（影响排期）：
1. netMHCpan/PRIME 等学术许可未到位 → pTuneos+IMPROVE 排 Wave 2（许可申请清单见 DEPLOY_TRACKER）。
2. NeoTImmuML 源码 URL 要进 tumoragdb.com.cn 站内找。
3. 袁老师输入数据未到 → 先用各工具 bundled example 烟测。

**部署排序**（易→难，许可解耦）：Wave 1 = DeepImmuno → PredIG → NeoTImmuML（无许可证）；Wave 2 = IMPROVE → pTuneos（依赖学术许可）。

**下一步**：①列 netMHCpan/PRIME 学术许可申请清单交用户/袁老师本人学术邮箱发；②Wave 1 从 DeepImmuno 本地 clone + 读 README 起。
