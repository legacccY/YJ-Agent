# -*- coding: utf-8 -*-
"""
prep_stabpan_FULL130_8to11.py — QuantImmuBench 8-11mer 口径(另窗)
服务：quantimmu-bench §工具部署 lever=netMHCstabpan 补满覆盖（43/130 → FULL130）

从 merged_all_tools_29tools.xlsx 的全 9mer 含突变子肽×HLA（m9）建 netMHCstabpan-1.0
的「FULL130」直跑输入：每个等位一个 <allele_safe>.pep（每行一个肽，去重）+ 一份等位
映射表 alleles_FULL130_8to11.tsv（供 run 脚本遍历）。

口径（严格对齐 _scratch/build_full130_inputs.py 的 flat 类工具，== MHCnuggets 参考）：
  m9 = old[(L==9) & (MT_Subpeptide != WT_Subpeptide)]        （DS1+DS2 全量）
  flat dedup (MT_Subpeptide, HLA_Allele) → 3283 唯一对（35 个 MHC-I 等位）
  netMHCstabpan 是 MHC-I 稳定性工具 → 只留 HLA-A/B/C。

等位命名三态：
  allele_star  原始带星       HLA-A*01:01   （回贴 universe 用，写进 raw CSV）
  allele_nmhc  去星 net 格式   HLA-A01:01    （netMHCstabpan -a 要这个）
  allele_safe  文件名安全       HLA-A01-01    （.pep / .out 文件名，冒号→短横）

只建输入文件，绝不跑工具 / 不连 HPC / 不 pip。纯本地 pandas。

产物（本目录 inputs_FULL130/，主线上传到 HPC ${ROOT}/HPC/deploy/netmhcstabpan/inputs_FULL130/）：
  inputs_FULL130/<allele_safe>.pep        每个等位一个肽文件
  inputs_FULL130/alleles_FULL130_8to11.tsv      无表头 3 列 TSV: safe<TAB>nmhc<TAB>star
"""
import pathlib
import pandas as pd

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]                         # QuantImmuBench/
SRC = ROOT / "scripts" / "out" / "merged_all_tools_29tools.xlsx"
OUT_DIR = SCRIPT_DIR / "inputs_FULL130_8to11"


def nostar(h: str) -> str:
    return str(h).replace("*", "").strip()


def safe_name(h_nostar: str) -> str:
    # HLA-A01:01 -> HLA-A01-01 （冒号→短横，文件名安全）
    return h_nostar.replace(":", "-")


def npep(df: pd.DataFrame) -> int:
    return df.groupby(["Patient_ID", "Peptide_ID"]).ngroups


def main():
    old = pd.read_excel(SRC)
    old["L"] = old["MT_Subpeptide"].astype(str).str.len()
    m9 = old[(old["L"].isin([8, 9, 10, 11])) &
             (old["MT_Subpeptide"].astype(str) != old["WT_Subpeptide"].astype(str))].copy()
    m9 = m9.dropna(subset=["MT_Subpeptide", "HLA_Allele"])
    print(f"[src] m8-11 rows(DS1+DS2, 非 dedup)={len(m9)}  peptides={npep(m9)}")

    # flat dedup (MT_Subpeptide, HLA_Allele)，只留 MHC-I（HLA-A/B/C）
    flat = m9.drop_duplicates(["MT_Subpeptide", "HLA_Allele"]).copy()
    flat = flat[flat["HLA_Allele"].astype(str).str.startswith(("HLA-A", "HLA-B", "HLA-C"))]
    print(f"[flat] dedup(pep,HLA) 唯一对={len(flat)}  peptides={npep(flat)}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 按等位（star 原始）分组建 .pep
    rows = []          # (safe, nmhc, star, n_pep)
    for star, grp in flat.groupby("HLA_Allele"):
        nmhc = nostar(star)
        safe = safe_name(nmhc)
        peps = sorted(grp["MT_Subpeptide"].astype(str).unique())
        pep_path = OUT_DIR / f"{safe}.pep"
        pep_path.write_text("\n".join(peps) + "\n", encoding="utf-8", newline="")  # LF only (防 CRLF 污染 netMHCstabpan 长度判定)
        rows.append((safe, nmhc, str(star), len(peps)))

    # 等位映射表（无表头，run 脚本 while-read 用）
    tsv_path = OUT_DIR / "alleles_FULL130_8to11.tsv"
    with open(tsv_path, "w", encoding="utf-8", newline="\n") as fh:
        for safe, nmhc, star, _ in sorted(rows):
            fh.write(f"{safe}\t{nmhc}\t{star}\n")

    print("\n==== per-allele .pep 汇总 ====")
    total = 0
    for safe, nmhc, star, n in sorted(rows):
        total += n
        print(f"{safe:14s} nmhc={nmhc:12s} star={star:14s} n_pep={n}")
    print(f"\n[out] 等位数={len(rows)}  肽行合计(去重后各等位内)={total}")
    print(f"[out] .pep 目录: {OUT_DIR}")
    print(f"[out] 映射表:   {tsv_path}")


if __name__ == "__main__":
    main()
