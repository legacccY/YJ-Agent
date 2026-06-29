# -*- coding: utf-8 -*-
"""
Finetune 启动器（复现零偏离）—— 照搬 CheXWorld FINETUNE.md 官方 recipe，驱动 repo 原版 train_finetune.py。

红线：finetune 训练循环/超参一律走 repo 自己的 train_finetune.py，**不在 harness 重写、不私调 lr/步数**。
本脚本只做一件事：把 FINETUNE.md 的命令模板对 NIH 实例化，仅变量化 {data_pct, pretrained, output_dir, seed}，
其余每个超参逐字照搬 FINETUNE.md（下方常量带 "# FINETUNE.md, 勿改" 标注）。

⚠️ Phase 0 一致性 caveat（已知，记 LOG）：
  repo 的 `--dataset nih` 走官方 Xray14_{train,val,test}_official.txt + data_pct 随机图级子采样(seed 42)，
  与 linear/attentive probe 用的 NCA-JEPA **patient-level** 无泄漏 split 不是同一套切分。
  Phase 0 finetune 为「可选/对照」，复现 recipe 优先于切分统一；Phase 1 受控横评再统一切分（需改 repo NIH dataset，
  本脚本不动 repo）。

coder 不跑（finetune = 真训练，走 gpu_slot）。本脚本默认只打印命令；--execute 才真起（交主线）。
"""
import os
import argparse
import subprocess

import paths

# --- FINETUNE.md 官方 recipe（分类数据集，CheXpert 除外）；逐字照搬，勿改 ---
RECIPE = dict(
    model='vit_base',          # FINETUNE.md, 勿改
    norm_type='default',       # FINETUNE.md, 勿改
    dataset_cat=1,             # FINETUNE.md, 勿改
    print_freq=20,             # FINETUNE.md
    batch_size=256,            # FINETUNE.md, 勿改
    num_workers=16,            # FINETUNE.md
    epochs=50,                 # FINETUNE.md, 勿改
    warmup_epochs=1,           # FINETUNE.md, 勿改
    eval_freq=1,               # FINETUNE.md
    input_size=224,            # FINETUNE.md, 勿改
    resize_size=256,           # FINETUNE.md, 勿改
    aug_type='jit',            # FINETUNE.md, 勿改
    rot=0,                     # FINETUNE.md, 勿改
    crop_type='rrc',           # FINETUNE.md, 勿改
    scale_min=0.4,             # FINETUNE.md, 勿改
    early_stop=15,             # FINETUNE.md, 勿改
    layer_decay=0.75,          # FINETUNE.md, 勿改（分类非 CheXpert）
    drop_path=0.6,             # FINETUNE.md, 勿改（分类非 CheXpert）
    lr='1e-4',                 # FINETUNE.md, 勿改（分类非 CheXpert）
    min_lr='1e-6',             # FINETUNE.md, 勿改
    weight_decay=0.05,         # FINETUNE.md, 勿改（分类非 CheXpert）
    clip_grad=1,               # FINETUNE.md, 勿改
    save_mode='best',          # FINETUNE.md
)


def build_command(data_pct, pretrained, output_dir, seed=0, dataset='nih', nproc=1):
    """构造与 FINETUNE.md 等价的 torchrun 命令（list 形式，便于 subprocess）。"""
    pretrained = pretrained or paths.CHEXWORLD_TAR
    r = RECIPE
    cmd = [
        'torchrun', '--nproc_per_node', str(nproc), '--nnodes', '1',
        '--rdzv_backend', 'c10d', '--rdzv_endpoint', 'localhost:0',
        'train_finetune.py',
        '--dataset', dataset, '--data_pct', str(data_pct), '--dataset_cat', str(r['dataset_cat']),
        '--norm_type', r['norm_type'], '--model', r['model'],
        '--print_freq', str(r['print_freq']), '--batch_size', str(r['batch_size']),
        '--num_workers', str(r['num_workers']), '--amp',
        '--epochs', str(r['epochs']), '--warmup_epochs', str(r['warmup_epochs']),
        '--eval_freq', str(r['eval_freq']),
        '--input_size', str(r['input_size']), '--resize_size', str(r['resize_size']),
        '--aug_type', r['aug_type'], '--rot', str(r['rot']), '--crop_type', r['crop_type'],
        '--scale_min', str(r['scale_min']),
        '--early_stop', str(r['early_stop']), '--layer_decay', str(r['layer_decay']),
        '--drop_path', str(r['drop_path']),
        '--lr', r['lr'], '--min_lr', r['min_lr'], '--weight_decay', str(r['weight_decay']),
        '--clip_grad', str(r['clip_grad']), '--save_mode', r['save_mode'],
        '--output_dir', output_dir, '--use_target', '--pretrained', pretrained,
        '--seed', str(seed),
    ]
    return cmd


def main():
    ap = argparse.ArgumentParser('CheXWorld finetune launcher (verbatim FINETUNE.md)')
    ap.add_argument('--data_pct', type=float, required=True, help='1.0 / 0.1 / 0.01 (对应 100/10/1%)')
    ap.add_argument('--pretrained', default=None, help='默认 paths.CHEXWORLD_TAR')
    ap.add_argument('--output_dir', required=True)
    ap.add_argument('--dataset', default='nih', choices=['nih', 'vindr_new', 'chex'])
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--nproc', type=int, default=1)
    ap.add_argument('--execute', action='store_true', help='真起训练（交主线；走 gpu_slot）。默认仅打印命令。')
    args = ap.parse_args()

    cmd = build_command(args.data_pct, args.pretrained, args.output_dir,
                        seed=args.seed, dataset=args.dataset, nproc=args.nproc)
    print('# cwd = CheXWorld repo:', paths.CHEXWORLD_REPO)
    print(' '.join(cmd))
    if args.execute:
        print('[run_finetune] 真起训练（在 repo 目录）...')
        subprocess.run(cmd, cwd=paths.CHEXWORLD_REPO, check=True)
    else:
        print('[run_finetune] 仅打印（未执行）。主线串行起：cd repo 后跑上面命令，或加 --execute。')


if __name__ == '__main__':
    main()
