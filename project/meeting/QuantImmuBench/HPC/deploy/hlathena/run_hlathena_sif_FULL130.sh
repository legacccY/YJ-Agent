#!/usr/bin/env bash
# ===========================================================================
# run_hlathena_sif_FULL130.sh — QuantImmuBench 覆盖修复（lever=HLAthena presentation proxy）
#   在【全 130 肽】backbone 上用 HPC singularity sif **内置 predict** 重跑 HLAthena，
#   补齐 allele 覆盖（原 121 -> ~130）。逐 allele 调 sif，合表 MT+WT。
#
# ⚠️⚠️ HLAthena 预测 MHC-I 提呈（presentation）不是免疫原性（Sarkizova 2020
#   Nat Biotech）。进 benchmark 只作 presentation baseline proxy，单列呈现，
#   绝不与免疫原性工具 apples-to-apples 并列。方向照原：MSi 越高越提呈，无翻转。
#
# 创建: 2026-07-03（QuantImmuBench 覆盖修复 / coder）
#
# ───────────────────────────────────────────────────────────────────────────
# ★ 与旧 run_hlathena_hpc.sh 的关键区别（本脚本修复的根因）★
#   旧 driver 失败根因 = 它去挂载一个【不存在的外部 predict_docker.bash】，且靠
#   patch 该 wrapper 的 fetch_models=false 关 GCS。经主线核实：
#     · sif 已内置 /usr/bin/predict（不需外部 wrapper 脚本）
#     · 模型已在 HPC：$ROOT/hla_arr/models（逐 allele，如 A0101/）+ $ROOT/hla_arr/models_panpan
#   ⇒ 本脚本 = 直接调 sif 内置 predict + 把本地模型挂进容器 /models、/models_panpan，
#     【不再挂 predict_docker.bash、不访问 GCS】。
#
# ★ 关 GCS（不联网拉模型）的做法 ★
#   1) 把本地 specific 模型挂到容器 /models（predict 从此读，找得到就不 fetch）。
#   2) 把 pan 模型挂到 /models_panpan。
#   3) export SINGULARITYENV_FETCH_MODELS=false —— 老 wrapper 里控制拉取的变量名是
#      fetch_models；用 SINGULARITYENV_ 前缀把它以 env 注入容器双保险（兼容各版 singularity）。
#   ⚠️ 若 predict 仍尝试连 GCS（日志见 retry_util.py Retrying request）：说明 sif 内置
#      predict 读的模型路径 / 关 fetch 的开关名与假设不同 → 主线用
#        singularity exec $SIF cat /usr/bin/predict
#      看它期望的模型目录与 fetch_models 变量，对应改 -B 目标路径 / env 名（本处标 TODO）。
#
# ───────────────────────────────────────────────────────────────────────────
# CLI（实测 SMOKE_PASS，见 TOOLS/HLAthena.md L43）:
#   predict --runID <tag> --rundir /work --peptides <pepfile> --alleles <tag>
#   → 产 <tag>-predictions.txt（17 列含 MSi_<tag> 提呈分 / prank.MSi / best.MSi_allele）
#   tag 格式 = 去 HLA- 去 * 去 :（HLA-A*02:01 -> A0201），仅 8/9/10/11-mer。
#
# 【主线在 HPC 上跑法（ssh 上去执行，本窗不跑）】
#   1) 把以下 4 个文件上传到同一 HPC 目录（如 $ROOT/scripts/out_official/coverage_fix/）：
#        run_hlathena_sif_FULL130.sh
#        prep_hlathena_hpc.py          （复用 scripts/phaseB/hpc/ 下同名，不改）
#        parse_hlathena_hpc.py         （复用 scripts/phaseB/hpc/ 下同名，不改）
#        hlathena_input_FULL130.csv    （全 130 肽 backbone，3610 行）
#   2) 确认 sif + 本地模型就位：
#        $ROOT/sif/hlathena.sif
#        $ROOT/hla_arr/models          （逐 allele specific 模型，覆盖判定真源）
#        $ROOT/hla_arr/models_panpan   （pan 模型）
#   3) ssh 后: bash <上传目录>/run_hlathena_sif_FULL130.sh
#      （纯 CPU 小网络，无需 GPU；可 sbatch 包一层）
#
# 产出:
#   $ROOT/scripts/out_official/coverage_fix/hlathena_raw_FULL130.csv
#     列 = bb_idx, MT_HLAthena, WT_HLAthena（与 parse_hlathena_hpc.py 输出对齐）
# ===========================================================================
# 注意：不用 set -e —— 单 allele 失败不杀整批（计数后继续）。仅 set -u/pipefail。
set -uo pipefail

# ---------- 路径配置（HPC 绝对路径）----------
ROOT=/gpfs/work/bio/jiayu2403/quantimmu
SIF="$ROOT/sif/hlathena.sif"
OUTDIR="$ROOT/scripts/out_official/coverage_fix"
WORK="$OUTDIR/hlathena_work"
FINAL_OUT="$OUTDIR/hlathena_raw_FULL130.csv"

# 本脚本所在目录 = 上传 bundle 目录（prep/parse/输入 csv 与本脚本同放）
STAGE="$(cd "$(dirname "$0")" && pwd)"
PREP_PY="$STAGE/prep_hlathena_hpc.py"
PARSE_PY="$STAGE/parse_hlathena_hpc.py"
BACKBONE="${BACKBONE:-$STAGE/hlathena_input_FULL130.csv}"   # 可经 env 覆盖

# ── 本地模型（关 GCS 的关键：挂进容器 /models、/models_panpan）──
MODELS_DIR="${MODELS_DIR:-$ROOT/hla_arr/models}"              # specific 模型 -> /models（覆盖判定真源）
MODELS_PANPAN="${MODELS_PANPAN:-$ROOT/hla_arr/models_panpan}"  # pan 模型     -> /models_panpan

# host python（仅 stdlib：csv/json/math，任意 python3 即可）。HLAthena 计算全在 sif 内。
PY="${PY:-python3}"

mkdir -p "$WORK/peps" "$OUTDIR"

echo "================================================================"
echo " HLAthena 全130肽 覆盖修复重推理（HPC singularity 内置 predict）"
echo " sif      : $SIF"
echo " backbone : $BACKBONE"
echo " models   : $MODELS_DIR (-> /models)"
echo " panpan   : $MODELS_PANPAN (-> /models_panpan)"
echo " 产出     : $FINAL_OUT"
echo "================================================================"

# ---------- 前置检查 ----------
[ -f "$SIF" ]      || { echo "[FAIL] sif 不存在: $SIF"; exit 1; }
[ -f "$BACKBONE" ] || { echo "[FAIL] backbone 不存在: $BACKBONE"; exit 1; }
[ -f "$PREP_PY" ]  || { echo "[FAIL] prep 脚本不存在（需与本脚本同目录）: $PREP_PY"; exit 1; }
[ -f "$PARSE_PY" ] || { echo "[FAIL] parse 脚本不存在（需与本脚本同目录）: $PARSE_PY"; exit 1; }
command -v singularity >/dev/null 2>&1 || { echo "[FAIL] singularity 不在 PATH"; exit 1; }
if [ ! -d "$MODELS_DIR" ]; then
    echo "[WARN] MODELS_DIR 不存在: $MODELS_DIR"
    echo "       无本地模型，predict 可能卡 GCS retry（见头注「关 GCS」段）。"
fi

# ── 关 GCS：以 env 注入容器（老 wrapper 变量名 fetch_models），兼容各版 singularity ──
export SINGULARITYENV_FETCH_MODELS=false

# ---------- Step 1: prep（backbone -> per-allele 肽文件 + manifest + bb_map）----------
echo ""
echo "[Step 1] prep（覆盖判定 = --models-dir 下逐 allele specific 模型是否存在）"
"$PY" "$PREP_PY" \
    --backbone "$BACKBONE" \
    --work "$WORK" \
    --models-dir "$MODELS_DIR"

MANIFEST="$WORK/alleles_manifest.csv"
[ -f "$MANIFEST" ] || { echo "[FAIL] prep 未产 manifest: $MANIFEST"; exit 1; }

# ---------- Step 2: 逐 covered allele 调 sif 内置 predict ----------
# manifest 列: tag,original_hla,covered,n_pep,pep_file —— 只跑 covered==1。
# prep 把肽写到 $WORK/peps/<tag>.txt；绑定 $WORK:/work 后容器内路径 = /work/peps/<tag>.txt。
echo ""
echo "[Step 2] singularity exec 内置 predict（逐 covered allele；单失败不杀整批）"

# panpan 可选绑定（存在才挂）
PANPAN_BIND=()
[ -d "$MODELS_PANPAN" ] && PANPAN_BIND=(-B "$MODELS_PANPAN:/models_panpan:ro")

n_run=0; n_ok=0; n_fail=0; n_skip=0
# 用进程替换而非管道，保证计数器在主 shell 生效（不进 subshell）
while IFS=, read -r tag original_hla covered n_pep pep_file; do
    if [ "$covered" != "1" ]; then
        echo "  [skip] $tag（$original_hla）无 specific 模型 -> 整组 NaN"
        n_skip=$((n_skip+1))
        continue
    fi
    n_run=$((n_run+1))
    echo "  [run]  $tag（$original_hla）$n_pep pep -> sif 内置 predict"
    # ★ 确切命令：内置 predict + 挂本地模型，不挂 predict_docker.bash、不访问 GCS ★
    if singularity exec \
            -B "$MODELS_DIR:/models:ro" \
            "${PANPAN_BIND[@]}" \
            -B "$WORK:/work" \
            "$SIF" \
            predict \
                --runID "$tag" \
                --rundir /work \
                --peptides "/work/peps/$tag.txt" \
                --alleles "$tag" \
            > "$WORK/${tag}_run.log" 2>&1; then
        if [ -f "$WORK/${tag}-predictions.txt" ]; then
            echo "         [ok] $WORK/${tag}-predictions.txt"
            n_ok=$((n_ok+1))
        else
            echo "         [FAIL] predict 退出 0 但无 ${tag}-predictions.txt（见 ${tag}_run.log）"
            n_fail=$((n_fail+1))
        fi
    else
        echo "         [FAIL] predict 非 0 退出（见 $WORK/${tag}_run.log；若含 GCS retry 见头注）"
        n_fail=$((n_fail+1))
    fi
done < <(tail -n +2 "$MANIFEST")

echo ""
echo "[Step 2] covered 跑=$n_run（ok=$n_ok / fail=$n_fail）| skip(未覆盖)=$n_skip"

# ---------- Step 3: parse（所有 <tag>-predictions.txt -> bb_idx 合表）----------
echo ""
echo "[Step 3] parse -> $FINAL_OUT"
"$PY" "$PARSE_PY" --work "$WORK" --out "$FINAL_OUT"

# ---------- 自校验 ----------
echo ""
echo "[QC] manifest 覆盖一览:"
cat "$MANIFEST"
echo ""
echo "[QC] 合表非空计数:"
"$PY" - "$FINAL_OUT" <<'PYEOF'
import csv, sys
path = sys.argv[1]
n = mt = wt = 0
with open(path, newline="", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        n += 1
        mt += (r["MT_HLAthena"] or "").strip() != ""
        wt += (r["WT_HLAthena"] or "").strip() != ""
print(f"  行={n} | MT_HLAthena 非NaN={mt} | WT_HLAthena 非NaN={wt}")
print("  ⚠️ NaN = 无 specific 模型 / 12-14mer / 非标准 AA（如实，未假填）")
PYEOF

echo ""
echo "===== HLAthena 全130肽 覆盖修复 DONE ====="
echo "合表: $FINAL_OUT  (bb_idx, MT_HLAthena, WT_HLAthena)"
echo "口径: allele-specific MSi presentation 分（越高越提呈，无翻转）"
echo "⚠️ presentation proxy，非免疫原性——下游单列，不与免疫原性工具并列。"
