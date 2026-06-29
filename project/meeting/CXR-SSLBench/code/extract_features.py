# -*- coding: utf-8 -*-
"""
冻结特征抽取 + 缓存。

两种 feature_type：
  pooled  -> mean-pool over tokens，存 .npz {feats[N,D], labels[N,14], patient_ids[N], img_names[N], meta}
             —— linear-probe 用，体积小。
  tokens  -> 整 token 序列 [N, num_tokens, D]，存 memmap .npy + 同名 .meta.npz（labels/pids/img_names）
             —— attentive-probe 用，体积大；带 size 守卫（默认 >25GB 拒绝，--force 强过）。

缓存命名：{backbone}__{domain}__{splitstem}__{ftype}.{npz|npy}  存于 paths.CACHE_DIR。

⚠️ GPU 算子脚本（DataLoader + ViT forward）：写好 --smoke 入口（限 batch 数），但**不自跑**，交主线烟测。
"""
import os
import argparse
import json

import numpy as np
import torch

import paths
import backbones
import datasets as D


def cache_basename(backbone, domain, split_txt, ftype):
    stem = os.path.splitext(os.path.basename(split_txt))[0]
    return f'{backbone}__{domain}__{stem}__{ftype}'


def _build_dataset(domain, split_txt, transform=None):
    # transform = 该 backbone 专属 eval transform（fb.transform）；None -> dataset 用默认 224 CXR transform。
    if domain == 'nih':
        return D.NIHFrozenDataset(split_txt=split_txt, transform=transform)
    elif domain == 'vindr':
        # TODO: researcher 回填 VinDr 标签后接 D.VinDrClsDataset
        return D.VinDrClsDataset(split_txt=split_txt)
    else:
        raise NotImplementedError(f'domain={domain}')


@torch.no_grad()
def extract(backbone_name, domain, split_txt, ftype='pooled', device='cuda',
            batch_size=128, num_workers=4, max_gb=25.0, force=False, smoke=0,
            overwrite=False):
    """抽取并缓存。返回缓存文件路径（pooled->.npz / tokens->.npy）。"""
    split_txt = paths.split_path(split_txt)
    os.makedirs(paths.CACHE_DIR, exist_ok=True)
    base = cache_basename(backbone_name, domain, split_txt, ftype)

    fb = backbones.load_backbone(backbone_name, device=device)
    # 用该 backbone 自己的预处理（输入尺寸/norm 因模型而异；None=默认 224 CXR transform）
    ds = _build_dataset(domain, split_txt, transform=getattr(fb, 'transform', None))
    loader = D.make_loader(ds, batch_size=batch_size, num_workers=num_workers, shuffle=False)

    N = len(ds)
    Dn = fb.feature_dim
    T = fb.num_tokens

    if ftype == 'tokens':
        est_gb = N * T * Dn * 4 / (1024 ** 3)
        npy_path = os.path.join(paths.CACHE_DIR, base + '.npy')
        meta_path = os.path.join(paths.CACHE_DIR, base + '.meta.npz')
        print(f'[extract] tokens 估算体积 = {est_gb:.2f} GB (N={N}, T={T}, D={Dn})')
        if est_gb > max_gb and not force:
            raise RuntimeError(
                f'tokens 缓存 {est_gb:.2f}GB 超过 --max_gb={max_gb}GB；'
                f'对大 split 改用 attentive 的 on-the-fly 模式，或加 --force 强存。')
        if os.path.exists(npy_path) and not overwrite and smoke == 0:
            print(f'[extract] 已存在，跳过：{npy_path}（--overwrite 重抽）')
            return npy_path
        mm = np.lib.format.open_memmap(npy_path, mode='w+', dtype=np.float32, shape=(N, T, Dn))
    else:  # pooled
        npz_path = os.path.join(paths.CACHE_DIR, base + '.npz')
        if os.path.exists(npz_path) and not overwrite and smoke == 0:
            print(f'[extract] 已存在，跳过：{npz_path}（--overwrite 重抽）')
            return npz_path
        feats = np.zeros((N, Dn), dtype=np.float32)

    labels = np.zeros((N, ds.num_classes), dtype=np.float32)
    pids = np.zeros((N,), dtype=np.int64)
    names = []

    cur = 0
    for bi, (imgs, lab, pid, name) in enumerate(loader):
        imgs = imgs.to(device, non_blocking=False)
        if ftype == 'tokens':
            out = fb.forward_tokens(imgs)          # [B,T,D]
        else:
            out = fb.forward_pooled(imgs)          # [B,D]
        b = imgs.shape[0]
        if ftype == 'tokens':
            mm[cur:cur + b] = out.float().cpu().numpy()
        else:
            feats[cur:cur + b] = out.float().cpu().numpy()
        labels[cur:cur + b] = lab.numpy()
        pids[cur:cur + b] = pid.numpy() if torch.is_tensor(pid) else np.asarray(pid)
        names.extend(list(name))
        cur += b
        if bi % 20 == 0:
            print(f'[extract] {backbone_name}/{domain}/{os.path.basename(split_txt)} '
                  f'batch {bi} ({cur}/{N})')
        if smoke and bi + 1 >= smoke:
            print(f'[extract][SMOKE] 仅跑 {smoke} batch 即停，不写完整缓存。')
            break

    meta = dict(backbone=backbone_name, domain=domain, split=os.path.basename(split_txt),
                ftype=ftype, N=int(cur), D=int(Dn), T=int(T),
                backbone_meta=json.dumps(fb.meta, default=str))

    if smoke:
        print('[extract][SMOKE] OK（未落盘），主线确认算子无误后去掉 --smoke 正式抽。')
        return None

    if ftype == 'tokens':
        mm.flush()
        np.savez(meta_path, labels=labels[:cur], patient_ids=pids[:cur],
                 img_names=np.array(names), **meta)
        print(f'[extract] 写出 tokens: {npy_path} + {meta_path}')
        return npy_path
    else:
        np.savez(npz_path, feats=feats[:cur], labels=labels[:cur], patient_ids=pids[:cur],
                 img_names=np.array(names), **meta)
        print(f'[extract] 写出 pooled: {npz_path}')
        return npz_path


def load_pooled_cache(npz_path):
    z = np.load(npz_path, allow_pickle=True)
    return dict(feats=z['feats'], labels=z['labels'], patient_ids=z['patient_ids'],
                img_names=z['img_names'])


def load_tokens_cache(npy_path):
    meta_path = os.path.splitext(npy_path)[0] + '.meta.npz'
    tokens = np.load(npy_path, mmap_mode='r')
    z = np.load(meta_path, allow_pickle=True)
    return dict(tokens=tokens, labels=z['labels'], patient_ids=z['patient_ids'],
                img_names=z['img_names'])


def main():
    ap = argparse.ArgumentParser('CXR-SSLBench frozen feature extractor')
    ap.add_argument('--backbone', required=True, choices=backbones.available_backbones())
    ap.add_argument('--domain', default='nih', choices=['nih', 'vindr'])
    ap.add_argument('--split', required=True,
                    help="split txt 名/绝对路径，或 int(1/10/100) 经 paths.SPLIT_BY_FRAC；test 用 probe_test.txt")
    ap.add_argument('--ftype', default='pooled', choices=['pooled', 'tokens'])
    ap.add_argument('--device', default='cuda')
    ap.add_argument('--batch_size', type=int, default=128)
    ap.add_argument('--num_workers', type=int, default=4)
    ap.add_argument('--max_gb', type=float, default=25.0)
    ap.add_argument('--force', action='store_true')
    ap.add_argument('--overwrite', action='store_true')
    ap.add_argument('--smoke', type=int, default=0, help='>0 仅跑 N batch 验算子，不落盘')
    args = ap.parse_args()
    split = int(args.split) if args.split.isdigit() else args.split
    extract(args.backbone, args.domain, split, ftype=args.ftype, device=args.device,
            batch_size=args.batch_size, num_workers=args.num_workers,
            max_gb=args.max_gb, force=args.force, smoke=args.smoke, overwrite=args.overwrite)


if __name__ == '__main__':
    main()
