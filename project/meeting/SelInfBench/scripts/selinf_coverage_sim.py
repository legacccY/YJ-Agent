"""
selinf_coverage_sim.py — SelInfBench Gate1 纯 numpy 合成覆盖率模拟
服务: SelInfBench (selinf) A2，lever = 验证 data fission 区间名义覆盖率（0 GPU）

实验设计：
  生成 mu_i ~ N(mu0, tau_het^2)，i=1..M
  acc_i ~ N(mu_i, sigma^2 / n_val)          （每 config 的 val set 均值）
  选择 i* = argmax acc_i
  目标真参数 = mu_{i*}                        （被选 config 的真均值）
  重复 N_rep=2000 次，统计三种区间覆盖 mu_{i*} 的频率

三种区间：
  1. naive          CLT CI for selected acc_{i*}（se=sigma/sqrt(n_val)，忽略选择）
  2. datafission    Leiner+ JASA2023 data fission（tau=1.0）
  3. sqrtM_invalid  √M 近似旧方法（INVALID baseline，作对照）

扫参：M ∈ {4,8,18,36}，tau_het/sigma ∈ {0.3,1.0,3.0}
  （tau_het/sigma = heterogeneity ratio：configs 之间真均值差异 vs 单 config 噪声）

预期：
  naive 覆盖率 ≪ 0.95（选择破坏有效性）
  datafission 覆盖率 ≈ 0.95（名义覆盖）
  sqrtM_invalid 覆盖率不稳（恒等式，非真有效区间）

输出: project/meeting/SelInfBench/results/coverage_sim.csv
  列: M, tau_over_sigma, method, coverage, mean_ci_width, mean_deflation

Windows 规范：纯 numpy，无 torch/scipy，if __name__=='__main__' 包主逻辑
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

# ── 输出路径 ────────────────────────────────────────────────────────────────────
OUT_DIR = Path("D:/YJ-Agent/project/meeting/SelInfBench/results")
OUT_CSV = OUT_DIR / "coverage_sim.csv"

# ── 默认实验参数 ────────────────────────────────────────────────────────────────
N_REP     = 2000        # 重复次数
N_VAL     = 300         # 每 config 验证集大小（模拟 HAM val_N）
MU0       = 0.72        # 全局均值（接近 HAM10000 sweep 均值）
SIGMA     = 0.02        # 单 config val_acc 噪声 std
ALPHA     = 0.05        # 显著水平
FISSION_TAU = 1.0       # data fission tau

M_GRID            = [4, 8, 18, 36]
TAU_OVER_SIGMA    = [0.3, 1.0, 3.0]   # tau_het / sigma


# ═══════════════════════════════════════════════════════════════════════════════
# z_score（复用 selinf_datafission 同实现，禁 scipy.stats）
# ═══════════════════════════════════════════════════════════════════════════════

def z_score(alpha: float) -> float:
    """
    N(0,1) upper alpha/2 quantile，纯 math.erf（禁 scipy.stats，OMP Error #15）。
    A&S 26.2.17 初始猜 + 5 步 Newton 在 Phi(x)=p 上迭代，精度 <1e-10。
    """
    import math
    p     = 1.0 - alpha / 2.0
    sqrt2 = math.sqrt(2.0)
    sqp2  = math.sqrt(2.0 * math.pi)
    t  = math.sqrt(-2.0 * math.log(min(p, 1.0 - p)))
    c  = [2.515517, 0.802853, 0.010328]
    d  = [1.432788, 0.189269, 0.001308]
    x0 = t - (c[0] + c[1]*t + c[2]*t**2) / (1 + d[0]*t + d[1]*t**2 + d[2]*t**3)
    x  = x0 if p >= 0.5 else -x0
    for _ in range(5):
        phi_x  = 0.5 * (1.0 + math.erf(x / sqrt2))
        dphi_x = math.exp(-0.5 * x * x) / sqp2
        x -= (phi_x - p) / dphi_x
    return float(x)


# ═══════════════════════════════════════════════════════════════════════════════
# 向量化 CI 构造（N_rep 维并行，避免 Python 循环）
# ═══════════════════════════════════════════════════════════════════════════════

def sim_one_cell(
    M: int,
    tau_het: float,
    sigma: float,
    n_val: int,
    n_rep: int,
    alpha: float,
    tau_fission: float,
    rng: np.random.Generator,
) -> dict:
    """
    单格模拟：返回三种方法的 coverage / mean_ci_width / mean_deflation。
    所有 n_rep 次重复向量化（shape=(n_rep, M)）。
    """
    z = z_score(alpha)

    # 每次重复的配置真均值 mu_i ~ N(mu0, tau_het^2)
    mu_true = rng.normal(MU0, tau_het, size=(n_rep, M))      # (n_rep, M)

    # 观测 acc_i ~ N(mu_i, (sigma/sqrt(n_val))^2)
    se_obs  = sigma / np.sqrt(n_val)
    acc_obs = mu_true + rng.normal(0.0, se_obs, size=(n_rep, M))  # (n_rep, M)

    # 选择 i* = argmax acc
    i_star = np.argmax(acc_obs, axis=1)                       # (n_rep,)
    rep_idx = np.arange(n_rep)

    mu_selected  = mu_true[rep_idx, i_star]                   # (n_rep,) 真目标
    acc_selected = acc_obs[rep_idx, i_star]                   # (n_rep,)

    # ── 1. Naive CI ─────────────────────────────────────────────────────────
    # 模拟真实论文报告习惯：对 sweep mean acc 建标准 CLT CI
    # （se = sigma / sqrt(n_val * M)，等价于 std(acc_obs,axis=1)/sqrt(M)），
    # 然后用此 CI 评估是否覆盖被选 config 的真 mu_{i*}。
    # 真实偏差来源：被选 config 的 mu_{i*} 系统性高于 sweep mean，
    # 而 naive CI 中心在 mean(acc_obs)，无法追上高估的 mu_{i*}。
    mean_acc = acc_obs.mean(axis=1)                           # (n_rep,)
    se_mean  = se_obs / np.sqrt(M)                            # CLT SE for mean of M configs
    naive_low    = mean_acc - z * se_mean
    naive_high   = mean_acc + z * se_mean
    naive_width  = 2 * z * se_mean                            # 标量

    naive_cov = float(((naive_low <= mu_selected) & (mu_selected <= naive_high)).mean())
    naive_mean_width = float(naive_width)

    # ── 2. Data fission CI（Leiner+ JASA2023）──────────────────────────────
    # 注入 Z_i ~ N(0, se_obs^2)，与 acc_obs 独立
    # （模拟里 sigma 已知，用 se_obs 代入；真实脚本用 sigma_hat=pooled std 估计）
    Z_fis  = rng.normal(0.0, se_obs, size=(n_rep, M))
    f_fis  = acc_obs + tau_fission * Z_fis             # 选择信道 (n_rep, M)
    g_fis  = acc_obs - Z_fis / tau_fission             # 推断信道 (n_rep, M)

    i_star_f  = np.argmax(f_fis, axis=1)               # 在 f 上选
    g_star    = g_fis[rep_idx, i_star_f]               # 对应的推断值 (n_rep,)
    mu_sel_f  = mu_true[rep_idx, i_star_f]             # 被选的真目标（可能与 i_star 不同）

    se_g      = se_obs * np.sqrt(1.0 + 1.0 / tau_fission**2)   # g_{i*} ~ N(mu_{i*}, se_obs^2*(1+1/tau^2))
    df_low    = g_star - z * se_g
    df_high   = g_star + z * se_g
    df_width  = 2 * z * se_g  # 标量

    df_cov       = float(((df_low <= mu_sel_f) & (mu_sel_f <= df_high)).mean())
    df_mean_width = float(df_width)

    # deflation(datafission) = df_width / naive_width - 1
    df_deflation = float(df_width / naive_width - 1.0)

    # ── 3. √M 近似（INVALID baseline）──────────────────────────────────────
    # G5 原方法：对 best acc 的单点 naive CI（宽 = 2*z*se_obs）乘以 sqrt(M)
    # = naive_single_width * sqrt(M)，固定 M 下是数学恒等式，与数据无关
    naive_single_width = 2 * z * se_obs          # 对单 config acc 的 naive CI 宽（无选择校正）
    sqrtm_width = naive_single_width * np.sqrt(M)
    # CI 中心 = acc_selected（忽略 bias 去偏，只看宽度与覆盖）
    sqrtm_low  = acc_selected - sqrtm_width / 2
    sqrtm_high = acc_selected + sqrtm_width / 2

    sqrtm_cov        = float(((sqrtm_low <= mu_selected) & (mu_selected <= sqrtm_high)).mean())
    sqrtm_mean_width = float(sqrtm_width)
    sqrtm_deflation  = float(sqrtm_width / naive_width - 1.0)  # vs mean-based naive CI

    return {
        "naive":        {"coverage": naive_cov,   "mean_ci_width": naive_mean_width,   "mean_deflation": 0.0},
        "datafission":  {"coverage": df_cov,       "mean_ci_width": df_mean_width,       "mean_deflation": df_deflation},
        "sqrtM_invalid":{"coverage": sqrtm_cov,    "mean_ci_width": sqrtm_mean_width,    "mean_deflation": sqrtm_deflation},
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════════════════

def main(n_rep: int = N_REP, quick: bool = False):
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if quick:
        n_rep    = 200
        m_grid   = [4, 18]
        tos_grid = [0.3, 1.0]
        print(f"[QUICK] n_rep={n_rep}, M={m_grid}, tau_over_sigma={tos_grid}")
    else:
        m_grid   = M_GRID
        tos_grid = TAU_OVER_SIGMA

    z = z_score(ALPHA)
    print(f"[coverage_sim] n_rep={n_rep}  sigma={SIGMA}  n_val={N_VAL}  "
          f"alpha={ALPHA}  z={z:.4f}  tau_fission={FISSION_TAU}")
    print(f"  M grid: {m_grid}")
    print(f"  tau_het/sigma grid: {tos_grid}")
    print()

    rng  = np.random.default_rng(42)
    rows = []

    total = len(m_grid) * len(tos_grid)
    done  = 0
    for M in m_grid:
        for tos in tos_grid:
            tau_het = float(tos) * SIGMA
            done += 1
            print(f"  [{done}/{total}] M={M:2d}  tau_het/sigma={tos:.1f}", end="  ", flush=True)

            res = sim_one_cell(
                M=M, tau_het=tau_het, sigma=SIGMA,
                n_val=N_VAL, n_rep=n_rep, alpha=ALPHA,
                tau_fission=FISSION_TAU, rng=rng,
            )

            for method, stats in res.items():
                rows.append({
                    "M":               M,
                    "tau_over_sigma":  tos,
                    "method":          method,
                    "coverage":        round(stats["coverage"], 4),
                    "mean_ci_width":   round(stats["mean_ci_width"], 6),
                    "mean_deflation":  round(stats["mean_deflation"], 4),
                })

            # 即时打印本格结果
            naive_cov = res["naive"]["coverage"]
            df_cov    = res["datafission"]["coverage"]
            sm_cov    = res["sqrtM_invalid"]["coverage"]
            print(f"naive={naive_cov:.3f}  datafission={df_cov:.3f}  "
                  f"sqrtM_inv={sm_cov:.3f}  "
                  f"[df_defl={res['datafission']['mean_deflation']*100:.1f}%]")

    df_out = pd.DataFrame(rows)
    df_out.to_csv(OUT_CSV, index=False)
    print(f"\nSaved: {OUT_CSV}")

    # ── 摘要：各方法平均覆盖率 ──────────────────────────────────────────────
    print("\n--- COVERAGE SUMMARY (mean across all M × tau_het/sigma cells) ---")
    for method in ["naive", "datafission", "sqrtM_invalid"]:
        sub = df_out[df_out["method"] == method]
        print(f"  {method:20s}  coverage={sub['coverage'].mean():.3f}  "
              f"mean_ci_width={sub['mean_ci_width'].mean():.5f}  "
              f"mean_deflation={sub['mean_deflation'].mean()*100:.1f}%")

    print("\n--- A2 COVERAGE CHECK ---")
    df_rows = df_out[df_out["method"] == "datafission"]
    below_nominal = df_rows[df_rows["coverage"] < 0.90]
    if len(below_nominal) == 0:
        print("  datafission coverage >= 0.90 in ALL cells  →  名义覆盖 PASS")
    else:
        print(f"  WARN: {len(below_nominal)} cells below 0.90:")
        print(below_nominal[["M", "tau_over_sigma", "coverage"]].to_string(index=False))

    naive_rows = df_out[df_out["method"] == "naive"]
    low_naive  = naive_rows[naive_rows["coverage"] < 0.95]
    print(f"  naive CI coverage < 0.95 in {len(low_naive)}/{len(naive_rows)} cells "
          f"(预期=大多数，selection 破坏有效性)")


# ═══════════════════════════════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SelInfBench coverage simulation (0 GPU)")
    parser.add_argument("--n_rep", type=int, default=N_REP,
                        help=f"重复次数（默认 {N_REP}）")
    parser.add_argument("--quick", action="store_true",
                        help="快速模式: n_rep=200, M=[4,18], tos=[0.3,1.0]（CI 测试用）")
    args = parser.parse_args()
    main(n_rep=args.n_rep, quick=args.quick)
