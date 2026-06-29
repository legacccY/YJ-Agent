"""
prep_input.py — QuantImmuBench §工具部署  ImmugenX 输入准备
服务项目：quantimmu-bench §工具部署 免疫原侧 lever=补满到 20（I20 = ImmugenX）

功能：
  1. 读 uniq_pep_hla.csv（列: peptide, HLA_Allele, source；53582 行）
  2. 肽长过滤（ImmugenX 模型 peptide_length=15：保留 8–15mer；
     肽>15 官方 immugenx_jit_runner 会静默跳过；<8 罕见也剔，记 unsupported 原因 len）
  3. 只保留 MHC-I（HLA-A / HLA-B / HLA-C）；其余（HLA-DRB/DQ/DP 等 Class II）记 unsupported
  4. 写 immugenx_input.csv，列 = Antigen, HLA, HLA_Allele, source
     —— Antigen = peptide（官方 cli 读 "Antigen" 列）；
        HLA = HLA_Allele 原始带星号 'HLA-A*02:01'（官方用 mhcnames 包内部 normalize，直喂即可）；
        HLA_Allele = 同值穿透（供 parse 回贴 universe，与 base 表 HLA_Allele 同款带星号）；
        source 穿透。
  5. 写 immugenx_unsupported.csv（被剔行 + 原因），供 parse 阶段 NaN 回填参考

注意：本脚本不做 allele 库精过滤（保持纯 stdlib，与 munis/transhla prep 一致）。
  allele 不在 class1_pseudosequences.csv 库的行会让官方 HLAEncoder._fetch_hla 抛 ValueError
  崩整批 → 交 run_immugenx.py（已装 mhcnames 环境）剔到 immugenx_unsupported_allele.csv。

输入：
  scripts/out/newtools/uniq_pep_hla.csv  (peptide, HLA_Allele, source)

输出（均在本脚本所在目录 HPC/deploy/immugenx/）：
  immugenx_input.csv        ← run_immugenx.py 的输入（Antigen, HLA, HLA_Allele, source）
  immugenx_unsupported.csv  ← 记录跳过的行（肽长 / 非 Class I）

官方源（2026-06-29 核自亲手解包 zenodo immugenx_runner_pub）：
  - 输入 CSV：官方 README 要求至少 "Antigen" + "HLA" 两列；runner.py _run_and_save 用
    row["Antigen"]/row["HLA"]，额外列（HLA_Allele/source）原样保留到输出。
  - HLA 编码：encoders.py HLAEncoder 用 mhcnames.normalize_allele_name 解析，
    'HLA-A*02:01' 带星号格式可直喂（README §Inputs 明示 mhcnames 容错）。
  - 肽长：immugenx_jit_runner.load_and_process_data `if len(epitope) > peptide_length(15): skip`。

用法：
  python prep_input.py [--uniq-csv PATH] [--out-dir DIR] [--smoke N]
  --smoke N: 只取前 N 行做快速格式验证（默认 0=全量）。
"""

import argparse
import csv
import pathlib
import sys

# ---------------------------------------------------------------------------
# 路径默认值（相对脚本位置，适配 HPC/deploy/immugenx/ 位置）
# ---------------------------------------------------------------------------
SCRIPT_DIR = pathlib.Path(__file__).parent.resolve()
PROJECT_DIR = SCRIPT_DIR.parents[2]   # QuantImmuBench/

DEFAULT_UNIQ_CSV = PROJECT_DIR / "scripts" / "out" / "newtools" / "uniq_pep_hla.csv"
DEFAULT_OUT_DIR = SCRIPT_DIR    # 输出到本脚本同目录

# 肽长范围（ImmugenX 模型 peptide_length=15：保留 8–15mer；universe 实际 8–14，全过）
MIN_PEP_LEN = 8
MAX_PEP_LEN = 15

# MHC-I 基因前缀
MHCI_PREFIXES = ("HLA-A", "HLA-B", "HLA-C")


def is_mhci(hla: str) -> bool:
    return hla.startswith(MHCI_PREFIXES)


# ---------------------------------------------------------------------------
# 主逻辑
# ---------------------------------------------------------------------------

def prep(uniq_csv: pathlib.Path, out_dir: pathlib.Path, smoke: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    input_csv_path = out_dir / "immugenx_input.csv"
    unsupported_csv_path = out_dir / "immugenx_unsupported.csv"

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

        # 表头：Antigen/HLA 是官方 cli 要求列；HLA_Allele/source 穿透列（runner 保留到输出）。
        writer_in.writerow(["Antigen", "HLA", "HLA_Allele", "source"])
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

            # MHC-I 过滤（ImmugenX class1_pseudosequences 仅 HLA-A/B/C；另含 BoLA 等非人类，不用）
            if not is_mhci(hla):
                n_classII_skip += 1
                writer_uns.writerow([pep, hla, src, "not_mhc_class_I"])
                continue

            # Antigen=pep，HLA=原始带星号（官方 mhcnames 解析），HLA_Allele=同值穿透，source 穿透
            writer_in.writerow([pep, hla, hla, src])
            n_written += 1

            if smoke and n_written >= smoke:
                print(f"[prep_input] --smoke {smoke}: 已写 {n_written} 行，提前结束。")
                break

    print(f"[prep_input] 读入总行数:            {n_total}")
    print(f"[prep_input] 肽长过滤跳过:          {n_len_skip}")
    print(f"[prep_input] 非 MHC-I 跳过:         {n_classII_skip}")
    print(f"[prep_input] 写入 immugenx_input:   {n_written}")
    print(f"[prep_input] 输出: {input_csv_path}")
    print(f"[prep_input] 不支持记录: {unsupported_csv_path}")
    print("[prep_input] 注意：allele 是否在 class1_pseudosequences 库内由 run_immugenx.py 二次过滤。")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="准备 ImmugenX 输入 CSV（肽长 8-15 + MHC-I 过滤；HLA 带星号直喂 mhcnames）"
    )
    parser.add_argument(
        "--uniq-csv",
        default=str(DEFAULT_UNIQ_CSV),
        help="uniq_pep_hla.csv 路径（默认 scripts/out/newtools/uniq_pep_hla.csv）",
    )
    parser.add_argument(
        "--out-dir",
        default=str(DEFAULT_OUT_DIR),
        help="输出目录（默认本脚本所在目录 HPC/deploy/immugenx/）",
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
