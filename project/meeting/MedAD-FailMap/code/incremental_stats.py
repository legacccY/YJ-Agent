"""
incremental_stats.py — PC-C C2/C3/C4 增量统计（纯 CPU）
服务: MedAD-FailMap Phase 0, PC-C

C2: 嵌套逻辑回归似然比检验 (LR test)
    base  = anomaly_score
    full  = anomaly_score + conspicuity_features
    H0: conspicuity given anomaly_score 无增量预测力
    stat: chi2 = 2*(loglik_full - loglik_base), df=n_conspicuity_feats
    p 值 Holm/FDR 校正 (多个 conspicuity 特征分别检验)

C3: 控制 size + contrast 后残差偏相关
    残差 = anomaly_score ~ size + contrast 的线性回归残差
    然后测 conspicuity 与 detected (binary) 的偏相关 (Pearson, 纯 numpy)
    p 值 Holm/FDR 校正

C4: risk-coverage / selective AUROC 曲线
    按 conspicuity 排序，丢 bottom-k% 后，剩余子集 AUROC 单调性
    输出 coverage 0.1~1.0 每步 0.05 的 AUROC

依赖: numpy, scikit-learn (LogisticRegression, roc_auc_score)
不用 scipy.stats（OMP#15 风险）

多重比较校正:
  - 内置 Holm 校正 (纯 numpy 实现)
  - 内置 Benjamini-Hochberg FDR 校正 (纯 numpy 实现)
  - 02_ACCEPTANCE.md 硬要求

输入 csv 列 (来自 conspicuity_proxy.py + stratify_eval.py):
  filename, anomaly_score, label,
  sigma_global, glcm_cluster_prom, glcm_contrast, fft_spectral_entropy, cnr_proxy_otsu,
  size_px (可选, 来自 stratify_eval), contrast (可选)

产出:
  incremental_C2_lr_test.csv      -- LR 检验结果 + Holm/FDR 校正 p 值
  incremental_C3_partial_corr.csv -- 残差偏相关结果 + 校正
  incremental_C4_risk_coverage.csv -- risk-coverage AUROC 曲线
"""

import argparse
import csv
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score


# ============================================================
# 纯 numpy 统计工具（无 scipy）
# ============================================================

def logistic_loglik(X, y, max_iter=1000):
    """
    拟合逻辑回归, 返回 log-likelihood (样本均值)
    使用 sklearn LogisticRegression (lbfgs, C=1e6 近似无正则)
    """
    clf = LogisticRegression(C=1e6, max_iter=max_iter, solver="lbfgs",
                             random_state=42)
    clf.fit(X, y)
    proba = clf.predict_proba(X)[:, 1]
    proba = np.clip(proba, 1e-12, 1 - 1e-12)
    loglik = float(np.sum(y * np.log(proba) + (1 - y) * np.log(1 - proba)))
    return loglik, clf


def chi2_sf_approx(chi2_val, df):
    """
    chi2 存活函数近似 (纯 numpy, 无 scipy)
    用 Chernoff/normal 近似: chi2(df) ~ N(df, 2*df) for large df,
    小 df 用更精确的 Wilson-Hilferty 变换

    Wilson-Hilferty: (chi2/df)^(1/3) ~ N(1 - 2/(9df), 2/(9df))
    p = P(Z > z)  -- 标准正态右尾
    """
    if chi2_val <= 0:
        return 1.0
    # Wilson-Hilferty 变换
    df_f  = float(df)
    x     = float(chi2_val)
    z     = ((x / df_f) ** (1.0/3.0) - (1.0 - 2.0/(9.0*df_f))) / np.sqrt(2.0/(9.0*df_f))
    # 标准正态右尾 (Abramowitz & Stegun 26.2.17 近似)
    p = _norm_sf(z)
    return float(np.clip(p, 0.0, 1.0))


def _norm_sf(z):
    """P(Z > z) 标准正态右尾，纯 numpy，误差 <1e-5 (Hart 1968 approximation)"""
    # 用误差函数近似: erfc(z/sqrt(2))/2
    # numpy 有 erfc 等价实现通过级数展开
    return float(0.5 * _erfc(z / np.sqrt(2.0)))


def _erfc(x):
    """erfc(x) 纯 numpy Horner 多项式近似 (Abramowitz & Stegun 7.1.26)"""
    x = np.asarray(x, dtype=np.float64)
    t = 1.0 / (1.0 + 0.3275911 * np.abs(x))
    poly = (((( 1.061405429  * t
              - 1.453152027) * t
              + 1.421413741) * t
              - 0.284496736) * t
              + 0.254829592) * t
    result = poly * np.exp(-x**2)
    # erfc(x) = 2 - erfc(-x) for x < 0
    return np.where(x >= 0, result, 2.0 - result)


def pearson_r_numpy(x, y):
    """Pearson r, 纯 numpy。返回 (r, p_approx)"""
    n = len(x)
    if n < 4:
        return 0.0, 1.0
    xm = x - x.mean()
    ym = y - y.mean()
    denom = np.sqrt((xm**2).sum() * (ym**2).sum())
    if denom < 1e-12:
        return 0.0, 1.0
    r = float(np.dot(xm, ym) / denom)
    r = np.clip(r, -1+1e-9, 1-1e-9)
    # t = r*sqrt(n-2)/sqrt(1-r^2), df=n-2
    t_stat = r * np.sqrt(n - 2) / np.sqrt(1 - r**2)
    # 近似 p (两尾): 用 chi2_sf_approx(t^2, df=1) * 0.5 * 2
    p = chi2_sf_approx(t_stat**2, df=1)
    return r, float(p)


def linear_residuals(X, y):
    """
    y = X @ beta 的最小二乘残差 (纯 numpy lstsq)
    X: (n, p), y: (n,)
    """
    X_aug = np.column_stack([np.ones(len(X)), X])
    beta, _, _, _ = np.linalg.lstsq(X_aug, y, rcond=None)
    resid = y - X_aug @ beta
    return resid


# ============================================================
# 多重比较校正 (纯 numpy)
# ============================================================

def holm_correction(pvals):
    """
    Holm-Bonferroni 校正
    返回 adjusted p 值 array (与输入等长)
    """
    n    = len(pvals)
    idx  = np.argsort(pvals)
    adj  = np.zeros(n)
    for i, orig_i in enumerate(idx):
        adj[orig_i] = min(1.0, pvals[orig_i] * (n - i))
    # 确保单调性
    for i in range(1, n):
        adj[idx[i]] = max(adj[idx[i]], adj[idx[i-1]])
    return adj


def fdr_bh_correction(pvals):
    """
    Benjamini-Hochberg FDR 校正
    返回 adjusted p 值 array
    """
    n    = len(pvals)
    idx  = np.argsort(pvals)
    adj  = np.zeros(n)
    for i, orig_i in enumerate(idx):
        adj[orig_i] = pvals[orig_i] * n / (i + 1)
    # 强制单调递减 (从大到小)
    for i in range(n - 2, -1, -1):
        adj[idx[i]] = min(adj[idx[i]], adj[idx[i+1]])
    adj = np.minimum(adj, 1.0)
    return adj


# ============================================================
# C2: 嵌套逻辑回归 LR 检验
# ============================================================

def run_c2_lr_test(df, conspicuity_cols, out_path):
    """
    base  = [anomaly_score]
    full_i = [anomaly_score, conspicuity_col_i]
    stat_i = 2*(loglik_full_i - loglik_base)  chi2(1)
    """
    y = df["label"].astype(int).to_numpy()
    X_base = df[["anomaly_score"]].to_numpy()
    loglik_base, _ = logistic_loglik(X_base, y)

    raw_ps = []
    stats  = []
    for col in conspicuity_cols:
        feat = df[col].to_numpy().reshape(-1, 1)
        X_full = np.hstack([X_base, feat])
        loglik_full, _ = logistic_loglik(X_full, y)
        chi2_stat = 2.0 * (loglik_full - loglik_base)
        chi2_stat = max(chi2_stat, 0.0)
        p_raw = chi2_sf_approx(chi2_stat, df=1)
        stats.append(chi2_stat)
        raw_ps.append(p_raw)

    raw_ps  = np.array(raw_ps)
    holm_ps = holm_correction(raw_ps)
    fdr_ps  = fdr_bh_correction(raw_ps)

    rows = []
    for i, col in enumerate(conspicuity_cols):
        rows.append({
            "feature":    col,
            "chi2_stat":  round(stats[i], 4),
            "p_raw":      round(float(raw_ps[i]), 6),
            "p_holm":     round(float(holm_ps[i]), 6),
            "p_fdr_bh":   round(float(fdr_ps[i]), 6),
            "sig_holm05": int(holm_ps[i] < 0.05),
            "sig_fdr05":  int(fdr_ps[i] < 0.05),
        })
    _write_csv(out_path, rows)
    print(f"[C2] LR test -> {out_path}")


# ============================================================
# C3: 残差偏相关
# ============================================================

def run_c3_partial_corr(df, conspicuity_cols, covariate_cols, out_path):
    """
    1. 线性回归 anomaly_score ~ size + contrast -> 残差
    2. 对每个 conspicuity 特征计算与 label 的偏相关 (控制 size+contrast 后)
       实现: residualize conspicuity ~ size+contrast, residualize label ~ size+contrast,
             然后 Pearson(resid_consp, resid_label)
    """
    y_bin  = df["label"].astype(float).to_numpy()

    # residualize label ~ covariates
    if len(covariate_cols) > 0:
        cov_arr   = df[covariate_cols].to_numpy().astype(float)
        resid_y   = linear_residuals(cov_arr, y_bin)
    else:
        resid_y = y_bin - y_bin.mean()

    raw_ps = []
    rs     = []
    for col in conspicuity_cols:
        consp = df[col].to_numpy().astype(float)
        if len(covariate_cols) > 0:
            resid_consp = linear_residuals(cov_arr, consp)
        else:
            resid_consp = consp - consp.mean()
        r, p = pearson_r_numpy(resid_consp, resid_y)
        rs.append(r)
        raw_ps.append(p)

    raw_ps  = np.array(raw_ps)
    holm_ps = holm_correction(raw_ps)
    fdr_ps  = fdr_bh_correction(raw_ps)

    rows = []
    for i, col in enumerate(conspicuity_cols):
        rows.append({
            "feature":      col,
            "controlled_for": "+".join(covariate_cols),
            "partial_r":    round(rs[i], 4),
            "p_raw":        round(float(raw_ps[i]), 6),
            "p_holm":       round(float(holm_ps[i]), 6),
            "p_fdr_bh":     round(float(fdr_ps[i]), 6),
            "sig_holm05":   int(holm_ps[i] < 0.05),
            "sig_fdr05":    int(fdr_ps[i] < 0.05),
        })
    _write_csv(out_path, rows)
    print(f"[C3] partial corr -> {out_path}")


# ============================================================
# C4: risk-coverage / selective AUROC 曲线
# ============================================================

def run_c4_risk_coverage(df, conspicuity_col, out_path, coverage_steps=None):
    """
    按 conspicuity_col 降序排列 (high conspicuity = more reliable)
    coverage = k/N: 保留 top-k 高 conspicuity 样本
    计算该子集的 AUROC
    期望: coverage 越高 AUROC 越低 (保留难样本 AUROC 降)
          coverage 越低 (只保留 easy 高 consp) AUROC 升

    🔴 TODO: 「conspicuity 高 = 更可靠」方向假设需实验验证;
             若方向相反应翻转排序，需主线/researcher 确认。
    """
    if coverage_steps is None:
        coverage_steps = [round(0.1 + 0.05*i, 2) for i in range(19)]  # 0.10~1.00

    df_sorted = df.sort_values(conspicuity_col, ascending=False).reset_index(drop=True)
    n_total   = len(df_sorted)
    y_all     = df_sorted["label"].astype(int).to_numpy()
    score_all = df_sorted["anomaly_score"].astype(float).to_numpy()

    rows = []
    for cov in coverage_steps:
        k = max(int(np.ceil(n_total * cov)), 2)
        k = min(k, n_total)
        y_sub   = y_all[:k]
        sc_sub  = score_all[:k]
        if len(np.unique(y_sub)) < 2:
            auroc = float("nan")
        else:
            auroc = float(roc_auc_score(y_sub, sc_sub))
        rows.append({
            "conspicuity_col": conspicuity_col,
            "coverage":        cov,
            "n_kept":          k,
            "auroc":           round(auroc, 4) if not np.isnan(auroc) else "nan",
        })
    _write_csv(out_path, rows)
    print(f"[C4] risk-coverage ({conspicuity_col}) -> {out_path}")


# ============================================================
# IO 工具
# ============================================================

def _write_csv(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        print(f"  [warn] no rows for {path}")
        return
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def load_merged_csv(conspicuity_csv, stratify_csv=None):
    """
    读 conspicuity_proxy.py 产出 csv，可选合并 stratify_eval.py 的 size/contrast 列
    返回简单 dict-of-arrays (避免 pandas 依赖)
    """
    rows = []
    with open(conspicuity_csv, newline="") as f:
        rows = list(csv.DictReader(f))

    # 可选合并 size/contrast (按 filename join)
    if stratify_csv and Path(stratify_csv).exists():
        extra = {}
        with open(stratify_csv, newline="") as f:
            for row in csv.DictReader(f):
                extra[row["filename"]] = row
        for r in rows:
            ex = extra.get(r["filename"], {})
            r["size_px"]  = ex.get("size_px",  float("nan"))
            r["contrast"] = ex.get("contrast",  float("nan"))

    return _rows_to_df(rows)


def _rows_to_df(rows):
    """简单列式字典，模拟 pandas DataFrame 的必要接口"""
    class SimpleDF:
        def __init__(self, rows):
            self._rows = rows
            self._cols = list(rows[0].keys()) if rows else []

        def __len__(self):
            return len(self._rows)

        def __getitem__(self, cols):
            if isinstance(cols, str):
                return _Col([_safe_float(r.get(cols, float("nan"))) for r in self._rows])
            return SimpleDF([{c: r.get(c) for c in cols} for r in self._rows])

        def to_numpy(self):
            return np.array([[_safe_float(r[c]) for c in self._cols]
                              for r in self._rows], dtype=np.float64)

        def sort_values(self, col, ascending=True):
            key = lambda r: _safe_float(r.get(col, 0))
            sorted_rows = sorted(self._rows, key=key, reverse=not ascending)
            return SimpleDF(sorted_rows)

        def reset_index(self, drop=True):
            return self

        @property
        def columns(self):
            return self._cols

    class _Col:
        def __init__(self, vals):
            self._vals = vals
        def astype(self, t):
            return _Col([t(v) for v in self._vals])
        def to_numpy(self):
            return np.array(self._vals)

    return SimpleDF(rows)


def _safe_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


# ============================================================
# Entry point
# ============================================================

CONSPICUITY_COLS = [
    "sigma_global",
    "glcm_cluster_prom",
    "glcm_contrast",
    "fft_spectral_entropy",
    "cnr_proxy_otsu",
]

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PC-C C2/C3/C4 增量统计 (Holm/FDR 校正)")
    _root = Path(__file__).resolve().parent.parent
    _res  = _root / "results"

    parser.add_argument("--conspicuity-csv",
                        default=str(_res / "conspicuity_features.csv"),
                        help="conspicuity_proxy.py 产出 csv")
    parser.add_argument("--stratify-csv",
                        default=str(_res / "stratify_size_ae.csv"),
                        help="(可选) stratify_eval.py 产出 csv，用于提取 size/contrast 列")
    parser.add_argument("--out-dir",
                        default=str(_res),
                        help="输出目录")
    parser.add_argument("--risk-coverage-col",
                        default="cnr_proxy_otsu",
                        help="C4 risk-coverage 用的 conspicuity 列名")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = load_merged_csv(args.conspicuity_csv, args.stratify_csv)
    print(f"[incremental] loaded {len(df)} rows")

    # 过滤掉 label=-1 (未知) 行
    valid_mask = [_safe_float(r.get("label", -1)) >= 0 for r in df._rows]
    df._rows = [r for r, m in zip(df._rows, valid_mask) if m]
    print(f"[incremental] valid (label>=0): {len(df)} rows")

    # C2
    run_c2_lr_test(df, CONSPICUITY_COLS,
                   out_dir / "incremental_C2_lr_test.csv")

    # C3 (需 size + contrast 列)
    covariate_cols = []
    if "size_px" in (df._rows[0] if df._rows else {}):
        covariate_cols = ["size_px", "contrast"]
    run_c3_partial_corr(df, CONSPICUITY_COLS, covariate_cols,
                        out_dir / "incremental_C3_partial_corr.csv")

    # C4 (对每个 conspicuity 列各出一个 csv)
    for col in CONSPICUITY_COLS:
        run_c4_risk_coverage(df, col,
                             out_dir / f"incremental_C4_risk_coverage_{col}.csv")

    print("[incremental] all done.")
