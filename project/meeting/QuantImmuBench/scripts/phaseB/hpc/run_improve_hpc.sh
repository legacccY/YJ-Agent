#!/usr/bin/env bash
# ===========================================================================
# run_improve_hpc.sh — Phase B：在 HPC 上对 101/102 backbone 子肽重推理 IMPROVE
#   口径与原 86 肽严格一致（降级版：netMHCpan-4.1 + PRIME/MixMHCpred + SelfSim，
#   跳 netMHCstabpan → Stability=NaN，Foreigness/NetMHCExp/Expression=NaN，
#   Predict 用 col.mean() impute；模型 = Simple）。
#   源口径见 scripts/improve/run_feature_calc.sh + feature_calc_local.py（WSL 原跑）。
#   本脚本是其 HPC 移植：仅换路径/conda 初始化/单 env，方法学零改动。
#
# 创建: 2026-06-27（quantimmu Phase B / lever=IMPROVE）
#
# 【主线在 HPC 上跑法（ssh 上去执行，本窗不跑）】
#   1) 把以下 4 个文件上传到同一 HPC 目录（如 $ROOT/phaseB/improve_hpc/）：
#        run_improve_hpc.sh
#        prep_improve_hpc.py
#        parse_improve_hpc.py
#        feature_calc_local.py      <- 从 scripts/improve/ 复制（口径核心，单一真源）
#   2) 确认 backbone 已在 $ROOT/phaseB/backbone_101102.csv
#   3) ssh 后: bash $ROOT/phaseB/improve_hpc/run_improve_hpc.sh
#      （或 sbatch 包一层；纯 CPU/RF，无需 GPU）
#
# 产出:
#   $ROOT/phaseB/IMPROVE_101102.csv   列 = bb_idx, MT_IMPROVE_mean_prediction_rf
# ===========================================================================
set -euo pipefail

# ---------- 路径配置（HPC 绝对路径，与其他 deploy 脚本一致）----------
ROOT=/gpfs/work/bio/jiayu2403/quantimmu
# 双 env 拆分（照原 WSL 口径，feature_calc 与 Predict 各用各 env）：
#   FEAT_PY → imp_feat (pandas 1.3.5 + numpy 1.21 + sklearn 1.0 + biopython + peptides)
#             —— 跑老 IMPROVE feature 代码不崩（HPC improve 是 pandas2.x 会崩）
#   PRED_PY → improve  (numpy 2.x) —— Predict 的 pkl 是 numpy2.x retrained，必须用它
FEAT_PY=$ROOT/envs/imp_feat/bin/python
PRED_PY=$ROOT/envs/improve/bin/python
IMPROVE_HOME=$ROOT/tools_repos/IMPROVE_tool
EXT_TOOLS=$ROOT/ext_tools
TOOL_REPOS=$ROOT/tools_repos

BACKBONE=$ROOT/phaseB/backbone_101102.csv
BASE=$ROOT/phaseB
WORK=$BASE/improve_work
FINAL_OUT=$BASE/IMPROVE_101102.csv

# 本脚本所在目录 = 上传 bundle 目录（prep/parse/feature_calc_local 都在这）
STAGE="$(cd "$(dirname "$0")" && pwd)"
PREP_PY="$STAGE/prep_improve_hpc.py"
PARSE_PY="$STAGE/parse_improve_hpc.py"
FEATURE_CALC_PY="$STAGE/feature_calc_local.py"

DATASET_NAME=elispot

mkdir -p "$WORK"

# ---------- conda 初始化（HPC，绝对 env python，不 activate 单一 env）----------
# 两步用不同 env，故不全局 activate，直接用各自绝对 python 路径（env 自包含可用）。
source /etc/profile.d/modules.sh 2>/dev/null || true
module load miniconda3/22.11.1-gcc-8.5.0-l4fo6ta 2>/dev/null || true
# 自校验两 env import（imp_feat 跑 feature，improve 跑 Predict pkl）
"$FEAT_PY" -c "import numpy,sklearn,pandas,Bio;print('FEAT_OK pandas',pandas.__version__,'np',numpy.__version__)"
"$PRED_PY" -c "import numpy,sklearn;print('PRED_OK np',numpy.__version__,'sk',sklearn.__version__)"

# feature_calc_local.py 的 src 路径走 env 覆盖（HPC $HOME != work 目录）
export IMPROVE_SRC="$IMPROVE_HOME/bin/src"

# ---------- Step 0a: 确认模型已解压 ----------
cd "$IMPROVE_HOME"
if [ ! -e "models/Simple" ] || [ "$(ls models/Simple 2>/dev/null | grep -c rf)" -eq 0 ]; then
    echo "=== unzip models ==="
    unzip -o -q models.zip && echo UNZIP_OK
fi
echo "Simple rf 数: $(ls models/Simple/ 2>/dev/null | grep -c rf)"

# ---------- Step 0b: 生成 predict_local.py（base_dir 指向 HPC repo）----------
PREDICT_PY="$IMPROVE_HOME/predict_local.py"
if [ ! -f "$PREDICT_PY" ]; then
    sed "s|^base_dir = .*|base_dir = \"$IMPROVE_HOME\"|" \
        Predict_immunogenicity_CLEAN_retrain.py > "$PREDICT_PY"
    echo "  生成 predict_local.py（base_dir -> $IMPROVE_HOME）"
fi

# ---------- Step 0c: ProgramDir symlink（与 run_feature_calc.sh Step0 一致）----------
PROG_DIR=$ROOT/improve_programs
mkdir -p "$PROG_DIR/netMHCpan-4.1"
# netMHCpan-4.1: 代码期待小写 netmhcpan
if [ ! -e "$PROG_DIR/netMHCpan-4.1/netmhcpan" ]; then
    ln -sfn "$EXT_TOOLS/netMHCpan-4.1/netMHCpan" "$PROG_DIR/netMHCpan-4.1/netmhcpan"
fi
# PRIME: 整目录 symlink（PRIME wrapper 靠 $0 找 lib/PRIME.x）
[ -e "$PROG_DIR/PRIME" ] || ln -sfn "$TOOL_REPOS/PRIME" "$PROG_DIR/PRIME"
# MixMHCpred: IMPROVE 硬编码 MixMHCpred-master/MixMHCpred
[ -e "$PROG_DIR/MixMHCpred-master" ] || ln -sfn "$TOOL_REPOS/MixMHCpred" "$PROG_DIR/MixMHCpred-master"
echo "[Step 0] ProgramDir 就绪: $PROG_DIR"

# ---------- Step 1: prep（backbone -> IMPROVE 输入 + bb_idx 映射）----------
INPUT_TSV=$WORK/improve_input.tsv
MAP_CSV=$WORK/improve_input_map.csv
echo "[Step 1] prep"
"$FEAT_PY" "$PREP_PY" --backbone "$BACKBONE" --input-tsv "$INPUT_TSV" --map-csv "$MAP_CSV"

# prep 写 WT_peptide 列；feature_calc_local 内部会 rename WT_peptide->Norm_peptide。
# 但原 run_feature_calc.sh 在 Step1 先 rename 并补 Patient 列，这里同样做以严格对齐口径。
PREPPED=$WORK/improve_input_prepped.tsv
"$FEAT_PY" - <<PYEOF
import pandas as pd
df = pd.read_csv("$INPUT_TSV", sep="\t")
if "WT_peptide" in df.columns:
    df = df.rename(columns={"WT_peptide": "Norm_peptide"})
if "Patient" not in df.columns:
    df["Patient"] = "elispot"
df.to_csv("$PREPPED", sep="\t", index=False)
print("[Step1] prepped:", len(df), "rows ->", "$PREPPED")
PYEOF

# ---------- Step 2: feature_calc（降级版，netMHCpan-4.1 + PRIME，跳 stabpan）----------
PRED_DIR=$WORK/predictions
FEATURES_OUT=$WORK/calculated_features.tsv
mkdir -p "$PRED_DIR/netmhcpan41/mut" "$PRED_DIR/netmhcpan41/wt" \
         "$PRED_DIR/netmhcstabpan" "$PRED_DIR/PRIME"

echo "[Step 2] feature_calc_local.py（no-stab 降级，与原 86 肽同口径）"
cd "$IMPROVE_HOME"   # cwd=IMPROVE_HOME，kernelSim 用 data/matrices/blosum62.qij 相对路径
"$FEAT_PY" "$FEATURE_CALC_PY" \
    --file "$PREPPED" \
    --dataset "$DATASET_NAME" \
    --PredDir "$PRED_DIR" \
    --ProgramDir "$PROG_DIR" \
    --TmpDir "$PROG_DIR" \
    --outfile "$FEATURES_OUT"

# QC: RankEL 非 NaN（netMHCpan-4.1 调用成功）
"$FEAT_PY" - <<PYEOF
import pandas as pd
df = pd.read_csv("$FEATURES_OUT", sep="\t")
ok = df["RankEL"].notna().sum()
print(f"[QC] feature 行={len(df)}, RankEL 非NaN={ok}, Stability=NaN(预期降级)")
if ok == 0:
    raise SystemExit("RankEL 全 NaN → netMHCpan-4.1 调用失败，检查 PROG_DIR symlink")
PYEOF

# ---------- Step 3: Predict Simple ----------
PREDICT_OUT=$WORK/improve_simple_101102.tsv
echo "[Step 3] Predict Simple"
"$PRED_PY" "$PREDICT_PY" \
    --file "$FEATURES_OUT" \
    --model Simple \
    --outfile "$PREDICT_OUT"

"$FEAT_PY" - <<PYEOF
import pandas as pd
df = pd.read_csv("$PREDICT_OUT", sep="\t")
ok = df["mean_prediction_rf"].notna().sum()
print(f"[QC] Predict 行={len(df)}, mean_prediction_rf 非NaN={ok}")
print(df[["Mut_peptide","HLA_allele","mean_prediction_rf"]].head(3).to_string())
PYEOF

# ---------- Step 4: parse（-> bb_idx 对齐合表列）----------
echo "[Step 4] parse -> $FINAL_OUT"
"$FEAT_PY" "$PARSE_PY" --pred "$PREDICT_OUT" --map-csv "$MAP_CSV" --out "$FINAL_OUT"

echo ""
echo "===== IMPROVE 101/102 DONE ====="
echo "特征: $FEATURES_OUT"
echo "预测: $PREDICT_OUT"
echo "合表列: $FINAL_OUT  (bb_idx, MT_IMPROVE_mean_prediction_rf)"
echo "口径: netMHCpan-4.1 + PRIME/MixMHCpred + SelfSim，跳 stabpan，Simple 模型（与原 86 肽一致）"
