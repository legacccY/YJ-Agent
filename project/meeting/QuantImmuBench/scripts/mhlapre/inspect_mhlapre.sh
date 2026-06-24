#!/usr/bin/env bash
# ===========================================================================
# MHLAPre repo 勘察脚本 — clone 后先跑这个，再写 run 脚本
# 服务：QuantImmuBench，Wave 3
#
# 目的：
#   repo 无 CLI 文档、无 example data → 必须读源码才知道：
#   1. 输入文件路径/列名（Pretreatment.py 读什么文件）
#   2. 路径有无硬编码（能否改 → 直接路径/工作目录）
#   3. 权重文件期待路径（TransfomerEncoder.py / TextCNN.py 加载哪里）
#   4. 输出文件名/列名（TextCNN.py 写什么）
#   5. example data 有无（目录扫描）
#
# 用法（clone 后，在 HPC 上）：
#   bash inspect_mhlapre.sh
#
# 输出：打印到 stdout，建议重定向保存：
#   bash inspect_mhlapre.sh 2>&1 | tee inspect_report.txt
# ===========================================================================

set -uo pipefail  # 注意：不加 -e，允许 grep 无结果时继续

MHLAPRE_HOME="/gpfs/work/bio/jiayu2403/quantimmu/tools_repos/MHLAPre"

echo "===== MHLAPre Repo 勘察报告 ====="
echo "repo 路径: $MHLAPRE_HOME"
echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# ---------- 检查 repo 是否存在 ----------
if [ ! -d "$MHLAPRE_HOME" ]; then
    echo "[ERROR] repo 目录不存在: $MHLAPRE_HOME"
    echo "请先运行 deploy_mhlapre.sh 完成 git clone"
    exit 1
fi

# ---------- 1. 目录树（全量，找 example/data/model 目录）----------
echo "========================================="
echo "1. 目录结构（全量）"
echo "========================================="
find "$MHLAPRE_HOME" -not -path "*/.git/*" | sort | head -100
echo ""
echo "--- 文件总数 ---"
find "$MHLAPRE_HOME" -not -path "*/.git/*" -type f | wc -l

# ---------- 2. 权重文件扫描 ----------
echo ""
echo "========================================="
echo "2. 权重文件扫描（.pt/.pth/.pkl/.h5/.bin）"
echo "========================================="
for ext in .pt .pth .pkl .h5 .bin .npy .npz; do
    FILES=$(find "$MHLAPRE_HOME" -name "*$ext" 2>/dev/null)
    if [ -n "$FILES" ]; then
        echo "  [FOUND] $ext:"
        echo "$FILES" | while read f; do
            SIZE=$(du -sh "$f" 2>/dev/null | cut -f1)
            echo "    $f  ($SIZE)"
        done
    else
        echo "  [MISS] $ext: 无"
    fi
done

# ---------- 3. example / test / data 目录 ----------
echo ""
echo "========================================="
echo "3. 样例数据扫描（example/test/data/sample）"
echo "========================================="
for dir_name in example examples test tests data sample input; do
    FOUND=$(find "$MHLAPRE_HOME" -type d -iname "$dir_name" 2>/dev/null)
    if [ -n "$FOUND" ]; then
        echo "  [FOUND] $dir_name 目录: $FOUND"
        ls -la "$FOUND" 2>/dev/null | head -20
    fi
done
# 也扫文件级别
echo ""
echo "--- csv/tsv/txt 数据文件 ---"
find "$MHLAPRE_HOME" -not -path "*/.git/*" \( -name "*.csv" -o -name "*.tsv" -o -name "*.txt" \) | head -20

# ---------- 4. Pretreatment.py 精读 ----------
echo ""
echo "========================================="
echo "4. Pretreatment.py — 输入路径/列名/硬编码"
echo "========================================="
PRETREAT="$MHLAPRE_HOME/Pretreatment.py"
if [ -f "$PRETREAT" ]; then
    echo "--- 文件头 50 行 ---"
    head -50 "$PRETREAT"
    echo ""
    echo "--- read_csv / read_excel / open() 调用（输入文件名）---"
    grep -n "read_csv\|read_excel\|open(" "$PRETREAT" || echo "  （无匹配）"
    echo ""
    echo "--- 列名引用（字符串索引/列名关键词）---"
    grep -n '"\(peptide\|seq\|HLA\|allele\|mut\|wt\|label\|immu\)"' "$PRETREAT" -i || true
    grep -n "'\(peptide\|seq\|HLA\|allele\|mut\|wt\|label\|immu\)'" "$PRETREAT" -i || true
    echo ""
    echo "--- 路径/目录硬编码 ---"
    grep -n '"\.\|/\|\.pt\|\.pkl\|model' "$PRETREAT" | head -30 || echo "  （无匹配）"
else
    echo "  [MISS] Pretreatment.py 不存在！路径: $PRETREAT"
fi

# ---------- 5. TransfomerEncoder.py 精读 ----------
echo ""
echo "========================================="
echo "5. TransfomerEncoder.py — 权重加载路径 + 输入来源"
echo "========================================="
# 注意：官方拼写是 TransfomerEncoder（少一个 r），不是 TransformerEncoder
ENCODER="$MHLAPRE_HOME/TransfomerEncoder.py"
if [ ! -f "$ENCODER" ]; then
    # 也尝试 TransformerEncoder.py（有些版本可能改过）
    ENCODER="$MHLAPRE_HOME/TransformerEncoder.py"
fi
if [ -f "$ENCODER" ]; then
    echo "  使用文件: $ENCODER"
    echo "--- 文件头 50 行 ---"
    head -50 "$ENCODER"
    echo ""
    echo "--- torch.load / load_state_dict（权重加载）---"
    grep -n "torch.load\|load_state_dict\|pickle.load" "$ENCODER" || echo "  （无匹配）"
    echo ""
    echo "--- read_csv / open（输入文件）---"
    grep -n "read_csv\|read_excel\|open(" "$ENCODER" || echo "  （无匹配）"
    echo ""
    echo "--- 路径硬编码 ---"
    grep -n '"\.\|/\|model\|weight\|checkpoint' "$ENCODER" -i | head -20 || echo "  （无匹配）"
else
    echo "  [MISS] TransfomerEncoder.py / TransformerEncoder.py 均不存在"
fi

# ---------- 6. TextCNN.py 精读 ----------
echo ""
echo "========================================="
echo "6. TextCNN.py — 输出文件名/列名 + 权重加载"
echo "========================================="
TEXTCNN="$MHLAPRE_HOME/TextCNN.py"
if [ -f "$TEXTCNN" ]; then
    echo "--- 文件头 50 行 ---"
    head -50 "$TEXTCNN"
    echo ""
    echo "--- to_csv / to_excel（输出文件）---"
    grep -n "to_csv\|to_excel\|open.*w\|write" "$TEXTCNN" | head -20 || echo "  （无匹配）"
    echo ""
    echo "--- 输出列名 ---"
    grep -n '"score"\|"label"\|"pred"\|"immu"\|"prob"\|"result"' "$TEXTCNN" -i || true
    grep -n "'score'\|'label'\|'pred'\|'immu'\|'prob'\|'result'" "$TEXTCNN" -i || true
    echo ""
    echo "--- torch.load / load_state_dict ---"
    grep -n "torch.load\|load_state_dict\|pickle.load" "$TEXTCNN" || echo "  （无匹配）"
else
    echo "  [MISS] TextCNN.py 不存在！路径: $TEXTCNN"
fi

# ---------- 7. requirements.txt / setup.py ----------
echo ""
echo "========================================="
echo "7. 依赖文件（requirements.txt / setup.py / environment.yml）"
echo "========================================="
for depfile in requirements.txt setup.py setup.cfg environment.yml pyproject.toml; do
    F="$MHLAPRE_HOME/$depfile"
    if [ -f "$F" ]; then
        echo "--- $depfile ---"
        cat "$F"
        echo ""
    fi
done

# ---------- 8. README ----------
echo ""
echo "========================================="
echo "8. README（全文）"
echo "========================================="
for readme in README.md README.txt README.rst readme.md; do
    F="$MHLAPRE_HOME/$readme"
    if [ -f "$F" ]; then
        echo "--- $readme ---"
        cat "$F"
        echo ""
        break
    fi
done

# ---------- 9. LICENSE 检查 ----------
echo ""
echo "========================================="
echo "9. LICENSE 检查"
echo "========================================="
for lic in LICENSE LICENSE.txt LICENSE.md; do
    F="$MHLAPRE_HOME/$lic"
    if [ -f "$F" ]; then
        echo "  [FOUND] $lic:"
        cat "$F"
    fi
done
# 检查 Python 文件头是否有版权声明
echo ""
echo "--- .py 文件头版权声明 ---"
for pyf in "$MHLAPRE_HOME"/*.py; do
    if [ -f "$pyf" ]; then
        HEAD=$(head -5 "$pyf" 2>/dev/null)
        if echo "$HEAD" | grep -qi "license\|copyright\|author"; then
            echo "  $(basename $pyf):"
            echo "$HEAD"
            echo ""
        fi
    fi
done

# ---------- 总结 ----------
echo ""
echo "========================================="
echo "勘察完成 — 关键 TODO（人工核查）"
echo "========================================="
echo "[ ] Pretreatment.py 的输入文件名/列名（见 Section 4）"
echo "[ ] 权重文件期待路径（TransfomerEncoder.py + TextCNN.py，见 Section 5-6）"
echo "[ ] TextCNN.py 输出列名（见 Section 6）"
echo "[ ] example data 是否存在（见 Section 3）"
echo "[ ] LICENSE 状态（见 Section 9）"
echo ""
echo "建议：将本脚本输出保存为 inspect_report.txt，回填 MHLAPre.md 的 TODO 项"
echo "  bash inspect_mhlapre.sh 2>&1 | tee inspect_report.txt"
echo "===== 勘察脚本结束 ====="
