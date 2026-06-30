#!/usr/bin/env bash
# ===========================================================================
# run_seq2neo_official.sh — Seq2Neo immuno 官方端到端 (HPC linux, 主线一次跑)
# 服务: quantimmu-bench Phase0 官方数据工具补跑舰队 (lever=Seq2Neo, bonus 升正式)
#
# 管线 (官方 seq2neo immuno --mode multiple, 复现零偏离):
#   Step1  prep_seq2neo_official.py  → 从 master_backbone 生成 Pep,HLA 输入 (唯一对, 去星, 8-11mer)
#   Step2  seq2neo immuno --mode multiple
#            ├─ add_tap_ic50.mutiple_cal: 逐肽调
#            │     netMHCpan-4.1b (-BA → IC50) + netCTLpan-1.1b (→ TAP)
#            │     → 写 <outdir>/immuno_input_file.csv (Pep,HLA,IC50,TAP)
#            └─ _cnn.file_process: CNN(4输入: pep onehot + HLA pseudoseq + IC50 + TAP)
#                  → 写 <outdir>/cnn_results.csv (列: Peptide,HLA,IC50,TAP,pseudosequence,immunogenicity)
#   (parse 在本地: parse_seq2neo_official.py → Seq2Neo_official.csv, 见末尾)
#
# CLI (官方源 seq2neo/lib/arg_immunoprediction.py 核实; 仅 5 参数, 无 --skip):
#   seq2neo immuno --mode multiple --inputfile <Pep,HLA.csv> --outdir <out>
#
# 硬依赖 (Seq2Neo 内部以裸命令名 `netMHCpan` / `netCTLpan` 调用 → 必须在 PATH):
#   - netMHCpan == 4.1.b  (已有: ext_tools/netMHCpan-4.1)
#   - netCTLpan == 1.1.b  (DTU 学术许可; 主线装到 ext_tools/netCTLpan-1.1)
#   依据: add_tap_ic50.py 用 NetMHCpan41CommandLine(cmd="netMHCpan") / NetCTLpanCommandLine(cmd="netCTLpan")。
#
# 跑序 (HPC, 主线串行; setsid 后台):
#   1) 确认 netCTLpan 已装 (which netCTLpan)；编辑下方 NETMHCPAN_DIR / NETCTLPAN_DIR / SEQ2NEO_ENV 为真路径
#   2) SMOKE=10 bash run_seq2neo_official.sh   # 先 10 条烟测验全链 (netMHCpan→netCTLpan→CNN)
#   3) bash run_seq2neo_official.sh            # 全量
#   后台: setsid bash run_seq2neo_official.sh > run_seq2neo.log 2>&1 < /dev/null &
#
# 许可红线: Seq2Neo(AFL-3.0) + netMHCpan/netCTLpan(DTU 学术许可)。发表前确认引用+条款合规。
# 红线: 完全按官方 seq2neo immuno, 不私改超参/算法/裁剪。
# ===========================================================================
set -euo pipefail

# ---------- 配置 (主线按真实环境填) ----------
BASE="${BASE:-/gpfs/work/bio/jiayu2403/quantimmu}"
EXT="${EXT:-$BASE/ext_tools}"

# Seq2Neo conda env (liuxslab::seq2neo, linux-64 only). 主线填真名/路径。
# TODO(主线): 确认 env 名 (如 $BASE/envs/seq2neo 或 conda env 名 seq2neo)。
SEQ2NEO_ENV="${SEQ2NEO_ENV:-$BASE/envs/seq2neo}"

# DTU 工具目录 (内含同名 wrapper 脚本 netMHCpan / netCTLpan)。主线填真路径。
NETMHCPAN_DIR="${NETMHCPAN_DIR:-$EXT/netMHCpan-4.1}"
NETCTLPAN_DIR="${NETCTLPAN_DIR:-$EXT/netCTLpan-1.1}"   # TODO(主线): 装好后核对目录名

# 输入 backbone (HPC 上路径)。
BACKBONE="${BACKBONE:-$BASE/official_inputs/out_official/master_backbone_official.csv}"

# 输出
WORKDIR="${WORKDIR:-$BASE/seq2neo_official_run}"
INPUT_CSV="$WORKDIR/seq2neo_input.csv"
OUTDIR="$WORKDIR/seq2neo_out"

SMOKE="${SMOKE:-0}"   # >0 取前 N 个唯一对

# 脚本自身目录 (prep_seq2neo_official.py 同级)
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREP_PY="$SELF_DIR/prep_seq2neo_official.py"

mkdir -p "$WORKDIR" "$OUTDIR"

echo "================ Seq2Neo official run ================"
echo "BACKBONE=$BACKBONE"
echo "WORKDIR=$WORKDIR  SMOKE=$SMOKE"
echo "NETMHCPAN_DIR=$NETMHCPAN_DIR  NETCTLPAN_DIR=$NETCTLPAN_DIR"

# ---------- conda ----------
module load miniconda3/22.11.1-gcc-8.5.0-l4fo6ta
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate "$SEQ2NEO_ENV"

# ---------- DTU 工具入 PATH (Seq2Neo 内部裸命令名调用) ----------
export PATH="$NETMHCPAN_DIR:$NETCTLPAN_DIR:$PATH"
echo "[check] which netMHCpan: $(which netMHCpan || echo MISSING)"
echo "[check] which netCTLpan: $(which netCTLpan || echo MISSING)"
if ! command -v netMHCpan >/dev/null 2>&1; then
    echo "[FATAL] netMHCpan 不在 PATH。检查 NETMHCPAN_DIR。" >&2; exit 2
fi
if ! command -v netCTLpan >/dev/null 2>&1; then
    echo "[FATAL] netCTLpan 不在 PATH (DTU 许可待装?)。检查 NETCTLPAN_DIR。" >&2; exit 2
fi

# ---------- Step 1: 生成输入 (Pep,HLA) ----------
echo "[Step 1] prep input -> $INPUT_CSV"
python3 "$PREP_PY" --backbone "$BACKBONE" --out "$INPUT_CSV" --smoke "$SMOKE"
echo "[Step 1] 输入行数: $(wc -l < "$INPUT_CSV") (含表头)"

# ---------- Step 2: seq2neo immuno ----------
# Seq2Neo 在 CWD 建临时目录 tmp/ (跑完自删), 故 cd WORKDIR 保持干净。
echo "[Step 2] seq2neo immuno --mode multiple"
cd "$WORKDIR"
seq2neo immuno \
    --mode multiple \
    --inputfile "$INPUT_CSV" \
    --outdir "$OUTDIR"
echo "[Step 2] done -> $OUTDIR/cnn_results.csv (+ immuno_input_file.csv)"

# ---------- QC ----------
if [ -f "$OUTDIR/cnn_results.csv" ]; then
    echo "[QC] cnn_results.csv 行数: $(wc -l < "$OUTDIR/cnn_results.csv") (含表头)"
    echo "[QC] 表头: $(head -1 "$OUTDIR/cnn_results.csv")"
else
    echo "[FATAL] 未产出 cnn_results.csv。检查 netMHCpan/netCTLpan 调用日志。" >&2; exit 3
fi

echo ""
echo "===== DONE ====="
echo "cnn_results: $OUTDIR/cnn_results.csv (关键列 immunogenicity)"
echo "拉回本地后跑:"
echo "  python scripts/hpc_official/parse_seq2neo_official.py \\"
echo "      --results <拉回的>/cnn_results.csv \\"
echo "      --backbone scripts/out_official/master_backbone_official.csv \\"
echo "      --out scripts/out_official/Seq2Neo_official.csv"
