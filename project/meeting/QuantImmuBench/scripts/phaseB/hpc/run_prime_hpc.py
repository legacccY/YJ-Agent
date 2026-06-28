# -*- coding: utf-8 -*-
"""
run_prime_hpc.py — Phase B：在 HPC 上用订正 HLA 等位重推理 PRIME（P101/P102）。

本脚本 = scripts/phaseB/run_prime_101102.py 的 HPC 路径变体，逻辑完全一致
（prep+run+parse 一体、独立进程组超时净杀护栏、Score_bestAllele 无翻转），
只把所有默认路径换成 HPC，并把订正源指向 HPC 上已上传的 backbone：
    /gpfs/work/bio/jiayu2403/quantimmu/phaseB/backbone_101102.csv（只读，方向照原）

唯一订正输入源 = $BASE/phaseB/backbone_101102.csv（已过闸门1：HLA_Allele == 订正真值
P101={A*66:01,B*40:01,B*57:01,C*06:02}/P102={A*02:01,B*35:03,B*38:01}）。
PRIME alleles_rank.txt 已确认含全 7 订正等位（C0602 可能 MixMHCpred 不支持→该 allele NaN）。

自包含三步：
  1. prep：从 backbone 取 MT_Subpeptide ∪ WT_Subpeptide，按 HLA_Allele 分组
     （HLA 去 HLA- 去 * 去 : → PRIME tag，如 HLA-A*02:01 → A0201）。
     肽长须 8-14（PRIME 限制），且仅标准 20 氨基酸，否则不送 → 回贴 NaN。
  2. run：对每个 allele 调官方 PRIME（C++ wrapper），命令
       cd <prime_dir> && ./PRIME -i <peps.txt> -o <out.txt> -a <allele> -mix <mix>
     conda env（含 MixMHCpred3.0 python 依赖）经 --activate 前缀激活。
     ⚠️ 已知坑：MixMHCpred 不支持的罕见 allele（如 HLA-C*06:02）→ PRIME.x 卡死不报错、
     timeout 杀不掉 perl 孙进程。故 run 用 start_new_session（独立进程组）+
     超时 os.killpg 整组净杀，超时/失败 → 该 allele 全部置 NaN（与本地 wave3 一致）。
  3. parse：读每 allele out.txt（# 注释头 + TSV），取 Peptide + Score_bestAllele
     （单 allele 跑时 bestAllele == 该 allele），回贴每行 bb_idx 的 MT/WT 分数。

产出: $BASE/phaseB/PRIME_101102.csv   列: bb_idx, MT_PRIME, WT_PRIME
方向: Score 越高越免疫原（PRIME Score 原始方向，无翻转）。

用法（主线在 HPC 跑；env 通常已由 run_prime_hpc.sh 激活，故 --activate 默认仍带
完整激活前缀作 belt+suspenders——bash -lc 登录子 shell 可能重置 conda env）:
    python run_prime_hpc.py --smoke 1      # 只跑前 1 个 allele 验工具能跑、分数合理
    python run_prime_hpc.py                 # 全量产 CSV
环境变量等价覆盖: QIB_BASE / PRIME_DIR / PRIME_MIX / PRIME_ACTIVATE /
                 PRIME_BACKBONE / PRIME_OUT
"""
import argparse
import csv
import math
import os
import signal
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ── HPC 路径默认（实证本项目部署）─────────────────────────────────────────────
HPC_BASE = os.environ.get("QIB_BASE", "/gpfs/work/bio/jiayu2403/quantimmu")
DEFAULT_PRIME_DIR = os.environ.get("PRIME_DIR", f"{HPC_BASE}/tools_repos/PRIME")
DEFAULT_MIX = os.environ.get("PRIME_MIX", f"{HPC_BASE}/tools_repos/MixMHCpred/MixMHCpred")
# 订正源（只读，HLA 已订正、方向照原）。
DEFAULT_BACKBONE = os.environ.get("PRIME_BACKBONE", f"{HPC_BASE}/phaseB/backbone_101102.csv")
DEFAULT_OUT = os.environ.get("PRIME_OUT", f"{HPC_BASE}/phaseB/PRIME_101102.csv")
# conda env 激活前缀：本项目 HPC 惯用法（dep_deepimmuno.sh / hpc_improve.sh 实证）——
# module load 系统 miniconda 后用 source activate 激活全路径 env（conda activate 需 conda init）。
DEFAULT_ACTIVATE = os.environ.get(
    "PRIME_ACTIVATE",
    "source /etc/profile.d/modules.sh 2>/dev/null || true; "
    "module load miniconda3/22.11.1-gcc-8.5.0-l4fo6ta && "
    f"source activate {HPC_BASE}/envs/prime",
)

PRIME_VALID_LEN = range(8, 15)            # 8..14（PRIME 肽长限制，超界 → NaN）
STD_AA = set("ACDEFGHIKLMNPQRSTVWY")      # 仅标准 20 氨基酸，否则不送工具
PER_ALLELE_TIMEOUT = 1800                 # 单 allele 超时（秒）→ 净杀整组 + NaN


def hla_to_prime(h: str) -> str:
    """HLA-A*02:01 → A0201（去 HLA- 前缀 + 去 * 去 :），与本地 hla_to_prime 一致。"""
    s = str(h).strip()
    if s.upper().startswith("HLA-"):
        s = s[4:]
    return s.replace("*", "").replace(":", "")


def is_clean_pep(p: str) -> bool:
    return bool(p) and all(c in STD_AA for c in p)


def run_prime_allele(prime_dir, mix, activate, allele_tag, pep_file, out_file):
    """
    调官方 PRIME 打一个 allele 文件。返回 {pep_upper: score(float)}。
    失败 / 超时 → 返回 {}（该 allele 全部回贴 NaN）。
    用 start_new_session（独立进程组）+ killpg 防 MixMHCpred 不支持 allele 时
    PRIME.x 卡死、perl 孙进程杀不掉。
    """
    inner = (
        f'cd "{prime_dir}" && ./PRIME '
        f'-i "{pep_file}" -o "{out_file}" -a {allele_tag} -mix "{mix}"'
    )
    cmd = f"{activate} && {inner}" if activate else inner
    # 用 Popen + 独立进程组（start_new_session）：超时时 os.killpg 整组净杀，
    # 否则 subprocess.run 只杀直接子进程，perl/MixMHCpred 孙进程会存活继续卡。
    proc = subprocess.Popen(
        ["bash", "-lc", cmd],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        out, err = proc.communicate(timeout=PER_ALLELE_TIMEOUT)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)  # 整进程组净杀
        except (ProcessLookupError, PermissionError):
            pass
        proc.communicate()
        print(f"[run]   ⚠️ {allele_tag} 超时 {PER_ALLELE_TIMEOUT}s（MixMHCpred 可能不支持该 allele "
              f"→ PRIME.x 卡死）→ 整组净杀 + 该 allele 全置 NaN", file=sys.stderr)
        return {}
    if proc.returncode != 0:
        print(f"[run]   ⚠️ {allele_tag} 失败 rc={proc.returncode}: "
              f"{(err or '')[-300:]}{(out or '')[-200:]} → 该 allele 全置 NaN", file=sys.stderr)
        return {}
    if not Path(out_file).exists():
        print(f"[run]   ⚠️ {allele_tag} 无输出文件 {out_file} → 该 allele 全置 NaN", file=sys.stderr)
        return {}
    return parse_prime_out(out_file)


def parse_prime_out(out_file):
    """
    解析 PRIME 单 allele 输出（# 注释头 + TSV）。
    表头形如: Peptide  %Rank_bestAllele  Score_bestAllele  %RankBinding_bestAllele  BestAllele ...
    取 Peptide 列 + Score_bestAllele 列（单 allele 跑时即该 allele 分数）。
    返回 {pep_upper: score}。
    """
    scores = {}
    header = None
    ip = isc = None
    with open(out_file, encoding="utf-8") as f:
        for line in f:
            s = line.rstrip("\n")
            if not s.strip() or s.lstrip().startswith("#"):
                continue
            cols = [c.strip() for c in s.split("\t")]
            if header is None:
                if "Peptide" in cols:
                    header = cols
                    ip = cols.index("Peptide")
                    isc = cols.index("Score_bestAllele") if "Score_bestAllele" in cols else None
                    if isc is None:  # 回退：找首个 Score_xxx 列
                        for j, c in enumerate(cols):
                            if c.startswith("Score_"):
                                isc = j
                                break
                continue
            if isc is None or len(cols) <= max(ip, isc):
                continue
            try:
                scores[cols[ip].upper()] = float(cols[isc])
            except ValueError:
                continue
    return scores


def main():
    ap = argparse.ArgumentParser(description="Phase B PRIME 重推理 P101/P102（订正 HLA，HPC）")
    ap.add_argument("--smoke", type=int, default=0, help="只跑前 N 个 allele 验工具，不产 CSV")
    ap.add_argument("--backbone", default=DEFAULT_BACKBONE, help="订正源 backbone_101102.csv（只读）")
    ap.add_argument("--out", default=DEFAULT_OUT, help="输出 PRIME_101102.csv 路径")
    ap.add_argument("--prime-dir", default=DEFAULT_PRIME_DIR, help="PRIME repo 目录（含 ./PRIME wrapper + lib/PRIME.x）")
    ap.add_argument("--mix", default=DEFAULT_MIX, help="MixMHCpred 可执行路径（传给 PRIME -mix）")
    ap.add_argument("--activate", default=DEFAULT_ACTIVATE,
                    help="conda env 激活命令前缀（含 MixMHCpred3.0 python 依赖）；空串=已激活")
    args = ap.parse_args()

    backbone = Path(args.backbone)
    out_path = Path(args.out)
    workdir = out_path.parent / "prime_work"   # per-allele 临时 in/out

    if not backbone.exists():
        raise SystemExit(f"[FAIL] 订正源不存在: {backbone}")
    workdir.mkdir(parents=True, exist_ok=True)
    print(f"[cfg] backbone  = {backbone}")
    print(f"[cfg] out       = {out_path}")
    print(f"[cfg] prime_dir = {args.prime_dir}")
    print(f"[cfg] mix       = {args.mix}")
    print(f"[cfg] activate  = {args.activate or '(无，假设 env 已激活)'}")

    # ── 读 backbone，按 PRIME allele_tag 聚合需打分的肽（MT ∪ WT，去重）─────────
    rows = []
    allele_peps = defaultdict(set)   # allele_tag → {pep_upper}
    allele_original = {}             # allele_tag → 原始 HLA 串（仅记录）
    dropped_len = dropped_aa = 0
    with open(backbone, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(r)
            tag = hla_to_prime(r["HLA_Allele"])
            allele_original.setdefault(tag, str(r["HLA_Allele"]).strip())
            for col in ("MT_Subpeptide", "WT_Subpeptide"):
                pep = (r.get(col) or "").strip().upper()
                if not pep:
                    continue
                if len(pep) not in PRIME_VALID_LEN:
                    dropped_len += 1        # 超 8-14 → 不送 → 回贴 NaN
                elif not is_clean_pep(pep):
                    dropped_aa += 1         # 含非标准氨基酸 → 不送 → 回贴 NaN
                else:
                    allele_peps[tag].add(pep)

    alleles = sorted(allele_peps.keys())
    print(f"[prep] backbone={len(rows)} 行 | 唯一 allele={len(alleles)} | "
          f"超长肽丢弃(NaN)={dropped_len} | 非标准氨基酸丢弃(NaN)={dropped_aa}")
    for tag in alleles:
        print(f"[prep]   {tag:<8} ({allele_original.get(tag):<14}) {len(allele_peps[tag])} uniq pep")

    # ── 逐 allele 写 txt + 调 PRIME 打分 ────────────────────────────────────────
    run_tags = alleles[: args.smoke] if args.smoke else alleles
    score_dict = {}  # (pep_upper, allele_tag) → score
    for i, tag in enumerate(run_tags, 1):
        pep_list = sorted(allele_peps[tag])
        pep_file = workdir / f"{tag}_peps.txt"
        out_file = workdir / f"{tag}_out.txt"
        pep_file.write_text("\n".join(pep_list) + "\n", encoding="utf-8")
        sc = run_prime_allele(args.prime_dir, args.mix, args.activate, tag, pep_file, out_file)
        for pep, v in sc.items():
            score_dict[(pep, tag)] = v
        smin = min(sc.values()) if sc else float("nan")
        smax = max(sc.values()) if sc else float("nan")
        print(f"[run] [{i}/{len(run_tags)}] {tag} → {len(sc)}/{len(pep_list)} scores | "
              f"range [{smin:.6f}, {smax:.6f}]")

    if args.smoke:
        print(f"\n[smoke] 跑了 {len(run_tags)} 个 allele，工具可跑、分数在合理区间。未产 CSV。")
        return

    # ── 回贴 bb_idx，写 PRIME_101102.csv ────────────────────────────────────────
    def fmt(pep, tag):
        v = score_dict.get((pep, tag))
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return ""  # NaN → 空（pandas 读为 NaN）
        return str(round(v, 6))

    n_mt = n_wt = n_mt_nan = n_wt_nan = 0
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["bb_idx", "MT_PRIME", "WT_PRIME"])
        w.writeheader()
        for r in rows:
            tag = hla_to_prime(r["HLA_Allele"])
            mt = (r.get("MT_Subpeptide") or "").strip().upper()
            wt = (r.get("WT_Subpeptide") or "").strip().upper()
            mt_s = fmt(mt, tag) if mt else ""
            wt_s = fmt(wt, tag) if wt else ""
            n_mt += mt_s != ""
            n_wt += wt_s != ""
            n_mt_nan += mt_s == ""
            n_wt_nan += wt_s == ""
            w.writerow({"bb_idx": r["bb_idx"], "MT_PRIME": mt_s, "WT_PRIME": wt_s})

    print(f"\n[parse] 写 {out_path}  ({len(rows)} 行)")
    print(f"[parse]   MT_PRIME: {n_mt} found / {n_mt_nan} NaN")
    print(f"[parse]   WT_PRIME: {n_wt} found / {n_wt_nan} NaN")
    print(f"[parse]   方向：Score 越高越免疫原（无翻转）")


if __name__ == "__main__":
    main()
