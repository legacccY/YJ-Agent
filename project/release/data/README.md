# Data Download Instructions

ITB v1.0 uses four public dermoscopy datasets. Download them from their original sources.

## ITB v1.0 Metadata (Zenodo)

Pre-computed quality scores, predictions, and subset assignments:

```bash
python scripts/download_itb.py --data_dir ./data
```

This downloads `itb_subsets.csv`, `itb_predictions.csv`, and the IQA checkpoint.
**Zenodo DOI will be activated upon paper acceptance.**

---

## Raw Images

### ISIC 2020 (primary, required)
- URL: https://challenge2020.isic-archive.com/
- License: CC-BY-NC 4.0
- Size: ~10 GB
- Download the training set ZIP; extract to `data/isic2020/`

### FitzPatrick17k (ITB-Diverse)
- URL: https://github.com/mattgroh/fitzpatrick17k
- License: CC-BY 4.0
- Size: ~2 GB
- Clone the upstream repo and follow its image-download instructions (it ships a
  URL list + downloader); place the images under `data/fitzpatrick17k/images/` and
  the metadata CSV at `data/fitzpatrick17k/fitzpatrick17k.csv`. Only the `isic_id`/
  image keys listed in `itb_subsets.csv` are needed for ITB.

### HAM10000 (zero-shot transfer)
- URL: https://www.kaggle.com/datasets/kmader/skin-lesion-analysis-toward-melanoma-detection
- License: CC-BY-NC-SA 4.0
- Size: ~3 GB
- Extract to `data/ham10000/`

### PAD-UFES-20 (zero-shot transfer)
- URL: https://data.mendeley.com/datasets/zr7vgbcyr2/1
- License: CC-BY 4.0
- Size: ~0.4 GB
- Extract to `data/pad_ufes/`

---

## Directory Layout

After downloading:

```
data/
├── itb_subsets.csv           (from Zenodo, auto-downloaded)
├── itb_predictions.csv       (from Zenodo, auto-downloaded)
├── qcts_itb_predictions.csv  (from Zenodo, auto-downloaded)
├── iqa_checkpoint.pth        (from Zenodo, auto-downloaded)
├── isic2020/
│   ├── train/                (JPEG images)
│   └── train.csv             (metadata)
├── fitzpatrick17k/
│   ├── images/
│   └── fitzpatrick17k.csv
├── ham10000/
│   └── images/
└── pad_ufes/
    └── images/
```
