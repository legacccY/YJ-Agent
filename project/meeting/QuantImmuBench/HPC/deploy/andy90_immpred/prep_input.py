"""
prep_input.py — QuantImmuBench §工具部署  andy90 immunogenicity_predictor 输入准备
服务项目：quantimmu-bench §工具部署 lever=免疫原补位（补到 20）

功能：
  1. 读 uniq_pep_hla.csv（列: peptide, HLA_Allele, source；53583 行 (肽,HLA) 对）
  2. 过滤 8-11mer（andy90 / netMHCpan-4.x Class-I 支持范围）
  3. 12-14mer → 记入 skipped（parse_output.py 阶段填 NaN）
  4. HLA 转 andy90 格式：去星  HLA-A*02:01 → HLA-A02:01（与项目 h.replace('*','') 一致）
  5. 按 HLA 分组写 per-HLA fasta（只跑实际出现的 (肽,HLA) 对，避开 7437×65 笛卡尔爆炸）
     —— 这样仍 100% 忠实官方：amplitude=self*foreign/binding，self/foreign 只依赖肽，
        binding=netMHCpan(%Rank) 只依赖 (HLA,肽)，逐 HLA 跑与一次跑全 HLA 数值完全一致。
  6. 写 manifest（run_andy90.py 按它逐 HLA 调 run_andy90.R）

andy90 输入格式（官方 main.R / src/binding_prediction.R 核实 2026-06-29）：
  - file_fasta：肽的 FASTA（read.fasta(as.string) + toupper）；每条记录一个肽
  - HLAs：逗号分隔字符串，无空格，去星，如 "HLA-A02:01,HLA-A03:01"
  - 肽长 8-11mer（README："all the 8-11mers of SARS-CoV-2"）

输入：
  scripts/out/newtools/uniq_pep_hla.csv  (peptide, HLA_Allele, source)

输出（均在 andy90_inputs/ 子目录，本脚本所在目录下）：
  andy90_inputs/<safe_hla>.fasta   ← 每个 HLA 的肽 FASTA（run_andy90.R 输入）
  andy90_inputs/andy90_manifest.csv ← hla_netmhcpan, hla_star, fasta_file, n_peptides
  andy90_inputs/andy90_skipped.csv  ← 超长肽 (12-14mer → parse 填 NaN)

用法：
  python prep_input.py [--uniq-csv PATH] [--inputs-dir DIR] [--smoke N]
  --smoke N：只保留前 N 个有效 (肽,HLA) 对（烟测，建议 N=5）
"""

import argparse
import csv
import pathlib
import sys

# ---------------------------------------------------------------------------
# 路径默认值（相对脚本位置，适配 HPC/deploy/andy90_immpred/ 位置）
# ---------------------------------------------------------------------------
SCRIPT_DIR  = pathlib.Path(__file__).parent.resolve()
PROJECT_DIR = SCRIPT_DIR.parents[2]   # QuantImmuBench/

DEFAULT_UNIQ_CSV   = PROJECT_DIR / "scripts" / "out" / "newtools" / "uniq_pep_hla.csv"
DEFAULT_INPUTS_DIR = SCRIPT_DIR / "andy90_inputs"

# andy90 / netMHCpan Class-I 支持肽长（8-11mer）
MIN_PEP_LEN = 8
MAX_PEP_LEN = 11


def hla_to_andy90(h: str) -> str:
    """HLA-A*02:01 → HLA-A02:01（去星，andy90/netMHCpan 格式）。"""
    return h.replace("*", "").strip()


def safe_hla_filename(h_nostar: str) -> str:
    """HLA-A02:01 → HLA-A02_01（去掉冒号做文件名安全）。"""
    return h_nostar.replace(":", "_").replace("*", "").replace("/", "_")


def prep(uniq_csv: pathlib.Path, inputs_dir: pathlib.Path, smoke: int) -> None:
    inputs_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = inputs_dir / "andy90_manifest.csv"
    skipped_path  = inputs_dir / "andy90_skipped.csv"

    # 按 HLA 收集肽（去重，保持插入序）
    hla_to_peps: dict[str, list[str]] = {}   # key=去星 HLA, value=肽列表(去重)
    hla_to_peps_seen: dict[str, set] = {}
    hla_star_map: dict[str, str] = {}        # 去星 → 原星格式（仅记录，parse 用归一无需依赖）

    n_total = 0
    n_long  = 0
    n_short = 0
    n_pairs = 0   # 写入的有效 (肽,HLA) 对数

    with (
        open(uniq_csv, newline="", encoding="utf-8") as f_in,
        open(skipped_path, "w", newline="", encoding="utf-8") as f_skip,
    ):
        reader = csv.DictReader(f_in)
        writer_skip = csv.writer(f_skip)
        writer_skip.writerow(["peptide", "HLA_Allele", "source", "reason"])

        for row in reader:
            n_total += 1
            pep = row["peptide"].strip()
            hla = row["HLA_Allele"].strip()
            src = row.get("source", "").strip()
            plen = len(pep)

            if plen < MIN_PEP_LEN:
                n_short += 1
                writer_skip.writerow([pep, hla, src, f"len={plen}_lt_{MIN_PEP_LEN}"])
                continue
            if plen > MAX_PEP_LEN:
                n_long += 1
                writer_skip.writerow([pep, hla, src, f"len={plen}_gt_{MAX_PEP_LEN}_NaN_in_parse"])
                continue

            # smoke：只保留前 N 个有效对
            if smoke > 0 and n_pairs >= smoke:
                continue

            hla_nostar = hla_to_andy90(hla)
            hla_star_map.setdefault(hla_nostar, hla)
            if hla_nostar not in hla_to_peps:
                hla_to_peps[hla_nostar] = []
                hla_to_peps_seen[hla_nostar] = set()
            if pep not in hla_to_peps_seen[hla_nostar]:
                hla_to_peps[hla_nostar].append(pep)
                hla_to_peps_seen[hla_nostar].add(pep)
            n_pairs += 1

    # 写 per-HLA fasta + manifest
    with open(manifest_path, "w", newline="", encoding="utf-8") as f_man:
        writer_man = csv.writer(f_man)
        writer_man.writerow(["hla_netmhcpan", "hla_star", "fasta_file", "n_peptides"])
        for hla_nostar, peps in hla_to_peps.items():
            fname = f"{safe_hla_filename(hla_nostar)}.fasta"
            fpath = inputs_dir / fname
            with open(fpath, "w", encoding="utf-8") as f_fa:
                for pep in peps:
                    # FASTA：header 用肽序列本身（andy90 read.fasta 只取序列，header 不影响）
                    f_fa.write(f">{pep}\n{pep}\n")
            writer_man.writerow([hla_nostar, hla_star_map[hla_nostar], fname, len(peps)])

    print(f"[prep_input] 读入总行数:           {n_total}")
    print(f"[prep_input] <{MIN_PEP_LEN}mer（理论为0）:   {n_short}")
    print(f"[prep_input] >{MAX_PEP_LEN}mer（→NaN）:      {n_long}")
    print(f"[prep_input] 写入有效 (肽,HLA) 对: {n_pairs}")
    print(f"[prep_input] 涉及 HLA 数:          {len(hla_to_peps)}")
    if smoke > 0:
        print(f"[prep_input] [SMOKE] 仅前 {n_pairs} 对，全量去掉 --smoke")
    print(f"[prep_input] fasta 目录: {inputs_dir}")
    print(f"[prep_input] manifest:   {manifest_path}")
    print(f"[prep_input] skipped:    {skipped_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="准备 andy90 输入（按 HLA 分组写 fasta + manifest，过滤 8-11mer）"
    )
    parser.add_argument(
        "--uniq-csv",
        default=str(DEFAULT_UNIQ_CSV),
        help="uniq_pep_hla.csv 路径（默认 scripts/out/newtools/uniq_pep_hla.csv）",
    )
    parser.add_argument(
        "--inputs-dir",
        default=str(DEFAULT_INPUTS_DIR),
        help="输出目录（默认本脚本目录下 andy90_inputs/）",
    )
    parser.add_argument(
        "--smoke",
        type=int,
        default=0,
        metavar="N",
        help="烟测：只保留前 N 个有效 (肽,HLA) 对（建议 N=5，0=关闭）",
    )
    args = parser.parse_args()

    uniq_csv   = pathlib.Path(args.uniq_csv)
    inputs_dir = pathlib.Path(args.inputs_dir)

    if not uniq_csv.exists():
        print(f"[prep_input] ERROR: 输入文件不存在: {uniq_csv}", file=sys.stderr)
        sys.exit(1)

    prep(uniq_csv, inputs_dir, smoke=args.smoke)


if __name__ == "__main__":
    main()
