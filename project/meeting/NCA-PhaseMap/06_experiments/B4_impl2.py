"""B4 第二独立 NCA 实现扫描 — NCA-PhaseMap Gate1 腿①-b

用 nca_impl2.MinimalNCA（独立实现，mask=rand<update_rate 正向写法）在
Hippocampus 上扫 B3 临界区 5 档 ur × 3 seed，no-clip。

目的：验证 A4「临界相变非单实现 artifact」（K3）。若 impl2 与官方 impl 的 ur*
一致（±0.10），A4 可 claim 普适。

超参全对齐官方（channel_n=16 / hidden=128 / LR=16e-4 / betas=(0.5,0.5) /
300step / no-clip），不受零偏离约束（故意换实现），但超参须一致。

【入口】
    python B4_impl2.py [--ur_min 0.30] [--ur_max 0.50] [--n_ur 5]
                       [--seeds 42,43,44] [--smoke 1]

【输出】
    results/B4_impl2.csv：ur, fire_rate, seed, final_dice, diverged, collapsed,
                           max_grad_norm, fg_ratio_mean, collapse_thresh

【环境变量（HPC）】
    MEDNCA_ROOT   Med-NCA 根目录
    PHASEMAP_OUT  输出根目录
    DICE_BG_HIP   Hippo dice_bg_mean（B0 产出）
    SIGMA_BG_HIP  Hippo dice_bg_std
"""

import os
import sys
import csv
import json
import time
import math
import argparse
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader

# ─── 路径 ────────────────────────────────────────────────────────────
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
OUT_CSV   = os.path.join(RESULTS_DIR, "B4_impl2.csv")
OUT_STATE = os.path.join(RESULTS_DIR, "B4_state.json")

# ─── 超参（全对齐官方，零偏离） ─────────────────────────────────────
DEVICE         = "cuda:0" if torch.cuda.is_available() else "cpu"
IMG_SIZE       = (64, 64)
ABLATION_STEPS = 300
LR             = 16e-4
BETAS          = (0.5, 0.5)
CHANNEL_N      = 16
HIDDEN_SIZE    = 128
INFERENCE_STEPS_EVAL = 16
FIXED_INIT_VAR = 0.01

NCA_CONFIG_BASE = {
    'img_path':        os.path.join(DATA_HIP, "imagesTr"),
    'label_path':      os.path.join(DATA_HIP, "labelsTr"),
    'device':          DEVICE,
    'channel_n':       CHANNEL_N,
    'inference_steps': INFERENCE_STEPS_EVAL,
    'cell_fire_rate':  0.5,
    'input_channels':  1,
    'output_channels': 1,
    'hidden_size':     HIDDEN_SIZE,
    'input_size':      [[16, 16], [64, 64]],
    'data_split':      [0.7, 0.0, 0.3],
    'rescale':         True,
}


# ─── 工具 ────────────────────────────────────────────────────────────
def set_seed(s):
    np.random.seed(s)
    torch.manual_seed(s)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(s)


def write_state(phase, extra=None):
    state = {"phase": phase, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")}
    if extra:
        state.update(extra)
    with open(OUT_STATE, "w") as f:
        json.dump(state, f, indent=2)


def dice_loss_fn(logit, target, smooth=1.0):
    pred  = torch.sigmoid(logit).flatten()
    tgt   = target.flatten()
    inter = (pred * tgt).sum()
    return 1.0 - (2.0 * inter + smooth) / (pred.sum() + tgt.sum() + smooth)


def write_csv(rows, path, cols):
    with open(path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)


# ─── 路径 patch（Hippo dataset 用） ─────────────────────────────────
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


# ─── Hippocampus dataset（复用 C044c） ──────────────────────────────
class HipSliceDataset(torch.utils.data.Dataset):
    def __init__(self):
        sys.path.insert(0, OFFICIAL_ROOT)
        os.chdir(OFFICIAL_ROOT)
        from src.datasets.Nii_Gz_Dataset_3D import Dataset_NiiGz_3D
        from src.utils.Experiment import Experiment
        from src.agents.Agent_Med_NCA import Agent_Med_NCA
        from src.models.Model_BackboneNCA import BackboneNCA
        device = torch.device(DEVICE)
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
        ca1 = BackboneNCA(CHANNEL_N, 0.5, device, hidden_size=HIDDEN_SIZE, input_channels=1).to(device)
        ca2 = BackboneNCA(CHANNEL_N, 0.5, device, hidden_size=HIDDEN_SIZE, input_channels=1).to(device)
        agent_tmp = Agent_Med_NCA([ca1, ca2])
        exp_tmp   = Experiment(config, dataset_nii, [ca1, ca2], agent_tmp)
        patch_experiment_paths(exp_tmp)
        dataset_nii.set_experiment(exp_tmp)
        exp_tmp.set_model_state('train')
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


# ─── Pool ────────────────────────────────────────────────────────────
class SimplePool:
    def __init__(self, maxsize=40):
        self.pool = {}
        self.maxsize = maxsize

    def __len__(self):
        return len(self.pool)

    def get(self, idx, seed_tensor, device):
        if idx in self.pool:
            return self.pool[idx].to(device)
        return seed_tensor

    def put(self, idx, state_tensor):
        if len(self.pool) >= self.maxsize:
            k = next(iter(self.pool))
            del self.pool[k]
        self.pool[idx] = state_tensor.detach().cpu()


def make_seed(img, channel_n, device):
    B, C, H, W = img.shape
    seed = torch.zeros(B, H, W, channel_n, device=device)
    seed[..., :C] = img.permute(0, 2, 3, 1)
    return seed


# ─── 初始化 MinimalNCA ───────────────────────────────────────────────
def build_impl2_nca(device):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from nca_impl2 import MinimalNCA
    ca = MinimalNCA(
        channel_n=CHANNEL_N,
        device=device,
        hidden_size=HIDDEN_SIZE,
        input_channels=1,
    ).to(device)
    with torch.no_grad():
        nn.init.normal_(ca.fc0.weight, mean=0.0, std=FIXED_INIT_VAR)
        if ca.fc0.bias is not None:
            nn.init.zeros_(ca.fc0.bias)
    return ca


# ─── 单 run 训练（no-clip，impl2） ──────────────────────────────────
def run_one_cell_impl2(ca_list, train_ds, update_rate, n_steps, device, seed_val):
    """no-clip（对齐官方），使用 MinimalNCA.forward(update_rate=...)。"""
    set_seed(seed_val)

    optimizer = [optim.Adam(ca.parameters(), lr=LR, betas=BETAS) for ca in ca_list]
    loader    = DataLoader(train_ds, batch_size=4, shuffle=True,
                           num_workers=0, pin_memory=False)
    pool      = SimplePool(maxsize=40)

    grad_norm_log = []
    loss_log      = []
    fg_ratio_log  = []
    diverged      = False
    final_loss    = float('nan')

    step = 0
    while step < n_steps:
        for img, lbl in loader:
            if step >= n_steps:
                break

            img, lbl = img.to(device), lbl.to(device)
            seed = make_seed(img, CHANNEL_N, device)

            if len(pool) > 0:
                for bi in range(seed.shape[0]):
                    seed[bi] = pool.get(step * 1000 + bi, seed[bi], device)

            for opt in optimizer:
                opt.zero_grad()

            x = seed
            for ca in ca_list:
                x = ca(x, steps=INFERENCE_STEPS_EVAL, update_rate=update_rate)

            pred         = x[..., 1:2]
            lbl_permuted = lbl.permute(0, 2, 3, 1)
            if lbl_permuted.sum() == 0:
                step += 1
                continue

            loss     = dice_loss_fn(pred, lbl_permuted)
            loss_val = loss.item()

            if math.isnan(loss_val) or math.isinf(loss_val):
                diverged   = True
                final_loss = float('nan')
                step += 1
                continue

            loss.backward()

            norms = []
            for ca in ca_list:
                for p in ca.parameters():
                    if p.grad is not None:
                        norms.append(float(p.grad.norm().item()))
            grad_norm_log.append(float(np.max(norms)) if norms else float('nan'))

            # no-clip（铁律，对齐官方 Agent.py）
            for opt in optimizer:
                opt.step()

            for bi in range(x.shape[0]):
                pool.put(step * 1000 + bi, x[bi])

            final_loss = loss_val
            loss_log.append(final_loss)

            with torch.no_grad():
                fg = float((torch.sigmoid(pred) > 0.5).float().mean().item())
            fg_ratio_log.append(fg)

            step += 1

    max_gn = float(np.max(grad_norm_log)) if grad_norm_log else float('nan')
    if len(loss_log) >= 10:
        final_dice = float(1.0 - np.mean(loss_log[-10:]))
    elif len(loss_log) > 0:
        final_dice = float(1.0 - loss_log[-1])
    else:
        final_dice = float('nan')

    fg_mean = float(np.mean(fg_ratio_log)) if fg_ratio_log else float('nan')

    return {
        'final_dice':    final_dice,
        'diverged':      diverged,
        'max_grad_norm': max_gn,
        'fg_ratio_mean': fg_mean,
        'n_steps_run':   step,
    }


# ─── 主流程 ──────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="B4 第二独立实现扫描（MinimalNCA）")
    parser.add_argument('--ur_min',  type=float, default=0.30)
    parser.add_argument('--ur_max',  type=float, default=0.50)
    parser.add_argument('--n_ur',    type=int,   default=5)
    parser.add_argument('--seeds',   type=str,   default='42,43,44')
    parser.add_argument('--dice_bg_mean', type=float,
                        default=float(os.environ.get('DICE_BG_HIP', '0.0')))
    parser.add_argument('--dice_bg_std',  type=float,
                        default=float(os.environ.get('SIGMA_BG_HIP', '0.0')))
    parser.add_argument('--smoke', type=int, default=0)
    args = parser.parse_args()

    smoke   = args.smoke > 0
    n_steps = 5 if smoke else ABLATION_STEPS

    seeds = [int(s) for s in args.seeds.split(',')]
    urs   = [round(args.ur_min + i * (args.ur_max - args.ur_min) / (args.n_ur - 1), 4)
             for i in range(args.n_ur)]
    grid  = [(u, s) for u in urs for s in seeds]
    if smoke:
        grid = grid[:args.smoke]

    thresh = max(0.01, args.dice_bg_mean + 3.0 * args.dice_bg_std)
    print(f"[B4] collapse_thresh={thresh:.6f}  ur={urs}  seeds={seeds}", flush=True)

    def is_collapse(fd, div):
        if div or math.isnan(fd):
            return False
        return fd < thresh

    if smoke:
        class MockDS(torch.utils.data.Dataset):
            def __init__(self):
                H, W = IMG_SIZE
                self.s = [(torch.rand(1, H, W), (torch.rand(1, H, W) > 0.7).float())
                          for _ in range(4)]
            def __len__(self): return len(self.s)
            def __getitem__(self, i): return self.s[i]
        train_ds = MockDS()
        print("[B4][SMOKE] MockDS", flush=True)
    else:
        print("[B4] 加载 HipSliceDataset ...", flush=True)
        train_ds = HipSliceDataset()
        print(f"[B4] Hippo samples={len(train_ds)}", flush=True)

    total  = len(grid)
    device = torch.device(DEVICE)
    write_state("init", {"total": total, "urs": urs, "seeds": seeds})

    cols = ['ur', 'fire_rate', 'seed', 'dataset',
            'final_dice', 'diverged', 'collapsed', 'max_grad_norm',
            'fg_ratio_mean', 'n_steps_run', 'collapse_thresh', 'impl']
    all_rows = []

    for run_idx, (ur, seed_val) in enumerate(grid):
        fire_rate = round(1.0 - ur, 4)
        print(f"\n[B4] [{run_idx+1}/{total}]  ur={ur}  seed={seed_val}", flush=True)
        write_state("running", {"run_idx": run_idx+1, "total": total,
                                "ur": ur, "seed": seed_val})

        set_seed(seed_val)
        ca1 = build_impl2_nca(device)
        ca2 = build_impl2_nca(device)

        result = run_one_cell_impl2(
            ca_list=[ca1, ca2],
            train_ds=train_ds,
            update_rate=ur,
            n_steps=n_steps,
            device=device,
            seed_val=seed_val,
        )

        collapsed_flag = is_collapse(result['final_dice'], result['diverged'])

        def _fmt(v):
            return round(v, 6) if not (math.isnan(v) or math.isinf(v)) else 'nan'

        print(
            f"  final_dice={result['final_dice']:.4f}  "
            f"diverged={result['diverged']}  collapsed={collapsed_flag}",
            flush=True
        )

        row = {
            'ur':              round(ur, 4),
            'fire_rate':       fire_rate,
            'seed':            seed_val,
            'dataset':         'Hippocampus',
            'final_dice':      _fmt(result['final_dice']),
            'diverged':        int(result['diverged']),
            'collapsed':       int(collapsed_flag),
            'max_grad_norm':   _fmt(result['max_grad_norm']),
            'fg_ratio_mean':   _fmt(result['fg_ratio_mean']),
            'n_steps_run':     result['n_steps_run'],
            'collapse_thresh': round(thresh, 6),
            'impl':            'MinimalNCA_impl2',
        }
        all_rows.append(row)
        write_csv(all_rows, OUT_CSV, cols)

    write_state("done", {
        "total": total,
        "diverged_runs":  sum(int(r['diverged'])  for r in all_rows),
        "collapsed_runs": sum(int(r['collapsed']) for r in all_rows),
        "csv": OUT_CSV,
    })
    print(f"\n[B4] 完成。CSV: {OUT_CSV}", flush=True)


if __name__ == '__main__':
    main()
