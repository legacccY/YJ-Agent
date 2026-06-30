#!/usr/bin/env bash
# ===========================================================================
# run_improve_official.sh — IMPROVE 官方端到端 (HPC, 主线一次跑)
# 服务: quantimmu-bench Phase0 官方数据工具补跑舰队 (lever=IMPROVE)
#
# 管线 (官方 IMPROVE + 档II, 用户拍板):
#   Step2  feature_calculations.py  (env=imp_feat, STAB=1)
#          → netMHCpan-4.1 (mut+wt) + netMHCstabpan-1.0 + PRIME/MixMHCpred + SelfSim + 理化
#          → 真算 ~18 特征 (含 Stability, 因 HPC 有 netMHCstabpan 二进制)
#   Step2a run_foreignness.R        (env=garnish_r)
#          → Foreigness **真算** (antigen.garnish foreignness_score db=human, 纯肽, Łuksza2017)
#   Step2b complete_features.py     (env=improve)
#          → 补 Patient(常量ID) + merge 真算Foreigness
#          → NetMHCExp/Expression 对纯肽 100% 缺 → 官方 predict 自带 mean-impute 的合法处理
#            (论文明示), 100%缺导致 batch-mean=NaN 故用官方参考文件列均值预填 (横幅披露)
#   Step3  predict_local.py --model Simple  (env=improve)
#          → mean_prediction_rf (0-1 免疫原性分)
#
# ⚠️ model=Simple: 唯一可行模型。TME_excluded 需 PrioScore(MuPeXI)+CelPrev(PyClone);
#    TME_included 还需 RNA(CYT/HLAexp/MCPmean)。纯肽输入全无 → 只能 Simple。
#
# 跑序 (HPC, 主线串行):
#   0) bash deploy_antigen_garnish.sh            # 先部署 antigen.garnish (建 garnish_r, 仅一次)
#   1) bash run_improve_official.sh              # 全量, STAB=1(真Stability)+FOREIGN=1(真Foreigness)
#      STAB=0 bash run_improve_official.sh       # stab 报错后备: 跳 netMHCstabpan, Stability 走参考均值
#      FOREIGN=0 bash run_improve_official.sh    # garnish 未就绪时: Foreigness 走参考均值 (非档II默认)
#      SMOKE=20 bash run_improve_official.sh     # 前20行验全链
#
# 复现零偏离: 官方 feature_calc + predict + antigen.garnish, 不私改超参/裁剪。
# 档II: Foreigness 真算; NetMHCExp/Expression 走论文认可的官方 mean-impute (参考均值 fallback, 披露)。
# ===========================================================================
set -euo pipefail

# ---------- 配置 ----------
BASE="/gpfs/work/bio/jiayu2403/quantimmu"
R="$BASE/tools_repos/IMPROVE_tool"
EXT="$BASE/ext_tools"
TOOLREPOS="$BASE/tools_repos"

INPUT="${INPUT:-$BASE/official_inputs/out_official/improve_input.tsv}"   # 1761 uniq (Mut/WT/HLA)
OUTDIR="${OUTDIR:-$BASE/improve_official_run}"
REF_FEATS="$R/data/calculated_features_test.tsv"   # 官方参考特征文件 (补不可得特征均值的来源)
DATASET="improve_official"

STAB="${STAB:-1}"                 # 1=官方含netMHCstabpan(真Stability); 0=降级跳stab
FOREIGN="${FOREIGN:-1}"           # 1=antigen.garnish 真算 Foreigness(档II默认); 0=跳过走参考均值
SMOKE="${SMOKE:-0}"               # >0 取前N行
# antigen.garnish (Foreigness) — 由 deploy_antigen_garnish.sh 产出
GARNISH_ENV="${GARNISH_ENV:-$BASE/envs/garnish_r}"
AG_DATA_DIR="${AG_DATA_DIR:-$BASE/ext_tools/antigen.garnish}"

# 脚本自身所在目录 (complete_features.py / run_foreignness.R 同级)
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPLETE_PY="$SELF_DIR/complete_features.py"
FOREIGN_R="$SELF_DIR/run_foreignness.R"
# 降级特征脚本 (STAB=0 后备, 已存在于仓库)
LOCAL_FEAT_PY="${LOCAL_FEAT_PY:-$SELF_DIR/../improve/feature_calc_local.py}"
OFFICIAL_FEAT_PY="$R/bin/feature_calculations.py"
PREDICT_PY="$R/predict_local.py"

mkdir -p "$OUTDIR"
PREPPED="$OUTDIR/improve_input_prepped.tsv"
FEATS="$OUTDIR/calculated_features.tsv"
FOREIGN_OUT="$OUTDIR/foreignness.csv"
FEATS_COMPLETE="$OUTDIR/calculated_features_complete.tsv"
PRED_OUT="$OUTDIR/improve_simple_official.tsv"
PROGDIR="$OUTDIR/programs"
PRED_WORK="$OUTDIR/predictions"

echo "================ IMPROVE official run ================"
echo "INPUT=$INPUT"
echo "OUTDIR=$OUTDIR  STAB=$STAB  FOREIGN=$FOREIGN  SMOKE=$SMOKE"

# ---------- conda ----------
module load miniconda3/22.11.1-gcc-8.5.0-l4fo6ta
source "$(conda info --base)/etc/profile.d/conda.sh"
ENV_FEAT="$BASE/envs/imp_feat"
ENV_PRED="$BASE/envs/improve"

# ---------- Step 0: ProgramDir symlink (4 工具) ----------
echo "[Step 0] 建 ProgramDir: $PROGDIR"
mkdir -p "$PROGDIR/netMHCpan-4.1"
# netMHCpan: 代码要小写 netmhcpan, 文件大写 netMHCpan → 文件级 symlink (本地已验此法可行)
ln -sfn "$EXT/netMHCpan-4.1/netMHCpan" "$PROGDIR/netMHCpan-4.1/netmhcpan"
# netMHCstabpan: 整目录 symlink 保 wrapper 相对解析, 名 netMHCstabpan 大小写与代码一致
ln -sfn "$EXT/netMHCstabpan-1.0" "$PROGDIR/netMHCstabpan-1.0"
# PRIME / MixMHCpred: 整目录
ln -sfn "$TOOLREPOS/PRIME" "$PROGDIR/PRIME"
ln -sfn "$TOOLREPOS/MixMHCpred" "$PROGDIR/MixMHCpred-master"
ls -la "$PROGDIR"

# ---------- Step 1: 准备输入 (WT_peptide -> Norm_peptide; smoke 切片) ----------
echo "[Step 1] prep input -> $PREPPED"
conda activate "$ENV_PRED"
python3 - "$INPUT" "$PREPPED" "$SMOKE" <<'PYEOF'
import sys, pandas as pd
inp, out, smoke = sys.argv[1], sys.argv[2], int(sys.argv[3])
df = pd.read_csv(inp, sep='\t')
if 'WT_peptide' in df.columns and 'Norm_peptide' not in df.columns:
    df = df.rename(columns={'WT_peptide': 'Norm_peptide'})
if smoke > 0:
    df = df.head(smoke)
    print(f"[smoke] head {smoke} -> {len(df)} rows")
df.to_csv(out, sep='\t', index=False)
print(f"[Step1] {len(df)} rows -> {out}; cols={list(df.columns)}")
PYEOF
conda deactivate

# ---------- Step 2: feature_calc ----------
mkdir -p "$PRED_WORK/netmhcpan41/mut" "$PRED_WORK/netmhcpan41/wt" \
         "$PRED_WORK/netmhcstabpan" "$PRED_WORK/PRIME"
echo "[Step 2] feature_calc (env=imp_feat, STAB=$STAB)"
conda activate "$ENV_FEAT"
export PYTHONPATH="$R/bin/src:${PYTHONPATH:-}"   # 官方脚本 sys.path.append 是死路径(/home/projects), 这里补真路径
cd "$R"                                          # kernelSim 用 data/matrices/blosum62.qij 相对路径

if [ "$STAB" = "1" ]; then
    echo "  -> 官方 feature_calculations.py (含 netMHCstabpan, 真 Stability)"
    python3 "$OFFICIAL_FEAT_PY" \
        --file "$PREPPED" --dataset "$DATASET" \
        --PredDir "$PRED_WORK" --ProgramDir "$PROGDIR" --TmpDir "$PROGDIR" \
        --outfile "$FEATS"
else
    echo "  -> 降级 feature_calc_local.py (跳 netMHCstabpan, Stability=NaN)"
    IMPROVE_SRC="$R/bin/src" python3 "$LOCAL_FEAT_PY" \
        --file "$PREPPED" --dataset "$DATASET" \
        --PredDir "$PRED_WORK" --ProgramDir "$PROGDIR" --TmpDir "$PROGDIR" \
        --outfile "$FEATS"
fi
conda deactivate
echo "[Step 2] done -> $FEATS"

# ---------- QC: RankEL 覆盖 ----------
conda activate "$ENV_PRED"
python3 - "$FEATS" <<'PYEOF'
import sys, pandas as pd
df = pd.read_csv(sys.argv[1], sep='\t')
n = len(df); ok = df['RankEL'].notna().sum() if 'RankEL' in df.columns else 0
print(f"[QC feat] rows={n}, RankEL非NaN={ok} ({ok/max(n,1)*100:.1f}%)")
if ok == 0:
    raise SystemExit("[FATAL] RankEL 全 NaN → netMHCpan-4.1 失败, 检查 ProgramDir symlink / netMHCpan 配置")
PYEOF

conda deactivate

# ---------- Step 2a: Foreigness 真算 (antigen.garnish, 档II) ----------
FOREIGN_ARG=""
if [ "$FOREIGN" = "1" ]; then
    echo "[Step 2a] run_foreignness.R (env=garnish_r, antigen.garnish db=human)"
    if [ ! -d "$GARNISH_ENV" ]; then
        echo "[FATAL] garnish_r 未部署 ($GARNISH_ENV)。先跑 deploy_antigen_garnish.sh, 或 FOREIGN=0 跳过(走参考均值)。"
        exit 2
    fi
    conda activate "$GARNISH_ENV"
    AG_DATA_DIR="$AG_DATA_DIR" Rscript "$FOREIGN_R" "$PREPPED" "$FOREIGN_OUT"
    conda deactivate
    FOREIGN_ARG="--foreignness $FOREIGN_OUT"
    echo "[Step 2a] Foreigness -> $FOREIGN_OUT"
else
    echo "[Step 2a] FOREIGN=0 跳过真算, Foreigness 走参考均值 fallback (非档II默认)"
fi

# ---------- Step 2b: 补 Patient + merge 真算Foreigness + NetMHCExp/Expression 参考均值 ----------
echo "[Step 2b] complete_features.py"
conda activate "$ENV_PRED"
python3 "$COMPLETE_PY" \
    --in "$FEATS" --ref "$REF_FEATS" --out "$FEATS_COMPLETE" \
    $FOREIGN_ARG --patient elispot

# ---------- Step 3: predict Simple ----------
echo "[Step 3] predict_local.py --model Simple (env=improve)"
cd "$R"
python3 "$PREDICT_PY" --file "$FEATS_COMPLETE" --model Simple --outfile "$PRED_OUT"
conda deactivate
echo "[Step 3] done -> $PRED_OUT"

# ---------- 最终 QC ----------
conda activate "$ENV_PRED"
python3 - "$PRED_OUT" <<'PYEOF'
import sys, pandas as pd
df = pd.read_csv(sys.argv[1], sep='\t')
n = len(df); ok = df['mean_prediction_rf'].notna().sum()
print(f"[FINAL QC] rows={n}, mean_prediction_rf非NaN={ok} ({ok/max(n,1)*100:.1f}%)")
print(df[['Mut_peptide','HLA_allele','mean_prediction_rf']].head(5).to_string())
PYEOF
conda deactivate

echo ""
echo "===== DONE ====="
echo "特征(原):   $FEATS"
echo "特征(补全): $FEATS_COMPLETE"
echo "预测:       $PRED_OUT   (关键列 mean_prediction_rf)"
echo "拉回本地后跑: python scripts/hpc_official/parse_improve_official.py \\"
echo "    --pred improve_simple_official.tsv \\"
echo "    --map-csv scripts/out_official/improve_input_map.csv \\"
echo "    --master scripts/out_official/master_backbone_official.csv \\"
echo "    --out analysis/IMPROVE_official.csv"
