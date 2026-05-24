# ITB v1.0

Quality-stratified evaluation protocol for dermatology calibration. Four public dermoscopy datasets are partitioned by a 5-dimensional learned quality scalar (sharpness, brightness, completeness, colour temperature, contrast); per-dimension PLCC 0.731–0.992 (SRCC 0.689–0.990) on a held-out IQA test split, with completeness the weakest. The aggregate q̄ = mean(q1..q5) drives the LQ/Edge/HQ/Diverse partition.

Version 1.0. Protocol and code under MIT; metadata under CC-BY-NC-SA 4.0; raw images retain their source licenses.

## Subsets

| Subset      | Source         | n    | q̄ range     |
|-------------|----------------|------|--------------|
| ITB-LQ      | ISIC 2020      | 300  | < 0.45       |
| ITB-Edge    | ISIC 2020      | 660  | [0.45, 0.55] |
| ITB-HQ      | ISIC 2020      | 360  | > 0.50       |
| ITB-Diverse | FitzPatrick17k | 1500 | full         |

Total 2,820 images, metadata only.

## Files

- `itb_subsets.csv` — isic_id, subset, qbar, q1–q5, target, split
- `itb_predictions.csv` — 9 baseline predictions (prob_pos, entropy)
- `qcts_itb_predictions.csv` — QCTS-calibrated predictions
- `iqa_checkpoint.pth` — trained 5-head IQA module (EfficientNet-B0 backbone)

## Sources

ISIC 2020 (CC-BY-NC 4.0, https://challenge2020.isic-archive.com/), HAM10000 (CC-BY-NC-SA 4.0), PAD-UFES-20 (CC-BY 4.0), FitzPatrick17k (CC-BY 4.0, https://github.com/mattgroh/fitzpatrick17k).

## Citation

```
@inproceedings{anonymous2026itb,
  title  = {Quality-Aware Calibration: Exposing and Mitigating Calibration
            Collapse under Image Quality Shift in Dermatology AI},
  author = {Anonymous},
  booktitle = {BMVC},
  year   = {2026},
}
```
