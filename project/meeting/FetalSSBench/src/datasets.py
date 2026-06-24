"""
datasets.py
===========
FetalSSBench 统一数据 loader，支持 PSFHS 和 HC18 两个数据集。

PSFHS：
  - 读 .mha（SimpleITK），resize 256²
  - 标签 0=背景 1=PS 2=FH，NUM_CLASSES=3

HC18：
  - 读 *_HC.png 灰度图 + 对应 *_HC_Annotation.png（2px 椭圆轮廓）
  - 用 cv2.findContours + cv2.fillPoly 把轮廓填实心 → mask
  - 单前景类(head)，0=背景 1=头，NUM_CLASSES=2
  - resize 256²（图双线性，mask 最近邻）

Split 策略（两个数据集统一）：
  - 固定 seed=42，held-out 20% test（与实验 seed 独立）
  - 从 trainpool 按 label_ratio 取标注子集，其余无标注
  - assert test ∩ train = ∅（红线：评估集不泄漏）

用法：
    from datasets import get_dataloaders, DATASET_INFO
    labeled_loader, unlabeled_loader, test_loader = get_dataloaders(
        dataset="hc18",
        data_dir="path/to/HC18",
        label_ratio=0.1,
        batch_size=4,
        seed=0,
    )
    num_classes = DATASET_INFO["hc18"]["num_classes"]  # 2
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import torch
from PIL import Image
from torch.utils.data import DataLoader, Dataset

# ------------------------------------------------------------------ #
# 数据集元信息（num_classes 含背景）
# ------------------------------------------------------------------ #
DATASET_INFO = {
    "psfhs": {
        "num_classes": 3,   # 0=bg, 1=PS, 2=FH
        "class_names": ["bg", "PS", "FH"],
        "in_channels": 1,
    },
    "hc18": {
        "num_classes": 2,   # 0=bg, 1=head
        "class_names": ["bg", "head"],
        "in_channels": 1,
    },
}

IMAGE_SIZE = 256   # resize 目标

# ------------------------------------------------------------------ #
# PSFHS 相关（从 pilot 迁移，保持兼容）
# ------------------------------------------------------------------ #
_IMAGE_DIR_CANDIDATES = ["image_mha", "images", "img", "Images"]
_LABEL_DIR_CANDIDATES = ["label_mha", "labels", "mask", "seg", "Labels"]


def _find_subdir(root: Path, candidates: List[str]) -> Path:
    """在 root 下（含一级子目录）查找候选目录名。"""
    for name in candidates:
        p = root / name
        if p.is_dir():
            return p
        for sub in root.iterdir():
            if sub.is_dir():
                p2 = sub / name
                if p2.is_dir():
                    return p2
    raise FileNotFoundError(
        f"在 {root} 下未找到目录（尝试了 {candidates}）。"
    )


def _get_mha_ids(img_dir: Path) -> List[str]:
    ids = sorted([p.stem for p in img_dir.glob("*.mha")])
    if not ids:
        raise FileNotFoundError(f"在 {img_dir} 下没有找到 .mha 文件")
    return ids


def _read_mha_as_numpy(path: Path) -> np.ndarray:
    try:
        import SimpleITK as sitk
    except ImportError:
        raise ImportError("缺少 SimpleITK，请 pip install SimpleITK")
    img = sitk.ReadImage(str(path))
    arr = sitk.GetArrayFromImage(img).squeeze()
    if arr.ndim == 3:
        arr = arr[0]
    if arr.ndim != 2:
        raise ValueError(f"读出的 .mha 形状异常: {arr.shape}，路径: {path}")
    return arr.astype(np.float32)


def _normalize(arr: np.ndarray) -> np.ndarray:
    mn, mx = arr.min(), arr.max()
    if mx - mn < 1e-6:
        return np.zeros_like(arr)
    return (arr - mn) / (mx - mn)


def _resize_2d(arr: np.ndarray, size: int, is_label: bool = False) -> np.ndarray:
    """PIL resize。图像用双线性，mask 用最近邻。"""
    mode = Image.NEAREST if is_label else Image.BILINEAR
    # PIL 要求 uint8 或 float；label 转 uint8 前确认值域合理
    if is_label:
        pil = Image.fromarray(arr.astype(np.uint8))
    else:
        # float [0,1] → uint8 再转回（PIL BILINEAR 支持 L mode float）
        pil = Image.fromarray(arr)
        if pil.mode != "F":
            pil = pil.convert("F")
        pil = pil.resize((size, size), Image.BILINEAR)
        return np.array(pil, dtype=np.float32)
    pil = pil.resize((size, size), mode)
    return np.array(pil)


def _random_flip(img: np.ndarray, lbl: np.ndarray):
    """随机左右 + 上下翻转（同步 img 和 lbl）。"""
    if random.random() > 0.5:
        img = np.fliplr(img).copy()
        lbl = np.fliplr(lbl).copy()
    if random.random() > 0.5:
        img = np.flipud(img).copy()
        lbl = np.flipud(lbl).copy()
    return img, lbl


# ------------------------------------------------------------------ #
# HC18 mask 填充
# ------------------------------------------------------------------ #

def _fill_annotation_to_mask(annotation_path: Path, target_size: int = IMAGE_SIZE) -> np.ndarray:
    """
    把 HC18 _Annotation.png（2px 椭圆轮廓）填充成实心 mask。

    策略：
      1. 读原始 Annotation PNG（灰度）
      2. 二值化（像素 > 127 → 前景轮廓）
      3. cv2.findContours 找所有轮廓
      4. cv2.fillPoly 或 cv2.drawContours(thickness=-1) 填实心
      5. resize 到 target_size² (最近邻)

    返回：[H, W] uint8，值域 {0, 1}
    """
    try:
        import cv2
    except ImportError:
        raise ImportError("缺少 opencv-python，请 pip install opencv-python-headless")

    ann = np.array(Image.open(annotation_path).convert("L"), dtype=np.uint8)
    # 二值化（轮廓是白色 255 线）
    _, binary = cv2.threshold(ann, 127, 255, cv2.THRESH_BINARY)

    # HC18 GT 本质是椭圆。2px 轮廓被 findContours 碎成多段→fillPoly 只填环不填盘(已实证 2.7×bug)。
    # 正解：对所有轮廓白点 cv2.fitEllipse 拟合椭圆，再画实心椭圆(thickness=-1)。
    mask = np.zeros_like(binary, dtype=np.uint8)
    pts = np.column_stack(np.where(binary > 0))[:, ::-1]  # (x, y)
    if len(pts) >= 5:  # fitEllipse 需 >=5 点
        try:
            ellipse = cv2.fitEllipse(pts.astype(np.float32))
            cv2.ellipse(mask, ellipse, color=1, thickness=-1)
        except cv2.error:
            # 极少数退化→fallback morphological close + fillPoly
            closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE,
                                      cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
            cnts, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if cnts:
                cv2.fillPoly(mask, [max(cnts, key=cv2.contourArea)], color=1)

    # resize 到目标分辨率（最近邻，保持 binary）
    if mask.shape[0] != target_size or mask.shape[1] != target_size:
        mask_pil = Image.fromarray(mask)
        mask_pil = mask_pil.resize((target_size, target_size), Image.NEAREST)
        mask = np.array(mask_pil, dtype=np.uint8)

    return mask


def _get_hc18_pairs(data_dir: Path) -> List[Tuple[Path, Path]]:
    """
    扫描 HC18 data_dir，返回 (image_path, annotation_path) 对列表，按文件名排序。

    HC18 文件结构：
      {data_dir}/training_set/{N}_HC.png          # 可能含 {N}_2HC.png, {N}_3HC.png
      {data_dir}/training_set/{N}_HC_Annotation.png

    实际可能是双层 training_set/training_set/，这里自动探测。
    """
    # 探测图像目录（可能是双层 training_set/training_set/）
    img_dir = None
    for candidate in [
        data_dir / "training_set" / "training_set",
        data_dir / "training_set",
        data_dir,
    ]:
        pngs = list(candidate.glob("*_HC.png")) if candidate.is_dir() else []
        # 排除 Annotation（不算图像）
        pngs = [p for p in pngs if "_Annotation" not in p.name]
        if pngs:
            img_dir = candidate
            break

    if img_dir is None:
        raise FileNotFoundError(
            f"在 {data_dir} 下未找到 HC18 图像（*_HC.png）。"
            "请确认数据已正确下载。"
        )

    # 只取主视角 *_HC.png（779 例），有意排除多视角 *_2HC/_3HC（220 例）：
    # 多视角=同患者另一切面，混入 train/test 会同患者跨集泄漏。单视角 779 更干净。
    all_imgs = sorted([
        p for p in img_dir.glob("*_HC.png")
        if "_Annotation" not in p.name
    ])

    pairs = []
    for img_path in all_imgs:
        # Annotation 文件名：{stem}_Annotation.png
        ann_name = img_path.stem + "_Annotation.png"
        ann_path = img_dir / ann_name
        if not ann_path.exists():
            raise FileNotFoundError(
                f"找不到对应的 Annotation 文件: {ann_path}\n"
                f"图像: {img_path}"
            )
        pairs.append((img_path, ann_path))

    if not pairs:
        raise FileNotFoundError(f"在 {img_dir} 下没有找到有效的图像-标注对")

    return pairs


# ------------------------------------------------------------------ #
# 通用 split 函数
# ------------------------------------------------------------------ #

def make_splits(
    all_ids: List,
    label_ratio: float,
    seed: int = 0,
    test_seed: int = 42,
    test_ratio: float = 0.2,
) -> Tuple[List, List, List]:
    """
    划分三组：
      - test_ids:      固定 test_seed=42 的 held-out test（不随实验 seed 变化）
      - labeled_ids:   trainpool 中按 label_ratio 取（随实验 seed 变化）
      - unlabeled_ids: trainpool 剩余

    返回 (labeled_ids, unlabeled_ids, test_ids)
    """
    # 固定 test split
    rng_test = random.Random(test_seed)
    ids_copy = list(all_ids)
    rng_test.shuffle(ids_copy)
    n_test = max(1, int(len(ids_copy) * test_ratio))
    test_ids = ids_copy[:n_test]
    trainpool = ids_copy[n_test:]

    # 验证不泄漏（红线）
    test_set_check = set(str(i) for i in test_ids)
    train_set_check = set(str(i) for i in trainpool)
    assert len(test_set_check & train_set_check) == 0, (
        "评估集泄漏！test ∩ train 非空，数据划分有 bug。"
    )

    # 按实验 seed 取标注子集
    rng_label = random.Random(seed)
    pool_shuffled = list(trainpool)
    rng_label.shuffle(pool_shuffled)
    n_labeled = max(1, int(len(pool_shuffled) * label_ratio))
    labeled_ids = pool_shuffled[:n_labeled]
    unlabeled_ids = pool_shuffled[n_labeled:]

    return labeled_ids, unlabeled_ids, test_ids


# ------------------------------------------------------------------ #
# PSFHS Dataset
# ------------------------------------------------------------------ #

class PSFHSDataset(Dataset):
    """
    PSFHS 有标注数据集。
    返回 (image [1,H,W] float32, label [H,W] int64)
    """
    def __init__(self, case_ids: List[str], img_dir: Path, lbl_dir: Path,
                 augment: bool = False, size: int = IMAGE_SIZE):
        self.case_ids = case_ids
        self.img_dir = img_dir
        self.lbl_dir = lbl_dir
        self.augment = augment
        self.size = size

    def __len__(self):
        return len(self.case_ids)

    def __getitem__(self, idx):
        cid = self.case_ids[idx]
        img = _read_mha_as_numpy(self.img_dir / f"{cid}.mha")
        lbl = _read_mha_as_numpy(self.lbl_dir / f"{cid}.mha")

        img = _normalize(img)
        img = _resize_2d(img, self.size, is_label=False)
        lbl = _resize_2d(lbl.astype(np.float32), self.size, is_label=True)

        if self.augment:
            img, lbl = _random_flip(img, lbl)

        img_t = torch.from_numpy(img).unsqueeze(0).float()
        lbl_t = torch.from_numpy(lbl.astype(np.int64)).long()
        return img_t, lbl_t


class PSFHSUnlabeledDataset(Dataset):
    """PSFHS 无标注数据集（只返回图像）。"""
    def __init__(self, case_ids: List[str], img_dir: Path,
                 size: int = IMAGE_SIZE, augment_weak: bool = False):
        self.case_ids = case_ids
        self.img_dir = img_dir
        self.size = size
        self.augment_weak = augment_weak  # FixMatch 弱增广用

    def __len__(self):
        return len(self.case_ids)

    def __getitem__(self, idx):
        cid = self.case_ids[idx]
        img = _read_mha_as_numpy(self.img_dir / f"{cid}.mha")
        img = _normalize(img)
        img = _resize_2d(img, self.size, is_label=False)
        if self.augment_weak:
            img, _ = _random_flip(img, img)  # 无标注，只翻图像
        return torch.from_numpy(img).unsqueeze(0).float()


# ------------------------------------------------------------------ #
# HC18 Dataset
# ------------------------------------------------------------------ #

class HC18Dataset(Dataset):
    """
    HC18 有标注数据集。
    mask 从 _Annotation.png 填充实心生成（cv2 fillPoly）。
    返回 (image [1,H,W] float32, label [H,W] int64)，label ∈ {0,1}
    """
    def __init__(self, pairs: List[Tuple[Path, Path]],
                 augment: bool = False, size: int = IMAGE_SIZE):
        self.pairs = pairs          # [(img_path, ann_path), ...]
        self.augment = augment
        self.size = size
        # 缓存 mask（填充成本高，小数据集可以全部缓存）
        self._mask_cache: dict = {}

    def __len__(self):
        return len(self.pairs)

    def __getitem__(self, idx):
        img_path, ann_path = self.pairs[idx]

        # 读图像（灰度）
        img = np.array(Image.open(img_path).convert("L"), dtype=np.float32)
        img = _normalize(img)
        img = _resize_2d(img, self.size, is_label=False)

        # 生成 mask（带缓存）
        cache_key = str(ann_path)
        if cache_key not in self._mask_cache:
            self._mask_cache[cache_key] = _fill_annotation_to_mask(ann_path, self.size)
        lbl = self._mask_cache[cache_key].copy()

        if self.augment:
            img, lbl = _random_flip(img, lbl)

        img_t = torch.from_numpy(img).unsqueeze(0).float()
        lbl_t = torch.from_numpy(lbl.astype(np.int64)).long()
        return img_t, lbl_t


class HC18UnlabeledDataset(Dataset):
    """HC18 无标注数据集（只返回图像）。"""
    def __init__(self, pairs: List[Tuple[Path, Path]],
                 size: int = IMAGE_SIZE, augment_weak: bool = False):
        # pairs: [(img_path, ann_path)]，我们只用 img_path
        self.img_paths = [p[0] for p in pairs]
        self.size = size
        self.augment_weak = augment_weak

    def __len__(self):
        return len(self.img_paths)

    def __getitem__(self, idx):
        img = np.array(Image.open(self.img_paths[idx]).convert("L"), dtype=np.float32)
        img = _normalize(img)
        img = _resize_2d(img, self.size, is_label=False)
        if self.augment_weak:
            img, _ = _random_flip(img, img)
        return torch.from_numpy(img).unsqueeze(0).float()


# ------------------------------------------------------------------ #
# FixMatch 双增广包装（弱+强同一张图）
# ------------------------------------------------------------------ #

class WeakStrongUnlabeledDataset(Dataset):
    """
    FixMatch 用：对同一无标注图像返回 (weak_aug, strong_aug)。
    弱增广：随机翻转
    强增广：随机翻转 + 随机高斯噪声（模拟颜色抖动 for 超声灰度图）+ 随机擦除

    TODO：可替换为 CTAugment（SSL4MIS ctaugment.py），见 reference/SSL4MIS_hparams.md
    """
    def __init__(self, base_dataset: Dataset):
        """base_dataset 是已经不做增广的底层 Dataset（PSFHSUnlabeledDataset 或 HC18UnlabeledDataset）。"""
        self.base = base_dataset

    def __len__(self):
        return len(self.base)

    def __getitem__(self, idx):
        # 从 base 取原始图像 tensor [1, H, W]
        img_t = self.base[idx]
        img_np = img_t.squeeze(0).numpy()  # [H, W] float32 [0,1]

        # 弱增广
        weak = _weak_aug(img_np)
        # 强增广
        strong = _strong_aug(img_np)

        return (
            torch.from_numpy(weak).unsqueeze(0).float(),
            torch.from_numpy(strong).unsqueeze(0).float(),
        )


def _weak_aug(img: np.ndarray) -> np.ndarray:
    """弱增广：随机左右翻转。"""
    if random.random() > 0.5:
        img = np.fliplr(img).copy()
    return img


def _strong_aug(img: np.ndarray) -> np.ndarray:
    """
    强增广：翻转 + 高斯噪声 + 随机擦除块。
    超声灰度图无法做 color jitter，用噪声模拟亮度扰动。
    TODO：替换为 CTAugment（见 SSL4MIS_hparams.md）
    """
    # 翻转
    if random.random() > 0.5:
        img = np.fliplr(img).copy()
    if random.random() > 0.5:
        img = np.flipud(img).copy()
    # 高斯噪声（σ 随机 0~0.05，模拟亮度抖动）
    noise_sigma = random.uniform(0.0, 0.05)
    img = img + np.random.randn(*img.shape).astype(np.float32) * noise_sigma
    img = np.clip(img, 0.0, 1.0)
    # 随机擦除（1~3 个小块，模拟 Cutout）
    h, w = img.shape
    n_erases = random.randint(1, 3)
    for _ in range(n_erases):
        eh = random.randint(h // 16, h // 6)
        ew = random.randint(w // 16, w // 6)
        y0 = random.randint(0, h - eh)
        x0 = random.randint(0, w - ew)
        img[y0:y0+eh, x0:x0+ew] = random.uniform(0.0, 1.0)  # 随机灰度填充
    return img


# ------------------------------------------------------------------ #
# 统一入口
# ------------------------------------------------------------------ #

def get_dataloaders(
    dataset: str,
    data_dir: str,
    label_ratio: float,
    batch_size: int = 4,
    seed: int = 0,
    num_workers: int = 0,   # Windows spawn 安全：默认 0
    fixmatch_mode: bool = False,  # FixMatch 无标注 loader 返回 (weak, strong) 对
) -> Tuple[DataLoader, DataLoader, DataLoader]:
    """
    统一入口：支持 dataset ∈ {"psfhs", "hc18"}。

    返回 (labeled_loader, unlabeled_loader, test_loader)
      - labeled_loader:   有标注，开增广，drop_last=True
      - unlabeled_loader: 无标注，无增广（fixmatch_mode=True → 返回 (weak,strong) 对）
      - test_loader:      固定 held-out test，无增广，batch_size=4，不 shuffle

    pin_memory=False（Windows spawn 不支持）
    """
    dataset = dataset.lower()
    if dataset not in DATASET_INFO:
        raise ValueError(f"未知 dataset: {dataset}，支持 {list(DATASET_INFO)}")

    data_dir = Path(data_dir)
    if not data_dir.exists():
        raise FileNotFoundError(f"数据目录不存在: {data_dir}")

    if dataset == "psfhs":
        return _get_psfhs_dataloaders(
            data_dir, label_ratio, batch_size, seed, num_workers, fixmatch_mode
        )
    else:  # hc18
        return _get_hc18_dataloaders(
            data_dir, label_ratio, batch_size, seed, num_workers, fixmatch_mode
        )


def _get_psfhs_dataloaders(
    data_dir: Path,
    label_ratio: float,
    batch_size: int,
    seed: int,
    num_workers: int,
    fixmatch_mode: bool,
) -> Tuple[DataLoader, DataLoader, DataLoader]:
    img_dir = _find_subdir(data_dir, _IMAGE_DIR_CANDIDATES)
    lbl_dir = _find_subdir(data_dir, _LABEL_DIR_CANDIDATES)
    print(f"[PSFHS] img_dir: {img_dir}")
    print(f"[PSFHS] lbl_dir: {lbl_dir}")

    all_ids = _get_mha_ids(img_dir)
    print(f"[PSFHS] 共 {len(all_ids)} 例")

    labeled_ids, unlabeled_ids, test_ids = make_splits(all_ids, label_ratio, seed=seed)
    print(
        f"[PSFHS] ratio={label_ratio:.0%} seed={seed} "
        f"labeled={len(labeled_ids)} unlabeled={len(unlabeled_ids)} test={len(test_ids)}"
    )

    labeled_ds = PSFHSDataset(labeled_ids, img_dir, lbl_dir, augment=True)
    test_ds = PSFHSDataset(test_ids, img_dir, lbl_dir, augment=False)

    if fixmatch_mode:
        base_unlabeled = PSFHSUnlabeledDataset(unlabeled_ids, img_dir, augment_weak=False)
        unlabeled_ds = WeakStrongUnlabeledDataset(base_unlabeled)
    else:
        unlabeled_ds = PSFHSUnlabeledDataset(unlabeled_ids, img_dir)

    return _make_loaders(labeled_ds, unlabeled_ds, test_ds, batch_size, num_workers)


def _get_hc18_dataloaders(
    data_dir: Path,
    label_ratio: float,
    batch_size: int,
    seed: int,
    num_workers: int,
    fixmatch_mode: bool,
) -> Tuple[DataLoader, DataLoader, DataLoader]:
    all_pairs = _get_hc18_pairs(data_dir)
    print(f"[HC18] 共 {len(all_pairs)} 对图像-标注")

    # 用文件名 stem 作为 ID，配合 make_splits
    all_stems = [p[0].stem for p in all_pairs]
    stem_to_pair = {p[0].stem: p for p in all_pairs}

    labeled_stems, unlabeled_stems, test_stems = make_splits(all_stems, label_ratio, seed=seed)
    print(
        f"[HC18] ratio={label_ratio:.0%} seed={seed} "
        f"labeled={len(labeled_stems)} unlabeled={len(unlabeled_stems)} test={len(test_stems)}"
    )

    labeled_pairs = [stem_to_pair[s] for s in labeled_stems]
    unlabeled_pairs = [stem_to_pair[s] for s in unlabeled_stems]
    test_pairs = [stem_to_pair[s] for s in test_stems]

    labeled_ds = HC18Dataset(labeled_pairs, augment=True)
    test_ds = HC18Dataset(test_pairs, augment=False)

    if fixmatch_mode:
        base_unlabeled = HC18UnlabeledDataset(unlabeled_pairs, augment_weak=False)
        unlabeled_ds = WeakStrongUnlabeledDataset(base_unlabeled)
    else:
        unlabeled_ds = HC18UnlabeledDataset(unlabeled_pairs)

    return _make_loaders(labeled_ds, unlabeled_ds, test_ds, batch_size, num_workers)


def _make_loaders(
    labeled_ds: Dataset,
    unlabeled_ds: Dataset,
    test_ds: Dataset,
    batch_size: int,
    num_workers: int,
) -> Tuple[DataLoader, DataLoader, DataLoader]:
    common_kw = dict(num_workers=num_workers, pin_memory=False)

    labeled_loader = DataLoader(
        labeled_ds, batch_size=batch_size, shuffle=True,
        drop_last=True, **common_kw
    )
    unlabeled_loader = DataLoader(
        unlabeled_ds, batch_size=batch_size, shuffle=True,
        drop_last=True, **common_kw
    )
    test_loader = DataLoader(
        test_ds, batch_size=4, shuffle=False,
        drop_last=False, **common_kw
    )
    return labeled_loader, unlabeled_loader, test_loader
