"""构建 ITB (Iterative Triage Benchmark) 4 个子集。

子集（按预计算 q̄ 严格分层，确保 fig3 覆盖完整 q̄ 范围）：
  ITB-LQ      低质量：heavy 退化且预计算 q̄ < 0.40
  ITB-HQ      高质量：原图且预计算 q̄ > 0.65
  ITB-Edge    边界质量：light/medium 退化且预计算 q̄ in [0.40, 0.55]
  ITB-Diverse 多肤色：FitzPatrick17k（Fitzpatrick I-VI 均衡采样 + 恶性过采样）

STRATIFIED SAMPLING (MICCAI revision):
  每个子集：保留质量过滤池中全部阳性样本，补充阴性使阳性率达到 ~20%。
  目标样本数（上限，视池中阳性数量而定）：
    ITB-LQ:   45 pos + 180 neg = 225 total
    ITB-HQ:   25 pos + 100 neg = 125 total
    ITB-Edge: 132 pos + 528 neg = 660 total

输出：results/itb_subsets.csv
  columns: subset, isic_id, image_path, target, level, source, qbar
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd

LABELS_CSV   = "D:/YJ-Agent/data/quality_labels_all.csv"
METADATA_CSV = "D:/YJ-Agent/data/raw/isic2020/train-metadata.csv"
SPLIT_CSV    = "D:/YJ-Agent/data/isic_split.csv"
FP17K_CSV    = "D:/YJ-Agent/data/raw/fitzpatrick17k/fitzpatrick17k.csv"
OUT_CSV      = "D:/YJ-Agent/project/results/itb_subsets.csv"
SEED         = 42

# Target positive rate for stratified sampling
TARGET_POS_RATE = 0.20   # 20% positive rate

Q_COLS = ["sharpness", "brightness", "completeness", "color_temp", "contrast"]

LQ_QBAR_MAX  = 0.40   # ITB-LQ:  q̄ < 0.40
HQ_QBAR_MIN  = 0.65   # ITB-HQ:  q̄ > 0.65
EDGE_LO      = 0.40   # ITB-Edge: q̄ in [0.40, 0.55]
EDGE_HI      = 0.55


def get_isic_id(path):
    return "_".join(Path(path).stem.split("_")[:2])


def stratified_sample(pool: pd.DataFrame, seed: int = SEED) -> pd.DataFrame:
    """Stratified sampling: keep ALL positives, sample negatives to hit ~20% positive rate.

    Formula: N_neg = N_pos * (1 - TARGET_POS_RATE) / TARGET_POS_RATE
             total = N_pos + N_neg

    Args:
        pool: DataFrame with a 'target' column (0/1).
        seed: Random seed for negative sampling.

    Returns:
        Sampled DataFrame with ~20% positive rate.
    """
    pos = pool[pool["target"] == 1]
    neg = pool[pool["target"] == 0]

    n_pos = len(pos)
    if n_pos == 0:
        # No positives: fall back to sampling 500 to avoid empty subset
        return neg.sample(min(500, len(neg)), random_state=seed)

    # Number of negatives needed for ~20% positive rate
    n_neg_target = int(n_pos * (1 - TARGET_POS_RATE) / TARGET_POS_RATE)
    n_neg = min(n_neg_target, len(neg))

    neg_sampled = neg.sample(n_neg, random_state=seed)
    return pd.concat([pos, neg_sampled]).sample(frac=1, random_state=seed)  # shuffle


def main():
    df = pd.read_csv(LABELS_CSV)
    df["qbar"] = df[Q_COLS].mean(axis=1)

    meta  = pd.read_csv(METADATA_CSV)[["isic_id", "target"]]
    split = pd.read_csv(SPLIT_CSV)
    test_ids = set(split[split["split"] == "test"]["isic_id"])

    df["isic_id"] = df["degraded_path"].apply(get_isic_id)
    isic = df[df["source"] == "isic2020"].copy()
    isic = (isic[isic["isic_id"].isin(test_ids)]
            .merge(meta, on="isic_id", how="left")
            .dropna(subset=["target"]))

    rows = []

    # ── ITB-LQ: heavy 且 q̄ < 0.40（stratified: all pos + fill neg to 20%) ──
    lq_pool = isic[(isic["level"] == "heavy") & (isic["qbar"] < LQ_QBAR_MAX)]
    lq = stratified_sample(lq_pool)
    for _, r in lq.iterrows():
        rows.append({"subset": "ITB-LQ", "isic_id": r["isic_id"],
                     "image_path": r["degraded_path"], "target": int(r["target"]),
                     "level": "heavy", "source": "isic2020", "qbar": float(r["qbar"])})
    pos_count = int(lq["target"].sum())
    print(f"ITB-LQ:  {len(lq)} samples  (pool={len(lq_pool)})  "
          f"pos={pos_count} ({pos_count/len(lq)*100:.1f}%)  "
          f"qbar range [{lq['qbar'].min():.3f}, {lq['qbar'].max():.3f}]")

    # ── ITB-HQ: 原图且 q̄ > 0.65（stratified: all pos + fill neg to 20%) ──
    # 用 sharpness 以外各维度的均值近似原图 q̄（brightness/completeness/color_temp/contrast
    # 基本不受 blur 影响）
    non_sharp = ["brightness", "completeness", "color_temp", "contrast"]
    isic_orig = isic[isic["level"] == "heavy"].copy()
    isic_orig["orig_qbar"] = isic_orig[non_sharp].mean(axis=1)
    hq_pool = isic_orig.drop_duplicates("isic_id").query(f"orig_qbar > {HQ_QBAR_MIN}")
    hq = stratified_sample(hq_pool)
    for _, r in hq.iterrows():
        rows.append({"subset": "ITB-HQ", "isic_id": r["isic_id"],
                     "image_path": r["original_path"], "target": int(r["target"]),
                     "level": "original", "source": "isic2020", "qbar": float(r["orig_qbar"])})
    pos_count = int(hq["target"].sum())
    print(f"ITB-HQ:  {len(hq)} samples  (pool={len(hq_pool)})  "
          f"pos={pos_count} ({pos_count/len(hq)*100:.1f}%)  "
          f"qbar range [{hq['orig_qbar'].min():.3f}, {hq['orig_qbar'].max():.3f}]")

    # ── ITB-Edge: light/medium 且 q̄ in [EDGE_LO, EDGE_HI]（stratified) ────
    edge_pool = isic[(isic["level"].isin(["light", "medium"])) &
                     (isic["qbar"] >= EDGE_LO) & (isic["qbar"] <= EDGE_HI)]
    edge = stratified_sample(edge_pool)
    for _, r in edge.iterrows():
        rows.append({"subset": "ITB-Edge", "isic_id": r["isic_id"],
                     "image_path": r["degraded_path"], "target": int(r["target"]),
                     "level": r["level"], "source": "isic2020", "qbar": float(r["qbar"])})
    pos_count = int(edge["target"].sum())
    print(f"ITB-Edge:{len(edge)} samples  (pool={len(edge_pool)})  "
          f"pos={pos_count} ({pos_count/len(edge)*100:.1f}%)  "
          f"qbar range [{edge['qbar'].min():.3f}, {edge['qbar'].max():.3f}]")

    # ── ITB-Diverse: FitzPatrick17k（Fitzpatrick I-VI 均衡 + 恶性过采样到 20%) ──
    fp_df = df[df["source"] == "fitzpatrick17k"].copy()
    fp_meta_path = Path(FP17K_CSV)
    if fp_meta_path.exists():
        fp_meta = pd.read_csv(fp_meta_path)[["md5hash", "fitzpatrick_scale", "label"]].rename(
            columns={"md5hash": "fp_id", "fitzpatrick_scale": "fitzpatrick"})
        fp_df["fp_id"] = fp_df["degraded_path"].apply(lambda p: Path(p).stem.split("_")[0])
        fp_df = fp_df.merge(fp_meta, on="fp_id", how="left").dropna(subset=["label"])
        fp_df["target"] = (fp_df["label"].str.lower().str.contains("melanoma|malignant")).astype(int)

        # Stratify within each Fitzpatrick type: keep all malignant, fill benign to 20%
        fp_sample_list = []
        for fitz_val, g in fp_df.groupby("fitzpatrick"):
            sampled = stratified_sample(g, seed=SEED + int(fitz_val) if str(fitz_val).isdigit() else SEED)
            sampled = sampled.assign(fitzpatrick=fitz_val)
            fp_sample_list.append(sampled)
        fp_sample = pd.concat(fp_sample_list)
        for _, r in fp_sample.iterrows():
            rows.append({"subset": "ITB-Diverse", "isic_id": str(r["fp_id"]),
                         "image_path": r["original_path"], "target": int(r["target"]),
                         "level": "original", "source": "fitzpatrick17k",
                         "qbar": float(r["qbar"])})
        fitz_dist = fp_sample["fitzpatrick"].value_counts().to_dict()
        pos_count = int(fp_sample["target"].sum())
        print(f"ITB-Diverse: {len(fp_sample)} samples  "
              f"pos={pos_count} ({pos_count/len(fp_sample)*100:.1f}%)  "
              f"Fitzpatrick dist: {fitz_dist}")
    else:
        # Fallback: use ISIC test set with stratified sampling
        div_pool = isic.drop_duplicates("isic_id")
        div = stratified_sample(div_pool, seed=SEED + 1)
        for _, r in div.iterrows():
            rows.append({"subset": "ITB-Diverse", "isic_id": r["isic_id"],
                         "image_path": r["original_path"], "target": int(r["target"]),
                         "level": "original", "source": "isic2020", "qbar": float(r["qbar"])})
        pos_count = int(div["target"].sum())
        print(f"ITB-Diverse: {len(div)} samples  "
              f"pos={pos_count} ({pos_count/len(div)*100:.1f}%)  (ISIC fallback)")

    out = pd.DataFrame(rows)
    Path(OUT_CSV).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_CSV, index=False)
    print(f"\nSaved {OUT_CSV}")
    print(out.groupby("subset")[["isic_id", "target", "qbar"]].agg(
        {"isic_id": "count", "target": "mean", "qbar": ["min", "mean", "max"]}
    ).round(3))


if __name__ == "__main__":
    main()
