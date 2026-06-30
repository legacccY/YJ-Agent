"""
prep_input.py — QuantImmuBench §工具部署 P10槽  MHCSeqNet 输入准备
服务项目：quantimmu-bench §工具部署 lever=补呈递组第 10 槽（替 MAAP）

功能（严格仿 mhcnuggets/prep_input.py，MHCSeqNet 同为 HLA-aware (peptide,HLA) 打分）：
  1. 从 uniq_pep_hla.csv (53582 unique peptide×HLA 对) 读输入
  2. 肽长过滤（MHC-I：8–15mer；universe 实际 8–14，全部通过 → 无行被砍）
  3. 只保留 MHC-I（HLA-A / HLA-B / HLA-C）；其余（Class II HLA-DRB/DQ/DP）记入 unsupported
  4. HLA 格式转换：universe 标准 HLA-A*02:01 → MHCSeqNet 输入格式
     ⚠️ TODO(主线 clone 后核 repo README/示例输入)：MHCSeqNet 究竟要哪种 allele 写法？
        researcher 已核「写法 HLA-A*02:01（带星号）」→ 当前 to_mhcseqnet_allele() 默认
        **保留带星号原样**（identity）。若 repo 实际要 HLA-A0201 / HLA-A02:01，改该函数即可。
  5. 写 mhcseqnet_input.csv（peptide, HLA_Allele, mhcseqnet_allele）
     —— HLA_Allele 保留原始带星号格式（供 parse 阶段回贴 universe，行序 join key），
        mhcseqnet_allele 是喂给 MHCSeqNet 的格式。该 csv 即「map」（行序 + 原始 HLA）。
  6. 写 mhcseqnet_unsupported.csv（被跳过的行 + 原因），供 parse 阶段 NaN 回填参考

输入：
  scripts/out/newtools/uniq_pep_hla.csv  (peptide, HLA_Allele, source)

输出（均在本脚本所在目录 HPC/deploy/mhcseqnet/）：
  mhcseqnet_input.csv        ← run_mhcseqnet.py 的输入
  mhcseqnet_unsupported.csv  ← 记录跳过的行（肽长 / 非 Class I）

运行前提（TODO 主线核精确版本，见 NOTES.md）：
  repo: github.com/cmb-chula/MHCSeqNet（Apache-2.0），权重自带 PretrainedModels/
  Python3 + Keras>=2.2 + TensorFlow>=1.6（TF1 老栈，需独立 env）+ numpy/scipy/sklearn

用法：
  python prep_input.py [--uniq-csv PATH] [--out-dir DIR] [--smoke N]
  --smoke N: 只取前 N 行做快速格式验证（默认 0=全量）。

官方源（TODO 主线 clone 后核 github.com/cmb-chula/MHCSeqNet README + PredictionInput 示例）：
  - HLA 写法：researcher 核为 HLA-A*02:01（带星号）→ 待 README 示例输入二次确认
  - MHC-I：pan-allele（one_hot_model + sequence_model），覆盖 HLA-A/B/C
"""

import argparse
import csv
import pathlib
import sys

# ---------------------------------------------------------------------------
# 路径默认值（相对脚本位置，适配 HPC/deploy/mhcseqnet/ 位置）
# ---------------------------------------------------------------------------
SCRIPT_DIR = pathlib.Path(__file__).parent.resolve()
PROJECT_DIR = SCRIPT_DIR.parents[2]   # QuantImmuBench/

DEFAULT_UNIQ_CSV = PROJECT_DIR / "scripts" / "out" / "newtools" / "uniq_pep_hla.csv"
DEFAULT_OUT_DIR = SCRIPT_DIR    # 输出到本脚本同目录

# 肽长范围（MHCSeqNet 支持 MHC-I 8–15mer；universe 实际 8–14，全部通过）
MIN_PEP_LEN = 8
MAX_PEP_LEN = 15

# MHC-I 基因前缀
MHCI_PREFIXES = ("HLA-A", "HLA-B", "HLA-C")


# ---------------------------------------------------------------------------
# HLA 格式转换
# ---------------------------------------------------------------------------

def to_mhcseqnet_allele(hla: str) -> str:
    """
    universe 标准 HLA-A*02:01 → MHCSeqNet 输入 allele 写法。

    ⚠️ TODO(主线核 repo README/示例)：researcher 核 MHCSeqNet 用 'HLA-A*02:01'（带星号）
       → 当前默认 **保留原样**（identity）。若 repo 实际要 HLA-A0201 / HLA-A02:01，
       在此改写（如 hla.replace('*','').replace(':','') 等）。
    """
    return hla


def is_mhci(hla: str) -> bool:
    return hla.startswith(MHCI_PREFIXES)


# ---------------------------------------------------------------------------
# 主逻辑
# ---------------------------------------------------------------------------

def load_supported_alleles(repo_dir: pathlib.Path) -> set:
    """
    读 sequence_model 的 AlleleInformation.txt 第一列 = 模型支持的 allele 集合。
    ⚠️ 主线烟测核实：MHCSeqNet 遇未在册 allele 直接 raise ValueError 整轮崩 →
       必须 prep 阶段预过滤，未支持 allele 路由 unsupported.csv（parse 阶段 NaN）。
    我们 65 allele 中 54 支持 / 11 罕见未支持（66:xx/38:xx/06:xx，仅 2.3% 行）。
    """
    info = repo_dir / "PretrainedModels" / "sequence_model" / "AlleleInformation.txt"
    sup = set()
    with open(info, newline="", encoding="utf-8") as fh:
        for line in fh:
            a = line.split(",", 1)[0].strip()
            if a:
                sup.add(a)
    return sup


def prep(uniq_csv: pathlib.Path, out_dir: pathlib.Path, smoke: int,
         repo_dir: pathlib.Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    input_csv_path = out_dir / "mhcseqnet_input.csv"
    unsupported_csv_path = out_dir / "mhcseqnet_unsupported.csv"

    supported = load_supported_alleles(repo_dir)
    print(f"[prep_input] sequence_model 支持 allele 数: {len(supported)}")

    n_total = 0
    n_written = 0
    n_len_skip = 0
    n_classII_skip = 0
    n_allele_skip = 0

    with open(uniq_csv, newline="", encoding="utf-8") as f_in, \
         open(input_csv_path, "w", newline="", encoding="utf-8") as f_out, \
         open(unsupported_csv_path, "w", newline="", encoding="utf-8") as f_unsup:
        reader = csv.DictReader(f_in)
        writer_in = csv.writer(f_out)
        writer_uns = csv.writer(f_unsup)

        # 表头
        writer_in.writerow(["peptide", "HLA_Allele", "mhcseqnet_allele"])
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

            # MHC-I 过滤
            if not is_mhci(hla):
                n_classII_skip += 1
                writer_uns.writerow([pep, hla, src, "not_mhc_class_I"])
                continue

            seqnet_allele = to_mhcseqnet_allele(hla)

            # allele 支持过滤（未在册 → MHCSeqNet 整轮崩，必须预过滤）
            if seqnet_allele not in supported:
                n_allele_skip += 1
                writer_uns.writerow([pep, hla, src, "allele_not_in_seqnet_model"])
                continue

            writer_in.writerow([pep, hla, seqnet_allele])
            n_written += 1

            if smoke and n_written >= smoke:
                print(f"[prep_input] --smoke {smoke}: 已写 {n_written} 行，提前结束。")
                break

    print(f"[prep_input] 读入总行数:            {n_total}")
    print(f"[prep_input] 肽长过滤跳过:          {n_len_skip}")
    print(f"[prep_input] 非 MHC-I 跳过:         {n_classII_skip}")
    print(f"[prep_input] allele 未支持跳过:     {n_allele_skip}")
    print(f"[prep_input] 写入 mhcseqnet_input:  {n_written}")
    print(f"[prep_input] 输出: {input_csv_path}")
    print(f"[prep_input] 不支持记录: {unsupported_csv_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="准备 MHCSeqNet 输入 CSV（肽长检查 + MHC-I 过滤 + HLA 格式转换）"
    )
    parser.add_argument(
        "--uniq-csv",
        default=str(DEFAULT_UNIQ_CSV),
        help="uniq_pep_hla.csv 路径（默认 scripts/out/newtools/uniq_pep_hla.csv）",
    )
    parser.add_argument(
        "--out-dir",
        default=str(DEFAULT_OUT_DIR),
        help="输出目录（默认本脚本所在目录 HPC/deploy/mhcseqnet/）",
    )
    parser.add_argument(
        "--smoke",
        type=int,
        metavar="N",
        default=0,
        help="烟测模式：只写前 N 行（N=0=全量）",
    )
    parser.add_argument(
        "--repo-dir",
        default=str(pathlib.Path.home() / "quantimmu" / "tools_repos" / "MHCSeqNet"),
        help="MHCSeqNet repo 目录（读 AlleleInformation.txt 做 allele 支持过滤）",
    )
    args = parser.parse_args()

    uniq_csv = pathlib.Path(args.uniq_csv)
    out_dir = pathlib.Path(args.out_dir)
    repo_dir = pathlib.Path(args.repo_dir)

    if not uniq_csv.exists():
        print(f"[prep_input] ERROR: 输入文件不存在: {uniq_csv}", file=sys.stderr)
        sys.exit(1)

    prep(uniq_csv, out_dir, args.smoke, repo_dir)


if __name__ == "__main__":
    main()
