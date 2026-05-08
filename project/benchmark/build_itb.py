"""构建 ITB (Iterative Triage Benchmark) 4 个子集。

子集（按预计算 q̄ 严格分层，确保 fig3 覆盖完整 q̄ 范围）：
  ITB-LQ      低质量：heavy 退化且预计算 q̄ < 0.40
  ITB-HQ      高质量：原图且预计算 q̄ > 0.65
  ITB-Edge    边界质量：light/medium 退化且预计算 q̄ in [0.40, 0.55]
  ITB-Diverse 多肤色：FitzPatrick17k（Fitzpatrick I-VI 均衡采样）

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
N_PER_SUBSET = 500
SEED         = 42

Q_COLS = ["sharpness", "brightness", "completeness", "color_temp", "contrast"]

LQ_QBAR_MAX  = 0.40   # ITB-LQ:  q̄ < 0.40
HQ_QBAR_MIN  = 0.65   # ITB-HQ:  q̄ > 0.65
EDGE_LO      = 0.40   # ITB-Edge: q̄ in [0.40, 0.55]
EDGE_HI      = 0.55


def get_isic_id(path):
    return "_".join(Path(path).stem.split("_")[:2])


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

    # ── ITB-LQ: heavy 且 q̄ < 0.40 ──────────────────────────────────────────
    lq_pool = isic[(isic["level"] == "heavy") & (isic["qbar"] < LQ_QBAR_MAX)]
    lq = lq_pool.sample(min(N_PER_SUBSET, len(lq_pool)), random_state=SEED)
    for _, r in lq.iterrows():
        rows.append({"subset": "ITB-LQ", "isic_id": r["isic_id"],
                     "image_path": r["degraded_path"], "target": int(r["target"]),
                     "level": "heavy", "source": "isic2020", "qbar": float(r["qbar"])})
    print(f"ITB-LQ:  {len(lq)} samples  (pool={len(lq_pool)})  qbar range [{lq['qbar'].min():.3f}, {lq['qbar'].max():.3f}]")

    # ── ITB-HQ: 原图且 q̄ > 0.65 ──────────────────────────────────────────
    # original_path 去重，借用 heavy 行的 original_path 找原图 q̄
    hq_pool = (isic[isic["level"] == "heavy"]
               .drop_duplicates("isic_id")
               .query(f"qbar > {HQ_QBAR_MIN}"))
    # 注：heavy 图的 q̄ < HQ 阈值，用原图对应的质量（brightness/completeness 等不变）
    # 实际上我们需要原图 q̄，而 quality_labels 存的是退化图的分数。
    # 用 sharpness 以外各维度的均值近似原图 q̄：brightness/completeness/color_temp/contrast 基本不受 blur 影响
    non_sharp = ["brightness", "completeness", "color_temp", "contrast"]
    isic_orig = isic[isic["level"] == "heavy"].copy()
    isic_orig["orig_qbar"] = isic_orig[non_sharp].mean(axis=1)
    hq_pool = (isic_orig.drop_duplicates("isic_id")
               .query(f"orig_qbar > {HQ_QBAR_MIN}"))
    hq = hq_pool.sample(min(N_PER_SUBSET, len(hq_pool)), random_state=SEED)
    for _, r in hq.iterrows():
        rows.append({"subset": "ITB-HQ", "isic_id": r["isic_id"],
                     "image_path": r["original_path"], "target": int(r["target"]),
                     "level": "original", "source": "isic2020", "qbar": float(r["orig_qbar"])})
    print(f"ITB-HQ:  {len(hq)} samples  (pool={len(hq_pool)})  qbar range [{hq['orig_qbar'].min():.3f}, {hq['orig_qbar'].max():.3f}]")

    # ── ITB-Edge: light/medium 且 q̄ in [EDGE_LO, EDGE_HI] ────────────────
    edge_pool = isic[(isic["level"].isin(["light", "medium"])) &
                     (isic["qbar"] >= EDGE_LO) & (isic["qbar"] <= EDGE_HI)]
    edge = edge_pool.sample(min(N_PER_SUBSET, len(edge_pool)), random_state=SEED)
    for _, r in edge.iterrows():
        rows.append({"subset": "ITB-Edge", "isic_id": r["isic_id"],
                     "image_path": r["degraded_path"], "target": int(r["target"]),
                     "level": r["level"], "source": "isic2020", "qbar": float(r["qbar"])})
    print(f"ITB-Edge:{len(edge)} samples  (pool={len(edge_pool)})  qbar range [{edge['qbar'].min():.3f}, {edge['qbar'].max():.3f}]")

    # ── ITB-Diverse: FitzPatrick17k ────────────────────────────────────────
    fp_df = df[df["source"] == "fitzpatrick17k"].copy()
    fp_meta_path = Path(FP17K_CSV)
    if fp_meta_path.exists():
        fp_meta = pd.read_csv(fp_meta_path)[["md5hash", "fitzpatrick_scale", "label"]].rename(
            columns={"md5hash": "fp_id", "fitzpatrick_scale": "fitzpatrick"})
        fp_df["fp_id"] = fp_df["degraded_path"].apply(lambda p: Path(p).stem.split("_")[0])
        fp_df = fp_df.merge(fp_meta, on="fp_id", how="left").dropna(subset=["label"])
        fp_df["target"] = (fp_df["label"].str.lower().str.contains("melanoma|malignant")).astype(int)
        fp_sample_list = []
        for fitz_val, g in fp_df.groupby("fitzpatrick"):
            s = g.sample(min(N_PER_SUBSET // 6, len(g)), random_state=SEED)
            s = s.assign(fitzpatrick=fitz_val)
            fp_sample_list.append(s)
        fp_sample = pd.concat(fp_sample_list).head(N_PER_SUBSET)
        for _, r in fp_sample.iterrows():
            rows.append({"subset": "ITB-Diverse", "isic_id": str(r["fp_id"]),
                         "image_path": r["original_path"], "target": int(r["target"]),
                         "level": "original", "source": "fitzpatrick17k",
                         "qbar": float(r["qbar"])})
        fitz_dist = fp_sample["fitzpatrick"].value_counts().to_dict()
        print(f"ITB-Diverse: {len(fp_sample)} samples  Fitzpatrick dist: {fitz_dist}")
    else:
        div = (isic.drop_duplicates("isic_id")
               .sample(min(N_PER_SUBSET, len(isic.drop_duplicates("isic_id"))), random_state=SEED + 1))
        for _, r in div.iterrows():
            rows.append({"subset": "ITB-Diverse", "isic_id": r["isic_id"],
                         "image_path": r["original_path"], "target": int(r["target"]),
                         "level": "original", "source": "isic2020", "qbar": float(r["qbar"])})
        print(f"ITB-Diverse: {len(div)} samples (ISIC fallback)")

    out = pd.DataFrame(rows)
    Path(OUT_CSV).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_CSV, index=False)
    print(f"\nSaved {OUT_CSV}")
    print(out.groupby("subset")[["isic_id", "target", "qbar"]].agg(
        {"isic_id": "count", "target": "mean", "qbar": ["min", "mean", "max"]}
    ).round(3))


if __name__ == "__main__":
    main()
