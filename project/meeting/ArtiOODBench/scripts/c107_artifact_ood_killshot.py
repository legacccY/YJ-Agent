"""
C107 Artifact OOD Kill-Shot
服务: run-006 G5 杀手锏预实验，lever=立项前廉价证伪

【这个 killshot 在验什么】
Claim: 医学 OOD detection benchmark 被 scanner/采集 artifact 污染。
artifact-only 手工特征（完全不看病理内容，只看采集层特征）就能
高 AUROC 区分 ID（NIH ChestX-ray14）vs OOD（VinDr-CXR）。

如果纯 artifact 特征 AUROC 很高，说明：
  1. 两数据集之间存在明显的采集层差异（分辨率、扫描机、后处理等）
  2. 现有 OOD benchmark 结果有被 artifact 污染的嫌疑
  3. "检测 OOD"的模型实际可能在学采集差异而非语义分布差异

【判据】
- AUROC > 0.95 -> artifact 污染坐实，benchmark 严重质疑，claim 成立
- 0.80 < AUROC <= 0.95 -> 中等污染，值得报告
- AUROC <= 0.80 -> 污染有限，claim 较弱，需重新审视

【公平性设计】
VinDr 原始分辨率 512x512，NIH 本地已是 224x224。
为防止分辨率本身直接泄漏（AUROC=1 毫无意义），
统一 resize 到 224x224 灰度后再提特征。
这样分辨率 artifact 被消除，剩余区分力来自纹理/统计/频域等真实采集差异。

【特征组（artifact-only，不含语义）】
1. hist32: 灰度强度直方图 32 bin（亮度分布差异）
2. edge_ratio: 零 padding / 边缘暗角比例（掩膜/裁剪模式）
3. glcm: GLCM Haralick 4 维（对比度/能量/同质性/相关，4 方向平均）
4. stats: 整体均值/方差/峰度/偏度（4 维）
5. fft_ratio: FFT 高低频能量比（采集模糊/锐化差异）
   - low_freq: DC+低频（中心 10x10 区域）
   - high_freq: 其余高频
   - ratio = high / (low + 1e-8)

【模型】
5-fold 交叉验证，LogisticRegression（L2，max_iter=1000）
标签: NIH=0（ID），VinDr=1（OOD）

【输出】
- results/c107_artifact_ood_killshot.csv
  列: feature_set, auroc_mean, auroc_std, n_samples
- results/c107_per_feature_auroc.csv
  列: feature_dim, auroc（各特征维度单独评估）
- stdout print 总 AUROC + 各特征组单独 AUROC

【运行】
  # smoke 测试（各 20 张，CPU，快）
  python c107_artifact_ood_killshot.py --smoke 20

  # 全量（各 500 张，约 1-2 min）
  python c107_artifact_ood_killshot.py

纯 sklearn + skimage + numpy，CPU 跑。无 scipy（Windows OMP 安全）。
"""

import argparse
import csv
import os
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image

# ============================================================
# 路径常量
# ============================================================
NIH_DIR = Path(
    "D:/YJ-Agent/project/meeting/Med-NCA/NCA-JEPA/data/nih_cxr14/images-224/images-224"
)
VINDR_DIR = Path("D:/YJ-Agent/data/external/vindr_cxr")
OUT_DIR = Path(__file__).resolve().parent / "results"
OUT_CSV = OUT_DIR / "c107_artifact_ood_killshot.csv"
OUT_PER_FEAT_CSV = OUT_DIR / "c107_per_feature_auroc.csv"

TARGET_SIZE = 224  # 统一 resize 到 224x224（消除分辨率直接泄漏）
N_SAMPLE = 500     # 各数据集采样数（全量模式）
RANDOM_SEED = 42


# ============================================================
# 纯 numpy AUROC（避 scipy，Windows OMP 安全）
# ============================================================
def auroc_numpy(labels: np.ndarray, scores: np.ndarray) -> float:
    """
    AUROC via Mann-Whitney U statistic.
    labels: 0/1 array（1=OOD=VinDr）; scores: float array（越高越 OOD）
    """
    pos_scores = scores[labels == 1]
    neg_scores = scores[labels == 0]
    if len(pos_scores) == 0 or len(neg_scores) == 0:
        return float("nan")
    u = 0.0
    for ps in pos_scores:
        u += (neg_scores < ps).sum() + 0.5 * (neg_scores == ps).sum()
    return float(u / (len(pos_scores) * len(neg_scores)))


# ============================================================
# 图像加载（统一 224x224 灰度）
# ============================================================
def load_image_gray224(path: Path) -> np.ndarray:
    """
    读取图像，resize 到 TARGET_SIZE x TARGET_SIZE 灰度，返回 uint8 numpy array。
    公平性保证：无论原始分辨率（NIH=224²，VinDr=512²），统一处理后再提特征。
    """
    img = Image.open(path).convert("L")
    if img.size != (TARGET_SIZE, TARGET_SIZE):
        img = img.resize((TARGET_SIZE, TARGET_SIZE), Image.BILINEAR)
    return np.array(img, dtype=np.uint8)


# ============================================================
# 特征提取函数（artifact-only，全部不含语义）
# ============================================================
def feat_hist32(arr: np.ndarray) -> np.ndarray:
    """
    灰度强度直方图 32 bin，归一化到 [0,1]（和=1）。
    32 维，捕获亮度分布 / windowing 差异。
    """
    hist, _ = np.histogram(arr.flatten(), bins=32, range=(0, 256))
    hist = hist.astype(np.float32)
    total = hist.sum()
    if total > 0:
        hist /= total
    return hist  # (32,)


def feat_edge_ratio(arr: np.ndarray, border_px: int = 10) -> np.ndarray:
    """
    边缘暗角/零 padding 比例。
    - 提取图像四周 border_px 像素的边缘带
    - 计算边缘带中 < 5 的像素比例（黑色 padding / 暗角）
    - 也计算全图中 < 5 的像素比例（整体暗场比例）
    返回 2 维向量。
    """
    h, w = arr.shape
    # 边缘带 mask
    border_mask = np.zeros((h, w), dtype=bool)
    border_mask[:border_px, :] = True
    border_mask[-border_px:, :] = True
    border_mask[:, :border_px] = True
    border_mask[:, -border_px:] = True

    border_pixels = arr[border_mask]
    border_dark_ratio = float((border_pixels < 5).sum()) / max(len(border_pixels), 1)
    global_dark_ratio = float((arr.flatten() < 5).sum()) / max(arr.size, 1)
    return np.array([border_dark_ratio, global_dark_ratio], dtype=np.float32)  # (2,)


def feat_glcm(arr: np.ndarray) -> np.ndarray:
    """
    GLCM Haralick 特征 4 维：对比度、能量、同质性、相关。
    4 方向（0/45/90/135 度）平均。
    使用 skimage.feature.graycomatrix / graycoprops。
    """
    try:
        from skimage.feature import graycomatrix, graycoprops
    except ImportError:
        raise ImportError("需要 scikit-image: pip install scikit-image")

    # 降采样到 64x64 提速（GLCM 原图 224² 慢）
    arr_small = np.array(
        Image.fromarray(arr).resize((64, 64), Image.BILINEAR),
        dtype=np.uint8,
    )
    # 量化到 32 级（减少矩阵大小）
    arr_q = (arr_small // 8).astype(np.uint8)  # 0-31

    angles = [0, np.pi / 4, np.pi / 2, 3 * np.pi / 4]
    glcm = graycomatrix(
        arr_q,
        distances=[1],
        angles=angles,
        levels=32,
        symmetric=True,
        normed=True,
    )
    contrast = graycoprops(glcm, "contrast").mean()
    energy = graycoprops(glcm, "energy").mean()
    homogeneity = graycoprops(glcm, "homogeneity").mean()
    correlation = graycoprops(glcm, "correlation").mean()
    return np.array([contrast, energy, homogeneity, correlation], dtype=np.float32)  # (4,)


def feat_stats(arr: np.ndarray) -> np.ndarray:
    """
    整体统计量 4 维：均值、方差、偏度、峰度。
    纯 numpy，无 scipy（Windows OMP 安全）。
    """
    flat = arr.flatten().astype(np.float32)
    mean = float(flat.mean())
    var = float(flat.var())
    std = float(flat.std()) + 1e-8
    # 偏度 (skewness)
    skewness = float(((flat - mean) ** 3).mean()) / (std ** 3)
    # 峰度 (kurtosis)
    kurt = float(((flat - mean) ** 4).mean()) / (std ** 4) - 3.0
    return np.array([mean, var, skewness, kurt], dtype=np.float32)  # (4,)


def feat_fft_ratio(arr: np.ndarray) -> np.ndarray:
    """
    FFT 高低频能量比 1 维。
    - 计算 2D FFT magnitude，shift 到中心
    - low_freq: 中心 10x10 区域（DC + 低频）
    - high_freq: 其余（高频纹理/噪声）
    - ratio = high_freq_sum / (low_freq_sum + 1e-8)
    捕获采集模糊/锐化/噪声差异。
    """
    f = np.fft.fft2(arr.astype(np.float32))
    fshift = np.fft.fftshift(f)
    magnitude = np.abs(fshift)

    h, w = magnitude.shape
    cy, cx = h // 2, w // 2
    half_win = 5  # 中心 10x10

    low_mask = np.zeros((h, w), dtype=bool)
    low_mask[cy - half_win: cy + half_win, cx - half_win: cx + half_win] = True

    low_energy = float(magnitude[low_mask].sum())
    high_energy = float(magnitude[~low_mask].sum())
    ratio = high_energy / (low_energy + 1e-8)
    return np.array([ratio], dtype=np.float32)  # (1,)


# 所有特征提取器，按组命名
FEATURE_EXTRACTORS = {
    "hist32": feat_hist32,          # 32 维
    "edge_ratio": feat_edge_ratio,  # 2 维
    "glcm": feat_glcm,              # 4 维
    "stats": feat_stats,            # 4 维
    "fft_ratio": feat_fft_ratio,    # 1 维
}
# total = 43 维


def extract_all_features(arr: np.ndarray) -> np.ndarray:
    """提取全部 43 维 artifact-only 特征，concat 返回。"""
    feats = []
    for name, fn in FEATURE_EXTRACTORS.items():
        feats.append(fn(arr))
    return np.concatenate(feats)  # (43,)


# ============================================================
# 纯 numpy 5-fold CV AUROC（避免引入 sklearn 分层打乱的不确定性）
# ============================================================
def sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -100, 100)))


def logistic_regression_numpy(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_test: np.ndarray,
    lr: float = 0.1,
    n_iter: int = 300,
    l2: float = 1.0,
) -> np.ndarray:
    """
    简单 numpy logistic regression（二分类），L2 正则，梯度下降。
    返回 X_test 的 sigmoid 概率（1=OOD）。
    注：killshot 用 sklearn 更可靠；见下方 sklearn 路径。
    """
    n, d = X_train.shape
    w = np.zeros(d, dtype=np.float64)
    b = 0.0
    X = X_train.astype(np.float64)
    y = y_train.astype(np.float64)
    for _ in range(n_iter):
        logits = X @ w + b
        probs = sigmoid(logits)
        err = probs - y
        grad_w = (X.T @ err) / n + l2 * w / n
        grad_b = err.mean()
        w -= lr * grad_w
        b -= lr * grad_b
    Xt = X_test.astype(np.float64)
    return sigmoid(Xt @ w + b).astype(np.float32)


def cross_val_auroc(X: np.ndarray, y: np.ndarray, k: int = 5, use_sklearn: bool = True):
    """
    K-fold CV，返回 (mean_auroc, std_auroc, fold_aurocs)。
    优先用 sklearn LogisticRegression（更稳定），fallback 纯 numpy。
    """
    n = len(y)
    idx = np.arange(n)
    rng = np.random.RandomState(RANDOM_SEED)
    rng.shuffle(idx)

    fold_size = n // k
    fold_aurocs = []

    for fold in range(k):
        val_idx = idx[fold * fold_size: (fold + 1) * fold_size]
        train_idx = np.concatenate([idx[: fold * fold_size], idx[(fold + 1) * fold_size:]])

        X_tr, X_val = X[train_idx], X[val_idx]
        y_tr, y_val = y[train_idx], y[val_idx]

        # 标准化（用 train 统计量）
        mu = X_tr.mean(axis=0)
        sigma = X_tr.std(axis=0) + 1e-8
        X_tr_s = (X_tr - mu) / sigma
        X_val_s = (X_val - mu) / sigma

        if use_sklearn:
            try:
                from sklearn.linear_model import LogisticRegression
                clf = LogisticRegression(
                    C=1.0, max_iter=1000, solver="lbfgs",
                    random_state=RANDOM_SEED
                )
                clf.fit(X_tr_s, y_tr)
                probs = clf.predict_proba(X_val_s)[:, 1].astype(np.float32)
            except ImportError:
                use_sklearn = False
                probs = logistic_regression_numpy(X_tr_s, y_tr, X_val_s)
        else:
            probs = logistic_regression_numpy(X_tr_s, y_tr, X_val_s)

        auroc = auroc_numpy(y_val, probs)
        fold_aurocs.append(auroc)

    auroc_arr = np.array(fold_aurocs)
    return float(auroc_arr.mean()), float(auroc_arr.std()), fold_aurocs


# ============================================================
# 主逻辑
# ============================================================
def main(smoke_n: int = 0):
    n_sample = smoke_n if smoke_n > 0 else N_SAMPLE
    print(f"[C107] artifact OOD kill-shot, n_per_dataset={n_sample}, target_size={TARGET_SIZE}x{TARGET_SIZE}")

    rng = random.Random(RANDOM_SEED)

    # 1. 采样 NIH 图像
    nih_files = [p for p in NIH_DIR.iterdir() if p.suffix.lower() == ".png"]
    rng.shuffle(nih_files)
    nih_files = nih_files[:n_sample]
    print(f"[C107] NIH samples: {len(nih_files)}")

    # 2. 采样 VinDr 图像（从 test/ + train/ 各取）
    vindr_test = [p for p in (VINDR_DIR / "test").iterdir() if p.suffix.lower() == ".png"]
    vindr_train = [p for p in (VINDR_DIR / "train").iterdir() if p.suffix.lower() == ".png"]
    vindr_all = vindr_test + vindr_train
    rng.shuffle(vindr_all)
    vindr_files = vindr_all[:n_sample]
    print(f"[C107] VinDr samples: {len(vindr_files)}")

    # 3. 提取特征
    def extract_batch(files, label, desc):
        X_list = []
        for i, p in enumerate(files):
            if (i + 1) % 50 == 0 or i == 0:
                print(f"  [{desc}] {i+1}/{len(files)}")
            try:
                arr = load_image_gray224(p)
                feat = extract_all_features(arr)
                X_list.append(feat)
            except Exception as e:
                print(f"  [WARN] skip {p.name}: {e}", file=sys.stderr)
        return np.array(X_list, dtype=np.float32)

    print("[C107] extracting NIH features...")
    X_nih = extract_batch(nih_files, 0, "NIH")
    print("[C107] extracting VinDr features...")
    X_vindr = extract_batch(vindr_files, 1, "VinDr")

    n_nih = len(X_nih)
    n_vindr = len(X_vindr)
    X_all = np.concatenate([X_nih, X_vindr], axis=0)
    y_all = np.array([0] * n_nih + [1] * n_vindr, dtype=np.int32)
    print(f"[C107] X_all shape: {X_all.shape}, y counts: NIH={n_nih}, VinDr={n_vindr}")

    # 4. 全特征 5-fold CV AUROC
    print("[C107] running 5-fold CV (all features)...")
    mean_auroc, std_auroc, fold_aurocs = cross_val_auroc(X_all, y_all, k=5)
    print(f"[C107] ALL features: AUROC = {mean_auroc:.4f} ± {std_auroc:.4f}")
    print(f"         folds: {[round(a,4) for a in fold_aurocs]}")

    # 5. 各特征组单独 AUROC（用完整数据，单维度评估检验哪个 artifact 最强）
    print("[C107] per-feature-group AUROC (full data, single group)...")
    feat_dim_names = []  # 用于 per-dim csv
    # 构建各特征组的列 index
    feat_group_aurocs = {}
    col_offset = 0
    feat_dims = {
        "hist32": 32,
        "edge_ratio": 2,
        "glcm": 4,
        "stats": 4,
        "fft_ratio": 1,
    }
    per_dim_rows = []

    for group_name, dim in feat_dims.items():
        X_group = X_all[:, col_offset: col_offset + dim]
        col_offset += dim

        # 用 all-data leave-one-out or 直接单组做 CV
        mean_g, std_g, _ = cross_val_auroc(X_group, y_all, k=5)
        feat_group_aurocs[group_name] = (mean_g, std_g)
        print(f"  {group_name:12s}: {mean_g:.4f} ± {std_g:.4f} ({dim} dims)")

        # 各维度单独 AUROC（直接全集）
        for d_i in range(dim):
            feat_score = X_group[:, d_i]
            # 标准化
            mu, sigma = feat_score.mean(), feat_score.std() + 1e-8
            feat_score_n = (feat_score - mu) / sigma
            a = auroc_numpy(y_all, feat_score_n)
            feat_name = f"{group_name}_d{d_i}"
            per_dim_rows.append({
                "feature_dim": feat_name,
                "auroc": round(a, 4),
            })

    # 6. 保存 CSV
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 主结果 csv
    csv_rows = [
        {
            "feature_set": "all_43dim",
            "auroc_mean": round(mean_auroc, 4),
            "auroc_std": round(std_auroc, 4),
            "n_samples": len(X_all),
        }
    ]
    for group_name, (ma, ms) in feat_group_aurocs.items():
        csv_rows.append({
            "feature_set": group_name,
            "auroc_mean": round(ma, 4),
            "auroc_std": round(ms, 4),
            "n_samples": len(X_all),
        })

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["feature_set", "auroc_mean", "auroc_std", "n_samples"])
        writer.writeheader()
        writer.writerows(csv_rows)
    print(f"[C107] main results -> {OUT_CSV}")

    # per-dim csv
    with open(OUT_PER_FEAT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["feature_dim", "auroc"])
        writer.writeheader()
        writer.writerows(per_dim_rows)
    print(f"[C107] per-dim results -> {OUT_PER_FEAT_CSV}")

    # 7. 最终判据 print
    print("\n" + "=" * 60)
    print("C107 Kill-Shot: artifact-only OOD AUROC (NIH=ID vs VinDr=OOD)")
    print("公平设计: 统一 resize 到 224x224，分辨率差异已消除")
    print("判据: AUROC > 0.95 -> 污染坐实，benchmark 严重质疑，claim 成立")
    print("      AUROC 0.80-0.95 -> 中等污染，值得报告")
    print("      AUROC <= 0.80  -> 污染有限，claim 较弱")
    print("-" * 60)
    flag = ""
    if mean_auroc > 0.95:
        flag = " *** 污染坐实 (claim 成立!)"
    elif mean_auroc > 0.80:
        flag = " -> 中等污染"
    else:
        flag = " -> 污染有限，claim 较弱"
    print(f"  ALL 43-dim: AUROC = {mean_auroc:.4f} ± {std_auroc:.4f}{flag}")
    print("\n  各特征组单独 AUROC:")
    for group_name, (ma, ms) in feat_group_aurocs.items():
        print(f"    {group_name:12s}: {ma:.4f} ± {ms:.4f}")
    print("=" * 60)

    if smoke_n > 0:
        print(f"\n[SMOKE] 仅用 {smoke_n} 张/数据集，数字供验算，非最终结果。全量跑去掉 --smoke。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="C107 artifact OOD kill-shot")
    parser.add_argument(
        "--smoke", type=int, default=0,
        help="smoke 测试每个数据集张数（0=全量 500 张/数据集）"
    )
    args = parser.parse_args()
    main(smoke_n=args.smoke)
