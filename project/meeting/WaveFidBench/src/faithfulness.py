"""
faithfulness.py — WaveFidBench 多 XAI × 多指标 忠实度评测（Gate1 非 nan 烟测 → Gate2/3 全表）

服务项目：WaveFidBench (wavefid)，lever：
  - Gate1 地基 Q 块：≥1 (XAI×指标) 非 nan。
  - Gate2 B：解释热图的 wavelet 子带能量分布可计算（量化「解释能量落哪个频带」）。
  - Gate3 全表：≥3 XAI × 4 子带 × ≥3 faithfulness 指标（本脚本产 XAI×指标块 + 子带能量）。

功能：
  加载冻结分类器，对 ≤n 张测试子样本，对每个 XAI 方法产 (N,H,W) 归因热图，
  用同一套 Quantus 指标 + 自实现 insertion 评每个 (XAI×指标)。

  XAI 方法（researcher T5 + captum 官方 API）：
    1. GradCAM         — captum LayerGradCam（仅 CNN，ResNet50 target=layer4[-1].conv3）。
                         ViT-B/16 无合适卷积 target → 跳过并在 csv 标记（不 crash）。
    2. IntegratedGradients — captum IntegratedGradients（CNN + ViT 通用，梯度型不依赖卷积层）。
    3. GradientShap    — captum GradientShap（CNN + ViT 通用，SHAP 系梯度近似）。

  归因归约（统一口径，与现有 Grad-CAM 一致）：
    - GradCAM 原生 (N,H,W)：ReLU + per-sample 归一化到 [0,1]（既有实现）。
    - IG / GradientShap 原生 (N,C,H,W)：sum over channel → clamp(min=0)=ReLU → per-sample /max → [0,1]。
      与 GradCAM 同为「正贡献 + 归一化」口径，故下游 Quantus 调用（abs=False, normalise=True）不变。

  Quantus 指标（每个 XAI 都算）：
    - PixelFlipping（deletion，perturb_baseline='black', return_auc_per_sample=True）
    - ROAD（percentages=range(1,100,2), noise=0.01，自定义 perturb 修多通道 bug）
    - IROF（slic, mean, return_aggregate，自定义 perturb 修多通道 bug）
    - insertion 自实现 <50 行（Quantus 无原生 insertion，researcher T5 核实）

  子带能量分布（Gate2 B）：
    对每个 XAI 的热图做 DWTForward(J=1, wave='db1', mode='symmetric')（同 subband_zero.py），
    算 LL/LH/HL/HH 四子带能量占比，输出到 faithfulness_subband_energy.csv。

  输出：
    - faithfulness_results.csv       每行 = (xai, metric, mean_score, nan_count, ...)
    - faithfulness_subband_energy.csv 每行 = (xai, subband, energy_ratio, ...)
    - faithfulness_state.json

Quantus API 来源：https://github.com/understandingai/Quantus（researcher T5 核实）
captum API：LayerGradCam / IntegratedGradients / GradientShap（captum.readthedocs.io）

用法：
  python src/faithfulness.py \\
      --config configs/gate1_oasis.yaml \\
      --split_csv_dir log/splits \\
      --checkpoint log/checkpoints/resnet50_seed42_best.pt \\
      --n_samples 200
"""

import argparse
import json
import logging
import warnings
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd
import torch
import yaml
from torch.utils.data import DataLoader, Subset
from torchvision import transforms

# captum
from captum.attr import (
    LayerGradCam,
    LayerAttribution,
    IntegratedGradients,
    GradientShap,
)

# pytorch_wavelets（子带能量分布，同 subband_zero.py 口径）
from pytorch_wavelets import DWTForward

# Quantus
import quantus
from quantus.functions.perturb_func import (
    noisy_linear_imputation as _nli_orig,
    baseline_replacement_by_mask as _brm_orig,
)

from train_classifier import build_backbone, MRIDataset

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# =========================================================
# 归因归约：(1,C,H,W) 或 (C,H,W) attribution → (H,W) 热图 [0,1]
# 与 GradCAM 口径一致：sum over channel → ReLU → per-sample /max
# =========================================================

def _reduce_attr_to_heatmap(attr: torch.Tensor) -> np.ndarray:
    """
    attr: (1,C,H,W) 或 (C,H,W) 的原生归因（可含负值，shape 恒 = 输入 (N,3,H,W)）。
    归约：channel 维取绝对值求和 .abs().sum(dim=channel)（researcher 核 captum 官方口径，
         attribution magnitude）→ per-sample 归一化到 [0,1]（max>0 时）。
    非负 + [0,1]，与 GradCAM 热图口径对齐（下游 Quantus abs=False, normalise=True 不变）。
    返回 (H,W) np.float32。
    """
    if attr.dim() == 4:
        attr = attr.squeeze(0)          # (C,H,W)
    heat = attr.abs().sum(dim=0)       # (H,W) abs-sum over channel（researcher 核官方口径）
    max_val = heat.max()
    if max_val > 0:
        heat = heat / max_val
    return heat.detach().cpu().numpy().astype(np.float32)


# =========================================================
# XAI 1: Grad-CAM（captum LayerGradCam，仅 CNN，researcher T5 核实 API）
# =========================================================

def compute_gradcam_batch(
    model: torch.nn.Module,
    x_batch: np.ndarray,       # (N,C,H,W) float32 归一化后
    labels: np.ndarray,        # (N,) int
    target_layer,
    device: torch.device,
) -> np.ndarray:
    """
    返回 a_batch: (N,H,W)，归一化到 [0,1]。
    captum LayerGradCam -> LayerAttribution.interpolate -> squeeze。
    target_layer = model.layer4[-1].conv3（ResNet50 Bottleneck 最后一层，researcher T5）。
    """
    model.eval()
    N, C, H, W = x_batch.shape
    lgc = LayerGradCam(model, target_layer)

    attrs_list = []
    for i in range(N):
        xi = torch.tensor(x_batch[i], dtype=torch.float32, device=device).unsqueeze(0).requires_grad_(True)
        attr = lgc.attribute(xi, target=int(labels[i]))
        # 插值回原图尺寸
        attr_interp = LayerAttribution.interpolate(attr, (H, W), interpolate_mode="bicubic")
        attr_map = attr_interp.squeeze(0).squeeze(0)  # (H,W)
        attr_map = torch.clamp(attr_map, min=0)       # ReLU
        max_val = attr_map.max()
        if max_val > 0:
            attr_map = attr_map / max_val
        attrs_list.append(attr_map.detach().cpu().numpy().astype(np.float32))

    return np.stack(attrs_list, axis=0)  # (N,H,W)


# =========================================================
# XAI 2: Integrated Gradients（captum，CNN + ViT 通用）
# researcher 核官方签名：
#   IntegratedGradients(forward_func, multiply_by_inputs=True)
#     .attribute(inputs, baselines=None, target=, n_steps=50, method='gausslegendre')
#   baselines=None → captum 默认黑图（可接受）；method='gausslegendre'（captum 默认积分近似）。
#   可选 'black' = 归一化空间纯黑像素 (0-mean)/std（显式构造）。
#   Source: captum.attr.IntegratedGradients（researcher 核官方签名）
# =========================================================

def compute_ig_batch(
    model: torch.nn.Module,
    x_batch: np.ndarray,       # (N,C,H,W)
    labels: np.ndarray,        # (N,)
    device: torch.device,
    n_steps: int = 50,
    baseline_tensor: Optional[torch.Tensor] = None,  # None → captum 默认黑图；(1,C,H,W)=显式 black
) -> np.ndarray:
    """返回 (N,H,W) [0,1]。per-sample IG，归约用 _reduce_attr_to_heatmap。"""
    model.eval()
    N = x_batch.shape[0]
    ig = IntegratedGradients(model)  # multiply_by_inputs=True 默认

    attrs_list = []
    for i in range(N):
        xi = torch.tensor(x_batch[i], dtype=torch.float32, device=device).unsqueeze(0)
        # baseline_tensor=None → 传 None（captum 默认黑图）；否则传显式 black 张量
        attr = ig.attribute(
            xi, target=int(labels[i]), baselines=baseline_tensor,
            n_steps=n_steps, method="gausslegendre",
        )
        attrs_list.append(_reduce_attr_to_heatmap(attr))

    return np.stack(attrs_list, axis=0)  # (N,H,W)


# =========================================================
# XAI 3: GradientShap（captum，CNN + ViT 通用，SHAP 系梯度近似）
# researcher 核官方签名：
#   GradientShap(forward_func).attribute(inputs, baselines, n_samples=5, stdevs=0.0, target=)
#   ⚠️ baseline 必须是「分布」（第一维=样本数 >1，随机采样几张训练图当 baseline），
#     不是单张黑图。captum 沿 input→baseline 路径随机采样求 SHAP 近似。
#   Source: captum.attr.GradientShap（researcher 核官方签名）
# =========================================================

def compute_gradshap_batch(
    model: torch.nn.Module,
    x_batch: np.ndarray,          # (N,C,H,W)
    labels: np.ndarray,           # (N,)
    baseline_pool: torch.Tensor,  # (B,C,H,W) 随机训练图分布（B>1），on device
    device: torch.device,
    n_samples: int = 5,
    stdevs: float = 0.0,
) -> np.ndarray:
    """返回 (N,H,W) [0,1]。per-sample GradientShap，baselines=随机训练图分布（共享）。"""
    model.eval()
    N = x_batch.shape[0]
    gs = GradientShap(model)

    attrs_list = []
    for i in range(N):
        xi = torch.tensor(x_batch[i], dtype=torch.float32, device=device).unsqueeze(0)
        attr = gs.attribute(
            xi, target=int(labels[i]), baselines=baseline_pool,  # 分布（B>1 随机训练图）
            n_samples=n_samples, stdevs=stdevs,
        )
        attrs_list.append(_reduce_attr_to_heatmap(attr))

    return np.stack(attrs_list, axis=0)  # (N,H,W)


# =========================================================
# Insertion 自实现（<50 行，Quantus 无原生实现，researcher T5 核实）
# insertion game：从全 baseline 图（全黑）开始，按归因从高到低逐步填入像素
# 与 PixelFlipping（deletion = 从原图逐步移除）方向相反
# =========================================================

def insertion_auc(
    model: torch.nn.Module,
    x_batch: np.ndarray,      # (N, C, H, W) float32 归一化后
    a_batch: np.ndarray,      # (N, H, W) 归因图
    labels: np.ndarray,       # (N,) int
    device: torch.device,
    n_steps: int = 50,
) -> List[float]:
    """
    insertion game 自实现，Quantus 无原生 insertion 实现（researcher T5 核实）。
    从全 baseline（全黑）渐加高归因像素，返回每样本 AUC（prob 曲线下面积）。
    """
    N, C, H, W = x_batch.shape
    auc_list = []

    model.eval()
    with torch.no_grad():
        for i in range(N):
            x = x_batch[i]          # (C, H, W)
            a = a_batch[i]          # (H, W) 归因图，值越高越重要
            label = int(labels[i])

            baseline = np.zeros_like(x)  # 全黑 baseline
            flat_idx = np.argsort(a.flatten())[::-1]  # 降序（高归因先填）
            step_size = max(1, (H * W) // n_steps)

            probs = []
            current = baseline.copy()
            for step in range(n_steps):
                start = step * step_size
                end = min((step + 1) * step_size, H * W)
                pix_to_reveal = flat_idx[start:end]
                rows = pix_to_reveal // W
                cols = pix_to_reveal % W
                current[:, rows, cols] = x[:, rows, cols]

                t = torch.tensor(current, dtype=torch.float32).unsqueeze(0).to(device)
                logits = model(t)
                prob = torch.softmax(logits, dim=1)[0, label].item()
                probs.append(prob)

            # AUC = trapezoid 积分（均匀 x 轴）
            auc = float(np.trapz(probs) / (len(probs) - 1)) if len(probs) > 1 else probs[0]
            auc_list.append(auc)

    return auc_list


# =========================================================
# 解释热图的 wavelet 子带能量分布（Gate2 B）
# 对 (N,H,W) 热图做 DWT（同 subband_zero.py：J=1, db1, symmetric），
# 算 LL/LH/HL/HH 能量占比（能量=平方和），返回四子带平均占比。
# Yh[0] dim=2: 0=LH / 1=HL / 2=HH（pytorch_wavelets finest-first，researcher T4 核实）
# =========================================================

def compute_subband_energy(
    a_batch: np.ndarray,       # (N,H,W) 热图 [0,1]
    device: torch.device,
    wave: str = "db1",
    mode: str = "symmetric",
) -> dict:
    """
    返回 {'LL':ratio, 'LH':ratio, 'HL':ratio, 'HH':ratio}（N 个样本的平均能量占比）。
    能量 = 子带系数平方和；ratio = 子带能量 / 四子带总能量。
    """
    dwt = DWTForward(J=1, wave=wave, mode=mode).to(device)
    dwt.eval()
    x = torch.tensor(a_batch, dtype=torch.float32, device=device).unsqueeze(1)  # (N,1,H,W)
    with torch.no_grad():
        Yl, Yh = dwt(x)  # Yl:(N,1,H',W')  Yh[0]:(N,1,3,H',W')
        ll = (Yl ** 2).sum(dim=(1, 2, 3))              # (N,)
        lh = (Yh[0][:, :, 0, :, :] ** 2).sum(dim=(1, 2, 3))
        hl = (Yh[0][:, :, 1, :, :] ** 2).sum(dim=(1, 2, 3))
        hh = (Yh[0][:, :, 2, :, :] ** 2).sum(dim=(1, 2, 3))
        total = ll + lh + hl + hh + 1e-12
        ratios = {
            "LL": float((ll / total).mean().item()),
            "LH": float((lh / total).mean().item()),
            "HL": float((hl / total).mean().item()),
            "HH": float((hh / total).mean().item()),
        }
    return ratios


# =========================================================
# Quantus 图像模式自定义 perturb 函数（修 0.6.0 多通道 bug）
# =========================================================

def _road_perturb_3ch(arr: np.ndarray, indices: np.ndarray, noise: float = 0.01, **kwargs) -> np.ndarray:
    """
    ROAD 自定义 perturb，修 Quantus 0.6.0 多通道图像越界 bug。
    根因：ROAD evaluate_batch 把 a_batch (N,1,H,W) broadcast 到 (N,C,H,W) 后 flatten，
         indices 范围变成 C*H*W，但 noisy_linear_imputation 内部
         arr.reshape((arr.shape[0], -1)) 以 arr.shape[0]=C 为 batch 维，
         mask 长 H*W，indices 超出 → `index out of bounds for axis 0 with size H*W`。
    修法：将 indices 先 % (H*W) 转回像素坐标（ROAD 语义=删像素，所有通道一起扰），
         再调原版 noisy_linear_imputation，保持算法语义不变。
    Source: quantus/functions/perturb_func.py noisy_linear_imputation
            quantus/metrics/faithfulness/road.py evaluate_batch line 317-318
    """
    n_px = arr.shape[-1] * arr.shape[-2]  # H * W
    # indices 可能来自 C*H*W flatten → 转为 H*W 像素索引（去重，保持降序）
    hw_indices = np.unique(indices % n_px)
    return _nli_orig(arr=arr, indices=hw_indices, noise=noise)


def _irof_perturb_broadcast(arr: np.ndarray, mask: np.ndarray, perturb_baseline: str = "mean", **kwargs) -> np.ndarray:
    """
    IROF 自定义 perturb，修 Quantus 0.6.0 多通道图像 mask 形状不匹配 bug。
    根因：IROF evaluate_batch 生成 mask (N,1,H,W) 但 arr=x_perturbed (N,C,H,W)，
         baseline_replacement_by_mask 要求 arr.shape==mask.shape → assert 失败。
    修法：在调 _brm_orig 前将 mask broadcast 到 arr.shape（C 通道方向复制），
         保持 IROF 算法语义（segment 内所有通道一起替换）不变。
    Source: quantus/functions/perturb_func.py baseline_replacement_by_mask line 196
            quantus/metrics/faithfulness/irof.py evaluate_batch line 369, 371-374
    """
    if arr.shape != mask.shape:
        mask = np.broadcast_to(mask, arr.shape).copy()
    return _brm_orig(arr=arr, mask=mask, perturb_baseline=perturb_baseline)


# =========================================================
# 单个 XAI 的 4 指标评测（PixelFlipping / ROAD / IROF / insertion）
# 每行结果打上 xai 标签，追加到 results。
# =========================================================

def run_faithfulness_metrics(
    model: torch.nn.Module,
    x_batch: np.ndarray,       # (N,C,H,W)
    labels_arr: np.ndarray,    # (N,)
    a_batch: np.ndarray,       # (N,H,W) 该 XAI 的热图
    xai_name: str,
    cfg: dict,
    device: torch.device,
    results: list,
):
    n_samples = x_batch.shape[0]

    # ---- Quantus: PixelFlipping (deletion) ----
    logger.info(f"[{xai_name}] 运行 Quantus PixelFlipping (deletion)...")
    try:
        # features_in_step: 每步翻多少像素。Quantus 检查 H*W % features_in_step == 0。
        # config 驱动，默认 512（224²=50176，512×98 整除）；不整除自动回退最近整除值。
        # Source: quantus/helpers/asserts.py assert_features_in_step
        pf_step = int(cfg.get("pixelflip_features_in_step", 512))
        hw_pixels = x_batch.shape[2] * x_batch.shape[3]  # H * W
        if hw_pixels % pf_step != 0:
            candidate = pf_step
            while candidate > 1 and hw_pixels % candidate != 0:
                candidate -= 1
            logger.warning(
                f"pixelflip_features_in_step={pf_step} 不整除 H*W={hw_pixels}，"
                f"自动回退到 {candidate}（请在 config 设置整除值）"
            )
            pf_step = candidate
        pf_metric = quantus.PixelFlipping(
            features_in_step=pf_step,
            perturb_baseline="black",
            return_auc_per_sample=True,
            disable_warnings=True,
        )
        pf_scores = pf_metric(
            model=model,
            x_batch=x_batch,
            y_batch=labels_arr,
            a_batch=a_batch,
            channel_first=True,
            softmax=True,
            device=device,
        )
        pf_mean = float(np.nanmean(pf_scores))
        nan_count = int(np.isnan(pf_scores).sum())
        logger.info(f"  [{xai_name}] PixelFlipping: mean={pf_mean:.4f}, nan_count={nan_count}/{n_samples}")
        results.append({
            "xai": xai_name, "metric": "PixelFlipping(deletion)",
            "mean_score": pf_mean, "nan_count": nan_count,
            "n_samples": n_samples, "is_nan": np.isnan(pf_mean),
        })
    except Exception as e:
        logger.warning(f"  [{xai_name}] PixelFlipping 失败: {e}")
        results.append({
            "xai": xai_name, "metric": "PixelFlipping(deletion)",
            "mean_score": float("nan"), "nan_count": n_samples,
            "n_samples": n_samples, "is_nan": True, "error": str(e),
        })

    # ---- Quantus: ROAD ----
    logger.info(f"[{xai_name}] 运行 Quantus ROAD...")
    try:
        # ROAD 越界根因（Quantus 0.6.0 多通道 bug）见 _road_perturb_3ch 注释。
        road_pcts = cfg.get("road_percentages") or list(range(1, 100, 2))
        road_metric = quantus.ROAD(
            percentages=list(road_pcts),
            noise=0.01,
            perturb_func=_road_perturb_3ch,  # 修 C*H*W indices 越界
            normalise=True,
            abs=False,        # 热图已 ReLU+归一化，不再取绝对值
            disable_warnings=True,
        )
        road_scores = road_metric(
            model=model,
            x_batch=x_batch,
            y_batch=labels_arr,
            a_batch=a_batch,
            channel_first=True,
            softmax=True,
            device=device,
        )
        road_vals = list(road_scores.values()) if isinstance(road_scores, dict) else road_scores
        road_mean = float(np.nanmean(road_vals))
        nan_count = int(np.isnan(np.array(road_vals, dtype=float)).sum())
        logger.info(f"  [{xai_name}] ROAD: mean={road_mean:.4f}")
        results.append({
            "xai": xai_name, "metric": "ROAD",
            "mean_score": road_mean, "nan_count": nan_count,
            "n_samples": n_samples, "is_nan": np.isnan(road_mean),
        })
    except Exception as e:
        logger.warning(f"  [{xai_name}] ROAD 失败: {e}")
        results.append({
            "xai": xai_name, "metric": "ROAD",
            "mean_score": float("nan"), "nan_count": n_samples,
            "n_samples": n_samples, "is_nan": True, "error": str(e),
        })

    # ---- Quantus: IROF ----
    logger.info(f"[{xai_name}] 运行 Quantus IROF...")
    try:
        # IROF mask 形状不匹配根因（Quantus 0.6.0 多通道 bug）见 _irof_perturb_broadcast 注释。
        irof_metric = quantus.IROF(
            segmentation_method="slic",
            perturb_baseline="mean",
            perturb_func=_irof_perturb_broadcast,  # 修 (N,1,H,W) vs (N,C,H,W) mask 不匹配
            return_aggregate=True,
            normalise=True,
            abs=False,
            disable_warnings=True,
        )
        irof_scores = irof_metric(
            model=model,
            x_batch=x_batch,
            y_batch=labels_arr,
            a_batch=a_batch,
            channel_first=True,
            softmax=True,
            device=device,
        )
        irof_mean = float(np.nanmean(irof_scores))
        logger.info(f"  [{xai_name}] IROF: mean={irof_mean:.4f}")
        results.append({
            "xai": xai_name, "metric": "IROF",
            "mean_score": irof_mean, "nan_count": 0,
            "n_samples": n_samples, "is_nan": np.isnan(irof_mean),
        })
    except Exception as e:
        logger.warning(f"  [{xai_name}] IROF 失败: {e}")
        results.append({
            "xai": xai_name, "metric": "IROF",
            "mean_score": float("nan"), "nan_count": n_samples,
            "n_samples": n_samples, "is_nan": True, "error": str(e),
        })

    # ---- Insertion 自实现（Quantus 无原生 insertion，researcher T5 核实）----
    logger.info(f"[{xai_name}] 运行 insertion game（自实现，LeRF 反转顺序）...")
    try:
        ins_aucs = insertion_auc(model, x_batch, a_batch, labels_arr, device, n_steps=50)
        ins_mean = float(np.nanmean(ins_aucs))
        nan_count = int(np.isnan(ins_aucs).sum())
        logger.info(f"  [{xai_name}] Insertion(自实现): mean AUC={ins_mean:.4f}, nan_count={nan_count}")
        results.append({
            "xai": xai_name,
            "metric": "Insertion(self-impl, Quantus-no-native)",
            "mean_score": ins_mean, "nan_count": nan_count,
            "n_samples": n_samples, "is_nan": np.isnan(ins_mean),
        })
    except Exception as e:
        logger.warning(f"  [{xai_name}] Insertion 失败: {e}")
        results.append({
            "xai": xai_name,
            "metric": "Insertion(self-impl, Quantus-no-native)",
            "mean_score": float("nan"), "nan_count": n_samples,
            "n_samples": n_samples, "is_nan": True, "error": str(e),
        })


# =========================================================
# 主入口
# =========================================================

def load_config(config_path: str) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _build_black_baseline(mean, std, C, H, W, device) -> torch.Tensor:
    """归一化空间的纯黑图 baseline：像素 0 经 Normalize → (0-mean)/std，逐通道。返回 (1,C,H,W)。"""
    m = torch.tensor(mean, dtype=torch.float32).view(1, C, 1, 1)
    s = torch.tensor(std, dtype=torch.float32).view(1, C, 1, 1)
    black = (torch.zeros(1, C, H, W) - m) / s
    return black.to(device)


def _sample_baseline_pool(
    train_csv: Path,
    transform,
    n_baseline: int,
    device: torch.device,
    fallback_x: np.ndarray,
    seed: int = 42,
) -> torch.Tensor:
    """
    GradientShap baseline 分布：随机采样 n_baseline 张训练图（researcher：baseline 须是分布）。
    train.csv 存在 → 从训练集随机取（不泄漏测试）；缺失 → 回退从 fallback_x（当前子样本）取。
    返回 (n_baseline, C, H, W) 张量 on device。
    """
    rng = np.random.RandomState(seed)
    try:
        train_ds = MRIDataset(train_csv, transform=transform)
        n = min(n_baseline, len(train_ds))
        idx = rng.choice(len(train_ds), size=n, replace=False).tolist()
        pool = torch.stack([train_ds[i][0] for i in idx], dim=0)  # (n,C,H,W)
        logger.info(f"GradientShap baseline 分布：从 train.csv 随机取 {n} 张")
        return pool.to(device)
    except Exception as e:
        n = min(n_baseline, fallback_x.shape[0])
        idx = rng.choice(fallback_x.shape[0], size=n, replace=False).tolist()
        pool = torch.tensor(fallback_x[idx], dtype=torch.float32)
        logger.warning(
            f"GradientShap baseline：train.csv 不可用（{e}），回退从当前子样本取 {n} 张"
        )
        return pool.to(device)


def main():
    parser = argparse.ArgumentParser(description="WaveFidBench faithfulness.py（多 XAI × 多指标）")
    parser.add_argument("--config", required=True, help="YAML config 路径")
    parser.add_argument(
        "--split_csv_dir", default=None, help="split csv 目录（默认从 config 推导）"
    )
    parser.add_argument("--checkpoint", required=True, help="冻结权重 .pt 路径")
    parser.add_argument(
        "--n_samples", type=int, default=200, help="子样本数"
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--smoke", type=int, default=0,
        help=">0 时走 CPU 烟测：仅取 min(n_samples, 4) 张，验多 XAI 管道不 crash（主线跑）",
    )
    args = parser.parse_args()

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    cfg = load_config(args.config)
    project_root = Path(__file__).parent.parent
    log_dir = project_root / cfg.get("log_dir", "log")
    log_dir.mkdir(parents=True, exist_ok=True)

    if args.split_csv_dir is None:
        args.split_csv_dir = str(project_root / cfg.get("split_csv_dir", "log/splits"))
    split_csv_dir = Path(args.split_csv_dir)

    # smoke 强制 CPU（Windows 本地 8GB 调试用；主线跑），正式走 config 设备
    if args.smoke > 0:
        device = torch.device("cpu")
        logger.info("[smoke] 强制 CPU")
    else:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info(f"设备: {device}")

    # 加载模型
    backbone_name = cfg.get("backbone", "resnet50")
    num_classes = cfg.get("num_classes", 4)
    model = build_backbone(backbone_name, num_classes, pretrained=False)
    ckpt = torch.load(args.checkpoint, map_location=device)
    model.load_state_dict(ckpt)
    model = model.to(device)
    model.eval()
    logger.info(f"权重已加载：{args.checkpoint}")

    # ---- backbone 分支：决定 XAI 列表 + GradCAM target_layer ----
    # GradCAM 依赖卷积 target_layer，仅适 CNN；ViT-B/16 无合适卷积 target → 跳过（不 crash）。
    # IG / GradientShap 梯度型，CNN + ViT 通用。
    target_layer = None
    if backbone_name == "resnet50":
        target_layer = model.layer4[-1].conv3  # ResNet50 Bottleneck 最后一层（researcher T5）
        xai_list = ["GradCAM", "IntegratedGradients", "GradientShap"]
        gradcam_skipped = False
    elif backbone_name == "vit_b_16":
        xai_list = ["IntegratedGradients", "GradientShap"]  # GradCAM 跳过（ViT 无卷积 target）
        gradcam_skipped = True
    else:
        raise NotImplementedError(
            f"faithfulness.py 支持 resnet50 / vit_b_16，backbone={backbone_name} 未适配。"
        )
    logger.info(f"backbone={backbone_name} → XAI 列表={xai_list}"
                + ("（GradCAM 跳过：ViT 无卷积 target）" if gradcam_skipped else ""))

    # ---- XAI 超参（config 驱动，禁硬编码；查不到官方值标 TODO）----
    # IG：n_steps 默认 50（captum 默认）；baseline 默认 'zero'（captum 默认 0 标量）。
    ig_n_steps = int(cfg.get("ig_n_steps", 50))
    ig_baseline_mode = cfg.get("ig_baseline", "zero")  # zero | black
    # GradientShap：n_samples/stdevs/n_baseline（researcher 核 captum 官方默认 n_samples=5, stdevs=0.0）。
    gs_n_samples = int(cfg.get("gradshap_n_samples", 5))
    gs_stdevs = float(cfg.get("gradshap_stdevs", 0.0))
    gs_n_baseline = int(cfg.get("gradshap_n_baseline", 5))  # baseline 分布样本数（须 >1）
    # 子带能量 wavelet 超参（同 subband_zero.py，researcher T4）
    wavelet_wave = cfg.get("wavelet_wave", "db1")
    wavelet_mode = cfg.get("wavelet_mode", "symmetric")

    # DataLoader 子样本
    mean = cfg["normalize_mean"]
    std = cfg["normalize_std"]
    img_size = cfg["image_size"]
    eval_transform = transforms.Compose([
        transforms.Resize((img_size, img_size)),
        transforms.ToTensor(),
        transforms.Normalize(mean=mean, std=std),
    ])
    test_ds = MRIDataset(split_csv_dir / "test.csv", transform=eval_transform)

    n_req = min(args.n_samples, len(test_ds))
    if args.smoke > 0:
        n_req = min(n_req, 4)  # 烟测仅取 ≤4 张验管道
    indices = np.random.choice(len(test_ds), size=n_req, replace=False).tolist()
    subset_ds = Subset(test_ds, indices)

    loader = DataLoader(
        subset_ds,
        batch_size=min(32, n_req),
        shuffle=False,
        num_workers=cfg.get("num_workers", 0) if args.smoke == 0 else 0,
        pin_memory=cfg.get("pin_memory", False) if args.smoke == 0 else False,
        multiprocessing_context="spawn" if (args.smoke == 0 and cfg.get("num_workers", 0) > 0) else None,
    )

    # 收集全部子样本 tensor（一次遍历）
    all_x, all_labels = [], []
    for imgs, lbls in loader:
        all_x.append(imgs.detach().cpu().numpy())
        all_labels.append(lbls.cpu().numpy())
    x_batch = np.concatenate(all_x, axis=0).astype(np.float32)   # (N,C,H,W)
    labels_arr = np.concatenate(all_labels, axis=0)              # (N,)
    n_samples = x_batch.shape[0]
    C, H, W = x_batch.shape[1], x_batch.shape[2], x_batch.shape[3]
    logger.info(f"子样本收集完成：x_batch shape={x_batch.shape}")

    # IG baseline 张量：'zero' → None（captum 默认黑图）；'black' → 归一化黑图显式构造
    ig_baseline_tensor = None
    if ig_baseline_mode == "black":
        ig_baseline_tensor = _build_black_baseline(mean, std, C, H, W, device)

    # GradientShap baseline 分布：随机训练图（researcher：baseline 须是分布 B>1）
    gs_baseline_pool = None
    if "GradientShap" in xai_list:
        gs_baseline_pool = _sample_baseline_pool(
            split_csv_dir / "train.csv", eval_transform, gs_n_baseline, device,
            fallback_x=x_batch, seed=args.seed,
        )

    # ---- 逐 XAI 产热图 ----
    heatmaps = {}  # xai_name -> (N,H,W)
    for xai in xai_list:
        logger.info(f"计算 {xai} 归因...")
        if xai == "GradCAM":
            a = compute_gradcam_batch(model, x_batch, labels_arr, target_layer, device)
        elif xai == "IntegratedGradients":
            a = compute_ig_batch(model, x_batch, labels_arr, device,
                                  n_steps=ig_n_steps, baseline_tensor=ig_baseline_tensor)
        elif xai == "GradientShap":
            a = compute_gradshap_batch(model, x_batch, labels_arr, gs_baseline_pool, device,
                                       n_samples=gs_n_samples, stdevs=gs_stdevs)
        else:
            raise ValueError(f"未知 XAI: {xai}")
        heatmaps[xai] = a
        logger.info(f"  {xai} 热图 shape={a.shape}")

    # ---- 逐 XAI 跑 4 指标 ----
    results = []
    # ViT 下 GradCAM 跳过（LayerGradCam 官方=CNN 最后卷积层设计，ViT 不适用）：
    # 写单行 is_skipped 标记留痕，不 crash（researcher 指示）。
    if gradcam_skipped:
        results.append({
            "xai": "GradCAM", "metric": "(skipped)",
            "mean_score": float("nan"), "nan_count": n_samples,
            "n_samples": n_samples, "is_nan": True, "is_skipped": True,
            "error": "ViT-B/16 无卷积 target_layer，LayerGradCam 不适用",
        })

    for xai in xai_list:
        run_faithfulness_metrics(
            model, x_batch, labels_arr, heatmaps[xai], xai, cfg, device, results,
        )

    # ---- 子带能量分布（Gate2 B）----
    logger.info("计算各 XAI 热图的 wavelet 子带能量分布...")
    energy_rows = []
    for xai in xai_list:
        try:
            ratios = compute_subband_energy(
                heatmaps[xai], device, wave=wavelet_wave, mode=wavelet_mode,
            )
            for sb in ["LL", "LH", "HL", "HH"]:
                energy_rows.append({
                    "xai": xai, "subband": sb, "energy_ratio": ratios[sb],
                    "n_samples": n_samples,
                })
            logger.info(f"  {xai} 子带能量占比: {ratios}")
        except Exception as e:
            logger.warning(f"  {xai} 子带能量失败: {e}")
            for sb in ["LL", "LH", "HL", "HH"]:
                energy_rows.append({
                    "xai": xai, "subband": sb, "energy_ratio": float("nan"),
                    "n_samples": n_samples, "error": str(e),
                })

    # ---- 写 csv ----
    df_res = pd.DataFrame(results)
    df_res["backbone"] = backbone_name
    df_res["split_mode"] = cfg.get("split_mode", "unknown")
    df_res["timestamp"] = datetime.now().isoformat()
    results_csv = log_dir / "faithfulness_results.csv"
    df_res.to_csv(results_csv, index=False)
    logger.info(f"结果 csv 已写 -> {results_csv}")

    df_energy = pd.DataFrame(energy_rows)
    df_energy["backbone"] = backbone_name
    df_energy["split_mode"] = cfg.get("split_mode", "unknown")
    df_energy["wavelet"] = f"{wavelet_wave}/{wavelet_mode}/J1"
    df_energy["timestamp"] = datetime.now().isoformat()
    energy_csv = log_dir / "faithfulness_subband_energy.csv"
    df_energy.to_csv(energy_csv, index=False)
    logger.info(f"子带能量 csv 已写 -> {energy_csv}")

    # Gate1 判断
    non_nan_count = int((~df_res["is_nan"]).sum())
    logger.info(
        f"\n=== Q 块摘要 ===\n"
        f"  非 nan 组合数：{non_nan_count} / {len(df_res)}\n"
        f"  XAI 数（实跑）：{len(xai_list)}（Gate3 需 ≥3；ViT 下 GradCAM 跳过）\n"
        f"  Gate1 要求：≥1 非 nan → {'PASS' if non_nan_count >= 1 else 'FAIL'}"
    )

    # state.json
    state = {
        "script": "faithfulness.py",
        "timestamp": datetime.now().isoformat(),
        "backbone": backbone_name,
        "checkpoint": args.checkpoint,
        "n_samples": n_samples,
        "split_mode": cfg.get("split_mode", "unknown"),
        "xai_methods": xai_list,
        "gradcam_skipped": gradcam_skipped,
        "xai_hyperparams": {
            "ig_n_steps": ig_n_steps,
            "ig_method": "gausslegendre",
            "ig_baseline": ig_baseline_mode,
            "gradshap_n_samples": gs_n_samples,
            "gradshap_stdevs": gs_stdevs,
            "gradshap_n_baseline": gs_n_baseline,
            "wavelet": f"{wavelet_wave}/{wavelet_mode}/J1",
        },
        "metrics": results,
        "subband_energy": energy_rows,
        "gate1_pass": non_nan_count >= 1,
        "insertion_note": "insertion game 自实现，Quantus 无原生 insertion 实现（researcher T5 核实）",
    }
    def _json_default(o):
        if isinstance(o, np.bool_):
            return bool(o)
        if isinstance(o, (np.floating, np.integer)):
            return o.item()
        return str(o)

    state_path = log_dir / "faithfulness_state.json"
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False, default=_json_default)
    logger.info(f"state.json 已写 -> {state_path}")

    print(f"\nDone. results -> {results_csv}")
    print(f"      energy  -> {energy_csv}")
    print(df_res[["xai", "metric", "mean_score", "is_nan"]].to_string(index=False))
    print("\n子带能量占比：")
    print(df_energy[["xai", "subband", "energy_ratio"]].to_string(index=False))


if __name__ == "__main__":
    main()
