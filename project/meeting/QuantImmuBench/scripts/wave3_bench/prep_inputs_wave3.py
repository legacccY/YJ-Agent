"""
prep_inputs_wave3.py — QuantImmuBench Wave-3 预处理
=====================================================
读 master_backbone.csv，为 3 工具（PRIME / ImmuneApp / deepHLApan）各生成
输入文件 + unique(肽,HLA)→bb_idx map。MT + WT 都生成。

产出文件（均在 --out-dir，默认 scripts/out/）：
    out/prime_input_{allele}/peps_MT.txt    每 HLA 一目录，MT 肽段（每行一条）
    out/prime_input_{allele}/peps_WT.txt    WT 肽段
    out/prime_input_map_MT.csv              unique (peptide, allele_prime) → bb_idx list（MT）
    out/prime_input_map_WT.csv              同，WT
    out/immuneapp_input_{allele}/peps_MT.txt   ImmuneApp 按 allele 分目录
    out/immuneapp_input_{allele}/peps_WT.txt
    out/immuneapp_input_map_MT.csv
    out/immuneapp_input_map_WT.csv
    out/deephlapan_input_MT.csv             deepHLApan 整张 CSV（Annotation,HLA,peptide）
    out/deephlapan_input_WT.csv
    out/deephlapan_input_map_MT.csv
    out/deephlapan_input_map_WT.csv

肽长过滤：
    PRIME       8-14（超界行跳过，map 中标 SKIPPED_LEN）
    ImmuneApp   8-15（超界行跳过，map 中标 SKIPPED_LEN）
    deepHLApan  8-15（超界行跳过，map 中标 SKIPPED_LEN）

HLA 格式转换：
    PRIME       HLA-A*24:02 → A2402（去 HLA- 前缀 + 去星号 + 去冒号）
    ImmuneApp   HLA-A*24:02 → 不变（原格式，带 HLA- 带星带冒号）
    deepHLApan  HLA-A*24:02 → HLA-A24:02（去星号，保留冒号）

复用 prepare_inputs.py 的 normalize_hla / hla_to_deepimmuno /
hla_to_improve（不重写 HLA 归一化）。

运行示例：
    python scripts/wave3_bench/prep_inputs_wave3.py
    python scripts/wave3_bench/prep_inputs_wave3.py \\
        --backbone scripts/out/master_backbone.csv \\
        --out-dir  scripts/out
"""

import argparse
import ast
import os
import sys
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# 把 scripts/ 目录加入路径，复用 prepare_inputs.py 的 HLA 工具函数
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent   # .../scripts/
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from prepare_inputs import normalize_hla, report_hla_warnings  # noqa: E402


# ---------------------------------------------------------------------------
# HLA 格式转换（wave-3 工具专用）
# ---------------------------------------------------------------------------

def hla_to_prime(hla_std: str) -> str:
    """
    HLA-A*24:02 → A2402
    去 'HLA-' 前缀 + 去星号 + 去冒号。
    示例：HLA-A*24:02 → A2402，HLA-B*57:01 → B5701
    """
    s = str(hla_std).strip()
    if s.upper().startswith('HLA-'):
        s = s[4:]
    s = s.replace('*', '').replace(':', '')
    return s


def hla_to_immuneapp(hla_std: str) -> str:
    """
    ImmuneApp 接受标准格式，HLA-A*24:02 不变。
    此处直接返回 hla_std（已由 normalize_hla 标准化）。
    """
    return str(hla_std)


def hla_to_deephlapan(hla_std: str) -> str:
    """
    HLA-A*24:02 → HLA-A24:02（去星号，保留 HLA- 和冒号）
    示例：HLA-B*57:01 → HLA-B57:01
    """
    return str(hla_std).replace('*', '')


# ---------------------------------------------------------------------------
# 内部辅助：按 (peptide, hla_fmt) unique 去重 + 建 map
# ---------------------------------------------------------------------------

def _build_unique_and_map(rows: list[dict], key_fields: tuple[str, str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    rows: list of {'peptide': ..., 'hla_fmt': ..., 'bb_idx': int}
    key_fields: ('peptide', 'hla_fmt')
    返回 (unique_df, map_df)
      unique_df 列：peptide, hla_fmt（去重）
      map_df 列：key（peptide|hla_fmt）, backbone_indices（str of list）
    """
    from collections import defaultdict
    key_to_indices: dict = defaultdict(list)
    seen_keys: list = []

    for r in rows:
        pep = str(r['peptide']).strip()
        hla = str(r['hla_fmt']).strip()
        k   = f'{pep}|{hla}'
        if k not in key_to_indices:
            seen_keys.append({'peptide': pep, 'hla_fmt': hla})
        key_to_indices[k].append(r['bb_idx'])

    unique_df = pd.DataFrame(seen_keys)
    map_df    = pd.DataFrame([
        {'key': k, 'backbone_indices': str(v)}
        for k, v in key_to_indices.items()
    ])
    return unique_df, map_df


# ---------------------------------------------------------------------------
# PRIME 输入生成
# ---------------------------------------------------------------------------

PRIME_VALID_LEN = range(8, 15)   # 8..14


def export_prime(backbone: pd.DataFrame, out_dir: Path):
    """
    PRIME 按 allele 分组：每个 unique allele 建一个子目录
        out/prime_input_<allele>/peps_MT.txt
        out/prime_input_<allele>/peps_WT.txt

    同时出两个 map：
        out/prime_input_map_MT.csv
        out/prime_input_map_WT.csv
    map key = peptide|allele_prime，backbone_indices = list of bb_idx。
    肽长超出 8-14 的行跳过；若 WT 子肽为空或超界也跳过 WT 侧（map 不填）。

    PRIME -a 参数接受逗号分隔 allele 列表；每目录对应单一 allele，
    命令行即 ./PRIME -i peps_MT.txt -o out_MT.txt -a <allele>。
    """
    mt_rows: list[dict] = []
    wt_rows: list[dict] = []

    for bb_idx, row in backbone.iterrows():
        hla_std = row['HLA_Allele']
        if pd.isna(hla_std):
            continue
        hla_std = str(hla_std)
        hla_pr  = hla_to_prime(hla_std)

        mt_sub = str(row['MT_Subpeptide']).strip()
        wt_sub = str(row['WT_Subpeptide']).strip() if pd.notna(row['WT_Subpeptide']) else ''

        mt_len = len(mt_sub)

        if mt_len not in PRIME_VALID_LEN:
            # 超界，记 SKIPPED_LEN 标记进 map（仅记录，不写输入文件）
            mt_rows.append({'peptide': f'SKIPPED_LEN:{mt_sub}', 'hla_fmt': hla_pr, 'bb_idx': bb_idx, 'skip': True})
        else:
            mt_rows.append({'peptide': mt_sub, 'hla_fmt': hla_pr, 'bb_idx': bb_idx, 'skip': False})

        wt_len = len(wt_sub)
        if wt_sub and wt_len in PRIME_VALID_LEN:
            wt_rows.append({'peptide': wt_sub, 'hla_fmt': hla_pr, 'bb_idx': bb_idx, 'skip': False})
        elif wt_sub and wt_len not in PRIME_VALID_LEN:
            wt_rows.append({'peptide': f'SKIPPED_LEN:{wt_sub}', 'hla_fmt': hla_pr, 'bb_idx': bb_idx, 'skip': True})

    # --- 写 map（含 SKIPPED_LEN 行） ---
    _write_prime_map(mt_rows, out_dir / 'prime_input_map_MT.csv', 'MT')
    _write_prime_map(wt_rows, out_dir / 'prime_input_map_WT.csv', 'WT')

    # --- 按 allele 分目录写肽段 txt（仅有效行）---
    _write_prime_allele_dirs(mt_rows, out_dir, 'MT')
    _write_prime_allele_dirs(wt_rows, out_dir, 'WT')


def _write_prime_map(rows: list[dict], map_path: Path, side: str):
    """写 prime_input_map_MT/WT.csv。"""
    from collections import defaultdict
    key_to_indices: dict = defaultdict(list)
    for r in rows:
        k = f'{r["peptide"]}|{r["hla_fmt"]}'
        key_to_indices[k].append(r['bb_idx'])

    map_df = pd.DataFrame([
        {'key': k, 'backbone_indices': str(v)}
        for k, v in key_to_indices.items()
    ])
    map_df.to_csv(map_path, index=False, encoding='utf-8')
    n_total  = len(key_to_indices)
    n_skip   = sum(1 for k in key_to_indices if k.startswith('SKIPPED_LEN:'))
    print(
        f'[PRIME-{side}] map 写入 {map_path.name}：{n_total} unique keys，'
        f'其中 {n_skip} 条 SKIPPED_LEN',
        file=sys.stderr
    )


def _write_prime_allele_dirs(rows: list[dict], out_dir: Path, side: str):
    """
    有效行（skip=False）按 hla_fmt 分组，
    每组写 out/prime_input_<allele>/peps_{side}.txt。
    """
    from collections import defaultdict
    allele_peps: dict = defaultdict(set)
    for r in rows:
        if not r.get('skip', True):
            allele_peps[r['hla_fmt']].add(r['peptide'])

    for allele, peps in allele_peps.items():
        allele_dir = out_dir / f'prime_input_{allele}'
        allele_dir.mkdir(parents=True, exist_ok=True)
        pep_file   = allele_dir / f'peps_{side}.txt'
        with open(pep_file, 'w', encoding='utf-8') as fh:
            for p in sorted(peps):
                fh.write(p + '\n')

    n_alleles = len(allele_peps)
    n_peps    = sum(len(v) for v in allele_peps.values())
    print(
        f'[PRIME-{side}] 写 {n_alleles} 个 allele 目录，共 {n_peps} unique 肽',
        file=sys.stderr
    )


# ---------------------------------------------------------------------------
# ImmuneApp 输入生成
# ---------------------------------------------------------------------------

IMMUNEAPP_VALID_LEN = range(8, 16)   # 8..15


def export_immuneapp(backbone: pd.DataFrame, out_dir: Path):
    """
    ImmuneApp 按 allele 分组（标准 HLA 格式，不转换）。
    每 allele 建子目录：
        out/immuneapp_input_<allele_safe>/peps_MT.txt
        out/immuneapp_input_<allele_safe>/peps_WT.txt
    allele_safe：把 HLA-A*24:02 中的 * / : 替换为 _ 以供目录命名（A_24_02 → HLA-A_24_02）。

    map：
        out/immuneapp_input_map_MT.csv
        out/immuneapp_input_map_WT.csv
    map key = peptide|HLA_std。
    """
    mt_rows: list[dict] = []
    wt_rows: list[dict] = []

    for bb_idx, row in backbone.iterrows():
        hla_std = row['HLA_Allele']
        if pd.isna(hla_std):
            continue
        hla_std = str(hla_std)
        # ImmuneApp 用原始标准格式
        hla_ia  = hla_to_immuneapp(hla_std)

        mt_sub = str(row['MT_Subpeptide']).strip()
        wt_sub = str(row['WT_Subpeptide']).strip() if pd.notna(row['WT_Subpeptide']) else ''

        mt_len = len(mt_sub)
        if mt_len not in IMMUNEAPP_VALID_LEN:
            mt_rows.append({'peptide': f'SKIPPED_LEN:{mt_sub}', 'hla_fmt': hla_ia, 'bb_idx': bb_idx, 'skip': True})
        else:
            mt_rows.append({'peptide': mt_sub, 'hla_fmt': hla_ia, 'bb_idx': bb_idx, 'skip': False})

        wt_len = len(wt_sub)
        if wt_sub and wt_len in IMMUNEAPP_VALID_LEN:
            wt_rows.append({'peptide': wt_sub, 'hla_fmt': hla_ia, 'bb_idx': bb_idx, 'skip': False})
        elif wt_sub and wt_len not in IMMUNEAPP_VALID_LEN:
            wt_rows.append({'peptide': f'SKIPPED_LEN:{wt_sub}', 'hla_fmt': hla_ia, 'bb_idx': bb_idx, 'skip': True})

    # --- map ---
    _write_simple_map(mt_rows, out_dir / 'immuneapp_input_map_MT.csv', 'ImmuneApp-MT')
    _write_simple_map(wt_rows, out_dir / 'immuneapp_input_map_WT.csv', 'ImmuneApp-WT')

    # --- allele dirs ---
    _write_immuneapp_allele_dirs(mt_rows, out_dir, 'MT')
    _write_immuneapp_allele_dirs(wt_rows, out_dir, 'WT')


def _allele_to_dirname(hla_ia: str) -> str:
    """HLA-A*24:02 → HLA-A_24_02（目录命名安全）。"""
    return hla_ia.replace('*', '_').replace(':', '_')


def _write_immuneapp_allele_dirs(rows: list[dict], out_dir: Path, side: str):
    from collections import defaultdict
    allele_peps: dict = defaultdict(set)
    for r in rows:
        if not r.get('skip', True):
            allele_peps[r['hla_fmt']].add(r['peptide'])

    for hla_ia, peps in allele_peps.items():
        dirname    = _allele_to_dirname(hla_ia)
        allele_dir = out_dir / f'immuneapp_input_{dirname}'
        allele_dir.mkdir(parents=True, exist_ok=True)
        pep_file   = allele_dir / f'peps_{side}.txt'
        with open(pep_file, 'w', encoding='utf-8') as fh:
            for p in sorted(peps):
                fh.write(p + '\n')

    n_alleles = len(allele_peps)
    n_peps    = sum(len(v) for v in allele_peps.values())
    print(
        f'[ImmuneApp-{side}] 写 {n_alleles} 个 allele 目录，共 {n_peps} unique 肽',
        file=sys.stderr
    )


# ---------------------------------------------------------------------------
# deepHLApan 输入生成
# ---------------------------------------------------------------------------

DEEPHLAPAN_VALID_LEN = range(8, 16)   # 8..15


def export_deephlapan(backbone: pd.DataFrame, out_dir: Path):
    """
    deepHLApan 输入：CSV，列 Annotation,HLA,peptide（有表头）。
    HLA 格式 HLA-A24:02（去星号）。

    MT/WT 各出一个 CSV：
        out/deephlapan_input_MT.csv
        out/deephlapan_input_WT.csv
    map：
        out/deephlapan_input_map_MT.csv
        out/deephlapan_input_map_WT.csv
    map key = annotation|HLA_dp（annotation 唯一标识每行，防肽段重复歧义）。

    Annotation = bb_idx（整数，确保唯一）；去重逻辑：
    deepHLApan 需要每肽对+HLA 一条（可重复肽），
    这里按 unique(peptide, HLA) 去重，Annotation = 第一次出现的 bb_idx。
    """
    mt_rows: list[dict] = []
    wt_rows: list[dict] = []

    for bb_idx, row in backbone.iterrows():
        hla_std = row['HLA_Allele']
        if pd.isna(hla_std):
            continue
        hla_std = str(hla_std)
        hla_dp  = hla_to_deephlapan(hla_std)

        mt_sub = str(row['MT_Subpeptide']).strip()
        wt_sub = str(row['WT_Subpeptide']).strip() if pd.notna(row['WT_Subpeptide']) else ''

        mt_len = len(mt_sub)
        if mt_len not in DEEPHLAPAN_VALID_LEN:
            # 跳过 + 记入 map 作 skip 标记
            mt_rows.append({
                'annotation': f'SKIPPED_LEN_{bb_idx}',
                'hla_dp':     hla_dp,
                'peptide':    mt_sub,
                'bb_idx':     bb_idx,
                'skip':       True,
            })
        else:
            mt_rows.append({
                'annotation': str(bb_idx),
                'hla_dp':     hla_dp,
                'peptide':    mt_sub,
                'bb_idx':     bb_idx,
                'skip':       False,
            })

        wt_len = len(wt_sub)
        if wt_sub and wt_len in DEEPHLAPAN_VALID_LEN:
            wt_rows.append({
                'annotation': str(bb_idx),
                'hla_dp':     hla_dp,
                'peptide':    wt_sub,
                'bb_idx':     bb_idx,
                'skip':       False,
            })
        elif wt_sub and wt_len not in DEEPHLAPAN_VALID_LEN:
            wt_rows.append({
                'annotation': f'SKIPPED_LEN_{bb_idx}',
                'hla_dp':     hla_dp,
                'peptide':    wt_sub,
                'bb_idx':     bb_idx,
                'skip':       True,
            })

    # --- 写输入 CSV（有效行） ---
    for side, rows in [('MT', mt_rows), ('WT', wt_rows)]:
        valid = [r for r in rows if not r['skip']]
        # unique by (peptide, hla_dp)
        seen: set = set()
        unique_rows = []
        for r in valid:
            k = (r['peptide'], r['hla_dp'])
            if k not in seen:
                seen.add(k)
                unique_rows.append({
                    'Annotation': r['annotation'],
                    'HLA':        r['hla_dp'],
                    'peptide':    r['peptide'],
                })
        out_csv = out_dir / f'deephlapan_input_{side}.csv'
        pd.DataFrame(unique_rows, columns=['Annotation', 'HLA', 'peptide']).to_csv(
            out_csv, index=False, encoding='utf-8'
        )
        print(
            f'[deepHLApan-{side}] 写 {len(unique_rows)} unique (peptide,HLA) → {out_csv.name}',
            file=sys.stderr
        )

    # --- 写 map ---
    _write_deephlapan_map(mt_rows, out_dir / 'deephlapan_input_map_MT.csv', 'MT')
    _write_deephlapan_map(wt_rows, out_dir / 'deephlapan_input_map_WT.csv', 'WT')


def _write_deephlapan_map(rows: list[dict], map_path: Path, side: str):
    """
    map key = peptide|HLA_dp（去重 key），backbone_indices = list of bb_idx。
    SKIPPED_LEN 行单独记录以便追溯。
    """
    from collections import defaultdict
    key_to_indices: dict = defaultdict(list)
    for r in rows:
        pep = r['peptide']
        hla = r['hla_dp']
        if r['skip']:
            k = f'SKIPPED_LEN:{pep}|{hla}'
        else:
            k = f'{pep}|{hla}'
        key_to_indices[k].append(r['bb_idx'])

    map_df = pd.DataFrame([
        {'key': k, 'backbone_indices': str(v)}
        for k, v in key_to_indices.items()
    ])
    map_df.to_csv(map_path, index=False, encoding='utf-8')
    n_skip = sum(1 for k in key_to_indices if k.startswith('SKIPPED_LEN:'))
    print(
        f'[deepHLApan-{side}] map 写入 {map_path.name}：'
        f'{len(key_to_indices)} unique keys，{n_skip} 条 SKIPPED_LEN',
        file=sys.stderr
    )


# ---------------------------------------------------------------------------
# 通用 map 写入（PRIME / ImmuneApp 共用）
# ---------------------------------------------------------------------------

def _write_simple_map(rows: list[dict], map_path: Path, tag: str):
    """rows 含 peptide/hla_fmt/bb_idx/skip，写 key(peptide|hla_fmt) → bb_idx list。"""
    from collections import defaultdict
    key_to_indices: dict = defaultdict(list)
    for r in rows:
        if r.get('skip'):
            k = f'SKIPPED_LEN:{r["peptide"]}|{r["hla_fmt"]}'
        else:
            k = f'{r["peptide"]}|{r["hla_fmt"]}'
        key_to_indices[k].append(r['bb_idx'])

    map_df = pd.DataFrame([
        {'key': k, 'backbone_indices': str(v)}
        for k, v in key_to_indices.items()
    ])
    map_df.to_csv(map_path, index=False, encoding='utf-8')
    n_skip = sum(1 for k in key_to_indices if k.startswith('SKIPPED_LEN:'))
    print(
        f'[{tag}] map 写入 {map_path.name}：'
        f'{len(key_to_indices)} unique keys，{n_skip} 条 SKIPPED_LEN',
        file=sys.stderr
    )


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description='QuantImmuBench Wave-3 预处理：为 PRIME/ImmuneApp/deepHLApan 生成输入'
    )
    _default_backbone = str(
        Path(__file__).resolve().parent.parent / 'out' / 'master_backbone.csv'
    )
    _default_out = str(
        Path(__file__).resolve().parent.parent / 'out'
    )
    parser.add_argument(
        '--backbone',
        default=_default_backbone,
        help='master_backbone.csv 路径（默认 scripts/out/master_backbone.csv）'
    )
    parser.add_argument(
        '--out-dir',
        default=_default_out,
        help='输出目录（默认 scripts/out/）'
    )
    return parser.parse_args()


def main():
    args   = parse_args()
    bb_path = Path(args.backbone).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f'[INFO] backbone = {bb_path}', file=sys.stderr)
    print(f'[INFO] out_dir  = {out_dir}',  file=sys.stderr)

    backbone = pd.read_csv(bb_path, index_col='bb_idx', encoding='utf-8')
    print(f'[backbone] 读入 {len(backbone)} 行，{len(backbone.columns)} 列', file=sys.stderr)

    # --- PRIME ---
    print('[INFO] === PRIME ===', file=sys.stderr)
    export_prime(backbone, out_dir)

    # --- ImmuneApp ---
    print('[INFO] === ImmuneApp ===', file=sys.stderr)
    export_immuneapp(backbone, out_dir)

    # --- deepHLApan ---
    print('[INFO] === deepHLApan ===', file=sys.stderr)
    export_deephlapan(backbone, out_dir)

    # --- HLA 告警（来自 normalize_hla，如有） ---
    report_hla_warnings()

    print('[DONE] prep_inputs_wave3.py 完成', file=sys.stderr)


if __name__ == '__main__':
    main()
