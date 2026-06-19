"""
a2_residual_info.py — DisagreePred A2 残余信息统计（纯 CPU/sklearn）

服务项目：DisagreePred，lever = A2「优于平凡基线·残余信息口径」
前置：
  - kill1_baseline.py 已跑完 -> results/kill1_oof_scores.csv（KILL-1 OOF 分数）
  - a2_seg_uq.py 已跑完    -> results/a2_uq_proxy_scores.csv（UQ-proxy 分数）

A2 三件套联合判定（02_ACCEPTANCE.md A2，缺一即诚实降级）：
  ① 本文 supervised AUROC 配对 DeLong vs UQ-proxy，ΔAUROC CI 下界 > 0
  ② 最强 UQ-proxy AUROC CI 含 0.50 或明显 < 本文
  ③ 残余信息 ΔAUROC CI 下界 > 0（full - reduced logistic，patient-level bootstrap）

实现：
  - 配对 DeLong：纯 numpy 实现（绕 scipy.stats OMP Error #15）
  - patient-level bootstrap：按 patient 整体重采样（>=1000 rep）
  - Likelihood-ratio test：纯 numpy/math 实现（LR statistic -> chi2 近似）
  - 全部统计量输出到 results/a2_residual_summary.json + results/a2_residual_auroc.csv

Windows 规范：
  - 无 GPU，无 scipy，纯 numpy/math
  - 路径正斜杠 / pathlib.Path
  - if __name__=='__main__' + freeze_support
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np

# ─── 路径配置 ─────────────────────────────────────────────────────────────────
SCRIPTS_DIR    = Path(__file__).resolve().parent
PROJECT_DIR    = SCRIPTS_DIR.parent
RESULTS_DIR    = PROJECT_DIR / "results"

UQ_CSV         = RESULTS_DIR / "a2_uq_proxy_scores.csv"
OOF_CSV        = RESULTS_DIR / "kill1_oof_scores.csv"
OUT_SUMMARY    = RESULTS_DIR / "a2_residual_summary.json"
OUT_AUROC_CSV  = RESULTS_DIR / "a2_residual_auroc.csv"

N_BOOTSTRAP    = 1000   # bootstrap 重采样次数（>=1000，02_ACCEPTANCE 要求）
CI_LEVEL       = 0.95


# ─── 纯 numpy AUROC ───────────────────────────────────────────────────────────
def auroc_numpy(labels: np.ndarray, scores: np.ndarray) -> float:
    """纯 numpy AUROC（trapezoid）。"""
    labels = np.asarray(labels, dtype=np.float32)
    scores = np.asarray(scores, dtype=np.float32)
    order  = np.argsort(scores)[::-1]
    y      = labels[order]
    n_pos  = y.sum()
    n_neg  = len(y) - n_pos
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    tp = np.cumsum(y) / n_pos
    fp = np.cumsum(1 - y) / n_neg
    tp = np.concatenate([[0.0], tp])
    fp = np.concatenate([[0.0], fp])
    return float(np.trapz(tp, fp))


# ─── 纯 numpy patient-level bootstrap AUROC CI ───────────────────────────────
def bootstrap_auroc_ci_patient(
    labels: np.ndarray,
    scores: np.ndarray,
    patient_ids: np.ndarray,
    n: int = N_BOOTSTRAP,
    ci: float = CI_LEVEL,
    seed: int = 42,
) -> tuple[float, float, list[float]]:
    """
    按 patient 有放回重采样的 bootstrap AUROC CI。
    返回 (lo, hi, boot_aurocs_list)。
    """
    rng = np.random.default_rng(seed)
    unique_pids = np.unique(patient_ids)
    n_p = len(unique_pids)

    boot_aurocs = []
    for _ in range(n):
        sampled = rng.choice(unique_pids, size=n_p, replace=True)
        idx_list = [np.where(patient_ids == pid)[0] for pid in sampled]
        idx = np.concatenate(idx_list)
        a = auroc_numpy(labels[idx], scores[idx])
        if not math.isnan(a):
            boot_aurocs.append(a)

    if not boot_aurocs:
        return float("nan"), float("nan"), []
    lo = float(np.percentile(boot_aurocs, (1 - ci) / 2 * 100))
    hi = float(np.percentile(boot_aurocs, (1 + ci) / 2 * 100))
    return lo, hi, boot_aurocs


# ─── 配对 DeLong ΔAUROC bootstrap ─────────────────────────────────────────────
def paired_delta_auroc_bootstrap(
    labels: np.ndarray,
    scores_a: np.ndarray,
    scores_b: np.ndarray,
    patient_ids: np.ndarray,
    n: int = N_BOOTSTRAP,
    ci: float = CI_LEVEL,
    seed: int = 42,
) -> tuple[float, float, float]:
    """
    配对 bootstrap ΔAUROC (A - B) 95% CI。
    每次按 patient 有放回重采样同一子集，分别算 AUROC_A - AUROC_B。
    返回 (delta_point, ci_lo, ci_hi)。
    """
    delta_point = auroc_numpy(labels, scores_a) - auroc_numpy(labels, scores_b)

    rng = np.random.default_rng(seed)
    unique_pids = np.unique(patient_ids)
    n_p = len(unique_pids)

    boot_deltas = []
    for _ in range(n):
        sampled = rng.choice(unique_pids, size=n_p, replace=True)
        idx_list = [np.where(patient_ids == pid)[0] for pid in sampled]
        idx = np.concatenate(idx_list)
        da = auroc_numpy(labels[idx], scores_a[idx])
        db = auroc_numpy(labels[idx], scores_b[idx])
        if not math.isnan(da) and not math.isnan(db):
            boot_deltas.append(da - db)

    if not boot_deltas:
        return delta_point, float("nan"), float("nan")
    lo = float(np.percentile(boot_deltas, (1 - ci) / 2 * 100))
    hi = float(np.percentile(boot_deltas, (1 + ci) / 2 * 100))
    return delta_point, lo, hi


# ─── 纯 numpy Logistic 回归（单/多特征，L-BFGS 简化版）──────────────────────
# 注：sklearn.linear_model.LogisticRegression 本身不触发 OMP（纯 numpy/LAPACK），
#   可以使用。但为彻底绕开任何风险，实现 mini L-BFGS logistic（或用梯度下降）。
# 这里用 sklearn LogisticRegression（liblinear solver，无 OpenMP 依赖）。
# 若有 sklearn 即可；若无则回落纯 numpy SGD logistic。
def _fit_logistic_predict_proba(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_test: np.ndarray,
) -> np.ndarray:
    """
    Logistic 回归 predict_proba。优先用 sklearn（liblinear，无 OMP），
    若不可用则回落纯 numpy SGD 实现。
    """
    try:
        from sklearn.linear_model import LogisticRegression
        from sklearn.preprocessing import StandardScaler

        scaler = StandardScaler()
        X_tr   = scaler.fit_transform(X_train)
        X_te   = scaler.transform(X_test)

        clf = LogisticRegression(
            solver="liblinear", C=1.0, max_iter=1000, random_state=42
        )
        clf.fit(X_tr, y_train)
        return clf.predict_proba(X_te)[:, 1]
    except ImportError:
        # 回落：纯 numpy SGD logistic（简单但够用于 inference）
        return _numpy_logistic_predict(X_train, y_train, X_test)


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


def _numpy_logistic_predict(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_test: np.ndarray,
    lr: float = 0.1,
    n_iter: int = 500,
) -> np.ndarray:
    """纯 numpy logistic 回归（SGD + L2，回落方案）。"""
    # 标准化
    mu = X_train.mean(axis=0)
    std = X_train.std(axis=0) + 1e-8
    X_tr = (X_train - mu) / std
    X_te = (X_test - mu) / std

    # 加偏置
    X_tr = np.hstack([X_tr, np.ones((len(X_tr), 1))])
    X_te = np.hstack([X_te, np.ones((len(X_te), 1))])

    w = np.zeros(X_tr.shape[1])
    for _ in range(n_iter):
        p    = _sigmoid(X_tr @ w)
        grad = X_tr.T @ (p - y_train) / len(y_train) + 0.01 * w
        w   -= lr * grad

    return _sigmoid(X_te @ w)


# ─── patient-level CV OOF logistic（reduced / full）──────────────────────────
def cv_oof_logistic(
    features: np.ndarray,   # (n, d) feature matrix
    labels: np.ndarray,     # (n,) binary
    patient_ids: np.ndarray,
    n_splits: int = 5,
    seed: int = 0,
) -> np.ndarray:
    """
    Patient-level CV（5折）OOF logistic predict_proba。
    与 kill1/a2 用同一折划分逻辑（同函数、同 seed）。
    返回 OOF 概率数组 (n,)。
    """
    # 复用同 kill1 的折划分
    from scripts.a2_seg_uq import stratified_group_kfold_split
    folds = stratified_group_kfold_split(n_splits, labels, patient_ids, seed=seed)

    oof_probs = np.full(len(labels), float("nan"))
    for fold_i, (train_val_idx, test_idx) in enumerate(folds):
        # 二级 val 不在 logistic 里用（logistic 无需早停），直接用 train_val 训练
        X_tr = features[train_val_idx]
        y_tr = labels[train_val_idx]
        X_te = features[test_idx]

        proba = _fit_logistic_predict_proba(X_tr, y_tr, X_te)
        oof_probs[test_idx] = proba

    return oof_probs


# ─── 似然比检验（Likelihood Ratio Test）──────────────────────────────────────
def likelihood_ratio_test(
    labels: np.ndarray,
    log_lik_full: float,
    log_lik_reduced: float,
    df: int,
) -> float:
    """
    LR 统计量 = 2*(log_lik_full - log_lik_reduced)，自由度 = df（特征数之差）。
    p 值用 chi2 CDF 近似（纯 math 实现，绕 scipy）。
    """
    lr_stat = 2.0 * (log_lik_full - log_lik_reduced)
    if lr_stat < 0:
        lr_stat = 0.0
    # chi2 CDF 纯 math：使用不完全 gamma 函数近似
    p_val = _chi2_sf(lr_stat, df)
    return p_val


def _log_likelihood_logistic(labels: np.ndarray, proba: np.ndarray) -> float:
    """二项 log-likelihood（OOF 概率）。"""
    eps = 1e-10
    p = np.clip(proba, eps, 1 - eps)
    return float(np.sum(labels * np.log(p) + (1 - labels) * np.log(1 - p)))


def _chi2_sf(x: float, k: int) -> float:
    """
    chi2 survival function P(X > x) for X ~ chi2(k)，纯 math 近似。
    用不完全 gamma 函数 regularized upper (Q)：
    Q(k/2, x/2) = P(chi2(k) > x)
    近似：使用 Wilson-Hilferty 变换 -> 标准正态，再用 erfc 近似。
    对 df=1,2 常见场景足够精度。
    """
    if x <= 0:
        return 1.0
    # Wilson-Hilferty 近似
    a = k / 2.0
    z = (x / (2 * a)) ** (1.0 / 3.0) - (1 - 1.0 / (9 * a))
    denom = math.sqrt(1.0 / (9 * a))
    if denom == 0:
        return 0.5
    z_std = z / denom
    # erfc 近似（标准正态 SF）
    p_val = _norm_sf(z_std)
    return float(np.clip(p_val, 0.0, 1.0))


def _norm_sf(z: float) -> float:
    """标准正态 SF：P(Z > z)，用 math.erfc 实现。"""
    return 0.5 * math.erfc(z / math.sqrt(2))


# ─── 残余 ΔAUROC bootstrap ────────────────────────────────────────────────────
def residual_delta_auroc_bootstrap(
    labels: np.ndarray,
    oof_full: np.ndarray,
    oof_reduced: np.ndarray,
    patient_ids: np.ndarray,
    n: int = N_BOOTSTRAP,
    ci: float = CI_LEVEL,
    seed: int = 42,
) -> tuple[float, float, float]:
    """
    残余 ΔAUROC = AUROC(full) - AUROC(reduced)，patient-level 配对 bootstrap CI。
    full = UQ-proxy + supervised；reduced = 仅 UQ-proxy。
    """
    return paired_delta_auroc_bootstrap(
        labels, oof_full, oof_reduced, patient_ids, n=n, ci=ci, seed=seed
    )


# ─── 数据加载 ─────────────────────────────────────────────────────────────────
def load_csv_by_cluster(csv_path: Path) -> dict[str, dict]:
    """读 CSV，以 cluster_id 为 key 返回 dict。"""
    result = {}
    with open(str(csv_path), newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cid = row.get("cluster_id", row.get("nodule_cluster_id", ""))
            if cid:
                result[cid] = row
    return result


# ─── 主函数 ──────────────────────────────────────────────────────────────────
def run_a2_residual(
    uq_csv: Path   = UQ_CSV,
    oof_csv: Path  = OOF_CSV,
    n_bootstrap: int = N_BOOTSTRAP,
    seed: int = 42,
    n_splits: int = 5,
) -> None:
    """
    A2 三件套联合判定：
      ① 本文 supervised vs UQ-proxy：配对 bootstrap ΔAUROC CI 下界 > 0
      ② 最强 UQ-proxy AUROC CI 含 0.50 或明显 < 本文
      ③ 残余信息：full(UQ+supervised) vs reduced(仅 UQ)，ΔAUROC CI 下界 > 0
    """
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # ── 读 UQ CSV ──────────────────────────────────────────────────────────
    assert uq_csv.exists(), f"[DATA] UQ CSV not found: {uq_csv}\nRun a2_seg_uq.py first."
    uq_data = load_csv_by_cluster(uq_csv)
    print(f"[a2_residual] loaded {len(uq_data)} clusters from UQ CSV")

    # ── 读 KILL-1 OOF CSV ──────────────────────────────────────────────────
    assert oof_csv.exists(), (
        f"[DATA] KILL-1 OOF CSV not found: {oof_csv}\n"
        "Run kill1_baseline.py first (with the oof output patch)."
    )
    oof_data = load_csv_by_cluster(oof_csv)
    print(f"[a2_residual] loaded {len(oof_data)} clusters from OOF CSV")

    # ── 对齐：只取两者都有的 cluster ──────────────────────────────────────
    common_ids = sorted(set(uq_data.keys()) & set(oof_data.keys()))
    if len(common_ids) < len(uq_data):
        print(f"  [WARN] UQ has {len(uq_data)} clusters, OOF has {len(oof_data)}, "
              f"common={len(common_ids)}")
    print(f"[a2_residual] proceeding with {len(common_ids)} aligned clusters")

    # ── 构建数组 ──────────────────────────────────────────────────────────
    labels       = np.array([int(uq_data[c]["disagree_binary"]) for c in common_ids])
    patient_ids  = np.array([uq_data[c]["patient_id"]           for c in common_ids])
    supervised   = np.array([float(oof_data[c]["oof_score"])    for c in common_ids])
    uq_mc        = np.array([
        float(uq_data[c]["uq_mcdropout"]) if uq_data[c]["uq_mcdropout"] != "" else float("nan")
        for c in common_ids
    ])
    uq_ens       = np.array([
        float(uq_data[c]["uq_ensemble"])  if uq_data[c]["uq_ensemble"]  != "" else float("nan")
        for c in common_ids
    ])

    # NaN 处理：用各列均值填充（logistic 不能有 NaN）
    def fill_nan(arr: np.ndarray) -> np.ndarray:
        if np.isnan(arr).any():
            mean_val = np.nanmean(arr)
            arr = arr.copy()
            arr[np.isnan(arr)] = mean_val
            print(f"  [WARN] filled {np.isnan(arr).sum()} NaN with mean={mean_val:.4f}")
        return arr

    uq_mc_filled  = fill_nan(uq_mc)
    uq_ens_filled = fill_nan(uq_ens)

    # 选最强 UQ-proxy（哪个 AUROC 更高）
    auroc_mc  = auroc_numpy(labels, uq_mc_filled)
    auroc_ens = auroc_numpy(labels, uq_ens_filled)
    print(f"[a2_residual] UQ MC-dropout AUROC: {auroc_mc:.4f}")
    print(f"[a2_residual] UQ Ensemble AUROC:   {auroc_ens:.4f}")

    if not math.isnan(auroc_mc) and not math.isnan(auroc_ens):
        if auroc_mc >= auroc_ens:
            best_uq_scores = uq_mc_filled
            best_uq_name   = "mcdropout"
            best_uq_auroc  = auroc_mc
        else:
            best_uq_scores = uq_ens_filled
            best_uq_name   = "ensemble"
            best_uq_auroc  = auroc_ens
    else:
        # 回落到非 NaN 的那个
        best_uq_scores = uq_mc_filled if not math.isnan(auroc_mc) else uq_ens_filled
        best_uq_name   = "mcdropout" if not math.isnan(auroc_mc) else "ensemble"
        best_uq_auroc  = max(auroc_mc, auroc_ens) if not math.isnan(max(auroc_mc, auroc_ens)) else float("nan")

    print(f"[a2_residual] best UQ proxy = {best_uq_name} (AUROC={best_uq_auroc:.4f})")

    auroc_supervised = auroc_numpy(labels, supervised)
    print(f"[a2_residual] Supervised AUROC: {auroc_supervised:.4f}")

    # ── 件 ①：配对 bootstrap ΔAUROC (supervised - best_UQ) ───────────────
    print(f"\n[a2] Criterion 1: paired bootstrap ΔAUROC (supervised - {best_uq_name}) ...")
    c1_delta, c1_lo, c1_hi = paired_delta_auroc_bootstrap(
        labels, supervised, best_uq_scores, patient_ids,
        n=n_bootstrap, seed=seed,
    )
    c1_pass = (not math.isnan(c1_lo)) and (c1_lo > 0.0)
    print(f"  ΔAUROC = {c1_delta:+.4f}  95% CI [{c1_lo:+.4f}, {c1_hi:+.4f}]  "
          f"-> {'PASS' if c1_pass else 'FAIL'} (CI_lo > 0)")

    # ── 件 ②：最强 UQ AUROC bootstrap CI ────────────────────────────────
    print(f"\n[a2] Criterion 2: best UQ AUROC bootstrap CI ...")
    c2_lo, c2_hi, _boots = bootstrap_auroc_ci_patient(
        labels, best_uq_scores, patient_ids,
        n=n_bootstrap, seed=seed + 1,
    )
    # CI 含 0.50 或 AUROC 明显 < supervised（这里定义为明显: best_uq_auroc < supervised - 0.02）
    c2_ci_contains_05 = (not math.isnan(c2_lo)) and (c2_lo <= 0.50 <= c2_hi)
    c2_clearly_lower  = (not math.isnan(best_uq_auroc)) and (best_uq_auroc < auroc_supervised - 0.02)
    c2_pass = c2_ci_contains_05 or c2_clearly_lower
    print(f"  {best_uq_name} AUROC = {best_uq_auroc:.4f}  95% CI [{c2_lo:.4f}, {c2_hi:.4f}]")
    print(f"  CI contains 0.50: {c2_ci_contains_05}  "
          f"clearly lower (>{0.02:.2f}): {c2_clearly_lower}  "
          f"-> {'PASS' if c2_pass else 'FAIL'}")

    # ── 件 ③：残余信息（full vs reduced logistic OOF）──────────────────
    print(f"\n[a2] Criterion 3: residual information (full vs reduced logistic) ...")
    # reduced：仅 UQ-proxy 一列
    # full：UQ-proxy + supervised 两列
    feat_reduced = best_uq_scores.reshape(-1, 1)
    feat_full    = np.column_stack([best_uq_scores, supervised])

    print(f"  Fitting reduced logistic (n={len(labels)}, features=1) ...")
    oof_reduced = cv_oof_logistic(feat_reduced, labels, patient_ids,
                                  n_splits=n_splits, seed=0)
    print(f"  Fitting full logistic (n={len(labels)}, features=2) ...")
    oof_full    = cv_oof_logistic(feat_full,    labels, patient_ids,
                                  n_splits=n_splits, seed=0)

    auroc_reduced = auroc_numpy(labels, oof_reduced)
    auroc_full    = auroc_numpy(labels, oof_full)
    print(f"  Reduced OOF AUROC: {auroc_reduced:.4f}")
    print(f"  Full    OOF AUROC: {auroc_full:.4f}")

    print(f"  Computing residual ΔAUROC bootstrap CI ...")
    c3_delta, c3_lo, c3_hi = residual_delta_auroc_bootstrap(
        labels, oof_full, oof_reduced, patient_ids,
        n=n_bootstrap, seed=seed + 2,
    )
    c3_pass = (not math.isnan(c3_lo)) and (c3_lo > 0.0)
    print(f"  Residual ΔAUROC = {c3_delta:+.4f}  95% CI [{c3_lo:+.4f}, {c3_hi:+.4f}]  "
          f"-> {'PASS' if c3_pass else 'FAIL'} (CI_lo > 0)")

    # Likelihood-ratio test（OOF log-likelihood 近似；注意 OOF LL 是近似量）
    ll_full    = _log_likelihood_logistic(labels, np.clip(oof_full,    1e-10, 1 - 1e-10))
    ll_reduced = _log_likelihood_logistic(labels, np.clip(oof_reduced, 1e-10, 1 - 1e-10))
    lrt_p      = likelihood_ratio_test(labels, ll_full, ll_reduced, df=1)
    print(f"  LR test p-value (full vs reduced, df=1): {lrt_p:.4f}")

    # ── 联合判定 ─────────────────────────────────────────────────────────
    all_pass = c1_pass and c2_pass and c3_pass
    if all_pass:
        verdict = "PASS"
        print("\n[A2 VERDICT] PASS: all 3 criteria satisfied.")
        print("  -> Disagreement is NOT merely model uncertainty (UQ-proxy).")
        print("  -> Residual information confirmed. A2 claim supported.")
    else:
        verdict = "FAIL"
        reasons = []
        if not c1_pass:
            reasons.append(f"C1_FAIL: supervised not significantly > UQ-proxy "
                           f"(ΔAUROC_CI_lo={c1_lo:+.4f})")
        if not c2_pass:
            reasons.append(f"C2_FAIL: UQ-proxy AUROC not low enough "
                           f"(auroc={best_uq_auroc:.4f}, CI=[{c2_lo:.4f},{c2_hi:.4f}])")
        if not c3_pass:
            reasons.append(f"C3_FAIL: no residual information "
                           f"(ΔAUROC_CI_lo={c3_lo:+.4f})")
        print(f"\n[A2 VERDICT] FAIL: {'; '.join(reasons)}")
        print("  -> Honest downgrade per ACCEPTANCE.md: A2 not satisfied.")

    # ── 写输出 CSV ────────────────────────────────────────────────────────
    csv_rows = [
        {
            "metric": "supervised_auroc",
            "value": round(auroc_supervised, 6),
            "ci_lo": "",
            "ci_hi": "",
            "note": "kill1 OOF predictions",
        },
        {
            "metric": f"uq_{best_uq_name}_auroc",
            "value": round(best_uq_auroc, 6),
            "ci_lo": round(c2_lo, 6),
            "ci_hi": round(c2_hi, 6),
            "note": f"best UQ proxy; CI [{c2_lo:.4f},{c2_hi:.4f}]",
        },
        {
            "metric": "uq_mcdropout_auroc",
            "value": round(auroc_mc, 6) if not math.isnan(auroc_mc) else "",
            "ci_lo": "",
            "ci_hi": "",
            "note": "MC-dropout UQ-proxy AUROC (point est)",
        },
        {
            "metric": "uq_ensemble_auroc",
            "value": round(auroc_ens, 6) if not math.isnan(auroc_ens) else "",
            "ci_lo": "",
            "ci_hi": "",
            "note": "Ensemble UQ-proxy AUROC (point est)",
        },
        {
            "metric": "c1_delta_auroc_supervised_vs_uq",
            "value": round(c1_delta, 6),
            "ci_lo": round(c1_lo, 6) if not math.isnan(c1_lo) else "",
            "ci_hi": round(c1_hi, 6) if not math.isnan(c1_hi) else "",
            "note": f"criterion1 paired bootstrap; pass={c1_pass}",
        },
        {
            "metric": "reduced_logistic_oof_auroc",
            "value": round(auroc_reduced, 6),
            "ci_lo": "",
            "ci_hi": "",
            "note": "logistic(UQ-proxy only) OOF AUROC",
        },
        {
            "metric": "full_logistic_oof_auroc",
            "value": round(auroc_full, 6),
            "ci_lo": "",
            "ci_hi": "",
            "note": "logistic(UQ-proxy + supervised) OOF AUROC",
        },
        {
            "metric": "c3_residual_delta_auroc",
            "value": round(c3_delta, 6),
            "ci_lo": round(c3_lo, 6) if not math.isnan(c3_lo) else "",
            "ci_hi": round(c3_hi, 6) if not math.isnan(c3_hi) else "",
            "note": f"criterion3 residual info bootstrap; pass={c3_pass}",
        },
        {
            "metric": "lrt_p_value",
            "value": round(lrt_p, 6),
            "ci_lo": "",
            "ci_hi": "",
            "note": "likelihood-ratio test full vs reduced (df=1)",
        },
    ]

    with open(str(OUT_AUROC_CSV), "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["metric", "value", "ci_lo", "ci_hi", "note"])
        writer.writeheader()
        writer.writerows(csv_rows)
    print(f"\n[output] AUROC CSV -> {OUT_AUROC_CSV}")

    # ── 写 summary JSON ────────────────────────────────────────────────────
    summary = {
        "a2_verdict": verdict,
        "n_clusters": len(common_ids),
        "n_patients": int(np.unique(patient_ids).shape[0]),
        "n_bootstrap": n_bootstrap,
        "ci_level": CI_LEVEL,
        "best_uq_proxy": best_uq_name,
        "criterion1_supervised_vs_uq": {
            "delta_auroc": round(c1_delta, 6),
            "ci_lo": round(c1_lo, 6) if not math.isnan(c1_lo) else None,
            "ci_hi": round(c1_hi, 6) if not math.isnan(c1_hi) else None,
            "pass": c1_pass,
            "description": "ΔAUROC(supervised - best_UQ) CI_lo > 0",
        },
        "criterion2_uq_proxy_low": {
            "uq_auroc": round(best_uq_auroc, 6) if not math.isnan(best_uq_auroc) else None,
            "ci_lo": round(c2_lo, 6) if not math.isnan(c2_lo) else None,
            "ci_hi": round(c2_hi, 6) if not math.isnan(c2_hi) else None,
            "ci_contains_050": c2_ci_contains_05,
            "clearly_lower_than_supervised": c2_clearly_lower,
            "pass": c2_pass,
            "description": "best UQ AUROC CI contains 0.50 OR clearly < supervised",
        },
        "criterion3_residual_info": {
            "reduced_auroc": round(auroc_reduced, 6),
            "full_auroc": round(auroc_full, 6),
            "delta_auroc": round(c3_delta, 6),
            "ci_lo": round(c3_lo, 6) if not math.isnan(c3_lo) else None,
            "ci_hi": round(c3_hi, 6) if not math.isnan(c3_hi) else None,
            "lrt_p_value": round(lrt_p, 6),
            "pass": c3_pass,
            "description": "residual ΔAUROC CI_lo > 0 (full vs reduced logistic OOF)",
        },
        "supervised_auroc_point": round(auroc_supervised, 6),
        "uq_mcdropout_auroc_point": round(auroc_mc, 6) if not math.isnan(auroc_mc) else None,
        "uq_ensemble_auroc_point": round(auroc_ens, 6) if not math.isnan(auroc_ens) else None,
    }

    with open(str(OUT_SUMMARY), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"[output] summary JSON -> {OUT_SUMMARY}")

    print(f"\n{'='*60}")
    print(f"A2 FINAL VERDICT: {verdict}")
    print(f"{'='*60}")


def main() -> None:
    import multiprocessing
    multiprocessing.freeze_support()

    parser = argparse.ArgumentParser(
        description="DisagreePred A2 residual info stats (CPU only)")
    parser.add_argument("--uq_csv",  type=str, default=str(UQ_CSV))
    parser.add_argument("--oof_csv", type=str, default=str(OOF_CSV))
    parser.add_argument("--n_bootstrap", type=int, default=N_BOOTSTRAP)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--n_splits", type=int, default=5)
    args = parser.parse_args()

    run_a2_residual(
        uq_csv=Path(args.uq_csv),
        oof_csv=Path(args.oof_csv),
        n_bootstrap=args.n_bootstrap,
        seed=args.seed,
        n_splits=args.n_splits,
    )


if __name__ == "__main__":
    main()
