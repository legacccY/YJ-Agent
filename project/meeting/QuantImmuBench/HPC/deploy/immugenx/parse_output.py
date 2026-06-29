"""
parse_output.py — QuantImmuBench §工具部署  ImmugenX 结果回贴 universe + 统一 schema
服务项目：quantimmu-bench §工具部署 免疫原侧 lever=补满到 20（I20 = ImmugenX）

功能（镜像 HPC/deploy/munis/parse_output.py 的 HLA-aware MT/WT 双 key join）：
  1. 读 immugenx_raw.csv（run_immugenx.py 输出）
     列: peptide, HLA_Allele, ImmugenX, Stability
  2. 读 universe.csv（34247 行，列：Dataset, Peptide_ID, HLA_Allele, MT_Subpeptide,
     WT_Subpeptide, Window_Size, Position, Elispot）
  3. 建 (peptide, HLA_Allele) → (ImmugenX, Stability) 查找表（HLA_Allele 在 raw 中已是原始
     带星号格式，与 universe 直接匹配，无需转换）
  4. 对 universe 每行：
       MT 分数: (MT_Subpeptide, HLA_Allele) → MT_ImmugenX / MT_ImmugenX_Stability
       WT 分数: (WT_Subpeptide, HLA_Allele) → WT_ImmugenX / WT_ImmugenX_Stability
  5. 方向：ImmugenX/Stability = sigmoid 分 [0-1]，越高越免疫原（方向正确）→ 直接用，不翻转。
  6. 输出 ImmugenX_DS1DS2_scores.csv（34247 行，未匹配/不支持 allele/超长肽 → NaN）

输入：
  HPC/deploy/immugenx/immugenx_raw.csv
  scripts/out/newtools/universe.csv

输出：
  scripts/out/newtools/ImmugenX_DS1DS2_scores.csv

输出列（固定，对齐其他新工具 parse 脚本）：
  Dataset, Peptide_ID, HLA_Allele, MT_Subpeptide,
  MT_ImmugenX, WT_ImmugenX, MT_ImmugenX_Stability, WT_ImmugenX_Stability

  MT/WT_ImmugenX           = ImmugenX 免疫原性分 [0-1]（主指标，越高越免疫原，无需翻转）。
  MT/WT_ImmugenX_Stability = pMHC 稳定性分 [0-1]（副产，同向）。

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

DEFAULT_RAW = SCRIPT_DIR / "immugenx_raw.csv"
DEFAULT_UNIVERSE = PROJECT_DIR / "scripts" / "out" / "newtools" / "universe.csv"
DEFAULT_OUT = PROJECT_DIR / "scripts" / "out" / "newtools" / "ImmugenX_DS1DS2_scores.csv"

# 输出列（固定 schema）
OUTPUT_COLS = [
    "Dataset", "Peptide_ID", "HLA_Allele", "MT_Subpeptide",
    "MT_ImmugenX", "WT_ImmugenX", "MT_ImmugenX_Stability", "WT_ImmugenX_Stability",
]


# ---------------------------------------------------------------------------
# 主逻辑
# ---------------------------------------------------------------------------

def build_lookup(raw_df: pd.DataFrame) -> dict:
    """
    构建 (peptide, HLA_Allele) → (ImmugenX, Stability) 查找表。
    若同一 (peptide, allele) 有多条（不应出现），保留最后一个并计数。
    """
    lookup: dict = {}
    n_dup = 0
    for _, row in raw_df.iterrows():
        key = (row["peptide"], row["HLA_Allele"])
        if key in lookup:
            n_dup += 1
        lookup[key] = (row["ImmugenX"], row["Stability"])
    if n_dup:
        print(f"[parse] WARN: raw 中有 {n_dup} 个重复 (peptide, HLA)，已取最后一个值", file=sys.stderr)
    return lookup


def _safe(v) -> float:
    NAN = float("nan")
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return NAN
    try:
        return float(v)
    except (TypeError, ValueError):
        return NAN


def get_scores(lookup: dict, peptide: str, allele: str):
    """查表返回 (ImmugenX, Stability)（越高越强，不翻转）。未找到 → (NaN, NaN)。"""
    NAN = float("nan")
    pair = lookup.get((peptide, allele))
    if pair is None:
        return NAN, NAN
    return _safe(pair[0]), _safe(pair[1])


def parse(raw_path: pathlib.Path, universe_path: pathlib.Path, out_path: pathlib.Path) -> None:
    # --- 读原始预测结果 ---
    print(f"[parse] 读 raw: {raw_path}")
    raw_df = pd.read_csv(raw_path, dtype={"peptide": str, "HLA_Allele": str})
    raw_df["peptide"] = raw_df["peptide"].str.strip()
    raw_df["HLA_Allele"] = raw_df["HLA_Allele"].str.strip()
    for col in ("ImmugenX", "Stability"):
        if col not in raw_df.columns:
            print(f"[parse] ERROR: raw CSV 缺列 '{col}'，实际列: {list(raw_df.columns)}", file=sys.stderr)
            sys.exit(1)
        raw_df[col] = pd.to_numeric(raw_df[col], errors="coerce")
    print(f"[parse]   shape: {raw_df.shape}  列: {list(raw_df.columns)}")

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

    # --- 回贴 MT / WT 分数（ImmugenX 主 + Stability 副）---
    mt_imm, wt_imm, mt_stab, wt_stab = [], [], [], []

    for _, row in univ.iterrows():
        hla = row["HLA_Allele"]
        mt_pep = row["MT_Subpeptide"]
        wt_pep = row["WT_Subpeptide"]

        # MT
        if pd.isna(mt_pep) or mt_pep == "" or mt_pep.lower() == "nan":
            mt_imm.append(float("nan")); mt_stab.append(float("nan"))
        else:
            a, b = get_scores(lookup, mt_pep, hla)
            mt_imm.append(a); mt_stab.append(b)

        # WT（可能为空）
        if pd.isna(wt_pep) or wt_pep == "" or wt_pep.lower() == "nan":
            wt_imm.append(float("nan")); wt_stab.append(float("nan"))
        else:
            a, b = get_scores(lookup, wt_pep, hla)
            wt_imm.append(a); wt_stab.append(b)

    # --- 组装输出 DataFrame ---
    out_df = univ[["Dataset", "Peptide_ID", "HLA_Allele", "MT_Subpeptide"]].copy()
    out_df["MT_ImmugenX"] = mt_imm
    out_df["WT_ImmugenX"] = wt_imm
    out_df["MT_ImmugenX_Stability"] = mt_stab
    out_df["WT_ImmugenX_Stability"] = wt_stab

    # --- 统计覆盖率 ---
    n_total = len(out_df)
    n_mt = int(out_df["MT_ImmugenX"].notna().sum())
    n_wt = int(out_df["WT_ImmugenX"].notna().sum())
    print(f"\n[parse] == 覆盖统计 ==")
    print(f"  总行数:                 {n_total}")
    print(f"  MT_ImmugenX 非NaN:      {n_mt} ({100*n_mt/n_total:.1f}%)")
    print(f"  WT_ImmugenX 非NaN:      {n_wt} ({100*n_wt/n_total:.1f}%)")

    if n_mt == 0:
        print("[parse] WARNING: MT 分数全为 NaN，请检查 raw CSV 与 universe 的 (peptide, HLA) 对应。", file=sys.stderr)

    # --- 写出 ---
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_df[OUTPUT_COLS].to_csv(out_path, index=False, encoding="utf-8", line_terminator="\n")
    print(f"\n[parse] 写出 {len(out_df)} 行 → {out_path}")

    if n_mt > 0:
        mt_valid = out_df["MT_ImmugenX"].dropna()
        print(f"[parse] MT_ImmugenX 统计: min={mt_valid.min():.4f}  max={mt_valid.max():.4f}  median={mt_valid.median():.4f}")

    # --- 方向确认 ---
    print("\n[parse] 方向说明：")
    print("  MT/WT_ImmugenX = ImmugenX sigmoid 免疫原性分 [0-1]，越高越强（方向正确）。")
    print("  MT/WT_ImmugenX_Stability = pMHC 稳定性副产分 [0-1]，同向。")
    print("  直接用于 Spearman(ρ, ELISpot)（正相关越高越好），无需翻转。")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="ImmugenX 结果回贴 universe 全集（MT+WT 双打分，HLA-aware；ImmugenX 主 + Stability 副）"
    )
    parser.add_argument(
        "--raw",
        default=str(DEFAULT_RAW),
        help="immugenx_raw.csv 路径（run_immugenx.py 生成）",
    )
    parser.add_argument(
        "--universe",
        default=str(DEFAULT_UNIVERSE),
        help="universe.csv 路径（scripts/out/newtools/universe.csv）",
    )
    parser.add_argument(
        "--out",
        default=str(DEFAULT_OUT),
        help="输出 ImmugenX_DS1DS2_scores.csv 路径",
    )
    args = parser.parse_args()

    raw_path = pathlib.Path(args.raw)
    universe_path = pathlib.Path(args.universe)
    out_path = pathlib.Path(args.out)

    if not raw_path.exists():
        print(f"[parse] ERROR: raw 文件不存在: {raw_path}", file=sys.stderr)
        print("  请先运行: python run_immugenx.py", file=sys.stderr)
        sys.exit(1)
    if not universe_path.exists():
        print(f"[parse] ERROR: universe 文件不存在: {universe_path}", file=sys.stderr)
        sys.exit(1)

    parse(raw_path, universe_path, out_path)


if __name__ == "__main__":
    main()
