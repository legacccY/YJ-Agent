"""
analysis_r4_r5.py — Med-NCA 验收分析脚本
R4: pseudo-ensemble Dice > single Dice（配对 bootstrap 95% CI）
R5: NQM 推理方差与误差正相关（Spearman ρ，p<0.05）

作者：YJ-Agent  日期：2026-06-02
禁止修改任何训练代码，本脚本仅做分析。
"""

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

# ── 路径配置 ──────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent                        # Med-NCA/
RESULTS = ROOT / "results"

SINGLE_CSV   = RESULTS / "r1_hippocampus_single.csv"
PSEUDO_CSV   = RESULTS / "r1_hippocampus_pseudo10.csv"
VAR_CSV      = RESULTS / "r1_hippocampus_variance.csv"
OUT_JSON     = RESULTS / "r4_r5_summary.json"

BOOTSTRAP_N  = 1000
SEED         = 0


# ── 工具函数 ──────────────────────────────────────────────────
def get_git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
            cwd=str(ROOT)
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


def bootstrap_ci(arr: np.ndarray, n: int, rng: np.random.Generator,
                 ci: float = 95.0):
    """对 arr 做 n 次 bootstrap，返回 mean 分布的 CI 区间。"""
    means = np.array([
        rng.choice(arr, size=len(arr), replace=True).mean()
        for _ in range(n)
    ])
    lo = np.percentile(means, (100 - ci) / 2)
    hi = np.percentile(means, 100 - (100 - ci) / 2)
    return float(lo), float(hi)


# ── R4 分析 ───────────────────────────────────────────────────
def run_r4() -> dict:
    print("=" * 60)
    print("R4: Pseudo-ensemble Dice > Single Dice（配对 bootstrap）")
    print("=" * 60)

    # 读数据
    df_single = pd.read_csv(SINGLE_CSV).rename(columns={"dice": "dice_single"})
    df_pseudo = pd.read_csv(PSEUDO_CSV).rename(columns={"dice": "dice_pseudo"})

    # 配对合并
    df = pd.merge(df_single, df_pseudo, on="patient_id", how="inner")
    n_pairs = len(df)
    print(f"  配对样本数: {n_pairs}")

    if n_pairs == 0:
        raise ValueError("无法配对：两份 csv 没有共同 patient_id")

    # 差值
    df["diff"] = df["dice_pseudo"] - df["dice_single"]
    mean_diff = float(df["diff"].mean())
    print(f"  mean(pseudo - single) = {mean_diff:.4f}")

    # 配对 bootstrap
    rng = np.random.default_rng(seed=SEED)
    ci_lo, ci_hi = bootstrap_ci(df["diff"].to_numpy(), BOOTSTRAP_N, rng)
    print(f"  Bootstrap 95% CI = [{ci_lo:.4f}, {ci_hi:.4f}]")

    verdict = "PASS" if ci_lo > 0 else "FAIL"
    print(f"  判据（CI 下界 > 0）: {verdict}")
    print()

    return {
        "mean_diff": mean_diff,
        "ci95": [ci_lo, ci_hi],
        "n_pairs": n_pairs,
        "verdict": verdict,
    }


# ── R5 分析 ───────────────────────────────────────────────────
def run_r5() -> dict:
    print("=" * 60)
    print("R5: NQM 推理方差 与 误差 正相关（Spearman ρ）")
    print("=" * 60)

    if not VAR_CSV.exists():
        msg = "R5 pending: needs variance export from inference"
        print(f"  {msg}")
        print(f"  期望文件: {VAR_CSV}")
        print()
        return {"status": "pending", "message": msg}

    # 读方差文件
    df_var = pd.read_csv(VAR_CSV)                          # patient_id, nqm_var
    df_single = pd.read_csv(SINGLE_CSV)                    # patient_id, dice

    df = pd.merge(df_var, df_single, on="patient_id", how="inner")
    df["error"] = 1.0 - df["dice"]

    n = len(df)
    if n < 5:
        return {"status": "insufficient_data", "n": n,
                "message": f"仅 {n} 对样本，无法可靠计算 Spearman ρ"}

    rho, pvalue = stats.spearmanr(df["nqm_var"], df["error"])
    rho, pvalue = float(rho), float(pvalue)

    print(f"  样本数: {n}")
    print(f"  Spearman ρ = {rho:.4f},  p = {pvalue:.4f}")

    verdict = "PASS" if (pvalue < 0.05 and rho > 0) else "FAIL"
    print(f"  判据（ρ>0 且 p<0.05）: {verdict}")
    print()

    return {
        "status": "done",
        "n": n,
        "rho": rho,
        "pvalue": pvalue,
        "verdict": verdict,
    }


# ── 主程序 ────────────────────────────────────────────────────
def main():
    git_commit = get_git_commit()
    print(f"\nMed-NCA 验收分析脚本  |  commit: {git_commit}\n")

    r4 = run_r4()
    r5 = run_r5()

    summary = {
        "seed": SEED,
        "bootstrap_n": BOOTSTRAP_N,
        "git_commit": git_commit,
        "r4": r4,
        "r5": r5,
    }

    OUT_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    print(f"结果已写入: {OUT_JSON}")

    # 汇总
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    r4_v = r4.get("verdict", "N/A")
    r5_v = r5.get("verdict", r5.get("status", "N/A"))
    print(f"  R4: {r4_v}   (mean_diff={r4.get('mean_diff', 'N/A'):.4f}, "
          f"CI=[{r4['ci95'][0]:.4f}, {r4['ci95'][1]:.4f}])")
    print(f"  R5: {r5_v}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
