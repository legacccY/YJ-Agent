"""
prep_input.py — QuantImmuBench §工具部署 第20槽  DeepNetBim 输入准备
服务项目：quantimmu-bench §工具部署 lever=补免疫原性组第 20 槽（DeepNetBim）

功能（严格仿 mhcseqnet/prep_input.py，但 DeepNetBim **仅支持 9-mer**）：
  1. 从 uniq_pep_hla.csv (53582 unique peptide×HLA 对) 读输入
  2. 肽长过滤：**只保留 9-mer**（DeepNetBim 模型架构固定 9 位输入，非 9mer 不支持）
     → 非 9mer 全部进 unsupported 表，parse 阶段填 NaN（低覆盖 ~17%，同 NetTepi caveat）
  3. 只保留 MHC-I（HLA-A / HLA-B / HLA-C）；其余（Class II HLA-DRB/DQ/DP）记入 unsupported
  4. HLA 格式转换：universe 标准 'HLA-A*01:01'（带星号）→ DeepNetBim 输入 'HLA-A01:01'
     ⚠️ 注意：DeepNetBim 写法 **无星号、保留冒号**（HLA-A01:01），区别于 universe 的
        带星号 HLA-A*01:01。当前 to_deepnetbim_allele() 仅去星号（.replace('*','')）。
     ⚠️ TODO(主线 clone 后核 repo README/示例输入)：核 DeepNetBim 确切 allele 写法
        （researcher 已核 'HLA-A01:01' 无星保冒号 → 当前默认）。若 repo 实际要别的
        （如 HLA-A0101 无冒号），改该函数即可。
  5. 写 deepnetbim_input.csv（peptide, HLA_Allele, mhc, sequence）
     —— peptide/HLA_Allele 保留原始（带星号），供 parse 回贴 universe 的 join key；
        mhc/sequence 是喂给 DeepNetBim 官方 predict 的两列（mhc=去星 HLA，sequence=肽）。
        该 csv 即「map」（原始 HLA ↔ 喂模型格式）。
  6. 写 deepnetbim_unsupported.csv（被跳过的行 + 原因），供 parse NaN 回填参考

输入：
  scripts/out/newtools/uniq_pep_hla.csv  (peptide, HLA_Allele, source)

输出（均在本脚本所在目录 HPC/deploy/deepnetbim/）：
  deepnetbim_input.csv        ← run_deepnetbim.py 的输入（含 map 列）
  deepnetbim_unsupported.csv  ← 记录跳过的行（非 9mer / 非 Class I）

运行前提（TODO 主线核精确版本，见 NOTES.md）：
  repo: github.com/Li-Lab-SJTU/DeepNetBim（**license=null，发表前须邮件索授权**），
  权重 repo 内自带 data/model_immuno.h5（36.4MB），clone 即得；
  Python + keras 2.2.4 + numpy/pandas/scipy/sklearn（TF1 老栈，需独立 env）+ 纯 CPU。

用法：
  python prep_input.py [--uniq-csv PATH] [--out-dir DIR] [--smoke N]
  --smoke N: 只取前 N 行（已过 9mer+MHCI 过滤）做快速格式验证（默认 0=全量）。

官方源（TODO 主线 clone 后核 github.com/Li-Lab-SJTU/DeepNetBim README + predict 示例）：
  - HLA 写法：researcher 核为 'HLA-A01:01'（无星保冒号）→ 待 README 示例输入二次确认
  - 仅 9-mer：universe 53582 对里只 ~9011 个 9-mer → 覆盖 ~17%（低覆盖，同 NetTepi）
"""

import argparse
import csv
import pathlib
import sys

# ---------------------------------------------------------------------------
# 路径默认值（相对脚本位置，适配 HPC/deploy/deepnetbim/ 位置）
# ---------------------------------------------------------------------------
SCRIPT_DIR = pathlib.Path(__file__).parent.resolve()
PROJECT_DIR = SCRIPT_DIR.parents[2]   # QuantImmuBench/

DEFAULT_UNIQ_CSV = PROJECT_DIR / "scripts" / "out" / "newtools" / "uniq_pep_hla.csv"
DEFAULT_OUT_DIR = SCRIPT_DIR    # 输出到本脚本同目录

# DeepNetBim **仅支持 9-mer**（模型架构固定 9 位输入）
SUPPORTED_PEP_LEN = 9

# MHC-I 基因前缀
MHCI_PREFIXES = ("HLA-A", "HLA-B", "HLA-C")


# ---------------------------------------------------------------------------
# HLA 格式转换
# ---------------------------------------------------------------------------

def to_deepnetbim_allele(hla: str) -> str:
    """
    universe 标准 'HLA-A*01:01'（带星号）→ DeepNetBim 输入 'HLA-A01:01'（无星保冒号）。

    ⚠️ TODO(主线核 repo README/示例)：researcher 核 DeepNetBim 用 'HLA-A01:01'
       （无星号、保留冒号）→ 当前实现 = 仅去星号。若 repo 实际要 'HLA-A0101'
       （连冒号也去），改为 hla.replace('*','').replace(':','')。
    """
    return hla.replace("*", "")


def is_mhci(hla: str) -> bool:
    return hla.startswith(MHCI_PREFIXES)


# ---------------------------------------------------------------------------
# 主逻辑
# ---------------------------------------------------------------------------

def prep(uniq_csv: pathlib.Path, out_dir: pathlib.Path, smoke: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    input_csv_path = out_dir / "deepnetbim_input.csv"
    unsupported_csv_path = out_dir / "deepnetbim_unsupported.csv"

    n_total = 0
    n_written = 0
    n_len_skip = 0
    n_classII_skip = 0

    with open(uniq_csv, newline="", encoding="utf-8") as f_in, \
         open(input_csv_path, "w", newline="", encoding="utf-8") as f_out, \
         open(unsupported_csv_path, "w", newline="", encoding="utf-8") as f_unsup:
        reader = csv.DictReader(f_in)
        writer_in = csv.writer(f_out)
        writer_uns = csv.writer(f_unsup)

        # 表头
        writer_in.writerow(["peptide", "HLA_Allele", "mhc", "sequence"])
        writer_uns.writerow(["peptide", "HLA_Allele", "source", "reason"])

        for row in reader:
            n_total += 1
            pep = row["peptide"].strip()
            hla = row["HLA_Allele"].strip()
            src = row.get("source", "").strip()

            # 肽长过滤：仅 9-mer
            if len(pep) != SUPPORTED_PEP_LEN:
                n_len_skip += 1
                writer_uns.writerow([pep, hla, src, f"len={len(pep)}_not_9mer"])
                continue

            # MHC-I 过滤
            if not is_mhci(hla):
                n_classII_skip += 1
                writer_uns.writerow([pep, hla, src, "not_mhc_class_I"])
                continue

            db_allele = to_deepnetbim_allele(hla)
            # mhc=喂模型 HLA（去星）, sequence=肽
            writer_in.writerow([pep, hla, db_allele, pep])
            n_written += 1

            if smoke and n_written >= smoke:
                print(f"[prep_input] --smoke {smoke}: 已写 {n_written} 行，提前结束。")
                break

    print(f"[prep_input] 读入总行数:            {n_total}")
    print(f"[prep_input] 非 9mer 跳过:          {n_len_skip}")
    print(f"[prep_input] 非 MHC-I 跳过:         {n_classII_skip}")
    print(f"[prep_input] 写入 deepnetbim_input: {n_written}  (仅 9-mer)")
    print(f"[prep_input] 输出: {input_csv_path}")
    print(f"[prep_input] 不支持记录: {unsupported_csv_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="准备 DeepNetBim 输入 CSV（仅 9mer 过滤 + MHC-I 过滤 + HLA 格式转换）"
    )
    parser.add_argument(
        "--uniq-csv",
        default=str(DEFAULT_UNIQ_CSV),
        help="uniq_pep_hla.csv 路径（默认 scripts/out/newtools/uniq_pep_hla.csv）",
    )
    parser.add_argument(
        "--out-dir",
        default=str(DEFAULT_OUT_DIR),
        help="输出目录（默认本脚本所在目录 HPC/deploy/deepnetbim/）",
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
