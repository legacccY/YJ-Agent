"""
prep_input.py  --  QuantImmuBench BigMHC -m=im 输入准备
服务项目：quantimmu-bench 扩张 v2 lever=部署BigMHC immunogenicity

功能：
  读 scripts/out/newtools/uniq_pep_hla.csv (peptide, HLA_Allele, source; 53582 行)
  输出 BigMHC predict.py 所需的双列 CSV：
      列 0 = mhc (HLA_Allele，HLA-A*02:01 格式，BigMHC 原生支持无需转换)
      列 1 = pep (peptide)
  文件：bigmhc_inputs/bigmhc_input.csv  (含表头 mhc,pep，供 -c=1 跳过)

  同时输出 bigmhc_inputs/bigmhc_index.csv 供 parse_output.py 校验行数用。

HLA 格式说明：
  BigMHC 使用模糊字符串匹配。HLA-A*02:01、A*02:01、HLAA0201、A0201
  均被视为等价。本 benchmark 输入已为 HLA-A*02:01 格式，直接透传，无需转换。
  （来源：BigMHC README src/cli.py _parseModel 及 mhcuid.py 逻辑）

用法：
  python prep_input.py [--uniq-pep-hla <csv>] [--out-dir <dir>] [--smoke N]
  默认 uniq-pep-hla: scripts/out/newtools/uniq_pep_hla.csv（相对脚本向上3级）
  默认 out-dir:      HPC/deploy/bigmhc_im/bigmhc_inputs/

  --smoke N：只处理前 N 行，输出到 bigmhc_input_smoke.csv（供快速烟测）
"""

import argparse
import csv
import pathlib


# ---------------------------------------------------------------------------
# 准备主逻辑
# ---------------------------------------------------------------------------

def prep(
    uniq_pep_hla_path: pathlib.Path,
    out_dir: pathlib.Path,
    smoke_n: int = 0,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    suffix = "_smoke" if smoke_n > 0 else ""
    out_csv = out_dir / f"bigmhc_input{suffix}.csv"
    idx_csv = out_dir / f"bigmhc_index{suffix}.csv"

    written = 0
    skipped_empty = 0

    with (
        open(uniq_pep_hla_path, newline="", encoding="utf-8") as f_in,
        open(out_csv, "w", newline="", encoding="utf-8") as f_out,
        open(idx_csv, "w", newline="", encoding="utf-8") as f_idx,
    ):
        reader = csv.DictReader(f_in)
        writer_out = csv.writer(f_out)
        writer_idx = csv.writer(f_idx)

        # BigMHC default: -a=0 (col 0 = mhc), -p=1 (col 1 = pep), -c=1 (skip 1 header)
        writer_out.writerow(["mhc", "pep"])
        writer_idx.writerow(["row_idx", "peptide", "HLA_Allele", "source"])

        for i, row in enumerate(reader):
            if smoke_n > 0 and written >= smoke_n:
                break

            pep = row["peptide"].strip()
            hla = row["HLA_Allele"].strip()
            source = row["source"].strip()

            if not pep or not hla:
                skipped_empty += 1
                continue

            # HLA-A*02:01 格式直接透传，BigMHC 原生接受
            writer_out.writerow([hla, pep])
            writer_idx.writerow([written, pep, hla, source])
            written += 1

    print(f"[prep_input] 写入 {out_csv.name}: {written} 行（含表头 = {written + 1} 行）")
    print(f"[prep_input] 跳过空行: {skipped_empty}")
    print(f"[prep_input] index: {idx_csv}")
    print(f"[prep_input] BigMHC 调用示例（从 repo/src/ 目录运行）:")
    print(f"  python predict.py \\")
    print(f"    -i={out_csv.resolve()} \\")
    print(f"    -m=im \\")
    print(f"    -a=0 -p=1 -c=1 \\")
    print(f"    -d=cpu \\")
    print(f"    -o={out_dir.resolve() / f'bigmhc_output{suffix}.prd'}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    script_dir = pathlib.Path(__file__).parent
    repo_root = script_dir.parents[2]  # QuantImmuBench/
    default_uniq = repo_root / "scripts" / "out" / "newtools" / "uniq_pep_hla.csv"
    default_out_dir = script_dir / "bigmhc_inputs"

    parser = argparse.ArgumentParser(description="Prepare BigMHC -m=im input from uniq_pep_hla.csv")
    parser.add_argument(
        "--uniq-pep-hla",
        default=str(default_uniq),
        help="uniq_pep_hla.csv 路径（peptide, HLA_Allele, source）",
    )
    parser.add_argument(
        "--out-dir",
        default=str(default_out_dir),
        help="输出目录（默认 bigmhc_inputs/）",
    )
    parser.add_argument(
        "--smoke",
        type=int,
        default=0,
        metavar="N",
        help="烟测模式：只处理前 N 行，输出 bigmhc_input_smoke.csv（0 = 关闭）",
    )
    args = parser.parse_args()

    uniq_path = pathlib.Path(args.uniq_pep_hla)
    if not uniq_path.exists():
        raise FileNotFoundError(f"uniq_pep_hla.csv 不存在: {uniq_path}")

    prep(
        uniq_pep_hla_path=uniq_path,
        out_dir=pathlib.Path(args.out_dir),
        smoke_n=args.smoke,
    )


if __name__ == "__main__":
    main()
