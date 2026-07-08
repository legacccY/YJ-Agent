#!/bin/bash
# 本地 WSL2 T-SCAPE 官方推理 —— WT 侧补跑（§3.1 DAI）。
# 用法: _run_tscape_wt_local.sh [<input_csv> [<output_csv>]]
#   默认 input  = scripts/out_rerun/tscape_inputs/tscape_input_WT.csv （prep 产，列 Allele,peptide 带星）
#   默认 output = scripts/out_rerun/tscape_inputs/tscape_output_WT.csv（列 Allele,peptide,score）
#
# ★ 复现零偏离：完全照 MT recipe（2026-06-30 本地补跑跑通版），只把肽源 MT→WT、换 WT outdir。
#   工具/权重(best_param/pmhc_im_neo)/超参/inf_type/device 一律不改。
# 官方两步（README 权威，cwd=repo 根）:
#   ① python mhc_pseudo_matching.py I  <input>          <input_modified>
#   ② python inference_csv.py --csv_path <input_modified> --inf_type pmhc_im_neo --output <output>
set -u

BASE=/mnt/d/YJ-Agent/project/meeting/QuantImmuBench/scripts/out_rerun/tscape_inputs
IN="${1:-$BASE/tscape_input_WT.csv}"
OUT="${2:-$BASE/tscape_output_WT.csv}"
MODIFIED="$BASE/tscape_input_WT_modified.csv"

REPO=/root/quantimmu/tools_repos/T-SCAPE          # WSL2 官方仓库（inference_csv.py 已 device patch）
PY=/root/miniconda3/envs/tscape/bin/python        # tscape conda env（pmhc_im_neo 权重 945M 就位）
INF_TYPE=pmhc_im_neo                              # 固定，勿改（复现零偏离）

echo "REPO=$REPO"
echo "PY=$PY"
echo "IN=$IN"
echo "OUT=$OUT"
[ ! -f "$IN" ] && { echo "[FATAL] 缺 WT 输入: $IN（先跑 prep）"; exit 2; }
[ ! -d "$REPO" ] && { echo "[FATAL] 缺 T-SCAPE 仓库: $REPO"; exit 2; }

cd "$REPO" || { echo "[FATAL] 无法 cd $REPO"; exit 2; }

# ① HLA→pseudo 序列映射（class I）。输入 Allele 保留 WHO 原格式（带星），脚本内部归一。
echo "[step1] $PY mhc_pseudo_matching.py I $IN $MODIFIED"
"$PY" mhc_pseudo_matching.py I "$IN" "$MODIFIED"
rc1=$?
if [ $rc1 -ne 0 ] || [ ! -f "$MODIFIED" ]; then
    echo "[FATAL] mhc_pseudo_matching 失败 rc=$rc1（modified 未生成）"; exit 3
fi

# ② 推理（单权重由 inf_type 自动选；device=cpu，patch 版）
echo "[step2] $PY inference_csv.py --csv_path $MODIFIED --inf_type $INF_TYPE --output $OUT"
"$PY" inference_csv.py --csv_path "$MODIFIED" --inf_type "$INF_TYPE" --output "$OUT"
rc2=$?
if [ $rc2 -ne 0 ] || [ ! -f "$OUT" ]; then
    echo "[FATAL] inference_csv 失败 rc=$rc2（output 未生成）"
    echo "        若 KeyError 'pmhc_im_neo' / 权重未加载 → 停下报主线 escalate researcher，勿改源码。"
    exit 4
fi

n=$(($(wc -l < "$OUT") - 1))
echo "[OUT] $OUT  数据行≈$n（列 Allele,peptide,score）"
echo "[next] parse+并入: python scripts/_build_seq2neo_tscape_wt.py merge"
