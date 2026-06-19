"""
G5 Kill-shot: S4A-01 — HAM10000 解剖位 metadata shortcut
服务: run-007 ACCV 选题流水线 G5 杀手锏（lever = G5 立项前证伪）
目标: 纯 CPU，零 GPU，从 HAM metadata 算位置-only / age-only / sex-only logistic melanoma AUC
      + 位置×dx 互信息(MI) + bootstrap 95%CI；对照 _G5_DESIGN.md 判读规则报结论。

R9 判读约定（_G5_DESIGN.md §S4A-01）：
  KILL  : 位置-only AUC <= 0.55 且 CI 含/低于 0.55 → 无泄漏 → 砍
  PASS/MAIN : 位置-only AUC >= 0.55 (CI 下界>0.5) AND > age/sex AUC+0.05 且 CI 不重叠 → 碾压 artifact → 回 MAIN
  PASS/FIND : 位置-only AUC >= 0.55 但不碾压 → 泄漏真但非最强 → 维持 FIND
  GRAY  : CI 宽（不太可能，mel=1113 应足够）

数据: D:/YJ-Agent/data/external/ham10000/HAM10000_metadata.csv
      列: lesion_id, image_id, dx, dx_type, age, sex, localization

输出: killshots/run-007/results/S4A01_position_shortcut.csv
      + stdout 判读摘要
"""
import argparse
import os
import sys
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import OneHotEncoder
from sklearn.metrics import roc_auc_score

# ── 路径 ──────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent.parent  # D:/YJ-Agent
HAM_CSV = REPO_ROOT / "data" / "external" / "ham10000" / "HAM10000_metadata.csv"
RESULTS_DIR = Path(__file__).resolve().parent / "results"

# ── 超参（均来自 _G5_DESIGN.md，不臆想）────────────────────────────────────
N_FOLDS = 5
N_BOOTSTRAP = 1000
RANDOM_STATE = 42
MDE_AUC = 0.55          # 位置-only AUC 下限（_G5_DESIGN §S4A-01 §2 MDE）
MAIN_DELTA = 0.05        # 位置 vs age/sex AUC 差门槛（回 MAIN 高门槛）


def compute_mi_categorical(x: np.ndarray, y: np.ndarray) -> float:
    """
    计算两个离散变量的互信息（nats）。
    纯 numpy 实现，不依赖 scipy（避免 OMP Error #15）。
    """
    x = np.asarray(x).flatten()
    y = np.asarray(y).flatten()
    assert len(x) == len(y)
    n = len(x)
    x_vals = np.unique(x)
    y_vals = np.unique(y)
    mi = 0.0
    for xv in x_vals:
        for yv in y_vals:
            p_xy = np.sum((x == xv) & (y == yv)) / n
            p_x = np.sum(x == xv) / n
            p_y = np.sum(y == yv) / n
            if p_xy > 0 and p_x > 0 and p_y > 0:
                mi += p_xy * np.log(p_xy / (p_x * p_y))
    return float(mi)


def bootstrap_auc_ci(y_true: np.ndarray, y_score: np.ndarray,
                     n_boot: int = N_BOOTSTRAP, alpha: float = 0.05,
                     rng: np.random.Generator = None) -> tuple:
    """
    Bootstrap 95%CI for AUC (percentile method).
    返回 (auc_point, ci_lo, ci_hi)
    纯 numpy + sklearn，不依赖 scipy。
    """
    if rng is None:
        rng = np.random.default_rng(RANDOM_STATE)
    n = len(y_true)
    boot_aucs = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        yt = y_true[idx]
        ys = y_score[idx]
        # skip bootstraps where only one class present
        if len(np.unique(yt)) < 2:
            continue
        boot_aucs.append(roc_auc_score(yt, ys))
    boot_aucs = np.array(boot_aucs)
    ci_lo = float(np.percentile(boot_aucs, 100 * alpha / 2))
    ci_hi = float(np.percentile(boot_aucs, 100 * (1 - alpha / 2)))
    auc_pt = float(roc_auc_score(y_true, y_score))
    return auc_pt, ci_lo, ci_hi


def cv_predict_proba(X: np.ndarray, y: np.ndarray, n_folds: int = N_FOLDS,
                     random_state: int = RANDOM_STATE) -> np.ndarray:
    """
    Stratified K-fold CV；返回 OOF predicted probabilities (class=1)。
    """
    skf = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=random_state)
    oof_proba = np.zeros(len(y), dtype=float)
    for train_idx, val_idx in skf.split(X, y):
        clf = LogisticRegression(max_iter=1000, random_state=random_state, solver="lbfgs")
        clf.fit(X[train_idx], y[train_idx])
        oof_proba[val_idx] = clf.predict_proba(X[val_idx])[:, 1]
    return oof_proba


def main(smoke: bool = False):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # ── 读数据 ──────────────────────────────────────────────────────────────
    if not HAM_CSV.exists():
        print(f"[MISSING DATA] HAM metadata not found at {HAM_CSV}", file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(HAM_CSV, encoding="utf-8")
    print(f"Loaded HAM metadata: {len(df)} rows, cols={list(df.columns)}")

    # ── 目标变量：melanoma vs rest ────────────────────────────────────────
    y = (df["dx"] == "mel").astype(int).values
    print(f"  mel={y.sum()} / non-mel={len(y)-y.sum()} (binary melanoma)")

    if smoke:
        # smoke 模式：stratified 采样确保两类都有
        mel_rows = df[df["dx"] == "mel"].head(30)
        non_mel_rows = df[df["dx"] != "mel"].head(170)
        df = pd.concat([mel_rows, non_mel_rows], ignore_index=True)
        y = (df["dx"] == "mel").astype(int).values
        print(f"[SMOKE] using {len(df)} rows (mel={y.sum()}, non-mel={len(y)-y.sum()})")

    # ── 特征构造 ─────────────────────────────────────────────────────────
    # 1) 位置-only：one-hot localization（15 类）
    loc_enc = OneHotEncoder(sparse_output=False, handle_unknown="ignore")
    X_loc = loc_enc.fit_transform(df[["localization"]])

    # 2) age-only：单特征，NaN 填中位数
    age_vals = df["age"].fillna(df["age"].median()).values.reshape(-1, 1)

    # 3) sex-only：one-hot (male/female/unknown)
    sex_enc = OneHotEncoder(sparse_output=False, handle_unknown="ignore")
    X_sex = sex_enc.fit_transform(df[["sex"]])

    # 4) age+sex 组合（对照组）
    X_agesex = np.hstack([age_vals, X_sex])

    # ── 互信息：localization × dx ────────────────────────────────────────
    # 离散化 localization → 整数编码
    loc_codes = pd.Categorical(df["localization"]).codes
    dx_codes = pd.Categorical(df["dx"]).codes
    mi_loc_dx = compute_mi_categorical(loc_codes, dx_codes)
    print(f"\nMutual Information (localization × dx): {mi_loc_dx:.4f} nats")

    # ── 5-fold CV 得 OOF 概率 ────────────────────────────────────────────
    print("\nRunning 5-fold CV (position-only) ...")
    oof_loc = cv_predict_proba(X_loc, y)

    print("Running 5-fold CV (age-only) ...")
    oof_age = cv_predict_proba(age_vals, y)

    print("Running 5-fold CV (sex-only) ...")
    oof_sex = cv_predict_proba(X_sex, y)

    print("Running 5-fold CV (age+sex) ...")
    oof_agesex = cv_predict_proba(X_agesex, y)

    # ── Bootstrap CI ─────────────────────────────────────────────────────
    rng = np.random.default_rng(RANDOM_STATE)
    print("\nBootstrapping CIs ...")
    auc_loc, ci_lo_loc, ci_hi_loc = bootstrap_auc_ci(y, oof_loc, rng=rng)
    auc_age, ci_lo_age, ci_hi_age = bootstrap_auc_ci(y, oof_age, rng=rng)
    auc_sex, ci_lo_sex, ci_hi_sex = bootstrap_auc_ci(y, oof_sex, rng=rng)
    auc_agesex, ci_lo_agesex, ci_hi_agesex = bootstrap_auc_ci(y, oof_agesex, rng=rng)

    # ── 结果打印 ──────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("S4A-01 RESULTS — HAM10000 Position Shortcut")
    print("=" * 60)
    rows = [
        ("position-only",  auc_loc,    ci_lo_loc,    ci_hi_loc),
        ("age-only",       auc_age,    ci_lo_age,    ci_hi_age),
        ("sex-only",       auc_sex,    ci_lo_sex,    ci_hi_sex),
        ("age+sex",        auc_agesex, ci_lo_agesex, ci_hi_agesex),
    ]
    for name, auc, lo, hi in rows:
        print(f"  {name:<20s}  AUC={auc:.4f}  95%CI=[{lo:.4f}, {hi:.4f}]")
    print(f"\n  MI(location×dx) = {mi_loc_dx:.4f} nats")
    print(f"  MDE threshold   = {MDE_AUC:.2f} (position-only AUC)")
    print(f"  MAIN delta gate = +{MAIN_DELTA:.2f} over age/sex AUC")

    # ── R9 判读 ──────────────────────────────────────────────────────────
    print("\n--- R9 判读 ---")
    best_agesex_auc = max(auc_age, auc_sex, auc_agesex)
    loc_above_mde = ci_lo_loc > 0.5 and auc_loc >= MDE_AUC
    loc_crushes_agesex = (auc_loc - best_agesex_auc) >= MAIN_DELTA and ci_lo_loc > ci_hi_agesex

    if not loc_above_mde and ci_hi_loc < MDE_AUC + 0.05:
        verdict = "KILL — 位置-only AUC 低于 MDE(0.55)且CI窄 → 无可利用泄漏 → 砍/降"
    elif loc_crushes_agesex:
        verdict = "PASS/MAIN — 位置-only AUC >= 0.55 且碾压 age/sex (+>=0.05, CI 不重叠) → 位置是最强 metadata shortcut → 天花板回升 MAIN"
    elif loc_above_mde:
        verdict = "PASS/FIND — 位置-only AUC >= 0.55 但未碾压 age/sex → 泄漏真但非最强 → 维持 FIND/MAIN 偏 FIND"
    else:
        verdict = "GRAY — CI 宽，功效不足，需扩数据"

    print(f"  {verdict}")

    # ── 存 CSV ───────────────────────────────────────────────────────────
    out_df = pd.DataFrame({
        "feature": [r[0] for r in rows],
        "auc":     [r[1] for r in rows],
        "ci_lo":   [r[2] for r in rows],
        "ci_hi":   [r[3] for r in rows],
    })
    out_df["mi_loc_dx"] = mi_loc_dx
    out_df["mde_threshold"] = MDE_AUC
    out_df["verdict"] = verdict
    out_path = RESULTS_DIR / "S4A01_position_shortcut.csv"
    out_df.to_csv(out_path, index=False, encoding="utf-8")
    print(f"\n  Saved -> {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="S4A-01 HAM10000 position shortcut kill-shot")
    parser.add_argument("--smoke", type=int, default=0, help="smoke test: use first N rows (0=full)")
    args = parser.parse_args()
    main(smoke=bool(args.smoke))
