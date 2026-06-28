"""
parse_output.py — QuantImmuBench §Tier-0  MHCflurry 2.0 结果回贴
服务项目：quantimmu-bench §Tier-0 lever=部署MHCflurry 扩张v2第一波

功能：
  1. 读 mhcflurry_raw.csv（run_mhcflurry.py 的输出）
     列: peptide, HLA_Allele, affinity, presentation_score, processing_score
  2. 读 universe.csv（34247 行，4-key = Dataset/Peptide_ID/HLA_Allele/MT_Subpeptide 唯一）
  3. 建 (peptide, HLA_Allele) → 分数 的查找表
  4. 对 universe 每行：
       MT 分数: (MT_Subpeptide, HLA_Allele) → lookup
       WT 分数: (WT_Subpeptide, HLA_Allele) → lookup
  5. 方向归一（越高越免疫原）：
       presentation_score: 已是越高越强 → 直接用作 MT/WT_MHCflurry_presentation
       affinity(nM): 越低越强 → 取负 → MT/WT_MHCflurry_affinity_neg = -affinity
  6. 输出 MHCflurry_DS1DS2_scores.csv（34247 行，含 NaN for 未查到/不支持 allele）

输入：
  HPC/deploy/mhcflurry/mhcflurry_raw.csv
  scripts/out/newtools/universe.csv

输出：
  scripts/out/newtools/MHCflurry_DS1DS2_scores.csv

输出列（固定）：
  Dataset, Peptide_ID, HLA_Allele, MT_Subpeptide,
  MT_MHCflurry_presentation, WT_MHCflurry_presentation,
  MT_MHCflurry_affinity_neg, WT_MHCflurry_affinity_neg

用法：
  python parse_output.py [--raw PATH] [--universe PATH] [--out PATH]
"""

import argparse
import pathlib
import sys

import pandas as pd

# ---------------------------------------------------------------------------
# 路径默认值
# ---------------------------------------------------------------------------
SCRIPT_DIR  = pathlib.Path(__file__).parent.resolve()
PROJECT_DIR = SCRIPT_DIR.parents[2]   # QuantImmuBench/

DEFAULT_RAW      = SCRIPT_DIR   / "mhcflurry_raw.csv"
DEFAULT_UNIVERSE = PROJECT_DIR  / "scripts" / "out" / "newtools" / "universe.csv"
DEFAULT_OUT      = PROJECT_DIR  / "scripts" / "out" / "newtools" / "MHCflurry_DS1DS2_scores.csv"

# 输出列（固定 schema，对齐其他新工具 parse 脚本）
OUTPUT_COLS = [
    "Dataset", "Peptide_ID", "HLA_Allele", "MT_Subpeptide",
    "MT_MHCflurry_presentation", "WT_MHCflurry_presentation",
    "MT_MHCflurry_affinity_neg", "WT_MHCflurry_affinity_neg",
]


# ---------------------------------------------------------------------------
# 主逻辑
# ---------------------------------------------------------------------------

def build_lookup(raw_df: pd.DataFrame) -> dict:
    """
    构建 (peptide, HLA_Allele) → {presentation_score, affinity, processing_score} 查找表。
    若同一 (peptide, allele) 有多条（不应出现），取第一条。
    """
    lookup = {}
    for _, row in raw_df.iterrows():
        key = (row["peptide"], row["HLA_Allele"])
        if key not in lookup:
            lookup[key] = {
                "presentation_score": row.get("presentation_score", float("nan")),
                "affinity":           row.get("affinity",           float("nan")),
                "processing_score":   row.get("processing_score",   float("nan")),
            }
    return lookup


def get_score(lookup: dict, peptide: str, allele: str) -> tuple:
    """
    查表返回 (presentation_score, affinity_neg)。
    presentation_score: 越高越强，直接用。
    affinity_neg: -affinity(nM)，越高越强（原始越低越强取负）。
    未找到 → (NaN, NaN)。
    """
    import math
    NAN = float("nan")
    entry = lookup.get((peptide, allele))
    if entry is None:
        return NAN, NAN
    ps = entry["presentation_score"]
    af = entry["affinity"]
    af_neg = -af if (af is not None and not math.isnan(af)) else NAN
    return ps, af_neg


def parse(raw_path: pathlib.Path, universe_path: pathlib.Path, out_path: pathlib.Path) -> None:
    # --- 读原始预测结果 ---
    print(f"[parse] 读 raw: {raw_path}")
    raw_df = pd.read_csv(raw_path, encoding="utf-8")
    print(f"[parse]   shape: {raw_df.shape}  列: {list(raw_df.columns)}")

    # 检查必需列
    for col in ["peptide", "HLA_Allele", "affinity", "presentation_score"]:
        if col not in raw_df.columns:
            print(f"[parse] ERROR: raw CSV 缺列 '{col}'，实际列: {list(raw_df.columns)}", file=sys.stderr)
            sys.exit(1)

    # --- 构建查找表 ---
    lookup = build_lookup(raw_df)
    print(f"[parse] 查找表条目数: {len(lookup)}")

    # --- 读 universe ---
    print(f"[parse] 读 universe: {universe_path}")
    univ = pd.read_csv(universe_path, encoding="utf-8")
    print(f"[parse]   shape: {univ.shape}  列: {list(univ.columns)}")
    if len(univ) != 34247:
        print(f"[parse] WARNING: universe 行数 {len(univ)} ≠ 期望 34247", file=sys.stderr)

    # --- 回贴 MT / WT 分数 ---
    mt_pres_list    = []
    wt_pres_list    = []
    mt_afneg_list   = []
    wt_afneg_list   = []

    for _, row in univ.iterrows():
        hla = row["HLA_Allele"]
        mt_pep = str(row["MT_Subpeptide"]).strip() if pd.notna(row["MT_Subpeptide"]) else ""
        wt_pep = str(row["WT_Subpeptide"]).strip() if pd.notna(row["WT_Subpeptide"]) else ""

        # MT
        mt_ps, mt_afneg = get_score(lookup, mt_pep, hla) if mt_pep else (float("nan"), float("nan"))
        # WT
        wt_ps, wt_afneg = get_score(lookup, wt_pep, hla) if wt_pep else (float("nan"), float("nan"))

        mt_pres_list.append(mt_ps)
        wt_pres_list.append(wt_ps)
        mt_afneg_list.append(mt_afneg)
        wt_afneg_list.append(wt_afneg)

    # --- 组装输出 DataFrame ---
    out_df = univ[["Dataset", "Peptide_ID", "HLA_Allele", "MT_Subpeptide"]].copy()
    out_df["MT_MHCflurry_presentation"] = mt_pres_list
    out_df["WT_MHCflurry_presentation"] = wt_pres_list
    out_df["MT_MHCflurry_affinity_neg"] = mt_afneg_list
    out_df["WT_MHCflurry_affinity_neg"] = wt_afneg_list

    # --- 统计覆盖率 ---
    n_total = len(out_df)
    n_mt_filled = out_df["MT_MHCflurry_presentation"].notna().sum()
    n_wt_filled = out_df["WT_MHCflurry_presentation"].notna().sum()
    print(f"\n[parse] == 覆盖统计 ==")
    print(f"  总行数:                     {n_total}")
    print(f"  MT_MHCflurry_presentation 非NaN: {n_mt_filled} ({100*n_mt_filled/n_total:.1f}%)")
    print(f"  WT_MHCflurry_presentation 非NaN: {n_wt_filled} ({100*n_wt_filled/n_total:.1f}%)")

    if n_mt_filled == 0:
        print("[parse] WARNING: MT 分数全为 NaN，请检查 raw CSV 和 universe 的 (peptide, HLA) 对应关系。", file=sys.stderr)

    # --- 写出 ---
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_df[OUTPUT_COLS].to_csv(out_path, index=False, encoding="utf-8", lineterminator="\n")
    print(f"\n[parse] 写出 {len(out_df)} 行 → {out_path}")

    # --- 方向归一确认 ---
    print("\n[parse] 方向归一说明：")
    print("  MT_MHCflurry_presentation:  原始 presentation_score（0-1），越高越强，直接使用。")
    print("  MT_MHCflurry_affinity_neg:  = -affinity(nM)，原始越低越强，取负后越高越强，与其他列方向一致。")
    print("  计算 Spearman 时直接用这两列（越高越免疫原）。")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="MHCflurry 结果回贴 universe 全集（MT+WT 双打分 + 方向归一）"
    )
    parser.add_argument(
        "--raw",
        default=str(DEFAULT_RAW),
        help="mhcflurry_raw.csv 路径（run_mhcflurry.py 生成）",
    )
    parser.add_argument(
        "--universe",
        default=str(DEFAULT_UNIVERSE),
        help="universe.csv 路径（scripts/out/newtools/universe.csv）",
    )
    parser.add_argument(
        "--out",
        default=str(DEFAULT_OUT),
        help="输出 MHCflurry_DS1DS2_scores.csv 路径",
    )
    args = parser.parse_args()

    raw_path      = pathlib.Path(args.raw)
    universe_path = pathlib.Path(args.universe)
    out_path      = pathlib.Path(args.out)

    if not raw_path.exists():
        print(f"[parse] ERROR: raw 文件不存在: {raw_path}", file=sys.stderr)
        print("  请先运行: python run_mhcflurry.py", file=sys.stderr)
        sys.exit(1)
    if not universe_path.exists():
        print(f"[parse] ERROR: universe 文件不存在: {universe_path}", file=sys.stderr)
        sys.exit(1)

    parse(raw_path, universe_path, out_path)


if __name__ == "__main__":
    main()
