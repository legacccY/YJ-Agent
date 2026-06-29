#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_add_netmhcpan_el.py — QuantImmuBench 工具补齐（合 NetMHCpan-EL presentation 列）
==================================================================
服务: quantimmu-bench / Conductor 节点 tools_present
       lever = 给 benchmark 加 netMHCpan-EL（呈递/presentation）列

⚠️ 链序由 merge 节点决定（重要，勿硬钉）:
  本 patch 由 merge 节点按 w4 各列顺序统一应用。--base / --out 由 merge 节点
  在命令行决定真正的链序（21→22tools 只是默认值，不代表最终位置）。本脚本
  只负责「在给定 base 上贴 NetMHCpan-EL 两列、写出 out」，不假设自己排第几。

设计（仿 scripts/patch_add_icerfire_nettepi.py 的 bb_idx 主键 join + DTU sidecar）:
  - base = merged_all_tools_NNtools.xlsx 活真源（默认 21tools，34247 行 × 65 列，
    已 HLA-FIX）。主线已核：base **有 bb_idx 列**（含 MT_Subpeptide/WT_Subpeptide/
    HLA_Allele）→ 走最稳的 (bb_idx, is_MT) → score join，无须 HLA 字符串转换。
  - score 源 = 交付1产出 scripts/out/newtools/netmhcpan_el_DS1DS2_scores.csv
    （列 bb_idx, netmhcpan_el_ELscore, netmhcpan_el_Rnk_EL, netmhcpan_el_score,
      is_MT, pending_DTU_consent）。
    按 is_MT 拆两 map：is_MT=True→MT_netMHCpan_EL，is_MT=False→WT_netMHCpan_EL，
    各 map 以 str(bb_idx) 为键（防 base int / csv str 类型不一致）。

================== 方向说明（重要，勿删）==================
  netmhcpan_el_score = EL-score（0-1，越高 = 越可能被呈递 = 越可能是真表位），
  本就与 benchmark 其他 MT_<tool>「越大越免疫原」约定一致 → **不翻向**，直接用。

================== HLA-FIX ==================
  按 bb_idx 主键查表，bb_idx 唯一映射到 base 自身已订正 HLA 的行 → P101/P102
  天然对齐、不置 NaN（同 icerfire/nettepi 的 bb_idx 对齐处理）。

================== 许可（DTU 红线，与 mhcnuggets/transhla 不同）==================
  NetMHCpan = DTU（丹麦科技大学）工具，许可须书面同意才可发表本工具的 benchmark
  数字（同 -BA 版 / ICERFIRE / NetTepi）。
  → 本脚本 **写** PENDING_DTU sidecar（追加 'NetMHCpan_EL'），score csv 各行
    pending_DTU_consent=True。拿到 DTU 书面同意前不得对外发布本列数字。

================== 输出 ==================
  默认 scripts/out/merged_all_tools_22tools.xlsx（真正文件名由 merge 节点 --out 定）
    新增列: MT_netMHCpan_EL, WT_netMHCpan_EL
  追加 scripts/out/newtools/PENDING_DTU_tools.txt: 'NetMHCpan_EL'（去重）

================== 跑法（主线串行，本脚本只写不跑；命中率/行数由主线跑后核）==================
  1) python HPC/deploy/netmhcpan_ba/parse_netmhcpan_el.py
       → scripts/out/newtools/netmhcpan_el_DS1DS2_scores.csv
  2) python scripts/patch_add_netmhcpan_el.py [--base ... --out ...]
       默认 21tools→22tools；merge 节点会以正确链序传 --base/--out。

依赖: pandas, openpyxl
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent          # scripts/
ROOT = HERE.parent                               # QuantImmuBench/

EXPECTED_ROWS = 34247

DEFAULT_BASE = ROOT / 'scripts' / 'out' / 'merged_all_tools_21tools.xlsx'
DEFAULT_OUT = ROOT / 'scripts' / 'out' / 'merged_all_tools_22tools.xlsx'
SCORE_CSV = ROOT / 'scripts' / 'out' / 'newtools' / 'netmhcpan_el_DS1DS2_scores.csv'
PENDING_TXT = ROOT / 'scripts' / 'out' / 'newtools' / 'PENDING_DTU_tools.txt'

SCORE_COL = 'netmhcpan_el_score'   # 统一方向列（=EL-score，越高越强）


def load_score_maps(csv_path: Path):
    """
    读 netmhcpan_el_DS1DS2_scores.csv，按 is_MT 拆两 map：
      mt_map[str(bb_idx)] = score   (is_MT=True)
      wt_map[str(bb_idx)] = score   (is_MT=False)
    键统一转 str(bb_idx) 防 base(int)/csv(str) 类型不一致。
    """
    df = pd.read_csv(csv_path, encoding='utf-8')
    df.columns = [c.strip() for c in df.columns]

    for c in ('bb_idx', 'is_MT', SCORE_COL):
        if c not in df.columns:
            print(f'[ERR] {csv_path.name} 缺列 {c}（实有: {list(df.columns)}）',
                  file=sys.stderr)
            sys.exit(1)

    df['bb_idx'] = df['bb_idx'].astype(str).str.strip()
    df['is_MT'] = df['is_MT'].astype(str).str.strip()
    df[SCORE_COL] = pd.to_numeric(df[SCORE_COL], errors='coerce')
    df = df[(df['bb_idx'] != '') & df[SCORE_COL].notna()]

    mt = df[df['is_MT'] == 'True']
    wt = df[df['is_MT'] == 'False']
    # 同 bb_idx 去重（最后一条覆盖），防一对多外扩
    mt_map = dict(zip(mt['bb_idx'], mt[SCORE_COL].astype(float)))
    wt_map = dict(zip(wt['bb_idx'], wt[SCORE_COL].astype(float)))

    print(f'[INFO] score 源读入: MT={len(mt_map)} 键 / WT={len(wt_map)} 键'
          f'（方向 EL-score 越高越强，不翻向）', file=sys.stderr)
    return mt_map, wt_map


def map_col(m: pd.DataFrame, score_map: dict, new_col: str) -> pd.DataFrame:
    """按 str(m['bb_idx']) 元素级查 score_map → 写 new_col（map 保证行数不变）。"""
    keys = m['bb_idx'].astype(str).str.strip()
    vals = [score_map.get(k, np.nan) for k in keys.tolist()]
    m[new_col] = pd.to_numeric(pd.Series(vals, index=m.index), errors='coerce')
    fill = int(m[new_col].notna().sum())
    pct = fill / len(m) * 100 if len(m) else 0.0
    flag = '  [WARN<50%]' if pct < 50 else ''
    print(f'[{new_col}] 填充率={fill}/{len(m)} ({pct:.1f}%){flag}', file=sys.stderr)
    return m


def append_pending(tools):
    """追加 DTU pending 工具名到 sidecar，去重保留原有顺序（仿 icerfire/nettepi patch）。"""
    existing = []
    if PENDING_TXT.exists():
        existing = [ln.strip() for ln in
                    PENDING_TXT.read_text(encoding='utf-8').splitlines() if ln.strip()]
    merged = list(existing)
    for t in tools:
        if t not in merged:
            merged.append(t)
    PENDING_TXT.parent.mkdir(parents=True, exist_ok=True)
    PENDING_TXT.write_text('\n'.join(merged) + '\n', encoding='utf-8')
    print(f'[INFO] DTU pending sidecar -> {PENDING_TXT}', file=sys.stderr)
    print(f'       工具列表: {merged}', file=sys.stderr)


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    parser = argparse.ArgumentParser(
        description='Patch NetMHCpan-EL (presentation) 两列进大表 (bb_idx,is_MT join)'
    )
    parser.add_argument('--base', default=str(DEFAULT_BASE),
                        help='base xlsx（链序由 merge 节点决定，默认 %(default)s）')
    parser.add_argument('--out', default=str(DEFAULT_OUT),
                        help='输出 xlsx（链序由 merge 节点决定，默认 %(default)s）')
    parser.add_argument('--score-csv', default=str(SCORE_CSV),
                        help='netmhcpan_el_DS1DS2_scores.csv (默认 %(default)s)')
    args = parser.parse_args()

    base = Path(args.base)
    out = Path(args.out)
    score_csv = Path(args.score_csv)

    if not base.exists():
        print(f'[ERR] base 不存在: {base}', file=sys.stderr); sys.exit(1)
    if not score_csv.exists():
        print(f'[ERR] score csv 不存在: {score_csv}', file=sys.stderr); sys.exit(1)

    m = pd.read_excel(base)
    print(f'[INFO] base 读入: {len(m)} 行 × {len(m.columns)} 列  ({base.name})',
          file=sys.stderr)

    if 'bb_idx' not in m.columns:
        print('[ERR] base 缺 bb_idx 列，无法 (bb_idx,is_MT) join', file=sys.stderr)
        sys.exit(1)
    if len(m) != EXPECTED_ROWS:
        print(f'[ERR] base 行数 {len(m)} ≠ 预期 {EXPECTED_ROWS}', file=sys.stderr)
        sys.exit(1)
    for col in ('MT_netMHCpan_EL', 'WT_netMHCpan_EL'):
        if col in m.columns:
            print(f'[ERR] base 已含 {col} 列，疑重复 patch，中止', file=sys.stderr)
            sys.exit(1)

    mt_map, wt_map = load_score_maps(score_csv)

    m = map_col(m, mt_map, 'MT_netMHCpan_EL')
    m = map_col(m, wt_map, 'WT_netMHCpan_EL')

    if len(m) != EXPECTED_ROWS:
        print(f'[ERR] 合并后行数 {len(m)} ≠ {EXPECTED_ROWS}！中止写出', file=sys.stderr)
        sys.exit(1)

    # ── HLA-FIX 报告（bb_idx 对齐，天然不置 NaN）──────────────────────────────────
    if 'Patient_ID' in m.columns:
        pid = m['Patient_ID'].astype(str)
        pp = pid.str.contains('101') | pid.str.contains('102')
        n_pp = int(pp.sum())
        mt_pp = int(m.loc[pp, 'MT_netMHCpan_EL'].notna().sum())
        wt_pp = int(m.loc[pp, 'WT_netMHCpan_EL'].notna().sum())
        print(f'[HLA-FIX] P101/P102 行={n_pp}（按 bb_idx 对齐，不置 NaN）；'
              f'MT 非空={mt_pp}，WT 非空={wt_pp}', file=sys.stderr)

    # ── DTU sidecar（NetMHCpan = DTU，pending_DTU_consent）─────────────────────────
    print('[LICENSE] NetMHCpan = DTU 工具，DTU 许可红线：拿到书面同意前不得发表本列数字。',
          file=sys.stderr)
    append_pending(['NetMHCpan_EL'])

    out.parent.mkdir(parents=True, exist_ok=True)
    m.to_excel(out, index=False, engine='openpyxl')
    print(f'\n[DONE] 输出: {out}\n[DONE] {len(m)} 行 × {len(m.columns)} 列'
          f'（新增 MT_netMHCpan_EL, WT_netMHCpan_EL）', file=sys.stderr)


if __name__ == '__main__':
    main()
