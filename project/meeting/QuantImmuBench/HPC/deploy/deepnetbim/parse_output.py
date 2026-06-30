"""
parse_output.py — QuantImmuBench §工具部署 第20槽  DeepNetBim 结果回贴 + 统一 schema
服务项目：quantimmu-bench §工具部署 lever=补免疫原性组第 20 槽（DeepNetBim）

功能（仿 mhcseqnet/parse_output.py，DeepNetBim immuno_probability 越高越免疫原 → **不翻转**）：
  1. 读 deepnetbim_raw.csv（run_deepnetbim.py 输出）列: mhc, sequence, immuno_probability
     —— mhc 为去星格式（HLA-A02:01）。本脚本 to_universe_allele() 重建带星
        （HLA-A*02:01）以匹配 universe 的 HLA_Allele。
  2. 读 universe.csv（34247 行，列 Dataset, Peptide_ID, HLA_Allele, MT_Subpeptide,
     WT_Subpeptide, Window_Size, Position, Elispot）
  3. 建 (sequence, 带星HLA) → immuno_probability 查找表（HLA-aware：按 (subpeptide, HLA)
     对级查表）
  4. 对 universe 每行：
       MT 分数: (MT_Subpeptide, HLA_Allele) → prob → MT_DeepNetBim
       WT 分数: (WT_Subpeptide, HLA_Allele) → prob → WT_DeepNetBim
       （仅 9mer 子肽能命中；非 9mer 子肽 → NaN，覆盖 ~17%，低覆盖 caveat 见 NOTES）
  5. 方向（重要）：DeepNetBim immuno_probability ∈[0,1]，**越高越免疫原 → 不翻转**，
     直接用。与 benchmark 其他「越大越免疫原」MT_* 列方向一致。
  6. 输出 DeepNetBim_DS1DS2_scores.csv（34247 行，未匹配/非9mer 填 NaN）

输入：
  HPC/deploy/deepnetbim/deepnetbim_raw.csv
  scripts/out/newtools/universe.csv

输出：
  scripts/out/newtools/DeepNetBim_DS1DS2_scores.csv

输出列（固定 schema，严格对齐 MUNIS：4-key + MT/WT 工具列）：
  Dataset, Peptide_ID, HLA_Allele, MT_Subpeptide, MT_DeepNetBim, WT_DeepNetBim

  MT/WT_DeepNetBim = immuno_probability（越高越免疫原，**未翻转**）。

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

DEFAULT_RAW = SCRIPT_DIR / "deepnetbim_raw.csv"
DEFAULT_UNIVERSE = PROJECT_DIR / "scripts" / "out" / "newtools" / "universe.csv"
DEFAULT_OUT = PROJECT_DIR / "scripts" / "out" / "newtools" / "DeepNetBim_DS1DS2_scores.csv"

# 输出列（固定 schema）
OUTPUT_COLS = [
    "Dataset", "Peptide_ID", "HLA_Allele", "MT_Subpeptide",
    "MT_DeepNetBim", "WT_DeepNetBim",
]

MHCI_PREFIXES = ("HLA-A", "HLA-B", "HLA-C")


# ---------------------------------------------------------------------------
# HLA 去星 → 带星（重建 universe 格式）
# ---------------------------------------------------------------------------

def to_universe_allele(mhc: str) -> str:
    """
    DeepNetBim 去星格式 'HLA-A02:01' → universe 带星 'HLA-A*02:01'。
    在单字母基因（HLA-A/B/C）后插入 '*'。已含 '*' 则原样返回。

    与 prep_input.to_deepnetbim_allele 的去星互逆（去星=.replace('*','')）。
    """
    mhc = mhc.strip()
    if "*" in mhc:
        return mhc
    # HLA-A02:01 → 前缀 'HLA-' + 基因字母 + '*' + 其余
    for pfx in MHCI_PREFIXES:
        if mhc.startswith(pfx):
            gene_letter = pfx[-1]          # 'A' / 'B' / 'C'
            rest = mhc[len(pfx):]          # '02:01'
            return f"HLA-{gene_letter}*{rest}"
    return mhc   # 非 MHC-I 前缀 → 原样（不应出现，prep 已过滤）


# ---------------------------------------------------------------------------
# 主逻辑
# ---------------------------------------------------------------------------

def build_lookup(raw_df: pd.DataFrame) -> dict:
    """构建 (sequence, 带星HLA) → immuno_probability 查找表（同键取最后一个并计数）。"""
    lookup: dict = {}
    n_dup = 0
    for _, row in raw_df.iterrows():
        hla_star = to_universe_allele(row["mhc"])
        key = (row["sequence"], hla_star)
        if key in lookup:
            n_dup += 1
        lookup[key] = row["immuno_probability"]
    if n_dup:
        print(f"[parse] WARN: raw 中有 {n_dup} 个重复 (sequence, HLA)，已取最后一个值", file=sys.stderr)
    return lookup


def get_score(lookup: dict, peptide: str, allele: str) -> float:
    """查表返回 immuno_probability（越高越免疫原，不翻转）。未找到或 NaN → NaN。"""
    NAN = float("nan")
    prob = lookup.get((peptide, allele))
    if prob is None or (isinstance(prob, float) and math.isnan(prob)):
        return NAN
    return float(prob)


def parse(raw_path: pathlib.Path, universe_path: pathlib.Path, out_path: pathlib.Path) -> None:
    # --- 读原始预测结果 ---
    print(f"[parse] 读 raw: {raw_path}")
    raw_df = pd.read_csv(raw_path, dtype={"mhc": str, "sequence": str})
    raw_df["mhc"] = raw_df["mhc"].str.strip()
    raw_df["sequence"] = raw_df["sequence"].str.strip()
    print(f"[parse]   shape: {raw_df.shape}  列: {list(raw_df.columns)}")

    for col in ["mhc", "sequence", "immuno_probability"]:
        if col not in raw_df.columns:
            print(f"[parse] ERROR: raw CSV 缺列 '{col}'，实际列: {list(raw_df.columns)}", file=sys.stderr)
            sys.exit(1)
    raw_df["immuno_probability"] = pd.to_numeric(raw_df["immuno_probability"], errors="coerce")

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

    # --- 回贴 MT / WT 分数（HLA-aware：按 (subpeptide, HLA) 对级查表）---
    mt_list = []
    wt_list = []

    for _, row in univ.iterrows():
        hla = row["HLA_Allele"]
        mt_pep = row["MT_Subpeptide"]
        wt_pep = row["WT_Subpeptide"]

        if pd.isna(mt_pep) or mt_pep == "" or mt_pep.lower() == "nan":
            mt_list.append(float("nan"))
        else:
            mt_list.append(get_score(lookup, mt_pep, hla))

        if pd.isna(wt_pep) or wt_pep == "" or wt_pep.lower() == "nan":
            wt_list.append(float("nan"))
        else:
            wt_list.append(get_score(lookup, wt_pep, hla))

    # --- 组装输出 DataFrame ---
    out_df = univ[["Dataset", "Peptide_ID", "HLA_Allele", "MT_Subpeptide"]].copy()
    out_df["MT_DeepNetBim"] = mt_list
    out_df["WT_DeepNetBim"] = wt_list

    # --- 统计覆盖率 ---
    n_total = len(out_df)
    n_mt = int(out_df["MT_DeepNetBim"].notna().sum())
    n_wt = int(out_df["WT_DeepNetBim"].notna().sum())
    print(f"\n[parse] == 覆盖统计（DeepNetBim 仅 9mer，预期低覆盖 ~17%）==")
    print(f"  总行数:                  {n_total}")
    print(f"  MT_DeepNetBim 非NaN:     {n_mt} ({100*n_mt/n_total:.1f}%)")
    print(f"  WT_DeepNetBim 非NaN:     {n_wt} ({100*n_wt/n_total:.1f}%)")

    if n_mt == 0:
        print("[parse] WARNING: MT 分数全为 NaN，请检查 raw CSV 与 universe 的 (peptide, HLA) 对应"
              "（核 to_universe_allele 重建带星是否与 universe 一致）。", file=sys.stderr)

    # --- 写出 ---
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_df[OUTPUT_COLS].to_csv(out_path, index=False, encoding="utf-8")
    print(f"\n[parse] 写出 {len(out_df)} 行 → {out_path}")

    if n_mt > 0:
        mt_valid = out_df["MT_DeepNetBim"].dropna()
        print(f"[parse] MT_DeepNetBim(immuno_prob) 统计: min={mt_valid.min():.4f}  "
              f"max={mt_valid.max():.4f}  median={mt_valid.median():.4f}")

    # --- 方向说明 ---
    print("\n[parse] 方向说明：")
    print("  MT/WT_DeepNetBim = immuno_probability∈[0,1]（越高越免疫原）。")
    print("  **不翻转**，与其他工具列方向一致。计算 Spearman(ρ, ELISpot) 时直接用。")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="DeepNetBim 结果回贴 universe 全集（MT+WT 双打分，方向不翻转，仅 9mer 命中）"
    )
    parser.add_argument(
        "--raw",
        default=str(DEFAULT_RAW),
        help="deepnetbim_raw.csv 路径（run_deepnetbim.py 生成）",
    )
    parser.add_argument(
        "--universe",
        default=str(DEFAULT_UNIVERSE),
        help="universe.csv 路径（scripts/out/newtools/universe.csv）",
    )
    parser.add_argument(
        "--out",
        default=str(DEFAULT_OUT),
        help="输出 DeepNetBim_DS1DS2_scores.csv 路径",
    )
    args = parser.parse_args()

    raw_path = pathlib.Path(args.raw)
    universe_path = pathlib.Path(args.universe)
    out_path = pathlib.Path(args.out)

    if not raw_path.exists():
        print(f"[parse] ERROR: raw 文件不存在: {raw_path}", file=sys.stderr)
        print("  请先运行: python run_deepnetbim.py", file=sys.stderr)
        sys.exit(1)
    if not universe_path.exists():
        print(f"[parse] ERROR: universe 文件不存在: {universe_path}", file=sys.stderr)
        sys.exit(1)

    parse(raw_path, universe_path, out_path)


if __name__ == "__main__":
    main()
