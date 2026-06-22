"""
gate_smoke.py — 路B Frangi门 gate-on/off 本地 e2e 烟测脚本。

目的：验证
  1. gate-on  (--use_frangi 1) 和 gate-off (--use_frangi 0) 在 DRIVE 单 run
     1 epoch 各能跑通（不 NaN，不 crash）。
  2. 输出目录含 reid_results.csv，且有 epsilon_beta0 / betti_err_total 列。
  3. Frangi 门数值稳定（clDice/ε_β0/Betti 均非全 NaN）。

此脚本**你（coder）不跑**，交主线串行烟测（见回执 README）。
主线跑命令（DRIVE 单 run，HPC or local）：

  # gate-on
  python scripts/gate_smoke.py --data_root <DRIVE_ROOT> --benchmark_npz <NPZ> \\
      --arm gate-on --output_dir outputs/gate_smoke_on

  # gate-off
  python scripts/gate_smoke.py --data_root <DRIVE_ROOT> --benchmark_npz <NPZ> \\
      --arm gate-off --output_dir outputs/gate_smoke_off

  # 对照验证（用 verdict 脚本检查 smoke 输出方向）：
  python scripts/gate_frangi_verdict.py \\
      --csv_files outputs/gate_smoke_on/gate_metrics.csv \\
                  outputs/gate_smoke_off/gate_metrics.csv \\
      --out_json outputs/gate_smoke_verdict.json

内部实现：
  调用 subprocess.run(sys.executable, 'src/train_reid_pilot.py', ...) 跑 1 epoch。
  读取输出 reid_results.csv，转化为 gate_metrics.csv（补 arm/seed 列）。
  打印 clDice/ε_β0/Betti 的 per-image 均值。
  不含 NaN 即判 SMOKE_PASS。

Windows 兼容：spawn 不需要，subprocess 足够（只启 1 次训练进程）。
路径全 pathlib。

红线：不跑此脚本本身——这是主线的事。
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

import numpy as np


def parse_args():
    p = argparse.ArgumentParser(description='路B Frangi门 gate-on/off e2e 烟测')
    p.add_argument('--data_root', type=str, required=True,
                   help='DRIVE data root (passed to train_reid_pilot --data_root)')
    p.add_argument('--benchmark_npz', type=str, required=True,
                   help='单个预冻结 NPZ (--benchmark_npz, smoke 模式)')
    p.add_argument('--arm', type=str, required=True,
                   choices=['gate-on', 'gate-off'],
                   help='测哪个臂：gate-on (--use_frangi 1) 或 gate-off (--use_frangi 0)')
    p.add_argument('--output_dir', type=str, default='outputs/gate_smoke',
                   help='输出目录')
    p.add_argument('--dataset', type=str, default='drive',
                   choices=['drive', 'chase', 'stare', 'hrf', 'fives'])
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--epochs', type=int, default=1,
                   help='烟测 epoch 数（默认 1，验通算子用）')
    p.add_argument('--smoke_train', action='store_true',
                   help='内部传 --smoke 给 train_reid_pilot（仅 2 mini-step，无 benchmark）')
    p.add_argument('--src_dir', type=str, default='src',
                   help='train_reid_pilot.py 所在目录（相对路径或绝对路径）')
    return p.parse_args()


def run_train_arm(args, use_frangi_val: int) -> Path:
    """
    调 train_reid_pilot.py 跑 1 epoch，返回输出目录 Path。
    """
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    src = Path(args.src_dir) / 'train_reid_pilot.py'
    cmd = [
        sys.executable, str(src),
        '--data_root',       args.data_root,
        '--benchmark_npz',   args.benchmark_npz,
        '--dataset',         args.dataset,
        '--seed',            str(args.seed),
        '--epochs',          str(args.epochs),
        '--output_dir',      str(out_dir),
        '--reid_feat_source', 'memory',   # A2 臂（有 memory + Frangi 门）
        '--use_frangi',      str(use_frangi_val),
        '--eval_benchmark_every', '1',    # 每 epoch 跑一次 benchmark 评估
    ]
    if args.smoke_train:
        cmd.append('--smoke')

    print(f'[gate_smoke] 启动 arm={args.arm}  use_frangi={use_frangi_val}',
          file=sys.stderr)
    print(f'[gate_smoke] cmd: {" ".join(cmd)}', file=sys.stderr)

    result = subprocess.run(cmd, capture_output=False)
    if result.returncode != 0:
        print(f'[gate_smoke] ERROR: train_reid_pilot 返回 code={result.returncode}',
              file=sys.stderr)
        sys.exit(result.returncode)
    return out_dir


def load_reid_csv(csv_path: Path) -> list[dict]:
    """读 reid_results.csv，返回行列表。"""
    if not csv_path.exists():
        print(f'[gate_smoke] ERROR: reid_results.csv 未产出: {csv_path}',
              file=sys.stderr)
        sys.exit(1)
    with open(csv_path, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def convert_to_gate_metrics(rows: list[dict], arm_label: str,
                             seed: int, out_path: Path) -> None:
    """
    将 reid_results.csv 转换为 gate_metrics.csv（补 arm / seed 列，
    保留 clDice / epsilon_beta0 / betti_err_total）。

    注：当前 reid_results.csv 没有 clDice 列（路B 专用列），
    本烟测先核已有列（epsilon_beta0 / betti_err_total），
    clDice 列如果存在则一并透传；不存在则填 'nan' + 警告。
    """
    fieldnames = [
        'image_id', 'dataset', 'seed', 'arm',
        'cldice', 'epsilon_beta0', 'betti_err_total',
    ]
    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            # clDice 可能不在 reid_results.csv（路B 尚未集成）→ 填 nan 告警
            cldice_val = r.get('cldice', r.get('cl_dice', 'nan'))
            w.writerow({
                'image_id':         r.get('image_id', ''),
                'dataset':          r.get('dataset', ''),
                'seed':             seed,
                'arm':              arm_label,
                'cldice':           cldice_val,
                'epsilon_beta0':    r.get('epsilon_beta0', 'nan'),
                'betti_err_total':  r.get('betti_err_total', 'nan'),
            })


def check_no_nan(rows: list[dict], col: str) -> bool:
    """检查列无全 NaN（至少有 1 个有效值）。"""
    vals = []
    for r in rows:
        try:
            v = float(r.get(col, 'nan'))
            if not np.isnan(v):
                vals.append(v)
        except (ValueError, TypeError):
            pass
    return len(vals) > 0


def main():
    args = parse_args()
    arm_label = args.arm
    use_frangi_val = 1 if arm_label == 'gate-on' else 0

    # ---- 跑训练 ----
    out_dir = run_train_arm(args, use_frangi_val)

    # ---- 检查产出 ----
    reid_csv = out_dir / 'reid_results.csv'
    rows = load_reid_csv(reid_csv)
    print(f'[gate_smoke] reid_results.csv 读取 {len(rows)} 行', file=sys.stderr)

    if not rows:
        print('[gate_smoke] ERROR: reid_results.csv 为空', file=sys.stderr)
        sys.exit(1)

    # ---- 转换为 gate_metrics.csv ----
    gate_csv = out_dir / 'gate_metrics.csv'
    convert_to_gate_metrics(rows, arm_label, args.seed, gate_csv)
    print(f'[gate_smoke] gate_metrics.csv 写出 → {gate_csv}', file=sys.stderr)

    # ---- 数值稳定性检查 ----
    smoke_pass = True
    for col in ('epsilon_beta0', 'betti_err_total'):
        ok = check_no_nan(rows, col)
        status = 'OK' if ok else 'FAIL(all-NaN)'
        print(f'[gate_smoke] {col}: {status}', file=sys.stderr)
        if not ok:
            smoke_pass = False

    # clDice：单独提示（可能尚未集成）
    if any('cldice' in r or 'cl_dice' in r for r in rows):
        ok = check_no_nan(rows, 'cldice') or check_no_nan(rows, 'cl_dice')
        print(f'[gate_smoke] cldice: {"OK" if ok else "FAIL(all-NaN)"}',
              file=sys.stderr)
    else:
        print('[gate_smoke] WARNING: reid_results.csv 无 cldice 列 — '
              '路B 正式 run 需在 train_reid_pilot 输出中集成 clDice metric',
              file=sys.stderr)

    # ---- 摘要 ----
    print(f'\n[gate_smoke] arm={arm_label}  SMOKE_PASS={smoke_pass}', file=sys.stderr)
    if not smoke_pass:
        sys.exit(1)

    # ---- 写 smoke state ----
    smoke_state = {
        'arm': arm_label,
        'use_frangi': use_frangi_val,
        'n_rows': len(rows),
        'SMOKE_PASS': smoke_pass,
        'output_dir': str(out_dir),
        'gate_csv': str(gate_csv),
    }
    state_path = out_dir / 'gate_smoke_state.json'
    with open(state_path, 'w', encoding='utf-8') as f:
        json.dump(smoke_state, f, indent=2)
    print(f'[gate_smoke] state → {state_path}', file=sys.stderr)


if __name__ == '__main__':
    main()
