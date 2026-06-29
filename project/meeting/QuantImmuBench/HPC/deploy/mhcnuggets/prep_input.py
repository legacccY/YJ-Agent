"""
prep_input.py — QuantImmuBench §工具部署 P10  MHCnuggets 输入准备
服务项目：quantimmu-bench §工具部署 lever=补满30工具呈递槽 P10

功能：
  1. 从 uniq_pep_hla.csv (53583 unique peptide×HLA 对) 读输入
  2. 肽长过滤（MHC-I：8–15mer；universe 实际 8–14，全部通过）
  3. 只保留 MHC-I（HLA-A / HLA-B / HLA-C）；其余（HLA-DRB/DQ/DP 等 Class II）记入 unsupported
  4. HLA 格式转换：universe 标准格式 HLA-A*02:01  →  MHCnuggets 格式 HLA-A02:01（去星号）
     依据：mhcnuggets/src/find_closest_mhcI.py 用 mhc[4]=基因字母, int(mhc[5:7])=超型,
           int(mhc[8:10])=亚型，星号会让 int() 崩，故 MHCnuggets 一律无星号格式。
  5. 写 mhcnuggets_input.csv（peptide, HLA_Allele, mhcnuggets_allele）
     —— HLA_Allele 保留原始带星号格式（供 parse 阶段回贴 universe），
        mhcnuggets_allele 是去星号格式（供 run 阶段喂 MHCnuggets）。该列即「map」。
  6. 写 mhcnuggets_unsupported.csv（被跳过的行 + 原因），供 parse 阶段 NaN 回填参考

输入：
  scripts/out/newtools/uniq_pep_hla.csv  (peptide, HLA_Allele, source)

输出（均在本脚本所在目录 HPC/deploy/mhcnuggets/）：
  mhcnuggets_input.csv        ← run_mhcnuggets.py 的输入
  mhcnuggets_unsupported.csv  ← 记录跳过的行（肽长 / 非 Class I）

运行前提：
  pip install mhcnuggets      （权重内置 pip 包，无需额外下载）

用法：
  python prep_input.py [--uniq-csv PATH] [--out-dir DIR] [--smoke N]
  --smoke N: 只取前 N 行做快速格式验证（默认 0=全量）。

官方源（2026-06-29 核自 github.com/KarchinLab/mhcnuggets master）：
  - HLA 格式：HLA-A02:01（无星号）—— find_closest_mhcI.py::closest_human_allele_name
  - MHC-I：HLA-A / HLA-B / HLA-C —— find_closest_mhcI.py 默认 pan model 仅 A/B/C
"""

import argparse
import csv
import pathlib
import sys

# ---------------------------------------------------------------------------
# 路径默认值（相对脚本位置，适配 HPC/deploy/mhcnuggets/ 位置）
# ---------------------------------------------------------------------------
SCRIPT_DIR = pathlib.Path(__file__).parent.resolve()
PROJECT_DIR = SCRIPT_DIR.parents[2]   # QuantImmuBench/

DEFAULT_UNIQ_CSV = PROJECT_DIR / "scripts" / "out" / "newtools" / "uniq_pep_hla.csv"
DEFAULT_OUT_DIR = SCRIPT_DIR    # 输出到本脚本同目录

# 肽长范围（MHC-I：8–15mer；universe 实际 8–14，全部通过）
MIN_PEP_LEN = 8
MAX_PEP_LEN = 15

# MHC-I 基因前缀
MHCI_PREFIXES = ("HLA-A", "HLA-B", "HLA-C")


# ---------------------------------------------------------------------------
# HLA 格式转换
# ---------------------------------------------------------------------------

def to_mhcnuggets_allele(hla: str) -> str:
    """
    universe 标准格式  HLA-A*02:01  →  MHCnuggets 格式  HLA-A02:01（去星号）。
    依据 find_closest_mhcI.py 的索引解析（mhc[4]=基因, mhc[5:7]/mhc[8:10]=数字）。
    """
    return hla.replace("*", "")


def is_mhci(hla: str) -> bool:
    return hla.startswith(MHCI_PREFIXES)


# ---------------------------------------------------------------------------
# 主逻辑
# ---------------------------------------------------------------------------

def prep(uniq_csv: pathlib.Path, out_dir: pathlib.Path, smoke: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    input_csv_path = out_dir / "mhcnuggets_input.csv"
    unsupported_csv_path = out_dir / "mhcnuggets_unsupported.csv"

    n_total = 0
    n_written = 0
    n_len_skip = 0
    n_classII_skip = 0

    with (
        open(uniq_csv, newline="", encoding="utf-8") as f_in,
        open(input_csv_path, "w", newline="", encoding="utf-8") as f_out,
        open(unsupported_csv_path, "w", newline="", encoding="utf-8") as f_unsup,
    ):
        reader = csv.DictReader(f_in)
        writer_in = csv.writer(f_out)
        writer_uns = csv.writer(f_unsup)

        # 表头
        writer_in.writerow(["peptide", "HLA_Allele", "mhcnuggets_allele"])
        writer_uns.writerow(["peptide", "HLA_Allele", "source", "reason"])

        for row in reader:
            n_total += 1
            pep = row["peptide"].strip()
            hla = row["HLA_Allele"].strip()
            src = row.get("source", "").strip()

            # 肽长过滤
            if not (MIN_PEP_LEN <= len(pep) <= MAX_PEP_LEN):
                n_len_skip += 1
                writer_uns.writerow([pep, hla, src, f"len={len(pep)}_out_of_{MIN_PEP_LEN}-{MAX_PEP_LEN}"])
                continue

            # MHC-I 过滤（MHCnuggets MHC-I 模式仅 HLA-A/B/C）
            if not is_mhci(hla):
                n_classII_skip += 1
                writer_uns.writerow([pep, hla, src, "not_mhc_class_I"])
                continue

            mhcn_allele = to_mhcnuggets_allele(hla)
            writer_in.writerow([pep, hla, mhcn_allele])
            n_written += 1

            if smoke and n_written >= smoke:
                print(f"[prep_input] --smoke {smoke}: 已写 {n_written} 行，提前结束。")
                break

    print(f"[prep_input] 读入总行数:            {n_total}")
    print(f"[prep_input] 肽长过滤跳过:          {n_len_skip}")
    print(f"[prep_input] 非 MHC-I 跳过:         {n_classII_skip}")
    print(f"[prep_input] 写入 mhcnuggets_input: {n_written}")
    print(f"[prep_input] 输出: {input_csv_path}")
    print(f"[prep_input] 不支持记录: {unsupported_csv_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="准备 MHCnuggets 输入 CSV（肽长检查 + MHC-I 过滤 + HLA 去星号格式转换）"
    )
    parser.add_argument(
        "--uniq-csv",
        default=str(DEFAULT_UNIQ_CSV),
        help="uniq_pep_hla.csv 路径（默认 scripts/out/newtools/uniq_pep_hla.csv）",
    )
    parser.add_argument(
        "--out-dir",
        default=str(DEFAULT_OUT_DIR),
        help="输出目录（默认本脚本所在目录 HPC/deploy/mhcnuggets/）",
    )
    parser.add_argument(
        "--smoke",
        type=int,
        metavar="N",
        default=0,
        help="烟测模式：只写前 N 行（N=0=全量）",
    )
    args = parser.parse_args()

    uniq_csv = pathlib.Path(args.uniq_csv)
    out_dir = pathlib.Path(args.out_dir)

    if not uniq_csv.exists():
        print(f"[prep_input] ERROR: 输入文件不存在: {uniq_csv}", file=sys.stderr)
        sys.exit(1)

    prep(uniq_csv, out_dir, args.smoke)


if __name__ == "__main__":
    main()
