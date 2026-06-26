#!/bin/bash
# =============================================================================
# run_neoapred_full_parallel.sh — NeoaPred 全量并行跑（本地 WSL2 docker）
# 服务 quantimmu-bench §Tier-3 lever=部署 NeoaPred 全量
#
# 背景：NeoaPred PepFore 每行重做结构弛豫（无缓存，~20s/结构×2/肽），
#   5692 unique 9mer 串行 ~100h → 切 N 块并行 docker 容器跑。
#   每容器限 OPENMM_CPU_THREADS 防过订阅（本机 22 核）。
#
# 用法：bash run_neoapred_full_parallel.sh <input_csv> <work_dir> [N_CHUNKS] [THREADS_PER]
#   input_csv    : neoapred_input.csv（ID,Allele,WT,Mut 全量 5692 行）
#   work_dir     : 工作目录（存分块+各容器输出+合并结果），WSL 本地路径
#   N_CHUNKS     : 并行块数，默认 8
#   THREADS_PER  : 每容器 OPENMM_CPU_THREADS，默认 2（8×2=16<22）
#
# 产出：<work_dir>/MhcPep_foreignness_full.csv（合并全部块，列 ID,Allele,WT,Mut,Foreignness_Score）
#       再用 merge_neoapred.py 回贴 bb_idx。
# =============================================================================
set -euo pipefail

INPUT="${1:?need input_csv}"
WORK="${2:?need work_dir}"
N="${3:-8}"
THREADS="${4:-2}"
IMG="panda1103/neoapred:1.0.0"

mkdir -p "$WORK/chunks" "$WORK/outs"
echo "[full] input=$INPUT work=$WORK N=$N threads=$THREADS"

# --- 切块（保留表头，按数据行平均分 N 块）---
HEADER=$(head -1 "$INPUT")
tail -n +2 "$INPUT" > "$WORK/_data.csv"
TOTAL=$(wc -l < "$WORK/_data.csv")
PER=$(( (TOTAL + N - 1) / N ))
echo "[full] total_rows=$TOTAL per_chunk=$PER"
split -l "$PER" -d "$WORK/_data.csv" "$WORK/chunks/part_"
for f in "$WORK"/chunks/part_*; do
  ( echo "$HEADER"; cat "$f" ) > "${f}.csv"
  rm -f "$f"
done
ls "$WORK"/chunks/*.csv

# --- 单块跑函数 ---
run_chunk() {
  local chunk_csv="$1"
  local tag
  tag=$(basename "$chunk_csv" .csv)
  local out="$WORK/outs/$tag"
  mkdir -p "$out"
  local cid
  # OpenMM 弛豫吃 OMP 线程，必须同时限 OMP_NUM_THREADS/MKL_NUM_THREADS/OPENMM_CPU_THREADS
  # 否则每容器开满核 → N 容器过订阅 thrash（实证 8 容器 load 60，弛豫 ~3/min）
  cid=$(docker run -d -e OMP_NUM_THREADS="$THREADS" -e MKL_NUM_THREADS="$THREADS" \
        -e OPENMM_CPU_THREADS="$THREADS" -e OPENBLAS_NUM_THREADS="$THREADS" "$IMG" sleep infinity)
  echo "[$tag] cid=$cid"
  docker cp "$chunk_csv" "$cid:/input.csv"
  docker exec "$cid" bash -c \
    "source ~/.bash_profile 2>/dev/null; source ~/.bashrc 2>/dev/null; conda activate neoa; cd /; export OMP_NUM_THREADS=$THREADS MKL_NUM_THREADS=$THREADS OPENMM_CPU_THREADS=$THREADS OPENBLAS_NUM_THREADS=$THREADS; python /var/software/NeoaPred/run_NeoaPred.py --input_file /input.csv --output_dir /test_out --mode PepFore" \
    > "$out/run.log" 2>&1 || echo "[$tag] EXEC_FAIL (see $out/run.log)"
  docker cp "$cid:/test_out/Foreignness/MhcPep_foreignness.csv" "$out/foreignness.csv" 2>/dev/null \
    || echo "[$tag] NO_FOREIGNNESS_OUT"
  docker stop "$cid" >/dev/null 2>&1 || true
  docker rm "$cid" >/dev/null 2>&1 || true
  echo "[$tag] DONE rows=$(wc -l < "$out/foreignness.csv" 2>/dev/null || echo 0)"
}

# --- 某块是否完成（foreignness 行数 == 该块数据行数）---
chunk_complete() {
  local chunk_csv="$1"; local tag; tag=$(basename "$chunk_csv" .csv)
  local fn="$WORK/outs/$tag/foreignness.csv"
  [ -s "$fn" ] || return 1
  local exp; exp=$(( $(wc -l < "$chunk_csv") - 1 ))
  local got; got=$(( $(wc -l < "$fn") - 1 ))
  [ "$got" -ge "$exp" ]
}

# --- 并行启动所有块 ---
echo "[full] launching $N parallel containers..."
for chunk_csv in "$WORK"/chunks/*.csv; do
  run_chunk "$chunk_csv" &
done
wait
echo "[full] first pass done"

# --- 重试未完成的块（OOM/straggler）：降并发 max 2，最多 RETRY 轮 ---
RETRY="${RETRY:-3}"
for attempt in $(seq 1 "$RETRY"); do
  pending=()
  for chunk_csv in "$WORK"/chunks/*.csv; do
    chunk_complete "$chunk_csv" || pending+=("$chunk_csv")
  done
  [ "${#pending[@]}" -eq 0 ] && { echo "[full] all chunks complete"; break; }
  echo "[full] retry attempt $attempt: ${#pending[@]} incomplete chunks (降并发 2)"
  i=0
  for chunk_csv in "${pending[@]}"; do
    run_chunk "$chunk_csv" &
    i=$((i+1)); [ $((i % 2)) -eq 0 ] && wait
  done
  wait
done

# --- 合并（取第一块表头 + 各块数据行）---
MERGED="$WORK/MhcPep_foreignness_full.csv"
first=1
for out in "$WORK"/outs/*/foreignness.csv; do
  [ -s "$out" ] || { echo "[merge] WARN empty $out"; continue; }
  if [ "$first" = 1 ]; then head -1 "$out" > "$MERGED"; first=0; fi
  tail -n +2 "$out" >> "$MERGED"
done
echo "[full] merged → $MERGED (rows=$(tail -n +2 "$MERGED" | wc -l))"
echo "NEOAPRED_FULL_DONE"
