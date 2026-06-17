"""
distribution_overlap.py — OVL/Bhattacharyya 固化落盘（PR-7c 可复现性缺口修复）
服务: MedAD-FailMap PR-7c iso 第二维（多灶性）+ A' 可复现性缺口

背景：
  LOG 中 OVL/BC 数值（如 HAM OVL=0.262/BC=0.547，IDRiD OVL=0.312/BC=0.533）
  只在文字态，无 csv 源。独立重算对 bin 数极敏感（IDRiD n=54 尤甚），
  本脚本钉死 bin 方案并落盘，保证可复现。

度量定义（纯 numpy，无 scipy）：
  OVL（直方图重叠面积）:
    将两个连续分布各归一化为 density（area=1），
    OVL = sum(min(p_source[i], p_target[i]) * bin_width[i])
    值域 [0,1]，越大越相似。
    注：因各 bin 乘以对应 bin_width，非等宽 bin 仍正确。

  Bhattacharyya 系数（BC）:
    BC = sum(sqrt(p_source[i] * p_target[i]) * bin_width[i])
    等价于归一化 count 版：p_i = count_i / (N * bin_width_i)
    （density histogram），故 BC = sum(sqrt(h1_i/N1 * h2_i/N2))
    其中 h_i 为 count（不 × bin_width）—— 此处采用 density 版统一口径。
    值域 [0,1]，越大越相似。

钉死 bin 方案（写死常量，保证可复现）：
  area_ratio:
    100 等宽线性 bins 覆盖 [0.0, 1.0]（含右边界，共 100 个 bin）
    BIN_SCHEME_AREA_RATIO = "linear_100_[0,1]"
    理由：area_ratio 值域严格 [0,1]，等宽线性自然对齐。

  n_components:
    50 对数 bins 覆盖 [0.5, 3000]，边界 np.logspace(log10(0.5), log10(3000), 51)
    BIN_SCHEME_NCOMP = "log50_[0.5,3000]"
    理由：
      - BraTS n_components 范围 [1,35]（中位 2）
      - HAM n_components 范围 [1,5]（中位 1）
      - CBIS n_components 范围 [1,~10]（中位 1）
      - IDRiD n_components 范围 [1,~2000]（中位 136）
      - 对数 bin 覆盖极端范围，低值区仍有分辨率。
      - 0.5 起点（<1 的 bin 只容纳值=0 的边缘情况，含 leftmost=0 处理）。

  对整数 n_components 的处理：
    bin 覆盖 [0.5, 3000]，0 值映射到 bin 左侧（不落在直方图中），
    因此 n_components=0 的 slice 不被计入（与 n>0 的分布比较时合理，
    因为 n=0 意味着空 mask，不属于"有病灶但单 vs 多灶"的讨论）。
    调用方可选择只传 n_components > 0 的子集。

输出：
  results/distribution_overlap_<pair>_<feature>.csv
  列：pair, feature, n_bins, bin_scheme, OVL, BC, n_source, n_target

依赖: numpy
不用 scipy（OMP#15），无 torch，纯 CPU
"""

import argparse
import csv
from pathlib import Path

import numpy as np


# ============================================================
# 钉死 bin 方案（常量）
# ============================================================

# area_ratio: 100 等宽线性 bins over [0, 1]
_AREA_RATIO_BINS = np.linspace(0.0, 1.0, 101)        # 101 edges → 100 bins
BIN_SCHEME_AREA_RATIO = "linear_100_[0,1]"
N_BINS_AREA_RATIO     = 100

# n_components: 50 对数 bins over [0.5, 3000]
_NCOMP_BINS = np.logspace(
    np.log10(0.5),
    np.log10(3000.0),
    51,                                                 # 51 edges → 50 bins
)
BIN_SCHEME_NCOMP = "log50_[0.5,3000]"
N_BINS_NCOMP     = 50


def _get_bins(feature):
    """返回 (bin_edges, bin_scheme, n_bins) 元组"""
    if feature == "area_ratio":
        return _AREA_RATIO_BINS.copy(), BIN_SCHEME_AREA_RATIO, N_BINS_AREA_RATIO
    elif feature == "n_components":
        return _NCOMP_BINS.copy(), BIN_SCHEME_NCOMP, N_BINS_NCOMP
    else:
        raise ValueError(
            f"不支持的 feature: {feature!r}，"
            f"支持: 'area_ratio', 'n_components'"
        )


# ============================================================
# 核心：OVL + BC 计算
# ============================================================

def compute_ovl_bc(source_vals, target_vals, bin_edges):
    """
    计算两个分布的 OVL（直方图重叠面积）与 Bhattacharyya 系数（BC）。

    source_vals, target_vals: 1-D numpy array（float 或 int）
    bin_edges: 1-D numpy array，长度 = n_bins + 1

    OVL = sum_i  min(density_source_i, density_target_i) * bin_width_i
    BC  = sum_i  sqrt(density_source_i * density_target_i) * bin_width_i

    density_i = count_i / (N * bin_width_i)  （归一化使整体 area=1）

    返回 (OVL: float, BC: float)，均在 [0, 1]。

    注意：
      - 值落在 bin_edges 范围外的样本被忽略（np.histogram 默认行为）。
      - 若某端 N=0，OVL=0.0, BC=0.0（无分布可比）。
    """
    bin_edges = np.asarray(bin_edges, dtype=float)
    bin_widths = np.diff(bin_edges)            # shape (n_bins,)

    # count histogram（np.histogram 自动处理边界）
    h_src, _ = np.histogram(source_vals, bins=bin_edges)
    h_tgt, _ = np.histogram(target_vals, bins=bin_edges)

    n_src = float(h_src.sum())
    n_tgt = float(h_tgt.sum())

    if n_src == 0 or n_tgt == 0:
        return 0.0, 0.0

    # density：count / (N * bin_width)
    d_src = h_src.astype(float) / (n_src * bin_widths)
    d_tgt = h_tgt.astype(float) / (n_tgt * bin_widths)

    # OVL = sum(min(d_src, d_tgt) * bin_width)
    ovl = float(np.sum(np.minimum(d_src, d_tgt) * bin_widths))

    # BC = sum(sqrt(d_src * d_tgt) * bin_width)
    bc  = float(np.sum(np.sqrt(d_src * d_tgt) * bin_widths))

    # 截断到 [0, 1]（浮点误差可能产生极微小负值或 >1）
    ovl = float(np.clip(ovl, 0.0, 1.0))
    bc  = float(np.clip(bc,  0.0, 1.0))

    return ovl, bc


# ============================================================
# 从 csv 读取特征值
# ============================================================

def _load_col(csv_path, col):
    """
    从 csv 读取指定列，返回有效 float 数组（跳过 nan / 空串 / 非数字）。
    csv_path: str or Path
    col: 列名
    """
    vals = []
    csv_path = Path(csv_path)
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            v = row.get(col, "")
            if v in ("", "nan", "NaN", "None", None):
                continue
            try:
                fv = float(v)
                if np.isfinite(fv):
                    vals.append(fv)
            except (TypeError, ValueError):
                continue
    return np.array(vals, dtype=float)


# ============================================================
# 主函数：计算单对单特征
# ============================================================

def compute_pair_overlap(
    source_csv,
    target_csv,
    feature,
    source_col=None,
    target_col=None,
    pair_name="brats_ham",
    out_dir=None,
):
    """
    计算 source↔target 某特征的 OVL/BC，落盘到 csv。

    Args:
        source_csv  : BraTS 特征 csv 路径
        target_csv  : 目标集特征 csv 路径
        feature     : "area_ratio" 或 "n_components"
        source_col  : source csv 中对应列名（None → 自动推断）
        target_col  : target csv 中对应列名（None → 自动推断）
        pair_name   : 配对名称（如 "brats_ham"），用于输出文件名
        out_dir     : 输出目录（None → 不写文件，只返回结果 dict）

    自动推断列名规则（source_col=None 时）：
      feature="area_ratio":
        source: brats_brain_px.csv → "area_ratio_brain"；
                stratify_per_image_ae.csv → "area_ratio"（无此列则用 size_px/4096）
                实际上本脚本调用方应显式传 source_col。
      feature="n_components":
        source: ncomp_brats.csv → "n_components"
        target: 各目标集 csv → "n_components"

    返回 dict:
      pair, feature, n_bins, bin_scheme, OVL, BC, n_source, n_target
    """
    bin_edges, bin_scheme, n_bins = _get_bins(feature)

    # 自动列名
    if source_col is None:
        source_col = "n_components" if feature == "n_components" else "area_ratio_brain"
    if target_col is None:
        target_col = "n_components" if feature == "n_components" else "area_ratio_fov"

    src_vals = _load_col(source_csv, source_col)
    tgt_vals = _load_col(target_csv, target_col)

    if len(src_vals) == 0:
        raise ValueError(
            f"source csv 列 '{source_col}' 无有效值: {source_csv}\n"
            f"可用列检查: 打开 csv 确认列名"
        )
    if len(tgt_vals) == 0:
        raise ValueError(
            f"target csv 列 '{target_col}' 无有效值: {target_csv}\n"
            f"可用列检查: 打开 csv 确认列名"
        )

    ovl, bc = compute_ovl_bc(src_vals, tgt_vals, bin_edges)

    result = {
        "pair":       pair_name,
        "feature":    feature,
        "n_bins":     n_bins,
        "bin_scheme": bin_scheme,
        "OVL":        round(ovl, 6),
        "BC":         round(bc,  6),
        "n_source":   len(src_vals),
        "n_target":   len(tgt_vals),
    }

    print(
        f"[distribution_overlap] {pair_name} | {feature} | "
        f"OVL={ovl:.4f}  BC={bc:.4f}  "
        f"n_src={len(src_vals)}  n_tgt={len(tgt_vals)}  "
        f"bins={bin_scheme}"
    )

    if out_dir is not None:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_csv = out_dir / f"distribution_overlap_{pair_name}_{feature}.csv"
        fieldnames = ["pair", "feature", "n_bins", "bin_scheme",
                      "OVL", "BC", "n_source", "n_target"]
        with open(out_csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerow(result)
        print(f"  -> {out_csv}")

    return result


# ============================================================
# 批量：三对 × 两特征
# ============================================================

def run_all_pairs(
    brats_ncomp_csv,
    brats_area_csv,
    ham_ncomp_csv,
    ham_area_csv,
    cbis_ncomp_csv,
    cbis_area_csv,
    idrid_ncomp_csv,
    idrid_area_csv,
    out_dir,
):
    """
    跑出 BraTS↔HAM / BraTS↔CBIS / BraTS↔IDRiD 三对 × {area_ratio, n_components} 的 OVL/BC。

    参数说明（各 csv + 对应列名）：
      brats_ncomp_csv  : results/ncomp_brats.csv，列 n_components
      brats_area_csv   : results/brats_brain_px.csv，列 area_ratio_brain
      ham_ncomp_csv    : results/ncomp_ham.csv，列 n_components
      ham_area_csv     : results/area_ratio_check_ham.csv ← 不含 per-image，
                         实际用 results/lesion_features_ham.csv 算 size_px / 64^2 → TODO
                         # TODO: HAM area_ratio 的 per-image 列不在 lesion_features_ham.csv
                         # （无 area_ratio 列，只有 size_px），调用方传 csv+col 显式处理。
      cbis_ncomp_csv   : results/lesion_features_cbis_mass.csv，列 n_components
      cbis_area_csv    : results/lesion_features_cbis_mass.csv，列 area_ratio_breast
      idrid_ncomp_csv  : results/lesion_features_idrid.csv，列 n_components
      idrid_area_csv   : results/lesion_features_idrid.csv，列 area_ratio_fov

    输出：6 个 csv 文件到 out_dir，命名 distribution_overlap_<pair>_<feature>.csv
    返回：所有结果 dict 列表。
    """
    out_dir = Path(out_dir)
    results = []

    pairs = [
        # (pair_name, src_nc_csv, src_nc_col, tgt_nc_csv, tgt_nc_col,
        #             src_ar_csv, src_ar_col, tgt_ar_csv, tgt_ar_col)
        (
            "brats_ham",
            brats_ncomp_csv, "n_components", ham_ncomp_csv,  "n_components",
            brats_area_csv,  "area_ratio_brain", ham_area_csv,  "area_ratio_ham",
        ),
        (
            "brats_cbis",
            brats_ncomp_csv, "n_components", cbis_ncomp_csv, "n_components",
            brats_area_csv,  "area_ratio_brain", cbis_area_csv, "area_ratio_breast",
        ),
        (
            "brats_idrid",
            brats_ncomp_csv, "n_components", idrid_ncomp_csv, "n_components",
            brats_area_csv,  "area_ratio_brain", idrid_area_csv, "area_ratio_fov",
        ),
    ]

    for (pair_name,
         snc_csv, snc_col, tnc_csv, tnc_col,
         sar_csv, sar_col, tar_csv, tar_col) in pairs:

        # n_components
        try:
            r = compute_pair_overlap(
                source_csv=snc_csv, target_csv=tnc_csv,
                feature="n_components",
                source_col=snc_col, target_col=tnc_col,
                pair_name=pair_name,
                out_dir=str(out_dir),
            )
            results.append(r)
        except Exception as e:
            print(f"[distribution_overlap] {pair_name} n_components 跳过: {e}")

        # area_ratio
        try:
            r = compute_pair_overlap(
                source_csv=sar_csv, target_csv=tar_csv,
                feature="area_ratio",
                source_col=sar_col, target_col=tar_col,
                pair_name=pair_name,
                out_dir=str(out_dir),
            )
            results.append(r)
        except Exception as e:
            print(f"[distribution_overlap] {pair_name} area_ratio 跳过: {e}")

    return results


# ============================================================
# Entry point（最小 CLI，支持单对计算）
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "OVL/BC 固化落盘 — 钉死 bin 方案保证可复现\n"
            "bin 方案:\n"
            "  area_ratio  : linear_100_[0,1]  (100 等宽 bins over [0,1])\n"
            "  n_components: log50_[0.5,3000]  (50 对数 bins over [0.5,3000])\n"
            "输出 csv 列: pair/feature/n_bins/bin_scheme/OVL/BC/n_source/n_target\n"
            "\n"
            "用法（单对）:\n"
            "  python code/distribution_overlap.py \\\n"
            "    --source-csv results/ncomp_brats.csv --source-col n_components \\\n"
            "    --target-csv results/ncomp_ham.csv   --target-col n_components \\\n"
            "    --feature n_components --pair brats_ham --out-dir results\n"
            "\n"
            "用法（跑全部三对）:\n"
            "  python code/distribution_overlap.py --run-all --out-dir results\n"
            "  （需要 results/ncomp_brats.csv, ncomp_ham.csv 已生成）"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _root = Path(__file__).resolve().parent.parent
    _res  = _root / "results"

    parser.add_argument("--source-csv",  default=None, help="source csv 路径")
    parser.add_argument("--source-col",  default=None, help="source 列名")
    parser.add_argument("--target-csv",  default=None, help="target csv 路径")
    parser.add_argument("--target-col",  default=None, help="target 列名")
    parser.add_argument(
        "--feature",
        choices=["area_ratio", "n_components"],
        default="n_components",
        help="特征名（决定 bin 方案）",
    )
    parser.add_argument("--pair",    default="brats_ham", help="配对名称（用于输出文件名）")
    parser.add_argument("--out-dir", default=str(_res),   help="输出目录")
    parser.add_argument(
        "--run-all",
        action="store_true",
        help=(
            "跑全部三对 × 两特征（需要 ncomp_brats.csv + ncomp_ham.csv 已生成）。\n"
            "HAM area_ratio 对应列 = lesion_features_ham.csv size_px（除以 64^2 在脚本内计算）。"
        ),
    )

    args = parser.parse_args()

    if args.run_all:
        # HAM area_ratio: lesion_features_ham.csv 无 area_ratio 列，
        # 用 size_px / 64^2 替代（img_size=64 对齐 BraTS 64px 口径）。
        # 临时计算并写入 tmp csv，再调用 compute_pair_overlap。
        ham_feat_csv = _res / "lesion_features_ham.csv"
        ham_area_tmp = _res / "_tmp_ham_area_ratio.csv"

        if ham_feat_csv.exists():
            with open(ham_feat_csv, newline="") as f:
                ham_rows = list(csv.DictReader(f))
            with open(ham_area_tmp, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["filename", "area_ratio_ham"])
                w.writeheader()
                for r in ham_rows:
                    spx = r.get("size_px", "nan")
                    try:
                        fv = float(spx)
                        ar = fv / (64.0 * 64.0)  # 64^2 分母（与 BraTS 同坐标系）
                    except (TypeError, ValueError):
                        ar = float("nan")
                    w.writerow({
                        "filename":       r["filename"],
                        "area_ratio_ham": f"{ar:.6f}" if np.isfinite(ar) else "nan",
                    })
            print(f"[distribution_overlap] HAM area_ratio tmp: {ham_area_tmp}")
        else:
            print(f"[distribution_overlap] WARNING: {ham_feat_csv} 不存在，跳过 HAM area_ratio")
            ham_area_tmp = None

        run_all_pairs(
            brats_ncomp_csv=str(_res / "ncomp_brats.csv"),
            brats_area_csv=str(_res / "brats_brain_px.csv"),
            ham_ncomp_csv=str(_res / "ncomp_ham.csv"),
            ham_area_csv=str(ham_area_tmp) if ham_area_tmp else "",
            cbis_ncomp_csv=str(_res / "lesion_features_cbis_mass.csv"),
            cbis_area_csv=str(_res / "lesion_features_cbis_mass.csv"),
            idrid_ncomp_csv=str(_res / "lesion_features_idrid.csv"),
            idrid_area_csv=str(_res / "lesion_features_idrid.csv"),
            out_dir=args.out_dir,
        )

    else:
        if not args.source_csv or not args.target_csv:
            parser.error(
                "单对模式需传 --source-csv / --target-csv；"
                "或用 --run-all 跑全部三对"
            )
        compute_pair_overlap(
            source_csv=args.source_csv,
            target_csv=args.target_csv,
            feature=args.feature,
            source_col=args.source_col,
            target_col=args.target_col,
            pair_name=args.pair,
            out_dir=args.out_dir,
        )
