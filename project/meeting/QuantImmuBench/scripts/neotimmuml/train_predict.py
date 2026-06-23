"""
train_predict.py — QuantImmuBench / NeoTImmuML
复刻 NeoTImmuML.ipynb 的 VotingClassifier (RF + LGB + XGB) 训练 + 对新肽段预测

端到端流程（使用 TumorAgDB2.0 真实数据）:

  Step A: 组装训练集肽段列表
    python build_trainset.py
    → train_data/trainset_peptides.csv  (Peptide, immunogenicity)

  Step B: 对训练集肽段算 78 特征（R）
    Rscript calc_78_features.R \
        --input  train_data/trainset_peptides.csv \
        --output train_data/trainset_features.csv

  Step C: 训练模型
    python train_predict.py train \
        --feature_csv train_data/trainset_features.csv \
        --label_csv   train_data/trainset_peptides.csv \
        --model_dir   scripts/neotimmuml/models/

  Step D: 对 ELISpot 肽段算 78 特征（R，若未做）
    python extract_peptides.py
    Rscript calc_78_features.R \
        --input  scripts/out/neotimmuml_peptides.txt \
        --output scripts/out/neotimmuml_features.csv

  Step E: 预测
    python train_predict.py predict \
        --feature_csv scripts/out/neotimmuml_features.csv \
        --model_dir   scripts/neotimmuml/models/ \
        --output      scripts/out/neotimmuml_scores.csv

超参来源: NeoTImmuML.ipynb Cell17 + Cell20（严格复刻，不修改）:
  RandomForest : n_estimators=300, max_depth=7, min_samples_split=2,
                 min_samples_leaf=4, max_features=None, bootstrap=True
  LightGBM     : n_estimators=300, learning_rate=0.05, max_depth=7,
                 num_leaves=31, min_child_samples=50, subsample=0.6,
                 colsample_bytree=0.8, reg_lambda=0.01
  XGBoost      : n_estimators=200, learning_rate=0.05, max_depth=5,
                 min_child_weight=3, subsample=0.6, colsample_bytree=1.0,
                 gamma=0.1, reg_alpha=0.01, reg_lambda=0
  Weights(Cell20): RF=4, LGB=8, XGB=9

类不平衡: notebook 无处理，严格照搬（直接 fit）

env: conda activate neotimmuml (py3.10 + lgbm4.6 + xgb3.2 + scikit-learn + joblib + pandas + openpyxl)
"""

import argparse
import os
import sys
import pathlib
import numpy as np
import pandas as pd
from joblib import dump, load


# ---- 特征列名（严格与 demo.csv col2-79 对应，共 78 列）----
FEATURE_COLS = (
    ["mol_weight", "isoelectric_point", "boman_index", "charge",
     "hydrophobicity_index", "lengthpep", "instability_index", "hmoment",
     "membpos.H", "membpos.uH", "aindex", "autoCorrelation", "autoCovariance",
     "aaComp_1"]
    + [f"blosum_{i}" for i in range(1, 11)]
    + ["cruciani_1"]
    + [f"fasgai_{i}" for i in range(1, 7)]
    + [f"kidera_{i}" for i in range(1, 11)]
    + [f"mswhim_{i}" for i in range(1, 4)]
    + [f"protFP_{i}" for i in range(1, 9)]
    + [f"stscale_{i}" for i in range(1, 9)]
    + [f"tscale_{i}" for i in range(1, 6)]
    + [f"vhse_{i}" for i in range(1, 9)]
    + [f"zscale_{i}" for i in range(1, 6)]
)
assert len(FEATURE_COLS) == 78, f"Expected 78 feature cols, got {len(FEATURE_COLS)}"

# ---- 模型超参（来源: notebook Cell17，不臆造）----
RANDOM_SEED = 42
RF_PARAMS = dict(
    n_estimators=300,
    max_depth=7,
    min_samples_split=2,
    min_samples_leaf=4,
    max_features=None,
    bootstrap=True,
    random_state=RANDOM_SEED,
)
LGB_PARAMS = dict(
    n_estimators=300,
    learning_rate=0.05,
    max_depth=7,
    num_leaves=31,
    min_child_samples=50,
    subsample=0.6,
    colsample_bytree=0.8,
    reg_lambda=0.01,
    random_state=RANDOM_SEED,
    verbose=-1,
)
XGB_PARAMS = dict(
    n_estimators=200,
    learning_rate=0.05,
    max_depth=5,
    min_child_weight=3,
    subsample=0.6,
    colsample_bytree=1.0,
    gamma=0.1,
    reg_alpha=0.01,
    reg_lambda=0,
    random_state=RANDOM_SEED,
    eval_metric="logloss",
    nthread=1,   # Windows OMP 安全
)
# 加权融合权重（来源: notebook Cell20）
WEIGHTS = {"rf": 4, "lgb": 8, "xgb": 9}
WEIGHTS_TOTAL = sum(WEIGHTS.values())  # 21


# ---- 数据加载 ----

def load_feature_csv(feature_csv: str) -> pd.DataFrame:
    """加载 calc_78_features.R 产出的特征 csv，验证 78 列存在"""
    if not os.path.exists(feature_csv):
        raise FileNotFoundError(f"Feature CSV not found: {feature_csv}\n"
                                "  请先跑 calc_78_features.R 产出特征文件")
    df = pd.read_csv(feature_csv)
    if "Peptide" not in df.columns:
        raise ValueError("feature_csv must have 'Peptide' column")
    missing = [c for c in FEATURE_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"feature_csv missing {len(missing)} feature cols: {missing[:5]}...")
    return df


def merge_features_labels(feature_csv: str, label_csv: str) -> tuple:
    """
    合并特征 csv（Peptide + 78特征）和标签 csv（Peptide + immunogenicity）
    按 Peptide 内连接，去除特征有 NaN 的行
    返回 (X: np.ndarray, y: np.ndarray, n_merged)
    """
    feat_df = load_feature_csv(feature_csv)

    label_df = pd.read_csv(label_csv)
    if "Peptide" not in label_df.columns or "immunogenicity" not in label_df.columns:
        raise ValueError("label_csv must have 'Peptide' and 'immunogenicity' columns")

    merged = feat_df.merge(label_df[["Peptide", "immunogenicity"]], on="Peptide", how="inner")
    print(f"[INFO] After merge: {len(merged)} rows (feat={len(feat_df)}, label={len(label_df)})")

    # 去 NaN（R 计算失败的肽段）
    before = len(merged)
    merged = merged.dropna(subset=FEATURE_COLS)
    if len(merged) < before:
        print(f"[WARN] Dropped {before - len(merged)} rows with NaN features")

    X = merged[FEATURE_COLS].values.astype(float)
    y = merged["immunogenicity"].values.astype(int)
    vc = pd.Series(y).value_counts()
    print(f"[INFO] Label dist: pos={vc.get(1,0)}, neg={vc.get(0,0)}")
    print(f"[INFO] NOTE: no class imbalance handling per notebook (direct fit)")
    return X, y


# ---- 模型构建 ----

def build_models():
    from lightgbm import LGBMClassifier
    from xgboost import XGBClassifier
    from sklearn.ensemble import RandomForestClassifier

    model_rf  = RandomForestClassifier(**RF_PARAMS)
    model_lgb = LGBMClassifier(**LGB_PARAMS)
    model_xgb = XGBClassifier(**XGB_PARAMS)
    return model_rf, model_lgb, model_xgb


# ---- 子命令实现 ----

def cmd_train(args):
    """
    train: feature_csv (R产出78特征) + label_csv (Peptide+immunogenicity) → 训练+保存模型
    """
    pathlib.Path(args.model_dir).mkdir(parents=True, exist_ok=True)
    X, y = merge_features_labels(args.feature_csv, args.label_csv)

    print(f"[INFO] Training on {len(X)} samples, {X.shape[1]} features")
    model_rf, model_lgb, model_xgb = build_models()

    print("[INFO] Fitting RandomForest...")
    model_rf.fit(X, y)
    dump(model_rf,  os.path.join(args.model_dir, "model_rf.joblib"))

    print("[INFO] Fitting LightGBM...")
    model_lgb.fit(X, y)
    dump(model_lgb, os.path.join(args.model_dir, "model_lgb.joblib"))

    print("[INFO] Fitting XGBoost...")
    model_xgb.fit(X, y)
    dump(model_xgb, os.path.join(args.model_dir, "model_xgb.joblib"))

    print(f"[DONE] Models saved to: {args.model_dir}")


def cmd_predict(args):
    """
    predict: feature_csv (R产出78特征) → 加载模型 → neotimmuml_score
    """
    feat_df = load_feature_csv(args.feature_csv)
    peptides = feat_df["Peptide"].values

    # 去 NaN 行（R 计算失败的肽段，预测时跳过）
    feat_clean = feat_df.dropna(subset=FEATURE_COLS)
    n_dropped = len(feat_df) - len(feat_clean)
    if n_dropped:
        print(f"[WARN] Skipping {n_dropped} peptides with NaN features")

    X = feat_clean[FEATURE_COLS].values.astype(float)
    peps_clean = feat_clean["Peptide"].values
    print(f"[INFO] Predicting for {len(peps_clean)} peptides...")

    rf_path  = os.path.join(args.model_dir, "model_rf.joblib")
    lgb_path = os.path.join(args.model_dir, "model_lgb.joblib")
    xgb_path = os.path.join(args.model_dir, "model_xgb.joblib")
    for p in [rf_path, lgb_path, xgb_path]:
        if not os.path.exists(p):
            raise FileNotFoundError(
                f"Model not found: {p}\n"
                "  先跑 'python train_predict.py train ...' 训练并保存模型"
            )
    model_rf  = load(rf_path)
    model_lgb = load(lgb_path)
    model_xgb = load(xgb_path)

    # 加权融合（Cell20 weights: RF=4, LGB=8, XGB=9）
    p_rf  = model_rf.predict_proba(X)[:, 1]
    p_lgb = model_lgb.predict_proba(X)[:, 1]
    p_xgb = model_xgb.predict_proba(X)[:, 1]
    score = (WEIGHTS["rf"] * p_rf + WEIGHTS["lgb"] * p_lgb + WEIGHTS["xgb"] * p_xgb) / WEIGHTS_TOTAL

    out_df = pd.DataFrame({
        "Peptide":          peps_clean,
        "neotimmuml_score": score,
        "rf_proba":         p_rf,
        "lgb_proba":        p_lgb,
        "xgb_proba":        p_xgb,
    })
    pathlib.Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(args.output, index=False)
    print(f"[INFO] Score range: {score.min():.4f} - {score.max():.4f}")
    print(f"[DONE] Scores written to: {args.output} ({len(out_df)} rows)")


def cmd_all(args):
    """一步跑: 训练 + 预测"""
    cmd_train(args)
    cmd_predict(args)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="NeoTImmuML VotingClassifier train + predict"
    )
    sub = parser.add_subparsers(dest="cmd")

    # ---- train ----
    p_train = sub.add_parser("train", help="Train on R-computed 78-feature CSV")
    p_train.add_argument(
        "--feature_csv", required=True,
        help="78-feature CSV produced by calc_78_features.R for training peptides"
    )
    p_train.add_argument(
        "--label_csv", required=True,
        help="CSV with columns [Peptide, immunogenicity] (output of build_trainset.py)"
    )
    p_train.add_argument(
        "--model_dir", default="scripts/neotimmuml/models/",
        help="Directory to save .joblib models"
    )
    p_train.set_defaults(func=cmd_train)

    # ---- predict ----
    p_pred = sub.add_parser("predict", help="Predict immunogenicity for new peptides")
    p_pred.add_argument(
        "--feature_csv", required=True,
        help="78-feature CSV produced by calc_78_features.R for target peptides"
    )
    p_pred.add_argument(
        "--model_dir", default="scripts/neotimmuml/models/",
        help="Directory containing trained .joblib models"
    )
    p_pred.add_argument(
        "--output", default="scripts/out/neotimmuml_scores.csv",
        help="Output CSV: Peptide + neotimmuml_score + per-model probas"
    )
    p_pred.set_defaults(func=cmd_predict)

    # ---- all ----
    p_all = sub.add_parser("all", help="Train then predict in one shot")
    p_all.add_argument("--feature_csv",       required=True,
                       help="78-feature CSV for training peptides")
    p_all.add_argument("--label_csv",         required=True,
                       help="Peptide+label CSV (output of build_trainset.py)")
    p_all.add_argument("--predict_feature_csv", required=True,
                       help="78-feature CSV for target peptides to score")
    p_all.add_argument("--model_dir",  default="scripts/neotimmuml/models/")
    p_all.add_argument("--output",     default="scripts/out/neotimmuml_scores.csv")
    p_all.set_defaults(func=cmd_all)

    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)

    # cmd_all 需要把 predict_feature_csv 传给 predict
    if args.cmd == "all":
        # train step
        cmd_train(args)
        # patch args for predict
        args.feature_csv = args.predict_feature_csv
        cmd_predict(args)
    else:
        args.func(args)
