"""
make_split_abide1.py
=====================
Patient-level split for HyperGALE / ABIDE-I / Schaefer400 泳道。

【偏离论文声明（红线合规注释）】
  HyperGALE 论文原用 StratifiedShuffleSplit(test_size=0.1, random_state=42)
  stratify by site，repeat_time=10（同一 split 跑 10 次）。
  本脚本改为同时输出：
    1. 官方对齐 90/10 StratifiedShuffleSplit（stratify=site，random_state=42）
       → fc.py / dataloader.py 兼容格式，供 train_hypergale.py 走官方 split 路径。
    2. 5-fold StratifiedKFold（stratify=DX label，random_state=112078）
       → 与 BrainGB 泳道对齐，Gate2 比较用。
  改用 ABIDE-I 后，被试集是 fc_large_data.npy 里实际成功的被试（871 QC pass 的子集），
  通过 inner-join（abide1_schaefer400_meta.csv 的 sub_id 列）与 BrainGB split 对齐。

【inner-join 对齐逻辑】
  BrainGB 泳道用的是 CC200 atlas，被试集可能与 Schaefer400 略有差异
  （同 cohort ABIDE-I QC pass，但若某被试 CC200 .1D 存在而 func_preproc 缺失则不同）。
  本脚本只处理 abide1_schaefer400_meta.csv（download_build_fc_abide1_schaefer400.py 产出），
  即实际有 Schaefer400 FC 的被试。两泳道的 split 通过 sub_id 做 inner-join 对比
  （数字核查留给主线 analyst，本脚本不做跨泳道 assert）。

运行（主线 HPC）：
  python src/hypergale_lane/make_split_abide1.py \\
      --meta /gpfs/work/bio/jiayu2403/hyperfid/data/external/abide1_schaefer400/abide1_schaefer400_meta.csv \\
      --output-dir /gpfs/work/bio/jiayu2403/hyperfid/data/external/abide1_schaefer400/splits
"""

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedShuffleSplit, StratifiedKFold

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_META = _ROOT / "data" / "external" / "abide1_schaefer400" / "abide1_schaefer400_meta.csv"
DEFAULT_OUTPUT_DIR = _ROOT / "data" / "external" / "abide1_schaefer400" / "splits"

# ── 官方超参（HyperGALE dataloader.py 反推）
OFFICIAL_TEST_SIZE  = 0.1   # fc_abide2.yaml test_set: 0.1
OFFICIAL_RANDOM_STATE = 42  # dataloader.py StratifiedShuffleSplit random_state=42

# ── BrainGB 对齐超参
BRAINGB_SEED    = 112078  # BrainGB example_main.py --seed 默认值
BRAINGB_N_FOLDS = 5       # BrainGB k_fold_splits=5


def make_official_split(
    meta_df: pd.DataFrame,
    test_size: float = OFFICIAL_TEST_SIZE,
    random_state: int = OFFICIAL_RANDOM_STATE,
) -> pd.DataFrame:
    """
    官方对齐 split：StratifiedShuffleSplit on site，90/10。
    stratify by site（对齐 HyperGALE dataloader.py: split.split(graph_data_list, site)）。

    若某 site 样本数 < 2 导致 stratify 失败，自动降级为 stratify by label。
    """
    X = np.arange(len(meta_df))
    y_site = meta_df["site_id"].values

    # 检查 site 分布是否允许 stratify（每 site 至少 2 样本）
    site_counts = pd.Series(y_site).value_counts()
    min_site_count = site_counts.min()

    if min_site_count < 2:
        logger.warning(
            "site %s 只有 %d 样本，StratifiedShuffleSplit by site 可能失败，"
            "降级为 stratify by label",
            site_counts.idxmin(), min_site_count,
        )
        y_stratify = meta_df["label"].values.astype(int)
    else:
        y_stratify = y_site

    splitter = StratifiedShuffleSplit(
        n_splits=1,
        test_size=test_size,
        train_size=1.0 - test_size,
        random_state=random_state,
    )
    train_idx, test_idx = next(splitter.split(X, y_stratify))

    split_col = pd.Series(["train"] * len(meta_df))
    split_col.iloc[test_idx] = "test"

    result = meta_df.copy().reset_index(drop=True)
    result["split"] = split_col.values
    result["split_idx"] = np.arange(len(result))

    return result, train_idx, test_idx


def make_kfold_split(
    meta_df: pd.DataFrame,
    n_splits: int = BRAINGB_N_FOLDS,
    random_state: int = BRAINGB_SEED,
) -> pd.DataFrame:
    """
    BrainGB 对齐：5-fold StratifiedKFold by DX label（label=0/1）。
    输出 fold_0..fold_{n-1} 列，值为 'train' / 'test'。
    """
    X = np.arange(len(meta_df))
    y = meta_df["label"].values.astype(int)

    kf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=random_state)
    result = meta_df.copy().reset_index(drop=True)

    for fold, (train_idx, test_idx) in enumerate(kf.split(X, y)):
        col = f"fold_{fold}"
        split_col = pd.Series(["train"] * len(result))
        split_col.iloc[test_idx] = "test"
        result[col] = split_col.values

        logger.info(
            "Fold %d: train=%d / test=%d | test ASD=%d TD=%d",
            fold, len(train_idx), len(test_idx),
            int(y[test_idx].sum()), int((y[test_idx] == 0).sum()),
        )

    return result


def validate_no_leakage(df: pd.DataFrame, split_col: str, id_col: str = "sub_id") -> None:
    """
    验证同 sub_id 不同时出现在 train 和 test。
    Gate1 红线：patient-level split 无泄漏。
    """
    train_subs = set(df[df[split_col] == "train"][id_col])
    test_subs  = set(df[df[split_col] == "test"][id_col])
    overlap = train_subs & test_subs
    assert len(overlap) == 0, (
        f"泄漏！sub_id 同时出现在 train 和 test: {overlap}"
    )
    logger.info(
        "无泄漏验证 PASS [%s]: train=%d, test=%d",
        split_col, len(train_subs), len(test_subs),
    )


def main(meta_path: Path, output_dir: Path) -> None:
    if not meta_path.exists():
        logger.error(
            "meta CSV 不存在: %s\n"
            "请先运行 download_build_fc_abide1_schaefer400.py",
            meta_path,
        )
        import sys; sys.exit(1)

    meta_df = pd.read_csv(meta_path)
    logger.info("加载 meta: %d subjects", len(meta_df))
    logger.info(
        "label 分布: ASD=%d, TD=%d",
        int((meta_df["label"] == 1.0).sum()),
        int((meta_df["label"] == 0.0).sum()),
    )
    logger.info("site 分布:\n%s", meta_df["site_id"].value_counts().to_string())

    # 确保 sub_id 无重复（patient-level 前提）
    if meta_df["sub_id"].duplicated().any():
        n_dup = meta_df["sub_id"].duplicated().sum()
        logger.warning("发现 %d 个重复 sub_id，保留首条", n_dup)
        meta_df = meta_df.drop_duplicates(subset=["sub_id"], keep="first").reset_index(drop=True)

    output_dir.mkdir(parents=True, exist_ok=True)

    # ── 1. 官方对齐 90/10 split
    split_df, train_idx, test_idx = make_official_split(meta_df)
    validate_no_leakage(split_df, split_col="split")

    train_df = split_df[split_df["split"] == "train"]
    test_df  = split_df[split_df["split"] == "test"]
    logger.info(
        "90/10 split: train=%d (ASD=%d, TD=%d) | test=%d (ASD=%d, TD=%d)",
        len(train_df),
        int((train_df["label"] == 1.0).sum()),
        int((train_df["label"] == 0.0).sum()),
        len(test_df),
        int((test_df["label"] == 1.0).sum()),
        int((test_df["label"] == 0.0).sum()),
    )

    split_path = output_dir / "split_90_10.csv"
    split_df.to_csv(split_path, index=False)
    logger.info("90/10 split → %s", split_path)

    # ── 2. BrainGB 对齐 5-fold split
    kfold_df = make_kfold_split(meta_df)

    # 验证每折无泄漏
    for fold in range(BRAINGB_N_FOLDS):
        validate_no_leakage(kfold_df, split_col=f"fold_{fold}")

    kfold_path = output_dir / "split_5fold.csv"
    kfold_df.to_csv(kfold_path, index=False)
    logger.info("5-fold split → %s", kfold_path)

    logger.info("所有 split 完成，无泄漏验证 PASS。")
    logger.info("后续：python src/hypergale_lane/train_hypergale.py --fc-path <fc_large_data.npy>")


def parse_args():
    p = argparse.ArgumentParser(
        description="Patient-level split for HyperGALE ABIDE-I Schaefer400"
    )
    p.add_argument(
        "--meta", type=Path, default=DEFAULT_META,
        help="abide1_schaefer400_meta.csv 路径（download_build_fc_abide1_schaefer400.py 产出）",
    )
    p.add_argument(
        "--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
        help="split CSV 输出目录",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    main(meta_path=args.meta, output_dir=args.output_dir)
