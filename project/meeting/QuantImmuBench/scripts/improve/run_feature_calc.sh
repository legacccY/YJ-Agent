#!/usr/bin/env bash
# ===========================================================================
# IMPROVE feature_calc (降级) → Predict (Simple) pipeline  v2
# 服务: quantimmu-bench，解锁 feature_calc 步骤
#
# 用法（WSL bash 下运行）:
#   # smoke 20行（先验证全链通）:
#   bash .../run_feature_calc.sh --smoke
#   # 全量 26790行:
#   bash .../run_feature_calc.sh
#
# 降级说明:
#   netMHCstabpan 已跳过（本地 WSL netMHCpan-2.8 后端乱码）
#   → Stability=NaN，Predict 脚本 fillna(col.mean()) 自动 impute
#   netMHCpan-4.1 binding/PRIME/SelfSim/理化特征 全部保留
#
# env 分工:
#   feature_calc (Step2) → conda env: improve   (py3.11, sklearn 1.9, numpy 2.x)
#   Predict      (Step3) → conda env: improve_new (numpy2.x pickle 兼容)
#
# 产出:
#   $OUTPUT_DIR/calculated_features.tsv      (所有行, Stability=NaN)
#   $OUTPUT_DIR/improve_simple_elispot.tsv   (含 mean_prediction_rf)
# ===========================================================================

set -euo pipefail

# ---------- 参数 ----------
SMOKE=0
if [[ "${1:-}" == "--smoke" ]]; then
    SMOKE=1
    echo "[SMOKE MODE] 取前20行验证全链"
fi

# ---------- 路径配置 ----------
IMPROVE_HOME="$HOME/quantimmu/tools_repos/IMPROVE_tool"
EXT_TOOLS="$HOME/quantimmu/ext_tools"
TOOL_REPOS="$HOME/quantimmu/tools_repos"
FULL_INPUT_TSV="/mnt/d/YJ-Agent/project/meeting/QuantImmuBench/scripts/out/improve_input.tsv"
OUTPUT_DIR="$HOME/quantimmu/elispot_run/improve_out"
DATASET_NAME="elispot"

FEATURE_CALC_PY="/mnt/d/YJ-Agent/project/meeting/QuantImmuBench/scripts/improve/feature_calc_local.py"
PREDICT_PY="$IMPROVE_HOME/predict_local.py"

# ---------- conda 初始化 ----------
# conda run -n <env> 在非交互 shell 里最可靠，不依赖 activate
# 但 Step1 的 python3 heredoc 用系统 python3（只需 pandas，improve env 已有）
# 非交互 shell 需先 source conda.sh 才有 conda 命令
source /root/miniconda3/etc/profile.d/conda.sh
_CONDA_RUN_IMPROVE="conda run --no-capture-output -n improve"
_CONDA_RUN_IMPROVE_NEW="conda run --no-capture-output -n improve_new"

# ---------- Step 0: 建 ProgramDir symlink 目录 ----------
# 降级版不需要 netMHCstabpan，但 mkdir 保留（clean=False 不会清它）
PROG_DIR="$HOME/quantimmu/improve_programs"
echo "[Step 0] 建 ProgramDir: $PROG_DIR"

mkdir -p "$PROG_DIR/netMHCpan-4.1"
mkdir -p "$PROG_DIR/netMHCstabpan-1.0"

# netMHCpan-4.1: 代码期待小写 netmhcpan，实际文件大写 netMHCpan → symlink 适配
if [ ! -e "$PROG_DIR/netMHCpan-4.1/netmhcpan" ]; then
    ln -sfn "$EXT_TOOLS/netMHCpan-4.1/netMHCpan" "$PROG_DIR/netMHCpan-4.1/netmhcpan"
    echo "  symlink: netMHCpan-4.1/netmhcpan -> ext_tools/netMHCpan-4.1/netMHCpan"
fi

# PRIME: 整目录 symlink（PRIME wrapper 靠 \$0 找 lib/PRIME.x）
if [ ! -e "$PROG_DIR/PRIME" ]; then
    ln -sfn "$TOOL_REPOS/PRIME" "$PROG_DIR/PRIME"
    echo "  symlink(dir): PRIME -> tools_repos/PRIME"
fi

# MixMHCpred: IMPROVE 代码硬编码 MixMHCpred-master/MixMHCpred
# 整目录 symlink（MixMHCpred wrapper 靠 executable_dir 找 code/ lib/）
if [ ! -e "$PROG_DIR/MixMHCpred-master" ]; then
    ln -sfn "$TOOL_REPOS/MixMHCpred" "$PROG_DIR/MixMHCpred-master"
    echo "  symlink(dir): MixMHCpred-master -> tools_repos/MixMHCpred"
fi

# ---------- Step 1: 准备输入 TSV（列名适配 + smoke 切片）----------
mkdir -p "$OUTPUT_DIR"
PREPPED_INPUT="$OUTPUT_DIR/improve_input_prepped.tsv"
echo "[Step 1] 转换列名 WT_peptide->Norm_peptide，smoke=$SMOKE"

${_CONDA_RUN_IMPROVE} python3 - <<PYEOF
import pandas as pd, os
inp = "$FULL_INPUT_TSV"
out = "$PREPPED_INPUT"
df = pd.read_csv(inp, sep='\t')
if 'WT_peptide' in df.columns:
    df = df.rename(columns={'WT_peptide': 'Norm_peptide'})
if 'Patient' not in df.columns:
    df['Patient'] = 'elispot'
if $SMOKE == 1:
    df = df.head(20)
    print(f"[smoke] 取前20行: {len(df)} rows")
os.makedirs(os.path.dirname(out), exist_ok=True)
df.to_csv(out, sep='\t', index=False)
print(f"Step1 done: {len(df)} rows -> {out}")
print(df[['Mut_peptide','Norm_peptide','HLA_allele']].head(3).to_string())
PYEOF

# ---------- Step 2: feature_calc（improve env, 跳过 netMHCstabpan）----------
PRED_DIR="$OUTPUT_DIR/predictions"
FEATURES_OUT="$OUTPUT_DIR/calculated_features.tsv"
mkdir -p "$PRED_DIR"
# 预建 IMPROVE 代码期待的子目录（multimerPatientTools clean=False 时不清，但会读）
mkdir -p "$PRED_DIR/netmhcpan41/mut" "$PRED_DIR/netmhcpan41/wt" \
         "$PRED_DIR/netmhcstabpan" "$PRED_DIR/PRIME"

echo "[Step 2] feature_calc_local.py (improve env, no-stab)"
cd "$IMPROVE_HOME"   # cwd=IMPROVE_HOME，kernelSim 用 data/matrices/blosum62.qij 相对路径

${_CONDA_RUN_IMPROVE} python3 "$FEATURE_CALC_PY" \
    --file "$PREPPED_INPUT" \
    --dataset "$DATASET_NAME" \
    --PredDir "$PRED_DIR" \
    --ProgramDir "$PROG_DIR" \
    --TmpDir "$PROG_DIR" \
    --outfile "$FEATURES_OUT"

echo "[Step 2] feature_calc done: $FEATURES_OUT"

# ---------- QC: 确认 RankEL 非 NaN ----------
echo "[QC] 检查 RankEL 覆盖率..."
${_CONDA_RUN_IMPROVE} python3 - <<PYEOF
import pandas as pd
df = pd.read_csv("$FEATURES_OUT", sep='\t')
total = len(df)
rankEL_ok = df['RankEL'].notna().sum()
stab_nan = df['Stability'].isna().sum()
print(f"[QC] 总行数={total}, RankEL非NaN={rankEL_ok} ({rankEL_ok/total*100:.1f}%), Stability=NaN: {stab_nan}")
if rankEL_ok == 0:
    raise RuntimeError("RankEL 全为 NaN，netMHCpan-4.1 调用失败！检查 PROG_DIR symlink")
PYEOF

# ---------- Step 3: Predict Simple（improve_new env）----------
PREDICT_OUT="$OUTPUT_DIR/improve_simple_elispot.tsv"
echo "[Step 3] predict_local.py (improve_new env, Simple)"

${_CONDA_RUN_IMPROVE_NEW} python3 "$PREDICT_PY" \
    --file "$FEATURES_OUT" \
    --model Simple \
    --outfile "$PREDICT_OUT"

echo "[Step 3] Predict done: $PREDICT_OUT"

# ---------- 最终 QC ----------
echo ""
${_CONDA_RUN_IMPROVE} python3 - <<PYEOF
import pandas as pd
df = pd.read_csv("$PREDICT_OUT", sep='\t')
total = len(df)
pred_ok = df['mean_prediction_rf'].notna().sum()
print(f"[FINAL QC] 输出行数={total}, mean_prediction_rf非NaN={pred_ok} ({pred_ok/total*100:.1f}%)")
print(df[['Mut_peptide','HLA_allele','mean_prediction_rf']].head(5).to_string())
PYEOF

echo ""
echo "===== DONE ====="
echo "特征文件: $FEATURES_OUT"
echo "预测结果: $PREDICT_OUT"
echo "关键列: mean_prediction_rf (0-1, Simple 模型免疫原性评分)"
echo "缺失列: Stability/Foreigness/NetMHCExp/Expression (均 NaN → imputed by col.mean)"
