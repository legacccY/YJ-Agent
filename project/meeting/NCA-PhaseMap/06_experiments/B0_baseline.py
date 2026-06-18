"""B0 全背景基线 — NCA-PhaseMap Gate1

不训练，纯统计两集（BraTS + Hippocampus）的全背景解（pred≡0）dice 分布。

目的：产出 collapse 判据阈值 max(0.01, dice_bg + 3·σ_bg)，跑前冻进 config 防 HARKing。

【全背景解 dice 推导】
    dice_proxy = 1 - dice_loss(pred≡0, lbl)
    dice_loss   = 1 - (2*0+1) / (0 + lbl_sum + 1) = lbl_sum / (lbl_sum + 1)
    → dice_proxy = 1 / (lbl_sum + 1)
    对 lbl_sum=0（全背景切片）→ dice_proxy=1，但这类已在 P0 被前景占比筛掉。
    对有前景切片 lbl_sum ≈ fg_ratio*H*W*B → dice_proxy≈1/(fg_ratio*H*W*B+1) 很小。

【输出】
    results/B0_baseline.csv：集名, n_slices, dice_bg_mean, dice_bg_std, dice_bg_p95,
                              fg_ratio_median, fg_ratio_min, fg_ratio_max
    打印 collapse 阈 max(0.01, dice_bg_mean + 3*dice_bg_std) 供冻 config。

【入口】
    python B0_baseline.py [--data_root_brats PATH] [--data_root_hip PATH]
                          [--fg_thresh 0.02] [--batch_size 4]

环境变量：
    BRATS_ROOT   BraTS test/ 目录
    MEDNCA_ROOT  Med-NCA 根目录
"""

import os
import sys
import csv
import math
import argparse
import numpy as np
import torch
from torch.utils.data import DataLoader
from pathlib import Path

# ─── 路径常量 ───────────────────────────────────────────────────────
_BRATS_ROOT_DEFAULT = os.environ.get(
    'BRATS_ROOT',
    os.path.join("D:", os.sep, "YJ-Agent", "project", "meeting",
                 "MedAD-FailMap", "data", "BraTS2021", "test")
)
MEDNCA_ROOT = os.environ.get(
    'MEDNCA_ROOT',
    os.path.join("D:", os.sep, "YJ-Agent", "project", "meeting", "Med-NCA")
)
OFFICIAL_ROOT = os.path.join(MEDNCA_ROOT, "M3D-NCA-official")
DATA_HIP      = os.path.join(MEDNCA_ROOT, "data", "Task04_Hippocampus")

THIS_DIR    = os.environ.get('PHASEMAP_OUT',
                             os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(THIS_DIR, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

OUT_CSV = os.path.join(RESULTS_DIR, "B0_baseline.csv")

IMG_SIZE       = (64, 64)
CHANNEL_N      = 16
LR             = 16e-4
BETAS          = (0.5, 0.5)
HIDDEN_SIZE    = 128

# NCA config 模板（复用 HipSliceDataset 构造用）
NCA_CONFIG_BASE = {
    'img_path':         os.path.join(DATA_HIP, "imagesTr"),
    'label_path':       os.path.join(DATA_HIP, "labelsTr"),
    'device':           "cpu",
    'channel_n':        CHANNEL_N,
    'inference_steps':  16,
    'cell_fire_rate':   0.5,
    'input_channels':   1,
    'output_channels':  1,
    'hidden_size':      HIDDEN_SIZE,
    'input_size':       [[16, 16], [64, 64]],
    'data_split':       [0.7, 0.0, 0.3],
    'rescale':          True,
}


# ─── dice proxy（全背景解：pred=0 处处为 0） ────────────────────────
def dice_bg_proxy(lbl_batch: torch.Tensor, smooth: float = 1.0) -> np.ndarray:
    """给定 lbl [B,1,H,W]，算「pred≡0」的 dice proxy（每张切片单独算）。

    dice_proxy = (2*0 + smooth) / (0 + lbl_sum + smooth)
               = smooth / (lbl_sum + smooth)
    与训练时 dice_loss smooth=1 对齐。
    """
    # lbl_batch: [B, 1, H, W]
    lbl_flat = lbl_batch.view(lbl_batch.shape[0], -1).float()  # [B, N]
    lbl_sum  = lbl_flat.sum(dim=1)                             # [B]
    dp = (smooth / (lbl_sum + smooth)).numpy()                 # [B]
    return dp  # shape [B]


# ─── Hippocampus dataset（复用 C044c 逻辑，零改） ───────────────────
def _patch_path(v):
    if not isinstance(v, str):
        return v
    v_posix = v.replace('\\', '/')
    marker = 'Med-NCA/'
    idx = v_posix.find(marker)
    if idx == -1:
        return v
    rel = v_posix[idx + len(marker):]
    return MEDNCA_ROOT.replace('\\', '/') + '/' + rel


def patch_experiment_paths(exp):
    for stage in exp.projectConfig:
        for k, v in stage.items():
            patched = _patch_path(v)
            if patched != v:
                stage[k] = patched
    exp.set_current_config()


class HipSliceDataset(torch.utils.data.Dataset):
    """从官方 Dataset_NiiGz_3D 取 train split 的 2D slices（接口=C044c）。"""
    def __init__(self, split='train'):
        sys.path.insert(0, OFFICIAL_ROOT)
        os.chdir(OFFICIAL_ROOT)
        from src.datasets.Nii_Gz_Dataset_3D import Dataset_NiiGz_3D
        from src.utils.Experiment import Experiment
        from src.agents.Agent_Med_NCA import Agent_Med_NCA
        from src.models.Model_BackboneNCA import BackboneNCA

        device = torch.device("cpu")
        config = [{
            **NCA_CONFIG_BASE,
            'model_path': os.path.join(MEDNCA_ROOT, "checkpoints", "r1_hippocampus"),
            'lr': LR, 'lr_gamma': 0.9999, 'betas': list(BETAS),
            'save_interval': 9999, 'evaluate_interval': 9999,
            'n_epoch': 1000, 'batch_size': 48, 'train_model': 1,
            'unlock_CPU': True, 'Persistence': False,
            'batch_duplication': 1, 'keep_original_scale': False,
        }]
        dataset_nii = Dataset_NiiGz_3D(slice=2)
        ca1 = BackboneNCA(CHANNEL_N, 0.5, device, hidden_size=HIDDEN_SIZE, input_channels=1)
        ca2 = BackboneNCA(CHANNEL_N, 0.5, device, hidden_size=HIDDEN_SIZE, input_channels=1)
        agent_tmp = Agent_Med_NCA([ca1, ca2])
        exp_tmp   = Experiment(config, dataset_nii, [ca1, ca2], agent_tmp)
        patch_experiment_paths(exp_tmp)
        dataset_nii.set_experiment(exp_tmp)
        exp_tmp.set_model_state(split)
        dataset_nii.set_size(IMG_SIZE)

        self.samples = []
        for idx in range(len(dataset_nii)):
            _, img_np, lbl_np = dataset_nii[idx]
            img = torch.from_numpy(img_np).permute(2, 0, 1).float()
            lbl = torch.from_numpy(lbl_np).permute(2, 0, 1).float()
            self.samples.append((img, lbl))

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        return self.samples[idx]


# ─── 统计单集 ────────────────────────────────────────────────────────
def compute_dataset_stats(ds, dataset_name: str, batch_size: int = 4):
    """遍历数据集，算全背景 dice 分布 + 前景占比分布。"""
    loader = DataLoader(ds, batch_size=batch_size, shuffle=False,
                        num_workers=0, pin_memory=False)

    all_dice_bg  = []
    all_fg_ratio = []

    for img, lbl in loader:
        # lbl: [B, 1, H, W]
        # 跳过全背景切片（和 B0 说明的：这类已被 fg_thresh 过滤/本来前景占比=0 产 dice_bg=1 会拉高）
        fg_per_sample = lbl.view(lbl.shape[0], -1).float().mean(dim=1)  # [B]
        dp = dice_bg_proxy(lbl)  # [B]

        for i in range(len(dp)):
            all_dice_bg.append(float(dp[i]))
            all_fg_ratio.append(float(fg_per_sample[i]))

    all_dice_bg  = np.array(all_dice_bg,  dtype=np.float32)
    all_fg_ratio = np.array(all_fg_ratio, dtype=np.float32)

    # 过滤全背景切片（fg=0 → dice_bg=1，不代表真实分割性能，单列排除）
    nonzero_mask = all_fg_ratio > 0
    dice_bg_valid = all_dice_bg[nonzero_mask]

    mean_bg = float(np.mean(dice_bg_valid)) if len(dice_bg_valid) > 0 else float('nan')
    std_bg  = float(np.std(dice_bg_valid))  if len(dice_bg_valid) > 0 else float('nan')
    p95_bg  = float(np.percentile(dice_bg_valid, 95)) if len(dice_bg_valid) > 0 else float('nan')

    collapse_thresh = max(0.01, mean_bg + 3 * std_bg) if not math.isnan(mean_bg) else 0.01

    stats = {
        'dataset':            dataset_name,
        'n_slices':           len(all_dice_bg),
        'n_zero_fg':          int((~nonzero_mask).sum()),
        'n_valid':            int(nonzero_mask.sum()),
        'dice_bg_mean':       round(mean_bg, 6),
        'dice_bg_std':        round(std_bg, 6),
        'dice_bg_p95':        round(p95_bg, 6),
        'collapse_thresh':    round(collapse_thresh, 6),
        'fg_ratio_median':    round(float(np.median(all_fg_ratio[nonzero_mask])), 6)
                              if nonzero_mask.sum() > 0 else float('nan'),
        'fg_ratio_min':       round(float(np.min(all_fg_ratio[nonzero_mask])), 6)
                              if nonzero_mask.sum() > 0 else float('nan'),
        'fg_ratio_max':       round(float(np.max(all_fg_ratio[nonzero_mask])), 6)
                              if nonzero_mask.sum() > 0 else float('nan'),
    }

    print(
        f"[B0][{dataset_name}]  n={len(all_dice_bg)} "
        f"(valid={stats['n_valid']}, zero_fg={stats['n_zero_fg']})",
        flush=True
    )
    print(
        f"  dice_bg  mean={mean_bg:.6f}  std={std_bg:.6f}  p95={p95_bg:.6f}",
        flush=True
    )
    print(
        f"  fg_ratio  median={stats['fg_ratio_median']}  "
        f"min={stats['fg_ratio_min']}  max={stats['fg_ratio_max']}",
        flush=True
    )
    print(
        f"  --> collapse_thresh = max(0.01, {mean_bg:.6f}+3×{std_bg:.6f}) = {collapse_thresh:.6f}",
        flush=True
    )

    return stats


# ─── 主流程 ──────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="B0 全背景基线（不训练）")
    parser.add_argument('--data_root_brats', default=_BRATS_ROOT_DEFAULT,
                        help='BraTS2021/test/ 目录')
    parser.add_argument('--data_root_hip',   default=DATA_HIP,
                        help='Task04_Hippocampus 目录（自动由 MEDNCA_ROOT 拼）')
    parser.add_argument('--fg_thresh', type=float, default=0.02,
                        help='BraTS 切片前景占比筛选阈（≥此保留）')
    parser.add_argument('--batch_size', type=int, default=4)
    parser.add_argument('--skip_hip',   action='store_true',
                        help='跳过 Hippocampus（加速调试）')
    args = parser.parse_args()

    all_stats = []

    # ── BraTS ──────────────────────────────────────────────────────
    print("[B0] 加载 BraTSSliceDataset ...", flush=True)
    # 把本地 data_brats 模块加入路径
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from data_brats import BraTSSliceDataset

    brats_ds = BraTSSliceDataset(
        data_root=args.data_root_brats,
        fg_thresh=args.fg_thresh,
    )
    print(brats_ds.report(), flush=True)
    stats_brats = compute_dataset_stats(brats_ds, 'BraTS2021', args.batch_size)
    all_stats.append(stats_brats)

    # ── Hippocampus ────────────────────────────────────────────────
    if not args.skip_hip:
        print("\n[B0] 加载 HipSliceDataset (train split) ...", flush=True)
        hip_ds = HipSliceDataset(split='train')
        print(f"  Hippo samples: {len(hip_ds)}", flush=True)
        stats_hip = compute_dataset_stats(hip_ds, 'Hippocampus', args.batch_size)
        all_stats.append(stats_hip)

    # ── 写 CSV ─────────────────────────────────────────────────────
    cols = ['dataset', 'n_slices', 'n_valid', 'n_zero_fg',
            'dice_bg_mean', 'dice_bg_std', 'dice_bg_p95', 'collapse_thresh',
            'fg_ratio_median', 'fg_ratio_min', 'fg_ratio_max']
    with open(OUT_CSV, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore')
        w.writeheader()
        w.writerows(all_stats)

    print(f"\n[B0] CSV 已写: {OUT_CSV}", flush=True)
    print("=" * 60, flush=True)
    print("[B0] 摘要（冻 config 用）：", flush=True)
    for s in all_stats:
        print(
            f"  {s['dataset']:12s}  dice_bg_mean={s['dice_bg_mean']:.6f}  "
            f"std={s['dice_bg_std']:.6f}  "
            f"collapse_thresh={s['collapse_thresh']:.6f}",
            flush=True
        )
    print("=" * 60, flush=True)
    print("[B0] 完成。跑前将 collapse_thresh 写入 config 冻结，事后不得调宽。", flush=True)


if __name__ == '__main__':
    main()
