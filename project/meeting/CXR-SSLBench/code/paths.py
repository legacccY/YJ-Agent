# -*- coding: utf-8 -*-
"""
CXR-SSLBench Phase 0 pilot —— 中央路径配置（单一真源 .portfolio/datasets.json 的本地落地）

铁律：本文件是 harness 唯一硬编码路径处。任何脚本引数据 / 权重 / repo 一律 import 此处常量，
不在别处重复硬编码、不臆想路径。换路径只改这里。

本地 + HPC 候选都列，运行时 pick 第一个存在的（仿 CheXWorld repo data_utils/data_path.py 风格）。
"""
import os
import sys

# ---------------------------------------------------------------------------
# 候选路径表（本地优先；不存在则退 HPC 绝对路径）
# 真源：.portfolio/datasets.json -> datasets.nih_cxr14 / CheXWorld 权重
# ---------------------------------------------------------------------------
_NIH_IMAGES_CANDS = [
    r'D:/YJ-Agent/project/meeting/Med-NCA/NCA-JEPA/data/nih_cxr14/images-224/images-224',
    # TODO（待主线在 HPC 核实子路径）：HPC NIH root = /gpfs/work/bio/jiayu2403/nca-jepa/data/nih_cxr14/
    # 解压后 png 直挂在该目录还是 images-224/images-224 子目录需 ls 确认，下面给两个候选。
    '/gpfs/work/bio/jiayu2403/nca-jepa/data/nih_cxr14/images-224/images-224',
    '/gpfs/work/bio/jiayu2403/nca-jepa/data/nih_cxr14',
]

_NIH_CSV_CANDS = [
    r'D:/YJ-Agent/project/meeting/Med-NCA/NCA-JEPA/data/nih_cxr14/Data_Entry_2017.csv',
    '/gpfs/work/bio/jiayu2403/nca-jepa/data/nih_cxr14/Data_Entry_2017.csv',
]

_NIH_SPLITS_CANDS = [
    r'D:/YJ-Agent/project/meeting/Med-NCA/NCA-JEPA/data/nih_cxr14/splits',
    '/gpfs/work/bio/jiayu2403/nca-jepa/data/nih_cxr14/splits',  # HPC 实测(2026-06-29 survey)
    '/gpfs/work/bio/jiayu2403/nca-jepa/splits',
]

_CHEXWORLD_TAR_CANDS = [
    r'D:/YJ-Agent/project/meeting/复现/CheXWorld/assets/chexworld_pretrained.tar',
    # TODO（待主线在 HPC 核实）：CheXWorld 权重 HPC 路径未登记到 datasets.json，传后回填。
    '/gpfs/work/bio/jiayu2403/chexworld/assets/chexworld_pretrained.tar',
]

# CheXWorld 复现 repo —— 复用其 models/ (jepa_vit / attentive_pooler) + data_utils 的 transform 常量
_CHEXWORLD_REPO_CANDS = [
    r'D:/YJ-Agent/project/meeting/复现/CheXWorld/repo',
    '/gpfs/work/bio/jiayu2403/chexworld/repo',
]

# VinDr-CXR 跨域 eval（⚠️ 分类标签可用性 researcher 在核；当前 train_meta.csv 仅 image_id/dim，无病理标签 → 跨域 eval 待标签回填）
_VINDR_ROOT_CANDS = [
    r'D:/YJ-Agent/data/external/vindr_cxr',
    '/gpfs/work/bio/jiayu2403/data/vindr_cxr',
]


def _pick(cands, what):
    for p in cands:
        if os.path.exists(p):
            return p
    # 返回第一个候选 + 警告（不 raise：有些脚本只用部分路径，缺的那条到真用时再 assert）
    sys.stderr.write(f'[paths.py][WARN] 未找到 {what}，候选均不存在：{cands}\n')
    return cands[0]


NIH_IMAGES_DIR = _pick(_NIH_IMAGES_CANDS, 'NIH images dir')
NIH_CSV = _pick(_NIH_CSV_CANDS, 'NIH Data_Entry_2017.csv')
NIH_SPLITS_DIR = _pick(_NIH_SPLITS_CANDS, 'NIH splits dir')
CHEXWORLD_TAR = _pick(_CHEXWORLD_TAR_CANDS, 'CheXWorld pretrained .tar')
CHEXWORLD_REPO = _pick(_CHEXWORLD_REPO_CANDS, 'CheXWorld repo')
VINDR_ROOT = _pick(_VINDR_ROOT_CANDS, 'VinDr-CXR root')

# harness 自有产物目录（缓存特征 + 结果 CSV）
_CODE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(_CODE_DIR)                      # .../CXR-SSLBench
CACHE_DIR = os.path.join(PROJECT_DIR, 'cache')               # 冻结特征 .npz / .npy memmap
RESULTS_DIR = os.path.join(PROJECT_DIR, 'results')           # 结果 CSV
WEIGHTS_DIR = os.path.join(CACHE_DIR, 'weights')             # 主线下载的 backbone 权重落地处

# ---------------------------------------------------------------------------
# backbone 权重本地路径（主线 gdown/curl 下到这里；文件下载前不存在，loader 在调用时才 assert）
# 真源 = researcher findings（见 backbones.py 各 _load_* 头注 + README_pilot.md 下载命令）
# 多候选：本地 cache/weights 优先，退 HPC（HPC 子路径待主线核实回填）。
# ---------------------------------------------------------------------------
_MEDICAL_MAE_WEIGHTS_CANDS = [
    os.path.join(WEIGHTS_DIR, 'medical_mae_vitb.pth'),
    '/gpfs/work/bio/jiayu2403/cxr-sslbench/weights/medical_mae_vitb.pth',  # TODO 主线核实 HPC 子路径
]
_CHESS_WEIGHTS_CANDS = [
    os.path.join(WEIGHTS_DIR, 'chess_r50.pth'),
    '/gpfs/work/bio/jiayu2403/cxr-sslbench/weights/chess_r50.pth',         # TODO 主线核实 HPC 子路径
]


def pick_weights(cands):
    """返回首个存在的候选；都不存在则返回 cands[0]（loader 在用时 assert 报清晰错误）。"""
    for p in cands:
        if os.path.exists(p):
            return p
    return cands[0]


MEDICAL_MAE_WEIGHTS = pick_weights(_MEDICAL_MAE_WEIGHTS_CANDS)
CHESS_WEIGHTS = pick_weights(_CHESS_WEIGHTS_CANDS)

# split 文件名映射：label_frac(int %) -> 文件名
SPLIT_BY_FRAC = {
    1:   'probe_train_1pct.txt',
    10:  'probe_train_10pct.txt',
    100: 'probe_train_100pct.txt',
}
TEST_SPLIT = 'probe_test.txt'


def ensure_repo_on_path():
    """把 CheXWorld repo 加入 sys.path，使 `from models.jepa_vit import ...` 可用。"""
    if CHEXWORLD_REPO not in sys.path:
        sys.path.insert(0, CHEXWORLD_REPO)


def split_path(name_or_frac):
    """接受 'probe_test.txt' / 完整路径 / int(1/10/100)，返回 split txt 绝对路径。"""
    if isinstance(name_or_frac, int):
        return os.path.join(NIH_SPLITS_DIR, SPLIT_BY_FRAC[name_or_frac])
    if os.path.isabs(name_or_frac) and os.path.exists(name_or_frac):
        return name_or_frac
    return os.path.join(NIH_SPLITS_DIR, name_or_frac)


if __name__ == '__main__':
    # 静态自检（只打印解析到的路径 + 是否存在，不执行项目逻辑）
    for k in ['NIH_IMAGES_DIR', 'NIH_CSV', 'NIH_SPLITS_DIR', 'CHEXWORLD_TAR',
              'CHEXWORLD_REPO', 'VINDR_ROOT', 'CACHE_DIR', 'RESULTS_DIR']:
        v = globals()[k]
        print(f'{k:18s} exists={os.path.exists(v)!s:5s} {v}')
