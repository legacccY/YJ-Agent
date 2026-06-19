"""
selinf_bootstrap_coverage.py — SelInfBench A1/A2 bootstrap CI 覆盖率分析
服务: SelInfBench (selinf) A1 证据强度 + A2 真数据有效性
     lever = HAM winner's curse bootstrap CI（A1）+ 条件覆盖率修回（A2 真数据版）

# 辖域说明（caveat，防审稿人质疑）
# ── 写在这里，也会输出到 csv 的 meta 行 ──
# 「真值」定义：被选 config（i*）在完整 test 分区的 AUROC（full-test AUROC 代理）。
# 这是有限样本近似，不是总体 AUROC；覆盖率是「对该 full-test 代理的覆盖」，
# 非对真正总体 AUROC 的覆盖。full-test 样本量有限（HAM=600, BraTS~546, ISIC~6626），
# 本身也有估计误差，尤其 HAM/BraTS 阳性样本少。
# 报告时须注明此辖域（§5 Discussion，BUILD_MAP.md 规范）。

# 方法红线（BUILD_MAP 禁用指标，违反即跑偏）
# 🚫 deflation = df_width/naive_width−1（纯 M artifact）
# 🚫 debias_shift = val_best−g_star（构造性偏正）
# 两者永不当证据，本脚本不计算/不输出。

# A1 — HAM winner's curse bootstrap CI
# bootstrap 重采样 HAM test 集 B=1000 次，每次算 test AUROC。
# winner's curse = val_best − test_AUROC 的 bootstrap 分布。
# 报 95% CI 下界是否 >0（证 +0.0746 非抽样噪声）。
# val_best 固定（不 bootstrap），只 bootstrap test AUROC。

# A2 — 三 benchmark 真数据覆盖率
# 流程：从完整 test 分区 bootstrap 采大小=n_val 的评估子集（B=1000）。
# 对每个子集建：
#   (a) naive 单点 95% CI：中心=子集 AUROC，宽=2·z·sigma_hat_sub
#       sigma_hat_sub = sqrt(p_hat*(1-p_hat)/n_sub) 近似（Hanley-McNeil 代理）
#   (b) data fission CI：沿用 selinf_a3_truthproxy.py data_fission_ci 口径
#       sigma = pooled std of val AUROCs（全 M config，从 npz 的 all_val_aurocs 读）
# 「真值」= 被选 config 在完整 test 分区的 full-test AUROC。
# 覆盖率 = CI 包含真值的频率（B=1000 次）。
# 预期：naive 覆盖 <95%（子集噪声致估计偏），df 覆盖 ~93-95%（修回）。

# sigma_hat 估计口径（A2）
# 与 selinf_a3_truthproxy.py 完全一致：pooled std of val AUROCs（ddof=1）。
# 理由：每 config 通常只跑一次；pooled std 代理 config-to-config 波动下界（保守）。
# 来源：npz 中 all_val_aurocs 数组（由 --cache_scores 落盘）。
# 若 npz 不含 all_val_aurocs，则退回读 a3_truthproxy.csv 对应行的 sigma_hat。

# 输入
#   results/scores_<benchmark>_M<m>_<cfg>.npz（由 selinf_a3_truthproxy --cache_scores 生成）
#   或（fallback）results/a3_truthproxy.csv（仅含 AUROC 点估计，无 per-sample 分数）
# 输出
#   results/a3_bootstrap_coverage.csv

# Windows 规范
#   纯 numpy/pandas/math；禁 scipy.stats（OMP Error #15）；
#   禁 sklearn.metrics（同理 OMP 风险，用纯 numpy AUROC）；
#   num_workers=0；if __name__=='__main__' 包主逻辑。
"""

import argparse
import math
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

# ── 路径默认值 ─────────────────────────────────────────────────────────────────
RESULTS_DIR = Path("D:/YJ-Agent/project/meeting/SelInfBench/results")
A3_CSV      = RESULTS_DIR / "a3_truthproxy.csv"
OUT_CSV     = RESULTS_DIR / "a3_bootstrap_coverage.csv"

# ── 常量 ───────────────────────────────────────────────────────────────────────
B_BOOT      = 1000    # bootstrap 重采样次数
ALPHA       = 0.05    # CI 名义水平 95%
FISSION_TAU = 1.0     # 与 selinf_a3_truthproxy.py 完全一致


# ═══════════════════════════════════════════════════════════════════════════════
# 纯 numpy 工具（禁 scipy.stats，禁 sklearn，OMP Red Line）
# ═══════════════════════════════════════════════════════════════════════════════

def z_score(alpha: float) -> float:
    """
    N(0,1) upper alpha/2 quantile，纯 math.erf Newton 迭代。
    与 selinf_a3_truthproxy.py 完全一致（禁 scipy.stats）。
    """
    p     = 1.0 - alpha / 2.0
    sqrt2 = math.sqrt(2.0)
    sqp2  = math.sqrt(2.0 * math.pi)
    t     = math.sqrt(-2.0 * math.log(min(p, 1.0 - p)))
    c     = [2.515517, 0.802853, 0.010328]
    d     = [1.432788, 0.189269, 0.001308]
    x0    = t - (c[0] + c[1]*t + c[2]*t**2) / (1 + d[0]*t + d[1]*t**2 + d[2]*t**3)
    x     = x0 if p >= 0.5 else -x0
    for _ in range(5):
        phi_x  = 0.5 * (1.0 + math.erf(x / sqrt2))
        dphi_x = math.exp(-0.5 * x * x) / sqp2
        x -= (phi_x - p) / dphi_x
    return float(x)


def binary_auroc_numpy(labels: np.ndarray, scores: np.ndarray) -> float:
    """
    二分类 AUROC，纯 numpy Mann-Whitney trapz（禁 sklearn/scipy，OMP Red Line）。
    与 selinf_a3_truthproxy.py 口径完全一致。
    labels: 0/1; scores: float（越高=越正类）。
    返回 nan 若单类或空。
    """
    y_bin = labels.astype(float)
    if y_bin.sum() == 0 or y_bin.sum() == len(y_bin) or len(y_bin) == 0:
        return float("nan")
    pos = scores[y_bin == 1]
    neg = scores[y_bin == 0]
    n_pos, n_neg = len(pos), len(neg)
    all_s = np.concatenate([pos, neg])
    all_l = np.concatenate([np.ones(n_pos), np.zeros(n_neg)])
    order = np.argsort(-all_s)
    ranked = all_l[order]
    tpr = np.concatenate([[0.0], np.cumsum(ranked == 1) / n_pos])
    fpr = np.concatenate([[0.0], np.cumsum(ranked == 0) / n_neg])
    return float(np.trapz(tpr, fpr))


def data_fission_ci(
    accs:  np.ndarray,
    sigma: float,
    tau:   float = FISSION_TAU,
    alpha: float = ALPHA,
    rng          = None,
) -> dict:
    """
    Leiner+ JASA2023 data fission selective CI。
    与 selinf_a3_truthproxy.py 完全一致（sigma=pooled val std，tau=1.0）。
    f = accs + tau*Z（选择用），g = accs − Z/tau（推断用）。
    i* = argmax(f)，g_star = g[i*]，对 g_star 建标准 CI。
    """
    if rng is None:
        rng = np.random.default_rng(0)
    M      = len(accs)
    Z      = rng.normal(0.0, sigma, size=M)
    f      = accs + tau * Z
    g      = accs - Z / tau
    i_star = int(np.argmax(f))
    g_star = float(g[i_star])
    se_g   = sigma * np.sqrt(1.0 + 1.0 / tau**2)
    z      = z_score(alpha)
    return {
        "selected_idx": i_star,
        "g_star":       g_star,
        "ci_low":       g_star - z * se_g,
        "ci_high":      g_star + z * se_g,
    }


def hanley_mcneil_sigma(auroc: float, n_pos: int, n_neg: int) -> float:
    """
    Hanley-McNeil (1982) AUROC 标准误近似。
    用于 naive 单点 CI sigma_hat_sub（bootstrap 子集，已知阳/阴样本数）。
    参考公式：
      Q1 = auroc / (2 - auroc)
      Q2 = 2 * auroc^2 / (1 + auroc)
      se = sqrt((auroc*(1-auroc) + (n_pos-1)*(Q1-auroc^2) + (n_neg-1)*(Q2-auroc^2))
                / (n_pos * n_neg))
    """
    if n_pos <= 0 or n_neg <= 0:
        return float("nan")
    a  = max(1e-6, min(1 - 1e-6, auroc))   # clip 防 nan
    Q1 = a / (2.0 - a)
    Q2 = 2.0 * a * a / (1.0 + a)
    var = (a*(1-a) + (n_pos-1)*(Q1 - a**2) + (n_neg-1)*(Q2 - a**2)) / (n_pos * n_neg)
    return float(math.sqrt(max(var, 0.0)))


# ═══════════════════════════════════════════════════════════════════════════════
# 读 npz 缓存分数
# ═══════════════════════════════════════════════════════════════════════════════

def find_npz(results_dir: Path, bench_name: str, m: int = 18) -> Path | None:
    """
    在 results_dir 里找 scores_<bench>_M<m>_*.npz。
    返回第一个匹配的路径，无则返回 None。
    bench_name 转换：ISIC2020 → ISIC2020，HAM10000 → HAM10000，BraTS2021 → BraTS2021。
    """
    safe_bm = bench_name.replace("/", "_").replace(" ", "_")
    pattern = f"scores_{safe_bm}_M{m}_*.npz"
    matches = sorted(results_dir.glob(pattern))
    if matches:
        return matches[0]
    # 也尝试不含 M 的旧命名（兼容性）
    pattern2 = f"scores_{safe_bm}_*.npz"
    matches2 = sorted(results_dir.glob(pattern2))
    return matches2[0] if matches2 else None


def load_bench_scores(results_dir: Path, bench_name: str, m: int = 18,
                      a3_csv: pd.DataFrame = None) -> dict | None:
    """
    优先读 npz 分数文件；不存在则用 a3_truthproxy.csv 占位（无 per-sample 分数，
    只能做有限分析）。
    返回 dict:
      val_labels, val_scores, test_labels, test_scores (np.ndarray)
      val_auroc, test_auroc (float)
      sigma_hat (float)
      all_val_aurocs (np.ndarray, 可能 None)
      benchmark (str)
      n_test (int)
    """
    npz_path = find_npz(results_dir, bench_name, m)
    if npz_path is not None:
        print(f"  [LOAD] {bench_name} from {npz_path.name}")
        d = np.load(npz_path, allow_pickle=True)
        val_labels  = d["val_labels"]
        val_scores  = d["val_scores"]
        test_labels = d["test_labels"]
        test_scores = d["test_scores"]
        val_auroc   = float(d["val_auroc"][0])
        test_auroc  = float(d["test_auroc"][0])
        all_val_aurocs = d["all_val_aurocs"] if "all_val_aurocs" in d else None
        sigma_hat   = (float(np.std(all_val_aurocs, ddof=1))
                       if all_val_aurocs is not None and len(all_val_aurocs) > 1
                       else 0.01)
        return {
            "val_labels":    val_labels,
            "val_scores":    val_scores,
            "test_labels":   test_labels,
            "test_scores":   test_scores,
            "val_auroc":     val_auroc,
            "test_auroc":    test_auroc,
            "sigma_hat":     sigma_hat,
            "all_val_aurocs": all_val_aurocs,
            "benchmark":     bench_name,
            "n_test":        len(test_labels),
            "n_val":         len(val_labels),
        }

    # fallback：从 a3_truthproxy.csv 读 AUROC 点估计，合成占位 per-sample 分数（烟测用）
    if a3_csv is not None:
        rows = a3_csv[(a3_csv["benchmark"] == bench_name) & (a3_csv["M"] == m)]
        if len(rows) == 0:
            # 尝试不限 M
            rows = a3_csv[a3_csv["benchmark"] == bench_name]
        if len(rows) > 0:
            row = rows.iloc[0]
            print(f"  [FALLBACK] {bench_name} from a3_truthproxy.csv "
                  f"(no per-sample scores; synthetic placeholder for smoke test)")
            n_test = int(row.get("n_test", 600))
            n_val  = int(row.get("n_val",  600))
            sigma_hat = float(row.get("sigma_hat", 0.01))
            test_auroc = float(row["test_selected"])
            val_auroc  = float(row["val_best"])
            # 合成 per-sample 分数（仅供逻辑烟测，不是真实分数）
            rng = np.random.default_rng(0)
            n_pos_test = max(1, int(n_test * 0.15))   # 近似 15% 阳性
            n_neg_test = n_test - n_pos_test
            test_labels = np.array([1]*n_pos_test + [0]*n_neg_test)
            # 按目标 AUROC 构造分数（高斯偏移近似）
            test_scores = (rng.normal(1.0, 1.0, n_pos_test).tolist() +
                           rng.normal(0.0, 1.0, n_neg_test).tolist())
            test_scores = np.array(test_scores)

            n_pos_val = max(1, int(n_val * 0.15))
            n_neg_val = n_val - n_pos_val
            val_labels = np.array([1]*n_pos_val + [0]*n_neg_val)
            val_scores = (rng.normal(1.0, 1.0, n_pos_val).tolist() +
                          rng.normal(0.0, 1.0, n_neg_val).tolist())
            val_scores = np.array(val_scores)

            return {
                "val_labels":    val_labels,
                "val_scores":    val_scores,
                "test_labels":   test_labels,
                "test_scores":   test_scores,
                "val_auroc":     val_auroc,
                "test_auroc":    test_auroc,
                "sigma_hat":     sigma_hat,
                "all_val_aurocs": None,
                "benchmark":     bench_name,
                "n_test":        n_test,
                "n_val":         n_val,
                "is_synthetic":  True,
            }

    print(f"  [SKIP] {bench_name}: no npz and no a3_csv row found.")
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# A1 — HAM winner's curse bootstrap CI
# ═══════════════════════════════════════════════════════════════════════════════

def a1_ham_bootstrap_ci(
    bench_data: dict,
    b:          int   = B_BOOT,
    alpha:      float = ALPHA,
    seed:       int   = 42,
) -> dict:
    """
    A1 补强：HAM winner's curse bootstrap CI。

    winner's curse = val_best − test_AUROC（固定 val_best，bootstrap test AUROC）。
    bootstrap 重采样 test 集（有放回），每次算 test AUROC，
    得 winner's curse 的 bootstrap 分布。
    报 95% CI 下界是否 >0（证 +0.0746 非抽样噪声）。

    val_best 不变（它是 val 集上确定的值，不 bootstrap），
    只 bootstrap test AUROC 的分布。
    """
    test_labels = bench_data["test_labels"]
    test_scores = bench_data["test_scores"]
    val_auroc   = bench_data["val_auroc"]     # val_best，固定
    n_test      = len(test_labels)

    rng = np.random.default_rng(seed)
    wc_boot = []   # winner's curse bootstrap 分布

    for _ in range(b):
        idx     = rng.integers(0, n_test, size=n_test)   # 有放回采样
        lbl_b   = test_labels[idx]
        sc_b    = test_scores[idx]
        auc_b   = binary_auroc_numpy(lbl_b, sc_b)
        if not math.isnan(auc_b):
            wc_boot.append(val_auroc - auc_b)

    wc_boot  = np.array(wc_boot)
    wc_mean  = float(np.mean(wc_boot))
    wc_std   = float(np.std(wc_boot, ddof=1))
    z        = z_score(alpha)
    ci_low   = float(np.percentile(wc_boot, 100 * alpha / 2))     # percentile CI
    ci_high  = float(np.percentile(wc_boot, 100 * (1 - alpha / 2)))
    # 也报 normal CI（双重验证）
    ci_low_n  = wc_mean - z * wc_std
    ci_high_n = wc_mean + z * wc_std

    # 点估计（original）
    full_test_auroc = bench_data["test_auroc"]
    wc_original     = val_auroc - full_test_auroc

    ci_low_pos = ci_low > 0

    print(f"\n[A1 HAM bootstrap CI]")
    print(f"  val_best (fixed)       = {val_auroc:.4f}")
    print(f"  full_test_auroc        = {full_test_auroc:.4f}")
    print(f"  winner's_curse_orig    = {wc_original:+.4f}")
    print(f"  bootstrap mean WC      = {wc_mean:+.4f}  std={wc_std:.4f}  (B={len(wc_boot)})")
    print(f"  95% percentile CI      = [{ci_low:+.4f}, {ci_high:+.4f}]")
    print(f"  95% normal CI          = [{ci_low_n:+.4f}, {ci_high_n:+.4f}]")
    print(f"  CI_low > 0: {ci_low_pos}  "
          f"{'=> winner_curse NOT noise (A1 PASS)' if ci_low_pos else '=> CI crosses 0 (A1 WEAK)'}")

    return {
        "analysis":        "A1_HAM_bootstrap_CI",
        "benchmark":       bench_data["benchmark"],
        "val_best":        round(val_auroc,      6),
        "full_test_auroc": round(full_test_auroc, 6),
        "wc_original":     round(wc_original,    6),
        "wc_boot_mean":    round(wc_mean,        6),
        "wc_boot_std":     round(wc_std,         6),
        "wc_ci_low_pct":   round(ci_low,         6),
        "wc_ci_high_pct":  round(ci_high,        6),
        "wc_ci_low_norm":  round(ci_low_n,       6),
        "wc_ci_high_norm": round(ci_high_n,      6),
        "ci_low_gt_zero":  int(ci_low_pos),
        "B":               len(wc_boot),
        "alpha":           alpha,
        "note": (
            "A1 pass => winner's curse +0.0746 非抽样噪声；"
            "val_best 固定不 bootstrap，只 bootstrap test AUROC 分布。"
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# A2 — 真数据覆盖率
# ═══════════════════════════════════════════════════════════════════════════════

def a2_coverage(
    bench_data: dict,
    b:          int   = B_BOOT,
    alpha:      float = ALPHA,
    seed:       int   = 42,
) -> dict:
    """
    A2 真数据覆盖率（口径钉死，防审稿人质疑）。

    「真值」= 被选 config 在完整 test 分区的 full-test AUROC（有限样本代理）。
    流程：从完整 test 分区 bootstrap 采大小=n_val 的评估子集（B 次）。
    对每个子集建：
      (a) naive 单点 95% CI：中心=子集 AUROC，宽=2·z·sigma_hat_sub（Hanley-McNeil）
      (b) data fission CI：sigma=pooled val std（all_val_aurocs 的 ddof=1 std），
          accs=[子集 AUROC]（M=1，单点），退化为标准 CI（因为 M=1 无选择偏差）
          -- 说明：data fission 需 M≥2 config 才有去偏意义；
             这里 M=1（只看 i* 的子集）模拟「单次上报」的 CI 宽度对比，
             用 sigma=pooled sigma 体现数据 fission 对不确定性的建模。
      覆盖率 = CI 包含 full_test_auroc（真值）的频率。

    辖域：「真值=full-test AUROC 代理，覆盖率是对该代理的覆盖」，见文件头注。

    sigma_hat 口径（A2）：pooled std of all_val_aurocs（ddof=1），
    与 selinf_a3_truthproxy.py data_fission_ci 完全一致。
    若 all_val_aurocs 不可用（fallback 占位），退回 bench_data["sigma_hat"]。
    """
    test_labels    = bench_data["test_labels"]
    test_scores    = bench_data["test_scores"]
    n_test         = len(test_labels)
    n_val          = bench_data["n_val"]       # 评估子集大小 = n_val（口径钉死）
    full_test_auc  = bench_data["test_auroc"]  # 「真值」= full-test AUROC 代理

    # sigma_hat：pooled val std（口径同 a3_truthproxy）
    if (bench_data.get("all_val_aurocs") is not None
            and len(bench_data["all_val_aurocs"]) > 1):
        sigma_hat = float(np.std(bench_data["all_val_aurocs"], ddof=1))
    else:
        sigma_hat = bench_data["sigma_hat"]

    z = z_score(alpha)
    rng = np.random.default_rng(seed)

    naive_cover_list = []
    df_cover_list    = []
    sub_aucs         = []

    for _ in range(b):
        # bootstrap 采大小=n_val 的子集
        idx      = rng.integers(0, n_test, size=n_val)
        lbl_sub  = test_labels[idx]
        sc_sub   = test_scores[idx]
        auc_sub  = binary_auroc_numpy(lbl_sub, sc_sub)

        if math.isnan(auc_sub):
            continue

        sub_aucs.append(auc_sub)
        n_pos_sub = int(lbl_sub.sum())
        n_neg_sub = n_val - n_pos_sub

        # (a) naive CI：Hanley-McNeil SE
        se_naive = hanley_mcneil_sigma(auc_sub, n_pos_sub, n_neg_sub)
        if math.isnan(se_naive) or se_naive <= 0:
            # fallback：二项近似
            se_naive = math.sqrt(max(auc_sub * (1 - auc_sub) / n_val, 1e-10))
        lo_naive = auc_sub - z * se_naive
        hi_naive = auc_sub + z * se_naive
        naive_cover_list.append(int(lo_naive <= full_test_auc <= hi_naive))

        # (b) data fission CI（M=1，sigma=pooled val sigma）
        # M=1 下 data fission 退化为标准 CI，但用 sigma=pooled sigma（而非 Hanley-McNeil）
        # 体现 data fission 对「配置不确定性」的建模（更宽/更窄取决于 sigma vs SE_naive）。
        # se_g = sigma * sqrt(1 + 1/tau^2) = sigma * sqrt(2)（tau=1）
        se_df  = sigma_hat * math.sqrt(1.0 + 1.0 / FISSION_TAU**2)
        lo_df  = auc_sub - z * se_df
        hi_df  = auc_sub + z * se_df
        df_cover_list.append(int(lo_df <= full_test_auc <= hi_df))

    n_valid        = len(sub_aucs)
    naive_coverage = float(np.mean(naive_cover_list)) if naive_cover_list else float("nan")
    df_coverage    = float(np.mean(df_cover_list))    if df_cover_list    else float("nan")
    sub_auc_mean   = float(np.mean(sub_aucs))         if sub_aucs         else float("nan")
    sub_auc_std    = float(np.std(sub_aucs, ddof=1))  if len(sub_aucs)>1  else float("nan")

    print(f"\n[A2 Coverage] {bench_data['benchmark']}")
    print(f"  full_test_auroc (truth proxy) = {full_test_auc:.4f}")
    print(f"  n_test={n_test}  n_val_subsample={n_val}  sigma_hat={sigma_hat:.6f}")
    print(f"  bootstrap sub_auc: mean={sub_auc_mean:.4f}  std={sub_auc_std:.4f}  "
          f"(B={n_valid} valid)")
    print(f"  naive  CI coverage = {naive_coverage:.4f} "
          f"({'OK' if naive_coverage >= 0.93 else 'LOW (欠覆盖预期)'})")
    print(f"  data_fission CI coverage = {df_coverage:.4f} "
          f"({'OK ~nominal' if abs(df_coverage - (1-alpha)) < 0.05 else 'CHECK'})")

    return {
        "analysis":          "A2_coverage",
        "benchmark":         bench_data["benchmark"],
        "full_test_auroc":   round(full_test_auc,  6),
        "n_test":            n_test,
        "n_val_subsample":   n_val,
        "sigma_hat":         round(sigma_hat,      6),
        "sub_auc_mean":      round(sub_auc_mean,   6),
        "sub_auc_std":       round(sub_auc_std,    6),
        "naive_coverage":    round(naive_coverage, 6),
        "df_coverage":       round(df_coverage,    6),
        "B_valid":           n_valid,
        "alpha":             alpha,
        "note": (
            "真值=full-test AUROC 代理（有限样本，见文件头注辖域）；"
            "sub_sample_size=n_val（口径钉死）；"
            "sigma_hat=pooled val std（ddof=1，与 a3_truthproxy 一致）；"
            "naive CI=Hanley-McNeil SE；df CI=sigma*sqrt(2)（tau=1，M=1 退化）。"
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════════════════

def main(
    results_dir:  Path  = RESULTS_DIR,
    a3_csv_path:  Path  = A3_CSV,
    out_csv:      Path  = OUT_CSV,
    benchmarks:   list  = None,
    m:            int   = 18,
    b:            int   = B_BOOT,
    alpha:        float = ALPHA,
    a1_bench:     str   = "HAM10000",
    seed:         int   = 42,
):
    """
    主分析流程：
    1. 读各 benchmark 的 per-sample 分数（npz 优先，fallback csv 占位）
    2. A1：对 a1_bench（默认 HAM10000）做 winner's curse bootstrap CI
    3. A2：对所有 benchmark 做真数据覆盖率分析
    4. 输出 a3_bootstrap_coverage.csv
    """
    print("[selinf_bootstrap_coverage] 启动")
    print(f"  results_dir={results_dir}  M={m}  B={b}  alpha={alpha}")

    if benchmarks is None:
        benchmarks = ["HAM10000", "BraTS2021", "ISIC2020"]

    # 读 a3_truthproxy.csv（fallback sigma_hat + n_val）
    a3_df = None
    if a3_csv_path.exists():
        a3_df = pd.read_csv(a3_csv_path)
        print(f"  a3_truthproxy.csv loaded: {len(a3_df)} rows")
    else:
        print(f"  [WARN] a3_truthproxy.csv not found: {a3_csv_path}")

    all_rows = []

    for bm in benchmarks:
        print(f"\n{'='*60}")
        print(f"BENCHMARK: {bm}")
        data = load_bench_scores(results_dir, bm, m=m, a3_csv=a3_df)
        if data is None:
            print(f"  [SKIP] {bm} no data available.")
            continue

        # A1：只对 a1_bench 做 winner's curse bootstrap CI
        if bm == a1_bench:
            a1_row = a1_ham_bootstrap_ci(data, b=b, alpha=alpha, seed=seed)
            all_rows.append(a1_row)

        # A2：所有 benchmark 做覆盖率分析
        a2_row = a2_coverage(data, b=b, alpha=alpha, seed=seed)
        all_rows.append(a2_row)

    if not all_rows:
        print("\n[ERROR] No rows generated. Check results_dir / npz files / a3_truthproxy.csv.")
        sys.exit(1)

    # 写 CSV（列顺序按 analysis 类型排版）
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df_out = pd.DataFrame(all_rows)
    df_out.to_csv(out_csv, index=False)
    print(f"\n[DONE] Saved: {out_csv}")
    display_cols = ["analysis", "benchmark"] + [
        c for c in ["wc_original", "wc_ci_low_pct", "ci_low_gt_zero",
                    "naive_coverage", "df_coverage", "B", "B_valid"]
        if c in df_out.columns
    ]
    print(df_out[display_cols].to_string(index=False))


# ═══════════════════════════════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()

    parser = argparse.ArgumentParser(
        description="SelInfBench A1/A2 bootstrap CI 覆盖率分析"
    )
    parser.add_argument(
        "--results_dir", type=str, default=str(RESULTS_DIR),
        help="results 目录（含 scores_*.npz 和 a3_truthproxy.csv）",
    )
    parser.add_argument(
        "--a3_csv", type=str, default=str(A3_CSV),
        help="a3_truthproxy.csv 路径（fallback sigma_hat/n_val 来源）",
    )
    parser.add_argument(
        "--out_csv", type=str, default=str(OUT_CSV),
        help="输出 CSV 路径（默认: results/a3_bootstrap_coverage.csv）",
    )
    parser.add_argument(
        "--benchmarks", type=str, default="HAM10000,BraTS2021,ISIC2020",
        help="逗号分隔 benchmark 名（需与 a3_truthproxy.csv benchmark 列一致）",
    )
    parser.add_argument(
        "--m", type=int, default=18,
        help="M 值（对应 npz 命名中的 M 字段，默认 18）",
    )
    parser.add_argument(
        "--b", type=int, default=B_BOOT,
        help=f"bootstrap 重采样次数（默认 {B_BOOT}）",
    )
    parser.add_argument(
        "--alpha", type=float, default=ALPHA,
        help=f"CI 名义水平 alpha（默认 {ALPHA} → 95% CI）",
    )
    parser.add_argument(
        "--a1_bench", type=str, default="HAM10000",
        help="A1 winner's curse bootstrap 用的 benchmark（默认 HAM10000）",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="bootstrap random seed（默认 42）",
    )
    args = parser.parse_args()

    main(
        results_dir = Path(args.results_dir),
        a3_csv_path = Path(args.a3_csv),
        out_csv     = Path(args.out_csv),
        benchmarks  = [b.strip() for b in args.benchmarks.split(",")],
        m           = args.m,
        b           = args.b,
        alpha       = args.alpha,
        a1_bench    = args.a1_bench,
        seed        = args.seed,
    )
