#!/usr/bin/env bash
# =============================================================================
# run_dtu_nettepi_official.sh — NetTepi-1.0 on NEW official inputs (HPC).
#   Service: quantimmu-bench / node tools_dtu (W1).
# =============================================================================
# NetTepi 经 python2.7 包装器 netTepi.py 跑（tcsh 二进制直跑报 setenv 错）。
#   python2.7 由 conda env qib_py27 提供（W1 smoke 确认）。
# 仅支持 13 等位（ext_tools/netTepi-1.0/alleles.lst）；我们 26 等位里命中
#   6 个（A01:01/A02:01/A03:01/B07:02/B27:05/B40:01），其余诚实 NaN（工具边界）。
# 复用 dtu_netmhcpan_inputs 的 per-allele .pep（全 9mer）。
# 输出 <allele_safe>_nettepi.txt → parse_nettepi_official.py 取 Comb 列。
#
# 直跑: bash run_dtu_nettepi_official.sh
# =============================================================================
set -u
ROOT=/gpfs/work/bio/jiayu2403/quantimmu
NETTEPI=${ROOT}/ext_tools/netTepi-1.0/netTepi.py
ALLELES_LST=${ROOT}/ext_tools/netTepi-1.0/alleles.lst
IN=${ROOT}/ds1/dtu_netmhcpan_inputs
OUT=${IN}/nettepi_out
ALLELE_MAP=${IN}/allele_map.tsv

# conda env qib_py27 → python2.7 in PATH
module load miniconda3/22.11.1-gcc-8.5.0-l4fo6ta 2>/dev/null
source "$(conda info --base)/etc/profile.d/conda.sh" 2>/dev/null
conda activate "${ROOT}/envs/qib_py27" || { echo "[FATAL] activate qib_py27 失败"; exit 1; }

# python2.7 路径锁定（qib_py27），先抓再改 PATH，防 qib_perl 的 python 抢
PY27="$(which python2.7)"

# netMHCcons 的 perl 脚本需 Env.pm；系统 perl @INC 缺，qib_perl 的 perl 含核心 Env.pm
# → 把 qib_perl/bin 前插 PATH，使 netMHCcons/netMHCstabpan tcsh wrapper 调到对的 perl。
export PATH="${ROOT}/envs/qib_perl/bin:${PATH}"
export PERL5LIB="${ROOT}/envs/qib_perl/lib/perl5/core_perl:${PERL5LIB:-}"

# netTepi.py 必需 env（tcsh wrapper netTepi 里硬设的同名变量，bash 里 export）
export NTHOME="${ROOT}/ext_tools/netTepi-1.0"
export NETMHCCONS_ENV="${ROOT}/ext_tools/netMHCcons-1.1/netMHCcons"
export NETMHCSTAB_ENV="${ROOT}/ext_tools/netMHCstabpan-1.0/netMHCstabpan"
export TMPDIR="${ROOT}/nettepi_tmp"
export PYTHON_ENV="${PY27}"
mkdir -p "${TMPDIR}"

mkdir -p "${OUT}"
[ -f "$ALLELE_MAP" ] || { echo "[FATAL] allele_map.tsv missing"; exit 1; }
[ -f "$ALLELES_LST" ] || { echo "[FATAL] alleles.lst missing"; exit 1; }

# NetTepi 支持等位集：清洗到临时文件（去空格+CR，规避 conda 环境下变量塌行 bug），直接 grep 文件比对
ALLELES_CLEAN="${TMPDIR}/alleles_clean.lst"
tr -d ' \r' < "$ALLELES_LST" > "$ALLELES_CLEAN"

n_ok=0; n_skip=0; n_fail=0
while IFS=$'\t' read -r safe nmhc; do
    [ -z "$safe" ] && continue
    nmhc="${nmhc%$'\r'}"; safe="${safe%$'\r'}"   # strip 可能的 CR
    # nmhc e.g. HLA-A02:01 ; alleles.lst 同格式
    if ! grep -qxF "$nmhc" "$ALLELES_CLEAN"; then
        echo "[SKIP] $nmhc 不在 NetTepi 13 等位 → NaN"; n_skip=$((n_skip+1)); continue
    fi
    pep="${IN}/${safe}.pep"
    [ -s "$pep" ] || { echo "[SKIP] $safe no pep"; n_skip=$((n_skip+1)); continue; }
    out="${OUT}/${safe}_nettepi.txt"
    if "$PY27" "$NETTEPI" -a "$nmhc" -p "$pep" -l 9 > "$out" 2>"${out}.err"; then
        echo "[OK ] $nmhc → $(basename $out)"; n_ok=$((n_ok+1))
    else
        echo "[FAIL] $nmhc (见 ${out}.err)"; n_fail=$((n_fail+1))
    fi
done < "$ALLELE_MAP"

echo "[DONE] NetTepi ok=$n_ok skip=$n_skip fail=$n_fail  OUT=${OUT}"
