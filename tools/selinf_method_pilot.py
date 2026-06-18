"""
selinf_method_pilot.py  —  kill-shot #2: 方法腿生死验证
服务 SelInfBench (selinf) kill-shot #2
纯 numpy/pathlib，无 torch/scipy，Windows-safe

命门问题：
  Kaggle private leaderboard = fresh holdout，冠军 private 分一次定。
  skeptic 反问：naive-on-private CI 是否已 ~95% 覆盖真值？
  若是 → private split 绕过自适应污染 → 新方法在 Kaggle 场景无必要。
  若否（某区制欠覆盖）→ 存在真方法空间。

输出：project/meeting/SelInfBench/results/method_pilot.csv
"""

import numpy as np
import pathlib
import csv

# ── 固定种子 ──────────────────────────────────────────────────────────────────
RNG_SEED = 42

# ── 输出路径 ──────────────────────────────────────────────────────────────────
OUT_CSV = pathlib.Path("D:/YJ-Agent/project/meeting/SelInfBench/results/method_pilot.csv")
OUT_CSV.parent.mkdir(parents=True, exist_ok=True)

# ── 参数扫描网格 ──────────────────────────────────────────────────────────────
# R: public 自适应提交轮数（1=无自适应；10/50=中/重度自适应）
R_GRID    = [1, 10, 50]
# n_pub: public split 样本数（越小越容易被自适应污染）
N_PUB_GRID = [200, 500, 2000]
# n_priv: private split 样本数（越小 CI 越宽，但注意覆盖率不是宽度问题）
N_PRIV_GRID = [200, 500, 2000]
# tau: 队间异质标准差（真实能力散布）
TAU_GRID  = [0.02, 0.10]
# K: 参赛队数
K = 100
# 重复次数
N_REP = 3000
# 置信水平 z
Z_95 = 1.96
# 真值分布基准（AUROC 量级，0.5 = random，0.7 = 典型医学任务）
MU0 = 0.70


def auroc_sd(n: int) -> float:
    """
    AUROC 标准误近似：
    对 balanced binary (0.5 正例率) AUC≈0.70：
      SE ≈ sqrt(AUC*(1-AUC)*(1 + (n/2-1)*Q1 + (n/2-1)*Q2)) / (n/2)
    简化高斯版：SE ≈ sqrt(AUC*(1-AUC)/n_eff)，n_eff = n/2（较保守）。
    这里用最简版：sd = sqrt(AUC*(1-AUC) / (n/2))
    """
    auc = MU0  # 近似用总体均值
    n_eff = max(n // 2, 1)
    return float(np.sqrt(auc * (1.0 - auc) / n_eff))


def run_scenario(R: int, n_pub: int, n_priv: int, tau: float,
                 rng: np.random.Generator) -> dict:
    """
    单场景 N_REP 次蒙特卡洛。
    返回三套方法的覆盖率 + 均值偏差。
    """
    sd_pub  = auroc_sd(n_pub)
    sd_priv = auroc_sd(n_priv)

    # ── 生成真实能力 theta[rep, k] ─────────────────────────────────────────
    theta = rng.normal(MU0, tau, size=(N_REP, K))          # (N_REP, K)

    # ── PUBLIC: R 轮自适应提交，保留最优 ─────────────────────────────────────
    # 每轮观测 obs_r[rep, k, r] = theta + noise(sd_pub)
    obs_pub = rng.normal(0.0, sd_pub, size=(N_REP, K, R))  # noise
    obs_pub = theta[:, :, np.newaxis] + obs_pub             # (N_REP, K, R)
    public_best = obs_pub.max(axis=2)                       # (N_REP, K)  自适应过拟合

    # ── PRIVATE: 一次性 fresh 观测 ───────────────────────────────────────────
    private_obs = theta + rng.normal(0.0, sd_priv, size=(N_REP, K))  # (N_REP, K)

    # ── 选 winner = argmax public_best ───────────────────────────────────────
    winner_idx = np.argmax(public_best, axis=1)             # (N_REP,)
    rep_idx    = np.arange(N_REP)

    theta_winner   = theta[rep_idx, winner_idx]             # (N_REP,) 真值
    pub_best_w     = public_best[rep_idx, winner_idx]       # winner 的 public best
    priv_obs_w     = private_obs[rep_idx, winner_idx]       # winner 的 private 观测

    # ── 方法 1: naive-on-public ──────────────────────────────────────────────
    # CI 中心 = pub_best_w，half-width = Z * sd_pub
    # 注意 sd_pub 是单轮的；best-of-R 让 pub_best_w 系统性偏高（winner's curse）
    lo1 = pub_best_w - Z_95 * sd_pub
    hi1 = pub_best_w + Z_95 * sd_pub
    cov1 = float(np.mean((theta_winner >= lo1) & (theta_winner <= hi1)))
    bias1 = float(np.mean(pub_best_w - theta_winner))

    # ── 方法 2: naive-on-private ─────────────────────────────────────────────
    # CI 中心 = priv_obs_w，half-width = Z * sd_priv
    # private 观测独立于 public selection 过程 → 理论上应该 ~95%
    lo2 = priv_obs_w - Z_95 * sd_priv
    hi2 = priv_obs_w + Z_95 * sd_priv
    cov2 = float(np.mean((theta_winner >= lo2) & (theta_winner <= hi2)))
    bias2 = float(np.mean(priv_obs_w - theta_winner))

    # ── 方法 3: public-only 条件推断（无 private 时的校正需求基线）───────────
    # 若平台只有 public（= 医学 benchmark HP sweep 场景），
    # 用最简 Bonferroni 校正（保守）：z_bonf = Phi^{-1}(1 - alpha/(2*K*R))
    alpha = 0.05
    bonf_level = 1.0 - alpha / (2.0 * K * R)
    bonf_level = min(bonf_level, 1.0 - 1e-10)  # 防越界
    # 手动 quantile（避免 scipy）：用牛顿法求 normal quantile
    z_bonf = _normal_quantile(bonf_level)
    lo3 = pub_best_w - z_bonf * sd_pub
    hi3 = pub_best_w + z_bonf * sd_pub
    cov3 = float(np.mean((theta_winner >= lo3) & (theta_winner <= hi3)))
    bias3 = float(np.mean(pub_best_w - theta_winner))

    return {
        "naive_pub":   (cov1, bias1),
        "naive_priv":  (cov2, bias2),
        "bonf_pub":    (cov3, bias3),
    }


def _normal_quantile(p: float, tol: float = 1e-8) -> float:
    """
    标准正态 quantile，纯 numpy 牛顿法（避免 scipy）。
    用 rational approximation 做初值（Abramowitz & Stegun 26.2.17）。
    """
    if p <= 0.0:
        return -1e10
    if p >= 1.0:
        return 1e10
    # 初值：rational approx（误差 < 4.5e-4）
    if p < 0.5:
        t = np.sqrt(-2.0 * np.log(p))
        c = [2.515517, 0.802853, 0.010328]
        d = [1.432788, 0.189269, 0.001308]
        x0 = -(t - (c[0] + c[1]*t + c[2]*t**2) / (1 + d[0]*t + d[1]*t**2 + d[2]*t**3))
    else:
        t = np.sqrt(-2.0 * np.log(1.0 - p))
        c = [2.515517, 0.802853, 0.010328]
        d = [1.432788, 0.189269, 0.001308]
        x0 = t - (c[0] + c[1]*t + c[2]*t**2) / (1 + d[0]*t + d[1]*t**2 + d[2]*t**3)
    # 牛顿 polish（2 步足够）
    x = float(x0)
    for _ in range(5):
        fx  = _normal_cdf(x) - p
        fpx = np.exp(-0.5 * x**2) / np.sqrt(2.0 * np.pi)
        x  -= fx / fpx
    return x


def _normal_cdf(x: float) -> float:
    """标准正态 CDF，用 erf 恒等式（numpy 有 erf）。"""
    return 0.5 * (1.0 + _erf(x / np.sqrt(2.0)))


def _erf(x):
    """numpy 没有直接的 erf，用 Horner 多项式近似（Abramowitz & Stegun 7.1.26，最大误差 1.5e-7）。"""
    a = np.abs(x)
    t = 1.0 / (1.0 + 0.3275911 * a)
    poly = t * (0.254829592 +
           t * (-0.284496736 +
           t * (1.421413741 +
           t * (-1.453152027 +
           t * 1.061405429))))
    result = 1.0 - poly * np.exp(-a * a)
    return float(np.where(x >= 0, result, -result))


def main():
    rng = np.random.default_rng(RNG_SEED)

    rows = []
    total = len(R_GRID) * len(N_PUB_GRID) * len(N_PRIV_GRID) * len(TAU_GRID)
    done = 0

    print(f"[method_pilot] K={K}, N_REP={N_REP}, scenarios={total}")
    print(f"{'R':>4} {'n_pub':>6} {'n_priv':>6} {'tau':>5}  "
          f"{'naive_pub':>10} {'naive_priv':>11} {'bonf_pub':>9}")
    print("-" * 65)

    for tau in TAU_GRID:
        for R in R_GRID:
            for n_pub in N_PUB_GRID:
                for n_priv in N_PRIV_GRID:
                    res = run_scenario(R, n_pub, n_priv, tau, rng)

                    for method, (cov, bias) in res.items():
                        rows.append({
                            "R":        R,
                            "n_pub":    n_pub,
                            "n_priv":   n_priv,
                            "tau":      tau,
                            "K":        K,
                            "method":   method,
                            "coverage": round(cov, 4),
                            "mean_bias": round(bias, 5),
                            "n_rep":    N_REP,
                        })

                    cov_pub  = res["naive_pub"][0]
                    cov_priv = res["naive_priv"][0]
                    cov_bonf = res["bonf_pub"][0]
                    print(f"R={R:>2} n_pub={n_pub:>4} n_priv={n_priv:>4} tau={tau:.2f}  "
                          f"naive_pub={cov_pub:.3f}  naive_priv={cov_priv:.3f}  bonf_pub={cov_bonf:.3f}")

                    done += 1

    # ── 写 CSV ────────────────────────────────────────────────────────────────
    fieldnames = ["R", "n_pub", "n_priv", "tau", "K", "method", "coverage", "mean_bias", "n_rep"]
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n[method_pilot] CSV → {OUT_CSV}")

    # ── KILL-SHOT 判读 ────────────────────────────────────────────────────────
    _print_killshot(rows)


def _print_killshot(rows: list):
    """
    判读逻辑：
      - 对每个配置看 naive_priv 覆盖率。
      - DEAD 条件：所有配置 naive_priv ≥ 0.93。
      - ALIVE 条件：存在配置 naive_priv < 0.90。
      - 中间地带：0.90 ≤ min < 0.93（边缘，需更多实验）。
    额外关注：R=50（重度自适应）下 naive_pub 是否深度欠覆盖。
    """
    priv_rows   = [r for r in rows if r["method"] == "naive_priv"]
    pub_rows    = [r for r in rows if r["method"] == "naive_pub"]

    priv_covs   = [r["coverage"] for r in priv_rows]
    min_priv    = min(priv_covs)
    max_priv    = max(priv_covs)
    mean_priv   = sum(priv_covs) / len(priv_covs)

    pub_covs    = [r["coverage"] for r in pub_rows]
    min_pub     = min(pub_covs)

    # R=50 子集
    r50_priv    = [r["coverage"] for r in priv_rows if r["R"] == 50]
    r50_pub     = [r["coverage"] for r in pub_rows  if r["R"] == 50]
    min_r50_priv = min(r50_priv) if r50_priv else float("nan")
    min_r50_pub  = min(r50_pub)  if r50_pub  else float("nan")

    # small n_priv 子集（n_priv=200, R=50）
    worst_priv = min(
        r["coverage"] for r in priv_rows if r["R"] == 50 and r["n_priv"] == 200
    )

    print("\n" + "=" * 65)
    print("KILL-SHOT #2 判读：naive-on-private 覆盖率分析")
    print("=" * 65)
    print(f"  naive_priv 覆盖：min={min_priv:.3f}  max={max_priv:.3f}  mean={mean_priv:.3f}")
    print(f"  naive_pub  覆盖：min={min_pub:.3f}  （winner's curse 验证）")
    print(f"  [R=50]  naive_priv min={min_r50_priv:.3f}  naive_pub min={min_r50_pub:.3f}")
    print(f"  [R=50, n_priv=200]  naive_priv={worst_priv:.3f}  ← 最坏区制")
    print()

    if min_priv >= 0.93:
        verdict = "方法腿 DEAD"
        explanation = (
            "所有扫参配置 naive-on-private 覆盖均 ≥ 0.93。\n"
            "  → private split 独立于 public 自适应选择，fresh holdout 天然绕过 winner's curse。\n"
            "  → Kaggle 场景下新方法无必要。\n"
            "  → 退回：(a) 纯 public leaderboard 场景 OR (b) 描述性审计工具 / D&B 方向。"
        )
    elif min_priv < 0.90:
        verdict = "方法腿 ALIVE"
        bad_configs = [r for r in priv_rows if r["coverage"] < 0.90]
        explanation = (
            f"发现 {len(bad_configs)} 个配置 naive-on-private < 0.90：\n" +
            "\n".join(
                f"    R={r['R']} n_pub={r['n_pub']} n_priv={r['n_priv']} tau={r['tau']} → cov={r['coverage']:.3f}"
                for r in bad_configs[:5]
            ) + "\n"
            "  → 存在真实方法空间（private 未完全免疫或信息泄漏）。\n"
            "  → 需进一步验证泄漏机制（ensemble 探针 / 元特征利用）。"
        )
    else:
        verdict = "方法腿 边缘（需更多证据）"
        explanation = (
            f"naive-on-private min={min_priv:.3f}，介于 [0.90, 0.93)。\n"
            "  → 单凭本 pilot 无法决定性排除/确认。\n"
            "  → 建议扩大 N_REP + 加入 ensemble 探针场景（间接污染）。"
        )

    print(f"  *** {verdict} ***")
    print()
    print(explanation)
    print()

    # 额外：public-only 场景（无 private）
    bonf_rows = [r for r in rows if r["method"] == "bonf_pub"]
    bonf_r50  = [r["coverage"] for r in bonf_rows if r["R"] == 50]
    if bonf_r50:
        mean_bonf_r50 = sum(bonf_r50) / len(bonf_r50)
        print(f"  [参考] bonf_pub R=50 mean覆盖={mean_bonf_r50:.3f}")
        print(f"  → 若平台只有 public（医学 HP sweep 场景），Bonferroni 校正{'有效' if mean_bonf_r50 >= 0.93 else '过于保守但'}覆盖目标；")
        print(f"     精确条件推断（SelInfBench 核心方法）在此场景仍有价值（Bonferroni 过保守）。")
    print("=" * 65)


if __name__ == "__main__":
    main()
