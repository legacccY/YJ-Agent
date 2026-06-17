"""
test_idrid_g1a.py — IDRiD 眼底 DR 适配器单元测试（Phase 1 G1-a 负臂 n=3）
服务: MedAD-FailMap Phase 1, PC-B Gate1 G1-a 几何同构验证
lever: A' 病灶几何双峰，负臂 n=3 实证

全部合成数据，无真实数据依赖，纯 CPU，几秒内跑完。

覆盖:
  I1: segment_fov 正确分割圆形 FOV + 黑角（最大连通域 = 圆形区）
  I2: area_ratio_fov > area_ratio_full（FOV 分母 < 全图分母）
  I3: area_ratio_fov ∈ [0, 1] 断言不崩溃
  I4: 多灶病变 n_components > 1（多个分离小斑点）
  I5: 无病理 mask 时 lesion_px=0, n_components=0, area_ratio_fov=0 不 crash
  I6: union 逻辑正确（MA+HE 两个不重叠区域 union_px = ma_px + he_px）
  I7: 全黑图 segment_fov 返回 fov_px=0，area_ratio_fov=nan 不 crash
  I8: batch_extract_idrid 输出 csv schema 包含所有必需列
"""

import csv
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

# 把 code/ 加到 sys.path
CODE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CODE_DIR))

from lesion_features_idrid import (
    segment_fov,
    extract_idrid_features,
    batch_extract_idrid,
    _LESION_TYPES,
)


# ============================================================
# Fixture helpers
# ============================================================

def _make_fundus(tmp_path, img_id="IDRiD_01", size=128,
                 fov_radius_frac=0.42, lesion_spots=None,
                 all_black=False):
    """
    合成眼底图 + DR mask 文件。

    fov_radius_frac: retina 圆形 FOV 半径占图宽百分比（默认 0.42）
    lesion_spots: dict {type_key: [(cx, cy, r), ...]}，各 type 小圆斑
      type_key ∈ {MA, HE, EX, SE}
    all_black: True → 全黑图（模拟极端情况）
    """
    img_dir  = tmp_path / "imgs"
    mask_dir = tmp_path / "masks"
    img_dir.mkdir(parents=True, exist_ok=True)

    # 创建各 type 子目录（与真实 IDRiD 结构一致）
    for key, (subdir, _suffix) in _LESION_TYPES.items():
        (mask_dir / subdir).mkdir(parents=True, exist_ok=True)

    # 合成眼底图（RGB）
    arr = np.zeros((size, size, 3), dtype=np.uint8)
    if not all_black:
        # 黑色背景（黑角模拟）；中央圆 = retina（亮）
        cy, cx = size // 2, size // 2
        r_fov = int(size * fov_radius_frac)
        Y, X = np.ogrid[:size, :size]
        circle = (X - cx) ** 2 + (Y - cy) ** 2 <= r_fov ** 2
        arr[circle] = 160  # 模拟眼底橙红色（灰度约 160）

    pil_img = Image.fromarray(arr)
    img_path = img_dir / f"{img_id}.jpg"
    pil_img.save(str(img_path))

    # 合成 lesion mask
    if lesion_spots is None:
        lesion_spots = {}

    mask_paths = {}
    for key, (subdir, suffix) in _LESION_TYPES.items():
        mask_arr = np.zeros((size, size), dtype=np.uint8)
        spots = lesion_spots.get(key, [])
        for (sx, sy, sr) in spots:
            Y, X = np.ogrid[:size, :size]
            spot = (X - sx) ** 2 + (Y - sy) ** 2 <= sr ** 2
            mask_arr[spot] = 255
        pil_mask = Image.fromarray(mask_arr)
        tif_path = mask_dir / subdir / f"{img_id}{suffix}.tif"
        pil_mask.save(str(tif_path))
        mask_paths[key] = tif_path

    return img_path, mask_dir, img_dir


# ============================================================
# I1: segment_fov 正确分割圆形 FOV + 黑角
# ============================================================

def test_I1_segment_fov_circle(tmp_path):
    """FOV Otsu 取最大连通域 = 圆形 retina，黑角排除。"""
    size = 128
    arr = np.zeros((size, size), dtype=np.uint8)
    cy, cx = size // 2, size // 2
    r_fov = 50
    Y, X = np.ogrid[:size, :size]
    circle = (X - cx) ** 2 + (Y - cy) ** 2 <= r_fov ** 2
    arr[circle] = 160  # 模拟 retina

    fov_mask, otsu_thr, fov_px = segment_fov(arr)

    # FOV 应覆盖圆内大部分像素
    expected_px = int(circle.sum())
    assert fov_px > 0, "FOV px 应 > 0"
    # 最大连通域应接近理论圆面积（允许 Otsu 误差 ±15%）
    assert abs(fov_px - expected_px) / expected_px < 0.15, (
        f"fov_px={fov_px} 偏离理论 {expected_px} 超 15%"
    )
    # 黑角（四角）不应在 FOV mask 内
    corners = [
        fov_mask[0, 0], fov_mask[0, -1],
        fov_mask[-1, 0], fov_mask[-1, -1],
    ]
    assert not any(corners), "黑角不应在 FOV mask 内"


# ============================================================
# I2: area_ratio_fov > area_ratio_full
# ============================================================

def test_I2_area_ratio_fov_gt_full(tmp_path):
    """FOV 分母 < 全图分母 → area_ratio_fov > area_ratio_full（有病灶时）。"""
    size = 128
    cy, cx = size // 2, size // 2
    lesion_spots = {
        "MA": [(cx, cy, 5)],   # 中央小圆 MA
    }
    img_path, mask_dir, img_dir = _make_fundus(
        tmp_path, size=size, lesion_spots=lesion_spots
    )
    feats = extract_idrid_features(
        img_path, mask_dir, "IDRiD_01", img_size=64
    )
    assert feats["lesion_px"] > 0, "应有病灶"
    assert feats["area_ratio_fov"] > feats["area_ratio_full"], (
        f"area_ratio_fov={feats['area_ratio_fov']:.4f} 应 > "
        f"area_ratio_full={feats['area_ratio_full']:.4f}"
    )


# ============================================================
# I3: area_ratio ∈ [0, 1] 断言
# ============================================================

def test_I3_area_ratio_in_range(tmp_path):
    """area_ratio_fov 和 area_ratio_full 均在 [0, 1]，断言不崩溃。"""
    size = 128
    cy, cx = size // 2, size // 2
    lesion_spots = {
        "EX": [(cx, cy, 8)],
    }
    img_path, mask_dir, img_dir = _make_fundus(
        tmp_path, size=size, lesion_spots=lesion_spots
    )
    feats = extract_idrid_features(
        img_path, mask_dir, "IDRiD_01", img_size=64
    )
    arf = feats["area_ratio_fov"]
    if arf == arf:  # not nan
        assert 0.0 <= arf <= 1.0, f"area_ratio_fov={arf} 超出 [0,1]"
    assert 0.0 <= feats["area_ratio_full"] <= 1.0


# ============================================================
# I4: 多灶病变 n_components > 1
# ============================================================

def test_I4_n_components_multi(tmp_path):
    """多个分离 MA 斑点 → n_components > 1（多灶性，A' 双峰论据）。"""
    size = 128
    # 四个间距足够大的小圆斑（4-连通不相连）
    spots = [(30, 30, 3), (90, 30, 3), (30, 90, 3), (90, 90, 3)]
    lesion_spots = {"MA": spots}
    img_path, mask_dir, img_dir = _make_fundus(
        tmp_path, size=size, lesion_spots=lesion_spots, fov_radius_frac=0.48
    )
    feats = extract_idrid_features(
        img_path, mask_dir, "IDRiD_01", img_size=64
    )
    # resize 64²：原 128×128 坐标 ÷2 → spots 在约 (15,15),(45,15),(15,45),(45,45)，仍分离
    assert feats["n_components"] > 1, (
        f"多灶斑点应 n_components>1，实得 {feats['n_components']}"
    )


# ============================================================
# I5: 无病理 mask（lesion_px=0）
# ============================================================

def test_I5_no_lesion_mask(tmp_path):
    """无任何病理 mask → lesion_px=0, n_components=0, area_ratio_fov=0.0，不 crash。"""
    img_path, mask_dir, img_dir = _make_fundus(
        tmp_path, lesion_spots={}
    )
    feats = extract_idrid_features(
        img_path, mask_dir, "IDRiD_01", img_size=64
    )
    assert feats["lesion_px"] == 0
    assert feats["n_components"] == 0
    assert feats["area_ratio_fov"] == 0.0
    assert feats["area_ratio_full"] == 0.0


# ============================================================
# I6: union 逻辑正确（不重叠 MA + HE → union_px = ma_px + he_px）
# ============================================================

def test_I6_union_nonoverlap(tmp_path):
    """两个不重叠区域 union_px = ma_px + he_px。"""
    size = 128
    # MA: 左上小圆，HE: 右下小圆，不重叠
    lesion_spots = {
        "MA": [(25, 25, 8)],
        "HE": [(100, 100, 8)],
    }
    img_path, mask_dir, img_dir = _make_fundus(
        tmp_path, size=size, lesion_spots=lesion_spots, fov_radius_frac=0.48
    )
    feats = extract_idrid_features(
        img_path, mask_dir, "IDRiD_01", img_size=64
    )
    # resize 到 64 → union_px ≈ ma_px + he_px（允许边缘舍入 ±2px²）
    total = feats["ma_px"] + feats["he_px"] + feats["ex_px"] + feats["se_px"]
    # lesion_px = union，不重叠时 = sum
    assert abs(feats["lesion_px"] - total) <= 4, (
        f"union={feats['lesion_px']}  sum_types={total}  diff={abs(feats['lesion_px']-total)}"
    )
    # n_components 应 >= 2（两个分离区域）
    assert feats["n_components"] >= 2


# ============================================================
# I7: 全黑图 → fov_px=0，area_ratio_fov=nan，不 crash
# ============================================================

def test_I7_all_black_image(tmp_path):
    """全黑图 FOV 分割失败 → fov_px=0，area_ratio_fov=nan（不 crash，不触发断言）。"""
    img_path, mask_dir, img_dir = _make_fundus(
        tmp_path, all_black=True, lesion_spots={}
    )
    feats = extract_idrid_features(
        img_path, mask_dir, "IDRiD_01", img_size=64
    )
    # 全黑无 FOV：fov_px 极小或 0
    # area_ratio_fov=nan（fov_px=0）或 0.0（lesion_px=0）均可接受
    # 关键：不崩溃，不触发断言
    assert feats["lesion_px"] == 0
    arf = feats["area_ratio_fov"]
    # nan 或 0.0 均合法
    assert (arf != arf) or (arf == 0.0), f"全黑图 area_ratio_fov 应为 nan 或 0，实得 {arf}"


# ============================================================
# I8: batch_extract_idrid 输出 csv schema
# ============================================================

def test_I8_batch_csv_schema(tmp_path):
    """batch_extract_idrid 输出 csv 包含所有必需列。"""
    size = 128
    lesion_spots = {"MA": [(64, 64, 6)], "HE": [(40, 80, 5)]}

    img_path, mask_dir, img_dir = _make_fundus(
        tmp_path, img_id="IDRiD_01", size=size, lesion_spots=lesion_spots
    )

    out_csv = tmp_path / "out" / "lesion_features_idrid.csv"
    rows = batch_extract_idrid(
        img_dir=str(img_dir),
        mask_root=str(mask_dir),
        out_csv=str(out_csv),
        img_size=64,
    )

    # 检查返回结果非空
    assert len(rows) >= 1, "batch 应有 >=1 行输出"

    # 检查 csv 文件存在
    assert out_csv.exists(), "csv 文件未生成"

    # 检查所有必需列
    required_cols = {
        "image_id", "fov_px", "lesion_px",
        "area_ratio_fov", "area_ratio_full",
        "n_components", "ma_px", "he_px", "ex_px", "se_px",
    }
    with open(out_csv, newline="") as f:
        reader = csv.DictReader(f)
        actual_cols = set(reader.fieldnames or [])

    missing = required_cols - actual_cols
    assert not missing, f"csv 缺列: {missing}"
