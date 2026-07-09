# RUN_NOTES_8TO11 — 8-11mer 可变窗全量重跑 · 全工具确切启动命令

服务 QuantImmuBench 改动②③「8-11mer 可变窗全量重跑」§ slice_hpc_env（W4）。
lever = 7 个 HPC 工具 + NeoTImmuML，输入路径 `$BASE/rerun/` → `$BASE/rerun8to11/`（隔离，9mer 原脚本零改动）。

- **HPC BASE** = `/gpfs/work/bio/jiayu2403/quantimmu`（下称 `$BASE`）。
- **本目录 4 脚本上传到** `$BASE/rerun8to11/hpc_official/`（与 9mer 的 `$BASE/rerun/hpc_official/` 平行隔离）。
- **上传前先建目录**：`mkdir -p $BASE/rerun8to11/logs`（immuneapp/prime 的 #SBATCH output/error 落这里）。
- **换行**：脚本本地写 LF；主线上传后统一 `sed -i 's/\r$//'` 去 CRLF 保险。
- 本 agent 只写脚本，**不跑任何代码/不连 HPC**——以下命令主线照抄执行（复现零偏离：路径外零改动）。

---

## 1) ImmuneApp（HPC, cpudebug）
```
sbatch $BASE/rerun8to11/hpc_official/run_immuneapp_8to11.sh
```
- INPUT_BASE=`$BASE/rerun8to11`（读 immuneapp_input_*/peps_MT.txt + peps_WT.txt），OUTPUT=`$BASE/rerun8to11/immuneapp_out`。
- MT+WT 双侧全跑。完成标记 `IMMUNEAPP_8TO11_DONE`。

## 2) PRIME（HPC, cpudebug）
```
sbatch $BASE/rerun8to11/hpc_official/run_prime_8to11.sh
```
- INPUT_BASE=`$BASE/rerun8to11`（读 prime_input_*/peps_MT.txt + peps_WT.txt），OUTPUT=`$BASE/rerun8to11/prime_out`。
- MixMHCpred 自动定位不变。完成标记 `PRIME_8TO11_DONE`。

## 3) PredIG（HPC, cpudebug, singularity 分块）
```
sbatch $BASE/rerun8to11/hpc_official/run_predig_8to11.sh
# 或 DTN 直跑（纯 CPU，无需 GPU）：
bash $BASE/rerun8to11/hpc_official/run_predig_8to11.sh
```
- INPUT=`$BASE/rerun8to11/predig_input.csv`（34176 数据行），OUTPUT=`$BASE/rerun8to11/predig_out/predig_out.csv`。
- 分块 ≤4000 行/块 → 约 9 块，按序拼接。invocation `--modelXG neoant --type recombinant` 逐字不变。
- 完成后自检：输出行数应 == 输入 34176，否则 [WARN]（parse 位置对齐会失败，需排查）。

## 4) HLAthena（HPC, singularity；DTN 直跑，源脚本无 #SBATCH 头）
```
bash $BASE/rerun8to11/hpc_official/run_hlathena_8to11.sh
```
- UNIQ=`$BASE/rerun8to11/newtools/uniq_pep_hla.csv`，WORK=`$BASE/rerun8to11/hlathena_official`，RAW=`$BASE/rerun8to11/hlathena_raw.csv`。
- PATCHED 复用 `$BASE/hla_predict_patched.bash`（存在则不重建）。
- ⚠️ 并发 `xargs -P 4`（非源脚本 -P 10，唯一 bug-fix：-P 10 超订 4-cpu 崩整等位）。8-11mer 长度过滤不变。
- 完成标记 `HLATHENA_8TO11_DONE`。

## 5) IMPROVE（HPC；env 覆盖复用 9mer 脚本，无需新脚本）
```
INPUT=$BASE/rerun8to11/improve_input.tsv \
OUTDIR=$BASE/rerun8to11/improve_official_run \
STAB=1 FOREIGN=1 \
bash $BASE/rerun8to11/hpc_official/run_improve_official.sh
```
- **复现 9mer = 档 II 真 Foreignness，`STAB=1 FOREIGN=1`**（需 garnish_r env 已在 `$BASE/envs/garnish_r`）。
- `run_improve_official.sh` 走环境变量覆盖 INPUT/OUTDIR/STAB/FOREIGN，**无需新脚本**——把 9mer 的 run_improve_official.sh 一并放到 `$BASE/rerun8to11/hpc_official/`（或直接引用现有 9mer 副本，env 覆盖即可）。

## 6) MHCflurry（HPC；参数化 py，直跑）
```
conda activate $BASE/envs/mhcflurry
python <HPC/deploy/mhcflurry/run_mhcflurry.py> \
  --input $BASE/rerun8to11/mhcflurry_input_official.csv \
  --raw-out $BASE/rerun8to11/mhcflurry_raw.csv
```
- `run_mhcflurry.py` 在 HPC 的 deploy/mhcflurry/ 下，已参数化；产列 peptide / HLA_Allele / affinity / presentation_score / processing_score。

## 7) MHCseqNet（HPC；参数化 py，直跑，借 immuneapp env）
```
conda activate $BASE/envs/immuneapp
python <run_mhcseqnet_official.py> \
  --input $BASE/rerun8to11/mhcseqnet_input_official.csv \
  --repo $BASE/tools_repos/MHCSeqNet \
  --out $BASE/rerun8to11/mhcseqnet_raw.csv
```
- 已参数化 input/repo/out。

## 8) NeoTImmuML（本机 R4.3.3，非 HPC；env 覆盖复用 9mer 脚本）
```
OUTDIR=<本机输出目录> \
BACKBONE=D:/YJ-Agent/project/meeting/QuantImmuBench/scripts/out_rerun/master_backbone_official.csv \
bash run_neotimmuml_official.sh
```
- `run_neotimmuml_official.sh` 已 env 覆盖 BACKBONE/OUTDIR，无需新脚本。
- ⚠️ 其 `extract_peptides` 是 8-13mer（**完整覆盖 8-11mer**，无需改长度）。
- BACKBONE 用 8-11 版 master_backbone_official.csv（若 8-11 单独产在 out_rerun8to11/ 下则改指该路径；此处按任务给定 out_rerun/ 路径照抄）。

---

## 覆盖清单
| # | 工具 | host | 脚本 | 新脚本? |
|---|------|------|------|--------|
| 1 | ImmuneApp | HPC | run_immuneapp_8to11.sh | ✅ 新 |
| 2 | PRIME | HPC | run_prime_8to11.sh | ✅ 新 |
| 3 | PredIG | HPC | run_predig_8to11.sh | ✅ 新 |
| 4 | HLAthena | HPC | run_hlathena_8to11.sh | ✅ 新 |
| 5 | IMPROVE | HPC | run_improve_official.sh（env 覆盖，复用 9mer） | ❌ 复用 |
| 6 | MHCflurry | HPC | run_mhcflurry.py（参数化，复用） | ❌ 复用 |
| 7 | MHCseqNet | HPC | run_mhcseqnet_official.py（参数化，复用） | ❌ 复用 |
| 8 | NeoTImmuML | 本机 R | run_neotimmuml_official.sh（env 覆盖，复用） | ❌ 复用 |
