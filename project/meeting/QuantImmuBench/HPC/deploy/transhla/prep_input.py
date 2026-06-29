"""
prep_input.py — QuantImmuBench §工具部署  TransHLA 输入准备
服务项目：quantimmu-bench §工具部署 P9 lever=补满 30 工具 apples-to-apples

功能：
  1. 读 uniq_pep_hla.csv（列: peptide, HLA_Allele, source；53583 行）
  2. 因 TransHLA HLA-agnostic（只吃肽不吃 HLA），取 unique peptide（去重 HLA 维）
  3. 过滤 8-14mer（TransHLA_I 官方支持范围）
  4. <8mer / >14mer 计数 + 记录（parse_output.py 阶段填 NaN）
  5. 输出 transhla_input.csv（单列 peptide）—— run_transhla.py 的输入

输入：
  scripts/out/newtools/uniq_pep_hla.csv  (peptide, HLA_Allele, source)

输出（均在本脚本所在目录 HPC/deploy/transhla/）：
  transhla_input.csv      ← run_transhla.py 输入（8-14mer 唯一肽，单列 peptide）
  transhla_skipped.csv    ← 超出长度范围的肽（<8 / >14mer → NaN，parse 阶段用）

TransHLA_I 肽长说明：
  - 官方 README："TransHLA_I is designed for shorter peptides ranging from
    8 to 14 amino acids in length"（HLA-I epitope detector）。
  - 来源：github.com/SkywalkerLuke/TransHLA README §Intended uses（2026-06-29 核）
  - TransHLA_II 覆盖 13-21mer（HLA-II），本 benchmark 不使用。

HLA-agnostic 说明：
  - TransHLA 是首个无需输入 HLA allele 的 epitope detector，仅依赖肽序列。
  - 取 unique peptide（同肽不同 allele 折叠为一条），parse 阶段广播回各 allele 行。
  - 与 Repitope 处理一致（见 HPC/deploy/repitope/prep_input.py）。

用法：
  python prep_input.py [--uniq-csv PATH] [--out-dir DIR] [--smoke N]
  --smoke N：仅保留前 N 个有效（8-14mer）唯一肽（烟测用，建议 N=5）
"""

import argparse
import csv
import pathlib
import sys

# ---------------------------------------------------------------------------
# 路径默认值（相对脚本位置，适配 HPC/deploy/transhla/ 位置）
# ---------------------------------------------------------------------------
SCRIPT_DIR  = pathlib.Path(__file__).parent.resolve()
PROJECT_DIR = SCRIPT_DIR.parents[2]   # QuantImmuBench/

DEFAULT_UNIQ_CSV = PROJECT_DIR / "scripts" / "out" / "newtools" / "uniq_pep_hla.csv"
DEFAULT_OUT_DIR  = SCRIPT_DIR   # 输出到本脚本同目录

# TransHLA_I 支持肽长范围（8-14mer）
MIN_PEP_LEN = 8
MAX_PEP_LEN = 14


# ---------------------------------------------------------------------------
# 主逻辑
# ---------------------------------------------------------------------------

def prep(uniq_csv: pathlib.Path, out_dir: pathlib.Path, smoke: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    input_csv_path   = out_dir / "transhla_input.csv"
    skipped_csv_path = out_dir / "transhla_skipped.csv"

    n_total   = 0           # 读入总行数（含 HLA 重复）
    n_uniq    = 0           # 去重 HLA 维后唯一肽数
    n_written = 0           # 写入有效肽数
    n_short   = 0           # < 8mer → parse 阶段填 NaN
    n_long    = 0           # > 14mer → parse 阶段填 NaN

    seen: set[str] = set()  # 已见过的肽（去重 HLA 维）

    with (
        open(uniq_csv, newline="", encoding="utf-8") as f_in,
        open(input_csv_path, "w", newline="", encoding="utf-8") as f_out,
        open(skipped_csv_path, "w", newline="", encoding="utf-8") as f_skip,
    ):
        reader      = csv.DictReader(f_in)
        writer_in   = csv.writer(f_out)
        writer_skip = csv.writer(f_skip)

        # 表头
        # TransHLA_I.py 读取时 test.iloc[:, 0] 取第一列为肽（与列名无关），
        # 这里写列名 "peptide"。
        writer_in.writerow(["peptide"])
        writer_skip.writerow(["peptide", "source", "reason"])

        for row in reader:
            n_total += 1
            pep = row["peptide"].strip()
            src = row.get("source", "").strip()

            # 去重 HLA 维：同一肽只处理一次
            if pep in seen:
                continue
            seen.add(pep)
            n_uniq += 1

            plen = len(pep)

            if plen < MIN_PEP_LEN:
                n_short += 1
                writer_skip.writerow([pep, src, f"len={plen}_lt_{MIN_PEP_LEN}_NaN_in_parse"])
                continue

            if plen > MAX_PEP_LEN:
                n_long += 1
                writer_skip.writerow([pep, src, f"len={plen}_gt_{MAX_PEP_LEN}_NaN_in_parse"])
                continue

            # smoke 截断（只截有效肽）
            if smoke > 0 and n_written >= smoke:
                continue

            writer_in.writerow([pep])
            n_written += 1

    print(f"[prep_input] 读入总行数（含 HLA 重复）: {n_total}")
    print(f"[prep_input] 去重 HLA 维后唯一肽:       {n_uniq}")
    print(f"[prep_input] <{MIN_PEP_LEN}mer（→NaN）:         {n_short}")
    print(f"[prep_input] >{MAX_PEP_LEN}mer（→NaN）:        {n_long}")
    print(f"[prep_input] 写入 transhla_input:         {n_written}")
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
            "准备 TransHLA 输入 CSV（去重 HLA 维取唯一肽 + 过滤 8-14mer TransHLA_I 范围，"
            "<8 / >14mer 在 parse_output.py 阶段填 NaN）"
        )
    )
    parser.add_argument(
        "--uniq-csv",
        default=str(DEFAULT_UNIQ_CSV),
        help="uniq_pep_hla.csv 路径（默认 scripts/out/newtools/uniq_pep_hla.csv）",
    )
    parser.add_argument(
        "--out-dir",
        default=str(DEFAULT_OUT_DIR),
        help="输出目录（默认本脚本所在目录 HPC/deploy/transhla/）",
    )
    parser.add_argument(
        "--smoke",
        type=int,
        default=0,
        metavar="N",
        help="烟测模式：只写前 N 个有效（8-14mer）唯一肽（建议 N=5，0=关闭）",
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
