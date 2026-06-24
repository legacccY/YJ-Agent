"""
download_abide2.py
==================
拉取 ABIDE-II 时序数据 + phenotypic 表到 data/external/abide2/。

【重要：ABIDE-I vs ABIDE-II 接口差异】
- nilearn.datasets.fetch_abide_pcp() = ABIDE-I 专用，不支持 ABIDE-II。
- ABIDE-II 无官方 nilearn 接口（截至 nilearn 0.10.x）。
  参见 nilearn issue #3821 / #4032，官方回应"暂无计划"。

【ABIDE-II 获取方式（人工步骤，需主线拍板确认 HPC 下载）】
ABIDE-II 预处理数据托管在 NITRC / FCP-INDI S3：
  s3://fcp-indi/data/Projects/ABIDE2/Outputs/cpac/filt_global/
  - rois_schaefer200/  （Schaefer200 ROI 时序，200 节点）
  - rois_schaefer400/  （Schaefer400 ROI 时序，400 节点）<-- HyperGALE 官方设置
  - rois_aal/
  - rois_cc200/
  Phenotypic: s3://fcp-indi/data/Projects/ABIDE2/Phenotypic_V1_0b_preprocessed1.csv

下载工具（S3 无需 AWS 凭证，公开 bucket）：
  aws s3 sync s3://fcp-indi/data/Projects/ABIDE2/Outputs/cpac/filt_global/rois_schaefer400/ \
      data/external/abide2/rois_schaefer400/ --no-sign-request

  或使用 boto3（本脚本实现，--no-sign-request 等价于 unsigned config）。

【HyperGALE 使用的 ABIDE-II 版本】
  n≈812（ASD=384，TD=428），16 sites，Schaefer400 atlas。
  时序文件命名示例：0050002_rois_schaefer400.1D（每行一个时间点，列为 ROI）。

TODO: 确认 HPC 是否已有 ABIDE-II 缓存（联系 IT 或查 /gpfs/work/bio/shared/）
      若已有，直接 symlink 跳过下载，在 build_fc_abide2.py 中指向已有路径即可。
"""

import argparse
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── 默认路径（HPC 上改用绝对路径或环境变量覆盖）
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[2] / "data" / "external" / "abide2"

# ── S3 公开 bucket 配置（ABIDE-II）
ABIDE2_S3_BUCKET = "fcp-indi"
ABIDE2_S3_PREFIX = "data/Projects/ABIDE2/Outputs/cpac/filt_global/rois_schaefer400"
ABIDE2_PHENOTYPIC_KEY = "data/Projects/ABIDE2/Phenotypic_V1_0b_preprocessed1.csv"


def download_via_boto3(output_dir: Path, pipeline: str = "cpac",
                       strategy: str = "filt_global",
                       atlas: str = "rois_schaefer400",
                       dry_run: bool = False) -> None:
    """
    用 boto3 匿名下载 FCP-INDI S3 上的 ABIDE-II 数据。
    需要安装：pip install boto3

    参数
    ----
    output_dir : 本地保存目录
    pipeline   : 预处理管线（默认 cpac）
    strategy   : 滤波策略（默认 filt_global）
    atlas      : ROI atlas（默认 rois_schaefer400，对应 HyperGALE 官方设置）
    dry_run    : True 时只打印 URL 不下载
    """
    try:
        import boto3
        from botocore import UNSIGNED
        from botocore.config import Config
    except ImportError:
        logger.error("boto3 未安装。请运行: pip install boto3")
        sys.exit(1)

    s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))
    bucket = ABIDE2_S3_BUCKET
    prefix = f"data/Projects/ABIDE2/Outputs/{pipeline}/{strategy}/{atlas}/"

    logger.info(f"扫描 s3://{bucket}/{prefix}")
    paginator = s3.get_paginator("list_objects_v2")
    pages = paginator.paginate(Bucket=bucket, Prefix=prefix)

    atlas_dir = output_dir / atlas
    atlas_dir.mkdir(parents=True, exist_ok=True)

    file_count = 0
    for page in pages:
        for obj in page.get("Contents", []):
            key = obj["Key"]
            filename = Path(key).name
            dest = atlas_dir / filename
            if dest.exists():
                logger.debug(f"已存在，跳过: {filename}")
                continue
            if dry_run:
                logger.info(f"[dry-run] 将下载: s3://{bucket}/{key} -> {dest}")
            else:
                logger.info(f"下载: {filename}")
                s3.download_file(bucket, key, str(dest))
            file_count += 1

    logger.info(f"atlas={atlas} 文件计数: {file_count}")

    # 下载 phenotypic csv
    pheno_dest = output_dir / "Phenotypic_V1_0b_preprocessed1.csv"
    if not pheno_dest.exists():
        if dry_run:
            logger.info(f"[dry-run] 将下载 phenotypic CSV")
        else:
            logger.info("下载 phenotypic CSV...")
            s3.download_file(bucket, ABIDE2_PHENOTYPIC_KEY, str(pheno_dest))


def download_via_awscli_instructions() -> None:
    """打印 AWS CLI 手动下载命令（无需 boto3）。"""
    print("\n" + "=" * 60)
    print("ABIDE-II 手动下载命令（在 HPC terminal 执行）：")
    print("=" * 60)
    print("""
# 1. 安装 AWS CLI（HPC 通常已有）
# aws --version

# 2. 下载 Schaefer400 ROI 时序（约 2GB）
aws s3 sync \\
    s3://fcp-indi/data/Projects/ABIDE2/Outputs/cpac/filt_global/rois_schaefer400/ \\
    /gpfs/work/bio/jiayu2403/hyperfid/data/external/abide2/rois_schaefer400/ \\
    --no-sign-request

# 3. 下载 Phenotypic 文件
aws s3 cp \\
    s3://fcp-indi/data/Projects/ABIDE2/Phenotypic_V1_0b_preprocessed1.csv \\
    /gpfs/work/bio/jiayu2403/hyperfid/data/external/abide2/ \\
    --no-sign-request

# 4. 验证文件数（预期 ~812 个 .1D 文件）
ls /gpfs/work/bio/jiayu2403/hyperfid/data/external/abide2/rois_schaefer400/ | wc -l
""")
    print("=" * 60)


def parse_args():
    p = argparse.ArgumentParser(description="下载 ABIDE-II Schaefer400 时序")
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
                   help="本地输出目录（默认 data/external/abide2/）")
    p.add_argument("--atlas", default="rois_schaefer400",
                   help="ROI atlas（默认 rois_schaefer400，对应 HyperGALE 官方设置）")
    p.add_argument("--dry-run", action="store_true",
                   help="只打印待下载文件，不实际下载")
    p.add_argument("--print-cli", action="store_true",
                   help="打印 AWS CLI 手动下载命令后退出")
    return p.parse_args()


if __name__ == "__main__":
    # Windows spawn 安全守门
    args = parse_args()

    if args.print_cli:
        download_via_awscli_instructions()
        sys.exit(0)

    logger.info(f"输出目录: {args.output_dir}")
    logger.info(
        "注意：nilearn.fetch_abide_pcp() 仅支持 ABIDE-I，"
        "ABIDE-II 无官方 nilearn 接口，本脚本使用 boto3 匿名 S3 下载。"
    )

    download_via_boto3(
        output_dir=args.output_dir,
        atlas=args.atlas,
        dry_run=args.dry_run,
    )

    logger.info("完成。")
    logger.info(
        "后续步骤：运行 build_fc_abide2.py --abide2-dir %s", args.output_dir
    )
