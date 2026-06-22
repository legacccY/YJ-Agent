"""临界扫描脚本 B1/B2/B3 — NCA-PhaseMap Gate1

复用 C044c run_one_cell 架构（pool/seed/forward/grad 逻辑零改），增加：
  1. clip 维度（--clip_norm None=no-clip[主条件] / 1.0=对照，对齐官方 Agent.py 无 clip）
  2. diverged flag 严记（loss→NaN/Inf → diverged=True，单列不计 collapse）
  3. collapse 判据从 config 读自适应阈（B0 产出），不硬编码 0.01
  4. BraTSSliceDataset（接口与 HipSliceDataset 相同）

三个阶段（--stage B1|B2|B3）：
  B1 粗扫：ur∈{0,.1,.2,.3,.4,.5,.625,.75,1.0} × clip∈{None,1.0}，seed=42，BraTS
  B2 加密：B1 断崖区±0.10 步长0.025 × clip∈{None,1.0}，seed=42（由 --ur_min/ur_max/ur_step 传）
  B3 seed：临界区±0.05 内 5 ur × seed{42,43,44,45,46}，no-clip，BraTS

collapse 判据（冻结，从 B0 config 读）：
    collapse := (not diverged) and final_dice < max(0.01, dice_bg + 3·σ_bg)
    diverged := loss 出现 NaN 或 Inf（严格 isnan/isinf 双检）

输出：results/B1_coarse.csv | B2_fine.csv | B3_seed.csv
列：stage, ur, fire_rate, clip_norm, seed, dataset,
    final_dice, diverged, collapsed, max_grad_norm, fg_ratio_mean

【入口】
    python B1_B2_B3_sweep.py --stage B1
    python B1_B2_B3_sweep.py --stage B2 --ur_min 0.30 --ur_max 0.50 --ur_step 0.025
    python B1_B2_B3_sweep.py --stage B3 --ur_min 0.30 --ur_max 0.50
    python B1_B2_B3_sweep.py --stage B1 --smoke 1   # mock 2 run × 5 step

【环境变量（HPC）】
    BRATS_ROOT      BraTS test/ 目录
    MEDNCA_ROOT     Med-NCA 根目录
    PHASEMAP_OUT    脚本输出根目录（默认=脚本所在目录）
    DICE_BG_BRATS   BraTS dice_bg_mean（B0 产出，冻 config 后注入）
    SIGMA_BG_BRATS  BraTS dice_bg_std （同上）
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

# ─── 路径常量 ───────────────────────────────────────────────────────
MEDNCA_ROOT = os.environ.get(
    'MEDNCA_ROOT',
    os.path.join("D:", os.sep, "YJ-Agent", "project", "meeting", "Med-NCA")
)
OFFICIAL_ROOT = os.path.join(MEDNCA_ROOT, "M3D-NCA-official")
DATA_HIP      = os.path.join(MEDNCA_ROOT, "data", "Task04_Hippocampus")

_BRATS_ROOT_DEFAULT = os.environ.get(
    'BRATS_ROOT',
    os.path.join("D:", os.sep, "YJ-Agent", "project", "meeting",
                 "MedAD-FailMap", "data", "BraTS2021", "test")
)

THIS_DIR    = os.environ.get('PHASEMAP_OUT',
                             os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(THIS_DIR, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

# ─── 超参（零偏离官方） ──────────────────────────────────────────────
DEVICE         = "cuda:0" if torch.cuda.is_available() else "cpu"
IMG_SIZE       = (64, 64)
ABLATION_STEPS = 300           # 官方对齐（C044b/c 同）
LR             = 16e-4
BETAS          = (0.5, 0.5)
CHANNEL_N      = 16
HIDDEN_SIZE    = 128
INFERENCE_STEPS_EVAL = 16
FIXED_INIT_VAR = 0.01
FIXED_POOL     = True

# NCA config 模板（Hippo dataset 构造用）
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

# ─── 共用工具 ────────────────────────────────────────────────────────
def set_seed(s):
    np.random.seed(s)
    torch.manual_seed(s)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(s)


def write_state(path, phase, extra=None):
    state = {"phase": phase, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")}
    if extra:
        state.update(extra)
    with open(path, "w") as f:
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


# ─── 路径 patch（Hippo Dataset 构造用） ─────────────────────────────
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


def get_max_grad_norm(model_list):
    norms = []
    for ca in model_list:
        for param in ca.parameters():
            if param.grad is not None:
                norms.append(float(param.grad.norm().item()))
    return float(np.max(norms)) if norms else float('nan')


# ─── 构建 NCA ────────────────────────────────────────────────────────
def build_nca(device):
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
        nn.init.normal_(ca.fc0.weight, mean=0.0, std=FIXED_INIT_VAR)
        if ca.fc0.bias is not None:
            nn.init.zeros_(ca.fc0.bias)
    return ca


# ─── 数据集 ──────────────────────────────────────────────────────────
class HipSliceDataset(torch.utils.data.Dataset):
    """Hippocampus train split（复用 C044c）。"""
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
        from src.agents.Agent_Med_NCA import Agent_Med_NCA
        agent_tmp = Agent_Med_NCA([ca1, ca2])
        from src.utils.Experiment import Experiment
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


# ─── 核心训练 cell ───────────────────────────────────────────────────
def run_one_cell(ca_list, train_ds, update_rate, n_steps, device, seed_val,
                 clip_norm=None):
    """
    单 run：(update_rate, seed, clip_norm)。
    clip_norm=None → no-clip（主条件，对齐官方 Agent.py L102-103）
    clip_norm=1.0  → 梯度裁剪（对照，解释 G5）

    返回 dict：final_dice, diverged, max_grad_norm, fg_ratio_mean, n_steps_run
    """
    fire_rate = 1.0 - update_rate
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
                x = ca(x, steps=INFERENCE_STEPS_EVAL, fire_rate=fire_rate)

            pred         = x[..., 1:2]                    # [B, H, W, 1]
            lbl_permuted = lbl.permute(0, 2, 3, 1)        # [B, H, W, 1]
            if lbl_permuted.sum() == 0:
                step += 1
                continue

            loss = dice_loss_fn(pred, lbl_permuted)

            # ── diverged 判定（严格 NaN/Inf 双检） ──
            loss_val = loss.item()
            if math.isnan(loss_val) or math.isinf(loss_val):
                diverged   = True
                final_loss = float('nan')
                step += 1
                continue  # 继续跑（不 break），记录 diverged 但完成步数

            loss.backward()

            # 记录梯度（clip 前）
            gn = get_max_grad_norm(ca_list)
            grad_norm_log.append(gn)

            # ── clip_norm：None=no-clip（官方），float=对照 ──
            if clip_norm is not None:
                for ca in ca_list:
                    torch.nn.utils.clip_grad_norm_(ca.parameters(), clip_norm)

            for opt in optimizer:
                opt.step()

            for bi in range(x.shape[0]):
                pool.put(step * 1000 + bi, x[bi])

            final_loss = loss_val
            loss_log.append(final_loss)

            # 前景占比（pred > 0.5）
            with torch.no_grad():
                fg = float((torch.sigmoid(pred) > 0.5).float().mean().item())
            fg_ratio_log.append(fg)

            step += 1

    # ── 结果汇总 ────────────────────────────────────────────────────
    max_gn = float(np.max(grad_norm_log))  if grad_norm_log else float('nan')

    if len(loss_log) >= 10:
        final_dice = float(1.0 - np.mean(loss_log[-10:]))
    elif len(loss_log) > 0:
        final_dice = float(1.0 - loss_log[-1])
    else:
        final_dice = float('nan')  # 全 diverged/skip

    fg_mean = float(np.mean(fg_ratio_log)) if fg_ratio_log else float('nan')

    return {
        'final_dice':    final_dice,
        'diverged':      diverged,
        'max_grad_norm': max_gn,
        'fg_ratio_mean': fg_mean,
        'n_steps_run':   step,
    }


# ─── collapse 判据（从 env/参数读 B0 阈） ───────────────────────────
def make_collapse_fn(dice_bg_mean: float, dice_bg_std: float):
    """返回 collapse 判定函数 f(final_dice, diverged) → bool。"""
    thresh = max(0.01, dice_bg_mean + 3.0 * dice_bg_std)
    print(f"[sweep] collapse_thresh = max(0.01, {dice_bg_mean:.6f}+3×{dice_bg_std:.6f}) = {thresh:.6f}",
          flush=True)

    def _f(final_dice, diverged):
        if diverged:
            return False  # diverged≠collapse，单列不混
        if math.isnan(final_dice):
            return False
        return final_dice < thresh

    _f.thresh = thresh
    return _f


# ─── 构建 run 网格 ───────────────────────────────────────────────────
def build_grid_b1():
    urs   = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.625, 0.75, 1.0]
    clips = [None, 1.0]
    seeds = [42]
    return [(u, c, s) for u in urs for c in clips for s in seeds]


def build_grid_b2(ur_min, ur_max, ur_step):
    urs   = list(np.arange(ur_min, ur_max + ur_step * 0.5, ur_step))
    urs   = [round(u, 4) for u in urs]
    clips = [None, 1.0]
    seeds = [42]
    return [(u, c, s) for u in urs for c in clips for s in seeds]


def build_grid_b3(ur_min, ur_max, ur_list=None):
    # 5 ur × 5 seed，no-clip 主条件；ur_list 提供则直接用（补1 扩 ur 0.45–0.80）
    if ur_list is not None:
        urs = [round(u, 4) for u in ur_list]
    else:
        n_ur  = 5
        urs   = [round(ur_min + i * (ur_max - ur_min) / (n_ur - 1), 4) for i in range(n_ur)]
    seeds = [42, 43, 44, 45, 46]
    clips = [None]
    return [(u, c, s) for u in urs for c in clips for s in seeds]


# ─── 主流程 ──────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="B1/B2/B3 临界扫描")
    parser.add_argument('--stage',    choices=['B1', 'B2', 'B3'], required=True)
    parser.add_argument('--ur_min',   type=float, default=0.25,
                        help='B2/B3 扫描下界')
    parser.add_argument('--ur_max',   type=float, default=0.50,
                        help='B2/B3 扫描上界')
    parser.add_argument('--ur_step',  type=float, default=0.025,
                        help='B2 步长')
    parser.add_argument('--data_root_brats', default=_BRATS_ROOT_DEFAULT)
    parser.add_argument('--fg_thresh',       type=float, default=0.02)
    # B0 产出阈（HPC 跑前通过 env 或 arg 注入）
    parser.add_argument('--dice_bg_mean', type=float,
                        default=float(os.environ.get('DICE_BG_BRATS', 'nan')))
    parser.add_argument('--dice_bg_std',  type=float,
                        default=float(os.environ.get('SIGMA_BG_BRATS', 'nan')))
    parser.add_argument('--smoke', type=int, default=0,
                        help='smoke 模式：仅跑 N 个 run × 5 step')
    parser.add_argument('--ur_list', type=str, default=None,
                        help='B3 显式 ur 列表（逗号分隔，覆盖 linspace），补1 扩 ur 用')
    parser.add_argument('--out_suffix', type=str, default='',
                        help='输出 csv/state 后缀，B3{suffix}_seed.csv，防覆盖既有 B3')
    parser.add_argument('--dataset', choices=['brats', 'hippo'], default='brats',
                        help='数据集：brats(默认) | hippo(补3 Hippo no-clip 尖锐性核)')
    args = parser.parse_args()

    smoke   = args.smoke > 0
    n_steps = 5 if smoke else ABLATION_STEPS

    # ── collapse 阈 ────────────────────────────────────────────────
    dice_bg_mean = args.dice_bg_mean
    dice_bg_std  = args.dice_bg_std
    if math.isnan(dice_bg_mean) or math.isnan(dice_bg_std):
        print(
            "[B1_B2_B3] WARNING: dice_bg_mean/std 未设定（B0 未跑或未注入）。"
            "collapse 阈将退回 0.01（BraTS 会有假性 collapse 风险）。"
            "建议先跑 B0 后再跑此脚本。",
            flush=True
        )
        dice_bg_mean = 0.0
        dice_bg_std  = 0.0
    is_collapse = make_collapse_fn(dice_bg_mean, dice_bg_std)

    # ── 构建 run 网格 ──────────────────────────────────────────────
    if args.stage == 'B1':
        grid   = build_grid_b1()
        out_csv = os.path.join(RESULTS_DIR, "B1_coarse.csv")
        out_state = os.path.join(RESULTS_DIR, "B1_state.json")
    elif args.stage == 'B2':
        grid   = build_grid_b2(args.ur_min, args.ur_max, args.ur_step)
        out_csv = os.path.join(RESULTS_DIR, "B2_fine.csv")
        out_state = os.path.join(RESULTS_DIR, "B2_state.json")
    else:  # B3
        ur_list = None
        if args.ur_list:
            ur_list = [float(x) for x in args.ur_list.split(',')]
        grid   = build_grid_b3(args.ur_min, args.ur_max, ur_list)
        out_csv = os.path.join(RESULTS_DIR, f"B3{args.out_suffix}_seed.csv")
        out_state = os.path.join(RESULTS_DIR, f"B3{args.out_suffix}_state.json")

    if smoke:
        grid = grid[:args.smoke]

    # ── 加载数据 ───────────────────────────────────────────────────
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    if args.dataset == 'hippo':
        ds_label = 'Hippocampus'
        print(f"[{args.stage}] 加载 HipSliceDataset（官方 Med-NCA Hippo 管线）...", flush=True)
        train_ds = HipSliceDataset()
    else:
        ds_label = 'BraTS2021'
        from data_brats import BraTSSliceDataset
        print(f"[{args.stage}] 加载 BraTSSliceDataset ...", flush=True)
        train_ds = BraTSSliceDataset(data_root=args.data_root_brats,
                                      fg_thresh=args.fg_thresh)
    print(f"[{args.stage}] dataset={ds_label} n={len(train_ds)}", flush=True)

    if smoke:
        class MockDS(torch.utils.data.Dataset):
            def __init__(self, n=4):
                H, W = IMG_SIZE
                self.s = [(torch.rand(1, H, W), (torch.rand(1, H, W) > 0.7).float())
                          for _ in range(n)]
            def __len__(self): return len(self.s)
            def __getitem__(self, i): return self.s[i]
        train_ds = MockDS()
        print(f"[{args.stage}][SMOKE] 使用 MockDS", flush=True)

    total  = len(grid)
    device = torch.device(DEVICE)
    print(f"[{args.stage}] 共 {total} run，stage={args.stage}，n_steps={n_steps}", flush=True)
    write_state(out_state, "init", {"stage": args.stage, "total": total})

    cols = ['stage', 'ur', 'fire_rate', 'clip_norm', 'seed', 'dataset',
            'final_dice', 'diverged', 'collapsed', 'max_grad_norm',
            'fg_ratio_mean', 'n_steps_run', 'collapse_thresh']
    all_rows = []

    for run_idx, (ur, clip, seed_val) in enumerate(grid):
        fire_rate   = round(1.0 - ur, 4)
        clip_label  = str(clip) if clip is not None else 'None'

        print(
            f"\n[{args.stage}] [{run_idx+1}/{total}]  "
            f"ur={ur}  clip={clip_label}  seed={seed_val}",
            flush=True
        )
        write_state(out_state, "running", {
            "run_idx": run_idx+1, "total": total,
            "ur": ur, "clip": clip_label, "seed": seed_val
        })

        set_seed(seed_val)
        ca1 = build_nca(device)
        ca2 = build_nca(device)

        result = run_one_cell(
            ca_list=[ca1, ca2],
            train_ds=train_ds,
            update_rate=ur,
            n_steps=n_steps,
            device=device,
            seed_val=seed_val,
            clip_norm=clip,
        )

        collapsed_flag = is_collapse(result['final_dice'], result['diverged'])

        print(
            f"  final_dice={result['final_dice']:.4f}  "
            f"diverged={result['diverged']}  "
            f"collapsed={collapsed_flag}  "
            f"max_grad={result['max_grad_norm']:.4f}",
            flush=True
        )

        def _fmt(v):
            return round(v, 6) if not (math.isnan(v) or math.isinf(v)) else 'nan'

        row = {
            'stage':          args.stage,
            'ur':             round(ur, 4),
            'fire_rate':      fire_rate,
            'clip_norm':      clip_label,
            'seed':           seed_val,
            'dataset':        ds_label,
            'final_dice':     _fmt(result['final_dice']),
            'diverged':       int(result['diverged']),
            'collapsed':      int(collapsed_flag),
            'max_grad_norm':  _fmt(result['max_grad_norm']),
            'fg_ratio_mean':  _fmt(result['fg_ratio_mean']),
            'n_steps_run':    result['n_steps_run'],
            'collapse_thresh': round(is_collapse.thresh, 6),
        }
        all_rows.append(row)
        write_csv(all_rows, out_csv, cols)

    write_state(out_state, "done", {
        "total": total,
        "diverged_runs": sum(int(r['diverged']) for r in all_rows),
        "collapsed_runs": sum(int(r['collapsed']) for r in all_rows),
        "csv": out_csv,
    })
    print(f"\n[{args.stage}] 完成。CSV: {out_csv}", flush=True)


if __name__ == '__main__':
    main()
