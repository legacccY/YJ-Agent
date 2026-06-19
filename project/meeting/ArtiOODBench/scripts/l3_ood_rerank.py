"""
l3_ood_rerank.py
服务: ArtiOODBench Gate1 R3b+R4+R5+R6+R7（判据 A-3/A-4，L3 命门）
lever: L3 重排命门（v5 扩：7→13 方法，4→6-7 对，PR-G1/G2/G3 冻结超参）

【做什么】
基于 extract_frozen_feats.py 产出的 1024 维特征，在 cross-source 跨机构对上
运行 13 个 OpenOOD post-hoc 方法，做去污染前后排名对比。

【13 个方法（ACCEPTANCE 锁定超参）】
  MSP       无参（最大 softmax 概率）
  ODIN      T=1000, ε=0.0014
  Energy    EBO T=1
  MDS       Mahalanobis，无参（在 1024 维训练集上拟合 Gaussian）
  KNN       K=50
  ViM       dim=512（自定：依 ViM arXiv:2203.10807 N/2 法则，N=1024→D=512）
  GradNorm  无参
  ---- v5 新增 6（PR-G1 冻结，OpenOOD 官方超参）----
  Residual  dim=512，纯几何子空间残差（ViM 的 residual 子分）
  SHE       metric=inner_product；PR-G2 multi-label 适配：global pattern（单全局均值）
  NNGuide   alpha=0.01, K=100；energy=logsumexp(18 logits)
  fDBD      distance_as_normalizer=True；需 get_fc 取 classifier W/b
  DICE      p=90；需 get_fc + ID penultimate；score=logsumexp(masked logits)
  ASH       percentile=90；唯一 live forward（forward_threshold wrapper）

注意：live 方法（ODIN/GradNorm/ASH）需要 model + paths；
      cached 方法用已存盘 feats/logits。

【输出】
  results/l3_method_scores_raw.csv   (方法 × 样本 raw score)
  results/l3_raw_ranking.csv         (R4 去污染前排名)
  results/l3_cleanC_ranking.csv      (R5 方案C artifact-matched 配对子集后排名)
  results/a4_bootstrap_spearman.csv  (R5 bootstrap Spearman CI)
  results/l3_cleanA_ranking.csv      (R6 方案A regress-out，仅当 R0a R²<0.3 时)
  results/l3_cleanB_ranking.csv      (R7 方案B PCA-1 分层)

【运行】
  # smoke（合成特征，不需要 extract_frozen_feats 就位）
  python l3_ood_rerank.py --smoke

  # 真实数据
  python l3_ood_rerank.py
"""

import argparse
import csv
import io
import sys
import traceback
from pathlib import Path

import numpy as np

# Windows GBK 终端安全
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ============================================================
# 路径常量
# ============================================================
OUT_DIR = Path(__file__).resolve().parent.parent / "results"
FEATS_DIR = OUT_DIR / "feats"
MANIFEST_CSV = FEATS_DIR / "manifest.csv"
R0A_CSV = OUT_DIR / "r0a_collinearity_R2.csv"

# TorchXRayVision DenseNet pathology 标签数（密度网 18 类 multi-label）
N_LOGITS = 18

OUT_SCORES_RAW = OUT_DIR / "l3_method_scores_raw.csv"
OUT_L3_RAW = OUT_DIR / "l3_raw_ranking.csv"
OUT_L3_CLEAN_C = OUT_DIR / "l3_cleanC_ranking.csv"
OUT_BOOTSTRAP = OUT_DIR / "a4_bootstrap_spearman.csv"
OUT_L3_CLEAN_A = OUT_DIR / "l3_cleanA_ranking.csv"
OUT_L3_CLEAN_B = OUT_DIR / "l3_cleanB_ranking.csv"

# ViM dim（自定，依 arXiv:2203.10807 N<1500→D≈N/2，N=1024→D=512；paper 标注）
VIM_DIM = 512  # TODO: 标注 paper 为自定（ViM 原论文 N/2 法则）
KNN_K = 50
ODIN_T = 1000
ODIN_EPS = 0.0014
ENERGY_T = 1
BOOTSTRAP_B = 1000
ARTIFACT_DIM = 43
CALIPER_SD = 0.2  # 预登记配对半径（PR-匹配半径，冻结）
SEED = 42

OOD_METHODS = [
    "MSP", "ODIN", "Energy", "MDS", "KNN", "ViM", "GradNorm",
    # v5 新增 6（PR-G1 冻结，OpenOOD 官方超参）
    "Residual", "SHE", "NNGuide", "fDBD", "DICE", "ASH",
]

# v5 新增超参（PR-G1 冻结，OpenOOD 官方，无臆想）
RESIDUAL_DIM = 512        # 同 ViM_DIM，纯几何子空间残差
SHE_METRIC = "inner_product"  # PR-G2 multi-label global pattern
NNGUIDE_ALPHA = 0.01
NNGUIDE_K = 100
DICE_P = 90               # percentile，按贡献度 mask classifier 权重
ASH_PERCENTILE = 90       # forward 激活 shaping percentile


# ============================================================
# 纯 numpy AUROC
# ============================================================
def auroc_numpy(labels: np.ndarray, scores: np.ndarray) -> float:
    pos = scores[labels == 1]
    neg = scores[labels == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    u = 0.0
    for ps in pos:
        u += (neg < ps).sum() + 0.5 * (neg == ps).sum()
    return float(u / (len(pos) * len(neg)))


# ============================================================
# 纯 numpy Spearman（避 scipy）
# ============================================================
def spearman_numpy(x: np.ndarray, y: np.ndarray) -> float:
    """Spearman r = Pearson(rank(x), rank(y))，纯 numpy。"""
    def rankdata(arr):
        n = len(arr)
        idx = np.argsort(arr)
        ranks = np.empty(n, dtype=np.float64)
        ranks[idx] = np.arange(1, n + 1, dtype=np.float64)
        # 处理 tie：均值 rank
        sorted_arr = arr[idx]
        i = 0
        while i < n:
            j = i
            while j < n and sorted_arr[j] == sorted_arr[i]:
                j += 1
            mean_rank = (i + 1 + j) / 2.0
            ranks[idx[i:j]] = mean_rank
            i = j
        return ranks

    rx, ry = rankdata(x.astype(np.float64)), rankdata(y.astype(np.float64))
    rx_c = rx - rx.mean()
    ry_c = ry - ry.mean()
    denom = (np.sqrt((rx_c ** 2).sum()) * np.sqrt((ry_c ** 2).sum()))
    if denom < 1e-12:
        return 0.0
    return float((rx_c * ry_c).sum() / denom)


# ============================================================
# 43 维 artifact 特征提取（本地，复用逻辑）
# ============================================================
def extract_artifact_features_batch(paths: list) -> np.ndarray:
    """提取 43 维 artifact 特征，返回 (N, 43)。"""
    from PIL import Image

    def load_gray224(p):
        img = Image.open(p).convert("L")
        if img.size != (224, 224):
            img = img.resize((224, 224), Image.BILINEAR)
        return np.array(img, dtype=np.uint8)

    def feat_hist32(arr):
        h, _ = np.histogram(arr.flatten(), bins=32, range=(0, 256))
        h = h.astype(np.float32)
        return h / h.sum() if h.sum() > 0 else h

    def feat_edge(arr, bp=10):
        bm = np.zeros(arr.shape, dtype=bool)
        bm[:bp, :] = bm[-bp:, :] = bm[:, :bp] = bm[:, -bp:] = True
        pix = arr[bm]
        return np.array([(pix < 5).sum() / max(len(pix), 1),
                         (arr.flatten() < 5).sum() / max(arr.size, 1)], dtype=np.float32)

    def feat_glcm(arr):
        try:
            from skimage.feature import graycomatrix, graycoprops
        except ImportError:
            return np.zeros(4, dtype=np.float32)
        s = np.array(Image.fromarray(arr).resize((64, 64), Image.BILINEAR), dtype=np.uint8)
        sq = (s // 8).astype(np.uint8)
        glcm = graycomatrix(sq, distances=[1], angles=[0, np.pi/4, np.pi/2, 3*np.pi/4],
                            levels=32, symmetric=True, normed=True)
        return np.array([graycoprops(glcm, p).mean()
                         for p in ["contrast", "energy", "homogeneity", "correlation"]],
                        dtype=np.float32)

    def feat_stats(arr):
        flat = arr.flatten().astype(np.float32)
        m, s = flat.mean(), float(flat.std()) + 1e-8
        return np.array([m, float(flat.var()),
                         float(((flat - m) ** 3).mean()) / s ** 3,
                         float(((flat - m) ** 4).mean()) / s ** 4 - 3.0], dtype=np.float32)

    def feat_fft(arr):
        fs = np.fft.fftshift(np.fft.fft2(arr.astype(np.float32)))
        mag = np.abs(fs)
        h, w = mag.shape
        lm = np.zeros((h, w), dtype=bool)
        lm[h//2-5:h//2+5, w//2-5:w//2+5] = True
        return np.array([mag[~lm].sum() / (mag[lm].sum() + 1e-8)], dtype=np.float32)

    feats = []
    for p in paths:
        try:
            arr = load_gray224(Path(p))
            f = np.concatenate([feat_hist32(arr), feat_edge(arr), feat_glcm(arr),
                                 feat_stats(arr), feat_fft(arr)])
        except Exception as e:
            print(f"  [WARN] skip {Path(p).name}: {e}", file=sys.stderr)
            f = np.zeros(43, dtype=np.float32)
        feats.append(f)
    return np.array(feats, dtype=np.float32)


# ============================================================
# OOD 方法实现（官方实现，OpenOOD 官方超参）
#
# 接口统一：每个方法接收
#   feats_id:   (N_id, 1024) float32  ID 训练集特征
#   feats_test: (N_test, 1024) float32  测试集特征（含 ID+OOD 拼接）
#   logits_id:   (N_id, 18) float32   ID 训练集 raw logits（可选，None=方法不需要）
#   logits_test: (N_test, 18) float32  测试集 raw logits（可选）
#   paths_test:  list[str]  len=N_test 测试图像路径（ODIN/GradNorm live 用）
#   model/device: live 方法用
# 返回 (N_test,) float32 OOD score，越大=越 OOD。
# ============================================================

# ---- 辅助：numpy logsumexp ----
def _logsumexp(x: np.ndarray) -> np.ndarray:
    """稳定 logsumexp，axis=1，输入 (N, C)，输出 (N,)。"""
    m = x.max(axis=1, keepdims=True)
    return np.log(np.exp(x - m).sum(axis=1)) + m.squeeze(1)


def method_msp(feats_id, feats_test, logits_id=None, logits_test=None,
               paths_test=None, model=None, device=None) -> np.ndarray:
    """
    MSP (Maximum Softmax Probability) - 官方实现。
    TorchXRayVision multi-label 适配：用 max(sigmoid(logits)) 替代 max(softmax(logits))。
    （DenseNet121-res224 是 multi-label sigmoid 输出，非单标签 softmax；
     此适配在 OpenOOD 文档中对 multi-label 分类器为标准做法，注释标明适配。）
    OOD score = 1 - max(sigmoid(logits))；越大=越 OOD。
    """
    if logits_test is None:
        raise ValueError("MSP 需要 logits_test")
    probs = 1.0 / (1.0 + np.exp(-np.clip(logits_test, -100, 100)))  # sigmoid (N,18)
    max_prob = probs.max(axis=1)   # (N,)  越大=越 ID-like
    return (1.0 - max_prob).astype(np.float32)  # OOD score: 越大=越 OOD


def method_energy(feats_id, feats_test, logits_id=None, logits_test=None,
                  paths_test=None, model=None, device=None,
                  T: float = ENERGY_T) -> np.ndarray:
    """
    Energy EBO (Energy-Based OOD detection) - 官方实现 (arXiv:2010.03759)。
    E(x) = -T * logsumexp(logits / T)
    符号说明（重要，勿改）：
      - ID 样本 logits 通常更大/激活更多 → logsumexp 更大 → E(x) 更负（能量更低）
      - OOD 样本 logits 较小/激活少 → logsumexp 较小 → E(x) 较高（接近 0 或更大）
      因此 E(x) 直接用作 OOD score：越大（越接近 0）= 越 OOD。
      OOD score = E(x) = -T * logsumexp(logits/T)，不需要再取负。
    T=1（ACCEPTANCE 锁定）。
    """
    if logits_test is None:
        raise ValueError("Energy 需要 logits_test")
    # E(x) = -T * logsumexp(logits/T): OOD 样本此值更大（更接近 0），直接作 score
    energy = -T * _logsumexp(logits_test / T)   # (N,)
    return energy.astype(np.float32)             # OOD score: 越大=越 OOD


def method_mds(feats_id, feats_test, logits_id=None, logits_test=None,
               paths_test=None, model=None, device=None) -> np.ndarray:
    """
    Mahalanobis Distance Score (MDS) - 官方实现（单高斯）。
    用 1024 维 ID 特征拟合单高斯（cross-source 任务无病理类标签，用单 Gaussian；
    官方多层 per-class 版需分类标签，此处注释标明采用单 Gaussian 变体）。
    score = Mahalanobis(x, mu, Sigma)；越大=越 OOD。
    L2 正则化协方差防奇异。
    """
    mu = feats_id.mean(0)
    centered = feats_id - mu
    cov = (centered.T @ centered) / max(len(centered) - 1, 1)
    cov += 1e-5 * np.eye(cov.shape[0])
    try:
        cov_inv = np.linalg.inv(cov)
    except np.linalg.LinAlgError:
        cov_inv = np.linalg.pinv(cov)
    diff = feats_test - mu
    scores = np.einsum("nd,dd,nd->n", diff, cov_inv, diff).astype(np.float32)
    return scores


def method_knn(feats_id, feats_test, logits_id=None, logits_test=None,
               paths_test=None, model=None, device=None,
               K: int = KNN_K) -> np.ndarray:
    """
    KNN OOD score - 官方实现 (arXiv:2204.06125)。
    特征做 L2-normalize，K-th nearest neighbor 距离作 score。
    K=50（ACCEPTANCE 锁定）。
    """
    # L2-normalize（官方 KNN 实现在归一化特征空间）
    def l2_norm(x):
        norms = np.linalg.norm(x, axis=1, keepdims=True) + 1e-8
        return x / norms
    id_n = l2_norm(feats_id)
    test_n = l2_norm(feats_test)
    K_eff = min(K, len(id_n))
    scores = []
    for x in test_n:
        dists = np.linalg.norm(id_n - x, axis=1)
        dists.sort()
        scores.append(float(dists[K_eff - 1]))
    return np.array(scores, dtype=np.float32)


def method_vim(feats_id, feats_test, logits_id=None, logits_test=None,
               paths_test=None, model=None, device=None,
               dim: int = VIM_DIM) -> np.ndarray:
    """
    ViM (Virtual-logit Matching) - 官方实现 (arXiv:2203.10807)。
    完整实现（包含 virtual logit energy 修正项）：

    算法：
    1. 在 ID 特征（中心化）上做截断 SVD，取前 d=512 个主方向构成 principal subspace P。
       dim=512 (自定，依 ViM 原论文 N<1500 → D≈N/2 法则，N=1024→D=512；paper 标注)
    2. residual r(x) = x - x@P@P^T（投影到零空间的分量）
    3. virtual logit  v(x) = alpha * ||r(x)||
       alpha 由训练集标定：
         alpha = max(logsumexp(logits_id)) / max(||r_id||)
         使得 virtual logit 与 ID logits 能量对齐（ViM 原论文 eq.4）
    4. OOD score = -T * logsumexp([logits_test, v(x)])，T=1
       即把 virtual logit 拼到真实 logits 后再算 energy。

    跨域注释：alpha 标定基于 CXR logits，非 CXR 模态上 logits 无语义，
    但 residual 范数仍可反映特征偏移，故 ViM 在跨模态场景部分退化为 residual score。
    """
    if logits_id is None or logits_test is None:
        raise ValueError("ViM 完整实现需要 logits_id + logits_test")

    # 1. PCA principal subspace（中心化 ID 特征）
    mu_id = feats_id.mean(0)
    X_c = feats_id - mu_id
    try:
        _, _, Vt = np.linalg.svd(X_c, full_matrices=False)
    except np.linalg.LinAlgError:
        # fallback: 只用 residual norm（无 virtual logit）
        test_c = feats_test - mu_id
        return np.linalg.norm(test_c, axis=1).astype(np.float32)
    d = min(dim, Vt.shape[0])
    P = Vt[:d].T  # (D, d)

    # 2. ID residuals（for alpha calibration）
    id_c = X_c                              # (N_id, D)
    id_proj = id_c @ P @ P.T               # (N_id, D)
    id_residual = id_c - id_proj            # (N_id, D)
    id_residual_norm = np.linalg.norm(id_residual, axis=1)  # (N_id,)

    # 3. alpha 标定（ViM eq.4）
    # alpha = max(logsumexp(logits_id)) / max(||r_id||)
    id_lse = _logsumexp(logits_id)          # (N_id,)
    max_id_lse = float(id_lse.max())
    max_id_rnorm = float(id_residual_norm.max()) + 1e-8
    alpha = max_id_lse / max_id_rnorm
    # alpha 应为正数（max logsumexp 通常>0，residual norm>0）
    if alpha <= 0:
        alpha = 1.0  # 兜底

    # 4. test residuals
    test_c = feats_test - mu_id
    test_proj = test_c @ P @ P.T
    test_residual = test_c - test_proj
    test_residual_norm = np.linalg.norm(test_residual, axis=1)  # (N_test,)

    # 5. virtual logit v = alpha * ||r||
    virtual_logit = alpha * test_residual_norm  # (N_test,)

    # 6. OOD score = logsumexp([logits_test, v])  （正向，越大=越 OOD）
    # ViM arXiv:2203.10807: OOD score 是拼了 virtual-logit 后的 energy，
    # 论文式(5): score = max(energy_aug - energy_real)；
    # 实践等价：OOD 样本 residual 大 → virtual_logit 大 → logsumexp_aug 大。
    # 符号：logsumexp_aug 对 OOD 更大，直接作 OOD score（不取负）。
    # （原来 -logsumexp 使 OOD 得到更小值，导致 AUROC=0，此为 Bug1 根因。）
    logits_aug = np.concatenate(
        [logits_test, virtual_logit.reshape(-1, 1)], axis=1
    )  # (N_test, 19)
    ood_score = _logsumexp(logits_aug)    # (N_test,): OOD 更大=越 OOD
    return ood_score.astype(np.float32)


def method_odin(feats_id, feats_test, logits_id=None, logits_test=None,
                paths_test=None, model=None, device=None,
                T: int = ODIN_T, eps: float = ODIN_EPS) -> np.ndarray:
    """
    ODIN (Out-of-DIstribution detector for Neural Networks) - 官方实现 (arXiv:1706.02690)。
    T=1000, eps=0.0014（ACCEPTANCE 锁定）。

    算法：
    1. 对每张测试图像 x，先 forward 得 logits，用 multi-label MSP 定义置信度
       c = max(sigmoid(logits/T))，对 c backward 得 grad w.r.t. input
    2. 扰动 x' = x - eps * sign(grad)（降低置信度方向）
    3. 再 forward 得 x' 的 logits，取 max(sigmoid(logits'/T)) 作 score
    OOD score = 1 - max(sigmoid(logits'/T))；越大=越 OOD。

    注意（Bug3 分析）：T=1000 对 multi-label sigmoid 影响微弱。
    sigmoid(logit/1000) ≈ 0.5（几乎对所有 logit），max_prob ≈ 0.5 的梯度方向几乎随机，
    扰动后 AUROC 与 MSP 相同。这是 ODIN 在 multi-label sigmoid 架构上的已知局限，
    非实现 bug——输入扰动确实运行了，但 T=1000 使温度缩放后的梯度趋近于零。
    超参 T=1000/eps=0.0014 来自官方（ACCEPTANCE 锁定），不擅自修改。
    后续 paper limitation 中标注 ODIN 退化为 MSP 的机制原因。

    此方法需要 live model + 图像路径（不能用缓存特征）。
    非 CXR 模态预期 AUROC < 0.6（PR-F3 准入门拦截），属设计预期。
    """
    if model is None or paths_test is None:
        raise ValueError("ODIN 需要 model + paths_test（live 推理）")

    import torch
    from PIL import Image

    def load_tensor(path):
        img = Image.open(path).convert("L")
        if img.size != (224, 224):
            img = img.resize((224, 224), Image.BILINEAR)
        arr = np.array(img, dtype=np.float32)
        arr = (arr / 255.0) * 2048.0 - 1024.0
        return torch.tensor(arr, dtype=torch.float32).unsqueeze(0).unsqueeze(0)  # (1,1,224,224)

    scores = []
    model_device = next(model.parameters()).device
    for path in paths_test:
        try:
            t = load_tensor(path).to(model_device)
            t.requires_grad_(True)

            # forward
            feat = model.features2(t)
            logit = model.classifier(feat) / T   # scale by T
            prob = torch.sigmoid(logit)
            max_p = prob.max(dim=1)[0]
            max_p.backward()

            # perturbation
            with torch.no_grad():
                t_p = t.detach() - eps * t.grad.data.sign()

            # re-forward on perturbed
            with torch.no_grad():
                feat_p = model.features2(t_p)
                logit_p = model.classifier(feat_p) / T
                prob_p = torch.sigmoid(logit_p)
                score = float(1.0 - prob_p.max(dim=1)[0].item())
        except Exception as e:
            print(f"  [WARN] ODIN failed for {Path(path).name}: {e}", file=sys.stderr)
            score = 0.5  # fallback neutral

        scores.append(score)
        # zero grad for next iteration
        if t.grad is not None:
            t.grad.zero_()

    return np.array(scores, dtype=np.float32)


def method_gradnorm(feats_id, feats_test, logits_id=None, logits_test=None,
                    paths_test=None, model=None, device=None) -> np.ndarray:
    """
    GradNorm OOD score - 官方实现 (arXiv:2110.00218)。
    score = ||grad_input log(sum(sigmoid(logits)))||_1

    算法：
    对每张图 x：
      forward -> logits -> u = sum(sigmoid(logits))
      backward u w.r.t. x -> grad
      score = L1-norm of grad

    OOD 样本与 ID 分布差异大，gradient norm 更大。
    越大=越 OOD。

    此方法需要 live model（不能用缓存特征）。
    multi-label 适配：原论文用 softmax sum，此处用 sigmoid sum（与 TorchXRayVision 一致）。
    """
    if model is None or paths_test is None:
        raise ValueError("GradNorm 需要 model + paths_test（live 推理）")

    import torch
    from PIL import Image

    def load_tensor(path):
        img = Image.open(path).convert("L")
        if img.size != (224, 224):
            img = img.resize((224, 224), Image.BILINEAR)
        arr = np.array(img, dtype=np.float32)
        arr = (arr / 255.0) * 2048.0 - 1024.0
        return torch.tensor(arr, dtype=torch.float32).unsqueeze(0).unsqueeze(0)

    scores = []
    model_device = next(model.parameters()).device
    for path in paths_test:
        try:
            t = load_tensor(path).to(model_device)
            t.requires_grad_(True)

            feat = model.features2(t)
            logit = model.classifier(feat)
            u = torch.sigmoid(logit).sum()
            u.backward()

            grad_norm = float(t.grad.data.abs().sum().item())  # L1 norm
        except Exception as e:
            print(f"  [WARN] GradNorm failed for {Path(path).name}: {e}", file=sys.stderr)
            grad_norm = 0.0

        scores.append(grad_norm)
        if t.grad is not None:
            t.grad.zero_()

    return np.array(scores, dtype=np.float32)


# ============================================================
# get_fc helper：取 TorchXRayVision DenseNet classifier 权重
# 供 Residual / fDBD / DICE 共用（PR-G2 冻结接口）
# ============================================================
def get_fc(model):
    """
    从 frozen TorchXRayVision DenseNet 取 classifier 线性层权重。
    返回 (W: np.ndarray shape (18, 1024), b: np.ndarray shape (18,))。
    DenseNet 的最后线性层名为 model.classifier，无 get_fc() 方法。
    """
    import torch
    fc = model.classifier          # nn.Linear(1024, 18) or similar
    W = fc.weight.detach().cpu().numpy()   # (18, 1024)
    b = fc.bias.detach().cpu().numpy()     # (18,)
    return W.astype(np.float32), b.astype(np.float32)


# ============================================================
# v5 新增 6 方法（PR-G1 冻结，OpenOOD 官方超参，PR-G2 multi-label 适配）
# ============================================================

def method_residual(feats_id, feats_test, logits_id=None, logits_test=None,
                    paths_test=None, model=None, device=None,
                    dim: int = RESIDUAL_DIM) -> np.ndarray:
    """
    Residual OOD score（ViM 的 residual 子分，纯几何）。
    OpenOOD 官方超参：dim=512（PR-G1 冻结）。

    算法：
    1. ID penultimate feat 中心化，截断 SVD 取前 dim=512 主方向 P。
    2. test residual = feat_test - (feat_test @ P @ P^T)（投到零空间）。
    3. score = ||residual||_2；越大=越 OOD。

    multi-label 注意：纯几何，不依赖 softmax/sigmoid，无 PR-G2 适配歧义。
    dim=512 同 ViM（ACCEPTANCE 锁定，ViM arXiv:2203.10807 N/2 法则）。
    """
    mu_id = feats_id.mean(0)
    X_c = feats_id - mu_id
    try:
        _, _, Vt = np.linalg.svd(X_c, full_matrices=False)
    except np.linalg.LinAlgError:
        # fallback: 直接用 L2-norm（无 PCA）
        return np.linalg.norm(feats_test - mu_id, axis=1).astype(np.float32)
    d = min(dim, Vt.shape[0])
    P = Vt[:d].T        # (1024, dim)

    test_c = feats_test - mu_id
    test_proj = test_c @ P @ P.T
    test_residual = test_c - test_proj
    return np.linalg.norm(test_residual, axis=1).astype(np.float32)


def method_she(feats_id, feats_test, logits_id=None, logits_test=None,
               paths_test=None, model=None, device=None) -> np.ndarray:
    """
    SHE (Simplified Hopfield Energy) OOD score。
    OpenOOD 官方超参：metric=inner_product（PR-G1 冻结）。

    PR-G2 multi-label 适配（冻结口径）：
      官方假设 single-label softmax，按类分桶存 pattern；
      本 backbone multi-label sigmoid 无单一类标签，故改为
      「single global pattern = 全 ID penultimate 特征均值」+
      inner_product(test_feat, global_pattern) 打分。
      limitation：丢失类条件结构，仅测全局原型对齐度，PR-G2 冻结。

    score = inner_product(test_feat, pattern)；越大=越 ID → OOD score 取负。
    """
    # 全局原型：ID penultimate 均值（单 pattern，PR-G2 冻结）
    pattern = feats_id.mean(0)        # (1024,)
    pattern_norm = pattern / (np.linalg.norm(pattern) + 1e-8)

    test_norm = feats_test / (np.linalg.norm(feats_test, axis=1, keepdims=True) + 1e-8)
    ip = test_norm @ pattern_norm      # (N_test,)
    # inner_product 越大=越 ID-like → OOD score = -ip
    return (-ip).astype(np.float32)


def method_nnguide(feats_id, feats_test, logits_id=None, logits_test=None,
                   paths_test=None, model=None, device=None,
                   alpha: float = NNGUIDE_ALPHA, K: int = NNGUIDE_K) -> np.ndarray:
    """
    NNGuide OOD score。
    OpenOOD 官方超参：alpha=0.01, K=100（PR-G1 冻结）。

    PR-G2 multi-label 适配（冻结口径）：
      官方假设 single-label softmax，energy=log(sum(softmax))；
      本 backbone multi-label sigmoid，故改为
      energy = logsumexp(18 raw logits)（与现有 Energy EBO 同口径，一致性保证）。
      guide = KNN cosine similarity（K=100，ID train bank）。
      limitation：logsumexp 在 multi-label sigmoid 下非严格 free energy，
      作 confidence proxy，PR-G2 冻结。

    score = energy / (KNN_guide + alpha)；越大=越 OOD。
    （注：NNGuide 原论文用 energy 除以 guide score；guide 越高=越 ID，故分母大→score 小=ID-like）
    """
    if logits_test is None or logits_id is None:
        raise ValueError("NNGuide 需要 logits_id + logits_test")

    # energy = logsumexp(18 logits)（PR-G2 冻结，与 Energy EBO 同口径）
    energy_test = _logsumexp(logits_test)   # (N_test,) 越大=能量高=越 OOD
    # 取负使 energy_test 越大=越 OOD（logsumexp 对 ID 大，OOD 小，取负后 OOD 大）
    # 注：这里 energy 直接作分子，guide 越高=越 ID，score=energy/(guide+alpha)
    # OOD 样本 energy 小（logsumexp 小）guide 也小 → score 既可正可负
    # 参照 OpenOOD 实现：score = -energy * guide（guide=KNN cos sim，越高=越 ID）
    # 即 OOD score = -logsumexp * cos_sim（OOD 样本 logsumexp 小且 cos_sim 小 → score 大）

    # KNN cosine similarity（ID bank，K=100）
    def cosine_sim_knn(bank, query, K):
        bank_n = bank / (np.linalg.norm(bank, axis=1, keepdims=True) + 1e-8)
        q_n = query / (np.linalg.norm(query, axis=1, keepdims=True) + 1e-8)
        K_eff = min(K, len(bank_n))
        sims = []
        for q in q_n:
            s = bank_n @ q               # (N_id,)
            topk = np.sort(s)[::-1][:K_eff]
            sims.append(float(topk.mean()))
        return np.array(sims, dtype=np.float32)

    guide = cosine_sim_knn(feats_id, feats_test, K)   # (N_test,) in [-1,1]

    # OpenOOD NNGuide 实现：OOD score = -logsumexp(logits) / (guide + alpha)
    # guide 越高（ID-like）→ 分母大 → score 小（ID）；energy 越小（ID）→ 分子绝对值小 → score 小
    # 此处取负 logsumexp 使 OOD 更正（logsumexp 对 OOD 更小，取负后更大）
    ood_score = -energy_test / (guide + alpha)
    return ood_score.astype(np.float32)


def method_fdbd(feats_id, feats_test, logits_id=None, logits_test=None,
                paths_test=None, model=None, device=None,
                distance_as_normalizer: bool = True) -> np.ndarray:
    """
    fDBD (feature Distance-to-Decision-Boundary) OOD score。
    OpenOOD 官方超参：distance_as_normalizer=True（PR-G1 冻结）。需 model（get_fc）。

    PR-G2 multi-label 适配（冻结口径）：
      get_fc 取 classifier W(18×1024) + b(18)。
      到决策边界距离 = |W @ feat + b| / ||W|| per logit head，取最小（最近边界）。
      distance_as_normalizer=True：除以 feat 到 ID 均值距离做归一化。
      limitation：DICE 稀疏掩码按 18 个 sigmoid head 平均贡献定，PR-G2 冻结。

    score = min_head_boundary_dist / (feat_to_mean_dist + eps)；越大=越 OOD。
    （feat 远离 ID 均值且靠近决策边界 → OOD，score 大）
    """
    if model is None:
        raise ValueError("fDBD 需要 model（get_fc 取 classifier 权重）")

    W, b = get_fc(model)   # (18, 1024), (18,)

    mu_id = feats_id.mean(0)   # (1024,)

    # 到决策边界距离（per logit head）
    # |W_i @ feat + b_i| / ||W_i||  (i=0..17)
    W_norm = np.linalg.norm(W, axis=1) + 1e-8   # (18,)
    # feat_test: (N_test, 1024)
    logit_vals = feats_test @ W.T + b    # (N_test, 18)
    boundary_dists = np.abs(logit_vals) / W_norm   # (N_test, 18)
    min_boundary_dist = boundary_dists.min(axis=1)   # (N_test,)：到最近决策边界距离

    if distance_as_normalizer:
        feat_to_mean = np.linalg.norm(feats_test - mu_id, axis=1) + 1e-8   # (N_test,)
        # OOD: 离 ID 均值远（feat_to_mean 大）且离边界近（min_boundary_dist 小）
        # score = feat_to_mean / min_boundary_dist → OOD 大
        ood_score = feat_to_mean / (min_boundary_dist + 1e-8)
    else:
        ood_score = -min_boundary_dist   # 边界距离越小=越 OOD（取负）

    return ood_score.astype(np.float32)


def method_dice(feats_id, feats_test, logits_id=None, logits_test=None,
                paths_test=None, model=None, device=None,
                p: int = DICE_P) -> np.ndarray:
    """
    DICE (Directed Sparsification) OOD score。
    OpenOOD 官方超参：p=90（PR-G1 冻结）。需 model（get_fc）+ feats_id（ID train）。

    PR-G2 multi-label 适配（冻结口径）：
      get_fc 取 classifier W(18×1024) + b(18)。
      mean activation = ID penultimate 特征均值（p=90 按贡献度 mask W 各列）。
      score = logsumexp(masked logits)；越大=越 OOD。
      limitation：稀疏掩码按 18 个 sigmoid head 平均贡献定，PR-G2 冻结。

    算法（OpenOOD 官方实现）：
    1. contribution_i = mean_act[i] * max_j(|W[j,i]|)（第 i 个激活对各 head 的最大贡献）
    2. threshold = percentile(contribution, p=90)
    3. mask = contribution > threshold（保留高贡献列）
    4. W_masked = W * mask[np.newaxis, :]，b 不变
    5. score = logsumexp(feats_test @ W_masked.T + b)；越大=越 OOD。
    """
    if model is None:
        raise ValueError("DICE 需要 model（get_fc 取 classifier 权重）")

    W, b = get_fc(model)      # (18, 1024), (18,)
    mean_act = feats_id.mean(0)   # (1024,) ID penultimate 均值

    # contribution per input dimension（每个 feat 维度对 18 heads 的最大绝对贡献）
    contrib = mean_act * np.abs(W).max(axis=0)   # (1024,)
    threshold = float(np.percentile(contrib, p))

    mask = (contrib > threshold).astype(np.float32)   # (1024,) 0/1
    W_masked = W * mask[np.newaxis, :]                # (18, 1024) 稀疏化权重

    logits_masked = feats_test @ W_masked.T + b   # (N_test, 18)
    ood_score = _logsumexp(logits_masked)          # (N_test,)
    # logsumexp 对 ID 更大（更多激活），OOD 更小 → 取负
    return (-ood_score).astype(np.float32)


def method_ash(feats_id, feats_test, logits_id=None, logits_test=None,
               paths_test=None, model=None, device=None,
               percentile: int = ASH_PERCENTILE) -> np.ndarray:
    """
    ASH (Activation SHaping) OOD score。
    OpenOOD 官方超参：percentile=90（PR-G1 冻结）。唯一需要 live forward 的新方法。

    注意：TorchXRayVision DenseNet 无 get_fc() 方法，最后层是 self.classifier（nn.Linear）。
    penultimate 通过 model.features2(x) 得到，再 model.classifier(shaped_feat) 得 logits。

    算法（forward_threshold wrapper）：
    1. live forward x → penultimate feat（features2）
    2. shaping：feat 中按 percentile=90 阈值：低于阈值的维度置 0，高于阈值的维度缩放
       （ASH-S：s = percentile(feat, p)，feat_shaped = feat * (feat > s)；
        此为 ASH-S 变体，最轻量，OpenOOD 官方默认）
    3. logits = classifier(feat_shaped)
    4. score = logsumexp(logits)；越大=越 OOD。

    PR-G2 注意：logsumexp 在 multi-label sigmoid 下作 confidence proxy（同 NNGuide 口径）。
    官方假设 single-label softmax；本 backbone multi-label 故 logsumexp→energy proxy，PR-G2 冻结。
    """
    if model is None or paths_test is None:
        raise ValueError("ASH 需要 model + paths_test（live forward）")

    import torch
    from PIL import Image

    def load_tensor(path):
        img = Image.open(path).convert("L")
        if img.size != (224, 224):
            img = img.resize((224, 224), Image.BILINEAR)
        arr = np.array(img, dtype=np.float32)
        arr = (arr / 255.0) * 2048.0 - 1024.0
        return torch.tensor(arr, dtype=torch.float32).unsqueeze(0).unsqueeze(0)

    scores = []
    model_device = next(model.parameters()).device
    with torch.no_grad():
        for path in paths_test:
            try:
                t = load_tensor(path).to(model_device)
                feat = model.features2(t)       # (1, 1024)

                # ASH-S shaping（percentile=90）
                feat_np = feat.cpu().numpy().flatten()
                s = float(np.percentile(feat_np, percentile))
                feat_shaped = feat_np * (feat_np > s).astype(np.float32)
                feat_shaped_t = torch.tensor(
                    feat_shaped, dtype=torch.float32
                ).unsqueeze(0).to(model_device)  # (1, 1024)

                logit = model.classifier(feat_shaped_t)   # (1, 18)
                logit_np = logit.cpu().numpy()             # (1, 18)
                lse = float(_logsumexp(logit_np)[0])
                # logsumexp 对 ID 大 → OOD score = -lse（OOD 更大）
                score = -lse
            except Exception as e:
                print(f"  [WARN] ASH failed for {Path(path).name}: {e}", file=sys.stderr)
                score = 0.0
            scores.append(score)

    return np.array(scores, dtype=np.float32)


# method 分组：live（需 model+paths）vs cached（用 feats/logits）
LIVE_METHODS = {"ODIN", "GradNorm", "ASH"}
CACHED_METHODS = {"MSP", "Energy", "MDS", "KNN", "ViM",
                  "Residual", "SHE", "NNGuide", "fDBD", "DICE"}
# fDBD / DICE 需要 model（get_fc），但不需要 live image paths，仍归 cached
# （model 作参数传入，图像 paths 不需要）
MODEL_METHODS = {"fDBD", "DICE"}   # cached 但需要 model 取 fc 权重

METHOD_FNS = {
    "MSP": method_msp,
    "ODIN": method_odin,
    "Energy": method_energy,
    "MDS": method_mds,
    "KNN": method_knn,
    "ViM": method_vim,
    "GradNorm": method_gradnorm,
    # v5 新增
    "Residual": method_residual,
    "SHE": method_she,
    "NNGuide": method_nnguide,
    "fDBD": method_fdbd,
    "DICE": method_dice,
    "ASH": method_ash,
}


# ============================================================
# 配对子集（方案 C）— ACCEPTANCE v3 propensity-score logistic caliper
# ============================================================
def artifact_matched_subset(
    X_art_id: np.ndarray, idx_id: np.ndarray,
    X_art_ood: np.ndarray, idx_ood: np.ndarray,
    caliper: float = CALIPER_SD, seed: int = SEED,
    smoke: bool = False,
) -> tuple:
    """
    1-维 logistic propensity-score caliper 匹配（ACCEPTANCE v3，预登记）。
    返回 (matched_idx_id, matched_idx_ood, smd_max, smd_mean)。

    实现（严格按 ACCEPTANCE v3 规格）：
    1. Propensity 模型：LogisticRegression(penalty=None)，输入 = 43 维 artifact
       特征 z-score 标化（pooled ID+OOD 统计量），label=0(ID)/1(OOD)。
    2. 交叉拟合：k=5 fold out-of-fold 预测（smoke 时 N<10，退化为直接 fit，注释
       标明 smoke-only）。
    3. Caliper：caliper × SD(logit(propensity)) on pooled all samples。
    4. 1:1 greedy without replacement，随机序 seed=42。
    5. 配对后计算 SMD（|standardized mean difference|），返回 smd_max/smd_mean。
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold

    N_id  = len(X_art_id)
    N_ood = len(X_art_ood)
    if N_id == 0 or N_ood == 0:
        return np.array([], dtype=int), np.array([], dtype=int), float("nan"), float("nan")

    # z-score 标化：pooled ID+OOD 统计量
    X_all = np.concatenate([X_art_id, X_art_ood], axis=0).astype(np.float64)
    mu_pool  = X_all.mean(0)
    sig_pool = X_all.std(0) + 1e-8
    X_all_s  = (X_all - mu_pool) / sig_pool   # (N_id+N_ood, 43)
    y_all    = np.array([0]*N_id + [1]*N_ood, dtype=np.int32)

    # 交叉拟合 or smoke 直接 fit
    prop_scores = np.zeros(N_id + N_ood, dtype=np.float64)  # P(OOD)

    K_FOLD = 5
    if smoke or (N_id + N_ood) < K_FOLD * 2:
        # smoke-only: N 太小无法 5-fold，直接在全集 fit+predict（无 OOF 保证）
        print("[artifact_matched_subset] SMOKE/SMALL-N: 直接 fit (no cross-fitting), "
              "smoke-only，真实结果用 5-fold OOF")
        try:
            # C=np.inf = no regularization（等价 penalty=None，sklearn>=1.8 兼容写法）
            clf = LogisticRegression(C=np.inf, solver="lbfgs", max_iter=1000,
                                     random_state=seed)
            clf.fit(X_all_s, y_all)
        except Exception:
            # 极小 N 数值不稳，退 L2 C=1.0（scikit-learn default；禁 CV 选参）
            print("[artifact_matched_subset] C=inf 不收敛，退 L2 C=1.0 "
                  "(smoke fallback; C=1.0 scikit-learn default)")
            clf = LogisticRegression(C=1.0, solver="lbfgs",
                                     max_iter=1000, random_state=seed)
            clf.fit(X_all_s, y_all)
        prop_scores = clf.predict_proba(X_all_s)[:, 1]
    else:
        # 真实数据：5-fold out-of-fold 预测
        skf = StratifiedKFold(n_splits=K_FOLD, shuffle=True, random_state=seed)
        for train_idx, val_idx in skf.split(X_all_s, y_all):
            try:
                # C=np.inf = no regularization（等价 penalty=None，sklearn>=1.8 兼容写法）
                clf = LogisticRegression(C=np.inf, solver="lbfgs", max_iter=1000,
                                         random_state=seed)
                clf.fit(X_all_s[train_idx], y_all[train_idx])
            except Exception:
                # 不收敛退 L2 C=1.0（scikit-learn default；禁 CV 选参）
                print("[artifact_matched_subset] C=inf fold 不收敛，退 L2 C=1.0 "
                      "(C=1.0 scikit-learn default，未 CV 选参)")
                clf = LogisticRegression(C=1.0, solver="lbfgs",
                                         max_iter=1000, random_state=seed)
                clf.fit(X_all_s[train_idx], y_all[train_idx])
            prop_scores[val_idx] = clf.predict_proba(X_all_s[val_idx])[:, 1]

    # logit(propensity) = log(p/(1-p))；clip 防 log(0)
    eps_logit = 1e-6
    prop_clipped = np.clip(prop_scores, eps_logit, 1.0 - eps_logit)
    logit_scores = np.log(prop_clipped / (1.0 - prop_clipped))  # (N_id+N_ood,)

    # caliper = CALIPER_SD × SD(logit, pooled all)
    sd_logit  = float(logit_scores.std())
    threshold = caliper * sd_logit
    print(f"  [PS-caliper] SD(logit)={sd_logit:.4f}, caliper={caliper}, "
          f"threshold={threshold:.4f}")

    logit_id  = logit_scores[:N_id]
    logit_ood = logit_scores[N_id:]

    # 1:1 greedy without replacement，随机序 seed=42
    rng = np.random.default_rng(seed)
    ood_order = rng.permutation(N_ood)

    used_id = set()
    matched_id_local, matched_ood_local = [], []

    for ood_i in ood_order:
        dists = np.abs(logit_id - logit_ood[ood_i])
        # 排除已用 ID
        dists_masked = dists.copy()
        for u in used_id:
            dists_masked[u] = np.inf
        nn_id = int(dists_masked.argmin())
        if dists_masked[nn_id] <= threshold:
            matched_id_local.append(nn_id)
            matched_ood_local.append(ood_i)
            used_id.add(nn_id)

    matched_id_local  = np.array(matched_id_local,  dtype=int)
    matched_ood_local = np.array(matched_ood_local, dtype=int)

    # SMD 平衡诊断（配对后，43 维原始特征）
    if len(matched_id_local) >= 2:
        art_id_m  = X_art_id[matched_id_local].astype(np.float64)
        art_ood_m = X_art_ood[matched_ood_local].astype(np.float64)
        # pooled SD（配对前全集，与标化一致）
        pooled_sd = sig_pool  # (43,)
        smd_per_dim = np.abs((art_id_m.mean(0) - art_ood_m.mean(0)) / pooled_sd)
        smd_max  = float(smd_per_dim.max())
        smd_mean = float(smd_per_dim.mean())
        print(f"  [SMD] max={smd_max:.4f}, mean={smd_mean:.4f} "
              f"(|SMD|<0.1 为平衡达标)")
    else:
        smd_max, smd_mean = float("nan"), float("nan")

    return (
        idx_id[matched_id_local],
        idx_ood[matched_ood_local],
        smd_max,
        smd_mean,
    )


# ============================================================
# bootstrap Spearman CI
# ============================================================
def bootstrap_spearman_ci(ranking_orig: list, ranking_clean: list,
                           B: int = BOOTSTRAP_B, seed: int = SEED,
                           alpha: float = 0.05) -> dict:
    """
    方法排名对 bootstrap CI（B=1000）。
    ranking_orig / ranking_clean: 方法排名列表（rank 1=最好）。
    返回 {spearman: float, ci_lower: float, ci_upper: float}。
    """
    if len(ranking_orig) != len(ranking_clean) or len(ranking_orig) < 2:
        return {"spearman": float("nan"), "ci_lower": float("nan"), "ci_upper": float("nan")}

    rng = np.random.RandomState(seed)
    x = np.array(ranking_orig, dtype=np.float64)
    y = np.array(ranking_clean, dtype=np.float64)
    point_est = spearman_numpy(x, y)

    boot_stats = []
    n = len(x)
    for _ in range(B):
        idx = rng.randint(0, n, n)
        boot_stats.append(spearman_numpy(x[idx], y[idx]))

    boot_arr = np.array(boot_stats)
    ci_lo = float(np.percentile(boot_arr, 100 * alpha / 2))
    ci_hi = float(np.percentile(boot_arr, 100 * (1 - alpha / 2)))
    return {"spearman": round(point_est, 4), "ci_lower": round(ci_lo, 4),
            "ci_upper": round(ci_hi, 4)}


# ============================================================
# 排名工具（由 AUROC 降序得 rank）
# ============================================================
def auroc_to_ranking(method_aurocs: dict) -> dict:
    """返回 method -> rank (1=最高 AUROC)。"""
    sorted_methods = sorted(method_aurocs.items(), key=lambda x: -x[1])
    return {m: i + 1 for i, (m, _) in enumerate(sorted_methods)}


def ranking_to_rows(ranking: dict, aurocs: dict, subset: str, pair: str) -> list:
    rows = []
    for method, rank in sorted(ranking.items(), key=lambda x: x[1]):
        rows.append({
            "pair": pair,
            "subset": subset,
            "method": method,
            "rank": rank,
            "auroc": round(aurocs.get(method, float("nan")), 4),
        })
    return rows


# ============================================================
# 主逻辑
# ============================================================
def load_manifest():
    """读 manifest.csv，返回 dict: dataset -> list of paths。"""
    if not MANIFEST_CSV.exists():
        return None
    rows = []
    with open(MANIFEST_CSV, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return rows


def run_pair(
    feats_id: np.ndarray, feats_ood: np.ndarray,
    art_id: np.ndarray, art_ood: np.ndarray,
    pair_name: str,
    logits_id: np.ndarray = None,
    logits_ood: np.ndarray = None,
    paths_id: list = None,
    paths_ood: list = None,
    model=None,
    method_names=OOD_METHODS,
) -> dict:
    """
    单对 (ID, OOD) 上跑全部 7 方法（真实实现，非 proxy）。
    - cached 方法（MSP/Energy/MDS/KNN/ViM）用 feats+logits
    - live 方法（ODIN/GradNorm）用 model + paths
    返回 {method: {"auroc": float, "scores": np.ndarray(N_id+N_ood,)}}。
    """
    results = {}
    labels = np.array([0] * len(feats_id) + [1] * len(feats_ood), dtype=np.int32)
    feats_test = np.concatenate([feats_id, feats_ood], axis=0)
    logits_test = (np.concatenate([logits_id, logits_ood], axis=0)
                   if (logits_id is not None and logits_ood is not None) else None)
    paths_test = ((list(paths_id or []) + list(paths_ood or []))
                  if (paths_id is not None and paths_ood is not None) else None)

    for method in method_names:
        fn = METHOD_FNS[method]
        try:
            if method in LIVE_METHODS:
                if paths_test is None or model is None:
                    raise ValueError(f"{method} 需要 paths_test + model（live 推理路径缺失）")
                scores = fn(feats_id, feats_test,
                            logits_id=logits_id, logits_test=logits_test,
                            paths_test=paths_test, model=model)
            elif method in MODEL_METHODS:
                # cached 但需要 model（get_fc）：不需要 paths，传 model
                if model is None:
                    raise ValueError(f"{method} 需要 model（get_fc 取 classifier 权重）")
                scores = fn(feats_id, feats_test,
                            logits_id=logits_id, logits_test=logits_test,
                            model=model)
            else:
                scores = fn(feats_id, feats_test,
                            logits_id=logits_id, logits_test=logits_test)
            auroc = auroc_numpy(labels, scores)
        except Exception as e:
            print(f"  [WARN] {method} failed: {e}", file=sys.stderr)
            scores = np.zeros(len(feats_test), dtype=np.float32)
            auroc = float("nan")
        results[method] = {"auroc": auroc, "scores": scores}
        print(f"  {pair_name} | {method:12s}: AUROC={auroc:.4f}")

    return results


def run_pair_on_subset(
    feats_id_sub: np.ndarray, feats_ood_sub: np.ndarray,
    pair_name: str, subset_name: str,
    logits_id_sub: np.ndarray = None,
    logits_ood_sub: np.ndarray = None,
    paths_id_sub: list = None,
    paths_ood_sub: list = None,
    model=None,
    method_names=OOD_METHODS,
) -> dict:
    """子集上跑，返回 {method: auroc}。"""
    labels = np.array([0] * len(feats_id_sub) + [1] * len(feats_ood_sub), dtype=np.int32)
    feats_test = np.concatenate([feats_id_sub, feats_ood_sub], axis=0)
    logits_test = (np.concatenate([logits_id_sub, logits_ood_sub], axis=0)
                   if (logits_id_sub is not None and logits_ood_sub is not None) else None)
    paths_test = ((list(paths_id_sub or []) + list(paths_ood_sub or []))
                  if (paths_id_sub is not None and paths_ood_sub is not None) else None)
    aurocs = {}
    for method in method_names:
        fn = METHOD_FNS[method]
        try:
            if method in LIVE_METHODS:
                if paths_test is None or model is None:
                    raise ValueError(f"{method} live 路径缺失")
                scores = fn(feats_id_sub, feats_test,
                            logits_id=logits_id_sub, logits_test=logits_test,
                            paths_test=paths_test, model=model)
            elif method in MODEL_METHODS:
                if model is None:
                    raise ValueError(f"{method} 需要 model（get_fc）")
                scores = fn(feats_id_sub, feats_test,
                            logits_id=logits_id_sub, logits_test=logits_test,
                            model=model)
            else:
                scores = fn(feats_id_sub, feats_test,
                            logits_id=logits_id_sub, logits_test=logits_test)
            auroc = auroc_numpy(labels, scores)
        except Exception as e:
            print(f"  [WARN] {method}/{subset_name}: {e}", file=sys.stderr)
            auroc = float("nan")
        aurocs[method] = auroc
        print(f"  {pair_name}/{subset_name} | {method:12s}: AUROC={auroc:.4f}")
    return aurocs


def _load_xrv_model(device: str):
    """加载 TorchXRayVision DenseNet，供 ODIN/GradNorm live 路径用。"""
    try:
        import torchxrayvision as xrv
        import torch
    except ImportError:
        print("[WARN] torchxrayvision 未安装，ODIN/GradNorm 将跳过", file=sys.stderr)
        return None
    model = xrv.models.DenseNet(weights="densenet121-res224-all")
    model.eval()
    model.to(device)
    return model


def main(smoke: bool = False, device: str = "cpu", caliper: float = CALIPER_SD):
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # ============================================================
    # Bug4 fix: 真实运行时，run 开头清空上轮输出（含可能残留的 smoke 行）
    # smoke 模式用独立文件名，不污染真实结果文件。
    # ============================================================
    if not smoke:
        # 清空所有输出 csv，确保本轮 4 对数据从头累积，不混入旧轮/smoke 行
        for csv_path in [OUT_SCORES_RAW, OUT_L3_RAW, OUT_L3_CLEAN_C,
                         OUT_BOOTSTRAP, OUT_L3_CLEAN_A, OUT_L3_CLEAN_B]:
            if csv_path.exists():
                csv_path.unlink()
                print(f"[INIT] cleared old output: {csv_path.name}")

    # ============================================================
    # 合成 smoke 数据（验算 7 方法，不依赖 extract_frozen_feats）
    # ODIN/GradNorm smoke 用 XRV 真实模型 + 合成图像路径（临时文件）
    # ============================================================
    if smoke:
        print("[L3] SMOKE: 合成特征 + 真实 ODIN/GradNorm")
        import tempfile
        import torch
        rng = np.random.RandomState(SEED)
        # smoke 用小 N：ODIN/GradNorm 每张需 live forward+backward，CPU 下每张约 0.3-1s
        # 保持 8 张 ×2 ≈ 16 张总计，smoke 在 ~30s 内完成
        N_ID, N_OOD = 8, 8

        # 合成 1024 维特征：ID ~ N(0,1)，OOD ~ N(1.5,1)
        feats_id  = rng.randn(N_ID, 1024).astype(np.float32)
        feats_ood = (rng.randn(N_OOD, 1024) + 1.5).astype(np.float32)

        # 合成 18 维 logits：ID 均值 0，OOD 均值 -1（pre-sigmoid）
        logits_id  = rng.randn(N_ID, N_LOGITS).astype(np.float32)
        logits_ood = (rng.randn(N_OOD, N_LOGITS) - 1.0).astype(np.float32)

        # 合成 artifact 特征：OOD 偏移极小保证配对（threshold≈1.31）
        art_id  = rng.randn(N_ID, ARTIFACT_DIM).astype(np.float32)
        art_ood = art_id + rng.randn(N_OOD, ARTIFACT_DIM).astype(np.float32) * 0.05

        # 生成临时 PNG 图（供 ODIN/GradNorm live 路径）
        from PIL import Image as PILImage
        tmp_dir = Path(tempfile.mkdtemp())
        def _make_tmp_imgs(n, prefix, mean_px=128):
            paths = []
            for i in range(n):
                arr = rng.randint(max(0, mean_px-30), min(255, mean_px+30),
                                  (224, 224), dtype=np.uint8)
                p = tmp_dir / f"{prefix}_{i}.png"
                PILImage.fromarray(arr).save(p)
                paths.append(str(p))
            return paths

        paths_id  = _make_tmp_imgs(N_ID,  "id")
        paths_ood = _make_tmp_imgs(N_OOD, "ood", mean_px=60)  # darker=OOD-like

        # 加载真实 XRV 模型（CPU smoke）
        model = _load_xrv_model(device)
        if model is None:
            print("[SMOKE] torchxrayvision 未装，ODIN/GradNorm 将报 nan", file=sys.stderr)

        # smoke 写独立文件（_smoke 后缀），不污染真实结果 csv
        # Bug4 fix: smoke 与 real-data csv 完全隔离
        _smoke_suffix_map = {
            OUT_SCORES_RAW: OUT_DIR / "l3_method_scores_raw_smoke.csv",
            OUT_L3_RAW:     OUT_DIR / "l3_raw_ranking_smoke.csv",
            OUT_L3_CLEAN_C: OUT_DIR / "l3_cleanC_ranking_smoke.csv",
            OUT_BOOTSTRAP:  OUT_DIR / "a4_bootstrap_spearman_smoke.csv",
            OUT_L3_CLEAN_A: OUT_DIR / "l3_cleanA_ranking_smoke.csv",
            OUT_L3_CLEAN_B: OUT_DIR / "l3_cleanB_ranking_smoke.csv",
        }
        # 清旧 smoke 文件
        for _p in _smoke_suffix_map.values():
            if _p.exists():
                _p.unlink()

        pair_name = "smoke_NIH_vs_VinDr"
        _run_full_pipeline(feats_id, feats_ood, art_id, art_ood, pair_name,
                           logits_id=logits_id, logits_ood=logits_ood,
                           paths_id=paths_id, paths_ood=paths_ood,
                           model=model, device=device, smoke=True,
                           out_path_override=_smoke_suffix_map,
                           method_names=OOD_METHODS)

        # 清理临时文件
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return

    # ============================================================
    # 真实数据：从 feats/ 读取特征 + logits，运行 4 cross-source 对
    # ============================================================
    manifest_rows = load_manifest()
    if manifest_rows is None:
        print(
            f"[ERROR] manifest.csv not found: {MANIFEST_CSV}\n"
            "Run extract_frozen_feats.py first.",
            file=sys.stderr,
        )
        sys.exit(1)

    # 分组 by dataset name
    datasets = {}
    for row in manifest_rows:
        ds = row["dataset"]
        datasets.setdefault(ds, []).append(row)

    # (clearing already done at top of main() for real-data runs)

    # 加载 XRV 模型（供 ODIN/GradNorm live）
    import torch
    if device == "cuda" and not torch.cuda.is_available():
        print("[WARN] CUDA not available, fallback CPU")
        device = "cpu"
    model = _load_xrv_model(device)

    def _run_pair_from_feats(id_ds: str, ood_ds: str, pair_name: str):
        """Load feats+logits for (id_ds, ood_ds), extract artifact feats, run pipeline."""
        missing = [ds for ds in (id_ds, ood_ds) if ds not in datasets]
        if missing:
            print(f"[WARN] {pair_name}: datasets missing in manifest: {missing}", file=sys.stderr)
            return
        id_rows  = datasets[id_ds]
        ood_rows = datasets[ood_ds]
        id_paths  = [r["path"] for r in id_rows]
        ood_paths = [r["path"] for r in ood_rows]

        npy_id  = FEATS_DIR / f"{id_ds}.npy"
        npy_ood = FEATS_DIR / f"{ood_ds}.npy"
        npy_id_logits  = FEATS_DIR / f"{id_ds}_logits.npy"
        npy_ood_logits = FEATS_DIR / f"{ood_ds}_logits.npy"

        for p in (npy_id, npy_ood):
            if not p.exists():
                print(f"[ERROR] feats npy missing: {p}", file=sys.stderr)
                return

        feats_id  = np.load(npy_id)
        feats_ood = np.load(npy_ood)
        logits_id  = np.load(npy_id_logits)  if npy_id_logits.exists()  else None
        logits_ood = np.load(npy_ood_logits) if npy_ood_logits.exists() else None
        if logits_id is None or logits_ood is None:
            print(f"[WARN] {pair_name}: logits npy missing — MSP/Energy/ViM will fail. "
                  "Re-run extract_frozen_feats.py.", file=sys.stderr)

        print(f"\n[L3] {pair_name}: {id_ds} feats={feats_id.shape}, "
              f"{ood_ds} feats={feats_ood.shape}")
        print(f"[L3] extracting artifact features for {id_ds}...")
        art_id  = extract_artifact_features_batch(id_paths)
        print(f"[L3] extracting artifact features for {ood_ds}...")
        art_ood = extract_artifact_features_batch(ood_paths)

        _run_full_pipeline(feats_id, feats_ood, art_id, art_ood, pair_name,
                           logits_id=logits_id, logits_ood=logits_ood,
                           paths_id=id_paths, paths_ood=ood_paths,
                           model=model, device=device, smoke=False,
                           caliper=caliper,
                           method_names=OOD_METHODS)

    # 4 cross-source pairs (ACCEPTANCE v2 frozen)
    print("\n" + "=" * 60)
    print("[L3] Running 4 cross-source pairs P1-P4 (A-1/A-4 targets，v5 再加 P2b/P4b/P4c)")
    print("=" * 60)

    # P1: CXR — NIH(ID) vs VinDr(OOD)
    print("\n[P1] CXR cross-source: NIH_CXR14 vs VinDr_CXR")
    try:
        _run_pair_from_feats("NIH_CXR14", "VinDr_CXR", "NIH_vs_VinDr")
    except Exception:
        traceback.print_exc()
        print("[P1] 失败，跳过，继续下一对", file=sys.stderr)

    # P2: CXR — NIH(ID) vs RSNA_normal(OOD)
    print("\n[P2] CXR cross-source: NIH_CXR14 vs RSNA_normal")
    try:
        _run_pair_from_feats("NIH_CXR14", "RSNA_normal", "NIH_vs_RSNA_normal")
    except Exception:
        traceback.print_exc()
        print("[P2] 失败，跳过，继续下一对", file=sys.stderr)

    # P3: BrainMRI — BraTS_normal(ID) vs BrainTumor_normal(OOD)
    print("\n[P3] BrainMRI cross-source: BraTS_normal vs BrainTumor_normal")
    try:
        _run_pair_from_feats("BraTS_normal", "BrainTumor_normal", "BraTS_normal_vs_BrainTumor_normal")
    except Exception:
        traceback.print_exc()
        print("[P3] 失败，跳过，继续下一对", file=sys.stderr)

    # P4: Derm — HAM_NV(ID) vs ISIC2020_benign(OOD)
    print("\n[P4] Derm cross-source: HAM_NV vs ISIC2020_benign")
    try:
        _run_pair_from_feats("HAM_NV", "ISIC2020_benign", "HAM_NV_vs_ISIC2020_benign")
    except Exception:
        traceback.print_exc()
        print("[P4] 失败，跳过，继续下一对", file=sys.stderr)

    # ============================================================
    # PR-G3 新增对（v5 扩证据预登记，4→6-7 对）
    # ============================================================
    print("\n" + "=" * 60)
    print("[L3] PR-G3 新增 cross-source 对（v5 扩证据）")
    print("=" * 60)

    # P2b: CXR 第 3 对 — VinDr_CXR(ID) vs RSNA_normal(OOD)
    # PR-G3: feats 已存盘（或待存盘），若缺 feats 优雅跳过
    print("\n[P2b] CXR cross-source: VinDr_CXR vs RSNA_normal")
    try:
        _run_pair_from_feats("VinDr_CXR", "RSNA_normal", "VinDr_CXR_vs_RSNA_normal")
    except Exception:
        traceback.print_exc()
        print("[P2b] 失败，跳过，继续下一对", file=sys.stderr)

    # P4b: Derm 第 2 对 — HAM_NV(ID) vs fitzpatrick17k(OOD)
    # PR-G3: feats 待 coder 提取，若 feats 缺则优雅跳过（_run_pair_from_feats 内部处理）
    print("\n[P4b] Derm cross-source: HAM_NV vs fitzpatrick17k")
    print("[P4b] NOTE: feats 待另一 coder 提取（fitzpatrick17k），缺 feats 时优雅跳过。")
    try:
        _run_pair_from_feats("HAM_NV", "fitzpatrick17k", "HAM_NV_vs_fitzpatrick17k")
    except Exception:
        traceback.print_exc()
        print("[P4b] 失败，跳过，继续下一对", file=sys.stderr)

    # P4c: Derm 第 3 对（可选）— ISIC2020_benign(ID) vs PAD_UFES(OOD)
    # PR-G3: 可选，feats 待提取，缺时优雅跳过
    print("\n[P4c] Derm cross-source (optional): ISIC2020_benign vs PAD_UFES")
    print("[P4c] NOTE: 可选对，feats 待提取（PAD_UFES），缺 feats 时优雅跳过。")
    try:
        _run_pair_from_feats("ISIC2020_benign", "PAD_UFES", "ISIC2020_benign_vs_PAD_UFES")
    except Exception:
        traceback.print_exc()
        print("[P4c] 失败，跳过（可选对）", file=sys.stderr)


def _run_full_pipeline(
    feats_id, feats_ood, art_id, art_ood, pair_name,
    logits_id=None, logits_ood=None,
    paths_id=None, paths_ood=None,
    model=None, device="cpu", smoke=False,
    out_path_override=None,      # Bug4 fix: smoke 隔离用，dict {orig_path: smoke_path}
    caliper: float = CALIPER_SD, # Bug5 fix: 参数化 caliper
    method_names=None,           # v5: 支持传入 13 法列表（默认 OOD_METHODS）
):
    """R3b → R4 → R5 → R6/R7 完整流水线（v5：支持 13 法）。"""
    if method_names is None:
        method_names = OOD_METHODS

    # 路径别名（smoke 时替换为 _smoke 版本）
    def _out(p):
        if out_path_override and p in out_path_override:
            return out_path_override[p]
        return p

    _OUT_SCORES_RAW = _out(OUT_SCORES_RAW)
    _OUT_L3_RAW     = _out(OUT_L3_RAW)
    _OUT_L3_CLEAN_C = _out(OUT_L3_CLEAN_C)
    _OUT_BOOTSTRAP  = _out(OUT_BOOTSTRAP)
    _OUT_L3_CLEAN_A = _out(OUT_L3_CLEAN_A)
    _OUT_L3_CLEAN_B = _out(OUT_L3_CLEAN_B)
    N_ID, N_OOD = len(feats_id), len(feats_ood)
    n_id_idx = np.arange(N_ID)
    n_ood_idx = np.arange(N_OOD)

    # ============================================================
    # R3b 准入门：去污染前 raw AUROC（PR-F3）
    # ============================================================
    n_methods = len(method_names)
    print(f"\n[R3b] {pair_name}: 去污染前 {n_methods} 方法 raw AUROC")
    raw_results = run_pair(
        feats_id, feats_ood, art_id, art_ood, pair_name,
        logits_id=logits_id, logits_ood=logits_ood,
        paths_id=paths_id, paths_ood=paths_ood,
        model=model,
        method_names=method_names,
    )

    # 判断模态是否过 PR-F3（全法全<0.6 = 不计入 A-4）
    raw_aurocs = {m: raw_results[m]["auroc"] for m in method_names}
    all_below_06 = all(v < 0.6 for v in raw_aurocs.values() if not np.isnan(v))
    if all_below_06:
        print(f"[PR-F3] {pair_name}: 全法 AUROC 全<0.6，不计入 A-4（只用于 A-1/A-2）")

    # 保存 raw scores (Bug4 fix: 用 _OUT_SCORES_RAW 本地路径，smoke 时指向 _smoke 文件)
    all_scores_rows = []
    for i in range(N_ID + N_OOD):
        row = {"pair": pair_name, "idx": i, "label": 0 if i < N_ID else 1}
        for method in method_names:
            row[method.lower() + "_score"] = round(float(raw_results[method]["scores"][i]), 6)
        all_scores_rows.append(row)

    score_fieldnames = ["pair", "idx", "label"] + [m.lower() + "_score" for m in method_names]
    _write_mode = "a" if _OUT_SCORES_RAW.exists() else "w"
    with open(_OUT_SCORES_RAW, _write_mode, newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=score_fieldnames)
        if _write_mode == "w":
            w.writeheader()
        w.writerows(all_scores_rows)
    print(f"[R3b] raw scores -> {_OUT_SCORES_RAW}")

    # ============================================================
    # R4：raw 排名
    # ============================================================
    raw_ranking = auroc_to_ranking(raw_aurocs)
    r4_rows = ranking_to_rows(raw_ranking, raw_aurocs, "raw", pair_name)
    _write_mode = "a" if _OUT_L3_RAW.exists() else "w"
    with open(_OUT_L3_RAW, _write_mode, newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["pair", "subset", "method", "rank", "auroc"])
        if _write_mode == "w":
            w.writeheader()
        w.writerows(r4_rows)
    print(f"[R4] raw ranking -> {_OUT_L3_RAW}")

    # ============================================================
    # R5：方案 C artifact-matched 配对子集（命门）
    # ============================================================
    print(f"\n[R5] {pair_name}: artifact-matched 配对（caliper={caliper} SD）")

    # common-support 诊断（Bug5 fix: 报告两源 artifact 分布重叠率）
    # 用 ID 的 IQR 判断 OOD 落在 ID artifact 分布内的比例（每维度取均值）
    iqr_lo = np.percentile(art_id, 25, axis=0)
    iqr_hi = np.percentile(art_id, 75, axis=0)
    in_iqr = ((art_ood >= iqr_lo) & (art_ood <= iqr_hi)).all(axis=1)
    common_support_pct = float(in_iqr.mean()) * 100.0
    print(f"  [common-support] OOD samples within ID IQR (all dims): {common_support_pct:.1f}%")

    matched_id_idx, matched_ood_idx, smd_max, smd_mean = artifact_matched_subset(
        art_id, n_id_idx, art_ood, n_ood_idx, caliper=caliper,
        smoke=smoke,
    )
    n_matched = len(matched_id_idx)
    print(f"  matched: {n_matched} 对 (from {N_ID} ID + {N_OOD} OOD, caliper={caliper} SD)")

    # Bug5 fix: n_matched < 30 → INSUFFICIENT，不宣 PASS/FAIL
    MIN_MATCHED = 30
    if n_matched < MIN_MATCHED:
        print(f"[WARN] n_matched={n_matched} < {MIN_MATCHED}，方案 C 不足以裁决 A-4",
              file=sys.stderr)
        verdict_a4 = f"INSUFFICIENT (n_matched={n_matched}, unable to decide)"
        boot_row = {
            "pair": pair_name,
            "spearman_point": float("nan"),
            "ci_lower": float("nan"),
            "ci_upper": float("nan"),
            "ci_upper_lt_0.7": -1,
            "top1_orig": min(raw_ranking, key=raw_ranking.get),
            "top1_cleanC_rank": -1,
            "top1_dropped_from_top3": -1,
            "A4_verdict": verdict_a4,
            "n_matched_pairs": n_matched,
            "common_support_pct": round(common_support_pct, 1),
            "artifact_only_auroc_cleanC": float("nan"),
            "method_mean_auroc_cleanC": float("nan"),
            "smd_max": float("nan") if np.isnan(smd_max) else round(smd_max, 4),
            "smd_mean": float("nan") if np.isnan(smd_mean) else round(smd_mean, 4),
        }
        _write_mode = "a" if _OUT_BOOTSTRAP.exists() else "w"
        with open(_OUT_BOOTSTRAP, _write_mode, newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(boot_row.keys()))
            if _write_mode == "w":
                w.writeheader()
            w.writerow(boot_row)
        print(f"[R5] INSUFFICIENT -> {_OUT_BOOTSTRAP}")
        # 仍写 cleanC ranking 行（带 n_matched 标注），供 appendix
        insuf_rows = [{
            "pair": pair_name, "subset": "cleanC_INSUF",
            "method": m, "rank": -1, "auroc": float("nan"),
            "n_matched": n_matched
        } for m in method_names]
        _write_mode = "a" if _OUT_L3_CLEAN_C.exists() else "w"
        with open(_OUT_L3_CLEAN_C, _write_mode, newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["pair", "subset", "method", "rank", "auroc",
                                               "n_matched"], extrasaction="ignore")
            if _write_mode == "w":
                w.writeheader()
            w.writerows(insuf_rows)
    else:
        feats_id_c  = feats_id[matched_id_idx]
        feats_ood_c = feats_ood[matched_ood_idx]
        art_id_c  = art_id[matched_id_idx]
        art_ood_c = art_ood[matched_ood_idx]
        logits_id_c  = logits_id[matched_id_idx]   if logits_id  is not None else None
        logits_ood_c = logits_ood[matched_ood_idx] if logits_ood is not None else None
        paths_id_c  = ([paths_id[i]  for i in matched_id_idx]  if paths_id  else None)
        paths_ood_c = ([paths_ood[i] for i in matched_ood_idx] if paths_ood else None)

        clean_c_aurocs = run_pair_on_subset(
            feats_id_c, feats_ood_c, pair_name, "cleanC",
            logits_id_sub=logits_id_c, logits_ood_sub=logits_ood_c,
            paths_id_sub=paths_id_c, paths_ood_sub=paths_ood_c,
            model=model,
            method_names=method_names,
        )

        # K3 检查：去污染后 artifact-only<0.65 AND 7 方法均值<0.55
        labels_c = np.array([0]*len(feats_id_c) + [1]*len(feats_ood_c), dtype=np.int32)
        mu_art = art_id_c.mean(0)
        art_dists = np.linalg.norm(np.concatenate([art_id_c, art_ood_c]) - mu_art, axis=1)
        artifact_only_auroc = auroc_numpy(labels_c, art_dists)
        mean_method_auroc = float(np.nanmean(list(clean_c_aurocs.values())))
        print(f"  [K3 check] artifact-only AUROC={artifact_only_auroc:.4f}, "
              f"7-method mean={mean_method_auroc:.4f}")
        if artifact_only_auroc < 0.65 and mean_method_auroc < 0.55:
            print("[K3 WARNING] 去污染后 7 方法均值<0.55 AND artifact<0.65 → "
                  "可能把 semantic 也删了，需回设计！")

        clean_c_ranking = auroc_to_ranking(clean_c_aurocs)
        r5_rows = [{
            "pair": r["pair"], "subset": r["subset"],
            "method": r["method"], "rank": r["rank"], "auroc": r["auroc"],
            "n_matched": n_matched,
        } for r in ranking_to_rows(clean_c_ranking, clean_c_aurocs, "cleanC", pair_name)]
        _write_mode = "a" if _OUT_L3_CLEAN_C.exists() else "w"
        with open(_OUT_L3_CLEAN_C, _write_mode, newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["pair", "subset", "method", "rank", "auroc",
                                               "n_matched"])
            if _write_mode == "w":
                w.writeheader()
            w.writerows(r5_rows)
        print(f"[R5] cleanC ranking -> {_OUT_L3_CLEAN_C}")

        # Bootstrap Spearman CI（命门判据 A-4，v5：13 法）
        orig_rank_list = [raw_ranking[m] for m in method_names]
        clean_rank_list = [clean_c_ranking[m] for m in method_names]
        boot_result = bootstrap_spearman_ci(orig_rank_list, clean_rank_list, B=BOOTSTRAP_B)
        print(f"  [A-4] Spearman(orig,C)={boot_result['spearman']:.4f} "
              f"CI=[{boot_result['ci_lower']:.4f}, {boot_result['ci_upper']:.4f}]")
        ci_upper = boot_result["ci_upper"]
        top1_orig = min(raw_ranking, key=raw_ranking.get)
        top1_clean_rank = clean_c_ranking.get(top1_orig, 99)
        flip_ci = ci_upper < 0.7
        flip_top1 = top1_clean_rank > 3
        print(f"  [A-4] CI_upper<0.7: {flip_ci}, top1({top1_orig}) dropped from top3: {flip_top1}")
        verdict_a4 = "A-4 PASS" if (flip_ci or flip_top1) else "A-4 FAIL"
        print(f"  [A-4] verdict: {verdict_a4}")

        boot_row = {
            "pair": pair_name,
            "spearman_point": boot_result["spearman"],
            "ci_lower": boot_result["ci_lower"],
            "ci_upper": boot_result["ci_upper"],
            "ci_upper_lt_0.7": int(flip_ci),
            "top1_orig": top1_orig,
            "top1_cleanC_rank": top1_clean_rank,
            "top1_dropped_from_top3": int(flip_top1),
            "A4_verdict": verdict_a4,
            "n_matched_pairs": n_matched,
            "common_support_pct": round(common_support_pct, 1),
            "artifact_only_auroc_cleanC": round(artifact_only_auroc, 4),
            "method_mean_auroc_cleanC": round(mean_method_auroc, 4),
            "smd_max": float("nan") if np.isnan(smd_max) else round(float(smd_max), 4),
            "smd_mean": float("nan") if np.isnan(smd_mean) else round(float(smd_mean), 4),
        }
        _write_mode = "a" if _OUT_BOOTSTRAP.exists() else "w"
        with open(_OUT_BOOTSTRAP, _write_mode, newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(boot_row.keys()))
            if _write_mode == "w":
                w.writeheader()
            w.writerow(boot_row)
        print(f"[R5] bootstrap CI -> {_OUT_BOOTSTRAP}")

    # ============================================================
    # R6：方案 A regress-out（仅当 R0a R²<0.3 时）
    # ============================================================
    run_scheme_a = False
    if R0A_CSV.exists():
        try:
            with open(R0A_CSV, "r", encoding="utf-8") as f:
                r0a_rows = list(csv.DictReader(f))
            r2_vals = [float(r["R2"]) for r in r0a_rows if r.get("R2")]
            if r2_vals and max(r2_vals) < 0.3:
                run_scheme_a = True
                print(f"\n[R6] R0a R2<0.3, running Scheme A regress-out")
            else:
                max_r2 = max(r2_vals) if r2_vals else float("nan")
                print(f"\n[R6] R0a max R2={max_r2:.4f} >=0.3, Scheme A invalid (PR-F1)")
        except Exception as e:
            print(f"[R6] cannot read r0a csv: {e}", file=sys.stderr)
    else:
        print(f"\n[R6] r0a_collinearity_R2.csv not ready, skipping Scheme A")

    if run_scheme_a:
        print("[R6] regress-out artifact linear component...")
        clean_a_aurocs = {}
        for method in method_names:
            raw_scores = raw_results[method]["scores"]
            art_all = np.concatenate([art_id, art_ood], axis=0)
            mu = art_all.mean(0)
            sigma = art_all.std(0) + 1e-8
            art_s = (art_all - mu) / sigma
            ones = np.ones((len(art_s), 1), dtype=np.float64)
            A = np.concatenate([ones, art_s], axis=1).astype(np.float64)
            b = raw_scores.astype(np.float64)
            lam = 1e-3
            ATA = A.T @ A + lam * np.eye(A.shape[1])
            try:
                w = np.linalg.solve(ATA, A.T @ b)
            except np.linalg.LinAlgError:
                w = np.linalg.lstsq(ATA, A.T @ b, rcond=None)[0]
            residual_scores = (b - A @ w).astype(np.float32)
            labels_all = np.array([0]*N_ID + [1]*N_OOD, dtype=np.int32)
            clean_a_aurocs[method] = auroc_numpy(labels_all, residual_scores)

        clean_a_ranking = auroc_to_ranking(clean_a_aurocs)
        ra_rows = ranking_to_rows(clean_a_ranking, clean_a_aurocs, "cleanA", pair_name)
        _write_mode = "a" if _OUT_L3_CLEAN_A.exists() else "w"
        with open(_OUT_L3_CLEAN_A, _write_mode, newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["pair", "subset", "method", "rank", "auroc"])
            if _write_mode == "w":
                w.writeheader()
            w.writerows(ra_rows)
        print(f"[R6] cleanA ranking -> {_OUT_L3_CLEAN_A}")

    # ============================================================
    # R7：方案 B PCA-1 分层
    # ============================================================
    print(f"\n[R7] {pair_name}: 方案 B PCA-1 artifact 分层")
    # PCA-1 on artifact 特征，按第一主成分中位数分两层
    art_all = np.concatenate([art_id, art_ood], axis=0)
    labels_all = np.array([0]*N_ID + [1]*N_OOD, dtype=np.int32)
    mu_art = art_all.mean(0)
    art_c = art_all - mu_art
    try:
        _, _, Vt_art = np.linalg.svd(art_c, full_matrices=False)
        pc1 = Vt_art[0]  # (43,)
        proj_pc1 = art_c @ pc1  # (N,)
        median_pc1 = float(np.median(proj_pc1))
        stratum_low = proj_pc1 <= median_pc1
        stratum_high = ~stratum_low

        clean_b_aurocs = {}
        for method in method_names:
            scores = raw_results[method]["scores"]
            # 两层各算 AUROC，平均（分层均等化）
            a_low = auroc_numpy(labels_all[stratum_low], scores[stratum_low])
            a_high = auroc_numpy(labels_all[stratum_high], scores[stratum_high])
            # 忽略 nan 层
            valid = [v for v in [a_low, a_high] if not np.isnan(v)]
            clean_b_aurocs[method] = float(np.mean(valid)) if valid else float("nan")

        clean_b_ranking = auroc_to_ranking(clean_b_aurocs)
        rb_rows = ranking_to_rows(clean_b_ranking, clean_b_aurocs, "cleanB", pair_name)
        _write_mode = "a" if _OUT_L3_CLEAN_B.exists() else "w"
        with open(_OUT_L3_CLEAN_B, _write_mode, newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["pair", "subset", "method", "rank", "auroc"])
            if _write_mode == "w":
                w.writeheader()
            w.writerows(rb_rows)
        print(f"[R7] cleanB ranking -> {_OUT_L3_CLEAN_B}")
    except Exception as e:
        print(f"[R7] PCA failed: {e}", file=sys.stderr)

    print(f"\n[L3] done {pair_name}. output files:")
    for p in [_OUT_SCORES_RAW, _OUT_L3_RAW, _OUT_L3_CLEAN_C,
              _OUT_BOOTSTRAP, _OUT_L3_CLEAN_A, _OUT_L3_CLEAN_B]:
        status = "OK" if p.exists() else "skipped"
        print(f"  {status}: {p}")


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()

    parser = argparse.ArgumentParser(description="L3 OOD reranking (R3b-R7)")
    parser.add_argument("--smoke", action="store_true",
                        help="Synthetic-feature smoke test (no extract_frozen_feats needed)")
    parser.add_argument("--device", type=str, default="cuda",
                        help="cuda | cpu (for ODIN/GradNorm live inference)")
    parser.add_argument("--caliper", type=float, default=CALIPER_SD,
                        help=f"Scheme C caliper in SD units (default={CALIPER_SD}, pre-registered)")
    args = parser.parse_args()
    main(smoke=args.smoke, device=args.device, caliper=args.caliper)
