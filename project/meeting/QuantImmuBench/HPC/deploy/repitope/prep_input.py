"""
prep_input.py — QuantImmuBench §Tier-0  Repitope 输入准备
服务项目：quantimmu-bench §工具扩张v2 lever=部署Repitope apples-to-apples

功能：
  1. 读 uniq_pep.csv（列: peptide, source; 11903 唯一肽，HLA-agnostic 工具专用）
  2. 过滤 8-11mer（Repitope MHC-I 模型支持范围）
  3. 12-14mer 计数 + 记录（parse_output.py 阶段填 NaN）
  4. 输出 repitope_input.csv（单列 Peptide）—— run_repitope.R 的输入

输入：
  scripts/out/newtools/uniq_pep.csv  (peptide, source)

输出（均在本脚本所在目录 HPC/deploy/repitope/）：
  repitope_input.csv      ← run_repitope.R 输入（8-11mer 肽序列）
  repitope_skipped.csv    ← 超出长度范围的肽（12-14mer→NaN，parse 阶段用）

Repitope 肽长说明：
  - 官方 MHC-I 模型：peptideLengthSet=8:11（8/9/10/11mer）
  - 官方 MHC-II 模型：peptideLengthSet=11:30（不用于本 benchmark）
  - 来源：github.com/masato-ogishi/Repitope/blob/master/R/EpitopePrioritization.R
            示例 peptideLengthSet=8:11 + MHCI_Human_MinimumFeatureSet（MHC-I 32特征）

用法：
  python prep_input.py [--uniq-csv PATH] [--out-dir DIR] [--smoke N]
  --smoke N：仅保留前 N 个有效（8-11mer）肽（烟测用，建议 N=5）
"""

import argparse
import csv
import pathlib
import sys

# ---------------------------------------------------------------------------
# 路径默认值（相对脚本位置，适配 HPC/deploy/repitope/ 位置）
# ---------------------------------------------------------------------------
SCRIPT_DIR  = pathlib.Path(__file__).parent.resolve()
PROJECT_DIR = SCRIPT_DIR.parents[2]   # QuantImmuBench/

DEFAULT_UNIQ_CSV = PROJECT_DIR / "scripts" / "out" / "newtools" / "uniq_pep.csv"
DEFAULT_OUT_DIR  = SCRIPT_DIR   # 输出到本脚本同目录

# Repitope MHC-I 支持肽长范围（8-11mer）
MIN_PEP_LEN = 8
MAX_PEP_LEN = 11


# ---------------------------------------------------------------------------
# 主逻辑
# ---------------------------------------------------------------------------

def prep(uniq_csv: pathlib.Path, out_dir: pathlib.Path, smoke: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    input_csv_path   = out_dir / "repitope_input.csv"
    skipped_csv_path = out_dir / "repitope_skipped.csv"

    n_total   = 0
    n_written = 0
    n_short   = 0   # < 8mer（理论上 uniq_pep 不会有，但防御性处理）
    n_long    = 0   # > 11mer（12-14mer → parse 阶段填 NaN）

    with (
        open(uniq_csv, newline="", encoding="utf-8") as f_in,
        open(input_csv_path, "w", newline="", encoding="utf-8") as f_out,
        open(skipped_csv_path, "w", newline="", encoding="utf-8") as f_skip,
    ):
        reader      = csv.DictReader(f_in)
        writer_in   = csv.writer(f_out)
        writer_skip = csv.writer(f_skip)

        # 表头
        # Repitope Features() 读取时使用列名 "Peptide"（大写 P）
        writer_in.writerow(["Peptide"])
        writer_skip.writerow(["peptide", "source", "reason"])

        for row in reader:
            n_total += 1
            pep = row["peptide"].strip()
            src = row.get("source", "").strip()
            plen = len(pep)

            if plen < MIN_PEP_LEN:
                n_short += 1
                writer_skip.writerow([pep, src, f"len={plen}_lt_{MIN_PEP_LEN}"])
                continue

            if plen > MAX_PEP_LEN:
                n_long += 1
                writer_skip.writerow([pep, src, f"len={plen}_gt_{MAX_PEP_LEN}_NaN_in_parse"])
                continue

            # smoke 截断（只截有效肽）
            if smoke > 0 and n_written >= smoke:
                # 继续计数超长肽，但不再写入有效肽
                continue

            writer_in.writerow([pep])
            n_written += 1

    print(f"[prep_input] 读入总行数:          {n_total}")
    print(f"[prep_input] <{MIN_PEP_LEN}mer（理论为0）:  {n_short}")
    print(f"[prep_input] >{MAX_PEP_LEN}mer（→NaN）:     {n_long}")
    print(f"[prep_input] 写入 repitope_input: {n_written}")
    if smoke > 0:
        print(f"[prep_input] [SMOKE] 仅写前 {n_written} 个有效肽，全量去掉 --smoke")
    print(f"[prep_input] 输出: {input_csv_path}")
    print(f"[prep_input] 跳过记录: {skipped_csv_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "准备 Repitope 输入 CSV（过滤 8-11mer MHC-I 范围，"
            "12-14mer 在 parse_output.py 阶段填 NaN）"
        )
    )
    parser.add_argument(
        "--uniq-csv",
        default=str(DEFAULT_UNIQ_CSV),
        help="uniq_pep.csv 路径（默认 scripts/out/newtools/uniq_pep.csv）",
    )
    parser.add_argument(
        "--out-dir",
        default=str(DEFAULT_OUT_DIR),
        help="输出目录（默认本脚本所在目录 HPC/deploy/repitope/）",
    )
    parser.add_argument(
        "--smoke",
        type=int,
        default=0,
        metavar="N",
        help="烟测模式：只写前 N 个有效（8-11mer）肽（建议 N=5，0=关闭）",
    )
    args = parser.parse_args()

    uniq_csv = pathlib.Path(args.uniq_csv)
    out_dir  = pathlib.Path(args.out_dir)

    if not uniq_csv.exists():
        print(f"[prep_input] ERROR: 输入文件不存在: {uniq_csv}", file=sys.stderr)
        sys.exit(1)

    prep(uniq_csv, out_dir, smoke=args.smoke)


if __name__ == "__main__":
    main()
