# Vendored from: https://github.com/creatis-myriad/plug-and-play-reco-regularization
# Path in repo: sources/source_2D/disconnect.py
# License: CeCILL (http://www.cecill.info) — French free software license;
#          academic use PERMITTED; cite [1][2] when publishing.
#          [1] Carneiro-Esteves et al., Neurocomputing 2024
#          [2] Carneiro-Esteves et al., TGI3 MICCAI Workshop 2024
# Fetched: 2026-06-20 (main branch)
# Modifications:
#   - Port to standalone Python module (removed file I/O + dataset builder).
#   - create_disconnections() and create_dataset() logic faithfully ported.
#
# Dependencies (already in gdn2venv):
#   scipy  >= 1.15.3  (distance_transform_bf, binary_dilation, gaussian_filter)
#   skimage >= 0.25.2  (skeletonize, disk morphology)
#   numpy  >= 1.x

"""
disconnect.py — 官方断点生成协议（creatis plug-and-play, 2D）。

核心函数:
  create_disconnections(groundTruth, nb_disconnection, size_max)
    → (input_with_artifacts, pos_dilation_mask)
      input_with_artifacts : (H,W) uint8 {0,255}，含人工断点的血管图
      pos_dilation_mask    : (H,W) uint8 {0,255}，断点区域膨胀 mask（= PonderatedDiceloss 的 mask）

create_dataset() 为批量生成入口（见函数注释）。

断点参数（论文 §3.1）:
  mean size s ∈ {6, 8, 10, 12}，σ=4（2D）
  nb_disconnection: TODO_researcher（官方 disconnect.py 默认值未从源码获取到，
    此参数须由调用方显式传入或由 researcher 核官方后确认默认值）。
"""

from __future__ import annotations

import warnings
from typing import Optional, Tuple

import numpy as np
from scipy.ndimage import binary_dilation, distance_transform_bf, gaussian_filter
from skimage.morphology import disk, skeletonize


# --------------------------------------------------------------------------- #
#  内部辅助
# --------------------------------------------------------------------------- #

def _make_disk_patch(radius: int) -> np.ndarray:
    """生成半径 radius 的实心圆盘（bool array）。"""
    d = disk(radius)
    return d.astype(bool)


def _place_disconnection(
    image: np.ndarray,
    center_rc: Tuple[int, int],
    break_radius: int,
    nb_pix: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """
    在 image 中以 center_rc 为中心，在 break_radius 圆盘内随机撒 nb_pix 个黑点，
    经 gaussian(σ=0.7) 平滑后阈值 0.4 二值化，抹除血管像素。

    官方逻辑：circle + random pixel erosion + gaussian smooth → threshold at 0.4。

    Returns:
        (H,W) uint8 — 已打断的图像副本。
    """
    H, W = image.shape
    r, c = center_rc
    result = image.copy().astype(np.float32)

    # 圆盘范围内的坐标
    d = _make_disk_patch(break_radius)
    rr_off, cc_off = np.where(d)
    half = break_radius
    rr = rr_off - half + r
    cc = cc_off - half + c

    # 裁剪到图像边界
    valid = (rr >= 0) & (rr < H) & (cc >= 0) & (cc < W)
    rr, cc = rr[valid], cc[valid]

    if len(rr) == 0:
        return image  # 中心在边界外，跳过

    # 随机选 nb_pix 个像素抹黑
    nb_pix = min(nb_pix, len(rr))
    chosen = rng.choice(len(rr), size=nb_pix, replace=False)
    result[rr[chosen], cc[chosen]] = 0.0

    # 高斯平滑后阈值化重建二值图（官方：gaussian σ=0.7, threshold=0.4）
    smoothed = gaussian_filter(result / 255.0, sigma=0.7)
    binary = (smoothed >= 0.4).astype(np.uint8) * 255

    return binary


# --------------------------------------------------------------------------- #
#  主函数
# --------------------------------------------------------------------------- #

def create_disconnections(
    groundTruth: np.ndarray,
    nb_disconnection: int,
    size_max: int,
    rng: Optional[np.random.Generator] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    官方 disconnect.py: create_disconnections() 忠实 port。

    在 groundTruth 血管图上生成人工断点，并返回断点膨胀 mask。

    算法（官方 sources/source_2D/disconnect.py）：
      1. skeleton = skeletonize(GT); radius_map = distance_transform_bf(GT,'chessboard') * skeleton
         → 骨架点处血管半径
      2. 按半径分桶（urns），取最细 3 类 urns[:3]（细血管优先）
      3. 加权采样断点中心：weight_i = (2^(n-i-1)) / (2^n - 1)（指数下降，最细权最大）
      4. 每个断点：
           mean_deco_size = size_max // vessel_size（对应桶的细度）
           actual_size ~ N(mean_deco_size, σ=4)，clip ≥ 1
           50% dense: nb_pix ~ N(nb_pix_max/2, nb_pix_max/4)
           50% sparse: nb_pix ~ N(nb_pix_max/4, nb_pix_max/8)
           （nb_pix_max = disk area within actual_size）
      5. place_disconnection → gaussian(σ=0.7) → threshold 0.4
      6. fragments = labels_with_art - inputs（断点区域）
         pos = binary_dilation(fragments, disk(2)) → mask（PonderatedDiceloss 用）

    Args:
        groundTruth     : (H,W) uint8 {0,255} 血管 GT 图。
        nb_disconnection: 断点数量。
                          TODO_researcher: 官方 disconnect.py 此参数默认值未获取到，
                          须核官方源码（sources/source_2D/disconnect.py）确认。
                          调用方须显式传入。
        size_max        : 断点最大半径（论文 §3.1: s ∈ {6,8,10,12}，σ=4(2D)）。
        rng             : numpy random Generator（None 则用 default_rng()）。

    Returns:
        input_with_art : (H,W) uint8 {0,255}，含断点的分割图（相当于 Stage-2 输入）。
        pos_mask       : (H,W) uint8 {0,255}，断点膨胀 mask（PonderatedDiceloss mask 列）。

    NOTE: 若 GT 中无血管像素，返回原图 + 全零 mask（发出警告）。
    """
    if rng is None:
        rng = np.random.default_rng()

    # 确保 uint8 {0,255}
    gt = groundTruth.astype(np.uint8)
    if gt.max() <= 1:
        gt = (gt * 255).astype(np.uint8)

    H, W = gt.shape
    gt_bool = gt > 0

    # 无血管像素
    if gt_bool.sum() == 0:
        warnings.warn(
            "create_disconnections: groundTruth contains no foreground pixels. "
            "Returning original image with zero pos_mask.",
            UserWarning,
        )
        return gt.copy(), np.zeros_like(gt)

    # Step 1: 骨架 + 血管半径图
    skeleton = skeletonize(gt_bool)  # bool (H,W)
    # distance_transform_bf 返回每个前景像素到最近背景的距离（chessboard metric）
    dist_map = distance_transform_bf(gt_bool.astype(np.uint8), metric="chessboard").astype(np.float32)
    radius_map = dist_map * skeleton.astype(np.float32)  # 骨架点血管半径

    # Step 2: 骨架点分桶（按半径从小到大）
    skel_coords = np.array(np.where(skeleton)).T  # (N, 2) [row, col]
    radii_at_skel = radius_map[skeleton]           # (N,) 各骨架点半径

    if len(skel_coords) == 0:
        warnings.warn(
            "create_disconnections: skeleton empty. Returning original + zero mask.",
            UserWarning,
        )
        return gt.copy(), np.zeros_like(gt)

    # 桶：按半径离散化（radius=1,2,3,...），官方取最细 3 类
    unique_radii = np.unique(radii_at_skel)
    unique_radii = unique_radii[unique_radii > 0]
    unique_radii_sorted = np.sort(unique_radii)  # 升序 → 最细在前

    urns = []  # list of coord-arrays per radius group
    for r_val in unique_radii_sorted:
        mask = (radii_at_skel == r_val)
        urns.append(skel_coords[mask])

    # 取最细 3 类（官方 urns[:3]）
    fine_urns = urns[:3]
    n = len(fine_urns)
    if n == 0:
        return gt.copy(), np.zeros_like(gt)

    # Step 3: 加权采样权重 w_i = (2^(n-i-1)) / (2^n - 1)
    weights_unnorm = np.array(
        [2 ** (n - i - 1) for i in range(n)], dtype=np.float64
    )
    denom = 2 ** n - 1
    if denom == 0:
        denom = 1
    weights = weights_unnorm / denom  # 归一化概率

    # 根据 nb_disconnection 采样各桶贡献数
    # 官方实现：对 nb_disconnection 次独立采样选桶，再从该桶采坐标
    urn_indices = rng.choice(n, size=nb_disconnection, p=weights)

    # vessel_size per bucket（使用对应 unique_radius 值，越小越细）
    fine_radii = unique_radii_sorted[:n]

    input_with_art = gt.copy()

    for idx in urn_indices:
        coords_pool = fine_urns[idx]
        if len(coords_pool) == 0:
            continue

        center = coords_pool[rng.integers(len(coords_pool))]
        vessel_size = max(1, int(fine_radii[idx]))

        # Step 4: 断点尺寸
        mean_deco_size = max(1, size_max // vessel_size)
        actual_size = int(max(1, rng.normal(loc=mean_deco_size, scale=4)))

        # 圆盘面积上限
        d_patch = _make_disk_patch(actual_size)
        nb_pix_max = int(d_patch.sum())

        # 50% dense / 50% sparse
        if rng.random() < 0.5:
            # dense
            nb_pix = int(max(1, rng.normal(loc=nb_pix_max / 2, scale=nb_pix_max / 4)))
        else:
            # sparse
            nb_pix = int(max(1, rng.normal(loc=nb_pix_max / 4, scale=nb_pix_max / 8)))

        input_with_art = _place_disconnection(
            input_with_art,
            center_rc=(center[0], center[1]),
            break_radius=actual_size,
            nb_pix=nb_pix,
            rng=rng,
        )

    # Step 6: pos mask = binary_dilation(fragments, disk(2))
    # fragments = original GT - 已有断点的图（二值差）
    fragments = ((gt > 0).astype(np.uint8) - (input_with_art > 0).astype(np.uint8))
    fragments = np.clip(fragments, 0, 1).astype(bool)

    pos_dilated = binary_dilation(fragments, structure=disk(2))
    pos_mask = (pos_dilated.astype(np.uint8) * 255)

    return input_with_art, pos_mask


def create_dataset(
    gt_images: list,
    nb_disconnection: int,
    size_max: int,
    rng: Optional[np.random.Generator] = None,
) -> list:
    """
    批量生成断点数据集（官方 create_dataset 的简化 port）。

    对每张 GT 图调用 create_disconnections，返回 (input_with_art, gt, pos_mask) 三元组列表。

    Args:
        gt_images       : list of (H,W) uint8 {0,255} GT 血管图。
        nb_disconnection: 每图断点数（TODO_researcher: 官方默认值未核实）。
        size_max        : 断点最大半径。
        rng             : numpy random Generator。

    Returns:
        list of dict: {"input": (H,W) uint8, "gt": (H,W) uint8, "pos": (H,W) uint8}
    """
    if rng is None:
        rng = np.random.default_rng()

    results = []
    for gt in gt_images:
        input_art, pos = create_disconnections(gt, nb_disconnection, size_max, rng=rng)
        results.append({"input": input_art, "gt": gt, "pos": pos})
    return results
