"""
prep_input.py — QuantImmuBench §Tier-0  MHCflurry 2.0 输入准备
服务项目：quantimmu-bench §Tier-0 lever=部署MHCflurry 扩张v2第一波

功能：
  1. 从 uniq_pep_hla.csv (53582 unique peptide×HLA 对) 读输入
  2. 加载 Class1PresentationPredictor 获取 supported_alleles 集合
  3. 过滤不支持的 allele：记录到 mhcflurry_unsupported.csv，分数在 parse_output.py 阶段填 NaN
  4. 过滤肽长范围（要求 8–15mer，universe 实际 8–14 均通过）
  5. 写 mhcflurry_input.csv（peptide, HLA_Allele）——仅保留可预测行
  6. 写 mhcflurry_unsupported.csv——不支持的 allele 记录，供 parse 阶段 NaN 回填参考

输入：
  scripts/out/newtools/uniq_pep_hla.csv  (peptide, HLA_Allele, source)

输出（均在本脚本所在目录 HPC/deploy/mhcflurry/）：
  mhcflurry_input.csv        ← run_mhcflurry.py 的输入
  mhcflurry_unsupported.csv  ← 记录跳过的 allele

运行前提：
  pip install mhcflurry
  mhcflurry-downloads fetch models_class1_presentation

用法：
  python prep_input.py [--uniq-csv PATH] [--out-dir DIR] [--skip-predictor]
  --skip-predictor: 跳过加载预测器（仅做长度过滤，跳过 allele 支持性检查）。
                    用于模型尚未下载时的快速格式验证。

API 来源（2026-06-26 核自 github.com/openvax/mhcflurry master）：
  Class1PresentationPredictor.supported_alleles —— property，返回 list[str]，格式 HLA-A*02:01
  github.com/openvax/mhcflurry/blob/master/mhcflurry/class1_presentation_predictor.py
"""

import argparse
import csv
import pathlib
import sys

# ---------------------------------------------------------------------------
# 路径默认值（相对脚本位置，适配 HPC/deploy/mhcflurry/ 位置）
# ---------------------------------------------------------------------------
SCRIPT_DIR = pathlib.Path(__file__).parent.resolve()
PROJECT_DIR = SCRIPT_DIR.parents[2]   # QuantImmuBench/

DEFAULT_UNIQ_CSV = PROJECT_DIR / "scripts" / "out" / "newtools" / "uniq_pep_hla.csv"
DEFAULT_OUT_DIR  = SCRIPT_DIR   # 输出到本脚本同目录

# 肽长范围（8–15mer；universe 实际 8–14，全部通过）
MIN_PEP_LEN = 8
MAX_PEP_LEN = 15


# ---------------------------------------------------------------------------
# 主逻辑
# ---------------------------------------------------------------------------

def load_supported_alleles():
    """加载 Class1PresentationPredictor 并返回 supported_alleles 集合。"""
    try:
        from mhcflurry import Class1PresentationPredictor
    except ImportError:
        print("[prep_input] ERROR: mhcflurry 未安装。请先 pip install mhcflurry", file=sys.stderr)
        sys.exit(1)

    print("[prep_input] 加载 Class1PresentationPredictor (首次加载可能需要数分钟)...")
    predictor = Class1PresentationPredictor.load()
    alleles = set(predictor.supported_alleles)
    print(f"[prep_input] supported_alleles: {len(alleles)} 个")
    return alleles


def prep(uniq_csv: pathlib.Path, out_dir: pathlib.Path, skip_predictor: bool) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    input_csv_path      = out_dir / "mhcflurry_input.csv"
    unsupported_csv_path = out_dir / "mhcflurry_unsupported.csv"

    # 获取 supported alleles（或 None → 跳过检查）
    supported = load_supported_alleles() if not skip_predictor else None
    if skip_predictor:
        print("[prep_input] --skip-predictor: 跳过 allele 支持性检查，仅做肽长过滤")

    n_total       = 0
    n_written     = 0
    n_len_skip    = 0
    n_allele_skip = 0

    with (
        open(uniq_csv, newline="", encoding="utf-8") as f_in,
        open(input_csv_path, "w", newline="", encoding="utf-8") as f_out,
        open(unsupported_csv_path, "w", newline="", encoding="utf-8") as f_unsup,
    ):
        reader      = csv.DictReader(f_in)
        writer_in   = csv.writer(f_out)
        writer_uns  = csv.writer(f_unsup)

        # 表头
        writer_in.writerow(["peptide", "HLA_Allele"])
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

            # Allele 支持性过滤
            if supported is not None and hla not in supported:
                n_allele_skip += 1
                writer_uns.writerow([pep, hla, src, "allele_not_supported"])
                continue

            writer_in.writerow([pep, hla])
            n_written += 1

    print(f"[prep_input] 读入总行数:            {n_total}")
    print(f"[prep_input] 肽长过滤跳过:          {n_len_skip}")
    print(f"[prep_input] Allele 不支持跳过:     {n_allele_skip}")
    print(f"[prep_input] 写入 mhcflurry_input:  {n_written}")
    print(f"[prep_input] 输出: {input_csv_path}")
    print(f"[prep_input] 不支持记录: {unsupported_csv_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="准备 MHCflurry 2.0 输入 CSV（过滤不支持 allele + 肽长检查）"
    )
    parser.add_argument(
        "--uniq-csv",
        default=str(DEFAULT_UNIQ_CSV),
        help="uniq_pep_hla.csv 路径（默认 scripts/out/newtools/uniq_pep_hla.csv）",
    )
    parser.add_argument(
        "--out-dir",
        default=str(DEFAULT_OUT_DIR),
        help="输出目录（默认本脚本所在目录 HPC/deploy/mhcflurry/）",
    )
    parser.add_argument(
        "--skip-predictor",
        action="store_true",
        help="跳过加载预测器（模型未下载时用，仅做肽长过滤）",
    )
    args = parser.parse_args()

    uniq_csv = pathlib.Path(args.uniq_csv)
    out_dir  = pathlib.Path(args.out_dir)

    if not uniq_csv.exists():
        print(f"[prep_input] ERROR: 输入文件不存在: {uniq_csv}", file=sys.stderr)
        sys.exit(1)

    prep(uniq_csv, out_dir, args.skip_predictor)


if __name__ == "__main__":
    main()
