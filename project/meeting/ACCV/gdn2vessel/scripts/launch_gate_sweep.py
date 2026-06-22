"""
launch_gate_sweep.py — 路B Frangi门 gate 正式 12run 批量启动器。

矩阵（ACCEPTANCE 路B命门预登记，2026-06-22 写死，禁改）：
  arm  ∈ {gate-on (--use_frangi 1), gate-off (--use_frangi 0)}
  dataset ∈ {drive, chase}
  seed ∈ {0, 1, 2}
  memory_mode 固定 delta_rule（--reid_feat_source memory，A2 臂载体）
  severity 固定 Medium
  = 2 × 2 × 3 = 12 run（≈6-15 GPU·h）

benchmark 接口（生产模式）：
  --benchmark_dir 指扁平 benchmark_cache 目录（含 manifest.json），
  按 --dataset + --severity 自动过滤全 test set 多图。
  烟测用的 --benchmark_npz 单图模式不在此。
  ⚠️ DRIVE benchmark NPZ 截至 2026-06-22 主线仍在 precompute 中，
     提交前确认 drive_Medium_*.npz + manifest.json 已在 benchmark_cache。

epoch 设计：
  EPOCHS = 200  # 用户 2026-06-22 拍板：路A 300 太猛 / 100 欠训，折中 200 充分收敛判 clDice

使用（dry-run 验证命令，不真提交）：
  python scripts/launch_gate_sweep.py --dry-run

真提交由主线串行（经 gpu_slot.py 卡槽调度 + 拍板点）：
  python tools/gpu_slot.py request gdn2vessel hpc 1 "gate_sweep 12run"
  # GO <id> → 主线逐 run 提交 gate_job.sbatch 实例

DEP 清单：
  [DEP-G1] DRIVE benchmark_cache 需先 precompute_benchmark.py 生成
            (drive_Medium_*.npz + manifest.json，2026-06-22 主线正进行)
  [DEP-G2] CHASE benchmark 已冻结 8 NPZ（Entry14）✓ 可直接跑
  [DEP-G3] seed 前缀防碰撞：gate_frangi_verdict 按 (image_id, seed) 配对，
            12 run output_dir 命名已含 arm+dataset+seed 独立隔离，
            verdict 读 csv 时须各 run 独立 → verdict 按 seed 列配对无需再加前缀
            （image_id × seed 天然唯一，与 launch_reid_sweep DEP-3 情形一致）

sbatch 实例化：
  主线用本脚本打印的 --cmd 实例化 scripts/gate_job.sbatch.template 各占位符，
  逐 run 上传 HPC，单独提交（不批量并发）。

红线（与 launch_reid_sweep 一致）：
  - 真提交 _submit_single_run_DISABLED 函数抛 NotImplementedError
  - 主线经卡槽调度 + 拍板点后才启
  - 不自动调 gate_frangi_verdict（12run 全 done 后主线串行跑）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

# ─────────────────────────────────────────────────────────────────────────────
# 集中配置区（只改此处，全脚本生效）
# ─────────────────────────────────────────────────────────────────────────────

HPC_PROJECT_ROOT = "/gpfs/work/bio/jiayu2403/gdn2vessel"
TRAIN_SCRIPT     = f"{HPC_PROJECT_ROOT}/src/train_reid_pilot.py"

# 数据根（per-set）
DATA_ROOT_BASE = "/gpfs/work/bio/jiayu2403/gdn2vessel/data/vessel"

# benchmark_cache：扁平单目录（同 launch_reid_sweep，Entry14 recon 确认）
BENCH_CACHE_DIR = "/gpfs/work/bio/jiayu2403/gdn2vessel/data/benchmark_cache"

# 路B gate 矩阵（ACCEPTANCE 预登记锁定，禁改）
GATE_ARMS = [
    {"label": "gate-on",  "use_frangi": 1},
    {"label": "gate-off", "use_frangi": 0},
]
DATASETS: List[str] = ["drive", "chase"]

DATASET_CONFIG = {
    "drive": {
        "data_root": f"{DATA_ROOT_BASE}/DRIVE",
        "benchmark_dir": BENCH_CACHE_DIR,
        # DEP-G1: DRIVE benchmark 2026-06-22 主线正 precompute，提交前确认
    },
    "chase": {
        "data_root": f"{DATA_ROOT_BASE}/CHASE",
        "benchmark_dir": BENCH_CACHE_DIR,
        # DEP-G2: CHASE 已冻结 8 NPZ ✓
    },
}

SEEDS: List[int] = [0, 1, 2]   # 路B 命门预登记：3 seed

# 固定参数
SEVERITY       = "Medium"        # 路B ACCEPTANCE 单 severity 防伪重复
REID_FEAT_SRC  = "memory"        # memory_mode=delta_rule，A2 载体
NO_USE_LOC_FEAT = True           # A-v2 M-A：memory-only head（同路A）

# 用户 2026-06-22 拍板：路A 300 太猛 / 100 欠训，折中 200 充分收敛判 clDice
EPOCHS = 200

# 输出根（HPC 端）
OUTPUT_ROOT = f"{HPC_PROJECT_ROOT}/outputs/gate_sweep"

# ─────────────────────────────────────────────────────────────────────────────
# 命令生成
# ─────────────────────────────────────────────────────────────────────────────

def make_output_dir(arm_label: str, dataset: str, seed: int) -> str:
    """
    生成独立 output_dir，命名含 arm+dataset+seed。
    示例：outputs/gate_sweep/gate_on_drive_s0/
    防碰撞：12 run 各独立目录，gate_frangi_verdict 按 seed 列配对无歧义。
    """
    # 转 arm_label 为文件系统安全名（gate-on → gate_on）
    arm_safe = arm_label.replace("-", "_")
    return f"{OUTPUT_ROOT}/{arm_safe}_{dataset}_s{seed}"


def make_run_command(arm: dict, dataset: str, seed: int) -> str:
    """
    拼单条 train_reid_pilot 命令。
    gate-on/off 唯一变量 = --use_frangi {1,0}，其余完全一致。
    """
    cfg = DATASET_CONFIG[dataset]
    out_dir = make_output_dir(arm["label"], dataset, seed)
    cmd_parts = [
        f"python {TRAIN_SCRIPT}",
        f"--reid_feat_source {REID_FEAT_SRC}",
        f"--use_frangi {arm['use_frangi']}",
        f"--data_root {cfg['data_root']}",
        f"--benchmark_dir {cfg['benchmark_dir']}",
        f"--dataset {dataset}",
        f"--severity {SEVERITY}",
        f"--epochs {EPOCHS}",
        f"--seed {seed}",
        f"--output_dir {out_dir}",
    ]
    if NO_USE_LOC_FEAT:
        cmd_parts.insert(3, "--no_use_loc_feat")
    return " ".join(cmd_parts)


def build_run_matrix() -> List[dict]:
    """
    返回 12 run 字典列表。
    排列顺序：arm × dataset × seed（外→内），便于逐 run 提交。
    """
    runs = []
    run_idx = 1
    for arm in GATE_ARMS:
        for dataset in DATASETS:
            for seed in SEEDS:
                out_dir = make_output_dir(arm["label"], dataset, seed)
                runs.append({
                    "run_id":     run_idx,
                    "arm_label":  arm["label"],
                    "use_frangi": arm["use_frangi"],
                    "dataset":    dataset,
                    "seed":       seed,
                    "command":    make_run_command(arm, dataset, seed),
                    "output_dir": out_dir,
                    "expected_outputs": [
                        f"{out_dir}/reid_results.csv",
                        f"{out_dir}/state.json",
                    ],
                    # sbatch 实例化所需占位符值（主线替换 gate_job.sbatch.template）
                    "sbatch_placeholders": {
                        "ARM_LABEL": arm["label"],
                        "USE_FRANGI": str(arm["use_frangi"]),
                        "DATASET":   dataset,
                        "SEED":      str(seed),
                        "DATA_ROOT": DATASET_CONFIG[dataset]["data_root"],
                        "BENCH_DIR": DATASET_CONFIG[dataset]["benchmark_dir"],
                        "OUT_DIR":   out_dir,
                        "EPOCHS":    str(EPOCHS),
                    },
                })
                run_idx += 1
    return runs


# ─────────────────────────────────────────────────────────────────────────────
# Verdict 聚合命令（12 run done 后，主线串行跑）
# ─────────────────────────────────────────────────────────────────────────────

def make_verdict_command() -> str:
    """
    生成 gate_frangi_verdict.py 聚合命令。
    读全 12 run 的 reid_results.csv（--csv_dir 递归搜）。
    注：verdict 按 (image_id, seed) 列配对，12 run output_dir 各含 arm+dataset+seed 标识，
    reid_results.csv 内有 seed 列 → 配对无歧义，无需额外 seed 前缀（与 DEP-G3 一致）。
    """
    verdict_out = f"{HPC_PROJECT_ROOT}/outputs/gate_verdict/gate_frangi_verdict.json"
    return (
        f"# ── 待主线 12 run 全 done 后执行 ──\n"
        f"mkdir -p {HPC_PROJECT_ROOT}/outputs/gate_verdict\n"
        f"python {HPC_PROJECT_ROOT}/scripts/gate_frangi_verdict.py \\\n"
        f"    --csv_dir {OUTPUT_ROOT} \\\n"
        f"    --datasets drive chase \\\n"
        f"    --out_json {verdict_out}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 真提交存根（默认禁用，主线串行+卡槽调度+拍板点才启）
# ─────────────────────────────────────────────────────────────────────────────

def _submit_single_run_DISABLED(run: dict) -> None:
    """
    真提交存根。禁用，主线经 gpu_slot.py 卡槽调度后才启。

    主线流程：
      1. python tools/gpu_slot.py request gdn2vessel hpc 1 "gate_sweep 12run"
      2. GO <id> → 逐 run 实例化 gate_job.sbatch.template（替换占位符）
      3. dos2unix 去 CRLF（防 HPC CRLF 报错）
      4. 逐一 sbatch <run_id>_gate_<arm>_<ds>_s<seed>.sbatch（单独提交不并发）
      5. 看 logs/*.out 确认真跑（不信 jobid）
      6. 全 done 后 python tools/gpu_slot.py release <id>
      7. 跑 make_verdict_command() 的聚合命令 → gate_frangi_verdict.json
    """
    raise NotImplementedError(
        "真提交已禁用。主线经 gpu_slot.py 卡槽调度 + 拍板点后才启。\n"
        "见 scripts/launch_gate_sweep.py 头注 + scripts/gate_job.sbatch.template。"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Dry-run 打印
# ─────────────────────────────────────────────────────────────────────────────

def dry_run(runs: List[dict]) -> None:
    """打印 12 run 命令 + output_dir + 预期产出 + sbatch 占位符。不执行提交。"""
    print(f"\n{'='*72}")
    print(f"[DRY-RUN] gdn2vessel 路B gate 正式扫矩阵 — 12 run")
    print(f"  arm×dataset×seed = {len(GATE_ARMS)}×{len(DATASETS)}×{len(SEEDS)}")
    print(f"  reid_feat_source={REID_FEAT_SRC}  severity={SEVERITY}  epochs={EPOCHS}")
    print(f"  seeds={SEEDS}")
    print(f"  OUTPUT_ROOT={OUTPUT_ROOT}")
    print(f"\n  epoch={EPOCHS}（用户 2026-06-22 拍板，路A 300 折中 / 充分收敛判 clDice）")
    print(f"{'='*72}\n")

    for run in runs:
        print(f"── Run {run['run_id']:02d}/12 ──────────────────────────────────────────────")
        print(f"   arm={run['arm_label']}  use_frangi={run['use_frangi']}  "
              f"dataset={run['dataset']}  seed={run['seed']}")
        print(f"   output_dir: {run['output_dir']}")
        print(f"   expected:   {run['expected_outputs'][0]}")
        print(f"               {run['expected_outputs'][1]}")
        print(f"   CMD: {run['command']}")
        # sbatch 实例化占位符
        ph = run["sbatch_placeholders"]
        print(f"   sbatch 占位符 (→ gate_job.sbatch.template):")
        for k, v in ph.items():
            print(f"     {{{k}}} = {v}")
        print()

    # DEP 清单
    print(f"{'='*72}")
    print(f"[汇总] 共 12 run  |  reid_feat_source={REID_FEAT_SRC}  "
          f"severity={SEVERITY}  epochs={EPOCHS}")
    print(f"  output 格式: {OUTPUT_ROOT}/{{arm}}_{{dataset}}_s{{seed}}/")
    print(f"  每 run 产出: reid_results.csv（含 cldice/epsilon_beta0/betti_err_total/seed 列）"
          f" + state.json")
    print()
    print("DEPENDENCY 清单（提交前必过）:")
    print("  [DEP-G1] DRIVE benchmark_cache: 2026-06-22 主线正 precompute")
    print("           必须 drive_Medium_*.npz + manifest.json 到位才能提交 DRIVE 6 run")
    print("           CHASE 已冻结（Entry14）✓ → CHASE 6 run 可先提交")
    print("  [DEP-G2] benchmark 接口确认: --benchmark_dir 生产模式（全 test set）✓")
    print("           manifest.json 按 dataset+severity 过滤，非单图 --benchmark_npz")
    print("  [DEP-G3] seed 配对: reid_results.csv 含 seed 列，gate_frangi_verdict")
    print("           按 (image_id, seed) 配对，12 run 各独立 output_dir 无碰撞")
    print("  [DEP-G4] venv 路径（Entry1 踩坑）: source /gpfs/work/bio/jiayu2403/gdn2venv/bin/activate")
    print("           注意 jiayu2403/ 而非 gdn2vessel/ 下")
    print()
    print("── 卡槽调度（提交前必做）─────────────────────────────────────────────")
    print("  python tools/gpu_slot.py request gdn2vessel hpc 1 \"gate_sweep 12run\"")
    print("  GO <id> → 逐 run 实例化 gate_job.sbatch.template，单独提交")
    print("  完成后 python tools/gpu_slot.py release <id>")
    print()
    print("── Verdict 聚合命令（12 run 全 done 后执行，主线串行）────────────────")
    print(make_verdict_command())
    print(f"\n{'='*72}")
    print("[DRY-RUN 完成] 未执行任何真实提交。")
    print(f"{'='*72}\n")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description=(
            "gdn2vessel 路B gate 正式 12run 批量启动器。\n"
            "默认 --dry-run：只打印，不真提交。"
        )
    )
    p.add_argument(
        "--dry-run", "--dry_run",
        action="store_true",
        default=True,
        help="只打印命令，不真提交（默认 ON）",
    )
    p.add_argument(
        "--no-dry-run", "--no_dry_run",
        dest="dry_run",
        action="store_false",
        help="关闭 dry-run → 触发 NotImplementedError（真提交由主线串行）",
    )
    return p.parse_args()


def main():
    args = parse_args()
    runs = build_run_matrix()

    if args.dry_run:
        dry_run(runs)
    else:
        raise NotImplementedError(
            "真提交已禁用。\n"
            "主线流程: gpu_slot.py request → GO → 逐 run 实例化 gate_job.sbatch.template "
            "→ dos2unix → 单独 sbatch → release。\n"
            "见 scripts/launch_gate_sweep.py 头注 + scripts/gate_job.sbatch.template。"
        )


if __name__ == "__main__":
    main()
