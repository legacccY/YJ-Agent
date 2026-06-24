#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IEDB overlap check — 补救红队 🟠-2：ELISpot 肽是否已被 IEDB T-cell 数据「污染」
(即工具训练集可能见过这些肽，导致 benchmark AUC 乐观偏高)。

输入:
  --merged   merged_all_tools_8tools.xlsx 路径 (默认 scripts/out/merged_all_tools_8tools.xlsx)
             从中提取 ELISpot 的全部 unique 肽序列 (优先用 MT_Subpeptide 短表位，
             并附带 MT_FullPeptide 长肽，两者都做 overlap)。
  --iedb     IEDB tcell_full 导出 csv 路径 (默认占位 data/iedb_tcell_full.csv)。
             ※ 本脚本不联网、不下载。需用户自行去 https://www.iedb.org/
               → Database Export → "tcell_full_v3.zip" (或 T Cell Assays csv 导出) 下载后
               解压传入。缺文件时脚本会清晰报错并打印下载指引，不会静默继续。

逻辑:
  ① 精确肽序列 match (ELISpot 肽 ∈ IEDB 肽集合)。
  ② 9mer 子串 match：把每条 ELISpot 肽切成所有 9mer 窗口，
     若任一 9mer 命中任一 IEDB 肽 (作为子串或反向 IEDB 9mer 集合) 则判 overlap。

输出 (写到 analysis/):
  iedb_overlap_hits.csv     —— 命中肽清单 (peptide, match_type=exact|9mer, matched_iedb_example)
  iedb_overlap_whitelist.csv—— 剔除 overlap 后剩余「干净」肽白名单 (建议据此重算 AUC)
  并打印 overlap 比例 + 「剔除后建议重算 AUC」的提示。

跑法 (主线):
  python analysis/iedb_overlap_check.py --iedb data/iedb_tcell_full.csv
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_MERGED = ROOT / "scripts" / "out" / "merged_all_tools_8tools.xlsx"
DEFAULT_IEDB = ROOT / "data" / "iedb_tcell_full.csv"
OUT_HITS = HERE / "iedb_overlap_hits.csv"
OUT_WHITELIST = HERE / "iedb_overlap_whitelist.csv"

# IEDB csv 列名候选 (不同导出格式列名不同，做多候选 fallback)
IEDB_PEPTIDE_COL_CANDIDATES = [
    "Description",            # tcell_full 经典列 (Epitope - Name/Description)
    "Epitope - Name",
    "Epitope Description",
    "Object Type - Name",
    "Peptide",
    "Linear peptide sequence",
    "Epitope",
]

# ELISpot 肽来源列 (短表位 + 长肽都做 overlap)
ELISPOT_PEP_COLS = ["MT_Subpeptide", "MT_FullPeptide"]

VALID_AA = set("ACDEFGHIKLMNPQRSTVWY")


def _clean_pep(x):
    if not isinstance(x, str):
        return None
    s = x.strip().upper()
    if not s or any(c not in VALID_AA for c in s):
        return None
    return s


def kmers(seq, k=9):
    if len(seq) < k:
        return []
    return [seq[i:i + k] for i in range(len(seq) - k + 1)]


def load_elispot_peptides(merged_path: Path):
    if not merged_path.exists():
        sys.exit(f"[ERR] merged 表不存在: {merged_path}\n"
                 f"      请确认 scripts/out/merged_all_tools_8tools.xlsx 已生成。")
    df = pd.read_excel(merged_path)
    peps = set()
    for col in ELISPOT_PEP_COLS:
        if col in df.columns:
            for v in df[col].dropna().unique():
                p = _clean_pep(v)
                if p:
                    peps.add(p)
        else:
            print(f"[warn] merged 表无列 {col}，跳过")
    if not peps:
        sys.exit("[ERR] 未从 merged 表提取到任何合法肽序列，检查列名。")
    return sorted(peps)


def load_iedb_peptides(iedb_path: Path):
    if not iedb_path.exists():
        msg = (
            f"\n[ERR] IEDB tcell_full 导出文件不存在: {iedb_path}\n"
            f"      本脚本不联网、不自动下载。请手动获取:\n"
            f"      1) 打开 https://www.iedb.org/ → 顶部 'Database Export' (或 https://www.iedb.org/database_export_v3.php)\n"
            f"      2) 下载 'tcell_full_v3.zip' (T Cell Assays 全量)，解压得 tcell_full_v3.csv\n"
            f"         或在 IEDB search 里筛 Linear peptide T-cell assays 导出 csv。\n"
            f"      3) 把 csv 传到本机，用 --iedb <path> 指向它再跑本脚本。\n"
            f"      (IEDB csv 通常有两行表头；本脚本会自动尝试跳过第 1 行 header。)\n"
        )
        sys.exit(msg)

    # IEDB tcell_full csv 通常是双层表头，先试 header=1，再 fallback header=0
    df = None
    for hdr in (1, 0):
        try:
            tmp = pd.read_csv(iedb_path, header=hdr, low_memory=False)
            if any(c in tmp.columns for c in IEDB_PEPTIDE_COL_CANDIDATES):
                df = tmp
                break
        except Exception:
            continue
    if df is None:
        try:
            df = pd.read_csv(iedb_path, low_memory=False)
        except Exception as e:
            sys.exit(f"[ERR] 无法读取 IEDB csv: {e}")

    pep_col = next((c for c in IEDB_PEPTIDE_COL_CANDIDATES if c in df.columns), None)
    if pep_col is None:
        sys.exit(f"[ERR] IEDB csv 未找到肽序列列。已试候选列名: {IEDB_PEPTIDE_COL_CANDIDATES}\n"
                 f"      实际列名: {list(df.columns)[:30]}\n"
                 f"      请检查导出格式或在脚本 IEDB_PEPTIDE_COL_CANDIDATES 里补列名。")
    print(f"[info] IEDB 肽序列列 = '{pep_col}'")

    peps = set()
    for v in df[pep_col].dropna().unique():
        p = _clean_pep(v)  # 只保留纯线性肽 (剔含修饰/非天然氨基酸的 Description)
        if p:
            peps.add(p)
    if not peps:
        sys.exit("[ERR] IEDB csv 未解析出任何合法线性肽，检查列内容。")
    return peps


def main():
    ap = argparse.ArgumentParser(description="ELISpot vs IEDB 肽 overlap 检查")
    ap.add_argument("--merged", default=str(DEFAULT_MERGED))
    ap.add_argument("--iedb", default=str(DEFAULT_IEDB))
    ap.add_argument("--k", type=int, default=9, help="子串窗口长度 (默认 9mer)")
    args = ap.parse_args()

    elispot = load_elispot_peptides(Path(args.merged))
    print(f"[info] ELISpot unique 肽数: {len(elispot)}")

    iedb_peps = load_iedb_peptides(Path(args.iedb))
    print(f"[info] IEDB 线性肽数: {len(iedb_peps)}")

    # IEDB 9mer 集合 (用于子串命中加速)
    iedb_9 = set()
    for p in iedb_peps:
        iedb_9.update(kmers(p, args.k))

    rows = []
    hit_peptides = set()
    for pep in elispot:
        # ① 精确 match
        if pep in iedb_peps:
            rows.append({"peptide": pep, "match_type": "exact",
                         "matched_iedb_example": pep})
            hit_peptides.add(pep)
            continue
        # ② 9mer 子串 match
        matched_kmer = None
        for km in kmers(pep, args.k):
            if km in iedb_9:
                matched_kmer = km
                break
        if matched_kmer is not None:
            rows.append({"peptide": pep, "match_type": f"{args.k}mer",
                         "matched_iedb_example": matched_kmer})
            hit_peptides.add(pep)

    hits = pd.DataFrame(rows, columns=["peptide", "match_type", "matched_iedb_example"])
    hits.to_csv(OUT_HITS, index=False)

    clean = [p for p in elispot if p not in hit_peptides]
    pd.DataFrame({"peptide": clean}).to_csv(OUT_WHITELIST, index=False)

    n = len(elispot)
    n_hit = len(hit_peptides)
    n_exact = int((hits["match_type"] == "exact").sum()) if len(hits) else 0
    n_kmer = n_hit - n_exact
    print("\n=== IEDB overlap 结果 ===")
    print(f"ELISpot 肽总数      : {n}")
    print(f"overlap 命中肽       : {n_hit}  ({n_hit / n:.1%})")
    print(f"  - 精确 match       : {n_exact}")
    print(f"  - {args.k}mer 子串 match: {n_kmer}")
    print(f"剔除后干净肽 (白名单): {len(clean)}")
    print(f"\n命中清单 -> {OUT_HITS}")
    print(f"干净白名单 -> {OUT_WHITELIST}")
    print(f"\n[建议] 用 iedb_overlap_whitelist.csv 的肽过滤 plotdata_perpep.csv / merged 表，"
          f"在剔除 overlap 肽的子集上重算各工具 AUC，对照原 AUC 看乐观偏差幅度。")


if __name__ == "__main__":
    main()
