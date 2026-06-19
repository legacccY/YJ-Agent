"""
collinearity_check.py
服务: ArtiOODBench Gate1 R0a（PR-F1 共线准入闸）
lever: L2 去污染

【做什么】
在同机构 normal-vs-anomaly 对（BraTS normal vs tumor）上：
  用 43 维 artifact 特征拟合回归器 f，
  测 f(artifact) 对各 OOD 方法 score 的 R²（纯 numpy，避 scipy）。

输出: r0a_collinearity_R2.csv (方法 × R²)

判定规则（代码注释冻结，预登记 PR-F1）：
  R²≥0.3 → 共线坐实 → 方案 A regress-out 作废，不进 paper
  R²<0.3 → 方案 A 可作 robustness 附录对照

【OOD 方法 score（此处用 proxy 模拟）】
真实 OOD 方法 score 来自 l3_ood_rerank.py 输出。
本脚本在 results/l3_raw_ranking.csv 就位后可直接读取。
若 l3 输出未就位，脚本会对每个方法 mock 一个 score（正态噪声叠加 artifact 均值），
并在输出中标记 is_mocked=True。

注意：共线性在「同机构」对上评估是防混淆设计——
跨机构对 artifact 与 semantic 混缠，同机构 normal/anomaly 对 artifact 相对稳定，
R² 高意味着 artifact 特征与 OOD score 在没有 domain shift 时也相关（共线）。

【运行】
  # smoke（合成数据，不需要真实图像）
  python collinearity_check.py --smoke

  # 真实数据（BraTS）
  python collinearity_check.py
"""

import argparse
import csv
import io
import sys
from pathlib import Path

import numpy as np

# Windows GBK 终端安全：强制 stdout/stderr 为 utf-8
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ============================================================
# 路径常量
# ============================================================
BRATS_DIR = Path("D:/YJ-Agent/project/meeting/MedAD-FailMap/data/BraTS2021")
OUT_DIR = Path(__file__).resolve().parent.parent / "results"
OUT_CSV = OUT_DIR / "r0a_collinearity_R2.csv"
L3_SCORE_CSV = OUT_DIR / "l3_method_scores_raw.csv"  # l3_ood_rerank.py 产出
TARGET_SIZE = 224
SEED = 42


# ============================================================
# 特征提取（复用 killshot 43 维）
# ============================================================
def load_image_gray224(path: Path, size: int = TARGET_SIZE) -> np.ndarray:
    from PIL import Image
    img = Image.open(path).convert("L")
    if img.size != (size, size):
        img = img.resize((size, size), Image.BILINEAR)
    return np.array(img, dtype=np.uint8)


def feat_hist32(arr):
    hist, _ = np.histogram(arr.flatten(), bins=32, range=(0, 256))
    hist = hist.astype(np.float32)
    total = hist.sum()
    return hist / total if total > 0 else hist


def feat_edge_ratio(arr, border_px=10):
    h, w = arr.shape
    bm = np.zeros((h, w), dtype=bool)
    bm[:border_px, :] = bm[-border_px:, :] = True
    bm[:, :border_px] = bm[:, -border_px:] = True
    bp = arr[bm]
    return np.array([(bp < 5).sum() / max(len(bp), 1),
                     (arr.flatten() < 5).sum() / max(arr.size, 1)], dtype=np.float32)


def feat_glcm(arr):
    try:
        from skimage.feature import graycomatrix, graycoprops
    except ImportError:
        raise ImportError("pip install scikit-image")
    s = np.array(__import__("PIL").Image.fromarray(arr).resize((64, 64),
                                                               __import__("PIL").Image.BILINEAR),
                 dtype=np.uint8)
    s_q = (s // 8).astype(np.uint8)
    angles = [0, np.pi / 4, np.pi / 2, 3 * np.pi / 4]
    glcm = graycomatrix(s_q, distances=[1], angles=angles, levels=32,
                        symmetric=True, normed=True)
    return np.array([graycoprops(glcm, p).mean() for p in
                     ["contrast", "energy", "homogeneity", "correlation"]], dtype=np.float32)


def feat_stats(arr):
    flat = arr.flatten().astype(np.float32)
    mean = flat.mean()
    std = flat.std() + 1e-8
    return np.array([mean, float(flat.var()),
                     float(((flat - mean) ** 3).mean()) / std ** 3,
                     float(((flat - mean) ** 4).mean()) / std ** 4 - 3.0], dtype=np.float32)


def feat_fft_ratio(arr):
    fshift = np.fft.fftshift(np.fft.fft2(arr.astype(np.float32)))
    mag = np.abs(fshift)
    h, w = mag.shape
    cy, cx = h // 2, w // 2
    lm = np.zeros((h, w), dtype=bool)
    lm[cy - 5:cy + 5, cx - 5:cx + 5] = True
    return np.array([mag[~lm].sum() / (mag[lm].sum() + 1e-8)], dtype=np.float32)


def extract_all_features(arr):
    return np.concatenate([feat_hist32(arr), feat_edge_ratio(arr),
                           feat_glcm(arr), feat_stats(arr), feat_fft_ratio(arr)])


def _glob_images(d: Path):
    if not d.exists():
        return []
    return sorted([p for p in d.iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg")])


# ============================================================
# 纯 numpy R² 计算
# ============================================================
def r_squared_numpy(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """R² = 1 - SS_res / SS_tot（纯 numpy，无 scipy）。"""
    ss_res = float(np.sum((y_true - y_pred) ** 2))
    ss_tot = float(np.sum((y_true - y_true.mean()) ** 2))
    if ss_tot < 1e-12:
        return 0.0
    return max(0.0, 1.0 - ss_res / ss_tot)


def linreg_predict_numpy(X_tr: np.ndarray, y_tr: np.ndarray,
                         X_te: np.ndarray) -> np.ndarray:
    """
    纯 numpy linear regression（OLS via closed-form，小矩阵可逆）。
    X_tr: (N, D), y_tr: (N,), X_te: (M, D)
    """
    # 加截距
    ones_tr = np.ones((len(X_tr), 1), dtype=X_tr.dtype)
    Xb_tr = np.concatenate([ones_tr, X_tr], axis=1)
    ones_te = np.ones((len(X_te), 1), dtype=X_te.dtype)
    Xb_te = np.concatenate([ones_te, X_te], axis=1)
    # OLS: w = (X^T X + λI)^{-1} X^T y
    lam = 1e-3
    A = Xb_tr.T @ Xb_tr + lam * np.eye(Xb_tr.shape[1])
    b_vec = Xb_tr.T @ y_tr.astype(np.float64)
    try:
        w = np.linalg.solve(A, b_vec)
    except np.linalg.LinAlgError:
        w = np.linalg.lstsq(A, b_vec, rcond=None)[0]
    return (Xb_te @ w).astype(np.float32)


def cross_val_r2(X: np.ndarray, y: np.ndarray, k: int = 5, seed: int = SEED) -> float:
    """k-fold CV 平均 R²。"""
    rng = np.random.RandomState(seed)
    idx = np.arange(len(y))
    rng.shuffle(idx)
    fold_size = len(y) // k
    r2s = []
    for fold in range(k):
        val_idx = idx[fold * fold_size: (fold + 1) * fold_size]
        tr_idx = np.concatenate([idx[:fold * fold_size], idx[(fold + 1) * fold_size:]])
        X_tr, X_val = X[tr_idx], X[val_idx]
        y_tr, y_val = y[tr_idx], y[val_idx]
        # 标准化 (train 统计量)
        mu = X_tr.mean(0)
        sigma = X_tr.std(0) + 1e-8
        X_tr_s = (X_tr - mu) / sigma
        X_val_s = (X_val - mu) / sigma
        y_pred = linreg_predict_numpy(X_tr_s, y_tr, X_val_s)
        r2s.append(r_squared_numpy(y_val.astype(np.float32), y_pred))
    return float(np.mean(r2s))


# ============================================================
# OOD 方法 score（从 l3 输出读取，或 mock）
# ============================================================
OOD_METHODS = ["MSP", "ODIN", "Energy", "MDS", "KNN", "ViM", "GradNorm"]


def load_or_mock_scores(n: int, rng: np.random.RandomState,
                        artifact_mean: np.ndarray) -> dict:
    """
    尝试从 l3_method_scores_raw.csv 读取真实 score。
    读不到则 mock（正态噪声 + 0.3 * artifact_mean 第一维）。
    返回 dict: method -> np.ndarray (n,)
    """
    if L3_SCORE_CSV.exists():
        try:
            rows = []
            with open(L3_SCORE_CSV, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    rows.append(row)
            if rows and len(rows) >= n:
                scores = {}
                for method in OOD_METHODS:
                    col = method.lower() + "_score"
                    if col in rows[0]:
                        scores[method] = np.array([float(r[col]) for r in rows[:n]])
                if scores:
                    print(f"[R0a] loaded real scores from {L3_SCORE_CSV}")
                    return scores, False
        except Exception as e:
            print(f"[WARN] failed to load l3 scores: {e}", file=sys.stderr)

    # Mock: 模拟 OOD score = 噪声 + 不同程度的 artifact 泄漏
    print("[R0a] l3 scores not available, using mock scores (is_mocked=True)")
    rng2 = np.random.RandomState(SEED + 99)
    scores = {}
    artifact_signal = artifact_mean[0] if len(artifact_mean) > 0 else 0.0
    for i, method in enumerate(OOD_METHODS):
        # 每个方法不同程度的 artifact 相关：最小 ~0 到最大 ~0.5 相关
        leak = 0.05 * i  # 0..0.3
        noise = rng2.randn(n).astype(np.float32)
        scores[method] = noise + leak * float(artifact_signal) * rng2.randn(n).astype(np.float32)
    return scores, True


# ============================================================
# 主逻辑
# ============================================================
def main(smoke: bool = False):
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # ---------- smoke: 合成数据 ----------
    if smoke:
        print("[R0a] SMOKE: 合成数据验结构")
        rng = np.random.RandomState(SEED)
        n = 100
        X_art = rng.randn(n, 43).astype(np.float32)
        labels = np.array([0] * (n // 2) + [1] * (n // 2), dtype=np.int32)
        artifact_mean = X_art.mean(0)
        scores, is_mocked = load_or_mock_scores(n, rng, artifact_mean)
        rows = []
        for method, score in scores.items():
            r2 = cross_val_r2(X_art, score.astype(np.float64))
            verdict = "共线坐实→方案A作废" if r2 >= 0.3 else "R²<0.3→方案A可用"
            rows.append({"method": method, "R2": round(r2, 4),
                         "collinear": int(r2 >= 0.3),
                         "verdict": verdict,
                         "is_mocked": int(is_mocked)})
            print(f"  {method}: R²={r2:.4f}  {verdict}")
        with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["method", "R2", "collinear", "verdict", "is_mocked"])
            w.writeheader()
            w.writerows(rows)
        print(f"[SMOKE] -> {OUT_CSV}")
        return

    # ---------- 真实数据 ----------
    # BraTS normal & tumor 同机构对（PR-F1 设计：同机构对）
    norm_dir = BRATS_DIR / "test" / "normal"
    if not norm_dir.exists():
        norm_dir = BRATS_DIR / "normal"
    tumor_dir = BRATS_DIR / "test" / "tumor"
    if not tumor_dir.exists():
        tumor_dir = BRATS_DIR / "tumor"

    norm_files = _glob_images(norm_dir)
    tumor_files = _glob_images(tumor_dir)

    if not norm_files or not tumor_files:
        print(
            f"[ERROR] BraTS 数据未找到:\n  normal: {norm_dir} ({len(norm_files)} files)\n"
            f"  tumor: {tumor_dir} ({len(tumor_files)} files)\n"
            "请先下载 BraTS2021 到 project/meeting/MedAD-FailMap/data/BraTS2021/",
            file=sys.stderr,
        )
        # 不退出——写空 CSV 以防下游报 FileNotFound
        with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["method", "R2", "collinear", "verdict", "is_mocked"])
            w.writeheader()
        print(f"[R0a] wrote empty -> {OUT_CSV}")
        return

    print(f"[R0a] BraTS: normal={len(norm_files)}, tumor={len(tumor_files)}")

    all_files = norm_files + tumor_files
    labels_full = np.array([0] * len(norm_files) + [1] * len(tumor_files), dtype=np.int32)

    # 限制 500/side 避免太慢
    rng = np.random.RandomState(SEED)
    n_side = min(500, len(norm_files), len(tumor_files))
    norm_sel = rng.choice(len(norm_files), n_side, replace=False)
    tumor_sel = rng.choice(len(tumor_files), n_side, replace=False)
    selected = ([norm_files[i] for i in norm_sel] +
                [tumor_files[i] for i in tumor_sel])
    labels = np.array([0] * n_side + [1] * n_side, dtype=np.int32)
    n = len(selected)

    print(f"[R0a] extracting 43-dim artifact features for {n} images...")
    feats = []
    for i, p in enumerate(selected):
        if (i + 1) % 100 == 0:
            print(f"  {i+1}/{n}")
        try:
            arr = load_image_gray224(Path(p))
            feats.append(extract_all_features(arr))
        except Exception as e:
            print(f"  [WARN] skip {Path(p).name}: {e}", file=sys.stderr)
            feats.append(np.zeros(43, dtype=np.float32))
    X_art = np.array(feats, dtype=np.float32)
    artifact_mean = X_art.mean(0)

    # 加载或 mock OOD scores
    scores, is_mocked = load_or_mock_scores(n, rng, artifact_mean)

    # 计算 R²
    rows = []
    print(f"\n[R0a] R² 判据：R²≥0.3=共线坐实(方案A作废), R²<0.3=方案A可用")
    for method, score in scores.items():
        # 确保 score 长度对齐
        score_n = score[:n] if len(score) >= n else np.pad(score, (0, n - len(score)))
        r2 = cross_val_r2(X_art, score_n.astype(np.float64))
        # 判定规则注释（预登记 PR-F1，冻结）：
        # R²≥0.3 = 共线坐实 → 方案 A regress-out 作废（artifact 与 OOD score 内生相关，
        #   regress-out 会破坏 OOD signal，不进 paper）
        # R²<0.3 = 方案 A 可作 robustness 附录对照
        collinear = int(r2 >= 0.3)
        verdict = "共线坐实→方案A作废" if collinear else "R²<0.3→方案A可用"
        rows.append({"method": method, "R2": round(r2, 4),
                     "collinear": collinear, "verdict": verdict,
                     "is_mocked": int(is_mocked)})
        print(f"  {method}: R²={r2:.4f}  {verdict}")

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["method", "R2", "collinear", "verdict", "is_mocked"])
        w.writeheader()
        w.writerows(rows)
    print(f"\n[R0a] -> {OUT_CSV}")

    # 汇总判决
    any_collinear = any(r["collinear"] for r in rows)
    if any_collinear:
        methods_col = [r["method"] for r in rows if r["collinear"]]
        print(f"\n[R0a] 共线 (R²≥0.3): {methods_col}")
        print("  → PR-F1 规则：方案 A regress-out 在这些方法上作废，不计入 paper 命门")
    else:
        print("\n[R0a] 全部 R²<0.3 → 方案 A 可作 robustness 附录对照（PR-F1 允许）")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="R0a collinearity check (PR-F1)")
    parser.add_argument("--smoke", action="store_true",
                        help="用合成数据 smoke 测试，不需要真实图像")
    args = parser.parse_args()
    main(smoke=args.smoke)
