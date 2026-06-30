"""
parse_presml_official.py — 4 个 ML 呈递工具官方结果严格回贴 bb_idx
===================================================================
QuantImmuBench Phase0 W2-presml slice。读各工具原始输出（主线跑完产），
严格 (peptide, allele) 精确匹配回贴 backbone 的 1761 行 bb_idx，每工具产
scripts/out_official/<Tool>_official.csv。

argparse 让每工具可单独 parse：
    python scripts/hpc_official/parse_presml_official.py --tool flurry  --raw .../mhcflurry_raw.csv
    python scripts/hpc_official/parse_presml_official.py --tool nuggets --raw .../mhcnuggets_raw.csv
    python scripts/hpc_official/parse_presml_official.py --tool seqnet  --raw .../mhcseqnet_raw.csv
    python scripts/hpc_official/parse_presml_official.py --tool transhla --raw .../transhla_raw.csv

★ strict 匹配纪律（同 parse_prime_immuneapp_official.py）★
  - score_map 仅以 (peptide, allele) 复合 key（TransHLA 仅 peptide）；
  - 回贴时只精确匹配，缺该 (pep,allele) 实际分 → 该 bb_idx 保持 NaN，
    **绝不用别等位 / 别肽的分回填**；
  - MT 侧用 (MT_Subpeptide, HLA_Allele) 查，WT 侧用 (WT_Subpeptide, HLA_Allele) 查；
  - WT_Subpeptide 为空/NaN（如 indel 无 WT）→ WT 列 NaN（诚实）。

各工具 raw schema + 输出列 + 方向（从官方 NOTES 核实）：
  MHCflurry  raw 列含 peptide,HLA_Allele,affinity,presentation_score
             HLA-aware，键 (peptide,HLA_Allele)
             → MHCflurry_official.csv：bb_idx, MT/WT_MHCflurry_presentation,
               MT/WT_MHCflurry_affinity_neg
               presentation 直接用（越高越强）；affinity_neg = -affinity（nM 越低越强→取负）
  MHCnuggets raw 列 peptide,HLA_Allele,ic50（HLA_Allele 已回写带星）
             HLA-aware，键 (peptide,HLA_Allele)
             → MHCnuggets_official.csv：bb_idx, MT/WT_MHCnuggets，值 = -ic50（越低越强→取负）
  MHCseqNet  raw 列 peptide,HLA_Allele,prob
             HLA-aware，键 (peptide,HLA_Allele)
             → MHCSeqNet_official.csv：bb_idx, MT/WT_MHCSeqNet，值 = prob（越高越强，不翻转）
  TransHLA   raw 列 peptide,prob,label
             HLA-agnostic！键仅 peptide，按子肽广播到该 bb_idx（无视 allele）
             → TransHLA_official.csv：bb_idx, MT/WT_TransHLA，值 = prob（越高越强，不翻转）

健壮性：raw 不存在 → 报错退出（不静默造空）；raw 列名大小写/别名容错（读到先 print 实际列名）。
Windows 规范：纯 pandas/pathlib，UTF-8，无 GPU。
"""

import argparse
import sys
from pathlib import Path

import pandas as pd


# ---------------------------------------------------------------------------
# 列名解析：大小写/别名容错
# ---------------------------------------------------------------------------

def resolve_col(df: pd.DataFrame, candidates: list[str], what: str) -> str:
    """在 df.columns 里按 candidates（不区分大小写/下划线）找列，返回真实列名。"""
    norm = lambda s: str(s).strip().lower().replace(' ', '').replace('_', '')
    cmap = {norm(c): c for c in df.columns}
    for cand in candidates:
        if norm(cand) in cmap:
            return cmap[norm(cand)]
    sys.exit(f'[FATAL] 找不到 {what} 列（候选 {candidates}）；raw 实际列名 = {list(df.columns)}')


def load_raw(raw_path: Path) -> pd.DataFrame:
    if not raw_path.exists():
        sys.exit(f'[FATAL] raw 文件不存在：{raw_path}（不静默造空，请先跑该工具产 raw）')
    df = pd.read_csv(raw_path, encoding='utf-8')
    print(f'[raw] 读入 {len(df)} 行 ← {raw_path}，实际列名 = {list(df.columns)}', file=sys.stderr)
    return df


def load_backbone(bb_path: Path) -> pd.DataFrame:
    if not bb_path.exists():
        sys.exit(f'[FATAL] backbone 不存在：{bb_path}')
    bb = pd.read_csv(bb_path, encoding='utf-8')
    for c in ('bb_idx', 'MT_Subpeptide', 'WT_Subpeptide', 'HLA_Allele'):
        if c not in bb.columns:
            sys.exit(f'[FATAL] backbone 缺列 {c}；实际列 = {list(bb.columns)}')
    bb = bb.sort_values('bb_idx').reset_index(drop=True)
    print(f'[backbone] 读入 {len(bb)} 行 ← {bb_path}', file=sys.stderr)
    return bb


def _norm_pep(v) -> str:
    return str(v).strip()


def _norm_allele(v) -> str:
    return str(v).strip()


def _is_empty(v) -> bool:
    if v is None:
        return True
    s = str(v).strip()
    return s == '' or s.lower() == 'nan'


# ---------------------------------------------------------------------------
# 回贴：HLA-aware（键 (pep,allele)）
# ---------------------------------------------------------------------------

def map_aware(bb: pd.DataFrame, score_map: dict, mt_col: str, wt_col: str) -> pd.DataFrame:
    """对每 bb_idx，MT 侧用 (MT_Subpeptide,HLA_Allele) 查，WT 侧用 (WT_Subpeptide,HLA_Allele) 查。"""
    mt_vals, wt_vals = [], []
    for _, row in bb.iterrows():
        allele = _norm_allele(row['HLA_Allele'])
        mt_pep = row['MT_Subpeptide']
        wt_pep = row['WT_Subpeptide']
        mt_vals.append(score_map.get((_norm_pep(mt_pep), allele), float('nan'))
                       if not _is_empty(mt_pep) else float('nan'))
        wt_vals.append(score_map.get((_norm_pep(wt_pep), allele), float('nan'))
                       if not _is_empty(wt_pep) else float('nan'))
    out = pd.DataFrame({'bb_idx': bb['bb_idx'].values})
    out[mt_col] = mt_vals
    out[wt_col] = wt_vals
    return out


def map_agnostic(bb: pd.DataFrame, score_map: dict, mt_col: str, wt_col: str) -> pd.DataFrame:
    """TransHLA：键仅 peptide，无视 allele，按子肽广播。"""
    mt_vals, wt_vals = [], []
    for _, row in bb.iterrows():
        mt_pep = row['MT_Subpeptide']
        wt_pep = row['WT_Subpeptide']
        mt_vals.append(score_map.get(_norm_pep(mt_pep), float('nan'))
                       if not _is_empty(mt_pep) else float('nan'))
        wt_vals.append(score_map.get(_norm_pep(wt_pep), float('nan'))
                       if not _is_empty(wt_pep) else float('nan'))
    out = pd.DataFrame({'bb_idx': bb['bb_idx'].values})
    out[mt_col] = mt_vals
    out[wt_col] = wt_vals
    return out


def _report(out: pd.DataFrame, bb: pd.DataFrame, cols: list[str], tool: str):
    print(f'[{tool}] 输出 {len(out)} 行（期望 {len(bb)}）', file=sys.stderr)
    assert len(out) == len(bb), f'{tool} 行数 {len(out)} != backbone {len(bb)}'
    for c in cols:
        n = out[c].notna().sum()
        print(f'[{tool}] {c} 非空 {n} 行', file=sys.stderr)
    # distinct 等位覆盖：MT 侧非空行对应的 HLA_Allele 数（取首个 MT 列）
    mt_col = cols[0]
    bb_idx_filled = set(out.loc[out[mt_col].notna(), 'bb_idx'])
    alleles = bb.loc[bb['bb_idx'].isin(bb_idx_filled), 'HLA_Allele'].nunique()
    print(f'[{tool}] MT 侧 distinct 等位覆盖 = {alleles}', file=sys.stderr)


# ---------------------------------------------------------------------------
# 各工具
# ---------------------------------------------------------------------------

def parse_flurry(raw: pd.DataFrame, bb: pd.DataFrame) -> pd.DataFrame:
    pc = resolve_col(raw, ['peptide'], 'peptide')
    ac = resolve_col(raw, ['HLA_Allele', 'allele', 'best_allele'], 'HLA_Allele')
    presc = resolve_col(raw, ['presentation_score', 'presentation', 'mhcflurry_presentation_score'],
                        'presentation_score')
    affc = resolve_col(raw, ['affinity', 'mhcflurry_affinity', 'prediction'], 'affinity')

    pres_map, aff_map = {}, {}
    for _, r in raw.iterrows():
        key = (_norm_pep(r[pc]), _norm_allele(r[ac]))
        pres_map[key] = r[presc]
        aff = r[affc]
        aff_map[key] = (-float(aff)) if pd.notna(aff) else float('nan')

    pres = map_aware(bb, pres_map, 'MT_MHCflurry_presentation', 'WT_MHCflurry_presentation')
    aff = map_aware(bb, aff_map, 'MT_MHCflurry_affinity_neg', 'WT_MHCflurry_affinity_neg')
    out = pres.merge(aff, on='bb_idx', how='left')
    out = out[['bb_idx', 'MT_MHCflurry_presentation', 'WT_MHCflurry_presentation',
               'MT_MHCflurry_affinity_neg', 'WT_MHCflurry_affinity_neg']]
    _report(out, bb, ['MT_MHCflurry_presentation', 'WT_MHCflurry_presentation',
                      'MT_MHCflurry_affinity_neg', 'WT_MHCflurry_affinity_neg'], 'MHCflurry')
    return out, 'MHCflurry_official.csv'


def parse_nuggets(raw: pd.DataFrame, bb: pd.DataFrame) -> pd.DataFrame:
    pc = resolve_col(raw, ['peptide'], 'peptide')
    ac = resolve_col(raw, ['HLA_Allele', 'allele'], 'HLA_Allele')
    ic = resolve_col(raw, ['ic50', 'IC50', 'prediction'], 'ic50')

    score_map = {}
    for _, r in raw.iterrows():
        key = (_norm_pep(r[pc]), _norm_allele(r[ac]))
        ic50 = r[ic]
        score_map[key] = (-float(ic50)) if pd.notna(ic50) else float('nan')

    out = map_aware(bb, score_map, 'MT_MHCnuggets', 'WT_MHCnuggets')
    _report(out, bb, ['MT_MHCnuggets', 'WT_MHCnuggets'], 'MHCnuggets')
    return out, 'MHCnuggets_official.csv'


def parse_seqnet(raw: pd.DataFrame, bb: pd.DataFrame) -> pd.DataFrame:
    pc = resolve_col(raw, ['peptide'], 'peptide')
    ac = resolve_col(raw, ['HLA_Allele', 'allele'], 'HLA_Allele')
    prc = resolve_col(raw, ['prob', 'probability', 'score'], 'prob')

    score_map = {}
    for _, r in raw.iterrows():
        key = (_norm_pep(r[pc]), _norm_allele(r[ac]))
        score_map[key] = r[prc]  # prob 不翻转

    out = map_aware(bb, score_map, 'MT_MHCSeqNet', 'WT_MHCSeqNet')
    _report(out, bb, ['MT_MHCSeqNet', 'WT_MHCSeqNet'], 'MHCSeqNet')
    return out, 'MHCSeqNet_official.csv'


def parse_transhla(raw: pd.DataFrame, bb: pd.DataFrame) -> pd.DataFrame:
    pc = resolve_col(raw, ['peptide'], 'peptide')
    prc = resolve_col(raw, ['prob', 'probability', 'score'], 'prob')

    score_map = {}
    for _, r in raw.iterrows():
        score_map[_norm_pep(r[pc])] = r[prc]  # 键仅 peptide，prob 不翻转

    out = map_agnostic(bb, score_map, 'MT_TransHLA', 'WT_TransHLA')
    _report(out, bb, ['MT_TransHLA', 'WT_TransHLA'], 'TransHLA')
    return out, 'TransHLA_official.csv'


def parse_hlathena(raw: pd.DataFrame, bb: pd.DataFrame) -> pd.DataFrame:
    # HLAthena MSi presentation proxy（单列，越高越强，不翻转）。HLA-aware 键 (pep,allele)。
    pc = resolve_col(raw, ['peptide', 'pep'], 'peptide')
    ac = resolve_col(raw, ['HLA_Allele', 'allele'], 'HLA_Allele')
    mc = resolve_col(raw, ['MSi', 'MSiC', 'MSi_score', 'best.MSi', 'score'], 'MSi')

    score_map = {}
    for _, r in raw.iterrows():
        key = (_norm_pep(r[pc]), _norm_allele(r[ac]))
        v = r[mc]
        score_map[key] = float(v) if pd.notna(v) and str(v).strip() not in ('', 'nan') else float('nan')

    out = map_aware(bb, score_map, 'MT_HLAthena', 'WT_HLAthena')
    _report(out, bb, ['MT_HLAthena', 'WT_HLAthena'], 'HLAthena')
    return out, 'HLAthena_official.csv'


_DISPATCH = {
    'flurry': parse_flurry,
    'nuggets': parse_nuggets,
    'seqnet': parse_seqnet,
    'transhla': parse_transhla,
    'hlathena': parse_hlathena,
}


def parse_args():
    here = Path(__file__).resolve().parent
    default_official = here.parent / 'out_official'
    p = argparse.ArgumentParser(
        description='4 个 ML 呈递工具官方结果严格回贴 bb_idx → <Tool>_official.csv')
    p.add_argument('--tool', required=True, choices=list(_DISPATCH.keys()),
                   help='flurry | nuggets | seqnet | transhla')
    p.add_argument('--raw', required=True, help='该工具原始输出 raw 文件路径')
    p.add_argument('--backbone', default=str(default_official / 'master_backbone_official.csv'),
                   help='master_backbone_official.csv')
    p.add_argument('--out-dir', default=str(default_official), help='输出目录')
    return p.parse_args()


def main():
    args = parse_args()
    bb = load_backbone(Path(args.backbone).resolve())
    raw = load_raw(Path(args.raw).resolve())
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    out_df, out_name = _DISPATCH[args.tool](raw, bb)
    out_df = out_df.sort_values('bb_idx').reset_index(drop=True)
    out_path = out_dir / out_name
    out_df.to_csv(out_path, index=False, encoding='utf-8')
    print(f'[OUT] {out_path}（{len(out_df)} 行，列 {list(out_df.columns)}）', file=sys.stderr)
    print('[DONE] parse_presml_official.py 完成', file=sys.stderr)


if __name__ == '__main__':
    main()
