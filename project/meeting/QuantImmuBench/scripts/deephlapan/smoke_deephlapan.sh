#!/usr/bin/env bash
# ===========================================================================
# smoke_deephlapan.sh — deepHLApan 全链烟测
# 服务: quantimmu-bench / deepHLApan
#
# 用法:
#   # 路 A（conda env）:
#   bash smoke_deephlapan.sh --mode conda
#
#   # 路 B（singularity sif）:
#   bash smoke_deephlapan.sh --mode sif
#
# 默认: --mode conda
#
# 烟测内容:
#   1. 用 repo 自带 demo/1.csv 跑 binding + immunogenicity 双模型
#   2. 用 benchmark ELISpot 数据集的前 5 行跑（需先运行 prepare_inputs.py）
#   3. 输出存 $OUTPUT_DIR/deephlapan_smoke_{demo,elispot5}.csv
#
# HLA 格式注意（ELISpot 数据集）:
#   master_backbone.csv 中 HLA_Allele 是标准格式 HLA-A*02:01（含星号）
#   deepHLApan 要求格式 HLA-A02:01（无星号，有连字符）
#   本脚本在写 CSV 前做转换: HLA-A*02:01 → HLA-A02:01（去掉 *）
#
# 成功标志:
#   打印 SMOKE_DEMO_DONE + SMOKE_ELISPOT5_DONE + ALL_SMOKE_DONE
# ===========================================================================

set -euo pipefail

# ---------- 参数解析 ----------
MODE="conda"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --mode) MODE="$2"; shift 2 ;;
        *) echo "[WARN] 未知参数: $1"; shift ;;
    esac
done

if [[ "$MODE" != "conda" && "$MODE" != "sif" ]]; then
    echo "[ERROR] --mode 只接受 conda 或 sif"
    exit 1
fi

echo "===== [smoke] deepHLApan 烟测 mode=$MODE ====="

# ---------- 路径配置 ----------
ROOT=/gpfs/work/bio/jiayu2403/quantimmu
REPO_DIR="$ROOT/tools_repos/deephlapan"
ENV_DIR="$ROOT/envs/deephlapan"
SIF_PATH="$ROOT/sif/deephlapan.sif"
OUTPUT_DIR="$ROOT/elispot_run/deephlapan_out"
SCRIPTS_DIR="$ROOT/scripts/deephlapan"

# ELISpot 输入（由 prepare_inputs.py 产出的 backbone）
BACKBONE_CSV="/gpfs/work/bio/jiayu2403/quantimmu/data/master_backbone.csv"
# 若 HPC 上 backbone 不存在，尝试 scripts/out/
ALT_BACKBONE="/gpfs/work/bio/jiayu2403/quantimmu/scripts/out/master_backbone.csv"

mkdir -p "$OUTPUT_DIR"

# ---------- conda / sif 执行器 ----------
source /etc/profile.d/modules.sh 2>/dev/null || true
module load miniconda3/22.11.1-gcc-8.5.0-l4fo6ta 2>/dev/null || true

if [[ "$MODE" == "conda" ]]; then
    if [ ! -d "$ENV_DIR" ]; then
        echo "[ERROR] conda env 不存在: $ENV_DIR，先跑 deploy_deephlapan_condaA.sh"
        exit 1
    fi
    RUN_PY="conda run --no-capture-output -p $ENV_DIR python"
elif [[ "$MODE" == "sif" ]]; then
    if [ ! -f "$SIF_PATH" ]; then
        echo "[ERROR] sif 不存在: $SIF_PATH，先跑 build_deephlapan_sifB.sh"
        exit 1
    fi
    # singularity exec：bind 项目根 + repo
    RUN_PY="singularity exec --bind $ROOT:$ROOT $SIF_PATH python"
fi

echo "[smoke] RUN_PY = $RUN_PY"

# ---------- 确认 repo 存在 ----------
if [ ! -d "$REPO_DIR" ]; then
    echo "[ERROR] repo 不存在: $REPO_DIR，先 git clone"
    exit 1
fi

# ---------- 烟测 1：官方 demo/1.csv ----------
echo ""
echo "===== [smoke-1] 官方 demo/1.csv ====="
DEMO_CSV="$REPO_DIR/demo/1.csv"

if [ ! -f "$DEMO_CSV" ]; then
    echo "[WARN] demo/1.csv 不存在于 $REPO_DIR/demo/"
    echo "  repo 内 demo 文件列表:"
    ls "$REPO_DIR/demo/" 2>/dev/null || echo "  demo/ 目录不存在"
    echo "  跳过 smoke-1"
else
    echo "demo CSV 头:"
    head -3 "$DEMO_CSV"
    DEMO_OUT="$OUTPUT_DIR/deephlapan_smoke_demo.csv"

    # deepHLApan 主脚本: deephlapan.py -F <csv> 输出到 stdout 或 --outdir
    # TODO: 实际输出参数名需跑一次确认（README 未列 --outdir 精确用法）
    # 先试 -F <csv>，输出重定向到文件
    cd "$REPO_DIR"
    $RUN_PY deephlapan.py -F "$DEMO_CSV" > "$DEMO_OUT" 2>&1 || {
        echo "[WARN] deephlapan.py -F 失败，尝试 main.py -F ..."
        $RUN_PY main.py -F "$DEMO_CSV" > "$DEMO_OUT" 2>&1 || {
            echo "[ERROR] 两种入口均失败，见 $DEMO_OUT"
            cat "$DEMO_OUT"
            exit 1
        }
    }

    echo "SMOKE_DEMO_DONE"
    echo "输出前5行:"
    head -5 "$DEMO_OUT"
    echo "输出路径: $DEMO_OUT"
fi

# ---------- 烟测 2：ELISpot 数据集前 5 行 ----------
echo ""
echo "===== [smoke-2] ELISpot backbone 前5行 ====="

# 找 backbone
BACKBONE=""
if [ -f "$BACKBONE_CSV" ]; then
    BACKBONE="$BACKBONE_CSV"
elif [ -f "$ALT_BACKBONE" ]; then
    BACKBONE="$ALT_BACKBONE"
else
    echo "[WARN] master_backbone.csv 未找到，跳过 smoke-2"
    echo "  tried: $BACKBONE_CSV"
    echo "  tried: $ALT_BACKBONE"
fi

if [ -n "$BACKBONE" ]; then
    ELISPOT5_INPUT="$OUTPUT_DIR/deephlapan_elispot5_input.csv"
    ELISPOT5_OUT="$OUTPUT_DIR/deephlapan_smoke_elispot5.csv"

    # 用 python 生成 deepHLApan 格式输入（HLA 去星号）
    # 取前 5 个有效行（MT_Subpeptide 长度 8-15，HLA_Allele 非空）
    conda run --no-capture-output -p "$ENV_DIR" python - <<PYEOF 2>&1 || \
    $RUN_PY - <<PYEOF2
import pandas as pd, sys

# 先用内嵌 python 构建输入（可能 env 不同，若失败用 RUN_PY 再试）
try:
    bb = pd.read_csv("$BACKBONE", low_memory=False)
except Exception as e:
    print(f"[ERROR] 读 backbone 失败: {e}", file=sys.stderr)
    sys.exit(1)

# 过滤有效行
mask = (
    bb['MT_Subpeptide'].apply(lambda x: 8 <= len(str(x)) <= 15)
    & bb['HLA_Allele'].notna()
    & bb['MT_Subpeptide'].notna()
)
sub = bb[mask].head(5).copy()

if len(sub) == 0:
    print("[WARN] 无有效行（肽长8-15且HLA非空），检查 backbone", file=sys.stderr)
    sys.exit(1)

# HLA 转换: HLA-A*02:01 → HLA-A02:01（去星号）
sub['HLA_deephlapan'] = sub['HLA_Allele'].str.replace('*', '', regex=False)

# 构建 deepHLApan 输入 CSV（Annotation,HLA,peptide）
out_df = pd.DataFrame({
    'Annotation': sub['Peptide_ID'].fillna('unknown').astype(str),
    'HLA':        sub['HLA_deephlapan'],
    'peptide':    sub['MT_Subpeptide'].astype(str),
})

out_df.to_csv("$ELISPOT5_INPUT", index=False)
print(f"[smoke-2] 输入5行 → $ELISPOT5_INPUT")
print(out_df.to_string())
PYEOF
PYEOF2

    # 跑 deepHLApan
    if [ -f "$ELISPOT5_INPUT" ]; then
        echo "[smoke-2] 跑 deepHLApan on elispot5..."
        cd "$REPO_DIR"
        $RUN_PY deephlapan.py -F "$ELISPOT5_INPUT" > "$ELISPOT5_OUT" 2>&1 || {
            echo "[WARN] deephlapan.py -F 失败，尝试 main.py ..."
            $RUN_PY main.py -F "$ELISPOT5_INPUT" > "$ELISPOT5_OUT" 2>&1 || {
                echo "[ERROR] smoke-2 失败，见 $ELISPOT5_OUT"
                cat "$ELISPOT5_OUT"
                exit 1
            }
        }
        echo "SMOKE_ELISPOT5_DONE"
        echo "输出前5行:"
        head -5 "$ELISPOT5_OUT"
        echo "输出路径: $ELISPOT5_OUT"
    fi
fi

# ---------- 最终汇总 ----------
echo ""
echo "===== [smoke] 结果汇总 ====="
ls -lh "$OUTPUT_DIR/"*.csv 2>/dev/null || echo "(无 csv 产出，见上方错误)"
echo ""
echo "ALL_SMOKE_DONE"
echo ""
echo "--- 后续步骤 ---"
echo "1. 确认输出列名（binding/immunogenicity score 列名 TODO，需回填 TOOLS/deepHLApan.md §3）"
echo "2. 回填 TOOLS/deepHLApan.md §1 实测输入样例 + §2 实测命令行 + §3 实测输出样例"
echo "3. 全量跑: 把 elispot5 换成完整 backbone，去掉 .head(5) 限制"
echo ""
echo "--- HLA 格式备忘 ---"
echo "  master_backbone HLA_Allele : HLA-A*02:01  (带星号，标准格式)"
echo "  deepHLApan 需要 : HLA-A02:01   (去星号，str.replace('*',''))"
echo "  转换已内置于本脚本 smoke-2 步"
