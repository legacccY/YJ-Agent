#!/bin/bash
# run_prime_hpc.sh — Phase B PRIME 重推理 P101/P102（订正 HLA）HPC 驱动。
# 激活 prime env → 调 run_prime_hpc.py（prep+run+parse 一体，护栏内置）。
# 既可登录/计算节点直跑（bash run_prime_hpc.sh [--smoke N]），也可 sbatch 提交
# （下方 #SBATCH 头已备；sbatch 时第一参数透传给 python）。
#
# 红线：只读 $BASE/phaseB/backbone_101102.csv，PRIME 方向照原（Score 越高越免疫原）。
#
#SBATCH --job-name=prime_101102
#SBATCH --partition=gpu4090
#SBATCH --qos=4gpus
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --time=08:00:00
#SBATCH --output=%x_%j.log
set -euo pipefail

BASE=${QIB_BASE:-/gpfs/work/bio/jiayu2403/quantimmu}
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── 激活 prime env（本项目 HPC 惯用法：module load 系统 miniconda + source activate 全路径 env）──
source /etc/profile.d/modules.sh 2>/dev/null || true
module load miniconda3/22.11.1-gcc-8.5.0-l4fo6ta
source activate "$BASE/envs/prime"

echo "[hpc] python = $(which python)"
echo "[hpc] base   = $BASE"

# 透传 --smoke 等参数；run_prime_hpc.py 内部 per-allele 子进程会再次激活同 env
# （bash -lc 登录子 shell 可能重置 conda，belt+suspenders）。
python "$HERE/run_prime_hpc.py" "$@"
