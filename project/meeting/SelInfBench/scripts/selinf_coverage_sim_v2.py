"""
selinf_coverage_sim_v2.py — SelInfBench Gate1 合成覆盖率模拟 v2（bug 修正版）
服务: SelInfBench (selinf)，lever = winner's curse 校正有效证据

=== 修正旧版两个致命 bug ===
Bug1 target 错配：旧版 naive CI 中心=sweep 均值、宽=σ/√M（均值 SE），
     覆盖目标本应是 mu_{i*}（被选者真值），不是 sweep 均值。
Bug2 naive 口径错：naive 应对被选 config 建「单点 CI」：
     中心 = acc_{i*}（被选观测值，winner's curse 偏高），
     宽   = 2z·σ（单观测 SE，不是 σ/√M 均值 SE）。

=== 正确设定 ===
协议统一：datafission 在 f 信道选 i*_f，三种方法全部对准同一 target：
  target = mu_{i*_f}（被选 config 的真值，可能比 sweep 均值高 = winner's curse）

三种 CI：
  1. naive          中心=acc_{i*_f}，宽=2z·σ（单点 SE，忽略选择偏差）
  2. datafission    中心=g_{i*_f}，  宽=2z·σ·√(1+1/τ²)（Leiner+JASA2023）
  3. sqrtM_invalid  中心=acc_{i*_f}，宽=2z·σ·√M（旧 baseline，inflation 倍数固定）

=== 核心扫描维度：σ_mu_ratio = σ_mu / σ ===
  σ_mu 小→mu 挤在一起→选择由噪声驱动→winner's curse 强→naive 应破裂
  σ_mu 大→真最好者明显→winner's curse 弱→naive 也不破裂
  这个 ratio 扫描是核心：验「gap 来自 winner's curse 而非 artifact」

输出: results/coverage_sim_v2.csv
  列: sigma_mu_ratio, M, method, coverage, mean_point_bias, mean_ci_width, n_rep

GO/NO-GO 判决（末尾打印）：
  GO  = 小 σ_mu_ratio（0/0.5）下 naive<0.90 AND datafission≥0.93
        且 gap 随 σ_mu_ratio 增大消失（大 ratio 下 naive 也回 0.95 附近）
  NO-GO = 任何 ratio 下 naive 都≥0.90 → winner's curse 测不出

Windows 规范：纯 numpy，无 torch/scipy，if __name__=='__main__'包主逻辑，
             正斜杠路径，np.random.default_rng(seed) 固定种子
"""

import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd

# ── 输出路径 ────────────────────────────────────────────────────────────────────
OUT_DIR = Path("D:/YJ-Agent/project/meeting/SelInfBench/results")
OUT_CSV = OUT_DIR / "coverage_sim_v2.csv"

# ── 默认实验参数 ────────────────────────────────────────────────────────────────
N_REP       = 2000        # 重复次数（≥2000，SE<0.011）
SIGMA       = 0.02        # 单 config 观测噪声 std（固定）
ALPHA       = 0.05        # 显著水平
FISSION_TAU = 1.0         # data fission τ（Leiner+ 默认）
SEED        = 42

# σ_mu_ratio = σ_mu / σ：0→全等 config，∞→真最好者完全显现
SIGMA_MU_RATIO_GRID = [0.0, 0.5, 1.0, 2.0, 5.0]
M_GRID              = [4, 18, 36]


# ═══════════════════════════════════════════════════════════════════════════════
# z_score（纯 math.erf，禁 scipy.stats → OMP Error #15）
# ═══════════════════════════════════════════════════════════════════════════════

def z_score(alpha: float) -> float:
    """N(0,1) upper alpha/2 quantile，A&S 26.2.17 初始猜+Newton 迭代，精度<1e-10。"""
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
# 单格模拟（向量化，N_rep 维并行）
# ═══════════════════════════════════════════════════════════════════════════════

def sim_one_cell(
    M: int,
    sigma_mu: float,
    sigma: float,
    n_rep: int,
    alpha: float,
    tau: float,
    rng: np.random.Generator,
) -> dict:
    """
    单 (M, sigma_mu_ratio) 格模拟。

    正确设计（修正旧版两 bug）：
    1. datafission 协议在 f 信道选 i*_f
    2. 三种方法 target 统一 = mu_{i*_f}（被选 config 真值）
    3. naive CI 中心=acc_{i*_f}（单点，winner's curse 偏高），SE=σ（单点），宽=2z·σ
    4. datafission CI 中心=g_{i*_f}，SE=σ·√(1+1/τ²)，宽=2z·σ·√(1+1/τ²)
    5. sqrtM CI 中心=acc_{i*_f}，宽=2z·σ·√M（invalid inflation baseline）

    Returns: dict keyed by method → {coverage, mean_point_bias, mean_ci_width}
    """
    z = z_score(alpha)

    # ── 生成真值 mu_i ~ N(0.72, sigma_mu²)，shape=(n_rep, M) ──────────────────
    mu0  = 0.72
    if sigma_mu > 0:
        mu_true = rng.normal(mu0, sigma_mu, size=(n_rep, M))  # (n_rep, M)
    else:
        # sigma_mu=0：所有 config 真值完全相等，winner's curse 纯噪声驱动
        mu_true = np.full((n_rep, M), mu0, dtype=np.float64)

    # ── 观测 acc_i = mu_i + ε_i，ε~N(0,σ²) ──────────────────────────────────
    acc_obs = mu_true + rng.normal(0.0, sigma, size=(n_rep, M))  # (n_rep, M)

    # ── Data fission：注入 Z~N(0,σ²)，f 信道选 i*_f ──────────────────────────
    Z_fis   = rng.normal(0.0, sigma, size=(n_rep, M))        # (n_rep, M)
    f_chan  = acc_obs + tau * Z_fis                           # f 信道（选择用）
    g_chan  = acc_obs - Z_fis / tau                           # g 信道（推断用）

    i_star  = np.argmax(f_chan, axis=1)                       # (n_rep,) 统一选择索引
    rep_idx = np.arange(n_rep)

    # ── 统一 target：mu_{i*_f}（被选 config 真值）────────────────────────────
    mu_sel  = mu_true[rep_idx, i_star]                        # (n_rep,)  ← BUG1修正
    acc_sel = acc_obs[rep_idx, i_star]                        # (n_rep,) 被选观测值
    g_star  = g_chan[rep_idx, i_star]                         # (n_rep,) datafission 推断值

    # ── 1. Naive CI（BUG2修正：单点 SE=σ，中心=acc_sel，对准 winner's curse）──
    # 旧版用 mean_acc + σ/√M → 中心偏低+宽度过窄，假装覆盖率极差；
    # 正确：对被选 config 建单点 CI，winner's curse 偏高显现在中心 acc_sel > mu_sel
    naive_low  = acc_sel - z * sigma                          # 中心=acc_sel（偏高），宽=2z·σ
    naive_high = acc_sel + z * sigma
    naive_cov  = float(((naive_low <= mu_sel) & (mu_sel <= naive_high)).mean())
    naive_width = 2.0 * z * sigma
    # point bias：E[acc_sel - mu_sel]，winner's curse 下为正
    naive_bias  = float((acc_sel - mu_sel).mean())            # (n_rep,)均值

    # ── 2. Data fission CI（Leiner+ JASA2023，已正确，三目标统一后无 bug）───
    se_g   = sigma * math.sqrt(1.0 + 1.0 / tau**2)           # σ·√(1+1/τ²)
    df_low  = g_star - z * se_g
    df_high = g_star + z * se_g
    df_cov  = float(((df_low <= mu_sel) & (mu_sel <= df_high)).mean())
    df_width = 2.0 * z * se_g
    df_bias  = float((g_star - mu_sel).mean())                # 应≈0，去偏验证

    # ── 3. √M invalid baseline（CI 中心=acc_sel，宽×√M）─────────────────────
    sqrtm_width = 2.0 * z * sigma * math.sqrt(M)
    sqrtm_low  = acc_sel - sqrtm_width / 2.0
    sqrtm_high = acc_sel + sqrtm_width / 2.0
    sqrtm_cov  = float(((sqrtm_low <= mu_sel) & (mu_sel <= sqrtm_high)).mean())
    sqrtm_bias  = float((acc_sel - mu_sel).mean())            # 同 naive（中心相同）

    return {
        "naive": {
            "coverage":         naive_cov,
            "mean_point_bias":  naive_bias,
            "mean_ci_width":    naive_width,
        },
        "datafission": {
            "coverage":         df_cov,
            "mean_point_bias":  df_bias,
            "mean_ci_width":    df_width,
        },
        "sqrtM_invalid": {
            "coverage":         sqrtm_cov,
            "mean_point_bias":  sqrtm_bias,
            "mean_ci_width":    sqrtm_width,
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# GO/NO-GO 判决逻辑
# ═══════════════════════════════════════════════════════════════════════════════

def go_nogo_verdict(df_out: pd.DataFrame) -> str:
    """
    GO 条件（三条全满足）：
      C1: 小 σ_mu_ratio（0 或 0.5）下 naive 覆盖 < 0.90（winner's curse 真破坏有效性）
      C2: 小 σ_mu_ratio（0 或 0.5）下 datafission 覆盖 ≥ 0.93（真修回）
      C3: 大 σ_mu_ratio（≥ 2.0）下 naive 覆盖 ≥ 0.90（gap 来自 winner's curse 非 artifact）
    NO-GO: 任何 σ_mu_ratio 下 naive 都≥0.90 → winner's curse 合成下测不出
    """
    small_ratio = [0.0, 0.5]
    large_ratio = [2.0, 5.0]

    # C1: 小 ratio 下 naive 至少一个格 < 0.90
    small_naive = df_out[
        (df_out["method"] == "naive") & (df_out["sigma_mu_ratio"].isin(small_ratio))
    ]["coverage"]
    c1 = bool((small_naive < 0.90).any())

    # C2: 小 ratio 下 datafission 所有格 ≥ 0.93
    small_df = df_out[
        (df_out["method"] == "datafission") & (df_out["sigma_mu_ratio"].isin(small_ratio))
    ]["coverage"]
    c2 = bool((small_df >= 0.93).all())

    # C3: 大 ratio 下 naive 均值 ≥ 0.90（gap 消失）
    large_naive = df_out[
        (df_out["method"] == "naive") & (df_out["sigma_mu_ratio"].isin(large_ratio))
    ]["coverage"]
    c3 = bool(large_naive.mean() >= 0.90)

    if c1 and c2 and c3:
        return "GO"
    elif not c1:
        return "NO-GO (C1 fail: naive 覆盖从未低于0.90，winner's curse 在合成下测不出)"
    elif not c2:
        return "NO-GO (C2 fail: 小 σ_mu 下 datafission 未达 0.93，校正无效)"
    else:
        return "NO-GO (C3 fail: 大 σ_mu 下 naive 仍<0.90，gap 非 winner's curse 特异)"


# ═══════════════════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════════════════

def main(n_rep: int = N_REP, quick: bool = False, seed: int = SEED):
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if quick:
        n_rep      = 400
        m_grid     = [4, 18]
        ratio_grid = [0.0, 0.5, 2.0]
        print(f"[QUICK] n_rep={n_rep}, M={m_grid}, sigma_mu_ratio={ratio_grid}")
    else:
        m_grid     = M_GRID
        ratio_grid = SIGMA_MU_RATIO_GRID

    z = z_score(ALPHA)
    print(f"[coverage_sim_v2] n_rep={n_rep}  sigma={SIGMA}  alpha={ALPHA}  "
          f"z={z:.4f}  tau={FISSION_TAU}  seed={seed}")
    print(f"  M grid: {m_grid}")
    print(f"  sigma_mu_ratio grid: {ratio_grid}")
    print(f"  NOTE: naive CI = single-point（中心=acc_i*，宽=2z·σ）"
          f"，target=mu_i*（被选 config 真值），三方法统一 target")
    print()

    rng  = np.random.default_rng(seed)
    rows = []

    total = len(m_grid) * len(ratio_grid)
    done  = 0

    for M in m_grid:
        for ratio in ratio_grid:
            sigma_mu = ratio * SIGMA
            done += 1
            print(f"  [{done}/{total}] M={M:2d}  σ_mu/σ={ratio:.1f}  "
                  f"(σ_mu={sigma_mu:.4f})", end="  ", flush=True)

            res = sim_one_cell(
                M=M,
                sigma_mu=sigma_mu,
                sigma=SIGMA,
                n_rep=n_rep,
                alpha=ALPHA,
                tau=FISSION_TAU,
                rng=rng,
            )

            for method, stats in res.items():
                rows.append({
                    "sigma_mu_ratio": ratio,
                    "M":              M,
                    "method":         method,
                    "coverage":       round(stats["coverage"], 4),
                    "mean_point_bias":round(stats["mean_point_bias"], 6),
                    "mean_ci_width":  round(stats["mean_ci_width"], 6),
                    "n_rep":          n_rep,
                })

            # 即时打印本格
            nc = res["naive"]["coverage"]
            dc = res["datafission"]["coverage"]
            sc = res["sqrtM_invalid"]["coverage"]
            nb = res["naive"]["mean_point_bias"]
            db = res["datafission"]["mean_point_bias"]
            print(f"naive={nc:.3f}(bias={nb:+.4f})  "
                  f"datafission={dc:.3f}(bias={db:+.4f})  "
                  f"sqrtM={sc:.3f}")

    df_out = pd.DataFrame(rows)
    df_out.to_csv(OUT_CSV, index=False)
    print(f"\nSaved: {OUT_CSV}")

    # ── 关键数字摘要 ────────────────────────────────────────────────────────────
    print("\n" + "="*70)
    print("COVERAGE TABLE (按 sigma_mu_ratio 聚合，均值 across M)")
    print("="*70)
    for ratio in ratio_grid:
        sub = df_out[df_out["sigma_mu_ratio"] == ratio]
        n_str = sub[sub["method"]=="naive"]["coverage"].mean()
        d_str = sub[sub["method"]=="datafission"]["coverage"].mean()
        s_str = sub[sub["method"]=="sqrtM_invalid"]["coverage"].mean()
        nb    = sub[sub["method"]=="naive"]["mean_point_bias"].mean()
        print(f"  σ_mu/σ={ratio:.1f}:  naive={n_str:.3f}  "
              f"datafission={d_str:.3f}  sqrtM={s_str:.3f}  "
              f"naive_bias={nb:+.4f}")

    # ── winner's curse 存在性（小 ratio 下 naive bias 是否显著正）─────────────
    print("\n" + "="*70)
    print("WINNER'S CURSE POINT BIAS（naive 中心偏差，应在小 σ_mu_ratio 下显著>0）")
    print("="*70)
    for ratio in [r for r in ratio_grid if r <= 1.0]:
        sub = df_out[
            (df_out["method"] == "naive") & (df_out["sigma_mu_ratio"] == ratio)
        ]
        biases = sub["mean_point_bias"].values
        print(f"  σ_mu/σ={ratio:.1f}:  mean naive bias = "
              f"{biases.mean():+.4f}  (across M={m_grid})")

    # ── GO/NO-GO 判决 ───────────────────────────────────────────────────────────
    verdict = go_nogo_verdict(df_out)
    print("\n" + "="*70)
    print(f"GO/NO-GO VERDICT: {verdict}")
    print("="*70)

    # 补充诊断细节
    print("\n[判决依据]")
    small_naive = df_out[
        (df_out["method"] == "naive") & (df_out["sigma_mu_ratio"].isin([0.0, 0.5]))
    ]["coverage"]
    small_df_cov = df_out[
        (df_out["method"] == "datafission") & (df_out["sigma_mu_ratio"].isin([0.0, 0.5]))
    ]["coverage"]
    large_naive = df_out[
        (df_out["method"] == "naive") & (df_out["sigma_mu_ratio"].isin([2.0, 5.0]))
    ]["coverage"]
    print(f"  C1 小 σ_mu naive 覆盖: min={small_naive.min():.3f} "
          f"max={small_naive.max():.3f} (threshold <0.90)")
    print(f"  C2 小 σ_mu datafission 覆盖: min={small_df_cov.min():.3f} "
          f"max={small_df_cov.max():.3f} (threshold ≥0.93)")
    print(f"  C3 大 σ_mu naive 覆盖: mean={large_naive.mean():.3f} "
          f"(threshold ≥0.90，gap 消失=winner's curse 特异)")

    return verdict


# ═══════════════════════════════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="SelInfBench coverage simulation v2 (bug-fixed, 0 GPU)"
    )
    parser.add_argument("--n_rep", type=int, default=N_REP,
                        help=f"重复次数（默认 {N_REP}）")
    parser.add_argument("--quick", action="store_true",
                        help="快速模式: n_rep=400, M=[4,18], ratio=[0,0.5,2.0]")
    parser.add_argument("--seed", type=int, default=SEED,
                        help=f"随机种子（默认 {SEED}）")
    args = parser.parse_args()
    main(n_rep=args.n_rep, quick=args.quick, seed=args.seed)
