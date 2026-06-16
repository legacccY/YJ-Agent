"""
conspicuity_proxy.py — PC-C C1 无 mask 代理特征提取（纯 CPU）
服务: MedAD-FailMap Phase 0, PC-C (C1)

输入: BraTS test/tumor/ 目录（或任意图像目录）+ anomaly_scores csv
产出: per-image 特征 csv，列:
  filename, anomaly_score, label,
  sigma_global,          -- 全图灰度标准差
  glcm_cluster_prom,     -- GLCM Cluster Prominence (距离=[1,2,3], 角度=4方向平均)
  glcm_contrast,         -- GLCM Contrast
  fft_spectral_entropy,  -- FFT 频谱熵
  cnr_proxy_otsu         -- Otsu 伪前景 CNR_proxy = |fg_mean - bg_mean| / pooled_std

依赖: numpy, scikit-image, Pillow
不依赖 scipy (OMP#15 风险)

参考:
  - 02_ACCEPTANCE.md: per-image 判据用无 mask 代理
  - Mammogram difficulty GLCM (arXiv/PMC12092920): 34 GLCM 无 mask AUC=0.75 先例
  - 03_phase0_plan.md C1

🔴 TODO: GLCM 距离/角度参数未找到 MedAD 领域官方设定，
         此处 distances=[1,2,3], angles=[0,pi/4,pi/2,3pi/4] 取自 scikit-image 文档默认，
         需 researcher/主线确认是否合理。
"""

import argparse
import csv
from pathlib import Path

import numpy as np
from PIL import Image
from skimage.feature import graycomatrix, graycoprops


# ============================================================
# 特征函数（纯 numpy/skimage，无 scipy）
# ============================================================

def feat_sigma_global(img_f32):
    """全图灰度标准差 (float32 [0,1])"""
    return float(np.std(img_f32))


def feat_glcm(img_f32, n_levels=64):
    """
    GLCM Cluster Prominence + Contrast
    distances=[1,2,3], angles=4方向, symmetric=True, normalized=True

    Cluster Prominence 公式 (Haralick 1973):
      CP = sum_{i,j} (i + j - mu_i - mu_j)^4 * P(i,j)
      mu_i = sum_i i * sum_j P(i,j)
      mu_j = sum_j j * sum_i P(i,j)

    graycoprops 不支持 cluster_prominence, 手动计算.
    🔴 TODO: n_levels=64, distances=[1,2,3] 未找到领域官方设定
    """
    # 量化到 [0, n_levels-1]
    img_uint = (img_f32 * (n_levels - 1)).astype(np.uint8)
    distances = [1, 2, 3]
    angles    = [0, np.pi/4, np.pi/2, 3*np.pi/4]
    glcm = graycomatrix(img_uint, distances=distances, angles=angles,
                        levels=n_levels, symmetric=True, normed=True)
    # shape: (n_levels, n_levels, n_dist, n_angles)

    # Contrast via graycoprops (支持)
    ct = float(graycoprops(glcm, "contrast").mean())

    # Cluster Prominence: 手动计算, 对所有 dist/angle 取均值
    cp_vals = []
    n_dist  = len(distances)
    n_ang   = len(angles)
    I = np.arange(n_levels, dtype=np.float64).reshape(-1, 1)  # (L,1)
    J = np.arange(n_levels, dtype=np.float64).reshape(1, -1)  # (1,L)
    for d in range(n_dist):
        for a in range(n_ang):
            P = glcm[:, :, d, a].astype(np.float64)
            P_sum = P.sum()
            if P_sum == 0:
                continue
            P = P / P_sum
            mu_i = float((I * P.sum(axis=1, keepdims=True)).sum())
            mu_j = float((J * P.sum(axis=0, keepdims=True)).sum())
            cp_val = float(np.sum(((I + J - mu_i - mu_j) ** 4) * P))
            cp_vals.append(cp_val)

    cp = float(np.mean(cp_vals)) if cp_vals else 0.0
    return cp, ct


def feat_fft_spectral_entropy(img_f32):
    """
    FFT 频谱熵: Shannon entropy of normalized power spectrum
    H = -sum(p * log2(p+eps))
    """
    fft2  = np.fft.fft2(img_f32)
    power = np.abs(fft2) ** 2
    p     = power / (power.sum() + 1e-12)
    eps   = 1e-12
    entropy = float(-np.sum(p * np.log2(p + eps)))
    return entropy


def feat_cnr_proxy_otsu(img_f32):
    """
    Otsu 伪前景 CNR_proxy = |mean(fg) - mean(bg)| / sqrt((std(fg)^2 + std(bg)^2) / 2)
    前景 = 像素值 >= Otsu 阈值
    若 fg 或 bg 为空返回 0.0
    不用 scipy (OMP#15); 纯 numpy Otsu
    """
    thresh = _otsu_threshold_numpy(img_f32)
    fg_mask = img_f32 >= thresh
    bg_mask = ~fg_mask
    if fg_mask.sum() == 0 or bg_mask.sum() == 0:
        return 0.0
    fg_vals = img_f32[fg_mask]
    bg_vals = img_f32[bg_mask]
    fg_mean, fg_std = fg_vals.mean(), fg_vals.std()
    bg_mean, bg_std = bg_vals.mean(), bg_vals.std()
    pooled_std = float(np.sqrt((fg_std**2 + bg_std**2) / 2.0))
    if pooled_std < 1e-8:
        return 0.0
    return float(abs(fg_mean - bg_mean) / pooled_std)


def _otsu_threshold_numpy(img_f32, n_bins=256):
    """纯 numpy Otsu 阈值（避免 skimage/scipy 的 OMP 冲突风险）"""
    hist, bin_edges = np.histogram(img_f32.ravel(), bins=n_bins, range=(0.0, 1.0))
    hist = hist.astype(np.float64)
    total = hist.sum()
    if total == 0:
        return 0.5
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2.0
    # Otsu: maximize inter-class variance
    weight1 = np.cumsum(hist)
    weight2 = total - weight1
    mean1   = np.cumsum(hist * bin_centers) / (weight1 + 1e-12)
    mean_total = (hist * bin_centers).sum() / total
    mean2   = (mean_total * total - np.cumsum(hist * bin_centers)) / (weight2 + 1e-12)
    var_between = weight1 * weight2 * (mean1 - mean2) ** 2
    idx = np.argmax(var_between)
    return float(bin_centers[idx])


# ============================================================
# 主逻辑
# ============================================================

def extract_features(img_path, size=64):
    """读图 -> resize 64x64 灰度 -> 提取所有代理特征"""
    img = Image.open(img_path).convert("L").resize((size, size), Image.BILINEAR)
    arr = np.array(img, dtype=np.float32) / 255.0

    sigma   = feat_sigma_global(arr)
    cp, ct  = feat_glcm(arr)
    fft_ent = feat_fft_spectral_entropy(arr)
    cnr     = feat_cnr_proxy_otsu(arr)
    return sigma, cp, ct, fft_ent, cnr


def run_conspicuity(args):
    img_dir   = Path(args.img_dir)
    out_csv   = Path(args.out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    # 读 anomaly scores (若提供)
    score_map = {}    # filename -> (anomaly_score, label)
    if args.score_csv and Path(args.score_csv).exists():
        with open(args.score_csv, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                score_map[row["filename"]] = (
                    float(row["anomaly_score"]),
                    int(row.get("label", -1)),
                )

    # 枚举图像
    exts = {".png", ".jpg", ".jpeg", ".PNG", ".JPG", ".JPEG"}
    img_files = sorted([p for p in img_dir.iterdir() if p.suffix in exts])
    if len(img_files) == 0:
        raise RuntimeError(f"No images found in {img_dir}")

    print(f"[conspicuity] extracting features from {len(img_files)} images ...")

    rows_out = []
    for i, p in enumerate(img_files):
        if (i + 1) % 200 == 0:
            print(f"  {i+1}/{len(img_files)}")
        try:
            sigma, cp, ct, fft_ent, cnr = extract_features(p, size=64)
        except Exception as e:
            print(f"  [warn] {p.name}: {e}")
            sigma = cp = ct = fft_ent = cnr = float("nan")

        sc, lbl = score_map.get(p.name, (float("nan"), -1))
        rows_out.append({
            "filename":           p.name,
            "anomaly_score":      sc,
            "label":              lbl,
            "sigma_global":       round(sigma,   6),
            "glcm_cluster_prom":  round(cp,      6),
            "glcm_contrast":      round(ct,       6),
            "fft_spectral_entropy": round(fft_ent, 6),
            "cnr_proxy_otsu":     round(cnr,      6),
        })

    fieldnames = list(rows_out[0].keys())
    with open(out_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows_out)

    print(f"[conspicuity] done. {len(rows_out)} rows -> {out_csv}")


# ============================================================
# Entry point
# ============================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PC-C C1: 无 mask conspicuity 代理特征提取")
    _root = Path(__file__).resolve().parent.parent
    _data = _root / "data" / "brats" / "test" / "tumor"
    _res  = _root / "results"

    parser.add_argument("--img-dir",   default=str(_data),
                        help="图像目录 (BraTS test/tumor/ 或任意)")
    parser.add_argument("--score-csv", default=str(_res / "anomaly_scores_brats_ae.csv"),
                        help="anomaly score csv (可选，用于合并输出)")
    parser.add_argument("--out-csv",   default=str(_res / "conspicuity_features.csv"),
                        help="输出 per-image 特征 csv")
    args = parser.parse_args()
    run_conspicuity(args)
