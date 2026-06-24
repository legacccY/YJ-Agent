"""
make_split.py
=============
Patient-level split，对齐 HyperGALE 官方设置，输出可复现 CSV。

【HyperGALE 官方 split 策略（source/dataset/dataloader.py 反推）】
  dataloader.py 用 StratifiedShuffleSplit(n_splits=1, test_size=0.1, train_size=0.9,
                                           random_state=42)
  stratify 变量 = site（而非 label）。
  repeat_time=10（在 __main__.py 外循环），每次 random_state=42 → 同一 split 跑 10 次。

【本脚本策略（Gate1 + 红线合规）】
  - 键 = SUB_ID（patient-level，同被试不跨 train/test）。
  - stratify = SITE_ID（对齐官方 dataloader.py：按 site 分层）。
  - 使用 StratifiedShuffleSplit(n_splits=1, test_size=0.1, random_state=42)
    10 次 repeat = 同一 split，与官方一致。
  - 同时输出 site-stratified 5-fold CV（Gate1 补充验证用）。
  - 输出：split_indices.csv（train/test index per subject）。

【红线】
  - 同被试绝不跨 train/test（SUB_ID 级别 split）。
  - 评估集不泄漏：split 基于 subject，不基于 sample。
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
DEFAULT_META = _ROOT / "data" / "external" / "abide2" / "abide2_meta.csv"
DEFAULT_OUTPUT_DIR = _ROOT / "data" / "external" / "abide2" / "splits"

RANDOM_STATE = 42  # 官方 dataloader.py random_state=42
TEST_RATIO = 0.1   # 官方 fc_abide2.yaml test_set: 0.1


def make_stratified_split(
    meta_df: pd.DataFrame,
    test_size: float = TEST_RATIO,
    random_state: int = RANDOM_STATE,
) -> pd.DataFrame:
    """
    官方对齐 split：StratifiedShuffleSplit on site，90/10。

    参数
    ----
    meta_df : 含 sub_id / site_id / label 列

    返回
    ----
    DataFrame 新增 split 列 ("train" / "test")
    """
    X = np.arange(len(meta_df))
    # stratify by site（对齐 dataloader.py 中 split.split(graph_data_list, site)）
    y = meta_df["site_id"].values

    splitter = StratifiedShuffleSplit(
        n_splits=1,
        test_size=test_size,
        train_size=1.0 - test_size,
        random_state=random_state,
    )
    train_idx, test_idx = next(splitter.split(X, y))

    split_col = [""] * len(meta_df)
    for i in train_idx:
        split_col[i] = "train"
    for i in test_idx:
        split_col[i] = "test"

    meta_df = meta_df.copy()
    meta_df["split"] = split_col
    meta_df["split_idx"] = np.arange(len(meta_df))

    return meta_df, train_idx, test_idx


def make_kfold_split(
    meta_df: pd.DataFrame,
    n_splits: int = 5,
    random_state: int = RANDOM_STATE,
) -> pd.DataFrame:
    """
    Gate1 补充验证：site-stratified K-fold（k=5，对齐 BrainGB 官方）。

    返回
    ----
    DataFrame 新增 fold_{k} 列（值为 "train" / "test"）
    """
    X = np.arange(len(meta_df))
    y = meta_df["site_id"].values

    kf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=random_state)
    meta_df = meta_df.copy()
    for fold, (train_idx, test_idx) in enumerate(kf.split(X, y)):
        col = f"fold_{fold}"
        split_col = [""] * len(meta_df)
        for i in train_idx:
            split_col[i] = "train"
        for i in test_idx:
            split_col[i] = "test"
        meta_df[col] = split_col

    return meta_df


def validate_no_leakage(
    meta_df: pd.DataFrame, split_col: str = "split"
) -> None:
    """
    验证同 SUB_ID 不同时出现在 train 和 test。
    Gate1 红线：patient-level split 无泄漏。
    """
    train_subs = set(meta_df[meta_df[split_col] == "train"]["sub_id"])
    test_subs = set(meta_df[meta_df[split_col] == "test"]["sub_id"])
    overlap = train_subs & test_subs
    assert len(overlap) == 0, (
        f"泄漏！以下 SUB_ID 同时出现在 train 和 test: {overlap}"
    )
    logger.info("无泄漏验证 PASS: train=%d subjects, test=%d subjects",
                len(train_subs), len(test_subs))


def main(meta_path: Path, output_dir: Path, n_folds: int = 5) -> None:
    if not meta_path.exists():
        logger.error(
            "abide2_meta.csv 不存在: %s\n"
            "请先运行 build_fc_abide2.py",
            meta_path,
        )
        import sys; sys.exit(1)

    meta_df = pd.read_csv(meta_path)
    logger.info("加载 meta: %d subjects", len(meta_df))
    logger.info("site 分布:\n%s", meta_df["site_id"].value_counts().to_string())
    logger.info(
        "label 分布: ASD=%d, TD=%d",
        int((meta_df["label"] == 1).sum()),
        int((meta_df["label"] == 0).sum()),
    )

    output_dir.mkdir(parents=True, exist_ok=True)

    # ── 官方对齐 90/10 split
    split_df, train_idx, test_idx = make_stratified_split(meta_df)
    validate_no_leakage(split_df, split_col="split")

    split_path = output_dir / "split_90_10.csv"
    split_df.to_csv(split_path, index=False)
    logger.info("90/10 split → %s", split_path)

    # 打印分布
    train_df = split_df[split_df["split"] == "train"]
    test_df = split_df[split_df["split"] == "test"]
    logger.info(
        "Train: %d (ASD=%d, TD=%d) | Test: %d (ASD=%d, TD=%d)",
        len(train_df),
        int((train_df["label"] == 1).sum()),
        int((train_df["label"] == 0).sum()),
        len(test_df),
        int((test_df["label"] == 1).sum()),
        int((test_df["label"] == 0).sum()),
    )

    # ── K-fold split（补充）
    kfold_df = make_kfold_split(meta_df, n_splits=n_folds)
    kfold_path = output_dir / f"split_{n_folds}fold.csv"
    kfold_df.to_csv(kfold_path, index=False)
    logger.info("%d-fold split → %s", n_folds, kfold_path)

    # 验证每折无泄漏
    for fold in range(n_folds):
        validate_no_leakage(kfold_df, split_col=f"fold_{fold}")

    logger.info("所有 split 完成，无泄漏验证 PASS。")


def parse_args():
    p = argparse.ArgumentParser(description="Patient-level split for ABIDE-II")
    p.add_argument("--meta", type=Path, default=DEFAULT_META,
                   help="abide2_meta.csv 路径（build_fc_abide2.py 产出）")
    p.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
                   help="split CSV 输出目录")
    p.add_argument("--n-folds", type=int, default=5,
                   help="K-fold 折数（默认5，对齐 BrainGB 官方）")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    main(
        meta_path=args.meta,
        output_dir=args.output_dir,
        n_folds=args.n_folds,
    )
