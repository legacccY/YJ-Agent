# -*- coding: utf-8 -*-
"""
04_dependence_demo.py — 命门 C3：依赖让 naive（假设独立的）多重检验失效吗？
============================================================================
回答的 Q（KS-3 承重前提）：
  多个告警器同窗触发时，把「联合判定该窗是否真事件」建成**多重检验/证据合并**问题。
  告警器彼此**正相关/依赖**（02 phi 实测 0.4 级，见 KS3_PILOT_REPORT）。
  问：假设独立的合并法（Fisher）在名义 α 下**实际**误报是否超标？而任意依赖仍 valid 的
  e-value 合并（Vovk–Wang 均值 e）是否真把误报控在 α？
  -> 独立法 empirical_error > α + e-value 控在 α  => 依赖稳健联合校准**有价值** => C3 GO；
     独立法本就控在 α                          => e-value 无增量               => C3 塌。

【为什么用「证据合并」框架而非跨窗 FDR】（诚实的统计站位）
  - Bonferroni（min-p × K）在**任意依赖**下都控 FWER -> 它不会失效（作诚实对照，防「所有 naive 都塌」的稻草人）。
  - BH-FDR 在 **PRDS/正依赖**下仍控 FDR（Benjamini–Yekutieli 2001）-> 真实告警是正相关，
    BH 在跨窗 FDR 上**不会明显失效** -> 跨窗 FDR 不是依赖真正咬人的地方。
  - **正依赖真正让 naive 失效的地方 = 合并多个相关告警的证据成一个窗决定**：
    Fisher 合并（-2Σln p ~ χ²_{2K}）假设 p 相互独立；正相关 p 使 Fisher 组合统计量方差>名义
    -> 零假设下过度拒绝 -> anti-conservative -> empirical Type-I > α。
    e-value 合并（Vovk–Wang 2021：**e-value 的算术均值在任意依赖下仍是 valid e-value**）
    经 Markov 阈值 1/α -> Type-I ≤ α，与依赖无关。
  => 本 demo 把 KS-3 的「同窗多告警 -> 单窗真事件判定」建成合并检验，正是依赖咬人的正确位置。

【统计构造 + 全部假设（显式，供 verifier / skeptic 核）】
  设某共触发窗内有 K 个活跃告警，各出一个针对自身零假设「该告警是假报/artifact」的 p 值。
  - 零假设成立（窗实为全假 artifact）时，各 p_k 边际服从 Uniform(0,1)（p 值定义）。            [假设 A]
  - 告警器依赖 -> p_k **跨告警器正相关**。用**高斯 copula**建相关：潜变量 z~N(0,Σ)、
    Σ=等相关(ρ)，p_k = 1-Φ(z_k)（上尾=对零假设的证据）。ρ 由 02 实测 phi 中位标定。       [假设 B]
    高斯 copula 只用于把「实测正相关」注入 p 值联合分布；边际仍精确 Uniform（Φ 变换保证）。
  - **本 demo 是半合成 pilot**：依赖结构 ρ 与合并个数 K 取自真实派生告警（或 report 缺省），
    但「零假设下 p 值」由 Monte-Carlo 模拟（真数据里没有非循环的 per-告警检验统计量，
    唯一的真/假信号=弱代理时长本身，直接拿来当统计量会循环 -> 故模拟零假设层）。         [诚实边界 R8+]
    -> 结论是「依赖是否破坏名义误报控制」的机制级 demo，非完整方法学证明。

  三法（都在名义 α 下判「拒绝零假设 = 判该窗为真事件」）：
    (1) fisher_indep  : X=-2Σ ln p_k；p_F=P(χ²_{2K}≥X)；拒绝 iff p_F≤α。  **假设独立**（Fisher 1932）。
                        χ²_{2K} 生存函数用偶数自由度闭式：sf=e^{-x/2}Σ_{j<K}(x/2)^j/j!（纯 numpy，无 scipy）。
    (2) bonferroni    : 拒绝 iff min_k p_k ≤ α/K。   **任意依赖**控 FWER（Boole 不等式）。诚实对照。
    (3) evalue_mean   : e_k = p→e 校准子 (1/2)·p_k^{-1/2}（Vovk–Wang 2021 p-to-e 校准，κ=1/2，
                        零假设下 E[e]=∫₀¹0.5 p^{-1/2}dp=1，valid）；merged = mean_k e_k；
                        拒绝 iff merged ≥ 1/α。 **任意依赖**下 Type-I≤α（Vovk–Wang：均值 e 仍 valid + Markov）。
  经验 Type-I = 全零假设 MC 试验中「误拒」的比例（所有零假设为真 -> 任何拒绝=误报）。
  controlled = empirical_error ≤ α + MC 容差（±1.5·√(α(1-α)/n_trials)，MC 噪声带）。

参考出处：
  - Vovk & Wang (2021), "E-values: Calibration, combination and applications", Ann. Statist.
      -> 均值 e-value 任意依赖 valid；p→e 校准子族 e=κ p^{κ-1}（κ∈(0,1)）。
  - Fisher (1932), Statistical Methods for Research Workers -> -2Σln p ~ χ²_{2K}（独立）。
  - Benjamini & Yekutieli (2001) -> BH 在 PRDS 下控 FDR（解释为何不用跨窗 FDR 当主 demo）。
  - Wang & Ramdas (2022), "False discovery rate control with e-values", JRSS-B
      -> e-BH 任意依赖控 FDR（若日后要做跨窗 FDR 版本的正确 naive-替代，用它；本 pilot 用合并框架）。
  # TODO(researcher/主线): 若要引 report 的精确 phi 中位替换缺省 ρ，核 02 cotrigger_stats.csv 后填。

输出 dependence_demo.csv，列：
  method, alpha, nominal, empirical_error, controlled(bool),
  dependence, rho, k_merged, n_trials, source_rho
纯 numpy + pandas（+ 可选 wfdb 派生 ρ/K）。Windows：pathlib/utf-8/无硬编码盘符。主线跑。含 --smoke。
**本模块不自跑；写完交主线跑。**
"""
import argparse
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from alarm_thresholds import COTRIGGER_WINDOW_S

THIS = Path(__file__).resolve()
OUT_DIR = THIS.parent
DEFAULT_PN_DIR = "mimic3wdb-matched/1.0"

# 缺省 ρ / K 来源：KS3_PILOT_REPORT phi 中位（HR|RESP≈0.41、ABPsys|SpO2≈0.39）-> ρ≈0.4；
# 共触发窗常见 2~3 类活跃 -> K=3。--records 提供时改由真实数据标定（见 estimate_dependence_from_records）。
DEFAULT_RHO = 0.4          # TODO 核 02 cotrigger_stats.csv 精确 phi 中位后可替换
DEFAULT_K = 3              # TODO 核 02 共触发窗活跃类中位数后可替换


# --------------------------------------------------------------------------- #
# 纯 numpy 数值工具（避 scipy.stats -> 避 OMP 冲突，且匹配 alarm_derive 手写风格）
# --------------------------------------------------------------------------- #
def _norm_cdf(z):
    """标准正态 CDF Φ(z)，用 erf（纯 numpy，逐元素）。"""
    return 0.5 * (1.0 + np.vectorize(math.erf)(z / math.sqrt(2.0)))


def chi2_sf_even(x, k):
    """
    χ² 生存函数 P(χ²_{2k} ≥ x)，自由度=2k（偶数）闭式：
        sf = e^{-x/2} · Σ_{j=0}^{k-1} (x/2)^j / j!
    （整数 shape=k 的上不完全 Gamma 闭式；纯 numpy，无 scipy）。x 可为向量。
    """
    x = np.asarray(x, dtype=float)
    half = x / 2.0
    term = np.ones_like(half)          # j=0 项 (x/2)^0/0! = 1
    s = term.copy()
    for j in range(1, k):
        term = term * half / j         # 递推 (x/2)^j / j!
        s = s + term
    return np.exp(-half) * s


def p_to_e_calibrator(p, kappa=0.5):
    """
    p->e 校准子（Vovk–Wang 2021）：e = κ · p^{κ-1}，κ∈(0,1)。零假设(p~Unif)下 E[e]=1。
    默认 κ=1/2 -> e = 0.5 · p^{-1/2}。p 下限 clip 防除零 -> e 有限上界（保守，不破坏 valid）。
    """
    p = np.clip(np.asarray(p, dtype=float), 1e-12, 1.0)
    return kappa * p ** (kappa - 1.0)


# --------------------------------------------------------------------------- #
# 依赖下零假设 Monte-Carlo：三法经验 Type-I 误报率
# --------------------------------------------------------------------------- #
def simulate_type1(rho, k, n_trials, alpha, rng, kappa=0.5):
    """
    全零假设（窗实为全假 artifact）下，K 个正相关 p 值，三法在名义 α 的经验 Type-I。
    高斯 copula：z~N(0,Σ)，Σ=等相关(ρ)；p=1-Φ(z)，边际精确 Uniform，跨告警器相关=ρ。
    返回 dict: fisher_indep / bonferroni / evalue_mean -> 经验误拒比例。
    """
    k = int(k)
    if k < 2:
        raise ValueError("合并检验需 K>=2 个同窗告警")
    # 等相关协方差 Σ = (1-ρ)I + ρ·11ᵀ，ρ∈[0,1) 保证半正定
    cov = (1.0 - rho) * np.eye(k) + rho * np.ones((k, k))
    z = rng.multivariate_normal(mean=np.zeros(k), cov=cov, size=n_trials)  # (n_trials, k)
    p = 1.0 - _norm_cdf(z)                    # 上尾 p 值，边际 Uniform(0,1)
    p = np.clip(p, 1e-12, 1.0)

    # (1) Fisher 合并（假设独立）
    X = -2.0 * np.log(p).sum(axis=1)          # ~χ²_{2K}（仅独立时）
    p_fisher = chi2_sf_even(X, k)
    reject_fisher = p_fisher <= alpha

    # (2) Bonferroni（min-p，任意依赖控 FWER）
    reject_bonf = p.min(axis=1) <= (alpha / k)

    # (3) e-value 均值合并（任意依赖 valid + Markov 1/α）
    e = p_to_e_calibrator(p, kappa=kappa)
    merged_e = e.mean(axis=1)
    reject_e = merged_e >= (1.0 / alpha)

    return {
        "fisher_indep": float(reject_fisher.mean()),
        "bonferroni": float(reject_bonf.mean()),
        "evalue_mean": float(reject_e.mean()),
    }


def estimate_dependence_from_records(records, pn_dir, local_dir, family, limit):
    """
    可选：从真实派生告警标定 ρ（成对 phi 中位）与 K（共触发窗活跃类中位）。
    复用 alarm_derive；数据不可达/告警不足则返回 (None, None, 0, 0)，main 回退缺省。
    """
    from alarm_derive import (
        load_numerics, derive_alarm_timelines, resample_to_common_grid, pairwise_phi,
    )
    phis, ksizes = [], []
    win = max(1, int(round(COTRIGGER_WINDOW_S)))
    recs = records[:limit] if limit and limit > 0 else records
    for rec in recs:
        try:
            signals = load_numerics(rec, pn_dir=None if local_dir else pn_dir, local_dir=local_dir)
        except Exception as e:  # noqa: BLE001
            print(f"[warn] 读取失败 {rec}: {e}")
            continue
        if not signals:
            continue
        timelines = derive_alarm_timelines(signals, family)
        types, grid = resample_to_common_grid(timelines)
        if grid.shape[0] < 2 or grid.shape[1] < 2:
            continue
        for v in pairwise_phi(grid).values():
            if v == v:                          # 非 NaN
                phis.append(v)
        n_types, n_bins = grid.shape
        for start in range(max(0, n_bins - win + 1)):
            s = int(grid[:, start:start + win].any(axis=1).sum())
            if s >= 2:
                ksizes.append(s)
    rho = float(np.median(phis)) if phis else None
    k = int(round(float(np.median(ksizes)))) if ksizes else None
    return rho, k, len(phis), len(ksizes)


def get_record_list(args):
    if args.records:
        recs = [ln.strip() for ln in Path(args.records).read_text(encoding="utf-8").splitlines() if ln.strip()]
        return recs[: args.limit] if args.limit > 0 else recs
    try:
        import wfdb
        recs = wfdb.get_record_list(DEFAULT_PN_DIR)
    except Exception as e:  # noqa: BLE001
        print(f"[warn] 在线取 RECORDS 失败({e})，用 --records 传清单。")
        return []
    return recs[: args.limit] if args.limit > 0 else recs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", type=str, default="",
                    help="record 清单（给了则从真实告警标定 ρ/K，否则用缺省）")
    ap.add_argument("--local-dir", type=str, default="")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--family", type=str, default="default", help="标定 ρ/K 用的阈值族")
    ap.add_argument("--rho", type=float, default=-1.0,
                    help="正相关强度；<0 表示未指定 -> 用真实标定或缺省 %.2f" % DEFAULT_RHO)
    ap.add_argument("--k", type=int, default=-1,
                    help="合并的同窗告警数；<0 -> 用真实标定或缺省 %d" % DEFAULT_K)
    ap.add_argument("--alphas", type=str, default="0.01,0.05,0.10")
    ap.add_argument("--n-trials", type=int, default=40000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--smoke", type=int, default=0)
    args = ap.parse_args()
    args.local_dir = args.local_dir or None

    if args.smoke:
        args.n_trials = 3000
        args.limit = 2

    alphas = [float(a) for a in args.alphas.split(",") if a.strip()]

    # ---- 标定 ρ / K ----
    src_rho = "cli"
    rho, k = args.rho, args.k
    if (rho < 0 or k < 0) and (args.records or args.local_dir) and not args.smoke:
        est_rho, est_k, n_ph, n_ks = estimate_dependence_from_records(
            get_record_list(args), DEFAULT_PN_DIR, args.local_dir, args.family, args.limit)
        print(f"[calib] 真实标定: phi 中位={est_rho} (n_pairs={n_ph}), "
              f"K 中位={est_k} (n_cotrig_win={n_ks})")
        if rho < 0 and est_rho is not None:
            rho, src_rho = est_rho, "data"
        if k < 0 and est_k is not None:
            k = est_k
    if rho < 0:
        rho, src_rho = DEFAULT_RHO, "default_report_phi"
    if k < 0:
        k = DEFAULT_K
    # copula 等相关须 ρ∈[0,1)；负 phi 出现时裁到 0（本 demo 聚焦正依赖，report 实测为正）
    rho_used = float(min(max(rho, 0.0), 0.99))
    if rho != rho_used:
        print(f"[calib] ρ={rho:.4f} 裁到 [0,0.99] -> {rho_used:.4f}"
              f"（等相关 copula 需 ρ≥0；负依赖非本 pilot 焦点，report 实测为正）")
    k = max(2, int(k))
    print(f"[calib] 采用 ρ={rho_used:.4f}（来源={src_rho}）, K={k}, "
          f"n_trials={args.n_trials}, seed={args.seed}")

    rng = np.random.default_rng(args.seed)

    # ---- 两档依赖对照：独立(ρ=0) sanity vs 真实正依赖(ρ_used) ----
    settings = [
        ("independent_rho=0.0", 0.0),
        (f"real_rho={rho_used:.2f}", rho_used),
    ]
    method_names = {
        "fisher_indep": "fisher_indep",
        "bonferroni": "bonferroni",
        "evalue_mean": "evalue_mean",
    }

    rows = []
    for dep_label, rho_s in settings:
        for alpha in alphas:
            res = simulate_type1(rho_s, k, args.n_trials, alpha, rng)
            mc_tol = 1.5 * math.sqrt(alpha * (1 - alpha) / args.n_trials)  # MC 噪声带
            for mkey, mname in method_names.items():
                emp = res[mkey]
                rows.append({
                    "method": mname,
                    "alpha": alpha,
                    "nominal": alpha,
                    "empirical_error": round(emp, 5),
                    "controlled": bool(emp <= alpha + mc_tol),
                    "dependence": dep_label,
                    "rho": round(rho_s, 4),
                    "k_merged": k,
                    "n_trials": args.n_trials,
                    "source_rho": src_rho,
                })

    df = pd.DataFrame(rows)
    out_csv = OUT_DIR / "dependence_demo.csv"
    df.to_csv(out_csv, index=False, encoding="utf-8")
    print(f"[written] {out_csv}")
    print(df.to_string(index=False))

    # ---- C3 判据汇总打印 ----
    print("\n[C3] 依赖是否让 naive（假设独立）合并检验失效？")
    print("     看 real_rho 档：fisher_indep（假设独立）empirical vs α，"
          "evalue_mean（任意依赖 valid）vs α。")
    real_label = settings[-1][0]
    for alpha in alphas:
        sub = {r["method"]: r for r in rows if r["dependence"] == real_label and r["alpha"] == alpha}
        f_emp = sub["fisher_indep"]["empirical_error"]
        e_emp = sub["evalue_mean"]["empirical_error"]
        b_emp = sub["bonferroni"]["empirical_error"]
        f_ok = sub["fisher_indep"]["controlled"]
        e_ok = sub["evalue_mean"]["controlled"]
        print(f"     α={alpha:<5}  fisher_indep={f_emp} (控={f_ok})  "
              f"evalue_mean={e_emp} (控={e_ok})  bonferroni={b_emp}")
    print("     判据：")
    print("       fisher_indep empirical_error > α（依赖下超标误报）+ evalue_mean 控在 α"
          " -> 依赖破坏 naive、e-value 有增量 -> C3 GO。")
    print("       fisher_indep 本就控在 α -> e-value 无增量 -> C3 塌。")
    print("     诚实对照：bonferroni（任意依赖控 FWER）应始终 ≤α -> 证明「非所有 naive 都失效」，"
          "失效特指假设独立的证据合并。")
    print("     sanity：independent_rho=0.0 档三法都应≈控在 α（构造正确性自检）。")
    print("     ⚠️ 半合成 pilot：ρ/K 取自真实告警，零假设 p 值 MC 模拟（真数据无非循环 per-告警统计量）；")
    print("        弱代理非结局金标（R8）；结论=机制级 demo 非完整方法学证明。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
