# -*- coding: utf-8 -*-
"""
中间预算 checkpoint probing 驱动（矩阵 §1 skeptic-1 最高杠杆）。

扫块A 产物 results/pretrain/<method>_s<seed>_ep<E>.pth（E∈{25,50,100,[200]}），对每个 ckpt 跑
linear-probe@10%（NIH in-domain），输出 probe-vs-budget 曲线数据 results/probe_vs_budget.csv。
用途：①probe-vs-budget 曲线证 C1 排名对预算稳定（杀 transient）②看 GPU·h/iteration-matched 点排名翻不翻
（杀 DINO multi-crop 偷喂算力）③把「上调 200」改成预登记平台判据。蹭已训过的中间 ckpt，近零额外算力。

输出列（对齐 eval_grid 扩展 schema）：
  backbone, probe_type, label_frac, domain, split, mAUC, per_class_auc, seed, n_train, n_test, seconds,
  timestamp, pretrain_seed, pretrain_ep, images_seen
  其中 backbone=ckpt 文件名 stem（如 mae_s0_ep25），seed=probe seed，pretrain_seed/pretrain_ep 来自文件名，
  images_seen 来自 ckpt['meta']（块A 写入；缺则空，标 TODO）。

⚠️ ckpt 加载是块A↔块B 接缝（INTERFACE §2/§3）：ckpt 含 model_state_dict(ViT-B backbone)+meta。
   load_backbone_from_ckpt 用 repo vit_base + FrozenBackbone(strict=False) 装权重；**确切键名/前缀须在
   integrate 棒对齐块A 实际 save 格式**（下方 key_strip 参数 + TODO 标注）。

GPU 算子（ViT forward + probe）：写好 --smoke，**coder 不跑**，交主线烟测/正式跑。
重型依赖（torch/backbones/datasets/extract_features）惰性 import，使文件名解析逻辑可在无 repo/GPU 环境 pytest。
"""
import os
import re
import csv
import glob
import json
import argparse
import datetime

import paths

# 中间预算 ckpt（eff-epoch）；矩阵 §1：25/50/100，平台未到再统一上调 [200]
DEFAULT_EPOCHS = [25, 50, 100]
PRETRAIN_DIR = os.path.join(paths.RESULTS_DIR, 'pretrain')

# eval_grid 扩展 schema（与 eval_collect 一致）
CSV_FIELDS = ['backbone', 'probe_type', 'label_frac', 'domain', 'split',
              'mAUC', 'per_class_auc', 'seed', 'n_train', 'n_test', 'seconds', 'timestamp',
              'pretrain_seed', 'pretrain_ep', 'images_seen']

# 文件名：<method>_s<seed>_ep<E>.pth
_CKPT_RE = re.compile(r'^(?P<method>.+)_s(?P<seed>\d+)_ep(?P<ep>\d+)\.pth$')


def _now():
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def parse_ckpt_name(fname):
    """'mae_s0_ep25.pth' -> dict(method='mae', pretrain_seed=0, pretrain_ep=25, stem='mae_s0_ep25')。
    不匹配返回 None。"""
    base = os.path.basename(fname)
    m = _CKPT_RE.match(base)
    if not m:
        return None
    return dict(method=m.group('method'), pretrain_seed=int(m.group('seed')),
                pretrain_ep=int(m.group('ep')), stem=base[:-4])


def scan_ckpts(pretrain_dir=None, epochs=None, methods=None):
    """扫 pretrain_dir 下匹配 ckpt，按 (method, seed, ep) 排序返回 [(path, parsed)]。"""
    pretrain_dir = pretrain_dir or PRETRAIN_DIR
    epochs = set(epochs or DEFAULT_EPOCHS)
    out = []
    for p in sorted(glob.glob(os.path.join(pretrain_dir, '*.pth'))):
        info = parse_ckpt_name(p)
        if info is None:
            continue
        if info['pretrain_ep'] not in epochs:
            continue
        if methods and info['method'] not in methods:
            continue
        out.append((p, info))
    out.sort(key=lambda x: (x[1]['method'], x[1]['pretrain_seed'], x[1]['pretrain_ep']))
    return out


def append_row(csv_path, row):
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    exists = os.path.exists(csv_path)
    with open(csv_path, 'a', newline='') as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if not exists:
            w.writeheader()
        w.writerow(row)


def _json_per_class(per_class):
    return json.dumps([None if (v != v) else round(float(v), 4) for v in per_class])


# ---------------------------------------------------------------------------
# 从 ckpt 装 frozen ViT-B backbone（块A↔块B 接缝；惰性 import 重依赖）
# ---------------------------------------------------------------------------
def load_backbone_from_ckpt(ckpt_path, device='cuda', model_name='vit_base', input_size=224,
                            patch_size=16, state_dict_key='model_state_dict', key_strip=''):
    """
    重建 frozen FrozenBackbone（复用 backbones.FrozenBackbone + repo vit_base，read-only 复用，不改 backbones.py）。
    ckpt 契约（INTERFACE §2）：ckpt[state_dict_key] = ViT-B backbone state_dict；ckpt['meta'] = 训练元信息。
    ⚠️ key_strip：若块A 存的键带前缀（如 'encoder.'/'backbone.'）在此剥除；确切值 integrate 棒按块A 实际 save 对齐（TODO）。
    """
    import torch
    import backbones  # 惰性：内部 from models.jepa_vit import vit_base（需 repo 在 path）

    encoder = backbones._VIT_BUILDERS[model_name](
        img_size=input_size, patch_size=patch_size, drop_path_rate=0.0)
    ckpt = torch.load(ckpt_path, map_location='cpu', weights_only=False)
    sd = ckpt.get(state_dict_key, ckpt)
    if key_strip:
        sd = {k[len(key_strip):] if k.startswith(key_strip) else k: v for k, v in sd.items()}
    msg = encoder.load_state_dict(sd, strict=False)
    if any(k.startswith('patch_embed') or k.startswith('blocks') for k in msg.missing_keys):
        print(f'[ckpt_probe][WARN] {os.path.basename(ckpt_path)} patch_embed/blocks 出现 missing，'
              f'键名/前缀可能不匹配块A save 格式（试 --key_strip）；missing(头5)={msg.missing_keys[:5]}')
    from backbones import _freeze, VIT_EMBED_DIMS  # noqa
    encoder = _freeze(encoder.to(device))
    feature_dim = VIT_EMBED_DIMS.get(model_name, 768)
    num_tokens = (input_size // patch_size) ** 2
    meta = dict(ckpt=ckpt_path, ckpt_meta=ckpt.get('meta', {}),
                missing_keys=list(msg.missing_keys), unexpected_keys=list(msg.unexpected_keys))
    return backbones.FrozenBackbone(encoder, feature_dim, num_tokens, meta, transform=None), ckpt.get('meta', {})


def _extract_pooled(fb, split_txt, device, batch_size, num_workers, smoke=0):
    """在给定 frozen backbone 上抽 NIH pooled 特征（自含，不经 EF 注册名）。返回 cache dict 或 None(smoke)。"""
    import numpy as np
    import torch
    import datasets as D

    ds = D.NIHFrozenDataset(split_txt=paths.split_path(split_txt),
                            transform=getattr(fb, 'transform', None))
    loader = D.make_loader(ds, batch_size=batch_size, num_workers=num_workers, shuffle=False)
    N = len(ds)
    Dn = fb.feature_dim
    feats = np.zeros((N, Dn), dtype=np.float32)
    labels = np.zeros((N, ds.num_classes), dtype=np.float32)
    pids = np.zeros((N,), dtype=np.int64)
    cur = 0
    for bi, (imgs, lab, pid, name) in enumerate(loader):
        imgs = imgs.to(device, non_blocking=False)
        out = fb.forward_pooled(imgs)
        b = imgs.shape[0]
        feats[cur:cur + b] = out.float().cpu().numpy()
        labels[cur:cur + b] = lab.numpy()
        pids[cur:cur + b] = pid.numpy() if torch.is_tensor(pid) else np.asarray(pid)
        cur += b
        if smoke and bi + 1 >= smoke:
            print(f'[ckpt_probe][SMOKE] {split_txt} 仅跑 {smoke} batch 即停。')
            return None
    return dict(feats=feats[:cur], labels=labels[:cur], patient_ids=pids[:cur])


def run(pretrain_dir=None, epochs=None, methods=None, label_frac=10, probe_seed=0,
        out_csv=None, device='cuda', batch_size=128, num_workers=4,
        state_dict_key='model_state_dict', key_strip='', smoke=0):
    import probes as P
    out_csv = out_csv or os.path.join(paths.RESULTS_DIR, 'probe_vs_budget.csv')
    train_split = paths.SPLIT_BY_FRAC[label_frac]
    test_split = paths.TEST_SPLIT

    ckpts = scan_ckpts(pretrain_dir, epochs, methods)
    if not ckpts:
        print(f'[ckpt_probe] 未找到匹配 ckpt（dir={pretrain_dir or PRETRAIN_DIR} epochs={epochs or DEFAULT_EPOCHS}）。'
              f'块A 产物就位后再跑。')
        return
    print(f'[ckpt_probe] 命中 {len(ckpts)} 个 ckpt -> probe@{label_frac}% (probe_seed={probe_seed})')

    for path, info in ckpts:
        fb, ckpt_meta = load_backbone_from_ckpt(
            path, device=device, state_dict_key=state_dict_key, key_strip=key_strip)
        tr = _extract_pooled(fb, train_split, device, batch_size, num_workers, smoke=smoke)
        te = _extract_pooled(fb, test_split, device, batch_size, num_workers, smoke=smoke)
        if smoke:
            print(f'[ckpt_probe][SMOKE] {info["stem"]} 抽取算子 OK（未跑 probe/未落盘）。')
            continue
        res = P.run_linear_probe(tr, te, seed=probe_seed, device=device)
        images_seen = ckpt_meta.get('images_seen', '')  # 块A 写入；缺则空（TODO 块A 补 meta）
        row = dict(backbone=info['stem'], probe_type='linear', label_frac=label_frac, domain='nih',
                   split=train_split, mAUC=round(res['mAUC'], 4),
                   per_class_auc=_json_per_class(res['per_class_auc']),
                   seed=probe_seed, n_train=res['n_train'], n_test=res['n_test'],
                   seconds=res['seconds'], timestamp=_now(),
                   pretrain_seed=info['pretrain_seed'], pretrain_ep=info['pretrain_ep'],
                   images_seen=images_seen)
        append_row(out_csv, row)
        print(f'[ckpt_probe][OK] {info["stem"]} ep{info["pretrain_ep"]} '
              f'mAUC={res["mAUC"]:.4f} images_seen={images_seen} -> {out_csv}')


def main():
    ap = argparse.ArgumentParser('中间 ckpt probe@10% 驱动（probe-vs-budget 曲线）')
    ap.add_argument('--pretrain_dir', default=None, help=f'默认 {PRETRAIN_DIR}')
    ap.add_argument('--epochs', nargs='+', type=int, default=None, help=f'默认 {DEFAULT_EPOCHS}')
    ap.add_argument('--methods', nargs='+', default=None, help='限定 method（mae/dino/moco/chexworld）')
    ap.add_argument('--label_frac', type=int, default=10, choices=[1, 10, 100])
    ap.add_argument('--probe_seed', type=int, default=0)
    ap.add_argument('--out_csv', default=None)
    ap.add_argument('--device', default='cuda')
    ap.add_argument('--batch_size', type=int, default=128)
    ap.add_argument('--num_workers', type=int, default=4)
    ap.add_argument('--state_dict_key', default='model_state_dict')
    ap.add_argument('--key_strip', default='', help='块A ckpt 键前缀（如 encoder.），integrate 棒对齐')
    ap.add_argument('--smoke', type=int, default=0, help='>0 仅跑 N batch 验抽取算子，不跑 probe/不落盘')
    args = ap.parse_args()
    run(pretrain_dir=args.pretrain_dir, epochs=args.epochs, methods=args.methods,
        label_frac=args.label_frac, probe_seed=args.probe_seed, out_csv=args.out_csv,
        device=args.device, batch_size=args.batch_size, num_workers=args.num_workers,
        state_dict_key=args.state_dict_key, key_strip=args.key_strip, smoke=args.smoke)


if __name__ == '__main__':
    main()
