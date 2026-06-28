# -*- coding: utf-8 -*-
"""
run_netmhcpan_ba_101102.py — Phase B：用订正 HLA 等位 + 本地 netMHCpan-4.1
重推理 netMHCpan-BA（P101/P102）。本机 WSL 跑。

唯一订正输入源 = scripts/out/phaseB/backbone_101102.csv（prep_101102_subset.py 产，
已过闸门1：HLA_Allele == 订正真值 P101={A*66:01,B*40:01,B*57:01,C*06:02}/
P102={A*02:01,B*35:03,B*38:01}）。本脚本只从这份派生，绝不读旧 netmhcpan 输入文件。

自包含三步（prep+run+parse 一体），逻辑对齐 HPC/deploy/netmhcpan_ba 三件套：
  1. prep：从 backbone 取 MT_Subpeptide + WT_Subpeptide，按 HLA_Allele 分组去重，
     HLA 转 netMHCpan 格式（去 '*' 保 ':'，HLA-A*66:01 → HLA-A66:01）。
  2. run：对每个 allele 调本地 netMHCpan-4.1：
       sudo <netMHCpan> -p <pep> -BA -a <allele_nmhc> -xls -xlsfile <out.xls>
     （subprocess；脚本在 WSL 内跑，netMHCpan 二进制在 WSL root，须 sudo）。
  3. parse：读 *_out.xls，取 BA-score（0-1，越高越强结合），方向 = parse_netmhcpan_ba.py
     一致（uni_score = BA-score；缺失回退 -BA_Rank），回贴每行 bb_idx 的 MT/WT 分数。

产出: scripts/out/phaseB/netMHCpan_BA_101102.csv
      列: bb_idx, MT_netmhcpan_ba, WT_netmhcpan_ba
方向: 分数越高越强结合 / 越可能免疫原（与 benchmark 内 netmhcpan_ba_DS1DS2_scores.csv
      同一方向定义，可直接对照；无翻转）。

⚠️ DTU 学术许可红线：netMHCpan-4.1 受 DTU 学术许可约束。本表所有数字
   pending_DTU_consent —— 未获 DTU 书面同意前**不得发布/外传** benchmark 数字。

用法（在 WSL 内）:
    sudo python3 run_netmhcpan_ba_101102.py [--smoke N]
    --smoke N: 只跑前 N 个 allele 分组（验工具能跑、分数合理），不产正式 CSV。

注：netMHCpan 二进制须 sudo（WSL root 部署）。建议**整脚本用 sudo 跑**，避免
    netMHCpan 以 root 写出的 *_out.xls 再被非 root python 读取时的权限问题。
"""
import argparse
import csv
import math
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]  # QuantImmuBench/
BACKBONE = ROOT / "scripts" / "out" / "phaseB" / "backbone_101102.csv"
WORKDIR = ROOT / "scripts" / "out" / "phaseB" / "netmhcpan_ba_work"   # per-allele .pep / *_out.xls
OUT = ROOT / "scripts" / "out" / "phaseB" / "netMHCpan_BA_101102.csv"

# 本地 WSL netMHCpan-4.1 二进制（WSL root 部署，须 sudo）。
NETMHCPAN = "/root/quantimmu/ext_tools/netMHCpan-4.1/netMHCpan"
USE_SUDO = True   # netMHCpan 在 root 目录；若整脚本已 root 跑可设 False

STD_AA = set("ACDEFGHIKLMNPQRSTVWY")  # netMHCpan 仅接受标准 20 种氨基酸


def hla_to_netmhcpan(h: str) -> str:
    """HLA-A*66:01 → HLA-A66:01（去 '*' 保 ':'），与 prep_netmhcpan_ba.py 一致。"""
    return h.replace("*", "")


def hla_to_safe(h: str) -> str:
    """HLA-A*66:01 → HLA-A66-01（去 '*'，':'→'-'；文件名安全）。"""
    return h.replace("*", "").replace(":", "-")


def is_clean_pep(p: str) -> bool:
    return bool(p) and all(c in STD_AA for c in p)


# ---------------------------------------------------------------------------
# XLS parsing —— 逻辑搬自 HPC/deploy/netmhcpan_ba/parse_netmhcpan_ba.py
#   实测 netMHCpan-4.1 -xls 表头（2026-06-26 HPC 核验）：
#     Pos  Peptide  ID  core  icore  EL-score  EL_Rank  BA-score  BA_Rank  Ave  NB
#   -xls 文件里没有 Aff(nM) 列；BA = `BA-score`(0-1 越高越强) + `BA_Rank`(%rank 越低越强)。
# ---------------------------------------------------------------------------

def _find_col(header_row, patterns):
    for pat in patterns:
        rx = re.compile(pat, re.IGNORECASE)
        for i, col in enumerate(header_row):
            if rx.search(col):
                return i
    return -1


def parse_xls_file(xls_path: Path) -> dict:
    """解析一个 netMHCpan-4.1 -xls 文件 → {peptide: {'BA_score':float, 'Rnk_BA':float}}。"""
    results = {}
    with open(xls_path, encoding="utf-8", errors="replace") as fh:
        lines = fh.readlines()

    # 找表头：第一条含 "Peptide" 的非注释行（跳过 allele 跨列首行）。
    header_idx = -1
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("#") or s == "":
            continue
        if re.search(r"\bPeptide\b", s, re.IGNORECASE):
            header_idx = i
            break
    if header_idx == -1:
        print(f"  WARN: 未找到表头 {xls_path.name}，跳过。")
        return results

    header_cols = lines[header_idx].rstrip("\n").split("\t")
    pep_col     = _find_col(header_cols, [r"^Peptide$"])
    bascore_col = _find_col(header_cols, [r"^BA-score$", r"^BA_score$", r"^BAscore$"])
    rank_col    = _find_col(header_cols, [r"^BA_Rank$", r"^BA-Rank$", r"^BARank$", r"%Rank_BA", r"Rnk_BA"])

    if pep_col == -1:
        print(f"  WARN: Peptide 列未找到 {xls_path.name}. Cols: {header_cols[:6]}")
        return results
    if bascore_col == -1:
        print(f"  WARN: BA-score 列未找到 {xls_path.name}. Cols: {header_cols}")
    if rank_col == -1:
        print(f"  WARN: BA_Rank 列未找到 {xls_path.name}. Cols: {header_cols}")

    for line in lines[header_idx + 1:]:
        s = line.strip()
        if s == "" or s.startswith("#"):
            continue
        cols = s.split("\t")
        if len(cols) <= pep_col:
            continue
        peptide = cols[pep_col].strip()
        if not peptide:
            continue
        ba_score = float("nan")
        rnk_ba = float("nan")
        try:
            if bascore_col != -1 and bascore_col < len(cols):
                ba_score = float(cols[bascore_col])
        except ValueError:
            pass
        try:
            if rank_col != -1 and rank_col < len(cols):
                rnk_ba = float(cols[rank_col])
        except ValueError:
            pass
        results[peptide] = {"BA_score": ba_score, "Rnk_BA": rnk_ba}

    return results


def uni_score(ba_score: float, rnk_ba: float) -> float:
    """统一方向：越高越强结合。直接用 BA-score（0-1）；缺失回退 -BA_Rank。
    与 parse_netmhcpan_ba.py 一致，保证与 benchmark 内其余 netmhcpan_ba 分数同尺度。"""
    if not math.isnan(ba_score):
        return ba_score
    if not math.isnan(rnk_ba):
        return -rnk_ba
    return float("nan")


def run_one_allele(pep_file: Path, allele_nmhc: str, out_xls: Path):
    """对一个 allele 调 netMHCpan -BA -xls。out_xls 复用则跳过重跑。"""
    cmd = []
    if USE_SUDO:
        cmd.append("sudo")
    cmd += [NETMHCPAN, "-p", str(pep_file), "-BA", "-a", allele_nmhc,
            "-xls", "-xlsfile", str(out_xls)]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if res.returncode != 0:
        raise RuntimeError(
            f"netMHCpan 失败 allele={allele_nmhc} rc={res.returncode}: "
            f"{res.stderr[:300]}{res.stdout[:200]}"
        )


def main():
    ap = argparse.ArgumentParser(description="Phase B netMHCpan-BA 本地重推理 P101/P102")
    ap.add_argument("--smoke", type=int, default=0, help="只跑前 N 个 allele 分组验工具，不产 CSV")
    args = ap.parse_args()

    if not BACKBONE.exists():
        raise SystemExit(f"[FAIL] 订正源不存在: {BACKBONE}")
    WORKDIR.mkdir(parents=True, exist_ok=True)

    # ── prep：读 backbone，按 allele 聚合 MT∪WT 去重 ─────────────────────────
    rows = []
    allele_peps = defaultdict(set)     # allele_safe → {pep_upper}
    allele_nmhc = {}                   # allele_safe → netMHCpan -a 串
    allele_original = {}               # allele_safe → 原始 HLA 串（仅记录）
    dropped = 0
    with open(BACKBONE, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(r)
            hla = r["HLA_Allele"].strip()
            safe = hla_to_safe(hla)
            allele_nmhc[safe] = hla_to_netmhcpan(hla)
            allele_original.setdefault(safe, hla)
            for col in ("MT_Subpeptide", "WT_Subpeptide"):
                pep = (r.get(col) or "").strip().upper()
                if not pep:
                    continue
                if is_clean_pep(pep):
                    allele_peps[safe].add(pep)
                else:
                    dropped += 1   # 非标准氨基酸 → 不送工具，回贴时 NaN

    alleles = sorted(allele_peps.keys())
    print(f"[prep] backbone={len(rows)} 行 | 唯一 allele={len(alleles)} | 非标准肽丢弃(置NaN)={dropped}")
    for safe in alleles:
        print(f"[prep]   {safe:<12} (-a {allele_nmhc[safe]:<12}) "
              f"{len(allele_peps[safe])} uniq pep")

    # ── run：逐 allele 写 .pep + 调 netMHCpan ────────────────────────────────
    run_safes = alleles[:args.smoke] if args.smoke else alleles
    # (pep_upper, allele_safe) → uni_score
    score_dict = {}
    for i, safe in enumerate(run_safes, 1):
        pep_list = sorted(allele_peps[safe])
        pep_file = WORKDIR / f"{safe}.pep"
        out_xls = WORKDIR / f"{safe}_out.xls"
        pep_file.write_text("\n".join(pep_list) + "\n", encoding="utf-8")

        run_one_allele(pep_file, allele_nmhc[safe], out_xls)
        parsed = parse_xls_file(out_xls)

        sc = {}
        for pep, d in parsed.items():
            sc[pep.upper()] = uni_score(d["BA_score"], d["Rnk_BA"])
        for pep, v in sc.items():
            score_dict[(pep, safe)] = v

        vals = [v for v in sc.values() if not math.isnan(v)]
        smin = min(vals) if vals else float("nan")
        smax = max(vals) if vals else float("nan")
        print(f"[run] [{i}/{len(run_safes)}] {safe} (-a {allele_nmhc[safe]}) "
              f"{len(sc)} scores | range [{smin:.4f}, {smax:.4f}]")

    if args.smoke:
        print(f"\n[smoke] 跑了 {len(run_safes)} 个 allele，工具可跑、分数在合理区间。未产 CSV。")
        return

    # ── parse：回贴 bb_idx，写 netMHCpan_BA_101102.csv ──────────────────────
    def fmt(pep, safe):
        v = score_dict.get((pep, safe))
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return ""   # NaN → 空（pandas 读为 NaN）
        return str(round(v, 6))

    n_mt = n_wt = n_mt_nan = n_wt_nan = 0
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["bb_idx", "MT_netmhcpan_ba", "WT_netmhcpan_ba"])
        w.writeheader()
        for r in rows:
            safe = hla_to_safe(r["HLA_Allele"].strip())
            mt = (r.get("MT_Subpeptide") or "").strip().upper()
            wt = (r.get("WT_Subpeptide") or "").strip().upper()
            mt_s = fmt(mt, safe) if mt else ""
            wt_s = fmt(wt, safe) if wt else ""
            n_mt += mt_s != ""
            n_wt += wt_s != ""
            n_mt_nan += mt_s == ""
            n_wt_nan += wt_s == ""
            w.writerow({"bb_idx": r["bb_idx"], "MT_netmhcpan_ba": mt_s, "WT_netmhcpan_ba": wt_s})

    print(f"\n[parse] 写 {OUT}  ({len(rows)} 行)")
    print(f"[parse]   MT_netmhcpan_ba: {n_mt} found / {n_mt_nan} NaN")
    print(f"[parse]   WT_netmhcpan_ba: {n_wt} found / {n_wt_nan} NaN")
    print(f"[parse]   方向：BA-score 越高越强结合（无翻转，与 DS1DS2 同尺度）")
    print(f"[parse]   ⚠️ DTU 学术许可：数字 pending_DTU_consent，未获书面同意前不得外传/发布")


if __name__ == "__main__":
    main()
