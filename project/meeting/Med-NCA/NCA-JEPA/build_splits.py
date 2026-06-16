# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------------
# NCA-JEPA pilot —— NIH ChestX-ray14 patient-level 切分脚本
#
# 铁律：所有切分一律「按 Patient ID 切」，绝不让同一患者的片子跨 train / probe。
# 这是 ChestX-ray14 的已知数据泄漏陷阱（同一患者多次随访影像高度相似，若按图
# 随机切会让下游 probe 虚高）。本脚本保证：
#   - pretrain 池 与 probe 池 的患者集合互不相交；
#   - probe_test 来自官方 test list（患者天然与 train_val 不重叠）。
#
# 生成到 data/nih_cxr14/splits/：
#   pretrain_10k.txt            —— 自监督预训练，按患者采样约 10,000 张图
#   probe_train_1pct.txt        —— 下游 linear probe 训练，probe 池的 1%（按患者）
#   probe_train_10pct.txt       —— probe 池的 10%
#   probe_train_100pct.txt      —— probe 池的 100%（整个 probe 池）
#   probe_test.txt              —— 官方 test，linear probe 评测
#
# seed=42 固定可复现。用 pandas。
# ---------------------------------------------------------------------------

import os
import argparse

import numpy as np
import pandas as pd

SEED = 42

# ---- 路径（已 ls 核实，2026-06-16）----
DATA_ROOT = os.path.join('data', 'nih_cxr14')
CSV_PATH = os.path.join(DATA_ROOT, 'Data_Entry_2017.csv')
SPLITS_DIR = os.path.join(DATA_ROOT, 'splits')

# 官方 train_val / test list 文件名（可能尚未解压）。
# 已知候选名（不同分发版本命名不一），脚本会逐个探测：
TRAINVAL_LIST_CANDIDATES = ['train_val_list_NIH.txt', 'train_val_list.txt']
TEST_LIST_CANDIDATES = ['test_list.txt', 'test_list_NIH.txt']

# ---- 采样规模 ----
PRETRAIN_TARGET = 10000   # pretrain 约 10k 张图（按患者累加，达标即停）


def _find_official_list(candidates):
    """在 DATA_ROOT 下逐个探测官方 list 文件，返回第一个存在的路径，否则 None。"""
    for name in candidates:
        path = os.path.join(DATA_ROOT, name)
        if os.path.exists(path):
            return path
    return None


def _read_list(path):
    """读官方 list txt（每行一个 Image Index），返回 set。"""
    with open(path, 'r') as f:
        return set(line.strip() for line in f if line.strip())


def load_metadata():
    """读 Data_Entry_2017.csv，返回含 Image Index / Patient ID 的 DataFrame。"""
    df = pd.read_csv(CSV_PATH)
    # 官方列名：'Image Index'、'Patient ID'
    df = df[['Image Index', 'Patient ID']].copy()
    df['Patient ID'] = df['Patient ID'].astype(int)
    return df


def get_trainval_test_split(df):
    """
    划分官方 train_val 与 test。

    优先用官方 list 文件（最权威）；若尚未解压，退化为按 Patient ID 数值切分：
    NIH 官方约定 test set 取患者 ID 较大的尾部约 25,596 张 / ~389 名患者。
    退化路径以 patient 数值切（保持 patient-level 不泄漏），并打 TODO。
    """
    trainval_path = _find_official_list(TRAINVAL_LIST_CANDIDATES)
    test_path = _find_official_list(TEST_LIST_CANDIDATES)

    if trainval_path is not None and test_path is not None:
        print(f'[官方 list] train_val: {trainval_path}')
        print(f'[官方 list] test:      {test_path}')
        trainval_imgs = _read_list(trainval_path)
        test_imgs = _read_list(test_path)
        df_tv = df[df['Image Index'].isin(trainval_imgs)].copy()
        df_test = df[df['Image Index'].isin(test_imgs)].copy()
        return df_tv, df_test

    # ---- 退化路径 ----
    # TODO（待解压后核）：官方 list txt（train_val_list_NIH.txt / test_list.txt）
    # 尚未在 data/nih_cxr14/ 出现。此处按 Patient ID 数值尾部切 test 仅为占位，
    # 解压完成后请重跑本脚本，让其走上面的官方 list 分支以对齐官方切分。
    print('[警告] 未找到官方 train_val/test list，退化为按 Patient ID 数值切分。')
    print('       TODO：官方 list 解压后请重跑本脚本以对齐官方划分。')
    patients = np.sort(df['Patient ID'].unique())
    # 官方 test 约占 20%（~389/2885 个患者各异，这里用图数比例近似找患者分界）
    n_test_patients = max(1, int(round(len(patients) * 0.20)))
    test_patients = set(patients[-n_test_patients:].tolist())
    df_test = df[df['Patient ID'].isin(test_patients)].copy()
    df_tv = df[~df['Patient ID'].isin(test_patients)].copy()
    return df_tv, df_test


def sample_pretrain_patients(df_tv, target, rng):
    """
    从 train_val 里按患者随机采样，累加其所有片子直到 >= target 张图。
    返回 (选中的 Image Index 列表, 选中的 patient set)。
    """
    patients = df_tv['Patient ID'].unique().tolist()
    rng.shuffle(patients)
    # 预聚合每个患者的图列表，避免循环里反复过滤
    by_patient = df_tv.groupby('Patient ID')['Image Index'].apply(list).to_dict()

    chosen_imgs = []
    chosen_patients = set()
    for pid in patients:
        if len(chosen_imgs) >= target:
            break
        chosen_imgs.extend(by_patient[pid])
        chosen_patients.add(pid)
    return chosen_imgs, chosen_patients


def write_split(name, img_list):
    os.makedirs(SPLITS_DIR, exist_ok=True)
    path = os.path.join(SPLITS_DIR, name)
    with open(path, 'w') as f:
        for img in img_list:
            f.write(f'{img}\n')
    return path


def report(name, df_all, img_list):
    """打印某 split 的图数 + 患者数。"""
    s = set(img_list)
    sub = df_all[df_all['Image Index'].isin(s)]
    n_imgs = len(img_list)
    n_pat = sub['Patient ID'].nunique()
    print(f'  {name:<26} 图数={n_imgs:<7} 患者数={n_pat}')


def main():
    parser = argparse.ArgumentParser(description='NIH ChestX-ray14 patient-level 切分')
    parser.add_argument('--pretrain_target', type=int, default=PRETRAIN_TARGET,
                        help='pretrain 目标图数（按患者累加至此停）')
    args = parser.parse_args()

    rng = np.random.RandomState(SEED)
    print(f'== NIH ChestX-ray14 patient-level 切分 (seed={SEED}) ==')

    df = load_metadata()
    print(f'总图数={len(df)}  总患者数={df["Patient ID"].nunique()}')

    # 1) 官方 train_val / test
    df_tv, df_test = get_trainval_test_split(df)
    print(f'train_val: 图数={len(df_tv)} 患者数={df_tv["Patient ID"].nunique()}')
    print(f'test:      图数={len(df_test)} 患者数={df_test["Patient ID"].nunique()}')

    # 2) pretrain_10k：从 train_val 按患者采样 ~target 张
    pretrain_imgs, pretrain_patients = sample_pretrain_patients(
        df_tv, args.pretrain_target, rng)

    # 3) probe 池：train_val 里「不属于 pretrain 患者」的全部 → 100% probe 池
    df_probe_pool = df_tv[~df_tv['Patient ID'].isin(pretrain_patients)].copy()
    probe_patients = np.sort(df_probe_pool['Patient ID'].unique())
    # 患者层面打散后取 1% / 10% / 100%（按患者比例，非按图，保持 patient-level）
    rng.shuffle(probe_patients)
    n_pool = len(probe_patients)
    n_1 = max(1, int(round(n_pool * 0.01)))
    n_10 = max(1, int(round(n_pool * 0.10)))
    pat_1 = set(probe_patients[:n_1].tolist())
    pat_10 = set(probe_patients[:n_10].tolist())   # 嵌套：1% ⊂ 10% ⊂ 100%
    pat_100 = set(probe_patients.tolist())

    def imgs_of(pat_set):
        return df_probe_pool[df_probe_pool['Patient ID'].isin(pat_set)]['Image Index'].tolist()

    probe_1 = imgs_of(pat_1)
    probe_10 = imgs_of(pat_10)
    probe_100 = imgs_of(pat_100)

    # 4) probe_test：官方 test 全量
    probe_test = df_test['Image Index'].tolist()

    # ---- 写文件 ----
    write_split('pretrain_10k.txt', pretrain_imgs)
    write_split('probe_train_1pct.txt', probe_1)
    write_split('probe_train_10pct.txt', probe_10)
    write_split('probe_train_100pct.txt', probe_100)
    write_split('probe_test.txt', probe_test)

    # ---- 报告 ----
    print('\n== 各 split 规模 ==')
    report('pretrain_10k', df, pretrain_imgs)
    report('probe_train_1pct', df, probe_1)
    report('probe_train_10pct', df, probe_10)
    report('probe_train_100pct', df, probe_100)
    report('probe_test', df, probe_test)

    # ---- 患者重叠检查（应全为 0）----
    print('\n== 患者重叠检查（应全为 0）==')
    overlaps = {
        'pretrain ∩ probe_pool': pretrain_patients & pat_100,
        'pretrain ∩ probe_test': pretrain_patients & set(df_test['Patient ID'].unique().tolist()),
        'probe_pool ∩ probe_test': pat_100 & set(df_test['Patient ID'].unique().tolist()),
    }
    all_zero = True
    for k, v in overlaps.items():
        print(f'  {k:<26} 重叠患者数={len(v)}')
        if len(v) != 0:
            all_zero = False
    print('  结果：', '全部不重叠 OK' if all_zero else '!! 存在重叠，请检查 !!')


if __name__ == '__main__':
    main()
