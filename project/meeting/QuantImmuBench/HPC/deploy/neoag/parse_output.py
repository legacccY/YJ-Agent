"""
parse_output.py — QuantImmuBench §工具部署  neoag 结果回贴 universe（第 30 工具）
服务项目：quantimmu-bench §工具部署 lever=补满 30 工具最后 1 个免疫原槽（neoag）

功能（对齐 repitope/parse 广播模式，但 key = (MT,WT) 肽-对，不吃 HLA）：
  1. 读 neoag_raw.csv（run_neoag.py 产生；列 mt_peptide, wt_peptide, score）
  2. 读 universe.csv（34247 行；列含 MT_Subpeptide, WT_Subpeptide, HLA_Allele）
  3. 建 (MT_upper, WT_upper) → score 查找表（**肽-对级，HLA-agnostic**）
  4. 对 universe 每行：按 (MT_Subpeptide, WT_Subpeptide) 对查表 → 同对各 HLA 行广播同值
  5. 未匹配（多差异/超长/MT≠WT长度/被 skip）→ NaN
  6. 输出 Neoag_DS1DS2_scores.csv（34247 行）

================== 输出列（固定 schema）==================
  Dataset, Peptide_ID, HLA_Allele, MT_Subpeptide, MT_Neoag, WT_Neoag

  ⚠️ neoag 是 **肽-对级单分数**：模型吃 (mut, wt, 位号) 输出一个 neoantigen 免疫原性分。
     → MT_Neoag = 该 (MT,WT) 对的 neoag 分（这就是「突变肽免疫原性」，benchmark 主用列）。
     → WT_Neoag = **NaN**（neoag 不对 WT 单独打 neoantigen 分；WT 只作参考）。
        保留 WT_Neoag 列只为与其他工具 MT_/WT_ 双列 schema 对齐，结构性全 NaN，
        主窗合表时可按需丢弃。

================== 方向（⚠️TODO 官方未核）==================
  GBM immunogenicity score 一般「越高越免疫原」→ 默认 FLIP=False 直接用。
  ⚠️ 本机无外网未核官方 README 的分数方向；主窗 clone 后核实：
     - 若官方确认越高越免疫原 → 保持 FLIP=False；
     - 若官方分数越低越免疫原 → 设 FLIP=True（取负），与 benchmark「MT_* 越大越强」约定对齐。

输入：
  HPC/deploy/neoag/neoag_raw.csv     ← run_neoag.py 产生
  scripts/out/newtools/universe.csv

输出：
  scripts/out/newtools/Neoag_DS1DS2_scores.csv

用法（主窗跑）：
  python parse_output.py [--raw PATH] [--universe PATH] [--out PATH] [--flip]
"""

import argparse
import pathlib
import sys

import pandas as pd

SCRIPT_DIR  = pathlib.Path(__file__).parent.resolve()
PROJECT_DIR = SCRIPT_DIR.parents[2]   # QuantImmuBench/

DEFAULT_RAW      = SCRIPT_DIR  / "neoag_raw.csv"
DEFAULT_UNIVERSE = PROJECT_DIR / "scripts" / "out" / "newtools" / "universe.csv"
DEFAULT_OUT      = PROJECT_DIR / "scripts" / "out" / "newtools" / "Neoag_DS1DS2_scores.csv"

OUTPUT_COLS = [
    "Dataset", "Peptide_ID", "HLA_Allele", "MT_Subpeptide",
    "MT_Neoag", "WT_Neoag",
]

# ⚠️TODO 官方未核：GBM 分方向。False=越高越免疫原直接用；True=取负翻转。
DEFAULT_FLIP = False


def build_pair_lookup(raw_path: pathlib.Path, flip: bool) -> dict:
    """读 neoag_raw.csv，建 (MT_upper, WT_upper) → score 字典（肽-对级）。"""
    raw_df = pd.read_csv(raw_path, encoding="utf-8")
    print(f"[parse] raw 输入: {len(raw_df)} 行，列: {list(raw_df.columns)}")
    for col in ("mt_peptide", "wt_peptide", "score"):
        if col not in raw_df.columns:
            print(f"[parse] ERROR: raw CSV 缺 '{col}' 列，实际列: {list(raw_df.columns)}", file=sys.stderr)
            sys.exit(1)

    lookup: dict[tuple[str, str], float] = {}
    n_dup = 0
    for _, row in raw_df.iterrows():
        mt = str(row["mt_peptide"]).strip().upper()
        wt = str(row["wt_peptide"]).strip().upper()
        sc = row["score"]
        if pd.isna(sc) or not mt or not wt:
            continue
        try:
            sc = float(sc)
        except (ValueError, TypeError):
            continue
        if flip:
            sc = -sc
        key = (mt, wt)
        if key in lookup:
            n_dup += 1
        else:
            lookup[key] = sc

    if n_dup > 0:
        print(f"[parse] WARNING: {n_dup} 个重复 (MT,WT) 对（已取首条）", file=sys.stderr)
    print(f"[parse] 查找表条目: {len(lookup)} 个唯一 (MT,WT) 对（flip={flip}）")
    return lookup


def parse(raw_path: pathlib.Path, universe_path: pathlib.Path,
          out_path: pathlib.Path, flip: bool) -> None:
    print(f"[parse] 读 raw: {raw_path}")
    lookup = build_pair_lookup(raw_path, flip)

    print(f"[parse] 读 universe: {universe_path}")
    univ = pd.read_csv(universe_path, encoding="utf-8")
    print(f"[parse]   shape: {univ.shape}  列: {list(univ.columns)}")
    if len(univ) != 34247:
        print(f"[parse] WARNING: universe 行数 {len(univ)} ≠ 期望 34247", file=sys.stderr)

    for col in ["Dataset", "Peptide_ID", "HLA_Allele", "MT_Subpeptide"]:
        if col not in univ.columns:
            print(f"[parse] ERROR: universe 缺列 '{col}'", file=sys.stderr)
            sys.exit(1)
    if "WT_Subpeptide" not in univ.columns:
        print("[parse] ERROR: universe 缺 WT_Subpeptide（neoag 需 (MT,WT) 对查表）", file=sys.stderr)
        sys.exit(1)

    NAN = float("nan")
    mt_scores = []
    n_hit = n_nan = 0

    for _, row in univ.iterrows():
        mt = str(row["MT_Subpeptide"]).strip().upper() if pd.notna(row["MT_Subpeptide"]) else ""
        wt = str(row["WT_Subpeptide"]).strip().upper() if pd.notna(row["WT_Subpeptide"]) else ""
        sc = lookup.get((mt, wt), NAN) if (mt and wt) else NAN
        if pd.isna(sc):
            n_nan += 1
        else:
            n_hit += 1
        mt_scores.append(sc)

    out_df = univ[["Dataset", "Peptide_ID", "HLA_Allele", "MT_Subpeptide"]].copy()
    out_df["MT_Neoag"] = mt_scores
    # neoag 不对 WT 单独打 neoantigen 分 → WT_Neoag 结构性 NaN（仅为 schema 对齐保留）
    out_df["WT_Neoag"] = NAN

    n_total = len(out_df)
    n_mt_filled = out_df["MT_Neoag"].notna().sum()

    print(f"\n[parse] == 覆盖统计 ==")
    print(f"  总行数:               {n_total}")
    print(f"  MT_Neoag 非NaN:       {n_mt_filled} ({100 * n_mt_filled / n_total:.1f}%)")
    print(f"  对级命中:             {n_hit}")
    print(f"  NaN（缺/多差异/超长/长度不等）: {n_nan}")
    print(f"  WT_Neoag:             全 NaN（neoag 无独立 WT neoantigen 分，schema 对齐保留）")

    if n_mt_filled == 0:
        print("[parse] WARNING: MT_Neoag 全为 NaN，检查 neoag_raw.csv 与 universe 的 (MT,WT) 对应。",
              file=sys.stderr)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_df[OUTPUT_COLS].to_csv(out_path, index=False, encoding="utf-8", lineterminator="\n")
    print(f"\n[parse] 写出 {len(out_df)} 行 → {out_path}")

    print("\n[parse] 方向说明：")
    print(f"  MT_Neoag: GBM immunogenicity 分（flip={flip}）。⚠️TODO 主窗核官方方向，"
          "越高越免疫原则 flip=False 直接用。")
    print("[parse] ⚠️ HLA-agnostic：neoag 只依赖 (MT,WT,位号)，同对各 HLA 行同值（报告标 caveat，同 Repitope）。")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="neoag 结果回贴 universe（(MT,WT) 对级广播，不吃 HLA）"
    )
    parser.add_argument("--raw", default=str(DEFAULT_RAW),
                        help="neoag_raw.csv 路径（run_neoag.py 生成）")
    parser.add_argument("--universe", default=str(DEFAULT_UNIVERSE),
                        help="universe.csv 路径")
    parser.add_argument("--out", default=str(DEFAULT_OUT),
                        help="输出 Neoag_DS1DS2_scores.csv 路径")
    parser.add_argument("--flip", action="store_true",
                        help="翻转分数方向（取负）。⚠️仅当官方确认分数越低越免疫原时用（默认不翻）")
    args = parser.parse_args()

    raw_path      = pathlib.Path(args.raw)
    universe_path = pathlib.Path(args.universe)
    out_path      = pathlib.Path(args.out)
    flip          = args.flip or DEFAULT_FLIP

    if not raw_path.exists():
        print(f"[parse] ERROR: raw 文件不存在: {raw_path}", file=sys.stderr)
        print("  请先运行: python run_neoag.py --repo ... --rscript ...", file=sys.stderr)
        sys.exit(1)
    if not universe_path.exists():
        print(f"[parse] ERROR: universe 文件不存在: {universe_path}", file=sys.stderr)
        sys.exit(1)

    parse(raw_path, universe_path, out_path, flip)


if __name__ == "__main__":
    main()
