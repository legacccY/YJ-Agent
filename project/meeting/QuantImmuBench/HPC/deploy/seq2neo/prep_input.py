"""
prep_input.py  --  QuantImmuBench Seq2Neo immuno 输入准备
服务项目：quantimmu-bench G1 工具补齐 lever=部署 Seq2Neo immunogenicity

功能：
  读 scripts/out/newtools/uniq_pep_hla.csv (peptide, HLA_Allele, source; 53582 行)
  输出 Seq2Neo `immuno --mode multiple` 所需的双列 CSV：
      列名 0 = Pep（peptide；确切列名 `Pep`，P 大写——researcher 核实自 Seq2Neo 文档）
      列名 1 = HLA（HLA allele，转成 `HLA-B44:02` 格式：无星号无空格）
  文件：seq2neo_inputs/seq2neo_input.csv  （含表头 Pep,HLA）

  同时输出 seq2neo_inputs/seq2neo_index.csv 供 parse_output.py 校验/调试用。

HLA 格式转换（关键，researcher 核实）：
  benchmark universe 的 HLA_Allele 为 `HLA-A*02:01` 格式。
  Seq2Neo 要求 `HLA-B44:02` 格式（无星号、无空格）。
  转换规则：去掉星号 `*` 即可：`HLA-A*02:01` -> `HLA-A02:01`。
  （同时 strip 空格防意外空白。其余字符原样保留。）

肽长过滤（关键，researcher 核实）：
  Seq2Neo netMHCpan/netCTLpan 链支持 8-11mer。
  - 8 <= len <= 11：写入 Seq2Neo 输入。
  - len == 12 或其它越界：跳过（不写入 Seq2Neo 输入），记录跳过数。
    parse_output.py 对这些行回贴 NaN（不在 score_map 即自然 NaN）。
  # TODO: 12mer 在 Seq2Neo 中的确切行为（直接报错 / 静默丢弃）未实跑确认；
  #       本脚本保守跳过 12mer 以免整批崩，待装后实跑核实是否可放宽。

用法：
  python prep_input.py [--uniq-pep-hla <csv>] [--out-dir <dir>] [--smoke N]
  默认 uniq-pep-hla: scripts/out/newtools/uniq_pep_hla.csv（相对脚本向上3级）
  默认 out-dir:      HPC/deploy/seq2neo/seq2neo_inputs/

  --smoke N：只处理前 N 行（通过过滤后计数），输出到 seq2neo_input_smoke.csv

红线：本脚本不运行 Seq2Neo（linux-only + netCTLpan 未部署）。仅生成输入文件。
"""

import argparse
import csv
import pathlib


# ---------------------------------------------------------------------------
# HLA 格式转换：HLA-A*02:01 -> HLA-A02:01（去星号、去空格）
# ---------------------------------------------------------------------------

def to_seq2neo_hla(hla: str) -> str:
    """benchmark `HLA-A*02:01` 格式 -> Seq2Neo `HLA-A02:01` 格式（去星号去空格）。"""
    return hla.strip().replace("*", "").replace(" ", "")


# ---------------------------------------------------------------------------
# 肽长合法性：Seq2Neo 支持 8-11mer
# ---------------------------------------------------------------------------

MIN_LEN = 8
MAX_LEN = 11


def is_supported_len(pep: str) -> bool:
    return MIN_LEN <= len(pep) <= MAX_LEN


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
    out_csv = out_dir / f"seq2neo_input{suffix}.csv"
    idx_csv = out_dir / f"seq2neo_index{suffix}.csv"

    written = 0
    skipped_empty = 0
    skipped_len = 0  # 越界肽长（含 12mer）

    with (
        open(uniq_pep_hla_path, newline="", encoding="utf-8") as f_in,
        open(out_csv, "w", newline="", encoding="utf-8") as f_out,
        open(idx_csv, "w", newline="", encoding="utf-8") as f_idx,
    ):
        reader = csv.DictReader(f_in)
        writer_out = csv.writer(f_out)
        writer_idx = csv.writer(f_idx)

        # Seq2Neo immuno --mode multiple 要求确切两列 Pep,HLA（P 大写）
        writer_out.writerow(["Pep", "HLA"])
        # index：记录原始与转换后值，供 join 校验
        writer_idx.writerow(["row_idx", "peptide", "HLA_Allele", "HLA_seq2neo", "source"])

        for row in reader:
            if smoke_n > 0 and written >= smoke_n:
                break

            pep = row["peptide"].strip()
            hla_raw = row["HLA_Allele"].strip()
            source = row["source"].strip()

            if not pep or not hla_raw:
                skipped_empty += 1
                continue

            if not is_supported_len(pep):
                # 12mer / 越界肽长：跳过，不写入 Seq2Neo 输入（parse 回贴 NaN）
                skipped_len += 1
                continue

            hla = to_seq2neo_hla(hla_raw)
            writer_out.writerow([pep, hla])
            writer_idx.writerow([written, pep, hla_raw, hla, source])
            written += 1

    print(f"[prep_input] 写入 {out_csv.name}: {written} 行（含表头 = {written + 1} 行）")
    print(f"[prep_input] 跳过空行: {skipped_empty}")
    print(f"[prep_input] 跳过越界肽长（<{MIN_LEN} 或 >{MAX_LEN}，含 12mer）: {skipped_len}")
    print(f"[prep_input] index: {idx_csv}")
    print(f"[prep_input] 输入列名: Pep,HLA（P 大写；HLA 已转 HLA-A02:01 无星号格式）")
    print(f"[prep_input] Seq2Neo 调用示例（linux-only，需 netMHCpan + netCTLpan）:")
    print(f"  seq2neo immuno --mode multiple \\")
    print(f"    --inputfile {out_csv.resolve()} \\")
    print(f"    --outdir {out_dir.resolve() / f'seq2neo_out{suffix}'}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    script_dir = pathlib.Path(__file__).parent
    repo_root = script_dir.parents[2]  # QuantImmuBench/
    default_uniq = repo_root / "scripts" / "out" / "newtools" / "uniq_pep_hla.csv"
    default_out_dir = script_dir / "seq2neo_inputs"

    parser = argparse.ArgumentParser(
        description="Prepare Seq2Neo immuno (--mode multiple) input from uniq_pep_hla.csv"
    )
    parser.add_argument(
        "--uniq-pep-hla",
        default=str(default_uniq),
        help="uniq_pep_hla.csv 路径（peptide, HLA_Allele, source）",
    )
    parser.add_argument(
        "--out-dir",
        default=str(default_out_dir),
        help="输出目录（默认 seq2neo_inputs/）",
    )
    parser.add_argument(
        "--smoke",
        type=int,
        default=0,
        metavar="N",
        help="烟测模式：只输出前 N 条（过滤后），文件名加 _smoke（0 = 关闭）",
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
