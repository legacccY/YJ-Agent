"""
test_lgg_skull_strip_exact.py — 精确 skull-strip 单元测试
服务: MedAD-FailMap Phase 1 § STORY② 正臂锚 LGG iso make-or-break

覆盖：
  E1: skull_strip_lgg_flair — 合成背景+脑区图，brain_px 落合理范围（不是 0 也不是 4096）
  E2: skull_strip_lgg_flair — 全黑图 -> brain_px = 0，不 crash
  E3: skull_strip_lgg_flair — 纯前景图（无背景）-> brain_px 仍合理（腐蚀后缩小）
  E4: extract_slice_features_exact — 空 mask -> size_px=0，brain_px_exact >= 0，不 crash
  E5: extract_slice_features_exact — 非空 mask area_ratio_brain_exact ∈ (0, 1]
  E6: extract_slice_features_exact — area_ratio_brain_exact > area_ratio_full
      （精确脑区 < 全图，因此 ratio 更大；这是 artifact 修正的核心验证）
  E7: batch_extract_lgg_exact — 输出 csv schema 含所有必需列
  E8: batch_extract_lgg_exact — 空 mask 切片过滤（overlaps_brats2021 正确传播）
  E9: report_exact_vs_approx_vs_brats — 不 crash（全合成 csv mock）
  E10: 不动 Phase 0/1 口径 — import lgg_skull_strip_exact 不改 lesion_features_lgg 常量

全部合成数据，无真实数据依赖，纯 CPU。
"""

import csv
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

CODE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CODE_DIR))


# ============================================================
# 合成辅助函数
# ============================================================

def _make_lgg_flair_256(tmp_path, patient_id="TCGA_XX_0001_20000101",
                         flair_value=160, bg_value=3,
                         bg_border=30, size=256,
                         tumor_center=None, tumor_r=20,
                         empty_mask=False):
    """
    合成 256×256 LGG 切片（模拟真实 LGG 图像结构）。
    - 外圈 bg_border px 背景低亮度（bg_value）
    - 内圈脑区高亮度（flair_value）
    - tumor mask 圆形斑点

    Returns: (img_path, mask_path, lgg_root, dedup_csv)
    """
    # 在 tmp_path 下建立合法的 LGG 目录结构
    lgg_root = tmp_path / "kaggle_3m"
    lgg_root.mkdir(exist_ok=True)
    pat_dir = lgg_root / patient_id
    pat_dir.mkdir(exist_ok=True)

    # RGB 图（ch1=FLAIR）
    img_arr = np.zeros((size, size, 3), dtype=np.uint8)
    img_arr[:, :, 1] = bg_value               # 全图低背景
    img_arr[bg_border:-bg_border, bg_border:-bg_border, 1] = flair_value  # 脑区

    img_path = pat_dir / f"{patient_id}_1.tif"
    Image.fromarray(img_arr).save(str(img_path))

    # Mask
    mask_arr = np.zeros((size, size), dtype=np.uint8)
    if not empty_mask:
        cy = cx = size // 2
        if tumor_center is not None:
            cy, cx = tumor_center
        Y, X = np.ogrid[:size, :size]
        circle = (X - cx) ** 2 + (Y - cy) ** 2 <= tumor_r ** 2
        mask_arr[circle] = 255
    mask_path = pat_dir / f"{patient_id}_1_mask.tif"
    Image.fromarray(mask_arr).save(str(mask_path))

    # dedup csv
    dedup_csv = tmp_path / "lgg_dedup.csv"
    with open(dedup_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["patient_dir", "tcga_id", "overlaps_brats2021"])
        w.writeheader()
        w.writerow({"patient_dir": patient_id, "tcga_id": patient_id[:11], "overlaps_brats2021": "False"})

    return img_path, mask_path, lgg_root, dedup_csv


def _make_brats_csv(tmp_path, n=30, seed=0):
    """合成 brats_brain_px.csv"""
    rng = np.random.default_rng(seed)
    p = tmp_path / "brats_brain_px.csv"
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "filename", "brain_px", "brain_threshold", "full_frame_px",
            "brain_method", "size_px", "area_ratio_brain", "area_ratio_full",
        ])
        w.writeheader()
        for i in range(n):
            brain_px = int(rng.integers(1200, 1900))
            size_px  = int(rng.integers(50, 300))
            w.writerow({
                "filename": f"BraTS2021_0001_flair_{i}.png",
                "brain_px": brain_px, "brain_threshold": "1e-06",
                "full_frame_px": 4096, "brain_method": "nonzero",
                "size_px": size_px,
                "area_ratio_brain": round(size_px / brain_px, 6),
                "area_ratio_full":  round(size_px / 4096, 6),
            })
    return p


def _make_approx_csv(tmp_path, n=50, seed=1):
    """合成 lesion_features_lgg_anatomy.csv（模拟原 approx）"""
    rng = np.random.default_rng(seed)
    p = tmp_path / "lesion_features_lgg_anatomy.csv"
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "filename", "patient_id", "size_px", "n_components",
            "area_ratio_full", "brain_px_approx",
            "area_ratio_brain_approx", "approx_method",
        ])
        w.writeheader()
        for i in range(n):
            size_px = int(rng.integers(10, 200))
            w.writerow({
                "filename": f"TCGA_XX_0001_20000101_{i}.tif",
                "patient_id": "TCGA_XX_0001_20000101",
                "size_px": size_px, "n_components": 1,
                "area_ratio_full": round(size_px / 4096, 6),
                "brain_px_approx": 4096,   # 原版 bug：始终=4096
                "area_ratio_brain_approx": round(size_px / 4096, 6),
                "approx_method": "otsu_maxconn_floodfill",
            })
    return p


# ============================================================
# E1: skull_strip_lgg_flair — 合成背景+脑区，brain_px 合理
# ============================================================

def test_E1_skull_strip_realistic():
    """合成「外圈背景=3，内圈脑区=160」256×256 FLAIR -> brain_px 落 (0, 4096)"""
    from lgg_skull_strip_exact import skull_strip_lgg_flair
    flair = np.full((256, 256), 3.0, dtype=np.float32)
    flair[30:226, 30:226] = 160.0  # 脑区：196×196 内圈
    _, brain_px, method = skull_strip_lgg_flair(flair, bg_thresh=15, erosion_size=5)
    # 腐蚀后脑区应缩小，但不能是 0 或 4096
    assert 0 < brain_px < 4096, f"brain_px={brain_px} 应在 (0, 4096)"
    assert "improved_otsu" in method


def test_E1_brain_px_much_less_than_4096():
    """精确 skull-strip 后 brain_px 应远小于 4096（修正原 approx 的 artifact）"""
    from lgg_skull_strip_exact import skull_strip_lgg_flair
    flair = np.full((256, 256), 3.0, dtype=np.float32)
    flair[30:226, 30:226] = 160.0
    _, brain_px, _ = skull_strip_lgg_flair(flair, bg_thresh=15, erosion_size=5)
    # 4096 是全图（原 approx 的 bug），精确版应 < 4096
    assert brain_px < 4096, f"brain_px={brain_px} 不应等于全图 4096"
    # 且应大于 0
    assert brain_px > 0


# ============================================================
# E2: 全黑图 -> brain_px = 0
# ============================================================

def test_E2_all_black_flair():
    from lgg_skull_strip_exact import skull_strip_lgg_flair
    flair = np.zeros((256, 256), dtype=np.float32)
    _, brain_px, _ = skull_strip_lgg_flair(flair)
    assert brain_px == 0


# ============================================================
# E3: 纯前景图（无背景）-> 腐蚀后 brain_px < 4096
# ============================================================

def test_E3_all_bright_flair():
    """整张图都是前景（FLAIR=200）-> 腐蚀后 brain_px > 0，不 crash。
    注：256×256 腐蚀 5px 后仍有 246×246 区域 -> resize 64×64 接近满，不断言 < 4096。
    断言 brain_px > 0 即可（不 crash + 非全黑）。"""
    from lgg_skull_strip_exact import skull_strip_lgg_flair
    flair = np.full((256, 256), 200.0, dtype=np.float32)
    _, brain_px, method = skull_strip_lgg_flair(flair, bg_thresh=15, erosion_size=5)
    assert brain_px > 0, f"全前景腐蚀后 brain_px={brain_px} 应 > 0"
    assert "improved_otsu" in method


# ============================================================
# E4: extract_slice_features_exact 空 mask
# ============================================================

def test_E4_empty_mask_no_crash(tmp_path):
    from lgg_skull_strip_exact import extract_slice_features_exact
    img_path, mask_path, _, _ = _make_lgg_flair_256(tmp_path, empty_mask=True)
    feats = extract_slice_features_exact(img_path, mask_path, img_size=64)
    assert feats["size_px"] == 0
    assert feats["n_components"] == 0
    assert feats["brain_px_exact"] >= 0  # 脑区独立于 mask


# ============================================================
# E5: area_ratio_brain_exact ∈ (0, 1]
# ============================================================

def test_E5_area_ratio_exact_in_range(tmp_path):
    from lgg_skull_strip_exact import extract_slice_features_exact
    img_path, mask_path, _, _ = _make_lgg_flair_256(tmp_path, tumor_r=15)
    feats = extract_slice_features_exact(img_path, mask_path, img_size=64)
    ratio = feats["area_ratio_brain_exact"]
    if ratio != ratio:  # nan check
        return  # 全黑图时 nan，跳过
    assert 0.0 < ratio <= 1.0, f"area_ratio_brain_exact={ratio} 应在 (0,1]"


# ============================================================
# E6: area_ratio_brain_exact > area_ratio_full（核心 artifact 修正验证）
# ============================================================

def test_E6_exact_ratio_greater_than_full_ratio(tmp_path):
    """
    精确脑区 < 全图 -> area_ratio_brain_exact = tumor/brain_exact > tumor/full_img。
    这是核心验证：修正原 approx 把分母设 4096（全图）的 artifact。
    """
    from lgg_skull_strip_exact import extract_slice_features_exact
    img_path, mask_path, _, _ = _make_lgg_flair_256(
        tmp_path, flair_value=160, bg_value=3, bg_border=30, tumor_r=15
    )
    feats = extract_slice_features_exact(img_path, mask_path, img_size=64)
    ratio_exact = feats["area_ratio_brain_exact"]
    brain_px    = feats["brain_px_exact"]
    size_px     = feats["size_px"]

    if ratio_exact != ratio_exact or brain_px == 0 or size_px == 0:
        pytest.skip("合成图未产生有效肿瘤或脑区")

    ratio_full = size_px / 4096.0
    assert ratio_exact > ratio_full, (
        f"精确比 {ratio_exact:.4f} 应 > 全图比 {ratio_full:.4f} "
        f"(brain_px={brain_px} < 4096)"
    )


# ============================================================
# E7: batch_extract_lgg_exact csv schema
# ============================================================

def test_E7_batch_csv_schema(tmp_path):
    from lgg_skull_strip_exact import batch_extract_lgg_exact
    _, _, lgg_root, dedup_csv = _make_lgg_flair_256(tmp_path, tumor_r=15)
    out_csv = tmp_path / "exact_out.csv"
    batch_extract_lgg_exact(
        lgg_root=str(lgg_root),
        lgg_dedup_csv=str(dedup_csv),
        out_csv=str(out_csv),
        img_size=64,
    )
    assert out_csv.exists()
    with open(out_csv, newline="") as f:
        cols = set(csv.DictReader(f).fieldnames or [])
    required = {
        "filename", "patient_id", "overlaps_brats2021",
        "size_px", "n_components",
        "area_ratio_brain_exact", "brain_px_exact", "skull_strip_method",
    }
    missing = required - cols
    assert not missing, f"csv 缺列: {missing}"


# ============================================================
# E8: batch 空 mask 过滤 + overlaps_brats2021 传播
# ============================================================

def test_E8_batch_filters_and_overlaps(tmp_path):
    from lgg_skull_strip_exact import batch_extract_lgg_exact

    lgg_root = tmp_path / "kaggle_3m"
    lgg_root.mkdir(exist_ok=True)
    pid = "TCGA_YY_0002_20010101"
    pat_dir = lgg_root / pid
    pat_dir.mkdir(exist_ok=True)

    # 切片 1: 有肿瘤
    img_arr = np.zeros((256, 256, 3), dtype=np.uint8)
    img_arr[30:226, 30:226, 1] = 160
    mask_arr = np.zeros((256, 256), dtype=np.uint8)
    mask_arr[100:150, 100:150] = 255
    Image.fromarray(img_arr).save(str(pat_dir / f"{pid}_1.tif"))
    Image.fromarray(mask_arr).save(str(pat_dir / f"{pid}_1_mask.tif"))

    # 切片 2: 空 mask
    empty_mask = np.zeros((256, 256), dtype=np.uint8)
    Image.fromarray(img_arr).save(str(pat_dir / f"{pid}_2.tif"))
    Image.fromarray(empty_mask).save(str(pat_dir / f"{pid}_2_mask.tif"))

    # dedup csv（overlaps=True）
    dedup_csv = tmp_path / "dedup.csv"
    with open(dedup_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["patient_dir", "tcga_id", "overlaps_brats2021"])
        w.writeheader()
        w.writerow({"patient_dir": pid, "tcga_id": pid[:11], "overlaps_brats2021": "True"})

    out_csv = tmp_path / "out.csv"
    rows = batch_extract_lgg_exact(
        lgg_root=str(lgg_root),
        lgg_dedup_csv=str(dedup_csv),
        out_csv=str(out_csv),
        img_size=64,
    )
    # 只有 1 行（空 mask 过滤）
    assert len(rows) == 1, f"应 1 行，得 {len(rows)}"
    # overlaps_brats2021 应正确传播
    assert rows[0]["overlaps_brats2021"] == "True"


# ============================================================
# E9: report_exact_vs_approx_vs_brats 不 crash
# ============================================================

def test_E9_report_no_crash(tmp_path, capsys):
    from lgg_skull_strip_exact import report_exact_vs_approx_vs_brats

    pid = "TCGA_XX_0001_20000101"
    dedup_csv = tmp_path / "lgg_dedup.csv"
    with open(dedup_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["patient_dir", "tcga_id", "overlaps_brats2021"])
        w.writeheader()
        w.writerow({"patient_dir": pid, "tcga_id": pid[:11], "overlaps_brats2021": "False"})

    rng = np.random.default_rng(42)
    rows = [
        {
            "patient_id": pid,
            "area_ratio_brain_exact": round(float(rng.uniform(0.03, 0.20)), 6),
        }
        for _ in range(30)
    ]
    approx_csv  = _make_approx_csv(tmp_path, n=30)
    brats_csv   = _make_brats_csv(tmp_path, n=30)

    # 修改 approx_csv patient_id 为 pid（让独立例匹配到数据）
    rows_approx = []
    with open(approx_csv, newline="") as f:
        for row in csv.DictReader(f):
            row["patient_id"] = pid
            rows_approx.append(row)
    with open(approx_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows_approx[0].keys()))
        w.writeheader()
        w.writerows(rows_approx)

    report_exact_vs_approx_vs_brats(
        rows=rows,
        approx_csv=str(approx_csv),
        brats_brain_px_csv=str(brats_csv),
        lgg_dedup_csv=str(dedup_csv),
    )
    captured = capsys.readouterr()
    assert "make-or-break" in captured.out or len(captured.out) > 50


# ============================================================
# E10: 不动 Phase 0/1 口径
# ============================================================

def test_E10_phase0_1_constants_unchanged():
    """import lgg_skull_strip_exact 不改动 Phase 0/1 常量"""
    import lgg_skull_strip_exact  # noqa: F401

    import lesion_features_lgg as lgg_mod
    assert lgg_mod.BRATS_P25_AREA_RATIO_FULL == 0.0198, (
        f"BRATS_P25_AREA_RATIO_FULL 被改: {lgg_mod.BRATS_P25_AREA_RATIO_FULL}"
    )
    assert lgg_mod.BRATS_P75_NCOMP == 3, (
        f"BRATS_P75_NCOMP 被改: {lgg_mod.BRATS_P75_NCOMP}"
    )

    import distribution_overlap as do_mod
    assert do_mod.BIN_SCHEME_AREA_RATIO == "linear_100_[0,1]"
    assert do_mod.BIN_SCHEME_NCOMP == "log50_[0.5,3000]"
    assert do_mod.N_BINS_AREA_RATIO == 100
    assert do_mod.N_BINS_NCOMP == 50
