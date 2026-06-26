"""
parse_icerfire.py  —  QuantImmuBench §Tier-2  ICERFIRE 1.0 输出解析 + 回贴 bb_idx
服务项目：quantimmu-bench §Tier-2 lever=部署ICERFIRE

# ============================================================
# 方向翻转说明（重要，勿删）
# ============================================================
# ICERFIRE 原始输出：%Rank，范围 0-100。
#   0  = 最强免疫原（最危险，排名最前）
#   100 = 最弱免疫原
# 与本 benchmark 其他工具方向（越高越强）相反。
#
# 翻转公式：icerfire_score = 100 - icerfire_rank
#   icerfire_score 100 = 最强免疫原（与其他工具方向一致）
#   icerfire_score 0   = 最弱免疫原
#
# 输出列 icerfire_rank 保留原始值（供溯源/审计），
# icerfire_score 为翻转后统一方向值（用于 apples-to-apples 对比）。
# ============================================================

# ============================================================
# Join 策略说明（重要）
# ============================================================
# ICERFIRE 内部会对输入重排，输出行序≠输入行序。
# 不能用行序（zip）绑定，必须按内容 join：
#   key = (Peptide, wild_type, HLA_nostar)
#   Peptide     = 突变肽  = 我们的 MT_Subpeptide
#   wild_type   = 野生肽  = 我们的 WT_Subpeptide
#   HLA_nostar  = 去星后的 HLA（ICERFIRE 输出 'HLA-A*0201'，index 存 'HLA-A0201'）
#
# 一个 (MT,WT,HLA) 可能对应多个 bb_idx（同子肽对+HLA 出现在多条 backbone 行），
# 全部赋同值，不去重。
# ============================================================
"""

import argparse
import csv
import pathlib
import sys


# ---------------------------------------------------------------------------
# HLA 归一化
# ---------------------------------------------------------------------------

def norm_hla(h: str) -> str:
    """去掉 HLA 字符串中的星号，使 'HLA-A*0201' → 'HLA-A0201'。"""
    return h.replace("*", "")


# ---------------------------------------------------------------------------
# 读 ICERFIRE_predictions.csv → lookup dict
# ---------------------------------------------------------------------------

def read_predictions_lookup(
    predictions_path: pathlib.Path,
) -> dict[tuple[str, str, str], tuple[float, float]]:
    """
    读 ICERFIRE_predictions.csv（逗号分隔，有表头）。

    已知列（实测）：
      Peptide, wild_type, HLA, Pep, Core, icore_start_pos, icore_mut,
      icore_wt_aligned, EL_rank_mut, EL_rank_wt_aligned, icore_similarity_score,
      icore_blsm_mut_score, prediction, %Rank

    取：Peptide, wild_type, HLA, %Rank, prediction。
    HLA 去星归一（norm_hla）后作为 key 的一部分。

    返回：
      dict[(Peptide, wild_type, HLA_nostar)] -> (%Rank_float, prediction_float)

    若同一 key 出现多次（ICERFIRE 内部扩充行），取最后一次（一般不会发生；打印警告）。
    """
    lookup: dict[tuple[str, str, str], tuple[float, float]] = {}
    duplicates = 0

    with open(predictions_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            peptide = row["Peptide"].strip()
            wt = row["wild_type"].strip()
            hla_raw = row["HLA"].strip()
            hla_nostar = norm_hla(hla_raw)
            try:
                pct_rank = float(row["%Rank"])
            except (KeyError, ValueError) as e:
                raise ValueError(
                    f"无法读取 %Rank 列，行={row!r}: {e}"
                ) from e
            try:
                pred_score = float(row["prediction"])
            except (KeyError, ValueError):
                pred_score = float("nan")

            key = (peptide, wt, hla_nostar)
            if key in lookup:
                duplicates += 1
            lookup[key] = (pct_rank, pred_score)

    if duplicates:
        print(
            f"[parse_icerfire] ⚠️ ICERFIRE_predictions.csv 中有 {duplicates} 个重复 key "
            "(Peptide,wild_type,HLA)，已取最后一次值。",
            file=sys.stderr,
        )
    return lookup


# ---------------------------------------------------------------------------
# 读 index
# ---------------------------------------------------------------------------

def read_index(index_path: pathlib.Path) -> list[dict]:
    """
    读 icerfire_index.csv（prep_icerfire.py 生成）。
    列：output_row, bb_idx, MT_Subpeptide, WT_Subpeptide, HLA_icerfire
    返回所有行（含 SKIPPED），SKIPPED 行 output_row 保持字符串。
    非 SKIPPED 行 output_row 转 int。
    """
    rows = []
    with open(index_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["output_row"] != "SKIPPED":
                row["output_row"] = int(row["output_row"])
            rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# 读 unsupported（HLA 不在白名单的 bb_idx）
# ---------------------------------------------------------------------------

def read_unsupported(unsupported_path: pathlib.Path) -> set[str]:
    """
    读 icerfire_unsupported_bbidx.csv（prep_icerfire.py 生成）。
    返回 bb_idx 集合，用于 parse 阶段填 NaN。
    文件不存在时返回空集合（兼容旧 prep 版本）。
    """
    if not unsupported_path.exists():
        return set()
    bb_ids: set[str] = set()
    with open(unsupported_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            bb_ids.add(row["bb_idx"])
    return bb_ids


# ---------------------------------------------------------------------------
# 主逻辑
# ---------------------------------------------------------------------------

def parse(
    predictions_path: pathlib.Path,
    index_path: pathlib.Path,
    out_csv: pathlib.Path,
    unsupported_path: pathlib.Path,
) -> None:
    """
    按 content join 回贴 bb_idx：
      key = (MT_Subpeptide, WT_Subpeptide, HLA_icerfire)  ←→  (Peptide, wild_type, HLA_nostar)
    """
    # 读 predictions lookup
    lookup = read_predictions_lookup(predictions_path)
    print(f"[parse_icerfire] 读取 ICERFIRE_predictions.csv: {len(lookup)} 个唯一 (Peptide,WT,HLA) key")

    # 读 index（所有行含 SKIPPED）
    index_rows = read_index(index_path)
    print(f"[parse_icerfire] index 总行数（含 SKIPPED）: {len(index_rows)}")

    # 读 unsupported
    unsupported_bb_ids = read_unsupported(unsupported_path)
    print(f"[parse_icerfire] unsupported HLA bb_idx 数: {len(unsupported_bb_ids)}")

    # 收集所有 bb_idx → (rank, score)；先统一为 None
    results: dict[str, tuple[float | None, float | None]] = {}

    miss_count = 0
    hit_count = 0

    for row in index_rows:
        bb_idx = row["bb_idx"]

        # unsupported：填 NaN（覆盖优先，不查 lookup）
        if bb_idx in unsupported_bb_ids:
            results[bb_idx] = (None, None)
            continue

        # SKIPPED（prep 阶段未送入 ICERFIRE）：也填 NaN
        if row["output_row"] == "SKIPPED":
            results[bb_idx] = (None, None)
            continue

        # 构造 join key
        mt = row["MT_Subpeptide"].strip()
        wt = row["WT_Subpeptide"].strip()
        hla = row["HLA_icerfire"].strip()  # 已是无星格式
        key = (mt, wt, hla)

        if key in lookup:
            pct_rank, pred_score = lookup[key]
            # 方向翻转
            icerfire_score = round(100.0 - pct_rank, 4)
            icerfire_rank = round(pct_rank, 4)
            # 一个 key 可能对多 bb_idx：全赋同值（不去重）
            results[bb_idx] = (icerfire_rank, icerfire_score)
            hit_count += 1
        else:
            # ICERFIRE 内部跳过的肽：填 NaN，打印警告
            results[bb_idx] = (None, None)
            miss_count += 1

    if miss_count:
        print(
            f"[parse_icerfire] ⚠️ {miss_count} 条 index 行在 predictions 中查不到 "
            "(ICERFIRE 内部跳过？)，填 NaN。",
            file=sys.stderr,
        )

    # 按 bb_idx 排序输出（bb_idx 为整数字符串，按数值排）
    def _sort_key(k: str) -> int:
        try:
            return int(k)
        except ValueError:
            return 0

    sorted_bb_idxs = sorted(results.keys(), key=_sort_key)

    # 写输出
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        f.write("# ICERFIRE 1.0 benchmark scores — QuantImmuBench §Tier-2\n")
        f.write("# icerfire_rank: 原始 ICERFIRE %Rank（0=最强免疫原，100=最弱）\n")
        f.write("# icerfire_score: 翻转方向 = 100 - icerfire_rank（越高越强，与其他工具一致）\n")
        f.write("# pending_DTU_consent: True = ICERFIRE binary 使用条款待 DTU 书面确认\n")
        f.write("# join_strategy: content join on (MT_Subpeptide, WT_Subpeptide, HLA_icerfire) — 非行序\n")

        writer = csv.writer(f)
        writer.writerow(["bb_idx", "icerfire_rank", "icerfire_score", "pending_DTU_consent"])

        nan_count = 0
        for bb_idx in sorted_bb_idxs:
            rank_val, score_val = results[bb_idx]
            if rank_val is None:
                writer.writerow([bb_idx, "", "", True])
                nan_count += 1
            else:
                writer.writerow([bb_idx, rank_val, score_val, True])

    total = len(sorted_bb_idxs)
    supported_count = total - nan_count
    print(
        f"[parse_icerfire] 输出: {out_csv}\n"
        f"  hit={hit_count}  miss/unsupported/skipped(NaN)={nan_count}  total={total}"
    )
    print("[parse_icerfire] icerfire_score 方向=越高越强（100-%Rank）")
    print("[parse_icerfire] pending_DTU_consent=True 全列")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    script_dir = pathlib.Path(__file__).parent
    repo_root = script_dir.parents[2]  # QuantImmuBench/
    icerfire_inputs_dir = repo_root / "scripts" / "out" / "newtools" / "icerfire_inputs"

    default_predictions = icerfire_inputs_dir / "ICERFIRE_predictions.csv"
    default_index = icerfire_inputs_dir / "icerfire_index.csv"
    default_unsupported = icerfire_inputs_dir / "icerfire_unsupported_bbidx.csv"
    default_out_csv = repo_root / "scripts" / "out" / "newtools" / "icerfire_DS1DS2_scores.csv"

    parser = argparse.ArgumentParser(
        description="解析 ICERFIRE 1.0 输出（ICERFIRE_predictions.csv），按 content join 回贴 bb_idx"
    )
    parser.add_argument(
        "--predictions",
        default=str(default_predictions),
        help=(
            "ICERFIRE 输出文件路径（默认 icerfire_inputs/ICERFIRE_predictions.csv）。\n"
            "列：Peptide,wild_type,HLA,%%Rank,prediction 等。\n"
            "HLA 含星（如 HLA-A*0201），脚本自动去星归一。"
        ),
    )
    parser.add_argument(
        "--index",
        default=str(default_index),
        help="prep_icerfire.py 生成的 icerfire_index.csv",
    )
    parser.add_argument(
        "--unsupported-csv",
        default=str(default_unsupported),
        help=(
            "prep_icerfire.py 生成的 icerfire_unsupported_bbidx.csv"
            "（HLA 不在白名单的 bb_idx，parse 阶段填 NaN；文件不存在时跳过）"
        ),
    )
    parser.add_argument(
        "--out-csv",
        default=str(default_out_csv),
        help="输出 CSV 路径（默认 scripts/out/newtools/icerfire_DS1DS2_scores.csv）",
    )

    args = parser.parse_args()

    predictions_path = pathlib.Path(args.predictions)
    index_path = pathlib.Path(args.index)

    if not predictions_path.exists():
        print(
            f"[parse_icerfire] ICERFIRE_predictions.csv 不存在: {predictions_path}\n"
            "先跑 run_icerfire.sh 产生 ICERFIRE_predictions.csv，再解析。\n"
            "（ICERFIRE binary pending DTU download: health-software@dtu.dk）",
            file=sys.stderr,
        )
        sys.exit(1)

    if not index_path.exists():
        print(
            f"[parse_icerfire] index 文件不存在: {index_path}\n"
            "先跑 prep_icerfire.py 生成 icerfire_index.csv",
            file=sys.stderr,
        )
        sys.exit(1)

    parse(
        predictions_path=predictions_path,
        index_path=index_path,
        out_csv=pathlib.Path(args.out_csv),
        unsupported_path=pathlib.Path(args.unsupported_csv),
    )


if __name__ == "__main__":
    main()
