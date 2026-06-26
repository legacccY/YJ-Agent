"""
merge_tscape.py  —  QuantImmuBench §Tier-3  T-SCAPE 输出解析 + 回贴 bb_idx
服务项目：quantimmu-bench §工具扩张v2 lever=部署T-SCAPE

功能：
  1. 读 T-SCAPE 输出 CSV（含列 Allele, Peptide, score）
  2. 读 prep_tscape_input.py 产生的 tscape_input_map.csv（(Peptide,Allele)→bb_idx列表）
  3. 按 (Peptide, Allele) join，将 score 回贴到每个 bb_idx 行
  4. 输出 tscape_scores.csv（列 bb_idx, MT_TSCAPE）

MT-only 说明：
  T-SCAPE 是 MT-only 工具（只需肽+HLA），输出只产 MT_TSCAPE 列（无 WT_TSCAPE）。
  方向：score 0-1，越高越强（>0.5 = 免疫原），无需翻转。

已知坑：
  - mhc_pseudo_matching.py 会过滤掉不在 MHC_classI_pseudo.csv 中的 allele
    → 这些 (Peptide, Allele) 对不会出现在 T-SCAPE 输出中
    → 对应 bb_idx 在输出中填 NaN（不报错，仅 stderr 计数）

用法：
  python merge_tscape.py [--tscape-out <csv>] [--map <csv>] [--out-csv <csv>]
  默认路径见 main() 注释
"""

import argparse
import csv
import pathlib
import sys


# ---------------------------------------------------------------------------
# Allele 归一（与 mhc_pseudo_matching.py modify_entry_2 一致）
# T-SCAPE 输出的 Allele 已被 mhc_pseudo_matching 转成缩写型（HLA-A*24:02 → A2402），
# 但 map 里是标准型。join 前两边都归一到缩写型（去 HLA-、去 *、去 :）。
# ---------------------------------------------------------------------------

def _norm_allele(a: str) -> str:
    a = str(a).strip()
    if a.upper().startswith("HLA-"):
        a = a[4:]
    elif a.upper().startswith("HLA"):
        a = a[3:]
    return a.replace("*", "").replace(":", "")


# ---------------------------------------------------------------------------
# 读 T-SCAPE 输出
# ---------------------------------------------------------------------------

def read_tscape_output(output_path: pathlib.Path) -> dict[tuple[str, str], float]:
    """
    读 T-SCAPE 推理输出 CSV。
    返回 {(Peptide, Allele): score} 字典。

    T-SCAPE 输出保留输入列（Allele, Peptide）并追加 score 列（0-1 浮点）。
    """
    pair_to_score: dict[tuple[str, str], float] = {}

    with open(output_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []

        # 验证必要列（T-SCAPE pmhc_im 输出列 = Allele, peptide[小写], score）
        required_cols = {"Allele", "peptide", "score"}
        missing = required_cols - set(fieldnames)
        if missing:
            raise ValueError(
                f"T-SCAPE 输出缺少列: {missing}。实际列: {fieldnames}\n"
                "预期列: Allele, peptide(小写), score（T-SCAPE inference_csv.py 产生）"
            )

        for row in reader:
            peptide = row["peptide"].strip()
            allele  = _norm_allele(row["Allele"])
            try:
                score = float(row["score"])
            except ValueError as e:
                print(
                    f"[merge_tscape] WARN: score 值无法转 float: {row['score']!r} "
                    f"(Peptide={peptide}, Allele={allele})，跳过: {e}",
                    file=sys.stderr,
                )
                continue

            pair = (peptide, allele)
            if pair in pair_to_score:
                # 同一 (Peptide, Allele) 出现多次：T-SCAPE 不应有重复，警告并取最后一个
                print(
                    f"[merge_tscape] WARN: 重复 (Peptide, Allele) = ({peptide}, {allele})，"
                    f"已有 score={pair_to_score[pair]:.4f}，覆盖为 {score:.4f}",
                    file=sys.stderr,
                )
            pair_to_score[pair] = score

    return pair_to_score


# ---------------------------------------------------------------------------
# 读 map CSV
# ---------------------------------------------------------------------------

def read_map(map_path: pathlib.Path) -> list[dict]:
    """
    读 prep_tscape_input.py 产生的 tscape_input_map.csv。
    列：Peptide, Allele, bb_idx_list（bb_idx 逗号分隔）
    返回 list of dicts，保持顺序。
    """
    rows = []
    with open(map_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# 主逻辑
# ---------------------------------------------------------------------------

def merge(
    tscape_out_path: pathlib.Path,
    map_path: pathlib.Path,
    out_csv_path: pathlib.Path,
) -> None:
    # 读 T-SCAPE 输出
    pair_to_score = read_tscape_output(tscape_out_path)
    print(f"[merge_tscape] T-SCAPE 输出: {len(pair_to_score)} 个 (Peptide, Allele) 对")

    # 读 map
    map_rows = read_map(map_path)
    print(f"[merge_tscape] map CSV: {len(map_rows)} 行（unique (MT, HLA) 对）")

    # 遍历 map，每行展开 bb_idx_list → 多行输出
    out_rows: list[dict] = []
    n_matched  = 0
    n_nan      = 0   # allele 被 mhc_pseudo_matching 过滤掉，无 T-SCAPE score

    for map_row in map_rows:
        peptide     = map_row["Peptide"].strip()
        allele      = _norm_allele(map_row["Allele"])
        bb_idx_list = [x.strip() for x in map_row["bb_idx_list"].split(",") if x.strip()]

        pair  = (peptide, allele)
        score = pair_to_score.get(pair, None)

        if score is None:
            # allele 被过滤（不在 MHC_classI_pseudo.csv），填 NaN
            n_nan += len(bb_idx_list)
            print(
                f"[merge_tscape] NaN: (Peptide={peptide}, Allele={allele}) "
                f"不在 T-SCAPE 输出（可能被 mhc_pseudo_matching 过滤）"
                f"→ {len(bb_idx_list)} 个 bb_idx 填 NaN",
                file=sys.stderr,
            )
        else:
            n_matched += len(bb_idx_list)

        for bb_idx in bb_idx_list:
            out_rows.append({
                "bb_idx":    bb_idx,
                "MT_TSCAPE": "" if score is None else f"{score:.6f}",
            })

    # 写输出
    out_csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["bb_idx", "MT_TSCAPE"])
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"[merge_tscape] 输出: {out_csv_path}（{len(out_rows)} 行）")
    print(f"[merge_tscape] 有 score 的 bb_idx 行: {n_matched}")
    print(f"[merge_tscape] NaN（allele 被过滤）行 : {n_nan}")
    print(f"[merge_tscape] MT_TSCAPE 方向：越高越强（0-1，>0.5=免疫原，无需翻转）")

    if n_nan > 0:
        print(
            f"[merge_tscape] ⚠️ {n_nan} 行 MT_TSCAPE=NaN —— 对应 allele 不在 T-SCAPE 支持列表\n"
            "  benchmark 合并时这些行按 NaN 处理（不参与该工具的 Spearman 计算）",
            file=sys.stderr,
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    script_dir  = pathlib.Path(__file__).parent
    repo_root   = script_dir.parents[3]   # YJ-Agent/project/meeting/QuantImmuBench/
    newtools    = repo_root / "scripts" / "out" / "newtools"

    default_tscape_out = newtools / "tscape_output.csv"          # HPC 下载后放这里
    default_map        = newtools / "tscape_input_map.csv"        # prep_tscape_input.py 产生
    default_out_csv    = newtools / "tscape_scores.csv"           # 最终输出

    parser = argparse.ArgumentParser(
        description="Merge T-SCAPE output → bb_idx level tscape_scores.csv"
    )
    parser.add_argument(
        "--tscape-out",
        default=str(default_tscape_out),
        help="T-SCAPE 推理输出 CSV（列 Allele,Peptide,score；默认 scripts/out/newtools/tscape_output.csv）",
    )
    parser.add_argument(
        "--map",
        default=str(default_map),
        help="prep_tscape_input.py 产生的 tscape_input_map.csv",
    )
    parser.add_argument(
        "--out-csv",
        default=str(default_out_csv),
        help="输出路径（默认 scripts/out/newtools/tscape_scores.csv）",
    )
    args = parser.parse_args()

    tscape_out_path = pathlib.Path(args.tscape_out)
    map_path        = pathlib.Path(args.map)
    out_csv_path    = pathlib.Path(args.out_csv)

    if not tscape_out_path.exists():
        print(
            f"[merge_tscape] ERROR: T-SCAPE 输出不存在: {tscape_out_path}\n"
            "  请先在 HPC 跑 submit_tscape.sbatch，下载结果后再 merge。",
            file=sys.stderr,
        )
        sys.exit(1)

    if not map_path.exists():
        print(
            f"[merge_tscape] ERROR: map 文件不存在: {map_path}\n"
            "  请先跑 prep_tscape_input.py 产生 tscape_input_map.csv。",
            file=sys.stderr,
        )
        sys.exit(1)

    merge(tscape_out_path, map_path, out_csv_path)


if __name__ == "__main__":
    main()
