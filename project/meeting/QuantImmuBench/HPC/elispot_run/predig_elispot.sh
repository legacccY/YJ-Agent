#!/bin/bash
#SBATCH --job-name=predig_elispot
#SBATCH --account=shuihuawang
#SBATCH --partition=cpudebug
#SBATCH --qos=cpudebug
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=12:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/quantimmu/elispot_run/predig_%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/quantimmu/elispot_run/predig_%j.err
cd /gpfs/work/bio/jiayu2403/quantimmu/elispot_run/predig_run
echo "PredIG start $(date) node=$SLURMD_NODENAME"
singularity run --writable-tmpfs -B /gpfs/work/bio/jiayu2403/quantimmu/elispot_run/predig_run:/work /gpfs/work/bio/jiayu2403/quantimmu/sif/predig.sif /work/input.csv -o /work/predig_out.csv --modelXG neoant --type recombinant
echo "PredIG exit=$? end $(date)"
