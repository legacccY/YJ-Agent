# Teaser figure — representative image candidates

All paths relative to `project/meeting/BMVC/figures/teaser_source/candidates/`.

## Part A — ITB Stratification (4 panels)

Source: `project/results/itb_subsets.csv` (4 subsets, total 2,820 images).

### ITB_LQ/  (n=300, q̄ ∈ [0.00, 0.45), heavy degradation, ISIC 2020 paired_dataset/heavy)

Selected: 6 lowest-q̄ examples — strong vignette/blur/exposure failures.

| q̄       | file |
|---------|------|
| 0.054   | ISIC_1810790.jpg |
| 0.126   | ISIC_8319711.jpg |
| 0.131   | ISIC_8325226.jpg |
| 0.133   | ISIC_6060741.jpg |
| 0.146   | ISIC_9256438.jpg |
| 0.160   | ISIC_5902734.jpg |

### ITB_EDGE/  (n=660, q̄ ∈ [0.40, 0.55], light/medium degradation, ISIC 2020)

Selected: 3 near-lower-edge (~0.40) + 3 near-upper-edge (~0.55).

| q̄       | file |
|---------|------|
| 0.400   | ISIC_0914168.jpg |
| 0.400   | ISIC_4263521.jpg |
| 0.407   | ISIC_6509682.jpg |
| 0.549   | ISIC_1255336.jpg |
| 0.549   | ISIC_6398669.jpg |
| 0.550   | ISIC_9335977.jpg |

### ITB_HQ/  (n=360, q̄ > 0.50, originals, ISIC 2020)

Selected: 6 highest-q̄ examples — sharp, well-lit, fully framed.

| q̄       | file |
|---------|------|
| 0.814   | ISIC_1162337.jpg |
| 0.810   | ISIC_7788318.jpg |
| 0.785   | ISIC_1193108.jpg |
| 0.765   | ISIC_9560483.jpg |
| 0.756   | ISIC_8713598.jpg |
| 0.745   | ISIC_9460903.jpg |

### ITB_DIVERSE/  (n=1500 cap, FitzPatrick17k, Fitzpatrick I–VI balanced)

Selected: 2 per Fitzpatrick scale (I–VI), prefix `I_1__` … `VI_6__` for sort order. Use one per palette slot in the I–VI strip.

## Part B — Source datasets (4 boxes × 2 images)

### DS_ISIC2020/
- ISIC_1162337.jpg  (high-quality dermoscopy, dark lesion)
- ISIC_7788318.jpg  (high-quality dermoscopy)

### DS_FP17k/
- ca108f21bba9d295a68be0606aab16ae.jpg  (Fitzpatrick IV)
- b20dd9c72a9fdde160b8d26af140a852.jpg  (Fitzpatrick VI — showcases dataset's diversity strength)

### DS_HAM10000/  (dx = mel)
- ISIC_0025964.jpg
- ISIC_0030623.jpg

### DS_PADUFES/  (diagnostic = MEL, clinical smartphone photos)
- PAT_680_1289_182.png
- PAT_995_1867_5.png

---

## Notes

- ITB-LQ/EDGE/HQ ISIC images come from the **degraded paired_dataset** (`light`/`medium`/`heavy`) — these are the actual benchmark inputs, not the clean originals.
- ITB-HQ images are the **clean originals** (q̄ computed on original ISIC 2020 train images).
- All q̄ values are means of `[sharpness, brightness, completeness, color_temp, contrast]` from `data/quality_labels_all.csv`.
- FP17k Fitzpatrick scale joined from `data/raw/fitzpatrick17k/fitzpatrick17k.csv`.
