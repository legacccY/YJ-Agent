"""
parse_prime_immuneapp_official.py — PRIME / ImmuneApp 官方数据结果回贴
=====================================================================
本地跑（HPC 结果拉回后）。解析 prime_out/ + immuneapp_out/ 的原始输出，
经 prime_input_map_MT/WT.csv、immuneapp_input_map_MT/WT.csv 回贴 bb_idx，
产出两张独立 CSV：

    scripts/out_official/PRIME_official.csv      列：bb_idx, MT_PRIME, WT_PRIME
    scripts/out_official/ImmuneApp_official.csv  列：bb_idx, MT_ImmuneApp, WT_ImmuneApp

★ 数据完整性修正（2026-06-30）★
本脚本**不再复用 merge_wave3.merge_prime / merge_immuneapp**——那两个函数建 score_map
时同时存肽级 key（score_map[pep]=score）与复合 key，回贴时 .get((pep,allele), .get(pep))
会在「某等位没跑出结果」时**用该肽在别等位的分回填**，制造假覆盖（PRIME 仅跑 14/26 等位
却把缺失等位的行全填满）。这里本地定义严格匹配版 merge_prime_strict / merge_immuneapp_strict：

  - score_map 仅以 (peptide, allele) 复合 key，且 allele **来自输出目录名**（= 该文件实际
    跑的等位），不靠 BestAllele 列；
  - 回贴时只做精确 (pep, map_key_allele) 匹配，缺该实际分 → 该 bb_idx 保持 NaN（诚实部分
    覆盖），**绝不肽级兜底回填别等位的分**；
  - PRIME 输出目录名为 PRIME 格式（A0101），与 map key allele 同格式，直接匹配；
  - ImmuneApp 输出目录名为安全文件名（HLA-A_01_01），转成 map 的标准格式（HLA-A*01:01）匹配。

parse 仍复用 merge_wave3.parse_prime / parse_immuneapp（只读列解析，无回贴逻辑）。

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
import ast
import sys
from pathlib import Path

import pandas as pd

# --- 仅复用 merge_wave3.py 的 parse（只读列解析）；回贴逻辑本地严格重写 ---
# 不再 import merge_prime / merge_immuneapp（含肽级兜底，会误填别等位的分）。
_WAVE3_DIR = Path(__file__).resolve().parent.parent / 'wave3_bench'
sys.path.insert(0, str(_WAVE3_DIR))
from merge_wave3 import (  # noqa: E402
    parse_prime,
    parse_immuneapp,
)


# ---------------------------------------------------------------------------
# HLA 安全文件名 → 标准格式（与 immuneapp 输出目录命名互逆）
# ---------------------------------------------------------------------------

def hla_safe_to_std(safe: str) -> str:
    """HLA-A_01_01 → HLA-A*01:01（首段后第一个 _ 变 *，其余 _ 变 :）。"""
    parts = str(safe).strip().split('_')
    if len(parts) < 2:
        return str(safe).strip()
    return parts[0] + '*' + ':'.join(parts[1:])


# ---------------------------------------------------------------------------
# 递归收集 + 逐文件解析（官方输出为 per-allele 嵌套目录，非平铺）
# ---------------------------------------------------------------------------

def _parse_side_files_tagged(files: list[Path], parser, side: str,
                             allele_of) -> pd.DataFrame | None:
    """
    对一组文件逐个调 parser（复用 merge_wave3），并给每行打 SrcAllele 列
    （= 该文件实际跑的等位，由 allele_of(file) 从目录名得出）。拼接。无文件返回 None。

    SrcAllele 是严格回贴的依据：PRIME/ImmuneApp 均 per-allele 分目录跑，一个输出文件里
    所有肽都是「该目录等位」的分，故用目录名而非 BestAllele/Allele 列来锁定等位，避免误填。
    """
    dfs = []
    for f in files:
        try:
            df = parser(str(f), side=side)
            df = df.copy()
            df['SrcAllele'] = allele_of(f)
            dfs.append(df)
        except Exception as e:
            print(f'[WARN] {side} 解析失败 {f}：{e}', file=sys.stderr)
    if not dfs:
        return None
    return pd.concat(dfs, ignore_index=True)


def collect_prime(prime_out: Path):
    """prime_out/<allele>/out_MT.txt + out_WT.txt → (mt_df, wt_df)。
    SrcAllele = 父目录名（PRIME 格式 A0101，与 map key allele 同格式）。"""
    mt_files = sorted(prime_out.rglob('out_MT.txt'))
    wt_files = sorted(prime_out.rglob('out_WT.txt'))
    print(f'[PRIME] 发现 out_MT.txt={len(mt_files)}，out_WT.txt={len(wt_files)}', file=sys.stderr)
    allele_of = lambda f: f.parent.name  # prime_out/<allele>/out_MT.txt
    mt_df = _parse_side_files_tagged(mt_files, parse_prime, 'MT', allele_of)
    wt_df = _parse_side_files_tagged(wt_files, parse_prime, 'WT', allele_of)
    return mt_df, wt_df


def collect_immuneapp(immuneapp_out: Path):
    """immuneapp_out/<allele_safe>/MT|WT/*.tsv → (mt_df, wt_df)。
    SrcAllele = 上上层目录名转标准格式（HLA-A_01_01 → HLA-A*01:01，与 map key allele 同格式）。"""
    mt_files = sorted(p for p in immuneapp_out.rglob('*.tsv')
                      if p.parent.name.upper() == 'MT')
    wt_files = sorted(p for p in immuneapp_out.rglob('*.tsv')
                      if p.parent.name.upper() == 'WT')
    print(f'[ImmuneApp] 发现 MT .tsv={len(mt_files)}，WT .tsv={len(wt_files)}', file=sys.stderr)
    allele_of = lambda f: hla_safe_to_std(f.parent.parent.name)  # <safe>/MT/*.tsv
    mt_df = _parse_side_files_tagged(mt_files, parse_immuneapp, 'MT', allele_of)
    wt_df = _parse_side_files_tagged(wt_files, parse_immuneapp, 'WT', allele_of)
    return mt_df, wt_df


# ---------------------------------------------------------------------------
# 严格回贴：仅精确 (peptide, allele) 匹配，allele 来自输出目录名（实际跑的等位）。
# 缺该 (pep,allele) 的实际分 → 保持 NaN，绝不肽级兜底回填别等位的分。
# ---------------------------------------------------------------------------

def merge_prime_strict(backbone, prime_mt_df, prime_wt_df, map_dir: Path):
    """PRIME 严格回贴。返回 (result, mt_run_alleles)。
    mt_run_alleles = MT 侧实际跑出结果的等位集合（PRIME 格式），供覆盖校验过滤。"""
    result = backbone.copy()
    result['MT_PRIME'] = float('nan')
    result['WT_PRIME'] = float('nan')

    def _do_merge(side_df, map_path: Path, col_name: str):
        if side_df is None:
            return set()
        if not map_path.exists():
            print(f'[WARN] PRIME map 不存在：{map_path}', file=sys.stderr)
            return set()
        map_df = pd.read_csv(map_path, encoding='utf-8')

        # 严格 (pep, SrcAllele) → score，SrcAllele 来自目录名（PRIME 格式）
        score_map: dict = {}
        run_alleles: set = set()
        for _, row in side_df.iterrows():
            pep = str(row['Peptide']).strip()
            src_allele = str(row['SrcAllele']).strip()
            run_alleles.add(src_allele)
            score_map[(pep, src_allele)] = row['Score_bestAllele']

        for _, map_row in map_df.iterrows():
            raw_key = str(map_row['key'])
            if raw_key.startswith('SKIPPED_LEN:'):
                continue
            parts = raw_key.split('|', 1)
            if len(parts) < 2:
                continue
            pep, allele_pr = parts[0], parts[1]
            # 仅精确匹配；缺该 (pep,该等位) 实际分 → 跳过（保持 NaN），不肽级兜底
            if (pep, allele_pr) not in score_map:
                continue
            score_val = score_map[(pep, allele_pr)]
            try:
                bb_indices = ast.literal_eval(str(map_row['backbone_indices']))
            except Exception:
                continue
            for idx in bb_indices:
                if idx in result.index:
                    result.at[idx, col_name] = score_val
        return run_alleles

    mt_alleles = _do_merge(prime_mt_df, map_dir / 'prime_input_map_MT.csv', 'MT_PRIME')
    wt_alleles = _do_merge(prime_wt_df, map_dir / 'prime_input_map_WT.csv', 'WT_PRIME')
    n_mt = result['MT_PRIME'].notna().sum()
    n_wt = result['WT_PRIME'].notna().sum()
    print(f'[PRIME] 严格回贴：MT_PRIME={n_mt} 行非空（{len(mt_alleles)} 个实际等位），'
          f'WT_PRIME={n_wt} 行非空（{len(wt_alleles)} 个实际等位）', file=sys.stderr)
    return result, mt_alleles


def merge_immuneapp_strict(backbone, ia_mt_df, ia_wt_df, map_dir: Path):
    """ImmuneApp 严格回贴。返回 (result, mt_run_alleles)。
    mt_run_alleles = MT 侧实际跑出结果的等位集合（标准格式），供覆盖校验过滤。"""
    result = backbone.copy()
    result['MT_ImmuneApp'] = float('nan')
    result['WT_ImmuneApp'] = float('nan')

    def _do_merge(side_df, map_path: Path, col_name: str):
        if side_df is None:
            return set()
        if not map_path.exists():
            print(f'[WARN] ImmuneApp map 不存在：{map_path}', file=sys.stderr)
            return set()
        map_df = pd.read_csv(map_path, encoding='utf-8')

        # 严格 (pep, SrcAllele) → score，SrcAllele 来自目录名（已转标准格式）
        score_map: dict = {}
        run_alleles: set = set()
        for _, row in side_df.iterrows():
            pep = str(row['Peptide']).strip()
            src_allele = str(row['SrcAllele']).strip()
            run_alleles.add(src_allele)
            score_map[(pep, src_allele)] = row['Immunogenicity_score']

        for _, map_row in map_df.iterrows():
            raw_key = str(map_row['key'])
            if raw_key.startswith('SKIPPED_LEN:'):
                continue
            parts = raw_key.split('|', 1)
            if len(parts) < 2:
                continue
            pep, hla_std = parts[0], parts[1]
            if (pep, hla_std) not in score_map:
                continue
            score_val = score_map[(pep, hla_std)]
            try:
                bb_indices = ast.literal_eval(str(map_row['backbone_indices']))
            except Exception:
                continue
            for idx in bb_indices:
                if idx in result.index:
                    result.at[idx, col_name] = score_val
        return run_alleles

    mt_alleles = _do_merge(ia_mt_df, map_dir / 'immuneapp_input_map_MT.csv', 'MT_ImmuneApp')
    wt_alleles = _do_merge(ia_wt_df, map_dir / 'immuneapp_input_map_WT.csv', 'WT_ImmuneApp')
    n_mt = result['MT_ImmuneApp'].notna().sum()
    n_wt = result['WT_ImmuneApp'].notna().sum()
    print(f'[ImmuneApp] 严格回贴：MT_ImmuneApp={n_mt} 行非空（{len(mt_alleles)} 个实际等位），'
          f'WT_ImmuneApp={n_wt} 行非空（{len(wt_alleles)} 个实际等位）', file=sys.stderr)
    return result, mt_alleles


# ---------------------------------------------------------------------------
# 校验：每个 map 中非 SKIPPED 的 bb_idx 都应拿到 MT 分（含 43 补跑肽）
# ---------------------------------------------------------------------------

def _expected_mt_bbidx(map_path: Path, run_alleles: set | None = None) -> set:
    """从 *_map_MT.csv 收集非 SKIPPED 的 bb_idx 集合。

    run_alleles 非 None 时，只计入 map key allele 落在「实际跑出结果的等位」内的 bb_idx
    ——这样覆盖断言只针对真正跑了的等位（诚实部分覆盖），不把未跑等位算作缺失而误报。
    """
    if not map_path.exists():
        print(f'[WARN] map 不存在，跳过校验：{map_path}', file=sys.stderr)
        return set()
    df = pd.read_csv(map_path, encoding='utf-8')
    s = set()
    for _, row in df.iterrows():
        key = str(row['key'])
        if key.startswith('SKIPPED_LEN:'):
            continue
        if run_alleles is not None:
            parts = key.split('|', 1)
            if len(parts) < 2 or parts[1] not in run_alleles:
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
    prime_mt_alleles: set = set()
    if prime_out.exists():
        prime_mt_df, prime_wt_df = collect_prime(prime_out)
        prime_res, prime_mt_alleles = merge_prime_strict(
            backbone, prime_mt_df, prime_wt_df, map_dir)
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
    ia_mt_alleles: set = set()
    if ia_out.exists():
        ia_mt_df, ia_wt_df = collect_immuneapp(ia_out)
        ia_res, ia_mt_alleles = merge_immuneapp_strict(
            backbone, ia_mt_df, ia_wt_df, map_dir)
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

    # ---------------- 覆盖摘要（distinct 等位 + 非空行）----------------
    print(f'[COVER] PRIME    : MT 实际跑 {len(prime_mt_alleles)} 个 distinct 等位，'
          f'MT_PRIME 非空 {prime_res["MT_PRIME"].notna().sum()} 行', file=sys.stderr)
    print(f'[COVER] ImmuneApp: MT 实际跑 {len(ia_mt_alleles)} 个 distinct 等位，'
          f'MT_ImmuneApp 非空 {ia_res["MT_ImmuneApp"].notna().sum()} 行', file=sys.stderr)

    # ---------------- 校验（仅针对实际跑出结果的等位，诚实部分覆盖）----------------
    # PRIME 只跑了部分等位 → 只断言这些等位对应的 bb_idx 都有分；未跑等位的行保持 NaN，不算缺失。
    prime_expect = _expected_mt_bbidx(map_dir / 'prime_input_map_MT.csv', prime_mt_alleles)
    ia_expect    = _expected_mt_bbidx(map_dir / 'immuneapp_input_map_MT.csv', ia_mt_alleles)
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
