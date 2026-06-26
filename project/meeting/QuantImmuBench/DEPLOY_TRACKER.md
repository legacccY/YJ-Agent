# DEPLOY_TRACKER — 10 工具部署状态总表

> 真源：每工具状态 + job_id + 阻塞写这里。详细 4 类信息写 `TOOLS/<tool>.md`。

---

## 🎯 规范状态总表（单一真源，10 工具）

> ⚠️ 此表是**唯一进度真源**。下方两张分表（第一批 5 / Wave3 5）= 部署细节归档，状态以本表为准。
> 教训：旧表「状态」列单维枚举混了三件事（部署到第几步 / 跑哪个版本 / 进没进 benchmark），导致 NeoTImmuML（自训版进了 benchmark）被读成"没做成"、PRIME/ImmuneApp/deepHLApan（已进 benchmark）被读成"停在烟测"。本表按维度拆列。
> **benchmark 列以 `analysis/metrics_ds2_9tools.csv` 为真源回填**（9 工具各 9 行 = 3 聚合×3 阈值；MHLAPre 0 行 = 唯一未进）。

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
