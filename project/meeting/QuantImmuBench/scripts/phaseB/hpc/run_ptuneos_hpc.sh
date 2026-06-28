#!/usr/bin/env bash
# ===========================================================================
# run_ptuneos_hpc.sh — Phase B：在 XJTLU HPC 经 singularity sif 重推理 pTuneos
#   Pre&RecNeo 识别子模型（model_pro）对 P101/P102 backbone。服务 quantimmu-bench
#   lever=pTuneos。口径与原 86 肽 ELISpot 跑分一致（TOOLS/pTuneos.md + 本地
#   run_ptuneos_101102.py 验过 r=1.0）。合表只填 **MT_pTuneos 一列**（无 WT）。
#
# 创建: 2026-06-27（quantimmu Phase B / pTuneos HPC sif 移植）
#
# ──────────────────────────────────────────────────────────────────────────
# pTuneos 历史最复杂 —— /root 访问坑 + blastdb 口径，两处显式 TODO，见下。
# ──────────────────────────────────────────────────────────────────────────
# 【坑 A · /root 访问】netMHCpan-4.0 在 /root/software/netMHCpan-4.0、模型在
#   /root/pTuneos/train_model —— 都在容器 /root 下（mode 700）。singularity 默认
#   以 host uid 跑 → 进不去 /root（hpc_neoapred.sh 注释实证「绕开 pTuneos 的
#   /root 访问坑」）。本脚本走 `--fakeroot`：sif 是 **rootless build 成功** 的
#   （build_ptuneos.log 全程 rootless{...}）→ 该 HPC 开了无特权 user namespace →
#   `singularity exec --fakeroot` 同机制把容器内 uid 映射成 root，可读 /root。
#   ⚠️ 若 --fakeroot 在此 HPC 被禁 → diag 会立刻报错；届时唯一备选 = 重打包镜像
#      把 /root/software + /root/pTuneos 挪到 /opt（需主线决策，标 TODO-A，别臆造）。
#
# 【坑 B · blastdb 口径】Self_similarity 特征的 homolog 项需 blastp 库。原 86 肽在
#   本地 docker 内 makeblastdb 建 **Ensembl release-97 human.pep.all（110048 序列）**
#   （04_LOG Entry 19，未提交 repo）。HPC 上该库**很可能不存在** → 本脚本 blastdb
#   解析按优先级：① 找现成 blast db(.pin/.phr/.psq) ② 找蛋白组 fasta 现场 makeblastdb
#   ③ 都没有 → 报错 + TODO-B（除非显式 --allow-degraded 走退化：homolog→AAAA，
#   Self_sim 回退 paired_s，**破原 86 肽严格口径**，仅救急）。
#   口径校验：建库后核序列数，!=110048 即告警（非 release-97 → 口径漂移，标 TODO-B）。
#
# ===========================================================================
# 【主线在 HPC 上跑法（ssh 上去执行，本窗不跑）】
#   0) 把这 4 个文件上传到同一 HPC 目录（建议 $BASE/phaseB/ptuneos_hpc/）：
#        run_ptuneos_hpc.sh
#        prep_ptuneos_hpc.py
#        parse_ptuneos_hpc.py
#        ptuneos_pre_recneo.py     <- 从 scripts/ptuneos/ 复制（容器内 Py2.7 wrapper，口径核心）
#   1) 确认 backbone 已在 $BASE/phaseB/backbone_101102.csv（主线已传）
#   2) ssh 后先跑诊断：bash run_ptuneos_hpc.sh diag
#        —— 验 --fakeroot + /root 访问 + netMHCpan + Py2.7 libs + blastdb 现状
#   3) diag 全绿后烟测：bash run_ptuneos_hpc.sh smoke 3
#   4) 烟测 OK 全量：   bash run_ptuneos_hpc.sh run
#      （纯 CPU/RF，无需 GPU；建议 gpu4090 节点多核，--nproc 见下）
#
# 产出: $BASE/phaseB/pTuneos_101102.csv   列 = bb_idx, MT_pTuneos
# ===========================================================================
set -euo pipefail

# ---------- 路径配置（HPC 绝对路径，与其他 deploy 脚本一致）----------
BASE=/gpfs/work/bio/jiayu2403/quantimmu
SIF=$BASE/sif/ptuneos.sif
SSREPO=$BASE/tools_repos/self_similarity      # team-lead 指为 blastdb 源
BACKBONE=$BASE/phaseB/backbone_101102.csv
WORK=$BASE/phaseB/ptuneos_work                 # 绑挂为容器 /work
FINAL_OUT=$BASE/phaseB/pTuneos_101102.csv

# 本脚本所在目录 = 上传 bundle（prep/parse/wrapper 都在这）
STAGE="$(cd "$(dirname "$0")" && pwd)"
PREP_PY="$STAGE/prep_ptuneos_hpc.py"
PARSE_PY="$STAGE/parse_ptuneos_hpc.py"
WRAPPER="$STAGE/ptuneos_pre_recneo.py"

# 容器内固定路径（坑 A：均在 /root，需 --fakeroot）
C_NETMHC=/root/software/netMHCpan-4.0
C_MODELS=/root/pTuneos/train_model
C_BLASTDB=/work/blastdb/peptide               # 物化到 /work 下（已绑挂），容器内统一用此前缀

NPROC="${NPROC:-8}"                            # wrapper calculate_R 并行进程数（gpu4090 48 核可调大）
ALLOW_DEGRADED="${ALLOW_DEGRADED:-0}"          # =1 时允许无 blastdb 退化跑（破口径，仅救急）
SING="singularity exec --fakeroot"             # 主路径：fakeroot 进 /root

# ---------- host 侧 python（仅跑 prep/parse，纯 stdlib）----------
if command -v python3 >/dev/null 2>&1; then
    HOST_PY=python3
else
    source /etc/profile.d/modules.sh 2>/dev/null || true
    module load miniconda3/22.11.1-gcc-8.5.0-l4fo6ta 2>/dev/null || true
    HOST_PY=python
fi

mkdir -p "$WORK"

# ===========================================================================
# 诊断：验 --fakeroot + /root 访问 + 容器内工具/库 + blastdb 现状
# ===========================================================================
do_diag() {
    echo "===== [diag] pTuneos HPC sif 自检 ====="
    [ -f "$SIF" ] || { echo "[diag] FAIL: 缺 sif $SIF"; exit 1; }
    [ -f "$WRAPPER" ] || { echo "[diag] FAIL: 缺 wrapper $WRAPPER（从 scripts/ptuneos/ 复制上来）"; exit 1; }
    [ -f "$BACKBONE" ] || { echo "[diag] FAIL: 缺 backbone $BACKBONE"; exit 1; }

    echo "[diag] 1) --fakeroot + /root 访问 + 容器内工具/库"
    $SING "$SIF" bash -c '
        set -e
        echo "  whoami in container: $(id -un) (uid=$(id -u))"
        echo -n "  netMHCpan bin: "; ls '"$C_NETMHC"'/netMHCpan
        echo -n "  models dir   : "; ls '"$C_MODELS"' | tr "\n" " "; echo
        echo -n "  python2      : "; python --version 2>&1
        python -c "import pandas,numpy,sklearn; from Bio import pairwise2; from sklearn.externals import joblib; print(\"  py2 libs OK: pandas/numpy/sklearn/Bio/joblib\")"
        echo -n "  makeblastdb  : "; command -v makeblastdb || echo "(无 — 建库不可用)"
        echo -n "  blastp       : "; command -v blastp || echo "(无)"
    ' || { echo "[diag] FAIL: 容器内访问失败 —— 大概率 --fakeroot 被禁（坑 A）。见脚本头 TODO-A。"; exit 1; }

    echo "[diag] 2) netMHCpan -p 单肽烟测（验 /root 二进制可跑）"
    printf 'SIINFEKL\n' > "$WORK/_diag.pep"
    $SING -B "$WORK":/work "$SIF" bash -c '
        export PATH='"$C_NETMHC"':$PATH
        netMHCpan -p /work/_diag.pep -a HLA-A02:01 2>&1 | grep -E "SIINFEKL|Distance|Error" | head -5
    ' || echo "[diag] WARN: netMHCpan 烟测非零退出（可能 allele 名/许可，跑 run 时再看）"

    echo "[diag] 3) blastdb 现状探测"
    resolve_blastdb probe || true
    echo "===== [diag] 结束（上面无 FAIL 即可继续 smoke/run）====="
}

# ===========================================================================
# blastdb 解析（坑 B）。两种调用：
#   resolve_blastdb probe   只探测报告，不建库（diag 用）
#   resolve_blastdb build   解析并物化到 $WORK/blastdb/peptide.*（run 用）
# 优先级：① 现成 blast db(.pin) → 拷贝；② 蛋白组 fasta → 容器内 makeblastdb；
#         ③ 都没有 → 退化(--allow-degraded)或报错。
# 口径：建库后核序列数，应 = 110048（release-97 human.pep.all）。
# ===========================================================================
resolve_blastdb() {
    local mode="$1"   # probe | build
    mkdir -p "$WORK/blastdb"

    # 允许主线用环境变量直接指定现成库前缀（host 路径）跳过搜索
    if [ -n "${BLASTDB_PREFIX_HOST:-}" ]; then
        echo "  [blastdb] 用 BLASTDB_PREFIX_HOST=$BLASTDB_PREFIX_HOST"
        if [ "$mode" = "build" ]; then
            cp -f "${BLASTDB_PREFIX_HOST}".p* "$WORK/blastdb/" 2>/dev/null \
                && for ext in pin phr psq; do
                       [ -f "$WORK/blastdb/$(basename "${BLASTDB_PREFIX_HOST}").$ext" ] && \
                       mv -f "$WORK/blastdb/$(basename "${BLASTDB_PREFIX_HOST}").$ext" "$WORK/blastdb/peptide.$ext"
                   done
            echo "  [blastdb] ⚠️ TODO-B：无法从 .pin 验证是否 release-97（110048 seqs），口径待主线确认。"
            return 0
        fi
    fi

    # ① 找现成 blast db（self_similarity repo + $BASE 下）
    local pin
    pin=$(find "$SSREPO" "$BASE/phaseB" "$BASE" -name '*.pin' 2>/dev/null | head -1 || true)
    if [ -n "$pin" ]; then
        local prefix="${pin%.pin}"
        echo "  [blastdb] ① 现成 blast db: $prefix(.pin/.phr/.psq)"
        if [ "$mode" = "build" ]; then
            cp -f "${prefix}".p* "$WORK/blastdb/" 2>/dev/null || true
            for ext in pin phr psq; do
                [ -f "$WORK/blastdb/$(basename "$prefix").$ext" ] && \
                mv -f "$WORK/blastdb/$(basename "$prefix").$ext" "$WORK/blastdb/peptide.$ext"
            done
            echo "  [blastdb] ⚠️ TODO-B：现成库未核 release-97（110048 seqs）口径，主线确认来源。"
        fi
        return 0
    fi

    # ② 找蛋白组 fasta（self_similarity repo 优先，team-lead 指为源）
    local fa
    fa=$(find "$SSREPO" "$BASE" \
            \( -iname 'human.pep.all*.fa' -o -iname '*pep.all*.fasta' -o -iname '*proteome*.fa' \
               -o -iname '*peptide*.fasta' -o -iname 'human.pep.all*' \) 2>/dev/null \
            | grep -viE '\.(pin|phr|psq|gz)$' | head -1 || true)
    if [ -n "$fa" ]; then
        echo "  [blastdb] ② 蛋白组 fasta: $fa"
        if [ "$mode" = "build" ]; then
            cp -f "$fa" "$WORK/blastdb/proteome.fa"
            local nseq
            nseq=$(grep -c '^>' "$WORK/blastdb/proteome.fa" || echo 0)
            echo "  [blastdb] makeblastdb（容器内）-> /work/blastdb/peptide  (源序列数=$nseq)"
            $SING -B "$WORK":/work "$SIF" bash -c \
                'makeblastdb -in /work/blastdb/proteome.fa -dbtype prot -out /work/blastdb/peptide' \
                | tail -3
            if [ "$nseq" != "110048" ]; then
                echo "  [blastdb] ⚠️ TODO-B：源序列数=$nseq != 110048(release-97 human.pep.all)"
                echo "            → 与原 86 肽口径不一致，主线核对 self_similarity 蛋白组版本。"
            else
                echo "  [blastdb] ✅ 序列数=110048，与原 86 肽 release-97 口径一致。"
            fi
        fi
        return 0
    fi

    # ③ 都没有
    echo "  [blastdb] ✗ 未找到现成库/蛋白组 fasta（搜过 $SSREPO 与 $BASE）。"
    if [ "$mode" = "build" ]; then
        if [ "$ALLOW_DEGRADED" = "1" ]; then
            echo "  [blastdb] ⚠️⚠️ --allow-degraded：无 blastdb 退化跑（homolog→AAAA，"
            echo "            Self_sim 回退 paired_s）。**破原 86 肽严格口径**，仅救急。"
            return 2   # 退化标记
        fi
        echo "  [blastdb] FAIL TODO-B：缺 blastdb 且未开 --allow-degraded。主线二选一："
        echo "            (a) 在 HPC 备好 release-97 human.pep.all 后置 BLASTDB_PREFIX_HOST 或放 self_similarity；"
        echo "            (b) ALLOW_DEGRADED=1 退化跑（破口径，需主线知情）。"
        exit 1
    fi
    return 0
}

# ===========================================================================
# 全量/烟测跑
# ===========================================================================
do_run() {
    local smoke_n="${1:-0}"
    local in_tsv="$WORK/ptuneos_input_101102.tsv"
    local out_tsv="$WORK/ptuneos_output_101102.tsv"
    local map_csv="$WORK/ptuneos_map_101102.csv"
    [ "$smoke_n" -gt 0 ] && { in_tsv="$WORK/ptuneos_input_smoke.tsv"; out_tsv="$WORK/ptuneos_output_smoke.tsv"; }

    echo "[Step 1] prep（backbone -> 容器输入 TSV + bb_idx 映射）"
    "$HOST_PY" "$PREP_PY" --backbone "$BACKBONE" \
        --input-tsv "$in_tsv" --map-csv "$map_csv" \
        $( [ "$smoke_n" -gt 0 ] && echo "--smoke $smoke_n" )

    echo "[Step 2] blastdb 解析（坑 B）"
    local degraded=0
    set +e; resolve_blastdb build; local rc=$?; set -e
    [ "$rc" = "2" ] && degraded=1
    local blastdb_arg="$C_BLASTDB"
    [ "$degraded" = "1" ] && blastdb_arg="/work/blastdb/__none__"   # 故意不存在 → wrapper 全回退 AAAA

    echo "[Step 3] 容器跑 wrapper（singularity --fakeroot，Py2.7 InVivoModelAndScore）"
    cp -f "$WRAPPER" "$WORK/ptuneos_pre_recneo.py"   # 进容器 /work/ptuneos_pre_recneo.py
    mkdir -p "$WORK/tmp"
    $SING -B "$WORK":/work "$SIF" bash -c '
        set -e
        export PATH='"$C_NETMHC"':$PATH
        export TMPDIR=/work/tmp
        python /work/ptuneos_pre_recneo.py \
            --input  /work/'"$(basename "$in_tsv")"' \
            --output /work/'"$(basename "$out_tsv")"' \
            --models '"$C_MODELS"' \
            --blastdb '"$blastdb_arg"' \
            --nproc '"$NPROC"'
    '
    [ -f "$out_tsv" ] || { echo "[Step 3] FAIL: 容器未产出 $out_tsv（核 fakeroot/挂载/stderr）"; exit 1; }

    if [ "$smoke_n" -gt 0 ]; then
        echo "[smoke] 容器输出前几行 model_pro:"
        "$HOST_PY" - "$out_tsv" <<'PYEOF'
import csv, sys, math
with open(sys.argv[1], newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f, delimiter="\t"))
vals = []
for r in rows:
    try: vals.append(float(r.get("model_pro", "")))
    except (TypeError, ValueError): pass
vals = [v for v in vals if not math.isnan(v)]
rng = (min(vals), max(vals)) if vals else (float("nan"), float("nan"))
print("[smoke] 送 %d 行，得 %d 有效 model_pro，range [%.6f, %.6f]（0-1）。未产合表。"
      % (len(rows), len(vals), rng[0], rng[1]))
PYEOF
        return 0
    fi

    echo "[Step 4] parse（model_pro -> bb_idx 合表列）-> $FINAL_OUT"
    "$HOST_PY" "$PARSE_PY" --map-csv "$map_csv" --output-tsv "$out_tsv" --out "$FINAL_OUT"

    echo ""
    echo "===== pTuneos 101/102 DONE ====="
    echo "容器输出: $out_tsv"
    echo "合表列  : $FINAL_OUT  (bb_idx, MT_pTuneos)"
    echo "口径    : Pre&RecNeo model_pro（5 特征 RF），方向越高越免疫原；$( [ "$degraded" = "1" ] && echo '⚠️退化无blastdb(破口径)' || echo 'blastdb 已解析' )"
}

# ===========================================================================
# 入口
# ===========================================================================
cmd="${1:-run}"
case "$cmd" in
    diag)  do_diag ;;
    smoke) do_run "${2:-3}" ;;
    run)   do_run 0 ;;
    *) echo "用法: bash run_ptuneos_hpc.sh [diag|smoke N|run]"; exit 1 ;;
esac
