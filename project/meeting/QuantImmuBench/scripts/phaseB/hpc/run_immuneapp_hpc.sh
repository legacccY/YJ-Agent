#!/bin/bash
# run_immuneapp_hpc.sh — Phase B：在 HPC 上用订正 HLA 重推理 ImmuneApp-Neo（P101/P102）。
#
# 做什么：module load conda → source activate envs/immuneapp（TF1.15/py3.7）→ 调
#         run_immuneapp_hpc.py（prep+run+parse 一体，只读 $BASE/phaseB/backbone_101102.csv）。
#         env 激活后 python 已在 PATH，编排器直接 subprocess 调官方脚本，不走 WSL/conda run。
#
# 用法（主线 ssh 到 HPC 登录节点后）:
#   bash run_immuneapp_hpc.sh            # 全量，产 $BASE/phaseB/ImmuneApp_101102.csv
#   bash run_immuneapp_hpc.sh --smoke 1  # 只跑前 1 个 allele 验工具，不产 CSV
#
# 注：CPU 推理即可（TF1.15；libcuda.so.1 警告无害）。耗时随 allele 数（7 个 allele）。
set -e

# ── conda（与 hpc_neotimmuml.sh / dep_deepimmuno.sh 同惯用法）────────────────
source /etc/profile.d/modules.sh 2>/dev/null || true
module load miniconda3/22.11.1-gcc-8.5.0-l4fo6ta

BASE=/gpfs/work/bio/jiayu2403/quantimmu
ENV=$BASE/envs/immuneapp
source activate $ENV

# 导出给编排器（与默认一致；如路径改了改这里，不改 .py）
export QIB_BASE=$BASE
export IMMUNEAPP_REPO=$BASE/tools_repos/ImmuneApp

HERE=$(cd "$(dirname "$0")" && pwd)
echo "[wrap] env=$ENV"
echo "[wrap] python=$(which python)  ($(python --version 2>&1))"
echo "[wrap] 调 run_immuneapp_hpc.py $*"
python "$HERE/run_immuneapp_hpc.py" "$@"
echo "[wrap] DONE"
