"""
prep_input.py — QuantImmuBench §工具部署  MUNIS 输入准备
服务项目：quantimmu-bench §工具部署 免疫原侧 lever=补满到 20（强补位 MUNIS）

功能：
  1. 读 uniq_pep_hla.csv（列: peptide, HLA_Allele, source；53582 行）
  2. 肽长过滤（MUNIS MHC-I：8–15mer；universe 实际 8–14，全部通过）
  3. 只保留 MHC-I（HLA-A / HLA-B / HLA-C）；其余（HLA-DRB/DQ/DP 等 Class II）记 unsupported
  4. HLA 格式归一：universe 标准格式 HLA-A*02:01 → MUNIS 内部 SEQUENCES 键 HLA-A02:01
     （去星号 + 截到 2 字段，镜像官方 predict.py::clean_mhc_name；详见 NOTES.md §HLA 编码）
  5. 写 munis_input.csv（pep, mhc, left, right, HLA_Allele, source）
     —— pep/mhc/left/right 是官方 predict.py --peptides 要求的列；
        HLA_Allele 保留原始带星号格式（穿透到 raw，供 parse 回贴 universe）。
     —— left/right 留空：本部署不带 flanking（universe 仅有 subpeptide），
        run 阶段不传 --use_flanks，官方 predict.py 会把 left/right 覆盖为 "GGGGG"
        并用 no-flanks 模型 ensemble（见 NOTES.md §flanking）。
  6. 写 munis_unsupported.csv（被跳过行 + 原因），供 parse 阶段 NaN 回填参考

注意：本脚本不校验 allele 是否在 MUNIS SEQUENCES 字典内（需 import munis，prep 保持纯
  stdlib，与 transhla/mhcnuggets prep 一致）。allele 不在 SEQUENCES 的行由 run_munis.py
  （已装 munis 环境）剔到 munis_unsupported_allele.csv，避免 predict.py KeyError 崩整批。

输入：
  scripts/out/newtools/uniq_pep_hla.csv  (peptide, HLA_Allele, source)

输出（均在本脚本所在目录 HPC/deploy/munis/）：
  munis_input.csv        ← run_munis.py 的输入
  munis_unsupported.csv  ← 记录跳过的行（肽长 / 非 Class I）

官方源（2026-06-29 核自 github.com/jwohlwend/munis main predict.py + munis/seqs.py）：
  - 输入 CSV 列：pep, mhc, left, right（predict.py main() 显式 check left/right 列存在）。
  - HLA 编码：SEQUENCES 键为 HLA-A02:01（无星号 2 字段）；
    process() 用 self.sequences[mhc.replace("*","")]，clean_mhc_name 另截 2 字段。
  - 肽长：--min_len 8 / --max_len 15（默认值，README）。

用法：
  python prep_input.py [--uniq-csv PATH] [--out-dir DIR] [--smoke N]
  --smoke N: 只取前 N 行做快速格式验证（默认 0=全量）。
"""

import argparse
import csv
import pathlib
import sys

# ---------------------------------------------------------------------------
# 路径默认值（相对脚本位置，适配 HPC/deploy/munis/ 位置）
# ---------------------------------------------------------------------------
SCRIPT_DIR = pathlib.Path(__file__).parent.resolve()
PROJECT_DIR = SCRIPT_DIR.parents[2]   # QuantImmuBench/

DEFAULT_UNIQ_CSV = PROJECT_DIR / "scripts" / "out" / "newtools" / "uniq_pep_hla.csv"
DEFAULT_OUT_DIR = SCRIPT_DIR    # 输出到本脚本同目录

# 肽长范围（MUNIS MHC-I：8–15mer；universe 实际 8–14，全部通过）
MIN_PEP_LEN = 8
MAX_PEP_LEN = 15

# MHC-I 基因前缀
MHCI_PREFIXES = ("HLA-A", "HLA-B", "HLA-C")


# ---------------------------------------------------------------------------
# HLA 格式归一（镜像官方 predict.py::clean_mhc_name，零改动）
# ---------------------------------------------------------------------------

def clean_mhc_name(mhc: str) -> str:
    """
    HLA-A*02:01 → HLA-A02:01（去星号 + 截到前 2 字段）。
    照抄官方 predict.py::clean_mhc_name，使结果恰为 MUNIS SEQUENCES 字典键。
    """
    mhc = mhc.replace("*", "")
    if len(mhc.split(":")) > 1:
        mhc = ":".join(mhc.split(":")[:2])
    return mhc


def is_mhci(hla: str) -> bool:
    return hla.startswith(MHCI_PREFIXES)


# ---------------------------------------------------------------------------
# 主逻辑
# ---------------------------------------------------------------------------

def prep(uniq_csv: pathlib.Path, out_dir: pathlib.Path, smoke: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    input_csv_path = out_dir / "munis_input.csv"
    unsupported_csv_path = out_dir / "munis_unsupported.csv"

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

        # 表头：pep/mhc/left/right 是官方 predict.py 要求列；
        #       HLA_Allele/source 是穿透列（predict.py 保留所有输入列到输出）。
        writer_in.writerow(["pep", "mhc", "left", "right", "HLA_Allele", "source"])
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

            # MHC-I 过滤（MUNIS 人类 HLA-I 仅 A/B/C；SEQUENCES 另含鼠/牛等非人类，不用）
            if not is_mhci(hla):
                n_classII_skip += 1
                writer_uns.writerow([pep, hla, src, "not_mhc_class_I"])
                continue

            mhc = clean_mhc_name(hla)
            # left/right 留空 —— run 阶段不传 --use_flanks，官方 predict.py 覆盖为 "GGGGG"
            writer_in.writerow([pep, mhc, "", "", hla, src])
            n_written += 1

            if smoke and n_written >= smoke:
                print(f"[prep_input] --smoke {smoke}: 已写 {n_written} 行，提前结束。")
                break

    print(f"[prep_input] 读入总行数:            {n_total}")
    print(f"[prep_input] 肽长过滤跳过:          {n_len_skip}")
    print(f"[prep_input] 非 MHC-I 跳过:         {n_classII_skip}")
    print(f"[prep_input] 写入 munis_input:      {n_written}")
    print(f"[prep_input] 输出: {input_csv_path}")
    print(f"[prep_input] 不支持记录: {unsupported_csv_path}")
    print("[prep_input] 注意：allele 是否在 MUNIS SEQUENCES 字典内由 run_munis.py 二次过滤。")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="准备 MUNIS 输入 CSV（肽长 8-15 + MHC-I 过滤 + HLA 归一为 SEQUENCES 键格式）"
    )
    parser.add_argument(
        "--uniq-csv",
        default=str(DEFAULT_UNIQ_CSV),
        help="uniq_pep_hla.csv 路径（默认 scripts/out/newtools/uniq_pep_hla.csv）",
    )
    parser.add_argument(
        "--out-dir",
        default=str(DEFAULT_OUT_DIR),
        help="输出目录（默认本脚本所在目录 HPC/deploy/munis/）",
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
