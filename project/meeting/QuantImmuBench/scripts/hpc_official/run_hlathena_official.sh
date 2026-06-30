#!/usr/bin/env bash
# run_hlathena_official.sh — HLAthena MSi 官方数据补跑（HPC singularity）。
# 服务 quantimmu-bench §Phase0 W2-presml。lever=HLAthena presentation proxy 单列。
# ⚠️ presentation proxy（非免疫原性），横评里单列 baseline。
#
# 复用已验证的老管道 invocation（run_hla_chunk.sh）：
#   singularity exec --writable-tmpfs --bind models:/models --bind models_panpan:/models_panpan
#     --bind patched.bash:/pred/predict_docker.bash --bind rundir:/work
#     hlathena.sif predict --runID r --rundir /work --peptides /work/p.txt --alleles <PRIME_FMT>
#   p.txt: 首行 "pep" + 每行一肽（单长度！）；输出 r-predictions.txt TSV 含列 MSi_<allele>。
#
# 输入：official_inputs/out_official/newtools/uniq_pep_hla.csv (peptide,HLA_Allele[带星],source)
#   —— 同其它 presml 工具的 universe，保证 strict 对齐 backbone。
# 输出：official_inputs/out_official/hlathena_raw.csv (peptide,HLA_Allele[带星],MSi)
#   缺 ecdf 模型的等位(B2706 只有 B2705)/超 8-11mer 的肽 → 不喂 → parse 诚实 NaN。
set -uo pipefail
BASE=/gpfs/work/bio/jiayu2403/quantimmu
SIF=$BASE/sif/hlathena.sif
A=$BASE/hla_arr
PATCHED=$BASE/hla_predict_patched.bash
UNIQ=$BASE/official_inputs/out_official/newtools/uniq_pep_hla.csv
WORK=$BASE/official_inputs/hlathena_official
JOBS=$WORK/jobs
OUT=$WORK/out
RAW=$BASE/official_inputs/out_official/hlathena_raw.csv
CHUNK=200
mkdir -p "$JOBS" "$OUT"

# patched bash（fetch_models=false，复用 /models 本地 ecdf）
[ -s "$PATCHED" ] || { singularity exec "$SIF" cat /pred/predict_docker.bash > "$PATCHED"; sed -i 's/fetch_models="true"/fetch_models="false"/' "$PATCHED"; chmod +x "$PATCHED"; }

# ecdf 可用等位（PRIME 格式），来自 hla_arr/models/ecdf/（字符串避免 mapfile/进程替换在非交互 shell 失效）
ECDF=" $(ls "$A/models/ecdf/" 2>/dev/null | sed -E 's/ecdf_panpan_([A-Z0-9]+)_.*/\1/' | sort -u | tr '\n' ' ') "
echo "[hlathena] ecdf alleles:$ECDF"

# 从 uniq_pep_hla.csv 建 (prime_allele,length) 肽列表（去 header，单长度，valid AA，8-11mer）
echo "[hlathena] building per-(allele,length) lists $(date)"
tail -n +2 "$UNIQ" | while IFS=, read -r pep hla src; do
  # star→PRIME: HLA-A*01:01 → A0101（bash 参数展开，无 subshell）
  pa="${hla//HLA-/}"; pa="${pa//\*/}"; pa="${pa//:/}"
  # 仅 ecdf 覆盖等位
  case "$ECDF" in *" $pa "*) ;; *) continue;; esac
  pep="${pep//$'\r'/}"
  L=${#pep}
  [ "$L" -ge 8 ] && [ "$L" -le 11 ] || continue
  echo "$pep" >> "$JOBS/_lst_${pa}_${L}"
done
# 去重 + chunk split
for f in "$JOBS"/_lst_*; do
  [ -s "$f" ] || continue
  b=$(basename "$f"); b=${b#_lst_}    # <pa>_<L>
  sort -u "$f" | grep -E '^[ACDEFGHIKLMNPQRSTVWY]+$' > "$JOBS/_u_${b}"
  split -l "$CHUNK" -d -a 3 "$JOBS/_u_${b}" "$JOBS/${b}_"
  rm -f "$f" "$JOBS/_u_${b}"
done
ls "$JOBS"/*_*_* 2>/dev/null | grep -E '_[0-9]{3}$' > "$JOBS/list.txt"
echo "[hlathena] $(wc -l < "$JOBS/list.txt") chunks"

run_chunk() {
  local cf="$1"; local base=$(basename "$cf")   # <pa>_<L>_<nnn>
  local pa="${base%%_*}"
  local o="$OUT/${base}.msi"
  [ -s "$o" ] && return
  local rdir="$OUT/run_${base}"; mkdir -p "$rdir"
  { echo pep; cat "$cf"; } > "$rdir/p.txt"
  timeout 3000 singularity exec --writable-tmpfs \
    --bind "$A/models":/models --bind "$A/models_panpan":/models_panpan \
    --bind "$PATCHED":/pred/predict_docker.bash --bind "$rdir":/work \
    "$SIF" predict --runID r --rundir /work --peptides /work/p.txt --alleles "$pa" > "$rdir/log.txt" 2>&1
  local pred="$rdir/r-predictions.txt"
  if [ -s "$pred" ]; then
    python3 -c "
import csv,sys
rows=list(csv.DictReader(open('$pred'),delimiter='\t'))
col='MSi_$pa'
with open('$o','w') as fo:
    for r in rows: fo.write(r.get('pep','')+'\t'+str(r.get(col,r.get('best.MSi','')))+'\n')
"
  fi
  rm -rf "$rdir"
}
export -f run_chunk; export BASE SIF A OUT JOBS PATCHED

echo "[hlathena] running chunks $(date)"
xargs -P 10 -d '\n' -a "$JOBS/list.txt" -I{} bash -c 'run_chunk "{}"'

echo "[hlathena] merging → raw $(date)"
python3 - <<PY
import csv,glob,os,re
BASE="$BASE"; OUT="$OUT"; UNIQ="$UNIQ"; RAW="$RAW"
# prime→star 反查：用 uniq 里的 (prime,star) 对照
prime2star={}
with open(UNIQ) as f:
    rd=csv.reader(f); next(rd)
    for row in rd:
        if len(row)<2: continue
        pep,hla=row[0],row[1]
        pa=hla.replace("HLA-","").replace("*","").replace(":","")
        prime2star[pa]=hla
# 收集 MSi: key (pep, prime_allele)
recs=[]
for msi in glob.glob(os.path.join(OUT,"*.msi")):
    b=os.path.basename(msi)[:-4]              # <pa>_<L>_<nnn>
    pa=b.split("_")[0]
    star=prime2star.get(pa)
    if not star: continue
    for line in open(msi):
        line=line.rstrip("\n")
        if not line: continue
        parts=line.split("\t")
        if len(parts)<2: continue
        pep,msv=parts[0],parts[1]
        if msv in("","None","nan"): continue
        recs.append((pep,star,msv))
with open(RAW,"w",newline="") as fo:
    w=csv.writer(fo); w.writerow(["peptide","HLA_Allele","MSi"])
    seen=set()
    for pep,star,msv in recs:
        k=(pep,star)
        if k in seen: continue
        seen.add(k); w.writerow([pep,star,msv])
print("[RAW]",RAW,"rows",len(seen))
PY
echo "[HLATHENA_OFFICIAL_DONE] $(date)"
wc -l "$RAW" 2>/dev/null
