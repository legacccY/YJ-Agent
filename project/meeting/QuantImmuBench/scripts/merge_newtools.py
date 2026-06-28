#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
merge_newtools.py — QuantImmuBench 新工具分数自动合并到大表
=========================================================
服务: quantimmu-bench / lever=扩张工具后 benchmark 表重建

输入:
  --base           基表 xlsx (默认 scripts/out/merged_all_tools_9tools.xlsx)
                   必须含 bb_idx 列 (主键)，预期 34247 行
  --newtools-dir   新工具分数目录 (默认 scripts/out/newtools)
                   自动 glob 扫描 *_DS1DS2_scores.csv
                   工具名从文件名提取: <tool>_DS1DS2_scores.csv -> <tool>
  --out            输出 xlsx 路径 (缺省则自动命名
                   scripts/out/merged_all_tools_<NN>tools.xlsx，NN=9+新工具数)

每个 *_DS1DS2_scores.csv 列约定:
  bb_idx             主键 (与基表 bb_idx 对应)
  <tool>_score       工具分数 (越高越免疫原，方向已统一)
  is_MT  (可选)      True=MT行 / False=WT行
                     有此列: True→MT_<tool>, False→WT_<tool>
                     无此列: 全行贴 MT_<tool>
  pending_DTU_consent (可选)  True=该工具数据使用待 DTU 授权

输出:
  scripts/out/merged_all_tools_<NN>tools.xlsx   合并大表
  scripts/out/newtools/PENDING_DTU_tools.txt     (若有 DTU pending 工具)

校验:
  - 合并后行数必须 == 34247，否则报错中止
  - 每新工具打印 MT_/WT_ 列填充率；填充率 < 50% 警告
  - 若 newtools 下暂无 score CSV → 优雅退出，复制基表

跑法:
  python scripts/merge_newtools.py
  python scripts/merge_newtools.py --base scripts/out/merged_all_tools_9tools.xlsx
  python scripts/merge_newtools.py --newtools-dir scripts/out/newtools
  python scripts/merge_newtools.py --out scripts/out/merged_all_tools_11tools.xlsx

依赖:
  pandas, openpyxl
"""

import argparse
import glob
import os
import re
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

EXPECTED_ROWS = 34247
BASE_N_TOOLS = 9


def extract_tool_name(csv_path: str) -> str:
    """
    从文件名提取工具名。
    例: netmhcpan_ba_DS1DS2_scores.csv -> netmhcpan_ba
         IcerFire_DS1DS2_scores.csv    -> IcerFire
    """
    basename = os.path.basename(csv_path)
    m = re.match(r'^(.+?)_DS1DS2_scores\.csv$', basename, re.IGNORECASE)
    if m:
        return m.group(1)
    # 兼容 <tool>_scores.csv (如 tscape_scores.csv)
    m = re.match(r'^(.+?)_scores\.csv$', basename, re.IGNORECASE)
    if m:
        return m.group(1)
    return basename.rsplit('.', 1)[0]


def _is_true(val) -> bool:
    """宽松解析 True/False/1/0/yes/no 字符串 → bool。"""
    return str(val).strip().lower() in ('true', '1', 'yes')


def merge_one_tool(
    result: pd.DataFrame,
    csv_path: str,
    tool_name: str,
    pending_tools: list,
) -> pd.DataFrame:
    """
    读取单个工具 score CSV，按 bb_idx left-join 到 result。
    返回新 result（含 MT_<tool> 及可选 WT_<tool> 列）。
    result.bb_idx 必须为列（非 index）。
    """
    try:
        sdf = pd.read_csv(csv_path, encoding='utf-8')
    except Exception as exc:
        print(f'[WARN] 读取 {csv_path} 失败: {exc}，跳过此工具', file=sys.stderr)
        return result

    sdf.columns = [c.strip() for c in sdf.columns]

    # ── 直接 schema 分支: CSV 已含 MT_*/WT_* 工具列 + 自然键 (B 窗约定) ─────────
    # 例: CNNeo/IEDB_Calis/MHCflurry 产 (Dataset,Peptide_ID,HLA_Allele,MT_Subpeptide)
    #     + MT_<Tool>/WT_<Tool> 列, 34247 行对齐. 按自然键 merge (基表此键唯一).
    NAT_KEY = ['Dataset', 'Peptide_ID', 'HLA_Allele', 'MT_Subpeptide']
    SEQ_COLS = {'MT_Subpeptide', 'WT_Subpeptide', 'MT_FullPeptide', 'WT_FullPeptide'}
    direct_cols = [c for c in sdf.columns
                   if (c.startswith('MT_') or c.startswith('WT_')) and c not in SEQ_COLS]
    has_nat_key = all(k in sdf.columns for k in NAT_KEY) and all(k in result.columns for k in NAT_KEY)
    # 自然键缺失但有 bb_idx → 用 bb_idx join (如 T-SCAPE: bb_idx + MT_TSCAPE)
    join_key = NAT_KEY if has_nat_key else (['bb_idx'] if ('bb_idx' in sdf.columns and 'bb_idx' in result.columns) else None)
    if direct_cols and join_key:
        if 'pending_DTU_consent' in sdf.columns and sdf['pending_DTU_consent'].apply(_is_true).any():
            pending_tools.append(tool_name)
            print(f'[INFO] {tool_name}: 标记 pending_DTU_consent', file=sys.stderr)
        for c in direct_cols:
            sdf[c] = pd.to_numeric(sdf[c], errors='coerce')
        join_df = sdf[join_key + direct_cols].drop_duplicates(join_key)
        before = len(result)
        result = result.merge(join_df, on=join_key, how='left')
        if len(result) != before:
            print(f'[ERR] {tool_name}: 自然键 merge 改变行数 {before}->{len(result)}，中止', file=sys.stderr)
            sys.exit(1)
        for c in direct_cols:
            fill = result[c].notna().sum()
            pct = fill / before * 100 if before else 0.0
            flag = '  [WARN<50%]' if pct < 50 else ''
            print(f'[{tool_name}] {c} 填充率={fill}/{before} ({pct:.1f}%){flag}', file=sys.stderr)
        print(f'[INFO] {tool_name}: 直接 schema, 新增列 {direct_cols}', file=sys.stderr)
        return result

    # ── 必要列检查 (长 schema: bb_idx + <tool>_score + is_MT) ──────────────────
    if 'bb_idx' not in sdf.columns:
        print(f'[WARN] {csv_path} 缺 bb_idx 列且非直接 schema，跳过', file=sys.stderr)
        return result

    # 找分数列：优先 <tool>_score，次选任意 *_score
    score_col = f'{tool_name}_score'
    if score_col not in sdf.columns:
        candidates = [c for c in sdf.columns if c.endswith('_score') and c != 'bb_idx']
        if not candidates:
            print(
                f'[WARN] {csv_path} 未找到 {tool_name}_score 或任何 *_score 列，跳过',
                file=sys.stderr,
            )
            return result
        score_col = candidates[0]
        print(
            f'[INFO] {tool_name}: 分数列用 {score_col!r} (非预期 {tool_name}_score)',
            file=sys.stderr,
        )

    # ── DTU pending 检查 ──────────────────────────────────────────────────────
    if 'pending_DTU_consent' in sdf.columns:
        n_pending = sdf['pending_DTU_consent'].apply(_is_true).sum()
        if n_pending > 0:
            pending_tools.append(tool_name)
            print(
                f'[INFO] {tool_name}: {n_pending} 行标记 pending_DTU_consent=True',
                file=sys.stderr,
            )

    # ── 强制分数列为数值 ──────────────────────────────────────────────────────
    sdf[score_col] = pd.to_numeric(sdf[score_col], errors='coerce')

    mt_col_name = f'MT_{tool_name}'
    wt_col_name = f'WT_{tool_name}'

    has_is_mt = 'is_MT' in sdf.columns

    if has_is_mt:
        # is_MT 存在 → 分 MT/WT 两侧
        is_mt_mask = sdf['is_MT'].apply(_is_true)

        mt_df = (
            sdf[is_mt_mask][['bb_idx', score_col]]
            .groupby('bb_idx')[score_col]
            .mean()
            .rename(mt_col_name)
            .reset_index()
        )
        wt_df = (
            sdf[~is_mt_mask][['bb_idx', score_col]]
            .groupby('bb_idx')[score_col]
            .mean()
            .rename(wt_col_name)
            .reset_index()
        )

        result = result.merge(mt_df, on='bb_idx', how='left')
        result = result.merge(wt_df, on='bb_idx', how='left')

    else:
        # 无 is_MT → 全行贴 MT 侧
        mt_df = (
            sdf[['bb_idx', score_col]]
            .groupby('bb_idx')[score_col]
            .mean()
            .rename(mt_col_name)
            .reset_index()
        )
        result = result.merge(mt_df, on='bb_idx', how='left')
        print(
            f'[INFO] {tool_name}: 无 is_MT 列，全行贴 {mt_col_name}',
            file=sys.stderr,
        )

    # ── 填充率报告 ────────────────────────────────────────────────────────────
    n_total = len(result)
    mt_fill = result[mt_col_name].notna().sum() if mt_col_name in result.columns else 0
    mt_pct = mt_fill / n_total * 100 if n_total else 0.0
    print(
        f'[{tool_name}] MT 填充率={mt_fill}/{n_total} ({mt_pct:.1f}%)',
        file=sys.stderr,
    )
    if has_is_mt:
        wt_fill = result[wt_col_name].notna().sum() if wt_col_name in result.columns else 0
        wt_pct = wt_fill / n_total * 100 if n_total else 0.0
        print(
            f'[{tool_name}] WT 填充率={wt_fill}/{n_total} ({wt_pct:.1f}%)',
            file=sys.stderr,
        )
    if mt_pct < 50.0:
        print(
            f'[WARN] {tool_name}: MT 填充率低于 50%（{mt_pct:.1f}%），请核实输入 CSV',
            file=sys.stderr,
        )

    return result


def parse_args():
    default_base = str(ROOT / 'scripts' / 'out' / 'merged_all_tools_9tools.xlsx')
    default_newtools = str(ROOT / 'scripts' / 'out' / 'newtools')

    parser = argparse.ArgumentParser(
        description='QuantImmuBench: 新工具分数自动合并到大表'
    )
    parser.add_argument(
        '--base', default=default_base,
        help='基表 xlsx 路径 (默认 merged_all_tools_9tools.xlsx)',
    )
    parser.add_argument(
        '--newtools-dir', default=default_newtools,
        help='新工具分数目录，glob *_DS1DS2_scores.csv (默认 scripts/out/newtools)',
    )
    parser.add_argument(
        '--out', default=None,
        help='输出 xlsx 路径（缺省自动命名 merged_all_tools_<NN>tools.xlsx）',
    )
    return parser.parse_args()


def main():
    args = parse_args()
    base_path = Path(args.base).resolve()
    newtools_dir = Path(args.newtools_dir).resolve()

    print(f'[INFO] 基表:         {base_path}', file=sys.stderr)
    print(f'[INFO] 新工具目录:   {newtools_dir}', file=sys.stderr)

    # ── 读基表 ────────────────────────────────────────────────────────────────
    if not base_path.exists():
        print(f'[ERR] 基表不存在: {base_path}', file=sys.stderr)
        sys.exit(1)

    base_df = pd.read_excel(base_path)
    print(
        f'[INFO] 基表读入: {len(base_df)} 行 × {len(base_df.columns)} 列',
        file=sys.stderr,
    )

    if 'bb_idx' not in base_df.columns:
        print('[ERR] 基表缺 bb_idx 列，无法主键 join', file=sys.stderr)
        sys.exit(1)

    if len(base_df) != EXPECTED_ROWS:
        print(
            f'[WARN] 基表行数 {len(base_df)} ≠ 预期 {EXPECTED_ROWS}，继续但请核查',
            file=sys.stderr,
        )

    # ── 扫描新工具 CSV ────────────────────────────────────────────────────────
    # 扫 *_DS1DS2_scores.csv (标准) + *_scores.csv (如 tscape_scores.csv); 排除 smoke
    _cands = set(glob.glob(str(newtools_dir / '*_DS1DS2_scores.csv'))) | set(glob.glob(str(newtools_dir / '*_scores.csv')))
    score_csvs = sorted(p for p in _cands if 'smoke' not in os.path.basename(p).lower())

    if not score_csvs:
        nn = BASE_N_TOOLS
        if args.out:
            out_path = Path(args.out).resolve()
        else:
            out_path = ROOT / 'scripts' / 'out' / f'merged_all_tools_{nn}tools.xlsx'
        print(
            f'[INFO] 无新工具分数 CSV，NN={nn}，复制基表 → {out_path}',
            file=sys.stderr,
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        base_df.to_excel(out_path, index=False, engine='openpyxl')
        print(f'[DONE] 输出: {out_path}', file=sys.stderr)
        return

    print(f'[INFO] 发现 {len(score_csvs)} 个新工具 score CSV:', file=sys.stderr)
    for p in score_csvs:
        print(f'       {os.path.basename(p)}', file=sys.stderr)

    # ── 逐工具 left-join ──────────────────────────────────────────────────────
    pending_tools: list = []
    merged = base_df.copy()
    tool_names_added: list = []

    for csv_path in score_csvs:
        tool_name = extract_tool_name(csv_path)
        tool_names_added.append(tool_name)
        print(f'\n[INFO] 处理工具: {tool_name}  ({os.path.basename(csv_path)})', file=sys.stderr)
        merged = merge_one_tool(merged, csv_path, tool_name, pending_tools)

    # ── 行数硬校验 ────────────────────────────────────────────────────────────
    if len(merged) != EXPECTED_ROWS:
        print(
            f'[ERR] 合并后行数 {len(merged)} ≠ 预期 {EXPECTED_ROWS}！'
            '可能存在 bb_idx 重复或外扩，中止写出',
            file=sys.stderr,
        )
        sys.exit(1)

    # ── DTU sidecar ───────────────────────────────────────────────────────────
    if pending_tools:
        pending_path = newtools_dir / 'PENDING_DTU_tools.txt'
        pending_path.write_text('\n'.join(pending_tools) + '\n', encoding='utf-8')
        print(f'[INFO] DTU pending 工具写入: {pending_path}', file=sys.stderr)
        print(f'       工具列表: {pending_tools}', file=sys.stderr)

    # ── 输出 xlsx ─────────────────────────────────────────────────────────────
    nn = BASE_N_TOOLS + len(tool_names_added)
    if args.out:
        out_path = Path(args.out).resolve()
    else:
        out_path = ROOT / 'scripts' / 'out' / f'merged_all_tools_{nn}tools.xlsx'

    out_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_excel(out_path, index=False, engine='openpyxl')

    print(f'\n[DONE] 输出: {out_path}', file=sys.stderr)
    print(
        f'[DONE] NN={nn} 工具  新增 ({len(tool_names_added)}): {tool_names_added}',
        file=sys.stderr,
    )
    print(
        f'[DONE] 最终表: {len(merged)} 行 × {len(merged.columns)} 列',
        file=sys.stderr,
    )


if __name__ == '__main__':
    main()
