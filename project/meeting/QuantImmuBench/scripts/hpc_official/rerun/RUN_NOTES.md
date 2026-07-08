# slice_immbox 全量重跑 — HPC 启动 + 本地 parse 命令（2026-07-07）

服务 QuantImmuBench slice_immbox 全量重跑（改动②/③）。新输入 4053 backbone（旧 official 为 1761）。
本文件由 coder 写，**所有命令由主线跑**（agent 不跑任何代码 / 不连 HPC）。

## 约定路径
- HPC base（下称 `$BASE`）= `/gpfs/work/bio/jiayu2403/quantimmu`
- 新输入镜像：`$BASE/rerun/`（= 本地 `scripts/out_rerun/`）
- 新输出统一：`$BASE/rerun_out/`
- 本地 parse 产物：`scripts/out_rerun_official/<Tool>_official.csv`
- parse 用 backbone/master（4053 行）：`scripts/out_rerun/master_backbone_official.csv`

---

## A. HPC 启动（主线在 HPC 上串行跑）

### 1) PredIG（本目录 `run_predig_rerun.sh`，含分块）
输入 `$BASE/rerun/predig_input.csv`（8106 数据行，超容器 5000 上限 → 脚本自动切 ≤4000 行/块，
3 块），逐块 `singularity run predig.sif`，按 `ls -v` 序拼回 → `$BASE/rerun_out/predig_out/predig_out.csv`。
纯 CPU。直跑或 sbatch（脚本顶部 `#SBATCH` 头已备 cpudebug / cpus=16 / mem=64G / time=12h）：
```
bash $BASE/rerun/hpc_official/rerun/run_predig_rerun.sh      # 上传后按实际路径调整
# 或： sbatch run_predig_rerun.sh
```

### 2) Repitope（本目录 `run_repitope_rerun.sh`）
PEP_CSV=`$BASE/rerun/newtools/uniq_pep.csv`（1648 唯一肽），OUTDIR=`$BASE/rerun_out/repitope_out`。
CPU+Java 重活，DTN 直跑或 CPU 分区 sbatch：
```
bash run_repitope_rerun.sh
# 长跑脱离： setsid nohup bash run_repitope_rerun.sh > $BASE/rerun_out/repitope_out/run.log 2>&1 &
```
⚠️ 依赖：`run_repitope.R` 需在本脚本父目录 `scripts/hpc_official/` 下（脚本已自动两处探测，
或 `REPITOPE_R=<路径> bash run_repitope_rerun.sh` 显式指定）。产出 `$OUTDIR/Repitope_scores.csv`。

### 3) IMPROVE（无需改脚本，env 覆盖既有 `run_improve_official.sh`）
`run_improve_official.sh` 的 INPUT/OUTDIR 走 env 覆盖，STAB/FOREIGN 亦然。确切启动行：
```
INPUT=$BASE/rerun/improve_input.tsv OUTDIR=$BASE/rerun_out/improve_official_run STAB=1 FOREIGN=1 bash run_improve_official.sh
```
（improve_input.tsv 4053 行；档 II = 真 Stability + 真 Foreignness；产出
`$BASE/rerun_out/improve_official_run/improve_simple_official.tsv`，关键列 `mean_prediction_rf`。）

---

## B. 本地 parse 命令（主线拉回 HPC 输出后跑）

拉回约定：把 `$BASE/rerun_out/<X>` 下载到本地 `scripts/out_rerun/<X>`（下方 `--输入` 用本地路径）。
所有 parse 已核 argparse 参数名真实存在（读源码确认，非臆测）。在
`D:/YJ-Agent/project/meeting/QuantImmuBench/` 下跑，先 `mkdir scripts/out_rerun_official`。

### 1) PredIG（`parse_predig_official.py`；参数 --out-csv/--input-csv/--map-csv/--backbone/--out）
```
python scripts/hpc_official/parse_predig_official.py \
  --out-csv   scripts/out_rerun/predig_out/predig_out.csv \
  --input-csv scripts/out_rerun/predig_input.csv \
  --map-csv   scripts/out_rerun/predig_input_map.csv \
  --backbone  scripts/out_rerun/master_backbone_official.csv \
  --out       scripts/out_rerun_official/PredIG_official.csv
```
（三方按行序位置对齐 + 三道断言；`predig_out.csv` = HPC 拼接后输出拉回本地。）

### 2) pTuneos（`parse_ptuneos_official.py`；参数 --ptuneos-out/--backbone/--out-dir）
```
python scripts/hpc_official/parse_ptuneos_official.py \
  --ptuneos-out scripts/out_rerun/ptuneos/work_official/ptuneos_official_output.tsv \
  --backbone    scripts/out_rerun/master_backbone_official.csv \
  --out-dir     scripts/out_rerun_official
```
（写 `pTuneos_official.csv`（--out-dir 下），列 bb_idx, MT_pTuneos。TODO：pTuneos 重跑 run 脚本
不在本 agent 交付范围内；`--ptuneos-out` 的确切 HPC 产出路径以 pTuneos rerun run 脚本为准，
上方按旧脚本 `work_official/ptuneos_official_output.tsv` 命名推定，拉回时对齐实际文件名。）

### 3) deepHLApan（`parse_deephlapan_official.py`；参数 --out-root/--map-dir/--backbone/--out-dir）
```
python scripts/hpc_official/parse_deephlapan_official.py \
  --out-root  scripts/out_rerun/deephlapan_out \
  --map-dir   scripts/out_rerun \
  --backbone  scripts/out_rerun/master_backbone_official.csv \
  --out-dir   scripts/out_rerun_official
```
（`--out-root` 下需含 `deephlapan_out_MT/` 与 `deephlapan_out_WT/`（各含 `*_predicted_result.csv`）；
`--map-dir` 用 `scripts/out_rerun/`（已含 `deephlapan_input_map_MT.csv` / `_WT.csv`）。写
`deepHLApan_official.csv`。TODO：deepHLApan 重跑 run 脚本非本 agent 交付；`--out-root` 结构以其
rerun run 脚本产出为准，上方按旧 `deephlapan_out/deephlapan_out_MT|WT` 命名推定。）

### 4) NeoTImmuML（`parse_neotimmuml_official.py`；参数 --scores/--backbone/--out-dir）
```
python scripts/hpc_official/parse_neotimmuml_official.py \
  --scores   scripts/out_rerun/neotimmuml_scores_official.csv \
  --backbone scripts/out_rerun/master_backbone_official.csv \
  --out-dir  scripts/out_rerun_official
```
（HLA-agnostic 纯肽→分广播；写 `NeoTImmuML_official.csv`，列 bb_idx, MT_NeoTImmuML, WT_NeoTImmuML。
TODO：NeoTImmuML 重跑 run 脚本非本 agent 交付；`--scores` 路径以其 rerun run 脚本产出为准，
上方按旧 `neotimmuml_scores_official.csv` 命名推定。）

### 5) Repitope（`parse_repitope_official.py`；参数 --scores/--backbone/--out）
```
python scripts/hpc_official/parse_repitope_official.py \
  --scores   scripts/out_rerun/repitope_out/Repitope_scores.csv \
  --backbone scripts/out_rerun/master_backbone_official.csv \
  --out      scripts/out_rerun_official/Repitope_official.csv
```
（HLA-agnostic 纯肽广播；`Repitope_scores.csv` = 本目录 `run_repitope_rerun.sh` 产出拉回本地。）

### 6) IMPROVE（`parse_improve_official.py`；参数 --pred/--map-csv/--master/--out）
```
python scripts/hpc_official/parse_improve_official.py \
  --pred    scripts/out_rerun/improve_official_run/improve_simple_official.tsv \
  --map-csv scripts/out_rerun/improve_input_map.csv \
  --master  scripts/out_rerun/master_backbone_official.csv \
  --out     scripts/out_rerun_official/IMPROVE_official.csv
```
（写 `IMPROVE_official.csv`，列 bb_idx, MT_IMPROVE；`improve_simple_official.tsv` = IMPROVE
run 产出拉回本地。IMPROVE 无独立 WT 免疫原分，故无 WT 列。）

---

## C. 保真 / 校验说明
- 6 个 parse 脚本用 `master_backbone_official.csv`（4053 行）定 bb_idx 全集，输出对齐 4053 行；
  精确 (肽,等位) / 三元组匹配缺 → 该单元留空（NaN），**绝不肽级以外兜底造数**。
- `official_io.py` 系硬校验输出行数 == backbone 行数（读入 master 决定，非硬编码 4053），4053 行
  master → 校验 4053，无需改。
- 复现零偏离：PredIG(recombinant+neoant) / Repitope(官方 R) / IMPROVE(Simple, 档 II) 口径均与
  旧 official 一致，未改超参/模型/裁剪；所有工具方向照原（分越高越免疫原，无翻转）。
