"""
test_phase1_lgg_facts.py — Phase 1 LGG 事实补全单元测试
服务: MedAD-FailMap Phase 1 § STORY② 正臂锚事实核实（skeptic 前置实证）

覆盖:
  D1: lgg_anatomy._otsu_threshold_numpy — 阈值落在 [0, 1]
  D2: lgg_anatomy._approx_brain_mask — 脑区 mask 非零、brain_px 在 [1, 64*64]
  D3: lgg_anatomy.extract_slice_features_anatomy — 空 mask -> size_px=0, brain_px_approx >= 0
  D4: lgg_anatomy.extract_slice_features_anatomy — 非空 mask area_ratio_brain_approx ∈ (0, 1]
  D5: lgg_anatomy.extract_slice_features_anatomy — area_ratio_full 与 lesion_features_lgg 口径一致
  D6: lgg_anatomy.batch_extract_lgg_anatomy — 输出 csv schema 含所有必需列
  D7: lgg_anatomy.batch_extract_lgg_anatomy — 空 mask 切片过滤掉
  D8: lgg_anatomy.report_quantile_comparison — 不 crash（BraTS csv mock）
  D9: 去重逻辑 normalize — TCGA_CS_4942_19970222 -> TCGA-CS-4942
  D10: 不动 Phase 0/1 既有口径 — lesion_features_lgg 常量未被 import 改变

全部合成数据，无真实数据依赖，纯 CPU，几秒内跑完。
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
# Fixture helpers
# ============================================================

def _make_lgg_anatomy_slice(tmp_path, patient_id="TCGA_XX_0001_20000101",
                             size=64, tumor_box=None, empty_mask=False):
    """
    合成单张 LGG 切片（RGB tif + mask tif），用于 lgg_anatomy 测试。
    tumor_box: (r0, c0, r1, c1) 前景区域；None = 中心 20x20
    """
    pat_dir = tmp_path / patient_id
    pat_dir.mkdir(parents=True, exist_ok=True)

    # RGB 图：ch0=pre（低），ch1=FLAIR（高），ch2=post（中）
    img_arr = np.zeros((size, size, 3), dtype=np.uint8)
    img_arr[:, :, 0] = 30   # pre: 低灰度
    img_arr[:, :, 1] = 180  # FLAIR: 高灰度（脑组织区域有信号）
    img_arr[:, :, 2] = 80   # post: 中灰度
    # 模拟脑内外：外圈(8px)背景为 0
    img_arr[:8, :, :] = 0
    img_arr[-8:, :, :] = 0
    img_arr[:, :8, :] = 0
    img_arr[:, -8:, :] = 0

    img_path = pat_dir / f"{patient_id}_1.tif"
    Image.fromarray(img_arr).save(str(img_path))

    mask_arr = np.zeros((size, size), dtype=np.uint8)
    if not empty_mask:
        if tumor_box is None:
            r0, c0, r1, c1 = size//4, size//4, size*3//4, size*3//4
        else:
            r0, c0, r1, c1 = tumor_box
        mask_arr[r0:r1, c0:c1] = 255

    mask_path = pat_dir / f"{patient_id}_1_mask.tif"
    Image.fromarray(mask_arr).save(str(mask_path))

    return img_path, mask_path


def _make_brats_brain_px_csv(tmp_path, n=20, seed=0):
    """合成 brats_brain_px.csv（含 area_ratio_brain 列）"""
    rng = np.random.default_rng(seed)
    p = tmp_path / "brats_brain_px.csv"
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "filename", "brain_px", "brain_threshold", "full_frame_px",
            "brain_method", "size_px", "area_ratio_brain", "area_ratio_full",
        ])
        w.writeheader()
        for i in range(n):
            brain_px = int(rng.integers(800, 2000))
            size_px  = int(rng.integers(10, brain_px))
            w.writerow({
                "filename":        f"BraTS2021_0001_flair_{i}.png",
                "brain_px":        brain_px,
                "brain_threshold": "1e-06",
                "full_frame_px":   4096,
                "brain_method":    "nonzero",
                "size_px":         size_px,
                "area_ratio_brain": round(size_px / brain_px, 6),
                "area_ratio_full":  round(size_px / 4096, 6),
            })
    return p


# ============================================================
# D1: _otsu_threshold_numpy 阈值在 [0, 1]
# ============================================================

def test_D1_otsu_range():
    from lgg_anatomy import _otsu_threshold_numpy
    rng = np.random.default_rng(42)
    arr = rng.random((64, 64)).astype(np.float32)
    t = _otsu_threshold_numpy(arr)
    assert 0.0 <= t <= 1.0, f"Otsu 阈值应在 [0,1]，得 {t}"


def test_D1_otsu_bimodal():
    """双峰分布 Otsu 应落在两峰之间"""
    from lgg_anatomy import _otsu_threshold_numpy
    rng = np.random.default_rng(7)
    low  = rng.random(512) * 0.3         # 峰 1: 0~0.3
    high = rng.random(512) * 0.3 + 0.7  # 峰 2: 0.7~1.0
    arr  = np.concatenate([low, high]).reshape(32, 32).astype(np.float32)
    t = _otsu_threshold_numpy(arr)
    # 两峰 0~0.3 和 0.7~1.0，阈值应落在 [0.25, 0.75] 之间（numpy Otsu 离散精度可能稍偏）
    assert 0.25 < t < 0.75, f"双峰 Otsu 应在 0.25~0.75 之间，得 {t}"


# ============================================================
# D2: _approx_brain_mask 返回有效 mask
# ============================================================

def test_D2_approx_brain_mask_valid():
    from lgg_anatomy import _approx_brain_mask
    rng = np.random.default_rng(0)
    # 合成 FLAIR：中心区域有信号，外围黑
    flair = np.zeros((64, 64), dtype=np.float32)
    flair[10:54, 10:54] = rng.random((44, 44)).astype(np.float32) * 200.0 + 30.0
    brain_mask, brain_px, method = _approx_brain_mask(flair)
    assert brain_mask.shape == (64, 64)
    assert 1 <= brain_px <= 64 * 64, f"brain_px={brain_px} 应在 [1, 4096]"
    assert method == "otsu_maxconn_floodfill"


def test_D2_approx_brain_mask_all_black():
    """全黑 FLAIR -> brain_px = 0，不 crash"""
    from lgg_anatomy import _approx_brain_mask
    flair = np.zeros((64, 64), dtype=np.float32)
    _, brain_px, _ = _approx_brain_mask(flair)
    assert brain_px == 0


# ============================================================
# D3: extract_slice_features_anatomy 空 mask
# ============================================================

def test_D3_empty_mask_no_crash(tmp_path):
    from lgg_anatomy import extract_slice_features_anatomy
    img_p, mask_p = _make_lgg_anatomy_slice(tmp_path, empty_mask=True)
    feats = extract_slice_features_anatomy(img_p, mask_p, img_size=64)
    assert feats["size_px"] == 0
    assert feats["n_components"] == 0
    assert feats["area_ratio_full"] == 0.0
    # brain_px_approx 仍应计算（脑区不依赖 mask）
    assert feats["brain_px_approx"] >= 0


# ============================================================
# D4: 非空 mask area_ratio_brain_approx ∈ (0, 1]
# ============================================================

def test_D4_area_ratio_brain_in_range(tmp_path):
    from lgg_anatomy import extract_slice_features_anatomy
    img_p, mask_p = _make_lgg_anatomy_slice(tmp_path)  # 默认中心 tumor
    feats = extract_slice_features_anatomy(img_p, mask_p, img_size=64)
    ratio = feats["area_ratio_brain_approx"]
    if not np.isnan(ratio):
        assert 0.0 < ratio <= 1.0, f"area_ratio_brain_approx={ratio} 应在 (0,1]"


# ============================================================
# D5: area_ratio_full 与 lesion_features_lgg 口径一致
# ============================================================

def test_D5_area_ratio_full_formula(tmp_path):
    """area_ratio_full = size_px / 64²（与 lesion_features_lgg 同口径）"""
    from lgg_anatomy import extract_slice_features_anatomy
    img_p, mask_p = _make_lgg_anatomy_slice(tmp_path)
    feats = extract_slice_features_anatomy(img_p, mask_p, img_size=64)
    expected = feats["size_px"] / (64.0 * 64.0)
    assert abs(feats["area_ratio_full"] - expected) < 1e-5, (
        f"area_ratio_full={feats['area_ratio_full']}, expected={expected:.6f}"
    )


# ============================================================
# D6: batch_extract_lgg_anatomy csv schema
# ============================================================

def test_D6_batch_csv_schema(tmp_path):
    lgg_root = tmp_path / "kaggle_3m"
    lgg_root.mkdir()
    _make_lgg_anatomy_slice(tmp_path=lgg_root, patient_id="TCGA_A_0001_20000101", size=64)

    from lgg_anatomy import batch_extract_lgg_anatomy
    out_csv = tmp_path / "out" / "anatomy.csv"
    batch_extract_lgg_anatomy(lgg_root=str(lgg_root), out_csv=str(out_csv), img_size=64)

    assert out_csv.exists()
    with open(out_csv, newline="") as f:
        reader = csv.DictReader(f)
        cols = set(reader.fieldnames or [])

    required = {
        "filename", "patient_id", "size_px", "n_components",
        "area_ratio_full", "brain_px_approx",
        "area_ratio_brain_approx", "approx_method",
    }
    missing = required - cols
    assert not missing, f"csv 缺列: {missing}"


# ============================================================
# D7: batch_extract_lgg_anatomy 过滤空 mask
# ============================================================

def test_D7_batch_filters_empty_masks(tmp_path):
    lgg_root = tmp_path / "kaggle_3m"
    lgg_root.mkdir()
    pat_dir = lgg_root / "TCGA_A_0001_20000101"
    pat_dir.mkdir()

    # 有 tumor 切片
    img_arr  = np.zeros((64, 64, 3), dtype=np.uint8)
    img_arr[:, :, 1] = 150  # ch1 FLAIR
    mask_arr = np.zeros((64, 64), dtype=np.uint8)
    mask_arr[20:40, 20:40] = 255
    Image.fromarray(img_arr).save(str(pat_dir / "TCGA_A_0001_20000101_1.tif"))
    Image.fromarray(mask_arr).save(str(pat_dir / "TCGA_A_0001_20000101_1_mask.tif"))

    # 空 mask 切片
    empty_mask = np.zeros((64, 64), dtype=np.uint8)
    Image.fromarray(img_arr).save(str(pat_dir / "TCGA_A_0001_20000101_2.tif"))
    Image.fromarray(empty_mask).save(str(pat_dir / "TCGA_A_0001_20000101_2_mask.tif"))

    from lgg_anatomy import batch_extract_lgg_anatomy
    out_csv = tmp_path / "out_filter.csv"
    rows = batch_extract_lgg_anatomy(lgg_root=str(lgg_root), out_csv=str(out_csv), img_size=64)

    assert len(rows) == 1, f"应只有 1 行（过滤空 mask），得 {len(rows)}"


# ============================================================
# D8: report_quantile_comparison 不 crash
# ============================================================

def test_D8_report_no_crash(tmp_path, capsys):
    from lgg_anatomy import report_quantile_comparison
    # 合成 lgg rows
    rng = np.random.default_rng(5)
    lgg_rows = [
        {"area_ratio_brain_approx": round(float(rng.random() * 0.1), 6)}
        for _ in range(20)
    ]
    brats_csv = _make_brats_brain_px_csv(tmp_path, n=30)
    report_quantile_comparison(lgg_rows, str(brats_csv))
    captured = capsys.readouterr()
    assert "P25" in captured.out or "P25" in captured.err or len(captured.out) > 0


# ============================================================
# D9: 去重 normalize 逻辑
# ============================================================

def test_D9_normalize_patient_id():
    """TCGA_CS_4942_19970222 -> TCGA-CS-4942（前三段 join）"""
    def normalize(name):
        parts = name.split("_")
        return "-".join(parts[:3])

    assert normalize("TCGA_CS_4942_19970222") == "TCGA-CS-4942"
    assert normalize("TCGA_DU_7013_19860523") == "TCGA-DU-7013"
    assert normalize("TCGA_HT_A616_19991226") == "TCGA-HT-A616"
    # 中间 ID 含字母数字混合（如 A616）也正常处理
    assert normalize("TCGA_FG_A4MU_20030903") == "TCGA-FG-A4MU"


def test_D9_dedup_join():
    """集合 join：brats_ids 已知 -> 正确区分 overlap/independent"""
    def normalize(name):
        return "-".join(name.split("_")[:3])

    brats_ids = {"TCGA-CS-4942", "TCGA-CS-4944", "TCGA-DU-5849"}
    local_dirs = [
        "TCGA_CS_4942_19970222",   # overlap
        "TCGA_CS_4944_20010208",   # overlap
        "TCGA_DU_5849_19950405",   # overlap
        "TCGA_FG_5962_20000626",   # independent
        "TCGA_HT_A616_19991226",   # independent
    ]
    overlap = [d for d in local_dirs if normalize(d) in brats_ids]
    indep   = [d for d in local_dirs if normalize(d) not in brats_ids]

    assert len(overlap) == 3
    assert len(indep) == 2
    assert "TCGA_FG_5962_20000626" in indep
    assert "TCGA_HT_A616_19991226" in indep


# ============================================================
# D10: 不动 Phase 0/1 既有口径
# ============================================================

def test_D10_existing_constants_unchanged():
    """import lgg_anatomy 不改动 lesion_features_lgg 及 distribution_overlap 常量"""
    import lgg_anatomy  # noqa: F401

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
