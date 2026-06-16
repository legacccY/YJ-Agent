"""
failure_boundary.py — PC-B 失败边界拟合 + 跨集外推 + strong baseline（纯 CPU）
服务: MedAD-FailMap Phase 0, PC-B (B1/B2/B3/B4)

流程:
  B1: 在 BraTS 拟合失败边界 f(size, contrast) — 逻辑回归 + 浅 GBM
  B2: 跨集零调参外推 -> HAM-NV (AUROC + 集内 vs 集外对比)
  B3: vs strong baseline (size 单变量 / size+contrast 双变量)
  B4: extrapolation — 训中等 size -> 测未见极小 size (非 i.i.d.)

失败定义:
  detected = 0 (anomaly_score < threshold)
  threshold = top-10% of test anomaly scores
  🔴 TODO: 阈值口径同 stratify_eval.py，需主线/researcher 确认。

输入:
  --brats-csv: anomaly_scores_brats_<m>.csv + size/contrast (来自 stratify_eval 或单独计算)
  --ham-csv:   anomaly_scores_isic_<m>.csv  + size/contrast (HAM-NV 的 conspicuity 代理)
              (HAM 无 GT mask -> size_proxy = sigma_global, contrast_proxy = cnr_proxy_otsu)
  --conspicuity-brats: conspicuity_features.csv (BraTS 图，提取 size_proxy/contrast_proxy)
  --conspicuity-ham:   conspicuity_features_ham.csv

产出:
  boundary_B1_coefs.csv         -- 拟合系数
  boundary_B2_extrapolation.csv -- 跨集 AUROC (in-domain vs cross-domain)
  boundary_B3_baseline.csv      -- vs strong baseline AUROC 对比 (Holm 校正)
  boundary_B4_extrapolation.csv -- extrapolation to unseen small size

依赖: numpy, scikit-learn
不用 scipy (OMP#15)

多重比较: B3 多个模型对比 Holm 校正
"""

import argparse
import csv
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import cross_val_score


# ============================================================
# 工具
# ============================================================

def _safe_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


def _write_csv(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"  -> {path.name}")


def load_csv_cols(csv_path, cols):
    """读 csv 中指定列，返回 dict of numpy arrays，跳过 nan 行"""
    rows = []
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            vals = {c: _safe_float(row.get(c, "nan")) for c in cols}
            if any(np.isnan(list(vals.values()))):
                continue
            rows.append(vals)
    out = {c: np.array([r[c] for r in rows]) for c in cols}
    return out


def holm_correction(pvals):
    n    = len(pvals)
    idx  = np.argsort(pvals)
    adj  = np.zeros(n)
    for i, orig_i in enumerate(idx):
        adj[orig_i] = min(1.0, pvals[orig_i] * (n - i))
    for i in range(1, n):
        adj[idx[i]] = max(adj[idx[i]], adj[idx[i-1]])
    return adj


def chi2_sf_approx(chi2_val, df=1):
    """Wilson-Hilferty chi2 右尾近似（无 scipy）"""
    if chi2_val <= 0:
        return 1.0
    df_f = float(df)
    x    = float(chi2_val)
    z    = ((x/df_f)**(1.0/3.0) - (1.0 - 2.0/(9.0*df_f))) / np.sqrt(2.0/(9.0*df_f))
    return float(0.5 * _erfc(z / np.sqrt(2.0)))


def _erfc(x):
    x = np.asarray(x, dtype=np.float64)
    t = 1.0 / (1.0 + 0.3275911 * np.abs(x))
    poly = (((( 1.061405429  * t
              - 1.453152027) * t
              + 1.421413741) * t
              - 0.284496736) * t
              + 0.254829592) * t
    result = poly * np.exp(-x**2)
    return np.where(x >= 0, result, 2.0 - result)


def bootstrap_auroc_ci(y_true, scores, n_boot=500, seed=42, alpha=0.05):
    """Bootstrap AUROC 置信区间（95%），纯 numpy + sklearn"""
    rng  = np.random.default_rng(seed)
    n    = len(y_true)
    boot = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        yt  = y_true[idx]
        ys  = scores[idx]
        if len(np.unique(yt)) < 2:
            continue
        boot.append(roc_auc_score(yt, ys))
    if len(boot) < 10:
        return float("nan"), float("nan")
    boot = np.array(boot)
    lo   = float(np.percentile(boot, 100 * alpha/2))
    hi   = float(np.percentile(boot, 100 * (1 - alpha/2)))
    return lo, hi


# ============================================================
# B1: 拟合失败边界
# ============================================================

def fit_boundary(X, y, model_type="lr"):
    """
    model_type = "lr"  -> LogisticRegression (C=1.0)
    model_type = "gbm" -> GradientBoostingClassifier (n_estimators=50, max_depth=3)
    🔴 TODO: GBM 超参 (n_estimators/max_depth) 未找到领域官方设定，
             此处 n_estimators=50, max_depth=3 为浅树经验值（防过拟合），
             需 researcher/主线确认。
    """
    if model_type == "lr":
        clf = LogisticRegression(C=1.0, max_iter=1000, solver="lbfgs", random_state=42)
    else:
        clf = GradientBoostingClassifier(
            n_estimators=50, max_depth=3, learning_rate=0.1,
            random_state=42,
        )
    clf.fit(X, y)
    return clf


def run_b1(brats_data, out_dir, threshold_pct=90):
    """B1: BraTS 拟合失败=f(size,contrast) 边界"""
    scores   = brats_data["anomaly_score"]
    y_detect = (scores >= np.percentile(scores, threshold_pct)).astype(int)
    y_fail   = 1 - y_detect   # 失败=未检出

    # 特征: size_proxy + contrast_proxy (GT mask 有则用 size_px/contrast, 否则代理)
    size_col     = "size_px"     if "size_px"     in brats_data else "size_proxy"
    contrast_col = "contrast"    if "contrast"    in brats_data else "contrast_proxy"

    X2 = np.column_stack([brats_data[size_col], brats_data[contrast_col]])
    X1 = brats_data[size_col].reshape(-1, 1)

    rows = []
    for feat_name, X, model_type in [
        ("size_only",      X1, "lr"),
        ("size+contrast",  X2, "lr"),
        ("size+contrast_gbm", X2, "gbm"),
    ]:
        clf = fit_boundary(X, y_fail, model_type.replace("_gbm","").replace("size_only","lr")
                           if "gbm" not in model_type else "gbm")
        proba = clf.predict_proba(X)[:, 1]
        if len(np.unique(y_fail)) < 2:
            auroc = float("nan")
        else:
            auroc = float(roc_auc_score(y_fail, proba))

        # coefs (LR only)
        if hasattr(clf, "coef_"):
            coef_str = ";".join([f"{c:.4f}" for c in clf.coef_[0]])
            intercept = round(float(clf.intercept_[0]), 4)
        else:
            coef_str  = "n/a (GBM)"
            intercept = float("nan")

        rows.append({
            "model":       feat_name,
            "in_domain_auroc": round(auroc, 4),
            "coefs":       coef_str,
            "intercept":   intercept,
            "n":           len(y_fail),
            "n_fail":      int(y_fail.sum()),
        })
        # 缓存 clf 供 B2 用
        brats_data[f"_clf_{feat_name}"] = clf

    _write_csv(out_dir / "boundary_B1_coefs.csv", rows)
    brats_data["_y_fail"] = y_fail
    brats_data["_X2"]     = X2
    brats_data["_X1"]     = X1
    brats_data["_threshold_pct"] = threshold_pct
    return brats_data


# ============================================================
# B2: 跨集外推 -> HAM
# ============================================================

def run_b2(brats_data, ham_data, out_dir):
    """
    零调参: 在 BraTS 训的 clf 直接 predict HAM 失败概率 -> AUROC
    HAM: 无 GT mask -> size_proxy=sigma_global, contrast_proxy=cnr_proxy_otsu
    """
    if ham_data is None:
        print("[B2] ham_data not provided, skip")
        return

    threshold_pct = brats_data.get("_threshold_pct", 90)
    ham_scores = ham_data["anomaly_score"]
    ham_y_fail = 1 - (ham_scores >= np.percentile(ham_scores, threshold_pct)).astype(int)

    # HAM 特征对齐 (size_proxy -> sigma_global, contrast_proxy -> cnr_proxy_otsu)
    ham_X2 = np.column_stack([
        ham_data.get("sigma_global", np.zeros(len(ham_scores))),
        ham_data.get("cnr_proxy_otsu", np.zeros(len(ham_scores))),
    ])
    ham_X1 = ham_data.get("sigma_global", np.zeros(len(ham_scores))).reshape(-1, 1)

    rows = []
    in_domain_aucs = {
        "size_only":         brats_data.get("boundary_B1_coefs_size_only",    float("nan")),
        "size+contrast":     brats_data.get("boundary_B1_coefs_size+contrast", float("nan")),
        "size+contrast_gbm": brats_data.get("boundary_B1_coefs_size+contrast_gbm", float("nan")),
    }

    for feat_name, ham_X in [
        ("size_only",         ham_X1),
        ("size+contrast",     ham_X2),
        ("size+contrast_gbm", ham_X2),
    ]:
        clf = brats_data.get(f"_clf_{feat_name}")
        if clf is None:
            continue
        if len(np.unique(ham_y_fail)) < 2:
            auroc = float("nan")
            ci_lo = ci_hi = float("nan")
        else:
            proba = clf.predict_proba(ham_X)[:, 1]
            auroc = float(roc_auc_score(ham_y_fail, proba))
            ci_lo, ci_hi = bootstrap_auroc_ci(ham_y_fail, proba)

        rows.append({
            "model":             feat_name,
            "cross_domain_auroc": round(auroc, 4) if not np.isnan(auroc) else "nan",
            "ci_lo_95":          round(ci_lo, 4)  if not np.isnan(ci_lo) else "nan",
            "ci_hi_95":          round(ci_hi, 4)  if not np.isnan(ci_hi) else "nan",
            "n_ham":             len(ham_y_fail),
            "n_fail_ham":        int(ham_y_fail.sum()),
            "note": "BraTS->HAM zero-shot; size/contrast proxied by sigma/cnr_otsu (no GT mask)",
        })

    _write_csv(out_dir / "boundary_B2_extrapolation.csv", rows)


# ============================================================
# B3: vs strong baseline (Holm 校正)
# ============================================================

def run_b3(brats_data, out_dir):
    """
    Strong baseline:
      SB1 = size 单变量逻辑回归
      SB2 = size + contrast 双变量逻辑回归
    多维边界 = size+contrast_gbm (B1)
    Delta AUROC = boundary_model - strong_baseline
    p 值近似 (DeLong test 无 scipy -> 用 bootstrap)
    Holm 校正
    """
    X2       = brats_data.get("_X2")
    X1       = brats_data.get("_X1")
    y_fail   = brats_data.get("_y_fail")
    if X2 is None or y_fail is None:
        print("[B3] missing fitted data, skip")
        return

    models = {
        "SB1_size_lr":        (X1, "lr"),
        "SB2_size+contrast_lr": (X2, "lr"),
        "boundary_gbm":       (X2, "gbm"),
    }
    aucs   = {}
    probas = {}
    for name, (X, mtype) in models.items():
        clf = fit_boundary(X, y_fail, mtype)
        proba = clf.predict_proba(X)[:, 1]
        probas[name] = proba
        if len(np.unique(y_fail)) < 2:
            aucs[name] = float("nan")
        else:
            aucs[name] = float(roc_auc_score(y_fail, proba))

    # 比较 boundary_gbm vs SB1, vs SB2
    comparisons = [
        ("boundary_gbm", "SB1_size_lr"),
        ("boundary_gbm", "SB2_size+contrast_lr"),
    ]
    raw_ps = []
    deltas = []
    for (a, b) in comparisons:
        delta = aucs.get(a, float("nan")) - aucs.get(b, float("nan"))
        deltas.append(delta)
        # bootstrap p 값: p = P(delta_boot <= 0)
        pa  = probas.get(a, np.zeros(len(y_fail)))
        pb  = probas.get(b, np.zeros(len(y_fail)))
        rng = np.random.default_rng(42)
        n   = len(y_fail)
        boot_deltas = []
        for _ in range(500):
            idx   = rng.integers(0, n, size=n)
            yt    = y_fail[idx]
            if len(np.unique(yt)) < 2:
                continue
            da = roc_auc_score(yt, pa[idx])
            db = roc_auc_score(yt, pb[idx])
            boot_deltas.append(da - db)
        if len(boot_deltas) < 10:
            p_raw = float("nan")
        else:
            boot_arr = np.array(boot_deltas)
            p_raw = float(np.mean(boot_arr <= 0))
        raw_ps.append(p_raw)

    raw_ps  = np.array([p for p in raw_ps if not np.isnan(p)])
    holm_ps = holm_correction(raw_ps) if len(raw_ps) > 0 else raw_ps

    rows = []
    for i, (a, b) in enumerate(comparisons):
        p_raw  = raw_ps[i]  if i < len(raw_ps)  else float("nan")
        p_holm = holm_ps[i] if i < len(holm_ps) else float("nan")
        rows.append({
            "model_a":       a,
            "model_b":       b,
            "auroc_a":       round(aucs.get(a, float("nan")), 4),
            "auroc_b":       round(aucs.get(b, float("nan")), 4),
            "delta_auroc":   round(deltas[i], 4),
            "p_raw_boot":    round(float(p_raw),  6) if not np.isnan(p_raw)  else "nan",
            "p_holm":        round(float(p_holm), 6) if not np.isnan(p_holm) else "nan",
            "sig_holm05":    int(p_holm < 0.05) if not np.isnan(p_holm) else "nan",
        })

    # 也输出各模型单独 AUROC
    for name, auc_val in aucs.items():
        rows.append({
            "model_a": name, "model_b": "self",
            "auroc_a": round(auc_val, 4) if not np.isnan(auc_val) else "nan",
            "auroc_b": "n/a", "delta_auroc": "n/a",
            "p_raw_boot": "n/a", "p_holm": "n/a", "sig_holm05": "n/a",
        })

    _write_csv(out_dir / "boundary_B3_baseline.csv", rows)


# ============================================================
# B4: Extrapolation (训中等 size -> 测未见极小 size)
# ============================================================

def run_b4(brats_data, out_dir):
    """
    B4: extrapolation AUROC
    训练集: 中等 size (33~66 percentile)
    测试集: 极小 size (< 33 percentile) — 训练集未见区域
    拟合 LR on 中等, predict 极小, 报 AUROC

    🔴 TODO: size 分位数切点 (33/66) 是 03_phase0_plan.md 说明的三等分，
             与 stratify_eval.py 一致，但如需调整需 researcher/主线确认。
    """
    X2     = brats_data.get("_X2")
    X1     = brats_data.get("_X1")
    y_fail = brats_data.get("_y_fail")
    size_col_data = brats_data.get("size_px", brats_data.get("size_proxy", None))

    if X2 is None or y_fail is None or size_col_data is None:
        print("[B4] missing data, skip")
        return

    size_arr = size_col_data
    p33 = np.percentile(size_arr, 33)
    p66 = np.percentile(size_arr, 66)

    mid_mask   = (size_arr >= p33) & (size_arr <= p66)
    small_mask = size_arr < p33

    if mid_mask.sum() < 10 or small_mask.sum() < 5:
        print(f"[B4] insufficient samples: mid={mid_mask.sum()}, small={small_mask.sum()}, skip")
        return

    rows = []
    for feat_name, X in [("size+contrast_lr", X2), ("size_only_lr", X1)]:
        X_mid   = X[mid_mask]
        y_mid   = y_fail[mid_mask]
        X_small = X[small_mask]
        y_small = y_fail[small_mask]

        if len(np.unique(y_mid)) < 2 or len(np.unique(y_small)) < 2:
            auroc = float("nan")
            ci_lo = ci_hi = float("nan")
        else:
            clf   = fit_boundary(X_mid, y_mid, "lr")
            proba = clf.predict_proba(X_small)[:, 1]
            auroc = float(roc_auc_score(y_small, proba))
            ci_lo, ci_hi = bootstrap_auroc_ci(y_small, proba)

        rows.append({
            "model":          feat_name,
            "train_split":    "mid_size (33~66 pct)",
            "test_split":     "small_size (<33 pct, unseen)",
            "n_train":        int(mid_mask.sum()),
            "n_test":         int(small_mask.sum()),
            "extrapolation_auroc": round(auroc, 4) if not np.isnan(auroc) else "nan",
            "ci_lo_95":       round(ci_lo, 4)  if not np.isnan(ci_lo)  else "nan",
            "ci_hi_95":       round(ci_hi, 4)  if not np.isnan(ci_hi)  else "nan",
            "size_threshold_p33": round(float(p33), 2),
            "size_threshold_p66": round(float(p66), 2),
        })

    _write_csv(out_dir / "boundary_B4_extrapolation.csv", rows)


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PC-B 失败边界拟合 + 跨集外推 + strong baseline")
    _root = Path(__file__).resolve().parent.parent
    _res  = _root / "results"

    parser.add_argument("--brats-score-csv",
                        default=str(_res / "anomaly_scores_brats_ae.csv"),
                        help="BraTS anomaly score csv (train_recon_ae.py 产出)")
    parser.add_argument("--brats-strat-csv",
                        default=str(_res / "stratify_interact_ae.csv"),
                        help="(可选) BraTS 分层 csv (size_px, contrast 列)")
    parser.add_argument("--brats-conspicuity-csv",
                        default=str(_res / "conspicuity_features.csv"),
                        help="(可选) BraTS conspicuity proxy csv (size_proxy/contrast_proxy)")
    parser.add_argument("--ham-score-csv",
                        default=str(_res / "anomaly_scores_isic_ae.csv"),
                        help="(可选) HAM anomaly score csv (B2 跨集外推)")
    parser.add_argument("--ham-conspicuity-csv",
                        default=str(_res / "conspicuity_features_ham.csv"),
                        help="(可选) HAM conspicuity proxy csv")
    parser.add_argument("--out-dir",
                        default=str(_res))
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ---- 加载 BraTS 数据 ----
    brats_cols_needed = ["anomaly_score", "label"]
    brats_data = load_csv_cols(args.brats_score_csv, brats_cols_needed)
    print(f"[boundary] brats rows: {len(brats_data['anomaly_score'])}")

    # 合并 size/contrast 列 (优先 strat csv，其次 conspicuity proxy)
    def _merge_col(data, src_csv, col_name, alias):
        if not src_csv or not Path(src_csv).exists():
            return
        try:
            extra = load_csv_cols(src_csv, [col_name])
            if len(extra.get(col_name, [])) == len(data["anomaly_score"]):
                data[alias] = extra[col_name]
        except Exception as e:
            print(f"[warn] merge {col_name} from {src_csv}: {e}")

    # 尝试从 stratify csv 读 size_px/contrast
    if Path(args.brats_strat_csv).exists():
        strat = {}
        with open(args.brats_strat_csv, newline="") as f:
            for row in csv.DictReader(f):
                fn = row.get("filename", "")
                strat[fn] = (_safe_float(row.get("size_px", "nan")),
                             _safe_float(row.get("contrast", "nan")))
        # 按 brats_score_csv 行顺序对齐
        with open(args.brats_score_csv, newline="") as f:
            fnames = [r["filename"] for r in csv.DictReader(f)
                      if r.get("split") == "tumor"]
        sizes_aligned     = np.array([strat.get(fn, (float("nan"), float("nan")))[0]
                                       for fn in fnames])
        contrasts_aligned = np.array([strat.get(fn, (float("nan"), float("nan")))[1]
                                       for fn in fnames])
        # 过滤对应行
        valid = ~np.isnan(sizes_aligned) & ~np.isnan(contrasts_aligned)
        if valid.sum() > 10:
            brats_data["size_px"]  = sizes_aligned[valid]
            brats_data["contrast"] = contrasts_aligned[valid]
            brats_data["anomaly_score"] = brats_data["anomaly_score"][:valid.sum()]
            brats_data["label"]         = brats_data["label"][:valid.sum()]

    # fallback: conspicuity proxy 作 size/contrast 代理
    if "size_px" not in brats_data:
        if Path(args.brats_conspicuity_csv).exists():
            consp = load_csv_cols(args.brats_conspicuity_csv,
                                  ["sigma_global", "cnr_proxy_otsu"])
            n = len(brats_data["anomaly_score"])
            brats_data["size_proxy"]     = consp["sigma_global"][:n]
            brats_data["contrast_proxy"] = consp["cnr_proxy_otsu"][:n]
        else:
            # 无协变量时用 anomaly_score 作 proxy（退化对比用）
            brats_data["size_proxy"]     = brats_data["anomaly_score"]
            brats_data["contrast_proxy"] = brats_data["anomaly_score"]

    # ---- B1 ----
    brats_data = run_b1(brats_data, out_dir)

    # ---- 加载 HAM 数据 ----
    ham_data = None
    if args.ham_score_csv and Path(args.ham_score_csv).exists():
        ham_data = load_csv_cols(args.ham_score_csv, ["anomaly_score", "label"])
        if Path(args.ham_conspicuity_csv).exists():
            hc = load_csv_cols(args.ham_conspicuity_csv, ["sigma_global", "cnr_proxy_otsu"])
            n  = len(ham_data["anomaly_score"])
            ham_data["sigma_global"]  = hc["sigma_global"][:n]
            ham_data["cnr_proxy_otsu"] = hc["cnr_proxy_otsu"][:n]
        print(f"[boundary] ham rows: {len(ham_data['anomaly_score'])}")

    # ---- B2 ----
    run_b2(brats_data, ham_data, out_dir)

    # ---- B3 ----
    run_b3(brats_data, out_dir)

    # ---- B4 ----
    run_b4(brats_data, out_dir)

    print("[boundary] all done.")
