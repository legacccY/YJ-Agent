#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
merge_metrics_NNtools.py — QuantImmuBench 全工具指标重算（自动 NN）
================================================================
服务: quantimmu-bench / lever=扩张工具后 benchmark 指标重建

依赖上游: scripts/merge_newtools.py（先跑，产出 merged_all_tools_<NN>tools.xlsx）

输入:
  --input   合并表 xlsx 路径
            默认自动寻找 scripts/out/ 下最高 NN 的 merged_all_tools_<NN>tools.xlsx
            退 9tools → 8tools
  --sub-agg 子肽聚合方式 max/mean/top3mean（默认 max，全局 Spearman 与 per-patient 统一）
  --min-pep per-patient Spearman 最少肽数（默认 3）

输出:
  analysis/metrics_ds2_<NN>tools.csv        DS2 全工具 AUC/AUPRC/Spearman 指标表
  analysis/per_patient_spearman_<NN>tools.csv  per-patient 7 法聚合表

每工具指标行 = Tool × Aggregation(max/mean/top3mean) × Threshold(>0/>10/>median)
列: Tool, Aggregation, Threshold, n_pep, n_pos, n_neg,
    AUC_ROC, AUPRC, Spearman_rho, Spearman_pval, pending_DTU_consent

per-patient 指标复用 per_patient_spearman_multimethod.py 的函数（import 方式）:
  spearman_np / fisherz_weighted / hs_weighted / geometric_mean_rho /
  power_mean_p2 / uwls3_agg / find_patient_col / patient_from_peptide_id /
  _agg_array / col_to_toolname

Windows 规范:
  - 禁 scipy.stats（OMP Error #15）
  - Spearman 用纯 numpy 实现（spearman_np，来自 per_patient 模块）
  - p-value 用 scipy.special.betainc（非 scipy.stats，无 OMP 风险）
  - 禁 scipy.stats.spearmanr / pearsonr 等

跑法:
  python analysis/merge_metrics_NNtools.py
  python analysis/merge_metrics_NNtools.py --input scripts/out/merged_all_tools_11tools.xlsx
  python analysis/merge_metrics_NNtools.py --sub-agg mean --min-pep 4

排他:
  MT_FullPeptide / MT_Subpeptide / MT_NOAH / MT_NetCleave /
  MT_Stab_peptide / MT_TCR_contact  不作为独立工具评估（和 per_patient 脚本一致）
"""

import argparse
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.special import betainc as _betainc
from sklearn.metrics import average_precision_score, roc_auc_score

# UTF-8 stdout（Windows 必要）
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

# ── 导入 per_patient 模块的纯 numpy 工具函数 ──────────────────────────────────
sys.path.insert(0, str(HERE))
try:
    from per_patient_spearman_multimethod import (
        ALL_PATIENTS,
        FISHER_CLIP,
        FISHER_MIN_N,
        MIN_PEP_DEFAULT,
        PATIENT_COL_CANDIDATES,
        _agg_array,
        col_to_toolname,
        find_patient_col,
        fisherz_weighted,
        geometric_mean_rho,
        hs_weighted,
        patient_from_peptide_id,
        power_mean_p2,
        spearman_np,
        uwls3_agg,
    )
    _PP_IMPORTED = True
except ImportError as _e:
    _PP_IMPORTED = False
    print(
        f'[WARN] 无法 import per_patient_spearman_multimethod: {_e}\n'
        '       per-patient 分析将跳过。请确认该脚本在 analysis/ 目录。',
        file=sys.stderr,
    )

# ── 排除列（与 per_patient 脚本保持一致）────────────────────────────────────
EXCLUDE_MT_COLS = {
    'MT_FullPeptide', 'MT_Subpeptide',
    'MT_NOAH', 'MT_NetCleave',
    'MT_Stab_peptide', 'MT_TCR_contact',
}


# ── Spearman p-value（纯 numpy + scipy.special，禁 scipy.stats）──────────────
def _spearman_pval_np(rho: float, n: int) -> float:
    """
    两尾 t 检验 p-value for Spearman rho，自由度 n-2。
    使用 scipy.special.betainc（非 scipy.stats，无 OMP 风险）。
    参考: t = rho*sqrt(n-2)/sqrt(1-rho^2),  p = 2*P(T_{n-2} > |t|)
          P via regularized incomplete beta: I(df/(df+t^2); df/2, 0.5)
    """
    if n <= 2 or np.isnan(rho) or abs(rho) >= 1.0 - 1e-10:
        return np.nan
    t = rho * np.sqrt(n - 2) / np.sqrt(max(1.0 - rho ** 2, 1e-15))
    df = float(n - 2)
    x = df / (df + t ** 2)
    p_one = 0.5 * float(_betainc(df / 2.0, 0.5, x))
    return float(2.0 * p_one)


# ── 自动寻找最新 merged xlsx ─────────────────────────────────────────────────
def resolve_xlsx(root: Path, arg_input) -> Path:
    """
    优先使用 --input 指定路径；
    否则自动找 scripts/out/ 下 NN 最大的 merged_all_tools_<NN>tools.xlsx。
    退而选 9tools → 8tools。
    """
    out_dir = root / 'scripts' / 'out'
    if arg_input is not None:
        p = Path(arg_input)
        if not p.is_absolute():
            p = root / p
        if p.exists():
            return p
        raise SystemExit(f'[ERR] 指定输入不存在: {p}')

    # 自动扫最大 NN
    candidates = sorted(out_dir.glob('merged_all_tools_*tools.xlsx'))
    if candidates:
        # 提取 NN，取最大
        def _nn(p):
            m = re.search(r'_(\d+)tools', p.name)
            return int(m.group(1)) if m else 0
        best = max(candidates, key=_nn)
        return best

    raise SystemExit(
        f'[ERR] 找不到 merged_all_tools_*tools.xlsx (目录: {out_dir})'
    )


def parse_nn_from_path(xlsx_path: Path) -> int:
    """从文件名提取 NN: merged_all_tools_11tools.xlsx -> 11。"""
    m = re.search(r'_(\d+)tools', xlsx_path.name)
    return int(m.group(1)) if m else 9


# ── 子肽聚合 → 肽级分数 ──────────────────────────────────────────────────────
def agg_pep_scores(ds2: pd.DataFrame, col: str, sub_agg: str) -> dict:
    """
    groupby(Peptide_ID) 对 col 聚合，返回 {pid: {max, mean, top3mean}} dict。
    只含 col 非空的行。
    """
    valid = ds2[ds2[col].notna()][['Peptide_ID', col]].copy()
    out = {}
    for pid, grp in valid.groupby('Peptide_ID')[col]:
        arr = grp.values.astype(float)
        k = min(3, len(arr))
        out[pid] = {
            'max': float(arr.max()),
            'mean': float(arr.mean()),
            'top3mean': float(np.sort(arr)[-k:].mean()),
        }
    return out


# ── 全局指标计算 ─────────────────────────────────────────────────────────────
def compute_global_metrics(df: pd.DataFrame, nn: int, sub_agg: str,
                            pending_set: set) -> pd.DataFrame:
    """
    对 df 的 DS2 子集，对每工具 × 3 聚合 × 3 阈值 计算 AUC/AUPRC/Spearman。
    返回 DataFrame。
    """
    ds2 = df[df['Dataset'] == 'DS2'].copy()
    if ds2.empty:
        raise SystemExit('[ERR] DS2 子集为空，请检查 Dataset 列')

    # 肽级 Elispot
    ds2_pep = (
        ds2.drop_duplicates('Peptide_ID')[['Peptide_ID', 'Elispot']]
        .set_index('Peptide_ID')
    )
    elispot = ds2_pep['Elispot']

    # 检测工具列
    mt_cols = []
    for c in ds2.columns:
        if not c.startswith('MT_') or c in EXCLUDE_MT_COLS:
            continue
        ds2[c] = pd.to_numeric(ds2[c], errors='coerce')
        if ds2[c].notna().any():
            mt_cols.append(c)

    if not mt_cols:
        raise SystemExit('[ERR] 未找到有效数值 MT_* 工具列')

    print(f'[INFO] 检测到 {len(mt_cols)} 个工具列: {[c[3:] for c in mt_cols]}',
          file=sys.stderr)

    rows = []
    for mt_col in mt_cols:
        tool_name = col_to_toolname(mt_col) if _PP_IMPORTED else mt_col[3:]

        ps = agg_pep_scores(ds2, mt_col, sub_agg)
        if not ps:
            print(f'[WARN] {tool_name}: 无有效分数，跳过', file=sys.stderr)
            continue

        pids = list(ps.keys())
        el = elispot.reindex(pids).values.astype(float)
        valid_mask = ~np.isnan(el)
        pids = [p for p, v in zip(pids, valid_mask) if v]
        el = el[valid_mask]
        if len(pids) == 0:
            continue

        med = float(np.median(el))
        is_pending = tool_name in pending_set

        for agg in ('max', 'mean', 'top3mean'):
            sc = np.array([ps[p][agg] for p in pids])

            # 全局 Spearman（纯 numpy，禁 scipy.stats）
            rho = spearman_np(sc, el) if _PP_IMPORTED else _spearman_np_fallback(sc, el)
            pval = _spearman_pval_np(rho, len(pids))

            for thr_name, thr in [('>0', 0.0), ('>10', 10.0), ('>median', med)]:
                labs = (el > thr).astype(int)
                n_pos = int(labs.sum())
                n_neg = int((1 - labs).sum())

                if n_pos > 0 and n_neg > 0:
                    auc = float(roc_auc_score(labs, sc))
                    ap = float(average_precision_score(labs, sc))
                else:
                    auc = np.nan
                    ap = np.nan

                rows.append({
                    'Tool': tool_name,
                    'Aggregation': agg,
                    'Threshold': thr_name,
                    'n_pep': len(pids),
                    'n_pos': n_pos,
                    'n_neg': n_neg,
                    'AUC_ROC': round(auc, 4) if not np.isnan(auc) else np.nan,
                    'AUPRC': round(ap, 4) if not np.isnan(ap) else np.nan,
                    'Spearman_rho': round(rho, 4) if not np.isnan(rho) else np.nan,
                    'Spearman_pval': round(pval, 4) if not np.isnan(pval) else np.nan,
                    'pending_DTU_consent': is_pending,
                })

    return pd.DataFrame(rows)


def _spearman_np_fallback(x, y):
    """备用纯 numpy Spearman（per_patient 模块 import 失败时使用）。"""
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


# ── per-patient 分析（复用 per_patient_spearman_multimethod 函数）──────────────
def run_per_patient(df: pd.DataFrame, nn: int, out_dir: Path,
                    sub_agg: str, min_pep: int) -> Path:
    """
    复用 per_patient_spearman_multimethod.py 的函数，对 df 运行 per-patient 7 法聚合。
    输出到 out_dir/per_patient_spearman_<NN>tools.csv。
    返回输出路径（或 None 若 import 失败）。
    """
    if not _PP_IMPORTED:
        print('[WARN] per_patient 模块未加载，跳过 per-patient 分析', file=sys.stderr)
        return None

    ds2 = df[df['Dataset'] == 'DS2'].copy()
    if ds2.empty:
        print('[WARN] DS2 为空，跳过 per-patient 分析', file=sys.stderr)
        return None

    # ── DS2 工具列检测（与全局指标一致的 EXCLUDE）────────────────────────────
    mt_cols = []
    for c in ds2.columns:
        if not c.startswith('MT_') or c in EXCLUDE_MT_COLS:
            continue
        ds2[c] = pd.to_numeric(ds2[c], errors='coerce')
        if ds2[c].notna().any():
            mt_cols.append(c)

    tools = {col_to_toolname(c): c for c in mt_cols}
    print(f'[per-patient] {len(tools)} 个工具: {list(tools.keys())}', file=sys.stderr)

    # ── 患者 ID 处理 ──────────────────────────────────────────────────────────
    pcol = find_patient_col(ds2)
    if pcol is None:
        print('[per-patient][warn] 未找到患者列，从 Peptide_ID 反解', file=sys.stderr)

    def get_patient(row):
        if pcol is not None and pd.notna(row[pcol]):
            return str(row[pcol])
        return patient_from_peptide_id(row['Peptide_ID'])

    ds2 = ds2.copy()
    ds2['_patient'] = ds2.apply(get_patient, axis=1)
    ds2 = ds2.dropna(subset=['_patient'])

    patients_in_data = sorted(ds2['_patient'].unique(),
                               key=lambda x: int(x) if str(x).isdigit() else 0)
    print(f'[per-patient] DS2 患者 ({len(patients_in_data)}): {patients_in_data}',
          file=sys.stderr)

    # 肽级元信息
    pep_info = (
        ds2.drop_duplicates('Peptide_ID')[['Peptide_ID', '_patient', 'Elispot']]
        .set_index('Peptide_ID')
    )

    results = []
    print('\n' + '=' * 95, file=sys.stderr)
    print(f"{'Tool':22s}  {'rho_global':>10}  {'fisher_z':>9}  "
          f"{'CI':>14}  {'median':>8}  {'n_valid_pat':>11}  {'global-fisherz':>14}",
          file=sys.stderr)
    print('=' * 95, file=sys.stderr)

    for tool_name, mt_col in tools.items():
        valid_sub = ds2[ds2[mt_col].notna()][['Peptide_ID', mt_col]].copy()
        if valid_sub.empty:
            print(f'[per-patient][warn] {tool_name}: 无有效分数，跳过', file=sys.stderr)
            continue

        pep_scores = (
            valid_sub.groupby('Peptide_ID')[mt_col]
            .agg(lambda arr: _agg_array(arr.values, sub_agg))
            .rename('peptide_score')
        )

        pep_df = (
            pep_scores.to_frame()
            .join(pep_info[['_patient', 'Elispot']], how='inner')
            .dropna(subset=['Elispot', 'peptide_score'])
        )
        if pep_df.empty:
            print(f'[per-patient][warn] {tool_name}: 合并后无有效肽，跳过', file=sys.stderr)
            continue

        rho_global = spearman_np(
            pep_df['peptide_score'].values, pep_df['Elispot'].values
        )

        pat_rhos: dict = {}
        pat_ns: dict = {}
        for pat, g in pep_df.groupby('_patient'):
            pat_key = str(pat)
            n_pep = len(g)
            rho = spearman_np(g['peptide_score'].values,
                              g['Elispot'].values) if n_pep >= min_pep else np.nan
            pat_rhos[pat_key] = rho
            pat_ns[pat_key] = n_pep

        valid_pairs = [
            (r, pat_ns[p]) for p, r in pat_rhos.items() if not np.isnan(r)
        ]
        if not valid_pairs:
            print(f'[per-patient][warn] {tool_name}: 无患者满足 >={min_pep} 肽条件，跳过',
                  file=sys.stderr)
            continue

        rhos_arr = np.array([v[0] for v in valid_pairs])
        ns_arr = np.array([v[1] for v in valid_pairs], float)
        n_patients_valid = len(rhos_arr)

        # 7 种聚合
        fz_rho, fz_ci_lo, fz_ci_hi, fz_n_used, fz_n_drop = \
            fisherz_weighted(rhos_arr, ns_arr)
        med = float(np.median(rhos_arr))
        smean = float(np.mean(rhos_arr))
        hs = hs_weighted(rhos_arr, ns_arr)
        gm = geometric_mean_rho(rhos_arr)
        pm2 = power_mean_p2(rhos_arr)
        uwls3_v = uwls3_agg(rhos_arr, ns_arr)

        rho_min = float(rhos_arr.min())
        rho_max = float(rhos_arr.max())
        rho_std = float(rhos_arr.std(ddof=1)) if len(rhos_arr) > 1 else np.nan

        def _r4(v):
            return round(float(v), 4) if (v is not None and not np.isnan(float(v) if v is not None else np.nan)) else np.nan

        row = {
            'Tool': tool_name,
            'n_patients': n_patients_valid,
            'rho_global': _r4(rho_global),
            'fisherz_weighted': _r4(fz_rho),
            'fisherz_ci_lo': _r4(fz_ci_lo),
            'fisherz_ci_hi': _r4(fz_ci_hi),
            'fisherz_n_used': fz_n_used,
            'fisherz_n_dropped': fz_n_drop,
            'median': _r4(med),
            'simple_mean': _r4(smean),
            'hs_weighted': _r4(hs),
            'geometric_mean': _r4(gm),
            'power_mean_p2': _r4(pm2),
            'uwls3': _r4(uwls3_v),
            'rho_min': _r4(rho_min),
            'rho_max': _r4(rho_max),
            'rho_std': _r4(rho_std),
        }

        for pid in ALL_PATIENTS:
            pid_s = str(pid)
            rho_v = pat_rhos.get(pid_s, np.nan)
            row[f'rho_p{pid_s}'] = _r4(rho_v) if not (isinstance(rho_v, float) and np.isnan(rho_v)) else np.nan
            row[f'n_p{pid_s}'] = pat_ns.get(pid_s, 0)

        results.append(row)

        # stdout 摘要
        diff = (_r4(fz_rho) - _r4(rho_global)) if (
            not np.isnan(fz_rho) and not np.isnan(rho_global)
        ) else float('nan')
        ci_str = (f'[{fz_ci_lo:+.3f},{fz_ci_hi:+.3f}]'
                  if not np.isnan(fz_ci_lo) else '[  n/a  ,  n/a  ]')
        print(
            f'  {tool_name:20s}  {rho_global:+10.4f}  {fz_rho:+9.4f}  '
            f'{ci_str:>16}  {med:+8.4f}  {n_patients_valid:>11d}  {diff:+14.4f}',
            file=sys.stderr,
        )

    print('=' * 95, file=sys.stderr)

    if not results:
        print('[per-patient][WARN] 所有工具均无有效结果，per-patient CSV 未写出',
              file=sys.stderr)
        return None

    out_df = pd.DataFrame(results)
    out_csv = out_dir / f'per_patient_spearman_{nn}tools.csv'
    out_df.to_csv(out_csv, index=False, encoding='utf-8')
    print(f'\n[per-patient] 已写 {out_csv}  shape={out_df.shape}', file=sys.stderr)

    # Fisher-z 排行榜（stdout）
    if 'fisherz_weighted' in out_df.columns:
        print('\n[per-patient] Fisher-z Spearman 排行榜 (按 fisherz_weighted 降序):')
        rank_df = out_df[['Tool', 'n_patients', 'rho_global',
                           'fisherz_weighted', 'fisherz_ci_lo', 'fisherz_ci_hi',
                           'median']].sort_values('fisherz_weighted', ascending=False)
        print(rank_df.to_string(index=False))

    return out_csv


# ── 读 PENDING_DTU_tools.txt ─────────────────────────────────────────────────
def load_pending_set(root: Path) -> set:
    pending_path = root / 'scripts' / 'out' / 'newtools' / 'PENDING_DTU_tools.txt'
    if not pending_path.exists():
        return set()
    tools = [t.strip() for t in pending_path.read_text(encoding='utf-8').splitlines() if t.strip()]
    print(f'[INFO] DTU pending 工具 ({len(tools)}): {tools}', file=sys.stderr)
    return set(tools)


# ── argparse ─────────────────────────────────────────────────────────────────
def parse_args():
    parser = argparse.ArgumentParser(
        description='QuantImmuBench: 全工具 DS2 指标重算（自动 NN）'
    )
    parser.add_argument(
        '--input', default=None,
        help='合并表 xlsx 路径（缺省自动寻找最高 NN 的 merged_all_tools_*tools.xlsx）',
    )
    parser.add_argument(
        '--sub-agg', choices=['max', 'mean', 'top3mean'], default='max',
        help='子肽聚合方式（默认 max）',
    )
    parser.add_argument(
        '--min-pep', type=int, default=3,
        help='per-patient Spearman 最少肽数（默认 3）',
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # ── 找输入 xlsx ───────────────────────────────────────────────────────────
    xlsx_path = resolve_xlsx(ROOT, args.input)
    nn = parse_nn_from_path(xlsx_path)
    print(f'[INFO] 输入: {xlsx_path}', file=sys.stderr)
    print(f'[INFO] NN={nn}  sub_agg={args.sub_agg}  min_pep={args.min_pep}',
          file=sys.stderr)

    df = pd.read_excel(xlsx_path)
    print(f'[INFO] 总行数: {len(df)}  列数: {len(df.columns)}', file=sys.stderr)

    if 'Dataset' not in df.columns:
        raise SystemExit("[ERR] 缺 'Dataset' 列，无法筛 DS2")

    # ── DTU pending set ───────────────────────────────────────────────────────
    pending_set = load_pending_set(ROOT)

    # ── 全局指标 ──────────────────────────────────────────────────────────────
    print('\n=== 全局指标计算 ===', file=sys.stderr)
    metrics_df = compute_global_metrics(df, nn, args.sub_agg, pending_set)

    out_metrics = HERE / f'metrics_ds2_{nn}tools.csv'
    with open(out_metrics, 'w', encoding='utf-8') as fo:
        fo.write(
            f'# QuantImmuBench DS2 全工具指标 | NN={nn} | sub_agg={args.sub_agg}\n'
            '# Spearman: 纯 numpy 实现(禁 scipy.stats); p-value via scipy.special.betainc\n'
            '# pending_DTU_consent: 工具原始数据使用待 DTU 授权\n'
        )
        metrics_df.to_csv(fo, index=False)
    print(f'[DONE] 全局指标 -> {out_metrics}  shape={metrics_df.shape}', file=sys.stderr)

    # 简要排行打印（max 聚合 >median 阈值）
    if not metrics_df.empty:
        print('\n=== AUC_ROC 排行 (max 聚合, >median 阈值) ===')
        sub = metrics_df[
            (metrics_df['Aggregation'] == 'max') & (metrics_df['Threshold'] == '>median')
        ][['Tool', 'AUC_ROC', 'AUPRC', 'Spearman_rho', 'pending_DTU_consent']]
        print(sub.sort_values('AUC_ROC', ascending=False).to_string(index=False))

    # ── per-patient 分析 ──────────────────────────────────────────────────────
    print('\n=== per-patient Spearman 分析 ===', file=sys.stderr)
    run_per_patient(df, nn, HERE, args.sub_agg, args.min_pep)

    print(f'\n[DONE] merge_metrics_NNtools.py 完成 (NN={nn})', file=sys.stderr)


if __name__ == '__main__':
    main()
