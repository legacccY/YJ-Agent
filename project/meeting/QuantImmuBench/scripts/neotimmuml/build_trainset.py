"""
build_trainset.py — QuantImmuBench / NeoTImmuML
从 TumorAgDB2.0 下载的两个 xlsx 组装训练集 peptide+label

输入:
  train_data/immunogenic_neopeptide.xlsx    (102行×52列, col12=mutant_seq, col51=immunogenicity=1)
  train_data/nonimmunogenic_neopeptide.xlsx (36590行×52列, col12=Peptide, col51=immunogenicity=0)

输出:
  train_data/trainset_peptides.csv  — 两列: Peptide, immunogenicity (1/0)

用法:
  python build_trainset.py [--immunogenic <path>] [--nonimmunogenic <path>] [--output <path>]

类不平衡处理:
  NeoTImmuML notebook 全程无 SMOTE / class_weight / 下采样处理，
  直接 model.fit(X_train, y_train)。本脚本严格遵循，不加任何均衡操作。
  # TODO: 102:36590 比例约 1:358，模型训练时若发现性能差可联系 NeoTImmuML 作者确认是否有额外处理

过滤规则:
  1. 去除非标准氨基酸 (非 ACDEFGHIKLMNPQRSTVWY)
  2. 保留长度 8-13mer（与 ELISpot 肽段范围一致）
  3. 去重（按 Peptide 去重，同序列保留第一个）
"""

import argparse
import pathlib
import sys

import pandas as pd

VALID_AAS = set("ACDEFGHIKLMNPQRSTVWY")
DEFAULT_BASE = pathlib.Path(__file__).parent / "train_data"


def load_xlsx_col(path: pathlib.Path, peptide_col: str, label_col: str = "immunogenicity") -> pd.DataFrame:
    """读 xlsx，取 peptide_col + label_col，返回 DataFrame(Peptide, immunogenicity)"""
    # 用 openpyxl 引擎（HPC neotimmuml env 需 openpyxl；若没有可 pip install openpyxl）
    df = pd.read_excel(str(path), engine="openpyxl")
    if peptide_col not in df.columns:
        raise ValueError(f"Column '{peptide_col}' not found in {path}. Columns: {list(df.columns)}")
    if label_col not in df.columns:
        raise ValueError(f"Column '{label_col}' not found in {path}. Columns: {list(df.columns)}")
    sub = df[[peptide_col, label_col]].copy()
    sub.columns = ["Peptide", "immunogenicity"]
    return sub


def is_valid_peptide(pep: str, min_len: int = 8, max_len: int = 13) -> bool:
    if not isinstance(pep, str):
        return False
    pep = pep.strip().upper()
    if len(pep) < min_len or len(pep) > max_len:
        return False
    return all(c in VALID_AAS for c in pep)


def main():
    parser = argparse.ArgumentParser(
        description="Assemble NeoTImmuML training set from TumorAgDB2.0 xlsx files"
    )
    parser.add_argument(
        "--immunogenic",
        default=str(DEFAULT_BASE / "immunogenic_neopeptide.xlsx"),
        help="Path to immunogenic_neopeptide.xlsx",
    )
    parser.add_argument(
        "--nonimmunogenic",
        default=str(DEFAULT_BASE / "nonimmunogenic_neopeptide.xlsx"),
        help="Path to nonimmunogenic_neopeptide.xlsx",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_BASE / "trainset_peptides.csv"),
        help="Output CSV: Peptide,immunogenicity",
    )
    parser.add_argument("--min_len", type=int, default=8)
    parser.add_argument("--max_len", type=int, default=13)
    args = parser.parse_args()

    # ---- 读取两文件 ----
    print(f"[INFO] Reading immunogenic: {args.immunogenic}")
    df_pos = load_xlsx_col(
        pathlib.Path(args.immunogenic),
        peptide_col="mutant_seq",   # col12 in immunogenic file
        label_col="immunogenicity", # col51, value=1
    )

    print(f"[INFO] Reading nonimmunogenic: {args.nonimmunogenic}")
    df_neg = load_xlsx_col(
        pathlib.Path(args.nonimmunogenic),
        peptide_col="Peptide",      # col12 in nonimmunogenic file
        label_col="immunogenicity", # col51, value=0
    )

    print(f"[INFO] Raw counts: pos={len(df_pos)}, neg={len(df_neg)}")

    # ---- 合并 ----
    df = pd.concat([df_pos, df_neg], ignore_index=True)

    # ---- 标准化 label → int 0/1 ----
    # label 已是整数 0/1（confirmed from xlsx inspection），但保险做转换
    def normalize_label(v):
        if isinstance(v, (int, float)):
            return int(v)
        s = str(v).strip().lower()
        if s in ("1", "positive", "pos", "yes", "immunogenic"):
            return 1
        if s in ("0", "negative", "neg", "no", "nonimmunogenic"):
            return 0
        return None  # 非法

    df["immunogenicity"] = df["immunogenicity"].apply(normalize_label)
    n_invalid_label = df["immunogenicity"].isna().sum()
    if n_invalid_label > 0:
        print(f"[WARN] {n_invalid_label} rows with unrecognized label — dropped")
        df = df.dropna(subset=["immunogenicity"])
    df["immunogenicity"] = df["immunogenicity"].astype(int)

    # ---- 过滤肽段 ----
    df["Peptide"] = df["Peptide"].astype(str).str.strip().str.upper()
    before = len(df)
    mask = df["Peptide"].apply(lambda p: is_valid_peptide(p, args.min_len, args.max_len))
    df = df[mask].copy()
    print(f"[INFO] After length/AA filter ({args.min_len}-{args.max_len}mer): {len(df)}/{before} rows kept")

    # ---- 去重（同序列保留第一个，维持 label 分布）----
    before_dedup = len(df)
    df = df.drop_duplicates(subset=["Peptide"], keep="first").reset_index(drop=True)
    print(f"[INFO] After dedup: {len(df)}/{before_dedup} rows")

    # ---- 统计 ----
    vc = df["immunogenicity"].value_counts()
    n_pos = vc.get(1, 0)
    n_neg = vc.get(0, 0)
    ratio = n_neg / n_pos if n_pos > 0 else float("inf")
    print(f"[INFO] Final: pos={n_pos}, neg={n_neg}, neg:pos ratio={ratio:.1f}:1")
    print(f"[INFO] NOTE: notebook has NO class imbalance handling — training on raw ratio")
    # TODO: 102:36590 类不平衡约 1:358，模型若效果差可查是否需额外处理

    # ---- 写出 ----
    pathlib.Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    df[["Peptide", "immunogenicity"]].to_csv(args.output, index=False)
    print(f"[DONE] Written {len(df)} rows to: {args.output}")


if __name__ == "__main__":
    main()
