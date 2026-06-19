"""
selinf_corrector.py — SelInfBench A4 报告值校正器 (CLI)
服务: SelInfBench (selinf) A4，lever = 交付「可挂任意 benchmark sweep 日志的报告值校正器」
不启动训练外部进程；写完交主线跑。

## 功能
接受任意 sweep 日志 CSV，识别 argmax-selected config，用 data fission 去偏：
  1. naive 报告值（被选 config 原始 metric）
  2. data fission 去偏点估计 g_star
  3. 恢复名义条件覆盖的有效 CI [lo, hi]
  4. 去偏移位 = naive − g_star

## 方法（Leiner+ JASA2023, data fission）
  Z_i ~ N(0, sigma^2)，独立注入
  f_i = X_i + tau * Z_i   → 选择信道（argmax 选 i*）
  g_i = X_i - Z_i / tau   → 推断信道
  i* = argmax(f)
  g_star = g_{i*}
  推断信道标准差: se_g = sigma * sqrt(1 + 1/tau^2)
  CI = g_star ± z_{1-alpha/2} * se_g
  理论保证: g_{i*} 与选择事件条件独立（fission 核心引理），
             标准 CI（不需截断正态）有覆盖保证。

## sigma 估计口径（禁臆想，注明依据）
  默认: sweep pooled std（所有 config 该 metric 的样本标准差, ddof=1）。
  理由: 每个 config 通常只跑一次，无重复采样无法做 per-config bootstrap；
        pooled std 代理「config-to-config 自然波动 + 噪声」下界（保守）。
  若用户提供 --sigma，直接用用户值（适合多 seed 重跑的场景，per-config sigma 更精确）。
  注: 如能多次重跑同 config，per-config bootstrap 估计 sigma 更精确——但多数 sweep 无重复。

## 禁止输出
  deflation = df_width/naive_width − 1（≡ sqrt(2M)−1 纯 M artifact，
  02_ACCEPTANCE 方法红线明确永禁当有效性证据，此处完全不计算/不输出）。

## 输入 CSV 格式
  - 一行一个 config（过滤 _STAT_ 元数据行）
  - 必须有：--metric-col 指定的列（float，越高=越好）
  - 必须有：--config-col 指定的列（config 标识符）
  - 可选：--seed-col（仅用于显示，不影响计算）
  - 忽略其他列

## Windows 规范
  纯 numpy + pandas + math，禁 scipy.stats（OMP Error #15）
  无 torch，无 DataLoader
  if __name__=='__main__' 包主逻辑

## 用法示例
  python selinf_corrector.py \
    --csv D:/YJ-Agent/project/meeting/SelInfBench/results/ham_datafission.csv \
    --metric-col macro_auc \
    --config-col config

  python selinf_corrector.py \
    --csv sweep.csv --metric-col val_acc --config-col config \
    --sigma 0.01 --tau 1.0 --alpha 0.05 --out result.json
"""

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd


# ─────────────────────────────────────────────────────────────────────────────
# 纯 numpy 工具（禁 scipy.stats，OMP Error #15 Red Line）
# ─────────────────────────────────────────────────────────────────────────────

def z_score(alpha: float) -> float:
    """
    N(0,1) upper alpha/2 quantile，纯 math.erf（禁 scipy.stats，OMP Error #15）。
    实现：A&S 26.2.17 初始猜 + 5 步 Newton 在 Phi(x)=p 上迭代，精度 <1e-10。
    与 selinf_datafission.py / selinf_a3_truthproxy.py 口径完全一致。
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


# ─────────────────────────────────────────────────────────────────────────────
# Data Fission CI（Leiner+ JASA2023，严格复原）
# ─────────────────────────────────────────────────────────────────────────────

def data_fission_correct(
    values: np.ndarray,
    sigma: float,
    tau: float = 1.0,
    alpha: float = 0.05,
    rng_seed: int = 42,
) -> dict:
    """
    Data fission 报告值校正（Leiner+ JASA2023）。

    参数：
      values : 1-D ndarray，M 个 config 的 metric 观测值 X_i
      sigma  : 注入噪声标准差（由 sweep pooled std 估计，或用户提供）
      tau    : 分裂参数（默认 1.0 = 选择/推断等分）
      alpha  : 显著水平（默认 0.05 → 95% CI）
      rng_seed : numpy rng seed（固定复现性）

    返回 dict：
      selected_idx   : argmax(f) 选中的行索引
      naive_value    : values[argmax(values)] 原始报告值（argmax 在原始 X 上）
      g_star         : 推断信道被选 config 的观测值（去偏点估计）
      ci_low / ci_high : 95% 有效 CI（恢复名义条件覆盖）
      ci_width       : ci_high - ci_low
      debias_shift   : naive_value - g_star（校正幅度，>0 = 原始报告高估）
      se_g           : CI 半宽除以 z（推断信道标准差）
      sigma_used     : 实际使用的 sigma
      M              : config 数量

    注：选择信道 f 与推断信道 g 上的 argmax 可能不同（f 含随机注入）；
        i_star = argmax(f)（data fission 协议定义），
        naive_value = values[argmax(values)]（原始 argmax，与 i_star 通常相同但可差异）。
    """
    M   = len(values)
    rng = np.random.default_rng(rng_seed)

    # 注入噪声 Z_i ~ N(0, sigma^2)（独立）
    Z = rng.normal(0.0, sigma, size=M)

    # 分裂
    f = values + tau * Z      # 选择信道
    g = values - Z / tau      # 推断信道

    # 选择：i* = argmax(f)
    i_star  = int(np.argmax(f))
    g_star  = float(g[i_star])

    # 推断信道条件标准差（精确值）
    # g_{i*} ~ N(mu_{i*}, sigma^2 * (1 + 1/tau^2))
    # （与 selinf_datafission.py data_fission_ci 口径完全一致）
    se_g = sigma * math.sqrt(1.0 + 1.0 / tau**2)
    z    = z_score(alpha)

    ci_low  = g_star - z * se_g
    ci_high = g_star + z * se_g

    # naive 报告值 = argmax 原始 metric（选择信道 f 上的 i* 与原始 argmax 可能略有差异）
    i_naive     = int(np.argmax(values))
    naive_value = float(values[i_naive])

    # 去偏移位（以原始 argmax 对应值为 "naive 报告值"）
    debias_shift = naive_value - g_star

    return {
        "M":             M,
        "sigma_used":    sigma,
        "tau":           tau,
        "alpha":         alpha,
        "i_star":        i_star,        # argmax(f) → data fission 选择协议
        "i_naive":       i_naive,       # argmax(X) → 原始 naive 选择
        "naive_value":   naive_value,   # X[argmax(X)]，即原始报告值
        "g_star":        g_star,        # g[i_star]，去偏点估计
        "debias_shift":  debias_shift,  # naive_value - g_star（>0 = 高估）
        "ci_low":        ci_low,
        "ci_high":       ci_high,
        "ci_width":      ci_high - ci_low,
        "se_g":          se_g,
        "z_alpha":       z,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 读 CSV + 过滤 _STAT_ 元数据行
# ─────────────────────────────────────────────────────────────────────────────

def load_sweep_csv(
    csv_path: str,
    metric_col: str,
    config_col: str,
    seed_col: str | None = None,
) -> tuple[pd.DataFrame, np.ndarray]:
    """
    读 sweep CSV，过滤 _STAT_ 元数据行，返回 (df_clean, values_array)。
    df_clean 只保留有效 config 行（metric_col 非空 + 非 NaN）。
    """
    df = pd.read_csv(csv_path)

    # 检查必需列
    if config_col not in df.columns:
        raise ValueError(f"config 列 '{config_col}' 不在 CSV 里。"
                         f"实际列: {list(df.columns)}")
    if metric_col not in df.columns:
        raise ValueError(f"metric 列 '{metric_col}' 不在 CSV 里。"
                         f"实际列: {list(df.columns)}")
    if seed_col is not None and seed_col not in df.columns:
        print(f"[WARN] seed 列 '{seed_col}' 不在 CSV 里，忽略。", file=sys.stderr)
        seed_col = None

    # 过滤 _STAT_ 元数据行（ham_datafission.csv 里的统计汇总行）
    mask_stat = df[config_col].astype(str).str.startswith("_STAT_")
    n_stat    = int(mask_stat.sum())
    if n_stat > 0:
        print(f"[INFO] 过滤 {n_stat} 个 _STAT_ 元数据行。", file=sys.stderr)

    # 过滤 metric 为空或非数值的行
    df_clean = df[~mask_stat].copy()
    df_clean[metric_col] = pd.to_numeric(df_clean[metric_col], errors="coerce")
    n_nan = int(df_clean[metric_col].isna().sum())
    if n_nan > 0:
        print(f"[INFO] 过滤 {n_nan} 行 metric=NaN。", file=sys.stderr)
    df_clean = df_clean[df_clean[metric_col].notna()].reset_index(drop=True)

    if len(df_clean) < 2:
        raise ValueError(f"过滤后有效 config 行数={len(df_clean)}，至少需要 2 个。")

    values = df_clean[metric_col].values.astype(float)
    return df_clean, values


# ─────────────────────────────────────────────────────────────────────────────
# 打印输出（人类可读）
# ─────────────────────────────────────────────────────────────────────────────

def print_results(
    result:     dict,
    df_clean:   pd.DataFrame,
    metric_col: str,
    config_col: str,
    seed_col:   str | None,
    csv_path:   str,
    sigma_mode: str,   # "user-provided" or "pooled-std"
):
    M           = result["M"]
    naive_val   = result["naive_value"]
    g_star      = result["g_star"]
    shift       = result["debias_shift"]
    ci_low      = result["ci_low"]
    ci_high     = result["ci_high"]
    ci_width    = result["ci_width"]
    sigma_used  = result["sigma_used"]
    tau         = result["tau"]
    alpha       = result["alpha"]
    i_star      = result["i_star"]
    i_naive     = result["i_naive"]

    conf_pct   = int(round((1 - alpha) * 100))
    naive_cfg  = str(df_clean.iloc[i_naive][config_col])
    fission_cfg = str(df_clean.iloc[i_star][config_col])

    print("=" * 68)
    print("SelInfBench 报告值校正器 — data fission (Leiner+ JASA2023)")
    print("=" * 68)
    print(f"  CSV       : {csv_path}")
    print(f"  metric    : {metric_col}  |  M={M} configs")
    print(f"  sigma     : {sigma_used:.6f}  ({sigma_mode})")
    print(f"  tau       : {tau}  |  alpha={alpha}  |  {conf_pct}% CI")
    print()
    print("  ── 被选 config ────────────────────────────────────────────")
    print(f"  Naive argmax  : [{i_naive}] {naive_cfg}")
    print(f"  Fission i*    : [{i_star}] {fission_cfg}")
    if seed_col:
        seed_val = df_clean.iloc[i_naive].get(seed_col, "N/A")
        print(f"  Seed          : {seed_val}")
    print()
    print("  ── 校正结果（交付指标）────────────────────────────────────")
    print(f"  (a) Naive 报告值     = {naive_val:.6f}   [argmax(X) 原始值，未校正]")
    print(f"  (b) 去偏点估计 g_star= {g_star:.6f}   [data fission 推断信道，有效去偏]")
    print(f"  (c) {conf_pct}% 有效 CI  = [{ci_low:.6f}, {ci_high:.6f}]  "
          f"width={ci_width:.6f}")
    print(f"  (d) 去偏移位         = {shift:+.6f}   "
          f"[naive - g_star; >0 = 原始报告高估]")
    print()
    print("  ── 方法注记 ────────────────────────────────────────────────")
    print(f"  · CI 基于推断信道标准差 se_g = sigma*sqrt(1+1/tau^2) = {result['se_g']:.6f}")
    print(f"  · g_star 与「i* 被选中」条件独立（fission 核心引理），CI 有名义覆盖保证")
    print( "  · [REDLINE] 禁输出宽度比 deflation (=sqrt(2M)-1 纯M artifact，见 02_ACCEPTANCE 方法红线)")
    print( "  · sigma 估计口径见模块注释；多 seed 重跑场景建议用 --sigma 传 per-config std")
    print("=" * 68)


# ─────────────────────────────────────────────────────────────────────────────
# 主函数
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="SelInfBench A4 报告值校正器 — data fission 去偏 (Leiner+ JASA2023)"
    )
    parser.add_argument(
        "--csv", required=True,
        help="sweep 日志 CSV 路径（每行一个 config）",
    )
    parser.add_argument(
        "--metric-col", required=True, dest="metric_col",
        help="选择 metric 列名（越高=越好，如 val_acc / macro_auc）",
    )
    parser.add_argument(
        "--config-col", default="config", dest="config_col",
        help="config id 列名（默认: config）",
    )
    parser.add_argument(
        "--seed-col", default=None, dest="seed_col",
        help="seed 列名（可选，仅用于显示）",
    )
    parser.add_argument(
        "--sigma", type=float, default=None,
        help="注入噪声标准差 sigma（不提供则从 sweep pooled std 估计）",
    )
    parser.add_argument(
        "--tau", type=float, default=1.0,
        help="data fission 分裂参数 tau（默认 1.0 = 等分）",
    )
    parser.add_argument(
        "--alpha", type=float, default=0.05,
        help="显著水平 alpha（默认 0.05 → 95%% CI）",
    )
    parser.add_argument(
        "--rng-seed", type=int, default=42, dest="rng_seed",
        help="numpy rng seed（固定复现性，默认 42）",
    )
    parser.add_argument(
        "--out", default=None,
        help="可选：将结果写成 JSON 文件（路径）",
    )
    args = parser.parse_args()

    # 1. 读 CSV
    df_clean, values = load_sweep_csv(
        csv_path   = args.csv,
        metric_col = args.metric_col,
        config_col = args.config_col,
        seed_col   = args.seed_col,
    )

    # 2. sigma 估计
    if args.sigma is not None:
        sigma      = args.sigma
        sigma_mode = "user-provided"
    else:
        # sweep pooled std（ddof=1）
        # 口径：所有 config 该 metric 的样本标准差
        # 理由：每个 config 通常只训练一次；pooled std 代理「config-to-config
        #        自然波动 + 噪声」下界（保守）；见 selinf_datafission.py 模块注释
        sigma      = float(np.std(values, ddof=1))
        sigma_mode = f"pooled-std (ddof=1, M={len(values)})"

    if sigma <= 0.0:
        print(f"[ERROR] sigma={sigma} <= 0，无法建 CI。"
              f"可能所有 config metric 完全相同？", file=sys.stderr)
        sys.exit(1)

    # 3. data fission 校正
    result = data_fission_correct(
        values   = values,
        sigma    = sigma,
        tau      = args.tau,
        alpha    = args.alpha,
        rng_seed = args.rng_seed,
    )

    # 4. 打印结果
    print_results(
        result     = result,
        df_clean   = df_clean,
        metric_col = args.metric_col,
        config_col = args.config_col,
        seed_col   = args.seed_col,
        csv_path   = args.csv,
        sigma_mode = sigma_mode,
    )

    # 5. 可选 JSON 输出
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_data = {
            "input": {
                "csv":        args.csv,
                "metric_col": args.metric_col,
                "config_col": args.config_col,
            },
            "params": {
                "sigma":    sigma,
                "sigma_mode": sigma_mode,
                "tau":      args.tau,
                "alpha":    args.alpha,
                "rng_seed": args.rng_seed,
            },
            "selected_config": {
                "i_naive":   result["i_naive"],
                "i_star":    result["i_star"],
                "naive_config": str(df_clean.iloc[result["i_naive"]][args.config_col]),
                "fission_config": str(df_clean.iloc[result["i_star"]][args.config_col]),
            },
            "corrections": {
                "naive_value":  result["naive_value"],
                "g_star":       result["g_star"],
                "ci_low":       result["ci_low"],
                "ci_high":      result["ci_high"],
                "ci_width":     result["ci_width"],
                "debias_shift": result["debias_shift"],
                "se_g":         result["se_g"],
                "z_alpha":      result["z_alpha"],
            },
            "meta": {
                "M":            result["M"],
                "method":       "data_fission_Leiner_JASA2023",
                "note_deflation_forbidden": (
                    "deflation=df_width/naive_width-1 is a sqrt(2M)-1 M-artifact "
                    "(02_ACCEPTANCE method redline), never computed or output here."
                ),
            },
        }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(out_data, f, indent=2, ensure_ascii=False)
        print(f"\n[OUT] JSON 已写: {out_path}")


# ─────────────────────────────────────────────────────────────────────────────
# CLI 入口（Windows spawn 安全）
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()   # Windows spawn 安全
    main()
