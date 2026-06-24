"""
build_fc_abide2.py
==================
ABIDE-II 时序 → Schaefer400 FC 矩阵 → HyperGALE 期望的 .npy 格式。

补充 HyperGALE repo open issue #2/#3（fc_large_data.npy 预处理脚本缺失）。

【HyperGALE 期望的 .npy 格式（source/dataset/fc.py 反向推导）】
  fc_data = np.load(path, allow_pickle=True).item()
  → fc_data["corr"]  : np.ndarray shape (N, 400, 400) float32，FC 矩阵
  → fc_data["label"] : np.ndarray shape (N,)           float32，0=TD / 1=ASD
  → fc_data["site"]  : list[str] 或 np.ndarray[str]，长度 N，site ID 字符串
    （construct_hyperaph.py 中 set(site) 用于映射，必须可 hash）

【FC 构建方法（官方设置）】
  - Atlas: Schaefer400（nilearn fetch_atlas_schaefer_2018, n_rois=400）
  - 相关估计: Ledoit-Wolf shrinkage full correlation
    → nilearn.connectome.ConnectivityMeasure(
          kind='correlation', estimator=LedoitWolf())
  - 节点特征 = FC 行向量（400 维），即 corr[i] 的每行

【数据源】
  ABIDE-II 时序文件（.1D 格式，每行一个时间点，每列一个 ROI）
  位于 data/external/abide2/rois_schaefer400/
  Phenotypic CSV: data/external/abide2/Phenotypic_V1_0b_preprocessed1.csv
  DX_GROUP 列: 1=ASD, 2=TD（ABIDE 标准编码）→ 转换为 1=ASD, 0=TD

【label 编码】
  HyperGALE Train.py 用 BCEWithLogitsLoss，target 需 float：
    ASD(DX_GROUP=1) → label=1.0
    TD(DX_GROUP=2)  → label=0.0
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

# ── 默认路径
_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ABIDE2_DIR = _ROOT / "data" / "external" / "abide2"
DEFAULT_OUTPUT = _ROOT / "data" / "external" / "abide2" / "fc_large_data.npy"

N_ROIS = 400  # Schaefer400
ATLAS_NAME = "schaefer_2018"


def load_timeseries(ts_file: Path) -> np.ndarray:
    """
    读取 ABIDE .1D 时序文件。
    .1D 格式：行=时间点，列=ROI，空白分隔。
    返回 shape (T, n_rois) float64。
    """
    return np.loadtxt(str(ts_file))


def build_fc_matrix(timeseries: np.ndarray) -> np.ndarray:
    """
    Ledoit-Wolf shrinkage full correlation。
    输入: (T, n_rois)
    输出: (n_rois, n_rois) float32，对角线=1
    """
    from sklearn.covariance import LedoitWolf
    from nilearn.connectome import ConnectivityMeasure

    conn_measure = ConnectivityMeasure(
        kind="correlation",
        estimator=LedoitWolf(),
    )
    # ConnectivityMeasure.fit_transform 接受 list of (T, n_rois)
    fc = conn_measure.fit_transform([timeseries])[0]  # (n_rois, n_rois)
    return fc.astype(np.float32)


def main(abide2_dir: Path, output_path: Path, max_subjects: int = None) -> None:
    """
    主流程：
    1. 读 Phenotypic CSV → 提取 SUB_ID / DX_GROUP / SITE_ID
    2. 匹配 .1D 时序文件
    3. 逐 subject 算 Ledoit-Wolf FC
    4. 存为 HyperGALE 期望格式
    """
    # ── Step 1: Phenotypic
    pheno_path = abide2_dir / "Phenotypic_V1_0b_preprocessed1.csv"
    if not pheno_path.exists():
        logger.error(
            "Phenotypic CSV 不存在: %s\n"
            "请先运行 download_abide2.py 或手动下载。",
            pheno_path,
        )
        sys.exit(1)

    pheno = pd.read_csv(pheno_path)
    logger.info("Phenotypic shape: %s, 列: %s", pheno.shape, list(pheno.columns[:8]))

    # ABIDE-II phenotypic 列名（官方标准）
    # SUB_ID, SITE_ID, DX_GROUP(1=ASD/2=TD), FILE_ID
    required_cols = ["SUB_ID", "SITE_ID", "DX_GROUP"]
    for col in required_cols:
        if col not in pheno.columns:
            logger.error("Phenotypic CSV 缺少列 %s，实际列: %s", col, list(pheno.columns))
            sys.exit(1)

    # ── Step 2: 匹配时序文件
    ts_dir = abide2_dir / "rois_schaefer400"
    if not ts_dir.exists():
        logger.error(
            "时序目录不存在: %s\n"
            "请先下载 rois_schaefer400 数据。",
            ts_dir,
        )
        sys.exit(1)

    # 文件名格式: {SUB_ID}_rois_schaefer400.1D
    # 或 {FILE_ID}_rois_schaefer400.1D（ABIDE-II 可能用 FILE_ID）
    # 尝试两种命名模式
    ts_files = {f.stem.split("_rois")[0]: f for f in ts_dir.glob("*_rois_schaefer400.1D")}
    logger.info("找到 %d 个时序文件", len(ts_files))

    if len(ts_files) == 0:
        logger.error(
            "ts_dir=%s 中无 *_rois_schaefer400.1D 文件，"
            "请确认下载完成。",
            ts_dir,
        )
        sys.exit(1)

    # ── Step 3: 对齐 phenotypic & 时序
    # ABIDE-II FILE_ID 格式示例: ABIDE2_KKI_0050002
    # 尝试用 SUB_ID 数字部分匹配文件名
    matched_records = []
    for _, row in pheno.iterrows():
        sub_id = str(row["SUB_ID"])
        site_id = str(row["SITE_ID"])
        dx = int(row["DX_GROUP"])  # 1=ASD, 2=TD

        # 尝试直接匹配
        ts_file = None
        if sub_id in ts_files:
            ts_file = ts_files[sub_id]
        else:
            # 尝试 FILE_ID 列（若存在）
            if "FILE_ID" in pheno.columns:
                file_id = str(row.get("FILE_ID", ""))
                if file_id in ts_files:
                    ts_file = ts_files[file_id]
                else:
                    # 部分匹配：文件名含 sub_id 数字
                    for key, f in ts_files.items():
                        if sub_id in key:
                            ts_file = f
                            break

        if ts_file is not None:
            matched_records.append({
                "sub_id": sub_id,
                "site_id": site_id,
                "dx": dx,
                "ts_file": ts_file,
            })

    logger.info("matched %d / %d subjects", len(matched_records), len(pheno))
    if len(matched_records) == 0:
        logger.error(
            "无匹配。文件名样例: %s\n"
            "phenotypic SUB_ID 样例: %s",
            list(ts_files.keys())[:3],
            pheno["SUB_ID"].head(3).tolist(),
        )
        sys.exit(1)

    if max_subjects is not None:
        matched_records = matched_records[:max_subjects]
        logger.info("截断到 %d subjects（调试模式）", max_subjects)

    # ── Step 4: 逐 subject 构建 FC
    corr_list = []
    label_list = []
    site_list = []

    for i, rec in enumerate(matched_records):
        if i % 50 == 0:
            logger.info("处理 %d / %d ...", i, len(matched_records))

        try:
            ts = load_timeseries(rec["ts_file"])  # (T, n_rois)
        except Exception as e:
            logger.warning("跳过 %s，读取失败: %s", rec["sub_id"], e)
            continue

        if ts.shape[1] != N_ROIS:
            logger.warning(
                "跳过 %s，ROI 数 %d != %d",
                rec["sub_id"], ts.shape[1], N_ROIS,
            )
            continue

        fc = build_fc_matrix(ts)  # (400, 400) float32
        corr_list.append(fc)

        # label: ASD(DX_GROUP=1)→1.0, TD(DX_GROUP=2)→0.0
        label = 1.0 if rec["dx"] == 1 else 0.0
        label_list.append(label)
        site_list.append(rec["site_id"])

    if len(corr_list) == 0:
        logger.error("无有效 FC 矩阵，退出。")
        sys.exit(1)

    corr_arr = np.stack(corr_list, axis=0).astype(np.float32)   # (N, 400, 400)
    label_arr = np.array(label_list, dtype=np.float32)           # (N,)
    site_arr = np.array(site_list)                                # (N,) str

    logger.info(
        "最终统计: N=%d, corr shape=%s, ASD=%d, TD=%d, sites=%s",
        corr_arr.shape[0],
        corr_arr.shape,
        int(label_arr.sum()),
        int((label_arr == 0).sum()),
        sorted(set(site_arr)),
    )

    # ── Step 5: 存 .npy（HyperGALE format）
    # fc.py: np.load(path, allow_pickle=True).item()
    # → dict with keys: "corr", "label", "site"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fc_data = {
        "corr": corr_arr,    # (N, 400, 400) float32
        "label": label_arr,  # (N,) float32
        "site": site_arr,    # (N,) str，供 dataloader stratify 用
    }
    np.save(str(output_path), fc_data)
    logger.info("已保存 → %s", output_path)

    # ── Step 6: 保存 subject 元数据（用于 make_split.py）
    meta_df = pd.DataFrame({
        "sub_id": [r["sub_id"] for r in matched_records[:len(corr_list)]],
        "site_id": site_list,
        "dx_group": [r["dx"] for r in matched_records[:len(corr_list)]],
        "label": label_list,
    })
    meta_path = output_path.parent / "abide2_meta.csv"
    meta_df.to_csv(meta_path, index=False)
    logger.info("已保存元数据 → %s", meta_path)


def parse_args():
    p = argparse.ArgumentParser(description="ABIDE-II → HyperGALE fc_large_data.npy")
    p.add_argument(
        "--abide2-dir", type=Path, default=DEFAULT_ABIDE2_DIR,
        help="ABIDE-II 数据根目录（含 rois_schaefer400/ 和 Phenotypic CSV）",
    )
    p.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT,
        help="输出 .npy 路径（HyperGALE fc_path）",
    )
    p.add_argument(
        "--max-subjects", type=int, default=None,
        help="调试用：只处理前 N 个 subject（None=全量）",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    main(
        abide2_dir=args.abide2_dir,
        output_path=args.output,
        max_subjects=args.max_subjects,
    )
