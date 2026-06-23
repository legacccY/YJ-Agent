"""
extract_peptides.py — QuantImmuBench / NeoTImmuML
从 master_backbone.csv 提取 unique 肽段（MT_Subpeptide + WT_Subpeptide，8-13mer）
输出单列 txt，供 calc_78_features.R --input 使用

用法:
  python extract_peptides.py \
      --backbone scripts/out/master_backbone.csv \
      --output   scripts/out/neotimmuml_peptides.txt \
      [--min_len 8] [--max_len 13]
"""

import argparse
import pathlib
import pandas as pd

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backbone", default="scripts/out/master_backbone.csv",
                        help="master_backbone.csv path")
    parser.add_argument("--output",   default="scripts/out/neotimmuml_peptides.txt",
                        help="Output file: one peptide per line, no header")
    parser.add_argument("--min_len",  type=int, default=8, help="Min peptide length (default 8)")
    parser.add_argument("--max_len",  type=int, default=13, help="Max peptide length (default 13)")
    args = parser.parse_args()

    df = pd.read_csv(args.backbone)
    mt = df["MT_Subpeptide"].dropna().astype(str)
    wt = df["WT_Subpeptide"].dropna().astype(str)
    all_peps = pd.concat([mt, wt], ignore_index=True)

    # 过滤长度
    mask = all_peps.str.len().between(args.min_len, args.max_len)
    filtered = all_peps[mask].unique()
    # 过滤非标准氨基酸（NeoTImmuML 不含非标准AA的肽段）
    valid = [p for p in filtered if all(c.upper() in "ACDEFGHIKLMNPQRSTVWY" for c in p)]

    pathlib.Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        for p in sorted(valid):
            f.write(p + "\n")

    print(f"[INFO] Extracted {len(valid)} unique peptides ({args.min_len}-{args.max_len}mer)")
    print(f"[DONE] Written to: {args.output}")


if __name__ == "__main__":
    main()
