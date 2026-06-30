"""
parse_prime_immuneapp_official.py — PRIME / ImmuneApp 官方数据结果回贴
=====================================================================
本地跑（HPC 结果拉回后）。解析 prime_out/ + immuneapp_out/ 的原始输出，
经 prime_input_map_MT/WT.csv、immuneapp_input_map_MT/WT.csv 回贴 bb_idx，
产出两张独立 CSV：

    scripts/out_official/PRIME_official.csv      列：bb_idx, MT_PRIME, WT_PRIME
    scripts/out_official/ImmuneApp_official.csv  列：bb_idx, MT_ImmuneApp, WT_ImmuneApp

parse / 回贴方向完全复用 scripts/wave3_bench/merge_wave3.py（不翻转方向）。

输出目录结构（HPC 脚本产出，拉回本地）：
  prime_out/<allele>/out_MT.txt            (+ out_WT.txt, 仅 7 个 allele)
  immuneapp_out/<allele_safe>/MT/*.tsv     (+ WT/*.tsv)

运行示例：
    python scripts/hpc_official/parse_prime_immuneapp_official.py \
        --prime-out     scripts/out_official/prime_out \
        --immuneapp-out scripts/out_official/immuneapp_out \
        --map-dir       scripts/out_official \
        --backbone      scripts/out_official/master_backbone_official.csv \
        --out-dir       scripts/out_official
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

# --- 复用 merge_wave3.py 的 parse / 回贴逻辑（方向沿用原，不翻转）---
_WAVE3_DIR = Path(__file__).resolve().parent.parent / 'wave3_bench'
sys.path.insert(0, str(_WAVE3_DIR))
from merge_wave3 import (  # noqa: E402
    parse_prime,
    parse_immuneapp,
    merge_prime,
    merge_immuneapp,
)


# ---------------------------------------------------------------------------
# 递归收集 + 逐文件解析（官方输出为 per-allele 嵌套目录，非平铺）
# ---------------------------------------------------------------------------

def _parse_side_files(files: list[Path], parser, side: str) -> pd.DataFrame | None:
    """对一组文件逐个调 parser（复用 merge_wave3），拼接。无文件返回 None。"""
    dfs = []
    for f in files:
        try:
            dfs.append(parser(str(f), side=side))
        except Exception as e:
            print(f'[WARN] {side} 解析失败 {f}：{e}', file=sys.stderr)
    if not dfs:
        return None
    return pd.concat(dfs, ignore_index=True)


def collect_prime(prime_out: Path):
    """prime_out/<allele>/out_MT.txt + out_WT.txt → (mt_df, wt_df)。"""
    mt_files = sorted(prime_out.rglob('out_MT.txt'))
    wt_files = sorted(prime_out.rglob('out_WT.txt'))
    print(f'[PRIME] 发现 out_MT.txt={len(mt_files)}，out_WT.txt={len(wt_files)}', file=sys.stderr)
    mt_df = _parse_side_files(mt_files, parse_prime, 'MT')
    wt_df = _parse_side_files(wt_files, parse_prime, 'WT')
    return mt_df, wt_df


def collect_immuneapp(immuneapp_out: Path):
    """immuneapp_out/<allele_safe>/MT|WT/*.tsv → (mt_df, wt_df)。"""
    mt_files = sorted(p for p in immuneapp_out.rglob('*.tsv')
                      if p.parent.name.upper() == 'MT')
    wt_files = sorted(p for p in immuneapp_out.rglob('*.tsv')
                      if p.parent.name.upper() == 'WT')
    print(f'[ImmuneApp] 发现 MT .tsv={len(mt_files)}，WT .tsv={len(wt_files)}', file=sys.stderr)
    mt_df = _parse_side_files(mt_files, parse_immuneapp, 'MT')
    wt_df = _parse_side_files(wt_files, parse_immuneapp, 'WT')
    return mt_df, wt_df


# ---------------------------------------------------------------------------
# 校验：每个 map 中非 SKIPPED 的 bb_idx 都应拿到 MT 分（含 43 补跑肽）
# ---------------------------------------------------------------------------

def _expected_mt_bbidx(map_path: Path) -> set:
    """从 *_map_MT.csv 收集所有非 SKIPPED 的 bb_idx 集合。"""
    import ast
    if not map_path.exists():
        print(f'[WARN] map 不存在，跳过校验：{map_path}', file=sys.stderr)
        return set()
    df = pd.read_csv(map_path, encoding='utf-8')
    s = set()
    for _, row in df.iterrows():
        if str(row['key']).startswith('SKIPPED_LEN:'):
            continue
        try:
            s.update(ast.literal_eval(str(row['backbone_indices'])))
        except Exception:
            continue
    return s


def _assert_mt_coverage(result: pd.DataFrame, col: str, expected: set, tool: str):
    """断言 expected 中每个 bb_idx 在 col 列都非空。打印覆盖统计。"""
    filled = set(result.index[result[col].notna()])
    missing = sorted(expected - filled)
    print(f'[CHECK] {tool}: MT 期望 {len(expected)} 个 bb_idx，已填 '
          f'{len(expected & filled)} 个，缺 {len(missing)} 个', file=sys.stderr)
    if missing:
        head = missing[:20]
        print(f'[CHECK][MISS] {tool} 缺失 bb_idx（前20）：{head}', file=sys.stderr)
    # 43 补跑肽：若全部覆盖则断言通过（覆盖即包含补跑子集）
    assert not missing, (
        f'{tool} MT 有 {len(missing)} 个 mapped bb_idx 未拿到分数，'
        f'补跑肽校验未通过：{missing[:20]}'
    )
    print(f'[CHECK][OK] {tool}: 全部 {len(expected)} 个 mapped MT bb_idx 均有分数 ✅',
          file=sys.stderr)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def parse_args():
    here = Path(__file__).resolve().parent
    default_official = here.parent / 'out_official'
    p = argparse.ArgumentParser(
        description='PRIME / ImmuneApp 官方结果回贴 → PRIME_official.csv + ImmuneApp_official.csv')
    p.add_argument('--prime-out',     default=str(default_official / 'prime_out'),
                   help='PRIME 输出根目录（含 <allele>/out_MT.txt）')
    p.add_argument('--immuneapp-out', default=str(default_official / 'immuneapp_out'),
                   help='ImmuneApp 输出根目录（含 <allele_safe>/MT|WT/*.tsv）')
    p.add_argument('--map-dir',       default=str(default_official),
                   help='存放 prime_input_map_*.csv / immuneapp_input_map_*.csv 的目录')
    p.add_argument('--backbone',      default=str(default_official / 'master_backbone_official.csv'),
                   help='master_backbone_official.csv（index_col=bb_idx）')
    p.add_argument('--out-dir',       default=str(default_official),
                   help='输出目录')
    p.add_argument('--no-assert', action='store_true',
                   help='关闭补跑肽覆盖断言（仅打印，不中断）')
    return p.parse_args()


def main():
    args = parse_args()
    map_dir = Path(args.map_dir).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    backbone = pd.read_csv(Path(args.backbone).resolve(),
                           index_col='bb_idx', encoding='utf-8')
    print(f'[backbone] 读入 {len(backbone)} 行 ← {args.backbone}', file=sys.stderr)

    # ---------------- PRIME ----------------
    prime_out = Path(args.prime_out).resolve()
    if prime_out.exists():
        prime_mt_df, prime_wt_df = collect_prime(prime_out)
        prime_res = merge_prime(backbone, prime_mt_df, prime_wt_df, map_dir)
    else:
        print(f'[WARN] PRIME 输出目录不存在：{prime_out}，MT/WT_PRIME 全 NaN', file=sys.stderr)
        prime_res = backbone.copy()
        prime_res['MT_PRIME'] = float('nan')
        prime_res['WT_PRIME'] = float('nan')

    prime_csv = (prime_res[['MT_PRIME', 'WT_PRIME']]
                 .reset_index()  # bb_idx 变列
                 .rename(columns={'index': 'bb_idx'}))
    if 'bb_idx' not in prime_csv.columns:
        prime_csv = prime_csv.rename(columns={prime_csv.columns[0]: 'bb_idx'})
    prime_path = out_dir / 'PRIME_official.csv'
    prime_csv.to_csv(prime_path, index=False, encoding='utf-8')
    print(f'[OUT] {prime_path}（{len(prime_csv)} 行，列 {list(prime_csv.columns)}）'
          f' MT非空={prime_res["MT_PRIME"].notna().sum()}'
          f' WT非空={prime_res["WT_PRIME"].notna().sum()}', file=sys.stderr)

    # ---------------- ImmuneApp ----------------
    ia_out = Path(args.immuneapp_out).resolve()
    if ia_out.exists():
        ia_mt_df, ia_wt_df = collect_immuneapp(ia_out)
        ia_res = merge_immuneapp(backbone, ia_mt_df, ia_wt_df, map_dir)
    else:
        print(f'[WARN] ImmuneApp 输出目录不存在：{ia_out}，MT/WT_ImmuneApp 全 NaN', file=sys.stderr)
        ia_res = backbone.copy()
        ia_res['MT_ImmuneApp'] = float('nan')
        ia_res['WT_ImmuneApp'] = float('nan')

    ia_csv = (ia_res[['MT_ImmuneApp', 'WT_ImmuneApp']]
              .reset_index()
              .rename(columns={'index': 'bb_idx'}))
    if 'bb_idx' not in ia_csv.columns:
        ia_csv = ia_csv.rename(columns={ia_csv.columns[0]: 'bb_idx'})
    ia_path = out_dir / 'ImmuneApp_official.csv'
    ia_csv.to_csv(ia_path, index=False, encoding='utf-8')
    print(f'[OUT] {ia_path}（{len(ia_csv)} 行，列 {list(ia_csv.columns)}）'
          f' MT非空={ia_res["MT_ImmuneApp"].notna().sum()}'
          f' WT非空={ia_res["WT_ImmuneApp"].notna().sum()}', file=sys.stderr)

    # ---------------- 校验（43 补跑肽全有 MT 分）----------------
    prime_expect = _expected_mt_bbidx(map_dir / 'prime_input_map_MT.csv')
    ia_expect    = _expected_mt_bbidx(map_dir / 'immuneapp_input_map_MT.csv')
    if args.no_assert:
        try:
            _assert_mt_coverage(prime_res, 'MT_PRIME', prime_expect, 'PRIME')
        except AssertionError as e:
            print(f'[CHECK][SOFT] {e}', file=sys.stderr)
        try:
            _assert_mt_coverage(ia_res, 'MT_ImmuneApp', ia_expect, 'ImmuneApp')
        except AssertionError as e:
            print(f'[CHECK][SOFT] {e}', file=sys.stderr)
    else:
        _assert_mt_coverage(prime_res, 'MT_PRIME', prime_expect, 'PRIME')
        _assert_mt_coverage(ia_res, 'MT_ImmuneApp', ia_expect, 'ImmuneApp')

    print('[DONE] parse_prime_immuneapp_official.py 完成', file=sys.stderr)


if __name__ == '__main__':
    main()
