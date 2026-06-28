#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
paired_bootstrap.py
===================
服务: quantimmu-bench F-pilot — 配对患者级 bootstrap CI
约束对齐: LEDGER §5 约束①②③ (效应量估计; 配对同折同患者; 去偏地板同口径)

设计
----
  对 DS2 9 患者有放回重抽 ≥1000 次 (患者级 bootstrap, 非肽级).
  Δz_i = z_i(meta) - z_i(baseline)  per patient (Fisher-z 变换后差值)
  bootstrap 聚合: 每次重抽 9 患者, 算 Δz̄ = mean(Δz_i)
  输出: 点估 Δz̄ + 95% CI [2.5%, 97.5%] + 方向概率 P(Δ>0)

决策规则 (LEDGER §5 约束①②)
------------------------------
  - 主读数 = 点估 Δ + CI 宽, **不**以 p<0.05 当 go/no-go
  - catastrophe gate: meta 点估**明显**低于同折地板 → stacking 反伤
  - "点估升一点 CI 宽" = 已去风险, 值得上 powered 研究 (不是负面结论)

输入
----
  --meta     lopo 主模型 per_patient CSV  (lopo_eval.py 产出, 通常 Ridge surv6)
  --baseline lopo 基线 per_patient CSV   (通常 FixAvg surv6; 或单工具 pTuneos/deepHLApan)
  --n_boot   bootstrap 次数 (默认 2000)
  --seed     随机种子 (默认 42)

输出
----
  quantimmune/results/bootstrap_{meta_tag}_vs_{baseline_tag}.json
  quantimmune/results/bootstrap_{meta_tag}_vs_{baseline_tag}.csv (每患者 Δz_i)

跑法
----
  python quantimmune/paired_bootstrap.py \\
    --meta     quantimmune/results/lopo_ridge_surv6_raw_sfc.per_patient.csv \\
    --baseline quantimmune/results/lopo_fixavg_surv6_raw_sfc.per_patient.csv
"""

import sys
import json
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
RESULTS_DIR = HERE / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

FISHER_CLIP = 0.9999

# DS2 9 patients (同 lopo_eval.py)
DS2_PATIENTS = {101, 102, 104, 105, 106, 107, 108, 109, 110}


def _to_fisherz(rho: float) -> float:
    """安全 Fisher-z 变换 (clip rho=±1)."""
    if np.isnan(rho):
        return np.nan
    return float(np.arctanh(np.clip(rho, -FISHER_CLIP, FISHER_CLIP)))


def load_per_patient(path: Path) -> pd.DataFrame:
    """读 lopo_eval.py 产出的 per_patient CSV, 过滤 DS2 + in_main_analysis.
    返回 DataFrame: Patient_ID, rho, rho_z, n_pep
    """
    if not path.exists():
        sys.exit(f"[ERR] per_patient CSV 不存在: {path}\n"
                 f"      请先运行 lopo_eval.py 生成对应模型结果")
    df = pd.read_csv(path, encoding="utf-8")
    required = ["Patient_ID", "rho", "n_pep"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        sys.exit(f"[ERR] {path.name} 缺少列: {missing}")

    # 过滤: DS2 + in_main_analysis (或退而使用 DS2 患者集合)
    if "in_main_analysis" in df.columns:
        df2 = df[df["in_main_analysis"] == True].copy()
    elif "Dataset" in df.columns:
        df2 = df[df["Dataset"] == "DS2"].copy()
    else:
        # fallback: Patient_ID 在 DS2_PATIENTS 集合中
        df2 = df[df["Patient_ID"].isin(DS2_PATIENTS)].copy()

    # 确保 rho_z 列存在
    if "rho_z" not in df2.columns or df2["rho_z"].isna().all():
        df2["rho_z"] = df2["rho"].apply(_to_fisherz)

    # 过滤有效 rho
    df2 = df2.dropna(subset=["rho"]).copy()
    df2["rho_z"] = df2["rho_z"].fillna(df2["rho"].apply(_to_fisherz))

    return df2[["Patient_ID", "rho", "rho_z", "n_pep"]].reset_index(drop=True)


def main():
    ap = argparse.ArgumentParser(
        description="F-pilot 配对患者级 bootstrap CI (quantimmu-bench)")
    ap.add_argument("--meta", required=True,
                    help="主模型 per_patient CSV (lopo_eval.py 产出)")
    ap.add_argument("--baseline", required=True,
                    help="基线 per_patient CSV (lopo_eval.py 产出)")
    ap.add_argument("--n_boot", type=int, default=2000,
                    help="bootstrap 次数 (默认 2000)")
    ap.add_argument("--seed", type=int, default=42,
                    help="随机种子 (默认 42)")
    ap.add_argument("--out", default=None,
                    help="输出 JSON 路径 (默认自动命名)")
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)

    meta_path     = Path(args.meta)
    baseline_path = Path(args.baseline)

    print(f"[info] meta:     {meta_path.name}")
    print(f"[info] baseline: {baseline_path.name}")

    # ── 读取两个 per_patient 结果 ──────────────────────────────────────────────
    meta_df     = load_per_patient(meta_path)
    baseline_df = load_per_patient(baseline_path)

    print(f"[info] meta DS2 患者数: {len(meta_df)}")
    print(f"[info] baseline DS2 患者数: {len(baseline_df)}")

    # ── 配对: 取两者共有 Patient_ID ──────────────────────────────────────────
    common_pats = sorted(
        set(meta_df["Patient_ID"].tolist()) & set(baseline_df["Patient_ID"].tolist())
    )
    if len(common_pats) == 0:
        sys.exit("[ERR] meta 和 baseline 无共同患者 ID, 检查输入文件")

    meta_aligned = (meta_df.set_index("Patient_ID")
                           .loc[common_pats]
                           .reset_index())
    base_aligned = (baseline_df.set_index("Patient_ID")
                               .loc[common_pats]
                               .reset_index())

    n_pat = len(common_pats)
    print(f"[info] 共同患者 ({n_pat}): {common_pats}")

    # ── per-patient Δz_i ─────────────────────────────────────────────────────
    delta_z = meta_aligned["rho_z"].values - base_aligned["rho_z"].values
    # Δρ 点估 (非 z 域, 仅参考)
    delta_rho = meta_aligned["rho"].values - base_aligned["rho"].values

    # 点估 Δz̄ (Fisher-z 域)
    delta_z_point = float(np.nanmean(delta_z))
    delta_rho_point = float(np.nanmean(delta_rho))

    # per-patient 明细 CSV
    detail_df = pd.DataFrame({
        "Patient_ID": common_pats,
        "meta_rho":     meta_aligned["rho"].values,
        "baseline_rho": base_aligned["rho"].values,
        "delta_rho":    delta_rho,
        "meta_rho_z":   meta_aligned["rho_z"].values,
        "baseline_rho_z": base_aligned["rho_z"].values,
        "delta_z":      delta_z,
    })

    # 方向一致性 (非 bootstrap)
    n_positive = int(np.nansum(delta_z > 0))
    n_negative = int(np.nansum(delta_z < 0))
    direction_frac = float(n_positive / n_pat) if n_pat > 0 else np.nan

    print(f"\n[点估] Δz̄ (Fisher-z) = {delta_z_point:+.4f}")
    print(f"[点估] Δρ̄ (raw)       = {delta_rho_point:+.4f}")
    print(f"[方向] meta > baseline: {n_positive}/{n_pat} 患者 "
          f"({direction_frac:.1%})")

    # ── 患者级 bootstrap ──────────────────────────────────────────────────────
    print(f"\n[bootstrap] n_boot={args.n_boot}, seed={args.seed}, "
          f"患者级重抽 (非肽级) ...")

    delta_z_valid = delta_z[~np.isnan(delta_z)]
    n_valid = len(delta_z_valid)
    if n_valid == 0:
        sys.exit("[ERR] 所有 Δz 均为 NaN, 无法 bootstrap")

    boot_means = np.empty(args.n_boot)
    for i in range(args.n_boot):
        idx = rng.integers(0, n_valid, n_valid)
        boot_means[i] = float(np.mean(delta_z_valid[idx]))

    ci_lo, ci_hi = float(np.percentile(boot_means, 2.5)), \
                   float(np.percentile(boot_means, 97.5))
    frac_gt0 = float(np.mean(boot_means > 0))

    print(f"[结果] Δz̄ 点估 = {delta_z_point:+.4f}")
    print(f"[结果] 95% CI = [{ci_lo:+.4f}, {ci_hi:+.4f}]  (CI 宽={ci_hi-ci_lo:.4f})")
    print(f"[结果] P(Δ>0)  = {frac_gt0:.3f}  (方向证据, 非 p 值)")

    # ── LEDGER §5 约束② catastrophe gate ────────────────────────────────────
    # meta 点估明显低于 baseline → stacking 反伤
    CATASTROPHE_THRESHOLD = -0.05  # Δz < -0.05 视为反伤 (可调)
    if delta_z_point < CATASTROPHE_THRESHOLD:
        decision = "CATASTROPHE: meta 明显低于 baseline, stacking 反伤"
    elif ci_lo > 0:
        decision = "CI 下界>0: 较强方向证据 (但样本小 CI 宽, 不宜过解读)"
    elif delta_z_point > 0:
        decision = "点估正向 + CI 含0: 值得上 powered 研究 (n=15 功效不足)"
    else:
        decision = "点估非正向: 无增量证据 (但 CI 宽, 不排除真实效应)"

    print(f"\n[决策] {decision}")
    print(f"  (LEDGER §5 约束①②: 主读数=点估+CI, 不以 p<0.05 当 go/no-go)")

    # ── 命名输出文件 ───────────────────────────────────────────────────────────
    def _tag(path):
        name = path.stem  # e.g. lopo_ridge_surv6_raw_sfc.per_patient
        return name.replace(".per_patient", "").replace("lopo_", "")

    meta_tag = _tag(meta_path)
    base_tag = _tag(baseline_path)
    out_stem = f"bootstrap_{meta_tag}_vs_{base_tag}"

    # per-patient 明细
    detail_csv = RESULTS_DIR / f"{out_stem}.per_patient.csv"
    detail_df.to_csv(detail_csv, index=False, encoding="utf-8")
    print(f"\n[saved] {detail_csv}")

    # summary JSON
    out_json_path = Path(args.out) if args.out else RESULTS_DIR / f"{out_stem}.json"

    def _f(v):
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return None
        return round(float(v), 6)

    summary = {
        "meta":     meta_path.name,
        "baseline": baseline_path.name,
        "n_patients": n_valid,
        "n_boot": args.n_boot,
        "seed": args.seed,
        "delta_z_point":  _f(delta_z_point),
        "delta_rho_point": _f(delta_rho_point),
        "delta_z_ci_lo":  _f(ci_lo),
        "delta_z_ci_hi":  _f(ci_hi),
        "delta_z_ci_width": _f(ci_hi - ci_lo),
        "P_delta_gt0":    _f(frac_gt0),
        "n_patients_positive": n_positive,
        "n_patients_negative": n_negative,
        "direction_frac":  _f(direction_frac),
        "catastrophe_gate_threshold": CATASTROPHE_THRESHOLD,
        "decision": decision,
        "ledger_notes": (
            "主读数=点估+CI宽 (非p值). catastrophe gate: 点估<-0.05=stacking反伤. "
            "点估正+CI含0=值得上powered研究 (LEDGER §5 约束①②)"
        ),
    }

    with open(out_json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"[saved] {out_json_path}")
    print(f"\n[DONE] bootstrap 完成")


if __name__ == "__main__":
    main()
