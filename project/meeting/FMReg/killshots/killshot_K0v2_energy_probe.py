"""
killshot_K0v2_energy_probe.py
FMReg A0 立项闸 K0v2：FM-in-SVF 能量地形多峰前置探针

证伪线（skeptic 红队定的命根）：
  GREEN_PROBE = λ=1.0（实际正则强度）下多数受控对仍双谷
                → warp-loss 能量地形多峰成立，放行写实现 a
  RED_PROBE   = λ=1.0 下多数单谷
                → FM-in-SVF 容器注定单峰，证伪多解后验假设，报拍板

核心逻辑（纯前向，零训练）：
  1. 构造受控歧义对：合成 moving（中心高斯 blob）+ fixed（双对称 blob）
     已知双解：psi_left（推中心→左 blob）/ psi_right（推中心→右 blob）
  2. 沿 psi_left ↔ psi_right 连线密采 α∈linspace(0,1,41)
     对每 alpha：E(α) = NCC(warp(moving, S&S(psi_alpha)), fixed)
                       + λ·smooth_reg(psi_alpha)
  3. 扫 λ_smooth ∈ {0.0, 0.1, 1.0}；机械判峰（纯 numpy，无 scipy）
  4. 汇总 verdict per (pair, lambda)

几何算子直接从 killshot_K0_fm_vs_vxmdiff.py 同目录 import 复用，
避免重复实现引入偏差。

输出：
  killshots/results/killshot_K0v2_energy_probe.csv
  killshots/results/energy_probe_lambda{λ}.png

运行：
  python killshot_K0v2_energy_probe.py             # full: 5 对, 41 点
  python killshot_K0v2_energy_probe.py --smoke     # 2 对, 11 点, cpu <30s

Windows 规范：num_workers=0, pin_memory=False, forward-slash 路径,
              纯 numpy 判峰 (no scipy, 避 OMP Error #15), matplotlib Agg
"""

import argparse
import os
import sys
import csv
import math

import numpy as np

# ---------- matplotlib (Agg before any display import) ----------
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ---------- torch ----------
try:
    import torch
    import torch.nn.functional as F
except ImportError:
    print("[ERROR] torch not found. pip install torch")
    sys.exit(1)

# ---------- 复用 K0v1 几何/损失算子 ----------
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

try:
    from killshot_K0_fm_vs_vxmdiff import (
        scaling_and_squaring,   # svf[B,2,H,W] → disp[B,H,W,2], int_steps=7
        warp_by_disp,           # (moving[B,1,H,W], disp[B,H,W,2]) → [B,1,H,W]
        make_identity_grid,     # (B,H,W,device) → [B,H,W,2]
        smooth_loss,            # svf[B,2,H,W] → scalar (||∇v||²)
    )
    print("[INFO] Imported geometry/loss ops from killshot_K0_fm_vs_vxmdiff.py")
except ImportError as e:
    print(f"[ERROR] Cannot import K0v1 ops: {e}")
    sys.exit(1)

# ---------- NCC loss：K0v1 版返回 -NCC（用于最小化），这里需要正 NCC 值算能量 ----------
# 直接自包含实现，避免符号混淆
def ncc_positive(pred, target, win=9):
    """
    Local NCC，返回正值（越高=越相似）。
    pred, target: [B, 1, H, W]
    win=9 参考 voxelmorph/py/losses.py NCC class default win=[9,9]
    """
    pad = win // 2
    p = F.unfold(pred,   kernel_size=win, padding=pad)
    t = F.unfold(target, kernel_size=win, padding=pad)
    pm = p.mean(dim=1, keepdim=True)
    tm = t.mean(dim=1, keepdim=True)
    pc = p - pm
    tc = t - tm
    num   = (pc * tc).sum(dim=1)
    denom = torch.sqrt((pc ** 2).sum(dim=1) * (tc ** 2).sum(dim=1) + 1e-8)
    return (num / denom).mean().item()


def energy(svf, moving, fixed, lam):
    """
    E = -NCC(warp(moving, S&S(svf)), fixed) + λ·smooth_reg(svf)
    注意用 -NCC 使"相似=低能量"（最小化语义）。
    svf: [1, 2, H, W]
    """
    with torch.no_grad():
        disp   = scaling_and_squaring(svf, int_steps=7)
        warped = warp_by_disp(moving, disp)
        ncc_val = ncc_positive(warped, fixed)   # 越高越好
        reg_val = smooth_loss(svf).item()
    return -ncc_val + lam * reg_val


# ============================================================
# 受控歧义对构造（人造，预登记，固定 seed=0，不事后调）
# ============================================================
def make_gaussian_blob(H, W, cx, cy, sigma):
    """
    在 [H, W] 画面上生成高斯 blob，返回 numpy float32 [H, W]，峰值≈1。
    cx, cy: 中心坐标（像素），sigma: 标准差（像素）
    """
    ys = np.arange(H, dtype=np.float32)
    xs = np.arange(W, dtype=np.float32)
    yy, xx = np.meshgrid(ys, xs, indexing='ij')
    return np.exp(-((yy - cy) ** 2 + (xx - cx) ** 2) / (2 * sigma ** 2))


# 受控歧义对参数表（固定，不事后调整）
# 每个 entry: (blob_sigma, blob_offset_x, note)
#   blob_offset_x = left blob 距中心的水平偏移（右 blob 是镜像）
#   note = 描述为何构成歧义
PAIR_CONFIGS = [
    # (sigma, offset_x, note)
    (10.0,  30, "standard: offset=30, sigma=10"),
    (10.0,  20, "closer blobs: offset=20, sigma=10"),
    (15.0,  35, "wider blob: offset=35, sigma=15"),
    (8.0,   25, "narrower blob: offset=25, sigma=8"),
    (12.0,  40, "large offset: offset=40, sigma=12"),
]

IMG_SIZE = 128
SS_INT_STEPS = 7   # 复用 K0v1 同值


def build_controlled_pair(H, W, sigma, offset_x, device):
    """
    构造 (moving, fixed, psi_left, psi_right)：
      moving : 中心高斯 blob
      fixed  : 左 + 右镜像高斯 blob（等强度），= 已知双解目标
      psi_left  : 把 moving blob 推到 fixed 左 blob 的 SVF（常量平移）
      psi_right : 推到右 blob 的 SVF（常量平移取反）

    SVF 编码约定（与 K0v1 scaling_and_squaring 一致）：
      svf 单位 = [-1, 1] 归一化坐标（即 pixel_shift / (W/2)）
    """
    cy, cx = H / 2, W / 2
    # moving: 中心 blob
    mov_np = make_gaussian_blob(H, W, cx=cx, cy=cy, sigma=sigma)
    # fixed: 左 blob + 右 blob（等强度，不归一化，两者之和约为 2×单 blob）
    left_np  = make_gaussian_blob(H, W, cx=cx - offset_x, cy=cy, sigma=sigma)
    right_np = make_gaussian_blob(H, W, cx=cx + offset_x, cy=cy, sigma=sigma)
    fix_np = np.clip(left_np + right_np, 0.0, 1.0).astype(np.float32)

    # 转 tensor [1, 1, H, W]
    moving = torch.from_numpy(mov_np[None, None]).to(device)  # [1,1,H,W]
    fixed  = torch.from_numpy(fix_np[None, None]).to(device)  # [1,1,H,W]

    # psi_left: 常量 SVF = 向左位移 offset_x 像素
    # 归一化：shift_norm = offset_x / (W/2)（x 轴负方向=向左）
    shift_norm_x = -float(offset_x) / (W / 2.0)   # 负=向左
    psi_left_np  = np.zeros((1, 2, H, W), dtype=np.float32)
    psi_left_np[:, 0, :, :] = shift_norm_x   # channel 0 = x 方向

    # psi_right: 向右，取反
    psi_right_np = np.zeros((1, 2, H, W), dtype=np.float32)
    psi_right_np[:, 0, :, :] = -shift_norm_x   # 向右

    psi_left  = torch.from_numpy(psi_left_np).to(device)
    psi_right = torch.from_numpy(psi_right_np).to(device)

    return moving, fixed, psi_left, psi_right


# ============================================================
# 纯 numpy 局部极小检测（无 scipy）
# ============================================================
def find_local_minima_numpy(E_curve, min_prominence=0.002):
    """
    检测 E_curve（1D numpy array）的局部极小，含端点。
    方法：内部极小用二阶邻居比较；端点单独补充（若端点 < 邻居则视为极小）。
    过滤 prominence < min_prominence（排除数值噪声；NCC 精度约 1e-4，实际 barrier 通常 >0.01）。

    Returns:
      minima_indices: list[int] 极小点位置（sorted）
      barrier_height: float  若 >=2 个极小则为两端极小之间最高点 - 两端极小均值，否则 0.0
    """
    n = len(E_curve)
    if n < 2:
        return [], 0.0

    # 收集候选：内部极小 + 端点极小
    candidates = []

    # 左端点
    if n >= 2 and E_curve[0] <= E_curve[1]:
        candidates.append(0)

    # 内部
    for i in range(1, n - 1):
        if E_curve[i] <= E_curve[i - 1] and E_curve[i] <= E_curve[i + 1]:
            candidates.append(i)

    # 右端点
    if n >= 2 and E_curve[-1] <= E_curve[-2]:
        candidates.append(n - 1)

    if not candidates:
        return [], 0.0

    # 计算 prominence（每个候选极小与左右最高点的最小高度差）
    filtered = []
    for idx in candidates:
        left_max  = E_curve[:idx].max()   if idx > 0     else E_curve[idx]
        right_max = E_curve[idx + 1:].max() if idx < n - 1 else E_curve[idx]
        prom = min(float(left_max) - float(E_curve[idx]),
                   float(right_max) - float(E_curve[idx]))
        if prom >= min_prominence:
            filtered.append(idx)

    # 若无高 prominence 极小，退回为全部候选（防 prominence 过严漏端点双谷）
    if not filtered and candidates:
        filtered = candidates[:]

    # barrier_height：最左与最右极小之间的最高点 - 两端极小均值
    barrier = 0.0
    if len(filtered) >= 2:
        i_left  = filtered[0]
        i_right = filtered[-1]
        between = E_curve[i_left:i_right + 1]
        barrier = float(between.max()) - (float(E_curve[i_left]) + float(E_curve[i_right])) / 2.0

    return filtered, max(barrier, 0.0)


# ============================================================
# 主扫描逻辑
# ============================================================
LAMBDA_LIST = [0.0, 0.1, 1.0]

RESULT_DIR = "D:/YJ-Agent/project/meeting/FMReg/killshots/results"
RESULT_CSV = os.path.join(RESULT_DIR, "killshot_K0v2_energy_probe.csv")


def run_probe(smoke=False):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    n_alpha = 11 if smoke else 41
    pair_configs = PAIR_CONFIGS[:2] if smoke else PAIR_CONFIGS

    print(f"[INFO] K0v2 energy probe | device={device} | smoke={smoke} "
          f"| n_pairs={len(pair_configs)} | n_alpha={n_alpha}")

    alphas = np.linspace(0.0, 1.0, n_alpha)

    # 储存所有结果
    # rows: dict per (pair_id, lambda)
    rows = []

    # per-lambda 曲线集合（供画图）
    # curves_by_lam[lam] = list of E_curve array (one per pair)
    curves_by_lam = {lam: [] for lam in LAMBDA_LIST}

    for pair_idx, (sigma, offset_x, note) in enumerate(pair_configs):
        print(f"\n[Pair {pair_idx}] sigma={sigma} offset_x={offset_x} | {note}")
        moving, fixed, psi_left, psi_right = build_controlled_pair(
            IMG_SIZE, IMG_SIZE, sigma, offset_x, device
        )

        for lam in LAMBDA_LIST:
            E_curve = np.zeros(n_alpha, dtype=np.float64)

            for ai, alpha in enumerate(alphas):
                # 线性插值 SVF
                psi_alpha = (1.0 - alpha) * psi_left + alpha * psi_right
                # psi_alpha: [1, 2, H, W]
                E_curve[ai] = energy(psi_alpha, moving, fixed, lam)

            # 判峰
            minima_idx, barrier = find_local_minima_numpy(E_curve, min_prominence=0.002)
            n_minima = len(minima_idx)
            min_alpha_positions = [float(alphas[i]) for i in minima_idx]

            # 单曲线 verdict
            if n_minima >= 2:
                curve_verdict = "BIMODAL"
            elif n_minima == 1:
                curve_verdict = "UNIMODAL"
            else:
                # 端点极小（单调或平坦）
                curve_verdict = "FLAT/MONOTONE"

            print(f"  lambda={lam:.1f} | n_minima={n_minima} | "
                  f"barrier={barrier:.5f} | minima_alpha={min_alpha_positions} | "
                  f"{curve_verdict}")

            rows.append({
                "pair_id":            pair_idx,
                "sigma":              sigma,
                "offset_x":          offset_x,
                "pair_note":         note,
                "lambda_smooth":     lam,
                "n_alpha_points":    n_alpha,
                "n_minima":          n_minima,
                "barrier_height":    round(barrier, 6),
                "min_alpha_positions": str(min_alpha_positions),
                "verdict_per_curve": curve_verdict,
            })

            curves_by_lam[lam].append((pair_idx, E_curve.copy()))

    # ============================================================
    # 汇总 verdict（按 lambda=1.0）
    # ============================================================
    rows_lam1 = [r for r in rows if r["lambda_smooth"] == 1.0]
    n_bimodal_lam1 = sum(1 for r in rows_lam1 if r["verdict_per_curve"] == "BIMODAL")
    n_total        = len(rows_lam1)
    frac_bimodal   = n_bimodal_lam1 / n_total if n_total > 0 else 0.0

    if frac_bimodal >= 0.5:
        summary_verdict = (
            f"GREEN_PROBE: lambda=1.0 下 {n_bimodal_lam1}/{n_total} 对 = {frac_bimodal:.0%} 双谷 "
            f"→ 多峰能量地形成立，FM-in-SVF 多解后验假设可保留，放行写实现 a"
        )
    else:
        summary_verdict = (
            f"RED_PROBE: lambda=1.0 下仅 {n_bimodal_lam1}/{n_total} 对 = {frac_bimodal:.0%} 双谷 "
            f"→ 正则主导单峰坍缩，FM-in-SVF 多解后验假设证伪，报主线拍板"
        )

    print("\n" + "=" * 70)
    print("  K0v2 ENERGY PROBE SUMMARY")
    print("=" * 70)
    for lam in LAMBDA_LIST:
        r_lam = [r for r in rows if r["lambda_smooth"] == lam]
        n_bi  = sum(1 for r in r_lam if r["verdict_per_curve"] == "BIMODAL")
        print(f"  lambda={lam:.1f}: {n_bi}/{len(r_lam)} bimodal")
    print(f"\n  VERDICT: {summary_verdict}")
    print("=" * 70)

    # 追加汇总行到 rows
    rows.append({
        "pair_id":            "SUMMARY",
        "sigma":              "",
        "offset_x":          "",
        "pair_note":         "",
        "lambda_smooth":     1.0,
        "n_alpha_points":    n_alpha,
        "n_minima":          n_bimodal_lam1,
        "barrier_height":    frac_bimodal,
        "min_alpha_positions": "",
        "verdict_per_curve": summary_verdict,
    })

    # ============================================================
    # 写 CSV
    # ============================================================
    os.makedirs(RESULT_DIR, exist_ok=True)
    fieldnames = [
        "pair_id", "sigma", "offset_x", "pair_note",
        "lambda_smooth", "n_alpha_points",
        "n_minima", "barrier_height", "min_alpha_positions",
        "verdict_per_curve",
    ]
    with open(RESULT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"\n[SAVED CSV] {RESULT_CSV}")

    # ============================================================
    # 出图：每个 lambda 一张（叠所有对）
    # ============================================================
    for lam in LAMBDA_LIST:
        fig, ax = plt.subplots(figsize=(7, 4))
        for (pair_idx, E_curve) in curves_by_lam[lam]:
            ax.plot(alphas, E_curve, label=f"pair {pair_idx}", alpha=0.8)
        ax.set_xlabel("alpha  (0=psi_left, 1=psi_right)")
        ax.set_ylabel("E(alpha) = -NCC + λ·smooth_reg")
        ax.set_title(f"K0v2 Energy Landscape  |  λ_smooth={lam:.1f}")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)
        png_path = os.path.join(RESULT_DIR, f"energy_probe_lambda{lam:.1f}.png")
        fig.tight_layout()
        fig.savefig(png_path, dpi=120)
        plt.close(fig)
        print(f"[SAVED FIG] {png_path}")

    print(f"\n[DONE] K0v2 probe complete.")
    return summary_verdict


# ============================================================
# Entry point
# ============================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Killshot K0v2: FM-in-SVF 能量地形多峰前置探针 (FMReg A0)")
    parser.add_argument(
        "--smoke", action="store_true",
        help="2 对, 11 alpha 点, CPU <30s 自测")
    parser.add_argument(
        "--out-dir", default=RESULT_DIR,
        help="override result output dir")
    args = parser.parse_args()

    RESULT_DIR = args.out_dir
    RESULT_CSV = os.path.join(RESULT_DIR, "killshot_K0v2_energy_probe.csv")

    run_probe(smoke=args.smoke)
