"""
test_lgg_g1a.py — LGG-MRI G1-a 同构判定单元测试
服务: MedAD-FailMap Phase 1 G1-a，§STORY② iso=True 正臂锚

全部合成数据，无真实数据依赖，纯 CPU，几秒内跑完。

覆盖：
  L1: extract_slice_features 单切片 n_components 正确（4-连通，与 ncomp_brats.py 口径一致）
  L2: n_components 单灶 = 1（无论灶大小）
  L3: extract_slice_features area_ratio_full = size_px / 64²
  L4: 空 mask -> size_px=0, n_components=0, area_ratio_full=0.0，不 crash
  L5: area_ratio_full 断言 [0,1] — 异常 mask 触发 ValueError
  L6: batch_extract_lgg 仅包含非空 mask 切片（空 mask 切片过滤掉）
  L7: batch_extract_lgg 输出 csv schema 含所有必需列
  L8: compute_g1a_iso iso_area 门正确（合成全落低区 -> True；全落高区 -> False）
  L9: compute_g1a_iso iso_ncomp 门正确（全 ≤3 -> True；全 >3 -> False）
  L10: iso = iso_area AND iso_ncomp（两维均须 True）
  L11: 口径不动 Phase 0 — import lesion_features_lgg 不改 distribution_overlap 常量
"""

import csv
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

# 把 code/ 加到 sys.path
CODE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CODE_DIR))

from lesion_features_lgg import (
    extract_slice_features,
    batch_extract_lgg,
    compute_g1a_iso,
    BRATS_P25_AREA_RATIO_FULL,
    BRATS_P75_NCOMP,
    MIN_OVERLAP_FRAC_AREA,
    MIN_OVERLAP_FRAC_NCOMP,
    _IMG_SIZE,
)


# ============================================================
# Fixture helpers
# ============================================================

def _make_lgg_slice(tmp_path, patient_id="TCGA_XX_0001_20000101",
                    size=256, spots=None, empty_mask=False):
    """
    合成单张 LGG 切片（RGB tif + mask tif）。

    spots: list of (cx, cy, r) 圆形肿瘤斑点（mask 前景）；
           None = 单个中央圆（半径 30）
    empty_mask: True = 全零 mask
    """
    pat_dir = tmp_path / patient_id
    pat_dir.mkdir(parents=True, exist_ok=True)

    # 合成 RGB 图（ch1=FLAIR 有信号，模拟未剥离脑图）
    img_arr = np.full((size, size, 3), 100, dtype=np.uint8)  # 均匀灰度
    img_path = pat_dir / f"{patient_id}_1.tif"
    Image.fromarray(img_arr).save(str(img_path))

    # 合成 mask
    mask_arr = np.zeros((size, size), dtype=np.uint8)
    if not empty_mask:
        if spots is None:
            # 默认：单个中央圆
            cy, cx = size // 2, size // 2
            r = 30
            Y, X = np.ogrid[:size, :size]
            circle = (X - cx) ** 2 + (Y - cy) ** 2 <= r ** 2
            mask_arr[circle] = 255
        else:
            for (cx, cy, r) in spots:
                Y, X = np.ogrid[:size, :size]
                circle = (X - cx) ** 2 + (Y - cy) ** 2 <= r ** 2
                mask_arr[circle] = 255

    mask_path = pat_dir / f"{patient_id}_1_mask.tif"
    Image.fromarray(mask_arr).save(str(mask_path))

    return img_path, mask_path


def _make_brats_ncomp_csv(tmp_path, ncomp_values):
    """合成 BraTS ncomp csv（ncomp_brats.py 口径）"""
    p = tmp_path / "ncomp_brats.csv"
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["filename","seg_filename","n_components"])
        w.writeheader()
        for i, v in enumerate(ncomp_values):
            w.writerow({
                "filename": f"BraTS2021_0001_flair_{i}.png",
                "seg_filename": f"BraTS2021_0001_seg_{i}.png",
                "n_components": v,
            })
    return p


def _make_brats_area_full_csv(tmp_path, area_full_values):
    """合成 brats_brain_px.csv（含 area_ratio_full 列）"""
    p = tmp_path / "brats_brain_px.csv"
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "filename","brain_px","brain_threshold","full_frame_px",
            "brain_method","size_px","area_ratio_brain","area_ratio_full",
        ])
        w.writeheader()
        for i, v in enumerate(area_full_values):
            w.writerow({
                "filename": f"BraTS2021_0001_flair_{i}.png",
                "brain_px": 1600, "brain_threshold": 1e-6,
                "full_frame_px": 4096, "brain_method": "nonzero",
                "size_px": int(v * 4096),
                "area_ratio_brain": round(v * 4096 / 1600, 6),
                "area_ratio_full": round(v, 6),
            })
    return p


# ============================================================
# L1: n_components 口径一致（多灶 4-连通）
# ============================================================

def test_L1_ncomp_multi_lesion(tmp_path):
    """两个间距足够大的圆斑 -> n_components = 2（4-连通）。"""
    # 原图 256: spots 分别在左上和右下
    spots = [(50, 50, 15), (200, 200, 15)]
    img_p, mask_p = _make_lgg_slice(tmp_path, spots=spots)
    feats = extract_slice_features(img_p, mask_p, img_size=64)
    # resize 到 64: 原 256 -> 64，坐标 /4，spots @ (12,12) and (50,50)，仍分离
    assert feats["n_components"] == 2, (
        f"两分离斑点应 n_components=2，得 {feats['n_components']}"
    )


# ============================================================
# L2: 单灶 n_components = 1
# ============================================================

def test_L2_ncomp_single_lesion(tmp_path):
    """单个连通圆斑 -> n_components = 1。"""
    img_p, mask_p = _make_lgg_slice(tmp_path)  # 默认单圆
    feats = extract_slice_features(img_p, mask_p, img_size=64)
    assert feats["n_components"] == 1, (
        f"单灶应 n_components=1，得 {feats['n_components']}"
    )


# ============================================================
# L3: area_ratio_full = size_px / 64²
# ============================================================

def test_L3_area_ratio_formula(tmp_path):
    """area_ratio_full = size_px / (img_size * img_size)。"""
    img_p, mask_p = _make_lgg_slice(tmp_path)
    feats = extract_slice_features(img_p, mask_p, img_size=64)
    expected = feats["size_px"] / (64.0 * 64.0)
    assert abs(feats["area_ratio_full"] - expected) < 1e-5, (
        f"area_ratio_full={feats['area_ratio_full']}，"
        f"expected size_px/{64*64}={expected:.6f}"
    )


# ============================================================
# L4: 空 mask -> size_px=0, n_components=0, area_ratio_full=0.0
# ============================================================

def test_L4_empty_mask(tmp_path):
    """空 mask（无肿瘤）-> 特征全零，不 crash。"""
    img_p, mask_p = _make_lgg_slice(tmp_path, empty_mask=True)
    feats = extract_slice_features(img_p, mask_p, img_size=64)
    assert feats["size_px"] == 0
    assert feats["n_components"] == 0
    assert feats["area_ratio_full"] == 0.0


# ============================================================
# L5: area_ratio_full ∈ [0, 1] 断言（正常 mask 不触发）
# ============================================================

def test_L5_area_ratio_in_range(tmp_path):
    """正常 mask area_ratio_full ∈ [0, 1]，不触发 ValueError。"""
    img_p, mask_p = _make_lgg_slice(tmp_path)
    feats = extract_slice_features(img_p, mask_p, img_size=64)
    assert 0.0 <= feats["area_ratio_full"] <= 1.0, (
        f"area_ratio_full={feats['area_ratio_full']} 超出 [0,1]"
    )


# ============================================================
# L6: batch_extract_lgg 过滤空 mask 切片
# ============================================================

def test_L6_batch_filters_empty_masks(tmp_path):
    """batch_extract_lgg 只输出非空 mask 切片（空 mask = 跳过）。"""
    lgg_root = tmp_path / "kaggle_3m"
    lgg_root.mkdir()

    # patient A: 1 张有肿瘤 + 1 张无肿瘤
    pat_dir = lgg_root / "TCGA_A_0001_20000101"
    pat_dir.mkdir()

    # 有肿瘤
    arr_img  = np.full((64, 64, 3), 120, dtype=np.uint8)
    arr_mask = np.zeros((64, 64), dtype=np.uint8)
    arr_mask[20:40, 20:40] = 255  # 20×20 块
    Image.fromarray(arr_img).save(str(pat_dir / "TCGA_A_0001_20000101_1.tif"))
    Image.fromarray(arr_mask).save(str(pat_dir / "TCGA_A_0001_20000101_1_mask.tif"))

    # 无肿瘤（空 mask）
    arr_empty_mask = np.zeros((64, 64), dtype=np.uint8)
    Image.fromarray(arr_img).save(str(pat_dir / "TCGA_A_0001_20000101_2.tif"))
    Image.fromarray(arr_empty_mask).save(str(pat_dir / "TCGA_A_0001_20000101_2_mask.tif"))

    out_csv = tmp_path / "out" / "lesion_features_lgg.csv"
    rows = batch_extract_lgg(lgg_root=str(lgg_root), out_csv=str(out_csv), img_size=64)

    # 只有 1 行（有肿瘤的）
    assert len(rows) == 1, f"应只有 1 行输出（过滤空 mask），实得 {len(rows)}"
    assert rows[0]["n_components"] >= 1


# ============================================================
# L7: batch_extract_lgg 输出 csv schema
# ============================================================

def test_L7_batch_csv_schema(tmp_path):
    """batch_extract_lgg 输出 csv 含所有必需列。"""
    lgg_root = tmp_path / "kaggle_3m"
    lgg_root.mkdir()
    pat_dir = lgg_root / "TCGA_B_0001_20000101"
    pat_dir.mkdir()

    arr_img  = np.full((64, 64, 3), 100, dtype=np.uint8)
    arr_mask = np.zeros((64, 64), dtype=np.uint8)
    arr_mask[10:30, 10:30] = 255
    Image.fromarray(arr_img).save(str(pat_dir / "TCGA_B_0001_20000101_1.tif"))
    Image.fromarray(arr_mask).save(str(pat_dir / "TCGA_B_0001_20000101_1_mask.tif"))

    out_csv = tmp_path / "out" / "lgg.csv"
    batch_extract_lgg(lgg_root=str(lgg_root), out_csv=str(out_csv), img_size=64)

    assert out_csv.exists()
    with open(out_csv, newline="") as f:
        reader = csv.DictReader(f)
        actual_cols = set(reader.fieldnames or [])

    required = {"filename", "patient_id", "size_px", "n_components",
                "area_ratio_full", "brain_px_note", "overlaps_brats2021"}
    missing = required - actual_cols
    assert not missing, f"csv 缺列: {missing}"


# ============================================================
# L8: compute_g1a_iso iso_area 门
# ============================================================

def test_L8_iso_area_true(tmp_path):
    """全部 LGG 切片 area_ratio 落低区 -> iso_area=True。"""
    # 构造 LGG rows（area_ratio_full 全部 = 0.01 < BRATS_P25=0.0198）
    low_val = BRATS_P25_AREA_RATIO_FULL * 0.5  # 0.0099
    rows = [
        {"area_ratio_full": low_val, "n_components": 1}
        for _ in range(100)
    ]

    brats_ncomp_csv = _make_brats_ncomp_csv(tmp_path, [1, 2, 1, 3, 2] * 40)
    brats_area_csv  = _make_brats_area_full_csv(tmp_path, [0.03, 0.05, 0.02, 0.04, 0.025] * 40)
    out_dir = tmp_path / "phase1_out"

    result = compute_g1a_iso(
        rows=rows,
        brats_ncomp_csv=str(brats_ncomp_csv),
        brats_area_full_csv=str(brats_area_csv),
        out_dir=str(out_dir),
    )
    assert result["iso_area"] is True, (
        f"全落低区应 iso_area=True，实得 {result['iso_area']}"
    )


def test_L8_iso_area_false(tmp_path):
    """全部 LGG 切片 area_ratio 落高区 -> iso_area=False。"""
    high_val = BRATS_P25_AREA_RATIO_FULL * 5  # 远高于 P25
    rows = [
        {"area_ratio_full": high_val, "n_components": 2}
        for _ in range(100)
    ]

    brats_ncomp_csv = _make_brats_ncomp_csv(tmp_path, [1, 2, 3] * 100)
    brats_area_csv  = _make_brats_area_full_csv(tmp_path, [0.02, 0.03, 0.04] * 100)
    out_dir = tmp_path / "phase1_out"

    result = compute_g1a_iso(
        rows=rows,
        brats_ncomp_csv=str(brats_ncomp_csv),
        brats_area_full_csv=str(brats_area_csv),
        out_dir=str(out_dir),
    )
    assert result["iso_area"] is False, (
        f"全落高区应 iso_area=False，实得 {result['iso_area']}"
    )


# ============================================================
# L9: compute_g1a_iso iso_ncomp 门
# ============================================================

def test_L9_iso_ncomp_true(tmp_path):
    """全部 LGG n_components = 1（<= BRATS_P75=3）-> iso_ncomp=True。"""
    rows = [
        {"area_ratio_full": 0.05, "n_components": 1}
        for _ in range(100)
    ]
    brats_ncomp_csv = _make_brats_ncomp_csv(tmp_path, [1, 2, 1, 3, 2] * 40)
    brats_area_csv  = _make_brats_area_full_csv(tmp_path, [0.02, 0.04] * 100)
    out_dir = tmp_path / "phase1_out"

    result = compute_g1a_iso(rows=rows,
                              brats_ncomp_csv=str(brats_ncomp_csv),
                              brats_area_full_csv=str(brats_area_csv),
                              out_dir=str(out_dir))
    assert result["iso_ncomp"] is True, (
        f"n_comp=1 全落 <=3 应 iso_ncomp=True，实得 {result['iso_ncomp']}"
    )


def test_L9_iso_ncomp_false(tmp_path):
    """全部 LGG n_components = 100（> BRATS_P75=3）-> iso_ncomp=False。"""
    rows = [
        {"area_ratio_full": 0.05, "n_components": 100}
        for _ in range(100)
    ]
    brats_ncomp_csv = _make_brats_ncomp_csv(tmp_path, [1, 2, 1, 3, 2] * 40)
    brats_area_csv  = _make_brats_area_full_csv(tmp_path, [0.02, 0.04] * 100)
    out_dir = tmp_path / "phase1_out"

    result = compute_g1a_iso(rows=rows,
                              brats_ncomp_csv=str(brats_ncomp_csv),
                              brats_area_full_csv=str(brats_area_csv),
                              out_dir=str(out_dir))
    assert result["iso_ncomp"] is False, (
        f"n_comp=100 全落 >3 应 iso_ncomp=False，实得 {result['iso_ncomp']}"
    )


# ============================================================
# L10: iso = iso_area AND iso_ncomp
# ============================================================

def test_L10_iso_requires_both_gates(tmp_path):
    """iso = True 需两维都过；任一 False 则 iso=False。"""
    brats_ncomp_csv = _make_brats_ncomp_csv(tmp_path, [1, 2, 3] * 100)
    brats_area_csv  = _make_brats_area_full_csv(tmp_path, [0.02, 0.03, 0.04] * 100)
    out_dir = tmp_path / "phase1_out"

    low_val  = BRATS_P25_AREA_RATIO_FULL * 0.5   # 落低区
    high_val = BRATS_P25_AREA_RATIO_FULL * 5      # 落高区

    # Case A: area ok, ncomp 全 >3 -> iso=False
    rows_a = [{"area_ratio_full": low_val,  "n_components": 100} for _ in range(100)]
    r_a = compute_g1a_iso(rows_a, str(brats_ncomp_csv), str(brats_area_csv), str(out_dir))
    assert r_a["iso"] is False, "area ok + ncomp fail -> iso 应 False"

    # Case B: ncomp ok, area 全高 -> iso=False
    rows_b = [{"area_ratio_full": high_val, "n_components": 1} for _ in range(100)]
    r_b = compute_g1a_iso(rows_b, str(brats_ncomp_csv), str(brats_area_csv), str(out_dir))
    assert r_b["iso"] is False, "area fail + ncomp ok -> iso 应 False"

    # Case C: 两维都过 -> iso=True
    rows_c = [{"area_ratio_full": low_val,  "n_components": 1} for _ in range(100)]
    r_c = compute_g1a_iso(rows_c, str(brats_ncomp_csv), str(brats_area_csv), str(out_dir))
    assert r_c["iso"] is True, "两维都过 -> iso 应 True"


# ============================================================
# L11: 口径不动 Phase 0 — distribution_overlap 常量未被改
# ============================================================

def test_L11_phase0_constants_unchanged():
    """import lesion_features_lgg 不改变 distribution_overlap 的 bin 常量。"""
    import distribution_overlap as do_mod
    # 口径常量（Phase 0 冻结，不得被动变）
    assert do_mod.BIN_SCHEME_AREA_RATIO == "linear_100_[0,1]", (
        f"area_ratio bin scheme 被改动: {do_mod.BIN_SCHEME_AREA_RATIO}"
    )
    assert do_mod.BIN_SCHEME_NCOMP == "log50_[0.5,3000]", (
        f"n_components bin scheme 被改动: {do_mod.BIN_SCHEME_NCOMP}"
    )
    assert do_mod.N_BINS_AREA_RATIO == 100
    assert do_mod.N_BINS_NCOMP == 50
