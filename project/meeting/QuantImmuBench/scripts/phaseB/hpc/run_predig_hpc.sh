#!/bin/bash
# run_predig_hpc.sh — Phase B PredIG 重推理 P101/P102（订正 HLA）HPC 驱动。
# 三步一体：prep_predig_hpc.py（建 recombinant 输入 + 切分块）→ 逐块 singularity 跑
# predig.sif → 各块 out 按 K 序拼回 out.csv → parse_predig_hpc.py（位置 join 回贴 bb_idx）。
# 分块原因：容器 run.py 限单次 input CSV < 5000 行，全量 input.csv ~8036 行须切（每块 ≤4000）。
# 既可登录/计算节点直跑（bash run_predig_hpc.sh [--smoke N]），也可 sbatch 提交
# （下方 #SBATCH 头已备；第一参数 --smoke N 透传给两个 py）。
#
# 红线：只读 $BASE/phaseB/backbone_101102.csv，PredIG 方向照原（分越高越免疫原，无翻转）。
#       口径与原 86 肽严格一致（recombinant + neoant + 8-14mer，源 = run_predig_101102.py）。
#
# 【主线在 HPC 上跑法（ssh 上去执行，本窗不跑）】
#   1) 把以下 3 个文件上传到同一 HPC 目录（如 $BASE/phaseB/predig_hpc/）：
#        run_predig_hpc.sh / prep_predig_hpc.py / parse_predig_hpc.py
#   2) 确认 backbone 已在 $BASE/phaseB/backbone_101102.csv，sif 已在 $BASE/sif/predig.sif
#   3) ssh 后烟测: bash $BASE/phaseB/predig_hpc/run_predig_hpc.sh --smoke 4
#      全量:       bash $BASE/phaseB/predig_hpc/run_predig_hpc.sh
#      （PredIG 纯 CPU，无需 GPU；可 sbatch 包一层走 cpu 分区）
#
# 产出: $BASE/phaseB/PredIG_101102.csv   列 = bb_idx, MT_PredIG, WT_PredIG
#
#SBATCH --job-name=predig_101102
#SBATCH --partition=cpudebug
#SBATCH --qos=cpudebug
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=12:00:00
#SBATCH --output=%x_%j.log
set -euo pipefail

BASE=${QIB_BASE:-/gpfs/work/bio/jiayu2403/quantimmu}
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

BACKBONE="$BASE/phaseB/backbone_101102.csv"
WORKDIR="$BASE/phaseB/predig_work"          # singularity 挂载 → /work
SIF="$BASE/sif/predig.sif"
FINAL_OUT="$BASE/phaseB/PredIG_101102.csv"

# QIB_BASE 透传给 py（默认值同步），py 内 PREDIG_* 也可单独覆盖
export QIB_BASE="$BASE"

echo "[hpc] base     = $BASE"
echo "[hpc] backbone = $BACKBONE"
echo "[hpc] sif      = $SIF"
echo "[hpc] workdir  = $WORKDIR"
echo "[hpc] args     = $*"

# ── 1) prep：读 backbone 建 recombinant 输入 input.csv + 同序 meta.csv + 切 input_chunk*.csv ──
python "$HERE/prep_predig_hpc.py" --backbone "$BACKBONE" --workdir "$WORKDIR" "$@"

# ── 2) run：逐块 singularity 跑 PredIG（绕容器 <5000 行限制）──────────────────────
#    命令照 HPC 实测（HPC/elispot_run/predig_elispot.sh）：singularity run --writable-tmpfs。
#    入参与 docker 一致：<input.csv 位置参> -o <out.csv> --modelXG neoant --type recombinant。
#    清理上轮残留 out_chunk*.csv，逐块跑，跑完按 K 序拼回 out.csv（仅首块保表头）。
rm -f "$WORKDIR"/out_chunk*.csv "$WORKDIR/out.csv"
echo "[hpc] PredIG start $(date)"
for cf in $(ls -v "$WORKDIR"/input_chunk*.csv); do
  k="$(basename "$cf" .csv)"          # input_chunkK
  k="${k#input_}"                      # chunkK
  echo "[hpc]   块 $k → $(wc -l < "$cf") 行（含表头）"
  singularity run --writable-tmpfs \
    -B "$WORKDIR:/work" \
    "$SIF" \
    "/work/input_${k}.csv" -o "/work/out_${k}.csv" --modelXG neoant --type recombinant
done
echo "[hpc] PredIG exit=$? end $(date)"

# 各块 out 按自然序拼回 out.csv：awk 只保第一块表头，后续块跳首行（FNR==1）。
# print 强制补行尾换行，防某块输出末行缺 \n 导致拼接黏行。
awk 'FNR==1 { if (seen++) next } { print }' $(ls -v "$WORKDIR"/out_chunk*.csv) > "$WORKDIR/out.csv"
echo "[hpc] 拼接 $(ls -v "$WORKDIR"/out_chunk*.csv | wc -l) 块 → out.csv（$(($(wc -l < "$WORKDIR/out.csv") - 1)) 数据行）"

# ── 3) parse：位置 join 回贴 bb_idx → PredIG_101102.csv（--smoke 时不写正式 CSV）──
python "$HERE/parse_predig_hpc.py" \
  --backbone "$BACKBONE" --workdir "$WORKDIR" --out "$FINAL_OUT" "$@"

echo "[hpc] done. out = $FINAL_OUT"
