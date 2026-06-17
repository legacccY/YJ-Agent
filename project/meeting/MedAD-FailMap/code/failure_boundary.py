"""
failure_boundary.py — PC-B 失败边界拟合 + 跨集外推 + strong baseline（纯 CPU）
服务: MedAD-FailMap Phase 0+1, PC-B (B1/B2/B3/B4)
Phase 1 新增: run_b2_extrap — BraTS fit / 目标集 transform-only 零调参外推

流程:
  B1: 在 BraTS 拟合失败边界 f(size, contrast) — 逻辑回归 + 浅 GBM
  B2: 跨集零调参外推 -> HAM-NV (AUROC + 集内 vs 集外对比)  [Phase 0 proxy]
  B2-extrap: BraTS-fit clf + scaler / 目标集 transform-only（Phase 1 真 mask 口径）
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
from sklearn.preprocessing import StandardScaler


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
    """
    Bootstrap AUROC 置信区间（双侧 1-alpha CI），纯 numpy + sklearn。
    alpha=0.05 → 95% CI（默认，B3 T8.x 用）
    alpha=0.0125 → 98.75% CI（T6/T7 Bonferroni 4 并入 F-B family，
                   来源: 05_preregistration C 节 α=0.05/4 Bonferroni）
    """
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

def fit_boundary(X, y, model_type="lr", seed=42):
    """
    model_type = "lr"  -> LogisticRegression (C=1.0)
    model_type = "gbm" -> GradientBoostingClassifier (n_estimators=50, max_depth=3)
    seed: random_state（PR-5 多 seed 支持）
    🔴 TODO: GBM 超参 (n_estimators/max_depth) 未找到领域官方设定，
             此处 n_estimators=50, max_depth=3 为浅树经验值（防过拟合），
             需 researcher/主线确认。
    """
    if model_type == "lr":
        clf = LogisticRegression(C=1.0, max_iter=1000, solver="lbfgs",
                                 random_state=seed)
    else:
        clf = GradientBoostingClassifier(
            n_estimators=50, max_depth=3, learning_rate=0.1,
            random_state=seed,
        )
    clf.fit(X, y)
    return clf


def run_b1(brats_data, out_dir, threshold_pct=90):
    """B1: BraTS 拟合失败=f(size,contrast) 边界"""
    scores   = brats_data["anomaly_score"]
    y_detect = (scores >= np.percentile(scores, threshold_pct)).astype(int)
    y_fail   = 1 - y_detect   # 失败=未检出
    # 注: y_fail 由 anomaly_score 派生（score < top-10% threshold）。
    # B3 strong baseline 对比时须报告为「score 自洽性」非独立 GT。
    # 即 B3 衡量的是 size/contrast 能否预测 score 排序，而非 score 之外独立失败标准。
    # ACCEPTANCE ③ 的循环论证风险：若 size/contrast 与 score 本身强相关，
    # 则 B1 分类器直接捕获了 score 的协变量而非"真正的预测失败能力"。

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
            # T6 (B2 跨集外推): α=0.05/4 Bonferroni 并入 F-B family → 98.75% CI
            # 来源: 05_preregistration C 节冻结 (选项 a)
            ci_lo, ci_hi = bootstrap_auroc_ci(ham_y_fail, proba, alpha=0.0125)

        rows.append({
            "model":             feat_name,
            "cross_domain_auroc": round(auroc, 4) if not np.isnan(auroc) else "nan",
            "ci_lo_9875":        round(ci_lo, 4)  if not np.isnan(ci_lo) else "nan",   # 98.75% CI lower (α=0.05/4 Bonf)
            "ci_hi_9875":        round(ci_hi, 4)  if not np.isnan(ci_hi) else "nan",   # 98.75% CI upper
            "ci_alpha":          0.0125,
            "n_ham":             len(ham_y_fail),
            "n_fail_ham":        int(ham_y_fail.sum()),
            "note": "T6 BraTS->HAM zero-shot; CI 98.75% (α=0.0125 Bonf/4 F-B family); size/contrast proxied by sigma/cnr_otsu",
        })

    _write_csv(out_dir / "boundary_B2_extrapolation.csv", rows)


# ============================================================
# B2-extrap (Phase 1): BraTS-fit clf+scaler / 目标集 transform-only 零调参外推
# ============================================================

def fit_boundary_with_scaler(X, y, seed=42):
    """
    Phase 1 真同构口径：StandardScaler + LogisticRegression(C=1.0,lbfgs) 在 BraTS fit。
    返回 (scaler, clf)，scaler.mean_/scale_ 冻结后目标集不得再 fit。

    PR-3: proxy-clf + scaler 零调参（BraTS fit/目标 transform 不 refit），
    已烤入 run_b2_extrap 的断言。
    """
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    clf = LogisticRegression(C=1.0, max_iter=1000, solver="lbfgs",
                             random_state=seed)
    clf.fit(X_scaled, y)
    return scaler, clf


def run_b2_extrap(
    brats_data,
    target_data,
    out_dir,
    target_name="ham",
    seed=42,
    detected_pct=90.0,
):
    """
    Phase 1 B2-extrap: BraTS 真 mask 口径 [size_px, contrast] fit
    目标集（HAM/METS）同口径特征 transform predict，绝不 refit。

    零调参铁律（PR-3）：
      scaler 仅 BraTS fit → target transform（断言 mean_/scale_ 前后不变）
      clf 仅 BraTS fit → target predict_proba（无 refit）

    PR-1: y_fail 在目标集病灶子集内算 P{detected_pct}（detected_pct 参数化）
    PR-5: seed 参数化（多 seed 聚合时传不同 seed）
    Bootstrap CI 98.75%（α=0.0125，沿用 Phase 0 Bonferroni 4 并入 F-B family）

    输入:
      brats_data:   dict，需含 size_px / contrast / anomaly_score（来自 run_b1 预处理后）
      target_data:  dict，需含 size_px / contrast / anomaly_score（来自 lesion_features.py）
                    key 可含 _filenames 列表（用于 filename join 验证）

    输出:
      extrap_B2_<target_name>.csv — 列:
        target / cross_domain_auroc / ci_lo_9875 / ci_hi_9875 /
        in_domain_auroc / ratio_cross_over_in /
        pass_ratio_80 / n_target / n_fail / seed
    """
    if target_data is None:
        print(f"[B2-extrap] target_data ({target_name}) not provided, skip")
        return

    # ---- BraTS fit ----
    brats_size = brats_data.get("size_px", brats_data.get("size_proxy"))
    brats_contrast = brats_data.get("contrast", brats_data.get("contrast_proxy"))
    if brats_size is None or brats_contrast is None:
        print("[B2-extrap] BraTS size/contrast 缺失，skip")
        return

    brats_scores = brats_data["anomaly_score"]
    threshold_pct = brats_data.get("_threshold_pct", 90)
    brats_y_fail = 1 - (
        (brats_scores >= np.percentile(brats_scores, threshold_pct)).astype(int)
    )

    X_brats = np.column_stack([brats_size, brats_contrast])
    scaler, clf = fit_boundary_with_scaler(X_brats, brats_y_fail, seed=seed)

    # 快照 scaler 参数（用于断言目标集 transform 后不被篡改）
    mean_snapshot = scaler.mean_.copy()
    scale_snapshot = scaler.scale_.copy()

    # in-domain AUROC（BraTS 上）
    X_brats_scaled = scaler.transform(X_brats)
    # 断言 scaler 未被 transform 改变（PR-3）
    assert np.allclose(scaler.mean_, mean_snapshot), "scaler.mean_ 被意外修改！"
    assert np.allclose(scaler.scale_, scale_snapshot), "scaler.scale_ 被意外修改！"

    if len(np.unique(brats_y_fail)) >= 2:
        in_domain_auroc = float(roc_auc_score(brats_y_fail,
                                               clf.predict_proba(X_brats_scaled)[:, 1]))
    else:
        in_domain_auroc = float("nan")

    # ---- 目标集 transform-only（绝不 refit）----
    target_size = target_data.get("size_px")
    target_contrast = target_data.get("contrast")
    if target_size is None or target_contrast is None:
        print(f"[B2-extrap] target {target_name} 缺少 size_px/contrast，skip")
        return

    # PR-1: y_fail 在目标集病灶子集内算 P{detected_pct}
    target_scores = target_data.get("anomaly_score")
    if target_scores is not None and len(target_scores) >= 10:
        valid_mask = ~np.isnan(target_scores)
        if valid_mask.sum() >= 10:
            thr = float(np.percentile(target_scores[valid_mask], detected_pct))
            target_y_fail = np.where(
                valid_mask,
                1 - (target_scores >= thr).astype(int),
                np.nan,
            ).astype(float)
            # 只保留有效（非 nan）行
            valid_idx = np.where(~np.isnan(target_y_fail))[0]
            target_y_fail = target_y_fail[valid_idx].astype(int)
            target_size_v = target_size[valid_idx]
            target_contrast_v = target_contrast[valid_idx]
        else:
            print(f"[B2-extrap] {target_name}: insufficient valid scores, skip")
            return
    else:
        # 无 anomaly score → 无法算 y_fail
        print(f"[B2-extrap] {target_name}: no anomaly_score in target_data, skip")
        return

    X_target = np.column_stack([target_size_v, target_contrast_v])
    X_target_scaled = scaler.transform(X_target)

    # 断言：transform 后 scaler 参数不变（PR-3 硬断言）
    assert np.allclose(scaler.mean_, mean_snapshot), \
        "PR-3 违反：scaler.mean_ 在 target transform 后被改变！"
    assert np.allclose(scaler.scale_, scale_snapshot), \
        "PR-3 违反：scaler.scale_ 在 target transform 后被改变！"

    if len(np.unique(target_y_fail)) < 2:
        cross_domain_auroc = float("nan")
        ci_lo = ci_hi = float("nan")
    else:
        proba_target = clf.predict_proba(X_target_scaled)[:, 1]
        cross_domain_auroc = float(roc_auc_score(target_y_fail, proba_target))
        # CI 98.75%（α=0.0125，沿用 Phase 0 F-B family Bonferroni 4）
        ci_lo, ci_hi = bootstrap_auroc_ci(
            target_y_fail, proba_target, alpha=0.0125, seed=seed
        )

    ratio_cross_over_in = (
        cross_domain_auroc / in_domain_auroc
        if (not np.isnan(cross_domain_auroc) and not np.isnan(in_domain_auroc)
            and in_domain_auroc > 0)
        else float("nan")
    )
    # pass_ratio_80: 跨集 ≥ 集内×0.80（Gate1 判据）
    pass_ratio_80 = int(
        not np.isnan(ratio_cross_over_in) and ratio_cross_over_in >= 0.80
    )

    row = {
        "target":               target_name,
        "cross_domain_auroc":   round(cross_domain_auroc, 4) if not np.isnan(cross_domain_auroc) else "nan",
        "ci_lo_9875":           round(ci_lo, 4)  if not np.isnan(ci_lo)  else "nan",
        "ci_hi_9875":           round(ci_hi, 4)  if not np.isnan(ci_hi)  else "nan",
        "in_domain_auroc":      round(in_domain_auroc, 4) if not np.isnan(in_domain_auroc) else "nan",
        "ratio_cross_over_in":  round(ratio_cross_over_in, 4) if not np.isnan(ratio_cross_over_in) else "nan",
        "pass_ratio_80":        pass_ratio_80,
        "n_target":             len(target_y_fail),
        "n_fail":               int(target_y_fail.sum()),
        "seed":                 seed,
        "detected_pct":         detected_pct,
        "note": (
            f"Phase1 B2-extrap PR-3 zero-adapt: BraTS fit scaler+clf, "
            f"{target_name} transform-only; "
            f"CI 98.75% (α=0.0125 Bonf/4 F-B family); "
            f"PR-1 y_fail=lesion-only P{detected_pct:.0f}; "
            f"PR-5 seed={seed}"
        ),
    }

    out_csv = Path(out_dir) / f"extrap_B2_{target_name}.csv"
    _write_csv(out_csv, [row])
    return row


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
# B4: Extrapolation (训中等 size -> 测未见 size 区域，两方向)
# ============================================================

def run_b4(brats_data, out_dir):
    """
    B4: extrapolation AUROC — 两个外推方向（reviewer 授权 split 重设计，2026-06-17）
    训练集: 中等 size (33~66 percentile，两方向共用)
    方向A: test = small (<P33, unseen) — 保留作透明，原设计；已知退化（test 近全 fail）
    方向B: test = large (>P66, unseen) — 新·信息性主读数；大病灶检出率高，有 detected variance

    判断准则（reviewer 前置定，非事后调）:
      test split 须 n_test_detected >= 20 且 y_fail 含两类 → interpretable=1

    冻结量（不得改动）:
      - y_fail 派生口径: anomaly_score < P90 threshold（同 run_b1 threshold_pct=90）
      - size 三等分切点: P33/P66（同 stratify_eval.py）
      - CI alpha: 0.0125（98.75% Bonferroni α=0.05/4 F-B family; 05_preregistration C 节）
      - fit_boundary lr（逻辑回归 C=1.0）

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
    large_mask = size_arr > p66   # 方向B: 新增大 size 测试集

    if mid_mask.sum() < 10:
        print(f"[B4] insufficient mid samples: mid={mid_mask.sum()}, skip")
        return

    # 两外推方向定义
    # (test_label_str, mask, direction_note)
    directions = [
        (
            "small_size (<33 pct, unseen, DEGENERATE)",
            small_mask,
            "方向A 原设计·透明保留: test 近全 fail 无 outcome variance, AUROC 不可解释, 仅透明保留",
        ),
        (
            "large_size (>66 pct, unseen)",
            large_mask,
            "方向B 信息性 within-domain 外推: test 有 detected variance, 大病灶检出率高",
        ),
    ]

    rows = []
    for test_split_str, test_mask, direction_note in directions:
        # 方向样本不足则 skip 标 note
        if test_mask.sum() < 5:
            for feat_name in ("size+contrast_lr", "size_only_lr"):
                rows.append({
                    "model":          feat_name,
                    "train_split":    "mid_size (33~66 pct)",
                    "test_split":     test_split_str,
                    "n_train":        int(mid_mask.sum()),
                    "n_test":         int(test_mask.sum()),
                    "n_test_detected":  0,
                    "interpretable":    0,
                    "extrapolation_auroc": "nan",
                    "ci_lo_9875":     "nan",
                    "ci_hi_9875":     "nan",
                    "ci_alpha":       0.0125,
                    "size_threshold_p33": round(float(p33), 2),
                    "size_threshold_p66": round(float(p66), 2),
                    "note": f"SKIP: test 样本不足 (<5); {direction_note}",
                })
            continue

        for feat_name, X in [("size+contrast_lr", X2), ("size_only_lr", X1)]:
            X_mid    = X[mid_mask]
            y_mid    = y_fail[mid_mask]
            X_test   = X[test_mask]
            y_test   = y_fail[test_mask]

            # n_test_detected: detected==1 即 y_fail==0
            n_test_detected = int((y_test == 0).sum())
            # interpretable: ≥20 detected 且 test 集含两类
            interpretable = int(n_test_detected >= 20 and len(np.unique(y_test)) >= 2)

            if len(np.unique(y_mid)) < 2 or len(np.unique(y_test)) < 2:
                auroc = float("nan")
                ci_lo = ci_hi = float("nan")
            else:
                clf   = fit_boundary(X_mid, y_mid, "lr")
                proba = clf.predict_proba(X_test)[:, 1]
                auroc = float(roc_auc_score(y_test, proba))
                # T7 (B4 extrapolation): α=0.05/4 Bonferroni 并入 F-B family → 98.75% CI
                # 来源: 05_preregistration C 节冻结 (选项 a)
                ci_lo, ci_hi = bootstrap_auroc_ci(y_test, proba, alpha=0.0125)

            rows.append({
                "model":          feat_name,
                "train_split":    "mid_size (33~66 pct)",
                "test_split":     test_split_str,
                "n_train":        int(mid_mask.sum()),
                "n_test":         int(test_mask.sum()),
                "n_test_detected":  n_test_detected,
                "interpretable":    interpretable,
                "extrapolation_auroc": round(auroc, 4) if not np.isnan(auroc) else "nan",
                "ci_lo_9875":     round(ci_lo, 4)  if not np.isnan(ci_lo)  else "nan",   # 98.75% CI lower (α=0.0125 Bonf/4 F-B)
                "ci_hi_9875":     round(ci_hi, 4)  if not np.isnan(ci_hi)  else "nan",   # 98.75% CI upper
                "ci_alpha":       0.0125,
                "size_threshold_p33": round(float(p33), 2),
                "size_threshold_p66": round(float(p66), 2),
                "note": f"T7 extrapolation; CI 98.75% (α=0.0125 Bonf/4 F-B family; 05_preregistration C 节); {direction_note}",
            })

    _write_csv(out_dir / "boundary_B4_extrapolation.csv", rows)


# ============================================================
# PR-5: 多 seed 聚合 — seed 间最差 CI 下界
# ============================================================

def aggregate_seed_results(
    seed_csv_paths,
    out_csv=None,
    target_name="ham",
):
    """
    PR-5 跨 seed 聚合：读多个 extrap_B2_<target>_seed*.csv（每 seed 一行），
    取 seed 间最差 CI 下界（min ci_lo_9875 across seeds）作为保守外推判据。

    「最差」定义（PR-5 reviewer 定论）：
      对每 seed 的 ci_lo_9875 取最小值（最差 CI 下界），不是最差 seed 点估计。
      判据：min_ci_lo_across_seeds >= 0.70 = PASS 门（沿用 05 §E CI 门不调松）。

    PR-4 校正基数注释（不改逻辑，仅标注）：
      - F-B' family CI（本函数 ci_lo_9875）基数=「对数（pairings）」：
        N_pairs = ≥2 对外推（HAM+METS等），Bonferroni 对 pair 数校正（α/N_pairs）。
        CI 本身已按 α=0.0125（05_preregistration C 节 Bonf/4）算，此为 per-pair CI。
      - SB Δ p 值（B3）基数=「对比数（comparisons）」：boundary vs SB1 + boundary vs SB2 = 2。
        Holm 校正基数=2（非 pair 数）。
      # TODO: PR-4 CI 类 vs Δ 类校正基数文字 待 05 冻结确认（此注释为 Phase 1 暂定，
              冻结前不应以此为判据文字）。

    Args:
        seed_csv_paths: list of str/Path，每个是 extrap_B2_<target>_seed*.csv 路径
        out_csv:        (可选) 聚合输出 csv 路径
        target_name:    目标集名称，写入输出

    输出 csv schema（extrap_B2_<target>_agg.csv）：
      target / min_ci_lo_across_seeds / mean_auroc / seeds_n / pass_ci_70 /
      seed_list / note
    """
    rows = []
    for p in seed_csv_paths:
        p = Path(p)
        if not p.exists():
            print(f"[seed_agg] WARNING: 文件不存在，跳过: {p}")
            continue
        with open(p, newline="") as f:
            for row in csv.DictReader(f):
                rows.append(row)

    if not rows:
        print(f"[seed_agg] {target_name}: 无有效 seed csv，跳过聚合")
        return None

    ci_los = []
    aurocs = []
    seeds_used = []
    for r in rows:
        ci_lo_str = r.get("ci_lo_9875", "nan")
        auroc_str = r.get("cross_domain_auroc", "nan")
        seed_str = r.get("seed", "nan")
        try:
            ci_lo = float(ci_lo_str)
            if not np.isnan(ci_lo):
                ci_los.append(ci_lo)
        except (TypeError, ValueError):
            pass
        try:
            auroc = float(auroc_str)
            if not np.isnan(auroc):
                aurocs.append(auroc)
        except (TypeError, ValueError):
            pass
        try:
            seeds_used.append(int(float(seed_str)))
        except (TypeError, ValueError):
            pass

    if not ci_los:
        print(f"[seed_agg] {target_name}: 所有 seed 的 ci_lo_9875 均为 nan，无法聚合")
        return None

    min_ci_lo = float(min(ci_los))
    mean_auroc = float(np.mean(aurocs)) if aurocs else float("nan")
    seeds_n = len(rows)
    pass_ci_70 = int(min_ci_lo >= 0.70)  # Gate1 PASS 门（05 §E）

    agg_row = {
        "target":                target_name,
        "min_ci_lo_across_seeds": round(min_ci_lo, 4),
        "mean_auroc":            round(mean_auroc, 4) if not np.isnan(mean_auroc) else "nan",
        "seeds_n":               seeds_n,
        "pass_ci_70":            pass_ci_70,
        "seed_list":             ";".join(str(s) for s in seeds_used),
        "note": (
            f"PR-5 seed-agg worst: min ci_lo_9875={min_ci_lo:.4f} across {seeds_n} seeds; "
            f"pass_ci_70={pass_ci_70} (gate1 threshold=0.70, 05 §E); "
            f"PR-4 CI 基数=对数(Bonf/N_pairs), Δ 基数=对比数(Holm/2)"
            f" # TODO: PR-4 校正基数文字 待 05 冻结"
        ),
    }

    if out_csv:
        out_csv = Path(out_csv)
        _write_csv(out_csv, [agg_row])
        print(f"[seed_agg] {target_name}: min_ci_lo={min_ci_lo:.4f}, "
              f"pass_ci_70={pass_ci_70}, seeds_n={seeds_n}")

    return agg_row


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
                        default=str(_res / "stratify_per_image_ae.csv"),
                        help="BraTS per-image 分层 csv (filename, size_px, contrast 列;"
                             " 必须 per-image 而非 interact 聚合表,否则无 filename 无法 join)")
    parser.add_argument("--brats-conspicuity-csv",
                        default=str(_res / "conspicuity_features_tumor.csv"),
                        help="(可选) BraTS conspicuity proxy csv (size_proxy/contrast_proxy)")
    parser.add_argument("--ham-score-csv",
                        default=str(_res / "anomaly_scores_isic_ae.csv"),
                        help="(可选) HAM anomaly score csv (Phase 0 B2 代理外推)")
    parser.add_argument("--ham-conspicuity-csv",
                        default=str(_res / "conspicuity_features_ham.csv"),
                        help="(可选) HAM conspicuity proxy csv (Phase 0)")
    # ---- Phase 1 新增参数 ----
    parser.add_argument("--target-lesion-csv",
                        default=None,
                        help="Phase 1: 目标集真 mask 特征 csv（lesion_features.py 产出）"
                             "；含 size_px/contrast/anomaly_score/filename 列")
    parser.add_argument("--target-name",
                        default="ham",
                        help="Phase 1: 目标集名称（ham/mets），用于输出文件名")
    parser.add_argument("--seed",
                        type=int, default=42,
                        help="PR-5: random seed（影响 clf/bootstrap/np/random；默认 42）")
    parser.add_argument("--seed-agg",
                        default="worst",
                        choices=["worst", "median"],
                        help="PR-5: 多 seed 跑后聚合方式（worst=取最差 seed CI 下界）"
                             " # TODO: PR-5 聚合方式待冻结（worst=取最差 seed CI 下界）")
    parser.add_argument("--seed-agg-csvs", nargs="+", default=None,
                        help="PR-5: 多 seed extrap_B2_*.csv 路径列表（空格分隔），"
                             "传入时自动跑 aggregate_seed_results（worst 聚合）输出 extrap_B2_<target>_agg.csv。"
                             "不传则仅跑单 seed。")
    parser.add_argument("--detected-pct",
                        type=float, default=90.0,
                        help="PR-1: 跨集 detected 语义（目标集病灶子集内 P{pct}=y_fail）"
                             " # TODO: PR-1 待冻结")
    parser.add_argument("--out-dir",
                        default=str(_res))
    parser.add_argument("--threshold-pct",
                        type=float, default=90.0,
                        help="检出阈值百分位，默认 90=05 预登记冻结值；三档敏感性扫描用 95/85")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ---- 加载 BraTS 数据 (只取 tumor 行，normal 无 size 定义) ----
    # Bug fix: load_csv_cols 读全行 (normal+tumor)，normal 无 size 定义导致索引错配。
    # 改为按 filename 显式 join: 先读 score csv 只取 split=="tumor" 行，
    # 保留 filename 作 join key；strat 按 filename dict 匹配，不按行序截断。
    brats_data = {}
    tumor_score_rows = []   # list of {filename, anomaly_score, label}
    with open(args.brats_score_csv, newline="") as f:
        for row in csv.DictReader(f):
            if row.get("split", row.get("label", "")) in ("tumor", "1"):
                # split=="tumor" 优先；若无 split 列则 label==1
                s = _safe_float(row.get("anomaly_score", "nan"))
                l = _safe_float(row.get("label", "1"))
                if not np.isnan(s):
                    tumor_score_rows.append({
                        "filename":     row.get("filename", ""),
                        "anomaly_score": s,
                        "label":         l,
                    })
    if not tumor_score_rows:
        raise RuntimeError(f"[boundary] brats score csv 中无 split==tumor 行: {args.brats_score_csv}")
    brats_data["_filenames"]   = [r["filename"] for r in tumor_score_rows]
    brats_data["anomaly_score"] = np.array([r["anomaly_score"] for r in tumor_score_rows])
    brats_data["label"]         = np.array([r["label"]         for r in tumor_score_rows])
    print(f"[boundary] brats tumor rows: {len(brats_data['anomaly_score'])}")

    # 尝试从 stratify csv 按 filename join 读 size_px/contrast
    if Path(args.brats_strat_csv).exists():
        strat = {}
        with open(args.brats_strat_csv, newline="") as f:
            for row in csv.DictReader(f):
                fn = row.get("filename", "")
                strat[fn] = (_safe_float(row.get("size_px", "nan")),
                             _safe_float(row.get("contrast", "nan")))
        # 按 tumor filename list 显式 join（不按行序截断）
        fnames = brats_data["_filenames"]
        sizes_aligned     = np.array([strat.get(fn, (float("nan"), float("nan")))[0]
                                       for fn in fnames])
        contrasts_aligned = np.array([strat.get(fn, (float("nan"), float("nan")))[1]
                                       for fn in fnames])
        valid = ~np.isnan(sizes_aligned) & ~np.isnan(contrasts_aligned)
        if valid.sum() > 10:
            # 只保留成功 join 的行（filename 在 strat 中存在且值非 nan）
            brats_data["size_px"]       = sizes_aligned[valid]
            brats_data["contrast"]      = contrasts_aligned[valid]
            brats_data["anomaly_score"] = brats_data["anomaly_score"][valid]
            brats_data["label"]         = brats_data["label"][valid]
            brats_data["_filenames"]    = [fn for fn, v in zip(fnames, valid) if v]
            print(f"[boundary] after strat join: {valid.sum()} tumor rows with size/contrast")

    # fallback: conspicuity proxy 作 size/contrast 代理
    if "size_px" not in brats_data:
        if Path(args.brats_conspicuity_csv).exists():
            # conspicuity csv 只含 tumor 图，按 filename join
            consp_map = {}
            with open(args.brats_conspicuity_csv, newline="") as f:
                for row in csv.DictReader(f):
                    fn = row.get("filename", "")
                    consp_map[fn] = (
                        _safe_float(row.get("sigma_global", "nan")),
                        _safe_float(row.get("cnr_proxy_otsu", "nan")),
                    )
            fnames = brats_data["_filenames"]
            sg  = np.array([consp_map.get(fn, (float("nan"), float("nan")))[0] for fn in fnames])
            cnr = np.array([consp_map.get(fn, (float("nan"), float("nan")))[1] for fn in fnames])
            brats_data["size_proxy"]     = sg
            brats_data["contrast_proxy"] = cnr
        else:
            # 无协变量时用 anomaly_score 作 proxy（退化对比用）
            brats_data["size_proxy"]     = brats_data["anomaly_score"]
            brats_data["contrast_proxy"] = brats_data["anomaly_score"]

    # ---- B1 ----
    brats_data = run_b1(brats_data, out_dir, threshold_pct=args.threshold_pct)

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

    # ---- B2 (Phase 0 proxy，保留) ----
    run_b2(brats_data, ham_data, out_dir)

    # ---- B2-extrap (Phase 1: 真 mask 同口径 + scaler BraTS fit/target transform) ----
    if args.target_lesion_csv and Path(args.target_lesion_csv).exists():
        # 从 lesion_features.py 产出 csv 读 size_px/contrast/anomaly_score/filename
        target_data_p1 = {}
        target_rows = []
        with open(args.target_lesion_csv, newline="") as f:
            for row in csv.DictReader(f):
                target_rows.append(row)
        if target_rows:
            target_data_p1["_filenames"]   = [r.get("filename", "") for r in target_rows]
            target_data_p1["size_px"]      = np.array([
                _safe_float(r.get("size_px", "nan")) for r in target_rows
            ])
            target_data_p1["contrast"]     = np.array([
                _safe_float(r.get("contrast", "nan")) for r in target_rows
            ])
            target_data_p1["anomaly_score"] = np.array([
                _safe_float(r.get("anomaly_score", "nan")) for r in target_rows
            ])
            # 禁 [:n] 截断：filename join 验证（打印重复/缺失 warning）
            fns = target_data_p1["_filenames"]
            if len(set(fns)) != len(fns):
                print(f"[B2-extrap] WARNING: target csv 有重复 filename！"
                      f" ({len(fns)-len(set(fns))} 重复)")
            print(f"[boundary] target ({args.target_name}) rows: {len(target_rows)}")
            run_b2_extrap(
                brats_data, target_data_p1, out_dir,
                target_name=args.target_name,
                seed=args.seed,
                detected_pct=args.detected_pct,
            )
    else:
        if args.target_lesion_csv:
            print(f"[boundary] --target-lesion-csv 文件不存在，跳过 B2-extrap: "
                  f"{args.target_lesion_csv}")

    # ---- B3 ----
    run_b3(brats_data, out_dir)

    # ---- B4 ----
    run_b4(brats_data, out_dir)

    # ---- PR-5: 多 seed 聚合（若传 --seed-agg-csvs）----
    if args.seed_agg_csvs:
        agg_out = out_dir / f"extrap_B2_{args.target_name}_agg.csv"
        aggregate_seed_results(
            seed_csv_paths=args.seed_agg_csvs,
            out_csv=str(agg_out),
            target_name=args.target_name,
        )

    print(f"[boundary] all done. seed={args.seed}, seed_agg={args.seed_agg}")
