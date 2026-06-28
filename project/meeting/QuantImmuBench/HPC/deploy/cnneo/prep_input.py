"""
prep_input.py — QuantImmuBench §扩张v2  CNNeo/CNNeoPP 输入准备
服务项目：quantimmu-bench §工具扩张v2 lever=部署CNNeo apples-to-apples

功能：
  1. 读 uniq_pep_hla.csv（53582 行，列：peptide, HLA_Allele, source）
  2. 重命名列为 CNNeo 所需格式（peptide, hla）
  3. HLA 格式：保持标准 HLA-A*02:01（run_cnneo.py 内部自动去除 * ）
  4. 肽长：全覆盖 8-14mer（训练数据主要 8-11mer，脚本用 trans_Mutated 补 X 至 11；
     >11mer 直接用原序列，轻度 OOD 但模型仍可处理）
  5. 输出 cnneo_input.csv（列：peptide, hla）——去重 unique (peptide, hla) 对
  6. 输出 cnneo_input_map.csv（列：peptide, hla, row_idx_list）——回贴用

输入（默认自动定位，相对本脚本向上找）：
  scripts/out/newtools/uniq_pep_hla.csv

输出（默认 scripts/out/newtools/）：
  cnneo_input.csv     — 喂 run_cnneo.py 的输入
  cnneo_input_map.csv — (peptide, hla) → row_idx 列表（0-based，逗号分隔）

注意：
  - source 列（MT/WT/BOTH）不过滤——MT 和 WT 肽都喂，parse_output.py 分别回贴
  - 肽长过滤：可选 --min-len / --max-len；默认 8-14，与 uniq_pep_hla.csv 实际分布一致

用法：
  python prep_input.py [--in-csv <path>] [--out-dir <dir>] [--smoke N]
  python prep_input.py --smoke 20
"""

import argparse
import csv
import pathlib
import sys
from collections import defaultdict


# ---------------------------------------------------------------------------
# 默认肽长范围（CNNeo trans_Mutated 填充到 11，>11 原样）
# ---------------------------------------------------------------------------
DEFAULT_MIN_LEN = 8
DEFAULT_MAX_LEN = 14   # 实际数据上限；>11 轻度 OOD，全量保留


# ---------------------------------------------------------------------------
# 主逻辑
# ---------------------------------------------------------------------------

def prep(
    in_csv: pathlib.Path,
    out_dir: pathlib.Path,
    smoke: int = 0,
    min_len: int = DEFAULT_MIN_LEN,
    max_len: int = DEFAULT_MAX_LEN,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    cnneo_input_path = out_dir / "cnneo_input.csv"
    cnneo_map_path   = out_dir / "cnneo_input_map.csv"

    # (peptide, hla) → [row_idx, ...] — 去重同时保留全部原始行索引（0-based，不含表头）
    pair_to_rowidx: dict[tuple[str, str], list[int]] = defaultdict(list)

    skipped_short  = 0
    skipped_long   = 0
    skipped_empty  = 0
    total_rows     = 0

    with open(in_csv, newline="", encoding="utf-8") as f_in:
        reader = csv.DictReader(f_in)
        for row_idx, row in enumerate(reader):
            total_rows += 1
            pep     = row["peptide"].strip()
            hla_raw = row["HLA_Allele"].strip()

            # 肽为空：跳过
            if not pep:
                skipped_empty += 1
                print(
                    f"[prep_input] SKIP row {row_idx}: peptide 为空",
                    file=sys.stderr,
                )
                continue

            pep_len = len(pep)
            if pep_len < min_len:
                skipped_short += 1
                print(
                    f"[prep_input] SKIP row {row_idx}: peptide={pep!r} "
                    f"长度={pep_len} < {min_len}mer",
                    file=sys.stderr,
                )
                continue
            if pep_len > max_len:
                skipped_long += 1
                print(
                    f"[prep_input] SKIP row {row_idx}: peptide={pep!r} "
                    f"长度={pep_len} > {max_len}mer",
                    file=sys.stderr,
                )
                continue

            # HLA 格式：标准 HLA-A*02:01 直接保留（run_cnneo.py 内部处理 * ）
            pair = (pep, hla_raw)
            pair_to_rowidx[pair].append(row_idx)

    unique_pairs = list(pair_to_rowidx.keys())

    # --smoke：截取前 N 个 unique (peptide, hla) 对
    if smoke > 0:
        print(
            f"[prep_input] --smoke {smoke}：截取前 {smoke} 个 unique (peptide, hla) 对",
            file=sys.stderr,
        )
        unique_pairs = unique_pairs[:smoke]

    # 写 CNNeo 输入 CSV（列：peptide, hla）
    with open(cnneo_input_path, "w", newline="", encoding="utf-8") as f_out:
        writer = csv.writer(f_out)
        writer.writerow(["peptide", "hla"])
        for (pep, hla) in unique_pairs:
            writer.writerow([pep, hla])

    # 写 map CSV（(peptide, hla) → row_idx 列表，逗号分隔）
    with open(cnneo_map_path, "w", newline="", encoding="utf-8") as f_map:
        writer_map = csv.writer(f_map)
        writer_map.writerow(["peptide", "hla", "row_idx_list"])
        for (pep, hla) in unique_pairs:
            idx_list = ",".join(str(i) for i in pair_to_rowidx[(pep, hla)])
            writer_map.writerow([pep, hla, idx_list])

    n_unique  = len(unique_pairs)
    n_covered = sum(len(v) for v in pair_to_rowidx.values())

    print(f"[prep_input] uniq_pep_hla 总行数         : {total_rows}")
    print(f"[prep_input] 跳过（peptide 为空）          : {skipped_empty}")
    print(f"[prep_input] 跳过（< {min_len}mer）          : {skipped_short}")
    print(f"[prep_input] 跳过（> {max_len}mer）          : {skipped_long}")
    print(f"[prep_input] unique (peptide, hla) 对     : {n_unique}")
    print(f"[prep_input] 覆盖原始行数                 : {n_covered}")
    if smoke > 0:
        print(f"[prep_input] [SMOKE] 仅写前 {n_unique} 对，全量需去掉 --smoke")
    print(f"[prep_input] 输出 cnneo_input.csv         : {cnneo_input_path}")
    print(f"[prep_input] 输出 cnneo_input_map.csv     : {cnneo_map_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    # 默认路径：本脚本在 HPC/deploy/cnneo/，uniq_pep_hla 在 scripts/out/newtools/
    script_dir   = pathlib.Path(__file__).parent
    repo_root    = script_dir.parents[2]   # QuantImmuBench/
    default_in   = repo_root / "scripts" / "out" / "newtools" / "uniq_pep_hla.csv"
    default_out  = repo_root / "scripts" / "out" / "newtools"

    parser = argparse.ArgumentParser(
        description=(
            "Prepare CNNeo input CSV from uniq_pep_hla.csv "
            "(peptide+hla, all lengths 8-14mer)"
        )
    )
    parser.add_argument(
        "--in-csv",
        default=str(default_in),
        help="uniq_pep_hla.csv 路径（默认自动定位）",
    )
    parser.add_argument(
        "--out-dir",
        default=str(default_out),
        help="输出目录（默认 scripts/out/newtools/）",
    )
    parser.add_argument(
        "--smoke",
        type=int,
        default=0,
        metavar="N",
        help="烟测：只写前 N 个 unique (peptide, hla) 对（0=全量）",
    )
    parser.add_argument(
        "--min-len",
        type=int,
        default=DEFAULT_MIN_LEN,
        help=f"最小肽长（默认 {DEFAULT_MIN_LEN}）",
    )
    parser.add_argument(
        "--max-len",
        type=int,
        default=DEFAULT_MAX_LEN,
        help=f"最大肽长（默认 {DEFAULT_MAX_LEN}）",
    )
    args = parser.parse_args()

    in_csv  = pathlib.Path(args.in_csv)
    out_dir = pathlib.Path(args.out_dir)

    if not in_csv.exists():
        print(
            f"[prep_input] ERROR: 输入文件不存在: {in_csv}",
            file=sys.stderr,
        )
        sys.exit(1)

    prep(in_csv, out_dir, smoke=args.smoke, min_len=args.min_len, max_len=args.max_len)


if __name__ == "__main__":
    main()
