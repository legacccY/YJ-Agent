"""
download_build_fc_abide1_schaefer400.py
========================================
ABIDE-I func_preproc → Schaefer400 FC → HyperGALE 期望 fc_large_data.npy

【偏离论文声明（红线合规注释）】
  原 HyperGALE 论文使用 ABIDE-II / Schaefer400 / n≈812。
  本脚本改用 ABIDE-I，原因：
    1. ABIDE-II Schaefer400 预提取时序在 FCP-INDI S3 不存在（open issue #2/#3 未回复）。
    2. ABIDE-II func_preproc 自跑 fMRIPrep 需 >1TB 空间，HPC 不可行。
    3. ABIDE-I 可经 nilearn.datasets.fetch_abide_pcp 免登录直下（QC=871 被试 ≈ 论文 n）。
    4. 与 BrainGB 泳道同 cohort，Gate2 统一可比。
  FC 方法（LedoitWolf correlation / Schaefer400 / nilearn 标准管道）完全对齐论文，
  仅 cohort 换为 ABIDE-I。

【流式处理策略（关键）】
  func_preproc.nii.gz 单被试 ~50MB，871 被试 ~43GB，解压 .nii ~170GB。
  流式：fetch → NiftiLabelsMasker 提时序（无需落盘 .nii）→ LedoitWolf FC → 累积。
  nilearn 的 fetch_abide_pcp 可仅下载 func_preproc，NiftiLabelsMasker 接受 .nii.gz 直接
  fit_transform，无需手动解压。峰值显存约 200MB（单 .nii.gz 内存映射）。

【HyperGALE 期望的 .npy 格式（source/dataset/fc.py 反向推导）】
  fc_data = np.load(path, allow_pickle=True).item()
  → fc_data["corr"]  : np.ndarray shape (N, 400, 400) float32
  → fc_data["label"] : np.ndarray shape (N,)           float32，0=TD / 1=ASD
  → fc_data["site"]  : np.ndarray shape (N,)            str，site ID（供 split stratify）

【label 编码（与 build_fc_abide2.py 一致）】
  DX_GROUP=1 → ASD → label=1.0
  DX_GROUP=2 → TD  → label=0.0
  HyperGALE Train.py 用 BCEWithLogitsLoss，target 需 float。

【官方 FC 超参（researcher 已核 HyperGALE 论文）】
  atlas  : Schaefer400 / yeo_networks=7 / resolution_mm=2
  masker : NiftiLabelsMasker(standardize='zscore_sample', resampling_target='data')
  FC     : ConnectivityMeasure(kind='correlation', cov_estimator=LedoitWolf())
  → resampling_target='data' 把 2mm atlas 自动 resample 到 func_preproc 的 3mm 空间

【sub_id 抓取（稳健正则，避免 261 丢失 bug）】
  nilearn phenotypic 的 SUB_ID 是整型（或含前导零的字符串）。
  文件路径中 sub_id 可能有前导零（如 0050002）。
  统一用 int() 去前导零对齐。
  braingb_lane/build_graphs.py 用 re.search(r"(\\d{5,7})", name) 从文件名抓 sub_id，
  本脚本用 nilearn 返回的文件路径列表（已与 phenotypic 一一对应），
  不依赖文件名解析，天然避免 261 丢失坑。

运行命令（主线 HPC 执行）：
  python src/hypergale_lane/download_build_fc_abide1_schaefer400.py \\
      --data-dir /gpfs/work/bio/jiayu2403/hyperfid/data/external/abide1_schaefer400 \\
      --output   /gpfs/work/bio/jiayu2403/hyperfid/data/external/abide1_schaefer400/fc_large_data.npy \\
      --max-subjects 0

调试（前 5 被试）：
  python src/hypergale_lane/download_build_fc_abide1_schaefer400.py \\
      --data-dir /tmp/abide1_test \\
      --output   /tmp/abide1_test/fc_large_data.npy \\
      --max-subjects 5
"""

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── 默认路径（HPC 用 --data-dir / --output 覆盖）
_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = _ROOT / "data" / "external" / "abide1_schaefer400"
DEFAULT_OUTPUT   = DEFAULT_DATA_DIR / "fc_large_data.npy"

# ── 官方超参（researcher 已核 HyperGALE 论文，禁私改）
N_ROIS        = 400   # Schaefer400
YEO_NETWORKS  = 7     # Schaefer atlas yeo_networks 参数
ATLAS_RES_MM  = 2     # atlas 分辨率 mm（masker 内 resample 到 func_preproc 3mm）
PIPELINE      = "cpac"           # HyperGALE 论文预处理 pipeline
STRATEGY      = "filt_global"    # bandpass + GSR（cpac/filt_global 子集）


def fetch_atlas():
    """
    获取 Schaefer400 atlas（yeo_networks=7, resolution_mm=2）。
    首次调用会缓存到 nilearn data dir，后续离线。
    """
    from nilearn.datasets import fetch_atlas_schaefer_2018
    atlas = fetch_atlas_schaefer_2018(
        n_rois=N_ROIS,
        yeo_networks=YEO_NETWORKS,
        resolution_mm=ATLAS_RES_MM,
    )
    logger.info("Schaefer400 atlas 加载: %s", atlas.maps)
    return atlas


def make_masker(atlas_maps):
    """
    构建 NiftiLabelsMasker（对齐论文预处理意图）。

    standardize='zscore_sample'：对每个 ROI 时序做 z-score（对齐 nilearn 标准）。
    resampling_target='data'：把 2mm atlas 自动 resample 到 func_preproc 的 3mm 空间，
                              无需手动 resample。
    """
    from nilearn.maskers import NiftiLabelsMasker
    masker = NiftiLabelsMasker(
        labels_img=atlas_maps,
        standardize="zscore_sample",
        resampling_target="data",
    )
    return masker


def build_fc_from_timeseries(ts: np.ndarray) -> np.ndarray:
    """
    时序 (T, 400) → LedoitWolf full correlation (400, 400) float32。

    对齐 HyperGALE 论文设置：
      ConnectivityMeasure(kind='correlation', cov_estimator=LedoitWolf())
    """
    from nilearn.connectome import ConnectivityMeasure
    from sklearn.covariance import LedoitWolf

    conn = ConnectivityMeasure(
        kind="correlation",
        cov_estimator=LedoitWolf(),
    )
    fc = conn.fit_transform([ts])[0]  # (400, 400)
    return fc.astype(np.float32)


def download_and_build_fc(
    data_dir: Path,
    output_path: Path,
    max_subjects: int = 0,
) -> None:
    """
    核心流程：fetch → 逐被试提时序 → LedoitWolf FC → 累积 → 保存。

    流式策略：
      nilearn fetch_abide_pcp 配 derivatives=['func_preproc'] 返回 .nii.gz 路径列表。
      NiftiLabelsMasker 直接 fit_transform(.nii.gz)，内存映射单被试 ~200MB，
      不需要解压整个数据集。
      处理完每个被试后 .nii.gz 可选删除（--delete-raw 控制），
      但 nilearn 会把文件放在 data_dir cache 里，是否删除影响断点续跑。
      默认不删（保留供检查），生产环境加 --delete-raw 节省磁盘。

    参数
    ----
    data_dir     : nilearn cache 目录（会存 func_preproc .nii.gz + atlas）
    output_path  : 输出 fc_large_data.npy
    max_subjects : 调试用，0=全量（≈871 被试 QC pass）
    """
    try:
        from nilearn import datasets as nl_datasets
    except ImportError:
        logger.error("nilearn 未安装。请先: pip install nilearn")
        sys.exit(1)

    data_dir.mkdir(parents=True, exist_ok=True)

    # ── Step 1: fetch phenotypic + func_preproc 文件列表
    # quality_checked=True → nilearn 内置 QC，保留 ~871 被试（对齐论文 n）
    # derivatives=['func_preproc'] → 只下 func_preproc，不下时序 .1D
    # band_pass_filtering=True + global_signal_regression=True → cpac/filt_global 策略
    logger.info("fetch_abide_pcp 开始（cpac/filt_global/func_preproc, quality_checked=True）")
    logger.info("⚠️  首次运行约下载 43GB，按网速可能需要数小时。已有缓存会跳过。")

    fetch_result = nl_datasets.fetch_abide_pcp(
        data_dir=str(data_dir),
        pipeline=PIPELINE,
        band_pass_filtering=True,
        global_signal_regression=True,
        derivatives=["func_preproc"],
        # smoke(max_subjects>0) 时只下 N 个，避免烟测就拖全 43GB；0=全量
        n_subjects=(max_subjects if max_subjects and max_subjects > 0 else None),
        quality_checked=True,     # 对齐 BrainGB / 论文 QC 设置
        verbose=1,
    )

    pheno = fetch_result.phenotypic  # pandas DataFrame
    func_files = fetch_result.func_preproc  # list of .nii.gz 路径（str）

    logger.info("Phenotypic: %d 被试，列: %s", len(pheno), list(pheno.columns[:8]))
    logger.info("func_preproc 文件数: %d", len(func_files))

    # 保存 phenotypic CSV（供 make_split.py 和调试用）
    pheno_path = data_dir / "phenotypic.csv"
    pheno.to_csv(pheno_path, index=False)
    logger.info("Phenotypic 已保存: %s", pheno_path)

    # ── 验证对齐（nilearn 保证 func_files 与 pheno 行顺序一致）
    if len(func_files) != len(pheno):
        logger.warning(
            "func_files(%d) 与 phenotypic(%d) 行数不一致，将按 min 对齐",
            len(func_files), len(pheno),
        )
        n = min(len(func_files), len(pheno))
        func_files = func_files[:n]
        pheno = pheno.iloc[:n].reset_index(drop=True)

    # ── 调试截断
    if max_subjects and max_subjects > 0:
        logger.info("调试模式：只处理前 %d 被试", max_subjects)
        func_files = func_files[:max_subjects]
        pheno = pheno.iloc[:max_subjects].reset_index(drop=True)

    # ── Step 2: 加载 Schaefer400 atlas + 构建 masker
    atlas = fetch_atlas()
    masker = make_masker(atlas.maps)
    # 预 fit masker（不需要数据，只加载 atlas，避免每个被试重复加载）
    masker.fit()
    logger.info("NiftiLabelsMasker 已 fit（Schaefer400, 2mm→3mm resample）")

    # ── Step 3: 逐被试流式提时序 + 算 FC
    corr_list  = []
    label_list = []
    site_list  = []
    sub_id_list = []

    n_total = len(func_files)
    n_skip  = 0

    for i, (func_file, (_, row)) in enumerate(zip(func_files, pheno.iterrows())):
        if i % 50 == 0:
            logger.info("处理进度: %d / %d（已成功 %d，跳过 %d）",
                        i, n_total, len(corr_list), n_skip)

        # ── sub_id 稳健提取（int 去前导零，对齐 braingb_lane 惯例）
        # 避免 261 丢失 bug：直接用 nilearn 给的行顺序对齐，不做文件名解析
        try:
            sub_id = str(int(row["SUB_ID"]))
        except (ValueError, KeyError):
            sub_id = str(row.get("SUB_ID", f"sub_{i:04d}"))

        site_id = str(row.get("SITE_ID", "UNKNOWN"))
        dx_group = int(row.get("DX_GROUP", -1))

        if dx_group not in (1, 2):
            logger.warning("被试 %s DX_GROUP=%s 异常，跳过", sub_id, dx_group)
            n_skip += 1
            continue

        # ── 提时序（NiftiLabelsMasker 直接接受 .nii.gz 路径）
        # 流式关键：transform 内存映射 .nii.gz，不解压到磁盘
        try:
            func_path = str(func_file)
            ts = masker.transform(func_path)  # (T, 400)
        except Exception as e:
            logger.warning("被试 %s 时序提取失败，跳过: %s", sub_id, e)
            n_skip += 1
            continue

        if ts.shape[1] != N_ROIS:
            logger.warning(
                "被试 %s ROI 数 %d != %d，跳过", sub_id, ts.shape[1], N_ROIS
            )
            n_skip += 1
            continue

        if ts.shape[0] < 50:
            logger.warning(
                "被试 %s 时间点数 %d 过少（< 50），跳过", sub_id, ts.shape[0]
            )
            n_skip += 1
            continue

        # ── LedoitWolf FC
        try:
            fc = build_fc_from_timeseries(ts)  # (400, 400) float32
        except Exception as e:
            logger.warning("被试 %s FC 构建失败，跳过: %s", sub_id, e)
            n_skip += 1
            continue

        corr_list.append(fc)
        # label: ASD(DX_GROUP=1)→1.0, TD(DX_GROUP=2)→0.0（对齐 build_fc_abide2.py）
        label_list.append(1.0 if dx_group == 1 else 0.0)
        site_list.append(site_id)
        sub_id_list.append(sub_id)

    logger.info(
        "流式处理完成: 成功 %d / 总 %d（跳过 %d）",
        len(corr_list), n_total, n_skip,
    )

    if len(corr_list) == 0:
        logger.error("无有效 FC 矩阵，请检查 func_preproc 文件。")
        sys.exit(1)

    # ── Step 4: 组装 arrays
    corr_arr  = np.stack(corr_list, axis=0).astype(np.float32)   # (N, 400, 400)
    label_arr = np.array(label_list, dtype=np.float32)            # (N,) float32
    site_arr  = np.array(site_list)                               # (N,) str

    n_asd = int(label_arr.sum())
    n_td  = int((label_arr == 0).sum())
    logger.info(
        "最终统计: N=%d, corr shape=%s, ASD=%d(%.1f%%), TD=%d(%.1f%%), sites=%d",
        corr_arr.shape[0], corr_arr.shape,
        n_asd, 100 * n_asd / len(label_arr),
        n_td,  100 * n_td  / len(label_arr),
        len(set(site_list)),
    )
    logger.info("Sites: %s", sorted(set(site_list)))

    # ── Step 5: 保存 fc_large_data.npy（HyperGALE format）
    # source/dataset/fc.py: np.load(path, allow_pickle=True).item()
    # → dict keys: "corr", "label", "site"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fc_data = {
        "corr":  corr_arr,   # (N, 400, 400) float32
        "label": label_arr,  # (N,) float32，0=TD / 1=ASD
        "site":  site_arr,   # (N,) str，site ID
    }
    np.save(str(output_path), fc_data)
    logger.info("fc_large_data.npy 已保存 → %s", output_path)
    logger.info("文件大小: %.1f MB", output_path.stat().st_size / 1e6)

    # ── Step 6: 保存 meta CSV（供 make_split.py + 调试）
    meta_df = pd.DataFrame({
        "sub_id":   sub_id_list,
        "site_id":  site_list,
        "label":    label_list,
        "dx_group": [1 if l == 1.0 else 2 for l in label_list],
        "fc_idx":   list(range(len(sub_id_list))),  # 对应 fc_large_data.npy 中的行索引
    })
    meta_path = output_path.parent / "abide1_schaefer400_meta.csv"
    meta_df.to_csv(meta_path, index=False)
    logger.info("meta CSV 已保存 → %s", meta_path)

    logger.info("完成。后续步骤：")
    logger.info("  python src/hypergale_lane/make_split_abide1.py --meta %s", meta_path)
    logger.info("  python src/hypergale_lane/train_hypergale.py --fc-path %s", output_path)


def parse_args():
    p = argparse.ArgumentParser(
        description="ABIDE-I func_preproc → Schaefer400 FC → HyperGALE fc_large_data.npy"
    )
    p.add_argument(
        "--data-dir", type=Path, default=DEFAULT_DATA_DIR,
        help="nilearn cache 目录（存 func_preproc .nii.gz 和 phenotypic）",
    )
    p.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT,
        help="输出 fc_large_data.npy 路径（HyperGALE --fc-path 参数）",
    )
    p.add_argument(
        "--max-subjects", type=int, default=0,
        help="调试用：只处理前 N 被试（0=全量 ≈871）",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    download_and_build_fc(
        data_dir=args.data_dir,
        output_path=args.output,
        max_subjects=args.max_subjects,
    )
