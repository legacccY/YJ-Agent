"""
dataset.py
==========
用途：PSFHS 数据集 dataloader。
      - 读 .mha（用 SimpleITK），resize 到 256x256
      - 固定 seed=42 划分：80% trainpool / 20% test
      - 从 trainpool 按 label_ratio 取标注子集 + 剩余为无标注池
      - 标注子集 / 无标注池 / 测试集三路分开，评估集绝不混入训练

怎么用：
    from dataset import get_dataloaders
    labeled_loader, unlabeled_loader, test_loader = get_dataloaders(
        data_dir="data/PSFHS",
        label_ratio=0.1,
        batch_size=4,
        seed=0,
    )
"""

import os
import random
from pathlib import Path
from typing import Tuple, List, Optional

import numpy as np
import torch
from torch.utils.data import Dataset, DataLoader

# SimpleITK 用于读 .mha
try:
    import SimpleITK as sitk
except ImportError:
    raise ImportError("缺少 SimpleITK，请 pip install SimpleITK")


# ---------- 目录名探测（兼容 Zenodo 不同打包方式）----------
_IMAGE_DIR_CANDIDATES = ["image_mha", "images", "img", "Images"]
_LABEL_DIR_CANDIDATES = ["label_mha", "labels", "mask", "seg", "Labels"]

IMAGE_SIZE = 256  # resize 目标


def _find_subdir(root: Path, candidates: List[str]) -> Path:
    """在 root 下（含一级子目录）查找候选目录名，返回第一个找到的 Path。"""
    for name in candidates:
        # 直接子目录
        p = root / name
        if p.is_dir():
            return p
        # 多一层嵌套（有些 zip 带顶层 PSFHS/ 目录）
        for sub in root.iterdir():
            if sub.is_dir():
                p2 = sub / name
                if p2.is_dir():
                    return p2
    raise FileNotFoundError(
        f"在 {root} 下未找到图像目录（尝试了 {candidates}）。\n"
        "请确认数据已正确解压，或手动在 dataset.py 顶部设置 IMAGE_DIR / LABEL_DIR 常量。"
    )


def _get_case_ids(img_dir: Path) -> List[str]:
    """从 image 目录列出所有 case id（stem，不含 .mha 后缀）。"""
    ids = sorted([p.stem for p in img_dir.glob("*.mha")])
    if len(ids) == 0:
        raise FileNotFoundError(f"在 {img_dir} 下没有找到 .mha 文件")
    return ids


def _read_mha_as_numpy(path: Path) -> np.ndarray:
    """
    读 .mha 文件，返回 2D float32 numpy array（H, W）。
    PSFHS 是 2D 超声图像，若读出来是 3D (1,H,W) 或 (H,W,1) 自动 squeeze。
    """
    img = sitk.ReadImage(str(path))
    arr = sitk.GetArrayFromImage(img)  # shape: (Z, H, W) or (H, W) or (H, W, C)
    arr = arr.squeeze()  # 去掉所有大小为 1 的维度
    if arr.ndim == 3:
        # 多通道或多帧：取第一帧/第一通道
        arr = arr[0]
    if arr.ndim != 2:
        raise ValueError(f"读出的 .mha 形状异常: {arr.shape}，路径: {path}")
    return arr.astype(np.float32)


def _normalize(arr: np.ndarray) -> np.ndarray:
    """归一化到 [0, 1]。"""
    mn, mx = arr.min(), arr.max()
    if mx - mn < 1e-6:
        return np.zeros_like(arr)
    return (arr - mn) / (mx - mn)


def _resize_2d(arr: np.ndarray, size: int, is_label: bool = False) -> np.ndarray:
    """
    用简单的 numpy/pillow resize 到 (size, size)。
    图像用双线性，mask 用最近邻（保持离散标签）。
    """
    from PIL import Image
    mode = Image.NEAREST if is_label else Image.BILINEAR
    pil = Image.fromarray(arr)
    pil_r = pil.resize((size, size), mode)
    return np.array(pil_r)


class PSFHSDataset(Dataset):
    """
    PSFHS 2D 超声分割数据集。
    label：0=背景，1=耻骨联合(PS)，2=胎头(FH)
    返回：(image_tensor [1,H,W] float32, label_tensor [H,W] long)
    """

    def __init__(
        self,
        case_ids: List[str],
        img_dir: Path,
        lbl_dir: Path,
        augment: bool = False,
        size: int = IMAGE_SIZE,
    ):
        self.case_ids = case_ids
        self.img_dir = img_dir
        self.lbl_dir = lbl_dir
        self.augment = augment
        self.size = size

    def __len__(self):
        return len(self.case_ids)

    def __getitem__(self, idx):
        cid = self.case_ids[idx]
        img_path = self.img_dir / f"{cid}.mha"
        lbl_path = self.lbl_dir / f"{cid}.mha"

        if not img_path.exists():
            raise FileNotFoundError(f"图像文件不存在: {img_path}")
        if not lbl_path.exists():
            raise FileNotFoundError(f"标签文件不存在: {lbl_path}")

        img = _read_mha_as_numpy(img_path)
        lbl = _read_mha_as_numpy(lbl_path)

        # resize
        img = _resize_2d(img, self.size, is_label=False)
        lbl = _resize_2d(lbl.astype(np.float32), self.size, is_label=True)

        # 归一化图像
        img = _normalize(img)

        # 简单增强（只用于标注样本训练）
        if self.augment:
            img, lbl = _random_flip(img, lbl)

        # 转 tensor
        img_t = torch.from_numpy(img).unsqueeze(0).float()   # [1, H, W]
        lbl_t = torch.from_numpy(lbl.astype(np.int64)).long()  # [H, W]

        return img_t, lbl_t


class UnlabeledPSFHSDataset(Dataset):
    """
    无标注池：只返回图像（Mean Teacher 需要对无标注样本做一致性损失）。
    返回：image_tensor [1,H,W] float32
    """

    def __init__(self, case_ids: List[str], img_dir: Path, size: int = IMAGE_SIZE):
        self.case_ids = case_ids
        self.img_dir = img_dir
        self.size = size

    def __len__(self):
        return len(self.case_ids)

    def __getitem__(self, idx):
        cid = self.case_ids[idx]
        img_path = self.img_dir / f"{cid}.mha"
        if not img_path.exists():
            raise FileNotFoundError(f"图像文件不存在: {img_path}")

        img = _read_mha_as_numpy(img_path)
        img = _resize_2d(img, self.size, is_label=False)
        img = _normalize(img)

        img_t = torch.from_numpy(img).unsqueeze(0).float()
        return img_t


def _random_flip(img: np.ndarray, lbl: np.ndarray):
    """随机左右 + 上下翻转。"""
    if random.random() > 0.5:
        img = np.fliplr(img).copy()
        lbl = np.fliplr(lbl).copy()
    if random.random() > 0.5:
        img = np.flipud(img).copy()
        lbl = np.flipud(lbl).copy()
    return img, lbl


def make_splits(
    case_ids: List[str],
    label_ratio: float,
    seed: int = 42,
) -> Tuple[List[str], List[str], List[str]]:
    """
    从所有 case_ids 划分三组：
      - test_ids:      固定 20%（seed=42，不随 label_ratio/seed 变化）
      - labeled_ids:   trainpool 中随机取 label_ratio 比例（按传入 seed）
      - unlabeled_ids: trainpool 中剩余

    固定 test split：保证评估集不泄漏（评估集始终与训练无关）。
    """
    # 固定测试集（seed=42，与实验 seed 无关）
    rng_test = random.Random(42)
    ids_shuffled = list(case_ids)
    rng_test.shuffle(ids_shuffled)
    n_test = max(1, int(len(ids_shuffled) * 0.2))
    test_ids = ids_shuffled[:n_test]
    trainpool_ids = ids_shuffled[n_test:]

    # 按实验 seed 从 trainpool 取标注子集
    rng_label = random.Random(seed)
    pool_shuffled = list(trainpool_ids)
    rng_label.shuffle(pool_shuffled)
    n_labeled = max(1, int(len(pool_shuffled) * label_ratio))
    labeled_ids = pool_shuffled[:n_labeled]
    unlabeled_ids = pool_shuffled[n_labeled:]

    return labeled_ids, unlabeled_ids, test_ids


def get_dataloaders(
    data_dir: str,
    label_ratio: float,
    batch_size: int = 4,
    seed: int = 0,
    num_workers: int = 0,  # Windows spawn 安全：默认 0
) -> Tuple[DataLoader, DataLoader, DataLoader]:
    """
    返回 (labeled_loader, unlabeled_loader, test_loader)。

    - labeled_loader:   标注子集，开启增强，drop_last=True
    - unlabeled_loader: 无标注池，无增强，batch_size 同
    - test_loader:      测试集，无增强，不 shuffle，batch_size=4
    """
    data_dir = Path(data_dir)
    img_dir = _find_subdir(data_dir, _IMAGE_DIR_CANDIDATES)
    lbl_dir = _find_subdir(data_dir, _LABEL_DIR_CANDIDATES)
    print(f"[dataset] image_dir: {img_dir}")
    print(f"[dataset] label_dir: {lbl_dir}")

    all_ids = _get_case_ids(img_dir)
    print(f"[dataset] 共 {len(all_ids)} 例")

    labeled_ids, unlabeled_ids, test_ids = make_splits(all_ids, label_ratio, seed=seed)
    print(
        f"[dataset] label_ratio={label_ratio:.0%}  seed={seed}  "
        f"labeled={len(labeled_ids)}  unlabeled={len(unlabeled_ids)}  test={len(test_ids)}"
    )

    labeled_ds = PSFHSDataset(labeled_ids, img_dir, lbl_dir, augment=True)
    unlabeled_ds = UnlabeledPSFHSDataset(unlabeled_ids, img_dir)
    test_ds = PSFHSDataset(test_ids, img_dir, lbl_dir, augment=False)

    labeled_loader = DataLoader(
        labeled_ds,
        batch_size=batch_size,
        shuffle=True,
        num_workers=num_workers,
        drop_last=True,
        pin_memory=False,  # Windows spawn 不支持 pin_memory
    )
    unlabeled_loader = DataLoader(
        unlabeled_ds,
        batch_size=batch_size,
        shuffle=True,
        num_workers=num_workers,
        drop_last=True,
        pin_memory=False,
    )
    test_loader = DataLoader(
        test_ds,
        batch_size=4,
        shuffle=False,
        num_workers=num_workers,
        drop_last=False,
        pin_memory=False,
    )

    return labeled_loader, unlabeled_loader, test_loader
