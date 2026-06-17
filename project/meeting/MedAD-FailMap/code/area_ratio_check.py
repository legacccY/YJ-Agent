"""
area_ratio_check.py — PR-7 面积比分布重叠检查（Gate1 G1-a 子条件）
服务: MedAD-FailMap Phase 1, PC-B Gate1 G1-a

算 BraTS tumor 与目标集（HAM/METS/CBIS）lesion 的「病灶/背景面积比」
（lesion_px / total_px），输出两端分位数 + 重叠区段统计 + flag（overlap_ok）。

G1-a 子条件：BraTS 驱动稀释的低面积比区段在目标集是否有非空样本支撑。
  overlap_ok=True  → 此对同构性前置满足，可继续外推
  overlap_ok=False → 假同构，此对作废省 GPU

PR-7 bug 修复（Phase 1 新代码，不动 Phase 0）：
  bug a — 坐标系统一：两端 size_px 必须在同一坐标系下算，area_ratio = size_px / (img_size^2)。
           Phase 1 路径 lesion_features.py --phase1-mode 强制 resize=64，两端统一用 64^2 分母。
           若 target_img_size != brats_img_size 则警告（两端 size_px 坐标系不同，area_ratio 不可比）。
           断言：area_ratio 值域 [0, 1]（含边界），超出则 ValueError。
  bug b — min_target_support 改为占比门槛：overlap_ok = target 落在 BraTS 低区段的样本数
           >= max(min_absolute, round(target_n * min_overlap_frac))，二者取较严（较大值）。
           默认 min_overlap_frac=0.05（5%）、min_absolute=30，保证统计支撑实质性。

PR-7: 面积比分布重叠检查（06_phase1_plan §7 预登记待冻）
# TODO: PR-7 重叠判定阈值（brats_low_ratio_pct, min_overlap_frac, min_absolute）待 reviewer 复裁 + 主线拍板冻结。

CBIS G1-a 扩展（Phase 1 正臂，不动既有接口）：
  --target-ratio-col   : 目标集 csv 中用作面积比的列名（默认 None = 沿用 size_px 路径）
                         CBIS 传 area_ratio_breast（机制公平）或 area_ratio_full（敏感性对照）
  --brats-brain-px-col : BraTS 脑组织像素列（可选）。若提供，BraTS 侧面积比改为
                         size_px / brain_px（而非 size_px / img_size²），机制对称。
                         # TODO: BraTS 脑组织 Otsu 分割待主线启动后填；目前为可选（未传则沿用旧分母）

输入:
  --brats-features-csv : BraTS per-image 特征 csv（含 size_px 列，来自 stratify_eval）
  --target-features-csv: 目标集特征 csv（含 size_px 列或自定义 ratio 列）
  --brats-img-size     : BraTS mask resize 尺寸（默认 64，用于算 total_px=size*size）
  --target-img-size    : 目标集 mask resize 尺寸（默认 None=同 brats-img-size；Phase 1 应传 64）
  --target-ratio-col   : 直接用目标集 csv 中此列作面积比（跳过 size_px / img_size² 计算）
                         CBIS 用 area_ratio_breast；HAM/METS 默认 None（沿用 size_px 路径）
  --brats-brain-px-col : BraTS csv 中脑组织像素列（可选）；传入时 BraTS 面积比 = size_px / brain_px
  --min-overlap-frac   : PR-7 bug b：目标集落在低区段的最低占比门槛（默认 0.05=5%）
  --min-absolute       : PR-7 bug b：绝对样本数下限（默认 30），与占比门槛取较严
  --out-dir            : 输出目录
  --target-name        : 目标集名称（ham/mets/cbis，用于输出文件名）

产出:
  area_ratio_check_<target>.csv  -- 分位数 + 重叠统计 + overlap_ok flag
  area_ratio_hist_<target>.png   -- 两端面积比直方图（matplotlib）

依赖: numpy, matplotlib
不用 scipy（OMP#15）
"""

import argparse
import csv
from pathlib import Path

import numpy as np


# ============================================================
# 核心：面积比计算 + 重叠检查
# ============================================================

def _load_size_px(csv_path, size_col="size_px"):
    """从 csv 读 size_px 列，返回 numpy array（float），跳过 nan / 0"""
    vals = []
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            v = row.get(size_col, "nan")
            try:
                fv = float(v)
                if not np.isnan(fv) and fv >= 0:
                    vals.append(fv)
            except (TypeError, ValueError):
                continue
    return np.array(vals, dtype=float)


def _load_ratio_col(csv_path, ratio_col):
    """
    从 csv 直接读面积比列（已预先计算，如 area_ratio_breast / area_ratio_full）。
    跳过 nan / 负值 / 空串。
    用于 CBIS 等目标集 csv 已有机制公平面积比时，跳过 size_px / img_size² 换算。

    返回 numpy array（float）。
    """
    vals = []
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            v = row.get(ratio_col, "nan")
            try:
                fv = float(v)
                if not np.isnan(fv) and fv >= 0:
                    vals.append(fv)
            except (TypeError, ValueError):
                continue
    return np.array(vals, dtype=float)


def _load_size_and_tissue_px(csv_path, size_col="size_px", tissue_px_col=None):
    """
    从 csv 读 size_px 和（可选）tissue_px 列，返回 (size_px_arr, tissue_px_arr)。
    tissue_px_col: 如 brain_px（BraTS 脑组织像素）；若为 None 则 tissue_px_arr = None。
    用于 BraTS 侧机制对称（tumor/brain 而非 tumor/全图）。

    # TODO: BraTS 脑组织 Otsu 分割待主线启动后填；目前 tissue_px_col 可选（未传则沿用旧分母）。
    """
    size_vals   = []
    tissue_vals = []
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            sv = row.get(size_col, "nan")
            try:
                sfv = float(sv)
                if not np.isnan(sfv) and sfv >= 0:
                    size_vals.append(sfv)
                    if tissue_px_col is not None:
                        tv = row.get(tissue_px_col, "nan")
                        try:
                            tfv = float(tv)
                            tissue_vals.append(tfv if not np.isnan(tfv) else float("nan"))
                        except (TypeError, ValueError):
                            tissue_vals.append(float("nan"))
            except (TypeError, ValueError):
                continue
    size_arr   = np.array(size_vals, dtype=float)
    tissue_arr = np.array(tissue_vals, dtype=float) if tissue_px_col is not None else None
    return size_arr, tissue_arr


def compute_area_ratio(size_px_arr, img_size):
    """
    area_ratio = size_px / (img_size * img_size)
    img_size: int（正方形假设）；若非正方形调用方传 total_px 另议。

    PR-7 bug a：两端必须传同一 img_size（Phase 1 均用 64）才能保证 area_ratio 可比。
    断言：所有 area_ratio 值在 [0, 1]（超出说明 size_px 坐标系与 img_size 不一致）。
    """
    total_px = float(img_size * img_size)
    ratios = size_px_arr / total_px
    # PR-7 bug a: 断言值域 [0, 1]
    if ratios.size > 0:
        bad = (ratios < 0) | (ratios > 1.0 + 1e-9)
        if bad.any():
            bad_vals = ratios[bad]
            raise ValueError(
                f"[area_ratio_check] area_ratio 超出 [0,1] 范围（共 {bad.sum()} 个），"
                f"最大值={ratios.max():.4f}，最小值={ratios.min():.4f}。"
                f"请检查 size_px 坐标系与 img_size={img_size} 是否一致。"
                f"Phase 1 路径须用 --phase1-mode 强制 resize=64。"
            )
    return ratios


def check_overlap(
    brats_ratios,
    target_ratios,
    brats_low_ratio_pct=25.0,
    min_target_support=1,
    min_overlap_frac=0.05,
    min_absolute=30,
):
    """
    G1-a 子条件判定：
      BraTS 低面积比区段 = brats_ratios <= brats_P{brats_low_ratio_pct}
      检查目标集在此区段有实质性样本支撑。

    PR-7 bug b 修复 — overlap_ok 判定：
      required = max(min_absolute, round(target_n * min_overlap_frac))
      overlap_ok = target_n_in_low_zone >= required
      二者取较严（较大值），保证「5% 且绝对 >=30」的双重门槛。
      min_target_support 参数保留供兼容旧调用，若传入且 > required 则取更严值。

    默认: brats_low_ratio_pct=25, min_overlap_frac=0.05, min_absolute=30
    # TODO: PR-7 三参数待 reviewer 复裁 + 主线拍板冻结。

    返回 dict:
      {
        "brats_low_threshold":   float,  # BraTS P{brats_low_ratio_pct}
        "target_n_in_low_zone":  int,    # 目标集落在 BraTS 低区段的样本数
        "target_n_total":        int,    # 目标集总样本数
        "required_support":      int,    # overlap_ok 门槛（取较严）
        "overlap_ok":            bool,
        "brats_low_ratio_pct":   float,
        "min_overlap_frac":      float,
        "min_absolute":          int,
      }
    """
    brats_low_threshold = float(np.percentile(brats_ratios, brats_low_ratio_pct))
    target_n_total = len(target_ratios)
    target_n_in_low_zone = int((target_ratios <= brats_low_threshold).sum())

    # PR-7 bug b: 占比门槛 + 绝对门槛取较严
    required_by_frac = int(round(target_n_total * min_overlap_frac))
    required = max(min_absolute, required_by_frac, min_target_support)
    overlap_ok = target_n_in_low_zone >= required

    return {
        "brats_low_threshold":  round(brats_low_threshold, 6),
        "target_n_in_low_zone": target_n_in_low_zone,
        "target_n_total":       target_n_total,
        "required_support":     required,
        "overlap_ok":           overlap_ok,
        "brats_low_ratio_pct":  brats_low_ratio_pct,
        "min_overlap_frac":     min_overlap_frac,
        "min_absolute":         min_absolute,
    }


def distribution_stats(ratios, prefix=""):
    """分位数统计"""
    pcts = [1, 5, 10, 25, 50, 75, 90, 95, 99]
    stats = {}
    for p in pcts:
        stats[f"{prefix}p{p}"] = round(float(np.percentile(ratios, p)), 6)
    stats[f"{prefix}mean"] = round(float(ratios.mean()), 6)
    stats[f"{prefix}std"] = round(float(ratios.std()), 6)
    stats[f"{prefix}n"] = len(ratios)
    return stats


# ============================================================
# 主函数
# ============================================================

def run_area_ratio_check(
    brats_features_csv,
    target_features_csv,
    out_dir,
    target_name="ham",
    brats_img_size=64,
    target_img_size=None,
    brats_low_ratio_pct=25.0,
    min_target_support=1,
    min_overlap_frac=0.05,
    min_absolute=30,
    target_ratio_col=None,
    brats_brain_px_col=None,
):
    """
    PR-7 面积比重叠检查主入口。

    brats_img_size:  BraTS mask 在 64×64 坐标系内，area_ratio = size_px / (64*64)
    target_img_size: 目标集（None→同 brats_img_size）。
                     PR-7 bug a：两端 img_size 必须一致，不一致则 WARNING。
                     Phase 1 两端均须用 64（lesion_features --phase1-mode）。
    min_overlap_frac: PR-7 bug b：目标集落在低区段的最低占比（默认 0.05=5%）
    min_absolute:     PR-7 bug b：绝对样本数下限（默认 30），与 min_overlap_frac 取较严

    CBIS G1-a 扩展（新参数，默认 None 保向后兼容）：
    target_ratio_col: 目标集 csv 中直接读取面积比的列名（如 area_ratio_breast）。
                      传入时跳过 size_px / img_size² 计算，直接用此列值作 target_ratios。
                      值域断言 [0, 1] 仍生效。
                      None = 沿用旧 size_px / img_size² 路径（HAM/METS 兼容）。
    brats_brain_px_col: BraTS csv 中脑组织像素列（如 brain_px）。
                        传入时 BraTS 面积比 = size_px / brain_px（tumor/brain，机制对称）。
                        None = 沿用旧 size_px / img_size²（tumor/全图，Phase 0 定义）。
                        # TODO: BraTS 脑组织 Otsu 待主线启动后填；目前可选，未传则沿用旧分母。
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ---- BraTS 面积比 ----
    if brats_brain_px_col is not None:
        # 机制对称模式：tumor/brain（Phase 1 CBIS 对应路径）
        brats_size_px, brats_brain_px = _load_size_and_tissue_px(
            brats_features_csv, size_col="size_px", tissue_px_col=brats_brain_px_col
        )
        if len(brats_size_px) == 0:
            raise ValueError(f"[area_ratio_check] brats csv 无有效 size_px: {brats_features_csv}")
        # 逐行算 tumor/brain ratio；过滤 brain_px=0 或 nan
        valid = (brats_brain_px > 0) & (~np.isnan(brats_brain_px))
        if valid.sum() == 0:
            raise ValueError(
                f"[area_ratio_check] brats csv 中 {brats_brain_px_col} 全为 0/nan，"
                f"无法计算 tumor/brain ratio"
            )
        brats_ratios = brats_size_px[valid] / brats_brain_px[valid]
        # 断言 [0, 1]
        bad = (brats_ratios < 0) | (brats_ratios > 1.0 + 1e-9)
        if bad.any():
            raise ValueError(
                f"[area_ratio_check] brats tumor/brain ratio 超出 [0,1]，"
                f"max={brats_ratios.max():.4f}。请检查 {brats_brain_px_col} 列。"
            )
        brats_ratio_note = f"tumor/{brats_brain_px_col}"
        _brats_img_size_for_note = None
    else:
        # 旧路径：tumor/全图（Phase 0 兼容）
        brats_size_px = _load_size_px(brats_features_csv)
        if len(brats_size_px) == 0:
            raise ValueError(f"[area_ratio_check] brats csv 无有效 size_px: {brats_features_csv}")
        brats_ratios = compute_area_ratio(brats_size_px, brats_img_size)
        brats_ratio_note = f"size_px/{brats_img_size}^2"
        _brats_img_size_for_note = brats_img_size

    # ---- 目标集面积比 ----
    if target_ratio_col is not None:
        # CBIS 模式：直接读预计算的面积比列（area_ratio_breast / area_ratio_full）
        target_ratios = _load_ratio_col(target_features_csv, ratio_col=target_ratio_col)
        if len(target_ratios) == 0:
            raise ValueError(
                f"[area_ratio_check] target csv 无有效 {target_ratio_col} 值: {target_features_csv}"
            )
        # 断言 [0, 1]
        bad = (target_ratios < 0) | (target_ratios > 1.0 + 1e-9)
        if bad.any():
            raise ValueError(
                f"[area_ratio_check] target {target_ratio_col} 超出 [0,1]，"
                f"max={target_ratios.max():.4f}。请检查 CBIS csv。"
            )
        target_ratio_note = target_ratio_col
        _target_img_size = None  # 不适用
    else:
        # 旧路径：size_px / img_size²（HAM/METS 兼容）
        target_size_px = _load_size_px(target_features_csv)
        if len(target_size_px) == 0:
            raise ValueError(f"[area_ratio_check] target csv 无有效 size_px: {target_features_csv}")

        # PR-7 bug a: 目标集 img_size 默认同 brats，若不同则警告
        _target_img_size = target_img_size if target_img_size is not None else brats_img_size
        if _target_img_size != brats_img_size:
            print(
                f"[area_ratio_check] WARNING PR-7 bug a: "
                f"target_img_size={_target_img_size} != brats_img_size={brats_img_size}。"
                f"两端坐标系不一致，area_ratio 不可直接比较！"
                f"Phase 1 路径请用 --phase1-mode 强制两端 resize=64。"
            )
        target_ratios = compute_area_ratio(target_size_px, _target_img_size)
        target_ratio_note = f"size_px/{_target_img_size}^2"

    overlap_result = check_overlap(
        brats_ratios, target_ratios,
        brats_low_ratio_pct=brats_low_ratio_pct,
        min_target_support=min_target_support,
        min_overlap_frac=min_overlap_frac,
        min_absolute=min_absolute,
    )

    brats_stats = distribution_stats(brats_ratios, prefix="brats_")
    target_stats = distribution_stats(target_ratios, prefix="target_")

    # 输出主 csv（summary + flag）
    out_csv = out_dir / f"area_ratio_check_{target_name}.csv"
    summary_row = {
        "target_name":          target_name,
        "brats_img_size":       brats_img_size if _brats_img_size_for_note is not None else "tissue_px",
        "target_img_size":      _target_img_size if _target_img_size is not None else target_ratio_col,
        "brats_ratio_mode":     brats_ratio_note,
        "target_ratio_mode":    target_ratio_note,
        **brats_stats,
        **target_stats,
        **overlap_result,
        "note": (
            f"PR-7 G1-a: brats ratio={brats_ratio_note}; target ratio={target_ratio_note}; "
            f"brats low zone <= P{brats_low_ratio_pct:.0f} "
            f"= {overlap_result['brats_low_threshold']:.4f}; "
            f"target support = {overlap_result['target_n_in_low_zone']}/"
            f"{overlap_result['target_n_total']} "
            f"(required>={overlap_result['required_support']}); "
            f"overlap_ok = {overlap_result['overlap_ok']}"
        ),
    }
    with open(out_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summary_row.keys()))
        w.writeheader()
        w.writerow(summary_row)
    print(f"  -> {out_csv.name}")

    # 输出直方图 png（matplotlib，纯 CPU）
    out_png = out_dir / f"area_ratio_hist_{target_name}.png"
    _plot_histogram(brats_ratios, target_ratios, target_name, overlap_result, out_png)

    flag = overlap_result["overlap_ok"]
    print(f"[area_ratio_check] {target_name}: overlap_ok={flag} "
          f"(brats ratio={brats_ratio_note}, low zone <= {overlap_result['brats_low_threshold']:.4f}, "
          f"target n_in_low={overlap_result['target_n_in_low_zone']}/"
          f"{overlap_result['target_n_total']}, "
          f"required>={overlap_result['required_support']})")
    return overlap_result


def _plot_histogram(brats_ratios, target_ratios, target_name, overlap_result, out_png):
    """画两端面积比直方图 + 低区段分界线"""
    try:
        import matplotlib
        matplotlib.use("Agg")  # 非交互后端，Windows spawn 安全
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(7, 4))
        bins = np.linspace(0, max(brats_ratios.max(), target_ratios.max()) * 1.05, 40)

        ax.hist(brats_ratios, bins=bins, alpha=0.55, label="BraTS tumor",
                color="#1f77b4", edgecolor="white")
        ax.hist(target_ratios, bins=bins, alpha=0.55, label=f"{target_name} lesion",
                color="#ff7f0e", edgecolor="white")

        low_thr = overlap_result["brats_low_threshold"]
        ax.axvline(low_thr, color="#2ca02c", linestyle="--", linewidth=1.5,
                   label=f"BraTS P{overlap_result['brats_low_ratio_pct']:.0f}={low_thr:.3f}")

        n_in = overlap_result["target_n_in_low_zone"]
        ok = overlap_result["overlap_ok"]
        ax.set_xlabel("lesion/image area ratio")
        ax.set_ylabel("count")
        ax.set_title(
            f"PR-7 G1-a: BraTS vs {target_name} area ratio\n"
            f"target in BraTS low zone: n={n_in}, overlap_ok={ok}"
        )
        ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(out_png, dpi=120)
        plt.close(fig)
        print(f"  -> {out_png.name}")
    except ImportError:
        print("[area_ratio_check] matplotlib not available, skip histogram")


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="PR-7 G1-a 面积比分布重叠检查（Gate1 前置同构性）"
    )
    _root = Path(__file__).resolve().parent.parent
    _res = _root / "results"

    parser.add_argument("--brats-features-csv",
                        default=str(_res / "stratify_per_image_ae.csv"),
                        help="BraTS per-image 特征 csv（含 size_px 列）")
    parser.add_argument("--target-features-csv",
                        required=True,
                        help="目标集特征 csv（来自 lesion_features.py，含 size_px 列）")
    parser.add_argument("--out-dir", default=str(_res))
    parser.add_argument("--target-name", default="ham",
                        help="目标集名称（ham/mets），用于输出文件名")
    parser.add_argument("--brats-img-size", type=int, default=64,
                        help="BraTS mask resize 尺寸（默认 64）")
    parser.add_argument("--target-img-size", type=int, default=None,
                        help="目标集 img 尺寸（None=同 brats-img-size）")
    parser.add_argument("--brats-low-ratio-pct", type=float, default=25.0,
                        help="PR-7: BraTS 低面积比区段分位数（默认 25）"
                             " # TODO: PR-7 待冻结")
    parser.add_argument("--min-target-support", type=int, default=1,
                        help="PR-7: （旧参数，兼容用）目标集最少绝对支撑，被 --min-absolute 取代"
                             " # TODO: PR-7 待冻结")
    parser.add_argument("--min-overlap-frac", type=float, default=0.05,
                        help="PR-7 bug b: 目标集落在低区段的最低占比门槛（默认 0.05=5%%）"
                             " # TODO: PR-7 待冻结")
    parser.add_argument("--min-absolute", type=int, default=30,
                        help="PR-7 bug b: 绝对样本数下限，与 --min-overlap-frac 取较严（默认 30）"
                             " # TODO: PR-7 待冻结")
    parser.add_argument("--target-ratio-col", default=None,
                        help=(
                            "CBIS G1-a 扩展: 目标集 csv 中直接读取面积比的列名。"
                            "传 area_ratio_breast（机制公平）或 area_ratio_full（敏感性对照）。"
                            "传入时跳过 size_px/img_size² 计算，直接用此列值。"
                            "None=沿用旧 size_px 路径（HAM/METS 兼容）。"
                        ))
    parser.add_argument("--brats-brain-px-col", default=None,
                        help=(
                            "CBIS G1-a 扩展: BraTS csv 中脑组织像素列（如 brain_px）。"
                            "传入时 BraTS 面积比 = size_px/brain_px（tumor/brain，机制对称）。"
                            "None=沿用旧 size_px/img_size²（Phase 0 定义）。"
                            "# TODO: BraTS 脑组织 Otsu 待主线启动后填"
                        ))
    args = parser.parse_args()

    run_area_ratio_check(
        brats_features_csv=args.brats_features_csv,
        target_features_csv=args.target_features_csv,
        out_dir=args.out_dir,
        target_name=args.target_name,
        brats_img_size=args.brats_img_size,
        target_img_size=args.target_img_size,
        brats_low_ratio_pct=args.brats_low_ratio_pct,
        min_target_support=args.min_target_support,
        min_overlap_frac=args.min_overlap_frac,
        min_absolute=args.min_absolute,
        target_ratio_col=args.target_ratio_col,
        brats_brain_px_col=args.brats_brain_px_col,
    )
