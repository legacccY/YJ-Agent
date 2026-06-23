# verify_features_vs_demo.py -- demo 交叉核验脚本
# 把 calc_78_features.R 对 demo.csv 肽段算的特征与 demo.csv 自带值逐列比对
# 确认 R 函数参数（尤其 autoCorrelation/autoCovariance/aaComp_1/cruciani）是否对应
#
# 用法（主线跑，在 Windows 本机 Python 环境）:
#
#   前置：把 demo.csv 从 WSL 复制到 verify_tmp/demo.xlsx
#   WSL 命令：
#     cp ~/quantimmu/tools_repos/NeoTImmuML/demo.csv
#        /mnt/d/YJ-Agent/project/meeting/QuantImmuBench/scripts/neotimmuml/verify_tmp/demo.xlsx
#
#   Step1: 从 demo.csv 提取肽段列表
#     python scripts/neotimmuml/verify_features_vs_demo.py extract
#
#   Step2: R 对这 10 条肽段算 78 特征
#     Rscript calc_78_features.R
#       --input  scripts/neotimmuml/verify_tmp/demo_peptides.txt
#       --output scripts/neotimmuml/verify_tmp/demo_r_features.csv
#
#   Step3: 逐列比对，输出 OK/WARN/MISMATCH
#     python scripts/neotimmuml/verify_features_vs_demo.py compare
#
#   Step4 (若有 MISMATCH): 调整 calc_78_features.R 参数，重跑 Step2+Step3
#   重点核验列: autoCorrelation, autoCovariance, aaComp_1, cruciani_1
#
# 依赖: pandas, openpyxl
# 注意: demo.csv 在 WSL 里实为 xlsx 格式，需用 openpyxl 读

import argparse
import pathlib
import sys
import pandas as pd
import numpy as np

DEMO_PATH = pathlib.Path(__file__).parent.parent.parent / "scripts" / "neotimmuml" / ".."
# 实际路径拼法：此文件在 scripts/neotimmuml/ 下
_HERE = pathlib.Path(__file__).parent
DEMO_XLSX = pathlib.Path("/root/quantimmu/tools_repos/NeoTImmuML/demo.csv")  # WSL 路径
# Windows 备用路径（若在 Windows 跑）
DEMO_XLSX_WIN = pathlib.Path(r"\\wsl$\Ubuntu\root\quantimmu\tools_repos\NeoTImmuML\demo.csv")

TMP_DIR = _HERE / "verify_tmp"
DEMO_PEPTIDES_OUT = TMP_DIR / "demo_peptides.txt"
R_FEATURES_CSV = TMP_DIR / "demo_r_features.csv"

FEATURE_COLS = (
    ["mol_weight", "isoelectric_point", "boman_index", "charge",
     "hydrophobicity_index", "lengthpep", "instability_index", "hmoment",
     "membpos.H", "membpos.uH", "aindex", "autoCorrelation", "autoCovariance",
     "aaComp_1"]
    + [f"blosum_{i}" for i in range(1, 11)]
    + ["cruciani_1"]
    + [f"fasgai_{i}" for i in range(1, 7)]
    + [f"kidera_{i}" for i in range(1, 11)]
    + [f"mswhim_{i}" for i in range(1, 4)]
    + [f"protFP_{i}" for i in range(1, 9)]
    + [f"stscale_{i}" for i in range(1, 9)]
    + [f"tscale_{i}" for i in range(1, 6)]
    + [f"vhse_{i}" for i in range(1, 9)]
    + [f"zscale_{i}" for i in range(1, 6)]
)


def load_demo():
    """尝试从多个路径加载 demo.csv（实为 xlsx）"""
    for p in [DEMO_XLSX, DEMO_XLSX_WIN]:
        try:
            df = pd.read_excel(str(p), engine="openpyxl")
            print(f"[INFO] Loaded demo from: {p}, shape={df.shape}")
            return df
        except Exception as e:
            continue
    # 若均失败，尝试 Windows 本地备份（若主线已从 WSL 复制过来）
    local_path = _HERE / "verify_tmp" / "demo.xlsx"
    if local_path.exists():
        df = pd.read_excel(str(local_path), engine="openpyxl")
        print(f"[INFO] Loaded demo from local copy: {local_path}")
        return df
    raise FileNotFoundError(
        "Cannot find demo.csv. Options:\n"
        "  A) Run from WSL where /root/quantimmu/... exists\n"
        "  B) Copy demo.csv to scripts/neotimmuml/verify_tmp/demo.xlsx\n"
        "     (from WSL: cp ~/quantimmu/tools_repos/NeoTImmuML/demo.csv "
        "     /mnt/d/YJ-Agent/project/meeting/QuantImmuBench/scripts/neotimmuml/verify_tmp/demo.xlsx)"
    )


def cmd_extract(args):
    """从 demo.csv 提取肽段列表"""
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    df = load_demo()
    peptides = df["Peptide"].dropna().astype(str).str.strip().tolist()
    with open(DEMO_PEPTIDES_OUT, "w") as f:
        for p in peptides:
            f.write(p + "\n")
    print(f"[DONE] Extracted {len(peptides)} peptides → {DEMO_PEPTIDES_OUT}")
    print()
    print("Next: run R to compute features:")
    print(f"  Rscript calc_78_features.R --input {DEMO_PEPTIDES_OUT} --output {R_FEATURES_CSV}")


def cmd_compare(args):
    """比对 R 算出的 78 特征 vs demo.csv 自带值"""
    if not R_FEATURES_CSV.exists():
        raise FileNotFoundError(f"R features not found: {R_FEATURES_CSV}\n  Please run Step2 first")

    demo_df = load_demo()
    r_df = pd.read_csv(str(R_FEATURES_CSV))

    # 对齐（按 Peptide）
    merged = demo_df.merge(r_df, on="Peptide", suffixes=("_demo", "_r"))
    print(f"[INFO] Matched {len(merged)} peptides")

    # 逐列比对
    print("\n=== Feature Comparison (demo vs R) ===")
    print(f"{'Feature':<25} {'demo_mean':>12} {'r_mean':>12} {'mean_abs_diff':>15} {'max_abs_diff':>13} {'status'}")
    print("-" * 90)

    flagged = []
    for col in FEATURE_COLS:
        demo_col = col + "_demo"
        r_col = col + "_r"
        if demo_col not in merged.columns or r_col not in merged.columns:
            print(f"  {col:<25} MISSING in one of the files")
            continue

        demo_vals = merged[demo_col].astype(float)
        r_vals    = merged[r_col].astype(float)
        abs_diff  = (demo_vals - r_vals).abs()

        # 使用相对误差（若 demo 均值接近 0 则用绝对差）
        denom = demo_vals.abs().mean()
        if denom > 1e-6:
            rel_err = abs_diff.mean() / denom
        else:
            rel_err = abs_diff.mean()

        status = "OK" if rel_err < 0.01 else ("WARN" if rel_err < 0.1 else "MISMATCH")
        if status != "OK":
            flagged.append((col, rel_err, abs_diff.max()))

        print(f"  {col:<25} {demo_vals.mean():>12.4f} {r_vals.mean():>12.4f} "
              f"{abs_diff.mean():>15.6f} {abs_diff.max():>13.6f}  {status}")

    print()
    if flagged:
        print(f"[WARN] {len(flagged)} features with >1% relative error:")
        for col, rel, maxd in sorted(flagged, key=lambda x: -x[1]):
            print(f"  {col}: rel_err={rel:.3f}, max_abs_diff={maxd:.6f}")
        print()
        print("  Action: Check R function parameters for flagged features.")
        print("  Likely candidates: autoCorrelation/autoCovariance (aaindex param),")
        print("                     aaComp_1 (which AA index), cruciani_1 (which PC)")
    else:
        print("[OK] All features match within 1% relative error!")
        print("     R parameters for calc_78_features.R are confirmed correct.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Cross-validate R-computed features against NeoTImmuML demo.csv"
    )
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("extract", help="Extract peptides from demo.csv").set_defaults(func=cmd_extract)
    sub.add_parser("compare", help="Compare R features vs demo.csv values").set_defaults(func=cmd_compare)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)
    args.func(args)
