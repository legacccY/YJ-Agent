#!/usr/bin/env bash
# =============================================================================
# run_predig_ds1.sh — PredIG on DS1 输入（HPC, CPU only, 分块）
# =============================================================================
# 服务: QuantImmuBench DS1 独立人类队列复现集（lever=PredIG，全 9mer）
#
# 克隆自 rerun8to11/run_predig_8to11.sh，唯一改动 = 输入/输出路径 rerun8to11→ds1：
#   - 输入切到 DS1 版 $BASE/ds1/predig_input.csv（DS1 数据行 <4000 → 单块，逻辑通用）。
#   - 输出统一落 $BASE/ds1/predig_out/predig_out.csv。
#   - 分块 + 拼接逻辑逐字保留（≤4000 行/块，split 保序 + 逐段前置表头 + 按 ls -v 序拼接）。
#     输入是现成 CSV（ds1/predig_input.csv 已由 prepare_inputs 产），不用 prep，直接按行切。
#
# 【真入口】predig.sif 是 OCI 镜像，runscript = python /Immuno/run_predig/run.py，
#   故用 `singularity run`（执行 runscript）而非 `singularity exec ... predig`。
#   入参与 docker/official 完全一致：
#   <input.csv 位置参> -o <out.csv> --modelXG neoant --type recombinant。
#
# 复现零偏离：口径与 DS2 official 严格一致（recombinant + neoant），不改超参/模型/裁剪。
# PredIG 分越高越免疫原（官方原始方向，无翻转）。
#
# 跑法（主线串行）：
#   直跑： bash run_predig_ds1.sh          （纯 CPU，无需 GPU）
#   或 sbatch 包一层（下方 #SBATCH 头已备，走 cpudebug 分区）。
#
#SBATCH --job-name=predig_ds1
#SBATCH --partition=cpudebug
#SBATCH --qos=cpudebug
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=12:00:00
#SBATCH --output=%x_%j.log
set -euo pipefail

# ---------------------------------------------------------------------------
# 路径配置
# ---------------------------------------------------------------------------
BASE="${QIB_BASE:-/gpfs/work/bio/jiayu2403/quantimmu}"
SIF="$BASE/sif/predig.sif"
INPUT_CSV="$BASE/ds1/predig_input.csv"                 # 现成输入，只读
WORKDIR="$BASE/ds1/predig_out/work"                    # singularity 挂载 → /work（放分块/中间 out）
FINAL_OUT="$BASE/ds1/predig_out/predig_out.csv"        # 拼接后最终输出
CHUNK_ROWS=4000                                        # 每块 ≤4000 数据行（< 容器 5000 上限）

echo "[INFO] SIF        = $SIF"
echo "[INFO] INPUT_CSV  = $INPUT_CSV"
echo "[INFO] WORKDIR    = $WORKDIR"
echo "[INFO] FINAL_OUT  = $FINAL_OUT"
echo "[INFO] CHUNK_ROWS = $CHUNK_ROWS"
echo "[INFO] -----------------------------------------------------------------"

[ -f "$SIF" ]       || { echo "[FATAL] 缺 sif: $SIF"; exit 1; }
[ -f "$INPUT_CSV" ] || { echo "[FATAL] 缺输入: $INPUT_CSV"; exit 1; }
mkdir -p "$WORKDIR"

n_in=$(($(wc -l < "$INPUT_CSV") - 1))
echo "[INFO] 输入数据行（不含表头）= $n_in"

# ── 1) 分块：按行切 ≤CHUNK_ROWS 行/块，保表头 + 行序 ────────────────────────────
rm -f "$WORKDIR"/input_chunk*.csv "$WORKDIR"/out_chunk*.csv "$WORKDIR"/_data_part_* "$WORKDIR/out.csv"
HEADER="$(head -n 1 "$INPUT_CSV")"
tail -n +2 "$INPUT_CSV" | split -l "$CHUNK_ROWS" -d -a 3 - "$WORKDIR/_data_part_"
i=0
for part in $(ls -v "$WORKDIR"/_data_part_*); do
  i=$((i + 1))
  { printf '%s\n' "$HEADER"; cat "$part"; } > "$WORKDIR/input_chunk${i}.csv"
done
rm -f "$WORKDIR"/_data_part_*
echo "[INFO] 切成 $i 块（每块含 1 表头 + ≤$CHUNK_ROWS 数据行）"

# ── 2) 逐块 singularity 跑 PredIG（绕容器 <5000 行限制）──────────────────────────
echo "[INFO] PredIG start $(date) node=$(hostname)"
for cf in $(ls -v "$WORKDIR"/input_chunk*.csv); do
  base="$(basename "$cf" .csv)"      # input_chunkK
  k="${base#input_}"                  # chunkK
  echo "[INFO]   块 $k → $(($(wc -l < "$cf") - 1)) 数据行"
  singularity run --writable-tmpfs \
    -B "$WORKDIR:/work" \
    "$SIF" \
    "/work/input_${k}.csv" -o "/work/out_${k}.csv" --modelXG neoant --type recombinant
done
echo "[INFO] PredIG exit=$? end $(date)"

# ── 3) 拼接：各块 out 按 ls -v 序拼回 out.csv（仅首块保表头，FNR==1 去重）───────────
awk 'FNR==1 { if (seen++) next } { print }' $(ls -v "$WORKDIR"/out_chunk*.csv) > "$WORKDIR/out.csv"
n_out=$(($(wc -l < "$WORKDIR/out.csv") - 1))
echo "[INFO] 拼接 $(ls -v "$WORKDIR"/out_chunk*.csv | wc -l) 块 → out.csv（$n_out 数据行）"

# ── 4) 落最终输出 predig_out.csv ────────────────────────────────────────────────
mkdir -p "$(dirname "$FINAL_OUT")"
cp "$WORKDIR/out.csv" "$FINAL_OUT"

if [ -s "$FINAL_OUT" ]; then
  echo "[DONE] PredIG ds1 输出 $n_out 数据行 → $FINAL_OUT"
  echo "[DONE] （预期 $n_in 行；行数应等于输入，parse 阶段按行序位置 join + 断言）"
  if [ "$n_out" -ne "$n_in" ]; then
    echo "[WARN] 输出 $n_out 行 != 输入 $n_in 行，parse 位置对齐会失败，请先排查。" >&2
  fi
else
  echo "[FATAL] 输出 $FINAL_OUT 为空，PredIG 未产结果。" >&2
  exit 1
fi
