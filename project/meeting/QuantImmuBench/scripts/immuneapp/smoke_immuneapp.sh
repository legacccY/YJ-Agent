#!/usr/bin/env bash
# ===========================================================================
# smoke_immuneapp.sh — ImmuneApp-Neo 烟测脚本
# 服务: quantimmu-bench / ImmuneApp-Neo 免疫原性预测
#
# 用法（HPC 登录节点或交互节点 bash 下运行）:
#   bash /gpfs/work/bio/jiayu2403/quantimmu/scripts/immuneapp/smoke_immuneapp.sh
#
# 产出：
#   $OUTPUT_DIR/ImmuneApp_Immunogenicity_predictions.tsv   (主要结果)
#   $LOG_DIR/immuneapp_smoke_stdout.log                    (完整 stdout)
#
# 说明：
#   使用 repo 自带 testdata/test_immunogenicity.txt（官方示例肽段）
#   + HLA-A*01:01 HLA-A*02:01 两个 allele 做烟测
#   成功标志：输出 tsv 含 Immunogenicity_score 列且行数 > 0
# ===========================================================================

set -euo pipefail

# ---------- 路径配置 ----------
QUANTIMMU_HOME="/gpfs/work/bio/jiayu2403/quantimmu"
CONDA_ENVS="$QUANTIMMU_HOME/envs"
ENV_NAME="immuneapp"
REPO_DIR="$QUANTIMMU_HOME/tools_repos/ImmuneApp"
OUTPUT_DIR="$QUANTIMMU_HOME/elispot_run/immuneapp_out"
LOG_DIR="$QUANTIMMU_HOME/logs"

mkdir -p "$OUTPUT_DIR" "$LOG_DIR"

_CONDA_RUN="conda run --no-capture-output -p $CONDA_ENVS/$ENV_NAME"

echo "========================================================"
echo "  ImmuneApp-Neo 烟测"
echo "  REPO_DIR   : $REPO_DIR"
echo "  OUTPUT_DIR : $OUTPUT_DIR"
echo "========================================================"

# ---------- Step 0: 加载 miniconda3 ----------
echo ""
echo "[Step 0] 加载 miniconda3/22.11.1 ..."
module load miniconda3/22.11.1
source "$(conda info --base)/etc/profile.d/conda.sh"

# ---------- Step 1: 确认 env / repo 存在 ----------
echo ""
echo "[Step 1] 前置检查 ..."

if [ ! -d "$CONDA_ENVS/$ENV_NAME" ]; then
    echo "[ERROR] conda env $ENV_NAME 不存在，请先运行 deploy_immuneapp.sh" >&2
    exit 1
fi

if [ ! -f "$REPO_DIR/ImmuneApp_immunogenicity_prediction.py" ]; then
    echo "[ERROR] $REPO_DIR/ImmuneApp_immunogenicity_prediction.py 不存在，repo 未 clone" >&2
    exit 1
fi

if [ ! -f "$REPO_DIR/testdata/test_immunogenicity.txt" ]; then
    echo "[ERROR] testdata/test_immunogenicity.txt 不存在，repo 结构异常" >&2
    exit 1
fi

echo "  env / repo / testdata 三项检查通过"

# ---------- Step 2: 展示 testdata 前几行（确认格式）----------
echo ""
echo "[Step 2] testdata/test_immunogenicity.txt 前 5 行（每行一个肽段，无 header）:"
head -5 "$REPO_DIR/testdata/test_immunogenicity.txt" || true

# ---------- Step 3: 运行 ImmuneApp-Neo ----------
echo ""
echo "[Step 3] 运行 ImmuneApp_immunogenicity_prediction.py ..."
echo "  命令: python ImmuneApp_immunogenicity_prediction.py"
echo "         -f testdata/test_immunogenicity.txt"
echo "         -a 'HLA-A*01:01' 'HLA-A*02:01'"
echo "         -o $OUTPUT_DIR"

# 必须 cd 到 REPO_DIR，脚本用相对路径加载权重（ImmuneApp_weights/）
cd "$REPO_DIR"

${_CONDA_RUN} python ImmuneApp_immunogenicity_prediction.py \
    -f testdata/test_immunogenicity.txt \
    -a 'HLA-A*01:01' 'HLA-A*02:01' \
    -o "$OUTPUT_DIR" \
    2>&1 | tee "$LOG_DIR/immuneapp_smoke_stdout.log"

echo ""
echo "[Step 3] 命令执行完成，stdout 已存: $LOG_DIR/immuneapp_smoke_stdout.log"

# ---------- Step 4: QC 检查输出 tsv ----------
echo ""
echo "[Step 4] QC 检查输出文件 ..."

TSV_PATH="$OUTPUT_DIR/ImmuneApp_Immunogenicity_predictions.tsv"

if [ ! -f "$TSV_PATH" ]; then
    echo "[ERROR] 输出文件不存在: $TSV_PATH" >&2
    echo "  可能原因：" >&2
    echo "  - 输出目录参数 -o 接受的是文件路径而非目录，请查看 stdout log 核实" >&2
    echo "  - 查 log: cat $LOG_DIR/immuneapp_smoke_stdout.log" >&2
    # 列出 OUTPUT_DIR 所有文件帮助调试
    echo "  $OUTPUT_DIR 当前文件列表:" >&2
    ls -la "$OUTPUT_DIR" >&2 || true
    exit 1
fi

# Python QC：检查列名 + 行数 + 分数值域
${_CONDA_RUN} python - <<PYEOF
import pandas as pd
import sys

tsv_path = "$TSV_PATH"
df = pd.read_csv(tsv_path, sep='\t')
print(f"  输出文件   : {tsv_path}")
print(f"  行数       : {len(df)}")
print(f"  列名       : {list(df.columns)}")

# 必要列检查
required = ['Allele', 'Peptide', 'Immunogenicity_score']
missing = [c for c in required if c not in df.columns]
if missing:
    print(f"[ERROR] 缺少必要列: {missing}", file=sys.stderr)
    sys.exit(1)

# 分数值域检查（sigmoid 输出应在 0~1）
score_min = df['Immunogenicity_score'].min()
score_max = df['Immunogenicity_score'].max()
print(f"  Immunogenicity_score 值域: [{score_min:.6f}, {score_max:.6f}]")
print(f"  每 allele 行数:")
print(df['Allele'].value_counts().to_string())

print("")
print("  --- 前 5 行输出 ---")
print(df.head(5).to_string(index=False))

# 判定通过
if len(df) == 0:
    print("[ERROR] 输出为空，0 行", file=sys.stderr)
    sys.exit(1)
if 'Sample' in df.columns:
    print(f"\n  [注] 含 Sample 列，每肽每 allele 独立一行（per-allele 输出格式确认）")

print("\n[QC PASS] ImmuneApp-Neo 烟测通过")
PYEOF

# ---------- 完成摘要 ----------
echo ""
echo "========================================================"
echo "  烟测完成"
echo "  输出 tsv    : $TSV_PATH"
echo "  stdout log  : $LOG_DIR/immuneapp_smoke_stdout.log"
echo "  关键列      : Allele / Peptide / Sample / Immunogenicity_score"
echo "  分数格式    : 0~1 连续（sigmoid 概率，.4% 格式化显示）"
echo ""
echo "  回填 TOOLS/ImmuneApp.md TODO 项："
echo "  - 实测命令行（见上 Step 3）"
echo "  - Immunogenicity_score 值域（见 QC 输出）"
echo "  - 多 HLA allele 是否 per-allele（见 Allele 列行数分布）"
echo "========================================================"
