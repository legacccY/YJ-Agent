# Data

Four public dermoscopy datasets; download from the original sources. Pre-computed q-scores, predictions, and the IQA checkpoint come from the ITB v1.0 Zenodo record (DOI activated after acceptance):

```
python scripts/download_itb.py --data_dir ./data
```

## Sources

- ISIC 2020, ~10 GB, CC-BY-NC 4.0 — https://challenge2020.isic-archive.com/ — extract the training ZIP to `data/isic2020/`.
- FitzPatrick17k, ~2 GB, CC-BY 4.0 — https://github.com/mattgroh/fitzpatrick17k — `python data/download_fitzpatrick17k.py --output data/fitzpatrick17k/`.
- HAM10000, ~3 GB, CC-BY-NC-SA 4.0 — https://www.kaggle.com/datasets/kmader/skin-lesion-analysis-toward-melanoma-detection — extract to `data/ham10000/`.
- PAD-UFES-20, ~0.4 GB, CC-BY 4.0 — https://data.mendeley.com/datasets/zr7vgbcyr2/1 — extract to `data/pad_ufes/`.

## Layout

```
data/
  itb_subsets.csv             (Zenodo)
  itb_predictions.csv         (Zenodo)
  qcts_itb_predictions.csv    (Zenodo)
  iqa_checkpoint.pth          (Zenodo)
  isic2020/train/             (images)
  isic2020/train.csv          (metadata)
  fitzpatrick17k/images/
  fitzpatrick17k/fitzpatrick17k.csv
  ham10000/images/
  pad_ufes/images/
```
