#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
official_io.py
===============================================================================
服务：quantimmu-bench / Conductor 节点 tools_dtu (W1窗) / lever=6。

6 个 parse_*_official.py 共用的输出/校验 helper：
  - load_backbone_bb_order(): 读 master_backbone_official.csv，返回 bb_idx 文件顺序列表
    （真源顺序，不假设连续 0..N）。
  - write_official_mt_wt(): 写 `bb_idx, MT_<Tool>, WT_<Tool>` 三列 CSV，按 backbone 顺序
    逐 bb_idx 一行；缺分留空（NaN）。**硬校验行数 = backbone 行数，不足/超 sys.exit(1)。**
    打印 MT/WT 填充率（notna/total）+ distinct 等位覆盖数。
  - write_official_mt_only(): 写 `bb_idx, MT_<Tool>` 两列（MT-only 工具：ICERFIRE/T-SCAPE）。

输出 NaN 约定：留空字符串（与范本 PRIME_official.csv / IEDB_Calis_official.csv 一致）。
Windows：utf-8 explicit。
"""

import csv
import sys
from pathlib import Path


def load_backbone_bb_order(backbone_path: Path) -> list:
    """读 backbone，返回 bb_idx（str）的文件顺序列表（真源顺序）。"""
    backbone_path = Path(backbone_path)
    if not backbone_path.exists():
        raise FileNotFoundError(f'master_backbone_official.csv 不存在: {backbone_path}')
    order = []
    with open(backbone_path, encoding='utf-8', newline='') as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            order.append(row['bb_idx'].strip())
    return order


def _fmt(v):
    """float/None/'' → 输出字符串；NaN/None → 空。"""
    if v is None or v == '':
        return ''
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if f != f:   # NaN
        return ''
    return repr(f) if isinstance(v, float) else str(v)


def write_official_mt_wt(out_path: Path, tool: str, bb_order: list,
                         mt_map: dict, wt_map: dict,
                         n_distinct_alleles_mt: int = -1) -> None:
    """
    写 bb_idx, MT_<tool>, WT_<tool>，逐 bb_idx 对齐 backbone。
    mt_map / wt_map: {bb_idx_str: score(float)}；缺即留空。
    硬校验：输出数据行数 == len(bb_order)，否则 sys.exit(1)。
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    mt_col = f'MT_{tool}'
    wt_col = f'WT_{tool}'

    n = len(bb_order)
    n_mt = 0
    n_wt = 0
    with open(out_path, 'w', encoding='utf-8', newline='') as fh:
        writer = csv.writer(fh)
        writer.writerow(['bb_idx', mt_col, wt_col])
        for bb in bb_order:
            mv = mt_map.get(bb)
            wv = wt_map.get(bb)
            mt_s = _fmt(mv)
            wt_s = _fmt(wv)
            if mt_s != '':
                n_mt += 1
            if wt_s != '':
                n_wt += 1
            writer.writerow([bb, mt_s, wt_s])

    # 硬校验：复读行数
    with open(out_path, encoding='utf-8', newline='') as fh:
        written = sum(1 for _ in csv.reader(fh)) - 1   # 去表头
    if written != n:
        print(f'[official_io][FATAL] {tool}: 输出 {written} 数据行 != backbone {n} 行', file=sys.stderr)
        sys.exit(1)

    print(f'[OUT] {out_path}', file=sys.stderr)
    print(f'[OUT] {tool}: {written} 行（对齐 backbone {n}）✅  '
          f'{mt_col} 填充={n_mt}/{n}（{100*n_mt/n:.1f}%）  '
          f'{wt_col} 填充={n_wt}/{n}（{100*n_wt/n:.1f}%）', file=sys.stderr)
    if n_distinct_alleles_mt >= 0:
        print(f'[OUT] {tool}: MT 实际覆盖 {n_distinct_alleles_mt} 个 distinct 等位', file=sys.stderr)


def write_official_mt_only(out_path: Path, tool: str, bb_order: list,
                           mt_map: dict, n_distinct_alleles_mt: int = -1) -> None:
    """写 bb_idx, MT_<tool>（MT-only 工具）。硬校验行数 == len(bb_order)。"""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    mt_col = f'MT_{tool}'

    n = len(bb_order)
    n_mt = 0
    with open(out_path, 'w', encoding='utf-8', newline='') as fh:
        writer = csv.writer(fh)
        writer.writerow(['bb_idx', mt_col])
        for bb in bb_order:
            mt_s = _fmt(mt_map.get(bb))
            if mt_s != '':
                n_mt += 1
            writer.writerow([bb, mt_s])

    with open(out_path, encoding='utf-8', newline='') as fh:
        written = sum(1 for _ in csv.reader(fh)) - 1
    if written != n:
        print(f'[official_io][FATAL] {tool}: 输出 {written} 数据行 != backbone {n} 行', file=sys.stderr)
        sys.exit(1)

    print(f'[OUT] {out_path}', file=sys.stderr)
    print(f'[OUT] {tool}: {written} 行（对齐 backbone {n}）✅  '
          f'{mt_col} 填充={n_mt}/{n}（{100*n_mt/n:.1f}%）', file=sys.stderr)
    if n_distinct_alleles_mt >= 0:
        print(f'[OUT] {tool}: MT 实际覆盖 {n_distinct_alleles_mt} 个 distinct 等位', file=sys.stderr)
