#!/usr/bin/env bash
# =============================================================================
# run_repitope_local.sh — 本机 Windows R 跑 Repitope 给 551 官方唯一肽打分
# =============================================================================
# 主线串行执行（agent 只写不跑）。Git Bash 下：
#   bash scripts/hpc_official/run_repitope_local.sh [cores]
#
# ★ 复用 2026-06-26 已跑通的 proven pipeline，不重造 ★
#   - runner   = HPC/deploy/repitope/run_repitope.R（13.8KB，proven：已产 7437 肽分）
#   - 数据集   = HPC/deploy/repitope/mendeley_data/（122MB frag + 5.1MB featureDF，已下好）
#   - 仅新增：把官方 551 肽（scripts/out_official/newtools/uniq_pep.csv）做成 Peptide 列输入
#
# 流程：prep（uniq_pep.csv→Peptide列输入）→ proven run_repitope.R → Repitope_scores.csv
# 之后跑：python scripts/hpc_official/parse_repitope_official.py
#
# ⚠️ 内存：proven run_repitope.R 行 39 自带 options(java.parameters=c("-Xmx60G","-Xms4G"))，
#    2026-06-26 在本机 R 4.3.3 已成功跑完 7437 肽（repitope_raw.csv 为证）。-Xmx 是上限非
#    预留，64位 JVM 懒提交，无 OOM。故【不改 proven 脚本内存】。如确需 8G：改该文件行 39。
# ⚠️ CPU+Java 活，非 GPU → 不走 gpu_slot.py。551 肽 << 7437，预计 Features 几~十几分钟，
#    + ERT 训练 5-20 分（MHCI_Human ~7000 肽，与肽数无关）+ 预测数分钟，总约 15-40 分钟。
# =============================================================================
set -euo pipefail

REPO="D:/YJ-Agent/project/meeting/QuantImmuBench"
RSCRIPT="/e/R-4.3.3/bin/Rscript.exe"
RUNNER="$REPO/HPC/deploy/repitope/run_repitope.R"          # proven
DATA="$REPO/HPC/deploy/repitope/mendeley_data"
FRAG="$DATA/FragmentLibrary_TCRSet_Public_RepitopeV3.fst"
FEAT="$DATA/FeatureDF_MHCI_Weighted.10000_RepitopeV3.fst"

UNIQ="$REPO/scripts/out_official/newtools/uniq_pep.csv"    # 551 官方唯一肽（列 peptide,source）
OUTDIR="$REPO/scripts/out_official/repitope_out"
INPUT="$OUTDIR/repitope_official_input.csv"                # 生成：列 Peptide
OUT="$OUTDIR/Repitope_scores.csv"                          # parse 默认读这个
TMP="$OUTDIR/tmp"
CORES="${1:-4}"

echo "==================================================================="
echo "[run_repitope_local] RSCRIPT=$RSCRIPT"
echo "[run_repitope_local] RUNNER=$RUNNER (proven)"
echo "[run_repitope_local] FRAG=$FRAG"
echo "[run_repitope_local] FEAT=$FEAT"
echo "[run_repitope_local] UNIQ=$UNIQ → INPUT=$INPUT"
echo "[run_repitope_local] OUT=$OUT  cores=$CORES"
echo "==================================================================="

# 前置检查（缺则停，不静默造数）
for f in "$RUNNER" "$FRAG" "$FEAT" "$UNIQ"; do
  [[ -s "$f" ]] || { echo "[FAIL] 缺文件: $f"; exit 1; }
done
mkdir -p "$OUTDIR" "$TMP"

# ── prep：uniq_pep.csv (列 peptide) → Peptide 列输入，仅留 8-11mer 标准氨基酸肽 ──
echo "[run_repitope_local] prep 官方输入 ..."
python - "$UNIQ" "$INPUT" << 'PYEOF'
import csv, sys
src, dst = sys.argv[1], sys.argv[2]
STD = set("ACDEFGHIKLMNPQRSTVWY")
seen, peps = set(), []
with open(src, newline="", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        p = (r.get("peptide") or "").strip().upper()
        if not p or p in seen: continue
        if not (8 <= len(p) <= 11): continue          # MHC-I 8-11mer
        if any(c not in STD for c in p): continue       # 非标准氨基酸 → 跳过(parse 阶段回 NaN)
        seen.add(p); peps.append(p)
with open(dst, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["Peptide"])
    for p in peps: w.writerow([p])
print(f"[prep] {len(peps)} 唯一肽 (8-11mer, 标准AA) → {dst}")
PYEOF

# ── 跑 proven runner（全量，不 smoke）──────────────────────────────────────
echo "[run_repitope_local] 跑 proven run_repitope.R（CPU+Java，约 15-40 分钟）..."
"$RSCRIPT" "$RUNNER" \
  --input      "$INPUT" \
  --frag-lib   "$FRAG" \
  --feature-df "$FEAT" \
  --out        "$OUT" \
  --cores      "$CORES" \
  --tmp-dir    "$TMP"

echo "==================================================================="
echo "[run_repitope_local] 完成。产出: $OUT"
echo "[run_repitope_local] 下一步: python scripts/hpc_official/parse_repitope_official.py"
echo "==================================================================="
