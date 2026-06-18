"""
run_m3_heldout.py — M-3 LGG held-out 全链 orchestrator（CPU 部分）
服务: MedAD-FailMap § M-3 (per-image C4 risk-coverage on LGG 独立例)
lever: AE ckpt 就绪 + LGG 切好后跑 C4 risk-coverage

依赖顺序（调用前需就绪）:
  [GPU] run_seedfill.py -> ae_s42 训练 -> results/phase2/ae_s42/checkpoints/brats_ae_ep250.pt
  [CPU] prep_lgg_heldout.py -> data/lgg_heldout/tumor/ + normal/
  [CPU] 本脚本: score_external -> conspicuity_proxy -> incremental_stats C4 + bootstrap CI

用法:
    # 完整流程（AE ckpt 就绪后）
    python code/run_m3_heldout.py \
        --ae-ckpt results/phase2/ae_s42/checkpoints/brats_ae_ep250.pt \
        --lgg-dir data/lgg_heldout

    # 跳过已完成步骤（幂等）
    python code/run_m3_heldout.py --ae-ckpt ... --lgg-dir ... --skip-score

输出文件:
    results/phase1/anomaly_scores_lgg_heldout_ae.csv
    results/phase1/conspicuity_features_lgg_heldout_tumor.csv
    results/phase1/conspicuity_features_lgg_heldout_normal.csv
    results/phase1/incremental_C4_risk_coverage_lgg_glcm_cluster_prom.csv
    results/phase1/m3_bootstrap_ci_lgg.csv   <- patient-level bootstrap CI

注意: 本脚本所有 stdout 数字（AUROC 端点）均为实测值；不含任何预填数字。
      主线核对这些数字与 BraTS 主结果（AUROC=0.8228）比较复现方向。
"""

import argparse
import csv
import random
import subprocess
import sys
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score

# 复用 incremental_stats 里的 C4 函数（import，不复制）
_CODE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_CODE_DIR))
from incremental_stats import (
    run_c4_risk_coverage,
    load_mixed_df,
    CONSPICUITY_COLS,
    _rows_to_df,
    _safe_float,
)
from conspicuity_proxy import run_conspicuity

PYTHON = sys.executable
_REPO_ROOT = Path(__file__).resolve().parent.parent


# ============================================================
# Patient-level bootstrap CI（228 切片，15 患者，同患者相关）
# ============================================================

def patient_level_bootstrap_auroc(
    rows,
    conspicuity_col,
    n_bootstrap=1000,
    ci_level=0.95,
    rng_seed=42,
):
    """
    按 patient 重抽样（非按切片）的 bootstrap AUROC CI。

    原理: 15 患者，每次 bootstrap 有放回抽 15 患者，
          用该 15 患者的所有切片计算 AUROC（normal vs tumor）。
          不按切片抽是因为同患者切片间强相关（pseudo-replication）。

    rows: list of dict, 含 filename, patient_dir, label, anomaly_score,
                         + conspicuity_col
    conspicuity_col: 用于 C4 排序的列名（glcm_cluster_prom 等）
    返回 dict:
        full_auroc       -- 全集 AUROC（不 bootstrap）
        top50_auroc      -- coverage=0.5 子集 AUROC（全集，不 bootstrap）
        top10_auroc      -- coverage=0.1 子集 AUROC（全集，不 bootstrap）
        bs_full_lo       -- bootstrap full_auroc (1-ci_level)/2 分位
        bs_full_hi       -- bootstrap full_auroc (1+ci_level)/2 分位
        bs_top50_lo/hi   -- coverage=0.5
        bs_top10_lo/hi   -- coverage=0.1
        n_bootstrap      -- 实际 bootstrap 次数
        n_patients       -- 15
        n_slices         -- 总切片数
    """
    rng = random.Random(rng_seed)

    # 按 patient_dir 分组
    patient_map = {}  # patient_dir -> list of row
    for r in rows:
        pid = r.get("patient_dir", "unknown")
        patient_map.setdefault(pid, []).append(r)
    patients = sorted(patient_map.keys())
    n_patients = len(patients)

    def _auroc_from_rows(sub_rows, col, top_frac=None):
        """
        从 sub_rows 计算 AUROC。
        top_frac: 若给，按 col 降序取 top-frac 比例子集再算（C4 coverage 口径）。
        返回 float 或 nan（< 2 类时）。
        """
        if not sub_rows:
            return float("nan")
        # 按 conspicuity_col 降序排列
        try:
            sub_sorted = sorted(sub_rows,
                                key=lambda r: _safe_float(r.get(col, 0)),
                                reverse=True)
        except Exception:
            return float("nan")

        if top_frac is not None:
            k = max(int(np.ceil(len(sub_sorted) * top_frac)), 2)
            sub_sorted = sub_sorted[:k]

        labels = [int(_safe_float(r.get("label", -1))) for r in sub_sorted]
        scores = [_safe_float(r.get("anomaly_score", float("nan"))) for r in sub_sorted]

        # 过滤 nan/unknown
        valid = [(l, s) for l, s in zip(labels, scores)
                 if l in (0, 1) and not np.isnan(s)]
        if len(valid) < 2:
            return float("nan")
        y_true = [v[0] for v in valid]
        y_score = [v[1] for v in valid]
        if len(set(y_true)) < 2:
            return float("nan")
        try:
            return float(roc_auc_score(y_true, y_score))
        except Exception:
            return float("nan")

    # 全集点估计
    full_auroc  = _auroc_from_rows(rows, conspicuity_col, top_frac=None)
    top50_auroc = _auroc_from_rows(rows, conspicuity_col, top_frac=0.5)
    top10_auroc = _auroc_from_rows(rows, conspicuity_col, top_frac=0.1)
    print(f"[bootstrap] full AUROC={full_auroc:.4f}, "
          f"top50={top50_auroc:.4f}, top10={top10_auroc:.4f}")

    # Bootstrap
    bs_full  = []
    bs_top50 = []
    bs_top10 = []

    for _ in range(n_bootstrap):
        # 按 patient 有放回抽取
        sampled_patients = [rng.choice(patients) for _ in range(n_patients)]
        bs_rows = []
        for pid in sampled_patients:
            bs_rows.extend(patient_map[pid])

        bs_full.append(_auroc_from_rows(bs_rows, conspicuity_col, top_frac=None))
        bs_top50.append(_auroc_from_rows(bs_rows, conspicuity_col, top_frac=0.5))
        bs_top10.append(_auroc_from_rows(bs_rows, conspicuity_col, top_frac=0.1))

    lo_q = (1.0 - ci_level) / 2.0
    hi_q = 1.0 - lo_q

    def _ci(vals):
        valid = [v for v in vals if not np.isnan(v)]
        if not valid:
            return float("nan"), float("nan")
        return float(np.quantile(valid, lo_q)), float(np.quantile(valid, hi_q))

    bs_full_lo,  bs_full_hi  = _ci(bs_full)
    bs_top50_lo, bs_top50_hi = _ci(bs_top50)
    bs_top10_lo, bs_top10_hi = _ci(bs_top10)

    return {
        "full_auroc":    round(full_auroc,  4) if not np.isnan(full_auroc)  else "nan",
        "top50_auroc":   round(top50_auroc, 4) if not np.isnan(top50_auroc) else "nan",
        "top10_auroc":   round(top10_auroc, 4) if not np.isnan(top10_auroc) else "nan",
        "bs_full_lo":    round(bs_full_lo,  4) if not np.isnan(bs_full_lo)  else "nan",
        "bs_full_hi":    round(bs_full_hi,  4) if not np.isnan(bs_full_hi)  else "nan",
        "bs_top50_lo":   round(bs_top50_lo, 4) if not np.isnan(bs_top50_lo) else "nan",
        "bs_top50_hi":   round(bs_top50_hi, 4) if not np.isnan(bs_top50_hi) else "nan",
        "bs_top10_lo":   round(bs_top10_lo, 4) if not np.isnan(bs_top10_lo) else "nan",
        "bs_top10_hi":   round(bs_top10_hi, 4) if not np.isnan(bs_top10_hi) else "nan",
        "n_bootstrap":   n_bootstrap,
        "n_patients":    n_patients,
        "n_slices":      len(rows),
        "ci_level":      ci_level,
        "conspicuity_col": conspicuity_col,
    }


# ============================================================
# 工具
# ============================================================

def run_subprocess(tag, cmd, log_fh=None):
    """运行子进程，返回 True/False。"""
    import os
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    print(f"\n[m3] START {tag}")
    print(f"  CMD: {' '.join(str(c) for c in cmd)}")
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        cwd=str(_REPO_ROOT),
        encoding="utf-8",
        errors="replace",
    )
    for line in proc.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
        if log_fh:
            log_fh.write(line)
    proc.wait()
    if proc.returncode != 0:
        print(f"[m3] FAIL {tag} exit={proc.returncode}")
        return False
    print(f"[m3] DONE  {tag}")
    return True


def read_csv_rows(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows):
    if not rows:
        print(f"  [warn] no rows for {path}")
        return
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


# ============================================================
# 主流程
# ============================================================

def main(args):
    res_phase1 = _REPO_ROOT / "results" / "phase1"
    res_phase1.mkdir(parents=True, exist_ok=True)

    ae_ckpt   = Path(args.ae_ckpt)
    lgg_dir   = Path(args.lgg_dir)
    tumor_dir  = lgg_dir / "tumor"
    normal_dir = lgg_dir / "normal"

    score_csv       = res_phase1 / "anomaly_scores_lgg_heldout_ae.csv"
    consp_tumor_csv = res_phase1 / "conspicuity_features_lgg_heldout_tumor.csv"
    consp_norm_csv  = res_phase1 / "conspicuity_features_lgg_heldout_normal.csv"
    c4_csv          = res_phase1 / "incremental_C4_risk_coverage_lgg_glcm_cluster_prom.csv"
    bootstrap_csv   = res_phase1 / "m3_bootstrap_ci_lgg.csv"
    manifest_csv    = res_phase1 / "lgg_heldout_manifest.csv"

    # ---- Step 0: 前置检查 ----
    print(f"[m3] checking prerequisites ...")
    if not ae_ckpt.exists():
        raise FileNotFoundError(
            f"AE ckpt not found: {ae_ckpt}\n"
            f"  -> Run run_seedfill.py first (GPU needed) to regenerate brats_ae ckpt."
        )
    if not tumor_dir.exists() or not normal_dir.exists():
        raise FileNotFoundError(
            f"lgg_heldout dirs not found: {tumor_dir}, {normal_dir}\n"
            f"  -> Run prep_lgg_heldout.py first."
        )
    print(f"  ae_ckpt:    {ae_ckpt}")
    print(f"  tumor_dir:  {tumor_dir} ({len(list(tumor_dir.iterdir()))} files)")
    print(f"  normal_dir: {normal_dir} ({len(list(normal_dir.iterdir()))} files)")

    # ---- Step 1: score_external 给 LGG 打分 ----
    if not score_csv.exists() or args.skip_score is False:
        ok = run_subprocess("score_external (LGG tumor+normal)", [
            PYTHON, str(_CODE_DIR / "score_external.py"),
            "--ckpt",       str(ae_ckpt),
            "--model",      "ae",
            "--img-dir",    str(lgg_dir),       # 含 tumor/ + normal/ 子目录
            "--out-csv",    str(score_csv),
            "--split",      "lgg_heldout",
            "--label-mode", "by-subdir",        # tumor/->1, normal/->0
            "--device",     args.device,
            "--batch-size", str(args.batch_size),
            "--num-workers", "0",
        ])
        if not ok:
            raise RuntimeError("score_external failed")
    else:
        print(f"[m3] SKIP step1 (score_csv exists): {score_csv}")

    # ---- Step 2: conspicuity_proxy for tumor ----
    if not consp_tumor_csv.exists():
        # 调用 conspicuity_proxy 的内部函数（直接 import，不起子进程）
        print(f"\n[m3] START conspicuity_proxy (tumor)")

        class _Args:
            img_dir = str(tumor_dir)
            img_dirs = None
            score_csv = str(score_csv)
            filter_csv = None
            out_csv = str(consp_tumor_csv)

        run_conspicuity(_Args())
    else:
        print(f"[m3] SKIP step2 tumor (exists): {consp_tumor_csv}")

    # ---- Step 3: conspicuity_proxy for normal ----
    if not consp_norm_csv.exists():
        print(f"\n[m3] START conspicuity_proxy (normal)")

        class _ArgsNorm:
            img_dir = str(normal_dir)
            img_dirs = None
            score_csv = str(score_csv)
            filter_csv = None
            out_csv = str(consp_norm_csv)

        run_conspicuity(_ArgsNorm())
    else:
        print(f"[m3] SKIP step3 normal (exists): {consp_norm_csv}")

    # ---- Step 4: C4 risk-coverage on LGG (glcm_cluster_prom, 与主结果同列) ----
    print(f"\n[m3] START C4 risk-coverage (glcm_cluster_prom)")
    df_mixed = load_mixed_df(
        tumor_conspicuity_csv  = str(consp_tumor_csv),
        normal_conspicuity_csv = str(consp_norm_csv),
        score_csv              = str(score_csv),
    )
    print(f"[m3] mixed df: {len(df_mixed)} rows (LGG normal+tumor)")

    run_c4_risk_coverage(
        df_mixed,
        conspicuity_col = "glcm_cluster_prom",  # 与 BraTS 主结果同列，不换列
        out_path        = str(c4_csv),
    )

    # ---- Step 5: patient-level bootstrap CI ----
    print(f"\n[m3] START patient-level bootstrap CI (1000 resample, by patient)")
    # 需要 patient_dir 信息：从 manifest 读（若有）
    # manifest 含: filename, patient_dir, split, label, mask_px
    all_rows_with_pid = []
    if manifest_csv.exists():
        manifest_rows = read_csv_rows(manifest_csv)
        pid_map = {r["filename"]: r["patient_dir"] for r in manifest_rows}
    else:
        print(f"  [warn] manifest not found: {manifest_csv}, patient_dir will be unknown")
        pid_map = {}

    # 合并 score + conspicuity（tumor + normal）
    score_rows  = read_csv_rows(score_csv)
    consp_t     = read_csv_rows(consp_tumor_csv) if consp_tumor_csv.exists() else []
    consp_n     = read_csv_rows(consp_norm_csv)  if consp_norm_csv.exists()  else []
    consp_all   = {r["filename"]: r for r in (consp_t + consp_n)}

    for sr in score_rows:
        fname = sr["filename"]
        cr    = consp_all.get(fname, {})
        merged = {
            "filename":         fname,
            "patient_dir":      pid_map.get(fname, "unknown"),
            "label":            sr.get("label", -1),
            "anomaly_score":    sr.get("anomaly_score", float("nan")),
            "glcm_cluster_prom": cr.get("glcm_cluster_prom", float("nan")),
        }
        all_rows_with_pid.append(merged)

    ci_result = patient_level_bootstrap_auroc(
        rows          = all_rows_with_pid,
        conspicuity_col = "glcm_cluster_prom",
        n_bootstrap   = 1000,
        ci_level      = 0.95,
        rng_seed      = 42,
    )
    write_csv(bootstrap_csv, [ci_result])

    # ---- 汇总 ----
    print(f"\n{'='*60}")
    print(f"[m3] M-3 held-out pipeline COMPLETE")
    print(f"{'='*60}")
    print(f"  score csv:        {score_csv}")
    print(f"  consp tumor:      {consp_tumor_csv}")
    print(f"  consp normal:     {consp_norm_csv}")
    print(f"  C4 csv:           {c4_csv}")
    print(f"  bootstrap CI csv: {bootstrap_csv}")
    print(f"\n  Bootstrap CI (glcm_cluster_prom, 15-patient, 1000 resample):")
    print(f"    full AUROC:  {ci_result['full_auroc']}  "
          f"[{ci_result['bs_full_lo']}, {ci_result['bs_full_hi']}] 95% CI")
    print(f"    top50 AUROC: {ci_result['top50_auroc']}  "
          f"[{ci_result['bs_top50_lo']}, {ci_result['bs_top50_hi']}] 95% CI")
    print(f"    top10 AUROC: {ci_result['top10_auroc']}  "
          f"[{ci_result['bs_top10_lo']}, {ci_result['bs_top10_hi']}] 95% CI")
    print(f"    n_patients={ci_result['n_patients']}, n_slices={ci_result['n_slices']}")
    print(f"\n  NOTE: 数字由主线跑出实测，不含预填值。")
    print(f"        主线对照 BraTS 主结果 AUROC=0.8228 核复现方向。")


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="run_m3_heldout.py — M-3 LGG held-out C4 全链 orchestrator (CPU)"
    )
    _repo = Path(__file__).resolve().parent.parent
    _res  = _repo / "results"
    _data = _repo / "data"

    parser.add_argument("--ae-ckpt",
                        default=str(_res / "phase2" / "ae_s42" / "checkpoints" / "brats_ae_ep250.pt"),
                        help="BraTS AE ckpt 路径（run_seedfill.py ae_s42 产出）")
    parser.add_argument("--lgg-dir",
                        default=str(_data / "lgg_heldout"),
                        help="prep_lgg_heldout.py 产出目录（含 tumor/ normal/ 子目录）")
    parser.add_argument("--device", default="cpu",
                        help="score_external 推理设备（默认 cpu，228 切片分钟级）")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--skip-score", action="store_true",
                        help="跳过 score_external 步骤（score_csv 已存在时）")
    args = parser.parse_args()
    main(args)
