"""
prep_icerfire.py  —  QuantImmuBench §Tier-2  ICERFIRE 1.0 输入准备
服务项目：quantimmu-bench §Tier-2 lever=部署ICERFIRE

功能：
  1. 读 master_backbone.csv
  2. 转换 HLA 格式：HLA-A*02:01 → HLA-A0201（去星号去冒号）
  3. HLA 白名单过滤（ICERFIRE_HLA_WHITELIST，65 个）：
       支持的行 → icerfire_input.csv（无表头 mut,wt,HLA）
       不支持的行 → icerfire_unsupported_bbidx.csv（parse 阶段填 NaN）
  4. 同时输出 icerfire_index.csv（行号→bb_idx），供 parse_icerfire.py 行序 join

行序约定：
  icerfire_input.csv 第 0 行（数据行，不含表头）对应 icerfire_index.csv 第 0 行（数据行，不含表头）。
  因输入无表头、输出无行标识，靠严格行序一一对应回贴 bb_idx。

WT 为空处理（TODO 待用户确认策略）：
  # TODO: WT_Subpeptide 为空时 ICERFIRE 是否支持仅突变肽模式？
  # TODO: 当前策略：跳过该行，icerfire_index.csv 中 output_row 标 -1，input_row 标 SKIPPED。
  默认跳过策略，不将空 WT 行写入输入文件（防止 ICERFIRE 报错）。

用法：
  python prep_icerfire.py [--backbone <csv>] [--out-dir <dir>]
  默认 backbone: scripts/out/master_backbone.csv（相对脚本向上3级）
  默认 out-dir:  scripts/out/newtools/icerfire_inputs/
"""

import argparse
import csv
import os
import pathlib


# ---------------------------------------------------------------------------
# HLA 白名单（ICERFIRE 1.0 支持的等位基因）
# ---------------------------------------------------------------------------
# 来源：ICERFIRE 1.0 官方 README（2026-06-26 核实）
# 格式：HLA-A0101（无星无冒号，与 hla_to_icerfire() 输出格式一致）
# 不在白名单的行：写入 icerfire_unsupported_bbidx.csv，parse 阶段填 NaN。
ICERFIRE_HLA_WHITELIST: frozenset = frozenset({
    # HLA-A（25 个）
    "HLA-A0101", "HLA-A0201", "HLA-A0202", "HLA-A0203", "HLA-A0205",
    "HLA-A0206", "HLA-A0210", "HLA-A0211", "HLA-A0224", "HLA-A0301",
    "HLA-A0302", "HLA-A1101", "HLA-A1102", "HLA-A2402", "HLA-A2501",
    "HLA-A2601", "HLA-A2902", "HLA-A3001", "HLA-A3002", "HLA-A3101",
    "HLA-A3301", "HLA-A6801", "HLA-A6802", "HLA-A6901", "HLA-A8001",
    # HLA-B（26 个）
    "HLA-B0702", "HLA-B0801", "HLA-B1302", "HLA-B1501", "HLA-B1801",
    "HLA-B2702", "HLA-B2705", "HLA-B3501", "HLA-B3503", "HLA-B3701",
    "HLA-B3704", "HLA-B3801", "HLA-B3901", "HLA-B3906", "HLA-B4001",
    "HLA-B4002", "HLA-B4102", "HLA-B4402", "HLA-B4403", "HLA-B4408",
    "HLA-B4901", "HLA-B5101", "HLA-B5201", "HLA-B5401", "HLA-B5601",
    "HLA-B5701",
    # HLA-C（14 个）
    "HLA-C0102", "HLA-C0303", "HLA-C0304", "HLA-C0401", "HLA-C0501",
    "HLA-C0602", "HLA-C0701", "HLA-C0702", "HLA-C0802", "HLA-C1202",
    "HLA-C1203", "HLA-C1402", "HLA-C1403", "HLA-C1502",
})  # 共 65 个


# ---------------------------------------------------------------------------
# HLA 格式转换
# ---------------------------------------------------------------------------

def hla_to_icerfire(h: str) -> str:
    """
    HLA-A*02:01 → HLA-A0201
    规则：去掉星号和冒号。
    示例：
      HLA-A*02:01 → HLA-A0201
      HLA-B*40:01 → HLA-B4001
      HLA-C*07:02 → HLA-C0702
    """
    return h.replace("*", "").replace(":", "")


# ---------------------------------------------------------------------------
# 主逻辑
# ---------------------------------------------------------------------------

def prep(backbone_path: str, out_dir: str) -> None:
    backbone_path = pathlib.Path(backbone_path)
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    input_csv_path = out_dir / "icerfire_input.csv"
    index_csv_path = out_dir / "icerfire_index.csv"
    unsupported_csv_path = out_dir / "icerfire_unsupported_bbidx.csv"

    skipped = 0      # WT/MT 为空跳过
    unsupported = 0  # HLA 不在白名单
    written = 0
    output_row = 0  # 写入 icerfire_input.csv 的行号（0-indexed，对应 ICERFIRE 输出行序）

    with (
        open(backbone_path, newline="", encoding="utf-8") as f_in,
        open(input_csv_path, "w", newline="", encoding="utf-8") as f_icerfire,
        open(index_csv_path, "w", newline="", encoding="utf-8") as f_idx,
        open(unsupported_csv_path, "w", newline="", encoding="utf-8") as f_unsup,
    ):
        reader = csv.DictReader(f_in)
        writer_icerfire = csv.writer(f_icerfire)
        writer_idx = csv.writer(f_idx)
        writer_unsup = csv.writer(f_unsup)

        # index 文件表头
        writer_idx.writerow(["output_row", "bb_idx", "MT_Subpeptide", "WT_Subpeptide", "HLA_icerfire"])
        # unsupported 文件表头
        writer_unsup.writerow(["bb_idx", "MT_Subpeptide", "WT_Subpeptide", "HLA_icerfire", "reason"])

        for row in reader:
            bb_idx = row["bb_idx"]
            mt_pep = row["MT_Subpeptide"].strip()
            wt_pep = row["WT_Subpeptide"].strip()
            hla_raw = row["HLA_Allele"].strip()

            # WT 为空：跳过，index 记 SKIPPED
            if not wt_pep:
                # TODO: 确认 ICERFIRE 是否接受空 WT；当前默认跳过
                writer_idx.writerow(["SKIPPED", bb_idx, mt_pep, "", hla_to_icerfire(hla_raw)])
                skipped += 1
                continue

            # MT 为空：同样跳过（防御性处理）
            if not mt_pep:
                writer_idx.writerow(["SKIPPED", bb_idx, "", wt_pep, hla_to_icerfire(hla_raw)])
                skipped += 1
                continue

            hla_icerfire = hla_to_icerfire(hla_raw)

            # HLA 白名单过滤：不支持的 HLA 写 unsupported CSV，parse 阶段填 NaN
            if hla_icerfire not in ICERFIRE_HLA_WHITELIST:
                writer_unsup.writerow([bb_idx, mt_pep, wt_pep, hla_icerfire, "HLA not in ICERFIRE whitelist"])
                unsupported += 1
                continue

            # 写 ICERFIRE 输入行（无表头，列序：mut,wt,HLA）
            writer_icerfire.writerow([mt_pep, wt_pep, hla_icerfire])

            # 写 index（output_row → bb_idx）
            writer_idx.writerow([output_row, bb_idx, mt_pep, wt_pep, hla_icerfire])

            output_row += 1
            written += 1

    print(f"[prep_icerfire] 写入 icerfire_input.csv: {written} 行")
    print(f"[prep_icerfire] 跳过（WT/MT 为空）: {skipped} 行")
    print(f"[prep_icerfire] 不支持 HLA（写 unsupported csv）: {unsupported} 行")
    print(f"[prep_icerfire] icerfire_index.csv: {out_dir / 'icerfire_index.csv'}")
    print(f"[prep_icerfire] icerfire_unsupported_bbidx.csv: {unsupported_csv_path}")
    print(f"[prep_icerfire] 输出目录: {out_dir}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    # 默认路径：本脚本在 HPC/deploy/icerfire/，master_backbone 在 scripts/out/
    script_dir = pathlib.Path(__file__).parent
    repo_root = script_dir.parents[2]  # YJ-Agent/project/meeting/QuantImmuBench/
    default_backbone = repo_root / "scripts" / "out" / "master_backbone.csv"
    default_out_dir = repo_root / "scripts" / "out" / "newtools" / "icerfire_inputs"

    parser = argparse.ArgumentParser(description="Prepare ICERFIRE 1.0 input from master_backbone.csv")
    parser.add_argument(
        "--backbone",
        default=str(default_backbone),
        help="master_backbone.csv 路径",
    )
    parser.add_argument(
        "--out-dir",
        default=str(default_out_dir),
        help="输出目录（默认 scripts/out/newtools/icerfire_inputs/）",
    )
    args = parser.parse_args()

    if not pathlib.Path(args.backbone).exists():
        raise FileNotFoundError(f"backbone 不存在: {args.backbone}")

    prep(args.backbone, args.out_dir)


if __name__ == "__main__":
    main()
