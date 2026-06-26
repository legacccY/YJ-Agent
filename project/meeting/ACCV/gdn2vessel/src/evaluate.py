"""
evaluate.py — 统一三轴评估台（BASELINE_SPEC §2.5）

三轴：
  轴1 重叠轴: dice / iou / auc / se(sensitivity) / sp(specificity)
              纯 numpy 实现，无 scipy.stats（OMP 安全）
  轴2 拓扑轴: cldice / betti_b0_err / betti_b1_err / skeleton_recall
              调 benchmark/tools_topology.py（graceful fallback）
  轴3 续连轴: epsilon_beta0 / success_rate / reid_rate / n_gaps
              调 benchmark/metrics.py（需 BreakResult；原图无 gap 时跳过/置0）

输出 CSV schema（BASELINE_SPEC §2.5）：
  dataset, baseline, kind, seed, split,
  dice, iou, auc, se, sp,
  cldice, betti_b0_err, betti_b1_err, skeleton_recall, topo_source,
  epsilon_beta0, success_rate, reid_rate, n_gaps,
  ckpt_path, eval_input_mode, threshold, git_commit

Usage::

    python src/evaluate.py \\
        --adapter ours_gdn2 \\
        --ckpt outputs/pilot/best.pth \\
        --data_root /path/to/DRIVE \\
        --dataset DRIVE \\
        --split val \\
        --seed 42 \\
        --output_csv outputs/eval/ours_gdn2_drive_seed42.csv

Windows compatibility:
  - num_workers=0（DataLoader）
  - 纯 numpy / sklearn 重叠轴，无 scipy.stats
  - if __name__ == '__main__' guard
  - pathlib.Path 路径

TODO (后续 adapter 实现时填充):
  - 滑窗推理 hook 在各 patch 模型 adapter 的 forward_adapt 中实现
  - 续连轴 (SR/reID) 需要 BreakResult，原图无 break → skip（已实现跳过逻辑）
  - AUC 口径：FOV 内 vs 全图 — 当前实现用 FOV 内（需 researcher 核 SOTA 口径）
    # TODO: 核 AUC 在 FOV 内 vs 全图的主流 vessel paper 口径（BASELINE_SPEC §2.5 NOTE）
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import torch
from torch.utils.data import DataLoader, Dataset

# --------------------------------------------------------------------------- #
#  sys.path 设置（兼容 cwd=project root 或 src/ 直接跑）
# --------------------------------------------------------------------------- #

_src_dir = Path(__file__).parent
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))


# --------------------------------------------------------------------------- #
#  重叠轴：纯 numpy 实现（无 scipy.stats — OMP 安全）
# --------------------------------------------------------------------------- #

def _compute_overlap_metrics(
    pred_bin: np.ndarray,
    gt: np.ndarray,
    fov: np.ndarray,
    pred_prob: Optional[np.ndarray] = None,
    eps: float = 1e-6,
) -> Dict[str, float]:
    """
    计算重叠轴五指标（FOV 内）：dice / iou / auc / se / sp。

    Args:
        pred_bin:  (H, W) binary prediction {0,1}
        gt:        (H, W) ground-truth {0,1}
        fov:       (H, W) FOV mask {0,1}
        pred_prob: (H, W) float32 prob for AUC，None→AUC=-1.0（跳过）
        eps:       smoothing epsilon

    Returns:
        dict 含 dice / iou / se / sp / auc

    NOTE: AUC 口径当前 = FOV 内。
    # TODO: researcher 核 SOTA AUC 口径（§2.5）后若需改全图，在此修改 fov_mask 过滤逻辑。
    """
    # 提取 FOV 内像素
    fov_b = (fov > 0)
    p = pred_bin[fov_b].astype(np.float32)
    t = gt[fov_b].astype(np.float32)

    tp = float(np.sum(p * t))
    fp = float(np.sum(p * (1 - t)))
    fn = float(np.sum((1 - p) * t))
    tn = float(np.sum((1 - p) * (1 - t)))

    dice = (2 * tp + eps) / (2 * tp + fp + fn + eps)
    iou = (tp + eps) / (tp + fp + fn + eps)
    se = (tp + eps) / (tp + fn + eps)        # sensitivity / recall
    sp = (tn + eps) / (tn + fp + eps)        # specificity

    # AUC via trapezoidal rule (ROC) — 纯 numpy，不用 sklearn（可选依赖）
    auc = -1.0
    if pred_prob is not None:
        try:
            auc = _roc_auc_numpy(pred_prob[fov_b], t)
        except Exception:
            auc = -1.0  # fallback 不崩

    return {
        "dice": float(dice),
        "iou": float(iou),
        "se": float(se),
        "sp": float(sp),
        "auc": float(auc),
    }


def _roc_auc_numpy(scores: np.ndarray, labels: np.ndarray) -> float:
    """
    纯 numpy ROC AUC（梯形积分）。
    无 scipy.stats，无 sklearn（OMP 安全）。

    Args:
        scores: (N,) float, prediction probabilities
        labels: (N,) float {0,1}

    Returns:
        AUC ∈ [0, 1].
    """
    # 按 score 降序排列
    desc_idx = np.argsort(-scores)
    labels_sorted = labels[desc_idx]

    n_pos = float(np.sum(labels == 1))
    n_neg = float(np.sum(labels == 0))
    if n_pos == 0 or n_neg == 0:
        return 0.5  # degenerate case

    # 累积 TP / FP
    tp_cumsum = np.cumsum(labels_sorted)
    fp_cumsum = np.cumsum(1 - labels_sorted)

    tpr = tp_cumsum / n_pos
    fpr = fp_cumsum / n_neg

    # 梯形积分
    tpr = np.concatenate([[0.0], tpr])
    fpr = np.concatenate([[0.0], fpr])
    auc = float(np.trapz(tpr, fpr))
    return auc


# --------------------------------------------------------------------------- #
#  数据加载辅助（evaluate.py 自行加载全图，不依赖 DRIVEDataset patch 模式）
# --------------------------------------------------------------------------- #

def _load_fullimg_dispatch(
    dataset: str,
    data_root: Path,
    split: str,
    clahe_clip: float = 2.0,
    pad_multiple: int = 32,
) -> List[Dict[str, Any]]:
    """
    Dispatch full-image loader by dataset name.

    Supported: DRIVE / CHASE / CHASE_DB1 / FIVES / STARE

    Returns same schema as _load_drive_fullimg:
      img_t: (1,1,H_pad,W_pad) float32 tensor
      gt:    (H,W) np.uint8
      fov:   (H,W) np.uint8
      orig_h, orig_w: int
      img_id: str|int
    """
    name = dataset.upper().replace('-', '_').replace(' ', '_')
    if name == 'DRIVE':
        from datasets.drive import DRIVEDataset
        if split == 'train':
            ids = DRIVEDataset.TRAIN_IDS
        elif split == 'val':
            ids = DRIVEDataset.VAL_IDS
        else:
            ids = DRIVEDataset.TRAINING_IDS
        return _load_drive_fullimg(data_root, ids, clahe_clip, pad_multiple)
    elif name in ('CHASE', 'CHASE_DB1'):
        return _load_chase_fullimg(data_root, split, clahe_clip, pad_multiple)
    elif name == 'FIVES':
        return _load_fives_fullimg(data_root, split, clahe_clip, pad_multiple)
    elif name == 'STARE':
        return _load_stare_fullimg(data_root, split, clahe_clip, pad_multiple)
    else:
        raise ValueError(
            f'Unknown dataset {dataset!r}. '
            f'Supported: DRIVE / CHASE / FIVES / STARE'
        )


def _load_drive_fullimg(
    data_root: Path,
    img_ids: List[int],
    clahe_clip: float = 2.0,
    pad_multiple: int = 32,
) -> List[Dict[str, Any]]:
    """
    加载 DRIVE 图像为全图（不裁 patch），返回 list of dict:
      img_t: (1, 1, H_pad, W_pad) float32 tensor
      gt:    (H, W) np.uint8
      fov:   (H, W) np.uint8
      orig_h, orig_w: 原始尺寸（裁掉 pad 用）
      img_id: int

    与 DRIVEDataset 同预处理（green_clahe → normalize(0.5, 0.1)）。
    """
    try:
        import cv2
    except ImportError as e:
        raise RuntimeError("cv2 (opencv-python) required for evaluate.py") from e

    GREEN_MEAN, GREEN_STD = 0.5, 0.1
    samples = []

    for sid in img_ids:
        img_path = data_root / "training" / "images" / f"{sid}_training.tif"
        gt_path = data_root / "training" / "1st_manual" / f"{sid}_manual1.gif"
        mask_path = data_root / "training" / "mask" / f"{sid}_training_mask.gif"

        if not img_path.exists():
            raise FileNotFoundError(f"DRIVE image not found: {img_path}")
        if not gt_path.exists():
            raise FileNotFoundError(f"DRIVE GT not found: {gt_path}")

        # --- image ---
        img_bgr = cv2.imread(str(img_path))
        assert img_bgr is not None
        green = img_bgr[:, :, 1].astype(np.uint8)
        clahe = cv2.createCLAHE(clipLimit=clahe_clip,
                                 tileGridSize=(8, 8))
        green_eq = clahe.apply(green)
        img_f = green_eq.astype(np.float32) / 255.0
        img_f = (img_f - GREEN_MEAN) / GREEN_STD

        orig_h, orig_w = img_f.shape

        # --- GT ---
        gt_raw = cv2.imread(str(gt_path), cv2.IMREAD_GRAYSCALE)
        assert gt_raw is not None
        gt = (gt_raw > 127).astype(np.uint8)

        # --- FOV ---
        if mask_path.exists():
            mask_raw = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
            fov = (mask_raw > 127).astype(np.uint8)
        else:
            fov = np.ones_like(gt, dtype=np.uint8)

        # --- pad to multiple ---
        h, w = img_f.shape
        pad_h = (pad_multiple - h % pad_multiple) % pad_multiple
        pad_w = (pad_multiple - w % pad_multiple) % pad_multiple
        img_pad = np.pad(img_f, ((0, pad_h), (0, pad_w)), mode="constant")

        # (1, 1, H_pad, W_pad)
        img_t = torch.from_numpy(img_pad).unsqueeze(0).unsqueeze(0)

        samples.append({
            "img_t": img_t,
            "gt": gt,
            "fov": fov,
            "orig_h": orig_h,
            "orig_w": orig_w,
            "img_id": sid,
        })

    return samples


# --------------------------------------------------------------------------- #
#  CHASE full-image loader
# --------------------------------------------------------------------------- #

def _load_chase_fullimg(
    data_root: Path,
    split: str = 'val',
    clahe_clip: float = 2.0,
    pad_multiple: int = 32,
) -> List[Dict[str, Any]]:
    """
    加载 CHASE_DB1 全图样本（不裁 patch）。

    Kaggle pack layout:
      images/training_NN_test.tif  (training_01 .. training_20)
      images/test_NN_test.tif      (test_01 .. test_08)
      masks/training_NN_manual1.tif / test_NN_manual1.tif
    FOV: no official mask → circular estimate ~90% min(H,W)/2.

    Returns same schema as _load_drive_fullimg.
    """
    try:
        import cv2
    except ImportError as e:
        raise RuntimeError('cv2 (opencv-python) required for evaluate.py') from e

    from datasets.chase import CHASEDataset
    GREEN_MEAN_C, GREEN_STD_C = 0.5, 0.1  # same convention as drive.py

    if split == 'train':
        ids = CHASEDataset.TRAIN_IDS
    elif split == 'val':
        ids = CHASEDataset.VAL_IDS
    elif split in ('test', 'all'):
        # 'all' = all 28; 'test' = held-out 8
        ids = (CHASEDataset.TRAIN_IDS + CHASEDataset.VAL_IDS
               if split == 'all' else CHASEDataset.TEST_IDS)
    else:
        raise ValueError(f'CHASE split {split!r} invalid; use train/val/test/all')

    samples = []
    for sid in ids:
        img_path  = data_root / 'images' / f'{sid}_test.tif'
        gt_path   = data_root / 'masks'  / f'{sid}_manual1.tif'

        if not img_path.exists():
            raise FileNotFoundError(f'CHASE image not found: {img_path}')
        if not gt_path.exists():
            raise FileNotFoundError(f'CHASE GT not found: {gt_path}')

        # Image
        img_bgr = cv2.imread(str(img_path))
        assert img_bgr is not None
        green = img_bgr[:, :, 1].astype(np.uint8)
        clahe = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=(8, 8))
        green_eq = clahe.apply(green)
        img_f = green_eq.astype(np.float32) / 255.0
        img_f = (img_f - GREEN_MEAN_C) / GREEN_STD_C
        orig_h, orig_w = img_f.shape

        # GT
        gt_raw = cv2.imread(str(gt_path), cv2.IMREAD_GRAYSCALE)
        assert gt_raw is not None
        gt = (gt_raw > 127).astype(np.uint8)

        # FOV: circular estimate (no official mask)
        h, w = img_bgr.shape[:2]
        fov = np.zeros((h, w), dtype=np.uint8)
        cy, cx = h // 2, w // 2
        r = int(0.90 * min(h, w) / 2)
        cv2.circle(fov, (cx, cy), r, 1, -1)

        # Pad
        pad_h = (pad_multiple - orig_h % pad_multiple) % pad_multiple
        pad_w = (pad_multiple - orig_w % pad_multiple) % pad_multiple
        img_pad = np.pad(img_f, ((0, pad_h), (0, pad_w)), mode='constant')
        img_t = torch.from_numpy(img_pad).unsqueeze(0).unsqueeze(0)

        samples.append({
            'img_t': img_t,
            'gt': gt,
            'fov': fov,
            'orig_h': orig_h,
            'orig_w': orig_w,
            'img_id': sid,
        })

    return samples


# --------------------------------------------------------------------------- #
#  FIVES full-image loader
# --------------------------------------------------------------------------- #

def _load_fives_fullimg(
    data_root: Path,
    split: str = 'test',
    clahe_clip: float = 2.0,
    pad_multiple: int = 32,
) -> List[Dict[str, Any]]:
    """
    加载 FIVES 全图样本（不裁 patch）。

    Kaggle pack layout:
      images/train_*_*.png  (600 training)
      images/test_*_*.png   (200 test)
      masks/train_*_*.png   /  masks/test_*_*.png  (matching GT)
    FOV: no official mask → all-ones.

    FIVES 2048×2048: 返回全图 tensor (1,1,H_pad,W_pad)。
    # TODO: adapter 级决定是否在 forward_adapt 内 resize 到 512 或滑窗推理。
    # TODO: 确认 FIVES 评估是否用全图推理（内存约 2048*2048*float32 ≈ 16MB/img）
    #        还是滑窗拼图（见 dataset.get_tiles(tile_size=512, overlap=64)）。

    Returns same schema as _load_drive_fullimg.
    """
    try:
        import cv2
    except ImportError as e:
        raise RuntimeError('cv2 (opencv-python) required for evaluate.py') from e

    GREEN_MEAN_F, GREEN_STD_F = 0.5, 0.1

    img_dir  = data_root / 'images'
    mask_dir = data_root / 'masks'

    if split in ('train', 'val', 'all'):
        prefix = 'train_'
    elif split == 'test':
        prefix = 'test_'
    else:
        raise ValueError(f'FIVES split {split!r} invalid; use train/val/test/all')

    stems = sorted(
        p.stem
        for p in img_dir.iterdir()
        if p.suffix.lower() == '.png' and p.name.startswith(prefix)
    )

    # For 'val' / 'train': carve last 10% as val (mirror FIVESDataset logic)
    if split == 'val':
        n_val = min(60, max(1, len(stems) // 10)) if stems else 0
        stems = stems[len(stems) - n_val:]
    elif split == 'train':
        n_val = min(60, max(1, len(stems) // 10)) if stems else 0
        stems = stems[:len(stems) - n_val]
    # 'all' and 'test' keep full list as-is

    samples = []
    for sid in stems:
        img_path = img_dir  / f'{sid}.png'
        gt_path  = mask_dir / f'{sid}.png'

        if not img_path.exists():
            raise FileNotFoundError(f'FIVES image not found: {img_path}')
        if not gt_path.exists():
            raise FileNotFoundError(f'FIVES GT not found: {gt_path}')

        img_bgr = cv2.imread(str(img_path))
        assert img_bgr is not None
        green = img_bgr[:, :, 1].astype(np.uint8)
        clahe = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=(8, 8))
        green_eq = clahe.apply(green)
        img_f = green_eq.astype(np.float32) / 255.0
        img_f = (img_f - GREEN_MEAN_F) / GREEN_STD_F
        orig_h, orig_w = img_f.shape

        gt_raw = cv2.imread(str(gt_path), cv2.IMREAD_GRAYSCALE)
        assert gt_raw is not None
        gt = (gt_raw > 127).astype(np.uint8)

        # Full-image FOV
        fov = np.ones((orig_h, orig_w), dtype=np.uint8)

        pad_h = (pad_multiple - orig_h % pad_multiple) % pad_multiple
        pad_w = (pad_multiple - orig_w % pad_multiple) % pad_multiple
        img_pad = np.pad(img_f, ((0, pad_h), (0, pad_w)), mode='constant')
        img_t = torch.from_numpy(img_pad).unsqueeze(0).unsqueeze(0)

        samples.append({
            'img_t': img_t,
            'gt': gt,
            'fov': fov,
            'orig_h': orig_h,
            'orig_w': orig_w,
            'img_id': sid,
        })

    return samples


# --------------------------------------------------------------------------- #
#  STARE full-image loader
# --------------------------------------------------------------------------- #

def _load_stare_fullimg(
    data_root: Path,
    split: str = 'test',
    clahe_clip: float = 2.0,
    pad_multiple: int = 32,
) -> List[Dict[str, Any]]:
    """
    加载 STARE 全图样本（不裁 patch）。

    Kaggle pack layout:
      images/im0001.ppm  ..  im0324.ppm  (plain PPM, 605×700)
      masks/im0001.ah.ppm .. (ah annotation)
    FOV: no official mask → circular estimate ~90% min(H,W)/2.

    Split (deterministic 12/4/4 matching STAREDataset):
      train = first 12 of _STARE_ALL_IDS
      val   = ids 12..16
      test  = ids 16..20 (last 4)
      all   = train + val (all 20 for full eval)

    Returns same schema as _load_drive_fullimg.
    """
    try:
        import cv2
    except ImportError as e:
        raise RuntimeError('cv2 (opencv-python) required for evaluate.py') from e

    from datasets.stare import _STARE_ALL_IDS, _load_ppm_gz
    GREEN_MEAN_S, GREEN_STD_S = 0.5, 0.1

    if split == 'train':
        ids = _STARE_ALL_IDS[:12]
    elif split == 'val':
        ids = _STARE_ALL_IDS[12:16]
    elif split == 'test':
        ids = _STARE_ALL_IDS[16:]
    elif split == 'all':
        ids = _STARE_ALL_IDS
    else:
        raise ValueError(f'STARE split {split!r} invalid; use train/val/test/all')

    samples = []
    for sid in ids:
        # Try plain .ppm first (Kaggle), then .ppm.gz (HPC compressed)
        img_path = data_root / 'images' / f'{sid}.ppm'
        if not img_path.exists():
            img_path = data_root / 'images' / f'{sid}.ppm.gz'
        gt_path = data_root / 'masks' / f'{sid}.ah.ppm'
        if not gt_path.exists():
            gt_path = data_root / 'masks' / f'{sid}.ah.ppm.gz'

        if not img_path.exists():
            raise FileNotFoundError(f'STARE image not found (tried .ppm/.ppm.gz): {sid}')
        if not gt_path.exists():
            raise FileNotFoundError(f'STARE GT not found (tried .ah.ppm/.ah.ppm.gz): {sid}')

        # Load image
        if ''.join(img_path.suffixes) == '.ppm.gz':
            img_bgr = _load_ppm_gz(img_path)
        else:
            img_bgr = cv2.imread(str(img_path))
            assert img_bgr is not None, f'cv2 failed to read STARE image {img_path}'

        green = img_bgr[:, :, 1].astype(np.uint8)
        clahe = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=(8, 8))
        green_eq = clahe.apply(green)
        img_f = green_eq.astype(np.float32) / 255.0
        img_f = (img_f - GREEN_MEAN_S) / GREEN_STD_S
        orig_h, orig_w = img_f.shape

        # Load GT
        if ''.join(gt_path.suffixes) == '.ppm.gz':
            gt_bgr  = _load_ppm_gz(gt_path)
            gt_gray = cv2.cvtColor(gt_bgr, cv2.COLOR_BGR2GRAY)
        else:
            gt_gray = cv2.imread(str(gt_path), cv2.IMREAD_GRAYSCALE)
            assert gt_gray is not None, f'cv2 failed to read STARE GT {gt_path}'

        gt = (gt_gray > 127).astype(np.uint8)

        # FOV: circular estimate
        h, w = img_bgr.shape[:2]
        fov = np.zeros((h, w), dtype=np.uint8)
        cy, cx = h // 2, w // 2
        r = int(0.90 * min(h, w) / 2)
        cv2.circle(fov, (cx, cy), r, 1, -1)

        # Pad
        pad_h = (pad_multiple - orig_h % pad_multiple) % pad_multiple
        pad_w = (pad_multiple - orig_w % pad_multiple) % pad_multiple
        img_pad = np.pad(img_f, ((0, pad_h), (0, pad_w)), mode='constant')
        img_t = torch.from_numpy(img_pad).unsqueeze(0).unsqueeze(0)

        samples.append({
            'img_t': img_t,
            'gt': gt,
            'fov': fov,
            'orig_h': orig_h,
            'orig_w': orig_w,
            'img_id': sid,
        })

    return samples


# --------------------------------------------------------------------------- #
#  git_commit helper
# --------------------------------------------------------------------------- #

def _get_git_commit() -> str:
    """返回当前 git commit hash（短），失败时返回 'unknown'。"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "unknown"


# --------------------------------------------------------------------------- #
#  M2: re-ID head forward helper
# --------------------------------------------------------------------------- #

def _compute_reid_head_metrics(
    model: Any,
    img_t: "torch.Tensor",
    break_result: Any,
    orig_h: int,
    orig_w: int,
    device: "torch.device",
) -> Tuple[float, float]:
    """
    Run the re-ID head forward with held-out break positions and return
    (reid_rate_head, reid_idf1).

    Design (M2, drift-契约：裁判=GT，head 只出离散 argmax):
      1. Extract gap centres from break_result.gaps.
      2. Scale to dec_feat coordinate space (same logic as train_reid_pilot:682-686).
      3. Call model(img_t, return_reid_ctx=True) → reid_ctx with o_seq / dec_feat.
      4. Call model.reid_head(o_seq, dec_feat, positions) → (1, K, K) logits.
      5. Squeeze logits to (K, K) numpy, call reid_rate_head() from metrics.py.

    A1' guard: memory_state from ctx may be list-of-None (stateless) —
    handled correctly by ReIDReadoutHead.forward (detach guards already handle it).

    Args:
        model:        UNetGDN2 with use_reid_head=True (checked by caller).
        img_t:        (1, 1, H_pad, W_pad) float32 tensor on device.
        break_result: BreakResult with .gaps list.
        orig_h, orig_w: original (un-padded) image dimensions.
        device:       torch.device.

    Returns:
        (reid_rate_head_float, reid_idf1_float) — both in [0,1] or nan.
    """
    from benchmark.metrics import reid_rate_head as _rrh

    gaps = break_result.gaps
    K = len(gaps)
    if K == 0:
        return float('nan'), float('nan')

    model.eval()
    with torch.no_grad():
        logits_out, reid_ctx = model(img_t, return_reid_ctx=True)

    o_seq = reid_ctx.get('o_seq')
    dec_feat = reid_ctx.get('dec_feat')
    memory_state = reid_ctx.get('memory_state')

    if o_seq is None or dec_feat is None:
        return float('nan'), float('nan')

    # dec_feat resolution (may differ from padded img due to stride)
    H_dec = dec_feat.shape[-2]
    W_dec = dec_feat.shape[-1]
    H_pad = img_t.shape[-2]
    W_pad = img_t.shape[-1]

    # Build breakpoint_positions in dec_feat coordinate space.
    # Gap centres are in original (un-padded) pixel space.
    # Scale: orig → padded → dec_feat (two stages, aligned with train_reid_pilot:682-686).
    positions = torch.zeros(1, K, 2, dtype=torch.float32, device=device)
    for idx, g in enumerate(gaps[:K]):
        cy, cx = g.center_yx
        # Scale orig → padded (pad only adds bottom/right, so orig ≤ padded)
        cy_pad = cy  # no shift (padding is zero-padded at end)
        cx_pad = cx
        # Scale padded → dec_feat (integer division, same as encoder stride)
        cy_dec = cy_pad * H_dec / H_pad
        cx_dec = cx_pad * W_dec / W_pad
        positions[0, idx, 0] = float(cy_dec)
        positions[0, idx, 1] = float(cx_dec)

    # Clamp to valid dec_feat range
    positions[..., 0].clamp_(0, H_dec - 1)
    positions[..., 1].clamp_(0, W_dec - 1)

    with torch.no_grad():
        reid_logits = model.reid_head(
            o_seq              = o_seq,
            dec_feat           = dec_feat,
            breakpoint_positions = positions,
            memory_state       = memory_state,
        )   # (1, K, K)

    logits_np = reid_logits[0].cpu().numpy().astype(np.float32)  # (K, K)

    result = _rrh(logits_np, gaps[:K])
    return result['reid_rate_head'], result['reid_idf1']


# --------------------------------------------------------------------------- #
#  主评估函数
# --------------------------------------------------------------------------- #

def evaluate_adapter(
    adapter_name: str,
    ckpt_path: str | Path,
    data_root: str | Path,
    dataset: str = "DRIVE",
    split: str = "val",
    seed: int = 42,
    threshold: float = 0.5,
    output_csv: Optional[str | Path] = None,
    device_str: str = "cpu",
    use_external_topo: bool = True,
    break_results: Optional[List] = None,
) -> List[Dict[str, Any]]:
    """
    对单个 adapter + ckpt 跑统一三轴评估，输出每张图的 metrics，
    并汇总写入 CSV（若 output_csv 指定）。

    Args:
        adapter_name:      MODEL_REGISTRY 中的 adapter name
        ckpt_path:         best.pth 路径
        data_root:         DRIVE 根目录
        dataset:           数据集名称（CSV 列 dataset）
        split:             'val' | 'train' | 'all'
        seed:              随机种子（CSV 记录用，不影响评估逻辑）
        threshold:         binarization 阈值（default 0.5）
        output_csv:        CSV 输出路径；None → 不写文件
        device_str:        'cpu' | 'cuda' | 'cuda:0'
        use_external_topo: 是否尝试外部 topo 库（False=强制 fallback）
        break_results:     续连轴 BreakResult 列表（与 img_ids 一一对应）；
                           None → 续连轴跳过（置 NaN/0）

    Returns:
        list of per-image metric dicts（也写入 CSV）
    """
    # import 在函数内，避免 top-level 触发注册副作用
    import baselines  # 触发 auto_discover → @register
    from baselines.registry import get_adapter
    from benchmark.tools_topology import compute_topology_suite
    from benchmark.metrics import compute_all_metrics

    device = torch.device(device_str)

    # 1. get adapter
    adapter = get_adapter(adapter_name)

    # 2. build model + load ckpt
    cfg: Dict[str, Any] = {}  # evaluate 时无需超参，只需 build_model 的默认值
    model = adapter.build_model(cfg).to(device)
    ckpt = torch.load(str(ckpt_path), map_location=device, weights_only=True)
    # 支持 state_dict 直存或包在 dict 里
    if isinstance(ckpt, dict) and "state_dict" in ckpt:
        ckpt = ckpt["state_dict"]
    model.load_state_dict(ckpt)
    model.eval()

    data_root = Path(data_root)

    # 3+4. 加载全图样本（统一分发）
    samples = _load_fullimg_dispatch(
        dataset=dataset,
        data_root=data_root,
        split=split,
    )

    # 5. git_commit
    git_commit = _get_git_commit()

    # 6. 逐图评估
    per_image_rows = []

    for i, sample in enumerate(samples):
        img_t = sample["img_t"].to(device)   # (1, 1, H_pad, W_pad)
        gt = sample["gt"]                     # (H, W) np.uint8
        fov = sample["fov"]                   # (H, W) np.uint8
        orig_h = sample["orig_h"]
        orig_w = sample["orig_w"]
        img_id = sample["img_id"]

        # --- forward ---
        logits = adapter.forward_adapt(model, img_t, device)  # (1,1,H_pad,W_pad)
        # 裁掉 padding，还原原始尺寸
        logits_crop = logits[0, 0, :orig_h, :orig_w].cpu()  # (H, W)
        prob = torch.sigmoid(logits_crop).numpy().astype(np.float32)
        pred_bin = (prob >= threshold).astype(np.uint8)

        # --- 轴1 重叠轴 ---
        overlap = _compute_overlap_metrics(pred_bin, gt, fov, pred_prob=prob)

        # --- 轴2 拓扑轴 ---
        # FOV-masked 推理（只在 FOV 内算拓扑，背景圆角不计）
        pred_fov = (pred_bin * fov).astype(np.uint8)
        gt_fov = (gt * fov).astype(np.uint8)
        topo = compute_topology_suite(pred_fov, gt_fov, use_external=use_external_topo)

        topo_source = topo.get("betti_source", "unknown")

        # --- 轴3 续连轴 ---
        # M2: 额外计算 reid_rate_head/reid_idf1（使用 re-ID head 的 (K,K) logits）。
        # 旧 reid_rate (seg-mask) 仍保留双报（不删）。
        reid_rate_head_val = float("nan")
        reid_idf1_val = float("nan")

        if break_results is not None and i < len(break_results):
            br = break_results[i]
            conn = compute_all_metrics(pred_bin, gt, br)
            eps_b0 = conn["epsilon_beta0"]
            sr = conn["success_rate"]
            rr = conn["reid_rate"]
            n_gaps = conn["n_gaps"]

            # M2: re-ID head 前向 — 仅当 model 有 reid_head 且有 gaps 时执行
            if (hasattr(model, 'use_reid_head') and model.use_reid_head
                    and hasattr(model, 'reid_head') and model.reid_head is not None
                    and len(br.gaps) > 0):
                try:
                    reid_rate_head_val, reid_idf1_val = _compute_reid_head_metrics(
                        model=model,
                        img_t=img_t,
                        break_result=br,
                        orig_h=orig_h,
                        orig_w=orig_w,
                        device=device,
                    )
                except Exception as _e:
                    # 非关键路径：reid head 前向失败不应停整个 eval
                    print(f"[evaluate] reid_head forward failed for img {img_id}: {_e}")
        else:
            # 原图无 break → 续连轴跳过，填 NaN/0
            # epsilon_beta0 仍可算（不依赖 break_result）
            from benchmark.metrics import epsilon_beta0 as _eps_b0
            eps_b0 = _eps_b0(pred_bin, gt)
            sr = float("nan")
            rr = float("nan")
            n_gaps = 0

        row = {
            # 元数据
            "dataset": dataset,
            "baseline": adapter_name,
            "kind": adapter.kind,
            "seed": seed,
            "split": split,
            "img_id": img_id,
            # 轴1 重叠
            "dice": overlap["dice"],
            "iou": overlap["iou"],
            "auc": overlap["auc"],
            "se": overlap["se"],
            "sp": overlap["sp"],
            # 轴2 拓扑
            "cldice": topo.get("cldice", float("nan")),
            "betti_b0_err": topo.get("betti_b0_err", float("nan")),
            "betti_b1_err": topo.get("betti_b1_err", float("nan")),
            "skeleton_recall": topo.get("skeleton_recall", float("nan")),
            "topo_source": topo_source,
            # 轴3 续连（旧 seg-mask reid_rate 保留双报）
            "epsilon_beta0": eps_b0,
            "success_rate": sr,
            "reid_rate": rr,
            "n_gaps": n_gaps,
            # 轴3 续连（M2 新增：re-ID head logit 直评）
            "reid_rate_head": reid_rate_head_val,
            "reid_idf1": reid_idf1_val,
            # 追踪
            "ckpt_path": str(ckpt_path),
            "eval_input_mode": "fullimg",
            "threshold": threshold,
            "git_commit": git_commit,
        }
        per_image_rows.append(row)

    # 7. 写 CSV
    if output_csv is not None:
        output_csv = Path(output_csv)
        output_csv.parent.mkdir(parents=True, exist_ok=True)

        fieldnames = [
            "dataset", "baseline", "kind", "seed", "split", "img_id",
            "dice", "iou", "auc", "se", "sp",
            "cldice", "betti_b0_err", "betti_b1_err", "skeleton_recall", "topo_source",
            "epsilon_beta0", "success_rate", "reid_rate", "n_gaps",
            "reid_rate_head", "reid_idf1",   # M2: re-ID head logit direct eval
            "ckpt_path", "eval_input_mode", "threshold", "git_commit",
        ]
        with open(output_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(per_image_rows)

        print(f"[evaluate] wrote {len(per_image_rows)} rows → {output_csv}")

    # 8. 打印摘要
    if per_image_rows:
        mean_dice = float(np.mean([r["dice"] for r in per_image_rows]))
        mean_cldice = float(np.nanmean([r["cldice"] for r in per_image_rows]))
        print(
            f"[evaluate] adapter={adapter_name} split={split} seed={seed} "
            f"mean_dice={mean_dice:.4f} mean_cldice={mean_cldice:.4f}"
        )

    return per_image_rows


# --------------------------------------------------------------------------- #
#  断点续连 benchmark 评测（三轴全含续连轴）
# --------------------------------------------------------------------------- #

def _tiled_inference_numpy(
    model: Any,
    device: "torch.device",
    image: np.ndarray,
    tile_size: int = 512,
    overlap: int = 64,
) -> np.ndarray:
    """
    Sliding-window tiled inference for large full-resolution images.

    Mirrors train_reid_pilot._tiled_inference exactly (BUG2 fix: avoids
    GDN-2 bottleneck sequence > max_seq_len=1024 on images like CHASE 960×999).
    A 512×512 tile → bottleneck 32×32 = 1024 tokens (at limit).

    Args:
        model:     PyTorch model (already .eval(), on device).
        device:    torch.device.
        image:     (H, W) float32 preprocessed image (green+CLAHE+norm).
        tile_size: tile side length in pixels (default 512).
        overlap:   overlap between adjacent tiles (pixels, default 64).

    Returns:
        logit_map: (H, W) float32 averaged raw logits in original image space.
    """
    H_orig, W_orig = image.shape
    stride = tile_size - overlap

    # Pad so full tiles cover every pixel (reflect mode preserves local structure)
    pad_h = (stride - (H_orig - overlap) % stride) % stride
    pad_w = (stride - (W_orig - overlap) % stride) % stride
    img_pad = np.pad(image, ((0, pad_h), (0, pad_w)), mode='reflect')
    H_pad, W_pad = img_pad.shape

    sum_map   = np.zeros((H_pad, W_pad), dtype=np.float64)
    count_map = np.zeros((H_pad, W_pad), dtype=np.float64)

    model.eval()
    with torch.no_grad():
        y0 = 0
        while y0 + tile_size <= H_pad:
            x0 = 0
            while x0 + tile_size <= W_pad:
                y1 = y0 + tile_size
                x1 = x0 + tile_size
                tile_np = img_pad[y0:y1, x0:x1]
                inp = torch.tensor(
                    tile_np, dtype=torch.float32
                ).unsqueeze(0).unsqueeze(0).to(device)   # (1,1,tile,tile)
                out = model(inp)
                # model may return (logits, reid_ctx) tuple or bare logits
                if isinstance(out, tuple):
                    logits_t = out[0]
                else:
                    logits_t = out
                logits_np = logits_t.squeeze(0).squeeze(0).cpu().numpy()
                sum_map[y0:y1, x0:x1]   += logits_np
                count_map[y0:y1, x0:x1] += 1.0
                x0 += stride
            y0 += stride

    logit_map = (sum_map / np.maximum(count_map, 1.0)).astype(np.float32)
    return logit_map[:H_orig, :W_orig]


def _load_manifest_entries(
    benchmark_dir: Path,
    dataset: Optional[str],
    severity: Optional[str],
) -> List[Dict[str, Any]]:
    """
    Read benchmark_dir/manifest.json and filter by dataset + severity.

    Dataset name matching is case-insensitive (lower() both sides), aligned with
    reid_verdict_v2:72 convention (manifest stores lowercase 'drive'/'chase', etc.).

    Args:
        benchmark_dir: path containing manifest.json + npz files.
        dataset:       dataset filter (e.g. 'drive', 'DRIVE'); None = all.
        severity:      severity filter (e.g. 'Medium'); None = all.

    Returns:
        List of manifest entry dicts with 'npz' key pointing to existing files.

    Raises:
        SystemExit(1): manifest not found or no matching entries.
    """
    manifest_path = benchmark_dir / 'manifest.json'
    if not manifest_path.exists():
        print(
            f'[benchmark] ERROR: manifest.json not found in {benchmark_dir}.\n'
            f'  Run: python src/datasets/precompute_benchmark.py --cache_dir {benchmark_dir}',
            file=sys.stderr,
        )
        sys.exit(1)

    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)

    ds_filter  = dataset.lower()  if dataset  is not None else None
    sev_filter = severity          if severity is not None else None

    selected = []
    for entry in manifest:
        if ds_filter  is not None and entry.get('dataset', '').lower() != ds_filter:
            continue
        if sev_filter is not None and entry.get('severity', '') != sev_filter:
            continue
        npz = entry.get('npz', '')
        if npz and Path(npz).exists():
            selected.append(entry)
        else:
            print(f'[benchmark] WARNING: NPZ missing on disk, skipping: {npz}',
                  file=sys.stderr)

    if not selected:
        print(
            f'[benchmark] ERROR: No valid NPZ entries found for '
            f'dataset={dataset!r} severity={severity!r} in {manifest_path}.\n'
            f'  Check precompute_benchmark.py output and manifest.json.',
            file=sys.stderr,
        )
        sys.exit(1)

    return selected


_VALID_SEVERITIES = ("Easy", "Medium", "Hard", "Extreme")

_BENCHMARK_FIELDNAMES = [
    'dataset', 'baseline', 'kind', 'seed', 'split', 'severity', 'img_id',
    'dice', 'iou', 'auc', 'se', 'sp',
    'cldice', 'betti_b0_err', 'betti_b1_err', 'skeleton_recall', 'topo_source',
    'epsilon_beta0', 'success_rate', 'reid_rate', 'n_gaps',
    'reid_rate_head', 'reid_idf1',
    'ckpt_path', 'eval_input_mode', 'threshold', 'git_commit',
]


def _resolve_severity_list(severity: "Optional[str | List[str]]") -> Optional[List[str]]:
    """
    Normalise the severity argument into a list of severity strings or None.

    Rules:
      - None                   → None  (no filter; _load_manifest_entries returns all)
      - 'all'                  → ['Easy', 'Medium', 'Hard', 'Extreme']
      - 'Medium'               → ['Medium']       (single string, backward compat)
      - ['Easy', 'Hard']       → ['Easy', 'Hard']
      - ['all']                → ['Easy', 'Medium', 'Hard', 'Extreme']

    Unknown values raise ValueError.
    """
    if severity is None:
        return None
    if isinstance(severity, str):
        severity = [severity]
    out = []
    for s in severity:
        if s.lower() == 'all':
            out.extend(_VALID_SEVERITIES)
        elif s in _VALID_SEVERITIES:
            out.append(s)
        else:
            raise ValueError(
                f'Unknown severity {s!r}. '
                f'Valid: {_VALID_SEVERITIES} or "all".'
            )
    # Deduplicate while preserving order
    seen: set = set()
    deduped = []
    for s in out:
        if s not in seen:
            seen.add(s)
            deduped.append(s)
    return deduped


def _derive_severity_csv(output_csv: "Optional[Path]", sev: str) -> "Optional[Path]":
    """
    Derive per-severity CSV path from the base output_csv stem.

    Examples:
        'outputs/p3_drive_fr_unet_s42.csv', 'Easy'
        → 'outputs/p3_drive_fr_unet_s42_Easy.csv'

        None → None
    """
    if output_csv is None:
        return None
    p = Path(output_csv)
    return p.parent / f'{p.stem}_{sev}{p.suffix}'


def _run_benchmark_single_severity(
    *,
    adapter: Any,
    adapter_name: str,
    model: Any,
    entries: List[Dict[str, Any]],
    sev: str,
    dataset: Optional[str],
    seed: int,
    threshold: float,
    device: "torch.device",
    use_external_topo: bool,
    data_root: "Optional[Path]",
    ckpt_path: "Path",
    git_commit: str,
    infer_cache: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Inner loop for a single severity level.

    model, adapter, and topology imports are already initialised by the caller
    (evaluate_benchmark). This function only runs the per-image eval loop.

    Args:
        ckpt_path:   Path to the checkpoint (stored verbatim in each CSV row).
        infer_cache: dict keyed by image_id → {'pred_bin', 'prob', 'orig_H', 'orig_W',
                     'inp_t'}.  Populated on first encounter; reused for subsequent
                     severities (safe because severity only affects BreakResult /
                     gap structure, NOT the model input image — by-design in the
                     benchmark construction).

    Returns:
        per-image metric rows for this severity.
    """
    from benchmark.tools_topology import compute_topology_suite
    from benchmark.metrics import compute_all_metrics
    from benchmark.synth_breaks import BreakResult, GapRecord
    from datasets.precompute_benchmark import load_benchmark_sample

    per_image_rows: List[Dict[str, Any]] = []
    data_root_str = str(data_root) if data_root is not None else None

    for entry in entries:
        npz_path = entry['npz']

        # ---- load NPZ sample ----
        sample = load_benchmark_sample(npz_path)

        image_f            = sample.get('image')        # (H,W) float32 or None
        mask_broken        = sample['mask_broken']
        vessel_segment_map = sample['vessel_segment_map']
        gaps_raw           = sample['gaps']
        image_id           = sample['image_id']
        ds_name            = sample['dataset']
        sev_name           = sample['severity']

        if image_f is None:
            print(
                f'[benchmark] WARNING: NPZ {Path(npz_path).name} missing "image" field. '
                f'Re-run precompute_benchmark.py --force to regenerate. Skipping.',
                file=sys.stderr,
            )
            continue

        image_f = image_f.astype(np.float32)

        # ---- GT mask (original, no breaks) ----
        gt_mask = (vessel_segment_map > 0).astype(np.uint8)

        # ---- reconstruct BreakResult (severity-specific — always reload) ----
        gaps = []
        for g in gaps_raw:
            gaps.append(GapRecord(**{
                'gap_id':           g['gap_id'],
                'center_yx':        tuple(g['center_yx']),
                'radius':           g['radius'],
                'gap_size':         g['gap_size'],
                'sigma':            g['sigma'],
                'segment_id_left':  g['segment_id_left'],
                'segment_id_right': g['segment_id_right'],
            }))
        break_result = BreakResult(
            mask_broken        = mask_broken,
            gaps               = gaps,
            vessel_segment_map = vessel_segment_map,
        )

        # ---- MODEL INFERENCE — cache hit avoids redundant forward pass ----
        # Same image_id across severities → same model input image (by benchmark design).
        # Cache key = image_id (unique within a dataset).
        if image_id in infer_cache:
            c = infer_cache[image_id]
            pred_bin = c['pred_bin']
            prob     = c['prob']
            orig_H   = c['orig_H']
            orig_W   = c['orig_W']
            inp_t    = c['inp_t']
        else:
            proc_image, (orig_H, orig_W) = adapter.preprocess_benchmark_image(
                npz_image    = image_f,
                image_id     = image_id,
                dataset_name = ds_name,
                data_root    = data_root_str,
            )
            _proc_t = torch.tensor(proc_image, dtype=torch.float32)
            if _proc_t.ndim == 3:
                # (H', W', C) → (1, C, H', W')  — 多通道 adapter（如 CS-Net RGB）
                inp_t = _proc_t.permute(2, 0, 1).unsqueeze(0).to(device)
            else:
                # (H', W') → (1, 1, H', W')  — 单通道 adapter（默认 green channel）
                inp_t = _proc_t.unsqueeze(0).unsqueeze(0).to(device)

            with torch.no_grad():
                logits_t = adapter.forward_adapt(model, inp_t, device)  # (1, 1, H', W')

            logit_crop = logits_t[0, 0, :orig_H, :orig_W].cpu().numpy().astype(np.float32)
            prob     = (1.0 / (1.0 + np.exp(-logit_crop))).astype(np.float32)
            pred_bin = (prob >= threshold).astype(np.uint8)

            infer_cache[image_id] = {
                'pred_bin': pred_bin,
                'prob':     prob,
                'orig_H':   orig_H,
                'orig_W':   orig_W,
                'inp_t':    inp_t,
            }

        fov = np.ones((orig_H, orig_W), dtype=np.uint8)

        # ---- axis-1 overlap ----
        overlap_m = _compute_overlap_metrics(pred_bin, gt_mask, fov, pred_prob=prob)

        # ---- axis-2 topology ----
        pred_fov = (pred_bin * fov).astype(np.uint8)
        gt_fov   = (gt_mask  * fov).astype(np.uint8)
        topo     = compute_topology_suite(pred_fov, gt_fov, use_external=use_external_topo)
        topo_source = topo.get('betti_source', 'unknown')

        # ---- axis-3 reconnection (HEADLINE: SR / reID / ε_β0) ----
        conn   = compute_all_metrics(pred_bin, gt_mask, break_result)
        eps_b0 = conn['epsilon_beta0']
        sr     = conn['success_rate']
        rr     = conn['reid_rate']
        n_gaps = conn['n_gaps']

        # reid_rate_head / reid_idf1 — only when model has reid_head
        reid_rate_head_val = float('nan')
        reid_idf1_val      = float('nan')
        if (hasattr(model, 'use_reid_head') and model.use_reid_head
                and hasattr(model, 'reid_head') and model.reid_head is not None
                and len(gaps) > 0):
            try:
                reid_rate_head_val, reid_idf1_val = _compute_reid_head_metrics(
                    model        = model,
                    img_t        = inp_t,
                    break_result = break_result,
                    orig_h       = orig_H,
                    orig_w       = orig_W,
                    device       = device,
                )
            except Exception as _e:
                print(f'[benchmark] reid_head forward failed for {image_id}: {_e}',
                      file=sys.stderr)

        row = {
            'dataset':         ds_name,
            'baseline':        adapter_name,
            'kind':            adapter.kind,
            'seed':            seed,
            'split':           'benchmark',
            'severity':        sev_name,
            'img_id':          image_id,
            'dice':            overlap_m['dice'],
            'iou':             overlap_m['iou'],
            'auc':             overlap_m['auc'],
            'se':              overlap_m['se'],
            'sp':              overlap_m['sp'],
            'cldice':          topo.get('cldice', float('nan')),
            'betti_b0_err':    topo.get('betti_b0_err', float('nan')),
            'betti_b1_err':    topo.get('betti_b1_err', float('nan')),
            'skeleton_recall': topo.get('skeleton_recall', float('nan')),
            'topo_source':     topo_source,
            'epsilon_beta0':   eps_b0,
            'success_rate':    sr,
            'reid_rate':       rr,
            'n_gaps':          n_gaps,
            'reid_rate_head':  reid_rate_head_val,
            'reid_idf1':       reid_idf1_val,
            'ckpt_path':       str(ckpt_path),
            'eval_input_mode': 'benchmark_adapter',
            'threshold':       threshold,
            'git_commit':      git_commit,
        }
        per_image_rows.append(row)

    return per_image_rows


def evaluate_benchmark(
    adapter_name: str,
    ckpt_path: "str | Path",
    benchmark_dir: "str | Path",
    dataset: Optional[str] = None,
    severity: "Optional[str | List[str]]" = None,
    seed: int = 42,
    threshold: float = 0.5,
    output_csv: "Optional[str | Path]" = None,
    device_str: str = "cpu",
    use_external_topo: bool = True,
    tile_size: int = 512,
    overlap: int = 64,
    data_root: "Optional[str | Path]" = None,
    extra_cfg: "Optional[Dict[str, Any]]" = None,
) -> List[Dict[str, Any]]:
    """
    Run three-axis evaluation on the frozen breakpoint benchmark.

    This is the BENCHMARK path (断点续连 leaderboard entry):
      - Reads frozen NPZ files from benchmark_dir (precomputed by precompute_benchmark.py).
      - INFERENCE PATH FIX (BUG3): Feeds model via adapter.preprocess_benchmark_image
        + adapter.forward_adapt — same path as train_harness._val_epoch.
        Previously used _tiled_inference_numpy(model, ...) which bypassed adapter
        preprocessing and inference logic, causing FR-UNet dice≈0 (OOD input).
      - adapter.preprocess_benchmark_image returns (img_array, (orig_H, orig_W)):
          - Non-FR-UNet adapters: returns npz 'image' field as-is (green+CLAHE+norm).
          - FR-UNet adapter: reloads from data_root with BT.601+minmax+get_square pipeline.
      - Computes all three axes: overlap (dice/iou/auc/se/sp) + topology (cldice/betti)
        + reconnection (epsilon_beta0 / success_rate / reid_rate — HEADLINE metrics).
      - FOV: benchmark NPZs have no FOV mask → full-image FOV (ones).
        Overlap axis is still computed on full image for consistency.
      - GT for overlap/topo: vessel_segment_map > 0 (original vessel mask before breaks).

    Performance optimisation (multi-severity):
      - model + adapter + ckpt loaded ONCE regardless of how many severities are requested.
      - Same image_id across severities reuses the model forward pass (inference cache).
        Severity only affects BreakResult (gap structure), NOT the input image.
      - topology lib imported once at top of function (not per iteration).
      - Saves ~4× wall-clock vs invoking this function once per severity from a shell loop.

    Args:
        adapter_name:   MODEL_REGISTRY adapter key.
        ckpt_path:      best.pth checkpoint path.
        benchmark_dir:  directory with manifest.json + npz files.
        dataset:        dataset filter (lowercase preferred, e.g. 'drive'). None=all.
        severity:       Severity filter.  Accepted forms:
                          - None                        → no filter (all severities present)
                          - 'Medium'                    → single severity (backward compat)
                          - 'all'                       → ['Easy','Medium','Hard','Extreme']
                          - ['Easy', 'Hard']            → list of severities
                          - ['all']                     → all four severities
                        When multiple severities are given, each severity writes its own
                        CSV (<output_csv_stem>_<Severity>.csv).  All rows are also
                        returned as a combined list.
        seed:           recorded in CSV (does not affect eval logic).
        threshold:      binarisation threshold (default 0.5).
        output_csv:     Base CSV path.
                          - Single severity or None: written as-is.
                          - Multiple severities: split into per-severity files
                            e.g. 'p3_drive_fr_unet_s42.csv' →
                            'p3_drive_fr_unet_s42_Easy.csv',
                            'p3_drive_fr_unet_s42_Medium.csv', ...
        device_str:     'cpu' | 'cuda' | 'cuda:0'.
        use_external_topo: try external topo libs (default True).
        tile_size:      [LEGACY] kept for backward compat; not used in adapter path.
        overlap:        [LEGACY] kept for backward compat; not used in adapter path.
        data_root:      Raw dataset root dir (e.g. /data/vessel/DRIVE). Required
                        by FR-UNet adapter for correct preprocessing (BT.601+minmax).
                        Non-FR-UNet adapters ignore this parameter (use npz image).
                        Pass the dataset-specific root matching --dataset filter.

    Returns:
        list of per-image metric dicts (all severities combined).
        schema identical to evaluate_adapter output, with extra columns:
        severity, image_id already present.

    CSV schema (superset of evaluate_adapter — adds 'severity' column):
        dataset, baseline, kind, seed, split, severity, img_id,
        dice, iou, auc, se, sp,
        cldice, betti_b0_err, betti_b1_err, skeleton_recall, topo_source,
        epsilon_beta0, success_rate, reid_rate, n_gaps,
        reid_rate_head, reid_idf1,
        ckpt_path, eval_input_mode, threshold, git_commit

    Raises:
        SystemExit(1): manifest missing, no matching NPZ, or ckpt not found.
        ValueError: unknown severity value.
    """
    import baselines  # trigger auto_discover → @register
    from baselines.registry import get_adapter

    benchmark_dir = Path(benchmark_dir)
    ckpt_path     = Path(ckpt_path)

    # ---- guard: ckpt exists ----
    if not ckpt_path.exists():
        print(
            f'[benchmark] ERROR: checkpoint not found: {ckpt_path}',
            file=sys.stderr,
        )
        sys.exit(1)

    # ---- resolve severity list ----
    sev_list = _resolve_severity_list(severity)
    # sev_list is None (no filter) or a list of severity strings

    # ---- build adapter + model ONCE ----
    device  = torch.device(device_str)
    adapter = get_adapter(adapter_name)
    # extra_cfg: 外部传入的额外 cfg 项（如 creatis_postproc 的 stage1_ckpt）
    # 优先级：extra_cfg 覆盖默认空 cfg（adapter 内部默认值也遵守）。
    cfg: Dict[str, Any] = dict(extra_cfg) if extra_cfg else {}
    model = adapter.build_model(cfg).to(device)
    ckpt  = torch.load(str(ckpt_path), map_location=device, weights_only=True)
    if isinstance(ckpt, dict) and 'state_dict' in ckpt:
        ckpt = ckpt['state_dict']
    model.load_state_dict(ckpt)
    model.eval()
    print(f'[benchmark] model loaded once: adapter={adapter_name} ckpt={ckpt_path.name}')

    git_commit = _get_git_commit()

    # ---- inference cache: image_id → {pred_bin, prob, orig_H, orig_W, inp_t} ----
    # Shared across all severity iterations — same image, same forward result.
    infer_cache: Dict[str, Dict[str, Any]] = {}

    all_rows: List[Dict[str, Any]] = []

    if sev_list is None:
        # No severity filter → load all entries, run as a single batch
        entries = _load_manifest_entries(benchmark_dir, dataset, None)
        print(f'[benchmark] {len(entries)} NPZ entries matched '
              f'(dataset={dataset!r}, severity=None/all)')
        rows = _run_benchmark_single_severity(
            adapter        = adapter,
            adapter_name   = adapter_name,
            model          = model,
            entries        = entries,
            sev            = 'all',
            dataset        = dataset,
            seed           = seed,
            threshold      = threshold,
            device         = device,
            use_external_topo = use_external_topo,
            data_root      = Path(data_root) if data_root is not None else None,
            ckpt_path      = ckpt_path,
            git_commit     = git_commit,
            infer_cache    = infer_cache,
        )
        all_rows.extend(rows)

        # Write single CSV
        if output_csv is not None:
            _write_benchmark_csv(Path(output_csv), rows)

        _print_benchmark_summary(adapter_name, severity, seed, rows)

    else:
        # One or more explicit severities → loop, write per-severity CSV
        multi_csv = len(sev_list) > 1
        for sev in sev_list:
            entries = _load_manifest_entries(benchmark_dir, dataset, sev)
            print(f'[benchmark] {len(entries)} NPZ entries matched '
                  f'(dataset={dataset!r}, severity={sev!r})')

            csv_path = _derive_severity_csv(
                Path(output_csv) if output_csv is not None else None,
                sev,
            ) if multi_csv else (
                Path(output_csv) if output_csv is not None else None
            )

            rows = _run_benchmark_single_severity(
                adapter        = adapter,
                adapter_name   = adapter_name,
                model          = model,
                entries        = entries,
                sev            = sev,
                dataset        = dataset,
                seed           = seed,
                threshold      = threshold,
                device         = device,
                use_external_topo = use_external_topo,
                data_root      = Path(data_root) if data_root is not None else None,
                ckpt_path      = ckpt_path,
                git_commit     = git_commit,
                infer_cache    = infer_cache,
            )
            all_rows.extend(rows)

            if csv_path is not None:
                _write_benchmark_csv(csv_path, rows)

            _print_benchmark_summary(adapter_name, sev, seed, rows)

    infer_cache_hits = sum(1 for _ in infer_cache)
    print(f'[benchmark] inference cache: {infer_cache_hits} unique images cached '
          f'({len(sev_list or [None])} severity pass(es)); '
          f'total rows={len(all_rows)}')

    return all_rows


def _write_benchmark_csv(output_csv: "Path", rows: List[Dict[str, Any]]) -> None:
    """Write benchmark metric rows to output_csv (creates parent dirs)."""
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(output_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=_BENCHMARK_FIELDNAMES,
                                extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    print(f'[benchmark] wrote {len(rows)} rows → {output_csv}')


def _print_benchmark_summary(
    adapter_name: str,
    severity: "Optional[str]",
    seed: int,
    rows: List[Dict[str, Any]],
) -> None:
    """Print per-severity summary statistics."""
    if not rows:
        return
    mean_dice = float(np.mean([r['dice'] for r in rows]))
    mean_sr   = float(np.nanmean([r['success_rate'] for r in rows]))
    mean_rr   = float(np.nanmean([r['reid_rate'] for r in rows]))
    mean_eps  = float(np.nanmean([r['epsilon_beta0'] for r in rows]))
    print(
        f'[benchmark] adapter={adapter_name} severity={severity} seed={seed}\n'
        f'  mean_dice={mean_dice:.4f}  mean_SR={mean_sr:.4f}'
        f'  mean_reID={mean_rr:.4f}  mean_ε_β0={mean_eps:.4f}'
    )


# --------------------------------------------------------------------------- #
#  CLI 入口
# --------------------------------------------------------------------------- #

def _parse_args():
    p = argparse.ArgumentParser(description="gdn2vessel unified evaluation")
    p.add_argument("--adapter", required=True,
                   help="Adapter name (e.g. ours_gdn2, backbone_unet)")
    p.add_argument("--ckpt", required=True,
                   help="Path to best.pth checkpoint")
    p.add_argument("--data_root", required=True,
                   help="Dataset root directory (contains training/ for DRIVE, etc.)")
    p.add_argument("--dataset", default="DRIVE",
                   help="Dataset name for CSV (default: DRIVE)")
    p.add_argument("--split", default="val", choices=["train", "val", "all"])
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--threshold", type=float, default=0.5)
    p.add_argument("--output_csv", default=None,
                   help="Output CSV path (default: none, print only)")
    p.add_argument("--device", default="cpu",
                   help="'cpu' | 'cuda' | 'cuda:0' (default: cpu)")
    p.add_argument("--no_external_topo", action="store_true",
                   help="Force fallback topo implementations (no external libs)")
    # ---- benchmark mode args (断点续连 leaderboard) ----
    p.add_argument("--benchmark_dir", default=None,
                   help=(
                       "If set, run BENCHMARK evaluation path (三轴含续连轴) instead of "
                       "val-split path. Path to precomputed benchmark cache containing "
                       "manifest.json + npz files (output of precompute_benchmark.py). "
                       "When --data_root is unused in this mode but still required by "
                       "argparse; pass any placeholder if not needed."
                   ))
    p.add_argument("--severity", default=None, nargs="*",
                   metavar="SEV",
                   help=(
                       "Severity filter(s) for benchmark mode. "
                       "Accepted forms: "
                       "  --severity Medium             (single, backward compat) "
                       "  --severity Easy Hard          (multi-value, one CSV per severity) "
                       "  --severity all                (= Easy Medium Hard Extreme) "
                       "  (omitted)                     (no filter = all entries in manifest) "
                       "When multiple severities are given, --output_csv stem is suffixed "
                       "per severity (e.g. p3_s42.csv → p3_s42_Easy.csv). "
                       "Ignored when --benchmark_dir is not set. "
                       "Valid values: Easy Medium Hard Extreme all."
                   ))
    p.add_argument("--tile_size", type=int, default=512,
                   help="Tile size for tiled inference in benchmark mode (default 512).")
    p.add_argument("--tile_overlap", type=int, default=64,
                   help="Tile overlap for benchmark tiled inference (default 64).")
    # ---- creatis_postproc 两段式专用参数 ----
    p.add_argument(
        "--creatis_stage1_ckpt", default=None,
        help=(
            "creatis_postproc 专用：Stage-1 backbone_unet best.pth 路径。"
            "设置后 CreatisPostprocAdapter.build_model 会加载 Stage-1 backbone "
            "到 _stage1_model，forward_adapt 走完整两段式（图像→backbone→creatis）。"
            "不设置则走旧接口（forward_adapt 接收 backbone logits）。"
            "# TODO: 未找到官方源，需 researcher 确认 Stage-1 ckpt HPC 路径"
        ),
    )
    p.add_argument(
        "--creatis_stage1_base_ch", type=int, default=32,
        help=(
            "creatis_postproc 专用：Stage-1 backbone UNet 的 base_ch（默认 32，"
            "与 backbone_unet 统一超参一致）。fr_unet 时忽略。"
        ),
    )
    p.add_argument(
        "--creatis_stage1_adapter", default="backbone_unet",
        choices=["backbone_unet", "fr_unet"],
        help=(
            "creatis_postproc 专用：Stage-1 架构类型。"
            "backbone_unet（默认）= models/unet.py UNet(base_ch)；"
            "fr_unet = FR_UNet(feature_scale=2) — 用户拍板：批1 FR-UNet ckpt 复用当 Stage-1。"
        ),
    )
    return p.parse_args()


def _main():
    args = _parse_args()

    if args.benchmark_dir is not None:
        # ---- BENCHMARK path: 断点续连三轴 (SR/reID/ε_β0 non-NaN) ----
        # Pass dataset as-is; _load_manifest_entries does lower() for case-insensitive match.
        # User explicitly passes --dataset drive (or DRIVE) to filter; default "DRIVE" = filter
        # to DRIVE images.  To skip dataset filter, user should not pass --dataset (TODO: add
        # --no_dataset_filter flag if multi-dataset all-in-one eval is needed later).
        #
        # BUG3 FIX: data_root is now passed to evaluate_benchmark so that FR-UNet adapter
        # can reload images with the correct BT.601+minmax pipeline (vs npz green+CLAHE+norm).
        # Non-FR-UNet adapters ignore data_root (use npz image_f directly).
        # --data_root is still required by argparse even in benchmark mode — now it's used.
        #
        # args.severity from nargs='*':
        #   omitted → None (evaluate_benchmark receives None = no filter)
        #   --severity Medium → ['Medium'] (single element list)
        #   --severity Easy Hard → ['Easy', 'Hard']
        #   --severity all → ['all'] (normalised inside _resolve_severity_list)
        # evaluate_benchmark handles all forms via _resolve_severity_list().
        severity_arg = args.severity  # None or List[str]
        if severity_arg is not None and len(severity_arg) == 0:
            # --severity with no values (edge case: treat as no-filter)
            severity_arg = None

        # ---- extra_cfg: adapter 特有参数 ----
        # creatis_postproc 两段式：stage1_ckpt 传入 cfg，trigger build_model 加载 Stage-1 backbone。
        # 其余 adapter 的 extra_cfg 为空，build_model(cfg={}) 与原行为一致。
        extra_cfg: Optional[Dict[str, Any]] = None
        if args.adapter == "creatis_postproc":
            extra_cfg = {}
            if getattr(args, "creatis_stage1_ckpt", None) is not None:
                extra_cfg["stage1_ckpt"] = args.creatis_stage1_ckpt
                extra_cfg["stage1_base_ch"] = getattr(
                    args, "creatis_stage1_base_ch", 32
                )
                extra_cfg["stage1_adapter"] = getattr(
                    args, "creatis_stage1_adapter", "backbone_unet"
                )
                print(
                    f"[evaluate] creatis_postproc 两段式模式: "
                    f"stage1_ckpt={args.creatis_stage1_ckpt!r}  "
                    f"stage1_adapter={extra_cfg['stage1_adapter']!r}  "
                    f"stage1_base_ch={extra_cfg['stage1_base_ch']}"
                )
            else:
                print(
                    "[evaluate] creatis_postproc: --creatis_stage1_ckpt 未设置，"
                    "将使用旧接口（forward_adapt 接收 backbone logits）。",
                    file=sys.stderr,
                )

        evaluate_benchmark(
            adapter_name      = args.adapter,
            ckpt_path         = args.ckpt,
            benchmark_dir     = args.benchmark_dir,
            dataset           = args.dataset,
            severity          = severity_arg,
            seed              = args.seed,
            threshold         = args.threshold,
            output_csv        = args.output_csv,
            device_str        = args.device,
            use_external_topo = not args.no_external_topo,
            tile_size         = args.tile_size,
            overlap           = args.tile_overlap,
            data_root         = args.data_root,  # BUG3 FIX: pass to adapter.preprocess_benchmark_image
            extra_cfg         = extra_cfg,       # adapter 特有 cfg（creatis Stage-1 ckpt 等）
        )
    else:
        # ---- LEGACY path: val-split overlap+topo only (向后兼容，续连轴 NaN) ----
        evaluate_adapter(
            adapter_name    = args.adapter,
            ckpt_path       = args.ckpt,
            data_root       = args.data_root,
            dataset         = args.dataset,
            split           = args.split,
            seed            = args.seed,
            threshold       = args.threshold,
            output_csv      = args.output_csv,
            device_str      = args.device,
            use_external_topo = not args.no_external_topo,
        )


if __name__ == "__main__":
    _main()
