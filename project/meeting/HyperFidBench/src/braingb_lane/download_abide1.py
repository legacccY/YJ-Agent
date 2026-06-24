"""
download_abide1.py
HyperFidBench Gate1 / BrainGB-ABIDE-I 泳道 / P0-download 步骤

ABIDE-I preprocessed CC200 下载脚本。
用 nilearn.datasets.fetch_abide_pcp 免登录走 S3 HTTP 直下。
下载目标：CPAC pipeline / filt_global / rois_cc200 ROI 时序 + phenotypic CSV。
产出目录：data/external/abide1/
"""

import argparse
import os
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# 项目根目录（此脚本在 src/braingb_lane/ 下，往上两级）
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = REPO_ROOT / "data" / "external" / "abide1"

# S3 备选路径注释（nilearn 内部已封装，直接走 fetch_abide_pcp 即可）
# 手动备选：
#   base = "https://s3.amazonaws.com/fcp-indi/data/Projects/ABIDE_Initiative/Outputs"
#   filt = "cpac/filt_global/rois_cc200/<site_id>_<sub_id>_rois_cc200.1D"
# 如 nilearn 不可用可用 boto3 或 requests 逐 subject 下载。


def download(data_dir: Path, pipeline: str = "cpac", derivatives: list = None) -> dict:
    """
    用 nilearn.datasets.fetch_abide_pcp 下 ABIDE-I preprocessed 数据。

    参数
    ----
    data_dir   : 本地存储根目录
    pipeline   : 'cpac'（官方默认，BrainGB 论文用）
    derivatives: 要下的衍生量，默认 ['rois_cc200']（CC200 atlas ROI 时序）

    返回
    ----
    dict, nilearn 返回对象（含 .phenotypic DataFrame 和 .rois_cc200 路径列表等）
    """
    try:
        from nilearn import datasets as nl_datasets
    except ImportError as e:
        raise ImportError(
            "nilearn 未安装。请先 `pip install nilearn`。"
            "若无法安装 nilearn，可用 S3 直下备选（见脚本顶部注释）。"
        ) from e

    if derivatives is None:
        derivatives = ["rois_cc200"]

    data_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"开始下载 ABIDE-I (pipeline={pipeline}, derivatives={derivatives})")
    logger.info(f"存储路径: {data_dir}")
    logger.info("注意：首次下载约 4-10 GB，按网速可能需要数小时。")

    # fetch_abide_pcp 参数说明：
    #   band_pass_filtering=True  : filt_global（bandpass + GSR）
    #   global_signal_regression=True : GSR（filt_global 子集）
    #   derivatives=['rois_cc200'] : CC200 atlas ROI 均值时序（200 ROI × T 矩阵）
    #   n_subjects=None           : 下全部（~1112 subjects）
    #   quality_checked=True      : nilearn 内置 QC 筛掉劣质被试（保留 ~871）
    fetch_result = nl_datasets.fetch_abide_pcp(
        data_dir=str(data_dir),
        pipeline=pipeline,
        band_pass_filtering=True,
        global_signal_regression=True,
        derivatives=derivatives,
        n_subjects=None,        # 全量
        quality_checked=True,   # 与 BrainGB 论文设置一致（过 QC）
    )

    # phenotypic 含 DX_GROUP / SITE_ID / SUB_ID 等关键列
    pheno = fetch_result.phenotypic
    logger.info(f"Phenotypic 字段: {list(pheno.columns)}")
    logger.info(f"被试总数 (QC pass): {len(pheno)}")
    logger.info(f"ASD={int((pheno['DX_GROUP'] == 1).sum())}  "
                f"TD={int((pheno['DX_GROUP'] == 2).sum())}")

    # 保存 phenotypic 到本地 CSV（方便后续 make_split.py 读取）
    pheno_path = data_dir / "phenotypic.csv"
    pheno.to_csv(pheno_path, index=False)
    logger.info(f"Phenotypic 已保存: {pheno_path}")

    # 打印 ROI 时序路径示例
    roi_key = derivatives[0]  # e.g. 'rois_cc200'
    roi_files = getattr(fetch_result, roi_key, [])
    logger.info(f"ROI 时序文件数: {len(roi_files)}")
    if roi_files:
        logger.info(f"示例路径: {roi_files[0]}")

    return fetch_result


def main():
    parser = argparse.ArgumentParser(description="下载 ABIDE-I preprocessed (CC200)")
    parser.add_argument(
        "--data_dir",
        type=str,
        default=str(DEFAULT_DATA_DIR),
        help="本地存储目录（默认 data/external/abide1/）",
    )
    parser.add_argument(
        "--pipeline",
        type=str,
        default="cpac",
        choices=["cpac", "ccs", "dpabi", "niak"],
        help="预处理 pipeline，默认 cpac（BrainGB 论文用）",
    )
    parser.add_argument(
        "--derivatives",
        type=str,
        nargs="+",
        default=["rois_cc200"],
        help="要下的 atlas ROI 时序，默认 ['rois_cc200']；"
             "Gate1 加分项可加 'rois_aal' 'rois_schaefer200parcel7networks'",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    fetch_result = download(data_dir, pipeline=args.pipeline, derivatives=args.derivatives)
    logger.info("下载完成。")
    return fetch_result


if __name__ == "__main__":
    main()
