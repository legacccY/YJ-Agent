#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
remetrics_fixed.py — QuantImmuBench HLA-AUDIT 修复：重算 DS2 指标
=================================================================
服务: quantimmu-bench / lever=HLA-AUDIT 修复后指标重建

读取 out_fixed/merged_all_tools_fixed.xlsx，按两种模式重算指标：

  模式 A「corrected-excl」（完全有效，无需重推理）：
    - 剔除 P101/P102（Patient_ID in {101,102}）行后，全工具全局 + per-patient Spearman
    - 输出: analysis/metrics_ds2_fixed_exclP101P102.csv
            analysis/per_patient_spearman_fixed_exclP101P102.csv

  模式 B「corrected-full」（含 P101/P102，HLA-dep 工具的 P101/P102 格子为 NaN）：
    - 包含 P101/P102 行，未重推理的格子 NaN→该工具该患者/肽级自然少样本
    - 每工具增加 reinference_pending 列（True=P101/P102 无有效分）
    - 输出: analysis/metrics_ds2_fixed_full.csv
            analysis/per_patient_spearman_fixed_full.csv

末尾打印对比表（stdout）：
  每工具 rho_buggy（旧表 max聚合/>median）vs rho_excl vs rho_full，+ p 值。
  标注：PredIG（预期显著→不显著）、TSCAPE（预期翻显著负）、
         NeoTImmuML/Repitope（HLA-agnostic 自检，应不变）。

pooling 默认 max；sub_agg 对应 per_patient_spearman_multimethod.py 的 max。

跑法:
  python scripts/remetrics_fixed.py
  python scripts/remetrics_fixed.py --sub-agg max --min-pep 3

依赖: pandas, numpy, openpyxl, sklearn, scipy
Windows 规范: 纯 numpy Spearman（禁 scipy.stats），p-value via scipy.special.betainc
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import betainc as _betainc
from sklearn.metrics import average_precision_score, roc_auc_score

# UTF-8 stdout
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

HERE = Path(__file__).resolve().parent          # scripts/
ROOT = HERE.parent                               # project/meeting/QuantImmuBench/
ANALYSIS_DIR = ROOT / 'analysis'

# ── 路径 ─────────────────────────────────────────────────────────────────────
FIXED_MERGED = HERE / 'out_fixed' / 'merged_all_tools_fixed.xlsx'
OLD_METRICS  = ANALYSIS_DIR / 'metrics_ds2_16tools.csv'
OLD_PERPT    = ANALYSIS_DIR / 'per_patient_spearman_16tools.csv'

OUT_METRICS_EXCL = ANALYSIS_DIR / 'metrics_ds2_fixed_exclP101P102.csv'
OUT_PERPT_EXCL   = ANALYSIS_DIR / 'per_patient_spearman_fixed_exclP101P102.csv'
OUT_METRICS_FULL = ANALYSIS_DIR / 'metrics_ds2_fixed_full.csv'
OUT_PERPT_FULL   = ANALYSIS_DIR / 'per_patient_spearman_fixed_full.csv'

P101P102_IDS = {101, 102}

# DS2 中 9 个患者（含 P101/P102）
ALL_PATIENTS      = [101, 102, 104, 105, 106, 107, 108, 109, 110]
ALL_PATIENTS_EXCL = [104, 105, 106, 107, 108, 109, 110]   # 剔除 P101/P102

# 排除不作为独立工具评估的 MT 列（与 per_patient_spearman_multimethod.py 一致）
EXCLUDE_MT_COLS = {
    'MT_FullPeptide', 'MT_Subpeptide',
    'MT_NOAH', 'MT_NetCleave',
    'MT_Stab_peptide', 'MT_TCR_contact',
}

# 重点关注工具（对比标注）
HLA_AGNOSTIC_TOOLS = {'NeoTImmuML', 'Repitope'}
NOTE_TOOLS = {
    'PredIG':      '预期 buggy 显著 → excl 不显著',
    'TSCAPE':      '预期 excl 翻显著负',
    'NeoTImmuML':  'HLA-agnostic 自检 (应 rho_excl ≈ rho_buggy 非P101P102子集)',
    'Repitope':    'HLA-agnostic 自检 (应 rho_excl ≈ rho_buggy 非P101P102子集)',
    'IMPROVE':     '预期 excl 仍显著',
}


# ============================================================
# 统计工具（纯 numpy + scipy.special，禁 scipy.stats）
# ============================================================

def spearman_np(x, y) -> float:
    """纯 numpy Spearman（禁 scipy.stats，防 OMP Error #15）。"""
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    m = ~(np.isnan(x) | np.isnan(y))
    x, y = x[m], y[m]
    n = len(x)
    if n < 3 or len(np.unique(x)) < 2 or len(np.unique(y)) < 2:
        return np.nan
    rx = pd.Series(x).rank().values
    ry = pd.Series(y).rank().values
    rx -= rx.mean()
    ry -= ry.mean()
    denom = np.sqrt((rx ** 2).sum() * (ry ** 2).sum())
    return float((rx * ry).sum() / denom) if denom > 0 else np.nan


def spearman_pval(rho: float, n: int) -> float:
    """两尾 t 检验 p-value for Spearman（scipy.special.betainc，非 scipy.stats）。"""
    if n <= 2 or np.isnan(rho) or abs(rho) >= 1.0 - 1e-10:
        return np.nan
    t = rho * np.sqrt(n - 2) / np.sqrt(max(1.0 - rho ** 2, 1e-15))
    df = float(n - 2)
    x = df / (df + t ** 2)
    p_one = 0.5 * float(_betainc(df / 2.0, 0.5, x))
    return float(2.0 * p_one)


def fisherz_weighted(rhos, ns):
    """Fisher-z 固定效应加权均值 + 95% CI。返回 (rho_bar, ci_lo, ci_hi, n_used, n_dropped)。"""
    FISHER_CLIP = 0.9999
    FISHER_MIN_N = 3

    rhos = np.asarray(rhos, float)
    ns   = np.asarray(ns, float)
    valid = ~np.isnan(rhos)
    rhos, ns = rhos[valid], ns[valid]
    keep = ns > FISHER_MIN_N
    n_dropped = int((~keep).sum())
    rhos_k, ns_k = rhos[keep], ns[keep]
    if len(rhos_k) == 0:
        return np.nan, np.nan, np.nan, 0, n_dropped
    rhos_k = np.clip(rhos_k, -FISHER_CLIP, FISHER_CLIP)
    z = np.arctanh(rhos_k)
    w = (ns_k - 3) / (1 + rhos_k ** 2 / 2)
    w = np.where(w > 0, w, 1e-9)
    z_bar = np.sum(w * z) / np.sum(w)
    var_z  = 1.0 / np.sum(w)
    ci_lo = np.tanh(z_bar - 1.96 * np.sqrt(var_z))
    ci_hi = np.tanh(z_bar + 1.96 * np.sqrt(var_z))
    return float(np.tanh(z_bar)), float(ci_lo), float(ci_hi), int(len(rhos_k)), n_dropped


def col_to_toolname(col: str) -> str:
    """MT_列名 → 工具短名（IMPROVE 特例）。"""
    name = col[3:]
    if name.startswith('IMPROVE'):
        return 'IMPROVE'
    return name


def agg_pep_scores(ds2: pd.DataFrame, col: str, sub_agg: str = 'max') -> dict:
    """groupby(Peptide_ID) 聚合子肽分数 → {pid: {max, mean, top3mean}}。"""
    valid = ds2[ds2[col].notna()][['Peptide_ID', col]].copy()
    out = {}
    for pid, grp in valid.groupby('Peptide_ID')[col]:
        arr = grp.values.astype(float)
        k = min(3, len(arr))
        out[pid] = {
            'max':      round(float(arr.max()), 8),
            'mean':     round(float(arr.mean()), 8),
            'top3mean': round(float(np.sort(arr)[-k:].mean()), 8),
        }
    return out


# ============================================================
# 全局指标计算
# ============================================================

def compute_global_metrics(
    ds2: pd.DataFrame,
    sub_agg: str = 'max',
    pending_set: set = None,
    mode: str = '',
) -> pd.DataFrame:
    """
    对 DS2 子集，对每工具 × 3 聚合 × 3 阈值计算 AUC/AUPRC/Spearman。
    pending_set: 工具名集合，标记 pending_DTU_consent。
    mode: 附加在输出列中（用于区分 excl/full）。
    """
    if pending_set is None:
        pending_set = set()

    elispot_pep = (
        ds2.drop_duplicates('Peptide_ID')[['Peptide_ID', 'Elispot']]
        .set_index('Peptide_ID')['Elispot']
    )

    mt_cols = []
    for c in ds2.columns:
        if not c.startswith('MT_') or c in EXCLUDE_MT_COLS:
            continue
        ds2[c] = pd.to_numeric(ds2[c], errors='coerce')
        if ds2[c].notna().any():
            mt_cols.append(c)

    if not mt_cols:
        print('[compute_global_metrics] 无有效 MT_* 工具列', file=sys.stderr)
        return pd.DataFrame()

    rows = []
    for mt_col in mt_cols:
        tool_name = col_to_toolname(mt_col)
        ps = agg_pep_scores(ds2, mt_col, sub_agg)
        if not ps:
            continue
        pids = list(ps.keys())
        el = elispot_pep.reindex(pids).values.astype(float)
        valid_m = ~np.isnan(el)
        pids = [p for p, v in zip(pids, valid_m) if v]
        el = el[valid_m]
        if len(pids) == 0:
            continue
        med = float(np.median(el))
        is_pending = tool_name in pending_set

        for agg in ('max', 'mean', 'top3mean'):
            sc = np.array([ps[p][agg] for p in pids])
            rho = spearman_np(sc, el)
            pval = spearman_pval(rho, len(pids))

            for thr_name, thr in [('>0', 0.0), ('>10', 10.0), ('>median', med)]:
                labs = (el > thr).astype(int)
                n_pos = int(labs.sum())
                n_neg = int((1 - labs).sum())
                if n_pos > 0 and n_neg > 0:
                    auc = float(roc_auc_score(labs, sc))
                    ap  = float(average_precision_score(labs, sc))
                else:
                    auc = np.nan
                    ap  = np.nan

                rows.append({
                    'Tool':               tool_name,
                    'Aggregation':        agg,
                    'Threshold':          thr_name,
                    'n_pep':              len(pids),
                    'n_pos':              n_pos,
                    'n_neg':              n_neg,
                    'AUC_ROC':            round(auc, 4) if not np.isnan(auc) else np.nan,
                    'AUPRC':              round(ap, 4)  if not np.isnan(ap)  else np.nan,
                    'Spearman_rho':       round(rho, 4) if not np.isnan(rho) else np.nan,
                    'Spearman_pval':      round(pval, 4) if not np.isnan(pval) else np.nan,
                    'pending_DTU_consent': is_pending,
                })

    return pd.DataFrame(rows)


# ============================================================
# Per-patient 指标计算
# ============================================================

def compute_per_patient(
    ds2: pd.DataFrame,
    patient_list: list,
    sub_agg: str = 'max',
    min_pep: int = 3,
    add_reinference_pending: bool = False,
    fixed_ds2_all: pd.DataFrame = None,
) -> pd.DataFrame:
    """
    Per-patient Spearman + 7 种聚合。
    patient_list: 哪些患者参与聚合（excl 模式用 ALL_PATIENTS_EXCL）。
    add_reinference_pending: True→ 增加 reinference_pending 列（full 模式用）。
    fixed_ds2_all: full DS2（含 P101/P102），用于判断 P101/P102 是否有有效分。
    """
    mt_cols = []
    for c in ds2.columns:
        if not c.startswith('MT_') or c in EXCLUDE_MT_COLS:
            continue
        ds2[c] = pd.to_numeric(ds2[c], errors='coerce')
        if ds2[c].notna().any():
            mt_cols.append(c)

    tools = {col_to_toolname(c): c for c in mt_cols}

    # Patient_ID 列
    pcol = next((c for c in ['Patient_ID', 'Patient', 'patient_id'] if c in ds2.columns), None)
    if pcol is None:
        print('[per-patient][WARN] 未找到患者列', file=sys.stderr)
        return pd.DataFrame()

    ds2 = ds2.copy()
    ds2['_pat'] = ds2[pcol].astype(str)

    pep_info = (
        ds2.drop_duplicates('Peptide_ID')[['Peptide_ID', '_pat', 'Elispot']]
        .set_index('Peptide_ID')
    )

    results = []
    for tool_name, mt_col in tools.items():
        valid_sub = ds2[ds2[mt_col].notna()][['Peptide_ID', mt_col]].copy()
        if valid_sub.empty:
            continue
        pep_scores = (
            valid_sub.groupby('Peptide_ID')[mt_col]
            .agg(lambda arr: _agg_max(arr.values, sub_agg))
            .rename('peptide_score')
        )
        pep_df = (
            pep_scores.to_frame()
            .join(pep_info[['_pat', 'Elispot']], how='inner')
            .dropna(subset=['Elispot', 'peptide_score'])
        )
        if pep_df.empty:
            continue

        rho_global = spearman_np(pep_df['peptide_score'].values, pep_df['Elispot'].values)

        # per-patient
        pat_rhos, pat_ns = {}, {}
        for pat, g in pep_df.groupby('_pat'):
            n_pep = len(g)
            rho   = spearman_np(g['peptide_score'].values, g['Elispot'].values) \
                    if n_pep >= min_pep else np.nan
            pat_rhos[str(pat)] = rho
            pat_ns[str(pat)]   = n_pep

        # 仅用 patient_list 中的患者做聚合
        valid_pairs = [
            (pat_rhos[str(p)], pat_ns[str(p)])
            for p in patient_list
            if str(p) in pat_rhos and not np.isnan(pat_rhos[str(p)])
        ]
        if not valid_pairs:
            continue

        rhos_arr = np.array([v[0] for v in valid_pairs])
        ns_arr   = np.array([v[1] for v in valid_pairs], float)
        n_valid  = len(rhos_arr)

        fz_rho, fz_ci_lo, fz_ci_hi, fz_n_used, fz_n_drop = fisherz_weighted(rhos_arr, ns_arr)
        med     = float(np.median(rhos_arr))
        smean   = float(np.mean(rhos_arr))
        hs      = float(np.sum(ns_arr * rhos_arr) / np.sum(ns_arr)) if np.sum(ns_arr) > 0 else np.nan

        def _r4(v):
            try:
                fv = float(v)
                return round(fv, 4) if not np.isnan(fv) else np.nan
            except Exception:
                return np.nan

        row = {
            'Tool':               tool_name,
            'n_patients':         n_valid,
            'rho_global':         _r4(rho_global),
            'fisherz_weighted':   _r4(fz_rho),
            'fisherz_ci_lo':      _r4(fz_ci_lo),
            'fisherz_ci_hi':      _r4(fz_ci_hi),
            'fisherz_n_used':     fz_n_used,
            'fisherz_n_dropped':  fz_n_drop,
            'median':             _r4(med),
            'simple_mean':        _r4(smean),
            'hs_weighted':        _r4(hs),
            'rho_min':            _r4(float(rhos_arr.min())),
            'rho_max':            _r4(float(rhos_arr.max())),
            'rho_std':            _r4(float(rhos_arr.std(ddof=1))) if len(rhos_arr) > 1 else np.nan,
        }

        # 各患者 rho / n（包括患者列表中所有患者，不管是否参与聚合）
        for pid in patient_list:
            pid_s = str(pid)
            rho_v = pat_rhos.get(pid_s, np.nan)
            row[f'rho_p{pid_s}'] = _r4(rho_v)
            row[f'n_p{pid_s}']   = pat_ns.get(pid_s, 0)

        # reinference_pending（full 模式：P101/P102 是否有有效分）
        if add_reinference_pending and fixed_ds2_all is not None:
            pp_rows = fixed_ds2_all[fixed_ds2_all['Patient_ID'].isin(P101P102_IDS)]
            pp_valid = pp_rows[mt_col].notna().any() if mt_col in pp_rows.columns else False
            row['reinference_pending'] = not pp_valid
        elif add_reinference_pending:
            row['reinference_pending'] = np.nan

        results.append(row)

    return pd.DataFrame(results) if results else pd.DataFrame()


def _agg_max(arr, method='max'):
    """子肽分数聚合（_agg_array 的 inline 简化版）。"""
    arr = arr[~np.isnan(arr.astype(float))]
    if len(arr) == 0:
        return np.nan
    arr = arr.astype(float)
    if method == 'max':
        return round(float(arr.max()), 8)
    if method == 'mean':
        return round(float(arr.mean()), 8)
    if method == 'top3mean':
        k = min(3, len(arr))
        return round(float(np.sort(arr)[-k:].mean()), 8)
    return round(float(arr.max()), 8)


# ============================================================
# 对比打印
# ============================================================

def print_comparison(
    metrics_excl: pd.DataFrame,
    metrics_full: pd.DataFrame,
    old_metrics_path: Path,
    sub_agg: str = 'max',
) -> None:
    """打印 rho_buggy vs rho_excl vs rho_full 对比表。"""
    print('\n' + '=' * 110)
    print('=== 对比表: rho_buggy (旧, 含 P101/P102 bug 等位) vs rho_corrected_excl vs rho_corrected_full ===')
    print('    Aggregation=max, Threshold=>median')
    print('=' * 110)

    # 旧表读取
    if old_metrics_path.exists():
        try:
            old_df = pd.read_csv(old_metrics_path, comment='#')
            old_sub = old_df[
                (old_df['Aggregation'] == sub_agg) & (old_df['Threshold'] == '>median')
            ][['Tool', 'Spearman_rho', 'Spearman_pval']].set_index('Tool')
        except Exception:
            old_sub = pd.DataFrame()
    else:
        old_sub = pd.DataFrame()

    # excl 子集
    excl_sub = pd.DataFrame()
    if not metrics_excl.empty:
        excl_sub = metrics_excl[
            (metrics_excl['Aggregation'] == sub_agg) & (metrics_excl['Threshold'] == '>median')
        ][['Tool', 'Spearman_rho', 'Spearman_pval']].set_index('Tool')

    # full 子集
    full_sub = pd.DataFrame()
    if not metrics_full.empty:
        full_sub = metrics_full[
            (metrics_full['Aggregation'] == sub_agg) & (metrics_full['Threshold'] == '>median')
        ][['Tool', 'Spearman_rho', 'Spearman_pval']].set_index('Tool')

    all_tools = sorted(set(
        list(old_sub.index if not old_sub.empty else []) +
        list(excl_sub.index if not excl_sub.empty else []) +
        list(full_sub.index if not full_sub.empty else [])
    ))

    header = f"{'Tool':28s}  {'rho_buggy':>10}  {'p_buggy':>8}  {'rho_excl':>10}  {'p_excl':>8}  {'rho_full':>10}  {'p_full':>8}  Note"
    print(header)
    print('-' * 110)

    for tool in all_tools:
        def _g(df, tool, col):
            if df.empty or tool not in df.index:
                return np.nan
            v = df.loc[tool, col]
            return float(v) if not pd.isna(v) else np.nan

        rho_b = _g(old_sub,  tool, 'Spearman_rho')
        p_b   = _g(old_sub,  tool, 'Spearman_pval')
        rho_e = _g(excl_sub, tool, 'Spearman_rho')
        p_e   = _g(excl_sub, tool, 'Spearman_pval')
        rho_f = _g(full_sub, tool, 'Spearman_rho')
        p_f   = _g(full_sub, tool, 'Spearman_pval')

        def _fmt_rho(v): return f'{v:+.4f}' if not np.isnan(v) else '     NaN'
        def _fmt_p(v):
            if np.isnan(v): return '     NaN'
            sig = '*' if v < 0.05 else ' '
            return f'{v:.4f}{sig}'

        note = NOTE_TOOLS.get(tool, '')
        print(
            f'  {tool:26s}  {_fmt_rho(rho_b):>10}  {_fmt_p(p_b):>8}  '
            f'{_fmt_rho(rho_e):>10}  {_fmt_p(p_e):>8}  '
            f'{_fmt_rho(rho_f):>10}  {_fmt_p(p_f):>8}  {note}'
        )

    print('=' * 110)
    print('* p < 0.05 标 *；rho_excl 为核心有效结论（无需重推理）')
    print('注: rho_full P101/P102 HLA-dep 工具为 NaN 行减少→ n_pep 减少→ rho 不稳定，参考为主')


# ============================================================
# main
# ============================================================

def parse_args():
    parser = argparse.ArgumentParser(description='QuantImmuBench HLA-AUDIT 修复后指标重算')
    parser.add_argument('--input', default=None, help='fixed merged xlsx 路径（缺省自动找）')
    parser.add_argument('--sub-agg', choices=['max', 'mean', 'top3mean'], default='max')
    parser.add_argument('--min-pep', type=int, default=3, help='per-patient 最少肽数（默认 3）')
    return parser.parse_args()


def main():
    args = parse_args()
    sub_agg = args.sub_agg
    min_pep = args.min_pep

    # ── 确定输入路径 ──────────────────────────────────────────────────────────
    xlsx_path = Path(args.input).resolve() if args.input else FIXED_MERGED
    if not xlsx_path.exists():
        print(f'[ERR] fixed merged xlsx 不存在: {xlsx_path}', file=sys.stderr)
        print('      请先运行 python scripts/remerge_fixed.py 生成该文件', file=sys.stderr)
        sys.exit(1)

    print(f'[INFO] 输入: {xlsx_path}', file=sys.stderr)
    print(f'[INFO] sub_agg={sub_agg}  min_pep={min_pep}', file=sys.stderr)

    # ── 读取 ─────────────────────────────────────────────────────────────────
    df = pd.read_excel(xlsx_path)
    df.columns = [c.strip() for c in df.columns]
    print(f'[INFO] 读入 {len(df)} 行 × {len(df.columns)} 列', file=sys.stderr)

    if 'Dataset' not in df.columns:
        print("[ERR] 缺 'Dataset' 列", file=sys.stderr)
        sys.exit(1)

    ds2_all = df[df['Dataset'] == 'DS2'].copy()
    if ds2_all.empty:
        print('[ERR] DS2 子集为空', file=sys.stderr)
        sys.exit(1)
    print(f'[INFO] DS2 行数: {len(ds2_all)}', file=sys.stderr)

    pp_mask_ds2 = ds2_all['Patient_ID'].isin(P101P102_IDS)
    ds2_excl = ds2_all[~pp_mask_ds2].copy()
    print(
        f'[INFO] DS2 中 P101/P102={pp_mask_ds2.sum()}  excl 后={len(ds2_excl)}',
        file=sys.stderr,
    )

    # ── DTU pending set ───────────────────────────────────────────────────────
    pending_path = HERE / 'out' / 'newtools' / 'PENDING_DTU_tools.txt'
    pending_set = set()
    if pending_path.exists():
        pending_set = {l.strip() for l in pending_path.read_text(encoding='utf-8').splitlines() if l.strip()}
        print(f'[INFO] DTU pending: {pending_set}', file=sys.stderr)

    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)

    # ==================================================================
    # 模式 A: corrected-excl
    # ==================================================================
    print('\n' + '=' * 60, file=sys.stderr)
    print('=== 模式 A: corrected-excl（剔除 P101/P102）===', file=sys.stderr)
    print('=' * 60, file=sys.stderr)

    metrics_excl = compute_global_metrics(ds2_excl.copy(), sub_agg, pending_set, mode='excl')
    if not metrics_excl.empty:
        with open(OUT_METRICS_EXCL, 'w', encoding='utf-8', newline='') as fo:
            fo.write(
                '# QuantImmuBench DS2 HLA-AUDIT 修复指标 | 模式=corrected-excl(剔除P101/P102)\n'
                f'# sub_agg={sub_agg} | 无需重推理，完全有效\n'
            )
            metrics_excl.to_csv(fo, index=False)
        print(f'[DONE-A] 全局指标 → {OUT_METRICS_EXCL}  shape={metrics_excl.shape}', file=sys.stderr)

        # 简要排行
        print('\n[excl] AUC_ROC 排行 (max, >median):')
        sub = metrics_excl[
            (metrics_excl['Aggregation'] == 'max') & (metrics_excl['Threshold'] == '>median')
        ][['Tool', 'n_pep', 'AUC_ROC', 'AUPRC', 'Spearman_rho', 'Spearman_pval']]
        print(sub.sort_values('AUC_ROC', ascending=False).to_string(index=False))
    else:
        print('[WARN-A] 全局指标为空', file=sys.stderr)

    print('\n=== 模式 A per-patient ===', file=sys.stderr)
    perpt_excl = compute_per_patient(
        ds2_excl.copy(), ALL_PATIENTS_EXCL, sub_agg, min_pep,
        add_reinference_pending=False,
    )
    if not perpt_excl.empty:
        perpt_excl.to_csv(OUT_PERPT_EXCL, index=False, encoding='utf-8')
        print(f'[DONE-A] per-patient → {OUT_PERPT_EXCL}  shape={perpt_excl.shape}', file=sys.stderr)
        print('\n[excl] Fisher-z 排行:')
        rank = perpt_excl[['Tool', 'n_patients', 'rho_global', 'fisherz_weighted',
                             'fisherz_ci_lo', 'fisherz_ci_hi', 'median']].sort_values(
            'fisherz_weighted', ascending=False)
        print(rank.to_string(index=False))
    else:
        print('[WARN-A] per-patient 为空', file=sys.stderr)

    # ==================================================================
    # 模式 B: corrected-full
    # ==================================================================
    print('\n' + '=' * 60, file=sys.stderr)
    print('=== 模式 B: corrected-full（含 P101/P102）===', file=sys.stderr)
    print('=' * 60, file=sys.stderr)

    metrics_full = compute_global_metrics(ds2_all.copy(), sub_agg, pending_set, mode='full')
    if not metrics_full.empty:
        # reinference_pending 列：该工具在 P101/P102 行是否全为 NaN
        def _pp_has_score(tool_name: str) -> bool:
            mt_col = 'MT_' + tool_name if tool_name != 'IMPROVE' else 'MT_IMPROVE_mean_prediction_rf'
            if mt_col not in ds2_all.columns:
                return False
            pp_rows = ds2_all[ds2_all['Patient_ID'].isin(P101P102_IDS)]
            return bool(pp_rows[mt_col].notna().any())

        metrics_full['reinference_pending'] = metrics_full['Tool'].apply(
            lambda t: not _pp_has_score(t)
        )

        with open(OUT_METRICS_FULL, 'w', encoding='utf-8', newline='') as fo:
            fo.write(
                '# QuantImmuBench DS2 HLA-AUDIT 修复指标 | 模式=corrected-full(含P101/P102)\n'
                f'# sub_agg={sub_agg} | P101/P102 HLA-dep工具格子为NaN(待重推理)\n'
                '# reinference_pending=True表示该工具P101/P102无有效分(待Phase B重跑)\n'
            )
            metrics_full.to_csv(fo, index=False)
        print(f'[DONE-B] 全局指标 → {OUT_METRICS_FULL}  shape={metrics_full.shape}', file=sys.stderr)

        print('\n[full] AUC_ROC 排行 (max, >median):')
        sub = metrics_full[
            (metrics_full['Aggregation'] == 'max') & (metrics_full['Threshold'] == '>median')
        ][['Tool', 'n_pep', 'AUC_ROC', 'AUPRC', 'Spearman_rho', 'Spearman_pval', 'reinference_pending']]
        print(sub.sort_values('AUC_ROC', ascending=False).to_string(index=False))
    else:
        print('[WARN-B] 全局指标为空', file=sys.stderr)

    print('\n=== 模式 B per-patient ===', file=sys.stderr)
    perpt_full = compute_per_patient(
        ds2_all.copy(), ALL_PATIENTS, sub_agg, min_pep,
        add_reinference_pending=True,
        fixed_ds2_all=ds2_all,
    )
    if not perpt_full.empty:
        perpt_full.to_csv(OUT_PERPT_FULL, index=False, encoding='utf-8')
        print(f'[DONE-B] per-patient → {OUT_PERPT_FULL}  shape={perpt_full.shape}', file=sys.stderr)
        print('\n[full] Fisher-z 排行:')
        rank = perpt_full[['Tool', 'n_patients', 'rho_global', 'fisherz_weighted',
                             'fisherz_ci_lo', 'fisherz_ci_hi', 'median']].sort_values(
            'fisherz_weighted', ascending=False)
        print(rank.to_string(index=False))
    else:
        print('[WARN-B] per-patient 为空', file=sys.stderr)

    # ==================================================================
    # 对比表（stdout）
    # ==================================================================
    print_comparison(metrics_excl, metrics_full, OLD_METRICS, sub_agg)

    print(f'\n[DONE] remetrics_fixed.py 完成', file=sys.stderr)
    print(f'  输出文件:', file=sys.stderr)
    for p in [OUT_METRICS_EXCL, OUT_PERPT_EXCL, OUT_METRICS_FULL, OUT_PERPT_FULL]:
        exists = '(待写)' if not p.exists() else '(已写)'
        print(f'    {p} {exists}', file=sys.stderr)


if __name__ == '__main__':
    main()
