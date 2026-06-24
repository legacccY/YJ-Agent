#!/bin/bash
#SBATCH --job-name=di_elispot
#SBATCH --account=shuihuawang
#SBATCH --partition=cpudebug
#SBATCH --qos=cpudebug
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=01:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/quantimmu/elispot_run/di_%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/quantimmu/elispot_run/di_%j.err
module load miniconda3/22.11.1
source activate /gpfs/work/bio/jiayu2403/quantimmu/envs/deepimmuno
cd /gpfs/work/bio/jiayu2403/quantimmu/tools_repos/DeepImmuno
echo "DI start $(date) node=$SLURMD_NODENAME"
python deepimmuno-cnn.py --mode multiple --intdir /gpfs/work/bio/jiayu2403/quantimmu/elispot_run/deepimmuno_input.csv --outdir /gpfs/work/bio/jiayu2403/quantimmu/elispot_run/di_out
echo "DI exit=$? end $(date)"
