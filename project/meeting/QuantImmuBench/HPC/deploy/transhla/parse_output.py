"""
parse_output.py — QuantImmuBench §工具部署  TransHLA 结果回贴 universe
服务项目：quantimmu-bench §工具部署 P9 lever=补满 30 工具 apples-to-apples

功能（镜像 HPC/deploy/repitope/parse_output.py 的 HLA-agnostic 广播逻辑）：
  1. 读 transhla_raw.csv（run_transhla.py 输出）
     列: peptide, prob, label
  2. 读 universe.csv（34247 行，4-key = Dataset/Peptide_ID/HLA_Allele/MT_Subpeptide 唯一）
  3. 建 peptide → prob 的查找表（HLA-agnostic：仅按肽序列查）
  4. 对 universe 每行：
       MT 分数: peptide_lookup[MT_Subpeptide]  → MT_TransHLA
       WT 分数: peptide_lookup[WT_Subpeptide]  → WT_TransHLA
  5. HLA-agnostic 映射：同一肽对所有 HLA_Allele 行填同值
     → 同肽不同 allele 的行 MT_TransHLA 值相同（caveat 详见 NOTES.md）
  6. <8mer / >14mer 及 run 未打分的肽 → NaN
  7. 输出 TransHLA_DS1DS2_scores.csv（34247 行，NaN 覆盖缺失）

输入：
  HPC/deploy/transhla/transhla_raw.csv      ← run_transhla.py 产生
  scripts/out/newtools/universe.csv

输出：
  scripts/out/newtools/TransHLA_DS1DS2_scores.csv

输出列（固定 schema，对齐其他新工具 parse 脚本）：
  Dataset, Peptide_ID, HLA_Allele, MT_Subpeptide,
  MT_TransHLA, WT_TransHLA

方向说明：
  prob = 「是表位」概率 [0-1]，越高越强（免疫原方向正确）。
  直接作为 MT_TransHLA / WT_TransHLA 使用，无需翻转。

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

DEFAULT_RAW      = SCRIPT_DIR  / "transhla_raw.csv"
DEFAULT_UNIVERSE = PROJECT_DIR / "scripts" / "out" / "newtools" / "universe.csv"
DEFAULT_OUT      = PROJECT_DIR / "scripts" / "out" / "newtools" / "TransHLA_DS1DS2_scores.csv"

# 输出列（固定 schema，对齐其他新工具 parse 脚本）
OUTPUT_COLS = [
    "Dataset", "Peptide_ID", "HLA_Allele", "MT_Subpeptide",
    "MT_TransHLA", "WT_TransHLA",
]


# ---------------------------------------------------------------------------
# 读 raw（transhla_raw.csv）→ 查找表
# ---------------------------------------------------------------------------

def build_lookup(raw_path: pathlib.Path) -> dict:
    """
    读 transhla_raw.csv，建 peptide → prob 字典。
    若同一 peptide 出现多次（不应发生，已去重），取第一条。
    """
    raw_df = pd.read_csv(raw_path, encoding="utf-8")
    print(f"[parse] raw 输入: {len(raw_df)} 行，列: {list(raw_df.columns)}")

    # 验证必需列
    if "peptide" not in raw_df.columns:
        print(f"[parse] ERROR: raw CSV 缺 'peptide' 列，实际列: {list(raw_df.columns)}", file=sys.stderr)
        sys.exit(1)
    if "prob" not in raw_df.columns:
        print(f"[parse] ERROR: raw CSV 缺 'prob' 列，实际列: {list(raw_df.columns)}", file=sys.stderr)
        sys.exit(1)

    lookup: dict[str, float] = {}
    n_dup = 0
    for _, row in raw_df.iterrows():
        pep = str(row["peptide"]).strip()
        score = row["prob"]
        if pd.isna(score):
            continue
        if pep in lookup:
            n_dup += 1
        else:
            lookup[pep] = float(score)

    if n_dup > 0:
        print(f"[parse] WARNING: {n_dup} 个重复 peptide（已取首条）", file=sys.stderr)

    print(f"[parse] 查找表条目: {len(lookup)} 个唯一肽")
    return lookup


# ---------------------------------------------------------------------------
# 主逻辑
# ---------------------------------------------------------------------------

def parse(raw_path: pathlib.Path, universe_path: pathlib.Path, out_path: pathlib.Path) -> None:
    # --- 读 raw → lookup ---
    print(f"[parse] 读 raw: {raw_path}")
    lookup = build_lookup(raw_path)

    # --- 读 universe ---
    print(f"[parse] 读 universe: {universe_path}")
    univ = pd.read_csv(universe_path, encoding="utf-8")
    print(f"[parse]   shape: {univ.shape}  列: {list(univ.columns)}")
    if len(univ) != 34247:
        print(f"[parse] WARNING: universe 行数 {len(univ)} ≠ 期望 34247", file=sys.stderr)

    # 必需列检查
    for col in ["Dataset", "Peptide_ID", "HLA_Allele", "MT_Subpeptide"]:
        if col not in univ.columns:
            print(f"[parse] ERROR: universe 缺列 '{col}'", file=sys.stderr)
            sys.exit(1)
    has_wt = "WT_Subpeptide" in univ.columns

    # --- HLA-agnostic 回贴（按肽序列查，忽略 HLA_Allele）---
    # 同一肽不同 HLA_Allele 行 → 相同 MT_TransHLA 值（此为 HLA-agnostic caveat）
    mt_scores = []
    wt_scores = []

    n_mt_hit = 0
    n_mt_nan = 0
    n_wt_hit = 0
    n_wt_nan = 0

    NAN = float("nan")

    for _, row in univ.iterrows():
        # MT
        mt_pep = str(row["MT_Subpeptide"]).strip() if pd.notna(row["MT_Subpeptide"]) else ""
        mt_score = lookup.get(mt_pep, NAN) if mt_pep else NAN
        if pd.isna(mt_score):
            n_mt_nan += 1
        else:
            n_mt_hit += 1
        mt_scores.append(mt_score)

        # WT
        if has_wt:
            wt_pep = str(row["WT_Subpeptide"]).strip() if pd.notna(row["WT_Subpeptide"]) else ""
            wt_score = lookup.get(wt_pep, NAN) if wt_pep else NAN
            if pd.isna(wt_score):
                n_wt_nan += 1
            else:
                n_wt_hit += 1
            wt_scores.append(wt_score)
        else:
            wt_scores.append(NAN)

    # --- 组装输出 DataFrame ---
    out_df = univ[["Dataset", "Peptide_ID", "HLA_Allele", "MT_Subpeptide"]].copy()
    out_df["MT_TransHLA"] = mt_scores
    out_df["WT_TransHLA"] = wt_scores

    # --- 覆盖统计 ---
    n_total = len(out_df)
    n_mt_filled = out_df["MT_TransHLA"].notna().sum()
    n_wt_filled = out_df["WT_TransHLA"].notna().sum()

    print(f"\n[parse] == 覆盖统计 ==")
    print(f"  总行数:                {n_total}")
    print(f"  MT_TransHLA 非NaN:     {n_mt_filled} ({100 * n_mt_filled / n_total:.1f}%)")
    print(f"  WT_TransHLA 非NaN:     {n_wt_filled} ({100 * n_wt_filled / n_total:.1f}%)")
    print(f"  MT 命中 (查找表):      {n_mt_hit}")
    print(f"  MT NaN（缺 or 超长）:  {n_mt_nan}")
    print(f"  WT 命中 (查找表):      {n_wt_hit}")
    print(f"  WT NaN（缺 or 超长）:  {n_wt_nan}")

    if n_mt_filled == 0:
        print(
            "[parse] WARNING: MT_TransHLA 全为 NaN，请检查 transhla_raw.csv 和 universe 的肽序列对应关系。",
            file=sys.stderr,
        )

    # --- 写出 ---
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_df[OUTPUT_COLS].to_csv(out_path, index=False, encoding="utf-8", lineterminator="\n")
    print(f"\n[parse] 写出 {len(out_df)} 行 → {out_path}")

    # --- 方向 + HLA-agnostic caveat ---
    print("\n[parse] 方向说明：")
    print("  MT_TransHLA:  表位概率 [0-1]，越高越强，直接使用（无需翻转）。")
    print("  WT_TransHLA:  同上，来自 WT_Subpeptide 的独立打分。")
    print("\n[parse] ⚠️ HLA-agnostic caveat：")
    print("  TransHLA 只依赖肽序列，不使用 HLA 信息（首个无需输入 allele 的 epitope detector）。")
    print("  同一肽对所有 HLA_Allele 行填相同 MT_TransHLA / WT_TransHLA 值。")
    print("  benchmark 报告须标注此 caveat（见 NOTES.md §HLA-agnostic，与 Repitope 同）。")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="TransHLA 结果回贴 universe 全集（MT+WT 双打分，HLA-agnostic 映射）"
    )
    parser.add_argument(
        "--raw",
        default=str(DEFAULT_RAW),
        help="transhla_raw.csv 路径（run_transhla.py 生成；默认 HPC/deploy/transhla/transhla_raw.csv）",
    )
    parser.add_argument(
        "--universe",
        default=str(DEFAULT_UNIVERSE),
        help="universe.csv 路径（scripts/out/newtools/universe.csv）",
    )
    parser.add_argument(
        "--out",
        default=str(DEFAULT_OUT),
        help="输出 TransHLA_DS1DS2_scores.csv 路径",
    )
    args = parser.parse_args()

    raw_path      = pathlib.Path(args.raw)
    universe_path = pathlib.Path(args.universe)
    out_path      = pathlib.Path(args.out)

    if not raw_path.exists():
        print(f"[parse] ERROR: raw 文件不存在: {raw_path}", file=sys.stderr)
        print("  请先运行: python run_transhla.py", file=sys.stderr)
        sys.exit(1)
    if not universe_path.exists():
        print(f"[parse] ERROR: universe 文件不存在: {universe_path}", file=sys.stderr)
        sys.exit(1)

    parse(raw_path, universe_path, out_path)


if __name__ == "__main__":
    main()
