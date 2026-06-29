# -*- coding: utf-8 -*-
"""
数据集 + eval transform + dataloader（Windows 规范：spawn / pin_memory=False / pathlib 路径）

- NIHFrozenDataset：读 NCA-JEPA 的 patient-level 无泄漏 split txt（图名列表），从 Data_Entry_2017.csv
  取 14 类多标签 + Patient ID。__getitem__ -> (img[3,224,224], label[14], patient_id:int, img_name:str)。
- eval transform 复刻 CheXWorld 评测路径（FINETUNE.md: --norm_type default --input_size 224 --resize_size 256）：
  Resize(256, bicubic) -> CenterCrop(224) -> Grayscale(3) -> ToTensor -> Normalize(IMAGENET_DEFAULT)。
  冻结特征抽取一律用此确定性 transform（无随机增强）。
- VinDrClsDataset：跨域 eval 占位（⚠️ VinDr 分类标签可用性 researcher 在核；当前 train_meta.csv 无病理标签）。
"""
import os
from pathlib import Path

import numpy as np
import torch
import torch.utils.data as data
from PIL import Image
from torchvision import transforms
from timm.data.constants import IMAGENET_DEFAULT_MEAN, IMAGENET_DEFAULT_STD

import paths

# NIH ChestX-ray14 14 类病理（顺序严格对齐 CheXWorld repo data_utils/nih.py::NIH.pathologies）
NIH_PATHOLOGIES = ['Atelectasis', 'Cardiomegaly', 'Effusion', 'Infiltration', 'Mass', 'Nodule',
                   'Pneumonia', 'Pneumothorax', 'Consolidation', 'Edema', 'Emphysema',
                   'Fibrosis', 'Pleural_Thickening', 'Hernia']
_PATH_TO_IDX = {p: i for i, p in enumerate(NIH_PATHOLOGIES)}
NUM_CLASSES = len(NIH_PATHOLOGIES)


# ---------------------------------------------------------------------------
# eval transform（确定性，无增强）
# ---------------------------------------------------------------------------
def build_eval_transform(input_size=224, resize_size=256, norm_type='default'):
    if norm_type == 'default':
        mean, std = IMAGENET_DEFAULT_MEAN, IMAGENET_DEFAULT_STD
    else:
        raise NotImplementedError(f'norm_type={norm_type} 未实现；FINETUNE.md 官方 eval 用 default')
    return transforms.Compose([
        transforms.Resize(resize_size, interpolation=Image.BICUBIC),
        transforms.CenterCrop((input_size, input_size)),
        transforms.Grayscale(num_output_channels=3),
        transforms.ToTensor(),
        transforms.Normalize(mean=mean, std=std),
    ])


# ---------------------------------------------------------------------------
# NIH 标签表：img_name -> (label_vec[14] float32, patient_id int)
# ---------------------------------------------------------------------------
def load_nih_label_map(csv_path=None):
    import csv as _csv
    csv_path = csv_path or paths.NIH_CSV
    label_map = {}
    pid_map = {}
    with open(csv_path, 'r', newline='') as f:
        reader = _csv.DictReader(f)
        for row in reader:
            img = row['Image Index'].strip()
            findings = row['Finding Labels'].strip()
            vec = np.zeros(NUM_CLASSES, dtype=np.float32)
            if findings != 'No Finding':
                for fnd in findings.split('|'):
                    fnd = fnd.strip()
                    if fnd in _PATH_TO_IDX:
                        vec[_PATH_TO_IDX[fnd]] = 1.0
            label_map[img] = vec
            pid_map[img] = int(row['Patient ID'])
    return label_map, pid_map


def _read_split(split_txt):
    with open(split_txt, 'r') as f:
        return [ln.strip() for ln in f if ln.strip()]


class NIHFrozenDataset(data.Dataset):
    def __init__(self, split_txt, images_dir=None, transform=None, label_map=None, pid_map=None):
        super().__init__()
        self.images_dir = Path(images_dir or paths.NIH_IMAGES_DIR)
        self.transform = transform or build_eval_transform()
        if label_map is None or pid_map is None:
            label_map, pid_map = load_nih_label_map()
        self.img_names = _read_split(split_txt)
        self.labels = np.stack([label_map[n] for n in self.img_names], axis=0)  # [N,14]
        self.patient_ids = np.array([pid_map[n] for n in self.img_names], dtype=np.int64)
        self.num_classes = NUM_CLASSES

    def __len__(self):
        return len(self.img_names)

    def __getitem__(self, idx):
        name = self.img_names[idx]
        img = Image.open(self.images_dir / name).convert('RGB')
        img = self.transform(img)
        label = torch.from_numpy(self.labels[idx])
        return img, label, int(self.patient_ids[idx]), name


def make_loader(dataset, batch_size=128, num_workers=4, shuffle=False):
    """Windows 规范：spawn context + pin_memory=False（spawn worker 不支持 pin）。"""
    kw = dict(batch_size=batch_size, shuffle=shuffle, num_workers=num_workers,
              pin_memory=False, drop_last=False)
    if num_workers > 0:
        kw['multiprocessing_context'] = 'spawn'
        kw['persistent_workers'] = True
    return data.DataLoader(dataset, **kw)


# ---------------------------------------------------------------------------
# VinDr-CXR 跨域 eval —— 占位（TODO：标签可用性 researcher 在核）
# ---------------------------------------------------------------------------
class VinDrClsDataset(data.Dataset):
    """
    NIH->VinDr 跨域分类 eval 接口骨架。
    ⚠️ 阻塞：VinDr-CXR train_meta.csv 仅含 image_id/dim0/dim1，无病理分类标签。
    需 researcher 回填：
      1. VinDr 官方 image-level 标签 csv（image_labels_*.csv，含 14+ 病理列）路径；
      2. VinDr 标签名 -> NIH 14 类的映射表（VinDr 有 28 类 finding，取与 NIH 重叠/可对齐子集做跨域评测）。
    回填后实现 __getitem__ 返回 (img, label_vec[对齐后的类数], image_id)。
    """
    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            'VinDr 分类标签未就位。待 researcher 回填官方 image-level 标签 csv + VinDr->NIH 类映射；'
            '见 datasets.py::VinDrClsDataset docstring。VINDR_ROOT=%s' % paths.VINDR_ROOT
        )


# VinDr->NIH 类映射占位表（researcher 回填实际重叠类）
VINDR_TO_NIH_LABEL_MAP = None  # TODO: e.g. {'Cardiomegaly':'Cardiomegaly', 'Pleural effusion':'Effusion', ...}


if __name__ == '__main__':
    # 静态自检：只打印类数/transform 结构，不读图、不建 loader（交主线烟测）
    print('NUM_CLASSES =', NUM_CLASSES)
    print('pathologies =', NIH_PATHOLOGIES)
    print('eval_transform =', build_eval_transform())
