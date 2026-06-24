"""
build_graphs.py
HyperFidBench Gate1 / BrainGB-ABIDE-I 泳道 / P2-connmat 步骤

ROI 时序 (.1D 文件) → Pearson FC 连接矩阵 → BrainGB 期望格式 (abide.npy)

BrainGB load_data_abide 期望（见 vendor/BrainGB/src/dataset/abcd/load_abcd.py）：
    data = np.load("abide.npy", allow_pickle=True).item()
    final_pearson = data["corr"]   # shape: (N_subjects, n_ROI, n_ROI)
    labels        = data["label"]  # shape: (N_subjects,)  值: 1=ASD, 0=TD（见下方注释）

节点特征对齐官方 Adj() transform（vendor/BrainGB/src/dataset/transforms.py）：
    Adj.__call__ 把 edge_attr 重建为 dense adj → data.x = adj
    即每个节点 i 的特征向量 = FC 矩阵第 i 行（connection profile）。
    build_graphs 只需正确保存 corr 矩阵；Adj() transform 由 BrainDataset 在 process 阶段自动调用。

标签约定（DX_GROUP in phenotypic）：
    DX_GROUP=1 → ASD；DX_GROUP=2 → TD
    BrainGB label 约定: ASD=1, TD=0 (二分类)
    → label = (DX_GROUP == 1).astype(int)
"""

import argparse
import logging
import re
from pathlib import Path

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ABIDE_DIR = REPO_ROOT / "data" / "external" / "abide1"
# BrainGB ABIDE 数据目录（BrainDataset 对 ABIDE 的 raw_dir）
DEFAULT_BRAINGB_ABIDE_DIR = REPO_ROOT / "vendor" / "BrainGB" / "examples" / "datasets" / "ABIDE"


def load_roi_timeseries(roi_files: list) -> np.ndarray:
    """
    读取 nilearn 返回的 .1D ROI 时序文件列表。
    .1D 文件格式：行=时间点, 列=ROI（whitespace 分隔）。
    返回: shape (N_subjects, n_ROI, n_timepoints)
    """
    ts_list = []
    for f in roi_files:
        try:
            ts = np.loadtxt(f)  # (n_timepoints, n_ROI)
            ts_list.append(ts.T)  # 转置为 (n_ROI, n_timepoints)
        except Exception as e:
            logger.warning(f"跳过无法读取的文件 {f}: {e}")
            ts_list.append(None)
    return ts_list


def pearson_corr(ts: np.ndarray) -> np.ndarray:
    """
    ROI 时序 (n_ROI, n_timepoints) → Pearson FC 矩阵 (n_ROI, n_ROI)。
    标准 Pearson 相关，无超参争议。
    """
    # np.corrcoef: 对行向量两两算相关
    corr = np.corrcoef(ts)
    # 对角线置 0（自相关无意义，与 BrainGB 其他数据集惯例一致）
    np.fill_diagonal(corr, 0.0)
    # nan 处理：若某 ROI 时序为全常数（方差=0）会产生 nan
    corr = np.nan_to_num(corr, nan=0.0)
    return corr.astype(np.float32)


def build_abide_npy(
    abide_dir: Path,
    braingb_abide_dir: Path,
    sub_id_col: str = "SUB_ID",
    dx_col: str = "DX_GROUP",
    roi_key: str = "rois_cc200",
) -> Path:
    """
    从 nilearn 下载的 ABIDE-I 数据构建 BrainGB 期望的 abide.npy。

    参数
    ----
    abide_dir         : nilearn 下载目录（含 phenotypic.csv）
    braingb_abide_dir : abide.npy 输出目录（BrainGB ABIDE raw_dir）
    sub_id_col        : phenotypic 中被试 ID 列名
    dx_col            : phenotypic 中诊断列名
    roi_key           : 要用的 atlas 名（rois_cc200）

    返回
    ----
    Path, 输出的 abide.npy 路径
    """
    # 读 phenotypic
    pheno_path = abide_dir / "phenotypic.csv"
    if not pheno_path.exists():
        raise FileNotFoundError(
            f"phenotypic.csv 不存在: {pheno_path}\n"
            "请先运行 download_abide1.py。"
        )
    pheno = pd.read_csv(pheno_path)
    logger.info(f"Phenotypic 加载: {len(pheno)} 行, 列: {list(pheno.columns)}")

    # 找 ROI 时序文件
    # nilearn 下载后文件结构：abide_dir/cpac_<pipeline>/<site>/<sub_id>/<sub_id>_rois_cc200.1D
    # 使用 glob 匹配
    roi_pattern = f"**/*_{roi_key}.1D"
    roi_files_found = sorted(abide_dir.glob(roi_pattern))
    if not roi_files_found:
        raise FileNotFoundError(
            f"未找到 {roi_key} 时序文件（pattern={roi_pattern}）在 {abide_dir}。\n"
            "请确认 download_abide1.py 已成功下载。"
        )
    logger.info(f"找到 {len(roi_files_found)} 个 {roi_key} 时序文件")

    # 从文件名提取 sub_id，与 phenotypic 对齐
    # 文件名格式：<site_id>_<sub_id>_rois_cc200.1D
    # 例如：NYU_0050954_rois_cc200.1D → sub_id=50954
    def extract_sub_id(filepath: Path) -> str:
        """从 .1D 文件名提取 SUB_ID（整型字符串，去前导零）

        ABIDE SUB_ID = 5-7 位零填充数字（如 0050272）。直接抓该数字串，
        避免多下划线站点（UM_1 / Leuven_1 / UCLA_1 等）导致 parts[1] 错取 site 后缀。
        """
        name = filepath.stem  # e.g. NYU_0050954_rois_cc200 / UM_1_0050272_rois_cc200
        # 主：抓 5-7 位数字串（atlas 后缀 cc200 的 '200' 仅 3 位，不会误命中）
        m = re.search(r"(\d{5,7})", name)
        if m:
            return str(int(m.group(1)))
        # fallback: 按下划线取 parts[1]
        parts = name.split("_")
        if len(parts) >= 2:
            try:
                return str(int(parts[1]))
            except ValueError:
                pass
        return name

    file_sub_ids = [extract_sub_id(f) for f in roi_files_found]
    file_by_subid = {sid: f for sid, f in zip(file_sub_ids, roi_files_found)}

    # phenotypic SUB_ID 统一化
    pheno_sub_ids = pheno[sub_id_col].astype(str).str.lstrip("0").replace("", "0")

    # 对齐：只保留 phenotypic 和文件都存在的被试
    matched_rows = []
    matched_files = []
    for idx, row in pheno.iterrows():
        sid = str(int(row[sub_id_col])) if not pd.isna(row[sub_id_col]) else None
        if sid and sid in file_by_subid:
            matched_rows.append(row)
            matched_files.append(file_by_subid[sid])

    logger.info(f"Phenotypic-文件匹配: {len(matched_rows)} 对")
    if len(matched_rows) == 0:
        raise RuntimeError("phenotypic 与时序文件无匹配，请检查 SUB_ID 格式。")

    matched_pheno = pd.DataFrame(matched_rows).reset_index(drop=True)

    # 构建 Pearson FC 矩阵
    logger.info("计算 Pearson FC 矩阵中...")
    corr_list = []
    valid_indices = []
    for i, (fp, (_, row)) in enumerate(zip(matched_files, matched_pheno.iterrows())):
        try:
            ts = np.loadtxt(fp)  # (n_timepoints, n_ROI)
            if ts.ndim != 2:
                logger.warning(f"跳过 {fp.name}：维度异常 {ts.shape}")
                continue
            corr = pearson_corr(ts.T)  # 转置 → (n_ROI, n_timepoints)
            corr_list.append(corr)
            valid_indices.append(i)
        except Exception as e:
            logger.warning(f"跳过 {fp.name}：{e}")

    logger.info(f"有效 FC 矩阵数: {len(corr_list)}")
    if len(corr_list) == 0:
        raise RuntimeError("无法构建任何 FC 矩阵，请检查时序文件格式。")

    corr_array = np.stack(corr_list, axis=0)  # (N, n_ROI, n_ROI)
    logger.info(f"FC 矩阵 shape: {corr_array.shape}")

    # 标签：DX_GROUP=1→ASD(label=1)；DX_GROUP=2→TD(label=0)
    valid_pheno = matched_pheno.iloc[valid_indices].reset_index(drop=True)
    labels = (valid_pheno[dx_col] == 1).astype(int).values
    logger.info(f"标签分布: ASD={int(labels.sum())}  TD={int((labels == 0).sum())}")

    # 保存 BrainGB 格式 abide.npy
    braingb_abide_dir.mkdir(parents=True, exist_ok=True)
    output_path = braingb_abide_dir / "abide.npy"

    data_dict = {
        "corr": corr_array,   # (N, n_ROI, n_ROI)
        "label": labels,       # (N,)  int, 1=ASD, 0=TD
        # 额外保存 sub_ids 供 make_split.py 读取（不影响 BrainGB 加载）
        "sub_ids": valid_pheno[sub_id_col].values,
        "site_ids": valid_pheno["SITE_ID"].values if "SITE_ID" in valid_pheno.columns else np.array([]),
    }
    np.save(str(output_path), data_dict)
    logger.info(f"abide.npy 已保存: {output_path}")

    # 同时保存一份方便 make_split.py 使用的 phenotypic 子集
    split_pheno_path = braingb_abide_dir / "split_phenotypic.csv"
    valid_pheno.to_csv(split_pheno_path, index=False)
    logger.info(f"split_phenotypic.csv 已保存: {split_pheno_path}")

    return output_path


def main():
    parser = argparse.ArgumentParser(description="构建 ABIDE-I BrainGB 格式 FC 图 (abide.npy)")
    parser.add_argument(
        "--abide_dir",
        type=str,
        default=str(DEFAULT_ABIDE_DIR),
        help="nilearn 下载目录（含 phenotypic.csv 和时序文件）",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default=str(DEFAULT_BRAINGB_ABIDE_DIR),
        help="abide.npy 输出目录（BrainGB ABIDE raw_dir，默认 vendor/.../datasets/ABIDE/）",
    )
    parser.add_argument(
        "--roi_key",
        type=str,
        default="rois_cc200",
        choices=["rois_cc200", "rois_aal"],
        help="atlas ROI 时序文件后缀，默认 rois_cc200（Gate1 BrainGB 泳道用）",
    )
    args = parser.parse_args()

    abide_dir = Path(args.abide_dir)
    output_dir = Path(args.output_dir)
    out_path = build_abide_npy(
        abide_dir=abide_dir,
        braingb_abide_dir=output_dir,
        roi_key=args.roi_key,
    )
    logger.info(f"完成: {out_path}")


if __name__ == "__main__":
    main()
