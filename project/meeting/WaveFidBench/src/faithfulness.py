"""
faithfulness.py — WaveFidBench Gate1 Quantus faithfulness 非 nan 烟测
服务项目：WaveFidBench (wavefid) Gate1，lever 地基 Q 块

功能：
  加载冻结分类器，对 ≤200 张测试子样本做：
  1. Grad-CAM（captum LayerGradCam → LayerAttribution.interpolate → a_batch (N,H,W)）
  2. Quantus 指标：
     - PixelFlipping（deletion，features_in_step=1, perturb_baseline='black', return_auc_per_sample=True）
     - ROAD（researcher T5 核实参数：percentages=range(1,100,2), noise=0.01）
     - IROF（slic, mean, return_aggregate，researcher T5）
  3. insertion 自实现 <50 行：
     反转 PixelFlipping 顺序（LeRF/从全 baseline 渐加高归因像素）
     注释标「insertion game 自实现，Quantus 无原生 insertion 实现（researcher T5 核实）」
  输出各 (XAI×指标) faithfulness 标量到 csv
  Gate1 只需 ≥1 组合非 nan

Quantus API 来源：https://github.com/understandingai/Quantus（researcher T5 核实）
captum API：LayerGradCam → LayerAttribution.interpolate → .squeeze(1)

用法：
  python src/faithfulness.py \\
      --config configs/gate1_kaggle.yaml \\
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
from captum.attr import LayerGradCam, LayerAttribution

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
# Grad-CAM 提取（captum，researcher T5 核实 API）
# =========================================================

def compute_gradcam_batch(
    model: torch.nn.Module,
    imgs: torch.Tensor,
    labels: torch.Tensor,
    target_layer,
    device: torch.device,
) -> np.ndarray:
    """
    返回 a_batch: np.ndarray (N, H, W)，归一化到 [0,1]
    captum LayerGradCam -> LayerAttribution.interpolate -> .squeeze(1)
    target_layer = model.layer4[-1].conv3（ResNet50 Bottleneck 最后一层，researcher T5）
    """
    model.eval()
    imgs = imgs.to(device).requires_grad_(True)
    labels = labels.to(device)

    lgc = LayerGradCam(model, target_layer)
    H, W = imgs.shape[2], imgs.shape[3]

    attrs_list = []
    for i in range(len(imgs)):
        attr = lgc.attribute(imgs[i].unsqueeze(0), target=int(labels[i].item()))
        # 插值回原图尺寸
        attr_interp = LayerAttribution.interpolate(attr, (H, W), interpolate_mode="bicubic")
        attr_map = attr_interp.squeeze(0).squeeze(0)  # (H, W)
        # ReLU + 归一化到 [0, 1]
        attr_map = torch.clamp(attr_map, min=0)
        max_val = attr_map.max()
        if max_val > 0:
            attr_map = attr_map / max_val
        attrs_list.append(attr_map.detach().cpu().numpy())

    return np.stack(attrs_list, axis=0)  # (N, H, W)


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
# Quantus 图像模式自定义 perturb 函数（修 0.6.0 多通道 bug）
# =========================================================

def _road_perturb_3ch(arr: np.ndarray, indices: np.ndarray, noise: float = 0.01, **kwargs) -> np.ndarray:
    """
    ROAD 自定义 perturb，修 Quantus 0.6.0 多通道图像越界 bug。
    根因：ROAD evaluate_batch 把 a_batch (N,1,H,W) broadcast 到 (N,C,H,W) 后
         flatten indices 范围变成 C*H*W，但 noisy_linear_imputation 内部
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
# 主入口
# =========================================================

def load_config(config_path: str) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(description="WaveFidBench faithfulness.py")
    parser.add_argument("--config", required=True, help="YAML config 路径")
    parser.add_argument(
        "--split_csv_dir", default=None, help="split csv 目录（默认从 config 推导）"
    )
    parser.add_argument("--checkpoint", required=True, help="冻结权重 .pt 路径")
    parser.add_argument(
        "--n_samples", type=int, default=200, help="子样本数（Gate1 验非 nan 用）"
    )
    parser.add_argument("--seed", type=int, default=42)
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

    # 仅支持 ResNet50（target_layer 写死 layer4[-1].conv3）
    if backbone_name != "resnet50":
        raise NotImplementedError(
            f"faithfulness.py 目前只支持 resnet50（target_layer=layer4[-1].conv3）。"
            f"backbone={backbone_name} 时请在代码中补对应 target_layer。"
        )
    target_layer = model.layer4[-1].conv3

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

    n_samples = min(args.n_samples, len(test_ds))
    indices = np.random.choice(len(test_ds), size=n_samples, replace=False).tolist()
    subset_ds = Subset(test_ds, indices)

    loader = DataLoader(
        subset_ds,
        batch_size=min(32, n_samples),
        shuffle=False,
        num_workers=cfg.get("num_workers", 0),
        pin_memory=cfg.get("pin_memory", False),
        multiprocessing_context="spawn" if cfg.get("num_workers", 0) > 0 else None,
    )

    # 收集全部子样本 tensor + 归因图
    all_x, all_labels, all_attr = [], [], []

    for imgs, lbls in loader:
        imgs_dev = imgs.to(device)
        lbls_dev = lbls.to(device)

        # Grad-CAM 归因
        attrs = compute_gradcam_batch(model, imgs, lbls, target_layer, device)  # (B, H, W)

        all_x.append(imgs.detach().cpu().numpy())
        all_labels.append(lbls.cpu().numpy())
        all_attr.append(attrs)

    x_batch = np.concatenate(all_x, axis=0)      # (N, C, H, W)
    labels_arr = np.concatenate(all_labels, axis=0)  # (N,)
    a_batch = np.concatenate(all_attr, axis=0)   # (N, H, W)

    logger.info(f"Grad-CAM 归因完成：a_batch shape={a_batch.shape}")

    results = []

    # ---- Quantus: PixelFlipping (deletion) ----
    logger.info("运行 Quantus PixelFlipping (deletion)...")
    try:
        # features_in_step: 每步翻多少像素。Quantus 检查 H*W % features_in_step == 0。
        # 224×224=50176。config 驱动，默认 3136（=224²/16，16 步整除），正式跑可调。
        # Source: quantus/helpers/asserts.py assert_features_in_step（检查 x_batch.shape[2:]）
        pf_step = int(cfg.get("pixelflip_features_in_step", 512))
        # 整除防御：Quantus 按 H*W 检查，若不整除自动回退到最近整除值
        hw_pixels = x_batch.shape[2] * x_batch.shape[3]  # H * W = 50176
        if hw_pixels % pf_step != 0:
            # 找最近的整除值（向下找）
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
            channel_first=True,   # 显式声明 (N,C,H,W)，防 channel_first 推断出错
            softmax=True,         # resnet50 输出 logits，Quantus wrapper 加 softmax
            device=device,
        )
        pf_mean = float(np.nanmean(pf_scores))
        nan_count = int(np.isnan(pf_scores).sum())
        logger.info(f"  PixelFlipping: mean={pf_mean:.4f}, nan_count={nan_count}/{n_samples}")
        results.append({
            "xai": "GradCAM",
            "metric": "PixelFlipping(deletion)",
            "mean_score": pf_mean,
            "nan_count": nan_count,
            "n_samples": n_samples,
            "is_nan": np.isnan(pf_mean),
        })
    except Exception as e:
        logger.warning(f"  PixelFlipping 失败: {e}")
        results.append({
            "xai": "GradCAM", "metric": "PixelFlipping(deletion)",
            "mean_score": float("nan"), "nan_count": n_samples,
            "n_samples": n_samples, "is_nan": True, "error": str(e),
        })

    # ---- Quantus: ROAD ----
    logger.info("运行 Quantus ROAD...")
    try:
        # ROAD 越界根因（Quantus 0.6.0 bug，多通道图像）：
        #   evaluate_batch 把 a_batch (N,1,H,W) broadcast 到 (N,C,H,W) 后 flatten，
        #   indices 范围变 C*H*W，但 noisy_linear_imputation 内 arr_flat 只有 H*W 列
        #   → index 101605 out of bounds for axis 0 with size 50176。
        # 修法：自定义 perturb_func=_road_perturb_3ch，将 indices % H*W 转回像素坐标。
        # 另外 ROAD.custom_batch_preprocess 里 self.a_size = a_batch[0,:,:].size 对
        #   (N,1,H,W) 算出 1*H 而非 H*W（numpy 3-index 切片），导致 top_k 极小。
        #   传 perturb_func 后 indices 问题已修，top_k 问题由 _road_perturb_3ch % 兜底。
        # Source: quantus/metrics/faithfulness/road.py custom_batch_preprocess line 260
        #         quantus/helpers/utils.py offset_coordinates line 1003-1012
        road_pcts = cfg.get("road_percentages") or list(range(1, 100, 2))
        road_metric = quantus.ROAD(
            percentages=list(road_pcts),
            noise=0.01,
            perturb_func=_road_perturb_3ch,  # 修 C*H*W indices 越界
            normalise=True,   # 默认 True，归一化归因
            abs=False,        # Grad-CAM 已 ReLU+归一化，不需再取绝对值
            disable_warnings=True,
        )
        road_scores = road_metric(
            model=model,
            x_batch=x_batch,
            y_batch=labels_arr,
            a_batch=a_batch,
            channel_first=True,   # 显式声明，防推断出错
            softmax=True,
            device=device,
        )
        # ROAD 返回 dict {percentage: accuracy}，取 values 再 nanmean
        road_vals = list(road_scores.values()) if isinstance(road_scores, dict) else road_scores
        road_mean = float(np.nanmean(road_vals))
        nan_count = int(np.isnan(np.array(road_vals, dtype=float)).sum())
        logger.info(f"  ROAD: mean={road_mean:.4f}")
        results.append({
            "xai": "GradCAM", "metric": "ROAD",
            "mean_score": road_mean, "nan_count": nan_count,
            "n_samples": n_samples, "is_nan": np.isnan(road_mean),
        })
    except Exception as e:
        logger.warning(f"  ROAD 失败: {e}")
        results.append({
            "xai": "GradCAM", "metric": "ROAD",
            "mean_score": float("nan"), "nan_count": n_samples,
            "n_samples": n_samples, "is_nan": True, "error": str(e),
        })

    # ---- Quantus: IROF ----
    logger.info("运行 Quantus IROF...")
    try:
        # IROF mask 形状不匹配根因（Quantus 0.6.0 bug，多通道图像）：
        #   evaluate_batch 生成 mask (N,1,H,W)（segments 展开时 [:, None]），
        #   但 arr=x_perturbed (N,C,H,W)，baseline_replacement_by_mask assert
        #   arr.shape==mask.shape → AssertionError: The shape of arr must be the same as the mask shape。
        # 修法：自定义 perturb_func=_irof_perturb_broadcast，调 _brm_orig 前
        #   broadcast mask 到 arr.shape（C 通道方向复制），语义等价（segment 所有通道一起替换）。
        # softmax=True 保持（IROF 内部用 y_pred_perturb/y_pred，需正数；Quantus wrapper 加 softmax）
        # disable_warnings=True 压掉「model contains no Softmax」警告（resnet50 输出 logits 正常）。
        # Source: quantus/metrics/faithfulness/irof.py evaluate_batch line 369, 371-374
        #         quantus/functions/perturb_func.py baseline_replacement_by_mask line 196
        irof_metric = quantus.IROF(
            segmentation_method="slic",
            perturb_baseline="mean",
            perturb_func=_irof_perturb_broadcast,  # 修 (N,1,H,W) vs (N,C,H,W) mask 不匹配
            return_aggregate=True,
            normalise=True,   # 归一化归因（默认 True）
            abs=False,        # Grad-CAM 已 ReLU，不再取绝对值
            disable_warnings=True,
        )
        irof_scores = irof_metric(
            model=model,
            x_batch=x_batch,
            y_batch=labels_arr,
            a_batch=a_batch,
            channel_first=True,   # 显式声明 (N,C,H,W)
            softmax=True,         # Quantus wrapper 加 softmax，IROF 比值需正数
            device=device,
        )
        irof_mean = float(np.nanmean(irof_scores))
        logger.info(f"  IROF: mean={irof_mean:.4f}")
        results.append({
            "xai": "GradCAM", "metric": "IROF",
            "mean_score": irof_mean, "nan_count": 0,
            "n_samples": n_samples, "is_nan": np.isnan(irof_mean),
        })
    except Exception as e:
        logger.warning(f"  IROF 失败: {e}")
        results.append({
            "xai": "GradCAM", "metric": "IROF",
            "mean_score": float("nan"), "nan_count": n_samples,
            "n_samples": n_samples, "is_nan": True, "error": str(e),
        })

    # ---- Insertion 自实现（Quantus 无原生 insertion 实现，researcher T5 核实）----
    logger.info("运行 insertion game（自实现，LeRF 反转顺序）...")
    try:
        ins_aucs = insertion_auc(model, x_batch, a_batch, labels_arr, device, n_steps=50)
        ins_mean = float(np.nanmean(ins_aucs))
        nan_count = int(np.isnan(ins_aucs).sum())
        logger.info(f"  Insertion(自实现): mean AUC={ins_mean:.4f}, nan_count={nan_count}")
        results.append({
            "xai": "GradCAM",
            "metric": "Insertion(self-impl, Quantus-no-native)",
            "mean_score": ins_mean,
            "nan_count": nan_count,
            "n_samples": n_samples,
            "is_nan": np.isnan(ins_mean),
        })
    except Exception as e:
        logger.warning(f"  Insertion 失败: {e}")
        results.append({
            "xai": "GradCAM",
            "metric": "Insertion(self-impl, Quantus-no-native)",
            "mean_score": float("nan"), "nan_count": n_samples,
            "n_samples": n_samples, "is_nan": True, "error": str(e),
        })

    # 写 csv
    df_res = pd.DataFrame(results)
    df_res["backbone"] = backbone_name
    df_res["split_mode"] = cfg.get("split_mode", "unknown")
    df_res["timestamp"] = datetime.now().isoformat()

    results_csv = log_dir / "faithfulness_results.csv"
    df_res.to_csv(results_csv, index=False)
    logger.info(f"结果 csv 已写 -> {results_csv}")

    # Gate1 判断
    non_nan_count = int((~df_res["is_nan"]).sum())
    logger.info(
        f"\n=== Gate1 Q 块摘要 ===\n"
        f"  非 nan 组合数：{non_nan_count} / {len(df_res)}\n"
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
        "xai_method": "GradCAM (captum LayerGradCam, layer4[-1].conv3)",
        "metrics": results,
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
    print(df_res[["xai", "metric", "mean_score", "is_nan"]].to_string(index=False))


if __name__ == "__main__":
    main()
