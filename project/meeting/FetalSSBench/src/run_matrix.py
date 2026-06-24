"""
run_matrix.py
=============
生成/展示 FetalSSBench 150-run 实验矩阵。

不直接跑训练，只输出 runlist.json 供主线按顺序逐条调用。

用法：
  # 生成完整 runlist.json（150 run）
  python run_matrix.py

  # 过滤：只看某 dataset / method
  python run_matrix.py --dataset hc18
  python run_matrix.py --method cps --dataset psfhs

  # 查看哪些已跑（对照 results/state.json）
  python run_matrix.py --status

  # 生成特定 dataset 的子 runlist
  python run_matrix.py --dataset hc18 --out runlist_hc18.json

输出字段（每条 run）：
  run_id     - 唯一标识，供主线去重
  method     - supervised/mean_teacher/cps/uamt/fixmatch
  dataset    - psfhs/hc18
  ratio      - 标注比例（float）
  seed       - 实验 seed
  cmd        - 直接可跑的命令字符串（供主线复制执行）
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

_SRC_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SRC_DIR))

# 从 harness 导入矩阵定义（避免重复定义）
from harness import METHODS, DATASETS, LABEL_RATIOS, SEEDS, N_EPOCHS

RESULTS_DIR = _SRC_DIR / "results"
STATE_JSON = RESULTS_DIR / "state.json"
DEFAULT_RUNLIST = _SRC_DIR / "runlist.json"


def build_matrix(
    methods: Optional[List[str]] = None,
    datasets: Optional[List[str]] = None,
    ratios: Optional[List[float]] = None,
    seeds: Optional[List[int]] = None,
) -> List[Dict]:
    """
    生成实验矩阵（笛卡尔积），返回 run 列表。
    默认：5方法 × 2数据集 × 5比例 × 3seed = 150 run
    """
    methods = methods or METHODS
    datasets = datasets or DATASETS
    ratios = ratios or LABEL_RATIOS
    seeds = seeds or SEEDS

    runs = []
    for ds in datasets:
        for method in methods:
            for ratio in ratios:
                for seed in seeds:
                    run_id = f"{method}_{ds}_r{int(ratio*100):03d}_s{seed}"
                    cmd = (
                        f"python src/harness.py "
                        f"--method {method} "
                        f"--dataset {ds} "
                        f"--ratio {ratio} "
                        f"--seed {seed} "
                        f"--epochs {N_EPOCHS}"
                    )
                    runs.append({
                        "run_id": run_id,
                        "method": method,
                        "dataset": ds,
                        "ratio": ratio,
                        "seed": seed,
                        "epochs": N_EPOCHS,
                        "cmd": cmd,
                    })
    return runs


def load_done_set() -> set:
    """从 state.json 读已跑完的 run_id 集合。"""
    if not STATE_JSON.exists():
        return set()
    try:
        with open(STATE_JSON, "r", encoding="utf-8") as f:
            state = json.load(f)
        return set(state.get("runs_done", []))
    except Exception:
        return set()


def print_matrix(runs: List[Dict], done_set: set, show_status: bool = False):
    """打印 run 矩阵概览。"""
    total = len(runs)
    done = sum(1 for r in runs if r["run_id"] in done_set)
    pending = total - done

    print(f"\n{'='*70}")
    print(f"FetalSSBench 实验矩阵  总计={total}  已完成={done}  待跑={pending}")
    print(f"{'='*70}")

    if show_status:
        print(f"\n{'run_id':<50} {'状态'}")
        print("-" * 60)
        for r in runs:
            status = "DONE" if r["run_id"] in done_set else "TODO"
            print(f"{r['run_id']:<50} {status}")
    else:
        # 按 dataset+method 分组展示
        from collections import defaultdict
        grouped = defaultdict(list)
        for r in runs:
            key = f"{r['dataset']}/{r['method']}"
            grouped[key].append(r)

        print(f"\n{'dataset/method':<30} {'runs':<8} {'done':<8} {'pending'}")
        print("-" * 55)
        for key in sorted(grouped.keys()):
            grp = grouped[key]
            g_done = sum(1 for r in grp if r["run_id"] in done_set)
            g_pending = len(grp) - g_done
            print(f"{key:<30} {len(grp):<8} {g_done:<8} {g_pending}")

    print(f"\n命令示例（第一条待跑 run）：")
    first_todo = next((r for r in runs if r["run_id"] not in done_set), None)
    if first_todo:
        print(f"  {first_todo['cmd']}")
    else:
        print("  [所有 run 已完成]")

    print(f"\n烟测命令（每个方法 × 每个数据集）：")
    seen = set()
    for r in runs:
        key = f"{r['method']}_{r['dataset']}"
        if key not in seen:
            seen.add(key)
            quick_cmd = (
                f"python src/harness.py "
                f"--method {r['method']} "
                f"--dataset {r['dataset']} "
                f"--ratio 0.05 "
                f"--seed 0 "
                f"--quick"
            )
            print(f"  {quick_cmd}")


def main():
    parser = argparse.ArgumentParser(description="FetalSSBench 实验矩阵生成器")
    parser.add_argument("--method", nargs="+", choices=METHODS,
                        help="过滤方法（默认全部）")
    parser.add_argument("--dataset", nargs="+", choices=DATASETS,
                        help="过滤数据集（默认全部）")
    parser.add_argument("--ratio", nargs="+", type=float,
                        help="过滤标注比例（默认全部）")
    parser.add_argument("--seed", nargs="+", type=int,
                        help="过滤 seed（默认全部）")
    parser.add_argument("--status", action="store_true",
                        help="显示每个 run 的完成状态")
    parser.add_argument("--out", type=str, default=None,
                        help=f"输出 runlist JSON 路径（默认 {DEFAULT_RUNLIST}）")
    parser.add_argument("--pending_only", action="store_true",
                        help="runlist 只包含未跑的 run")
    args = parser.parse_args()

    runs = build_matrix(
        methods=args.method,
        datasets=args.dataset,
        ratios=args.ratio,
        seeds=args.seed,
    )

    done_set = load_done_set()
    print_matrix(runs, done_set, show_status=args.status)

    # 写 runlist.json
    if args.pending_only:
        out_runs = [r for r in runs if r["run_id"] not in done_set]
    else:
        out_runs = runs

    out_path = Path(args.out) if args.out else DEFAULT_RUNLIST
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"total": len(out_runs), "runs": out_runs}, f, indent=2, ensure_ascii=False)

    print(f"\n[matrix] runlist 写入: {out_path}（{len(out_runs)} run）")
    print("[matrix] 主线逐条执行：for run in runlist['runs']: subprocess.run(run['cmd'])")
    print("[matrix] 或用 /loop /run-experiment 按 harness.py 接口启动")


if __name__ == "__main__":
    main()
