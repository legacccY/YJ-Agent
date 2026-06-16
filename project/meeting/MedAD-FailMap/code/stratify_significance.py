"""
stratify_significance.py — PC-A F-A family 显著性检验 (T1/T2/T3)
服务: MedAD-FailMap Phase 0, 05_preregistration.md C 节缺口 1

检验定义 (05_preregistration B 节，冻结):
  T1: detected ~ size_px    LR 系数 Wald → chi2(1) 双侧
  T2: detected ~ contrast   LR 系数 Wald → chi2(1) 双侧
  T3: 交互似然比: full=detected~size+contrast+size:contrast
                   base=detected~size+contrast
                   stat = 2(ll_full - ll_base) → chi2(1) 双侧

y = detected = (anomaly_score >= top-10% P90，tumor-only 集内定阈)
  与 stratify_eval.py / incremental_stats.py / failure_boundary.py threshold_pct=90 一致

多重比较: 3 个 raw p → F-A family Holm (主) + BH-FDR (辅)
  校正函数 import from incremental_stats（同一实现，不另写）

输出: results/stratify_significance_FA.csv
  列: test_id / stat_chi2 / df / p_raw / p_holm / p_fdr_bh / sig_holm

依赖: statsmodels (0.14+), numpy, sklearn (LogisticRegression fallback)
     不用 scipy (OMP#15 风险)
"""

import argparse
import csv
from pathlib import Path

import numpy as np

# ============================================================
# 复用 incremental_stats 里的 Holm/FDR（同一实现，不另新写）
# ============================================================
import sys
_CODE_DIR = Path(__file__).resolve().parent
if str(_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(_CODE_DIR))
from incremental_stats import holm_correction, fdr_bh_correction


# ============================================================
# 工具
# ============================================================

def _safe_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


def load_tumor_rows(score_csv, mask_dir=None, tumor_img_dir=None):
    """
    读 anomaly score csv 中 tumor 行，返回 (scores, filenames) numpy array。
    仅需 anomaly_score 列——size/contrast 由 strat_csv 提供。
    """
    rows = []
    with open(score_csv, newline="") as f:
        for row in csv.DictReader(f):
            if row.get("split", row.get("label", "")) in ("tumor", "1"):
                s = _safe_float(row.get("anomaly_score", "nan"))
                if not np.isnan(s):
                    rows.append((row.get("filename", ""), s))
    filenames = [r[0] for r in rows]
    scores    = np.array([r[1] for r in rows])
    return filenames, scores


def load_strat_covariates(strat_csv, filenames):
    """
    从 stratify_eval.py 产出 csv 按 filename join size_px + contrast。
    strat_csv 中的行是 per-image（stratify_interact_ae.csv 是 bin 聚合格，
    改用 stratify_eval 产出的每图行级 csv；若 strat_csv 不含 filename 列
    则尝试读 stratify_size / stratify_contrast 任一，再 join）。

    注: 若 strat_csv 是 per-image csv（含 filename/size_px/contrast 列），
    按 filename dict 匹配；若缺失则 nan。

    返回 (size_arr, contrast_arr) numpy arrays，与 filenames 对齐。
    """
    strat = {}
    with open(strat_csv, newline="") as f:
        for row in csv.DictReader(f):
            fn  = row.get("filename", "")
            sz  = _safe_float(row.get("size_px", "nan"))
            ct  = _safe_float(row.get("contrast", "nan"))
            if fn:
                strat[fn] = (sz, ct)

    sizes_arr     = np.array([strat.get(fn, (float("nan"), float("nan")))[0] for fn in filenames])
    contrasts_arr = np.array([strat.get(fn, (float("nan"), float("nan")))[1] for fn in filenames])
    return sizes_arr, contrasts_arr


# ============================================================
# 核心：Logit Wald 检验 + 嵌套 LLR
# ============================================================

def _logit_wald_chi2(y, X_names, data_dict):
    """
    用 statsmodels Logit 拟合，返回 (wald_chi2, p_raw) for 最后一个系数 (Wald 双侧)。
    X_names: list of str，与 data_dict keys 对应。
    data_dict: {'y': ..., 'x1': ..., ...} numpy arrays。
    返回 (chi2_stat, p_raw, loglik) 其中 chi2=Wald stat for last coef (df=1)。
    """
    import statsmodels.api as sm

    y_arr = data_dict["y"].astype(float)
    X_list = [data_dict[k].astype(float) for k in X_names]
    X_arr  = sm.add_constant(np.column_stack(X_list) if len(X_list) > 1 else X_list[0].reshape(-1, 1),
                              has_constant="add")

    try:
        model  = sm.Logit(y_arr, X_arr)
        result = model.fit(disp=0, maxiter=200, method="bfgs")
        # Wald chi2 for last predictor（交互/主效应参数，df=1）
        # t_stat for last coef = coef / bse; chi2 = t^2 (Wald df=1)
        last_idx = len(result.params) - 1
        coef     = result.params[last_idx]
        bse      = result.bse[last_idx]
        if bse < 1e-12:
            return float("nan"), float("nan"), result.llf
        wald_chi2 = float((coef / bse) ** 2)
        p_raw     = float(result.pvalues[last_idx])   # 双侧 Wald p
        return wald_chi2, p_raw, result.llf
    except Exception as e:
        print(f"  [FA warn] statsmodels Logit failed ({e}), fallback sklearn")
        return _sklearn_wald_fallback(y_arr, np.column_stack(X_list))


def _sklearn_wald_fallback(y, X):
    """
    Wald 检验 fallback（不依赖 statsmodels）。
    对 X 最后一列计算 Wald se = sqrt((X^T W X)^{-1}_{jj})，W=p(1-p)。
    返回 (wald_chi2_last, p_raw, loglik)。
    """
    from sklearn.linear_model import LogisticRegression
    from incremental_stats import chi2_sf_approx

    clf = LogisticRegression(C=1e6, max_iter=1000, solver="lbfgs", random_state=42)
    X_aug = np.column_stack([np.ones(len(X)), X])
    clf.fit(X, y)
    # 重建增广特征矩阵的系数（含截距）
    coefs = np.concatenate([clf.intercept_, clf.coef_[0]])  # (p+1,)

    proba = clf.predict_proba(X)[:, 1]
    proba = np.clip(proba, 1e-12, 1 - 1e-12)
    W     = proba * (1 - proba)

    # Fisher 信息矩阵 X^T W X
    XW = X_aug * W[:, None]
    I  = X_aug.T @ XW   # (p+1, p+1)
    try:
        I_inv = np.linalg.inv(I)
        se    = np.sqrt(np.diag(I_inv))
        last  = len(coefs) - 1
        wald_chi2 = float((coefs[last] / se[last]) ** 2) if se[last] > 1e-12 else float("nan")
        p_raw     = chi2_sf_approx(wald_chi2, df=1)
    except np.linalg.LinAlgError:
        wald_chi2 = float("nan")
        p_raw     = float("nan")

    loglik = float(np.sum(y * np.log(proba) + (1 - y) * np.log(1 - proba)))
    return wald_chi2, p_raw, loglik


def _logit_loglik(y, X_cols, data_dict):
    """仅返回 loglik，用于 T3 嵌套 LLR。"""
    import statsmodels.api as sm

    y_arr  = data_dict["y"].astype(float)
    X_list = [data_dict[k].astype(float) for k in X_cols]
    X_arr  = sm.add_constant(np.column_stack(X_list) if len(X_list) > 1 else X_list[0].reshape(-1, 1),
                              has_constant="add")
    try:
        model  = sm.Logit(y_arr, X_arr)
        result = model.fit(disp=0, maxiter=200, method="bfgs")
        return result.llf
    except Exception:
        from incremental_stats import logistic_loglik
        X_np = np.column_stack(X_list) if len(X_list) > 1 else X_list[0].reshape(-1, 1)
        ll, _ = logistic_loglik(X_np, y_arr)
        return ll


# ============================================================
# 主函数
# ============================================================

def run_fa_significance(score_csv, strat_per_image_csv, out_csv,
                         threshold_pct=90):
    """
    跑 T1/T2/T3，输出 F-A family 校正结果。

    score_csv:            anomaly_scores_brats_ae.csv（含 split/filename/anomaly_score）
    strat_per_image_csv:  per-image csv，含 filename / size_px / contrast 列。
                          由 stratify_eval.py 产出的 stratify_per_image_<model>.csv，
                          须在此函数前运行 stratify_eval.py 以生成该文件。
    out_csv:              results/stratify_significance_FA.csv
    """
    # 1. 读 tumor 行 scores
    filenames, scores = load_tumor_rows(score_csv)
    print(f"[FA] tumor rows from score_csv: {len(scores)}")

    # 2. 读 size/contrast 协变量
    size_arr, contrast_arr = load_strat_covariates(strat_per_image_csv, filenames)

    # 3. 过滤掉 nan（size 或 contrast 缺失的行）
    valid = (~np.isnan(size_arr)) & (~np.isnan(contrast_arr))
    scores_v   = scores[valid]
    size_v     = size_arr[valid]
    contrast_v = contrast_arr[valid]
    print(f"[FA] valid rows (size+contrast found): {int(valid.sum())}")

    if valid.sum() < 20:
        raise RuntimeError("[FA] 太少有效行 (<20)，检查 strat_per_image_csv 是否含 filename/size_px/contrast 列")

    # 4. detected (tumor-only P90，与预登记一致)
    threshold = float(np.percentile(scores_v, threshold_pct))
    y         = (scores_v >= threshold).astype(float)
    print(f"[FA] threshold P{threshold_pct} = {threshold:.6f}, n_detected = {int(y.sum())}/{len(y)}")

    data = {"y": y, "size": size_v, "contrast": contrast_v,
            "size_x_contrast": size_v * contrast_v}

    # ---- T1: detected ~ size ----
    chi2_T1, p_T1, _ = _logit_wald_chi2(y, ["size"], data)
    print(f"[FA] T1 size   chi2={chi2_T1:.4f}  p_raw={p_T1:.6f}")

    # ---- T2: detected ~ contrast ----
    chi2_T2, p_T2, _ = _logit_wald_chi2(y, ["contrast"], data)
    print(f"[FA] T2 contrast chi2={chi2_T2:.4f}  p_raw={p_T2:.6f}")

    # ---- T3: 嵌套 LLR —— full=size+contrast+size:contrast vs base=size+contrast ----
    # stat = 2(ll_full - ll_base) → chi2(1) 双侧
    ll_base = _logit_loglik(y, ["size", "contrast"], data)
    ll_full = _logit_loglik(y, ["size", "contrast", "size_x_contrast"], data)
    chi2_T3 = max(0.0, 2.0 * (ll_full - ll_base))
    # T3 p via 同一 Wilson-Hilferty 近似（incremental_stats 已有）
    from incremental_stats import chi2_sf_approx
    p_T3 = chi2_sf_approx(chi2_T3, df=1)
    print(f"[FA] T3 interact LLR chi2={chi2_T3:.4f}  p_raw={p_T3:.6f}  (ll_full={ll_full:.2f} ll_base={ll_base:.2f})")

    # ---- F-A family Holm + FDR ----
    raw_ps  = np.array([p_T1, p_T2, p_T3])
    holm_ps = holm_correction(raw_ps)
    fdr_ps  = fdr_bh_correction(raw_ps)

    tests = [
        dict(test_id="T1", description="detected~size LR Wald",
             stat_chi2=chi2_T1, df=1, p_raw=p_T1),
        dict(test_id="T2", description="detected~contrast LR Wald",
             stat_chi2=chi2_T2, df=1, p_raw=p_T2),
        dict(test_id="T3", description="interact LLR full vs base (size+contrast+size:contrast vs size+contrast)",
             stat_chi2=chi2_T3, df=1, p_raw=p_T3),
    ]

    rows_out = []
    for i, t in enumerate(tests):
        rows_out.append({
            "test_id":     t["test_id"],
            "description": t["description"],
            "stat_chi2":   round(float(t["stat_chi2"]), 4) if not np.isnan(t["stat_chi2"]) else "nan",
            "df":          t["df"],
            "p_raw":       round(float(t["p_raw"]),     6) if not np.isnan(t["p_raw"])     else "nan",
            "p_holm":      round(float(holm_ps[i]),     6),
            "p_fdr_bh":    round(float(fdr_ps[i]),      6),
            "sig_holm":    int(holm_ps[i] < 0.05),
            "family":      "F-A",
            "n_family":    3,
            "note":        "FA family Holm α=0.05/4=0.0125 per step; Gate0 用 p_holm<0.05 判显著",
        })

    out_path = Path(out_csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows_out[0].keys()))
        writer.writeheader()
        writer.writerows(rows_out)
    print(f"[FA] -> {out_path}")
    return rows_out


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="PC-A F-A family T1/T2/T3 显著性检验 (LR Wald + 嵌套 LLR + Holm/FDR)"
    )
    _root = Path(__file__).resolve().parent.parent
    _res  = _root / "results"

    parser.add_argument("--score-csv",
                        default=str(_res / "anomaly_scores_brats_ae.csv"),
                        help="train_recon_ae.py 产出 anomaly score csv (含 split=tumor 行)")
    parser.add_argument("--strat-per-image-csv",
                        default=str(_res / "stratify_per_image_ae.csv"),
                        help="per-image csv (含 filename/size_px/contrast 列)。"
                             "由 stratify_eval.py 产出的 stratify_per_image_<model>.csv，"
                             "需在此脚本前运行 stratify_eval.py。")
    parser.add_argument("--out-csv",
                        default=str(_res / "stratify_significance_FA.csv"),
                        help="输出 F-A family 检验结果 csv")
    parser.add_argument("--threshold-pct", type=float, default=90.0,
                        help="检出阈值百分位 (默认90，与 05_preregistration 冻结值一致)")
    args = parser.parse_args()

    run_fa_significance(
        score_csv=args.score_csv,
        strat_per_image_csv=args.strat_per_image_csv,
        out_csv=args.out_csv,
        threshold_pct=args.threshold_pct,
    )
