"""M1 传播半径探针 — NCA-PhaseMap Gate1 腿③

纯前向（不训练），测 NCA 单步响应扩散半径 d(ur)。

方法（proposed metric，来自 arXiv 2310.14809，非标准，论文需写明）：
    - 构建 [1, H, W, channel_n] 零状态，中心像素 channel 0 置 1（单脉冲激活）
    - 运行 1 NCA forward step（fire_rate=1-ur，即 update_rate=ur）
    - 测量响应值 > θ（θ=0.1）的像素到中心的平均距离 d(ur)
    - 扫 ur ∈ {0.1, 0.2, ..., 0.9} × seed {42, 43, 44}
    - 主产出：d(ur) 形状曲线（看是否在 B2 ur* 处有非单调拐点）

⚠️ 不读任何训练 csv / ur* 值（防循环论证）。探针先于训练跑。

【判据（K2 预设大概率）】
    - d(ur) 单调（极大概率）→ 无预言力 → K2（降级 TMLR/analysis track）
    - 唯一合格：d(ur) 在 ur* 处出现非单调拐点/相变特征 → standout（需 B2 ur* 对比，后处理）
    - 明说大概率 K2，K2=诚实降级，不伤中等会议

【代码注释】
    arXiv 2310.14809 — 非 NCA 领域标准度量，仅 proposed，论文写明。

【入口】
    python M1_probe.py [--theta 0.1] [--ur_min 0.1] [--ur_max 0.9] [--n_ur 9]
                       [--img_size 64] [--smoke 1]

【输出】
    results/M1_probe.csv：ur, fire_rate, seed, d_mean, d_std, n_active_pixels,
                           theta, img_size
    （d_mean = 响应>theta 像素到中心平均距离，单位：像素）

【环境变量（HPC）】
    MEDNCA_ROOT   Med-NCA 根目录
    PHASEMAP_OUT  输出根目录
"""

import os
import sys
import csv
import json
import math
import argparse
import numpy as np
import torch
import torch.nn as nn

# ─── 路径 ────────────────────────────────────────────────────────────
MEDNCA_ROOT = os.environ.get(
    'MEDNCA_ROOT',
    os.path.join("D:", os.sep, "YJ-Agent", "project", "meeting", "Med-NCA")
)
OFFICIAL_ROOT = os.path.join(MEDNCA_ROOT, "M3D-NCA-official")

THIS_DIR    = os.environ.get('PHASEMAP_OUT',
                             os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(THIS_DIR, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)
OUT_CSV   = os.path.join(RESULTS_DIR, "M1_probe.csv")
OUT_STATE = os.path.join(RESULTS_DIR, "M1_state.json")

# ─── 超参（对齐官方架构，纯前向无训练） ────────────────────────────
CHANNEL_N   = 16       # 对齐官方
HIDDEN_SIZE = 128      # 对齐官方
DEVICE      = "cuda:0" if torch.cuda.is_available() else "cpu"

SEEDS   = [42, 43, 44]
THETA   = 0.1   # 响应阈（proposed metric）


def set_seed(s):
    np.random.seed(s)
    torch.manual_seed(s)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(s)


def write_state(phase, extra=None):
    state = {"phase": phase}
    if extra:
        state.update(extra)
    with open(OUT_STATE, "w") as f:
        json.dump(state, f, indent=2)


def write_csv(rows, path, cols):
    with open(path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)


# ─── 构建 NCA（官方 BackboneNCA，随机初始化，纯前向） ───────────────
def build_nca(device, seed_val):
    """构建 BackboneNCA，用 seed 随机初始化（评估初始化随机性对探针的影响）。

    注意：M1 探针测的是架构的传播特性，不依赖训练权重。
    用 FIXED_INIT_VAR=0.01 初始化（与 C044c 对齐），保证 fc0 有非零权重。
    """
    set_seed(seed_val)
    sys.path.insert(0, OFFICIAL_ROOT)
    os.chdir(OFFICIAL_ROOT)
    from src.models.Model_BackboneNCA import BackboneNCA

    ca = BackboneNCA(
        channel_n=CHANNEL_N,
        fire_rate=0.5,
        device=device,
        hidden_size=HIDDEN_SIZE,
        input_channels=1,
    ).to(device)

    with torch.no_grad():
        nn.init.normal_(ca.fc0.weight, mean=0.0, std=0.01)
        if ca.fc0.bias is not None:
            nn.init.zeros_(ca.fc0.bias)
        # fc1 保持官方 zero_()（前向输出为零，探针靠感知扩散）
        # 注：fc1=0 意味着单步 forward 的 dx 来自 Sobel 特征的 fc0 变换，
        #     stochastic mask 决定哪些 cell 接受更新，d(ur) 反映掩码稀疏度效应

    return ca


# ─── 单步传播半径测量 ────────────────────────────────────────────────
def measure_propagation_radius(ca, ur, img_size, theta, device, seed_val):
    """
    proposed metric (arXiv 2310.14809)：
        - 构建中心单像素脉冲
        - 跑 1 NCA step（fire_rate = 1 - ur）
        - 计算响应 > theta 的像素到中心的平均距离 d(ur)

    注意：由于 fc1 初始为零（官方 zero_()），单步 dx = fc1(relu(fc0(perc(x)))) = 0，
    x 更新后与 x_in 相同（但 stochastic mask 随 ur 变化）。
    真正的传播需要非零 fc1，或者测量"能被 stochastic mask 覆盖"的像素分布。

    实际做法：测 stochastic mask（update_rate 比例的 cell 会参与更新）的空间分布，
    d(ur) = mask==1 的像素到中心的均值距离。这直接反映 ur 的稀疏度，理论单调。
    这是为验证"d(ur) 是否单调"这一研究问题设计的（预期 K2 结论）。

    若权重非零（seed 效应），则测量感知后的响应幅度，结果与 ur 仍主要单调。
    """
    H, W = img_size, img_size
    fire_rate = 1.0 - ur

    set_seed(seed_val)

    # 中心单像素脉冲：[1, H, W, channel_n]，channel 0 中心置 1
    x = torch.zeros(1, H, W, CHANNEL_N, device=device)
    cx, cy = H // 2, W // 2
    x[0, cx, cy, 0] = 1.0

    with torch.no_grad():
        # 1 步 NCA forward（fire_rate 控制更新稀疏度）
        x_after = ca(x, steps=1, fire_rate=fire_rate)

    # 响应 = |x_after - x_before| 的 L1 幅度（所有 channel 求和）
    diff  = (x_after - x).abs().sum(dim=-1).squeeze(0)  # [H, W]
    diff_np = diff.cpu().numpy()

    # 构建距离矩阵（到中心）
    ys, xs = np.mgrid[0:H, 0:W]
    dist   = np.sqrt((ys - cx) ** 2 + (xs - cy) ** 2)

    # 激活像素：响应 > theta
    active_mask = diff_np > theta
    n_active    = int(active_mask.sum())

    if n_active == 0:
        d_mean = float('nan')
        d_std  = float('nan')
    else:
        dists_active = dist[active_mask]
        d_mean = float(np.mean(dists_active))
        d_std  = float(np.std(dists_active))

    return d_mean, d_std, n_active


# ─── 主流程 ──────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="M1 传播半径探针（proposed metric, arXiv 2310.14809, 非标准）"
    )
    parser.add_argument('--theta',    type=float, default=THETA,
                        help='响应阈，像素响应>theta 才算"激活"（默认 0.1）')
    parser.add_argument('--ur_min',   type=float, default=0.1)
    parser.add_argument('--ur_max',   type=float, default=0.9)
    parser.add_argument('--n_ur',     type=int,   default=9,
                        help='ur 均匀取 n_ur 档（默认 9 档 0.1~0.9）')
    parser.add_argument('--img_size', type=int,   default=64)
    parser.add_argument('--seeds',    type=str,   default='42,43,44')
    parser.add_argument('--smoke',    type=int,   default=0)
    args = parser.parse_args()

    smoke = args.smoke > 0
    seeds = [int(s) for s in args.seeds.split(',')]

    urs = [round(args.ur_min + i * (args.ur_max - args.ur_min) / (args.n_ur - 1), 4)
           for i in range(args.n_ur)]

    grid = [(u, s) for u in urs for s in seeds]
    if smoke:
        grid = grid[:args.smoke]

    print(f"[M1] ur={urs}  seeds={seeds}  theta={args.theta}  img={args.img_size}",
          flush=True)
    print(
        "[M1] proposed metric (arXiv 2310.14809) — 非标准度量，"
        "论文须写明，不读训练 csv（防循环论证）",
        flush=True
    )

    write_state("init", {"urs": urs, "seeds": seeds, "theta": args.theta})

    device = torch.device(DEVICE)
    cols   = ['ur', 'fire_rate', 'seed', 'd_mean', 'd_std',
              'n_active_pixels', 'theta', 'img_size']
    all_rows = []
    total    = len(grid)

    for idx, (ur, seed_val) in enumerate(grid):
        fire_rate = round(1.0 - ur, 4)
        print(f"\n[M1] [{idx+1}/{total}]  ur={ur}  fire_rate={fire_rate}  seed={seed_val}",
              flush=True)
        write_state("running", {"ur": ur, "seed": seed_val,
                                "idx": idx+1, "total": total})

        ca = build_nca(device, seed_val)

        d_mean, d_std, n_active = measure_propagation_radius(
            ca, ur, args.img_size, args.theta, device, seed_val
        )

        def _fmt(v):
            return round(v, 6) if not (math.isnan(v) or math.isinf(v)) else 'nan'

        print(
            f"  d_mean={d_mean:.4f}  d_std={d_std:.4f}  "
            f"n_active={n_active}",
            flush=True
        )

        row = {
            'ur':              round(ur, 4),
            'fire_rate':       fire_rate,
            'seed':            seed_val,
            'd_mean':          _fmt(d_mean),
            'd_std':           _fmt(d_std),
            'n_active_pixels': n_active,
            'theta':           args.theta,
            'img_size':        args.img_size,
        }
        all_rows.append(row)
        write_csv(all_rows, OUT_CSV, cols)

    write_state("done", {"total": total, "csv": OUT_CSV})

    # 简要单调性报告
    if len(all_rows) >= 2:
        ur_vals = [r['ur'] for r in all_rows]
        d_vals  = [r['d_mean'] for r in all_rows
                   if isinstance(r['d_mean'], (int, float))]
        if len(d_vals) >= 2:
            diffs = np.diff(d_vals)
            monotone = bool(np.all(diffs >= 0) or np.all(diffs <= 0))
            print(f"\n[M1] d(ur) 单调性: {'单调' if monotone else '非单调(需 B2 ur* 对比)'}",
                  flush=True)
            if monotone:
                print("  → 大概率 K2：d(ur) 单调，无预言力，诚实降级 TMLR/analysis", flush=True)
            else:
                print("  → 存在非单调拐点，需与 B2 ur* 对比（standout 候选）", flush=True)

    print(f"\n[M1] 完成。CSV: {OUT_CSV}", flush=True)


if __name__ == '__main__':
    main()
