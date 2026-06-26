"""
train_harness.py — 统一训练台（gdn2vessel P3 baseline 全谱）。

接口约定（baseline_job.sbatch.template 第 5 段）:
    python src/train_harness.py \\
        --config <baseline yaml> \\
        --base_eval src/configs/_base_eval.yaml \\
        --baseline <name> \\
        --data_root <root> \\
        --dataset <NAME> \\
        --seed <int> \\
        --epochs <int> \\
        --output_dir <dir>

内部流程:
  读 config → registry.get_adapter(name) → adapter.build_model/loss/optimizer
  → 统一训练循环 → 存 best.pth（按 val Dice）+ state.json。

设计红线:
  🔒 loss 权重唯一真源 = adapter.build_loss()（不得从 cfg 覆盖 loss 内部权重）
  🔒 env_tag=mamba 时自动关 AMP（U-Mamba README: AMP → Mamba nan）
  🔒 best.pth 存纯 state_dict（与 evaluate.py weights_only=True 直取兼容）
  🔒 state.json schema = train_pilot.py 同款（主线监控脚本依赖）

Dataset dispatch 策略:
  - fr_unet adapter → FRUNetDRIVE/CHASE/STARE/FIVES（frunet_pipeline 官方化预处理）
  - 其他 adapter   → BaseVesselDataset 子类（DRIVEDataset/CHASEDataset/等）通用 pipeline
    TODO: 其他 baseline adapter 接入时在 _build_datasets() 里加对应分支。

Windows 兼容:
  - multiprocessing_context='spawn'（num_workers>0 时）
  - pin_memory=False
  - if __name__ == '__main__' guard
  - 无 scipy.stats（统计用纯 numpy）
  - 路径用 pathlib.Path

Outputs (in output_dir/):
    best.pth     — 最优 val Dice epoch 的 model.state_dict()
    state.json   — 实时训练状态（每 epoch 原子写入）

state.json schema（与 train_pilot.py 完全一致）:
    {
      "epoch": int,
      "train_loss": float,
      "val_dice": float,
      "best_dice": float,
      "status": "running" | "done" | "error"
    }
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

# --------------------------------------------------------------------------- #
#  sys.path 设置（兼容 cwd=project root 或 src/ 直接跑）
# --------------------------------------------------------------------------- #

_src_dir = Path(__file__).parent
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))


# --------------------------------------------------------------------------- #
#  YAML 读取（用 PyYAML 或 fallback 到 json）
# --------------------------------------------------------------------------- #

def _load_yaml(path: str | Path) -> Dict[str, Any]:
    """Load YAML config. Requires PyYAML (pyyaml). Falls back to json if .json."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"[train_harness] Config not found: {p}")
    try:
        import yaml  # type: ignore
        with open(p, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        if p.suffix == ".json":
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        raise RuntimeError(
            "[train_harness] PyYAML not installed. "
            "Install via: pip install pyyaml"
        )


def _merge_configs(
    baseline_cfg: Dict[str, Any],
    base_eval_cfg: Dict[str, Any],
) -> Dict[str, Any]:
    """
    浅合并：baseline_cfg 为主，base_eval 的评估量尺字段附加进来。
    🔒 不修改 loss 权重（loss 内部权重唯一真源 = adapter.build_loss()）。
    返回合并后的平铺 dict，方便 adapter 直接 cfg.get(key)。
    """
    merged: Dict[str, Any] = {}

    # 解包 baseline yaml 各 section
    for section_val in baseline_cfg.values():
        if isinstance(section_val, dict):
            merged.update(section_val)

    # 附加 base_eval 评估量尺（eval/csv sections）
    for section_key, section_val in base_eval_cfg.items():
        if isinstance(section_val, dict):
            # 以 section_key 为前缀加入（防 key 冲突）
            for k, v in section_val.items():
                merged.setdefault(f"_eval_{section_key}_{k}", v)

    # 顶层 baseline metadata 直接加
    if "baseline" in baseline_cfg and isinstance(baseline_cfg["baseline"], dict):
        merged.update(baseline_cfg["baseline"])

    return merged


# --------------------------------------------------------------------------- #
#  Metrics — 纯 numpy（无 scipy.stats，OMP 安全）
# --------------------------------------------------------------------------- #

def _dice_np(
    pred_bin: np.ndarray,
    target: np.ndarray,
    mask: np.ndarray,
    eps: float = 1e-6,
) -> float:
    """Dice coefficient inside FOV mask, pure numpy."""
    m = mask > 0
    p = pred_bin[m].astype(np.float32)
    t = target[m].astype(np.float32)
    intersection = float((p * t).sum())
    denom = float(p.sum() + t.sum())
    return float((2.0 * intersection + eps) / (denom + eps))


# --------------------------------------------------------------------------- #
#  state.json 原子写入（同 train_pilot.py）
# --------------------------------------------------------------------------- #

def _write_state(
    path: Path,
    epoch: int,
    train_loss: float,
    val_dice: float,
    best_dice: float,
    status: str,
) -> None:
    """原子写入 state.json（tmp → rename）。"""
    state = {
        "epoch": epoch,
        "train_loss": round(float(train_loss), 6),
        "val_dice": round(float(val_dice), 6),
        "best_dice": round(float(best_dice), 6),
        "status": status,
    }
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    tmp.replace(path)


# --------------------------------------------------------------------------- #
#  Dataset builder — dispatch by adapter name + dataset name
# --------------------------------------------------------------------------- #

def _build_datasets(
    adapter_name: str,
    dataset: str,
    data_root: Path,
    cfg: Dict[str, Any],
) -> Tuple[Any, Any]:
    """
    按 adapter_name 和 dataset 构建 (train_dataset, val_dataset)。

    FR-UNet → FRUNetDRIVE/CHASE/STARE/FIVES（官方化 pipeline）
    其他 baseline → BaseVesselDataset 子类（通用 pipeline）

    Args:
        adapter_name: registry key（如 'fr_unet', 'backbone_unet'）
        dataset:      数据集名（'DRIVE'/'CHASE'/'CHASE_DB1'/'FIVES'/'STARE'）
        data_root:    该集根目录
        cfg:          合并后的平铺 config dict

    Returns:
        (train_dataset, val_dataset)

    Raises:
        ValueError: 不支持的 dataset 或 adapter 组合
        FileNotFoundError: data_root 不存在
    """
    if not data_root.exists():
        raise FileNotFoundError(
            f"[train_harness] data_root 不存在: {data_root}\n"
            f"请检查 --data_root 路径。"
        )

    ds_upper = dataset.upper().replace("-", "_").replace(" ", "_")

    # ------------------------------------------------------------------ #
    #  FR-UNet → 官方化 frunet_pipeline（FIX Q6/Q7 已改正，BT.601 + get_square）
    # ------------------------------------------------------------------ #
    if adapter_name == "fr_unet":
        from datasets.frunet_pipeline import make_frunet_dataset

        patch_size = int(cfg.get("patch_size", 48))
        cache_path = cfg.get("frunet_cache_path", None)  # 可选，从 config 读
        # cache_path 也可由 --frunet_cache_path CLI arg 覆盖（见 parse_args）

        # BUG-FIX-patch-epoch: 官方 dataset size = 预切 patch 总数（非图片数）。
        # 本实现等价：train dataset 里每张图重复 repeats 次，每次随机切 1 patch。
        # repeats=200 → DRIVE(16张)=3200 items, bs=512 → 6 steps/epoch（合理量级）。
        # BUG-FIX-val: val 传 patch_size=None → 整图模式，配合 _val_epoch 里的
        # adapter.forward_adapt 做官方 get_square+整图推理，Dice 信号才有意义。
        _FRUNET_TRAIN_REPEATS = int(cfg.get("frunet_train_repeats", 1000))

        if ds_upper == "DRIVE":
            train_ds = make_frunet_dataset(
                name="drive",
                data_root=str(data_root),
                split="train",
                patch_size=patch_size,
                augment=True,
                cache_path=cache_path,
                repeats=_FRUNET_TRAIN_REPEATS,  # BUG-FIX-patch-epoch
            )
            val_ds = make_frunet_dataset(
                name="drive",
                data_root=str(data_root),
                split="val",
                patch_size=None,          # BUG-FIX-val: 整图模式（官方 get_square）
                augment=False,
                cache_path=cache_path,
            )
        elif ds_upper in ("CHASE", "CHASE_DB1"):
            train_ds = make_frunet_dataset(
                name="chase",
                data_root=str(data_root),
                split="train",
                patch_size=patch_size,
                augment=True,
                cache_path=cache_path,
                repeats=_FRUNET_TRAIN_REPEATS,  # BUG-FIX-patch-epoch
            )
            val_ds = make_frunet_dataset(
                name="chase",
                data_root=str(data_root),
                split="val",
                patch_size=None,          # BUG-FIX-val: 整图模式
                augment=False,
                cache_path=cache_path,
            )
        elif ds_upper == "STARE":
            # GDN-2 主实验协议（12/4/4 hold-out），非官方 train=test
            train_ds = make_frunet_dataset(
                name="stare",
                data_root=str(data_root),
                split="train",
                patch_size=patch_size,
                augment=True,
                cache_path=cache_path,
                stare_official_baseline=False,
                repeats=_FRUNET_TRAIN_REPEATS,  # BUG-FIX-patch-epoch
            )
            val_ds = make_frunet_dataset(
                name="stare",
                data_root=str(data_root),
                split="val",
                patch_size=None,          # BUG-FIX-val: 整图模式
                augment=False,
                cache_path=cache_path,
                stare_official_baseline=False,
            )
        elif ds_upper == "FIVES":
            train_ds = make_frunet_dataset(
                name="fives",
                data_root=str(data_root),
                split="train",
                patch_size=patch_size,
                augment=True,
                cache_path=cache_path,
                repeats=_FRUNET_TRAIN_REPEATS,  # BUG-FIX-patch-epoch
            )
            val_ds = make_frunet_dataset(
                name="fives",
                data_root=str(data_root),
                split="val",
                patch_size=None,          # BUG-FIX-val: 整图模式
                augment=False,
                cache_path=cache_path,
            )
        else:
            raise ValueError(
                f"[train_harness] fr_unet: 不支持的 dataset {dataset!r}. "
                "Supported: DRIVE / CHASE / STARE / FIVES"
            )
        return train_ds, val_ds

    # ------------------------------------------------------------------ #
    #  CS-Net 专用 RGB pipeline（color_mode='rgb'，官方 iMED-Lab/CS-Net /255 无 CLAHE）
    # ------------------------------------------------------------------ #
    if adapter_name == "cs_net":
        # CS-Net 官方用 RGB 3ch 输入（Image.open → ToTensor，/255，无 CLAHE）。
        # dataset 输出 image: (3, H, W) float32 /255。
        # 其余超参（patch_size / augment）与通用流程一致。
        # 来源：iMED-Lab/CS-Net dataloader/drive.py（2026-06-25 核实）
        cs_patch_size = int(cfg.get("patch_size") or 512)
        if ds_upper == "DRIVE":
            from datasets.drive import DRIVEDataset
            train_ds = DRIVEDataset(
                data_root=data_root, split="train",
                patch_size=cs_patch_size, augment=True, color_mode='rgb',
            )
            val_ds = DRIVEDataset(
                data_root=data_root, split="val",
                patch_size=cs_patch_size, augment=False, color_mode='rgb',
            )
        elif ds_upper in ("CHASE", "CHASE_DB1"):
            from datasets.chase import CHASEDataset
            train_ds = CHASEDataset(
                data_root=data_root, split="train",
                patch_size=cs_patch_size, augment=True, color_mode='rgb',
            )
            val_ds = CHASEDataset(
                data_root=data_root, split="val",
                patch_size=cs_patch_size, augment=False, color_mode='rgb',
            )
        elif ds_upper == "STARE":
            from datasets.stare import STAREDataset
            train_ds = STAREDataset(
                data_root=data_root, split="train",
                patch_size=cs_patch_size, augment=True, color_mode='rgb',
            )
            val_ds = STAREDataset(
                data_root=data_root, split="val",
                patch_size=cs_patch_size, augment=False, color_mode='rgb',
            )
        elif ds_upper == "FIVES":
            from datasets.fives import FIVESDataset
            train_ds = FIVESDataset(
                data_root=data_root, split="train",
                patch_size=cs_patch_size, augment=True, color_mode='rgb',
            )
            val_ds = FIVESDataset(
                data_root=data_root, split="val",
                patch_size=cs_patch_size, augment=False, color_mode='rgb',
            )
        else:
            raise ValueError(
                f"[train_harness] cs_net: 不支持的 dataset {dataset!r}. "
                "Supported: DRIVE / CHASE / STARE / FIVES"
            )
        return train_ds, val_ds

    # ------------------------------------------------------------------ #
    #  通用 BaseVesselDataset pipeline（backbone_unet / ours_gdn2 / 未来 adapter）
    # ------------------------------------------------------------------ #
    # patch_size None(yaml null, 如 backbone_unet input_mode=fullimg) → 512 全图 pad-crop 默认
    patch_size = int(cfg.get("patch_size") or 512)

    if ds_upper == "DRIVE":
        from datasets.drive import DRIVEDataset
        train_ds = DRIVEDataset(
            data_root=data_root,
            split="train",
            patch_size=patch_size,
            augment=True,
        )
        val_ds = DRIVEDataset(
            data_root=data_root,
            split="val",
            patch_size=patch_size,
            augment=False,
        )
    elif ds_upper in ("CHASE", "CHASE_DB1"):
        from datasets.chase import CHASEDataset
        train_ds = CHASEDataset(
            data_root=data_root,
            split="train",
            patch_size=patch_size,
            augment=True,
        )
        val_ds = CHASEDataset(
            data_root=data_root,
            split="val",
            patch_size=patch_size,
            augment=False,
        )
    elif ds_upper == "STARE":
        from datasets.stare import STAREDataset
        train_ds = STAREDataset(
            data_root=data_root,
            split="train",
            patch_size=patch_size,
            augment=True,
        )
        val_ds = STAREDataset(
            data_root=data_root,
            split="val",
            patch_size=patch_size,
            augment=False,
        )
    elif ds_upper == "FIVES":
        from datasets.fives import FIVESDataset
        train_ds = FIVESDataset(
            data_root=data_root,
            split="train",
            patch_size=patch_size,
            augment=True,
        )
        val_ds = FIVESDataset(
            data_root=data_root,
            split="val",
            patch_size=patch_size,
            augment=False,
        )
    else:
        raise ValueError(
            f"[train_harness] 不支持的 dataset {dataset!r}. "
            "Supported: DRIVE / CHASE / STARE / FIVES"
        )

    # TODO: cldice / cbdice / skeleton_recall adapter 接入时，
    #       若它们有自定义 dataset 需求（如特殊增强/预处理），
    #       在此 if/elif 链里加 adapter_name 分支。
    # TODO: creatis_postproc 两段式（Stage-1 分割 + Stage-2 断点续连 postproc）
    #       可能需要独立 dataset 分支或 train_harness 内部识别 kind 走两段。
    # TODO: vm_unet / mm_unet (mamba 系) 若需特殊预处理，加对应分支。

    return train_ds, val_ds


# --------------------------------------------------------------------------- #
#  Train one epoch
# --------------------------------------------------------------------------- #

def _train_epoch(
    model: nn.Module,
    loader: DataLoader,
    optimizer: torch.optim.Optimizer,
    loss_fn: Any,
    device: torch.device,
    use_amp: bool,
    scaler: Optional[Any],
) -> float:
    """
    单 epoch 训练。loss_fn 签名：(logits, target, fov_mask) → scalar tensor。
    🔒 loss 由 adapter.build_loss() 返回，此处直接调用，不修改权重。
    """
    model.train()
    total_loss = 0.0
    n_batches = 0

    for batch in loader:
        img = batch["image"].to(device, non_blocking=False)
        gt = batch["gt"].to(device, non_blocking=False)
        fov = batch["fov"].to(device, non_blocking=False)

        optimizer.zero_grad()

        if use_amp and scaler is not None:
            from torch.cuda.amp import autocast
            with autocast():
                logits = model(img)
                loss = loss_fn(logits, gt, fov)
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
        else:
            logits = model(img)
            loss = loss_fn(logits, gt, fov)
            loss.backward()
            optimizer.step()

        total_loss += loss.item()
        n_batches += 1

    return total_loss / max(n_batches, 1)


# --------------------------------------------------------------------------- #
#  Val one epoch
# --------------------------------------------------------------------------- #

@torch.no_grad()
def _val_epoch(
    model: nn.Module,
    loader: DataLoader,
    device: torch.device,
    adapter: Optional[Any] = None,
) -> float:
    """
    单 epoch 验证，返回 mean val Dice（FOV 内，纯 numpy，无 scipy）。
    阈值固定 0.5（与 evaluate.py _base_eval.yaml 量尺一致）。

    BUG-FIX-val: 若 adapter 有 forward_adapt（如 fr_unet 的滑窗推理），
    则调 adapter.forward_adapt(model, img, device) 代替直接 model(img)。
    fr_unet val_ds 传 patch_size=None → 整图 get_square → forward_adapt 滑窗 →
    frunet_test_crop_tensor 裁回 orig_hw → Dice 才是真实全图 Dice。
    """
    from datasets.frunet_pipeline import frunet_test_crop_tensor  # 整图裁回工具

    model.eval()
    dice_scores = []
    use_forward_adapt = (adapter is not None and hasattr(adapter, 'forward_adapt'))

    for batch in loader:
        img = batch["image"].to(device, non_blocking=False)
        gt  = batch["gt"].to(device, non_blocking=False)
        fov = batch["fov"].to(device, non_blocking=False)
        # orig_hw: frunet 整图模式下返回 (orig_H, orig_W)，patch 模式下 = patch_size
        orig_hw = batch.get("orig_hw", None)  # tuple of (Tensor, Tensor) after collate

        if use_forward_adapt:
            # BUG-FIX-val: fr_unet 整图推理路径
            # DataLoader collate 会把 orig_hw tuple → (Tensor[B], Tensor[B])
            logits = adapter.forward_adapt(model, img, device)  # (B,1,H_pad,W_pad)
        else:
            logits = model(img)

        prob = torch.sigmoid(logits)
        pred_bin = (prob > 0.5).float()

        for b in range(img.shape[0]):
            # BUG-FIX-val: 整图模式时裁回 orig_hw，去掉 get_square 的 zero-padding
            if use_forward_adapt and orig_hw is not None:
                oh = int(orig_hw[0][b]) if hasattr(orig_hw[0], '__len__') else int(orig_hw[0])
                ow = int(orig_hw[1][b]) if hasattr(orig_hw[1], '__len__') else int(orig_hw[1])
                pred_b  = frunet_test_crop_tensor(pred_bin[b],   oh, ow)   # (1,oh,ow)
                gt_b    = frunet_test_crop_tensor(gt[b],          oh, ow)   # (1,oh,ow)
                fov_b   = frunet_test_crop_tensor(fov[b],         oh, ow)   # (1,oh,ow)
            else:
                pred_b = pred_bin[b]
                gt_b   = gt[b]
                fov_b  = fov[b]

            d = _dice_np(
                pred_b[0].cpu().numpy(),
                gt_b[0].cpu().numpy(),
                fov_b[0].cpu().numpy(),
            )
            dice_scores.append(d)

    return float(np.mean(dice_scores)) if dice_scores else 0.0


# --------------------------------------------------------------------------- #
#  CLI parser
# --------------------------------------------------------------------------- #

def _parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="gdn2vessel unified baseline training harness (P3)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    # --- 接口契约必填 ---
    p.add_argument(
        "--config", required=True,
        help="Baseline YAML config path (e.g. src/configs/baselines/frunet.yaml)",
    )
    p.add_argument(
        "--base_eval", required=True,
        help="Base eval YAML path (src/configs/_base_eval.yaml)",
    )
    p.add_argument(
        "--baseline", required=True,
        help="Registry adapter name (e.g. fr_unet, backbone_unet, ours_gdn2)",
    )
    p.add_argument(
        "--data_root", required=True,
        help="Dataset root directory (e.g. /path/to/DRIVE)",
    )
    p.add_argument(
        "--dataset", required=True,
        help="Dataset name: DRIVE / CHASE / STARE / FIVES",
    )
    p.add_argument(
        "--seed", type=int, default=42,
        help="Random seed for reproducibility",
    )
    p.add_argument(
        "--epochs", type=int, default=None,
        help="Max epochs. Overrides config train.epochs if given.",
    )
    p.add_argument(
        "--output_dir", required=True,
        help="Output directory for best.pth + state.json",
    )
    # --- 可选覆盖 ---
    p.add_argument(
        "--num_workers", type=int, default=0,
        help="DataLoader workers. 0=Windows safe. Use 2 on HPC Linux.",
    )
    p.add_argument(
        "--patience", type=int, default=None,
        help="Early stopping patience (epochs). None = no early stopping.",
    )
    p.add_argument(
        "--device", default=None,
        help="'cpu' | 'cuda' | 'cuda:0'. Default: auto-detect.",
    )
    p.add_argument(
        "--batch_size", type=int, default=None,
        help="Train batch size. Overrides config train.batch_size if given.",
    )
    p.add_argument(
        "--frunet_cache_path", default=None,
        help=(
            "FR-UNet preprocessed pickle cache path (for fr_unet adapter). "
            "If not set, falls back to config frunet_cache_path or no-cache "
            "(per-image minmax only, no global mean/std normalization)."
        ),
    )
    p.add_argument(
        "--smoke", action="store_true",
        help="Smoke test: run 2 training steps and exit. For CI/quick sanity check.",
    )
    return p.parse_args(argv)


# --------------------------------------------------------------------------- #
#  Main training loop
# --------------------------------------------------------------------------- #

def main(argv=None):
    args = _parse_args(argv)

    # --- seed 全链路确定性 ---
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)
    # cudnn 确定性（速度换精确复现，baseline 要求零偏离）
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False

    # --- 输出目录 ---
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    state_path = output_dir / "state.json"
    ckpt_path = output_dir / "best.pth"

    # --- 读 config ---
    baseline_cfg = _load_yaml(args.config)
    base_eval_cfg = _load_yaml(args.base_eval)
    cfg = _merge_configs(baseline_cfg, base_eval_cfg)

    # CLI --frunet_cache_path 覆盖 config
    if args.frunet_cache_path is not None:
        cfg["frunet_cache_path"] = args.frunet_cache_path

    # --- 取 adapter ---
    try:
        import baselines  # 触发 auto_discover
        from baselines.registry import get_adapter
        adapter = get_adapter(args.baseline)
    except KeyError as e:
        print(f"[train_harness] FATAL: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"[train_harness] adapter={adapter}")

    # ------------------------------------------------------------------ #
    #  creatis_postproc 两段式分支（识别 two_stage kind，特殊处理）
    # ------------------------------------------------------------------ #
    # creatis baseline 是两段式：
    #   Stage 1 = backbone_unet 标准训练（单独跑 train_harness --baseline backbone_unet）
    #   Stage 2 = creatis reconnecting model 训练（需要官方 disconnect.py 生成的断点数据）
    # 当前 harness 对 Stage-2 训练的支持状态：
    #   - Stage-2 数据集（断点图 + GT 对）尚未接好（见 creatis.yaml data.stage2_train_source）
    #   - 需要先跑 sources/source_2D/disconnect.py 生成断点训练数据
    #   - TODO: 未找到官方源，需 researcher 确认 Stage-2 训练数据 HPC 路径
    # 当 baseline = creatis_postproc 时：
    #   - 若 cfg.two_stage=True 且无 Stage-2 训练数据路径 → 打印说明并提示
    #   - 若 cfg.stage2_data_dir 已配置 → 继续走常规训练循环（Stage-2 训练）
    _two_stage = bool(cfg.get("two_stage", False))
    if args.baseline == "creatis_postproc" and _two_stage:
        stage2_data_dir = cfg.get("stage2_data_dir", None)
        if stage2_data_dir is None:
            # Stage-2 训练数据未配置 → 无法继续
            print(
                "\n[train_harness] creatis_postproc 两段式说明:\n"
                "  Stage 1 (backbone_unet) 必须先独立训练:\n"
                "    python src/train_harness.py --baseline backbone_unet "
                "--dataset DRIVE --output_dir outputs/backbone_drive_s42\n"
                "\n"
                "  Stage 2 (creatis reconnecting model) 训练步骤:\n"
                "    1. 生成断点训练数据:\n"
                "       python third_party/creatis_postproc/disconnect.py "
                "--data_root <vessel_data> --out_dir <stage2_data_dir>\n"
                "       # TODO: 未找到官方源，需 researcher 确认 HPC 断点数据路径\n"
                "       # 官方: sources/source_2D/disconnect.py (main branch)\n"
                "    2. 配置 creatis.yaml data.stage2_data_dir 指向生成的断点数据\n"
                "    3. 重新运行 train_harness --baseline creatis_postproc\n"
                "\n"
                "  评估（Stage-2 权重已有或使用官方预训权重）:\n"
                "    python src/evaluate.py --adapter creatis_postproc\n"
                "      --ckpt <stage2.pth>  (或 --config creatis.yaml model.model_dir=<dir>)\n"
                "    cfg: stage1_ckpt=<backbone_best.pth>  (两段式完整评估)\n"
                "    # TODO: 需 researcher 确认官方预训权重 2D_model_stare 的 HPC 路径\n"
                "    #       官方 repo: sources/source_2D/models/2D_model_stare/\n",
                file=sys.stderr,
            )
            print(
                "[train_harness] creatis Stage-2 训练数据未配置，退出。\n"
                "  配置 creatis.yaml data.stage2_data_dir 后重试。",
                file=sys.stderr,
            )
            _write_state(state_path, 0, 0.0, 0.0, 0.0, "error")
            sys.exit(1)
        else:
            # stage2_data_dir 已设置 → 继续走常规训练循环
            # TODO: Stage-2 训练循环需配套断点 dataset 类（pos_i mask 用于 PonderatedDiceloss）
            #       当前 _build_datasets 对 creatis_postproc 走通用 BaseVesselDataset
            #       （不含 pos_i 列），PonderatedDiceloss dice_2 项会用 fov_mask 近似。
            #       精确复现须接入官方断点 dataloader（见 creatis_postproc.py TODO_harness）。
            print(
                f"[train_harness] creatis_postproc Stage-2 训练模式\n"
                f"  stage2_data_dir={stage2_data_dir!r}\n"
                f"  WARNING: PonderatedDiceloss dice_2 项用 fov_mask 近似（非官方 pos_i）\n"
                f"  精确复现需官方断点 dataloader（见 creatis_postproc.py TODO_harness）"
            )
            # 继续下面的常规训练循环

    # --- device ---
    if args.device is not None:
        device = torch.device(args.device)
    else:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[train_harness] device={device}")

    # --- AMP：mamba 系强制关 ---
    cfg_amp = bool(cfg.get("amp", False))
    if adapter.env_tag == "mamba":
        # U-Mamba README: AMP → Mamba nan（RTX4090 sm_89 确认）
        use_amp = False
        print("[train_harness] env_tag=mamba → AMP disabled (U-Mamba README)")
    else:
        use_amp = cfg_amp and device.type == "cuda"
    print(f"[train_harness] use_amp={use_amp}")

    scaler = None
    if use_amp:
        from torch.cuda.amp import GradScaler
        scaler = GradScaler()

    # --- build model（从 adapter 取，cfg 仅作超参容器）---
    model = adapter.build_model(cfg).to(device)
    n_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"[train_harness] model params = {n_params:,}")

    # --- build loss（🔒 唯一真源 = adapter.build_loss()，不从 cfg 覆盖）---
    loss_fn = adapter.build_loss(cfg)
    print(f"[train_harness] loss_fn = {loss_fn.__class__.__name__}")

    # --- build optimizer ---
    optimizer = adapter.build_optimizer(model, cfg)

    # --- build scheduler（可选）---
    scheduler = adapter.build_scheduler(optimizer, cfg)

    # --- epochs ---
    if args.epochs is not None:
        n_epochs = args.epochs
    else:
        # 从 config 取 train.epochs
        n_epochs = int(cfg.get("epochs", 40))
    print(f"[train_harness] epochs={n_epochs}")

    # --- batch_size ---
    if args.batch_size is not None:
        batch_size = args.batch_size
    else:
        batch_size = int(cfg.get("batch_size", 4))
    print(f"[train_harness] batch_size={batch_size}")

    # --- datasets ---
    data_root = Path(args.data_root)
    try:
        train_ds, val_ds = _build_datasets(
            adapter_name=args.baseline,
            dataset=args.dataset,
            data_root=data_root,
            cfg=cfg,
        )
    except (FileNotFoundError, ValueError) as e:
        print(f"[train_harness] FATAL: {e}", file=sys.stderr)
        sys.exit(1)

    print(
        f"[train_harness] dataset={args.dataset}  "
        f"train={len(train_ds)}  val={len(val_ds)}"
    )

    # --- DataLoader — Windows 兼容（spawn + pin_memory=False）---
    loader_kwargs: Dict[str, Any] = dict(
        batch_size=batch_size,
        num_workers=args.num_workers,
        pin_memory=False,          # spawn worker 不支持 pin_memory
    )
    if args.num_workers > 0:
        loader_kwargs["multiprocessing_context"] = "spawn"

    train_loader = DataLoader(train_ds, shuffle=True, **loader_kwargs)
    val_loader = DataLoader(val_ds, shuffle=False, **loader_kwargs)

    # --- 初始化 state.json ---
    best_dice = 0.0
    no_improve = 0
    patience = args.patience  # None = 不 early stop
    _write_state(state_path, 0, 0.0, 0.0, 0.0, "running")

    print(
        f"[train_harness] start training — "
        f"baseline={args.baseline}  dataset={args.dataset}  seed={args.seed}"
    )

    # --- 训练循环 ---
    final_epoch = 0
    final_train_loss = 0.0
    final_val_dice = 0.0

    for epoch in range(1, n_epochs + 1):
        t0 = time.time()

        train_loss = _train_epoch(
            model, train_loader, optimizer, loss_fn,
            device, use_amp, scaler,
        )
        val_dice = _val_epoch(model, val_loader, device, adapter=adapter)

        elapsed = time.time() - t0

        # scheduler step（按 adapter 返回的 scheduler 类型决定 step 参数）
        if scheduler is not None:
            try:
                scheduler.step(val_dice)   # ReduceLROnPlateau (max)
            except TypeError:
                scheduler.step()           # CosineAnnealingLR 等无参 step

        improved = val_dice > best_dice
        if improved:
            best_dice = val_dice
            # 🔒 存纯 state_dict（evaluate.py torch.load(weights_only=True) 直取）
            torch.save(model.state_dict(), str(ckpt_path))
            no_improve = 0
        else:
            no_improve += 1

        _write_state(state_path, epoch, train_loss, val_dice, best_dice, "running")

        print(
            f"[epoch {epoch:04d}/{n_epochs}] "
            f"loss={train_loss:.4f}  val_dice={val_dice:.4f}  "
            f"best={best_dice:.4f}  {'*' if improved else ' '}  "
            f"({elapsed:.1f}s)"
        )

        final_epoch = epoch
        final_train_loss = train_loss
        final_val_dice = val_dice

        # --- smoke test: 2 steps 后退出 ---
        if args.smoke and epoch >= 2:
            print("[train_harness] smoke done — exiting after 2 epochs.")
            _write_state(
                state_path, epoch, train_loss, val_dice, best_dice, "done"
            )
            return

        # --- early stopping ---
        if patience is not None and no_improve >= patience:
            print(
                f"[train_harness] early stop at epoch {epoch} "
                f"(no improvement for {patience} epochs)"
            )
            break

    _write_state(
        state_path, final_epoch, final_train_loss, final_val_dice, best_dice, "done"
    )
    print(
        f"[train_harness] done. "
        f"best val Dice = {best_dice:.4f}  ckpt → {ckpt_path}"
    )


# --------------------------------------------------------------------------- #
#  Windows __main__ guard（spawn 安全必须）
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    main()
