"""
make_split_cc200.py
====================
将 BrainGB 的 split_indices.csv（patient-level 5-fold）对齐到
fc_large_data_cc200.npy 的行序，输出 HyperGALE 可用的 split 索引 CSV。

【策略：BrainGB 同 split（Gate2 纯比架构）】
  split_indices.csv 的 fold_0..fold_4 按 SUB_ID 标注 train/test。
  fc_large_data_cc200.npy 的行序由 build_fc_cc200_from_braingb.py 决定
  （= abide.npy 的原始行序，sub_ids 逐行对应）。
  本脚本 inner-join 两者，按 fc_idx 输出：
    split_cc200_5fold.csv：columns = [fc_idx, sub_id, site_id, label, fold_0..fold_4]
    split_cc200_90_10.csv：columns = [fc_idx, sub_id, site_id, label, split]（官方风格备用）

  train_hypergale.py 用 --split-csv 读此文件，bypass vendor StratifiedShuffleSplit，
  直接用 fc_idx 切 train/test（见 train_hypergale.py 说明）。

【inner-join 注意】
  sub_id 统一为 str(int(...)) 去前导零（与 build_fc_cc200_from_braingb.py 一致）。
  若 abide.npy 的某被试不在 split_indices.csv（极少情况，< 5 被试），
  该被试会被 inner-join 排除，并在日志里报告。

运行（HPC/本地，秒级）：
  python src/hypergale_lane/make_split_cc200.py \\
      --meta        data/external/abide1_cc200/abide1_cc200_meta.csv \\
      --split-csv   data/external/abide1/split_indices.csv \\
      --output-dir  data/external/abide1_cc200/splits
"""

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_META      = _ROOT / "data" / "external" / "abide1_cc200" / "abide1_cc200_meta.csv"
DEFAULT_SPLIT_CSV = _ROOT / "data" / "external" / "abide1" / "split_indices.csv"
DEFAULT_OUTPUT_DIR = _ROOT / "data" / "external" / "abide1_cc200" / "splits"

N_FOLDS = 5


def validate_no_leakage(df: pd.DataFrame, fold_col: str, id_col: str = "sub_id") -> None:
    train_subs = set(df[df[fold_col] == "train"][id_col])
    test_subs  = set(df[df[fold_col] == "test"][id_col])
    overlap = train_subs & test_subs
    assert len(overlap) == 0, f"泄漏！{id_col} 同时出现在 train/test [fold={fold_col}]: {overlap}"
    logger.info(
        "无泄漏验证 PASS [%s]: train=%d, test=%d",
        fold_col, len(train_subs), len(test_subs),
    )


def main(meta_path: Path, split_csv_path: Path, output_dir: Path) -> None:
    """
    core: inner-join meta (fc_idx, sub_id) × split_indices (SUB_ID, fold_*) → 对齐 split。
    """
    import sys

    if not meta_path.exists():
        logger.error(
            "meta CSV 不存在: %s\n"
            "请先运行 build_fc_cc200_from_braingb.py",
            meta_path,
        )
        sys.exit(1)

    if not split_csv_path.exists():
        logger.error(
            "split_indices.csv 不存在: %s\n"
            "请确认 data/external/abide1/split_indices.csv 存在（BrainGB 泳道 make_split.py 产出）。",
            split_csv_path,
        )
        sys.exit(1)

    # ── 读 meta（fc_large_data_cc200.npy 行序）
    meta = pd.read_csv(meta_path)
    logger.info("meta: %d 被试", len(meta))
    # sub_id 统一 str，去前导零
    meta["sub_id_key"] = meta["sub_id"].astype(str).apply(
        lambda x: str(int(x)) if x.isdigit() else x
    )

    # ── 读 split_indices.csv（BrainGB patient-level 5-fold）
    split_df = pd.read_csv(split_csv_path, low_memory=False)
    logger.info("split_indices.csv: %d 行，列 fold_*: %s",
                len(split_df),
                [c for c in split_df.columns if c.startswith("fold_")])

    # SUB_ID 统一 str，去前导零
    split_df["sub_id_key"] = split_df["SUB_ID"].astype(str).apply(
        lambda x: str(int(float(x))) if x.replace(".", "").isdigit() else x
    )

    fold_cols = [c for c in split_df.columns if c.startswith("fold_")]
    if not fold_cols:
        logger.error("split_indices.csv 无 fold_* 列，无法对齐 split")
        sys.exit(1)

    # ── inner-join：以 meta 行序为基准
    split_lookup = split_df.set_index("sub_id_key")[fold_cols + ["label"]].to_dict("index")

    matched_fc_idx   = []
    matched_sub_id   = []
    matched_site_id  = []
    matched_label    = []
    fold_assignments = {c: [] for c in fold_cols}

    n_missing = 0
    for _, row in meta.iterrows():
        key = row["sub_id_key"]
        if key not in split_lookup:
            logger.warning("sub_id=%s 在 split_indices.csv 中无对应，跳过", row["sub_id"])
            n_missing += 1
            continue

        split_row = split_lookup[key]
        matched_fc_idx.append(int(row["fc_idx"]))
        matched_sub_id.append(row["sub_id"])
        matched_site_id.append(row["site_id"])
        matched_label.append(row["label"])
        for c in fold_cols:
            fold_assignments[c].append(str(split_row[c]))

    if n_missing > 0:
        logger.warning(
            "%d 被试在 split_indices.csv 无对应（inner-join 排除），"
            "已保留 %d 被试",
            n_missing, len(matched_fc_idx),
        )

    if len(matched_fc_idx) == 0:
        logger.error("inner-join 结果为空，请检查 sub_id 格式对齐情况")
        sys.exit(1)

    # ── 构建对齐 split 表
    result = pd.DataFrame({
        "fc_idx":  matched_fc_idx,    # 对应 fc_large_data_cc200.npy 的行索引
        "sub_id":  matched_sub_id,
        "site_id": matched_site_id,
        "label":   matched_label,
    })
    for c in fold_cols:
        result[c] = fold_assignments[c]

    logger.info(
        "对齐结果: %d 被试 (ASD=%d, TD=%d), %d folds",
        len(result),
        int((result["label"] == 1).sum()),
        int((result["label"] == 0).sum()),
        len(fold_cols),
    )

    # ── 验证无泄漏
    for c in fold_cols:
        validate_no_leakage(result, fold_col=c)

    # ── 保存 5-fold 对齐 split
    output_dir.mkdir(parents=True, exist_ok=True)
    split5_path = output_dir / "split_cc200_5fold.csv"
    result.to_csv(split5_path, index=False)
    logger.info("5-fold 对齐 split → %s", split5_path)

    # ── 同时输出 fold_0 作为单次 90/10 split（train_hypergale.py 默认 fold）
    # 以 fold_0 的 train/test 作为官方风格 90/10 备用
    split90 = result[["fc_idx", "sub_id", "site_id", "label", "fold_0"]].copy()
    split90 = split90.rename(columns={"fold_0": "split"})
    split90_path = output_dir / "split_cc200_90_10.csv"
    split90.to_csv(split90_path, index=False)
    logger.info("fold_0 → 90/10 备用 split → %s", split90_path)

    # ── 打印折分布
    for c in fold_cols:
        test_df = result[result[c] == "test"]
        logger.info(
            "%-8s: test=%d (ASD=%d, TD=%d)",
            c,
            len(test_df),
            int((test_df["label"] == 1).sum()),
            int((test_df["label"] == 0).sum()),
        )

    logger.info(
        "完成。train_hypergale.py 使用:\n"
        "  --fc-path  <fc_large_data_cc200.npy>\n"
        "  --split-csv %s",
        split5_path,
    )


def parse_args():
    p = argparse.ArgumentParser(
        description="BrainGB split_indices.csv → HyperGALE cc200 对齐 split CSV"
    )
    p.add_argument(
        "--meta", type=Path, default=DEFAULT_META,
        help="abide1_cc200_meta.csv（build_fc_cc200_from_braingb.py 产出）",
    )
    p.add_argument(
        "--split-csv", type=Path, default=DEFAULT_SPLIT_CSV,
        help="BrainGB split_indices.csv（含 SUB_ID + fold_0..fold_4）",
    )
    p.add_argument(
        "--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
        help="split CSV 输出目录",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    main(
        meta_path=args.meta,
        split_csv_path=args.split_csv,
        output_dir=args.output_dir,
    )
