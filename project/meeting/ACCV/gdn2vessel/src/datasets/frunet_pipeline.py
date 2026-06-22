"""
frunet_pipeline.py — FR-UNet 官方风格 data pipeline，用于 P1 主实验官方化迁移。

官方源: https://github.com/lseventeen/FR-UNet  (MIT License)
官方论文: Liu et al., JBHI 2022

预处理（完全按官方 data_process.py）：
  1. 灰度单通道：DRIVE/CHASEDB1/STARE 一律用 torchvision.transforms.Grayscale(1)
     （ITU-R 601 加权：0.2989R + 0.5870G + 0.1140B），**非 green channel 单独提取**。
     官方 data_process.py normalize() 路径：PILImage → Grayscale(1)（BT.601 加权）。
     DCA1/CHUAC（本实现未含）官方用 cv2.imread(..., 0)，同 BT.601。
     [FIX Q6] 2026-06-22: 已从 green channel split()[1] 改为 Grayscale(1)，零偏离官方。
  2. Global normalize: 全训练集 pixel mean/std（channel-wise, uint8 → /255 → mean/std）
     官方: transforms.Normalize(mean, std) 作用于 [0,1] float
  3. Per-image minmax → [0,1]
     官方: 归一化后再 minmax，公式 (x-x.min)/(x.max-x.min)
  上述三步离线预处理后 pickle 存盘（官方做法）。Dataset.__getitem__ 直接读 pickle。

增强（完全按官方 dataset.py + utils/helpers.py，仅 training split）：
  - RandomHorizontalFlip(p=0.5)
  - RandomVerticalFlip(p=0.5)
  - Fix_RandomRotation: 等概率选 {-180°,-90°,0°,90°}（各 25%）
  image 与 gt 同 seed 同步（官方用 torch.manual_seed / random.seed 同步）。

Patch（官方训练时）：
  - 48×48 随机切 patch，stride=6 对应 DataLoader 分 patch 策略
  - 官方训练 dataloader: __getitem__ 返回 48×48 patch，外层 batch
    本实现同 base_vessel.py random_crop 逻辑，patch_size=48

Test/eval（官方 tester.py 路径，FIX Q7 2026-06-22）：
  - 官方**无滑窗**。测试用 frunet_get_square() ConstantPad2d padding 到方形
    （DRIVE 584×565 → 592×592；CHASE 960×999 → 1008×1008），整图推理，
    再用 frunet_test_crop() TF.crop(pre,0,0,H,W) 裁回原始 H×W。
  - __getitem__ 在 eval 路径（patch_size=None）返回 pad-to-square 的全图；
    原始 H×W 通过 sample['orig_hw'] 传递给 adapter 做后裁。
  - 之前的 pad_to_multiple(32) 全图 eval 是偏离，已移除（FIX Q7）。

STARE split（FIX Q2 2026-06-22）：
  - FR-UNet 官方 data_process.py STARE 分支对 mode 无判断，
    train_pro=test_pro=全20张（无 hold-out），train=test 共用全集。
  - FRUNetSTARE(official_baseline=True)：复现官方协议，全20张 train=test。
    ⚠️ 本协议有评估泄漏（train=test），仅用于 FR-UNet baseline 数字复现。
  - FRUNetSTARE(official_baseline=False，默认)：用于 GDN-2 主实验评估，
    12/4/4 deterministic hold-out split，防评估泄漏，**不沿用官方 train=test**。
  两套 split 显式分开，防止 GDN-2 主实验误用官方 train=test。

数据路径：从 .portfolio/datasets.json key='vessel_collection_kaggle' 读
  local: D:/YJ-Agent/data/vessel/{DRIVE,CHASE,STARE,HRF,FIVES}/
  hpc:   /gpfs/work/bio/jiayu2403/gdn2vessel/data/vessel/{DRIVE,...}/

Pickle 缓存格式（与官方 data_process.py 兼容）：
  {sid_str: (img_arr: np.float32 (H,W), gt_arr: np.uint8 (H,W) {0,1})}

Windows 规范：
  - 无 scipy.stats，无 multiprocessing（preprocess 单进程 serial）
  - 路径用 pathlib.Path（不含反斜杠）
  - DataLoader 调用侧 multiprocessing_context='spawn', pin_memory=False

TODO / 未核细节（researcher 核实前不改值）：
  [T1] 官方 global mean/std 是在全训练集（包含 patch 前还是全图像素）计算的。
       本实现：全图 pixel mean/std（flatten all H×W pixels across train IDs）。
       官方 data_process.py normalize() 直接对整张图算，应是全图级别，非 patch 级别。
       → 标 TODO: researcher 核确认是全图还是 patch 采样计算。
  [T2] STARE official_baseline 模式下 mean/std 计算用全20张还是无训练划分？
       本实现 official_baseline=True 时用全20张算 mean/std（官方无 train/test 区分）。
       → TODO researcher 核：FR-UNet 官方 STARE 数字是否可复现（可能 LOO+重算？）。
  [T3] FOV mask 在归一化中的作用：官方 data_process.py 中 minmax 是在 FOV 内算
       还是全图像素算？→ TODO researcher 核。
  [T4] HRF：不在官方 FR-UNet（官方仅 DRIVE/CHASEDB1/STARE/CHUAC/DCA1），split 待定。
       → TODO 主线/researcher 确认 HRF 是否纳入 P1 及 split 依据。
  [T5] Per-image minmax 在 global normalize 之前还是之后？
       官方代码顺序：先 Normalize(mean,std) 再 minmax。本实现按此顺序。
       → TODO researcher 二次核官方 transforms pipeline 顺序。
"""

from __future__ import annotations

import pickle
import random
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
import torch
from torch.utils.data import Dataset
import torchvision.transforms as TVT  # for Grayscale(1) BT.601 — FIX Q6

# 继承各集路径/split/GT 读取逻辑，只改 normalize + augment
from datasets.drive import DRIVEDataset
from datasets.chase import CHASEDataset
from datasets.stare import STAREDataset, _STARE_ALL_IDS
from datasets.hrf   import HRFDataset
from datasets.fives import FIVESDataset
from datasets.base_vessel import pad_to_multiple

try:
    from PIL import Image as PILImage
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

# BT.601 Grayscale transform — 官方 FR-UNet 用于 DRIVE/CHASE/STARE（FIX Q6）
# torchvision.transforms.Grayscale(num_output_channels=1) 对 PIL Image 做
# ITU-R 601 加权：L = 0.2989R + 0.5870G + 0.1140B
_GRAYSCALE_TRANSFORM = TVT.Grayscale(num_output_channels=1)


# --------------------------------------------------------------------------- #
#  官方 Fix_RandomRotation — dataset.py 等概率 {-180,-90,0,90}
# --------------------------------------------------------------------------- #

_ROTATION_CHOICES = [-180, -90, 0, 90]  # 官方 4 个角度，各 25%


def _apply_rotation(img: np.ndarray, degree: int) -> np.ndarray:
    """Apply fixed rotation: degree in {-180,-90,0,90}.
    -180 和 180 等价（np.rot90 k=2），-90=k=3, 90=k=1, 0=不转。
    """
    if degree == 0:
        return img
    elif degree == 90:
        return np.rot90(img, 1).copy()
    elif degree == -90:
        return np.rot90(img, 3).copy()
    elif degree in (-180, 180):
        return np.rot90(img, 2).copy()
    else:
        raise ValueError(f"Unexpected rotation degree: {degree}. Must be in {_ROTATION_CHOICES}")


# --------------------------------------------------------------------------- #
#  官方增强函数（image + gt 同 seed 同步）
# --------------------------------------------------------------------------- #

def frunet_augment(
    img: np.ndarray,
    gt: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    官方 FR-UNet 增强（dataset.py + utils/helpers.py 移植，复现零偏离）：
      1. RandomHorizontalFlip(p=0.5)
      2. RandomVerticalFlip(p=0.5)
      3. Fix_RandomRotation: 等概率 {-180,-90,0,90}（各 1/4）

    image 与 gt 共享同一随机数序列 → 同步。
    返回 (img, gt)，均为 np.ndarray (H,W)。
    """
    # ---------- HFlip ----------
    if random.random() < 0.5:
        img = np.fliplr(img).copy()
        gt  = np.fliplr(gt).copy()

    # ---------- VFlip ----------
    if random.random() < 0.5:
        img = np.flipud(img).copy()
        gt  = np.flipud(gt).copy()

    # ---------- Fix_RandomRotation: 等概率 4 个选项 ----------
    degree = random.choice(_ROTATION_CHOICES)
    img = _apply_rotation(img, degree)
    gt  = _apply_rotation(gt, degree)

    return img, gt


# --------------------------------------------------------------------------- #
#  官方 test pad 工具 — tester.py get_square + crop（FIX Q7 2026-06-22）
#
#  官方逻辑（tester.py L40-62 / data_process.py L122-130）：
#    1. get_square(img, target_size): ConstantPad2d 到方形 target_size×target_size
#       padding=0（黑边），保留左上角原始图（top=0,left=0）。
#       target_size 按数据集预设（DRIVE=592, CHASE=1008）。
#    2. 整图推理得 pre（target_size×target_size logit/pred）
#    3. TF.crop(pre, 0, 0, orig_H, orig_W) 裁回原始尺寸
#       （官方用 torchvision.transforms.functional.crop，即 top=0,left=0 裁剪）
#
#  numpy 实现（无 torchvision 依赖于 numpy 路径，兼容 __getitem__ 里的 np.ndarray）：
#  Tensor crop 用 tensor[:, :orig_H, :orig_W] 等价。
#
#  官方各集 target_size（data_process.py get_square 调用行）：
#    DRIVE:    原始 584×565 → pad 到 592×592  (ceil(max(584,565)/32)*32 = 19*32=608? 官方固定 592)
#              TODO researcher 核确认官方 target_size=592 的计算依据（可能取 ceil(565/16)*16*..?）
#    CHASE:    原始 960×999 → pad 到 1008×1008 (官方 tester.py line 40)
#              TODO researcher 核确认 target_size=1008
#    STARE:    官方 STARE test 同 train=test，无需单独 pad（官方 train=test 全图无 pad 路径）
#              → FRUNetSTARE(official_baseline=True) 时按 train patch 走，不走 get_square。
# --------------------------------------------------------------------------- #

# 官方 get_square target_size 预设（TODO researcher 核官方值）
_FRUNET_SQUARE_SIZE: Dict[str, int] = {
    'drive': 592,   # TODO researcher 核：官方 tester.py DRIVE target_size
    'chase': 1008,  # TODO researcher 核：官方 tester.py CHASE target_size
    # 其余数据集官方未标注，用 None 表示不做 get_square（fallback 到 pad_to_square）
}


def frunet_get_square(
    img: np.ndarray,
    target_size: int,
) -> Tuple[np.ndarray, Tuple[int, int]]:
    """
    官方 get_square()：ConstantPad2d 零填充到 target_size×target_size 方形。
    padding 从右/下填充（保留左上角，top=0, left=0），与官方 TF.crop(0,0,H,W) 对应。

    Args:
        img:         (H, W) float32 归一化图像
        target_size: 目标方形边长（如 DRIVE=592, CHASE=1008）

    Returns:
        (padded_img, (orig_H, orig_W))：padded 图像 + 原始尺寸（用于 crop 还原）

    FIX Q7 2026-06-22: 官方无滑窗，test 路径为 pad→整图→crop。
    """
    orig_H, orig_W = img.shape[:2]
    if orig_H > target_size or orig_W > target_size:
        # 如原图比 target_size 大（不应发生，但保护），直接中心 crop（官方未覆盖此 case）
        # TODO researcher 核：官方如何处理超出 target_size 的图
        padded = img[:target_size, :target_size].copy()
    else:
        padded = np.zeros((target_size, target_size), dtype=img.dtype)
        padded[:orig_H, :orig_W] = img
    return padded, (orig_H, orig_W)


def frunet_test_crop(
    pred: np.ndarray,
    orig_H: int,
    orig_W: int,
) -> np.ndarray:
    """
    官方 TF.crop(pre, 0, 0, H, W)：从 pred 左上角裁回原始 H×W。
    numpy 等价：pred[:orig_H, :orig_W]。

    FIX Q7 2026-06-22: 配合 frunet_get_square 使用。
    """
    return pred[:orig_H, :orig_W]


def frunet_test_crop_tensor(
    pred: torch.Tensor,
    orig_H: int,
    orig_W: int,
) -> torch.Tensor:
    """
    Tensor 版 TF.crop（用于 adapter forward 后的 logit/pred tensor 裁剪）：
    pred: (..., target_H, target_W) → (..., orig_H, orig_W)
    FIX Q7 2026-06-22.
    """
    return pred[..., :orig_H, :orig_W]


# --------------------------------------------------------------------------- #
#  官方 Per-image minmax → [0,1]（data_process.py normalization() 末步）
# --------------------------------------------------------------------------- #

def frunet_per_image_minmax(img: np.ndarray) -> np.ndarray:
    """Per-image minmax normalization → [0,1].
    官方公式: (img - img.min) / (img.max - img.min)
    Edge case: constant image → all zeros（避免除以零）。
    """
    vmin = img.min()
    vmax = img.max()
    denom = vmax - vmin
    if denom < 1e-8:
        return np.zeros_like(img, dtype=np.float32)
    return ((img - vmin) / denom).astype(np.float32)


# --------------------------------------------------------------------------- #
#  FRUNetDataset — 核心 Dataset，把官方 pipeline 接到各集
# --------------------------------------------------------------------------- #

class FRUNetDataset(Dataset):
    """
    FR-UNet 官方 data pipeline Dataset — 适配我们 5 集。

    使用方式：
      1. 先用 FRUNetPreprocessor 离线计算 global mean/std + pickle 存盘：
           FRUNetPreprocessor(source_dataset).run(cache_path)
      2. 然后用 FRUNetDataset 加载：
           ds = FRUNetDRIVE(data_root, split='train', cache_path='...', ...)

    source_dataset: 底层各集 Dataset（DRIVEDataset 等），提供
      - ids: List（split IDs）
      - TRAIN_IDS, VAL_IDS, TEST_IDS（split 定义）
      - _load_gt(sid) → (H,W) uint8 {0,1}
      - _load_image_raw(sid) → (H,W) uint8 Grayscale BT.601（FIX Q6）

    cache_path: FRUNetPreprocessor 存的 pickle，内含：
      {
        'mean': float,  # global mean over training set (on [0,1] Grayscale BT.601, FIX Q6)
        'std':  float,  # global std
        'images': {sid_str: np.float32 (H,W)},  # global-normalized + minmax
        'gts':    {sid_str: np.uint8   (H,W)},  # binary GT {0,1}
      }
    """

    def __init__(
        self,
        source_dataset: Dataset,
        split: str = 'train',
        patch_size: Optional[int] = 48,  # 官方: 48×48
        augment: bool = False,
        pad_multiple: int = 32,
        cache_path: Optional[str] = None,
        eval_square_size: Optional[int] = None,  # FIX Q7: 官方 get_square target_size（如 DRIVE=592,CHASE=1008）
    ):
        """
        Args:
            source_dataset:   已构造好的底层 Dataset，提供 _load_gt/_img_path 等。
            split:            'train' | 'val' | 'test' — 决定哪些 ID 进 __getitem__。
            patch_size:       训练时 48（官方）；eval 时 None（走 get_square 整图）。
            augment:          True 仅 training split 时开。
            pad_multiple:     保留接口（eval 路径已改为 get_square，此参数暂不使用）。
            cache_path:       pickle 路径。None → 实时 normalize（仅 minmax，无 global 统计）。
            eval_square_size: FIX Q7 官方 get_square target_size。None 时 eval 路径
                              自动取 max(H,W) 的最小 16 倍数（兜底，非官方原值）。
                              正式复现应传官方值（DRIVE=592, CHASE=1008）。
        """
        super().__init__()
        self._src = source_dataset
        self.split = split
        self.patch_size = patch_size
        self.augment = augment
        self.pad_multiple = pad_multiple
        self.eval_square_size = eval_square_size

        # IDs by split
        if split == 'train':
            self.ids = list(self._src.TRAIN_IDS)
        elif split == 'val':
            self.ids = list(self._src.VAL_IDS)
        elif split == 'test':
            self.ids = list(self._src.TEST_IDS)
        elif split == 'all':
            self.ids = list(self._src.TRAIN_IDS) + list(self._src.VAL_IDS)
        else:
            raise ValueError(f"split must be 'train'/'val'/'test'/'all', got {split!r}")

        # Load pickle cache
        self._cache: Optional[Dict] = None
        if cache_path is not None:
            cache_p = Path(cache_path)
            if cache_p.exists():
                with open(cache_p, 'rb') as f:
                    self._cache = pickle.load(f)
            else:
                raise FileNotFoundError(
                    f"FRUNetDataset: cache_path 不存在: {cache_p}\n"
                    "请先运行 FRUNetPreprocessor.run() 生成 pickle 缓存。"
                )

    def __len__(self) -> int:
        return len(self.ids)

    def __getitem__(self, idx: int) -> dict:
        sid = self.ids[idx]
        sid_str = str(sid)

        # ---------- load image + gt ----------
        if self._cache is not None and sid_str in self._cache.get('images', {}):
            # Cached: global-normalized + minmax 已完成
            img = self._cache['images'][sid_str].copy()   # (H,W) float32
            gt  = self._cache['gts'][sid_str].copy()      # (H,W) uint8
        else:
            # Fallback: no cache → Grayscale BT.601 + per-image minmax only (FIX Q6)
            # (无 global mean/std，警告但不崩)
            img = self._load_image_normalized(sid)        # (H,W) float32
            gt  = self._src._load_gt(sid)                 # (H,W) uint8 {0,1}

        # ---------- augment (training only) ----------
        if self.augment and self.split == 'train':
            img, gt = frunet_augment(img, gt)

        # ---------- patch（train）/ get_square（eval） ----------
        # FIX Q7 2026-06-22: 官方无滑窗 test。
        #   train:  随机裁 48×48 patch（官方训练 dataloader）。
        #   eval:   get_square(target_size) 零填充到方形 → 整图推理 →
        #           adapter 侧用 frunet_test_crop_tensor(pred, orig_H, orig_W) 裁回原始尺寸。
        orig_H, orig_W = img.shape[:2]
        if self.patch_size is not None:
            img, gt = self._random_crop(img, gt, self.patch_size)
            orig_H_out, orig_W_out = self.patch_size, self.patch_size  # patch 无需 crop
        else:
            # eval: 官方 get_square pad 到方形
            target_sz = self.eval_square_size
            if target_sz is None:
                # 兜底：最大边 ceil 到 16 倍数（非官方，需传 eval_square_size 才合规）
                max_side = max(orig_H, orig_W)
                target_sz = int(np.ceil(max_side / 16) * 16)
            img, _ = frunet_get_square(img, target_sz)
            gt_padded = np.zeros((target_sz, target_sz), dtype=gt.dtype)
            gt_padded[:orig_H, :orig_W] = gt
            gt = gt_padded
            orig_H_out, orig_W_out = orig_H, orig_W  # 原始尺寸，供 adapter crop 还原

        # ---------- to tensor ----------
        img_t = torch.from_numpy(img).unsqueeze(0)               # (1,H,W) float32
        gt_t  = torch.from_numpy(gt.astype(np.float32)).unsqueeze(0)  # (1,H,W) float32

        return {
            'image':   img_t,   # (1,H,W) float32, FR-UNet normalized
            'gt':      gt_t,    # (1,H,W) float32 {0,1}
            'fov':     gt_t.new_ones(gt_t.shape),  # 全图 loss（官方 BCELoss 无 FOV mask）
            'id':      sid,
            # FIX Q7: eval 路径下记录原始尺寸，供 adapter frunet_test_crop_tensor 裁回
            # train 路径下为 (patch_size, patch_size)，adapter 不需要此字段
            'orig_hw': (orig_H_out, orig_W_out),
        }

    # ---------------------------------------------------------------------- #
    #  Load raw → Grayscale(1) BT.601 → [0,1] float → per-image minmax
    #  FIX Q6 2026-06-22: 改为官方 torchvision.transforms.Grayscale(1)，不再用 green channel
    #  (无 global normalize；有 cache 时不走此路径)
    # ---------------------------------------------------------------------- #

    def _load_image_normalized(self, sid) -> np.ndarray:
        """Grayscale(1) BT.601 → /255 → per-image minmax → [0,1] float32.
        FIX Q6: 官方 DRIVE/CHASE/STARE 用 Grayscale(1)（ITU-R 601 加权），非 green channel。
        Fallback when no pickle cache. Production 应走 cache 路径。
        """
        img_path = self._src._img_path(sid)
        if _HAS_PIL:
            try:
                pil_rgb = PILImage.open(str(img_path)).convert('RGB')
                pil_gray = _GRAYSCALE_TRANSFORM(pil_rgb)  # PIL L mode, BT.601
                gray_u8 = np.array(pil_gray, dtype=np.uint8)  # (H,W)
                img_f = gray_u8.astype(np.float32) / 255.0
                return frunet_per_image_minmax(img_f)
            except Exception:
                pass  # fallback to cv2 BT.601
        # cv2 fallback: COLOR_BGR2GRAY 也是 BT.601 (0.114B+0.587G+0.299R)
        img_bgr = cv2.imread(str(img_path))
        if img_bgr is None:
            raise IOError(f"FRUNetDataset: cv2 无法读取 {img_path}")
        gray_u8 = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)  # BT.601 等价
        img_f = gray_u8.astype(np.float32) / 255.0
        return frunet_per_image_minmax(img_f)

    # ---------------------------------------------------------------------- #
    #  Spatial helpers
    # ---------------------------------------------------------------------- #

    def _random_crop(
        self, img: np.ndarray, gt: np.ndarray, size: int
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Random crop to size×size. Reflect-pad if image smaller."""
        h, w = img.shape[:2]
        if h < size or w < size:
            pad_h = max(0, size - h)
            pad_w = max(0, size - w)
            img = np.pad(img, ((0, pad_h), (0, pad_w)), mode='reflect')
            gt  = np.pad(gt,  ((0, pad_h), (0, pad_w)), mode='constant')
            h, w = img.shape[:2]
        y0 = random.randint(0, h - size)
        x0 = random.randint(0, w - size)
        return (img[y0:y0 + size, x0:x0 + size],
                gt[y0:y0 + size, x0:x0 + size])

    def _pad_to_multiple(
        self, img: np.ndarray, gt: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        # 保留接口兼容性，但 FIX Q7 后 eval 路径已改为 frunet_get_square。
        # 若有子类显式调用此方法，仍正常工作。
        img_p, _ = pad_to_multiple(img, self.pad_multiple)
        gt_p,  _ = pad_to_multiple(gt,  self.pad_multiple)
        return img_p, gt_p

    # ---------------------------------------------------------------------- #
    #  Split ID accessors (match BaseVesselDataset API for compatibility)
    # ---------------------------------------------------------------------- #

    def get_train_ids(self) -> List:
        return list(self._src.TRAIN_IDS)

    def get_val_ids(self) -> List:
        return list(self._src.VAL_IDS)

    def get_test_ids(self) -> List:
        return list(self._src.TEST_IDS)


# --------------------------------------------------------------------------- #
#  FRUNetPreprocessor — 离线计算 global mean/std + 序列化 pickle
#  对应官方 data_process.py 的 normalization() 函数
# --------------------------------------------------------------------------- #

class FRUNetPreprocessor:
    """
    离线预处理器（data_process.py 风格）：
      1. 遍历训练集所有图像，Grayscale BT.601 → /255 → float32（FIX Q6，改自 green channel）
      2. 计算全集 mean, std（pixel-wise，flatten 所有 H×W）
      3. 对所有 split（train+val+test）做 global normalize + per-image minmax
      4. Pickle 序列化存盘

    TODO[T1]: 官方 normalization() 是否包含 val/test 图像的统计计算？
              本实现：mean/std 只在 train IDs 计算（标准做法），apply 到所有 IDs。
              → researcher 核确认。

    TODO[T3]: 官方 minmax 是否在 FOV 内（masked region）算还是全图？
              本实现：全图（含黑边）。如官方是 FOV-masked minmax，需更新。
              → researcher 核 data_process.py 代码。

    Usage:
        src = DRIVEDataset(data_root, split='train', skip_missing=True)
        pre = FRUNetPreprocessor(src, dataset_name='drive')
        pre.run(cache_path='data/frunet_cache/drive.pkl')
    """

    def __init__(self, source_dataset: Dataset, dataset_name: str = ''):
        """
        Args:
            source_dataset: 底层 Dataset（任何 split 都可，preprocessor 自己选 train IDs 算统计）。
            dataset_name:   仅用于日志打印。
        """
        self._src = source_dataset
        self.dataset_name = dataset_name or self._src.__class__.__name__

    # ---------------------------------------------------------------------- #
    #  Grayscale BT.601 extraction（FIX Q6 2026-06-22）
    #  官方 data_process.py 路径：PILImage → Grayscale(1)（ITU-R 601 加权）
    #  改名 _grayscale_u8（原 _grayscale_u8 是偏离，已修正）
    # ---------------------------------------------------------------------- #

    def _grayscale_u8(self, sid) -> np.ndarray:
        """Load image → Grayscale BT.601 (H,W) uint8.
        FIX Q6: 官方用 torchvision.transforms.Grayscale(1)（ITU-R 601）。
        PIL 路径：PILImage.open → convert('RGB') → Grayscale(1) → L mode array。
        cv2 fallback：COLOR_BGR2GRAY（BT.601 等价）。
        """
        img_path = self._src._img_path(sid)
        if _HAS_PIL:
            try:
                pil_rgb = PILImage.open(str(img_path)).convert('RGB')
                pil_gray = _GRAYSCALE_TRANSFORM(pil_rgb)  # PIL L mode, BT.601
                return np.array(pil_gray, dtype=np.uint8)  # (H,W) uint8
            except Exception:
                pass  # fallback to cv2

        img_bgr = cv2.imread(str(img_path))
        if img_bgr is None:
            raise IOError(f"FRUNetPreprocessor: 无法读取 {img_path}")
        # cv2.cvtColor BGR2GRAY: 0.114*B + 0.587*G + 0.299*R ≈ BT.601
        return cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

    # ---------------------------------------------------------------------- #
    #  Compute global mean/std from training IDs
    # ---------------------------------------------------------------------- #

    def _compute_global_stats(self, train_ids: List) -> Tuple[float, float]:
        """
        全训练集 pixel mean/std（在 [0,1] float 域）。
        官方 data_process.py normalization() 用 Normalize(mean, std)，
        其中 mean/std 由全训练集计算（TODO[T1]：待 researcher 核）。
        """
        all_pixels: List[np.ndarray] = []
        for sid in train_ids:
            try:
                gray_u8 = self._grayscale_u8(sid)
                all_pixels.append(gray_u8.astype(np.float32).ravel() / 255.0)
            except Exception as e:
                print(f"  [WARN] FRUNetPreprocessor: skip {sid}: {e}")
        if not all_pixels:
            print(f"  [WARN] {self.dataset_name}: no training images found, using mean=0 std=1")
            return 0.0, 1.0
        flat = np.concatenate(all_pixels)
        mean = float(flat.mean())
        std  = float(flat.std())
        if std < 1e-8:
            std = 1.0  # constant-image edge case
        return mean, std

    # ---------------------------------------------------------------------- #
    #  Normalize one image: global mean/std → per-image minmax → [0,1]
    #  Official order (TODO[T5]): step1=Normalize, step2=minmax
    # ---------------------------------------------------------------------- #

    def _normalize_image(self, gray_u8: np.ndarray, mean: float, std: float) -> np.ndarray:
        """
        官方双步归一化（data_process.py 顺序，TODO[T5] researcher 核顺序）：
          step1: global normalize: (x/255 - mean) / std
          step2: per-image minmax → [0,1]
        输入: gray_u8 (H,W) uint8，Grayscale BT.601（FIX Q6）。
        Returns (H,W) float32 in [0,1].
        """
        img_f = gray_u8.astype(np.float32) / 255.0
        img_f = (img_f - mean) / max(std, 1e-8)  # global normalize
        img_f = frunet_per_image_minmax(img_f)    # per-image minmax → [0,1]
        return img_f

    # ---------------------------------------------------------------------- #
    #  Run: compute stats + preprocess all IDs + save pickle
    # ---------------------------------------------------------------------- #

    def run(
        self,
        cache_path: str,
        force_recompute: bool = False,
        all_ids: Optional[List] = None,
    ) -> str:
        """
        Compute global stats and preprocess all IDs, save to pickle.

        Args:
            cache_path:      Output pickle file path.
            force_recompute: Recompute even if pickle exists.
            all_ids:         IDs to preprocess. Default: TRAIN+VAL+TEST combined.

        Returns:
            cache_path (str) — for chaining.
        """
        cache_p = Path(cache_path)
        if cache_p.exists() and not force_recompute:
            print(f"[FRUNetPreprocessor] Cache exists: {cache_p} (skip; use force_recompute=True to redo)")
            return str(cache_p)

        cache_p.parent.mkdir(parents=True, exist_ok=True)

        # FIVESDataset: class attrs TRAIN/VAL/TEST_IDS = [] (dynamic discovery).
        # Use instance attrs _train_ids/_val_ids/_test_ids if available.
        if hasattr(self._src, '_train_ids') and self._src._train_ids:
            train_ids = list(self._src._train_ids)
            val_ids   = list(self._src._val_ids)
            test_ids  = list(self._src._test_ids)
        else:
            train_ids = list(self._src.TRAIN_IDS)
            val_ids   = list(self._src.VAL_IDS)
            test_ids  = list(self._src.TEST_IDS)

        if all_ids is None:
            all_ids = train_ids + val_ids + test_ids

        if not all_ids:
            print(f"[FRUNetPreprocessor] WARN: no IDs found for {self.dataset_name}. "
                  "For FIVESDataset, pass all_ids explicitly (see docstring).")
            return str(cache_p)

        print(f"[FRUNetPreprocessor] {self.dataset_name}: computing global mean/std from {len(train_ids)} train IDs...")
        mean, std = self._compute_global_stats(train_ids)
        print(f"  global mean={mean:.6f} std={std:.6f}")

        images: Dict[str, np.ndarray] = {}
        gts:    Dict[str, np.ndarray] = {}

        for sid in all_ids:
            sid_str = str(sid)
            try:
                gray_u8 = self._grayscale_u8(sid)
                img_f = self._normalize_image(gray_u8, mean, std)
                gt    = self._src._load_gt(sid)
                images[sid_str] = img_f
                gts[sid_str]    = gt
            except Exception as e:
                print(f"  [WARN] {self.dataset_name}/{sid}: {e}")

        cache_data = {
            'dataset_name': self.dataset_name,
            'mean': mean,
            'std':  std,
            'images': images,
            'gts':    gts,
        }

        with open(cache_p, 'wb') as f:
            pickle.dump(cache_data, f, protocol=4)

        print(f"[FRUNetPreprocessor] Done. {len(images)} images cached → {cache_p}")
        return str(cache_p)


# --------------------------------------------------------------------------- #
#  Concrete dataset classes for each collection
# --------------------------------------------------------------------------- #
#  每个集只做：(1) 初始化底层 source dataset（路径/split/GT 读取）
#             (2) 调用 FRUNetDataset，传 source dataset
#
#  路径从 .portfolio/datasets.json 'vessel_collection_kaggle' 取，
#  local base: D:/YJ-Agent/data/vessel/ hpc: /gpfs/.../data/vessel/
# --------------------------------------------------------------------------- #


class FRUNetDRIVE(FRUNetDataset):
    """
    FR-UNet pipeline on DRIVE.
    DRIVE split: TRAIN_IDS 21-36 (16), VAL_IDS 37-40 (4), TEST_IDS 1-20 (20官方 test).
    GT: .gif (PIL required)；Image: .tif。
    FIX Q7: eval 路径默认 eval_square_size=592（官方 tester.py，TODO researcher 核）。
    """
    def __init__(
        self,
        data_root: str,
        split: str = 'train',
        patch_size: Optional[int] = 48,
        augment: bool = False,
        pad_multiple: int = 32,
        cache_path: Optional[str] = None,
        skip_missing: bool = False,
        eval_square_size: Optional[int] = 592,  # FIX Q7: DRIVE 官方 get_square 目标尺寸（TODO researcher 核）
    ):
        src = DRIVEDataset(data_root=data_root, split=split,
                           patch_size=None, augment=False,
                           skip_missing=skip_missing)
        # DRIVE: TRAIN_IDS/VAL_IDS/TEST_IDS 是类 attr（整数 list），直接可用
        super().__init__(
            source_dataset=src,
            split=split,
            patch_size=patch_size,
            augment=augment,
            pad_multiple=pad_multiple,
            cache_path=cache_path,
            eval_square_size=eval_square_size,
        )

    def _load_image_normalized(self, sid) -> np.ndarray:
        """DRIVE: PIL Grayscale(1) BT.601 (.tif 兼容）。
        FIX Q6 2026-06-22: 改为 Grayscale(1) 官方做法，去掉 green channel split。
        """
        img_path = self._src._img_path(sid)
        if _HAS_PIL:
            try:
                pil_rgb = PILImage.open(str(img_path)).convert('RGB')
                pil_gray = _GRAYSCALE_TRANSFORM(pil_rgb)  # BT.601
                gray_u8 = np.array(pil_gray, dtype=np.uint8)
                img_f = gray_u8.astype(np.float32) / 255.0
                return frunet_per_image_minmax(img_f)
            except Exception:
                pass
        # fallback cv2 BT.601
        img_bgr = cv2.imread(str(img_path))
        if img_bgr is None:
            raise IOError(f"FRUNetDRIVE: cv2 cannot read {img_path}")
        gray_u8 = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        img_f = gray_u8.astype(np.float32) / 255.0
        return frunet_per_image_minmax(img_f)


class FRUNetCHASE(FRUNetDataset):
    """
    FR-UNet pipeline on CHASE_DB1.
    Split: TRAIN 16 / VAL 4 / TEST 8（official held-out）。
    GT: .tif（cv2 可读）；Image: .tif。
    FIX Q7: eval 路径默认 eval_square_size=1008（官方 tester.py，TODO researcher 核）。
    """
    def __init__(
        self,
        data_root: str,
        split: str = 'train',
        patch_size: Optional[int] = 48,
        augment: bool = False,
        pad_multiple: int = 32,
        cache_path: Optional[str] = None,
        skip_missing: bool = False,
        eval_square_size: Optional[int] = 1008,  # FIX Q7: CHASE 官方 get_square 目标尺寸（TODO researcher 核）
    ):
        src = CHASEDataset(data_root=data_root, split=split,
                           patch_size=None, augment=False,
                           skip_missing=skip_missing)
        super().__init__(
            source_dataset=src,
            split=split,
            patch_size=patch_size,
            augment=augment,
            pad_multiple=pad_multiple,
            cache_path=cache_path,
            eval_square_size=eval_square_size,
        )


class FRUNetSTARE(FRUNetDataset):
    """
    FR-UNet pipeline on STARE.

    ⚠️ 两套 split 协议（FIX Q2 2026-06-22），用 official_baseline 参数区分：

    official_baseline=True（FR-UNet baseline 复现）：
      - 官方 data_process.py STARE 分支对 mode 无判断，train_pro=test_pro=全20张。
      - train=test=全20张，无 hold-out。
      - ⚠️ 此协议有评估泄漏（train 集 == test 集），仅用于复现 FR-UNet 官方数字。
      - self.ids = 全20张，split 参数被忽略。

    official_baseline=False（默认，GDN-2 主实验用）：
      - 12/4/4 deterministic hold-out split，防评估泄漏。
      - 不沿用官方 train=test。
      - 这是 GDN-2 自己的评估协议，与 FR-UNet 官方数字不可直接对比。

    Image/GT: .ppm（cv2 + PIL 均可；STAREDataset 已处理 .ppm.gz fallback）。
    """
    def __init__(
        self,
        data_root: str,
        split: str = 'train',
        patch_size: Optional[int] = 48,
        augment: bool = False,
        pad_multiple: int = 32,
        cache_path: Optional[str] = None,
        skip_missing: bool = False,
        official_baseline: bool = False,  # FIX Q2: True=全20张无split（官方），False=12/4/4（GDN-2主实验）
    ):
        """
        Args:
            official_baseline: True → FR-UNet 官方协议（train=test=全20张，无 hold-out）。
                               False（默认）→ 12/4/4 deterministic split（GDN-2 主实验用）。
                               两套协议显式区分，防 GDN-2 主实验误用官方 train=test 泄漏。
        """
        self.official_baseline = official_baseline

        if official_baseline:
            # FIX Q2: 官方 STARE 无 split，train=test=全20张
            # STAREDataset split='all' 返回 TRAIN_IDS+VAL_IDS（前16），不含最后4
            # 这里直接用 all split 并在 super() 之后手动覆盖 ids
            src = STAREDataset(data_root=data_root, split='train',
                               patch_size=None, augment=False,
                               skip_missing=skip_missing)
            # 调用父类 __init__，随后覆盖 ids 为全20张
            Dataset.__init__(self)
            self._src = src
            self.split = 'all'   # 标记语义：official_baseline 全集
            self.patch_size = patch_size
            self.augment = augment
            self.pad_multiple = pad_multiple
            self.eval_square_size = None
            # 全20张 IDs（官方 train=test）
            self.ids = list(_STARE_ALL_IDS)
            # Load pickle cache（复用父类 cache 逻辑）
            self._cache = None
            if cache_path is not None:
                cache_p = Path(cache_path)
                if cache_p.exists():
                    import pickle as _pkl
                    with open(cache_p, 'rb') as f:
                        self._cache = _pkl.load(f)
                else:
                    raise FileNotFoundError(
                        f"FRUNetSTARE(official_baseline=True): cache_path 不存在: {cache_p}\n"
                        "请先运行 FRUNetPreprocessor.run(all_ids=_STARE_ALL_IDS) 生成 pickle。"
                    )
        else:
            # GDN-2 主实验协议：12/4/4 deterministic hold-out split
            src = STAREDataset(data_root=data_root, split=split,
                               patch_size=None, augment=False,
                               skip_missing=skip_missing)
            super().__init__(
                source_dataset=src,
                split=split,
                patch_size=patch_size,
                augment=augment,
                pad_multiple=pad_multiple,
                cache_path=cache_path,
            )

    def _load_image_normalized(self, sid) -> np.ndarray:
        """STARE .ppm → Grayscale BT.601 → per-image minmax (no cache fallback).
        FIX Q6 2026-06-22: 改为 Grayscale(1) 官方做法，去掉 green channel 提取。
        """
        img_path = self._src._img_path(sid)
        suffixes = ''.join(img_path.suffixes)
        if suffixes == '.ppm.gz':
            from datasets.stare import _load_ppm_gz
            img_bgr = _load_ppm_gz(img_path)
            # cv2 BGR → BT.601 gray
            gray_u8 = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        else:
            if _HAS_PIL:
                try:
                    pil_rgb = PILImage.open(str(img_path)).convert('RGB')
                    pil_gray = _GRAYSCALE_TRANSFORM(pil_rgb)  # BT.601
                    gray_u8 = np.array(pil_gray, dtype=np.uint8)
                    img_f = gray_u8.astype(np.float32) / 255.0
                    return frunet_per_image_minmax(img_f)
                except Exception:
                    pass
            img_bgr = cv2.imread(str(img_path))
            if img_bgr is None:
                raise IOError(f"FRUNetSTARE: cv2 cannot read {img_path}")
            gray_u8 = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        img_f = gray_u8.astype(np.float32) / 255.0
        return frunet_per_image_minmax(img_f)


class FRUNetHRF(FRUNetDataset):
    """
    ⚠️ 非官方 FR-UNet 扩展 — HRF 不在官方 FR-UNet 数据集列表中。
    官方 lseventeen/FR-UNet 仅包含：DRIVE / CHASEDB1 / STARE / CHUAC / DCA1。
    HRF 适配器为 GDN-2 扩展实验，无官方 FR-UNet baseline 对应数字。

    # TODO 主线/researcher 确认 HRF 是否纳入 P1 实验及 split 依据。
    # 当前 split：TRAIN 12(healthy) / VAL 3(healthy) / TEST 30(dr+glaucoma)
    # 此 split 无官方 FR-UNet 依据，属临时约定，不可作为 FR-UNet baseline 复现。

    Image: .jpg / .JPG（大小写鲁棒，HRFDataset 已处理）。
    官方 FOV: roi_masks/ 有真实 FOV mask；FR-UNet 是否用 FOV → TODO[T3]。
    """
    def __init__(
        self,
        data_root: str,
        split: str = 'train',
        patch_size: Optional[int] = 48,
        augment: bool = False,
        pad_multiple: int = 32,
        cache_path: Optional[str] = None,
        skip_missing: bool = False,
    ):
        # TODO 主线/researcher 确认 HRF 是否纳入 P1 及 split 依据，当前 split 无官方源。
        src = HRFDataset(data_root=data_root, split=split,
                         patch_size=None, augment=False,
                         skip_missing=skip_missing)
        super().__init__(
            source_dataset=src,
            split=split,
            patch_size=patch_size,
            augment=augment,
            pad_multiple=pad_multiple,
            cache_path=cache_path,
        )


class FRUNetFIVES(FRUNetDataset):
    """
    FR-UNet pipeline on FIVES.
    Split: 动态发现（train_ 前缀 600 张 / test_ 前缀 200 张 + 10% val）。
    Image/GT: .png（cv2 可读）。

    注意：FIVESDataset 用动态 id 发现，TRAIN/VAL/TEST 类 attr 是 []，
    实例 _train_ids/_val_ids/_test_ids 保存真实 ids。
    FRUNetDataset 里需从实例读，而非类 attr。
    """
    def __init__(
        self,
        data_root: str,
        split: str = 'train',
        patch_size: Optional[int] = 48,
        augment: bool = False,
        pad_multiple: int = 32,
        cache_path: Optional[str] = None,
        skip_missing: bool = False,
    ):
        src = FIVESDataset(data_root=data_root, split=split,
                           patch_size=None, augment=False,
                           skip_missing=skip_missing)
        # FIVESDataset 的真实 ids 在实例属性，需要 patch class attrs 为实例值
        # 让 FRUNetDataset 的 split-branch 能正确取到 ids。
        # 这里直接绕开 super().__init__，手动设置 ids：
        Dataset.__init__(self)
        self._src = src
        self.split = split
        self.patch_size = patch_size
        self.augment = augment
        self.pad_multiple = pad_multiple

        # Use instance-level ids from FIVESDataset
        if split == 'train':
            self.ids = list(src._train_ids)
        elif split == 'val':
            self.ids = list(src._val_ids)
        elif split == 'test':
            self.ids = list(src._test_ids)
        elif split == 'all':
            self.ids = list(src._train_ids) + list(src._val_ids)
        else:
            raise ValueError(f"split must be train/val/test/all, got {split!r}")

        # Load pickle cache (replicate parent logic)
        self._cache = None
        if cache_path is not None:
            cache_p = Path(cache_path)
            if cache_p.exists():
                with open(cache_p, 'rb') as f:
                    self._cache = pickle.load(f)
            else:
                raise FileNotFoundError(
                    f"FRUNetFIVES: cache_path 不存在: {cache_p}\n"
                    "请先运行 FRUNetPreprocessor.run() 生成 pickle 缓存。"
                )

    # Override split ID accessors for FIVES (instance-level)
    def get_train_ids(self) -> List:
        return list(self._src._train_ids)

    def get_val_ids(self) -> List:
        return list(self._src._val_ids)

    def get_test_ids(self) -> List:
        return list(self._src._test_ids)


# --------------------------------------------------------------------------- #
#  Convenience factory: get dataset by name
# --------------------------------------------------------------------------- #

_FRUNET_DATASET_MAP = {
    'drive': FRUNetDRIVE,
    'chase': FRUNetCHASE,
    'stare': FRUNetSTARE,
    'hrf':   FRUNetHRF,
    'fives': FRUNetFIVES,
}


def make_frunet_dataset(
    name: str,
    data_root: str,
    split: str = 'train',
    patch_size: Optional[int] = 48,
    augment: bool = False,
    cache_path: Optional[str] = None,
    skip_missing: bool = False,
    stare_official_baseline: bool = False,  # FIX Q2: STARE 官方协议（True=全20张，False=GDN-2 held-out）
) -> FRUNetDataset:
    """
    Factory: 按 name 构造对应 FR-UNet Dataset 实例。

    Args:
        name:       'drive' | 'chase' | 'stare' | 'hrf' | 'fives'
        data_root:  dataset 根目录（从 datasets.json 读，例如 D:/YJ-Agent/data/vessel/DRIVE）
        split:      'train' | 'val' | 'test'
        patch_size: 训练 48；eval None
        augment:    True 仅 training
        cache_path: FRUNetPreprocessor 生成的 pickle 路径
        skip_missing: 路径验证宽松（HPC 同步中时用）
        stare_official_baseline: FIX Q2 — 仅对 name='stare' 生效。
            True：官方 FR-UNet STARE 协议（train=test=全20张，有评估泄漏，仅用于复现官方数字）。
            False（默认）：GDN-2 主实验 12/4/4 held-out split（防泄漏）。

    Example（从 datasets.json 取路径）：
        import json, pathlib
        ds_json = json.loads(pathlib.Path('.portfolio/datasets.json').read_text())
        drive_root = 'D:/YJ-Agent/data/vessel/DRIVE'
        ds = make_frunet_dataset('drive', drive_root, split='train',
                                 cache_path='data/frunet_cache/drive.pkl')

        # FR-UNet STARE 官方 baseline 复现（train=test=全20张）：
        ds_stare_repro = make_frunet_dataset('stare', stare_root,
                                             stare_official_baseline=True)
        # GDN-2 主实验（held-out split）：
        ds_stare_gdn = make_frunet_dataset('stare', stare_root,
                                           split='test', stare_official_baseline=False)
    """
    name = name.lower()
    if name not in _FRUNET_DATASET_MAP:
        raise ValueError(f"Unknown dataset: {name!r}. Choose from {list(_FRUNET_DATASET_MAP)}")
    cls = _FRUNET_DATASET_MAP[name]
    kwargs: Dict = dict(
        data_root=data_root,
        split=split,
        patch_size=patch_size,
        augment=augment,
        cache_path=cache_path,
        skip_missing=skip_missing,
    )
    if name == 'stare':
        kwargs['official_baseline'] = stare_official_baseline
    return cls(**kwargs)
