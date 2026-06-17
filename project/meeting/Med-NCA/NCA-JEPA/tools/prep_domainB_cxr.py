# -*- coding: utf-8 -*-
# ===========================================================================
# NCA-JEPA 路线 B — 域 B 胸片数据集准备（VinDr-CXR 优先，CheXpert 备选）
#
# 目的：把域 B 胸片数据建成与 NIH ChestX-ray14 同格式的 10k 子集 split，
#       对齐域 A（pretrain_10k.txt）规模，用于续训 + 遗忘探针评估。
#
# 用法（先把原始数据下好，再跑本脚本）：
#   python tools/prep_domainB_cxr.py \
#       --src vindrcxr \
#       --raw_dir /path/to/VinDr-CXR/raw/ \
#       --out_dir data/domainB_vindrcxr/ \
#       --n 10000 \
#       --seed 42
#
# 所需原始文件：
#   VinDr-CXR（优先）：
#     - 原始目录含 PA 位 DICOM 或 PNG，如 physionet.org/content/vindr-cxr/1.0.0/
#       典型文件树：<raw_dir>/train/images/*.png（约 18k PA 位图）
#       需要 PhysioNet 凭证下载（wget --user --ask-password 或官方 CLI）。
#       TODO: 下载命令——
#         wget -r -N -c -np --user <physionet_user> --ask-password \
#           https://physionet.org/files/vindr-cxr/1.0.0/train/images/
#     - 官方元数据：annotations/image_labels_train.csv（含 image_id + 14 类标签）
#       注：本脚本不用标签，纯 SSL，仅用文件列表。
#   CheXpert（备选，需 Stanford 凭证）：
#     - 官方网站 https://stanfordmlgroup.github.io/competitions/chexpert/
#     - 解压后：CheXpert-v1.0/train/*/frontal/*.jpg
#     TODO: 下载说明见 Stanford 官方页；凭证需用户自行申请。
#
# 脚本只做 split 构建（不下载、不联网）。凭证 / 下载在脚本外由用户完成。
# 输出：
#   <out_dir>/splits/domainB_10k.txt    — 10k 子集图片相对路径列表
#   <out_dir>/splits/domainB_full.txt   — 全集路径列表（备查）
#   <out_dir>/splits/domainB_val.txt    — 小 val 集（10k 的 10%）
#   并更新 .portfolio/datasets.json 中 vindrcxr / chexpert_domainB 条目。
#
# 与 NIH split 格式对齐：每行一个相对路径（相对于 <out_dir>），如：
#   images/1.0.0/train/images/00001.png
# （NIH 格式：images-224/images-224/00000001_000.png）
# ===========================================================================

import os
import sys
import json
import random
import argparse
import pathlib


# ---------------------------------------------------------------------------
# 工具：递归收集图片路径
# ---------------------------------------------------------------------------
ALLOWED_EXT = {'.png', '.jpg', '.jpeg', '.dicom', '.dcm'}


def collect_images(raw_dir, extensions=None):
    """递归收集 raw_dir 下所有图片文件，返回相对路径列表（相对于 raw_dir）。"""
    ext = extensions or ALLOWED_EXT
    paths = []
    raw = pathlib.Path(raw_dir)
    for p in raw.rglob('*'):
        if p.suffix.lower() in ext and p.is_file():
            paths.append(str(p.relative_to(raw)))
    return sorted(paths)


def filter_pa_frontal(paths, src):
    """尽力过滤出 PA/frontal 位（VinDr 目录名含 'train', CheXpert 含 'frontal'）。
    找不到 frontal 标记时直接返回原列表（宁可不过滤也不丢图）。
    """
    if src == 'vindrcxr':
        # VinDr-CXR train set 全是 PA 位（官方说明），无需过滤
        return paths
    elif src == 'chexpert':
        frontal = [p for p in paths if 'frontal' in p.lower()]
        return frontal if frontal else paths
    return paths


# ---------------------------------------------------------------------------
# 写 split txt
# ---------------------------------------------------------------------------
def write_split(lines, out_path):
    out_path = pathlib.Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        for line in lines:
            f.write(line + '\n')
    print(f'  写出 split: {out_path} ({len(lines)} 张)')


# ---------------------------------------------------------------------------
# 更新 datasets.json（真源）
# ---------------------------------------------------------------------------
def update_datasets_json(datasets_json_path, src, out_dir, n_total, n_subset):
    """在 datasets.json 追加/更新域 B 数据集条目。"""
    p = pathlib.Path(datasets_json_path)
    if not p.is_file():
        print(f'  [警告] datasets.json 不存在 ({p})，跳过更新。')
        return
    with open(p, encoding='utf-8') as f:
        d = json.load(f)

    key_map = {
        'vindrcxr':  'vindrcxr_domainB',
        'chexpert':  'chexpert_domainB',
    }
    key = key_map.get(src, f'{src}_domainB')

    entry = {
        'name': f'Domain-B CXR ({src})',
        'n': n_total,
        'n_subset': n_subset,
        'local': str(pathlib.Path(out_dir).as_posix()),
        'hpc': 'TODO: 填 HPC 部署路径',
        'source': {
            'vindrcxr': 'https://physionet.org/content/vindr-cxr/1.0.0/ (需 PhysioNet 凭证)',
            'chexpert': 'https://stanfordmlgroup.github.io/competitions/chexpert/ (需 Stanford 凭证)',
        }.get(src, 'TODO'),
        'split': f'{out_dir}/splits/domainB_10k.txt',
        'used_by': ['nca-jepa'],
        'purpose': 'NCA-JEPA 路线 B — 遗忘探针域 B 续训集（对齐域 A NIH 10k 规模）',
        'status': 'ready(local)',
    }
    d['datasets'][key] = entry
    d['updated'] = 'updated-by-prep_domainB_cxr'

    with open(p, 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    print(f'  datasets.json 已更新条目 [{key}]')


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser(
        description='NCA-JEPA 路线 B — 域 B 胸片 10k split 构建')
    p.add_argument('--src',     required=True, choices=['vindrcxr', 'chexpert'],
                   help='数据集来源')
    p.add_argument('--raw_dir', required=True,
                   help='原始图片根目录（已下载好）')
    p.add_argument('--out_dir', required=True,
                   help='输出根目录（splits/ 将在此下创建）')
    p.add_argument('--n',       type=int, default=10000,
                   help='子集大小（对齐域 A pretrain_10k，默认 10000）')
    p.add_argument('--val_frac', type=float, default=0.1,
                   help='从子集中划出 val 比例（默认 0.1，即 1000 张）')
    p.add_argument('--seed',    type=int, default=42)
    p.add_argument('--datasets_json',
                   default=os.path.join(
                       os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       '..', '..', '..', '.portfolio', 'datasets.json'),
                   help='datasets.json 真源路径（默认：.portfolio/datasets.json）')
    args = p.parse_args()

    random.seed(args.seed)

    raw_dir = pathlib.Path(args.raw_dir)
    if not raw_dir.is_dir():
        print(f'[错误] raw_dir 不存在：{raw_dir}')
        print('  请先下载原始数据（见脚本顶部注释的 TODO 下载命令）。')
        sys.exit(1)

    print(f'[prep_domainB] src={args.src}  raw_dir={raw_dir}')
    print('  收集图片文件...')
    all_paths = collect_images(raw_dir)
    print(f'  找到 {len(all_paths)} 张图')

    # PA/frontal 过滤
    all_paths = filter_pa_frontal(all_paths, args.src)
    print(f'  PA/frontal 过滤后 {len(all_paths)} 张')

    if len(all_paths) == 0:
        print('[错误] 找不到图片文件，请检查 raw_dir 路径和文件格式。')
        sys.exit(1)

    # 全集 txt
    write_split(all_paths, pathlib.Path(args.out_dir) / 'splits' / 'domainB_full.txt')

    # 10k 子集（不足则取全部）
    n_sub = min(args.n, len(all_paths))
    subset = random.sample(all_paths, n_sub)

    # 划 val（从子集中取，不与 train 重叠）
    n_val = max(1, int(n_sub * args.val_frac))
    val = subset[:n_val]
    train = subset[n_val:]

    write_split(train, pathlib.Path(args.out_dir) / 'splits' / 'domainB_10k.txt')
    write_split(val,   pathlib.Path(args.out_dir) / 'splits' / 'domainB_val.txt')

    # 更新 datasets.json
    ds_json = pathlib.Path(args.datasets_json).resolve()
    update_datasets_json(str(ds_json), args.src, args.out_dir, len(all_paths), n_sub)

    print(f'\n[done] 子集 {n_sub} 张（train={len(train)} val={len(val)}）')
    print(f'  TODO: 把 out_dir={args.out_dir} 传到 HPC，更新 datasets.json HPC 路径字段。')
    print(f'  TODO: b_continual_*.yaml 中 data.root_path / data.subset_file 填对应路径。')


if __name__ == '__main__':
    main()
