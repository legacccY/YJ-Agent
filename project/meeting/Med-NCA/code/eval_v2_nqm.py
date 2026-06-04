"""V2 + R5 验收：Med-NCA 内建质量控制 (NQM) 复现脚本
===========================================================
功能：
  1. 复用 R1 boilerplate 加载 epoch_300 ckpt + test split (78 volumes)
  2. 对每个 test volume 做 10x 随机推理 → 计算 NQM 不确定度 + ensemble Dice
  3. V2：统计 NQM 高分命中 Dice<0.8 失败 case 的检出率，核对论文声明 94.6%
  4. R5：NQM vs (1-Dice) 的 Spearman ρ + p 值（纯 numpy 实现，避免 OMP Error #15）
  5. 落盘：r1_nqm_per_volume.csv + v2_r5_summary.json

NQM 口径（官方 labelVariance 方法，Agent.py L279）：
  - 10× sigmoid 预测 → 逐像素 std → NQM = sum(std_map) / sum(mean_map)
  - 分母 mean_map = sigmoid 均值（全图/volume-level 聚合，与官方一致）
  - 此口径在 json calibration_note 中注明

禁止在 GPU 上直接执行本脚本（单卡串行纪律），仅做静态语法检查。
主线执行命令（进入 M3D-NCA-official 目录后）：
  cd D:\\YJ-Agent\\project\\meeting\\Med-NCA\\M3D-NCA-official
  python ..\\code\\eval_v2_nqm.py

seed=42，device=cuda:0（若无 CUDA 则 cpu）。
"""

import os
import sys
import json
import csv
import math
import subprocess
import numpy as np
import torch

# ── 种子 ──────────────────────────────────────────────────────────────────────
SEED = 42
np.random.seed(SEED)
torch.manual_seed(SEED)

# ── 路径 ──────────────────────────────────────────────────────────────────────
ROOT = r"D:\YJ-Agent\project\meeting\Med-NCA"
OFFICIAL = os.path.join(ROOT, "M3D-NCA-official")
sys.path.insert(0, OFFICIAL)
os.chdir(OFFICIAL)  # 官方代码依赖相对路径导入

from src.datasets.Nii_Gz_Dataset_3D import Dataset_NiiGz_3D
sys.path.insert(0, os.path.join(ROOT, "code"))
from src.models.Model_BackboneNCA import BackboneNCA
from src.utils.Experiment import Experiment
from src.agents.Agent_Med_NCA import Agent_Med_NCA
from src.losses.LossFunctions import DiceLoss

# ── 设备 ──────────────────────────────────────────────────────────────────────
DEVICE_STR = "cuda:0" if torch.cuda.is_available() else "cpu"
device = torch.device(DEVICE_STR)

# ── Git commit ─────────────────────────────────────────────────────────────────
def git_commit():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=r"D:\YJ-Agent", stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return "unknown"

COMMIT = git_commit()

# ── 模型配置（与 eval_r1.py 完全一致）─────────────────────────────────────────
config = [{
    'img_path':   os.path.join(ROOT, "data", "Task04_Hippocampus", "imagesTr"),
    'label_path': os.path.join(ROOT, "data", "Task04_Hippocampus", "labelsTr"),
    'model_path': os.path.join(ROOT, "checkpoints", "r1_hippocampus_official"),
    'device': DEVICE_STR,
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
ca1 = BackboneNCA(config[0]['channel_n'], config[0]['cell_fire_rate'], device,
                  hidden_size=config[0]['hidden_size'],
                  input_channels=config[0]['input_channels']).to(device)
ca2 = BackboneNCA(config[0]['channel_n'], config[0]['cell_fire_rate'], device,
                  hidden_size=config[0]['hidden_size'],
                  input_channels=config[0]['input_channels']).to(device)
ca = [ca1, ca2]
agent = Agent_Med_NCA(ca)
exp = Experiment(config, dataset, ca, agent)  # 自动 reload epoch_300 ckpt + data_split.dt
dataset.set_experiment(exp)
exp.set_model_state('train')

epochs_trained = exp.currentStep
epochs_target = exp.get_max_steps()
n_params = sum(p.numel() for m in ca for p in m.parameters())
print(f"[V2-NQM] ckpt loaded: epochs={epochs_trained}/{epochs_target} "
      f"params={n_params} device={DEVICE_STR} commit={COMMIT}", flush=True)

# ── 纯 numpy Spearman（避免 scipy OMP Error #15）─────────────────────────────
def spearman_numpy(x, y):
    """计算 Spearman ρ 及近似 p 值（t 分布近似，df=n-2）。
    返回 (rho, p_value)。
    p 值使用 t 近似：t = rho * sqrt((n-2)/(1-rho^2))，两尾。
    """
    n = len(x)
    assert n == len(y) and n > 2, "需至少 3 个样本"

    def _rank(arr):
        """平均秩（处理 ties）"""
        order = np.argsort(arr)
        ranks = np.empty_like(order, dtype=float)
        ranks[order] = np.arange(1, n + 1, dtype=float)
        # 处理 ties：相同值取平均秩
        i = 0
        while i < n:
            j = i
            while j < n - 1 and arr[order[j]] == arr[order[j + 1]]:
                j += 1
            if j > i:
                mean_rank = (i + j + 2) / 2.0  # 1-indexed
                ranks[order[i:j + 1]] = mean_rank
            i = j + 1
        return ranks

    rx = _rank(np.asarray(x, dtype=float))
    ry = _rank(np.asarray(y, dtype=float))

    # Pearson on ranks = Spearman
    rx_c = rx - rx.mean()
    ry_c = ry - ry.mean()
    denom = np.sqrt((rx_c ** 2).sum() * (ry_c ** 2).sum())
    rho = (rx_c * ry_c).sum() / denom if denom > 0 else 0.0

    # t 近似 p 值（两尾）
    if abs(rho) >= 1.0:
        p_value = 0.0
    else:
        t_stat = rho * math.sqrt((n - 2) / (1.0 - rho ** 2))
        # 使用正态近似（n>=30 时足够准，n<30 时略保守；标注在 json）
        # 用 |t| → z 近似两尾 p（避免引入 scipy）
        # Abramowitz & Stegun 正态 CDF 近似
        z = abs(t_stat) / math.sqrt(1 + t_stat ** 2 / (n - 2))  # 标准化
        # 改用更直接的方式：erf 近似（Python 标准库 math.erf）
        # P(Z > z) ≈ 0.5 * erfc(z / sqrt(2))
        p_one_tail = 0.5 * math.erfc(abs(t_stat) / math.sqrt(2 * (n - 2) / (n - 2)))
        # 更精确的近似：直接用 t 分布的正态近似
        # 对于 n≥10，t_stat/sqrt(n-2) 近似 N(0,1/(n-2)) 不对
        # 改用：标准正态近似 p（t 大时成立，df=n-2）
        # z_approx = t_stat * (1 - 1/(4*(n-2))) / sqrt(1 + t_stat^2/(2*(n-2)))  # Cornish-Fisher
        # 最简单可靠：直接用 math.erf
        val = abs(t_stat) / math.sqrt(2)
        p_one_tail = 0.5 * math.erfc(val)  # 正态近似（df→∞）
        p_value = 2.0 * p_one_tail

    return float(rho), float(p_value)


# ── NQM 逐 volume 推理主循环 ──────────────────────────────────────────────────
N_ENSEMBLE = 10  # 论文声明的随机推理次数
DICE_FAIL_THRESH = 0.8  # V2 失败 case 定义：Dice < 0.8
dice_loss_fn = DiceLoss(useSigmoid=True)

print(f"[V2-NQM] 开始逐 volume 10x 推理 (N_ENSEMBLE={N_ENSEMBLE}) ...", flush=True)

exp.set_model_state('test')
test_dataset = exp.dataset
dataloader = torch.utils.data.DataLoader(test_dataset, batch_size=1)

# 按 patient 聚合 2D slices → 3D volume（复用 Agent.test() 逻辑）
patient_slices = {}   # pid → {'preds': list[tensor], 'labels': list[tensor]}
                      # 每个元素 shape: (1, H, W, 1)

with torch.no_grad():
    for i, data in enumerate(dataloader):
        data = agent.prepare_data(data, eval=True)
        data_id, inputs, _ = data

        # 解析 patient id（与 Agent.py test() 保持一致）
        if isinstance(data_id, str):
            _, pid, sl = test_dataset.__getname__(data_id).split('_')
        else:
            text = data_id[0].split('_')
            if len(text) == 3:
                _, pid, sl = text
            else:
                pid = data_id[0]
                sl = None

        # ── 10× 随机推理（每次 cell_fire_rate=0.5 造成随机 dropout-like 差异）
        ensemble_preds = []
        for _ in range(N_ENSEMBLE):
            out, tgt = agent.get_outputs(data, full_img=True, tag="nqm")
            # out: (1, H, W, 1)，sigmoid 后即概率图
            ensemble_preds.append(torch.sigmoid(out).detach().cpu())

        # stack → (10, 1, H, W, 1)
        stack = torch.stack(ensemble_preds, dim=0)  # shape: (10, 1, H, W, 1)

        # ensemble mean 预测（用于 Dice 计算）：(1, H, W, 1)
        mean_pred = stack.mean(dim=0)  # sigmoid 空间的均值

        # 收集到 patient 字典
        if pid not in patient_slices:
            patient_slices[pid] = {
                'stack_slices': [],   # list of (10, 1, H, W, 1) per slice
                'label_slices': [],   # list of (1, H, W, 1) per slice
                'mean_slices':  [],   # list of (1, H, W, 1) per slice
            }
        patient_slices[pid]['stack_slices'].append(stack)
        patient_slices[pid]['label_slices'].append(tgt.detach().cpu())
        patient_slices[pid]['mean_slices'].append(mean_pred)

        if (i + 1) % 50 == 0:
            print(f"  处理 slice {i+1}...", flush=True)

exp.set_model_state('train')

# ── 聚合 volume-level NQM + Dice ──────────────────────────────────────────────
results = []  # list of dict: {pid, dice, nqm}

for pid, data_dict in patient_slices.items():
    # 拼接所有 slice → volume
    # stack_vol: (10, n_slices, H, W, 1) — 先把每个 slice 的 batch 维度去掉
    # 每个 stack_slice: (10, 1, H, W, 1) → squeeze batch → (10, H, W, 1)
    ensemble_vol = torch.cat(
        [s.squeeze(1) for s in data_dict['stack_slices']], dim=1
    )  # (10, total_slices, H, W, 1)

    mean_vol = torch.cat(
        [m.squeeze(0) for m in data_dict['mean_slices']], dim=0
    )  # (total_slices, H, W, 1)

    label_vol = torch.cat(
        [l.squeeze(0) for l in data_dict['label_slices']], dim=0
    )  # (total_slices, H, W, 1)

    # ── NQM 口径（官方 labelVariance，Agent.py L238-279）
    # ensemble_vol: (10, slices, H, W, 1) → numpy
    ens_np = ensemble_vol.numpy()  # (10, S, H, W, 1)
    mean_np = ens_np.mean(axis=0)  # (S, H, W, 1)

    # 逐像素 std（沿 ensemble axis=0）
    std_np = ens_np.std(axis=0)    # (S, H, W, 1)

    # NQM = sum(std) / sum(mean)  【官方公式，分母避免 /0 加 eps】
    eps = 1e-8
    nqm = float(np.sum(std_np) / (np.sum(mean_np) + eps))

    # ── Dice（ensemble mean 预测 vs GT，Dice = 1 - DiceLoss）
    # mean_vol: (slices, H, W, 1)，label_vol: (slices, H, W, 1)
    # DiceLoss 期望 (N, ...) 且 useSigmoid=True 但此时 mean_vol 已是 sigmoid 后
    # → 用 useSigmoid=False 版本（直接过阈值 0.5 Dice）或手算
    # 手算 Dice 与官方 test() 保持一致（1 - DiceLoss(useSigmoid=True, 输入 logit)）
    # 但 mean_vol 是 sigmoid 均值（非 logit），不能再过 sigmoid；
    # 改为手算 hard Dice（threshold 0.5）：
    pred_hard = (mean_vol.numpy() > 0.5).astype(float)
    gt_hard = label_vol.numpy()

    # 只计算有前景的 mask 通道（与官方 test() 一致：跳过全 0 label）
    if gt_hard.sum() == 0:
        print(f"  [SKIP] pid={pid} 无前景，跳过", flush=True)
        continue

    intersection = (pred_hard * gt_hard).sum()
    dice = float(2.0 * intersection / (pred_hard.sum() + gt_hard.sum() + eps))

    results.append({'pid': pid, 'dice': dice, 'nqm': nqm})
    print(f"  pid={pid:>10s}  dice={dice:.4f}  nqm={nqm:.6f}", flush=True)

print(f"\n[V2-NQM] 共处理 {len(results)} 个 volumes", flush=True)

# ── 落盘 CSV ──────────────────────────────────────────────────────────────────
RESULTS_DIR = os.path.join(ROOT, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

csv_path = os.path.join(RESULTS_DIR, "r1_nqm_per_volume.csv")
with open(csv_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["pid", "dice", "nqm", "seed", "git_commit"])
    for r in results:
        writer.writerow([r['pid'], round(r['dice'], 6), round(r['nqm'], 8), SEED, COMMIT])
print(f"[V2-NQM] CSV 已写入：{csv_path}", flush=True)

# ── V2 检出率分析 ──────────────────────────────────────────────────────────────
dices = np.array([r['dice'] for r in results])
nqms = np.array([r['nqm'] for r in results])
n_total = len(results)

# 失败 case：Dice < 0.8
fail_mask = dices < DICE_FAIL_THRESH
n_fail = int(fail_mask.sum())
n_pass = n_total - n_fail

print(f"\n[V2] 总 volumes={n_total}, 失败(Dice<0.8)={n_fail}, 通过={n_pass}", flush=True)

# 用 NQM 阈值检出：按 NQM 从高到低排，取前 n_fail 个，看命中几个失败 case
nqm_rank_idx = np.argsort(nqms)[::-1]  # 降序：NQM 最高在前
top_k_indices = nqm_rank_idx[:n_fail]  # 取前 n_fail 个高 NQM
top_k_fail_hit = fail_mask[top_k_indices].sum()
detection_rate_topk = float(top_k_fail_hit) / n_fail if n_fail > 0 else float('nan')

print(f"[V2] 检出率（top-{n_fail} NQM 命中 {top_k_fail_hit}/{n_fail} 失败 case）= "
      f"{detection_rate_topk:.1%}", flush=True)
print(f"[V2] 论文声明检出率 = 94.6%（hippocampus）", flush=True)

# 额外报告：多个 NQM 分位数阈值的检出率
thresholds_pct = [50, 60, 70, 75, 80, 90, 95]  # 取前 X% 高 NQM 的 volumes
detection_by_pct = {}
for pct in thresholds_pct:
    k = max(1, int(np.ceil(n_total * pct / 100)))
    top_idx = nqm_rank_idx[:k]
    hits = fail_mask[top_idx].sum()
    dr = float(hits) / n_fail if n_fail > 0 else float('nan')
    detection_by_pct[f"top{pct}pct_k{k}"] = {
        "k": k, "hits": int(hits), "n_fail": n_fail,
        "detection_rate": round(dr, 4)
    }
    print(f"  top-{pct}% (k={k}): {hits}/{n_fail} 失败命中 → DR={dr:.1%}", flush=True)

# ── R5：NQM vs (1-Dice) Spearman ρ ───────────────────────────────────────────
errors = 1.0 - dices  # 误差 = 1 - Dice（越高越差）
rho, p_val = spearman_numpy(nqms, errors)
print(f"\n[R5] Spearman ρ(NQM, 1-Dice) = {rho:.4f}, p ≈ {p_val:.4e} (n={n_total})", flush=True)

# ── 落盘 JSON ─────────────────────────────────────────────────────────────────
summary = {
    "task": "V2_NQM_detection + R5_correlation",
    "n_volumes": n_total,
    "n_fail_dice_lt_0.8": n_fail,
    "n_pass_dice_ge_0.8": n_pass,
    "dice_stats": {
        "mean": round(float(dices.mean()), 4),
        "std":  round(float(dices.std()), 4),
        "min":  round(float(dices.min()), 4),
        "max":  round(float(dices.max()), 4),
    },
    "nqm_stats": {
        "mean": round(float(nqms.mean()), 6),
        "std":  round(float(nqms.std()), 6),
        "min":  round(float(nqms.min()), 6),
        "max":  round(float(nqms.max()), 6),
    },
    "V2_detection": {
        "method": f"按 NQM 降序，取 top-{n_fail}（= n_fail）命中 Dice<0.8 case 数",
        "top_k": n_fail,
        "hits": int(top_k_fail_hit),
        "detection_rate": round(detection_rate_topk, 4),
        "paper_anchor_pct": 94.6,
        "detection_by_topN_pct": detection_by_pct,
    },
    "R5_spearman": {
        "rho": round(rho, 4),
        "p_value_approx": round(p_val, 6),
        "n": n_total,
        "p_note": "正态近似（t → z，df=n-2；n≥30 误差<1%；若 n<30 略保守），无 scipy 依赖",
    },
    "calibration_note": (
        "NQM 口径来自官方 Agent.py labelVariance()：10x sigmoid 预测→逐像素 std→"
        "NQM = sum(std_map) / sum(mean_map)。Dice 用 hard threshold 0.5 on ensemble mean。"
        "10x 推理随机性来自 cell_fire_rate=0.5（stochastic mask），与论文一致。"
        "本脚本实现直接在每个 slice 做 10x 推理，最终 slice 拼接成 volume 再聚合。"
    ),
    "seed": SEED,
    "git_commit": COMMIT,
    "device": DEVICE_STR,
    "epochs_trained": epochs_trained,
    "n_ensemble": N_ENSEMBLE,
    "dice_fail_threshold": DICE_FAIL_THRESH,
}

json_path = os.path.join(RESULTS_DIR, "v2_r5_summary.json")
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=2, ensure_ascii=False)
print(f"[V2-NQM] JSON 已写入：{json_path}", flush=True)

print("\n" + "=" * 60, flush=True)
print(f"V2 检出率 = {detection_rate_topk:.1%}  (论文: 94.6%)", flush=True)
print(f"R5 Spearman ρ = {rho:.4f},  p ≈ {p_val:.4e}", flush=True)
print("=" * 60, flush=True)
