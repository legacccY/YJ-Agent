"""
parse_output.py — QuantImmuBench §工具部署 P10  MHCnuggets 结果回贴 + 统一 schema
服务项目：quantimmu-bench §工具部署 lever=补满30工具呈递槽 P10

功能：
  1. 读 mhcnuggets_raw.csv（run_mhcnuggets.py 的输出）
     列: peptide, HLA_Allele, ic50
  2. 读 universe.csv（34247 行，列：Dataset, Peptide_ID, HLA_Allele, MT_Subpeptide,
     WT_Subpeptide, Window_Size, Position, Elispot）
  3. 建 (peptide, HLA_Allele) → ic50 查找表（HLA_Allele 在 raw 中已是带星号原始格式，
     与 universe 直接匹配，无需转换）
  4. 对 universe 每行：
       MT 分数: (MT_Subpeptide, HLA_Allele) → ic50 → 取负 → MT_MHCnuggets
       WT 分数: (WT_Subpeptide, HLA_Allele) → ic50 → 取负 → WT_MHCnuggets
  5. 方向归一（越高越免疫原）：
       ic50(nM) 越低越强 → 取负 (MT/WT_MHCnuggets = -ic50)，越高越强，与其他工具列方向一致
  6. 输出 MHCnuggets_DS1DS2_scores.csv（34247 行，未匹配/不支持 allele 填 NaN）

输入：
  HPC/deploy/mhcnuggets/mhcnuggets_raw.csv
  scripts/out/newtools/universe.csv

输出：
  scripts/out/newtools/MHCnuggets_DS1DS2_scores.csv

输出列（固定，对齐其他新工具 parse 脚本）：
  Dataset, Peptide_ID, HLA_Allele, MT_Subpeptide, MT_MHCnuggets, WT_MHCnuggets

  MT/WT_MHCnuggets = -ic50(nM)（已方向归一：越高越免疫原）。

用法：
  python parse_output.py [--raw PATH] [--universe PATH] [--out PATH]
"""

import argparse
import math
import pathlib
import sys

import pandas as pd

# ---------------------------------------------------------------------------
# 路径默认值
# ---------------------------------------------------------------------------
SCRIPT_DIR = pathlib.Path(__file__).parent.resolve()
PROJECT_DIR = SCRIPT_DIR.parents[2]   # QuantImmuBench/

DEFAULT_RAW = SCRIPT_DIR / "mhcnuggets_raw.csv"
DEFAULT_UNIVERSE = PROJECT_DIR / "scripts" / "out" / "newtools" / "universe.csv"
DEFAULT_OUT = PROJECT_DIR / "scripts" / "out" / "newtools" / "MHCnuggets_DS1DS2_scores.csv"

# 输出列（固定 schema）
OUTPUT_COLS = [
    "Dataset", "Peptide_ID", "HLA_Allele", "MT_Subpeptide",
    "MT_MHCnuggets", "WT_MHCnuggets",
]


# ---------------------------------------------------------------------------
# 主逻辑
# ---------------------------------------------------------------------------

def build_lookup(raw_df: pd.DataFrame) -> dict:
    """
    构建 (peptide, HLA_Allele) → ic50 查找表。
    若同一 (peptide, allele) 有多条（不应出现），保留最后一个并计数。
    """
    lookup: dict[tuple[str, str], float] = {}
    n_dup = 0
    for _, row in raw_df.iterrows():
        key = (row["peptide"], row["HLA_Allele"])
        if key in lookup:
            n_dup += 1
        lookup[key] = row["ic50"]
    if n_dup:
        print(f"[parse] WARN: raw 中有 {n_dup} 个重复 (peptide, HLA)，已取最后一个值", file=sys.stderr)
    return lookup


def get_score_neg(lookup: dict, peptide: str, allele: str) -> float:
    """
    查表返回 -ic50（越高越强）。未找到或 ic50 为 NaN → NaN。
    """
    NAN = float("nan")
    ic50 = lookup.get((peptide, allele))
    if ic50 is None or (isinstance(ic50, float) and math.isnan(ic50)):
        return NAN
    return -float(ic50)


def parse(raw_path: pathlib.Path, universe_path: pathlib.Path, out_path: pathlib.Path) -> None:
    # --- 读原始预测结果 ---
    print(f"[parse] 读 raw: {raw_path}")
    raw_df = pd.read_csv(raw_path, dtype={"peptide": str, "HLA_Allele": str})
    raw_df["peptide"] = raw_df["peptide"].str.strip()
    raw_df["HLA_Allele"] = raw_df["HLA_Allele"].str.strip()
    print(f"[parse]   shape: {raw_df.shape}  列: {list(raw_df.columns)}")

    for col in ["peptide", "HLA_Allele", "ic50"]:
        if col not in raw_df.columns:
            print(f"[parse] ERROR: raw CSV 缺列 '{col}'，实际列: {list(raw_df.columns)}", file=sys.stderr)
            sys.exit(1)

    # --- 构建查找表 ---
    lookup = build_lookup(raw_df)
    print(f"[parse] 查找表条目数: {len(lookup)}")

    # --- 读 universe ---
    print(f"[parse] 读 universe: {universe_path}")
    univ = pd.read_csv(universe_path, dtype=str)
    print(f"[parse]   shape: {univ.shape}  列: {list(univ.columns)}")
    for col in ["Dataset", "Peptide_ID", "HLA_Allele", "MT_Subpeptide", "WT_Subpeptide"]:
        if col not in univ.columns:
            print(f"[parse] ERROR: universe 缺列 {col!r}，实际: {list(univ.columns)}", file=sys.stderr)
            sys.exit(1)
    if len(univ) != 34247:
        print(f"[parse] WARNING: universe 行数 {len(univ)} ≠ 期望 34247", file=sys.stderr)

    univ["MT_Subpeptide"] = univ["MT_Subpeptide"].str.strip()
    univ["WT_Subpeptide"] = univ["WT_Subpeptide"].str.strip()
    univ["HLA_Allele"] = univ["HLA_Allele"].str.strip()

    # --- 回贴 MT / WT 分数 ---
    mt_list = []
    wt_list = []

    for _, row in univ.iterrows():
        hla = row["HLA_Allele"]
        mt_pep = row["MT_Subpeptide"]
        wt_pep = row["WT_Subpeptide"]

        # MT
        if pd.isna(mt_pep) or mt_pep == "" or mt_pep.lower() == "nan":
            mt_list.append(float("nan"))
        else:
            mt_list.append(get_score_neg(lookup, mt_pep, hla))

        # WT（可能为空）
        if pd.isna(wt_pep) or wt_pep == "" or wt_pep.lower() == "nan":
            wt_list.append(float("nan"))
        else:
            wt_list.append(get_score_neg(lookup, wt_pep, hla))

    # --- 组装输出 DataFrame ---
    out_df = univ[["Dataset", "Peptide_ID", "HLA_Allele", "MT_Subpeptide"]].copy()
    out_df["MT_MHCnuggets"] = mt_list
    out_df["WT_MHCnuggets"] = wt_list

    # --- 统计覆盖率 ---
    n_total = len(out_df)
    n_mt = int(out_df["MT_MHCnuggets"].notna().sum())
    n_wt = int(out_df["WT_MHCnuggets"].notna().sum())
    print(f"\n[parse] == 覆盖统计 ==")
    print(f"  总行数:                  {n_total}")
    print(f"  MT_MHCnuggets 非NaN:     {n_mt} ({100*n_mt/n_total:.1f}%)")
    print(f"  WT_MHCnuggets 非NaN:     {n_wt} ({100*n_wt/n_total:.1f}%)")

    if n_mt == 0:
        print("[parse] WARNING: MT 分数全为 NaN，请检查 raw CSV 与 universe 的 (peptide, HLA) 对应。", file=sys.stderr)

    # --- 写出 ---
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_df[OUTPUT_COLS].to_csv(out_path, index=False, encoding="utf-8", lineterminator="\n")
    print(f"\n[parse] 写出 {len(out_df)} 行 → {out_path}")

    if n_mt > 0:
        mt_valid = out_df["MT_MHCnuggets"].dropna()
        print(f"[parse] MT_MHCnuggets(-ic50) 统计: min={mt_valid.min():.1f}  max={mt_valid.max():.1f}  median={mt_valid.median():.1f}")

    # --- 方向归一确认 ---
    print("\n[parse] 方向归一说明：")
    print("  MT/WT_MHCnuggets = -ic50(nM)。原始 ic50 越低越强 → 取负后越高越强，")
    print("  与其他工具列方向一致。计算 Spearman 时直接用（越高越免疫原）。")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="MHCnuggets 结果回贴 universe 全集（MT+WT 双打分 + 方向归一）"
    )
    parser.add_argument(
        "--raw",
        default=str(DEFAULT_RAW),
        help="mhcnuggets_raw.csv 路径（run_mhcnuggets.py 生成）",
    )
    parser.add_argument(
        "--universe",
        default=str(DEFAULT_UNIVERSE),
        help="universe.csv 路径（scripts/out/newtools/universe.csv）",
    )
    parser.add_argument(
        "--out",
        default=str(DEFAULT_OUT),
        help="输出 MHCnuggets_DS1DS2_scores.csv 路径",
    )
    args = parser.parse_args()

    raw_path = pathlib.Path(args.raw)
    universe_path = pathlib.Path(args.universe)
    out_path = pathlib.Path(args.out)

    if not raw_path.exists():
        print(f"[parse] ERROR: raw 文件不存在: {raw_path}", file=sys.stderr)
        print("  请先运行: python run_mhcnuggets.py", file=sys.stderr)
        sys.exit(1)
    if not universe_path.exists():
        print(f"[parse] ERROR: universe 文件不存在: {universe_path}", file=sys.stderr)
        sys.exit(1)

    parse(raw_path, universe_path, out_path)


if __name__ == "__main__":
    main()
