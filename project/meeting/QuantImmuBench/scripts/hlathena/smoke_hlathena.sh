#!/usr/bin/env bash
# ===========================================================================
# smoke_hlathena.sh
# 服务: quantimmu-bench  lever: HLAthena presentation proxy baseline
#
# ⚠️  HLAthena 预测 MHC-I 提呈（presentation）不是免疫原性。
#     进 benchmark 只作 presentation baseline proxy，不与免疫原性工具并列。
#
# 功能: 最小烟测 — 准备小 peptide TSV → singularity run HLAthena → 存输出
#
# 在 HPC 登录节点执行（singularity 3.11.3 可用）:
#   bash smoke_hlathena.sh [--smoke N]
#   --smoke N: 用内置 N 条测试肽（默认 8，可选 8/9/10/11 mer 各 2 条）
#
# TODO（主线在 hlathena.tools 文档核实后回填）:
#   [1] HLA 格式字符串: hlathena.tools Predict→"How to use" 核实。
#       目前占位格式为 "HLA-A*02:01"（标准 netMHCpan 格式）。
#       如 Docker 内部用不同格式（如 "A0201" / "HLA-A0201"）需修改下方 HLA_ALLELE 列值。
#   [2] Docker 命令行参数: 镜像 entrypoint/CMD 未在公开文档中确认。
#       下方用 `singularity run` + 猜测参数 `--input_file / --output_file`。
#       ⚠️ 实际参数需先: singularity exec hlathena.sif python run_hlathena.py --help
#          或: singularity inspect --runscript hlathena.sif  查看 entrypoint
#   [3] MSiC/MSiCE 模型需额外列（ctex_up/ctex_dn 或 TPM），此烟测只跑 MSi（最简）。
#   [4] 阈值（MSiC ≥0.95 strong/≥0.90/≥0.80 weak）需 hlathena.tools 文档确认。
# ===========================================================================

set -euo pipefail

# ---------- 参数 ----------
SMOKE_N=8
if [[ "${1:-}" == "--smoke" ]]; then
    SMOKE_N="${2:-8}"
fi

echo "================================================================"
echo " HLAthena 最小烟测 (MSi 模型)"
echo " ⚠️  presentation proxy — 非免疫原性"
echo "================================================================"

# ---------- 路径配置（HPC 侧）----------
HPC_QUANTIMMU="/gpfs/work/bio/jiayu2403/quantimmu"
SIF_PATH="$HPC_QUANTIMMU/sif/hlathena.sif"
SMOKE_DIR="$HPC_QUANTIMMU/smoke/hlathena"
INPUT_TSV="$SMOKE_DIR/smoke_peptides.tsv"
OUTPUT_TSV="$SMOKE_DIR/smoke_output.tsv"

mkdir -p "$SMOKE_DIR"

# ===========================================================================
# 步骤 1: 生成测试 peptide TSV
# ===========================================================================
echo ""
echo "===== [1] 生成测试 peptide TSV ====="

# TODO [1]: 下方 HLA_ALLELE 值 "HLA-A*02:01" 需在 hlathena.tools 文档确认。
#   运行前请在 hlathena.tools 的 Predict → How to use 中查看 HLA allele 字段格式。
#   如格式不对，singularity run 会报 "unknown HLA allele" 类错误。

python3 - <<PYEOF
import csv, os

# 测试肽 (8-11mer，覆盖所有支持长度)
# 来源: 随机构建的测试序列，不含真实免疫原性标注，仅用于烟测
# TODO [1]: HLA 格式待确认 — 当前占位 "HLA-A*02:01"
peptides = [
    # 8-mer
    ("GILGFVFTL", "HLA-A*02:01"),   # 经典 flu 肽（公知 MHC-I 配体）
    ("NLVPMVATV", "HLA-A*02:01"),   # CMV pp65
    # 9-mer
    ("GILGFVFTLV", "HLA-A*02:01"),
    ("SIINFEKL", "TODO_MOUSE"),      # OVA (H-2Kb，TODO: 小鼠等位基因格式确认)
    # 10-mer
    ("GILGFVFTLVK", "HLA-A*02:01"),
    ("ELAGIGILTV", "HLA-A*02:01"),  # MART-1
    # 11-mer
    ("GILGFVFTLVKM", "HLA-A*02:01"),
    ("FLPSDYFPSV", "HLA-A*02:01"),
][:$SMOKE_N]

os.makedirs("$SMOKE_DIR", exist_ok=True)
with open("$INPUT_TSV", "w", newline="") as f:
    writer = csv.writer(f, delimiter="\t")
    # TODO [1]: 列名 "peptide" 和 "hla" 需按 Docker 内部期待格式确认
    #   (hlathena.tools 示例显示 header=peptide，HLA 列名待查)
    writer.writerow(["peptide", "hla"])
    for pep, hla in peptides:
        writer.writerow([pep, hla])

print(f"[1] 写入 $SMOKE_N 条测试肽 -> $INPUT_TSV")
PYEOF

echo "[1] 测试 TSV 内容:"
cat "$INPUT_TSV"
echo ""

# ===========================================================================
# 步骤 2: 检查 SIF 是否存在
# ===========================================================================
echo "===== [2] 检查 SIF ====="
if [[ ! -f "$SIF_PATH" ]]; then
    echo "[ERROR] SIF 不存在: $SIF_PATH"
    echo "  请先运行 build_hlathena_sif.sh 构建镜像"
    exit 1
fi
echo "[2] SIF 存在: $SIF_PATH"
ls -lh "$SIF_PATH"

# ===========================================================================
# 步骤 3: 先 inspect entrypoint，确认正确命令行
# ===========================================================================
echo ""
echo "===== [3] inspect SIF runscript ====="
singularity inspect --runscript "$SIF_PATH" 2>&1 | head -40 || true
echo ""
echo "------- inspect deffile (if available) -------"
singularity inspect --deffile "$SIF_PATH" 2>&1 | head -40 || true
echo ""

# TODO [2]: 用 exec 看 help，帮助确认参数
echo "------- help (python run script if exists) -------"
singularity exec "$SIF_PATH" python /run_hlathena.py --help 2>&1 | head -60 || \
    echo "[WARN] /run_hlathena.py --help 失败，尝试其他入口..." && \
    singularity exec "$SIF_PATH" ls / 2>&1 | head -30 || true
echo ""

# ===========================================================================
# 步骤 4: 运行 HLAthena MSi 预测
# ===========================================================================
echo "===== [4] singularity run MSi 预测 ====="

# TODO [2]: 下方命令行参数为根据 Docker Hub README 推断的占位版本。
#   实际参数在步骤 3 inspect 后确认，运行前手动更新此处。
#   已知: 输入需带 header 的 tab 分隔文件；输出含 MSi 列；模型选 MSi。
#
# 占位命令 (inspect 后替换为真实参数):
singularity run \
    --bind "$SMOKE_DIR:/data" \
    "$SIF_PATH" \
    --input_file /data/smoke_peptides.tsv \
    --output_file /data/smoke_output.tsv \
    --model MSi \
    2>&1 | tee "$SMOKE_DIR/smoke_run.log"

# ===========================================================================
# 步骤 5: 验证输出
# ===========================================================================
echo ""
echo "===== [5] 验证输出 ====="

if [[ ! -f "$OUTPUT_TSV" ]]; then
    echo "[WARN] 预期输出不存在: $OUTPUT_TSV"
    echo "  可能原因:"
    echo "  1. --output_file 参数名不对 (TODO [2] 确认)"
    echo "  2. 输出写到了容器内其他路径"
    echo "  3. HLA 格式不对导致跑失败 (TODO [1] 确认)"
    echo "  查看日志: $SMOKE_DIR/smoke_run.log"
    echo ""
    echo "  列出 $SMOKE_DIR 中所有文件 (找实际输出位置):"
    ls -la "$SMOKE_DIR/"
    exit 1
fi

echo "[5] 输出文件: $OUTPUT_TSV"
echo "[5] 行数: $(wc -l < "$OUTPUT_TSV") (含 header)"
echo "[5] 前 15 行:"
head -15 "$OUTPUT_TSV"
echo ""

# 简单 QC: 检查有没有 MSi 列
python3 - <<PYEOF
import csv, sys

with open("$OUTPUT_TSV") as f:
    reader = csv.reader(f, delimiter="\t")
    header = next(reader, None)
    rows = list(reader)

print(f"[QC] 输出列: {header}")
if header and 'MSi' in header:
    msi_idx = header.index('MSi')
    scores = [float(r[msi_idx]) for r in rows if len(r) > msi_idx and r[msi_idx]]
    print(f"[QC] MSi 分数范围: min={min(scores):.4f}, max={max(scores):.4f}, n={len(scores)}")
    print(f"[QC] MSi 前 5 行: {scores[:5]}")
    print("[QC] SMOKE PASS: MSi 列存在且有值")
else:
    print(f"[QC] WARN: 未找到 MSi 列，实际输出列={header}")
    print("     请核实 TODO [2] 的参数设置")
    sys.exit(1)

# TODO [4]: 阈值注释（待 hlathena.tools 文档确认后更新）
# MSiC >= 0.95 -> strong binder (presentation proxy)
# MSiC >= 0.90 -> normal binder
# MSiC >= 0.80 -> weak binder
# ⚠️  以上阈值仅为论文推断，非官方文档确认值
PYEOF

# ===========================================================================
# 完成
# ===========================================================================
echo ""
echo "================================================================"
echo " SMOKE TEST 完成"
echo " 输入: $INPUT_TSV"
echo " 输出: $OUTPUT_TSV"
echo " 日志: $SMOKE_DIR/smoke_run.log"
echo ""
echo " ⚠️  结果含义提醒:"
echo "   HLAthena 输出 MSi = MHC-I 提呈分（presentation score）"
echo "   不是免疫原性分。进 ELISpot benchmark 只作 presentation proxy。"
echo "   AUC 预期 ~0.6（近随机），参考 Sarkizova 2020 Nat Biotech Supp。"
echo ""
echo " TODO 回填 TOOLS/HLAthena.md:"
echo "   [ ] HLA 格式字符串（步骤 3 确认）"
echo "   [ ] 实际命令行参数（步骤 3 确认后更新 步骤 4）"
echo "   [ ] 实测输入/输出样例"
echo "   [ ] MSi 阈值（hlathena.tools 文档核实）"
echo "================================================================"
