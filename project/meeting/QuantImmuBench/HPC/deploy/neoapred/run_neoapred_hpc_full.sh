#!/bin/bash
# =============================================================================
# run_neoapred_hpc_full.sh — NeoaPred 全量 HPC 并行驱动（被 sbatch 调用，或手动）
# 服务 quantimmu-bench §Tier-3。在 gpu4090 节点（48核/257GB）跑。
#
# 用法：bash run_neoapred_hpc_full.sh <input_csv> <work_dir> [N_CHUNKS] [OMP]
#   默认 N=24 OMP=2（48 核满用；257GB 内存不约束）
# 产出：<work_dir>/MhcPep_foreignness_full.csv → 拉回本地 merge_neoapred.py
# =============================================================================
set -uo pipefail
HERE=$(dirname "$(readlink -f "$0")")
INPUT="${1:?need input_csv}"
WORK="${2:?need work_dir}"
N="${3:-24}"
OMP="${4:-2}"

mkdir -p "$WORK/chunks" "$WORK/outs"
echo "[hpc-full] input=$INPUT work=$WORK N=$N omp=$OMP node=$(hostname)"

# 切块
HEADER=$(head -1 "$INPUT")
tail -n +2 "$INPUT" > "$WORK/_data.csv"
TOTAL=$(wc -l < "$WORK/_data.csv")
PER=$(( (TOTAL + N - 1) / N ))
echo "[hpc-full] total=$TOTAL per=$PER"
split -l "$PER" -d -a 3 "$WORK/_data.csv" "$WORK/chunks/part_"
for f in "$WORK"/chunks/part_*; do [ -f "$f.csv" ] && continue; ( echo "$HEADER"; cat "$f" ) > "${f}.csv"; rm -f "$f"; done

chunk_complete() {
  local cc="$1"; local tag; tag=$(basename "$cc" .csv)
  local fn="$WORK/outs/$tag/foreignness.csv"
  [ -s "$fn" ] || return 1
  local exp got; exp=$(( $(wc -l < "$cc") - 1 )); got=$(( $(wc -l < "$fn") - 1 ))
  [ "$got" -ge "$exp" ]
}

# 第一轮：全部并行
echo "[hpc-full] launching $N parallel singularity exec..."
for cc in "$WORK"/chunks/*.csv; do
  tag=$(basename "$cc" .csv)
  bash "$HERE/hpc_neoapred.sh" chunk "$cc" "$WORK/outs/$tag" "$OMP" &
done
wait
echo "[hpc-full] first pass done"

# 重试未完成块（OOM/straggler 不应在 257GB 出现，但保底）
for attempt in 1 2 3; do
  pending=(); for cc in "$WORK"/chunks/*.csv; do chunk_complete "$cc" || pending+=("$cc"); done
  [ "${#pending[@]}" -eq 0 ] && { echo "[hpc-full] all complete"; break; }
  echo "[hpc-full] retry $attempt: ${#pending[@]} chunks"
  for cc in "${pending[@]}"; do tag=$(basename "$cc" .csv); bash "$HERE/hpc_neoapred.sh" chunk "$cc" "$WORK/outs/$tag" "$OMP" & done
  wait
done

# 合并
MERGED="$WORK/MhcPep_foreignness_full.csv"; first=1
for out in "$WORK"/outs/*/foreignness.csv; do
  [ -s "$out" ] || continue
  [ "$first" = 1 ] && { head -1 "$out" > "$MERGED"; first=0; }
  tail -n +2 "$out" >> "$MERGED"
done
echo "[hpc-full] merged → $MERGED rows=$(tail -n +2 "$MERGED" 2>/dev/null | wc -l)"
echo "NEOAPRED_HPC_FULL_DONE"
