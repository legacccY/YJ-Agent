#!/bin/bash
# MedAD-FailMap Phase 0 — A0: BraTS2021 AE 训练 (PC-A 地基)
# 提交: sbatch code/submit_a0.sh  (在 /gpfs/work/bio/jiayu2403/medad-failmap/ 下)
# 复现零偏离: MedIAnomaly 官方超参 (epochs=250/bs=64/lr=1e-3/latent=16/L2)
#SBATCH --job-name=medad_a0_ae
#SBATCH --account=shuihuawang
#SBATCH --partition=gpu4090
#SBATCH --qos=4gpus
#SBATCH --gres=gpu:rtx4090:1
#SBATCH --cpus-per-task=8
#SBATCH --time=02:00:00
#SBATCH --output=/gpfs/work/bio/jiayu2403/medad-failmap/logs/a0_ae_%j.out
#SBATCH --error=/gpfs/work/bio/jiayu2403/medad-failmap/logs/a0_ae_%j.err

ROOT=/gpfs/work/bio/jiayu2403/medad-failmap
PY=/gpfs/work/bio/jiayu2403/.conda/envs/yjcu124py310/bin/python
cd $ROOT
echo "[A0] start=$(date) node=$(hostname)"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader

# ---- GPU: train ----
$PY code/train_recon_ae.py -d brats -m ae --data-root data --out-dir results -g 0 --num-workers 8
echo "[A0] train done=$(date)"
echo "===== anomaly score csv 头部 ====="
head -3 $ROOT/results/anomaly_scores_brats_ae.csv

# ---- CPU: PC-A stratify_eval (size/contrast 分桶 → stratify_size_ae.csv, stratify_interact_ae.csv) ----
echo "[A0] running stratify_eval..."
$PY code/stratify_eval.py \
    --score-csv      $ROOT/results/anomaly_scores_brats_ae.csv \
    --mask-dir       $ROOT/data/BraTS2021/test/annotation \
    --tumor-img-dir  $ROOT/data/BraTS2021/test/tumor \
    --out-dir        $ROOT/results \
    --model-tag      ae
echo "[A0] stratify_eval done=$(date)"

# ---- CPU: PC-C conspicuity_proxy tumor (无 mask 代理特征 → conspicuity_features_tumor.csv) ----
echo "[A0] running conspicuity_proxy (tumor)..."
$PY code/conspicuity_proxy.py \
    --img-dir   $ROOT/data/BraTS2021/test/tumor \
    --score-csv $ROOT/results/anomaly_scores_brats_ae.csv \
    --out-csv   $ROOT/results/conspicuity_features_tumor.csv
echo "[A0] conspicuity_proxy tumor done=$(date)"

# ---- CPU: PC-C conspicuity_proxy normal (C4 risk-coverage 需要 normal+tumor 混合集) ----
# LOG: test/normal = 828 张
echo "[A0] running conspicuity_proxy (normal)..."
$PY code/conspicuity_proxy.py \
    --img-dir   $ROOT/data/BraTS2021/test/normal \
    --score-csv $ROOT/results/anomaly_scores_brats_ae.csv \
    --out-csv   $ROOT/results/conspicuity_features_normal.csv
echo "[A0] conspicuity_proxy normal done=$(date)"

# ---- CPU: PC-C incremental_stats (C2/C3/C4 增量检验) ----
# C2/C3 用 tumor-only csv; C4 用 normal+tumor 混合集（AD AUROC 需两类）
echo "[A0] running incremental_stats..."
$PY code/incremental_stats.py \
    --conspicuity-csv        $ROOT/results/conspicuity_features_tumor.csv \
    --normal-conspicuity-csv $ROOT/results/conspicuity_features_normal.csv \
    --score-csv              $ROOT/results/anomaly_scores_brats_ae.csv \
    --stratify-csv           $ROOT/results/stratify_interact_ae.csv \
    --out-dir                $ROOT/results
echo "[A0] incremental_stats done=$(date)"

# ---- CPU: PC-A 显著性检验 T1/T2/T3 (F-A family Holm/FDR) ----
# 注: 依赖 stratify_eval.py 产出的 stratify_per_image_ae.csv
#     (含 filename/size_px/contrast，stratify_eval 已在上方先跑)
echo "[A0] running stratify_significance (F-A T1/T2/T3)..."
$PY code/stratify_significance.py \
    --score-csv              $ROOT/results/anomaly_scores_brats_ae.csv \
    --strat-per-image-csv    $ROOT/results/stratify_per_image_ae.csv \
    --out-csv                $ROOT/results/stratify_significance_FA.csv
echo "[A0] stratify_significance done=$(date)"

# ---- CPU: PC-B failure_boundary (B1/B2/B3/B4 失败边界) ----
echo "[A0] running failure_boundary..."
$PY code/failure_boundary.py \
    --brats-score-csv       $ROOT/results/anomaly_scores_brats_ae.csv \
    --brats-strat-csv       $ROOT/results/stratify_interact_ae.csv \
    --brats-conspicuity-csv $ROOT/results/conspicuity_features.csv \
    --out-dir               $ROOT/results
echo "[A0] failure_boundary done=$(date)"

echo "[A0] all done=$(date)"
