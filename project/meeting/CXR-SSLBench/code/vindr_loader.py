# -*- coding: utf-8 -*-
"""
VinDr-CXR 跨域 eval loader（C4：NIH→VinDr 跨域退化，每 backbone VinDr-train 训 probe、VinDr-test 评）。

数据真源（.portfolio/datasets.json -> paths.VINDR_ROOT）：
  labels/image_labels_train.csv : 45000 数据行 = 15000 image_id × 3 放射师(rad_id R8/R9/R10...)，28 类 finding 列。
  labels/image_labels_test.csv  :  3000 数据行 = 3000 image_id（官方已聚合，无 rad_id 列）。
  train/<image_id>.png / test/<image_id>.png : 本地解压图（各 15000 / 3000）。

核心职责：
  1. train 按 image_id 聚合 3 放射师 -> 每图一个多热标签（method='union' 并集(默认) | 'majority' 多数票）。
  2. NIH∩VinDr 共享类映射（SHARED_CLASS_MAP_DEFAULT，~11 类）—— **参数位**，重训前主线冻结(TODO-E)，
     此处给可配置默认（矩阵 §4 列）。NIH 侧 Mass∪Nodule 对齐 VinDr 单列 'Nodule/Mass'。
  3. VinDrCrossDomainDataset：image_id join 本地 png，__getitem__ 契约对齐 datasets.NIHFrozenDataset
     -> (img[3,224,224], label[len(shared)], id_int, image_id_str)。

R5 无泄漏：VinDr 官方 train/test 为不同 study/image 集，image_id 全不相交（probe 训 train、评 test）。
  surrogate patient_id = int(image_id[:15],16)（image_id 为 32-hex；取前 15 位 -> <2^60 安全装 int64），
  供 probes.assert_no_patient_leak 做 train∩test=∅ 断言（红线 R4 评估泄漏）。

Windows 规范：pathlib 路径；spawn loader（复用 datasets.make_loader）；csv 编码 try utf-8 -> latin1。

⚠️ 标签 csv 解析 + 聚合 + 类映射为纯 numpy/csv（pytest 可测，无 GPU）；
   extract_vindr_pooled 为 GPU 特征抽取薄包装（ViT forward），写好 --smoke 入口但**不自跑**，交主线烟测。
"""
import os
import csv as _csv
import argparse
from pathlib import Path

import numpy as np

import paths


# ---------------------------------------------------------------------------
# 路径（从 paths.VINDR_ROOT 派生，禁硬编码）
# ---------------------------------------------------------------------------
def vindr_labels_dir():
    return os.path.join(paths.VINDR_ROOT, 'labels')


def vindr_images_dir(split):
    """split in {'train','test'} -> 本地 png 目录。"""
    assert split in ('train', 'test'), f'split 须为 train/test，得到 {split}'
    return os.path.join(paths.VINDR_ROOT, split)


def vindr_labels_csv(split):
    return os.path.join(vindr_labels_dir(), f'image_labels_{split}.csv')


# ---------------------------------------------------------------------------
# NIH∩VinDr 共享类映射（参数位；默认 = 矩阵 §4 的 ~11 类；TODO-E 重训前主线冻结）
# 每项 = (canonical_name(NIH 侧/输出名), [VinDr 列名列表])；canonical 取值 = 其 VinDr 列的 OR。
#   - Effusion        <-> 'Pleural effusion'
#   - Fibrosis        <-> 'Pulmonary fibrosis'
#   - Pleural_Thickening <-> 'Pleural thickening'
#   - Mass_Nodule     <-> 'Nodule/Mass'（NIH 侧 Mass∪Nodule 合并对齐 VinDr 单列）
# ---------------------------------------------------------------------------
SHARED_CLASS_MAP_DEFAULT = [
    ('Atelectasis',         ['Atelectasis']),
    ('Cardiomegaly',        ['Cardiomegaly']),
    ('Effusion',            ['Pleural effusion']),
    ('Infiltration',        ['Infiltration']),
    ('Mass_Nodule',         ['Nodule/Mass']),
    ('Pneumothorax',        ['Pneumothorax']),
    ('Consolidation',       ['Consolidation']),
    ('Edema',               ['Edema']),
    ('Emphysema',           ['Emphysema']),
    ('Fibrosis',            ['Pulmonary fibrosis']),
    ('Pleural_Thickening',  ['Pleural thickening']),
]


def shared_class_names(shared_map=None):
    shared_map = shared_map or SHARED_CLASS_MAP_DEFAULT
    return [name for name, _ in shared_map]


# ---------------------------------------------------------------------------
# csv 读取（编码 fallback）
# ---------------------------------------------------------------------------
def _read_csv_rows(path):
    """返回 (fieldnames, rows[list[dict]])；编码先 utf-8(-sig) 后 latin1。"""
    assert os.path.exists(path), f'VinDr 标签 csv 不存在: {path}'
    for enc in ('utf-8-sig', 'utf-8', 'latin1'):
        try:
            with open(path, 'r', newline='', encoding=enc) as f:
                reader = _csv.DictReader(f)
                rows = list(reader)
                return reader.fieldnames, rows
        except UnicodeDecodeError:
            continue
    raise UnicodeError(f'VinDr csv 三种编码(utf-8-sig/utf-8/latin1)均解码失败: {path}')


def _row_class_vec(row, shared_map):
    """单行(单放射师/test 单图) -> 各共享类 0/1 向量；canonical = 其 VinDr 列的 OR。"""
    vec = np.zeros(len(shared_map), dtype=np.float32)
    for ci, (_, vindr_cols) in enumerate(shared_map):
        present = 0
        for col in vindr_cols:
            v = row.get(col, '0')
            v = (v or '0').strip()
            if v not in ('', '0', '0.0'):
                present = 1
                break
        vec[ci] = float(present)
    return vec


# ---------------------------------------------------------------------------
# 聚合：train(多放射师) / test(已聚合)
# ---------------------------------------------------------------------------
def aggregate_train_labels(rows, shared_map=None, method='union'):
    """
    train rows（每 image_id 多放射师）-> {image_id: label_vec[len(shared)]}。
      method='union'   : 任一放射师标阳即阳（max over rads，默认）。
      method='majority': 阳性放射师数 > 放射师总数/2 才算阳（3 rad -> 需 >=2；2 rad -> 需 >=2）。
    """
    shared_map = shared_map or SHARED_CLASS_MAP_DEFAULT
    assert method in ('union', 'majority'), f'method 须为 union/majority，得到 {method}'
    votes = {}   # image_id -> 累加阳性票数向量
    counts = {}  # image_id -> 放射师行数
    for row in rows:
        iid = row['image_id'].strip()
        v = _row_class_vec(row, shared_map)
        if iid not in votes:
            votes[iid] = np.zeros(len(shared_map), dtype=np.float32)
            counts[iid] = 0
        votes[iid] += v
        counts[iid] += 1
    out = {}
    for iid, vsum in votes.items():
        n = counts[iid]
        if method == 'union':
            out[iid] = (vsum >= 1.0).astype(np.float32)
        else:  # majority：严格多数（> n/2）
            out[iid] = (vsum > (n / 2.0)).astype(np.float32)
    return out


def parse_test_labels(rows, shared_map=None):
    """test rows（每 image_id 一行，官方已聚合）-> {image_id: label_vec[len(shared)]}。"""
    shared_map = shared_map or SHARED_CLASS_MAP_DEFAULT
    out = {}
    for row in rows:
        iid = row['image_id'].strip()
        out[iid] = _row_class_vec(row, shared_map)
    return out


def load_vindr_labels(split, aggregate='union', shared_map=None, labels_csv=None):
    """
    返回 (image_ids[list[str]], labels[np.ndarray N×len(shared)], class_names[list[str]])。
    split='train' -> 多放射师聚合(aggregate)；split='test' -> 直接解析(官方已聚合)。
    """
    shared_map = shared_map or SHARED_CLASS_MAP_DEFAULT
    csv_path = labels_csv or vindr_labels_csv(split)
    fieldnames, rows = _read_csv_rows(csv_path)
    has_rad = fieldnames is not None and 'rad_id' in fieldnames
    if split == 'train' or has_rad:
        lab_map = aggregate_train_labels(rows, shared_map=shared_map, method=aggregate)
    else:
        lab_map = parse_test_labels(rows, shared_map=shared_map)
    image_ids = sorted(lab_map.keys())
    labels = np.stack([lab_map[i] for i in image_ids], axis=0).astype(np.float32)
    return image_ids, labels, shared_class_names(shared_map)


# ---------------------------------------------------------------------------
# surrogate patient_id（image_id 32-hex；前 15 位 -> <2^60 安全 int64，供无泄漏断言）
# ---------------------------------------------------------------------------
def imgid_to_int(image_id):
    return int(str(image_id).strip()[:15], 16)


# ---------------------------------------------------------------------------
# 跨域 Dataset（契约对齐 datasets.NIHFrozenDataset）
# torch/PIL/torchvision/datasets 惰性 import，使纯标签逻辑可在无重依赖环境 pytest。
# ---------------------------------------------------------------------------
def make_vindr_dataset(split, aggregate='union', shared_map=None, transform=None,
                       images_dir=None, labels_csv=None):
    """工厂：返回 VinDrCrossDomainDataset 实例（torch 在调用时才 import）。"""
    import torch.utils.data as _data  # noqa: F401（仅确保 torch 可用）
    return VinDrCrossDomainDataset(split, aggregate=aggregate, shared_map=shared_map,
                                   transform=transform, images_dir=images_dir, labels_csv=labels_csv)


try:
    import torch.utils.data as _tud

    class VinDrCrossDomainDataset(_tud.Dataset):
        """
        VinDr 跨域分类 eval dataset。
        __getitem__ -> (img[3,224,224], label[len(shared)] float32, id_int:int, image_id:str)
        与 datasets.NIHFrozenDataset 同契约，可被 extract_features 的抽取循环消费（主线把 domain='vindr'
        路由到此即可；datasets.py/extract_features.py 在块B 领地外为只读，路由是一行 main-thread TODO）。
        """
        def __init__(self, split, aggregate='union', shared_map=None, transform=None,
                     images_dir=None, labels_csv=None):
            super().__init__()
            self.split = split
            self.images_dir = Path(images_dir or vindr_images_dir(split))
            self.shared_map = shared_map or SHARED_CLASS_MAP_DEFAULT
            self.image_ids, self.labels, self.class_names = load_vindr_labels(
                split, aggregate=aggregate, shared_map=self.shared_map, labels_csv=labels_csv)
            self.patient_ids = np.array([imgid_to_int(i) for i in self.image_ids], dtype=np.int64)
            self.num_classes = len(self.class_names)
            if transform is None:
                import datasets as _D  # 惰性：复用 CheXWorld 评测 transform（224+ImageNet norm）
                transform = _D.build_eval_transform()
            self.transform = transform

        def __len__(self):
            return len(self.image_ids)

        def __getitem__(self, idx):
            import torch
            from PIL import Image
            iid = self.image_ids[idx]
            img = Image.open(self.images_dir / f'{iid}.png').convert('RGB')
            img = self.transform(img)
            label = torch.from_numpy(self.labels[idx])
            return img, label, int(self.patient_ids[idx]), iid

except Exception:  # torch 不在环境（纯标签测试场景）—— 跳过 Dataset 定义，不阻断标签逻辑 import
    VinDrCrossDomainDataset = None


# ---------------------------------------------------------------------------
# GPU 特征抽取薄包装（pooled，写 EF 兼容 npz）—— 写好 --smoke，**coder 不跑**，交主线烟测
# 产物键对齐 extract_features：feats/labels/patient_ids/img_names，使 eval_collect/EF.load_pooled_cache 可读。
# ---------------------------------------------------------------------------
def extract_vindr_pooled(backbone_name, split, aggregate='union', shared_map=None,
                         device='cuda', batch_size=128, num_workers=4, smoke=0, overwrite=False):
    import torch
    import backbones
    import datasets as D
    import extract_features as EF

    os.makedirs(paths.CACHE_DIR, exist_ok=True)
    stem = f'vindr_{split}_{aggregate}'
    base = EF.cache_basename(backbone_name, 'vindr', stem, 'pooled')
    npz_path = os.path.join(paths.CACHE_DIR, base + '.npz')
    if os.path.exists(npz_path) and not overwrite and smoke == 0:
        print(f'[vindr_extract] 已存在，跳过：{npz_path}')
        return npz_path

    fb = backbones.load_backbone(backbone_name, device=device)
    ds = make_vindr_dataset(split, aggregate=aggregate, shared_map=shared_map,
                            transform=getattr(fb, 'transform', None))
    loader = D.make_loader(ds, batch_size=batch_size, num_workers=num_workers, shuffle=False)

    N = len(ds)
    Dn = fb.feature_dim
    feats = np.zeros((N, Dn), dtype=np.float32)
    labels = np.zeros((N, ds.num_classes), dtype=np.float32)
    pids = np.zeros((N,), dtype=np.int64)
    names = []
    cur = 0
    for bi, (imgs, lab, pid, name) in enumerate(loader):
        imgs = imgs.to(device, non_blocking=False)
        out = fb.forward_pooled(imgs)
        b = imgs.shape[0]
        feats[cur:cur + b] = out.float().cpu().numpy()
        labels[cur:cur + b] = lab.numpy()
        pids[cur:cur + b] = pid.numpy() if torch.is_tensor(pid) else np.asarray(pid)
        names.extend(list(name))
        cur += b
        if bi % 20 == 0:
            print(f'[vindr_extract] {backbone_name}/{split} batch {bi} ({cur}/{N})')
        if smoke and bi + 1 >= smoke:
            print(f'[vindr_extract][SMOKE] 仅跑 {smoke} batch 即停，不落盘。')
            return None
    np.savez(npz_path, feats=feats[:cur], labels=labels[:cur], patient_ids=pids[:cur],
             img_names=np.array(names), backbone=backbone_name, domain='vindr',
             split=stem, aggregate=aggregate, class_names=np.array(ds.class_names))
    print(f'[vindr_extract] 写出 pooled: {npz_path}')
    return npz_path


def main():
    ap = argparse.ArgumentParser('VinDr 跨域 loader / 抽取（--smoke 仅验，不落盘）')
    ap.add_argument('--check_labels', action='store_true',
                    help='仅解析标签打印聚合统计（纯 csv，无 GPU）')
    ap.add_argument('--split', default='train', choices=['train', 'test'])
    ap.add_argument('--aggregate', default='union', choices=['union', 'majority'])
    ap.add_argument('--backbone', default=None)
    ap.add_argument('--smoke', type=int, default=0, help='>0 仅跑 N batch 验算子')
    args = ap.parse_args()

    if args.check_labels or args.backbone is None:
        ids, labels, names = load_vindr_labels(args.split, aggregate=args.aggregate)
        print(f'[check] split={args.split} aggregate={args.aggregate} N={len(ids)} C={len(names)}')
        print(f'[check] class_names={names}')
        print(f'[check] 各类阳性数={labels.sum(0).astype(int).tolist()}')
        return
    # GPU 抽取（交主线）
    extract_vindr_pooled(args.backbone, args.split, aggregate=args.aggregate, smoke=args.smoke)


if __name__ == '__main__':
    main()
