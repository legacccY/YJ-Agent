# 改动②/③ 全量重跑 · 多窗启动指南（quantimmu-rerun DAG）

> 服务 QuantImmuBench 改动②(原始蛋白定点切肽)/③(WT+DAI) 全量重跑。用户授权「整一组跑」，铁律**不能漏跑、多跑没关系、事后必核有没有漏**。
> **看情况分本地/HPC**：原部署 15 工具本地(WSL2/docker/R/CPU/RTX4070)、15 工具 HPC(conda/sif/DTU)——本地半**不用碰 HPC 上传**。Conductor 图=`quantimmu-rerun`。

## 0.0 ⚠️ 撞车协调铁律 + 实时进度（2026-07-07 多窗并行踩到，必读）
> DAG 曾从工具组切片重构为按位置切片（本窗干的，扰动了正跑的窗）。教训：**`scripts/out_rerun_official/<Tool>_official.csv` 存在(4053行) = 该工具已完成 = 唯一真源，DAG 节点名次要**。
- **开工跑任何工具前先查该工具 CSV 是否已存在 → 存在即 skip 直接复用，绝不重跑**（避免重复 + 避免踩别窗已解的坑：MHCnuggets 权重名含冒号 Windows 存不了、TransHLA 权重镜像慢下载——这俩**已由 presml 窗跑完在 CSV 里**，别再本地重跑）。
- **✅ 已完成 21/30**：BigMHC_IM, CNNeo, HLAthena, IEDB_Calis, IMPROVE, ImmuGenX, MHCseqNet, MHCflurry, MHCnuggets, NeoTImmuML, NeoaG, NetTepi, PredIG, Seq2Neo, TSCAPE, TransHLA, deepHLApan, netMHCpan_BA, netMHCpan_EL, netMHCstabpan, pTuneos
- **⏳ 剩 9 个**：本地(WSL2/R) 4 = **DeepImmuno, Repitope, MUNIS, DeepNetBim** ｜ HPC 5 = **ImmuneApp, PRIME, ICERFIRE, andy90, NeoaPred**(结构慢)。谁空谁跑剩下的，跑前查 CSV。
- **待补 1**：NeoTImmuML 漏 5 格(见 §3.5)。
- 真实进度用 `python scripts/build_coverage_matrix.py`（逐工具覆盖%，比 DAG 节点准）。

## 0. 已就绪（prep ✓，本窗完成，别重做）
- **完整输入包 `scripts/out_rerun/`**：改动②完整窗集(914 窗=756 SLP+158 MANE, MT+WT 双侧, 102 SNV 肽)灌全 30 工具输入。MT 窗=WT 窗=914，manifest=`data/frozen/rerun_input_manifest.NEW.csv`，全非空。3 旧名基因已补(CCDC104/CCDC130/KIAA1429)，isoform 冲突 0，仅 4 END_TRUNCATED(落 `newcut_dropped_windows.NEW.csv`)。
- 数据真源：`data/frozen/newcut_subpep_hla_{MT,WT}.for_tools.csv`、`newcut_mt_wt_pairs.NEW.csv`。

## 1. 本地切片（在本机 WSL2/docker/R/RTX4070 跑，**无需上传 HPC**）
认领：`python tools/pipeline.py claim quantimmu-rerun <slice> <窗名>`；完成 `done`。**喂 `scripts/out_rerun/` 对应输入**，各工具复用原部署环境（见下表右列，真源 `TOOL_RERUN_STATUS.md`）。

| 切片 | 工具(8/7) · 原环境 |
|---|---|
| **slice_local_a** | IEDB_Calis(本地 py) · DeepImmuno(WSL deepimmuno TF2.3) · BigMHC_IM(本地 CPU torch) · CNNeo(本地 CPU torch) · MHCnuggets(WSL2 CPU TF2.10) · ImmuGenX(WSL2 CPU torch1.12) · MUNIS(WSL munis_env ESM-2 CPU) · DeepNetBim(WSL qib_tf1 TF1.15) |
| **slice_local_b** | Seq2Neo(本地 pip+自带 netMHCpan-4.1/netCTLpan) · NeoaG(本地 R4.3.3 GBM) · Repitope(本机 R4.3.3 proven) · pTuneos(WSL docker bm2lab/ptuneos) · deepHLApan(WSL docker biopharm/deephlapan) · TransHLA(WSL2 RTX4070 GPU) · TSCAPE(WSL2 tscape env RTX4070, 仅 best_param/pmhc_im_neo 0.53G) |

**每本地切片窗做**：本机激活各工具 env → 跑 `out_rerun/` 的 MT+WT 双侧 → parse 落 `scripts/out_rerun_official/<Tool>_official.csv` → 核输出行数对上输入窗×HLA → `done`。GPU 工具(TransHLA/TSCAPE)串行占本机 RTX4070(8GB)，别与训练撞。**本机无需 gpu_slot HPC 申请**(本地卡)，但两 GPU 工具彼此串行。

## 2. HPC 切片（**需上传 out_rerun/ 到 HPC** + conda/sif/DTU）
| 切片 | 工具(6/9) · 原环境 |
|---|---|
| **slice_hpc_dtu** | netMHCpan_BA · netMHCpan_EL · netMHCstabpan · andy90(需 netMHCpan) · NetTepi · ICERFIRE — 全 DTU 二进制(`ext_tools/`)；**consent=发表闸非算力闸**，照跑；netMHCpan=DAI 硬输入 |
| **slice_hpc_env** | ImmuneApp(envs) · PRIME(envs) · PredIG(sif) · IMPROVE(envs imp_feat+improve) · MHCflurry(envs) · MHCseqNet(envs 复用) · HLAthena(sif) · NeoTImmuML(envs) · NeoaPred(结构物理最慢,单独排/可搁置) |

**HPC 共享前置**(第一个 HPC 切片窗做一次，🛑对外传输先报)：上传 `scripts/out_rerun/` 到 `/gpfs/work/bio/jiayu2403/quantimmu/rerun/`。HPC 根=`/gpfs/.../quantimmu`(tools_repos/ext_tools/sif/envs 47G 已在)；conda 激活 `module load miniconda3/... + conda activate envs/<tool>`。
**每 HPC 切片窗做**：`gpu_slot.py request quantimmu-rerun hpc 1`(GPU 工具)→ sbatch 各工具 on `out_rerun/` MT+WT → 拉回 parse 落 `out_rerun_official/` → 核行数 → `done`。

## 3. 收口（4 切片全 done 后一个窗接）
- **merge**🛑：`python scripts/merge_official_30.py --strict-roster`(**缺任一 roster 工具报错**=不能漏出口硬闸)→ `merged_all_tools_30_rerun.csv`。
- **coverage**(verifier)：**逐(窗×HLA×side×工具)覆盖矩阵**，空缺**逐条列原因**(工具不支持 HLA/长度=正常 vs 真漏=补)。用户「事后必核有没有漏」的命门交付。
- **pool**(coder)：`p0e2_pool_clean.py --ninemer --input merged_rerun` → max pooling → `per_patient_spearman_multimethod.py` → 改动②最终 max 排名，对照 SLP 版(MHCnuggets 0.476/netMHCpan_BA 0.469)看溢出补全变化。
- **dai**(主线)：`R10_feature_builder.py --wt_scores` DAI(MT/WT 同窗配对已备)→ 解锁 L2/R10，**别预焊胜利**(旧 SLP DAI 只帮 4/24)。
- **recheck**(verifier)：核数字对 claim i/ii/iii + csv 三方对账。

## 3.5 切片窗自查（跑完 done 前必做，分布式「不能漏」）
每切片窗跑完自己的工具后、`done` 前：`python scripts/build_coverage_matrix.py` → 看**自己那几个工具**有没有 🔴unknown（真漏=工具在同长度+同HLA别处打过分却漏某格）。有 unknown 就补跑那几格再 done，别把漏留给收口。（覆盖脚本已修多列工具 deepHLApan/MHCflurry 归位。）

**⚠️ 已知待补（hpcENV 窗）**：NeoTImmuML 漏 5 格 = 窗 `AAALGFAFY`(患者 106-06 MANE 溢出窗, bb_idx 2129-2133) × HLA-A*03:01/A*31:01/B*40:01/B*55:01/C*03:03 全 NaN（NeoTImmuML 支持这些 HLA、别处打过，就这窗跳了）。补跑这 5 格再 done slice_hpc_env。详 `data/frozen/coverage_gaps.NEW.csv` reason=unknown。

## 4. 铁律（全窗通用）
- **不能漏**：strict-roster 硬闸 + 覆盖矩阵双保险 + 切片窗自查（§3.5）三重；被排除的格子必显式记原因，绝不静默丢。多跑没关系。
- **本地半不碰 HPC**；HPC 半上传先报，GPU 经 `gpu_slot.py` 不挤正在跑的。数字 Bash/Grep 核 csv 不信 Read。
- 状态真源=`python tools/pipeline.py status quantimmu-rerun`，别手改 JSON。
