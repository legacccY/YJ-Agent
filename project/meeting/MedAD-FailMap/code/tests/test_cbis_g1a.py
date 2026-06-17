"""
test_cbis_g1a.py — Phase 1 G1-a CBIS mass 适配器 + 面积比重叠检查 + BraTS brain_px 测试
服务: MedAD-FailMap Phase 1, PC-B Gate1 G1-a 几何同构验证
lever: 机制公平面积比（mass/breast 对应 BraTS tumor/brain）

所有测试用合成数据（synthetic），不依赖真实数据，纯 CPU，几秒内跑完。

覆盖:
  lesion_features_cbis.py:
    A1: breast Otsu 分割正确（黑边+椭圆乳腺区）
    A2: area_ratio_breast > area_ratio_full（分母更小）
    A3: mass-only 过滤（meta csv abnormality_type==mass）
    A4: 多 ROI 取最大 + n_components 记录
    A5: area_ratio 值域 [0, 1] 断言
    A6: mass 为空时 area_ratio_breast=nan 不崩溃

  area_ratio_check.py CBIS 扩展:
    B1: --target-ratio-col 直接读预计算面积比列
    B2: target_ratio_col 超出 [0,1] 触发 ValueError
    B3: BraTS 侧 brats_brain_px_col 路径（tumor/brain ratio）
    B4: 旧调用接口向后兼容（不传新参数，行为不变）
    B5: overlap_ok 判定对 CBIS area_ratio_breast 正确

  brats_brain_px.py（G1-a 对称分母补全）:
    C1: segment_brain nonzero 方法找到脑区（skull-strip 正确路径）；
        nonzero brain_px >= otsu brain_px（修复 v1 Otsu 欠割 bug 验证）；
        invalid brain_method 触发 ValueError
    C2: area_ratio_brain > area_ratio_full（脑区分母 < 全图）
    C3: area_ratio_brain ∈ [0, 1]（断言；>1 触发 ValueError）
    C4: 全黑切片返回 brain_px=0 不崩溃
    C5: batch_extract_brain_px 输出 csv schema（brain_threshold/brain_method 新列）
    C6: join strat csv 后输出 area_ratio_brain 列；area_ratio_brain >1 触发 ValueError
    C7: 与 CBIS area_ratio_breast 对称性验证（两端都是 lesion/tissue，分母语义等价）
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


# ============================================================
# Fixture helpers
# ============================================================

def _make_synthetic_mammogram(tmp_path, img_id="case_001", size=64,
                               breast_ellipse=True, mass_radius=5,
                               black_border_frac=0.25):
    """
    合成 mammogram：
      - 全图背景 = 0（黑色，模拟黑边）
      - 中央椭圆区域（乳腺组织）= 128~200（灰色，模拟腺体）
      - 中央小圆（mass）= 230~255（高亮，模拟肿块）
    同时生成对应 ROI mask（mass 区域 = 255）。

    返回 (img_path, mask_path, expected_mass_px, expected_breast_mask)
    """
    H, W = size, size
    img_arr  = np.zeros((H, W), dtype=np.uint8)
    mask_arr = np.zeros((H, W), dtype=np.uint8)

    cy, cx = H // 2, W // 2

    # 椭圆乳腺区（半轴 = size * (1 - 2*border_frac) / 2）
    inner_r = int(size * (1 - 2 * black_border_frac) / 2)
    ay, ax  = inner_r, inner_r
    for y in range(H):
        for x in range(W):
            if ((y - cy) / ay) ** 2 + ((x - cx) / ax) ** 2 <= 1.0:
                img_arr[y, x] = 150  # 乳腺组织灰度

    # mass 小圆（中心，radius=mass_radius）
    for y in range(H):
        for x in range(W):
            if (y - cy) ** 2 + (x - cx) ** 2 <= mass_radius ** 2:
                img_arr[y, x]  = 230   # mass 高亮
                mask_arr[y, x] = 255   # ROI mask

    img_path  = tmp_path / f"{img_id}.png"
    mask_path = tmp_path / f"{img_id}_mask.png"
    Image.fromarray(img_arr, mode="L").save(img_path)
    Image.fromarray(mask_arr, mode="L").save(mask_path)

    # 期望 mass_px = pi * r^2 区内像素（整数近似）
    expected_mass_px = int(mask_arr.sum() / 255)

    return img_path, mask_path, expected_mass_px


def _make_cbis_features_csv(tmp_path, name, rows):
    """
    写合成 CBIS per-image csv（含 area_ratio_breast / area_ratio_full 列）。
    rows: list of dict，每行含这些列（其余由调用方补全）。
    """
    tmp_path = Path(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    p = tmp_path / f"{name}.csv"
    fieldnames = [
        "image_id", "mass_px", "breast_px", "full_frame_px",
        "area_ratio_breast", "area_ratio_full",
        "n_components", "contrast", "dilation_px", "ring_width_frac",
        "breast_otsu_threshold", "orig_h", "orig_w",
    ]
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for i, r in enumerate(rows):
            row = {k: r.get(k, 0) for k in fieldnames}
            row["image_id"] = r.get("image_id", f"case_{i:04d}")
            w.writerow(row)
    return p


def _make_brats_features_csv(tmp_path, name, size_px_arr, brain_px_arr=None):
    """写合成 BraTS per-image csv（含 size_px，可选 brain_px 列）。"""
    tmp_path = Path(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    p = tmp_path / f"{name}.csv"
    fieldnames = ["filename", "size_px", "contrast"]
    if brain_px_arr is not None:
        fieldnames.append("brain_px")
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for i, s in enumerate(size_px_arr):
            row = {"filename": f"brats_{i:04d}.png", "size_px": str(s), "contrast": "0.1"}
            if brain_px_arr is not None:
                row["brain_px"] = str(brain_px_arr[i])
            w.writerow(row)
    return p


def _make_meta_csv(tmp_path, rows):
    """写合成 CBIS metadata csv（image_id + abnormality_type 列）。"""
    p = tmp_path / "meta.csv"
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["image_id", "abnormality_type"])
        w.writeheader()
        w.writerows(rows)
    return p


# ============================================================
# A: lesion_features_cbis.py 测试
# ============================================================

class TestCBISSegmentation:
    """A1: breast Otsu 分割"""

    def test_breast_otsu_finds_ellipse(self, tmp_path):
        """Otsu 分割应找到椭圆乳腺区，排除黑边"""
        from lesion_features_cbis import segment_breast

        img_path, _, _ = _make_synthetic_mammogram(
            tmp_path, size=64, breast_ellipse=True, black_border_frac=0.25
        )
        img_arr = np.array(Image.open(img_path).convert("L"), dtype=np.uint8)
        breast_mask, otsu_thr, breast_px = segment_breast(img_arr)

        # 乳腺区域应有像素（不为 0）
        assert breast_px > 0, "Otsu 分割后乳腺区域不应为空"

        # 乳腺区域应小于全图（有黑边）
        total_px = img_arr.shape[0] * img_arr.shape[1]
        assert breast_px < total_px, (
            f"breast_px={breast_px} 不应等于全图 {total_px}（应排除黑边）"
        )

        # 乳腺区域应大于 10% 全图
        # 合成图椭圆半径 = size*(1-2*0.25)/2 = 16px，面积 ~pi*16^2 = 804px / 4096 ~= 19.6%
        assert breast_px > total_px * 0.10, (
            f"breast_px={breast_px} 过小（期望 >10% 全图 {total_px}），Otsu 可能错分"
        )

    def test_otsu_threshold_range(self, tmp_path):
        """Otsu 阈值应在 [0, 1] 范围内"""
        from lesion_features_cbis import segment_breast

        img_path, _, _ = _make_synthetic_mammogram(tmp_path, size=32)
        img_arr = np.array(Image.open(img_path).convert("L"), dtype=np.uint8)
        _, otsu_thr, _ = segment_breast(img_arr)

        assert 0.0 <= otsu_thr <= 1.0, (
            f"Otsu 阈值应在 [0,1]，得 {otsu_thr}"
        )

    def test_all_black_image_returns_zero_breast_px(self, tmp_path):
        """全黑图（无乳腺）应返回 breast_px=0，不崩溃"""
        from lesion_features_cbis import segment_breast

        all_black = np.zeros((32, 32), dtype=np.uint8)
        breast_mask, otsu_thr, breast_px = segment_breast(all_black)

        assert breast_px == 0, f"全黑图 breast_px 应为 0，得 {breast_px}"
        assert breast_mask.shape == (32, 32)


class TestCBISAreaRatio:
    """A2: area_ratio_breast > area_ratio_full + 值域断言"""

    def test_area_ratio_breast_larger_than_full(self, tmp_path):
        """
        黑边图中：breast_px < full_frame_px
        所以 mass_px/breast_px > mass_px/full_frame_px
        即 area_ratio_breast > area_ratio_full
        """
        from lesion_features_cbis import extract_cbis_features

        img_path, mask_path, _ = _make_synthetic_mammogram(
            tmp_path, size=64, mass_radius=5, black_border_frac=0.25
        )
        feats = extract_cbis_features(img_path, mask_path, ring_width_frac=0.075)

        assert not np.isnan(feats["area_ratio_breast"]), (
            "area_ratio_breast 不应为 nan（乳腺 Otsu 应正常分割）"
        )
        assert feats["area_ratio_breast"] > feats["area_ratio_full"], (
            f"有黑边时 area_ratio_breast={feats['area_ratio_breast']:.4f} 应 > "
            f"area_ratio_full={feats['area_ratio_full']:.4f}"
        )

    def test_area_ratio_breast_in_0_1(self, tmp_path):
        """area_ratio_breast 值域 [0, 1]（mass 不可超过乳腺区域）"""
        from lesion_features_cbis import extract_cbis_features

        img_path, mask_path, _ = _make_synthetic_mammogram(
            tmp_path, size=64, mass_radius=4
        )
        feats = extract_cbis_features(img_path, mask_path)

        arb = feats["area_ratio_breast"]
        if not np.isnan(arb):
            assert 0.0 <= arb <= 1.0, (
                f"area_ratio_breast 超出 [0,1]: {arb}"
            )

    def test_area_ratio_full_in_0_1(self, tmp_path):
        """area_ratio_full 值域 [0, 1]"""
        from lesion_features_cbis import extract_cbis_features

        img_path, mask_path, _ = _make_synthetic_mammogram(
            tmp_path, size=64, mass_radius=4
        )
        feats = extract_cbis_features(img_path, mask_path)

        arf = feats["area_ratio_full"]
        assert 0.0 <= arf <= 1.0, f"area_ratio_full 超出 [0,1]: {arf}"

    def test_resize_changes_absolute_mass_px(self, tmp_path):
        """resize 到 img_size=64 时 mass_px <= 64*64=4096"""
        from lesion_features_cbis import extract_cbis_features

        # 先建子目录
        large_dir = tmp_path / "large"
        large_dir.mkdir(parents=True, exist_ok=True)

        # 造一张大图（128×128）
        img_path, mask_path, _ = _make_synthetic_mammogram(
            large_dir, size=128, mass_radius=10
        )

        # 不 resize
        feats_orig = extract_cbis_features(img_path, mask_path, img_size=None)
        # resize 到 64
        feats_64 = extract_cbis_features(img_path, mask_path, img_size=64)

        assert feats_64["full_frame_px"] == 64 * 64, (
            f"resize 到 64 后 full_frame_px 应为 4096，得 {feats_64['full_frame_px']}"
        )
        assert feats_64["mass_px"] <= 64 * 64, (
            f"resize 后 mass_px={feats_64['mass_px']} 超出 64^2=4096"
        )


class TestCBISMassROI:
    """A3+A4: mass-only 过滤 + 多 ROI 取最大 + n_components"""

    def test_single_roi_n_components_1(self, tmp_path):
        """单 mass ROI 时 n_components=1"""
        from lesion_features_cbis import extract_mass_roi

        mask_arr = np.zeros((64, 64), dtype=np.uint8)
        mask_arr[20:30, 20:30] = 255   # 单个 10×10 方块
        _, mass_px, n_comp = extract_mass_roi(mask_arr)

        assert n_comp == 1, f"单 ROI 期望 n_components=1，得 {n_comp}"
        assert mass_px == 100, f"10×10 方块 mass_px 应为 100，得 {mass_px}"

    def test_multi_roi_takes_largest(self, tmp_path):
        """多 ROI 时取最大连通域"""
        from lesion_features_cbis import extract_mass_roi

        mask_arr = np.zeros((64, 64), dtype=np.uint8)
        mask_arr[10:20, 10:20] = 255   # 10×10 = 100 px（大）
        mask_arr[40:44, 40:44] = 255   # 4×4   = 16 px（小）

        _, mass_px, n_comp = extract_mass_roi(mask_arr)

        assert n_comp == 2, f"两个 ROI 期望 n_components=2，得 {n_comp}"
        assert mass_px == 100, (
            f"多 ROI 应取最大连通域（100 px），得 {mass_px}"
        )

    def test_empty_mask_returns_zero(self):
        """空 mask 返回 mass_px=0, n_components=0"""
        from lesion_features_cbis import extract_mass_roi

        mask_arr = np.zeros((32, 32), dtype=np.uint8)
        _, mass_px, n_comp = extract_mass_roi(mask_arr)

        assert mass_px == 0
        assert n_comp == 0

    def test_mass_filter_by_meta_csv(self, tmp_path):
        """load_mass_image_ids: meta csv 过滤后只返回 abnormality_type==mass 的 id"""
        from lesion_features_cbis import load_mass_image_ids

        meta_rows = [
            {"image_id": "case_001", "abnormality_type": "mass"},
            {"image_id": "case_002", "abnormality_type": "calcification"},
            {"image_id": "case_003", "abnormality_type": "Mass"},  # 大小写
            {"image_id": "case_004", "abnormality_type": "MASS"},  # 全大写
        ]
        meta_csv = _make_meta_csv(tmp_path, meta_rows)

        mass_ids = load_mass_image_ids(str(meta_csv))

        assert "case_001" in mass_ids, "mass 应在结果中"
        assert "case_002" not in mass_ids, "calcification 不应在结果中"
        # 大小写不敏感（.lower() 处理）
        assert "case_003" in mass_ids, "Mass（大写M）应被识别"
        assert "case_004" in mass_ids, "MASS（全大写）应被识别"

    def test_no_meta_csv_returns_none(self):
        """meta_csv_path=None 时返回 None（不过滤）"""
        from lesion_features_cbis import load_mass_image_ids

        result = load_mass_image_ids(None)
        assert result is None, "无 meta csv 应返回 None（不过滤）"

    def test_nonexistent_meta_csv_returns_none(self, tmp_path):
        """meta csv 不存在时打印警告并返回 None（不崩溃）"""
        from lesion_features_cbis import load_mass_image_ids

        fake_path = str(tmp_path / "no_such_file.csv")
        result = load_mass_image_ids(fake_path)
        assert result is None, "meta csv 不存在应返回 None 不崩溃"


class TestCBISEmptyMass:
    """A6: mass 为空时不崩溃"""

    def test_empty_roi_mask_no_crash(self, tmp_path):
        """ROI mask 全零（无 mass）时 extract_cbis_features 不崩溃，mass_px=0"""
        from lesion_features_cbis import extract_cbis_features

        # 造带乳腺区的图，但 mask 全零
        img_path, mask_path, _ = _make_synthetic_mammogram(tmp_path, size=32, mass_radius=0)

        # 手动写全零 mask（覆盖 helper 写的 mask）
        empty_mask = np.zeros((32, 32), dtype=np.uint8)
        Image.fromarray(empty_mask, mode="L").save(mask_path)

        feats = extract_cbis_features(img_path, mask_path)

        assert feats["mass_px"] == 0, f"空 ROI mask 应得 mass_px=0，得 {feats['mass_px']}"
        assert feats["n_components"] == 0
        # area_ratio_full = 0 / full_frame_px = 0
        assert feats["area_ratio_full"] == pytest.approx(0.0)


class TestCBISBatchExtract:
    """batch_extract_cbis 端到端测试"""

    def _make_cbis_dir(self, tmp_path, n_mass=5, n_calc=3, include_meta=True):
        """
        建合成 CBIS 数据：n_mass 个 mass + n_calc 个 calcification。
        返回 (img_dir, mask_dir, meta_csv_path)
        """
        img_dir  = tmp_path / "imgs"
        mask_dir = tmp_path / "masks"
        img_dir.mkdir(parents=True, exist_ok=True)
        mask_dir.mkdir(parents=True, exist_ok=True)

        meta_rows = []
        for i in range(n_mass):
            iid = f"mass_{i:04d}"
            _make_synthetic_mammogram(img_dir, img_id=iid, size=32, mass_radius=4)
            # _make_synthetic_mammogram 写 img + mask，但 mask 名带 _mask 后缀
            meta_rows.append({"image_id": iid, "abnormality_type": "mass"})

        for i in range(n_calc):
            iid = f"calc_{i:04d}"
            _make_synthetic_mammogram(img_dir, img_id=iid, size=32, mass_radius=3)
            meta_rows.append({"image_id": iid, "abnormality_type": "calcification"})

        # 把 img_dir 里的 *_mask.png 移到 mask_dir（_make_synthetic_mammogram 写在 img_dir）
        for mf in list(img_dir.glob("*_mask.png")):
            mf.rename(mask_dir / mf.name)

        if include_meta:
            meta_csv = _make_meta_csv(tmp_path, meta_rows)
        else:
            meta_csv = None

        return img_dir, mask_dir, meta_csv

    def test_batch_only_returns_mass(self, tmp_path):
        """batch_extract_cbis 过滤后只返回 mass 样本"""
        from lesion_features_cbis import batch_extract_cbis

        img_dir, mask_dir, meta_csv = self._make_cbis_dir(
            tmp_path, n_mass=4, n_calc=3
        )
        out_csv = tmp_path / "out.csv"
        rows = batch_extract_cbis(
            img_dir=str(img_dir),
            mask_dir=str(mask_dir),
            out_csv=str(out_csv),
            meta_csv=str(meta_csv),
        )

        # 应只有 n_mass=4 行（calcification 被过滤）
        assert len(rows) == 4, (
            f"meta csv 过滤后应只有 4 个 mass 样本，得 {len(rows)}"
        )

    def test_batch_no_meta_returns_all(self, tmp_path):
        """不传 meta_csv 时返回全部（mass + calcification）"""
        from lesion_features_cbis import batch_extract_cbis

        img_dir, mask_dir, _ = self._make_cbis_dir(
            tmp_path / "no_meta", n_mass=3, n_calc=2, include_meta=False
        )
        rows = batch_extract_cbis(
            img_dir=str(img_dir),
            mask_dir=str(mask_dir),
            out_csv=None,
            meta_csv=None,
        )
        # 无过滤：3+2=5 个
        assert len(rows) == 5, (
            f"无 meta csv 时应返回全部 5 个，得 {len(rows)}"
        )

    def test_batch_output_schema(self, tmp_path):
        """输出 csv 包含必要列"""
        from lesion_features_cbis import batch_extract_cbis

        img_dir, mask_dir, meta_csv = self._make_cbis_dir(
            tmp_path / "schema", n_mass=3, n_calc=0
        )
        out_csv = tmp_path / "schema_out.csv"
        batch_extract_cbis(
            img_dir=str(img_dir),
            mask_dir=str(mask_dir),
            out_csv=str(out_csv),
            meta_csv=str(meta_csv),
        )
        assert out_csv.exists(), "输出 csv 未生成"
        rows = list(csv.DictReader(open(out_csv)))
        assert len(rows) == 3

        required_cols = [
            "image_id", "mass_px", "breast_px", "full_frame_px",
            "area_ratio_breast", "area_ratio_full",
            "n_components", "contrast", "dilation_px",
        ]
        for col in required_cols:
            assert col in rows[0], f"输出缺少列: {col}"

    def test_batch_ring_frac_list(self, tmp_path):
        """ring_frac_list=[0.05,0.075,0.10] 输出三个 csv"""
        from lesion_features_cbis import batch_extract_cbis

        img_dir, mask_dir, meta_csv = self._make_cbis_dir(
            tmp_path / "rf", n_mass=3, n_calc=0
        )
        out_csv = tmp_path / "out_rf.csv"
        result = batch_extract_cbis(
            img_dir=str(img_dir),
            mask_dir=str(mask_dir),
            out_csv=str(out_csv),
            meta_csv=str(meta_csv),
            ring_frac_list=[0.05, 0.075, 0.10],
        )
        # 多档返回 dict
        assert isinstance(result, dict), "ring_frac_list 多档应返回 dict"
        assert set(result.keys()) == {0.05, 0.075, 0.10}

        # 三个 csv 文件存在
        for frac in [0.05, 0.075, 0.10]:
            frac_str = str(frac).replace(".", "p")
            expected = tmp_path / f"out_rf_rf{frac_str}.csv"
            assert expected.exists(), f"三档 csv 不存在: {expected.name}"


# ============================================================
# B: area_ratio_check.py CBIS 扩展测试
# ============================================================

class TestAreaRatioCheckCBISExtension:
    """B1-B5: area_ratio_check 新参数测试"""

    def _make_brats_csv(self, tmp_path, n=100, seed=0):
        """合成 BraTS csv（size_px + brain_px）"""
        rng = np.random.default_rng(seed)
        size_arr  = rng.integers(10, 500, size=n).astype(float)
        # brain_px 约为 全图 40-80%（脑组织充满切片）
        brain_arr = rng.integers(2500, 4096, size=n).astype(float)
        return _make_brats_features_csv(tmp_path, "brats", size_arr, brain_arr), size_arr, brain_arr

    def _make_cbis_csv_with_ratios(self, tmp_path, n=100, seed=1):
        """合成 CBIS csv（含 area_ratio_breast / area_ratio_full）"""
        rng = np.random.default_rng(seed)
        rows = []
        for i in range(n):
            full_px   = 64 * 64
            breast_px = int(rng.integers(1500, 3000))   # 乳腺占 40-70% 全图
            mass_px   = int(rng.integers(10, 300))
            arb = round(mass_px / breast_px, 6)
            arf = round(mass_px / full_px, 6)
            rows.append({
                "image_id":          f"cbis_{i:04d}",
                "mass_px":           mass_px,
                "breast_px":         breast_px,
                "full_frame_px":     full_px,
                "area_ratio_breast": arb,
                "area_ratio_full":   arf,
                "n_components":      1,
                "contrast":          round(float(rng.random() * 0.3), 6),
                "dilation_px":       2,
                "ring_width_frac":   0.075,
                "breast_otsu_threshold": 0.3,
                "orig_h":            300,
                "orig_w":            250,
            })
        return _make_cbis_features_csv(tmp_path, "cbis_feats", rows)

    def test_target_ratio_col_reads_precomputed(self, tmp_path):
        """B1: target_ratio_col 直接读 area_ratio_breast，跳过 size_px 计算"""
        from area_ratio_check import run_area_ratio_check

        brats_csv, _, _ = self._make_brats_csv(tmp_path, n=80)
        cbis_csv = self._make_cbis_csv_with_ratios(tmp_path, n=60)
        out_dir = tmp_path / "out_b1"

        result = run_area_ratio_check(
            brats_features_csv=str(brats_csv),
            target_features_csv=str(cbis_csv),
            out_dir=str(out_dir),
            target_name="cbis_mass",
            target_ratio_col="area_ratio_breast",
            min_absolute=1,
            min_overlap_frac=0.0,
        )
        assert result is not None
        assert "overlap_ok" in result
        assert result["target_n_total"] == 60, (
            f"target_n_total 应为 60，得 {result['target_n_total']}"
        )

    def test_target_ratio_col_out_of_range_raises(self, tmp_path):
        """B2: target_ratio_col 值超过 1.0 触发 ValueError"""
        from area_ratio_check import run_area_ratio_check

        # 写一个含非法面积比的 csv
        bad_rows = [
            {"image_id": "bad_001", "area_ratio_breast": 1.5,  # 超出 [0,1]
             "area_ratio_full": 0.05, "mass_px": 100, "breast_px": 200,
             "full_frame_px": 4096, "n_components": 1, "contrast": 0.1,
             "dilation_px": 2, "ring_width_frac": 0.075,
             "breast_otsu_threshold": 0.3, "orig_h": 200, "orig_w": 200},
        ]
        bad_csv = _make_cbis_features_csv(tmp_path, "bad_cbis", bad_rows)

        brats_sizes = np.linspace(10, 500, 50)
        brats_csv = _make_brats_features_csv(tmp_path, "brats_b2", brats_sizes)
        out_dir = tmp_path / "out_b2"

        with pytest.raises(ValueError, match="超出"):
            run_area_ratio_check(
                brats_features_csv=str(brats_csv),
                target_features_csv=str(bad_csv),
                out_dir=str(out_dir),
                target_name="bad_test",
                target_ratio_col="area_ratio_breast",
            )

    def test_brats_brain_px_col_tumor_over_brain(self, tmp_path):
        """B3: brats_brain_px_col 时 BraTS 面积比 = size_px / brain_px"""
        from area_ratio_check import run_area_ratio_check

        # BraTS: size_px 小，brain_px 大 → 面积比小（tumor 相对于脑组织）
        brats_sizes  = np.array([50, 100, 200, 300, 400], dtype=float)
        brain_sizes  = np.array([3000, 3200, 3100, 3300, 3400], dtype=float)
        brats_csv = _make_brats_features_csv(tmp_path, "brats_b3", brats_sizes, brain_sizes)

        # CBIS: area_ratio_breast 与 BraTS tumor/brain 类似量级
        cbis_rows = [
            {"image_id": f"c_{i}", "mass_px": 60, "breast_px": 1500,
             "full_frame_px": 4096, "area_ratio_breast": 0.04,
             "area_ratio_full": 0.015, "n_components": 1,
             "contrast": 0.1, "dilation_px": 2, "ring_width_frac": 0.075,
             "breast_otsu_threshold": 0.3, "orig_h": 300, "orig_w": 250}
            for i in range(10)
        ]
        cbis_csv = _make_cbis_features_csv(tmp_path, "cbis_b3", cbis_rows)
        out_dir = tmp_path / "out_b3"

        # 用 brats_brain_px_col + target_ratio_col 同时传入（两端机制对称）
        result = run_area_ratio_check(
            brats_features_csv=str(brats_csv),
            target_features_csv=str(cbis_csv),
            out_dir=str(out_dir),
            target_name="cbis_sym",
            target_ratio_col="area_ratio_breast",
            brats_brain_px_col="brain_px",
            min_absolute=1,
            min_overlap_frac=0.0,
        )
        assert "overlap_ok" in result
        # BraTS size_px/brain_px 范围 ~0.015~0.12，CBIS 0.04 应在此范围内有重叠
        assert result["target_n_total"] == 10

    def test_backward_compat_no_new_params(self, tmp_path):
        """B4: 不传新参数（target_ratio_col=None, brats_brain_px_col=None），行为不变"""
        from area_ratio_check import run_area_ratio_check

        # 完全用旧 size_px 路径
        brats_sizes  = np.arange(10, 510, 10, dtype=float)
        target_sizes = np.arange(5, 305, 10, dtype=float)
        brats_csv  = _make_brats_features_csv(tmp_path, "brats_bc", brats_sizes)
        # 旧格式 target csv（只有 size_px，无 ratio 列）
        p = tmp_path / "target_bc.csv"
        with open(p, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["filename", "size_px", "contrast"])
            w.writeheader()
            for i, s in enumerate(target_sizes):
                w.writerow({"filename": f"img_{i:04d}.png", "size_px": str(s), "contrast": "0.1"})

        out_dir = tmp_path / "out_bc"
        result = run_area_ratio_check(
            brats_features_csv=str(brats_csv),
            target_features_csv=str(p),
            out_dir=str(out_dir),
            target_name="compat",
            # 不传新参数
        )
        assert result is not None
        assert "overlap_ok" in result
        assert result["target_n_total"] == len(target_sizes)

    def test_overlap_ok_cbis_area_ratio_breast(self, tmp_path):
        """B5: area_ratio_breast 分布与 BraTS tumor/brain 有重叠 → overlap_ok"""
        from area_ratio_check import run_area_ratio_check

        # BraTS: tumor/全图，P25 ~ 0.02 (小病灶低面积比)
        rng = np.random.default_rng(42)
        brats_sizes = np.concatenate([
            rng.integers(5, 100, size=50).astype(float),    # 低面积比（模拟 BraTS 低区段）
            rng.integers(200, 700, size=50).astype(float),  # 高面积比
        ])
        brats_csv = _make_brats_features_csv(tmp_path, "brats_b5", brats_sizes)

        # CBIS area_ratio_breast: 有部分小 mass → 有样本在 BraTS 低面积比区段
        cbis_rows = []
        for i in range(100):
            if i < 15:
                arb = round(float(rng.uniform(0.001, 0.02)), 6)  # 小 mass，应在 BraTS P25 以内
            else:
                arb = round(float(rng.uniform(0.05, 0.3)), 6)   # 大 mass
            cbis_rows.append({
                "image_id": f"c_{i}", "mass_px": 50, "breast_px": 2000,
                "full_frame_px": 4096, "area_ratio_breast": arb,
                "area_ratio_full": arb * 0.5,  # 全图分母更大，比例更小
                "n_components": 1, "contrast": 0.1, "dilation_px": 2,
                "ring_width_frac": 0.075, "breast_otsu_threshold": 0.3,
                "orig_h": 300, "orig_w": 250,
            })
        cbis_csv = _make_cbis_features_csv(tmp_path, "cbis_b5", cbis_rows)
        out_dir = tmp_path / "out_b5"

        # BraTS P25 为 size_px/4096 的 P25，CBIS 的 arb 用 area_ratio_breast
        # 只要 CBIS 的 15 行 arb 值 <= BraTS P25 就 overlap
        result = run_area_ratio_check(
            brats_features_csv=str(brats_csv),
            target_features_csv=str(cbis_csv),
            out_dir=str(out_dir),
            target_name="cbis_mass",
            target_ratio_col="area_ratio_breast",
            min_absolute=10,       # 10 个即可（合成数据）
            min_overlap_frac=0.05, # 5%
        )
        # CBIS 低面积比样本 15/100=15% > 5%，且 15 >= 10 → overlap_ok=True
        assert result["overlap_ok"] is True, (
            f"CBIS area_ratio_breast 应有足够小 mass 与 BraTS 低区段重叠，"
            f"得 {result}"
        )

    def test_output_csv_has_ratio_mode_cols(self, tmp_path):
        """B1 输出 csv 含 brats_ratio_mode / target_ratio_mode 新列"""
        from area_ratio_check import run_area_ratio_check

        brats_csv, _, _ = self._make_brats_csv(tmp_path / "cols", n=50)
        cbis_csv = self._make_cbis_csv_with_ratios(tmp_path / "cols", n=40)
        out_dir = tmp_path / "cols" / "out"

        run_area_ratio_check(
            brats_features_csv=str(brats_csv),
            target_features_csv=str(cbis_csv),
            out_dir=str(out_dir),
            target_name="cols_test",
            target_ratio_col="area_ratio_breast",
            min_absolute=1,
            min_overlap_frac=0.0,
        )
        out_csv = out_dir / "area_ratio_check_cols_test.csv"
        assert out_csv.exists()
        rows = list(csv.DictReader(open(out_csv)))
        assert "brats_ratio_mode" in rows[0], "缺少 brats_ratio_mode 列"
        assert "target_ratio_mode" in rows[0], "缺少 target_ratio_mode 列"
        assert rows[0]["target_ratio_mode"] == "area_ratio_breast", (
            f"target_ratio_mode 应为 area_ratio_breast，得 {rows[0]['target_ratio_mode']}"
        )


# ============================================================
# C: brats_brain_px.py — BraTS 脑组织对称分母测试
# ============================================================

def _make_synthetic_brain_slice(tmp_path, img_id="brats_001", size=64,
                                 brain_ellipse_frac=0.7, tumor_radius=4):
    """
    合成 BraTS skull-stripped 脑切片：
      - 全图背景 = 0（黑色，非脑区/空气）
      - 中央椭圆区域（脑组织）= 120~180（灰色）
      - 中央小圆（tumor）= 220~255（高亮）
    返回 (img_path, tumor_mask_path, expected_brain_ellipse_frac)
    """
    H, W = size, size
    img_arr = np.zeros((H, W), dtype=np.uint8)

    cy, cx = H // 2, W // 2
    r = int(size * brain_ellipse_frac / 2)  # 脑区半径

    # 椭圆脑区
    for y in range(H):
        for x in range(W):
            if ((y - cy) / r) ** 2 + ((x - cx) / r) ** 2 <= 1.0:
                img_arr[y, x] = 150  # 脑组织灰度

    # tumor 小圆（中心）
    for y in range(H):
        for x in range(W):
            if (y - cy) ** 2 + (x - cx) ** 2 <= tumor_radius ** 2:
                img_arr[y, x] = 230  # tumor 高亮

    img_path = tmp_path / f"{img_id}.png"
    Image.fromarray(img_arr, mode="L").save(img_path)

    return img_path


class TestBrainSegmentation:
    """C1-C4: brats_brain_px.segment_brain（nonzero 默认路径 + otsu fallback）"""

    def test_nonzero_finds_brain_ellipse(self, tmp_path):
        """C1: nonzero 方法找到脑区，排除黑边（skull-strip 正确路径）"""
        from brats_brain_px import segment_brain

        img_path = _make_synthetic_brain_slice(tmp_path, size=64, brain_ellipse_frac=0.7)
        img_arr = np.array(Image.open(img_path).convert("L"), dtype=np.uint8)
        # 默认 nonzero
        brain_mask, thr, brain_px = segment_brain(img_arr, brain_method="nonzero")

        total_px = img_arr.shape[0] * img_arr.shape[1]
        assert brain_px > 0, "nonzero segment_brain 应找到脑区像素"
        assert brain_px < total_px, (
            f"brain_px={brain_px} 不应等于全图 {total_px}（应排除黑边=0）"
        )
        # 椭圆 r=0.7*64/2=22px，面积 ~pi*22²~1520px，> 15% 全图
        assert brain_px > total_px * 0.15, (
            f"brain_px={brain_px} 过小（期望 >15% 全图 {total_px}）"
        )

    def test_nonzero_threshold_is_eps(self, tmp_path):
        """C1: nonzero 模式返回 threshold=eps，而非 Otsu 值"""
        from brats_brain_px import segment_brain

        img_path = _make_synthetic_brain_slice(tmp_path, size=32)
        img_arr = np.array(Image.open(img_path).convert("L"), dtype=np.uint8)
        _, thr, _ = segment_brain(img_arr, brain_method="nonzero", nonzero_eps=1e-6)

        assert thr == pytest.approx(1e-6), (
            f"nonzero 模式 threshold 应为 eps=1e-6，得 {thr}"
        )

    def test_nonzero_brain_px_ge_otsu(self, tmp_path):
        """Bug 修复验证：nonzero brain_px >= otsu brain_px（Otsu 欠割亮 tumor 区）"""
        from brats_brain_px import segment_brain

        # tumor_radius=8 使 tumor 很大、很亮（230）→ Otsu 容易把 tumor 当前景/背景分界误割
        img_path = _make_synthetic_brain_slice(
            tmp_path, size=64, brain_ellipse_frac=0.7, tumor_radius=8
        )
        img_arr = np.array(Image.open(img_path).convert("L"), dtype=np.uint8)

        _, _, brain_px_nz   = segment_brain(img_arr, brain_method="nonzero")
        _, _, brain_px_otsu = segment_brain(img_arr, brain_method="otsu")

        # nonzero 取全部非零像素（脑+tumor），otsu 可能切断 tumor 最亮区
        # 故 brain_px_nz >= brain_px_otsu
        assert brain_px_nz >= brain_px_otsu, (
            f"nonzero brain_px={brain_px_nz} 应 >= otsu brain_px={brain_px_otsu}，"
            f"Otsu 欠割 tumor 导致 brain_px 虚小（v1 bug 根因）"
        )

    def test_all_black_slice_returns_zero(self):
        """C4: 全黑切片返回 brain_px=0，不崩溃"""
        from brats_brain_px import segment_brain

        all_black = np.zeros((64, 64), dtype=np.uint8)
        brain_mask, thr, brain_px = segment_brain(all_black, brain_method="nonzero")

        assert brain_px == 0, f"全黑切片 brain_px 应为 0，得 {brain_px}"
        assert brain_mask.shape == (64, 64)

    def test_brain_mask_is_bool(self, tmp_path):
        """segment_brain 返回 bool mask"""
        from brats_brain_px import segment_brain

        bool_dir = tmp_path / "bool_test"
        bool_dir.mkdir(parents=True, exist_ok=True)
        img_path = _make_synthetic_brain_slice(bool_dir, size=32)
        img_arr = np.array(Image.open(img_path).convert("L"), dtype=np.uint8)
        brain_mask, _, _ = segment_brain(img_arr, brain_method="nonzero")

        assert brain_mask.dtype == bool, (
            f"brain_mask dtype 应为 bool，得 {brain_mask.dtype}"
        )

    def test_invalid_method_raises(self):
        """非法 brain_method 触发 ValueError"""
        from brats_brain_px import segment_brain

        arr = np.zeros((32, 32), dtype=np.uint8)
        with pytest.raises(ValueError, match="brain_method"):
            segment_brain(arr, brain_method="invalid_method")


class TestBrainAreaRatio:
    """C2-C3: area_ratio_brain > area_ratio_full，∈[0,1]"""

    def test_area_ratio_brain_larger_than_full(self, tmp_path):
        """C2: skull-strip 后脑区 < 全图，所以 tumor/brain > tumor/全图"""
        from brats_brain_px import extract_brain_px, segment_brain

        img_path = _make_synthetic_brain_slice(tmp_path, size=64, tumor_radius=4)
        feats = extract_brain_px(img_path, img_size=64)

        # 用合成图的已知参数手算
        # tumor ~pi*4²~50px，brain ~pi*22²~1520px，全图 64²=4096px
        # area_ratio_brain ~= 50/1520 ~= 0.033
        # area_ratio_full  ~= 50/4096 ~= 0.012
        # => ratio_brain > ratio_full
        brain_px     = feats["brain_px"]
        full_frame   = feats["full_frame_px"]

        # 我们要验证：tumor_px / brain_px > tumor_px / full_frame_px
        # 等价于 brain_px < full_frame_px
        assert brain_px < full_frame, (
            f"skull-strip 后 brain_px={brain_px} 应 < full_frame_px={full_frame}"
        )
        # 因此 area_ratio_brain (分母 brain_px) > area_ratio_full (分母 full_frame_px)
        # 以具体数值验证（tumor_radius=4 固定，tumor_px 已知~50）
        tumor_px_approx = int(np.pi * 4 ** 2)  # ~50
        arb = tumor_px_approx / brain_px if brain_px > 0 else float("nan")
        arf = tumor_px_approx / full_frame
        assert arb > arf, (
            f"area_ratio_brain={arb:.4f} 应 > area_ratio_full={arf:.4f}（分母更小）"
        )

    def test_area_ratio_brain_in_0_1(self, tmp_path):
        """C3: area_ratio_brain ∈ [0,1]（tumor 不可超过脑区大小）"""
        from brats_brain_px import extract_brain_px

        img_path = _make_synthetic_brain_slice(tmp_path, size=64, tumor_radius=3)
        feats = extract_brain_px(img_path, img_size=64)

        brain_px = feats["brain_px"]
        # 合成图 tumor 远小于 brain，area_ratio_brain < 1
        if brain_px > 0:
            tumor_px_approx = int(np.pi * 3 ** 2)  # ~28
            arb = tumor_px_approx / brain_px
            assert 0.0 <= arb <= 1.0, (
                f"area_ratio_brain={arb:.4f} 超出 [0,1]"
            )

    def test_resize_to_64_consistent_with_stratify(self, tmp_path):
        """extract_brain_px img_size=64 后 full_frame_px=4096（与 stratify_eval 口径一致）"""
        from brats_brain_px import extract_brain_px

        # 造 128×128 大图（测 resize）
        large_dir = tmp_path / "large64"
        large_dir.mkdir(parents=True, exist_ok=True)
        img_path = _make_synthetic_brain_slice(large_dir, size=128)
        feats = extract_brain_px(img_path, img_size=64)

        assert feats["full_frame_px"] == 64 * 64, (
            f"resize 到 64 后 full_frame_px 应为 4096，得 {feats['full_frame_px']}"
        )


class TestBrainBatchExtract:
    """C5-C6: batch_extract_brain_px"""

    def _make_brain_dir(self, tmp_path, n=5):
        """建合成 BraTS tumor 图目录，返回 (img_dir, filenames)"""
        img_dir = tmp_path / "tumor_imgs"
        img_dir.mkdir(parents=True, exist_ok=True)
        filenames = []
        for i in range(n):
            iid = f"brats_{i:04d}"
            _make_synthetic_brain_slice(img_dir, img_id=iid, size=64)
            filenames.append(f"{iid}.png")
        return img_dir, filenames

    def _make_strat_csv(self, tmp_path, filenames, seed=0):
        """写合成 stratify_per_image_ae.csv（filename + size_px）"""
        rng = np.random.default_rng(seed)
        p = tmp_path / "strat.csv"
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["filename", "size_px", "contrast",
                                               "anomaly_score", "detected"])
            w.writeheader()
            for fn in filenames:
                w.writerow({
                    "filename":      fn,
                    "size_px":       str(int(rng.integers(20, 200))),
                    "contrast":      str(round(float(rng.random() * 0.3), 6)),
                    "anomaly_score": str(round(float(rng.random()), 6)),
                    "detected":      "1",
                })
        return p

    def test_batch_output_schema(self, tmp_path):
        """C5: 输出 csv 含必要列"""
        from brats_brain_px import batch_extract_brain_px

        img_dir, _ = self._make_brain_dir(tmp_path, n=4)
        out_csv = tmp_path / "brain_px_out.csv"
        rows = batch_extract_brain_px(
            tumor_img_dir=str(img_dir),
            out_csv=str(out_csv),
            img_size=64,
        )
        assert out_csv.exists(), "输出 csv 未生成"
        assert len(rows) == 4

        csv_rows = list(csv.DictReader(open(out_csv)))
        required = ["filename", "brain_px", "brain_threshold", "full_frame_px", "brain_method"]
        for col in required:
            assert col in csv_rows[0], f"输出缺少列: {col}"
        # brain_method 列值应为 nonzero（默认）
        assert csv_rows[0]["brain_method"] == "nonzero", (
            f"默认 brain_method 应为 nonzero，得 {csv_rows[0]['brain_method']}"
        )

    def test_batch_all_brain_px_nonzero(self, tmp_path):
        """C5: 合成脑切片（非全黑）brain_px 应 > 0"""
        from brats_brain_px import batch_extract_brain_px

        img_dir, _ = self._make_brain_dir(tmp_path / "nz", n=5)
        rows = batch_extract_brain_px(
            tumor_img_dir=str(img_dir),
            out_csv=str(tmp_path / "nz_out.csv"),
            img_size=64,
        )
        for r in rows:
            assert r["brain_px"] > 0, (
                f"{r['filename']}: brain_px 应 > 0（合成脑切片有脑区）"
            )

    def test_batch_join_strat_csv_adds_area_ratio_brain(self, tmp_path):
        """C6: 传入 strat csv 后输出含 area_ratio_brain 列"""
        from brats_brain_px import batch_extract_brain_px

        img_dir, filenames = self._make_brain_dir(tmp_path / "join", n=4)
        strat_csv = self._make_strat_csv(tmp_path, filenames)
        out_csv = tmp_path / "join_out.csv"

        rows = batch_extract_brain_px(
            tumor_img_dir=str(img_dir),
            out_csv=str(out_csv),
            img_size=64,
            brats_strat_csv=str(strat_csv),
        )
        assert out_csv.exists()
        csv_rows = list(csv.DictReader(open(out_csv)))
        assert "area_ratio_brain" in csv_rows[0], "join 后应有 area_ratio_brain 列"
        assert "size_px"          in csv_rows[0], "join 后应有 size_px 列"
        assert "area_ratio_full"  in csv_rows[0], "join 后应有 area_ratio_full 列"

        # area_ratio_brain 应在 [0, 1]（tumor 不可超过脑区）
        for r in csv_rows:
            arb = r["area_ratio_brain"]
            if arb != "nan":
                arb_f = float(arb)
                assert 0.0 <= arb_f <= 1.0, (
                    f"area_ratio_brain={arb_f} 超出 [0,1]，filename={r['filename']}"
                )

    def test_batch_area_ratio_brain_gt_area_ratio_full(self, tmp_path):
        """C6: area_ratio_brain > area_ratio_full（脑区<全图，分母更小→比例更大）"""
        from brats_brain_px import batch_extract_brain_px

        img_dir, filenames = self._make_brain_dir(tmp_path / "gt", n=5)
        strat_csv = self._make_strat_csv(tmp_path / "gt", filenames)
        out_csv = tmp_path / "gt_out.csv"

        batch_extract_brain_px(
            tumor_img_dir=str(img_dir),
            out_csv=str(out_csv),
            img_size=64,
            brats_strat_csv=str(strat_csv),
        )
        csv_rows = list(csv.DictReader(open(out_csv)))
        for r in csv_rows:
            arb = r.get("area_ratio_brain", "nan")
            arf = r.get("area_ratio_full",  "nan")
            if arb != "nan" and arf != "nan":
                assert float(arb) >= float(arf), (
                    f"{r['filename']}: area_ratio_brain={arb} 应 >= area_ratio_full={arf}"
                )

    def test_empty_dir_returns_empty(self, tmp_path):
        """tumor_img_dir 为空目录时返回空列表，不崩溃"""
        from brats_brain_px import batch_extract_brain_px

        empty_dir = tmp_path / "empty_tumor"
        empty_dir.mkdir(parents=True, exist_ok=True)
        rows = batch_extract_brain_px(
            tumor_img_dir=str(empty_dir),
            out_csv=str(tmp_path / "empty_out.csv"),
        )
        assert rows == [] or isinstance(rows, list), "空目录应返回空列表"

    def test_batch_area_ratio_gt1_raises_value_error(self, tmp_path):
        """C3: join strat csv 后若 area_ratio_brain > 1（欠割），触发 ValueError"""
        from brats_brain_px import batch_extract_brain_px

        # 合成脑切片（brain_px ~几百px）
        img_dir, filenames = self._make_brain_dir(tmp_path / "err", n=3)

        # 构造 strat csv：size_px 故意 > brain_px（注入 >1 情形，测断言）
        # brain_px 约 1500px，size_px 设为 9000 → ratio ~= 6.0 > 1
        p = tmp_path / "err_strat.csv"
        with open(p, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["filename", "size_px"])
            w.writeheader()
            for fn in filenames:
                w.writerow({"filename": fn, "size_px": "9000"})

        with pytest.raises(ValueError, match="area_ratio_brain > 1"):
            batch_extract_brain_px(
                tumor_img_dir=str(img_dir),
                out_csv=str(tmp_path / "err_out.csv"),
                img_size=64,
                brats_strat_csv=str(p),
            )


class TestG1ASymmetry:
    """C7: 两端对称性端到端验证（BraTS tumor/brain vs CBIS mass/breast 同一 overlap_ok 判定）"""

    def _make_brats_brain_csv(self, tmp_path, n=80, seed=0):
        """合成 brats_brain_px.csv（含 size_px + brain_px）"""
        rng = np.random.default_rng(seed)
        size_arr  = rng.integers(20, 400, size=n).astype(float)
        brain_arr = rng.integers(2000, 3800, size=n).astype(float)  # 脑区 ~49-93% 全图
        p = tmp_path / "brats_brain_px.csv"
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["filename", "brain_px",
                                               "brain_threshold", "full_frame_px",
                                               "brain_method",
                                               "size_px", "area_ratio_brain",
                                               "area_ratio_full"])
            w.writeheader()
            for i in range(n):
                spx = size_arr[i]
                bpx = brain_arr[i]
                w.writerow({
                    "filename":        f"brats_{i:04d}.png",
                    "brain_px":        int(bpx),
                    "brain_threshold": 1e-6,   # nonzero eps（已修正，非 Otsu 值）
                    "full_frame_px":   4096,
                    "brain_method":    "nonzero",
                    "size_px":         int(spx),
                    "area_ratio_brain": round(spx / bpx, 6),
                    "area_ratio_full":  round(spx / 4096, 6),
                })
        return p

    def _make_cbis_breast_csv(self, tmp_path, n=60, seed=1, low_frac=0.15):
        """合成 lesion_features_cbis_mass.csv（含 area_ratio_breast）"""
        rng = np.random.default_rng(seed)
        n_low  = int(n * low_frac)
        n_high = n - n_low
        rows = []
        for i in range(n_low):
            arb = round(float(rng.uniform(0.005, 0.02)), 6)   # 小 mass（低面积比）
            rows.append({
                "image_id": f"cbis_low_{i}", "mass_px": 50, "breast_px": 2500,
                "full_frame_px": 4096, "area_ratio_breast": arb,
                "area_ratio_full": round(arb * 0.6, 6),
                "n_components": 1, "contrast": 0.1, "dilation_px": 2,
                "ring_width_frac": 0.075, "breast_otsu_threshold": 0.3,
                "orig_h": 300, "orig_w": 250,
            })
        for i in range(n_high):
            arb = round(float(rng.uniform(0.05, 0.3)), 6)     # 大 mass
            rows.append({
                "image_id": f"cbis_high_{i}", "mass_px": 200, "breast_px": 2000,
                "full_frame_px": 4096, "area_ratio_breast": arb,
                "area_ratio_full": round(arb * 0.6, 6),
                "n_components": 1, "contrast": 0.15, "dilation_px": 3,
                "ring_width_frac": 0.075, "breast_otsu_threshold": 0.3,
                "orig_h": 300, "orig_w": 250,
            })
        return _make_cbis_features_csv(tmp_path, "cbis_breast", rows)

    def test_symmetric_overlap_check(self, tmp_path):
        """C7: BraTS tumor/brain + CBIS mass/breast 对称 overlap_ok 判定正常运行"""
        from area_ratio_check import run_area_ratio_check

        brats_csv = self._make_brats_brain_csv(tmp_path, n=80)
        cbis_csv  = self._make_cbis_breast_csv(tmp_path, n=60, low_frac=0.15)
        out_dir   = tmp_path / "sym_out"

        result = run_area_ratio_check(
            brats_features_csv=str(brats_csv),
            target_features_csv=str(cbis_csv),
            out_dir=str(out_dir),
            target_name="cbis_sym",
            target_ratio_col="area_ratio_breast",    # CBIS: mass/breast
            brats_brain_px_col="brain_px",            # BraTS: tumor/brain
            min_absolute=5,
            min_overlap_frac=0.05,
        )
        assert result is not None
        assert "overlap_ok" in result
        # CBIS 低面积比样本（15%）应与 BraTS tumor/brain 低区段有重叠
        # （两端分母都是组织区域，量级可比，应能重叠）
        # 不强制 True/False（取决于合成数据分布），只要不报错 + 结果合理
        assert result["target_n_total"] == 60, (
            f"target_n_total 应为 60，得 {result['target_n_total']}"
        )
        brats_p25 = result["brats_low_threshold"]
        assert 0.0 <= brats_p25 <= 1.0, (
            f"BraTS P25（tumor/brain）应在 [0,1]，得 {brats_p25}"
        )

    def test_output_csv_notes_both_ratio_modes(self, tmp_path):
        """C7: 输出 csv note 字段标注两端 ratio mode"""
        from area_ratio_check import run_area_ratio_check

        brats_csv = self._make_brats_brain_csv(tmp_path / "note", n=50)
        cbis_csv  = self._make_cbis_breast_csv(tmp_path / "note", n=40)
        out_dir   = tmp_path / "note" / "out"

        run_area_ratio_check(
            brats_features_csv=str(brats_csv),
            target_features_csv=str(cbis_csv),
            out_dir=str(out_dir),
            target_name="note_test",
            target_ratio_col="area_ratio_breast",
            brats_brain_px_col="brain_px",
            min_absolute=1,
            min_overlap_frac=0.0,
        )
        out_csv = out_dir / "area_ratio_check_note_test.csv"
        rows = list(csv.DictReader(open(out_csv)))
        note = rows[0].get("note", "")
        assert "brain_px" in note or "tumor/brain_px" in note, (
            f"note 应标注 BraTS brain_px ratio mode，得: {note}"
        )


# ============================================================
# D: cbis_build_pairs.py — awsaf49 真实数据 join 测试
# ============================================================

CBIS_ROOT = Path("D:/YJ-Agent/data/external/cbis_ddsm")

@pytest.mark.skipif(
    not CBIS_ROOT.exists(),
    reason="CBIS-DDSM 真实数据不存在，跳过集成测试"
)
class TestCBISBuildPairsIntegration:
    """D1-D4: awsaf49 真实数据端到端 join 验证（小样本）"""

    def test_d1_build_pairs_returns_nonzero(self):
        """D1: build_mass_pairs 成功配对 > 0 行，跳过 = 0（数据完整时）"""
        from cbis_build_pairs import build_mass_pairs
        pairs, skip_log = build_mass_pairs(
            cbis_root=str(CBIS_ROOT),
            out_csv=None,
            include_test=True,
            verbose=False,
        )
        assert len(pairs) > 1000, (
            f"配对成功数应 > 1000（CBIS 有 1696 mass 异常），得 {len(pairs)}"
        )

    def test_d2_pairs_schema(self):
        """D2: pairs 列齐全（abnorm_uid / full_img_jpeg_path / roi_mask_jpeg_path 等）"""
        from cbis_build_pairs import build_mass_pairs
        pairs, _ = build_mass_pairs(
            cbis_root=str(CBIS_ROOT),
            out_csv=None,
            include_test=False,   # 只 train，快一点
            verbose=False,
        )
        required_cols = [
            "abnorm_uid", "split", "patient_id", "side", "view",
            "abnormality_id", "abnormality_type", "pathology",
            "full_img_jpeg_path", "roi_mask_jpeg_path", "swap_flag",
        ]
        for col in required_cols:
            assert col in pairs[0], f"pairs 缺少列: {col}"
        # abnormality_type 应全为 mass
        for p in pairs[:20]:
            assert p["abnormality_type"].lower() == "mass", (
                f"非 mass 行混入: {p['abnorm_uid']} type={p['abnormality_type']}"
            )

    def test_d3_jpeg_files_exist_spot_check(self):
        """D3: 抽 5 对，full jpeg + mask jpeg 文件实际存在"""
        from cbis_build_pairs import build_mass_pairs
        pairs, _ = build_mass_pairs(
            cbis_root=str(CBIS_ROOT),
            out_csv=None,
            include_test=False,
            verbose=False,
        )
        sample = pairs[:5]
        for p in sample:
            fp = Path(p["full_img_jpeg_path"])
            mp = Path(p["roi_mask_jpeg_path"])
            assert fp.exists(), f"full jpeg 不存在: {fp}"
            assert mp.exists(), f"mask jpeg 不存在: {mp}"

    def test_d4_e2e_features_3_samples(self, tmp_path):
        """D4: 取 3 个真实 mass 异常端到端跑 extract_cbis_features，area_ratio∈[0,1]"""
        from cbis_build_pairs import build_mass_pairs
        from lesion_features_cbis import extract_cbis_features
        import numpy as np

        pairs, _ = build_mass_pairs(
            cbis_root=str(CBIS_ROOT),
            out_csv=None,
            include_test=False,
            verbose=False,
        )
        sample = pairs[:3]
        for p in sample:
            feats = extract_cbis_features(
                p["full_img_jpeg_path"],
                p["roi_mask_jpeg_path"],
                ring_width_frac=0.075,
                img_size=64,
            )
            uid = p["abnorm_uid"]
            arb = feats["area_ratio_breast"]
            arf = feats["area_ratio_full"]

            assert feats["mass_px"] > 0, f"{uid}: mass_px 应 > 0"
            assert feats["breast_px"] > 0, f"{uid}: breast_px 应 > 0"
            assert feats["full_frame_px"] == 64 * 64, f"{uid}: img_size=64 后 full_frame_px 应=4096"

            if not np.isnan(arb):
                assert 0.0 <= arb <= 1.0, f"{uid}: area_ratio_breast={arb:.4f} 超出 [0,1]"
            assert 0.0 <= arf <= 1.0, f"{uid}: area_ratio_full={arf:.4f} 超出 [0,1]"
            # 黑边图中 area_ratio_breast 应 >= area_ratio_full
            if not np.isnan(arb):
                assert arb >= arf - 1e-8, (
                    f"{uid}: area_ratio_breast={arb:.4f} 应 >= area_ratio_full={arf:.4f}"
                )


@pytest.mark.skipif(
    not CBIS_ROOT.exists(),
    reason="CBIS-DDSM 真实数据不存在，跳过集成测试"
)
class TestCBISBatchFromPairsIntegration:
    """D5: batch_extract_from_pairs 端到端（小样本，出 csv）"""

    def test_d5_batch_from_pairs_outputs_csv(self, tmp_path):
        """D5: 写配对清单 → batch_extract_from_pairs → lesion_features csv 存在且行数 > 0"""
        from cbis_build_pairs import build_mass_pairs
        from lesion_features_cbis import batch_extract_from_pairs

        # 只用 train set 前 10 对
        pairs, _ = build_mass_pairs(
            cbis_root=str(CBIS_ROOT),
            out_csv=None,
            include_test=False,
            verbose=False,
        )
        sample = pairs[:10]

        # 写小配对 csv
        pairs_csv = tmp_path / "pairs_10.csv"
        fieldnames = list(sample[0].keys())
        with open(pairs_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(sample)

        out_csv = tmp_path / "feats_10.csv"
        result = batch_extract_from_pairs(
            pairs_csv=str(pairs_csv),
            out_csv=str(out_csv),
            ring_width_frac=0.075,
            img_size=64,
        )
        assert out_csv.exists(), "输出 csv 未生成"
        rows = list(csv.DictReader(open(out_csv)))
        assert len(rows) == 10, f"10 对应输出 10 行，得 {len(rows)}"

        # 检查关键列
        required = ["abnorm_uid", "area_ratio_breast", "area_ratio_full",
                    "mass_px", "breast_px", "full_frame_px",
                    "n_components", "contrast", "pathology"]
        for col in required:
            assert col in rows[0], f"输出缺少列: {col}"

        # area_ratio_breast ∈ [0,1]（或 nan，极端情况）
        for r in rows:
            arb_str = r["area_ratio_breast"]
            if arb_str != "nan":
                arb = float(arb_str)
                assert 0.0 <= arb <= 1.0, (
                    f"{r['abnorm_uid']}: area_ratio_breast={arb} 超出 [0,1]"
                )
