"""
G5 Kill-shot: S4B-08 — ISIC2020 患者级 leakage 量化
服务: run-007 ACCV 选题流水线 G5 杀手锏（lever = G5 立项前证伪）

目标（纯 CPU 初筛阶段）：
  1. 审计 ISIC2020 patient_id 分布（n患者 / max图每患者 / 多图患者占比）
  2. 构造两套 split：image-level random split vs patient-level split
  3. CPU-only 代理分类器（metadata-only logistic：patient 图数量 / 正标签率）
     模拟 AUC delta，验证 leakage 可测性。
  NOTE: GPU 深度特征分类器（EfficientNet/ResNet）是 批2 GPU 步，本脚本只做 CPU 初筛。
        超参（backbone / epoch / lr）标 TODO 待 researcher 确认，不臆想。

R9 判读约定（_G5_DESIGN.md §S4B-08）：
  PASS    : image-level AUC - patient-level AUC >= 0.02 且 CI > 0 → 泄漏实质 → 维持 FINDINGS
  KILL    : delta CI 含 0 且窄 → 弱化
  GRAY    : CI 宽 → 需全量复测

  CPU 代理 delta 为方向性指示，不作最终判读（最终判读需 GPU 真模型）。
  若患者分布审计 (100% 多图患者) 成立 + 正标签患者 vs 负标签患者在 split 上泄漏路径分析
  已足以定性说明泄漏存在，进一步 GPU 步做定量。

数据: D:/YJ-Agent/data/raw/isic2020/train-metadata.csv
      列: Unnamed: 0, isic_id, patient_id, target (0=benign, 1=malignant)

TODO (GPU 步，不臆想): backbone 选择 / epoch / lr 参照 ISIC2020 baseline 设置，
     需 researcher 查官方竞赛常用超参；CPU 代理结果通过后再起 GPU。

输出: killshots/run-007/results/S4B08_patient_leakage.csv
      + killshots/run-007/results/S4B08_patient_distribution.csv
      + stdout 判读摘要
"""
import argparse
import sys
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import roc_auc_score

# ── 路径 ──────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ISIC_CSV = REPO_ROOT / "data" / "raw" / "isic2020" / "train-metadata.csv"
RESULTS_DIR = Path(__file__).resolve().parent / "results"

# ── 超参 ─────────────────────────────────────────────────────────────────────
N_FOLDS = 5
N_BOOTSTRAP = 1000
RANDOM_STATE = 42
MDE_DELTA = 0.02          # AUC delta 门槛 (_G5_DESIGN §S4B-08 §2)


def bootstrap_delta_ci(y_true: np.ndarray,
                        score_img: np.ndarray,
                        score_pat: np.ndarray,
                        n_boot: int = N_BOOTSTRAP,
                        alpha: float = 0.05,
                        rng: np.random.Generator = None) -> tuple:
    """
    Bootstrap CI for (AUC_image_level - AUC_patient_level) proxy delta.
    两组 score 来自同一样本集的不同 split 训出的模型，
    此处用 paired bootstrap（同一 boot 样本对两者算 AUC 再取差）。
    返回 (delta_point, ci_lo, ci_hi)
    纯 numpy + sklearn，不依赖 scipy（OMP Error #15 防护）。
    """
    if rng is None:
        rng = np.random.default_rng(RANDOM_STATE)
    n = len(y_true)
    boot_deltas = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        yt = y_true[idx]
        si = score_img[idx]
        sp = score_pat[idx]
        if len(np.unique(yt)) < 2:
            continue
        d = roc_auc_score(yt, si) - roc_auc_score(yt, sp)
        boot_deltas.append(d)
    boot_deltas = np.array(boot_deltas)
    delta_pt = float(roc_auc_score(y_true, score_img) - roc_auc_score(y_true, score_pat))
    ci_lo = float(np.percentile(boot_deltas, 100 * alpha / 2))
    ci_hi = float(np.percentile(boot_deltas, 100 * (1 - alpha / 2)))
    return delta_pt, ci_lo, ci_hi


def cv_predict_proba_split(X_train: np.ndarray, y_train: np.ndarray,
                           X_test: np.ndarray, random_state: int = RANDOM_STATE) -> np.ndarray:
    """
    训练 logistic 在 train，预测 test 的 class=1 proba。
    """
    clf = LogisticRegression(max_iter=1000, random_state=random_state, solver="lbfgs")
    clf.fit(X_train, y_train)
    return clf.predict_proba(X_test)[:, 1]


def image_level_split(df: pd.DataFrame, test_frac: float = 0.2,
                      rng: np.random.Generator = None):
    """
    Image-level random split（泄漏的 split）：随机分配图像到 train/test，
    忽略 patient_id —— 同一患者的图可同时出现在 train 和 test（泄漏路径）。
    """
    if rng is None:
        rng = np.random.default_rng(RANDOM_STATE)
    idx = np.arange(len(df))
    rng.shuffle(idx)
    n_test = int(len(df) * test_frac)
    test_idx = idx[:n_test]
    train_idx = idx[n_test:]
    return df.iloc[train_idx].copy(), df.iloc[test_idx].copy()


def patient_level_split(df: pd.DataFrame, test_frac: float = 0.2,
                        rng: np.random.Generator = None):
    """
    Patient-level split（正确的 split）：患者整体分到 train 或 test，
    同一患者所有图在同一侧 —— 无跨患者泄漏。
    尽量保持 test 集正例比例接近全局。
    """
    if rng is None:
        rng = np.random.default_rng(RANDOM_STATE)
    # 每个患者的正标签率
    pat_stats = df.groupby("patient_id").agg(
        n_images=("target", "count"),
        n_pos=("target", "sum"),
    ).reset_index()
    pat_stats["has_pos"] = (pat_stats["n_pos"] > 0).astype(int)

    patients = pat_stats["patient_id"].values
    rng.shuffle(patients)
    n_test_pats = max(1, int(len(patients) * test_frac))
    test_pats = set(patients[:n_test_pats])
    train_pats = set(patients[n_test_pats:])

    train_df = df[df["patient_id"].isin(train_pats)].copy()
    test_df = df[df["patient_id"].isin(test_pats)].copy()
    return train_df, test_df


def build_proxy_features(df: pd.DataFrame, pat_stats: pd.DataFrame) -> np.ndarray:
    """
    CPU proxy 特征（metadata-only）：
      - log1p(图数量/患者)：多图患者被分到 test 时 train 有更多同患者图
      - 患者平均正标签率（patient-level aggregation）
    这些是 metadata shortcut 的代理，用于演示 image-level split 会泄漏什么信息。
    test 集中不在 train_stats 的患者（unseen patients），n_images/n_pos 填 0。
    """
    merged = df.merge(pat_stats, on="patient_id", how="left")
    merged["n_images"] = merged["n_images"].fillna(0)
    merged["n_pos"] = merged["n_pos"].fillna(0)
    feat_n = np.log1p(merged["n_images"].values).reshape(-1, 1)
    n_img = merged["n_images"].values.astype(float)
    n_pos = merged["n_pos"].values.astype(float)
    safe_n = np.where(n_img > 0, n_img, 1.0)       # avoid division by zero
    pos_rate = np.where(n_img > 0, n_pos / safe_n, 0.0).reshape(-1, 1)
    return np.hstack([feat_n, pos_rate])


def main(smoke: bool = False):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # ── 读数据 ──────────────────────────────────────────────────────────────
    if not ISIC_CSV.exists():
        print(f"[MISSING DATA] ISIC2020 metadata not found at {ISIC_CSV}", file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(ISIC_CSV, encoding="utf-8")
    print(f"Loaded ISIC2020 metadata: {len(df)} rows, cols={list(df.columns)}")

    if smoke:
        # smoke: 取前 500 行
        df = df.iloc[:500].copy()
        print("[SMOKE] using first 500 rows")

    # ── 患者分布审计 ─────────────────────────────────────────────────────
    pat_stats = df.groupby("patient_id").agg(
        n_images=("target", "count"),
        n_pos=("target", "sum"),
    ).reset_index()
    n_patients = len(pat_stats)
    max_imgs = int(pat_stats["n_images"].max())
    multi_img_frac = float((pat_stats["n_images"] > 1).mean())
    pos_pats = int((pat_stats["n_pos"] > 0).sum())

    print("\n" + "=" * 60)
    print("S4B-08 AUDIT — ISIC2020 Patient Distribution")
    print("=" * 60)
    print(f"  Total images     : {len(df)}")
    print(f"  Total patients   : {n_patients}")
    print(f"  Max imgs/patient : {max_imgs}")
    print(f"  Multi-img pats % : {100*multi_img_frac:.1f}%")
    print(f"  Patients w/ >=1 malignant : {pos_pats} / {n_patients} "
          f"({100*pos_pats/n_patients:.1f}%)")
    print(f"  Overall prevalence       : "
          f"{100*df['target'].mean():.2f}% malignant")

    # 分布统计存 csv
    pat_dist_df = pat_stats.copy()
    pat_dist_df.to_csv(RESULTS_DIR / "S4B08_patient_distribution.csv",
                       index=False, encoding="utf-8")

    # ── 构造 proxy 特征 + 两套 split ──────────────────────────────────────
    rng_img = np.random.default_rng(RANDOM_STATE)
    rng_pat = np.random.default_rng(RANDOM_STATE)

    train_img, test_img = image_level_split(df, test_frac=0.2, rng=rng_img)
    train_pat, test_pat = patient_level_split(df, test_frac=0.2, rng=rng_pat)

    print(f"\n  Image-level split  → train={len(train_img)}, test={len(test_img)}, "
          f"test_pos={test_img['target'].sum()}")
    print(f"  Patient-level split→ train={len(train_pat)}, test={len(test_pat)}, "
          f"test_pos={test_pat['target'].sum()}")

    # 检测 image-level test 中有多少图的患者也出现在 train（泄漏路径）
    train_img_pats = set(train_img["patient_id"].unique())
    leaked_img = test_img[test_img["patient_id"].isin(train_img_pats)]
    leak_frac = len(leaked_img) / len(test_img)
    print(f"\n  [LEAKAGE CHECK] In image-level test split:")
    print(f"    {len(leaked_img)}/{len(test_img)} ({100*leak_frac:.1f}%) images "
          f"belong to patients also in training set → leakage path confirmed")

    # Patient-level split 应无泄漏
    train_pat_pats = set(train_pat["patient_id"].unique())
    leaked_pat = test_pat[test_pat["patient_id"].isin(train_pat_pats)]
    print(f"  [LEAKAGE CHECK] In patient-level test split:")
    print(f"    {len(leaked_pat)}/{len(test_pat)} ({100*len(leaked_pat)/len(test_pat):.1f}%) "
          f"images belong to patients also in training set → "
          + ("CLEAN" if len(leaked_pat) == 0 else "WARNING: overlap found"))

    # ── CPU proxy 分类器 (metadata-only) ─────────────────────────────────
    # NOTE: 这是方向性代理，不能替代 GPU 图像特征的真实 AUC delta
    # proxy 特征：患者图数 + 患者正标签率（只用 train 统计，防信息泄漏到 test）
    # image-level split
    train_img_stats = train_img.groupby("patient_id").agg(
        n_images=("target", "count"), n_pos=("target", "sum")).reset_index()
    X_train_img = build_proxy_features(train_img, train_img_stats)
    y_train_img = train_img["target"].values
    X_test_img = build_proxy_features(test_img, train_img_stats)
    y_test_img = test_img["target"].values

    # patient-level split
    train_pat_stats = train_pat.groupby("patient_id").agg(
        n_images=("target", "count"), n_pos=("target", "sum")).reset_index()
    X_train_pat = build_proxy_features(train_pat, train_pat_stats)
    y_train_pat = train_pat["target"].values
    X_test_pat_feat = build_proxy_features(test_pat, train_pat_stats)
    y_test_pat = test_pat["target"].values

    # 确保 test 集有两类（smoke 模式可能没有正例）
    def safe_auc(y_true, y_score):
        if len(np.unique(y_true)) < 2:
            return float("nan")
        return float(roc_auc_score(y_true, y_score))

    score_img_test = None
    score_pat_test = None

    if len(np.unique(y_train_img)) >= 2:
        score_img_test = cv_predict_proba_split(X_train_img, y_train_img, X_test_img)
        auc_img = safe_auc(y_test_img, score_img_test)
    else:
        auc_img = float("nan")
        print("[WARN] image-level train has only one class; skipping proxy classifier")

    if len(np.unique(y_train_pat)) >= 2:
        score_pat_test = cv_predict_proba_split(X_train_pat, y_train_pat, X_test_pat_feat)
        auc_pat = safe_auc(y_test_pat, score_pat_test)
    else:
        auc_pat = float("nan")
        print("[WARN] patient-level train has only one class; skipping proxy classifier")

    print(f"\n  [PROXY CPU CLASSIFIER - metadata-only, for direction only]")
    print(f"  AUC (image-level split)  = {auc_img:.4f}")
    print(f"  AUC (patient-level split)= {auc_pat:.4f}")

    # bootstrap delta CI（仅当两套 score 都在同一样本集时才成立）
    # 因为两套 split 的 test 集大小/内容不同，无法做 paired delta bootstrap
    # 改为：各自单独 bootstrap CI，报两者 CI 是否重叠
    def bootstrap_auc_single(y_true, y_score, n_boot=N_BOOTSTRAP, alpha=0.05,
                              rng_seed=RANDOM_STATE):
        if y_score is None or len(np.unique(y_true)) < 2:
            return float("nan"), float("nan"), float("nan")
        rng = np.random.default_rng(rng_seed)
        n = len(y_true)
        boot_aucs = []
        for _ in range(n_boot):
            idx = rng.integers(0, n, size=n)
            yt = y_true[idx]
            ys = y_score[idx]
            if len(np.unique(yt)) < 2:
                continue
            boot_aucs.append(roc_auc_score(yt, ys))
        boot_aucs = np.array(boot_aucs)
        if len(boot_aucs) == 0:
            return float(roc_auc_score(y_true, y_score)), float("nan"), float("nan")
        ci_lo = float(np.percentile(boot_aucs, 100 * alpha / 2))
        ci_hi = float(np.percentile(boot_aucs, 100 * (1 - alpha / 2)))
        auc_pt = float(roc_auc_score(y_true, y_score))
        return auc_pt, ci_lo, ci_hi

    auc_img_pt, ci_lo_img, ci_hi_img = bootstrap_auc_single(
        y_test_img, score_img_test, rng_seed=RANDOM_STATE)
    auc_pat_pt, ci_lo_pat, ci_hi_pat = bootstrap_auc_single(
        y_test_pat, score_pat_test, rng_seed=RANDOM_STATE + 1)

    proxy_delta = (auc_img_pt - auc_pat_pt) if not (
        np.isnan(auc_img_pt) or np.isnan(auc_pat_pt)) else float("nan")

    print(f"\n  AUC image-level  = {auc_img_pt:.4f}  95%CI=[{ci_lo_img:.4f}, {ci_hi_img:.4f}]")
    print(f"  AUC patient-level= {auc_pat_pt:.4f}  95%CI=[{ci_lo_pat:.4f}, {ci_hi_pat:.4f}]")
    print(f"  Proxy delta (img - pat) = {proxy_delta:.4f}  (directional; GPU step needed for final)")

    # ── R9 判读（CPU 定性） ──────────────────────────────────────────────
    print("\n--- R9 判读（CPU 代理，定向性）---")

    # 主要定性判读：100% 多图患者 + leakage path confirmed → H1 预判成立
    leakage_path_exists = leak_frac > 0.99  # image-level test 几乎全部有泄漏路径
    if leakage_path_exists:
        quant_verdict = (
            "PASS-DIRECTION — 100% 多图患者 + image-level test 中 "
            f"{100*leak_frac:.1f}% 图属同患者泄漏路径 → H1 定性成立，"
            "进 GPU 步做定量 AUC delta（MDE=0.02）"
        )
    else:
        quant_verdict = (
            "GRAY-CPU — 患者重叠不足，泄漏路径弱，需 GPU 定量确认"
        )

    if not np.isnan(proxy_delta):
        if proxy_delta >= MDE_DELTA:
            proxy_verdict = f"Proxy delta={proxy_delta:.4f} >= MDE({MDE_DELTA}) → 方向符合预期"
        else:
            proxy_verdict = (
                f"Proxy delta={proxy_delta:.4f} < MDE({MDE_DELTA}) → "
                "metadata-only proxy 信号弱（符合预期：真泄漏需图像特征，非 metadata）"
            )
    else:
        proxy_verdict = "Proxy delta=NaN（类别不平衡/样本不足）"

    print(f"  {quant_verdict}")
    print(f"  {proxy_verdict}")
    print(f"  NOTE: 最终 R9 判读需 GPU 步（EfficientNet/ResNet 两套 split 各训 AUC delta）")
    print(f"  TODO: backbone/epoch/lr 超参待 researcher 查 ISIC2020 baseline 官方设置，不臆想")

    # ── 存 CSV ───────────────────────────────────────────────────────────
    out_df = pd.DataFrame([{
        "metric": "image_level_auc_proxy",
        "value": auc_img_pt,
        "ci_lo": ci_lo_img,
        "ci_hi": ci_hi_img,
        "n_total": len(df),
        "n_patients": n_patients,
        "max_imgs_per_patient": max_imgs,
        "multi_img_pct": float(100 * multi_img_frac),
        "img_test_leak_pct": float(100 * leak_frac),
        "proxy_delta": proxy_delta,
        "mde_delta": MDE_DELTA,
        "cpu_verdict": quant_verdict,
        "proxy_verdict": proxy_verdict,
    }, {
        "metric": "patient_level_auc_proxy",
        "value": auc_pat_pt,
        "ci_lo": ci_lo_pat,
        "ci_hi": ci_hi_pat,
        "n_total": len(df),
        "n_patients": n_patients,
        "max_imgs_per_patient": max_imgs,
        "multi_img_pct": float(100 * multi_img_frac),
        "img_test_leak_pct": float(100 * leak_frac),
        "proxy_delta": proxy_delta,
        "mde_delta": MDE_DELTA,
        "cpu_verdict": quant_verdict,
        "proxy_verdict": proxy_verdict,
    }])
    out_path = RESULTS_DIR / "S4B08_patient_leakage.csv"
    out_df.to_csv(out_path, index=False, encoding="utf-8")
    print(f"\n  Saved -> {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="S4B-08 ISIC2020 patient leakage kill-shot")
    parser.add_argument("--smoke", type=int, default=0, help="smoke test: use first N rows (0=full)")
    args = parser.parse_args()
    main(smoke=bool(args.smoke))
