"""V1 鲁棒性退化曲线评估脚本
对 test split（78 volumes）施加 3 类扰动，每类多个强度档，逐档算 per-image Dice，
输出退化曲线数据。

禁止在 GPU 上直接执行该脚本（单卡串行纪律），主线负责调用。
运行命令（在 D:/YJ-Agent/project/meeting/Med-NCA/M3D-NCA-official 目录下）：
    cd D:/YJ-Agent/project/meeting/Med-NCA/M3D-NCA-official
    python ../code/eval_v1_robustness.py

或从任意目录：
    python D:/YJ-Agent/project/meeting/Med-NCA/code/eval_v1_robustness.py

扰动类型与档位：
  1. scale（缩放）：factor ∈ {0.8, 0.9, 1.0(baseline), 1.1, 1.2}
     - img 和 GT 同步缩放到原始尺寸（img 双线性，GT 最近邻）
     - 缩小时先缩再补零填回原尺寸；放大时先放大再中心裁剪

  2. translate（平移）：shift_px ∈ {0(baseline), ±2, ±5, ±10}（仅正方向成档：0, 2, 5, 10 px）
     - img 和 GT 同步向右下平移（GT 同步），空出区域补 0
     - 注：负方向等价于向左上，物理对称，只跑正向

  3. MRI-artifact（伪影）：使用 torchio，强度递增
     - RandomNoise：std ∈ {0.0(baseline), 0.05, 0.1, 0.2, 0.4}
     - RandomBiasField：coefficients ∈ {0.0(baseline), 0.1, 0.3, 0.5, 0.7}
     - RandomGhosting：intensity ∈ {0.0(baseline), 0.25, 0.5, 0.75, 1.0}
     - 伪影类只施于 img（像素值扰动），GT 不动

对齐保证：
  - scale/translate：用 scipy.ndimage 对 img 和 GT 分别变换，img 用 order=1（双线性），
    GT 用 order=0（最近邻），变换后形状保持和原始 inputs tensor 一致
  - artifact：torchio 只作用于 img 通道，GT 完全不变

输出：
  - ROOT/results/r1_v1_robustness.csv
  - ROOT/results/v1_robustness_summary.json
"""

import os
import sys
import json
import csv
import subprocess
import math

import numpy as np
import torch
import torch.nn.functional as F
import scipy.ndimage
import torchio as tio

# ─────────────────────────────────────────────────────────────────────────────
# 路径 & 环境设置（复用 eval_r1.py 第 21-67 行 boilerplate）
# ─────────────────────────────────────────────────────────────────────────────

SEED = 42
np.random.seed(SEED)
torch.manual_seed(SEED)

ROOT = r"D:\YJ-Agent\project\meeting\Med-NCA"
OFFICIAL = os.path.join(ROOT, "M3D-NCA-official")
sys.path.insert(0, OFFICIAL)
os.chdir(OFFICIAL)

from src.datasets.Nii_Gz_Dataset_3D import Dataset_NiiGz_3D
sys.path.insert(0, os.path.join(ROOT, "code"))
from src.models.Model_BackboneNCA import BackboneNCA
from src.utils.Experiment import Experiment
from src.agents.Agent_Med_NCA import Agent_Med_NCA
from src.losses.LossFunctions import DiceLoss


def git_commit():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=r"D:\YJ-Agent", stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "unknown"


DEVICE = "cuda:0" if torch.cuda.is_available() else "cpu"

config = [{
    'img_path':   os.path.join(ROOT, "data", "Task04_Hippocampus", "imagesTr"),
    'label_path': os.path.join(ROOT, "data", "Task04_Hippocampus", "labelsTr"),
    'model_path': os.path.join(ROOT, "checkpoints", "r1_hippocampus_official"),
    'device': DEVICE,
    'unlock_CPU': True,
    'lr': 16e-4, 'lr_gamma': 0.9999, 'betas': (0.5, 0.5),
    'save_interval': 50, 'evaluate_interval': 25,
    'n_epoch': 1500, 'batch_size': 40,
    'channel_n': 32, 'inference_steps': 16, 'cell_fire_rate': 0.5,
    'input_channels': 1, 'output_channels': 1, 'hidden_size': 128,
    'train_model': 1,
    'input_size': [(16, 16), (64, 64)],
    'rescale': True,
    'data_split': [0.7, 0, 0.3],
}]

dataset = Dataset_NiiGz_3D(slice=2)
device = torch.device(config[0]['device'])
ca1 = BackboneNCA(
    config[0]['channel_n'], config[0]['cell_fire_rate'], device,
    hidden_size=config[0]['hidden_size'],
    input_channels=config[0]['input_channels']).to(device)
ca2 = BackboneNCA(
    config[0]['channel_n'], config[0]['cell_fire_rate'], device,
    hidden_size=config[0]['hidden_size'],
    input_channels=config[0]['input_channels']).to(device)
ca = [ca1, ca2]
agent = Agent_Med_NCA(ca)
exp = Experiment(config, dataset, ca, agent)   # reload epoch_300 ckpt + data_split.dt
dataset.set_experiment(exp)
exp.set_model_state('train')

commit = git_commit()
n_params = sum(p.numel() for m in ca for p in m.parameters())
print(f"[V1-robustness] device={DEVICE} params={n_params} commit={commit}", flush=True)

# ─────────────────────────────────────────────────────────────────────────────
# 扰动函数定义
# ─────────────────────────────────────────────────────────────────────────────

def apply_scale(img_np: np.ndarray, gt_np: np.ndarray, factor: float):
    """缩放扰动：img 和 GT 同步缩放，然后裁剪/补零回原始尺寸。

    参数
    ----
    img_np : shape (H, W)，已归一化浮点图
    gt_np  : shape (H, W)，二值 GT
    factor : 缩放因子，<1 缩小，>1 放大

    返回
    ----
    img_out, gt_out : shape 与输入相同 (H, W)，对齐保证
    """
    if factor == 1.0:
        return img_np.copy(), gt_np.copy()

    H, W = img_np.shape
    # scipy.ndimage.zoom 对每个像素独立缩放（几何中心对齐）
    zoom = (factor, factor)
    img_zoomed = scipy.ndimage.zoom(img_np, zoom, order=1)   # 双线性
    gt_zoomed  = scipy.ndimage.zoom(gt_np,  zoom, order=0)   # 最近邻

    img_out = np.zeros((H, W), dtype=img_np.dtype)
    gt_out  = np.zeros((H, W), dtype=gt_np.dtype)

    # 缩小（factor < 1）：zoomed 比原始小，居中粘贴
    # 放大（factor > 1）：zoomed 比原始大，居中裁剪
    h_z, w_z = img_zoomed.shape

    # 源区域（从 zoomed 里取）
    src_y1 = max(0, (h_z - H) // 2)
    src_x1 = max(0, (w_z - W) // 2)
    src_y2 = src_y1 + min(h_z, H)
    src_x2 = src_x1 + min(w_z, W)

    # 目标区域（粘贴到 out 里）
    dst_y1 = max(0, (H - h_z) // 2)
    dst_x1 = max(0, (W - w_z) // 2)
    dst_y2 = dst_y1 + (src_y2 - src_y1)
    dst_x2 = dst_x1 + (src_x2 - src_x1)

    img_out[dst_y1:dst_y2, dst_x1:dst_x2] = img_zoomed[src_y1:src_y2, src_x1:src_x2]
    gt_out[dst_y1:dst_y2,  dst_x1:dst_x2] = gt_zoomed[src_y1:src_y2,  src_x1:src_x2]

    return img_out, gt_out


def apply_translate(img_np: np.ndarray, gt_np: np.ndarray, shift_px: int):
    """平移扰动：img 和 GT 同步向右下方向平移 shift_px 像素，空出区域补 0。

    参数
    ----
    img_np  : shape (H, W)
    gt_np   : shape (H, W)
    shift_px: 平移像素数（>=0 右下，<0 左上）

    返回
    ----
    img_out, gt_out : shape 与输入相同，对齐保证（GT 同步平移）
    """
    if shift_px == 0:
        return img_np.copy(), gt_np.copy()

    # scipy.ndimage.shift：正值向下/右，负值向上/左；order=0 GT 不插值
    img_out = scipy.ndimage.shift(img_np, shift=(shift_px, shift_px), order=1, mode='constant', cval=0.0)
    gt_out  = scipy.ndimage.shift(gt_np,  shift=(shift_px, shift_px), order=0, mode='constant', cval=0.0)
    return img_out.astype(img_np.dtype), gt_out.astype(gt_np.dtype)


def apply_noise(img_np: np.ndarray, std: float, rng: np.random.Generator):
    """RandomNoise 伪影：对 img 加高斯噪声（GT 不动）。"""
    if std == 0.0:
        return img_np.copy()
    noise = rng.normal(0.0, std, size=img_np.shape).astype(img_np.dtype)
    img_out = np.clip(img_np + noise, 0.0, 1.0)
    return img_out


def apply_bias_field(img_np: np.ndarray, coefficients: float, rng: np.random.Generator):
    """RandomBiasField 伪影：torchio 施加随机偏置场（GT 不动）。

    torchio RandomBiasField 接受 tio.Subject，img 格式为 (C, H, W) 的 tensor。
    """
    if coefficients == 0.0:
        return img_np.copy()

    seed_val = int(rng.integers(0, 2**31))
    # torchio 要求输入为 (C, H, W) 或 (C, H, W, D) 的 ScalarImage
    img_t = torch.from_numpy(img_np[None, :, :]).float()   # (1, H, W)
    subject = tio.Subject(img=tio.ScalarImage(tensor=img_t.unsqueeze(-1)))  # (1,H,W,1)
    transform = tio.RandomBiasField(coefficients=coefficients, order=3)
    torch.manual_seed(seed_val)
    augmented = transform(subject)
    out = augmented['img'].data.squeeze(-1).squeeze(0).numpy()  # (H, W)
    # 偏置场 = exp(多项式)，高 coef 可能溢出 inf/NaN → 先兜底再归一化
    out = np.nan_to_num(out, nan=0.0, posinf=0.0, neginf=0.0)
    lo, hi = out.min(), out.max()
    if hi > lo:
        out = (out - lo) / (hi - lo)
    return out.astype(img_np.dtype)


def apply_ghosting(img_np: np.ndarray, intensity: float, rng: np.random.Generator):
    """RandomGhosting 伪影：torchio 施加鬼影（GT 不动）。"""
    if intensity == 0.0:
        return img_np.copy()

    seed_val = int(rng.integers(0, 2**31))
    img_t = torch.from_numpy(img_np[None, :, :]).float()
    subject = tio.Subject(img=tio.ScalarImage(tensor=img_t.unsqueeze(-1)))
    transform = tio.RandomGhosting(intensity=intensity, num_ghosts=(2, 10))
    torch.manual_seed(seed_val)
    augmented = transform(subject)
    out = augmented['img'].data.squeeze(-1).squeeze(0).numpy()
    out = np.nan_to_num(out, nan=0.0, posinf=0.0, neginf=0.0)
    lo, hi = out.min(), out.max()
    if hi > lo:
        out = (out - lo) / (hi - lo)
    return out.astype(img_np.dtype)


# ─────────────────────────────────────────────────────────────────────────────
# 推理 + Dice 计算（单 slice，避免走 test() 产生 tensorboard 副作用）
# ─────────────────────────────────────────────────────────────────────────────

dice_loss_fn = DiceLoss(useSigmoid=True)


def compute_dice_for_perturbed_inputs(inputs_seed: torch.Tensor,
                                      targets: torch.Tensor) -> float:
    """给定已扰动的 inputs_seed (B,H,W,channel_n) 和 targets (B,H,W,1)，
    跑 full_img 推理，返回 Dice（float）。

    inputs_seed[..., 0] 是图像通道，已被调用者替换为扰动后图像。
    targets 已被调用者替换为（若有空间变换则同步变换过的）GT。
    """
    with torch.no_grad():
        data = ("_perturbed_", inputs_seed, targets)
        outputs, targets_out = agent.get_outputs(data, full_img=True, tag="0")
        # outputs: (B, H, W, 1)   targets_out: (B, H, W, 1)
        # Dice = 1 - DiceLoss（smooth=0）
        dice_val = 1.0 - dice_loss_fn(
            outputs[..., 0], targets_out[..., 0], smooth=0).item()
        if math.isnan(dice_val):
            dice_val = 0.0
    return dice_val


# ─────────────────────────────────────────────────────────────────────────────
# 扰动档位定义
# ─────────────────────────────────────────────────────────────────────────────

PERTURBATIONS = [
    # (perturb_type, level_name, level_value)
    # scale 档位：factor
    ("scale", "0.80", 0.80),
    ("scale", "0.90", 0.90),
    ("scale", "1.00", 1.00),   # baseline
    ("scale", "1.10", 1.10),
    ("scale", "1.20", 1.20),

    # translate 档位：shift_px（正值=右下，0=baseline）
    ("translate", "0px",  0),
    ("translate", "2px",  2),
    ("translate", "5px",  5),
    ("translate", "10px", 10),

    # noise 档位：std
    ("noise", "std0.00", 0.00),   # baseline
    ("noise", "std0.05", 0.05),
    ("noise", "std0.10", 0.10),
    ("noise", "std0.20", 0.20),
    ("noise", "std0.40", 0.40),

    # bias_field 档位：coefficients
    ("bias_field", "coef0.0", 0.0),  # baseline
    ("bias_field", "coef0.1", 0.1),
    ("bias_field", "coef0.3", 0.3),
    ("bias_field", "coef0.5", 0.5),
    ("bias_field", "coef0.7", 0.7),

    # ghosting 档位：intensity
    ("ghosting", "int0.00", 0.00),  # baseline
    ("ghosting", "int0.25", 0.25),
    ("ghosting", "int0.50", 0.50),
    ("ghosting", "int0.75", 0.75),
    ("ghosting", "int1.00", 1.00),
]

# ─────────────────────────────────────────────────────────────────────────────
# 主评估循环
# ─────────────────────────────────────────────────────────────────────────────

results_dir = os.path.join(ROOT, "results")
os.makedirs(results_dir, exist_ok=True)
out_csv  = os.path.join(results_dir, "r1_v1_robustness.csv")
out_json = os.path.join(results_dir, "v1_robustness_summary.json")

# 固定 rng（种子 42），伪影类扰动用
rng = np.random.default_rng(SEED)

# 用于存汇总数据的结构
# { (perturb_type, level_name): [dice_val, ...] }
summary_data: dict = {}

# 先拿到 baseline（无扰动）的 per-patient Dice，作为退化幅度基准
# baseline 从 scale=1.0 / translate=0px / noise=std0.00 / bias_field=coef0.0 / ghosting=int0.00
# 均代表同一个无扰动状态，但我们各自独立跑（确保 GT/img 保持原始值），
# 然后取 scale level=1.00 作为全局 baseline 参考均值

print("\n[V1] 开始扰动评估，共 {} 档位".format(len(PERTURBATIONS)), flush=True)
print("[V1] 注意：每档位需要遍历 test split 全部 slices，耗时较长", flush=True)

all_rows = []  # 用于写 CSV

for perturb_type, level_name, level_value in PERTURBATIONS:
    key = (perturb_type, level_name)
    print(f"\n[V1] >>> perturb={perturb_type}  level={level_name}  value={level_value}", flush=True)

    # 切到 test 模式
    exp.set_model_state('test')
    dataloader = torch.utils.data.DataLoader(dataset, batch_size=1)

    # 按 patient 聚合（2D slice 模式，需要把所有 slice 的 outputs/targets 堆起来再算 3D Dice）
    patient_id_cur  = None
    patient_outputs = None   # (slices, H, W, 1)
    patient_targets = None   # (slices, H, W, 1)

    patient_dices: dict = {}   # pid -> dice

    with torch.no_grad():
        for i, data in enumerate(dataloader):
            # 标准 prepare_data（eval=True：不做 pool/batch_duplication）
            data_prep = agent.prepare_data(data, eval=True)
            data_id, inputs_seed, targets = data_prep
            # inputs_seed : (1, H, W, channel_n)   已经 make_seed 过
            # targets      : (1, H, W, 1)

            # 解析 patient id 和 slice（参考 Agent.py test() 第 339-344 行）
            if isinstance(data_id, str):
                _, pid, slc = dataset.__getname__(data_id).split('_')
            else:
                text = data_id[0].split('_')
                if len(text) == 3:
                    _, pid, slc = text
                else:
                    pid = data_id[0]
                    slc = None

            # ── 提取 img / GT 的 numpy（H, W）──────────────────────────────
            img_np = inputs_seed[0, :, :, 0].detach().cpu().numpy()  # (H, W)
            gt_np  = targets[0, :, :, 0].detach().cpu().numpy()      # (H, W)

            # ── 施加扰动 ─────────────────────────────────────────────────────
            if perturb_type == "scale":
                img_p, gt_p = apply_scale(img_np, gt_np, float(level_value))
            elif perturb_type == "translate":
                img_p, gt_p = apply_translate(img_np, gt_np, int(level_value))
            elif perturb_type == "noise":
                img_p = apply_noise(img_np, float(level_value), rng)
                gt_p  = gt_np.copy()   # 伪影类 GT 不变
            elif perturb_type == "bias_field":
                img_p = apply_bias_field(img_np, float(level_value), rng)
                gt_p  = gt_np.copy()
            elif perturb_type == "ghosting":
                img_p = apply_ghosting(img_np, float(level_value), rng)
                gt_p  = gt_np.copy()
            else:
                raise ValueError(f"未知扰动类型: {perturb_type}")

            # ── 注入前统一兜底：任何扰动产生的 NaN/Inf 都清掉 + clip 回 [0,1]
            #    防止 NaN 喂进 conv 触发 CUDA "illegal instruction"（崩因）
            img_p = np.nan_to_num(img_p, nan=0.0, posinf=1.0, neginf=0.0)
            img_p = np.clip(img_p, 0.0, 1.0).astype(np.float32)

            # ── 把扰动后的 img 写回 seed 的 channel 0 ─────────────────────
            inputs_seed_p = inputs_seed.clone()
            inputs_seed_p[0, :, :, 0] = torch.from_numpy(img_p).float()

            # targets 同步替换（空间类扰动已更新 gt_p，伪影类 gt_p = gt_np.copy()）
            targets_p = targets.clone()
            targets_p[0, :, :, 0] = torch.from_numpy(gt_p).float()

            # 送到 device
            inputs_seed_p = inputs_seed_p.to(device)
            targets_p     = targets_p.to(device)

            # ── 推理 ─────────────────────────────────────────────────────────
            data_perturbed = (data_id, inputs_seed_p, targets_p)
            outputs, targets_out = agent.get_outputs(data_perturbed, full_img=True, tag="0")
            # outputs / targets_out: (1, H, W, 1) on device

            # ── 按 patient 聚合 slices ────────────────────────────────────
            if pid != patient_id_cur and patient_id_cur is not None:
                # 前一个 patient 完成，计算 3D Dice
                if 1 in np.unique(patient_targets[..., 0].detach().cpu().numpy()):
                    dice_3d = 1.0 - dice_loss_fn(
                        patient_outputs[..., 0],
                        patient_targets[..., 0],
                        smooth=0).item()
                    if math.isnan(dice_3d):
                        dice_3d = 0.0
                    patient_dices[patient_id_cur] = dice_3d
                    print(f"  pid={patient_id_cur}  dice={dice_3d:.4f}", flush=True)

                patient_id_cur  = pid
                patient_outputs = outputs.detach().cpu()
                patient_targets = targets_out.detach().cpu()
            else:
                if patient_id_cur is None:
                    patient_id_cur  = pid
                    patient_outputs = outputs.detach().cpu()
                    patient_targets = targets_out.detach().cpu()
                else:
                    patient_outputs = torch.vstack([patient_outputs, outputs.detach().cpu()])
                    patient_targets = torch.vstack([patient_targets, targets_out.detach().cpu()])

        # ── 最后一个 patient ─────────────────────────────────────────────
        if patient_id_cur is not None and patient_outputs is not None:
            if 1 in np.unique(patient_targets[..., 0].detach().cpu().numpy()):
                dice_3d = 1.0 - dice_loss_fn(
                    patient_outputs[..., 0],
                    patient_targets[..., 0],
                    smooth=0).item()
                if math.isnan(dice_3d):
                    dice_3d = 0.0
                patient_dices[patient_id_cur] = dice_3d
                print(f"  pid={patient_id_cur}  dice={dice_3d:.4f}", flush=True)

    # ── 汇总本档位 ───────────────────────────────────────────────────────
    summary_data[key] = list(patient_dices.values())
    dice_vals = list(patient_dices.values())
    mean_dice = float(np.mean(dice_vals)) if dice_vals else 0.0
    print(f"  [level={level_name}] n={len(dice_vals)} mean_dice={mean_dice:.4f}", flush=True)

    # 写 CSV 行
    for pid, d in patient_dices.items():
        all_rows.append({
            "perturb_type": perturb_type,
            "level": level_name,
            "pid": pid,
            "dice": round(d, 6),
            "seed": SEED,
            "commit": commit,
        })

    # 回到 train 模式（避免影响 dataset state）
    exp.set_model_state('train')

# ─────────────────────────────────────────────────────────────────────────────
# 写 CSV
# ─────────────────────────────────────────────────────────────────────────────

with open(out_csv, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["perturb_type", "level", "pid", "dice", "seed", "commit"])
    w.writeheader()
    w.writerows(all_rows)

print(f"\n[V1] CSV 已写出 → {out_csv}  ({len(all_rows)} 行)", flush=True)

# ─────────────────────────────────────────────────────────────────────────────
# 构建汇总 JSON（退化幅度 = mean_dice / baseline_dice - 1）
# ─────────────────────────────────────────────────────────────────────────────

# 各扰动类型的 baseline level name（无扰动档）
BASELINE_LEVEL = {
    "scale":      "1.00",
    "translate":  "0px",
    "noise":      "std0.00",
    "bias_field": "coef0.0",
    "ghosting":   "int0.00",
}

summary_json: dict = {
    "meta": {
        "seed": SEED,
        "commit": commit,
        "device": DEVICE,
        "desc": (
            "V1 鲁棒性退化曲线：对 test split 施加 scale/translate/noise/bias_field/ghosting 扰动，"
            "逐档算 per-patient 3D Dice（slice=2 轴聚合）。"
            "mean_dice_delta = mean_dice - baseline_mean_dice。"
            "正值代表高于 baseline（不太可能），负值代表退化。"
        ),
    },
    "by_type": {},
}

for ptype in ["scale", "translate", "noise", "bias_field", "ghosting"]:
    baseline_key = (ptype, BASELINE_LEVEL[ptype])
    baseline_vals = summary_data.get(baseline_key, [])
    baseline_mean = float(np.mean(baseline_vals)) if baseline_vals else 0.0

    type_summary = {"baseline_level": BASELINE_LEVEL[ptype], "baseline_mean_dice": round(baseline_mean, 4), "levels": {}}

    for (pt, lvl), vals in summary_data.items():
        if pt != ptype:
            continue
        m = float(np.mean(vals)) if vals else 0.0
        s = float(np.std(vals))  if vals else 0.0
        delta = m - baseline_mean
        type_summary["levels"][lvl] = {
            "n": len(vals),
            "mean_dice": round(m, 4),
            "std_dice":  round(s, 4),
            "mean_dice_delta": round(delta, 4),
        }

    summary_json["by_type"][ptype] = type_summary

with open(out_json, "w", encoding="utf-8") as f:
    json.dump(summary_json, f, indent=2, ensure_ascii=False)

print(f"[V1] summary JSON 已写出 → {out_json}", flush=True)
print("[V1] 评估完成。", flush=True)
