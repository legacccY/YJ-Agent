"""
run_seedfill.py — MedAD-FailMap Phase 2 seed-fill orchestrator (Python 版)

目标: 补齐 vae seed1/seed2 + memae seed1/seed2 共 4 个 run，
      使 vae/memae 各拥有 3 seeds (42/1/2)，凑 PR-5 confirmatory 方差带。

用法 (从项目根跑，或直接绝对路径调):
    python code/run_seedfill.py
    # 后台调用示例:
    python code/run_seedfill.py > results/phase2/seedfill_master.log 2>&1

预计时间: ~2h (单卡 RTX4070，每个 run ~30min x 4)

完整 5-step 命令链 (每个 run):
  1. train_recon_ae.py  -> train_log + ckpt + anomaly_scores + config
  2. stratify_eval.py   -> stratify_{size,contrast,interact,per_image}_{model}.csv
  3. stratify_significance.py (x3: P85/P90/P95)
  4. conspicuity_proxy.py (tumor only)
  5. incremental_stats.py (C2/C3/C4/FC)

幂等规则:
  - train_log 达 250 epoch 行 (含 header = 251 行) + anomaly_scores csv 存在 => skip
  - 否则 shutil.rmtree 清掉重跑

不启动训练: 此脚本由主线后台起，Coder 只交脚本
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

# ---- 路径常量 (绝对路径，不依赖 cwd) ----------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent          # code/
REPO_ROOT  = SCRIPT_DIR.parent                        # MedAD-FailMap/
DATA_DIR   = REPO_ROOT / "data"
RESULTS    = REPO_ROOT / "results"
PHASE2     = RESULTS / "phase2"

NORMAL_CONSPICUITY = RESULTS / "conspicuity_features_normal.csv"

# Python 解释器: 同 run_seedfill.py 自身用的解释器，保证 env 一致
PYTHON = sys.executable

# ---- 待填 run 列表 -----------------------------------------------------------
RUNS = [
    ("vae",   1),
    ("vae",   2),
    ("memae", 1),
    ("memae", 2),
]

# ---- 工具函数 ----------------------------------------------------------------

def is_run_complete(out_dir: Path, model: str) -> bool:
    """
    完整判定: train_log 达 250 epoch 行(含 header=251 行) + anomaly_scores 存在
    """
    log_csv   = out_dir / f"train_log_brats_{model}.csv"
    score_csv = out_dir / f"anomaly_scores_brats_{model}.csv"
    if not log_csv.exists() or not score_csv.exists():
        return False
    with open(log_csv, encoding="utf-8") as f:
        lines = sum(1 for _ in f)
    return lines >= 251  # 1 header + 250 epoch rows


def run_step(tag: str, step_n, label: str, cmd: list, log_fh) -> bool:
    """
    运行单步子进程。stdout/stderr 同时打印到 stdout + tee 到 log_fh。
    返回 True=成功, False=失败。
    """
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    print(f"[seedfill] START {tag} step{step_n}: {label}", flush=True)
    log_fh.write(f"\n>>> START {tag} step{step_n}: {label}\n")
    log_fh.write(f"    CMD: {' '.join(str(c) for c in cmd)}\n\n")
    log_fh.flush()

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        cwd=str(REPO_ROOT),   # cwd = 项目根
        encoding="utf-8",
        errors="replace",
    )
    for line in proc.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
        log_fh.write(line)
    proc.wait()

    if proc.returncode != 0:
        msg = f"[seedfill] ERROR {tag} step{step_n} exit={proc.returncode}"
        print(msg, flush=True)
        log_fh.write(msg + "\n")
        return False

    print(f"[seedfill] DONE  {tag} step{step_n}: {label}", flush=True)
    log_fh.write(f"[seedfill] DONE  {tag} step{step_n}: {label}\n")
    return True


# ---- 主逻辑 -----------------------------------------------------------------

def run_one(model: str, seed: int) -> bool:
    """
    运行单个 run 的完整 5-step 命令链。
    返回 True=成功, False=某步失败(已打印报错)。
    """
    tag    = f"{model}_s{seed}"
    outdir = PHASE2 / tag
    logfile = PHASE2 / f"{tag}.log"

    print(f"\n{'='*56}", flush=True)
    print(f"  RUN: {tag}  (model={model} seed={seed})", flush=True)
    print(f"{'='*56}", flush=True)

    # ---- 幂等检查 ----
    if is_run_complete(outdir, model):
        print(f"[seedfill] SKIP {tag}: already complete", flush=True)
        return True

    # ---- 半截目录清除 ----
    if outdir.exists():
        print(f"[seedfill] CLEAN {tag}: removing incomplete dir ...", flush=True)
        shutil.rmtree(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    with open(logfile, "w", encoding="utf-8") as log_fh:
        log_fh.write(f"# seedfill log: {tag}\n\n")

        # ---- STEP 1: 训练 ----
        ok = run_step(tag, 1, "train_recon_ae", [
            PYTHON, str(SCRIPT_DIR / "train_recon_ae.py"),
            "-d", "brats",
            "-m", model,
            "--seed", str(seed),
            "--out-dir", str(outdir),
            "-g", "0",
            "--data-root", str(DATA_DIR),
        ], log_fh)
        if not ok:
            print(f"[seedfill] FAIL {tag} at step1, skipping remaining steps", flush=True)
            return False

        # ---- STEP 2: stratify_eval ----
        ok = run_step(tag, 2, "stratify_eval", [
            PYTHON, str(SCRIPT_DIR / "stratify_eval.py"),
            "--score-csv",     str(outdir / f"anomaly_scores_brats_{model}.csv"),
            "--mask-dir",      str(DATA_DIR / "BraTS2021" / "test" / "annotation"),
            "--tumor-img-dir", str(DATA_DIR / "BraTS2021" / "test" / "tumor"),
            "--out-dir",       str(outdir),
            "--model-tag",     model,
        ], log_fh)
        if not ok:
            print(f"[seedfill] FAIL {tag} at step2, skipping remaining steps", flush=True)
            return False

        # ---- STEP 3: stratify_significance x3 (P85/P90/P95) ----
        for pct in [85, 90, 95]:
            ok = run_step(tag, f"3-P{pct}", f"stratify_significance P{pct}", [
                PYTHON, str(SCRIPT_DIR / "stratify_significance.py"),
                "--score-csv",           str(outdir / f"anomaly_scores_brats_{model}.csv"),
                "--strat-per-image-csv", str(outdir / f"stratify_per_image_{model}.csv"),
                "--out-csv",             str(outdir / f"stratify_significance_FA_{model}_P{pct}.csv"),
                "--threshold-pct",       str(pct),
            ], log_fh)
            if not ok:
                print(f"[seedfill] FAIL {tag} at step3-P{pct}, skipping remaining steps", flush=True)
                return False

        # ---- STEP 4: conspicuity_proxy (tumor only) ----
        ok = run_step(tag, 4, "conspicuity_proxy tumor", [
            PYTHON, str(SCRIPT_DIR / "conspicuity_proxy.py"),
            "--img-dir",   str(DATA_DIR / "BraTS2021" / "test" / "tumor"),
            "--score-csv", str(outdir / f"anomaly_scores_brats_{model}.csv"),
            "--out-csv",   str(outdir / f"conspicuity_features_tumor_{model}.csv"),
        ], log_fh)
        if not ok:
            print(f"[seedfill] FAIL {tag} at step4, skipping remaining steps", flush=True)
            return False

        # ---- STEP 5: incremental_stats (C2/C3/C4/FC) ----
        # 注: --stratify-csv 传 stratify_per_image_<model>.csv (含 filename/size_px/contrast)
        #     非 stratify_interact (聚合桶无 filename，join 不上，会导致 covariate_cols=[] 漏传)
        ok = run_step(tag, 5, "incremental_stats", [
            PYTHON, str(SCRIPT_DIR / "incremental_stats.py"),
            "--conspicuity-csv",        str(outdir / f"conspicuity_features_tumor_{model}.csv"),
            "--stratify-csv",           str(outdir / f"stratify_per_image_{model}.csv"),
            "--normal-conspicuity-csv", str(NORMAL_CONSPICUITY),
            "--score-csv",              str(outdir / f"anomaly_scores_brats_{model}.csv"),
            "--out-dir",                str(outdir),
        ], log_fh)
        if not ok:
            print(f"[seedfill] FAIL {tag} at step5", flush=True)
            return False

    print(f"[seedfill] COMPLETE {tag}", flush=True)
    return True


def main():
    PHASE2.mkdir(parents=True, exist_ok=True)

    print("[seedfill] MedAD-FailMap Phase 2 seed-fill start", flush=True)
    print(f"[seedfill] REPO_ROOT  = {REPO_ROOT}", flush=True)
    print(f"[seedfill] PYTHON     = {PYTHON}", flush=True)
    print(f"[seedfill] DATA_DIR   = {DATA_DIR}", flush=True)
    print(f"[seedfill] PHASE2     = {PHASE2}", flush=True)
    print(f"[seedfill] normal_conspicuity = {NORMAL_CONSPICUITY}", flush=True)
    print(f"[seedfill] runs = {RUNS}", flush=True)

    results = {}
    for model, seed in RUNS:
        tag = f"{model}_s{seed}"
        ok = run_one(model, seed)
        results[tag] = ok

    # ---- 汇总 ----
    print(f"\n{'='*56}", flush=True)
    print("[seedfill] SUMMARY", flush=True)
    ok_list   = [t for t, v in results.items() if v]
    fail_list = [t for t, v in results.items() if not v]
    for tag in ok_list:
        print(f"  OK   {tag}", flush=True)
    for tag in fail_list:
        print(f"  FAIL {tag}", flush=True)
    print(f"{'='*56}", flush=True)

    if fail_list:
        sys.exit(1)


if __name__ == "__main__":
    main()
