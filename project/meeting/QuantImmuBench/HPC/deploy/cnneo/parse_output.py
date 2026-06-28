"""
parse_output.py — QuantImmuBench §扩张v2  CNNeo 结果回贴 + 统一 schema
服务项目：quantimmu-bench §工具扩张v2 lever=部署CNNeo apples-to-apples

功能：
  1. 读 cnneo_raw_output.csv（列：peptide, hla, score, label）
  2. 读 universe.csv（34247 行，列：Dataset, Peptide_ID, HLA_Allele, MT_Subpeptide,
     WT_Subpeptide, Window_Size, Position, Elispot）
  3. join MT 侧：(MT_Subpeptide, HLA_Allele) → score → MT_CNNeo
  4. join WT 侧：(WT_Subpeptide, HLA_Allele) → score → WT_CNNeo（若 WT 肽在 cnneo 输出中）
  5. 输出 CNNeo_DS1DS2_scores.csv
     列：Dataset, Peptide_ID, HLA_Allele, MT_Subpeptide [, WT_CNNeo], MT_CNNeo
     覆盖全 34247 行，未匹配到 score 的行填 NaN

分数方向：
  score 0-1，越高越免疫原，直接用（run_cnneo.py 输出 softmax class=1 概率，无需翻转）。

join key 设计：
  - MT：(universe.MT_Subpeptide, universe.HLA_Allele) ↔ (cnneo.peptide, cnneo.hla)
  - WT：(universe.WT_Subpeptide, universe.HLA_Allele) ↔ (cnneo.peptide, cnneo.hla)
  HLA 格式：universe 和 cnneo_raw_output 均使用标准 HLA-A*02:01，直接 join 无需转换。

用法：
  python parse_output.py [--cnneo-out <csv>] [--universe <csv>] [--out-csv <csv>]
  默认路径自动定位（相对脚本向上找 scripts/out/newtools/）
"""

import argparse
import pathlib
import sys

import pandas as pd


# ---------------------------------------------------------------------------
# 主逻辑
# ---------------------------------------------------------------------------

def parse_output(
    cnneo_out_path: pathlib.Path,
    universe_path: pathlib.Path,
    out_csv_path: pathlib.Path,
) -> None:
    # ------------------------------------------------------------------
    # 读 CNNeo 推理输出
    # ------------------------------------------------------------------
    if not cnneo_out_path.exists():
        print(
            f"[parse_output] ERROR: cnneo_raw_output.csv 不存在: {cnneo_out_path}\n"
            "  请先运行 run_cnneo.py 产生推理输出。",
            file=sys.stderr,
        )
        sys.exit(1)

    cnneo_df = pd.read_csv(cnneo_out_path, dtype={"peptide": str, "hla": str})
    cnneo_df["peptide"] = cnneo_df["peptide"].str.strip()
    cnneo_df["hla"]     = cnneo_df["hla"].str.strip()

    print(
        f"[parse_output] cnneo_raw_output: {len(cnneo_df)} 行，"
        f"score 有值行: {cnneo_df['score'].notna().sum()}",
        file=sys.stderr,
    )

    # 构建 (peptide, hla) → score 字典（大小写敏感，精确匹配）
    # 同一 (peptide, hla) 若有重复（不应有），保留最后一个，并打印警告
    pair_to_score: dict[tuple[str, str], float] = {}
    n_dup = 0
    for _, row in cnneo_df.iterrows():
        key = (row["peptide"], row["hla"])
        if key in pair_to_score:
            n_dup += 1
        pair_to_score[key] = row["score"]

    if n_dup:
        print(
            f"[parse_output] WARN: cnneo_raw_output 中有 {n_dup} 个重复 (peptide, hla)，"
            "已取最后一个值",
            file=sys.stderr,
        )

    print(
        f"[parse_output] unique (peptide, hla) → score 对: {len(pair_to_score)}",
        file=sys.stderr,
    )

    # ------------------------------------------------------------------
    # 读 universe
    # ------------------------------------------------------------------
    if not universe_path.exists():
        print(
            f"[parse_output] ERROR: universe.csv 不存在: {universe_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    univ = pd.read_csv(universe_path, dtype=str)
    for col in ["Dataset", "Peptide_ID", "HLA_Allele", "MT_Subpeptide", "WT_Subpeptide"]:
        if col not in univ.columns:
            print(
                f"[parse_output] ERROR: universe.csv 缺少列 {col!r}，"
                f"实际列: {list(univ.columns)}",
                file=sys.stderr,
            )
            sys.exit(1)

    univ["MT_Subpeptide"]  = univ["MT_Subpeptide"].str.strip()
    univ["WT_Subpeptide"]  = univ["WT_Subpeptide"].str.strip()
    univ["HLA_Allele"]     = univ["HLA_Allele"].str.strip()

    print(f"[parse_output] universe: {len(univ)} 行", file=sys.stderr)

    # ------------------------------------------------------------------
    # join MT 侧：(MT_Subpeptide, HLA_Allele) → MT_CNNeo
    # ------------------------------------------------------------------
    mt_scores = []
    n_mt_match = 0
    n_mt_nan   = 0

    for _, row in univ.iterrows():
        mt_key = (row["MT_Subpeptide"], row["HLA_Allele"])
        score  = pair_to_score.get(mt_key)
        if score is not None:
            mt_scores.append(score)
            n_mt_match += 1
        else:
            mt_scores.append(float("nan"))
            n_mt_nan += 1

    # ------------------------------------------------------------------
    # join WT 侧：(WT_Subpeptide, HLA_Allele) → WT_CNNeo
    # ------------------------------------------------------------------
    wt_scores = []
    n_wt_match = 0
    n_wt_nan   = 0

    for _, row in univ.iterrows():
        wt_pep = row["WT_Subpeptide"]
        hla    = row["HLA_Allele"]

        # WT 肽可能为空（若 DS 未提供 WT 配对）
        if pd.isna(wt_pep) or wt_pep.strip() == "" or wt_pep.strip().lower() == "nan":
            wt_scores.append(float("nan"))
            n_wt_nan += 1
            continue

        wt_key = (wt_pep.strip(), hla)
        score  = pair_to_score.get(wt_key)
        if score is not None:
            wt_scores.append(score)
            n_wt_match += 1
        else:
            wt_scores.append(float("nan"))
            n_wt_nan += 1

    # ------------------------------------------------------------------
    # 构建输出 DataFrame（4-key + MT_CNNeo + WT_CNNeo）
    # ------------------------------------------------------------------
    out_df = univ[["Dataset", "Peptide_ID", "HLA_Allele", "MT_Subpeptide"]].copy()
    out_df["MT_CNNeo"] = mt_scores
    out_df["WT_CNNeo"] = wt_scores

    # 4-key 保留原始类型（Dataset=str, Peptide_ID=str, HLA_Allele=str, MT_Subpeptide=str）
    # 分数列已为 float（NaN 处理由 pandas 负责）

    # ------------------------------------------------------------------
    # 写输出
    # ------------------------------------------------------------------
    out_csv_path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(out_csv_path, index=False, encoding="utf-8")

    n_mt_not_nan = int(out_df["MT_CNNeo"].notna().sum())
    n_wt_not_nan = int(out_df["WT_CNNeo"].notna().sum())

    print(f"[parse_output] MT_CNNeo 有值行: {n_mt_not_nan}（NaN: {n_mt_nan}）", file=sys.stderr)
    print(f"[parse_output] WT_CNNeo 有值行: {n_wt_not_nan}（NaN: {n_wt_nan}）", file=sys.stderr)

    if n_mt_not_nan > 0:
        mt_valid = out_df["MT_CNNeo"].dropna()
        print(
            f"[parse_output] MT_CNNeo 统计: "
            f"min={mt_valid.min():.4f}, max={mt_valid.max():.4f}, "
            f"mean={mt_valid.mean():.4f}, "
            f">0.5 候选={int((mt_valid > 0.5).sum())} 行",
            file=sys.stderr,
        )

    print(f"[parse_output] 输出: {out_csv_path}（{len(out_df)} 行）", file=sys.stderr)

    if n_mt_nan > 0:
        print(
            f"[parse_output] ⚠️ {n_mt_nan} 行 MT_CNNeo=NaN\n"
            "  可能原因：① cnneo_raw_output.csv 未包含对应 (peptide, hla) 对\n"
            "             ② prep_input.py 时该对被过滤（肽长/格式）\n"
            "             ③ run_cnneo.py 使用了 --smoke 未跑全量",
            file=sys.stderr,
        )

    print("[parse_output] 完成。", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    script_dir = pathlib.Path(__file__).parent
    repo_root  = script_dir.parents[2]   # QuantImmuBench/
    newtools   = repo_root / "scripts" / "out" / "newtools"

    default_cnneo_out = newtools / "cnneo_raw_output.csv"
    default_universe  = newtools / "universe.csv"
    default_out_csv   = newtools / "CNNeo_DS1DS2_scores.csv"

    parser = argparse.ArgumentParser(
        description=(
            "CNNeo 推理结果回贴 universe.csv → CNNeo_DS1DS2_scores.csv\n"
            "（4-key + MT_CNNeo + WT_CNNeo，全 34247 行覆盖，缺值 NaN）"
        )
    )
    parser.add_argument(
        "--cnneo-out",
        default=str(default_cnneo_out),
        help="run_cnneo.py 产生的 cnneo_raw_output.csv（列：peptide,hla,score,label）",
    )
    parser.add_argument(
        "--universe",
        default=str(default_universe),
        help="universe.csv 路径（默认 scripts/out/newtools/universe.csv）",
    )
    parser.add_argument(
        "--out-csv",
        default=str(default_out_csv),
        help="输出路径（默认 scripts/out/newtools/CNNeo_DS1DS2_scores.csv）",
    )
    args = parser.parse_args()

    parse_output(
        cnneo_out_path=pathlib.Path(args.cnneo_out),
        universe_path=pathlib.Path(args.universe),
        out_csv_path=pathlib.Path(args.out_csv),
    )


if __name__ == "__main__":
    main()
