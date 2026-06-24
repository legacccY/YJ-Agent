#!/bin/bash
#SBATCH --job-name=hf_buildenv
#SBATCH --account=shuihuawang
#SBATCH --partition=cpudebug
#SBATCH --qos=cpudebug
#SBATCH --cpus-per-task=4
#SBATCH --mem=24G
#SBATCH --time=01:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/hyperfid/logs/buildenv_%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/hyperfid/logs/buildenv_%j.err

# 单 env 构建（cpudebug 限 1h/4cpu/1job）。$1=braingb|hypergale，默认 braingb
ROOT=/gpfs/work/bio/jiayu2403/hyperfid
cd $ROOT
WHICH=${1:-braingb}
echo "===== buildenv $WHICH on $(hostname) at $(date) ====="
bash hpc_setup_${WHICH}.sh
echo "===== buildenv $WHICH DONE at $(date) ====="
