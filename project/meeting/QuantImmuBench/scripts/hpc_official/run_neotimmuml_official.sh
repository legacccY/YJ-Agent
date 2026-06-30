#!/usr/bin/env bash
# =============================================================================
# run_neotimmuml_official.sh — NeoTImmuML 忠实复现补跑（QuantImmuBench Phase0）
# =============================================================================
# 工具: NeoTImmuML (Front. Immunol. 2025, DOI 10.3389/fimmu.2025.1681396)
#       repo https://github.com/01SYan19/NeoTImmuML
#
# ★ 本工具特点（已核 HPC ipynb + 论文 + researcher 实测）：
#   1) HLA-agnostic：模型输入=纯肽段 78 个 R-Peptides 物化特征，无 HLA（按肽打分→广播回 bb）。
#   2) 无官方预训练权重 + 无公开训练 CSV：repo 只有 ipynb+README+demo.csv，notebook 现场
#      训练 RF/LGBM/XGB(cell17)+加权 4:8:9 阈值0.5(cell20) 后 joblib.dump（权重/训练CSV 未公开）。
#   3) demo.csv 的 aaComp_1/cruciani_1 两列损坏不可复刻 → 用论文语义口径(NonPolar Mole%/PP1)，
#      训练+推理同口径自洽（见 calc_78_features.R 尾注）。
#
# ★ 忠实复现训练集（用户拍板「还原工具真实能力」）：
#   论文构集口径 = 真实带标正样本 + 把丰富负样本【平衡到正样本数】（论文自己的做法，非弱化）。
#   用 TumorAgDB2.0 原始带标数据重建 → build_balanced_trainset.py 得 5147 正 : 5147 负 = 10294，
#   几乎等于论文 5156:5156=10312（差=5 个标签冲突肽 + 微小 dedup）。=> 忠实复现，非 bit-exact
#   （论文精确 CSV/权重需邮件作者 13401930670@163.com）。
#
# ★ 本机跑（HPC 无 R/Rscript，R Peptides 2.4.6 在 E:/R-4.3.3；NeoTImmuML 无 GPU 需求）。
#   数据下载 + build + extract + predict + parse 为纯 Python（可任意跑）；
#   R 算特征 + train_predict 训练由主线串行跑（agent 不擅自跑 R/训练）。
# =============================================================================
set -euo pipefail

PROJ="${PROJ:-D:/YJ-Agent/project/meeting/QuantImmuBench}"
RSCRIPT="${RSCRIPT:-E:/R-4.3.3/bin/Rscript.exe}"
PYTHON="${PYTHON:-python}"
NT="$PROJ/scripts/neotimmuml"
BACKBONE="${BACKBONE:-$PROJ/scripts/out_official/master_backbone_official.csv}"
OUTDIR="${OUTDIR:-$PROJ/scripts/out_official}"
MODELDIR="${MODELDIR:-$NT/models_official}"        # 新目录，不覆盖旧(失真)models/

TRAINCSV="$NT/train_data/trainset_balanced.csv"
TRAINFEAT="$NT/train_data/trainset_features_bal.csv"
PEPS="$OUTDIR/neotimmuml_peptides.txt"
INFERFEAT="$OUTDIR/neotimmuml_features_official.csv"
SCORES="$OUTDIR/neotimmuml_scores_official.csv"

mkdir -p "$OUTDIR" "$MODELDIR"
cd "$PROJ"

# ---- [纯Python, 可跑] 0. 下载 TumorAgDB2.0 带标数据(若未下) ----
# python <scratchpad>/dl_tumoragdb.py   # 已下到 $NT/train_data/tumoragdb/

# ---- [纯Python, 可跑] 1. 重建平衡训练集 (5147:5147) ----
echo "[1/6] build balanced trainset (TumorAgDB2.0 真实带标, 论文平衡口径)"
"$PYTHON" "$NT/build_balanced_trainset.py" --output "$TRAINCSV"

# ---- [R, 主线串行跑] 2. 训练集 78 物化特征 ----
echo "[2/6] R Peptides 2.4.6 算训练集 78 特征 (aaComp_1=NonPolar/cruciani_1=PP1)"
"$RSCRIPT" "$NT/calc_78_features.R" --input "$TRAINCSV" --output "$TRAINFEAT"

# ---- [训练, 主线串行跑] 3. 论文超参重训 + held-out AUC 证明模型有效 ----
echo "[3/6] 训练 RF/LGBM/XGB (论文超参) + held-out(0.2) 报融合 AUC, 证明非全判负"
"$PYTHON" "$NT/train_predict.py" train \
    --feature_csv "$TRAINFEAT" --label_csv "$TRAINCSV" \
    --model_dir "$MODELDIR" --test_size 0.2

# ---- [纯Python, 可跑] 4. 从 backbone 抽 distinct 肽 ----
echo "[4/6] 抽 backbone distinct 肽 (MT+WT, 8-13mer)"
"$PYTHON" "$NT/extract_peptides.py" --backbone "$BACKBONE" --output "$PEPS" --min_len 8 --max_len 13

# ---- [R, 主线串行跑] 5. 推理肽 78 特征 (同口径) ----
echo "[5/6] R 算推理肽 78 特征 (同 aaComp_1=NonPolar/cruciani_1=PP1 口径)"
"$RSCRIPT" "$NT/calc_78_features.R" --input "$PEPS" --output "$INFERFEAT"

# ---- [纯Python, 可跑] 6. 加权融合预测 → 肽级分 ----
echo "[6/6] 加载 models_official 预测 (RF:LGB:XGB=4:8:9, 阈值0.5)"
"$PYTHON" "$NT/train_predict.py" predict \
    --feature_csv "$INFERFEAT" --model_dir "$MODELDIR" --output "$SCORES"

echo "[NEXT] parse 回贴 backbone (纯Python, 可跑):"
echo "  python scripts/hpc_official/parse_neotimmuml_official.py \\"
echo "    --scores $SCORES --backbone $BACKBONE --out-dir $OUTDIR"
echo "[DONE] run_neotimmuml_official.sh"
