"""
parse_output.py — QuantImmuBench §工具部署  andy90 结果回贴 universe
服务项目：quantimmu-bench §工具部署 lever=免疫原补位（补到 20）

功能：
  1. 读 andy90_raw.csv（run_andy90.py 汇总）
     列: HLA, peptide, amplitude, immunogenic
  2. 读 universe.csv（34247 行；2-key = (Subpeptide, HLA_Allele)，MT/WT 双查）
  3. 建 (peptide_upper, HLA_nostar) → amplitude 查找表（HLA-matched，非 HLA-agnostic）
  4. 对 universe 每行：
       MT: lookup[(MT_Subpeptide, HLA_Allele)]  → MT_Andy90
       WT: lookup[(WT_Subpeptide, HLA_Allele)]  → WT_Andy90
  5. 12-14mer / netMHCpan 未支持 allele / 未打分 → NaN
  6. 输出 Andy90ImmPred_DS1DS2_scores.csv（34247 行，NaN 覆盖缺失）

输入：
  HPC/deploy/andy90_immpred/andy90_raw.csv     ← run_andy90.py 产生
  scripts/out/newtools/universe.csv

输出：
  scripts/out/newtools/Andy90ImmPred_DS1DS2_scores.csv

输出列（固定 schema）：
  Dataset, Peptide_ID, HLA_Allele, MT_Subpeptide, MT_Andy90, WT_Andy90

方向说明（官方 src/predict_amp.R 核实 2026-06-29）：
  amplitude = self*foreign/binding，amp > 7024 → immunogenic=YES。
  amplitude 越高越免疫原 → 直接作为 MT_Andy90 / WT_Andy90，无需翻转。

HLA 归一：andy90_raw 的 HLA 与 universe 的 HLA_Allele 两侧都去星（replace '*'）后匹配，
  规避 netMHCpan 输出 allele 是否带星的不确定性（如 HLA-A*03:01 vs HLA-A03:01）。

用法：
  python parse_output.py [--raw PATH] [--universe PATH] [--out PATH]
"""

import argparse
import pathlib
import sys

import pandas as pd

SCRIPT_DIR  = pathlib.Path(__file__).parent.resolve()
PROJECT_DIR = SCRIPT_DIR.parents[2]   # QuantImmuBench/

DEFAULT_RAW      = SCRIPT_DIR  / "andy90_raw.csv"
DEFAULT_UNIVERSE = PROJECT_DIR / "scripts" / "out" / "newtools" / "universe.csv"
DEFAULT_OUT      = PROJECT_DIR / "scripts" / "out" / "newtools" / "Andy90ImmPred_DS1DS2_scores.csv"

OUTPUT_COLS = [
    "Dataset", "Peptide_ID", "HLA_Allele", "MT_Subpeptide",
    "MT_Andy90", "WT_Andy90",
]


def norm_hla(h: str) -> str:
    """去星归一：HLA-A*03:01 → HLA-A03:01（两侧统一，规避带星/不带星差异）。"""
    return str(h).replace("*", "").strip()


def build_lookup(raw_path: pathlib.Path) -> dict:
    """读 andy90_raw.csv，建 (peptide_upper, HLA_nostar) → amplitude 字典。"""
    raw_df = pd.read_csv(raw_path, encoding="utf-8")
    print(f"[parse] raw 输入: {len(raw_df)} 行，列: {list(raw_df.columns)}")

    for col in ("HLA", "peptide", "amplitude"):
        if col not in raw_df.columns:
            print(f"[parse] ERROR: raw CSV 缺 '{col}' 列，实际列: {list(raw_df.columns)}", file=sys.stderr)
            sys.exit(1)

    lookup: dict[tuple[str, str], float] = {}
    n_dup = 0
    for _, row in raw_df.iterrows():
        pep = str(row["peptide"]).strip().upper()
        hla = norm_hla(row["HLA"])
        amp = row["amplitude"]
        if pd.isna(amp):
            continue
        try:
            amp = float(amp)
        except (ValueError, TypeError):
            continue
        key = (pep, hla)
        if key in lookup:
            n_dup += 1
        else:
            lookup[key] = amp

    if n_dup > 0:
        print(f"[parse] WARNING: {n_dup} 个重复 (peptide,HLA)（已取首条）", file=sys.stderr)
    print(f"[parse] 查找表条目: {len(lookup)} 个唯一 (肽,HLA) 对")
    return lookup


def parse(raw_path: pathlib.Path, universe_path: pathlib.Path, out_path: pathlib.Path) -> None:
    print(f"[parse] 读 raw: {raw_path}")
    lookup = build_lookup(raw_path)

    print(f"[parse] 读 universe: {universe_path}")
    univ = pd.read_csv(universe_path, encoding="utf-8")
    print(f"[parse]   shape: {univ.shape}  列: {list(univ.columns)}")
    if len(univ) != 34247:
        print(f"[parse] WARNING: universe 行数 {len(univ)} ≠ 期望 34247", file=sys.stderr)

    for col in ["Dataset", "Peptide_ID", "HLA_Allele", "MT_Subpeptide"]:
        if col not in univ.columns:
            print(f"[parse] ERROR: universe 缺列 '{col}'", file=sys.stderr)
            sys.exit(1)
    has_wt = "WT_Subpeptide" in univ.columns

    mt_scores, wt_scores = [], []
    n_mt_hit = n_mt_nan = n_wt_hit = n_wt_nan = 0
    NAN = float("nan")

    for _, row in univ.iterrows():
        hla = norm_hla(row["HLA_Allele"])

        mt_pep = str(row["MT_Subpeptide"]).strip().upper() if pd.notna(row["MT_Subpeptide"]) else ""
        mt_score = lookup.get((mt_pep, hla), NAN) if mt_pep else NAN
        if pd.isna(mt_score):
            n_mt_nan += 1
        else:
            n_mt_hit += 1
        mt_scores.append(mt_score)

        if has_wt:
            wt_pep = str(row["WT_Subpeptide"]).strip().upper() if pd.notna(row["WT_Subpeptide"]) else ""
            wt_score = lookup.get((wt_pep, hla), NAN) if wt_pep else NAN
            if pd.isna(wt_score):
                n_wt_nan += 1
            else:
                n_wt_hit += 1
            wt_scores.append(wt_score)
        else:
            wt_scores.append(NAN)

    out_df = univ[["Dataset", "Peptide_ID", "HLA_Allele", "MT_Subpeptide"]].copy()
    out_df["MT_Andy90"] = mt_scores
    out_df["WT_Andy90"] = wt_scores

    n_total = len(out_df)
    n_mt_filled = out_df["MT_Andy90"].notna().sum()
    n_wt_filled = out_df["WT_Andy90"].notna().sum()

    print(f"\n[parse] == 覆盖统计 ==")
    print(f"  总行数:               {n_total}")
    print(f"  MT_Andy90 非NaN:      {n_mt_filled} ({100 * n_mt_filled / n_total:.1f}%)")
    print(f"  WT_Andy90 非NaN:      {n_wt_filled} ({100 * n_wt_filled / n_total:.1f}%)")
    print(f"  MT 命中:              {n_mt_hit}")
    print(f"  MT NaN（缺/超长/未支持allele）: {n_mt_nan}")
    print(f"  WT 命中:              {n_wt_hit}")
    print(f"  WT NaN:               {n_wt_nan}")

    if n_mt_filled == 0:
        print("[parse] WARNING: MT_Andy90 全为 NaN，检查 andy90_raw.csv 与 universe 的肽/HLA 对应。",
              file=sys.stderr)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_df[OUTPUT_COLS].to_csv(out_path, index=False, encoding="utf-8", lineterminator="\n")
    print(f"\n[parse] 写出 {len(out_df)} 行 → {out_path}")

    print("\n[parse] 方向说明：")
    print("  MT_Andy90 / WT_Andy90: amplitude = self*foreign/binding，越高越免疫原，直接用（无需翻转）。")
    print("[parse] HLA-matched：分数依赖 (肽,HLA) 对，同肽不同 allele 取各自值（非 HLA-agnostic）。")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="andy90 结果回贴 universe（MT+WT 双打分，按 (肽,HLA) 匹配）"
    )
    parser.add_argument("--raw", default=str(DEFAULT_RAW),
                        help="andy90_raw.csv 路径（run_andy90.py 生成）")
    parser.add_argument("--universe", default=str(DEFAULT_UNIVERSE),
                        help="universe.csv 路径")
    parser.add_argument("--out", default=str(DEFAULT_OUT),
                        help="输出 Andy90ImmPred_DS1DS2_scores.csv 路径")
    args = parser.parse_args()

    raw_path      = pathlib.Path(args.raw)
    universe_path = pathlib.Path(args.universe)
    out_path      = pathlib.Path(args.out)

    if not raw_path.exists():
        print(f"[parse] ERROR: raw 文件不存在: {raw_path}", file=sys.stderr)
        print("  请先运行: python run_andy90.py --repo ... --netmhcpan ...", file=sys.stderr)
        sys.exit(1)
    if not universe_path.exists():
        print(f"[parse] ERROR: universe 文件不存在: {universe_path}", file=sys.stderr)
        sys.exit(1)

    parse(raw_path, universe_path, out_path)


if __name__ == "__main__":
    main()
