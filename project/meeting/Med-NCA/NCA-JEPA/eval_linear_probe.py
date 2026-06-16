# -*- coding: utf-8 -*-
# ===========================================================================
# NCA-JEPA pilot —— Linear Probe 评估脚本（Gate0 判定用）
#
# 用途：
#   I-JEPA 自监督预训练完后，测「预训练表征质量」。做法是冻结 encoder、抽特征、
#   在冻结特征上训一个线性分类器（logistic regression），测下游 NIH ChestX-ray14
#   14 病理多标签分类的 AUROC。这是 self-supervised 表征评估的标准协议（linear probe）。
#
# Gate0 判据：
#   A0（预训练 target_encoder）的 probe macro-mean AUROC
#       − from-scratch（随机初始化 encoder）的 probe macro-mean AUROC  ≥ +5 个点
#   → Gate0 probe 项「通过」（说明预训练确实学到了优于随机初始化的表征）。
#
# 用法（两次跑，分别得 A0 和 scratch，再对比 mean_auroc）：
#   python eval_linear_probe.py --ckpt <A0.pth.tar> --probe-train 100pct
#   python eval_linear_probe.py --scratch            --probe-train 100pct
#
# 关键设计：
#   - 用 ckpt 的 target_encoder（EMA 版，JEPA linear probe 惯例），strip module. 前缀，
#     load 用 strict=False 并打印 missing/unexpected keys 确认对齐。
#   - encoder 冻结 eval()+no_grad，forward 不带 mask，对 patch 维度 mean pool → [B, D]。
#   - sklearn LogisticRegression（MultiOutputClassifier 包一层做 14 标签多标签）。
#   - 逐标签 roc_auc_score，跳过 test 里全 0 / 全 1 的标签（无法定义 AUROC）。
# ===========================================================================

import os
import sys
import argparse

import numpy as np
import pandas as pd

import torch
import torch.nn as nn
from torch.utils.data import DataLoader
import torchvision.transforms as T

# -- 让 ijepa/src 可 import（vision_transformer / nih_cxr14 都在 ijepa/src 下）
_HERE = os.path.dirname(os.path.abspath(__file__))
_IJEPA_ROOT = os.path.join(_HERE, 'ijepa')
if _IJEPA_ROOT not in sys.path:
    sys.path.insert(0, _IJEPA_ROOT)

import src.models.vision_transformer as vit  # noqa: E402
from src.datasets.nih_cxr14 import NIHChestXray14  # noqa: E402

from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.multioutput import MultiOutputClassifier  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402


# -- NIH ChestX-ray14 的 14 个病理（顺序固定，决定 14 维 multi-hot 的列顺序）
#    "No Finding" 不算病理（即该图 14 维全 0）。
PATHOLOGIES = [
    'Atelectasis', 'Cardiomegaly', 'Effusion', 'Infiltration', 'Mass',
    'Nodule', 'Pneumonia', 'Pneumothorax', 'Consolidation', 'Edema',
    'Emphysema', 'Fibrosis', 'Pleural_Thickening', 'Hernia',
]

# -- ImageNet mean/std（I-JEPA 预训练用的归一化，probe 抽特征须保持一致）
_IMAGENET_MEAN = (0.485, 0.456, 0.406)
_IMAGENET_STD = (0.229, 0.224, 0.225)


def build_label_map(csv_path):
    """读 Data_Entry_2017.csv，构造 {Image Index: 14维 multi-hot np.float32}。"""
    df = pd.read_csv(csv_path)
    path_to_col = {name: i for i, name in enumerate(PATHOLOGIES)}
    label_map = {}
    for img_index, finding in zip(df['Image Index'], df['Finding Labels']):
        vec = np.zeros(len(PATHOLOGIES), dtype=np.float32)
        # Finding Labels 多标签用 | 分隔，如 "Effusion|Infiltration" 或 "No Finding"
        for f in str(finding).split('|'):
            f = f.strip()
            if f in path_to_col:
                vec[path_to_col[f]] = 1.0
        label_map[img_index] = vec
    return label_map


def build_eval_transform():
    """纯 eval transform：Resize(224)+ToTensor+Normalize(ImageNet)。不要 train 增强。"""
    return T.Compose([
        T.Resize((224, 224)),
        T.ToTensor(),
        T.Normalize(mean=_IMAGENET_MEAN, std=_IMAGENET_STD),
    ])


def build_encoder(ckpt_path, scratch, device):
    """
    构造 vit_small（img_size=224, patch16, embed_dim=384）encoder。
    - 若给 ckpt 且非 scratch：strip module. 前缀 + load target_encoder（strict=False）。
    - scratch / 无 ckpt：保持随机初始化（from-scratch baseline）。
    返回冻结 eval() 的 encoder。
    """
    encoder = vit.__dict__['vit_small'](img_size=[224], patch_size=16)

    if (ckpt_path is not None) and (not scratch):
        print(f'[encoder] loading checkpoint: {ckpt_path}')
        ckpt = torch.load(ckpt_path, map_location='cpu')
        if 'target_encoder' not in ckpt:
            raise KeyError(
                f"checkpoint 里没有 'target_encoder' 键，实有键: {list(ckpt.keys())}")
        state = ckpt['target_encoder']
        # DDP 存的 state_dict 可能有 module. 前缀 → strip 掉再 load
        state = {k.replace('module.', ''): v for k, v in state.items()}
        msg = encoder.load_state_dict(state, strict=False)
        print(f'[encoder] load_state_dict (strict=False) result:')
        print(f'  missing keys    ({len(msg.missing_keys)}): {msg.missing_keys}')
        print(f'  unexpected keys ({len(msg.unexpected_keys)}): {msg.unexpected_keys}')
    else:
        print('[encoder] from-scratch (random init), no checkpoint loaded')

    encoder = encoder.to(device)
    encoder.eval()
    for p in encoder.parameters():
        p.requires_grad = False
    return encoder


@torch.no_grad()
def extract_features(encoder, split_file, data_root, label_map, device,
                     batch_size, num_workers, max_n=None):
    """
    用 NIHChestXray14 跑 split，encoder forward（不带 mask），对 patch 维度 mean pool
    → 每图 [D] 特征。同时按 basename(Image Index) 从 label_map 取 14 维 label。
    返回 (X [N, D] np.float32, Y [N, 14] np.float32)。
    """
    transform = build_eval_transform()
    dataset = NIHChestXray14(
        root=data_root,
        image_folder=None,        # 用默认 images-224/images-224
        transform=transform,
        subset_file=split_file,
        train=False,
        copy_data=False,
    )

    # dataset.samples 是完整路径列表；basename 即 Image Index，用来对齐 label
    img_indices = [os.path.basename(p) for p in dataset.samples]
    if max_n is not None and max_n < len(img_indices):
        # 截断：dataset 与 label 都按相同前 max_n 取
        dataset.samples = dataset.samples[:max_n]
        img_indices = img_indices[:max_n]

    # 先把 label 备好（顺序与 dataset 一致，逐 batch 切片）
    labels = np.stack([label_map[idx] for idx in img_indices], axis=0)  # [N, 14]

    loader = DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=False,            # 不打乱，保证与 labels 顺序对齐
        num_workers=num_workers,
        pin_memory=True,
        drop_last=False,
    )

    feats = []
    n_done = 0
    for imgs, _ in loader:                 # dataset 返回的 label 是占位 0，丢弃
        imgs = imgs.to(device, non_blocking=True)
        out = encoder(imgs)                # [B, N_patch, D]，无 cls token，已过 norm
        feat = out.mean(dim=1)             # patch 维度 mean pool → [B, D]
        feats.append(feat.cpu().numpy().astype(np.float32))
        n_done += imgs.size(0)
        if n_done % (batch_size * 20) < batch_size:
            print(f'  extracted {n_done}/{len(img_indices)}', flush=True)

    X = np.concatenate(feats, axis=0)      # [N, D]
    Y = labels                             # [N, 14]
    assert X.shape[0] == Y.shape[0], f'特征数 {X.shape[0]} 与 label 数 {Y.shape[0]} 不一致'
    print(f'[extract] {split_file}: X {X.shape}, Y {Y.shape}')
    return X, Y


def fit_and_eval_probe(X_train, Y_train, X_test, Y_test):
    """
    在冻结特征上训线性 probe（LogisticRegression，多标签用 MultiOutputClassifier），
    逐标签算 test AUROC，跳过 test 里全 0/全 1 的标签。
    返回 (mean_auroc, per_label_auroc list[float|None])。
    """
    base = LogisticRegression(max_iter=1000)
    clf = MultiOutputClassifier(base)
    clf.fit(X_train, Y_train)

    # predict_proba 返回 list（每标签一个 [N, 2] 数组），取正类概率列
    proba_list = clf.predict_proba(X_test)

    per_label = []
    valid_scores = []
    for i in range(len(PATHOLOGIES)):
        y_true = Y_test[:, i]
        # 跳过 test 里全 0 或全 1 的标签（roc_auc_score 无法定义）
        if y_true.sum() == 0 or y_true.sum() == len(y_true):
            per_label.append(None)
            continue
        # MultiOutputClassifier 内部每个子分类器 classes_ 可能只有单类（训练集退化），
        # 这种情况 predict_proba 只有 1 列 → 也无法给正类概率，跳过
        proba_i = proba_list[i]
        if proba_i.shape[1] < 2:
            per_label.append(None)
            continue
        y_score = proba_i[:, 1]
        auc = roc_auc_score(y_true, y_score)
        per_label.append(float(auc))
        valid_scores.append(auc)

    mean_auroc = float(np.mean(valid_scores)) if valid_scores else float('nan')
    return mean_auroc, per_label


def main():
    parser = argparse.ArgumentParser(
        description='NCA-JEPA Gate0 linear probe (NIH ChestX-ray14, 14-label AUROC)')
    parser.add_argument('--ckpt', type=str, default=None,
                        help='A0 checkpoint 路径（jepa-latest.pth.tar）；给则加载 target_encoder')
    parser.add_argument('--scratch', action='store_true',
                        help='强制 from-scratch（随机初始化），忽略 --ckpt，作为 baseline')
    parser.add_argument('--data-root', type=str, default='data/nih_cxr14',
                        help='NIH 数据根目录（含 images-224/ 与 splits/）')
    parser.add_argument('--probe-train', type=str, default='100pct',
                        choices=['1pct', '10pct', '100pct'],
                        help='probe 训练 split（probe_train_<X>.txt）')
    parser.add_argument('--out', type=str, default='results/gate0_probe.csv',
                        help='结果 csv（append 一行）')
    parser.add_argument('--device', type=str, default='cuda')
    parser.add_argument('--batch-size', type=int, default=128)
    parser.add_argument('--num-workers', type=int, default=8)
    parser.add_argument('--max-train', type=int, default=None,
                        help='probe_train 抽特征的图数上限（防太慢），默认 None 全量')
    args = parser.parse_args()

    device = torch.device(args.device if torch.cuda.is_available() else 'cpu')
    setting = 'scratch' if (args.scratch or args.ckpt is None) else 'A0'
    print(f'=== Gate0 linear probe | setting={setting} | '
          f'probe_train={args.probe_train} | device={device} ===')

    # -- 路径
    csv_path = os.path.join(args.data_root, 'Data_Entry_2017.csv')
    splits_dir = os.path.join(args.data_root, 'splits')
    train_split = os.path.join(splits_dir, f'probe_train_{args.probe_train}.txt')
    test_split = os.path.join(splits_dir, 'probe_test.txt')

    # -- label map（从 csv 读，dataset 占位 0 不用）
    print(f'[label] reading {csv_path}')
    label_map = build_label_map(csv_path)

    # -- encoder
    encoder = build_encoder(args.ckpt, args.scratch, device)

    # -- 抽特征（train 受 --max-train 限制；test 全量）
    X_train, Y_train = extract_features(
        encoder, train_split, args.data_root, label_map, device,
        args.batch_size, args.num_workers, max_n=args.max_train)
    X_test, Y_test = extract_features(
        encoder, test_split, args.data_root, label_map, device,
        args.batch_size, args.num_workers, max_n=None)

    # -- 线性 probe + 逐标签 AUROC
    mean_auroc, per_label = fit_and_eval_probe(X_train, Y_train, X_test, Y_test)

    print('\n=== per-label AUROC ===')
    for name, auc in zip(PATHOLOGIES, per_label):
        s = f'{auc:.4f}' if auc is not None else 'skip(degenerate)'
        print(f'  {name:<18s} {s}')
    print(f'\n=== macro-mean AUROC ({setting}, {args.probe_train}): {mean_auroc:.4f} ===')

    # -- append 一行到 csv
    out_path = args.out
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    header = ['setting', 'probe_train_split', 'mean_auroc'] + PATHOLOGIES
    row = {
        'setting': setting,
        'probe_train_split': args.probe_train,
        'mean_auroc': round(mean_auroc, 6),
    }
    for name, auc in zip(PATHOLOGIES, per_label):
        row[name] = round(auc, 6) if auc is not None else ''
    row_df = pd.DataFrame([row], columns=header)
    write_header = not os.path.exists(out_path)
    row_df.to_csv(out_path, mode='a', header=write_header, index=False)
    print(f'[out] appended 1 row to {out_path}')


if __name__ == '__main__':
    main()
