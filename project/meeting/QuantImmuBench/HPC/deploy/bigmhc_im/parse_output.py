"""
parse_output.py  --  QuantImmuBench BigMHC -m=im 输出解析 + 回贴 universe.csv
服务项目：quantimmu-bench 扩张 v2 lever=部署BigMHC immunogenicity

功能：
  读 BigMHC predict.py 输出 .prd（CSV）→ 按 (peptide, HLA_Allele) join universe.csv
  输出 BigMHC_DS1DS2_scores.csv：universe 全部列 + MT_BigMHC + WT_BigMHC（34247 行）

用法：
  python parse_output.py [--prd <file>] [--universe <csv>] [--out-csv <csv>] [--smoke]

  --smoke: 使用 bigmhc_output_smoke.prd，输出 BigMHC_DS1DS2_scores_smoke.csv
"""

# ============================================================
# 输出方向说明（重要，勿删）
# ============================================================
# BigMHC_IM 值域 [0, 1]，sigmoid 激活后的免疫原性概率。
# 高值 = 免疫原性强（与 benchmark 其他工具方向一致）。
# 无需方向翻转，直接使用。
#
# 输出列名：BigMHC_IM
# 已核实来源：src/cli.py _parseModel → args.modelname = "BigMHC_IM"（-m=im 时）
# 输出文件列顺序（.prd CSV）：mhc, pep, tgt, len, BigMHC_IM
#   tgt = NaN（推理时无 label），len = 肽长（int8）
# ============================================================

# ============================================================
# join 策略
# ============================================================
# BigMHC 输入 = uniq_pep_hla.csv 全部 53582 行（MT + WT + BOTH）。
# 输出 .prd 中 mhc 列保留原始输入的 HLA_Allele 字符串（不规范化）。
#
# 查表 key = (peptide, mhc_str)，原始字符串直接匹配：
#   MT_BigMHC = score_map.get((MT_Subpeptide, HLA_Allele), NaN)
#   WT_BigMHC = score_map.get((WT_Subpeptide, HLA_Allele), NaN)
#
# 若 BigMHC 对某 (peptide, allele) 跳过（不支持），则 score_map 无该 key → NaN。
# ============================================================

import argparse
import csv
import math
import pathlib
import sys


# ---------------------------------------------------------------------------
# 读 BigMHC 输出 .prd
# ---------------------------------------------------------------------------

def load_bigmhc_prd(prd_path: pathlib.Path) -> dict:
    """
    读 BigMHC predict.py 输出 CSV（.prd 扩展名实为标准 CSV）。

    输出列（已核实 src/predict.py + src/cli.py）：mhc, pep, tgt, len, BigMHC_IM

    返回：score_map = {(pep, mhc): float(BigMHC_IM)}
    mhc 列存原始输入字符串（HLA-A*02:01 等），直接用于 join。
    """
    score_map = {}
    missing_col_warned = False

    with open(prd_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []

        # 确认 BigMHC_IM 列存在；若不存在则尝试 fallback
        im_col = "BigMHC_IM"
        if im_col not in fieldnames:
            fallback_candidates = [
                c for c in fieldnames
                if "IM" in c or "im" in c or "imm" in c.lower()
            ]
            if fallback_candidates:
                im_col = fallback_candidates[0]
                if not missing_col_warned:
                    print(
                        f"[parse_output] WARNING: 找不到 BigMHC_IM 列，"
                        f"fallback 到 '{im_col}'",
                        file=sys.stderr,
                    )
                    print(f"  实际列名: {fieldnames}", file=sys.stderr)
                    missing_col_warned = True
            else:
                raise KeyError(
                    f"BigMHC 输出中找不到 BigMHC_IM 列，实际列名: {fieldnames}\n"
                    "TODO: 核实 BigMHC 版本与 cli.py _parseModel 中 modelname 赋值。"
                )

        n_loaded = 0
        n_nan = 0
        for row in reader:
            pep = row.get("pep", "").strip()
            mhc = row.get("mhc", "").strip()
            val_str = row.get(im_col, "").strip()
            if not pep or not mhc:
                continue
            try:
                val = float(val_str)
                if math.isnan(val):
                    n_nan += 1
                    continue
            except (ValueError, TypeError):
                n_nan += 1
                continue
            score_map[(pep, mhc)] = val
            n_loaded += 1

    print(f"[parse_output] 读入 BigMHC_IM 分数: {n_loaded} 条（NaN/空跳过: {n_nan}）")
    return score_map


# ---------------------------------------------------------------------------
# 主逻辑：回贴 universe.csv
# ---------------------------------------------------------------------------

def parse(
    prd_path: pathlib.Path,
    universe_path: pathlib.Path,
    out_csv: pathlib.Path,
) -> None:
    """读 BigMHC 输出并 join 到 universe，写 BigMHC_DS1DS2_scores.csv。"""

    # 1. 读 BigMHC 输出 → score_map
    score_map = load_bigmhc_prd(prd_path)

    # 2. 读 universe.csv，回贴分数
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    n_total = 0
    n_mt_hit = 0
    n_wt_hit = 0

    with (
        open(universe_path, newline="", encoding="utf-8") as f_uni,
        open(out_csv, "w", newline="", encoding="utf-8") as f_out,
    ):
        reader = csv.DictReader(f_uni)
        uni_fields = list(reader.fieldnames or [])

        # 输出列：universe 全部列 + MT_BigMHC + WT_BigMHC
        out_fields = uni_fields + ["MT_BigMHC", "WT_BigMHC"]
        writer = csv.DictWriter(f_out, fieldnames=out_fields, extrasaction="ignore")
        writer.writeheader()

        for row in reader:
            hla = row["HLA_Allele"].strip()
            mt_pep = row["MT_Subpeptide"].strip()
            wt_pep = row["WT_Subpeptide"].strip()

            # join：key = (peptide, mhc_str)，与 prep_input.py 写的 mhc 列一致
            mt_score = score_map.get((mt_pep, hla), float("nan"))
            wt_score = score_map.get((wt_pep, hla), float("nan"))

            if not math.isnan(mt_score):
                n_mt_hit += 1
            if wt_pep and not math.isnan(wt_score):
                n_wt_hit += 1

            out_row = dict(row)
            out_row["MT_BigMHC"] = "" if math.isnan(mt_score) else round(mt_score, 6)
            out_row["WT_BigMHC"] = "" if math.isnan(wt_score) else round(wt_score, 6)
            writer.writerow(out_row)
            n_total += 1

    print(f"[parse_output] 写出: {out_csv}（{n_total} 行）")
    print(f"[parse_output] MT_BigMHC 命中: {n_mt_hit}/{n_total} 行有分数")
    print(f"[parse_output] WT_BigMHC 命中: {n_wt_hit}/{n_total} 行有分数")
    pct_mt = n_mt_hit / n_total * 100 if n_total else 0.0
    pct_wt = n_wt_hit / n_total * 100 if n_total else 0.0
    print(f"[parse_output] 覆盖率: MT={pct_mt:.1f}%  WT={pct_wt:.1f}%")
    if n_total > 0 and n_mt_hit < n_total * 0.9:
        print(
            "[parse_output] WARNING: MT 覆盖率 < 90%，"
            "可能有 allele/肽长不被 BigMHC 支持的行。",
            file=sys.stderr,
        )
        print(
            "  建议：检查 bigmhc_output.prd 行数是否 = bigmhc_input.csv 行数（去表头）",
            file=sys.stderr,
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    script_dir = pathlib.Path(__file__).parent
    repo_root = script_dir.parents[2]  # QuantImmuBench/
    default_prd = script_dir / "bigmhc_inputs" / "bigmhc_output.prd"
    default_universe = repo_root / "scripts" / "out" / "newtools" / "universe.csv"
    default_out = repo_root / "scripts" / "out" / "newtools" / "BigMHC_DS1DS2_scores.csv"

    parser = argparse.ArgumentParser(
        description="解析 BigMHC -m=im 输出，回贴 universe.csv → BigMHC_DS1DS2_scores.csv"
    )
    parser.add_argument(
        "--prd",
        default=str(default_prd),
        help="BigMHC 输出 .prd 文件（CSV；默认 bigmhc_inputs/bigmhc_output.prd）",
    )
    parser.add_argument(
        "--universe",
        default=str(default_universe),
        help="universe.csv 路径（默认 scripts/out/newtools/universe.csv）",
    )
    parser.add_argument(
        "--out-csv",
        default=str(default_out),
        help="输出 CSV（默认 scripts/out/newtools/BigMHC_DS1DS2_scores.csv）",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="烟测：使用 bigmhc_output_smoke.prd，"
             "输出 BigMHC_DS1DS2_scores_smoke.csv",
    )
    args = parser.parse_args()

    if args.smoke:
        prd_path = script_dir / "bigmhc_inputs" / "bigmhc_output_smoke.prd"
        out_csv = repo_root / "scripts" / "out" / "newtools" / "BigMHC_DS1DS2_scores_smoke.csv"
    else:
        prd_path = pathlib.Path(args.prd)
        out_csv = pathlib.Path(args.out_csv)

    universe_path = pathlib.Path(args.universe)

    if not prd_path.exists():
        print(
            f"[parse_output] BigMHC 输出文件不存在: {prd_path}\n"
            "先运行 python run_bigmhc_im.py [--smoke] 生成输出。",
            file=sys.stderr,
        )
        sys.exit(1)

    if not universe_path.exists():
        print(
            f"[parse_output] universe.csv 不存在: {universe_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    parse(
        prd_path=prd_path,
        universe_path=universe_path,
        out_csv=out_csv,
    )


if __name__ == "__main__":
    main()
