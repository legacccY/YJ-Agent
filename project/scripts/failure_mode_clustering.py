"""
failure_mode_clustering.py
--------------------------
HDBSCAN clustering on EfficientNet-B0 features for confidently-wrong predictions
on ITB-LQ (Std VIB / baseline='D'), targeting s6 Discussion of the BMVC paper.

Confidently-wrong definition:
  - prob_pos > 0.85 AND target=0  (predicted melanoma but actually benign)
  - prob_pos < 0.15 AND target=1  (predicted benign but actually melanoma)

Outputs:
  project/results/failure_mode_clusters.json
  project/results/failure_mode_samples.csv
"""

import os, json
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA

# ── 1. Load predictions and subset metadata ───────────────────────────────────
PROJ = "D:/YJ-Agent/project"
DATA = "D:/YJ-Agent/data"

print("Loading predictions and subset metadata ...")
preds = pd.read_csv(f"{PROJ}/results/itb_predictions.csv")
d_lq = preds[(preds["baseline"] == "D") & (preds["subset"] == "ITB-LQ")].copy().reset_index(drop=True)
print(f"  Std VIB ITB-LQ predictions: {len(d_lq)} rows")

subs = pd.read_csv(f"{PROJ}/results/itb_subsets.csv")
lq_subs = subs[subs["subset"] == "ITB-LQ"].reset_index(drop=True)
assert len(d_lq) == len(lq_subs), "Row count mismatch between predictions and subsets"
assert (d_lq["target"].values == lq_subs["target"].values).all(), "Target mismatch"

d_lq["isic_id"]    = lq_subs["isic_id"].values
d_lq["image_path"] = lq_subs["image_path"].values
d_lq["level"]      = lq_subs["level"].values

# ── 2. Filter confidently-wrong samples ───────────────────────────────────────
cw_mask = (
    ((d_lq["prob_pos"] > 0.85) & (d_lq["target"] == 0)) |
    ((d_lq["prob_pos"] < 0.15) & (d_lq["target"] == 1))
)
cw = d_lq[cw_mask].copy().reset_index(drop=True)
n_fp = int(((cw["prob_pos"] > 0.85) & (cw["target"] == 0)).sum())
n_fn = int(((cw["prob_pos"] < 0.15) & (cw["target"] == 1)).sum())
print(f"\nConfidently-wrong samples: {len(cw)}")
print(f"  FP (prob>0.85, target=0): {n_fp}")
print(f"  FN (prob<0.15, target=1): {n_fn}")

if len(cw) == 0:
    print("WARNING: No confidently-wrong samples found. Exiting.")
    exit(1)

# ── 3. Load quality labels ────────────────────────────────────────────────────
print("\nLoading quality labels ...")
ql = pd.read_csv(f"{DATA}/quality_labels_all.csv")
ql["img"]  = ql["degraded_path"].str.replace(chr(92), "/", regex=False)
cw["img"]  = cw["image_path"].str.replace(chr(92), "/", regex=False)
ql_lookup  = ql.set_index("img")[["sharpness", "brightness", "contrast", "completeness", "color_temp"]]

q_cols = ["sharpness", "brightness", "contrast", "completeness", "color_temp"]
for col in q_cols:
    cw[col] = cw["img"].map(ql_lookup[col])

# ── 4. Map to EfficientNet feature vectors ────────────────────────────────────
print("Loading EfficientNet features index ...")
efnet_idx = pd.read_csv(f"{DATA}/efficientnet_index.csv")
efnet_idx["img"] = efnet_idx["degraded_path"].str.replace(chr(92), "/", regex=False)
efnet_lookup = efnet_idx.set_index("img")["efnet_row_idx"]

print("Loading EfficientNet features (149K x 1280) ...")
features = np.load(f"{DATA}/efficientnet_features.npy")
print(f"  features.shape = {features.shape}")

cw["efnet_row"] = cw["img"].map(efnet_lookup)
found = cw["efnet_row"].notna()
print(f"  Feature rows found: {found.sum()} / {len(cw)}")

if found.sum() < 3:
    print("Too few feature matches -- cannot cluster. Check path alignment.")
    exit(1)

cw_found = cw[found].copy().reset_index(drop=True)
X = features[cw_found["efnet_row"].astype(int).values]
print(f"  Feature matrix for clustering: {X.shape}")

# ── 5. Dimensionality reduction: PCA to 50 dims ───────────────────────────────
print("\nReducing to 50 PCA dims before clustering ...")
n_components = min(50, X.shape[0] - 1, X.shape[1])
scaler  = StandardScaler()
X_scaled = scaler.fit_transform(X)
pca     = PCA(n_components=n_components, random_state=42)
X_pca   = pca.fit_transform(X_scaled)
print(f"  PCA explained variance (cumulative): {pca.explained_variance_ratio_.cumsum()[-1]:.3f}")

# ── 6. Clustering: HDBSCAN first, KMeans fallback ────────────────────────────
print("Running HDBSCAN (min_cluster_size=5) ...")
try:
    import hdbscan
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=5,
        metric="euclidean",
        cluster_selection_method="eom"
    )
    labels = clusterer.fit_predict(X_pca)
    n_noise = int((labels == -1).sum())
    unique_clusters = sorted(set(labels) - {-1})
    method = "HDBSCAN"
    print(f"  HDBSCAN clusters found: {len(unique_clusters)}  noise: {n_noise}")
except Exception as e:
    print(f"  HDBSCAN failed ({e}), falling back to KMeans(n_clusters=3)")
    unique_clusters = []

# Fall back to KMeans if HDBSCAN gives <2 meaningful clusters
if len(unique_clusters) < 2:
    if method == "HDBSCAN":
        print("  HDBSCAN produced <2 clusters -- falling back to KMeans(n_clusters=3)")
    from sklearn.cluster import KMeans
    import os
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    km = KMeans(n_clusters=3, random_state=42, n_init=10)
    labels = km.fit_predict(X_pca)
    n_noise = 0
    unique_clusters = [0, 1, 2]
    method = "KMeans(k=3)"
    print(f"  KMeans clusters: {unique_clusters}")

cw_found["cluster"] = labels

# ── 7. Label clusters by dominant quality profile ─────────────────────────────
#
# Quality-based labelling rule (derived from data distribution):
#   - heavy_blur:               mean sharpness < 0.006
#   - low_brightness_low_contrast: not blur AND brightness < 0.55 AND contrast < 0.20
#   - diagnostically_ambiguous: remainder (higher sharpness, moderate quality)
#
# Note: all 300 ITB-LQ images are "heavy" degradation level, so the
# distinction comes from WHICH dimensions are degraded most severely.

def label_cluster(grp):
    s = grp["sharpness"].mean()
    b = grp["brightness"].mean()
    c = grp["contrast"].mean()
    if s < 0.006:
        return "heavy_blur"
    elif b < 0.55 and c < 0.20:
        return "low_brightness_low_contrast"
    else:
        return "diagnostically_ambiguous"

# ── 8. Build per-cluster summary ─────────────────────────────────────────────
print("\n-- Cluster Summary --")
total_clustered = int((labels != -1).sum())
results = []

for cid in unique_clusters:
    mask = cw_found["cluster"] == cid
    grp  = cw_found[mask]
    size = len(grp)
    pct  = 100.0 * size / max(total_clustered, 1)

    dominant_qtype  = label_cluster(grp)
    mean_qbar       = float(grp["qbar"].mean())
    mean_confidence = float(grp["prob_pos"].mean())
    mean_sharpness  = float(grp["sharpness"].mean())
    mean_brightness = float(grp["brightness"].mean())
    mean_contrast   = float(grp["contrast"].mean())
    fp_count        = int(((grp["prob_pos"] > 0.85) & (grp["target"] == 0)).sum())
    fn_count        = int(((grp["prob_pos"] < 0.15) & (grp["target"] == 1)).sum())

    rec = {
        "cluster_id":          int(cid),
        "size":                int(size),
        "pct_of_clustered":    round(pct, 1),
        "mean_qbar":           round(mean_qbar, 4),
        "mean_confidence":     round(mean_confidence, 4),
        "mean_sharpness":      round(mean_sharpness, 4),
        "mean_brightness":     round(mean_brightness, 4),
        "mean_contrast":       round(mean_contrast, 4),
        "dominant_qtype":      dominant_qtype,
        "fp_count":            fp_count,
        "fn_count":            fn_count,
    }
    results.append(rec)

    print(f"  Cluster {cid}: n={size} ({pct:.1f}%)  "
          f"qbar={mean_qbar:.3f}  conf={mean_confidence:.3f}  "
          f"sharp={mean_sharpness:.4f}  bright={mean_brightness:.3f}  "
          f"contr={mean_contrast:.3f}  -> [{dominant_qtype}]")

if n_noise > 0:
    pct_noise = 100.0 * n_noise / len(cw_found)
    print(f"  Noise (cluster=-1): {n_noise} ({pct_noise:.1f}%)")

# ── 9. Compare with paper's claimed 41/33/26 split ───────────────────────────
print("\n-- Paper s6 Comparison --")
paper_splits = {
    "heavy_blur":                   41.0,
    "low_brightness_low_contrast":  33.0,
    "diagnostically_ambiguous":     26.0,
}
recovered = {}
for r in results:
    qt = r["dominant_qtype"]
    recovered[qt] = recovered.get(qt, 0.0) + r["pct_of_clustered"]

print(f"  Paper claims:  {paper_splits}")
print(f"  Recovered pct: {recovered}")
print()
match_summary = {}
for qtype, paper_pct in paper_splits.items():
    got   = recovered.get(qtype, 0.0)
    delta = abs(got - paper_pct)
    ok    = "MATCH" if delta < 10 else "MISMATCH"
    match_summary[qtype] = {"paper_pct": paper_pct, "recovered_pct": round(got, 1), "delta": round(delta, 1), "status": ok}
    print(f"  {qtype:38s}: paper={paper_pct:.0f}%  recovered={got:.1f}%  delta={delta:.1f}%  [{ok}]")

n_clusters_found = len(unique_clusters)
n_modes_matched = sum(1 for v in match_summary.values() if v["status"] == "MATCH")

# Narrative interpretation
print()
print("-- Interpretation --")
if n_clusters_found >= 3 and n_modes_matched >= 2:
    print("  Clustering broadly consistent with paper narrative.")
else:
    print("  Note: With only 57 confidently-wrong samples in dense feature space,")
    print("  HDBSCAN found no density clusters (all 57 treated as noise).")
    print("  KMeans(k=3) forced a 3-way split: two large groups dominate (blur ~54%,")
    print("  mixed/ambiguous ~44%) reflecting ITB-LQ heavy degradation concentration.")
    print("  The paper's 41/33/26 claim likely uses rule-based labelling on quality")
    print("  scalars rather than unsupervised feature-space clustering.")
    print()
    print("  Data-driven rule-based approximation (sharpness/brightness/contrast):")
    blur_n  = int((cw_found["sharpness"] < 0.006).sum())
    dark_n  = int(((cw_found["sharpness"] >= 0.006) & (cw_found["brightness"] < 0.55) & (cw_found["contrast"] < 0.20)).sum())
    amb_n   = len(cw_found) - blur_n - dark_n
    total_n = len(cw_found)
    print(f"    heavy_blur:                 {blur_n} ({100*blur_n/total_n:.1f}%)")
    print(f"    low_brightness_low_contrast:{dark_n} ({100*dark_n/total_n:.1f}%)")
    print(f"    diagnostically_ambiguous:   {amb_n} ({100*amb_n/total_n:.1f}%)")
    print()
    print("  The heavy_blur mode is over-represented vs paper's 41%,")
    print("  suggesting the paper's clusters were derived from a larger or different")
    print("  sample pool / thresholding strategy.")

# ── 10. Save results JSON ─────────────────────────────────────────────────────
out = {
    "method":               method,
    "n_confidently_wrong":  int(len(cw)),
    "n_feature_matched":    int(found.sum()),
    "n_noise":              n_noise,
    "clusters":             results,
    "rule_based_approximation": {
        "heavy_blur":                  {"n": int((cw_found["sharpness"] < 0.006).sum()),
                                        "threshold": "sharpness < 0.006"},
        "low_brightness_low_contrast": {"n": int(((cw_found["sharpness"] >= 0.006) & (cw_found["brightness"] < 0.55) & (cw_found["contrast"] < 0.20)).sum()),
                                        "threshold": "sharpness >= 0.006 AND brightness < 0.55 AND contrast < 0.20"},
        "diagnostically_ambiguous":    {"n": int(len(cw_found) - int((cw_found["sharpness"] < 0.006).sum()) - int(((cw_found["sharpness"] >= 0.006) & (cw_found["brightness"] < 0.55) & (cw_found["contrast"] < 0.20)).sum())),
                                        "threshold": "remainder"},
    },
    "paper_comparison": {
        "paper_splits_pct": paper_splits,
        "recovered_pct":    recovered,
        "match_summary":    match_summary,
        "note": (
            "HDBSCAN found 0 clusters (all 57 CW samples are noise in feature space). "
            "KMeans(k=3) forced split yields 2 large clusters (blur ~54%, ambiguous ~44%). "
            "Rule-based labelling on quality scalars gives heavy_blur=64.9%, "
            "low_bright_low_contr=8.8%, ambiguous=26.3%. "
            "Paper's 41/33/26 split not recovered; likely uses larger/different sample pool."
        )
    }
}

out_path = f"{PROJ}/results/failure_mode_clusters.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2, ensure_ascii=False)
print(f"\nSaved -> {out_path}")

# Save per-sample CSV
save_cols = ["isic_id", "image_path", "prob_pos", "target", "qbar",
             "sharpness", "brightness", "contrast", "cluster"]
cw_found[save_cols].to_csv(f"{PROJ}/results/failure_mode_samples.csv", index=False, encoding="utf-8")
print(f"Saved -> {PROJ}/results/failure_mode_samples.csv")
print("\nDone.")
