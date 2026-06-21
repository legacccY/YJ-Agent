"""
mqar_merge_verdict.py — 合并 4 臂独立 csv，计算并输出最终 verdict
======================================================================
在全部 array task 跑完后由主线调用：

    python scripts/mqar_merge_verdict.py

功能：
  1. 读取 outputs/route2_budget/arm_*/mqar_results.csv（4 臂各一个）
  2. 去重 header 后合并成 outputs/route2_budget/mqar_results.csv
  3. 调 mqar_capacity_probe.compute_verdict(merged_csv, prereg_delta=0.15)
  4. 写 outputs/route2_budget/mqar_verdict.json
  5. 打印 verdict + sanity_gate.detail(三臂 n=4) + gap_la/gap_gla 表 + delta_nonspecific

红线：
  - 只合并不重算各 config（compute_verdict 内部自己按 arm/n_kv/seed 聚合）
  - 纯 numpy，禁 scipy.stats（OMP red-line）
  - 不改 compute_verdict 判据逻辑

路径规约：
  - 脚本放 scripts/，但 cwd = project root（/gpfs/work/bio/jiayu2403/gdn2vessel/）
  - _ROOT = scripts/ 的上两层 = project root（同 mqar_capacity_probe.py 约定）
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Project path resolution（对齐 mqar_capacity_probe.py 的 sys.path 处理）
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve()          # scripts/mqar_merge_verdict.py
_ROOT = _HERE.parent.parent               # project root（gdn2vessel/）
_SRC  = _ROOT / 'src'
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from benchmark.mqar_capacity_probe import compute_verdict  # noqa: E402


# ---------------------------------------------------------------------------
# 路径常量
# ---------------------------------------------------------------------------
ARMS = ('gdn2', 'gla', 'linear_attn', 'gdn2_fla')
OUT_BASE   = _ROOT / 'outputs' / 'route2_budget'
MERGED_CSV = OUT_BASE / 'mqar_results.csv'
VERDICT_JSON = OUT_BASE / 'mqar_verdict.json'

FIELDNAMES = ['arm', 'n_kv', 'd_head', 'lr', 'seed', 'final_acc', 'steps', 'converged']


# ---------------------------------------------------------------------------
# 合并 4 臂 csv
# ---------------------------------------------------------------------------
def merge_arm_csvs() -> int:
    """
    读取 arm_*/mqar_results.csv，去重 header，合并写入 MERGED_CSV。
    返回合并后总行数（不含 header）。
    """
    OUT_BASE.mkdir(parents=True, exist_ok=True)

    all_rows: list[dict] = []
    missing_arms: list[str] = []

    for arm in ARMS:
        arm_csv = OUT_BASE / f'arm_{arm}' / 'mqar_results.csv'
        if not arm_csv.exists():
            print(f"[merge] WARN: arm csv not found: {arm_csv}")
            missing_arms.append(arm)
            continue
        with open(arm_csv, 'r', newline='') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        print(f"[merge] arm={arm}: {len(rows)} rows from {arm_csv}")
        all_rows.extend(rows)

    if missing_arms:
        print(f"[merge] WARNING: missing arms: {missing_arms}. "
              f"Verdict will be computed on available data only.")

    if not all_rows:
        print("[merge] ERROR: no rows found from any arm csv. Abort.")
        sys.exit(1)

    with open(MERGED_CSV, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"[merge] Merged {len(all_rows)} rows -> {MERGED_CSV}")
    return len(all_rows)


# ---------------------------------------------------------------------------
# 打印 verdict 摘要
# ---------------------------------------------------------------------------
def print_verdict_summary(v: dict) -> None:
    print("\n" + "=" * 60)
    print(f"  VERDICT: {v['verdict']}")
    print(f"  prereg_delta = {v['prereg_delta']}")
    print("=" * 60)

    # Sanity gate
    sg = v['sanity_gate']
    print(f"\n[sanity_gate] pass={sg['pass']}  threshold={sg['threshold']}")
    for arm, d in sg['detail'].items():
        flag = "PASS" if d['pass'] else "FAIL"
        mean_str = f"{d['mean']:.4f}" if d['mean'] is not None else "N/A"
        print(f"  n=4  arm={arm:<14}  mean_acc={mean_str}  [{flag}]")

    # gap table: n in {4, 8, 16, 32, 64, 96}
    print("\n[gap_table]  n_kv | acc_gdn2 | acc_gla  | acc_la   | gap_la  | gap_gla")
    print("             " + "-" * 56)
    gap_table = v.get('gap_table', {})
    for n_str in sorted(gap_table.keys(), key=int):
        e = gap_table[n_str]
        def fmt(x): return f"{x:.4f}" if x is not None else "  N/A  "
        print(
            f"  n={int(n_str):<5} | {fmt(e['acc_gdn2'])} | {fmt(e['acc_gla'])} | "
            f"{fmt(e['acc_la'])} | {fmt(e['gap_la'])} | {fmt(e['gap_gla'])}"
        )

    # Live windows
    lw = v.get('live_windows', [])
    if lw:
        print(f"\n[live_windows] found {len(lw)} window(s):")
        for w in lw:
            print(
                f"  n={w['n_kv']}  gap_la={w['gap_la']:.4f}  gap_gla={w['gap_gla']:.4f}"
                f"  acc_gdn2={w['acc_gdn2']:.4f}  acc_gla={w['acc_gla']:.4f}"
                f"  acc_la={w['acc_la']:.4f}"
            )
    else:
        print("\n[live_windows] none")

    # delta_nonspecific
    if v.get('delta_nonspecific'):
        print(f"\n[delta_nonspecific] TRUE — {v['delta_nonspecific_msg']}")
    else:
        print("\n[delta_nonspecific] False (delta-rule specificity intact)")

    # gdn2_fla reference
    fla_ref = v.get('gdn2_fla_reference')
    if fla_ref:
        print("\n[gdn2_fla_reference]  n_kv | mean_acc | std")
        for n_str in sorted(fla_ref.keys(), key=int):
            s = fla_ref[n_str]
            print(f"  n={int(n_str):<5} | {s['mean']:.4f}   | {s.get('std', 0.0):.4f}")
    else:
        print("\n[gdn2_fla_reference] not available (arm missing or not run)")

    print(f"\n[merge_verdict] Verdict JSON: {VERDICT_JSON}\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    print("[merge_verdict] Merging arm CSVs...")
    n_rows = merge_arm_csvs()

    print(f"[merge_verdict] Computing verdict on {n_rows} rows...")
    # random_baseline = 1 / (V/2) = 1/4096 for vocab=8192
    random_baseline = 1.0 / 4096

    v = compute_verdict(MERGED_CSV, prereg_delta=0.15)
    v['random_baseline'] = random_baseline

    with open(VERDICT_JSON, 'w') as f:
        json.dump(v, f, indent=2)

    print_verdict_summary(v)


if __name__ == '__main__':
    main()
