#!/bin/bash
# 路线 A/B 轨迹探针（纯推理，非训练；走 slurm 占 1 卡跑快）。提交：
#   sbatch --export=ALL,PROBE=conv    --job-name=ncaj_probe_conv    hpc/sbatch_probe.sh
#   sbatch --export=ALL,PROBE=genesis --job-name=ncaj_probe_genesis hpc/sbatch_probe.sh
# 主臂锁 trained_S=16（MAXSTEPS=16），不外推到 64（避训练分布外未定义动力学污染，planner 设计）。
# 外推敏感性臂（可选）：用 S32 ckpt + MAXSTEPS=32。
#SBATCH --account=shuihuawang
#SBATCH --partition=gpu4090
#SBATCH --qos=4gpus
#SBATCH --gres=gpu:rtx4090:1
#SBATCH --cpus-per-task=8
#SBATCH --time=01:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/nca-jepa/logs/%x_%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/nca-jepa/logs/%x_%j.err

ROOT=/gpfs/work/bio/jiayu2403/nca-jepa
PY=/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/python
cd $ROOT
PROBE=${PROBE:-conv}
N=${N:-200}
MAXSTEPS=${MAXSTEPS:-16}
COSTHR=${COSTHR:-0.01}
NIHSUB=${NIHSUB:-}              # NIH split（留空=用 config 的 pretrain_10k；有 held split 时传入避泄漏）
NIHARG=""; [ -n "$NIHSUB" ] && NIHARG="--nih-subset $NIHSUB"

echo "[probe] host=$(hostname) PROBE=$PROBE N=$N MAXSTEPS=$MAXSTEPS start=$(date)"
case "$PROBE" in
  conv)
    $PY eval/traj_probe_convergence.py \
      --config configs/a2_scp_nca_vits_nih10k.yaml \
      --ckpt logs/a2_scp_nca_vits_nih10k/jepa-ep50.pth.tar \
      --n $N --max-steps $MAXSTEPS --cos-thr $COSTHR \
      --vindr-root data/vindr_cxr --device cuda $NIHARG ;;
  genesis)
    $PY eval/traj_probe_genesis.py \
      --config configs/a2_scp_nca_vits_nih10k.yaml \
      --ckpt logs/a2_scp_nca_vits_nih10k/jepa-ep50.pth.tar \
      --n ${N:-100} --K $MAXSTEPS --device cuda $NIHARG ;;
  *) echo "unknown PROBE=$PROBE"; exit 1 ;;
esac
echo "[probe] done=$(date)"
