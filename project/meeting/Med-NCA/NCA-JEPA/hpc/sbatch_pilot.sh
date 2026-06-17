#!/bin/bash
# NCA-JEPA pilot 单臂训练。提交（A0 baseline）：
#   sbatch --export=ALL,ARM=a0,SEED=42 --job-name=ncaj_a0_s42 hpc/sbatch_pilot.sh
# A1/A2 多 seed：ARM=a1|a2，SEED=42|123|2024（每 seed 一个 job，qos 上限 4 卡可并行）
# trade-off S 扫描：ARM=a2_s4|a2_s8|a2|a2_s32（a2=S16），各训一 ckpt → eval_anytime 出 §9.1 主图
#SBATCH --account=shuihuawang
#SBATCH --partition=gpu4090
#SBATCH --qos=4gpus
#SBATCH --gres=gpu:rtx4090:1
#SBATCH --cpus-per-task=8
#SBATCH --time=08:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/nca-jepa/logs/%x_%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/nca-jepa/logs/%x_%j.err

ROOT=/gpfs/work/bio/jiayu2403/nca-jepa
PY=/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/python
export EXP_LOG_ROOT=$ROOT/logs
# 单节点多 job 并发时唯一 MASTER_PORT，避免固定 40112 抢端口致 DDP init 失败
export MASTER_PORT=$(( 20000 + (SLURM_JOB_ID % 20000) ))
ARM=${ARM:-a0}
SEED=${SEED:-42}

# ARM -> config 文件名映射
case "$ARM" in
  a0) CFG=configs/a0_vit_vits_nih10k.yaml ;;
  a0plus) CFG=configs/a0plus_earlyexit_vit_vits_nih10k.yaml ;;
  a1) CFG=configs/a1_vanilla_nca_vits_nih10k.yaml ;;
  a2) CFG=configs/a2_scp_nca_vits_nih10k.yaml ;;        # = S16（默认主臂）
  a2_s4)  CFG=configs/a2_scp_nca_vits_nih10k_S4.yaml ;;   # trade-off 扫描点
  a2_s8)  CFG=configs/a2_scp_nca_vits_nih10k_S8.yaml ;;
  a2_s32) CFG=configs/a2_scp_nca_vits_nih10k_S32.yaml ;;
  # --- 路线 B：等容量遗忘探针 ---
  b_smallvit)     CFG=configs/b_smallvit_pred_vits_nih10k.yaml ;;    # 等参小 ViT 预训练（NIH ep50）
  b_cont_nca)     CFG=configs/b_continual_nca.yaml ;;                # NCA A2 域 A→B 续训（S16）
  b_cont_smallvit) CFG=configs/b_continual_smallvit.yaml ;;          # 小 ViT 域 A→B 续训（等容量对照）
  b_cont_a0plus)  CFG=configs/b_continual_a0plus.yaml ;;             # A0+ 域 A→B 续训（大容量参照）
  # --- 路线 C：SP² 平面 S 扫描续训（补 S4/S8/S32 的 RF，配已有 L_f 回归）---
  b_cont_nca_s4)  CFG=configs/b_continual_nca_S4.yaml ;;             # S4  续训（L_f=1.6103）
  b_cont_nca_s8)  CFG=configs/b_continual_nca_S8.yaml ;;             # S8  续训（L_f=1.4362）
  b_cont_nca_s32) CFG=configs/b_continual_nca_S32.yaml ;;            # S32 续训（L_f=1.0032）
  *)  echo "未知 ARM=$ARM"; exit 1 ;;
esac

cd $ROOT
echo "[pilot] host=$(hostname) ARM=$ARM SEED=$SEED CFG=$CFG start=$(date)"
$PY ijepa/main.py --fname $CFG --devices cuda:0 --seed $SEED
echo "[pilot] done=$(date)"
