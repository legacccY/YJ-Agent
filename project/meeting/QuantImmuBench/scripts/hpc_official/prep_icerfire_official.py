#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
prep_icerfire_official.py
===============================================================================
服务：quantimmu-bench / Conductor 节点 tools_dtu (W1窗) / lever=6 DTU 工具补跑 out_official。

作用：读 master_backbone_official.csv → 产 ICERFIRE 1.0 输入（无表头 csv: mut,wt,HLA）
      + index（输出行序 → bb_idx）+ unsupported（HLA 不在白名单 / 无 WT → parse 填 NaN）。

ICERFIRE 是 DAI 类外源性工具，**需 WT**（突变肽相对野生肽的免疫原性）：
      - 仅有 WT_Subpeptide 的行（SNV 肽）才写入输入；无 WT 行 → index 记 SKIPPED，
        其 bb_idx 走 unsupported/skipped 路径，parse 填 NaN（诚实部分覆盖）。
      - HLA 白名单沿用旧 prep_icerfire.py 的 ICERFIRE_HLA_WHITELIST（65 个，DTU 官方 README 核实）。

HLA 格式：HLA-A*02:01 → HLA-A0201（去 *，去 :）。

行序约定：icerfire_input.csv 第 k 个数据行（无表头）对应 icerfire_index.csv 中 output_row=k；
      但 ICERFIRE 内部会重排输出，故 parse 阶段**按内容 (mut,wt,HLA) join**，不靠行序
      （见 parse_icerfire_official.py）。index 同时保留 output_row 供审计。

方向：方向在 parse 里统一（ICERFIRE 原始 %Rank 越低越强 → parse 翻为 100-%Rank 越大越免疫原）。

输入：scripts/out_official/master_backbone_official.csv（只读）
输出：scripts/out_official/icerfire_inputs/{icerfire_input.csv, icerfire_index.csv,
      icerfire_unsupported_bbidx.csv}

跑法（主线本地跑，我不跑）：
      python scripts/hpc_official/prep_icerfire_official.py
      # 上传 icerfire_input.csv 到 HPC 跑 run_icerfire.sh → 拉回 ICERFIRE_predictions.csv

依赖：标准库（csv, pathlib）。Windows：pathlib + utf-8 + sys.stdout.reconfigure。
"""

import argparse
import csv
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass


# ---------------------------------------------------------------------------
# HLA 白名单（ICERFIRE 1.0 支持的等位，65 个；DTU 官方 README 2026-06-26 核实）
# 格式：HLA-A0101（无星无冒号，与 hla_to_icerfire() 输出一致）。沿用旧 prep_icerfire.py。
# ---------------------------------------------------------------------------
ICERFIRE_HLA_WHITELIST: frozenset = frozenset({
    # HLA-A（25）
    "HLA-A0101", "HLA-A0201", "HLA-A0202", "HLA-A0203", "HLA-A0205",
    "HLA-A0206", "HLA-A0210", "HLA-A0211", "HLA-A0224", "HLA-A0301",
    "HLA-A0302", "HLA-A1101", "HLA-A1102", "HLA-A2402", "HLA-A2501",
    "HLA-A2601", "HLA-A2902", "HLA-A3001", "HLA-A3002", "HLA-A3101",
    "HLA-A3301", "HLA-A6801", "HLA-A6802", "HLA-A6901", "HLA-A8001",
    # HLA-B（26）
    "HLA-B0702", "HLA-B0801", "HLA-B1302", "HLA-B1501", "HLA-B1801",
    "HLA-B2702", "HLA-B2705", "HLA-B3501", "HLA-B3503", "HLA-B3701",
    "HLA-B3704", "HLA-B3801", "HLA-B3901", "HLA-B3906", "HLA-B4001",
    "HLA-B4002", "HLA-B4102", "HLA-B4402", "HLA-B4403", "HLA-B4408",
    "HLA-B4901", "HLA-B5101", "HLA-B5201", "HLA-B5401", "HLA-B5601",
    "HLA-B5701",
    # HLA-C（14）
    "HLA-C0102", "HLA-C0303", "HLA-C0304", "HLA-C0401", "HLA-C0501",
    "HLA-C0602", "HLA-C0701", "HLA-C0702", "HLA-C0802", "HLA-C1202",
    "HLA-C1203", "HLA-C1402", "HLA-C1403", "HLA-C1502",
})  # 共 65


def hla_to_icerfire(h: str) -> str:
    """HLA-A*02:01 → HLA-A0201（去 *，去 :）。"""
    return h.replace('*', '').replace(':', '')


def prep(backbone_path: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    input_csv_path = out_dir / 'icerfire_input.csv'
    index_csv_path = out_dir / 'icerfire_index.csv'
    unsupported_csv_path = out_dir / 'icerfire_unsupported_bbidx.csv'

    skipped = 0       # WT/MT 为空跳过
    unsupported = 0   # HLA 不在白名单
    written = 0
    output_row = 0

    with (
        open(backbone_path, newline='', encoding='utf-8') as f_in,
        open(input_csv_path, 'w', newline='', encoding='utf-8') as f_ice,
        open(index_csv_path, 'w', newline='', encoding='utf-8') as f_idx,
        open(unsupported_csv_path, 'w', newline='', encoding='utf-8') as f_unsup,
    ):
        reader = csv.DictReader(f_in)
        writer_ice = csv.writer(f_ice)
        writer_idx = csv.writer(f_idx)
        writer_unsup = csv.writer(f_unsup)

        writer_idx.writerow(['output_row', 'bb_idx', 'MT_Subpeptide', 'WT_Subpeptide', 'HLA_icerfire'])
        writer_unsup.writerow(['bb_idx', 'MT_Subpeptide', 'WT_Subpeptide', 'HLA_icerfire', 'reason'])

        for row in reader:
            bb_idx  = row['bb_idx'].strip()
            mt_pep  = row['MT_Subpeptide'].strip()
            wt_pep  = row['WT_Subpeptide'].strip()
            hla_raw = row['HLA_Allele'].strip()
            hla_ice = hla_to_icerfire(hla_raw)

            # 无 WT（非 SNV 肽）：ICERFIRE 需 WT → SKIPPED，parse 填 NaN
            if not wt_pep:
                writer_idx.writerow(['SKIPPED', bb_idx, mt_pep, '', hla_ice])
                skipped += 1
                continue
            if not mt_pep:
                writer_idx.writerow(['SKIPPED', bb_idx, '', wt_pep, hla_ice])
                skipped += 1
                continue

            # HLA 白名单过滤
            if hla_ice not in ICERFIRE_HLA_WHITELIST:
                writer_unsup.writerow([bb_idx, mt_pep, wt_pep, hla_ice, 'HLA not in ICERFIRE whitelist'])
                unsupported += 1
                continue

            writer_ice.writerow([mt_pep, wt_pep, hla_ice])
            writer_idx.writerow([output_row, bb_idx, mt_pep, wt_pep, hla_ice])
            output_row += 1
            written += 1

    print(f'[prep_icerfire] icerfire_input.csv 写入: {written} 行（有 WT + HLA 白名单内）')
    print(f'[prep_icerfire] 跳过（无 WT/MT）: {skipped} 行 → parse 填 NaN')
    print(f'[prep_icerfire] 不支持 HLA: {unsupported} 行 → parse 填 NaN')
    print(f'[prep_icerfire] 输出目录: {out_dir}')


def main():
    script_dir = Path(__file__).resolve().parent              # scripts/hpc_official
    default_backbone = script_dir.parent / 'out_official' / 'master_backbone_official.csv'
    default_out = script_dir.parent / 'out_official' / 'icerfire_inputs'

    parser = argparse.ArgumentParser(
        description='Prepare ICERFIRE 1.0 input from master_backbone_official.csv'
    )
    parser.add_argument('--backbone', default=str(default_backbone),
                        help='master_backbone_official.csv 路径')
    parser.add_argument('--out-dir', default=str(default_out),
                        help='输出目录（default: %(default)s）')
    args = parser.parse_args()

    backbone_path = Path(args.backbone)
    if not backbone_path.exists():
        raise FileNotFoundError(f'backbone 不存在: {backbone_path}')

    prep(backbone_path, Path(args.out_dir))


if __name__ == '__main__':
    main()
