# RUN_NOTES_DS1 — DS1 独立人类队列复现集 · slice_hpc_env 8 工具确切启动命令

服务 QuantImmuBench DS1（Elispot_Dataset1，6 例黑色素瘤/82 肽/全 9mer/MT+WT/ELISpot 全阳）
§ slice_hpc_env（窗4）。lever = 7 HPC 工具 + NeoTImmuML（本机）。
输入路径 `$BASE/rerun8to11/` → `$BASE/ds1/`（隔离，DS2 脚本零改动，只换路径）。

- **HPC BASE** = `/gpfs/work/bio/jiayu2403/quantimmu`（下称 `$BASE`）。工具二进制/env/sif（47G）已在。
- **本目录 4 脚本上传到** `$BASE/ds1/hpc_official/`（与 DS2 的 `$BASE/rerun8to11/hpc_official/` 平行隔离）。
- **🛑 上传 out_ds1 到 `$BASE/ds1/` = 对外传输拍板点**，停下报主窗/用户放行后传。helper=`scripts/_rerun_hpc.py putdir`。
- **上传前建目录**：`mkdir -p $BASE/ds1/logs`。
- **上传后必 dos2unix 全部输入 + 脚本**（不止脚本，见 feedback_hpc_submit_checklist；DS2 slice_hpc_dtu 踩过 CRLF 坑）：`find $BASE/ds1 -name '*.sh' -o -name '*.csv' -o -name '*.txt' -o -name '*.tsv' | xargs sed -i 's/\r$//'`。
- **卡槽**：CPU 工具填 0 卡（`gpu_slot.py request quantimmu-ds1 hpc 0`），恒 GO 不占卡。全 env 工具纯 CPU/推理。
- 输出统一落本地 `scripts/out_ds1_official/<Tool>_official.csv`（不覆盖 DS2 的 `out_rerun_official*/`）。
- DS1 全 9mer → 无长度剔除；HLAthena 9mer 走 ecdf 近满覆盖（DS1 HLA 集含 B*27:05 有 ecdf，无 B*27:06 缺口）。

---

## 1) ImmuneApp（HPC, cpudebug）
```
sbatch $BASE/ds1/hpc_official/run_immuneapp_ds1.sh
```
- INPUT_BASE=`$BASE/ds1`（读 immuneapp_input_*/peps_MT.txt + peps_WT.txt，18 allele），OUTPUT=`$BASE/ds1/immuneapp_out`。
- MT+WT 双侧全跑。完成标记 `IMMUNEAPP_DS1_DONE`。

## 2) PRIME（HPC, cpudebug）
```
sbatch $BASE/ds1/hpc_official/run_prime_ds1.sh
```
- INPUT_BASE=`$BASE/ds1`（读 prime_input_*/peps_MT.txt + peps_WT.txt，18 allele），OUTPUT=`$BASE/ds1/prime_out`。
- MixMHCpred 自动定位不变。完成标记 `PRIME_DS1_DONE`。

## 3) PredIG（HPC, cpudebug, singularity 分块）
```
sbatch $BASE/ds1/hpc_official/run_predig_ds1.sh
# 或 DTN 直跑（纯 CPU）：bash $BASE/ds1/hpc_official/run_predig_ds1.sh
```
- INPUT=`$BASE/ds1/predig_input.csv`（DS1 650 数据行，<4000 → 单块），OUTPUT=`$BASE/ds1/predig_out/predig_out.csv`。
- invocation `--modelXG neoant --type recombinant` 逐字不变。完成后自检输出行数 == 输入 650。

## 4) HLAthena（HPC, singularity；DTN 直跑，无 #SBATCH 头）
```
bash $BASE/ds1/hpc_official/run_hlathena_ds1.sh
```
- UNIQ=`$BASE/ds1/newtools/uniq_pep_hla.csv`（642 对），WORK=`$BASE/ds1/hlathena_official`，RAW=`$BASE/ds1/hlathena_raw.csv`。
- PATCHED 复用 `$BASE/hla_predict_patched.bash`。并发 `xargs -P 4`。完成标记 `HLATHENA_DS1_DONE`。

## 5) IMPROVE（HPC；env 覆盖复用 9mer 脚本，无需新脚本）
```
INPUT=$BASE/ds1/improve_input.tsv \
OUTDIR=$BASE/ds1/improve_official_run \
STAB=1 FOREIGN=1 \
bash $BASE/rerun8to11/hpc_official/run_improve_official.sh
```
- **复现 = 档 II 真 Foreignness，`STAB=1 FOREIGN=1`**（需 garnish_r env 在 `$BASE/envs/garnish_r`）。
- `run_improve_official.sh` 走 env 变量覆盖 INPUT/OUTDIR/STAB/FOREIGN，直接引用 DS2 副本即可。

## 6) MHCflurry（HPC；参数化 py，直跑）
```
conda activate $BASE/envs/mhcflurry
python <HPC/deploy/mhcflurry/run_mhcflurry.py> \
  --input $BASE/ds1/mhcflurry_input_official.csv \
  --raw-out $BASE/ds1/mhcflurry_raw.csv
```
- 输入 642 行。产列 peptide / HLA_Allele / affinity / presentation_score / processing_score。

## 7) MHCseqNet（HPC；参数化 py，直跑，借 immuneapp env）
```
conda activate $BASE/envs/immuneapp
python <run_mhcseqnet_official.py> \
  --input $BASE/ds1/mhcseqnet_input_official.csv \
  --repo $BASE/tools_repos/MHCSeqNet \
  --out $BASE/ds1/mhcseqnet_raw.csv
```
- 输入 642 行。已参数化 input/repo/out。

## 8) NeoTImmuML（本机 R4.3.3，非 HPC；env 覆盖复用 9mer 脚本）
```
OUTDIR=<本机输出目录> \
BACKBONE=D:/YJ-Agent/project/meeting/QuantImmuBench/scripts/out_ds1/master_backbone_official.csv \
bash run_neotimmuml_official.sh
```
- BACKBONE 用 DS1 版 master_backbone_official.csv（325 行）。⚠️ `extract_peptides` 8-13mer 完整覆盖 9mer。
- ⚠️ 复用 9mer models_official（不重训防漂移）。calc_78_features.R 已修 header bug（见 Entry 65）。

---

## 覆盖清单
| # | 工具 | host | 脚本 | 新脚本? |
|---|------|------|------|--------|
| 1 | ImmuneApp | HPC | run_immuneapp_ds1.sh | ✅ 新（路径 swap） |
| 2 | PRIME | HPC | run_prime_ds1.sh | ✅ 新（路径 swap） |
| 3 | PredIG | HPC | run_predig_ds1.sh | ✅ 新（路径 swap） |
| 4 | HLAthena | HPC | run_hlathena_ds1.sh | ✅ 新（路径 swap） |
| 5 | IMPROVE | HPC | run_improve_official.sh（env 覆盖，复用 DS2） | ❌ 复用 |
| 6 | MHCflurry | HPC | run_mhcflurry.py（参数化，复用） | ❌ 复用 |
| 7 | MHCseqNet | HPC | run_mhcseqnet_official.py（参数化，复用） | ❌ 复用 |
| 8 | NeoTImmuML | 本机 R | run_neotimmuml_official.sh（env 覆盖，复用） | ❌ 复用 |

## DoD
8 工具全 parse 落 `scripts/out_ds1_official/<Tool>_official.csv` + 行数核对上 backbone（325 行 × MT/WT）
+ `build_coverage_matrix.py` 我 8 工具无 🔴unknown（documented 缺口除外）→ `pipeline.py done quantimmu-ds1 slice_hpc_env`。
到 DoD 停，不冲收口（merge 由收口窗接）。
