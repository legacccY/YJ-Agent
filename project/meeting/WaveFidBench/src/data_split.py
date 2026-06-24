"""
data_split.py — WaveFidBench Gate1 数据 split 脚本
服务项目：WaveFidBench (wavefid) Gate1，lever L1 地基

功能：
- slice 模式（Kaggle 烟测）：分层随机 split，显式泄漏警告
- patient 模式（OASIS 正式）：按 subject ID 分组 split，同患者不跨 train/test
输出：train/val/test 索引 csv + 类分布统计 + state.json

用法：
  python src/data_split.py --config configs/gate1_kaggle.yaml --data_root /path/to/data
"""

import argparse
import json
import logging
import os
import re
import warnings
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from sklearn.model_selection import StratifiedShuffleSplit, GroupShuffleSplit

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# 支持的图像后缀
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}


def load_config(config_path: str) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def collect_samples(data_root: Path) -> pd.DataFrame:
    """遍历 data_root 下 4 类子文件夹，收集所有图像路径和标签。"""
    records = []
    for class_dir in sorted(data_root.iterdir()):
        if not class_dir.is_dir():
            continue
        label = class_dir.name
        for img_file in class_dir.iterdir():
            if img_file.suffix.lower() in IMAGE_EXTENSIONS:
                records.append({"filepath": str(img_file), "label": label})
    if len(records) == 0:
        raise ValueError(
            f"data_root={data_root} 下未找到任何图像。"
            f"请确认子文件夹名称（NonDemented/VeryMildDemented/MildDemented/ModerateDemented）。"
        )
    df = pd.DataFrame(records)
    logger.info(f"共收集 {len(df)} 张图像，类别：{sorted(df['label'].unique())}")
    return df


def extract_subject_id(filepath: str, regex: str) -> str:
    """提取 subject ID（OASIS 模式用）。

    OASIS subject ID 在父目录（如 OAS1_0001_MR1/），不在切片文件名里。
    遍历路径各段（文件名 stem + 父目录名）逐段匹配 regex，命中即返回——
    这样 r"^(OAS1_\\d+)" 的 ^ 锚点对每个 path 段成立。
    """
    p = Path(filepath)
    parts = [p.stem] + [parent.name for parent in p.parents if parent.name]
    for part in parts:
        m = re.match(regex, part)
        if m:
            return m.group(1)
    # 无法提取时返回文件名本身（slice fallback，会触发警告）
    return p.stem


def split_slice(df: pd.DataFrame, cfg: dict, out_dir: Path) -> dict:
    """
    分层随机 slice-level split。
    ⚠️ WARNING: slice-level = 泄漏，仅烟测勿报正式数字。
    """
    logger.warning(
        "=====================================================================\n"
        "  ⚠️  slice-level split 模式：同患者切片可能分布在 train/test 两侧。\n"
        "  acc 虚高约 28-45pp（文献 patient-level 66-90% vs slice-level 95-99%）。\n"
        "  此 split 仅作工程烟测，禁止作为正式结果报出！\n"
        "====================================================================="
    )

    train_ratio = cfg["train_ratio"]
    val_ratio = cfg["val_ratio"]
    test_ratio = cfg["test_ratio"]
    assert abs(train_ratio + val_ratio + test_ratio - 1.0) < 1e-6, "比例之和须为 1.0"

    seed = cfg["random_seed"]
    labels = df["label"].values

    # 先切出 test
    sss1 = StratifiedShuffleSplit(n_splits=1, test_size=test_ratio, random_state=seed)
    trainval_idx, test_idx = next(sss1.split(np.zeros(len(labels)), labels))

    # 再从 trainval 切出 val
    val_ratio_adj = val_ratio / (train_ratio + val_ratio)
    sss2 = StratifiedShuffleSplit(n_splits=1, test_size=val_ratio_adj, random_state=seed)
    train_idx, val_idx = next(
        sss2.split(np.zeros(len(trainval_idx)), labels[trainval_idx])
    )
    train_idx = trainval_idx[train_idx]
    val_idx = trainval_idx[val_idx]

    return {"train": train_idx, "val": val_idx, "test": test_idx}


def split_patient(df: pd.DataFrame, cfg: dict, out_dir: Path) -> dict:
    """
    患者级 split（OASIS 正式用）。
    同一 subject ID 的所有切片划入同一 split，防泄漏。
    """
    regex = cfg.get("subject_id_regex", r"^(OAS\d+_\d+)")
    df = df.copy()
    df["subject_id"] = df["filepath"].apply(lambda p: extract_subject_id(p, regex))

    # 统计每个 subject 的主类（取众数）
    subject_label = df.groupby("subject_id")["label"].agg(lambda x: x.mode()[0])
    subjects = subject_label.index.tolist()
    subj_labels = subject_label.values

    unique_subjects = np.array(subjects)
    n = len(unique_subjects)
    logger.info(f"patient split：共 {n} 个 subject")

    train_ratio = cfg["train_ratio"]
    val_ratio = cfg["val_ratio"]
    test_ratio = cfg["test_ratio"]
    seed = cfg["random_seed"]

    # 用 GroupShuffleSplit 拆 test
    gss1 = GroupShuffleSplit(n_splits=1, test_size=test_ratio, random_state=seed)
    subj_idx = np.arange(n)
    trainval_s_idx, test_s_idx = next(
        gss1.split(subj_idx, subj_labels, groups=unique_subjects)
    )

    # 再拆 val
    val_ratio_adj = val_ratio / (train_ratio + val_ratio)
    gss2 = GroupShuffleSplit(n_splits=1, test_size=val_ratio_adj, random_state=seed)
    train_s_idx, val_s_idx = next(
        gss2.split(
            subj_idx[trainval_s_idx],
            subj_labels[trainval_s_idx],
            groups=unique_subjects[trainval_s_idx],
        )
    )
    train_s_idx = trainval_s_idx[train_s_idx]
    val_s_idx = trainval_s_idx[val_s_idx]

    train_subjects = set(unique_subjects[train_s_idx])
    val_subjects = set(unique_subjects[val_s_idx])
    test_subjects = set(unique_subjects[test_s_idx])

    # 检查无交叉
    assert len(train_subjects & test_subjects) == 0, "train/test subject 有交叉！"
    assert len(val_subjects & test_subjects) == 0, "val/test subject 有交叉！"
    assert len(train_subjects & val_subjects) == 0, "train/val subject 有交叉！"
    logger.info("patient split 无交叉验证 PASS")

    train_idx = df.index[df["subject_id"].isin(train_subjects)].tolist()
    val_idx = df.index[df["subject_id"].isin(val_subjects)].tolist()
    test_idx = df.index[df["subject_id"].isin(test_subjects)].tolist()

    return {"train": np.array(train_idx), "val": np.array(val_idx), "test": np.array(test_idx)}


def compute_class_dist(df: pd.DataFrame, indices: np.ndarray) -> dict:
    sub = df.iloc[indices]
    counts = sub["label"].value_counts().to_dict()
    return counts


def warn_moderate_shortage(dist: dict, split_name: str, threshold: int = 10):
    moderate_count = dist.get("ModerateDemented", 0)
    if moderate_count < threshold:
        logger.warning(
            f"⚠️  {split_name} 集 ModerateDemented 仅 {moderate_count} 张（< {threshold}），"
            f"极少数类，评估指标不可靠，请关注。"
        )


def save_split_csv(df: pd.DataFrame, indices: np.ndarray, out_path: Path):
    sub = df.iloc[indices].copy()
    sub["split_index"] = indices
    sub.to_csv(out_path, index=False)
    logger.info(f"split csv 已写 -> {out_path}")


def main():
    parser = argparse.ArgumentParser(description="WaveFidBench data_split.py")
    parser.add_argument("--config", required=True, help="YAML config 路径")
    parser.add_argument(
        "--data_root",
        required=True,
        help="数据根目录，含 4 类子文件夹",
    )
    args = parser.parse_args()

    cfg = load_config(args.config)

    # 命令行参数覆盖 config 中 data_root
    data_root = Path(args.data_root)
    if not data_root.exists():
        raise FileNotFoundError(f"data_root 不存在：{data_root}")

    # 确定输出目录（相对于本脚本所在项目根）
    project_root = Path(__file__).parent.parent
    log_dir = project_root / cfg.get("log_dir", "log")
    split_csv_dir = project_root / cfg.get("split_csv_dir", "log/splits")
    split_csv_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    # 收集样本
    df = collect_samples(data_root)

    # 可选：每类子采样（烟测用，正式跑设 null 不裁剪）
    max_per_class = cfg.get("max_samples_per_class")
    if max_per_class:
        seed = cfg.get("random_seed", 42)
        df = (
            df.groupby("label", group_keys=False)
            .apply(lambda g: g.sample(n=min(len(g), int(max_per_class)), random_state=seed))
            .reset_index(drop=True)
        )
        logger.warning(
            f"⚠️ max_samples_per_class={max_per_class} 子采样生效（烟测），"
            f"裁剪后共 {len(df)} 张。正式跑须设 null。"
        )

    # Split
    split_mode = cfg.get("split_mode", "slice")
    logger.info(f"split_mode = {split_mode}")

    if split_mode == "slice":
        splits = split_slice(df, cfg, split_csv_dir)
    elif split_mode == "patient":
        splits = split_patient(df, cfg, split_csv_dir)
    else:
        raise ValueError(f"未知 split_mode: {split_mode}（支持 slice / patient）")

    # 写 csv + 统计
    dist_summary = {}
    for split_name, indices in splits.items():
        csv_path = split_csv_dir / f"{split_name}.csv"
        save_split_csv(df, indices, csv_path)
        dist = compute_class_dist(df, indices)
        dist_summary[split_name] = dist
        logger.info(f"  {split_name}: {len(indices)} 张，类分布 = {dist}")
        warn_moderate_shortage(dist, split_name)

    # 总计核对
    total_assigned = sum(len(v) for v in splits.values())
    logger.info(f"总分配 {total_assigned} / {len(df)} 张")
    if total_assigned != len(df):
        logger.warning(f"⚠️ 分配总数 {total_assigned} != 样本总数 {len(df)}，请检查。")

    # state.json
    state = {
        "script": "data_split.py",
        "timestamp": datetime.now().isoformat(),
        "dataset": cfg.get("dataset", "unknown"),
        "data_root": str(data_root),
        "split_mode": split_mode,
        "split_mode_note": (
            "slice-level: 泄漏，仅烟测"
            if split_mode == "slice"
            else "patient-level: 按 subject ID 分组，无泄漏"
        ),
        "total_samples": len(df),
        "split_sizes": {k: int(len(v)) for k, v in splits.items()},
        "class_distribution": dist_summary,
        "split_csv_dir": str(split_csv_dir),
        "config": cfg,
    }

    state_path = log_dir / "data_split_state.json"
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    logger.info(f"state.json 已写 -> {state_path}")

    print(f"\nDone. split_mode={split_mode}, state -> {state_path}")


if __name__ == "__main__":
    main()
