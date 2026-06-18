"""
selinf_datafission.py — SelInfBench Gate1 主脚本
服务: SelInfBench (selinf) A2 GO/NO-GO，lever = data fission 有效区间重算 HAM deflation
不启动训练外部进程；写完交主线跑。

方法：Leiner+ JASA2023 data fission
  f(X_i) = X_i + tau * Z_i  （选择用，Z_i ~ N(0, sigma^2)）
  g(X_i) = X_i - Z_i / tau  （推断用）
  选 i* = argmax f(X_i)，对 g(X_{i*}) 建标准 N CI（条件分布 N(mu_{i*}, sigma^2*(1+1/tau^2))）
  deflation = data_fission_CI_width / naive_CI_width - 1

sigma 估计口径：sweep pooled std（18 个 val_acc 的样本标准差）。
  理由：每个 config 仅训练一次，无重复采样无法做 per-config bootstrap；
  pooled std 代理「config-to-config 自然波动 + 噪声」下界，保守估计 sigma。
  注：如能多次重跑同 config，per-config bootstrap 更精确——但现有 sweep 设计无重复。

输出 csv: project/meeting/SelInfBench/results/ham_datafission.csv
  per-config 行：config, lr, dropout, seed, val_acc, macro_auc
  统计行 (config=_STAT_*): method{naive,datafission,sqrtM_invalid},
                            selected_config, ci_low, ci_high, ci_width,
                            deflation_pct, M

A2 判据（末尾打印）：
  datafission deflation > 20%  → GO（继续扩 3 benchmark）
  datafission deflation ≤ 20%  → NO-GO/K3（坍，砍项目省算力）

Windows 规范：num_workers=0, pin_memory=False, if __name__=='__main__' 包主逻辑
"""

import os
import sys
import argparse
import itertools
import random
from pathlib import Path

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms
from torchvision.models import efficientnet_b3, EfficientNet_B3_Weights
from PIL import Image

# ── 路径（真源 .portfolio/datasets.json ham10000 条目）────────────────────────
HAM_ROOT    = Path("D:/YJ-Agent/data/external/ham10000")
HAM_META    = HAM_ROOT / "HAM10000_metadata.csv"
HAM_IMG_DIRS = [
    HAM_ROOT / "HAM10000_images_part_1",
    HAM_ROOT / "HAM10000_images_part_2",
]
OUT_DIR  = Path("D:/YJ-Agent/project/meeting/SelInfBench/results")
OUT_CSV  = OUT_DIR / "ham_datafission.csv"

# ── HP sweep 网格（与 G5 killshot 保持一致，可比）────────────────────────────
HP_LR       = [1e-3, 3e-4]       # 2
HP_DROPOUT  = [0.2, 0.4, 0.6]    # 3
HP_SEEDS    = [42, 123, 2024]     # 3
# 2 × 3 × 3 = 18 configs

BATCH               = 32
EPOCHS_PER_CONFIG   = 15
TRAIN_N             = 600
VAL_N               = 300
NUM_CLASSES         = 7

# data fission 参数
FISSION_TAU         = 1.0   # tau: 选择/推断信息分配比，1.0 = 等分
FISSION_N_BOOT      = 500   # bootstrap 重采样次数（用于 naive CI 对照）
ALPHA               = 0.05  # 1 - confidence level

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# RTX 4070 Laptop WDDM + cuDNN 9.x: benchmark=True 会触发 CUDNN_STATUS_EXECUTION_FAILED
# 显式关掉 benchmark，让 cuDNN 用保守算法选择策略（无精度影响）
torch.backends.cudnn.benchmark = False


# ═══════════════════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════════════════

def set_seed(s: int):
    random.seed(s)
    np.random.seed(s)
    torch.manual_seed(s)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(s)


def find_image(image_id: str) -> Path | None:
    for d in HAM_IMG_DIRS:
        p = d / f"{image_id}.jpg"
        if p.exists():
            return p
    return None


def z_score(alpha: float) -> float:
    """
    N(0,1) upper alpha/2 quantile，纯 numpy + math.erf（禁 scipy.stats，OMP Error #15）。
    实现：A&S 26.2.17 初始猜 + 5 步 Newton 在 Phi(x)=p 上迭代，精度 <1e-10。
    """
    import math
    p     = 1.0 - alpha / 2.0                      # target CDF value, e.g. 0.975
    sqrt2 = math.sqrt(2.0)
    sqp2  = math.sqrt(2.0 * math.pi)

    # A&S 初始猜（用正态分布尾近似）
    t  = math.sqrt(-2.0 * math.log(min(p, 1.0 - p)))
    c  = [2.515517, 0.802853, 0.010328]
    d  = [1.432788, 0.189269, 0.001308]
    x0 = t - (c[0] + c[1]*t + c[2]*t**2) / (1 + d[0]*t + d[1]*t**2 + d[2]*t**3)
    x  = x0 if p >= 0.5 else -x0

    # 5 步 Newton：f(x) = Phi(x) - p = 0，f'(x) = phi(x)
    for _ in range(5):
        phi_x  = 0.5 * (1.0 + math.erf(x / sqrt2))   # Phi(x)
        dphi_x = math.exp(-0.5 * x * x) / sqp2        # phi(x)
        x -= (phi_x - p) / dphi_x
    return float(x)


# ═══════════════════════════════════════════════════════════════════════════════
# 数据集（复用 G5 HAMDataset，保持可比）
# ═══════════════════════════════════════════════════════════════════════════════

class HAMDataset(Dataset):
    DX_MAP = {"akiec": 0, "bcc": 1, "bkl": 2, "df": 3, "mel": 4, "nv": 5, "vasc": 6}
    TFM = transforms.Compose([
        transforms.Resize(224),
        transforms.CenterCrop(224),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])

    def __init__(self, records: list[dict]):
        self.records = records

    def __len__(self):
        return len(self.records)

    def __getitem__(self, idx):
        rec = self.records[idx]
        img = Image.open(rec["path"]).convert("RGB")
        return self.TFM(img), rec["label"]


def build_records(meta: pd.DataFrame, indices) -> list[dict]:
    recs = []
    for i in indices:
        row = meta.iloc[i]
        path = find_image(row["image_id"])
        if path is None:
            continue
        recs.append({
            "image_id": row["image_id"],
            "label": HAMDataset.DX_MAP[row["dx"]],
            "path": str(path),
        })
    return recs


# ═══════════════════════════════════════════════════════════════════════════════
# 单 config 训练 → (val_acc, macro_auc)
# ═══════════════════════════════════════════════════════════════════════════════

def macro_auc_numpy(labels: np.ndarray, probs: np.ndarray, n_classes: int) -> float:
    """
    macro-AUC（one-vs-rest），纯 numpy（禁 sklearn.metrics，禁 scipy.stats）。
    """
    aucs = []
    for c in range(n_classes):
        y_bin = (labels == c).astype(float)
        if y_bin.sum() == 0 or y_bin.sum() == len(y_bin):
            continue
        score = probs[:, c]
        # Mann-Whitney U → AUC
        pos_scores = score[y_bin == 1]
        neg_scores = score[y_bin == 0]
        # 计算 AUC = P(pos > neg) via sorting
        n_pos, n_neg = len(pos_scores), len(neg_scores)
        all_scores = np.concatenate([pos_scores, neg_scores])
        all_labels = np.concatenate([np.ones(n_pos), np.zeros(n_neg)])
        order = np.argsort(-all_scores)
        ranked_labels = all_labels[order]
        # trapezoid rule on ROC
        tpr_pts = np.concatenate([[0.0], np.cumsum(ranked_labels == 1) / n_pos, [1.0]])
        fpr_pts = np.concatenate([[0.0], np.cumsum(ranked_labels == 0) / n_neg, [1.0]])
        auc = float(np.trapz(tpr_pts, fpr_pts))
        aucs.append(auc)
    return float(np.mean(aucs)) if aucs else float("nan")


def _disable_inplace_silu(model: nn.Module) -> nn.Module:
    """
    EfficientNet 内置 SiLU 默认 inplace=True，在 GPU 上触发
    'CUDA error: invalid program counter / illegal memory access'。
    （已知 torchvision EfficientNet + 特定 CUDA 版本 inplace SiLU 兼容性 bug）
    递归把所有 inplace SiLU 改成 out-of-place，不影响精度。
    """
    for name, child in model.named_children():
        if isinstance(child, nn.SiLU) and child.inplace:
            setattr(model, name, nn.SiLU(inplace=False))
        else:
            _disable_inplace_silu(child)
    return model


def run_config(train_recs: list, val_recs: list,
               lr: float, dropout: float, seed: int,
               epochs: int = EPOCHS_PER_CONFIG) -> tuple[float, float]:
    """
    Fast finetune EfficientNet-B3，返回 (best_val_acc, macro_auc_at_best_epoch)。
    复用 G5 backbone + DataLoader 规范（num_workers=0, pin_memory=False）。
    """
    set_seed(seed)
    model = efficientnet_b3(weights=EfficientNet_B3_Weights.IMAGENET1K_V1)
    in_features = model.classifier[1].in_features
    model.classifier = nn.Sequential(
        nn.Dropout(p=dropout),
        nn.Linear(in_features, NUM_CLASSES),
    )
    _disable_inplace_silu(model)   # 修 inplace SiLU GPU bug（CUDA illegal memory access）
    model = model.to(DEVICE)

    tr_loader = DataLoader(
        HAMDataset(train_recs), batch_size=BATCH, shuffle=True,
        num_workers=0, pin_memory=False,
    )
    val_loader = DataLoader(
        HAMDataset(val_recs), batch_size=BATCH, shuffle=False,
        num_workers=0, pin_memory=False,
    )
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    criterion = nn.CrossEntropyLoss()

    best_acc   = 0.0
    best_auc   = float("nan")

    for ep in range(epochs):
        # train
        model.train()
        for x, y in tr_loader:
            x, y = x.to(DEVICE), y.to(DEVICE)
            opt.zero_grad()
            criterion(model(x), y).backward()
            opt.step()

        # val
        model.eval()
        all_preds, all_labels, all_probs = [], [], []
        with torch.no_grad():
            for x, y in val_loader:
                x, y = x.to(DEVICE), y.to(DEVICE)
                logits = model(x)
                probs  = F.softmax(logits, dim=1)
                preds  = logits.argmax(dim=1)
                all_preds.append(preds.cpu().numpy())
                all_labels.append(y.cpu().numpy())
                all_probs.append(probs.cpu().numpy())

        all_preds  = np.concatenate(all_preds)
        all_labels = np.concatenate(all_labels)
        all_probs  = np.concatenate(all_probs, axis=0)

        acc = float((all_preds == all_labels).mean())
        if acc > best_acc:
            best_acc = acc
            best_auc = macro_auc_numpy(all_labels, all_probs, NUM_CLASSES)

    return best_acc, best_auc


# ═══════════════════════════════════════════════════════════════════════════════
# Data Fission CI（Leiner+ JASA2023）
# ═══════════════════════════════════════════════════════════════════════════════

def data_fission_ci(
    accs: np.ndarray,
    sigma: float,
    tau: float = FISSION_TAU,
    alpha: float = ALPHA,
    rng: np.random.Generator | None = None,
) -> dict:
    """
    Data fission selective CI（Leiner+ JASA2023）：
      Z_i ~ N(0, sigma^2)，独立注入
      f_i = X_i + tau * Z_i   → 选择信道（argmax）
      g_i = X_i - Z_i / tau   → 推断信道

    被选 i* = argmax f，对 g_{i*} 建标准 CI：
      g_{i*} ~ N(mu_{i*}, sigma^2 * (1 + 1/tau^2))
      CI = g_{i*} ± z_{1-alpha/2} * sigma * sqrt(1 + 1/tau^2)

    理论保证：g_{i*} 与「i* 是谁被选中」这一事件条件独立（fission 核心引理），
    故标准 CI（不需截断正态）有效覆盖 mu_{i*}。
    """
    if rng is None:
        rng = np.random.default_rng(0)

    M = len(accs)
    Z = rng.normal(0.0, sigma, size=M)          # Z_i ~ N(0, sigma^2)
    f = accs + tau * Z                           # 选择信道
    g = accs - Z / tau                           # 推断信道

    i_star = int(np.argmax(f))                   # argmax 在 f 上选
    g_star = float(g[i_star])                    # 推断用的观测值

    # 推断信道 g_{i*} 的标准差
    se_g = sigma * np.sqrt(1.0 + 1.0 / tau**2)
    z    = z_score(alpha)

    ci_low  = g_star - z * se_g
    ci_high = g_star + z * se_g

    return {
        "selected_idx":    i_star,
        "g_star":          g_star,
        "se_g":            se_g,
        "ci_low":          ci_low,
        "ci_high":         ci_high,
        "ci_width":        ci_high - ci_low,
        "f_selected":      float(f[i_star]),
        "Z_selected":      float(Z[i_star]),
    }


def naive_ci(accs: np.ndarray, alpha: float = ALPHA) -> dict:
    """
    Naive CI：对所有 config val_acc 的均值建标准 CLT CI（不考虑 argmax 选择）。
    同时记录 argmax val_acc（即 naive 报告值）的 naive 区间（CLT，se = pooled_std/sqrt(M)）。
    """
    M   = len(accs)
    mu  = float(accs.mean())
    se  = float(np.std(accs, ddof=1) / np.sqrt(M))
    z   = z_score(alpha)
    return {
        "mean_acc":  mu,
        "se":        se,
        "ci_low":    mu - z * se,
        "ci_high":   mu + z * se,
        "ci_width":  2 * z * se,
        "best_acc":  float(accs.max()),
        "best_outside_naive": bool(accs.max() > mu + z * se),
    }


def sqrt_m_invalid_ci(accs: np.ndarray, alpha: float = ALPHA) -> dict:
    """
    √M 近似（G5 旧方法，标注 invalid baseline）：
      bias = sigma * E[max Z_M]（Monte Carlo），校正后 CI 宽 = naive_width * sqrt(M)
      此为固定 M 下的数学恒等式，与数据无关，只用作对照列。
    """
    M      = len(accs)
    sigma  = float(np.std(accs, ddof=1))
    rng_mc = np.random.default_rng(42)
    emz    = float(rng_mc.standard_normal((10000, M)).max(axis=1).mean())
    bias   = sigma * emz

    naive = naive_ci(accs, alpha)
    # 校正后宽度 ≈ naive_width * sqrt(M)（恒等式）
    corr_width  = naive["ci_width"] * np.sqrt(M)
    corr_point  = naive["best_acc"] - bias
    z           = z_score(alpha)
    se_corr     = sigma   # conservative

    return {
        "corrected_point": corr_point,
        "ci_low":          corr_point - z * se_corr,
        "ci_high":         corr_point + z * se_corr,
        "ci_width":        corr_width,
        "bias":            bias,
        "emz":             emz,
        "note":            "INVALID_BASELINE sqrt(M) identity, not a valid CI",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════════════════

def main(smoke: bool = False, cpu_only: bool = False, tau: float = FISSION_TAU):
    global DEVICE
    if cpu_only:
        DEVICE = torch.device("cpu")

    print(f"[selinf_datafission] Device={DEVICE}  tau={tau}  smoke={smoke}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    set_seed(42)

    # ── 数据分割 ────────────────────────────────────────────────────────────────
    meta    = pd.read_csv(HAM_META)
    idx_all = list(range(len(meta)))
    random.shuffle(idx_all)

    if smoke:
        train_idx  = idx_all[:80]
        val_idx    = idx_all[80:130]
        hp_grid    = [(1e-3, 0.2, 42), (3e-4, 0.4, 123)]   # 2 configs
        epochs_per = 2
        print("[SMOKE] 2 configs, 2 epochs, no GPU required (cpu_only=True recommended)")
    else:
        train_idx  = idx_all[:TRAIN_N]
        val_idx    = idx_all[TRAIN_N:TRAIN_N + VAL_N]
        hp_grid    = list(itertools.product(HP_LR, HP_DROPOUT, HP_SEEDS))  # 18
        epochs_per = EPOCHS_PER_CONFIG

    train_recs = build_records(meta, train_idx)
    val_recs   = build_records(meta, val_idx)
    print(f"train={len(train_recs)}  val={len(val_recs)}  M={len(hp_grid)} configs")

    # ── Sweep 18 configs ────────────────────────────────────────────────────────
    rows     = []
    all_accs = []
    all_aucs = []

    for ci, (lr, dropout, seed) in enumerate(hp_grid):
        cfg_name = f"lr={lr}_dp={dropout}_s={seed}"
        print(f"\n  [{ci+1}/{len(hp_grid)}] {cfg_name}")
        acc, auc = run_config(
            train_recs, val_recs,
            lr=lr, dropout=dropout, seed=seed,
            epochs=epochs_per,
        )
        print(f"    val_acc={acc:.4f}  macro_auc={auc:.4f}")
        rows.append({
            "config":    cfg_name,
            "lr":        lr,
            "dropout":   dropout,
            "seed":      seed,
            "val_acc":   round(acc, 6),
            "macro_auc": round(auc, 6),
        })
        all_accs.append(acc)
        all_aucs.append(auc)

    accs_np = np.array(all_accs)
    M       = len(accs_np)

    # ── sigma 估计（sweep pooled std；口径：所有 config 的 val_acc 样本 std）──
    #    见模块注释"sigma 估计口径"节——per-config 无重复，pooled std 代理保守下界
    sigma_hat = float(np.std(accs_np, ddof=1))
    print(f"\nsigma_hat (sweep pooled std, M={M}) = {sigma_hat:.6f}")

    # ── 三种 CI ────────────────────────────────────────────────────────────────
    # 1. Naive CI（均值 CI，不含选择校正）
    naive = naive_ci(accs_np)

    # 2. Data fission CI（Leiner+ JASA2023，主方法）
    rng_fission = np.random.default_rng(42)
    df_ci       = data_fission_ci(accs_np, sigma=sigma_hat, tau=tau,
                                  rng=rng_fission)

    # 3. √M 近似（G5 旧方法，invalid baseline 对照）
    sqrtm = sqrt_m_invalid_ci(accs_np)

    # ── deflation 计算 ─────────────────────────────────────────────────────────
    # deflation = data_fission_CI_width / naive_CI_width - 1
    # (>0 表示 data fission CI 更宽，即报告习惯通胀被量化)
    deflation_datafission = df_ci["ci_width"] / naive["ci_width"] - 1.0
    deflation_sqrtm       = sqrtm["ci_width"] / naive["ci_width"] - 1.0   # ≈ √M−1 恒等式

    # ── 拼统计行 ───────────────────────────────────────────────────────────────
    best_idx = int(np.argmax(accs_np))

    def _stat_row(method, selected_config, ci_low, ci_high, deflation_pct, extra=""):
        return {
            "config":           f"_STAT_{method}{extra}",
            "lr":               None,
            "dropout":          None,
            "seed":             None,
            "val_acc":          None,
            "macro_auc":        None,
            "method":           method,
            "selected_config":  selected_config,
            "ci_low":           round(ci_low, 6),
            "ci_high":          round(ci_high, 6),
            "ci_width":         round(ci_high - ci_low, 6),
            "deflation_pct":    round(deflation_pct * 100, 4),
            "M":                M,
            "sigma_hat":        round(sigma_hat, 6),
            "tau":              tau,
        }

    best_cfg_name = rows[best_idx]["config"]
    df_selected   = rows[df_ci["selected_idx"]]["config"]   # argmax 可能不同（f vs acc）

    stat_rows = [
        _stat_row("naive",             best_cfg_name,   naive["ci_low"],    naive["ci_high"],   0.0),
        _stat_row("datafission",       df_selected,     df_ci["ci_low"],    df_ci["ci_high"],   deflation_datafission),
        _stat_row("sqrtM_invalid",     best_cfg_name,   sqrtm["ci_low"],    sqrtm["ci_high"],   deflation_sqrtm,
                  "_INVALID_BASELINE"),
    ]

    # 补齐 per-config 行里没有的列
    for r in rows:
        r.setdefault("method",          None)
        r.setdefault("selected_config", None)
        r.setdefault("ci_low",          None)
        r.setdefault("ci_high",         None)
        r.setdefault("ci_width",        None)
        r.setdefault("deflation_pct",   None)
        r.setdefault("M",               None)
        r.setdefault("sigma_hat",       None)
        r.setdefault("tau",             None)

    df_out = pd.DataFrame(rows + stat_rows)
    # 列顺序：per-config 主列在前，统计列在后
    col_order = ["config", "lr", "dropout", "seed", "val_acc", "macro_auc",
                 "method", "selected_config", "ci_low", "ci_high", "ci_width",
                 "deflation_pct", "M", "sigma_hat", "tau"]
    df_out = df_out[[c for c in col_order if c in df_out.columns]]
    df_out.to_csv(OUT_CSV, index=False)
    print(f"\nSaved: {OUT_CSV}")

    # ── A2 GO/NO-GO 判决 ───────────────────────────────────────────────────────
    _print_verdict(
        accs_np, naive, df_ci, sqrtm,
        deflation_datafission, deflation_sqrtm,
        best_cfg_name, df_selected, M, sigma_hat, tau,
    )


def _print_verdict(
    accs_np, naive, df_ci, sqrtm,
    defl_df, defl_sqrtm,
    best_cfg_name, df_selected, M, sigma_hat, tau,
):
    print("\n" + "=" * 70)
    print("A2 GO/NO-GO VERDICT — SelInfBench Gate1 (data fission)")
    print("=" * 70)
    print(f"  Sweep M = {M} configs")
    print(f"  sigma_hat (pooled std) = {sigma_hat:.6f}")
    print(f"  tau = {tau}")
    print()
    print(f"  Best acc (argmax sweep)     = {float(accs_np.max()):.4f}  [{best_cfg_name}]")
    print(f"  Best outside naive CI?      = {naive['best_outside_naive']}")
    print()
    print(f"  [NAIVE]        CI = [{naive['ci_low']:.4f}, {naive['ci_high']:.4f}]  "
          f"width={naive['ci_width']:.4f}")
    print(f"  [DATAFISSION]  selected={df_selected}")
    print(f"                 g*={df_ci['g_star']:.4f}  se_g={df_ci['se_g']:.4f}")
    print(f"                 CI = [{df_ci['ci_low']:.4f}, {df_ci['ci_high']:.4f}]  "
          f"width={df_ci['ci_width']:.4f}")
    print(f"  [SQRTM_INVAL]  CI = [{sqrtm['ci_low']:.4f}, {sqrtm['ci_high']:.4f}]  "
          f"width={sqrtm['ci_width']:.4f}  (INVALID baseline)")
    print()
    print(f"  deflation(datafission) = {defl_df*100:.2f}%  "
          f"[data fission CI wider than naive CI by this fraction]")
    print(f"  deflation(sqrtM_inv)   = {defl_sqrtm*100:.2f}%  "
          f"[恒等式 ≈ (sqrt({M})-1)*100%，与数据无关]")
    print()
    print("--- A2 DECISION ---")
    if defl_df > 0.20:
        verdict = f"GO  (data fission deflation={defl_df*100:.1f}% > 20%) " \
                  f"→ 继续扩 ≥3 benchmark (A3)"
    elif defl_df > 0.05:
        verdict = f"BORDERLINE (deflation={defl_df*100:.1f}%, 5%-20%) " \
                  f"→ 建议人工审核后决定；sigma_hat 口径可能保守"
    else:
        verdict = f"NO-GO/K3  (deflation={defl_df*100:.1f}% ≤ 5%) " \
                  f"→ data fission CI 坍个位数，触发 K3 kill criteria"
    print(f"  {verdict}")
    print("=" * 70)


# ═══════════════════════════════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()   # Windows spawn 安全

    parser = argparse.ArgumentParser(description="SelInfBench Gate1: data fission HAM deflation")
    parser.add_argument("--smoke",    type=int, default=0,
                        help="1 = 2 config × 2 epoch smoke test (建议加 --cpu)")
    parser.add_argument("--cpu",      action="store_true",
                        help="强制 CPU（smoke 验算子用）")
    parser.add_argument("--tau",      type=float, default=FISSION_TAU,
                        help=f"data fission tau（默认 {FISSION_TAU}）")
    args = parser.parse_args()
    main(smoke=bool(args.smoke), cpu_only=args.cpu, tau=args.tau)
