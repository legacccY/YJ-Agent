#!/usr/bin/env bash
# =============================================================================
# run_repitope_official.sh — 跑 Repitope 给 551 唯一肽打 MHC-I 免疫原性分
# =============================================================================
# 主线串行执行（agent 只写不跑）。先跑完 deploy_repitope.sh。
#   bash run_repitope_official.sh
#
# ⚠️ 这是 CPU+Java 重活，非 GPU 训练 —— 不走 gpu_slot.py（那是 GPU 调度）。
#    Features 步对 551 肽耗时约几十分钟~1~2h（远小于官方 21k 训练集）。
#    内存：JVM 默认 -Xmx 60G（登录节点 125G RAM 够；issue#7 OOM 是大集，551 肽小）。
#    coreN 默认 8（勿过大，issue#7 报过 "cannot create GC thread, out of resources"）。
#
# 跑法二选一（主线定）：
#   A) DTN 登录节点直接跑（CPU 活，DTN 允许）—— 本脚本默认；长跑用 setsid nohup 脱离。
#   B) CPU 计算节点 sbatch —— 若 DTN 限时，主线包成 SLURM 脚本投 CPU 分区（无需 GPU）。
# =============================================================================
set -euo pipefail

BASE=/gpfs/work/bio/jiayu2403/quantimmu
ENV="$BASE/envs/andy90_r"
RBIN="$ENV/bin"
DATADIR="$BASE/tools_repos/Repitope_data"
HERE="$(cd "$(dirname "$0")" && pwd)"

PEP_CSV="$BASE/official_inputs/out_official/newtools/uniq_pep.csv"   # 551 肽（已在 HPC）
FRAGLIB="$DATADIR/FragmentLibrary.fst"
FEATDF="$DATADIR/FeatureDF_MHCI_Weighted.10000.fst"
OUTDIR="$BASE/scripts/out_official/repitope_out"
CORE_N="${1:-8}"      # 可传参覆盖核数

export JAVA_TOOL_OPTIONS="-Xmx60G"   # rJava JVM 堆（README 用 java.parameters=-Xmx60G）
export R_LIBS_USER="$ENV/lib/R/library"

echo "==================================================================="
echo "[run_repitope] PEP=$PEP_CSV"
echo "[run_repitope] FRAGLIB=$FRAGLIB  FEATDF=$FEATDF"
echo "[run_repitope] OUTDIR=$OUTDIR  coreN=$CORE_N  Xmx=60G"
echo "==================================================================="

# 前置检查（缺则停，不静默造数）
for f in "$PEP_CSV" "$FRAGLIB" "$FEATDF"; do
  [[ -s "$f" ]] || { echo "[FAIL] 缺文件: $f （先跑 deploy_repitope.sh 下数据集）"; exit 1; }
done
mkdir -p "$OUTDIR"

echo "[run_repitope] 启动 R（前台；长跑想脱离请用：setsid nohup bash run_repitope_official.sh > $OUTDIR/run.log 2>&1 &）"
"$RBIN/Rscript" "$HERE/run_repitope.R" "$PEP_CSV" "$FRAGLIB" "$FEATDF" "$OUTDIR" "$CORE_N"

echo "==================================================================="
echo "[run_repitope] 完成。产出: $OUTDIR/Repitope_scores.csv"
echo "[run_repitope] 下一步（本地）: python parse_repitope_official.py"
echo "==================================================================="
