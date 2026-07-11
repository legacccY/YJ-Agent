# DS1 全 30 工具重跑 · 多窗启动指南（quantimmu-ds1 DAG）

> 建 2026-07-11（主窗）。给新窗口直接读的自包含启动指南。DS1（老师给的独立人类队列）以新切 9mer 口径在全 30 工具上跑，作 DS2 之外的**独立复现集加固阴性结论**。
> 输入包主窗已产（`scripts/out_ds1/`）；本指南给 4 个 slice 窗 + 收口窗并行分工。Conductor 图=`quantimmu-ds1`。

## 0. 先读档（强制，别跳）
本窗做 quantimmu-bench 的 DS1 子任务。开工先认领 **slice claim**：`python tools/pipeline.py claim quantimmu-ds1 <slice>`，再读：
- `04_LOG.md` 最新 **Entry 66**（DS1 审计 + 适配器 + 输入包全过程，重点读）
- 本指南 §3 找到自己那个 slice 的工具清单/env/输入输出
- `RERUN_LAUNCH_GUIDE.md`（DS2 原版：工具→env 映射 §1/§2、收口 §3、不漏铁律 §4——**本指南复用其脚本，只换输入/输出路径**）

数字一律 Bash/Grep 核 csv，不信 md/Read。**复现零偏离**（工具/权重/超参不改）。

## 1. 目标（一句话）
DS1 = 6 例黑色素瘤 / 82 肽 / **全 9mer** / MT+WT 单点对 / ELISpot 全阳（Entry 66 审计）。灌全 30 工具出 DS1 单工具排名，与 DS2 对照，作独立复现加固阴性。**诚实边界（Entry 63/66）**：DS1 全阳窄 regime、融合在其上负相关，作独立复现集，**不当救融合样本、不预焊胜利**。

## 2. 输入包已就绪（主窗产，别重做）
- **`scripts/out_ds1/`**：backbone 325 行/82 肽（`master_backbone_official.csv`）+ 本地工具输入（deepimmuno/deephlapan/predig/prime×18HLA/immuneapp×18HLA/improve/ptuneos）+ **newtools universe**（`newtools/{universe.csv 326行, uniq_pep_hla.csv, uniq_pep.csv}`，HPC binding 工具通用喂料）。
- 数据真源：`data/frozen/newcut_subpep_hla_{MT,WT}.DS1.for_tools.csv`（各 325 行）+ `ds1_official_groundtruth.csv`（82 行，评估用）。
- **产法（可复现）**：`python scripts/build_ds1_newcut.py`（适配器）→ `python scripts/prepare_inputs_official.py --mt-csv ...DS1... --wt-csv ...DS1... --out-dir scripts/out_ds1 --window 9 --expected-peptides 82`。
- ⚠️ **backbone 的 Elispot 列空**（prepare_inputs 硬编码 join ds2 gt）——无害（工具输入只含肽+HLA）；评估阶段 join `ds1_official_groundtruth.csv`（按 mut_key）。
- ⚠️ **GRM4 患者6 有 1 对同序列/HLA 但 ELISpot 不同**（381/286，两次测量）→ Peptide_ID 加 `-r2` 保 82 条；工具输入按肽×HLA 去重只算一次，评估各配自己 ELISpot。

## 3. 四 slice 分工（各窗认领一个，并行）
**输出统一落 `scripts/out_ds1_official/<Tool>_official.csv`**（独立目录，绝不覆盖 DS2 的 `out_rerun_official/`）。

| slice | 工具 · 原环境（真源 `TOOL_RERUN_STATUS.md`） | 上传 HPC? |
|---|---|---|
| **slice_local_a**(8) | IEDB_Calis(本地py) · DeepImmuno(WSL deepimmuno TF2.3, **仅9-10mer**全支持) · BigMHC_IM(本地CPU torch) · CNNeo(本地CPU torch) · MHCnuggets(WSL2 CPU TF2.10) · ImmuGenX(WSL2 torch1.12) · MUNIS(WSL munis_env ESM-2) · DeepNetBim(WSL qib_tf1 TF1.15) | 否(本地) |
| **slice_local_b**(7) | Seq2Neo(本地pip自带netMHCpan-4.1) · NeoaG(本地R4.3.3) · Repitope(本机R4.3.3) · pTuneos(WSL docker bm2lab) · deepHLApan(WSL docker biopharm) · TransHLA(WSL2 RTX4070) · TSCAPE(WSL2 tscape RTX4070) | 否(本地) |
| **slice_hpc_dtu**(6) | netMHCpan_BA · netMHCpan_EL · netMHCstabpan · andy90(需netMHCpan) · NetTepi · ICERFIRE — 全 DTU 二进制(`$QD/ext_tools/`) | **是**🛑 |
| **slice_hpc_env**(8) | ImmuneApp · PRIME · PredIG(sif) · IMPROVE · MHCflurry · MHCseqNet · HLAthena(sif) · NeoTImmuML（NeoaPred 结构物理最慢，**本轮搁置**） | **是**🛑 |

**工具窗长支持**：DS1 全 9mer → DeepNetBim(仅9mer)/DeepImmuno(仅9-10mer) **本轮全适用**，无长度剔除。

## 4. 各 slice 执行步骤（复用 DS2 脚本，只换路径 out_rerun→out_ds1）
**本地 slice（a/b）**：本机激活各工具 env → 喂 `out_ds1/` 对应输入 → parse 落 `out_ds1_official/<Tool>_official.csv` → 核输出行数对上输入肽×HLA → `done`。
- ⚠️ WSL bash 命令前缀 `MSYS_NO_PATHCONV=1`（防 `/mnt/d/...` 被 Git Bash 转坏）。
- GPU 工具(TransHLA/TSCAPE)串行占本机 RTX4070，**避开训练**（查 `gpu_slot.py`）。
- 各工具 run 脚本参考 DS2：`scripts/run_deepimmuno_official.py`、`scripts/out_rerun/_run_seq2neo_local.sh` 等，输入路径改 `out_ds1`。

**HPC slice（dtu/env）**：
1. 产 HPC 工具专用输入（从 out_ds1 backbone/universe）：DTU 用 `scripts/hpc_official/prep_dtu_netmhcpan_official.py`（产 `.pep`+`allele_map.tsv`，输入指向 out_ds1）；env 工具 deploy 脚本读 `out_ds1/newtools/uniq_pep_hla.csv`。
2. 🛑**上传 out_ds1 到 HPC `$QD/ds1/`**（对外传输拍板点，停下报主窗/用户放行后传）。HPC 根 `$QD=/gpfs/work/bio/jiayu2403/quantimmu`，工具二进制/env/sif（47G）已在。上传 helper=`scripts/_rerun_hpc.py putdir`。
3. `gpu_slot.py request quantimmu-ds1 hpc <0或1>`（CPU 工具填 0 不占卡；GPU 工具填 1）→ sbatch（QOS 限用 `/loop` 轮询）→ 拉回 parse 落 `out_ds1_official/` → 核行数 → `done`。
4. 参考 DS2 HPC 编排 `scripts/out_rerun/dtu_hpc_run.py`（step=upload/submit/poll/download）+ `hpc_official/run_dtu_*.sh`，路径改 ds1。

## 5. 收口（4 slice 全 done 后，收口窗接）
- **merge**🛑：`python scripts/merge_official_30.py --in-dir scripts/out_ds1_official --out scripts/out/merged_all_tools_30_ds1.csv --pure-new --strict-roster`（缺任一 roster 工具报错=不漏硬闸）。
- **coverage**(verifier)：`python scripts/build_coverage_matrix.py`（指向 out_ds1_official）逐(肽×HLA×side×工具)核，空缺逐条记原因（工具不支持=正常 vs 真漏=补）。
- **pool**(coder)：`p0e2_pool_clean.py --input merged_ds1` → per-patient Spearman → DS1 单工具排名（用 ds1 gt 的 ELISpot）。
- **recheck**(verifier)：核数字 + 与 DS2 单工具排名对照 + 落 04_LOG。

## 6. 铁律（全窗通用，命门）
- **不能漏**：`merge --strict-roster` 硬闸 + 覆盖矩阵 + 切片窗自查三重；被排除格必显式记原因，绝不静默丢。多跑没关系，漏跑不行。
- **复现零偏离**：工具/权重/超参一律不改，完全按 DS2 同口径（DS1 只是换输入数据）。
- **本地半不碰 HPC**；HPC 半上传先报（对外传输拍板点）；GPU 经 `gpu_slot.py` 不挤正在跑的。
- **数字 Bash/Grep 核 csv 不信 Read**。
- **DS1 诚实边界**：独立复现加固阴性，不当救融合样本、不预焊胜利。
- 状态真源=`python tools/pipeline.py status quantimmu-ds1`，别手改 JSON。

## 7. DoD（每 slice 完成线）
自己那几个工具全部 parse 落 `out_ds1_official/<Tool>_official.csv` + 行数核对上输入 + 覆盖自查无真漏（`build_coverage_matrix.py` 看自己的工具无 🔴unknown）→ `python tools/pipeline.py done quantimmu-ds1 <slice>`。**到 DoD 停，不冲下一棒**（收口由收口窗接）。

## 8. 开窗认领
```
# 各窗选一个 slice 认领（4 窗并行 + 可选 1 收口窗）
python tools/pipeline.py claim quantimmu-ds1 slice_local_a   # 窗1
python tools/pipeline.py claim quantimmu-ds1 slice_local_b   # 窗2
python tools/pipeline.py claim quantimmu-ds1 slice_hpc_dtu   # 窗3（HPC，上传先报）
python tools/pipeline.py claim quantimmu-ds1 slice_hpc_env   # 窗4（HPC，上传先报）
python tools/pipeline.py status quantimmu-ds1                # 看全貌
```
