#!/bin/bash
# =============================================================================
# hpc_neoapred.sh — NeoaPred 在 XJTLU HPC 经 singularity 跑（build/smoke/full）
# 服务 quantimmu-bench §Tier-3 lever=NeoaPred 全量（本地 ~60h 不可行→上 HPC）
#
# 用法（在 HPC 上跑）：
#   bash hpc_neoapred.sh build              # 从 docker-archive build neoapred.sif
#   bash hpc_neoapred.sh smoke              # 5 肽烟测，验 singularity + /var/software 访问
#   bash hpc_neoapred.sh chunk <in.csv> <outdir> <omp>   # 单块（sbatch 内并行调用）
#
# 关键（实证 docker 镜像 env）：所有依赖二进制在 /var/software（非 /root）→
#   singularity 非 root 可读，绕开 pTuneos 的 /root 访问坑。env vars 显式 export
#   （/root/.bashrc 里的 export 不会自动加载，因 HOME 非 /root）。
# =============================================================================
set -uo pipefail

WORK=/gpfs/work/bio/jiayu2403/quantimmu/neoapred_hpc
SIF=${WORK}/neoapred.sif
ARCHIVE=/gpfs/work/bio/jiayu2403/quantimmu/neoapred_1.0.0.tar.gz
IMG_ENV='
source /var/software/miniconda3/etc/profile.d/conda.sh
conda activate neoa
export MSMS_BIN=/var/software/tools/msms
export PDB2XYZRN=/var/software/tools/pdb_to_xyzrn
export PDB2PQR_BIN=/var/software/miniconda3/envs/neoa/bin/pdb2pqr
export APBS_BIN=/var/software/APBS-3.0.0.Linux/bin/apbs
export MULTIVALUE_BIN=/var/software/APBS-3.0.0.Linux/share/apbs/tools/bin/multivalue
export LD_LIBRARY_PATH=/var/software/miniconda3/lib:/var/software/APBS-3.0.0.Linux/lib:${LD_LIBRARY_PATH:-}
'

mkdir -p "$WORK"

cmd="${1:?need build|smoke|chunk}"

case "$cmd" in
  build)
    echo "[build] singularity build $SIF from $ARCHIVE"
    [ -f "$ARCHIVE" ] || { echo "[build] ERROR: 缺 $ARCHIVE（先上传）"; exit 1; }
    # 从 docker-archive 直接 build（不需 root，3.11 支持）
    singularity build "$SIF" "docker-archive://${ARCHIVE}"
    echo "[build] DONE: $(ls -lh $SIF 2>&1)"
    ;;

  smoke)
    echo "[smoke] 5 肽端到端"
    mkdir -p "$WORK/smoke"
    head -6 /gpfs/work/bio/jiayu2403/quantimmu/neoapred_hpc/neoapred_input.csv > "$WORK/smoke/in.csv" 2>/dev/null \
      || { echo "[smoke] ERROR 缺 neoapred_input.csv（先上传到 $WORK/）"; exit 1; }
    singularity exec -B "$WORK/smoke:/work" "$SIF" bash -c "${IMG_ENV}
      cd /work
      python /var/software/NeoaPred/run_NeoaPred.py --input_file /work/in.csv --output_dir /work/out --mode PepFore" 2>&1 | tail -15
    echo "[smoke] === Foreignness 输出 ==="
    cat "$WORK/smoke/out/Foreignness/MhcPep_foreignness.csv" 2>&1 | head || echo "[smoke] NO OUTPUT — 失败"
    ;;

  chunk)
    # 单块跑（sbatch 内被 N 路并行调用）。$2=chunk_csv $3=outdir $4=omp
    chunk_csv="$2"; outdir="$3"; omp="${4:-2}"
    mkdir -p "$outdir"
    singularity exec -B "$outdir:/work" "$SIF" bash -c "${IMG_ENV}
      export OMP_NUM_THREADS=$omp MKL_NUM_THREADS=$omp OPENMM_CPU_THREADS=$omp OPENBLAS_NUM_THREADS=$omp
      cp $chunk_csv /work/input.csv
      cd /work
      python /var/software/NeoaPred/run_NeoaPred.py --input_file /work/input.csv --output_dir /work/out --mode PepFore" \
      > "$outdir/run.log" 2>&1
    cp "$outdir/out/Foreignness/MhcPep_foreignness.csv" "$outdir/foreignness.csv" 2>/dev/null \
      || echo "[chunk] $(basename $outdir) NO_FOREIGNNESS"
    ;;

  *)
    echo "unknown cmd: $cmd"; exit 1;;
esac
