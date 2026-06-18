"""G 梯度时序轨迹 — NCA-PhaseMap Gate1 腿②

扩展自 C044 梯度记录母版，改为逐 step 落 csv，测 A3/K4（梯度先死 vs 网络先垮因果）。

三档（--run_id G1|G2|G3）：
    G1 ur=0.45 全塌   × clip∈{None,1.0} × seed{42,43,44}  Hippo
    G2 ur=0.25 全活   × clip∈{None,1.0} × seed{42,43,44}  Hippo
    G3 ur=0.30 一活一塌 × clip∈{None,1.0} × seed{42,43,44}  Hippo（最干净因果对照）

clip=None → no-clip（主条件，对齐官方，A3 必在此上测）
clip=1.0  → 对照（解释 G5 r=0.238 是 clip artifact）

每 step 落：step, per-layer grad_norm（各层独立列）, dice_proxy（1-loss）,
            fg_ratio（pred>0.5比例）, diverged_flag

阈值敏感性扫描（P_g×P_f×N 27 组）放 G_sensitivity.py 后处理，不在训练里做。

【输出】
    results/G_traj_g1.csv / G_traj_g2.csv / G_traj_g3.csv
    列：run_id, ur, clip_norm, seed, step,
        grad_norm_fc0, grad_norm_fc1, grad_norm_max, grad_norm_mean,
        dice_proxy, fg_ratio, diverged

    results/G_state.json  心跳

【入口】
    python G_gradient_traj.py --run_id G1
    python G_gradient_traj.py --run_id G2
    python G_gradient_traj.py --run_id G3
    python G_gradient_traj.py --run_id G1 --smoke 1

【环境变量（HPC）】
    MEDNCA_ROOT   Med-NCA 根目录
    PHASEMAP_OUT  输出根目录
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

# ─── 超参（零偏离官方） ──────────────────────────────────────────────
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

# G 档配置
G_CONFIGS = {
    'G1': {'ur': 0.45, 'label': 'collapse'},
    'G2': {'ur': 0.25, 'label': 'survive'},
    'G3': {'ur': 0.30, 'label': 'critical'},
}
SEEDS      = [42, 43, 44]
CLIP_MODES = [None, 1.0]  # None=no-clip（主条件），1.0=对照


# ─── 工具 ────────────────────────────────────────────────────────────
def set_seed(s):
    np.random.seed(s)
    torch.manual_seed(s)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(s)


def dice_loss_fn(logit, target, smooth=1.0):
    pred  = torch.sigmoid(logit).flatten()
    tgt   = target.flatten()
    inter = (pred * tgt).sum()
    return 1.0 - (2.0 * inter + smooth) / (pred.sum() + tgt.sum() + smooth)


def write_state(path, phase, extra=None):
    state = {"phase": phase, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")}
    if extra:
        state.update(extra)
    with open(path, "w") as f:
        json.dump(state, f, indent=2)


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


# ─── 数据集（Hippocampus，复用 C044c） ──────────────────────────────
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

    def __len__(self): return len(self.pool)

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


def build_nca(device):
    sys.path.insert(0, OFFICIAL_ROOT)
    os.chdir(OFFICIAL_ROOT)
    from src.models.Model_BackboneNCA import BackboneNCA
    ca = BackboneNCA(CHANNEL_N, 0.5, device, hidden_size=HIDDEN_SIZE,
                     input_channels=1).to(device)
    with torch.no_grad():
        nn.init.normal_(ca.fc0.weight, mean=0.0, std=FIXED_INIT_VAR)
        if ca.fc0.bias is not None:
            nn.init.zeros_(ca.fc0.bias)
    return ca


def get_per_layer_grad_norms(ca_list):
    """返回 {layer_key: norm} 聚合两 NCA 模型的同名层梯度 norm（取 max，两层独立）。"""
    norms = {}
    for i, ca in enumerate(ca_list):
        for name, param in ca.named_parameters():
            if param.grad is not None:
                key = f"ca{i}_{name.replace('.', '_')}"
                norms[key] = float(param.grad.norm().item())
    return norms


# ─── 逐 step 训练（梯度时序核心） ───────────────────────────────────
def run_traj(ca_list, train_ds, update_rate, n_steps, device, seed_val,
             clip_norm, run_id, csv_path):
    """
    逐 step 记录 per-layer grad_norm / dice_proxy / fg_ratio / diverged，
    每 step 追加写 csv（防断电丢数据）。

    clip_norm=None → no-clip（主条件）
    clip_norm=1.0  → 对照（A3 支柱2 修正：clip 下 r=0.238 是 artifact）
    """
    fire_rate  = 1.0 - update_rate
    clip_label = str(clip_norm) if clip_norm is not None else 'None'

    set_seed(seed_val)
    optimizer = [optim.Adam(ca.parameters(), lr=LR, betas=BETAS) for ca in ca_list]
    loader    = DataLoader(train_ds, batch_size=4, shuffle=True,
                           num_workers=0, pin_memory=False)
    pool      = SimplePool(maxsize=40)

    diverged = False

    # 提前确定 CSV 列名（需跑一 batch 前向才知道层名）
    # 先用 dummy 枚举层名
    layer_keys = []
    for i, ca in enumerate(ca_list):
        for name, _ in ca.named_parameters():
            layer_keys.append(f"ca{i}_{name.replace('.', '_')}")

    cols = (['run_id', 'ur', 'fire_rate', 'clip_norm', 'seed', 'step',
              'dice_proxy', 'fg_ratio', 'diverged', 'grad_norm_max', 'grad_norm_mean']
             + layer_keys)

    # 首次写 header（如文件不存在）
    file_exists = os.path.exists(csv_path)
    f_csv = open(csv_path, 'a', newline='')
    writer = csv.DictWriter(f_csv, fieldnames=cols, extrasaction='ignore')
    if not file_exists:
        writer.writeheader()

    step = 0
    try:
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

                pred         = x[..., 1:2]
                lbl_permuted = lbl.permute(0, 2, 3, 1)

                if lbl_permuted.sum() == 0:
                    step += 1
                    continue

                loss     = dice_loss_fn(pred, lbl_permuted)
                loss_val = loss.item()

                is_div = math.isnan(loss_val) or math.isinf(loss_val)
                if is_div:
                    diverged = True

                if not is_div:
                    loss.backward()

                    # 记录 per-layer grad（clip 前真实梯度）
                    layer_norms = get_per_layer_grad_norms(ca_list)
                    all_nv = list(layer_norms.values())
                    gn_max  = float(np.max(all_nv))  if all_nv else float('nan')
                    gn_mean = float(np.mean(all_nv)) if all_nv else float('nan')

                    # clip（None=no-clip 主条件）
                    if clip_norm is not None:
                        for ca in ca_list:
                            torch.nn.utils.clip_grad_norm_(ca.parameters(), clip_norm)

                    for opt in optimizer:
                        opt.step()

                    dice_proxy = float(1.0 - loss_val)

                    with torch.no_grad():
                        fg_ratio = float((torch.sigmoid(pred) > 0.5).float().mean().item())

                    for bi in range(x.shape[0]):
                        pool.put(step * 1000 + bi, x[bi])

                else:
                    layer_norms = {k: 'nan' for k in layer_keys}
                    gn_max  = float('nan')
                    gn_mean = float('nan')
                    dice_proxy = float('nan')
                    fg_ratio   = float('nan')

                # 每 step 落 csv
                row = {
                    'run_id':        run_id,
                    'ur':            round(update_rate, 4),
                    'fire_rate':     round(fire_rate, 4),
                    'clip_norm':     clip_label,
                    'seed':          seed_val,
                    'step':          step,
                    'dice_proxy':    round(dice_proxy, 6) if not math.isnan(dice_proxy) else 'nan',
                    'fg_ratio':      round(fg_ratio, 6)   if not math.isnan(fg_ratio) else 'nan',
                    'diverged':      int(diverged),
                    'grad_norm_max': round(gn_max, 6)     if not math.isnan(gn_max) else 'nan',
                    'grad_norm_mean':round(gn_mean, 6)    if not math.isnan(gn_mean) else 'nan',
                }
                for k in layer_keys:
                    v = layer_norms.get(k, float('nan'))
                    row[k] = round(v, 6) if isinstance(v, float) and not math.isnan(v) else 'nan'

                writer.writerow(row)
                f_csv.flush()

                step += 1

    finally:
        f_csv.close()

    return diverged


# ─── 主流程 ──────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="G 梯度时序轨迹（逐 step）")
    parser.add_argument('--run_id', choices=['G1', 'G2', 'G3'], required=True)
    parser.add_argument('--smoke',  type=int, default=0,
                        help='smoke: 跑 N run × 5 step')
    args = parser.parse_args()

    cfg    = G_CONFIGS[args.run_id]
    ur     = cfg['ur']
    smoke  = args.smoke > 0
    n_steps = 5 if smoke else ABLATION_STEPS

    out_csv   = os.path.join(RESULTS_DIR, f"G_traj_{args.run_id.lower()}.csv")
    out_state = os.path.join(RESULTS_DIR, "G_state.json")

    # 删除旧 csv（run 从头开始）
    if os.path.exists(out_csv):
        os.remove(out_csv)

    write_state(out_state, "init", {
        "run_id": args.run_id, "ur": ur,
        "seeds": SEEDS, "clips": [str(c) for c in CLIP_MODES]
    })

    print(f"[G] run_id={args.run_id}  ur={ur}  seeds={SEEDS}  "
          f"clips={CLIP_MODES}  n_steps={n_steps}", flush=True)

    sys.path.insert(0, OFFICIAL_ROOT)
    os.chdir(OFFICIAL_ROOT)

    if smoke:
        class MockDS(torch.utils.data.Dataset):
            def __init__(self):
                H, W = IMG_SIZE
                self.s = [(torch.rand(1, H, W), (torch.rand(1, H, W) > 0.7).float())
                          for _ in range(4)]
            def __len__(self): return len(self.s)
            def __getitem__(self, i): return self.s[i]
        train_ds = MockDS()
        print("[G][SMOKE] MockDS", flush=True)
    else:
        print("[G] 加载 HipSliceDataset ...", flush=True)
        train_ds = HipSliceDataset()
        print(f"[G] Hippo samples={len(train_ds)}", flush=True)

    device = torch.device(DEVICE)

    # 构建 run 列表
    runs = [(c, s) for c in CLIP_MODES for s in SEEDS]
    if smoke:
        runs = runs[:args.smoke]

    total = len(runs)
    for run_idx, (clip, seed_val) in enumerate(runs):
        clip_label = str(clip) if clip is not None else 'None'
        print(
            f"\n[G] [{run_idx+1}/{total}]  ur={ur}  clip={clip_label}  seed={seed_val}",
            flush=True
        )
        write_state(out_state, "running", {
            "run_id": args.run_id, "ur": ur,
            "clip": clip_label, "seed": seed_val,
            "run_idx": run_idx+1, "total": total,
        })

        set_seed(seed_val)
        ca1 = build_nca(device)
        ca2 = build_nca(device)

        diverged = run_traj(
            ca_list=[ca1, ca2],
            train_ds=train_ds,
            update_rate=ur,
            n_steps=n_steps,
            device=device,
            seed_val=seed_val,
            clip_norm=clip,
            run_id=args.run_id,
            csv_path=out_csv,
        )
        print(f"  done  diverged={diverged}", flush=True)

    write_state(out_state, "done", {
        "run_id": args.run_id, "total_runs": total, "csv": out_csv
    })
    print(f"\n[G] 完成 {args.run_id}。CSV: {out_csv}", flush=True)


if __name__ == '__main__':
    main()
