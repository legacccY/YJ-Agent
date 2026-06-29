"""
parse_output.py  --  QuantImmuBench Seq2Neo immuno 输出解析 + 回贴 universe.csv
服务项目：quantimmu-bench G1 工具补齐 lever=部署 Seq2Neo immunogenicity

功能：
  读 Seq2Neo `cnn_results.csv` → 按 (peptide, HLA) join universe.csv
  输出 Seq2Neo_DS1DS2_scores.csv：universe 全部列 + MT_Seq2Neo + WT_Seq2Neo（34247 行）

用法：
  python parse_output.py [--results <cnn_results.csv>] [--universe <csv>]
                         [--out-csv <csv>] [--score-col <列名>]
                         [--pep-col <列名>] [--hla-col <列名>] [--smoke]

  --smoke: 使用 seq2neo_inputs/seq2neo_out_smoke/cnn_results.csv，
           输出 Seq2Neo_DS1DS2_scores_smoke.csv

红线：本脚本不运行 Seq2Neo。仅解析其产物 cnn_results.csv。

============================================================
输出方向说明（重要，勿删）
============================================================
Seq2Neo CNN 免疫原性分：**值越大越免疫原**（阈值 >0.5；researcher 核实 §6）。
与 benchmark 其他工具方向一致，无需翻转。直接使用。

============================================================
分数 / 列名 TODO（关键，未装实跑前无法确认）
============================================================
# TODO: cnn_results.csv 的确切**分数列名**未实跑确认（researcher 标 TODO）。
#       本脚本默认猜测列名列表见 DEFAULT_SCORE_COLS，命中即用；
#       都不命中则报错并打印实际列名。主线实跑后用 --score-col <真名> 锁定。
# TODO: cnn_results.csv 的 peptide / HLA 列名也未实跑确认。
#       默认猜测见 DEFAULT_PEP_COLS / DEFAULT_HLA_COLS，可用 --pep-col/--hla-col 覆盖。

============================================================
join 策略
============================================================
Seq2Neo 输入 HLA 已被 prep_input.py 转为 `HLA-A02:01`（无星号）格式，
cnn_results.csv 中的 HLA 列**大概率沿用该无星号格式**。
universe.csv 的 HLA_Allele 为 `HLA-A*02:01`（有星号）。
=> 回贴时把 universe 的 HLA_Allele 也用同一函数转无星号，再与 score_map 的 key 匹配。
   key = (peptide, to_seq2neo_hla(HLA_Allele))
12mer / 越界肽长在 prep 阶段被跳过，不在 score_map 中 → 自然回贴 NaN。
# TODO: 若实跑发现 cnn_results.csv 的 HLA 列保留星号，改 --keep-star-join 逻辑（见下）。
"""

import argparse
import csv
import math
import pathlib
import sys

# 复用 prep_input 的 HLA 转换函数，保证 join key 一致
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from prep_input import to_seq2neo_hla  # noqa: E402


# 默认列名猜测（未实跑确认，researcher 标 TODO）
DEFAULT_SCORE_COLS = ["immunogenicity", "Immunogenicity", "score", "Score",
                      "cnn_score", "CNN_Score", "prediction", "Prediction"]
DEFAULT_PEP_COLS = ["Pep", "peptide", "Peptide", "pep", "mt_peptide", "MT_pep"]
DEFAULT_HLA_COLS = ["HLA", "hla", "HLA_Allele", "allele", "Allele", "MHC"]


# ---------------------------------------------------------------------------
# 列名自动定位（带 TODO fallback）
# ---------------------------------------------------------------------------

def _pick_col(fieldnames, override, candidates, what):
    """返回命中的列名。override 优先；否则按 candidates 顺序取第一个命中。"""
    if override:
        if override not in fieldnames:
            raise KeyError(
                f"指定的 {what} 列 '{override}' 不在 cnn_results.csv 中。"
                f"实际列名: {fieldnames}"
            )
        return override
    for c in candidates:
        if c in fieldnames:
            return c
    raise KeyError(
        f"找不到 {what} 列（猜测 {candidates} 均未命中）。\n"
        f"实际列名: {fieldnames}\n"
        f"TODO: 装 Seq2Neo 实跑后用对应 --*-col 参数锁定真列名。"
    )


# ---------------------------------------------------------------------------
# 读 cnn_results.csv → score_map
# ---------------------------------------------------------------------------

def load_cnn_results(
    results_path: pathlib.Path,
    score_col_override: str,
    pep_col_override: str,
    hla_col_override: str,
) -> dict:
    """
    读 Seq2Neo cnn_results.csv，返回 score_map = {(pep, hla_nostar): float(score)}。
    hla_nostar = cnn_results 中 HLA 列原值（已假定为无星号格式）经 to_seq2neo_hla 再规范一次。
    """
    score_map = {}
    with open(results_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []

        pep_col = _pick_col(fieldnames, pep_col_override, DEFAULT_PEP_COLS, "peptide")
        hla_col = _pick_col(fieldnames, hla_col_override, DEFAULT_HLA_COLS, "HLA")
        score_col = _pick_col(fieldnames, score_col_override, DEFAULT_SCORE_COLS, "score")

        print(f"[parse_output] cnn_results.csv 列名: {fieldnames}")
        print(f"[parse_output] 使用列：pep='{pep_col}'  hla='{hla_col}'  score='{score_col}'")

        n_loaded = 0
        n_nan = 0
        for row in reader:
            pep = (row.get(pep_col) or "").strip()
            hla = to_seq2neo_hla((row.get(hla_col) or "").strip())
            val_str = (row.get(score_col) or "").strip()
            if not pep or not hla:
                continue
            try:
                val = float(val_str)
                if math.isnan(val):
                    n_nan += 1
                    continue
            except (ValueError, TypeError):
                n_nan += 1
                continue
            score_map[(pep, hla)] = val
            n_loaded += 1

    print(f"[parse_output] 读入 Seq2Neo 分数: {n_loaded} 条（NaN/空跳过: {n_nan}）")
    return score_map


# ---------------------------------------------------------------------------
# 主逻辑：回贴 universe.csv
# ---------------------------------------------------------------------------

def parse(
    results_path: pathlib.Path,
    universe_path: pathlib.Path,
    out_csv: pathlib.Path,
    score_col_override: str,
    pep_col_override: str,
    hla_col_override: str,
) -> None:
    score_map = load_cnn_results(
        results_path, score_col_override, pep_col_override, hla_col_override
    )

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

        # 输出列：universe 全部列 + MT_Seq2Neo + WT_Seq2Neo
        out_fields = uni_fields + ["MT_Seq2Neo", "WT_Seq2Neo"]
        writer = csv.DictWriter(f_out, fieldnames=out_fields, extrasaction="ignore")
        writer.writeheader()

        for row in reader:
            # universe HLA_Allele = HLA-A*02:01，转无星号与 score_map key 对齐
            hla = to_seq2neo_hla(row["HLA_Allele"].strip())
            mt_pep = row["MT_Subpeptide"].strip()
            wt_pep = row["WT_Subpeptide"].strip()

            mt_score = score_map.get((mt_pep, hla), float("nan"))
            wt_score = score_map.get((wt_pep, hla), float("nan"))

            if not math.isnan(mt_score):
                n_mt_hit += 1
            if wt_pep and not math.isnan(wt_score):
                n_wt_hit += 1

            out_row = dict(row)
            out_row["MT_Seq2Neo"] = "" if math.isnan(mt_score) else round(mt_score, 6)
            out_row["WT_Seq2Neo"] = "" if math.isnan(wt_score) else round(wt_score, 6)
            writer.writerow(out_row)
            n_total += 1

    print(f"[parse_output] 写出: {out_csv}（{n_total} 行）")
    print(f"[parse_output] MT_Seq2Neo 命中: {n_mt_hit}/{n_total} 行有分数")
    print(f"[parse_output] WT_Seq2Neo 命中: {n_wt_hit}/{n_total} 行有分数")
    pct_mt = n_mt_hit / n_total * 100 if n_total else 0.0
    pct_wt = n_wt_hit / n_total * 100 if n_total else 0.0
    print(f"[parse_output] 覆盖率: MT={pct_mt:.1f}%  WT={pct_wt:.1f}%")
    if n_total > 0 and n_mt_hit < n_total * 0.9:
        print(
            "[parse_output] WARNING: MT 覆盖率 < 90%。可能原因：\n"
            "  (a) 12mer/越界肽长在 prep 阶段被跳过（预期，正常）；\n"
            "  (b) cnn_results.csv 的 HLA 列仍含星号 → join 不上（用 --hla-col 核实列名/格式）；\n"
            "  (c) Seq2Neo 对部分 allele/肽长不支持。",
            file=sys.stderr,
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    script_dir = pathlib.Path(__file__).parent
    repo_root = script_dir.parents[2]  # QuantImmuBench/
    default_results = script_dir / "seq2neo_inputs" / "seq2neo_out" / "cnn_results.csv"
    default_universe = repo_root / "scripts" / "out" / "newtools" / "universe.csv"
    default_out = repo_root / "scripts" / "out" / "newtools" / "Seq2Neo_DS1DS2_scores.csv"

    parser = argparse.ArgumentParser(
        description="解析 Seq2Neo cnn_results.csv，回贴 universe.csv → Seq2Neo_DS1DS2_scores.csv"
    )
    parser.add_argument(
        "--results",
        default=str(default_results),
        help="Seq2Neo cnn_results.csv（默认 seq2neo_inputs/seq2neo_out/cnn_results.csv）",
    )
    parser.add_argument(
        "--universe",
        default=str(default_universe),
        help="universe.csv 路径（默认 scripts/out/newtools/universe.csv）",
    )
    parser.add_argument(
        "--out-csv",
        default=str(default_out),
        help="输出 CSV（默认 scripts/out/newtools/Seq2Neo_DS1DS2_scores.csv）",
    )
    parser.add_argument(
        "--score-col",
        default="",
        help="cnn_results.csv 中的分数列名（# TODO 未实跑确认；默认自动猜测）",
    )
    parser.add_argument(
        "--pep-col",
        default="",
        help="cnn_results.csv 中的 peptide 列名（默认自动猜测）",
    )
    parser.add_argument(
        "--hla-col",
        default="",
        help="cnn_results.csv 中的 HLA 列名（默认自动猜测）",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="烟测：使用 seq2neo_out_smoke/cnn_results.csv，输出 *_smoke.csv",
    )
    args = parser.parse_args()

    if args.smoke:
        results_path = script_dir / "seq2neo_inputs" / "seq2neo_out_smoke" / "cnn_results.csv"
        out_csv = repo_root / "scripts" / "out" / "newtools" / "Seq2Neo_DS1DS2_scores_smoke.csv"
    else:
        results_path = pathlib.Path(args.results)
        out_csv = pathlib.Path(args.out_csv)

    universe_path = pathlib.Path(args.universe)

    if not results_path.exists():
        print(
            f"[parse_output] Seq2Neo 输出文件不存在: {results_path}\n"
            "先在 linux/WSL/HPC 运行 python run_seq2neo.py [--smoke] 生成 cnn_results.csv。",
            file=sys.stderr,
        )
        sys.exit(1)

    if not universe_path.exists():
        print(f"[parse_output] universe.csv 不存在: {universe_path}", file=sys.stderr)
        sys.exit(1)

    parse(
        results_path=results_path,
        universe_path=universe_path,
        out_csv=out_csv,
        score_col_override=args.score_col,
        pep_col_override=args.pep_col,
        hla_col_override=args.hla_col,
    )


if __name__ == "__main__":
    main()
