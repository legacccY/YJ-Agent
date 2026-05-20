# ITB v1.0 — Image Triage Benchmark

## Overview

ITB (Image Triage Benchmark) is a quality-stratified evaluation protocol for
assessing calibration under image quality shift in dermatology AI. It partitions
four public dermoscopy datasets into quality-stratified subsets using a learned
5-dimensional quality scalar.

**Version**: 1.0  
**License (protocol & code)**: MIT  
**License (metadata)**: CC-BY-NC-SA 4.0  
**Raw images**: Each source dataset retains its original license (see below).

## Dataset Statistics

| Subset      | Source       | n     | Quality range | Purpose |
|-------------|--------------|-------|---------------|---------|
| ITB-LQ      | ISIC 2020    | 300   | q̄ < 0.45     | Low-quality calibration test |
| ITB-Edge    | ISIC 2020    | 660   | q̄ ∈ [0.45, 0.55] | Calibration proxy / borderline |
| ITB-HQ      | ISIC 2020    | 360   | q̄ > 0.50     | High-quality calibration test |
| ITB-Diverse | FitzPatrick17k | 1500 | Full range    | Fairness / skin-type diversity |

**Total**: 2,820 images (metadata only; raw images from original sources)

## Quality Dimensions

Each image has a 5-dimensional quality vector q ∈ [0,1]^5:

| Dimension | Name             | PLCC  | SRCC  |
|-----------|------------------|-------|-------|
| q1        | Sharpness        | 0.947 | 0.863 |
| q2        | Brightness       | 0.987 | 0.986 |
| q3        | Completeness     | 0.731 | 0.689 |
| q4        | Colour temperature | 0.992 | 0.990 |
| q5        | Contrast         | 0.961 | 0.945 |

q̄ = mean(q1,...,q5) is the aggregate quality scalar used for ITB partitioning.

## Files

| File | Description |
|------|-------------|
| `itb_subsets.csv` | isic_id, subset, qbar, q1-q5, target, split |
| `itb_predictions.csv` | Predictions for 9 baseline methods (prob_pos, entropy) |
| `qcts_itb_predictions.csv` | QCTS-calibrated predictions |
| `iqa_checkpoint.pth` | Trained 5-head IQA module (EfficientNet-B0) |

## Citation

If you use ITB in your work, please cite:

```bibtex
@inproceedings{anonymous2026itb,
  title  = {Quality-Aware Calibration: Exposing and Mitigating Calibration
            Collapse under Image Quality Shift in Dermatology AI},
  author = {Anonymous},
  booktitle = {British Machine Vision Conference (BMVC)},
  year   = {2026},
}
```

## Source Dataset Licenses

- ISIC 2020: CC-BY-NC 4.0 (https://challenge2020.isic-archive.com/)
- FitzPatrick17k: CC-BY 4.0 (https://github.com/mattgroh/fitzpatrick17k)
- HAM10000: CC-BY-NC-SA 4.0
- PAD-UFES-20: CC-BY 4.0
