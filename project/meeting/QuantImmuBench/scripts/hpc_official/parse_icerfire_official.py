#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parse_icerfire_official.py
===============================================================================
服务：quantimmu-bench / Conductor 节点 tools_dtu (W1窗) / lever=6 DTU 工具补跑 out_official。

作用：读 HPC 拉回的 ICERFIRE_predictions.csv + icerfire_index.csv（prep_icerfire_official.py 产）
      → 按内容 (MT, WT, HLA) join 回贴 bb_idx → 产
      scripts/out_official/ICERFIRE_official.csv（列 bb_idx, MT_ICERFIRE）。
      1761 行对齐 backbone。仅有 WT 的 SNV 肽 + HLA 白名单内才有分，其余诚实 NaN。

ICERFIRE 是 DAI 类（突变肽相对野生肽的免疫原性），输出**一个**分代表 MT 的免疫原性
      → MT-only，只产 MT_ICERFIRE 列（无 WT 列）。

★ 方向（沿用旧 parse_icerfire.py 既定做法）★
      ICERFIRE 原始 **%Rank** ∈[0,100]，越低=越强免疫原（排名最前）。
      翻向：MT_ICERFIRE = 100 - %Rank → 越大越免疫原，与本 benchmark 一致。
      # TODO researcher 确认：predictions.csv 另有 'prediction' 原始分（可能越高越强），
        是否改用 prediction 更自然？当前照旧脚本用 100-%Rank。

Join 铁律：ICERFIRE 内部重排输出，**不靠行序**，按 (Peptide=MT, wild_type=WT, HLA_nostar)
      内容精确 join；一个 (MT,WT,HLA) 可对多 bb_idx（全赋同值）。缺即 NaN，绝不兜底。

输入：--predictions ICERFIRE_predictions.csv、--index icerfire_index.csv、
      --unsupported icerfire_unsupported_bbidx.csv、--backbone master_backbone_official.csv
输出：scripts/out_official/ICERFIRE_official.csv
跑法：python scripts/hpc_official/parse_icerfire_official.py（主线本地跑，我不跑）
依赖：标准库 + official_io.py。Windows：pathlib + utf-8。
DTU 许可红线：ICERFIRE binary 使用条款待 DTU 书面确认前勿对外发表。
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from official_io import load_backbone_bb_order, write_official_mt_only  # noqa: E402

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

TOOL = 'ICERFIRE'


def norm_hla(h: str) -> str:
    """去星：HLA-A*0201 → HLA-A0201。"""
    return h.replace('*', '')


def read_predictions_lookup(predictions_path: Path) -> dict:
    """读 ICERFIRE_predictions.csv → {(Peptide, wild_type, HLA_nostar): prediction_float}。
    用 `prediction` 列（RF 免疫原概率，越高越免疫原 = benchmark 标准方向，researcher 定论），
    不用 %Rank（百分位需翻向且相对参考集）。"""
    lookup = {}
    dups = 0
    with open(predictions_path, newline='', encoding='utf-8') as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            peptide = row['Peptide'].strip()
            wt = row['wild_type'].strip()
            hla_nostar = norm_hla(row['HLA'].strip())
            try:
                pred = float(row['prediction'])
            except (KeyError, ValueError) as e:
                raise ValueError(f'无法读取 prediction 列，行={row!r}: {e}') from e
            key = (peptide, wt, hla_nostar)
            if key in lookup:
                dups += 1
            lookup[key] = pred
    if dups:
        print(f'[parse_icerfire] ⚠️ predictions 有 {dups} 个重复 (Peptide,WT,HLA) key，取最后一次。',
              file=sys.stderr)
    return lookup


def read_index(index_path: Path) -> list:
    rows = []
    with open(index_path, newline='', encoding='utf-8') as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append(row)
    return rows


def read_unsupported(unsupported_path: Path) -> set:
    if not unsupported_path.exists():
        return set()
    bb_ids = set()
    with open(unsupported_path, newline='', encoding='utf-8') as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            bb_ids.add(row['bb_idx'].strip())
    return bb_ids


def main():
    script_dir = Path(__file__).resolve().parent
    ice_dir = script_dir.parent / 'out_official' / 'icerfire_inputs'
    default_pred = ice_dir / 'ICERFIRE_predictions.csv'
    default_index = ice_dir / 'icerfire_index.csv'
    default_unsup = ice_dir / 'icerfire_unsupported_bbidx.csv'
    default_backbone = script_dir.parent / 'out_official' / 'master_backbone_official.csv'
    default_out = script_dir.parent / 'out_official' / 'ICERFIRE_official.csv'

    ap = argparse.ArgumentParser(description='Parse ICERFIRE 1.0 → ICERFIRE_official.csv')
    ap.add_argument('--predictions', default=str(default_pred))
    ap.add_argument('--index', default=str(default_index))
    ap.add_argument('--unsupported-csv', default=str(default_unsup))
    ap.add_argument('--backbone', default=str(default_backbone))
    ap.add_argument('--out-csv', default=str(default_out))
    args = ap.parse_args()

    bb_order = load_backbone_bb_order(Path(args.backbone))

    index_path = Path(args.index)
    if not index_path.exists():
        raise FileNotFoundError(f'icerfire_index.csv 不存在: {index_path}（先跑 prep_icerfire_official.py）')
    index_rows = read_index(index_path)
    unsupported = read_unsupported(Path(args.unsupported_csv))

    pred_path = Path(args.predictions)
    if not pred_path.exists():
        print(f'[parse_icerfire] WARNING: predictions 不存在: {pred_path}（HPC 跑完拉回？）。'
              f'MT_ICERFIRE 全 NaN。', file=sys.stderr)
        lookup = {}
    else:
        lookup = read_predictions_lookup(pred_path)
        print(f'[parse_icerfire] predictions: {len(lookup)} 个唯一 (Peptide,WT,HLA) key', file=sys.stderr)

    mt_map = {}
    hit = 0
    miss = 0
    for row in index_rows:
        bb_idx = row['bb_idx'].strip()
        if bb_idx in unsupported:
            continue   # HLA 不在白名单 → NaN
        if row['output_row'] == 'SKIPPED':
            continue   # 无 WT → NaN
        mt = row['MT_Subpeptide'].strip()
        wt = row['WT_Subpeptide'].strip()
        hla = row['HLA_icerfire'].strip()   # 已去星格式 HLA-A0201
        key = (mt, wt, hla)
        if key in lookup:
            mt_map[bb_idx] = round(lookup[key], 6)   # prediction 已越大越免疫原，不翻向
            hit += 1
        else:
            miss += 1   # ICERFIRE 内部跳过 → NaN

    if miss:
        print(f'[parse_icerfire] ⚠️ {miss} 条 index 行在 predictions 查不到（ICERFIRE 内部跳过？）→ NaN。',
              file=sys.stderr)
    print(f'[parse_icerfire] hit={hit}  miss={miss}  unsupported={len(unsupported)}', file=sys.stderr)

    write_official_mt_only(Path(args.out_csv), TOOL, bb_order, mt_map)
    print('[parse_icerfire] 方向：MT_ICERFIRE = prediction（RF 免疫原概率，越大越免疫原，不翻向）。'
          'DTU 许可红线：未获书面同意前勿对外发表。', file=sys.stderr)


if __name__ == '__main__':
    main()
