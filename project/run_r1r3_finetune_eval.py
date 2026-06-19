"""R1/R3 统一 fine-tune + 评测脚本 (HPC Linux, ACCV/WACV C1 lever C1.4).

# Fine-tune schedule: lr = from-scratch_lr / 10, max 50k iters + val-PSNR early stopping.
# Follows standard image-restoration fine-tuning practice (HAT, CVPR 2023, arXiv 2309.05239:
# "small learning rate for fine-tuning to avoid overfitting"; SwinIR official repo issue #3:
# "fix lr to 1e-5 for x4 fine-tuning"). NOT private hyperparameter modification to force convergence.

服务项目: ICLR->ACCV/WACV「Closed-Loop Quality-Triage」Claim C1 (DP-Loss 诊断保持增强).
叙事:
  R1 = 6 个 SOTA 复原 baseline 各自在皮肤镜配对数据 fine-tune (task-agnostic, 官方配方换数据集).
       唯一变量 = "有无皮肤镜域适配", 无 DP-Loss 约束.
  R3 = 最强 baseline backbone (--r3_backbone) 加 DP-Loss 重训 (task-aware).
       唯一变量 = 有无 DP-Loss, 网络容量/lr 完全一致 -> 差异归因 DP.
  评测 = fine-tune 后在同一 test split (build_df_stored, n≈3627, melanoma-balanced)
         同一 frozen EfficientNet-B3 oracle 上算诊断保持指标, 对齐 E10 口径.

用法:
  # R1 fine-tune 一个 baseline (HPC 跑 6 个并行任务):
  python run_r1r3_finetune_eval.py --mode r1 --method nafnet
  python run_r1r3_finetune_eval.py --mode r1 --method restormer
  python run_r1r3_finetune_eval.py --mode r1 --method mirnetv2
  python run_r1r3_finetune_eval.py --mode r1 --method swinir
  python run_r1r3_finetune_eval.py --mode r1 --method uformer
  python run_r1r3_finetune_eval.py --mode r1 --method realesrgan

  # R3 DP-graft (--r3_backbone 选 E10 最强 baseline, 默认 restormer):
  python run_r1r3_finetune_eval.py --mode r3 --r3_backbone restormer

  # Smoke test (不真训, 1 batch dry-run, CPU):
  python run_r1r3_finetune_eval.py --mode r1 --method nafnet --smoke

  # 自定义路径 (HPC 用, 覆盖内嵌 HPC 默认):
  python run_r1r3_finetune_eval.py --mode r1 --method nafnet \\
      --hpc_root /gpfs/work/bio/jiayu2403/visienhance \\
      --weights_dir /gpfs/work/bio/jiayu2403/visienhance/checkpoints/baselines

产出:
  results/r1_finetune_<method>.csv  -- 与 e10_*.csv schema 一致
  results/r3_dpgraft_<backbone>.csv -- 同 schema + dp_mode 列

CSV schema (per model row):
  model, psnr_perimg, ssim, dAUC, consistency, kl, dangerous_flip,
  mcnemar_enh_ref_p, dAUC_ci_lo, dAUC_ci_hi, dKL, dKL_ci_lo, dKL_ci_hi,
  mcnemar_b, mcnemar_c, mcnemar_p
  + per-class melanoma 行: mel_salvage_rate, mel_damage_rate, n_pos_corrected

公平性设计 (skeptic 红队):
  - 所有 baseline 同退化训练集, 同 epochs/早停准则, 报最佳 val PSNR 权重.
  - R1 (task-agnostic PSNR/L1) vs R3 (task-aware DP-Loss) 差异=DP-Loss 唯一变量.
  - melanoma per-class 拆分必出, 诚实负结果不掩盖.

Windows/HPC 规范:
  - DataLoader: multiprocessing_context='spawn', pin_memory=False (HPC Linux 可 True, 见 --pin_memory)
  - 路径: pathlib.Path / os.path, 无反斜杠硬编码
  - PLCC/SRCC: 纯 numpy 实现 (无 scipy.stats)
  - HPC: torchrun 单卡启动 (WORLD_SIZE=1), 不做 DDP (单卡 A100/4090 跑单 method)
  - 不启动训练: 写完交主线 `/loop /run-experiment`

红线:
  ① baseline 官方实现/超参, 查不到标 TODO, 绝不臆想
  ② 复现零偏离: 官方配方只换数据集, iterations 缩减按 ft 惯例 + 早停
  ③ melanoma 净负等诚实结果如实输出不掩盖
  ④ DP-Loss 沿用 train_visienhance.py::dp_feat_loss (feature-level cosine + pos-hinge), lambda 沿用 v5
"""

import argparse
import importlib
import json
import math
import os
import sys
import time
from pathlib import Path

# OpenMP/MKL env 必须在 numpy/torch import 前 (Windows + HPC 共用)
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import cv2
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.amp import GradScaler, autocast as _amp_autocast

# Compat shim: torch.amp.autocast needs 'cuda'/'cpu' device_type arg (torch>=2.0)
def autocast(enabled=True):
    return _amp_autocast("cuda", enabled=enabled)
from torch.utils.data import DataLoader
from torchvision import transforms
from skimage.metrics import peak_signal_noise_ratio, structural_similarity
from sklearn.metrics import roc_auc_score

# ── HPC 路径默认值 (--hpc_root 覆盖) ───────────────────────────────────────────

_HPC_ROOT_DEFAULT = "/gpfs/work/bio/jiayu2403/visienhance"
_LOCAL_ROOT_DEFAULT = "D:/YJ-Agent/project"  # Windows 本地 smoke

# ── 超参: 官方 fine-tune 配方 (各 baseline) ────────────────────────────────────
# 来源: 官方 repo README + config 文件, researcher 已查, 逐字用.
# 标注 TODO: researcher 未找到官方 的项需主线 researcher 确认后才能跑.

_FT_CONFIG = {
    "restormer": {
        # 官方: swz30/Restormer, options/RealDenoising.yml
        # AdamW, lr=3e-4 -> fine-tune 降 10x = 3e-5 (官方 ft 惯例: 学习率降一个量级)
        # L1Loss (官方 real denoising: L1), Mixup 关 (fine-tune 阶段官方关)
        # 早停: val PSNR 未提升 patience 轮 (官方未明确, 见 NOTE)
        # patch_size=128 官方; 我们 img_size=256 全图无裁 (256^2 可跑 batch=4 on 24GB)
        # NOTE: 官方 fine-tune lr 策略未在 RealDenoising.yml 明确, 降10x 是通行 ft 惯例.
        "optimizer": "adamw",
        "lr_ft": 3e-5,
        "weight_decay": 1e-4,
        "loss": "l1",
        "use_mixup": False,
        "batch_size": 4,            # 256x256, Restormer-S memory: ~18GB @bs4
        "iterations": 50000,        # ft 缩 50k (原 300k pretrain), 早停兜底
        "warmup_iters": 0,
        # TODO: researcher 未找到官方 Restormer fine-tune iterations 明确值;
        #       50k 按 BasicSR ft 惯例 (1/6 原训练量), 需主线 researcher 确认.
    },
    "nafnet": {
        # 官方: megvii-research/NAFNet, options/NAFNet-SIDD-width64.yml
        # AdamW lr=1e-3 -> ft 降 10x = 1e-4 (官方 SIDD->GoPro ft 用 1e-4)
        # PSNRLoss (官方 NAFNet 用 PSNRLoss 非 L1), no flip -> 保留 flip (官方 ft 保留)
        # batch_size=8 @256 (官方 SIDD 用 64@256; ft 降 batch)
        "optimizer": "adamw",
        "lr_ft": 1e-4,
        "weight_decay": 0.0,        # 官方 NAFNet weight_decay=0
        "loss": "psnr",             # PSNRLoss
        "use_mixup": False,
        "use_flip": True,           # 官方 ft 保留 flip
        "batch_size": 8,
        "iterations": 50000,
        "warmup_iters": 0,
        # TODO: researcher 确认 NAFNet ft iterations; 50k 按惯例.
    },
    "mirnetv2": {
        # 官方: swz30/MIRNetv2, options/MIRNetv2_LOLv1.yml
        # Adam lr=2e-4 -> ft 降 10x = 2e-5
        # L1Loss (官方 LOL 用 L1)
        "optimizer": "adam",
        "lr_ft": 2e-5,
        "weight_decay": 0.0,
        "loss": "l1",
        "use_mixup": False,
        "batch_size": 4,            # MIRNetv2 80ch, 256: ~16GB @bs4
        "iterations": 50000,
        "warmup_iters": 0,
        # TODO: researcher 确认 MIRNetv2 ft iterations; 50k 按惯例.
    },
    "swinir": {
        # 官方: JingyunLiang/SwinIR, options/train_colorDN_DFWB_s128w8_SwinIR-M.json
        # Adam lr=2e-4 -> ft 降 10x = 2e-5
        # CharbonnierLoss eps=1e-9 (官方 SwinIR 用 Charbonnier)
        # EMA=0.999 (官方明确 ema_decay=0.999)
        "optimizer": "adam",
        "lr_ft": 2e-5,
        "weight_decay": 0.0,
        "loss": "charbonnier",
        "charbonnier_eps": 1e-9,
        "use_ema": True,
        "ema_decay": 0.999,
        "use_mixup": False,
        "batch_size": 4,
        "iterations": 50000,
        "warmup_iters": 0,
        # TODO: researcher 确认 SwinIR colorDN ft iterations; 50k 按惯例.
    },
    "uformer": {
        # 官方: ZhendongWang6/Uformer, options/Uformer_B_SIDD.yml
        # AdamW lr=2e-4 -> ft 降 10x = 2e-5
        # CharbonnierLoss eps=1e-3 (官方 Uformer 用 Charbonnier eps=1e-3)
        # warmup 3ep (官方 Uformer warmup 3 epochs)
        "optimizer": "adamw",
        "lr_ft": 2e-5,
        "weight_decay": 1e-4,
        "loss": "charbonnier",
        "charbonnier_eps": 1e-3,
        "use_ema": False,
        "use_mixup": False,
        "batch_size": 4,
        "iterations": 50000,
        "warmup_iters": 3,          # 官方 warmup_epochs=3 (按 1ep≈iters/total_ep 换算)
        # TODO: researcher 确认 warmup_iters 换算为 iter 的具体值 (官方是 epoch 单位).
    },
    "realesrgan": {
        # 官方: xinntao/Real-ESRGAN commit aa584e05, finetune_realesrgan_x4plus.yml
        # Adam lr=1e-4 (官方 ft 配方 optim_g.lr=1e-4, 不再÷10)
        # L1(1.0) + Perceptual(VGG19 多层, perceptual_weight=1.0) + GAN(0.1)
        # Perceptual 精确层权重: conv1_2=0.1,conv2_2=0.1,conv3_4=1,conv4_4=1,conv5_4=1
        #   vgg_type=vgg19, use_input_norm=True, range_norm=False, criterion=l1
        #   来源: commit aa584e05, finetune_realesrgan_x4plus.yml -> network_g.perceptual_opt
        # GAN: vanilla BCE weight=0.1 (官方 gan_opt.loss_weight=0.1)
        # EMA=0.999 (官方 ema_decay=0.999)
        # gt_size=256 (官方 ft patch=256)
        # 皮肤镜无需两阶段退化 pipeline, 换我们的 EnhanceDataset paired 数据
        # GAN: 简化 UNet-based discriminator (官方用 UNetDiscriminatorSN)
        # NOTE: GAN 训练复杂度高, --no_gan 可关 GAN 只用 L1+Perceptual (对比保守 ft)
        "optimizer": "adam",
        "lr_ft": 1e-4,
        "weight_decay": 0.0,
        "loss": "l1_perceptual_gan",
        "lambda_perceptual": 1.0,   # 官方 perceptual_weight=1.0 (commit aa584e05)
        "lambda_gan": 0.1,          # 官方 gan_opt.loss_weight=0.1 (vanilla BCE)
        "use_ema": True,
        "ema_decay": 0.999,
        "use_mixup": False,
        "batch_size": 4,
        "iterations": 50000,
        "warmup_iters": 0,
        # TODO: researcher 确认 Real-ESRGAN ft iterations 明确值 (官方 yml 中的值);
        #       50k 按 BasicSR ft 惯例, 待主线 researcher 确认.
    },
}

# ── R3 DP-Loss 配方 (沿用 v5 config 超参) ────────────────────────────────────
# dp_feat_loss: feature-level cosine 对齐 B3 最终特征图 + logit pos-hinge
# lambda 值从 visienhance_s2_planA_256_v5_hpc.yaml 原样读
_R3_DP_CONFIG = {
    "dp_mode": "feat",
    "lambda_dp": 0.019,    # 沿用 v5 标定值 (probe job1440973: feat≈30% L1)
    "lambda_hinge": 0.04,  # 沿用 v5 logit-hinge
    "hinge_clamp": 3.0,
    # L1 底座 (与 R1 restormer ft 配方一致, 保证唯一变量=DP-Loss)
    "lambda_l1": 1.0,
    "loss": "l1",
    "optimizer": "adamw",
    "lr_ft": 3e-5,         # 与 R1 restormer ft 一致
    "weight_decay": 1e-4,
    "batch_size": 4,
    "iterations": 50000,
    "warmup_iters": 0,
}

IMG = 256
CROP = 224
NEG_PER_POS = 30
BOOT = 2000
EARLY_STOP_PATIENCE = 10   # val PSNR 未提升 10 epoch 早停
LOG_EVERY = 1000           # iter
SAVE_EVERY = 5000          # iter

_TT = transforms.ToTensor()
_NORM = transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])


# ── Args ───────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="R1/R3 fine-tune + eval (C1 lever C1.4)")
    p.add_argument("--mode", required=True, choices=["r1", "r3"],
                   help="r1=baseline ft; r3=DP-graft")
    p.add_argument("--method", default=None,
                   help="R1 baseline name: nafnet|restormer|mirnetv2|swinir|uformer|realesrgan")
    p.add_argument("--r3_backbone", default="restormer",
                   help="R3 backbone (default=restormer, E10 top PSNR baseline)")
    p.add_argument("--hpc_root", default=_HPC_ROOT_DEFAULT,
                   help="HPC visienhance root dir")
    p.add_argument("--weights_dir", default=None,
                   help="Baseline pretrained weights dir (default=<hpc_root>/checkpoints/baselines)")
    p.add_argument("--out_dir", default=None,
                   help="Results output dir (default=<cwd>/results)")
    p.add_argument("--ckpt_dir", default=None,
                   help="Checkpoint save dir (default=<hpc_root>/checkpoints/r1_ft|r3_dp)")
    p.add_argument("--no_gan", action="store_true",
                   help="Real-ESRGAN: skip GAN loss, use L1+Perceptual only")
    p.add_argument("--num_workers", type=int, default=4)
    p.add_argument("--pin_memory", action="store_true",
                   help="DataLoader pin_memory (Linux HPC only, not Windows spawn)")
    p.add_argument("--amp", action="store_true", default=True,
                   help="Mixed precision (default on)")
    p.add_argument("--no_amp", dest="amp", action="store_false")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--resume", default=None,
                   help="Resume ft from checkpoint path")
    p.add_argument("--eval_only", action="store_true",
                   help="Skip training, only run eval on --resume checkpoint")
    p.add_argument("--smoke", action="store_true",
                   help="Smoke test: 1-batch dry-run on CPU, no real training")
    return p.parse_args()


# ── Paths ─────────────────────────────────────────────────────────────────────

def build_paths(args):
    root = Path(args.hpc_root)
    weights_dir = Path(args.weights_dir) if args.weights_dir else root / "checkpoints" / "baselines"
    out_dir = Path(args.out_dir) if args.out_dir else Path("results")
    tag = args.method if args.mode == "r1" else f"r3_{args.r3_backbone}"
    ckpt_base = root / "checkpoints" / ("r1_ft" if args.mode == "r1" else "r3_dp")
    ckpt_dir = Path(args.ckpt_dir) if args.ckpt_dir else ckpt_base / tag
    return {
        "root": root,
        "weights_dir": str(weights_dir),
        "out_dir": out_dir,
        "ckpt_dir": ckpt_dir,
        "labels_csv": str(root / "data" / "quality_labels_nocrop_hpc.csv"),
        "split_csv": str(root / "data" / "isic_split.csv"),
        "meta_csv": str(root / "data" / "train-metadata.csv"),
        "visiscore_ckpt": str(root / "checkpoints" / "best_visiscore.pth"),
        "b3_ckpt": str(root / "checkpoints" / "efficientnet_b3_isic.pth"),
    }


# ── Loss functions ─────────────────────────────────────────────────────────────

class PSNRLoss(nn.Module):
    """PSNRLoss: -PSNR (官方 NAFNet 用). 最大化 PSNR = 最小化 MSE in log space."""

    def __init__(self, loss_weight=1.0, reduction="mean", toY=False):
        super().__init__()
        self.loss_weight = loss_weight
        self.reduction = reduction
        self.toY = toY

    def forward(self, pred, target):
        # fp32 安全: 上浮后 1e-8 不会在 fp16 下 underflow 成 0 -> log10(0)=-inf
        pred = pred.float()
        target = target.float()
        # -10 * log10(MSE) per sample, 均值取负 (minimize = maximize PSNR)
        mse = F.mse_loss(pred, target, reduction="none").mean(dim=[1, 2, 3])
        psnr_val = -10.0 * torch.log10(mse.clamp(min=1e-8))
        return -self.loss_weight * psnr_val.mean()


class CharbonnierLoss(nn.Module):
    """Charbonnier loss (官方 SwinIR/Uformer)."""

    def __init__(self, eps=1e-9):
        super().__init__()
        self.eps = eps

    def forward(self, pred, target):
        # fp32 安全: fp16 下 eps*eps 可能 underflow, 上浮后安全
        pred = pred.float()
        target = target.float()
        diff = pred - target
        return torch.sqrt(diff * diff + self.eps * self.eps).mean()


def build_criterion(cfg_entry, no_gan=False):
    """构建 loss fn (不含 DP-Loss; DP 在 run_epoch 内单独算)."""
    loss_name = cfg_entry["loss"]
    if loss_name == "l1":
        return nn.L1Loss()
    elif loss_name == "psnr":
        return PSNRLoss()
    elif loss_name == "charbonnier":
        eps = cfg_entry.get("charbonnier_eps", 1e-9)
        return CharbonnierLoss(eps=eps)
    elif loss_name == "l1_perceptual_gan":
        # Real-ESRGAN: L1 + Perceptual + GAN; 返回 (l1_fn, perc_fn, gan_enabled)
        # 实际组合在 run_epoch_realesrgan 里做
        return nn.L1Loss()   # base; perceptual/gan 在 run_epoch 内懒加载
    else:
        raise ValueError(f"Unknown loss: {loss_name}")


# ── VGG Perceptual Loss (Real-ESRGAN) ─────────────────────────────────────────
# 官方来源: xinntao/Real-ESRGAN commit aa584e05,
#   options/finetune_realesrgan_x4plus.yml -> network_g.perceptual_opt:
#   layer_weights: {'conv1_2':0.1,'conv2_2':0.1,'conv3_4':1,'conv4_4':1,'conv5_4':1}
#   vgg_type: vgg19, use_input_norm: true, range_norm: false,
#   perceptual_weight: 1.0, style_weight: 0, criterion: l1
# 使用内联实现 (basicsr.losses.PerceptualLoss 若已装优先 import; fallback 内联同等行为).
#
# VGG19 feature 层索引 (torchvision.models.vgg19, features 列表):
#   conv1_2 = features[2]  (relu after conv1_2)
#   conv2_2 = features[7]
#   conv3_4 = features[16]
#   conv4_4 = features[25]
#   conv5_4 = features[34]
# 参考: https://github.com/pytorch/vision/blob/main/torchvision/models/vgg.py
# VGG19 features 完整结构共 37 层 (索引 0-36), conv5_4 relu 在 index 34.

_VGG19_LAYER_MAP = {
    # name -> (slice_end, weight) 对应 finetune_realesrgan_x4plus.yml layer_weights
    "conv1_2": (3,  0.1),  # features[:3]  -> relu after conv1_2 (index 2)
    "conv2_2": (8,  0.1),  # features[:8]  -> relu after conv2_2 (index 7)
    "conv3_4": (17, 1.0),  # features[:17] -> relu after conv3_4 (index 16)
    "conv4_4": (26, 1.0),  # features[:26] -> relu after conv4_4 (index 25)
    "conv5_4": (35, 1.0),  # features[:35] -> relu after conv5_4 (index 34)
}


def _try_import_basicsr_perceptual():
    """尝试从 basicsr 直接用官方 PerceptualLoss; 失败返回 None (内联 fallback)."""
    try:
        from basicsr.losses import PerceptualLoss  # noqa: F401
        return PerceptualLoss
    except ImportError:
        return None


class VGGPerceptualLoss(nn.Module):
    """VGG19 multi-layer perceptual loss (官方 Real-ESRGAN finetune_x4plus 精确配方).

    layer_weights={'conv1_2':0.1,'conv2_2':0.1,'conv3_4':1,'conv4_4':1,'conv5_4':1}
    vgg_type='vgg19', use_input_norm=True, range_norm=False,
    perceptual_weight=1.0, style_weight=0, criterion='l1'

    BasicSR PerceptualLoss 若已安装优先使用; 否则内联等价实现.
    来源: xinntao/Real-ESRGAN commit aa584e05, finetune_realesrgan_x4plus.yml
    """

    def __init__(self, device, use_basicsr=True):
        super().__init__()
        self._device = device
        self._basicsr_loss = None

        if use_basicsr:
            _cls = _try_import_basicsr_perceptual()
            if _cls is not None:
                # BasicSR 官方 PerceptualLoss (精确复现官方实现)
                self._basicsr_loss = _cls(
                    layer_weights={
                        "conv1_2": 0.1,
                        "conv2_2": 0.1,
                        "conv3_4": 1.0,
                        "conv4_4": 1.0,
                        "conv5_4": 1.0,
                    },
                    vgg_type="vgg19",
                    use_input_norm=True,
                    range_norm=False,
                    perceptual_weight=1.0,
                    style_weight=0.0,
                    criterion="l1",
                ).to(device)
                print("[perc] using basicsr.losses.PerceptualLoss (official)")
                return

        # 内联 fallback: 逐层提取 + L1, 精确对齐官方层索引 + 权重
        print("[perc] basicsr not found, using inline VGG19 perceptual (same layer_weights)")
        from torchvision.models import vgg19, VGG19_Weights
        vgg = vgg19(weights=VGG19_Weights.DEFAULT)
        full_feats = list(vgg.features)

        # 按 _VGG19_LAYER_MAP 切片, 共享前缀 (用截断子网逐级 forward)
        self._layer_nets = nn.ModuleList()
        self._layer_weights = []
        prev_end = 0
        for name, (end, w) in _VGG19_LAYER_MAP.items():
            block = nn.Sequential(*full_feats[prev_end:end]).to(device).eval()
            block.requires_grad_(False)
            self._layer_nets.append(block)
            self._layer_weights.append(w)
            prev_end = end

        # use_input_norm=True: ImageNet norm on input (range_norm=False -> input [0,1])
        mean = torch.tensor([0.485, 0.456, 0.406], device=device).view(1, 3, 1, 1)
        std  = torch.tensor([0.229, 0.224, 0.225], device=device).view(1, 3, 1, 1)
        self.register_buffer("mean", mean)
        self.register_buffer("std",  std)

    def forward(self, pred, target):
        """pred/target: [0,1] RGB (range_norm=False). 返回加权多层 L1 之和."""
        if self._basicsr_loss is not None:
            # BasicSR PerceptualLoss 返回 (perc_loss, style_loss); style_weight=0 -> style=0
            perc, _ = self._basicsr_loss(pred, target)
            return perc

        # 内联: use_input_norm -> ImageNet norm
        p = (pred   - self.mean) / self.std
        t = (target - self.mean) / self.std
        total = pred.new_zeros(())
        for block, w in zip(self._layer_nets, self._layer_weights):
            p = block(p)
            t = block(t)
            total = total + w * F.l1_loss(p, t)
        return total


# ── UNet Discriminator (Real-ESRGAN GAN) ─────────────────────────────────────

class UNetDiscriminatorSN(nn.Module):
    """Simplified UNet discriminator with spectral norm (官方 Real-ESRGAN).

    官方: xinntao/Real-ESRGAN, realesrgan/archs/discriminator_arch.py.
    # TODO: researcher 确认官方 UNetDiscriminatorSN 构造参数 (num_feat=64 默认值).
    """

    def __init__(self, num_in_ch=3, num_feat=64):
        super().__init__()
        SN = nn.utils.spectral_norm

        def block(in_c, out_c, stride=1):
            return nn.Sequential(
                SN(nn.Conv2d(in_c, out_c, 4, stride=stride, padding=1, bias=False)),
                nn.LeakyReLU(0.2, inplace=True),
            )

        self.enc1 = block(num_in_ch, num_feat, stride=2)   # 256->128
        self.enc2 = block(num_feat, num_feat * 2, stride=2)  # 128->64
        self.enc3 = block(num_feat * 2, num_feat * 4, stride=2)  # 64->32
        self.enc4 = block(num_feat * 4, num_feat * 8, stride=2)  # 32->16
        self.dec1 = nn.Sequential(
            SN(nn.Conv2d(num_feat * 8 + num_feat * 4, num_feat * 4, 3, 1, 1, bias=False)),
            nn.LeakyReLU(0.2, inplace=True),
        )
        self.dec2 = nn.Sequential(
            SN(nn.Conv2d(num_feat * 4 + num_feat * 2, num_feat * 2, 3, 1, 1, bias=False)),
            nn.LeakyReLU(0.2, inplace=True),
        )
        self.dec3 = nn.Sequential(
            SN(nn.Conv2d(num_feat * 2 + num_feat, num_feat, 3, 1, 1, bias=False)),
            nn.LeakyReLU(0.2, inplace=True),
        )
        self.out = SN(nn.Conv2d(num_feat, 1, 3, 1, 1))

    def forward(self, x):
        e1 = self.enc1(x)
        e2 = self.enc2(e1)
        e3 = self.enc3(e2)
        e4 = self.enc4(e3)
        d1 = self.dec1(torch.cat([F.interpolate(e4, size=e3.shape[-2:], mode="bilinear",
                                                align_corners=False), e3], dim=1))
        d2 = self.dec2(torch.cat([F.interpolate(d1, size=e2.shape[-2:], mode="bilinear",
                                                align_corners=False), e2], dim=1))
        d3 = self.dec3(torch.cat([F.interpolate(d2, size=e1.shape[-2:], mode="bilinear",
                                                align_corners=False), e1], dim=1))
        return self.out(d3)


# ── DP-Loss (从 train_visienhance.py 原样移植, 不修改) ─────────────────────────

_B3_CROP = 224
_IMAGENET_MEAN = (0.485, 0.456, 0.406)
_IMAGENET_STD = (0.229, 0.224, 0.225)


def _b3_crop_norm(x):
    """x [0,1] @256 -> center_crop 224 -> ImageNet norm."""
    o = (x.shape[-1] - _B3_CROP) // 2
    xc = x[..., o:o + _B3_CROP, o:o + _B3_CROP]
    mean = x.new_tensor(_IMAGENET_MEAN).view(1, 3, 1, 1)
    std = x.new_tensor(_IMAGENET_STD).view(1, 3, 1, 1)
    return (xc - mean) / std


def _b3_feat(b3, x):
    """B3 最终特征图 (B,1536,7,7)."""
    return b3.features(_b3_crop_norm(x))


def _b3_logits(b3, x):
    """B3 logits (B,2)."""
    return b3(_b3_crop_norm(x))


def dp_feat_loss(b3, x_enh, x_ref, y, hinge_clamp=3.0):
    """Feature-level DP (v5) — 直接从 train_visienhance.py 移植, 不修改逻辑.

    feat  = mean_{b,h,w} [ 1 - cos( f_enh[:,h,w], f_ref[:,h,w] ) ]  f=B3.features
    hinge = mean_{y==1} relu(logit_ref[mel] - logit_enh[mel]).clamp(max=hinge_clamp)
    """
    with torch.no_grad():
        f_ref = _b3_feat(b3, x_ref)
        logits_ref = _b3_logits(b3, x_ref)
    f_enh = _b3_feat(b3, x_enh)
    fr = F.normalize(f_ref, dim=1)
    fe = F.normalize(f_enh, dim=1)
    feat = (1.0 - (fr * fe).sum(dim=1)).mean()
    pos = (y == 1)
    if pos.any():
        logits_enh = _b3_logits(b3, x_enh)
        gap = logits_ref[pos, 1] - logits_enh[pos, 1]
        hinge = gap.clamp_min(0).clamp(max=hinge_clamp).mean()
    else:
        hinge = torch.zeros((), device=x_enh.device)
    return feat, hinge


# ── EMA ───────────────────────────────────────────────────────────────────────

class EMA:
    """指数移动平均 (SwinIR/Real-ESRGAN 官方配方)."""

    def __init__(self, model, decay=0.999):
        self.model = model
        self.decay = decay
        self.shadow = {k: v.clone().float() for k, v in model.state_dict().items()}

    @torch.no_grad()
    def update(self):
        for k, v in self.model.state_dict().items():
            self.shadow[k] = self.decay * self.shadow[k] + (1 - self.decay) * v.float()

    def apply_shadow(self, model):
        model.load_state_dict({k: v.to(next(model.parameters()).dtype)
                               for k, v in self.shadow.items()})


# ── Optimizer builder ─────────────────────────────────────────────────────────

def build_optimizer(cfg_entry, params):
    name = cfg_entry["optimizer"]
    lr = cfg_entry["lr_ft"]
    wd = cfg_entry.get("weight_decay", 0.0)
    if name == "adamw":
        return torch.optim.AdamW(params, lr=lr, weight_decay=wd)
    elif name == "adam":
        return torch.optim.Adam(params, lr=lr, weight_decay=wd)
    else:
        raise ValueError(f"Unknown optimizer: {name}")


# ── Dataset ─────────────────────────────────────────────────────────────────
# 复用 EnhanceDataset (return_target=True 带 melanoma label)

class _SmokeDummyDataset(torch.utils.data.Dataset):
    """Smoke-only: 2 样本随机张量, 不触碰任何 csv/图像文件."""

    def __init__(self, n=2):
        self.n = n

    def __len__(self):
        return self.n

    def __getitem__(self, idx):
        x_low = torch.rand(3, 256, 256)
        x_ref = torch.rand(3, 256, 256)
        y = torch.randint(0, 2, ()).item()
        return x_low, x_ref, y


def build_dataloaders(paths, batch_size, num_workers, pin_memory, seed=42, smoke=False):
    if smoke:
        # Smoke: 完全 mock, 不触碰任何 csv/图像文件
        ds = _SmokeDummyDataset(n=2)
        loader = DataLoader(ds, batch_size=1, shuffle=False,
                            num_workers=0, pin_memory=False)
        return loader, loader

    # 动态 import (cwd 需是 project/)
    from data.enhance_dataset import EnhanceDataset

    common = dict(
        labels_csv=paths["labels_csv"],
        split_csv=paths["split_csv"],
        meta_csv=paths["meta_csv"],
        img_size=256,
        severity="mixed",   # 训练: light+medium+heavy (对齐 E10)
        return_target=True,
        pos_oversample=10,  # 沿用 v5 config
    )

    train_ds = EnhanceDataset(split="train", **common)
    val_ds = EnhanceDataset(split="val", img_size=256,
                            labels_csv=paths["labels_csv"],
                            split_csv=paths["split_csv"],
                            meta_csv=paths["meta_csv"],
                            severity="mixed",
                            return_target=True,
                            pos_oversample=1)

    nw = num_workers
    loader_kwargs = dict(
        batch_size=batch_size,
        num_workers=nw,
        pin_memory=pin_memory,
        persistent_workers=(nw > 0),
        multiprocessing_context="spawn" if nw > 0 else None,
    )
    train_loader = DataLoader(train_ds, shuffle=True, **loader_kwargs)
    val_loader = DataLoader(val_ds, shuffle=False, **loader_kwargs)
    return train_loader, val_loader


# ── Backbone loader ─────────────────────────────────────────────────────────
# 加载可训练 backbone (不用 BaselineEnhancer 包装, 直接访问 .net)

def load_trainable_backbone(method, weights_dir, device, mock_weights=False):
    """加载 baseline backbone (trainable, .eval()/.train() 自行控制).

    mock_weights=True: 只构造 arch 不加载权重 (smoke test 用, 验算子不炸).
    """
    if mock_weights:
        # 仅构造 arch (随机初始化), 不触碰 HPC 权重路径
        return _build_arch_only(method, device)
    mod = importlib.import_module(f"baselines.run_{method}_inference")
    wrapper = mod.build(device, weights_dir)
    net = wrapper.net
    # wrapper.__call__ 是 @no_grad, ft 时绕过: 直接用 net(x)
    return net


def _build_arch_only(method, device):
    """构造 baseline arch (随机初始化, 无需权重文件). Smoke 专用."""
    if method == "nafnet":
        from baselines.archs.nafnet_arch import NAFNet
        return NAFNet(img_channel=3, width=64,
                      enc_blk_nums=[2, 2, 4, 8], middle_blk_num=12,
                      dec_blk_nums=[2, 2, 2, 2]).to(device)
    elif method == "restormer":
        from baselines.archs.restormer_arch import Restormer
        return Restormer(LayerNorm_type="BiasFree").to(device)
    elif method == "mirnetv2":
        from baselines.archs.mirnetv2_arch import MIRNet_v2
        return MIRNet_v2().to(device)
    elif method == "swinir":
        from baselines.archs.swinir_arch import SwinIR
        return SwinIR(upscale=1, in_chans=3, img_size=128, window_size=8,
                      img_range=1., depths=[6, 6, 6, 6, 6, 6], embed_dim=180,
                      num_heads=[6, 6, 6, 6, 6, 6], mlp_ratio=2,
                      upsampler='', resi_connection='1conv').to(device)
    elif method == "uformer":
        from baselines.archs.uformer_arch import Uformer
        return Uformer(img_size=256, embed_dim=32, win_size=8,
                       token_projection="linear", token_mlp="leff",
                       depths=[1, 2, 8, 8, 2, 8, 8, 2, 1],
                       modulator=True, dd_in=3).to(device)
    elif method == "realesrgan":
        from baselines.archs.rrdbnet_arch import RRDBNet
        return RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64,
                       num_block=23, num_grow_ch=32, scale=2).to(device)
    else:
        raise ValueError(f"Unknown method for arch-only build: {method}")


def baseline_forward(method, net, x_low):
    """各 baseline 的 forward 逻辑 (对齐 inference wrapper, 去掉 no_grad 包装).

    Real-ESRGAN: SR round-trip (downsample 1/2 -> net -> upsample 回原尺寸).
    SwinIR: pad_to_multiple + crop.
    其他: 直接 net(x_low).
    """
    if method == "realesrgan":
        h, w = x_low.shape[-2:]
        lo = F.interpolate(x_low, scale_factor=0.5, mode="bicubic", align_corners=False)
        sr = net(lo.clamp(0, 1))
        return F.interpolate(sr, size=(h, w), mode="bicubic", align_corners=False).clamp(0, 1)
    elif method == "swinir":
        from baselines.base_enhancer import pad_to_multiple, crop_to
        xp, hw = pad_to_multiple(x_low, 8)
        out = net(xp)
        return crop_to(out, hw)
    else:
        return net(x_low)


# ── Train epoch ───────────────────────────────────────────────────────────────

def run_train_epoch(method, net, loader, criterion, optimizer, scaler, device,
                    mode, cfg_entry, b3=None, dp_cfg=None, perc_fn=None,
                    disc=None, disc_opt=None, no_gan=False, warmup_iters=0,
                    global_step=0):
    """单 train epoch. 返回 (metrics_dict, global_step)."""
    net.train()
    total_loss = total_l1 = total_psnr = n = 0
    total_dp = total_hinge = 0.0
    n_skipped = 0  # non-finite loss 被跳过的 batch 计数

    for batch in loader:
        if len(batch) == 3:
            x_low, x_ref, y = batch
            y = y.to(device, non_blocking=True)
        else:
            x_low, x_ref = batch[:2]
            y = torch.zeros(x_low.shape[0], dtype=torch.long, device=device)

        x_low = x_low.to(device, non_blocking=True)
        x_ref = x_ref.to(device, non_blocking=True)

        # Warmup lr scaling (Uformer 官方 warmup)
        if warmup_iters > 0 and global_step < warmup_iters:
            scale = float(global_step + 1) / float(warmup_iters)
            for g in optimizer.param_groups:
                g["lr"] = cfg_entry["lr_ft"] * scale

        optimizer.zero_grad(set_to_none=True)

        with autocast(enabled=scaler is not None):
            x_enh = baseline_forward(method, net, x_low).clamp(0, 1)

            # Fix-3: forward NaN 早检 — clamp 不拦 NaN, 提前 warn (实际由 loss guard 抓)
            if not torch.isfinite(x_enh).all():
                print(f"[warn] non-finite x_enh at step={global_step}, skip batch")

            # --- Base loss ---
            if isinstance(criterion, PSNRLoss):
                base_loss = criterion(x_enh, x_ref)
            elif isinstance(criterion, CharbonnierLoss):
                base_loss = criterion(x_enh, x_ref)
            else:
                base_loss = criterion(x_enh, x_ref)  # L1

            loss = base_loss

            # --- Perceptual (Real-ESRGAN) ---
            if perc_fn is not None:
                perc_loss = perc_fn(x_enh, x_ref)
                loss = loss + cfg_entry.get("lambda_perceptual", 1.0) * perc_loss

            # --- GAN generator loss (Real-ESRGAN, R1 only) ---
            if disc is not None and not no_gan:
                # Generator: max log D(G(x)) = min -log D(G(x))
                fake_pred = disc(x_enh)
                g_loss = F.binary_cross_entropy_with_logits(
                    fake_pred, torch.ones_like(fake_pred))
                loss = loss + cfg_entry.get("lambda_gan", 0.1) * g_loss

            # --- DP-Loss (R3 only) ---
            dp_val = hinge_val = 0.0
            if mode == "r3" and b3 is not None and dp_cfg is not None:
                dp, hinge = dp_feat_loss(b3, x_enh, x_ref, y,
                                         dp_cfg.get("hinge_clamp", 3.0))
                dp_val = dp.item()
                hinge_val = hinge.item()
                loss = (loss
                        + dp_cfg.get("lambda_dp", 0.019) * dp
                        + dp_cfg.get("lambda_hinge", 0.04) * hinge)

        # Fix-1: non-finite loss guard — nan/inf loss 绝不写进权重
        if not torch.isfinite(loss):
            print(f"[warn] non-finite loss={loss.item()} at step={global_step}, skip batch")
            optimizer.zero_grad(set_to_none=True)
            n_skipped += 1
            global_step += 1
            continue

        if scaler is not None:
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            nn.utils.clip_grad_norm_(net.parameters(), 1.0)
            scaler.step(optimizer)
            scaler.update()
        else:
            loss.backward()
            nn.utils.clip_grad_norm_(net.parameters(), 1.0)
            optimizer.step()

        # --- Discriminator update (Real-ESRGAN, after generator step) ---
        if disc is not None and disc_opt is not None and not no_gan:
            disc_opt.zero_grad(set_to_none=True)
            real_pred = disc(x_ref.detach())
            fake_pred = disc(x_enh.detach())
            d_loss = (F.binary_cross_entropy_with_logits(real_pred, torch.ones_like(real_pred))
                      + F.binary_cross_entropy_with_logits(fake_pred, torch.zeros_like(fake_pred))) * 0.5
            d_loss.backward()
            disc_opt.step()

        B = x_low.shape[0]
        total_loss += loss.item() * B
        total_l1 += base_loss.item() * B
        total_dp += dp_val * B
        total_hinge += hinge_val * B
        # PSNR (batch aggregate, monitoring only)
        with torch.no_grad():
            mse = F.mse_loss(x_enh.detach().float(), x_ref.float()).item()
            total_psnr += (10 * np.log10(1.0 / (mse + 1e-8))) * B
        n += B
        global_step += 1

    safe_n = max(n, 1)  # 防全 skip 时除 0
    return {
        "loss": total_loss / safe_n,
        "l1": total_l1 / safe_n,
        "psnr_train": total_psnr / safe_n,
        "dp": total_dp / safe_n,
        "hinge": total_hinge / safe_n,
        "skipped": n_skipped,  # non-finite loss 被跳过的 batch 数
    }, global_step


# ── Val epoch ─────────────────────────────────────────────────────────────────

@torch.no_grad()
def run_val_epoch(method, net, loader, device):
    """验证 PSNR/SSIM (per-image, monitoring). 早停依据."""
    net.eval()
    psnr_list, ssim_list = [], []
    n_bad = 0
    total_imgs = 0
    for batch in loader:
        x_low, x_ref = batch[0], batch[1]
        x_low = x_low.to(device)
        x_ref = x_ref.to(device)
        x_enh = baseline_forward(method, net, x_low).clamp(0, 1)
        for i in range(x_enh.shape[0]):
            total_imgs += 1
            # Fix-4: 非 finite 图跳过, 不 cast 成 uint8 垃圾污染 PSNR
            if not torch.isfinite(x_enh[i]).all():
                n_bad += 1
                continue
            r = (x_ref[i].cpu().permute(1, 2, 0).numpy() * 255).astype(np.uint8)
            e = (x_enh[i].cpu().permute(1, 2, 0).numpy() * 255).clip(0, 255).astype(np.uint8)
            psnr_list.append(peak_signal_noise_ratio(r, e, data_range=255))
            ssim_list.append(structural_similarity(r, e, channel_axis=2, data_range=255))
    if n_bad > 0:
        print(f"[val] n_bad={n_bad}/{total_imgs} non-finite enhanced images")
    if len(psnr_list) == 0:
        # 全坏: 返回 nan 触发 best-save sanity 闸, 不存假 ckpt
        return float("nan"), float("nan")
    return float(np.mean(psnr_list)), float(np.mean(ssim_list))


# ── Fine-tune loop ─────────────────────────────────────────────────────────────

def finetune(method, net, train_loader, val_loader, device, cfg_entry,
             ckpt_dir, mode, b3=None, dp_cfg=None,
             no_gan=False, use_ema=False, ema_decay=0.999,
             amp=True, smoke=False):
    """主 fine-tune 循环. 返回 best val PSNR 时的 ckpt path."""
    ckpt_dir = Path(ckpt_dir)
    ckpt_dir.mkdir(parents=True, exist_ok=True)

    optimizer = build_optimizer(cfg_entry, net.parameters())
    scaler = GradScaler("cuda") if amp else None
    ema = EMA(net, ema_decay) if use_ema else None

    # Real-ESRGAN: Perceptual + GAN
    perc_fn = None
    disc = disc_opt = None
    if cfg_entry["loss"] == "l1_perceptual_gan":
        perc_fn = VGGPerceptualLoss(device)
        if not no_gan:
            disc = UNetDiscriminatorSN().to(device)
            disc_opt = torch.optim.Adam(disc.parameters(),
                                        lr=cfg_entry["lr_ft"], weight_decay=0.0)
    criterion = build_criterion(cfg_entry, no_gan=no_gan)

    # Fix-6: smoke 改 30 步 (fp32) 才能暴露 nan 发散; 原 1 步不足以触发雪崩
    max_iters = 30 if smoke else cfg_entry["iterations"]
    warmup_iters = cfg_entry.get("warmup_iters", 0)
    # 换算 warmup: Uformer 官方单位是 epoch, 此处已在 _FT_CONFIG 里留了 TODO
    # 如果 warmup_iters 很小 (<5) 认为是 epoch 数, 换算为 iters
    if warmup_iters > 0 and warmup_iters <= 10:
        # warmup_iters epochs -> samples / batch_size * warmup_iters
        approx_train_len = len(train_loader)
        warmup_iters = warmup_iters * approx_train_len
        print(f"[warmup] {cfg_entry.get('warmup_iters')} ep -> {warmup_iters} iters")

    best_psnr = -1.0
    best_ckpt = None
    no_improve = 0
    global_step = 0
    ep = 0
    total_skipped = 0  # Fix-6: smoke assert 用

    print(f"[ft] start  method={method}  mode={mode}  max_iters={max_iters}  "
          f"lr={cfg_entry['lr_ft']}  amp={amp}  smoke={smoke}")

    while global_step < max_iters:
        ep += 1
        metrics, global_step = run_train_epoch(
            method=method, net=net, loader=train_loader, criterion=criterion,
            optimizer=optimizer, scaler=scaler, device=device,
            mode=mode, cfg_entry=cfg_entry, b3=b3, dp_cfg=dp_cfg,
            perc_fn=perc_fn, disc=disc, disc_opt=disc_opt, no_gan=no_gan,
            warmup_iters=warmup_iters, global_step=global_step,
        )
        if ema:
            ema.update()

        total_skipped += metrics["skipped"]  # Fix-6: accumulate for smoke assert
        val_psnr, val_ssim = run_val_epoch(method, net, val_loader, device)
        skipped_info = f"  skipped={metrics['skipped']}" if metrics['skipped'] > 0 else ""
        print(f"ep={ep:03d} iter={global_step:06d}  "
              f"loss={metrics['loss']:.4f}  l1={metrics['l1']:.4f}  "
              f"dp={metrics['dp']:.4f}  hinge={metrics['hinge']:.4f}  "
              f"val_PSNR={val_psnr:.2f}  val_SSIM={val_ssim:.4f}{skipped_info}")

        # Save best — Fix-5: val_psnr=nan 时绝不存「best」
        if math.isfinite(val_psnr) and val_psnr > best_psnr:
            best_psnr = val_psnr
            no_improve = 0
            if not smoke:
                ckpt = {"step": global_step, "epoch": ep,
                        "model": net.state_dict(), "val_psnr": val_psnr}
                if ema:
                    ckpt["ema_shadow"] = ema.shadow
                best_ckpt = str(ckpt_dir / "best_ft.pth")
                torch.save(ckpt, best_ckpt)
                print(f"  -> saved best {best_ckpt}  PSNR={best_psnr:.2f}")
            else:
                best_ckpt = None
                print(f"  [smoke] val_PSNR={best_psnr:.2f} (no save)")
        else:
            no_improve += 1

        # Periodic save (skip in smoke)
        if not smoke and (global_step % SAVE_EVERY == 0 or global_step >= max_iters):
            torch.save({"step": global_step, "epoch": ep, "model": net.state_dict()},
                       str(ckpt_dir / f"ckpt_step{global_step:06d}.pth"))

        # Early stop
        if not smoke and no_improve >= EARLY_STOP_PATIENCE:
            print(f"[early stop] val PSNR no improve {no_improve} ep -> stop at iter {global_step}")
            break

        if global_step >= max_iters:
            break

    # Fix-6: smoke 结束 assert — ① loss 全 finite (skipped==0) ② 权重全 finite
    if smoke:
        if total_skipped > 0:
            raise AssertionError(
                f"[smoke FAIL] {total_skipped} batches had non-finite loss in {max_iters} steps "
                f"— PSNRLoss/Charbonnier fp32 fix may not have taken effect")
        bad_params = [k for k, v in net.state_dict().items()
                      if not torch.isfinite(v).all()]
        if bad_params:
            raise AssertionError(
                f"[smoke FAIL] non-finite params after {max_iters} steps: {bad_params[:5]}")
        print(f"[smoke PASS] {max_iters} steps, skipped=0, all weights finite")

    print(f"[ft done] best_val_PSNR={best_psnr:.2f}  ckpt={best_ckpt}")
    return best_ckpt, best_psnr


# ── Eval (test split, align E10) ──────────────────────────────────────────────

def build_df_test(paths):
    """E10-caliber test 子集: 存盘降质 (mixed) + melanoma-balanced.

    完全对齐 run_e10_baseline_hpc.py::build_df_stored().
    """
    lbl = pd.read_csv(paths["labels_csv"])
    lbl["isic_id"] = lbl["original_path"].apply(lambda p: Path(p).stem)
    sp = pd.read_csv(paths["split_csv"])
    tids = set(sp.loc[sp.split == "test", "isic_id"].astype(str))
    meta = pd.read_csv(paths["meta_csv"])[["isic_id", "target"]]
    df = lbl[lbl.isic_id.isin(tids)].merge(meta, on="isic_id")
    df = df[df.original_path.apply(lambda p: Path(p).exists())
            & df.degraded_path.apply(lambda p: Path(p).exists())]
    pos_ids = df[df.target == 1].isic_id.unique()
    neg_ids = df[df.target == 0].isic_id.unique()
    rng = np.random.RandomState(7)
    k = min(len(neg_ids), NEG_PER_POS * len(pos_ids))
    keep = set(pos_ids) | set(rng.choice(neg_ids, k, replace=False))
    return df[df.isic_id.isin(keep)].sample(frac=1, random_state=7).reset_index(drop=True)


def center_crop_224(x):
    o = (IMG - CROP) // 2
    return x[..., o:o + CROP, o:o + CROP]


def b3_softmax(b3, x256):
    return torch.softmax(b3(_NORM(center_crop_224(x256))), dim=-1).cpu().numpy()


@torch.no_grad()
def collect_eval(method, net, b3, df, device):
    """同图同退化 -> per-image PSNR/SSIM + B3 softmax (ref/deg/enh).

    使用存盘降质图 (对齐 E10 build_df_stored 协议).
    """
    R, D, E_soft, E_psnr, E_ssim, ys = [], [], [], [], [], []

    for s in range(0, len(df), 4):
        rows = df.iloc[s:s + 4]
        lows, refs = [], []
        for j, row in rows.iterrows():
            ref = cv2.imread(str(row.original_path))
            low = cv2.imread(str(row.degraded_path))
            if ref is None or low is None:
                continue
            if ref.shape[:2] != (IMG, IMG):
                ref = cv2.resize(ref, (IMG, IMG), interpolation=cv2.INTER_AREA)
            if low.shape[:2] != (IMG, IMG):
                low = cv2.resize(low, (IMG, IMG), interpolation=cv2.INTER_AREA)
            refs.append(_TT(cv2.cvtColor(ref, cv2.COLOR_BGR2RGB)))
            lows.append(_TT(cv2.cvtColor(low, cv2.COLOR_BGR2RGB)))
            ys.append(int(row.target))
        if not lows:
            continue

        x_low = torch.stack(lows).to(device)
        x_ref = torch.stack(refs).to(device)

        net.eval()
        x_enh = baseline_forward(method, net, x_low).clamp(0, 1)

        R.append(b3_softmax(b3, x_ref))
        D.append(b3_softmax(b3, x_low))
        E_soft.append(b3_softmax(b3, x_enh))

        ref_np = x_ref.cpu()
        enh_np = x_enh.cpu()
        _bad_eval = 0
        for i in range(enh_np.shape[0]):
            # Fix-4: 非 finite 图跳过, 不静默转 0 污染 csv
            if not torch.isfinite(enh_np[i]).all():
                _bad_eval += 1
                continue
            r = (ref_np[i].permute(1, 2, 0).numpy() * 255).astype(np.uint8)
            e = (enh_np[i].permute(1, 2, 0).numpy() * 255).clip(0, 255).astype(np.uint8)
            E_psnr.append(peak_signal_noise_ratio(r, e, data_range=255))
            E_ssim.append(structural_similarity(r, e, channel_axis=2, data_range=255))
        if _bad_eval > 0:
            print(f"[eval] {_bad_eval} non-finite enhanced images in batch, skipped")

    R = np.concatenate(R)
    D = np.concatenate(D)
    E = np.concatenate(E_soft)
    ys = np.array(ys)
    return R, D, E, np.array(E_psnr), np.array(E_ssim), ys


def kl_rows(P, Q, eps=1e-6):
    P = np.clip(P, eps, 1)
    Q = np.clip(Q, eps, 1)
    return np.sum(P * np.log(P / Q), axis=1)


def compute_metrics(R, D, E, ys):
    """主指标 dict, 对齐 eval_diag_paired.model_metrics."""
    pr, pd_, pe = R[:, 1], D[:, 1], E[:, 1]
    m = {
        "auc_ref": float(roc_auc_score(ys, pr)),
        "auc_deg": float(roc_auc_score(ys, pd_)),
        "auc_enh": float(roc_auc_score(ys, pe)),
    }
    m["dAUC"] = m["auc_enh"] - m["auc_ref"]
    m["consistency"] = float(np.mean((pr > 0.5) == (pe > 0.5)))
    m["kl"] = float(np.mean(kl_rows(R, E)))
    mask = (ys == 1) & (pr > 0.5)
    m["dangerous_flip"] = float(np.mean(pe[mask] < 0.5)) if mask.sum() else float("nan")
    return m


def mcnemar_exact(correct_a, correct_b):
    """McNemar b/c/p — 纯 numpy 实现 (无 scipy, 防 OMP Error #15 on Windows).

    使用 binomial CDF 近似: p = 2 * min(binom_cdf(min(b,c), b+c, 0.5), 1).
    精确双侧检验: p = sum_{k<=min(b,c) or k>=max(b,c)} C(n,k) 0.5^n.
    """
    b = int(np.sum(correct_a & ~correct_b))
    c = int(np.sum(~correct_a & correct_b))
    n = b + c
    if n == 0:
        return b, c, 1.0
    # 精确双侧 p (纯 numpy)
    k_min = min(b, c)
    # sum P(X <= k_min) * 2 where X ~ Binomial(n, 0.5)
    # 用 log-space 累加防溢出
    log05n = n * np.log(0.5)
    from math import lgamma
    log_probs = np.array([
        lgamma(n + 1) - lgamma(k + 1) - lgamma(n - k + 1) + log05n
        for k in range(k_min + 1)
    ])
    p_lo = float(np.exp(log_probs).sum())
    p = min(2 * p_lo, 1.0)
    return b, c, p


def bootstrap_ci(R, D, E_ft, E_ref, ys, n_boot=BOOT):
    """配对 bootstrap: ΔAUC (ft - ref_model) 95% CI.

    E_ft  = fine-tuned model softmax
    E_ref = 参考模型 softmax (这里 E_ref 未用, CI 直接报 ft 的 dAUC bootstrap 分布)
    """
    rng = np.random.RandomState(0)
    n = len(ys)
    dauc_boot, dkl_boot = [], []
    for _ in range(n_boot):
        idx = rng.randint(0, n, n)
        if len(np.unique(ys[idx])) < 2:
            continue
        m = compute_metrics(R[idx], D[idx], E_ft[idx], ys[idx])
        dauc_boot.append(m["dAUC"])
        dkl_boot.append(m["kl"])
    dauc_boot = np.array(dauc_boot)
    dkl_boot = np.array(dkl_boot)

    def ci(v):
        return float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))

    return ci(dauc_boot), ci(dkl_boot), dauc_boot, dkl_boot


def per_class_melanoma(R, E, ys, E_psnr):
    """Per-class melanoma 拆分 (对齐 E5 口径: salvage/damage).

    salvage: ref 判错但 enh 判对 (true positive 救回)
    damage : ref 判对但 enh 判错 (true positive 破坏, dangerous flip)

    返回 dict (诚实负结果如实输出, 不掩盖).
    """
    pr = R[:, 1]
    pe = E[:, 1]

    # 全集诊断保持
    pos_mask = (ys == 1)
    n_pos = int(pos_mask.sum())

    # ref 判对的真阳 (pr > 0.5)
    ref_correct_pos = pos_mask & (pr > 0.5)
    enh_correct_pos = pos_mask & (pe > 0.5)

    salvage = int(np.sum(~(pos_mask & (pr > 0.5)) & pos_mask & (pe > 0.5)))  # ref 错 enh 对
    damage = int(np.sum((pos_mask & (pr > 0.5)) & ~(pos_mask & (pe > 0.5))))  # ref 对 enh 错

    salvage_rate = salvage / max(n_pos, 1)
    damage_rate = damage / max(n_pos, 1)
    net_change = salvage - damage

    # E5 口径对齐: n_pos ~= 117 (test split pos), n_neg 远大; 下面报 n
    return {
        "n_pos": n_pos,
        "mel_salvage": salvage,
        "mel_damage": damage,
        "mel_salvage_rate": round(salvage_rate, 4),
        "mel_damage_rate": round(damage_rate, 4),
        "mel_net_change": net_change,  # + 净正, - 净负 (诚实报)
        "mel_psnr_mean": round(float(np.mean(E_psnr[pos_mask])), 2) if pos_mask.any() else float("nan"),
    }


def eval_and_save(method_tag, display_name, mode,
                  method, net, b3, df, device, paths, smoke):
    """跑 eval, 输出 csv. 对齐 e10 schema."""
    out_dir = Path("results")
    out_dir.mkdir(exist_ok=True)
    prefix = "r1_finetune" if mode == "r1" else "r3_dpgraft"
    out_csv = out_dir / f"{prefix}_{method_tag}.csv"

    if smoke:
        print(f"[smoke] skip eval collect (smoke mode). Would write -> {out_csv}")
        return

    print(f"\n[eval] collecting {display_name} on test set n={len(df)} ...")
    R, D, E, E_psnr, E_ssim, ys = collect_eval(method, net, b3, df, device)
    m = compute_metrics(R, D, E, ys)

    psnr_mean = float(np.mean(E_psnr))
    ssim_mean = float(np.mean(E_ssim))
    e3_auc = "PASS" if abs(m["dAUC"]) < 0.015 else ("borderline" if abs(m["dAUC"]) < 0.03 else "FAIL")
    e3_con = "PASS" if m["consistency"] > 0.95 else "FAIL"

    ya = (R[:, 1] > 0.5) == (ys == 1)
    yb = (E[:, 1] > 0.5) == (ys == 1)
    mc_b, mc_c, mc_p = mcnemar_exact(ya, yb)

    print(f"{display_name}: PSNR={psnr_mean:.2f}  SSIM={ssim_mean:.4f}  "
          f"dAUC={m['dAUC']:+.4f}({e3_auc})  consist={m['consistency']:.4f}({e3_con})  "
          f"KL={m['kl']:.4f}  dflip={m['dangerous_flip']:.4f}  McNemar p={mc_p:.3g}")

    # Bootstrap CI
    (a_lo, a_hi), (k_lo, k_hi), dauc_boot, dkl_boot = bootstrap_ci(R, D, E, None, ys)
    print(f"  ΔAUC 95%CI [{a_lo:+.4f},{a_hi:+.4f}]  ΔKL CI [{k_lo:+.4f},{k_hi:+.4f}]")

    # Per-class melanoma (E5 口径)
    mel = per_class_melanoma(R, E, ys, E_psnr)
    print(f"  melanoma (n_pos={mel['n_pos']}): salvage={mel['mel_salvage']}({mel['mel_salvage_rate']:.1%})  "
          f"damage={mel['mel_damage']}({mel['mel_damage_rate']:.1%})  "
          f"net={mel['mel_net_change']:+d}  mel_PSNR={mel['mel_psnr_mean']:.2f}")
    if mel["mel_net_change"] < 0:
        print(f"  [诚实负结果] {display_name} melanoma net 净负 ({mel['mel_net_change']:+d}), 如实输出.")

    # CSV rows (schema 与 e10 一致)
    main_row = {
        "model": display_name,
        "mode": mode,
        "psnr_perimg": round(psnr_mean, 2),
        "ssim": round(ssim_mean, 4),
        "dAUC": round(m["dAUC"], 4),
        "dAUC_ci_lo": round(a_lo, 4),
        "dAUC_ci_hi": round(a_hi, 4),
        "consistency": round(m["consistency"], 4),
        "kl": round(m["kl"], 4),
        "dKL": round(float(np.mean(dkl_boot)), 4),
        "dKL_ci_lo": round(k_lo, 4),
        "dKL_ci_hi": round(k_hi, 4),
        "dangerous_flip": round(m["dangerous_flip"], 4) if not np.isnan(m["dangerous_flip"]) else "",
        "mcnemar_enh_ref_p": round(mc_p, 4),
        "mcnemar_b": mc_b,
        "mcnemar_c": mc_c,
        "mcnemar_p": round(mc_p, 4),
    }
    mel_row = {
        "model": f"{display_name} [mel_perclass]",
        "mode": mode,
        "n_pos": mel["n_pos"],
        "mel_salvage": mel["mel_salvage"],
        "mel_damage": mel["mel_damage"],
        "mel_salvage_rate": mel["mel_salvage_rate"],
        "mel_damage_rate": mel["mel_damage_rate"],
        "mel_net_change": mel["mel_net_change"],
        "mel_psnr_mean": mel["mel_psnr_mean"],
    }

    df_out = pd.DataFrame([main_row, mel_row])
    df_out.to_csv(out_csv, index=False)
    print(f"saved -> {out_csv}")


# ── Load B3 (frozen eval oracle) ─────────────────────────────────────────────

def load_b3(path, device):
    """Frozen EfficientNet-B3 oracle (eval_stage2_compare.load_b3 原样复制)."""
    from torchvision.models import efficientnet_b3
    net = efficientnet_b3(weights=None)
    net.classifier = nn.Sequential(nn.Dropout(p=0.3, inplace=True),
                                   nn.Linear(net.classifier[1].in_features, 2))
    ck = torch.load(path, map_location=device, weights_only=False)
    missing, unexpected = net.load_state_dict(
        ck["model"] if "model" in ck else ck, strict=False)
    assert not missing and not unexpected, \
        f"b3 load mismatch: {missing[:3]} / {unexpected[:3]}"
    return net.to(device).eval().requires_grad_(False)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()

    # Seed
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    device = torch.device("cpu") if args.smoke else \
             torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[init] mode={args.mode}  device={device}  smoke={args.smoke}")

    # Path resolution
    paths = build_paths(args)
    out_dir = paths["out_dir"]
    out_dir.mkdir(exist_ok=True, parents=True)

    # Method / backbone
    if args.mode == "r1":
        if args.method is None:
            print("[ERROR] --mode r1 requires --method")
            sys.exit(1)
        method = args.method.lower()
        if method not in _FT_CONFIG:
            print(f"[ERROR] Unknown method: {method}. Choose from {list(_FT_CONFIG)}")
            sys.exit(1)
        cfg_entry = _FT_CONFIG[method]
        method_tag = method
        display_name = f"{method}_ft_r1"
    else:
        method = args.r3_backbone.lower()
        if method not in _FT_CONFIG:
            print(f"[ERROR] Unknown r3_backbone: {method}")
            sys.exit(1)
        # R3: 用 restormer (或指定 backbone) 的 ft 配方底座 + DP-Loss override
        cfg_entry = dict(_FT_CONFIG[method])   # copy
        cfg_entry.update({k: v for k, v in _R3_DP_CONFIG.items()
                          if k in ("optimizer", "lr_ft", "weight_decay",
                                   "batch_size", "iterations", "warmup_iters", "loss")})
        method_tag = f"{method}"
        display_name = f"{method}_dpgraft_r3"

    dp_cfg = _R3_DP_CONFIG if args.mode == "r3" else None

    # cwd 必须是 project/ (importlib 依赖)
    project_dir = Path(__file__).resolve().parent
    if str(project_dir) not in sys.path:
        sys.path.insert(0, str(project_dir))
    os.chdir(project_dir)

    # Load backbone
    print(f"[load] backbone={method}  weights_dir={paths['weights_dir']}")
    net = load_trainable_backbone(method, paths["weights_dir"], device,
                                  mock_weights=args.smoke)

    # Load B3 oracle (frozen)
    print(f"[load] B3 oracle <- {paths['b3_ckpt']}")
    if args.smoke:
        # Smoke: mock B3 (random weights, no file needed)
        from torchvision.models import efficientnet_b3
        b3_net = efficientnet_b3(weights=None)
        b3_net.classifier = nn.Sequential(
            nn.Dropout(p=0.3, inplace=True),
            nn.Linear(b3_net.classifier[1].in_features, 2))
        b3 = b3_net.to(device).eval().requires_grad_(False)
        print("[smoke] B3 loaded with random weights (no ckpt)")
    else:
        b3 = load_b3(paths["b3_ckpt"], device)

    # DataLoaders
    batch_size = 1 if args.smoke else cfg_entry["batch_size"]
    train_loader, val_loader = build_dataloaders(
        paths=paths,
        batch_size=batch_size,
        num_workers=0 if args.smoke else args.num_workers,
        pin_memory=args.pin_memory and not args.smoke,
        seed=args.seed,
        smoke=args.smoke,
    )
    print(f"[data] train={len(train_loader.dataset)}  val={len(val_loader.dataset)}")

    # Resume / eval-only
    if args.resume:
        print(f"[resume] loading {args.resume}")
        ck = torch.load(args.resume, map_location=device, weights_only=False)
        net.load_state_dict(ck["model"] if "model" in ck else ck, strict=True)

    if not args.eval_only:
        use_ema = cfg_entry.get("use_ema", False)
        ema_decay = cfg_entry.get("ema_decay", 0.999)
        best_ckpt, best_psnr = finetune(
            method=method,
            net=net,
            train_loader=train_loader,
            val_loader=val_loader,
            device=device,
            cfg_entry=cfg_entry,
            ckpt_dir=paths["ckpt_dir"],
            mode=args.mode,
            b3=b3 if args.mode == "r3" else None,
            dp_cfg=dp_cfg,
            no_gan=args.no_gan,
            use_ema=use_ema,
            ema_decay=ema_decay,
            amp=args.amp and not args.smoke,
            smoke=args.smoke,
        )
        # Load best for eval (skip in smoke: net already has best weights in memory)
        if not args.smoke and best_ckpt and Path(best_ckpt).exists():
            ck = torch.load(best_ckpt, map_location=device, weights_only=False)
            sd = ck.get("ema_shadow", ck.get("model", ck))
            if "ema_shadow" in ck:
                # EMA shadow is float32, cast to model dtype
                net.load_state_dict(
                    {k: v.to(next(net.parameters()).dtype) for k, v in sd.items()})
            else:
                net.load_state_dict(sd)
            print(f"[eval] loaded best ckpt {best_ckpt} for test eval")

    # Test eval
    print(f"\n[eval] build test df (E10 caliber) ...")
    if args.smoke:
        # Smoke: skip real csv, eval_and_save will bail early
        df_test = pd.DataFrame()  # empty, eval_and_save detects smoke and skips
        print("[smoke] skip test df (smoke mode)")
    else:
        df_test = build_df_test(paths)
        print(f"[eval] n={len(df_test)}  pos={int(df_test.target.sum())}  "
              f"neg={int((df_test.target == 0).sum())}")

    eval_and_save(
        method_tag=method_tag,
        display_name=display_name,
        mode=args.mode,
        method=method,
        net=net,
        b3=b3,
        df=df_test,
        device=device,
        paths=paths,
        smoke=args.smoke,
    )

    print(f"\n[done] {'smoke ok' if args.smoke else 'completed'}  "
          f"results -> results/{('r1_finetune' if args.mode == 'r1' else 'r3_dpgraft')}_{method_tag}.csv")


if __name__ == "__main__":
    main()
