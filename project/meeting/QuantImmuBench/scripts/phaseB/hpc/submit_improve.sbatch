#!/bin/bash
# ===========================================================================
# submit_improve.sbatch — Phase B IMPROVE 101/102 重推理，提交到 CPU 计算节点
#   修 DTN 限流坑：feature_calc(netMHCpan-4.1+PRIME) 是 CPU 重活，不能在
#   DTN 登录节点 inline 跑（共享+限流→PRIME.x 拿不到 CPU 假卡），必须 sbatch
#   到 cpu8358 计算节点。
#   qos=cpudebug（jiayu2403 仅有 4gpus/cpudebug/gpudebug；cpudebug=唯一 CPU qos，
#   上限 cpu=4 / MaxWall 1h；15 肽 4018 子肽规模小，足够）。
#   创建: 2026-06-28（quantimmu Phase B / lever=IMPROVE）
# ===========================================================================
#SBATCH --job-name=imp101102
#SBATCH --partition=cpu8358
#SBATCH --qos=cpudebug
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/quantimmu/phaseB/improve_%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/quantimmu/phaseB/improve_%j.out

set -euo pipefail
echo "=== node: $(hostname) | start: $(date) ==="
bash /gpfs/work/bio/jiayu2403/quantimmu/phaseB/run_improve_hpc.sh
echo "=== end: $(date) ==="
