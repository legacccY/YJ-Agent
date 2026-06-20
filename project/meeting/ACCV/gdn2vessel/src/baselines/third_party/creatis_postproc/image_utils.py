# Vendored from: https://github.com/creatis-myriad/plug-and-play-reco-regularization
# Path in repo: sources/source_2D/image_utils.py  (or utils/image_utils.py)
# License: CeCILL (http://www.cecill.info) — French free software license;
#          academic use PERMITTED; cite [1][2] when publishing.
# Fetched: 2026-06-20 (main branch)
# Modifications:
#   - Port to standalone module; no other changes.
#
# TODO_researcher (TODO-3): 官方 image_utils.normalize_image 第二参数 max_val 的精确
#   语义未核实（sources/image_utils.py 在 2026-06-20 抓取时未获取到完整实现）。
#   此处实现按最可能语义：normalize_image(image, max_val=1) → image.astype(float)/255.0*max_val
#   即 max_val=1 时等效 /255，产生 [0,1] float。
#   须与官方源码对账后确认；若官方语义不同需同步修 apply_postproc_iterations。

"""
image_utils.py — 图像归一化工具（creatis 官方 port）。
"""

from __future__ import annotations

import numpy as np


def normalize_image(image: np.ndarray, max_val: float = 1.0) -> np.ndarray:
    """
    归一化二值分割图到 [0, max_val]。

    官方调用方式 (post_treatement.py):
        image = image_utils.normalize_image(image, 1)
    等效于将 uint8 {0,255} 图像除以 255 得到 [0,1] float32。

    Args:
        image   : numpy array，通常为 uint8 {0,255}（二值分割图）。
        max_val : 目标最大值（官方传 1 → 结果在 [0,1]）。

    Returns:
        float32 numpy array，值域 [0, max_val]。

    NOTE — TODO_researcher: 官方 image_utils.normalize_image 的第二参数语义
      在 2026-06-20 未能从官方仓库获取完整实现。当前实现假设：
        normalized = image.astype(float) / 255.0 * max_val
      即对 {0,255} 输入，max_val=1 → [0,1]；max_val=255 → 原值域。
      须核对官方 sources/source_2D/image_utils.py 确认。
    """
    return (image.astype(np.float64) / 255.0 * max_val).astype(np.float32)
