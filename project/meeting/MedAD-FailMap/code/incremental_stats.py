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

C4: risk-coverage / selective AUROC 曲线 (normal+tumor 混合集)
    按 conspicuity 排序，丢 bottom-k% 后，剩余子集 AD AUROC (normal=0 vs tumor=1)
    输出列: coverage, retained_n, ad_auroc (0.1~1.0 每步 0.05)

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
    C2: 嵌套 LR 检验 (ACCEPTANCE ③ 防循环论证核心)
    y = detected (tumor 是否被检出), 非 label
    理由: conspicuity_features.csv 来自 tumor-only 图像目录，label 全为 1 (常数)，
          无区分度; ACCEPTANCE ③ 要测「given anomaly_score 后 conspicuity 是否额外预测
          检出成败 detected」——y 必须是 detected 而非 label。
          tumor-only 集内: detected = (anomaly_score >= top-10% threshold)
    base  = [anomaly_score]
    full_i = [anomaly_score, conspicuity_col_i]
    stat_i = 2*(loglik_full_i - loglik_base)  chi2(1)
    """
    # y = detected: tumor 样本中 anomaly_score >= 90th percentile → 检出
    # 阈值 top-10% (预登记口径, 与 failure_boundary.py threshold_pct=90 一致)
    scores = df["anomaly_score"].to_numpy()
    threshold = float(np.percentile(scores, 90))
    y = (scores >= threshold).astype(int)
    # 注: y=detected 非 label; tumor-only 集内做 LR 检验 (ACCEPTANCE ③ 防循环论证)
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
            "p_holm":     round(float(holm_ps[i]), 6),     # 注: family 内 5 个校正，非确证判定用，确证看 incremental_FC_family_holm.csv
            "p_fdr_bh":   round(float(fdr_ps[i]), 6),     # 同上
            "sig_holm05": int(holm_ps[i] < 0.05),
            "sig_fdr05":  int(fdr_ps[i] < 0.05),
            "note":       "C2 family-internal 5-test Holm; Gate0 determination: see incremental_FC_family_holm.csv (10-test unified)",
        })
    _write_csv(out_path, rows)
    print(f"[C2] LR test -> {out_path}")


# ============================================================
# C3: 残差偏相关
# ============================================================

def run_c3_partial_corr(df, conspicuity_cols, covariate_cols, out_path):
    """
    C3: 残差偏相关 (ACCEPTANCE ③ 防循环论证核心)
    y = detected (tumor 是否被检出), 非 label
    理由同 run_c2_lr_test: tumor-only 集, label 为常数 (全 1), 无区分度;
    ACCEPTANCE ③ 要控制 size+contrast 后测 conspicuity 与「检出成败」的独立相关。
    y = detected: anomaly_score >= 90th percentile (tumor-only, top-10% 预登记口径)
    注: y=detected 非 label; tumor-only 集内做偏相关 (ACCEPTANCE ③ 防循环论证)
    1. 线性回归 anomaly_score ~ size + contrast -> 残差
    2. 对每个 conspicuity 特征计算与 detected 的偏相关 (控制 size+contrast 后)
       实现: residualize conspicuity ~ size+contrast, residualize detected ~ size+contrast,
             然后 Pearson(resid_consp, resid_detected)
    """
    # y = detected: tumor 样本中 anomaly_score >= 90th percentile → 检出
    scores = df["anomaly_score"].to_numpy()
    threshold = float(np.percentile(scores, 90))
    y_bin  = (scores >= threshold).astype(float)

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
            "p_holm":       round(float(holm_ps[i]), 6),     # 注: family 内 5 个校正，非确证判定用，确证看 incremental_FC_family_holm.csv
            "p_fdr_bh":     round(float(fdr_ps[i]), 6),     # 同上
            "sig_holm05":   int(holm_ps[i] < 0.05),
            "sig_fdr05":    int(fdr_ps[i] < 0.05),
            "note":         "C3 family-internal 5-test Holm; Gate0 determination: see incremental_FC_family_holm.csv (10-test unified)",
        })
    _write_csv(out_path, rows)
    print(f"[C3] partial corr -> {out_path}")


# ============================================================
# C4: risk-coverage / selective AUROC 曲线
# ============================================================

def load_mixed_df(tumor_conspicuity_csv, normal_conspicuity_csv, score_csv):
    """
    合并 normal + tumor 的 conspicuity csv，并从 score_csv join anomaly_score。
    label: normal=0 / tumor=1 (真实 AD label，不依赖 conspicuity csv 里的 label 列)

    参数:
        tumor_conspicuity_csv  -- conspicuity_proxy.py 对 tumor 目录产出的 csv
        normal_conspicuity_csv -- conspicuity_proxy.py 对 normal 目录产出的 csv
        score_csv              -- anomaly_scores_brats_ae.csv (含 filename + anomaly_score)
    返回 SimpleDF，列: filename, label(0/1), anomaly_score, <conspicuity feats>
    注: 若 score_csv 不存在，anomaly_score 保留 nan（仅特征列可用）
    """
    def _read_csv(path):
        with open(path, newline="") as f:
            return list(csv.DictReader(f))

    tumor_rows  = _read_csv(tumor_conspicuity_csv)
    normal_rows = _read_csv(normal_conspicuity_csv)

    # 打真实 AD label：tumor=1, normal=0
    for r in tumor_rows:
        r["label"] = "1"
    for r in normal_rows:
        r["label"] = "0"

    all_rows = tumor_rows + normal_rows

    # join anomaly_score from score_csv (by filename)
    score_map = {}  # filename -> anomaly_score str
    if score_csv and Path(score_csv).exists():
        with open(score_csv, newline="") as f:
            for row in csv.DictReader(f):
                score_map[row["filename"]] = row["anomaly_score"]
    else:
        print(f"  [warn] score_csv not found: {score_csv}, anomaly_score will be nan")

    for r in all_rows:
        r["anomaly_score"] = score_map.get(r["filename"], str(float("nan")))

    return _rows_to_df(all_rows)


def run_c4_risk_coverage(df_mixed, conspicuity_col, out_path, coverage_steps=None):
    """
    C4: risk-coverage / selective AUROC 曲线 (ACCEPTANCE ③ per-image 可靠性判据)

    正确语义: AD AUROC = normal(0) vs tumor(1) 区分度
    必须在 normal+tumor 混合集上算——否则 label 全 1，roc_auc_score crash。

    输入 df_mixed: load_mixed_df() 产出，含 normal+tumor 两类，label∈{0,1}
    排序键 = conspicuity_col（high = 更显著 = 暂代 reliability 代理）
    coverage c: 保留 top-c 比例（按 conspicuity 降序）→ 子集 AUROC
    期望: low coverage（只留高 conspicuity 肿瘤/低 conspicuity 正常）→ AUROC ↑

    # TODO: 「conspicuity 高 = 更可靠」方向假设需实验验证;
    #       若方向相反应翻转排序，需主线/researcher 确认。
    #       conspicuity 作为 reliability 代理权重尚未确定，此处单特征占位。
    """
    if coverage_steps is None:
        coverage_steps = [round(0.1 + 0.05*i, 2) for i in range(19)]  # 0.10~1.00

    df_sorted = df_mixed.sort_values(conspicuity_col, ascending=False).reset_index(drop=True)
    n_total   = len(df_sorted)
    y_all     = df_sorted["label"].astype(int).to_numpy()
    score_all = df_sorted["anomaly_score"].astype(float).to_numpy()

    rows = []
    for cov in coverage_steps:
        k = max(int(np.ceil(n_total * cov)), 2)
        k = min(k, n_total)
        y_sub  = y_all[:k]
        sc_sub = score_all[:k]

        n_classes = len(np.unique(y_sub[~np.isnan(sc_sub)]))
        if n_classes < 2 or np.all(np.isnan(sc_sub[:k])):
            # 子集仍单类（低 coverage 时可能发生），跳过不 crash
            auroc = float("nan")
            print(f"  [C4 warn] coverage={cov:.2f}: only {n_classes} class(es) in subset, skip")
        else:
            valid = ~np.isnan(sc_sub)
            auroc = float(roc_auc_score(y_sub[valid], sc_sub[valid]))

        rows.append({
            "conspicuity_col": conspicuity_col,
            "coverage":        cov,
            "retained_n":      k,
            "ad_auroc":        round(auroc, 4) if not np.isnan(auroc) else "nan",
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


# ============================================================
# F-C 合并 family：C2(5) + C3(5) = 10 统一 Holm + FDR
# ============================================================

def run_fc_family_holm(c2_csv_path, c3_csv_path, out_path):
    """
    缺口 2 (05_preregistration C 节): F-C family 合并 C2+C3 共 10 个检验统一 Holm/FDR。

    背景: C2/C3 各自内部 Holm (5 个) 是描述性输出，非确证判定用。
          Gate0 F-C 确证判定须用本函数输出 incremental_FC_family_holm.csv (10 个统一校正)。

    输入:
        c2_csv_path: incremental_C2_lr_test.csv (run_c2_lr_test 产出)
        c3_csv_path: incremental_C3_partial_corr.csv (run_c3_partial_corr 产出)
    输出:
        incremental_FC_family_holm.csv，10 行：
          test_id(T4.1-4.5/T5.1-5.5) / feature / source(C2/C3) / p_raw /
          p_holm_family10 / p_fdr_family10 / sig / note
    """
    # 读 C2 子 csv（5 行 per CONSPICUITY_COLS 顺序）
    c2_rows, c3_rows = [], []
    test_id_map_c2 = {
        "sigma_global":         "T4.1",
        "glcm_cluster_prom":    "T4.2",
        "glcm_contrast":        "T4.3",
        "fft_spectral_entropy": "T4.4",
        "cnr_proxy_otsu":       "T4.5",
    }
    test_id_map_c3 = {
        "sigma_global":         "T5.1",
        "glcm_cluster_prom":    "T5.2",
        "glcm_contrast":        "T5.3",
        "fft_spectral_entropy": "T5.4",
        "cnr_proxy_otsu":       "T5.5",
    }

    def _read(path, id_map, source):
        rows_out = []
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                feat  = row["feature"]
                p_raw = float(row["p_raw"])
                rows_out.append({
                    "test_id":  id_map.get(feat, feat),
                    "feature":  feat,
                    "source":   source,
                    "p_raw":    p_raw,
                    # 保留子 csv 内的 chi2 或 partial_r 方便溯源
                    "stat":     row.get("chi2_stat", row.get("partial_r", "n/a")),
                    "stat_type": "chi2" if "chi2_stat" in row else "partial_r",
                })
        return rows_out

    c2_rows = _read(c2_csv_path, test_id_map_c2, "C2")
    c3_rows = _read(c3_csv_path, test_id_map_c3, "C3")

    all_rows = c2_rows + c3_rows   # 10 个，顺序: T4.1-T4.5 / T5.1-T5.5
    if len(all_rows) != 10:
        print(f"  [FC warn] 期望 10 行，实际 {len(all_rows)} 行（C2={len(c2_rows)}, C3={len(c3_rows)}）")

    raw_ps  = np.array([r["p_raw"] for r in all_rows])
    holm_ps = holm_correction(raw_ps)
    fdr_ps  = fdr_bh_correction(raw_ps)

    rows_out = []
    for i, r in enumerate(all_rows):
        rows_out.append({
            "test_id":         r["test_id"],
            "feature":         r["feature"],
            "source":          r["source"],
            "stat":            r["stat"],
            "stat_type":       r["stat_type"],
            "p_raw":           round(r["p_raw"],        6),
            "p_holm_family10": round(float(holm_ps[i]), 6),   # 10 个统一 Holm
            "p_fdr_family10":  round(float(fdr_ps[i]),  6),   # 10 个统一 BH-FDR
            "sig":             int(holm_ps[i] < 0.05),        # Gate0 F-C 判定用此列
            "family":          "F-C",
            "n_family":        10,
            "note": "FC 10-test unified Holm (05_preregistration C 节冻结); Gate0 F-C 判定以此表为准",
        })

    _write_csv(out_path, rows_out)
    print(f"[FC family] -> {out_path}  ({len(rows_out)} tests, Holm over 10)")
    return rows_out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PC-C C2/C3/C4 增量统计 (Holm/FDR 校正)")
    _root = Path(__file__).resolve().parent.parent
    _res  = _root / "results"

    # C2/C3 用 tumor-only conspicuity csv（label 全1，detected 做 y）
    parser.add_argument("--conspicuity-csv",
                        default=str(_res / "conspicuity_features_tumor.csv"),
                        help="tumor-only conspicuity_proxy.py 产出 csv (C2/C3 用)")
    parser.add_argument("--stratify-csv",
                        default=str(_res / "stratify_interact_ae.csv"),
                        help="(可选) stratify_eval.py 产出 csv，用于提取 size/contrast 列")
    # C4 用 normal+tumor 混合集
    parser.add_argument("--normal-conspicuity-csv",
                        default=str(_res / "conspicuity_features_normal.csv"),
                        help="normal 图像 conspicuity_proxy.py 产出 csv (C4 用)")
    parser.add_argument("--score-csv",
                        default=str(_res / "anomaly_scores_brats_ae.csv"),
                        help="AE 产出 anomaly score csv (C4 join 用，含 normal+tumor 全行)")
    parser.add_argument("--out-dir",
                        default=str(_res),
                        help="输出目录")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ---- C2/C3: tumor-only df ----
    df_tumor = load_merged_csv(args.conspicuity_csv, args.stratify_csv)
    print(f"[incremental] tumor df loaded {len(df_tumor)} rows")

    # 过滤掉 label=-1 (未知) 行（tumor csv 里默认 label 可能为 -1）
    df_tumor._rows = [r for r in df_tumor._rows
                      if _safe_float(r.get("label", -1)) != -1
                      or True]  # tumor-only: 保留全部，C2/C3 用 detected 不用 label
    print(f"[incremental] tumor df after filter: {len(df_tumor)} rows")

    # C2
    run_c2_lr_test(df_tumor, CONSPICUITY_COLS,
                   out_dir / "incremental_C2_lr_test.csv")

    # C3 (需 size + contrast 列)
    covariate_cols = []
    if df_tumor._rows and "size_px" in df_tumor._rows[0]:
        covariate_cols = ["size_px", "contrast"]
    run_c3_partial_corr(df_tumor, CONSPICUITY_COLS, covariate_cols,
                        out_dir / "incremental_C3_partial_corr.csv")

    # ---- C4: normal+tumor 混合集 ----
    print(f"[incremental] loading mixed df for C4 ...")
    df_mixed = load_mixed_df(
        tumor_conspicuity_csv  = args.conspicuity_csv,
        normal_conspicuity_csv = args.normal_conspicuity_csv,
        score_csv              = args.score_csv,
    )
    print(f"[incremental] mixed df: {len(df_mixed)} rows (normal+tumor)")

    # C4 (对每个 conspicuity 列各出一个 csv)
    for col in CONSPICUITY_COLS:
        run_c4_risk_coverage(df_mixed, col,
                             out_dir / f"incremental_C4_risk_coverage_{col}.csv")

    # ---- F-C family 合并: C2(5) + C3(5) = 10 统一 Holm/FDR ----
    # 注: 须在 C2/C3 csv 已产出后调用
    c2_csv = out_dir / "incremental_C2_lr_test.csv"
    c3_csv = out_dir / "incremental_C3_partial_corr.csv"
    if c2_csv.exists() and c3_csv.exists():
        run_fc_family_holm(c2_csv, c3_csv,
                           out_dir / "incremental_FC_family_holm.csv")
    else:
        print("[incremental] warn: C2 or C3 csv missing, skip FC family merge")

    print("[incremental] all done.")
