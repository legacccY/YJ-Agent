#!/usr/bin/env bash
# ===========================================================================
# run_hlathena_hpc.sh — Phase B：在 HPC 用 singularity sif 对 101/102 backbone
#   子肽重推理 HLAthena（presentation proxy 单列）。逐 allele 调 sif，合表 MT+WT。
#
# ⚠️⚠️ HLAthena 预测 MHC-I 提呈（presentation）不是免疫原性（Sarkizova 2020
#   Nat Biotech）。进 benchmark 只作 presentation baseline proxy，单列呈现，
#   绝不与免疫原性工具 apples-to-apples 并列。方向照原：MSi 越高越提呈，无翻转。
#
# 创建: 2026-06-27（quantimmu Phase B / lever=HLAthena presentation proxy）
#
# CLI（实测 SMOKE_PASS，见 TOOLS/HLAthena.md L43）:
#   predict --runID <tag> --rundir /work --peptides /pred/<file> --alleles <tag>
#   → 产 <tag>-predictions.txt（17 列含 MSi_<tag> 提呈分 / prank.MSi / best.MSi_allele）
#   tag 格式 = 去 HLA- 去 * 去 :（HLA-A*02:01 -> A0201），仅 8/9/10/11-mer。
#
# 【主线在 HPC 上跑法（ssh 上去执行，本窗不跑）】
#   1) 把以下 3 个文件上传到同一 HPC 目录（如 $ROOT/phaseB/hlathena_hpc/）：
#        run_hlathena_hpc.sh
#        prep_hlathena_hpc.py
#        parse_hlathena_hpc.py
#   2) 确认 sif + 订正 backbone + GCS 绕过的模型/patch 已就位（见下方 TODO 段）：
#        $ROOT/sif/hlathena.sif
#        $ROOT/phaseB/backbone_101102.csv
#        $MODELS_DIR / $MODELS_PANPAN / $PREDICT_SCRIPT（GCS 死锁绕过，详见 NOTES）
#   3) ssh 后: bash $ROOT/phaseB/hlathena_hpc/run_hlathena_hpc.sh
#      （纯 CPU 小网络，无需 GPU；可 sbatch 包一层）
#
# 产出:
#   $ROOT/phaseB/HLAthena_101102.csv   列 = bb_idx, MT_HLAthena, WT_HLAthena
# ===========================================================================
set -euo pipefail

# ---------- 路径配置（HPC 绝对路径，与其他 deploy 脚本一致）----------
ROOT=/gpfs/work/bio/jiayu2403/quantimmu
SIF=$ROOT/sif/hlathena.sif
BACKBONE=$ROOT/phaseB/backbone_101102.csv
BASE=$ROOT/phaseB
WORK=$BASE/hlathena_work
FINAL_OUT=$BASE/HLAthena_101102.csv

# 本脚本所在目录 = 上传 bundle 目录（prep/parse 都在这）
STAGE="$(cd "$(dirname "$0")" && pwd)"
PREP_PY="$STAGE/prep_hlathena_hpc.py"
PARSE_PY="$STAGE/parse_hlathena_hpc.py"

# ── GCS 死锁绕过的本地模型布局（详见 scripts/hlathena/NOTES.md + TOOLS/HLAthena.md）──
#   镜像 standalone 时从作者 GCS bucket 现拉模型，bundled key 已死 → 卡 retry。
#   解：①匿名下需要的 specific 模型 + pan CV + linear/ecdf RDS（共 ~136M）布置到本地
#       ②patch predict_docker.bash（sed fetch_models="true"->"false" + chmod +x）
#       ③挂载本地模型 + patched 脚本跑（fetch_models=false 不再访问 GCS）。
#   ⚠️ TODO（主线确认）：以下 3 路径在 HPC 的实际位置需主线核实/布置（本地 WSL2 SMOKE
#      用 ~/quantimmu/hlathena/{models,models_panpan,predict_docker.bash}）。若未布置，
#      sif 会卡 GCS retry。可经环境变量覆盖：MODELS_DIR=... MODELS_PANPAN=... PREDICT_SCRIPT=...
MODELS_DIR="${MODELS_DIR:-$ROOT/hlathena/models}"             # specific 模型 -> 挂 /models
MODELS_PANPAN="${MODELS_PANPAN:-$ROOT/hlathena/models_panpan}" # pan 模型     -> 挂 /models_panpan
PREDICT_SCRIPT="${PREDICT_SCRIPT:-$ROOT/hlathena/predict_docker.bash}"  # patched fetch_models=false

# host python（仅 stdlib：csv/json/math，任意 python3 即可）。HLAthena 计算全在 sif 内。
PY="${PY:-python3}"

mkdir -p "$WORK/peps"

echo "================================================================"
echo " HLAthena 101/102 重推理（HPC singularity，presentation proxy）"
echo " sif      : $SIF"
echo " backbone : $BACKBONE"
echo " 产出     : $FINAL_OUT"
echo "================================================================"

# ---------- 前置检查 ----------
[ -f "$SIF" ]      || { echo "[FAIL] sif 不存在: $SIF"; exit 1; }
[ -f "$BACKBONE" ] || { echo "[FAIL] backbone 不存在: $BACKBONE"; exit 1; }
command -v singularity >/dev/null 2>&1 || { echo "[FAIL] singularity 不在 PATH"; exit 1; }
if [ ! -d "$MODELS_DIR" ]; then
    echo "[WARN] MODELS_DIR 不存在: $MODELS_DIR"
    echo "       未布置 GCS 绕过模型，sif 可能卡 GCS retry（见上方 TODO）。"
fi

# ---------- Step 1: prep（backbone -> per-allele 肽文件 + manifest + bb_map）----------
echo ""
echo "[Step 1] prep"
"$PY" "$PREP_PY" \
    --backbone "$BACKBONE" \
    --work "$WORK" \
    --models-dir "$MODELS_DIR"

MANIFEST="$WORK/alleles_manifest.csv"
[ -f "$MANIFEST" ] || { echo "[FAIL] prep 未产 manifest: $MANIFEST"; exit 1; }

# ---------- Step 2: 逐 covered allele 调 sif 跑 HLAthena ----------
# manifest 列: tag,original_hla,covered,n_pep,pep_file —— 只跑 covered==1。
echo ""
echo "[Step 2] singularity exec HLAthena（逐 covered allele）"
# 跳表头，按行读 manifest
tail -n +2 "$MANIFEST" | while IFS=, read -r tag original_hla covered n_pep pep_file; do
    if [ "$covered" != "1" ]; then
        echo "  [skip] $tag（$original_hla）无 specific 模型 → 整组 NaN"
        continue
    fi
    echo "  [run]  $tag（$original_hla）$n_pep pep -> sif"
    # ⚠️ TODO（主线确认 sif 调用方式）：原本地用 `docker run img predict ...`（predict 作
    #    entrypoint 的子命令）。singularity 下若 `predict` 不在容器 PATH，需改成
    #    `singularity run "$SIF" predict ...`（run=走 runscript/entrypoint 分发 predict）。
    #    此处按团队 lead 指定用 `exec`；如报 "predict: command not found" 即切 run。
    #    rundir/peptides/alleles 路径以容器内为准（/work /pred /models）。
    singularity exec \
        -B "$MODELS_DIR":/models:ro \
        -B "$MODELS_PANPAN":/models_panpan:ro \
        -B "$PREDICT_SCRIPT":/hlathena/predict_docker.bash:ro \
        -B "$WORK/peps":/pred:ro \
        -B "$WORK":/work \
        "$SIF" \
        predict \
            --runID "$tag" \
            --rundir /work \
            --peptides "/pred/$tag.txt" \
            --alleles "$tag" \
        2>&1 | tee "$WORK/${tag}_run.log"
done

# ---------- Step 3: parse（所有 <tag>-predictions.txt -> bb_idx 合表）----------
echo ""
echo "[Step 3] parse -> $FINAL_OUT"
"$PY" "$PARSE_PY" --work "$WORK" --out "$FINAL_OUT"

# ---------- 自校验：等位覆盖 + 8-11mer vs 12-14mer NaN 计数 ----------
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
echo "===== HLAthena 101/102 DONE ====="
echo "合表列: $FINAL_OUT  (bb_idx, MT_HLAthena, WT_HLAthena)"
echo "口径: allele-specific MSi presentation 分（越高越提呈，无翻转）"
echo "⚠️ presentation proxy，非免疫原性——下游单列，不与免疫原性工具并列。"
