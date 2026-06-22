"""probe_rho.py — ρ(J) 谱半径探针 — NCA-PhaseMap 补2 §1
服务项目：NCA-PhaseMap / K-new-3 机制段（解耦路A）

方法：
    受控随机初始化 BackboneNCA（fc0.w~N(0,0.01), fc0.b=0,
    fc1.w~N(0,0.01) 非零，fc1.b=0），不训练、不读训练 csv。
    背景态 x0（可选 zero 或 foreground 演化态），单步 update 算子 F:x→NCA_step(x,fire_rate)。
    Jacobian 不显式建（HWC² 巨阵），power iteration：
      随机向量 v，反复算 Jv/Jᵀv（autograd vjp），Rayleigh 商收敛到 λ_max/谱半径。
    n_iter=100, tol=1e-6。
    λ_max=0 是 CA 相变判据（收缩域判据，[2606.14521]）。

参考：locuslab/deq lib/jacobian.py（power_method 写法）。

x0_mode 参数（planner 揪问题修复）：
    zero（旧行为）：x0=全零背景 seed → 背景态 f'(0)≈0 → ρ 恒≈1 → 无信号。
    foreground（默认，新行为）：x0=喂真实 patch 跑 warmup_steps（默认8步）后的演化态，
        贴近训练网络的工作点，测工作点附近的局部收缩率（线性化更有意义）。
    物理含义：不再是吸收域判据，而是工作点局部动力学稳定性。
    csv 输出新增 x0_mode 列标清。

注意（stochastic mask 处理）：
    NCA update 含随机 mask（fire_rate 控制哪些 cell 更新）。
    power iter 时固定单次 mask 实例（torch.no_grad() 包住 mask 采样，
    同一 forward 图上反复做 vjp），测**实际算子在该 mask 下的** ρ。
    期望 Jacobian E[J] = I + p·diag(f')P 可通过多次平均，
    此脚本默认固定 mask 实例（更简单/可重复），
    # TODO: 期望版（多次 mask 采样平均）见 --n_mask_avg 参数（暂未实现）。

【入口】
    python probe_rho.py [--dataset hippo|brats|both]
                        [--x0_mode zero|foreground]
                        [--warmup_steps 8]
                        [--n_iter 100]
                        [--smoke 1] [--out_suffix _test]

【输出】
    results/probe_rho.csv
    列: ur, fire_rate, dataset, init_seed, x0_mode,
        rho, lambda_max, n_iter_conv, converged
    results/probe_rho_state.json  心跳

【环境变量（HPC）】
    MEDNCA_ROOT    Med-NCA 根目录
    BRATS_ROOT     BraTS test/ 目录
    PHASEMAP_OUT   输出根目录
"""

import os
import sys
import csv
import json
import math
import time
import argparse
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

# ─── 路径常量（复用 B1_B2_B3_sweep.py 口径） ────────────────────────
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

# ─── NCA 超参（零偏离官方） ──────────────────────────────────────────
CHANNEL_N   = 16
HIDDEN_SIZE = 128
DEVICE      = "cuda:0" if torch.cuda.is_available() else "cpu"
IMG_SIZE    = (64, 64)
LR          = 16e-4
BETAS       = (0.5, 0.5)
INFERENCE_STEPS_EVAL = 16

FIXED_INIT_VAR = 0.01

# ur 网格（对齐补1/补3）
UR_GRID = [0.25, 0.30, 0.35, 0.40, 0.45, 0.50,
           0.55, 0.60, 0.65, 0.70, 0.75, 0.80]

INIT_SEEDS = [42, 43, 44, 45, 46]

# Power iteration 超参
N_ITER_DEFAULT = 100
TOL_DEFAULT    = 1e-6

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


# ─── 工具函数 ─────────────────────────────────────────────────────────

def set_seed(s):
    np.random.seed(s)
    torch.manual_seed(s)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(s)


def write_state(path, phase, extra=None):
    state = {"phase": phase, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")}
    if extra:
        state.update(extra)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def write_csv(rows, path, cols):
    with open(path, 'w', newline='', encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)


def _fmt(v):
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return 'nan'
    if isinstance(v, float):
        return round(v, 8)
    return v


# ─── 路径 patch ───────────────────────────────────────────────────────

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


# ─── 受控初始化 NCA（同 probe_sigma.py） ─────────────────────────────

def build_controlled_nca(device, init_seed):
    """
    受控随机初始化 BackboneNCA（破循环论证，不读训练权重）。
    fc1.w~N(0,0.01) 非零（修旧 M1 bug，测量协议，论文须写明）。
    """
    set_seed(init_seed)
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
        nn.init.normal_(ca.fc1.weight, mean=0.0, std=FIXED_INIT_VAR)
        if ca.fc1.bias is not None:
            nn.init.zeros_(ca.fc1.bias)

    return ca


# ─── make_seed + 背景态 ───────────────────────────────────────────────

def make_seed(img, channel_n, device):
    """img: [B, C, H, W] → seed: [B, H, W, channel_n]"""
    B, C, H, W = img.shape
    seed = torch.zeros(B, H, W, channel_n, device=device)
    seed[..., :C] = img.permute(0, 2, 3, 1)
    return seed


def make_background_seed(device, h=64, w=64):
    """
    背景态 x0：全零前景，channel 0 = 全零图（纯背景）。
    x0_mode='zero' 时使用；背景态 f'(0)≈0 可能导致 ρ 恒≈1 无信号（planner 揪）。
    """
    seed = torch.zeros(1, h, w, CHANNEL_N, device=device, requires_grad=False)
    return seed


def make_foreground_seed(ca, patch_img, fire_rate, device, warmup_steps=8, mask_seed=9999):
    """
    foreground 演化态 x0：喂真实 patch 跑 warmup_steps 步后的演化态，
    贴近训练网络工作点，测工作点局部收缩率（比纯零背景更有动力学意义）。

    Args:
        ca:           BackboneNCA（已 eval，无 grad）
        patch_img:    [1, C, H, W] float tensor（真实 patch，CPU）
        fire_rate:    1 - ur
        device:
        warmup_steps: warmup 步数（默认8），研究员可通过 --warmup_steps 调
        mask_seed:    warmup 阶段 torch seed（固定保证可复现）

    Returns:
        x0:  [1, H, W, channel_n] tensor，detached（无 grad，作为线性化点）

    注意：
      - warmup 不建图（no_grad），只取演化末态作线性化点。
      - mask_seed 与 power_iter seed 分开（power_iter 用 init_seed*1000），不重叠。
    """
    img = patch_img.to(device)
    x = make_seed(img, CHANNEL_N, device)   # [1, H, W, ch]

    torch.manual_seed(mask_seed)
    with torch.no_grad():
        x = ca(x, steps=warmup_steps, fire_rate=fire_rate)

    return x.detach()


# ─── 数据集加载（与 probe_sigma 相同） ───────────────────────────────

def load_dataset(dataset_name, brats_root, smoke):
    """返回 (ds, label_str)；仅用于 ρ 探针从真实 patch 取背景态（可选）。"""
    if smoke:
        class MockDS(torch.utils.data.Dataset):
            def __init__(self, n=8):
                H, W = IMG_SIZE
                self.s = [
                    (torch.rand(1, H, W), (torch.rand(1, H, W) > 0.7).float())
                    for _ in range(n)
                ]
            def __len__(self): return len(self.s)
            def __getitem__(self, i): return self.s[i]
        return MockDS(), "mock"

    if dataset_name == 'hippo':
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
        ca1_tmp = BackboneNCA(CHANNEL_N, 0.5, device, hidden_size=HIDDEN_SIZE, input_channels=1).to(device)
        ca2_tmp = BackboneNCA(CHANNEL_N, 0.5, device, hidden_size=HIDDEN_SIZE, input_channels=1).to(device)
        agent_tmp = Agent_Med_NCA([ca1_tmp, ca2_tmp])
        exp_tmp   = Experiment(config, dataset_nii, [ca1_tmp, ca2_tmp], agent_tmp)
        patch_experiment_paths(exp_tmp)
        dataset_nii.set_experiment(exp_tmp)
        exp_tmp.set_model_state('train')
        dataset_nii.set_size(IMG_SIZE)

        samples = []
        for idx in range(len(dataset_nii)):
            _, img_np, lbl_np = dataset_nii[idx]
            img = torch.from_numpy(img_np).permute(2, 0, 1).float()
            lbl = torch.from_numpy(lbl_np).permute(2, 0, 1).float()
            samples.append((img, lbl))

        class ListDS(torch.utils.data.Dataset):
            def __init__(self, s): self.s = s
            def __len__(self): return len(self.s)
            def __getitem__(self, i): return self.s[i]

        return ListDS(samples), "hippo"

    else:  # brats
        exp_dir = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, exp_dir)
        from data_brats import BraTSSliceDataset
        ds = BraTSSliceDataset(data_root=brats_root, fg_thresh=0.02)
        return ds, "brats"


# ─── Power Iteration（autograd vjp，参 locuslab/deq） ────────────────

def power_iteration_rho(ca, x0, fire_rate, n_iter, tol, device, init_seed):
    """
    估计单步算子 F(x)=NCA_step(x, fire_rate) 在 x0 处的 Jacobian 谱半径 ρ(J)。

    策略：固定单次 mask 实例（stochastic mask 在 forward 时采样一次，
    整个 power iter 过程用同一计算图反复做 vjp）。
    这测量「实际算子在该 mask 下的 ρ」而非期望版本。
    # TODO: 期望版（多次 mask 采样平均）见 --n_mask_avg 参数（暂未实现）。

    实现参考：locuslab/deq lib/jacobian.py power_method
      - 每步：v_new = J^T v / ||J^T v||（vjp），Rayleigh 商 = v^T J v / v^T v
      - 收敛判据：|λ_k - λ_{k-1}| / max(|λ_k|, 1e-8) < tol

    注意：
      - x0 需要 requires_grad=True，ca 参数无需 grad（probe 不训练）
      - 固定 mask：torch.manual_seed(init_seed) 在 forward 前设，保证 mask 可重复

    TODO: BackboneNCA forward 内部的随机 mask 是否通过 torch.bernoulli 实现？
      若否（如 numpy.random），则 torch.manual_seed 不足以固定，需确认官方实现。
      主线跑时：若 power iter 不收敛（n_iter_conv 始终=n_iter），
      检查 ca.forward 里的 mask 采样方式。
    """
    H, W = IMG_SIZE

    # x0: [1, H, W, channel_n]，需要 grad
    x0_detach = x0.detach().clone().to(device)
    x0_detach.requires_grad_(True)

    # 固定随机 mask（固定 torch seed，使 mask 可重复）
    torch.manual_seed(init_seed)

    # 单次 forward 建图（不 no_grad）
    # fire_rate 控制 stochastic update mask
    y = ca(x0_detach, steps=1, fire_rate=fire_rate)  # [1, H, W, ch]

    # 初始化随机单位向量 v（与 y 形状相同）
    set_seed(init_seed + 1000)  # 和 mask seed 分开
    v = torch.randn_like(y)
    v = v / (v.norm() + 1e-12)

    lambda_prev = float('nan')
    n_iter_conv = n_iter
    lambda_max  = float('nan')

    for it in range(n_iter):
        # Jᵀv（vjp）：对 y 关于 x0 的梯度，方向为 v
        # retain_graph=True：同一计算图反复用
        try:
            Jt_v = torch.autograd.grad(
                outputs=y,
                inputs=x0_detach,
                grad_outputs=v,
                retain_graph=True,
                create_graph=False,
            )[0]  # [1, H, W, ch]，= J^T v
        except RuntimeError as e:
            # grad 计算失败（如 NCA 内部有 in-place op 导致图断裂）
            # TODO: 若此处报错 "one of the variables needed for gradient computation
            #       has been modified by an inplace operation"，
            #       需在 build_controlled_nca 后手动 ca.eval() + 检查 forward 里的 in-place op
            print(f"    [ρ] autograd.grad 失败 iter={it}: {e}", flush=True)
            lambda_max = float('nan')
            n_iter_conv = it
            break

        # Rayleigh 商 λ = v^T (J^T v) / ||v||² = (v·Jᵀv) / (v·v)
        # 但我们用的是 Jᵀv 近似主特征值（幂法在对称算子上 Jv=Jᵀv，非对称则这里估 Jᵀ 的主奇异值）
        # TODO: 对非对称 Jacobian，power iter Jᵀv 收敛到最大**左**奇异向量，
        #       对应最大奇异值 σ_max（而非特征值）。
        #       若 J 近似对称（NCA 在背景态常见），σ_max ≈ |λ_max|。
        #       论文须区分「最大奇异值」和「谱半径」，此处存疑，标注供主线确认。
        norm_Jtv = Jt_v.norm().item()
        if norm_Jtv < 1e-20:
            # 算子零化（可能 collapse 态），ρ≈0
            lambda_max = 0.0
            n_iter_conv = it
            break

        lambda_k = float((v * Jt_v).sum().item()) / (float((v * v).sum().item()) + 1e-20)
        lambda_max = abs(lambda_k)  # 谱半径取绝对值

        # 收敛判定
        if not math.isnan(lambda_prev):
            rel_diff = abs(lambda_max - abs(lambda_prev)) / max(abs(lambda_max), 1e-8)
            if rel_diff < tol:
                n_iter_conv = it + 1
                break

        lambda_prev = lambda_k
        # 更新 v：归一化 Jᵀv
        v = Jt_v / (norm_Jtv + 1e-12)

    return float(lambda_max), n_iter_conv


# ─── 单次 (ur, init_seed, dataset) 探针 ─────────────────────────────

def run_probe_rho(ca, ur, n_iter, tol, device, init_seed, dataset_label,
                  x0_mode='foreground', patch_img=None, warmup_steps=8,
                  smoke=False):
    """
    用线性化态 x0 估 ρ(J)。

    x0_mode:
      'zero'       : x0=全零背景 seed（旧行为，f'(0)≈0 可能 ρ≈1 无信号）
      'foreground' : x0=真实 patch 跑 warmup_steps 步后的演化态（默认，工作点）

    Args:
        ca:           BackboneNCA（eval）
        ur:           update ratio（0~1）
        n_iter:       power iteration 最大步数
        tol:          收敛阈
        device:
        init_seed:    power iter seed（与 warmup mask seed 分开）
        dataset_label: 仅用于 csv 标签
        x0_mode:      'zero' | 'foreground'（默认 foreground）
        patch_img:    [1, C, H, W] float tensor，foreground 模式必须提供
        warmup_steps: foreground 模式 warmup 步数（默认 8）
        smoke:        smoke 模式用极少 iter

    Returns:
        dict: rho, lambda_max, n_iter_conv, converged, x0_mode
    """
    fire_rate = round(1.0 - ur, 6)
    H, W = IMG_SIZE

    if x0_mode == 'foreground':
        if patch_img is None:
            raise ValueError(
                "x0_mode='foreground' 需提供 patch_img（真实 patch [1,C,H,W]）"
            )
        x0 = make_foreground_seed(
            ca=ca,
            patch_img=patch_img,
            fire_rate=fire_rate,
            device=device,
            warmup_steps=warmup_steps,
            mask_seed=9999,
        )
    else:  # 'zero'
        x0 = make_background_seed(device, h=H, w=W)

    if smoke:
        n_iter_actual = min(n_iter, 5)
    else:
        n_iter_actual = n_iter

    lambda_max, n_iter_conv = power_iteration_rho(
        ca=ca,
        x0=x0,
        fire_rate=fire_rate,
        n_iter=n_iter_actual,
        tol=tol,
        device=device,
        init_seed=init_seed,
    )

    converged = (n_iter_conv < n_iter_actual)

    rho_str = f"{lambda_max:.6f}" if not math.isnan(lambda_max) else "nan"
    print(
        f"    [ρ] ur={ur:.2f} seed={init_seed} ds={dataset_label} "
        f"x0={x0_mode} rho={rho_str} n_iter_conv={n_iter_conv} "
        f"converged={converged}",
        flush=True
    )

    return {
        'rho':         lambda_max,
        'lambda_max':  lambda_max,
        'n_iter_conv': n_iter_conv,
        'converged':   int(converged),
        'x0_mode':     x0_mode,
    }


# ─── 主流程 ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="ρ(J) 谱半径探针 — NCA-PhaseMap §1")
    parser.add_argument('--dataset',    choices=['hippo', 'brats', 'both'],
                        default='hippo', help='数据集（foreground 模式需真实 patch）')
    parser.add_argument('--x0_mode',    choices=['zero', 'foreground'],
                        default='foreground',
                        help='线性化点选择：zero=全零背景（旧行为，f\'(0)≈0可能 ρ≈1无信号）；'
                             'foreground=真实patch演化态（默认，工作点局部收缩率）')
    parser.add_argument('--warmup_steps', type=int, default=8,
                        help='foreground 模式 warmup 步数（默认 8）')
    parser.add_argument('--n_iter',     type=int, default=N_ITER_DEFAULT,
                        help='power iteration 最大步数（默认 100）')
    parser.add_argument('--tol',        type=float, default=TOL_DEFAULT,
                        help='收敛阈（默认 1e-6）')
    parser.add_argument('--ur_list',    type=str, default=None,
                        help='覆盖默认 ur 网格（逗号分隔）')
    parser.add_argument('--seeds',      type=str, default='42,43,44,45,46',
                        help='init_seed 列表（逗号分隔）')
    parser.add_argument('--brats_root', default=_BRATS_ROOT_DEFAULT)
    parser.add_argument('--smoke',      type=int, default=0,
                        help='smoke 模式：1=仅前 2 run + 5 iter')
    parser.add_argument('--out_suffix', type=str, default='',
                        help='输出文件后缀，防覆盖既有结果')
    args = parser.parse_args()

    smoke        = args.smoke > 0
    n_iter       = args.n_iter
    tol          = args.tol
    x0_mode      = args.x0_mode
    warmup_steps = args.warmup_steps
    init_seeds   = [int(s) for s in args.seeds.split(',')]
    ur_grid      = ([float(u) for u in args.ur_list.split(',')]
                    if args.ur_list else UR_GRID)

    datasets = (['hippo', 'brats'] if args.dataset == 'both'
                else [args.dataset])

    out_csv   = os.path.join(RESULTS_DIR, f"probe_rho{args.out_suffix}.csv")
    out_state = os.path.join(RESULTS_DIR, f"probe_rho{args.out_suffix}_state.json")

    # x0_mode 新增列
    cols = ['ur', 'fire_rate', 'dataset', 'init_seed', 'x0_mode',
            'rho', 'lambda_max', 'n_iter_conv', 'converged']

    all_rows = []
    device   = torch.device(DEVICE)

    print(f"[probe_rho] 开始 ρ(J) 探针", flush=True)
    print(f"  ur_grid={ur_grid}", flush=True)
    print(f"  init_seeds={init_seeds}", flush=True)
    print(f"  n_iter={n_iter}  tol={tol}  smoke={smoke}", flush=True)
    print(f"  x0_mode={x0_mode}  warmup_steps={warmup_steps}", flush=True)
    print(f"  datasets={datasets}", flush=True)
    if x0_mode == 'foreground':
        print(
            "  [注意] x0_mode=foreground：需加载数据集取真实 patch 做 warmup 演化态。",
            flush=True
        )
    else:
        print(
            "  [注意] x0_mode=zero：x0=全零背景，dataset 参数只影响 csv 标签列。",
            flush=True
        )
    write_state(out_state, "init", {
        "ur_grid": ur_grid, "init_seeds": init_seeds,
        "n_iter": n_iter, "tol": tol, "datasets": datasets,
        "x0_mode": x0_mode, "warmup_steps": warmup_steps,
    })

    for ds_label in datasets:
        # foreground 模式需加载数据集取一张真实 patch
        patch_img = None
        if x0_mode == 'foreground':
            print(f"\n[probe_rho] 加载数据集 {ds_label} 取 foreground patch...", flush=True)
            ds, _ = load_dataset(ds_label, args.brats_root, smoke)
            img_first, _ = ds[0]
            # 统一形状到 [1, C, H, W]
            if img_first.dim() == 2:
                img_first = img_first.unsqueeze(0)
            if img_first.shape[0] > img_first.shape[-1]:
                img_first = img_first.permute(2, 0, 1)
            patch_img = img_first[:1].unsqueeze(0).float()  # [1, 1, H, W]
            print(f"  patch shape={patch_img.shape}", flush=True)

        grid = [(ur, seed) for ur in ur_grid for seed in init_seeds]
        if smoke:
            grid = grid[:2]

        for run_idx, (ur, init_seed) in enumerate(grid):
            fire_rate = round(1.0 - ur, 6)
            print(
                f"\n[probe_rho] [{ds_label}] [{run_idx+1}/{len(grid)}]  "
                f"ur={ur}  fire_rate={fire_rate}  init_seed={init_seed}  x0={x0_mode}",
                flush=True
            )
            write_state(out_state, "running", {
                "dataset": ds_label, "ur": ur,
                "init_seed": init_seed, "x0_mode": x0_mode,
                "run": run_idx + 1, "total": len(grid)
            })

            ca = build_controlled_nca(device, init_seed)
            ca.eval()  # eval mode，关 dropout 等（如有），不影响 NCA stochastic mask

            try:
                res = run_probe_rho(
                    ca=ca,
                    ur=ur,
                    n_iter=n_iter,
                    tol=tol,
                    device=device,
                    init_seed=init_seed,
                    dataset_label=ds_label,
                    x0_mode=x0_mode,
                    patch_img=patch_img,
                    warmup_steps=warmup_steps,
                    smoke=smoke,
                )
            except Exception as ex:
                print(f"  [probe_rho] 报错: {ex}", flush=True)
                res = {
                    'rho': float('nan'), 'lambda_max': float('nan'),
                    'n_iter_conv': -1, 'converged': 0, 'x0_mode': x0_mode,
                }

            row = {
                'ur':          round(ur, 4),
                'fire_rate':   round(fire_rate, 4),
                'dataset':     ds_label,
                'init_seed':   init_seed,
                'x0_mode':     x0_mode,
                'rho':         _fmt(res['rho']),
                'lambda_max':  _fmt(res['lambda_max']),
                'n_iter_conv': res['n_iter_conv'],
                'converged':   res['converged'],
            }
            all_rows.append(row)
            write_csv(all_rows, out_csv, cols)

    write_state(out_state, "done", {
        "total_runs": len(all_rows),
        "converged_count": sum(r['converged'] for r in all_rows),
        "csv": out_csv,
        "x0_mode": x0_mode,
    })
    print(f"\n[probe_rho] 完成。CSV: {out_csv}", flush=True)
    conv_n = sum(r['converged'] for r in all_rows)
    print(f"  converged: {conv_n}/{len(all_rows)} runs", flush=True)
    if conv_n == 0 and not smoke:
        print(
            "  [WARNING] 全量 converged=0，power iter 未收敛。\n"
            "  可能原因：\n"
            "    1. NCA forward 含 in-place op → autograd.grad 失败（看上方报错）\n"
            "    2. stochastic mask 用 numpy.random 不被 torch seed 固定\n"
            "    3. ρ 真的很小/0（collapse 分支也会这样）\n"
            "  主线先跑 --smoke 1 看单次报错，再 dir(ca) 确认 forward 是否有 in-place。",
            flush=True
        )


if __name__ == '__main__':
    main()
