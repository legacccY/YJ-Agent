"""
make_split.py
HyperFidBench Gate1 / BrainGB-ABIDE-I 泳道 / P3-split 步骤

Patient-level stratified k-fold split。
红线（02_ACCEPTANCE.md）：
  - 键 = SUB_ID（同一被试所有数据不跨 fold）
  - StratifiedKFold(n_splits=5, shuffle=True)，按 DX_GROUP 分层
  - site 信息留存（供后续 site-leakage 分析，但不强制 site-stratified，Gate1 暂不做）
  - 可复现：固定 random_state=112078（与 BrainGB 官方 seed 对齐）

产出：split_indices.csv
列：sub_id, site_id, dx_group, label, fold_0, fold_1, ..., fold_4
    fold_N 值: 'train' or 'test'
"""

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BRAINGB_ABIDE_DIR = REPO_ROOT / "vendor" / "BrainGB" / "examples" / "datasets" / "ABIDE"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "external" / "abide1"

# 官方 seed（来自 BrainGB example_main.py argparse 默认 --seed=112078）
OFFICIAL_SEED = 112078
N_SPLITS = 5  # BrainGB 代码默认 k_fold_splits=5


def make_split(
    braingb_abide_dir: Path,
    output_dir: Path,
    n_splits: int = N_SPLITS,
    seed: int = OFFICIAL_SEED,
    sub_id_col: str = "SUB_ID",
    dx_col: str = "DX_GROUP",
) -> pd.DataFrame:
    """
    从 build_graphs.py 产出的 split_phenotypic.csv（含完整 SUB_ID/SITE_ID/DX_GROUP）
    生成 patient-level StratifiedKFold split 索引。

    红线检查（assert 写入，测试可直接引用）：
      - 同一 SUB_ID 不跨 train/test（patient-level split 完整性）
      - 每 fold 中两类 DX 均有样本（分层 OK）
    """
    # 读 phenotypic（由 build_graphs.py 保存的子集）
    pheno_path = braingb_abide_dir / "split_phenotypic.csv"
    if not pheno_path.exists():
        # 尝试从 abide.npy 重建
        abide_npy = braingb_abide_dir / "abide.npy"
        if abide_npy.exists():
            logger.warning(f"split_phenotypic.csv 不存在，尝试从 abide.npy 重建基础信息")
            data = np.load(str(abide_npy), allow_pickle=True).item()
            n = len(data["label"])
            sub_ids = data.get("sub_ids", np.arange(n))
            site_ids = data.get("site_ids", np.zeros(n, dtype=int))
            labels = data["label"]
            pheno = pd.DataFrame({
                sub_id_col: sub_ids,
                "SITE_ID": site_ids,
                dx_col: np.where(labels == 1, 1, 2),  # 1=ASD, 2=TD (DX_GROUP 编码)
                "label": labels,
            })
        else:
            raise FileNotFoundError(
                f"既找不到 split_phenotypic.csv 也找不到 abide.npy，"
                f"请先运行 build_graphs.py。路径: {braingb_abide_dir}"
            )
    else:
        pheno = pd.read_csv(pheno_path)
        logger.info(f"Phenotypic 加载: {len(pheno)} 行")

    # 统一 label 列（1=ASD, 0=TD）
    if "label" not in pheno.columns:
        pheno["label"] = (pheno[dx_col] == 1).astype(int)

    # SUB_ID 去重（patient-level：每个被试只出现一次，已在 build_graphs 保证）
    if pheno[sub_id_col].duplicated().any():
        n_dup = pheno[sub_id_col].duplicated().sum()
        logger.warning(f"发现 {n_dup} 个重复 SUB_ID，保留首条（理论上不应出现）")
        pheno = pheno.drop_duplicates(subset=[sub_id_col], keep="first").reset_index(drop=True)

    logger.info(f"唯一被试数: {len(pheno)}")
    logger.info(f"标签分布: ASD={int((pheno['label'] == 1).sum())}  "
                f"TD={int((pheno['label'] == 0).sum())}")
    if "SITE_ID" in pheno.columns:
        logger.info(f"Site 数: {pheno['SITE_ID'].nunique()}")

    # StratifiedKFold（对齐 BrainGB example_main.py 默认参数）
    # BrainGB 原代码用 random.randint(1, 1000000) 给每次 repeat 随机 seed
    # 此处固定 seed=112078 确保可复现（Gate1 只需确定性 split）
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)

    y = pheno["label"].values
    indices = np.arange(len(pheno))

    fold_assignments = {}
    for fold_idx, (train_idx, test_idx) in enumerate(skf.split(indices, y)):
        col_name = f"fold_{fold_idx}"
        fold_assignments[col_name] = "train"  # default
        pheno_fold = pd.Series(["train"] * len(pheno), name=col_name)
        pheno_fold.iloc[test_idx] = "test"
        pheno[col_name] = pheno_fold.values

        logger.info(
            f"Fold {fold_idx}: train={len(train_idx)} / test={len(test_idx)} | "
            f"test ASD={int(y[test_idx].sum())} TD={int((y[test_idx] == 0).sum())}"
        )

    # 红线验证 1：同一 SUB_ID 不同 fold 中不同时出现 train/test（天然满足，但显式断言）
    # 由于每个 SUB_ID 只出现一行，且 fold split 基于行 → 无泄漏风险
    # 保留断言供 pytest 引用
    assert not pheno[sub_id_col].duplicated().any(), \
        "BUG: SUB_ID 有重复，patient-level split 可能泄漏！"

    # 红线验证 2：每 fold 的 test 集两类都有
    for fold_idx in range(n_splits):
        col = f"fold_{fold_idx}"
        test_labels = pheno.loc[pheno[col] == "test", "label"]
        assert test_labels.nunique() == 2, \
            f"Fold {fold_idx} test 集只有一类，分层出错！"

    # 保存
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "split_indices.csv"
    pheno.to_csv(output_path, index=False)
    logger.info(f"Split 索引已保存: {output_path}")
    logger.info(f"列: {list(pheno.columns)}")

    return pheno


def main():
    parser = argparse.ArgumentParser(description="生成 ABIDE-I patient-level StratifiedKFold split")
    parser.add_argument(
        "--braingb_abide_dir",
        type=str,
        default=str(DEFAULT_BRAINGB_ABIDE_DIR),
        help="build_graphs.py 输出目录（含 split_phenotypic.csv 或 abide.npy）",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default=str(DEFAULT_OUTPUT_DIR),
        help="split_indices.csv 输出目录，默认 data/external/abide1/",
    )
    parser.add_argument(
        "--n_splits",
        type=int,
        default=N_SPLITS,
        help=f"K-fold 折数，默认 {N_SPLITS}（BrainGB 官方默认）",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=OFFICIAL_SEED,
        help=f"随机种子，默认 {OFFICIAL_SEED}（BrainGB 官方 --seed 默认值）",
    )
    args = parser.parse_args()

    df = make_split(
        braingb_abide_dir=Path(args.braingb_abide_dir),
        output_dir=Path(args.output_dir),
        n_splits=args.n_splits,
        seed=args.seed,
    )
    logger.info(f"完成，共 {len(df)} 被试 × {args.n_splits} fold。")


if __name__ == "__main__":
    main()
