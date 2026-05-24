# ITB + QCTS code

Code for the BMVC 2026 submission *Quality-Aware Calibration: Exposing and Mitigating Calibration Collapse under Image Quality Shift in Dermatology AI* (anonymous).

## Install

Python 3.10, PyTorch 2.7 (CUDA 12.6). Pinned versions in `requirements.txt`.

```
pip install -r requirements.txt
```

A Docker image is provided (`Dockerfile`, `docker-compose.yml`); on a single GPU `bash reproduce.sh` runs the Table 1 pipeline end to end (about 2 hours on an A100, 8 hours on a 4070).

## Layout

```
itb/             ECE, QCDI, Spearman, bootstrap CI; evaluate.py runs the full ITB pass
qcts/            QCTSCalibrator: fit T0, alpha by L-BFGS, predict
iqa/             5-head IQA module (EfficientNet-B0 backbone)
baselines/       scalar temperature scaling
scripts/         download_itb.py, run_qcts.py, generate_tables.py, threshold_sensitivity.py
configs/         default.yaml
data/            README on how to fetch raw images
```

## Using QCTS on a different model

```python
from qcts import QCTSCalibrator
cal = QCTSCalibrator().fit(val_logits, val_qbar, val_targets)
prob = cal.predict(test_logits, test_qbar)
```

`qbar` is any per-input scalar in [0,1]: the trained 5-head module for dermoscopy, Laplacian variance, BRISQUE, or corruption severity (Sec. 5.5 of the paper). All give different alpha; only the dermoscopy 5-head reaches QCDI<0 on Std VIB.

## Data

`scripts/download_itb.py` pulls the ITB v1.0 metadata (image IDs, q-scores, splits, degradation manifests). Raw images come from ISIC 2020, HAM10000, PAD-UFES, FitzPatrick17k under their original licenses; see `data/README.md`. ITB metadata: CC-BY-NC-SA 4.0, DOI to be activated after acceptance.

## Reproducing the paper

`bash reproduce.sh` covers Table 1. `python scripts/run_qcts.py --backbone all` produces Table 3. `python scripts/threshold_sensitivity.py` covers supplementary Sec. A14.

## License

Code MIT (`LICENSE`); ITB metadata CC-BY-NC-SA 4.0 (`DATASET_CARD.md`).
