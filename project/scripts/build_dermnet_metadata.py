"""Build DermNet metadata CSV for L7 cross-domain (clinical-photo skin domain).

DermNet is a clinical (non-dermoscopy) dermatology atlas with 23 disease-class
folders under train/ and test/. For the malignant-vs-benign neoplasm proxy we keep
ONLY the two unambiguous tumour classes and pool train+test (cross-domain eval is
frozen inference, no training):

  malignant (target=1): "Actinic Keratosis Basal Cell Carcinoma and other Malignant Lesions"
  benign    (target=0): "Seborrheic Keratoses and other Benign Tumors"

EXCLUDED:
  - "Melanoma Skin Cancer Nevi and Moles" -> melanoma + benign nevi share one folder
    (label ambiguous, cannot split) -> dropped to keep the binary clean.
  - 20 inflammatory / infectious classes -> not the neoplasm axis.

Emits data/external/dermnet/dermnet_metadata.csv with columns:
  image_id (path relative to dermnet root, includes .jpg), label (folder name).

precompute_external_features.py then reads this via build_index() and computes
q_bar / ABCD / efnet features itself (do NOT pre-write index.csv).
"""
from pathlib import Path
import pandas as pd

ROOT = Path("D:/YJ-Agent/data/external/dermnet")
MALIGNANT = "Actinic Keratosis Basal Cell Carcinoma and other Malignant Lesions"
BENIGN = "Seborrheic Keratoses and other Benign Tumors"
KEEP = {MALIGNANT, BENIGN}
EXTS = {".jpg", ".jpeg", ".png"}

rows = []
for split in ("train", "test"):
    for cls in KEEP:
        d = ROOT / split / cls
        if not d.exists():
            print(f"[warn] missing {d}")
            continue
        for p in d.iterdir():
            if p.suffix.lower() in EXTS:
                rel = p.relative_to(ROOT).as_posix()
                rows.append({"image_id": rel, "label": cls, "split": split})

df = pd.DataFrame(rows)
out = ROOT / "dermnet_metadata.csv"
df.to_csv(out, index=False)
n_mal = (df["label"] == MALIGNANT).sum()
n_ben = (df["label"] == BENIGN).sum()
print(f"DermNet metadata: {len(df)} images -> {out}")
print(f"  malignant (AK/BCC): {n_mal}  |  benign (SK): {n_ben}")
print(f"  split: train={int((df['split']=='train').sum())} test={int((df['split']=='test').sum())}")
